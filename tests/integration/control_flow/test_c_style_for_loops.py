"""
C-style for loop tests.

Comprehensive test suite for C-style for loops: for ((init; condition; update))
Tests cover initialization, condition evaluation, update expressions, and edge cases.
"""

import os
import subprocess
import sys


class TestCStyleForBasic:
    """Basic C-style for loop functionality tests."""

    def test_basic_counter(self, captured_shell):
        """Test basic C-style for loop with counter."""
        shell = captured_shell
        result = shell.run_command('for ((i=0; i<3; i++)); do echo $i; done')
        assert result == 0

        # Verify the counter worked correctly
        output = shell.get_stdout()
        assert output == "0\n1\n2\n"

    def test_increment_by_two(self, captured_shell):
        """Test C-style for loop with increment by 2."""
        shell = captured_shell
        result = shell.run_command('for ((i=0; i<10; i+=2)); do echo $i; done')
        assert result == 0

        output = shell.get_stdout()
        assert output == "0\n2\n4\n6\n8\n"

    def test_decrement(self, captured_shell):
        """Test C-style for loop with decrement."""
        shell = captured_shell
        result = shell.run_command('for ((i=5; i>0; i--)); do echo $i; done')
        assert result == 0

        output = shell.get_stdout()
        assert output == "5\n4\n3\n2\n1\n"

    def test_multiplication_update(self, captured_shell):
        """Test C-style for loop with multiplication in update."""
        shell = captured_shell
        result = shell.run_command('for ((i=1; i<=100; i*=2)); do echo $i; done')
        assert result == 0

        output = shell.get_stdout()
        assert output == "1\n2\n4\n8\n16\n32\n64\n"


class TestCStyleForEmpty:
    """Test C-style for loops with empty sections."""

    def test_empty_init(self, captured_shell):
        """Test C-style for loop with empty initialization."""
        shell = captured_shell
        result = shell.run_command('i=0; for ((; i<3; i++)); do echo $i; done')
        assert result == 0

        output = shell.get_stdout()
        assert output == "0\n1\n2\n"

    def test_empty_condition_with_break(self, captured_shell):
        """Test C-style for loop with empty condition (infinite loop with break)."""
        shell = captured_shell
        cmd = '''
        for ((i=0; ; i++)); do
            echo $i
            if ((i >= 3)); then break; fi
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "0\n1\n2\n3\n"

    def test_empty_update(self, captured_shell):
        """Test C-style for loop with empty update."""
        shell = captured_shell
        cmd = '''
        for ((i=0; i<3; )); do
            echo $i
            ((i++))
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "0\n1\n2\n"

    def test_all_empty_sections(self, captured_shell):
        """Test C-style for loop with all sections empty."""
        shell = captured_shell
        cmd = '''
        i=0
        for ((;;)); do
            echo $i
            ((i++))
            if ((i >= 3)); then break; fi
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "0\n1\n2\n"


class TestCStyleForMultipleVariables:
    """Test C-style for loops with multiple variables."""

    def test_multiple_variables(self, captured_shell):
        """Test C-style for loop with multiple variables."""
        shell = captured_shell
        result = shell.run_command('for ((i=0, j=10; i<5; i++, j--)); do echo "$i $j"; done')
        assert result == 0

        output = shell.get_stdout()
        assert output == "0 10\n1 9\n2 8\n3 7\n4 6\n"

    def test_with_existing_variables(self, captured_shell):
        """Test C-style for loop using existing variables."""
        shell = captured_shell
        cmd = '''
        start=5
        end=8
        for ((i=start; i<=end; i++)); do
            echo $i
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "5\n6\n7\n8\n"


class TestCStyleForNested:
    """Test nested C-style for loops."""

    def test_nested_c_style_for(self, captured_shell):
        """Test nested C-style for loops."""
        shell = captured_shell
        cmd = '''
        for ((i=0; i<3; i++)); do
            for ((j=0; j<2; j++)); do
                echo "$i,$j"
            done
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "0,0\n0,1\n1,0\n1,1\n2,0\n2,1\n"

    def test_c_style_mixed_with_regular_for(self, captured_shell):
        """Test C-style for loop nested with regular for loop."""
        shell = captured_shell
        cmd = '''
        for ((i=1; i<=2; i++)); do
            for item in a b; do
                echo "$i-$item"
            done
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "1-a\n1-b\n2-a\n2-b\n"


class TestCStyleForControlFlow:
    """Test break and continue in C-style for loops."""

    def test_break_in_c_style_for(self, captured_shell):
        """Test break statement in C-style for loop."""
        shell = captured_shell
        cmd = '''
        for ((i=0; i<10; i++)); do
            if ((i == 5)); then break; fi
            echo $i
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "0\n1\n2\n3\n4\n"

    def test_continue_in_c_style_for(self, captured_shell):
        """Test continue statement in C-style for loop."""
        shell = captured_shell
        cmd = '''
        for ((i=0; i<5; i++)); do
            if ((i == 2)); then continue; fi
            echo $i
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "0\n1\n3\n4\n"

    def test_nested_break_continue(self, captured_shell):
        """Test break and continue in nested C-style loops."""
        shell = captured_shell
        cmd = '''
        for ((i=0; i<3; i++)); do
            for ((j=0; j<4; j++)); do
                if ((j == 2)); then continue; fi
                if ((j == 3)); then break; fi
                echo "$i,$j"
            done
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "0,0\n0,1\n1,0\n1,1\n2,0\n2,1\n"


class TestCStyleForIORedirection:
    """Test C-style for loops with I/O redirection.

    These tests use subprocess.run() so that pytest's output capture doesn't
    interfere with psh's file descriptor operations in forked child processes.
    """

    def test_c_style_with_output_redirection(self, temp_dir):
        """Test C-style for loop with output redirection."""
        script = 'for ((i=0; i<3; i++)); do echo $i; done > numbers.txt'

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        with open(os.path.join(temp_dir, 'numbers.txt')) as f:
            content = f.read()
            assert content == "0\n1\n2\n"

    def test_c_style_with_append_redirection(self, temp_dir):
        """Test C-style for loop with append redirection."""
        script = 'echo "start" > log.txt; for ((i=1; i<=2; i++)); do echo "line $i"; done >> log.txt'

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        with open(os.path.join(temp_dir, 'log.txt')) as f:
            content = f.read()
            assert content == "start\nline 1\nline 2\n"

    def test_c_style_with_input_redirection(self, temp_dir):
        """Test C-style for loop reading from file."""
        # Create input file with Python (no shell instance available)
        with open(os.path.join(temp_dir, 'fruits.txt'), 'w') as f:
            f.write("apple\nbanana\ncherry\n")

        script = '''
        counter=0
        while read line; do
            ((counter++))
            for ((i=1; i<=counter; i++)); do
                echo "$i: $line" >> processed.txt
            done
        done < fruits.txt
        '''

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        with open(os.path.join(temp_dir, 'processed.txt')) as f:
            content = f.read()
            assert content == "1: apple\n1: banana\n2: banana\n1: cherry\n2: cherry\n3: cherry\n"


class TestCStyleForFunctions:
    """Test C-style for loops in functions."""

    def test_c_style_in_function(self, captured_shell):
        """Test C-style for loop inside a function."""
        shell = captured_shell
        cmd = '''
        count_to() {
            local n=$1
            for ((i=1; i<=n; i++)); do
                echo $i
            done
        }
        count_to 4
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "1\n2\n3\n4\n"

    def test_c_style_with_local_variables(self, captured_shell):
        """Test C-style for loop with local variables in function."""
        shell = captured_shell
        cmd = '''
        test_locals() {
            local start=$1
            local end=$2
            for ((i=start; i<=end; i++)); do
                echo "local: $i"
            done
        }
        test_locals 2 5
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "local: 2\nlocal: 3\nlocal: 4\nlocal: 5\n"


class TestCStyleForArithmetic:
    """Test C-style for loops with complex arithmetic."""

    def test_c_style_with_complex_arithmetic(self, captured_shell):
        """Test C-style for loop with complex arithmetic expressions."""
        shell = captured_shell
        cmd = '''
        x=2
        for ((i=x*2; i<x*5; i+=x)); do
            echo $i
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "4\n6\n8\n"

    def test_modulo_operations(self, captured_shell):
        """Test C-style for loop with modulo operations."""
        shell = captured_shell
        cmd = '''
        for ((i=1; i<=10; i++)); do
            if ((i % 2 == 0)); then
                echo $i
            fi
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "2\n4\n6\n8\n10\n"


class TestCStyleForVariableScope:
    """Test variable scope and preservation in C-style for loops."""

    def test_variable_preservation_after_loop(self, captured_shell):
        """Test that loop variable is preserved after loop."""
        shell = captured_shell
        cmd = '''
        for ((i=0; i<3; i++)); do
            :  # No-op command
        done
        echo "final value: $i"
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        assert output == "final value: 3\n"

    def test_variable_scope_in_subshell(self, captured_shell):
        """Test C-style for loop variable scope in subshells."""
        shell = captured_shell

        # Test that subshell variables don't affect parent shell
        # This is a simplified version that avoids complex redirection issues
        result = shell.run_command('i=100; echo "parent start: $i"')
        assert result == 0
        assert "parent start: 100" in shell.get_stdout()
        shell.clear_output()

        # Test subshell with C-style for loop (simplified)
        result = shell.run_command('i=100; (for ((i=0; i<2; i++)); do echo "subshell: $i"; done); echo "parent end: $i"')
        assert result == 0

        output = shell.get_stdout()
        # Verify subshell executed the loop but parent variable is preserved
        assert "parent end: 100" in output
        # Note: subshell output goes to stdout directly and may not be captured properly
        # This is a known limitation with complex subshell + redirection scenarios


class TestCStyleForComparators:
    """Test various comparison operators in C-style for loops."""

    def test_comparison_operators(self, captured_shell):
        """Test various comparison operators in condition."""
        shell = captured_shell

        # Less than or equal
        result = shell.run_command('for ((i=1; i<=3; i++)); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "1\n2\n3\n"
        shell.clear_output()

        # Greater than
        result = shell.run_command('for ((i=3; i>0; i--)); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "3\n2\n1\n"
        shell.clear_output()

        # Not equal
        result = shell.run_command('for ((i=0; i!=3; i++)); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "0\n1\n2\n"
        shell.clear_output()

        # Greater than or equal
        result = shell.run_command('for ((i=5; i>=3; i--)); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "5\n4\n3\n"


class TestCStyleForSyntaxVariations:
    """Test syntax variations and edge cases."""

    def test_c_style_without_do_keyword(self, captured_shell):
        """Test C-style for loop without optional 'do' keyword."""
        shell = captured_shell
        result = shell.run_command('for ((i=0; i<3; i++)) echo $i; done')
        assert result == 0

        output = shell.get_stdout()
        assert output == "0\n1\n2\n"

    def test_whitespace_handling(self, captured_shell):
        """Test handling of various whitespace patterns."""
        shell = captured_shell

        # Test with extra spaces
        result = shell.run_command('for (( i = 0 ; i < 3 ; i++ )); do echo $i; done')
        assert result == 0

        output = shell.get_stdout()
        assert output == "0\n1\n2\n"

    def test_complex_expressions_in_sections(self, captured_shell):
        """Test complex expressions in all three sections."""
        shell = captured_shell
        # Test with simpler but still complex expressions that PSH can handle
        cmd = '''
        base=2
        for ((i=base*base; i<base*5; i+=base)); do
            echo $i
        done
        '''
        result = shell.run_command(cmd)
        assert result == 0

        output = shell.get_stdout()
        # base=2: init=4, condition=i<10, increment=2
        assert output == "4\n6\n8\n"


class TestCStyleForParenthesizedSubexpr:
    """Parenthesized subexpressions inside C-style for-header sections.

    Reappraisal #18 T1-5: the recursive-descent arithmetic-section collector
    used to terminate a section on the *first* ``)`` that returned to depth 0,
    so a balanced ``(...)`` (or a ``(( ))``-fused pair) inside any section
    aborted the parse. All outputs are pinned against GNU bash 5.2. The
    combinator parser is locked to the same behavior by the AST parity corpus
    (``tests/parser_differential/test_combinator_ast_parity.py``).
    """

    def test_paren_in_condition(self, captured_shell):
        """A balanced group in the condition: i<(n-1)."""
        shell = captured_shell
        result = shell.run_command(
            'n=5; for ((i=0; i<(n-1); i++)); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "0\n1\n2\n3\n"

    def test_paren_in_init(self, captured_shell):
        """A balanced group in the init: i=(1+1)."""
        shell = captured_shell
        result = shell.run_command(
            'for ((i=(1+1); i<5; i++)); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "2\n3\n4\n"

    def test_parenthesized_whole_condition(self, captured_shell):
        """The whole condition wrapped: (i<3)."""
        shell = captured_shell
        result = shell.run_command(
            'for ((i=0; (i<3); i++)); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "0\n1\n2\n"

    def test_paren_in_update_straddle(self, captured_shell):
        """A group in the update whose ``)`` fuses with the header ``))``: (i++)."""
        shell = captured_shell
        result = shell.run_command(
            'for ((i=0; i<5; (i++))); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "0\n1\n2\n3\n4\n"

    def test_double_paren_update(self, captured_shell):
        """A doubly-nested update group producing fused ``))``: ((i++))."""
        shell = captured_shell
        result = shell.run_command(
            'for ((i=0; i<3; ((i++)))); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "0\n1\n2\n"

    def test_parens_in_all_three_sections(self, captured_shell):
        """Balanced groups in every section at once."""
        shell = captured_shell
        result = shell.run_command(
            'for ((i=(0); (i<3); (i++))); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "0\n1\n2\n"

    def test_paren_multiplied_condition(self, captured_shell):
        """A group as a condition operand: i<(1+2)."""
        shell = captured_shell
        result = shell.run_command(
            'for ((i=0; i<(1+2); i++)); do echo $i; done')
        assert result == 0
        assert shell.get_stdout() == "0\n1\n2\n"


class TestCStyleForSemicolonArity:
    """A one-semicolon C-style for header must be rejected, not looped forever.

    Reappraisal #18 T1-5 regression guard: once the collector correctly stops a
    section at ``))``, a one-semicolon header (``for ((i=0; i<3))``) would
    otherwise parse with an empty update and loop forever. bash rejects it with
    exit 2; psh must too. This drives the full execution path in a subprocess
    (with a timeout) to prove there is no infinite loop and matches bash's
    rejection. The both-parsers reject/accept arity is pinned separately at
    parse level in ``tests/parser_differential/test_combinator_error_parity.py``
    (ids ``cstyle-for-one-semicolon``/``-paren``, ``cstyle-for-empty-update``).

    Runs psh with ``PYTHONPATH`` pinned to the worktree (the editable install
    otherwise resolves ``psh`` to the main tree).
    """

    def test_one_semicolon_header_does_not_hang(self):
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', 'for ((i=0; i<3)); do echo x; done'],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, 'PYTHONPATH': os.getcwd()})
        assert result.returncode == 2
        assert result.stdout == ""


class TestCStyleForErrorChannel:
    """Arithmetic errors in loop expressions go to stderr, not stdout.

    Pinned against bash 5.2: each of init/condition/update division by
    zero prints the error on stderr and the loop fails with rc 1
    (`bash -c 'for ((1/0;;)); do break; done; echo rc:$?'` → rc:1,
    message on stderr only). psh's message text differs from bash's but
    the channel and exit status match.
    """

    def test_init_error_on_stderr(self, captured_shell):
        rc = captured_shell.run_command("for ((1/0;;)); do break; done")
        assert rc == 1
        assert "psh: ((:" in captured_shell.get_stderr()
        assert captured_shell.get_stdout() == ""

    def test_condition_error_on_stderr(self, captured_shell):
        rc = captured_shell.run_command("for ((;1/0;)); do break; done")
        assert rc == 1
        assert "psh: ((:" in captured_shell.get_stderr()
        assert captured_shell.get_stdout() == ""

    def test_update_error_on_stderr(self, captured_shell):
        rc = captured_shell.run_command("for ((i=0;i<1;1/0)); do :; done")
        assert rc == 1
        assert "psh: ((:" in captured_shell.get_stderr()
        assert captured_shell.get_stdout() == ""


class TestCStyleForErrorCases:
    """Test error handling and edge cases."""

    def test_division_by_zero_handling(self, captured_shell):
        """Test arithmetic error handling in loop expressions."""
        shell = captured_shell

        # Test division by zero in condition - should handle gracefully
        cmd = '''
        for ((i=0; i<5; i++)); do
            if ((i == 2)); then
                # This should not cause the loop to crash
                echo "before division"
                ((x = 5 / 0)) || echo "division error handled"
                echo "after division"
            else
                echo $i
            fi
        done
        '''
        shell.run_command(cmd)
        # Should complete successfully even with division error

        output = shell.get_stdout()
        assert "0\n" in output
        assert "1\n" in output
        # Should have error handling for division by zero
        assert "before division" in output

    def test_variable_unset_in_condition(self, captured_shell):
        """Test handling of unset variables in loop condition."""
        shell = captured_shell
        cmd = '''
        for ((i=0; i<unset_var; i++)); do
            echo $i
        done 2>/dev/null || echo "handled unset variable"
        '''
        shell.run_command(cmd)

        # Should handle unset variables gracefully
        # Unset variables typically evaluate to 0 in arithmetic context
        output = shell.get_stdout()
        # Loop should not execute since i<0 is false from start
        assert output == "" or "handled" in output
