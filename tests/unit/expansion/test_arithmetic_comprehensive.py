"""
Comprehensive arithmetic expansion tests.

Tests for arithmetic expression evaluation, tokenizing, parsing,
and integration with shell expansions. Covers:
- Basic arithmetic operations
- Operator precedence
- Variable handling
- Complex expressions
- Error handling
"""

import pytest


class TestArithmeticTokenizer:
    """Test arithmetic expression tokenizer."""

    def test_basic_numbers(self):
        """Test tokenizing basic numbers."""
        from psh.expansion.arithmetic import ArithTokenizer

        tokenizer = ArithTokenizer("42")
        tokens = tokenizer.tokenize()
        assert len(tokens) == 2  # number + EOF
        assert tokens[0].value == 42

    def test_hex_numbers(self):
        """Test tokenizing hexadecimal numbers."""
        from psh.expansion.arithmetic import ArithTokenizer

        tokenizer = ArithTokenizer("0xFF")
        tokens = tokenizer.tokenize()
        assert tokens[0].value == 255

        tokenizer = ArithTokenizer("0x10")
        tokens = tokenizer.tokenize()
        assert tokens[0].value == 16

    def test_octal_numbers(self):
        """Test tokenizing octal numbers."""
        from psh.expansion.arithmetic import ArithTokenizer

        tokenizer = ArithTokenizer("010")
        tokens = tokenizer.tokenize()
        assert tokens[0].value == 8

        tokenizer = ArithTokenizer("077")
        tokens = tokenizer.tokenize()
        assert tokens[0].value == 63

    def test_basic_operators(self):
        """Test tokenizing basic operators."""
        from psh.expansion.arithmetic import ArithTokenizer

        tokenizer = ArithTokenizer("1 + 2 * 3")
        tokens = tokenizer.tokenize()
        values = [t.value for t in tokens[:-1]]  # Exclude EOF
        assert values == [1, '+', 2, '*', 3]

    def test_comparison_operators(self):
        """Test tokenizing comparison operators."""
        from psh.expansion.arithmetic import ArithTokenizer

        tokenizer = ArithTokenizer("a < b && c >= d")
        tokens = tokenizer.tokenize()
        values = [t.value for t in tokens[:-1]]
        assert values == ['a', '<', 'b', '&&', 'c', '>=', 'd']

    def test_assignment_operators(self):
        """Test tokenizing assignment operators."""
        from psh.expansion.arithmetic import ArithTokenizer

        tokenizer = ArithTokenizer("x = 5, x += 3")
        tokens = tokenizer.tokenize()
        values = [t.value for t in tokens[:-1]]
        assert values == ['x', '=', 5, ',', 'x', '+=', 3]

    def test_increment_decrement(self):
        """Test tokenizing increment/decrement operators."""
        from psh.expansion.arithmetic import ArithTokenizer

        tokenizer = ArithTokenizer("++x + y--")
        tokens = tokenizer.tokenize()
        values = [t.value for t in tokens[:-1]]
        assert values == ['++', 'x', '+', 'y', '--']


class TestArithmeticParser:
    """Test arithmetic expression parser."""

    def test_simple_expression(self):
        """Test parsing simple expressions."""
        from psh.expansion.arithmetic import ArithParser, ArithTokenizer

        tokenizer = ArithTokenizer("2 + 3")
        tokens = tokenizer.tokenize()
        parser = ArithParser(tokens)
        ast = parser.parse()
        assert ast is not None

    def test_precedence(self):
        """Test operator precedence parsing."""
        from psh.expansion.arithmetic import ArithParser, ArithTokenizer

        # Test that multiplication has higher precedence than addition
        tokenizer = ArithTokenizer("2 + 3 * 4")
        tokens = tokenizer.tokenize()
        parser = ArithParser(tokens)
        ast = parser.parse()
        # Should parse as 2 + (3 * 4), not (2 + 3) * 4
        assert ast.op.name == 'PLUS'
        assert ast.right.op.name == 'MULTIPLY'

    def test_parentheses(self):
        """Test parentheses override precedence."""
        from psh.expansion.arithmetic import ArithParser, ArithTokenizer

        tokenizer = ArithTokenizer("(2 + 3) * 4")
        tokens = tokenizer.tokenize()
        parser = ArithParser(tokens)
        ast = parser.parse()
        # Should parse as (2 + 3) * 4
        assert ast.op.name == 'MULTIPLY'
        assert ast.left.op.name == 'PLUS'

    def test_ternary_operator(self):
        """Test ternary operator parsing."""
        from psh.expansion.arithmetic import ArithParser, ArithTokenizer

        tokenizer = ArithTokenizer("x > 0 ? x : -x")
        tokens = tokenizer.tokenize()
        parser = ArithParser(tokens)
        ast = parser.parse()
        assert hasattr(ast, 'condition')
        assert hasattr(ast, 'true_expr')
        assert hasattr(ast, 'false_expr')


class TestArithmeticEvaluator:
    """Test arithmetic expression evaluator."""

    def test_basic_arithmetic(self, shell):
        """Test basic arithmetic operations."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        assert evaluate_arithmetic("2 + 2", shell) == 4
        assert evaluate_arithmetic("10 - 3", shell) == 7
        assert evaluate_arithmetic("4 * 5", shell) == 20
        assert evaluate_arithmetic("20 / 4", shell) == 5
        assert evaluate_arithmetic("17 % 5", shell) == 2
        assert evaluate_arithmetic("2 ** 8", shell) == 256

    def test_precedence_evaluation(self, shell):
        """Test operator precedence in evaluation."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        assert evaluate_arithmetic("2 + 3 * 4", shell) == 14
        assert evaluate_arithmetic("(2 + 3) * 4", shell) == 20
        assert evaluate_arithmetic("2 * 3 + 4", shell) == 10
        assert evaluate_arithmetic("2 * (3 + 4)", shell) == 14

    def test_comparison_operators(self, shell):
        """Test comparison operators."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        assert evaluate_arithmetic("5 > 3", shell) == 1
        assert evaluate_arithmetic("3 > 5", shell) == 0
        assert evaluate_arithmetic("5 >= 5", shell) == 1
        assert evaluate_arithmetic("5 < 3", shell) == 0
        assert evaluate_arithmetic("3 <= 3", shell) == 1
        assert evaluate_arithmetic("5 == 5", shell) == 1
        assert evaluate_arithmetic("5 != 3", shell) == 1

    def test_logical_operators(self, shell):
        """Test logical operators."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        assert evaluate_arithmetic("1 && 1", shell) == 1
        assert evaluate_arithmetic("1 && 0", shell) == 0
        assert evaluate_arithmetic("0 || 1", shell) == 1
        assert evaluate_arithmetic("0 || 0", shell) == 0
        assert evaluate_arithmetic("!0", shell) == 1
        assert evaluate_arithmetic("!5", shell) == 0

    def test_bitwise_operators(self, shell):
        """Test bitwise operators."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        assert evaluate_arithmetic("5 & 3", shell) == 1  # 101 & 011 = 001
        assert evaluate_arithmetic("5 | 3", shell) == 7  # 101 | 011 = 111
        assert evaluate_arithmetic("5 ^ 3", shell) == 6  # 101 ^ 011 = 110
        assert evaluate_arithmetic("~0", shell) == -1  # Bash uses 32-bit signed integers
        assert evaluate_arithmetic("~5", shell) == -6  # Bash behavior: ~5 = -6
        assert evaluate_arithmetic("4 << 2", shell) == 16
        assert evaluate_arithmetic("16 >> 2", shell) == 4

    def test_variable_expansion(self, shell):
        """Test variable expansion in arithmetic."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        shell.state.set_variable('x', '10')
        assert evaluate_arithmetic("x", shell) == 10
        assert evaluate_arithmetic("x + 5", shell) == 15
        assert evaluate_arithmetic("x * 2", shell) == 20

    def test_variable_assignment(self, shell):
        """Test variable assignment in arithmetic."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        evaluate_arithmetic("x = 10", shell)
        assert shell.state.get_variable('x') == '10'

        evaluate_arithmetic("x += 5", shell)
        assert shell.state.get_variable('x') == '15'

        evaluate_arithmetic("x *= 2", shell)
        assert shell.state.get_variable('x') == '30'

    def test_increment_decrement(self, shell):
        """Test increment and decrement operators."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        shell.state.set_variable('x', '5')

        # Pre-increment
        assert evaluate_arithmetic("++x", shell) == 6
        assert shell.state.get_variable('x') == '6'

        # Post-increment
        assert evaluate_arithmetic("x++", shell) == 6
        assert shell.state.get_variable('x') == '7'

        # Pre-decrement
        assert evaluate_arithmetic("--x", shell) == 6
        assert shell.state.get_variable('x') == '6'

        # Post-decrement
        assert evaluate_arithmetic("x--", shell) == 6
        assert shell.state.get_variable('x') == '5'

    def test_ternary_operator(self, shell):
        """Test ternary conditional operator."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        assert evaluate_arithmetic("1 ? 10 : 20", shell) == 10
        assert evaluate_arithmetic("0 ? 10 : 20", shell) == 20

        shell.state.set_variable('x', '5')
        assert evaluate_arithmetic("x > 0 ? x : -x", shell) == 5

        shell.state.set_variable('x', '-3')
        assert evaluate_arithmetic("x > 0 ? x : -x", shell) == 3

    def test_comma_operator(self, shell):
        """Test comma operator."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        # Comma operator evaluates both but returns rightmost
        assert evaluate_arithmetic("3, 5", shell) == 5

        # With side effects
        evaluate_arithmetic("x = 10, y = 20", shell)
        assert shell.state.get_variable('x') == '10'
        assert shell.state.get_variable('y') == '20'

        assert evaluate_arithmetic("x = 5, x + 10", shell) == 15

    def test_complex_expressions(self, shell):
        """Test complex arithmetic expressions."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        # Fibonacci-like calculation
        shell.state.set_variable('a', '1')
        shell.state.set_variable('b', '1')
        result = evaluate_arithmetic("c = a + b, a = b, b = c, c", shell)
        assert result == 2
        assert shell.state.get_variable('a') == '1'
        assert shell.state.get_variable('b') == '2'
        assert shell.state.get_variable('c') == '2'

    def test_division_by_zero(self, shell):
        """Test division by zero error handling."""
        from psh.expansion.arithmetic import ArithmeticError, evaluate_arithmetic

        with pytest.raises(ArithmeticError, match="Division by zero"):
            evaluate_arithmetic("5 / 0", shell)

        with pytest.raises(ArithmeticError, match="Division by zero"):
            evaluate_arithmetic("5 % 0", shell)

    def test_empty_expression(self, shell):
        """Test empty expression evaluation."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        # Empty expression evaluates to 0
        assert evaluate_arithmetic("", shell) == 0

    def test_non_numeric_variables(self, shell):
        """Test non-numeric variable handling."""
        from psh.expansion.arithmetic import evaluate_arithmetic

        # Non-numeric strings evaluate to 0
        shell.state.set_variable('text', 'hello')
        assert evaluate_arithmetic("text", shell) == 0
        assert evaluate_arithmetic("text + 5", shell) == 5


class TestArithmeticCommandErrorChannel:
    """((expr)) errors go to stderr with rc 1, matching bash 5.2.

    Probe: `bash -c '((1/0)); echo rc:$?'` prints the division-by-0
    message on stderr only and rc:1; psh matches the channel and rc
    (message text differs: "psh: ((: Division by zero").
    """

    def test_division_by_zero_command_stderr_and_rc(self, captured_shell):
        rc = captured_shell.run_command("((1/0))")
        assert rc == 1
        assert "psh: ((:" in captured_shell.get_stderr()
        assert captured_shell.get_stdout() == ""

    def test_script_continues_after_arithmetic_error(self, captured_shell):
        rc = captured_shell.run_command("((1/0)); echo rc:$?")
        assert rc == 0
        assert captured_shell.get_stdout() == "rc:1\n"


class TestArithmeticIntegration:
    """Test arithmetic expansion integration with shell."""

    def test_basic_arithmetic_expansion(self, shell, capsys):
        """Test basic arithmetic expansion in commands."""
        shell.run_command("echo $((2 + 2))")
        captured = capsys.readouterr()
        assert "4" in captured.out

    def test_arithmetic_with_variables(self, shell, capsys):
        """Test arithmetic with variable expansion."""
        shell.run_command("x=10")
        shell.run_command("y=3")
        shell.run_command("echo $((x + y))")
        captured = capsys.readouterr()
        assert "13" in captured.out

    def test_arithmetic_assignment(self, shell, capsys):
        """Test arithmetic assignment in expansion."""
        shell.run_command("echo $((x = 5 * 4))")
        captured = capsys.readouterr()
        assert "20" in captured.out
        assert shell.state.get_variable('x') == '20'

    def test_nested_arithmetic(self, shell, capsys):
        """Test nested arithmetic expressions."""
        shell.run_command("echo $(( (2 + 3) * (4 + 5) ))")
        captured = capsys.readouterr()
        assert "45" in captured.out

    def test_arithmetic_in_conditionals(self, shell):
        """Test arithmetic in conditional statements."""
        # Test arithmetic in if statements
        result = shell.run_command("if [ $((5 > 3)) -eq 1 ]; then echo yes; fi")
        assert result == 0

    def test_multiple_arithmetic_expansions(self, shell, capsys):
        """Test multiple arithmetic expansions in one command."""
        shell.run_command("echo $((2 + 2)) plus $((3 * 3)) equals $((4 + 9))")
        captured = capsys.readouterr()
        assert "4" in captured.out
        assert "9" in captured.out
        assert "13" in captured.out

    def test_arithmetic_with_hex(self, shell, capsys):
        """Test arithmetic with hexadecimal numbers."""
        shell.run_command("echo $((0xFF))")
        captured = capsys.readouterr()
        assert "255" in captured.out

        shell.run_command("echo $((0x10 + 0x20))")
        captured = capsys.readouterr()
        assert "48" in captured.out

    def test_arithmetic_with_octal(self, shell, capsys):
        """Test arithmetic with octal numbers."""
        shell.run_command("echo $((010))")
        captured = capsys.readouterr()
        assert "8" in captured.out

        shell.run_command("echo $((010 + 020))")
        captured = capsys.readouterr()
        assert "24" in captured.out

    def test_arithmetic_errors(self, shell, capsys):
        """Test arithmetic error handling in shell context."""
        result = shell.run_command("echo $((5 / 0))")
        captured = capsys.readouterr()
        # Should handle error gracefully - either show error or return 0
        assert result != 0 or "0" in captured.out or "error" in captured.err

    def test_arithmetic_side_effects(self, shell, capsys):
        """Test arithmetic assignments have side effects."""
        shell.run_command("echo $((x = 10, y = x + 5, x * y))")
        captured = capsys.readouterr()
        assert "150" in captured.out  # 10 * 15

        assert shell.state.get_variable('x') == '10'
        assert shell.state.get_variable('y') == '15'

    def test_arithmetic_in_assignment(self, shell):
        """Test arithmetic expansion in variable assignment."""
        shell.run_command("result=$((2 ** 10))")
        assert shell.state.get_variable('result') == '1024'

    def test_arithmetic_in_array_index(self, shell, capsys):
        """Test arithmetic in array indexing."""
        shell.run_command("arr=(zero one two three)")
        shell.run_command("echo ${arr[$((1 + 1))]}")
        captured = capsys.readouterr()
        assert "two" in captured.out

    def test_arithmetic_in_for_loop(self, shell, capsys):
        """Test arithmetic in for loop ranges."""
        shell.run_command("for i in $(seq 1 $((2 + 3))); do echo $i; done")
        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')
        assert len(lines) == 5
        assert "1" in captured.out
        assert "5" in captured.out

    def test_arithmetic_with_command_substitution(self, shell, capsys):
        """Test arithmetic with command substitution."""
        shell.run_command("echo $(($(echo 5) + $(echo 3)))")
        captured = capsys.readouterr()
        assert "8" in captured.out
