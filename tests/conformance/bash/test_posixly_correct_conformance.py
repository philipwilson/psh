"""POSIXLY_CORRECT <-> posix option coupling conformance (bash 5.2).

Task #31. Live re-check against the host bash that psh's ``posix`` option is
two-way coupled to the POSIXLY_CORRECT variable exactly like bash's
set_posix_mode / sv_strict_posix:

* POSIXLY_CORRECT present in the startup environment (any value) enables
  posix mode;
* assigning it mid-session enables posix mode, unsetting it disables it;
* ``set -o posix`` binds POSIXLY_CORRECT to ``y`` (unexported, and only when
  the variable is not already set, so an existing value is preserved);
* ``set +o posix`` unsets it;
* $SHELLOPTS reflects ``posix`` once it flips on (cross-release with the
  v0.675 option-reflection surface).

Each row compares stdout + exit code exactly (the coupling is observable
without diagnostics); the startup-environment row is exercised through the
framework's ``env`` parameter. The ``--posix`` flag and the
special-builtin-exit interaction (v0.673) live in the system suite, which can
vary invocation argv and inspect a real process environment.
"""


from conformance_framework import ConformanceTest


class TestPosixlyCorrectCoupling(ConformanceTest):
    """Two-way POSIXLY_CORRECT <-> posix coupling matches bash."""

    # --- variable -> option ---------------------------------------------

    def test_assign_enables_posix(self):
        # CLAIM marker (test_claims_have_tests.py): the compatibility-table
        # "set -o posix / POSIXLY_CORRECT" row maps here.
        self.assert_identical_behavior(
            'POSIXLY_CORRECT=1; set -o | grep posix')

    def test_empty_assign_enables_posix(self):
        self.assert_identical_behavior(
            'POSIXLY_CORRECT=; set -o | grep posix')

    def test_unset_disables_posix(self):
        self.assert_identical_behavior(
            'POSIXLY_CORRECT=1; unset POSIXLY_CORRECT; set -o | grep posix')

    def test_reassignment_keeps_value(self):
        self.assert_identical_behavior(
            'POSIXLY_CORRECT=1; POSIXLY_CORRECT=2; '
            'set -o | grep posix; echo "[$POSIXLY_CORRECT]"')

    # --- option -> variable ---------------------------------------------

    def test_set_o_posix_binds_y(self):
        self.assert_identical_behavior(
            'set -o posix; echo "[${POSIXLY_CORRECT-UNSET}]"')

    def test_set_o_posix_not_exported(self):
        self.assert_identical_behavior(
            'set -o posix; env | grep POSIXLY || echo NOT-EXPORTED')

    def test_set_o_posix_keeps_existing_value(self):
        self.assert_identical_behavior(
            'POSIXLY_CORRECT=custom; set -o posix; echo "[$POSIXLY_CORRECT]"')

    def test_set_plus_o_posix_unsets(self):
        self.assert_identical_behavior(
            'POSIXLY_CORRECT=1; set +o posix; '
            'echo "[${POSIXLY_CORRECT-UNSET}]"; set -o | grep posix')

    def test_round_trip(self):
        self.assert_identical_behavior(
            'set -o posix; echo "[${POSIXLY_CORRECT-U}]"; '
            'set +o posix; echo "[${POSIXLY_CORRECT-U}]"; set -o | grep posix')

    def test_export_enables_and_exports(self):
        self.assert_identical_behavior(
            'export POSIXLY_CORRECT=1; set -o | grep posix; env | grep POSIXLY')

    # --- SHELLOPTS reflection (cross-release with v0.675) ----------------

    def test_shellopts_lists_posix(self):
        self.assert_identical_behavior(
            'POSIXLY_CORRECT=1; case ":$SHELLOPTS:" in '
            '*:posix:*) echo yes;; *) echo no;; esac')

    # --- temporary-env one-shot (cross-release with v0.669) --------------

    def test_one_shot_builtin_sees_posix(self):
        # A POSIXLY_CORRECT=1 prefix on a builtin flips posix for that command
        # only; the shell reverts afterwards.
        self.assert_identical_behavior(
            'POSIXLY_CORRECT=1 set -o | grep posix; set -o | grep posix')

    # --- startup environment import -------------------------------------

    def test_startup_env_enables_posix(self):
        self.assert_identical_behavior(
            'set -o | grep posix; echo "[$POSIXLY_CORRECT]"',
            env={'POSIXLY_CORRECT': '1'})

    def test_startup_env_empty_enables_posix(self):
        self.assert_identical_behavior(
            'set -o | grep posix', env={'POSIXLY_CORRECT': ''})
