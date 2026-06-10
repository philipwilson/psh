"""
Tab completion integration tests.

Tests for tab completion functionality including:
- Command completion
- File/directory completion
- Variable completion
- Path completion
- Custom completion scenarios
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


class InteractiveTestHelper:
    """Helper class for interactive PSH testing using subprocess."""

    @classmethod
    def run_psh_interactive(cls, input_sequence, timeout=5, expect_prompt=True):
        """Run PSH interactively and return output."""
        env = os.environ.copy()
        psh_root = Path(__file__).parent.parent.parent.parent
        env['PYTHONPATH'] = str(psh_root)
        env['PYTHONUNBUFFERED'] = '1'

        # Add input termination
        if isinstance(input_sequence, str):
            input_text = input_sequence + '\nexit\n'
        else:
            input_text = '\n'.join(input_sequence) + '\nexit\n'

        proc = subprocess.Popen(
            [sys.executable, '-u', '-m', 'psh', '--norc', '--force-interactive'],
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


class TestCommandCompletion:
    """Test command name completion."""

    @pytest.mark.xfail(reason="tab completion is implemented, but requires a real PTY; piped stdin cannot trigger it — live coverage is in tests/system/interactive/test_pty_smoke.py")
    def test_builtin_command_completion(self):
        """Test completion of builtin command names."""
        # Test that 'ec<TAB>' completes to 'echo'
        result = InteractiveTestHelper.run_psh_interactive('ec\t')
        assert result['success']
        assert 'echo' in result['stdout']

    def test_external_command_completion(self):
        """Test completion of external command names from PATH."""
        # Test that 'l<TAB>' shows 'ls' among options
        result = InteractiveTestHelper.run_psh_interactive('l\t')
        assert result['success']
        # Should show available commands starting with 'l'

    def test_command_completion_multiple_options(self):
        """Test completion when multiple commands match."""
        # Test completion with multiple matches
        result = InteractiveTestHelper.run_psh_interactive('ca\t')
        assert result['success']
        # Should show multiple options like 'cat', 'cal', etc.

    @pytest.mark.xfail(reason="tab completion is implemented, but requires a real PTY; piped stdin cannot trigger it — live coverage is in tests/system/interactive/test_pty_smoke.py")
    def test_command_completion_unique_match(self):
        """Test completion when only one command matches."""
        # Test unique completion
        result = InteractiveTestHelper.run_psh_interactive('ech\t')
        assert result['success']
        assert 'echo' in result['stdout']

    def test_no_command_completion_match(self):
        """Test completion behavior when no commands match."""
        # Test with non-existent command prefix
        result = InteractiveTestHelper.run_psh_interactive('xyz123\t')
        assert result['success']
        # Should not complete anything


class TestFileCompletion:
    """Test file and directory name completion."""

    def setup_method(self):
        """Set up test files and directories."""
        self.test_dir = tempfile.mkdtemp(prefix='psh_completion_test_')
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Create test files and directories
        os.makedirs('test_directory', exist_ok=True)
        os.makedirs('another_dir', exist_ok=True)

        # Create test files
        for filename in ['test_file.txt', 'test_script.sh', 'another_file.py']:
            with open(filename, 'w') as f:
                f.write('test content\n')

    def teardown_method(self):
        """Clean up test files and directories."""
        os.chdir(self.old_cwd)
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_file_completion_basic(self):
        """Test basic file completion."""
        # Test completing 'test_<TAB>'
        result = InteractiveTestHelper.run_psh_interactive(f'cd {self.test_dir}\nls test_\t')
        assert result['success']
        # Should complete to available files starting with 'test_'

    def test_directory_completion(self):
        """Test directory completion."""
        # Test completing directory names
        result = InteractiveTestHelper.run_psh_interactive(f'cd {self.test_dir}\ncd test_\t')
        assert result['success']
        # Should complete to 'test_directory'

    def test_hidden_file_completion(self):
        """Test completion of hidden files."""
        # Create hidden file
        with open('.hidden_file', 'w') as f:
            f.write('hidden content\n')

        result = InteractiveTestHelper.run_psh_interactive(f'cd {self.test_dir}\nls .hid\t')
        assert result['success']
        # Should complete to '.hidden_file'

    def test_path_completion_with_slash(self):
        """Test completion with path separators."""
        result = InteractiveTestHelper.run_psh_interactive(f'cd {self.test_dir}\nls test_directory/\t')
        assert result['success']
        # Should show contents of test_directory

    def test_absolute_path_completion(self):
        """Test completion of absolute paths."""
        result = InteractiveTestHelper.run_psh_interactive(f'ls {self.test_dir}/test_\t')
        assert result['success']
        # Should complete files in absolute path


class TestVariableCompletion:
    """Test variable name completion."""

    def test_environment_variable_completion(self):
        """Test completion of environment variables."""
        # Test completing '$HO<TAB>' to '$HOME'
        result = InteractiveTestHelper.run_psh_interactive('echo $HO\t')
        assert result['success']
        # Should complete to $HOME

    def test_user_variable_completion(self):
        """Test completion of user-defined variables."""
        # Set a variable and test completion
        result = InteractiveTestHelper.run_psh_interactive(['MY_TEST_VAR=hello', 'echo $MY_\t'])
        assert result['success']
        # Should complete to $MY_TEST_VAR

    def test_special_variable_completion(self):
        """Test completion of special variables like $?, $$, etc."""
        # Test special variables
        result = InteractiveTestHelper.run_psh_interactive('echo $\t')
        assert result['success']
        # Should show special variables like $?, $$, $!, etc.

    def test_variable_completion_in_quotes(self):
        """Test variable completion inside quotes."""
        result = InteractiveTestHelper.run_psh_interactive('echo "Value is $HO\t"')
        assert result['success']
        # Should complete variables even inside quotes


class TestAdvancedCompletion:
    """Test advanced completion scenarios."""

    def test_completion_after_pipe(self):
        """Test completion after pipe operators."""
        result = InteractiveTestHelper.run_psh_interactive('echo hello | ca\t')
        assert result['success']
        # Should complete commands after pipe

    def test_completion_after_redirection(self):
        """Test completion after redirection operators."""
        result = InteractiveTestHelper.run_psh_interactive('echo hello > test_\t')
        assert result['success']
        # Should complete filenames after redirection

    def test_completion_in_command_substitution(self):
        """Test completion inside command substitution."""
        result = InteractiveTestHelper.run_psh_interactive('echo $(ech\t)')
        assert result['success']
        # Should complete commands inside $()

    def test_completion_with_quotes(self):
        """Test completion with quoted arguments."""
        result = InteractiveTestHelper.run_psh_interactive('echo "test_\t"')
        assert result['success']
        # Should handle completion inside quotes

    def test_completion_function_names(self):
        """Test completion of function names."""
        # Define a function and test completion
        result = InteractiveTestHelper.run_psh_interactive([
            'my_test_function() { echo "test"; }',
            'my_\t'
        ])
        assert result['success']
        # Should complete to my_test_function

    def test_completion_alias_names(self):
        """Test completion of alias names."""
        # Define an alias and test completion
        result = InteractiveTestHelper.run_psh_interactive([
            'alias my_alias="echo test"',
            'my_a\t'
        ])
        assert result['success']
        # Should complete to my_alias


class TestCompletionConfiguration:
    """Test completion configuration and customization."""

    def test_completion_disable(self):
        """Test disabling tab completion."""
        # Test with completion disabled
        result = InteractiveTestHelper.run_psh_interactive([
            'set +o completion',  # Disable completion if supported
            'ech\t'
        ])
        assert result['success']
        # Should not complete when disabled

    def test_completion_case_sensitivity(self):
        """Test case-sensitive vs case-insensitive completion."""
        # Test case sensitivity in completion
        result = InteractiveTestHelper.run_psh_interactive('EC\t')
        assert result['success']
        # Behavior depends on case sensitivity setting

    def test_completion_cycling(self):
        """Test cycling through multiple completion options."""
        # Test pressing TAB multiple times
        result = InteractiveTestHelper.run_psh_interactive('ca\t\t')
        assert result['success']
        # Should cycle through options if multiple matches


class TestCompletionErrorHandling:
    """Test completion error handling and edge cases."""

    def test_completion_permission_denied(self):
        """Test completion in directories without read permission."""
        # This test would require creating a directory without read permissions
        # and testing completion behavior
        pass

    def test_completion_nonexistent_directory(self):
        """Test completion in non-existent directories."""
        result = InteractiveTestHelper.run_psh_interactive('ls /nonexistent/path/\t')
        assert result['success']
        # Should handle gracefully

    def test_completion_with_very_long_path(self):
        """Test completion with very long file paths."""
        # Create a deep directory structure
        long_path = '/'.join(['very_long_directory_name'] * 10)
        result = InteractiveTestHelper.run_psh_interactive(f'ls {long_path}\t')
        assert result['success']
        # Should handle long paths gracefully

    def test_completion_special_characters(self):
        """Test completion with special characters in filenames."""
        # Test files with spaces, quotes, etc.
        pass


# Test runner integration
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
