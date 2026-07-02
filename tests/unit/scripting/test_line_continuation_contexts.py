"""Context-aware line-continuation preprocessing (reappraisal #15, A5).

``process_line_continuations`` removes backslash-newline pairs from command
text BEFORE the lexer runs, so it must know which backslashes are not
continuations at all: comment text (the newline ends the comment), quoted
heredoc bodies (every character is literal), and single-quoted strings.
Unquoted heredoc bodies DO join, like bash. These tests pin the
per-context decisions directly against the function; the end-to-end
script/-c/stdin parity lives in tests/integration/scripting/.
"""

from psh.scripting.input_preprocessing import process_line_continuations
from psh.utils.heredoc_detection import (
    open_heredoc_delimiters,
    scan_line_heredoc_markers,
)


class TestCommentContext:
    def test_comment_trailing_backslash_not_joined(self):
        text = "# comment ends in backslash \\\necho survived"
        assert process_line_continuations(text) == text

    def test_comment_after_command_not_joined(self):
        text = "echo one # trailing \\\necho two"
        assert process_line_continuations(text) == text

    def test_comment_inside_construct_not_joined(self):
        text = "if true; then\n# c \\\necho body\nfi"
        assert process_line_continuations(text) == text

    def test_comment_inside_command_sub_not_joined(self):
        # bash: '#' after whitespace inside $( ) is a comment to end of line
        text = "echo $(echo a # c \\\necho b)"
        assert process_line_continuations(text) == text

    def test_hash_mid_word_is_not_a_comment(self):
        assert (process_line_continuations("echo a#b \\\nc")
                == "echo a#b c")

    def test_param_length_expansion_is_not_a_comment(self):
        assert (process_line_continuations("echo ${#a[@]} \\\n4")
                == "echo ${#a[@]} 4")

    def test_comment_quote_does_not_poison_later_joins(self):
        # The apostrophe in the comment must not open a "single quote"
        # that would suppress the next line's real continuation.
        assert (process_line_continuations("echo hi # don't\necho a \\\nb")
                == "echo hi # don't\necho a b")


class TestHeredocBodyContext:
    def test_quoted_delimiter_body_kept_verbatim(self):
        text = "cat <<'EOF'\na\\\nb\nEOF\necho after"
        assert process_line_continuations(text) == text

    def test_double_quoted_delimiter_body_kept_verbatim(self):
        text = 'cat <<"EOF"\na\\\nb\nEOF\necho after'
        assert process_line_continuations(text) == text

    def test_backslash_escaped_delimiter_body_kept_verbatim(self):
        text = "cat <<\\EOF\na\\\nb\nEOF\necho after"
        assert process_line_continuations(text) == text

    def test_quoted_delimiter_with_tab_stripping(self):
        text = "cat <<-'EOF'\n\ta\\\n\tb\n\tEOF\necho after"
        assert process_line_continuations(text) == text

    def test_quoted_body_backslash_before_terminator(self):
        # The terminator on the next line must still be recognized.
        text = "cat <<'EOF'\na\\\nEOF\necho after"
        assert process_line_continuations(text) == text

    def test_unquoted_delimiter_body_joins(self):
        assert (process_line_continuations("cat <<EOF\na\\\nb\nEOF")
                == "cat <<EOF\nab\nEOF")

    def test_unquoted_body_join_fuses_next_terminator(self):
        # bash removes \<newline> in unquoted bodies while reading them,
        # so a terminator on the joined-away line becomes body text.
        assert (process_line_continuations("cat <<EOF\na\\\nEOF\nb")
                == "cat <<EOF\naEOF\nb")

    def test_terminator_with_trailing_space_is_body(self):
        text = "cat <<'EOF'\nx\\\nEOF \nEOF\necho after"
        assert process_line_continuations(text) == text

    def test_sequential_bodies_track_their_own_quoting(self):
        text = "cat <<'A' <<B\nx\\\ny\nA\np\\\nq\nB"
        assert (process_line_continuations(text)
                == "cat <<'A' <<B\nx\\\ny\nA\npq\nB")

    def test_command_after_heredoc_still_joins(self):
        assert (process_line_continuations(
                    "cat <<'EOF'\nbody\nEOF\necho a \\\nb")
                == "cat <<'EOF'\nbody\nEOF\necho a b")

    def test_body_quote_does_not_poison_later_joins(self):
        # An apostrophe in a heredoc body is body text, not a quote.
        assert (process_line_continuations(
                    "cat <<EOF\ndon't\nEOF\necho a \\\nb")
                == "cat <<EOF\ndon't\nEOF\necho a b")

    def test_heredoc_marker_in_comment_is_command_text(self):
        assert (process_line_continuations("echo hi # <<EOF\necho a \\\nb")
                == "echo hi # <<EOF\necho a b")


class TestExistingBehaviorUnchanged:
    def test_double_quote_continuation_still_joins(self):
        assert (process_line_continuations('echo "a \\\nb"')
                == 'echo "a b"')

    def test_single_quote_still_literal(self):
        text = "echo 'a \\\nb'"
        assert process_line_continuations(text) == text

    def test_crlf_continuation_still_joins(self):
        assert (process_line_continuations("echo a \\\r\nb")
                == "echo a b")

    def test_trailing_backslash_at_eof_kept(self):
        assert process_line_continuations("echo hello\\") == "echo hello\\"

    def test_escaped_backslash_before_newline_not_joined(self):
        text = "echo a\\\\\nb"
        assert process_line_continuations(text) == text


class TestHeredocMarkerScan:
    """The shared per-line marker scan (also used by the accumulator)."""

    def test_marker_reports_quoting(self):
        markers, quote = scan_line_heredoc_markers("cat <<'A' <<B <<-\\C")
        assert markers == [("A", False, True), ("B", False, False),
                           ("C", True, True)]
        assert quote is None

    def test_marker_in_comment_ignored(self):
        markers, _ = scan_line_heredoc_markers("echo hi # <<EOF")
        assert markers == []

    def test_comment_quote_excluded_from_carried_state(self):
        _, quote = scan_line_heredoc_markers("echo hi # don't")
        assert quote is None

    def test_open_heredoc_delimiters_ignores_comment_marker(self):
        assert open_heredoc_delimiters("echo hi # <<EOF") == []
