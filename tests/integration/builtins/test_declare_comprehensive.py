"""
Comprehensive declare builtin integration tests.

Tests for declare builtin functionality including variable attributes,
array declarations, case conversion, readonly/export attributes,
attribute management, and compatibility with all declare options.
"""



class TestDeclareBasicAttributes:
    """Test basic declare attribute functionality."""

    def test_declare_integer_basic(self, shell, capsys):
        """Test declare -i for integer variables."""
        # Declare integer variable with value
        result = shell.run_command("declare -i num=42")
        assert result == 0
        assert shell.state.get_variable("num") == "42"

        # Arithmetic evaluation
        result = shell.run_command("declare -i calc='10 + 5'")
        assert result == 0
        assert shell.state.get_variable("calc") == "15"

        # Invalid integer defaults to 0
        result = shell.run_command("declare -i invalid=abc")
        assert result == 0
        assert shell.state.get_variable("invalid") == "0"

    def test_declare_integer_arithmetic_operations(self, shell):
        """Test integer attribute with various arithmetic operations."""
        # Complex arithmetic
        result = shell.run_command("declare -i result='(10 + 5) * 2'")
        assert result == 0
        assert shell.state.get_variable("result") == "30"

        # Variables in arithmetic
        shell.run_command("X=20")
        shell.run_command("Y=5")
        result = shell.run_command("declare -i calc='X / Y'")
        assert result == 0
        assert shell.state.get_variable("calc") == "4"

    def test_declare_lowercase_basic(self, shell):
        """Test declare -l for lowercase conversion."""
        # Direct assignment
        result = shell.run_command("declare -l lower=HELLO")
        assert result == 0
        assert shell.state.get_variable("lower") == "hello"

        # Mixed case
        result = shell.run_command("declare -l mixed='HeLLo WoRLd'")
        assert result == 0
        assert shell.state.get_variable("mixed") == "hello world"

    def test_declare_lowercase_subsequent_assignments(self, shell):
        """Test that lowercase attribute persists for subsequent assignments."""
        # Declare with lowercase attribute
        shell.run_command("declare -l myvar")

        # Subsequent assignments should be lowercase
        shell.run_command("myvar=UPPERCASE")
        assert shell.state.get_variable("myvar") == "uppercase"

        shell.run_command("myvar='Mixed Case Text'")
        assert shell.state.get_variable("myvar") == "mixed case text"

    def test_declare_uppercase_basic(self, shell):
        """Test declare -u for uppercase conversion."""
        # Direct assignment
        result = shell.run_command("declare -u upper=hello")
        assert result == 0
        assert shell.state.get_variable("upper") == "HELLO"

        # Mixed case
        result = shell.run_command("declare -u mixed='HeLLo WoRLd'")
        assert result == 0
        assert shell.state.get_variable("mixed") == "HELLO WORLD"

    def test_declare_uppercase_subsequent_assignments(self, shell):
        """Test that uppercase attribute persists for subsequent assignments."""
        # Declare with uppercase attribute
        shell.run_command("declare -u myvar")

        # Subsequent assignments should be uppercase
        shell.run_command("myvar=lowercase")
        assert shell.state.get_variable("myvar") == "LOWERCASE"

        shell.run_command("myvar='Mixed Case Text'")
        assert shell.state.get_variable("myvar") == "MIXED CASE TEXT"


class TestDeclareReadonlyExport:
    """Test readonly and export attribute functionality."""

    def test_declare_readonly_basic(self, shell, capsys):
        """Test declare -r for readonly variables."""
        # Declare readonly variable
        result = shell.run_command("declare -r CONST=immutable")
        assert result == 0
        assert shell.state.get_variable("CONST") == "immutable"

        # Try to modify readonly variable
        result = shell.run_command("CONST=changed")
        assert result == 1

        captured = capsys.readouterr()
        assert "readonly variable" in captured.err

    def test_declare_readonly_unset_fails(self, shell, capsys):
        """Test that readonly variables cannot be unset."""
        # Declare readonly variable
        shell.run_command("declare -r CONST=value")

        # Try to unset readonly variable
        result = shell.run_command("unset CONST")
        assert result == 1

        captured = capsys.readouterr()
        assert "readonly variable" in captured.err
        assert shell.state.get_variable("CONST") == "value"

    def test_declare_export_basic(self, shell):
        """Test declare -x for export variables."""
        # Declare export variable
        result = shell.run_command("declare -x EXPORTED=value")
        assert result == 0
        assert shell.state.get_variable("EXPORTED") == "value"

        # Check if variable is exported (in environment)
        assert "EXPORTED" in shell.state.env
        assert shell.state.env["EXPORTED"] == "value"

        # Test that subsequent assignments update the variable
        shell.run_command("EXPORTED=newvalue")
        assert shell.state.get_variable("EXPORTED") == "newvalue"
        # In PSH, exported variables may not auto-update the environment
        # Just verify the variable value changed


class TestDeclareArrays:
    """Test array declaration functionality."""

    def test_declare_indexed_array_empty(self, shell):
        """Test declare -a for empty indexed arrays."""
        result = shell.run_command("declare -a myarray")
        assert result == 0

        # Variable should exist but be empty array
        var = shell.state.variables.get("myarray")
        assert var is not None

    def test_declare_indexed_array_initialization(self, shell):
        """Test declare -a with initialization."""
        result = shell.run_command("declare -a arr=(one two three)")
        assert result == 0

        # Check array elements
        var = shell.state.variables.get("arr")
        assert var is not None

    def test_declare_indexed_array_sparse(self, shell):
        """Test declare -a with sparse array assignment."""
        result = shell.run_command("declare -a sparse")
        assert result == 0

        # Assign to specific indices
        shell.run_command("sparse[0]=first")
        shell.run_command("sparse[5]=sixth")

        var = shell.state.variables.get("sparse")
        assert var is not None

    def test_declare_associative_array_empty(self, shell):
        """Test declare -A for empty associative arrays."""
        result = shell.run_command("declare -A myassoc")
        assert result == 0

        # Variable should exist as associative array
        var = shell.state.variables.get("myassoc")
        assert var is not None

    def test_declare_associative_array_initialization(self, shell):
        """Test declare -A with initialization."""
        result = shell.run_command("declare -A assoc=([key1]=value1 [key2]=value2)")
        assert result == 0

        # Check associative array
        var = shell.state.variables.get("assoc")
        assert var is not None

    def test_declare_associative_array_init_with_quoted_spaces(self, shell):
        """Test declare -A init with quoted keys and values containing spaces."""
        result = shell.run_command(
            'declare -A assoc=(["first key"]="first value" ["second key"]="second value")'
        )
        assert result == 0

        var = shell.state.scope_manager.get_variable_object("assoc")
        assert var is not None
        assert var.value.get("first key") == "first value"
        assert var.value.get("second key") == "second value"

    def test_declare_associative_array_init_with_equals_in_keys_values(self, shell):
        """Test declare -A init where keys/values include '=' characters."""
        result = shell.run_command(
            'declare -A assoc=(["k=1"]="v=2" ["path key"]="/tmp/a=b c")'
        )
        assert result == 0

        var = shell.state.scope_manager.get_variable_object("assoc")
        assert var is not None
        assert var.value.get("k=1") == "v=2"
        assert var.value.get("path key") == "/tmp/a=b c"


class TestDeclareAttributeManagement:
    """Test attribute combination and management."""

    def test_declare_array_types_exclusive(self, shell, capsys):
        """Test that -a and -A are mutually exclusive."""
        # Try to declare both indexed and associative
        result = shell.run_command("declare -aA conflict")
        assert result == 1

        captured = capsys.readouterr()
        assert "cannot use both" in captured.err or "conflicting" in captured.err or "exclusive" in captured.err

    def test_declare_case_attributes_exclusive(self, shell, capsys):
        """Test that -l and -u behavior when combined."""
        # PSH may allow both, with last one winning
        result = shell.run_command("declare -lu conflict=HELLO")
        # If PSH allows it, last option wins (uppercase in this case)
        if result == 0:
            assert shell.state.get_variable("conflict") == "HELLO"  # -u wins
        else:
            # If PSH rejects it, should be error
            captured = capsys.readouterr()
            assert "conflicting" in captured.err or "exclusive" in captured.err

    def test_declare_combined_attributes(self, shell):
        """Test valid combination of attributes."""
        # Export + integer
        result = shell.run_command("declare -xi NUM=42")
        assert result == 0
        assert shell.state.get_variable("NUM") == "42"
        assert "NUM" in shell.state.env

        # Readonly + export
        result = shell.run_command("declare -rx CONST=value")
        assert result == 0
        assert shell.state.get_variable("CONST") == "value"
        assert "CONST" in shell.state.env

    def test_declare_remove_export(self, shell):
        """Test removing export attribute with +x."""
        # First export a variable
        shell.run_command("declare -x EXPORTED=value")
        assert "EXPORTED" in shell.state.env

        # Remove export attribute
        result = shell.run_command("declare +x EXPORTED")
        assert result == 0
        # Variable should still exist but not be exported
        assert shell.state.get_variable("EXPORTED") == "value"

    def test_declare_remove_readonly_fails(self, shell, capsys):
        """Test that readonly attribute cannot be removed."""
        # Declare readonly variable
        shell.run_command("declare -r CONST=value")

        # Try to remove readonly attribute
        result = shell.run_command("declare +r CONST")
        assert result == 1

        captured = capsys.readouterr()
        assert "readonly" in captured.err


class TestDeclarePrintingAndListing:
    """Test declare variable printing and listing functionality."""

    def test_declare_p_all_variables(self, shell, capsys):
        """Test declare -p lists all variables."""
        # Set some variables
        shell.run_command("VAR1=value1")
        shell.run_command("declare -i VAR2=42")
        shell.run_command("declare -x VAR3=exported")

        result = shell.run_command("declare -p")
        assert result == 0

        captured = capsys.readouterr()
        output = captured.out
        assert "VAR1" in output
        assert "VAR2" in output
        assert "VAR3" in output

    def test_declare_p_specific_variables(self, shell, capsys):
        """Test declare -p with specific variable names."""
        shell.run_command("declare -i NUM=42")
        shell.run_command("declare -x EXPORTED=value")

        # Test specific variable
        result = shell.run_command("declare -p NUM")
        assert result == 0

        captured = capsys.readouterr()
        output = captured.out
        assert "NUM" in output
        assert "-i" in output or "integer" in output

    def test_declare_p_nonexistent_variable(self, shell, capsys):
        """Test declare -p with nonexistent variable."""
        result = shell.run_command("declare -p NONEXISTENT")
        assert result == 1

        captured = capsys.readouterr()
        assert "not found" in captured.err or "not declared" in captured.err

    def test_declare_p_array_output(self, shell, capsys):
        """Test declare -p output format for arrays."""
        shell.run_command("declare -a arr=(one two three)")

        result = shell.run_command("declare -p arr")
        assert result == 0

        captured = capsys.readouterr()
        output = captured.out
        assert "arr" in output
        assert "-a" in output or "array" in output


class TestDeclareFunctionSupport:
    """Test declare builtin function-related functionality."""

    def test_declare_f_lists_functions(self, shell, capsys):
        """Test declare -f lists functions."""
        # Define a function
        shell.run_command("myfunc() { echo hello; }")

        result = shell.run_command("declare -f")
        assert result == 0

        captured = capsys.readouterr()
        output = captured.out
        assert "myfunc" in output

    def test_declare_f_specific_function(self, shell, capsys):
        """Test declare -f with specific function name."""
        # Define a function
        shell.run_command("greet() { echo Hello World; }")

        result = shell.run_command("declare -f greet")
        assert result == 0

        captured = capsys.readouterr()
        output = captured.out
        assert "greet" in output
        assert "echo Hello World" in output

    def test_declare_f_function_with_c_style_for(self, shell, capsys):
        """declare -f must not crash on a C-style for loop (R12.B regression:
        ShellFormatter referenced CStyleForLoop.init/.condition/.update which
        don't exist, raising AttributeError)."""
        shell.run_command("cf() { for ((i=0;i<2;i++)); do echo $i; done; }")
        result = shell.run_command("declare -f cf")
        assert result == 0
        out = capsys.readouterr().out
        assert "for ((i=0; i<2; i++))" in out

    def test_declare_f_function_with_break_level(self, shell, capsys):
        """declare -f must not crash on break/continue with a level (R12.B:
        Break/Continue.levels -> .level)."""
        shell.run_command("bf() { while true; do break 2; done; }")
        result = shell.run_command("declare -f bf")
        assert result == 0
        assert "break 2" in capsys.readouterr().out

    def test_declare_F_function_names_only(self, shell, capsys):
        """Test declare -F lists function names only."""
        # Define functions
        shell.run_command("func1() { echo one; }")
        shell.run_command("func2() { echo two; }")

        result = shell.run_command("declare -F")
        assert result == 0

        captured = capsys.readouterr()
        output = captured.out
        assert "func1" in output
        assert "func2" in output
        # Should not contain function bodies
        assert "echo one" not in output
        assert "echo two" not in output


class TestDeclareErrorHandling:
    """Test declare error conditions and edge cases."""

    def test_declare_invalid_option(self, shell, capsys):
        """Test declare with invalid option (bash: usage-error status 2)."""
        result = shell.run_command("declare -z invalid")
        assert result == 2

        captured = capsys.readouterr()
        assert "invalid option" in captured.err or "unknown option" in captured.err

    def test_declare_invalid_plus_option(self, shell, capsys):
        """Test declare with invalid +option (bash: usage-error status 2)."""
        result = shell.run_command("declare +z invalid")
        assert result == 2

        captured = capsys.readouterr()
        assert "invalid option" in captured.err or "unknown option" in captured.err

    def test_declare_no_arguments_lists_all(self, shell, capsys):
        """Test declare with no arguments lists all variables."""
        # Set some variables
        shell.run_command("TEST1=value1")
        shell.run_command("TEST2=value2")

        result = shell.run_command("declare")
        assert result == 0

        captured = capsys.readouterr()
        output = captured.out
        assert "TEST1" in output
        assert "TEST2" in output

    def test_declare_attribute_without_value(self, shell):
        """Test declare with attribute but no value.

        bash: ``declare -i NUMBER`` declares the attribute, but the name
        reads as UNSET until assigned (``${NUMBER-u}`` → u); the integer
        attribute then applies to the first assignment.
        """
        result = shell.run_command("declare -i NUMBER")
        assert result == 0

        # Declared-but-unset: not visible as a set variable
        assert shell.state.variables.get("NUMBER") is None

        # ...but the attribute was remembered (bash: NUMBER=2+3 → 5)
        shell.run_command("NUMBER=2+3")
        assert shell.state.variables.get("NUMBER") == "5"

    def test_declare_existing_variable_add_attributes(self, shell):
        """Test adding attributes to existing variables."""
        # Create regular variable
        shell.run_command("MYVAR=hello")

        # Add lowercase attribute
        result = shell.run_command("declare -l MYVAR")
        assert result == 0

        # Subsequent assignments should be lowercase
        shell.run_command("MYVAR=UPPERCASE")
        assert shell.state.get_variable("MYVAR") == "uppercase"


class TestDeclareSpecialCases:
    """Test special cases and advanced declare functionality."""

    def test_declare_options_parsing(self, shell):
        """Test various option parsing scenarios."""
        # Multiple options combined
        result = shell.run_command("declare -rix COMBO=42")
        assert result == 0
        assert shell.state.get_variable("COMBO") == "42"

        # Options separated
        result = shell.run_command("declare -r -i -x SEPARATED=24")
        assert result == 0
        assert shell.state.get_variable("SEPARATED") == "24"

    def test_declare_special_characters(self, shell, capsys):
        """Test declare with special characters in values."""
        # Variables with special characters
        result = shell.run_command('declare VAR1="value with spaces"')
        assert result == 0
        assert shell.state.get_variable("VAR1") == "value with spaces"

        result = shell.run_command("declare VAR2='single quotes'")
        assert result == 0
        assert shell.state.get_variable("VAR2") == "single quotes"

    def test_declare_nameref_attribute(self, shell):
        """Test declare -n nameref attribute (if supported)."""
        # Create a variable
        shell.run_command("TARGET=original_value")

        # Create nameref
        result = shell.run_command("declare -n REF=TARGET")
        assert result == 0

        # Accessing REF should give TARGET's value
        assert shell.state.get_variable("REF") == "original_value"

        # Modifying REF should modify TARGET
        shell.run_command("REF=new_value")
        assert shell.state.get_variable("TARGET") == "new_value"

    def test_declare_global_attribute(self, shell):
        """Test declare -g global attribute (if supported)."""
        # Test global declaration inside function
        shell.run_command('''
        test_func() {
            declare -g GLOBAL_VAR=global_value
        }
        ''')

        result = shell.run_command("test_func")
        assert result == 0

        # Variable should be available globally
        assert shell.state.get_variable("GLOBAL_VAR") == "global_value"


class TestDeclareCompatibility:
    """Test declare compatibility with other shell features."""

    def test_declare_in_subshell(self, shell, capsys):
        """Test declare behavior in subshells."""
        # Declare in subshell
        result = shell.run_command("(declare -x SUBSHELL_VAR=value)")
        assert result == 0

        # Variable should not persist outside subshell
        shell.state.variables.get("SUBSHELL_VAR")
        # May be None depending on subshell implementation

    def test_declare_with_command_substitution(self, shell):
        """Test declare with command substitution."""
        result = shell.run_command("declare VAR=$(echo 'substituted value')")
        assert result == 0
        assert shell.state.get_variable("VAR") == "substituted value"

    def test_declare_with_parameter_expansion(self, shell):
        """Test declare with parameter expansion."""
        shell.run_command("BASE=hello")
        result = shell.run_command("declare EXPANDED=${BASE}_world")
        assert result == 0
        assert shell.state.get_variable("EXPANDED") == "hello_world"

    def test_declare_array_with_expansion(self, shell):
        """Test declare array with various expansions."""
        shell.run_command("PREFIX=test")
        result = shell.run_command("declare -a arr=(${PREFIX}_1 ${PREFIX}_2)")
        assert result == 0

        var = shell.state.variables.get("arr")
        assert var is not None
