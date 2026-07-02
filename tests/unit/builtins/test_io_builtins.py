"""
Unit tests for I/O builtins (echo, printf, read).

Tests cover:
- echo with various flags (-n, -e, -E)
- printf format strings and conversions
- read with various options
- Error handling
- Edge cases
"""

import os


class TestEchoBuiltin:
    """Test echo builtin functionality."""

    def test_echo_basic(self, shell, capsys):
        """Test basic echo functionality."""
        shell.run_command('echo hello world')
        captured = capsys.readouterr()
        assert captured.out == "hello world\n"

    def test_echo_empty(self, shell, capsys):
        """Test echo with no arguments."""
        shell.run_command('echo')
        captured = capsys.readouterr()
        assert captured.out == "\n"

    def test_echo_n_flag(self, shell, capsys):
        """Test echo -n (no newline)."""
        shell.run_command('echo -n hello')
        captured = capsys.readouterr()
        assert captured.out == "hello"

    def test_echo_e_flag_escapes(self, shell, capsys):
        """Test echo -e with escape sequences."""
        shell.run_command('echo -e "line1\\nline2"')
        captured = capsys.readouterr()
        assert captured.out == "line1\nline2\n"

        shell.run_command('echo -e "tab\\there"')
        captured = capsys.readouterr()
        assert captured.out == "tab\there\n"

        shell.run_command('echo -e "back\\bspace"')
        captured = capsys.readouterr()
        assert captured.out == "back\bspace\n"

    def test_echo_E_flag_no_escapes(self, shell, capsys):
        """Test echo -E disables escape interpretation."""
        shell.run_command('echo -E "test\\n"')
        captured = capsys.readouterr()
        assert captured.out == "test\\n\n"

    def test_echo_multiple_spaces(self, shell, capsys):
        """Test echo preserves multiple spaces."""
        shell.run_command('echo "a    b    c"')
        captured = capsys.readouterr()
        assert captured.out == "a    b    c\n"

    def test_echo_special_chars(self, shell, capsys):
        """Test echo with special characters."""
        shell.run_command('echo "$HOME is home"')
        captured = capsys.readouterr()
        assert "is home" in captured.out
        assert captured.out.endswith("\n")

    def test_echo_with_quotes(self, shell, capsys):
        """Test echo with various quoting."""
        shell.run_command('echo "double quotes"')
        captured = capsys.readouterr()
        assert captured.out == "double quotes\n"

        shell.run_command("echo 'single quotes'")
        captured = capsys.readouterr()
        assert captured.out == "single quotes\n"

        shell.run_command('echo "mix \'of\' quotes"')
        captured = capsys.readouterr()
        assert captured.out == "mix 'of' quotes\n"

    def test_echo_escape_sequences(self, shell, capsys):
        """Test various escape sequences with -e."""
        # Alert (bell)
        shell.run_command('echo -e "\\a"')

        # Carriage return
        shell.run_command('echo -e "abc\\rdef"')
        captured = capsys.readouterr()
        # \r might overwrite

        # Vertical tab
        shell.run_command('echo -e "line1\\vline2"')
        captured = capsys.readouterr()
        assert "\v" in captured.out or "line1" in captured.out

        # Hex escape
        shell.run_command('echo -e "\\x41"')
        captured = capsys.readouterr()
        assert "A" in captured.out

        # Octal escape
        shell.run_command('echo -e "\\101"')
        captured = capsys.readouterr()
        assert "A" in captured.out

    def test_echo_backslash_c(self, shell, capsys):
        """Test echo -e with \\c to suppress newline."""
        shell.run_command('echo -e "no newline\\c"')
        captured = capsys.readouterr()
        assert captured.out == "no newline"


class TestPrintfBuiltin:
    """Test printf builtin functionality."""

    def test_printf_basic(self, shell, capsys):
        """Test basic printf functionality."""
        shell.run_command('printf "Hello, World!\\n"')
        captured = capsys.readouterr()
        assert captured.out == "Hello, World!\n"

    def test_printf_no_newline(self, shell, capsys):
        """Test printf doesn't add newline by default."""
        shell.run_command('printf "hello"')
        captured = capsys.readouterr()
        assert captured.out == "hello"

    def test_printf_string_format(self, shell, capsys):
        """Test printf %s string format."""
        shell.run_command('printf "%s\\n" "test string"')
        captured = capsys.readouterr()
        assert captured.out == "test string\n"

        shell.run_command('printf "%s %s\\n" "hello" "world"')
        captured = capsys.readouterr()
        assert captured.out == "hello world\n"

    def test_printf_integer_formats(self, shell, capsys):
        """Test printf integer formats."""
        # Decimal
        shell.run_command('printf "%d\\n" 42')
        captured = capsys.readouterr()
        assert captured.out == "42\n"

        # Octal
        shell.run_command('printf "%o\\n" 8')
        captured = capsys.readouterr()
        assert captured.out == "10\n"

        # Hexadecimal
        shell.run_command('printf "%x\\n" 255')
        captured = capsys.readouterr()
        assert captured.out == "ff\n"

        shell.run_command('printf "%X\\n" 255')
        captured = capsys.readouterr()
        assert captured.out == "FF\n"

    def test_printf_float_formats(self, shell, capsys):
        """Test printf floating point formats."""
        shell.run_command('printf "%.2f\\n" 3.14159')
        captured = capsys.readouterr()
        assert captured.out == "3.14\n"

        shell.run_command('printf "%e\\n" 1000')
        captured = capsys.readouterr()
        assert "e" in captured.out.lower()

        shell.run_command('printf "%g\\n" 0.0001')
        captured = capsys.readouterr()
        # Should use shorter of %f or %e

    def test_printf_width_precision(self, shell, capsys):
        """Test printf width and precision."""
        shell.run_command('printf "%10s\\n" "right"')
        captured = capsys.readouterr()
        assert captured.out == "     right\n"

        shell.run_command('printf "%-10s\\n" "left"')
        captured = capsys.readouterr()
        assert captured.out == "left      \n"

        shell.run_command('printf "%05d\\n" 42')
        captured = capsys.readouterr()
        assert captured.out == "00042\n"

    def test_printf_escape_sequences(self, shell, capsys):
        """Test printf escape sequences."""
        shell.run_command('printf "line1\\nline2\\n"')
        captured = capsys.readouterr()
        assert captured.out == "line1\nline2\n"

        shell.run_command('printf "\\t\\ttab\\n"')
        captured = capsys.readouterr()
        assert captured.out == "\t\ttab\n"

        shell.run_command('printf "\\x41\\n"')
        captured = capsys.readouterr()
        assert captured.out == "A\n"

    def test_printf_percent_escape(self, shell, capsys):
        """Test printf %% for literal percent."""
        shell.run_command('printf "100%%\\n"')
        captured = capsys.readouterr()
        assert captured.out == "100%\n"

    def test_printf_multiple_arguments(self, shell, capsys):
        """Test printf with format reuse."""
        shell.run_command('printf "%s\\n" one two three')
        captured = capsys.readouterr()
        assert captured.out == "one\ntwo\nthree\n"

    def test_printf_missing_arguments(self, shell, capsys):
        """Test printf with missing arguments."""
        shell.run_command('printf "%s %s\\n" one')
        captured = capsys.readouterr()
        # Second %s might be empty or show special behavior
        assert "one" in captured.out

    def test_printf_char_format(self, shell, capsys):
        """Test printf %c character format."""
        shell.run_command('printf "%c\\n" A')
        captured = capsys.readouterr()
        assert captured.out == "A\n"

        shell.run_command('printf "%c\\n" ABC')
        captured = capsys.readouterr()
        assert captured.out == "A\n"  # Only first char

class TestReadBuiltin:
    """Test read builtin functionality."""

    def test_read_timeout(self, shell, capsys, monkeypatch):
        """read -t returns non-zero when no full line arrives in time."""
        from io import StringIO
        # No input available: read must give up (non-zero) rather than hang.
        monkeypatch.setattr('sys.stdin', StringIO(""))
        assert shell.run_command('read -t 0.1 var') != 0
        # Might timeout and return non-zero

    def test_read_n_chars(self, shell, capsys, monkeypatch):
        """Test read -n to read N characters."""
        from io import StringIO
        monkeypatch.setattr('sys.stdin', StringIO("abcdefghij"))
        shell.run_command('read -n 5 var')
        shell.run_command('echo "Read: $var"')
        captured = capsys.readouterr()
        assert "Read: abcde" in captured.out

    def test_read_array(self, shell, capsys, monkeypatch):
        """Test read -a into array."""
        from io import StringIO
        monkeypatch.setattr('sys.stdin', StringIO("one two three four\n"))
        shell.run_command('read -a arr')
        shell.run_command('echo "${arr[0]} ${arr[1]} ${arr[2]}"')
        captured = capsys.readouterr()
        assert "one two three" in captured.out

    def test_read_raw_mode(self, shell, capsys, monkeypatch):
        """Test read -r raw mode (no backslash escape)."""
        from io import StringIO
        monkeypatch.setattr('sys.stdin', StringIO("test\\nstring\\tdata\n"))
        shell.run_command('read -r var')
        shell.run_command('echo "$var"')
        captured = capsys.readouterr()
        assert "test\\nstring\\tdata" in captured.out

        # Without -r, backslashes might be processed
        monkeypatch.setattr('sys.stdin', StringIO("test\\nstring\n"))
        shell.run_command('read var2')
        shell.run_command('echo "$var2"')
        captured = capsys.readouterr()
        # Might have processed the \n

    def test_read_ifs(self, shell, capsys, monkeypatch):
        """Test read with custom IFS."""
        from io import StringIO
        monkeypatch.setattr('sys.stdin', StringIO("one:two:three\n"))
        shell.run_command('IFS=: read a b c')
        shell.run_command('echo "a=$a b=$b c=$c"')
        captured = capsys.readouterr()
        assert "a=one" in captured.out
        assert "b=two" in captured.out
        assert "c=three" in captured.out

    def test_read_empty_input(self, shell, capsys, monkeypatch):
        """Test read with empty input."""
        from io import StringIO
        monkeypatch.setattr('sys.stdin', StringIO("\n"))
        shell.run_command('read var')
        shell.run_command('echo "var=[$var]"')
        captured = capsys.readouterr()
        assert "var=[]" in captured.out

    def test_read_eof(self, shell, capsys, monkeypatch):
        """Test read at EOF."""
        from io import StringIO
        monkeypatch.setattr('sys.stdin', StringIO(""))  # No input
        exit_code = shell.run_command('read var')
        assert exit_code != 0  # Should fail on EOF

    def test_read_line_continuation(self, shell, capsys, monkeypatch):
        """A trailing backslash-newline continues the line into `read`."""
        from io import StringIO
        monkeypatch.setattr('sys.stdin', StringIO("line one \\\nline two\n"))
        shell.run_command('read var')
        capsys.readouterr()
        shell.run_command('echo "$var"')
        captured = capsys.readouterr()
        assert captured.out.strip() == 'line one line two'
        # Might join lines or not depending on mode


class TestIORedirection:
    """Test I/O builtin behavior with redirection."""

    def test_echo_to_file(self, shell, capsys):
        """Test echo with output redirection."""
        shell.run_command('echo "test content" > testfile.txt')

        # Verify file was created and has content
        assert os.path.exists('testfile.txt')
        with open('testfile.txt', 'r') as f:
            content = f.read()
        assert content == "test content\n"

        # Clean up
        os.remove('testfile.txt')

    def test_printf_append(self, shell, capsys):
        """Test printf with append redirection."""
        shell.run_command('printf "line1\\n" > testfile.txt')
        shell.run_command('printf "line2\\n" >> testfile.txt')

        # Verify file has both lines
        with open('testfile.txt', 'r') as f:
            content = f.read()
        assert content == "line1\nline2\n"

        # Clean up
        os.remove('testfile.txt')

    def test_read_from_file(self, shell, capsys):
        """Test read with input redirection."""
        # Create input file
        with open('input.txt', 'w') as f:
            f.write('file content\n')

        shell.run_command('read var < input.txt')
        shell.run_command('echo "Read: $var"')
        captured = capsys.readouterr()
        assert "Read: file content" in captured.out

        # Clean up
        os.remove('input.txt')
