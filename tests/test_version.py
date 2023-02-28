"""Tests for the hypothesis-jsonschema library."""

import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"
INIT_FILE = Path(__file__).parent.parent / "src/shed/__init__.py"
for line in INIT_FILE.read_text().splitlines():
    if line.startswith("__version__ = "):
        _, SHED_VERSION, _ = line.split('"')


class Version(NamedTuple):
    major: int
    minor: int
    patch: int

    @classmethod
    def from_string(cls, string):
        return cls(*map(int, string.split(".")))

    def __str__(self):
        return ".".join(map(str, self))


@lru_cache()
def get_releases():
    pattern = re.compile(r"^#### (\d+\.\d+\.\d+) - (\d\d\d\d-\d\d-\d\d)$")
    return tuple(
        (Version.from_string(match.group(1)), match.group(2))
        for match in map(pattern.match, CHANGELOG.read_text().splitlines())
        if match is not None
    )


def test_last_release_against_changelog():
    last_version, last_date = get_releases()[0]
    assert last_version == Version.from_string(SHED_VERSION)
    assert last_date <= datetime.now(timezone.utc).date().isoformat()


def test_changelog_is_ordered():
    versions, dates = zip(*get_releases())
    assert versions == tuple(sorted(versions, reverse=True))
    assert dates == tuple(sorted(dates, reverse=True))


if __name__ == "__main__":
    # If we've added a new version to the changelog, update __version__ to match
    last_version, _ = get_releases()[0]
    if Version.from_string(SHED_VERSION) != last_version:
        subs = (f'__version__ = "{SHED_VERSION}"', f'__version__ = "{last_version}"')
        INIT_FILE.write_text(INIT_FILE.read_text().replace(*subs))

    # Similarly, update the pre-commit config example in the README
    README = CHANGELOG.parent / "README.md"
    current = README.read_text()
    wanted = re.sub(
        pattern=r"^  rev: (\d+\.\d+\.\d+)$",
        repl=f"  rev: {last_version}",
        string=current,
        flags=re.MULTILINE,
    )
    if current != wanted:
        README.write_text(wanted)

    # For our release automation, ensure that we've tagged the latest version.
    # This is only ever expected to run in CI, just before uploading to PyPI.
    import sys

    if "--ensure-tag" in sys.argv:
        import git

        repo = git.Repo(CHANGELOG.parent)
        if last_version not in repo.tags:
            repo.create_tag(str(last_version))
            repo.remotes.origin.push(str(last_version))
