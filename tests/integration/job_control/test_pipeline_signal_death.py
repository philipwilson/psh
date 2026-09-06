"""Abnormal-termination diagnostic for a signal-killed foreground PIPELINE
member (reappraisal #17 MED-2).

``true | sh -c 'kill -TERM $$'`` printed nothing in psh where bash prints
``Terminated: 15`` — the single-command path reported signal deaths
(strategies.py) but the foreground-pipeline wait path never did.

bash's rule (probed on the 5.2 oracle, re-verified on bash 5.3.15 in Wave
0.1): the announced member is the one whose status becomes the pipeline's
EXIT STATUS — the last member normally, the rightmost failing member under
pipefail. Any other member's signal death is silent, as are SIGINT/SIGPIPE,
and anything inside command/process substitutions.

Wording is host-libc specific, so expectations use ``signal.strsignal`` (the
same source bash uses). DECLARED FORMAT DIVERGENCE: bash 5.3 announces through
its job-table printer — the status text left-justified in a 27-column field
followed by the job's command text (see ``bash_job_notice``), and for signals
other than SIGTERM a ``bash: line N: PID`` prefix as well; the 5.2 oracle
printed the bare ``Terminated: 15`` for SIGTERM, which was exact parity. psh
emits just the bare signal description on every path (same as the
single-command path in test_signal_killed_diagnostic.py). Both sides are
pinned; the parity flip (bash-faithful job text) is owned by slot 4.12 (C065)
through the program's FLIP-PINS.md.

Determinism over realism: the child signals itself. This path is auto-marked
``serial`` (job_control) — spawn/kill/wait is xdist-unsafe.
"""

import signal

from core_dump_env import signal_death_text
from shell_oracle import is_comparable
from shell_oracle import run_bash as _oracle_run_bash
from shell_oracle import run_psh as _oracle_run_psh


def run_psh(cmd, timeout=15):
    r = _oracle_run_psh(['-c', cmd], timeout=timeout)
    assert is_comparable(r), r
    return r


def run_bash(cmd, timeout=15):
    r = _oracle_run_bash(['-c', cmd], timeout=timeout)
    assert is_comparable(r), r
    return r


def bash_job_notice(status_text, job_text):
    """bash 5.3's foreground signal-death line: ``status_text`` left-justified
    in a 27-column field, then the job's command text (its pre-expansion
    re-print: whitespace normalised, quotes verbatim), then a newline.
    Empirical, 5.3.15 — the field is a pure ``ljust(27)``: a 27-character
    description (SIGFPE's on macOS) is followed by the text with NO
    separator. Identical in -c, script-file and stdin modes."""
    return status_text.ljust(27) + job_text + '\n'


def _run_modes(cmd, tmp_path):
    """(mode, psh, bash) for `cmd` in -c, script-file and stdin modes (D6)."""
    script = tmp_path / 'job.sh'
    script.write_text(cmd + '\n')
    for mode, args, stdin in (('-c', ['-c', cmd], None),
                              ('file', [str(script)], None),
                              ('stdin', [], cmd + '\n')):
        p = _oracle_run_psh(args, stdin_data=stdin, timeout=15)
        b = _oracle_run_bash(args, stdin_data=stdin, timeout=15)
        assert is_comparable(p) and is_comparable(b), (mode, p, b)
        yield mode, p, b


class TestPipelineLastMemberSignalDeath:
    def test_sigterm_last_member_announced(self, tmp_path):
        """psh: the bare SIGTERM description; bash 5.3: the padded job-table
        line (declared format divergence — module docstring). Pinned in all
        three input modes because the shape of the announcement is the
        subject (D6)."""
        cmd = 'true | sh -c "kill -TERM \\$\\$"; echo rc=$?'
        for mode, psh, bash in _run_modes(cmd, tmp_path):
            assert psh.stdout == 'rc=143\n' == bash.stdout, mode
            assert psh.stderr == signal.strsignal(signal.SIGTERM) + '\n', mode
            assert bash.stderr == bash_job_notice(
                signal.strsignal(signal.SIGTERM),
                'true | sh -c "kill -TERM \\$\\$"'), (mode, bash.stderr)

    def test_sigterm_no_trailing_command(self):
        """The announcement is unchanged when the signal death is the
        shell's last command in a pipeline (no exec-optimisation for
        pipeline members); rc 143 in both shells."""
        cmd = 'echo hi | sh -c "kill -TERM \\$\\$"'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.returncode == 143 == bash.returncode
        assert psh.stderr == signal.strsignal(signal.SIGTERM) + '\n'
        assert bash.stderr == bash_job_notice(
            signal.strsignal(signal.SIGTERM),
            'echo hi | sh -c "kill -TERM \\$\\$"'), bash.stderr

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
        # SIGSEGV dumps core wherever the host allows it, and psh then appends
        # bash's " (core dumped)" from WCOREDUMP -- a host property, not a psh
        # one, so the expectation is built with the kernel's own rule (see
        # tests/harness/core_dump_env.py) and stays exact on both platforms.
        assert psh.stderr.strip() == signal_death_text(
            signal.strsignal(signal.SIGSEGV))
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
        status and BOTH shells announce the job — the announce DECISION is
        pipefail-driven in both. bash 5.3 announces through its job-table
        printer, whose status column is the LAST member's label (`Done`,
        cat exited 0) followed by the command text, even though the
        announced condition is the pipefail member's signal death (a job
        whose `$?` is 143 is printed as `Done`; empirical, 5.3.15 — the 5.2
        oracle printed the member's bare `Terminated: 15`). psh keeps
        naming the status-determining member's signal — declared
        divergence, both sides pinned; do NOT "fix" psh to print `Done`
        without the command text."""
        cmd = ('set -o pipefail; sh -c "kill -TERM \\$\\$" | cat; '
               'echo rc=$?')
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'rc=143\n' == bash.stdout
        assert psh.stderr == signal.strsignal(signal.SIGTERM) + '\n'
        assert bash.stderr == bash_job_notice(
            'Done', 'sh -c "kill -TERM \\$\\$" | cat'), bash.stderr

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
