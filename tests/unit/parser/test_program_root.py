"""Contract tests for the canonical :class:`Program` parser root.

The recursive-descent and combinator parsers both return a single ``Program``
node for every parse (see the root-shape removal campaign). This module pins the
structural invariants of that root; the parse-driven invariants
(``test_every_parse_returns_program``, ancestry, line-stamping) are added
alongside the parser change, and behavioral equivalence is covered by the
execution/formatter suites.
"""

import sys

from psh.ast_nodes import AndOrList, ASTNode, Program
from psh.lexer import tokenize
from psh.parser import parse


def _statements(src):
    """Statements the current parser produces for *src* (root shape agnostic).

    Handles the Program root as well as the transitional TopLevel/StatementList
    roots so these visitor tests exercise the new Program handlers from the very
    first commit, before the parser is switched over.
    """
    root = parse(tokenize(src))
    if hasattr(root, 'statements'):
        return list(root.statements)
    flat = []
    for item in root.items:  # TopLevel.items: Statement or StatementList
        flat.extend(item.statements if hasattr(item, 'statements') else [item])
    return flat


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
