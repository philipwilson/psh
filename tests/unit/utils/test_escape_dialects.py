r"""Dialect tests for the shared backslash-escape scanner (psh/utils/escapes.py).

Every expectation here was probed byte-exact against bash 5.2
(tmp/probes-r17t2-escapes truth table, 2026-07-04, 216 rows): the two
argument dialects differ ONLY in their octal grammar —

- echo -e / print:  octal requires the leading zero (\0ddd); \101 literal
- printf %b:        \0ddd AND the POSIX bare form \ddd (\101 -> 'A')

Both process escapes left-to-right and stop at \c AFTER everything
before it (reappraisal #17 M3: the old implementation returned the raw
prefix, leaving `echo -e 'a\tb\cd'` with a literal backslash-t).
"""

import pytest

from psh.utils.escapes import (
    ansi_c_encode,
    has_control_char,
    process_echo_escapes,
    process_percent_b_escapes,
    quote_at_q,
    quote_printf_q,
)

DIALECTS = [process_echo_escapes, process_percent_b_escapes]


class TestSimpleEscapesBothDialects:
    @pytest.mark.parametrize("scan", DIALECTS)
    def test_c_escape_set(self, scan):
        assert scan(r'\a\b\e\E\f\n\r\t\v') == ('\a\b\x1b\x1b\f\n\r\t\v', False)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_double_backslash(self, scan):
        assert scan(r'\\') == ('\\', False)
        # \\n is a literal backslash then a literal n — not a newline
        assert scan(r'\\n') == ('\\n', False)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_unknown_escapes_keep_backslash(self, scan):
        # bash: \' \" \? \z \% all stay literal in the argument dialects
        for seq in (r"\'", r'\"', r'\?', r'\z', r'\%'):
            assert scan(seq) == (seq, False)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_trailing_lone_backslash(self, scan):
        assert scan('a\\') == ('a\\', False)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_no_placeholder_hazard(self, scan):
        # The old multi-pass implementation used \x01BACKSLASH\x01 as a
        # temporary marker: this input decoded to a single backslash.
        assert scan(r'\x01BACKSLASH\x01') == ('\x01BACKSLASH\x01', False)


class TestBackslashCTermination:
    @pytest.mark.parametrize("scan", DIALECTS)
    def test_bare_c_terminates(self, scan):
        assert scan(r'\c') == ('', True)
        assert scan(r'pre\cpost') == ('pre', True)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_escapes_before_c_are_processed(self, scan):
        # M3(a): bash processes everything before the \c
        assert scan(r'a\tb\cd') == ('a\tb', True)
        assert scan(r'x\ny\cz') == ('x\ny', True)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_consumed_backslash_does_not_terminate(self, scan):
        # \\c: the backslash pairs with \\ so the c is literal (bash)
        assert scan(r'\\c') == ('\\c', False)
        assert scan(r'a\\b\cd') == ('a\\b', True)


class TestEchoOctalDialect:
    r"""echo -e: \0 + up to 3 octal digits, value mod 256; \ddd literal."""

    def test_leading_zero_forms(self):
        assert process_echo_escapes(r'\0') == ('\x00', False)
        assert process_echo_escapes(r'\01') == ('\x01', False)
        assert process_echo_escapes(r'\041') == ('!', False)
        assert process_echo_escapes(r'\0101') == ('A', False)

    def test_mod_256_truncation(self):
        # bash: echo -e '\0777' emits 0xFF (511 % 256)
        assert process_echo_escapes(r'\0777') == ('\xff', False)

    def test_at_most_three_digits_after_zero(self):
        assert process_echo_escapes(r'\04012') == ('\x012', False)

    def test_zero_then_non_octal_digit(self):
        assert process_echo_escapes(r'\08') == ('\x008', False)

    def test_bare_octal_stays_literal(self):
        # M3(b): bash echo -e requires the leading 0
        for seq in (r'\1', r'\41', r'\101', r'\1013', r'\777', r'\8'):
            assert process_echo_escapes(seq) == (seq, False)


class TestPercentBOctalDialect:
    r"""printf %b: \ddd (POSIX) and \0ddd both decode, value mod 256."""

    def test_bare_octal(self):
        assert process_percent_b_escapes(r'\1') == ('\x01', False)
        assert process_percent_b_escapes(r'\41') == ('!', False)
        assert process_percent_b_escapes(r'\101') == ('A', False)

    def test_bare_octal_three_digit_max(self):
        assert process_percent_b_escapes(r'\1013') == ('A3', False)

    def test_bare_octal_mod_256(self):
        # bash: printf '%b' '\777' -> 0xFF, '\400' -> NUL
        assert process_percent_b_escapes(r'\777') == ('\xff', False)
        assert process_percent_b_escapes(r'\400') == ('\x00', False)

    def test_leading_zero_allows_three_more_digits(self):
        assert process_percent_b_escapes(r'\0') == ('\x00', False)
        assert process_percent_b_escapes(r'\0101') == ('A', False)
        assert process_percent_b_escapes(r'\0777') == ('\xff', False)
        assert process_percent_b_escapes(r'\04012') == ('\x012', False)

    def test_eight_is_not_octal(self):
        assert process_percent_b_escapes(r'\8') == ('\\8', False)


class TestHexAndUnicodeBothDialects:
    @pytest.mark.parametrize("scan", DIALECTS)
    def test_hex_one_or_two_digits(self, scan):
        assert scan(r'\x41') == ('A', False)
        assert scan(r'\x4') == ('\x04', False)
        assert scan(r'\x413') == ('A3', False)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_hex_without_digits_is_literal(self, scan):
        assert scan(r'\x') == ('\\x', False)
        assert scan(r'\xgg') == ('\\xgg', False)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_unicode_short_forms(self, scan):
        # bash accepts 1-4 digits for \u and 1-8 for \U
        assert scan(r'\u0041') == ('A', False)
        assert scan(r'\u41') == ('A', False)
        assert scan(r'\u123') == ('ģ', False)
        assert scan(r'\U41') == ('A', False)
        assert scan(r'\U0001F600') == ('\U0001F600', False)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_unicode_greedy_then_literal(self, scan):
        assert scan(r'\u00411') == ('A1', False)
        assert scan(r'\U000000411') == ('A1', False)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_unicode_without_digits_is_literal(self, scan):
        assert scan(r'\u') == ('\\u', False)
        assert scan(r'\U') == ('\\U', False)

    @pytest.mark.parametrize("scan", DIALECTS)
    def test_unrepresentable_codepoints_emit_nothing(self, scan):
        # bash writes raw bytes here (surrogates / values past U+10FFFF);
        # a Python str cannot survive the encode, so the scanner emits
        # nothing — matching bash's own \UFFFFFFFF behavior — instead of
        # crashing at write time (byte-model limitation).
        assert scan(r'\ud800') == ('', False)
        assert scan(r'\UFFFFFFFF') == ('', False)
        assert scan(r'a\ud800b') == ('ab', False)


class TestAnsiCEncode:
    r"""The SINGLE ``$'...'`` reuse-form ENCODER (T11 unification).

    Every expectation probed byte-exact against bash 5.2 (2026-07-12,
    tmp/r19-ledgers/T11-probes). This is the opposite family from the
    decoders above: they are kept apart on purpose; the encoder is one
    shared authority feeding ${var@Q}, printf %q, declare -p, set, hash -l.
    """

    def test_named_escapes_where_bash_has_them(self):
        # bash renders these as \a \b \E \f \n \r \t \v (NOT octal, NOT hex)
        assert ansi_c_encode('\a\b\x1b\f\n\r\t\v') == r'\a\b\E\f\n\r\t\v'

    def test_esc_uses_capital_E_not_octal(self):
        # The @Q divergence the fix closes: ESC is \E, not \033.
        assert ansi_c_encode('\x1b') == r'\E'

    def test_other_controls_are_octal_not_hex(self):
        # The printf %q divergence the fix closes: octal, not \xNN.
        assert ansi_c_encode('\x01') == r'\001'
        assert ansi_c_encode('\x7f') == r'\177'

    def test_backslash_and_quote_escaped(self):
        assert ansi_c_encode('\\') == r'\\'
        assert ansi_c_encode("'") == r"\'"

    def test_non_control_passthrough(self):
        assert ansi_c_encode('abc') == 'abc'

    def test_mixed(self):
        assert ansi_c_encode('a\x01b\x1bc') == r'a\001b\Ec'

    def test_has_control_char(self):
        assert has_control_char('\x01')
        assert has_control_char('\x7f')
        assert has_control_char('a\nb')
        assert not has_control_char('abc')
        assert not has_control_char('')
        # High byte U+00FF is NOT a control char (byte-model: stays printable).
        # DELIBERATE DIVERGENCE: bash renders a raw 0xff byte as $'\377' on all
        # four reuse surfaces; psh's str-based byte model keeps it printable
        # text. Pre-existing (byte-model M8 family), unchanged by T11, recorded
        # in the campaign deferred-divergence ledger.
        assert not has_control_char('\xff')


class TestReuseQuotersDelegate:
    r"""``quote_at_q`` (${var@Q}) and ``quote_printf_q`` (printf %q) share the
    ONE encoder for control chars — the T11 convergence. Both emit the same
    ``$'...'`` body; they differ only in how they wrap NON-control text."""

    # Control-char values whose $'...' body must be byte-identical across
    # both quoters and equal to ``$'`` + ansi_c_encode + ``'``.
    # Every value holds at least one control char (so it routes through the
    # $'...' encoder); the last two also carry a quote / backslash to pin
    # that those are escaped inside the shared body.
    CONTROL_VALUES = ['\x01', '\x1b', '\x7f', 'a\nb', 'a\tb',
                      'a\x07b', 'a\x08b', 'a\x0cb', 'a\x0bb',
                      'a\x01b\x1bc', "q'x\n", 'a\\b\t']

    @pytest.mark.parametrize('v', CONTROL_VALUES)
    def test_both_quoters_emit_shared_encoder_body(self, v):
        expected = "$'" + ansi_c_encode(v) + "'"
        assert quote_at_q(v) == expected
        assert quote_printf_q(v) == expected
        # ...and therefore agree with each other on control-char values:
        assert quote_at_q(v) == quote_printf_q(v)

    def test_printf_q_control_regression_octal_and_E(self):
        # RED-ON-BASE: pre-fix printf %q used hex (\x01/\x1b/\x7f).
        assert quote_printf_q('\x01') == r"$'\001'"
        assert quote_printf_q('\x1b') == r"$'\E'"
        assert quote_printf_q('\x7f') == r"$'\177'"
        assert quote_printf_q('a\x01b\x1bc') == r"$'a\001b\Ec'"

    def test_at_q_control_regression_E_not_octal_esc(self):
        # RED-ON-BASE: pre-fix ${var@Q} rendered ESC as \033, not \E.
        assert quote_at_q('\x1b') == r"$'\E'"
        assert quote_at_q('a\x01b\x1bc') == r"$'a\001b\Ec'"

    def test_non_control_wrapping_still_differs(self):
        # The intended divergence (bash 5.2): %q backslash-escapes specials,
        # @Q single-quotes them. Only the $'...' body is shared.
        assert quote_printf_q('a b') == r'a\ b'
        assert quote_at_q('a b') == "'a b'"
        assert quote_printf_q('') == "''"
        assert quote_at_q('') == "''"
