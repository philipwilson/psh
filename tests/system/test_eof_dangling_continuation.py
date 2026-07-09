"""Trailing backslash(-newline) at end of input, per input mode.

Bash has TWO rules here, probe-verified vs bash 5.2.26 (tmp/contcarry/,
2026-07-09):

* A backslash-NEWLINE pair at EOF is an ordinary continuation in EVERY
  input mode — it joins with the empty remainder, so a script/-c string/
  eval string ending ``echo hi \\<LF>`` runs ``echo hi``.
* A DANGLING backslash (no newline after it) at true EOF splits by mode:
  STREAM inputs (a script file argument, a script on stdin, a ``/dev/fd``
  process-substitution script) DROP it; STRING inputs (``-c``, ``eval``,
  and ``source``/``.`` — bash reads a sourced file into a string) keep it
  as a literal word character.

psh used to treat every mode like ``-c`` (backslash always literal). The
``-c``/string rows are pinned in ``tests/behavioral/golden_cases.yaml``
(``contcarry_*``); this file pins the modes a ``-c`` golden cannot reach.

Known, deliberately-accepted divergences (see tmp/contcarry/ledger.md):
an unterminated heredoc whose body ends in a dangling backslash at a
stream input's EOF prints ``body \\n`` in psh vs bash's ``body `` (one
trailing-newline byte — psh's EOF-delimited bodies are always
newline-terminated); in string modes bash leaks its internal 0xFF EOF
sentinel into that body (a bash artifact psh does not reproduce).
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, 'PYTHONPATH': str(REPO_ROOT)}


def run_psh(*args, stdin_input=None, cwd=None):
    return subprocess.run(
        [sys.executable, '-m', 'psh', *args],
        capture_output=True, text=True, timeout=10, cwd=cwd, env=ENV,
        input=stdin_input if stdin_input is not None else '')


def write_script(tmp_path, content, name='s.sh'):
    path = tmp_path / name
    # newline='' so the exact bytes (including a missing final newline)
    # reach the file verbatim.
    with open(path, 'w', newline='') as f:
        f.write(content)
    return str(path)


class TestScriptFileMode:
    """A script file argument is a stream input: dangling backslash drops."""

    def test_bs_newline_at_eof_joins(self, tmp_path):
        script = write_script(tmp_path, 'echo hi \\\n')
        result = run_psh(script)
        assert (result.returncode, result.stdout) == (0, 'hi\n')

    def test_dangling_bs_no_newline_dropped(self, tmp_path):
        script = write_script(tmp_path, 'echo hi \\')
        result = run_psh(script)
        assert (result.returncode, result.stdout) == (0, 'hi\n')

    def test_dangling_bs_no_space_dropped(self, tmp_path):
        script = write_script(tmp_path, 'echo hi\\')
        result = run_psh(script)
        assert (result.returncode, result.stdout) == (0, 'hi\n')

    def test_file_of_only_backslash_runs_nothing(self, tmp_path):
        script = write_script(tmp_path, '\\')
        result = run_psh(script)
        assert (result.returncode, result.stdout, result.stderr) == (0, '', '')

    def test_operator_then_dangling_bs_is_syntax_error(self, tmp_path):
        # bash: `echo a && \<EOF>` never runs echo — rc 2 syntax error.
        script = write_script(tmp_path, 'echo a && \\')
        result = run_psh(script)
        assert result.returncode == 2
        assert result.stdout == ''

    def test_escaped_backslash_stays(self, tmp_path):
        script = write_script(tmp_path, 'echo hi \\\\\n')
        result = run_psh(script)
        assert (result.returncode, result.stdout) == (0, 'hi \\\n')

    def test_mid_file_continuation_control(self, tmp_path):
        script = write_script(tmp_path, 'echo hi \\\nthere\n')
        result = run_psh(script)
        assert (result.returncode, result.stdout) == (0, 'hi there\n')


class TestStdinScriptMode:
    """A script on stdin is a stream input — and must stay LAZY (v0.666)."""

    def test_bs_newline_at_eof_joins(self):
        result = run_psh(stdin_input='echo hi \\\n')
        assert (result.returncode, result.stdout) == (0, 'hi\n')

    def test_dangling_bs_no_newline_dropped(self):
        result = run_psh(stdin_input='echo hi \\')
        assert (result.returncode, result.stdout) == (0, 'hi\n')

    def test_complete_cmd_then_dangling(self):
        result = run_psh(stdin_input='echo one\necho two \\\n')
        assert (result.returncode, result.stdout) == (0, 'one\ntwo\n')

    def test_trailing_continuation_keeps_stdin_lazy(self):
        # `read` consumes the DATA line even though the final command line
        # ends in a continuation — the trailing backslash must not force a
        # drain of fd 0 (bash: got DATA).
        result = run_psh(stdin_input='read v\nDATA\necho got $v \\\n')
        assert (result.returncode, result.stdout) == (0, 'got DATA\n')

    def test_final_empty_line_not_a_phantom_command(self):
        # StdinInput now reports a newline-terminated final line exactly
        # like FileInput (one empty final line); it must not execute
        # anything or change rc.
        result = run_psh(stdin_input='echo hi\n')
        assert (result.returncode, result.stdout, result.stderr) == (0, 'hi\n', '')

    def test_heredoc_eof_trailing_blank_body_lines_kept(self):
        # flush() used to rstrip the blank body lines away (bash keeps them).
        result = run_psh(stdin_input='cat <<XX\nbody\n\n\n')
        assert result.returncode == 0
        assert result.stdout == 'body\n\n\n'
        assert 'delimited by end-of-file' in result.stderr


class TestSourceMode:
    """source/. is a bash STRING input: a dangling backslash stays literal."""

    def test_dangling_bs_kept_literal(self, tmp_path):
        script = write_script(tmp_path, 'echo hi \\')
        result = run_psh('-c', f'. {script}')
        assert (result.returncode, result.stdout) == (0, 'hi \\\n')

    def test_bs_newline_at_eof_joins(self, tmp_path):
        # The pair form is a continuation in every mode, source included.
        script = write_script(tmp_path, 'echo hi \\\n')
        result = run_psh('-c', f'. {script}')
        assert (result.returncode, result.stdout) == (0, 'hi\n')

    def test_same_file_differs_by_mode(self, tmp_path):
        # THE mode split, one file: as a script argument the dangling
        # backslash drops; sourced, it is literal (bash 5.2 does the same).
        script = write_script(tmp_path, 'echo hi \\')
        as_script = run_psh(script)
        sourced = run_psh('-c', f'. {script}')
        assert as_script.stdout == 'hi\n'
        assert sourced.stdout == 'hi \\\n'


def run_psh_eval(code):
    """Run `eval "$CODE"` with CODE delivered via the environment, so the
    eval'd string's exact bytes (trailing backslash included) are preserved."""
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'eval "$CODE"'],
        capture_output=True, text=True, timeout=10,
        env={**ENV, 'CODE': code}, input='')


class TestEvalMode:
    """eval is a string input: dangling backslash literal, pair joins."""

    def test_dangling_bs_kept_literal(self):
        result = run_psh_eval('echo hi \\')
        assert (result.returncode, result.stdout) == (0, 'hi \\\n')

    def test_bs_newline_at_eof_joins(self):
        result = run_psh_eval('echo hi \\\n')
        assert (result.returncode, result.stdout) == (0, 'hi\n')


class TestHeredocEofBodies:
    """EOF-delimited heredoc bodies keep their bytes; unquoted bodies
    resolve a trailing continuation like bash (modulo the ledgered
    one-byte S18 corner, pinned here as psh's documented behavior)."""

    def test_unquoted_body_bs_newline_joins(self, tmp_path):
        script = write_script(tmp_path, 'cat <<XX\nbody \\\n')
        result = run_psh(script)
        assert result.returncode == 0
        assert result.stdout == 'body \n'

    def test_quoted_body_keeps_backslash(self, tmp_path):
        script = write_script(tmp_path, "cat <<'XX'\nbody \\\n")
        result = run_psh(script)
        assert result.returncode == 0
        assert result.stdout == 'body \\\n'

    def test_multi_continued_body_joins_at_eof(self, tmp_path):
        script = write_script(tmp_path, 'cat <<XX\nb1 \\\nb2 \\\n')
        result = run_psh(script)
        assert result.returncode == 0
        assert result.stdout == 'b1 b2 \n'

    def test_trailing_blank_body_lines_kept(self, tmp_path):
        script = write_script(tmp_path, 'cat <<XX\nbody\n\n\n')
        result = run_psh(script)
        assert result.returncode == 0
        assert result.stdout == 'body\n\n\n'

    def test_s18_stream_corner_documented(self, tmp_path):
        # LEDGERED divergence (tmp/contcarry/ledger.md): bash emits
        # 'body ' (no trailing newline); psh's EOF-delimited bodies are
        # always newline-terminated -> 'body \n'. The backslash itself
        # IS dropped (stream input), which is the load-bearing part.
        script = write_script(tmp_path, 'cat <<XX\nbody \\')
        result = run_psh(script)
        assert result.returncode == 0
        assert result.stdout == 'body \n'

    def test_s18_string_corner_documented(self):
        # LEDGERED: bash -c keeps the backslash and leaks a 0xFF EOF
        # sentinel byte into the body ('body \<0xFF>\n'); psh keeps the
        # backslash without the artifact byte.
        result = run_psh('-c', 'cat <<XX\nbody \\')
        assert result.returncode == 0
        assert result.stdout == 'body \\\n'


class TestValidateMode:
    """--validate / -n analysis sees the same per-mode text execution does."""

    def test_script_dangling_bs_validates_clean(self, tmp_path):
        script = write_script(tmp_path, 'echo hi \\')
        result = run_psh('--validate', script)
        assert result.returncode == 0
