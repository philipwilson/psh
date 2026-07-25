"""The single schema-declared structural AST traversal (campaign S5; totality
made framework-owned by remediation slot 2.1, HIGH-2).

``walk_ast(node)`` is the sole structural traversal: it yields each direct
structural ``ASTNode`` child of a node, reading the DECLARED ``AstChildSchema``
rather than re-discovering children by ad-hoc reflection. The schema names every
concrete node's child fields AND their container shape, so it handles shapes a
plain "is it an ASTNode / a list of ASTNodes?" reflection walk MISSES — notably
``IfConditional.elif_parts`` (a ``List[Tuple[StatementList, StatementList]]``,
which the historical reflection walk silently skipped, under-counting the elif
branches of every analysis pass that relied on the generic walk).

The schema is the authority; it is drift-locked against reflection over the real
node classes by ``tests/unit/tooling/test_ast_child_schema_guard.py`` (a new
child-bearing field on any node, or a stale declaration, fails that guard).

The S3 syntax templates are non-``ASTNode`` carriers, but the parsed
substitutions they hold (``SyntaxTemplate.subs[*].expansion`` — the read-time
validated ``$()``/``<()``/``>()`` inside ``${x:-...}`` operands, arithmetic
regions, and array subscripts) ARE structural children: each template-carrier
field is declared with ``ChildShape.TEMPLATE_SUBS`` and ``walk_ast`` yields the
nested expansion nodes. (Reappraisal #22 HIGH-2 overturned the earlier
"never descend into templates" exception: those subs carry executable programs,
and an analysis that skips them makes a false clean claim.)

``TotalTraversalVisitor`` is the analysis-visitor base that makes consumption
of this enumeration FRAMEWORK-OWNED: after a handler runs, the base sweeps
every declared child edge the handler did not dispatch. A handler can order or
contextualize its descent, but it can no longer accidentally omit an edge; a
deliberate skip must be declared in ``PRUNED_EDGES``.

``iter_child_nodes`` is retained as a thin alias delegating to ``walk_ast``.
``visit_children`` is its callback protocol.
"""
import dataclasses
import enum
from typing import Dict, FrozenSet, Iterator, Set, Tuple

from ..ast_nodes import ASTNode, SyntaxTemplate
from .base import ASTVisitor


class ChildShape(enum.Enum):
    """How a declared child field holds its ``ASTNode`` child/children."""

    NODE = "node"                        # a single (optional) ASTNode field
    NODE_LIST = "node_list"              # List[ASTNode]
    NODE_TUPLE_LIST = "node_tuple_list"  # List[Tuple[..., ASTNode, ...]]
    TEMPLATE_SUBS = "template_subs"      # Optional[SyntaxTemplate]: children
    #                                      are the .subs[*].expansion nodes


_N = ChildShape.NODE
_L = ChildShape.NODE_LIST
_T = ChildShape.NODE_TUPLE_LIST
_S = ChildShape.TEMPLATE_SUBS

# AstChildSchema: for each concrete ``psh.ast_nodes`` node class (keyed by class
# name, the flat namespace the coverage-matrix meta-test also keys on), the
# ORDERED tuple of its structural child fields and their container shape. This is
# the declared authority ``walk_ast`` reads. It is drift-locked against reflection
# over the resolved field annotations (test_ast_child_schema_guard.py): every
# field whose (resolved) type is an ``ASTNode`` subclass, a ``List`` of one, or a
# ``List[Tuple[...]]`` containing one is declared here with the matching shape;
# every other field (scalars, str/int/bool, and the non-``ASTNode`` S3
# syntax-template carriers) is omitted. Fields are in dataclass-declaration order
# so ``walk_ast`` yields children in the same order the historical reflection walk
# did (byte-stable for order-sensitive consumers), with the previously-skipped
# tuple-list children inserted at their field position.
AstChildSchema: Dict[str, Tuple[Tuple[str, ChildShape], ...]] = {
    'AndOrList': (('pipelines', _L),),
    'ArithmeticEvaluation': (('redirects', _L), ('arith_template', _S)),
    'ArithmeticExpansion': (('arith_template', _S),),
    'ArrayAssignment': (),
    'ArrayElementAssignment': (('value_word', _N), ('index_spec', _S)),
    'ArrayInitialization': (('words', _L),),
    'BinaryTestExpression': (('left_word', _N), ('right_word', _N)),
    'BraceGroup': (('statements', _N), ('redirects', _L)),
    'CStyleForLoop': (('body', _N), ('redirects', _L), ('init_template', _S),
                      ('condition_template', _S), ('update_template', _S)),
    'CaseConditional': (('items', _L), ('redirects', _L), ('subject_word', _N)),
    'CaseItem': (('patterns', _L), ('commands', _N)),
    'CasePattern': (('word', _N),),
    'CommandSubstitution': (('program', _N),),
    'CompoundTestExpression': (('left', _N), ('right', _N)),
    'EnhancedTestStatement': (('expression', _N), ('redirects', _L)),
    'ExpansionPart': (('expansion', _N),),
    'ForLoop': (('body', _N), ('redirects', _L), ('item_words', _L)),
    'FunctionDef': (('body', _N), ('redirects', _L)),
    'IfConditional': (('condition', _N), ('then_part', _N),
                      ('elif_parts', _T), ('else_part', _N), ('redirects', _L)),
    'LiteralPart': (),
    'NegatedTestExpression': (('expression', _N),),
    'ParameterExpansion': (('word_template', _S), ('subscript_spec', _S)),
    'Pipeline': (('commands', _L),),
    'ProcessSubstitution': (('program', _N),),
    'Program': (('statements', _L),),
    'Redirect': (('target_word', _N),),
    'SelectLoop': (('body', _N), ('redirects', _L), ('item_words', _L)),
    'SimpleCommand': (('redirects', _L), ('array_assignments', _L), ('words', _L)),
    'StatementList': (('statements', _L),),
    'SubshellGroup': (('statements', _N), ('redirects', _L)),
    'UnaryTestExpression': (('operand_word', _N),),
    'UntilLoop': (('condition', _N), ('body', _N), ('redirects', _L)),
    'VariableExpansion': (('subscript_spec', _S),),
    'WhileLoop': (('condition', _N), ('body', _N), ('redirects', _L)),
    'Word': (('parts', _L), ('array_init', _N)),
    'WordPart': (),
}


def walk_ast_edges(node: ASTNode) -> Iterator[Tuple[str, ASTNode]]:
    """Yield ``(field_name, child)`` for each direct structural child edge.

    THE sole structural enumeration. Reads ``AstChildSchema`` for *node*'s
    class and yields the child(ren) of each declared field per its container
    shape — including, for ``TEMPLATE_SUBS`` fields, the parsed substitution
    nodes carried by an S3 syntax template (``template.subs[*].expansion``; a
    deferred backtick's node is yielded too, its unparsed body being the
    visitor's concern). A node class not in the schema (a synthetic ``ASTNode``
    subclass defined outside ``psh.ast_nodes`` — e.g. a test's
    ``_UnknownCarrier``) falls back to reflection; the drift-lock guard proves
    every production node IS registered, so production traversal never uses the
    fallback.
    """
    fields = AstChildSchema.get(type(node).__name__)
    if fields is None:
        yield from _reflect_child_edges(node)
        return
    for name, shape in fields:
        value = getattr(node, name, None)
        if value is None:
            continue
        if shape is ChildShape.NODE:
            if isinstance(value, ASTNode):
                yield name, value
        elif shape is ChildShape.NODE_LIST:
            for item in value:
                if isinstance(item, ASTNode):
                    yield name, item
        elif shape is ChildShape.TEMPLATE_SUBS:
            if isinstance(value, SyntaxTemplate):
                for sub in value.subs:
                    yield name, sub.expansion
        else:  # NODE_TUPLE_LIST
            for item in value:
                if isinstance(item, tuple):
                    for element in item:
                        if isinstance(element, ASTNode):
                            yield name, element
                elif isinstance(item, ASTNode):
                    yield name, item


def walk_ast(node: ASTNode) -> Iterator[ASTNode]:
    """Yield each direct structural ``ASTNode`` child of *node* (schema order).

    The child view of :func:`walk_ast_edges` (the sole structural
    enumeration), for consumers that don't need the field names.
    """
    for _name, child in walk_ast_edges(node):
        yield child


def _reflect_child_edges(node: ASTNode) -> Iterator[Tuple[str, ASTNode]]:
    """Reflection fallback for UNREGISTERED synthetic node classes only.

    Walks the node's dataclass fields, yielding any ``ASTNode`` value, any
    ``ASTNode`` element of a list, and any ``ASTNode`` element of a tuple inside
    a list (so a synthetic node exercising the tuple-list shape still traverses
    — totality). Production nodes never reach here (drift-lock).
    """
    if not dataclasses.is_dataclass(node):
        return
    for field in dataclasses.fields(node):
        attr = getattr(node, field.name, None)
        if isinstance(attr, ASTNode):
            yield field.name, attr
        elif isinstance(attr, list):
            for item in attr:
                if isinstance(item, ASTNode):
                    yield field.name, item
                elif isinstance(item, tuple):
                    for element in item:
                        if isinstance(element, ASTNode):
                            yield field.name, element


def iter_child_nodes(node: ASTNode) -> Iterator[ASTNode]:
    """Yield each direct ``ASTNode`` child of *node*.

    Thin back-compat alias over :func:`walk_ast` — the sole structural
    traversal. (Retained because analysis visitors and their tests import this
    name; new code should call ``walk_ast`` directly.)
    """
    yield from walk_ast(node)


def visit_children(visitor, node: ASTNode) -> None:
    """Visit every direct ``ASTNode`` child of *node* with *visitor*.

    The callback protocol over :func:`walk_ast`: a visitor's ``generic_visit``
    delegates here to descend into an unhandled node's children.
    """
    for child in walk_ast(node):
        visitor.visit(child)


class TotalTraversalVisitor(ASTVisitor[None]):
    """Analysis-visitor base with FRAMEWORK-OWNED total child traversal.

    ``visit()`` runs the node's handler (``visit_X`` or ``generic_visit``),
    recording every child the handler itself dispatches, then SWEEPS: it
    dispatches every remaining child edge the schema declares for the node.
    A handler therefore keeps full control of descent ORDER and surrounding
    context (context stacks, nesting depth, scope enter/exit), but it cannot
    accidentally omit an edge — an early return or a forgotten field no longer
    silently skips a subtree; the sweep visits it. This is the seam that makes
    the four reappraisal-#22 HIGH-2 bypasses (redirect-only commands, redirect
    targets, for/case subject words, template subs) structurally impossible.

    Deliberate pruning must be declared in ``PRUNED_EDGES`` as
    ``(NodeClassName, field_name)`` pairs — an explicit, named decision at the
    authority's seam. Production analysis visitors declare NONE; the guard
    battery (``tests/unit/visitor/test_traversal_totality_battery.py``) fails
    on any undeclared skip and audits every declared one.

    INVARIANT: within one traversal, every node OBJECT is analysis-dispatched
    exactly once, regardless of which ancestor's handler dispatched it. The
    dispatch record is therefore a single traversal-scoped set, visible to
    every descendant's sweep — NOT a per-parent frame. (A per-parent record
    shipped an exponential double-visit: a handler dispatching a GRANDCHILD,
    like a case handler visiting ``item.commands`` past the ``CaseItem``,
    recorded it only in the grandparent's frame, and the intermediate node's
    own sweep re-dispatched it — 2^N re-analysis under nested cases. Pinned
    by ``tests/unit/visitor/test_traversal_multiplicity.py``.) An AST is a
    tree (no node object under two parents — the parsers never alias), so
    once-per-traversal and once-per-parent-edge coincide; the set clears when
    the outermost visit returns, so a reused visitor instance cannot skip
    nodes of a later tree whose ids happen to collide with a collected
    earlier one.

    Subclasses must not override ``visit()`` — the totality guarantee lives
    there (enforced by the battery's no-override check).
    """

    #: Explicit, named pruned edges: {(node class name, field name)}. Empty for
    #: every production analysis visitor.
    PRUNED_EDGES: FrozenSet[Tuple[str, str]] = frozenset()

    def __init__(self) -> None:
        super().__init__()
        # Ids of every node dispatched during the CURRENT traversal (cleared
        # when the outermost visit returns), plus the current dispatch depth.
        self._visited: Set[int] = set()
        self._depth = 0

    def visit(self, node: ASTNode) -> None:
        self._visited.add(id(node))
        self._depth += 1
        try:
            super().visit(node)
            for field_name, child in walk_ast_edges(node):
                if (type(node).__name__, field_name) in self.PRUNED_EDGES:
                    continue
                if id(child) not in self._visited:
                    self.visit(child)
        finally:
            self._depth -= 1
            if self._depth == 0:
                self._visited.clear()

    @property
    def at_traversal_root(self) -> bool:
        """True while handling the node ``visit()`` was originally called on.

        Lets a visitor scope whole-program logic (e.g. the linter's
        end-of-program checks) to the outermost node, so a nested ``Program``
        reached inside a substitution body does not re-trigger it.
        """
        return self._depth == 1

    def generic_visit(self, node: ASTNode) -> None:
        """No per-node analysis for unhandled types; the sweep still descends
        into every declared child edge."""
