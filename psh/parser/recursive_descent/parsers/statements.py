"""
Statement parsing for PSH shell.

This module handles parsing of statement-level constructs including command lists,
and/or lists, and statement sequencing.
"""

from typing import Optional, Union

from ....ast_nodes import AndOrList, BreakStatement, CommandList, ContinueStatement, Statement
from ....token_types import TokenType
from ..helpers import TokenGroups


class StatementParser:
    """Parser for statement-level constructs."""

    def __init__(self, main_parser):
        """Initialize with reference to main parser."""
        self.parser = main_parser

    def parse_statement(self) -> Optional[Statement]:
        """Parse a statement."""
        # Check for function definition first
        if self.parser.functions.is_function_def():
            return self.parser.functions.parse_function_def()

        # Otherwise parse an and_or_list
        return self.parse_and_or_list()

    def parse_command_list(self) -> CommandList:
        """Parse a command list (statements separated by ; or newline)."""
        command_list = CommandList()
        self.parser.skip_newlines()

        if self.parser.at_end():
            return command_list

        # Parse first statement
        statement = self.parse_statement()
        if statement:
            command_list.statements.append(statement)

        # Parse additional statements
        while self.parser.match_any(TokenGroups.STATEMENT_SEPARATORS):
            self.parser.skip_separators()

            # Check for terminators
            if self.parser.at_end():
                break

            statement = self.parse_statement()
            if statement:
                command_list.statements.append(statement)

        return command_list

    def parse_command_list_until(self, *end_tokens: TokenType) -> CommandList:
        """Parse a command list until one of the end tokens is encountered."""
        command_list = CommandList()
        self.parser.skip_newlines()

        while not self.parser.match(*end_tokens) and not self.parser.at_end():
            statement = self.parse_statement()
            if statement:
                command_list.statements.append(statement)

            # Handle separators but stop at end tokens
            while self.parser.match_any(TokenGroups.STATEMENT_SEPARATORS):
                self.parser.advance()
                if self.parser.match(*end_tokens):
                    break

        return command_list

    def parse_command_list_until_top_level(self) -> CommandList:
        """Parse command list until top-level boundary - minimal implementation."""
        # For now, just delegate to regular command list parsing
        return self.parse_command_list()

    def parse_and_or_list(self) -> Union[AndOrList, BreakStatement, ContinueStatement]:
        """Parse an and/or list - minimal implementation."""
        # Check for break/continue first
        if self.parser.match(TokenType.BREAK):
            return self.parser.control_structures.parse_break_statement()
        elif self.parser.match(TokenType.CONTINUE):
            return self.parser.control_structures.parse_continue_statement()

        # Otherwise parse a simple pipeline and wrap it
        and_or_list = AndOrList()

        pipeline = self.parser.commands.parse_pipeline()
        and_or_list.pipelines.append(pipeline)

        # Handle && and || operators
        while self.parser.match(TokenType.AND_AND, TokenType.OR_OR):
            operator = self.parser.advance()
            and_or_list.operators.append(operator.value)
            self.parser.skip_newlines()
            pipeline = self.parser.commands.parse_pipeline()
            and_or_list.pipelines.append(pipeline)

        # POSIX: a trailing '&' backgrounds the whole and-or list
        if self.parser.match(TokenType.AMPERSAND):
            self.parser.advance()
            if self.parser.match(TokenType.AND_AND, TokenType.OR_OR):
                raise self.parser.error(
                    f"syntax error near unexpected token '{self.parser.peek().value}'")
            self._apply_background(and_or_list)

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
