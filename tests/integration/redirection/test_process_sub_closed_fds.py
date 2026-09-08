"""Process substitution with standard descriptors initially closed (Commit 5).

The process-substitution children reused the same unsafe fd recipe that D1/D2/D3
fixed elsewhere:

- The read side <(cmd) did close(parent);dup2(child_stdout,1);close(child_stdout).
  With fd 1 closed (exec 1>&-) os.pipe() could return the write end AS fd 1 and
  the close destroyed the substitution's own stdout; and the parent's read end
  could land on fd 1, so /dev/fd/1 aliased the closed shell stdout and the
  consumer's open failed (EACCES on macOS).
- The write side >(cmd) did dup2(sub_fd,0) then closed sub_fd in a finally;
  with fd 0 closed the open returned fd 0 and the finally closed the
  substitution body's stdin (`cat: stdin: Bad file descriptor`).

Both now wire their endpoints through the collision-safe remap_fds utility (and
both keep the parent's /dev/fd descriptor above fd 2). The redirect
dup/close paths were audited and needed no change — they already validate the
source fd and preserve the target, matching bash apart from the universal
`psh:` vs `bash:` diagnostic prefix.

Subprocess tests: they permanently close the shell's own std fds, so they MUST
NOT run in-process. The substitution's delivery is observed on a fresh high
descriptor (fd 9) written to a file, independent of the closed std fds. Pinned
against the resolve_bash() oracle, executed through the shared typed
runner (hermetic env, own session, file-backed capture, bounded output).

Environment sanity: in some execution environments (a seatbelt sandbox — seen
in the v0.724-era gate as ``/dev/fd/63: Operation not permitted``, while the
same commands pass in a normal session) reopening ``/dev/fd/N`` is refused
outright. BOTH shells are pipe-and-``/dev/fd`` backed, so neither can process
substitute there and no row in this module means anything. The precondition is
therefore probed shell-neutrally, at the syscall (a pipe descriptor reopened
through its own /dev/fd name), and every row skips loudly on it — a broken
environment is a harness failure, never a psh divergence.
"""
import fcntl
import os
import sys
import tempfile
from pathlib import Path

import pytest
from shell_oracle import hermetic_shell_env, is_comparable, resolve_bash, run_shell_case

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV = hermetic_shell_env({'LC_ALL': 'C', 'LANG': 'C',
                          'PYTHONPATH': str(REPO_ROOT)})
BASH = resolve_bash().path


def _dev_fd_reopen_works():
    """True when THIS environment lets a process reopen its own /dev/fd/N.

    Shell-neutral on purpose: probing with bash would let a psh regression hide
    behind a bash failure, and probing with psh would let it hide behind its
    own. Both shells need exactly this syscall to process-substitute.
    """
    read_fd, write_fd = os.pipe()
    try:
        flags = fcntl.fcntl(write_fd, fcntl.F_GETFD)
        fcntl.fcntl(write_fd, fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)
        try:
            probe = os.open(f"/dev/fd/{write_fd}", os.O_WRONLY)
        except OSError:
            return False
        os.close(probe)
        return True
    finally:
        os.close(read_fd)
        os.close(write_fd)


_require_dev_fd_reopen = pytest.mark.skipif(
    not _dev_fd_reopen_works(),
    reason="this environment refuses to reopen /dev/fd/N (sandbox EPERM "
           "class); no shell can process-substitute here")


def _bash_procsub_sane():
    """True when the bash oracle can procsub in THIS execution environment."""
    r = run_shell_case([BASH, "-c", "echo probe > >(cat > /dev/null); wait"],
                       stdin_data="", env=ENV, timeout=20)
    return is_comparable(r) and r.returncode == 0 and not r.stderr


_require_sane_bash_oracle = pytest.mark.skipif(
    not _bash_procsub_sane(),
    reason="bash oracle cannot process-substitute in this environment "
           "(/dev/fd EPERM class) — oracle harness failure, not psh behavior")


def _observe(argv, closures, body):
    """Run `closures; exec 9>FILE; body` and return (stdout, stderr, fd9)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False) as tf:
        path = tf.name
    try:
        script = f'{closures}exec 9>{path}; {body}'
        r = run_shell_case(argv + ["-c", script], stdin_data="",
                           env=ENV, timeout=20)
        assert is_comparable(r), f"harness failure: {r!r}"
        with open(path) as f:
            return r.stdout, r.stderr, f.read()
    finally:
        os.unlink(path)


READ_CASES = [
    ("", 'cat <(printf x) >&9'),
    ("exec 1>&-; ", 'cat <(printf x) >&9'),
    ("exec 0<&-; ", 'cat <(printf x) >&9'),
    ("exec 0<&- 1>&-; ", 'cat <(printf x) >&9'),
    ("exec 0<&- 1>&- 2>&-; ", 'cat <(printf x) >&9'),
]

# Write-side delivery is ASYNCHRONOUS in both shells: neither bash nor
# psh waits for a >(...) child at command end (bash's bare `wait` does reach
# it; psh's does not — recorded as a successor divergence, deliberately not
# exercised here), so fd 9's content at parent exit is a race, and the
# harness's post-exit orphan sweep SIGKILLs a child that has not written yet.
# That race is what the 2026-07-27/-30 Linux nightlies lost: bash's `cat` was
# swept before writing -> ('', '', '') against psh's ('', '', 'data\n'), psh
# winning only by interpreter-teardown latency. The body therefore carries its
# own shell-neutral completion barrier: the substitution touches a flag file
# AFTER writing, and the parent spin-waits (bounded, so a genuine delivery
# regression still fails as a comparison, not a harness timeout) until the
# flag appears. Delivery is then deterministic on both sides before either
# shell exits, and the sweep only ever kills an already-idle child.
_WRITE_BODY = ('echo data > >(cat >&9; : > ps-done); '
               'i=0; until [ -e ps-done ] || [ "$i" -ge 400 ]; '
               'do sleep 0.01; i=$((i+1)); done')

WRITE_CASES = [
    ("", _WRITE_BODY),
    ("exec 0<&-; ", _WRITE_BODY),
    ("exec 1>&-; ", _WRITE_BODY),
    ("exec 0<&- 1>&-; ", _WRITE_BODY),
]


@_require_dev_fd_reopen
@_require_sane_bash_oracle
@pytest.mark.parametrize("closures,body", READ_CASES)
def test_read_side_procsub_closed_fds_matches_bash(closures, body):
    psh = _observe([sys.executable, "-m", "psh"], closures, body)
    bash = _observe([BASH], closures, body)
    assert psh == bash, f"{closures!r}: psh={psh!r} bash={bash!r}"


@_require_dev_fd_reopen
@_require_sane_bash_oracle
@pytest.mark.parametrize("closures,body", WRITE_CASES)
def test_write_side_procsub_closed_fds_matches_bash(closures, body):
    psh = _observe([sys.executable, "-m", "psh"], closures, body)
    bash = _observe([BASH], closures, body)
    assert psh == bash, f"{closures!r}: psh={psh!r} bash={bash!r}"


@_require_dev_fd_reopen
def test_read_side_delivers_with_stdout_closed():
    """exec 1>&-; cat <(printf x) delivers x (was EACCES on /dev/fd/1)."""
    _out, _err, fd9 = _observe([sys.executable, "-m", "psh"],
                               "exec 1>&-; ", 'cat <(printf x) >&9')
    assert fd9 == "x"


@_require_dev_fd_reopen
def test_write_side_delivers_with_stdin_closed():
    """exec 0<&-; echo data > >(cat) delivers data (was Bad file descriptor)."""
    _out, _err, fd9 = _observe([sys.executable, "-m", "psh"],
                               "exec 0<&-; ", _WRITE_BODY)
    assert fd9 == "data\n"
