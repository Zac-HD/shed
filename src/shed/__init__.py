"""Shed canoncalises your code.

It works on all Python files in the current git repository; or you can
pass the names of specific files to format instead.
"""

import functools
import os
import re
import sys
import textwrap
import warnings
from operator import attrgetter
from typing import Any, FrozenSet, Match, Tuple

import autoflake
import black
import isort
import pyupgrade._main
from black.mode import TargetVersion
from black.parsing import InvalidInput, lib2to3_parse
from isort.exceptions import FileSkipComment

__version__ = "0.10.5"
__all__ = ["shed", "docshed"]

# Conditionally imported in refactor mode to reduce startup latency in the common case
com2ann: Any = None
_run_codemods: Any = None

_version_map = {
    k: (int(k.name[2]), int(k.name[3:]))
    for k in TargetVersion
    if k.value >= TargetVersion.PY37.value
}
_default_min_version = min(_version_map.values())
_SUGGESTIONS = (
    # If we fail on invalid syntax, check for detectable wrong-codeblock types
    (r"^(>>> | In [\d+]: )", "pycon"),
    (r"^Traceback \(most recent call last\):$", "python-traceback"),
)


class ShedSyntaxWarning(SyntaxWarning):
    """Warns that shed has been called on something with invalid syntax."""


def _fallback(source: str, **kw: object) -> Tuple[str, object]:
    return source, None  # pragma: no cover


@functools.lru_cache()
def shed(
    source_code: str,
    *,
    refactor: bool = False,
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

    # Use black to autodetect our target versions
    target_versions = {k for k, v in _version_map.items() if v >= min_version}
    try:
        # Black errors out if we have pattern matching (3.10+), and the target versions
        # include older versions.  Very well; we'll add a temporary workaround.
        try:
            parsed = lib2to3_parse(source_code.lstrip(), target_versions)
        except InvalidInput as err:
            if not re.match(r"Cannot parse: \d+:\d+: match ", str(err)):
                raise
            target_versions = {k for k, v in _version_map.items() if v >= (3, 10)}
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
        # Even if the code itself has invalid syntax, we might be able to
        # regex-match and therefore reformat code embedded in docstrings.
        return docshed(
            source_code,
            refactor=refactor,
            first_party_imports=first_party_imports,
            min_version=min_version,
            _location=_location,
        )
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
            from ._codemods import _run_codemods  # type: ignore

            try:
                from com2ann import com2ann
            except ImportError:  # pragma: no cover  # on Python 3.8
                assert sys.version_info < (3, 8)
                com2ann = _fallback
            # OK, everything's imported, back to the runtime logic!

        # Some tools assume that the file is multi-line, but empty files are valid input.
        source_code += "\n"
        # Use com2ann to comvert type comments to annotations on Python 3.8+
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

    # One tricky thing: running `isort` or `autoflake` can "unlock" further fixes
    # for `black`, e.g. "pass;#" -> "pass\n#\n" -> "#\n".  We therefore run it
    # before other fixers, and then (if they made changes) again afterwards.
    black_mode = black.Mode(target_versions=target_versions)  # type: ignore
    source_code = blackened = black.format_str(source_code, mode=black_mode)

    pyupgrade_min = min(min_version, max(pyupgrade._plugins.imports.REPLACE_EXACT))
    pu_settings = pyupgrade._main.Settings(min_version=pyupgrade_min)
    source_code = pyupgrade._main._fix_plugins(source_code, settings=pu_settings)
    if source_code != blackened:
        # Second step to converge: without this we have f-string problems.
        # Upstream issue: https://github.com/asottile/pyupgrade/issues/703
        source_code = pyupgrade._main._fix_plugins(source_code, settings=pu_settings)
    source_code = pyupgrade._main._fix_tokens(source_code)

    if refactor:
        source_code = _run_codemods(source_code, min_version=min_version)

    try:
        source_code = isort.code(
            source_code,
            known_first_party=first_party_imports,
            known_local_folder={"tests"},
            profile="black",
            combine_as_imports=True,
        )
    except FileSkipComment:
        pass

    source_code = autoflake.fix_code(
        source_code,
        expand_star_imports=True,
        remove_all_unused_imports=_remove_unused_imports,
    )

    if source_code != blackened:
        source_code = black.format_str(source_code, mode=black_mode)

    # Then shed.docshed (below) formats any code blocks in documentation
    source_code = docshed(
        source_code,
        refactor=refactor,
        first_party_imports=first_party_imports,
        min_version=min_version,
        _location=_location,
    )
    # Remove any extra trailing whitespace
    return source_code.rstrip() + "\n"


@functools.lru_cache()
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
