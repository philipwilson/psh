"""POSIX-mode special-builtin exit-on-error conformance (bash 5.2).

Live re-check of docs/reviews/posix_special_builtin_exit_matrix_2026-07-07.md
against the host bash: with ``set -o posix`` a non-interactive shell exits
on a special builtin's USAGE/SYNTAX error (invalid option, top-level
``return``, missing dot file, ``eval`` syntax error, readonly assignment)
with the builtin's own status, and does NOT exit on OPERAND errors (bad
identifier, bad signal spec, unset of a readonly). ``command`` strips the
exit; subshells/command substitution contain it.

Diagnostics carry different shell-name prefixes and wording, so these rows
compare stdout + exit code and only require stderr-presence agreement
(the ``check_behavior`` pattern of test_readonly_conformance.py).

Deliberately NOT pinned here: bare ``r=2`` on a readonly under ``-c``
(bash's -c mode exits 127 via an internal artifact where its own file and
stdin modes — and psh everywhere — exit 1; see the integration pins in
tests/integration/test_posix_special_builtin_exit.py).
"""


from conformance_framework import ConformanceTest


class _StatusConformance(ConformanceTest):
    def _assert_same_stdout_and_status(self, command):
        result = self.check_behavior(command)
        assert result.psh_result.stdout == result.bash_result.stdout, command
        assert result.psh_result.exit_code == result.bash_result.exit_code, command
        assert bool(result.psh_result.stderr) == bool(result.bash_result.stderr), command


class TestPosixSpecialBuiltinExit(_StatusConformance):
    """Rows that EXIT: 'survived' must not print; exact status matches."""

    def test_set_invalid_option_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; set -q; echo survived")

    def test_export_invalid_option_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; export -q; echo survived")

    def test_readonly_invalid_option_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; readonly -q; echo survived")

    def test_unset_invalid_option_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; unset -q; echo survived")

    def test_trap_invalid_option_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; trap -q; echo survived")

    def test_set_o_bad_name_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; set -o nosuchoption; echo survived")

    def test_exec_invalid_option_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; exec -q true; echo survived")

    def test_return_top_level_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; return; echo survived")

    def test_dot_missing_file_exits_1(self):
        self._assert_same_stdout_and_status(
            "set -o posix; . /nonexistent/psh-conf-posixexit; echo survived")

    def test_source_missing_file_exits_1(self):
        self._assert_same_stdout_and_status(
            "set -o posix; source /nonexistent/psh-conf-posixexit; echo survived")

    def test_eval_syntax_error_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; eval 'if'; echo survived")

    def test_eval_nested_special_error_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; eval 'set -q'; echo survived")

    def test_readonly_assignment_exits_1(self):
        self._assert_same_stdout_and_status(
            "set -o posix; readonly r=1; readonly r=2; echo survived")

    def test_export_readonly_assignment_exits_1(self):
        self._assert_same_stdout_and_status(
            "set -o posix; readonly r=1; export r=2; echo survived")

    def test_function_body_special_error_exits_2(self):
        self._assert_same_stdout_and_status(
            "set -o posix; f() { set -q; }; f; echo survived")


class TestPosixSpecialBuiltinNoExit(_StatusConformance):
    """Operand/semantic errors and stripped/contained contexts survive."""

    def test_export_bad_identifier_survives(self):
        self._assert_same_stdout_and_status(
            "set -o posix; export 1bad=x; echo rc=$?")

    def test_readonly_bad_identifier_survives(self):
        self._assert_same_stdout_and_status(
            "set -o posix; readonly 1bad=x; echo rc=$?")

    def test_trap_bad_signal_survives(self):
        self._assert_same_stdout_and_status(
            "set -o posix; trap 'x' NOSUCHSIG; echo rc=$?")

    def test_unset_readonly_survives(self):
        self._assert_same_stdout_and_status(
            "set -o posix; readonly r=1; unset r; echo rc=$?")

    def test_unset_bad_identifier_survives(self):
        self._assert_same_stdout_and_status(
            "set -o posix; unset 1bad; echo rc=$?")

    def test_declare_readonly_assignment_survives(self):
        self._assert_same_stdout_and_status(
            "set -o posix; readonly r=1; declare r=2; echo rc=$?")

    def test_break_top_level_silent_rc0(self):
        self._assert_same_stdout_and_status(
            "set -o posix; break; echo rc=$?")

    def test_continue_top_level_silent_rc0(self):
        self._assert_same_stdout_and_status(
            "set -o posix; continue; echo rc=$?")

    def test_subshell_contains_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; ( set -q ); echo rc=$?")

    def test_command_substitution_contains_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; x=$(set -q); echo rc=$?")

    def test_command_strips_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; command set -q; echo rc=$?")

    def test_command_strips_eval_syntax_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; command eval 'if'; echo rc=$?")

    def test_posix_off_again_survives(self):
        self._assert_same_stdout_and_status(
            "set -o posix; set +o posix; set -q; echo rc=$?")

    def test_shift_out_of_range_survives_with_message(self):
        self._assert_same_stdout_and_status(
            "set -o posix; shift 5; echo rc=$?")

    def test_prefix_readonly_nonspecial_discards_unit(self):
        # The command does not run and the rest of the -c string (the
        # current input unit) is discarded, rc 1 — same shape as a pure
        # readonly-assignment error.
        self._assert_same_stdout_and_status(
            "set -o posix; readonly r=1; r=2 echo RAN; echo rc=$?")

    # `r=2 :` (special builtin) exits the shell — rc 1 in file/stdin modes
    # (pinned in tests/integration/test_posix_special_builtin_exit.py) but
    # 127 in bash's -c mode (the same ledgered -c artifact as bare `r=2`),
    # so it has no -c-shaped conformance row here.


class TestPosixSuppressibleExit(_StatusConformance):
    """Bounce F1: the suppressible/hard exit-class split, live vs bash.
    Invalid-option and top-level-return exits are suppressed in
    errexit-exempt contexts (through functions, not across eval/dot);
    dot-file and readonly-assignment exits are hard even when guarded."""

    def test_or_guard_suppresses_invalid_option(self):
        self._assert_same_stdout_and_status(
            "set -o posix; set -q || echo caught; echo rc=$?")

    def test_if_guard_suppresses_through_function(self):
        self._assert_same_stdout_and_status(
            "set -o posix; f() { set -q; }; if f; then echo T; else echo F; fi")

    def test_eval_boundary_not_suppressed(self):
        self._assert_same_stdout_and_status(
            "set -o posix; eval 'set -q' || echo caught; echo survived")

    def test_hard_dot_missing_guarded_still_exits(self):
        self._assert_same_stdout_and_status(
            "set -o posix; if . /nonexistent/psh-conf-sup; then echo T; fi; echo x")
