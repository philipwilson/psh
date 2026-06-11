"""
Array initialization expansion semantics (bash-verified).

Array initializers ``a=(...)`` must route each element through the same
Word expansion pipeline that command arguments use: quote-aware globbing,
IFS-aware word splitting of unquoted expansions, tilde expansion, and the
noglob/nullglob/dotglob options. Every expectation in this file was
verified against bash 5.2 (see the probe battery referenced in the
2026-06-11 code quality assessment, Concrete Correctness Risk #1).

Glob tests use isolated_shell_with_temp_dir (real chdir into a per-test
dir with known files); pure-logic tests use captured_shell.
"""

import os


def arr_values(shell, name):
    """Return array elements in index order as a list of strings."""
    var_obj = shell.state.scope_manager.get_variable_object(name)
    assert var_obj is not None, f"array {name} not set"
    array = var_obj.value
    return [array.get(i) for i in array.indices()]


def make_files(*names):
    for n in names:
        with open(n, 'w'):
            pass


class TestQuotedGlobsStayLiteral:
    """Quoted glob patterns in initializers must not be expanded."""

    def test_double_quoted_glob_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt', 'b.txt')
        assert shell.run_command('a=("*.txt" lit)') == 0
        assert arr_values(shell, 'a') == ['*.txt', 'lit']

    def test_single_quoted_glob_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt')
        shell.run_command("a=('*.txt')")
        assert arr_values(shell, 'a') == ['*.txt']

    def test_unquoted_glob_expands(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt', 'b.txt')
        shell.run_command('a=(*.txt)')
        assert arr_values(shell, 'a') == ['a.txt', 'b.txt']

    def test_mixed_quoted_and_unquoted_glob(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt', 'b.txt')
        shell.run_command('a=("*.txt" *.txt)')
        assert arr_values(shell, 'a') == ['*.txt', 'a.txt', 'b.txt']

    def test_quoted_variable_with_glob_chars_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt')
        shell.run_command('x="*.txt"; a=("$x")')
        assert arr_values(shell, 'a') == ['*.txt']

    def test_unquoted_variable_with_glob_chars_expands(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt', 'b.txt')
        shell.run_command('x="*.txt"; a=($x)')
        assert arr_values(shell, 'a') == ['a.txt', 'b.txt']

    def test_append_quoted_glob_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt')
        shell.run_command('a=(1); a+=("*.txt")')
        assert arr_values(shell, 'a') == ['1', '*.txt']


class TestGlobOptions:
    """noglob / nullglob / dotglob / no-match behavior in initializers."""

    def test_no_match_stays_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('a=(*.nomatch)')
        assert arr_values(shell, 'a') == ['*.nomatch']

    def test_nullglob_removes_no_match(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        shell.run_command('shopt -s nullglob; a=(*.nomatch x)')
        assert arr_values(shell, 'a') == ['x']

    def test_dotglob_includes_hidden(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt', '.hidden.txt')
        shell.run_command('shopt -s dotglob; a=(*.txt)')
        assert arr_values(shell, 'a') == ['.hidden.txt', 'a.txt']

    def test_noglob_suppresses_globbing(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt', 'b.txt')
        shell.run_command('set -f; a=(*.txt)')
        assert arr_values(shell, 'a') == ['*.txt']

    def test_noglob_suppresses_glob_from_expansion(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt')
        shell.run_command('set -f; x="*.txt"; a=($x)')
        assert arr_values(shell, 'a') == ['*.txt']


class TestIFSSplitting:
    """Unquoted expansions in initializers split on $IFS, not whitespace."""

    def test_custom_ifs_splits_unquoted_var(self, captured_shell):
        captured_shell.run_command('x="a:b:c"; IFS=:; a=($x)')
        assert arr_values(captured_shell, 'a') == ['a', 'b', 'c']

    def test_default_ifs_splits_whitespace(self, captured_shell):
        captured_shell.run_command('x="a b  c"; a=($x)')
        assert arr_values(captured_shell, 'a') == ['a', 'b', 'c']

    def test_quoted_var_not_split(self, captured_shell):
        captured_shell.run_command('x="a b"; a=("$x")')
        assert arr_values(captured_shell, 'a') == ['a b']

    def test_custom_ifs_quoted_element_not_split(self, captured_shell):
        captured_shell.run_command('IFS=:; a=("a:b")')
        assert arr_values(captured_shell, 'a') == ['a:b']

    def test_custom_ifs_then_glob(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt')
        shell.run_command('x="*.txt:b"; IFS=:; a=($x)')
        assert arr_values(shell, 'a') == ['a.txt', 'b']

    def test_assignment_like_element_is_split(self, captured_shell):
        # bash word-splits k=$x inside initializers (no POSIX
        # assignment-word suppression in this context)
        captured_shell.run_command('x="1 2"; a=(k=$x)')
        assert arr_values(captured_shell, 'a') == ['k=1', '2']


class TestEmptyElements:
    """Empty strings and empty expansions."""

    def test_empty_quoted_string_is_element(self, captured_shell):
        captured_shell.run_command('a=("" b)')
        assert arr_values(captured_shell, 'a') == ['', 'b']

    def test_unquoted_empty_var_contributes_nothing(self, captured_shell):
        captured_shell.run_command('x=""; a=($x)')
        assert arr_values(captured_shell, 'a') == []

    def test_quoted_empty_var_is_element(self, captured_shell):
        captured_shell.run_command('x=""; a=("$x" b)')
        assert arr_values(captured_shell, 'a') == ['', 'b']

    def test_unset_var_contributes_nothing(self, captured_shell):
        captured_shell.run_command('unset x; a=($x b)')
        assert arr_values(captured_shell, 'a') == ['b']


class TestArrayAndParamSplicing:
    """Splicing arrays and positional parameters into initializers."""

    def test_quoted_array_at_preserves_elements(self, captured_shell):
        captured_shell.run_command('a=("x y" z); b=("${a[@]}")')
        assert arr_values(captured_shell, 'b') == ['x y', 'z']

    def test_unquoted_array_at_resplits(self, captured_shell):
        captured_shell.run_command('a=("x y" z); b=(${a[@]})')
        assert arr_values(captured_shell, 'b') == ['x', 'y', 'z']

    def test_quoted_at_preserves_params(self, captured_shell):
        captured_shell.run_command('set -- p q; a=("$@")')
        assert arr_values(captured_shell, 'a') == ['p', 'q']

    def test_unquoted_at_resplits_params(self, captured_shell):
        captured_shell.run_command('set -- "p q" r; a=($@)')
        assert arr_values(captured_shell, 'a') == ['p', 'q', 'r']

    def test_quoted_at_with_affixes(self, captured_shell):
        captured_shell.run_command('set -- "p q" r; a=(pre"$@"post)')
        assert arr_values(captured_shell, 'a') == ['prep q', 'rpost']


class TestCommandSubstitution:
    def test_unquoted_command_sub_splits(self, captured_shell):
        captured_shell.run_command('a=($(echo "1 2") 3)')
        assert arr_values(captured_shell, 'a') == ['1', '2', '3']

    def test_quoted_command_sub_single_element(self, captured_shell):
        captured_shell.run_command('a=("$(echo "1 2")")')
        assert arr_values(captured_shell, 'a') == ['1 2']

    def test_backtick_command_sub_splits(self, captured_shell):
        captured_shell.run_command('a=(`echo 1 2`)')
        assert arr_values(captured_shell, 'a') == ['1', '2']


class TestOtherExpansions:
    def test_arithmetic_expansion(self, captured_shell):
        captured_shell.run_command('a=($((1+2)) $((2*3)))')
        assert arr_values(captured_shell, 'a') == ['3', '6']

    def test_tilde_expansion(self, captured_shell):
        captured_shell.run_command('a=(~)')
        assert arr_values(captured_shell, 'a') == [os.path.expanduser('~')]

    def test_quoted_tilde_literal(self, captured_shell):
        captured_shell.run_command('a=("~")')
        assert arr_values(captured_shell, 'a') == ['~']

    def test_non_leading_tilde_literal(self, captured_shell):
        captured_shell.run_command('a=(x~)')
        assert arr_values(captured_shell, 'a') == ['x~']

    def test_brace_expansion_range(self, captured_shell):
        captured_shell.run_command('a=({1..3})')
        assert arr_values(captured_shell, 'a') == ['1', '2', '3']

    def test_brace_expansion_list(self, captured_shell):
        captured_shell.run_command('a=(p{1,2} q)')
        assert arr_values(captured_shell, 'a') == ['p1', 'p2', 'q']

    def test_ansi_c_quoting_single_element(self, captured_shell):
        captured_shell.run_command("a=($'x\\ty')")
        assert arr_values(captured_shell, 'a') == ['x\ty']


class TestCompositeElements:
    """Elements built from adjacent quoted/unquoted/expansion parts."""

    def test_unquoted_var_in_composite_splits(self, captured_shell):
        captured_shell.run_command('x="a b"; a=(pre$x post)')
        assert arr_values(captured_shell, 'a') == ['prea', 'b', 'post']

    def test_quoted_var_in_composite_no_split(self, captured_shell):
        captured_shell.run_command('x="a b"; a=(pre"$x"post)')
        assert arr_values(captured_shell, 'a') == ['prea bpost']

    def test_adjacent_quote_styles(self, captured_shell):
        captured_shell.run_command('a=("a"b\'c\')')
        assert arr_values(captured_shell, 'a') == ['abc']


class TestMultilineAndAppend:
    def test_newlines_inside_initializer(self, captured_shell):
        captured_shell.run_command('a=(1\n2\n3)')
        assert arr_values(captured_shell, 'a') == ['1', '2', '3']

    def test_append_splits_unquoted_var(self, captured_shell):
        captured_shell.run_command('a=(1); x="2 3"; a+=($x)')
        assert arr_values(captured_shell, 'a') == ['1', '2', '3']

    def test_append_preserves_quoted(self, captured_shell):
        captured_shell.run_command('a=(1 2); a+=("3 4")')
        assert arr_values(captured_shell, 'a') == ['1', '2', '3 4']


class TestScalarElementAssignmentContext:
    """a[i]=v is scalar assignment context: NO word splitting, NO globbing."""

    def test_glob_char_value_stays_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('a.txt')
        shell.run_command('b[0]=*.txt')
        assert arr_values(shell, 'b') == ['*.txt']

    def test_star_value_stays_literal(self, captured_shell):
        captured_shell.run_command('a[0]=*')
        assert arr_values(captured_shell, 'a') == ['*']

    def test_var_with_spaces_not_split(self, captured_shell):
        captured_shell.run_command('x="1 2"; a[0]=$x')
        assert arr_values(captured_shell, 'a') == ['1 2']

    def test_custom_ifs_value_not_split(self, captured_shell):
        captured_shell.run_command('IFS=:; x="a:b"; a[0]=$x')
        assert arr_values(captured_shell, 'a') == ['a:b']


class TestDeclareInitializersUnaffected:
    """declare/local array initializers go through the builtin path;
    pin that the executor change does not regress them."""

    def test_declare_assoc_initializer(self, captured_shell):
        captured_shell.run_command('declare -A h=([k]=v); echo "${h[k]}"')
        assert captured_shell.get_stdout() == 'v\n'

    def test_declare_assoc_quoted_value(self, captured_shell):
        captured_shell.run_command(
            'declare -A h=([k]="v 1" [j]=w); echo "${h[k]}|${h[j]}"')
        assert captured_shell.get_stdout() == 'v 1|w\n'

    def test_declare_indexed_initializer(self, captured_shell):
        captured_shell.run_command('declare -a d=(one "two words" three)')
        assert arr_values(captured_shell, 'd') == ['one', 'two words', 'three']

    def test_bare_assoc_explicit_keys(self, captured_shell):
        # h=([k]=v) after declare -A (explicit-assignment path preserved)
        captured_shell.run_command('declare -A h; h=([k]=v); echo "${h[k]}"')
        assert captured_shell.get_stdout() == 'v\n'
