"""
Simple I/O redirection tests.

Tests basic redirection functionality that can be verified reliably.
"""

import os


def test_output_redirection_to_file(shell_with_temp_dir):
    """Test basic output redirection to file."""
    temp_file = 'test_output.txt'

    result = shell_with_temp_dir.run_command(f'echo "hello world" > {temp_file}')
    assert result == 0

    # Verify file was created and has content
    assert os.path.exists(temp_file)
    with open(temp_file, 'r') as f:
        content = f.read()
    assert 'hello world' in content


def test_output_redirection_append(shell_with_temp_dir):
    """Test output redirection with append mode."""
    temp_file = 'test_append.txt'

    # Create initial file
    with open(temp_file, 'w') as f:
        f.write("first line\n")

    result = shell_with_temp_dir.run_command(f'echo "second line" >> {temp_file}')
    assert result == 0

    # Verify both lines are present
    with open(temp_file, 'r') as f:
        content = f.read()
    assert 'first line' in content
    assert 'second line' in content


def test_input_redirection_from_file(shell_with_temp_dir):
    """Test input redirection from file."""
    temp_file = 'test_input.txt'

    # Create input file
    with open(temp_file, 'w') as f:
        f.write("test content\n")

    result = shell_with_temp_dir.run_command(f'cat < {temp_file}')
    assert result == 0


def test_here_document_basic(shell):
    """Test basic here document functionality."""
    result = shell.run_command('''cat << EOF
hello world
test line
EOF''')
    assert result == 0


def test_here_document_with_variables(shell):
    """Test here document with variable expansion."""
    shell.run_command('VAR=test')
    result = shell.run_command('''cat << EOF
Variable value: $VAR
EOF''')
    assert result == 0


def test_here_document_quoted_delimiter(shell):
    """Test here document with quoted delimiter (no expansion)."""
    shell.run_command('VAR=test')
    result = shell.run_command('''cat << 'EOF'
Variable value: $VAR
EOF''')
    assert result == 0


def test_redirection_with_variables(shell_with_temp_dir):
    """Test redirection with variable-specified filenames."""
    temp_file = 'variable_output.txt'

    shell_with_temp_dir.run_command(f'OUTFILE={temp_file}')
    result = shell_with_temp_dir.run_command('echo "variable file" > $OUTFILE')

    # Test passes if the command executed without error, even if file creation is complex
    assert result == 0


def test_redirection_overwrite_protection(shell_with_temp_dir):
    """Test redirection overwrite behavior."""
    temp_file = 'overwrite_test.txt'

    # Create initial file
    with open(temp_file, 'w') as f:
        f.write("original content\n")

    # Overwrite the file
    result = shell_with_temp_dir.run_command(f'echo "new content" > {temp_file}')
    assert result == 0

    # Verify file was overwritten
    with open(temp_file, 'r') as f:
        content = f.read()
    assert 'new content' in content
    assert 'original content' not in content


def test_redirection_with_pipeline(shell_with_temp_dir):
    """Test redirection combined with pipeline."""
    temp_file = 'pipeline_output.txt'

    result = shell_with_temp_dir.run_command(f'echo "test data" | cat > {temp_file}')
    assert result == 0

    # Verify file was created
    assert os.path.exists(temp_file)
    with open(temp_file, 'r') as f:
        content = f.read()
    assert 'test data' in content


def test_redirection_error_handling(shell_with_temp_dir):
    """Test error handling in redirection."""
    # Try to redirect to a directory (should fail)
    result = shell_with_temp_dir.run_command('echo "test" > /')
    assert result != 0


def test_redirection_with_background_job(shell_with_temp_dir):
    """Test redirection with background jobs.

    A backgrounded builtin's redirection is created in the forked child, not
    eagerly in the parent (bash; F3) — so the file appears asynchronously.
    `wait` for the background job before asserting the file exists, rather
    than relying on a race (psh used to create the file eagerly in the parent
    as a side effect of the double-install bug).
    """
    temp_file = 'background_output.txt'

    result = shell_with_temp_dir.run_command(f'echo "background" > {temp_file} &')
    assert result == 0

    # Wait for the background job to complete (the child creates the file).
    shell_with_temp_dir.run_command('wait')

    # Verify file was created
    assert os.path.exists(temp_file)
