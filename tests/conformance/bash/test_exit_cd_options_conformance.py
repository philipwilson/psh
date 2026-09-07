"""Conformance tests for `exit` status semantics and `cd -L/-P` (R14.A).

`exit` (verified vs bash 5.3.15):
  - bare `exit` uses $? (the last command's status), not 0;
  - a numeric argument wraps modulo 256 (`exit 257`->1, `exit -1`->255,
    `exit 300`->44);
  - a non-numeric argument errors with status 2 and the shell CONTINUES on the
    same line (`exit abc; echo rc=$?` prints `rc=2`);
  - too many arguments errors and does NOT exit; the rest of the input line is
    dropped and the next line sees `$?` = 2, while under `-c` both shells
    abandon the rest of the string with process rc 1.

`cd` (verified vs bash 5.3.15):
  - `-L` (default) keeps the logical symlink path; `-P` records the physical
    path; `cd a b` is "too many arguments" (no chdir) with status 2.

USAGE-ERROR STATUS ON BASH 5.3.  The status-1 -> status-2 shift for `cd`,
`exit`, `shift`, `return`, `break` and `continue` usage errors has NO
CHANGES/NEWS item in the 5.3.15 documentation -- it is empirical, probed on
5.3.15 (2026-09-06 and 2026-09-07) in -c, script-file and stdin modes.  The 5.2
series returned 1 for the same cells (the 2026-08-09 gate was green on that
day's 5.2 oracle), and psh followed 5.2 until slot 2.3 adopted the 5.3 family:
one owner, `psh/core/internal_errors.py#special_builtin_usage_discard` and its
two sibling entry points.  Wave 0.3 pinned each row BOTH SIDES as a declared
divergence; every one of those rows is now a PARITY pin that still asserts the
agreed value, so it goes red if psh regresses OR the oracle drifts.  Ledger
rows closed here: G30, G31, W0-N4 (`exit abc` continues), W0-N8 (`shift abc`
status), W0-N9 (next-line status after too many arguments), W0-N10 (`break
abc` / `continue abc` exit the shell with 2), W0-N31 (an abandoned line with
no line after it exits 2).  Gate triage node family C242 (Wave 0.3).

These run in a subprocess through the shell-oracle runner, so the real
process exit code is what's compared.

Reproduce one row by hand (oracle = the resolved bash 5.3.15)::

    /opt/homebrew/bin/bash -c 'cd a b; echo rc=$?'     # rc=2
    python -m psh -c 'cd a b; echo rc=$?'              # rc=2
"""

import pytest
from conformance_framework import ConformanceTest
from divergence_pins import MODES, assert_mode_parity
from shell_oracle import is_comparable, run_bash, run_psh


def _assert_parity(command, *, expected, tmp_path, modes=MODES,
                   stderr_has=None):
    """Slot 2.3 parity pin in the given input modes (D6): the two shells must
    agree AND agree on ``expected``; both must diagnose, and ``stderr_has``
    names the wording fragment both diagnostics carry.  See
    tests/conformance/divergence_pins.py.
    """
    assert_mode_parity(command, expected=expected, tmp_path=tmp_path,
                       modes=modes, stderr_has=stderr_has)


class TestExitStatus(ConformanceTest):
    def test_bare_exit_uses_last_status(self):
        self.assert_identical_behavior('false; exit')

    def test_bare_exit_after_true(self):
        self.assert_identical_behavior('true; exit')

    def test_exit_wraps_over_255(self):
        self.assert_identical_behavior('exit 257')

    def test_exit_wraps_300(self):
        self.assert_identical_behavior('exit 300')

    def test_exit_negative_wraps(self):
        self.assert_identical_behavior('exit -1')

    def test_exit_256_is_zero(self):
        self.assert_identical_behavior('exit 256')

    def test_exit_explicit_code(self):
        self.assert_identical_behavior('exit 42')

    @pytest.mark.oracle_min("5.3")
    def test_exit_too_many_args_does_not_exit(self, tmp_path):
        """W0-N9 / G31, flipped to parity by slot 2.3.

        Both shells report "too many arguments" and KEEP RUNNING, so the
        following line executes -- and the status that line sees is 2
        (empirical, 5.3.15; the 5.2 series gave 1).  Script-file and stdin
        modes only: under ``-c`` the error abandons the rest of the string in
        both shells (see the parity control below), which is a different fact
        from "exit doesn't terminate".
        """
        _assert_parity(
            'exit 1 2 3\necho after=$?',
            expected=('after=2\n', 0), tmp_path=tmp_path,
            modes=("script", "stdin"), stderr_has='too many arguments')

    @pytest.mark.oracle_min("5.3")
    def test_too_many_args_with_no_next_line_exits_two(self, tmp_path):
        """W0-N31, flipped to parity by slot 2.3.

        The sub-row of W0-N9 with NOTHING after the abandoned line: the whole
        input is one line, so the discard leaves $? = 2 with no line left to
        observe it and the shell exits with that status.  Reproduce::

            printf 'f(){ exit 1 2; echo in=$?; }; f; echo out=$?\\n' > s.sh
            bash s.sh; echo $?          # 2
        """
        _assert_parity(
            'f(){ exit 1 2; echo in=$?; }; f; echo out=$?',
            expected=('', 2), tmp_path=tmp_path,
            modes=("script", "stdin"), stderr_has='too many arguments')

    @pytest.mark.oracle_min("5.3")
    def test_too_many_args_no_next_line_exits_two_for_every_verb(self, tmp_path):
        """W0-N31 across the three special builtins that share the cell."""
        for head in ('exit 1 2; echo dropped',
                     'set -- a b c; shift 1 2; echo dropped',
                     'f(){ return 1 2; echo in=$?; }; f; echo out=$?'):
            _assert_parity(
                head, expected=('', 2), tmp_path=tmp_path,
                modes=("script", "stdin"), stderr_has='too many arguments')

    @pytest.mark.oracle_min("5.3")
    def test_discard_is_contained_by_a_substitution_but_not_a_subshell(
            self, tmp_path):
        """The discard's status is channel-dependent at a fork: a command
        substitution child exits 1 where the ``( )`` subshell beside it exits
        with the family's 2 (empirical, 5.3.15).  Backticks behave as ``$( )``.
        """
        _assert_parity(
            '( exit 1 2 )\necho after=$?',
            expected=('after=2\n', 0), tmp_path=tmp_path,
            modes=("script", "stdin"), stderr_has='too many arguments')
        for spelling in ('x=$(exit 1 2)', 'x=`exit 1 2`'):
            _assert_parity(
                f'{spelling}\necho after=$?',
                expected=('after=1\n', 0), tmp_path=tmp_path,
                modes=("script", "stdin"), stderr_has='too many arguments')

    def test_exit_too_many_args_abandons_c_string_in_both(self):
        # Parity control for the row above: -c mode abandons the string with
        # process status 1 in BOTH shells on 5.3.15 (the -c leg is not part
        # of the 5.3 status change).
        cmd = 'exit 1 2 3; echo after=$?'
        psh = run_psh(['-c', cmd])
        assert is_comparable(psh), psh
        bash = run_bash(['-c', cmd])
        assert is_comparable(bash), bash
        assert (psh.stdout, psh.returncode) == (bash.stdout, bash.returncode) \
            == ('', 1)
        assert 'too many arguments' in psh.stderr
        assert 'too many arguments' in bash.stderr

    @pytest.mark.oracle_min("5.3")
    def test_exit_non_numeric_continues(self, tmp_path):
        """W0-N4, flipped to parity by slot 2.3.

        ``exit abc`` prints "exit: abc: numeric argument required", sets ``$?``
        to 2 and CONTINUES with the next command ON THE SAME LINE, in every
        input mode (empirical, 5.3.15; the 5.2 series exited 2).  The second
        row is the shape of golden ``bcontract_exit_bad_first_operand_exits_two``
        and also pins the operand ORDER: a bad first operand is diagnosed
        before the operand count, so ``exit abc 7`` is NOT "too many
        arguments".
        """
        _assert_parity(
            'exit abc; echo rc=$?',
            expected=('rc=2\n', 0), tmp_path=tmp_path,
            stderr_has='numeric argument required')
        _assert_parity(
            'exit abc 7; echo survived',
            expected=('survived\n', 0), tmp_path=tmp_path,
            stderr_has='numeric argument required')

    @pytest.mark.oracle_min("5.3")
    def test_numeric_operand_cell_exits_in_posix_mode(self, tmp_path):
        """The operand cell is a POSIX special-builtin error too: under
        ``set -o posix`` a non-interactive shell EXITS with the same status
        instead of continuing, and an outer guard suppresses that exit
        (empirical, 5.3.15).  This is why the cell raises the typed outcome
        the ONE posix exit policy resolves, rather than returning a status.
        """
        for verb in ('exit abc', 'shift abc'):
            _assert_parity(
                f'set -o posix\n{verb}\necho after=$?',
                expected=('', 2), tmp_path=tmp_path,
                stderr_has='numeric argument required')
            _assert_parity(
                f'set -o posix\n{verb} || echo caught=$?\necho after=$?',
                expected=('caught=2\nafter=0\n', 0), tmp_path=tmp_path,
                stderr_has='numeric argument required')


@pytest.mark.oracle_min("5.3")
class TestUsageStatusMatchesBash:
    """W0-N8 / W0-N9 / W0-N10: the usage-error status family on bash 5.3.15,
    flipped to parity by slot 2.3.  Values are the 5.3.15 probes of 2026-09-06
    and 2026-09-07 (empirical: no CHANGES/NEWS item)."""

    def test_shift_non_numeric_status_2(self, tmp_path):
        # W0-N8: rc 2 and the shell continues on the same line.
        _assert_parity(
            'shift abc; echo rc=$?',
            expected=('rc=2\n', 0), tmp_path=tmp_path,
            stderr_has='numeric argument required')

    def test_shift_bad_first_operand_wins_over_extra(self, tmp_path):
        # The operand ORDER: a bad first operand is diagnosed before the
        # operand count, so `shift x y` is the numeric cell (continue), not
        # the discard cell -- and the positional parameters are untouched.
        _assert_parity(
            'set -- a b c; shift x y; echo "rc=$? n=$#"',
            expected=('rc=2 n=3\n', 0), tmp_path=tmp_path,
            stderr_has='numeric argument required')

    def test_return_bad_first_operand_wins_over_extra(self, tmp_path):
        # Same order for `return`, which psh used to get backwards (it
        # reported "too many arguments" and discarded the line).
        _assert_parity(
            'f(){ return abc 7; echo in=$?; }\nf\necho after=$?',
            expected=('after=2\n', 0), tmp_path=tmp_path,
            stderr_has='numeric argument required')

    def test_too_many_args_next_line_status_2(self, tmp_path):
        # W0-N9: shift/return/exit with too many arguments drop the rest of
        # the input line; the NEXT line sees $?=2.
        # (-c mode: both shells abandon the string with rc 1 -- see
        # test_too_many_args_abandons_c_string_in_both.)
        for head in ('shift 1 2', 'return 1 2', 'exit 7 8'):
            _assert_parity(
                f'{head}\necho rc=$?',
                expected=('rc=2\n', 0), tmp_path=tmp_path,
                modes=("script", "stdin"), stderr_has='too many arguments')

    def test_too_many_args_drops_the_rest_of_the_line(self, tmp_path):
        # The discard is a LINE discard, not a status: the `&&` tail and the
        # commands after the `;` on the same line never run, in every mode
        # (under -c that means the whole string, rc 1).
        _assert_parity(
            'exit 7 8; echo dropped\necho rc=$?',
            expected=('rc=2\n', 0), tmp_path=tmp_path,
            modes=("script", "stdin"), stderr_has='too many arguments')
        _assert_parity(
            'for i in 1 2; do break 1 2; echo dropped; done\necho rc=$?',
            expected=('rc=2\n', 0), tmp_path=tmp_path,
            modes=("script", "stdin"), stderr_has='too many arguments')

    def test_break_continue_non_numeric_exit_2(self, tmp_path):
        # W0-N10: a non-numeric break/continue operand inside a loop EXITS
        # the shell with status 2 in every mode; the following line never
        # runs.
        for verb in ('break', 'continue'):
            _assert_parity(
                f'for i in 1; do {verb} abc; done\necho rc=$?',
                expected=('', 2), tmp_path=tmp_path,
                stderr_has='numeric argument required')

    def test_break_continue_exit_is_not_suppressible(self, tmp_path):
        # Unlike the operand cell, this exit ignores an enclosing guard --
        # `|| echo caught` and an `if` condition both still exit -- and a
        # function body does not contain it either.  Only a fork does: the
        # subshell dies with 2 and the parent runs on.
        _assert_parity(
            'for i in 1; do break abc || echo caught; done\necho rc=$?',
            expected=('', 2), tmp_path=tmp_path,
            stderr_has='numeric argument required')
        _assert_parity(
            'f(){ for i in 1; do break abc; done; }\nf\necho rc=$?',
            expected=('', 2), tmp_path=tmp_path,
            stderr_has='numeric argument required')
        _assert_parity(
            '( for i in 1; do break abc; done )\necho rc=$?',
            expected=('rc=2\n', 0), tmp_path=tmp_path,
            stderr_has='numeric argument required')

    def test_break_out_of_range_and_out_of_loop_cells_are_unchanged(
            self, tmp_path):
        # Neighbours of the bad-count cell that did NOT move in 5.3: a
        # non-positive count is "loop count out of range" (exit all loops,
        # status 1, shell lives), and break with no enclosing loop is a
        # status-0 warning whose argument is not even validated.
        _assert_parity(
            'for i in 1 2; do break 0; echo body; done\necho rc=$?',
            expected=('rc=1\n', 0), tmp_path=tmp_path,
            stderr_has='loop count out of range')
        _assert_parity(
            'break abc\necho rc=$?',
            expected=('rc=0\n', 0), tmp_path=tmp_path,
            stderr_has='only meaningful in')


class TestCdOptions(ConformanceTest):
    @pytest.mark.oracle_min("5.3")
    def test_cd_empty_operand_is_null_directory(self):
        """``cd ""`` is "null directory", rc 1, cwd unchanged, even under CDPATH
        (bash 5.3.15, empirical; 5.2 was a no-op success). Wave 0.3 retune.
        stderr prefixes differ, so stderr goes to /dev/null and stdout + $?
        are compared."""
        self.assert_identical_behavior(
            'cd /usr; cd "" 2>/dev/null; echo "$?:$PWD"; '
            'CDPATH=/tmp cd "" 2>/dev/null; echo "$?:$PWD"; '
            'cd -P "" 2>/dev/null; echo "$?"; x=; cd $x 2>/dev/null; echo "$?"')

    @pytest.mark.oracle_min("5.3")
    def test_cd_too_many_arguments(self, tmp_path):
        """G30, flipped to parity by slot 2.3.

        ``cd a b`` is "too many arguments" with status 2 in every input mode
        (empirical, 5.3.15; the 5.2 series gave 1).  ``cd`` is not a special
        builtin, so unlike ``exit 1 2`` nothing is discarded -- the command
        just fails, which is why the ``&&`` tail below is skipped by ordinary
        short-circuiting and the NEXT line still sees the 2.  The pin asserts
        the real target as well as the status: the working directory is
        unchanged.  stderr banner prefixes differ, so only the tail wording is
        compared.
        """
        _assert_parity(
            'cd a b; echo rc=$?',
            expected=('rc=2\n', 0), tmp_path=tmp_path,
            stderr_has='too many arguments')
        _assert_parity(
            'cd a b && echo tail\necho after=$?',
            expected=('after=2\n', 0), tmp_path=tmp_path,
            stderr_has='too many arguments')
        _assert_parity(
            'here=$(pwd -P); cd a b; [ "$(pwd -P)" = "$here" ] && echo same-cwd',
            expected=('same-cwd\n', 0), tmp_path=tmp_path,
            stderr_has='too many arguments')

    def test_cd_dash_P_is_physical(self):
        # /tmp is a symlink on macOS; -P resolves it. Compare $PWD basename
        # logic via realpath equality, which both shells compute identically.
        self.assert_identical_behavior(
            'cd -P / && [ "$PWD" = "$(pwd -P)" ] && echo physical-ok')

    def test_cd_dash_L_default_logical(self):
        self.assert_identical_behavior('cd -L / && echo $PWD')

    def test_cd_invalid_option(self):
        # Exit code parity (2); stderr prefix differs so not compared here.
        psh = run_psh(['-c', 'cd -Z'])
        assert is_comparable(psh), psh
        bash = run_bash(['-c', 'cd -Z'])
        assert is_comparable(bash), bash
        assert psh.returncode == bash.returncode == 2
