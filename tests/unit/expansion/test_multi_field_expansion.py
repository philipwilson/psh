"""
Tests for multi-field expansion of quoted @-subscripted expansions.

Regression guards (verified against bash 5.2): only "$@" used to produce
multiple fields inside double quotes — "${arr[@]}", "${@:2}",
"${arr[@]:1:2}", "${arr[@]@Q}" etc. all collapsed into ONE word, silently
corrupting any array element containing whitespace. Also: empty "$@"
produced one empty field instead of zero, and unquoted $@ lost parameter
boundaries under a custom IFS.

All assertions are FIELD-COUNT based (printf '[%s]' / $#) — the assertion
style whose absence let the bug survive.
"""


def out(shell):
    return shell.get_stdout()


class TestQuotedArrayFields:
    def test_quoted_array_at_produces_fields(self, captured_shell):
        captured_shell.run_command('a=(1 "2 3" 4); printf "[%s]" "${a[@]}"')
        assert out(captured_shell) == '[1][2 3][4]'

    def test_set_from_quoted_array_field_count(self, captured_shell):
        captured_shell.run_command('a=(1 "2 3"); set -- "${a[@]}"; echo $#')
        assert out(captured_shell) == '2\n'

    def test_for_loop_over_quoted_array(self, captured_shell):
        captured_shell.run_command(
            'a=(1 "2 3" 4); for x in "${a[@]}"; do echo "<$x>"; done')
        assert out(captured_shell) == '<1>\n<2 3>\n<4>\n'

    def test_assoc_array_fields(self, captured_shell):
        captured_shell.run_command(
            'declare -A m=([k]="v 1" [j]=w); set -- "${m[@]}"; echo $#')
        assert out(captured_shell) == '2\n'

    def test_affix_distribution(self, captured_shell):
        captured_shell.run_command('a=("x y" z); printf "[%s]" pre"${a[@]}"post')
        assert out(captured_shell) == '[prex y][zpost]'

    def test_star_still_joins(self, captured_shell):
        """"${a[*]}" stays one field, IFS-joined."""
        captured_shell.run_command('a=(one two); IFS=:; printf "[%s]" "${a[*]}"')
        assert out(captured_shell) == '[one:two]'


class TestZeroFields:
    def test_empty_at_yields_zero_fields(self, captured_shell):
        captured_shell.run_command('set --; set -- "$@"; echo $#')
        assert out(captured_shell) == '0\n'

    def test_empty_array_yields_zero_fields(self, captured_shell):
        captured_shell.run_command('a=(); set -- "${a[@]}"; echo $#')
        assert out(captured_shell) == '0\n'

    def test_empty_at_with_affix_yields_one_field(self, captured_shell):
        captured_shell.run_command('set --; printf "[%s]" "$@x"')
        assert out(captured_shell) == '[x]'


class TestSlices:
    def test_positional_slice_fields(self, captured_shell):
        captured_shell.run_command('set -- x y z; printf "[%s]" "${@:2}"')
        assert out(captured_shell) == '[y][z]'

    def test_negative_positional_slice(self, captured_shell):
        captured_shell.run_command('set -- a b c; printf "[%s]" "${@: -1}"')
        assert out(captured_shell) == '[c]'

    def test_array_slice_fields(self, captured_shell):
        captured_shell.run_command('a=(1 "2 3" 4); printf "[%s]" "${a[@]:1:2}"')
        assert out(captured_shell) == '[2 3][4]'

    def test_sparse_array_slices_by_index(self, captured_shell):
        """bash slices indexed arrays by INDEX, not element position."""
        captured_shell.run_command('a=(x); a[5]=y; printf "[%s]" "${a[@]:5:1}"')
        assert out(captured_shell) == '[y]'


class TestPerElementOperators:
    def test_prefix_removal_per_element(self, captured_shell):
        captured_shell.run_command('a=(ab cb); printf "[%s]" "${a[@]#a}"')
        assert out(captured_shell) == '[b][cb]'

    def test_substitution_per_element(self, captured_shell):
        captured_shell.run_command('a=(ab cb); printf "[%s]" "${a[@]/b/X}"')
        assert out(captured_shell) == '[aX][cX]'

    def test_case_op_per_element(self, captured_shell):
        captured_shell.run_command('a=(ab cb); printf "[%s]" "${a[@]^^}"')
        assert out(captured_shell) == '[AB][CB]'

    def test_quote_transform_per_element(self, captured_shell):
        captured_shell.run_command('a=(ab "c d"); printf "[%s]" "${a[@]@Q}"')
        assert out(captured_shell) == "['ab']['c d']"

    def test_default_when_empty(self, captured_shell):
        captured_shell.run_command('a=(); printf "[%s]" "${a[@]:-def}"')
        assert out(captured_shell) == '[def]'

    def test_default_skipped_when_nonempty(self, captured_shell):
        captured_shell.run_command('a=("x y"); printf "[%s]" "${a[@]:-def}"')
        assert out(captured_shell) == '[x y]'

    def test_array_length_still_scalar(self, captured_shell):
        captured_shell.run_command('a=(1 2 3); printf "[%s]" "${#a[@]}"')
        assert out(captured_shell) == '[3]'


class TestUnquotedBoundaries:
    def test_unquoted_at_keeps_param_boundaries_with_custom_ifs(self, captured_shell):
        """Regression: $@ was joined with spaces then re-split on IFS."""
        captured_shell.run_command('set -- "a b" c; IFS=:; printf "[%s]" $@')
        assert out(captured_shell) == '[a b][c]'

    def test_unquoted_array_keeps_element_boundaries_with_custom_ifs(self, captured_shell):
        captured_shell.run_command('a=("a b" c); IFS=:; printf "[%s]" ${a[@]}')
        assert out(captured_shell) == '[a b][c]'

    def test_unquoted_at_default_ifs_splits_within_params(self, captured_shell):
        captured_shell.run_command('set -- "a b" c; printf "[%s]" $@')
        assert out(captured_shell) == '[a][b][c]'
