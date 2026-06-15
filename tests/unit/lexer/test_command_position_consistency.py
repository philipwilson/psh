"""Drift-lock for the three command-position machines (review Ugly 8).

`psh/lexer/command_position.py` is the SINGLE shared vocabulary for the three
machines that track "command position" — the lexer pass
(`ModularLexer._update_command_position_context`), the keyword normalizer
(`KeywordNormalizer`), and the command-substitution extent scanner
(`cmdsub_scanner`). They deliberately consult DIFFERENT subsets because they
run at different pipeline stages over different alphabets (token types vs
keyword values vs raw text) — see that module's docstring.

A unified `CommandPositionMachine` is intentionally NOT extracted: the
stage-specific differences are irreducible, and the shared classifications
already live in one file. What CAN silently drift is the vocabulary — a new
keyword added to one set but not another, or a documented asymmetry quietly
broken. These tests lock those relationships (the risk the review flagged).
"""

from psh.lexer import tokenize
from psh.lexer.command_position import (
    CMDPOS_KEEPING_WORDS,
    LEXER_COMMAND_POSITION_WORDS,
    RESET_TO_COMMAND_POSITION,
)
from psh.lexer.constants import KEYWORDS
from psh.lexer.keyword_defs import keyword_from_type
from psh.lexer.token_types import TokenType

# Entries of CMDPOS_KEEPING_WORDS that are NOT reserved words: structural
# symbols the scanner sees as raw text, plus `time`/`coproc` (handled
# structurally elsewhere). Documented in command_position.py.
_NON_KEYWORD_KEEPING = frozenset({'{', '}', '!', 'time', 'coproc'})

# The control-structure openers, intermediates, and closers (bash grammar).
_OPENERS = frozenset({'if', 'while', 'until', 'for', 'case'})
_INTERMEDIATES = frozenset({'then', 'do', 'else', 'elif'})
_CLOSERS = frozenset({'fi', 'done', 'esac'})

# Non-keyword entries of RESET_TO_COMMAND_POSITION: the compound-command
# closers `))` and `]]` are operator token types (not reserved words). They
# reset command position so `then`/`do` can follow a `(( ))`/`[[ ]]` condition
# header directly without a separator (`if ((1)) then …`). Documented in
# command_position.py.
_COMPOUND_CLOSER_RESET = frozenset({
    TokenType.DOUBLE_RPAREN, TokenType.DOUBLE_RBRACKET,
})


class TestVocabularyCoherence:
    """Keyword-valued entries across the sets must be real keywords."""

    def test_lexer_words_are_all_keywords(self):
        assert LEXER_COMMAND_POSITION_WORDS <= KEYWORDS

    def test_cmdsub_keeping_words_are_keywords_or_documented_symbols(self):
        keyword_entries = CMDPOS_KEEPING_WORDS - _NON_KEYWORD_KEEPING
        assert keyword_entries <= KEYWORDS, (
            f"non-keyword(s) in CMDPOS_KEEPING_WORDS not in the documented "
            f"symbol allow-list: {keyword_entries - KEYWORDS}")

    def test_reset_types_map_to_keywords(self):
        # The reserved-word reset types map to keywords; the compound closers
        # (`))`/`]]`) are operator types and are exempt.
        for tok_type in RESET_TO_COMMAND_POSITION - _COMPOUND_CLOSER_RESET:
            kw = keyword_from_type(tok_type)
            assert kw in KEYWORDS, f"{tok_type} does not map to a keyword"

    def test_compound_closers_are_reset_types(self):
        # `))` and `]]` reset command position (condition-header-before-then/do).
        assert _COMPOUND_CLOSER_RESET <= RESET_TO_COMMAND_POSITION


class TestDocumentedAsymmetries:
    """The deliberate per-stage differences documented in command_position.py."""

    def test_openers_set_command_position_in_lexer(self):
        # The lexer needs `while [[ -f x ]]` to enable `[[` right after the
        # opener, so every opener is a lexer command-position word.
        assert _OPENERS <= LEXER_COMMAND_POSITION_WORDS

    def test_closers_omitted_from_lexer_words(self):
        # Documented omission: a closer is always followed by a separator (or
        # another closer) in valid syntax, never directly by a command.
        assert not (_CLOSERS & LEXER_COMMAND_POSITION_WORDS)

    def test_reset_types_are_intermediates_and_closers(self):
        reset_words = {keyword_from_type(t)
                       for t in RESET_TO_COMMAND_POSITION - _COMPOUND_CLOSER_RESET}
        # The normalizer (typed stage) resets after intermediates AND closers
        # (plus the two compound-command closers, checked separately).
        assert reset_words == _INTERMEDIATES | _CLOSERS

    def test_intermediates_shared_by_lexer_and_scanner(self):
        assert _INTERMEDIATES <= LEXER_COMMAND_POSITION_WORDS
        assert _INTERMEDIATES <= CMDPOS_KEEPING_WORDS


class TestBehavioralKeywordRecognition:
    """End-to-end: keywords are recognized ONLY at command position, which
    transitively exercises the lexer pass + normalizer agreeing."""

    def _types_for(self, source, value):
        return [t.type for t in tokenize(source) if t.value == value]

    def test_keywords_recognized_at_command_position(self):
        toks = {t.value: t.type for t in tokenize('if true; then echo hi; fi')}
        assert toks['if'] == TokenType.IF
        assert toks['then'] == TokenType.THEN
        assert toks['fi'] == TokenType.FI

    def test_case_recognized_after_command_position_keyword(self):
        # `then case ...` — case directly after an intermediate keyword is a
        # keyword, not a plain word (all three machines agree on this).
        src = 'if x; then case y in a) echo A;; esac; fi'
        assert TokenType.CASE in self._types_for(src, 'case')
        assert TokenType.ESAC in self._types_for(src, 'esac')

    def test_keyword_value_not_at_command_position_stays_word(self):
        # `echo case` — `case` as an argument is NOT a keyword.
        toks = [t for t in tokenize('echo case') if t.value == 'case']
        assert toks and all(t.type == TokenType.WORD for t in toks)

    def test_for_enables_operator_context(self):
        # opener keyword recognized; the `[[` after `while` is an operator.
        toks = {t.type for t in tokenize('while [[ -f x ]]; do :; done')}
        assert TokenType.WHILE in toks
        assert TokenType.DOUBLE_LBRACKET in toks
