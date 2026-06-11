"""
Array element assignment VALUE semantics (bash-verified).

``a[i]=value`` (and the explicit ``[i]=value`` elements of ``a=(...)``
initializers) expand their values with bash assignment-value semantics:

- all expansions are performed (parameter, command, arithmetic),
- NO word splitting and NO pathname expansion of the result,
- unquoted tilde prefixes expand at the start of the value and after
  each ``:`` (``a[0]=a:~:b``), but not mid-text or when quoted,
- quote removal happens via Word-part quote context, not string surgery.

The value travels as a Word AST node (``ArrayElementAssignment.value_word``)
and is expanded by the shared assignment-value policy in
``ExpansionManager.expand_assignment_value_word()`` — the same policy
scalar ``v=...`` assignments use. Every expectation in this file was
verified against bash 5.2 (probe battery, 2026-06 reassessment Finding #4).
"""

import subprocess
import sys


def arr_values(shell, name):
    """Return indexed-array elements in index order as a list of strings."""
    var_obj = shell.state.scope_manager.get_variable_object(name)
    assert var_obj is not None, f"array {name} not set"
    array = var_obj.value
    return [array.get(i) for i in array.indices()]


def arr_get(shell, name, index):
    """Return one element of an indexed or associative array."""
    var_obj = shell.state.scope_manager.get_variable_object(name)
    assert var_obj is not None, f"array {name} not set"
    return var_obj.value.get(index)


def make_files(*names):
    for n in names:
        with open(n, 'w'):
            pass


def run_psh(cmd, parser='rd'):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '--parser', parser, '-c', cmd],
        capture_output=True, text=True, timeout=15)


class TestElementValueNoSplitting:
    """Assignment-value context: expansions are never word-split."""

    def test_plain_literal_value(self, captured_shell):
        """Regression: a[0]=v."""
        assert captured_shell.run_command('a[0]=v') == 0
        assert arr_values(captured_shell, 'a') == ['v']

    def test_variable_value_not_split(self, captured_shell):
        """bash: a[0]=$x with x="a b" -> ONE element "a b"."""
        captured_shell.run_command('x="a b"; a[0]=$x')
        assert arr_values(captured_shell, 'a') == ['a b']

    def test_unquoted_command_sub_not_split(self, captured_shell):
        """bash: a[0]=$(echo p q) -> one element "p q" (no split)."""
        captured_shell.run_command('a[0]=$(echo p q)')
        assert arr_values(captured_shell, 'a') == ['p q']

    def test_quoted_command_sub(self, captured_shell):
        """bash: a[0]="$(echo p q)" -> "p q" (no literal quotes kept)."""
        captured_shell.run_command('a[0]="$(echo p q)"')
        assert arr_values(captured_shell, 'a') == ['p q']

    def test_composite_value_not_split(self, captured_shell):
        """bash: a[0]=pre${x}post -> "prea bpost" as one element."""
        captured_shell.run_command('x="a b"; a[0]=pre${x}post')
        assert arr_values(captured_shell, 'a') == ['prea bpost']

    def test_quoted_unquoted_composite(self, captured_shell):
        """bash: a[0]="pre"$x"post" -> one element."""
        captured_shell.run_command('x="a b"; a[0]="pre"$x"post"')
        assert arr_values(captured_shell, 'a') == ['prea bpost']

    def test_empty_expansion_keeps_element(self, captured_shell):
        """bash: a[0]=$unset -> element exists with empty value."""
        captured_shell.run_command('a[0]=$unset_zz')
        assert arr_values(captured_shell, 'a') == ['']

    def test_arithmetic_expansion_value(self, captured_shell):
        """bash: a[0]=$((2*3)) -> 6."""
        captured_shell.run_command('a[0]=$((2*3))')
        assert arr_values(captured_shell, 'a') == ['6']


class TestElementValueNoGlobbing:
    """Assignment-value context: results are never pathname-expanded."""

    def test_star_stays_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('f1.txt', 'f2.txt')
        shell.run_command('a[0]=*')
        assert arr_values(shell, 'a') == ['*']

    def test_glob_from_expansion_stays_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('g1.txt', 'g2.txt')
        shell.run_command('x="*.txt"; a[0]=$x')
        assert arr_values(shell, 'a') == ['*.txt']

    def test_question_mark_stays_literal(self, captured_shell):
        captured_shell.run_command('a[0]=?')
        assert arr_values(captured_shell, 'a') == ['?']


class TestElementValueTilde:
    """Tilde expansion follows assignment-value rules."""

    def test_bare_tilde_expands(self, captured_shell):
        captured_shell.run_command('a[0]=~')
        home = captured_shell.state.get_variable('HOME')
        assert arr_values(captured_shell, 'a') == [home]

    def test_tilde_slash_expands(self, captured_shell):
        captured_shell.run_command('a[0]=~/sub')
        home = captured_shell.state.get_variable('HOME')
        assert arr_values(captured_shell, 'a') == [home + '/sub']

    def test_tilde_after_colon_expands(self, captured_shell):
        """bash: a[0]=a:~:b expands the middle segment."""
        captured_shell.run_command('a[0]=a:~:b')
        home = captured_shell.state.get_variable('HOME')
        assert arr_values(captured_shell, 'a') == [f'a:{home}:b']

    def test_tilde_mid_text_literal(self, captured_shell):
        """bash: a[0]=x~ keeps the tilde literal."""
        captured_shell.run_command('a[0]=x~')
        assert arr_values(captured_shell, 'a') == ['x~']

    def test_quoted_tilde_literal(self, captured_shell):
        captured_shell.run_command('a[0]="~"')
        assert arr_values(captured_shell, 'a') == ['~']

    def test_tilde_running_into_quoted_text_literal(self, captured_shell):
        """bash: a[0]=~"x" -> literal ~x (prefix runs into quoted text)."""
        captured_shell.run_command('a[0]=~"x"')
        assert arr_values(captured_shell, 'a') == ['~x']


class TestElementValueQuoting:
    """Quote context comes from Word parts, not outer-quote stripping."""

    def test_single_quoted_value_literal(self, captured_shell):
        """bash: a[0]='lit $x' keeps $x literal (no quotes kept)."""
        captured_shell.run_command("x=zz; a[0]='lit $x'")
        assert arr_values(captured_shell, 'a') == ['lit $x']

    def test_double_quoted_value(self, captured_shell):
        captured_shell.run_command('a[0]="dq lit"')
        assert arr_values(captured_shell, 'a') == ['dq lit']

    def test_adjacent_quoted_segments(self, captured_shell):
        """bash: a[0]="x""y" -> xy."""
        captured_shell.run_command('a[0]="x""y"')
        assert arr_values(captured_shell, 'a') == ['xy']

    def test_backslash_escape(self, captured_shell):
        """bash: a[0]=a\\ b -> "a b"."""
        captured_shell.run_command(r'a[0]=a\ b')
        assert arr_values(captured_shell, 'a') == ['a b']

    def test_ansi_c_quoted_value(self, captured_shell):
        """bash: a[0]=$'t\\tb' processes the escape."""
        captured_shell.run_command(r"a[0]=$'t\tb'")
        assert arr_values(captured_shell, 'a') == ['t\tb']


class TestElementAppendAndIndex:
    """+= append and index expansion (index path unchanged)."""

    def test_append_literal(self, captured_shell):
        captured_shell.run_command('a[0]=foo; a[0]+=bar')
        assert arr_values(captured_shell, 'a') == ['foobar']

    def test_append_expansion_not_split(self, captured_shell):
        captured_shell.run_command('x="s x"; a[0]=foo; a[0]+=$x')
        assert arr_values(captured_shell, 'a') == ['foos x']

    def test_append_to_missing_index(self, captured_shell):
        """bash: a[5]+=$x on an unset element just assigns."""
        captured_shell.run_command('x="a b"; a[5]+=$x')
        assert arr_get(captured_shell, 'a', 5) == 'a b'

    def test_arithmetic_index_with_expansion_value(self, captured_shell):
        captured_shell.run_command('x="a b"; a[$((1+1))]=$x')
        assert arr_get(captured_shell, 'a', 2) == 'a b'

    def test_bare_name_index_arithmetic(self, captured_shell):
        """bash: i=1+1; a[i]=v evaluates the index arithmetically."""
        captured_shell.run_command('i=1+1; a[i]=v')
        assert arr_get(captured_shell, 'a', 2) == 'v'

    def test_variable_index(self, captured_shell):
        captured_shell.run_command('x=5; a[$x]=v')
        assert arr_get(captured_shell, 'a', 5) == 'v'


class TestAssociativeElementValues:
    """declare -A element assignments share the same value policy."""

    def test_assoc_value_not_split(self, captured_shell):
        captured_shell.run_command('declare -A h; x="a b"; h[k]=$x')
        assert arr_get(captured_shell, 'h', 'k') == 'a b'

    def test_assoc_comma_key(self, captured_shell):
        """v0.289 regression: comma stays part of the key."""
        captured_shell.run_command('declare -A h; h[x,y]=v')
        assert arr_get(captured_shell, 'h', 'x,y') == 'v'

    def test_assoc_quoted_key(self, captured_shell):
        captured_shell.run_command('declare -A h; h["q k"]=$(echo m n)')
        assert arr_get(captured_shell, 'h', 'q k') == 'm n'


class TestRoundTrips:
    """Read-back and unset round-trips."""

    def test_element_read_back(self, captured_shell):
        captured_shell.run_command('x="a b"; a[0]=$x')
        captured_shell.run_command('echo "${a[0]}"')
        assert captured_shell.get_stdout() == 'a b\n'

    def test_unset_element(self, captured_shell):
        captured_shell.run_command("a[0]=v; unset 'a[0]'")
        captured_shell.run_command('echo "${#a[@]}"')
        assert captured_shell.get_stdout() == '0\n'

    def test_count_after_value_with_spaces(self, captured_shell):
        captured_shell.run_command('a[0]=$(echo p q); echo "${#a[@]}"')
        assert captured_shell.get_stdout() == '1\n'


class TestExplicitInitializerElements:
    """[index]=value elements inside a=(...) use the same value policy."""

    def test_explicit_value_not_split(self, captured_shell):
        captured_shell.run_command('x="a b"; a=([0]=$x)')
        assert arr_values(captured_shell, 'a') == ['a b']

    def test_explicit_glob_stays_literal(self, isolated_shell_with_temp_dir):
        shell = isolated_shell_with_temp_dir
        make_files('e1.txt', 'e2.txt')
        shell.run_command('a=([0]=$x [1]=*)')
        assert arr_get(shell, 'a', 1) == '*'

    def test_explicit_tilde_expands(self, captured_shell):
        """bash: a=([0]=~) expands (assignment-value rules)."""
        captured_shell.run_command('a=([0]=~)')
        home = captured_shell.state.get_variable('HOME')
        assert arr_values(captured_shell, 'a') == [home]

    def test_explicit_tilde_after_colon(self, captured_shell):
        captured_shell.run_command('a=([0]=a:~:b)')
        home = captured_shell.state.get_variable('HOME')
        assert arr_values(captured_shell, 'a') == [f'a:{home}:b']

    def test_out_of_order_explicit_indices(self, captured_shell):
        """bash: a=([2]=two [0]=zero) sets both."""
        captured_shell.run_command('a=([2]=two [0]=zero)')
        assert arr_get(captured_shell, 'a', 0) == 'zero'
        assert arr_get(captured_shell, 'a', 2) == 'two'

    def test_explicit_append_element(self, captured_shell):
        """bash: a=([0]+=x) -> x; a=(z [0]+=x) -> zx."""
        captured_shell.run_command('a=([0]+=x)')
        assert arr_values(captured_shell, 'a') == ['x']
        captured_shell.run_command('b=(z [0]+=x)')
        assert arr_values(captured_shell, 'b') == ['zx']

    def test_quoted_bracket_element_is_literal(self, captured_shell):
        """bash: a=("[0]=x") is a literal element, not an assignment."""
        captured_shell.run_command('a=("[0]=x")')
        assert arr_values(captured_shell, 'a') == ['[0]=x']

    def test_arithmetic_explicit_index(self, captured_shell):
        captured_shell.run_command('a=([1+1]=v)')
        assert arr_get(captured_shell, 'a', 2) == 'v'

    def test_variable_explicit_index(self, captured_shell):
        captured_shell.run_command('i=3; a=([$i]=v)')
        assert arr_get(captured_shell, 'a', 3) == 'v'

    def test_sequential_continues_after_explicit(self, captured_shell):
        """bash: a=([3]=x y z) -> y,z at 4,5."""
        captured_shell.run_command('a=([3]=x y z)')
        assert arr_get(captured_shell, 'a', 4) == 'y'
        assert arr_get(captured_shell, 'a', 5) == 'z'

    def test_command_sub_explicit_value(self, captured_shell):
        """bash: a=([0]=$(echo p q)) -> one element, no split."""
        captured_shell.run_command('a=([0]=$(echo p q))')
        assert arr_values(captured_shell, 'a') == ['p q']


class TestAssociativeInitializer:
    """declare -A variables initialized with h=(...) keep string keys."""

    def test_explicit_keys_and_values(self, captured_shell):
        captured_shell.run_command(
            'x="a b"; declare -A h; h=([k]=$x [k2]="c d")')
        assert arr_get(captured_shell, 'h', 'k') == 'a b'
        assert arr_get(captured_shell, 'h', 'k2') == 'c d'

    def test_keys_listing(self, captured_shell):
        captured_shell.run_command('declare -A h; h=([k]=v)')
        captured_shell.run_command('echo "${!h[@]}"')
        assert captured_shell.get_stdout() == 'k\n'

    def test_append_preserves_existing_keys(self, captured_shell):
        """bash: h=([k]=v); h+=([k2]=w) keeps both."""
        captured_shell.run_command('declare -A h; h=([k]=v); h+=([k2]=w)')
        assert arr_get(captured_shell, 'h', 'k') == 'v'
        assert arr_get(captured_shell, 'h', 'k2') == 'w'

    def test_reinit_replaces(self, captured_shell):
        captured_shell.run_command('declare -A h; h=([k]=v); h=([k2]=w)')
        assert arr_get(captured_shell, 'h', 'k') is None
        assert arr_get(captured_shell, 'h', 'k2') == 'w'

    def test_duplicate_key_last_wins(self, captured_shell):
        """bash: h=([k]=v [k]=w) -> w."""
        captured_shell.run_command('declare -A h; h=([k]=v [k]=w)')
        assert arr_get(captured_shell, 'h', 'k') == 'w'

    def test_expanded_key_with_space(self, captured_shell):
        """bash: h=([$key]=v) with key="x y" -> single key "x y"."""
        captured_shell.run_command('declare -A h; key="x y"; h=([$key]=v)')
        assert arr_get(captured_shell, 'h', 'x y') == 'v'

    def test_quoted_key_with_space(self, captured_shell):
        captured_shell.run_command('declare -A h; h=(["q k"]=v)')
        assert arr_get(captured_shell, 'h', 'q k') == 'v'

    def test_paired_list_form(self, captured_shell):
        """bash 5.2: h=(a b) -> h[a]=b."""
        captured_shell.run_command('declare -A h; h=(a b)')
        assert arr_get(captured_shell, 'h', 'a') == 'b'

    def test_paired_list_odd_trailing_key(self, captured_shell):
        """bash 5.2: h=(a b c) -> h[a]=b, h[c]=""."""
        captured_shell.run_command('declare -A h; h=(a b c)')
        assert arr_get(captured_shell, 'h', 'a') == 'b'
        assert arr_get(captured_shell, 'h', 'c') == ''

    def test_paired_field_not_split(self, captured_shell):
        """bash 5.2: h=($x) with x="k v" -> single key "k v" (no split)."""
        captured_shell.run_command('declare -A h; x="k v"; h=($x)')
        assert arr_get(captured_shell, 'h', 'k v') == ''


class TestSharedScalarPolicy:
    """Scalar assignments share the same value policy (regression net)."""

    def test_scalar_backslash_escape(self, captured_shell):
        """bash: v=a\\ b -> "a b" (shared escape processing)."""
        captured_shell.run_command(r'v=a\ b; echo "$v"')
        assert captured_shell.get_stdout() == 'a b\n'

    def test_scalar_value_not_split(self, captured_shell):
        captured_shell.run_command('x="a b"; v=$x; echo "$v"')
        assert captured_shell.get_stdout() == 'a b\n'

    def test_scalar_tilde_after_colon(self, captured_shell):
        captured_shell.run_command('P=a:~:b; echo "$P"')
        home = captured_shell.state.get_variable('HOME')
        assert captured_shell.get_stdout() == f'a:{home}:b\n'


class TestCombinatorParser:
    """The combinator parser populates value_word too (subprocess)."""

    def test_combinator_value_not_split(self):
        r = run_psh('x="a b"; a[0]=$x; echo "${#a[@]}:${a[0]}"',
                    parser='combinator')
        assert r.returncode == 0, r.stderr
        assert r.stdout == '1:a b\n'

    def test_combinator_tilde_value(self):
        r = run_psh('a[0]=~/sub; echo "${a[0]}"', parser='combinator')
        assert r.returncode == 0, r.stderr
        assert r.stdout.endswith('/sub\n') and not r.stdout.startswith('~')

    def test_combinator_quoted_command_sub(self):
        r = run_psh('a[0]="$(echo p q)"; echo "${a[0]}"',
                    parser='combinator')
        assert r.returncode == 0, r.stderr
        assert r.stdout == 'p q\n'
