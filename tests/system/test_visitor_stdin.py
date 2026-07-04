"""Analysis modes must ANALYZE piped stdin, never execute it (r17 H2).

Before this fix the stdin branch of ``__main__.main()`` never checked the
visitor-mode flags, so ``cat script | psh --security`` EXECUTED the very
script it was asked to analyze (same for --format/--lint/--metrics), and
``--validate`` on stdin ran a second, divergent line-by-line implementation
inside the execution loop that printed the syntax error AND a contradictory
"No issues found" summary with exit 0.

All three input channels (-c, script file, piped stdin) now route through the
single chokepoint ``visitor_modes.handle_visitor_mode_for_content``: identical
content must produce identical analysis output and exit codes, with zero
execution side effects. The -c form is the reference behavior.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Run THIS tree's psh regardless of cwd (subprocesses run with cwd=tmp_path,
# where a bare `python -m psh` would resolve to an installed copy instead).
REPO_ROOT = str(Path(__file__).resolve().parents[2])

MODES = ['--validate', '--format', '--metrics', '--security', '--lint']

# A payload whose execution is unmissable: creates a file and prints a line.
SIDE_EFFECT_SCRIPT = 'echo executed > marker.txt\necho SIDEEFFECT\n'


def _env():
    return dict(os.environ, PYTHONPATH=REPO_ROOT)


def _run_stdin(mode, content, cwd):
    return subprocess.run(
        [sys.executable, '-m', 'psh', mode],
        input=content, capture_output=True, text=True,
        cwd=cwd, env=_env())


def _run_c(mode, content, cwd):
    return subprocess.run(
        [sys.executable, '-m', 'psh', mode, '-c', content],
        capture_output=True, text=True, cwd=cwd, env=_env())


class TestStdinAnalysisNeverExecutes:
    @pytest.mark.parametrize('mode', MODES)
    def test_no_side_effects(self, mode, tmp_path):
        r = _run_stdin(mode, SIDE_EFFECT_SCRIPT, tmp_path)
        assert not (tmp_path / 'marker.txt').exists(), \
            f"{mode} on stdin EXECUTED its input (marker file created)"
        assert 'SIDEEFFECT' not in r.stdout.splitlines(), \
            f"{mode} on stdin EXECUTED its input (echo output appeared)"

    @pytest.mark.parametrize('mode', MODES)
    def test_stdin_matches_dash_c(self, mode, tmp_path):
        """Identical content -> identical analysis output and exit code."""
        content = 'echo hello\nls | wc -l\n'
        stdin = _run_stdin(mode, content, tmp_path)
        ref = _run_c(mode, content, tmp_path)
        assert stdin.stdout == ref.stdout
        assert stdin.returncode == ref.returncode


class TestStdinSyntaxErrors:
    @pytest.mark.parametrize('mode', MODES)
    def test_exit_2_like_dash_c(self, mode, tmp_path):
        """A truncated construct exits 2 on stdin, exactly like the -c form."""
        r = _run_stdin(mode, 'if true; then\n', tmp_path)
        assert r.returncode == 2
        assert 'Traceback' not in r.stderr
        assert 'psh:' in r.stderr

    def test_validate_no_contradictory_summary(self, tmp_path):
        """--validate on bad stdin must not ALSO print the all-clear summary.

        The old divergent line-by-line implementation printed the syntax
        error, then "No issues found - AST is valid!", and exited 0.
        """
        r = _run_stdin('--validate', 'if true; then\n', tmp_path)
        assert 'No issues found' not in r.stdout
        assert r.returncode == 2


class TestStdinAnalysisOutput:
    def test_validate_clean(self, tmp_path):
        r = _run_stdin('--validate', 'if true; then echo x; fi\n', tmp_path)
        assert r.returncode == 0
        assert 'No issues found - AST is valid!' in r.stdout

    def test_format_pretty_prints(self, tmp_path):
        r = _run_stdin('--format', 'if true;    then echo x;fi\n', tmp_path)
        assert r.returncode == 0
        assert 'then' in r.stdout
        # The formatter prints the script; nothing was executed, so no bare
        # "x" output line from the echo.
        assert 'x' not in [line.strip() for line in r.stdout.splitlines()]

    def test_security_flags_real_issue_exit_1(self, tmp_path):
        r = _run_stdin('--security', 'rm -rf /\n', tmp_path)
        assert r.returncode == 1
        assert 'rm of /' in r.stdout

    def test_heredoc_body_is_data_on_stdin(self, tmp_path):
        """The heredoc-aware analysis parse applies to the stdin channel too."""
        r = _run_stdin('--security', 'cat <<END\nrm -rf /\nEND\n', tmp_path)
        assert r.returncode == 0
        assert 'No security issues found' in r.stdout

    def test_plain_stdin_still_executes(self, tmp_path):
        """No analysis flag: piped stdin is still executed normally."""
        r = subprocess.run(
            [sys.executable, '-m', 'psh'],
            input='echo ran > marker.txt\n', capture_output=True, text=True,
            cwd=tmp_path, env=_env())
        assert r.returncode == 0
        assert (tmp_path / 'marker.txt').read_text() == 'ran\n'
