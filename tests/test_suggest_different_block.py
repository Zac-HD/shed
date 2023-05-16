import pytest

from shed import ShedSyntaxWarning, shed


def test_shed_suggest_different_block_python():
    with pytest.raises(
        ShedSyntaxWarning, match="Perhaps you should use a 'pycon' block instead?"
    ):
        assert shed(source_code=">>> a = b\n")


def test_shed_suggest_different_block_ipython():
    with pytest.raises(
        ShedSyntaxWarning, match="Perhaps you should use a 'pycon' block instead?"
    ):
        assert shed(
            source_code="In [1]: import re\n\nIn [2]: a = 1\n\nIn [3]: b = a*2\n"
        )


def test_shed_suggest_different_block_stacktrace():
    with pytest.raises(
        ShedSyntaxWarning,
        match="Perhaps you should use a 'python-traceback' block instead?",
    ):
        assert shed(
            source_code=(
                "Traceback (most recent call last):\n"
                '  File "<string>", line 1, in <module>\n'
                "ZeroDivisionError: division by zero\n"
            )
        )
