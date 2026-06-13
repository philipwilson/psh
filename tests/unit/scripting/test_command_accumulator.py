"""CommandAccumulator unit tests.

The accumulator is the ONE completeness oracle shared by the script/`-c`
reader (source_processor) and the interactive PS2 loop (multiline_handler).
These tests pin the feed() contract: which buffers are Complete, which are
NeedMore, and that each NeedMore carries the honest hint the lexer/parser
actually produced (heredoc delimiter, quote character, unclosed-expansion
kind, open-construct trail).
"""

import pytest

from psh.scripting.command_accumulator import (
    CommandAccumulator,
    Complete,
    HintKind,
    NeedMore,
)


@pytest.fixture
def acc(shell):
    shell.state.is_script_mode = True  # no history expansion in the trial
    return CommandAccumulator(shell)


def feed_all(acc, lines):
    """Feed every line; return the last result."""
    result = None
    for line in lines:
        result = acc.feed(line)
    return result


class TestCompleteCommands:
    def test_simple_command(self, acc):
        result = acc.feed("echo hello")
        assert isinstance(result, Complete)
        assert result.text == "echo hello"
        assert result.error is None

    def test_complete_resets_buffer(self, acc):
        acc.feed("echo one")
        assert acc.is_empty
        result = acc.feed("echo two")
        assert isinstance(result, Complete)
        assert result.text == "echo two"

    def test_multiline_accumulation(self, acc):
        assert isinstance(acc.feed("if true; then"), NeedMore)
        assert isinstance(acc.feed("  echo hello"), NeedMore)
        result = acc.feed("fi")
        assert isinstance(result, Complete)
        assert result.text == "if true; then\n  echo hello\nfi"

    def test_trial_parse_ast_returned(self, acc):
        """The trial parse's AST rides along so execution need not re-parse."""
        result = acc.feed("echo hello")
        assert result.ast is not None
        assert result.tokens is not None
        assert result.source == "echo hello"

    def test_brace_expansion_word_is_complete(self, acc):
        """`echo {a,` executes immediately (bash-probed: prints `{a,`).

        The old interactive heuristic hand-counted braces and wrongly
        prompted for more input; psh's own script mode always executed.
        """
        result = acc.feed("echo {a,")
        assert isinstance(result, Complete)

    def test_escaped_space_is_complete(self, acc):
        """`echo \\ ` is an escaped space, not a line continuation
        (bash-probed: prints one space immediately)."""
        result = acc.feed("echo \\ ")
        assert isinstance(result, Complete)

    def test_real_syntax_error_is_complete_with_error(self, acc):
        """A real syntax error means the command is complete but invalid."""
        result = acc.feed("echo )")
        assert isinstance(result, Complete)
        assert result.error is not None
        assert result.ast is None


class TestLineContinuation:
    def test_trailing_backslash_needs_more(self, acc):
        result = acc.feed("echo hello \\")
        assert isinstance(result, NeedMore)
        assert result.hint.kind is HintKind.LINE_CONTINUATION

    def test_escaped_backslash_is_complete(self, acc):
        assert isinstance(acc.feed("echo hello \\\\"), Complete)

    def test_continuation_then_completion(self, acc):
        acc.feed("echo hello \\")
        result = acc.feed("world")
        assert isinstance(result, Complete)
        assert result.text == "echo hello \\\nworld"
        # the parsed source has the continuation joined
        assert result.source == "echo hello world"


class TestUnclosedQuotes:
    def test_double_quote(self, acc):
        result = acc.feed('echo "unclosed')
        assert isinstance(result, NeedMore)
        assert result.hint.kind is HintKind.UNCLOSED_QUOTE
        assert result.hint.detail == '"'

    def test_single_quote(self, acc):
        result = acc.feed("echo 'unclosed")
        assert result.hint.kind is HintKind.UNCLOSED_QUOTE
        assert result.hint.detail == "'"

    def test_ansi_c_quote(self, acc):
        result = acc.feed("echo $'unclosed")
        assert result.hint.kind is HintKind.UNCLOSED_QUOTE
        assert result.hint.detail == "$'"

    def test_quote_closed_across_lines(self, acc):
        acc.feed('echo "one')
        result = acc.feed('two"')
        assert isinstance(result, Complete)
        assert result.text == 'echo "one\ntwo"'


class TestUnclosedExpansions:
    @pytest.mark.parametrize("text,kind", [
        ("echo $(", "command"),
        ("echo $(echo hi", "command"),
        ("echo ${x", "parameter"),
        ("echo $((1+", "arithmetic"),
        ("echo `foo", "backtick"),
    ])
    def test_unclosed_expansion_kinds(self, acc, text, kind):
        result = acc.feed(text)
        assert isinstance(result, NeedMore)
        assert result.hint.kind is HintKind.UNCLOSED_EXPANSION
        assert result.hint.detail == kind

    def test_multiline_command_substitution(self, acc):
        acc.feed("echo $(")
        acc.feed("echo hi")
        result = acc.feed(")")
        assert isinstance(result, Complete)


class TestHeredocs:
    def test_heredoc_needs_body(self, acc):
        result = acc.feed("cat <<EOF")
        assert isinstance(result, NeedMore)
        assert result.hint.kind is HintKind.HEREDOC
        assert result.hint.detail == "EOF"
        assert acc.pending_heredoc

    def test_heredoc_completes_at_delimiter(self, acc):
        feed_all(acc, ["cat <<EOF", "line1", "line2"])
        result = acc.feed("EOF")
        assert isinstance(result, Complete)
        assert not acc.pending_heredoc

    def test_heredoc_body_close_paren_line(self, acc):
        """A heredoc body line `)` is body text, not a parse error
        (the v0.306 case: the trial must lex with heredoc support)."""
        feed_all(acc, ["cat <<EOF", ")"])
        result = acc.feed("EOF")
        assert isinstance(result, Complete)
        assert result.error is None
        assert result.ast is not None

    def test_heredoc_strip_tabs(self, acc):
        feed_all(acc, ["cat <<-EOF", "\tline1"])
        result = acc.feed("\tEOF")
        assert isinstance(result, Complete)

    def test_multiple_heredocs(self, acc):
        result = feed_all(acc, ["cat <<A && cat <<B", "one", "A"])
        assert isinstance(result, NeedMore)
        assert result.hint.kind is HintKind.HEREDOC
        assert result.hint.detail == "B"
        assert isinstance(feed_all(acc, ["two", "B"]), Complete)


class TestIncompleteStructures:
    @pytest.mark.parametrize("lines,constructs", [
        (["if true"], ("if",)),
        (["if true; then"], ("then",)),
        (["if true; then echo; elif false"], ("elif",)),
        (["if true; then echo; else"], ("else",)),
        (["while true; do"], ("while",)),
        (["until false"], ("until",)),
        (["for i in 1 2"], ("for",)),
        (["for i in 1 2; do"], ("for",)),
        (["case x in"], ("case",)),
        (["select s in a b"], ("select",)),
        (["( echo hi"], ("subshell",)),
        (["{ echo hi"], ("brace",)),
        (["[[ -n x"], ("test",)),
        (["f() {"], ("brace",)),
        (["function g {"], ("function", "brace")),
        (["if true; then", "while true; do"], ("then", "while")),
    ])
    def test_open_construct_trail(self, acc, lines, constructs):
        result = feed_all(acc, lines)
        assert isinstance(result, NeedMore)
        assert result.hint.kind is HintKind.INCOMPLETE_STRUCTURE
        assert result.hint.constructs == constructs

    def test_data_words_are_not_constructs(self, acc):
        """Keyword-shaped DATA never fakes a construct (the old interactive
        pseudo-parser split on whitespace: `echo if ; while true` showed
        'if while> '; `for x in done ; do` lost its for)."""
        result = acc.feed("echo if ; while true")
        assert result.hint.constructs == ("while",)
        acc.reset()
        result = acc.feed("for x in done ; do")
        assert result.hint.constructs == ("for",)

    def test_trailing_operator_needs_more(self, acc):
        result = acc.feed("echo hello &&")
        assert isinstance(result, NeedMore)
        assert result.hint.kind is HintKind.INCOMPLETE_STRUCTURE
        assert result.hint.constructs == ()


class TestBufferManagement:
    def test_reset_clears_state(self, acc):
        acc.feed("if true; then")
        assert not acc.is_empty
        acc.reset()
        assert acc.is_empty
        assert not acc.pending_heredoc
        # a fresh command parses on its own
        assert isinstance(acc.feed("echo hello"), Complete)

    def test_flush_returns_pending_buffer_unparsed(self, acc):
        """EOF mid-construct: the buffer is handed back for the execution
        path to parse (and report 'unexpected end of input')."""
        acc.feed("if true; then")
        result = acc.flush()
        assert isinstance(result, Complete)
        assert result.text == "if true; then"
        assert result.ast is None
        assert acc.is_empty

    def test_empty_line_is_complete(self, acc):
        result = acc.feed("")
        assert isinstance(result, Complete)
        assert result.text == ""
