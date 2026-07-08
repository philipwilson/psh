"""Permanent `exec >&-`/`2>&-` close: a builtin's write must never leak.

The invariant these tests pin (absent from the pre-existing close/reopen
matrix, which never wrote through a builtin while the std fd was closed and
then reopened it and inspected the reopened stream):

    bytes a builtin writes to a std fd closed by permanent `exec >&-` never
    reappear on ANY later reopen of that fd.

Before the fix, `exec >&-` left the natural buffering `TextIOWrapper` in
`sys.stdout`; a builtin's post-close write buffered there, its flush failed
EBADF, and the retained bytes flushed into the REOPENED fd at shutdown
(`exec 3>&1; exec >&-; echo LEAK; exec >&3 3>&-; echo end` → psh printed
`end` THEN `LEAK`; bash prints only `end`). The fix installs a `_RawFdStream`
(write→`os.write`, no buffer) that fails cleanly while the fd is closed yet
still follows the fd when a compound/function body reopens it at the fd level.

Every expected value below is bash 5.2's output for the same script.

CRITICAL: permanent fd redirection rewrites the shell's own fds, which in the
test runner are the pytest/xdist channel — so every test here runs psh in a
SUBPROCESS, never in-process (see CLAUDE.md "Parallel-safety rules"). That
also keeps them xdist-safe without the `serial` marker.
"""

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def run_psh(script, cwd):
    env = {**os.environ, 'PYTHONPATH': str(_REPO_ROOT)}
    env.pop('DISPLAY', None)
    env.pop('XAUTHORITY', None)
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, cwd=cwd, timeout=10, env=env)


def read(path):
    with open(path) as f:
        return f.read()


class TestExecCloseOutputLeak:
    """The MED-1 no-leak invariant: builtin output to a closed std fd is gone."""

    def test_echo_reopen_via_saved_fd_no_leak(self, temp_dir):
        # The canonical repro. bash prints only `end`.
        r = run_psh('exec 3>&1; exec >&-; echo LEAK; exec >&3 3>&-; echo end',
                    temp_dir)
        assert r.returncode == 0
        assert r.stdout == 'end\n'
        assert 'LEAK' not in r.stdout

    def test_printf_reopen_via_saved_fd_no_leak(self, temp_dir):
        # printf (no trailing newline) buffers just the same — must not leak.
        r = run_psh('exec 3>&1; exec >&-; printf LEAK; exec >&3 3>&-; echo end',
                    temp_dir)
        assert r.returncode == 0
        assert r.stdout == 'end\n'

    def test_echo_n_reopen_no_leak(self, temp_dir):
        r = run_psh('exec 3>&1; exec >&-; echo -n LEAK; exec >&3 3>&-; echo end',
                    temp_dir)
        assert r.returncode == 0
        assert r.stdout == 'end\n'

    def test_multiple_builtins_between_close_and_reopen(self, temp_dir):
        # A, B, C all write to the closed fd; none may resurface.
        r = run_psh(
            'exec 3>&1; exec >&-; echo A; echo B; printf C; '
            'exec >&3 3>&-; echo end', temp_dir)
        assert r.returncode == 0
        assert r.stdout == 'end\n'

    def test_heal_reopen_onto_fd2_no_leak(self, temp_dir):
        # The "healing" reopen the old docstring claimed was safe: close fd 1,
        # write, then point fd 1 at fd 2. bash: nothing leaks to fd 2.
        r = run_psh(
            'exec 3>&1; exec 1>&-; echo LEAK; exec 1>&2; echo end >&2', temp_dir)
        assert r.returncode == 0
        assert r.stdout == ''
        assert 'end' in r.stderr
        assert 'LEAK' not in r.stderr

    def test_reopen_to_file_leak_not_in_file(self, temp_dir):
        # The reopen target is a fresh file; the closed-fd bytes must not land
        # in it. bash: the file holds only `end`.
        r = run_psh('exec >&-; echo LEAK; exec >out.txt; echo end', temp_dir)
        assert r.returncode == 0
        assert read(os.path.join(temp_dir, 'out.txt')) == 'end\n'

    def test_reopen_via_fresh_file_redirect_no_leak(self, temp_dir):
        r = run_psh('exec 3>&1; exec >&-; echo LEAK; exec >o2.txt; echo end',
                    temp_dir)
        assert r.returncode == 0
        assert read(os.path.join(temp_dir, 'o2.txt')) == 'end\n'

    def test_double_close_reopen_no_leak(self, temp_dir):
        r = run_psh(
            'exec 3>&1; exec >&-; echo L1; exec >&3; echo mid; '
            'exec >&-; echo L2; exec >&3 3>&-; echo end', temp_dir)
        assert r.returncode == 0
        assert r.stdout == 'mid\nend\n'

    def test_with_prior_override_close_reopen_no_leak(self, temp_dir):
        # exec >file installs a state override (dup of the file); closing then
        # reopening onto fd 2 must not leak the buffered write into fd 2.
        r = run_psh(
            'exec >f.txt; exec >&-; echo LEAK; exec >&2; echo end >&2', temp_dir)
        assert r.returncode == 0
        assert 'LEAK' not in r.stderr
        assert 'end' in r.stderr
        # f.txt captured nothing after the close either.
        assert read(os.path.join(temp_dir, 'f.txt')) == ''

    def test_external_writer_does_not_leak_control(self, temp_dir):
        # An external command writes through the raw fd, gets EBADF at once,
        # buffers nothing — already correct; pin it as the control.
        r = run_psh(
            'exec 3>&1; exec >&-; /bin/echo LEAK; exec >&3 3>&-; echo end',
            temp_dir)
        assert r.returncode == 0
        assert r.stdout == 'end\n'


class TestExecCloseReopenTransparency:
    """The other side of the fix: a compound/function body that reopens the
    closed fd at the fd level (`f 1>&2`, `{ ...; } >g`, `&>f`) must still land
    — the raw stream follows the fd, so the reopen heals exactly as bash does.
    """

    def test_function_reopen_fd1_to_stderr_lands(self, temp_dir):
        r = run_psh('exec 1>&-; f(){ echo a; }; f 1>&2', temp_dir)
        assert r.returncode == 0
        assert r.stderr == 'a\n'
        assert r.stdout == ''

    def test_function_reopen_fd1_to_file_lands(self, temp_dir):
        r = run_psh('exec 1>&-; f(){ echo a; }; f 1>g', temp_dir)
        assert r.returncode == 0
        assert read(os.path.join(temp_dir, 'g')) == 'a\n'

    def test_brace_group_combined_reopen_lands(self, temp_dir):
        run_psh('exec 1>&-; { echo a; } &> f', temp_dir)
        assert read(os.path.join(temp_dir, 'f')) == 'a\n'

    def test_bare_builtin_after_close_still_fails(self, temp_dir):
        # No reopen: fd 1 stays closed, so the write fails (no output).
        r = run_psh('exec >&-; echo x', temp_dir)
        assert r.returncode == 1
        assert r.stdout == ''

    def test_stderr_close_then_compound_reopen_lands(self, temp_dir):
        # fd 2 twin: close stderr, a compound body redirects fd 2 to a file.
        r = run_psh('exec 2>&-; { echo E >&2; } 2>g; echo done', temp_dir)
        assert r.returncode == 0
        assert r.stdout == 'done\n'
        assert read(os.path.join(temp_dir, 'g')) == 'E\n'
