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

from psh.lexer.heredoc_lexer import HeredocLexer


def tokenize_with_heredocs(source):
    """Drive ``HeredocLexer`` directly (raw tokens, no post-lex pipeline).

    The retired module-level ``heredoc_lexer.tokenize_with_heredocs`` was a
    thin wrapper around exactly this; these tests want the raw (un-fused,
    un-normalized) token stream, so they construct the lexer here.
    """
    return HeredocLexer(source).tokenize_with_heredocs()


def run_psh_script(script, cwd=None):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                          capture_output=True, text=True, cwd=cwd, timeout=15)


def body_of(heredocs, delim):
    """Body of the (first) collected heredoc whose COOKED terminator is
    *delim* — the LexedUnit map is id-keyed (ordinal identity)."""
    for _key, entry in sorted(heredocs.items()):
        if entry.spec.cooked == delim:
            return entry.collected.body
    raise AssertionError(f'no heredoc for {delim}: {dict(heredocs)}')


class TestHeredocLexerUnit:
    def test_basic_collection(self):
        tokens, hmap = tokenize_with_heredocs('cat <<EOF\nhello\nworld\nEOF\n')
        assert body_of(hmap, 'EOF') == 'hello\nworld\n'
        values = [t.value for t in tokens]
        assert 'cat' in values and 'hello' not in values

    def test_quoted_delimiter_flag(self):
        _, hmap = tokenize_with_heredocs('cat <<"EOF"\n$x\nEOF\n')
        entry = next(iter(hmap.values()))
        assert entry.spec.quoted is True
        assert entry.spec.raw == '"EOF"'
        assert entry.spec.cooked == 'EOF'

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

    def test_punctuation_delimiters(self):
        """Bash accepts almost any non-blank run as the delimiter word —
        glob chars, dots, dashes, leading punctuation, mid-word # — and the
        terminator is the same literal run (reappraisal #17 round-2)."""
        for delim in ('E*F', 'A?B', 'AB[cd]', 'E.F', 'E-F', '@X', 'E#F',
                      'E,F', 'E{F', 'E+F', '{abc}', '!', '123'):
            src = f'cat <<{delim}\nhello\n{delim}\necho after\n'
            tokens, hmap = tokenize_with_heredocs(src)
            assert body_of(hmap, delim) == 'hello\n', delim
            assert 'after' in [t.value for t in tokens], delim
        # A leading-dash delimiter needs a space (`<<-EOF` is the <<-
        # operator); `<<--EOF` is <<- with delimiter `-EOF`.
        _, hmap = tokenize_with_heredocs('cat << -EOF\nhello\n-EOF\n')
        assert body_of(hmap, '-EOF') == 'hello\n'
        _, hmap = tokenize_with_heredocs('cat <<--EOF\nhello\n-EOF\n')
        assert body_of(hmap, '-EOF') == 'hello\n'

    def test_brace_delimiter_not_brace_expanded(self):
        # `cat <<E{a,b}F` must NOT become delimiter words `EaF EbF`. Use the
        # PACKAGE entry point — the post-lex pipeline (TokenBraceExpander)
        # is where the delimiter word used to get expanded.
        from psh.lexer import tokenize_with_heredocs as package_twh
        tokens, hmap = package_twh('cat <<E{a,b}F\nhello\nE{a,b}F\n')
        values = [t.value for t in tokens]
        assert 'E{a,b}F' in values and 'EaF' not in values
        assert body_of(hmap, 'E{a,b}F') == 'hello\n'

    def test_brace_expansion_still_works_after_heredoc_delimiter(self):
        # Brace expansion moved to the Word stage (v0.678): tokenization keeps
        # `x{1,2}` as one WORD; it expands at execution time. The end-to-end
        # behavior (the line's non-delimiter words still brace-expand while the
        # heredoc body/delimiter stay literal) is verified in
        # tests/unit/lexer/test_heredoc_brace_expansion.py.
        from psh.lexer import tokenize_with_heredocs as package_twh
        tokens, _ = package_twh('cat <<EOF x{1,2}\nbody\nEOF\n')
        values = [t.value for t in tokens]
        assert 'x{1,2}' in values and 'x1' not in values

    def test_incomplete_heredoc_delimited_by_eof(self, capsys):
        """An unterminated heredoc is NOT dropped: like bash, the gathered
        lines become the body ("delimited by end-of-file") and a warning is
        printed to stderr. (It used to be silently excluded from the map —
        the command then ran with an EMPTY body, silent data loss.)"""
        _, hmap = tokenize_with_heredocs('cat <<EOF\nno terminator\n')
        assert body_of(hmap, 'EOF') == 'no terminator\n'
        err = capsys.readouterr().err
        assert ("warning: here-document at line 1 delimited by end-of-file "
                "(wanted `EOF')") in err

    def test_incomplete_heredoc_warning_suppressed_for_trials(self, capsys):
        from psh.lexer.heredoc_lexer import HeredocLexer
        lexer = HeredocLexer('cat <<EOF\nbody\n', warn_unterminated=False)
        _, hmap = lexer.tokenize_with_heredocs()
        assert body_of(hmap, 'EOF') == 'body\n'
        assert capsys.readouterr().err == ''

    def test_incomplete_second_heredoc_gets_empty_body(self, capsys):
        # bash content routing: the first pending heredoc keeps everything
        # gathered up to EOF; later pending heredocs get empty bodies.
        _, hmap = tokenize_with_heredocs('cat <<A <<B\nbody1\n')
        assert body_of(hmap, 'A') == 'body1\n'
        assert body_of(hmap, 'B') == ''
        err = capsys.readouterr().err
        assert "(wanted `A')" in err and "(wanted `B')" in err


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
