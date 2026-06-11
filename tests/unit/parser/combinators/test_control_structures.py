"""Tests for control structure parsers."""

import pytest

from psh.ast_nodes import (
    BraceGroup,
    BreakStatement,
    CaseConditional,
    ContinueStatement,
    CStyleForLoop,
    ForLoop,
    FunctionDef,
    IfConditional,
    SelectLoop,
    SubshellGroup,
    WhileLoop,
)
from psh.lexer.token_types import Token, TokenType
from psh.parser.combinators.commands import CommandParsers
from psh.parser.combinators.control_structures import ControlStructureParsers, create_control_structure_parsers
from psh.parser.recursive_descent.helpers import ParseError


def make_token(token_type: TokenType, value: str, position: int = 0) -> Token:
    """Helper to create a token with minimal required fields."""
    return Token(type=token_type, value=value, position=position)


class TestIfStatements:
    """Test if/elif/else statement parsing."""

    def test_simple_if_then_fi(self):
        """Test basic if-then-fi structure."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "if"),
            make_token(TokenType.WORD, "test"),
            make_token(TokenType.WORD, "-f"),
            make_token(TokenType.WORD, "file"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "then"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "found"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "fi")
        ]

        result = parsers.if_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, IfConditional)
        assert len(result.value.condition.statements) == 1
        assert len(result.value.then_part.statements) == 1
        assert result.value.elif_parts == []
        assert result.value.else_part is None

    def test_if_with_else(self):
        """Test if-then-else-fi structure."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "if"),
            make_token(TokenType.WORD, "true"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "then"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "yes"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "else"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "no"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "fi")
        ]

        result = parsers.if_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, IfConditional)
        assert result.value.else_part is not None
        assert len(result.value.else_part.statements) == 1

    def test_if_with_elif(self):
        """Test if-then-elif-then-fi structure."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "if"),
            make_token(TokenType.WORD, "test1"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "then"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "first"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "elif"),
            make_token(TokenType.WORD, "test2"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "then"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "second"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "fi")
        ]

        result = parsers.if_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, IfConditional)
        assert len(result.value.elif_parts) == 1
        elif_cond, elif_body = result.value.elif_parts[0]
        assert len(elif_cond.statements) == 1
        assert len(elif_body.statements) == 1

    def test_nested_if_statements(self):
        """Test nested if statements."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "if"),
            make_token(TokenType.WORD, "test1"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "then"),
            make_token(TokenType.WORD, "if"),
            make_token(TokenType.WORD, "test2"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "then"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "nested"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "fi"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "fi")
        ]

        result = parsers.if_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, IfConditional)
        # The nested if/then/fi are parsed as separate commands, not as a nested IfConditional
        # This is a known limitation - nested control structures aren't recognized
        assert len(result.value.then_part.statements) == 3  # if test2; then echo nested; fi


class TestWhileLoops:
    """Test while loop parsing."""

    def test_simple_while_loop(self):
        """Test basic while-do-done structure."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "while"),
            make_token(TokenType.WORD, "test"),
            make_token(TokenType.WORD, "condition"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "do"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "loop"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "done")
        ]

        result = parsers.while_loop.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, WhileLoop)
        assert len(result.value.condition.statements) == 1
        assert len(result.value.body.statements) == 1

    def test_nested_while_loops(self):
        """Test nested while loops."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "while"),
            make_token(TokenType.WORD, "outer"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "do"),
            make_token(TokenType.WORD, "while"),
            make_token(TokenType.WORD, "inner"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "do"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "nested"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "done"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "done")
        ]

        result = parsers.while_loop.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, WhileLoop)
        # Nested while is parsed as separate commands, not as a nested WhileLoop
        # This is a known limitation
        assert len(result.value.body.statements) == 3  # while inner; do echo nested; done


class TestForLoops:
    """Test for loop parsing."""

    def test_traditional_for_loop(self):
        """Test traditional for-in loop."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "for"),
            make_token(TokenType.WORD, "i"),
            make_token(TokenType.WORD, "in"),
            make_token(TokenType.WORD, "a"),
            make_token(TokenType.WORD, "b"),
            make_token(TokenType.WORD, "c"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "do"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.VARIABLE, "i"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "done")
        ]

        result = parsers.for_loop.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, ForLoop)
        assert result.value.variable == "i"
        assert result.value.items == ["a", "b", "c"]
        assert len(result.value.body.statements) == 1

    def test_c_style_for_loop(self):
        """Test C-style for loop."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "for"),
            make_token(TokenType.DOUBLE_LPAREN, "(("),
            make_token(TokenType.WORD, "i"),
            make_token(TokenType.WORD, "="),
            make_token(TokenType.WORD, "0"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "i"),
            make_token(TokenType.WORD, "<"),
            make_token(TokenType.WORD, "10"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "i"),
            make_token(TokenType.WORD, "++"),
            make_token(TokenType.DOUBLE_RPAREN, "))"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "do"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.VARIABLE, "i"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "done")
        ]

        result = parsers.for_loop.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, CStyleForLoop)
        assert result.value.init_expr == "i = 0"
        assert result.value.condition_expr == "i < 10"
        assert result.value.update_expr == "i ++"
        assert len(result.value.body.statements) == 1

    def test_for_loop_with_variable_expansion(self):
        """Test for loop with variable in items."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "for"),
            make_token(TokenType.WORD, "file"),
            make_token(TokenType.WORD, "in"),
            make_token(TokenType.VARIABLE, "FILES"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "do"),
            make_token(TokenType.WORD, "process"),
            make_token(TokenType.VARIABLE, "file"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "done")
        ]

        result = parsers.for_loop.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, ForLoop)
        assert result.value.variable == "file"
        assert result.value.items == ["$FILES"]


class TestCaseStatements:
    """Test case statement parsing."""

    def test_simple_case_statement(self):
        """Test basic case-esac structure."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "case"),
            make_token(TokenType.VARIABLE, "var"),
            make_token(TokenType.WORD, "in"),
            make_token(TokenType.WORD, "pattern1"),
            make_token(TokenType.RPAREN, ")"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "one"),
            make_token(TokenType.DOUBLE_SEMICOLON, ";;"),
            make_token(TokenType.WORD, "pattern2"),
            make_token(TokenType.RPAREN, ")"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "two"),
            make_token(TokenType.DOUBLE_SEMICOLON, ";;"),
            make_token(TokenType.WORD, "esac")
        ]

        result = parsers.case_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, CaseConditional)
        assert result.value.expr == "$var"
        assert len(result.value.items) == 2
        assert result.value.items[0].patterns[0].pattern == "pattern1"
        assert result.value.items[1].patterns[0].pattern == "pattern2"

    def test_case_with_multiple_patterns(self):
        """Test case with multiple patterns per item."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "case"),
            make_token(TokenType.WORD, "option"),
            make_token(TokenType.WORD, "in"),
            make_token(TokenType.WORD, "yes"),
            make_token(TokenType.PIPE, "|"),
            make_token(TokenType.WORD, "y"),
            make_token(TokenType.PIPE, "|"),
            make_token(TokenType.WORD, "Y"),
            make_token(TokenType.RPAREN, ")"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "affirmative"),
            make_token(TokenType.DOUBLE_SEMICOLON, ";;"),
            make_token(TokenType.WORD, "esac")
        ]

        result = parsers.case_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, CaseConditional)
        assert len(result.value.items) == 1
        assert len(result.value.items[0].patterns) == 3
        assert result.value.items[0].patterns[0].pattern == "yes"
        assert result.value.items[0].patterns[1].pattern == "y"
        assert result.value.items[0].patterns[2].pattern == "Y"


class TestSelectLoops:
    """Test select loop parsing."""

    def test_simple_select_loop(self):
        """Test basic select-in-do-done structure."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "select"),
            make_token(TokenType.WORD, "choice"),
            make_token(TokenType.WORD, "in"),
            make_token(TokenType.WORD, "opt1"),
            make_token(TokenType.WORD, "opt2"),
            make_token(TokenType.WORD, "opt3"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "do"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.VARIABLE, "choice"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "done")
        ]

        result = parsers.select_loop.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, SelectLoop)
        assert result.value.variable == "choice"
        assert result.value.items == ["opt1", "opt2", "opt3"]
        assert len(result.value.body.statements) == 1


class TestFunctionDefinitions:
    """Test function definition parsing."""

    def test_posix_function(self):
        """Test POSIX-style function: name() { body }"""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "myfunc"),
            make_token(TokenType.LPAREN, "("),
            make_token(TokenType.RPAREN, ")"),
            make_token(TokenType.LBRACE, "{"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "hello"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.RBRACE, "}")
        ]

        result = parsers.function_def.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, FunctionDef)
        assert result.value.name == "myfunc"
        assert len(result.value.body.statements) == 1

    def test_function_keyword_style(self):
        """Test function keyword style: function name { body }"""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "function"),
            make_token(TokenType.WORD, "myfunc"),
            make_token(TokenType.LBRACE, "{"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "hello"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.RBRACE, "}")
        ]

        result = parsers.function_def.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, FunctionDef)
        assert result.value.name == "myfunc"

    def test_function_keyword_with_parens(self):
        """Test function keyword with parentheses: function name() { body }"""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "function"),
            make_token(TokenType.WORD, "myfunc"),
            make_token(TokenType.LPAREN, "("),
            make_token(TokenType.RPAREN, ")"),
            make_token(TokenType.LBRACE, "{"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "hello"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.RBRACE, "}")
        ]

        result = parsers.function_def.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, FunctionDef)
        assert result.value.name == "myfunc"

    def test_invalid_function_name(self):
        """Test that invalid function names are handled."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        # Name starting with digit - parser currently accepts any WORD token
        tokens = [
            make_token(TokenType.WORD, "1func"),
            make_token(TokenType.LPAREN, "("),
            make_token(TokenType.RPAREN, ")"),
            make_token(TokenType.LBRACE, "{"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.RBRACE, "}")
        ]

        # The parser detects WORD followed by '(' ')' and commits to function
        # parsing.  An invalid name raises ParseError instead of returning
        # success=False, preventing fallthrough to simple-command parsing.
        with pytest.raises(ParseError):
            parsers.function_def.parse(tokens, 0)

    def test_reserved_word_function_name(self):
        """Test that reserved words as function names are handled."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        # Using 'if' as function name - will be parsed as if statement instead
        tokens = [
            make_token(TokenType.WORD, "if"),
            make_token(TokenType.LPAREN, "("),
            make_token(TokenType.RPAREN, ")"),
            make_token(TokenType.LBRACE, "{"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.RBRACE, "}")
        ]

        # 'if' is a reserved word — _build_function_name rejects it.
        # Since the test creates a WORD token (not an IF keyword token),
        # _build_function_def sees WORD+( and commits, then raises ParseError.
        with pytest.raises(ParseError, match="(?i)reserved word"):
            parsers.function_def.parse(tokens, 0)


class TestCompoundCommands:
    """Test compound command parsing."""

    def test_subshell_group(self):
        """Test subshell group (...) syntax."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.LPAREN, "("),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "subshell"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "pwd"),
            make_token(TokenType.RPAREN, ")")
        ]

        result = parsers.subshell_group.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, SubshellGroup)
        assert len(result.value.statements.statements) == 2

    def test_brace_group(self):
        """Test brace group {...} syntax."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.LBRACE, "{"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.WORD, "group"),
            make_token(TokenType.SEMICOLON, ";"),
            make_token(TokenType.WORD, "pwd"),
            make_token(TokenType.RBRACE, "}")
        ]

        result = parsers.brace_group.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, BraceGroup)
        assert len(result.value.statements.statements) == 2


class TestBreakContinue:
    """Test break and continue statement parsing."""

    def test_break_statement(self):
        """Test break statement."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "break")
        ]

        result = parsers.break_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, BreakStatement)
        assert result.value.level == 1  # Default

    def test_break_with_level(self):
        """Test break statement with level."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "break"),
            make_token(TokenType.WORD, "2")
        ]

        result = parsers.break_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, BreakStatement)
        assert result.value.level == 2

    def test_continue_statement(self):
        """Test continue statement."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "continue")
        ]

        result = parsers.continue_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, ContinueStatement)
        assert result.value.level == 1  # Default

    def test_continue_with_level(self):
        """Test continue statement with level."""
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "continue"),
            make_token(TokenType.WORD, "3")
        ]

        result = parsers.continue_statement.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, ContinueStatement)
        assert result.value.level == 3


class TestConvenienceFunctions:
    """Test convenience functions for control structure parsing."""

    def test_create_control_structure_parsers(self):
        """Test factory function."""
        parsers = create_control_structure_parsers()
        assert isinstance(parsers, ControlStructureParsers)
        assert parsers.config is not None
        assert parsers.tokens is not None
