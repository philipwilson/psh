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

Two divergences from bash are deliberate and documented (not tested here):
  * bash prefixes ``bash: line N: PID ... CMD`` for signals other than
    SIGTERM; psh emits just the signal description.
  * a signal death that is the shell's LAST action, and pipeline-member
    deaths, use bash's exec-optimization / column job-notification machinery
    that psh does not replicate.
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


class TestAbnormalTerminationDiagnostic:
    """psh announces a signal-killed foreground command like bash does."""

    def test_sigterm_prints_bare_signal_description(self):
        """`sh -c "kill -TERM $$"; echo next` — psh prints the SIGTERM
        description to stderr and still runs the next command. For SIGTERM
        bash uses the same bare form, so this is exact parity."""
        cmd = 'sh -c "kill -TERM \\$\\$"; echo next'
        psh = run_psh(cmd)
        assert psh.stdout == 'next\n'
        assert psh.returncode == 0
        assert psh.stderr.strip() == signal.strsignal(signal.SIGTERM)
        # bash on this host names the same signal (bare for SIGTERM).
        bash = run_bash(cmd)
        assert psh.stderr == bash.stderr

    def test_diagnostic_names_the_signal(self):
        """A crash signal (SIGSEGV) is announced with its description. bash
        adds a verbose ``bash: line N: PID`` prefix for non-SIGTERM signals,
        so here we pin psh's own bare form and merely confirm bash mentions
        the same signal."""
        cmd = 'sh -c "kill -SEGV \\$\\$"; echo next'
        psh = run_psh(cmd)
        assert psh.stdout == 'next\n'
        assert psh.stderr.strip() == signal.strsignal(signal.SIGSEGV)
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
        """A ( ) subshell announces its foreground child's signal death, like
        bash (exact parity for SIGTERM)."""
        cmd = '(sh -c "kill -TERM \\$\\$"); echo next'
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'next\n'
        assert psh.stderr.strip() == signal.strsignal(signal.SIGTERM)
        assert psh.stderr == bash.stderr

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
