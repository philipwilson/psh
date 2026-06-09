"""
Unit tests for lexer pure helper functions.

Tests the pure helper functions used by the lexer - stateless, reusable functions
that handle specific lexing operations like text processing, delimiter matching,
escape handling, and content extraction.
"""

from psh.lexer import pure_helpers
from psh.lexer.constants import SPECIAL_VARIABLES
from psh.token_types import TokenType


class TestTextProcessing:
    """Test basic text processing functions."""


class TestDelimiterMatching:
    """Test delimiter and structure matching functions."""

    def test_find_closing_delimiter_simple(self):
        """Test simple delimiter matching."""
        pos, found = pure_helpers.find_closing_delimiter("(hello)", 1, "(", ")")
        assert found is True
        assert pos == 7

    def test_find_closing_delimiter_nested(self):
        """Test nested delimiter matching."""
        pos, found = pure_helpers.find_closing_delimiter("(hello (world))", 1, "(", ")")
        assert found is True
        assert pos == 15

    def test_find_closing_delimiter_unclosed(self):
        """Test unclosed delimiter handling."""
        pos, found = pure_helpers.find_closing_delimiter("(hello", 1, "(", ")")
        assert found is False
        assert pos == 6

    def test_find_closing_delimiter_with_quotes(self):
        """Test delimiter matching with quotes."""
        pos, found = pure_helpers.find_closing_delimiter('(echo "hello)")', 1, "(", ")")
        assert found is True
        assert pos == 15  # Should ignore ) inside quotes

    def test_find_closing_delimiter_with_escapes(self):
        """Test delimiter matching with escape sequences."""
        pos, found = pure_helpers.find_closing_delimiter("(echo \\))", 1, "(", ")", track_escapes=True)
        assert found is True
        assert pos == 9  # Should ignore escaped )

    def test_find_closing_delimiter_multi_char(self):
        """Test matching with multi-character delimiters."""
        pos, found = pure_helpers.find_closing_delimiter("$((2 + 3))", 3, "(", "))", track_quotes=False)
        assert found is True
        assert pos == 10

    def test_find_balanced_parentheses_simple(self):
        """Test simple balanced parentheses."""
        pos, found = pure_helpers.find_balanced_parentheses("echo hello)", 0)
        assert found is True
        assert pos == 11

    def test_find_balanced_parentheses_nested(self):
        """Test nested balanced parentheses."""
        pos, found = pure_helpers.find_balanced_parentheses("echo (nested) command)", 0)
        assert found is True
        assert pos == 22

    def test_find_balanced_double_parentheses(self):
        """Test double parentheses for arithmetic expansion."""
        pos, found = pure_helpers.find_balanced_double_parentheses("2 + (3 * 4)))", 0)
        assert found is True
        assert pos == 13  # Should find )) at positions 11-12, so end at 13

    def test_validate_brace_expansion_simple(self):
        """Test simple brace expansion validation."""
        content, pos, found = pure_helpers.validate_brace_expansion("var}", 0)
        assert content == "var"
        assert pos == 4
        assert found is True

    def test_validate_brace_expansion_nested(self):
        """Test nested brace expansion validation."""
        content, pos, found = pure_helpers.validate_brace_expansion("var{inner}}", 0)
        assert content == "var{inner}"
        assert pos == 11
        assert found is True

    def test_validate_brace_expansion_unclosed(self):
        """Test unclosed brace expansion handling."""
        content, pos, found = pure_helpers.validate_brace_expansion("var", 0)
        assert content == "var"
        assert pos == 3
        assert found is False


class TestEscapeSequenceHandling:
    """Test escape sequence processing functions."""

    def test_handle_escape_outside_quotes(self):
        """Test escape sequences outside quotes."""
        escaped, pos = pure_helpers.handle_escape_sequence("\\n", 0, None)
        assert escaped == "n"
        assert pos == 2

        escaped, pos = pure_helpers.handle_escape_sequence("\\$", 0, None)
        assert escaped == "$"  # Escaped dollar is literal $
        assert pos == 2

    def test_handle_escape_in_double_quotes(self):
        """Test escape sequences in double quotes."""
        # In bash, \n is NOT converted in double quotes - it stays literal
        escaped, pos = pure_helpers.handle_escape_sequence("\\n", 0, '"')
        assert escaped == "\\n"  # Should stay literal in double quotes
        assert pos == 2

        escaped, pos = pure_helpers.handle_escape_sequence('\\"', 0, '"')
        assert escaped == '"'
        assert pos == 2

        escaped, pos = pure_helpers.handle_escape_sequence("\\$", 0, '"')
        assert escaped == "\\$"  # Should preserve backslash
        assert pos == 2

    def test_handle_escape_in_single_quotes(self):
        """Test escape sequences in single quotes."""
        escaped, pos = pure_helpers.handle_escape_sequence("\\n", 0, "'")
        assert escaped == "\\n"  # Should preserve literal backslash
        assert pos == 2

    def test_handle_escape_line_continuation(self):
        """Test line continuation with escaped newline."""
        escaped, pos = pure_helpers.handle_escape_sequence("\\\n", 0, None)
        assert escaped == ""  # Should be removed
        assert pos == 2

        escaped, pos = pure_helpers.handle_escape_sequence("\\\n", 0, '"')
        assert escaped == ""  # Should be removed in double quotes too
        assert pos == 2

    def test_handle_escape_end_of_input(self):
        """Test escape sequence at end of input."""
        escaped, pos = pure_helpers.handle_escape_sequence("\\", 0, None)
        assert escaped == "\\"
        assert pos == 1


class TestQuoteProcessing:
    """Test quote content extraction functions."""

    def test_extract_quoted_content_double_quotes(self):
        """Test double-quoted content extraction."""
        content, pos, found = pure_helpers.extract_quoted_content('hello world"', 0, '"')
        assert content == "hello world"
        assert pos == 12
        assert found is True

    def test_extract_quoted_content_single_quotes(self):
        """Test single-quoted content extraction."""
        content, pos, found = pure_helpers.extract_quoted_content("hello'", 0, "'", allow_escapes=False)
        assert content == "hello"
        assert pos == 6
        assert found is True

    def test_extract_quoted_content_with_escapes(self):
        """Test quoted content extraction with escape sequences."""
        content, pos, found = pure_helpers.extract_quoted_content('hello\\"world"', 0, '"')
        assert content == 'hello"world'
        assert pos == 13
        assert found is True

    def test_extract_quoted_content_unclosed(self):
        """Test unclosed quoted string handling."""
        content, pos, found = pure_helpers.extract_quoted_content("hello", 0, '"')
        assert content == "hello"
        assert pos == 5
        assert found is False

    def test_extract_quoted_content_empty(self):
        """Test empty quoted string."""
        content, pos, found = pure_helpers.extract_quoted_content('"', 0, '"')
        assert content == ""
        assert pos == 1
        assert found is True


class TestVariableNameExtraction:
    """Test variable name extraction functions."""

    def test_extract_variable_name_simple(self):
        """Test simple variable name extraction."""
        name, pos = pure_helpers.extract_variable_name("var", 0, SPECIAL_VARIABLES)
        assert name == "var"
        assert pos == 3

    def test_extract_variable_name_special(self):
        """Test special single-character variable extraction."""
        name, pos = pure_helpers.extract_variable_name("$", 0, SPECIAL_VARIABLES)
        assert name == "$"
        assert pos == 1

        name, pos = pure_helpers.extract_variable_name("?", 0, SPECIAL_VARIABLES)
        assert name == "?"
        assert pos == 1

    def test_extract_variable_name_with_numbers(self):
        """Test variable names containing numbers."""
        name, pos = pure_helpers.extract_variable_name("var123", 0, SPECIAL_VARIABLES)
        assert name == "var123"
        assert pos == 6

    def test_extract_variable_name_special_sequence(self):
        """Test extraction from sequence of special characters."""
        # Use a character that's not in SPECIAL_VARIABLES
        name, pos = pure_helpers.extract_variable_name("@#$", 1, SPECIAL_VARIABLES)  # Start at '#'
        assert name == "#"  # '#' is a special variable
        assert pos == 2

    def test_extract_variable_name_underscore_start(self):
        """Test variable starting with underscore."""
        name, pos = pure_helpers.extract_variable_name("_var", 0, SPECIAL_VARIABLES)
        assert name == "_var"
        assert pos == 4


class TestCommentDetection:
    """Test comment detection functions."""

    def test_is_comment_start_at_line_start(self):
        """Test comment detection at start of line."""
        assert pure_helpers.is_comment_start("#comment", 0) is True

    def test_is_comment_start_after_whitespace(self):
        """Test comment detection after whitespace."""
        assert pure_helpers.is_comment_start("echo #comment", 5) is True

    def test_is_comment_start_after_operator(self):
        """Test comment detection after operator."""
        assert pure_helpers.is_comment_start("cmd; #comment", 5) is True

    def test_is_comment_start_invalid_context(self):
        """Test # that's not a comment start."""
        assert pure_helpers.is_comment_start("var#not", 3) is False

    def test_is_comment_start_wrong_character(self):
        """Test non-# character for comment detection."""
        assert pure_helpers.is_comment_start("hello", 0) is False


class TestOperatorRecognition:
    """Test operator recognition functions."""


class TestExpansionDetection:
    """Test expansion context detection functions."""

    def test_is_inside_expansion_arithmetic(self):
        """Test position detection inside arithmetic expansion."""
        # Position 5 is inside $((2+3))
        assert pure_helpers.is_inside_expansion("$((2+3))", 5) is True
        assert pure_helpers.is_inside_expansion("$((2+3))", 8) is False

    def test_is_inside_expansion_command_substitution(self):
        """Test position detection inside command substitution."""
        # Position 3 is inside $(echo)
        assert pure_helpers.is_inside_expansion("$(echo)", 3) is True
        assert pure_helpers.is_inside_expansion("$(echo)", 7) is False

    def test_is_inside_expansion_backticks(self):
        """Test position detection inside backtick substitution."""
        # Position 2 is inside `cmd`
        assert pure_helpers.is_inside_expansion("`cmd`", 2) is True
        assert pure_helpers.is_inside_expansion("`cmd`", 5) is False

    def test_is_inside_expansion_outside(self):
        """Test position detection outside any expansions."""
        assert pure_helpers.is_inside_expansion("echo hello", 5) is False
        assert pure_helpers.is_inside_expansion("$var", 2) is False


class TestPureFunctionIntegration:
    """Integration tests for pure functions working together."""

    def test_complex_parsing_scenario(self):
        """Test complex parsing scenario using multiple pure functions."""
        input_text = 'echo "hello $(echo world)" | grep test'

        # Extract the quoted content
        content, end_pos, found = pure_helpers.extract_quoted_content(
            input_text, 6, '"', allow_escapes=True
        )
        assert content == "hello $(echo world)"
        assert found is True

    def test_nested_structures_parsing(self):
        """Test parsing of nested expansion structures."""
        input_text = "$((2 + $(echo 3)))"

        # Should detect we're inside expansions at various positions
        assert pure_helpers.is_inside_expansion(input_text, 5) is True   # Inside arithmetic
        assert pure_helpers.is_inside_expansion(input_text, 12) is True  # Inside command sub
        assert pure_helpers.is_inside_expansion(input_text, 18) is False # After everything

    def test_error_recovery_scenarios(self):
        """Test error recovery with unclosed structures."""
        # Test unclosed parentheses
        pos, found = pure_helpers.find_balanced_parentheses("echo (hello", 5)
        assert found is False
        assert pos == 11

        # Test unclosed quotes
        content, pos, found = pure_helpers.extract_quoted_content("hello", 0, '"')
        assert found is False
        assert content == "hello"

    def test_escape_and_quote_interaction(self):
        """Test interaction between escape handling and quote processing."""
        # Test escaped quote within quotes
        content, pos, found = pure_helpers.extract_quoted_content('test\\"value"', 0, '"')
        assert content == 'test"value'
        assert found is True
        assert pos == 12

    def test_variable_name_boundary_detection(self):
        """Test variable name extraction with boundary detection."""
        # Extract variable name and then find word boundary
        name, var_end = pure_helpers.extract_variable_name("var123_test", 0, SPECIAL_VARIABLES)
        assert name == "var123_test"

    def test_comment_and_operator_interaction(self):
        """Test comment detection in operator-adjacent positions."""
        text = "cmd; # comment with | pipe"

        # Should detect comment start
        assert pure_helpers.is_comment_start(text, 5) is True
