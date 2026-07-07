"""
Conformance tests for settable computed special variables (SECONDS, RANDOM).

Both are computed on read, but assignment is honored (bash):
  - SECONDS=N resets the elapsed-time baseline.
  - RANDOM=N seeds bash's Park-Miller minimal-standard generator; psh
    reproduces bash 5.x's sequence value-for-value, so the seeded
    sequences can be matched exactly.

Verified against bash 5.2.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestSecondsAssignmentConformance(ConformanceTest):
    """SECONDS assignment baseline behavior (immediate, deterministic cases)."""

    def test_assignment_immediate(self):
        # Right after assignment ~no time has elapsed -> exactly N.
        self.assert_identical_behavior('SECONDS=100; echo $SECONDS')
        self.assert_identical_behavior('SECONDS=0; echo $SECONDS')

    def test_noninteger_assignment_is_zero(self):
        self.assert_identical_behavior('SECONDS=abc; echo $SECONDS')
        self.assert_identical_behavior('SECONDS=5xy; echo $SECONDS')
        self.assert_identical_behavior('SECONDS=0x10; echo $SECONDS')

    def test_negative_assignment(self):
        self.assert_identical_behavior('SECONDS=-5; echo $SECONDS')

    def test_arithmetic_assignment(self):
        self.assert_identical_behavior('SECONDS=$((2+3)); echo $SECONDS')
        self.assert_identical_behavior('(( SECONDS = 50 )); echo $SECONDS')

    def test_unset_makes_ordinary_variable(self):
        self.assert_identical_behavior(
            'unset SECONDS; SECONDS=foo; echo "[$SECONDS]"')
        self.assert_identical_behavior('unset SECONDS; echo "[$SECONDS]"')


class TestRandomSeedConformance(ConformanceTest):
    """RANDOM seeding reproduces bash's exact sequence for a given seed."""

    def test_seeded_sequences_match_bash(self):
        self.assert_identical_behavior('RANDOM=1; echo $RANDOM $RANDOM $RANDOM')
        self.assert_identical_behavior('RANDOM=42; echo $RANDOM $RANDOM $RANDOM')
        self.assert_identical_behavior('RANDOM=0; echo $RANDOM $RANDOM $RANDOM')
        self.assert_identical_behavior('RANDOM=123; echo $RANDOM $RANDOM')

    def test_noninteger_seed_matches_zero(self):
        self.assert_identical_behavior('RANDOM=abc; echo $RANDOM $RANDOM')

    def test_arithmetic_seed(self):
        self.assert_identical_behavior('RANDOM=$((40+2)); echo $RANDOM')
        self.assert_identical_behavior('(( RANDOM = 1 )); echo $RANDOM $RANDOM')

    def test_unset_makes_ordinary_variable(self):
        self.assert_identical_behavior(
            'unset RANDOM; RANDOM=hi; echo "[$RANDOM]"')


class TestSpecialUnsetDeactivationConformance(ConformanceTest):
    """`unset` deactivates EVERY dynamic special (appraisal H1), not just
    SECONDS/RANDOM: a later assignment then stores the literal string."""

    def test_unset_epochseconds_then_assign(self):
        self.assert_identical_behavior(
            'unset EPOCHSECONDS; EPOCHSECONDS=hello; echo "[$EPOCHSECONDS]"')

    def test_unset_epochrealtime_then_assign(self):
        self.assert_identical_behavior(
            'unset EPOCHREALTIME; EPOCHREALTIME=hello; echo "[$EPOCHREALTIME]"')

    def test_unset_lineno_then_assign(self):
        self.assert_identical_behavior(
            'unset LINENO; LINENO=hello; echo "[$LINENO]"')

    def test_unset_bashpid_then_assign(self):
        self.assert_identical_behavior(
            'unset BASHPID; BASHPID=hello; echo "[$BASHPID]"')


class TestSpecialExportMaterializationConformance(ConformanceTest):
    """`export`-ing a computed special materialises a SNAPSHOT of its value
    into the environment (appraisal H1)."""

    def test_export_seconds_with_value_snapshots(self):
        # export SECONDS=100 seeds the baseline AND snapshots 100 into the env
        # a child sees.
        self.assert_identical_behavior(
            'export SECONDS=100; printenv SECONDS')

    def test_export_random_visible_to_child(self):
        # The exact value is unpredictable, but a child must find SOME value.
        self.assert_identical_behavior(
            'export RANDOM; printenv RANDOM >/dev/null; echo "rc=$?"')

    def test_export_then_export_n_removes_entry(self):
        self.assert_identical_behavior(
            'export EPOCHSECONDS; export -n EPOCHSECONDS; '
            'printenv EPOCHSECONDS >/dev/null; echo "rc=$?"')


class TestSpecialDeclarePConformance(ConformanceTest):
    """`declare -p NAME` lists a computed special with its attributes
    (appraisal H1). The value is stripped so the comparison is deterministic
    despite RANDOM / clock values differing between the shells."""

    def test_declare_p_random_integer(self):
        self.assert_identical_behavior("declare -p RANDOM | sed 's/=.*//'")

    def test_declare_p_seconds_integer(self):
        self.assert_identical_behavior("declare -p SECONDS | sed 's/=.*//'")

    def test_declare_p_epochseconds_plain(self):
        self.assert_identical_behavior("declare -p EPOCHSECONDS | sed 's/=.*//'")

    def test_declare_p_lineno_plain(self):
        self.assert_identical_behavior("declare -p LINENO | sed 's/=.*//'")

    def test_declare_p_readonly_export_random(self):
        self.assert_identical_behavior(
            "readonly RANDOM; export RANDOM; declare -p RANDOM | sed 's/=.*//'")
