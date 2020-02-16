"""Shed: canoncalises your code."""

import argparse
import functools
import subprocess
from operator import attrgetter

import autoflake
import black
import isort
import pyupgrade

__version__ = "0.0.1"
__all__ = ["shed"]

_version_map = {
    black.TargetVersion.PY36: (3, 6),
    black.TargetVersion.PY37: (3, 7),
    black.TargetVersion.PY38: (3, 8),
}


@functools.lru_cache()
def shed(
    *, source_code: str, min_version: black.TargetVersion = black.TargetVersion.PY36
) -> str:
    """Process the source code of a single module."""
    assert isinstance(source_code, str)
    assert isinstance(min_version, black.TargetVersion)
    assert min_version.value >= black.TargetVersion.PY36.value

    # Use black to autodetect our target versions
    target_versions = black.detect_target_versions(
        black.lib2to3_parse(source_code.lstrip(), set(_version_map))
    )
    target_versions = {v for v in target_versions if v.value >= min_version.value}
    assert target_versions
    min_version = min(target_versions, key=attrgetter("value"))

    input_code = source_code
    # Autoflake first:
    source_code = autoflake.fix_code(
        source_code,
        expand_star_imports=True,
        remove_all_unused_imports=True,
        remove_duplicate_keys=True,
        remove_unused_variables=True,
    )

    # Then isort...
    # TODO: swap to `isort.api.sorted_imports()` as soon as 5.0 is released
    #       (for black compat & to avoid picking up whatever config is around)
    source_code = isort.SortImports(file_contents=source_code).output

    # Now pyupgrade - see pyupgrade._fix_file
    source_code = pyupgrade._fix_tokens(
        source_code, min_version=_version_map[min_version]
    )
    source_code = pyupgrade._fix_percent_format(source_code)
    source_code = pyupgrade._fix_py3_plus(source_code)
    source_code = pyupgrade._fix_fstrings(source_code)

    # and finally Black!
    source_code = black.format_str(
        source_code, mode=black.FileMode(target_versions=target_versions)
    )

    if source_code == input_code:
        return source_code
    # If we've modified the code, iterate to a fixpoint.
    # e.g. "pass;#" -> "pass\n#\n" -> "#\n"
    return shed(source_code=source_code, min_version=min_version)


def cli() -> None:  # pragma: no cover  # mutates things in-place, will test later.
    """Execute the `shed` CLI."""
    # TODO: make this provide useful CLI help and usage hints
    # TODO: single-file mode with optional min_version support
    argparse.ArgumentParser(prog="shed").parse_args()

    # TODO: detect package-level python_requires or default to py36
    min_version = black.TargetVersion.PY36

    # Get all tracked files from `git ls-files`
    all_filenames = subprocess.run(
        ["git", "ls-files"],
        check=True,
        timeout=10,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    ).stdout.splitlines()

    for fname in all_filenames:
        if autoflake.is_python_file(fname):
            with open(fname) as handle:
                on_disk = handle.read()
            result = shed(source_code=on_disk, min_version=min_version)
            if result == on_disk:
                continue
            assert result == shed(source_code=result, min_version=min_version)
            with open(fname, mode="w") as fh:
                fh.write(result)
