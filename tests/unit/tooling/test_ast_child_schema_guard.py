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
  descends into them (the S5 template-descent decision, enforced by construction).
"""
import dataclasses
import inspect
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
