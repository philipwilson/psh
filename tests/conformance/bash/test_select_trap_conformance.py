"""select and trap conformance tests.

The user guide claims "Full support" for select and standard-signal +
EXIT/DEBUG/ERR traps — per the project's development principles, those
claims are proven here against bash.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestSelectConformance(ConformanceTest):
    """select reads menu choices from stdin (menu/prompt go to stderr)."""

    def test_numeric_choice_sets_variable(self):
        self.assert_identical_behavior(
            'echo 1 | { select x in alpha beta; do echo "got:$x"; break; done; } 2>/dev/null')

    def test_out_of_range_choice_is_empty(self):
        self.assert_identical_behavior(
            'echo 9 | { select x in alpha beta; do echo "got:[$x]"; break; done; } 2>/dev/null')

    def test_non_numeric_sets_reply_only(self):
        self.assert_identical_behavior(
            'echo foo | { select x in alpha beta; do echo "reply:$REPLY got:[$x]"; break; done; } 2>/dev/null')

    def test_second_item(self):
        self.assert_identical_behavior(
            "printf '2\\n' | { select x in a b c; do echo \"x:$x\"; break; done; } 2>/dev/null")

    def test_eof_exits_with_status_one(self):
        self.assert_identical_behavior(
            'select x in a b; do break; done < /dev/null 2>/dev/null; echo "rc:$?"')


class TestTrapConformance(ConformanceTest):
    def test_exit_trap_runs_on_exit(self):
        self.assert_identical_behavior("trap 'echo exit_trap' EXIT; echo body")

    def test_exit_trap_can_be_cleared(self):
        self.assert_identical_behavior("trap 'echo cleanup' EXIT; trap - EXIT; echo no_trap")

    def test_exit_trap_replaced_not_stacked(self):
        self.assert_identical_behavior("trap 'echo t1' EXIT; trap 'echo t2' EXIT; echo body")

    def test_subshell_runs_its_own_exit_trap(self):
        self.assert_identical_behavior(
            "(trap 'echo sub_exit' EXIT; echo in_sub); echo out")

    def test_err_trap_sees_status(self):
        self.assert_identical_behavior(
            "f() { return 4; }; trap 'echo \"err:$?\"' ERR; f; echo after")

    def test_debug_trap_fires_per_command(self):
        self.assert_identical_behavior(
            "trap 'echo dbg' DEBUG; echo one >/dev/null; trap - DEBUG; echo two")

    def test_usr1_trap_runs_action(self):
        self.assert_identical_behavior(
            "trap 'echo got_usr1' USR1; kill -USR1 $$; echo after")

    def test_trap_action_can_exit(self):
        self.assert_identical_behavior(
            "trap 'echo int_exit; exit 7' USR1; kill -USR1 $$; echo no")

    def test_ignored_signal_does_not_kill(self):
        self.assert_identical_behavior("trap '' TERM; kill -TERM $$; echo survived")

    def test_ignored_usr2_does_not_kill(self):
        self.assert_identical_behavior("trap '' USR2; kill -USR2 $$; echo survived")
