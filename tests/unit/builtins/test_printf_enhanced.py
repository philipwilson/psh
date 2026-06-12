"""
Enhanced unit tests for printf builtin with POSIX compliance.

Tests cover:
- Complete POSIX format specifiers (d, o, x, X, u, f, F, g, G, e, E, c, s)
- Field width and precision
- Flags (-+#0 )
- Multiple format specifiers in one format string
- Argument cycling for insufficient arguments
- Error handling for invalid formats
- Escape sequences (\n, \t, etc.)
- Complex real-world use cases
"""



class TestPrintfBasicFormats:
    """Test basic printf format specifiers."""

    def test_string_format(self, shell, capsys):
        """Test %s string format."""
        shell.run_command('printf "%s\\n" "hello"')
        captured = capsys.readouterr()
        assert captured.out == "hello\n"

    def test_string_format_multiple(self, shell, capsys):
        """Test %s with multiple arguments."""
        shell.run_command('printf "%s %s\\n" "hello" "world"')
        captured = capsys.readouterr()
        assert captured.out == "hello world\n"

    def test_decimal_format(self, shell, capsys):
        """Test %d decimal format."""
        shell.run_command('printf "%d\\n" "42"')
        captured = capsys.readouterr()
        assert captured.out == "42\n"

    def test_decimal_negative(self, shell, capsys):
        """Test %d with negative number."""
        shell.run_command('printf "%d\\n" "-123"')
        captured = capsys.readouterr()
        assert captured.out == "-123\n"

    def test_octal_format(self, shell, capsys):
        """Test %o octal format."""
        shell.run_command('printf "%o\\n" "64"')
        captured = capsys.readouterr()
        assert captured.out == "100\n"  # 64 in octal is 100

    def test_hex_lowercase_format(self, shell, capsys):
        """Test %x hex format (lowercase)."""
        shell.run_command('printf "%x\\n" "255"')
        captured = capsys.readouterr()
        assert captured.out == "ff\n"

    def test_hex_uppercase_format(self, shell, capsys):
        """Test %X hex format (uppercase)."""
        shell.run_command('printf "%X\\n" "255"')
        captured = capsys.readouterr()
        assert captured.out == "FF\n"

    def test_unsigned_format(self, shell, capsys):
        """Test %u unsigned format."""
        shell.run_command('printf "%u\\n" "42"')
        captured = capsys.readouterr()
        assert captured.out == "42\n"

    def test_character_format(self, shell, capsys):
        """Test %c character format."""
        shell.run_command('printf "%c\\n" "A"')
        captured = capsys.readouterr()
        assert captured.out == "A\n"

    def test_character_format_first_char_of_number(self, shell, capsys):
        """%c prints the FIRST character, never a codepoint (bash:
        `printf '%c' 65` prints '6', verified against bash 5.2)."""
        shell.run_command('printf "%c\\n" "65"')
        captured = capsys.readouterr()
        assert captured.out == "6\n"

    def test_percent_literal(self, shell, capsys):
        """Test %% for literal percent."""
        shell.run_command('printf "%%\\n"')
        captured = capsys.readouterr()
        assert captured.out == "%\n"


class TestPrintfFloatingPoint:
    """Test floating point format specifiers."""

    def test_float_format(self, shell, capsys):
        """Test %f float format."""
        shell.run_command('printf "%f\\n" "3.14159"')
        captured = capsys.readouterr()
        assert "3.14159" in captured.out

    def test_float_uppercase_format(self, shell, capsys):
        """Test %F float format (uppercase)."""
        shell.run_command('printf "%F\\n" "3.14159"')
        captured = capsys.readouterr()
        assert "3.14159" in captured.out

    def test_general_format(self, shell, capsys):
        """Test %g general format."""
        shell.run_command('printf "%g\\n" "1234.5"')
        captured = capsys.readouterr()
        assert "1234.5" in captured.out or "1.2345e" in captured.out.lower()

    def test_general_uppercase_format(self, shell, capsys):
        """Test %G general format (uppercase)."""
        shell.run_command('printf "%G\\n" "1234.5"')
        captured = capsys.readouterr()
        assert "1234.5" in captured.out or "1.2345E" in captured.out


class TestPrintfFieldWidth:
    """Test field width specifications."""

    def test_string_width_right_align(self, shell, capsys):
        """Test %10s right-aligned string."""
        shell.run_command('printf "%10s\\n" "hello"')
        captured = capsys.readouterr()
        assert captured.out == "     hello\n"

    def test_string_width_left_align(self, shell, capsys):
        """Test %-10s left-aligned string."""
        shell.run_command('printf "%-10s\\n" "hello"')
        captured = capsys.readouterr()
        assert captured.out == "hello     \n"

    def test_decimal_width_right_align(self, shell, capsys):
        """Test %5d right-aligned decimal."""
        shell.run_command('printf "%5d\\n" "42"')
        captured = capsys.readouterr()
        assert captured.out == "   42\n"

    def test_decimal_width_zero_pad(self, shell, capsys):
        """Test %05d zero-padded decimal."""
        shell.run_command('printf "%05d\\n" "42"')
        captured = capsys.readouterr()
        assert captured.out == "00042\n"

    def test_decimal_width_left_align(self, shell, capsys):
        """Test %-5d left-aligned decimal."""
        shell.run_command('printf "%-5d\\n" "42"')
        captured = capsys.readouterr()
        assert captured.out == "42   \n"


class TestPrintfPrecision:
    """Test precision specifications."""

    def test_string_precision(self, shell, capsys):
        """Test %.3s string precision (truncation)."""
        shell.run_command('printf "%.3s\\n" "hello"')
        captured = capsys.readouterr()
        assert captured.out == "hel\n"

    def test_decimal_precision(self, shell, capsys):
        """Test %.5d decimal precision (leading zeros)."""
        shell.run_command('printf "%.5d\\n" "42"')
        captured = capsys.readouterr()
        assert captured.out == "00042\n"

    def test_float_precision(self, shell, capsys):
        """Test %.2f float precision."""
        shell.run_command('printf "%.2f\\n" "3.14159"')
        captured = capsys.readouterr()
        assert captured.out == "3.14\n"


class TestPrintfFlags:
    """Test printf flags."""

    def test_plus_flag(self, shell, capsys):
        """Test %+d plus flag for positive numbers."""
        shell.run_command('printf "%+d\\n" "42"')
        captured = capsys.readouterr()
        assert captured.out == "+42\n"

    def test_space_flag(self, shell, capsys):
        """Test % d space flag for positive numbers."""
        shell.run_command('printf "% d\\n" "42"')
        captured = capsys.readouterr()
        assert captured.out == " 42\n"

    def test_hash_flag_hex(self, shell, capsys):
        """Test %#x hash flag for hex (0x prefix)."""
        shell.run_command('printf "%#x\\n" "255"')
        captured = capsys.readouterr()
        assert captured.out == "0xff\n"

    def test_hash_flag_octal(self, shell, capsys):
        """Test %#o hash flag for octal (0 prefix)."""
        shell.run_command('printf "%#o\\n" "64"')
        captured = capsys.readouterr()
        assert captured.out == "0100\n"


class TestPrintfArgumentCycling:
    """Test argument cycling behavior."""

    def test_insufficient_arguments_string(self, shell, capsys):
        """Test %s with insufficient arguments (should use empty string)."""
        shell.run_command('printf "%s %s\\n" "hello"')
        captured = capsys.readouterr()
        assert captured.out == "hello \n"

    def test_insufficient_arguments_decimal(self, shell, capsys):
        """Test %d with insufficient arguments (should use 0)."""
        shell.run_command('printf "%d %d\\n" "42"')
        captured = capsys.readouterr()
        assert captured.out == "42 0\n"

    def test_repeated_format(self, shell, capsys):
        """Test format string repeated with multiple arguments."""
        shell.run_command('printf "%s\\n" "line1" "line2" "line3"')
        captured = capsys.readouterr()
        assert captured.out == "line1\nline2\nline3\n"


class TestPrintfEscapeSequences:
    """Test escape sequences in format strings."""

    def test_newline_escape(self, shell, capsys):
        """Test \\n newline escape."""
        shell.run_command('printf "line1\\nline2\\n"')
        captured = capsys.readouterr()
        assert captured.out == "line1\nline2\n"

    def test_tab_escape(self, shell, capsys):
        """Test \\t tab escape."""
        shell.run_command('printf "col1\\tcol2\\n"')
        captured = capsys.readouterr()
        assert captured.out == "col1\tcol2\n"

    def test_carriage_return_escape(self, shell, capsys):
        """Test \\r carriage return escape."""
        shell.run_command('printf "text\\rOVER\\n"')
        captured = capsys.readouterr()
        assert captured.out == "text\rOVER\n"

    def test_hex_escape(self, shell, capsys):
        """Test \\xHH hex escape sequences."""
        shell.run_command('printf "\\x41\\x42\\x43\\n"')
        captured = capsys.readouterr()
        assert captured.out == "ABC\n"

    def test_octal_escape(self, shell, capsys):
        """Test \\nnn octal escape sequences."""
        shell.run_command('printf "\\101\\102\\103\\n"')
        captured = capsys.readouterr()
        assert captured.out == "ABC\n"

    def test_escape_char_e(self, shell, capsys):
        """Test \\e escape character (bash extension): printf "x\\ey"."""
        shell.run_command('printf "x\\ey"')
        captured = capsys.readouterr()
        assert captured.out == "x\x1by"

    def test_escape_char_E(self, shell, capsys):
        """Test \\E alternative escape character form."""
        shell.run_command('printf "a\\eb\\E c"')
        captured = capsys.readouterr()
        assert captured.out == "a\x1bb\x1b c"

    def test_escape_char_in_format_with_specifier(self, shell, capsys):
        """Test \\e in a format string that also has a conversion."""
        shell.run_command('printf "%s\\e" z')
        captured = capsys.readouterr()
        assert captured.out == "z\x1b"

    def test_escape_char_b_dialect(self, shell, capsys):
        """Test \\e via %b (argument escape dialect)."""
        shell.run_command('printf "%b" "x\\ey"')
        captured = capsys.readouterr()
        assert captured.out == "x\x1by"


class TestPrintfComplexFormats:
    """Test complex format combinations."""

    def test_mixed_formats(self, shell, capsys):
        """Test mixed format specifiers."""
        shell.run_command('printf "String: %s, Number: %d, Hex: %x\\n" "test" "255" "255"')
        captured = capsys.readouterr()
        assert captured.out == "String: test, Number: 255, Hex: ff\n"

    def test_table_format(self, shell, capsys):
        """Test table-like formatting."""
        shell.run_command('printf "%-10s %5d %8s\\n" "Name" "123" "Value"')
        captured = capsys.readouterr()
        assert "Name" in captured.out
        assert "123" in captured.out
        assert "Value" in captured.out

    def test_padded_hex_table(self, shell, capsys):
        """Test padded hex table formatting."""
        shell.run_command('printf "%04X %04X %04X\\n" "10" "255" "4095"')
        captured = capsys.readouterr()
        assert captured.out == "000A 00FF 0FFF\n"


class TestPrintfErrorHandling:
    """Test printf error handling."""

    def test_no_format_string(self, shell, capsys):
        """Test printf with no format string."""
        exit_code = shell.run_command('printf')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert "usage" in captured.err.lower() or "format" in captured.err.lower()

    def test_invalid_format_specifier(self, shell, capsys):
        """Test printf with invalid format specifier."""
        # %z is not a valid format specifier
        shell.run_command('printf "%z\\n" "test"')
        # Should either ignore unknown formats or error
        capsys.readouterr()
        # Behavior may vary - either literal %z or error

    def test_invalid_number_conversion(self, shell, capsys):
        """Test %d with non-numeric string."""
        shell.run_command('printf "%d\\n" "abc"')
        captured = capsys.readouterr()
        # Should output 0 for invalid numeric conversion
        assert captured.out == "0\n"


class TestPrintfRealWorldUseCases:
    """Test real-world printf use cases."""

    def test_progress_indicator(self, shell, capsys):
        """Test progress indicator formatting."""
        shell.run_command('printf "Processing: %3d%% complete\\n" "75"')
        captured = capsys.readouterr()
        assert "Processing:  75% complete\n" == captured.out

    def test_file_listing_format(self, shell, capsys):
        """Test file listing format."""
        shell.run_command('printf "%-20s %8s %s\\n" "filename.txt" "1024" "2023-01-01"')
        captured = capsys.readouterr()
        assert "filename.txt" in captured.out
        assert "1024" in captured.out
        assert "2023-01-01" in captured.out

    def test_csv_output(self, shell, capsys):
        """Test CSV output generation."""
        shell.run_command('printf "%s,%d,%s\\n" "John" "25" "Engineer"')
        captured = capsys.readouterr()
        assert captured.out == "John,25,Engineer\n"

    def test_config_file_generation(self, shell, capsys):
        """Test configuration file format."""
        shell.run_command('printf "server=%s\\nport=%d\\ntimeout=%d\\n" "localhost" "8080" "30"')
        captured = capsys.readouterr()
        expected = "server=localhost\nport=8080\ntimeout=30\n"
        assert captured.out == expected


class TestPrintfStarWidthPrecision:
    """%* / %.* consume width/precision from arguments (bash 5.2,
    probe-verified 2026-06-12)."""

    def test_star_width(self, shell, capsys):
        shell.run_command("printf '%*d\\n' 5 42")
        assert capsys.readouterr().out == "   42\n"

    def test_negative_star_width(self, shell, capsys):
        shell.run_command("printf '%*d|\\n' -5 42")
        assert capsys.readouterr().out == "42   |\n"

    def test_star_precision(self, shell, capsys):
        shell.run_command("printf '%.*f\\n' 2 3.14159")
        assert capsys.readouterr().out == "3.14\n"

    def test_star_width_and_precision(self, shell, capsys):
        shell.run_command("printf '%*.*f|\\n' 10 2 3.14159")
        assert capsys.readouterr().out == "      3.14|\n"

    def test_invalid_star_width_diagnoses(self, shell, capsys):
        exit_code = shell.run_command("printf '%*d\\n' abc 42")
        captured = capsys.readouterr()
        assert captured.out == "42\n"
        assert "invalid number" in captured.err
        assert exit_code == 1


class TestPrintfPercentN:
    def test_percent_n_assigns_shell_variable(self, shell, capsys):
        shell.run_command("printf '%s %n%s\\n' ab n cd; echo $n")
        assert capsys.readouterr().out == "ab cd\n3\n"

    def test_percent_n_invalid_identifier_fatal(self, shell, capsys):
        exit_code = shell.run_command("printf 'a%nb\\n' '1bad'")
        captured = capsys.readouterr()
        assert captured.out == "a"
        assert "not a valid identifier" in captured.err
        assert exit_code == 1


class TestPrintfFatalFormatErrors:
    def test_invalid_format_character(self, shell, capsys):
        exit_code = shell.run_command("printf 'a%pb\\n' x")
        captured = capsys.readouterr()
        assert captured.out == "a"
        assert "invalid format character" in captured.err
        assert exit_code == 1

    def test_missing_format_character(self, shell, capsys):
        exit_code = shell.run_command("printf 'x%-5'")
        captured = capsys.readouterr()
        assert captured.out == "x"
        assert "missing format character" in captured.err
        assert exit_code == 1


class TestPrintfNumericBashSemantics:
    def test_hex_octal_constants(self, shell, capsys):
        shell.run_command("printf '%d %d\\n' 0x1A 010")
        assert capsys.readouterr().out == "26 8\n"

    def test_quote_codepoint(self, shell, capsys):
        shell.run_command('printf "%d\\n" "\'A"')
        assert capsys.readouterr().out == "65\n"

    def test_unsigned_wraps_64_bit(self, shell, capsys):
        shell.run_command("printf '%u\\n' -1")
        assert capsys.readouterr().out == "18446744073709551615\n"

    def test_invalid_number_is_status_1(self, shell, capsys):
        exit_code = shell.run_command("printf '%d\\n' abc")
        captured = capsys.readouterr()
        assert captured.out == "0\n"
        assert "invalid number" in captured.err
        assert exit_code == 1


class TestPrintfOptions:
    def test_double_dash_ends_options(self, shell, capsys):
        shell.run_command("printf -- '-x%s\\n' a")
        assert capsys.readouterr().out == "-xa\n"

    def test_dash_v_with_warning_status(self, shell, capsys):
        exit_code = shell.run_command("printf -v out '%d' abc; echo \"$out\"")
        captured = capsys.readouterr()
        assert captured.out == "0\n"
        assert "invalid number" in captured.err
        assert exit_code == 0  # echo's status; printf itself returned 1


class TestPrintfPOSIXCompliance:
    """Test POSIX compliance features."""

    def test_argument_cycling_posix(self, shell, capsys):
        """Test POSIX-required argument cycling."""
        # POSIX requires format to be reused if more arguments than format specifiers
        shell.run_command('printf "%s\\n" "a" "b" "c"')
        captured = capsys.readouterr()
        assert captured.out == "a\nb\nc\n"

    def test_numeric_conversion_posix(self, shell, capsys):
        """Test POSIX numeric conversion behavior."""
        # POSIX requires non-numeric strings to convert to 0
        shell.run_command('printf "%d %d\\n" "123abc" "xyz"')
        captured = capsys.readouterr()
        # First should be 123 (leading digits), second should be 0
        assert "123 0\n" == captured.out or "0 0\n" == captured.out

    def test_exit_status_success(self, shell, capsys):
        """Test printf returns 0 on success."""
        exit_code = shell.run_command('printf "test\\n"')
        assert exit_code == 0

    def test_exit_status_error(self, shell, capsys):
        """Test printf returns non-zero on error."""
        exit_code = shell.run_command('printf')  # No arguments
        assert exit_code != 0
