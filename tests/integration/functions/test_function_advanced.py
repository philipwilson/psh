"""
Advanced function integration tests.

Tests advanced function features including function composition,
complex parameter handling, and interaction with other shell features.
"""


def test_function_composition(shell, capsys):
    """Test composing multiple functions together."""
    shell.run_command('double() { echo $(($1 * 2)); }')
    shell.run_command('triple() { echo $(($1 * 3)); }')
    shell.run_command('compose() { triple $(double $1); }')

    result = shell.run_command('compose 5')
    assert result == 0
    captured = capsys.readouterr()
    assert '30' in captured.out  # 5 * 2 * 3 = 30


def test_function_with_command_substitution(shell, capsys):
    """Test function using command substitution."""
    shell.run_command('get_date() { echo "Today is $(date +%Y-%m-%d)"; }')
    result = shell.run_command('get_date')
    assert result == 0
    captured = capsys.readouterr()
    assert 'Today is' in captured.out
def test_function_parameter_expansion(shell, capsys):
    """Test function with parameter expansion."""
    shell.run_command('greet() { echo "Hello ${1:-World}"; }')

    # With parameter
    result = shell.run_command('greet Alice')
    assert result == 0
    captured = capsys.readouterr()
    assert 'Hello Alice' in captured.out

    # Without parameter (should use default)
    result = shell.run_command('greet')
    assert result == 0
    captured = capsys.readouterr()
    assert 'Hello World' in captured.out


def test_function_array_handling(shell, capsys):
    """Test function handling array-like parameters."""
    shell.run_command('show_all() { for arg in "$@"; do echo "Arg: $arg"; done; }')
    result = shell.run_command('show_all one "two three" four')
    assert result == 0
    captured = capsys.readouterr()
    assert 'Arg: one' in captured.out
    assert 'Arg: two three' in captured.out
    assert 'Arg: four' in captured.out


def test_function_with_case_statement(shell, capsys):
    """Test function with case statement."""
    shell.run_command('''classify() {
        case "$1" in
            [0-9]*) echo "Number" ;;
            [a-zA-Z]*) echo "Letter" ;;
            *) echo "Other" ;;
        esac
    }''')

    shell.run_command('classify 123')
    captured = capsys.readouterr()
    assert 'Number' in captured.out

    shell.run_command('classify abc')
    captured = capsys.readouterr()
    assert 'Letter' in captured.out


def test_function_with_while_loop(shell, capsys):
    """Test function with while loop."""
    shell.run_command('''countdown() {
        local count=$1
        while [ $count -gt 0 ]; do
            echo "Count: $count"
            count=$((count - 1))
        done
        echo "Done!"
    }''')
    result = shell.run_command('countdown 3')
    assert result == 0
    captured = capsys.readouterr()
    assert 'Count: 3' in captured.out
    assert 'Count: 2' in captured.out
    assert 'Count: 1' in captured.out
    assert 'Done!' in captured.out


def test_function_with_trap(shell, capsys):
    """Test function with signal traps."""
    shell.run_command('''trapped_func() {
        trap 'echo "Trapped!"; return 1' TERM
        sleep 1
        echo "Normal completion"
    }''')
    result = shell.run_command('trapped_func')
    assert result == 0


def test_function_error_propagation(shell):
    """Test error propagation from functions."""
    shell.run_command('failing_func() { false; }')
    shell.run_command('caller_func() { failing_func && echo "Success" || echo "Failed"; }')

    result = shell.run_command('caller_func')
    assert result == 0  # caller_func itself succeeds


def test_function_with_here_document(isolated_shell_with_temp_dir):
    """Test function with here document.

    The heredoc is fed to external ``cat``, whose output is fd-level and
    invisible to capsys — so redirect to a file and read it back.
    """
    shell = isolated_shell_with_temp_dir
    cmd = 'show_doc() { cat << EOF\nThis is a here document\nin a function with parameter: $1\nEOF\n}'
    result = shell.run_command(cmd)
    assert result == 0

    result = shell.run_command('show_doc test > heredoc_output.txt')
    assert result == 0
    with open('heredoc_output.txt', 'r') as f:
        output = f.read()
    assert 'here document' in output
    assert 'parameter: test' in output


def test_function_variable_assignment(shell, capsys):
    """Test variable assignment within functions."""
    shell.run_command('set_var() { FUNC_VAR="set by function"; }')
    shell.run_command('set_var')
    shell.run_command('echo $FUNC_VAR')
    captured = capsys.readouterr()
    assert 'set by function' in captured.out


def test_function_debug_mode(shell):
    """Test function execution in debug mode."""
    shell.run_command('set -x')
    shell.run_command('debug_func() { echo "debug test"; }')
    result = shell.run_command('debug_func')
    assert result == 0
    shell.run_command('set +x')


def test_function_with_subshell(isolated_shell_with_temp_dir, capsys):
    """Test function execution in subshell."""
    shell = isolated_shell_with_temp_dir
    shell.run_command('VAR=original')
    shell.run_command('modify_var() { VAR=modified; echo "In function: $VAR"; }')

    # Execute in subshell with output redirection to capture properly
    result = shell.run_command('(modify_var) > subshell_output.txt')
    assert result == 0

    # Read the output file
    with open('subshell_output.txt', 'r') as f:
        output = f.read()
    assert 'In function: modified' in output

    # Check original variable is unchanged
    shell.run_command('echo "Outside: $VAR"')
    captured = capsys.readouterr()
    assert 'Outside: original' in captured.out


def test_function_with_background_job(shell):
    """Test function execution as background job."""
    shell.run_command('bg_func() { sleep 1; echo "Background done"; }')
    result = shell.run_command('bg_func &')
    assert result == 0


def test_function_vs_alias(shell, capsys):
    """Test function vs alias precedence."""
    shell.run_command('alias test_cmd="echo alias"')
    shell.run_command('test_cmd() { echo "function"; }')

    result = shell.run_command('test_cmd')
    assert result == 0
    captured = capsys.readouterr()
    # Function should take precedence over alias
    assert 'function' in captured.out


def test_function_with_glob_patterns(shell, capsys):
    """Test function with glob pattern expansion."""
    shell.run_command('show_files() { for file in *.py; do echo "File: $file"; done; }')
    result = shell.run_command('show_files')
    assert result == 0
    # Test should work even if no .py files exist


def test_function_parameter_shift(shell, capsys):
    """Test parameter shifting within functions."""
    shell.run_command('''shift_test() {
        echo "First: $1"
        shift
        echo "After shift: $1"
    }''')
    result = shell.run_command('shift_test one two three')
    assert result == 0
    captured = capsys.readouterr()
    assert 'First: one' in captured.out
    assert 'After shift: two' in captured.out


def test_function_getopts(shell, capsys):
    """Test function using getopts for option parsing."""
    shell.run_command('''parse_opts() {
        while getopts "ab:c" opt; do
            case $opt in
                a) echo "Option a" ;;
                b) echo "Option b: $OPTARG" ;;
                c) echo "Option c" ;;
            esac
        done
    }''')
    result = shell.run_command('parse_opts -a -b value -c')
    assert result == 0


def test_function_exit_vs_return(shell):
    """Test difference between exit and return in functions."""
    shell.run_command('return_func() { return 42; echo "After return"; }')
    result = shell.run_command('return_func')
    assert result == 42

    # exit would terminate the shell, so we can't test it safely
    # shell.run_command('exit_func() { exit 42; echo "After exit"; }')


def test_function_readonly_parameters(shell):
    """Test readonly parameter behavior in functions."""
    shell.run_command('readonly READONLY_VAR=value')
    shell.run_command('modify_readonly() { READONLY_VAR=new_value; }')
    result = shell.run_command('modify_readonly')
    # Should fail to modify readonly variable
    assert result != 0
