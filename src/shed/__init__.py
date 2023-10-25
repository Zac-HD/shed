"""Shed canoncalises your code.

It works on all Python files in the current git repository; or you can
pass the names of specific files to format instead.
"""

import functools
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import warnings
from contextlib import contextmanager
from operator import attrgetter
from typing import Any, FrozenSet, Generator, Match, Tuple

import black
from black.mode import TargetVersion
from black.parsing import lib2to3_parse

__version__ = "2023.6.1"
__all__ = ["shed", "docshed"]

# Conditionally imported in refactor mode to reduce startup latency in the common case
com2ann: Any = None
_run_codemods: Any = None

_version_map = {
    k: (int(k.name[2]), int(k.name[3:]))
    for k in TargetVersion
    if k.value >= TargetVersion.PY38.value
}
_default_min_version = min(_version_map.values())
_SUGGESTIONS = (
    # If we fail on invalid syntax, check for detectable wrong-codeblock types
    (r"^(>>> | ?In \[\d+\]: )", "pycon"),
    (r"^Traceback \(most recent call last\):$", "python-traceback"),
)

_RUFF_TOML = """[lint]
select = ["F", "UP", "I", "C400", "C405"]
target_version = "{target_version}"

[isort]
force-single-line = false
force-wrap-aliases = false
lines-after-imports = false
lines-between-types = false
split-on-trailing-comma = false
"""


@contextmanager
def _ruff_toml(target_version: str) -> Generator[str, None, None]:
    """Context manager to temporarily write a ruff.toml file."""
    # TODO: Use real ruff config file if present?

    with tempfile.NamedTemporaryFile("w", suffix="_ruff.toml") as f:
        f.write(_RUFF_TOML.format(target_version=target_version))
        yield f.name


class ShedSyntaxWarning(SyntaxWarning):
    """Warns that shed has been called on something with invalid syntax."""


@functools.lru_cache
def shed(
    source_code: str,
    *,
    refactor: bool = False,
    is_pyi: bool = False,
    first_party_imports: FrozenSet[str] = frozenset(),
    min_version: Tuple[int, int] = _default_min_version,
    _location: str = "string passed to shed.shed()",
    _remove_unused_imports: bool = True,
) -> str:
    """Process the source code of a single module."""
    assert isinstance(source_code, str)
    assert isinstance(refactor, bool)
    assert isinstance(first_party_imports, frozenset)
    assert all(isinstance(name, str) for name in first_party_imports)
    assert all(name.isidentifier() for name in first_party_imports)
    assert min_version in _version_map.values()

    if source_code == "":
        return ""

    # TODO: Find alternative for black to get target versions
    # Use black to autodetect our target versions
    target_versions = {k for k, v in _version_map.items() if v >= min_version}
    try:
        parsed = lib2to3_parse(source_code.lstrip(), target_versions)
        # black.InvalidInput, blib2to3.pgen2.tokenize.TokenError, SyntaxError...
        # for forwards-compatibility I'm just going general here.
    except Exception as err:
        msg = f"Could not parse {_location}\n    {type(err).__qualname__}: {err}"
        for pattern, blocktype in _SUGGESTIONS:
            if re.search(pattern, source_code, flags=re.MULTILINE):
                msg += f"\n    Perhaps you should use a {blocktype!r} block instead?"
        try:
            compile(source_code, "<string>", "exec")
        except SyntaxError:
            pass
        else:
            msg += (
                f"\n    The syntax is valid for Python {sys.version_info.major}"
                f".{sys.version_info.minor}, so please report this as a bug."
            )
        w = ShedSyntaxWarning(msg)
        w.__cause__ = err
        if "SHED_RAISE" in os.environ:  # pragma: no cover
            raise w
        warnings.warn(w, stacklevel=_location.count(" block in ") + 2)
        return source_code

    target_versions &= set(black.detect_target_versions(parsed))
    assert target_versions
    min_version = max(
        min_version,
        _version_map[min(target_versions, key=attrgetter("value"))],
    )

    if refactor:
        # Here we have a deferred imports section, which is pretty ugly.
        # It does however have one crucial advantage: several hundred milliseconds
        # of startup latency in the common case where --refactor was *not* passed.
        # This is a big deal for interactive use-cases such as pre-commit hooks
        # or format-on-save in editors (though I prefer Black for the latter).
        global com2ann
        global _run_codemods
        if com2ann is None:
            from com2ann import com2ann

            from ._codemods import _run_codemods  # type: ignore

        # Some tools assume that the file is multi-line, but empty files are valid input.
        source_code += "\n"
        # Use com2ann to comvert type comments to annotations
        annotated = com2ann(
            source_code,
            drop_ellipsis=True,
            silent=True,
            python_minor_version=min(min_version[1], sys.version_info[1]),
        )
        if annotated:  # pragma: no branch
            # This can only be None if ast.parse() raises a SyntaxError,
            # which is possible but rare after the parsing checks above.
            source_code, _ = annotated

    with _ruff_toml(f"py3{min_version[1]}") as ruff_toml:
        # run ruff format
        source_code = subprocess.run(
            [
                "ruff",
                "format",
                "--config",
                ruff_toml,
                "-",
            ],
            input=source_code,
            encoding="utf-8",
            check=True,
            capture_output=True,
        ).stdout

        # Run ruff fixes
        source_code = subprocess.run(
            [
                "ruff",
                "check",
                "--fix-only",
                "--unsafe-fixes",
                "--config",
                ruff_toml,
                "-",
            ],
            input=source_code,
            encoding="utf-8",
            check=True,
            capture_output=True,
        ).stdout

    if refactor and not is_pyi:
        source_code = _run_codemods(source_code, min_version=min_version)

    # Remove any extra trailing whitespace
    return source_code.rstrip() + "\n"


@functools.lru_cache
def docshed(
    source: str,
    *,
    refactor: bool = False,
    first_party_imports: FrozenSet[str] = frozenset(),
    min_version: Tuple[int, int] = _default_min_version,
    _location: str = "string passed to shed.docshed()",
) -> str:
    """Process Python code blocks embedded in documentation."""
    # Inspired by the blacken-docs package.
    assert isinstance(source, str)
    assert isinstance(first_party_imports, frozenset)
    assert all(isinstance(name, str) for name in first_party_imports)
    assert all(name.isidentifier() for name in first_party_imports)
    assert min_version in _version_map.values()
    format_code = functools.partial(
        shed,
        refactor=refactor,
        first_party_imports=first_party_imports,
        min_version=min_version,
        _remove_unused_imports=False,
    )

    markdown_pattern = re.compile(
        r"(?P<before>^(?P<indent> *)```python\n)"
        r"(?P<code>.*?)"
        r"(?P<after>^(?P=indent)```\s*$)",
        flags=re.DOTALL | re.MULTILINE,
    )
    rst_pattern = re.compile(
        r"(?P<before>"
        r"^(?P<indent> *)\.\. "
        r"(?P<block>jupyter-execute::|"
        r"invisible-code-block: python|"  # magic rst comment for Sybil doctests
        r"(code|code-block|sourcecode|ipython):: (python|py|sage|python3|py3|numpy))\n"
        r"((?P=indent) +:.*\n)*"
        r"\n*"
        r")"
        r"(?P<code>(^((?P=indent) +.*)?\n)+)",
        flags=re.MULTILINE,
    )

    def _md_match(match: Match[str]) -> str:
        code = textwrap.dedent(match["code"])
        code = format_code(code, _location=f"```python markdown block in {_location}")
        code = textwrap.indent(code, match["indent"])
        return f'{match["before"]}{code}{match["after"]}'

    def _rst_match(match: Match[str]) -> str:
        indent_pattern = re.compile("^ +(?=[^ ])", re.MULTILINE)
        trailing_newline_pattern = re.compile(r"\n+\Z", re.MULTILINE)
        min_indent = min(indent_pattern.findall(match["code"]))
        trailing_ws_match = trailing_newline_pattern.search(match["code"])
        assert trailing_ws_match
        trailing_ws = trailing_ws_match.group()
        code = textwrap.dedent(match["code"])
        code = format_code(
            code, _location=f"{match['block']!r} rst block in {_location}"
        )
        code = textwrap.indent(code, min_indent)
        return f'{match["before"]}{code.rstrip()}{trailing_ws}'

    return rst_pattern.sub(_rst_match, markdown_pattern.sub(_md_match, source))
