"""Main parser integration for the modular parser combinator implementation.

This module integrates all the parser combinator modules into a cohesive
parser for shell commands using functional combinators.
"""

from typing import Dict, List, Optional, Tuple, Union

from ...ast_nodes import ASTNode, CommandList, Statement, StatementList, TopLevel
from ...lexer.keyword_normalizer import KeywordNormalizer
from ...lexer.token_types import Token, TokenType
from ..config import ParserConfig
from ..recursive_descent.helpers import ErrorContext, ParseError
from .commands import create_command_parsers
from .control_structures import create_control_structure_parsers
from .expansions import create_expansion_parsers
from .heredoc_processor import create_heredoc_processor
from .special_commands import create_special_command_parsers

# Import all parser modules
from .tokens import create_token_parsers


class ParserCombinatorShellParser:
    """Experimental parser combinator implementation.

    **Status: Experimental / Educational -- not the production parser.**

    This parser demonstrates functional parsing through composable combinators.
    It breaks down complex shell syntax into small, reusable parsing functions
    that can be combined to handle the full shell grammar.

    The production parser is the recursive descent parser in
    ``recursive_descent/``.  This combinator parser exists as an educational
    counterpoint and proof of concept.  It may lag behind on edge-case fixes
    and new features.  There is no plan to converge the two implementations.

    Project decision (2026-06-12): this parser is **outside the production
    quality bar**.  Parity regression tests pin known-good behavior against
    drift, but remaining gaps (e.g. composite words in some list contexts)
    are documented rather than tracked as defects, and conformance work does
    not target this parser.  Revisit if/when dedicated time is available.

    Use ``parser-select combinator`` inside psh to activate it interactively.
    """

    def __init__(self, config: Optional[ParserConfig] = None,
                 heredoc_contents: Optional[Dict[str, str]] = None):
        """Initialize the parser combinator.

        Args:
            config: Parser configuration
            heredoc_contents: Optional map of heredoc keys to their content
        """
        self.config = config or ParserConfig()
        self.heredoc_contents = heredoc_contents or {}

        # Initialize all parser modules
        self._initialize_modules()

    def _initialize_modules(self):
        """Initialize all parser modules and wire them together."""
        # Create token parsers
        self.tokens = create_token_parsers()

        # Create expansion parsers
        self.expansions = create_expansion_parsers(self.config)

        # Create command parsers with dependencies
        self.commands = create_command_parsers(
            config=self.config,
            token_parsers=self.tokens,
            expansion_parsers=self.expansions
        )

        # Create control structure parsers
        self.control = create_control_structure_parsers(
            config=self.config,
            token_parsers=self.tokens,
            command_parsers=self.commands
        )

        # Create special command parsers
        self.special = create_special_command_parsers(
            config=self.config,
            token_parsers=self.tokens,
            command_parsers=self.commands
        )

        # Create heredoc processor
        self.heredoc_processor = create_heredoc_processor()

        # Wire circular dependencies
        self._wire_dependencies()

        # Build the complete parser after dependencies are wired
        self._build_complete_parser()

    def _wire_dependencies(self):
        """Wire circular dependencies between modules.

        Some parser modules have circular dependencies (e.g., commands
        can contain control structures which contain commands). This
        method resolves these dependencies after all modules are created.
        """
        # Wire command parsers in dependent modules - this triggers
        # initialization of parsers that depend on commands
        self.control.set_command_parsers(self.commands)
        self.special.set_command_parsers(self.commands)

        # Wire forward declarations in commands module if needed
        if hasattr(self.commands, 'set_control_parsers'):
            self.commands.set_control_parsers(self.control)

        if hasattr(self.commands, 'set_special_parsers'):
            self.commands.set_special_parsers(self.special)

    def _build_complete_parser(self):
        """Build the complete top-level parser."""
        # First check if control structures have been initialized
        if not hasattr(self.control, 'control_structure') or self.control.control_structure is None:
            # Control structures haven't been initialized yet, use simple commands only
            self.command = self.commands.and_or_list
        else:
            # Build a pipeline-element parser: what can appear as a single
            # element inside a pipeline.  Control structures and special
            # commands are included so that e.g.
            #   for i in 1 2 3; do echo $i; done | grep 2
            # is parsed correctly.
            pipeline_element = (
                self.control.control_structure
                .or_else(self.special.special_command)
                .or_else(self.commands.simple_command)
            )

            # Update the pipeline/and-or layer to use this element parser.
            if hasattr(self.commands, 'set_command_parser'):
                self.commands.set_command_parser(pipeline_element)

            # The top-level command parser is now the and-or list, which
            # internally uses the pipeline layer (which now accepts compound
            # commands as elements).
            self.command = self.commands.and_or_list

        # CRITICAL: Update the statement parser to include control structures
        # The statement parser was built before control structures were available
        # Now we need to update it to use the full command parser
        self.commands.statement = (
            # Try function definitions first
            self.control.function_def
            # Then the full command parser (and-or lists which include pipelines)
            .or_else(self.command)
        )

        # Rebuild statement_list parser with the updated statement parser.
        # The statement_list was built with the old statement parser that only
        # had and_or_list.  Use a committed loop rather than many(...), because
        # many() intentionally swallows failures; at a real command token that
        # loses diagnostics and turns syntax errors into generic top-level
        # "unexpected token after valid input" messages.
        from .core import Parser as CombinatorParser
        from .core import ParseResult, many1, optional
        separator = self.tokens.semicolon.or_else(self.tokens.newline)
        separators = many1(separator)

        def parse_statement_list(tokens: List[Token], pos: int):
            statements = []
            current_pos = optional(separators).parse(tokens, pos).position

            while current_pos < len(tokens):
                if tokens[current_pos].type in (
                    TokenType.EOF, TokenType.RPAREN, TokenType.RBRACE,
                ):
                    break

                statement_result = self.commands.statement.parse(tokens, current_pos)
                if not statement_result.success:
                    return statement_result

                statements.append(statement_result.value)
                if statement_result.position == current_pos:
                    break
                current_pos = statement_result.position
                current_pos = optional(separators).parse(tokens, current_pos).position

            return ParseResult(
                success=True,
                value=CommandList(statements=statements),
                position=current_pos,
            )

        self.commands.statement_list = CombinatorParser(parse_statement_list)

        # Build top-level parser (statement list)
        self.top_level = self.commands.statement_list

    def _prepare_tokens(self, tokens: List[Token]) -> Tuple[List[Token], int]:
        """Normalize keywords and skip leading whitespace.

        Returns:
            (normalized_tokens, start_pos).  start_pos == len(tokens)
            when input is empty/whitespace-only.
        """
        normalizer = KeywordNormalizer()
        tokens = normalizer.normalize(list(tokens))
        start_pos = 0
        while start_pos < len(tokens) and tokens[start_pos].type.name in ['WHITESPACE', 'NEWLINE']:
            start_pos += 1
        return tokens, start_pos

    def _apply_heredocs(self, ast):
        """Populate heredoc content in AST if available."""
        if self.heredoc_contents:
            self.heredoc_processor.populate_heredocs(ast, self.heredoc_contents)

    def parse(self, tokens: List[Token]) -> Union[TopLevel, CommandList]:
        """Parse a list of tokens into an AST.

        Args:
            tokens: List of tokens from the lexer

        Returns:
            The root AST node (either TopLevel or CommandList)

        Raises:
            ParseError: If parsing fails
        """
        tokens, start_pos = self._prepare_tokens(tokens)

        # Empty input
        if start_pos >= len(tokens):
            return TopLevel(items=[])

        # Parse the tokens
        result = self.top_level.parse(tokens, start_pos)

        if not result.success:
            # Try to provide a helpful error message
            error_msg = result.error or "Failed to parse input"
            error_token = None
            if result.position < len(tokens):
                error_token = tokens[result.position]
                error_msg = f"{error_msg} at position {result.position}: {error_token.type.name} '{error_token.value}'"
            if error_token is None:
                error_token = tokens[-1] if tokens else Token(type=TokenType.WORD, value='', position=0)
            raise ParseError(ErrorContext(token=error_token, message=error_msg, position=result.position))

        # Get the parsed AST
        ast = result.value

        # Ensure we consumed all tokens (allowing trailing whitespace/newlines and EOF)
        pos = result.position
        while pos < len(tokens) and tokens[pos].type.name in ['WHITESPACE', 'NEWLINE', 'EOF']:
            pos += 1

        if pos < len(tokens):
            # We didn't consume all tokens
            remaining_token = tokens[pos]
            raise ParseError(ErrorContext(
                message=f"Unexpected token after valid input: {remaining_token.type.name} '{remaining_token.value}'",
                position=pos,
                token=remaining_token,
            ))

        self._apply_heredocs(ast)

        # Wrap in TopLevel if needed
        if isinstance(ast, CommandList):
            # Convert CommandList to TopLevel by putting statements as items
            items: List[Union[Statement, StatementList]] = list(ast.statements)
            return TopLevel(items=items)
        elif isinstance(ast, StatementList):
            # Convert StatementList to TopLevel
            items = list(ast.statements)
            return TopLevel(items=items)
        elif isinstance(ast, TopLevel):
            return ast
        else:
            # Single statement - wrap it
            return TopLevel(items=[ast])

    def parse_with_heredocs(self, tokens: List[Token],
                           heredoc_contents: Dict[str, str]) -> Union[TopLevel, CommandList]:
        """Parse tokens with heredoc content support.

        This method performs a two-pass parse:
        1. Parse the token stream into an AST
        2. Populate heredoc content in AST nodes

        Args:
            tokens: List of tokens from the lexer
            heredoc_contents: Map of heredoc keys to their content

        Returns:
            Parsed AST with heredoc content populated
        """
        # Store heredoc contents
        self.heredoc_contents = heredoc_contents

        # Parse normally (which will populate heredocs)
        return self.parse(tokens)

    def parse_partial(self, tokens: List[Token]) -> Tuple[Optional[ASTNode], int]:
        """Parse as much as possible from the token stream.

        Args:
            tokens: List of tokens from the lexer

        Returns:
            Tuple of (AST node or None, position where parsing stopped)
        """
        tokens, start_pos = self._prepare_tokens(tokens)

        # Empty input
        if start_pos >= len(tokens):
            return None, start_pos

        # Try parsers from broadest to narrowest
        for parser in [self.top_level, self.commands.statement, self.command]:
            result = parser.parse(tokens, start_pos)
            if result.success:
                self._apply_heredocs(result.value)
                return result.value, result.position

        # Nothing could be parsed
        return None, start_pos

    def can_parse(self, tokens: List[Token]) -> bool:
        """Check if the tokens can be parsed without actually parsing.

        Args:
            tokens: List of tokens to check

        Returns:
            True if the tokens appear to be parseable
        """
        try:
            tokens, start_pos = self._prepare_tokens(tokens)

            # Empty input is valid
            if start_pos >= len(tokens):
                return True

            # Try to parse
            result = self.top_level.parse(tokens, start_pos)

            if not result.success:
                return False

            # Check if we consumed all tokens (allowing trailing whitespace)
            pos = result.position
            while pos < len(tokens) and tokens[pos].type.name in ['WHITESPACE', 'NEWLINE', 'EOF']:
                pos += 1

            return pos == len(tokens)
        except (AttributeError, IndexError, TypeError, ParseError):
            return False

    def configure(self, **options):
        """Configure the parser with implementation-specific options.

        Args:
            **options: Implementation-specific configuration options
        """
        # Update configuration
        for key, value in options.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

        # Reinitialize modules with new config
        self._initialize_modules()
        self._build_complete_parser()

    def explain_parse(self, tokens: List[Token]) -> str:
        """Provide an educational explanation of how parsing works.

        Args:
            tokens: List of tokens to parse

        Returns:
            Multi-line string explaining the parsing process
        """
        return """
=== Modular Parser Combinator Parsing ===

This parser uses a modular architecture with specialized modules:

1. TOKEN PARSERS - Recognize basic tokens:
   - Keywords (if, then, while, etc.)
   - Operators (|, &, ;, etc.)
   - Delimiters and separators

2. EXPANSION PARSERS - Handle shell expansions:
   - Variable expansion ($var, ${var})
   - Command substitution $(cmd) and `cmd`
   - Arithmetic expansion $((expr))
   - Parameter expansion ${var:-default}

3. COMMAND PARSERS - Parse command structures:
   - Simple commands (cmd arg1 arg2)
   - Pipelines (cmd1 | cmd2)
   - And-or lists (cmd1 && cmd2 || cmd3)
   - Redirections (< file, > file, 2>&1)

4. CONTROL STRUCTURE PARSERS - Handle control flow:
   - If/elif/else conditionals
   - While/for loops
   - Case statements
   - Function definitions

5. SPECIAL COMMAND PARSERS - Parse special syntax:
   - Arithmetic commands ((expr))
   - Enhanced tests [[ condition ]]
   - Array operations
   - Process substitution <(cmd)

6. HEREDOC PROCESSOR - Post-processing phase:
   - Populates heredoc content in redirect nodes
   - Traverses AST after main parsing

The parser works by:
1. Starting with the top-level statement list parser
2. Trying control structures first (most specific)
3. Then special commands
4. Finally regular commands
5. Each parser can recursively call others
6. Results are composed into a complete AST

Key advantages:
- Modular and maintainable
- Clear separation of concerns
- Reusable parser components
- Easy to extend with new features
- Functional programming style
"""


# Convenience functions

def create_parser_combinator_shell_parser(
    config: Optional[ParserConfig] = None,
    heredoc_contents: Optional[Dict[str, str]] = None
) -> ParserCombinatorShellParser:
    """Create and return a ParserCombinatorShellParser instance.

    Args:
        config: Optional parser configuration
        heredoc_contents: Optional heredoc content map

    Returns:
        Initialized ParserCombinatorShellParser object
    """
    return ParserCombinatorShellParser(config, heredoc_contents)
