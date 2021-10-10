# type: ignore
"""Custom LibCST-based codemods for Shed.

These are mostly based on flake8, flake8-comprehensions, and some personal
nitpicks about typing unions and literals.
"""

from ast import literal_eval
from typing import Tuple

import libcst as cst
import libcst.matchers as m
from libcst._parser.types.config import _pick_compatible_python_version
from libcst.codemod import VisitorBasedCodemodCommand

try:
    from hypothesis.extra.codemods import (
        HypothesisFixComplexMinMagnitude as Hy1,
        HypothesisFixPositionalKeywonlyArgs as Hy2,
    )
except ImportError:  # pragma: no cover
    hypothesis_fixers = []
else:
    hypothesis_fixers = [Hy1, Hy2]


def _run_codemods(code: str, refactor: bool, min_version: Tuple[int, int]) -> str:
    """Run all Shed fixers on a code string."""
    context = cst.codemod.CodemodContext()

    # We want LibCST to parse the code as if running on our target minimum version,
    # but fall back to the latest version it supports (currently 3.8) if our target
    # version is newer than that.
    v = _pick_compatible_python_version(".".join(map(str, min_version)))
    config = cst.PartialParserConfig(python_version=f"{v.major}.{v.minor}")
    mod = cst.parse_module(code, config)

    for fixer in [ShedFixers] + refactor * hypothesis_fixers:
        mod = fixer(context).transform_module(mod)
    return mod.code


class ShedFixers(VisitorBasedCodemodCommand):
    """Fix a variety of small problems.

    Replaces `raise NotImplemented` with `raise NotImplementedError`,
    and converts always-failing assert statements to explicit `raise` statements.

    Also includes code closely modelled on pybetter's fixers, because it's
    considerably faster to run all transforms in a single pass if possible.
    """

    DESCRIPTION = "Fix `raise NotImplemented` and `assert False` statements."

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
        return updated_node.with_changes(lpar=[], rpar=[])
