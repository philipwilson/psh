"""
Conformance tests for `trap` signal-spec normalization.

`trap` accepts a signal as a bare name (`INT`), a `SIG`-prefixed name
(`SIGINT`), or a number (`2`) — all referring to the same signal. Before
v0.487 psh keyed trap handlers by the raw spec, so two everyday idioms broke
(reappraisal #13 HIGH):

  - `trap … SIGINT` was rejected outright ("invalid signal specification");
  - `trap … 2` for a managed signal (INT/TERM/HUP/QUIT) was accepted but
    never fired — the shell died on the default action — because the
    name-keyed signal dispatch never matched the number key.

All three spellings now normalize to one canonical key, so they set, fire,
and query interchangeably. Verified against bash 5.2.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest, find_bash


class TestTrapSignalSpecConformance(ConformanceTest):
    """SIG-prefixed names, bare names, and numbers are interchangeable."""

    def test_sig_prefixed_name_accepted(self):
        self.assert_identical_behavior("trap 'echo x' SIGINT && echo OK")

    def test_sig_prefixed_other_signals(self):
        self.assert_identical_behavior("trap 'echo a' SIGUSR1 && echo OK")
        self.assert_identical_behavior("trap 'echo a' SIGTERM && echo OK")

    def test_invalid_signal_rejected(self):
        # An unknown signal is still rejected (exit 1 from trap) with the same
        # diagnostic — compared by exit code + stderr substring because the
        # bash `line N:` prefix differs from psh's by design.
        cmd = "trap 'echo x' NOTASIGNAL; echo rc=$?"
        psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                             capture_output=True, text=True)
        bash = subprocess.run([find_bash(), '-c', cmd],
                              capture_output=True, text=True)
        assert psh.stdout == bash.stdout == "rc=1\n"
        assert 'invalid signal specification' in psh.stderr
        assert 'invalid signal specification' in bash.stderr


class TestTrapFiresConformance(ConformanceTest):
    """A trap set by name / SIG-name / number all fire on delivery."""

    def test_numbered_managed_signal_fires(self):
        self.assert_identical_behavior(
            "trap 'echo GOT' 2\nkill -2 $$\necho after")

    def test_numbered_term_fires(self):
        self.assert_identical_behavior(
            "trap 'echo T' 15\nkill -15 $$\necho after")

    def test_sig_name_signal_fires(self):
        self.assert_identical_behavior(
            "trap 'echo GOT' SIGINT\nkill -INT $$\necho after")

    def test_bare_name_signal_fires(self):
        self.assert_identical_behavior(
            "trap 'echo GOT' INT\nkill -INT $$\necho after")


class TestTrapQueryConformance(ConformanceTest):
    """`trap -p` finds a trap regardless of how the query names the signal."""

    def test_query_by_sig_prefixed_name(self):
        self.assert_identical_behavior("trap 'echo x' INT; trap -p SIGINT")

    def test_query_by_number(self):
        self.assert_identical_behavior("trap 'echo x' INT; trap -p 2")

    def test_query_by_bare_name(self):
        self.assert_identical_behavior("trap 'echo x' SIGINT; trap -p INT")

    def test_reset_then_query_empty(self):
        self.assert_identical_behavior(
            "trap 'echo x' SIGINT; trap - SIGINT; trap -p SIGINT; echo done")
