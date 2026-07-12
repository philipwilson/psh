"""Conformance tests: namerefs (``declare -n``) that point at arrays.

A nameref reads/writes through to its target. Scalar nameref reads always
worked, but the array-access paths (``${r[i]}``, ``${r[@]}``, ``${#r[@]}``,
``${!r[@]}``, slicing, and element writes ``r[i]=v``) did not follow the
nameref to its target array name — they accessed a variable literally named
``r``. They now resolve the nameref to its target name at a single point
before every array lookup. These tests pin identical bash behavior.
"""



from conformance_framework import ConformanceTest

_IDX = 'declare -a arr=(10 20 30); declare -n r=arr; '
_ASSOC = 'declare -A m=([k1]=v1 [k2]=v2); declare -n r=m; '


class TestNamerefIndexedArrayReads(ConformanceTest):
    """Indexed-array reads through a nameref match bash."""

    def test_all_elements_at(self):
        self.assert_identical_behavior(_IDX + 'echo "${r[@]}"')

    def test_all_elements_star(self):
        self.assert_identical_behavior(_IDX + 'echo "${r[*]}"')

    def test_single_element(self):
        self.assert_identical_behavior(_IDX + 'echo "${r[1]}"')

    def test_length(self):
        self.assert_identical_behavior(_IDX + 'echo "${#r[@]}"')

    def test_keys(self):
        self.assert_identical_behavior(_IDX + 'echo "${!r[@]}"')

    def test_quoted_iteration(self):
        self.assert_identical_behavior(
            'declare -a arr=(a b c); declare -n r=arr; '
            'for x in "${r[@]}"; do echo "<$x>"; done')

    def test_slice(self):
        self.assert_identical_behavior(
            'declare -a arr=(10 20 30 40); declare -n r=arr; '
            'echo "${r[@]:1:2}"')

    def test_chained_namerefs(self):
        self.assert_identical_behavior(
            'declare -a arr=(x y z); declare -n r1=arr; declare -n r2=r1; '
            'echo "${r2[@]}" "${r2[1]}"')


class TestNamerefAssociativeArrayReads(ConformanceTest):
    """Associative-array reads through a nameref match bash."""

    def test_single_key(self):
        self.assert_identical_behavior(_ASSOC + 'echo "${r[k1]}"')

    def test_all_values(self):
        self.assert_identical_behavior(
            _ASSOC + 'echo "${r[@]}" | tr " " "\\n" | sort | tr "\\n" " "')

    def test_keys(self):
        self.assert_identical_behavior(
            _ASSOC + 'echo "${!r[@]}" | tr " " "\\n" | sort | tr "\\n" " "')


class TestNamerefArrayWrites(ConformanceTest):
    """Element writes through a nameref target the underlying array."""

    def test_write_new_element(self):
        self.assert_identical_behavior(
            _IDX + 'r[3]=99; echo "${arr[@]}"')

    def test_overwrite_element(self):
        self.assert_identical_behavior(
            _IDX + 'r[0]=AA; echo "${arr[@]}"')


class TestNamerefArrayEdgeCases(ConformanceTest):
    """Edge cases match bash."""

    def test_element_nameref_subscripted(self):
        # declare -n r=arr[1]: scalar $r is the element; ${r[@]} is empty.
        self.assert_identical_behavior(
            'declare -a arr=(10 20 30); declare -n r=arr[1]; '
            'echo "$r"; echo "[${r[@]}]"; echo "${#r[@]}"')

    def test_nameref_to_unset(self):
        self.assert_identical_behavior(
            'declare -n r=nope; echo "[${r[@]}]"; echo "${#r[@]}"')

    def test_nameref_to_scalar_subscript(self):
        self.assert_identical_behavior(
            'x=hi; declare -n r=x; echo "${r[@]}" "${r[0]}"')

    def test_non_nameref_array_unchanged(self):
        self.assert_identical_behavior(
            'declare -a arr=(1 2 3); '
            'echo "${arr[@]} ${arr[1]} ${#arr[@]} ${!arr[@]}"')
