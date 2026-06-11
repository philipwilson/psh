"""Associative-array keys containing ',' or '^' (bash-pinned).

Regression: ``declare -A a; a[x,y]=hi; echo "${a[x,y]}"`` printed empty
because the case-modification exclusion in the ``${...}`` dispatch
(psh/expansion/variable.py) misrouted any content containing ','/'^' away
from the subscript path, and the case-mod operator scan in
parse_expansion split at a ','/'^' inside the brackets.

All expected values verified against bash.
"""


class TestAssocKeysWithCommaCaret:
    def test_comma_key_expansion(self, captured_shell):
        result = captured_shell.run_command(
            'declare -A a; a[x,y]=hi; echo "${a[x,y]}"')
        assert result == 0
        assert captured_shell.get_stdout() == "hi\n"

    def test_caret_key_expansion(self, captured_shell):
        result = captured_shell.run_command(
            'declare -A a; a[x^y]=hi; echo "${a[x^y]}"')
        assert result == 0
        assert captured_shell.get_stdout() == "hi\n"

    def test_comma_key_length(self, captured_shell):
        captured_shell.run_command('declare -A a; a[x,y]=hi; echo "${#a[x,y]}"')
        assert captured_shell.get_stdout() == "2\n"

    def test_comma_key_unset(self, captured_shell):
        captured_shell.run_command(
            "declare -A a; a[x,y]=hi; unset 'a[x,y]'; echo \"${a[x,y]:-gone}\"")
        assert captured_shell.get_stdout() == "gone\n"

    def test_comma_keys_listed(self, captured_shell):
        captured_shell.run_command(
            'declare -A a; a[x,y]=1; a[p,q]=2; printf "%s\\n" "${!a[@]}"')
        assert sorted(captured_shell.get_stdout().split()) == ['p,q', 'x,y']

    def test_variable_key_with_comma(self, captured_shell):
        captured_shell.run_command(
            'declare -A a; key="x,y"; a[$key]=hi; echo "${a[x,y]}"')
        assert captured_shell.get_stdout() == "hi\n"


class TestCaseModOnSpecialKeys:
    """Case modification applied to elements whose key contains ','/'^'."""

    def test_uppercase_all_on_comma_key(self, captured_shell):
        captured_shell.run_command('declare -A a; a[x,y]=hi; echo "${a[x,y]^^}"')
        assert captured_shell.get_stdout() == "HI\n"

    def test_lowercase_all_on_comma_key(self, captured_shell):
        captured_shell.run_command('declare -A a; a[x,y]=HI; echo "${a[x,y],,}"')
        assert captured_shell.get_stdout() == "hi\n"

    def test_uppercase_first_on_comma_key(self, captured_shell):
        captured_shell.run_command(
            'declare -A a; a[x,y]=lower; echo "${a[x,y]^}"')
        assert captured_shell.get_stdout() == "Lower\n"

    def test_lowercase_all_on_caret_key(self, captured_shell):
        captured_shell.run_command('declare -A a; a[x^y]=HI; echo "${a[x^y],,}"')
        assert captured_shell.get_stdout() == "hi\n"


class TestCaseModStillWorks:
    """The subscript fix must not regress scalar case modification."""

    def test_scalar_uppercase(self, captured_shell):
        captured_shell.run_command('v=hello; echo "${v^^}"')
        assert captured_shell.get_stdout() == "HELLO\n"

    def test_scalar_lowercase(self, captured_shell):
        captured_shell.run_command('v=HELLO; echo "${v,,}"')
        assert captured_shell.get_stdout() == "hello\n"

    def test_scalar_uppercase_with_bracket_pattern(self, captured_shell):
        """${v^^[a-m]} ends in ']' but is case-mod, not a subscript."""
        captured_shell.run_command('v=hello; echo "${v^^[a-m]}"')
        assert captured_shell.get_stdout() == "HELLo\n"

    def test_array_element_uppercase(self, captured_shell):
        captured_shell.run_command('arr=(a b c); echo "${arr[1]^^}"')
        assert captured_shell.get_stdout() == "B\n"

    def test_whole_array_uppercase(self, captured_shell):
        captured_shell.run_command('arr=(a b c); echo "${arr[@]^^}"')
        assert captured_shell.get_stdout() == "A B C\n"


class TestIndexedSubscriptArithmetic:
    def test_comma_operator_in_indexed_subscript(self, captured_shell):
        """bash evaluates arr[i,2] as arithmetic: comma yields the last value."""
        captured_shell.run_command('arr=(a b c); i=1; echo "${arr[i,2]}"')
        assert captured_shell.get_stdout() == "c\n"

    def test_nested_subscript_arithmetic(self, captured_shell):
        captured_shell.run_command('arr=(1 0 c); echo "${arr[arr[0]+1]}"')
        assert captured_shell.get_stdout() == "c\n"

    def test_default_operator_with_bracket_operand(self, captured_shell):
        """${a-b[x]} is the '-' default operator, not a subscript of 'a-b'."""
        captured_shell.run_command('unset a; echo "${a-b[x]}"')
        assert captured_shell.get_stdout() == "b[x]\n"
