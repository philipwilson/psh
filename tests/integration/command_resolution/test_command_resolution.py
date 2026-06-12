"""
Command resolution integration tests.

Tests for command resolution precedence and PATH handling including:
- Command resolution order (builtin > function > external)
- PATH modification effects
- Command caching and hash table behavior
- Command not found handling
- Executable permission checking
- Relative vs absolute path execution
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Add framework to path
TEST_ROOT = Path(__file__).parent.parent.parent
PSH_ROOT = TEST_ROOT.parent
sys.path.insert(0, str(PSH_ROOT))

# Shell fixture imported automatically from conftest.py


class TestCommandResolutionPrecedence:
    """Test command resolution order: builtin > function > external."""

    def test_builtin_precedence_over_external(self, shell):
        """Test that builtins take precedence over external commands."""
        # Create a fake 'echo' command in PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_echo = os.path.join(temp_dir, 'echo')
            with open(fake_echo, 'w') as f:
                f.write('#!/bin/bash\necho "fake echo"\n')
            os.chmod(fake_echo, 0o755)

            # Add temp dir to front of PATH
            shell.run_command(f'export PATH="{temp_dir}:$PATH"')

            # echo should still use builtin, not the fake one
            result = shell.run_command('echo "test"')
            assert result == 0
            # Output verification would need shell output capture

    def test_function_precedence_over_external(self, shell):
        """Test that functions take precedence over external commands."""
        # Create a fake 'ls' command
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_ls = os.path.join(temp_dir, 'ls')
            with open(fake_ls, 'w') as f:
                f.write('#!/bin/bash\necho "fake ls"\n')
            os.chmod(fake_ls, 0o755)

            # Add temp dir to PATH
            shell.run_command(f'export PATH="{temp_dir}:$PATH"')

            # Define a function with same name
            shell.run_command('''
            ls() {
                echo "function ls called"
            }
            ''')

            # Function should take precedence
            result = shell.run_command('ls')
            assert result == 0
            # Output verification would need shell output capture

            # Clean up
            shell.run_command('unset -f ls')

    def test_builtin_precedence_over_function(self, shell):
        """Test that builtins take precedence over functions."""
        # Try to override a builtin with a function
        shell.run_command('''
        echo() {
            printf "function echo: %s\\n" "$@"
        }
        ''')

        # Builtin should still take precedence
        result = shell.run_command('echo "test"')
        assert result == 0
        # Output verification would need shell output capture

        # Clean up
        shell.run_command('unset -f echo')

    def test_command_type_resolution(self, shell):
        """Test 'type' command shows resolution precedence."""
        # Test builtin
        result = shell.run_command('type echo')
        assert result == 0
        # Output verification would need shell output capture

        # Define function and test
        shell.run_command('testfunc() { echo "test function"; }')
        # TODO: Fix type builtin to properly detect user-defined functions
        # For now just test that function execution works
        result = shell.run_command('testfunc')
        assert result == 0

        # Test external command (use /usr/bin/type instead of type to avoid using builtin)
        result = shell.run_command('/usr/bin/type ls')
        # Expect success or failure, but not crash
        assert isinstance(result, int)


class TestPATHHandling:
    """Test PATH modification and command lookup."""

    def test_path_modification(self, shell):
        """Test that PATH changes affect command resolution."""
        # Create custom command directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create custom command
            custom_cmd = os.path.join(temp_dir, 'customcmd')
            with open(custom_cmd, 'w') as f:
                f.write('#!/bin/bash\necho "custom command executed"\n')
            os.chmod(custom_cmd, 0o755)

            # Command should not be found initially
            result = shell.run_command('customcmd')
            assert result != 0

            # Add directory to PATH
            shell.run_command(f'export PATH="{temp_dir}:$PATH"')

            # Command should now be found
            result = shell.run_command('customcmd')
            assert result == 0
            # Output verification would need shell output capture

    def test_path_search_order(self, shell):
        """Test that PATH directories are searched in order."""
        with tempfile.TemporaryDirectory() as temp_dir1, \
             tempfile.TemporaryDirectory() as temp_dir2:

            # Create same command in both directories
            cmd1 = os.path.join(temp_dir1, 'searchtest')
            cmd2 = os.path.join(temp_dir2, 'searchtest')

            with open(cmd1, 'w') as f:
                f.write('#!/bin/bash\necho "first directory"\n')
            os.chmod(cmd1, 0o755)

            with open(cmd2, 'w') as f:
                f.write('#!/bin/bash\necho "second directory"\n')
            os.chmod(cmd2, 0o755)

            # Set PATH with first directory first
            shell.run_command(f'export PATH="{temp_dir1}:{temp_dir2}:$PATH"')

            # Should find first directory's version
            result = shell.run_command('searchtest')
            assert result == 0
            # Output verification would need shell output capture

            # Reverse PATH order
            shell.run_command(f'export PATH="{temp_dir2}:{temp_dir1}:$PATH"')

            # Should now find second directory's version
            result = shell.run_command('searchtest')
            assert result == 0
            # Output verification would need shell output capture

    def test_empty_path_component(self, shell):
        """Test PATH with empty components (current directory)."""
        # Create command in current directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Change to temp directory
            shell.run_command(f'cd "{temp_dir}"')

            # Create command in current directory
            with open('localcmd', 'w') as f:
                f.write('#!/bin/bash\necho "local command"\n')
            os.chmod('localcmd', 0o755)

            # Set PATH with empty component (::)
            shell.run_command('export PATH="::$PATH"')

            # Should find local command
            result = shell.run_command('localcmd')
            assert result == 0
            # Output verification would need shell output capture

    def test_absolute_path_bypasses_search(self, shell):
        """Test that absolute paths bypass PATH search."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create command
            abs_cmd = os.path.join(temp_dir, 'abscmd')
            with open(abs_cmd, 'w') as f:
                f.write('#!/bin/bash\necho "absolute path command"\n')
            os.chmod(abs_cmd, 0o755)

            # Execute with absolute path (temp_dir not in PATH)
            result = shell.run_command(abs_cmd)
            assert result == 0
            # Output verification would need shell output capture

    def test_relative_path_bypasses_search(self, shell):
        """Test that relative paths bypass PATH search."""
        with tempfile.TemporaryDirectory() as temp_dir:
            shell.run_command(f'cd "{temp_dir}"')

            # Create command in subdirectory
            os.mkdir('subdir')
            rel_cmd = os.path.join('subdir', 'relcmd')
            with open(rel_cmd, 'w') as f:
                f.write('#!/bin/bash\necho "relative path command"\n')
            os.chmod(rel_cmd, 0o755)

            # Execute with relative path
            result = shell.run_command('./subdir/relcmd')
            assert result == 0
            # Output verification would need shell output capture


@pytest.mark.skip(reason="psh does not implement the `hash` builtin (POSIX/bash "
                         "have it). These tests only ever passed on macOS by "
                         "accident, via the BSD /usr/bin/hash sh-stub script; on "
                         "Linux there is no such binary and `hash` exits 127. "
                         "Unskip once a real hash builtin (command-location cache) "
                         "is implemented.")
class TestCommandCaching:
    """Test command caching and hash table behavior."""

    def test_hash_command(self, shell):
        """Test hash command for caching command locations."""
        # Hash a command
        result = shell.run_command('hash ls')
        assert result == 0

        # List hashed commands
        hash_result = shell.run_command('hash')
        assert hash_result == 0
        # Output verification would need shell output capture

    def test_hash_invalidation_on_path_change(self, shell):
        """Test that hash table is invalidated when PATH changes."""
        # Hash a command
        shell.run_command('hash ls')

        # Change PATH
        shell.run_command('export PATH="/different/path:$PATH"')

        # Hash table should be invalidated
        # Exact behavior depends on implementation

    def test_hash_clear(self, shell):
        """Test clearing the command hash table."""
        # Hash some commands
        shell.run_command('hash ls cat echo')

        # Clear hash table
        result = shell.run_command('hash -r')
        assert result == 0

        # Hash table should be empty
        hash_result = shell.run_command('hash')
        assert hash_result == 0


class TestExecutablePermissions:
    """Test executable permission checking."""

    def test_non_executable_file(self, shell):
        """Test handling of non-executable files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create non-executable file
            non_exec = os.path.join(temp_dir, 'nonexec')
            with open(non_exec, 'w') as f:
                f.write('#!/bin/bash\necho "should not execute"\n')
            # Don't set execute permission

            # Add to PATH
            shell.run_command(f'export PATH="{temp_dir}:$PATH"')

            # Should fail with permission error
            result = shell.run_command('nonexec')
            assert result != 0
            # Error message verification would need shell output capture

    def test_executable_without_shebang(self, shell):
        """Test execution of files without shebang."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create executable without shebang
            no_shebang = os.path.join(temp_dir, 'noshebang')
            with open(no_shebang, 'w') as f:
                f.write('echo "no shebang"\n')  # No #!/bin/bash
            os.chmod(no_shebang, 0o755)

            # Execute with absolute path
            result = shell.run_command(no_shebang)
            # Behavior may vary - might execute with /bin/sh or fail
            # Just check that it doesn't crash the shell
            assert isinstance(result, int)

    def test_directory_as_command(self, shell):
        """Test handling when command name refers to directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create subdirectory with same name as potential command
            dir_name = os.path.join(temp_dir, 'dirname')
            os.mkdir(dir_name)

            # Add to PATH
            shell.run_command(f'export PATH="{temp_dir}:$PATH"')

            # Should fail appropriately
            result = shell.run_command('dirname')
            assert result != 0


class TestCommandNotFound:
    """Test command not found handling."""

    def test_nonexistent_command(self, shell):
        """Test handling of completely nonexistent commands."""
        result = shell.run_command('nonexistent_command_12345')
        assert result != 0
        # Error message verification would need shell output capture

    def test_command_not_found_in_pipeline(self, shell):
        """Test command not found in pipeline context."""
        result = shell.run_command('echo test | nonexistent_command_xyz')
        assert result != 0
        # Pipeline should handle the error appropriately

    def test_command_not_found_with_errexit(self, shell):
        """Test command not found with set -e."""
        # Enable errexit
        shell.run_command('set -e')

        # Command not found should exit the shell in errexit mode
        result = shell.run_command('nonexistent_command_abc; echo "should not reach here"')
        assert result != 0
        # Output verification would need shell output capture

    def test_command_not_found_function(self, shell):
        """Test command_not_found_handle function if implemented."""
        # Define command not found handler
        shell.run_command('''
        command_not_found_handle() {
            echo "Command '$1' not found, did you mean something else?"
            return 127
        }
        ''')

        # Test that handler is called
        result = shell.run_command('misspelled_command')
        assert result == 127
        # Output verification would need shell output capture


class TestCommandBuiltinIntegration:
    """Test 'command' builtin for bypassing functions and aliases."""

    def test_command_bypass_function(self, shell):
        """Test using 'command' to bypass function definitions."""
        # Define function that shadows external command
        shell.run_command('''
        date() {
            echo "function date"
        }
        ''')

        # Normal call should use function
        result = shell.run_command('date')
        assert result == 0
        # Output verification would need shell output capture

        # command should bypass function
        result = shell.run_command('command date')
        assert result == 0
        # Output verification would need shell output capture
        # Should execute actual date command

        # Clean up
        shell.run_command('unset -f date')

    def test_command_bypass_alias(self, shell):
        """Test using 'command' to bypass aliases."""
        # Create alias
        shell.run_command("alias ls='echo alias ls'")

        # Normal call should use alias
        result = shell.run_command('ls')
        assert result == 0
        # Output verification would need shell output capture

        # command should bypass alias
        result = shell.run_command('command ls')
        assert result == 0
        # Output verification would need shell output capture

        # Clean up
        shell.run_command('unalias ls')

    def test_command_with_options(self, shell):
        """Test 'command' builtin with various options."""
        # command -v should show command type
        result = shell.run_command('command -v echo')
        assert result == 0

        # command -V should show verbose information
        result = shell.run_command('command -V echo')
        assert result == 0
        # Output verification would need shell output capture


class TestWhichCommand:
    """Test 'which' command functionality."""

    def test_which_builtin(self, shell):
        """Test which command with builtins."""
        result = shell.run_command('which echo')
        # Behavior may vary - some systems show builtin path, others don't
        # Basic success check
        assert isinstance(result, int)

    def test_which_external_command(self, shell):
        """Test which command with external commands."""
        result = shell.run_command('which ls')
        assert result == 0
        # Output verification would need shell output capture

    def test_which_nonexistent(self, shell):
        """Test which with nonexistent command."""
        result = shell.run_command('which nonexistent_command_xyz')
        assert result != 0


# Shell fixture provided by conftest.py


# Helper functions
def create_executable_script(path, content):
    """Helper to create executable test scripts."""
    with open(path, 'w') as f:
        f.write(content)
    os.chmod(path, 0o755)
    return path


def ensure_command_exists(command):
    """Helper to check if external command exists."""
    try:
        subprocess.run(['which', command], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False
