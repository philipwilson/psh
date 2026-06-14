"""Command and pipeline parsers for the shell parser combinator.

This module provides parsers for simple commands, pipelines, and-or lists,
and statement lists - the core command structures in shell syntax.
"""

import re
from typing import List, Optional, Union

from ...ast_nodes import (
    AndOrList,
    ArithmeticEvaluation,
    ASTNode,
    BraceGroup,
    CaseConditional,
    CommandList,
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
    SubshellGroup,
    WhileLoop,
)
from ...lexer.token_types import Token
from ..config import ParserConfig
from ..recursive_descent.support.word_builder import WordBuilder
from .core import ForwardParser, Parser, ParseResult, many, many1, optional, separated_by, sequence, token
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
            if pos >= len(tokens):
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
            content_result = self.tokens.word_like.parse(tokens, pos)
            if not content_result.success:
                return ParseResult(
                    success=False,
                    error="Expected content after <<<",
                    position=pos
                )

            content_value = content_result.value.value if hasattr(content_result.value, 'value') else str(content_result.value)

            redirect = Redirect(
                type=op_token.value, target=content_value,
                heredoc_content=content_value, fd=fd,
            )
            return ParseResult(success=True, value=redirect, position=content_result.position)

        # Normal redirection - needs a target
        target_result = self.tokens.word_like.parse(tokens, pos)
        if not target_result.success:
            return ParseResult(
                success=False,
                error=f"Expected redirection target after {op_token.value}",
                position=pos
            )

        target_value = target_result.value.value if hasattr(target_result.value, 'value') else str(target_result.value)

        # Check for combined redirect (&> or &>>)
        combined = getattr(op_token, 'combined_redirect', False)

        redirect = Redirect(type=op_token.value, target=target_value, fd=fd, combined=combined)
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

            # Collect words, redirections, and FD dup words in any order
            while pos < len(tokens):
                # Try FD dup word first (e.g., 2>&1, >&-)
                if pos < len(tokens) and tokens[pos].type.name == 'WORD':
                    fd_dup = self._parse_fd_dup_word(tokens[pos])
                    if fd_dup is not None:
                        redirects.append(fd_dup)
                        pos += 1
                        continue

                # Try redirection (includes FD-prefixed redirects)
                redir_result = self.redirection.parse(tokens, pos)
                if redir_result.success:
                    redirects.append(redir_result.value)
                    pos = redir_result.position
                    continue

                # Try a word-like token
                word_result = self.tokens.word_like.parse(tokens, pos)
                if word_result.success:
                    word_tokens.append(word_result.value)
                    pos = word_result.position

                    # Check for array assignment: WORD('name=') followed by
                    # adjacent LPAREN — e.g. `declare -a arr=(one two three)`.
                    # Collect the parenthesized items and synthesize a single
                    # WORD token "name=(item1 item2 ...)" that the executor
                    # recognises as an array initialization.
                    if (pos < len(tokens)
                            and tokens[pos].type.name == 'LPAREN'
                            and getattr(tokens[pos], 'adjacent_to_previous', False)
                            and word_tokens[-1].value.endswith('=')):
                        arr_prefix = word_tokens.pop()  # remove the 'name=' token
                        pos += 1  # skip '('
                        items: List[str] = []
                        while pos < len(tokens) and tokens[pos].type.name != 'RPAREN':
                            tok = tokens[pos]
                            if tok.type.name in _WORD_LIKE_TYPES or tok.type.name in ('LBRACKET', 'RBRACKET'):
                                # Preserve quotes around STRING tokens so the executor
                                # can parse ["key"]="value" for associative arrays.
                                qt = getattr(tok, 'quote_type', None)
                                if qt and tok.type.name == 'STRING':
                                    text = f'{qt}{tok.value}{qt}'
                                else:
                                    text = tok.value
                                # Group adjacent tokens into a single element
                                # (e.g. ["key"]="value" is one element, not four).
                                if items and getattr(tok, 'adjacent_to_previous', False):
                                    items[-1] += text
                                else:
                                    items.append(text)
                            # Skip whitespace/newlines inside array parens
                            pos += 1
                        if pos < len(tokens) and tokens[pos].type.name == 'RPAREN':
                            pos += 1  # skip ')'
                        # Build a single synthetic token: "name=(item1 item2 ...)"
                        arr_value = arr_prefix.value + '(' + ' '.join(items) + ')'
                        synth_token = Token(
                            type=arr_prefix.type,
                            value=arr_value,
                            position=getattr(arr_prefix, 'position', 0),
                        )
                        word_tokens.append(synth_token)

                    continue

                # Nothing matched — stop collecting
                break

            if not word_tokens and not redirects:
                return ParseResult(success=False, error="Expected command", position=pos)

            # Parse optional background operator
            background_result = optional(self.tokens.ampersand).parse(tokens, pos)
            background = background_result.value is not None
            pos = background_result.position

            # Build the simple command
            cmd = self._build_simple_command(word_tokens, redirects, background)

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
                             background: bool = False) -> SimpleCommand:
        """Build a SimpleCommand with proper token type and quote preservation.

        Args:
            word_tokens: List of word tokens
            redirects: List of redirections
            background: Whether command runs in background

        Returns:
            SimpleCommand AST node
        """
        cmd = SimpleCommand(redirects=redirects, background=background)

        # Group adjacent tokens into composite sequences
        groups = self._group_adjacent_tokens(word_tokens)

        # Build Word AST nodes; the string view (SimpleCommand.args)
        # derives from them.
        for group in groups:
            if len(group) == 1:
                word = self.expansions.build_word_from_token(group[0])
            else:
                word = WordBuilder.build_composite_word(group)
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
                    return cmd_result
                commands.append(cmd_result.value)
                pos = cmd_result.position

            if len(commands) == 1 and not negated:
                cmd = commands[0]
                if isinstance(cmd, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                                  SubshellGroup, BraceGroup, CStyleForLoop, ArithmeticEvaluation,
                                  EnhancedTestStatement)):
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

        # Parse pipeline followed by optional and/or operators and more pipelines
        and_or_parser = sequence(
            self.pipeline,
            many(sequence(and_or_operator, self.pipeline))
        ).map(self._build_and_or_list_from_parts)

        return and_or_parser

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
                                         SubshellGroup, BraceGroup, CStyleForLoop, ArithmeticEvaluation,
                                         EnhancedTestStatement)):
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
                    return cmd_result
                commands.append(cmd_result.value)
                pos = cmd_result.position

            if len(commands) == 1 and not negated:
                cmd = commands[0]
                if isinstance(cmd, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                                  SubshellGroup, BraceGroup, CStyleForLoop, ArithmeticEvaluation,
                                  EnhancedTestStatement)):
                    return ParseResult(success=True, value=cmd, position=pos)
            pipeline = Pipeline(commands=commands, negated=negated, pipe_stderr=pipe_stderr_list) if commands else None
            return ParseResult(success=True, value=pipeline, position=pos)

        self.pipeline = Parser(parse_pipeline_with_negation)

        # Update and-or list parser
        and_or_element = self.pipeline.or_else(command_parser)
        and_or_operator = self.tokens.and_if.or_else(self.tokens.or_if)

        self.and_or_list = sequence(
            and_or_element,
            many(sequence(and_or_operator, and_or_element))
        ).map(self._build_and_or_list_from_parts)


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
                return cmd_result
            commands.append(cmd_result.value)
            pos = cmd_result.position

        if len(commands) == 1 and not negated:
            cmd = commands[0]
            if isinstance(cmd, (IfConditional, WhileLoop, ForLoop, CaseConditional, SelectLoop,
                              SubshellGroup, BraceGroup, CStyleForLoop, ArithmeticEvaluation,
                              EnhancedTestStatement)):
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
                                SubshellGroup, BraceGroup, CStyleForLoop, ArithmeticEvaluation,
                                EnhancedTestStatement)):
                return first
            return AndOrList(pipelines=[first])

        pipelines = [first]
        operators = []
        for op, pipeline in rest:
            operators.append(op.value)
            pipelines.append(pipeline)

        return AndOrList(pipelines=pipelines, operators=operators)

    return sequence(
        pipeline_parser,
        many(sequence(and_or_operator, pipeline_parser))
    ).map(build_and_or)
