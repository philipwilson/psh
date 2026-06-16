"""
Conformance tests for `[[ -v name ]]` / `test -v name` on arrays.

bash's `-v name` on an array tests element 0 (`-v name[0]`), so an array with
no element 0 — including an empty array, even one explicitly assigned `=()` —
is "unset". psh returned true whenever the array variable merely existed
(reappraisal #13 MED).

Verified against bash 5.2. (A separate, still-open item is `declare -p` of a
never-assigned array printing `declare -a a` vs an assigned-empty `declare -a a=()`
— that needs an UNSET-array-state model and is not addressed here.)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestVOnArrays(ConformanceTest):
    def test_declared_empty_indexed_is_unset(self):
        self.assert_identical_behavior(
            'declare -a a; [[ -v a ]] && echo SET || echo UNSET')

    def test_assigned_empty_indexed_is_unset(self):
        self.assert_identical_behavior(
            'declare -a a=(); [[ -v a ]] && echo SET || echo UNSET')

    def test_populated_indexed_is_set(self):
        self.assert_identical_behavior(
            'a=(x y); [[ -v a ]] && echo SET || echo UNSET')

    def test_indexed_without_element_zero_is_unset(self):
        self.assert_identical_behavior(
            'a=([5]=z); [[ -v a ]] && echo SET || echo UNSET')

    def test_unset_element_zero_is_unset(self):
        self.assert_identical_behavior(
            'a=(x); unset "a[0]"; [[ -v a ]] && echo SET || echo UNSET')

    def test_assoc_without_key_zero_is_unset(self):
        self.assert_identical_behavior(
            'declare -A m=([x]=1); [[ -v m ]] && echo SET || echo UNSET')

    def test_assoc_with_key_zero_is_set(self):
        self.assert_identical_behavior(
            'declare -A m=([0]=1); [[ -v m ]] && echo SET || echo UNSET')


class TestVUnchangedCases(ConformanceTest):
    """Scalars and explicit element refs are unaffected."""

    def test_scalar_set(self):
        self.assert_identical_behavior('s=hi; [[ -v s ]] && echo SET || echo UNSET')

    def test_scalar_unset(self):
        self.assert_identical_behavior(
            'unset s; [[ -v s ]] && echo SET || echo UNSET')

    def test_element_present(self):
        self.assert_identical_behavior(
            'a=(x); [[ -v a[0] ]] && echo SET || echo UNSET')

    def test_element_absent(self):
        self.assert_identical_behavior(
            'a=(x); [[ -v a[5] ]] && echo SET || echo UNSET')

    def test_test_builtin_form(self):
        self.assert_identical_behavior(
            'declare -a a; test -v a && echo SET || echo UNSET')
