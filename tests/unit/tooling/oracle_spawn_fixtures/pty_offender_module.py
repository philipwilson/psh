"""Synthetic PTY offender for the anti-spawn guard's PTY face (slot 1.2, r3).

An oracle-bearing module (it imports ``shell_oracle``) that creates a process
via ``pexpect.spawn`` — the NON-subprocess family the original subprocess-only
detector could not see, and which let a real PTY bash-differential sit inside
the bearing set unclassified.

It lives in ``oracle_spawn_fixtures/`` (the one directory the guard's scan
skips), so it does not fail the real guard; a dedicated test feeds it through
``find_non_subprocess_spawns`` and asserts it WOULD be flagged, proving the PTY
face fires (sequence-doc §5.6 mutation check).

Not a test module (no ``test_`` prefix); never imported at runtime — the
``pexpect`` import is deliberately unguarded because nothing executes this file.
"""
import pexpect  # noqa: F401  (never executed; the guard reads this statically)
from shell_oracle import is_comparable  # makes this module oracle-bearing


def offending_pty_spawn():
    # The offense: a PTY process launch the runner/PTY harness should own.
    return pexpect.spawn("/bin/sh", ["-c", "echo nope"], encoding="utf-8")


def looks_comparable(result):
    # Uses the shell_oracle import so the dependency is genuine, not cosmetic.
    return is_comparable(result)
