"""
Shed canoncalises your code.

It works on all Python files in the current git repository;
or you can pass the names of specific files to format instead.
"""

import argparse
import functools
import subprocess
import sys
from operator import attrgetter
from pathlib import Path
from typing import FrozenSet

import autoflake
import black
import isort
import pyupgrade

__version__ = "0.1.1"
__all__ = ["shed"]

_version_map = {
    black.TargetVersion.PY36: (3, 6),
    black.TargetVersion.PY37: (3, 7),
    black.TargetVersion.PY38: (3, 8),
}


@functools.lru_cache()
def shed(*, source_code: str, first_party_imports: FrozenSet[str] = frozenset()) -> str:
    """Process the source code of a single module."""
    assert isinstance(source_code, str)
    assert isinstance(first_party_imports, frozenset)
    assert all(isinstance(name, str) for name in first_party_imports)
    assert all(name.isidentifier() for name in first_party_imports)

    # Use black to autodetect our target versions
    target_versions = {
        v
        for v in black.detect_target_versions(
            black.lib2to3_parse(source_code.lstrip(), set(_version_map))
        )
        if v.value >= black.TargetVersion.PY36.value
    }
    assert target_versions
    min_version = _version_map[min(target_versions, key=attrgetter("value"))]

    input_code = source_code
    # Autoflake first:
    source_code = autoflake.fix_code(
        source_code,
        expand_star_imports=True,
        remove_all_unused_imports=True,
        remove_duplicate_keys=True,
        remove_unused_variables=True,
    )

    # Now pyupgrade - see pyupgrade._fix_file
    source_code = pyupgrade._fix_tokens(source_code, min_version=min_version)
    source_code = pyupgrade._fix_percent_format(source_code)
    source_code = pyupgrade._fix_py3_plus(source_code, min_version=min_version)

    # Then isort...
    source_code = isort.code(
        source_code,
        known_first_party=first_party_imports,
        profile="black",
        combine_as_imports=True,
    )

    # and finally Black!
    source_code = black.format_str(
        source_code, mode=black.FileMode(target_versions=target_versions)
    )

    if source_code == input_code:
        return source_code
    # If we've modified the code, iterate to a fixpoint.
    # e.g. "pass;#" -> "pass\n#\n" -> "#\n"
    return shed(source_code=source_code, first_party_imports=first_party_imports)


def cli() -> None:  # pragma: no cover  # mutates things in-place, will test later.
    """Execute the `shed` CLI."""
    # TODO: make this provide useful CLI help and usage hints
    # TODO: single-file mode with optional min_version support
    parser = argparse.ArgumentParser(prog="shed", description=__doc__.strip())
    parser.add_argument(
        nargs="*",
        metavar="file",
        dest="files",
        help="File(s) to format, instead of autodetection",
    )
    args = parser.parse_args()

    if args.files:
        first_party_imports: FrozenSet[str] = frozenset()
        all_filenames = args.files
        for f in all_filenames:
            if not autoflake.is_python_file(f):
                print(f"{f!r} does not seem to be a Python file")  # noqa
                sys.exit(1)
    else:
        # Try to work out the name of the current package for first-party imports
        try:
            base = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                check=True,
                timeout=10,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            ).stdout.strip()
        except subprocess.SubprocessError:
            print("Doesn't seem to be a git repo; pass filenames to format.")  # noqa
            sys.exit(1)

        provides = {Path(base).name} | {
            init.name for init in Path(base).glob("**/src/*/__init__.py")
        }
        first_party_imports = frozenset(p for p in provides if p.isidentifier())

        # Get all tracked files from `git ls-files`
        all_filenames = subprocess.run(
            ["git", "ls-files"],
            check=True,
            timeout=10,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        ).stdout.splitlines()
        all_filenames = [f for f in all_filenames if autoflake.is_python_file(f)]

    for fname in all_filenames:
        try:
            with open(fname) as handle:
                on_disk = handle.read()
        except OSError:
            continue  # Permissions issue, or file deleted since last commit.
        result = shed(source_code=on_disk, first_party_imports=first_party_imports)
        if result == on_disk:
            continue
        with open(fname, mode="w") as fh:
            fh.write(result)
