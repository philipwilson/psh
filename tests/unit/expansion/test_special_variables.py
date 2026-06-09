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
