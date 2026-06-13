"""Test expansion AST nodes."""

from psh.ast_nodes import (
    ArithmeticExpansion,
    CommandSubstitution,
    ExpansionPart,
    LiteralPart,
    ParameterExpansion,
    VariableExpansion,
    Word,
)
from psh.lexer.token_types import Token, TokenType
from psh.parser.recursive_descent.support.word_builder import WordBuilder


class TestExpansionASTNodes:
    """Test the expansion AST node classes."""

    def test_variable_expansion(self):
        """Test VariableExpansion node."""
        var = VariableExpansion("USER")
        assert str(var) == "$USER"
        assert var.name == "USER"

    def test_command_substitution(self):
        """Test CommandSubstitution node."""
        # Modern style
        cmd = CommandSubstitution("date +%Y", backtick_style=False)
        assert str(cmd) == "$(date +%Y)"
        assert cmd.command == "date +%Y"
        assert not cmd.backtick_style

        # Backtick style
        cmd2 = CommandSubstitution("hostname", backtick_style=True)
        assert str(cmd2) == "`hostname`"
        assert cmd2.command == "hostname"
        assert cmd2.backtick_style

    def test_parameter_expansion(self):
        """Test ParameterExpansion node."""
        # Simple form
        param = ParameterExpansion("HOME")
        assert str(param) == "${HOME}"

        # With default value
        param2 = ParameterExpansion("USER", ":-", "nobody")
        assert str(param2) == "${USER:-nobody}"

        # Length operator
        param3 = ParameterExpansion("PATH", "#", None)
        assert str(param3) == "${#PATH}"

        # Pattern removal
        param4 = ParameterExpansion("FILE", "%", ".txt")
        assert str(param4) == "${FILE%.txt}"

    def test_arithmetic_expansion(self):
        """Test ArithmeticExpansion node."""
        arith = ArithmeticExpansion("2 + 2")
        assert str(arith) == "$((2 + 2))"
        assert arith.expression == "2 + 2"

    def test_word_with_literal(self):
        """Test Word with only literal content."""
        word = Word(parts=[LiteralPart("hello")])
        assert str(word) == "hello"

        # With quotes (the part carries the quote; quote_type is derived)
        word2 = Word(parts=[LiteralPart("hello world", quoted=True,
                                        quote_char='"')])
        assert str(word2) == '"hello world"'

    def test_word_with_expansion(self):
        """Test Word with expansion."""
        word = Word(parts=[ExpansionPart(VariableExpansion("USER"))])
        assert str(word) == "$USER"

    def test_word_mixed_content(self):
        """Test Word with mixed literal and expansion."""
        word = Word(parts=[
            LiteralPart("Hello "),
            ExpansionPart(VariableExpansion("USER")),
            LiteralPart("!")
        ])
        assert str(word) == "Hello $USER!"

    def test_word_from_string(self):
        """Test Word.from_string helper."""
        word = Word.from_string("hello")
        assert str(word) == "hello"
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], LiteralPart)


class TestWordBuilder:
    """Test the WordBuilder utility."""

    def test_parse_variable_token(self):
        """Test parsing VARIABLE tokens."""
        # Simple variable
        token = Token(TokenType.VARIABLE, "USER", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, VariableExpansion)
        assert expansion.name == "USER"

        # Braced variable
        token2 = Token(TokenType.VARIABLE, "{HOME}", 0)
        expansion2 = WordBuilder.parse_expansion_token(token2)
        assert isinstance(expansion2, VariableExpansion)
        assert expansion2.name == "HOME"

    def test_parse_command_sub_token(self):
        """Test parsing COMMAND_SUB tokens."""
        token = Token(TokenType.COMMAND_SUB, "$(date)", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, CommandSubstitution)
        assert expansion.command == "date"
        assert not expansion.backtick_style

    def test_parse_backtick_token(self):
        """Test parsing COMMAND_SUB_BACKTICK tokens."""
        token = Token(TokenType.COMMAND_SUB_BACKTICK, "`hostname`", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, CommandSubstitution)
        assert expansion.command == "hostname"
        assert expansion.backtick_style

    def test_parse_arithmetic_token(self):
        """Test parsing ARITH_EXPANSION tokens."""
        token = Token(TokenType.ARITH_EXPANSION, "$((10 + 5))", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ArithmeticExpansion)
        assert expansion.expression == "10 + 5"

    def test_parse_param_expansion_token(self):
        """Test parsing PARAM_EXPANSION tokens."""
        # Default value
        token = Token(TokenType.PARAM_EXPANSION, "${USER:-nobody}", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ParameterExpansion)
        assert expansion.parameter == "USER"
        assert expansion.operator == ":-"
        assert expansion.word == "nobody"

        # Pattern removal
        token2 = Token(TokenType.PARAM_EXPANSION, "${PATH##*/}", 0)
        expansion2 = WordBuilder.parse_expansion_token(token2)
        assert isinstance(expansion2, ParameterExpansion)
        assert expansion2.parameter == "PATH"
        assert expansion2.operator == "##"
        assert expansion2.word == "*/"

        # Length
        token3 = Token(TokenType.PARAM_EXPANSION, "${#VAR}", 0)
        expansion3 = WordBuilder.parse_expansion_token(token3)
        assert isinstance(expansion3, ParameterExpansion)
        assert expansion3.parameter == "VAR"
        assert expansion3.operator == "#"
        assert expansion3.word is None

    def test_parse_prefix_substitution(self):
        """Test ${var/#pat/repl} produces operator='/#'."""
        token = Token(TokenType.PARAM_EXPANSION, "${path/#\\/usr/\\/opt}", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ParameterExpansion)
        assert expansion.parameter == "path"
        assert expansion.operator == "/#"
        assert expansion.word == "\\/usr/\\/opt"

    def test_parse_suffix_substitution(self):
        """Test ${var/%pat/repl} produces operator='/%'."""
        token = Token(TokenType.PARAM_EXPANSION, "${path/%bin/sbin}", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ParameterExpansion)
        assert expansion.parameter == "path"
        assert expansion.operator == "/%"
        assert expansion.word == "bin/sbin"

    def test_parse_substring_extraction(self):
        """Test ${var:offset:length} produces operator=':'."""
        token = Token(TokenType.PARAM_EXPANSION, "${str:0:-1}", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ParameterExpansion)
        assert expansion.parameter == "str"
        assert expansion.operator == ":"
        assert expansion.word == "0:-1"

    def test_parse_substring_offset_only(self):
        """Test ${var:offset} produces operator=':'."""
        token = Token(TokenType.PARAM_EXPANSION, "${str:3}", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ParameterExpansion)
        assert expansion.parameter == "str"
        assert expansion.operator == ":"
        assert expansion.word == "3"

    def test_parse_first_substitution(self):
        """Test ${var/pat/repl} still works correctly."""
        token = Token(TokenType.PARAM_EXPANSION, "${var/foo/bar}", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ParameterExpansion)
        assert expansion.parameter == "var"
        assert expansion.operator == "/"
        assert expansion.word == "foo/bar"

    def test_parse_global_substitution(self):
        """Test ${var//pat/repl} still works correctly."""
        token = Token(TokenType.PARAM_EXPANSION, "${var//foo/bar}", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ParameterExpansion)
        assert expansion.parameter == "var"
        assert expansion.operator == "//"
        assert expansion.word == "foo/bar"

    def test_parse_default_value_still_works(self):
        """Test ${var:-default} is not affected by new : operator."""
        token = Token(TokenType.PARAM_EXPANSION, "${x:-fallback}", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ParameterExpansion)
        assert expansion.parameter == "x"
        assert expansion.operator == ":-"
        assert expansion.word == "fallback"

    def test_parse_shortest_prefix_removal(self):
        """Test ${var#pat} is not confused with /#."""
        token = Token(TokenType.PARAM_EXPANSION, "${file#*.}", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ParameterExpansion)
        assert expansion.parameter == "file"
        assert expansion.operator == "#"
        assert expansion.word == "*."

    def test_parse_shortest_suffix_removal(self):
        """Test ${var%pat} is not confused with /%."""
        token = Token(TokenType.PARAM_EXPANSION, "${file%.txt}", 0)
        expansion = WordBuilder.parse_expansion_token(token)
        assert isinstance(expansion, ParameterExpansion)
        assert expansion.parameter == "file"
        assert expansion.operator == "%"
        assert expansion.word == ".txt"

    def test_build_word_from_token(self):
        """Test building Word from a single token."""
        # Literal token
        token = Token(TokenType.WORD, "hello", 0)
        word = WordBuilder.build_word_from_token(token)
        assert str(word) == "hello"
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], LiteralPart)

        # Variable token
        token2 = Token(TokenType.VARIABLE, "USER", 0)
        word2 = WordBuilder.build_word_from_token(token2)
        assert str(word2) == "$USER"
        assert len(word2.parts) == 1
        assert isinstance(word2.parts[0], ExpansionPart)
        assert isinstance(word2.parts[0].expansion, VariableExpansion)

    def test_build_composite_word(self):
        """Test building Word from multiple tokens."""
        tokens = [
            Token(TokenType.WORD, "Hello-", 0),
            Token(TokenType.VARIABLE, "USER", 6),
            Token(TokenType.WORD, "-world", 11)
        ]
        word = WordBuilder.build_composite_word(tokens)
        assert str(word) == "Hello-$USER-world"
        assert len(word.parts) == 3
        assert isinstance(word.parts[0], LiteralPart)
        assert isinstance(word.parts[1], ExpansionPart)
        assert isinstance(word.parts[2], LiteralPart)
