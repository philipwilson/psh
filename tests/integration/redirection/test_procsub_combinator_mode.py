"""Combinator-parser-mode pins for process-substitution redirects (r19-T5).

The golden --compare-bash harness drives -c through the RD parser only, so the
H1 node-carry fix (planner detects procsub structurally from the Word AST,
never by string-sniffing the expanded target) needs its own combinator-mode
regression pins — the campaign's mode-blind-pin lesson applied to parser mode.
"""
import subprocess
import sys


def _psh_combinator(cmd, cwd):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '--parser', 'combinator', '-c', cmd],
        capture_output=True, text=True, cwd=cwd)


def test_procsub_redirect_works_under_combinator(tmp_path):
    r = _psh_combinator('cat < <(echo hi)', tmp_path)
    assert r.returncode == 0
    assert r.stdout == 'hi\n'


def test_quoted_procsub_literal_is_a_filename_under_combinator(tmp_path):
    r = _psh_combinator("cat < '<(echo x)'", tmp_path)
    assert r.returncode == 1
    assert 'No such file' in r.stderr
    assert 'x' not in r.stdout
