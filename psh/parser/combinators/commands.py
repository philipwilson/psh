"""Command and pipeline parsers for the shell parser combinator.

This module provides parsers for simple commands, pipelines, and-or lists,
and statement lists - the core command structures in shell syntax.
"""

import re
from typing import List, Optional, Union

from ...ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    ArrayAssignment,
    ASTNode,
    BreakStatement,
    CaseConditional,
    CommandList,
    ContinueStatement,
    CStyleForLoop,
    EnhancedTestStatement,
    ForLoop,
    FunctionDef,
    # Control structures for type checking
    IfConditional,
    Pipeline,
    Redirect,
    SelectLoop,
    SimpleCommand,
    WhileLoop,
)
from ...lexer.token_types import Token, TokenType
from ..config import ParserConfig
from ..recursive_descent.helpers import ErrorContext, ParseError
from ..recursive_descent.support.word_builder import WordBuilder
from .arrays import ArrayParsers
from .core import ForwardParser, Parser, ParseResult, many1, optional, separated_by, sequence, token
from .diagnostics import raise_committed_error
from .expansions import ExpansionParsers
from .tokens import TokenParsers

# Pre-compiled regex for fd duplication detection (e.g. ">&2", "2>&1", ">&-")
_FD_DUP_RE = re.compile(r'^(\d*)([><])&(-|\d+)$')

# Token types that should be treated as word-like for composite merging
_WORD_LIKE_TYPES = frozenset({
    'WORD', 'STRING', 'VARIABLE', 'PARAM_EXPANSION', 'COMMAND_SUB',
    'COMMAND_SUB_BACKTICK', 'ARITH_EXPANSION', 'PROCESS_SUB_IN', 'PROCESS_SUB_OUT',
})

class CommandParsers:
    """Parsers for shell commands and command structures.

    This class provides parsers for building the command hierarchy:
    simple commands -> pipelines -> and-or lists -> statement lists
    """

    def __init__(self, config: Optional[ParserConfig] = None,
                 token_parsers: Optional[TokenParsers] = None,
                 expansion_parsers: Optional[ExpansionParsers] = None):
        """Initialize command parsers.

        Args:
            config: Parser configuration
            token_parsers: Token parsers to use
            expansion_parsers: Expansion parsers to use
        """
        self.config = config or ParserConfig()
        self.tokens = token_parsers or TokenParsers()
        self.expansions = expansion_parsers or ExpansionParsers(self.config)
        self.arrays = ArrayParsers(self.tokens)

        # Forward declarations for recursive structures
        self.statement_forward = ForwardParser[Union[AndOrList, FunctionDef]]()
        self.statement_list_forward = ForwardParser[CommandList]()

        self._initialize_parsers()

    def _initialize_parsers(self):
        """Initialize all command-related parsers."""
        # Build redirection parser
        self.redirection = Parser(self._parse_redirection)

        # Build simple command parser
        self.simple_command = self._build_simple_command_parser()

        # Build pipeline parser
        self.pipeline = self._build_pipeline_parser()

        # Build and-or list parser
        self.and_or_list = self._build_and_or_list_parser()

        # Build statement parser
        self.statement = self._build_statement_parser()

        # Build statement list parser
        self.statement_list = self._build_statement_list_parser()

    def _parse_word_as_word(self, tokens: List[Token], pos: int) -> ParseResult:
        """Parse one word-like shell word, including adjacent composite parts."""
        return self.arrays.parse_word_as_word(tokens, pos)

    def _parse_redirection(self, tokens: List[Token], pos: int) -> ParseResult[Redirect]:
        """Parse I/O redirection.

        Args:
            tokens: List of tokens
            pos: Current position

        Returns:
            ParseResult with Redirect node
        """
        # First try to parse a redirection operator
        op_result = self.tokens.redirect_operator.parse(tokens, pos)
        if not op_result.success:
            return ParseResult(success=False, error=op_result.error, position=pos)

        op_token = op_result.value
        pos = op_result.position

        # Propagate fd from token metadata (set by lexer for fd-prefixed
        # redirects like 2>, 3>>)
        fd = op_token.fd

        # Handle redirect duplication (e.g., 2>&1, >&2, etc.)
        if op_token.type.name == 'REDIRECT_DUP':
            # REDIRECT_DUP tokens contain the full operator (e.g., "2>&1")
            # Parse the fd and dup_fd from the token value
            dup_match = _FD_DUP_RE.match(op_token.value)
            if dup_match:
                source_fd_str, direction, target = dup_match.groups()
                default_fd = 1 if direction == '>' else 0
                source_fd = int(source_fd_str) if source_fd_str else default_fd
                if target == '-':
                    redirect = Redirect(type=direction + '&-', target=None, fd=source_fd)
                else:
                    redirect = Redirect(
                        type=direction + '&', target=None,
                        fd=source_fd, dup_fd=int(target),
                    )
            else:
                redirect = Redirect(type=op_token.value, target='', fd=fd)
            return ParseResult(success=True, value=redirect, position=pos)

        # Handle heredoc operators
        if op_token.type.name in ['HEREDOC', 'HEREDOC_STRIP']:
            # Parse delimiter
            if pos >= len(tokens) or tokens[pos].type.name == 'EOF':
                return ParseResult(
                    success=False,
                    error="Expected heredoc delimiter",
                    position=pos
                )

            delimiter_token = tokens[pos]
            delimiter = delimiter_token.value

            redirect = Redirect(type=op_token.value, target=delimiter, fd=fd)
            return ParseResult(success=True, value=redirect, position=pos + 1)

        # Handle here string (<<<)
        if op_token.type.name == 'HERE_STRING':
            # Parse the content
            content_result = self._parse_word_as_word(tokens, pos)
            if not content_result.success:
                return ParseResult(
                    success=False,
                    error="Expected content after <<<",
                    position=pos
                )

            content_word = content_result.value
            assert content_word is not None  # success implies a value
            content_value = content_word.display_text()

            redirect = Redirect(
                type=op_token.value, target=content_value,
                quote_type=content_word.effective_quote_char, fd=fd,
            )
            return ParseResult(success=True, value=redirect, position=content_result.position)

        # Normal redirection - needs a target
        target_result = self._parse_word_as_word(tokens, pos)
        if not target_result.success:
            return ParseResult(
                success=False,
                error=f"Expected redirection target after {op_token.value}",
                position=pos
            )

        target_word = target_result.value
        assert target_word is not None  # success implies a value
        target_value = target_word.display_text()

        # Check for combined redirect (&> or &>>)
        combined = getattr(op_token, 'combined_redirect', False)

        redirect = Redirect(
            type=op_token.value,
            target=target_value,
            fd=fd,
            combined=combined,
            target_word=target_word,
        )
        return ParseResult(success=True, value=redirect, position=target_result.position)

    def _build_simple_command_parser(self) -> Parser[SimpleCommand]:
        """Build parser for simple commands.

        Returns:
            Parser that produces SimpleCommand nodes
        """
        def parse_simple_command(tokens: List[Token], pos: int) -> ParseResult[SimpleCommand]:
            """Parse a simple command with words, redirections, and FD dups."""
            word_tokens: List[Token] = []
            redirects: List[Redirect] = []
            array_assignments: List[ArrayAssignment] = []
            parsed_regular_arg = False

            # Collect words, redirections, and FD dup words in any order
            while pos < len(tokens):
                # Try FD dup word first (e.g., 2>&1, >&-)
                if pos < len(tokens) and tokens[pos].type.name == 'WORD':
                    fd_dup = self._parse_fd_dup_word(tokens[pos])
                    if fd_dup is not None:
                        redirects.append(fd_dup)
                        pos += 1
                        continue

                if not parsed_regular_arg:
                    array_result = self.arrays.parse_assignment(tokens, pos)
                    if array_result.success:
                        assert array_result.value is not None
                        array_assignments.append(array_result.value)
                        pos = array_result.position
                        continue

                # Try redirection (includes FD-prefixed redirects)
                redir_result = self.redirection.parse(tokens, pos)
                if redir_result.success:
                    redirects.append(redir_result.value)
                    pos = redir_result.position
                    continue
                if pos < len(tokens) and self.tokens.is_redirect_operator(tokens[pos]):
                    error_pos = min(redir_result.position, len(tokens) - 1)
                    raise ParseError(ErrorContext(
                        token=tokens[error_pos],
                        message=redir_result.error or "Invalid redirection",
                        position=error_pos,
                    ))

                # Try a word-like token
                word_result = self.tokens.word_like.parse(tokens, pos)
                if word_result.success:
                    if self.arrays.is_initializer_head(tokens, pos):
                        init_result = self.arrays.parse_initialization(tokens, pos)
                        if not init_result.success:
                            return ParseResult(
                                success=False,
                                error=init_result.error,
                                position=init_result.position,
                            )
                        array_init = init_result.value
                        assert array_init is not None
                        flat_text = (
                            array_init.name
                            + ('+=' if array_init.is_append else '=')
                            + '('
                            + ' '.join(array_init.elements)
                            + ')'
                        )
                        array_token = Token(
                            type=TokenType.WORD,
                            value=flat_text,
                            position=getattr(tokens[pos], 'position', 0),
                        )
                        setattr(array_token, 'array_init', array_init)
                        word_tokens.append(array_token)
                        pos = init_result.position
                        parsed_regular_arg = True
                        continue

                    word_tokens.append(word_result.value)
                    pos = word_result.position
                    parsed_regular_arg = True
                    continue

                # Nothing matched — stop collecting
                break

            if not word_tokens and not redirects and not array_assignments:
                return ParseResult(success=False, error="Expected command", position=pos)

            # Parse optional background operator
            background_result = optional(self.tokens.ampersand).parse(tokens, pos)
            background = background_result.value is not None
            pos = background_result.position

            # Build the simple command
            cmd = self._build_simple_command(
                word_tokens,
                redirects,
                background,
                array_assignments=array_assignments,
            )

            return ParseResult(
                success=True,
                value=cmd,
                position=pos
            )

        return Parser(parse_simple_command)

    @staticmethod
    def _group_adjacent_tokens(word_tokens: List[Token]) -> List[List[Token]]:
        """Group adjacent tokens into composite sequences.

        Tokens with adjacent_to_previous=True are merged with their
        predecessor to form a single composite word (e.g. i= + $((1+1))
        becomes a single word i=$((1+1))).
        """
        if not word_tokens:
            return []
        groups: List[List[Token]] = [[word_tokens[0]]]
        for tok in word_tokens[1:]:
            if (getattr(tok, 'adjacent_to_previous', False)
                    and tok.type.name in _WORD_LIKE_TYPES):
                groups[-1].append(tok)
            else:
                groups.append([tok])
        return groups

    def _build_simple_command(self, word_tokens: List[Token],
                             redirects: List[Redirect],
                             background: bool = False,
                             array_assignments: Optional[List[ArrayAssignment]] = None) -> SimpleCommand:
        """Build a SimpleCommand with proper token type and quote preservation.

        Args:
            word_tokens: List of word tokens
            redirects: List of redirections
            background: Whether command runs in background

        Returns:
            SimpleCommand AST node
        """
        cmd = SimpleCommand(
            redirects=redirects,
            background=background,
            array_assignments=array_assignments or [],
        )

        # Group adjacent tokens into composite sequences
        groups = self._group_adjacent_tokens(word_tokens)

        # Build Word AST nodes; the string view (SimpleCommand.args)
        # derives from them.
        for group in groups:
            if len(group) == 1:
                word = self.expansions.build_word_from_token(group[0])
            else:
                word = WordBuilder.build_composite_word(group)
            group_array_init = getattr(group[0], 'array_init', None)
            if group_array_init is not None:
                word.array_init = group_array_init
            cmd.words.append(word)

        return cmd

    @staticmethod
    def _parse_fd_dup_word(tok: Token) -> Optional[Redirect]:
        """Try to parse a WORD token as an FD duplication (e.g., 2>&1, >&-, <&0).

        Returns a Redirect node if the token matches, otherwise None.
        """
        if tok.type.name != 'WORD':
            return None
        match = _FD_DUP_RE.match(tok.value)
        if not match:
            return None

        source_fd_str, direction, target = match.groups()
        default_fd = 1 if direction == '>' else 0
        source_fd = int(source_fd_str) if source_fd_str else default_fd

        if target == '-':
            return Redirect(type=direction + '&-', target=None, fd=source_fd)
        return Redirect(
            type=direction + '&', target=None,
            fd=source_fd, dup_fd=int(target),
        )

    def _build_pipeline_parser(self) -> Parser[Union[Pipeline, ASTNode]]:
        """Build parser for pipelines.

        Returns:
            Parser that produces Pipeline or unwrapped command nodes
        """
        # Note: We need a command parser first, but that includes control structures
        # For now, we'll use simple_command and expect control structures to be added later

        # For initial version, just use simple commands
        # Control structures will be added when we have a command parser that includes them
        pipe_sep = self.tokens.pipe.or_else(self.tokens.pipe_and)

        def parse_pipeline_with_negation(tokens: List[Token], pos: int) -> ParseResult:
            """Parse optional `!` followed by a pipeline."""
            neg_result = optional(self.tokens.exclamation).parse(tokens, pos)
            negated = neg_result.value is not None
            pos = neg_result.position

            # Parse first command
            first_result = self.simple_command.parse(tokens, pos)
            if not first_result.success:
                return first_result

            commands = [first_result.value]
            pipe_stderr_list = []
            pos = first_result.position

            # Parse remaining | or |& separated commands
            while pos < len(tokens):
                sep_result = pipe_sep.parse(tokens, pos)
                if not sep_result.success:
                    break
                is_pipe_stderr = sep_result.value.type.name == 'PIPE_AND'
                pipe_stderr_list.append(is_pipe_stderr)
                pos = sep_result.position

                cmd_result = self.simple_command.parse(tokens, pos)
                if not cmd_result.success:
                    raise_committed_error(
                        tokens,
                        cmd_result.position,
                        cmd_result.error or "Expected command after pipe",
                    )
                commands.append(cmd_result.value)
                pos = cmd_result.position

            if len(commands) == 1 and not negated:
                cmd = commands[0]
                if isinstance(cmd, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                                  CStyleForLoop, ArithmeticEvaluation, EnhancedTestStatement,
                                  BreakStatement, ContinueStatement)):
                    return ParseResult(success=True, value=cmd, position=pos)
            pipeline = Pipeline(commands=commands, negated=negated, pipe_stderr=pipe_stderr_list) if commands else None
            return ParseResult(success=True, value=pipeline, position=pos)

        return Parser(parse_pipeline_with_negation)

    def _build_and_or_list_parser(self) -> Parser[Union[AndOrList, ASTNode]]:
        """Build parser for and-or lists.

        Returns:
            Parser that produces AndOrList nodes
        """
        # And-or operator
        and_or_operator = self.tokens.and_if.or_else(self.tokens.or_if)

        def parse_and_or_list(tokens: List[Token], pos: int) -> ParseResult[Union[AndOrList, ASTNode]]:
            first_result = self.pipeline.parse(tokens, pos)
            if not first_result.success:
                return first_result

            first = first_result.value
            rest = []
            pos = first_result.position

            while pos < len(tokens):
                op_result = and_or_operator.parse(tokens, pos)
                if not op_result.success:
                    break
                op_token = op_result.value
                pos = op_result.position

                rhs_result = self.pipeline.parse(tokens, pos)
                if not rhs_result.success:
                    raise_committed_error(
                        tokens,
                        rhs_result.position,
                        rhs_result.error or f"Expected command after {op_token.value}",
                    )
                rest.append((op_token, rhs_result.value))
                pos = rhs_result.position

            return ParseResult(
                success=True,
                value=self._build_and_or_list_from_parts((first, rest)),
                position=pos,
            )

        return Parser(parse_and_or_list)

    def _build_and_or_list_from_parts(self, parse_result: tuple) -> Union[AndOrList, ASTNode]:
        """Build an AndOrList from parsed components.

        Args:
            parse_result: Tuple of (first_element, rest_pairs)

        Returns:
            AndOrList AST node
        """
        first_element = parse_result[0]
        rest = parse_result[1]  # List of (operator, element) pairs

        # Normalize first element to Pipeline if needed
        if isinstance(first_element, Pipeline):
            first_pipeline = first_element
        else:
            # Single command - add directly as pipeline element
            first_pipeline = first_element

        if not rest:
            # Single element with no operators - return it directly instead of wrapping
            # This prevents unnecessary AndOrList wrapping for standalone control structures
            if isinstance(first_pipeline, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                                         CStyleForLoop, ArithmeticEvaluation, EnhancedTestStatement,
                                         BreakStatement, ContinueStatement)):
                return first_pipeline
            return AndOrList(pipelines=[first_pipeline])

        pipelines = [first_pipeline]
        operators = []

        for op_token, element in rest:
            operators.append(op_token.value)
            # Normalize element to Pipeline if needed
            if isinstance(element, Pipeline):
                pipelines.append(element)
            else:
                # Single command - add directly as pipeline element
                pipelines.append(element)

        return AndOrList(pipelines=pipelines, operators=operators)

    def _build_statement_parser(self) -> Parser[Union[AndOrList, FunctionDef]]:
        """Build parser for statements.

        Returns:
            Parser that produces statement nodes
        """
        # For now, just use and-or list
        # Function definitions and control structures will be added later
        return self.and_or_list

    def _build_statement_list_parser(self) -> Parser[CommandList]:
        """Build parser for statement lists.

        Returns:
            Parser that produces CommandList nodes
        """
        # Statement separator
        separator = self.tokens.semicolon.or_else(self.tokens.newline)
        separators = many1(separator)

        # Parse optional leading separators, statements separated by separators, and optional trailing separators
        statement_list_parser = sequence(
            optional(separators),  # Allow optional leading separators
            optional(
                separated_by(
                    self.statement,
                    separators
                )
            ),
            optional(separators)  # Allow optional trailing separators
        ).map(lambda triple: CommandList(statements=triple[1] if triple[1] else []))

        return statement_list_parser

    def set_command_parser(self, command_parser: Parser):
        """Set the command parser (includes control structures).

        This is called after control structures are initialized to break circular dependency.

        Args:
            command_parser: Parser that handles both simple commands and control structures
        """
        # Update pipeline parser to use full command parser with negation support
        pipe_sep = self.tokens.pipe.or_else(self.tokens.pipe_and)

        def parse_pipeline_with_negation(tokens: List[Token], pos: int) -> ParseResult:
            neg_result = optional(self.tokens.exclamation).parse(tokens, pos)
            negated = neg_result.value is not None
            pos = neg_result.position

            # Parse first command
            first_result = command_parser.parse(tokens, pos)
            if not first_result.success:
                return first_result

            commands: List = [first_result.value]
            pipe_stderr_list = []
            pos = first_result.position

            # Parse remaining | or |& separated commands
            while pos < len(tokens):
                sep_result = pipe_sep.parse(tokens, pos)
                if not sep_result.success:
                    break
                is_pipe_stderr = sep_result.value.type.name == 'PIPE_AND'
                pipe_stderr_list.append(is_pipe_stderr)
                pos = sep_result.position

                cmd_result = command_parser.parse(tokens, pos)
                if not cmd_result.success:
                    raise_committed_error(
                        tokens,
                        cmd_result.position,
                        cmd_result.error or "Expected command after pipe",
                    )
                commands.append(cmd_result.value)
                pos = cmd_result.position

            if len(commands) == 1 and not negated:
                cmd = commands[0]
                if isinstance(cmd, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                                  CStyleForLoop, ArithmeticEvaluation, EnhancedTestStatement,
                                  BreakStatement, ContinueStatement)):
                    return ParseResult(success=True, value=cmd, position=pos)
            pipeline = Pipeline(commands=commands, negated=negated, pipe_stderr=pipe_stderr_list) if commands else None
            return ParseResult(success=True, value=pipeline, position=pos)

        self.pipeline = Parser(parse_pipeline_with_negation)

        # Update and-or list parser
        and_or_element = self.pipeline.or_else(command_parser)
        and_or_operator = self.tokens.and_if.or_else(self.tokens.or_if)

        def parse_and_or_list(tokens: List[Token], pos: int) -> ParseResult[Union[AndOrList, ASTNode]]:
            first_result = and_or_element.parse(tokens, pos)
            if not first_result.success:
                return first_result

            first = first_result.value
            rest = []
            pos = first_result.position

            while pos < len(tokens):
                op_result = and_or_operator.parse(tokens, pos)
                if not op_result.success:
                    break
                op_token = op_result.value
                pos = op_result.position

                rhs_result = and_or_element.parse(tokens, pos)
                if not rhs_result.success:
                    raise_committed_error(
                        tokens,
                        rhs_result.position,
                        rhs_result.error or f"Expected command after {op_token.value}",
                    )
                rest.append((op_token, rhs_result.value))
                pos = rhs_result.position

            return ParseResult(
                success=True,
                value=self._build_and_or_list_from_parts((first, rest)),
                position=pos,
            )

        self.and_or_list = Parser(parse_and_or_list)


# Convenience functions

def create_command_parsers(config: Optional[ParserConfig] = None,
                          token_parsers: Optional[TokenParsers] = None,
                          expansion_parsers: Optional[ExpansionParsers] = None) -> CommandParsers:
    """Create and return a CommandParsers instance.

    Args:
        config: Optional parser configuration
        token_parsers: Optional token parsers
        expansion_parsers: Optional expansion parsers

    Returns:
        Initialized CommandParsers object
    """
    return CommandParsers(config, token_parsers, expansion_parsers)


def parse_simple_command(tokens: TokenParsers,
                         expansions: ExpansionParsers) -> Parser[SimpleCommand]:
    """Create parser for simple commands.

    Args:
        tokens: Token parsers
        expansions: Expansion parsers

    Returns:
        Parser that matches simple commands
    """
    cmd_parsers = CommandParsers(token_parsers=tokens, expansion_parsers=expansions)
    return cmd_parsers.simple_command


def parse_pipeline(command_parser: Parser) -> Parser[Union[Pipeline, ASTNode]]:
    """Create parser for pipelines.

    Args:
        command_parser: Parser for commands

    Returns:
        Parser that matches pipelines
    """
    pipe_sep = token('PIPE').or_else(token('PIPE_AND'))
    exclamation = token('EXCLAMATION')

    def parse_pipeline_with_negation(tokens: List[Token], pos: int) -> ParseResult:
        neg_result = optional(exclamation).parse(tokens, pos)
        negated = neg_result.value is not None
        pos = neg_result.position

        # Parse first command
        first_result = command_parser.parse(tokens, pos)
        if not first_result.success:
            return first_result

        commands: List = [first_result.value]
        pipe_stderr_list = []
        pos = first_result.position

        # Parse remaining | or |& separated commands
        while pos < len(tokens):
            sep_result = pipe_sep.parse(tokens, pos)
            if not sep_result.success:
                break
            assert sep_result.value is not None
            is_pipe_stderr = sep_result.value.type.name == 'PIPE_AND'
            pipe_stderr_list.append(is_pipe_stderr)
            pos = sep_result.position

            cmd_result = command_parser.parse(tokens, pos)
            if not cmd_result.success:
                raise_committed_error(
                    tokens,
                    cmd_result.position,
                    cmd_result.error or "Expected command after pipe",
                )
            commands.append(cmd_result.value)
            pos = cmd_result.position

        if len(commands) == 1 and not negated:
            cmd = commands[0]
            if isinstance(cmd, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                              CStyleForLoop, ArithmeticEvaluation, EnhancedTestStatement,
                              BreakStatement, ContinueStatement)):
                return ParseResult(success=True, value=cmd, position=pos)
        pipeline = Pipeline(commands=commands, negated=negated, pipe_stderr=pipe_stderr_list) if commands else None
        return ParseResult(success=True, value=pipeline, position=pos)

    return Parser(parse_pipeline_with_negation)


def parse_and_or_list(pipeline_parser: Parser) -> Parser[AndOrList]:
    """Create parser for and-or lists.

    Args:
        pipeline_parser: Parser for pipelines

    Returns:
        Parser that matches and-or lists
    """
    and_or_operator = token('AND_AND').or_else(token('OR_OR'))

    def build_and_or(parts):
        first = parts[0]
        rest = parts[1]

        if not rest:
            if isinstance(first, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                                CStyleForLoop, ArithmeticEvaluation, EnhancedTestStatement,
                                BreakStatement, ContinueStatement)):
                return first
            return AndOrList(pipelines=[first])

        pipelines = [first]
        operators = []
        for op, pipeline in rest:
            operators.append(op.value)
            pipelines.append(pipeline)

        return AndOrList(pipelines=pipelines, operators=operators)

    def parse_and_or(tokens: List[Token], pos: int) -> ParseResult[AndOrList]:
        first_result = pipeline_parser.parse(tokens, pos)
        if not first_result.success:
            return first_result

        first = first_result.value
        rest = []
        pos = first_result.position

        while pos < len(tokens):
            op_result = and_or_operator.parse(tokens, pos)
            if not op_result.success:
                break
            assert op_result.value is not None
            op_token = op_result.value
            pos = op_result.position

            rhs_result = pipeline_parser.parse(tokens, pos)
            if not rhs_result.success:
                raise_committed_error(
                    tokens,
                    rhs_result.position,
                    rhs_result.error or f"Expected command after {op_token.value}",
                )
            rest.append((op_token, rhs_result.value))
            pos = rhs_result.position

        return ParseResult(success=True, value=build_and_or((first, rest)), position=pos)

    return Parser(parse_and_or)
