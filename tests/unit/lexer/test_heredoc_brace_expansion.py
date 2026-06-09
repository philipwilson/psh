"""
Tests for brace expansion on command lines that contain heredocs.

Regression guard: tokenize_with_heredocs() omitted the TokenBraceExpander
pass that tokenize() performs, so any command line containing a heredoc
silently lost brace expansion (`cat <<EOF; echo {a,b}` printed `{a,b}`).
Verified against bash 5.2.
"""

import subprocess
import sys

from psh.lexer import tokenize_with_heredocs


class TestTokenizeWithHeredocsBraceExpansion:
    def test_brace_expansion_applied(self):
        tokens, heredoc_map = tokenize_with_heredocs(
            'cat <<EOF; echo {a,b}\nhi\nEOF\n')
        values = [t.value for t in tokens]
        assert 'a' in values
        assert 'b' in values
        assert '{a,b}' not in values

    def test_heredoc_body_not_brace_expanded(self):
        tokens, heredoc_map = tokenize_with_heredocs(
            'cat <<EOF\n{x,y}\nEOF\n')
        bodies = ''.join(str(v) for v in heredoc_map.values())
        assert '{x,y}' in bodies

    def test_sequence_expansion_applied(self):
        tokens, _ = tokenize_with_heredocs(
            'cat <<EOF; echo {1..3}\nhi\nEOF\n')
        values = [t.value for t in tokens]
        assert [v for v in values if v in ('1', '2', '3')] == ['1', '2', '3']
        assert '{1..3}' not in values


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
