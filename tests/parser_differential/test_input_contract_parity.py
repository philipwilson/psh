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

  * Space: {command substitution, nested command substitution, process
    substitution, ``${...}`` operand with a nested substitution, composite word,
    double-quoted} x {@, !, *, +, ?} extglob operators, all threaded with
    ``lexer_options={'extglob': True}`` through the one entry. Every case is
    accepted by recursive descent and bash (the corpus is validated green
    against both before it can pin parity).
  * STRUCTURE parity is asserted over the WHOLE canonical AST.
  * LOCATION parity is asserted over NESTED-substitution bodies — the ``.line``
    stamps both parsers set via the shared ``WordBuilder``/``_nested_program``.
    Top-level statement ``.line`` is recursive-descent-only (a pre-existing,
    documented combinator limitation) and is deliberately OUT of scope here.
  * Array-INITIALIZATION elements are OUT of scope: ``ArrayParsers`` builds
    element words through the static ``WordBuilder`` without the per-call ctx (a
    separate, pre-existing combinator residual — see
    ``psh/parser/combinators/arrays.py``), so ``a=($(echo @(a|b)))`` still
    diverges there. That seam is NOT the HIGH-5 entry facade and is unchanged
    by this slot's fix.
"""

import dataclasses
from enum import Enum

import pytest

from psh.ast_nodes import CommandSubstitution, ProcessSubstitution
from psh.lexer import tokenize
from psh.parser import ParseError, ParseInputs, parse_with_inputs

_EXTGLOB = {'extglob': True}

# Extglob operators (bash: @ ! * + ?). The bug is option-sensitive re-lexing of
# a nested substitution body, so every operator must survive the round trip.
_OPERATORS = ('@', '!', '*', '+', '?')

# Construct shapes that re-lex a nested substitution body at parse time. Each
# ``{pat}`` slot is filled with an extglob pattern; the resulting body is what
# the combinator used to re-lex WITHOUT extglob when the entry dropped options.
_SHAPES = (
    ('cmd-sub', 'echo $(echo {pat})'),
    ('cmd-sub-nested', 'echo $(echo $(echo {pat}))'),
    ('process-sub', 'cat <(echo {pat})'),
    ('param-operand-cmd-sub', 'echo ${{x:-$(echo {pat})}}'),
    ('composite-word', 'echo pre$(echo {pat})post'),
    ('double-quoted-cmd-sub', 'echo "$(echo {pat})"'),
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
