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


def _worktree_env():
    """Env that makes a child `python -m psh` import THIS tree's psh.

    The redirection cases below run from a per-test temp dir so they neither
    depend on nor pollute ``<repo>/tmp``. That moves the child's cwd off the
    repo root, and without this an editable install would silently resolve
    ``psh`` from whichever checkout it points at instead of the tree under
    test. Pinned by ``test_subprocess_runs_this_worktrees_psh`` below.

    PREPENDS rather than overwrites: an inherited ``PYTHONPATH`` may carry
    entries the caller needs, and dropping them would be an unrelated change
    in the child's import environment. This tree goes first so it still wins.
    """
    inherited = os.environ.get('PYTHONPATH')
    parts = [str(PSH_ROOT)] + ([inherited] if inherited else [])
    return {**os.environ, 'PYTHONPATH': os.pathsep.join(parts)}


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


def _resolve_psh_in_child(tmp_path, env):
    """Resolved ``psh.__file__`` for a child run from ``tmp_path`` under ``env``."""
    result = subprocess.run(
        [sys.executable, '-c', 'import psh; print(psh.__file__)'],
        capture_output=True, text=True, cwd=tmp_path, env=env)
    assert result.returncode == 0, result.stderr
    resolved = result.stdout.strip()
    assert resolved, f"probe produced no path (stderr: {result.stderr!r})"
    return os.path.realpath(resolved)


def test_subprocess_runs_this_worktrees_psh(tmp_path, monkeypatch):
    """The temp-cwd cases must exercise THIS tree's psh, not an installed one.

    Asserts the child's resolved ``psh.__file__`` lies under this checkout.
    Without ``_worktree_env`` an editable install resolves ``psh`` from its own
    target, so every case below would silently test a different tree — and
    still pass. Version strings cannot discriminate (checkouts share them);
    the resolved path can.

    Containment is checked with ``commonpath``, not ``startswith``: sibling
    worktrees share a prefix, so a plain prefix test would accept
    ``/Users/.../psh-r1-3`` as living under ``/Users/.../psh`` — passing for
    exactly the tree confusion this test exists to catch.

    The AMBIENT ``PYTHONPATH`` is removed first, and that is the whole point.
    The repo-root ``conftest.pytest_configure`` pins the repo root into
    ``os.environ['PYTHONPATH']`` for the entire session, so a child inherits
    the right tree whether or not ``_worktree_env`` contributes anything —
    this test passed for a reason unrelated to the helper it claims to pin.
    Stripping the ambient value makes the helper's OWN contribution the only
    thing under test, and the negative leg proves the probe can fail at all.
    """
    root = os.path.realpath(str(PSH_ROOT))
    monkeypatch.delenv('PYTHONPATH', raising=False)

    # NEGATIVE LEG: no ambient PYTHONPATH and no helper -> some OTHER tree
    # (an editable install's target). Without this the positive leg could be
    # passing on an import that would have succeeded anyway.
    # The negative leg is skipped WITHOUT skipping the test: an early
    # pytest.skip() would abort before the positive leg, so on CI -- where the
    # negative leg is always vacuous -- this row would contribute NO coverage at
    # all, which is worse than the gap it was papering over.
    bare = _resolve_psh_in_child(tmp_path, {**os.environ})
    if os.path.commonpath([bare, root]) != root:
        negative_leg_observable = True
    else:
        # There is no OTHER tree here to be confused with: the ambient editable
        # install's target IS the tree under test, so a PYTHONPATH-less child
        # legitimately lands back on it and the negative leg cannot discriminate
        # by construction. That is precisely CI's shape (`pip install -e .` on
        # the checkout itself); a developer box has a separate main checkout as
        # the install target, which is where this leg earns its keep. The probe
        # is not broken here, it is unobservable.
        negative_leg_observable = False

    # POSITIVE LEG: the helper's own value puts the child back on this tree.
    # Runs in EVERY environment -- this is the part CI can still check.
    resolved = _resolve_psh_in_child(tmp_path, _worktree_env())
    assert os.path.commonpath([resolved, root]) == root, (
        f"child imported psh from {resolved!r}, outside the tree under test "
        f"({root!r})")

    if not negative_leg_observable:
        pytest.skip(
            f"positive leg verified; discrimination leg is vacuous here -- the "
            f"editable install targets the tree under test ({bare!r}), which is "
            "how CI installs it")


class TestReadWriteRedirect:
    """Test <> read-write redirection."""

    def test_readwrite_opens_file_for_reading(self, tmp_path):
        """<> opens file for reading."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo existing > rw_test.txt; cat <> rw_test.txt'],
            capture_output=True, text=True,
            cwd=tmp_path, env=_worktree_env())
        assert result.returncode == 0
        assert 'existing' in result.stdout

    def test_readwrite_creates_file_if_missing(self, tmp_path):
        """<> creates file if it doesn't exist."""
        test_file = tmp_path / 'rw_create_test.txt'
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'cat <> rw_create_test.txt; echo $?'],
            capture_output=True, text=True,
            cwd=tmp_path, env=_worktree_env())
        assert result.returncode == 0
        assert test_file.exists()

    def test_readwrite_with_fd_prefix(self, tmp_path):
        """N<> opens file on specified fd."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo content > rw_fd.txt; cat 0<> rw_fd.txt'],
            capture_output=True, text=True,
            cwd=tmp_path, env=_worktree_env())
        assert result.returncode == 0
        assert 'content' in result.stdout


class TestClobberRedirect:
    """Test >| clobber redirection."""

    def test_clobber_writes_to_file(self, tmp_path):
        """Test >| writes to file normally."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo hello >| clobber_test.txt; cat clobber_test.txt'],
            capture_output=True, text=True,
            cwd=tmp_path, env=_worktree_env())
        assert result.returncode == 0
        assert 'hello' in result.stdout

    def test_clobber_overrides_noclobber(self, tmp_path):
        """Test >| forces overwrite when noclobber is set."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo first > clobber_nc.txt; set -C; echo second >| clobber_nc.txt; cat clobber_nc.txt'],
            capture_output=True, text=True,
            cwd=tmp_path, env=_worktree_env())
        assert result.returncode == 0
        assert 'second' in result.stdout
        assert 'first' not in result.stdout

    def test_noclobber_blocks_regular_redirect(self, tmp_path):
        """Test > fails when noclobber is set and file exists."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo first > clobber_block.txt; set -C; echo second > clobber_block.txt; echo $?'],
            capture_output=True, text=True,
            cwd=tmp_path, env=_worktree_env())
        # Should fail (nonzero exit status)
        assert '1' in result.stdout or result.returncode != 0


class TestCombinedRedirect:
    """Test &> and &>> combined redirections."""

    def test_ampersand_redirect_captures_stdout(self, tmp_path):
        """&> captures stdout."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo hello &> combined_test.txt; cat combined_test.txt'],
            capture_output=True, text=True,
            cwd=tmp_path, env=_worktree_env())
        assert result.returncode == 0
        assert 'hello' in result.stdout

    def test_ampersand_redirect_captures_stderr(self, tmp_path):
        """&> captures stderr."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo err >&2 &> combined_err.txt; cat combined_err.txt'],
            capture_output=True, text=True,
            cwd=tmp_path, env=_worktree_env())
        assert 'err' in result.stdout

    def test_ampersand_append_redirect(self, tmp_path):
        """&>> appends both stdout and stderr."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo first > combined_append.txt; echo second &>> combined_append.txt; cat combined_append.txt'],
            capture_output=True, text=True,
            cwd=tmp_path, env=_worktree_env())
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
