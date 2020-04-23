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
2. Runs `isort` (configuration support waiting on 5.0), with autodetected first-party imports
3. Runs `pyupgrade`, with autodetected minimum version >= py36
4. Runs `black`, with autodetected minimum version >= py36
5. (WIP) Runs some custom fixers based on `flake8-bugbear`
6. Iterates those steps until the source code stops changing.

## Changelog

#### 0.0.3 - 2020-04-23
- compatible with pyupgrade==2.2

#### 0.0.2 - 2020-03-08
- usable CLI
- better isort autoconfig

#### 0.0.1 - 2020-02-15
- project kickoff
