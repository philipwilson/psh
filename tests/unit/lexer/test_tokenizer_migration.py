"""
Migrated tokenizer tests from tests/test_tokenizer.py.

These tests focus on comprehensive tokenization scenarios beyond
the basic tests in test_basic_tokenization.py.
"""

import sys
from pathlib import Path

import pytest

# Add PSH to path
PSH_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PSH_ROOT))

from psh.lexer import tokenize
from psh.lexer.token_types import TokenType


class TestTokenizerMigration:
    """Migrated tests from the original test_tokenizer.py."""

    def test_simple_command(self):
        tokens = list(tokenize("ls -la"))
        assert len(tokens) == 3  # ls, -la, EOF
        assert tokens[0].type == TokenType.WORD
        assert tokens[0].value == "ls"
        assert tokens[1].type == TokenType.WORD
        assert tokens[1].value == "-la"
        assert tokens[2].type == TokenType.EOF

    def test_pipe(self):
        tokens = list(tokenize("cat file | grep pattern"))
        assert len(tokens) == 6  # cat, file, |, grep, pattern, EOF
        assert tokens[2].type == TokenType.PIPE
        assert tokens[2].value == "|"

    def test_redirections(self):
        # Input redirection
        tokens = list(tokenize("cat < input.txt"))
        assert tokens[1].type == TokenType.REDIRECT_IN
        assert tokens[1].value == "<"

        # Output redirection
        tokens = list(tokenize("echo hello > output.txt"))
        assert tokens[2].type == TokenType.REDIRECT_OUT
        assert tokens[2].value == ">"

        # Append redirection
        tokens = list(tokenize("echo world >> output.txt"))
        assert tokens[2].type == TokenType.REDIRECT_APPEND
        assert tokens[2].value == ">>"

    def test_semicolon(self):
        tokens = list(tokenize("echo first; echo second"))
        assert tokens[2].type == TokenType.SEMICOLON
        assert tokens[2].value == ";"

    def test_ampersand(self):
        tokens = list(tokenize("sleep 10 &"))
        assert tokens[2].type == TokenType.AMPERSAND
        assert tokens[2].value == "&"

    def test_newline(self):
        tokens = list(tokenize("echo hello\necho world"))
        assert tokens[2].type == TokenType.NEWLINE
        assert tokens[2].value == "\n"

    def test_quoted_strings(self):
        # Single quotes
        tokens = list(tokenize("echo 'hello world'"))
        assert tokens[1].type == TokenType.STRING
        assert tokens[1].value == "hello world"

        # Double quotes
        tokens = list(tokenize('echo "hello world"'))
        assert tokens[1].type == TokenType.STRING
        assert tokens[1].value == "hello world"

        # Escaped quotes
        tokens = list(tokenize('echo "hello \\"world\\""'))
        assert tokens[1].type == TokenType.STRING
        assert tokens[1].value == 'hello "world"'

    def test_variables(self):
        tokens = list(tokenize("echo $HOME $USER"))
        assert tokens[1].type == TokenType.VARIABLE
        assert tokens[1].value == "HOME"
        assert tokens[2].type == TokenType.VARIABLE
        assert tokens[2].value == "USER"

    def test_brace_expansion_variables(self):
        # Simple brace expansion
        tokens = list(tokenize("echo ${HOME}"))
        assert tokens[1].type == TokenType.VARIABLE
        assert tokens[1].value == "{HOME}"

        # Parameter expansion with default — braced ${...} emits one VARIABLE
        # token (value {...}); the parser's WordBuilder classifies it.
        tokens = list(tokenize("echo ${FOO:-default}"))
        assert tokens[1].type == TokenType.VARIABLE
        assert tokens[1].value == "{FOO:-default}"

        # Multiple variables
        tokens = list(tokenize("echo ${VAR1} ${VAR2}"))
        assert tokens[1].type == TokenType.VARIABLE
        assert tokens[1].value == "{VAR1}"
        assert tokens[2].type == TokenType.VARIABLE
        assert tokens[2].value == "{VAR2}"

        # Concatenation (tokenizer splits this)
        tokens = list(tokenize("echo ${PREFIX}suffix"))
        assert tokens[1].type == TokenType.VARIABLE
        assert tokens[1].value == "{PREFIX}"
        assert tokens[2].type == TokenType.WORD
        assert tokens[2].value == "suffix"

    def test_whitespace_handling(self):
        tokens = list(tokenize("  echo   hello   "))
        assert len(tokens) == 3  # echo, hello, EOF
        assert tokens[0].value == "echo"
        assert tokens[1].value == "hello"

    def test_empty_input(self):
        tokens = list(tokenize(""))
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

        # Whitespace only - PSH may include NEWLINE tokens
        tokens = list(tokenize("   "))
        assert tokens[-1].type == TokenType.EOF

    def test_complex_command(self):
        tokens = list(tokenize("cat < in.txt | grep -v error | sort > out.txt &"))
        expected_types = [
            TokenType.WORD,           # cat
            TokenType.REDIRECT_IN,    # <
            TokenType.WORD,           # in.txt
            TokenType.PIPE,           # |
            TokenType.WORD,           # grep
            TokenType.WORD,           # -v
            TokenType.WORD,           # error
            TokenType.PIPE,           # |
            TokenType.WORD,           # sort
            TokenType.REDIRECT_OUT,   # >
            TokenType.WORD,           # out.txt
            TokenType.AMPERSAND,      # &
            TokenType.EOF
        ]

        assert len(tokens) == len(expected_types)
        for token, expected_type in zip(tokens, expected_types):
            assert token.type == expected_type

    def test_position_tracking(self):
        tokens = list(tokenize("echo hello"))
        assert tokens[0].position == 0  # echo starts at 0
        assert tokens[1].position == 5  # hello starts at 5

    def test_unclosed_quote_error(self):
        with pytest.raises(SyntaxError, match="Unclosed"):
            list(tokenize('echo "hello world'))

        with pytest.raises(SyntaxError, match="Unclosed"):
            list(tokenize("echo 'hello world"))

    def test_escaped_characters_in_words(self):
        # Note: PSH's ModularLexer preserves escape sequences in token values

        # Escaped spaces
        tokens = list(tokenize(r"echo hello\ world"))
        assert len(tokens) == 3  # echo, hello\ world, EOF
        # ModularLexer keeps the backslash in the token value
        assert tokens[1].value == "hello\\ world"

        # Escaped special characters
        tokens = list(tokenize(r"echo \$HOME"))
        assert tokens[1].type == TokenType.WORD
        # ModularLexer keeps the backslash
        assert tokens[1].value == "\\$HOME"

        # Escaped glob characters
        tokens = list(tokenize(r"echo \*.txt"))
        # ModularLexer keeps the backslash
        assert tokens[1].value == "\\*.txt"


class TestAdvancedTokenization:
    """Additional advanced tokenization tests."""

    def test_heredoc_tokens(self):
        """Test heredoc operator tokenization."""
        tokens = list(tokenize("cat << EOF"))
        assert any(t.type == TokenType.HEREDOC for t in tokens)

        # Strip tabs variant
        tokens = list(tokenize("cat <<- EOF"))
        assert any(t.type == TokenType.HEREDOC_STRIP for t in tokens)

    def test_logical_operators(self):
        """Test && and || operators."""
        tokens = list(tokenize("true && echo success"))
        assert any(t.type == TokenType.AND_AND for t in tokens)

        tokens = list(tokenize("false || echo failure"))
        assert any(t.type == TokenType.OR_OR for t in tokens)

    def test_parentheses(self):
        """Test parentheses tokenization."""
        tokens = list(tokenize("(echo hello)"))
        assert tokens[0].type == TokenType.LPAREN
        assert tokens[3].type == TokenType.RPAREN

    def test_command_substitution(self):
        """Test command substitution tokens."""
        # Modern $() form
        tokens = list(tokenize("echo $(date)"))
        assert any(t.type == TokenType.COMMAND_SUB for t in tokens)

        # Legacy backtick form
        tokens = list(tokenize("echo `date`"))
        assert any(t.type == TokenType.COMMAND_SUB_BACKTICK for t in tokens)

    def test_arithmetic_expansion(self):
        """Test arithmetic expansion tokens."""
        tokens = list(tokenize("echo $((2 + 2))"))
        assert any(t.type == TokenType.ARITH_EXPANSION for t in tokens)

    def test_keywords(self):
        """Test shell keyword tokenization."""
        # Keywords are recognized by KeywordNormalizer at command position.
        # Most keywords are recognized when they appear alone (command position
        # defaults to True). 'in' is context-sensitive: only recognized after
        # for/case/select.
        keyword_map = {
            "if": TokenType.IF,
            "then": TokenType.THEN,
            "else": TokenType.ELSE,
            "fi": TokenType.FI,
            "while": TokenType.WHILE,
            "do": TokenType.DO,
            "done": TokenType.DONE,
            "for": TokenType.FOR,
        }

        for kw, expected_type in keyword_map.items():
            tokens = list(tokenize(kw))
            assert tokens[0].type == expected_type
            assert tokens[0].value == kw

        # 'in' is only a keyword after for/case/select
        tokens = list(tokenize("in"))
        assert tokens[0].type == TokenType.WORD

        # Verify 'in' IS recognized as keyword in proper context
        tokens = list(tokenize("for x in a; do echo; done"))
        in_tokens = [t for t in tokens if t.value == 'in']
        assert len(in_tokens) == 1
        assert in_tokens[0].type == TokenType.IN

    def test_special_parameters(self):
        """Test special parameter variables."""
        special_vars = ["$@", "$*", "$#", "$$", "$?", "$!", "$0", "$-"]
        for var in special_vars:
            tokens = list(tokenize(f"echo {var}"))
            assert tokens[1].type == TokenType.VARIABLE
            # PSH strips the $ prefix
            assert tokens[1].value == var[1:]

    def test_file_descriptor_redirects(self):
        """Test file descriptor redirections."""
        # Standard error redirect: 2> is a single REDIRECT_OUT with fd=2
        tokens = list(tokenize("cmd 2> errors.txt"))
        redirect = next(t for t in tokens if t.type == TokenType.REDIRECT_OUT)
        assert redirect.value == ">"
        assert redirect.fd == 2

        # Redirect and duplicate - PSH tokenizes this as a single token
        tokens = list(tokenize("cmd 2>&1"))
        assert any(t.type == TokenType.REDIRECT_DUP and t.value == "2>&1" for t in tokens)

    def test_here_string(self):
        """Test here-string operator."""
        tokens = list(tokenize("cat <<< 'hello world'"))
        assert any(t.type == TokenType.HERE_STRING for t in tokens)
