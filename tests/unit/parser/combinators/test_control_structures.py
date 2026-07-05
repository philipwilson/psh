"""Tests for control structure parsers."""

import pytest

from psh.ast_nodes import (
    BraceGroup,
    CaseConditional,
    CStyleForLoop,
    ForLoop,
    FunctionDef,
    IfConditional,
    SelectLoop,
    SimpleCommand,
    SubshellGroup,
    WhileLoop,
)
from psh.lexer import tokenize
from psh.lexer.token_types import Token, TokenType
from psh.parser.combinators.commands import CommandParsers
from psh.parser.combinators.control_structures import ControlStructureParsers, create_control_structure_parsers
from psh.parser.combinators.parser import ParserCombinatorShellParser


def make_token(token_type: TokenType, value: str, position: int = 0) -> Token:
    """Helper to create a token with minimal required fields."""
    return Token(type=token_type, value=value, position=position)


def parse_combinator(source: str):
    """Parse source through the full (wired, normalized) combinator parser."""
    return ParserCombinatorShellParser().parse(tokenize(source))


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
        """A nested if is parsed as a single nested IfConditional.

        Goes through the full (wired, keyword-normalized) parser: the then-body
        is parsed by recursion, so the inner ``if ... fi`` is one statement — a
        nested ``IfConditional`` — not three flattened tokens-as-commands. The
        recursion consumes the inner ``fi``, leaving the outer ``fi`` for the
        outer if.
        """
        top = parse_combinator('if true; then if false; then echo nested; fi; fi')
        # Bare compound keeps its AndOrList -> Pipeline ancestry under Program.
        outer = top.statements[0].pipelines[0].commands[0]
        assert isinstance(outer, IfConditional)
        assert len(outer.then_part.statements) == 1
        # The nested compound is likewise wrapped in AndOrList -> Pipeline.
        inner = outer.then_part.statements[0].pipelines[0].commands[0]
        assert isinstance(inner, IfConditional)
        assert len(inner.then_part.statements) == 1


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
        """A nested while is parsed as a single nested WhileLoop.

        Through the full parser, the outer body is parsed by recursion: the
        inner ``while ... done`` consumes its own ``done`` and is one statement
        (a nested ``WhileLoop``), leaving the outer ``done`` for the outer loop.
        """
        top = parse_combinator('while true; do while false; do echo nested; done; done')
        # Bare compound keeps its AndOrList -> Pipeline ancestry under Program.
        outer = top.statements[0].pipelines[0].commands[0]
        assert isinstance(outer, WhileLoop)
        assert len(outer.body.statements) == 1
        # The nested compound is likewise wrapped in AndOrList -> Pipeline.
        inner = outer.body.statements[0].pipelines[0].commands[0]
        assert isinstance(inner, WhileLoop)
        assert len(inner.body.statements) == 1


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

    def test_digit_leading_function_name(self):
        """bash accepts a name() function whose name starts with a digit.

        `1func() { ...; }` is a valid function definition in bash (and the
        recursive descent parser); the combinator's name parser must not
        impose an identifier shape. Regression pin for appraisal #18 T2-H.
        """
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        tokens = [
            make_token(TokenType.WORD, "1func"),
            make_token(TokenType.LPAREN, "("),
            make_token(TokenType.RPAREN, ")"),
            make_token(TokenType.LBRACE, "{"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.RBRACE, "}")
        ]

        result = parsers.function_def.parse(tokens, 0)
        assert result.success is True
        assert isinstance(result.value, FunctionDef)
        assert result.value.name == "1func"

    def test_reserved_word_function_name(self):
        """A reserved word (in KEYWORDS) is never a name() function name.

        bash rejects `if() { ...; }` as a syntax error. The commit heuristic
        excludes reserved words, so with a WORD-typed `if` the function-def
        parser declines (success=False) and routes to the command/keyword
        path rather than committing. Mirrors the recursive descent parser's
        is_function_def, which returns False for reserved words.
        """
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        # Hand-built WORD 'if' (real tokenization emits an IF keyword token,
        # which the name parser also rejects since IF is not a name token).
        tokens = [
            make_token(TokenType.WORD, "if"),
            make_token(TokenType.LPAREN, "("),
            make_token(TokenType.RPAREN, ")"),
            make_token(TokenType.LBRACE, "{"),
            make_token(TokenType.WORD, "echo"),
            make_token(TokenType.RBRACE, "}")
        ]

        result = parsers.function_def.parse(tokens, 0)
        assert result.success is False

    def test_permissive_function_names_match_bash(self):
        """bash-valid non-identifier function names parse end to end.

        Names like `a.b`, `foo+bar`, `[x`, `9`, `echo:` and `]` are all legal
        `name()` function names in bash. Each must parse as a FunctionDef
        through the full (wired) combinator. Regression pin for #18 T2-H.
        """
        cases = {
            "9() { echo x; }": "9",
            "123abc() { echo x; }": "123abc",
            "a.b() { echo x; }": "a.b",
            "foo-bar() { echo x; }": "foo-bar",
            "a+b() { echo x; }": "a+b",
            "[x() { echo x; }": "[x",
            "echo:() { echo x; }": "echo:",
            "2=b() { echo x; }": "2=b",
            "]() { echo x; }": "]",
        }
        for source, name in cases.items():
            ast = parse_combinator(source)
            fn = ast.statements[0]
            assert isinstance(fn, FunctionDef), source
            assert fn.name == name, source

    def test_assignment_word_is_not_a_function(self):
        """An assignment word followed by () is never a function definition.

        `arr=()` is an array initialization and `a=b()` / `a[0]=b()` are
        syntax errors in bash — none define a function. The commit heuristic
        excludes assignment words (ASSIGNMENT_WORD_RE) so they route to the
        command/array path. Mirrors the recursive descent parser.
        """
        parsers = ControlStructureParsers()
        command_parsers = CommandParsers()
        parsers.set_command_parsers(command_parsers)

        for name in ("arr=", "a=b", "a[0]=b"):
            tokens = [
                make_token(TokenType.WORD, name),
                make_token(TokenType.LPAREN, "("),
                make_token(TokenType.RPAREN, ")"),
                make_token(TokenType.LBRACE, "{"),
                make_token(TokenType.WORD, "echo"),
                make_token(TokenType.RBRACE, "}")
            ]
            result = parsers.function_def.parse(tokens, 0)
            assert result.success is False, name


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
    """break/continue are NOT statements: they parse as ordinary simple
    commands backed by builtins (bash treats them as builtins, not
    reserved words)."""

    def _parse_single(self, source: str):
        parser = ParserCombinatorShellParser()
        ast = parser.parse(tokenize(source))
        assert len(ast.statements) == 1
        return ast.statements[0]

    @pytest.mark.parametrize("source,args", [
        ("break", ["break"]),
        ("break 2", ["break", "2"]),
        ("continue", ["continue"]),
        ("continue 3", ["continue", "3"]),
    ])
    def test_parses_as_simple_command(self, source, args):
        stmt = self._parse_single(source)
        cmd = stmt.pipelines[0].commands[0] if hasattr(stmt, 'pipelines') else stmt
        assert isinstance(cmd, SimpleCommand)
        assert cmd.args == args


class TestConvenienceFunctions:
    """Test convenience functions for control structure parsing."""

    def test_create_control_structure_parsers(self):
        """Test factory function."""
        parsers = create_control_structure_parsers()
        assert isinstance(parsers, ControlStructureParsers)
        assert parsers.config is not None
        assert parsers.tokens is not None
