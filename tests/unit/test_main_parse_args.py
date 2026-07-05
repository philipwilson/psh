"""Unit tests for psh.__main__.parse_args (reappraisal #15 I1).

Left-to-right option parsing that stops at the first non-option operand:
everything from the operand on belongs to the script/command untouched.
"""
import pytest

from psh.__main__ import parse_args


class TestStopsAtFirstOperand:
    def test_operand_ends_option_parsing(self):
        opts, operands = parse_args(['script.sh', '-i', '--norc', 'foo'])
        assert operands == ['script.sh', '-i', '--norc', 'foo']
        assert opts['force_interactive'] is False
        assert opts['norc'] is False

    def test_flags_before_operand_are_consumed(self):
        opts, operands = parse_args(['--norc', '-i', 'script.sh', '--norc'])
        assert operands == ['script.sh', '--norc']
        assert opts['norc'] is True
        assert opts['force_interactive'] is True

    def test_c_command_string_is_an_operand(self):
        opts, operands = parse_args(['-c', 'echo $@', 'x', '--parser', 'bar'])
        assert opts['command_mode'] is True
        assert operands == ['echo $@', 'x', '--parser', 'bar']
        assert opts['parser_type'] is None

    def test_flag_between_c_and_command_string(self):
        opts, operands = parse_args(['-c', '--norc', 'echo hi'])
        assert opts['command_mode'] is True
        assert opts['norc'] is True
        assert operands == ['echo hi']


class TestEndOfOptionsMarkers:
    def test_double_dash_ends_options(self):
        opts, operands = parse_args(['--', 'script.sh', '-i'])
        assert operands == ['script.sh', '-i']
        assert opts['force_interactive'] is False

    def test_double_dash_operand_may_start_with_dash(self):
        _, operands = parse_args(['--', '--weird-name.sh'])
        assert operands == ['--weird-name.sh']

    def test_lone_dash_ends_options(self):
        _, operands = parse_args(['-', 'script.sh', 'x'])
        assert operands == ['script.sh', 'x']

    def test_lone_dash_with_nothing_after(self):
        _, operands = parse_args(['-'])
        assert operands == []


class TestValueOptions:
    def test_parser_space_form(self):
        opts, operands = parse_args(['--parser', 'pc', '-c', 'echo hi'])
        assert opts['parser_type'] == 'pc'
        assert operands == ['echo hi']

    def test_parser_equals_form(self):
        opts, _ = parse_args(['--parser=pc'])
        assert opts['parser_type'] == 'pc'

    def test_rcfile_space_form(self):
        opts, _ = parse_args(['--rcfile', '/some/rc'])
        assert opts['rcfile'] == '/some/rc'

    def test_missing_value_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            parse_args(['--parser'])
        assert exc.value.code == 2

    def test_value_flag_consumes_dash_value_in_flag_position(self):
        # The token after --rcfile is its value even if it starts with '-'.
        opts, _ = parse_args(['--rcfile', '-odd-name'])
        assert opts['rcfile'] == '-odd-name'


class TestInvalidOptions:
    def test_unknown_option_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            parse_args(['--bogus'])
        assert exc.value.code == 2

    def test_unknown_short_option_exits_2(self):
        # -Z is not a recognized short option (bash rejects it too). The
        # POSIX set-options -e/-u/-x/-v/-n/-f/-C and -s are now accepted.
        with pytest.raises(SystemExit) as exc:
            parse_args(['-Z', 'script.sh'])
        assert exc.value.code == 2

    def test_unknown_char_in_cluster_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            parse_args(['-eZ', 'script.sh'])
        assert exc.value.code == 2


class TestPosixShortOptions:
    """bash-style POSIX short options: -e/-u/-x/-v/-n/-f/-C, -s, clusters."""

    def test_single_set_option(self):
        opts, operands = parse_args(['-e', 'script.sh'])
        assert opts['set_options'] == [('errexit', True)]
        assert operands == ['script.sh']

    def test_cluster_maps_each_char(self):
        opts, _ = parse_args(['-eux'])
        assert opts['set_options'] == [
            ('errexit', True), ('nounset', True), ('xtrace', True)]

    def test_all_finding_short_options(self):
        opts, _ = parse_args(['-e', '-u', '-x', '-v', '-n', '-f', '-C'])
        assert opts['set_options'] == [
            ('errexit', True), ('nounset', True), ('xtrace', True),
            ('verbose', True), ('noexec', True), ('noglob', True),
            ('noclobber', True)]

    def test_dash_s_sets_stdin_mode(self):
        opts, operands = parse_args(['-s', 'foo', 'bar'])
        assert opts['stdin_mode'] is True
        assert operands == ['foo', 'bar']

    def test_cluster_with_s_and_interactive(self):
        opts, _ = parse_args(['-si'])
        assert opts['stdin_mode'] is True
        assert opts['force_interactive'] is True

    def test_short_options_stop_at_operand(self):
        opts, operands = parse_args(['-x', 'script.sh', '-e'])
        assert opts['set_options'] == [('xtrace', True)]
        assert operands == ['script.sh', '-e']


class TestInvocationOptionForms:
    """R18 T2-E (M-s3): -o/+o NAME, +flag (disable), and -c clustered.

    Verified against bash 5.2 (`bash -o pipefail -c`, `bash +x -c`,
    `bash -xc 'cmd'`, `bash -eo pipefail`).
    """

    def test_o_long_option_enables(self):
        opts, operands = parse_args(['-o', 'pipefail', '-c', 'x'])
        assert opts['set_options'] == [('pipefail', True)]
        assert opts['command_mode'] is True
        assert operands == ['x']

    def test_plus_o_long_option_disables(self):
        opts, _ = parse_args(['+o', 'pipefail', '-c', 'x'])
        assert opts['set_options'] == [('pipefail', False)]

    def test_plus_short_flag_disables(self):
        opts, _ = parse_args(['+x', '-c', 'x'])
        assert opts['set_options'] == [('xtrace', False)]

    def test_plus_cluster_disables_each(self):
        opts, _ = parse_args(['+ex'])
        assert opts['set_options'] == [('errexit', False), ('xtrace', False)]

    def test_c_clustered_with_short_flag(self):
        # -xc 'cmd': -x enables xtrace, -c starts command mode.
        opts, operands = parse_args(['-xc', 'echo hi'])
        assert opts['set_options'] == [('xtrace', True)]
        assert opts['command_mode'] is True
        assert operands == ['echo hi']

    def test_c_first_in_cluster(self):
        opts, operands = parse_args(['-cx', 'echo hi'])
        assert opts['set_options'] == [('xtrace', True)]
        assert opts['command_mode'] is True
        assert operands == ['echo hi']

    def test_o_in_cluster_consumes_next_arg(self):
        # -eo pipefail: -e enables errexit, -o consumes 'pipefail'.
        opts, operands = parse_args(['-eo', 'pipefail', '-c', 'x'])
        assert opts['set_options'] == [('errexit', True), ('pipefail', True)]
        assert operands == ['x']

    def test_o_attached_name(self):
        opts, _ = parse_args(['-opipefail', '-c', 'x'])
        assert opts['set_options'] == [('pipefail', True)]

    def test_later_plus_overrides_earlier_minus(self):
        # bash: last wins. Applied in order, so -x then +x leaves xtrace off.
        opts, _ = parse_args(['-x', '+x', '-c', 'x'])
        assert opts['set_options'] == [('xtrace', True), ('xtrace', False)]

    def test_o_bad_name_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            parse_args(['-o', 'nosuchoption', '-c', 'x'])
        assert exc.value.code == 2

    def test_o_missing_argument_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            parse_args(['-o'])
        assert exc.value.code == 2

    def test_o_rejects_internal_option_name(self):
        # `interactive` is INTERNAL — not user-settable by name (bash).
        with pytest.raises(SystemExit) as exc:
            parse_args(['-o', 'interactive', '-c', 'x'])
        assert exc.value.code == 2


class TestHelpVersionFlags:
    def test_help_flag(self):
        opts, _ = parse_args(['--help'])
        assert opts['help'] is True

    def test_version_flag(self):
        opts, _ = parse_args(['-V'])
        assert opts['version'] is True

    def test_help_in_operand_position_passes_through(self):
        opts, operands = parse_args(['script.sh', '--help'])
        assert opts['help'] is False
        assert operands == ['script.sh', '--help']
