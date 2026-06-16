"""
Conformance tests for whole-array assignment/append through a nameref.

`declare -n r=arr` makes `r` an alias for `arr`. Element writes (`r[i]=x`) and
whole-array replacement (`r=(...)`) already resolved the nameref, but `r+=(...)`
did NOT: the existing-contents lookup used the nameref's value (the target NAME
string), so the append started from a fresh array and REPLACED the target
instead of appending (reappraisal #13 HIGH — `a=(1 2 3); declare -n r=a; r+=(4)`
gave `a=([0]="4")`).

Verified against bash 5.2.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestNamerefArrayAppend(ConformanceTest):
    def test_indexed_append_single(self):
        self.assert_identical_behavior(
            'a=(1 2 3); declare -n r=a; r+=(4); declare -p a')

    def test_indexed_append_multiple(self):
        self.assert_identical_behavior(
            'a=(1); declare -n r=a; r+=(2 3); declare -p a')

    def test_assoc_append(self):
        self.assert_identical_behavior(
            'declare -A h=([x]=1); declare -n r=h; r+=([y]=2); '
            'echo "${h[x]} ${h[y]}"')

    def test_append_to_empty_target(self):
        self.assert_identical_behavior(
            'declare -a a; declare -n r=a; r+=(1 2); echo "${a[@]}"')


class TestNamerefArrayOtherWritesUnchanged(ConformanceTest):
    """Whole-array replace and element write through a nameref still work."""

    def test_whole_array_replace(self):
        self.assert_identical_behavior(
            'a=(1 2 3); declare -n r=a; r=(9 8); declare -p a')

    def test_element_write(self):
        self.assert_identical_behavior(
            'a=(1 2 3); declare -n r=a; r[1]=X; declare -p a')


class TestNonNamerefAppendUnchanged(ConformanceTest):
    """Plain (non-nameref) array append is unaffected."""

    def test_indexed(self):
        self.assert_identical_behavior('a=(1 2); a+=(3); declare -p a')

    def test_assoc(self):
        self.assert_identical_behavior(
            'declare -A h=([x]=1); h+=([y]=2); echo "${h[x]} ${h[y]}"')
