"""Unit tests for the shared heredoc-detection helpers.

These pin the single source of truth (`psh/utils/heredoc_detection.py`) that the
script/`-c`/stdin path and the interactive multiline path both use. Cases marked
"regression" caught a bug in one of the two former divergent copies.
"""

import pytest

from psh.utils.heredoc_detection import (
    contains_heredoc,
    has_unclosed_heredoc,
    is_inside_expansion,
    open_heredoc_specs,
    scan_line_heredoc_markers,
    unquote_heredoc_delimiter,
)


class TestUnquoteHeredocDelimiter:
    """Direct pins on THE delimiter-word rule (r19-T4 M2 convergence).

    Expectations are the bash 5.2 probe battery: for each raw delimiter
    spelling, which terminator line closes the heredoc and whether the body
    is literal. The end-to-end halves live in the heredoc_delimiter_* goldens
    (tests/behavioral/golden_cases.yaml)."""

    @pytest.mark.parametrize("raw,literal,quoted", [
        ("EOF", "EOF", False),
        ("'EOF'", "EOF", True),
        ('"EOF"', "EOF", True),
        ('E"O"F', "EOF", True),
        ("E\\OF", "EOF", True),
        ("$EOF", "$EOF", False),          # unquoted $ is ordinary text
        ('"EO F"', "EO F", True),
        ("EO\\ F", "EO F", True),
        ("\\EOF", "EOF", True),
        ("E\"O\"'F'", "EOF", True),
        # double quotes: backslash escapes ONLY $ ` " \ — literal otherwise
        ('"A\\B"', "A\\B", True),          # the drifted case (two copies said AB)
        ('"A\\\\B"', "A\\B", True),
        ('"A\\"B"', 'A"B', True),
        ('"A\\$B"', "A$B", True),
        # single quotes: contents verbatim
        ("'A\\B'", "A\\B", True),
        ("'A\\\\B'", "A\\\\B", True),
        # ANSI-C $'...': escapes decoded (campaign S2 / reappraisal #20 H3 —
        # $'EOF' used to cook to "$EOF" and eat the terminator)
        ("$'EOF'", "EOF", True),
        ("$'E\\tF'", "E\tF", True),
        ("$'E\\'F'", "E'F", True),
        ("$'E\\x41F'", "EAF", True),
        ("$'A'B", "AB", True),
        # locale $"...": double-quote rules (translation is identity)
        ('$"EOF"', "EOF", True),
        ('$"A\\$B"', "A$B", True),
        # procsub-shaped delimiter: literal text, unquoted (body expands)
        ("<(x)", "<(x)", False),
        (">(x)y", ">(x)y", False),
    ])
    def test_rule(self, raw, literal, quoted):
        assert unquote_heredoc_delimiter(raw) == (literal, quoted)


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

    def test_quoted_parens_flanking_open_heredoc(self):
        # H2 regression: quote-blind `((`/`))` index-pairing in contains_heredoc
        # made a real heredoc flanked by quoted parens look arithmetic-only, so
        # the oracle wrongly reported "no open heredoc" (the accumulator then
        # ran the body as commands). The `))` here is heredoc BODY.
        assert has_unclosed_heredoc("echo '(('\ncat <<EOF\n))") is True
        specs = open_heredoc_specs("echo '(('\ncat <<EOF\n))")
        assert [(s.cooked, s.strip_tabs) for s in specs] == [("EOF", False)]

    def test_quoted_arith_open_then_bare_heredoc(self):
        # A quoted `$((` before a bare heredoc must not open an arithmetic region.
        assert has_unclosed_heredoc("echo '$(('\ncat <<END\nbody") is True


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

    def test_quoted_paren_does_not_open_region(self):
        # H2: a QUOTED `((` is text and cannot open an arithmetic region, so a
        # bare `<<` after it is NOT "inside an expansion".
        line = "echo '((' <<EOF '))'"
        assert is_inside_expansion(line, line.index("<<")) is False

    def test_quoted_dollar_paren_does_not_open_region(self):
        line = "echo '$((' <<EOF '))'"
        assert is_inside_expansion(line, line.index("<<")) is False

    def test_real_arith_still_inside(self):
        # The unquoted arithmetic case must still be detected (no over-fix).
        line = "echo $(( 1 << 2 ))"
        assert is_inside_expansion(line, line.index("<<")) is True


class TestScanLineHeredocMarkers:
    def test_quoted_paren_line_still_finds_heredoc(self):
        specs, _ = scan_line_heredoc_markers("echo '((' <<EOF '))'")
        assert [(s.cooked, s.strip_tabs, s.quoted) for s in specs] == \
            [("EOF", False, False)]

    def test_quoted_heredoc_operator_is_not_marker(self):
        # `<<EOF` inside quotes must not open a heredoc (both spellings).
        assert scan_line_heredoc_markers("echo '<<EOF'")[0] == []
        assert scan_line_heredoc_markers('echo "<<EOF"')[0] == []

    def test_specs_carry_raw_and_ordinal_identity(self):
        # The text-level scanner produces HeredocSpec values: raw spelling
        # kept, ids ordinal from first_ordinal, spans line-relative.
        line = "cat <<'A' <<A"
        specs, _ = scan_line_heredoc_markers(line, None, 5)
        assert [(s.id, s.raw, s.cooked, s.quoted) for s in specs] == [
            (5, "'A'", "A", True),
            (6, "A", "A", False),
        ]
        for s in specs:
            assert line[s.span[0]:s.span[1]] == s.raw


class TestContainsHeredoc:
    # contains_heredoc is a cheap OVER-APPROXIMATION ('<<' present?): it only
    # gates the accurate scanner and must never be False for a real heredoc.
    # The accurate arithmetic/quote exclusion lives in has_unclosed_heredoc /
    # open_heredoc_delimiters (see TestHasUnclosedHeredoc).
    def test_plain_heredoc(self):
        assert contains_heredoc("cat <<EOF") is True

    def test_arithmetic_shift_over_approximates_true(self):
        # '<<' present -> True (over-approx); the accurate path returns no
        # heredoc for pure arithmetic (has_unclosed_heredoc is False).
        assert contains_heredoc("echo $((1<<2))") is True
        assert has_unclosed_heredoc("echo $((1<<2))") is False

    def test_none(self):
        assert contains_heredoc("echo hi") is False


class TestQuoteAwareHeredocExecution:
    """End-to-end pin on the full-buffer run_command path (the path the H2 bug
    broke; `-c`/script/stdin use the incremental accumulator and masked it)."""

    def test_quoted_parens_flanking_heredoc_execute(self, captured_shell):
        # The `read` builtin must consume the heredoc body; `captured_body`,
        # `EOF`, and `))` must NOT be run as commands.
        rc = captured_shell.run_command(
            "echo '(('\n"
            "read line <<EOF\n"
            "captured_body\n"
            "EOF\n"
            'echo "[$line]"\n'
            "echo '))'")
        assert rc == 0
        assert captured_shell.get_stdout() == "((\n[captured_body]\n))\n"
        assert "not found" not in captured_shell.get_stderr()
