"""Contract tests for the canonical :class:`Program` parser root.

The recursive-descent and combinator parsers both return a single ``Program``
node for every parse (see the root-shape removal campaign). This module pins the
structural invariants of that root; the parse-driven invariants
(``test_every_parse_returns_program``, ancestry, line-stamping) are added
alongside the parser change, and behavioral equivalence is covered by the
execution/formatter suites.
"""

import sys

import pytest

from psh.ast_nodes import (
    AndOrList,
    ASTNode,
    FunctionDef,
    Pipeline,
    Program,
    Statement,
    StatementList,
    WhileLoop,
)
from psh.lexer import tokenize
from psh.parser import create_parser, parse, parse_with_heredocs
from psh.parser.recursive_descent.support.utils import (
    parse_with_heredocs as rd_parse_with_heredocs,
)


def _statements(src):
    """The statements the parser produces for *src* (always a Program root)."""
    return list(parse(tokenize(src)).statements)


def _program(src):
    return Program(statements=_statements(src))


class TestProgramStructure:
    """The Program dataclass itself (independent of any parser)."""

    def test_program_is_ast_node(self):
        assert issubclass(Program, ASTNode)

    def test_default_statements_is_empty_list(self):
        assert Program().statements == []

    def test_statements_field_independent_per_instance(self):
        a, b = Program(), Program()
        a.statements.append(AndOrList())
        assert b.statements == []

    def test_holds_statement_instances(self):
        prog = Program(statements=[AndOrList(), AndOrList()])
        assert all(isinstance(s, AndOrList) for s in prog.statements)


class TestProgramVisitors:
    """Every visitor with a Program handler renders/executes a Program."""

    def test_formatter_joins_statements_with_newline(self):
        from psh.visitor import FormatterVisitor
        prog = _program("echo a; echo b")
        assert FormatterVisitor().visit(prog) == "echo a\necho b"

    def test_formatter_background_single_newline(self):
        from psh.visitor import FormatterVisitor
        prog = _program("echo a & echo b")
        out = FormatterVisitor().visit(prog)
        assert out == "echo a &\necho b"
        assert "\n\n" not in out

    def test_formatter_empty_program(self):
        from psh.visitor import FormatterVisitor
        assert FormatterVisitor().visit(Program()) == ""

    def test_debug_ast_renders_program_header(self):
        from psh.visitor import DebugASTVisitor
        out = DebugASTVisitor().visit(_program("echo hi"))
        assert out.startswith("Program")

    def test_validator_traverses_program(self):
        from psh.visitor import ValidatorVisitor
        v = ValidatorVisitor()
        v.visit(_program("echo hi"))  # should not raise

    def test_executor_program_exit_codes(self, captured_shell):
        # true/false produce no stdout, so no capture plumbing is needed to
        # verify visit_Program sequences statements and returns the status.
        assert captured_shell.execute_program(_program("true")) == 0
        assert captured_shell.execute_program(_program("false")) == 1

    def test_executor_program_produces_output(self, captured_shell):
        from io import StringIO
        buf = StringIO()
        saved_sys, saved_shell = sys.stdout, captured_shell.stdout
        sys.stdout = captured_shell.stdout = buf
        try:
            rc = captured_shell.execute_program(_program("echo hi"))
        finally:
            sys.stdout, captured_shell.stdout = saved_sys, saved_shell
        assert rc == 0
        assert buf.getvalue() == "hi\n"


# Sources spanning every root shape the old parser distinguished, plus the
# decorated/pipelined forms that never unwrapped.
EVERY_ROOT_SOURCE = [
    "",                                    # empty input
    "   ",                                 # whitespace only
    "# just a comment",                    # comment-only
    "echo hi",                             # simple command
    "echo a; echo b",                      # multi-statement
    "echo a | cat",                        # pipeline
    "true && false || echo x",             # and-or chain
    "( echo a )",                          # subshell
    "{ echo a; }",                         # brace group
    "while false; do :; done",             # bare while
    "until true; do :; done",              # bare until
    "for i in 1 2; do echo $i; done",      # bare for
    "for ((i=0;i<2;i++)); do :; done",     # bare c-style for
    "if true; then echo y; fi",            # bare if
    "case x in a) echo a;; esac",          # bare case
    "[[ -n x ]]",                          # bare [[ ]]
    "(( 1 + 1 ))",                         # bare (( ))
    "f() { echo hi; }",                    # function definition
    "while false; do :; done | cat",       # compound piped
    "while false; do :; done && echo x",   # compound in and-or
    "while false; do :; done; echo hi",    # compound then simple
    "! while false; do :; done",           # negated compound
    "time while false; do :; done",        # timed compound
    "echo a & echo b",                     # background list
    "echo a &",                            # single background
]


class TestEveryParseReturnsProgram:
    @pytest.mark.parametrize("source", EVERY_ROOT_SOURCE)
    def test_root_is_program(self, source):
        ast = parse(tokenize(source))
        assert isinstance(ast, Program), (
            f"{source!r} produced {type(ast).__name__}, expected Program")

    @pytest.mark.parametrize("source", EVERY_ROOT_SOURCE)
    def test_statements_are_statements(self, source):
        for stmt in parse(tokenize(source)).statements:
            assert isinstance(stmt, Statement), (
                f"{source!r} yielded non-Statement {type(stmt).__name__}")

    @pytest.mark.parametrize("source", EVERY_ROOT_SOURCE)
    def test_no_nested_program_or_statement_list(self, source):
        # Program.statements never contains another Program or a raw
        # StatementList (those live only inside compound bodies).
        for stmt in parse(tokenize(source)).statements:
            assert not isinstance(stmt, (Program, StatementList))

    def test_empty_input_is_empty_program(self):
        assert parse(tokenize("")).statements == []

    def test_heredoc_input_returns_program(self):
        src = "cat <<EOF\nhi\nEOF"
        assert isinstance(parse(tokenize(src)), Program)

    def test_rd_parse_with_heredocs_returns_program(self):
        from psh.lexer import tokenize_with_heredocs
        tokens, hmap = tokenize_with_heredocs("cat <<EOF\nhi\nEOF")
        assert isinstance(rd_parse_with_heredocs(tokens, hmap), Program)

    def test_public_parse_with_heredocs_returns_program(self):
        from psh.lexer import tokenize_with_heredocs
        tokens, hmap = tokenize_with_heredocs("cat <<EOF\nhi\nEOF")
        assert isinstance(parse_with_heredocs(tokens, hmap), Program)

    def test_create_parser_returns_program(self):
        p = create_parser(tokenize("echo hi"), source_text="echo hi")
        assert isinstance(p.parse(), Program)


class TestBareCompoundKeepsAncestry:
    """A bare compound retains its normal AndOrList -> Pipeline ancestry;
    it is NOT unwrapped at the root (the old TopLevel behavior)."""

    def test_bare_compound_wrapped_in_andorlist_pipeline(self):
        ast = parse(tokenize("while false; do :; done"))
        assert len(ast.statements) == 1
        stmt = ast.statements[0]
        assert isinstance(stmt, AndOrList)
        assert len(stmt.pipelines) == 1
        pipeline = stmt.pipelines[0]
        assert isinstance(pipeline, Pipeline)
        assert len(pipeline.commands) == 1
        assert isinstance(pipeline.commands[0], WhileLoop)

    def test_function_def_is_direct_statement(self):
        ast = parse(tokenize("f() { echo hi; }"))
        assert len(ast.statements) == 1
        assert isinstance(ast.statements[0], FunctionDef)


class TestProgramLineStamping:
    """Every statement in a Program carries a $LINENO stamp."""

    def test_all_statements_stamped(self):
        ast = parse(tokenize("echo a\necho b\nwhile false; do :; done"))
        assert ast.statements
        for stmt in ast.statements:
            assert stmt.line is not None, f"{stmt} was not line-stamped"

    def test_line_numbers_track_source_lines(self):
        ast = parse(tokenize("echo a\necho b\necho c"))
        assert [s.line for s in ast.statements] == [1, 2, 3]
