"""Nameref attribute resolution conformance (campaign R2, #20 R2 mutation engine).

"Attribute changes resolve namerefs except when modifying the nameref attribute
itself." A `declare -n r=x` reference redirects a subsequent `declare -i/-u/-l`,
`readonly`, or `export` onto its TARGET x — but `declare -n`/`declare +n` (which
change the nameref attribute) land on the reference cell.

Every row probed against bash 5.2 at base 9230699b (family N in
tmp/boundary-ledgers/R2-probes/deep_base_9230699b.txt): N1-N5/N8 were DIVERGENT
at base (red-on-base pins); N6/N7/N9 matched at base (parity pins guarding the
"don't over-resolve" boundary).
"""
from conformance_framework import ConformanceTest


class TestAttributeResolvesNameref(ConformanceTest):
    def test_declare_integer_through_ref_arithmetic(self):
        self.assert_identical_behavior(
            'x=5; declare -n r=x; declare -i r; r=3+4; echo "x=[$x]"')

    def test_declare_uppercase_through_ref(self):
        self.assert_identical_behavior(
            'x=hi; declare -n r=x; declare -u r; r=abc; echo "x=[$x]"')

    def test_declare_lowercase_through_ref(self):
        self.assert_identical_behavior(
            'x=HI; declare -n r=x; declare -l r; r=ABC; echo "x=[$x]"')

    def test_readonly_through_ref_marks_target(self):
        # Observe via declare -p (a readonly-assignment error would only differ
        # in the location prefix `psh:` vs the bash argv0 — the documented
        # convention; the readonly attribute LANDING on x is the behavior).
        self.assert_identical_behavior(
            'x=5; declare -n r=x; readonly r; declare -p x')

    def test_declare_p_shows_attribute_on_target(self):
        self.assert_identical_behavior(
            'x=5; declare -n r=x; declare -i r; declare -p x')

    def test_export_through_ref_exports_target(self):
        self.assert_identical_behavior(
            'x=5; declare -n r=x; export r; f(){ printenv x; }; f')


class TestAttributeRemovalResolvesNameref(ConformanceTest):
    def test_remove_integer_through_ref(self):
        self.assert_identical_behavior(
            'x=5; declare -n r=x; declare -i r; declare +i r; r=3+4; echo "x=[$x]"')


class TestNamerefAttributeItselfDoesNotResolve(ConformanceTest):
    """The nameref attribute itself (declare -n / declare +n) targets the
    reference cell — it must NOT resolve through."""

    def test_declare_n_on_existing_does_not_deref(self):
        self.assert_identical_behavior('x=y; y=deep; declare -n r; r=x; declare -p r')

    def test_declare_n_twice_stays_on_ref(self):
        self.assert_identical_behavior('x=v; declare -n r=x; declare -n r; declare -p r')

    def test_declare_plus_n_unreferences_ref(self):
        self.assert_identical_behavior('x=5; declare -n r=x; declare +n r; echo "r=[$r]"')
