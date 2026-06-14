"""
Tests for the dynamic special variables added in v0.261.0:
PIPESTATUS, $PPID, $UID/$EUID, $EPOCHSECONDS/$EPOCHREALTIME, and the
'c' flag in $-. Verified against bash 5.2.
"""

import os
import re
import subprocess
import sys
import time


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestPipestatus:
    def test_multi_pipeline_statuses(self):
        result = run_psh('true | false | true; echo "${PIPESTATUS[@]}"')
        assert result.stdout == '0 1 0\n'

    def test_single_command_sets_one_element(self):
        result = run_psh('false; echo "${PIPESTATUS[@]}"; echo "${#PIPESTATUS[@]}"')
        assert result.stdout == '1\n1\n'

    def test_single_command_overwrites_pipeline(self):
        result = run_psh('true | false; true; echo "${PIPESTATUS[@]}"')
        assert result.stdout == '0\n'

    def test_pipefail_keeps_all_statuses(self):
        result = run_psh('set -o pipefail; false | true; echo "$? ${PIPESTATUS[@]}"')
        assert result.stdout == '1 1 0\n'


class TestProcessIdentity:
    def test_ppid_is_invoking_process(self):
        result = run_psh('echo $PPID')
        assert int(result.stdout) == os.getpid()

    def test_ppid_stable_in_subshell(self):
        result = run_psh('(echo $PPID); echo $PPID')
        a, b = result.stdout.split()
        assert a == b == str(os.getpid())

    def test_uid_euid(self):
        result = run_psh('echo "$UID $EUID"')
        assert result.stdout == f"{os.getuid()} {os.geteuid()}\n"


class TestEpochVariables:
    def test_epochseconds(self):
        before = int(time.time())
        result = run_psh('echo $EPOCHSECONDS')
        after = int(time.time())
        assert before <= int(result.stdout) <= after

    def test_epochrealtime_format(self):
        result = run_psh('echo $EPOCHREALTIME')
        assert re.match(r'^\d+\.\d{6}$', result.stdout.strip())


class TestDashVariable:
    def test_dash_contains_c_for_command_mode(self):
        result = run_psh('echo $-')
        assert 'c' in result.stdout


class TestSecondsAssignment:
    """SECONDS is computed on read, but assignment resets the baseline
    (bash: SECONDS=N then reads return N + elapsed-since-assignment)."""

    def test_assignment_is_honored_immediately(self):
        # Right after assignment essentially no time has elapsed -> exactly N.
        result = run_psh('SECONDS=100; echo $SECONDS')
        assert result.stdout == '100\n'

    def test_assign_zero(self):
        result = run_psh('SECONDS=0; echo $SECONDS')
        assert result.stdout == '0\n'

    def test_elapses_across_sleep(self):
        result = run_psh('SECONDS=0; sleep 1; echo $SECONDS')
        assert result.stdout == '1\n'

    def test_baseline_plus_elapsed(self):
        result = run_psh('SECONDS=100; sleep 1; echo $SECONDS')
        assert result.stdout == '101\n'

    def test_noninteger_is_zero(self):
        # bash parses a plain integer; non-integer -> 0 (not arithmetic eval).
        for value in ('abc', '5xy', '0x10'):
            result = run_psh(f'SECONDS={value}; echo $SECONDS')
            assert result.stdout == '0\n', value

    def test_negative_accepted(self):
        result = run_psh('SECONDS=-5; echo $SECONDS')
        assert result.stdout == '-5\n'

    def test_arithmetic_assignment(self):
        # (( )) and the value pre-expansion both route through set_variable.
        assert run_psh('(( SECONDS = 50 )); echo $SECONDS').stdout == '50\n'
        assert run_psh('SECONDS=$((2+3)); echo $SECONDS').stdout == '5\n'

    def test_unset_makes_it_an_ordinary_variable(self):
        # After unset, SECONDS loses special behavior: a string sticks.
        assert run_psh('unset SECONDS; SECONDS=foo; echo "[$SECONDS]"').stdout \
            == '[foo]\n'
        assert run_psh('unset SECONDS; echo "[$SECONDS]"').stdout == '[]\n'


class TestRandomSeeding:
    """RANDOM=N seeds bash's Park-Miller generator; psh reproduces bash's
    5.x sequence value-for-value, so these are exact-match assertions."""

    def test_seed_one_sequence(self):
        result = run_psh('RANDOM=1; echo $RANDOM $RANDOM $RANDOM')
        assert result.stdout == '16807 10791 19566\n'

    def test_seed_42_sequence(self):
        result = run_psh('RANDOM=42; echo $RANDOM $RANDOM $RANDOM')
        assert result.stdout == '17772 26794 1435\n'

    def test_seed_zero_sequence(self):
        result = run_psh('RANDOM=0; echo $RANDOM $RANDOM $RANDOM')
        assert result.stdout == '20814 24386 149\n'

    def test_noninteger_seed_is_zero(self):
        # Non-integer seed parses as 0 (same sequence as RANDOM=0).
        assert run_psh('RANDOM=abc; echo $RANDOM $RANDOM').stdout \
            == '20814 24386\n'

    def test_reproducible_same_seed(self):
        first = run_psh('RANDOM=42; echo $RANDOM $RANDOM').stdout
        second = run_psh('RANDOM=42; echo $RANDOM $RANDOM').stdout
        assert first == second

    def test_arithmetic_seed(self):
        assert run_psh('RANDOM=$((40+2)); echo $RANDOM').stdout == '17772\n'
        assert run_psh('(( RANDOM = 1 )); echo $RANDOM $RANDOM').stdout \
            == '16807 10791\n'

    def test_values_in_range(self):
        result = run_psh('RANDOM=7; for i in 1 2 3 4 5; do echo $RANDOM; done')
        values = [int(x) for x in result.stdout.split()]
        assert len(values) == 5
        assert all(0 <= v <= 32767 for v in values)

    def test_unseeded_varies(self):
        # Without a seed, RANDOM is unpredictable; two reads almost never
        # collide. Use several reads to make a chance collision negligible.
        result = run_psh('for i in 1 2 3 4 5 6; do echo $RANDOM; done')
        values = result.stdout.split()
        assert len(set(values)) > 1

    def test_unset_makes_it_an_ordinary_variable(self):
        assert run_psh('unset RANDOM; RANDOM=hi; echo "[$RANDOM]"').stdout \
            == '[hi]\n'
