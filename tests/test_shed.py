"""Tests for the `shed` library."""

import os
import site
import tempfile
from pathlib import Path

import black
import blib2to3
import hypothesmith
import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

import shed


@given(
    source_code=hypothesmith.from_grammar(),
    provides=st.frozensets(st.from_regex(r"\A[\w\d_]+\Z").filter(str.isidentifier)),
)
@settings(suppress_health_check=HealthCheck.all(), deadline=None)
def test_shed_is_idempotent(source_code, provides):
    # Given any syntatically-valid source code, shed should not crash.
    # This tests doesn't check that we do the *right* thing,
    # just that we don't crash on valid-if-poorly-styled code!
    try:
        result = shed.shed(source_code=source_code, first_party_imports=provides)
    except (IndentationError, black.InvalidInput, blib2to3.pgen2.tokenize.TokenError):
        assume(False)
    assert result == shed.shed(source_code=result, first_party_imports=provides)


def test_guesses_shed_is_first_party():
    assert shed._guess_first_party_modules() == frozenset(["shed"])


def test_guesses_empty_for_non_repo_dirs():
    assert shed._guess_first_party_modules("../..") == frozenset()


@pytest.mark.parametrize(
    "fname,should",
    [("a.md", True), ("a.rst", True), ("a.py", True), ("does not exist", False)],
)
def test_should_format_autodetection(fname, should):
    assert shed._should_format(fname) == should


@pytest.mark.parametrize(
    "fname,contents,changed",
    [
        ("a.md", "Lorem ipsum...", False),
        ("a.rst", "Lorem ipsum...", False),
        ("a.py", "# A comment\n", False),
        ("a.md", "```python\nprint(\n'hello world')\n```", True),
        ("a.rst", ".. code-block:: python\n\n    'single quotes'\n", True),
        ("a.py", "print(\n'hello world')\n", True),
        ("from shebang", "#! python3\nprint(\n'hello world')\n", True),
    ],
)
def test_rewrite_on_disk(fname, contents, changed):
    kwargs = {"refactor": True, "first_party_imports": frozenset()}
    with tempfile.TemporaryDirectory() as dirname:
        f = Path(dirname) / fname
        f.write_text(contents)
        ret = shed._rewrite_on_disk(str(f), **kwargs)
        result = f.read_text()
    assert ret == changed
    assert changed == (contents != result)


def test_rewrite_returns_error_message_for_nonexistent_file():
    kwargs = {"refactor": True, "first_party_imports": frozenset()}
    with tempfile.TemporaryDirectory() as dirname:
        f = Path(dirname) / "nonexistent"
        result = shed._rewrite_on_disk(str(f), **kwargs)
        assert isinstance(result, str)
        f.write_text("# comment\n")
        assert shed._rewrite_on_disk(str(f), **kwargs) is False


python_files = []
for base in sorted(set(site.PREFIXES)):
    for dirname, _, files in os.walk(base):
        python_files.extend(Path(dirname) / f for f in files if f.endswith(".py"))


# NOTE: this test is disabled by default because it takes several minutes
@pytest.mark.parametrize("py_file", python_files, ids=str)
def est_on_site_code(py_file):
    # Because the generator isn't perfect, we'll also test on all the code
    # we can easily find in our current Python environment - this includes
    # the standard library, and all installed packages.
    try:
        source_code = py_file.read_text()
    except UnicodeDecodeError:
        pytest.xfail(reason="encoding problem")

    try:
        result = shed.shed(source_code=source_code)
    except (IndentationError, black.InvalidInput, blib2to3.pgen2.tokenize.TokenError):
        pytest.xfail(reason="Black can't handle that")
    assert result == shed.shed(source_code=result)
