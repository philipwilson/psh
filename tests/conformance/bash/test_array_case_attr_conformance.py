"""
Conformance tests for the case attributes (-u/-l) on ARRAY element writes.

`declare -u`/`-l` upper/lower-cases a variable's value on assignment. psh
applied this to scalars and the integer (-i) attribute to array elements, but
NOT case-folding to array element writes (reappraisal #13): `declare -au a;
a[0]=foo` left `foo` instead of `FOO`.

Verified against bash 5.2.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestArrayElementCaseAttr(ConformanceTest):
    def test_indexed_uppercase_element(self):
        self.assert_identical_behavior(
            'declare -au a; a[0]=foo; a[1]=bar; echo "${a[@]}"')

    def test_assoc_uppercase_element(self):
        self.assert_identical_behavior('declare -Au m; m[k]=foo; echo "${m[k]}"')

    def test_indexed_lowercase_element(self):
        self.assert_identical_behavior('declare -al a; a[0]=HELLO; echo "${a[0]}"')

    def test_uppercase_append_element(self):
        self.assert_identical_behavior(
            'declare -au a; a[0]=foo; a[0]+=bar; echo "${a[0]}"')


class TestArrayCaseAttrInteractions(ConformanceTest):
    """Integer attribute still wins; init folding and scalars unaffected."""

    def test_integer_element_still_arithmetic(self):
        self.assert_identical_behavior('declare -ai a; a[0]=3+4; echo "${a[0]}"')

    def test_array_init_uppercase(self):
        self.assert_identical_behavior('declare -au a=(foo bar); echo "${a[@]}"')

    def test_assoc_init_lowercase(self):
        self.assert_identical_behavior('declare -Al m=([k]=VAL); echo "${m[k]}"')

    def test_scalar_uppercase_unaffected(self):
        self.assert_identical_behavior('declare -u s; s=foo; echo "$s"')

    def test_no_attribute_element_unchanged(self):
        self.assert_identical_behavior('a[0]=Foo; echo "${a[0]}"')
