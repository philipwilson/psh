"""
Nested builtin redirections (per-invocation frames).

Builtin redirections NEST: ``eval "echo one >&3" 3>&1`` opens a
redirection frame for the eval builtin, then the eval'd ``echo`` opens an
inner frame while the outer is still active. The same happens for
``source file 3>&1`` (the sourced file's commands) and for trap handlers
firing while a redirected builtin runs.

Before v0.302 the IOManager kept this state on the SHARED manager
instance (``_saved_fds_list`` drained wholesale, ``_opened_streams``
reassigned on every setup), so the INNER restore undid the OUTER
invocation's redirects: in the headline case, the second ``echo ... >&3``
found fd 3 pointing back at the exec-time file instead of stdout. Each
``setup_builtin_redirections`` now returns a ``BuiltinRedirectFrame`` and
``restore_builtin_redirections(frame)`` restores exactly that frame,
innermost-first.

Every expectation below was probed against bash 5.2 first
(bash-verification workflow); psh and bash agree on all of them.

Cases that involve ``exec n>file`` (permanent, process-level fd
redirection) run psh in a subprocess per the parallel-safety rules in
CLAUDE.md. Purely per-command cases use the isolated shell fixture.
This directory is auto-marked ``serial`` by conftest.
"""

import os
import subprocess
import sys

PSH = [sys.executable, '-m', 'psh', '-c']


def run_psh(script: str, cwd=None):
    return subprocess.run(PSH + [script], capture_output=True, text=True,
                          cwd=cwd, timeout=30)


class TestEvalNestingFdLevel:
    """fd-level (fd >= 3) redirects must survive a nested frame's restore."""

    def test_headline_eval_fd3_nesting(self, tmp_path):
        """eval body redirects via fd 3 while the eval itself has 3>&1.

        bash 5.2: both lines reach stdout, the exec'd file stays empty.
        Before the frame fix, the first echo's restore re-pointed fd 3 at
        the file, so the second line landed in the file.
        """
        f = tmp_path / 'fd3.txt'
        result = run_psh(
            f'exec 3>"{f}"; eval "echo one >&3; echo two >&3" 3>&1')
        assert result.returncode == 0
        assert result.stdout == 'one\ntwo\n'
        assert result.stderr == ''
        assert f.read_text() == ''

    def test_double_eval_three_frames_deep(self, tmp_path):
        """eval inside eval: three frames open at once (bash-verified)."""
        f = tmp_path / 'fd3.txt'
        result = run_psh(
            f'exec 3>"{f}"; '
            'eval "eval \\"echo i1 >&3; echo i2 >&3\\" 3>&1; echo o1 >&3" 3>&1')
        assert result.returncode == 0
        assert result.stdout == 'i1\ni2\no1\n'
        assert f.read_text() == ''

    def test_fd4_dup_to_stderr_nesting(self, tmp_path):
        """exec 4>f; eval "echo ... >&4" 4>&2 — both lines go to stderr."""
        f = tmp_path / 'fd4.txt'
        result = run_psh(f'exec 4>"{f}"; eval "echo a >&4; echo b >&4" 4>&2')
        assert result.returncode == 0
        assert result.stdout == ''
        assert result.stderr == 'a\nb\n'
        assert f.read_text() == ''

    def test_three_deep_mixed_universes(self, tmp_path):
        """Inner frame swaps the stdout STREAM (>/dev/null) while ``>&3``
        needs the fd universe — bash prints b and c, file g gets a.

        Also pins the both-universes handling of ``1>&m`` (m >= 3): the
        builtin writes through a possibly-swapped sys.stdout, so the dup
        must swap the stream too, not just dup2 fd 1.
        """
        f = tmp_path / 'fd3.txt'
        g = tmp_path / 'g.txt'
        result = run_psh(
            f'exec 3>"{f}"; '
            f'eval "eval \\"echo a >\\\\\\"{g}\\\\\\"; echo b >&3\\" >/dev/null; '
            'echo c >&3" 3>&1')
        assert result.returncode == 0
        assert result.stdout == 'b\nc\n'
        assert f.read_text() == ''
        assert g.read_text() == 'a\n'


class TestEvalNestingStreamLevel:
    """Stream-universe (fd 1/2 swap) state is also per-frame."""

    def test_eval_stdout_nesting(self, isolated_shell_with_temp_dir):
        """eval "echo a >/dev/null; echo b" >f — b lands in f (bash-verified).

        The inner echo's frame swaps sys.stdout to /dev/null and must
        restore the OUTER eval's file stream, not the shell's original.
        """
        shell = isolated_shell_with_temp_dir
        shell.run_command('eval "echo a >/dev/null; echo b" > outer.txt')
        cwd = shell.state.variables['PWD']
        with open(os.path.join(cwd, 'outer.txt')) as fh:
            assert fh.read() == 'b\n'

    def test_eval_stream_clobber_two_files(self, isolated_shell_with_temp_dir):
        """Nested stream redirects to two different files (bash-verified)."""
        shell = isolated_shell_with_temp_dir
        shell.run_command('eval "echo in1 > g.txt; echo in2" > f.txt')
        cwd = shell.state.variables['PWD']
        with open(os.path.join(cwd, 'f.txt')) as fh:
            assert fh.read() == 'in2\n'
        with open(os.path.join(cwd, 'g.txt')) as fh:
            assert fh.read() == 'in1\n'

    def test_eval_stdin_nesting(self):
        """Inner here-string must not clobber outer stdin (bash-verified:
        x:inner then y:<outer>)."""
        result = subprocess.run(
            PSH + ['eval "read x <<< inner; echo x:\\$x"; read y; echo "y:<$y>"'],
            input='outer\n', capture_output=True, text=True, timeout=30)
        assert result.returncode == 0
        assert result.stdout == 'x:inner\ny:<outer>\n'


class TestSourceNesting:
    """source file with redirections; the file's builtins redirect too."""

    def test_source_fd3_nesting(self, tmp_path):
        f = tmp_path / 'fd3.txt'
        s = tmp_path / 'lib.sh'
        s.write_text('echo s1 >&3\necho s2 >&3\n')
        result = run_psh(f'exec 3>"{f}"; source "{s}" 3>&1')
        assert result.returncode == 0
        assert result.stdout == 's1\ns2\n'
        assert f.read_text() == ''

    def test_source_stdout_nesting(self, tmp_path):
        f = tmp_path / 'out.txt'
        s = tmp_path / 'lib.sh'
        s.write_text('echo in1 >/dev/null\necho in2\n')
        result = run_psh(f'source "{s}" > "{f}"')
        assert result.returncode == 0
        assert result.stdout == ''
        assert f.read_text() == 'in2\n'


class TestTrapNesting:
    """Trap handlers run redirected builtins while other frames are open."""

    def test_debug_trap_during_redirected_eval(self, tmp_path):
        """DEBUG trap writes to fd 3 around a redirected eval.

        bash 5.2 (probe-verified): the trap fires for the eval (fd 3 ->
        stdout at that moment, T to stdout) and for the two top-level
        commands after it (fd 3 -> file, T,T to the file); the eval'd
        echo goes to stdout.
        """
        f = tmp_path / 'fd3.txt'
        result = run_psh(
            f'exec 3>"{f}"; trap "echo T >&3" DEBUG; '
            'eval "echo e >&3" 3>&1; trap - DEBUG; '
            f'printf "FILE:<%s>\\n" "$(cat "{f}")"')
        assert result.returncode == 0
        assert result.stdout == 'T\ne\nFILE:<T\nT>\n'
        assert f.read_text() == 'T\nT\n'

    def test_exit_trap_after_redirected_eval(self, tmp_path):
        """EXIT trap's fd-3 redirect sees the exec-time target, not the
        eval's 3>&1 (bash-verified: e to stdout, T to the file)."""
        f = tmp_path / 'fd3.txt'
        result = run_psh(
            f'exec 3>"{f}"; trap "echo T >&3" EXIT; eval "echo e >&3" 3>&1')
        assert result.returncode == 0
        assert result.stdout == 'e\n'
        assert f.read_text() == 'T\n'


class TestCommandSubstitutionNesting:
    """Command substitution forks; the child's builtin redirects must not
    leak into the parent's frame state."""

    def test_cmdsub_builtin_inside_redirected_eval(self, tmp_path):
        """x=$(echo cs >&3) inside eval ... 3>&1 (bash-verified: the
        cmdsub child inherits fd 3 -> the shell's stdout, so cs bypasses
        the capture pipe and x is empty; the following echo still sees
        fd 3 -> stdout; the exec'd file stays empty)."""
        f = tmp_path / 'fd3.txt'
        result = run_psh(
            f'exec 3>"{f}"; '
            'eval "x=\\$(echo cs >&3); echo after >&3; echo x:\\$x" 3>&1')
        assert result.returncode == 0
        assert result.stdout == 'cs\nafter\nx:\n'
        assert f.read_text() == ''


class TestRollbackNesting:
    """A failing redirect in a nested frame rolls back ONLY that frame."""

    def test_failed_inner_redirect_keeps_outer_fd3(self, tmp_path):
        """eval "echo x > /nonexistent-dir/f; echo y" 3>&1 inside
        exec 3>file: bash continues, y goes to stdout (fd 3 -> stdout
        still), exit 0, file empty. Before the frame fix the failed
        setup's rollback drained the outer frame's fd saves, so y landed
        in the file."""
        f = tmp_path / 'fd3.txt'
        result = run_psh(
            f'exec 3>"{f}"; '
            'eval "echo x > /nonexistent-dir/f; echo y >&3" 3>&1; echo rc=$?')
        assert result.returncode == 0
        assert 'No such file or directory' in result.stderr
        assert result.stdout == 'y\nrc=0\n'
        assert f.read_text() == ''

    def test_failed_inner_redirect_keeps_outer_stream(
            self, isolated_shell_with_temp_dir):
        """Stream-universe rollback: the inner failure must not restore
        the OUTER eval's stdout swap (bash-verified: f gets ok)."""
        shell = isolated_shell_with_temp_dir
        shell.run_command(
            'eval "echo bad > /nonexistent-dir/x; echo ok" > f.txt')
        cwd = shell.state.variables['PWD']
        with open(os.path.join(cwd, 'f.txt')) as fh:
            assert fh.read() == 'ok\n'


class TestSingleLevelRegression:
    """Plain single-frame builtin redirections keep working (the bulk of
    coverage lives in the rest of this directory and unit/builtins)."""

    def test_simple_builtin_redirects(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('echo hi > a.txt')
        shell.run_command('echo more >> a.txt')
        cwd = shell.state.variables['PWD']
        with open(os.path.join(cwd, 'a.txt')) as fh:
            assert fh.read() == 'hi\nmore\n'

    def test_stderr_dup_then_normal_output(self, tmp_path):
        """2>&1 swap restores cleanly; later builtin output unaffected."""
        result = run_psh('echo one 2>&1; echo two')
        assert result.returncode == 0
        assert result.stdout == 'one\ntwo\n'
