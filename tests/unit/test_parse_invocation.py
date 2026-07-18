"""Unit tests for psh.invocation.parse_invocation (campaign F1).

Replaces the retired tests/unit/test_main_parse_args.py: the same
left-to-right/stop-at-first-operand pins, re-expressed against the frozen
InvocationConfig, plus the F1 additions — the registry-derived short-option
surface (-a -b -h -m -E -T -H ...), the bash-probed sign semantics of the
invocation-only letters (+i cancels; +s/+c act like -s/-c), -h == hashall,
bare trailing -o/+o listing requests, and validated --parser names.

Sign-semantics and surface expectations are bash 5.2 ground truth
(tmp/boundary-ledgers/F1-probes/base-battery.txt and base-followup.txt,
integrator-ratified 2026-07-18).
"""
import dataclasses

import pytest

from psh.invocation import (
    InvocationError,
    SourceKind,
    parse_invocation,
)


class TestFrozenConfig:
    """The config is a frozen dataclass: invocation facts cannot be rewritten."""

    def test_mutation_raises(self):
        config = parse_invocation(['-c', 'echo hi'])
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.interactive = True  # type: ignore[misc]

    def test_field_deletion_raises(self):
        config = parse_invocation([])
        with pytest.raises(dataclasses.FrozenInstanceError):
            del config.parser  # type: ignore[misc]

    def test_collections_are_immutable_types(self):
        config = parse_invocation(['-e', '-s', 'A', 'B'])
        assert isinstance(config.option_transitions, tuple)
        assert isinstance(config.positionals, tuple)
        assert isinstance(config.option_listings, tuple)
        assert isinstance(config.analysis_modes, tuple)


class TestStopsAtFirstOperand:
    def test_operand_ends_option_parsing(self):
        config = parse_invocation(['script.sh', '-i', '--norc', 'foo'])
        assert config.source_kind is SourceKind.SCRIPT
        assert config.script_path == 'script.sh'
        assert config.positionals == ('-i', '--norc', 'foo')
        assert config.interactive is False
        assert config.norc is False

    def test_flags_before_operand_are_consumed(self):
        config = parse_invocation(['--norc', '-i', 'script.sh', '--norc'])
        assert config.script_path == 'script.sh'
        assert config.positionals == ('--norc',)
        assert config.norc is True
        assert config.interactive is True

    def test_c_command_string_is_an_operand(self):
        config = parse_invocation(['-c', 'echo $@', 'x', '--parser', 'bar'])
        assert config.source_kind is SourceKind.COMMAND
        assert config.command == 'echo $@'
        assert config.argv0 == 'x'
        assert config.positionals == ('--parser', 'bar')
        assert config.parser is None

    def test_flag_between_c_and_command_string(self):
        config = parse_invocation(['-c', '--norc', 'echo hi'])
        assert config.command == 'echo hi'
        assert config.norc is True


class TestEndOfOptionsMarkers:
    def test_double_dash_ends_options(self):
        config = parse_invocation(['--', 'script.sh', '-i'])
        assert config.script_path == 'script.sh'
        assert config.positionals == ('-i',)
        assert config.interactive is False

    def test_double_dash_operand_may_start_with_dash(self):
        config = parse_invocation(['--', '--weird-name.sh'])
        assert config.script_path == '--weird-name.sh'

    def test_lone_dash_ends_options(self):
        config = parse_invocation(['-', 'script.sh', 'x'])
        assert config.script_path == 'script.sh'
        assert config.positionals == ('x',)

    def test_lone_dash_with_nothing_after(self):
        config = parse_invocation(['-'])
        assert config.source_kind is SourceKind.STDIN
        assert config.positionals == ()


class TestValueOptions:
    def test_parser_space_form(self):
        config = parse_invocation(['--parser', 'pc', '-c', 'echo hi'])
        assert config.parser == 'combinator'
        assert config.command == 'echo hi'

    def test_parser_equals_form(self):
        config = parse_invocation(['--parser=pc'])
        assert config.parser == 'combinator'

    def test_parser_canonical_name(self):
        config = parse_invocation(['--parser', 'recursive_descent'])
        assert config.parser == 'recursive_descent'

    def test_parser_invalid_name_raises_before_any_shell(self):
        # Probe class A4a: an invalid parser must fail during PURE parsing
        # (exit 2 path) — no Shell, no rc.
        with pytest.raises(InvocationError) as exc:
            parse_invocation(['--parser', 'bogus', '-i', '-s'])
        assert exc.value.status == 2
        assert 'unknown parser: bogus' in exc.value.lines[0]

    def test_rcfile_space_form(self):
        config = parse_invocation(['--rcfile', '/some/rc'])
        assert config.rcfile == '/some/rc'

    def test_missing_value_raises_2(self):
        with pytest.raises(InvocationError) as exc:
            parse_invocation(['--parser'])
        assert exc.value.status == 2

    def test_value_flag_consumes_dash_value_in_flag_position(self):
        # The token after --rcfile is its value even if it starts with '-'.
        config = parse_invocation(['--rcfile', '-odd-name'])
        assert config.rcfile == '-odd-name'


class TestInvalidOptions:
    def test_unknown_option_raises_2(self):
        with pytest.raises(InvocationError) as exc:
            parse_invocation(['--bogus'])
        assert exc.value.status == 2

    def test_unknown_short_option_raises_2(self):
        with pytest.raises(InvocationError) as exc:
            parse_invocation(['-Z', 'script.sh'])
        assert exc.value.status == 2

    def test_unknown_char_in_cluster_raises_2(self):
        with pytest.raises(InvocationError) as exc:
            parse_invocation(['-eZ', 'script.sh'])
        assert exc.value.status == 2

    def test_c_missing_command_raises_2(self):
        with pytest.raises(InvocationError) as exc:
            parse_invocation(['-c'])
        assert exc.value.status == 2
        assert exc.value.lines[0] == 'psh: -c: option requires an argument'


class TestRegistryDerivedShortOptions:
    """The short surface derives from OPTION_REGISTRY (medium 1): the old
    hardcoded 'euxvnfCB' set is gone, so -a -b -h -m -E -T -H work too."""

    def test_single_set_option(self):
        config = parse_invocation(['-e', 'script.sh'])
        assert config.option_transitions == (('errexit', True),)

    def test_cluster_maps_each_char(self):
        config = parse_invocation(['-eux'])
        assert config.option_transitions == (
            ('errexit', True), ('nounset', True), ('xtrace', True))

    def test_previously_missing_letters_now_map(self):
        config = parse_invocation(['-a', '-b', '-m', '-E', '-T', '-H'])
        assert config.option_transitions == (
            ('allexport', True), ('notify', True), ('monitor', True),
            ('errtrace', True), ('functrace', True), ('histexpand', True))

    def test_dash_h_is_hashall_not_help(self):
        # Campaign decision: -h means bash hashall; --help prints help.
        config = parse_invocation(['-h', '-c', 'echo hi'])
        assert config.option_transitions == (('hashall', True),)
        assert config.print_help is False

    def test_plus_h_disables_hashall(self):
        config = parse_invocation(['+h', '-c', 'echo hi'])
        assert config.option_transitions == (('hashall', False),)

    def test_surface_is_registry_derived(self):
        # Every registry short flag parses; the guard fails if a new
        # short-flagged option is not automatically accepted.
        from psh.core.option_registry import SHORT_TO_LONG
        for letter, long_name in SHORT_TO_LONG.items():
            config = parse_invocation([f'-{letter}'])
            assert config.option_transitions == ((long_name, True),), letter
            config = parse_invocation([f'+{letter}'])
            assert config.option_transitions == ((long_name, False),), letter

    def test_later_transition_recorded_after_earlier(self):
        # bash: last wins; the ORDER of transitions carries that.
        config = parse_invocation(['-x', '+x', '-c', 'x'])
        assert config.option_transitions == (
            ('xtrace', True), ('xtrace', False))


class TestInvocationOnlySignSemantics:
    """bash 5.2 probed: i is sign-aware; s and c are sign-blind."""

    def test_dash_i_requests_interactive(self):
        assert parse_invocation(['-i']).interactive is True

    def test_plus_i_alone_does_not_force(self):
        # bash: `bash +i -c 'echo $-'` has no i (probe C8).
        assert parse_invocation(['+i', '-c', 'x']).interactive is False

    def test_plus_i_cancels_earlier_dash_i(self):
        # bash: `bash -i +i -c 'echo $-'` has no i (probe C9).
        assert parse_invocation(['-i', '+i', '-c', 'x']).interactive is False

    def test_dash_i_after_plus_i_wins(self):
        assert parse_invocation(['+i', '-i', '-c', 'x']).interactive is True

    def test_plus_s_acts_like_dash_s(self):
        # bash: `bash +s A B` collects positionals and reads stdin (probe E2).
        config = parse_invocation(['+s', 'A', 'B'])
        assert config.source_kind is SourceKind.STDIN
        assert config.forced_stdin is True
        assert config.positionals == ('A', 'B')

    def test_plus_s_does_not_cancel_dash_s(self):
        # bash: `bash -s +s s.sh` still reads stdin (probe C10).
        config = parse_invocation(['-s', '+s', 's.sh'])
        assert config.source_kind is SourceKind.STDIN
        assert config.positionals == ('s.sh',)

    def test_plus_c_enables_command_mode(self):
        # bash: `bash +c 'echo hi'` prints hi (probe C12).
        config = parse_invocation(['+c', 'echo hi'])
        assert config.source_kind is SourceKind.COMMAND
        assert config.command == 'echo hi'

    def test_plus_c_does_not_cancel_dash_c(self):
        # bash: `bash -c +c s.sh` treats s.sh as the command string
        # (probe C11).
        config = parse_invocation(['-c', '+c', 's.sh'])
        assert config.source_kind is SourceKind.COMMAND
        assert config.command == 's.sh'

    def test_cluster_with_s_and_interactive(self):
        config = parse_invocation(['-si'])
        assert config.forced_stdin is True
        assert config.interactive is True

    def test_ic_cluster_takes_next_arg_as_command(self):
        config = parse_invocation(['-uic', 'echo hi', 'name', 'p1'])
        assert config.source_kind is SourceKind.COMMAND
        assert config.command == 'echo hi'
        assert config.argv0 == 'name'
        assert config.positionals == ('p1',)
        assert config.interactive is True
        assert config.option_transitions == (('nounset', True),)


class TestSourceKindAndDollarZero:
    def test_default_is_stdin(self):
        config = parse_invocation([])
        assert config.source_kind is SourceKind.STDIN
        assert config.argv0 == 'psh'
        assert config.positionals == ()

    def test_c_positional_zero_and_params(self):
        # POSIX: `sh -c cmd name a b` -> $0=name, $1=a, $2=b.
        config = parse_invocation(['-c', 'echo', 'name', 'a', 'b'])
        assert config.argv0 == 'name'
        assert config.positionals == ('a', 'b')

    def test_c_without_name_keeps_shell_argv0(self):
        config = parse_invocation(['-c', 'echo'])
        assert config.argv0 == 'psh'

    def test_script_argv0_is_script_path(self):
        config = parse_invocation(['s.sh', 'a'])
        assert config.argv0 == 's.sh'
        assert config.positionals == ('a',)

    def test_s_with_operands_collects_positionals(self):
        config = parse_invocation(['-s', 'foo', 'bar'])
        assert config.source_kind is SourceKind.STDIN
        assert config.argv0 == 'psh'
        assert config.positionals == ('foo', 'bar')

    def test_s_with_c_keeps_forced_stdin_fact(self):
        # bash `-sc 'echo $-'` shows 's' (probe E1a): the -s fact survives -c.
        config = parse_invocation(['-s', '-c', 'echo hi'])
        assert config.source_kind is SourceKind.COMMAND
        assert config.forced_stdin is True


class TestLongOptionForms:
    def test_o_long_option_enables(self):
        config = parse_invocation(['-o', 'pipefail', '-c', 'x'])
        assert config.option_transitions == (('pipefail', True),)

    def test_plus_o_long_option_disables(self):
        config = parse_invocation(['+o', 'pipefail', '-c', 'x'])
        assert config.option_transitions == (('pipefail', False),)

    def test_o_in_cluster_consumes_next_arg(self):
        config = parse_invocation(['-eo', 'pipefail', '-c', 'x'])
        assert config.option_transitions == (
            ('errexit', True), ('pipefail', True))

    def test_o_attached_name(self):
        config = parse_invocation(['-opipefail', '-c', 'x'])
        assert config.option_transitions == (('pipefail', True),)

    def test_o_bad_name_raises_2(self):
        with pytest.raises(InvocationError) as exc:
            parse_invocation(['-o', 'nosuchoption', '-c', 'x'])
        assert exc.value.status == 2

    def test_o_rejects_internal_option_name(self):
        # `interactive` is INTERNAL — not user-settable by name (bash).
        with pytest.raises(InvocationError) as exc:
            parse_invocation(['-o', 'interactive', '-c', 'x'])
        assert exc.value.status == 2

    def test_bare_trailing_o_is_listing_request(self):
        # bash: `bash -o` prints the set -o table and continues (probe E3b).
        config = parse_invocation(['-o'])
        assert config.option_listings == ('-',)
        assert config.option_transitions == ()
        assert config.source_kind is SourceKind.STDIN

    def test_bare_trailing_plus_o_is_listing_request(self):
        config = parse_invocation(['+o'])
        assert config.option_listings == ('+',)

    def test_posix_flag_is_a_transition(self):
        config = parse_invocation(['--posix', '-c', 'x'])
        assert config.option_transitions == (('posix', True),)


class TestDebugAndAnalysisFlags:
    def test_debug_flags_become_transitions(self):
        config = parse_invocation(['--debug-ast', '--debug-tokens'])
        assert config.option_transitions == (
            ('debug-ast', True), ('debug-tokens', True))

    def test_debug_ast_format(self):
        config = parse_invocation(['--debug-ast=tree'])
        assert config.option_transitions == (('debug-ast', True),)
        assert config.ast_format == 'tree'

    def test_debug_detail_implies_base(self):
        config = parse_invocation(['--debug-expansion-detail'])
        assert config.option_transitions == (
            ('debug-expansion-detail', True), ('debug-expansion', True))

    def test_analysis_modes_ordered(self):
        config = parse_invocation(['--security', '--format', 's.sh'])
        assert config.analysis_modes == ('security', 'format')

    def test_analysis_mode_deduplicated(self):
        config = parse_invocation(['--lint', '--lint', 's.sh'])
        assert config.analysis_modes == ('lint',)


class TestHelpVersionFlags:
    def test_help_flag(self):
        assert parse_invocation(['--help']).print_help is True

    def test_dash_h_is_not_help(self):
        assert parse_invocation(['-h']).print_help is False

    def test_version_flag(self):
        assert parse_invocation(['-V']).print_version is True

    def test_help_in_operand_position_passes_through(self):
        config = parse_invocation(['script.sh', '--help'])
        assert config.print_help is False
        assert config.positionals == ('--help',)
