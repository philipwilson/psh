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


class TestLocalCaseTransformCancellation:
    """`local -ul` / `local -lu`: -u and -l together CANCEL — bash applies
    neither transform and records neither attribute (matches the `declare`
    builtin and the single ScopeManager._apply_attributes chokepoint). The
    duplicate `_apply_attributes` that `local` used to run first uppercased
    `-ul` instead. All expectations verified against bash 5.2.
    """

    def test_ul_leaves_value_unfolded(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -ul x=Hello; echo "$x"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "Hello\n"

    def test_lu_leaves_value_unfolded(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -lu x=Hello; echo "$x"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "Hello\n"

    def test_ul_records_neither_attribute(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -ul x=Hello; declare -p x; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == 'declare -- x="Hello"\n'

    def test_u_alone_still_uppercases(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -u x=Hello; echo "$x"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "HELLO\n"

    def test_l_alone_still_lowercases(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -l x=Hello; echo "$x"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "hello\n"


class TestLocalReadonlyRedeclare:
    """A same-scope `local` redeclare that ASSIGNS A VALUE to an already-
    readonly local is rejected (appraisal H7 — `create_local` used to
    overwrite the readonly cell unguarded). bash prints
    `local: NAME: readonly variable`, keeps the old value, `local` returns 1,
    and the function CONTINUES. An ATTRIBUTE-ONLY redeclare (no value) is
    NOT rejected — bash lets you merge attributes onto a readonly local.
    All expectations verified against bash 5.2.
    """

    def test_value_redeclare_rejected_keeps_old(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -r x=1; local x=2; echo val=$x; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "val=1\n"
        assert "local: x: readonly variable" in captured_shell.get_stderr()

    def test_local_returns_1_on_readonly(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -r x=1; local x=2; echo "rc=$?"; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "rc=1\n"

    def test_function_continues_after_error(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -r x=1; local x=2; echo AFTER; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "AFTER\n"
        assert "readonly variable" in captured_shell.get_stderr()

    def test_r_on_r_rejected(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -r x=1; local -r x=2; echo val=$x; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "val=1\n"
        assert "local: x: readonly variable" in captured_shell.get_stderr()

    def test_append_on_readonly_rejected(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ local -r x=1; local x+=y; echo val=$x; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "val=1\n"
        assert "local: x: readonly variable" in captured_shell.get_stderr()

    def test_attrs_only_redeclare_allowed(self, captured_shell):
        """`local x` (no value) on a readonly local is a no-op, NOT an error
        (bash: prints ``declare -r x="1"``, rc 0)."""
        result = captured_shell.run_command(
            'f(){ local -r x=1; local x; declare -p x; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == 'declare -r x="1"\n'
        assert captured_shell.get_stderr() == ""

    def test_attrs_only_add_integer_allowed(self, captured_shell):
        """Merging an attribute (`-i`) onto a readonly local succeeds — bash
        keeps readonly and adds integer (``declare -ir x="1"``)."""
        result = captured_shell.run_command(
            'f(){ local -r x=1; local -i x; declare -p x; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == 'declare -ir x="1"\n'
        assert captured_shell.get_stderr() == ""

    def test_nonreadonly_redeclare_still_works(self, captured_shell):
        """Control: a NON-readonly local redeclare with a value overwrites."""
        result = captured_shell.run_command(
            'f(){ local x=1; local x=2; echo val=$x; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "val=2\n"
        assert captured_shell.get_stderr() == ""

    def test_not_special_builtin_posix_survives(self, captured_shell):
        """`local` is NOT a POSIX special builtin, so even in posix mode a
        readonly-redeclare failure does NOT exit the shell (v0.673 matrix
        not implicated)."""
        result = captured_shell.run_command(
            'set -o posix; f(){ local -r x=1; local x=2; }; f; echo SURVIVED')
        assert result == 0
        assert captured_shell.get_stdout() == "SURVIVED\n"
        assert "readonly variable" in captured_shell.get_stderr()
