"""POSIX-mode special-builtin exit-on-error conformance (bash 5.3.15).

Live re-check of docs/reviews/posix_special_builtin_exit_matrix_2026-07-07.md
against the host bash: with ``set -o posix`` a non-interactive shell exits
on a special builtin's USAGE/SYNTAX error (invalid option, top-level
``return``, missing dot file, ``eval`` syntax error, readonly assignment)
with the builtin's own status.  ``command`` strips the exit;
subshells/command substitution contain it.

BASH 5.3 WIDENED THE EXIT SET (CHANGES, bash-5.3-alpha, "1. Changes to
Bash" item jj: "POSIX special builtins now exit the shell in posix mode on
more failure cases"; item nnnnn: "Fix posix-mode cases where failure of
special builtins did not cause the shell to exit").  Probed on 5.3.15 in -c,
script-file and stdin modes: ``export``/``readonly`` with an invalid
identifier (stopping the operand loop at the FIRST one) and ``unset``
refusing a readonly variable, array, element or function now EXIT with
status 1, and the exit is SUPPRESSIBLE by a guard OUTSIDE an ``eval`` or
``.`` boundary (``eval 'set -q' || echo caught`` prints ``caught``).  Under
the 5.2 series those operand errors continued and the eval/dot boundary
reset suppression.  psh adopted the 5.3 shape in slot 2.2, so every former
declared-divergence row here is now a parity row in
``TestPosixSpecialBuiltinExit`` / ``TestPosixSuppressibleExit``.  Still
surviving on 5.3.15 (parity, unchanged): ``unset 1bad`` (rc 0, silent), a bad
signal spec to ``trap``, ``declare`` of a readonly (not special),
``command``-stripped and subshell-contained exits.  Gate triage node family
C242 (Wave 0.3).

Diagnostics carry different shell-name prefixes and wording, so these rows
compare stdout + exit code and only require stderr-presence agreement
(the ``check_behavior`` pattern of test_readonly_conformance.py).

Deliberately NOT pinned here: bare ``r=2`` on a readonly under ``-c``
(bash's -c mode exits 127 via an internal artifact where its own file and
stdin modes — and psh everywhere — exit 1; see the integration pins in
tests/integration/test_posix_special_builtin_exit.py).

Reproduce one 5.3 row by hand (oracle = the resolved bash 5.3.15)::

    /opt/homebrew/bin/bash -c 'set -o posix; export 1bad=x; echo survived'
    echo rc=$?                                  # (no stdout) rc=1
    python -m psh -c 'set -o posix; export 1bad=x; echo survived'
    echo rc=$?                                  # (no stdout) rc=1
"""


import pytest
from conformance_framework import ConformanceTest
from divergence_pins import MODES, run_in_mode
from shell_oracle import is_comparable, run_bash, run_psh


def _assert_parity(command, *, tmp_path, stdout, status, diagnoses=True):
    """Equality pin for one command in -c, script-file and stdin modes (D6).

    Flipped from a slot-2.2 declared divergence, so it keeps the three-mode
    coverage AND the literal expectation: both shells must produce exactly
    ``(stdout, status)``.  Naming the value (rather than only comparing the
    two shells) keeps an oracle that stopped exiting here visible as oracle
    drift instead of silently agreeing with a psh regression.  stderr is
    compared by PRESENCE (shell-name prefixes and wording differ).
    """
    for mode in MODES:
        b = run_in_mode(run_bash, mode, command, tmp_path, "oracle")
        p = run_in_mode(run_psh, mode, command, tmp_path, "psh")
        assert is_comparable(b), b
        assert is_comparable(p), p
        assert (b.stdout, b.returncode) == (stdout, status), (
            f"[{mode}] ORACLE side moved for {command!r}: "
            f"bash {b.stdout!r} rc={b.returncode} (oracle drift -> "
            f"re-baseline, do not edit in place)")
        assert (p.stdout, p.returncode) == (stdout, status), (
            f"[{mode}] psh diverged for {command!r}: "
            f"psh {p.stdout!r} rc={p.returncode}")
        assert bool(b.stderr) is diagnoses and bool(p.stderr) is diagnoses, (
            f"[{mode}] stderr presence for {command!r}: "
            f"bash={b.stderr!r} psh={p.stderr!r}")


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


@pytest.mark.oracle_min("5.3")
class TestPosixSpecialBuiltinExitParity:
    """The bash 5.3 OPERAND-error exits and the transparent eval/dot
    boundary, pinned as EQUALITY rows in three input modes.

    These were the Wave 0.3 declared divergences (FLIP-PINS slot 2.2, gate
    rows G18-G22 and W0-N25); slot 2.2 made psh follow bash 5.3 and flipped
    them here.  Values are the 5.3.15 probes of 2026-09-07.
    """

    # -- operand errors that EXIT (status 1) -------------------------------

    def test_export_bad_identifier_exits_in_posix(self, tmp_path):
        _assert_parity("set -o posix; export 1bad=x; echo rc=$?",
                       stdout="", status=1, tmp_path=tmp_path)

    def test_readonly_bad_identifier_exits_in_posix(self, tmp_path):
        _assert_parity("set -o posix; readonly 1bad=x; echo rc=$?",
                       stdout="", status=1, tmp_path=tmp_path)

    def test_readonly_bare_bad_identifier_exits_in_posix(self, tmp_path):
        _assert_parity("set -o posix; readonly 1bad; echo rc=$?",
                       stdout="", status=1, tmp_path=tmp_path)

    def test_unset_readonly_exits_in_posix(self, tmp_path):
        _assert_parity("set -o posix; readonly r=1; unset r; echo rc=$?",
                       stdout="", status=1, tmp_path=tmp_path)

    def test_unset_readonly_function_exits_in_posix(self, tmp_path):
        # W0-N25.  The wording halves also agree now: both shells say
        # "unset: f: cannot unset: readonly function".
        _assert_parity(
            "set -o posix; f() { :; }; readonly -f f; unset -f f; echo rc=$?",
            stdout="", status=1, tmp_path=tmp_path)

    def test_unset_readonly_array_element_exits_in_posix(self, tmp_path):
        _assert_parity(
            "set -o posix; declare -a a=(1 2); readonly a; unset 'a[0]'; "
            "echo rc=$?",
            stdout="", status=1, tmp_path=tmp_path)

    def test_export_stops_at_first_bad_identifier(self, tmp_path):
        # ONE diagnostic, then the exit: the second operand is never reached.
        _assert_parity("set -o posix; export 1bad=x 2bad=y; echo survived",
                       stdout="", status=1, tmp_path=tmp_path)

    def test_unset_reports_every_readonly_operand_then_exits(self, tmp_path):
        # unset is NOT in the stop-at-first class: both operands are
        # diagnosed and the exit happens after the loop.
        _assert_parity(
            "set -o posix; readonly r=1 s=2; unset r s; echo survived",
            stdout="", status=1, tmp_path=tmp_path)

    # -- the exit is suppressible by a guard OUTSIDE an eval/dot boundary --

    def test_outer_guard_suppresses_across_eval(self, tmp_path):
        # bash 5.2 exited 2 here (the guard outside eval did not suppress).
        _assert_parity(
            "set -o posix; eval 'set -q' || echo caught; echo survived",
            stdout="caught\nsurvived\n", status=0, tmp_path=tmp_path)

    def test_if_guard_suppresses_across_eval(self, tmp_path):
        _assert_parity(
            "set -o posix; if eval 'set -q'; then echo T; else echo F; fi; "
            "echo survived",
            stdout="F\nsurvived\n", status=0, tmp_path=tmp_path)

    def test_outer_guard_suppresses_across_dot(self, tmp_path):
        # The dot file is written into the runner's fresh temp cwd.
        _assert_parity(
            "printf 'set -q\\n' > d.sh; set -o posix; . ./d.sh || echo caught; "
            "echo survived",
            stdout="caught\nsurvived\n", status=0, tmp_path=tmp_path)

    def test_outer_guard_suppresses_operand_exit_across_eval(self, tmp_path):
        _assert_parity(
            "set -o posix; eval 'export 1bad=x' || echo caught; echo survived",
            stdout="caught\nsurvived\n", status=0, tmp_path=tmp_path)

    def test_unguarded_operand_exit_across_eval_still_exits(self, tmp_path):
        # Discriminator for the row above: the suppression is the guard's
        # doing, not the eval boundary's.
        _assert_parity("set -o posix; eval 'export 1bad=x'; echo survived",
                       stdout="", status=1, tmp_path=tmp_path)

    # -- the one boundary the suppression does NOT cross: a trap action ----

    def test_outer_guard_does_not_suppress_into_a_trap_action(self, tmp_path):
        _assert_parity(
            "set -o posix; trap 'set -q' DEBUG; false || echo caught; "
            "echo survived",
            stdout="", status=2, tmp_path=tmp_path)

    def test_guard_inside_a_trap_action_still_suppresses(self, tmp_path):
        _assert_parity(
            "set -o posix; trap 'set -q || echo in' EXIT; echo body",
            stdout="body\nin\n", status=0, tmp_path=tmp_path)

    def test_operand_exit_inside_a_trap_action_exits(self, tmp_path):
        _assert_parity(
            "set -o posix; trap 'export 1bad=x; echo after' EXIT; echo body",
            stdout="body\n", status=1, tmp_path=tmp_path)


class TestPosixSpecialBuiltinNoExit(_StatusConformance):
    """Rows that still SURVIVE on bash 5.3.15 (parity): the operand errors
    5.3 left alone, and stripped/contained contexts."""

    def test_trap_bad_signal_survives(self):
        self._assert_same_stdout_and_status(
            "set -o posix; trap 'x' NOSUCHSIG; echo rc=$?")

    def test_unset_bad_identifier_survives(self):
        # bash 5.3 still treats `unset 1bad` as a silent rc-0 no-op.
        self._assert_same_stdout_and_status(
            "set -o posix; unset 1bad; echo rc=$?")

    def test_declare_readonly_assignment_survives(self):
        # declare is not a POSIX special builtin.
        self._assert_same_stdout_and_status(
            "set -o posix; readonly r=1; declare r=2; echo rc=$?")

    def test_export_guard_suppresses_bad_identifier_exit(self):
        # The 5.3 identifier exit is SUPPRESSIBLE class: a direct guard
        # catches it in both shells.
        self._assert_same_stdout_and_status(
            "set -o posix; export 1bad=x || echo caught; echo survived")

    def test_unset_guard_suppresses_readonly_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; readonly r=1; unset r || echo caught; echo survived")

    def test_readonly_f_operand_is_exempt(self):
        # `readonly -f`/`unset -f` NAME operands never take the identifier
        # exit — bash reports and continues (the wording differs, so only
        # stdout/status/stderr-presence are compared).
        self._assert_same_stdout_and_status(
            "set -o posix; readonly -f 1bad; echo rc=$?")

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

    def test_command_strips_bad_identifier_exit(self):
        # `command export` strips the 5.3 identifier exit too: rc 1, continue.
        # The operand loop still stops at the first bad name (that half
        # belongs to posix mode, not to the exit).
        self._assert_same_stdout_and_status(
            "set -o posix; command export 1bad=x; echo rc=$?")

    def test_command_strips_unset_readonly_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; readonly r=1; command unset r; echo rc=$?")

    def test_unset_non_array_subscript_survives(self):
        # An operand error 5.3 did NOT make fatal: rc 1, the shell lives.
        self._assert_same_stdout_and_status(
            "set -o posix; a=1; unset 'a[1]'; echo rc=$?")

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
    errexit-exempt contexts (through functions; on bash 5.3 also across
    eval/dot — see TestPosixSpecialBuiltinExitParity); dot-file and
    readonly-assignment exits are hard even when guarded."""

    def test_or_guard_suppresses_invalid_option(self):
        self._assert_same_stdout_and_status(
            "set -o posix; set -q || echo caught; echo rc=$?")

    def test_if_guard_suppresses_through_function(self):
        self._assert_same_stdout_and_status(
            "set -o posix; f() { set -q; }; if f; then echo T; else echo F; fi")

    def test_hard_dot_missing_guarded_still_exits(self):
        self._assert_same_stdout_and_status(
            "set -o posix; if . /nonexistent/psh-conf-sup; then echo T; fi; echo x")
