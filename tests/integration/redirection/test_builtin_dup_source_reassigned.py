"""A builtin's dup source fd may be reassigned by a LATER redirect.

Reappraisal #16, H1 (a regression from the v0.576 Cluster C commit) and its
`exec 1>&-` executor sibling.

`echo hi 1>&2 2>err` must send "hi" to the terminal's stderr (the OLD target
of fd 2), NOT into `err`: `1>&2` makes fd 1 a snapshot of fd 2's *current*
target, so the later `2>err` reassigns fd 2 without disturbing fd 1. The
regression aliased the `sys.stdout`/`sys.stderr` STREAM OBJECT (still backed by
real fd 2), which the later `2>err` clobbered out from under it, so the
builtin's own output landed in `err`.

The C-cluster's own pinning test used `echo out 2>&1 1>/dev/null`, where echo
writes only to stdout, so it never exercised the misrouting. These pins VARY
WHICH FD THE COMMAND WRITES TO — including a builtin that writes to BOTH
streams (`type name nosuch`).

Runs psh in a subprocess (process-level fd state). The
`integration/redirection` path is auto-marked `serial`. Expectations verified
against bash 5.2.
"""

import subprocess
import sys


def run_psh(cmd, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, cwd=cwd, timeout=15)


class TestDupSourceReassigned:
    """`n>&m` then `m>file`: fd n keeps m's OLD target (H1)."""

    def test_stdout_dup_then_stderr_reassigned(self, tmp_path):
        """`echo hi 1>&2 2>err`: hi on the real stderr, err empty."""
        psh = run_psh('echo hi 1>&2 2>err', cwd=tmp_path)
        assert psh.stderr == 'hi\n'
        assert psh.stdout == ''
        assert (tmp_path / 'err').read_text() == ''

    def test_printf_dup_then_stderr_reassigned(self, tmp_path):
        psh = run_psh('printf p 1>&2 2>err', cwd=tmp_path)
        assert psh.stderr == 'p'
        assert (tmp_path / 'err').read_text() == ''

    def test_dup_stderr_via_amp_then_reassigned(self, tmp_path):
        """`echo E >&2 2>err`: >&2 aliases fd 1 to fd 2's old target."""
        psh = run_psh('echo E >&2 2>err', cwd=tmp_path)
        assert psh.stderr == 'E\n'
        assert (tmp_path / 'err').read_text() == ''

    def test_swap_idiom_on_bare_builtin(self, tmp_path):
        """The documented `3>&1 1>&2 2>&3 3>&-` swap on a bare builtin sends
        echo's output to stderr (docs/user_guide/09_io_redirection.md:478)."""
        psh = run_psh('echo hi 3>&1 1>&2 2>&3 3>&-', cwd=tmp_path)
        assert psh.stderr == 'hi\n'
        assert psh.stdout == ''

    def test_builtin_writes_both_streams_routing(self, tmp_path):
        """The dimension the C-cluster pin missed: a builtin writing to BOTH
        stdout and stderr under a reassigning dup.

        `type echo nosuch 2>&1 1>/dev/null`: `2>&1` makes fd 2 a snapshot of
        fd 1, then `1>/dev/null` reassigns fd 1. `type echo` (stdout) is
        discarded to /dev/null; the `type nosuch` error (stderr) follows fd 2
        to the ORIGINAL stdout. The regression sent the stderr write into
        /dev/null (aliased stream on the clobbered fd 1), silently losing it.
        Assert on ROUTING, not psh's exact message wording.
        """
        psh = run_psh('type echo nosuch_zz 2>&1 1>/dev/null', cwd=tmp_path)
        assert 'nosuch_zz' in psh.stdout          # error routed to stdout
        assert 'not found' in psh.stdout
        assert psh.stderr == ''                    # nothing on the real stderr
        assert 'echo' not in psh.stdout            # the stdout line was /dev/null'd

    def test_stdout_write_survives_dup_reassign(self, tmp_path):
        """`echo out 2>&1 1>f`: echo writes stdout, which now points at f."""
        run_psh('echo out 2>&1 1>f', cwd=tmp_path)
        assert (tmp_path / 'f').read_text() == 'out\n'


class TestExecClosedFdThenBuiltin:
    """`exec 1>&-` then a builtin: fd 1 stays closed (executor sibling)."""

    def test_exec_close_then_stderr_redirect_no_leak(self, tmp_path):
        """`exec 1>&-; echo X 2>g`: fd 1 stays closed, so echo's write fails
        with EBADF; the write-error diagnostic follows fd 2 into g. The
        regression let the `2>g` open() reallocate the freed fd 1, so the
        stale sys.stdout wrapper wrote X into g with rc 0."""
        psh = run_psh('exec 1>&-; echo X 2>g', cwd=tmp_path)
        assert psh.returncode == 1
        g = (tmp_path / 'g').read_text()
        assert 'write error' in g
        assert 'X' not in g                        # stdout did NOT leak into g

    def test_exec_close_then_high_fd_redirect_no_leak(self, tmp_path):
        """`exec 1>&-; echo X 5>g`: fd >= 3 target already closed cleanly."""
        psh = run_psh('exec 1>&-; echo X 5>g', cwd=tmp_path)
        assert psh.returncode == 1
        assert 'write error' in psh.stderr
        assert (tmp_path / 'g').read_text() == ''

    def test_exec_close_then_reopen_fd1_still_works(self, tmp_path):
        """`exec 1>&-; echo a > f`: a redirect that REOPENS fd 1 must make the
        builtin's output reach the file (bash: f == 'a'). Guards against
        over-severing the stream on the permanent close."""
        run_psh('exec 1>&-; echo a > f', cwd=tmp_path)
        assert (tmp_path / 'f').read_text() == 'a\n'

    def test_exec_close_then_combined_reopen_still_works(self, tmp_path):
        """`exec 1>&-; { echo a; } &> f`: the compound reopens fd 1 via &>;
        the inner builtin's output must reach f."""
        run_psh('exec 1>&-; { echo a; } &> f', cwd=tmp_path)
        assert (tmp_path / 'f').read_text() == 'a\n'

    def test_exec_close_stderr_then_stdout_redirect(self, tmp_path):
        """`exec 2>&-; echo X 1>g`: fd 1 open, fd 2 closed; X reaches g."""
        psh = run_psh('exec 2>&-; echo X 1>g', cwd=tmp_path)
        assert psh.returncode == 0
        assert (tmp_path / 'g').read_text() == 'X\n'
