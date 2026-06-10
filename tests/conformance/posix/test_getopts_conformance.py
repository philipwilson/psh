"""POSIX getopts conformance tests.

The user guide claims "Full support" for the getopts builtin — per the
project's development principles, that claim is proven here. Every case
asserts byte-identical psh/bash behavior.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestGetoptsBasics(ConformanceTest):
    def test_simple_flags_and_argument(self):
        self.assert_identical_behavior(
            'set -- -a -b val arg; while getopts "ab:" opt; do '
            'echo "opt:$opt arg:$OPTARG"; done; echo "ind:$OPTIND"')

    def test_clustered_options(self):
        self.assert_identical_behavior(
            'set -- -ab val; while getopts "ab:" opt; do echo "o:$opt:$OPTARG"; done')

    def test_option_argument_attached(self):
        self.assert_identical_behavior(
            'set -- -bval; while getopts "ab:" opt; do echo "o:$opt:$OPTARG"; done')

    def test_stops_at_first_operand(self):
        self.assert_identical_behavior(
            'set -- arg1; while getopts "ab" opt; do echo "o:$opt"; done; '
            'echo "ind:$OPTIND rest:$1"')

    def test_double_dash_terminates(self):
        self.assert_identical_behavior(
            'set -- -a -- -b; while getopts "ab" opt; do echo "o:$opt"; done; '
            'echo "ind:$OPTIND"')


class TestGetoptsErrors(ConformanceTest):
    def test_silent_mode_invalid_option(self):
        # leading ':' = silent mode: opt becomes '?', OPTARG the bad char
        self.assert_identical_behavior(
            'set -- -x; while getopts ":ab" opt; do echo "o:$opt:$OPTARG"; done')

    def test_silent_mode_missing_argument(self):
        # silent mode: opt becomes ':', OPTARG the option lacking its arg
        self.assert_identical_behavior(
            'set -- -b; while getopts ":ab:" opt; do echo "o:$opt:$OPTARG"; done')

    def test_loud_mode_sets_question_mark(self):
        # error text goes to stderr with the shell's own name; compare
        # stdout and status only
        self.assert_identical_behavior(
            'set -- -x; while getopts "ab" opt 2>/dev/null; do echo "o:$opt"; done; echo done')


class TestGetoptsState(ConformanceTest):
    def test_local_optind_resets_per_function(self):
        self.assert_identical_behavior(
            'f() { local OPTIND; while getopts "x:" o; do echo "$o=$OPTARG"; done; }; '
            'f -x one; f -x two')

    def test_exit_status_when_options_exhausted(self):
        self.assert_identical_behavior(
            'set -- -a; getopts "a" o; echo "rc1:$?"; getopts "a" o; echo "rc2:$?"')
