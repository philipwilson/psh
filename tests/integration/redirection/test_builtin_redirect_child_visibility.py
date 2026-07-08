"""Redirections on in-process builtins reach the CHILDREN they spawn.

Reappraisal #15, Cluster C1/C2. An in-process builtin (``eval``, ``source``,
``command``) writes through the Python stream objects, but a child it spawns
(``eval`` running an external / a pipeline, ``command`` running an external)
inherits the raw fds. Before the fix, a ``> file`` / ``2> file`` on such a
builtin was applied as a Python-stream swap ONLY, so the child's fd 1/2
still pointed at the terminal and its output/errors leaked. stdin already
got the fd-level treatment; fd 1/2 now do too (a per-command dup2 sharing
the opened file's description, saved/restored around the one command).

Contract pinned to bash 5.2:

- ``command EXT > f`` / ``> /dev/null`` — the external's stdout obeys the
  redirect (no leak);
- ``eval "... EXT ..." > f`` / ``2> f`` / ``2>&1`` — a child spawned by the
  eval'd string obeys the redirect;
- ``source file > f`` / ``2> f`` — likewise for a sourced file's commands;
- a pure-builtin write and a builtin-in-a-pipeline are unaffected.

Runs psh in a subprocess (process-level fd state), so it is xdist-safe and
runs in the parallel phase (vetted in campaign #21).
"""

import subprocess
import sys


def run_psh(cmd, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, cwd=cwd, timeout=15)


class TestCommandBuiltinRedirect:
    """`command EXT`/`command BUILTIN` obey the redirect on the word."""

    def test_command_external_stdout_to_file(self, tmp_path):
        run_psh("command /bin/echo hi > out", cwd=tmp_path)
        assert (tmp_path / 'out').read_text() == 'hi\n'

    def test_command_external_stdout_to_devnull_no_leak(self, tmp_path):
        """`command ls . > /dev/null` prints nothing (the external's fd 1
        was redirected, not just the builtin's Python stream)."""
        psh = run_psh("command ls . > /dev/null", cwd=tmp_path)
        assert psh.stdout == ''

    def test_command_external_stderr_to_file(self, tmp_path):
        psh = run_psh("command ls /nonexistent_zz 2> err", cwd=tmp_path)
        assert psh.stderr == '', 'stderr must be redirected, not leak'
        assert (tmp_path / 'err').read_text() != ''

    def test_command_external_combined_2to1(self, tmp_path):
        run_psh("command ls /nonexistent_zz > out 2>&1", cwd=tmp_path)
        assert (tmp_path / 'out').read_text() != ''

    def test_command_builtin_stdout_to_file(self, tmp_path):
        run_psh("command echo hi > out", cwd=tmp_path)
        assert (tmp_path / 'out').read_text() == 'hi\n'

    def test_builtin_keyword_stdout_to_file(self, tmp_path):
        run_psh("builtin echo hi > out", cwd=tmp_path)
        assert (tmp_path / 'out').read_text() == 'hi\n'

    def test_command_builtin_write_error_on_closed_fd(self, tmp_path):
        """`command echo 1>&-` reports bash's write error (guarded path)."""
        psh = run_psh("command echo hi 1>&-", cwd=tmp_path)
        assert psh.returncode == 1
        assert 'write error' in psh.stderr


class TestEvalRedirect:
    """A child spawned by an eval'd string obeys the eval's redirect."""

    def test_eval_external_stdout_to_file(self, tmp_path):
        run_psh('eval "echo pre; /bin/echo EXT" > out', cwd=tmp_path)
        assert (tmp_path / 'out').read_text() == 'pre\nEXT\n'

    def test_eval_pipeline_stdout_to_file(self, tmp_path):
        run_psh('eval "/bin/echo X | cat" > out', cwd=tmp_path)
        assert (tmp_path / 'out').read_text() == 'X\n'

    def test_eval_external_stderr_to_file(self, tmp_path):
        psh = run_psh('eval "ls /nonexistent_zz" 2> err', cwd=tmp_path)
        assert psh.stderr == ''
        assert (tmp_path / 'err').read_text() != ''

    def test_eval_external_combined_2to1(self, tmp_path):
        run_psh('eval "ls /nonexistent_zz" > out 2>&1', cwd=tmp_path)
        assert (tmp_path / 'out').read_text() != ''
        # nothing leaked to the real stderr
        psh = run_psh('eval "ls /nonexistent_zz" > out 2>&1', cwd=tmp_path)
        assert psh.stderr == ''

    def test_nested_eval_stdout_to_file(self, tmp_path):
        run_psh('eval "eval \\"/bin/echo deep\\"" > out', cwd=tmp_path)
        assert (tmp_path / 'out').read_text() == 'deep\n'

    def test_eval_write_and_external_share_offset(self, tmp_path):
        """The builtin's stream write and the external child's fd write keep
        one file offset (no re-truncation): both land, in order."""
        run_psh('eval "echo one; /bin/echo two" > out', cwd=tmp_path)
        assert (tmp_path / 'out').read_text() == 'one\ntwo\n'


class TestSourceRedirect:
    """A sourced file's commands obey the redirect on the `source` word."""

    def test_source_stdout_to_file(self, tmp_path):
        (tmp_path / 's.sh').write_text('echo fromfile\n/bin/echo ext\n')
        run_psh('source s.sh > out', cwd=tmp_path)
        assert (tmp_path / 'out').read_text() == 'fromfile\next\n'

    def test_source_stderr_to_file(self, tmp_path):
        (tmp_path / 's.sh').write_text('ls /nonexistent_zz\n')
        psh = run_psh('source s.sh 2> err', cwd=tmp_path)
        assert psh.stderr == ''
        assert (tmp_path / 'err').read_text() != ''


class TestNoRegressionForCoveredPaths:
    """Paths that already worked must keep working."""

    def test_pure_builtin_write_still_redirected(self, tmp_path):
        run_psh('eval "echo hi" > out', cwd=tmp_path)
        assert (tmp_path / 'out').read_text() == 'hi\n'

    def test_builtin_in_pipeline_still_redirected(self, tmp_path):
        run_psh('echo hi | cat > out', cwd=tmp_path)
        assert (tmp_path / 'out').read_text() == 'hi\n'
