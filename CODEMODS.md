This document attempts to document all codemods that shed does.


## `leave_Assert`
Remove redundant `assert x` where x is a literal that always evaluate to `True`.  
Replace `assert y` where y is a literal that always evaluates to `False`.

### Examples
#### input
```py
# truthy statements removed, with corresponding comments
assert True
assert "message"  # rip
assert (1, 2)

# false statements replaced with raise AssertionError
assert None
assert ""
assert 0, "hello"

assert False, "this is the only case handled by ruff"
```
#### output
```python
# false statements replaced with raise AssertionError
raise AssertionError
raise AssertionError
raise AssertionError("hello")

raise AssertionError("this is the only case handled by ruff")
```

Full test data in tests/recorded/asserts.txt

Ruff supports autofixing B011, but that only covers the precise case of exactly replacing `assert False` with `raise AssertionError`.

## `remove_pointless_parens_around_call`
Removes pointless parentheses wrapping a call.
Ruff has UP034, but that only handles a subset of the cases shed handles.

### Examples
Full test data in `tests/recorded/parens.txt` and `tests/recorded/parens_with_comment.txt`
#### input
```py
(list("abc"))
(["foo"].append("bar"))
(["foo"].append("bar"))
foo((list("abc")))  # only one handled by ruff

# handled by the codemod after shed runs black on it
(
    []
    .append(1)
)
```

#### output
```python
list("abc")
["foo"].append("bar")
["foo"].append("bar")
foo(list("abc"))  # only one handled by ruff

# handled by the codemod after shed runs black on it
[].append(1)
```


## `replace_unnecessary_nested_calls`
Resolves flake8-comprehension C414. Ruffs implementation currently breaks sorting stability in one case.

### Examples
Full test data in `tests/recorded/comprehensions/C414.txt`
#### input
```python
list(tuple(iterable))
set(reversed(iterable))
sorted(reversed(iterable))  # unsafe to fix, but ruff does

# cases handled by our codemod, but not by ruff
sorted(sorted(iterable, reverse=True))
sorted(sorted(iterable), reverse=True)
sorted(sorted(iterable, reverse=True), reverse=False)
sorted(sorted(iterable, reverse=False), reverse=True)

# unsafe to fix, even if both have the same key function (it might have side-effects)
sorted(sorted(iterable), key=int)
sorted(sorted(iterable, key=bool))
sorted(sorted(iterable, key=bool), key=int)
sorted(sorted(iterable, key=bool), key=bool)
```
#### output
```python
list(iterable)
set(iterable)
sorted(reversed(iterable))  # unsafe to fix, but ruff does

# cases handled by our codemod, but not by ruff
sorted(iterable)
sorted(iterable, reverse=True)
sorted(iterable, reverse=False)
sorted(iterable, reverse=True)

# unsafe to fix
sorted(sorted(iterable), key=int)
sorted(sorted(iterable, key=bool))
sorted(sorted(iterable, key=bool), key=int)
sorted(sorted(iterable, key=bool), key=bool)
```


## `replace_unnecessary_subscript_reversal`
Fix flake8-comprehensions C415.

Unnecessary subscript reversal of iterable within `[reversed/set/sorted]()`.
ruff does not support autofixing of C415

#### input
```python
set(iterable[::-1])
sorted(iterable[::-1])
reversed(iterable[::-1])

set(iterable[None:])
set(iterable[:None:1])
set(iterable[None:None:])
```
#### output
```python
set(iterable)
sorted(iterable)
reversed(iterable)

set(iterable)
set(iterable)
set(iterable)
```


## `reorder_union_literal_contents_none_last`
Puts `None` last in a subscript of `Union` or `Literal`

Test data in tests/recorded/flatten_literal.txt and tests/recorded/reorder_none.txt

#### input
```python
def g(x: Union[None, float] = None):
    pass


var3: Optional[None, int, float]
foo: set[None, int]
```
#### output
```python
def g(x: Union[int, None] = None):
    pass


var3: Optional[int, float, None]
foo: set[int, None]
```

## `reorder_merge_optional_union`
Turn `Union[..., None]` into `Optional[Union[...]]`. 

Test data in tests/recorded/flatten_union.txt
#### input
```python
Union[int, str, None]
Union[int, None, str]
```
#### output
```python
Optional[Union[int, str]]
Optional[Union[int, str]]
```

## `reorder_union_operator_contents_none_last`
Reorders binary-operator type unions to have `None` last.

Test data in tests/recorded/union_op_none_last.txt
#### input
```python
None | int  # not a type annotation
var: None | int
var2: bool | None | float
var3: float | None | bool
```
#### output
```python
None | int  # not a type annotation
var: int | None
var2: bool | float | None
var3: float | bool | None
```

## [Not Implemented] sort union types
Fully sort types in union/optional, so as to standardize their ordering and make it easier to see if two type annotations are in fact the same. This was never implemented, it was deemed to controversial as shed does not allow disabling specific checks, but may be of interest to ruff.

#### input
```python
k: Union[int, float]
l: Union[int, float]
m: float | bool
n: Optional[str, MyOtherType, bool]
```

#### output
```python
k: Union[float, int]
l: Union[float, int]
m: bool | float
n: Optional[MyOtherType, bool, str]
```

## `flatten_literal_subscript`
Flattens a `Literal` inside a `Literal`.

Test data in tests/recorded/flatten_literal.txt
#### input
```python
Literal[1, Literal[2, 3]]
```
#### output
```python
Literal[1, 2, 3]
```

## `flatten_union_subscript`
Flattens an `Optional`/`Union` inside a `Union`.

Test data in tests/recorded/flatten_literal.txt
#### input
```python
Union[int, Optional[str], bool]
Union[int, Optional[str], None]
Union[Union[int, float], str]
Union[int, Literal[1, 2]]  # this should not change
Union[int, Literal[1, 2], Optional[str]]
Union[int, str, None]
```
#### output
```python
Union[int, str, bool, None]
Union[int, str, None]
Union[int, float, str]
Union[int, Literal[1, 2]]  # this should not change
Union[int, Literal[1, 2], str, None]
Union[int, str, None]
```

## `discard_empty_else_blocks`
An `else: pass` block can always simply be discarded. This should also remove `else: ...` blocks but that's not currently supported.

Test data in tests/recorded/empty-else.txt
#### input
```python
if foo:
    ...
else:
    pass

while foo:
    ...
else:
    pass

for _ in range(10):
    ...
else:
    pass

try:
    1 / 0
except Exception:
    ...
else:
    pass

if foo:
    ...
else:
    ...
```

#### output
```python
if foo:
    ...

while foo:
    ...

for _ in range(10):
    ...

try:
    1 / 0
except Exception:
    ...

if foo:
    ...
else:  # should ideally be removed
    ...
```

## `remove_lambda_indirection`
Removes useless lambda wrapper.

Test data in tests/recorded/lambda-unwrapping.txt
#### input
```python
lambda: self.func()
lambda x: foo(x)
lambda x, y, z: (t + u).math_call(x, y, z)
```

#### output
```python
self.func
foo
(t + u).math_call
```

## `split_assert_and`
Split `assert a and b` into `assert a` and `assert b`. This is supported by ruff, but we have much more sophisticated handling of comments.

Test data in tests/recorded/split_assert.txt

## `remove_unnecessary_call_*`
Removes unnecessary len/bool calls in tests, autofixes PIE787.

No check for this in ruff; SIM103 needless-bool is specifically about returns.

Test data in tests/recorded/pie788_no_bool.txt and tests/recorded/pie788_no_len.txt

#### input
```python
if len(foo):
    ...
while bool(foo):
    ...
print(5 if len(foo) else 7)
```
#### output
```python
if foo:
    ...
while foo:
    ...
print(5 if foo else 7)
```

## `split_nested_with`
Ruff does this, but only if it wouldn't turn it into a multi-line with.

#### input
```python
with make_context_manager(1) as cm1:
    with make_context_manager(2) as cm2:
        pass
    # Preserve this comment

with make_context_manager(1) as cm1, make_context_manager(2) as cm2:
    with make_context_manager(3) as cm3:
        pass

with make_context_manager(1) as cm1:
    with make_context_manager(2) as cm2:
        with make_context_manager(3) as cm3:
            with make_context_manager(4) as cm4:
                pass
```

#### output
```python
with make_context_manager(1) as cm1, make_context_manager(2) as cm2:
    pass
    # Preserve this comment

with (
    make_context_manager(1) as cm1,
    make_context_manager(2) as cm2,
    make_context_manager(3) as cm3,
):
    pass

with (
    make_context_manager(1) as cm1,
    make_context_manager(2) as cm2,
    make_context_manager(3) as cm3,
    make_context_manager(4) as cm4,
):
    pass
```

## `replace_builtin_empty_collection` [removed]
A codemod that was removed in favor of ruffs C406/C409/C410/C418, but that also covered some cases that ruff currently raises no errors for.

#### input
```py
# handled by ruff
list([])  # C410
list(())  # C410

dict({})  # C418
dict([])  # C406
dict(())  # C406

tuple([])  # C409
tuple(())  # C409

# not handled by ruff, but was handled by our codemod
list({})
list("")
dict("")
tuple({})
tuple("")
```

#### output
```py
# handled by ruff
[]  # C410
[]  # C410

{}  # C418
{}  # C406
{}  # C406

()  # C409
()  # C409

# not handled by ruff, but was handled by our codemod
[]
[]
{}
()
()
```
