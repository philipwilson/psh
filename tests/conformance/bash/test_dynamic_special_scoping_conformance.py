"""Dynamic specials consult lexical scope — `local RANDOM` masks it (R2).

bash: a `local RANDOM`/`local SECONDS`/`local LINENO` makes the name an ordinary
variable in that scope (and nested calls, via dynamic scoping), suspending the
dynamic behaviour until the declaring scope exits; a GLOBAL `RANDOM=5` still
seeds. Every masked-read row below is deterministic (the local holds a literal),
so it compares exactly against bash.

Probed against bash 5.2 at base 9230699b (family D in
tmp/boundary-ledgers/R2-probes/deep_base_9230699b.txt): the masking rows were
DIVERGENT at base (psh always computed the dynamic value); the global-seed
parity row matched at base.
"""
from conformance_framework import ConformanceTest


class TestLocalMasksDynamicSpecial(ConformanceTest):
    def test_local_random_reads_literal(self):
        self.assert_identical_behavior('f(){ local RANDOM=5; echo "$RANDOM$RANDOM"; }; f')

    def test_local_seconds_reads_literal(self):
        self.assert_identical_behavior('f(){ local SECONDS=99; echo "$SECONDS"; }; f')

    def test_local_lineno_reads_literal(self):
        self.assert_identical_behavior('f(){ local LINENO=7; echo "$LINENO"; }; f')

    def test_local_random_no_value_is_unset(self):
        self.assert_identical_behavior('f(){ local RANDOM; echo "[${RANDOM-U}]"; }; f')

    def test_local_random_declare_p_shows_plain_local(self):
        self.assert_identical_behavior('f(){ local RANDOM=5; declare -p RANDOM; }; f')

    def test_assign_to_masked_random_updates_local(self):
        self.assert_identical_behavior('f(){ local RANDOM=5; RANDOM=6; echo "$RANDOM"; }; f')

    def test_unset_masked_random_stays_unset(self):
        self.assert_identical_behavior(
            'f(){ local RANDOM=5; unset RANDOM; echo "[${RANDOM-U}]"; }; f')

    def test_integer_attribute_on_masked_random(self):
        self.assert_identical_behavior(
            'f(){ local RANDOM=abc; declare -i RANDOM; RANDOM=3+4; echo "$RANDOM"; }; f')

    def test_masked_special_visible_in_nested_call(self):
        self.assert_identical_behavior(
            'g(){ echo "[$RANDOM]"; }; f(){ local RANDOM=5; g; }; f')

    def test_exported_masked_special_materializes_local_to_child_env(self):
        # An exported `local SECONDS=5` must reach a child's environment as 5,
        # not the special's computed snapshot (find_exported_instance mask).
        self.assert_identical_behavior(
            'export SECONDS; f(){ local SECONDS=5; printenv SECONDS; }; f')


class TestPrefixMasksDynamicSpecial(ConformanceTest):
    """Bounce B3: a function-prefix assignment over a dynamic special
    (`RANDOM=5 f`) MASKS it for the invocation, like a local — the prefix
    binding lives in the temp-env scope, which `_local_shadows_special` scans.
    Bash-correct at tip; pinned so a mutation restricting the mask to
    non-temp-env scopes goes red (mutation transcript in
    tmp/boundary-ledgers/R2-probes/mutation-tempenv-mask.txt)."""

    def test_random_prefix_masks_and_body_write_updates(self):
        self.assert_identical_behavior(
            'f(){ echo "[$RANDOM]"; RANDOM=7; echo "[$RANDOM]"; }; RANDOM=5 f')

    def test_seconds_prefix_masks(self):
        self.assert_identical_behavior(
            'f(){ echo "[$SECONDS]"; }; SECONDS=42 f')

    def test_random_prefix_declare_p_shows_binding(self):
        self.assert_identical_behavior(
            'f(){ declare -p RANDOM; }; RANDOM=5 f')

    def test_random_dynamic_again_after_prefix_call(self):
        self.assert_identical_behavior(
            'f(){ :; }; RANDOM=5 f; v=$RANDOM; '
            'case "$v" in (*[!0-9]*|"") echo notnum;; (*) echo dynamic;; esac')


class TestReadonlySpecialRefusesLocal(ConformanceTest):
    """Bounce B4: `readonly SECONDS` (overlay readonly, no stored cell) REFUSES
    a masking local — bash: 'local: SECONDS: readonly variable', rc 1, the
    function CONTINUES, and reads stay dynamic. Message suppressed here (the
    location prefix differs by the documented convention); the message body is
    pinned in tests/unit/core/test_dynamic_special_masking.py. Rows were RED at
    tip 9c1cdde5 (the local was silently created)."""

    def test_readonly_seconds_local_refused_reads_dynamic(self):
        self.assert_identical_behavior(
            'readonly SECONDS; f(){ local SECONDS=5 2>/dev/null; '
            'echo "in=[$SECONDS]"; }; f; echo "rc=$? after"')

    def test_readonly_random_local_refused_continues(self):
        self.assert_identical_behavior(
            'readonly RANDOM; f(){ local RANDOM=7 2>/dev/null; echo done; }; '
            'f; echo "rc=$?"')


class TestGlobalDynamicSpecialStillActive(ConformanceTest):
    """A global assignment SEEDS the dynamic special (not a mask) — parity."""

    def test_global_random_seed_is_repeatable(self):
        # Both shells reseed repeatably (the VALUES differ by RNG, so pin the
        # PROPERTY, not the number).
        self.assert_identical_behavior(
            'RANDOM=5; a=$RANDOM; RANDOM=5; b=$RANDOM; [ "$a" = "$b" ] && echo same || echo diff')

    def test_dynamic_special_returns_after_scope_exit(self):
        self.assert_identical_behavior(
            'f(){ local RANDOM=5; echo "$RANDOM"; }; f; '
            'v=$RANDOM; case "$v" in (*[!0-9]*|"") echo notnum;; (*) echo dynamic-again;; esac')
