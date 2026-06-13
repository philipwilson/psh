"""Conformance tests for command-prefix assignment restore semantics.

Pins the Tier B10a fix (2026-06-13) of B2's pinned quirk: after
``W=1 true`` a previously-UNSET variable must return to UNSET — psh used
to leave it set-but-empty because the apply_prefix snapshot went through
``state.get_variable()``'s ``''`` default, which cannot represent unset.
The whole probe matrix (bash 5.2) is pinned here.

Deliberately NOT pinned to bash: ``W=1 :`` — psh implements the POSIX
special-builtin persistence rule (the assignment persists), which bash
only does in ``--posix`` mode; that documented choice is unchanged and
covered by the existing assignment batteries.
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
