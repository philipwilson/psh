"""Regression tests for reappraisal #16 Tier-2 EXPANSION-OPERATORS cluster.

Pinned to bash 5.2:

1. Colon operators (:-/:+/:=/:?) on the ${a[@]}, ${a[*]}, ${@}, ${*} VIEWS
   test whether the JOINED view is null, NOT the element count.  psh used to
   gate on element count, so ``a=(""); "${a[@]:+X}"`` wrongly yielded X (the
   joined view is null, so bash yields nothing).
2. ${a[i]@A}/${a[i]@a} on a single array element report the whole array's
   NAME and attributes (bash: ``declare -a a='2'`` / ``a``), not the
   subscripted element (psh used to emit ``a[1]='2'`` / '').
3. ${1:=default} / ${@:=default} on unset positional/special parameters
   abort like bash ("cannot assign in this way") instead of silently
   succeeding.
"""


def out(shell):
    return shell.get_stdout()


class TestColonViewJoinedNullness:
    """:-/:+ test joined-nullness on array/positional views (bash)."""

    def test_at_view_plus_single_empty_element_is_null(self, captured_shell):
        # a=("") -> joined "${a[@]}" is '' (null) -> :+ yields nothing.
        captured_shell.run_command('a=(""); echo "[${a[@]:+SET}]"')
        assert out(captured_shell) == "[]\n"

    def test_at_view_minus_single_empty_element_uses_default(self, captured_shell):
        captured_shell.run_command('a=(""); echo "[${a[@]:-D}]"')
        assert out(captured_shell) == "[D]\n"

    def test_at_view_plus_two_empty_elements_not_null(self, captured_shell):
        # a=("" "") -> joined is a single space (non-null) -> :+ yields SET.
        captured_shell.run_command('a=("" ""); echo "[${a[@]:+SET}]"')
        assert out(captured_shell) == "[SET]\n"

    def test_star_view_plus_single_empty_element_is_null(self, captured_shell):
        captured_shell.run_command('a=(""); echo "[${a[*]:+SET}]"')
        assert out(captured_shell) == "[]\n"

    def test_star_view_minus_single_empty_element_uses_default(self, captured_shell):
        captured_shell.run_command('a=(""); echo "[${a[*]:-D}]"')
        assert out(captured_shell) == "[D]\n"

    def test_positional_at_minus_single_empty_uses_default(self, captured_shell):
        captured_shell.run_command('set -- ""; echo "[${@:-D}]"')
        assert out(captured_shell) == "[D]\n"

    def test_positional_at_plus_single_empty_is_null(self, captured_shell):
        captured_shell.run_command('set -- ""; echo "[${@:+S}]"')
        assert out(captured_shell) == "[]\n"

    def test_positional_at_plus_two_empty_not_null(self, captured_shell):
        captured_shell.run_command('set -- "" ""; echo "[${@:+S}]"')
        assert out(captured_shell) == "[S]\n"

    def test_unquoted_at_view_plus_null(self, captured_shell):
        captured_shell.run_command('a=(""); echo [${a[@]:+SET}]')
        assert out(captured_shell) == "[]\n"

    def test_noncolon_plus_still_tests_setness(self, captured_shell):
        # ${a[@]+SET} (no colon) tests set-ness: a set-but-empty element is set.
        captured_shell.run_command('a=(""); echo "[${a[@]+SET}]"')
        assert out(captured_shell) == "[SET]\n"

    def test_noncolon_minus_still_tests_setness(self, captured_shell):
        captured_shell.run_command('a=(""); echo "[${a[@]-D}]"')
        assert out(captured_shell) == "[]\n"

    def test_empty_array_plus_is_null(self, captured_shell):
        captured_shell.run_command('a=(); echo "[${a[@]:+SET}]"')
        assert out(captured_shell) == "[]\n"


class TestViewAssignAndErrorOperators:
    """:=/= and :?/? on views raise bash's errors when null/unset."""

    def test_array_assign_on_null_view_errors(self, captured_shell):
        rc = captured_shell.run_command('a=(""); echo "[${a[@]:=D}]"')
        assert rc == 1
        assert captured_shell.get_stdout() == ""
        assert "a[@]: bad array subscript" in captured_shell.get_stderr()

    def test_star_assign_on_null_view_errors(self, captured_shell):
        rc = captured_shell.run_command('a=(""); echo "[${a[*]:=D}]"')
        assert rc == 1
        assert "a[*]: bad array subscript" in captured_shell.get_stderr()

    def test_array_qmark_on_null_view_errors(self, captured_shell):
        # Fatal expansion error: an embedded/interactive shell discards
        # the line with status 1 (bash -i; 127 is the -c exit status).
        rc = captured_shell.run_command('a=(""); echo "[${a[@]:?boom}]"')
        assert rc == 1
        assert "a[@]: boom" in captured_shell.get_stderr()

    def test_array_assign_on_nonnull_view_keeps_elements(self, captured_shell):
        rc = captured_shell.run_command('a=(x y); echo "[${a[@]:=D}]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "[x y]\n"

    def test_positional_at_assign_on_null_view_errors(self, captured_shell):
        rc = captured_shell.run_command('set -- ""; echo "[${@:=D}]"')
        assert rc == 1
        assert "$@: cannot assign in this way" in captured_shell.get_stderr()


class TestPositionalSpecialAssignRejected:
    """${1:=x} / ${@:=x} / ${*:=x} abort (item 3)."""

    def test_unset_positional_colon_assign(self, captured_shell):
        rc = captured_shell.run_command('echo "[${1:=default}]"')
        assert rc == 1
        assert captured_shell.get_stdout() == ""
        assert "$1: cannot assign in this way" in captured_shell.get_stderr()

    def test_unset_positional_noncolon_assign(self, captured_shell):
        rc = captured_shell.run_command('echo "[${1=default}]"')
        assert rc == 1
        assert "$1: cannot assign in this way" in captured_shell.get_stderr()

    def test_out_of_range_positional_assign(self, captured_shell):
        rc = captured_shell.run_command('set -- a; echo "[${2:=default}]"')
        assert rc == 1
        assert "$2: cannot assign in this way" in captured_shell.get_stderr()

    def test_at_special_assign(self, captured_shell):
        rc = captured_shell.run_command('echo "[${@:=default}]"')
        assert rc == 1
        assert "$@: cannot assign in this way" in captured_shell.get_stderr()

    def test_star_special_assign(self, captured_shell):
        rc = captured_shell.run_command('echo "[${*:=default}]"')
        assert rc == 1
        assert "$*: cannot assign in this way" in captured_shell.get_stderr()

    def test_set_positional_assign_returns_value(self, captured_shell):
        # A set positional never triggers the assign path (bash keeps value).
        rc = captured_shell.run_command('set -- a; echo "[${1:=default}]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "[a]\n"

    def test_count_special_never_triggers(self, captured_shell):
        # ${#} is always set and non-null, so := returns the count (no error).
        rc = captured_shell.run_command('echo "[${#:=default}]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "[0]\n"

    def test_scalar_assign_still_works(self, captured_shell):
        rc = captured_shell.run_command('unset x; echo "[${x:=hi}]"; echo "[$x]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "[hi]\n[hi]\n"

    def test_array_element_assign_still_works(self, captured_shell):
        rc = captured_shell.run_command('a=(); echo "[${a[0]:=z}]"; echo "[${a[0]}]"')
        assert rc == 0
        assert captured_shell.get_stdout() == "[z]\n[z]\n"


class TestSingleElementAttrTransform:
    """${a[i]@A} / ${a[i]@a} strip the subscript (item 2)."""

    def test_indexed_element_at_A(self, captured_shell):
        captured_shell.run_command('a=(1 2 3); echo "${a[1]@A}"')
        assert out(captured_shell) == "declare -a a='2'\n"

    def test_indexed_element_at_a(self, captured_shell):
        captured_shell.run_command('a=(1 2 3); echo "${a[1]@a}"')
        assert out(captured_shell) == "a\n"

    def test_indexed_element_zero_at_A(self, captured_shell):
        captured_shell.run_command('a=(1 2 3); echo "${a[0]@A}"')
        assert out(captured_shell) == "declare -a a='1'\n"

    def test_assoc_element_at_A(self, captured_shell):
        captured_shell.run_command('declare -A m=([k]=v); echo "${m[k]@A}"')
        assert out(captured_shell) == "declare -A m='v'\n"

    def test_assoc_element_at_a(self, captured_shell):
        captured_shell.run_command('declare -A m=([k]=v); echo "${m[k]@a}"')
        assert out(captured_shell) == "A\n"

    def test_whole_array_at_A_unchanged(self, captured_shell):
        captured_shell.run_command('a=(1 2 3); echo "${a[@]@A}"')
        assert out(captured_shell) == 'declare -a a=([0]="1" [1]="2" [2]="3")\n'
