"""`$LINENO` is correct when psh runs a SCRIPT FILE (the FileInput path).

The conformance suite exercises LINENO via `-c`; this pins the file path,
where the source processor offsets each statement's buffer-relative parser
stamp to its absolute file line. Compares psh against bash on the same temp
script files (matching exact stdout). See CHANGELOG v0.485.0.
"""

import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path


def _run(shell_cmd, path):
    return subprocess.run(shell_cmd + [path], capture_output=True, text=True)


def _assert_matches_bash(tmp_path, body):
    path = tmp_path / 's.sh'
    path.write_text(body)
    psh = _run([sys.executable, '-m', 'psh'], str(path))
    bash = _run([BASH], str(path))
    assert psh.returncode == bash.returncode
    assert psh.stdout == bash.stdout, (
        f"\nscript:\n{body}\npsh : {psh.stdout!r}\nbash: {bash.stdout!r}")


class TestLinenoScriptFile:
    def test_top_level_with_blanks_and_comments(self, tmp_path):
        _assert_matches_bash(
            tmp_path,
            'echo $LINENO\n\n# comment\necho $LINENO\necho $LINENO\n')

    def test_compound_constructs(self, tmp_path):
        _assert_matches_bash(
            tmp_path,
            'echo $LINENO\n'
            'if true; then\n  echo $LINENO\nfi\n'
            'for i in 1 2; do\n  echo $LINENO\ndone\n'
            'echo $LINENO\n')

    def test_function_reports_definition_line(self, tmp_path):
        # The function body lines (3, 4) are baked at definition time and are
        # reported on every call, regardless of the call-site line (8, 10).
        _assert_matches_bash(
            tmp_path,
            'echo top $LINENO\n'
            'myfunc() {\n'
            '  echo a $LINENO\n'
            '  echo b $LINENO\n'
            '}\n'
            '\n'
            'echo before $LINENO\n'
            'myfunc\n'
            'echo after $LINENO\n'
            'myfunc\n')

    def test_shebang_comment_does_not_shift_lines(self, tmp_path):
        # A `#!` first line is a comment but still occupies line 1, so the
        # following statements are on lines 2, 3 (not 1, 2).
        _assert_matches_bash(
            tmp_path,
            '#!/bin/sh\necho $LINENO\necho $LINENO\n')

    def test_lineno_not_shifted_by_preceding_continuation(self, tmp_path):
        # Reappraisal #16 Tier-2: each backslash-newline continuation used to
        # subtract 1 from every LATER $LINENO (pre-join happened before line
        # numbering). Physical lines must be preserved: bash reports 3, 4.
        _assert_matches_bash(
            tmp_path,
            ': \\\n:\necho $LINENO\necho $LINENO\n')

    def test_lineno_not_shifted_by_two_continuations(self, tmp_path):
        # A command spanning three physical lines (two continuations); the
        # following echoes are on physical lines 4 and 5.
        _assert_matches_bash(
            tmp_path,
            ': \\\n\\\n:\necho $LINENO\necho $LINENO\n')

    def test_lineno_of_spanning_command(self, tmp_path):
        # The command starting on line 2 spans to line 3; the next echo is on
        # physical line 4.
        _assert_matches_bash(
            tmp_path,
            'echo $LINENO\ntrue \\\n  arg\necho $LINENO\n')
