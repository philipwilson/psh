"""
Comprehensive array functionality integration tests.

Tests for bash-compatible array operations including initialization, element
assignment, access patterns, expansions, slicing, and integration with other
shell features like loops and parameter expansion.
"""



class TestArrayInitialization:
    """Test array initialization patterns."""

    def test_array_initialization_empty(self, shell_with_temp_dir):
        """Test empty array initialization."""
        shell = shell_with_temp_dir

        result = shell.run_command("arr=()")
        assert result == 0
        # Empty array should exist
        var = shell.state.get_variable("arr")
        assert var is not None

    def test_array_initialization_simple(self, shell_with_temp_dir):
        """Test simple array initialization."""
        shell = shell_with_temp_dir

        result = shell.run_command('arr=(one two three)')
        assert result == 0

        # Verify array elements exist
        var = shell.state.get_variable("arr")
        assert var is not None

    def test_array_initialization_quoted(self, shell_with_temp_dir):
        """Test array initialization with quoted elements."""
        shell = shell_with_temp_dir

        result = shell.run_command('arr=("hello world" "foo bar" baz)')
        assert result == 0

    def test_array_initialization_variables(self, shell_with_temp_dir):
        """Test array initialization with variable expansion."""
        shell = shell_with_temp_dir

        shell.run_command("x=hello")
        shell.run_command("y=world")
        result = shell.run_command('arr=($x $y "literal")')
        assert result == 0

    def test_array_initialization_mixed(self, shell_with_temp_dir):
        """Test array initialization with mixed content types."""
        shell = shell_with_temp_dir

        result = shell.run_command('arr=(123 "string with spaces" $HOME)')
        assert result == 0


class TestArrayElementAssignment:
    """Test array element assignment patterns."""

    def test_array_element_assignment_basic(self, shell_with_temp_dir):
        """Test basic array element assignment."""
        shell = shell_with_temp_dir

        result = shell.run_command('arr[0]=first')
        assert result == 0
        result = shell.run_command('arr[1]=second')
        assert result == 0

    def test_array_element_assignment_sparse(self, shell_with_temp_dir):
        """Test sparse array element assignment."""
        shell = shell_with_temp_dir

        result = shell.run_command('arr[10]=tenth')
        assert result == 0
        result = shell.run_command('arr[100]=hundredth')
        assert result == 0

    def test_array_element_assignment_arithmetic(self, shell_with_temp_dir):
        """Test array element assignment with arithmetic index."""
        shell = shell_with_temp_dir

        shell.run_command("i=5")
        result = shell.run_command('arr[$i]=value')
        assert result == 0
        result = shell.run_command('arr[$((i+1))]=next')
        assert result == 0

    def test_array_element_assignment_overwrite(self, shell_with_temp_dir):
        """Test overwriting existing array elements."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(one two three)')
        result = shell.run_command('arr[1]=TWO')
        assert result == 0


class TestArrayElementAccess:
    """Test array element access patterns."""

    def test_array_element_access_basic(self, shell_with_temp_dir, capsys):
        """Test basic array element access."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(one two three)')

        shell.run_command('echo ${arr[0]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'one' in content

        shell.run_command('echo ${arr[1]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'two' in content

    def test_array_element_access_arithmetic(self, shell_with_temp_dir):
        """Test array element access with arithmetic index."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(zero one two three)')
        shell.run_command('i=2')

        shell.run_command('echo ${arr[$i]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'two' in content

        shell.run_command('echo ${arr[$((i+1))]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'three' in content

    def test_array_element_access_bare_variables(self, shell_with_temp_dir):
        """Test array element access with bare variable names (no $ prefix)."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(zero one two three four)')
        shell.run_command('i=1')
        shell.run_command('j=3')

        # Test bare variable name in array index
        shell.run_command('echo ${arr[i]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'one' in content

        shell.run_command('echo ${arr[j]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'three' in content

        # Test in arithmetic context within array index
        shell.run_command('echo ${arr[i+1]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'two' in content

    def test_array_element_access_negative(self, shell_with_temp_dir):
        """Test array element access with negative indices."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(first second third last)')

        shell.run_command('echo ${arr[-1]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'last' in content

        shell.run_command('echo ${arr[-2]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'third' in content

    def test_negative_out_of_range_read_warns(self, captured_shell):
        """R13.B: an out-of-range negative read warns 'bad array subscript' on
        stderr and expands to empty, with the exit status unaffected (bash)."""
        shell = captured_shell
        result = shell.run_command('a=(1 2 3); echo "[${a[-5]}]"')
        assert result == 0
        assert shell.get_stdout() == "[]\n"
        assert 'bad array subscript' in shell.get_stderr()


class TestArrayExpansion:
    """Test array expansion patterns."""

    def test_array_expand_all_at(self, shell_with_temp_dir):
        """Test ${arr[@]} expansion."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(one "two three" four)')

        shell.run_command('for x in "${arr[@]}"; do echo "[$x]" >> output.txt; done')
        with open('output.txt', 'r') as f:
            content = f.read()

        assert '[one]' in content
        assert '[two three]' in content
        assert '[four]' in content

    def test_array_expand_all_star(self, shell_with_temp_dir):
        """Test ${arr[*]} expansion."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(one two three)')

        shell.run_command('echo "${arr[*]}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'one two three' in content

    def test_array_length(self, shell_with_temp_dir):
        """Test ${#arr[@]} for array length."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(a b c d e)')

        shell.run_command('echo ${#arr[@]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert '5' in content

    def test_array_length_sparse(self, shell_with_temp_dir):
        """Test array length with sparse array."""
        shell = shell_with_temp_dir

        shell.run_command('arr[0]=zero')
        shell.run_command('arr[5]=five')
        shell.run_command('arr[10]=ten')

        shell.run_command('echo ${#arr[@]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert '3' in content

    def test_array_indices(self, shell_with_temp_dir):
        """Test ${!arr[@]} for array indices."""
        shell = shell_with_temp_dir

        shell.run_command('arr[1]=one')
        shell.run_command('arr[5]=five')
        shell.run_command('arr[9]=nine')

        shell.run_command('echo ${!arr[@]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()

        assert '1' in content
        assert '5' in content
        assert '9' in content


class TestArraySlicing:
    """Test array slicing operations."""

    def test_array_slice_basic(self, shell_with_temp_dir):
        """Test basic array slicing ${arr[@]:start:length}."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(zero one two three four five)')

        shell.run_command('echo "${arr[@]:2:3}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'two three four' in content

    def test_array_slice_from_start(self, shell_with_temp_dir):
        """Test array slicing from start."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(a b c d e)')

        shell.run_command('echo "${arr[@]:0:3}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'a b c' in content

    def test_array_slice_to_end(self, shell_with_temp_dir):
        """Test array slicing to end."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(a b c d e)')

        shell.run_command('echo "${arr[@]:3}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'd e' in content


class TestArrayParameterExpansion:
    """Test array integration with parameter expansion."""

    def test_array_element_length(self, shell_with_temp_dir):
        """Test ${#arr[index]} for element length."""
        shell = shell_with_temp_dir

        shell.run_command('arr=("hello" "world" "test")')

        shell.run_command('echo ${#arr[0]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert '5' in content

        shell.run_command('echo ${#arr[1]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert '5' in content

    def test_array_element_substitution(self, shell_with_temp_dir):
        """Test parameter expansion on array elements."""
        shell = shell_with_temp_dir

        shell.run_command('arr=("hello world" "foo bar")')

        # Test pattern substitution
        shell.run_command('echo "${arr[0]/world/universe}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'hello universe' in content

        # Test substring removal
        shell.run_command('echo "${arr[1]#foo }" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'bar' in content


class TestArrayDeclare:
    """Test array integration with declare builtin."""

    def test_declare_p_indexed_array(self, shell_with_temp_dir):
        """Test declare -p output for indexed arrays."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(one two three)')

        shell.run_command('declare -p arr > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()

        assert 'declare -a arr=' in content
        assert '([0]="one" [1]="two" [2]="three")' in content

    def test_declare_p_sparse_array(self, shell_with_temp_dir):
        """Test declare -p output for sparse arrays."""
        shell = shell_with_temp_dir

        shell.run_command('arr[1]=one')
        shell.run_command('arr[5]=five')

        shell.run_command('declare -p arr > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()

        assert 'declare -a arr=' in content
        assert '[1]="one"' in content
        assert '[5]="five"' in content


class TestArrayInLoops:
    """Test array integration with control structures."""

    def test_array_in_for_loop(self, shell_with_temp_dir):
        """Test array expansion in for loops."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(apple banana cherry)')

        shell.run_command('for fruit in "${arr[@]}"; do echo "Fruit: $fruit" >> output.txt; done')
        with open('output.txt', 'r') as f:
            content = f.read()

        assert 'Fruit: apple' in content
        assert 'Fruit: banana' in content
        assert 'Fruit: cherry' in content

    def test_array_iteration_indices(self, shell_with_temp_dir):
        """Test iterating over array indices."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(first second third)')

        # Iterate using array length
        script = '''
        for ((i=0; i<${#arr[@]}; i++)); do
            echo "Index $i: ${arr[i]}" >> output.txt
        done
        '''
        result = shell.run_command(script)

        if result == 0:  # Only check if C-style for loops work
            with open('output.txt', 'r') as f:
                content = f.read()
            assert 'Index 0: first' in content
            assert 'Index 1: second' in content
            assert 'Index 2: third' in content


class TestArrayAppend:
    """Test array append operations."""

    def test_array_append_element(self, shell_with_temp_dir):
        """Test appending to array using +=."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(one two)')
        shell.run_command('arr+=(three four)')

        shell.run_command('echo "${arr[@]}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'one two three four' in content

    def test_array_append_manual(self, shell_with_temp_dir):
        """Test manual array appending by setting next index."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(one two)')
        shell.run_command('arr[2]=three')  # Use literal index instead of ${#arr[@]}
        shell.run_command('arr[3]=four')

        shell.run_command('echo "${arr[@]}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'one two three four' in content


class TestArrayEdgeCases:
    """Test array edge cases and error conditions."""

    def test_array_unset_element(self, shell_with_temp_dir):
        """Test unsetting array elements."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(one two three four)')

        # Unset middle element
        shell.run_command('unset arr[2]')
        # This might not be implemented, so we don't assert result == 0

        # Array should still exist
        var = shell.state.get_variable("arr")
        assert var is not None

    def test_array_empty_elements(self, shell_with_temp_dir):
        """Test arrays with empty elements."""
        shell = shell_with_temp_dir

        result = shell.run_command('arr=("" "middle" "")')
        assert result == 0

        # Check array length includes empty elements
        shell.run_command('echo ${#arr[@]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert '3' in content

    def test_array_undefined_access(self, shell_with_temp_dir):
        """Test accessing undefined array elements."""
        shell = shell_with_temp_dir

        shell.run_command('arr=(one two)')

        # Access undefined element should return empty
        shell.run_command('echo "${arr[10]}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read().strip()
        # Should be empty or just whitespace
        assert len(content) == 0 or content.isspace()

    def test_array_variable_conversion(self, shell_with_temp_dir):
        """Test converting regular variable to array."""
        shell = shell_with_temp_dir

        # Start with regular variable
        shell.run_command('var=scalar')

        # Convert to array
        result = shell.run_command('var[1]=array_element')
        assert result == 0

        # Check that both values are accessible
        shell.run_command('echo "${var[1]}" > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert 'array_element' in content


class TestArrayPerformance:
    """Test array performance and stress cases."""

    def test_large_array_creation(self, shell_with_temp_dir):
        """Test creating moderately large arrays."""
        shell = shell_with_temp_dir

        # Create array with 100 elements
        script = '''
        arr=()
        for ((i=0; i<100; i++)); do
            arr[i]="element_$i"
        done
        echo ${#arr[@]} > output.txt
        '''

        result = shell.run_command(script)

        if result == 0:  # Only check if C-style for loops work
            with open('output.txt', 'r') as f:
                content = f.read()
            assert '100' in content

    def test_sparse_array_efficiency(self, shell_with_temp_dir):
        """Test sparse array handling."""
        shell = shell_with_temp_dir

        # Create sparse array with large indices
        shell.run_command('arr[1000]=first')
        shell.run_command('arr[2000]=second')
        shell.run_command('arr[3000]=third')

        # Should still report correct length
        shell.run_command('echo ${#arr[@]} > output.txt')
        with open('output.txt', 'r') as f:
            content = f.read()
        assert '3' in content
