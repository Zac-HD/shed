"""Update and check saved examples of shed formatting."""

import pathlib
import warnings

import pytest

import shed

from .test_shed import check


@pytest.mark.parametrize(
    "min_version", sorted(shed._version_map.values()), ids=lambda t: f"{t[0]}.{t[1]}"
)
@pytest.mark.parametrize(
    "filename",
    pathlib.Path(__file__).parent.glob("recorded/**/*.txt"),
    ids=lambda p: p.stem,
)
def test_saved_examples(filename: pathlib.Path, min_version):
    """Replay and save expected outputs from `shed`.

    To add a file to the test corpus, write it into recorded/foo.txt and
    run the tests; the expected results will be automatically appended
    to the file.

    On test failure, the expected output is automatically updated.
    You can therefore see what changed by examining the `git diff`
    and roll back with `git reset`.
    """
    joiner = "\n\n" + "=" * 80 + "\n\n"
    input_, expected, *_ = map(str.strip, (filename.read_text() + joiner).split(joiner))
    if filename.suffix == ".py" and "invalid" not in filename.stem:
        compile(input_, filename, "exec")  # check for SyntaxError
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", shed.ShedSyntaxWarning)
        result = check(
            source_code=input_, refactor=True, min_version=min_version, except_=...
        )
    if result.strip() != expected:
        filename.write_text(joiner.join([input_, result]))
        raise AssertionError(filename.name + " changed formatting")
