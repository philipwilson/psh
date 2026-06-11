"""Unit tests for extglob lexer tokenization."""

from psh.lexer import tokenize
from psh.lexer.token_types import TokenType


class TestExtglobTokenization:
    """Test that extglob patterns are collected as single WORD tokens."""

    def _tokenize_extglob(self, text):
        """Tokenize with extglob enabled."""
        return tokenize(text, shell_options={'extglob': True})

    def _tokenize_no_extglob(self, text):
        """Tokenize without extglob."""
        return tokenize(text, shell_options={'extglob': False})

    def test_at_pattern_single_word(self):
        """@(a|b) should be a single WORD token."""
        tokens = self._tokenize_extglob('echo @(a|b)')
        words = [t for t in tokens if t.type == TokenType.WORD]
        assert len(words) == 2
        assert words[0].value == 'echo'
        assert words[1].value == '@(a|b)'

    def test_question_pattern_single_word(self):
        """?(a|b) should be a single WORD token."""
        tokens = self._tokenize_extglob('echo ?(a|b)')
        words = [t for t in tokens if t.type == TokenType.WORD]
        assert len(words) == 2
        assert words[1].value == '?(a|b)'

    def test_star_pattern_single_word(self):
        """*(a|b) should be a single WORD token."""
        tokens = self._tokenize_extglob('echo *(a|b)')
        words = [t for t in tokens if t.type == TokenType.WORD]
        assert len(words) == 2
        assert words[1].value == '*(a|b)'

    def test_plus_pattern_single_word(self):
        """+(a|b) should be a single WORD token."""
        tokens = self._tokenize_extglob('echo +(a|b)')
        words = [t for t in tokens if t.type == TokenType.WORD]
        assert len(words) == 2
        assert words[1].value == '+(a|b)'

    def test_exclamation_pattern_single_word(self):
        """!(a|b) should be a single WORD token."""
        tokens = self._tokenize_extglob('echo !(a|b)')
        words = [t for t in tokens if t.type == TokenType.WORD]
        assert len(words) == 2
        assert words[1].value == '!(a|b)'

    def test_nested_extglob(self):
        """+(a|*(b|c)) should be a single WORD token."""
        tokens = self._tokenize_extglob('echo +(a|*(b|c))')
        words = [t for t in tokens if t.type == TokenType.WORD]
        assert len(words) == 2
        assert words[1].value == '+(a|*(b|c))'

    def test_extglob_with_prefix(self):
        """file_@(a|b).txt should be a single WORD token."""
        tokens = self._tokenize_extglob('echo file_@(a|b).txt')
        words = [t for t in tokens if t.type == TokenType.WORD]
        assert len(words) == 2
        assert words[1].value == 'file_@(a|b).txt'

    def test_extglob_with_suffix(self):
        """*.+(c|h) should be a single WORD token."""
        tokens = self._tokenize_extglob('echo *.+(c|h)')
        words = [t for t in tokens if t.type == TokenType.WORD]
        assert len(words) == 2
        assert words[1].value == '*.+(c|h)'

    def test_extglob_disabled_breaks_tokens(self):
        """Without extglob, !(a|b) should not be a single WORD.

        When extglob is off, ! should be recognized as EXCLAMATION operator.
        """
        tokens = self._tokenize_no_extglob('!(a|b)')
        # Should tokenize as: EXCLAMATION, LPAREN, WORD, PIPE, WORD, RPAREN
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert TokenType.EXCLAMATION in types

    def test_at_without_extglob_is_word(self):
        """Without extglob, @(a|b) tokenizes differently.

        @ is not a shell operator so it stays as part of a word, but
        the ( and ) would be LPAREN/RPAREN.
        """
        tokens = self._tokenize_no_extglob('echo @(a|b)')
        # The @ won't be collected with the parenthesized group
        values = [t.value for t in tokens if t.type != TokenType.EOF]
        # Should NOT have '@(a|b)' as single token
        assert '@(a|b)' not in values

    def test_multiple_extglob_patterns(self):
        """Multiple extglob patterns in one command."""
        tokens = self._tokenize_extglob('echo @(a|b) +(c|d)')
        words = [t for t in tokens if t.type == TokenType.WORD]
        assert len(words) == 3
        assert words[1].value == '@(a|b)'
        assert words[2].value == '+(c|d)'

    def test_exclamation_not_operator_in_extglob(self):
        """When extglob enabled, !(pattern) should not be EXCLAMATION + subshell."""
        tokens = self._tokenize_extglob('echo !(bad)')
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert TokenType.EXCLAMATION not in types

    def test_regular_exclamation_still_works(self):
        """! without ( should still be EXCLAMATION when extglob enabled."""
        tokens = self._tokenize_extglob('! true')
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert TokenType.EXCLAMATION in types
