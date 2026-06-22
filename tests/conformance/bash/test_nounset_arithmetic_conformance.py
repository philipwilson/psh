"""
Conformance tests for `set -u` (nounset) inside ARITHMETIC contexts.

Bash errors when an unset variable is referenced in arithmetic under `set -u`,
exactly like a bare `$undef`. psh enforced nounset for plain expansion but the
arithmetic evaluator silently substituted 0 (reappraisal #14) — so
`$(( undef ))`, `(( undef ))`, and `for ((i=undef;...))` all wrongly succeeded.
Now they raise `NAME: unbound variable` and abort the non-interactive shell,
matching bash. The set-but-empty case (`e=; $((e+1))`) and a present value stay
exempt.

Error messages are compared by exit code + substring (the `bash: line N:`
prefix differs from psh's by design); non-error behavior is compared exactly.
Verified against bash 5.2.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest, find_bash


class TestNounsetArithmeticErrors(ConformanceTest):
    """An unset variable in arithmetic under set -u errors like a bare $undef."""

    def _assert_unbound(self, cmd, name):
        psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                             capture_output=True, text=True)
        bash = subprocess.run([find_bash(), '-c', cmd],
                              capture_output=True, text=True)
        assert bash.returncode != 0, f"expected bash to fail: {cmd}"
        assert psh.returncode == bash.returncode, (
            f"{cmd}: psh rc={psh.returncode} bash rc={bash.returncode}")
        assert f'{name}: unbound variable' in psh.stderr, psh.stderr
        assert f'{name}: unbound variable' in bash.stderr, bash.stderr

    def test_arith_expansion(self):
        self._assert_unbound('set -u; echo $(( undefined + 1 ))', 'undefined')

    def test_arith_expansion_assignment(self):
        self._assert_unbound('set -u; x=$(( y )); echo $x', 'y')

    def test_arith_command(self):
        self._assert_unbound('set -u; (( z + 1 )); echo done', 'z')

    def test_reference_chain_to_unset(self):
        self._assert_unbound('set -u; a=b; echo $(( a ))', 'b')

    def test_second_operand_unset(self):
        self._assert_unbound('set -u; a=3; echo $(( a + b ))', 'b')

    def test_unset_whole_array(self):
        self._assert_unbound('set -u; unset arr; echo $(( arr[0] ))', 'arr')

    def test_cstyle_for_init(self):
        self._assert_unbound(
            'set -u; for ((i=n;i<3;i++)); do echo $i; done', 'n')

    def test_cstyle_for_condition(self):
        self._assert_unbound(
            'set -u; for ((i=0;i<n;i++)); do echo $i; done', 'n')


class TestNounsetArithmeticExempt(ConformanceTest):
    """Cases that must NOT error (match bash exactly)."""

    def test_set_but_empty(self):
        self.assert_identical_behavior('set -u; e=; echo $(( e + 1 ))')

    def test_defined_value(self):
        self.assert_identical_behavior('set -u; v=5; echo $(( v + 1 ))')

    def test_defined_zero(self):
        self.assert_identical_behavior('set -u; z=0; echo $(( z + 5 ))')

    def test_literal(self):
        self.assert_identical_behavior('set -u; echo $(( 2 + 3 ))')

    def test_no_nounset_unset_is_zero(self):
        self.assert_identical_behavior('echo $(( undefined + 1 ))')

    def test_set_array_unset_index(self):
        self.assert_identical_behavior('set -u; arr=(1 2); echo $(( arr[5] ))')
