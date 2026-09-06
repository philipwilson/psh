"""Conformance tests for `exit` status semantics and `cd -L/-P` (R14.A).

`exit` (verified vs bash 5.3.15):
  - bare `exit` uses $? (the last command's status), not 0;
  - a numeric argument wraps modulo 256 (`exit 257`→1, `exit -1`→255,
    `exit 300`→44);
  - a non-numeric argument errors with status 2 -- on bash 5.3.15 the shell
    then CONTINUES (`exit abc; echo rc=$?` prints `rc=2`); psh exits 2
    (declared divergence, below);
  - too many arguments errors and does NOT exit; the next input line sees
    `$?` = 2 on bash 5.3.15 where psh reports 1 (declared divergence);
    under `-c` both shells abandon the rest of the string with process rc 1.

`cd` (verified vs bash 5.3.15):
  - `-L` (default) keeps the logical symlink path; `-P` records the physical
    path; `cd a b` is "too many arguments" (no chdir) with status 2 on bash
    5.3.15 where psh reports 1 (declared divergence).

USAGE-ERROR STATUS ON BASH 5.3.  The status-1 -> status-2 shift for `cd`,
`exit`, `shift`, `return`, `break` and `continue` usage errors has NO
CHANGES/NEWS item in the 5.3.15 documentation -- it is empirical, probed on
5.3.15 (2026-09-06) in -c, script-file and stdin modes.  bash 5.2 returned 1
for the same cells (the 2026-08-09 gate was green on 5.2.26).  psh still
returns 1 (and exits 128 for a non-numeric `break`/`continue` operand where
bash 5.3.15 exits the shell with 2).  Those rows are pinned BOTH SIDES as
declared divergences: bash 5.3 semantics; psh to follow in slot 2.3, which
flips each row to a parity pin.  Every divergence row asserts bash 5.3.15's
output AND psh's current output, so it goes red the moment EITHER side moves.
Ledger rows: W0-N4 (`exit abc` continues), W0-N8 (`shift abc` status),
W0-N9 (script-mode next-line status after too many arguments), W0-N10
(`break abc` / `continue abc`).  Gate triage node family C242 (Wave 0.3).

These run in a subprocess through the shell-oracle runner, so the real
process exit code is what's compared.

Reproduce one divergence row by hand (oracle = the resolved bash 5.3.15)::

    /opt/homebrew/bin/bash -c 'cd a b; echo rc=$?'     # rc=2
    python -m psh -c 'cd a b; echo rc=$?'              # rc=1
"""

from conformance_framework import ConformanceTest
from divergence_pins import MODES, assert_declared_divergence
from shell_oracle import is_comparable, run_bash, run_psh


def _assert_declared_divergence(command, *, bash, psh, tmp_path,
                                modes=MODES, stderr_has=None):
    """Slot 2.3 both-sides pin in the given input modes (D6); both
    shells must diagnose, ``stderr_has`` names the wording fragment
    both diagnostics carry.  See tests/conformance/divergence_pins.py.
    """
    assert_declared_divergence(command, bash=bash, psh=psh,
                               tmp_path=tmp_path, slot="2.3",
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

    def test_exit_too_many_args_does_not_exit(self, tmp_path):
        """DECLARED DIVERGENCE (W0-N9), both sides pinned; slot 2.3 flips.

        Both shells report "too many arguments" and KEEP RUNNING, so the
        following line executes -- but the status that line sees is 2 on
        bash 5.3.15 (empirical; 5.2 gave 1) and still 1 in psh.  Script-file
        and stdin modes only: under ``-c`` the error abandons the rest of the
        string in both shells (see the parity control below), which is a
        different fact from "exit doesn't terminate".
        """
        _assert_declared_divergence(
            'exit 1 2 3\necho after=$?',
            bash=('after=2\n', 0), psh=('after=1\n', 0), tmp_path=tmp_path,
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

    def test_exit_non_numeric_continues_declared_divergence(self, tmp_path):
        """DECLARED DIVERGENCE (W0-N4), both sides pinned; slot 2.3 flips.

        bash 5.3.15: ``exit abc`` prints "exit: abc: numeric argument
        required", sets ``$?`` to 2 and CONTINUES with the next command, in
        every input mode (empirical, 5.3.15; bash 5.2 exited 2).  psh exits
        the shell with status 2.  The second row is the shape of golden
        ``bcontract_exit_bad_first_operand_exits_two`` (now ``psh_only``).
        """
        _assert_declared_divergence(
            'exit abc; echo rc=$?',
            bash=('rc=2\n', 0), psh=('', 2), tmp_path=tmp_path,
            stderr_has='numeric argument required')
        _assert_declared_divergence(
            'exit abc 7; echo survived',
            bash=('survived\n', 0), psh=('', 2), tmp_path=tmp_path,
            stderr_has='numeric argument required')


class TestUsageStatusDeclaredDivergence:
    """W0-N8 / W0-N9 / W0-N10: the usage-error status family on bash 5.3.15,
    both sides pinned; slot 2.3 flips every row.  Values are the 5.3.15
    probes of 2026-09-06 (empirical: no CHANGES/NEWS item)."""

    def test_shift_non_numeric_status_2(self, tmp_path):
        # W0-N8: bash 5.3.15 rc 2 and continues; psh rc 1 and continues.
        _assert_declared_divergence(
            'shift abc; echo rc=$?',
            bash=('rc=2\n', 0), psh=('rc=1\n', 0), tmp_path=tmp_path,
            stderr_has='numeric argument required')

    def test_too_many_args_next_line_status_2(self, tmp_path):
        # W0-N9: shift/return/exit with too many arguments drop the rest of
        # the input line; the NEXT line sees $?=2 on 5.3.15, 1 in psh.
        # (-c mode: both shells abandon the string with rc 1 -- parity.)
        for head in ('shift 1 2', 'return 1 2', 'exit 7 8'):
            _assert_declared_divergence(
                f'{head}\necho rc=$?',
                bash=('rc=2\n', 0), psh=('rc=1\n', 0), tmp_path=tmp_path,
                modes=("script", "stdin"), stderr_has='too many arguments')

    def test_break_continue_non_numeric_exit_2(self, tmp_path):
        # W0-N10: a non-numeric break/continue operand inside a loop EXITS
        # the shell in every mode -- status 2 on bash 5.3.15, 128 in psh; the
        # following line never runs in either shell.
        for verb in ('break', 'continue'):
            _assert_declared_divergence(
                f'for i in 1; do {verb} abc; done\necho rc=$?',
                bash=('', 2), psh=('', 128), tmp_path=tmp_path,
                stderr_has='numeric argument required')


class TestCdOptions(ConformanceTest):
    def test_cd_empty_operand_is_null_directory(self):
        """``cd ""`` is "null directory", rc 1, cwd unchanged, even under CDPATH
        (bash 5.3.15, empirical; 5.2 was a no-op success). Wave 0.3 retune.
        stderr prefixes differ, so stderr goes to /dev/null and stdout + $?
        are compared."""
        self.assert_identical_behavior(
            'cd /usr; cd "" 2>/dev/null; echo "$?:$PWD"; '
            'CDPATH=/tmp cd "" 2>/dev/null; echo "$?:$PWD"; '
            'cd -P "" 2>/dev/null; echo "$?"; x=; cd $x 2>/dev/null; echo "$?"')

    def test_cd_too_many_arguments(self, tmp_path):
        """DECLARED DIVERGENCE, both sides pinned; slot 2.3 flips.

        ``cd a b`` is "too many arguments" with no chdir in both shells; the
        status is 2 on bash 5.3.15 (empirical; 5.2 gave 1) and 1 in psh, in
        every input mode.  stderr banner prefixes differ, so only the tail
        wording is compared.
        """
        _assert_declared_divergence(
            'cd a b; echo rc=$?',
            bash=('rc=2\n', 0), psh=('rc=1\n', 0), tmp_path=tmp_path,
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
