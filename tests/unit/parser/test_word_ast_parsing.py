"""Test Word AST node creation in parsers."""

from psh.ast_nodes import (
    CommandSubstitution,
    ExpansionPart,
    LiteralPart,
    ParameterExpansion,
    SimpleCommand,
    VariableExpansion,
    Word,
)
from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.config import ParserConfig


class TestRecursiveDescentWordAST:
    """Test Word AST creation in recursive descent parser."""

    def test_word_ast_disabled_by_default(self):
        """Test that Word AST nodes are not created by default."""
        tokens = tokenize("echo $USER")
        ast = Parser(tokens).parse()

        # Get the command
        cmd = ast.statements[0].pipelines[0].commands[0]
        assert isinstance(cmd, SimpleCommand)
        assert cmd.args == ["echo", "$USER"]
        assert cmd.words is not None  # Word AST is enabled by default

    def test_simple_literal_word(self):
        """Test Word AST for simple literal arguments."""
        tokens = tokenize("echo hello world")
        ast = Parser(tokens, config=ParserConfig()).parse()

        cmd = ast.statements[0].pipelines[0].commands[0]
        assert cmd.words is not None
        assert len(cmd.words) == 3

        # Check each word
        for i, expected in enumerate(["echo", "hello", "world"]):
            word = cmd.words[i]
            assert isinstance(word, Word)
            assert len(word.parts) == 1
            assert isinstance(word.parts[0], LiteralPart)
            assert word.parts[0].text == expected
            assert str(word) == expected

    def test_variable_expansion_word(self):
        """Test Word AST for variable expansion."""
        tokens = tokenize("echo $USER $HOME")
        ast = Parser(tokens, config=ParserConfig()).parse()

        cmd = ast.statements[0].pipelines[0].commands[0]
        assert cmd.words is not None
        assert len(cmd.words) == 3

        # First word is literal "echo"
        assert isinstance(cmd.words[0].parts[0], LiteralPart)

        # Second word is $USER
        word = cmd.words[1]
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, VariableExpansion)
        assert word.parts[0].expansion.name == "USER"
        assert str(word) == "$USER"

        # Third word is $HOME
        word = cmd.words[2]
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, VariableExpansion)
        assert word.parts[0].expansion.name == "HOME"
        assert str(word) == "$HOME"

    def test_command_substitution_word(self):
        """Test Word AST for command substitution."""
        tokens = tokenize("echo $(date) `hostname`")
        ast = Parser(tokens, config=ParserConfig()).parse()

        cmd = ast.statements[0].pipelines[0].commands[0]
        assert len(cmd.words) == 3

        # Check $(date)
        word = cmd.words[1]
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, CommandSubstitution)
        assert word.parts[0].expansion.source == "date"
        assert not word.parts[0].expansion.backtick_style
        assert str(word) == "$(date)"

        # Check `hostname`
        word = cmd.words[2]
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, CommandSubstitution)
        assert word.parts[0].expansion.source == "hostname"
        assert word.parts[0].expansion.backtick_style
        assert str(word) == "`hostname`"

    def test_parameter_expansion_word(self):
        """Test Word AST for parameter expansion."""
        tokens = tokenize("echo ${USER:-nobody} ${#PATH}")
        ast = Parser(tokens, config=ParserConfig()).parse()

        cmd = ast.statements[0].pipelines[0].commands[0]
        assert len(cmd.words) == 3

        # Check ${USER:-nobody}
        word = cmd.words[1]
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, ParameterExpansion)
        assert word.parts[0].expansion.parameter == "USER"
        assert word.parts[0].expansion.operator == ":-"
        assert word.parts[0].expansion.word == "nobody"
        assert str(word) == "${USER:-nobody}"

        # Check ${#PATH}
        word = cmd.words[2]
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, ParameterExpansion)
        assert word.parts[0].expansion.parameter == "PATH"
        assert word.parts[0].expansion.operator == "#"
        assert word.parts[0].expansion.word is None
        assert str(word) == "${#PATH}"

    def test_quoted_word(self):
        """Test Word AST for quoted strings."""
        tokens = tokenize('echo "hello world" \'single quoted\'')
        ast = Parser(tokens, config=ParserConfig()).parse()

        cmd = ast.statements[0].pipelines[0].commands[0]
        assert len(cmd.words) == 3

        # Double quoted
        word = cmd.words[1]
        assert word.quote_type == '"'
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], LiteralPart)
        assert word.parts[0].text == "hello world"
        assert str(word) == '"hello world"'

        # Single quoted
        word = cmd.words[2]
        assert word.quote_type == "'"
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], LiteralPart)
        assert word.parts[0].text == "single quoted"
        assert str(word) == "'single quoted'"

    def test_composite_word(self):
        """Test Word AST for composite words with mixed content."""
        tokens = tokenize("echo prefix-$USER-suffix")
        ast = Parser(tokens, config=ParserConfig()).parse()

        cmd = ast.statements[0].pipelines[0].commands[0]
        word = cmd.words[1]
        assert len(word.parts) == 3
        assert isinstance(word.parts[0], LiteralPart)
        assert word.parts[0].text == "prefix-"
        assert not word.parts[0].quoted  # unquoted literal
        assert isinstance(word.parts[1], ExpansionPart)
        assert isinstance(word.parts[1].expansion, VariableExpansion)
        assert not word.parts[1].quoted  # unquoted expansion
        assert isinstance(word.parts[2], LiteralPart)
        assert word.parts[2].text == "-suffix"
        assert str(word) == "prefix-$USER-suffix"
        # Composite words have no single quote_type
        assert word.quote_type is None

    def test_composite_word_mixed_quotes(self):
        """Test Word AST for composite words with mixed quoted/unquoted parts.

        The lexer tokenizes "$var" as a RichToken STRING with TokenPart
        metadata.  The WordBuilder decomposes it into an ExpansionPart
        with the proper quote context.
        """
        tokens = tokenize('echo foo"$var"bar')
        ast = Parser(tokens, config=ParserConfig()).parse()

        cmd = ast.statements[0].pipelines[0].commands[0]
        assert cmd.words is not None
        word = cmd.words[1]
        # 3 parts: foo (unquoted), $var (quoted expansion), bar (unquoted)
        assert len(word.parts) == 3
        # foo - unquoted literal
        assert isinstance(word.parts[0], LiteralPart)
        assert word.parts[0].text == "foo"
        assert not word.parts[0].quoted
        # "$var" - quoted expansion (decomposed from STRING token)
        assert isinstance(word.parts[1], ExpansionPart)
        assert isinstance(word.parts[1].expansion, VariableExpansion)
        assert word.parts[1].expansion.name == "var"
        assert word.parts[1].quoted
        assert word.parts[1].quote_char == '"'
        # bar - unquoted literal
        assert isinstance(word.parts[2], LiteralPart)
        assert word.parts[2].text == "bar"
        assert not word.parts[2].quoted
        # Composite has no single quote_type
        assert word.quote_type is None

    def test_composite_word_single_quote_part(self):
        """Test Word AST for composite with single-quoted part."""
        tokens = tokenize("echo FOO='value'")
        ast = Parser(tokens, config=ParserConfig()).parse()

        cmd = ast.statements[0].pipelines[0].commands[0]
        word = cmd.words[1]
        # Should have FOO= (unquoted) and value (single-quoted)
        assert len(word.parts) == 2
        assert isinstance(word.parts[0], LiteralPart)
        assert word.parts[0].text == "FOO="
        assert not word.parts[0].quoted
        assert isinstance(word.parts[1], LiteralPart)
        assert word.parts[1].text == "value"
        assert word.parts[1].quoted
        assert word.parts[1].quote_char == "'"

    def test_double_quoted_string_decomposed_into_expansion(self):
        """Test that "$HOME" is decomposed into ExpansionPart."""
        tokens = tokenize('echo "$HOME"')
        ast = Parser(tokens, config=ParserConfig()).parse()

        cmd = ast.statements[0].pipelines[0].commands[0]
        assert cmd.words is not None
        assert len(cmd.words) == 2

        word = cmd.words[1]
        # "$HOME" should be a Word with quote_type='"' containing an ExpansionPart
        assert word.quote_type == '"'
        assert len(word.parts) == 1
        assert isinstance(word.parts[0], ExpansionPart)
        assert isinstance(word.parts[0].expansion, VariableExpansion)
        assert word.parts[0].expansion.name == "HOME"
        assert word.parts[0].quoted
        assert word.parts[0].quote_char == '"'

    def test_double_quoted_string_with_text_and_expansion(self):
        """Test that "hello $USER!" is decomposed into mixed parts."""
        tokens = tokenize('echo "hello $USER!"')
        ast = Parser(tokens, config=ParserConfig()).parse()

        cmd = ast.statements[0].pipelines[0].commands[0]
        word = cmd.words[1]
        assert word.quote_type == '"'
        # Should have 3 parts: "hello " + $USER + "!"
        assert len(word.parts) == 3
        assert isinstance(word.parts[0], LiteralPart)
        assert word.parts[0].text == "hello "
        assert word.parts[0].quoted
        assert isinstance(word.parts[1], ExpansionPart)
        assert isinstance(word.parts[1].expansion, VariableExpansion)
        assert word.parts[1].expansion.name == "USER"
        assert word.parts[1].quoted
        assert isinstance(word.parts[2], LiteralPart)
        assert word.parts[2].text == "!"
        assert word.parts[2].quoted
