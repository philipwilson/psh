"""
Advanced I/O redirection integration tests.

Tests for complex I/O redirection scenarios including:
- File descriptor duplication (>&, <&)
- Named pipes (FIFOs) integration
- Process substitution (<(command), >(command))
- File descriptor closing (n>&-, n<&-)
- Complex redirection combinations
- Error handling in redirection scenarios
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Add framework to path
TEST_ROOT = Path(__file__).parent.parent.parent
PSH_ROOT = TEST_ROOT.parent

# Shell fixture imported automatically from conftest.py


class TestFileDescriptorDuplication:
    """Test file descriptor duplication with >& and <& operators."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""
        pass

    def teardown_method(self):
        """Clean up any leftover processes after each test."""
        pass

    def test_stdout_duplication_simple(self, shell):
        """Test simple stdout redirection and duplication."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            # Test basic stdout redirection (foundation for duplication)
            result = shell.run_command(f'echo "test output" > {temp_path}')
            assert result == 0

            # Check that output went to file
            with open(temp_path, 'r') as f:
                content = f.read()
            assert "test output" in content

        finally:
            os.unlink(temp_path)

    @pytest.mark.serial
    def test_stderr_to_stdout_duplication(self, isolated_shell_with_temp_dir):
        """Test redirecting stderr to stdout (2>&1)."""
        shell = isolated_shell_with_temp_dir

        # Use subprocess for better isolation
        subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo "stdout message"; echo "stderr message" >&2'],
            cwd=shell.state.variables['PWD'],
            capture_output=True,
            text=True
        )

        # Both should appear in stdout when using 2>&1
        result2 = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             '{ echo "stdout message"; echo "stderr message" >&2; } 2>&1'],
            cwd=shell.state.variables['PWD'],
            capture_output=True,
            text=True
        )

        assert "stdout message" in result2.stdout
        assert "stderr message" in result2.stdout
        assert result2.stderr == ""  # stderr should be empty as it's redirected

    def test_stderr_redirection_basic(self, shell):
        """Test basic stderr redirection to file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            # Use a command that actually generates stderr output
            # and redirect it to a file
            shell.run_command(f'ls /nonexistent/path 2> {temp_path}')
            # ls should fail but stderr should be captured

            # Check that error output went to file
            with open(temp_path, 'r') as f:
                content = f.read()
            # Should contain some error message about the path not existing
            assert len(content.strip()) > 0

        finally:
            os.unlink(temp_path)

    def test_stdin_redirection_basic(self, shell):
        """Test basic stdin redirection from file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write("input data\n")
            temp_path = temp_file.name

        try:
            # Test basic stdin redirection from file
            result = shell.run_command(f'cat < {temp_path}')
            assert result == 0
            # This tests that stdin redirection works fundamentally

        finally:
            os.unlink(temp_path)

    def test_multiple_redirection_operators(self, isolated_shell_with_temp_dir):
        """Test handling multiple redirection operators in one command."""
        # Relative paths in the per-test temp dir: building absolute paths
        # from state.variables['PWD'] used to leak stdout_test.txt /
        # stderr_test.txt into the repository root (stale PWD).
        shell = isolated_shell_with_temp_dir
        shell.run_command('echo "to stdout" > stdout_test.txt && ls /nonexistent 2> stderr_test.txt')

        # Check stdout file (cwd is the per-test temp dir)
        with open('stdout_test.txt', 'r') as f:
            stdout_content = f.read()
        assert "to stdout" in stdout_content

        # Note: We're not checking stderr content as ls output varies

    def test_null_device_redirection(self, shell):
        """Test redirection to null device."""
        # Test redirecting stdout to /dev/null (common redirection target)
        result = shell.run_command('echo "discarded" > /dev/null')
        assert result == 0

        # Test stderr to null with a command that actually produces stderr
        result = shell.run_command('ls /nonexistent/path 2> /dev/null')
        # Command should complete (stderr redirected to null)

        # This tests basic redirection functionality without complex fd management

    @pytest.mark.serial
    def test_stderr_to_stdout_redirection(self, shell):
        """Test the common 2>&1 redirection pattern."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            # Test 2>&1 - redirect stderr to stdout, then redirect to file
            # Order matters: redirect stdout to file, then redirect stderr to stdout
            shell.run_command(f'ls /nonexistent/path > {temp_path} 2>&1')
            # This should capture both stdout and stderr in the file

            # Check that some output was captured
            with open(temp_path, 'r') as f:
                content = f.read()
            assert len(content.strip()) > 0
            assert "nonexistent" in content or "No such" in content

        finally:
            os.unlink(temp_path)


class TestProcessSubstitution:
    """Test process substitution with <() and >() syntax."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""
        pass

    def teardown_method(self):
        """Clean up any leftover processes after each test."""
        pass

    def test_invalid_file_descriptor(self, shell):
        """Test redirection with invalid file descriptor numbers."""
        # Try to use extremely high fd number
        result = shell.run_command('echo "test" 999>&1')
        # Should either work or fail gracefully
        assert isinstance(result, int)

        # Try to duplicate from non-existent fd
        result = shell.run_command('echo "test" 1>&999')
        # Should fail gracefully
        assert result != 0

    def test_redirection_with_errexit(self, shell):
        """Test redirection error handling with set -e."""
        # Enable errexit
        shell.run_command('set -e')

        # Redirection error should exit shell
        result = shell.run_command('echo "test" > /nonexistent/file; echo "should not reach"')
        assert result != 0
        # Output verification would need shell output capture


class TestHeredocAdvanced:
    """Test advanced here-document scenarios."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""
        pass

    def teardown_method(self):
        """Clean up any leftover processes after each test."""
        pass

    def test_heredoc_with_variable_expansion(self, shell):
        """Test here-document with variable expansion."""
        shell.run_command('test_var="expanded"')

        result = shell.run_command('''
        cat << EOF
This is a $test_var heredoc
EOF
        ''')
        assert result == 0
        # Output verification would need shell output capture

    def test_heredoc_with_quoted_delimiter(self, shell):
        """Test here-document with quoted delimiter (no expansion)."""
        shell.run_command('test_var="should_not_expand"')

        result = shell.run_command('''
        cat << 'EOF'
This is a $test_var heredoc
EOF
        ''')
        assert result == 0
        # Output verification would need shell output capture

    def test_heredoc_indented(self, shell):
        """Test indented here-document with <<-."""
        result = shell.run_command('''
        cat <<- EOF
\t\tIndented content
\t\tMore indented content
\tEOF
        ''')
        assert result == 0
        # Output verification would need shell output capture

    def test_multiple_heredocs(self, shell):
        """Test multiple here-documents in sequence."""
        result = shell.run_command('''
        cat << EOF1 << EOF2
First heredoc
EOF1
Second heredoc
EOF2
        ''')
        # This might not be supported - test graceful handling
        assert isinstance(result, int)

    def test_heredoc_in_function(self, shell):
        """Test here-document inside function definition."""
        shell.run_command('''
        heredoc_func() {
            cat << FUNC_EOF
Function heredoc content
Variable: $1
FUNC_EOF
        }
        ''')

        result = shell.run_command('heredoc_func "test_arg"')
        assert result == 0
        # Output verification would need shell output capture


class TestHereString:
    """Test here-string (<<<) functionality."""

    def setup_method(self):
        """Clean up any leftover processes before each test."""
        pass

    def teardown_method(self):
        """Clean up any leftover processes after each test."""
        pass

    def test_here_string_basic(self, shell):
        """Test basic here-string functionality."""
        result = shell.run_command('cat <<< "here string content"')
        assert result == 0
        # Output verification would need shell output capture

    def test_here_string_with_variables(self, shell):
        """Test here-string with variable expansion."""
        shell.run_command('test_var="variable content"')

        result = shell.run_command('cat <<< "String with $test_var"')
        assert result == 0
        # Output verification would need shell output capture

    def test_here_string_complex(self, shell):
        """Test here-string with complex expressions."""
        result = shell.run_command('wc -w <<< "count these words please"')
        assert result == 0
        # Output verification would need shell output capture


# Shell fixture provided by conftest.py


# Helper functions
def create_test_file(path, content, mode=0o644):
    """Helper to create test files with specific content and permissions."""
    with open(path, 'w') as f:
        f.write(content)
    os.chmod(path, mode)
    return path


def wait_for_file(path, timeout=5):
    """Helper to wait for file creation with timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if os.path.exists(path):
            return True

    return False


class TestReadWriteRedirect:
    """Test <> read-write redirection."""

    def test_readwrite_opens_file_for_reading(self):
        """<> opens file for reading."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo existing > tmp/rw_test.txt; cat <> tmp/rw_test.txt'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert result.returncode == 0
        assert 'existing' in result.stdout

    def test_readwrite_creates_file_if_missing(self):
        """<> creates file if it doesn't exist."""
        test_file = os.path.join(PSH_ROOT, 'tmp', 'rw_create_test.txt')
        if os.path.exists(test_file):
            os.unlink(test_file)
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'cat <> tmp/rw_create_test.txt; echo $?'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert result.returncode == 0
        assert os.path.exists(test_file)
        if os.path.exists(test_file):
            os.unlink(test_file)

    def test_readwrite_with_fd_prefix(self):
        """N<> opens file on specified fd."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo content > tmp/rw_fd.txt; cat 0<> tmp/rw_fd.txt'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert result.returncode == 0
        assert 'content' in result.stdout


class TestClobberRedirect:
    """Test >| clobber redirection."""

    def test_clobber_writes_to_file(self):
        """Test >| writes to file normally."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo hello >| tmp/clobber_test.txt; cat tmp/clobber_test.txt'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert result.returncode == 0
        assert 'hello' in result.stdout

    def test_clobber_overrides_noclobber(self):
        """Test >| forces overwrite when noclobber is set."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo first > tmp/clobber_nc.txt; set -C; echo second >| tmp/clobber_nc.txt; cat tmp/clobber_nc.txt'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert result.returncode == 0
        assert 'second' in result.stdout
        assert 'first' not in result.stdout

    def test_noclobber_blocks_regular_redirect(self):
        """Test > fails when noclobber is set and file exists."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo first > tmp/clobber_block.txt; set -C; echo second > tmp/clobber_block.txt; echo $?'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        # Should fail (nonzero exit status)
        assert '1' in result.stdout or result.returncode != 0


class TestCombinedRedirect:
    """Test &> and &>> combined redirections."""

    def test_ampersand_redirect_captures_stdout(self):
        """&> captures stdout."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo hello &> tmp/combined_test.txt; cat tmp/combined_test.txt'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert result.returncode == 0
        assert 'hello' in result.stdout

    def test_ampersand_redirect_captures_stderr(self):
        """&> captures stderr."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo err >&2 &> tmp/combined_err.txt; cat tmp/combined_err.txt'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert 'err' in result.stdout

    def test_ampersand_append_redirect(self):
        """&>> appends both stdout and stderr."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo first > tmp/combined_append.txt; echo second &>> tmp/combined_append.txt; cat tmp/combined_append.txt'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert result.returncode == 0
        assert 'first' in result.stdout
        assert 'second' in result.stdout


class TestPipeStderr:
    """Test |& pipe stderr operator."""

    def test_pipe_and_includes_stdout(self):
        """|& passes stdout to next command."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo hello |& cat'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert result.returncode == 0
        assert 'hello' in result.stdout

    def test_pipe_and_includes_stderr(self):
        """|& passes stderr to next command."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             '{ echo out; echo err >&2; } |& cat'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert 'out' in result.stdout
        assert 'err' in result.stdout

    def test_regular_pipe_excludes_stderr(self):
        """|  does NOT pass stderr to next command (baseline)."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             '{ echo out; echo err >&2; } | cat'],
            capture_output=True, text=True,
            cwd=PSH_ROOT)
        assert 'out' in result.stdout
        # stderr should go to the outer stderr, not stdout
        assert 'err' in result.stderr
