"""Drift-lock for the declared AST child schema (campaign S5).

``walk_ast`` reads a DECLARED ``AstChildSchema`` (psh/visitor/traversal.py). This
guard walks every concrete ``psh.ast_nodes`` node class and, by reflecting over
each field's RESOLVED type annotation, re-derives the child-bearing fields and
their container shapes. It fails if the declared schema is missing a child-bearing
field, declares a stale one, or gets a shape wrong — so a new AST field, or a
change to an existing one, cannot silently escape the traversal. Synthetic
offenders prove the mechanism fires.

It also pins:
- the second structural walker (``parser.visualization.node_fields``) agrees with
  the schema on which fields are AST children (no drifting second authority);
- the S3 syntax templates remain non-``ASTNode`` carriers, so ``walk_ast`` never
  descends into them (the S5 template-descent decision, enforced by construction);
- **campaign Q2 (§13, "visitor recursion outside walk_ast"):** no production
  module re-implements generic AST-tree descent by reflecting over a node's
  dataclass fields — the anti-pattern #20 named (the elif-skip class of bug). The
  reflection primitives (``dataclasses.fields`` / ``dataclasses.is_dataclass`` /
  ``__dataclass_fields__`` / ``vars`` / ``.__dict__``) used to walk a node's
  fields are confined to a justified, shrink-only allowlist; a synthetic offender
  proves the scan bites.
"""
import ast as _ast
import dataclasses
import inspect
import pathlib
import types
import typing

import pytest

import psh.ast_nodes as ast_mod
from psh.ast_nodes import ASTNode
from psh.visitor.traversal import AstChildSchema, ChildShape

# The flat psh.ast_nodes namespace, for resolving ForwardRef('Word') etc.
_NS = {name: getattr(ast_mod, name) for name in dir(ast_mod)}


def _resolve(t):
    """Resolve a ForwardRef / str annotation to its class via the ast_nodes ns."""
    if isinstance(t, typing.ForwardRef):
        return _NS.get(t.__forward_arg__)
    if isinstance(t, str):
        return _NS.get(t)
    return t


def _is_astnode_type(t) -> bool:
    t = _resolve(t)
    return isinstance(t, type) and issubclass(t, ASTNode)


def reflect_child_shape(ftype):
    """The child container shape a field's resolved annotation implies, or None.

    NODE for an (optional) ASTNode, NODE_LIST for List[ASTNode], NODE_TUPLE_LIST
    for List[Tuple[..., ASTNode, ...]]; None for everything else — crucially,
    the S3 template carriers resolve to non-ASTNode classes and therefore return
    None (they are never children).
    """
    origin = typing.get_origin(ftype)
    if origin is typing.Union or isinstance(ftype, types.UnionType):
        for arg in typing.get_args(ftype):
            if arg is type(None):
                continue
            shape = reflect_child_shape(arg)
            if shape is not None:
                return shape
        return None
    if origin is list:
        args = typing.get_args(ftype)
        arg = args[0] if args else None
        if _is_astnode_type(arg):
            return ChildShape.NODE_LIST
        if typing.get_origin(arg) is tuple:
            if any(_is_astnode_type(x) for x in typing.get_args(arg)):
                return ChildShape.NODE_TUPLE_LIST
        return None
    if _is_astnode_type(ftype):
        return ChildShape.NODE
    return None


def reflect_child_fields(cls):
    """Child-bearing fields of *cls*, as an ordered tuple of (name, shape)."""
    out = []
    for f in dataclasses.fields(cls):
        shape = reflect_child_shape(f.type)
        if shape is not None:
            out.append((f.name, shape))
    return tuple(out)


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


def test_every_concrete_node_is_in_the_schema():
    """The schema must cover every concrete node class (no silent omission)."""
    missing = [c.__name__ for c in CONCRETE if c.__name__ not in AstChildSchema]
    assert not missing, f"AstChildSchema omits concrete node classes: {missing}"


def test_no_stale_schema_keys():
    """Every schema key must name a real concrete node class."""
    real = {c.__name__ for c in CONCRETE}
    stale = sorted(set(AstChildSchema) - real)
    assert not stale, f"AstChildSchema has stale keys (no such node): {stale}"


@pytest.mark.parametrize("cls", CONCRETE, ids=lambda c: c.__name__)
def test_schema_matches_reflection_for_every_node(cls):
    """DRIFT-LOCK: declared child fields+shapes == reflection over annotations.

    A new child-bearing field, a removed one, or a wrong container shape fails
    here — the schema cannot drift from the actual node definitions.
    """
    declared = AstChildSchema.get(cls.__name__, ())
    reflected = reflect_child_fields(cls)
    assert declared == reflected, (
        f"{cls.__name__}: schema {declared} != reflection {reflected}. "
        "Update AstChildSchema (in psh/visitor/traversal.py) to match the node's "
        "child-bearing fields."
    )


# --- Synthetic offenders: prove the drift-lock mechanism fires ---------------

@dataclasses.dataclass
class _OffenderWithUndeclaredChild(ASTNode):
    """A node with an ASTNode child field that no schema declares."""
    child: ASTNode = None  # type: ignore[assignment]
    name: str = "x"


def test_offender_undeclared_child_field_is_detected():
    """An undeclared child-bearing field is caught by the reflection oracle."""
    reflected = reflect_child_fields(_OffenderWithUndeclaredChild)
    assert ('child', ChildShape.NODE) in reflected, (
        "reflection must flag an ASTNode-typed field as a child"
    )
    # And it is genuinely absent from the declared schema, so the drift-lock
    # comparison (declared != reflected) would fire for such a node.
    declared = AstChildSchema.get('_OffenderWithUndeclaredChild', ())
    assert declared != reflected


@dataclasses.dataclass
class _OffenderWithTupleListChild(ASTNode):
    """A node with a List[Tuple[ASTNode, ASTNode]] field (the elif shape)."""
    branches: typing.List[typing.Tuple[ASTNode, ASTNode]] = dataclasses.field(
        default_factory=list)


def test_offender_tuple_list_child_shape_is_detected():
    """The tuple-in-list shape is recognized (the shape reflection historically missed)."""
    reflected = reflect_child_fields(_OffenderWithTupleListChild)
    assert ('branches', ChildShape.NODE_TUPLE_LIST) in reflected


def test_offender_stale_declaration_is_detected():
    """A schema entry naming a field the node lacks fails the match check."""
    from psh.ast_nodes import Pipeline
    stale = {'Pipeline': (('commands', ChildShape.NODE_LIST),
                          ('ghost', ChildShape.NODE))}
    reflected = reflect_child_fields(Pipeline)
    assert stale['Pipeline'] != reflected, (
        "a stale extra declared field must differ from reflection"
    )


# --- node_fields agreement (no drifting second authority) --------------------

def test_node_fields_agrees_with_schema_on_ast_children():
    """The visualization walker (node_fields) must agree with the schema on which
    fields are structural AST children — it is not a second authority."""
    from psh.parser.visualization.node_fields import node_fields
    for cls in CONCRETE:
        declared_names = {name for name, _ in AstChildSchema[cls.__name__]}
        # Build a representative instance whose every declared child field holds
        # a real ASTNode (scalar), an ASTNode list, or an ASTNode tuple-list, so
        # node_fields (which drops empty/None) surfaces exactly the child fields.
        instance = _build_populated(cls)
        if instance is None:
            continue
        surfaced_children = set()
        for name, value in node_fields(instance, include_empty=True):
            if _field_holds_astnode(value):
                surfaced_children.add(name)
        assert surfaced_children == declared_names, (
            f"{cls.__name__}: node_fields AST-child fields {surfaced_children} "
            f"!= schema {declared_names}"
        )


def _field_holds_astnode(value) -> bool:
    if isinstance(value, ASTNode):
        return True
    if isinstance(value, list):
        for item in value:
            if isinstance(item, ASTNode):
                return True
            if isinstance(item, tuple) and any(isinstance(x, ASTNode) for x in item):
                return True
    return False


def _build_populated(cls):
    """A cls instance with every declared child field populated by sentinels."""
    from psh.ast_nodes import Redirect, Word
    sentinel_word = Word(parts=[])
    sentinel_redirect = Redirect(type='>', target='x')

    kwargs = {}
    for f in dataclasses.fields(cls):
        decl = dict(AstChildSchema[cls.__name__])
        if f.name in decl:
            shape = decl[f.name]
            child = sentinel_redirect if f.name == 'redirects' else sentinel_word
            if shape is ChildShape.NODE:
                kwargs[f.name] = child
            elif shape is ChildShape.NODE_LIST:
                kwargs[f.name] = [child]
            else:  # NODE_TUPLE_LIST
                kwargs[f.name] = [(child, child)]
        elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:  # type: ignore[misc]
            # A required non-child field: give it a benign value by type name.
            kwargs[f.name] = _benign_value(f)
    try:
        return cls(**kwargs)
    except Exception:  # noqa: BLE001
        return None


def _benign_value(f):
    t = f.type
    if t in (str, 'str') or getattr(t, '__name__', '') == 'str':
        return ''
    if t in (bool, 'bool'):
        return False
    if t in (int, 'int'):
        return 0
    return ''


# --- S5 template-descent decision (templates non-ASTNode, never walked) ------

def test_syntax_templates_are_not_astnodes():
    """S3 syntax templates are NON-ASTNode carriers, so walk_ast never descends
    into them (the S5 template-descent decision, enforced by construction). If a
    template were made an ASTNode, the schema-vs-reflection drift-lock above
    would immediately require its carrier fields to be declared children."""
    from psh.ast_nodes import (
        ArithmeticTemplate,
        NestedSub,
        SubscriptSpec,
        SyntaxTemplate,
        WordTemplate,
    )
    for tmpl in (SyntaxTemplate, WordTemplate, ArithmeticTemplate,
                 SubscriptSpec, NestedSub):
        assert not (isinstance(tmpl, type) and issubclass(tmpl, ASTNode)), (
            f"{tmpl.__name__} must not be an ASTNode subclass (S5 decision)"
        )


def test_no_template_carrier_field_is_a_declared_child():
    """No node's template carrier (word_template / arith_template / *_template /
    subscript_spec) is declared as a structural child."""
    template_fields = {
        'word_template', 'subscript_spec', 'arith_template',
        'init_template', 'condition_template', 'update_template',
    }
    for name, fields in AstChildSchema.items():
        declared = {fname for fname, _ in fields}
        leaked = declared & template_fields
        assert not leaked, f"{name} declares template field(s) as children: {leaked}"


# === Q2 family 8: no generic AST-reflection traversal outside walk_ast ========
#
# ``walk_ast`` (reading ``AstChildSchema``) is the SOLE structural AST traversal.
# The anti-pattern is a SECOND traversal engine: code that descends an AST tree
# by reflecting over a node's dataclass fields generically (``dataclasses.fields``
# / ``__dataclass_fields__`` / ``vars`` / ``.__dict__``) and recursing — the exact
# shape whose historical instance silently skipped ``IfConditional.elif_parts``.
# This scan flags those reflection primitives in production code (``psh/**``);
# the allowlist is the small set of files that legitimately reflect, each with a
# specific reason, and it may only SHRINK.
#
# A ``visit_<Type>`` method that reads its node's OWN named fields
# (``self.visit(node.condition)``) is the normal visitor pattern, not generic
# reflection, and never matches — this scanner keys on the reflection primitives,
# not on ``self.visit`` calls.

_PSH_ROOT = pathlib.Path(__file__).resolve().parents[3] / "psh"

# file (posix-rel to psh/) -> why it legitimately reflects over node fields.
# Shrink-only: an entry that no longer reflects must be pruned
# (test_reflection_allowlist_entries_still_reflect).
_REFLECTION_ALLOWLIST = {
    "visitor/traversal.py":
        "_reflect_children is walk_ast's OWN fallback, reached only by "
        "UNREGISTERED synthetic node classes (tests); the drift-lock above "
        "proves every production node is in the schema, so production traversal "
        "never uses it — it is inside the one engine, not a second one",
    "parser/visualization/node_fields.py":
        "the single sanctioned second walker: it must surface SCALAR fields too "
        "(for rendering), so it cannot be walk_ast; it is drift-locked to AGREE "
        "with the schema on child-bearing fields "
        "(test_node_fields_agrees_with_schema_on_ast_children)",
    "visitor/debug_ast_visitor.py":
        "generic_visit dumps a node's scalar __dict__ items for a one-line debug "
        "line; it does NOT recurse into children (not a traversal engine)",
}

# The reflection primitives that signal generic dataclass-field traversal.
_REFLECT_ATTRS = {"fields", "is_dataclass"}          # <dataclasses-alias>.<attr>()
_REFLECT_DUNDER = {"__dataclass_fields__", "__dict__"}


def _dataclasses_import_bindings(tree):
    """Resolve how *tree* refers to the dataclasses reflection primitives.

    Returns (module_aliases, bare_names): ``module_aliases`` is every name bound
    to the ``dataclasses`` MODULE (``import dataclasses`` -> {'dataclasses'};
    ``import dataclasses as _dc`` -> {'_dc'}); ``bare_names`` is every local name
    bound directly to ``fields``/``is_dataclass`` (``from dataclasses import
    fields as F`` -> {'F', ...}). This closes the aliased-import evasion —
    ``import dataclasses as _dc; _dc.fields(node)`` is caught."""
    module_aliases = set()
    bare_names = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                if alias.name == "dataclasses":
                    module_aliases.add(alias.asname or "dataclasses")
        elif isinstance(node, _ast.ImportFrom) and node.module == "dataclasses":
            for alias in node.names:
                if alias.name in _REFLECT_ATTRS:
                    bare_names.add(alias.asname or alias.name)
    return module_aliases, bare_names


def _find_reflection_primitives(src: str):
    """Return [(lineno, primitive)] generic field-reflection primitives in *src*.

    Matches ``<dataclasses-alias>.fields``/``.is_dataclass`` (the module name OR
    any ``import dataclasses as X`` alias), the bare imported name (``from
    dataclasses import fields [as F]``), ``vars(...)``, and
    ``<expr>.__dataclass_fields__`` / ``<expr>.__dict__`` (attribute OR the
    getattr-string form). Comments and docstrings that merely name these do NOT
    match (this is an AST scan)."""
    tree = _ast.parse(src)
    module_aliases, bare_names = _dataclasses_import_bindings(tree)
    hits = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Attribute):
            if node.attr in _REFLECT_DUNDER:
                hits.append((node.lineno, node.attr))
            elif (node.attr in _REFLECT_ATTRS
                  and isinstance(node.value, _ast.Name)
                  and node.value.id in module_aliases):
                hits.append((node.lineno, f"{node.value.id}.{node.attr}"))
        elif isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name):
            if node.func.id == "vars":
                hits.append((node.lineno, "vars()"))
            elif node.func.id in bare_names:
                hits.append((node.lineno, node.func.id))
        # getattr(node, "__dataclass_fields__"/"__dict__", ...) — the string form
        # (also the getattr-smuggling evasion of the attribute-access shapes).
        elif (isinstance(node, _ast.Constant) and isinstance(node.value, str)
              and node.value in _REFLECT_DUNDER):
            hits.append((node.lineno, node.value))
    return hits


def _scan_production_reflection():
    """{rel_posix: [(lineno, primitive)]} for every production psh/ module."""
    out = {}
    for path in sorted(_PSH_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(_PSH_ROOT).as_posix()
        hits = _find_reflection_primitives(path.read_text())
        if hits:
            out[rel] = hits
    return out


def test_no_generic_reflection_traversal_outside_walk_ast():
    """No production module reflects over dataclass fields for AST descent
    except the justified, sanctioned reflectors."""
    found = _scan_production_reflection()
    offenders = {rel: hits for rel, hits in found.items()
                 if rel not in _REFLECTION_ALLOWLIST}
    assert not offenders, (
        "generic dataclass-field reflection outside walk_ast — route AST descent "
        "through visitor.traversal.walk_ast / iter_child_nodes (the ONE schema-"
        "declared traversal), or, if this is a justified non-AST reflection, add "
        "it to _REFLECTION_ALLOWLIST with a specific reason:\n  "
        + "\n  ".join(f"{rel}: {hits}" for rel, hits in sorted(offenders.items())))


def test_reflection_allowlist_entries_still_reflect():
    """Shrink-only: an allowlisted file that no longer reflects must be pruned."""
    found = _scan_production_reflection()
    for rel in _REFLECTION_ALLOWLIST:
        assert (_PSH_ROOT / rel).exists(), f"allowlisted file missing: {rel}"
        assert rel in found, (
            f"{rel} no longer reflects over node fields — remove its "
            "_REFLECTION_ALLOWLIST entry (the ratchet only shrinks)")


def test_every_reflection_allowlist_entry_has_justification():
    for rel, reason in _REFLECTION_ALLOWLIST.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 30, (
            f"_REFLECTION_ALLOWLIST[{rel!r}] needs a specific justification")


def test_offender_generic_reflection_recursion_is_flagged():
    """SYNTHETIC OFFENDER: a private walker re-implementing generic AST descent
    by reflecting over dataclass fields is detected."""
    offender = (
        "import dataclasses\n"
        "def _offset(node, delta):\n"
        "    node.line += delta\n"
        "    if dataclasses.is_dataclass(node):\n"
        "        for f in dataclasses.fields(node):\n"
        "            _offset(getattr(node, f.name), delta)\n"
    )
    prims = {p for _, p in _find_reflection_primitives(offender)}
    assert {"dataclasses.is_dataclass", "dataclasses.fields"} <= prims


def test_offender_dunder_reflection_is_flagged():
    """SYNTHETIC OFFENDER: descending via __dataclass_fields__ / __dict__ / vars
    is detected (evasion shapes that avoid the ``dataclasses`` module name)."""
    off1 = "def w(n):\n    for k in n.__dataclass_fields__:\n        w(getattr(n, k))\n"
    off2 = "def w(n):\n    for k, v in n.__dict__.items():\n        w(v)\n"
    off3 = "def w(n):\n    for k, v in vars(n).items():\n        w(v)\n"
    assert any(p == "__dataclass_fields__" for _, p in _find_reflection_primitives(off1))
    assert any(p == "__dict__" for _, p in _find_reflection_primitives(off2))
    assert any(p == "vars()" for _, p in _find_reflection_primitives(off3))


def test_offender_aliased_dataclasses_import_is_flagged():
    """SYNTHETIC OFFENDER (aliased-import evasion): ``import dataclasses as _dc;
    _dc.fields(...)`` and ``from dataclasses import fields as F; F(...)`` must be
    caught — the detector resolves the dataclasses import bindings, so an alias
    cannot smuggle a second traversal engine past it."""
    aliased_mod = (
        "import dataclasses as _dc\n"
        "def w(n):\n"
        "    for f in _dc.fields(n):\n"
        "        w(getattr(n, f.name))\n"
    )
    prims = {p for _, p in _find_reflection_primitives(aliased_mod)}
    assert "_dc.fields" in prims, prims

    aliased_from = (
        "from dataclasses import fields as F, is_dataclass as ID\n"
        "def w(n):\n"
        "    if ID(n):\n"
        "        for f in F(n):\n"
        "            w(getattr(n, f.name))\n"
    )
    prims = {p for _, p in _find_reflection_primitives(aliased_from)}
    assert {"F", "ID"} <= prims, prims

    # And a bare `fields` that is NOT imported from dataclasses is NOT flagged
    # (no false positive on an unrelated local `fields` helper).
    unrelated = "def fields(n):\n    return n.cols\ndef g(n):\n    return fields(n)\n"
    assert all(p not in ("fields",) for _, p in _find_reflection_primitives(unrelated))


def test_scanner_ignores_named_field_visit_and_prose():
    """A normal visit_<Type> reading its node's OWN fields, and prose that merely
    names the primitives, do not match (no false positives)."""
    clean = (
        "def visit_IfConditional(self, node):\n"
        "    '''Visits node.condition and dataclasses.fields (in prose only).'''\n"
        "    # we no longer use vars(node) or node.__dict__ here\n"
        "    self.visit(node.condition)\n"
        "    for c, b in node.elif_parts:\n"
        "        self.visit(c)\n"
    )
    assert _find_reflection_primitives(clean) == []


def test_source_processor_offset_uses_walk_ast_not_reflection():
    """Campaign Q2 carry: source_processor._offset_line_numbers was migrated off
    generic field reflection onto walk_ast — it must no longer reflect."""
    found = _scan_production_reflection()
    assert "scripting/source_processor.py" not in found, (
        "source_processor.py reintroduced generic field reflection — "
        "_offset_line_numbers must descend via walk_ast")
    src = (_PSH_ROOT / "scripting" / "source_processor.py").read_text()
    assert "walk_ast" in src, "source_processor must import/use walk_ast"
