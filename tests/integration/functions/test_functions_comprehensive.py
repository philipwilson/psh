"""
Comprehensive shell function integration tests.

Tests for shell function definition, execution, parameter handling, return values,
scoping, management commands (declare -f, unset -f), and integration with other
shell features like pipelines, aliases, and redirection.
"""



class TestFunctionDefinition:
    """Test function definition syntax and parsing."""

    def test_posix_function_definition(self, shell_with_temp_dir):
        """Test POSIX-style function definition name() { ... }."""
        shell = shell_with_temp_dir

        result = shell.run_command('greet() { echo "Hello, World!"; }')
        assert result == 0

        # Verify function was defined
        assert shell.function_manager.get_function('greet') is not None

    def test_function_keyword_syntax(self, shell_with_temp_dir):
        """Test function keyword syntax."""
        shell = shell_with_temp_dir

        result = shell.run_command('function greet { echo "Hello"; }')
        assert result == 0

        # Verify function was defined
        assert shell.function_manager.get_function('greet') is not None

    def test_function_keyword_with_parentheses(self, shell_with_temp_dir):
        """Test function keyword with parentheses."""
        shell = shell_with_temp_dir

        result = shell.run_command('function greet() { echo "Hello"; }')
        assert result == 0

        # Verify function was defined
        assert shell.function_manager.get_function('greet') is not None

    def test_multiline_function_definition(self, shell_with_temp_dir):
        """Test multiline function definition."""
        shell = shell_with_temp_dir

        script = '''
        greet() {
            echo "Hello"
            echo "World"
        }
        '''
        result = shell.run_command(script)
        assert result == 0

        # Verify function was defined
        assert shell.function_manager.get_function('greet') is not None

    def test_empty_function_definition(self, shell_with_temp_dir):
        """An empty-bodied function uses `:` (bash rejects a literally empty body)."""
        shell = shell_with_temp_dir

        result = shell.run_command('noop() { :; }')
        assert result == 0

        # Verify function was defined
        assert shell.function_manager.get_function('noop') is not None

    def test_literally_empty_function_body_is_syntax_error(self, shell_with_temp_dir):
        """`f() { }` with no command is a syntax error, exactly as in bash."""
        shell = shell_with_temp_dir

        # bash: "syntax error near unexpected token `}'" (exit 2); the body must
        # contain at least one command. PSH parses, so the definition fails and
        # the function is never created.
        result = shell.run_command('noop() { }')
        assert result != 0
        assert shell.function_manager.get_function('noop') is None

    def test_function_with_complex_body(self, shell_with_temp_dir):
        """Test function with complex command structures."""
        shell = shell_with_temp_dir

        script = '''
        complex_func() {
            echo "Starting"
            VAR="test"
            echo "VAR is: $VAR"
        }
        '''
        result = shell.run_command(script)
        assert result == 0

        # Verify function was defined
        assert shell.function_manager.get_function('complex_func') is not None


class TestFunctionExecution:
    """Test function execution and calling."""

    def test_simple_function_call(self, shell, capsys):
        """Test calling a simple function."""
        shell.run_command('greet() { echo "Hello World"; }')
        shell.run_command('greet')

        captured = capsys.readouterr()
        assert captured.out == "Hello World\n"

    def test_function_with_arguments(self, shell, capsys):
        """Test function with positional parameters."""
        shell.run_command('greet() { echo "Hello $1"; }')
        shell.run_command('greet Alice')

        captured = capsys.readouterr()
        assert captured.out == "Hello Alice\n"

    def test_function_multiple_arguments(self, shell, capsys):
        """Test function with multiple arguments."""
        shell.run_command('showargs() { echo "Args: $1 $2 $3"; }')
        shell.run_command('showargs a b c')

        captured = capsys.readouterr()
        assert captured.out == "Args: a b c\n"

    def test_function_special_variables(self, shell, capsys):
        """Test special variables in functions ($#, $@, $*)."""
        shell.run_command('info() { echo "Count: $# All: $@"; }')
        shell.run_command('info one two three')

        captured = capsys.readouterr()
        assert captured.out == 'Count: 3 All: one two three\n'

    def test_function_no_arguments(self, shell, capsys):
        """Test function called with no arguments."""
        shell.run_command('noargs() { echo "No args: $#"; }')
        shell.run_command('noargs')

        captured = capsys.readouterr()
        assert captured.out == "No args: 0\n"


class TestFunctionReturnValues:
    """Test function return values and exit codes."""

    def test_function_return_success(self, shell_with_temp_dir):
        """Test function explicit return with success."""
        shell = shell_with_temp_dir

        shell.run_command('success() { return 0; }')
        result = shell.run_command('success')
        assert result == 0

    def test_function_return_failure(self, shell_with_temp_dir):
        """Test function explicit return with failure."""
        shell = shell_with_temp_dir

        shell.run_command('fail() { return 42; }')
        result = shell.run_command('fail')
        assert result == 42

    def test_function_implicit_return(self, shell_with_temp_dir):
        """Test function implicit return from last command."""
        shell = shell_with_temp_dir

        shell.run_command('test_func() { true; false; }')
        result = shell.run_command('test_func')
        assert result == 1  # false returns 1

    def test_function_empty_body_return(self, shell_with_temp_dir):
        """A no-op function body (`:`) returns 0."""
        shell = shell_with_temp_dir

        shell.run_command('noop() { :; }')
        result = shell.run_command('noop')
        assert result == 0


class TestFunctionScoping:
    """Test function variable scoping and parameter handling."""

    def test_function_modifies_global_variables(self, shell_with_temp_dir):
        """Test that functions can modify global variables."""
        shell = shell_with_temp_dir

        shell.run_command('var=initial')
        shell.run_command('modify() { var=modified; }')
        shell.run_command('modify')
        shell.run_command('echo $var > output.txt')

        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "modified"

    def test_function_parameters_dont_leak(self, shell_with_temp_dir):
        """Test that function parameters don't affect outer scope."""
        shell = shell_with_temp_dir

        shell.run_command('set a b c')  # Set positional params
        shell.run_command('func() { echo "In func: $1" > func_output.txt; }')
        shell.run_command('func xyz')
        shell.run_command('echo "After func: $1" > outer_output.txt')

        with open('func_output.txt', 'r') as f:
            func_content = f.read().strip()
        with open('outer_output.txt', 'r') as f:
            outer_content = f.read().strip()

        assert func_content == "In func: xyz"
        assert outer_content == "After func: a"

    def test_function_accesses_global_variables(self, shell, capsys):
        """Test that functions can access global variables."""
        shell.run_command('GLOBAL_VAR="global_value"')
        shell.run_command('showglobal() { echo "Global: $GLOBAL_VAR"; }')
        shell.run_command('showglobal')

        captured = capsys.readouterr()
        assert captured.out == "Global: global_value\n"

    def test_function_parameter_shadowing(self, shell, capsys):
        """Test function parameters shadow global positional parameters."""
        shell.run_command('set global1 global2')
        shell.run_command('test_shadow() { echo "Param1: $1 Param2: $2"; }')
        shell.run_command('test_shadow func1 func2')

        captured = capsys.readouterr()
        assert captured.out == "Param1: func1 Param2: func2\n"


class TestFunctionNesting:
    """Test function calling other functions."""

    def test_function_calling_function(self, shell, capsys):
        """Test function calling another function."""
        shell.run_command('inner() { echo "Inner function"; }')
        shell.run_command('outer() { echo "Outer function"; inner; }')
        shell.run_command('outer')

        captured = capsys.readouterr()
        assert "Outer function" in captured.out
        assert "Inner function" in captured.out

    def test_function_chain_calls(self, shell, capsys):
        """Test chain of function calls."""
        shell.run_command('func1() { echo "Function 1"; func2; }')
        shell.run_command('func2() { echo "Function 2"; func3; }')
        shell.run_command('func3() { echo "Function 3"; }')
        shell.run_command('func1')

        captured = capsys.readouterr()
        assert "Function 1" in captured.out
        assert "Function 2" in captured.out
        assert "Function 3" in captured.out

    def test_function_vs_builtin(self, shell, capsys):
        """Test function precedence vs builtins."""
        # Define function with builtin name
        shell.run_command('echo() { printf "Function echo: %s\\n" "$@"; }')
        shell.run_command('echo test')

        captured = capsys.readouterr()
        # Should call function, not builtin
        assert "Function echo" in captured.out


class TestFunctionWithRedirection:
    """Test functions with I/O redirection."""

    def test_function_output_redirection(self, temp_dir):
        """Test redirecting function output to file."""
        import os
        import subprocess
        import sys

        # Run PSH as subprocess to avoid pytest stream capture conflicts
        script = '''
greet() { echo "Hello from function"; }
greet > function_output.txt
'''

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        output_path = os.path.join(temp_dir, 'function_output.txt')
        with open(output_path, 'r') as f:
            content = f.read().strip()
        assert content == "Hello from function"

    def test_function_input_redirection(self, temp_dir):
        """Test function with input redirection."""
        import os
        import subprocess
        import sys

        # Create input file
        input_path = os.path.join(temp_dir, 'input.txt')
        with open(input_path, 'w') as f:
            f.write("test input\n")

        # Run PSH as subprocess to avoid pytest stream capture conflicts
        script = '''
read_func() { read line; echo "Read: $line"; }
read_func < input.txt > output.txt
'''

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        output_path = os.path.join(temp_dir, 'output.txt')
        with open(output_path, 'r') as f:
            content = f.read().strip()
        assert content == "Read: test input"

    def test_function_error_redirection(self, temp_dir):
        """Test function with error output redirection."""
        import os
        import subprocess
        import sys

        # Run PSH as subprocess to avoid pytest stream capture conflicts
        script = '''
error_func() { echo "error message" >&2; }
error_func 2> error.txt
'''

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        error_path = os.path.join(temp_dir, 'error.txt')
        with open(error_path, 'r') as f:
            content = f.read().strip()
        assert content == "error message"


class TestFunctionInPipelines:
    """Test functions in pipeline contexts."""

    def test_function_as_pipeline_source(self, shell_with_temp_dir):
        """Test function as source of pipeline."""
        shell = shell_with_temp_dir

        shell.run_command('generate() { echo "line1"; echo "line2"; }')
        shell.run_command('generate | wc -l > output.txt')

        with open('output.txt', 'r') as f:
            content = f.read().strip()
        assert content == "2"

    def test_function_as_pipeline_filter(self):
        """Test function as filter in pipeline.

        Uses subprocess because pytest captures stdin, so `read` inside a
        pipeline function can't read from the pipe in-process.
        """
        import os
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            script = (
                'add_prefix() { while read line; do echo "PREFIX: $line"; done; }\n'
                'echo "test" | add_prefix > output.txt\n'
                'cat output.txt'
            )
            result = subprocess.run(
                [sys.executable, '-m', 'psh', '-c', script],
                cwd=td, capture_output=True, text=True,
                env={**os.environ, 'PYTHONPATH': os.getcwd()},
            )
            assert result.returncode == 0
            assert result.stdout.strip() == "PREFIX: test"

    def test_function_pipeline_chain(self):
        """Test multiple functions in pipeline.

        Uses subprocess because pytest captures stdin, so `read` inside a
        pipeline function can't read from the pipe in-process.
        """
        import os
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            script = (
                'func1() { echo "data"; }\n'
                'func2() { read input; echo "processed: $input"; }\n'
                'func1 | func2 > output.txt\n'
                'cat output.txt'
            )
            result = subprocess.run(
                [sys.executable, '-m', 'psh', '-c', script],
                cwd=td, capture_output=True, text=True,
                env={**os.environ, 'PYTHONPATH': os.getcwd()},
            )
            assert result.returncode == 0
            assert result.stdout.strip() == "processed: data"


class TestFunctionErrorHandling:
    """Test function error conditions and edge cases."""

    def test_invalid_function_name_reserved_word(self, shell_with_temp_dir):
        """Test error on reserved word as function name."""
        shell = shell_with_temp_dir

        result = shell.run_command('function() { echo "test"; }')
        assert result != 0  # Should fail

    def test_function_name_starting_with_number(self, shell_with_temp_dir):
        """bash accepts function names starting with a digit (probe:
        `123func(){ :; }; 123func` runs it, rc=0) — so must psh."""
        shell = shell_with_temp_dir

        result = shell.run_command('123func() { echo "test"; }; 123func')
        assert result == 0

    def test_function_with_syntax_error(self, shell_with_temp_dir):
        """Test function definition with syntax error."""
        shell = shell_with_temp_dir

        # Missing closing brace
        result = shell.run_command('broken() { echo "test"')
        assert result != 0  # Should fail

    def test_calling_undefined_function(self, shell_with_temp_dir):
        """Test calling undefined function."""
        shell = shell_with_temp_dir

        result = shell.run_command('undefined_function')
        assert result == 127  # Command not found


class TestFunctionWithControlStructures:
    """Test functions containing control structures."""

    def test_function_with_if_statement(self, temp_dir):
        """Test function with if statement."""
        import os
        import subprocess
        import sys

        script = '''
test_if() {
    if [ "$1" = "yes" ]; then
        echo "affirmative"
    else
        echo "negative"
    fi
}
test_if yes > output.txt
'''

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        output_path = os.path.join(temp_dir, 'output.txt')
        with open(output_path, 'r') as f:
            content = f.read().strip()
        assert content == "affirmative"

    def test_function_with_for_loop(self, temp_dir):
        """Test function with for loop."""
        import os
        import subprocess
        import sys

        script = '''
list_items() {
    for item in a b c; do
        echo "Item: $item"
    done
}
list_items > output.txt
'''

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        output_path = os.path.join(temp_dir, 'output.txt')
        with open(output_path, 'r') as f:
            content = f.read()
        assert "Item: a" in content
        assert "Item: b" in content
        assert "Item: c" in content

    def test_function_with_while_loop(self, temp_dir):
        """Test function with while loop."""
        import os
        import subprocess
        import sys

        script = '''
count_down() {
    local i=$1
    while [ $i -gt 0 ]; do
        echo "Count: $i"
        i=$((i - 1))
    done
}
count_down 3 > output.txt
'''

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        output_path = os.path.join(temp_dir, 'output.txt')
        with open(output_path, 'r') as f:
            content = f.read()
        assert "Count: 3" in content
        assert "Count: 2" in content
        assert "Count: 1" in content


class TestFunctionPerformance:
    """Test function performance and stress cases."""

    def test_many_function_definitions(self, shell_with_temp_dir):
        """Test defining many functions."""
        shell = shell_with_temp_dir

        # Define 50 functions
        for i in range(50):
            result = shell.run_command(f'func{i}() {{ echo "Function {i}"; }}')
            assert result == 0

        # Verify they all exist
        for i in range(50):
            assert shell.function_manager.get_function(f'func{i}') is not None

    def test_function_with_many_commands(self, tmp_path):
        """Test function with many commands.

        Uses subprocess because function output redirection to a file
        conflicts with pytest's output capture.
        """
        import subprocess
        import sys
        outfile = tmp_path / "output.txt"
        commands = "; ".join(f'echo "Line {i}"' for i in range(20))
        script = (
            f'many_commands() {{ {commands}; }}\n'
            f'many_commands > {outfile}'
        )
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', script],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        content = outfile.read_text()
        assert "Line 0" in content
        assert "Line 19" in content

    def test_function_call_overhead(self, shell_with_temp_dir):
        """Test overhead of function calls."""
        shell = shell_with_temp_dir

        shell.run_command('simple() { echo "simple"; }')

        # Call function multiple times
        for _ in range(10):
            result = shell.run_command('simple > /dev/null')
            assert result == 0
