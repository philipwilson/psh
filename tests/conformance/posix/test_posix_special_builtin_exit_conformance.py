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
from divergence_pins import MODES, assert_declared_divergence, run_in_mode
from shell_oracle import is_comparable, run_bash, run_psh


def _assert_parity(command, *, tmp_path, stdout, status, diagnoses=True,
                   diag_lines=None):
    """Equality pin for one command in -c, script-file and stdin modes (D6).

    Flipped from a slot-2.2 declared divergence, so it keeps the three-mode
    coverage AND the literal expectation: both shells must produce exactly
    ``(stdout, status)``.  Naming the value (rather than only comparing the
    two shells) keeps an oracle that stopped exiting here visible as oracle
    drift instead of silently agreeing with a psh regression.  stderr is
    compared by PRESENCE (shell-name prefixes and wording differ).

    ``diag_lines`` additionally pins HOW MANY diagnostic lines each shell
    prints.  Exit rows need it: the operand-loop rule ("export stops at the
    first bad identifier" vs "unset diagnoses every operand") is invisible in
    (stdout, status), because the diagnostics go to stderr and the exit
    status is 1 either way.  Only rows whose wording already matches
    line-for-line can use it — an invalid-OPTION row cannot, since bash adds
    a usage line psh does not print (the separate C200 family).
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
        if diag_lines is not None:
            counts = (len(b.stderr.splitlines()), len(p.stderr.splitlines()))
            assert counts == (diag_lines, diag_lines), (
                f"[{mode}] diagnostic-line count for {command!r}: "
                f"bash={counts[0]} psh={counts[1]}, expected {diag_lines}\n"
                f"  bash stderr: {b.stderr!r}\n  psh stderr: {p.stderr!r}")


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
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_readonly_bad_identifier_exits_in_posix(self, tmp_path):
        _assert_parity("set -o posix; readonly 1bad=x; echo rc=$?",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_readonly_bare_bad_identifier_exits_in_posix(self, tmp_path):
        _assert_parity("set -o posix; readonly 1bad; echo rc=$?",
                       stdout="", status=1, tmp_path=tmp_path)

    def test_unset_readonly_exits_in_posix(self, tmp_path):
        _assert_parity("set -o posix; readonly r=1; unset r; echo rc=$?",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_unset_readonly_function_exits_in_posix(self, tmp_path):
        # W0-N25.  The wording halves also agree now: both shells say
        # "unset: f: cannot unset: readonly function".
        _assert_parity(
            "set -o posix; f() { :; }; readonly -f f; unset -f f; echo rc=$?",
            stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_unset_readonly_array_element_exits_in_posix(self, tmp_path):
        _assert_parity(
            "set -o posix; declare -a a=(1 2); readonly a; unset 'a[0]'; "
            "echo rc=$?",
            stdout="", status=1, tmp_path=tmp_path)

    def test_unset_readonly_scalar_subscript_exits_in_posix(self, tmp_path):
        # READONLY outranks the "not an array variable" shape complaint: bash
        # reports the refusal for a subscripted readonly scalar and exits.
        _assert_parity(
            "set -o posix; readonly r=1; unset 'r[1]'; echo rc=$?",
            stdout="", status=1, tmp_path=tmp_path)

    def test_export_stops_at_first_bad_identifier(self, tmp_path):
        # ONE diagnostic, then the exit: the second operand is never reached.
        _assert_parity("set -o posix; export 1bad=x 2bad=y; echo survived",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_unset_f_reports_every_readonly_function_then_exits(self, tmp_path):
        _assert_parity(
            "set -o posix; f() { :; }; g() { :; }; readonly -f f g; "
            "unset -f f g; echo survived",
            stdout="", status=1, diag_lines=2, tmp_path=tmp_path)

    def test_unset_reports_every_readonly_operand_then_exits(self, tmp_path):
        # unset is NOT in the stop-at-first class: both operands are
        # diagnosed and the exit happens after the loop.
        _assert_parity(
            "set -o posix; readonly r=1 s=2; unset r s; echo survived",
            stdout="", status=1, diag_lines=2, tmp_path=tmp_path)

    def test_unset_v_bad_identifier_exits_in_posix(self, tmp_path):
        # W0-N32.  An explicit `-v` identifier-checks every operand; without
        # it bash falls back to a function lookup and stays silent (the
        # `unset 1bad` row in TestPosixSpecialBuiltinNoExit).
        _assert_parity("set -o posix; unset -v 1bad; echo survived",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_unset_v_reports_every_bad_identifier_then_exits(self, tmp_path):
        # Like the readonly refusals and unlike export/readonly's identifier
        # error, the unset operand loop is NOT truncated.
        _assert_parity("set -o posix; unset -v 1bad 2bad; echo survived",
                       stdout="", status=1, diag_lines=2, tmp_path=tmp_path)

    def test_unset_v_mixes_identifier_and_readonly_refusals(self, tmp_path):
        _assert_parity(
            "set -o posix; readonly r=1; unset -v a-b r; echo survived",
            stdout="", status=1, diag_lines=2, tmp_path=tmp_path)

    def test_unset_v_subscripted_operand_judged_on_its_base_name(self, tmp_path):
        _assert_parity("set -o posix; unset -v '1a[0]'; echo survived",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_unset_v_trailing_junk_after_the_subscript_is_a_bad_name(
            self, tmp_path):
        _assert_parity("set -o posix; unset -v 'a[0]x'; echo survived",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_unset_v_empty_operand_is_a_bad_name(self, tmp_path):
        _assert_parity("set -o posix; unset -v ''; echo survived",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_unset_v_unicode_operand_is_a_bad_name_in_posix(self, tmp_path):
        # The `-v` name check consults POSIX MODE, like every other identifier
        # site: `é` is refused here and accepted outside posix (psh's
        # documented Unicode extension — the default-mode half is
        # test_identifier_policy_conformance.py::
        # TestUnicodeAcceptedWithoutPosixDivergence::test_unset_v_accepted_by_psh).
        # Diagnostics render differently by locale, so only stdout, status and
        # the line count are compared.
        _assert_parity("set -o posix; unset -v é; echo survived",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    # -- ACTUAL TARGETS (D3): the operands the rules leave alone or apply ----

    def test_export_applies_operands_before_the_first_bad_identifier(
            self, tmp_path):
        # The stop rule read off the variables themselves, not off a status:
        # A really carries the export attribute, B was never created.
        _assert_parity(
            "set -o posix; export A=1 1bad=x B=2 || echo caught; "
            "echo \"B=${B-unset}\"; declare -p A",
            stdout='caught\nB=unset\ndeclare -x A="1"\n', status=0,
            diag_lines=1, tmp_path=tmp_path)

    def test_readonly_applies_operands_before_the_first_bad_identifier(
            self, tmp_path):
        _assert_parity(
            "set -o posix; readonly A=1 1bad B=2 || echo caught; "
            "echo \"B=${B-unset}\"; declare -p A",
            stdout='caught\nB=unset\ndeclare -r A="1"\n', status=0,
            diag_lines=1, tmp_path=tmp_path)

    def test_unset_v_unsets_the_operands_after_a_bad_one(self, tmp_path):
        # The mirror image: unset does NOT truncate, so `d` after the bad
        # operand is really gone.
        _assert_parity(
            "set -o posix; a=1 d=1; unset -v a b-c d || echo caught; "
            "echo \"a=[${a-unset}] d=[${d-unset}]\"; echo survived",
            stdout="caught\na=[unset] d=[unset]\nsurvived\n", status=0,
            diag_lines=1, tmp_path=tmp_path)

    def test_readonly_stops_at_first_bad_identifier(self, tmp_path):
        _assert_parity("set -o posix; readonly 1bad 2bad; echo survived",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_readonly_stops_before_a_later_good_operand(self, tmp_path):
        _assert_parity("set -o posix; readonly 1bad A=1; echo survived",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    # -- $? seen by the EXIT trap is the builtin's status, not 0 ------------

    def test_exit_trap_sees_the_operand_status(self, tmp_path):
        _assert_parity(
            "set -o posix; trap 'echo trap rc=$?' EXIT; export 1bad=x; "
            "echo survived",
            stdout="trap rc=1\n", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_exit_trap_sees_the_unset_readonly_status(self, tmp_path):
        _assert_parity(
            "set -o posix; trap 'echo trap rc=$?' EXIT; readonly r=1; "
            "unset r; echo survived",
            stdout="trap rc=1\n", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_exit_trap_sees_the_unset_v_identifier_status(self, tmp_path):
        _assert_parity(
            "set -o posix; trap 'echo trap rc=$?' EXIT; unset -v 1bad; "
            "echo survived",
            stdout="trap rc=1\n", status=1, diag_lines=1, tmp_path=tmp_path)

    def test_exit_trap_sees_the_invalid_option_status_2(self, tmp_path):
        # The usage class carries 2, so the trap must not see 1 either.
        # (bash prints a usage line psh does not, so no diag_lines here.)
        _assert_parity(
            "set -o posix; trap 'echo trap rc=$?' EXIT; set -q; echo survived",
            stdout="trap rc=2\n", status=2, tmp_path=tmp_path)

    def test_suppressed_exit_leaves_the_trap_status_alone(self, tmp_path):
        # Discriminator: publishing the status must NOT happen when a guard
        # suppresses the exit — the shell runs on and ends successfully.
        _assert_parity(
            "set -o posix; trap 'echo trap rc=$?' EXIT; set -q || echo caught; "
            "echo survived",
            stdout="caught\nsurvived\ntrap rc=0\n", status=0,
            tmp_path=tmp_path)

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


@pytest.mark.oracle_min("5.3")
class TestErrTrapDefeatsTheExitInBashOnly:
    """DECLARED DIVERGENCE (ledger row W1-N55): with an ERR trap installed,
    bash 5.3.15 runs the action and does NOT take the posix special-builtin
    exit; psh exits.  Both sides pinned, in three input modes.

    Not a rule psh emulates, because bash's behaviour here is an
    IMPLEMENTATION ACCIDENT rather than a documented semantic.  No CHANGES or
    NEWS item covers it — the 5.3 items this file cites elsewhere (bash-5.3-alpha
    "1. Changes to Bash" jj and nnnnn) say nothing about ERR — so the
    provenance is "empirical, 5.3.15", and the shape of the accident is visible
    in the discriminators: an action that runs no simple command IN THE PARENT
    still exits, while any action that does runs and clears the pending exit.
    Probed on 5.3.15, `export 1bad=x` under `set -o posix` in all three modes::

        trap '' ERR       -> exits 1      trap ':' ERR      -> survives
        trap ' ' ERR      -> exits 1      trap 'true' ERR   -> survives
        trap '# c' ERR    -> exits 1      trap 'x=1' ERR    -> survives
        trap '(true)' ERR -> exits 1      trap '{ :; }' ERR -> survives

    i.e. bash's "a special builtin failed" flag is cleared by the first simple
    command the action runs in the parent, so the pending exit is lost; a
    subshell action cannot clear it.  Emulating that faithfully would mean
    encoding "did the trap action run a simple command in the parent" into the
    exit policy, which is not a rule any script should rely on.

    The HARD class is unaffected in both shells (rows below), and `set -e` plus
    an ERR trap still exits in bash — the accident only reaches the
    SUPPRESSIBLE class.  psh's behaviour is stated in
    docs/user_guide/17_differences_from_bash.md §17.
    """

    def _pin(self, command, *, bash, psh, tmp_path):
        assert_declared_divergence(command, bash=bash, psh=psh,
                                   tmp_path=tmp_path, slot="2.2")

    def test_err_trap_defeats_the_export_identifier_exit(self, tmp_path):
        self._pin("set -o posix; trap 'echo err rc=$?' ERR; export 1bad=x; "
                  "echo survived",
                  bash=("err rc=1\nsurvived\n", 0), psh=("", 1),
                  tmp_path=tmp_path)

    def test_err_trap_defeats_the_readonly_identifier_exit(self, tmp_path):
        self._pin("set -o posix; trap 'echo err rc=$?' ERR; readonly 1bad; "
                  "echo survived",
                  bash=("err rc=1\nsurvived\n", 0), psh=("", 1),
                  tmp_path=tmp_path)

    def test_err_trap_defeats_the_unset_readonly_exit(self, tmp_path):
        self._pin("set -o posix; trap 'echo err rc=$?' ERR; readonly r=1; "
                  "unset r; echo survived",
                  bash=("err rc=1\nsurvived\n", 0), psh=("", 1),
                  tmp_path=tmp_path)

    def test_err_trap_defeats_the_unset_v_identifier_exit(self, tmp_path):
        self._pin("set -o posix; trap 'echo err rc=$?' ERR; unset -v 1bad; "
                  "echo survived",
                  bash=("err rc=1\nsurvived\n", 0), psh=("", 1),
                  tmp_path=tmp_path)

    def test_err_trap_defeats_the_invalid_option_exit(self, tmp_path):
        self._pin("set -o posix; trap 'echo err rc=$?' ERR; set -q; "
                  "echo survived",
                  bash=("err rc=2\nsurvived\n", 0), psh=("", 2),
                  tmp_path=tmp_path)

    def test_err_trap_does_not_defeat_the_stop_at_first_rule(self, tmp_path):
        # Only the EXIT is lost: `2bad=y` is still never diagnosed, so bash
        # prints ONE `err` for the one failing command.
        self._pin("set -o posix; trap 'echo err' ERR; export 1bad=x 2bad=y; "
                  "echo survived",
                  bash=("err\nsurvived\n", 0), psh=("", 1),
                  tmp_path=tmp_path)

    # -- discriminators: the accident's shape, and where it does NOT reach --

    @pytest.mark.parametrize("action", ["", " ", "# c", "(true)"],
                             ids=["empty", "blank", "comment", "subshell"])
    def test_action_with_no_parent_simple_command_still_exits(self, action,
                                                              tmp_path):
        # Equality rows: these actions never clear bash's flag, so BOTH shells
        # exit 1.  They are what makes the divergence an accident rather than
        # a rule about ERR traps.
        _assert_parity(f"set -o posix; trap '{action}' ERR; export 1bad=x; "
                       "echo survived",
                       stdout="", status=1, diag_lines=1, tmp_path=tmp_path)

    @pytest.mark.parametrize("case,status", [
        (". /nonexistent/psh-conf-errtrap", 1),
        ("readonly r=1; readonly r=2", 1),
        ("eval 'if'", 2),
    ], ids=["dot-missing", "readonly-assign", "eval-syntax"])
    def test_hard_class_exits_with_an_err_trap_in_both_shells(self, case,
                                                              status,
                                                              tmp_path):
        # The accident reaches only the SUPPRESSIBLE class: the hard class
        # exits without running the action, in both shells.
        _assert_parity(f"set -o posix; trap 'echo err' ERR; {case}; "
                       "echo survived",
                       stdout="", status=status, tmp_path=tmp_path)


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

    def test_readonly_guard_suppresses_bad_identifier_exit(self):
        # The readonly twin of the export row above: its identifier exit is
        # the SUPPRESSIBLE class too, in every guard shape.
        self._assert_same_stdout_and_status(
            "set -o posix; readonly 1bad || echo caught; echo survived")

    def test_readonly_if_guard_suppresses_bad_identifier_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; if readonly 1bad; then echo T; else echo F; fi; "
            "echo survived")

    def test_readonly_guard_suppresses_through_a_function(self):
        self._assert_same_stdout_and_status(
            "set -o posix; f() { readonly 1bad=x; }; f || echo caught; "
            "echo survived")

    def test_export_if_guard_suppresses_bad_identifier_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; if export 1bad=x; then echo T; else echo F; fi; "
            "echo survived")

    def test_export_guard_suppresses_through_a_function(self):
        self._assert_same_stdout_and_status(
            "set -o posix; f() { export 1bad=x; }; f || echo caught; "
            "echo survived")

    def test_unset_v_guard_suppresses_identifier_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; unset -v 1bad || echo caught; echo survived")

    def test_unset_v_if_guard_suppresses_identifier_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; if unset -v 1bad; then echo T; else echo F; fi; "
            "echo survived")

    def test_unset_v_guard_suppresses_through_a_function(self):
        self._assert_same_stdout_and_status(
            "set -o posix; f() { unset -v 1bad; }; f || echo caught; "
            "echo survived")

    def test_command_strips_unset_v_identifier_exit(self):
        self._assert_same_stdout_and_status(
            "set -o posix; command unset -v 1bad; echo rc=$?")

    def test_bare_unset_bad_identifier_still_silent(self):
        # Without -v bash falls back to a FUNCTION lookup, so the word is
        # never judged as a variable name: silent, rc 0, no exit.
        self._assert_same_stdout_and_status(
            "set -o posix; unset 1bad a-b; echo rc=$?")

    def test_unset_f_bad_identifier_still_silent(self):
        self._assert_same_stdout_and_status(
            "set -o posix; unset -f 1bad; echo rc=$?")

    def test_unset_n_bad_identifier_still_silent(self):
        self._assert_same_stdout_and_status(
            "set -o posix; unset -n 1bad; echo rc=$?")

    def test_unset_v_subscripted_good_name_survives(self):
        # `a[0]` is judged on its base name, so it is a normal element unset.
        self._assert_same_stdout_and_status(
            "set -o posix; declare -a a=(1 2); unset -v 'a[0]'; "
            "echo \"left=${a[*]} rc=$?\"")

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
