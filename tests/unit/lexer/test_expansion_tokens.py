"""Unit tests for enhanced lexer expansion tokens."""

from psh.lexer import tokenize
from psh.lexer.token_types import TokenType


class TestCommandSubstitution:
    """Test command substitution tokenization."""

    def test_simple_command_substitution(self):
        """Test basic $(command) substitution."""
        tokens = tokenize("echo $(date)")

        assert len(tokens) == 3  # echo, $(date), EOF
        assert tokens[0].type == TokenType.WORD
        assert tokens[0].value == "echo"
        assert tokens[1].type == TokenType.COMMAND_SUB
        assert tokens[1].value == "$(date)"

    def test_nested_command_substitution(self):
        """Test nested command substitution."""
        tokens = tokenize("echo $(echo $(date))")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.COMMAND_SUB
        assert tokens[1].value == "$(echo $(date))"
        assert "$(date)" in tokens[1].value

    def test_backtick_substitution(self):
        """Test backtick command substitution."""
        tokens = tokenize("echo `date`")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.COMMAND_SUB_BACKTICK
        assert tokens[1].value == "`date`"

    def test_command_sub_with_quotes(self):
        """Test command substitution with quotes inside."""
        tokens = tokenize('echo $(echo "hello world")')

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.COMMAND_SUB
        assert tokens[1].value == '$(echo "hello world")'

    def test_arithmetic_expansion(self):
        """Test arithmetic expansion $((...))."""
        tokens = tokenize("echo $((2 + 2))")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.ARITH_EXPANSION
        assert tokens[1].value == "$((2 + 2))"


class TestParameterExpansion:
    """Test parameter expansion tokenization."""

    def test_simple_variable(self):
        """Test simple $VAR variable."""
        tokens = tokenize("echo $USER")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.VARIABLE
        assert tokens[1].value == "USER"

    def test_simple_brace_variable(self):
        """Test simple ${VAR} variable."""
        tokens = tokenize("echo ${USER}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.VARIABLE
        assert tokens[1].value == "{USER}"

    def test_param_expansion_default(self):
        """Test parameter expansion with default value."""
        tokens = tokenize("echo ${USER:-nobody}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.PARAM_EXPANSION
        assert tokens[1].value == "${USER:-nobody}"

    def test_param_expansion_assign_default(self):
        """Test parameter expansion with assign default."""
        tokens = tokenize("echo ${USER:=nobody}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.PARAM_EXPANSION
        assert tokens[1].value == "${USER:=nobody}"

    def test_param_expansion_error(self):
        """Test parameter expansion with error."""
        tokens = tokenize("echo ${USER:?User not set}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.PARAM_EXPANSION
        assert tokens[1].value == "${USER:?User not set}"

    def test_param_expansion_alternate(self):
        """Test parameter expansion with alternate value."""
        tokens = tokenize("echo ${USER:+logged in}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.PARAM_EXPANSION
        assert tokens[1].value == "${USER:+logged in}"

    def test_param_expansion_length(self):
        """Test parameter expansion for length."""
        tokens = tokenize("echo ${#USER}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.PARAM_EXPANSION
        assert tokens[1].value == "${#USER}"

    def test_param_expansion_prefix_remove(self):
        """Test parameter expansion with prefix removal."""
        tokens = tokenize("echo ${PATH#/usr}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.PARAM_EXPANSION
        assert tokens[1].value == "${PATH#/usr}"

    def test_param_expansion_suffix_remove(self):
        """Test parameter expansion with suffix removal."""
        tokens = tokenize("echo ${FILE%.txt}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.PARAM_EXPANSION
        assert tokens[1].value == "${FILE%.txt}"

    def test_param_expansion_replace(self):
        """Test parameter expansion with replacement."""
        tokens = tokenize("echo ${PATH/bin/sbin}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.PARAM_EXPANSION
        assert tokens[1].value == "${PATH/bin/sbin}"

    def test_param_expansion_replace_all(self):
        """Test parameter expansion with replace all."""
        tokens = tokenize("echo ${PATH//bin/sbin}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.PARAM_EXPANSION
        assert tokens[1].value == "${PATH//bin/sbin}"


class TestMixedExpansions:
    """Test mixed expansion scenarios."""

    def test_command_sub_in_param_expansion(self):
        """Test command substitution inside parameter expansion."""
        tokens = tokenize("echo ${VAR:-$(date)}")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.PARAM_EXPANSION
        assert tokens[1].value == "${VAR:-$(date)}"
        assert "$(date)" in tokens[1].value

    def test_param_expansion_in_command_sub(self):
        """Test parameter expansion inside command substitution."""
        tokens = tokenize("echo $(echo ${USER})")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.COMMAND_SUB
        assert tokens[1].value == "$(echo ${USER})"
        assert "${USER}" in tokens[1].value

    def test_multiple_expansions(self):
        """Test multiple expansions in one command."""
        tokens = tokenize("echo $USER $(date) ${HOME:-/tmp}")

        assert len(tokens) == 5  # echo, $USER, $(date), ${HOME:-/tmp}, EOF
        assert tokens[1].type == TokenType.VARIABLE
        assert tokens[1].value == "USER"
        assert tokens[2].type == TokenType.COMMAND_SUB
        assert tokens[2].value == "$(date)"
        assert tokens[3].type == TokenType.PARAM_EXPANSION
        assert tokens[3].value == "${HOME:-/tmp}"

    def test_expansions_in_string(self):
        """Test expansions inside double-quoted string."""
        tokens = tokenize('"Hello $USER, today is $(date)"')

        assert len(tokens) == 2  # string, EOF
        assert tokens[0].type == TokenType.STRING
        # The string token should contain the expansions
        assert "$USER" in tokens[0].value
        assert "$(date)" in tokens[0].value

    def test_no_expansion_in_single_quotes(self):
        """Test that single quotes prevent expansion."""
        tokens = tokenize("'$USER $(date) ${HOME}'")

        assert len(tokens) == 2
        assert tokens[0].type == TokenType.STRING
        # Single quotes should preserve literal text
        assert tokens[0].value == "$USER $(date) ${HOME}"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_unclosed_command_sub(self):
        """Test unclosed command substitution."""
        tokens = tokenize("echo $(date")

        # Lexer should still produce tokens
        assert len(tokens) >= 2
        # The second token might be marked as unclosed or error

    def test_unclosed_param_expansion(self):
        """Test unclosed parameter expansion."""
        tokens = tokenize("echo ${USER")

        # Lexer should still produce tokens
        assert len(tokens) >= 2

    def test_empty_command_sub(self):
        """Test empty command substitution."""
        tokens = tokenize("echo $()")

        assert len(tokens) == 3
        assert tokens[1].type == TokenType.COMMAND_SUB
        assert tokens[1].value == "$()"

    def test_empty_param_expansion(self):
        """Test empty parameter expansion."""
        tokens = tokenize("echo ${}")

        # This might be treated as a simple variable or error
        assert len(tokens) >= 2

    def test_dollar_at_end(self):
        """Test dollar sign at end of input."""
        tokens = tokenize("echo $")

        assert len(tokens) == 3
        # The $ should be treated as a literal
        assert tokens[1].value == "$"

    def test_special_variables(self):
        """Test special shell variables."""
        special_vars = ["$?", "$#", "$$", "$!", "$@", "$*", "$-", "$0"]

        for var in special_vars:
            tokens = tokenize(f"echo {var}")
            assert len(tokens) == 3
            assert tokens[1].type == TokenType.VARIABLE
            # The value should be the variable name without $
            assert tokens[1].value == var[1:]
