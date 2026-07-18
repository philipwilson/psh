"""The single schema-declared structural AST traversal (campaign S5).

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
child-bearing field on any node, or a stale declaration, fails that guard). The
S3 syntax templates are deliberately NOT ``ASTNode`` subclasses, so they never
appear in the schema and ``walk_ast`` never descends into them — the same net
policy as ``CommandSubstitution.program`` (a declared child, but reached in
practice only by the opt-in ``visit_word_substitution_bodies`` helper, since no
analysis visitor dispatches a ``Word`` through ``visit()``).

``iter_child_nodes`` is retained as a thin alias delegating to ``walk_ast`` so
the analysis visitors' ``generic_visit`` and the substitution-body helper share
the one authority. ``visit_children`` and ``visit_word_substitution_bodies`` are
its callback protocol.
"""
import dataclasses
import enum
from typing import Dict, Iterator, Tuple

from ..ast_nodes import ASTNode, ExpansionPart, Word


class ChildShape(enum.Enum):
    """How a declared child field holds its ``ASTNode`` child/children."""

    NODE = "node"                        # a single (optional) ASTNode field
    NODE_LIST = "node_list"              # List[ASTNode]
    NODE_TUPLE_LIST = "node_tuple_list"  # List[Tuple[..., ASTNode, ...]]


_N = ChildShape.NODE
_L = ChildShape.NODE_LIST
_T = ChildShape.NODE_TUPLE_LIST

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
    'ArithmeticEvaluation': (('redirects', _L),),
    'ArithmeticExpansion': (),
    'ArrayAssignment': (),
    'ArrayElementAssignment': (('value_word', _N),),
    'ArrayInitialization': (('words', _L),),
    'BinaryTestExpression': (('left_word', _N), ('right_word', _N)),
    'BraceGroup': (('statements', _N), ('redirects', _L)),
    'CStyleForLoop': (('body', _N), ('redirects', _L)),
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
    'ParameterExpansion': (),
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
    'VariableExpansion': (),
    'WhileLoop': (('condition', _N), ('body', _N), ('redirects', _L)),
    'Word': (('parts', _L), ('array_init', _N)),
    'WordPart': (),
}


def walk_ast(node: ASTNode) -> Iterator[ASTNode]:
    """Yield each direct structural ``ASTNode`` child of *node* (schema order).

    THE sole structural traversal. Reads ``AstChildSchema`` for *node*'s class
    and yields the child(ren) of each declared field per its container shape. A
    node class not in the schema (a synthetic ``ASTNode`` subclass defined
    outside ``psh.ast_nodes`` — e.g. a test's ``_UnknownCarrier``) falls back to
    reflection; the drift-lock guard proves every production node IS registered,
    so production traversal never uses the fallback.
    """
    fields = AstChildSchema.get(type(node).__name__)
    if fields is None:
        yield from _reflect_children(node)
        return
    for name, shape in fields:
        value = getattr(node, name, None)
        if value is None:
            continue
        if shape is ChildShape.NODE:
            if isinstance(value, ASTNode):
                yield value
        elif shape is ChildShape.NODE_LIST:
            for item in value:
                if isinstance(item, ASTNode):
                    yield item
        else:  # NODE_TUPLE_LIST
            for item in value:
                if isinstance(item, tuple):
                    for element in item:
                        if isinstance(element, ASTNode):
                            yield element
                elif isinstance(item, ASTNode):
                    yield item


def _reflect_children(node: ASTNode) -> Iterator[ASTNode]:
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
            yield attr
        elif isinstance(attr, list):
            for item in attr:
                if isinstance(item, ASTNode):
                    yield item
                elif isinstance(item, tuple):
                    for element in item:
                        if isinstance(element, ASTNode):
                            yield element


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


def visit_word_substitution_bodies(visitor, node: ASTNode) -> None:
    """Descend into the parsed bodies of substitutions embedded in *node*'s Words.

    Word-bearing nodes (``SimpleCommand`` args and assignment values) analyze
    their words inline rather than dispatching them, so a modern command/process
    substitution embedded in a word — and the nested ``Program`` it carries —
    is otherwise never reached by an analysis visitor. For each such
    substitution this visits the body's *statements* (not the ``Program`` node),
    so per-command analysis (security, lint, metrics, validation) runs on the
    inner commands WITHOUT re-triggering any program-level/root logic the
    visitor attaches to ``visit_Program``. Backtick substitutions carry
    ``program=None`` and are skipped. (This is the opt-in path by which
    ``CommandSubstitution.program`` — a declared but generically-unreached
    structural child — is analyzed; S3 syntax-template subs are non-``ASTNode``
    and out of scope here, matching that policy.)
    """
    for child in walk_ast(node):
        if not isinstance(child, Word):
            continue
        for part in child.parts:
            if isinstance(part, ExpansionPart):
                program = getattr(part.expansion, 'program', None)
                if program is not None:
                    for statement in program.statements:
                        visitor.visit(statement)
