#!/usr/bin/env python3
"""Tests for ANSI-C quoting ($'...') functionality."""



class TestAnsiCQuoting:
    """Test ANSI-C quoting functionality."""

    def test_basic_ansi_c_quote(self, shell, capsys):
        """Test basic ANSI-C quoting."""
        result = shell.run_command("echo $'hello world'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "hello world\n"

    def test_newline_escape(self, shell, capsys):
        """Test newline escape sequence."""
        result = shell.run_command("echo $'line1\\nline2'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "line1\nline2\n"

    def test_tab_escape(self, shell, capsys):
        """Test tab escape sequence."""
        result = shell.run_command("echo $'col1\\tcol2'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "col1\tcol2\n"

    def test_all_basic_escapes(self, shell, capsys):
        """Test all basic escape sequences."""
        # Test each escape sequence
        escapes = {
            '\\n': '\n',  # newline
            '\\t': '\t',  # tab
            '\\r': '\r',  # carriage return
            '\\b': '\b',  # backspace
            '\\f': '\f',  # form feed
            '\\v': '\v',  # vertical tab
            '\\a': '\a',  # bell
            '\\\\': '\\', # backslash
            "\\'": "'",   # single quote
            '\\"': '"',   # double quote
            '\\?': '?',   # question mark
        }

        for escape, expected in escapes.items():
            result = shell.run_command(f"echo -n $'{escape}'")
            assert result == 0
            captured = capsys.readouterr()
            assert captured.out == expected

    def test_ansi_escape(self, shell, capsys):
        """Test ANSI escape sequences."""
        # \e and \E should both produce ESC character (0x1b)
        # Since ESC is a control character, test by checking its presence in a string
        result = shell.run_command("test $'\\e' = $'\\x1b' && echo 'ESC works'")
        assert result == 0
        captured = capsys.readouterr()
        assert "ESC works" in captured.out

        # Test \E as well
        result = shell.run_command("test $'\\E' = $'\\x1b' && echo 'ESC-E works'")
        assert result == 0
        captured = capsys.readouterr()
        assert "ESC-E works" in captured.out

    def test_hex_escapes(self, shell, capsys):
        """Test hexadecimal escape sequences."""
        # \xHH format
        result = shell.run_command("echo $'\\x41\\x42\\x43'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "ABC\n"

        # Test single hex digit
        result = shell.run_command("echo -n $'\\x9'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "\t"  # \x9 is tab

    def test_octal_escapes(self, shell, capsys):
        """Test octal escape sequences (\\nnn, 1-3 digits, like bash)."""
        # \NNN format (no leading zero required): \101 = 'A'
        result = shell.run_command("echo $'\\101\\102\\103'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "ABC\n"

        # A leading zero is just the first octal digit; only 3 digits are
        # consumed, so \0101 == octal 010 (backspace) followed by '1'.
        result = shell.run_command("echo $'\\0101'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "\b1\n"

        # Short octal escape.
        result = shell.run_command("echo $'\\7'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "\a\n"

        # Test null character
        # Since null is hard to test directly, verify it's different from other chars
        result = shell.run_command("test $'\\0' != 'a' && echo 'null works'")
        assert result == 0
        captured = capsys.readouterr()
        assert "null works" in captured.out

    def test_unicode_escapes(self, shell, capsys):
        """Test Unicode escape sequences."""
        # \uHHHH format (4 hex digits)
        result = shell.run_command("echo $'\\u0041\\u0042\\u0043'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "ABC\n"

        # bash accepts 1-4 digits after \u and 1-8 after \U.
        result = shell.run_command("echo $'\\u41'")
        assert result == 0
        assert capsys.readouterr().out == "A\n"

        result = shell.run_command("echo $'\\U41'")
        assert result == 0
        assert capsys.readouterr().out == "A\n"

        # Test emoji
        result = shell.run_command("echo $'\\u263A'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "☺\n"

        # \UHHHHHHHH format (8 hex digits)
        result = shell.run_command("echo $'\\U0001F600'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "😀\n"

    def test_no_variable_expansion(self, shell, capsys):
        """Test that variables are not expanded in ANSI-C quotes."""
        result = shell.run_command("HOME=/test; echo $'$HOME'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "$HOME\n"

        # Also test with braces
        result = shell.run_command("VAR=value; echo $'${VAR}'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "${VAR}\n"

    def test_no_command_substitution(self, shell, capsys):
        """Test that command substitution doesn't occur in ANSI-C quotes."""
        result = shell.run_command("echo $'$(echo test)'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "$(echo test)\n"

        # Also test backticks
        result = shell.run_command("echo $'`echo test`'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "`echo test`\n"

    def test_mixed_quotes(self, shell, capsys):
        """Test mixing ANSI-C quotes with other quote types."""
        # ANSI-C quotes inside double quotes are not processed (bash behavior)
        result = shell.run_command('echo "$\'hello\\nworld\'"')
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "$'hello\\nworld'\n"

        # ANSI-C quote containing regular quotes
        result = shell.run_command("echo $'He said \"hello\" to me'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == 'He said "hello" to me\n'

    def test_unclosed_ansi_c_quote(self, shell, capsys):
        """Test error handling for unclosed ANSI-C quotes."""
        result = shell.run_command("echo $'unclosed")
        assert result != 0
        captured = capsys.readouterr()
        assert "Unclosed $' quote" in captured.err

    def test_invalid_escape_sequences(self, shell, capsys):
        """Test handling of invalid escape sequences."""
        # Invalid hex escape (no digits)
        result = shell.run_command("echo $'\\x'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "\\x\n"

        # Unknown escape sequence
        result = shell.run_command("echo $'\\q'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "\\q\n"

    def test_concatenation(self, shell, capsys):
        """Test concatenation with ANSI-C quotes."""
        result = shell.run_command("echo $'hello'$'\\n'$'world'")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "hello\nworld\n"

    def test_concatenation_with_strings(self, shell, capsys):
        """Test concatenation of ANSI-C quotes with regular strings."""
        # This should work but currently doesn't - PSH treats $' as separate token
        result = shell.run_command("echo prefix$'\\t'suffix")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "prefix\tsuffix\n"

    def test_in_variable_assignment(self, shell, capsys):
        """Test ANSI-C quotes in variable assignments."""
        result = shell.run_command("var=$'line1\\nline2'; echo \"$var\"")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "line1\nline2\n"

    def test_in_array_assignment(self, shell, capsys):
        """Test ANSI-C quotes in array assignments."""
        result = shell.run_command("arr=($'a\\tb' $'c\\nd'); echo \"${arr[0]}\"; echo \"${arr[1]}\"")
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "a\tb\nc\nd\n"

    def test_in_here_string(self):
        """Test ANSI-C quotes in here strings.

        Run in a subprocess: the here string feeds an external command (`cat`)
        that forks and writes via raw file descriptors, so capsys cannot capture
        it in-process. The subprocess captures the real fd output.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', "cat <<< $'line1\\nline2'"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert result.stdout == "line1\nline2\n"

    def test_in_case_patterns(self, shell, capsys):
        """Test ANSI-C quotes in case patterns."""
        script = '''
        var=$'a\\tb'
        case "$var" in
            $'a\\tb') echo "matched tab";;
            *) echo "no match";;
        esac
        '''
        result = shell.run_command(script)
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == "matched tab\n"

    def test_complex_example(self, shell, capsys):
        """Test a complex example with multiple features."""
        script = r'''
        msg=$'Error on line 42:\n\tFile not found: \x22test.txt\x22\n\tPlease check the path'
        echo "$msg"
        '''
        result = shell.run_command(script)
        assert result == 0
        captured = capsys.readouterr()
        expected = 'Error on line 42:\n\tFile not found: "test.txt"\n\tPlease check the path\n'
        assert captured.out == expected


class TestAnsiCQuoteMetadata:
    """Reappraisal #15 J6: a ``$'...'`` in assignment-value / concatenation
    position must keep its quote metadata (it lexes as its own ``$'``-typed
    STRING token that the parser re-joins into a composite Word), exactly like
    ``"..."`` does — instead of being decoded inline into a flat, quote-less
    literal. Previously the metadata was lost, so ``--format`` re-emitted a raw
    (word-splitting) value and ran the second line as a command.
    """

    def _tokens(self, src):
        # ANSI-C metadata is a RECOGNIZER property (a $'...' value lexes as its
        # own STRING before word fusion composites it into the assignment word);
        # assert on the pre-fusion stream.
        from lexer_test_helpers import tokenize_unfused
        return [t for t in tokenize_unfused(src) if t.type.name != 'EOF']

    def _assignment_word(self, src):
        from psh.ast_nodes import SimpleCommand
        from psh.lexer import tokenize
        from psh.parser import parse
        node = parse(tokenize(src))

        found = []

        def walk(n):
            if isinstance(n, SimpleCommand):
                found.extend(n.words)
            for attr in ('items', 'statements', 'pipelines', 'commands'):
                v = getattr(n, attr, None)
                if isinstance(v, list):
                    for x in v:
                        walk(x)
        walk(node)
        return found[0]

    def test_assignment_value_lexes_as_separate_string(self):
        from psh.lexer.token_types import TokenType
        toks = self._tokens("v=$'a\\tb'")
        assert [t.type for t in toks] == [TokenType.WORD, TokenType.STRING]
        assert toks[0].value == 'v='
        assert toks[1].value == 'a\tb'      # decoded value
        assert toks[1].quote_type == "$'"   # quote metadata preserved

    def test_assignment_word_carries_ansi_c_part(self):
        from psh.ast_nodes import LiteralPart
        word = self._assignment_word("v=$'a\\tb'")
        # v= (unquoted) + a<tab>b (quoted with $')
        assert word.parts[0] == LiteralPart('v=', quoted=False, quote_char=None)
        assert word.parts[-1].quote_char == "$'"
        assert word.parts[-1].text == 'a\tb'

    def test_concatenation_word_carries_ansi_c_part(self):
        word = self._assignment_word("echo a$'b\\tc'd")  # first word is `echo`
        word = self._assignment_word("x=a$'b\\tc'd")
        quote_chars = [getattr(p, 'quote_char', None) for p in word.parts]
        assert "$'" in quote_chars
        assert word.display_text() == 'x=ab\tcd'

    def test_runtime_value_preserved(self, shell, capsys):
        # The whole point: metadata is added WITHOUT changing the value.
        assert shell.run_command("v=$'a\\tb'; printf '%s' \"$v\"") == 0
        assert capsys.readouterr().out == 'a\tb'


class TestTrailingControlEscape:
    """`\\c` immediately before the closing quote of a $'...' string.

    Regression for reappraisal #16 Tier-2 (lexer): the ``\\c`` control-escape
    read its control char using the whole input length as the boundary, so a
    ``\\c`` right before the closing quote consumed the quote and reported an
    unclosed string. bash finds the string's closing quote before decoding
    escapes, so a ``\\c`` with no control char left in the string stays a
    literal ``\\c`` (bash 5.2-verified).
    """

    def test_trailing_c_is_literal(self, shell, capsys):
        assert shell.run_command(r"printf '%s' $'abc\c'") == 0
        assert capsys.readouterr().out == 'abc\\c'

    def test_lone_c_is_literal(self, shell, capsys):
        assert shell.run_command(r"printf '[%s]' $'\c'") == 0
        assert capsys.readouterr().out == '[\\c]'

    def test_c_then_text_after_quote(self, shell, capsys):
        # $'a\c' is a\c (literal), then z concatenates outside the quote.
        assert shell.run_command(r"printf '[%s]' $'a\c'z") == 0
        assert capsys.readouterr().out == '[a\\cz]'

    def test_interior_control_escape_still_decodes(self, shell, capsys):
        # \cb (a real control char follows) is still Ctrl-B (0x02).
        assert shell.run_command(r"printf '%s' $'a\cb'") == 0
        assert capsys.readouterr().out == 'a\x02'

    def test_at_E_expansion_still_consumes_control_char(self, shell, capsys):
        # ${var@E} has no closing-quote boundary: \c' consumes the quote as
        # its control char there (bash), unlike the lexer's $'...' context.
        # v holds the literal bytes a \ c ' b; @E decodes \c' to Ctrl-' (0x07).
        assert shell.run_command(
            r"""v=$'a\\c\x27b'; printf '%s' "${v@E}" """) == 0
        assert capsys.readouterr().out == 'a\x07b'
