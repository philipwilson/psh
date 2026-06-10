"""C-style for loops, control structures in pipelines, and eval.

The user guide claims "Full support" for all three — these tests prove
the claims (added when the claims meta-test flagged them as unproven).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestCStyleForConformance(ConformanceTest):
    def test_basic_counting(self):
        self.assert_identical_behavior('for ((i=0; i<3; i++)); do echo "i:$i"; done')

    def test_countdown(self):
        self.assert_identical_behavior('for ((i=10; i>7; i--)); do echo "$i"; done')

    def test_accumulator(self):
        self.assert_identical_behavior(
            's=0; for ((i=1; i<=4; i++)); do ((s+=i)); done; echo "sum:$s"')

    def test_empty_sections_with_break(self):
        self.assert_identical_behavior('for ((;;)); do echo once; break; done')


class TestControlStructuresInPipelines(ConformanceTest):
    def test_while_read_from_pipe(self):
        self.assert_identical_behavior(
            'echo data | while read -r x; do echo "got:$x"; done')

    def test_if_into_pipe(self):
        self.assert_identical_behavior('if true; then echo yes; fi | tr a-z A-Z')

    def test_while_read_from_herestring(self):
        self.assert_identical_behavior(
            "while read -r l; do echo \"[$l]\"; done <<< $'one\\ntwo'")

    def test_brace_group_reading_pipe(self):
        self.assert_identical_behavior(
            "printf '3\\n1\\n2\\n' | { while read -r n; do echo \"n=$n\"; done; }")


class TestEvalConformance(ConformanceTest):
    def test_simple_eval(self):
        self.assert_identical_behavior("eval 'echo evaled'")

    def test_eval_with_expansion(self):
        self.assert_identical_behavior('x=\'echo nested\'; eval "$x $((1+1))"')

    def test_eval_assignment_persists(self):
        self.assert_identical_behavior("eval 'a=5'; echo \"a:$a\"")

    def test_eval_exit_status(self):
        self.assert_identical_behavior("eval 'echo \"rc test\"; false'; echo \"rc:$?\"")
