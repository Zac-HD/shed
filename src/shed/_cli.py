"""Shed canoncalises your code.

It works on all Python files in the current git repository; or you can
pass the names of specific files to format instead.
"""

import argparse
import functools
import io
import multiprocessing
import os
import subprocess
import sys
import tokenize
import warnings
from pathlib import Path
from typing import Callable, FrozenSet, Optional, Union

from . import ShedSyntaxWarning, _version_map, docshed, shed
from ._is_python_file import is_python_file

if sys.version_info[:2] > (3, 9):  # pragma: no cover
    from sys import stdlib_module_names
elif sys.version_info[:2] == (3, 9):  # pragma: no cover
    from ._stdlib_module_names.py39 import stdlib_module_names
else:  # pragma: no cover
    from ._stdlib_module_names.py38 import stdlib_module_names


@functools.lru_cache
def _get_git_repo_root(cwd: Optional[str] = None) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        timeout=10,
        capture_output=True,
        text=True,
        cwd=cwd,
    ).stdout.strip()


@functools.lru_cache
def _guess_first_party_modules(cwd: Optional[str] = None) -> FrozenSet[str]:
    """Guess the name of the current package for first-party imports."""
    # Note: this fails inside git worktrees
    try:
        base = _get_git_repo_root(cwd)
    except (subprocess.SubprocessError, FileNotFoundError):
        return frozenset()

    def _walk_path(path: Path) -> set[str]:
        provides = set()
        try:
            for p in path.iterdir():
                if p.name.startswith(".") or not p.is_dir():
                    continue
                if p.name == "src":
                    provides |= {init.parent.name for init in p.glob("*/__init__.py")}
                    # in case of nested src/ directories, like
                    #   src/tools/src/helper/__init__.py
                    provides |= _walk_path(p)
                else:
                    provides |= _walk_path(p)
        except Exception:  # pragma: no cover
            pass

        return provides

    provides = _walk_path(Path(base))
    return frozenset(
        p
        for p in {Path(base).name} | provides
        # TODO: isort.place_module is horrendously complicated, but we only use
        # a fraction of the functionality. So best approach, if we still need
        # the ability to exclude stdlib modules here, is probably to generate a list of
        # known stdlib modules - either dynamically or store in a file.
        if p.isidentifier() and p not in stdlib_module_names
    )


@functools.cache
def _should_format(fname: str) -> bool:
    return fname.endswith((".md", ".rst", ".pyi")) or is_python_file(fname)


def _rewrite_on_disk(
    fname: str, **kwargs: Union[bool, FrozenSet[str]]
) -> Union[bool, str]:
    """Return either bool(rewrote the file), or an error message string."""
    try:
        with open(fname, mode="rb") as handle:
            bytes_on_disk = handle.read()
        encoding, _ = tokenize.detect_encoding(io.BytesIO(bytes_on_disk).readline)
        with io.TextIOWrapper(io.BytesIO(bytes_on_disk), encoding) as wrapper:
            on_disk = wrapper.read()
    except (OSError, UnicodeError) as err:
        # Permissions or encoding issue, or file deleted since last commit.
        err_msg = f"skipping {fname!r} due to {err}"
        if "*" in fname:
            err_msg += ", maybe due to unexpanded glob pattern?"
        return err_msg
    if fname.endswith((".md", ".rst")):
        writer: Callable[..., str] = docshed
    elif fname.endswith(".pyi"):
        writer = functools.partial(shed, is_pyi=True)
    else:
        writer = shed

    msg = ""
    try:
        with warnings.catch_warnings(record=True) as record:
            result = writer(on_disk, _location=f"file {fname!r}", **kwargs)
    except Exception as err:  # pragma: no cover  # bugs are unknown xor fixed ;-)
        if "SHED_RAISE" in os.environ:
            raise
        return (
            f"Skipping {fname!r} due to an internal error: {type(err).__name__}: {err}\n"
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
        with open(fname, mode="w", encoding=encoding) as fh:
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
            root = os.path.relpath(_get_git_repo_root())
            all_filenames = subprocess.run(
                ["git", "ls-files"],
                check=True,
                timeout=10,
                stdout=subprocess.PIPE,
                text=True,
                cwd=root,
            ).stdout.splitlines()
        except (subprocess.SubprocessError, FileNotFoundError):
            print("Doesn't seem to be a git repo; pass filenames to format.")  # noqa
            sys.exit(1)
        all_filenames = [
            os.path.join(root, f) for f in all_filenames if _should_format(f)
        ]

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
