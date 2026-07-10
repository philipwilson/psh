"""read builtin error-message wording, pinned to bash 5.2.

Reappraisal #17 io cross-finding: reading after `exec 0<&-` printed the raw
Python OSError repr ("read: [Errno 9] Bad file descriptor"); bash prints
"read: read error: 0: Bad file descriptor". Similarly `read -u BADFD` now
includes the strerror tail ("read: 9: invalid file descriptor: Bad file
descriptor").

Subprocess tests: `exec 0<&-` is a PERMANENT fd change — in-process it would
close the test runner's own stdin (see parallel-safety rules in CLAUDE.md).
"""

import subprocess
import sys


def _run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=15)


class TestReadErrorMessages:
    def test_read_after_closed_stdin(self):
        result = _run_psh('exec 0<&-; read x; echo rc=$?')
        assert result.stdout == 'rc=1\n'
        assert result.stderr.strip() == \
            'psh: line 1: read: read error: 0: Bad file descriptor'

    def test_read_r_after_closed_stdin(self):
        result = _run_psh('exec 0<&-; read -r a b; echo rc=$?')
        assert result.stdout == 'rc=1\n'
        assert result.stderr.strip() == \
            'psh: line 1: read: read error: 0: Bad file descriptor'

    def test_read_u_bad_fd_includes_strerror(self):
        result = _run_psh('read -u 9 x; echo rc=$?')
        assert result.stdout == 'rc=1\n'
        assert result.stderr.strip() == \
            'psh: line 1: read: 9: invalid file descriptor: Bad file descriptor'

    def test_no_raw_oserror_repr(self):
        for cmd in ('exec 0<&-; read x', 'read -u 9 x'):
            result = _run_psh(cmd)
            assert '[Errno' not in result.stderr, (cmd, result.stderr)
