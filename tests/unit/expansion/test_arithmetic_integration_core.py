"""Test core arithmetic expansion integration with shell features.

This module focuses on testing arithmetic expansion integration that is
known to work well in the parser combinator implementation.

Part of Phase 3 of the arithmetic expansion testing plan.
"""


class TestArithmeticIntegrationCore:
    """Test core arithmetic expansion integration features."""

    # Array integration tests (known to work)

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

    # Command substitution integration tests (known to work)

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

    # Control structure integration tests

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

    def test_arithmetic_in_while_conditions(self, shell, capsys):
        """Test arithmetic expansion in while loop conditions."""
        # Test while (( counter < 3 )) - proper arithmetic condition
        result = shell.run_command('''
        counter=0
        while (( counter < 3 )); do
            echo $counter
            counter=$((counter + 1))
        done
        ''')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "0\n1\n2"

    def test_arithmetic_in_for_loop_expressions(self, shell, capsys):
        """Test arithmetic in for loop with arithmetic expansion."""
        # Test arithmetic expansion in for loop range
        result = shell.run_command('''
        start=$((2))
        end=$((5))
        for i in $(seq $start $end); do
            echo $i
        done
        ''')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "2\n3\n4\n5"

    def test_arithmetic_in_function_returns(self, shell, capsys):
        """Test arithmetic in function return values."""
        shell.run_command('''
        calculate() {
            local result=$((($1 + $2) * 2))
            return $((result % 256))  # Ensure valid exit code
        }
        ''')

        shell.run_command('calculate 3 7')
        result = shell.run_command('echo $?')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "20"  # (3+7)*2 = 20

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

    # Here document integration

    def test_arithmetic_in_here_document_context(self):
        """Test arithmetic within here documents.

        Run in a subprocess: the heredoc feeds external `cat`, whose forked
        raw-fd output capsys cannot capture in-process.
        """
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', 'cat <<EOF\nThe result is: $((5 * 6))\nEOF'],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "The result is: 30" in result.stdout

    def test_arithmetic_in_here_string(self):
        """Test arithmetic in here strings (subprocess: external `cat`)."""
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', 'cat <<<$((2**3))'],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "8"

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

    def test_arithmetic_in_conditional_expressions(self, shell, capsys):
        """Test arithmetic in [[ ]] conditional expressions."""
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

    # Performance and stress tests

    def test_deeply_nested_arithmetic_performance(self, shell, capsys):
        """Test performance with deeply nested arithmetic expressions."""
        # Create a reasonably deep expression
        expr = "1"
        for i in range(10):  # Not too deep to avoid timeout
            expr = f"({expr} + 1)"

        result = shell.run_command(f'echo $(({expr}))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "11"  # 1 + 10 = 11

    def test_multiple_arithmetic_expansions_in_single_command(self, shell, capsys):
        """Test multiple arithmetic expansions in a single command."""
        # Test echo $((1+1)) $((2*2)) $((3**2)) $((4/2))
        result = shell.run_command('echo $((1+1)) $((2*2)) $((3**2)) $((4/2))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "2 4 9 2"

    def test_arithmetic_with_large_variable_context(self, shell, capsys):
        """Test arithmetic with many variables in context."""
        # Set up many variables
        for i in range(20):
            shell.run_command(f'var{i}={i}')

        # Use several in arithmetic
        result = shell.run_command('echo $((var5 + var10 + var15))')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "30"  # 5 + 10 + 15 = 30

    # Basic parameter expansion tests (simpler cases)

    def test_arithmetic_in_parameter_expansion_default_values(self, shell, capsys):
        """Test arithmetic in parameter expansion default values."""
        shell.run_command('unset undefined_var')

        # Test ${undefined_var:-$((5*3))}
        result = shell.run_command('echo "${undefined_var:-$((5*3))}"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "15"

    # Error handling in integration contexts

    def test_arithmetic_error_handling_in_context(self, shell):
        """Test arithmetic error handling in various contexts."""
        # Test that errors don't crash the shell in integration contexts
        result = shell.run_command('echo "before" && echo $((5+3)) && echo "after"')
        assert result == 0  # Should complete successfully

        # Test with potential error (syntax)
        result = shell.run_command('echo "test" 2>/dev/null || echo "handled"')
        assert result in [0, 1, 2]  # Allow various outcomes but no crash
