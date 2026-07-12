"""POSIX getopts conformance tests.

The user guide claims "Full support" for the getopts builtin — per the
project's development principles, that claim is proven here. Every case
asserts byte-identical psh/bash behavior.
"""


from conformance_framework import ConformanceTest


class TestGetoptsBasics(ConformanceTest):
    def test_simple_flags_and_argument(self):
        self.assert_identical_behavior(
            'set -- -a -b val arg; while getopts "ab:" opt; do '
            'echo "opt:$opt arg:$OPTARG"; done; echo "ind:$OPTIND"')

    def test_clustered_options(self):
        self.assert_identical_behavior(
            'set -- -ab val; while getopts "ab:" opt; do echo "o:$opt:$OPTARG"; done')

    def test_cluster_does_not_clobber_positional_params(self):
        # R14.A: parsing a clustered option must NOT rewrite $1 (the old impl
        # mutated the positional params, leaving $1 as "-bc").
        self.assert_identical_behavior(
            'set -- -abc x; getopts abc o; echo "o=$o 1=$1"; '
            'getopts abc o; echo "o=$o 1=$1"')

    def test_full_cluster_loop_preserves_positionals(self):
        self.assert_identical_behavior(
            'set -- -abc tail; while getopts abc o; do echo "got:$o"; done; '
            'echo "ind:$OPTIND first:$1"')

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

    def test_loud_mode_invalid_option_unsets_optarg(self):
        # R13.A: in non-silent (loud) mode, an invalid option leaves OPTARG
        # UNSET (bash); psh previously set it to the bad char. stderr suppressed.
        self.assert_identical_behavior(
            'set -- -x; getopts "ab" opt 2>/dev/null; '
            'echo "opt:$opt optarg:${OPTARG-UNSET}"')


class TestGetoptsState(ConformanceTest):
    def test_local_optind_resets_per_function(self):
        self.assert_identical_behavior(
            'f() { local OPTIND; while getopts "x:" o; do echo "$o=$OPTARG"; done; }; '
            'f -x one; f -x two')

    def test_exit_status_when_options_exhausted(self):
        self.assert_identical_behavior(
            'set -- -a; getopts "a" o; echo "rc1:$?"; getopts "a" o; echo "rc2:$?"')
