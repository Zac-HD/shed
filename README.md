# shed
`shed` canonicalises Python code.  Shed your legacy, stop bikeshedding, and move on.  Black++

## What does it do?
`shed` is basically [`black`](https://pypi.org/project/black/)
plus [`autoflake`](https://pypi.org/project/autoflake/)
plus [`isort`](https://pypi.org/project/isort/)
plus [`pyupgrade`](https://pypi.org/project/pyupgrade/)
plus some custom fixers.

`shed` is *all about* [convention over configuration](https://en.wikipedia.org/wiki/Convention_over_configuration).
It's designed to be a single opinionated tool that fully canonicalises my
code - formatting, imports, updates, and every other fix I can possibly
automate.

There are no configuration options at all, but if the defaults aren't for you
that's OK - you can still use the underlying tools directly and get most of
the same effect... though you'll have to configure them yourself.

Only works in git repos, because version control is great and so is `git ls-files`,
or in single-file mode.

## Features
`shed`...

1. Runs `autoflake`, to remove unused imports and variables, and expand star-imports
2. Runs `pyupgrade`, with autodetected minimum version >= py36
3. Runs `isort`, with autodetected first-party imports and `--ca --profile=black` args
4. Runs `black`, with autodetected minimum version >= py36
5. (WIP) Runs some custom fixers based on `flake8-bugbear`
6. Iterates those steps until the source code stops changing.

The version detection logic is provided by `black`, with an extra step to discard
versions before Python 3.6.

First-party import detection is disabled in single-file mode.  If you run `shed`
in a Git repository, the name of the root directory is assumed to be a
first-party import.  [`src` layout](https://hynek.me/articles/testing-packaging/)
packages are also automatically detected, i.e. the `foo` in any paths like
`.../src/foo/__init__.py`.

## Changelog

#### 0.1.1 - 2020-07-10
- combine "as" imports with `isort` on a single line

#### 0.1.0 - 2020-07-09
- automatic and isolated `isort` configuration.
  I am now happy to recommend that you try `shed`!

#### 0.0.5 - 2020-05-29
- better handling of permissions issues or deleted files

#### 0.0.4 - 2020-05-13
- compatible with pyupgrade==2.4

#### 0.0.3 - 2020-04-23
- compatible with pyupgrade==2.2

#### 0.0.2 - 2020-03-08
- usable CLI
- better isort autoconfig

#### 0.0.1 - 2020-02-15
- project kickoff
