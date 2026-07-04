"""Scalar assignment onto an existing array, and the associative-array
attribute invariant (reappraisal #18 Tier-1, T1-3).

A plain scalar assigned to a variable that is already an array assigns
element 0 (key "0" for associative) and PRESERVES the array container —
``a=(1 2 3); a=x`` yields ``a[0]=x`` with ``a`` still an array; only a
compound ``a=(...)`` replaces the whole array. This also makes a temp-env
prefix (``a=x cmd``) non-destructive, and it must not leave a spurious
``[0]`` on a sparse or associative array. An associative array must never
carry the indexed (-a) attribute. All expectations verified against
bash 5.2.
"""


class TestScalarOverwriteKeepsIndexedArray:
    def test_scalar_sets_element_zero(self, captured_shell):
        result = captured_shell.run_command('a=(1 2 3); a=x; echo "${a[@]}"')
        assert result == 0
        assert captured_shell.get_stdout() == "x 2 3\n"

    def test_scalar_keeps_array_via_declare_p(self, captured_shell):
        result = captured_shell.run_command('a=(1 2 3); a=x; declare -p a')
        assert result == 0
        assert captured_shell.get_stdout() == (
            'declare -a a=([0]="x" [1]="2" [2]="3")\n')

    def test_declare_scalar_onto_array(self, captured_shell):
        result = captured_shell.run_command('a=(1 2 3); declare a=x; declare -p a')
        assert result == 0
        assert captured_shell.get_stdout() == (
            'declare -a a=([0]="x" [1]="2" [2]="3")\n')

    def test_read_onto_array(self, captured_shell):
        result = captured_shell.run_command(
            'a=(1 2 3); read a <<<"hello"; declare -p a')
        assert result == 0
        assert captured_shell.get_stdout() == (
            'declare -a a=([0]="hello" [1]="2" [2]="3")\n')

    def test_index_write_after_scalar(self, captured_shell):
        result = captured_shell.run_command('a=(1 2 3); a=x; a[1]=Q; declare -p a')
        assert result == 0
        assert captured_shell.get_stdout() == (
            'declare -a a=([0]="x" [1]="Q" [2]="3")\n')

    def test_scalar_onto_empty_declared_array(self, captured_shell):
        result = captured_shell.run_command('declare -a a; a=x; declare -p a')
        assert result == 0
        assert captured_shell.get_stdout() == 'declare -a a=([0]="x")\n'


class TestScalarOverwriteKeepsAssociativeArray:
    def test_scalar_sets_key_zero(self, captured_shell):
        result = captured_shell.run_command(
            'declare -A m=([k]=v); m=x; echo "${m[0]}|${m[k]}"')
        assert result == 0
        assert captured_shell.get_stdout() == "x|v\n"

    def test_stays_associative(self, captured_shell):
        # -A only, never a stray -a; key "0" added, key "k" preserved.
        result = captured_shell.run_command(
            'declare -A m=([k]=v); m=x; declare -p m')
        assert result == 0
        out = captured_shell.get_stdout()
        assert out.startswith("declare -A m=(")
        assert '[0]="x"' in out and '[k]="v"' in out


class TestTempEnvNonDestructive:
    """A temp-env prefix (``a=x cmd``) is temporary: the array is restored
    intact after the command (bash), with no spurious element 0."""

    def test_dense_indexed_restored(self, captured_shell):
        result = captured_shell.run_command('a=(1 2 3); a=x true; echo "${a[@]}"')
        assert result == 0
        assert captured_shell.get_stdout() == "1 2 3\n"

    def test_dense_indexed_declare_p_restored(self, captured_shell):
        result = captured_shell.run_command('a=(1 2 3); a=x true; declare -p a')
        assert result == 0
        assert captured_shell.get_stdout() == (
            'declare -a a=([0]="1" [1]="2" [2]="3")\n')

    def test_sparse_indexed_no_spurious_zero(self, captured_shell):
        result = captured_shell.run_command(
            'a=([1]=x [2]=y); a=z true; declare -p a')
        assert result == 0
        assert captured_shell.get_stdout() == (
            'declare -a a=([1]="x" [2]="y")\n')

    def test_associative_no_spurious_zero(self, captured_shell):
        result = captured_shell.run_command(
            'declare -A m=([k]=v); m=x true; declare -p m')
        assert result == 0
        assert captured_shell.get_stdout() == 'declare -A m=([k]="v" )\n'


class TestAssociativeAttributeInvariant:
    """An associative array carries ONLY the ASSOC_ARRAY (-A) bit, never the
    indexed ARRAY (-a) bit — otherwise ``declare -p`` printed ``declare -aA``,
    which does not round-trip back into bash or psh."""

    def test_compound_reassign_no_stray_a(self, captured_shell):
        result = captured_shell.run_command(
            'declare -A m=([a]=1); m=([c]=3); declare -p m')
        assert result == 0
        assert captured_shell.get_stdout() == 'declare -A m=([c]="3" )\n'

    def test_declare_p_starts_with_dash_A_only(self, captured_shell):
        result = captured_shell.run_command('declare -A m=([a]=1); declare -p m')
        assert result == 0
        assert captured_shell.get_stdout().startswith("declare -A m=(")
