"""Redirect-setup failures print ONE message shape on every dispatch site.

Reappraisal #17 io MED-1 + LOW-3: the FD_LEVEL_WINDOW dispatch path
(function calls; builtins in pipelines/forked children) applied redirects
with no guard, so a setup failure leaked the raw Python OSError repr
("psh: [Errno 21] Is a directory: 'd'") instead of bash's
"psh: line 1: d: Is a directory". The empty-string target (`> ""`) additionally
produced a different malformed message per path (`if target:` treated ''
as absent). Both now route through format_redirect_error /
guarded_redirections — the documented "one message shape" invariant is
true on all four dispatch sites (builtin in-process, external, compound,
FD_LEVEL_WINDOW) plus the no-command-word and pure-assignment sites.

Subprocess tests: several cases exercise forked pipeline members writing
diagnostics at the fd level.
"""

import subprocess
import sys

import pytest


def _run_psh(cmd, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          cwd=cwd, capture_output=True, text=True, timeout=15)


MISSING = '/nonexistent_dir_zz_psh/y'


class TestFdLevelWindowMessages:
    """The FD_LEVEL_WINDOW path (functions, builtins in pipelines)."""

    def test_function_redirect_to_directory(self, tmp_path):
        (tmp_path / 'd').mkdir()
        result = _run_psh('f(){ echo hi; }; f > d; echo rc=$?',
                          cwd=str(tmp_path))
        assert result.stdout == 'rc=1\n'
        assert result.stderr.strip() == 'psh: line 1: d: Is a directory'

    def test_function_redirect_to_missing_dir(self):
        result = _run_psh(f'f(){{ echo hi; }}; f > {MISSING}; echo rc=$?')
        assert result.stdout == 'rc=1\n'
        assert result.stderr.strip() == \
            f'psh: line 1: {MISSING}: No such file or directory'

    def test_builtin_in_pipeline_redirect_failure(self):
        result = _run_psh(f'echo x > {MISSING} | cat; echo rc=$?')
        assert result.stdout == 'rc=0\n'  # pipeline status is cat's
        assert result.stderr.strip() == \
            f'psh: line 1: {MISSING}: No such file or directory'

    def test_function_in_pipeline_redirect_failure(self):
        result = _run_psh(
            f'f(){{ echo hi; }}; f > {MISSING} | cat; echo rc=$?')
        assert result.stdout == 'rc=0\n'
        assert result.stderr.strip() == \
            f'psh: line 1: {MISSING}: No such file or directory'

    def test_no_raw_oserror_repr_anywhere(self, tmp_path):
        (tmp_path / 'd').mkdir()
        cases = [
            'f(){ echo hi; }; f > d',
            f'f(){{ echo hi; }}; f > {MISSING}',
            f'echo x > {MISSING} | cat',
            '> ""',
            'f(){ echo hi; }; f > ""',
        ]
        for cmd in cases:
            result = _run_psh(cmd, cwd=str(tmp_path))
            assert '[Errno' not in result.stderr, (cmd, result.stderr)


class TestEmptyTargetOneShape:
    """`> ""` prints bash's `psh: line 1: : No such file or directory` on EVERY
    dispatch path (was: three different malformed messages)."""

    EXPECTED = 'psh: line 1: : No such file or directory'

    @pytest.mark.parametrize('cmd', [
        '> ""',                        # no command word
        'echo hi > ""',                # builtin in-process
        '/bin/echo hi > ""',           # external (forked child)
        '{ echo hi; } > ""',           # compound (guarded_redirections)
        'f(){ echo hi; }; f > ""',     # FD_LEVEL_WINDOW (function)
    ], ids=['bare', 'builtin', 'external', 'compound', 'function'])
    def test_empty_target_message(self, cmd):
        result = _run_psh(cmd + '; echo rc=$?')
        assert result.stdout == 'rc=1\n'
        assert result.stderr.strip() == self.EXPECTED


class TestAssignmentRedirectOrdering:
    """bash performs pure/bare-array assignments BEFORE the command's
    redirections: a redirect failure still assigns and fails with 1."""

    def test_pure_assignment_persists_on_redirect_failure(self):
        result = _run_psh(f'x=5 > {MISSING}; echo x=[$x] rc=$?')
        assert result.stdout == 'x=[5] rc=1\n'
        assert result.stderr.strip() == \
            f'psh: line 1: {MISSING}: No such file or directory'

    def test_cmdsub_value_runs_before_redirect(self):
        result = _run_psh(f'x=$(echo 9) > {MISSING}; echo x=[$x] rc=$?')
        assert result.stdout == 'x=[9] rc=1\n'

    def test_bare_array_assignment_persists_on_redirect_failure(self):
        result = _run_psh(
            f'a=(1 2); a[0]=x > {MISSING}; echo a0=[${{a[0]}}] rc=$?')
        assert result.stdout == 'a0=[x] rc=1\n'
        assert result.stderr.strip() == \
            f'psh: line 1: {MISSING}: No such file or directory'

    def test_pure_assignment_value_reads_original_stdin(self, tmp_path):
        """bash: `x=$(cat) < file` expands the value with the ORIGINAL
        stdin (redirects are applied after the assignments)."""
        f = tmp_path / 'in.txt'
        f.write_text('fromfile\n')
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             f'x=$(cat) < {f}; echo x=[$x]'],
            capture_output=True, text=True, timeout=15,
            stdin=subprocess.DEVNULL)
        assert result.stdout == 'x=[]\n'

    def test_successful_redirect_still_applies(self, tmp_path):
        out = tmp_path / 'created.txt'
        result = _run_psh(f'x=5 > {out}; echo x=$x rc=$?')
        assert result.stdout == 'x=5 rc=0\n'
        assert out.exists()
