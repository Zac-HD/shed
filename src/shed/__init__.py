"""Shed canoncalises your code.

It works on all Python files in the current git repository; or you can
pass the names of specific files to format instead.
"""

import functools
import re
import sys
import textwrap
from operator import attrgetter
from typing import FrozenSet, Match, Tuple

import autoflake
import black
import isort
import libcst
import pyupgrade._main
from black.mode import TargetVersion
from black.parsing import lib2to3_parse
from pybetter.cli import (
    ALL_IMPROVEMENTS,
    FixMissingAllAttribute,
    FixParenthesesInReturn,
    FixTrivialNestedWiths,
)


def _fallback(source: str, **kw: object) -> Tuple[str, object]:
    return source, None  # pragma: no cover


try:
    from teyit import refactor_until_deterministic as _teyit_refactor
except ImportError:  # pragma: no cover  # on Python 3.9
    assert sys.version_info < (3, 9)
    _teyit_refactor = _fallback

try:
    from hypothesis.extra.codemods import refactor as _hypothesis_refactor
except ImportError:  # pragma: no cover  # optional integration

    def _hypothesis_refactor(source_code: str) -> str:
        return source_code


# We can't use a try-except here because com2ann does not declare python_requires,
# and so it is entirely possible to install it on a Python version that it does
# not support, and nothing goes wrong until you call the function.  We therefore
# explicitly check the Python version, while waiting on an upstream fix.
com2ann = _fallback
if sys.version_info[:2] >= (3, 8):  # pragma: no cover
    from com2ann import com2ann


__version__ = "0.3.8"
__all__ = ["shed", "docshed"]

_version_map = {
    k: (int(k.name[2]), int(k.name[3:]))
    for k in TargetVersion
    if k.value >= TargetVersion.PY36.value
}
_pybetter_fixers = tuple(
    fix().improve
    for fix in set(ALL_IMPROVEMENTS)
    - {FixMissingAllAttribute, FixParenthesesInReturn, FixTrivialNestedWiths}
)


@functools.lru_cache()
def shed(
    source_code: str,
    *,
    refactor: bool = False,
    first_party_imports: FrozenSet[str] = frozenset(),
) -> str:
    """Process the source code of a single module."""
    assert isinstance(source_code, str)
    assert isinstance(refactor, bool)
    assert isinstance(first_party_imports, frozenset)
    assert all(isinstance(name, str) for name in first_party_imports)
    assert all(name.isidentifier() for name in first_party_imports)

    if source_code == "":
        return ""

    # Use black to autodetect our target versions
    target_versions = {
        v
        for v in black.detect_target_versions(
            lib2to3_parse(source_code.lstrip(), set(_version_map))
        )
        if v.value >= TargetVersion.PY36.value
    }
    assert target_versions
    min_version = _version_map[min(target_versions, key=attrgetter("value"))]

    if refactor:
        # Some tools assume that the file is multi-line, but empty files are valid input.
        source_code += "\n"
        # Use com2ann to comvert type comments to annotations on Python 3.8+
        source_code, _ = com2ann(
            source_code,
            drop_ellipsis=True,
            silent=True,
            python_minor_version=min_version[1],
        )
        # Use teyit to replace old unittest.assertX methods on Python 3.9+
        source_code, _ = _teyit_refactor(source_code)
        # Apply Hypothesis codemods to fix any deprecated code
        source_code = _hypothesis_refactor(source_code)
        # Then apply pybetter's fixes with libcst
        tree = libcst.parse_module(source_code)
        for fixer in _pybetter_fixers:
            try:
                # Might raise e.g. https://github.com/Instagram/LibCST/issues/446
                newtree = fixer(tree)
            except Exception:
                pass
            else:
                tree = newtree
                # Catches e.g. https://github.com/lensvol/pybetter/issues/60
                compile(newtree.code, "<string>", "exec")
        source_code = tree.code
    # Then shed.docshed (below) formats any code blocks in documentation
    source_code = docshed(source=source_code, first_party_imports=first_party_imports)
    # And pyupgrade - see pyupgrade._main._fix_file - is our last stable fixer
    # Calculate separate minver because pyupgrade can take a little while to update
    pyupgrade_min = min(min_version, max(pyupgrade._main.IMPORT_REMOVALS))
    source_code = pyupgrade._main._fix_plugins(
        source_code, settings=pyupgrade._main.Settings(min_version=pyupgrade_min)
    )
    source_code = pyupgrade._main._fix_tokens(source_code, min_version=pyupgrade_min)
    source_code = pyupgrade._main._fix_py36_plus(source_code, min_version=pyupgrade_min)

    # One tricky thing: running `isort` or `autoflake` can "unlock" further fixes
    # for `black`, e.g. "pass;#" -> "pass\n#\n" -> "#\n".  We therefore loop until
    # neither of them have made a change in the last loop body, trusting that
    # `black` itself is idempotent because that's tested upstream.
    prev = ""
    black_mode = black.Mode(target_versions=target_versions)  # type: ignore
    while prev != source_code:
        prev = source_code = black.format_str(source_code, mode=black_mode)
        source_code = autoflake.fix_code(
            source_code,
            expand_star_imports=True,
            remove_all_unused_imports=True,
            remove_duplicate_keys=True,
            remove_unused_variables=True,
        )
        source_code = isort.code(
            source_code,
            known_first_party=first_party_imports,
            known_local_folder={"tests"},
            profile="black",
            combine_as_imports=True,
        )

    # Remove any extra trailing whitespace
    return source_code.rstrip() + "\n"


@functools.lru_cache()
def docshed(
    source: str,
    *,
    refactor: bool = False,
    first_party_imports: FrozenSet[str] = frozenset(),
) -> str:
    """Process Python code blocks embedded in documentation."""
    # Inspired by the blacken-docs package.
    assert isinstance(source, str)
    assert isinstance(first_party_imports, frozenset)
    assert all(isinstance(name, str) for name in first_party_imports)
    assert all(name.isidentifier() for name in first_party_imports)
    markdown_pattern = re.compile(
        r"(?P<before>^(?P<indent> *)```python\n)"
        r"(?P<code>.*?)"
        r"(?P<after>^(?P=indent)```\s*$)",
        flags=re.DOTALL | re.MULTILINE,
    )
    rst_pattern = re.compile(
        r"(?P<before>"
        r"^(?P<indent> *)\.\. (jupyter-execute::|(code|code-block|sourcecode|ipython):: "
        r"(python|py|sage|python3|py3|numpy))\n"
        r"((?P=indent) +:.*\n)*"
        r"\n*"
        r")"
        r"(?P<code>(^((?P=indent) +.*)?\n)+)",
        flags=re.MULTILINE,
    )

    def _md_match(match: Match[str]) -> str:
        code = textwrap.dedent(match["code"])
        code = shed(code, refactor=refactor, first_party_imports=first_party_imports)
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
        code = shed(code, refactor=refactor, first_party_imports=first_party_imports)
        code = textwrap.indent(code, min_indent)
        return f'{match["before"]}{code.rstrip()}{trailing_ws}'

    return rst_pattern.sub(_rst_match, markdown_pattern.sub(_md_match, source))
