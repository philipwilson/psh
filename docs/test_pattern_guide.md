# PSH Test Pattern Standardization Guide

## Overview

This guide provides standardized patterns for writing PSH tests to ensure consistency, reliability, and maintainability across the test suite.

## Test Categories and Appropriate Fixtures

### 1. Unit Tests - Builtin Output Testing

**Use: `captured_shell` fixture**

For testing builtin commands that produce output to stdout/stderr.

```python
def test_builtin_output(captured_shell):
    """Standard pattern for testing builtin output."""
    # Run command
    result = captured_shell.run_command("echo hello")
    
    # Check exit code
    assert result == 0
    
    # Check output
    assert captured_shell.get_stdout() == "hello\n"
    assert captured_shell.get_stderr() == ""
    
    # Clear output between tests if needed
    captured_shell.clear_output()
```

**When to use:**
- Testing builtin commands (echo, printf, type, etc.)
- Testing command output without file I/O
- Testing error messages

**When NOT to use:**
- Tests involving file redirection
- Tests involving pipelines
- Tests involving background jobs

### 2. Integration Tests - File I/O and Redirection

**Use: `isolated_shell_with_temp_dir` fixture**

For testing features that manipulate files or file descriptors.

```python
def test_file_redirection(isolated_shell_with_temp_dir):
    """Standard pattern for testing file I/O."""
    shell = isolated_shell_with_temp_dir
    
    # Create and redirect to file
    result = shell.run_command("echo 'content' > file.txt")
    assert result == 0
    
    # Read file directly (not through shell output capture)
    import os
    file_path = os.path.join(shell.state.variables['PWD'], 'file.txt')
    with open(file_path) as f:
        assert f.read() == "content\n"
```

**When to use:**
- Testing I/O redirection (>, >>, <, etc.)
- Testing file manipulation
- Testing features that need real file descriptors

**When NOT to use:**
- Simple output testing
- When you need to capture command output

### 3. System Tests - External Process Comparison

**Use: `subprocess.run` directly**

For conformance testing or comparing PSH behavior with other shells.

```python
def test_conformance():
    """Standard pattern for conformance testing."""
    import subprocess
    import sys
    
    command = "echo $((1 + 1))"
    
    # Test PSH
    psh_result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', command],
        capture_output=True,
        text=True
    )
    
    # Test bash
    bash_result = subprocess.run(
        ['bash', '-c', command],
        capture_output=True,
        text=True
    )
    
    # Compare
    assert psh_result.stdout == bash_result.stdout
    assert psh_result.returncode == bash_result.returncode
```

**When to use:**
- Conformance testing
- Testing PSH as an external process
- Comparing with other shells

**When NOT to use:**
- Unit testing individual components
- When you need access to shell state

## Common Patterns

### Pattern 1: Testing Multiple Commands

```python
def test_command_sequence(captured_shell):
    """Test multiple commands in sequence."""
    # Set up state
    captured_shell.run_command("VAR1=hello")
    captured_shell.run_command("VAR2=world")
    captured_shell.clear_output()  # Clear setup output
    
    # Test actual command
    result = captured_shell.run_command("echo $VAR1 $VAR2")
    assert result == 0
    assert captured_shell.get_stdout() == "hello world\n"
```

### Pattern 2: Testing Error Conditions

```python
def test_error_handling(captured_shell):
    """Test error output and exit codes."""
    result = captured_shell.run_command("cd /nonexistent/directory")
    
    # Check failure
    assert result != 0
    
    # Check error message
    stderr = captured_shell.get_stderr()
    assert "No such file or directory" in stderr
```

### Pattern 3: Testing with Temporary Files

```python
def test_with_temp_files(isolated_shell_with_temp_dir):
    """Test with temporary files in isolated directory."""
    shell = isolated_shell_with_temp_dir
    
    # Create test data
    shell.run_command("echo 'test data' > input.txt")
    
    # Process data
    result = shell.run_command("cat input.txt | wc -w > count.txt")
    assert result == 0
    
    # Verify result
    import os
    count_file = os.path.join(shell.state.variables['PWD'], 'count.txt')
    with open(count_file) as f:
        # Note: exact format may vary
        assert "2" in f.read()
```

## Anti-Patterns to Avoid

### ❌ Don't mix capsys with shell that does I/O redirection

```python
# BAD - This will fail due to FD conflicts
def test_bad_pattern(shell, capsys):
    shell.run_command("echo hello > file.txt")
    captured = capsys.readouterr()  # Won't capture redirected output
```

### ❌ Don't use captured_shell for file operations

```python
# BAD - Output capture conflicts with redirection
def test_bad_file_ops(captured_shell):
    captured_shell.run_command("echo hello > file.txt")
    # get_stdout() won't show the output (it went to file)
```

### ❌ Don't forget to clear output between tests

```python
# BAD - Output accumulates
def test_accumulation(captured_shell):
    captured_shell.run_command("echo first")
    captured_shell.run_command("echo second")
    # get_stdout() now contains "first\nsecond\n"
```

### ✅ Good practice - Clear between tests

```python
def test_good_practice(captured_shell):
    captured_shell.run_command("echo first")
    assert captured_shell.get_stdout() == "first\n"
    
    captured_shell.clear_output()
    
    captured_shell.run_command("echo second")
    assert captured_shell.get_stdout() == "second\n"
```

## Migration Guide

### From capsys to captured_shell

Before:
```python
def test_old_style(shell, capsys):
    shell.run_command("echo hello")
    captured = capsys.readouterr()
    assert captured.out == "hello\n"
```

After:
```python
def test_new_style(captured_shell):
    result = captured_shell.run_command("echo hello")
    assert result == 0
    assert captured_shell.get_stdout() == "hello\n"
```

### From shell to isolated_shell_with_temp_dir

Before:
```python
def test_old_file_test(shell):
    # Risky - modifies current directory
    shell.run_command("echo data > test.txt")
```

After:
```python
def test_new_file_test(isolated_shell_with_temp_dir):
    shell = isolated_shell_with_temp_dir
    # Safe - isolated temp directory
    shell.run_command("echo data > test.txt")
```

## Test Markers

Use appropriate markers for special test requirements:

```python
@pytest.mark.serial
def test_needs_serial_execution():
    """Test that can't run in parallel."""
    pass

@pytest.mark.slow
def test_performance():
    """Test that takes more than 1 second."""
    pass
```

## Summary

1. **Choose the right fixture**:
   - `captured_shell` for output testing
   - `isolated_shell_with_temp_dir` for file I/O
   - `subprocess` for external testing

2. **Be consistent**:
   - Always check exit codes
   - Clear output between tests
   - Use appropriate assertions

3. **Avoid conflicts**:
   - Don't mix output capture methods
   - Don't use capsys with I/O redirection
   - Use proper isolation for file operations

Following these patterns will lead to more reliable, maintainable tests that work correctly in parallel execution.