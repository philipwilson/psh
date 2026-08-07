"""``read -N`` honors ``-t`` at a REAL terminal (slot 4B.2, the A5 rider's TTY arm).

``_read_exact`` has two arms, and the rider fix threaded the deadline through
BOTH. The non-tty arm is pinned exhaustively in
``tests/unit/builtins/test_read_exact_timeout_4b2.py``; those cells cannot reach
this one, because the tty arm additionally enters raw mode and echoes each
character. This file is that arm's evidence.

Red at base 21a23a4c: with stdin a pseudo-terminal, ``read -t 1 -N 3 x`` IGNORED
the deadline and blocked — measured HUNG past an 8s bound (8x the deadline) with
and without partial input typed, while bash returned 142 at ~1.1s in both. At
the fixed tip both cells match bash. The third cell is the CONTROL: a count
satisfied before the deadline was already correct at base and must stay so.

Why ``-c`` rather than a driven REPL: ``read`` takes its tty branch whenever
stdin is a terminal, so a ``-c`` script under a pty exercises the raw-mode path
directly. That keeps each cell a single deterministic spawn with no prompt
synchronisation — the neighbours here drive a REPL because their subjects are
REPL behaviours; this one is not.

**psh-only by construction.** bash's numbers for these same cells are recorded by
this slot's own instrument ``tmp/w4b2/i11_pty_rider.py`` (which drives both
shells and is where the base-vs-tip comparison above comes from). Keeping the
pin psh-only avoids importing ``shell_oracle`` here, which would make the module
oracle-bearing and put a ``pexpect.spawn`` differential into the frozen
PTY_REGISTRY — a scope this slot has no mandate to widen.

Conventions follow the neighbouring PTY files: hermetic env, ``PYTHONPATH`` AND
``cwd`` both pinned to this tree, bounded spawn timeout. Auto-marked ``serial``
by the ``test_pty`` path marker in ``tests/conftest.py`` and admitted to that
file's run-by-default PTY allowlist — an opt-in pin for a terminal-only fact is
a pin that never runs.
"""
import os
import sys
from pathlib import Path

import pexpect
import pytest

PSH_ROOT = str(Path(__file__).parent.parent.parent.parent)

DEADLINE = 1.0        # the -t deadline under test
HANG_BOUND = 8.0      # 8x the deadline: past this the deadline was ignored

_REPORT = r"""rc=$?; printf 'RC=%s VAL=[%s]\n' "$rc" "$x" """
SCRIPT = f"read -t {DEADLINE} -N 3 x; {_REPORT}"


def _env():
    return {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': os.environ.get('HOME', '/tmp'),
        'TERM': 'xterm',
        'LC_ALL': 'en_US.UTF-8',
        'LANG': 'en_US.UTF-8',
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': PSH_ROOT,
    }


def _read_at_a_tty(typed=None):
    """Run SCRIPT with stdin on a pty; return ``(rc, value)``.

    ``cwd`` is pinned to ``PSH_ROOT`` as well as ``PYTHONPATH``: ``python -m``
    prepends the child's CWD to ``sys.path``, where it OUTRANKS ``PYTHONPATH``,
    so a probe that sets only the latter can silently measure a different tree.
    """
    child = pexpect.spawn(
        sys.executable, ['-u', '-m', 'psh', '--norc', '-c', SCRIPT],
        timeout=HANG_BOUND, encoding='utf-8', env=_env(), cwd=PSH_ROOT)
    try:
        if typed is not None:
            # The deadline is armed by the read itself; type only after it is
            # running so the cell measures the deadline and not the spawn.
            child.expect(pexpect.TIMEOUT, timeout=0.2)
            child.send(typed)
        try:
            child.expect(r'RC=(\d+) VAL=\[([^\]]*)\]')
        except pexpect.TIMEOUT:
            pytest.fail(
                f"read -t {DEADLINE} -N 3 did not return within {HANG_BOUND}s at "
                f"a terminal: the deadline was ignored on the tty arm "
                f"(base behaviour). Buffer so far: {child.before!r}")
        return int(child.match.group(1)), child.match.group(2)
    finally:
        child.close(force=True)


def test_exact_count_honors_the_deadline_at_a_tty():
    """RED AT BASE (hung >8s): nothing typed, so only the deadline can end it."""
    rc, value = _read_at_a_tty()
    assert (rc, value) == (142, ""), f"got rc={rc} value={value!r}"


def test_exact_count_assigns_the_partial_at_a_tty():
    """RED AT BASE (hung >8s): the partial typed before the deadline is kept."""
    rc, value = _read_at_a_tty(typed="ab")
    assert (rc, value) == (142, "ab"), f"got rc={rc} value={value!r}"


def test_full_count_before_the_deadline_at_a_tty():
    """CONTROL, green at base: the count is satisfied, so no deadline applies."""
    rc, value = _read_at_a_tty(typed="abc")
    assert (rc, value) == (0, "abc"), f"got rc={rc} value={value!r}"
