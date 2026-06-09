"""
Unit tests for the heredoc lexer (rewritten in v0.265.0).

The previous implementation re-lexed each physical line with a fresh
ModularLexer, discarding cross-line state — any multi-line construct
sharing a command with a heredoc broke ("Unclosed quote"). The new design
classifies lines (command vs body) and tokenizes the joined command text
once. These are the first unit tests for the heredoc modules (previously
0% coverage). Expectations verified against bash 5.2.
"""

import subprocess
import sys

from psh.lexer.heredoc_lexer import tokenize_with_heredocs


def run_psh_script(script, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                          capture_output=True, text=True, cwd=cwd, timeout=15)


def body_of(heredoc_map, delim):
    for key, info in heredoc_map.items():
        if key.endswith('_' + delim):
            return info['content']
    raise AssertionError(f'no heredoc for {delim}: {list(heredoc_map)}')


class TestHeredocLexerUnit:
    def test_basic_collection(self):
        tokens, hmap = tokenize_with_heredocs('cat <<EOF\nhello\nworld\nEOF\n')
        assert body_of(hmap, 'EOF') == 'hello\nworld\n'
        values = [t.value for t in tokens]
        assert 'cat' in values and 'hello' not in values

    def test_quoted_delimiter_flag(self):
        _, hmap = tokenize_with_heredocs('cat <<"EOF"\n$x\nEOF\n')
        key = next(iter(hmap))
        assert hmap[key]['quoted'] is True

    def test_strip_tabs(self):
        _, hmap = tokenize_with_heredocs('cat <<-EOF\n\tindented\n\tEOF\n')
        assert body_of(hmap, 'EOF') == 'indented\n'

    def test_two_heredocs_in_order(self):
        _, hmap = tokenize_with_heredocs(
            'cat <<A <<B\na-body\nA\nb-body\nB\n')
        assert body_of(hmap, 'A') == 'a-body\n'
        assert body_of(hmap, 'B') == 'b-body\n'

    def test_quoted_marker_is_not_a_heredoc(self):
        tokens, hmap = tokenize_with_heredocs('echo "<<EOF" ok\n')
        assert hmap == {}

    def test_command_after_heredoc_lines(self):
        tokens, hmap = tokenize_with_heredocs('cat <<EOF\nbody\nEOF\necho tail\n')
        values = [t.value for t in tokens]
        assert 'tail' in values
        assert body_of(hmap, 'EOF') == 'body\n'

    def test_incomplete_heredoc_excluded(self):
        _, hmap = tokenize_with_heredocs('cat <<EOF\nno terminator\n')
        assert hmap == {}


class TestHeredocCrossLineState:
    """The cases the per-line re-lexing design broke."""

    def test_multiline_string_with_heredoc(self):
        """Regression: used to die with "Unclosed quote"."""
        result = run_psh_script('cat <<EOF && echo "two\nbody\nEOF\nwords"')
        # bash: the command continues through the multi-line string, so the
        # heredoc body region is empty and echo prints all four pieces.
        assert result.stdout == 'two\nbody\nEOF\nwords\n'

    def test_multiline_string_closing_before_heredoc_lines(self):
        result = run_psh_script('echo "a\nb"; cat <<EOF\nbody\nEOF')
        assert result.stdout == 'a\nb\nbody\n'

    def test_case_statement_with_heredoc(self):
        result = run_psh_script(
            'case x in\nx) cat <<EOF\nmatched\nEOF\n;;\nesac')
        assert result.stdout == 'matched\n'

    def test_heredoc_then_quoted_marker_text(self):
        result = run_psh_script('echo "<<EOF" ok')
        assert result.stdout == '<<EOF ok\n'
