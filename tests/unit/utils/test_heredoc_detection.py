"""Unit tests for the shared heredoc-detection helpers.

These pin the single source of truth (`psh/utils/heredoc_detection.py`) that the
script/`-c`/stdin path and the interactive multiline path both use. Cases marked
"regression" caught a bug in one of the two former divergent copies.
"""

from psh.utils.heredoc_detection import (
    contains_heredoc,
    has_unclosed_heredoc,
    is_inside_expansion,
)


class TestHasUnclosedHeredoc:
    def test_open_heredoc(self):
        assert has_unclosed_heredoc("cat <<EOF") is True

    def test_closed_heredoc(self):
        assert has_unclosed_heredoc("cat <<EOF\nhi\nEOF") is False

    def test_dash_heredoc_closed_with_tabs(self):
        assert has_unclosed_heredoc("cat <<-EOF\n\thi\n\tEOF") is False

    def test_arithmetic_shift_is_not_heredoc(self):
        assert has_unclosed_heredoc("echo $((1<<2))") is False

    def test_bare_arithmetic_shift_is_not_heredoc(self):
        # Regression: the script-path copy treated `<< 2` here as a heredoc
        # with delimiter "2"; the bare (( )) arithmetic must be excluded.
        assert has_unclosed_heredoc("(( x << 2 ))") is False

    def test_mixed_arithmetic_and_real_heredoc(self):
        assert has_unclosed_heredoc("echo $((1<<2)) <<EOF") is True

    def test_mixed_bare_arith_and_closed_heredoc(self):
        # The `<< b` is arithmetic; the real heredoc is closed -> complete.
        assert has_unclosed_heredoc("(( a << b ))\ncat <<EOF\nhi\nEOF") is False

    def test_here_string_is_not_heredoc(self):
        # Regression: the interactive copy matched `<<` inside `<<<word` and
        # waited forever for a delimiter.
        assert has_unclosed_heredoc("cat <<<word") is False

    def test_heredoc_inside_command_sub_closed(self):
        assert has_unclosed_heredoc("x=$(cat <<EOF\nhi\nEOF\n)") is False

    def test_no_heredoc_operator(self):
        assert has_unclosed_heredoc("echo hello") is False

    def test_multiple_heredocs_one_open(self):
        assert has_unclosed_heredoc("cat <<A; cat <<B\nfoo\nA") is True

    def test_multiple_heredocs_all_closed(self):
        assert has_unclosed_heredoc("cat <<A; cat <<B\nfoo\nA\nbar\nB") is False


class TestIsInsideExpansion:
    def test_inside_arithmetic(self):
        line = "echo $((1<<2))"
        assert is_inside_expansion(line, line.index("<<")) is True

    def test_inside_bare_arithmetic(self):
        line = "(( x << 2 ))"
        assert is_inside_expansion(line, line.index("<<")) is True

    def test_inside_command_sub(self):
        line = "echo $(foo <<x)"
        assert is_inside_expansion(line, line.index("<<")) is True

    def test_inside_backticks(self):
        line = "echo `foo <<x`"
        assert is_inside_expansion(line, line.index("<<")) is True

    def test_outside_any_expansion(self):
        line = "cat <<EOF"
        assert is_inside_expansion(line, line.index("<<")) is False


class TestContainsHeredoc:
    def test_plain_heredoc(self):
        assert contains_heredoc("cat <<EOF") is True

    def test_arithmetic_only(self):
        assert contains_heredoc("echo $((1<<2))") is False

    def test_none(self):
        assert contains_heredoc("echo hi") is False
