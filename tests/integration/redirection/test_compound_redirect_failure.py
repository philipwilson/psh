"""Redirect failure on IN-PROCESS COMPOUND commands, pinned to bash 5.2.

Reappraisal #15, Cluster C3. A bad redirect target on a compound command
(``{ }``, ``if``, ``for``, ``while``, ``until``, ``case``, ``[[ ]]``,
``(( ))``) used to raise an uncaught ``OSError`` that reached the generic
"unexpected error" handler — so ``|| fallback`` was skipped. The contract,
verified against bash, is the same as for a simple command:

- a diagnostic is printed to stderr;
- the compound BODY does not run;
- the construct fails with status 1, so ``|| fallback`` runs;
- the shell's fds are restored for the following command.

One redirect-error chokepoint (``IOManager.guarded_redirections``) now
serves every in-process compound dispatch site with one message format
(``psh: line N: TARGET: STRERROR``), matching the simple-command path.

Runs psh in a subprocess: process-level fd state must not touch the test
runner's own fds — which keeps it xdist-safe, so it runs in the parallel
phase (vetted in campaign #21).
"""

import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

BASH = resolve_bash().path

BAD = '/nonexistent_zz_dir/x'

# (id, compound command whose whole body has a bad `> BAD`)
COMPOUNDS = [
    ('brace', '{ echo a; }'),
    ('subshell', '( echo a )'),
    ('if', 'if true; then echo a; fi'),
    ('for', 'for i in 1 2; do echo $i; done'),
    ('while', 'n=0; while [ $n -lt 1 ]; do n=1; echo a; done'),
    ('until', 'n=0; until [ $n -ge 1 ]; do n=1; echo a; done'),
    ('case', 'case x in x) echo a;; esac'),
    ('dbracket', '[[ 1 == 1 ]]'),
    ('arith', '(( 1 + 1 ))'),
]


def run_psh(cmd, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, cwd=cwd, timeout=15)


def run_bash(cmd, cwd=None):
    return subprocess.run([BASH, '-c', cmd], capture_output=True,
                          text=True, cwd=cwd, timeout=15)


@pytest.mark.parametrize('label,compound', COMPOUNDS,
                         ids=[c[0] for c in COMPOUNDS])
class TestCompoundRedirectFailure:
    def test_fallback_runs_and_rc_zero(self, label, compound, tmp_path):
        """`COMPOUND > BAD || echo fallback` runs the fallback (rc 0 overall)."""
        cmd = f'{compound} > {BAD} || echo fallback; echo rc=$?'
        psh = run_psh(cmd, cwd=tmp_path)
        assert psh.stdout == 'fallback\nrc=0\n', psh.stderr
        assert psh.stderr != '', 'a diagnostic should be printed'

    def test_body_did_not_run(self, label, compound, tmp_path):
        """The compound's body must NOT run when its redirect fails."""
        psh = run_psh(f'{compound} > {BAD} || true', cwd=tmp_path)
        assert 'a' not in psh.stdout.split(), psh.stdout
        assert psh.stdout == '', 'body output must not leak'

    def test_standalone_rc_is_one(self, label, compound, tmp_path):
        """Without a fallback the failing compound reports status 1 (bash)."""
        cmd = f'{compound} > {BAD}; echo rc=$?'
        psh = run_psh(cmd, cwd=tmp_path)
        bash = run_bash(cmd, cwd=tmp_path)
        assert psh.stdout == bash.stdout == 'rc=1\n'

    def test_fds_restored_for_next_command(self, label, compound, tmp_path):
        """A following command still writes to the real stdout."""
        psh = run_psh(f'{compound} > {BAD}; echo RESTORED', cwd=tmp_path)
        assert psh.stdout == 'RESTORED\n', psh.stderr

    def test_message_format_matches_simple_command(self, label, compound,
                                                   tmp_path):
        """The diagnostic uses the same `psh: line N: TARGET: ...` shape a simple
        command emits (the unified chokepoint), naming the bad target."""
        psh = run_psh(f'{compound} > {BAD}', cwd=tmp_path)
        assert psh.stderr.startswith(f'psh: line 1: {BAD}:'), psh.stderr
        assert 'unexpected error' not in psh.stderr


class TestCompoundRedirectFailureContexts:
    """Redirect-failure in the special contexts that suppress set -e."""

    def test_bad_redirect_in_if_condition(self, tmp_path):
        """A compound with a bad redirect used as an if-CONDITION fails (1),
        so the else branch runs (bash)."""
        cmd = (f'if {{ echo a; }} > {BAD}; then echo then; '
               f'else echo else; fi')
        psh = run_psh(cmd, cwd=tmp_path)
        bash = run_bash(cmd, cwd=tmp_path)
        assert psh.stdout == bash.stdout == 'else\n'

    def test_set_e_aborts_on_compound_redirect_failure(self, tmp_path):
        """Under set -e a bare failing-redirect compound aborts the shell
        (the following command does not run), like bash."""
        cmd = f'set -e; {{ echo a; }} > {BAD}; echo after'
        psh = run_psh(cmd, cwd=tmp_path)
        bash = run_bash(cmd, cwd=tmp_path)
        assert psh.stdout == bash.stdout == ''
        assert psh.returncode == bash.returncode == 1

    def test_function_definition_redirect_failure(self, tmp_path):
        """A function with a bad definition-attached redirect fails the call
        with the unified message format, and `|| fallback` runs."""
        cmd = f'f() {{ echo hi; }} > {BAD}; f || echo fallback; echo rc=$?'
        psh = run_psh(cmd, cwd=tmp_path)
        assert psh.stdout == 'fallback\nrc=0\n', psh.stderr
        assert psh.stderr.startswith(f'psh: line 1: {BAD}:'), psh.stderr

    def test_combined_redirect_after_closed_stdout(self, tmp_path):
        """`exec 1>&-; { ...; } &> f` must not crash and must leave fd 2
        intact: a later `echo x >&2` still reaches the real stderr (the
        high-fd combined-save fix)."""
        out = tmp_path / 'out'
        cmd = f'exec 1>&-; {{ echo a; }} &> {out}; echo done >&2'
        psh = run_psh(cmd, cwd=tmp_path)
        assert psh.returncode == 0
        assert psh.stderr == 'done\n', psh.stderr
        assert out.read_text() == 'a\n'
