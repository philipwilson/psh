"""Regression pins for the [[ ]] UNARY operand Word (appraisal #15, G1).

The unary operand used to be a flattened string that was re-expanded
(tilde + variables) on every evaluation, so a single-quoted operand was
WRONGLY re-expanded: `x=; [[ -n '$x' ]]` reported false (empty) instead of
true (the literal text `$x` is non-empty). It now carries a Word
(UnaryTestExpression.operand_word) expanded quote-aware, the same path as a
binary operand's subject string. Expected values verified against bash 5.2.
"""

from psh.ast_nodes import (
    EnhancedTestStatement,
    UnaryTestExpression,
    Word,
)
from psh.lexer import tokenize
from psh.parser import parse


class TestUnaryOperandQuoting:
    def test_single_quoted_dollar_is_literal_nonempty(self, captured_shell):
        rc = captured_shell.run_command("x=; [[ -n '$x' ]]; echo $?")
        assert rc == 0
        assert captured_shell.get_stdout() == "0\n"

    def test_single_quoted_dollar_is_literal_z_false(self, captured_shell):
        rc = captured_shell.run_command("x=; [[ -z '$x' ]]; echo $?")
        assert rc == 0
        assert captured_shell.get_stdout() == "1\n"

    def test_unquoted_var_still_expands(self, captured_shell):
        rc = captured_shell.run_command("x=; [[ -n $x ]]; echo $?")
        assert rc == 0
        assert captured_shell.get_stdout() == "1\n"

    def test_double_quoted_var_expands(self, captured_shell):
        rc = captured_shell.run_command('x=; [[ -n "$x" ]]; echo $?')
        assert rc == 0
        assert captured_shell.get_stdout() == "1\n"

    def test_single_operand_implicit_n_literal(self, captured_shell):
        rc = captured_shell.run_command("x=; [[ '$x' ]]; echo $?")
        assert rc == 0
        assert captured_shell.get_stdout() == "0\n"

    def test_tilde_operand_expands(self, captured_shell):
        # -z ~ : ~ expands to a non-empty $HOME so -z is false.
        rc = captured_shell.run_command("[[ -z ~ ]]; echo $?")
        assert rc == 0
        assert captured_shell.get_stdout() == "1\n"

    def test_v_operator_uses_variable_name(self, captured_shell):
        rc = captured_shell.run_command("x=1; [[ -v x ]]; echo $?")
        assert rc == 0
        assert captured_shell.get_stdout() == "0\n"

    def test_v_operator_quoted_name(self, captured_shell):
        rc = captured_shell.run_command("x=1; [[ -v 'x' ]]; echo $?")
        assert rc == 0
        assert captured_shell.get_stdout() == "0\n"

    def test_nested_in_function(self, captured_shell):
        rc = captured_shell.run_command(
            "f() { x=; [[ -n '$x' ]]; echo $?; }; f")
        assert rc == 0
        assert captured_shell.get_stdout() == "0\n"

    def test_parser_populates_operand_word(self):
        ast = parse(tokenize("[[ -n '$x' ]]"))

        def find(node, seen=None):
            seen = seen or set()
            if id(node) in seen:
                return None
            seen.add(id(node))
            if isinstance(node, EnhancedTestStatement):
                return node.expression
            import dataclasses
            if dataclasses.is_dataclass(node):
                for f in dataclasses.fields(node):
                    r = find(getattr(node, f.name), seen)
                    if r is not None:
                        return r
            elif isinstance(node, (list, tuple)):
                for it in node:
                    r = find(it, seen)
                    if r is not None:
                        return r
            return None

        expr = find(ast)
        assert isinstance(expr, UnaryTestExpression)
        assert isinstance(expr.operand_word, Word)
        assert expr.operand_word.effective_quote_char == "'"
        # The derived .operand display string still works for consumers.
        assert expr.operand == "$x"
