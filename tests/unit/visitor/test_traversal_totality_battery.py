"""Generated traversal-totality battery + anti-bypass guard (remediation 2.1).

Reappraisal #22 HIGH-2: the production analysis visitors hand-maintained their
child traversal and silently skipped executable positions (redirect-only
commands, redirect targets, for/case subject words, template subs). The fix
made child enumeration framework-owned (``AstChildSchema`` read by
``TotalTraversalVisitor``'s post-handler sweep). This module is the executable
guard that the fix STAYS total:

1. **Generated sentinel battery** — for every concrete AST node class, every
   declared child edge, and every production analysis visitor, a generated
   test builds the parent node with sentinel children planted at that edge and
   asserts the visitor's dispatch reaches every sentinel. The node inventory
   and the edge list come from ``psh.ast_nodes`` reflection and the schema —
   never a hand list — so a new node/field gets battery rows automatically
   (and the schema drift-lock in ``test_ast_child_schema_guard.py`` fails
   first if the field is not declared at all).
2. **Visitor roster guard** — every ``ASTVisitor`` subclass in the production
   tree must be classified: either a migrated analysis visitor (subclasses
   ``TotalTraversalVisitor``, never overrides ``visit``, declares no
   unaudited prune) or a named exemption with a rationale (rendering /
   evaluation visitors, where traversal is the computation itself). A new
   unclassified visitor fails here.
3. **Synthetic offenders** — a visitor that overrides ``visit()``, declares
   an unaudited prune, or relies on pruning to skip an edge turns the guard
   RED; proven below.
"""

import dataclasses
import importlib
import inspect
import pkgutil
import typing

import pytest

import psh
import psh.ast_nodes as ast_mod
from psh.ast_nodes import ASTNode, Program, SyntaxTemplate
from psh.visitor import (
    EnhancedValidatorVisitor,
    LinterVisitor,
    MetricsVisitor,
    SecurityVisitor,
    ValidatorVisitor,
)
from psh.visitor.base import ASTVisitor
from psh.visitor.traversal import AstChildSchema, ChildShape, TotalTraversalVisitor

# ---------------------------------------------------------------------------
# Rosters (the classification the roster guard enforces)
# ---------------------------------------------------------------------------

# The production analysis visitors: framework-owned traversal, battery-covered.
ANALYSIS_VISITORS = (
    ValidatorVisitor,
    EnhancedValidatorVisitor,
    SecurityVisitor,
    MetricsVisitor,
    LinterVisitor,
)

# Named exemptions from the framework sweep, each with its rationale. These are
# visitors where traversal IS the computation, so a post-handler auto-descent
# would be wrong — their totality is enforced by other guards (noted per entry).
EXEMPT_VISITORS = {
    "ExecutorVisitor":
        "traversal is EVALUATION: which children run, and in what order, is "
        "shell semantics (an if visits one branch); totality = explicit "
        "visit_X for every executable node (test_ast_coverage_matrix.py)",
    "FormatterVisitor":
        "traversal is the RENDERING: children are formatted in syntax "
        "positions; totality = explicit visit_X for every concrete node plus "
        "reparse round-trips (test_ast_coverage_matrix.py)",
    "DebugASTVisitor":
        "debug rendering (--debug-ast), not an analysis mode; major nodes "
        "have explicit methods, fallback dumps fields",
    "ASTPrettyPrinter":
        "visualization renderer driven by node_fields, which is drift-locked "
        "to agree with the schema (test_ast_child_schema_guard.py)",
    "ASTDotGenerator":
        "visualization renderer driven by node_fields (same drift-lock)",
}

# Audited prunes: (VisitorClassName, NodeClassName, field). EMPTY — no
# production analysis visitor skips any declared edge. Growing this set
# requires editing both the visitor's PRUNED_EDGES and this registry (with a
# reason), which is the explicit, named decision the framework demands.
AUDITED_PRUNES: dict = {}


# ---------------------------------------------------------------------------
# Mechanical node construction (no hand lists)
# ---------------------------------------------------------------------------

_NS = {name: getattr(ast_mod, name) for name in dir(ast_mod)}


def _resolve(t):
    if isinstance(t, typing.ForwardRef):
        return _NS.get(t.__forward_arg__)
    if isinstance(t, str):
        return _NS.get(t)
    return t


def _is_astnode_type(t) -> bool:
    t = _resolve(t)
    return isinstance(t, type) and issubclass(t, ASTNode)


def _concrete_node_classes():
    seen, out = set(), []
    for obj in vars(ast_mod).values():
        if (inspect.isclass(obj) and issubclass(obj, ASTNode)
                and obj.__module__ == 'psh.ast_nodes'
                and dataclasses.is_dataclass(obj) and obj not in seen):
            seen.add(obj)
            out.append(obj)
    return sorted(out, key=lambda c: c.__name__)


CONCRETE = _concrete_node_classes()


def _unwrap_optional(t):
    origin = typing.get_origin(t)
    if origin is typing.Union:
        args = [a for a in typing.get_args(t) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return t


def _benign_scalar(t):
    """A benign value for a non-node field annotation, or MISSING sentinel."""
    t = _resolve(_unwrap_optional(t))
    if t is str:
        return 'x'
    if t is int:
        return 0
    if t is bool:
        return False
    origin = typing.get_origin(t)
    if origin is list:
        return []
    if origin is tuple:
        return ()
    return None


def _minimal_instance(cls):
    """Build a minimal instance of concrete node class *cls* mechanically.

    Required fields are filled from their annotations: scalars get benign
    values, node-typed fields get a minimal instance of (a deterministic
    concrete subclass of) the annotated type. No per-class special cases — a
    hand list here would be the disease this battery cures.
    """
    kwargs = {}
    for f in dataclasses.fields(cls):
        if (f.default is not dataclasses.MISSING
                or f.default_factory is not dataclasses.MISSING):  # type: ignore[misc]
            continue
        target = _resolve(_unwrap_optional(f.type))
        if isinstance(target, type) and issubclass(target, ASTNode):
            kwargs[f.name] = _instance_of(target)
        else:
            kwargs[f.name] = _benign_scalar(f.type)
    return cls(**kwargs)


def _instance_of(base):
    """A minimal instance of *base* or (if abstract) of its first concrete
    subclass in name order — deterministic, no hand list."""
    if dataclasses.is_dataclass(base) and base in CONCRETE:
        return _minimal_instance(base)
    for cls in CONCRETE:
        if issubclass(cls, base):
            return _minimal_instance(cls)
    raise AssertionError(f"no concrete node class implements {base!r}")


def _template_with_sentinel(field_type):
    """An instance of the annotated SyntaxTemplate subclass carrying one
    parsed command-substitution sub; returns (template, sentinel_node)."""
    from psh.ast_nodes import CommandSubstitution, NestedSub
    tmpl_cls = _resolve(_unwrap_optional(field_type))
    assert isinstance(tmpl_cls, type) and issubclass(tmpl_cls, SyntaxTemplate)
    sentinel = CommandSubstitution(program=Program(), source='sentinel')
    text = '$(sentinel)'
    return tmpl_cls(text=text, subs=(NestedSub(sentinel, 0, len(text)),)), sentinel


def _plant_sentinels(node_cls, field_name, shape):
    """Build a *node_cls* instance with sentinel children planted at
    *field_name*; returns (parent, [sentinel nodes])."""
    parent = _minimal_instance(node_cls)
    ftype = next(f.type for f in dataclasses.fields(node_cls)
                 if f.name == field_name)
    inner = _resolve(_unwrap_optional(ftype))
    if shape is ChildShape.NODE:
        sentinel = _instance_of(inner)
        object.__setattr__(parent, field_name, sentinel)
        return parent, [sentinel]
    if shape is ChildShape.NODE_LIST:
        elem = _resolve(typing.get_args(inner)[0]) if typing.get_args(inner) else ASTNode
        sentinel = _instance_of(elem)
        object.__setattr__(parent, field_name, [sentinel])
        return parent, [sentinel]
    if shape is ChildShape.NODE_TUPLE_LIST:
        tup = typing.get_args(inner)[0] if typing.get_args(inner) else None
        elems = [_instance_of(_resolve(a)) for a in typing.get_args(tup)]
        object.__setattr__(parent, field_name, [tuple(elems)])
        return parent, [e for e in elems if isinstance(e, ASTNode)]
    # TEMPLATE_SUBS
    template, sentinel = _template_with_sentinel(ftype)
    object.__setattr__(parent, field_name, template)
    return parent, [sentinel]


def _dispatched_ids(visitor, root):
    """Every node id dispatched through *visitor*.visit during a traversal of
    *root* — instrumented on the PRODUCTION visitor instance (the sweep and
    every handler route through self.visit, which resolves to the wrapper)."""
    seen = set()
    orig = visitor.visit

    def _recording_visit(n):
        seen.add(id(n))
        return orig(n)

    visitor.visit = _recording_visit  # type: ignore[method-assign]
    _recording_visit(root)
    return seen


def _dispatch_counts(visitor, root):
    """id -> dispatch count through *visitor*.visit during a traversal of
    *root*. Counts, not a set: the battery asserts EXACTLY-ONCE, not mere
    reach — a reach-only assertion stayed green over the B1 double-traversal
    bug (2^N re-analysis under nested cases)."""
    from collections import Counter
    counts: Counter = Counter()
    orig = visitor.visit

    def _recording_visit(n):
        counts[id(n)] += 1
        return orig(n)

    visitor.visit = _recording_visit  # type: ignore[method-assign]
    _recording_visit(root)
    return counts


# Every (node class, edge) pair, derived from the schema — which the drift-lock
# proves equal to reflection over the real node annotations.
EDGES = [(cls, name, shape)
         for cls in CONCRETE
         for name, shape in AstChildSchema[cls.__name__]]


def test_edge_inventory_is_alive():
    """The generated inventory keeps covering the known positions (a discovery
    regression cannot silently empty the battery)."""
    named = {(cls.__name__, name) for cls, name, _ in EDGES}
    for expected in [
        ('SimpleCommand', 'redirects'),          # redirect-only command
        ('Redirect', 'target_word'),             # redirect target
        ('ForLoop', 'item_words'),               # for subject words
        ('CaseConditional', 'subject_word'),     # case subject word
        ('IfConditional', 'elif_parts'),         # the historical elif skip
        ('ParameterExpansion', 'word_template'),  # ${x:-$(...)} operand subs
        ('ArithmeticEvaluation', 'arith_template'),
        ('ArrayElementAssignment', 'index_spec'),  # a[$(...)]=v subscript subs
        ('CommandSubstitution', 'program'),
    ]:
        assert expected in named, f"battery lost edge {expected}"
    assert len(EDGES) >= 45


@pytest.mark.parametrize(
    "node_cls,field_name,shape", EDGES,
    ids=[f"{c.__name__}.{n}" for c, n, _ in EDGES])
def test_every_visitor_reaches_every_child_edge_exactly_once(
        node_cls, field_name, shape):
    """THE BATTERY: sentinels planted at this edge are dispatched by every
    production analysis visitor EXACTLY ONCE — a miss (skipped subtree) and a
    multiple (double analysis, the B1 exponential class) both fail."""
    for visitor_cls in ANALYSIS_VISITORS:
        parent, sentinels = _plant_sentinels(node_cls, field_name, shape)
        assert sentinels, f"builder planted nothing at {node_cls.__name__}.{field_name}"
        counts = _dispatch_counts(visitor_cls(), parent)
        bad = {counts[id(s)] for s in sentinels if counts[id(s)] != 1}
        assert not bad, (
            f"{visitor_cls.__name__} dispatched the sentinel child at "
            f"{node_cls.__name__}.{field_name} ({shape.name}) with "
            f"multiplicities {sorted(bad)} (want exactly 1)"
        )
        # And NO node anywhere in the built tree is dispatched twice — this
        # is what catches a grandchild-dispatch frame bug (B1), where the
        # doubled node is a sentinel's OWN child rather than the sentinel.
        dupes = sorted(c for c in counts.values() if c > 1)
        assert not dupes, (
            f"{visitor_cls.__name__} double-dispatched {len(dupes)} node(s) "
            f"under {node_cls.__name__}.{field_name}: multiplicities {dupes[:5]}"
        )


# ---------------------------------------------------------------------------
# Visitor roster guard (classification is total and mechanically discovered)
# ---------------------------------------------------------------------------

def _all_production_visitor_classes():
    """Every ASTVisitor subclass defined in the psh package, discovered by
    importing every psh module (no hand-maintained module list)."""
    for modinfo in pkgutil.walk_packages(psh.__path__, 'psh.'):
        if modinfo.name.endswith('__main__'):
            continue
        importlib.import_module(modinfo.name)

    out = []
    pending = list(ASTVisitor.__subclasses__())
    seen = set()
    while pending:
        cls = pending.pop()
        if cls in seen:
            continue
        seen.add(cls)
        pending.extend(cls.__subclasses__())
        if cls.__module__.startswith('psh.'):
            out.append(cls)
    return sorted(out, key=lambda c: c.__name__)


def test_every_production_visitor_is_classified():
    """A new ASTVisitor subclass in psh/ must be rostered: either a migrated
    analysis visitor or a named exemption with a rationale."""
    analysis_names = {c.__name__ for c in ANALYSIS_VISITORS}
    for cls in _all_production_visitor_classes():
        if cls is TotalTraversalVisitor:
            continue  # the framework base itself
        name = cls.__name__
        if issubclass(cls, TotalTraversalVisitor):
            assert name in analysis_names, (
                f"{name} subclasses TotalTraversalVisitor but is not in the "
                "battery roster (ANALYSIS_VISITORS) — add it so the sentinel "
                "battery covers it"
            )
        else:
            assert name in EXEMPT_VISITORS, (
                f"{name} is an unclassified production visitor: migrate it "
                "through TotalTraversalVisitor (and add to ANALYSIS_VISITORS) "
                "or add a justified EXEMPT_VISITORS entry"
            )


def test_exemption_roster_has_no_stale_entries_and_real_reasons():
    live = {c.__name__ for c in _all_production_visitor_classes()}
    for name, reason in EXEMPT_VISITORS.items():
        assert name in live, f"stale exemption (no such visitor): {name}"
        assert isinstance(reason, str) and len(reason.strip()) >= 30, (
            f"EXEMPT_VISITORS[{name!r}] needs a specific rationale")


def _bypass_defects(visitor_cls):
    """The anti-bypass check for one analysis visitor class: returns a list of
    defect strings (empty = clean). Factored out so the offender tests can
    prove it fires."""
    defects = []
    for klass in visitor_cls.__mro__:
        if klass is TotalTraversalVisitor:
            break
        if 'visit' in vars(klass):
            defects.append(
                f"{visitor_cls.__name__} overrides visit() (in {klass.__name__}) "
                "— the totality sweep lives there")
    for edge in visitor_cls.PRUNED_EDGES:
        key = (visitor_cls.__name__,) + tuple(edge)
        if key not in AUDITED_PRUNES:
            defects.append(
                f"{visitor_cls.__name__} prunes {edge} without an "
                "AUDITED_PRUNES entry")
    return defects


@pytest.mark.parametrize("visitor_cls", ANALYSIS_VISITORS,
                         ids=lambda c: c.__name__)
def test_analysis_visitor_cannot_bypass_the_sweep(visitor_cls):
    """No production analysis visitor overrides visit() or prunes unaudited."""
    assert issubclass(visitor_cls, TotalTraversalVisitor)
    assert _bypass_defects(visitor_cls) == []


def test_no_production_prunes_exist():
    """Belt and braces: today every production PRUNED_EDGES is empty, and the
    audit registry is empty with it. Growing either is a two-place, reviewed
    decision."""
    for visitor_cls in ANALYSIS_VISITORS:
        assert visitor_cls.PRUNED_EDGES == frozenset(), visitor_cls
    assert AUDITED_PRUNES == {}


# ---------------------------------------------------------------------------
# Synthetic offenders: the guard turns RED
# ---------------------------------------------------------------------------

class _OffenderOverridesVisit(TotalTraversalVisitor):
    """OFFENDER: reclaims traversal by overriding visit() (no sweep)."""

    def visit(self, node):  # noqa: D102 — deliberately bypasses the framework
        method = getattr(self, f'visit_{type(node).__name__}', self.generic_visit)
        return method(node)


class _OffenderUnauditedPrune(TotalTraversalVisitor):
    """OFFENDER: prunes a declared edge with no audit entry."""

    PRUNED_EDGES = frozenset({('Redirect', 'target_word')})


def test_offender_visit_override_is_flagged():
    defects = _bypass_defects(_OffenderOverridesVisit)
    assert any('overrides visit()' in d for d in defects), defects


def test_offender_unaudited_prune_is_flagged():
    defects = _bypass_defects(_OffenderUnauditedPrune)
    assert any('without an AUDITED_PRUNES entry' in d for d in defects), defects


def test_offender_prune_really_skips_and_battery_detects_it():
    """The behavioral leg: a pruned edge's sentinel is NOT reached, i.e. the
    battery's reach assertion goes RED for a pruning offender — pruning is
    visible, never silent."""
    from psh.ast_nodes import Redirect
    parent, sentinels = _plant_sentinels(Redirect, 'target_word', ChildShape.NODE)
    seen = _dispatched_ids(_OffenderUnauditedPrune(), parent)
    assert all(id(s) not in seen for s in sentinels), (
        "prune did not actually skip — PRUNED_EDGES seam broken")
    # And the same edge under a REAL production visitor IS reached.
    parent2, sentinels2 = _plant_sentinels(Redirect, 'target_word', ChildShape.NODE)
    seen2 = _dispatched_ids(SecurityVisitor(), parent2)
    assert all(id(s) in seen2 for s in sentinels2)


def test_offender_handler_omission_is_neutralized_by_sweep():
    """The disease itself, synthesized: a handler that early-returns without
    dispatching anything STILL gets its children visited — omission is
    structurally impossible for a TotalTraversalVisitor."""
    from psh.ast_nodes import Redirect, SimpleCommand, Word

    class _ForgetfulVisitor(TotalTraversalVisitor):
        def visit_SimpleCommand(self, node):
            return  # analyzes nothing, dispatches nothing

    target = Word.from_string('t')
    node = SimpleCommand(
        redirects=[Redirect(type='>', target='t', target_word=target)])
    seen = _dispatched_ids(_ForgetfulVisitor(), node)
    assert id(node.redirects[0]) in seen
    assert id(target) in seen
