"""Preservation locks for the explicit lexical-state machine (Phase A / R1).

Phase A replaced the lexer's ad-hoc command-position + case booleans with an
explicit :class:`~psh.lexer.state_context.LexicalState` (command-position axis
as a :class:`~psh.lexer.state_context.LexicalRole`, case phase as independent
flags) whose single mutator is
:func:`~psh.lexer.command_position.advance_lexical_state` — the ONE lexer-stage
transition function. This is a PURE-PRESERVATION refactor: the frozen token
corpus (test_lexer_stream_corpus.py) and the whole suite lock end-to-end token
identity. These tests pin the state machine *directly* (new surface) so the
transition rules and their subtleties stay documented and locked.

Key subtlety pinned here: ``case_expecting_in`` and ``in_case_pattern`` are
INDEPENDENT bits — a malformed ``case x ;;`` sets both at once — so they are
NOT collapsible into a single mutually-exclusive phase enum. See
test_expecting_in_and_pattern_are_independent.
"""

import pytest

from psh.lexer import ModularLexer, tokenize, tokenize_with_heredocs
from psh.lexer.command_position import advance_lexical_state
from psh.lexer.position import LexerConfig
from psh.lexer.state_context import (
    CasePhase,
    LexerContext,
    LexicalRole,
    LexicalState,
)
from psh.lexer.token_types import TokenType

W = TokenType.WORD


def drive(*events, state=None):
    """Apply a sequence of (token_type, value) events to a fresh state."""
    if state is None:
        state = LexicalState()
    for ev in events:
        if isinstance(ev, tuple):
            token_type, value = ev
        else:
            token_type, value = ev, ''
        advance_lexical_state(state, token_type, value)
    return state


# --------------------------------------------------------------------------
# LexicalState representation & derived properties
# --------------------------------------------------------------------------

class TestRepresentation:
    def test_default_is_command_position(self):
        s = LexicalState()
        assert s.role is LexicalRole.COMMAND_POSITION
        assert s.command_position is True
        assert s.case_phase is CasePhase.NOT_IN_CASE

    def test_constructed_not_command_is_argument_role(self):
        s = LexicalState(command_position=False)
        assert s.role is LexicalRole.ARGUMENT
        assert s.command_position is False

    def test_command_position_setter_updates_role(self):
        s = LexicalState()
        s.command_position = False
        assert s.role is LexicalRole.ARGUMENT
        s.command_position = True
        assert s.role is LexicalRole.COMMAND_POSITION

    def test_set_reset_helpers(self):
        s = LexicalState()
        s.reset_command_position()
        assert s.command_position is False
        s.set_command_position()
        assert s.command_position is True

    def test_lexercontext_is_alias(self):
        assert LexerContext is LexicalState

    def test_backward_compat_construction_kwargs(self):
        s = LexerContext(command_position=False, bracket_depth=2,
                         arithmetic_depth=1, posix_mode=True)
        assert s.command_position is False
        assert s.bracket_depth == 2
        assert s.arithmetic_depth == 1
        assert s.posix_mode is True

    def test_case_phase_expecting_in(self):
        s = LexicalState(case_depth=1, case_expecting_in=True)
        assert s.case_phase is CasePhase.EXPECTING_IN

    def test_case_phase_pattern(self):
        s = LexicalState(case_depth=1, in_case_pattern=True)
        assert s.case_phase is CasePhase.PATTERN

    def test_case_phase_body(self):
        s = LexicalState(case_depth=1)
        assert s.case_phase is CasePhase.BODY

    def test_case_phase_precedence_when_degenerate(self):
        # Both bits set (reachable on malformed input): the derived view has a
        # fixed precedence; the stored flags remain authoritative.
        s = LexicalState(case_depth=1, case_expecting_in=True,
                         in_case_pattern=True)
        assert s.case_phase is CasePhase.EXPECTING_IN
        assert s.case_expecting_in is True
        assert s.in_case_pattern is True


# --------------------------------------------------------------------------
# Transition function — command position axis
# --------------------------------------------------------------------------

class TestCommandPositionTransitions:
    def test_initial_state_is_command_position(self):
        assert LexicalState().command_position is True

    @pytest.mark.parametrize("tok", [
        TokenType.SEMICOLON, TokenType.AMPERSAND, TokenType.NEWLINE,
        TokenType.AND_AND, TokenType.OR_OR, TokenType.PIPE, TokenType.PIPE_AND,
    ])
    def test_separator_sets_command_position(self, tok):
        # Argument first (reset), then a separator restores command position.
        s = drive((W, 'echo'), tok)
        assert s.command_position is True

    @pytest.mark.parametrize("tok", [TokenType.LPAREN, TokenType.LBRACE])
    def test_group_openers_set_command_position(self, tok):
        s = drive((W, 'echo'), tok)
        assert s.command_position is True

    @pytest.mark.parametrize("tok", [TokenType.EXCLAMATION, TokenType.TIME])
    def test_pipeline_prefix_sets_command_position(self, tok):
        s = drive((W, 'echo'), tok)
        assert s.command_position is True

    def test_argument_word_resets_command_position(self):
        s = drive((W, 'echo'))
        assert s.command_position is False

    @pytest.mark.parametrize("tok", [
        TokenType.REDIRECT_IN, TokenType.REDIRECT_OUT, TokenType.REDIRECT_APPEND,
        TokenType.HEREDOC, TokenType.HEREDOC_STRIP, TokenType.HERE_STRING,
    ])
    def test_redirections_are_neutral(self, tok):
        # A redirection before a command keeps the following word at command
        # position: it does not change the axis.
        assert drive(tok).command_position is True
        assert drive((W, 'echo'), tok).command_position is False

    def test_rparen_sets_command_position_outside_brackets(self):
        s = drive((W, 'echo'), TokenType.RPAREN)
        assert s.command_position is True

    def test_rparen_neutral_inside_double_brackets(self):
        # Inside [[ ]] a ) is part of the operand and must NOT flip to command
        # position (else the following [[ mis-lexes as DOUBLE_LBRACKET).
        s = drive(TokenType.DOUBLE_LBRACKET, (W, 'x'), TokenType.RPAREN)
        assert s.command_position is False


# --------------------------------------------------------------------------
# Transition function — nesting depths
# --------------------------------------------------------------------------

class TestDepthTransitions:
    def test_double_bracket_depth(self):
        s = drive(TokenType.DOUBLE_LBRACKET)
        assert s.bracket_depth == 1
        s = drive(TokenType.DOUBLE_LBRACKET, TokenType.DOUBLE_RBRACKET)
        assert s.bracket_depth == 0

    def test_double_paren_counts_two(self):
        s = drive(TokenType.DOUBLE_LPAREN)
        assert s.arithmetic_depth == 2

    def test_single_paren_inside_arith(self):
        s = drive(TokenType.DOUBLE_LPAREN, TokenType.LPAREN)
        assert s.arithmetic_depth == 3
        s = drive(TokenType.DOUBLE_LPAREN, TokenType.LPAREN, TokenType.RPAREN)
        assert s.arithmetic_depth == 2

    def test_arith_depth_floored_at_zero(self):
        s = drive(TokenType.DOUBLE_RPAREN)
        assert s.arithmetic_depth == 0

    def test_single_paren_outside_arith_ignored(self):
        # Outside arithmetic, a plain ( does not touch arithmetic_depth.
        s = drive(TokenType.LPAREN)
        assert s.arithmetic_depth == 0


# --------------------------------------------------------------------------
# Transition function — case FSM
# --------------------------------------------------------------------------

class TestCaseTransitions:
    def test_case_opens_expecting_in(self):
        s = drive((W, 'case'))
        assert s.case_depth == 1
        assert s.case_expecting_in is True

    def test_case_as_argument_does_not_open(self):
        # `case` not at command position (an argument) must not open case state.
        s = drive((W, 'echo'), (W, 'case'))
        assert s.case_depth == 0
        assert s.case_expecting_in is False

    def test_in_enters_pattern(self):
        s = drive((W, 'case'), (W, 'x'), (W, 'in'))
        assert s.case_expecting_in is False
        assert s.in_case_pattern is True

    def test_esac_closes_case(self):
        s = drive((W, 'case'), (W, 'x'), (W, 'in'), (W, 'esac'))
        assert s.case_depth == 0
        assert s.in_case_pattern is False

    def test_rparen_closes_pattern_to_body(self):
        s = drive((W, 'case'), (W, 'x'), (W, 'in'), (W, 'a'), TokenType.RPAREN)
        assert s.in_case_pattern is False
        assert s.case_phase is CasePhase.BODY

    def test_terminator_returns_to_pattern(self):
        s = drive((W, 'case'), (W, 'x'), (W, 'in'), (W, 'a'), TokenType.RPAREN,
                  (W, 'echo'), TokenType.DOUBLE_SEMICOLON)
        assert s.in_case_pattern is True

    def test_nested_case_depth(self):
        s = drive((W, 'case'), (W, 'x'), (W, 'in'), (W, 'a'), TokenType.RPAREN,
                  (W, 'case'), (W, 'y'), (W, 'in'))
        assert s.case_depth == 2

    def test_expecting_in_and_pattern_are_independent(self):
        # The load-bearing subtlety: a malformed `case x ;;` (terminator before
        # `in`) leaves BOTH bits set. This is why the case dimension is stored
        # as independent flags, not a single mutually-exclusive phase enum.
        s = drive((W, 'case'), (W, 'x'), TokenType.DOUBLE_SEMICOLON)
        assert s.case_expecting_in is True
        assert s.in_case_pattern is True


# --------------------------------------------------------------------------
# copy() / heredoc cross-command carry (v0.648 interaction)
# --------------------------------------------------------------------------

class TestCopyAndCarry:
    def test_copy_carries_all_semantic_fields(self):
        s = LexicalState(command_position=False, bracket_depth=2,
                         arithmetic_depth=3, case_depth=1,
                         case_expecting_in=True, in_case_pattern=True,
                         posix_mode=True)
        c = s.copy()
        assert c.command_position is False
        assert c.bracket_depth == 2
        assert c.arithmetic_depth == 3
        assert c.case_depth == 1
        assert c.case_expecting_in is True
        assert c.in_case_pattern is True
        assert c.posix_mode is True

    def test_copy_drops_assignment_cache(self):
        s = LexicalState(assignment_map_cache=("abc", bytearray(3)))
        assert s.copy().assignment_map_cache is None

    def test_initial_context_command_position_seeds_operator(self):
        # A lexer seeded AT command position recognizes `[[` as the test
        # operator — the lexer-level observable of the carried role. (Keyword
        # promotion is a later normalizer pass, not visible here.)
        seed = LexicalState(command_position=True)
        toks = ModularLexer('[[ x', config=LexerConfig(),
                            initial_context=seed.copy()).tokenize()
        assert toks[0].type is TokenType.DOUBLE_LBRACKET

    def test_initial_context_argument_position_disables_operator(self):
        # Seeded at argument position, `[[` is NOT the test operator (mirrors a
        # mid-command continuation line).
        seed = LexicalState(command_position=False)
        toks = ModularLexer('[[ x', config=LexerConfig(),
                            initial_context=seed.copy()).tokenize()
        assert toks[0].type is not TokenType.DOUBLE_LBRACKET
        assert toks[0].value == '[['

    def test_heredoc_carry_case_across_lines(self):
        # A case arm whose body contains a multi-line heredoc: the incremental
        # heredoc driver carries LexicalState across command boundaries via
        # copy()/initial_context. The case structure must tokenize correctly
        # (CASE/IN/ESAC recognized) and the heredoc body must be collected out
        # of the token stream, not left as WORD tokens.
        script = "case x in\n  a) cat <<EOF\nbody\nEOF\n  ;;\nesac\n"
        toks, hmap = tokenize_with_heredocs(script)
        types = [t.type for t in toks]
        assert TokenType.CASE in types
        assert TokenType.IN in types
        assert TokenType.ESAC in types
        assert 'body' not in [t.value for t in toks]
        assert any(entry.collected.body == 'body\n' for entry in hmap.values())


# --------------------------------------------------------------------------
# D1 residual — for/select/case SUBJECT positions (token-level, vs the corpus
# these are already all-green; pinned here as explicit named rows)
# --------------------------------------------------------------------------

class TestSubjectPositions:
    def _types(self, text):
        return [(t.type, t.value) for t in tokenize(text)]

    def test_case_subject_in_stays_word(self):
        # `case in in in) ...` — the subject `in` is a WORD, not the IN keyword;
        # only the second `in` (the case keyword) is IN.
        types = self._types("case in in in) echo hi;; esac")
        # first three words: CASE, then subject WORD 'in', then IN keyword
        assert types[0] == (TokenType.CASE, 'case')
        assert types[1] == (TokenType.WORD, 'in')
        assert types[2] == (TokenType.IN, 'in')

    def test_for_subject_in_stays_word(self):
        types = self._types("for in in a b; do echo; done")
        assert types[0] == (TokenType.FOR, 'for')
        assert types[1] == (TokenType.WORD, 'in')
        assert types[2] == (TokenType.IN, 'in')

    def test_select_subject_in_stays_word(self):
        types = self._types("select in in a b; do break; done")
        assert types[0] == (TokenType.SELECT, 'select')
        assert types[1] == (TokenType.WORD, 'in')
        assert types[2] == (TokenType.IN, 'in')

    def test_case_subject_keyword_spelled_stays_word(self):
        # `case if in if) ...` — subject spelled `if` is a WORD subject.
        types = self._types("case if in if) echo hit;; esac")
        assert types[0] == (TokenType.CASE, 'case')
        assert types[1] == (TokenType.WORD, 'if')
