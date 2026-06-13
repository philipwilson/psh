"""
Tests for the `local` builtin's assignment semantics.

Regression guard for a double-expansion injection: `local` used to re-expand
its (already executor-expanded) scalar value, so single-quoted text like
'$(cmd)' executed the command. All expectations verified against bash 5.2.
"""


class TestLocalScalarAssignment:
    def test_single_quoted_command_sub_stays_literal(self, captured_shell):
        """Regression: local must not re-expand a single-quoted '$(cmd)'."""
        result = captured_shell.run_command(
            "f(){ local v='$(echo injected)'; echo \"$v\"; }; f")
        assert result == 0
        assert captured_shell.get_stdout() == "$(echo injected)\n"

    def test_single_quoted_variable_stays_literal(self, captured_shell):
        result = captured_shell.run_command(
            "f(){ local v='$x literal'; echo \"$v\"; }; f")
        assert result == 0
        assert captured_shell.get_stdout() == "$x literal\n"

    def test_double_quoted_command_sub_expands_once(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local v="$(echo ok)"; echo "$v"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "ok\n"

    def test_unquoted_variable_expands(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ x=hi; local v=$x; echo "$v"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "hi\n"

    def test_integer_attribute_still_evaluates(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -i n=2+3; echo $n; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "5\n"

    def test_uppercase_attribute(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -u s=abc; echo $s; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "ABC\n"


class TestLocalArrayAssignment:
    def test_unquoted_variable_element_expands(self, captured_shell):
        """Regression: $x inside arr=(...) used to lose its '$' in the parser."""
        result = captured_shell.run_command(
            'f(){ x=hi; local arr=(one $x); echo "${arr[1]}"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "hi\n"

    def test_braced_variable_element_expands(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ x=hi; local arr=(one ${x}); echo "${arr[1]}"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "hi\n"

    def test_single_quoted_element_stays_literal(self, captured_shell):
        """Regression: '$(cmd)' as an array element must not execute."""
        result = captured_shell.run_command(
            "f(){ local arr=('$(echo bad)'); echo \"${arr[0]}\"; }; f")
        assert result == 0
        assert captured_shell.get_stdout() == "$(echo bad)\n"

    def test_double_quoted_command_sub_element(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local arr=("$(echo sub)" two); echo "${arr[0]}"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "sub\n"

    def test_unquoted_expansion_word_splits(self, captured_shell):
        """bash: arr=($x) with x="a b" yields two elements."""
        result = captured_shell.run_command(
            'f(){ x="a b"; local arr=($x); echo "${#arr[@]}"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "2\n"

    def test_double_quoted_expansion_does_not_split(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ x="a b"; local arr=("$x"); echo "${#arr[@]}"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "1\n"


class TestDeclareArrayAssignment:
    """declare shares the same structured element expansion as the bare
    ``a=(...)`` path (ArrayOperationExecutor.build_indexed_array /
    build_associative_array)."""

    def test_unquoted_variable_element_expands(self, captured_shell):
        result = captured_shell.run_command(
            'x=hi; declare -a arr=(one $x); echo "${arr[1]}"')
        assert result == 0
        assert captured_shell.get_stdout() == "hi\n"

    def test_quoting_rules(self, captured_shell):
        result = captured_shell.run_command(
            'declare -a arr=("two words" \'$lit\'); echo "[${arr[0]}][${arr[1]}]"')
        assert result == 0
        assert captured_shell.get_stdout() == "[two words][$lit]\n"
