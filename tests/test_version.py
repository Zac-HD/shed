"""Tests for the hypothesis-jsonschema library."""

import re
from datetime import date
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
    assert last_date <= date.today().isoformat()


def test_changelog_is_ordered():
    versions, dates = zip(*get_releases())
    assert versions == tuple(sorted(versions, reverse=True))
    assert dates == tuple(sorted(dates, reverse=True))


def test_version_increments_are_correct():
    # We either increment the patch version by one, increment the minor version
    # and reset the patch, or increment major and reset both minor and patch.
    versions, _ = zip(*get_releases())
    for prev, current in zip(versions[1:], versions):
        assert prev < current  # remember that `versions` is newest-first
        assert current in (
            prev._replace(patch=prev.patch + 1),
            prev._replace(minor=prev.minor + 1, patch=0),
            prev._replace(major=prev.major + 1, minor=0, patch=0),
        ), f"{current} does not follow {prev}"


if __name__ == "__main__":
    # If we've added a new version to the changelog, update __version__ to match
    last_version, _ = get_releases()[0]
    if Version.from_string(SHED_VERSION) != last_version:
        subs = (f'__version__ = "{SHED_VERSION}"', f'__version__ = "{last_version}"')
        INIT_FILE.write_text(INIT_FILE.read_text().replace(*subs))
