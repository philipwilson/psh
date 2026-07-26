"""RD vs combinator parity through the ONE parse entry that carries ParseInputs.

Executable proof for remediation HIGH-5. The single
``parse_with_inputs(tokens, inputs, active_parser)`` entry threads the whole
frozen ``ParseInputs`` (source_text, line_offset, lexer_options, heredocs,
config) into BOTH parsers, so the combinator no longer discards the caller's
option-sensitive lexing context on the nested-substitution re-lex.

Red-on-base (db6dfb13): with ``shopt -s extglob`` active, the combinator
REJECTED a nested extglob pattern inside a modern substitution —
``echo $(echo @(a|b))`` raised "syntax error near unexpected token '('" — while
recursive descent (and bash 5.2.26) accepted it. The old facade wrapper in
``create_parser`` dropped ``lexer_options`` before the combinator saw them, so
the ``$(...)`` body re-lexed WITHOUT extglob. Threading ``ParseInputs`` through
the one entry flips every such case to parity.

DOMAIN (instrument discipline — a "no divergence" result is only as strong as
its corpus):

  * Space (parser x construct x nesting x context-flag): the RE-LEX constructs
    {command substitution ($()), nested command substitution (depth 2), process
    substitution (<()), ``${...}`` operand, composite/fused word, double-quoted,
    arithmetic ($(()) with a nested $()), heredoc-bearing command} x
    {@, !, *, +, ?} extglob operators, threaded with ``lexer_options={'extglob':
    True}`` through the one entry. Every case is accepted by recursive descent
    and bash 5.2.26 (validated green against both before it can pin parity).
  * CONTEXT-FLAG dimension is exercised explicitly: an ordinary nested $()
    (no extglob pattern) agrees on both parsers whether or not extglob is
    threaded (``test_nested_substitution_parity_independent_of_extglob``).
  * BACKTICKS are a CONTROL, not a re-lex path: `...` command substitution is
    DEFERRED (``program=None``, raw source; execution re-parses), so an extglob
    pattern in a backtick body is never re-lexed at parse time — both parsers
    agree regardless of the flag
    (``test_backtick_body_is_deferred_not_relexed``). Outside the HIGH-5 domain
    by design.
  * STRUCTURE parity is asserted over the WHOLE canonical AST.
  * LOCATION parity is asserted over NESTED-substitution bodies — the ``.line``
    stamps both parsers set via the shared ``WordBuilder``/``_nested_program``.
    Top-level statement ``.line`` is recursive-descent-only — a pre-existing
    combinator gap (newly documented by this slot, not previously written down) —
    and is deliberately OUT of scope here.
  * The ``arrays.py#parse_word_as_word`` seam is OUT of scope (a CARRY,
    remediation RULING 2 + N8): it builds element/target words through the static
    ``WordBuilder`` without the per-call ctx (a separate, pre-existing combinator
    residual). Its blast radius is the FULL ``parse_word_as_word`` reach — array
    INITIALIZATION elements (``a=($(echo @(a|b)))``), array ELEMENT assignments
    (``a[0]=$(echo @(a|b))``), AND REDIRECT TARGETS via ``RedirectionMixin``
    (``echo hi > $(echo @(a|b))``) all still diverge on the combinator. Not the
    HIGH-5 entry facade, unchanged by this slot; flip-pinned by
    ``test_CARRY_array_init_nested_substitution_still_diverges_on_combinator`` and
    ``test_CARRY_redirect_target_nested_substitution_still_diverges_on_combinator``
    (both co-flip only when the whole seam is threaded at once).
"""

import dataclasses
from enum import Enum

import pytest

from psh.ast_nodes import CommandSubstitution, ProcessSubstitution
from psh.lexer import tokenize, tokenize_with_heredocs
from psh.parser import ParseError, ParseInputs, parse_with_inputs

_EXTGLOB = {'extglob': True}

# Extglob operators (bash: @ ! * + ?). The bug is option-sensitive re-lexing of
# a nested substitution body, so every operator must survive the round trip.
_OPERATORS = ('@', '!', '*', '+', '?')

# Construct shapes that re-lex a nested substitution body at parse time. Each
# ``{pat}`` slot is filled with an extglob pattern; the resulting body is what
# the combinator used to re-lex WITHOUT extglob when the entry dropped options.
_SHAPES = (
    ('cmd-sub', 'echo $(echo {pat})'),                       # $() depth 1
    ('cmd-sub-nested', 'echo $(echo $(echo {pat}))'),        # $() depth 2
    ('process-sub', 'cat <(echo {pat})'),                    # <(...)
    ('param-operand-cmd-sub', 'echo ${{x:-$(echo {pat})}}'),  # ${...} operand
    ('composite-word', 'echo pre$(echo {pat})post'),         # fused word part
    ('double-quoted-cmd-sub', 'echo "$(echo {pat})"'),       # quoting context
    ('arith-nested-cmd-sub', 'echo $(( $(echo {pat}) ))'),   # $() inside $(())
)


def _extglob_corpus():
    params = []
    for op in _OPERATORS:
        pat = f'{op}(a|b)'
        for shape_id, template in _SHAPES:
            src = template.format(pat=pat)
            params.append(pytest.param(src, id=f'{shape_id}-{op}'))
    return params


EXTGLOB_CORPUS = _extglob_corpus()


def _canonical_ast(value):
    """AST dataclasses -> plain nested values for structural equality.

    ``.line`` is a plain class attribute, not a dataclass field, so it is NOT
    part of this structural view (location parity is checked separately).
    """
    if isinstance(value, Enum):
        return value.name
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, list):
        return [_canonical_ast(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_canonical_ast(item) for item in value)
    if dataclasses.is_dataclass(value):
        return {
            'type': type(value).__name__,
            **{
                field.name: _canonical_ast(getattr(value, field.name))
                for field in dataclasses.fields(value)
            },
        }
    return repr(value)


def _nested_substitution_lines(root):
    """Collect ``(kind, [stmt.line, ...])`` for every nested-substitution body.

    Walks the whole AST and records, for each ``CommandSubstitution`` /
    ``ProcessSubstitution`` that carries a parsed nested ``program``, the kind
    and the ``.line`` stamps of that program's statements. These stamps are the
    location context the shared ``WordBuilder``/``_nested_program`` sets from the
    threaded ``ParseInputs``; both parsers must agree.
    """
    lines = []
    seen: set = set()

    def walk(node):
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, (CommandSubstitution, ProcessSubstitution)):
            prog = getattr(node, 'program', None)
            if prog is not None and hasattr(prog, 'statements'):
                kind = type(node).__name__
                lines.append((kind, [s.line for s in prog.statements]))
        for name in getattr(node, '__dataclass_fields__', {}):
            child = getattr(node, name)
            if isinstance(child, (list, tuple)):
                for item in child:
                    if hasattr(item, '__dataclass_fields__'):
                        walk(item)
            elif hasattr(child, '__dataclass_fields__'):
                walk(child)
        for stmt in getattr(node, 'statements', []):
            walk(stmt)

    walk(root)
    return lines


def _parse_both(source, *, lexer_options=None, line_offset=0):
    """Parse *source* through the one entry with both parsers, same inputs."""
    inputs = ParseInputs(source_text=source, line_offset=line_offset,
                         lexer_options=lexer_options)
    rd = parse_with_inputs(list(tokenize(source, shell_options=lexer_options)),
                           inputs, 'recursive_descent')
    pc = parse_with_inputs(list(tokenize(source, shell_options=lexer_options)),
                           inputs, 'combinator')
    return rd, pc


def _parse_both_heredoc(source, *, lexer_options=None):
    """Parse a heredoc-bearing *source* through the entry (heredoc path)."""
    tokens, heredocs = tokenize_with_heredocs(source, shell_options=lexer_options)
    inputs = ParseInputs(source_text=source, lexer_options=lexer_options,
                         heredocs=heredocs)
    rd = parse_with_inputs(list(tokens), inputs, 'recursive_descent')
    pc = parse_with_inputs(list(tokens), inputs, 'combinator')
    return rd, pc


@pytest.mark.parametrize('source', EXTGLOB_CORPUS)
def test_extglob_nested_structure_parity(source):
    """With extglob threaded through the entry, both parsers agree structurally.

    Before the HIGH-5 fix the combinator raised on the nested extglob body;
    after it, the canonical ASTs are identical node for node.
    """
    rd, pc = _parse_both(source, lexer_options=_EXTGLOB)
    assert _canonical_ast(pc) == _canonical_ast(rd)


@pytest.mark.parametrize('source', EXTGLOB_CORPUS)
def test_extglob_nested_location_parity(source):
    """Nested-substitution body ``.line`` stamps agree under a line offset.

    Threaded through the entry with a non-zero ``line_offset``, both parsers
    build the nested body with the same shared context, so its line stamps
    match — the executable proof that ``line_offset`` is no longer dropped.
    """
    rd, pc = _parse_both(source, lexer_options=_EXTGLOB, line_offset=7)
    assert _nested_substitution_lines(pc) == _nested_substitution_lines(rd)


def test_high5_signature_case_flips_to_parity():
    """The exact LEDGER signature: nested ``@(a|b)`` in ``$()`` under extglob.

    Red-on-base: combinator raised ParseError; RD accepted. After the fix the
    combinator accepts it and matches RD.
    """
    source = 'echo $(echo @(a|b))'
    # Sanity: without extglob threaded, this is genuinely not extglob syntax and
    # BOTH parsers reject it (the body is `echo @` then a subshell `(a|b)`),
    # proving the corpus's parity is contingent on the threaded context.
    for parser in ('recursive_descent', 'combinator'):
        with pytest.raises(ParseError):
            parse_with_inputs(list(tokenize(source)),
                              ParseInputs(source_text=source), parser)
    # With extglob threaded through the one entry, both accept and agree.
    rd, pc = _parse_both(source, lexer_options=_EXTGLOB)
    assert _canonical_ast(pc) == _canonical_ast(rd)


@pytest.mark.parametrize('op', _OPERATORS)
def test_extglob_nested_in_heredoc_command_parity(op):
    """Heredoc PATH: a command carrying a heredoc AND a nested extglob $().

    Exercises the heredoc parse path (tokenize_with_heredocs → the entry with a
    heredocs map) with the same nested-substitution re-lex — parity confirms the
    entry threads options on the heredoc path too, not just the plain path.
    """
    source = f'echo $(echo {op}(a|b)) <<END\nbody\nEND'
    rd, pc = _parse_both_heredoc(source, lexer_options=_EXTGLOB)
    assert _canonical_ast(pc) == _canonical_ast(rd)


@pytest.mark.parametrize('flag', [None, _EXTGLOB], ids=['extglob-off', 'extglob-on'])
def test_nested_substitution_parity_independent_of_extglob(flag):
    """Context-flag dimension: an ordinary nested $() (no extglob pattern) agrees
    on both parsers whether or not extglob is threaded — the fix does not perturb
    the no-extglob case.
    """
    rd, pc = _parse_both('echo $(echo hi) $(( 1 + $(echo 2) ))', lexer_options=flag)
    assert _canonical_ast(pc) == _canonical_ast(rd)


@pytest.mark.parametrize('flag', [None, _EXTGLOB], ids=['extglob-off', 'extglob-on'])
def test_backtick_body_is_deferred_not_relexed(flag):
    """Control: legacy backticks are NOT a parse-time re-lex path.

    `...` command substitution is deferred — the parser keeps the raw source and
    leaves ``program=None`` (execution re-parses it), so an extglob pattern in a
    backtick body is never re-lexed at parse time. Both parsers agree regardless
    of the extglob flag, and BOTH leave the body unparsed (program is None) — so
    this construct is outside the HIGH-5 re-lex domain by design.
    """
    source = 'echo `echo @(a|b)`'
    rd, pc = _parse_both(source, lexer_options=flag)
    assert _canonical_ast(pc) == _canonical_ast(rd)

    def backtick_programs(root):
        found = []
        seen: set = set()

        def walk(node):
            if id(node) in seen:
                return
            seen.add(id(node))
            if isinstance(node, CommandSubstitution) and node.backtick_style:
                found.append(node.program)
            for name in getattr(node, '__dataclass_fields__', {}):
                child = getattr(node, name)
                if isinstance(child, (list, tuple)):
                    for item in child:
                        if hasattr(item, '__dataclass_fields__'):
                            walk(item)
                elif hasattr(child, '__dataclass_fields__'):
                    walk(child)
            for stmt in getattr(node, 'statements', []):
                walk(stmt)

        walk(root)
        return found

    for ast in (rd, pc):
        programs = backtick_programs(ast)
        assert programs == [None]      # deferred: not eagerly parsed


def test_CARRY_array_init_nested_substitution_still_diverges_on_combinator():
    """CARRY divergence-pin (remediation RULING 2): the ArrayParsers ctx=None
    residual is a SEPARATE, pre-existing combinator seam the HIGH-5 entry fix
    does NOT reach, left in place by ruling.

    ``psh/parser/combinators/arrays.py`` builds array-INITIALIZATION element
    words through the STATIC ``WordBuilder.build_word_from_token`` (bypassing the
    shared ``ExpansionParsers`` that carries the per-call ctx), so an extglob
    pattern in a ``$()`` array element re-lexes WITHOUT extglob and the combinator
    rejects it — while recursive descent (and bash) accept it. Documented at
    ``arrays.py`` as the "ctx=None residual, not chased, for the educational
    combinator".

    This pin FIXES the current divergence: recursive descent parses, the
    combinator raises. It is a FLIP-PIN — if a successor threads ctx into
    ArrayParsers and closes the residual, the combinator will start ACCEPTING and
    THIS TEST GOES RED, signalling the carry is closed (update/retire it then).
    """
    source = 'a=($(echo @(a|b)))'
    inputs = ParseInputs(source_text=source, lexer_options=_EXTGLOB)
    tokens = list(tokenize(source, shell_options=_EXTGLOB))
    # Recursive descent accepts it (matches bash).
    rd = parse_with_inputs(list(tokens), inputs, 'recursive_descent')
    assert len(rd.statements) == 1
    # The combinator still rejects it — the documented ArrayParsers residual.
    with pytest.raises(ParseError):
        parse_with_inputs(list(tokens), inputs, 'combinator')


def test_CARRY_redirect_target_nested_substitution_still_diverges_on_combinator():
    """CARRY divergence-pin #2 (remediation N8): the SAME ArrayParsers seam
    (arrays.py#parse_word_as_word, static WordBuilder, no ctx) also serves
    REDIRECT TARGETS via RedirectionMixin — so the residual's blast radius is
    wider than array initialization. ``echo hi > $(echo @(a|b))`` diverges for
    the same reason: the redirect-target word re-lexes its ``$()`` body without
    extglob on the combinator, so it rejects while recursive descent (and bash)
    accept.

    FLIP-PIN, same as the array-init pin: closing the seam (threading ctx through
    parse_word_as_word) flips BOTH — this test and the array-init one co-flip
    only if the whole seam is threaded at once. Goes RED when the carry closes.
    """
    source = 'echo hi > $(echo @(a|b))'
    inputs = ParseInputs(source_text=source, lexer_options=_EXTGLOB)
    tokens = list(tokenize(source, shell_options=_EXTGLOB))
    rd = parse_with_inputs(list(tokens), inputs, 'recursive_descent')
    assert len(rd.statements) == 1
    with pytest.raises(ParseError):
        parse_with_inputs(list(tokens), inputs, 'combinator')
