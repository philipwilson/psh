"""Triad guards for the S3 syntax templates (campaign: boundary integrity).

Three protected facts, each with a synthetic offender that is actually RUN here
(so the guard is proven to BITE, not merely to pass):

1. Guarded-consistent legacy fields — a template's ``text`` reconstructs the
   raw field it backs (``word``/``expression``/``index``/subscript) and its
   spans index that text. Offender: a template whose text diverges is detected.
2. DeferredBacktick policy — a backtick substitution NEVER carries a parsed
   program (``backtick_style`` implies ``program is None``) and
   ``NestedSub.is_deferred_backtick`` is the one named seam. Offender: a
   backtick node carrying a program is detected.
3. Substitution-origin chokepoint — every substitution-body syntax error is
   raised as ``SubstitutionSyntaxError`` (the I3 producer contract); no
   substitution parse error escapes untagged. Offender: a plain-``ParseError``
   substitution error is distinguishable and the chokepoint re-types it.
"""

import pytest

from psh.ast_nodes import (
    ArithmeticEvaluation,
    ArithmeticExpansion,
    ArrayElementAssignment,
    CommandSubstitution,
    CStyleForLoop,
    NestedSub,
    ParameterExpansion,
    Program,
    VariableExpansion,
    WordTemplate,
)
from psh.lexer import tokenize_with_heredocs
from psh.parser import ParseError, Parser, SubstitutionSyntaxError, is_substitution_origin
from psh.parser.recursive_descent.support.syntax_templates import (
    build_arithmetic_template,
    build_word_template,
)
from psh.parser.recursive_descent.support.word_builder import WordBuilder
from psh.visitor.traversal import iter_child_nodes


def _parse(src: str) -> Program:
    tokens, heredocs = tokenize_with_heredocs(src)
    return Parser(list(tokens), source_text=src, heredocs=heredocs).parse()


def _all_nodes(node):
    yield node
    for child in iter_child_nodes(node):
        yield from _all_nodes(child)


def _template_pairs(root):
    """Yield (template, raw_field_value) for every S3-template-bearing node."""
    for node in _all_nodes(root):
        if isinstance(node, ParameterExpansion):
            if node.word_template is not None:
                yield (node.word_template, node.word)
            if node.subscript_spec is not None:
                yield (node.subscript_spec, WordBuilder._extract_subscript(node.parameter))
        elif isinstance(node, VariableExpansion):
            if node.subscript_spec is not None:
                yield (node.subscript_spec, WordBuilder._extract_subscript(node.name))
        elif isinstance(node, (ArithmeticExpansion, ArithmeticEvaluation)):
            if node.arith_template is not None:
                yield (node.arith_template, node.expression)
        elif isinstance(node, ArrayElementAssignment):
            if node.index_spec is not None:
                yield (node.index_spec, node.index)
        elif isinstance(node, CStyleForLoop):
            for tmpl, raw in ((node.init_template, node.init_expr),
                              (node.condition_template, node.condition_expr),
                              (node.update_template, node.update_expr)):
                if tmpl is not None:
                    yield (tmpl, raw)


# A corpus exercising every region and every quoting/nesting shape.
_CORPUS = [
    "x=set; echo ${x:-$(echo a)b~c}",
    "echo ${x#pat*} ${x%.txt} ${x/a/b} ${x//x/y}",
    "echo ${x:-`legacy`} ${x:-'$(lit)'}",
    "echo ${x:-${y:-$(echo deep)}}",
    "echo $(( $(echo 1) + 2 * 3 ))",
    "(( a + b ))",
    "for ((i=0; i<$(echo 3); i=i+1)); do echo $i; done",
    "a[$(echo 1)+1]=v",
    "a=(1 2 3); echo ${a[$(echo 0)]}",
    "echo ${arr[i+1]}",
    "echo $(( 1 << 4 )) $(( a < b ))",
]


def _collect():
    pairs = []
    for src in _CORPUS:
        pairs.extend(_template_pairs(_parse(src)))
    return pairs


# ---- GUARD 1: guarded-consistent legacy fields -----------------------------

def test_templates_reconstruct_their_raw_field():
    """Every template's text equals the raw field it backs, and its spans index
    that text (the designed authority split stays consistent)."""
    pairs = _collect()
    assert pairs, "corpus produced no templates — guard would be vacuous"
    for tmpl, raw in pairs:
        assert tmpl.text == raw, (type(tmpl).__name__, tmpl.text, raw)
        assert tmpl.spans_reconstruct(), (type(tmpl).__name__, tmpl.text)


def test_synthetic_inconsistent_template_is_detected():
    """SYNTHETIC OFFENDER: a template whose spans no longer index its text
    fails ``spans_reconstruct`` — the drift the consistency guard catches."""
    good = build_word_template("$(echo x)")
    assert good.spans_reconstruct()
    # Corrupt the span so it no longer selects the substitution source.
    bad = WordTemplate(text="$(echo x)",
                       subs=(NestedSub(good.subs[0].expansion, 0, 3),))
    assert not bad.spans_reconstruct()  # offender detected
    # Corrupt the text so it diverges from the field it would back.
    diverged = WordTemplate(text="TOTALLY DIFFERENT", subs=good.subs)
    assert not diverged.spans_reconstruct()


# ---- GUARD 2: DeferredBacktick policy ---------------------------------------

def test_is_deferred_backtick_is_the_named_seam():
    modern = NestedSub(CommandSubstitution(program=Program(), source="x",
                                           backtick_style=False), 0, 1)
    backtick = NestedSub(CommandSubstitution(program=None, source="x",
                                             backtick_style=True), 0, 1)
    assert backtick.is_deferred_backtick is True
    assert modern.is_deferred_backtick is False


def test_deferred_backticks_never_carry_a_program():
    """Across the corpus, every deferred backtick carries program=None."""
    saw_backtick = False
    for tmpl, _ in _collect():
        for sub in tmpl.deferred_backticks:
            saw_backtick = True
            assert isinstance(sub.expansion, CommandSubstitution)
            assert sub.expansion.backtick_style is True
            assert sub.expansion.program is None
    assert saw_backtick, "corpus had no backtick — guard would be vacuous"


def test_synthetic_backtick_with_program_is_detectable():
    """SYNTHETIC OFFENDER: a backtick node forced to carry a parsed program
    violates the deferred-timing invariant, and the guard predicate detects it."""
    offender = CommandSubstitution(program=Program(), source="x",
                                   backtick_style=True)

    def backtick_program_invariant(cs: CommandSubstitution) -> bool:
        # The invariant is_deferred_backtick encodes: backtick ⟹ program None.
        return not (cs.backtick_style and cs.program is not None)

    assert backtick_program_invariant(
        CommandSubstitution(program=None, source="x", backtick_style=True))
    assert not backtick_program_invariant(offender)  # offender fires the guard


def test_backticks_are_not_read_time_validated():
    """A backtick body with invalid shell syntax is DEFERRED, so building a
    template does not raise (bash never read-time-validates backticks)."""
    tmpl = build_word_template("`if`")          # would reject if eagerly parsed
    assert len(tmpl.deferred_backticks) == 1
    assert build_arithmetic_template(" `if` + 1 ").deferred_backticks  # arith too


# ---- GUARD 3: substitution-origin chokepoint --------------------------------

_INVALID_IN_EACH_REGION = [
    "echo $(if)",                       # top-level command sub
    "cat <(if)",                        # process sub
    "x=set; echo ${x:-$(if)}",          # parameter operand
    "echo $(( $(if) + 1 ))",            # arithmetic expansion
    "(( $(if) ))",                      # arithmetic command
    "for ((i=$(if); i<2; i++)); do :; done",  # C-style clause
    "a[$(if)]=v",                       # element-assignment subscript
    "a=(1 2); echo ${a[$(if)]}",        # subscript reference
    "echo $( $(if) )",                  # nested
]


@pytest.mark.parametrize("src", _INVALID_IN_EACH_REGION)
def test_every_substitution_body_error_is_tagged(src):
    """No substitution-body syntax error escapes untagged (I3 producer)."""
    with pytest.raises(SubstitutionSyntaxError) as exc:
        _parse(src)
    assert is_substitution_origin(exc.value) is True
    assert isinstance(exc.value, ParseError)  # behaviorally inert: still a ParseError


def test_plain_syntax_error_is_not_tagged():
    """A NON-substitution syntax error stays untagged (the flag is inert)."""
    with pytest.raises(ParseError) as exc:
        _parse("if")
    assert not isinstance(exc.value, SubstitutionSyntaxError)
    assert is_substitution_origin(exc.value) is False


def test_synthetic_untagged_substitution_error_is_distinguishable():
    """SYNTHETIC OFFENDER: a substitution body error raised as PLAIN ParseError
    is missing the origin the chokepoint guarantees — proving the tag is
    load-bearing, and the chokepoint (parse_nested_command) closes the gap."""
    from psh.parser.recursive_descent.support.nested_parse import parse_nested_command
    # Bypass the chokepoint: parse the body directly -> plain ParseError (untagged).
    tokens, heredocs = tokenize_with_heredocs("if")
    with pytest.raises(ParseError) as raw:
        Parser(list(tokens), source_text="if", heredocs=heredocs).parse()
    assert is_substitution_origin(raw.value) is False  # the gap
    # The chokepoint re-types the SAME body error as substitution-origin.
    with pytest.raises(SubstitutionSyntaxError) as tagged:
        parse_nested_command("if")
    assert is_substitution_origin(tagged.value) is True


def test_typed_error_retyping_is_inert():
    """Re-typing preserves the rendered diagnostic and the continuation signal
    (at_eof), so consumers that key on them are unaffected."""
    from psh.parser.recursive_descent.support.nested_parse import parse_nested_command
    tokens, heredocs = tokenize_with_heredocs("if")
    plain = None
    try:
        Parser(list(tokens), source_text="if", heredocs=heredocs).parse()
    except ParseError as e:
        plain = e
    tagged = None
    try:
        parse_nested_command("if")
    except SubstitutionSyntaxError as e:
        tagged = e
    assert plain is not None and tagged is not None
    assert plain.at_eof == tagged.at_eof          # structural signal preserved
    assert plain.summary == tagged.summary        # same short reason
