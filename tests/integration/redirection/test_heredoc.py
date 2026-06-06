"""
Here document (heredoc) integration tests.

Tests for heredoc (<<) and here string (<<<) redirection functionality.
"""

import subprocess
import sys


def test_tokenize_heredoc():
    """Test that << is tokenized correctly."""
    from psh.lexer import tokenize
    from psh.token_types import TokenType

    tokens = tokenize("cat << EOF")
    assert tokens[1].type == TokenType.HEREDOC
    assert tokens[1].value == "<<"
    assert tokens[2].type == TokenType.WORD
    assert tokens[2].value == "EOF"


def test_tokenize_heredoc_strip():
    """Test that <<- is tokenized correctly."""
    from psh.lexer import tokenize
    from psh.token_types import TokenType

    tokens = tokenize("cat <<- END")
    assert tokens[1].type == TokenType.HEREDOC_STRIP
    assert tokens[1].value == "<<-"
    assert tokens[2].type == TokenType.WORD
    assert tokens[2].value == "END"


def test_parse_heredoc():
    """Test parsing of here document."""
    from psh.lexer import tokenize
    from psh.parser import parse

    tokens = tokenize("cat << EOF")
    ast = parse(tokens)
    command = ast.and_or_lists[0].pipelines[0].commands[0]

    assert len(command.redirects) == 1
    redirect = command.redirects[0]
    assert redirect.type == "<<"
    assert redirect.target == "EOF"
    assert redirect.heredoc_content is None  # Not collected yet


def test_tokenize_here_string():
    """Test that <<< is tokenized correctly."""
    from psh.lexer import tokenize
    from psh.token_types import TokenType

    tokens = tokenize("cat <<< 'hello world'")
    assert tokens[1].type == TokenType.HERE_STRING
    assert tokens[1].value == "<<<"
    assert tokens[2].type == TokenType.STRING
    assert tokens[2].value == "hello world"


def test_parse_here_string():
    """Test parsing of here string."""
    from psh.lexer import tokenize
    from psh.parser import parse

    tokens = tokenize("cat <<< 'test string'")
    ast = parse(tokens)
    command = ast.and_or_lists[0].pipelines[0].commands[0]

    assert len(command.redirects) == 1
    redirect = command.redirects[0]
    assert redirect.type == "<<<"
    assert redirect.target == "test string"


def test_here_string_literal(shell_with_temp_dir):
    """Test here string with literal text."""
    output_file = "herestring_literal_test.txt"
    result = shell_with_temp_dir.run_command(f"cat <<< 'literal text' > {output_file}")
    assert result == 0

    with open(output_file, 'r') as f:
        content = f.read()
    assert content == "literal text\n"


def test_here_string_with_builtin(shell_with_temp_dir):
    """Test here string output to file."""
    output_file = "herestring_builtin_test.txt"
    result = shell_with_temp_dir.run_command(f"cat <<< 'from here string' > {output_file}")
    assert result == 0

    with open(output_file, 'r') as f:
        content = f.read()
    assert content == "from here string\n"


def test_here_string_with_quotes(shell_with_temp_dir):
    """Test here string handling quotes properly."""
    output_file = "herestring_quotes_test.txt"
    result = shell_with_temp_dir.run_command(f'cat <<< "She said \\"Hello\\"" > {output_file}')
    assert result == 0

    with open(output_file, 'r') as f:
        content = f.read()
    assert 'She said "Hello"' in content


def test_here_string_empty(shell_with_temp_dir):
    """Test empty here string."""
    output_file = "herestring_empty_test.txt"
    result = shell_with_temp_dir.run_command(f"cat <<< '' > {output_file}")
    assert result == 0

    with open(output_file, 'r') as f:
        content = f.read()
    assert content == "\n"  # Just a newline


def test_here_string_in_pipeline(shell_with_temp_dir):
    """Test here string in a pipeline."""
    output_file = "herestring_pipeline_test.txt"
    result = shell_with_temp_dir.run_command(f"cat <<< 'apple banana cherry' | wc -w > {output_file}")
    assert result == 0

    with open(output_file, 'r') as f:
        content = f.read().strip()
    assert "3" in content


def test_here_string_with_variable(shell_with_temp_dir):
    """Test here string with variable expansion."""
    shell_with_temp_dir.state.set_variable('NAME', 'World')

    output_file = "herestring_var_test.txt"
    result = shell_with_temp_dir.run_command(f'cat <<< "Hello $NAME" > {output_file}')
    assert result == 0

    with open(output_file, 'r') as f:
        content = f.read()
    assert content == "Hello World\n"


def test_heredoc_with_builtin():
    """Test here document with cat command."""
    import subprocess
    import sys
    # Use subprocess since cat is an external command
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', '''cat << EOF
Hello from heredoc
Line 2
EOF
'''],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert result.stdout == "Hello from heredoc\nLine 2\n"


def test_heredoc_strip_tabs():
    """Test here document with tab stripping."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', """cat <<- EOF
\tIndented line
\t\tDouble indented
Not indented
EOF
"""],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert result.stdout == "Indented line\nDouble indented\nNot indented\n"


def test_heredoc_strip_tabs_indented_delimiter():
    """`<<-` strips leading tabs from the closing delimiter, not just content.

    In bash, `cat <<-EOF ... \\tEOF` closes on the tab-indented `EOF` and prints
    the (tab-stripped) body. Regression test for a bug where psh emitted nothing
    because the lexer heredoc collector compared the delimiter line without
    stripping its leading tabs.
    """
    script = "cat <<-EOF\n\tindented\n\tEOF\n"
    psh = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True,
    )
    bash = subprocess.run(['bash', '-c', script], capture_output=True, text=True)

    assert psh.returncode == 0
    assert bash.stdout == "indented\n"   # documents the correct behavior
    assert psh.stdout == bash.stdout


def test_heredoc_empty():
    """Test empty here document."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', """cat << EOF
EOF
"""],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_heredoc_with_variable_expansion():
    """Test variable expansion in heredocs."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'NAME="World"; cat << EOF\nHello $NAME\nPath: $PWD\nEOF\n'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Hello World" in result.stdout
    assert "Path: " in result.stdout


def test_heredoc_with_external_command():
    """Test here document with external command."""
    import subprocess
    import sys
    # Use subprocess to test external command
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'cat << EOF\nExternal test\nEOF'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert result.stdout == "External test\n"


def test_heredoc_with_output_redirect(isolated_shell_with_temp_dir):
    """Test here document with output redirection."""
    shell = isolated_shell_with_temp_dir
    result = shell.run_command("""cat << EOF > output.txt
Redirected content
Line 2
EOF
""")
    assert result == 0

    # Check file content
    import os
    output_file = os.path.join(shell.state.variables['PWD'], 'output.txt')
    with open(output_file, 'r') as f:
        content = f.read()
    assert content == "Redirected content\nLine 2\n"


def test_heredoc_in_pipeline():
    """Test here document in pipeline."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', """cat << EOF | wc -l
Line 1
Line 2
Line 3
EOF
"""],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "3"


def test_heredoc_syntax_variants():
    """Test various heredoc syntax forms are parsed correctly."""
    from psh.lexer import tokenize
    from psh.parser import parse

    # Test different spacing patterns
    test_cases = [
        "cat <<EOF",
        "cat << EOF",
        "cat <<-EOF",
        "cat <<- EOF"
    ]

    for case in test_cases:
        tokens = tokenize(case)
        ast = parse(tokens)
        command = ast.and_or_lists[0].pipelines[0].commands[0]
        assert len(command.redirects) == 1
        assert command.redirects[0].type in ["<<", "<<-"]


def test_here_string_syntax_variants():
    """Test various here string syntax forms are parsed correctly."""
    from psh.lexer import tokenize
    from psh.parser import parse

    # Test different quoting patterns
    test_cases = [
        "cat <<<word",
        "cat <<< word",
        "cat <<<'word'",
        "cat <<<\"word\"",
        "cat <<< 'quoted word'",
        "cat <<< \"quoted word\""
    ]

    for case in test_cases:
        tokens = tokenize(case)
        ast = parse(tokens)
        command = ast.and_or_lists[0].pipelines[0].commands[0]
        assert len(command.redirects) == 1
        assert command.redirects[0].type == "<<<"
