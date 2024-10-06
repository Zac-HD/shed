# Changelog
*`shed` uses [calendar versioning](https://calver.org/), with a year.month.patch scheme.*

#### 2024.10.1 - 2024-04-27
- Disable `PIE790` fix due to [ruff issue #10538](https://github.com/astral-sh/ruff/issues/10538)
- [Python 3.8 has reached end-of-life](https://devguide.python.org/versions/),
  so `shed` targets and runs on Python 3.9 or later.

#### 2024.3.1 - 2024-03-13
- Replace usage of Autoflake, PyUpgrade and isort with ruff.

#### 2024.1.1 - 2024-01-26
- Require `black >= 24.1.0`, with their [updated code style](https://black.readthedocs.io/en/stable/change_log.html)

#### 2023.6.1 - 2023-06-29
- [Python 3.7 has reached end-of-life](https://devguide.python.org/versions/),
  so `shed` targets and runs on Python 3.8 or later.
- Clarify error when missing target file looks like an unexpanded glob pattern.

#### 2023.5.2 - 2023-05-26
- Require latest versions of `black` and `libcst` for bugfixes and perf improvements

#### 2023.5.1 - 2023-05-01
- `shed --refactor` now merges nested with-statements for Python 3.9+
- Skip LibCST passes when it (correctly) objects to invalid code accepted by Black

#### 2023.4.1 - 2023-04-19
- Fixed some crash and incorrect-output bugs in `shed --refactor`

#### 2023.3.1 - 2023-03-05
- Fixed cases where `shed` took two passes to handle unordered and removable imports
- Fixed cases where `--refactor` was making unintended semantic changes

#### 2023.2.1 - 2023-02-27
- Switch to calendar versioning to match underlying tools
- Fixed cases where `--refactor` could delete comments in parens
- `--refactor` replaces some calls to `list()`, `tuple()` and `dict()` builtins with literals

#### 0.10.9 - 2023-02-01
- Require Black >= 23.1.0 for latest code style

#### 0.10.8 - 2022-12-10
- Reformat `.pyi` files too

#### 0.10.7 - 2022-11-05
- Fixed `--refactor` to avoid incorrect changes to e.g. `x = y or len(z)`
- `--refactor` also removes redundant calls to `bool()` in boolean contexts.

#### 0.10.6 - 2022-11-03
- `--refactor` now splits `assert a and b [and c and ...]` into a separate
  assertion for each clause, so that it's always clear which (if any) failed.
- `--refactor` removes redundant calls to `len()` in boolean contexts.

#### 0.10.5 - 2022-10-08
- Preserve trailing commas in literals in `--refactor` mode
- `--refactor` mode now flattens `Optional[Union[...]]` to `Union[..., None]`
- Don't convert `==` to `is` in subscripts, to save e.g. `df[df.flag == True]`

#### 0.10.4 - 2022-10-04
- Updated for compatibility with new `pyupgrade==3.0.0`

#### 0.10.3 - 2022-09-10
- Fix a crash when used with Python 3.10 pattern matching
- Fix a bug where the minimum-version argument was sometimes ignored
- Clarified some error messages for easier debugging

#### 0.10.2 - 2022-09-05
- Require latest version of Black to detect that `f"{x=}"` requires Python 3.8+
  (and remove previous workaround)
- Fixed detection of Hypothesis codemods in `--refactor` mode

#### 0.10.1 - 2022-06-06
- Handle non-locale-encoded files, such as UTF-8 on Windows (#42)
- Preserve comments on the last element of `Literal` types with `--refactor`

#### 0.10.0 - 2022-05-22
- When finding files in a git repo, search from root not current directory
- Keep `else: pass` blocks if they contain any comments
- Leave `Optional[Literal[...]]` alone too
- Merge `isinstance(x, y) or isinstance(x, z)` to `isinstance(x, (y, z))`

#### 0.9.7 - 2022-05-15
- Dropped `teyit` because `pyupgrade` now handles deprecated unittest methods
- Don't merge `None` into `Literal` types; it's easier to read `| None`
- Avoid crashing on some rare and questionable code patterns
- With `--refactor`, remove `else: pass` blocks
- With `--refactor`, "unwrap" lambdas - e.g. `lambda x: sorted(x)` -> `sorted`

#### 0.9.6 - 2022-05-12
- Several new custom refactoring passes (#37, #38, #39, #40)

#### 0.9.5 - 2022-04-12
- Supports (and requires) new version of `pyupgrade`

#### 0.9.4 - 2022-03-16
- Performance optimizations, reducing startup latency via deferred imports

#### 0.9.3 - 2022-03-14
- Fixed an internal error on `# isort: skip_file` (#32)

#### 0.9.2 - 2022-03-05
- Fixed a crash with `--refactor` on files containing `f"{...=}"` (#31)

#### 0.9.1 - 2022-02-15
- Fixed `__init__.py`-based detection heuristic for first-party module names
- Avoid guessing that stdlib modules are first-party due to e.g. a `code/` directory

#### 0.9.0 - 2022-02-01
- Require a stable version of Black, which now has a formatting stability policy
- Suppress ``stderr`` messages from Git when used outside a repository

#### 0.8.0 - 2022-01-16
- Updated minimum dependency versions - bugfixes and improved support for Python 3.9+
- Avoid importing Hypothesis if it's not going to be used (#26)

#### 0.7.0 - 2021-12-23
- Python 3.6 is end-of-life, so format code as 3.7+

#### 0.6.0 - 2021-12-16
- Codemods to fix most warnings from [`flake8-comprehensions`](https://pypi.org/project/flake8-comprehensions/), in `--refactor` mode
- Moves all `libCST` fixers to `--refactor` mode for speed

#### 0.5.3 - 2021-10-12
- Fix an internal error on files with lambdas containing positional-only arguments
  which were [not detected as requiring Python 3.8](https://github.com/psf/black/pull/2532)
- Fix an internal error on files with
  ['fluent interface' call chains](https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html#call-chains)
  (introduced in 0.5.2)

#### 0.5.2 - 2021-10-11
- Fix latent bugs around min-version handling with Black and LibCST
- Fix a rare crash with `--refactor` where com2ann could fail to parse input

#### 0.5.1 - 2021-10-05
- Continue in a single process if `os.fork()` fails with `BlockingIOError`

#### 0.5.0 - 2021-10-03
- Stop removing "unused" imports in code blocks; often they're used in later blocks
- Use custom LibCST refactoring passes instead of `pybetter`; because these are faster
  they're also enabled outside of `--refactor` mode
- Replace `raise NotImplemented` with `raise NotImplementedError`
- Replace `assert False [, msg]` with `raise AssertionError [(msg)]`, for all falsey
  literals, to avoid surprising behaviour with `PYTHONOPTIMIZE`
  (use `if __debug__` if you need such behaviour)
- Remove `assert True`, or other truthy literals, which can never fail

#### 0.4.2 - 2021-09-16
- Warn on invalid syntax, and try to format docstrings anyway
  ([#23](https://github.com/Zac-HD/shed/issues/23))

#### 0.4.1 - 2021-09-15
- Skip files or code-blocks with invalid syntax
  ([#23](https://github.com/Zac-HD/shed/issues/23))

#### 0.4.0 - 2021-09-15
- Add new `--py-37-plus` (etc) arguments to select the minimum Python version
- disable `autoflake`'s remove-unused-variables; allow linters to warn about probable bugs

#### 0.3.10 - 2021-08-21
- require latest versions of all dependencies; variously fixing some upstream bugs,
  avoiding installation problems, and adding some refactoring features.

#### 0.3.9 - 2021-08-18
- Fix the *other* `FileNotFoundError` on Windows, if `git` is not installed.

#### 0.3.8 - 2021-08-11
- Fix a `FileNotFoundError` on Windows, if `git` is not installed.

#### 0.3.7 - 2021-07-14
- require [`black >= 21.6b0`](https://github.com/psf/black/blob/master/CHANGES.md#216b0)
- support, and require, [`pyupgrade >= 2.21`](https://pypi.org/project/pyupgrade/)

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
