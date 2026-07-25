"""Exactly-once traversal pins (remediation 2.1 fix round, blocker B1).

The first battery asserted REACH but never MULTIPLICITY, so a frame-model bug
in ``TotalTraversalVisitor`` shipped green: a handler that dispatched a
GRANDCHILD (the case handlers' ``self.visit(item.commands)``) recorded the id
only in the grandparent's frame, and the intermediate ``CaseItem``'s own frame
re-swept it — every case branch analyzed twice, cost 2^N in nested-case depth
(verified 2 issues for one ``rm``, 4096 counted commands for one ``echo``
under 12 nested cases, 262,144 under 18).

These pins were run RED against tip 5116939e before the fix (replay recipe:
``git worktree add --detach <dir> 5116939e``, copy this file in, run it) and
pin the repaired invariant: ONE analysis dispatch per node object per
traversal, at any nesting depth, for every production analysis visitor.
"""

from collections import Counter

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import (
    EnhancedValidatorVisitor,
    LinterVisitor,
    MetricsVisitor,
    SecurityVisitor,
    ValidatorVisitor,
)

ALL_ANALYSIS_VISITORS = (
    ValidatorVisitor,
    EnhancedValidatorVisitor,
    SecurityVisitor,
    MetricsVisitor,
    LinterVisitor,
)


def _ast(src):
    return parse(tokenize(src))


def _dispatch_counts(visitor, root):
    """id -> number of times visitor.visit dispatched that node object."""
    counts: Counter = Counter()
    orig = visitor.visit

    def _recording_visit(n):
        counts[id(n)] += 1
        return orig(n)

    visitor.visit = _recording_visit  # type: ignore[method-assign]
    _recording_visit(root)
    return counts


def _nested_case(depth, innermost):
    src = innermost
    for _ in range(depth):
        src = f'case x in a) {src};; esac'
    return src


_MIXED = (
    'f() { case $1 in a) echo x | cat;; esac; }\n'
    'if true; then f a; fi\n'
    'for i in 1 2; do echo $(echo n); done\n'
    'while [ -n "$i" ]; do break; done > /tmp/out\n'
)


@pytest.mark.parametrize("visitor_cls", ALL_ANALYSIS_VISITORS,
                         ids=lambda c: c.__name__)
@pytest.mark.parametrize("src", [
    'case x in a) echo one;; b) echo two;; esac',
    _nested_case(4, 'echo deep'),
    _MIXED,
], ids=['flat-case', 'nested-case-4', 'mixed-constructs'])
def test_every_node_dispatched_exactly_once(visitor_cls, src):
    """No node object is analysis-dispatched more than once per traversal."""
    counts = _dispatch_counts(visitor_cls(), _ast(src))
    dupes = {i: c for i, c in counts.items() if c > 1}
    assert not dupes, (
        f"{visitor_cls.__name__} dispatched {len(dupes)} node(s) more than "
        f"once on {src!r}: multiplicities {sorted(dupes.values(), reverse=True)[:5]}"
    )


def test_one_dangerous_command_yields_one_security_issue():
    """The verifier's replay: one rm inside a case branch = ONE issue."""
    v = SecurityVisitor()
    v.visit(_ast('case x in a) rm -rf /tmp/psh-never-created;; esac'))
    assert len(v.issues) == 1, [str(i) for i in v.issues]


def test_metrics_counts_case_branch_commands_once():
    m = MetricsVisitor()
    m.visit(_ast('case x in a) echo a; echo b;; esac'))
    assert m.metrics.total_commands == 2


def test_nested_case_depth_is_linear_not_exponential():
    """Depth guard: 12 nested cases around ONE command count exactly 1
    command (the buggy frame model counted 2^12 = 4096)."""
    m = MetricsVisitor()
    m.visit(_ast(_nested_case(12, 'echo deep')))
    assert m.metrics.total_commands == 1

    v = SecurityVisitor()
    v.visit(_ast(_nested_case(12, 'rm -rf /tmp/psh-never-created')))
    assert len(v.issues) == 1, [str(i) for i in v.issues]


def test_linter_dedup_stays_benign():
    """NEGATIVE CONTROL (nit n5): the linter had no duplicate dispatch even
    under the buggy frame model (no case handler of its own) — pin that so it
    cannot silently regress either."""
    lv = LinterVisitor()
    lv.visit(_ast(_nested_case(3, 'eval "$y"')))
    dangerous = [i for i in lv.issues
                 if i.message == "Use of potentially dangerous command 'eval'"]
    assert len(dangerous) == 1, [i.message for i in lv.issues]


def test_manually_aliased_node_is_analyzed_once():
    """Legitimate re-entry, pinned: the parsers never alias (an AST is a
    tree), but a MANUALLY-built AST can place one node object under two
    edges. The documented behavior (TotalTraversalVisitor docstring): re-entry
    is a NO-OP at the visit() seam itself, so the node is ANALYZED exactly
    once whether the second edge arrives via the sweep or via a handler's own
    self.visit (the security Pipeline handler dispatches its members
    directly, which is exactly the second shape). Asserted at the analysis
    level — one rm object yields one issue, one echo object counts once —
    because the dispatch-count instrument tallies visit() CALLS, and the
    handler's second call legitimately happens before the no-op returns."""
    from psh.ast_nodes import Pipeline, SimpleCommand, StatementList, Word

    def aliased_tree(cmd_words):
        shared = SimpleCommand(words=[Word.from_string(w) for w in cmd_words])
        return StatementList(statements=[
            Pipeline(commands=[shared]),
            Pipeline(commands=[shared]),  # the SAME object, second edge
        ])

    v = SecurityVisitor()
    v.visit(aliased_tree(['rm', 'x']))
    assert len(v.issues) == 1, [str(i) for i in v.issues]

    m = MetricsVisitor()
    m.visit(aliased_tree(['echo', 'x']))
    assert m.metrics.total_commands == 1
