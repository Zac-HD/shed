# type: ignore
"""Custom LibCST-based codemods for Shed.

These are mostly based on flake8, flake8-comprehensions, and some personal
nitpicks about typing unions and literals.
"""

import os
import re
from ast import literal_eval
from functools import wraps
from typing import List, Tuple

import libcst as cst
import libcst.matchers as m
from libcst.codemod import VisitorBasedCodemodCommand


def leave(matcher):
    """Wrap `libcst.matchers.leave` for fixed behaviour.

    This works around https://github.com/Instagram/LibCST/issues/888
    by checking if the updated node matches the matcher.
    """

    def inner(fn):
        @wraps(fn)
        @m.leave(matcher)
        def wrapped(self, original_node, updated_node):
            if not m.matches(updated_node, matcher):
                return updated_node
            return fn(self, original_node, updated_node)

        return wrapped

    return inner


def attempt_hypothesis_codemods(context, mod):  # pragma: no cover
    try:
        from hypothesis.extra.codemods import (
            HypothesisFixComplexMinMagnitude,
            HypothesisFixPositionalKeywonlyArgs,
        )
    except ImportError:
        return mod
    mod = HypothesisFixComplexMinMagnitude(context).transform_module(mod)
    return HypothesisFixPositionalKeywonlyArgs(context).transform_module(mod)


imports_hypothesis = re.compile(
    r"^ *(?:import hypothesis|from hypothesis(?:\.[a-z]+)* import )", flags=re.MULTILINE
).search


def _run_codemods(code: str, min_version: Tuple[int, int]) -> str:
    """Run all Shed fixers on a code string."""
    context = cst.codemod.CodemodContext()

    # Only the native parser supports Python 3.9 and later, but for now it's
    # only active if you set an environment variable.  Very well then:
    var = os.environ.get("LIBCST_PARSER_TYPE")
    try:
        os.environ["LIBCST_PARSER_TYPE"] = "native"
        mod = cst.parse_module(code)
    finally:
        os.environ.pop("LIBCST_PARSER_TYPE")
        if var is not None:
            os.environ["LIBCST_PARSER_TYPE"] = var

    if imports_hypothesis(code):  # pragma: no cover
        mod = attempt_hypothesis_codemods(context, mod)
    mod = ShedFixers(context).transform_module(mod)
    return mod.code


def oneof_names(*names):
    return m.OneOf(*map(m.Name, names))


def multi(*args, **kwargs):
    """Return a combined matcher for multiple similar types.

    *args are the matcher types, and **kwargs are arguments that will be passed to
    each type.  Returns m.OneOf(...) the results.
    """
    return m.OneOf(*(a(**kwargs) for a in args))


def remove_trailing_comma(node):
    # Remove the comma from this node, *unless* it's already a comma node with comments
    if node.comma is cst.MaybeSentinel.DEFAULT or m.findall(node, m.Comment()):
        return node
    return node.with_changes(comma=cst.MaybeSentinel.DEFAULT)


MATCH_NONE = m.MatchIfTrue(lambda x: x is None)
ALL_ELEMS_SLICE = m.Slice(
    lower=MATCH_NONE | m.Name("None"),
    upper=MATCH_NONE | m.Name("None"),
    step=MATCH_NONE
    | m.Name("None")
    | m.Integer("1")
    | m.UnaryOperation(m.Minus(), m.Integer("1")),
)


# helper function for ShedFixers.remove_unnecessary_call
def _collapsible_expression():
    value = multi(
        m.Name,
        m.Attribute,
        m.Call,
        m.Dict,
        m.DictComp,
        m.List,
        m.ListComp,
        m.Set,
        m.SetComp,
    )
    return m.OneOf(
        m.Call(func=m.Name("len"), args=[m.Arg(value)]),
        m.Call(func=m.Name("bool")),
        m.BooleanOperation(),
    )


class ShedFixers(VisitorBasedCodemodCommand):
    """Fix a variety of small problems.

    Replaces `raise NotImplemented` with `raise NotImplementedError`,
    and converts always-failing assert statements to explicit `raise` statements.

    Also includes code closely modelled on pybetter's fixers, because it's
    considerably faster to run all transforms in a single pass if possible.
    """

    DESCRIPTION = "Fix a variety of style, performance, and correctness issues."

    @m.call_if_inside(m.Raise(exc=m.Name(value="NotImplemented")))
    def leave_Name(self, _, updated_node):  # noqa
        return updated_node.with_changes(value="NotImplementedError")

    def leave_Assert(self, _, updated_node):  # noqa
        test_code = cst.Module("").code_for_node(updated_node.test)
        try:
            test_literal = literal_eval(test_code)
        except Exception:
            return updated_node
        if test_literal:
            return cst.RemovalSentinel.REMOVE
        if updated_node.msg is None:
            return cst.Raise(cst.Name("AssertionError"))
        return cst.Raise(
            cst.Call(cst.Name("AssertionError"), args=[cst.Arg(updated_node.msg)])
        )

    @leave(m.ComparisonTarget(comparator=m.Name("None"), operator=m.Equal()))
    def convert_none_cmp(self, _, updated_node):
        """Inspired by Pybetter."""
        return updated_node.with_changes(operator=cst.Is())

    @leave(
        m.UnaryOperation(
            operator=m.Not(),
            expression=m.Comparison(comparisons=[m.ComparisonTarget(operator=m.In())]),
        )
    )
    def replace_not_in_condition(self, _, updated_node):
        """Also inspired by Pybetter."""
        expr = cst.ensure_type(updated_node.expression, cst.Comparison)
        return cst.Comparison(
            left=expr.left,
            lpar=updated_node.lpar,
            rpar=updated_node.rpar,
            comparisons=[expr.comparisons[0].with_changes(operator=cst.NotIn())],
        )

    @leave(
        m.Call(
            lpar=[m.AtLeastN(n=1, matcher=m.LeftParen())],
            rpar=[m.AtLeastN(n=1, matcher=m.RightParen())],
        )
    )
    def remove_pointless_parens_around_call(self, _, updated_node):
        # Don't remove whitespace if it includes comments
        if m.findall(updated_node, m.Comment()):
            return updated_node
        # This is *probably* valid, but we might have e.g. a multi-line parenthesised
        # chain of attribute accesses ("fluent interface"), where we need the parens.
        noparens = updated_node.with_changes(lpar=[], rpar=[])
        try:
            compile(self.module.code_for_node(noparens), "<string>", "eval")
            return noparens
        except SyntaxError:
            return updated_node

    @leave(m.Call(func=oneof_names("dict", "list", "tuple"), args=[]))
    def replace_builtin_with_literal(self, _, updated_node):
        if updated_node.func.value == "dict":
            return cst.Dict([])
        elif updated_node.func.value == "list":
            return cst.List([])
        else:
            assert updated_node.func.value == "tuple"
            return cst.Tuple([])

    @leave(
        m.Call(
            func=oneof_names("dict", "list", "tuple"),
            args=[m.Arg(m.Dict([]) | m.List([]) | m.SimpleString() | m.Tuple([]))],
        )
    )
    def replace_builtin_empty_collection(self, _, updated_node):
        # If there is a keyword argument either this is a dict (and thus
        # not empty) or the user has made an error we shouldn't mask.
        if updated_node.args[0].keyword:
            return updated_node
        val = updated_node.args[0].value
        val_is_empty_seq = (
            isinstance(val, (cst.Dict, cst.List, cst.Tuple)) and not val.elements
        )
        val_is_empty_str = (
            isinstance(val, cst.SimpleString) and val.evaluated_value == ""
        )
        if not (val_is_empty_seq or val_is_empty_str):
            return updated_node
        elif updated_node.func.value == "dict":
            return cst.Dict([])
        elif updated_node.func.value == "list":
            return cst.List([])
        else:
            assert updated_node.func.value == "tuple"
            return cst.Tuple([])

    # The following methods fix https://pypi.org/project/flake8-comprehensions/

    @leave(m.Call(func=m.Name("list"), args=[m.Arg(m.GeneratorExp())]))
    def replace_generator_in_call_with_comprehension(self, _, updated_node):
        """Fix flake8-comprehensions C400-402 and 403-404.

        C400-402: Unnecessary generator - rewrite as a <list/set/dict> comprehension.
        Note that set and dict conversions are handled by pyupgrade!
        """
        return cst.ListComp(
            elt=updated_node.args[0].value.elt, for_in=updated_node.args[0].value.for_in
        )

    @leave(
        m.Call(func=m.Name("list"), args=[m.Arg(m.ListComp(), star="")])
        | m.Call(func=m.Name("set"), args=[m.Arg(m.SetComp(), star="")])
        | m.Call(
            func=m.Name("list"),
            args=[m.Arg(m.Call(func=oneof_names("sorted", "list")), star="")],
        )
    )
    def replace_unnecessary_list_around_sorted(self, _, updated_node):
        """Fix flake8-comprehensions C411 and C413.

        Unnecessary list() call around sorted().

        Also covers C411 Unnecessary list call around list comprehension
        for lists and sets.
        """
        return updated_node.args[0].value

    _sets = oneof_names("set", "frozenset")
    _seqs = oneof_names("list", "sorted", "tuple")

    @leave(
        m.Call(
            func=_sets,
            args=[m.Arg(m.Call(func=_sets | _seqs | m.Name("reversed")), star="")],
        )
        | m.Call(
            func=oneof_names("list", "tuple"),
            args=[m.Arg(m.Call(func=oneof_names("list", "tuple")), star="")],
        )
        | m.Call(
            func=m.Name("sorted"),
            args=[m.Arg(m.Call(func=_seqs), star=""), m.ZeroOrMore()],
        )
    )
    def replace_unnecessary_nested_calls(self, _, updated_node):
        """Fix flake8-comprehensions C414.

        Unnecessary <list/sorted/tuple> call within <list/set/sorted/tuple>()..
        """
        # If either of two nested sorted calls have a key, it's incorrect to try
        # to merge them. Theoretically the keys could be combined into a tuple,
        # but this is hard to make work in generality, and it's better to just
        # leave this alone and let a human deal with it if they care.
        if (
            updated_node.func.value == "sorted"
            and updated_node.args[0].value.func.value == "sorted"
            and any(
                arg.keyword and arg.keyword.value == "key"
                for args in (updated_node.args, updated_node.args[0].value.args)
                for arg in args
            )
        ):
            return updated_node

        return updated_node.with_changes(
            args=[cst.Arg(updated_node.args[0].value.args[0].value)]
            + list(updated_node.args[1:]),
        )

    @leave(
        m.Call(
            func=oneof_names("reversed", "set", "sorted"),
            args=[m.Arg(m.Subscript(slice=[m.SubscriptElement(ALL_ELEMS_SLICE)]))],
        )
    )
    def replace_unnecessary_subscript_reversal(self, _, updated_node):
        """Fix flake8-comprehensions C415.

        Unnecessary subscript reversal of iterable within <reversed/set/sorted>().
        """
        return updated_node.with_changes(
            args=[cst.Arg(updated_node.args[0].value.value)],
        )

    @leave(
        multi(
            m.ListComp,
            m.SetComp,
            elt=m.Name(),
            for_in=m.CompFor(
                target=m.Name(), ifs=[], inner_for_in=None, asynchronous=None
            ),
        )
    )
    def replace_unnecessary_listcomp_or_setcomp(self, _, updated_node):
        """Fix flake8-comprehensions C416.

        Unnecessary <list/set> comprehension - rewrite using <list/set>().
        """
        if updated_node.elt.value == updated_node.for_in.target.value:
            func = cst.Name("list" if isinstance(updated_node, cst.ListComp) else "set")
            return cst.Call(func=func, args=[cst.Arg(updated_node.for_in.iter)])
        return updated_node

    @leave(m.Subscript(oneof_names("Union", "Literal")))
    def reorder_union_literal_contents_none_last(self, _, updated_node):
        subscript = list(updated_node.slice)
        try:
            has_comma = isinstance(subscript[-1].comma, cst.Comma)
            subscript.sort(key=lambda elt: elt.slice.value.value == "None")
            if not has_comma:
                subscript[-1] = remove_trailing_comma(subscript[-1])
            return updated_node.with_changes(slice=subscript)
        except Exception:  # Single-element literals are not slices, etc.
            return updated_node

    @leave(
        m.Subscript(
            m.Name("Optional"),
            [m.SubscriptElement(m.Index(m.Subscript(value=m.Name("Union"))))],
        )
    )
    def reorder_merge_optional_union(self, _, updated_node):
        union = updated_node.slice[0].slice.value
        none = [cst.SubscriptElement(cst.Index(cst.Name("None")))]
        return union.with_changes(slice=list(union.slice) + none)

    @m.call_if_inside(m.Annotation(annotation=m.BinaryOperation()))
    @leave(
        m.BinaryOperation(
            left=m.Name("None") | m.BinaryOperation(),
            operator=m.BitOr(),
            right=m.DoNotCare(),
        )
    )
    def reorder_union_operator_contents_none_last(self, _, updated_node):
        def _has_none(node):
            if m.matches(node, m.Name("None")):
                return True
            elif m.matches(node, m.BinaryOperation()):
                return _has_none(node.left) or _has_none(node.right)
            else:
                return False

        node_left = updated_node.left
        if _has_none(node_left):
            return updated_node.with_changes(left=updated_node.right, right=node_left)
        else:
            return updated_node

    @leave(m.Subscript(value=m.Name("Literal")))
    def flatten_literal_subscript(self, _, updated_node):
        new_slice = []
        for item in updated_node.slice:
            if m.matches(item.slice.value, m.Subscript(m.Name("Literal"))):
                new_slice += item.slice.value.slice
            else:
                new_slice.append(item)
        return updated_node.with_changes(slice=new_slice)

    @leave(m.Subscript(value=m.Name("Union")))
    def flatten_union_subscript(self, _, updated_node):
        new_slice = []
        has_none = False
        for item in updated_node.slice:
            if m.matches(item.slice.value, m.Subscript(m.Name("Optional"))):
                new_slice += item.slice.value.slice  # peel off "Optional"
                has_none = True
            elif m.matches(
                item.slice.value, m.Subscript(m.Name("Union"))
            ) and m.matches(updated_node.value, item.slice.value.value):
                new_slice += item.slice.value.slice  # peel off "Union" or "Literal"
            elif m.matches(item.slice.value, m.Name("None")):
                has_none = True
            else:
                new_slice.append(item)
        if has_none:
            new_slice.append(cst.SubscriptElement(slice=cst.Index(cst.Name("None"))))
        return updated_node.with_changes(slice=new_slice)

    @leave(m.Else(m.IndentedBlock([m.SimpleStatementLine([m.Pass()])])))
    def discard_empty_else_blocks(self, _, updated_node):
        # An `else: pass` block can always simply be discarded, and libcst ensures
        # that an Else node can only ever occur attached to an If, While, For, or Try
        # node; in each case `None` is the valid way to represent "no else block".
        if m.findall(updated_node, m.Comment()):
            return updated_node  # If there are any comments, keep the node
        return cst.RemoveFromParent()

    @leave(
        m.Lambda(
            params=m.MatchIfTrue(
                lambda node: (
                    node.star_kwarg is None
                    and not node.kwonly_params
                    and not node.posonly_params
                    and isinstance(node.star_arg, cst.MaybeSentinel)
                    and all(param.default is None for param in node.params)
                )
            )
        )
    )
    def remove_lambda_indirection(self, _, updated_node):
        same_args = [
            m.Arg(m.Name(param.name.value), star="", keyword=None)
            for param in updated_node.params.params
        ]
        if m.matches(updated_node.body, m.Call(args=same_args)):
            return cst.ensure_type(updated_node.body, cst.Call).func
        return updated_node

    @leave(
        m.BooleanOperation(
            left=m.Call(m.Name("isinstance"), [m.Arg(), m.Arg()]),
            operator=m.Or(),
            right=m.Call(m.Name("isinstance"), [m.Arg(), m.Arg()]),
        )
    )
    def collapse_isinstance_checks(self, _, updated_node):
        left_target, left_type = updated_node.left.args
        right_target, right_type = updated_node.right.args
        if left_target.deep_equals(right_target):
            merged_type = cst.Arg(
                cst.Tuple([cst.Element(left_type.value), cst.Element(right_type.value)])
            )
            return updated_node.left.with_changes(args=[left_target, merged_type])
        return updated_node

    # main function to split assertions
    # i.e. turn `assert a and b` into `assert a` and `assert b`
    # it's a separate function, since it recursively calls itself on recursive structures,
    # e.g. `a and (b and c)` and `a and b and c`
    # it handles comments on multi-line assertions, assigning comments to the correct
    # statements as far as possible
    # The parent SimpleLineStatement can have comments on leading lines, these are sent
    # in `leading_lines` and put before the first assert.
    # It can also have a comment in
    # it's TrailingWhitespace, which is sent in `comments` and added to the correct
    # statement, or left until the end to be added at the end.
    # Further comments are saved in
    # [lpar/operator/rpar].[whitespace_after/whitespace_before].[first_line/empty_lines]
    # and set as leading_lines and trailing_whitespace for the different assert statements.
    # comments on lines after the last tested statement are added to a pass statement,
    # this will require manual intervention - but in libCST comments are either on the
    # lines before, or the same line as, a statement. In theory one could do a module-level
    # analysis, but this should be a very rare case and regardless the user will probably
    # need to manually intervene.
    def _flatten_bool(
        self,
        expr,
        leading_lines: List[cst.EmptyLine],
        comments: List[cst.Comment],
    ) -> List[cst.SimpleStatementLine]:
        def handle_leftright(node, comments, nodes, leading_lines):
            # if node is a BoolOp, recurse - sending them our leading lines
            if m.matches(node, m.BooleanOperation(operator=m.And())):
                nodes.extend(self._flatten_bool(node, leading_lines, comments))
            else:
                nodes.append(
                    cst.SimpleStatementLine(
                        [cst.Assert(node)],
                        leading_lines,
                        cst.TrailingWhitespace(
                            whitespace=cst.SimpleWhitespace("  " if comments else ""),
                            comment=comments.pop(0) if comments else None,
                        ),
                    )
                )

        assert m.matches(expr, m.BooleanOperation(operator=m.And()))

        nodes = []
        if not leading_lines:
            leading_lines = []

        # add comments in expr.lpar as leading_lines
        for lpar in expr.lpar:
            if m.matches(lpar.whitespace_after, m.ParenthesizedWhitespace()):
                leading_lines.append(
                    cst.EmptyLine(comment=lpar.whitespace_after.first_line.comment)
                )
                for empty_line in lpar.whitespace_after.empty_lines:
                    leading_lines.append(cst.EmptyLine(comment=empty_line.comment))

        # the comment belonging to the left value (or left.right in nested cases) is
        # put in operator.whitespace_before.first_line for some reason, so we add it
        # to comments before handling left.
        if isinstance(expr.operator.whitespace_before, cst.ParenthesizedWhitespace):
            comments.insert(0, expr.operator.whitespace_before.first_line.comment)

        # handle left value, updating comments & nodes
        handle_leftright(expr.left, comments, nodes, leading_lines)

        # the other comments on the operator are added as leading lines to the right
        # value
        leading_lines = []
        if isinstance(expr.operator.whitespace_before, cst.ParenthesizedWhitespace):
            leading_lines.extend(expr.operator.whitespace_before.empty_lines)
        if isinstance(expr.operator.whitespace_after, cst.ParenthesizedWhitespace):
            leading_lines.append(expr.operator.whitespace_after.first_line)
            leading_lines.extend(expr.operator.whitespace_after.empty_lines)

        # add first comment in rpar.whitespace_before.first_line to comments
        # as this would be the comment on the same line as right
        if expr.rpar and m.matches(
            expr.rpar[0].whitespace_before, m.ParenthesizedWhitespace()
        ):
            comments.insert(0, expr.rpar[0].whitespace_before.first_line.comment)

        # handle right value, updating comments & nodes
        handle_leftright(expr.right, comments, nodes, leading_lines)

        # shuffle around references a bit to insert all rpar comments before old comments
        # and preserve the reference to comments
        old_comments = comments.copy()
        comments.clear()
        for i, rpar in enumerate(expr.rpar):
            if m.matches(rpar.whitespace_before, m.ParenthesizedWhitespace()):
                # other reformatters remove extra parentheses, so unless they change
                # this won't be executed (afaik)
                if i != 0:  # pragma: no cover
                    comments.append(rpar.whitespace_before.first_line.comment)
                for line in rpar.whitespace_before.empty_lines:
                    comments.append(line.comment)
        comments.extend(old_comments)
        # remaining comments are handled by the caller afterwards

        return nodes

    # split `assert a and b` into `assert a` and `assert b`
    @leave(
        m.SimpleStatementLine(
            body=[m.Assert(msg=None, test=m.BooleanOperation(operator=m.And()))]
        )
    )
    def split_assert_and(self, _, updated_node):
        # the simple statements trailing whitespace may be on the same line
        # as the first assert, or if there's sufficient comments within the assert
        # it may be left for later and inserted at the end.
        if m.matches(
            updated_node,
            m.SimpleStatementLine(
                trailing_whitespace=m.TrailingWhitespace(comment=m.Comment())
            ),
        ):
            comments = [updated_node.trailing_whitespace.comment]
        else:
            comments = []

        nodes = self._flatten_bool(
            updated_node.body[0].test, list(updated_node.leading_lines), comments
        )

        # if there is a single comment left and the last node doesn't have trailing
        # whitespace, add it as trailing whitespace to the last
        # statement
        if len(comments) == 1 and nodes[-1].trailing_whitespace.comment is None:
            nodes[-1] = nodes[-1].with_changes(
                trailing_whitespace=cst.TrailingWhitespace(
                    whitespace=cst.SimpleWhitespace("  "), comment=comments.pop()
                )
            )
        # if there are multiple comments left, e.g. comments on lines after the last rpar,
        # insert them as leading lines to a pass statement and let the user handle them
        elif comments:
            nodes.append(
                cst.SimpleStatementLine(
                    [cst.Pass()],  # pointless-pass is removed by autoflake later
                    [cst.EmptyLine(comment=c) for c in comments],
                    cst.TrailingWhitespace(whitespace=cst.SimpleWhitespace(" ")),
                )
            )
        # work around https://github.com/Instagram/LibCST/issues/911
        try:
            cst.parse_module(cst.Module([*nodes]).code)
        except Exception:
            return updated_node
        return cst.FlattenSentinel(nodes)

    # Remove unnecessary len() and bool() calls in tests
    # we can't use call_if_inside since it matches on any parents, which breaks on
    # complicated nested cases - so we have to split into different leave's
    # len/bool inside boolops (and/or) can only be removed if the boolop is inside a test
    # otherwise `print(False or bool(5))` changes functionality (prints `True` vs `5`)
    @leave(
        multi(
            m.If,
            m.IfExp,
            m.While,
            test=_collapsible_expression(),
        )
    )
    def remove_unnecessary_call_test(self, _, updated_node):
        return self._collapse_attribute(updated_node, "test")

    # remove not:ed len/bool
    # `not len(foo)` -> `not foo`
    @leave(m.UnaryOperation(operator=m.Not(), expression=_collapsible_expression()))
    def remove_unnecessary_call_expression(self, _, updated_node):
        return self._collapse_attribute(updated_node, "expression")

    # used by the above functions
    @classmethod
    def _collapse_attribute(cls, node, attr):
        child_node = getattr(node, attr)

        # if the attribute is a boolop, recurse through it and replace len/bool that are
        # direct child nodes to (a chain of) boolops
        if isinstance(child_node, cst.BooleanOperation):
            return node.with_changes(**{attr: cls._remove_recursive_helper(child_node)})
        # otherwise just remove the len/bool
        return node.with_changes(**{attr: child_node.args[0]})

    # remove len/bool inside bool()
    # `bool(len(foo))` or `bool(bool(foo))` -> `bool(foo)`
    @leave(m.Call(func=m.Name("bool"), args=[m.Arg(value=_collapsible_expression())]))
    def remove_unnecessary_call2(self, _, updated_node):
        collapse_node = updated_node.args[0].value
        if isinstance(collapse_node, cst.BooleanOperation):
            return updated_node.with_deep_changes(
                updated_node.args[0], value=self._remove_recursive_helper(collapse_node)
            )

        return updated_node.with_changes(args=updated_node.args[0].value.args)

    # remove len/bool inside (any number of) boolops inside the above
    @classmethod
    def _remove_recursive_helper(cls, bool_node):
        for side in "left", "right":
            side_node = getattr(bool_node, side)
            if isinstance(side_node, cst.BooleanOperation):
                bool_node = bool_node.with_changes(
                    **{side: cls._remove_recursive_helper(side_node)},
                )
            elif m.matches(side_node, _collapsible_expression()):
                bool_node = bool_node.with_changes(
                    **{side: side_node.args[0]},
                )
        return bool_node
