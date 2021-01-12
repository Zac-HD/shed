"""Shed canoncalises your code.

It works on all Python files in the current git repository; or you can
pass the names of specific files to format instead.
"""

import argparse
import functools
import multiprocessing
import re
import subprocess
import sys
import textwrap
from operator import attrgetter
from pathlib import Path
from typing import FrozenSet, Match, Tuple, Union

import autoflake
import black
import isort
import libcst
import pyupgrade
from pybetter.cli import (
    ALL_IMPROVEMENTS,
    FixMissingAllAttribute,
    FixParenthesesInReturn,
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


__version__ = "0.3.0"
__all__ = ["shed", "docshed"]

_version_map = {
    k: (int(k.name[2]), int(k.name[3:]))
    for k in black.TargetVersion
    if k.value >= black.TargetVersion.PY36.value
}
_pybetter_fixers = tuple(
    fix().improve
    for fix in set(ALL_IMPROVEMENTS) - {FixMissingAllAttribute, FixParenthesesInReturn}
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

    # Use black to autodetect our target versions
    target_versions = {
        v
        for v in black.detect_target_versions(
            black.lib2to3_parse(source_code.lstrip(), set(_version_map))
        )
        if v.value >= black.TargetVersion.PY36.value
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
                # Catches e.g. https://github.com/lensvol/pybetter/issues/60
                compile(newtree.code, "<string>", "exec")
            except Exception:
                pass
            else:
                tree = newtree
        source_code = tree.code
    # Then shed.docshed (below) formats any code blocks in documentation
    source_code = docshed(source=source_code, first_party_imports=first_party_imports)
    # And pyupgrade - see pyupgrade._fix_file - is our last stable fixer
    # Calculate separate minver because pyupgrade doesn't have py39-specific logic yet
    pyupgrade_min_ver = min(min_version, max(pyupgrade.IMPORT_REMOVALS.keys()))
    source_code = pyupgrade._fix_tokens(source_code, min_version=pyupgrade_min_ver)
    source_code = pyupgrade._fix_percent_format(source_code)
    source_code = pyupgrade._fix_py3_plus(source_code, min_version=pyupgrade_min_ver)
    source_code = pyupgrade._fix_py36_plus(source_code)

    # One tricky thing: running `isort` or `autoflake` can "unlock" further fixes
    # for `black`, e.g. "pass;#" -> "pass\n#\n" -> "#\n".  We therefore loop until
    # neither of them have made a change in the last loop body, trusting that
    # `black` itself is idempotent because that's tested upstream.
    prev = ""
    black_mode = black.FileMode(target_versions=target_versions)
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


@functools.lru_cache()
def _guess_first_party_modules(cwd: str = None) -> FrozenSet[str]:
    """Guess the name of the current package for first-party imports."""
    try:
        base = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            timeout=10,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            cwd=cwd,
        ).stdout.strip()
    except subprocess.SubprocessError:
        return frozenset()
    provides = {init.name for init in Path(base).glob("**/src/*/__init__.py")}
    return frozenset(p for p in {Path(base).name} | provides if p.isidentifier())


@functools.lru_cache(maxsize=None)
def _should_format(fname: str) -> bool:
    return fname.endswith((".md", ".rst")) or autoflake.is_python_file(fname)


def _rewrite_on_disk(
    fname: str, **kwargs: Union[bool, FrozenSet[str]]
) -> Union[bool, str]:
    """Return either bool(rewrote the file), or an error message string."""
    try:
        with open(fname) as handle:
            on_disk = handle.read()
    except (OSError, UnicodeError) as err:
        # Permissions or encoding issue, or file deleted since last commit.
        return f"skipping {fname!r} due to {err}"
    writer = docshed if fname.endswith((".md", ".rst")) else shed
    try:
        result = writer(on_disk, **kwargs)
    except Exception as err:  # pragma: no cover  # bugs are unknown xor fixed ;-)
        return (
            f"Internal error formatting {fname!r}: {err}\n"
            "    Please report this to https://github.com/Zac-HD/shed/issues"
        )
    if result != on_disk:
        with open(fname, mode="w") as fh:
            fh.write(result)
    return result != on_disk


def cli() -> None:  # pragma: no cover  # mutates things in-place, will test later.
    """Execute the `shed` CLI."""
    # TODO: make this provide useful CLI help and usage hints
    parser = argparse.ArgumentParser(prog="shed", description=__doc__.strip())
    parser.add_argument(
        "--refactor",
        action="store_true",
        help="Run additional passes to refactor code",
    )
    parser.add_argument(
        nargs="*",
        metavar="file",
        dest="files",
        help="File(s) to format, instead of autodetection",
    )
    args = parser.parse_args()

    if args.files:
        all_filenames = args.files
    else:
        # Get all tracked files from `git ls-files`
        try:
            all_filenames = subprocess.run(
                ["git", "ls-files"],
                check=True,
                timeout=10,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            ).stdout.splitlines()
        except subprocess.SubprocessError:
            print("Doesn't seem to be a git repo; pass filenames to format.")  # noqa
            sys.exit(1)
        all_filenames = [f for f in all_filenames if _should_format(f)]

    rewrite = functools.partial(
        _rewrite_on_disk,
        first_party_imports=_guess_first_party_modules(),
        refactor=args.refactor,
    )

    if len(all_filenames) <= 4:
        # If we're only formatting a few files, starting up a process pool
        # probably takes up more time that it saves.
        for fname in all_filenames:
            error_msg = rewrite(fname)
            if isinstance(error_msg, str):
                print(error_msg)  # noqa
    else:
        with multiprocessing.Pool() as pool:
            for error_msg in pool.imap_unordered(rewrite, all_filenames):
                if isinstance(error_msg, str):
                    print(error_msg)  # noqa
