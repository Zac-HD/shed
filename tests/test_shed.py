"""Tests for the `shed` library."""

import os
import site
from pathlib import Path

import black
import blib2to3
import hypothesmith
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import shed


@given(
    source_code=hypothesmith.from_grammar(),
    provides=st.frozensets(st.from_regex(r"\A[\w\d_]+\Z").filter(str.isidentifier)),
)
@settings(suppress_health_check=HealthCheck.all())
def test_shed_is_idempotent(source_code, provides):
    # Given any syntatically-valid source code, shed should not crash.
    # This tests doesn't check that we do the *right* thing,
    # just that we don't crash on valid-if-poorly-styled code!
    try:
        result = shed.shed(source_code=source_code, first_party_imports=provides)
    except (IndentationError, black.InvalidInput, blib2to3.pgen2.tokenize.TokenError):
        assume(False)
    assert result == shed.shed(source_code=result, first_party_imports=provides)


python_files = []
for base in sorted(set(site.PREFIXES)):
    for dirname, _, files in os.walk(base):
        python_files.extend(Path(dirname) / f for f in files if f.endswith(".py"))


# NOTE: this test is disabled by default because it takes several minutes
@pytest.mark.parametrize("py_file", python_files, ids=[str(s) for s in python_files])
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
