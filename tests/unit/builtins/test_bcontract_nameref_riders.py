"""Nameref array-element riders (builtins contracts cluster, item 5).

Two pre-existing nameref defects surfaced by the varstore verification:
  (a) arithmetic on an ASSOC key THROUGH a nameref wrote element [0] instead
      of the named key: `declare -n r=h; (( r[foo] += 5 ))` set h[0], not
      h[foo].
  (b) `unset "r[1]"` through a nameref refused ("not an array variable")
      instead of unsetting the target's element.

Pinned to bash 5.2.26. Uses captured_shell (pure variable-store operations).
"""


class TestNamerefArithAssocKey:
    def test_compound_assign_writes_named_key(self, captured_shell):
        captured_shell.run_command(
            'declare -A h; declare -n r=h; r[foo]=0; (( r[foo] += 5 )); '
            'echo "foo=${h[foo]} zero=${h[0]-unset}"')
        assert captured_shell.get_stdout() == "foo=5 zero=unset\n"

    def test_compound_assign_reads_named_key(self, captured_shell):
        captured_shell.run_command(
            'declare -A h; h[k]=10; declare -n r=h; (( r[k] += 7 )); '
            'echo "k=${h[k]} zero=${h[0]-unset}"')
        assert captured_shell.get_stdout() == "k=17 zero=unset\n"

    def test_plain_assign_named_key(self, captured_shell):
        captured_shell.run_command(
            'declare -A h; declare -n r=h; (( r[key] = 3 )); '
            'echo "key=${h[key]} zero=${h[0]-unset}"')
        assert captured_shell.get_stdout() == "key=3 zero=unset\n"

    def test_indexed_nameref_still_arithmetic(self, captured_shell):
        """An indexed-array nameref keeps arithmetic subscripts (regression)."""
        captured_shell.run_command(
            'a=(0 0 0); declare -n r=a; (( r[1+1] = 9 )); echo "${a[2]}"')
        assert captured_shell.get_stdout() == "9\n"


class TestNamerefUnsetElement:
    def test_unset_indexed_element_via_nameref(self, captured_shell):
        captured_shell.run_command(
            'a=(x y z); declare -n r=a; unset "r[1]"; '
            'echo "${a[@]}" "keys=${!a[*]}"')
        assert captured_shell.get_stdout() == "x z keys=0 2\n"

    def test_unset_assoc_element_via_nameref(self, captured_shell):
        captured_shell.run_command(
            'declare -A h; h[k1]=1; h[k2]=2; declare -n r=h; unset "r[k1]"; '
            'echo "k1=${h[k1]-gone} k2=${h[k2]}"')
        assert captured_shell.get_stdout() == "k1=gone k2=2\n"

    def test_direct_unset_element_unchanged(self, captured_shell):
        """Non-nameref element unset still works (regression)."""
        captured_shell.run_command('a=(x y z); unset "a[1]"; echo "${a[@]}"')
        assert captured_shell.get_stdout() == "x z\n"
