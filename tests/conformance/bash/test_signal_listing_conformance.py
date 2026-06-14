"""Conformance tests for `kill -l` and `trap -l` signal listings (bash).

Pins the M4/M5 fix (2026-06-14, reappraisal #7): a single source of truth for
signal name<->number (psh.utils.signal_utils, built from signal.Signals) drives
both listings, so they are byte-identical to bash and to each other.

  M4 — `kill -l SIGSPEC`:
        a NUMBER prints the signal NAME (no SIG prefix); a NAME (with or
        without SIG prefix) prints the NUMBER; a NUMBER > 128 prints the name
        for N-128 (the exit-status convention).
  M5 — `kill -l` / `trap -l` with no argument list ALL real signals as
        ``NUM) SIGNAME`` in bash's column layout (no pseudo-signals), and the
        two listings are identical.

All expectations are checked against the live bash via assert_identical_behavior
so they self-adjust to the platform (signal numbers like SIGINFO=29, SIGEMT=7
are BSD-specific on macOS; Linux differs).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestSignalListing(ConformanceTest):
    """kill -l / trap -l match bash byte-for-byte and each other."""

    # --- M5: full listing (no argument) ---------------------------------

    def test_kill_l_full_listing(self):
        """`kill -l` lists all signals in bash's column layout."""
        self.assert_identical_behavior("kill -l")

    def test_trap_l_full_listing(self):
        """`trap -l` is identical to `kill -l` (no pseudo-signals)."""
        self.assert_identical_behavior("trap -l")

    def test_kill_l_equals_trap_l(self):
        """The two listings are byte-identical (single source of truth)."""
        self.assert_identical_behavior("diff <(kill -l) <(trap -l) && echo SAME")

    # --- M4: number -> name ---------------------------------------------

    def test_kill_l_number_9_is_name(self):
        """`kill -l 9` prints the NAME (KILL), not an error."""
        self.assert_identical_behavior("kill -l 9")

    def test_kill_l_number_15_is_name(self):
        """`kill -l 15` prints TERM."""
        self.assert_identical_behavior("kill -l 15")

    # --- M4: name -> number ---------------------------------------------

    def test_kill_l_name_kill_is_number(self):
        """`kill -l KILL` prints the NUMBER."""
        self.assert_identical_behavior("kill -l KILL")

    def test_kill_l_signame_is_number(self):
        """`kill -l SIGKILL` (with SIG prefix) prints the NUMBER."""
        self.assert_identical_behavior("kill -l SIGKILL")

    def test_kill_l_name_term_is_number(self):
        """`kill -l TERM` prints 15."""
        self.assert_identical_behavior("kill -l TERM")

    # --- M4: exit-status convention (N > 128) ---------------------------

    def test_kill_l_137_is_signal_name(self):
        """`kill -l 137` (= 9 + 128) prints KILL."""
        self.assert_identical_behavior("kill -l 137")

    def test_kill_l_143_is_signal_name(self):
        """`kill -l 143` (= 15 + 128) prints TERM."""
        self.assert_identical_behavior("kill -l 143")

    # --- M4: error cases -------------------------------------------------
    #
    # stdout and exit code match bash exactly; only the stderr diagnostic
    # PREFIX differs (psh "kill:" vs bash's "<path>: line N: kill:"), which is
    # the universal program-name banner difference. So these compare exit code
    # and the shared message tail rather than full stderr.

    def _assert_invalid_spec(self, spec: str):
        import subprocess
        cmd = f"kill -l {spec}"
        psh = subprocess.run(
            [sys.executable, "-m", "psh", "-c", cmd],
            capture_output=True, text=True)
        bash = subprocess.run(
            ["bash", "-c", cmd], capture_output=True, text=True)
        assert psh.returncode == bash.returncode == 1
        assert psh.stdout == bash.stdout == ""
        msg = f"{spec}: invalid signal specification"
        assert msg in psh.stderr
        assert msg in bash.stderr

    def test_kill_l_invalid_number(self):
        """An out-of-range number is an invalid signal specification."""
        self._assert_invalid_spec("999")

    def test_kill_l_invalid_name(self):
        """An unknown name is an invalid signal specification."""
        self._assert_invalid_spec("BOGUS")
