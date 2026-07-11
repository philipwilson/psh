"""
Exec builtin tests.

Tests for the exec builtin which can replace the shell process or
apply redirections permanently to the current shell.

`exec` applies redirections *permanently* to the running shell's file
descriptors. These must be tested in a subprocess, never via the in-process
`shell` fixture: an in-process `exec >file` rewrites the test runner's own fds,
which under pytest-xdist are the execnet worker channel — clobbering them aborts
the whole parallel session. See docs/reviews/parallel_test_safety_2026-06-06.md.
"""

import os
import subprocess
import sys


def _run_psh(script, cwd):
    """Run a psh script in a subprocess so permanent fd redirection is isolated."""
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        cwd=cwd, capture_output=True, text=True,
    )


def test_exec_builtin_exists(shell):
    """Test that exec is registered as a builtin."""
    result = shell.run_command('type exec')
    assert result == 0


def test_exec_without_command(shell):
    """Test exec without command and no redirections."""
    result = shell.run_command('exec')
    assert result == 0


def test_exec_with_output_redirection(temp_dir):
    """exec >file redirects all subsequent output to the file (subprocess)."""
    result = _run_psh('exec > exec_test.txt; echo "redirected output"', temp_dir)
    assert result.returncode == 0
    with open(os.path.join(temp_dir, "exec_test.txt")) as f:
        assert "redirected output" in f.read()


def test_exec_with_input_redirection(temp_dir):
    """exec <file makes subsequent reads come from the file (subprocess)."""
    with open(os.path.join(temp_dir, "exec_input.txt"), 'w') as f:
        f.write("test input data\n")
    result = _run_psh('exec < exec_input.txt; read line; echo "got: $line"', temp_dir)
    assert result.returncode == 0
    assert result.stdout.strip() == "got: test input data"


def test_exec_with_command_replacement():
    """Test exec with command replacement using subprocess."""
    import subprocess
    import sys

    # Test exec replacing the shell process
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'exec echo "replaced process"'],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    assert "replaced process" in result.stdout

    # Test exec with different command
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'exec true'],
        capture_output=True
    )
    assert result.returncode == 0

    # Test exec with failing command
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'exec false'],
        capture_output=True
    )
    assert result.returncode != 0


def test_exec_with_error_redirection(temp_dir):
    """exec 2>file redirects subsequent stderr to the file (subprocess)."""
    result = _run_psh('exec 2> exec_error.txt; echo oops >&2', temp_dir)
    assert result.returncode == 0
    with open(os.path.join(temp_dir, "exec_error.txt")) as f:
        assert "oops" in f.read()


def test_exec_with_fd_operations(temp_dir):
    """exec 3>&1 duplicates stdout to fd 3 for later use (subprocess)."""
    result = _run_psh('exec 3>&1; echo viafd3 >&3', temp_dir)
    assert result.returncode == 0
    assert result.stdout.strip() == "viafd3"


def test_exec_fd_redirection_lifecycle(temp_dir):
    """exec fd lifecycle should preserve explicit descriptors across commands."""
    import subprocess
    import sys

    output_file = "fd3_output.txt"
    command = f'exec 3> {output_file}; echo "fd write" >&3; exec 3>&-; cat {output_file}'

    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", command],
        cwd=temp_dir,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == "fd write\n"
    assert result.stderr == ""

    with open(os.path.join(temp_dir, output_file), 'r') as f:
        assert f.read().strip() == "fd write"


def test_exec_error_handling(shell):
    """Test exec error handling with invalid arguments."""
    # Test with non-existent command
    result = shell.run_command('exec /nonexistent/command')
    assert result != 0


def test_exec_with_environment(shell):
    """Test exec with environment variable assignment."""
    result = shell.run_command('VAR=value exec')
    assert result == 0


def test_exec_help_option(shell):
    """exec has no --help flag: like bash it rejects the unknown option with
    a usage error (status 2), not command-not-found."""
    assert shell.run_command('exec --help') == 2
    # Just test that it doesn't crash


def test_exec_syntax_error(shell):
    """Test exec with syntax errors."""
    result = shell.run_command('exec >')
    # Should fail with incomplete redirection
    assert result != 0


def test_exec_redirection_persistence(temp_dir):
    """exec redirection persists across subsequent commands (subprocess)."""
    result = _run_psh(
        'exec > persistent_output.txt; echo first; echo second; echo third',
        temp_dir,
    )
    assert result.returncode == 0
    with open(os.path.join(temp_dir, "persistent_output.txt")) as f:
        content = f.read()
    assert 'first' in content and 'second' in content and 'third' in content


class TestExecFailureExitsShell:
    """POSIX: a non-interactive shell exits when `exec command` fails.

    Regression: psh used to print the error and keep executing with rc 0
    (bash: rc 127, no further commands run).
    """

    @staticmethod
    def _run_psh(cmd):
        import subprocess
        import sys
        return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                              capture_output=True, text=True)

    def test_exec_missing_command_exits_127(self):
        result = self._run_psh('exec nonexistent_cmd_zz; echo after')
        assert result.returncode == 127
        assert 'after' not in result.stdout
        # bash's exec builtin says "exec: NAME: not found" for a bare name
        # (unlike the plain-command "command not found").
        assert 'exec: nonexistent_cmd_zz: not found' in result.stderr

    def test_exec_not_executable_exits_126(self):
        result = self._run_psh('exec /etc; echo after')
        assert result.returncode == 126
        assert 'after' not in result.stdout

    def test_exec_success_replaces_shell(self):
        result = self._run_psh('exec /bin/echo replaced; echo not-reached')
        assert result.returncode == 0
        assert result.stdout == 'replaced\n'
        assert 'not-reached' not in result.stdout

    def test_interactive_shell_survives_exec_failure(self, shell):
        """The interactive-mode shell reports 127 but keeps running."""
        result = shell.run_command('exec nonexistent_cmd_zz')
        assert result == 127
        # Shell still functional
        assert shell.run_command('true') == 0


class TestExecFailureDiagnostics:
    """Exec-failure wording, pinned to bash 5.2 (reappraisal #17 builtins M2).

    Every line carries bash's ``<$0>: line N:`` location prefix (task #21 [#35]);
    ``psh``'s $0 analogue is "psh". Wording after the prefix:
      exec /no/such/x   -> "/no/such/x: No such file or directory"   rc 127
      exec nosuchcmd    -> "exec: nosuchcmd: not found"              rc 127
      exec ""           -> "exec: : not found"                       rc 127
      exec /etc         -> "/etc: Is a directory" + a second line
                           "exec: /etc: cannot execute: Is a directory", rc 126
    Never the raw Python OSError repr ("[Errno 13] ...").
    """

    @staticmethod
    def _run_psh(cmd):
        import subprocess
        import sys
        return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                              capture_output=True, text=True, timeout=15)

    def test_pathname_not_found_says_no_such_file(self):
        result = self._run_psh('exec /no/such/path/x')
        assert result.returncode == 127
        # bash location-prefixes it (`<$0>: line N:`), no `exec:` builtin name.
        assert result.stderr.strip() == \
            'psh: line 1: /no/such/path/x: No such file or directory'

    def test_bare_name_says_not_found(self):
        result = self._run_psh('exec nosuchcmd_zz_9')
        assert result.returncode == 127
        assert result.stderr.strip() == 'psh: line 1: exec: nosuchcmd_zz_9: not found'
        assert 'command not found' not in result.stderr

    def test_empty_command_says_not_found(self):
        result = self._run_psh('exec ""')
        assert result.returncode == 127
        assert result.stderr.strip() == 'psh: line 1: exec: : not found'

    def test_directory_two_line_diagnostic(self):
        result = self._run_psh('exec /etc')
        assert result.returncode == 126
        lines = result.stderr.strip().splitlines()
        # Both lines are location-prefixed in bash; the first names the file
        # (no builtin name), the second is the exec builtin's own diagnostic.
        assert lines == [
            'psh: line 1: /etc: Is a directory',
            'psh: line 1: exec: /etc: cannot execute: Is a directory',
        ]

    def test_not_executable_file_two_line_diagnostic(self, tmp_path):
        target = tmp_path / 'noexec.sh'
        target.write_text('#!/bin/sh\necho hi\n')
        target.chmod(0o644)
        result = self._run_psh(f'exec {target}')
        assert result.returncode == 126
        lines = result.stderr.strip().splitlines()
        assert lines[0] == f'psh: line 1: {target}: Permission denied'
        assert lines[1] == f'psh: line 1: exec: {target}: cannot execute: Permission denied'

    def test_no_raw_oserror_repr(self):
        for cmd in ('exec /etc', 'exec /no/such/x', 'exec ""'):
            result = self._run_psh(cmd)
            assert '[Errno' not in result.stderr, (cmd, result.stderr)
