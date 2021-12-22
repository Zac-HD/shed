"""Shed canoncalises your code.

It works on all Python files in the current git repository; or you can
pass the names of specific files to format instead.
"""

import argparse
import functools
import multiprocessing
import os
import subprocess
import sys
import warnings
from pathlib import Path
from typing import FrozenSet, Union

import autoflake

from . import ShedSyntaxWarning, _version_map, docshed, shed


@functools.lru_cache()
def _guess_first_party_modules(cwd: str = None) -> FrozenSet[str]:
    """Guess the name of the current package for first-party imports."""
    try:
        base = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            timeout=10,
            stdout=subprocess.PIPE,
            text=True,
            cwd=cwd,
        ).stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return frozenset()
    provides = {init.name for init in Path(base).glob("**/src/*/__init__.py")}
    return frozenset(p for p in {Path(base).name} | provides if p.isidentifier())


@functools.lru_cache(maxsize=None)
def _should_format(fname: str) -> bool:
    return fname.endswith((".md", ".rst")) or autoflake.is_python_file(fname)


def _rewrite_on_disk(
    fname: str, **kwargs: Union[bool, FrozenSet[str]]
) -> Union[bool, str]:
    """Return either bool(rewrote the file), or an error message string."""
    try:
        with open(fname) as handle:
            on_disk = handle.read()
    except (OSError, UnicodeError) as err:
        # Permissions or encoding issue, or file deleted since last commit.
        return f"skipping {fname!r} due to {err}"
    writer = docshed if fname.endswith((".md", ".rst")) else shed
    msg = ""
    try:
        with warnings.catch_warnings(record=True) as record:
            result = writer(on_disk, _location=f"file {fname!r}", **kwargs)
    except Exception as err:  # pragma: no cover  # bugs are unknown xor fixed ;-)
        if "SHED_RAISE" in os.environ:
            raise
        return (
            f"Internal error formatting {fname!r}: {type(err).__name__}: {err}\n"
            "    Please report this to https://github.com/Zac-HD/shed/issues"
        )
    else:
        msg = "\n".join(
            str(w.message) for w in record if issubclass(w.category, ShedSyntaxWarning)
        )
        for w in record:  # pragma: no cover  # just being careful not to hide anything
            if not issubclass(w.category, ShedSyntaxWarning):
                warnings.warn(w.message, category=w.category, stacklevel=2)
    if result != on_disk:
        with open(fname, mode="w") as fh:
            fh.write(result)
    return msg or result != on_disk


def cli() -> None:  # pragma: no cover  # mutates things in-place, will test later.
    """Execute the `shed` CLI."""
    # TODO: make this provide useful CLI help and usage hints
    parser = argparse.ArgumentParser(prog="shed", description=__doc__.strip())
    parser.add_argument(
        "--refactor",
        action="store_true",
        help="Run additional passes to refactor code",
    )
    parser.add_argument(
        nargs="*",
        metavar="file",
        dest="files",
        help="File(s) to format, instead of autodetection",
    )
    min_version_group = parser.add_mutually_exclusive_group()
    oldest, *rest = sorted(_version_map.values())
    parser.set_defaults(min_version=oldest)
    for version in rest:
        min_version_group.add_argument(
            f"--py3{version[1]}-plus",
            action="store_const",
            dest="min_version",
            const=version,
        )
    args = parser.parse_args()

    if args.files:
        all_filenames = args.files
    else:
        # Get all tracked files from `git ls-files`
        try:
            all_filenames = subprocess.run(
                ["git", "ls-files"],
                check=True,
                timeout=10,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.splitlines()
        except (subprocess.SubprocessError, FileNotFoundError):
            print("Doesn't seem to be a git repo; pass filenames to format.")  # noqa
            sys.exit(1)
        all_filenames = [f for f in all_filenames if _should_format(f)]

    rewrite = functools.partial(
        _rewrite_on_disk,
        first_party_imports=_guess_first_party_modules(),
        refactor=args.refactor,
        min_version=args.min_version,
    )

    if len(all_filenames) > 4:
        # If we're formatting more than a few files, the improved throughput
        # of a process pool probably covers the startup cost.
        try:
            with multiprocessing.Pool() as pool:
                for error_msg in pool.imap_unordered(rewrite, all_filenames):
                    if isinstance(error_msg, str):
                        print(error_msg)  # noqa
            return
        except BlockingIOError as err:  # pragma: no cover
            # This can occur when `os.fork()` fails due to limited available
            # memory or number-of-processes.  In this case, we fall back to
            # the slow path; and reprocess whatever we've already done for
            # simplicity.  See https://stackoverflow.com/q/44534288/
            print(f"Error: {err!r}\n    Falling back to serial mode.")  # noqa

    for fname in all_filenames:
        error_msg = rewrite(fname)
        if isinstance(error_msg, str):
            print(error_msg)  # noqa
