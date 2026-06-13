"""Exported-variable environment-sync conformance (pinned to bash 5.2).

Probe battery: tmp/probe_env_sync.sh / tmp/probe2.sh / tmp/probe3.sh
(2026-06-13, Tier B10b). The defining behavior: a plain reassignment of
an export-attributed variable updates the environment the next child
sees — the assignment itself syncs, not just the ``export`` builtin.
The matrix covers reassignment, ``+=``, locals shadowing exports,
unset, declared-but-unset exports, arrays (never exported), attribute
add/remove, allexport interplay, and prefix-assignment restore.

``printenv NAME`` is the child's-eye view of the environment in every
case (exit 1 when the entry is absent).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestExportedAssignmentSync(ConformanceTest):
    """Assignments to export-attributed variables reach children."""

    def test_plain_reassignment_updates_environment(self):
        self.assert_identical_behavior(
            'export FOO=old; FOO=new; printenv FOO')

    def test_append_updates_environment(self):
        self.assert_identical_behavior(
            'export FOO=old; FOO+=new; printenv FOO')

    def test_assign_empty_keeps_entry_empty(self):
        self.assert_identical_behavior(
            'export FOO=x; FOO=; printenv FOO; echo "rc=$?"')

    def test_declare_x_then_reassign(self):
        self.assert_identical_behavior(
            'declare -x FOO=old; FOO=new; printenv FOO')

    def test_path_reassignment_visible_to_child(self):
        self.assert_identical_behavior(
            'PATH=/usr/bin:/bin; printenv PATH')

    def test_arithmetic_assignment_syncs(self):
        self.assert_identical_behavior(
            'export FOO=1; : $((FOO=42)); printenv FOO')

    def test_default_assignment_expansion_syncs(self):
        self.assert_identical_behavior(
            'export FOO; : ${FOO:=defaulted}; printenv FOO; echo "rc=$?"')

    def test_read_into_exported_syncs(self):
        self.assert_identical_behavior(
            'export FOO=old; read FOO <<< "fromread"; printenv FOO')

    def test_for_loop_variable_syncs(self):
        self.assert_identical_behavior(
            'export FOO=old; for FOO in loopval; do printenv FOO; done')

    def test_nameref_write_to_exported_syncs(self):
        self.assert_identical_behavior(
            'export FOO=old; declare -n r=FOO; r=vianref; printenv FOO')


class TestExportAttributeLifecycle(ConformanceTest):
    """Gaining/losing the attribute adds/removes the env entry."""

    def test_unset_removes_entry(self):
        self.assert_identical_behavior(
            'export FOO=x; unset FOO; printenv FOO; echo "rc=$?"')

    def test_unset_clears_attribute_for_later_assignment(self):
        self.assert_identical_behavior(
            'export FOO=a; unset FOO; FOO=b; printenv FOO; echo "rc=$?"')

    def test_export_n_then_reassign_stays_unexported(self):
        self.assert_identical_behavior(
            'export FOO=old; export -n FOO; FOO=new; printenv FOO; echo "rc=$?"')

    def test_valueless_export_of_unset_name_no_entry_until_assigned(self):
        self.assert_identical_behavior(
            'export FOO; printenv FOO; echo "rc=$?"; FOO=now; printenv FOO')

    def test_valueless_export_reads_as_unset(self):
        self.assert_identical_behavior(
            'export FOO; echo "${FOO-u}"')

    def test_valueless_export_of_existing_readonly(self):
        self.assert_identical_behavior(
            'readonly R=1; export R; printenv R; declare -p R')

    def test_declare_i_on_readonly_succeeds(self):
        # readonly forbids changing the VALUE, not the metadata
        self.assert_identical_behavior(
            'readonly R=1; declare -i R; echo "rc=$?"')


class TestLocalsShadowingExports(ConformanceTest):
    """Function locals shadowing exported variables (bash semantics)."""

    def test_local_with_value_shadows_in_environment(self):
        self.assert_identical_behavior(
            'export FOO=outer; f() { local FOO=inner; printenv FOO; }; f; '
            'printenv FOO')

    def test_local_assigned_later_shadows_in_environment(self):
        self.assert_identical_behavior(
            'export FOO=outer; f() { local FOO; FOO=inner; printenv FOO; }; '
            'f; printenv FOO')

    def test_unvalued_local_leaves_outer_entry_visible(self):
        self.assert_identical_behavior(
            'export FOO=outer; f() { local FOO; printenv FOO; echo "rc=$?"; }; f')

    def test_local_inherits_only_export_attribute(self):
        self.assert_identical_behavior(
            'declare -xi N=5; f() { local N; declare -p N; }; f')

    def test_local_x_entry_removed_on_return(self):
        self.assert_identical_behavior(
            'f() { local -x FOO=loc; printenv FOO; }; f; '
            'printenv FOO; echo "rc=$?"')

    def test_local_of_unexported_global_stays_out_of_env(self):
        self.assert_identical_behavior(
            'FOO=glob; f() { local FOO=loc; printenv FOO; echo "rc=$?"; }; f')

    def test_unvalued_local_reads_as_unset(self):
        self.assert_identical_behavior(
            'f() { local FOO; echo "${FOO-u}"; }; f')

    def test_function_assignment_without_local_syncs_global(self):
        self.assert_identical_behavior(
            'export FOO=old; f() { FOO=infunc; }; f; printenv FOO')

    def test_export_inside_function_is_global(self):
        self.assert_identical_behavior(
            'f() { export FOO=fn; }; f; printenv FOO')


class TestArraysNeverExported(ConformanceTest):
    """bash never places arrays in the environment."""

    def test_exported_name_assigned_array_loses_entry(self):
        self.assert_identical_behavior(
            'export FOO=v; FOO=(a b); printenv FOO; echo "rc=$?"')

    def test_declare_x_array_no_entry(self):
        self.assert_identical_behavior(
            'declare -x ARR=(a b c); printenv ARR; echo "rc=$?"; echo "${ARR[1]}"')


class TestAllexportAndPrefixInterplay(ConformanceTest):
    """set -a and one-shot prefix assignments."""

    def test_allexport_assignment_exports(self):
        self.assert_identical_behavior(
            'set -a; FOO=auto; printenv FOO')

    def test_attribute_survives_allexport_off(self):
        self.assert_identical_behavior(
            'set -a; FOO=auto; set +a; FOO=second; printenv FOO')

    def test_prefix_assignment_is_temporary(self):
        self.assert_identical_behavior(
            'export FOO=old; FOO=tmp printenv FOO; printenv FOO')

    def test_declare_unset_reads_as_unset_then_keeps_attribute(self):
        self.assert_identical_behavior(
            'declare -i NUMBER; echo "${NUMBER-u}"; NUMBER=2+3; echo "$NUMBER"')
