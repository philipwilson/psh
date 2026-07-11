"""
Statement parsing for PSH shell.

This module handles parsing of statement-level constructs including command lists,
and/or lists, and statement sequencing.
"""

from ....ast_nodes import AndOrList, Statement, StatementList
from ....lexer.token_types import TokenType
from ..helpers import TokenGroups, unexpected_token_message
from .base import ParserSubcomponent


class StatementParser(ParserSubcomponent):
    """Parser for statement-level constructs."""


    def parse_statement(self) -> Statement:
        """Parse a statement.

        Stamps the parsed node with the (buffer-relative) line of its first
        token for ``$LINENO``. This is the single chokepoint every nested
        statement list funnels through (loop/if/case/function bodies), so it
        covers them all; the source processor later offsets the stamp to an
        absolute line. See ``ASTNode.line``.
        """
        start_line = self.parser.peek().line

        # Check for function definition first
        if self.parser.functions.is_function_def():
            stmt: Statement = self.parser.functions.parse_function_def()
        else:
            # Otherwise parse an and_or_list
            stmt = self.parse_and_or_list()

        if stmt.line is None:
            stmt.line = start_line
        return stmt

    def parse_command_list(self) -> StatementList:
        """Parse a command list (statements separated by ; or newline)."""
        command_list = StatementList()
        self.parser.skip_newlines()

        if self.parser.at_end():
            return command_list

        # Parse first statement
        statement = self.parse_statement()
        if statement:
            command_list.statements.append(statement)
        self._require_statement_boundary()

        # Parse additional statements
        while self.parser.match_any(TokenGroups.STATEMENT_SEPARATORS):
            self._consume_interstatement_separators()

            # Check for terminators
            if self.parser.at_end():
                break

            statement = self.parse_statement()
            if statement:
                command_list.statements.append(statement)
            self._require_statement_boundary()

        return command_list

    def _consume_interstatement_separators(self) -> None:
        """Consume one statement's terminator plus following blank lines.

        A statement is terminated by a single ``;`` / newline (a trailing
        ``&`` is consumed earlier by ``parse_and_or_list``). Only blank lines
        may follow before the next statement begins; a *second* ``;`` is left
        in place so the next ``parse_statement`` rejects the empty command —
        matching bash, where ``echo a; ; echo b`` (and ``echo a\\n; echo b``)
        is a syntax error, not two commands.
        """
        if self.parser.match_any(TokenGroups.STATEMENT_SEPARATORS):
            self.parser.advance()
            self.parser.skip_newlines()

    def parse_command_list_until(self, *end_tokens: TokenType) -> StatementList:
        """Parse a command list until one of the end tokens is encountered.

        May return an EMPTY list when the end token is already current (e.g. an
        empty ``case`` branch ``a) ;;``, which bash allows). For positions where
        bash requires at least one command — every loop/if body and condition —
        use :meth:`parse_required_command_list_until` instead.
        """
        command_list = StatementList()
        self.parser.skip_newlines()

        while not self.parser.match(*end_tokens) and not self.parser.at_end():
            statement = self.parse_statement()
            if statement:
                command_list.statements.append(statement)
            self._require_statement_boundary(*end_tokens)

            # Consume the statement's terminator and any blank lines, stopping
            # at a second `;` (left for parse_statement to reject). An end
            # token reached here is caught by the outer loop condition.
            self._consume_interstatement_separators()

        return command_list

    def _require_statement_boundary(self, *end_tokens: TokenType) -> None:
        """Require the statement just parsed to have ended at a legal boundary.

        bash validates statement boundaries at parse time: after a statement
        only a separator (``;``/newline — or the ``&`` parse_and_or_list
        already consumed), the enclosing construct's terminator, or end of
        input may come next. Anything else is a syntax error — ``echo (ls)``
        is NOT ``echo`` followed by a subshell to silently execute.
        """
        if (self.parser.at_end()
                or self.parser.match_any(TokenGroups.STATEMENT_SEPARATORS)
                or (end_tokens and self.parser.match(*end_tokens))):
            return
        # A statement that consumed a trailing '&' is already delimited; the
        # next token legitimately starts a new statement (`echo a & echo b`).
        if self.parser.tokens[self.parser.current - 1].type == TokenType.AMPERSAND:
            return
        raise self.parser.error(
            f"syntax error near unexpected token '{self.parser.peek().value}'")

    def parse_required_command_list_until(self, *end_tokens: TokenType) -> StatementList:
        """Parse a command list that must contain at least one statement.

        bash rejects empty compound-command bodies and conditions at PARSE
        time, not at runtime: ``while ...; do done`` and ``if then ...; fi`` are
        syntax errors (an empty ``do`` body would otherwise be an infinite loop,
        an empty ``then`` body a silent no-op). This is the required-position
        twin of :meth:`parse_command_list_until`; the guard mirrors
        ``CommandParser.parse_brace_group``. (Separator-only bodies like
        ``do ; done`` are already rejected earlier, when ``parse_statement``
        fails on the leading separator.)
        """
        command_list = self.parse_command_list_until(*end_tokens)
        if not command_list.statements:
            raise self.parser.error(unexpected_token_message(self.parser.peek()))
        return command_list

    def parse_and_or_list(self) -> AndOrList:
        """Parse an and/or list."""
        and_or_list = AndOrList()

        pipeline = self.parser.commands.parse_pipeline()
        and_or_list.pipelines.append(pipeline)

        # Handle && and || operators
        self.parse_and_or_tail(and_or_list)

        # POSIX: a trailing '&' backgrounds the whole and-or list. '&' is
        # itself a separator, so another operator right after it ('&& b',
        # '| cat', '; c') is a syntax error in bash — while ';;' (case) and
        # closing keywords ('& fi', '& }') remain legal.
        if self.parser.match(TokenType.AMPERSAND):
            self.parser.advance()
            if self.parser.match(TokenType.AND_AND, TokenType.OR_OR,
                                 TokenType.PIPE, TokenType.PIPE_AND,
                                 TokenType.SEMICOLON):
                raise self.parser.error(
                    f"syntax error near unexpected token '{self.parser.peek().value}'")
            self._apply_background(and_or_list)

        return and_or_list

    def parse_and_or_tail(self, and_or_list: AndOrList) -> AndOrList:
        """Consume trailing `&& pipeline` / `|| pipeline` continuations.

        Shared by every place an and-or chain can continue (plain lists,
        pipelines, control structures used as a chain head).
        """
        while self.parser.match(TokenType.AND_AND, TokenType.OR_OR):
            operator = self.parser.advance()
            and_or_list.operators.append(operator.value)
            self.parser.skip_newlines()
            and_or_list.pipelines.append(self.parser.commands.parse_pipeline())
        return and_or_list

    @staticmethod
    def _apply_background(and_or_list: AndOrList) -> None:
        """Mark a parsed and-or list as background.

        Single simple-command and single-pipeline cases keep the legacy
        per-command flag (the executor's direct job-control paths);
        everything else backgrounds the whole list via a subshell.
        """
        from ....ast_nodes import BraceGroup, SimpleCommand, SubshellGroup
        if len(and_or_list.pipelines) == 1:
            commands = and_or_list.pipelines[0].commands
            if commands and isinstance(commands[-1], SimpleCommand):
                commands[-1].background = True
                return
            if len(commands) == 1 and isinstance(commands[0], (SubshellGroup, BraceGroup)):
                commands[0].background = True
                return
        and_or_list.background = True
