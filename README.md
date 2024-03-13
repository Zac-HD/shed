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

- Runs [`ruff`](https://pypi.org/project/ruff/),
  to remove unused imports and variables, upgrade code, sort imports, and more.
- Runs [`black`](https://pypi.org/project/black/),
  with autodetected minimum version >= py38
- Formats code blocks in docstrings, markdown, and restructured text docs
  (based on [`blacken-docs`](https://pypi.org/project/blacken-docs/)).
- If `shed --refactor`, also runs [`com2ann`](https://pypi.org/project/com2ann/)
  and custom refactoring logic using [`libcst`](https://pypi.org/project/libcst/). See documentation for the codemods in [CODEMODS.md](CODEMODS.md)

The version detection logic is provided by `black`.  Because `shed` supports the same
[versions of Python as upstream](https://devguide.python.org/#status-of-python-branches),
it assumes that the minimum version is Python 3.8.

If you run `shed` in a Git repository, the name of the root directory is assumed to be a
first-party import.  [`src` layout](https://hynek.me/articles/testing-packaging/)
packages are also automatically detected, i.e. the `foo` in any paths like
`.../src/foo/__init__.py`.

### Jupyter Notebook support
We recommend [using `jupytext` to save your notebooks in `.py` or `.md` files](https://jupytext.readthedocs.io/en/latest/),
in which case `shed` supports them natively.  For a quick-and-dirty workflow,
you can [use `nbqa shed notebook.ipynb`](https://nbqa.readthedocs.io/en/latest/readme.html) -
`nbqa` works for any linter or formatter.

## Using `shed` in your editor
We recommend [using `black` in your editor](https://black.readthedocs.io/en/stable/integrations/editors.html)
instead of `shed`, since it provides our core formatting logic and `shed`'s extra
smarts can be counterproductive while you're actively editing code - for example,
removing an "unused" import just after you add it!

Then, when you're done editing, you can run `shed` from the command-line, `pre-commit`
hooks, and your CI system.

## Using `shed` with pre-commit
If you use [pre-commit](https://pre-commit.com/), you can use it with Shed by
adding the following to your `.pre-commit-config.yaml`:

```yaml
minimum_pre_commit_version: '2.9.0'
repos:
- repo: https://github.com/Zac-HD/shed
  rev: 2024.3.1
  hooks:
    - id: shed
      # args: [--refactor, --py311-plus]
      types_or: [python, pyi, markdown, rst]
```

This is often considerably faster for large projects, because `pre-commit`
can avoid running `shed` on unchanged files.

## See also
`shed` inherits `pyupgrade`'s careful approach to converting string formatting
code.  If you want a more aggressive refactoring tool and don't mind checking
for breaking changes, [check out `flynt`](https://github.com/ikamensh/flynt).

For Django upgrades, see [`django-codemod`](https://github.com/browniebroke/django-codemod)
or [`django-upgrade`](https://github.com/adamchainz/django-upgrade).

The [`ssort` project](https://pypi.org/project/ssort/) sorts the contents of
python modules so that statements are placed after the things they depend on,
for easier navigation and consistency of design.

[`Semgrep` supports some autofixes](https://r2c.dev/blog/2022/autofixing-code-with-semgrep/#the-results),
with patterns for a wide variety of languages.  This includes a variety of both
security and style checks, with manual inspection of results recommended.

## Changelog

Patch notes [can be found in `CHANGELOG.md`](https://github.com/Zac-HD/shed/blob/master/CHANGELOG.md).
