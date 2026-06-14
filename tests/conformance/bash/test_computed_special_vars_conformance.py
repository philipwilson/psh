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
