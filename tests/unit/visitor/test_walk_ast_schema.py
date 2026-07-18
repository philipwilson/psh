"""walk_ast behavior + traversal totality (campaign S5).

Pins that walk_ast is the schema-driven sole structural traversal: it yields the
declared children of each container shape (NODE / NODE_LIST / NODE_TUPLE_LIST) in
declaration order, descends into elif_parts (the shape the old reflection walker
missed), never descends into the non-ASTNode S3 templates, skips None-valued
optional children, and falls back to reflection only for unregistered synthetic
nodes. ``iter_child_nodes`` is proven equal to ``walk_ast``.
"""
import dataclasses

import pytest

from psh.ast_nodes import (
    ASTNode,
    CommandSubstitution,
    CStyleForLoop,
    IfConditional,
    SimpleCommand,
    Word,
)
from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor.metrics_visitor import MetricsVisitor
from psh.visitor.traversal import (
    AstChildSchema,
    ChildShape,
    iter_child_nodes,
    walk_ast,
)


def _ast(src):
    return parse(tokenize(src))


def _find(root, cls):
    out, stack = [], [root]
    while stack:
        n = stack.pop()
        if isinstance(n, cls):
            out.append(n)
        stack.extend(walk_ast(n))
    return out


# --- Totality: a synthetic node with one child in EVERY container shape -------

@dataclasses.dataclass
class _ShapeProbe(ASTNode):
    """A node with a NODE, a NODE_LIST, and a NODE_TUPLE_LIST child field."""
    scalar: ASTNode = None            # type: ignore[assignment]
    lst: list = dataclasses.field(default_factory=list)
    tuplist: list = dataclasses.field(default_factory=list)


def test_walk_ast_totality_over_every_container_shape():
    """walk_ast yields a child in each supported container shape, in schema order.

    Registers _ShapeProbe in AstChildSchema so the SCHEMA path (not the
    reflection fallback) drives all three shapes — the totality proof.
    """
    a, b, c, d = (Word(parts=[]) for _ in range(4))
    probe = _ShapeProbe(scalar=a, lst=[b, c], tuplist=[(d,)])
    AstChildSchema['_ShapeProbe'] = (
        ('scalar', ChildShape.NODE),
        ('lst', ChildShape.NODE_LIST),
        ('tuplist', ChildShape.NODE_TUPLE_LIST),
    )
    try:
        children = list(walk_ast(probe))
    finally:
        del AstChildSchema['_ShapeProbe']
    assert children == [a, b, c, d], (
        "walk_ast must yield the NODE child, then each NODE_LIST child, then each "
        "NODE_TUPLE_LIST child, in declaration order"
    )


def test_walk_ast_tuple_list_yields_all_tuple_elements():
    """A NODE_TUPLE_LIST yields every ASTNode element of every tuple."""
    w = [Word(parts=[]) for _ in range(4)]
    probe = _ShapeProbe(tuplist=[(w[0], w[1]), (w[2], w[3])])
    AstChildSchema['_ShapeProbe'] = (('tuplist', ChildShape.NODE_TUPLE_LIST),)
    try:
        assert list(walk_ast(probe)) == w
    finally:
        del AstChildSchema['_ShapeProbe']


# --- Real-node behavior ------------------------------------------------------

def test_walk_ast_descends_into_elif_parts():
    """The elif branches (List[Tuple[...]]) ARE traversed — the latent-bug fix."""
    node = _find(_ast('if a; then b; elif c; then d; elif e; then g; fi'),
                 IfConditional)[0]
    children = list(walk_ast(node))
    # condition, then_part, 2x(elif cond+body), (no else), plus no redirects
    assert node.condition in children
    assert node.then_part in children
    # each elif tuple contributes its condition StatementList and body StatementList
    elif_children = [sl for pair in node.elif_parts for sl in pair]
    for sl in elif_children:
        assert sl in children
    assert len(elif_children) == 4


def test_walk_ast_skips_none_optional_child():
    """An absent optional child (else_part=None, subject_word=None) is not yielded."""
    node = _find(_ast('if a; then b; fi'), IfConditional)[0]
    assert node.else_part is None
    assert all(c is not None for c in walk_ast(node))


def test_walk_ast_yields_in_declaration_order():
    """SimpleCommand yields redirects, then array_assignments, then words."""
    node = _find(_ast('a=1 echo hi >out'), SimpleCommand)[0]
    kinds = [type(c).__name__ for c in walk_ast(node)]
    # redirects (Redirect) come before words (Word) per schema order
    assert kinds.index('Redirect') < kinds.index('Word')


def test_walk_ast_declares_command_substitution_program_as_child():
    """CommandSubstitution.program IS a declared structural child (walk yields it
    when a CommandSubstitution is walked directly), matching the historical
    iter_child_nodes behavior — even though analysis visitors reach it only via
    the opt-in visit_word_substitution_bodies helper."""
    sub = _find(_ast('echo $(true)'), CommandSubstitution)[0]
    assert sub.program is not None
    assert sub.program in list(walk_ast(sub))


def test_walk_ast_does_not_descend_into_syntax_templates():
    """A C-style for loop carries ArithmeticTemplates (non-ASTNode); walk_ast
    never yields them — the S5 template-descent decision."""
    node = _find(_ast('for ((i=0; i<3; i++)); do echo x; done'), CStyleForLoop)[0]
    # It DOES carry the templates...
    assert node.init_template is not None
    # ...but walk_ast yields only the body StatementList and (no) redirects.
    children = list(walk_ast(node))
    assert node.body in children
    for c in children:
        assert isinstance(c, ASTNode)  # every yielded child is a real node
    # None of the yielded children is a template carrier.
    template_types = {'ArithmeticTemplate', 'WordTemplate', 'SubscriptSpec',
                      'SyntaxTemplate', 'NestedSub'}
    assert not any(type(c).__name__ in template_types for c in children)


def test_walk_ast_reflection_fallback_for_unregistered_node():
    """An unregistered synthetic node (not in the schema) still traverses via the
    reflection fallback — so a test's _UnknownCarrier keeps working."""
    @dataclasses.dataclass
    class _Unregistered(ASTNode):
        kid: ASTNode = None  # type: ignore[assignment]
        kids: list = dataclasses.field(default_factory=list)

    assert '_Unregistered' not in AstChildSchema
    a, b = Word(parts=[]), Word(parts=[])
    node = _Unregistered(kid=a, kids=[b])
    assert list(walk_ast(node)) == [a, b]


# --- iter_child_nodes is walk_ast --------------------------------------------

CORPUS = [
    'echo hi', 'a | b | c', 'if x; then y; elif z; then w; else v; fi',
    'while a; do b; done', 'for i in 1 2; do echo $i; done',
    'case $x in a) b;; *) c;; esac', 'f() { echo hi; } | cat',
    '{ a; b; } | c', '( a; b )', 'echo $(x) <(y)', '[[ -n $x ]]', '((1+2))',
]


@pytest.mark.parametrize("src", CORPUS)
def test_iter_child_nodes_equals_walk_ast(src):
    """iter_child_nodes is a thin alias over walk_ast — identical everywhere."""
    for node in _find(_ast(src), ASTNode):
        assert list(iter_child_nodes(node)) == list(walk_ast(node))


# --- The one deliberate metrics improvement (elif-in-function command count) --

def test_metrics_counts_commands_in_elif_function_body():
    """walk_ast fixes the reflection walker's elif blind spot: a function whose
    body has an if/elif now counts the elif-branch commands (was under-counted).
    Pre-registered deliberate change (internal metric; no bash oracle)."""
    src = 'ef() { if a; then b; elif c; then d; elif e; then g; fi; }'
    m = MetricsVisitor()
    m.visit(_ast(src))
    # commands: a, b, c, d, e, g = 6 (base's reflection walker returned 2).
    assert m.get_report()['function_metrics']['ef']['commands'] == 6
