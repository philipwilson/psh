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
        # Only THIS invocation's prefix is inherited, not an outer local.
        self.assert_identical_behavior(
            'g(){ local x; echo "[$x]"; }; f(){ local x=7; g; }; f')


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
