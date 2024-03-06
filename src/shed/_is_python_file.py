import re
import tokenize

# Copied from https://github.com/PyCQA/autoflake autoflake.py

PYTHON_SHEBANG_REGEX = re.compile(r"^#!.*\bpython[3]?\b\s*$")

MAX_PYTHON_FILE_DETECTION_BYTES = 1024

def is_python_file(filename):
    """Return True if filename is Python file."""
    if filename.endswith(".py"):
        return True

    try:
        with open_with_encoding(
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

    if not PYTHON_SHEBANG_REGEX.match(first_line):
        return False

    return True
def open_with_encoding(
    filename,
    encoding,
    mode="r",
    limit_byte_check=-1,
):
    """Return opened file with a specific encoding."""
    if not encoding:
        encoding = detect_encoding(filename, limit_byte_check=limit_byte_check)

    return open(
        filename,
        mode=mode,
        encoding=encoding,
        newline="",
    )  # Preserve line endings
def detect_encoding(filename, limit_byte_check=-1):
    """Return file encoding."""
    try:
        with open(filename, "rb") as input_file:
            encoding = _detect_encoding(input_file.readline)

            # Check for correctness of encoding.
            with open_with_encoding(filename, encoding) as input_file:
                input_file.read(limit_byte_check)

        return encoding
    except (LookupError, SyntaxError, UnicodeDecodeError):
        return "latin-1"

def _detect_encoding(readline):
    """Return file encoding."""
    try:
        encoding = tokenize.detect_encoding(readline)[0]
        return encoding
    except (LookupError, SyntaxError, UnicodeDecodeError):
        return "latin-1"
