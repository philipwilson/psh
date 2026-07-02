"""
Unit tests for arithmetic expansion in PSH.

Tests cover:
- Basic arithmetic operations (+, -, *, /, %)
- Comparison operators (<, >, <=, >=, ==, !=)
- Logical operators (&&, ||, !)
- Bitwise operators (&, |, ^, ~, <<, >>)
- Assignment operators (=, +=, -=, etc.)
- Increment/decrement (++, --)
- Ternary operator (? :)
- Parentheses and precedence
- Variable references in arithmetic
- Nested arithmetic expressions
"""



class TestBasicArithmetic:
    """Test basic arithmetic operations."""

    def test_addition(self, shell, capsys):
        """Test addition operation."""
        shell.run_command('echo $((5 + 3))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "8"

    def test_subtraction(self, shell, capsys):
        """Test subtraction operation."""
        shell.run_command('echo $((10 - 4))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "6"

    def test_multiplication(self, shell, capsys):
        """Test multiplication operation."""
        shell.run_command('echo $((6 * 7))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "42"

    def test_division(self, shell, capsys):
        """Test division operation."""
        shell.run_command('echo $((20 / 4))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"

        # Integer division
        shell.run_command('echo $((7 / 2))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "3"

    def test_modulo(self, shell, capsys):
        """Test modulo operation."""
        shell.run_command('echo $((10 % 3))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

    def test_power(self, shell, capsys):
        """Test the ** power operator."""
        shell.run_command('echo $((2 ** 3))')
        captured = capsys.readouterr()
        assert captured.out.strip() == '8'
        # Should be 8 if supported, or might be an error

    def test_negative_numbers(self, shell, capsys):
        """Test negative numbers."""
        shell.run_command('echo $((-5 + 3))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "-2"

        shell.run_command('echo $((5 + -3))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "2"


class TestComparisonOperators:
    """Test comparison operators."""

    def test_less_than(self, shell, capsys):
        """Test < operator."""
        shell.run_command('echo $((5 < 10))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

        shell.run_command('echo $((10 < 5))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "0"

    def test_greater_than(self, shell, capsys):
        """Test > operator."""
        shell.run_command('echo $((10 > 5))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

    def test_less_equal(self, shell, capsys):
        """Test <= operator."""
        shell.run_command('echo $((5 <= 5))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

        shell.run_command('echo $((6 <= 5))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "0"

    def test_greater_equal(self, shell, capsys):
        """Test >= operator."""
        shell.run_command('echo $((5 >= 5))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

    def test_equal(self, shell, capsys):
        """Test == operator."""
        shell.run_command('echo $((5 == 5))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

        shell.run_command('echo $((5 == 6))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "0"

    def test_not_equal(self, shell, capsys):
        """Test != operator."""
        shell.run_command('echo $((5 != 6))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"


class TestLogicalOperators:
    """Test logical operators."""

    def test_logical_and(self, shell, capsys):
        """Test && operator."""
        shell.run_command('echo $((1 && 1))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

        shell.run_command('echo $((1 && 0))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "0"

    def test_logical_or(self, shell, capsys):
        """Test || operator."""
        shell.run_command('echo $((1 || 0))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

        shell.run_command('echo $((0 || 0))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "0"

    def test_logical_not(self, shell, capsys):
        """Test ! operator."""
        shell.run_command('echo $((!0))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"

        shell.run_command('echo $((!1))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "0"


class TestBitwiseOperators:
    """Test bitwise operators."""

    def test_bitwise_and(self, shell, capsys):
        """Test & operator."""
        shell.run_command('echo $((5 & 3))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "1"  # 0101 & 0011 = 0001

    def test_bitwise_or(self, shell, capsys):
        """Test | operator."""
        shell.run_command('echo $((5 | 3))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "7"  # 0101 | 0011 = 0111

    def test_bitwise_xor(self, shell, capsys):
        """Test ^ operator."""
        shell.run_command('echo $((5 ^ 3))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "6"  # 0101 ^ 0011 = 0110

    def test_bitwise_not(self, shell, capsys):
        """Test ~ operator."""
        # This is tricky as it depends on integer size
        shell.run_command('echo $((~0))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "-1"

    def test_left_shift(self, shell, capsys):
        """Test << operator."""
        shell.run_command('echo $((2 << 3))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "16"  # 2 * 2^3

    def test_right_shift(self, shell, capsys):
        """Test >> operator."""
        shell.run_command('echo $((16 >> 2))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "4"  # 16 / 2^2


class TestVariableArithmetic:
    """Test arithmetic with variables."""

    def test_variable_reference(self, shell, capsys):
        """Test variable references in arithmetic."""
        shell.run_command('X=10')
        shell.run_command('echo $((X + 5))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "15"

    def test_variable_assignment(self, shell, capsys):
        """Test variable assignment in arithmetic."""
        shell.run_command('echo $((X = 20))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "20"

        shell.run_command('echo $X')
        captured = capsys.readouterr()
        assert captured.out.strip() == "20"

    def test_compound_assignment(self, shell, capsys):
        """Test compound assignment operators."""
        shell.run_command('X=10')
        shell.run_command('echo $((X += 5))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "15"

        shell.run_command('echo $((X -= 3))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "12"

        shell.run_command('echo $((X *= 2))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "24"

        shell.run_command('echo $((X /= 4))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "6"

    def test_increment_decrement(self, shell, capsys):
        """Test increment and decrement operators."""
        shell.run_command('X=5')

        # Pre-increment
        shell.run_command('echo $((++X))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "6"

        # Post-increment
        shell.run_command('echo $((X++))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "6"

        shell.run_command('echo $X')
        captured = capsys.readouterr()
        assert captured.out.strip() == "7"

        # Pre-decrement
        shell.run_command('echo $((--X))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "6"

        # Post-decrement
        shell.run_command('echo $((X--))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "6"

        shell.run_command('echo $X')
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"


class TestComplexExpressions:
    """Test complex arithmetic expressions."""

    def test_precedence(self, shell, capsys):
        """Test operator precedence."""
        # Multiplication before addition
        shell.run_command('echo $((2 + 3 * 4))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "14"  # Not 20

        # Parentheses override precedence
        shell.run_command('echo $(((2 + 3) * 4))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "20"

    def test_ternary_operator(self, shell, capsys):
        """Test ternary conditional operator."""
        shell.run_command('X=5')
        shell.run_command('echo $((X > 0 ? X : -X))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"

        shell.run_command('X=-5')
        shell.run_command('echo $((X > 0 ? X : -X))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"

    def test_comma_operator(self, shell, capsys):
        """Test comma operator."""
        # Comma evaluates both but returns last
        shell.run_command('echo $((X = 5, Y = 10, X + Y))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "15"

        shell.run_command('echo "$X $Y"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "5 10"

    def test_nested_expressions(self, shell, capsys):
        """Test nested arithmetic expressions."""
        shell.run_command('X=2; Y=3')
        shell.run_command('echo $(($((X + 1)) * $((Y + 1))))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "12"  # 3 * 4


class TestNumberFormats:
    """Test different number formats."""

    def test_decimal(self, shell, capsys):
        """Test decimal numbers."""
        shell.run_command('echo $((42))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "42"

    def test_octal(self, shell, capsys):
        """Test octal numbers."""
        shell.run_command('echo $((010))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "8"

        shell.run_command('echo $((077))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "63"

    def test_hexadecimal(self, shell, capsys):
        """Test hexadecimal numbers."""
        shell.run_command('echo $((0xFF))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "255"

        shell.run_command('echo $((0x10))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "16"

    def test_base_notation(self, shell, capsys):
        """Test base#number notation."""
        # Binary
        shell.run_command('echo $((2#1010))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "10"

        # Base 8
        shell.run_command('echo $((8#77))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "63"

        # Base 16
        shell.run_command('echo $((16#FF))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "255"


class TestArithmeticErrors:
    """Test error handling in arithmetic expansion."""

    def test_division_by_zero(self, shell, capsys):
        """Test division by zero error."""
        exit_code = shell.run_command('echo $((1 / 0))')
        # Bash returns 1 for arithmetic errors
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "division" in captured.err.lower() or "divide" in captured.err.lower()
        # Output should be empty (command doesn't execute on arithmetic error)
        assert captured.out.strip() == ""

    def test_undefined_variable(self, shell, capsys):
        """Test undefined variable (should be treated as 0)."""
        shell.run_command('unset UNDEF')
        shell.run_command('echo $((UNDEF + 5))')
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"

    def test_invalid_syntax(self, shell, capsys):
        """Test invalid arithmetic syntax."""
        exit_code = shell.run_command('echo $((2 +))')
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "syntax" in captured.err.lower() or "unexpected" in captured.err.lower()

        # Note: $((2 + + 3)) is actually valid (unary plus)
        exit_code = shell.run_command('echo $((2 + + 3))')
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"


class TestArithmeticCommand:
    """Test (( )) arithmetic command syntax."""

    def test_arithmetic_command(self, shell, capsys):
        """Test standalone arithmetic command."""
        exit_code = shell.run_command('(( 1 + 1 == 2 ))')
        assert exit_code == 0

        exit_code = shell.run_command('(( 1 + 1 == 3 ))')
        assert exit_code == 1

    def test_arithmetic_in_condition(self, shell, capsys):
        """Test arithmetic in if conditions."""
        shell.run_command('if (( 5 > 3 )); then echo "yes"; else echo "no"; fi')
        captured = capsys.readouterr()
        assert captured.out.strip() == "yes"

        shell.run_command('if (( 3 > 5 )); then echo "yes"; else echo "no"; fi')
        captured = capsys.readouterr()
        assert captured.out.strip() == "no"

    def test_c_style_for_loop(self, shell, capsys):
        """Test C-style for loop with arithmetic."""
        cmd = '''
        for ((i=0; i<3; i++)); do
            echo $i
        done
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert captured.out.strip() == "0\n1\n2"
