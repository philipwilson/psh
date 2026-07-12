"""
Conformance tests for `declare -a`/`-A` type changes preserving content.

Before v0.491 a bare `declare -a`/`-A` installed a fresh EMPTY array, so it
(reappraisal #13 HIGH):
  - discarded an existing scalar's value (`x=foo; declare -a x` -> `()` instead
    of `([0]="foo")`), and
  - WIPED an existing array's elements on re-declaration
    (`a=(1 2 3); declare -a a` -> `()`).

bash's actual rules (verified 5.2):
  - re-declaring an existing array (indexed or associative, local or global)
    keeps its elements;
  - converting a GLOBAL scalar preserves its value at index 0 / key "0";
  - a function-LOCAL scalar is NOT preserved (bash empties it), and a bare
    `declare -a` in a function creates a fresh local that does not pull in an
    outer-scope variable.

Empty-array cases are checked by VALUE (length / element), not `declare -p`,
because rendering a declared-but-never-assigned array (`declare -a a` vs
`declare -a a=()`) is a separate, still-open difference.
"""


from conformance_framework import ConformanceTest


class TestDeclareScalarConversionConformance(ConformanceTest):
    """A global scalar's value survives conversion to an array."""

    def test_scalar_to_indexed(self):
        self.assert_identical_behavior('x=foo; declare -a x; declare -p x')

    def test_scalar_to_assoc(self):
        self.assert_identical_behavior('x=foo; declare -A x; declare -p x')

    def test_empty_scalar_to_indexed(self):
        self.assert_identical_behavior('x=""; declare -a x; declare -p x')

    def test_scalar_with_integer_attr(self):
        self.assert_identical_behavior('x=5; declare -ai x; declare -p x')


class TestDeclareRedeclareKeepsContents(ConformanceTest):
    """Re-declaring an existing array keeps its elements."""

    def test_redeclare_indexed(self):
        self.assert_identical_behavior('a=(1 2 3); declare -a a; declare -p a')

    def test_redeclare_single_key_assoc(self):
        # single key avoids bash-vs-psh associative iteration order
        self.assert_identical_behavior(
            'declare -A m=([x]=1); declare -A m; declare -p m')

    def test_redeclare_then_append(self):
        self.assert_identical_behavior(
            'a=(1 2 3); declare -a a; a+=(4); echo "${a[@]}"')

    def test_redeclare_local_array_in_function(self):
        self.assert_identical_behavior(
            'f(){ local a=(1 2 3); declare -a a; echo "${a[@]}"; }; f')


class TestDeclareLocalScalarNotPreserved(ConformanceTest):
    """In a function, declare creates/empties a local; checked by value."""

    def test_local_scalar_emptied(self):
        self.assert_identical_behavior(
            'f(){ local x=hi; declare -a x; echo "len=${#x[@]} v=[${x[0]}]"; }; f')

    def test_bare_declare_does_not_pull_outer_scalar(self):
        self.assert_identical_behavior(
            'x=hi; f(){ declare -a x; echo "len=${#x[@]} v=[${x[0]}]"; }; f')

    def test_global_scalar_value_via_element(self):
        self.assert_identical_behavior('x=foo; declare -a x; echo "[${x[0]}]"')
