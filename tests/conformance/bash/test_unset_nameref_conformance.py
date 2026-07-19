"""`unset -n` semantics conformance (campaign R2).

bash: `unset -n NAME` unsets the nameref VARIABLE itself (not its target), but
ONLY when NAME actually holds a nameref — on a plain variable, an array, or a
missing name it is a SILENT NO-OP. A bare `unset` (or `-v`) instead resolves a
nameref to its target.

Probed against bash 5.2 at base 9230699b (family U in
tmp/boundary-ledgers/R2-probes/deep_base_9230699b.txt): U1 (the no-op on a plain
var) was DIVERGENT at base (psh unset it); the nameref rows matched at base.
"""
from conformance_framework import ConformanceTest


class TestUnsetNameref(ConformanceTest):
    def test_unset_n_on_plain_var_is_noop(self):
        self.assert_identical_behavior('x=v; unset -n x; echo "[${x-U}]"')

    def test_unset_n_on_array_is_noop(self):
        self.assert_identical_behavior('declare -a a=(1 2); unset -n a; echo "rc=$? [${a[0]}]"')

    def test_unset_n_on_missing_name_is_noop(self):
        self.assert_identical_behavior('unset -n NOPE; echo "rc=$?"')

    def test_unset_n_on_nameref_unsets_the_ref(self):
        self.assert_identical_behavior(
            'x=v; declare -n r=x; unset -n r; echo "x=[${x-U}] r=[${r-U}]"')

    def test_unset_n_mixed_ref_and_plain(self):
        self.assert_identical_behavior(
            'x=v; y=w; declare -n r=x; unset -n r y; echo "x=[${x-U}] y=[${y-U}] r=[${r-U}]"')

    def test_bare_unset_on_nameref_resolves_target(self):
        self.assert_identical_behavior(
            'x=v; declare -n r=x; unset r; echo "x=[${x-U}] r=[${r-U}]"')
