"""Analysis modes (--security/--metrics/--validate/--lint/--format) must treat
a heredoc BODY as data, not as shell commands.

Before v0.489 the CLI analysis modes parsed with a bare tokenize/parse (no
heredoc collection), so a heredoc body was analyzed as separate commands — e.g.
`rm -rf /` sitting in heredoc *data* was reported as a HIGH security risk, and
command counts were inflated. These pin the real CLI entry points.
"""

import subprocess
import sys

# A script whose heredoc body contains text that LOOKS dangerous but is data.
HEREDOC_SCRIPT = 'cat <<END\nrm -rf /\neval "$danger"\nEND\necho done\n'


def _run(mode, script_path):
    return subprocess.run(
        [sys.executable, '-m', 'psh', mode, script_path],
        capture_output=True, text=True)


class TestVisitorHeredocBodyIsData:
    def test_security_ignores_heredoc_body(self, tmp_path):
        p = tmp_path / 's.sh'
        p.write_text(HEREDOC_SCRIPT)
        r = _run('--security', str(p))
        assert 'rm of /' not in r.stdout
        assert 'No security issues found' in r.stdout
        assert r.returncode == 0

    def test_metrics_counts_two_commands(self, tmp_path):
        # cat + echo — NOT the two heredoc-body lines.
        p = tmp_path / 's.sh'
        p.write_text(HEREDOC_SCRIPT)
        r = _run('--metrics', str(p))
        assert 'Total Commands:             2' in r.stdout

    def test_validate_clean(self, tmp_path):
        p = tmp_path / 's.sh'
        p.write_text(HEREDOC_SCRIPT)
        r = _run('--validate', str(p))
        assert r.returncode == 0


class TestVisitorStillFlagsRealCommands:
    """Regression guard: a real dangerous command (not in a heredoc) still fires."""

    def test_security_flags_real_rm(self, tmp_path):
        p = tmp_path / 'r.sh'
        p.write_text('rm -rf /\n')
        r = _run('--security', str(p))
        assert 'rm of /' in r.stdout
        assert r.returncode == 1
