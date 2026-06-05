"""Variable values are recursively evaluated as arithmetic expressions.

Covers the Batch 1 correctness fix: a variable holding an expression
("2*3"), a base-prefixed value (0x10, 010, 2#101), or a reference to
another variable is resolved like bash inside $(( )).
"""


class TestArithmeticVariableEvaluation:
    def _eval(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out.strip()

    def test_expression_valued_variable(self, shell, capsys):
        assert self._eval(shell, capsys, 'a="2*3"; echo $((a))') == "6"

    def test_expression_valued_variable_in_larger_expr(self, shell, capsys):
        assert self._eval(shell, capsys, 'a="2+3"; echo $((a + 1))') == "6"

    def test_chained_expression_reference(self, shell, capsys):
        assert self._eval(shell, capsys, 'a="2*3"; b=a; echo $((b))') == "6"

    def test_bare_identifier_indirection(self, shell, capsys):
        assert self._eval(shell, capsys, 'a=b; b=42; echo $((a))') == "42"

    def test_hex_valued_variable(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=0x10; echo $((x))') == "16"

    def test_octal_valued_variable(self, shell, capsys):
        # Leading zero is octal in arithmetic context (int("010") would be 10).
        assert self._eval(shell, capsys, 'x=010; echo $((x))') == "8"

    def test_base_n_valued_variable(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=2#101; echo $((x))') == "5"

    def test_plain_decimal_unaffected(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=42; echo $((x + 8))') == "50"

    def test_negative_decimal_unaffected(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=-7; echo $((x * 2))') == "-14"

    def test_circular_reference_is_zero(self, shell, capsys):
        # psh resolves a self-reference to 0 rather than erroring; this is
        # pre-existing safe behavior (bash raises a recursion error).
        assert self._eval(shell, capsys, 'a=a; echo $((a))') == "0"
