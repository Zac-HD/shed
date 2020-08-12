# shed
`shed` canonicalises Python code.  Shed your legacy, stop bikeshedding, and move on.  Black++

## What does it do?
`shed` is the *maximally opinionated* autoformatting tool.  It's *all about*
[convention over configuration](https://en.wikipedia.org/wiki/Convention_over_configuration),
and designed to be a single opinionated tool that fully canonicalises my
code - formatting, imports, updates, and every other fix I can possibly
automate.

There are no configuration options at all, but if the defaults aren't for you
that's OK - you can still use the underlying tools directly and get most of
the same effect... though you'll have to configure them yourself.

`shed` must either be run in a git repo to auto-detect the files to format,
or explicitly passed a list of files to format on the command-line.

## Features
`shed`...

- Runs [`autoflake`](https://pypi.org/project/autoflake/),
  to remove unused imports and variables
- Runs [`teyit`](https://pypi.org/project/teyit/), on Python 3.9 or later,
  to replace deprecated `unittest` methods with the new aliases
- Runs [`docformatter`](https://pypi.org/project/docformatter/),
  to format and rewrap docstrings
- Runs [`pyupgrade`](https://pypi.org/project/pyupgrade/),
  with autodetected minimum version >= py36
- Runs [`isort`](https://pypi.org/project/isort/),
  with autodetected first-party imports and `--ca --profile=black` args
- Runs [`pybetter`](https://pypi.org/project/pybetter/),
  applying [`libCST`](https://pypi.org/project/libCST/)-based codemods
- Runs [`black`](https://pypi.org/project/black/),
  with autodetected minimum version >= py36
- Runs logic inspired by [`blacken-docs`](https://pypi.org/project/blacken-docs/)
  to format code in docstrings (via the `shed.docshed` function)
- Iterates those steps until the source code stops changing.

The version detection logic is provided by `black`, with an extra step to discard
versions before Python 3.6.

If you run `shed` in a Git repository, the name of the root directory is assumed to be a
first-party import.  [`src` layout](https://hynek.me/articles/testing-packaging/)
packages are also automatically detected, i.e. the `foo` in any paths like
`.../src/foo/__init__.py`.

## Using with pre-commit
If you use [pre-commit](https://pre-commit.com/), you can use it with Shed by
adding the following to your `.pre-commit-config.yaml`:

```yaml
repos:
- repo: https://github.com/Zac-HD/shed
  rev: 0.2.0
  hooks:
  - id: shed
```

## Changelog

Patch notes [can be found in `CHANGELOG.md`](https://github.com/Zac-HD/shed/blob/master/CHANGELOG.md).
