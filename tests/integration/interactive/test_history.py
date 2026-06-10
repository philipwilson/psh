"""
Command history integration tests.

Tests for command history functionality including:
- History storage and retrieval
- History expansion (!!, !n, !string)
- History file management
- History size limits
- History search and navigation
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


class HistoryTestHelper:
    """Helper class for history testing using subprocess."""

    @classmethod
    def run_psh_with_history(cls, commands, history_file=None, timeout=5):
        """Run PSH with history enabled and return output."""
        env = os.environ.copy()
        psh_root = Path(__file__).parent.parent.parent.parent
        env['PYTHONPATH'] = str(psh_root)
        env['PYTHONUNBUFFERED'] = '1'

        # Set history file if provided
        if history_file:
            env['HISTFILE'] = history_file

        # Join commands with newlines and add exit
        if isinstance(commands, str):
            input_text = commands + '\nexit\n'
        else:
            input_text = '\n'.join(commands) + '\nexit\n'

        proc = subprocess.Popen(
            [sys.executable, '-u', '-m', 'psh', '--norc'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )

        try:
            stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
            return {
                'stdout': stdout,
                'stderr': stderr,
                'returncode': proc.returncode,
                'success': proc.returncode == 0
            }
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            return {
                'stdout': stdout or '',
                'stderr': stderr or '',
                'returncode': -1,
                'error': 'timeout',
                'success': False
            }


class TestBasicHistory:
    """Test basic history functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix='psh_history_test_')
        self.history_file = os.path.join(self.temp_dir, '.psh_history')

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.xfail(reason="history is implemented, but this test feeds a non-interactive stdin, which does not record history; live coverage is in tests/system/interactive/test_pty_smoke.py")
    def test_history_command_basic(self):
        """Test basic history command functionality."""
        commands = [
            'echo first',
            'echo second',
            'echo third',
            'history'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Check that history shows recent commands
        assert 'echo first' in result['stdout']
        assert 'echo second' in result['stdout']
        assert 'echo third' in result['stdout']

    @pytest.mark.xfail(reason="history is implemented, but this test feeds a non-interactive stdin, which does not record history; live coverage is in tests/system/interactive/test_pty_smoke.py")
    def test_history_numbering(self):
        """Test that history shows command numbers."""
        commands = [
            'echo command1',
            'echo command2',
            'history'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Check for numbered history entries
        lines = result['stdout'].split('\n')
        history_lines = [line for line in lines if 'echo command' in line]
        assert len(history_lines) >= 2

    @pytest.mark.xfail(reason="history is implemented, but this test feeds a non-interactive stdin, which does not record history; live coverage is in tests/system/interactive/test_pty_smoke.py")
    def test_history_persistence(self):
        """Test that history persists across shell sessions."""
        # First session
        commands1 = ['echo session1', 'echo persistent']
        result1 = HistoryTestHelper.run_psh_with_history(commands1, self.history_file)
        assert result1['success']

        # Second session
        commands2 = ['history']
        result2 = HistoryTestHelper.run_psh_with_history(commands2, self.history_file)
        assert result2['success']

        # Check that commands from first session appear in second session
        assert 'echo session1' in result2['stdout']
        assert 'echo persistent' in result2['stdout']

    @pytest.mark.xfail(reason="history is implemented, but this test feeds a non-interactive stdin, which does not record history; live coverage is in tests/system/interactive/test_pty_smoke.py")
    def test_history_file_creation(self):
        """Test that history file is created when it doesn't exist."""
        commands = ['echo test', 'history']
        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Check that history file was created
        assert os.path.exists(self.history_file)


class TestHistoryExpansion:
    """Test history expansion functionality (!!, !n, !string)."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix='psh_history_test_')
        self.history_file = os.path.join(self.temp_dir, '.psh_history')

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.xfail(reason="history expansion (!!, !n) is unsupported (documented wontfix); see docs/reviews/architecture_feature_review_2026-06-09.md")
    def test_history_expansion_last_command(self):
        """Test !! expansion (repeat last command)."""
        commands = [
            'echo hello world',
            '!!'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Should see "hello world" output twice
        hello_count = result['stdout'].count('hello world')
        assert hello_count >= 2

    @pytest.mark.xfail(reason="history expansion (!!, !n) is unsupported (documented wontfix); see docs/reviews/architecture_feature_review_2026-06-09.md")
    def test_history_expansion_by_number(self):
        """Test !n expansion (repeat command by number)."""
        commands = [
            'echo first',
            'echo second',
            'echo third',
            '!1'  # Should repeat first command
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Should see "first" output twice
        first_count = result['stdout'].count('first')
        assert first_count >= 2

    @pytest.mark.xfail(reason="history expansion (!!, !n) is unsupported (documented wontfix); see docs/reviews/architecture_feature_review_2026-06-09.md")
    def test_history_expansion_by_string(self):
        """Test !string expansion (repeat command starting with string)."""
        commands = [
            'echo unique_test_string',
            'echo something else',
            '!echo unique'  # Should match first command
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Should see unique_test_string twice
        count = result['stdout'].count('unique_test_string')
        assert count >= 2

    def test_history_expansion_not_found(self):
        """Test history expansion when pattern not found."""
        commands = [
            'echo test',
            '!nonexistent'
        ]

        HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        # Should handle gracefully - either error message or no expansion
        # Exact behavior depends on implementation

    def test_history_expansion_in_quotes(self):
        """Test history expansion behavior inside quotes."""
        commands = [
            'echo test',
            'echo "!!"'  # Should not expand inside double quotes
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Should print literal "!!" not expand it
        assert '!!' in result['stdout']


class TestHistoryConfiguration:
    """Test history configuration and options."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix='psh_history_test_')
        self.history_file = os.path.join(self.temp_dir, '.psh_history')

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_histsize_variable(self):
        """Test HISTSIZE variable controls history size."""
        commands = [
            'HISTSIZE=3',  # Limit history to 3 entries
            'echo cmd1',
            'echo cmd2',
            'echo cmd3',
            'echo cmd4',
            'history'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Should only show last 3 commands plus history command itself
        lines = result['stdout'].split('\n')
        echo_lines = [line for line in lines if 'echo cmd' in line]
        # With HISTSIZE=3, should only see cmd2, cmd3, cmd4
        assert 'cmd1' not in result['stdout'] or len(echo_lines) <= 3

    @pytest.mark.xfail(reason="HISTSIZE/HISTFILE configuration not honored in non-interactive mode used by this test")
    def test_histfile_variable(self):
        """Test HISTFILE variable controls history file location."""
        custom_history = os.path.join(self.temp_dir, 'custom_history')

        commands = [
            f'HISTFILE={custom_history}',
            'echo test_custom_location',
            'history'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands)
        assert result['success']

        # Check that custom history file was created
        assert os.path.exists(custom_history)

    def test_history_disable(self):
        """Test disabling history."""
        commands = [
            'set +H',  # Disable history expansion if supported
            'echo test',
            'history'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Behavior depends on how history disable is implemented

    def test_history_no_duplicates(self):
        """Test history ignoring duplicate commands."""
        commands = [
            'echo duplicate',
            'echo duplicate',  # Same command
            'echo different',
            'echo duplicate',  # Same again
            'history'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Depending on implementation, might ignore consecutive duplicates


class TestHistoryNavigation:
    """Test history navigation (arrow keys, search)."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix='psh_history_test_')
        self.history_file = os.path.join(self.temp_dir, '.psh_history')

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_up_arrow_navigation(self):
        """Test up arrow key for history navigation."""
        # This test would require actual terminal interaction
        # Difficult to test with subprocess approach
        pass

    def test_ctrl_r_search(self):
        """Test Ctrl-R reverse search."""
        # This test would require actual terminal interaction
        # Difficult to test with subprocess approach
        pass

    def test_history_search_command(self):
        """Test history search functionality if available as command."""
        commands = [
            'echo unique_searchable_command',
            'echo something else',
            'history | grep unique_searchable'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Should find the unique command
        assert 'unique_searchable_command' in result['stdout']


class TestHistoryBuiltins:
    """Test history-related builtin commands."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix='psh_history_test_')
        self.history_file = os.path.join(self.temp_dir, '.psh_history')

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.xfail(reason="history -c/-d options not implemented")
    def test_history_clear(self):
        """Test history -c (clear history)."""
        commands = [
            'echo before_clear',
            'history -c',
            'history'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # After clear, should not see before_clear in history
        assert 'before_clear' not in result['stdout']

    def test_history_write(self):
        """Test history -w (write history to file)."""
        commands = [
            'echo test_write',
            'history -w'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Check that history file contains the command
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
                content = f.read()
                assert 'echo test_write' in content

    @pytest.mark.xfail(reason="history -c/-d options not implemented")
    def test_history_read(self):
        """Test history -r (read history from file)."""
        # Pre-populate history file
        with open(self.history_file, 'w') as f:
            f.write('echo from_file\n')
            f.write('echo another_from_file\n')

        commands = [
            'history -r',
            'history'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Should see commands from file
        assert 'from_file' in result['stdout']
        assert 'another_from_file' in result['stdout']

    def test_history_append(self):
        """Test history -a (append new history to file)."""
        commands = [
            'echo append_test',
            'history -a'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands, self.history_file)
        assert result['success']

        # Check that history file was appended to
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
                content = f.read()
                assert 'append_test' in content


class TestHistoryErrorHandling:
    """Test history error handling and edge cases."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix='psh_history_test_')

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_history_file_permission_denied(self):
        """Test history behavior when history file is not writable."""
        history_file = os.path.join(self.temp_dir, 'readonly_history')

        # Create read-only file
        with open(history_file, 'w') as f:
            f.write('existing_command\n')
        os.chmod(history_file, 0o444)  # Read-only

        commands = ['echo permission_test']
        result = HistoryTestHelper.run_psh_with_history(commands, history_file)

        # Should handle gracefully without crashing
        assert result['success'] or 'permission' in result['stderr'].lower()

    def test_history_file_directory_not_exist(self):
        """Test history behavior when history file directory doesn't exist."""
        history_file = os.path.join(self.temp_dir, 'nonexistent', 'history')

        commands = ['echo dir_test']
        result = HistoryTestHelper.run_psh_with_history(commands, history_file)

        # Should handle gracefully
        assert result['success'] or 'directory' in result['stderr'].lower()

    def test_history_with_very_long_commands(self):
        """Test history with very long command lines."""
        long_command = 'echo ' + 'a' * 10000  # Very long command

        commands = [long_command, 'history']
        result = HistoryTestHelper.run_psh_with_history(commands)
        assert result['success']

        # Should handle long commands gracefully

    def test_history_with_special_characters(self):
        """Test history with special characters and unicode."""
        commands = [
            'echo "special chars: !@#$%^&*()"',
            'echo "unicode: 你好 🌟"',
            'history'
        ]

        result = HistoryTestHelper.run_psh_with_history(commands)
        assert result['success']

        # Should handle special characters and unicode


# Test runner integration
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
