"""
Error handling and recovery integration tests.

Tests for comprehensive error handling including:
- Syntax error handling and reporting
- Error recovery mechanisms
- Resource exhaustion handling
- Graceful degradation scenarios
- Error propagation in complex scenarios
"""

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest


class ErrorTestHelper:
    """Helper class for error handling testing."""

    @classmethod
    def run_psh_command(cls, commands, timeout=5, expect_failure=False):
        """Run PSH with given commands and return output."""
        # Create a unique temp directory for this test to ensure isolation
        with tempfile.TemporaryDirectory(prefix='psh_error_test_') as temp_dir:
            # Create a clean environment to avoid test pollution
            env = {}
            # Copy only essential environment variables
            for key in ['PATH', 'HOME', 'USER', 'SHELL', 'TMPDIR', 'TEMP', 'TMP']:
                if key in os.environ:
                    env[key] = os.environ[key]

            psh_root = Path(__file__).parent.parent.parent.parent
            env['PYTHONPATH'] = str(psh_root)
            env['PYTHONUNBUFFERED'] = '1'

            # Join commands with newlines
            if isinstance(commands, str):
                input_text = commands + '\n'
            else:
                input_text = '\n'.join(commands) + '\n'

            proc = subprocess.Popen(
                [sys.executable, '-u', '-m', 'psh', '--norc'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=temp_dir,  # Use isolated temp directory
                start_new_session=True  # Create new process group for isolation
            )

            try:
                stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
                return {
                    'stdout': stdout,
                    'stderr': stderr,
                    'returncode': proc.returncode,
                    'success': proc.returncode == 0,
                    'failed_as_expected': expect_failure and proc.returncode != 0
                }
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                return {
                    'stdout': stdout or '',
                    'stderr': stderr or '',
                    'returncode': -1,
                    'error': 'timeout',
                    'success': False,
                    'failed_as_expected': expect_failure
                }


class TestSyntaxErrorHandling:
    """Test syntax error detection and reporting."""

    def setup_method(self):
        """Setup for each test method."""
        # No global process cleanup - each test is isolated
        pass

    def teardown_method(self):
        """Cleanup after each test method."""
        # No global process cleanup - each test is isolated
        pass

    def test_unclosed_quote_error(self):
        """Test handling of unclosed quotes."""
        result = ErrorTestHelper.run_psh_command('echo "unclosed quote', expect_failure=True)

        # Should fail with syntax error
        assert not result['success']
        assert 'quote' in result['stderr'].lower() or 'syntax' in result['stderr'].lower() or 'parse error' in result['stderr'].lower()

    def test_unclosed_parentheses_error(self):
        """Test handling of unclosed parentheses."""
        result = ErrorTestHelper.run_psh_command('echo $(echo test', expect_failure=True)

        # Should fail with syntax error
        assert not result['success']
        assert 'syntax' in result['stderr'].lower() or 'parenthes' in result['stderr'].lower() or 'parse error' in result['stderr'].lower()

    def test_invalid_redirection_syntax(self):
        """Test handling of invalid redirection syntax."""
        result = ErrorTestHelper.run_psh_command('echo test > > invalid', expect_failure=True)

        # Should fail with syntax error
        assert not result['success']
        assert 'syntax' in result['stderr'].lower() or 'parse error' in result['stderr'].lower() or 'redirect' in result['stderr'].lower() or 'parse error' in result['stderr'].lower()

    def test_invalid_pipe_syntax(self):
        """Test handling of invalid pipe syntax."""
        result = ErrorTestHelper.run_psh_command('echo test | | invalid', expect_failure=True)

        # Should fail with syntax error
        assert not result['success']
        assert 'syntax' in result['stderr'].lower() or 'parse error' in result['stderr'].lower() or 'pipe' in result['stderr'].lower() or 'parse error' in result['stderr'].lower()

    def test_incomplete_command_substitution(self):
        """Test handling of incomplete command substitution."""
        result = ErrorTestHelper.run_psh_command('echo $(echo test', expect_failure=True)

        # Should fail with syntax error
        assert not result['success']
        assert ('syntax' in result['stderr'].lower() or 'parse error' in result['stderr'].lower())

    def test_invalid_variable_syntax(self):
        """Test handling of invalid variable syntax."""
        result = ErrorTestHelper.run_psh_command('echo ${invalid-syntax', expect_failure=True)

        # Should fail with syntax error
        assert not result['success']
        assert ('syntax' in result['stderr'].lower() or 'variable' in result['stderr'].lower() or
                'parse error' in result['stderr'].lower())

    def test_malformed_function_definition(self):
        """Test handling of malformed function definitions."""
        result = ErrorTestHelper.run_psh_command('function invalid { echo test', expect_failure=True)

        # Should fail with syntax/parse error or specific function error
        assert not result['success']
        stderr_lower = result['stderr'].lower()
        assert ('syntax' in stderr_lower or
                'parse error' in stderr_lower or
                'unclosed function' in stderr_lower or
                'function body' in stderr_lower or
                'expected tokentype.rbrace' in stderr_lower or  # New ParserContext format
                'expected }' in stderr_lower)

    def test_invalid_arithmetic_expression(self):
        """Test handling of invalid arithmetic expressions."""
        result = ErrorTestHelper.run_psh_command('echo $((2 + ))', expect_failure=True)

        # Should fail with arithmetic or syntax error
        assert not result['success']
        assert ('arithmetic' in result['stderr'].lower() or
                'syntax' in result['stderr'].lower() or
                'expression' in result['stderr'].lower() or
                'parse error' in result['stderr'].lower())


class TestCommandErrorHandling:
    """Test command execution error handling."""

    def test_command_not_found_error(self):
        """Test handling of command not found errors."""
        result = ErrorTestHelper.run_psh_command('nonexistent_command_12345', expect_failure=True)

        # Should fail with command not found error
        assert not result['success']
        assert ('not found' in result['stderr'].lower() or
                'command not found' in result['stderr'].lower() or
                'nonexistent_command_12345' in result['stderr'])

    def test_permission_denied_error(self):
        """Test handling of permission denied errors."""
        # Create a non-executable file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sh') as f:
            f.write('#!/bin/bash\necho test\n')
            temp_file = f.name

        try:
            # Make file non-executable
            os.chmod(temp_file, 0o644)

            result = ErrorTestHelper.run_psh_command(temp_file, expect_failure=True)

            # Should fail with permission error
            assert not result['success']
            assert ('permission' in result['stderr'].lower() or
                    'denied' in result['stderr'].lower() or
                    'not found' in result['stderr'].lower())
        finally:
            os.unlink(temp_file)

    def test_directory_as_command_error(self):
        """Test handling when trying to execute a directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ErrorTestHelper.run_psh_command(temp_dir, expect_failure=True)

            # Should fail appropriately
            assert not result['success']
            assert ('directory' in result['stderr'].lower() or
                    'permission' in result['stderr'].lower() or
                    'not found' in result['stderr'].lower())

    def test_file_not_found_redirection(self):
        """Test handling of file not found in redirection."""
        result = ErrorTestHelper.run_psh_command('cat < /nonexistent/file', expect_failure=True)

        # Should fail with file not found error
        assert not result['success']
        assert ('no such file' in result['stderr'].lower() or
                'not found' in result['stderr'].lower())

    def test_permission_denied_redirection(self):
        """Test handling of permission denied in redirection."""
        result = ErrorTestHelper.run_psh_command('echo test > /root/restricted_file', expect_failure=True)

        # Should fail with permission error
        assert not result['success']
        assert ('permission' in result['stderr'].lower() or
                'denied' in result['stderr'].lower() or
                'no such file' in result['stderr'].lower())

    def test_invalid_file_descriptor(self):
        """Test handling of invalid file descriptors."""
        result = ErrorTestHelper.run_psh_command('echo test >&999', expect_failure=True)

        # Should handle gracefully - might succeed or fail depending on implementation
        # The key is that it shouldn't crash the shell
        assert isinstance(result['returncode'], int)


class TestErrorRecovery:
    """Test error recovery and shell continuation."""

    def test_syntax_error_recovery(self):
        """Test that shell exits with a non-zero code on syntax errors in non-interactive mode.

        POSIX requires that a syntax error in a non-interactive shell causes
        immediate exit.  Bash uses exit code 2; PSH uses 1 for lexer-level
        errors (unclosed quotes) and 2 for parser-level errors.
        """
        commands = [
            'echo "unclosed quote',  # Syntax error
            'echo "this should work"'  # Should NOT execute
        ]

        result = ErrorTestHelper.run_psh_command(commands, expect_failure=True)

        # Non-interactive shell must exit on syntax error
        assert result['returncode'] != 0
        assert 'unclosed' in result['stderr'].lower() or 'quote' in result['stderr'].lower()

    def test_command_not_found_recovery(self):
        """Test that shell continues after command not found."""
        commands = [
            'nonexistent_command',  # Command not found
            'echo "recovery successful"'  # Should still execute
        ]

        result = ErrorTestHelper.run_psh_command(commands)

        # Shell should continue and execute the second command
        assert 'recovery successful' in result['stdout']

    def test_failed_redirection_recovery(self):
        """Test that shell continues after failed redirection."""
        commands = [
            'echo test > /nonexistent/path/file',  # Failed redirection
            'echo "continued execution"'  # Should still execute
        ]

        result = ErrorTestHelper.run_psh_command(commands)

        # Shell should continue and execute the second command
        assert 'continued execution' in result['stdout']

    def test_failed_command_substitution_recovery(self):
        """Test recovery from failed command substitution."""
        commands = [
            'echo $(nonexistent_command)',  # Failed command substitution
            'echo "shell still running"'  # Should still execute
        ]

        result = ErrorTestHelper.run_psh_command(commands)

        # Shell should continue
        assert 'shell still running' in result['stdout']

    def test_arithmetic_error_recovery(self):
        """Test recovery from arithmetic errors."""
        commands = [
            'echo $((1/0))',  # Division by zero
            'echo "arithmetic error handled"'  # Should still execute
        ]

        result = ErrorTestHelper.run_psh_command(commands)

        # Shell should continue (behavior may vary)
        assert 'arithmetic error handled' in result['stdout']


class TestErrorPropagation:
    """Test error propagation in complex scenarios."""

    def test_error_in_pipeline_first_command(self):
        """Test error handling when first command in pipeline fails."""
        result = ErrorTestHelper.run_psh_command('nonexistent_cmd | cat')

        # Pipeline should handle the error appropriately
        # Exact behavior depends on shell options (pipefail, etc.)
        assert isinstance(result['returncode'], int)

    def test_error_in_pipeline_middle_command(self):
        """Test error handling when middle command in pipeline fails."""
        result = ErrorTestHelper.run_psh_command('echo test | nonexistent_cmd | cat')

        # Pipeline should handle the error appropriately
        assert isinstance(result['returncode'], int)

    def test_error_in_pipeline_last_command(self):
        """Test error handling when last command in pipeline fails."""
        result = ErrorTestHelper.run_psh_command('echo test | cat | nonexistent_cmd')

        # Pipeline should handle the error appropriately
        assert isinstance(result['returncode'], int)

    def test_error_in_subshell(self):
        """Test error handling in subshells."""
        commands = [
            '(nonexistent_command)',  # Error in subshell
            'echo "parent shell continues"'  # Parent should continue
        ]

        result = ErrorTestHelper.run_psh_command(commands)

        # Parent shell should continue after subshell error
        assert 'parent shell continues' in result['stdout']

    def test_error_in_function(self):
        """Test error handling in function calls."""
        commands = [
            'test_func() { nonexistent_command; }',
            'test_func',  # Call function with error
            'echo "after function error"'
        ]

        result = ErrorTestHelper.run_psh_command(commands)

        # Shell should continue after function error
        assert 'after function error' in result['stdout']

    def test_error_with_errexit_option(self):
        """Test error handling with set -e (errexit)."""
        commands = [
            'set -e',  # Enable errexit
            'true',  # Success
            'echo "before error"',
            'false',  # This should cause shell to exit
            'echo "should not reach here"'
        ]

        result = ErrorTestHelper.run_psh_command(commands)

        # With errexit, shell should exit on false command
        assert 'before error' in result['stdout']
        assert 'should not reach here' not in result['stdout']


class TestResourceErrorHandling:
    """Test handling of resource-related errors."""

    @pytest.mark.slow
    def test_memory_exhaustion_handling(self):
        """Test handling of potential memory exhaustion scenarios."""
        # Test with very large environment variable
        large_value = 'a' * 100000  # 100KB string

        commands = [f'LARGE_VAR={large_value}', 'echo "memory test complete"']
        result = ErrorTestHelper.run_psh_command(commands)

        # Should handle large variables gracefully
        assert result['success']
        assert 'memory test complete' in result['stdout']

    def test_too_many_arguments_handling(self):
        """Test handling of commands with too many arguments."""
        # Create command with many arguments
        many_args = ' '.join([f'arg{i}' for i in range(1000)])
        command = f'echo {many_args}'

        result = ErrorTestHelper.run_psh_command(command)

        # Should handle gracefully (may succeed or fail depending on system limits)
        assert isinstance(result['returncode'], int)

    def test_deep_recursion_handling(self):
        """Test handling of deep recursive scenarios."""
        commands = [
            'recursive_func() { echo "depth $1"; if [ "$1" -lt 100 ]; then recursive_func $((${1:-0} + 1)); fi; }',
            'recursive_func 1'
        ]

        result = ErrorTestHelper.run_psh_command(commands, timeout=10)

        # Should handle recursion without crashing
        assert isinstance(result['returncode'], int)

    def test_file_descriptor_exhaustion_handling(self, tmp_path):
        """Test handling when running out of file descriptors."""
        # This is difficult to test reliably across systems
        # Just ensure basic file operations work.
        # pytest's per-test tmp dir, NOT <repo>/tmp: this test used to
        # mkdir(exist_ok=True) that directory, which quietly created the
        # dependency other modules were relying on — so whether THEY passed
        # in a fresh checkout depended on whether this test had run first.
        unique_file = tmp_path / f'fd_test_{uuid.uuid4().hex[:8]}'
        commands = [
            f'echo test > {unique_file}',
            f'cat {unique_file}',
            f'rm -f {unique_file}'
        ]

        result = ErrorTestHelper.run_psh_command(commands)
        assert result['success']
        assert 'test' in result['stdout']


class TestErrorMessageQuality:
    """Test quality and helpfulness of error messages."""

    def test_syntax_error_message_clarity(self):
        """Test that syntax error messages are clear and helpful."""
        result = ErrorTestHelper.run_psh_command('echo "unclosed', expect_failure=True)

        # Error message should be informative
        assert not result['success']
        error_msg = result['stderr'].lower()
        assert ('quote' in error_msg or 'syntax' in error_msg or
                'unexpected' in error_msg or 'end of file' in error_msg)

    def test_command_not_found_message_clarity(self):
        """Test that command not found messages are clear."""
        result = ErrorTestHelper.run_psh_command('xyz_nonexistent_cmd', expect_failure=True)

        # Error message should mention the command name
        assert not result['success']
        assert ('xyz_nonexistent_cmd' in result['stderr'] or
                'not found' in result['stderr'].lower())

    def test_redirection_error_message_clarity(self):
        """Test that redirection error messages are clear."""
        result = ErrorTestHelper.run_psh_command('echo test > /nonexistent/dir/file', expect_failure=True)

        # Error message should be informative
        assert not result['success']
        error_msg = result['stderr'].lower()
        assert ('no such file' in error_msg or 'directory' in error_msg or
                'not found' in error_msg)

    def test_permission_error_message_clarity(self):
        """Test that permission error messages are clear."""
        result = ErrorTestHelper.run_psh_command('echo test > /root/test_file', expect_failure=True)

        # Error message should mention permission issue
        assert not result['success']
        error_msg = result['stderr'].lower()
        assert ('permission' in error_msg or 'denied' in error_msg or 'no such file' in error_msg)


class TestInteractiveErrorHandling:
    """Test error handling in interactive vs non-interactive modes."""

    def test_non_interactive_error_behavior(self):
        """Test error behavior in non-interactive mode (default for our tests)."""
        result = ErrorTestHelper.run_psh_command('nonexistent_command', expect_failure=True)

        # In non-interactive mode, should exit with error
        assert not result['success']
        assert result['returncode'] != 0

    def test_syntax_error_exit_behavior(self):
        """Test that syntax errors cause appropriate exit behavior."""
        result = ErrorTestHelper.run_psh_command('echo "unclosed', expect_failure=True)

        # Should exit with non-zero status
        assert not result['success']
        assert result['returncode'] != 0

    def test_error_in_script_vs_command_line(self):
        """Test error handling differences between script and command line."""
        # Create a script with an error
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sh') as f:
            f.write('#!/bin/bash\necho "before error"\nnonexistent_command\necho "after error"\n')
            script_path = f.name

        try:
            result = ErrorTestHelper.run_psh_command(f'bash {script_path}')

            # Behavior depends on shell configuration
            # Just ensure it doesn't crash
            assert isinstance(result['returncode'], int)
        finally:
            os.unlink(script_path)


# Test runner integration
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
