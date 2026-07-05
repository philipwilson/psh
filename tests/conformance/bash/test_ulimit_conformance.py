"""Conformance tests for the ``ulimit`` builtin (reappraisal #18 Tier-2 T2-G).

psh previously had no ulimit builtin, so `ulimit` fell through to an external
``/usr/bin/ulimit`` binary that runs in a child process and therefore could not
change the shell's own limits (and does not exist at all on Linux). The builtin
now calls ``resource.setrlimit`` on the psh process itself, matching bash's
shell-builtin semantics.

These pin the portable, cross-platform behaviors: set/query round-trips for
resources every platform exposes, and hard/soft queries (which both shells read
from the same live kernel limits, so they agree by construction). The full
``ulimit -a`` layout and platform-specific resources are intentionally NOT
compared byte-for-byte — the available resource set and the (non-rlimit) pipe
size line differ between macOS and Linux. Each case runs in its own subprocess,
so lowering a soft limit cannot affect the test runner.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestUlimitConformance(ConformanceTest):
    def test_set_and_query_open_files_soft(self):
        # Marker for CLAIM_TESTS: 'ulimit -S -n 256'
        self.assert_identical_behavior('ulimit -S -n 256; ulimit -n')

    def test_set_open_files_sets_both_when_no_hs(self):
        self.assert_identical_behavior('ulimit -n 256; ulimit -n')

    def test_set_core_size(self):
        self.assert_identical_behavior('ulimit -S -c 0; ulimit -c')

    def test_set_file_size_blocks(self):
        # File size reports in 512-byte blocks; a set/query round-trip proves
        # the block-factor scaling is inverse-consistent.
        self.assert_identical_behavior('ulimit -S -f 100; ulimit -f')

    def test_set_cpu_seconds(self):
        self.assert_identical_behavior('ulimit -S -t 30; ulimit -t')

    def test_query_hard_open_files(self):
        self.assert_identical_behavior('ulimit -Hn')

    def test_query_soft_open_files(self):
        self.assert_identical_behavior('ulimit -Sn')

    def test_bare_ulimit_is_file_size_soft(self):
        self.assert_identical_behavior('ulimit')

    def test_soft_wins_when_both_hs(self):
        self.assert_identical_behavior('ulimit -HSn')

    def test_multiple_resources_print_labelled(self):
        self.assert_identical_behavior('ulimit -n -c')

    def test_unlimited_keyword(self):
        self.assert_identical_behavior('ulimit -c unlimited; ulimit -c')

    def test_hard_and_soft_queries_separately(self):
        self.assert_identical_behavior(
            'ulimit -c 0; ulimit -Sc; ulimit -Hc')
