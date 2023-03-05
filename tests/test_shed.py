"""Tests for the `shed` library."""

import ast
import os
import tempfile
from pathlib import Path

import black
import blib2to3
import hypothesmith
import libcst
import pytest
from flake8_comprehensions import ComprehensionChecker
from hypothesis import HealthCheck, example, given, reject, settings, strategies as st

from shed import ShedSyntaxWarning, _default_min_version, _version_map, shed
from shed._cli import _guess_first_party_modules, _rewrite_on_disk, _should_format

TEYIT_TWO_PASS = """
import unittest

unittest.assertIs(a > b, True)
"""
NOT_YET_FIXED = (
    "C402",
    "C406",
    "C408",
    "C409",
    "C410",
)
SHOULD_NOT_FIX = (
    # Removing calls to reversed() changes results of stable sorting.
    "C413",
    # This error will fire in cases where it would be inappropriate
    # to fix automatically (because e.g. sorted has a call to key),
    # so we can't always reliably fix it.
    "C414",
)


def check(
    source_code,
    *,
    refactor,
    provides=frozenset(),
    min_version=_default_min_version,
    except_=reject,
):
    # Given any syntatically-valid source code, shed should not crash.
    # This tests doesn't check that we do the *right* thing,
    # just that we don't crash on valid-if-poorly-styled code!
    try:
        result = shed(
            source_code=source_code,
            refactor=refactor,
            first_party_imports=provides,
            min_version=min_version,
        )
    except (
        IndentationError,
        black.InvalidInput,
        blib2to3.pgen2.tokenize.TokenError,
        libcst.ParserSyntaxError,
        ShedSyntaxWarning,
    ):
        if except_ is ...:
            raise
        except_()
    assert result == shed(
        source_code=result,
        refactor=refactor,
        first_party_imports=provides,
        min_version=min_version,
    )
    assert result == shed(source_code=result, first_party_imports=provides)

    try:
        tree = ast.parse(result)
    except SyntaxError:
        return result
    errors = [
        err
        for err in ComprehensionChecker(tree).run()
        if not err[2].startswith(NOT_YET_FIXED + SHOULD_NOT_FIX)
    ]
    assert not errors
    return result


example_kwargs = {"refactor": True, "provides": frozenset(), "min_version": (3, 8)}


@given(
    source_code=hypothesmith.from_grammar(auto_target=False)
    | hypothesmith.from_node(auto_target=False),
    refactor=st.booleans(),
    provides=st.frozensets(st.from_regex(r"\A[\w\d_]+\Z").filter(str.isidentifier)),
    min_version=st.sampled_from(sorted(_version_map.values())),
)
@example(source_code=TEYIT_TWO_PASS, **example_kwargs)
@example(source_code="class A:\n\x0c pass\n", **example_kwargs)
@example(
    source_code="from.import(A)#",
    refactor=False,
    provides=frozenset(),
    min_version=(3, 7),
)
# Minimum-version examples via https://github.com/jwilk/python-syntax-errors/
@example(source_code="lambda: (x := 0)\n", **example_kwargs)
@example(source_code="@0\ndef f(): pass\n", **example_kwargs)
@example(source_code="match 0:\n  case 0: ...\n", **example_kwargs)
@example(source_code="try: pass\nexcept* 0: pass\n", **example_kwargs)
@example(
    source_code="async def f(x): [[x async for x in ...] for y in ()]\n",
    **example_kwargs,
)
@settings(suppress_health_check=HealthCheck.all(), deadline=None)
def test_shed_is_idempotent(source_code, refactor, provides, min_version):
    check(source_code, refactor=refactor, min_version=min_version, provides=provides)


def test_guesses_shed_is_first_party():
    assert _guess_first_party_modules() == frozenset(["shed"])


def test_guesses_empty_for_non_repo_dirs():
    assert _guess_first_party_modules("../..") == frozenset()


@pytest.mark.parametrize(
    "fname,should",
    [
        ("a.md", True),
        ("a.rst", True),
        ("a.py", True),
        ("does not exist", False),
        ("a.pyi", True),
    ],
)
def test_should_format_autodetection(fname, should):
    assert _should_format(fname) == should


@pytest.mark.parametrize(
    "fname,contents,changed",
    [
        ("a.md", "Lorem ipsum...", False),
        ("a.rst", "Lorem ipsum...", False),
        ("a.py", "# A comment\n", False),
        ("a.pyi", "## Another comment\n", False),
        ("a.md", "```python\nprint(\n'hello world')\n```", True),
        ("a.rst", ".. code-block:: python\n\n    'single quotes'\n", True),
        ("a.py", "print(\n'hello world')\n", True),
        ("a.py", 'f"{x=}"\n', False),
        ("from shebang", "#! python3\nprint(\n'hello world')\n", True),
    ],
)
def test_rewrite_on_disk(fname, contents, changed):
    kwargs = {"refactor": True, "first_party_imports": frozenset()}
    with tempfile.TemporaryDirectory() as dirname:
        f = Path(dirname) / fname
        f.write_text(contents)
        ret = _rewrite_on_disk(str(f), **kwargs)
        result = f.read_text()
    assert ret == changed, repr(result)
    assert changed == (contents != result)


def test_rewrite_returns_error_message_for_nonexistent_file():
    kwargs = {"refactor": True, "first_party_imports": frozenset()}
    with tempfile.TemporaryDirectory() as dirname:
        f = Path(dirname) / "nonexistent"
        result = _rewrite_on_disk(str(f), **kwargs)
        assert isinstance(result, str)
        f.write_text("# comment\n")
        assert _rewrite_on_disk(str(f), **kwargs) is False


@pytest.mark.parametrize("refactor", [True, False])
def test_empty_stays_empty(refactor):
    assert shed(source_code="", refactor=refactor) == ""


@pytest.mark.parametrize(
    "source_code,exception",
    [
        ("this isn't valid Python", ShedSyntaxWarning),
        # We request a bug report for valid unhandled syntax, i.e. (upstream) bugs
        ("class A:\\\r# type: ignore\n pass\n", ShedSyntaxWarning),
    ],
)
@pytest.mark.parametrize("refactor", [True, False])
def test_error_on_invalid_syntax(source_code, exception, refactor):
    with pytest.raises(exception):
        assert shed(source_code=source_code, refactor=refactor)


def test_cleans_up_after_setting_env_var(monkeypatch):
    monkeypatch.setenv("LIBCST_PARSER_TYPE", "non-native")
    assert os.environ.get("LIBCST_PARSER_TYPE") == "non-native"
    shed(source_code="match x:\n  case _:\n    pass\n", refactor=True)
    assert os.environ.get("LIBCST_PARSER_TYPE") == "non-native"


python_files = []
if "SHED_SLOW_TESTS" in os.environ:
    # When I say slow I'm not kidding, testing all site code takes almost an hour!
    import site

    for base in sorted(site.PREFIXES):
        python_files.extend(Path(base).glob("**/*.py"))
    python_files = sorted(python_files, key=str)


@pytest.mark.parametrize("py_file", python_files, ids=str)
def test_on_site_code(py_file):
    # Because the generator isn't perfect, we'll also test on all the code
    # we can easily find in our current Python environment - this includes
    # the standard library, and all installed packages.
    try:
        source_code = py_file.read_text()
    except UnicodeDecodeError:
        pytest.xfail(reason="encoding problem")
    try:
        compile(source_code, str(py_file), "exec")
    except Exception:
        pytest.xfail(reason="invalid source code")
    for refactor in [False, True]:
        for min_version in sorted(_version_map.values()):
            check(
                source_code,
                refactor=refactor,
                min_version=min_version,
                except_=lambda: pytest.xfail(reason="Black can't handle that"),
            )
