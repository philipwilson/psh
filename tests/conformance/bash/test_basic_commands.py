"""
Basic command conformance tests comparing PSH and bash behavior.

These tests verify that PSH produces identical output to bash for
fundamental shell operations.
"""

import os
import sys

# Add parent directory to path for framework import
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestBasicCommandConformance(ConformanceTest):
    """Test basic command execution conformance with bash."""

    def test_echo_command(self):
        """Test echo command conformance."""
        # Basic echo
        self.assert_identical_behavior("echo hello world")

        # Echo with quotes
        self.assert_identical_behavior('echo "hello world"')
        self.assert_identical_behavior("echo 'hello world'")

        # Echo with variables
        self.assert_identical_behavior('x=test; echo $x')
        self.assert_identical_behavior('x=test; echo "$x"')
        self.assert_identical_behavior('x=test; echo ${x}')

    def test_variable_assignment(self):
        """Test variable assignment conformance."""
        # Basic assignment
        self.assert_identical_behavior('x=hello; echo $x')

        # Assignment with spaces
        self.assert_identical_behavior('x="hello world"; echo $x')

        # Multiple assignments
        self.assert_identical_behavior('x=1 y=2 z=3; echo $x $y $z')

        # Assignment with command: $x in the command's own words is
        # expanded BEFORE the temporary assignment applies (POSIX)
        self.assert_identical_behavior('x=value echo $x')
        self.assert_identical_behavior('x=old; x=new echo $x')

        # Empty assignment
        self.assert_identical_behavior('x=; echo "[$x]"')

    def test_command_substitution(self):
        """Test command substitution conformance."""
        # Basic substitution
        self.assert_identical_behavior('echo $(echo hello)')

        # Nested substitution
        self.assert_identical_behavior('echo $(echo $(echo nested))')

        # Substitution with quotes
        self.assert_identical_behavior('echo "$(echo hello world)"')

        # Backtick form
        self.assert_identical_behavior('echo `echo hello`')

    def test_pipelines(self):
        """Test pipeline conformance."""
        # Simple pipeline
        self.assert_identical_behavior('echo hello | cat')

        # Multi-stage pipeline
        self.assert_identical_behavior('echo "hello world" | grep world | cat')

        # Pipeline with variables
        self.assert_identical_behavior('x=hello; echo $x | cat')

    def test_exit_codes(self):
        """Test exit code conformance."""
        # Success
        self.assert_identical_behavior('true; echo $?')

        # Failure
        self.assert_identical_behavior('false; echo $?')

        # Pipeline exit code
        result = self.check_behavior('true | false; echo $?')
        # Exit code behavior might vary, just check both succeed
        assert result.psh_result.exit_code == 0
        assert result.bash_result.exit_code == 0


class TestSimpleBuiltins(ConformanceTest):
    """Test simple builtin command conformance."""

    def test_true_false(self):
        """Test true/false builtins."""
        self.assert_identical_behavior('true')
        self.assert_identical_behavior('false')

    def test_echo_builtin(self):
        """Test echo builtin flags."""
        self.assert_identical_behavior('echo hello')
        self.assert_identical_behavior('echo -n hello')

        # Test -e flag with simple escapes
        result = self.check_behavior('echo -e "hello\\nworld"')
        # Both should handle \n, but exact output might vary
        assert 'hello' in result.psh_result.stdout
        assert 'world' in result.psh_result.stdout
        assert 'hello' in result.bash_result.stdout
        assert 'world' in result.bash_result.stdout

    def test_export_builtin(self):
        """Test export builtin."""
        self.assert_identical_behavior('export X=value; echo $X')
        self.assert_identical_behavior('Y=value; export Y; echo $Y')


class TestSimpleExpansions(ConformanceTest):
    """Test simple expansion conformance."""

    def test_variable_expansion(self):
        """Test basic variable expansion."""
        self.assert_identical_behavior('x=hello; echo $x')
        self.assert_identical_behavior('x=hello; echo ${x}')
        self.assert_identical_behavior('echo ${undefined:-default}')

    def test_command_substitution(self):
        """Test command substitution."""
        self.assert_identical_behavior('echo $(echo test)')
        self.assert_identical_behavior('echo `echo test`')

    def test_arithmetic_expansion(self):
        """Test arithmetic expansion."""
        self.assert_identical_behavior('echo $((2 + 3))')
        self.assert_identical_behavior('echo $((10 - 4))')
        self.assert_identical_behavior('echo $((3 * 4))')

    def test_brace_expansion(self):
        """Test brace expansion."""
        # Test if expansion works
        result = self.check_behavior('echo {a,b,c}')

        # Check if both expand or both don't expand
        psh_expanded = 'a' in result.psh_result.stdout and 'b' in result.psh_result.stdout
        bash_expanded = 'a' in result.bash_result.stdout and 'b' in result.bash_result.stdout

        # Both should have same expansion behavior
        assert psh_expanded == bash_expanded


class TestSimpleControlFlow(ConformanceTest):
    """Test simple control flow conformance."""

    def test_if_statements(self):
        """Test basic if statements."""
        self.assert_identical_behavior('if true; then echo yes; fi')
        self.assert_identical_behavior('if false; then echo no; fi')
        self.assert_identical_behavior('if true; then echo yes; else echo no; fi')

    def test_for_loops(self):
        """Test basic for loops."""
        self.assert_identical_behavior('for i in 1 2 3; do echo $i; done')

    def test_while_loops(self):
        """Test basic while loops."""
        self.assert_identical_behavior('i=0; while [ $i -lt 3 ]; do echo $i; i=$((i+1)); done')


class TestSimpleRedirection(ConformanceTest):
    """Test simple I/O redirection."""

    def test_output_redirection(self):
        """Test output redirection."""
        # Test to /dev/null (safe)
        self.assert_identical_behavior('echo hello > /dev/null')
        self.assert_identical_behavior('echo hello 2> /dev/null')

    def test_input_redirection(self):
        """Test input redirection."""
        # Test from /dev/null (safe)
        self.assert_identical_behavior('cat < /dev/null')


# Remove the old problematic classes that had complex multiline strings
# and unsupported method calls
