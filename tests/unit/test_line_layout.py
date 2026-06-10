"""Unit tests for the pure line-layout computation (v0.273.0)."""

from psh.line_layout import (
    at_row_boundary,
    displayable_prompt,
    position,
    total_rows,
    visible_prompt_length,
)


class TestVisiblePromptLength:
    def test_plain_text(self):
        assert visible_prompt_length("PSH$ ") == 5

    def test_bare_ansi_csi(self):
        assert visible_prompt_length("\x1b[32mgreen\x1b[0m$ ") == 7

    def test_readline_markers(self):
        # \[ \] in PS1 become \x01 ... \x02: zero-width spans
        prompt = "\x01\x1b[32m\x02user\x01\x1b[0m\x02$ "
        assert visible_prompt_length(prompt) == 6

    def test_osc_title_sequence(self):
        # Terminal title sequences are zero-width
        assert visible_prompt_length("\x1b]0;my title\x07$ ") == 2

    def test_osc_with_st_terminator(self):
        assert visible_prompt_length("\x1b]0;t\x1b\\$ ") == 2

    def test_mixed_markers_and_bare(self):
        prompt = "\x01\x1b[1m\x02bold\x01\x1b[0m\x02 \x1b[33m>\x1b[0m "
        assert visible_prompt_length(prompt) == 7  # 'bold > '


class TestDisplayablePrompt:
    def test_strips_marker_bytes_keeps_sequences(self):
        prompt = "\x01\x1b[32m\x02ok\x01\x1b[0m\x02$ "
        assert displayable_prompt(prompt) == "\x1b[32mok\x1b[0m$ "

    def test_plain_unchanged(self):
        assert displayable_prompt("PSH$ ") == "PSH$ "


class TestPosition:
    def test_single_row(self):
        assert position(5, 0, 80) == (0, 5)
        assert position(5, 10, 80) == (0, 15)

    def test_wraps_to_second_row(self):
        # prompt 5 + pos 75 = 80 → row 1, col 0
        assert position(5, 75, 80) == (1, 0)
        assert position(5, 76, 80) == (1, 1)

    def test_third_row(self):
        assert position(5, 155, 80) == (2, 0)

    def test_zero_width_degrades(self):
        assert position(5, 10, 0) == (0, 15)


class TestTotalRowsAndBoundary:
    def test_fits_one_row(self):
        assert total_rows(5, 10, 80) == 1

    def test_exact_boundary_occupies_next_row(self):
        # 5 + 75 = 80: cursor would sit at (1, 0) → two rows
        assert total_rows(5, 75, 80) == 2
        assert at_row_boundary(5, 75, 80)

    def test_past_boundary(self):
        assert total_rows(5, 76, 80) == 2
        assert not at_row_boundary(5, 76, 80)

    def test_empty(self):
        assert total_rows(0, 0, 80) == 1
        assert not at_row_boundary(0, 0, 80)
