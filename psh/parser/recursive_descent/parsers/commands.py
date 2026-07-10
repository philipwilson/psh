"""
Command parsing for PSH shell.

This module handles parsing of commands, pipelines, and command arguments.
"""

from dataclasses import replace
from typing import List, Optional, Tuple

from ....ast_nodes import (
    ArrayInitialization,
    BraceGroup,
    Command,
    LiteralPart,
    Pipeline,
    SimpleCommand,
    SubshellGroup,
    Word,
)
from ....lexer.token_types import Token, TokenType
from ..helpers import ParseError, TokenGroups, unexpected_token_message
from ..support.word_builder import WordBuilder
from .base import ParserSubcomponent
from .redirections import _FD_DUP_RE

# Mapping from expansion_type to (description, prefix, chars_to_skip)
_UNCLOSED_EXPANSION_MSGS = {
    'parameter_unclosed': ("unclosed parameter expansion", '${', 2),
    'command_unclosed': ("unclosed command substitution", '$(', 2),
    'arithmetic_unclosed': ("unclosed arithmetic expansion", '$((', 3),
    'backtick_unclosed': ("unclosed backtick substitution", '`', 1),
}

# Maximum compound-command nesting depth (brace groups, subshells,
# if/while/for/case/select, ((...)), [[...]] inside one another). The
# recursive-descent parser burns ~9 Python frames per nesting level, so
# runaway nesting would otherwise die as a Python RecursionError; this
# explicit guard (the statement-parser analogue of ArithParser.MAX_DEPTH)
# turns it into a clean ParseError instead, well before the interpreter
# limit raised by psh.shell.RECURSION_LIMIT (40,000 — parsing, executing
# and formatting a 1000-deep script all fit with headroom; bash itself
# parses such scripts without complaint, limited only by memory).
MAX_NESTING_DEPTH = 1000


class CommandParser(ParserSubcomponent):
    """Parser for command-level constructs."""


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
        # Build through the context so the error carries line/column,
        # the source line for the caret, and token context — the same
        # rich rendering every other parse error gets.
        error_context = self.parser.ctx._create_error_context(msg, token)
        error = ParseError(error_context)
        if at_eof:
            error.at_eof = True
        if unclosed:
            error.unclosed_expansion = unclosed
        raise error

    def _check_for_unclosed_expansions(self, token: Token) -> None:
        """Check if a token contains unclosed expansions and raise appropriate errors."""
        # Check tokens that might contain expansions
        if token.type not in [TokenType.WORD, TokenType.COMMAND_SUB,
                              TokenType.COMMAND_SUB_BACKTICK, TokenType.ARITH_EXPANSION, TokenType.VARIABLE,
                              TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT]:
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
        elif token.type in (TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT) \
                and not token.value.endswith(')'):
            # An unclosed `<(`/`>(` swallows everything to end of input (so a
            # `<<EOF` inside it stays nested, like $(...)). Treat it as
            # incomplete input — interactive/script line-gathering reads more
            # lines until the matching ')' arrives (multi-line process subs,
            # including heredocs inside them).
            self._raise_syntax_error(
                f"syntax error: unclosed process substitution '{token.value}'", token,
                at_eof=True, unclosed='command')

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

        # A bare '}' can never START a command (bash: syntax error, rc 2,
        # nothing runs). RBRACE stays in WORD_LIKE so `echo }` keeps working
        # as an ARGUMENT; a real brace group's closer never reaches here —
        # parse_brace_group's expect(RBRACE) consumes it first.
        if self.parser.match(TokenType.RBRACE):
            self._raise_syntax_error(
                "syntax error near unexpected token '}'", self.parser.peek())

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

        # Detection is shared with the statement-position path: the same
        # classifier recognises both the single-token head (``arr=`` / ``arr+=``
        # followed by ``(``) and the split form (``arr`` + ``=``/``+=`` + ``(``,
        # incl. the spaced variant). It is peek-only; this argument-position
        # path then consumes the head tokens and synthesizes one head Token so
        # the caller's flat-string rebuild and name/append detection work
        # uniformly across both forms.
        candidate = self.parser.arrays._candidate_initializer()
        if candidate is None or not candidate.is_initializer:
            return False, None

        start = self.parser.peek()
        for _ in range(candidate.head_token_count):
            self.parser.advance()
        head = Token(TokenType.WORD,
                     candidate.name + candidate.operator,
                     start.position)
        return True, head

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
        TOKENS (not the element Words) so any consumer that wants the
        verbatim source quoting has it; the structured path never re-reads it.

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

        # Shared element-collection loop (also used by the bare ``a=(...)``
        # statement path in arrays.py); element_strings are token-faithful so
        # the argument keeps verbatim source quoting in its flat Word text.
        element_words, element_strings = self.parse_array_init_elements()

        flat_string = name + ('+=' if is_append else '=') + '(' + ' '.join(element_strings) + ')'
        array_init = ArrayInitialization(
            name=name,
            elements=[w.display_text() for w in element_words],
            is_append=is_append,
            words=element_words,
        )
        return flat_string, array_init

    def parse_array_init_elements(self) -> Tuple[List['Word'], List[str]]:
        """Parse an array initializer body up to and including the closing ``)``.

        The opening ``(`` must already be consumed. Returns
        ``(element_words, element_strings)``: the structured per-element Words
        (full per-part quote context) and a token-faithful source string for
        each element (so a caller can rebuild the verbatim ``(...)`` text).
        Newlines between elements are allowed, as in bash. Shared by the
        argument-position (`declare a=(...)`) and statement-position
        (`a=(...)`) array-init parsers.
        """
        element_words: List['Word'] = []
        element_strings: List[str] = []
        element_start_pos = self.parser.current

        while not self.parser.match(TokenType.RPAREN) and not self.parser.at_end():
            if self.parser.match(TokenType.NEWLINE):
                self.parser.advance()
                element_start_pos = self.parser.current
            elif self.parser.match_any(TokenGroups.WORD_LIKE):
                word = self.parse_argument_as_word()  # consume element
                element_words.append(word)
                element_strings.append(
                    self._serialize_array_element(element_start_pos, self.parser.current))
                element_start_pos = self.parser.current
            else:
                raise self.parser.error("Expected array element")

        if not self.parser.consume_if(TokenType.RPAREN):
            raise self.parser.error("Expected ')' to close array initialization")

        return element_words, element_strings

    def _serialize_array_element(self, start_pos: int, end_pos: int) -> str:
        """Source-faithful rendering of one array element's tokens.

        Word fusion merges an element's pieces into ONE WORD whose ``parts``
        carry the DECODED, quote-stripped piece values (an ANSI-C ``$'a\\tb'``
        arrives as a part valued ``a<TAB>b``). Re-wrapping each part's decoded
        value in its quote (and re-``$``-ing variables) reproduces the
        pre-fusion per-token serialization while — crucially — leaving NO
        backslash escapes in the result. That matters because this string
        becomes the array-init argument's flat text, which the declaration
        builtin looks its structured init up by AFTER unquoted-escape
        processing: a leftover ``\\t`` would make the parse-time key
        (``$'a\\tb'``) miss the runtime lookup (``$'atb'``). A part valued from
        the decoded content has no escapes, so key == lookup.
        """
        out = []
        for token in self.parser.tokens[start_pos:end_pos]:
            if token.parts:
                for p in token.parts:
                    if p.is_variable:
                        # '$' + name ('x' -> $x, '{x}' -> ${x}); keep any quote.
                        v = '$' + p.value
                        out.append(p.quote_type + v + p.quote_type
                                   if p.quote_type else v)
                    elif p.quote_type is not None:
                        out.append(p.quote_type + p.value + p.quote_type)
                    else:
                        out.append(p.value)
            elif token.type == TokenType.STRING and token.quote_type:
                out.append(token.quote_type + token.value + token.quote_type)
            elif token.type == TokenType.VARIABLE:
                out.append('$' + token.value)
            else:
                out.append(token.value)
        return ''.join(out)

    def parse_pipeline(self) -> Pipeline:
        """Parse a pipeline (commands connected by | or |&)."""
        pipeline = Pipeline()
        # Stamp the pipeline's first-token line so $LINENO tracks per pipeline
        # within a multi-line && / || chain (see ASTNode.line).
        pipeline.line = self.parser.peek().line

        # `time [-p]` / `!` prefixes. bash's pipeline_command grammar is
        # RECURSIVE, so the prefixes may repeat and interleave freely:
        # `! time cmd`, `time time cmd`, `time ! time cmd`, `time -p ! cmd`.
        # Each `!` toggles the negation sense (`! ! true` -> 0); repeated
        # `time` still times once. Inside a prefix run the lexer may have
        # left a later `time`/`!` as a plain WORD (its command-position
        # tracking stops at the `-p` word) — an UNQUOTED word spelling
        # `time`/`!` there is still the reserved word (escaped `\!` and
        # quoted forms keep their backslash/STRING type, so they don't
        # match).
        saw_prefix = False
        while True:
            tok = self.parser.peek()
            in_run = saw_prefix and tok.type == TokenType.WORD
            if tok.type == TokenType.TIME or (in_run and tok.value == 'time'):
                self.parser.advance()
                saw_prefix = True
                pipeline.timed = True
                # `-p` (POSIX output format), only as the immediate next word.
                tok = self.parser.peek()
                if tok.type == TokenType.WORD and tok.value == '-p':
                    self.parser.advance()
                    pipeline.time_posix = True
            elif tok.type == TokenType.EXCLAMATION or (in_run and tok.value == '!'):
                self.parser.advance()
                saw_prefix = True
                pipeline.negated = not pipeline.negated
            else:
                break

        # A prefix with no following command is valid ONLY before a list
        # terminator — `;`, newline, or end of input (bash's grammar:
        # `BANG list_terminator` / `timespec list_terminator`). `time`
        # times an empty pipeline (status 0); `!` negates it (status 1).
        # Anything else (`time &&`, `( ! )`, `{ time }`) falls through to
        # parse a command and fails there, exactly like bash (rc 2).
        if saw_prefix and self._at_list_terminator():
            return pipeline

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

    # bash's list_terminator: the ONLY tokens after which a bare `time`/`!`
    # prefix forms a complete (empty) pipeline. Deliberately narrow — bash
    # REJECTS `time &&`, `time |`, `( ! )`, `{ time }`, `time ;;` (rc 2).
    _LIST_TERMINATORS = frozenset({
        TokenType.SEMICOLON, TokenType.NEWLINE, TokenType.EOF,
    })

    def _at_list_terminator(self) -> bool:
        """True if the current token is a list terminator (`;`, newline, or
        end of input), so a bare `time`/`!` prefix is a complete pipeline."""
        return self.parser.peek().type in self._LIST_TERMINATORS

    def parse_pipeline_component(self) -> Command:
        """Parse a single component of a pipeline (simple or compound command).

        Every compound command's body parses back through here for its own
        components, so this is the single chokepoint where NESTING depth
        accumulates — and therefore where the MAX_NESTING_DEPTH guard
        lives. Only compound components count (a simple command inside
        1000 brace groups is at depth 1000, not 1001), and sequential
        components at the same level balance out (increment/decrement
        around each), so flat scripts never approach the limit.
        """
        # `time` is a reserved word only at the START of a pipeline — the
        # prefix loop in parse_pipeline consumed any leading TIME tokens, so
        # one reaching here follows a `|`. bash runs the EXTERNAL time there
        # (`echo a | time cat` -> /usr/bin/time); interpret it as a plain word.
        #
        # Substitute a WORD copy in the parser's OWN token list rather than
        # mutating the token in place: create_context() copied the token LIST
        # but not the token OBJECTS, so an in-place `tok.type = WORD` was
        # visible to the caller and to any other parser sharing the stream.
        # Replacing the list slot leaves every caller-owned token untouched,
        # keeping the parser observationally pure w.r.t. its input (finding 14).
        if self.parser.match(TokenType.TIME):
            idx = self.parser.current
            self.parser.ctx.tokens[idx] = replace(
                self.parser.ctx.tokens[idx],
                type=TokenType.WORD, is_keyword=False)

        compound = self._parse_compound_component()
        if compound is not None:
            return compound
        # Fall back to simple command
        return self.parse_command()

    def _parse_compound_component(self) -> Optional[Command]:
        """Dispatch to the compound-command parsers under the depth guard.

        Returns None when the current token starts a simple command instead.
        """
        if not self.parser.match(TokenType.WHILE, TokenType.UNTIL,
                                 TokenType.FOR, TokenType.IF,
                                 TokenType.CASE, TokenType.SELECT,
                                 TokenType.DOUBLE_LPAREN,
                                 TokenType.DOUBLE_LBRACKET,
                                 TokenType.LPAREN, TokenType.LBRACE):
            return None

        ctx = self.parser.ctx
        ctx.nesting_depth += 1
        try:
            if ctx.nesting_depth > MAX_NESTING_DEPTH:
                raise self.parser.error(
                    f"commands nested too deeply "
                    f"(maximum depth {MAX_NESTING_DEPTH})")

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
            elif self.parser.match(TokenType.LPAREN):
                self._reject_escaped_dollar_paren()
                return self.parse_subshell_group()
            else:  # TokenType.LBRACE (guaranteed by the match above)
                return self.parse_brace_group()
        finally:
            ctx.nesting_depth -= 1

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

        The lexer emits one WORD per shell word (word fusion), so this consumes
        a single word-like token. Delegates to WordBuilder for token-to-Word
        conversion (a fused WORD carries its per-part quote context in its parts;
        ``ctx`` binds embedded ``$()``/``<()``/``>()`` to this parse for nested
        validation).
        """
        if self.parser.match_any(TokenGroups.WORD_LIKE):
            token = self.parser.advance()
            self._check_for_unclosed_expansions(token)
            quote_type = token.quote_type if token.type == TokenType.STRING else None
            return WordBuilder.build_word_from_token(token, quote_type,
                                                     ctx=self.parser.ctx)
        raise self.parser.error("Expected word-like token")

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
            raise self.parser.error(unexpected_token_message(self.parser.peek()))
        self.parser.expect(TokenType.RPAREN)
        self.parser.ctx.pop_construct()

        # Parse any redirections after the subshell
        redirects = self.parser.redirections.parse_redirects()

        # NOTE: '&' is parsed at the and-or-list level (POSIX grammar), not
        # here — `(a) && (b) &` backgrounds the whole list.
        return SubshellGroup(statements=statements, redirects=redirects)

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
            raise self.parser.error(unexpected_token_message(self.parser.peek()))
        self.parser.expect(TokenType.RBRACE)
        self.parser.ctx.pop_construct()

        # Parse any redirections after the brace group
        redirects = self.parser.redirections.parse_redirects()

        # NOTE: '&' is parsed at the and-or-list level (POSIX grammar), not
        # here — `{ a; } && { b; } &` backgrounds the whole list.
        return BraceGroup(statements=statements, redirects=redirects)
