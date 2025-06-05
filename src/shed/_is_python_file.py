from __future__ import annotations

import re
import tokenize
from typing import Any, Callable

# Copied from https://github.com/PyCQA/autoflake autoflake.py

PYTHON_SHEBANG_REGEX = re.compile(r"^#!.*\bpython[3]?\b\s*$")

MAX_PYTHON_FILE_DETECTION_BYTES = 1024


def is_python_file(filename: str) -> bool:
    """Return True if filename is Python file."""
    # this is the only check that's covered in tests, and only when True
    if filename.endswith(".py"):
        return True

    try:  # pragma: no cover
        with _open_with_encoding(
            filename,
            None,
            limit_byte_check=MAX_PYTHON_FILE_DETECTION_BYTES,
        ) as f:
            text = f.read(MAX_PYTHON_FILE_DETECTION_BYTES)
            if not text:
                return False
            first_line = text.splitlines()[0]
    except (OSError, IndexError):
        return False

    if not PYTHON_SHEBANG_REGEX.match(first_line):  # pragma: no cover
        return False

    return True  # pragma: no cover


def _open_with_encoding(  # pragma: no cover
    filename: str,
    encoding: str | None,
    mode: str = "r",
    limit_byte_check: int = -1,
) -> Any:  # IO[Any], or BufferedReader, or something
    """Return opened file with a specific encoding."""
    if not encoding:
        encoding = _detect_encoding(filename, limit_byte_check=limit_byte_check)

    return open(  # noqa: SIM115 # use context handler for opening files
        filename,
        mode=mode,
        encoding=encoding,
        newline="",
    )  # Preserve line endings


def _detect_encoding(
    filename: str, limit_byte_check: int = -1
) -> str:  # pragma: no cover
    """Return file encoding."""
    try:
        with open(filename, "rb") as input_file:
            encoding = _inner_detect_encoding(input_file.readline)

            # Check for correctness of encoding.
            with _open_with_encoding(filename, encoding) as input_file:
                input_file.read(limit_byte_check)

        return encoding
    except (LookupError, SyntaxError, UnicodeDecodeError):
        return "latin-1"


def _inner_detect_encoding(
    readline: Callable[[], bytes | bytearray],
) -> str:  # pragma: no cover
    """Return file encoding."""
    try:
        encoding = tokenize.detect_encoding(readline)[0]
        return encoding
    except (LookupError, SyntaxError, UnicodeDecodeError):
        return "latin-1"
