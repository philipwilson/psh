"""Essential arithmetic expansion integration tests.

This module tests the core arithmetic expansion integration features that
are confirmed to work well in the parser combinator implementation.
Focuses on fast, reliable tests without complex control structures.

Part of Phase 3 of the arithmetic expansion testing plan.
"""


class TestArithmeticIntegrationEssential:
    """Test essential arithmetic expansion integration features."""

    # Array integration tests (confirmed working)

    def test_arithmetic_in_array_indices(self, shell, capsys):
        """Test arithmetic in array index expressions."""
        shell.run_command('arr=(zero one two three four five)')
        shell.run_command('i=2')
        shell.run_command('j=1')

        # Test ${arr[$((i*2))]} and ${arr[$((i+j))]}
        result = shell.run_command('echo "${arr[$((i*2))]}" "${arr[$((i+j))]}"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "four three"  # arr[4] arr[3]

    def test_arithmetic_in_nested_array_operations(self, shell, capsys):
        """Test complex nested array operations with arithmetic."""
        shell.run_command('indices=(1 3 5)')
        shell.run_command('data=(a b c d e f g h)')

        # Test ${data[${indices[$((0))]}]} - use array element as index
        result = shell.run_command('echo "${data[${indices[$((0))]}]}"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "b"  # data[indices[0]] = data[1] = "b"

    def test_arithmetic_in_array_assignment(self, shell, capsys):
        """Test arithmetic in array assignment contexts."""
        shell.run_command('declare -a result')
        shell.run_command('result[$((2*3))]=42')

        result = shell.run_command('echo ${result[6]}')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "42"

    # Command substitution integration tests (confirmed working)

    def test_arithmetic_within_command_substitution(self, shell, capsys):
        """Test arithmetic expansion within command substitution."""
        # Test $(echo $((5 + 3)))
        result = shell.run_command('echo "$(echo $((5 + 3)))"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "8"

    def test_command_substitution_within_arithmetic(self, shell, capsys):
        """Test command substitution within arithmetic expansion."""
        # Create a function that returns a number
        shell.run_command('get_num() { echo 42; }')

        # Test $(($(get_num) / 2))
        result = shell.run_command('echo $(($(get_num) / 2))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "21"

    def test_nested_command_substitution_arithmetic(self, shell, capsys):
        """Test deeply nested command substitution and arithmetic."""
        shell.run_command('calc() { echo $(($1 * 2)); }')

        # Test $(calc $(echo $((3 + 2))))
        result = shell.run_command('echo "$(calc $(echo $((3 + 2))))"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "10"  # calc(5) = 5*2 = 10

    def test_arithmetic_with_command_substitution_in_variables(self, shell, capsys):
        """Test arithmetic using variables set from command substitution."""
        shell.run_command('num=$(echo 15)')

        # Test $((num + $(echo 25)))
        result = shell.run_command('echo $((num + $(echo 25)))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "40"

    def test_backtick_command_substitution_in_arithmetic(self, shell, capsys):
        """Test backtick command substitution within arithmetic."""
        # Test $((`echo 6` * `echo 7`))
        result = shell.run_command('echo $((`echo 6` * `echo 7`))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "42"

    # Simple control structure integration

    def test_arithmetic_in_if_conditions(self, shell, capsys):
        """Test arithmetic expansion in if statement conditions."""
        shell.run_command('x=10')
        shell.run_command('y=5')

        # Test if (( $((x / y)) > 1 ))
        result = shell.run_command('''
        if (( $((x / y)) > 1 )); then
            echo "greater"
        else
            echo "not greater"
        fi
        ''')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "greater"  # 10/5 = 2 > 1

    def test_arithmetic_in_simple_conditional(self, shell, capsys):
        """Test arithmetic in simple conditional expressions."""
        shell.run_command('a=15')
        shell.run_command('b=10')

        # Test [[ $((a + b)) -gt $((20)) ]]
        result = shell.run_command('''
        if [[ $((a + b)) -gt $((20)) ]]; then
            echo "sum greater than 20"
        else
            echo "sum not greater than 20"
        fi
        ''')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "sum greater than 20"  # 15+10=25 > 20

    # Variable and export integration

    def test_arithmetic_in_export_statements(self, shell, capsys):
        """Test arithmetic in export variable assignments."""
        # Test export VAR=$((10 * 5))
        shell.run_command('export CALC_VAR=$((10 * 5))')

        result = shell.run_command('echo $CALC_VAR')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "50"

    def test_arithmetic_in_variable_assignment(self, shell, capsys):
        """Test arithmetic in regular variable assignments."""
        shell.run_command('result=$((15 + 25))')

        result = shell.run_command('echo $result')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "40"

    def test_arithmetic_in_local_variable_assignment(self, shell, capsys):
        """Test arithmetic in local variable assignments."""
        shell.run_command('''
        test_func() {
            local value=$((10 + 20))
            echo $value
        }
        ''')

        result = shell.run_command('test_func')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "30"

    # Here document integration - moved to advanced tests due to issues

    # Multi-level integration tests

    def test_deeply_nested_expansions(self, shell, capsys):
        """Test deeply nested combination of expansions."""
        shell.run_command('arr=(10 20 30)')
        shell.run_command('idx=1')
        shell.run_command('multiplier=3')

        # Test ${arr[$((idx))]} in arithmetic: $(( ${arr[$((idx))]} * $((multiplier + 1)) ))
        result = shell.run_command('echo $(( ${arr[$((idx))]} * $((multiplier + 1)) ))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "80"  # arr[1] * (3+1) = 20 * 4 = 80

    # Parameter expansion integration (simple cases)

    def test_arithmetic_in_parameter_expansion_default_values(self, shell, capsys):
        """Test arithmetic in parameter expansion default values."""
        shell.run_command('unset undefined_var')

        # Test ${undefined_var:-$((5*3))}
        result = shell.run_command('echo "${undefined_var:-$((5*3))}"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "15"

    def test_arithmetic_in_parameter_expansion_alternative(self, shell, capsys):
        """Test arithmetic in parameter expansion alternative values."""
        shell.run_command('defined_var=hello')

        # Test ${defined_var:+$((2*10))}
        result = shell.run_command('echo "${defined_var:+$((2*10))}"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "20"

    # Performance tests (simple)

    def test_moderately_nested_arithmetic_performance(self, shell, capsys):
        """Test performance with moderately nested arithmetic expressions."""
        # Create a reasonably deep expression
        expr = "1"
        for _ in range(5):  # Keep it moderate to avoid timeout
            expr = f"({expr} + 1)"

        result = shell.run_command(f'echo $(({expr}))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "6"  # 1 + 5 = 6

    def test_multiple_arithmetic_expansions_in_single_command(self, shell, capsys):
        """Test multiple arithmetic expansions in a single command."""
        # Test echo $((1+1)) $((2*2)) $((3**2)) $((4/2))
        result = shell.run_command('echo $((1+1)) $((2*2)) $((3**2)) $((4/2))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "2 4 9 2"

    def test_arithmetic_with_moderate_variable_context(self, shell, capsys):
        """Test arithmetic with several variables in context."""
        # Set up some variables
        for i in range(10):
            shell.run_command(f'var{i}={i}')

        # Use several in arithmetic
        result = shell.run_command('echo $((var2 + var5 + var8))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "15"  # 2 + 5 + 8 = 15

    # Function integration

    def test_arithmetic_in_function_parameters(self, shell, capsys):
        """Test arithmetic in function parameter contexts."""
        shell.run_command('''
        add_func() {
            echo $(($1 + $2))
        }
        ''')

        result = shell.run_command('add_func $((3*2)) $((4+1))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "11"  # add_func(6, 5) = 11

    def test_arithmetic_with_function_return_values(self, shell, capsys):
        """Test arithmetic using function return values."""
        shell.run_command('''
        get_value() {
            return $((5 + 3))
        }
        ''')

        shell.run_command('get_value')
        result = shell.run_command('echo $(($? * 2))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "16"  # (5+3)*2 = 16

    # Error handling (basic)

    def test_arithmetic_error_handling_basic(self, shell):
        """Test basic arithmetic error handling in integration contexts."""
        # Test that basic errors don't crash the shell
        result = shell.run_command('echo "before" && echo $((5+3)) && echo "after"')
        assert result == 0  # Should complete successfully

    def test_arithmetic_with_undefined_variables_in_context(self, shell, capsys):
        """Test arithmetic with undefined variables in integration contexts."""
        shell.run_command('unset undefined_var')

        # Undefined variables should be treated as 0
        result = shell.run_command('echo $((undefined_var + 10))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "10"  # 0 + 10 = 10
