"""Abnormal-termination diagnostic for a signal-killed foreground external.

bash prints a line like ``Terminated: 15`` / ``Segmentation fault: 11`` to
stderr — even non-interactively — when a foreground command dies by a signal
other than SIGINT/SIGPIPE, so a following command isn't preceded by
unexplained silence (reappraisal #16 Tier-2 EXECUTOR-DIAGNOSTICS #1). The exit
status (128+N) is already correct and unchanged; this pins the diagnostic.

Wording is host-libc specific (``Terminated: 15`` on macOS, ``Terminated`` on
Linux), so the expected text is computed with ``signal.strsignal`` — the same
source bash's diagnostic uses — rather than hard-coded, and bash on the same
host is cross-checked to mention the signal.

Determinism over realism: a child sends the signal to *itself*
(``sh -c 'kill -N $$'``); no timing, no flake. The ``job_control`` path is
auto-marked ``serial`` (spawn/kill/wait — xdist-unsafe).

DECLARED FORMAT DIVERGENCE (both sides pinned below; the parity flip —
bash-faithful job text — is owned by slot 4.12 (C065) through the program's
FLIP-PINS.md): bash 5.3 announces every foreground signal death through its
job-table printer — the status text left-justified in a 27-column field
followed by the job's command text (its pre-expansion re-print: whitespace
normalised, quotes verbatim, ``( … )`` for a subshell; see
``bash_job_notice``), and for signals other than SIGTERM a ``bash: line N:
PID`` prefix as well. The 5.2 oracle printed the bare ``Terminated: 15`` for
SIGTERM, which was exact parity. psh emits just the signal description on
every path. A second documented, untested divergence: a signal death that is
the shell's LAST action uses bash's exec-optimization machinery that psh does
not replicate. (Pipeline-member deaths ARE announced since reappraisal #17
MED-2 — see test_pipeline_signal_death.py.)
"""

import signal

from core_dump_env import signal_death_text
from shell_oracle import is_comparable
from shell_oracle import run_bash as _run_bash
from shell_oracle import run_psh as _run_psh


def run_psh(cmd, timeout=15):
    r = _run_psh(['-c', cmd], timeout=timeout)
    assert is_comparable(r), r
    return r


def run_bash(cmd, timeout=15):
    r = _run_bash(['-c', cmd], timeout=timeout)
    assert is_comparable(r), r
    return r


def bash_job_notice(status_text, job_text):
    """bash 5.3's foreground signal-death line: ``status_text`` left-justified
    in a 27-column field, then the job's command text, then a newline.
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
        p = _run_psh(args, stdin_data=stdin, timeout=15)
        b = _run_bash(args, stdin_data=stdin, timeout=15)
        assert is_comparable(p) and is_comparable(b), (mode, p, b)
        yield mode, p, b


class TestAbnormalTerminationDiagnostic:
    """psh announces a signal-killed foreground command like bash does."""

    def test_sigterm_prints_bare_signal_description(self, tmp_path):
        """`sh -c "kill -TERM $$"; echo next` — psh prints the bare SIGTERM
        description to stderr and still runs the next command; bash 5.3
        appends the padded job text (declared format divergence — module
        docstring). Pinned in all three input modes because the shape of the
        announcement is the subject (D6)."""
        cmd = 'sh -c "kill -TERM \\$\\$"; echo next'
        for mode, psh, bash in _run_modes(cmd, tmp_path):
            assert psh.stdout == 'next\n' == bash.stdout, mode
            assert psh.returncode == 0 == bash.returncode, mode
            assert psh.stderr == signal.strsignal(signal.SIGTERM) + '\n', mode
            assert bash.stderr == bash_job_notice(
                signal.strsignal(signal.SIGTERM),
                'sh -c "kill -TERM \\$\\$"'), (mode, bash.stderr)

    def test_diagnostic_names_the_signal(self):
        """A crash signal (SIGSEGV) is announced with its description. bash
        adds a verbose ``bash: line N: PID`` prefix for non-SIGTERM signals,
        so here we pin psh's own bare form and merely confirm bash mentions
        the same signal."""
        cmd = 'sh -c "kill -SEGV \\$\\$"; echo next'
        psh = run_psh(cmd)
        assert psh.stdout == 'next\n'
        # SIGSEGV dumps core wherever the host allows it, and psh then appends
        # bash's " (core dumped)" from WCOREDUMP. Whether that happens is the
        # HOST's call, not psh's, so build the expected text with the same rule
        # the kernel uses (tests/harness/core_dump_env.py). That keeps this an
        # EXACT pin in both environments instead of one accepting either answer.
        assert psh.stderr.strip() == signal_death_text(
            signal.strsignal(signal.SIGSEGV))
        bash = run_bash(cmd)
        assert signal.strsignal(signal.SIGSEGV) in bash.stderr

    def test_sigint_and_sigpipe_are_silent(self):
        """bash does NOT announce SIGINT or SIGPIPE deaths; psh matches
        (empty stderr, next command runs)."""
        for signame in ('INT', 'PIPE'):
            cmd = f'sh -c "kill -{signame} \\$\\$"; echo next'
            psh = run_psh(cmd)
            bash = run_bash(cmd)
            assert psh.stdout == 'next\n'
            assert psh.stderr == '', f'{signame}: {psh.stderr!r}'
            assert bash.stderr == ''

    def test_normal_and_nonzero_exit_are_silent(self):
        """No diagnostic for an ordinary exit, zero or non-zero."""
        for tail in ('true', 'sh -c "exit 3"'):
            cmd = f'{tail}; echo next'
            psh = run_psh(cmd)
            assert psh.stdout == 'next\n'
            assert psh.stderr == ''

    def test_reported_in_explicit_subshell(self):
        """A ( ) subshell announces its foreground child's signal death in
        both shells. bash 5.3 re-prints the subshell as `( … )` with inner
        spaces in the padded job text (empirical, 5.3.15); psh's bare form
        is unchanged (declared format divergence — module docstring)."""
        cmd = '(sh -c "kill -TERM \\$\\$"); echo next'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'next\n' == bash.stdout
        assert psh.stderr == signal.strsignal(signal.SIGTERM) + '\n'
        assert bash.stderr == bash_job_notice(
            signal.strsignal(signal.SIGTERM),
            '( sh -c "kill -TERM \\$\\$" )'), bash.stderr

    def test_suppressed_in_command_substitution(self):
        """bash suppresses the diagnostic inside a command substitution; psh
        matches (silent), both single- and multi-command bodies."""
        for body in ('sh -c "kill -TERM \\$\\$"',
                     'sh -c "kill -TERM \\$\\$"; echo hi'):
            cmd = f'x=$({body}); echo next'
            psh = run_psh(cmd)
            bash = run_bash(cmd)
            assert psh.stderr == '', psh.stderr
            assert bash.stderr == ''
            assert psh.stdout == bash.stdout

    def test_suppressed_in_process_substitution(self):
        """Likewise silent inside a process substitution, matching bash."""
        cmd = 'cat <(sh -c "kill -TERM \\$\\$"); echo next'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stderr == ''
        assert bash.stderr == ''
        assert psh.stdout == 'next\n' == bash.stdout

    def test_suppressed_in_subshell_nested_in_command_substitution(self):
        """The suppression propagates: a ( ) subshell nested inside a
        command substitution stays silent (the whole substitution is)."""
        cmd = 'x=$( (sh -c "kill -TERM \\$\\$") ); echo next'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stderr == ''
        assert bash.stderr == ''
        assert psh.stdout == 'next\n'
