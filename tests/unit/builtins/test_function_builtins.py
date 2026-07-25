"""
Unit tests for function-related builtins (return, readonly, declare).

Tests cover:
- Return from functions/scripts
- Readonly variable declaration
- Declare variable attributes
"""



class TestReturnBuiltin:
    """Test return builtin functionality."""

    def test_return_from_function(self, shell, capsys):
        """Test return from function with exit code."""
        cmd = '''
        testfunc() {
            echo "in function"
            return 42
            echo "should not print"
        }
        testfunc
        echo "exit code: $?"
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "in function" in captured.out
        assert "should not print" not in captured.out
        assert "exit code: 42" in captured.out

    def test_return_no_args(self, shell, capsys):
        """Test return with no arguments (returns last exit code)."""
        cmd = '''
        testfunc() {
            false  # Sets $? to 1
            return
        }
        testfunc
        echo "exit code: $?"
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "exit code: 1" in captured.out

    def test_return_outside_function(self, shell, capsys):
        """Test return outside of function.

        Pinned against bash 5.2, which rejects this with rc 2 and the message
        below. The checks used to hang off `if exit_code != 0:`, so a psh that
        silently ACCEPTED `return 5` outside a function passed.

        The assertion is a SUBSTRING on purpose. A three-channel re-probe
        (stdout / stderr / rc compared separately) shows stdout and rc are
        byte-identical to bash and the message TEXT is too, but the
        shell-name prefix is not: bash emits
        "/opt/homebrew/bin/bash: line 1: return: ..." where psh emits
        "psh: line 1: return: ...". That prefix difference belongs to the
        campaign's existing error-wording carry family, not to this test.
        """
        exit_code = shell.run_command('return 5')
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "can only `return' from a function or sourced script" in captured.err

    def test_return_invalid_number(self, shell, capsys):
        """Test return with invalid number."""
        cmd = '''
        testfunc() {
            return abc
        }
        testfunc
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        # Should have an error about numeric argument
        assert 'numeric' in captured.err or 'invalid' in captured.err

    def test_return_range(self, shell, capsys):
        """Test return value range (0-255)."""
        cmd = '''
        testfunc() {
            return 256
        }
        testfunc
        echo "exit code: $?"
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        # 256 should wrap to 0
        assert "exit code: 0" in captured.out

    def test_return_negative(self, shell, capsys):
        """Test return with negative number."""
        cmd = '''
        testfunc() {
            return -1
        }
        testfunc
        echo "exit code: $?"
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        # -1 should become 255
        assert "exit code: 255" in captured.out


class TestReadonlyBuiltin:
    """Test readonly builtin functionality."""

    def test_readonly_variable(self, shell, capsys):
        """Test making a variable readonly."""
        shell.run_command('readonly MYVAR="test"')
        # Try to modify it
        exit_code = shell.run_command('MYVAR="new value"')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'readonly' in captured.err

    def test_readonly_existing_variable(self, shell, capsys):
        """Test making existing variable readonly."""
        shell.run_command('VAR="initial"')
        shell.run_command('readonly VAR')
        # Try to modify
        exit_code = shell.run_command('VAR="changed"')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'readonly' in captured.err

    def test_readonly_list(self, shell, capsys):
        """Test listing readonly variables."""
        shell.run_command('readonly RO1="value1"')
        shell.run_command('readonly RO2="value2"')
        shell.run_command('readonly')
        captured = capsys.readouterr()
        assert 'RO1=' in captured.out
        assert 'RO2=' in captured.out

    def test_readonly_with_p_option(self, shell, capsys):
        """Test readonly -p option."""
        shell.run_command('readonly MYRO="test"')
        shell.run_command('readonly -p')
        captured = capsys.readouterr()
        # Should show in declare -r format
        assert 'readonly' in captured.out or 'declare -r' in captured.out
        assert 'MYRO' in captured.out

    def test_readonly_function(self, shell, capsys):
        """Test readonly -f for functions.

        readonly -f IS supported: the redefinition is refused with rc 1 and a
        'readonly function' diagnostic, and the ORIGINAL body survives. The
        redefinition check used to hang off `if exit_code == 0:`, so a psh
        where `readonly -f` itself failed skipped the real assertion and
        passed.

        stdout and rc are byte-identical to bash 5.2 (three-channel re-probe);
        the stderr PREFIX differs — bash "…/bash: line 1: myfunc: readonly
        function" vs psh "psh: myfunc: readonly function" (psh also omits the
        line marker here) — so the diagnostic is asserted as a substring.
        That prefix/marker difference is the existing error-wording carry
        family, not this test's subject.
        """
        cmd = '''
        myfunc() { echo "test"; }
        readonly -f myfunc
        '''
        assert shell.run_command(cmd) == 0
        capsys.readouterr()

        # Redefinition is refused...
        assert shell.run_command('myfunc() { echo "new"; }') == 1
        assert 'readonly function' in capsys.readouterr().err

        # ...and the original definition is the one that survives.
        assert shell.run_command('myfunc') == 0
        assert capsys.readouterr().out.strip() == 'test'

    def test_readonly_invalid_name(self, shell, capsys):
        """Test readonly with invalid variable name."""
        exit_code = shell.run_command('readonly 123VAR="test"')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'invalid' in captured.err or 'identifier' in captured.err

    def test_readonly_export(self, temp_dir):
        """Test readonly exported variable."""
        import os
        import subprocess
        import sys

        script = '''
export ROVAR="exported"
readonly ROVAR
echo $ROVAR > output.txt
'''

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        output_path = os.path.join(temp_dir, 'output.txt')
        with open(output_path, 'r') as f:
            content = f.read().strip()
        assert content == "exported"


class TestDeclareBuiltin:
    """Test declare builtin functionality."""

    def test_declare_variable(self, shell, capsys):
        """Test basic variable declaration."""
        shell.run_command('declare VAR="value"')
        shell.run_command('echo "$VAR"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "value"

    def test_declare_integer(self, shell, capsys):
        """Test declare -i for integer variables."""
        shell.run_command('declare -i NUM=42')
        shell.run_command('NUM=10+5')
        shell.run_command('echo "$NUM"')
        captured = capsys.readouterr()
        # Should perform arithmetic
        assert captured.out.strip() == "15"

    def test_declare_readonly(self, shell, capsys):
        """Test declare -r for readonly variables."""
        shell.run_command('declare -r CONST="fixed"')
        exit_code = shell.run_command('CONST="changed"')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'readonly' in captured.err

    def test_declare_export(self, temp_dir):
        """Test declare -x for exported variables."""
        import os
        import subprocess
        import sys

        script = '''
declare -x EXPORTED="value"
echo $EXPORTED > output.txt
'''

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        output_path = os.path.join(temp_dir, 'output.txt')
        with open(output_path, 'r') as f:
            content = f.read().strip()
        assert content == "value"

    def test_declare_array(self, shell, capsys):
        """Test declare -a for arrays."""
        shell.run_command('declare -a ARR=(one two three)')
        shell.run_command('echo "${ARR[1]}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "two"

    def test_declare_associative_array(self, shell, capsys):
        """Test declare -A for associative arrays."""
        shell.run_command('declare -A HASH')
        shell.run_command('HASH[key]="value"')
        shell.run_command('echo "${HASH[key]}"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "value"

    def test_declare_list_variables(self, shell, capsys):
        """Test declare without arguments lists variables."""
        shell.run_command('MYVAR="test"')
        shell.run_command('declare')
        captured = capsys.readouterr()
        assert 'MYVAR=' in captured.out

    def test_declare_with_p_option(self, shell, capsys):
        """Test declare -p to display attributes."""
        shell.run_command('declare -i -r CONST=42')
        shell.run_command('declare -p CONST')
        captured = capsys.readouterr()
        # Should show attributes (may be combined)
        assert ('-i' in captured.out or 'i' in captured.out)
        assert ('-r' in captured.out or 'r' in captured.out)
        assert 'CONST' in captured.out

    def test_declare_local_scope(self, shell, capsys):
        """Test declare in function creates local variable."""
        cmd = '''
        VAR="global"
        func() {
            declare VAR="local"
            echo "in func: $VAR"
        }
        func
        echo "outside: $VAR"
        '''
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert "in func: local" in captured.out
        assert "outside: global" in captured.out

    def test_declare_multiple_attributes(self, temp_dir):
        """Test declare with multiple attributes."""
        import os
        import subprocess
        import sys

        script = '''
declare -i -x NUM=100
NUM=50+50
echo $NUM > output.txt
'''

        result = subprocess.run([
            sys.executable, '-m', 'psh', '-c', script
        ], cwd=temp_dir, capture_output=True, text=True,
           env={**os.environ, 'PYTHONPATH': os.getcwd()})

        assert result.returncode == 0

        output_path = os.path.join(temp_dir, 'output.txt')
        with open(output_path, 'r') as f:
            content = f.read().strip()
        assert content == "100"

    def test_declare_invalid_option(self, shell, capsys):
        """Test declare with invalid option."""
        exit_code = shell.run_command('declare -z VAR')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'invalid option' in captured.err or 'unknown option' in captured.err
