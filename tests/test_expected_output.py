"""Update and check saved examples of shed formatting."""

import pathlib

import pytest

import shed


@pytest.mark.parametrize(
    "filename", (pathlib.Path(__file__).parent / "recorded").glob("*.txt")
)
def test_saved_examples(filename):
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
    result = shed.shed(source_code=input_)
    if result.strip() != expected:
        filename.write_text(joiner.join([input_, result]))
        raise AssertionError(filename.name + " changed formatting")
