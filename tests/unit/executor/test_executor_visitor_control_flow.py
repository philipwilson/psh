"""
Executor visitor control flow unit tests.

Tests ExecutorVisitor functionality for control flow operations including
logical operators (&&, ||), control structures (if/while/for/case),
and loop control statements (break/continue).
"""



class TestLogicalOperators:
    """Test logical operators (&& and ||) execution."""

    def test_and_operator_success_path(self, shell, capsys):
        """Test && operator when first command succeeds."""
        result = shell.run_command("true && echo 'second command'")
        assert result == 0

        captured = capsys.readouterr()
        assert "second command" in captured.out

    def test_and_operator_failure_path(self, shell, capsys):
        """Test && operator when first command fails."""
        result = shell.run_command("false && echo 'should not print'")
        assert result == 1  # Should return failure status

        captured = capsys.readouterr()
        assert "should not print" not in captured.out

    def test_or_operator_success_path(self, shell, capsys):
        """Test || operator when first command succeeds."""
        result = shell.run_command("true || echo 'should not print'")
        assert result == 0

        captured = capsys.readouterr()
        assert "should not print" not in captured.out

    def test_or_operator_failure_path(self, shell, capsys):
        """Test || operator when first command fails."""
        result = shell.run_command("false || echo 'second command'")
        assert result == 0  # Should succeed due to second command

        captured = capsys.readouterr()
        assert "second command" in captured.out

    def test_chained_logical_operators(self, shell, capsys):
        """Test chaining multiple logical operators."""
        result = shell.run_command("true && echo 'first' && echo 'second'")
        assert result == 0

        captured = capsys.readouterr()
        assert "first" in captured.out
        assert "second" in captured.out

    def test_mixed_logical_operators(self, shell, capsys):
        """Test mixing && and || operators."""
        result = shell.run_command("false || echo 'from or' && echo 'from and'")
        assert result == 0

        captured = capsys.readouterr()
        assert "from or" in captured.out
        assert "from and" in captured.out


class TestConditionalStatements:
    """Test if/then/else statement execution."""

    def test_simple_if_true(self, shell, capsys):
        """Test simple if statement with true condition."""
        script = '''
        if true; then
            echo "condition was true"
        fi
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "condition was true" in captured.out

    def test_simple_if_false(self, shell, capsys):
        """Test simple if statement with false condition."""
        script = '''
        if false; then
            echo "should not print"
        fi
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "should not print" not in captured.out

    def test_if_else_true_path(self, shell, capsys):
        """Test if/else with true condition."""
        script = '''
        if true; then
            echo "true path"
        else
            echo "false path"
        fi
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "true path" in captured.out
        assert "false path" not in captured.out

    def test_if_else_false_path(self, shell, capsys):
        """Test if/else with false condition."""
        script = '''
        if false; then
            echo "true path"
        else
            echo "false path"
        fi
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "true path" not in captured.out
        assert "false path" in captured.out

    def test_if_elif_else_chain(self, shell, capsys):
        """Test if/elif/else chain."""
        script = '''
        VAR=2
        if [ "$VAR" -eq 1 ]; then
            echo "one"
        elif [ "$VAR" -eq 2 ]; then
            echo "two"
        else
            echo "other"
        fi
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "two" in captured.out
        assert "one" not in captured.out
        assert "other" not in captured.out


class TestLoopStatements:
    """Test while and for loop execution."""

    def test_while_loop_execution(self, shell, capsys):
        """Test basic while loop execution."""
        script = '''
        counter=0
        while [ "$counter" -lt 3 ]; do
            echo "count: $counter"
            counter=$((counter + 1))
        done
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "count: 0" in captured.out
        assert "count: 1" in captured.out
        assert "count: 2" in captured.out
        assert "count: 3" not in captured.out

    def test_for_loop_with_list(self, shell, capsys):
        """Test for loop with explicit list."""
        script = '''
        for item in apple banana cherry; do
            echo "fruit: $item"
        done
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "fruit: apple" in captured.out
        assert "fruit: banana" in captured.out
        assert "fruit: cherry" in captured.out

    def test_for_loop_with_range(self, shell, capsys):
        """Test for loop with numeric range."""
        script = '''
        for num in 1 2 3; do
            echo "number: $num"
        done
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "number: 1" in captured.out
        assert "number: 2" in captured.out
        assert "number: 3" in captured.out

    def test_nested_loops(self, shell, capsys):
        """Test nested loop execution."""
        script = '''
        for outer in 1 2; do
            for inner in a b; do
                echo "$outer$inner"
            done
        done
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "1a" in captured.out
        assert "1b" in captured.out
        assert "2a" in captured.out
        assert "2b" in captured.out


class TestCaseStatements:
    """Test case statement execution."""

    def test_simple_case_match(self, shell, capsys):
        """Test basic case statement with pattern matching."""
        script = '''
        value="apple"
        case "$value" in
            apple)
                echo "found apple"
                ;;
            banana)
                echo "found banana"
                ;;
            *)
                echo "found other"
                ;;
        esac
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "found apple" in captured.out
        assert "found banana" not in captured.out
        assert "found other" not in captured.out

    def test_case_wildcard_match(self, shell, capsys):
        """Test case statement with wildcard patterns."""
        script = '''
        filename="test.txt"
        case "$filename" in
            *.txt)
                echo "text file"
                ;;
            *.log)
                echo "log file"
                ;;
            *)
                echo "other file"
                ;;
        esac
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "text file" in captured.out
        assert "log file" not in captured.out
        assert "other file" not in captured.out

    def test_case_multiple_patterns(self, shell, capsys):
        """Test case statement with multiple patterns per case."""
        script = '''
        value="two"
        case "$value" in
            one|1)
                echo "number one"
                ;;
            two|2)
                echo "number two"
                ;;
            *)
                echo "other number"
                ;;
        esac
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "number two" in captured.out
        assert "number one" not in captured.out
        assert "other number" not in captured.out

    def test_case_no_match(self, shell, capsys):
        """Test case statement with no matching patterns."""
        script = '''
        value="xyz"
        case "$value" in
            apple)
                echo "found apple"
                ;;
            banana)
                echo "found banana"
                ;;
            *)
                echo "found other"
                ;;
        esac
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "found other" in captured.out
        assert "found apple" not in captured.out
        assert "found banana" not in captured.out


class TestLoopControl:
    """Test break and continue statements."""

    def test_break_in_for_loop(self, shell, capsys):
        """Test break statement in for loop."""
        script = '''
        for i in 1 2 3 4 5; do
            if [ "$i" -eq 3 ]; then
                break
            fi
            echo "number: $i"
        done
        echo "after loop"
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "number: 1" in captured.out
        assert "number: 2" in captured.out
        assert "number: 3" not in captured.out
        assert "number: 4" not in captured.out
        assert "after loop" in captured.out

    def test_continue_in_for_loop(self, shell, capsys):
        """Test continue statement in for loop."""
        script = '''
        for i in 1 2 3 4 5; do
            if [ "$i" -eq 3 ]; then
                continue
            fi
            echo "number: $i"
        done
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "number: 1" in captured.out
        assert "number: 2" in captured.out
        assert "number: 3" not in captured.out
        assert "number: 4" in captured.out
        assert "number: 5" in captured.out

    def test_break_in_while_loop(self, shell, capsys):
        """Test break statement in while loop."""
        script = '''
        counter=0
        while [ "$counter" -lt 10 ]; do
            counter=$((counter + 1))
            if [ "$counter" -eq 3 ]; then
                break
            fi
            echo "count: $counter"
        done
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "count: 1" in captured.out
        assert "count: 2" in captured.out
        assert "count: 3" not in captured.out

    def test_break_outside_loop_warns(self, captured_shell):
        """break outside a loop warns on stderr but exits 0 (bash)."""
        result = captured_shell.run_command("break")
        assert result == 0
        assert "break" in captured_shell.get_stderr()

    def test_continue_outside_loop_warns(self, captured_shell):
        """continue outside a loop warns on stderr but exits 0 (bash)."""
        result = captured_shell.run_command("continue")
        assert result == 0
        assert "continue" in captured_shell.get_stderr()


class TestComplexControlFlow:
    """Test complex combinations of control flow structures."""

    def test_if_in_loop(self, shell, capsys):
        """Test if statement inside loop."""
        script = '''
        for i in 1 2 3 4 5; do
            if [ "$i" -gt 3 ]; then
                echo "big: $i"
            else
                echo "small: $i"
            fi
        done
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "small: 1" in captured.out
        assert "small: 2" in captured.out
        assert "small: 3" in captured.out
        assert "big: 4" in captured.out
        assert "big: 5" in captured.out

    def test_case_in_loop(self, shell, capsys):
        """Test case statement inside loop."""
        script = '''
        for item in apple 123 banana; do
            case "$item" in
                [0-9]*)
                    echo "number: $item"
                    ;;
                *)
                    echo "text: $item"
                    ;;
            esac
        done
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "text: apple" in captured.out
        assert "number: 123" in captured.out
        assert "text: banana" in captured.out

    def test_nested_if_statements(self, shell, capsys):
        """Test nested if statements."""
        script = '''
        value=15
        if [ "$value" -gt 10 ]; then
            echo "greater than 10"
            if [ "$value" -gt 20 ]; then
                echo "greater than 20"
            else
                echo "between 10 and 20"
            fi
        fi
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "greater than 10" in captured.out
        assert "between 10 and 20" in captured.out
        assert "greater than 20" not in captured.out

    def test_loop_with_logical_operators(self, shell, capsys):
        """Test loops combined with logical operators."""
        script = '''
        for i in 1 2 3; do
            true && echo "true branch: $i" || echo "false branch: $i"
        done
        '''

        result = shell.run_command(script)
        assert result == 0

        captured = capsys.readouterr()
        assert "true branch: 1" in captured.out
        assert "true branch: 2" in captured.out
        assert "true branch: 3" in captured.out
        assert "false branch" not in captured.out
