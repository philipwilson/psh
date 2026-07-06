"""Conformance tests for command-prefix assignment restore semantics.

Pins the Tier B10a fix (2026-06-13) of B2's pinned quirk: after
``W=1 true`` a previously-UNSET variable must return to UNSET — psh used
to leave it set-but-empty because the apply_prefix snapshot went through
``state.get_variable()``'s ``''`` default, which cannot represent unset.
The whole probe matrix (bash 5.2) is pinned here.

``W=1 :`` (a prefix before a POSIX special builtin) is now mode-aware
(F9, 2026-07-06): temporary in default mode (matching bash), persisting
ONLY under ``set -o posix``. psh previously persisted it in BOTH modes — a
non-conformant divergence the execution-subsystem review flagged. The
mode-aware behavior is pinned by the exec_p1a_* golden cases and
tests/integration/test_special_builtin_modes.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestPrefixAssignmentRestore(ConformanceTest):
    """NAME=value cmd is temporary — and restores the EXACT prior state."""

    def test_unset_variable_returns_to_unset(self):
        """The headline fix: ${W+yes} stays empty after `W=1 true`."""
        self.assert_identical_behavior(
            'W=1 true; echo "${W+yes}${W-unset}"')

    def test_set_variable_restores_old_value(self):
        self.assert_identical_behavior('W=0; W=1 true; echo "$W"')

    def test_set_but_empty_variable_stays_set(self):
        """W= (empty but SET) is restored to set-but-empty, not unset."""
        self.assert_identical_behavior(
            'W=; W=1 true; echo "${W+setempty}${W-unset}"')

    def test_exported_variable_restores_value_and_export(self):
        self.assert_identical_behavior(
            'export W=0; W=1 true; echo "$W"; env | grep -c "^W="')

    def test_restore_happens_after_failing_command(self):
        self.assert_identical_behavior(
            'unset W; W=1 false; echo "rc=$? ${W+yes}${W-unset}"')

    def test_duplicate_prefix_first_snapshot_wins(self):
        self.assert_identical_behavior(
            'W=1 W=2 true; echo "${W+yes}${W-unset}"')

    def test_readonly_prefix_skips_and_command_runs(self):
        """bash: the readonly error is reported, the command still runs
        with status 0, and the variable keeps its value. (stderr text
        prefixes differ; the brace group suppresses the SHELL-emitted
        assignment error so the visible behavior is compared.)"""
        self.assert_identical_behavior(
            'readonly R=5; { R=6 true; } 2>/dev/null; echo "after=$? R=$R"')

    def test_unset_local_in_function_restored_to_unset(self):
        self.assert_identical_behavior(
            'f() { local L; unset L; L=1 true; '
            'echo "${L+yes}${L-unset}"; }; f')


class TestPrefixAssignmentReachesCommandEnvironment(ConformanceTest):
    """NAME=value cmd places NAME in cmd's environment (exported for it).

    Pins H5 (reappraisal #7): a prefix assignment was not reaching the
    environment of a command in a pipeline (nor the ``env`` builtin even
    outside a pipeline) — psh set the variable as a plain shell var, which
    ``sync_exports_to_environment`` then dropped from ``shell.env`` because
    it carried no EXPORT attribute. bash exports the prefix for the command
    only (the variable is not exported afterwards).
    """

    def test_prefix_in_environment_of_pipeline_member(self):
        self.assert_identical_behavior('FOO=bar env | grep "^FOO="')

    def test_multiple_prefixes_in_pipeline_member(self):
        self.assert_identical_behavior(
            "A=1 B=2 env | grep -E '^(A|B)=' | sort")

    def test_prefix_in_builtin_pipeline_member(self):
        self.assert_identical_behavior('FOO=bar printenv FOO | cat')

    def test_prefix_through_two_pipe_stages(self):
        self.assert_identical_behavior('FOO=bar env | cat | grep "^FOO="')

    def test_prefix_does_not_persist_after_pipeline(self):
        self.assert_identical_behavior(
            'FOO=bar env | grep "^FOO=" >/dev/null; echo "[${FOO+set}]"')

    def test_prefix_visible_to_external_no_pipeline(self):
        self.assert_identical_behavior('FOO=bar env | grep "^FOO="')

    def test_prefix_reaches_explicit_external(self):
        self.assert_identical_behavior(
            'X=temp bash -c "echo inchild=$X"; echo "[${X+set}]"')

    def test_previously_unexported_var_stays_unexported(self):
        """A plain var prefixed onto a command is `declare --` afterwards,
        not `declare -x` — the temporary export must be taken back off."""
        self.assert_identical_behavior(
            'Y=set; Y=tmp true; declare -p Y')

    def test_previously_exported_var_stays_exported(self):
        self.assert_identical_behavior(
            'export Z=1; Z=2 true; declare -p Z')

    def test_function_prefix_in_pipeline(self):
        self.assert_identical_behavior(
            'f(){ echo "fn sees $V"; }; V=hi f | cat')
