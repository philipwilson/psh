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

READONLY ATTRIBUTE REFUSAL (gate-triage row G17 / FLIP-PINS slot 2.4).  bash 5.3.15 CHANGES line
705, 5.3-alpha
item llllll: "Fixed a bug that allowed attribute changes to readonly variables
that changed the effects of attempted assignments".  ``declare`` / ``typeset``
/ ``local`` REFUSE adding or removing an attribute that changes how assignment
behaves -- ``-i``, ``-l``, ``-u``, ``-a``, ``-A``, ``-n`` and their ``+``
forms -- on a readonly variable: ``<builtin>: NAME: readonly variable``, rc 1,
NOTHING applied (not even a co-specified ``-x``), while ``-x`` / ``+x`` /
``-t`` / ``+t`` / ``-r`` / ``-g`` / ``export`` / bare ``declare R`` still
succeed.  The refusal is keyed on the REQUESTED option, not a computed delta:
5.3.15 refuses the no-op ``declare -ir R=1; declare -i R`` as readily as a real
change.  The one carve-out is ``+n`` against a variable that is NOT a nameref.
The 5.2 series accepted every attribute change on a readonly ("readonly forbids
changing the value, not the metadata"); psh followed 5.3 in slot 2.4, so
``TestReadonlyAttributeRefusal`` below pins both halves as PARITY, in ``-c``,
script-file and stdin modes (D6).  The owner is
``psh/core/scope.py#ScopeManager.check_readonly_attribute_change``.
"""


import pytest
from conformance_framework import ConformanceTest
from divergence_pins import MODES, run_in_mode
from shell_oracle import is_comparable, run_bash, run_psh


def _parity_in_modes(command, *, tmp_path, stderr_has=None):
    """Assert psh and the bash 5.3.15 oracle agree on stdout and exit status
    for ``command`` in all three input modes (D6).

    ``stderr_has`` names the wording fragment BOTH sides must diagnose (the
    shell-name prefix differs, so only the fragment is compared); when it is
    None both sides must stay silent.  Uses the shell-oracle runner only, so
    the anti-spawn guard is satisfied by construction.
    """
    for mode in MODES:
        b = run_in_mode(run_bash, mode, command, tmp_path, "oracle")
        p = run_in_mode(run_psh, mode, command, tmp_path, "psh")
        assert is_comparable(b), b
        assert is_comparable(p), p
        assert (p.stdout, p.returncode) == (b.stdout, b.returncode), (
            f"[{mode}] {command!r}: psh {p.stdout!r} rc={p.returncode} != "
            f"bash {b.stdout!r} rc={b.returncode}")
        if stderr_has is None:
            assert not b.stderr and not p.stderr, (
                f"[{mode}] {command!r} expected silence: "
                f"psh={p.stderr!r} bash={b.stderr!r}")
        else:
            assert stderr_has in b.stderr, (mode, command, b.stderr)
            assert stderr_has in p.stderr, (mode, command, p.stderr)


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


class TestReadonlyAttributeRefusal:
    """A READONLY variable refuses every attribute change that would alter what
    a later assignment DOES; the rest still apply (G17 / FLIP-PINS slot 2.4).

    bash 5.3.15 CHANGES line 705, 5.3-alpha item llllll ("Fixed a bug that
    allowed attribute changes to readonly variables that changed the effects of
    attempted assignments").  Every row is a PARITY pin in ``-c``, script-file
    and stdin modes -- these four were declared divergences at Wave 0.3 and are
    flipped here: ``test_declare_i_on_readonly_refused``,
    ``test_declare_l_on_readonly_refused``,
    ``test_declare_plus_i_on_readonly_integer_refused`` and
    ``test_local_i_on_readonly_local_refused``.  Owner:
    ``psh/core/scope.py#ScopeManager.check_readonly_attribute_change``.
    """

    # -- refused: `declare` --------------------------------------------------

    @pytest.mark.oracle_min("5.3")
    def test_declare_i_on_readonly_refused(self, tmp_path):
        """Was ``test_declare_i_on_readonly_succeeds`` -- the 5.2 premise
        "readonly forbids changing the VALUE, not the metadata"."""
        _parity_in_modes(
            'readonly R=1; declare -i R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_l_on_readonly_refused(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; declare -l R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_u_on_readonly_refused(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; declare -u R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_plus_i_on_readonly_integer_refused(self, tmp_path):
        """REMOVING an assignment-affecting attribute is refused too."""
        _parity_in_modes(
            'declare -ir R=1; declare +i R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_i_no_op_on_readonly_integer_refused(self, tmp_path):
        """The refusal is keyed on the REQUESTED option, not on a delta: -i on
        a readonly that is ALREADY integer changes nothing and still fails."""
        _parity_in_modes(
            'declare -ir R=1; declare -i R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_plus_i_no_op_on_plain_readonly_refused(self, tmp_path):
        """The mirror no-op: +i on a readonly that never had -i."""
        _parity_in_modes(
            'readonly R=1; declare +i R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_a_on_readonly_scalar_refused(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; declare -a R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_A_on_readonly_indexed_array_refused(self, tmp_path):
        """readonly is tested BEFORE the array-kind conversion, so this is
        `readonly variable`, not `cannot convert indexed to associative`."""
        _parity_in_modes(
            'declare -ar R=(a b); declare -A R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_n_on_readonly_refused(self, tmp_path):
        """The value is a VALID name, so bash's nameref-shape diagnostics do
        not preempt the readonly one."""
        _parity_in_modes(
            'readonly R=abc; declare -n R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_i_on_declared_unset_readonly_refused(self, tmp_path):
        _parity_in_modes(
            'declare -r R; declare -i R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_i_on_readonly_special_variable_refused(self, tmp_path):
        _parity_in_modes(
            'declare -i UID; echo "rc=$?"',
            tmp_path=tmp_path, stderr_has="declare: UID: readonly variable")

    # -- refused: nothing else in the command lands either -------------------

    @pytest.mark.oracle_min("5.3")
    def test_refused_command_applies_no_attribute_at_all(self, tmp_path):
        """`declare -xi R` is refused whole: the ALLOWED -x does not land."""
        _parity_in_modes(
            'readonly R=1; declare -xi R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_refusal_does_not_stop_later_operands(self, tmp_path):
        """The arg loop is continue-on-error: S still gets -i and -x."""
        _parity_in_modes(
            'readonly R=1; S=2; declare -xi R S; echo "rc=$?"; '
            'declare -p R; declare -p S',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_refusal_status_is_one_and_visible_to_the_next_command(
            self, tmp_path):
        _parity_in_modes(
            'readonly R=1; declare -i R 2>/dev/null; echo "first=$?"; '
            'echo "second=$?"',
            tmp_path=tmp_path)

    @pytest.mark.oracle_min("5.3")
    def test_refusal_under_errexit_aborts(self, tmp_path):
        _parity_in_modes(
            'set -e; readonly R=1; declare -i R; echo survived',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    # -- refused: nameref resolution and scope -------------------------------

    @pytest.mark.oracle_min("5.3")
    def test_nameref_chain_reports_the_resolved_target(self, tmp_path):
        """-i follows the reference, so the diagnostic names R, not b."""
        _parity_in_modes(
            'readonly R=1; declare -n a=R; declare -n b=a; declare -i b; '
            'echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_plus_n_on_readonly_nameref_refused(self, tmp_path):
        """+n does NOT follow the reference, so the readonly nameref cell
        itself refuses -- and the diagnostic names r."""
        _parity_in_modes(
            'T=1; declare -rn r=T; declare +n r; echo "rc=$?"; declare -p r',
            tmp_path=tmp_path, stderr_has="declare: r: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_plus_ni_on_plain_readonly_refused(self, tmp_path):
        """The +n carve-out is per ATTRIBUTE: the +i alongside it still
        refuses."""
        _parity_in_modes(
            'readonly R=1; declare +ni R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_g_from_function_on_readonly_global_refused(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; f(){ declare -gi R; echo "in=$?"; }; f; '
            'declare -p R',
            tmp_path=tmp_path, stderr_has="declare: R: readonly variable")

    # -- refused: the other spellings label themselves -----------------------

    @pytest.mark.oracle_min("5.3")
    def test_typeset_i_on_readonly_refused_labels_typeset(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; typeset -i R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="typeset: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_typeset_plus_l_on_readonly_refused_labels_typeset(self, tmp_path):
        _parity_in_modes(
            'declare -rl R=AB; typeset +l R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path, stderr_has="typeset: R: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_local_i_on_readonly_local_refused(self, tmp_path):
        """Unit twin: tests/unit/builtins/test_local_builtin.py::
        TestLocalReadonlyRedeclare::test_attrs_only_add_integer_refused;
        golden row local_readonly_attrs_only_add_integer_refused."""
        _parity_in_modes(
            'f(){ local -r x=1; local -i x; echo "rc=$?"; declare -p x; }; f',
            tmp_path=tmp_path, stderr_has="local: x: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_local_l_on_readonly_local_refused(self, tmp_path):
        _parity_in_modes(
            'f(){ local -r x=1; local -l x; echo "rc=$?"; declare -p x; }; f',
            tmp_path=tmp_path, stderr_has="local: x: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_declare_on_readonly_local_labels_declare(self, tmp_path):
        """Same cell, reached through `declare` inside the function."""
        _parity_in_modes(
            'f(){ local -r x=1; declare -i x; echo "rc=$?"; declare -p x; }; f',
            tmp_path=tmp_path, stderr_has="declare: x: readonly variable")

    @pytest.mark.oracle_min("5.3")
    def test_local_i_shadowing_a_readonly_global_refused(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; f(){ local -i R; echo "in=$?"; }; f; declare -p R',
            tmp_path=tmp_path, stderr_has="local: R: readonly variable")

    # -- allowed: attributes that do not change what an assignment does ------

    def test_declare_x_on_readonly_still_allowed(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; declare -x R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path)

    def test_declare_plus_x_on_readonly_still_allowed(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; export R; declare +x R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path)

    def test_declare_t_on_readonly_still_allowed(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; declare -t R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path)

    def test_declare_plus_t_on_readonly_still_allowed(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; declare -t R; declare +t R; echo "rc=$?"; '
            'declare -p R',
            tmp_path=tmp_path)

    def test_declare_r_on_readonly_still_allowed(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; declare -r R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path)

    def test_declare_g_on_readonly_still_allowed(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; declare -g R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path)

    @pytest.mark.oracle_min("5.3")
    def test_plus_n_on_plain_readonly_allowed(self, tmp_path):
        """The carve-out: bash drops a +n that has no nameref to remove."""
        _parity_in_modes(
            'readonly R=1; declare +n R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path)

    @pytest.mark.oracle_min("5.3")
    def test_plus_nx_on_plain_readonly_allowed(self, tmp_path):
        _parity_in_modes(
            'readonly R=1; export R; declare +nx R; echo "rc=$?"; '
            'declare -p R',
            tmp_path=tmp_path)

    def test_integer_through_nameref_to_writable_target_allowed(self, tmp_path):
        """The readonly is on the nameref cell r, not on its target T, so -i
        (which follows the reference) lands on T."""
        _parity_in_modes(
            'T=1; declare -rn r=T; declare -i r; echo "rc=$?"; declare -p T',
            tmp_path=tmp_path)

    def test_readonly_and_integer_in_one_command_allowed(self, tmp_path):
        """The variable is not yet readonly when the command is applied."""
        _parity_in_modes(
            'R=1; declare -ri R; echo "rc=$?"; declare -p R',
            tmp_path=tmp_path)

    def test_local_x_on_readonly_local_still_allowed(self, tmp_path):
        _parity_in_modes(
            'f(){ local -r x=1; local -x x; echo "rc=$?"; declare -p x; }; f',
            tmp_path=tmp_path)


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
