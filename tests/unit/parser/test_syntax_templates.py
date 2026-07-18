"""Unit pins for the S3 syntax templates and their validators.

Covers the canonical types, the three named region validators (read-time
nested-shell validation with lazy own-grammar), and that both parsers attach
the templates to their AST nodes. Companion triad guards live in
tests/unit/tooling/test_syntax_template_guards.py.
"""

import pytest

from psh.ast_nodes import (
    ArithmeticEvaluation,
    ArithmeticExpansion,
    ArithmeticTemplate,
    ArrayElementAssignment,
    CStyleForLoop,
    NestedSub,
    ParameterExpansion,
    SubscriptSpec,
    VariableExpansion,
    WordTemplate,
)
from psh.ast_nodes.syntax_templates import SyntaxTemplate
from psh.lexer import tokenize_with_heredocs
from psh.parser import (
    Parser,
    SubstitutionSyntaxError,
    is_substitution_origin,
)
from psh.parser.recursive_descent.support.syntax_templates import (
    build_arithmetic_template,
    build_subscript_spec,
    build_word_template,
)


def _parse(src, parser="rd"):
    tokens, heredocs = tokenize_with_heredocs(src)
    if parser == "combinator":
        from psh.parser.combinators.parser import ParserCombinatorShellParser
        from psh.parser.config import ParserConfig
        return ParserCombinatorShellParser(ParserConfig()).parse(list(tokens))
    return Parser(list(tokens), source_text=src, heredocs=heredocs).parse()


def _first(root, cls):
    """First node of type cls anywhere in the tree (dataclass-field walk)."""
    import dataclasses
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, cls):
            return node
        if dataclasses.is_dataclass(node):
            for f in dataclasses.fields(node):
                v = getattr(node, f.name, None)
                if dataclasses.is_dataclass(v):
                    stack.append(v)
                elif isinstance(v, list):
                    stack.extend(x for x in v if dataclasses.is_dataclass(x))
    return None


# ---- canonical types --------------------------------------------------------

def test_template_types_are_frozen_and_named():
    import dataclasses
    for cls in (WordTemplate, ArithmeticTemplate, SubscriptSpec):
        assert issubclass(cls, SyntaxTemplate)
    t = build_word_template("$(echo x)")
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.text = "mutated"  # frozen


def test_validated_and_deferred_partition():
    t = build_word_template("$(echo a)`b`$(echo c)")
    assert len(t.subs) == 3
    assert len(t.validated) == 2          # two modern $()
    assert len(t.deferred_backticks) == 1  # one backtick
    assert t.spans_reconstruct()


# ---- validator: read-time reject vs lazy accept -----------------------------

_REJECT = [
    ("word", build_word_template, "$(if)"),
    ("word_dq", build_word_template, '"$(if)"'),
    ("word_nested", build_word_template, "${y:-$(if)}"),
    ("word_procsub", build_word_template, "<(if)"),
    ("arith", build_arithmetic_template, " $(if) + 1 "),
    ("arith_param", build_arithmetic_template, " ${x:-$(if)} "),
    ("subscript", build_subscript_spec, "$(if)"),
]


@pytest.mark.parametrize("label,fn,text", _REJECT, ids=[r[0] for r in _REJECT])
def test_validator_rejects_invalid_nested_substitution(label, fn, text):
    with pytest.raises(SubstitutionSyntaxError) as exc:
        fn(text)
    assert is_substitution_origin(exc.value)


_ACCEPT = [
    ("word_valid", build_word_template, "$(echo ok)"),
    ("word_squote", build_word_template, "'$(if)'"),       # single-quoted literal
    ("word_backtick", build_word_template, "`if`"),         # deferred
    ("word_pattern", build_word_template, "pat*/[abc]"),    # no subs
    ("arith_valid", build_arithmetic_template, " $(echo 3) + 1 "),
    ("arith_shift", build_arithmetic_template, " 1 << 2 "),  # NOT a heredoc
    ("arith_lt", build_arithmetic_template, " a < b "),      # < NOT procsub
    ("arith_dynamic", build_arithmetic_template, " 1 $op 2 "),
    ("subscript_arith", build_subscript_spec, "k+1"),
    ("subscript_cmdsub", build_subscript_spec, "$(echo 1)"),
]


@pytest.mark.parametrize("label,fn,text", _ACCEPT, ids=[r[0] for r in _ACCEPT])
def test_validator_accepts_valid_or_lazy(label, fn, text):
    t = fn(text)
    assert t.text == text
    assert t.spans_reconstruct()


# ---- node attachment (both parsers) -----------------------------------------

@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_parameter_operand_template_attached(parser):
    node = _first(_parse("x=set; echo ${x:-$(echo d)}", parser), ParameterExpansion)
    assert node is not None and node.word == "$(echo d)"
    assert isinstance(node.word_template, WordTemplate)
    assert node.word_template.text == node.word
    assert len(node.word_template.validated) == 1


@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_arith_expansion_template_attached(parser):
    node = _first(_parse("echo $(( $(echo 1) + 2 ))", parser), ArithmeticExpansion)
    assert node is not None
    assert isinstance(node.arith_template, ArithmeticTemplate)
    assert node.arith_template.text == node.expression


@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_arith_command_template_attached(parser):
    node = _first(_parse("(( 1 + 2 ))", parser), ArithmeticEvaluation)
    assert node is not None
    assert isinstance(node.arith_template, ArithmeticTemplate)
    assert node.arith_template.text == node.expression


def test_cstyle_for_clause_templates_attached():
    node = _first(_parse("for ((i=0; i<3; i++)); do :; done"), CStyleForLoop)
    assert node is not None
    for tmpl, raw in ((node.init_template, node.init_expr),
                      (node.condition_template, node.condition_expr),
                      (node.update_template, node.update_expr)):
        assert isinstance(tmpl, ArithmeticTemplate)
        assert tmpl.text == raw


@pytest.mark.parametrize("parser", ["rd", "combinator"])
def test_element_assignment_index_spec_attached(parser):
    node = _first(_parse("a[1+1]=v", parser), ArrayElementAssignment)
    assert node is not None
    assert isinstance(node.index_spec, SubscriptSpec)
    assert node.index_spec.text == node.index


def test_subscripted_reference_spec_attached():
    # A subscripted ${arr[SUB]} stays a braced VariableExpansion with SUB in the
    # name; find the one that carries a subscript_spec.
    root = _parse("a=(1 2 3); echo ${a[0+1]}")
    import dataclasses
    found = None
    stack = [root]
    while stack:
        n = stack.pop()
        if isinstance(n, VariableExpansion) and n.subscript_spec is not None:
            found = n
        if dataclasses.is_dataclass(n):
            for f in dataclasses.fields(n):
                v = getattr(n, f.name, None)
                if dataclasses.is_dataclass(v):
                    stack.append(v)
                elif isinstance(v, list):
                    stack.extend(x for x in v if dataclasses.is_dataclass(x))
    assert found is not None
    assert isinstance(found.subscript_spec, SubscriptSpec)
    assert found.subscript_spec.text == "0+1"


# ---- structural identity via the TYPE (Ruling 2c) ---------------------------

def test_operand_error_is_same_type_as_toplevel_cmdsub_error():
    """The read-time error for a nested sub in a parameter operand is the SAME
    typed error as a top-level $() — asserted VIA THE TYPE, not a message
    string. This is what lets I3 treat the whole family with one consumer."""
    errors = {}
    for label, src in (("toplevel", "echo $(if)"),
                       ("operand", "x=set; echo ${x:-$(if)}"),
                       ("arith", "echo $(( $(if) ))"),
                       ("subscript", "a[$(if)]=v")):
        with pytest.raises(SubstitutionSyntaxError) as exc:
            _parse(src)
        errors[label] = exc.value
    # Identity via the type: every one is the same SubstitutionSyntaxError class
    # and carries the substitution origin.
    for err in errors.values():
        assert type(err) is SubstitutionSyntaxError
        assert is_substitution_origin(err) is True


def test_typed_error_render_is_unchanged_for_toplevel_cmdsub():
    """Inertness: retyping top-level $()'s error did not change its rendered
    diagnostic (position/caret/reason) — only the class and the origin flag."""
    with pytest.raises(SubstitutionSyntaxError) as exc:
        _parse("echo $(if)")
    render = exc.value.render()
    assert "syntax error: unexpected end of file" in render
    assert "if" in render
    # The flag is the ONLY added fact.
    assert exc.value.substitution_origin is True


# ---- deferred backtick is not eagerly validated -----------------------------

def test_backtick_in_operand_is_not_validated():
    t = build_word_template("`if`")
    assert len(t.deferred_backticks) == 1
    assert t.deferred_backticks[0].expansion.program is None


def test_nestedsub_span_round_trips():
    t = build_word_template("pre$(echo x)post")
    sub = t.validated[0]
    assert t.text[sub.start:sub.end] == "$(echo x)"
    assert isinstance(sub, NestedSub)
