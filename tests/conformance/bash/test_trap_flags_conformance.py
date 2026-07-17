"""Conformance tests for `trap` option-flag handling (getopt over "lp").

`trap`'s flags -l/-p parse getopt-style: they cluster (`-lp`, `-pl`, `-ll`,
`-pp`) and may be split across words (`-p -l`), with -l dominating when
present. Before this fix psh matched only the exact words `-l`/`-p`, so every
cluster was rejected as an invalid option and `trap -p -l` mis-parsed `-l` as a
signal spec. Verified against bash 5.2.

The listing cases are written as SELF-checking differentials (`[ "$(trap
-lp)" = "$(trap -l)" ]`) so the assertion is platform-independent (macOS and
Linux signal names/numbers differ). Bad-option diagnostics are compared by
exit code + stderr substring, because bash prefixes the message with
`bash: line N:` and psh does not (a separate systemic divergence, task #35).
"""

import subprocess
import sys

from conformance_framework import ConformanceTest
from shell_oracle import resolve_bash


class TestTrapFlagClustersConformance(ConformanceTest):
    """Clusters and split words parse like bash; -l dominates."""

    def test_lp_cluster_lists_like_l(self):
        self.assert_identical_behavior(
            'trap "echo hi" INT; [ "$(trap -lp)" = "$(trap -l)" ] && echo SAME')

    def test_pl_cluster_lists_like_l(self):
        self.assert_identical_behavior(
            'trap "echo hi" INT; [ "$(trap -pl)" = "$(trap -l)" ] && echo SAME')

    def test_ll_doubled_lists_like_l(self):
        self.assert_identical_behavior(
            '[ "$(trap -ll)" = "$(trap -l)" ] && echo SAME')

    def test_p_l_split_words_list_like_l(self):
        # Regression: `trap -p -l` used to fail with 'invalid signal
        # specification' rc 1 because `-l` was parsed as a signal spec.
        self.assert_identical_behavior(
            'trap "echo hi" INT; [ "$(trap -p -l)" = "$(trap -l)" ] && echo SAME')

    def test_pp_doubled_shows_like_p(self):
        self.assert_identical_behavior(
            'trap "echo h" INT; [ "$(trap -pp)" = "$(trap -p)" ] && echo SAME')


class TestTrapBadOptionConformance(ConformanceTest):
    """A bad flag char reports the CHAR (not the cluster), rc 2."""

    def _run(self, cmd):
        psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                             capture_output=True, text=True)
        bash = subprocess.run([resolve_bash().path, '-c', cmd],
                              capture_output=True, text=True)
        return psh, bash

    def test_lx_reports_x_not_l(self):
        # bash: `trap: -x: invalid option`; the valid `l` is consumed first.
        psh, bash = self._run("trap -lx 2>&1; echo rc=$?")
        assert psh.stdout.endswith("rc=2\n")
        assert bash.stdout.endswith("rc=2\n")
        assert "trap: -x: invalid option" in psh.stdout
        assert "trap: -x: invalid option" in bash.stdout

    def test_pq_reports_q_not_p(self):
        psh, bash = self._run("trap -pq 2>&1; echo rc=$?")
        assert psh.stdout.endswith("rc=2\n")
        assert bash.stdout.endswith("rc=2\n")
        assert "trap: -q: invalid option" in psh.stdout
        assert "trap: -q: invalid option" in bash.stdout
