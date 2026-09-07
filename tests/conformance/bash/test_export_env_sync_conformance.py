"""Exported-variable environment-sync conformance (pinned to bash 5.3.15).

Probe battery: tmp/probe_env_sync.sh / tmp/probe2.sh / tmp/probe3.sh
(2026-06-13, Tier B10b). The defining behavior: a plain reassignment of
an export-attributed variable updates the environment the next child
sees — the assignment itself syncs, not just the ``export`` builtin.
The matrix covers reassignment, ``+=``, locals shadowing exports,
unset, declared-but-unset exports, arrays (never exported), attribute
add/remove, allexport interplay, and prefix-assignment restore.

``printenv NAME`` is the child's-eye view of the environment in every
case (exit 1 when the entry is absent).

READONLY ATTRIBUTE REFUSAL ON BASH 5.3 (CHANGES 5.3-alpha section 1 item
llllll: "Fixed a bug that allowed attribute changes to readonly variables
that changed the effects of attempted assignments").  Probed on 5.3.15 in
-c, script-file and stdin modes: ``declare``/``local`` REFUSE adding or
removing an attribute that changes how assignment behaves (``-i``, ``-l``,
``-u``, ``-a``, ``-A``, ``-n`` and their ``+`` forms) on a readonly
variable -- ``declare: R: readonly variable``, rc 1, attributes unchanged --
while ``-x`` / ``-t`` / ``-r`` / ``export`` / bare ``declare R`` still
succeed.  bash 5.2 accepted every attribute change on a readonly ("readonly
forbids changing the value, not the metadata"), and psh still does
(``psh/core/scope.py#ScopeManager.apply_attribute``).  The refused half is
pinned BOTH SIDES in ``TestExportAttributeLifecycle`` as declared
divergences: bash 5.3 semantics; psh to follow in slot 2.4, which flips
each row to a parity pin; the allowed half is pinned as parity.  Gate
triage node family C242 (Wave 0.3).
"""


import pytest
from conformance_framework import ConformanceTest
from divergence_pins import assert_declared_divergence


def _refused_by_bash_53(command, *, bash, psh, tmp_path):
    """Slot 2.4 both-sides pin in -c, script-file and stdin modes (D6):
    bash 5.3.15 refuses with a diagnostic, psh silently succeeds.  See
    tests/conformance/divergence_pins.py.
    """
    assert_declared_divergence(command, bash=bash, psh=psh,
                               tmp_path=tmp_path, slot="2.4",
                               stderr="bash", stderr_has="readonly variable")


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

    # -- bash 5.3 readonly attribute refusal (CHANGES 5.3-alpha 1.llllll):
    #    refused half = declared divergences (slot 2.4 flips), allowed
    #    half = parity. Values are the 5.3.15 probes of 2026-09-06. -------

    @pytest.mark.oracle_min("5.3")
    def test_declare_i_on_readonly_refused_by_bash_53(self, tmp_path):
        # Was test_declare_i_on_readonly_succeeds ("readonly forbids
        # changing the VALUE, not the metadata" -- the 5.2 premise).
        # bash 5.3.15: rc 1, attribute NOT added; psh: rc 0, -i added.
        _refused_by_bash_53(
            'readonly R=1; declare -i R; echo "rc=$?"; declare -p R',
            bash=('rc=1\ndeclare -r R="1"\n', 0),
            psh=('rc=0\ndeclare -ir R="1"\n', 0), tmp_path=tmp_path)

    @pytest.mark.oracle_min("5.3")
    def test_declare_l_on_readonly_refused_by_bash_53(self, tmp_path):
        _refused_by_bash_53(
            'readonly R=1; declare -l R; echo "rc=$?"; declare -p R',
            bash=('rc=1\ndeclare -r R="1"\n', 0),
            psh=('rc=0\ndeclare -rl R="1"\n', 0), tmp_path=tmp_path)

    @pytest.mark.oracle_min("5.3")
    def test_declare_plus_i_on_readonly_integer_refused_by_bash_53(
            self, tmp_path):
        # Removing an assignment-affecting attribute is refused too.
        _refused_by_bash_53(
            'declare -ir R=1; declare +i R; echo "rc=$?"; declare -p R',
            bash=('rc=1\ndeclare -ir R="1"\n', 0),
            psh=('rc=0\ndeclare -r R="1"\n', 0), tmp_path=tmp_path)

    @pytest.mark.oracle_min("5.3")
    def test_local_i_on_readonly_local_refused_by_bash_53(self, tmp_path):
        # The `local` twin (unit pin: tests/unit/builtins/test_local_builtin
        # .py::test_attrs_only_add_integer_allowed; golden
        # local_readonly_attrs_only_add_integer_ok is psh_only).
        _refused_by_bash_53(
            'f(){ local -r x=1; local -i x; echo "rc=$?"; declare -p x; }; f',
            bash=('rc=1\ndeclare -r x="1"\n', 0),
            psh=('rc=0\ndeclare -ir x="1"\n', 0), tmp_path=tmp_path)

    def test_declare_x_on_readonly_still_allowed(self):
        # The allowed half: -x does not change assignment semantics.
        self.assert_identical_behavior(
            'readonly R=1; declare -x R; echo "rc=$?"; declare -p R')

    def test_declare_t_on_readonly_still_allowed(self):
        self.assert_identical_behavior(
            'readonly R=1; declare -t R; echo "rc=$?"; declare -p R')

    def test_local_x_on_readonly_local_still_allowed(self):
        self.assert_identical_behavior(
            'f(){ local -r x=1; local -x x; echo "rc=$?"; declare -p x; }; f')


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


class TestExportPrintListing(ConformanceTest):
    """`export -p` (and bare `export`) list exported variables, INCLUDING a
    declared-but-unset export as `declare -x NAME` with no value — the old
    env-dict iteration dropped it (reappraisal #14)."""

    def test_valueless_export_listed(self):
        self.assert_identical_behavior('export NOVAL; export -p | grep NOVAL')

    def test_valueless_export_bare_export(self):
        self.assert_identical_behavior('export NOVAL2; export | grep NOVAL2')

    def test_valued_export_listed(self):
        self.assert_identical_behavior('export V=1; export -p | grep "^declare -x V="')

    def test_multi_attribute_export(self):
        self.assert_identical_behavior('declare -ix N=5; export -p | grep " N="')

    def test_valueless_then_assigned(self):
        self.assert_identical_behavior(
            'export FOO; FOO=bar; export -p | grep "^declare -x FOO="')

    def test_export_p_escapes_value(self):
        self.assert_identical_behavior(
            "export Q='a\"b'; export -p | grep '^declare -x Q='")

    def test_named_export_p_prints_nothing(self):
        # `export -p NAME` treats NAME as an export operand, not a print target.
        self.assert_identical_behavior('export ZZQ; export -p ZZQ; echo end')
