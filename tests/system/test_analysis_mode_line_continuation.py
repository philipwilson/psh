"""Analysis modes (--validate/--format/... ) join line continuations first.

R18 T2-E (M-v1): the CLI analysis modes parsed raw file content without the
backslash-newline joining the execution path performs
(`SourceProcessor._preprocess_command`). The lexer does NOT collapse a
continuation in every context (a `\\`-newline right after `then`, or inside
`[[ ]]`), so `--validate` reported false syntax errors on scripts that execute
cleanly. `visitor_modes._parse_for_analysis` now runs
`process_line_continuations` first. Pinned against bash 5.2 (the scripts run).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, 'PYTHONPATH': str(REPO_ROOT)}

# Each script uses a backslash-newline continuation in a context the lexer does
# not join on its own; all are valid and execute successfully.
CONTINUATION_SCRIPTS = {
    'after_then': 'if true; then\\\n echo yes; fi\n',
    'inside_dbracket': '[[ 1 -eq 1 \\\n&& 2 -eq 2 ]] && echo ok\n',
    'in_pipeline': 'echo hi |\\\ncat\n',
    'in_command': 'echo one \\\ntwo three\n',
}


def _run(argv, script, tmp_path, name):
    path = tmp_path / name
    path.write_text(script)
    return subprocess.run([sys.executable, '-m', 'psh', *argv, str(path)],
                          capture_output=True, text=True, timeout=10, env=ENV)


@pytest.mark.parametrize("key", sorted(CONTINUATION_SCRIPTS))
@pytest.mark.parametrize("parser", ['rd', 'pc'])
def test_validate_accepts_continuations(key, parser, tmp_path):
    r = _run(['--parser', parser, '--validate'],
             CONTINUATION_SCRIPTS[key], tmp_path, f'{key}.sh')
    assert r.returncode == 0, (key, parser, r.stderr)
    assert 'syntax error' not in r.stderr.lower()
    assert 'Expected' not in r.stderr


@pytest.mark.parametrize("key", sorted(CONTINUATION_SCRIPTS))
def test_debug_ast_does_not_error_on_continuations(key, tmp_path):
    r = _run(['--debug-ast'], CONTINUATION_SCRIPTS[key], tmp_path, f'{key}.sh')
    assert r.returncode == 0, (key, r.stderr)


def test_execution_still_works(tmp_path):
    # Guard: the same scripts run correctly (the analysis path must agree).
    r = _run([], CONTINUATION_SCRIPTS['after_then'], tmp_path, 'exec.sh')
    assert r.returncode == 0
    assert r.stdout == 'yes\n'
