"""Conformance tests for the `time` keyword's TIMEFORMAT handling (F15).

psh now honors $TIMEFORMAT (previously it always printed its default report).
Timing VALUES are non-deterministic, so these pin the deterministic corners
where psh must match bash exactly: a %-free (literal) format, an empty format
(which suppresses the report), and `%%` (literal percent). The directive
FORMATTING for the non-deterministic values is shape-pinned by
tests/integration/test_timeformat.py.
"""

import os
import sys

# Add parent directory to path for framework import
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestTimeFormatConformance(ConformanceTest):
    """$TIMEFORMAT is honored, matching bash on the deterministic cases."""

    def test_timeformat_literal_format(self):
        """A %-free TIMEFORMAT is deterministic; psh must honor it like bash."""
        self.assert_identical_behavior('TIMEFORMAT="CUSTOM_FMT"; { time true; } 2>&1')

    def test_timeformat_empty_suppresses_report(self):
        """An empty TIMEFORMAT prints no report at all (bash)."""
        self.assert_identical_behavior('TIMEFORMAT=; { time true; } 2>&1; echo END')

    def test_timeformat_percent_percent_literal(self):
        """`%%` is a literal percent in TIMEFORMAT (the rest is %-free)."""
        self.assert_identical_behavior('TIMEFORMAT="100%% done"; { time true; } 2>&1')
