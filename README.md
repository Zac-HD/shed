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
the same effect.

Only works in git repos, because version control is great and so is `git ls-files`.

## Current status
Thin wrapper + big dreams + lots of bugs.  Ready to `shed` like an old snakeskin!

Still follows whatever `isort` config is in your environment, even if it's not
Black-compatible :sob:

## Wishlist
- Convenient interface to all four of the tools above
- Autodetect minimum Python version from greater of `python_requires` metadata
  or per-file syntax or Python 3.6
- Canonicalise **everything possible**, ignoring input format.
  If that means bigger diffs, so be it.

## Changelog

#### 0.0.1 - 2020-02-15
- project kickoff
