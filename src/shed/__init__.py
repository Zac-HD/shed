"""Shed canoncalises your code.

It works on all Python files in the current git repository; or you can
pass the names of specific files to format instead.
"""

import functools
import os
import re
import subprocess
import sys
import textwrap
import warnings
from operator import attrgetter
from re import Match
from typing import Any, FrozenSet, Tuple

import black
from black.mode import TargetVersion
from black.parsing import lib2to3_parse

__version__ = "2025.6.1"
__all__ = ["shed", "docshed"]

# Conditionally imported in refactor mode to reduce startup latency in the common case
com2ann: Any = None
_run_codemods: Any = None

_version_map = {
    k: (int(k.name[2]), int(k.name[3:]))
    for k in TargetVersion
    if k.value >= TargetVersion.PY39.value
}
_default_min_version = min(_version_map.values())
_SUGGESTIONS = (
    # If we fail on invalid syntax, check for detectable wrong-codeblock types
    (r"^(>>> | ?In \[\d+\]: )", "pycon"),
    (r"^Traceback \(most recent call last\):$", "python-traceback"),
)

_RUFF_RULES = (
    "I",  # isort; sort imports
    "UP",  # pyupgrade
    # F401 # unused-import # added dynamically
    "F841",  # unused-variable # was enabled in autoflake
    # many of these are direct replacements of codemods
    "F901",  # raise NotImplemented -> raise NotImplementedError
    "E711",  # == None -> is None
    "E713",  # not x in y-> x not in y
    "E714",  # not x is y -> x is not y
    "C400",  # unnecessary generator -> list comprehension
    "C401",  # unnecessary generator -> set comprehension
    "C402",  # unnecessary generator -> dict comprehension
    "C403",  # unnecessary list comprehension -> set comprehension
    "C404",  # unnecessary list comprehension -> dict comprehension
    "C405",  # set(...) -> {...}
    "C406",  # dict(...) -> {...}
    "C408",  # empty dict/list/tuple call -> {}/[]/()
    "C409",  # unnecessary-literal-within-tuple-call
    "C410",  # unnecessary-literal-within-list-call
    "C411",  # unnecessary-list-call
    "C413",  # unnecessary-call-around-sorted
    # C415 # fix is not available
    "C416",  # unnecessary-comprehension
    "C417",  # unnecessary-map
    "C418",  # unnecessary-literal-within-dict-call
    "C419",  # unnecessary-comprehension-any-all
    # Disabled pending https://github.com/astral-sh/ruff/issues/10538
    # "PIE790",  # unnecessary-placeholder; unnecessary pass/... statement
    "SIM101",  # duplicate-isinstance-call # Replacing `collapse_isinstance_checks`
    # partially replaces assert codemod
    "B011",  # assert False -> raise
    # ** Codemods that could be replaced once ruffs implementation improves
    # "PT018",  # break up composite assertions # codemod: `split_assert_and`
    # Ruff implementation gives up when reaching end of line regardless of python version.
    # "SIM117", # multiple-with-statement # codemod: `remove_nested_with`
    # https://github.com/astral-sh/ruff/issues/10245
    # ruff replaces `sorted(reversed(iterable))` with `sorted(iterable)`
    # "C414", # unnecessary-double-cast # codemod: `replace_unnecessary_nested_calls`
    #
    #
    # ** These are new fixes that Zac had enabled in his branch
    # "E731", # don't assign lambdas
    # "B007",  # unused loop variable
    # "B009",  # constant getattr
    # "B010",  # constant setattr
    # "B013",  # catching 1-tuple
    # "PIE807"  # reimplementing list
    # "PIE810",  # repeated startswith/endswith
    # "RSE102",  # Unnecessary parentheses on raised exception
    # "RET502",  # `return None` if could return non-None
    # "RET504",  # Unnecessary assignment before return statement
    # "SIM110",  # Use any or all
    # "TCH005",  # remove `if TYPE_CHECKING: pass`
    # "PLR1711",  # remove useless trailing return
    # "TRY201",  # `raise` without name
    # "FLY002",  # static ''.join to f-string
    # "NPY001",  # deprecated np type aliases
    # "RUF010",  # f-string conversions
)
_RUFF_EXTEND_SAFE_FIXES = (
    "F841",  # unused variable
    # Several of C4xx rules are marked unsafe:
    # "This rule's fix is marked as unsafe, as it may occasionally drop comments when rewriting the call. In most cases, though, comments will be preserved."
    "C400",
    "C401",
    "C402",
    "C403",
    "C404",
    "C405",
    "C406",
    "C408",
    "C409",
    "C410",
    "C411",
    # 'C414',  # currently disabled
    "C416",
    "C417",
    "C418",
    "C419",
    # not stated as unsafe by docs, but actually requires --unsafe-fixes
    "SIM101",
    "E711",
    "UP031",
    # This rule's fix is marked as unsafe, as reversed and reverse=True will yield different results in the event of custom sort keys or equality functions. Specifically, reversed will reverse the order of the collection, while sorted with reverse=True will perform a stable reverse sort, which will preserve the order of elements that compare as equal.
    "C413",
    # This rule's fix is marked as unsafe, as changing an assert to a raise will change the behavior of your program when running in optimized mode (python -O).
    "B011",
)


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

    # Use black to autodetect our target versions
    # TODO: we don't want to rely on black
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

    # ***Black***
    # Run black first to unlock `remove_pointless_parens_around_call` fixes.
    # Running it first  unfortunately breaks comment association for `split_assert_and`
    # and adds a trailing comma in imports in tests/recorded/issue75.txt
    black_mode = black.Mode(target_versions=target_versions, is_pyi=is_pyi)
    source_code = blackened = black.format_str(source_code, mode=black_mode)

    # ***Shed Codemods***
    # codemods need to run before ruff, since `split_assert` relies on it to remove
    # needless `pass` statements.
    if refactor and not is_pyi:
        source_code = _run_codemods(source_code, min_version=min_version)

    # ***Ruff***
    select = ",".join(_RUFF_RULES)
    if _remove_unused_imports:
        select += ",F401"
    source_code = subprocess.run(
        [
            "ruff",
            "check",
            f"--select={select}",
            "--fix-only",
            f"--target-version=py3{min_version[1]}",
            "--isolated",  # ignore configuration files
            "--exit-zero",  # Exit with 0, even upon detecting lint violations.
            "--config=lint.isort.combine-as-imports=true",
            f"--config=lint.isort.known-first-party={list(first_party_imports)}",
            f"--config=lint.extend-safe-fixes={list(_RUFF_EXTEND_SAFE_FIXES)}",
            "-",  # pass code on stdin
        ],
        input=source_code,
        encoding="utf-8",
        check=True,
        capture_output=True,
    ).stdout

    # ***Black***
    # Run formatter again last, if codemods/ruff did any changes, since they tend to
    # leave dirty code
    if source_code != blackened:
        source_code = black.format_str(source_code, mode=black_mode)

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
