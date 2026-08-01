"""walk_ast behavior + traversal totality (campaign S5; totality remediation 2.1).

Pins that walk_ast is the schema-driven sole structural traversal: it yields the
declared children of each container shape (NODE / NODE_LIST / NODE_TUPLE_LIST /
TEMPLATE_SUBS) in declaration order, descends into elif_parts (the shape the old
reflection walker missed), yields the parsed substitutions inside S3 template
carriers (the exception reappraisal #22 HIGH-2 overturned), skips None-valued
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
    """CommandSubstitution.program IS a declared structural child; analysis
    visitors now reach it through the framework sweep (TotalTraversalVisitor),
    not an opt-in helper."""
    sub = _find(_ast('echo $(true)'), CommandSubstitution)[0]
    assert sub.program is not None
    assert sub.program in list(walk_ast(sub))


def test_walk_ast_yields_template_subs_not_template_carriers():
    """A template carrier field yields the parsed substitution NODES the
    template holds — never the (non-ASTNode) template object itself.

    The `$(echo 2)` inside an arithmetic region lives only in the
    ArithmeticTemplate's subs; walk_ast enumerating it is what lets every
    analysis pass see the executable program a raw-text region embeds
    (reappraisal #22 HIGH-2 overturned the old never-descend exception).
    """
    node = _find(_ast('for ((i=0; i<$(echo 2); i++)); do echo x; done'),
                 CStyleForLoop)[0]
    assert node.condition_template is not None
    assert node.condition_template.subs, "condition template should carry the $()"
    children = list(walk_ast(node))
    assert node.body in children
    for c in children:
        assert isinstance(c, ASTNode)  # every yielded child is a real node
    # The nested substitution node itself is yielded...
    sub_nodes = [s.expansion for s in node.condition_template.subs]
    for sub in sub_nodes:
        assert sub in children
    # ...but never the template carrier objects.
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


# --- Line offsetting over template-sub programs (round-3 B8 disclosure pin) --

def testoffset_line_numbers_reaches_stamped_template_sub_nodes():
    """TEMPLATE_SUBS descent is a REAL (if today invisible) change for
    source_processor.offset_line_numbers: some nodes inside a template-sub
    program DO carry buffer-relative line stamps (AndOrList/Pipeline; the
    inner SimpleCommand/Word are unstamped by the word builder), and they are
    now offset with the rest of the buffer — at base they were never touched.
    No user-visible delta exists today: execution re-parses the template TEXT
    at runtime, so $LINENO inside the substitution comes from the fresh
    runtime parse, and nothing consumes these read-time nodes' .line. Pinned
    so the behavior is a documented fact rather than an accident."""
    from psh.ast_nodes import ParameterExpansion
    from psh.scripting.source_processor import offset_line_numbers

    ast = _ast('echo "${x:-$(inner)}"')
    pe = _find(ast, ParameterExpansion)[0]
    program = pe.word_template.subs[0].expansion.program
    stamped = [n for n in _find(program, ASTNode) if n.line is not None]
    assert stamped, "expected stamped nodes (AndOrList/Pipeline) in the sub program"
    before = [n.line for n in stamped]
    offset_line_numbers(ast, 100)
    assert [n.line for n in stamped] == [line + 100 for line in before]
