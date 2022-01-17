# type: ignore
"""Custom LibCST-based codemods for Shed.

These are mostly based on flake8, flake8-comprehensions, and some personal
nitpicks about typing unions and literals.
"""

import re
from ast import literal_eval
from typing import Tuple

import libcst as cst
import libcst.matchers as m
from libcst._parser.types.config import _pick_compatible_python_version
from libcst.codemod import VisitorBasedCodemodCommand


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
    r"^ *(?:import hypothesis|from hypothesis(?:\.[a-z]+)* import )"
).search


def _run_codemods(code: str, min_version: Tuple[int, int]) -> str:
    """Run all Shed fixers on a code string."""
    context = cst.codemod.CodemodContext()

    # We want LibCST to parse the code as if running on our target minimum version,
    # but fall back to the latest version it supports (currently 3.8) if our target
    # version is newer than that.
    v = _pick_compatible_python_version(".".join(map(str, min_version)))
    config = cst.PartialParserConfig(python_version=f"{v.major}.{v.minor}")
    mod = cst.parse_module(code, config)

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


MATCH_NONE = m.MatchIfTrue(lambda x: x is None)
ALL_ELEMS_SLICE = m.Slice(
    lower=MATCH_NONE | m.Name("None"),
    upper=MATCH_NONE | m.Name("None"),
    step=MATCH_NONE
    | m.Name("None")
    | m.Integer("1")
    | m.UnaryOperation(m.Minus(), m.Integer("1")),
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

    @m.leave(m.ComparisonTarget(comparator=m.Name(value="None"), operator=m.Equal()))
    def convert_none_cmp(self, _, updated_node):
        """Inspired by Pybetter."""
        return updated_node.with_changes(operator=cst.Is())

    @m.leave(
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

    @m.leave(
        m.Call(
            lpar=[m.AtLeastN(n=1, matcher=m.LeftParen())],
            rpar=[m.AtLeastN(n=1, matcher=m.RightParen())],
        )
    )
    def remove_pointless_parens_around_call(self, _, updated_node):
        # This is *probably* valid, but we might have e.g. a multi-line parenthesised
        # chain of attribute accesses ("fluent interface"), where we need the parens.
        noparens = updated_node.with_changes(lpar=[], rpar=[])
        try:
            compile(self.module.code_for_node(noparens), "<string>", "eval")
            return noparens
        except SyntaxError:
            return updated_node

    # The following methods fix https://pypi.org/project/flake8-comprehensions/

    @m.leave(m.Call(func=m.Name("list"), args=[m.Arg(m.GeneratorExp())]))
    def replace_generator_in_call_with_comprehension(self, _, updated_node):
        """Fix flake8-comprehensions C400-402 and 403-404.

        C400-402: Unnecessary generator - rewrite as a <list/set/dict> comprehension.
        Note that set and dict conversions are handled by pyupgrade!
        """
        return cst.ListComp(
            elt=updated_node.args[0].value.elt, for_in=updated_node.args[0].value.for_in
        )

    @m.leave(
        m.Call(func=m.Name("list"), args=[m.Arg(m.ListComp(), star="")])
        | m.Call(func=m.Name("set"), args=[m.Arg(m.SetComp(), star="")])
        | m.Call(
            func=m.Name("list"),
            args=[m.Arg(m.Call(func=oneof_names("sorted", "list")), star="")],
        )
    )
    def replace_unnecessary_list_around_sorted(self, _, updated_node):
        """Fix flake8-comprehensions C411 and C413.

        Unnecessary <list/reversed> call around sorted().

        Also covers C411 Unnecessary list call around list comprehension
        for lists and sets.
        """
        return updated_node.args[0].value

    @m.leave(
        m.Call(
            func=m.Name("reversed"),
            args=[m.Arg(m.Call(func=m.Name("sorted")), star="")],
        )
    )
    def replace_unnecessary_reversed_around_sorted(self, _, updated_node):
        """Fix flake8-comprehensions C413.

        Unnecessary reversed call around sorted().
        """
        call = updated_node.args[0].value
        args = list(call.args)
        for i, arg in enumerate(args):
            if m.matches(arg.keyword, m.Name("reverse")):
                try:
                    val = bool(literal_eval(self.module.code_for_node(arg.value)))
                except Exception:
                    args[i] = arg.with_changes(
                        value=cst.UnaryOperation(cst.Not(), arg.value)
                    )
                else:
                    if not val:
                        args[i] = arg.with_changes(value=cst.Name("True"))
                    else:
                        del args[i]
                        args[i - 1] = args[i - 1].with_changes(
                            comma=cst.MaybeSentinel.DEFAULT
                        )
                break
        else:
            args.append(cst.Arg(keyword=cst.Name("reverse"), value=cst.Name("True")))
        return call.with_changes(args=args)

    _sets = oneof_names("set", "frozenset")
    _seqs = oneof_names("list", "reversed", "sorted", "tuple")

    @m.leave(
        m.Call(func=_sets, args=[m.Arg(m.Call(func=_sets | _seqs), star="")])
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

        Unnecessary <list/reversed/sorted/tuple> call within <list/set/sorted/tuple>()..
        """
        return updated_node.with_changes(
            args=[cst.Arg(updated_node.args[0].value.args[0].value)]
            + list(updated_node.args[1:]),
        )

    @m.leave(
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

    @m.leave(
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
