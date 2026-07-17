"""Process substitution with standard descriptors initially closed (Commit 5).

The process-substitution children reused the same unsafe fd recipe that D1/D2/D3
fixed elsewhere:

- The read side <(cmd) did close(parent);dup2(child_stdout,1);close(child_stdout).
  With fd 1 closed (exec 1>&-) os.pipe() could return the write end AS fd 1 and
  the close destroyed the substitution's own stdout; and the parent's read end
  could land on fd 1, so /dev/fd/1 aliased the closed shell stdout and the
  consumer's open failed (EACCES on macOS).
- The write side >(cmd) did dup2(fifo_fd,0) then closed fifo_fd in a finally;
  with fd 0 closed the FIFO open returned fd 0 and the finally closed the
  substitution body's stdin (`cat: stdin: Bad file descriptor`).

Both now wire their endpoints through the collision-safe remap_fds utility (and
the read side keeps the parent's /dev/fd descriptor above fd 2). The redirect
dup/close paths were audited and needed no change — they already validate the
source fd and preserve the target, matching bash apart from the universal
`psh:` vs `bash:` diagnostic prefix.

Subprocess tests: they permanently close the shell's own std fds, so they MUST
NOT run in-process. The substitution's delivery is observed on a fresh high
descriptor (fd 9) written to a file, independent of the closed std fds. Pinned
against the resolve_bash() oracle (5.2), executed through the shared typed
runner (hermetic env, own session, file-backed capture, bounded output).

Oracle sanity: on macOS, bash's own ``/dev/fd/N`` open for a procsub pipe can
fail with EPERM in some execution environments (observed in the v0.724-era
gate: ``/dev/fd/63: Operation not permitted`` on every write-side case, while
the same commands pass in a normal session — psh itself is immune, it uses
FIFOs). A bash that cannot process-substitute AT ALL in this environment is a
broken ORACLE, not a psh divergence, so the bash-comparison tests skip loudly
instead of comparing against its failure (typed-harness principle: a harness
failure never enters a behavior comparison).
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest
from shell_oracle import Completed, hermetic_shell_env, resolve_bash, run_shell_case

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV = hermetic_shell_env({'LC_ALL': 'C', 'LANG': 'C',
                          'PYTHONPATH': str(REPO_ROOT)})
BASH = resolve_bash().path


def _bash_procsub_sane():
    """True when the bash oracle can procsub in THIS execution environment."""
    r = run_shell_case([BASH, "-c", "echo probe > >(cat > /dev/null); wait"],
                       stdin_data="", env=ENV, timeout=20)
    return isinstance(r, Completed) and r.returncode == 0 and not r.stderr


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
        assert isinstance(r, Completed), f"harness failure: {r!r}"
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

WRITE_CASES = [
    ("", 'echo data > >(cat >&9)'),
    ("exec 0<&-; ", 'echo data > >(cat >&9)'),
    ("exec 1>&-; ", 'echo data > >(cat >&9)'),
    ("exec 0<&- 1>&-; ", 'echo data > >(cat >&9)'),
]


@_require_sane_bash_oracle
@pytest.mark.parametrize("closures,body", READ_CASES)
def test_read_side_procsub_closed_fds_matches_bash(closures, body):
    psh = _observe([sys.executable, "-m", "psh"], closures, body)
    bash = _observe([BASH], closures, body)
    assert psh == bash, f"{closures!r}: psh={psh!r} bash={bash!r}"


@_require_sane_bash_oracle
@pytest.mark.parametrize("closures,body", WRITE_CASES)
def test_write_side_procsub_closed_fds_matches_bash(closures, body):
    psh = _observe([sys.executable, "-m", "psh"], closures, body)
    bash = _observe([BASH], closures, body)
    assert psh == bash, f"{closures!r}: psh={psh!r} bash={bash!r}"


def test_read_side_delivers_with_stdout_closed():
    """exec 1>&-; cat <(printf x) delivers x (was EACCES on /dev/fd/1)."""
    _out, _err, fd9 = _observe([sys.executable, "-m", "psh"],
                               "exec 1>&-; ", 'cat <(printf x) >&9')
    assert fd9 == "x"


def test_write_side_delivers_with_stdin_closed():
    """exec 0<&-; echo data > >(cat) delivers data (was Bad file descriptor)."""
    _out, _err, fd9 = _observe([sys.executable, "-m", "psh"],
                               "exec 0<&-; ", 'echo data > >(cat >&9)')
    assert fd9 == "data\n"
