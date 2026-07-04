"""Abnormal-termination diagnostic for a signal-killed foreground PIPELINE
member (reappraisal #17 MED-2).

``true | sh -c 'kill -TERM $$'`` printed nothing in psh where bash prints
``Terminated: 15`` — the single-command path reported signal deaths
(strategies.py) but the foreground-pipeline wait path never did.

bash's rule (pinned in tmp/probes-r17t2-grabbag/probe_c_pipeline_signal.sh
against bash 5.2): the announced member is the one whose status becomes the
pipeline's EXIT STATUS — the last member normally, the rightmost failing
member under pipefail. Any other member's signal death is silent, as are
SIGINT/SIGPIPE, and anything inside command/process substitutions.

Wording is host-libc specific, so expectations use ``signal.strsignal`` (the
same source bash uses). For non-SIGTERM signals bash wraps the message in a
PID/command job table; psh emits just the bare signal description (documented
format difference, same as the single-command path).

Determinism over realism: the child signals itself. This path is auto-marked
``serial`` (job_control) — spawn/kill/wait is xdist-unsafe.
"""

import signal
import subprocess
import sys


def run_psh(cmd, timeout=15):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=timeout)


def run_bash(cmd, timeout=15):
    return subprocess.run(['bash', '-c', cmd],
                          capture_output=True, text=True, timeout=timeout)


class TestPipelineLastMemberSignalDeath:
    def test_sigterm_last_member_announced(self):
        """Exact bash parity for SIGTERM (bare form in both shells)."""
        cmd = 'true | sh -c "kill -TERM \\$\\$"; echo rc=$?'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'rc=143\n' == bash.stdout
        assert psh.stderr.strip() == signal.strsignal(signal.SIGTERM)
        assert psh.stderr == bash.stderr

    def test_sigterm_no_trailing_command(self):
        cmd = 'echo hi | sh -c "kill -TERM \\$\\$"'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.returncode == 143 == bash.returncode
        assert psh.stderr == bash.stderr
        assert psh.stderr.strip() == signal.strsignal(signal.SIGTERM)

    def test_three_stage_pipeline_last_member(self):
        cmd = 'true | true | sh -c "kill -TERM \\$\\$"; echo rc=$?'
        psh = run_psh(cmd)
        assert psh.stdout == 'rc=143\n'
        assert psh.stderr.strip() == signal.strsignal(signal.SIGTERM)

    def test_non_sigterm_names_the_signal(self):
        """psh's bare form; bash adds the job-table wrapper for non-TERM
        signals, so only the signal name is cross-checked there."""
        cmd = 'true | sh -c "kill -SEGV \\$\\$"; echo rc=$?'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'rc=139\n' == bash.stdout
        assert psh.stderr.strip() == signal.strsignal(signal.SIGSEGV)
        assert signal.strsignal(signal.SIGSEGV) in bash.stderr

    def test_sigint_last_member_silent(self):
        """bash does not announce SIGINT deaths; rc still 130."""
        cmd = 'true | sh -c "kill -INT \\$\\$"; echo rc=$?'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'rc=130\n' == bash.stdout
        assert psh.stderr == '' == bash.stderr


class TestPipelineNonLastMemberSignalDeath:
    def test_middle_member_silent_without_pipefail(self):
        """A non-last member's signal death is silent in bash: the
        pipeline's status is the last member's (0 here)."""
        cmd = 'sh -c "kill -TERM \\$\\$" | cat; echo rc=$?'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'rc=0\n' == bash.stdout
        assert psh.stderr == '' == bash.stderr

    def test_pipefail_announces_status_determining_member(self):
        """Under pipefail the signal-killed member's 143 becomes the exit
        status, and bash announces it (bare form — exact parity)."""
        cmd = ('set -o pipefail; sh -c "kill -TERM \\$\\$" | cat; '
               'echo rc=$?')
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'rc=143\n' == bash.stdout
        assert psh.stderr.strip() == signal.strsignal(signal.SIGTERM)
        assert psh.stderr == bash.stderr

    def test_pipefail_silent_when_later_failure_wins(self):
        """The rightmost NON-ZERO status is grep's plain 1, so the earlier
        signal death is NOT announced (bash)."""
        cmd = ('set -o pipefail; sh -c "kill -TERM \\$\\$" | grep nomatch; '
               'echo rc=$?')
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'rc=1\n' == bash.stdout
        assert psh.stderr == '' == bash.stderr


class TestPipelineSignalDeathSuppression:
    def test_silent_inside_command_substitution(self):
        cmd = 'v=$(true | sh -c "kill -TERM \\$\\$"); echo rc=$?'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'rc=143\n' == bash.stdout
        assert psh.stderr == '' == bash.stderr

    def test_normal_pipeline_failure_stays_silent(self):
        cmd = 'true | false; echo rc=$?'
        psh = run_psh(cmd)
        assert psh.stdout == 'rc=1\n'
        assert psh.stderr == ''

    def test_successful_pipeline_stays_silent(self):
        cmd = 'echo ok | cat; echo rc=$?'
        psh = run_psh(cmd)
        assert psh.stdout == 'ok\nrc=0\n'
        assert psh.stderr == ''
