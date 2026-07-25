"""Redirection-failure behavior, pinned to bash 5.2.

When a redirection cannot be satisfied (target dir missing, source file
missing, permission denied) the documented contract — verified against
bash — is:

- the command exits nonzero (status 1 for the redirect-open failure);
- an error is written to stderr;
- the command BODY does not run (no output, no side effects);
- the shell's own fds are RESTORED — a following command in the same
  shell still writes to the right place.

Complements ``test_redirection_restore.py`` (which pins the save/restore
*rollback* defects); this file pins the user-visible failure contract and
the "body did not run" guarantee for input, output, and permission cases,
across builtin and external command bodies.

Most cases run psh in a subprocess: they exercise process-level fd state,
which must not run in the test runner's own process (CLAUDE.md); the one
in-process case uses only per-command fd-1 redirects. Vetted xdist-safe, so
this file runs in the parallel phase (campaign #21).
"""

import os

from shell_oracle import is_comparable
from shell_oracle import run_bash as _run_bash
from shell_oracle import run_psh as _run_psh


def run_psh(cmd, cwd=None):
    r = _run_psh(['-c', cmd], cwd=cwd, timeout=15)
    assert is_comparable(r), r
    return r


class TestOutputRedirectToMissingDir:
    """`cmd > /nonexistent_dir/x` — open fails before the body runs."""

    def test_builtin_body_does_not_run(self, tmp_path):
        """`echo SHOULDNOTPRINT > /missing/x`: nothing reaches stdout, the
        body did not execute, status is nonzero, error on stderr."""
        result = run_psh(
            'echo SHOULDNOTPRINT > /nonexistent_zz/x', cwd=tmp_path)
        assert result.returncode != 0
        assert result.stdout == '', "command body must not run"
        assert result.stderr != '', "an error should be reported"

    def test_external_body_does_not_run(self, tmp_path):
        result = run_psh(
            '/bin/echo NOPE > /nonexistent_zz/x', cwd=tmp_path)
        assert result.returncode != 0
        assert result.stdout == ''
        assert result.stderr != ''

    def test_exit_status_matches_bash(self, tmp_path):
        """Status for a failed output-redirect open is 1, like bash 5.2."""
        cmd = 'echo hi > /nonexistent_zz/x; echo rc=$?'
        psh = run_psh(cmd, cwd=tmp_path)
        bash = _run_bash(['-c', cmd], cwd=tmp_path)
        assert is_comparable(bash), bash
        assert psh.stdout == bash.stdout == 'rc=1\n'

    def test_fds_restored_following_command_writes(self, tmp_path):
        """A following command in the same shell writes to the real
        stdout, proving the failed redirect did not hijack fd 1."""
        result = run_psh(
            'echo hi > /nonexistent_zz/x; echo RESTORED', cwd=tmp_path)
        assert result.stdout == 'RESTORED\n'


class TestInputRedirectFromMissingFile:
    """`cmd < /nonexistent_file` — open fails before the body runs."""

    def test_body_does_not_run(self, tmp_path):
        result = run_psh('cat < /nonexistent_file_zz', cwd=tmp_path)
        assert result.returncode != 0
        assert result.stdout == '', "cat must not run"
        assert result.stderr != ''

    def test_exit_status_matches_bash(self, tmp_path):
        cmd = 'cat < /nonexistent_file_zz; echo rc=$?'
        psh = run_psh(cmd, cwd=tmp_path)
        bash = _run_bash(['-c', cmd], cwd=tmp_path)
        assert is_comparable(bash), bash
        assert psh.stdout == bash.stdout == 'rc=1\n'

    def test_stdin_restored_following_read(self, tmp_path):
        """After a failed input redirect, the shell's stdin is restored:
        a following `read` from the (here-doc) stdin still works."""
        # Feed stdin via a heredoc-free pipe through subprocess input.
        result = _run_psh(
            ['-c', 'cat < /nonexistent_file_zz; read v; echo "got=$v"'],
            stdin_data='hello\n', stdin_mode='pipe', cwd=tmp_path, timeout=15)
        assert is_comparable(result), result
        assert result.stdout == 'got=hello\n'


class TestPermissionDeniedRedirect:
    """Output redirect into a read-only directory fails deterministically.

    A 0555 directory denies file creation regardless of system load — no
    resource exhaustion needed.
    """

    def test_body_does_not_run(self, tmp_path):
        ro = tmp_path / 'ro'
        ro.mkdir()
        os.chmod(ro, 0o555)
        try:
            result = run_psh('echo NOPE > ro/x', cwd=tmp_path)
            assert result.returncode != 0
            assert result.stdout == ''
            assert result.stderr != ''
            # The file was never created.
            assert not (ro / 'x').exists()
        finally:
            os.chmod(ro, 0o755)

    def test_exit_status_matches_bash(self, tmp_path):
        ro = tmp_path / 'ro'
        ro.mkdir()
        os.chmod(ro, 0o555)
        try:
            cmd = 'echo hi > ro/x; echo rc=$?'
            psh = run_psh(cmd, cwd=tmp_path)
            bash = _run_bash(['-c', cmd], cwd=tmp_path)
            assert is_comparable(bash), bash
            assert psh.stdout == bash.stdout == 'rc=1\n'
        finally:
            os.chmod(ro, 0o755)

    def test_fds_restored_following_command(self, tmp_path):
        ro = tmp_path / 'ro'
        ro.mkdir()
        os.chmod(ro, 0o555)
        try:
            result = run_psh('echo hi > ro/x; echo RESTORED', cwd=tmp_path)
            assert result.stdout == 'RESTORED\n'
        finally:
            os.chmod(ro, 0o755)


class TestRedirectFailureInProcessRestore:
    """The in-process per-command fd save/restore path (not exec/permanent).

    A per-command redirect failure inside a single live shell must restore
    the shell's output so the NEXT command in the same shell still prints.
    Uses ``captured_shell`` (captures via the shell's own stdout object,
    never capsys/real fds — per CLAUDE.md). Per-command redirects are the
    documented-safe in-process case; this is NOT a permanent `exec`
    redirect.
    """

    def test_following_command_output_intact(self, captured_shell):
        shell = captured_shell
        rc1 = shell.run_command('echo first > /nonexistent_zz/x')
        assert rc1 != 0
        rc2 = shell.run_command('echo SECOND')
        assert rc2 == 0
        out = shell.get_stdout()
        assert 'first' not in out, "failed-redirect body must not run"
        assert 'SECOND' in out, "shell output must be restored for next command"
