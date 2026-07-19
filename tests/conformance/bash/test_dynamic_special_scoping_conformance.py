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
