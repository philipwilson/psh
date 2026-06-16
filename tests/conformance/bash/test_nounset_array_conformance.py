"""
Conformance tests for `set -u` (nounset) on ARRAY element reads.

Bash errors when a bare `${arr[i]}` / `${arr[key]}` reads an absent element
under `set -u` (just like a missing scalar). psh enforced nounset for scalars
(v0.480) but not for array elements (reappraisal #13) — `${a[5]}` returned ''
with exit 0. Now an absent element errors with `arr[idx]: unbound variable`,
while the value-substituting operator forms (`${a[i]:-d}`, `${a[i]:+s}`), the
length form (`${#a[i]}`), and the whole-array forms (`${a[@]}`/`${a[*]}`)
remain exempt — matching bash.

Error messages are compared by exit code + substring (the `bash: line N:`
prefix differs from psh's by design); non-error behavior is compared exactly.

Verified against bash 5.2.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest, find_bash


def _both_unbound(cmd):
    """psh and bash both fail with an 'unbound variable' diagnostic."""
    psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                         capture_output=True, text=True)
    bash = subprocess.run([find_bash(), '-c', cmd],
                          capture_output=True, text=True)
    return psh, bash


class TestNounsetArrayElementErrors(ConformanceTest):
    """An absent element read under set -u errors (exit + message substring)."""

    def _assert_unbound(self, cmd, name):
        psh, bash = _both_unbound(cmd)
        assert bash.returncode != 0, f"expected bash to fail: {cmd}"
        assert psh.returncode == bash.returncode, (
            f"{cmd}: psh rc={psh.returncode} bash rc={bash.returncode}")
        assert f'{name}: unbound variable' in psh.stderr, psh.stderr
        assert f'{name}: unbound variable' in bash.stderr, bash.stderr

    def test_unset_indexed_element(self):
        self._assert_unbound('set -u; a=(1 2 3); echo ${a[5]}', 'a[5]')

    def test_missing_assoc_key(self):
        self._assert_unbound(
            'set -u; declare -A m=([a]=1); echo ${m[b]}', 'm[b]')

    def test_declared_empty_array_element(self):
        self._assert_unbound('set -u; declare -a a; echo ${a[0]}', 'a[0]')

    def test_never_declared_array_element(self):
        self._assert_unbound('set -u; echo ${a[5]}', 'a[5]')


class TestNounsetArrayExempt(ConformanceTest):
    """Operator / length / whole-array forms are NOT subject to the error."""

    def test_default_operator(self):
        self.assert_identical_behavior('set -u; a=(1); echo ${a[5]:-def}')

    def test_alt_operator(self):
        self.assert_identical_behavior('set -u; a=(1); echo ${a[5]:+set}')

    def test_length_of_absent_element(self):
        self.assert_identical_behavior('set -u; a=(1); echo ${#a[5]}')

    def test_whole_array_unset(self):
        self.assert_identical_behavior(
            'set -u; declare -a a; echo "${a[@]}"; echo ok')

    def test_whole_array_star_unset(self):
        self.assert_identical_behavior(
            'set -u; declare -a a; echo "${a[*]}"; echo ok')


class TestNounsetArrayPresent(ConformanceTest):
    """Present elements (including empty ones) read fine under set -u."""

    def test_present_element(self):
        self.assert_identical_behavior('set -u; a=(1 2 3); echo ${a[1]}')

    def test_present_element_zero(self):
        self.assert_identical_behavior('set -u; a=(9 8); echo ${a[0]}')

    def test_present_empty_element(self):
        self.assert_identical_behavior('set -u; a=(""); echo [${a[0]}]')

    def test_present_assoc_key(self):
        self.assert_identical_behavior(
            'set -u; declare -A m=([k]=v); echo ${m[k]}')

    def test_no_nounset_absent_is_empty(self):
        self.assert_identical_behavior('a=(1); echo [${a[5]}]')
