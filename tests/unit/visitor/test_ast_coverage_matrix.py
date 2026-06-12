"""AST coverage matrix: visitor tooling must stay total over the AST.

These tests introspect every concrete AST node class in ``psh/ast_nodes.py``
and assert that each visitor handles every node it is supposed to handle,
via the mechanism that visitor actually uses:

- **FormatterVisitor** emits ``# Unknown node: X`` from ``generic_visit``,
  so every concrete node class must have an explicit ``visit_X`` method.
- **ExecutorVisitor** raises from ``generic_visit`` (base class), so every
  *executable* node must have an explicit ``visit_X`` method.
- **ValidatorVisitor** (and EnhancedValidatorVisitor, which inherits from
  it) has a non-traversing ``generic_visit`` (``pass``): any executable node
  without an explicit method is silently skipped, children and all. So every
  executable node must have an explicit ``visit_X`` method.
- **SecurityVisitor / MetricsVisitor / LinterVisitor** use the shared
  ``visit_children`` walk as ``generic_visit``, so nodes without explicit
  methods are still traversed; the tests verify that traversal behaviorally.

A second matrix covers the ``redirects`` field: for every node class that
carries one, parsing real source with a sensitive-path redirect must make
the security visitor flag it, the formatter emit it, and the metrics
visitor count it.

When a new AST node class is added these tests fail loudly until the node
is either supported by the relevant visitors or added to an exemption list
below with a justification.
"""

import dataclasses
import inspect

import pytest

import psh.ast_nodes as ast_mod
from psh.ast_nodes import (
    ArrayAssignment,
    ASTNode,
    BreakStatement,
    Command,
    ContinueStatement,
    Pipeline,
    Redirect,
    SimpleCommand,
    Statement,
    StatementList,
    TopLevel,
    WordPart,
)
from psh.executor.core import ExecutorVisitor
from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import (
    EnhancedValidatorVisitor,
    FormatterVisitor,
    LinterVisitor,
    MetricsVisitor,
    SecurityVisitor,
    ValidatorVisitor,
)
from psh.visitor.traversal import iter_child_nodes

# ---------------------------------------------------------------------------
# Node inventory (the introspection spine)
# ---------------------------------------------------------------------------

# Dataclass-decorated classes that are nevertheless pure base classes: no
# parser ever instantiates them directly and dispatch never sees them.
_ABSTRACT_DATACLASS_BASES = {ArrayAssignment, WordPart}


def concrete_node_classes():
    """Every concrete AST node class defined in psh.ast_nodes.

    Concrete means: subclass of ASTNode, defined in psh.ast_nodes, and a
    dataclass (the non-dataclass classes - ASTNode, Statement, Command,
    CompoundCommand, Expansion, TestExpression, UnifiedControlStructure -
    are abstract bases), minus the dataclass-decorated pure bases above.
    """
    seen, out = set(), []
    for obj in vars(ast_mod).values():
        if (inspect.isclass(obj)
                and issubclass(obj, ASTNode)
                and obj.__module__ == 'psh.ast_nodes'
                and dataclasses.is_dataclass(obj)
                and obj not in _ABSTRACT_DATACLASS_BASES
                and obj not in seen):
            seen.add(obj)
            out.append(obj)
    return sorted(out, key=lambda c: c.__name__)


def executable_node_classes():
    """Statement/command nodes plus the structural containers.

    These are the nodes the executor and validator dispatch on. Word-level
    nodes (Word, WordPart subclasses, Expansion subclasses), test-expression
    nodes and helper nodes (Redirect, CaseItem, CasePattern, array
    assignments) are consumed as *data* by their parent's handler, not
    dispatched through visit().
    """
    containers = {TopLevel, StatementList, Pipeline}
    return [c for c in concrete_node_classes()
            if issubclass(c, (Statement, Command)) or c in containers]


def _ast(src):
    return parse(tokenize(src))


def _find_nodes(root, cls):
    """Collect all nodes of type *cls* in the tree rooted at *root*."""
    out, stack = [], [root]
    while stack:
        node = stack.pop()
        if isinstance(node, cls):
            out.append(node)
        stack.extend(iter_child_nodes(node))
    return out


def test_inventory_is_sane():
    """The introspection itself must keep finding the known node set."""
    names = {c.__name__ for c in concrete_node_classes()}
    # Spot-check entries from each category so an introspection regression
    # (e.g. an import refactor) cannot silently empty the matrix.
    for expected in ('SimpleCommand', 'UntilLoop', 'Word', 'LiteralPart',
                     'ProcessSubstitution', 'Redirect', 'CasePattern',
                     'BinaryTestExpression', 'ArrayInitialization'):
        assert expected in names
    assert len(names) >= 36


# ---------------------------------------------------------------------------
# Explicit visit_ method coverage
# ---------------------------------------------------------------------------

# Formatter: must be total over every concrete node class. The
# ``# Unknown node`` generic_visit stays only as a defensive fallback for
# future node types; no current node may rely on it.
FORMATTER_EXEMPT = set()

# Executor: must cover every executable node. Helper/word nodes are data.
EXECUTOR_EXEMPT = set()

# Validator: generic_visit is non-traversing, so every executable node needs
# an explicit method or its subtree is silently skipped.
VALIDATOR_EXEMPT = set()


def test_formatter_has_visit_method_for_every_concrete_node():
    missing = [c.__name__ for c in concrete_node_classes()
               if c not in FORMATTER_EXEMPT
               and not hasattr(FormatterVisitor, f'visit_{c.__name__}')]
    assert not missing, (
        f"FormatterVisitor lacks visit_ methods for: {missing}. "
        "Real nodes must never hit the '# Unknown node' fallback - add a "
        "visit method (or, only for a genuinely unreachable node, add it to "
        "FORMATTER_EXEMPT with a justification)."
    )


def test_executor_has_visit_method_for_every_executable_node():
    missing = [c.__name__ for c in executable_node_classes()
               if c not in EXECUTOR_EXEMPT
               and not hasattr(ExecutorVisitor, f'visit_{c.__name__}')]
    assert not missing, (
        f"ExecutorVisitor lacks visit_ methods for: {missing}. "
        "ExecutorVisitor.generic_visit raises NotImplementedError, so these "
        "nodes cannot be executed."
    )


@pytest.mark.parametrize("visitor_cls", [ValidatorVisitor, EnhancedValidatorVisitor])
def test_validator_has_visit_method_for_every_executable_node(visitor_cls):
    missing = [c.__name__ for c in executable_node_classes()
               if c not in VALIDATOR_EXEMPT
               and not hasattr(visitor_cls, f'visit_{c.__name__}')]
    assert not missing, (
        f"{visitor_cls.__name__} lacks visit_ methods for: {missing}. "
        "Its generic_visit is a non-traversing pass, so these nodes (and "
        "their entire subtrees) would be silently skipped during validation."
    )


# ---------------------------------------------------------------------------
# Traversing generic_visit (security / metrics / linter design)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class _UnknownCarrier(ASTNode):
    """A node type no visitor knows, to force the generic_visit path."""
    child: ASTNode = None
    redirects: list = dataclasses.field(default_factory=list)


def test_security_generic_visit_traverses_children():
    v = SecurityVisitor()
    v.visit(_UnknownCarrier(redirects=[Redirect(type='>', target='/etc/passwd')]))
    assert any(i.issue_type == 'SENSITIVE_FILE_WRITE' for i in v.issues), (
        "SecurityVisitor.generic_visit must descend into children "
        "(including redirects) of unhandled node types"
    )


def test_metrics_generic_visit_traverses_children():
    v = MetricsVisitor()
    v.visit(_UnknownCarrier(child=SimpleCommand(args=['echo'])))
    assert v.metrics.total_commands == 1, (
        "MetricsVisitor.generic_visit must descend into children of "
        "unhandled node types"
    )


def test_linter_generic_visit_traverses_children():
    v = LinterVisitor()
    v.visit(_UnknownCarrier(child=SimpleCommand(args=['eval', 'x'])))
    assert any('eval' in i.message for i in v.issues), (
        "LinterVisitor.generic_visit must descend into children of "
        "unhandled node types"
    )


# ---------------------------------------------------------------------------
# Redirects-field matrix
# ---------------------------------------------------------------------------

# Source snippet producing each redirect-carrying node WITH a redirect
# attached, written against a sensitive path the security visitor flags.
REDIRECT_SOURCES = {
    'SimpleCommand': 'echo x >/etc/passwd',
    'WhileLoop': 'while true; do :; done >/etc/passwd',
    'UntilLoop': 'until false; do :; done >/etc/passwd',
    'ForLoop': 'for i in 1; do :; done >/etc/passwd',
    'CStyleForLoop': 'for ((i=0; i<1; i++)); do :; done >/etc/passwd',
    'IfConditional': 'if true; then :; fi >/etc/passwd',
    'CaseConditional': 'case x in a) :;; esac >/etc/passwd',
    'SelectLoop': 'select x in a; do :; done >/etc/passwd',
    'SubshellGroup': '( : ) >/etc/passwd',
    'BraceGroup': '{ :; } >/etc/passwd',
    'FunctionDef': 'f() { :; } >/etc/passwd',
    'EnhancedTestStatement': '[[ -n x ]] >/etc/passwd',
    'ArithmeticEvaluation': '((1 + 1)) >/etc/passwd',
}

# Nodes whose redirects field is unreachable from source: both parsers
# treat a redirect after break/continue as a separate command
# (`break >f` parses as BreakStatement followed by a bare-redirect
# SimpleCommand). The field exists only to satisfy the Command interface.
REDIRECT_EXEMPT = {'BreakStatement', 'ContinueStatement'}


def _redirect_carrier_classes():
    return [c for c in concrete_node_classes()
            if any(f.name == 'redirects' for f in dataclasses.fields(c))]


def test_redirect_field_inventory_matches_matrix():
    """Every node class with a redirects field is in the matrix or exempt."""
    carriers = {c.__name__ for c in _redirect_carrier_classes()}
    covered = set(REDIRECT_SOURCES) | REDIRECT_EXEMPT
    assert carriers == covered, (
        f"redirects-field inventory drifted: "
        f"unmapped={sorted(carriers - covered)}, "
        f"stale={sorted(covered - carriers)}. "
        "Add a source snippet to REDIRECT_SOURCES (or a justified entry to "
        "REDIRECT_EXEMPT) for any new redirect-carrying node."
    )


def test_break_continue_redirects_truly_unreachable():
    """Pin the justification for REDIRECT_EXEMPT."""
    for src, cls in [('break >/etc/passwd', BreakStatement),
                     ('continue >/etc/passwd', ContinueStatement)]:
        nodes = _find_nodes(_ast(f'while true; do {src}; done'), cls)
        assert nodes and all(not n.redirects for n in nodes), (
            f"{cls.__name__} now carries parsed redirects - remove it from "
            "REDIRECT_EXEMPT and add it to REDIRECT_SOURCES"
        )


@pytest.mark.parametrize("node_name,src", sorted(REDIRECT_SOURCES.items()))
def test_parse_attaches_redirect(node_name, src):
    """Sanity: each snippet really produces that node with a redirect."""
    cls = getattr(ast_mod, node_name)
    nodes = _find_nodes(_ast(src), cls)
    assert any(n.redirects for n in nodes), (
        f"{src!r} did not attach a redirect to {node_name}"
    )


@pytest.mark.parametrize("node_name,src", sorted(REDIRECT_SOURCES.items()))
def test_security_flags_redirect_on_carrier(node_name, src):
    v = SecurityVisitor()
    v.visit(_ast(src))
    assert any(i.issue_type == 'SENSITIVE_FILE_WRITE' for i in v.issues), (
        f"SecurityVisitor missed the /etc/passwd write attached to {node_name}"
    )


@pytest.mark.parametrize("node_name,src", sorted(REDIRECT_SOURCES.items()))
def test_formatter_emits_redirect_on_carrier(node_name, src):
    out = FormatterVisitor().visit(_ast(src))
    assert '# Unknown node' not in out
    assert '/etc/passwd' in out, (
        f"FormatterVisitor dropped the redirect attached to {node_name}: {out!r}"
    )
    # And the formatted text reparses with the redirect still attached.
    cls = getattr(ast_mod, node_name)
    nodes = _find_nodes(_ast(out), cls)
    assert any(n.redirects for n in nodes), (
        f"reparsing formatter output lost the redirect on {node_name}: {out!r}"
    )


@pytest.mark.parametrize("node_name,src", sorted(REDIRECT_SOURCES.items()))
def test_metrics_counts_redirect_on_carrier(node_name, src):
    v = MetricsVisitor()
    v.visit(_ast(src))
    assert v.metrics.total_redirections >= 1, (
        f"MetricsVisitor did not count the redirect attached to {node_name}"
    )


# ---------------------------------------------------------------------------
# Formatter round-trips for previously-missing nodes
# ---------------------------------------------------------------------------

def _round_trip(src):
    """format(parse(src)) must reparse, and reformat to the same text."""
    once = FormatterVisitor().visit(_ast(src))
    assert '# Unknown node' not in once
    reparsed = _ast(once)  # must not raise
    twice = FormatterVisitor().visit(reparsed)
    assert twice == once, (
        f"formatter output is not a fixpoint for {src!r}:\n"
        f"--- first ---\n{once}\n--- second ---\n{twice}"
    )
    return reparsed


@pytest.mark.parametrize("src,node_name", [
    # UntilLoop: used to fall through to '# Unknown node: UntilLoop'.
    ('until false; do echo hi; done', 'UntilLoop'),
    ('until false; do echo hi; done >/tmp/x', 'UntilLoop'),
    # FunctionDef: formatter used to drop the definition's redirects.
    ('f() { :; } >/tmp/x', 'FunctionDef'),
    # ArithmeticEvaluation: formatter used to drop its redirects.
    ('((1 + 2)) >/tmp/x', 'ArithmeticEvaluation'),
    # Background and/or list: formatter used to drop the trailing '&'.
    ('echo a && echo b &', 'AndOrList'),
])
def test_round_trip_previously_missing(src, node_name):
    reparsed = _round_trip(src)
    cls = getattr(ast_mod, node_name)
    assert _find_nodes(reparsed, cls), (
        f"round-tripped output for {src!r} no longer contains {node_name}"
    )


def test_andor_background_round_trip_preserves_flag():
    reparsed = _round_trip('echo a && echo b &')
    from psh.ast_nodes import AndOrList
    assert any(n.background for n in _find_nodes(reparsed, AndOrList))


@pytest.mark.parametrize("src", sorted(REDIRECT_SOURCES.values()))
def test_round_trip_all_redirect_carriers(src):
    _round_trip(src)


# ---------------------------------------------------------------------------
# The original repro defects, pinned
# ---------------------------------------------------------------------------

def test_until_loop_formats_as_shell_not_unknown_node():
    out = FormatterVisitor().visit(_ast('until false; do echo hi; done'))
    assert 'Unknown node' not in out
    assert out.splitlines()[0] == 'until'
    assert out.splitlines()[-1] == 'done'


def test_security_catches_while_loop_etc_passwd_write():
    v = SecurityVisitor()
    v.visit(_ast('while true; do :; done >/etc/passwd'))
    assert any(i.issue_type == 'SENSITIVE_FILE_WRITE' for i in v.issues)
    assert 'No security issues found' not in v.get_summary()


def test_validator_traverses_until_loop_body():
    """until-loop bodies used to be skipped entirely by the validator."""
    v = ValidatorVisitor()
    v.visit(_ast('until false; do break 5; done'))
    assert any('loop count 5 exceeds' in i.message for i in v.issues)


def test_validator_traverses_group_bodies():
    """subshell/brace group bodies used to be skipped by the validator."""
    for src in ('( break )', '{ break; }'):
        v = ValidatorVisitor()
        v.visit(_ast(src))
        assert any('break' in i.message for i in v.issues), src
