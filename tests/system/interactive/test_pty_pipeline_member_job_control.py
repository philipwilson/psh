"""PTY: a pipeline member never does job control of its own (C001, C180).

Job control belongs to the shell process. When a pipeline member forks an
external command — which is what a function body, ``eval`` text or a sourced
file does now that exec-in-place is a one-shot (C001) — that grandchild must
NOT get a process group of its own and the member must NOT hand it the
terminal: the member would then reclaim the terminal with ``tcsetpgrp`` from
a process group that no longer owns it, take SIGTTOU, and stop. At an
interactive prompt that turns a working command into::

    ll(){ /bin/ls /dev/null; }; ll | cat
    /dev/null
    [1]+  Stopped                 ll | cat

with the rest of the body arriving only after ``fg``. These rows are only
reachable with a REAL TERMINAL: without one ``supports_job_control`` is false,
nothing is transferred, and the bug is invisible.

Owner of the rule: ``psh/executor/job_control.py#JobManager.does_job_control``.

The assertions are absolute invariants, not comparisons, so this module drives
psh alone. Each was verified against GNU bash 5.3.15 over the same pexpect PTY
while the pins were written: bash prints ``A``/``B`` with no job notice for
every shape below, and reports ``pgid == tcgetpgrp(0)`` for the shell, a
function-body external, a direct member, a brace-group member and a plain
foreground external — the same values these tests require of psh.
"""

import itertools
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pexpect
import pytest

# Signals and terminal ownership: never alongside xdist siblings. (The
# "test_pty" filename prefix also auto-marks this module in conftest; the
# explicit marker states the intent.)
pytestmark = pytest.mark.serial

PROMPT = 'PSH\\$ '
PSH_ROOT = str(Path(__file__).resolve().parents[3])
OSC = re.compile(r'\x1b\][^\x07]*\x07')  # terminal-title sequences

# Prints the process group this command lands in and the terminal's current
# foreground group. Equal ⇒ the command is in the foreground group, so Ctrl-C
# at the prompt reaches it.
PG_PROBE = (
    "import os\n"
    "print(f'pg={os.getpgrp()} tc={os.tcgetpgrp(0)}')\n"
)


@pytest.fixture(scope="module")
def workdir(tmp_path_factory):
    """A temp dir holding the helper files the rows source and run.

    ``pgsh`` wraps the probe so the typed command stays short: a line that
    wraps the 80-column PTY is echoed with an embedded newline and the echo
    consumption in :func:`run` would not match it.
    """
    d = tmp_path_factory.mktemp("pty-member")
    (d / "pg.py").write_text(PG_PROBE)
    wrapper = d / "pgsh"
    wrapper.write_text(f'#!/bin/sh\nexec {sys.executable} {d}/pg.py\n')
    wrapper.chmod(0o755)
    (d / "sourced.sh").write_text("/bin/echo A; echo B\n")
    return d


def _spawn(workdir):
    """An interactive psh on a real pseudo-terminal, cwd in the temp dir.

    ``cwd`` is pinned as well as ``PYTHONPATH``: ``-m psh`` resolves the
    current directory FIRST, so without this the child would import whichever
    tree the test runner happens to be sitting in.
    """
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': str(workdir),
        'TERM': 'xterm',
        'PS1': 'PSH$ ',
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': PSH_ROOT,
    }
    child = pexpect.spawn(
        sys.executable, ['-u', '-m', 'psh', '--norc', '--force-interactive'],
        timeout=20, encoding='utf-8', env=env, cwd=str(workdir))
    child.send('\r')
    child.expect(PROMPT)
    return child


@pytest.fixture
def psh(workdir):
    """A session of its OWN for every row.

    Deliberately not shared: a row that leaves a stopped job behind — exactly
    what these pins exist to catch — would otherwise perturb the next row and
    blur which shape actually regressed. A spawn is ~0.3s; the whole module
    stays well under ten seconds.
    """
    child = _spawn(workdir)
    yield child
    child.close(force=True)


def run(child, cmd):
    """Type *cmd*, consume its terminal echo, and return its output lines.

    The echo is consumed explicitly (``expect_exact``) so the returned lines
    are the command's own output and any job notice — not the previous
    command's tail. Keep commands short: a line that wraps the 80-column PTY
    is echoed with an embedded newline and would not match.
    """
    child.send(cmd + '\r')
    child.expect_exact(cmd)
    child.expect(PROMPT)
    text = OSC.sub('', child.before).replace('\r', '')
    return [ln for ln in text.split('\n') if ln.strip()]


# (id, command, expected output lines) — every shape that reaches an external
# command from inside a pipeline member, plus the controls.
SHAPES = [
    ("function_body_external", 'f(){ /bin/echo A; echo B; }; f | cat', ['A', 'B']),
    ("ll_shape", 'll(){ /bin/ls /dev/null; }; ll | cat', ['/dev/null']),
    ("eval_member", 'echo x | eval "/bin/echo A; echo B"', ['A', 'B']),
    ("source_member", 'echo x | . ./sourced.sh', ['A', 'B']),
    ("nested_function", 'g(){ /bin/echo A; }; f(){ g; echo B; }; f | cat', ['A', 'B']),
    # C180's common shapes, which the same rule closes.
    ("brace_member", '{ /bin/echo A; echo B; } | cat', ['A', 'B']),
    ("for_member", 'for i in 1; do /bin/echo A; echo B; done | cat', ['A', 'B']),
    ("subshell_member", '( /bin/echo A; echo B ) | cat', ['A', 'B']),
    # Controls: shapes that never forked a grandchild.
    ("builtins_only", 'g(){ echo A; echo B; }; g | cat', ['A', 'B']),
    ("plain_external_member", '/bin/echo A | cat', ['A']),
    ("toplevel_external", '/bin/echo A', ['A']),
]


@pytest.mark.parametrize("cmd,expected",
                         [(c, e) for _, c, e in SHAPES],
                         ids=[i for i, _, _ in SHAPES])
def test_pipeline_member_is_not_stopped(psh, cmd, expected):
    """The whole pipeline runs to completion, with no job-control notice.

    A SIGTTOU stop shows up two ways and both are asserted: the shell prints
    `[N]+ Stopped ...`, and the body's later commands are missing until `fg`.
    """
    lines = run(psh, cmd)
    assert not any('Stopped' in ln for ln in lines), (
        f"{cmd!r} was stopped by the shell: {lines}")
    assert lines == expected, f"{cmd!r} produced {lines}, expected {expected}"


def test_stopped_member_would_also_lose_its_later_output(psh):
    """The `fg`-recovers-B symptom specifically (C001+C180 together).

    Pinned as its own row because the regression this closes was visible as
    "B only arrives after fg" even when a reader ignored the job notice.
    """
    lines = run(psh, 'f(){ /bin/echo A; echo B; }; f | cat')
    assert lines == ['A', 'B'], lines
    # Nothing is left behind in the job table to resume.
    assert run(psh, 'jobs') == [], "a completed pipeline left a job behind"


def test_member_body_external_runs_in_the_terminal_foreground_group(psh):
    """The grandchild INHERITS the member's group (bash 5.3.15 agrees).

    `pg == tc` means the command sits in the terminal's foreground process
    group, so Ctrl-C at the prompt reaches it. A group of its own would also
    be the group the member then wrongly tried to reclaim the terminal from.
    """
    for label, cmd in (
        ("shell", './pgsh'),
        ("function body", 'f(){ ./pgsh; }; f | cat'),
        ("direct member", './pgsh | cat'),
        ("brace member", '{ ./pgsh; } | cat'),
        ("foreground external", './pgsh'),
    ):
        lines = run(psh, cmd)
        assert len(lines) == 1, f"{label}: {lines}"
        pg, tc = lines[0].split()
        assert pg.split('=')[1] == tc.split('=')[1], (
            f"{label}: {lines[0]} — the command is not in the terminal's "
            f"foreground process group")


def test_job_control_itself_still_works(psh):
    """Control: backgrounding, `jobs` and `fg` are unaffected by the rule."""
    started = run(psh, '/bin/sleep 0.3 &')
    assert started and started[0].startswith('[1]'), started
    assert any('sleep' in ln for ln in run(psh, 'jobs'))
    assert any('sleep' in ln for ln in run(psh, 'fg'))
    assert run(psh, 'jobs') == []


def test_set_m_pipeline_member_completes(psh):
    """`set -m` does not reintroduce the nested session (C001, C180)."""
    run(psh, 'set -m')
    assert run(psh, 'f(){ /bin/echo A; echo B; }; f | cat') == ['A', 'B']
    run(psh, 'set +m')
    assert run(psh, 'f | cat') == ['A', 'B']


# ---------------------------------------------------------------------------
# Interactive Ctrl-C must reach a pipeline NESTED inside a forked child.
#
# The same rule, other half: a forked child forms no process group for what it
# runs, so a nested pipeline stays inside the terminal's foreground group and
# the interrupt reaches it. When only the standalone role was gated, a nested
# pipeline still called setpgid(0,0) while the terminal handoff was (correctly)
# suppressed — so Ctrl-C reached nothing and the processes leaked as live
# orphans that `jobs` did not even list:
#
#     ( /bin/sleep 5 | /bin/cat )     # ^C -> bash kills; psh leaked both
# ---------------------------------------------------------------------------

# Each row gets a unique sleep duration so `pgrep -f` can identify ITS OWN
# processes and nothing else on the machine. Both stages carry the token, so
# one pattern finds either survivor.
_TOKENS = itertools.count(98701)


def _survivors(token):
    """PIDs of this row's still-live pipeline processes."""
    r = subprocess.run(['pgrep', '-f', str(token)],
                       capture_output=True, text=True)
    return [pid for pid in r.stdout.split() if pid]


def _sweep(token):
    for pid in _survivors(token):
        subprocess.run(['kill', '-9', pid], capture_output=True)


def _describe(token):
    """`ps` detail for whatever still matches, for the failure message.

    A process that has already exited but is not yet reaped still matches
    `pgrep`; the state column (Z) is what tells a leak from a zombie.
    """
    rows = []
    for pid in _survivors(token):
        r = subprocess.run(['ps', '-o', 'pid=,pgid=,ppid=,state=,command=', '-p', pid],
                           capture_output=True, text=True)
        rows.append(r.stdout.strip() or f"{pid} <gone>")
    return rows


def _wait_for(predicate, timeout=5.0):
    """Poll *predicate* until true or the deadline passes; return its value."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return predicate()


@pytest.fixture
def token():
    """A unique marker for one row's processes, always swept afterwards."""
    tok = next(_TOKENS)
    yield tok
    _sweep(tok)


LEAK_SHAPES = [
    # The REGRESSION guard: a top-level shape, correct in bash and at base,
    # that leaked once the terminal handoff was suppressed without gating the
    # pipeline roles.
    ("subshell_pipeline", '( /bin/sleep {t} | /usr/bin/grep {t} )'),
    ("function_member_nested_pipeline",
     'f(){{ /bin/sleep {t} | /usr/bin/grep {t}; }}; f | cat'),
    ("brace_member_nested_pipeline",
     '{{ /bin/sleep {t} | /usr/bin/grep {t}; }} | cat'),
]


@pytest.mark.parametrize("shape", [s for _, s in LEAK_SHAPES],
                         ids=[i for i, _ in LEAK_SHAPES])
def test_ctrl_c_reaches_a_pipeline_nested_in_a_forked_child(psh, token, shape):
    """Ctrl-C kills every process; nothing is orphaned and `jobs` agrees."""
    cmd = shape.format(t=token)
    psh.send(cmd + '\r')
    psh.expect_exact(cmd)
    assert _wait_for(lambda: _survivors(token)), (
        f"{cmd!r} never started its pipeline")

    psh.sendintr()
    psh.expect(PROMPT)

    _wait_for(lambda: not _survivors(token))
    assert _survivors(token) == [], (
        f"{cmd!r} leaked live processes past Ctrl-C: {_describe(token)} — "
        f"a pipeline nested in a forked child must stay in the terminal's "
        f"foreground process group")
    assert run(psh, 'jobs') == [], "the shell still lists a job for it"


def test_ctrl_c_does_not_kill_a_background_pipeline(psh, token):
    """Control: `&` puts the pipeline OUT of the foreground group, so the
    interrupt must not touch it — the gating must not over-reach."""
    cmd = '/bin/sleep {t} | /usr/bin/grep {t} &'.format(t=token)
    psh.send(cmd + '\r')
    psh.expect(PROMPT)
    assert _wait_for(lambda: _survivors(token)), "background pipeline not started"

    psh.sendintr()
    time.sleep(0.5)
    assert _survivors(token), (
        "Ctrl-C killed a BACKGROUND pipeline; only the foreground group may "
        "receive the interrupt")
