"""POSIX-mode special-builtin exit-on-error conformance (bash 5.3.15).

Live re-check of docs/reviews/posix_special_builtin_exit_matrix_2026-07-07.md
against the host bash: with ``set -o posix`` a non-interactive shell exits
on a special builtin's USAGE/SYNTAX error (invalid option, top-level
``return``, missing dot file, ``eval`` syntax error, readonly assignment)
with the builtin's own status.  ``command`` strips the exit;
subshells/command substitution contain it.

BASH 5.3 WIDENED THE EXIT SET (CHANGES 5.3-alpha section 1 item jj: "POSIX
special builtins now exit the shell in posix mode on more failure cases";
item nnnnn: "Fix posix-mode cases where failure of special builtins did not
cause the shell to exit").  Probed on 5.3.15 in -c, script-file and stdin
modes: ``export``/``readonly`` with an invalid identifier and ``unset`` of a
readonly variable or function now EXIT (status 1, at the FIRST bad operand),
and the exit is SUPPRESSIBLE by a guard OUTSIDE an ``eval`` or ``.`` boundary
(``eval 'set -q' || echo caught`` now prints ``caught``).  Under bash 5.2
those operand errors continued (status 1) and the eval/dot boundary reset
suppression; the matrix doc rows 48/49/51 and its "eval/dot boundaries
reset suppression" sentence describe 5.2.  psh still implements the 5.2
shape.  Those rows are pinned BOTH SIDES in
``TestPosixSpecialBuiltinExitDeclaredDivergence``: bash 5.3 semantics; psh to
follow in slot 2.2, which moves each row into ``TestPosixSpecialBuiltinExit``
/ ``TestPosixSuppressibleExit`` as a parity row.  Still surviving on 5.3.15
(parity, unchanged): ``unset 1bad`` (rc 0, silent), a bad signal spec to
``trap``, ``declare`` of a readonly (not special), ``command``-stripped and
subshell-contained exits.  Gate triage node family C242 (Wave 0.3).

Diagnostics carry different shell-name prefixes and wording, so these rows
compare stdout + exit code and only require stderr-presence agreement
(the ``check_behavior`` pattern of test_readonly_conformance.py).

Deliberately NOT pinned here: bare ``r=2`` on a readonly under ``-c``
(bash's -c mode exits 127 via an internal artifact where its own file and
stdin modes — and psh everywhere — exit 1; see the integration pins in
tests/integration/test_posix_special_builtin_exit.py).

Reproduce one divergence row by hand (oracle = the resolved bash 5.3.15)::

    /opt/homebrew/bin/bash -c 'set -o posix; export 1bad=x; echo survived'
    echo rc=$?                                  # (no stdout) rc=1
    python -m psh -c 'set -o posix; export 1bad=x; echo survived'
    echo rc=$?                                  # survived / rc=0
"""


from conformance_framework import ConformanceTest
from shell_oracle import is_comparable, run_bash, run_psh

MODES = ("command", "script", "stdin")


def _run_mode(runner, mode, command, tmp_path, tag):
    """One command in one input mode through the shell-oracle runner.

    ``runner`` is ``run_psh`` / ``run_bash`` (a callable, never a shell-name
    string); ``tag`` only names the temp script file.
    """
    if mode == "command":
        return runner(["-c", command])
    if mode == "script":
        path = tmp_path / f"{tag}.sh"
        path.write_text(command + "\n")
        return runner([str(path)])
    return runner([], stdin_data=command + "\n", stdin_mode="pipe")


def _assert_declared_divergence(command, *, bash, psh, tmp_path):
    """Both-sides pin in every input mode (D6).

    ``bash``/``psh`` are the expected ``(stdout, exit status)`` of each side.
    Red the moment EITHER side moves: an oracle mismatch means the oracle
    drifted (re-baseline, do not edit in place); a psh mismatch means the
    slot 2.2 fix landed and the row must become a parity row.  Both sides
    must diagnose (stderr-presence agreement, as in ``_StatusConformance``).
    """
    for mode in MODES:
        b = _run_mode(run_bash, mode, command, tmp_path, "oracle")
        p = _run_mode(run_psh, mode, command, tmp_path, "psh")
        assert is_comparable(b), b
        assert is_comparable(p), p
        assert (b.stdout, b.returncode) == bash, (
            f"[{mode}] ORACLE side moved for {command!r}: "
            f"bash {b.stdout!r} rc={b.returncode}, expected {bash}")
        assert (p.stdout, p.returncode) == psh, (
            f"[{mode}] PSH side moved for {command!r} (slot 2.2 landed? flip "
            f"this row): psh {p.stdout!r} rc={p.returncode}, expected {psh}")
        assert bool(p.stderr) == bool(b.stderr), (
            f"[{mode}] stderr-presence disagreement for {command!r}: "
            f"psh={p.stderr!r} bash={b.stderr!r}")


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


class TestPosixSpecialBuiltinExitDeclaredDivergence:
    """DECLARED DIVERGENCES, both sides pinned in three input modes.

    bash 5.3 semantics (CHANGES 5.3-alpha 1.jj / 1.nnnnn); psh to follow in
    slot 2.2.  Each row asserts bash 5.3.15's ``(stdout, status)`` AND psh's
    current ``(stdout, status)``; the 2.2 flip moves the row into
    ``TestPosixSpecialBuiltinExit`` or ``TestPosixSuppressibleExit`` as a
    parity row.  Values are the 5.3.15 probes of 2026-09-06.
    """

    # -- operand errors that now EXIT (status 1, first bad operand) --------

    def test_export_bad_identifier_exits_in_posix(self, tmp_path):
        # bash: exits 1, nothing printed; psh: reports, continues, rc 1.
        _assert_declared_divergence(
            "set -o posix; export 1bad=x; echo rc=$?",
            bash=("", 1), psh=("rc=1\n", 0), tmp_path=tmp_path)

    def test_readonly_bad_identifier_exits_in_posix(self, tmp_path):
        _assert_declared_divergence(
            "set -o posix; readonly 1bad=x; echo rc=$?",
            bash=("", 1), psh=("rc=1\n", 0), tmp_path=tmp_path)

    def test_unset_readonly_exits_in_posix(self, tmp_path):
        _assert_declared_divergence(
            "set -o posix; readonly r=1; unset r; echo rc=$?",
            bash=("", 1), psh=("rc=1\n", 0), tmp_path=tmp_path)

    def test_unset_readonly_function_exits_in_posix(self, tmp_path):
        # bash 5.3.15 stderr: "unset: f: cannot unset: readonly function";
        # psh: "unset: f: readonly function" (wording gap noted for 2.2).
        _assert_declared_divergence(
            "set -o posix; f() { :; }; readonly -f f; unset -f f; echo rc=$?",
            bash=("", 1), psh=("rc=1\n", 0), tmp_path=tmp_path)

    def test_export_stops_at_first_bad_identifier(self, tmp_path):
        # bash diagnoses ONLY `1bad=x` and exits; psh diagnoses both operands
        # and continues.
        _assert_declared_divergence(
            "set -o posix; export 1bad=x 2bad=y; echo survived",
            bash=("", 1), psh=("survived\n", 0), tmp_path=tmp_path)

    # -- the exit is suppressible by a guard OUTSIDE an eval/dot boundary --

    def test_outer_guard_suppresses_across_eval(self, tmp_path):
        # Was test_eval_boundary_not_suppressed (bash 5.2: the guard outside
        # eval did NOT suppress; both exited 2).  bash 5.3: caught/survived.
        _assert_declared_divergence(
            "set -o posix; eval 'set -q' || echo caught; echo survived",
            bash=("caught\nsurvived\n", 0), psh=("", 2), tmp_path=tmp_path)

    def test_if_guard_suppresses_across_eval(self, tmp_path):
        _assert_declared_divergence(
            "set -o posix; if eval 'set -q'; then echo T; else echo F; fi; "
            "echo survived",
            bash=("F\nsurvived\n", 0), psh=("", 2), tmp_path=tmp_path)

    def test_outer_guard_suppresses_across_dot(self, tmp_path):
        # The dot file is written into the runner's fresh temp cwd.
        _assert_declared_divergence(
            "printf 'set -q\\n' > d.sh; set -o posix; . ./d.sh || echo caught; "
            "echo survived",
            bash=("caught\nsurvived\n", 0), psh=("", 2), tmp_path=tmp_path)


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
        # The new 5.3 exit is SUPPRESSIBLE class: a direct guard catches it
        # in both shells (psh never exited here, so this is parity today and
        # stays parity after slot 2.2).
        self._assert_same_stdout_and_status(
            "set -o posix; export 1bad=x || echo caught; echo survived")

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
        self._assert_same_stdout_and_status(
            "set -o posix; command export 1bad=x; echo rc=$?")

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
    eval/dot — see the declared-divergence class); dot-file and
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
