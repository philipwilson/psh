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


class TestCycleAttributeOpsWarnAndContinue(ConformanceTest):
    """Bounce B2: an attribute op on a nameref CYCLE warns twice and CONTINUES
    rc 0 (bash), even under set -e — unlike a value write, which rejects.
    Warnings are suppressed here (the location prefix differs by the documented
    convention); the warn-count is pinned in
    tests/unit/core/test_nameref_attribute_resolution.py. Rows were RED at tip
    9c1cdde5 (attribute ops raised, rc 1, set -e aborted)."""

    def test_declare_i_on_cycle_survives_set_e(self):
        self.assert_identical_behavior(
            'set -e; declare -n a=b; declare -n b=a; declare -i a 2>/dev/null; '
            'echo "survived rc=$?"')

    def test_readonly_on_cycle_continues_rc0(self):
        self.assert_identical_behavior(
            'declare -n a=b; declare -n b=a; readonly a 2>/dev/null; echo "rc=$?"')

    def test_declare_plus_i_on_cycle_continues_rc0(self):
        self.assert_identical_behavior(
            'declare -n a=b; declare -n b=a; declare +i a 2>/dev/null; echo "rc=$?"')

    def test_export_on_cycle_continues_rc0(self):
        self.assert_identical_behavior(
            'declare -n a=b; declare -n b=a; export a 2>/dev/null; echo "rc=$?"')

    def test_cycle_attr_op_leaves_state_unchanged(self):
        self.assert_identical_behavior(
            'declare -n a=b; declare -n b=a; declare -i a 2>/dev/null; '
            'declare -p a b')


class TestAttributeThroughMissingTarget(ConformanceTest):
    """Bounce B5: an attribute op through a nameref whose TARGET does not exist
    creates a declared-unset attribute-carrying cell — the standard upvar idiom
    (`declare -n ref=$1; declare -i ref`). declare/typeset/readonly create in
    declare's target scope (LOCAL inside a function — bash); export creates the
    exported cell non-locally so it survives the function. Rows were RED at
    BASE 9230699b (and at tip 9c1cdde5: silent no-op)."""

    def test_declare_i_missing_target_creates_cell(self):
        self.assert_identical_behavior(
            'declare -n r=missing; declare -i r; declare -p missing')

    def test_declare_i_missing_target_arithmetic_works(self):
        self.assert_identical_behavior(
            'declare -n r=missing; declare -i r; r=3+4; echo "[$missing]"')

    def test_upvar_idiom_declare_i_in_function_is_local(self):
        # The created cell is LOCAL to the declaring function: tgt dies with f.
        self.assert_identical_behavior(
            'f(){ declare -n r=$1; declare -i r; r=3+4; }; f tgt; echo "[${tgt-U}]"')

    def test_declare_i_in_function_local_cell_shown_then_gone(self):
        self.assert_identical_behavior(
            'f(){ declare -n r=gv; declare -i r; declare -p gv; }; f; '
            'declare -p gv 2>/dev/null; echo "rc=$?"')

    def test_declare_u_missing_target_uppercases_later(self):
        self.assert_identical_behavior(
            'declare -n r=missing; declare -u r; missing=abc; echo "[$missing]"')

    def test_export_missing_target_survives_function(self):
        self.assert_identical_behavior(
            'f(){ declare -n r=gv; export r; gv=5; printenv gv; }; f; '
            'echo "top=[${gv-U}]"')

    def test_readonly_missing_target_protects(self):
        self.assert_identical_behavior(
            'declare -n r=missing; readonly r; declare -p missing')

    def test_two_deep_chain_lands_on_final_target(self):
        self.assert_identical_behavior(
            'declare -n r2=mid; declare -n mid=deep; declare -i r2; declare -p deep')
