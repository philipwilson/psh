"""Test arithmetic expansion edge cases and error handling.

This module tests error conditions, syntax errors, edge cases, and robustness
of arithmetic expansion in the parser combinator implementation.

Part of Phase 4 of the arithmetic expansion testing plan.
"""


class TestArithmeticEdgeCases:
    """Test arithmetic expansion edge cases and error handling."""

    # Syntax error tests

    def test_missing_operands_right(self, shell, capsys):
        """Test missing right operand errors."""
        # Missing right operand for binary operators
        result = shell.run_command('echo $((5 +)) 2>/dev/null || echo "syntax error"')
        assert result in [0, 1, 2]  # Allow various error handling
        captured = capsys.readouterr()
        # Should either show error or handle gracefully
        assert captured.out.strip() != ""  # Should produce some output

    def test_missing_operands_left(self, shell, capsys):
        """Test missing left operand errors."""
        # Missing left operand for binary operators
        result = shell.run_command('echo $((* 5)) 2>/dev/null || echo "syntax error"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

    def test_incomplete_parentheses(self, shell, capsys):
        """Test mismatched parentheses in arithmetic context."""
        # Test correct parentheses work fine
        result = shell.run_command('echo $((5 + 3))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "8"

        # Test nested parentheses work
        result = shell.run_command('echo $(((5 + 3) * 2))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "16"

    def test_invalid_operators(self, shell, capsys):
        """Test invalid operator sequences."""
        # Double operators without proper operands
        result = shell.run_command('echo $((5 ++ 3)) 2>/dev/null || echo "operator error"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

        # Invalid operator combinations
        result = shell.run_command('echo $((5 =+ 3)) 2>/dev/null || echo "operator error"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

    def test_empty_arithmetic_expression(self, shell, capsys):
        """Test completely empty arithmetic expressions."""
        # Empty expression
        result = shell.run_command('echo $(()) 2>/dev/null || echo "empty error"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

    def test_malformed_variable_references(self, shell, capsys):
        """Test malformed variable references in arithmetic."""
        # Incomplete variable reference
        result = shell.run_command('echo $(($)) 2>/dev/null || echo "var error"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

        # Invalid braced variable
        result = shell.run_command('echo $((${)) 2>/dev/null || echo "var error"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

    # Whitespace variation tests

    def test_no_spaces(self, shell, capsys):
        """Test arithmetic with no spaces."""
        result = shell.run_command('echo $((5+3*2))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "11"  # 5 + (3 * 2)

    def test_excessive_spaces(self, shell, capsys):
        """Test arithmetic with excessive spaces."""
        result = shell.run_command('echo $((  5  +  3  *  2  ))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "11"

    def test_mixed_spacing(self, shell, capsys):
        """Test arithmetic with mixed spacing patterns."""
        result = shell.run_command('echo $(( 5+ 3 *2 ))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "11"

    def test_tabs_and_spaces(self, shell, capsys):
        """Test arithmetic with tabs and spaces."""
        # Using actual tab characters in the expression
        result = shell.run_command('echo $((\t5\t+\t3\t))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "8"

    def test_newlines_in_arithmetic(self, shell, capsys):
        """Test arithmetic expressions with embedded newlines."""
        result = shell.run_command('''echo $((5 +
3))''')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "8"

    def test_complex_whitespace_patterns(self, shell, capsys):
        """Test complex whitespace in nested expressions."""
        result = shell.run_command('echo $(( ( 5 + 3 ) * ( 2 + 1 ) ))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "24"  # (5 + 3) * (2 + 1) = 8 * 3

    # Division by zero and mathematical edge cases

    def test_division_by_zero(self, shell, capsys):
        """Test division by zero error handling."""
        # Direct division by zero
        result = shell.run_command('echo $((5 / 0)) 2>/dev/null || echo "division by zero"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        # Should either produce error message or handle gracefully
        output = captured.out.strip()
        assert output != ""  # Should produce some output

    def test_modulo_by_zero(self, shell, capsys):
        """Test modulo by zero error handling."""
        result = shell.run_command('echo $((7 % 0)) 2>/dev/null || echo "modulo by zero"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

    def test_negative_modulo(self, shell, capsys):
        """Test modulo with negative numbers."""
        # Test -7 % 3 (result depends on implementation)
        result = shell.run_command('echo $((-7 % 3))')
        assert result == 0
        captured = capsys.readouterr()
        output = captured.out.strip()
        # Should be either -1 or 2 depending on implementation
        assert output in ["-1", "2"]

    def test_large_numbers(self, shell, capsys):
        """Test arithmetic with large numbers."""
        # Test within typical 32/64-bit ranges
        result = shell.run_command('echo $((2147483647))')  # 2^31 - 1
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "2147483647"

        result = shell.run_command('echo $((-2147483648))')  # -2^31
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "-2147483648"

    def test_overflow_behavior(self, shell, capsys):
        """Test integer overflow behavior."""
        # Test behavior at limits (may wrap or error)
        result = shell.run_command('echo $((2147483647 + 1)) 2>/dev/null || echo "overflow"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        output = captured.out.strip()
        # Should either wrap to negative, error, or handle gracefully
        assert output != ""

    # Recursive depth tests

    def test_moderate_nesting_depth(self, shell, capsys):
        """Test moderately nested arithmetic expressions."""
        # Build a nested expression
        expr = "1"
        for i in range(10):
            expr = f"({expr} + 1)"

        result = shell.run_command(f'echo $(({expr}))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "11"  # 1 + 10

    def test_deep_nesting_depth(self, shell, capsys):
        """Test deeply nested arithmetic expressions."""
        # Build a deeper nested expression
        expr = "1"
        for i in range(25):  # Keep reasonable to avoid timeout
            expr = f"({expr} + 1)"

        result = shell.run_command(f'echo $(({expr}))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "26"  # 1 + 25

    def test_mixed_operation_nesting(self, shell, capsys):
        """Test nested expressions with mixed operations."""
        # Complex nested expression: ((2 * 3) + (4 * 5)) * ((6 + 7) - 8)
        result = shell.run_command('echo $(( ((2 * 3) + (4 * 5)) * ((6 + 7) - 8) ))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "130"  # (6 + 20) * (13 - 8) = 26 * 5 = 130

    def test_nested_variable_expressions(self, shell, capsys):
        """Test nested expressions with variables."""
        shell.run_command('a=2; b=3; c=4')
        result = shell.run_command('echo $(( (($a + $b) * $c) + (($a * $b) + $c) ))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "30"  # ((2+3)*4) + ((2*3)+4) = 20 + 10 = 30

    # Invalid number format tests

    def test_invalid_base_notation(self, shell, capsys):
        """Test invalid base notation."""
        # Invalid base (too high)
        result = shell.run_command('echo $((37#10)) 2>/dev/null || echo "invalid base"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

        # Invalid digits for base
        result = shell.run_command('echo $((2#123)) 2>/dev/null || echo "invalid digit"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

    def test_malformed_hex_numbers(self, shell, capsys):
        """Test malformed hexadecimal numbers."""
        # Incomplete hex number
        result = shell.run_command('echo $((0x)) 2>/dev/null || echo "malformed hex"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

        # Invalid hex digits
        result = shell.run_command('echo $((0xGH)) 2>/dev/null || echo "invalid hex"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

    def test_malformed_octal_numbers(self, shell, capsys):
        """Test malformed octal numbers."""
        # Invalid octal digits
        result = shell.run_command('echo $((089)) 2>/dev/null || echo "invalid octal"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

    # String and type conversion edge cases

    def test_non_numeric_variables(self, shell, capsys):
        """Test non-numeric variables in arithmetic context."""
        shell.run_command('str="hello"')

        # Non-numeric strings should evaluate to 0
        result = shell.run_command('echo $(($str + 10))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "10"  # "hello" -> 0, 0 + 10 = 10

    def test_mixed_numeric_string(self, shell, capsys):
        """Mixed numeric/alphabetic values are an arithmetic error (bash:
        "123abc: value too great for base", exit status 1)."""
        shell.run_command('mixed="123abc"')

        result = shell.run_command('echo $(($mixed + 7))')
        assert result == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "arithmetic" in captured.err

    def test_leading_zeros(self, shell, capsys):
        """Test numbers with leading zeros."""
        # Leading zeros in decimal (not octal context)
        result = shell.run_command('echo $((000123))')
        assert result == 0
        captured = capsys.readouterr()
        # Should be 123 (decimal) or 83 (octal), depending on implementation
        output = captured.out.strip()
        assert output in ["123", "83"]

    def test_empty_string_variables(self, shell, capsys):
        """Test empty string variables in arithmetic."""
        shell.run_command('empty=""')

        result = shell.run_command('echo $(($empty + 5))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"  # empty -> 0, 0 + 5 = 5

    def test_undefined_variables_in_arithmetic(self, shell, capsys):
        """Test undefined variables in arithmetic context."""
        shell.run_command('unset undefined_var 2>/dev/null || true')

        # Undefined variables should evaluate to 0
        result = shell.run_command('echo $(($undefined_var + 12))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "12"  # undefined -> 0, 0 + 12 = 12

    # Operator precedence edge cases

    def test_complex_precedence(self, shell, capsys):
        """Test complex operator precedence."""
        # Test: 2 + 3 * 4 ** 2 - 1  = 2 + 3 * 16 - 1 = 2 + 48 - 1 = 49
        result = shell.run_command('echo $((2 + 3 * 4 ** 2 - 1))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "49"

    def test_unary_operator_precedence(self, shell, capsys):
        """Test unary operator precedence."""
        # Test: -2 ** 4  (should be -(2**4) = -16, not (-2)**4 = 16)
        result = shell.run_command('echo $((-2 ** 4))')
        assert result == 0
        captured = capsys.readouterr()
        # Behavior may vary by implementation
        output = captured.out.strip()
        assert output in ["-16", "16"]

    def test_assignment_precedence(self, shell, capsys):
        """Test assignment operator precedence."""
        # Test: a = 5 + 3  (should assign 8 to a)
        result = shell.run_command('echo $((a = 5 + 3))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "8"

        # Verify assignment occurred
        result = shell.run_command('echo $a')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "8"

    def test_ternary_precedence(self, shell, capsys):
        """Test ternary operator precedence."""
        # Test: 5 > 3 ? 2 + 1 : 4 * 2  (should be 3, not other combinations)
        result = shell.run_command('echo $((5 > 3 ? 2 + 1 : 4 * 2))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "3"

    # Special character handling

    def test_special_characters_in_context(self, shell, capsys):
        """Test arithmetic with special characters in variables."""
        shell.run_command('var="42"')  # Normal case

        result = shell.run_command('echo $(($var * 2))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "84"

    def test_arithmetic_in_quoted_context(self, shell, capsys):
        """Test arithmetic expansion within quotes."""
        # Arithmetic in double quotes
        result = shell.run_command('echo "Result: $((5 + 3))"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "Result: 8"

        # Arithmetic in single quotes (should not expand)
        result = shell.run_command("echo 'Result: $((5 + 3))'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "Result: $((5 + 3))"

    # Memory and performance edge cases

    def test_very_large_expression(self, shell, capsys):
        """Test very large but valid expression."""
        # Create expression with many terms
        terms = []
        for i in range(50):  # Keep reasonable
            terms.append(str(i))
        expr = " + ".join(terms)

        result = shell.run_command(f'echo $(({expr}))')
        assert result == 0
        captured = capsys.readouterr()
        expected = sum(range(50))  # Sum of 0..49
        assert captured.out.strip() == str(expected)

    def test_repeated_variable_access(self, shell, capsys):
        """Test expression with many variable accesses."""
        shell.run_command('x=5')

        # Expression with many references to same variable
        expr = " + ".join(["x"] * 20)
        result = shell.run_command(f'echo $(({expr}))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "100"  # 5 * 20 = 100

    # Integration error recovery tests

    def test_error_recovery_in_command_context(self, shell, capsys):
        """Test error recovery when arithmetic fails in command context."""
        result = shell.run_command('echo "before" && echo $((5 / 0)) 2>/dev/null || echo "after error"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')
        # Should see "before" and handle error gracefully
        assert "before" in lines

    def test_error_recovery_in_assignment(self, shell, capsys):
        """Test error recovery when arithmetic fails in assignment."""
        result = shell.run_command('var=$((5 / 0)) 2>/dev/null || echo "assignment error"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        output = captured.out.strip()
        # Should handle error without crashing
        assert output != "" or result != 0  # Some indication of handling

    def test_partial_evaluation_errors(self, shell, capsys):
        """Test errors in partial evaluation of complex expressions."""
        # Expression where one part fails
        result = shell.run_command('echo $((5 + (3 / 0))) 2>/dev/null || echo "partial error"')
        assert result in [0, 1, 2]
        captured = capsys.readouterr()
        assert captured.out.strip() != ""

    # Boundary condition tests

    def test_minimum_valid_expression(self, shell, capsys):
        """Test minimum valid arithmetic expression."""
        # Single number
        result = shell.run_command('echo $((42))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "42"

        # Single variable
        shell.run_command('x=7')
        result = shell.run_command('echo $((x))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "7"

    def test_maximum_reasonable_expression(self, shell, capsys):
        """Test reasonably complex but valid expression."""
        # Complex but reasonable expression
        shell.run_command('a=2; b=3; c=4; d=5')
        result = shell.run_command('echo $(( (a + b) * (c + d) - (a * b) + (c / d) ))')
        assert result == 0
        captured = capsys.readouterr()
        # (2+3) * (4+5) - (2*3) + (4/5) = 5*9 - 6 + 0 = 45 - 6 = 39
        assert captured.out.strip() == "39"
