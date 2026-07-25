"""
Basic subshell integration tests.

Tests for subshell group (...) syntax support including variable isolation,
command execution, redirections, and proper process management.
"""

import io
import os
import subprocess
import sys

import pytest


def test_subshell_basic_execution(isolated_shell_with_temp_dir):
    """Test basic subshell command execution."""
    shell = isolated_shell_with_temp_dir

    # Test basic subshell execution with output redirection
    result = shell.run_command('(echo "hello from subshell") > subshell_output.txt')
    assert result == 0

    # Verify output
    with open('subshell_output.txt', 'r') as f:
        content = f.read()
    assert "hello from subshell" in content


def test_subshell_variable_isolation(isolated_shell_with_temp_dir):
    """Test that variables set in subshell don't affect parent."""
    shell = isolated_shell_with_temp_dir

    # Set a variable in parent
    shell.run_command('PARENT_VAR=parent_value')

    # Modify variable in subshell and create new one, redirect to file
    result = shell.run_command('(PARENT_VAR=subshell_value; NEW_VAR=new_value; echo "In subshell: $PARENT_VAR $NEW_VAR") > subshell_vars.txt')
    assert result == 0

    # Check parent variables are unchanged
    assert shell.state.get_variable('PARENT_VAR') == 'parent_value'
    assert shell.state.get_variable('NEW_VAR') == ''

    # Verify subshell output
    with open('subshell_vars.txt', 'r') as f:
        output = f.read()
    assert "In subshell: subshell_value new_value" in output


def test_subshell_with_pipelines(isolated_shell_with_temp_dir):
    """Test subshell containing pipelines."""
    shell = isolated_shell_with_temp_dir

    result = shell.run_command('(echo "line1"; echo "line2") | wc -l > line_count.txt')
    assert result == 0

    with open('line_count.txt', 'r') as f:
        count = f.read().strip()
    # Should count 2 lines
    assert '2' in count


def test_subshell_exit_status(shell):
    """Test subshell exit status propagation."""
    # Successful subshell
    result = shell.run_command('(true)')
    assert result == 0

    # Failed subshell
    result = shell.run_command('(false)')
    assert result == 1

    # Subshell with explicit exit
    result = shell.run_command('(exit 42)')
    assert result == 42


def test_subshell_with_conditionals(isolated_shell_with_temp_dir):
    """Test subshell containing conditional statements."""
    shell = isolated_shell_with_temp_dir
    shell.run_command('TEST_VAR=hello')

    result = shell.run_command('(if [ "$TEST_VAR" = "hello" ]; then echo "match"; else echo "no match"; fi) > conditional_output.txt')
    assert result == 0

    with open('conditional_output.txt', 'r') as f:
        output = f.read()
    assert "match" in output


def test_subshell_with_loops(isolated_shell_with_temp_dir):
    """Test subshell containing loops."""
    shell = isolated_shell_with_temp_dir

    result = shell.run_command('(for i in 1 2 3; do echo "Item: $i"; done) > loop_output.txt')
    assert result == 0

    with open('loop_output.txt', 'r') as f:
        output = f.read()
    assert "Item: 1" in output
    assert "Item: 2" in output
    assert "Item: 3" in output


def test_subshell_with_functions(isolated_shell_with_temp_dir):
    """Test function calls within subshells."""
    shell = isolated_shell_with_temp_dir

    # Define function in parent
    shell.run_command('test_func() { echo "Function called with: $1"; }')

    # Call function in subshell
    result = shell.run_command('(test_func "subshell param") > function_output.txt')
    assert result == 0

    with open('function_output.txt', 'r') as f:
        output = f.read()
    assert "Function called with: subshell param" in output


def test_subshell_input_redirection(isolated_shell_with_temp_dir):
    """Test subshell with input redirection."""
    shell = isolated_shell_with_temp_dir

    # Create input file
    with open('input.txt', 'w') as f:
        f.write('line1\nline2\nline3\n')

    # Use subshell with input redirection
    result = shell.run_command('(cat; echo "appended") < input.txt > output.txt')
    assert result == 0

    with open('output.txt', 'r') as f:
        content = f.read()
    assert 'line1' in content
    assert 'line2' in content
    assert 'line3' in content
    assert 'appended' in content


def test_subshell_error_handling(shell):
    """Test error handling in subshells."""
    # Command not found in subshell
    result = shell.run_command('(nonexistent_command)')
    assert result != 0

    # Syntax error in subshell
    result = shell.run_command('(echo "unterminated quote)')
    assert result != 0


def test_nested_subshells(isolated_shell_with_temp_dir):
    """Test nested subshells."""
    shell = isolated_shell_with_temp_dir

    result = shell.run_command('(echo "outer"; (echo "inner")) > nested_output.txt')
    assert result == 0

    with open('nested_output.txt', 'r') as f:
        output = f.read()
    assert "outer" in output
    assert "inner" in output


@pytest.mark.timeout(60)
def test_subshell_with_background_jobs(tmp_path):
    """Test subshell with background job execution.

    Runs psh in a SUBPROCESS: a backgrounded subshell writing through a
    redirect is process-lifecycle behavior, which this project's test
    guidelines put in a subprocess rather than the in-process fixture. The
    in-process fixture additionally cannot observe it — under pytest's fd
    capture the backgrounded subshell's output reaches the captured stream
    instead of the redirect target, leaving the file empty. The shipped shell
    redirects correctly, which is exactly what this test now pins.

    ``wait`` is the deterministic hand-off: the shell's own job API blocks
    until every background job has been reaped, so no sleep is involved and
    the assertions below run on every execution. The marker bounds the wait,
    turning a hung job into a loud failure instead of a stalled suite.

    Regression pin (MEDIUM-13): this test used to read the output file only
    ``if os.path.exists(...)`` after an empty "give it time" comment, so losing
    the race made it pass having asserted nothing about the output.
    """
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c',
         '(echo "background subshell"; echo "done") > bg_output.txt & wait'],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr

    # Unconditional: the file must exist, holding exactly bash's bytes
    # (pinned against bash 5.2 — 'background subshell\ndone\n'), and the
    # redirect must have taken that output OFF stdout.
    out_file = tmp_path / 'bg_output.txt'
    assert out_file.exists()
    assert out_file.read_text() == "background subshell\ndone\n"
    assert result.stdout == ""


@pytest.mark.timeout(60)
def test_background_subshell_redirect_inprocess_characterization(
        isolated_shell_with_temp_dir):
    """CHARACTERIZATION of a known anomaly — asserts what psh does TODAY.

    This is not a statement that the behavior is correct. It pins the
    in-process/under-capture behavior of a backgrounded subshell's redirect
    so the anomaly cannot drift silently in EITHER direction: if it is fixed,
    this test fails and should be deleted; if it worsens, this test fails too.

    The anomaly (campaign LEDGER Part D, owner: successor queue; discharge
    trigger: any slot touching ``psh/executor/subshell.py``
    ``#_execute_background_subshell`` / ``child_policy.run_background_shell_child``):
    a backgrounded subshell shares the parent's PYTHON-level stream objects,
    so when those are not bound to fd 1 — which is exactly the case under
    pytest's fd capture — a dup2-based redirect on fd 1 is bypassed. The file
    is created and left EMPTY while the output reaches the captured stream.

    Not reachable from the CLI, where ``sys.stdout`` is always fd 1: the
    subprocess test above pins the correct behavior. The foreground twin and
    a backgrounded SIMPLE command are both correct under the same capture,
    and that asymmetry is the load-bearing fact for the Part D row.
    """
    shell = isolated_shell_with_temp_dir

    # The anomaly's PRECONDITION, measured rather than assumed: is the shell's
    # Python-level stdout bound to fd 1? Under pytest's fd capture it is not
    # (fileno() reads 6); under `-s` / --all-nocapture it is (fileno() reads
    # 1) and the redirect behaves correctly. Both regimes are asserted, so
    # this test characterizes rather than skipping itself in either one.
    try:
        stdout_is_fd1 = shell.stdout.fileno() == 1
    except io.UnsupportedOperation:
        # `--capture=sys` swaps sys.stdout for an object with NO underlying
        # fd, so the precondition is genuinely UNMEASURABLE rather than false.
        # That is an environment gate — the one legitimate reason to skip —
        # not a supported feature skipping itself.
        pytest.skip("--capture=sys: stdout has no fileno(), so the "
                    "bound-to-fd-1 precondition cannot be measured")

    assert shell.run_command('(echo A; echo B) > anomaly.txt &') == 0
    assert shell.run_command('wait') == 0
    assert os.path.exists('anomaly.txt')

    if stdout_is_fd1:
        # No decoupling -> no anomaly; the redirect lands as it should.
        assert open('anomaly.txt').read() == 'A\nB\n'
    else:
        # THE ANOMALY, as it stands today: file created, left EMPTY, and the
        # output went to the captured stream instead.
        assert open('anomaly.txt').read() == ''

    # The two paths that are NOT affected in EITHER regime, pinned alongside
    # so the asymmetry is visible here and not only in the ledger.
    assert shell.run_command('(echo A; echo B) > fg.txt') == 0
    assert open('fg.txt').read() == 'A\nB\n'

    assert shell.run_command('echo A > bgsimple.txt &') == 0
    assert shell.run_command('wait') == 0
    assert open('bgsimple.txt').read() == 'A\n'


def test_subshell_environment_inheritance(isolated_shell_with_temp_dir):
    """Test that subshell inherits parent environment."""
    shell = isolated_shell_with_temp_dir

    # Set environment variable
    shell.run_command('export INHERITED_VAR=inherited_value')

    # Access in subshell
    result = shell.run_command('(echo "Inherited: $INHERITED_VAR") > inherited_output.txt')
    assert result == 0

    with open('inherited_output.txt', 'r') as f:
        output = f.read()
    assert "Inherited: inherited_value" in output


def test_subshell_current_directory(isolated_shell_with_temp_dir):
    """Test subshell directory isolation."""
    shell = isolated_shell_with_temp_dir
    original_dir = os.getcwd()

    # Create subdirectory
    os.makedirs('subdir', exist_ok=True)

    # Change directory in subshell
    result = shell.run_command('(cd subdir; pwd) > pwd_output.txt')
    assert result == 0

    # Verify we're still in original directory
    assert os.getcwd() == original_dir

    # Verify subshell was in subdirectory
    with open('pwd_output.txt', 'r') as f:
        pwd_output = f.read().strip()
    assert 'subdir' in pwd_output


def test_subshell_complex_redirections(isolated_shell_with_temp_dir):
    """Test complex redirection patterns with subshells."""
    shell = isolated_shell_with_temp_dir

    # Multiple redirections in subshell
    result = shell.run_command('(echo "stdout"; echo "stderr" >&2) > out.txt 2> err.txt')
    assert result == 0

    with open('out.txt', 'r') as f:
        stdout_content = f.read()
    with open('err.txt', 'r') as f:
        stderr_content = f.read()

    assert "stdout" in stdout_content
    assert "stderr" in stderr_content


def test_subshell_process_substitution():
    """Test process substitution with subshells.

    Uses subprocess because process substitution uses file descriptors
    that conflict with pytest's output capture.
    """
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'cat <(echo "from subshell")'],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "from subshell" in result.stdout
