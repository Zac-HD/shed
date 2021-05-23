# Changelog

#### 0.3.6 - 2021-05-23
- leave empty files empty, instead of adding a blank line (which triggered `flake8` W391)

#### 0.3.5 - 2021-05-05
- require [`black >= 21.5b0`](https://github.com/psf/black/blob/master/CHANGES.md#215b0)
  to avoid version-detection bug

#### 0.3.4 - 2021-04-12
- avoid new duplicate work when running `shed` (without `python -m`)

#### 0.3.3 - 2021-03-18
- support running via `python -m shed`
- stop merging nested `with`-statements (ugly when multiline on Python <= 3.9)

#### 0.3.2 - 2021-02-01
- support, and require, `pyupgrade` >= 2.8.0

#### 0.3.1 - 2021-01-28
- sort `tests` imports as a `known_local_folder` with [`isort`](https://pypi.org/project/isort/)
- increase minimum dependency versions

#### 0.3.0 - 2021-01-12
- integrates [`hypothesis codemod`](https://hypothesis.readthedocs.io/en/latest/extras.html#hypothesis-codemods)
  in `--refactor` mode (optional dependency)
- improved reporting for internal errors
- work around known errors in pybetter and libcst

#### 0.2.5 - 2020-12-10
- supports Python-3.9-only files
- improved idempotence in `--refactor` mode with Teyit

#### 0.2.4 - 2020-08-28
- requires newer dependencies - `black` 20.8b1 or later, `autoflake` 1.4 or later

#### 0.2.3 - 2020-08-17
- add [`com2ann`](https://pypi.org/project/com2ann/) to `--refactor` on Python 3.8+

#### 0.2.2 - 2020-08-14
- use multiple processes if formatting many files (ncpus times faster!)

#### 0.2.1 - 2020-08-13
- drop `docformatter` due to poor performance
- reorganise remaining passes for speed and split out `--refactor` passes

#### 0.2.0 - 2020-08-12
- use [`pybetter`](https://pypi.org/project/pybetter/) codemods
- use [`teyit`](https://pypi.org/project/teyit/) to replace deprecated
  `unittest` methods with the new aliases (if running on Python 3.9+)
- use [`docformatter`](https://pypi.org/project/docformatter/) to format docstrings
- new logic inspired by [`blacken-docs`](https://pypi.org/project/blacken-docs/)
  to format code in docstrings, via the new `shed.docshed` function

#### 0.1.3 - 2020-08-12
- detect first-party imports in single-file mode as well as all-repo mode

#### 0.1.2 - 2020-07-13
- run `pyupgrade --py36-plus` logic too
- print each file skipped due to permissions or encoding issues

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
