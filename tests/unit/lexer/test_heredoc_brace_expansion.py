"""
Tests for brace expansion on command lines that contain heredocs.

Behavior guard (bash 5.2): a command line containing a heredoc must still
brace-expand its command part (`cat <<EOF; echo {a,b}` prints `a b`), and the
heredoc BODY must stay literal. Since v0.678 brace expansion is a WORD-stage
step, not a tokenize-time pass, so tokenization keeps `{a,b}` intact regardless
of heredocs — the behavior is verified end-to-end by
TestHeredocBraceExpansionEndToEnd below.
"""

import subprocess
import sys

from psh.lexer import tokenize_with_heredocs


class TestTokenizeWithHeredocsKeepsBracesIntact:
    def test_command_braces_kept_as_word(self):
        # No token-level expansion: `{a,b}` stays one WORD; the Word stage
        # expands it at execution time.
        tokens, heredoc_map = tokenize_with_heredocs(
            'cat <<EOF; echo {a,b}\nhi\nEOF\n')
        values = [t.value for t in tokens]
        assert '{a,b}' in values
        assert 'a' not in values

    def test_heredoc_body_not_brace_expanded(self):
        tokens, heredoc_map = tokenize_with_heredocs(
            'cat <<EOF\n{x,y}\nEOF\n')
        bodies = ''.join(str(v) for v in heredoc_map.values())
        assert '{x,y}' in bodies

    def test_sequence_braces_kept_as_word(self):
        tokens, _ = tokenize_with_heredocs(
            'cat <<EOF; echo {1..3}\nhi\nEOF\n')
        values = [t.value for t in tokens]
        assert '{1..3}' in values
        assert '2' not in values


class TestHeredocBraceExpansionEndToEnd:
    @staticmethod
    def _run_psh_script(script):
        return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                              capture_output=True, text=True)

    def test_heredoc_then_brace_expansion(self):
        result = self._run_psh_script('cat <<EOF; echo {a,b}\nhi\nEOF\n')
        assert result.stdout == 'hi\na b\n'
        assert result.stderr == ''

    def test_heredoc_body_stays_literal(self):
        result = self._run_psh_script('cat <<EOF\n{x,y}\nEOF\necho {1..3}\n')
        assert result.stdout == '{x,y}\n1 2 3\n'

    def test_tab_stripping_heredoc_with_braces(self):
        result = self._run_psh_script(
            'cat <<-EOF; echo pre{1,2}post\n\tindented\nEOF\n')
        assert result.stdout == 'indented\npre1post pre2post\n'
