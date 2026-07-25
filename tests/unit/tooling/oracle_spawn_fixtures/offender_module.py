"""Synthetic offender for the anti-spawn guard (slot 1.2).

This module is an oracle-bearing module (it imports ``shell_oracle``) that ALSO
creates a process directly — exactly what the guard
``tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py`` forbids. It
lives under ``oracle_spawn_fixtures/``, the ONE directory the guard's scan
deliberately skips, so it does not fail the real guard; a dedicated test feeds
it through the full guard pipeline and asserts it WOULD be flagged, proving the
guard fires (sequence-doc rule 6 / §5.6 mutation check).

It is not a test module (no ``test_`` prefix) and is never imported at runtime.
"""
import subprocess
import sys

from shell_oracle import is_comparable  # makes this module oracle-bearing


def offending_spawn():
    # The offense: a direct process launch the runner should own instead.
    return subprocess.run([sys.executable, "-c", "print('nope')"],
                          capture_output=True, text=True)


def looks_comparable(result):
    # Uses the shell_oracle import so the dependency is genuine, not cosmetic.
    return is_comparable(result)
