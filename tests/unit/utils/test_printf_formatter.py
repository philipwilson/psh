"""Engine-direct tests for the pure printf formatter.

Every expectation here was probed against bash 5.2
(tmp/printf_probes*.sh batteries, 2026-06-12): the engine is pinned to
bash, not to intuition.  No shell is constructed — format_printf() is a
pure function of (format, arguments).
"""

from psh.utils.printf_formatter import format_printf


def fmt(format_str, *args):
    return format_printf(format_str, list(args))


class TestStarWidthPrecision:
    """%* / %.* consume width/precision from the argument list (bash)."""

    def test_star_width(self):
        r = fmt('%*d\n', '5', '42')
        assert r.output == '   42\n'
        assert r.exit_code == 0

    def test_negative_star_width_left_justifies(self):
        assert fmt('%*d|', '-5', '42').output == '42   |'

    def test_star_precision_float(self):
        assert fmt('%.*f\n', '2', '3.14159').output == '3.14\n'

    def test_star_width_and_precision(self):
        assert fmt('%*.*f|', '10', '2', '3.14159').output == '      3.14|'

    def test_star_width_string(self):
        assert fmt('%*s|', '8', 'hi').output == '      hi|'

    def test_star_precision_string_truncates(self):
        assert fmt('%.*s|', '3', 'hello').output == 'hel|'

    def test_star_precision_integer_min_digits(self):
        assert fmt('%.*d\n', '5', '42').output == '00042\n'

    def test_zero_flag_with_star_width(self):
        assert fmt('%0*d\n', '6', '42').output == '000042\n'

    def test_missing_width_argument_is_zero(self):
        # bash: printf '%*d' 5  ->  '    0' (5 becomes the width)
        assert fmt('%*d', '5').output == '    0'

    def test_no_arguments_at_all(self):
        assert fmt('%*d\n').output == '0\n'

    def test_empty_width_argument_is_zero(self):
        r = fmt('%.*f\n', '', '3.5')
        assert r.output == '4\n'  # precision 0
        assert r.exit_code == 0

    def test_invalid_width_argument_diagnoses_and_continues(self):
        r = fmt('%*d\n', 'abc', '42')
        assert r.output == '42\n'
        assert r.exit_code == 1
        assert r.errors == ['abc: invalid number']

    def test_negative_star_precision_treated_as_omitted(self):
        assert fmt('%.*f\n', '-2', '3.14159').output == '3.141590\n'

    def test_two_star_specs_consume_in_order(self):
        assert fmt('%*d %*d\n', '4', '1', '6', '2').output == '   1      2\n'

    def test_star_width_char(self):
        assert fmt('%*c|', '4', 'x').output == '   x|'


class TestIntegerConversion:
    """strtoimax/strtoumax semantics with base-0 constants (bash)."""

    def test_hex_and_octal_constants(self):
        assert fmt('%d\n', '0x1A', '010').output == '26\n8\n'

    def test_negative_hex(self):
        assert fmt('%d\n', '-0x10').output == '-16\n'

    def test_leading_quote_is_codepoint(self):
        assert fmt('%d\n', '"A').output == '65\n'
        assert fmt('%d\n', "'A").output == '65\n'

    def test_bare_quote_is_zero_no_error(self):
        r = fmt('%d\n', "'")
        assert r.output == '0\n'
        assert r.exit_code == 0

    def test_invalid_number_diagnostic_value_zero(self):
        r = fmt('%d\n', 'abc')
        assert (r.output, r.exit_code) == ('0\n', 1)
        assert r.errors == ['abc: invalid number']

    def test_trailing_junk_uses_parsed_prefix(self):
        r = fmt('%d\n', '42abc')
        assert (r.output, r.exit_code) == ('42\n', 1)

    def test_trailing_whitespace_is_invalid(self):
        r = fmt('%i\n', ' 42 ')
        assert (r.output, r.exit_code) == ('42\n', 1)

    def test_invalid_octal_message(self):
        r = fmt('%d\n', '018')
        assert (r.output, r.exit_code) == ('1\n', 1)
        assert r.errors == ['018: invalid octal number']

    def test_overflow_clamps_with_warning_rc0(self):
        r = fmt('%d\n', '99999999999999999999')
        assert r.output == '9223372036854775807\n'
        assert r.exit_code == 0  # bash: warning only
        assert r.errors == [
            'warning: 99999999999999999999: Result too large']

    def test_unsigned_wraps_64_bit(self):
        assert fmt('%u\n', '-1').output == '18446744073709551615\n'
        assert fmt('%x\n', '-255').output == 'ffffffffffffff01\n'
        assert fmt('%o\n', '-8').output == '1777777777777777777770\n'

    def test_unsigned_max_no_warning(self):
        r = fmt('%x\n', '18446744073709551615')
        assert (r.output, r.exit_code) == ('ffffffffffffffff\n', 0)

    def test_empty_argument_is_zero_no_error(self):
        r = fmt('%d\n', '')
        assert (r.output, r.exit_code) == ('0\n', 0)

    def test_precision_zero_of_zero_is_empty(self):
        assert fmt('%.0d|', '0').output == '|'

    def test_flags_unchanged(self):
        assert fmt('%+d % d\n', '5', '5').output == '+5  5\n'
        assert fmt('%#o %#x\n', '8', '255').output == '010 0xff\n'
        assert fmt('%05d\n', '42').output == '00042\n'
        assert fmt('%-5d|', '42').output == '42   |'


class TestFloatConversion:
    def test_invalid_float_diagnostic(self):
        r = fmt('%f\n', 'abc')
        assert (r.output, r.exit_code) == ('0.000000\n', 1)

    def test_float_trailing_junk(self):
        r = fmt('%f\n', '3.5xyz')
        assert (r.output, r.exit_code) == ('3.500000\n', 1)

    def test_quote_codepoint_float(self):
        assert fmt('%e\n', "'A").output == '6.500000e+01\n'

    def test_empty_float_is_zero(self):
        r = fmt('%f\n', '')
        assert (r.output, r.exit_code) == ('0.000000\n', 0)

    def test_zero_pad_negative(self):
        assert fmt('%09.2f|', '-3.14159').output == '-00003.14|'

    def test_g_format(self):
        assert fmt('%g\n', '100000', '1000000', '0.0001',
                   '0.00001').output == '100000\n1e+06\n0.0001\n1e-05\n'

    def test_hex_float(self):
        # bash 5.2: printf '%a' 3.14 -> 0x1.91eb851eb851fp+1
        assert fmt('%a\n', '3.14').output == '0x1.91eb851eb851fp+1\n'


class TestPercentN:
    def test_assigns_count_so_far(self):
        r = fmt('%s %n %s\n', 'a', 'c', 'b')
        assert r.output == 'a  b\n'
        assert r.assignments == [('c', '2')]
        assert r.exit_code == 0

    def test_invalid_identifier_is_fatal(self):
        r = fmt('a%nb\n', '1bad')
        assert r.output == 'a'  # output so far is kept; processing stops
        assert r.exit_code == 1
        assert r.errors == ["`1bad': not a valid identifier"]

    def test_array_element_rejected(self):
        # bash 5.2 rejects subscripted names for %n
        r = fmt('a%nb\n', 'arr[2]')
        assert r.exit_code == 1

    def test_missing_argument_skipped_silently(self):
        r = fmt('%n')
        assert (r.output, r.exit_code, r.assignments) == ('', 0, [])


class TestFatalFormatErrors:
    def test_invalid_format_character(self):
        r = fmt('a%pb\n', 'x')
        assert r.output == 'a'
        assert r.exit_code == 1
        assert r.errors == ["`p': invalid format character"]

    def test_invalid_format_character_stops_cycling(self):
        r = fmt('%v abc %s\n', 'x', 'y')
        assert r.output == ''
        assert r.exit_code == 1

    def test_missing_format_character_quotes_whole_spec(self):
        r = fmt('x%-5')
        assert r.output == 'x'
        assert r.errors == ["`%-5': missing format character"]
        assert r.exit_code == 1

    def test_lone_percent_at_end(self):
        r = fmt('%')
        assert r.errors == ["`%': missing format character"]

    def test_length_modifier_then_end(self):
        # bash: `%5z' missing format character (z eaten as a modifier)
        r = fmt('%5z', 'a')
        assert r.errors == ["`%5z': missing format character"]


class TestLengthModifiers:
    def test_modifiers_accepted_and_ignored(self):
        assert fmt('%ld\n', '99').output == '99\n'
        assert fmt('%lld %hd\n', '9', '9').output == '9 9\n'
        assert fmt('%zu\n', '9').output == '9\n'


class TestExistingBehaviorPinned:
    """Regression net: behavior that already matched bash must not move."""

    def test_argument_cycling(self):
        assert fmt('%s\n', 'a', 'b', 'c').output == 'a\nb\nc\n'
        assert fmt('%s %d\n', 'a', '1', 'b', '2').output == 'a 1\nb 2\n'

    def test_missing_args_format_applied_once(self):
        assert fmt('[%s]').output == '[]'
        assert fmt('%d %d\n', '3').output == '3 0\n'

    def test_percent_q(self):
        assert fmt('%q\n', 'a b$c').output == 'a\\ b\\$c\n'
        assert fmt('%q', '').output == "''"

    def test_percent_b(self):
        assert fmt('%b\n', 'x\\ty').output == 'x\ty\n'

    def test_percent_b_backslash_c_terminates_everything(self):
        r = fmt('%bX', 'a\\cb')
        assert r.output == 'a'
        assert r.exit_code == 0

    def test_percent_b_escapes_before_backslash_c_are_processed(self):
        # bash: printf '%b' 'x\ny\cz' -> 'x<NL>y' (reappraisal #17 M3a)
        r = fmt('%b', 'x\\ny\\cz')
        assert r.output == 'x\ny'
        assert r.exit_code == 0

    def test_percent_b_bare_octal_posix_form(self):
        # bash %b octal does NOT need the leading 0 (reappraisal #17 M3b):
        # \1 -> 0x01, \41 -> '!', \777 -> 0xFF (mod 256), \0 -> NUL
        assert fmt('%b', '\\1').output == '\x01'
        assert fmt('%b', '\\41').output == '!'
        assert fmt('%b', '\\777').output == '\xff'
        assert fmt('%b', '\\0').output == '\x00'
        assert fmt('%b', '\\0101').output == 'A'

    def test_char_is_first_char_not_codepoint(self):
        assert fmt('%c\n', '65').output == '6\n'
        assert fmt('%c', 'hello').output == 'h'

    def test_char_empty_is_nul(self):
        assert fmt('%c', '').output == '\0'

    def test_string_width_precision(self):
        assert fmt('%10s|', 'hello').output == '     hello|'
        assert fmt('%-10s|', 'hello').output == 'hello     |'
        assert fmt('%.3s|', 'hello').output == 'hel|'

    def test_bare_dot_precision_is_zero(self):
        # bash: printf '%.s' abc -> ''
        assert fmt('%.s|', 'abc').output == '|'

    def test_format_escapes(self):
        assert fmt('a\\tb\\n').output == 'a\tb\n'
        assert fmt('\\x41\\102\\u0043').output == 'ABC'
        assert fmt('x\\ey').output == 'x\x1by'

    def test_unknown_escape_keeps_backslash(self):
        # bash prints 'a\zb' literally; \c is NOT special in the format
        assert fmt('a\\zb').output == 'a\\zb'
        assert fmt('a\\cb').output == 'a\\cb'

    def test_question_mark_escape_drops_backslash(self):
        # bash: printf '\?' -> '?' (like \' and \" in the format dialect)
        assert fmt('\\?').output == '?'

    def test_unicode_short_forms(self):
        # bash accepts 1-4 hex digits for \u and 1-8 for \U in the format
        assert fmt('\\u41').output == 'A'
        assert fmt('\\u123').output == 'ģ'
        assert fmt('\\U41').output == 'A'
        assert fmt('\\u00411').output == 'A1'

    def test_format_octal_leading_zero_not_special(self):
        # Format dialect: 1-3 octal digits TOTAL — '\0101' is \010 + '1'
        # (unlike echo -e / %b where \0ddd allows 3 digits after the 0)
        assert fmt('\\0101').output == '\x081'
        assert fmt('\\101').output == 'A'
        assert fmt('\\777').output == '\xff'

    def test_backslash_percent_feeds_conversion_parsing(self):
        # bash: printf '\%' emits '\' then fails on the bare '%'
        r = fmt('\\%')
        assert r.output == '\\'
        assert r.exit_code == 1
        assert r.errors == ["`%': missing format character"]

    def test_unrepresentable_unicode_emits_nothing(self):
        # bash writes raw bytes for surrogates; a Python str cannot, so
        # the engine emits nothing instead of crashing at write time
        r = fmt('a\\ud800b')
        assert r.output == 'ab'
        assert r.exit_code == 0

    def test_double_percent(self):
        assert fmt('%%\n').output == '%\n'

    def test_time_format(self):
        import time
        assert fmt('%(%Y)T\n', '0').output == (
            time.strftime('%Y', time.localtime(0)) + '\n')
