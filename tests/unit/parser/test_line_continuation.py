"""
Line continuation processing tests.

Tests for the line continuation preprocessing functionality
that handles backslash-newline sequences.
"""



def test_basic_line_continuation():
    """Test basic line continuation processing."""
    from psh.lexer import tokenize
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo hello \\\nworld")
    assert result == "echo hello world"

    # Verify tokenization works correctly
    tokens = tokenize(result)
    token_values = [t.value for t in tokens if t.type.name != 'EOF']
    assert token_values == ['echo', 'hello', 'world']


def test_line_continuation_without_space():
    """Test line continuation without space before backslash."""
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo hello\\\nworld")
    assert result == "echo helloworld"


def test_line_continuation_with_spaces_after():
    """Test line continuation with spaces after the newline."""
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo hello \\\n   world")
    assert result == "echo hello    world"


def test_multiple_continuations():
    """Test multiple line continuations."""
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo \\\nhello \\\nworld")
    assert result == "echo hello world"


def test_escaped_backslashes_with_continuation():
    """Test escaped backslashes with line continuations."""
    from psh.scripting.input_preprocessing import process_line_continuations

    # 3 backslashes: \\\\ -> \\, last \ escapes \n
    result = process_line_continuations("echo hello\\\\\\\nworld")
    assert result == "echo hello\\\\world"

    # 5 backslashes: \\\\\\\\\\ -> \\\\, last \ escapes \n
    result = process_line_continuations("echo hello\\\\\\\\\\\nworld")
    assert result == "echo hello\\\\\\\\world"


def test_even_backslashes_no_continuation():
    """Test even number of backslashes - no line continuation."""
    from psh.scripting.input_preprocessing import process_line_continuations

    # 2 backslashes: \\\\ -> \\, \n stays as literal
    result = process_line_continuations("echo hello\\\\\nworld")
    assert result == "echo hello\\\\\nworld"

    # 4 backslashes: \\\\\\\\ -> \\\\, \n stays as literal
    result = process_line_continuations("echo hello\\\\\\\\\nworld")
    assert result == "echo hello\\\\\\\\\nworld"


def test_quotes_prevent_processing():
    """Test that quotes prevent line continuation processing."""
    from psh.scripting.input_preprocessing import process_line_continuations

    # Single quotes prevent processing
    result = process_line_continuations("echo 'hello \\\nworld'")
    assert result == "echo 'hello \\\nworld'"

    # Double quotes allow processing (bash behavior)
    result = process_line_continuations('echo "hello \\\nworld"')
    assert result == 'echo "hello world"'


def test_mixed_quotes_and_continuations():
    """Test mixed quotes and line continuations."""
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo 'no \\\nprocess' \\\nyes")
    assert result == "echo 'no \\\nprocess' yes"


def test_escaped_quotes():
    """Test that escaped quotes don't affect quote state."""
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo \\\"hello \\\nworld\\\"")
    assert result == "echo \\\"hello world\\\""


def test_carriage_return_line_endings():
    """A ``\\<CR><LF>`` is NOT a line continuation (bash only joins ``\\<LF>``).

    The backslash escapes the CR into a literal CR word character and the LF
    ends the command, so the text is left verbatim for the lexer rather than
    spliced. (The file reader's documented dos2unix strip removes a trailing CR
    before this runs; the CR-keeping stdin/-c paths match bash here.)
    """
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo hello \\\r\nworld")
    assert result == "echo hello \\\r\nworld"


def test_empty_input():
    """Test empty input."""
    from psh.scripting.input_preprocessing import process_line_continuations

    assert process_line_continuations("") == ""


def test_no_continuation():
    """Test input without line continuations."""
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo hello world")
    assert result == "echo hello world"


def test_trailing_backslash_no_newline():
    """Test trailing backslash without newline."""
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo hello\\")
    assert result == "echo hello\\"


def test_tokenization_after_preprocessing():
    """Test that tokenization works correctly after preprocessing."""
    from psh.lexer import tokenize
    from psh.scripting.input_preprocessing import process_line_continuations

    # Test case that previously failed
    input_text = "echo hello \\\nworld"
    processed = process_line_continuations(input_text)
    tokens = tokenize(processed)

    # Should produce: echo, hello, world, EOF
    assert len(tokens) == 4
    assert tokens[0].value == "echo"
    assert tokens[1].value == "hello"
    assert tokens[2].value == "world"
    assert tokens[3].type.name == "EOF"


def test_complex_command_preprocessing():
    """Test preprocessing of complex multi-line commands."""
    from psh.scripting.input_preprocessing import process_line_continuations

    complex_command = """echo {1..3} \\
    | while read num
do
    echo "Number: $num"
done"""

    processed = process_line_continuations(complex_command)
    expected = """echo {1..3}     | while read num
do
    echo "Number: $num"
done"""

    assert processed == expected


def test_pipeline_with_continuations():
    """Test pipeline with line continuations."""
    from psh.lexer import tokenize
    from psh.scripting.input_preprocessing import process_line_continuations

    pipeline = "ls -la \\\n| grep test \\\n| sort"
    processed = process_line_continuations(pipeline)
    assert processed == "ls -la | grep test | sort"

    # Verify it tokenizes correctly
    tokens = tokenize(processed)
    pipe_count = sum(1 for t in tokens if t.type.name == 'PIPE')
    assert pipe_count == 2


def test_complex_script_like_testscript():
    """Test complex script similar to testscript.sh."""
    from psh.lexer import tokenize
    from psh.scripting.input_preprocessing import process_line_continuations

    script = """echo {1..10} \\
    | sed 's/ /\\n/g' \\
    | while read num
do echo -n "$num "
   if [ $((num%2)) -eq 0 ]
   then echo "even"
   else echo "odd"
   fi
done \\
    | sort +1"""

    processed = process_line_continuations(script)

    # Should not contain any \\\n sequences
    assert '\\\n' not in processed

    # Should contain the expected pipeline structure
    assert 'echo {1..10}     | sed' in processed
    assert 'done     | sort +1' in processed

    # Verify it can be tokenized without errors
    tokens = tokenize(processed)
    assert len(tokens) > 10  # Should have many tokens


def test_continuation_at_start_of_line():
    """Test line continuation at start of line."""
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("\\\necho hello")
    assert result == "echo hello"


def test_multiple_consecutive_continuations():
    """Test multiple consecutive line continuations."""
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo \\\n\\\n\\\nhello")
    assert result == "echo hello"


def test_continuation_with_only_whitespace_after():
    """Test line continuation with only whitespace after newline."""
    from psh.scripting.input_preprocessing import process_line_continuations

    result = process_line_continuations("echo hello \\\n   \\\nworld")
    assert result == "echo hello    world"


def test_complex_quoting_scenarios():
    """Test complex quoting scenarios."""
    from psh.scripting.input_preprocessing import process_line_continuations

    # Escaped quote doesn't end quote context, line continuation is processed
    result = process_line_continuations('echo "hello \\" \\\nworld"')
    assert result == 'echo "hello \\" world"'

    # Multiple quote levels
    result = process_line_continuations("echo 'single \"double \\\ninside\" single'")
    assert result == "echo 'single \"double \\\ninside\" single'"


def test_backslash_quote_interactions():
    """Test interactions between backslashes and quotes."""
    from psh.scripting.input_preprocessing import process_line_continuations

    # Backslash before quote
    result = process_line_continuations("echo \\' \\\nhello")
    assert result == "echo \\' hello"

    # Multiple backslashes before quote
    result = process_line_continuations("echo \\\\\\' \\\nhello")
    assert result == "echo \\\\\\' hello"
