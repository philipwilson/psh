"""
Command parsing for PSH shell.

This module handles parsing of commands, pipelines, and command arguments.
"""

from typing import Optional, Tuple

from ....ast_nodes import (
    AndOrList,
    ArrayInitialization,
    BraceGroup,
    BreakStatement,
    Command,
    ContinueStatement,
    LiteralPart,
    Pipeline,
    SimpleCommand,
    Statement,
    SubshellGroup,
    Word,
)
from ....lexer.token_stream import TokenStream
from ....lexer.token_types import Token, TokenType
from ..helpers import ErrorContext, ParseError, TokenGroups
from ..support.word_builder import WordBuilder
from .redirections import _FD_DUP_RE

# Mapping from expansion_type to (description, prefix, chars_to_skip)
_UNCLOSED_EXPANSION_MSGS = {
    'parameter_unclosed': ("unclosed parameter expansion", '${', 2),
    'command_unclosed': ("unclosed command substitution", '$(', 2),
    'arithmetic_unclosed': ("unclosed arithmetic expansion", '$((', 3),
    'backtick_unclosed': ("unclosed backtick substitution", '`', 1),
}


class CommandParser:
    """Parser for command-level constructs."""

    def __init__(self, main_parser):
        """Initialize with reference to main parser."""
        self.parser = main_parser

    def _is_fd_duplication(self, value: str) -> bool:
        """Check if a WORD token is actually a file descriptor duplication."""
        # Patterns: >&N, <&N, N>&M, N<&M, >&-, <&-
        return bool(_FD_DUP_RE.match(value))

    def _raise_syntax_error(self, msg: str, token: Token,
                            at_eof: bool = False,
                            unclosed: Optional[str] = None) -> None:
        """Raise a ParseError with the given message at the given token.

        ``at_eof=True`` marks the error as structurally "incomplete input":
        an unclosed expansion consumes everything to the end of the input by
        construction, so more lines could complete it. Interactive and
        script line-gathering key off this flag to keep reading (multi-line
        ``$(...)``, ``${...}``, backticks, and heredocs inside them).

        ``unclosed`` names WHICH expansion kind is open ('command',
        'parameter', 'arithmetic', 'backtick') — a structured signal for
        the CommandAccumulator's continuation hints, so nothing has to
        string-match the error message.
        """
        error_context = ErrorContext(
            token=token,
            message=msg,
            position=token.position
        )
        error = ParseError(error_context)
        if at_eof:
            error.at_eof = True
        if unclosed:
            error.unclosed_expansion = unclosed
        raise error

    def _check_for_unclosed_expansions(self, token: Token) -> None:
        """Check if a token contains unclosed expansions and raise appropriate errors."""
        # Check tokens that might contain expansions
        if token.type not in [TokenType.WORD, TokenType.COMPOSITE, TokenType.COMMAND_SUB,
                              TokenType.COMMAND_SUB_BACKTICK, TokenType.ARITH_EXPANSION, TokenType.VARIABLE,
                              TokenType.PARAM_EXPANSION]:
            return

        # Check token parts for unclosed expansions
        if token.parts:
            for part in token.parts:
                if part.expansion_type and part.expansion_type.endswith('_unclosed'):
                    kind = part.expansion_type[:-len('_unclosed')]
                    fmt = _UNCLOSED_EXPANSION_MSGS.get(part.expansion_type)
                    if fmt:
                        desc, prefix, skip = fmt
                        error_msg = f"syntax error: {desc} '{prefix}{part.value[skip:]}'"
                    else:
                        error_msg = f"syntax error: unclosed expansion '{part.value}'"

                    self._raise_syntax_error(error_msg, token, at_eof=True,
                                             unclosed=kind)

        # Also check for specific token types that indicate unclosed expansions
        if token.type == TokenType.COMMAND_SUB and not token.value.endswith(')'):
            self._raise_syntax_error(
                f"syntax error: unclosed command substitution '{token.value}'", token,
                at_eof=True, unclosed='command')
        elif token.type == TokenType.COMMAND_SUB_BACKTICK and token.value.count('`') == 1:
            self._raise_syntax_error(
                f"syntax error: unclosed backtick substitution '{token.value}'", token,
                at_eof=True, unclosed='backtick')
        elif token.type == TokenType.ARITH_EXPANSION and not token.value.endswith('))'):
            self._raise_syntax_error(
                f"syntax error: unclosed arithmetic expansion '{token.value}'", token,
                at_eof=True, unclosed='arithmetic')
        elif token.type == TokenType.VARIABLE and token.value.startswith('${') and not token.value.endswith('}'):
            self._raise_syntax_error(
                f"syntax error: unclosed parameter expansion '{token.value}'", token,
                at_eof=True, unclosed='parameter')

    def parse_command(self) -> SimpleCommand:
        """Parse a single command with its arguments and redirections."""
        command = SimpleCommand()

        # Validate command start
        self._validate_command_start()

        # Parse all arguments and redirections
        self._parse_command_elements(command)

        # NOTE: '&' is parsed at the and-or-list level (POSIX grammar), not
        # here — `a && b &` backgrounds the whole list.
        return command

    def _validate_command_start(self) -> None:
        """Validate that we're at a valid command start position."""
        # Check for unexpected tokens
        if self.parser.match_any(TokenGroups.CASE_TERMINATORS):
            self._raise_syntax_error(
                f"syntax error near unexpected token '{self.parser.peek().value}'",
                self.parser.peek()
            )

        # Ensure we have a word-like token, redirect, or fd-duplication word
        if not self.parser.match_any(TokenGroups.WORD_LIKE | TokenGroups.REDIRECTS):
            if not (self.parser.match(TokenType.WORD) and
                    self._is_fd_duplication(self.parser.peek().value)):
                raise self.parser.error("Expected command")

    def _parse_command_elements(self, command: SimpleCommand) -> None:
        """Parse arguments, redirections, and array assignments for a command."""
        has_parsed_regular_args = False

        while (self.parser.match_any(TokenGroups.WORD_LIKE | TokenGroups.REDIRECTS) or
               (self.parser.match(TokenType.EXCLAMATION) and
                command.args and command.args[0] in ('test', '['))):

            if self.parser.match_any(TokenGroups.REDIRECTS):
                redirect = self.parser.redirections.parse_redirect()
                command.redirects.append(redirect)

            elif self.parser.match(TokenType.WORD) and self._is_fd_duplication(self.parser.peek().value):
                redirect = self.parser.redirections.parse_fd_dup_word()
                command.redirects.append(redirect)

            elif self.parser.match(TokenType.EXCLAMATION):
                token = self.parser.advance()
                command.words.append(Word(parts=[LiteralPart(token.value)]))
                has_parsed_regular_args = True

            else:
                # Only check for array assignments if no regular args parsed yet
                if not has_parsed_regular_args and self.parser.arrays.is_array_assignment():
                    array_assignment = self.parser.arrays.parse_array_assignment()
                    command.array_assignments.append(array_assignment)
                else:
                    has_parsed_regular_args = self._parse_argument(
                        command, has_parsed_regular_args
                    )

    def _parse_argument(self, command: SimpleCommand,
                       has_parsed_regular_args: bool) -> bool:
        """Parse a single argument, handling array initialization specially.

        Returns:
            True if a regular argument was parsed (updates has_parsed_regular_args)
        """
        # Check for array initialization syntax: arr=(...) or arr = (...)
        is_array_init, word_token = self._check_array_initialization()

        if is_array_init:
            assert word_token is not None  # guaranteed when is_array_init is True
            arg_value, array_init = self._parse_array_initialization(word_token)
            command.words.append(
                Word(parts=[LiteralPart(arg_value)], array_init=array_init))
            return True

        # Parse argument as Word AST node. The string view of the
        # argument (SimpleCommand.args) is derived from this Word.
        command.words.append(self.parse_argument_as_word())

        return True

    def _check_array_initialization(self) -> Tuple[bool, Optional[Token]]:
        """Check if current position is array initialization syntax.

        Returns:
            Tuple of (is_array_init, word_token). The returned word_token's
            value carries the assignment head (``arr=`` or ``arr+=``) so the
            caller can rebuild the flat string view; on the split-token forms
            the head is synthesized.
        """
        if not self.parser.match(TokenType.WORD):
            return False, None

        word_token = self.parser.peek()

        # `arr=(...)` / `arr+=(...)`: the lexer emits the name and operator
        # as one WORD ('arr=' or 'arr+=') followed by LPAREN. This is the
        # form bash accepts.
        if ((word_token.value.endswith('=')) and
            self.parser.peek(1) and
            self.parser.peek(1).type == TokenType.LPAREN):
            self.parser.advance()
            return True, word_token

        # `arr += (...)` / `arr = (...)`: the operator is a separate WORD
        # token ('+=' or '='). The lexer splits ``a+=`` into ``a`` + ``+=``
        # (verified), and ``arr = (...)`` (with spaces) into three tokens.
        # bash rejects the spaced form but accepts ``a+=`` written
        # together; psh accepts both (the spaced form is pinned behavior).
        op_token = self.parser.peek(1)
        if (op_token and op_token.type == TokenType.WORD and
                op_token.value in ('=', '+=') and
                self.parser.peek(2) and
                self.parser.peek(2).type == TokenType.LPAREN):
            name_token = self.parser.advance()
            self.parser.advance()  # consume the '=' / '+=' operator
            # Synthesize a head token carrying name + operator so the
            # caller's flat-string rebuild and name/append detection work
            # uniformly with the single-token form.
            head = Token(TokenType.WORD, name_token.value + op_token.value,
                         name_token.position)
            return True, head

        return False, None

    def _parse_array_initialization(
            self, word_token: Token) -> Tuple[str, 'ArrayInitialization']:
        """Parse array initialization syntax ``arr=(...)`` / ``arr+=(...)``
        in ARGUMENT position (e.g. ``declare -a arr=(1 2)``).

        Returns ``(flat_string, ArrayInitialization)``:

        - The flat string (``arr=(elem1 elem2)``) becomes the literal text
          of the argument's Word, so ``SimpleCommand.args`` and display keep
          working for ordinary commands and tooling.
        - The structured ArrayInitialization carries the per-element Words
          (with full per-part quote context). The declaration builtins
          (``declare``/``typeset``/``local``/``export``/``readonly``) consume
          it through the SAME structured expansion the bare ``a=(...)`` path
          uses — no serialize-then-shlex-reparse, which is what fixes
          adjacent-quote joining (``("x""y")``), tilde, command-sub elements,
          explicit ``[i]=v`` indices, bare assoc keys, and ``+=`` append.

        The flat string's elements are still serialized from the source
        TOKENS (not the element Words) so the legacy fallback path
        (``array_init.py``, used only when no structured init is present)
        keeps its verbatim quoting; the structured path never re-reads it.

        Args:
            word_token: Head token whose value is ``arr=`` or ``arr+=``.

        Returns:
            (flat_string, ArrayInitialization)
        """
        is_append = word_token.value.endswith('+=')
        if is_append:
            name = word_token.value[:-2]
        else:
            name = word_token.value[:-1]

        self.parser.advance()  # consume LPAREN

        elements: list = []        # flat-string fragments (token-faithful)
        element_words: list = []   # structured element Words
        element_start_pos = self.parser.current

        while not self.parser.match(TokenType.RPAREN) and not self.parser.at_end():
            if self.parser.match(TokenType.NEWLINE):
                # Newlines between elements are allowed (as in bash).
                self.parser.advance()
                element_start_pos = self.parser.current
            elif self.parser.match_any(TokenGroups.WORD_LIKE):
                word = self.parse_argument_as_word()  # consume element
                element_words.append(word)

                # Serialize the element from the tokens just consumed
                element_end_pos = self.parser.current
                original_tokens = self.parser.tokens[element_start_pos:element_end_pos]

                original_repr_parts = []
                for token in original_tokens:
                    if token.type == TokenType.STRING and token.quote_type:
                        original_repr_parts.append(token.quote_type + token.value + token.quote_type)
                    elif token.type == TokenType.VARIABLE:
                        # VARIABLE token values carry the name without the
                        # leading '$' ('x' or '{x}') — restore it so the
                        # consuming builtin can expand the element.
                        original_repr_parts.append('$' + token.value)
                    else:
                        original_repr_parts.append(token.value)

                elements.append(''.join(original_repr_parts))
                element_start_pos = self.parser.current
            else:
                raise self.parser.error("Expected array element")

        if not self.parser.consume_if(TokenType.RPAREN):
            raise self.parser.error("Expected ')' to close array initialization")

        flat_string = name + ('+=' if is_append else '=') + '(' + ' '.join(elements) + ')'
        array_init = ArrayInitialization(
            name=name,
            elements=[w.display_text() for w in element_words],
            is_append=is_append,
            words=element_words,
        )
        return flat_string, array_init

    def parse_pipeline(self) -> Pipeline:
        """Parse a pipeline (commands connected by | or |&)."""
        pipeline = Pipeline()

        # Check for leading ! (negation)
        if self.parser.consume_if(TokenType.EXCLAMATION):
            pipeline.negated = True

        # Parse first command (could be simple or compound)
        command = self.parse_pipeline_component()
        pipeline.commands.append(command)

        # Parse additional piped commands (| or |&). POSIX allows a
        # linebreak after the pipe operator.
        while self.parser.match(TokenType.PIPE, TokenType.PIPE_AND):
            is_pipe_stderr = self.parser.peek().type == TokenType.PIPE_AND
            self.parser.advance()
            self.parser.skip_newlines()
            pipeline.pipe_stderr.append(is_pipe_stderr)
            command = self.parse_pipeline_component()
            pipeline.commands.append(command)

        return pipeline


    def parse_pipeline_with_initial_component(self, initial_component: Command) -> Statement:
        """Parse a pipeline starting with an already-parsed component."""
        # Create pipeline and add initial component
        pipeline = Pipeline()
        pipeline.commands.append(initial_component)

        # Must have at least one pipe since we were called due to seeing a pipe
        # Accept either | or |&
        if self.parser.match(TokenType.PIPE, TokenType.PIPE_AND):
            is_pipe_stderr = self.parser.peek().type == TokenType.PIPE_AND
            self.parser.advance()
            pipeline.pipe_stderr.append(is_pipe_stderr)
        else:
            self.parser.expect(TokenType.PIPE)

        # Parse remaining pipeline components
        while True:
            command = self.parse_pipeline_component()
            pipeline.commands.append(command)

            if not self.parser.match(TokenType.PIPE, TokenType.PIPE_AND):
                break
            is_pipe_stderr = self.parser.peek().type == TokenType.PIPE_AND
            self.parser.advance()
            pipeline.pipe_stderr.append(is_pipe_stderr)

        # Wrap pipeline in AndOrList for consistency
        and_or_list = AndOrList()
        and_or_list.pipelines.append(pipeline)

        # Check for && or || continuation
        return self.parser.statements.parse_and_or_tail(and_or_list)

    def parse_pipeline_component(self) -> Command:
        """Parse a single component of a pipeline (simple or compound command)."""
        # Try parsing as control structure first
        if self.parser.match(TokenType.WHILE):
            return self.parser.control_structures.parse_while_statement()
        elif self.parser.match(TokenType.UNTIL):
            return self.parser.control_structures.parse_until_statement()
        elif self.parser.match(TokenType.FOR):
            return self.parser.control_structures.parse_for_statement()
        elif self.parser.match(TokenType.IF):
            return self.parser.control_structures.parse_if_statement()
        elif self.parser.match(TokenType.CASE):
            return self.parser.control_structures.parse_case_statement()
        elif self.parser.match(TokenType.SELECT):
            return self.parser.control_structures.parse_select_statement()
        elif self.parser.match(TokenType.DOUBLE_LPAREN):
            return self.parser.arithmetic.parse_arithmetic_command()
        elif self.parser.match(TokenType.DOUBLE_LBRACKET):
            return self.parser.tests.parse_enhanced_test_statement()
        elif self.parser.match(TokenType.BREAK):
            return self.parse_break_statement()
        elif self.parser.match(TokenType.CONTINUE):
            return self.parse_continue_statement()
        elif self.parser.match(TokenType.LPAREN):
            self._reject_escaped_dollar_paren()
            return self.parse_subshell_group()
        elif self.parser.match(TokenType.LBRACE):
            return self.parse_brace_group()
        else:
            # Fall back to simple command
            return self.parse_command()

    def _reject_escaped_dollar_paren(self) -> None:
        """Reject `\\$(`-style constructs, matching bash's syntax error.

        In `echo \\$(echo test)` the backslash escapes the dollar, so `$(`
        is not a command substitution: the lexer emits a WORD ending in
        `\\$` followed by a bare LPAREN. Bash treats this as a syntax error
        ("syntax error near unexpected token `('") rather than a subshell.

        The check lives in the parser, not the lexer, because only here do
        we see the WORD/LPAREN token *pair*: the lexer has already (correctly)
        tokenized each piece on its own, and a bare LPAREN is normally a
        valid subshell start. We count the backslashes preceding the `$` in
        the previous WORD token — an odd count means the dollar is escaped
        (e.g. `\\$(` and `\\\\\\$(`), while an even count means the backslashes
        escape each other and the `$(` is a real command substitution.

        Raises ParseError if the LPAREN at the current position follows an
        escaped dollar; otherwise returns normally.
        """
        if self.parser.current == 0:
            return
        prev_token = self.parser.tokens[self.parser.current - 1]
        if not (prev_token.type == TokenType.WORD and
                prev_token.value.endswith('\\$')):
            return

        # Count trailing backslashes before the $
        num_backslashes = 0
        for i in range(len(prev_token.value) - 2, -1, -1):
            if prev_token.value[i] == '\\':
                num_backslashes += 1
            else:
                break

        # If odd number of backslashes, the $ is escaped
        if num_backslashes % 2 == 1:
            self._raise_syntax_error(
                "syntax error near unexpected token '('", self.parser.peek())

    def parse_argument_as_word(self) -> 'Word':
        """Parse an argument as a Word AST node with expansions.

        Delegates to WordBuilder (support/word_builder.py) for token-to-Word
        conversion. See WordBuilder for details on RichToken decomposition,
        composite word building, and parameter expansion parsing.
        """
        # Check for composite tokens
        stream = TokenStream(self.parser.tokens, self.parser.current)
        composite = stream.peek_composite_sequence()

        if composite:
            # Check for unclosed expansions in composite parts
            for token in composite:
                self._check_for_unclosed_expansions(token)
            # Build composite word from multiple tokens.
            # Per-part quote context is handled inside build_composite_word().
            self.parser.current = stream.pos + len(composite)
            return WordBuilder.build_composite_word(composite)
        else:
            # Single token
            if self.parser.match_any(TokenGroups.WORD_LIKE):
                token = self.parser.advance()
                self._check_for_unclosed_expansions(token)
                quote_type = token.quote_type if token.type == TokenType.STRING else None
                return WordBuilder.build_word_from_token(token, quote_type)
            else:
                raise self.parser.error("Expected word-like token")

    def parse_break_statement(self) -> BreakStatement:
        """Parse break statement for use in pipelines."""
        return self.parser.control_structures.parse_break_statement()

    def parse_continue_statement(self) -> ContinueStatement:
        """Parse continue statement for use in pipelines."""
        return self.parser.control_structures.parse_continue_statement()

    def parse_subshell_group(self) -> SubshellGroup:
        """Parse subshell group (...) that executes in isolated environment."""
        self.parser.expect(TokenType.LPAREN)
        self.parser.ctx.push_construct('subshell')
        self.parser.skip_newlines()

        # Parse statements inside the subshell
        statements = self.parser.statements.parse_command_list_until(TokenType.RPAREN)

        self.parser.skip_newlines()
        # Bash requires at least one command inside a subshell: `()`, `( )`,
        # newline-only or comment-only groups are a syntax error (exit 2).
        if not statements.statements:
            raise self.parser.error(
                f"syntax error near unexpected token '{self.parser.peek().value}'")
        self.parser.expect(TokenType.RPAREN)
        self.parser.ctx.pop_construct()

        # Parse any redirections after the subshell
        redirects = self.parser.redirections.parse_redirects()

        # Check for background operator
        background = self.parser.match(TokenType.AMPERSAND)
        if background:
            self.parser.advance()

        return SubshellGroup(
            statements=statements,
            redirects=redirects,
            background=background
        )

    def parse_brace_group(self) -> BraceGroup:
        """Parse brace group {...} that executes in current environment.

        POSIX syntax rules:
        - Space required after {
        - Semicolon or newline required before }
        """
        self.parser.expect(TokenType.LBRACE)
        self.parser.ctx.push_construct('brace')
        self.parser.skip_newlines()

        # Parse statements inside the brace group
        statements = self.parser.statements.parse_command_list_until(TokenType.RBRACE)

        self.parser.skip_newlines()
        # Bash requires at least one command inside a brace group: `{ }`,
        # newline-only or comment-only groups are a syntax error (exit 2).
        if not statements.statements:
            raise self.parser.error(
                f"syntax error near unexpected token '{self.parser.peek().value}'")
        self.parser.expect(TokenType.RBRACE)
        self.parser.ctx.pop_construct()

        # Parse any redirections after the brace group
        redirects = self.parser.redirections.parse_redirects()

        # Check for background operator
        background = self.parser.match(TokenType.AMPERSAND)
        if background:
            self.parser.advance()

        return BraceGroup(
            statements=statements,
            redirects=redirects,
            background=background
        )
