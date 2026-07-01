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
        with pytest.raises(SystemExit) as exc:
            parse_args(['-x', 'script.sh'])
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
