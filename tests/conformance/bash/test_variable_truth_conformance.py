"""Variable truth & environment materialization conformance (#20 H13, campaign R2).

`ScopeManager.lookup()` is the tri-state read authority (MISSING | PRESENT_UNSET
| VALUE). A declared-unset LOCAL stops the lookup — it never falls through to the
environment, so an exported outer value is not resurrected under a `local` shadow.
`$!` is absent until the first background job. A function-prefix assignment is a
local of the invocation, so a value-less `local x` inherits it.

Every row was probed against bash 5.2 at base 9230699b — see
tmp/boundary-ledgers/R2-probes/matrix_base_9230699b.txt (families A/C/D/H) and
deep_base_9230699b.txt. The H13/$! rows were DIVERGENT at base (red-on-base pins);
the declared-unset-vs-empty rows matched at base (parity pins).
"""
from conformance_framework import ConformanceTest


class TestH13ShadowingUnsetLocal(ConformanceTest):
    """A declared-unset local shadowing an exported outer reads as unset — bash
    does NOT see the exported value through the environment (#20 H13)."""

    def test_declared_unset_local_default_operator(self):
        self.assert_identical_behavior(
            'export FOO=outer; f(){ local FOO; printf "<%s> <%s>\\n" "$FOO" "${FOO-u}"; }; f')

    def test_declared_unset_local_plus_operator(self):
        self.assert_identical_behavior(
            'export FOO=outer; f(){ local FOO; printf "<%s>\\n" "${FOO+set}"; }; f')

    def test_local_then_unset_default_operator(self):
        self.assert_identical_behavior(
            'export FOO=outer; f(){ local FOO=x; unset FOO; printf "<%s> <%s>\\n" "$FOO" "${FOO-u}"; }; f')

    def test_declared_unset_local_colon_default(self):
        self.assert_identical_behavior(
            'export V=out; f(){ local V; printf "[%s]\\n" "${V:-D}"; }; f')

    def test_declared_unset_local_colon_plus(self):
        self.assert_identical_behavior(
            'export V=out; f(){ local V; printf "[%s]\\n" "${V:+D}"; }; f')

    def test_declared_unset_local_question_aborts(self):
        # ${V?} fires because the LOCAL V is unset (not the exported outer): the
        # shell aborts before `echo AFTER` (rc 127, no output). Without `local V`
        # this would read the global "out" and NOT abort. The error MESSAGE is
        # suppressed (2>/dev/null) because it differs only in the documented
        # location prefix (`psh:` vs the bash argv0); the abort is the behavior.
        self.assert_identical_behavior(
            'export V=out; f(){ local V; echo "${V?msg}"; }; f 2>/dev/null; echo AFTER')

    def test_declared_unset_local_assign_default(self):
        self.assert_identical_behavior(
            'export V=out; f(){ local V; echo "${V=assigned}"; echo "now=[$V]"; }; f')

    def test_env_provided_var_local_shadow_unset(self):
        self.assert_identical_behavior(
            'f(){ local ENVV; unset ENVV; echo "${ENVV-u}"; }; f',
            env={"ENVV": "fromenv"})

    def test_env_provided_var_visible_at_top_level(self):
        # Not shadowed: the env var IS a shell variable and reads normally.
        self.assert_identical_behavior('echo "${ENVV-u}"', env={"ENVV": "fromenv"})


class TestDeclaredUnsetVsEmpty(ConformanceTest):
    """`local x` (declared-unset) vs `local x=` (empty) discrimination — parity."""

    def test_local_declared_unset_plus(self):
        self.assert_identical_behavior('f(){ local x; echo "${x+SET}"; }; f')

    def test_local_empty_plus(self):
        self.assert_identical_behavior('f(){ local x=; echo "${x+SET}"; }; f')

    def test_local_declared_unset_default(self):
        self.assert_identical_behavior('f(){ local x; echo "${x-DEF}"; }; f')

    def test_local_declared_unset_declare_p(self):
        self.assert_identical_behavior('f(){ local x; declare -p x; }; f')

    def test_local_empty_declare_p(self):
        self.assert_identical_behavior('f(){ local x=; declare -p x; }; f')


class TestFunctionPrefixLocal(ConformanceTest):
    """A function-prefix assignment (`x=1 f`) is a local of the invocation, so a
    value-less `local x` inherits it (bash merges prefix vars into locals). This
    was masked by the H13 env fallback and surfaced when it was removed."""

    def test_valueless_local_inherits_prefix(self):
        self.assert_identical_behavior('f(){ local x; echo "[$x]"; }; x=1 f')

    def test_local_empty_overrides_prefix(self):
        self.assert_identical_behavior('f(){ local x=; echo "[$x]"; }; x=1 f')

    def test_local_declare_p_shows_exported_prefix_value(self):
        self.assert_identical_behavior('f(){ local x; declare -p x; }; x=5 f')

    def test_valueless_local_typed_inherits_prefix(self):
        self.assert_identical_behavior('f(){ local -i x; echo "[$x]"; }; x=10 f')

    def test_outer_function_local_not_inherited(self):
        # A provenance-less outer local is never inherited (no prefix anywhere).
        self.assert_identical_behavior(
            'g(){ local x; echo "[$x]"; }; f(){ local x=7; g; }; f')


class TestFunctionPrefixLocalDepth(ConformanceTest):
    """Bounce B1: prefix inheritance is DEPTH-AWARE (bash att_tempvar model).
    A value-less `local x` inherits value+export from the nearest enclosing
    temp-env-provenance instance at ANY call depth: the prefix binding itself,
    or a local that (re)declared it in the prefixed invocation (which keeps
    provenance). A provenance-less instance in between BLOCKS inheritance, and
    copies do not carry provenance onward. All rows probed against bash 5.2
    (R2-B1 matrix); the depth/intervening rows were RED at tip 9c1cdde5."""

    def test_depth2_inherits_prefix(self):
        self.assert_identical_behavior(
            'g(){ local x; echo "g=[${x-U}]"; }; f(){ g; }; x=5 f')

    def test_depth3_inherits_prefix(self):
        self.assert_identical_behavior(
            'h(){ local x; echo "h=[${x-U}]"; }; g(){ h; }; f(){ g; }; x=5 f')

    def test_intervening_value_local_keeps_provenance(self):
        # f redeclares the merged prefix binding with a value: g inherits L.
        self.assert_identical_behavior(
            'g(){ local x; echo "g=[${x-U}]"; }; f(){ local x=L; g; }; x=5 f')

    def test_intervening_valueless_local_keeps_provenance(self):
        self.assert_identical_behavior(
            'g(){ local x; echo "g=[${x-U}]"; }; f(){ local x; g; }; x=5 f')

    def test_body_write_updates_what_deeper_local_inherits(self):
        self.assert_identical_behavior(
            'g(){ local x; echo "g=[${x-U}]"; }; f(){ x=W; g; }; x=5 f')

    def test_unset_prefix_blocks_inheritance(self):
        self.assert_identical_behavior(
            'g(){ local x; echo "g=[${x-U}]"; }; f(){ unset x; g; }; x=5 f')

    def test_plain_global_never_inherited(self):
        self.assert_identical_behavior(
            'g(){ local x; echo "g=[${x-U}]"; }; f(){ g; }; x=5; f')

    def test_deeper_fresh_value_local_has_no_provenance(self):
        # g's `local x=G` (a different frame from the prefixed one) is a fresh
        # variable WITHOUT provenance — h does not inherit G.
        self.assert_identical_behavior(
            'h(){ local x; echo "h=[${x-U}]"; }; g(){ local x=G; h; }; '
            'f(){ g; }; x=5 f')

    def test_copies_do_not_carry_provenance(self):
        # g's value-less inherit from f's provenance local is an ordinary
        # local: h reads unset.
        self.assert_identical_behavior(
            'h(){ local x; echo "h=[${x-U}]"; }; g(){ local x; h; }; '
            'f(){ local x=L; g; }; x=5 f')

    def test_direct_tempenv_copy_has_no_provenance(self):
        self.assert_identical_behavior(
            'h(){ local x; echo "h=[${x-U}]"; }; '
            'g(){ local x; echo "g=[${x-U}]"; h; }; f(){ g; }; x=5 f')

    def test_inherited_copy_keeps_export_declare_p(self):
        self.assert_identical_behavior(
            'g(){ local x; declare -p x; }; '
            'f(){ local x=L; declare -p x; g; }; x=5 f')

    def test_tombstoned_provenance_local_blocks(self):
        self.assert_identical_behavior(
            'g(){ local x; echo "[${x-U}]"; }; '
            'f(){ local x=L; unset x; g; }; x=5 f')


class TestBangAbsence(ConformanceTest):
    """$! is absent until the first background job runs (#20 R2)."""

    def test_bang_default_before_bg(self):
        self.assert_identical_behavior('echo "[${!-EMPTY}]"')

    def test_bang_plus_before_bg(self):
        self.assert_identical_behavior('echo "[${!+SET}]"')

    def test_bang_plain_before_bg(self):
        self.assert_identical_behavior('echo "[$!]"')

    def test_bang_colon_default_before_bg(self):
        self.assert_identical_behavior('echo "[${!:-EMPTY}]"')
