"""The variable-read result rejects mutation — MEDIUM-5, slot 4B.1.

`ScopeManager.lookup()` is the tri-state READ authority; every WRITE goes
through `VariableStore` by identifier. Before this suite the read result did
not enforce that split: its fields were plain writable slots and it handed out
the live `Variable` cell as ``.binding``, so an attribute assignment on a read
result could poison a process-wide singleton, bypass the readonly guard, mutate
a nameref's target, and desync ``state.env`` from what the shell reads — all
without a store transaction and without firing the ``variable_changed``
observer.

These pins lock the read result as immutable and the four authorities
(readonly / nameref / observer / export) as coherent, along the
MUTATION SURFACE x AUTHORITY GUARD axis: each mutation surface (fresh VALUE
instance / MISSING singleton / PRESENT_UNSET singleton, x each public name) is
attempted against each authority's guarantee.

THREAT MODEL (ruled, slot 4B.1 ruling (c)). These pins prove HONEST-CALLER
ACCIDENT: plain attribute assignment to a public name raises, on fresh
instances and on both shared singletons alike, and a poisoning attempt leaves
the next read clean. Declared OUT OF SCOPE as deliberate circumvention:
``object.__setattr__``, module rebinding, and direct writes to the private
``_status`` / ``_value`` slots. That third clause is WEAKER than the frozen-
dataclass surface used for pattern nodes (slot 3.2, MEDIUM-6); the alternatives
that would close it were priced and declined on measured cost (raising
``__setattr__`` 1.081x, frozen dataclass 1.13x end-to-end on ``lookup()``).
``TestDeclaredThreatModelBoundary`` commits that boundary as a LABELLED
CONTROL, so the declared limit is visible in the suite rather than only in
prose — strengthening it later is a deliberate edit that flips a control.

Tri-state SEMANTICS are not this suite's subject and are unchanged: the
classification rows live in `test_variable_lookup.py`, the tombstone rows in
`test_scope_tombstones.py`, and the masked-special row in
`test_dynamic_special_masking.py`. This suite varies the MUTATION dimension
over them.
"""

import pytest

from psh.core.scope import ScopeManager
from psh.core.variable_lookup import LookupStatus, VariableLookup
from psh.shell import Shell

# --- the mutation-surface axis --------------------------------------------
# Every lookup result a consumer can hold: a freshly built VALUE, and the two
# shared singletons. A rule that holds for fresh instances but not for the
# shared ones is exactly the _MISSING poisoning defect, so both are walked.
SURFACES = ("fresh_value", "missing_singleton", "present_unset_singleton")

# The public read surface. `status`/`value` were writable slots before this
# slot; `is_set`/`is_present` were already setter-less properties and are
# carried so the axis is walked in full rather than only where it was broken.
PUBLIC_NAMES = ("status", "value", "is_set", "is_present")

EXPECTED = {
    "fresh_value": (LookupStatus.VALUE, "v"),
    "missing_singleton": (LookupStatus.MISSING, None),
    "present_unset_singleton": (LookupStatus.PRESENT_UNSET, None),
}


def make(surface):
    """Build one lookup result per surface, through the public factories."""
    if surface == "fresh_value":
        return VariableLookup.of_value("v")
    if surface == "missing_singleton":
        return VariableLookup.missing()
    return VariableLookup.present_unset()


def assert_intact(result, surface):
    """The surface still reports exactly what it did before the attempt.

    Agreement form against the declared expectation rather than a re-read of
    the same object: for the shared singletons a re-read would show a landed
    mutation just as happily as it shows a rejected one.
    """
    assert (result.status, result.value) == EXPECTED[surface]


class TestMutationSurfaceRejected:
    """Every public name, on every surface, rejects assignment and deletion —
    and the instances stay closed.

    CARRIED SUCCESSORS (green at base — NOT defect evidence): the six
    `test_new_attribute_rejected[*]` and `test_no_instance_dict[*]` cells were
    already green before this slot, because `__slots__` closed instances then
    too. They carry the retired `test_slots_closed_no_dict` guard forward from
    `test_variable_lookup.py`, widened to all three surfaces. Labelled so this
    class's red-on-base count is not read as though every cell in it evidenced
    the defect: the twelve genuinely red-on-base cells are the assignment and
    deletion attempts on `status`/`value`, which were plain writable slots at
    base.
    """

    @pytest.mark.parametrize("name", PUBLIC_NAMES)
    @pytest.mark.parametrize("surface", SURFACES)
    def test_assignment_rejected(self, surface, name):
        result = make(surface)
        with pytest.raises(AttributeError):
            setattr(result, name, "MUTATED")
        assert_intact(result, surface)

    @pytest.mark.parametrize("name", PUBLIC_NAMES)
    @pytest.mark.parametrize("surface", SURFACES)
    def test_deletion_rejected(self, surface, name):
        result = make(surface)
        with pytest.raises(AttributeError):
            delattr(result, name)
        assert_intact(result, surface)

    @pytest.mark.parametrize("surface", SURFACES)
    def test_new_attribute_rejected(self, surface):
        """Instances stay CLOSED — no ad-hoc state can be grown on a result."""
        result = make(surface)
        with pytest.raises(AttributeError):
            result.extra = 1
        assert_intact(result, surface)

    @pytest.mark.parametrize("surface", SURFACES)
    def test_no_instance_dict(self, surface):
        assert not hasattr(make(surface), "__dict__")


class TestBindingSurfaceOmitted:
    """There is no path from a lookup result to a live `Variable` cell.

    The exit criterion is met STRUCTURALLY rather than defensively: the field
    that leaked the live cell is gone, so there is no mutation surface left on
    it to guard. Consumers that need attributes or scope identity ask the
    write engine's own surface (`get_variable_object` /
    `get_declared_variable_object`), which is where the two callers the old
    docstring named — ``${x@a}`` and ``declare -p`` — always went anyway.
    """

    @pytest.mark.parametrize("surface", SURFACES)
    def test_result_exposes_no_binding(self, surface):
        assert not hasattr(make(surface), "binding")

    def test_of_value_takes_no_binding_argument(self):
        with pytest.raises(TypeError):
            VariableLookup.of_value("v", object())

    def test_present_unset_takes_no_binding_argument(self):
        with pytest.raises(TypeError):
            VariableLookup.present_unset(object())


class TestMissingSingletonNotPoisonable:
    """The shared singletons are safe BECAUSE they are immutable.

    Sharing was never the defect — mutability was. A frozen shared constant is
    safe on the same argument that makes `True` and `None` safe to share, so
    misses stay allocation-free. Each cell carries the follow-up assertion that
    a SUBSEQUENT read is clean: proving the attempt raised is not the same as
    proving nothing landed.
    """

    def test_mutating_a_miss_raises_and_the_next_miss_is_clean(self):
        mgr = ScopeManager()
        miss = mgr.lookup("unset_a")
        with pytest.raises(AttributeError):
            miss.status = LookupStatus.VALUE
        with pytest.raises(AttributeError):
            miss.value = "POISON"
        other = mgr.lookup("a_different_unset_name")
        assert other.status is LookupStatus.MISSING
        assert other.value is None
        assert other.is_set is False

    def test_mutating_a_declared_unset_result_leaves_the_next_read_clean(self):
        mgr = ScopeManager()
        mgr.push_scope("f")
        try:
            mgr.create_local("x")  # bare `local x` -> PRESENT_UNSET
            first = mgr.lookup("x")
            with pytest.raises(AttributeError):
                first.value = "POISON"
            mgr.create_local("y")
            assert mgr.lookup("y").status is LookupStatus.PRESENT_UNSET
            assert mgr.lookup("y").value is None
        finally:
            mgr.pop_scope()

    def test_poisoning_attempt_does_not_fire_a_parameter_operator(self):
        """End-to-end: the poisoning consequence that made MEDIUM-5 real was
        an unrelated unset name making `${u+w}` expand."""
        shell = Shell()
        try:
            miss = shell.state.scope_manager.lookup("unset_probe")
            with pytest.raises(AttributeError):
                miss.status = LookupStatus.VALUE
            assert shell.run_command('test -z "${SOME_UNSET_NAME+FIRED}"') == 0
        finally:
            shell.close()

    def test_poisoning_attempt_cannot_cross_two_sequential_shells(self):
        """A process-global singleton outlives any one shell, so the pin has to
        outlive one too: shell A's attempt must not reach shell B."""
        first = Shell()
        try:
            miss = first.state.scope_manager.lookup("unset_in_first")
            with pytest.raises(AttributeError):
                miss.status = LookupStatus.VALUE
        finally:
            first.close()

        second = Shell()
        try:
            assert second.run_command('test -z "${TOTALLY_UNSET+FIRED}"') == 0
            assert (second.state.scope_manager.lookup("another_unset").status
                    is LookupStatus.MISSING)
        finally:
            second.close()


class TestAuthorityCoherence:
    """The exit criterion's four authorities, each as a (M) mutation-attempt
    cell and a (C) legitimate-path coherence cell.

    The (C) cells are must-holds: this slot froze the READ return type and must
    not have weakened the write engine to do it.
    """

    # -- readonly ----------------------------------------------------------
    def test_readonly_value_unreachable_from_a_lookup_result(self):
        shell = Shell()
        try:
            shell.run_command("readonly RO=original")
            result = shell.state.scope_manager.lookup("RO")
            assert not hasattr(result, "binding")
            for name in PUBLIC_NAMES:
                with pytest.raises(AttributeError):
                    setattr(result, name, "hacked")
            assert shell.state.get_variable("RO") == "original"
        finally:
            shell.close()

    def test_readonly_write_still_refused_through_the_store(self):
        from psh.core.exceptions import ReadonlyVariableError
        shell = Shell()
        try:
            shell.run_command("readonly RO=original")
            assert shell.run_command("RO=viaShell") == 1
            with pytest.raises(ReadonlyVariableError):
                shell.state.scope_manager.store.assign("RO", "viaStore")
            assert shell.state.get_variable("RO") == "original"
        finally:
            shell.close()

    # -- nameref -----------------------------------------------------------
    def test_nameref_target_unreachable_from_a_lookup_result(self):
        """`lookup()` derefs to the FINAL cell, so a leaked binding would have
        mutated the TARGET with none of the write path's guards."""
        shell = Shell()
        try:
            shell.run_command("target=hi")
            shell.run_command("declare -n ref=target")
            result = shell.state.scope_manager.lookup("ref")
            assert result.value == "hi"
            assert not hasattr(result, "binding")
            for name in PUBLIC_NAMES:
                with pytest.raises(AttributeError):
                    setattr(result, name, "clobbered")
            assert shell.state.get_variable("target") == "hi"
        finally:
            shell.close()

    def test_nameref_legitimate_write_still_lands_and_still_guards(self):
        shell = Shell()
        try:
            shell.run_command("target=hi")
            shell.run_command("declare -n ref=target")
            shell.run_command("ref=viaRef")
            assert shell.state.get_variable("target") == "viaRef"
            assert shell.state.get_variable("ref") == "viaRef"
            shell.run_command("readonly target")
            assert shell.run_command("ref=blocked") == 1
            assert shell.state.get_variable("target") == "viaRef"
        finally:
            shell.close()

    # -- observer ----------------------------------------------------------
    def test_no_read_can_change_without_notifying_the_observer(self):
        """The observer drives `_materialize_env_name`; a read change that
        skipped it is how `state.env` went stale."""
        shell = Shell()
        try:
            shell.run_command("export EX=one")
            fired = []
            manager = shell.state.scope_manager
            original = manager._notify_variable_changed

            def spy(name, *args, **kwargs):
                fired.append(name)
                return original(name, *args, **kwargs)

            manager._notify_variable_changed = spy
            result = manager.lookup("EX")
            for name in PUBLIC_NAMES:
                with pytest.raises(AttributeError):
                    setattr(result, name, "two")
            assert shell.state.get_variable("EX") == "one"
            assert fired == []
        finally:
            shell.close()

    def test_legitimate_write_fires_the_observer(self):
        shell = Shell()
        try:
            shell.run_command("export EX=one")
            fired = []
            manager = shell.state.scope_manager
            original = manager._notify_variable_changed

            def spy(name, *args, **kwargs):
                fired.append(name)
                return original(name, *args, **kwargs)

            manager._notify_variable_changed = spy
            shell.run_command("EX=two")
            assert "EX" in fired
            assert shell.state.get_variable("EX") == "two"
            assert shell.state.env.get("EX") == "two"
        finally:
            shell.close()

    # -- export ------------------------------------------------------------
    def test_env_and_shell_agree_after_mutation_attempts(self):
        shell = Shell()
        try:
            shell.run_command("export EX=one")
            result = shell.state.scope_manager.lookup("EX")
            for name in PUBLIC_NAMES:
                with pytest.raises(AttributeError):
                    setattr(result, name, "two")
            assert shell.state.get_variable("EX") == shell.state.env.get("EX")
        finally:
            shell.close()

    def test_env_stays_coherent_across_a_legitimate_sequence(self):
        shell = Shell()
        try:
            for command in ("export EX=one", "EX=two", "export EX=three"):
                shell.run_command(command)
                assert shell.state.get_variable("EX") == shell.state.env.get("EX")
            shell.run_command("unset EX")
            assert shell.state.env.get("EX") is None
            shell.run_command("export EX=four")
            assert shell.state.get_variable("EX") == shell.state.env.get("EX") == "four"
        finally:
            shell.close()


class TestCompositionCells:
    """Fixes compose: the immutable result meets each neighbouring mechanism."""

    def test_mutation_attempt_across_a_two_level_nameref_chain(self):
        """A chain derefs to the final cell; neither link may be reachable."""
        shell = Shell()
        try:
            shell.run_command("final=deep")
            shell.run_command("declare -n mid=final")
            shell.run_command("declare -n outer=mid")
            result = shell.state.scope_manager.lookup("outer")
            assert result.value == "deep"
            assert not hasattr(result, "binding")
            for name in PUBLIC_NAMES:
                with pytest.raises(AttributeError):
                    setattr(result, name, "clobbered")
            assert shell.state.get_variable("final") == "deep"
            assert shell.state.get_variable("mid") == "deep"
        finally:
            shell.close()

    def test_mutation_attempt_on_a_readonly_export_leaves_env_coherent(self):
        """readonly x export: the refused write must not half-apply."""
        shell = Shell()
        try:
            shell.run_command("export RX=one")
            shell.run_command("readonly RX")
            result = shell.state.scope_manager.lookup("RX")
            for name in PUBLIC_NAMES:
                with pytest.raises(AttributeError):
                    setattr(result, name, "two")
            assert shell.run_command("RX=viaShell") == 1
            assert shell.state.get_variable("RX") == "one"
            assert shell.state.env.get("RX") == "one"
        finally:
            shell.close()

    def test_computed_special_read_is_frozen_too(self):
        """A computed special has no stored cell — it is served from the
        special registry — so its result reaches the type by a different route
        and must be just as immutable."""
        shell = Shell()
        try:
            manager = shell.state.scope_manager
            assert manager._special.is_computed("SECONDS")
            result = manager.lookup("SECONDS")
            assert result.status is LookupStatus.VALUE
            assert not hasattr(result, "binding")
            for name in PUBLIC_NAMES:
                with pytest.raises(AttributeError):
                    setattr(result, name, "999999")
            assert manager.get_variable("SECONDS") != "999999"
        finally:
            shell.close()

    def test_masked_special_still_reads_unset_through_a_frozen_result(self):
        """`local RANDOM; unset RANDOM` shadows the special: the tombstone must
        still stop the read rather than resurrect the generator."""
        manager = ScopeManager()
        manager.push_scope("f")
        try:
            manager.create_local("RANDOM", "5")
            manager.unset_variable("RANDOM")
            result = manager.lookup("RANDOM")
            assert result.is_set is False
            with pytest.raises(AttributeError):
                result.value = "resurrected"
            assert manager.lookup("RANDOM").is_set is False
        finally:
            manager.pop_scope()


class TestRepresentationSemantics:
    """The declared shape of the immutable result (slot 4B.1 ruling (a)/(c))."""

    def test_missing_is_a_shared_singleton(self):
        assert VariableLookup.missing() is VariableLookup.missing()

    def test_present_unset_is_a_shared_singleton(self):
        """New under this slot: with no binding to carry, a declared-unset
        result holds no per-instance data, so it stops allocating."""
        assert VariableLookup.present_unset() is VariableLookup.present_unset()

    def test_equality_is_status_and_value(self):
        assert VariableLookup.of_value("v") == VariableLookup.of_value("v")
        assert VariableLookup.of_value("v") != VariableLookup.of_value("w")
        assert VariableLookup.missing() != VariableLookup.present_unset()

    def test_all_declared_unset_results_are_equal(self):
        """Declared representation-detail change: the binding used to
        differentiate two PRESENT_UNSET results. Nothing compared lookup
        results whole, so this flips no behaviour — it is pinned forward.

        The two instances are built through the constructor, not through
        `lookup()`: `lookup()` hands back the shared constant, so a cell that
        went through it would be comparing an object with ITSELF and would
        stay green even under an identity `__eq__` — vacuous for the rule it
        claims to pin. (Found by the M8-5 lock, which is what that lock is
        for.) The `lookup()` pair is kept as the second assertion, where
        sharing makes equality hold for the stronger reason.
        """
        first = VariableLookup(LookupStatus.PRESENT_UNSET, None)
        second = VariableLookup(LookupStatus.PRESENT_UNSET, None)
        assert first is not second
        assert first == second

        manager = ScopeManager()
        manager.push_scope("f")
        try:
            manager.create_local("x")
            manager.create_local("y")
            assert manager.lookup("x") == manager.lookup("y")
        finally:
            manager.pop_scope()

    def test_repr_shows_status_and_value_and_no_binding(self):
        text = repr(VariableLookup.of_value("v"))
        assert "VALUE" in text
        assert "'v'" in text
        assert "binding" not in text

    def test_results_stay_unhashable(self):
        """Preserved, not changed: defining `__eq__` already set `__hash__` to
        None before this slot. Pinned so it reads as a decision."""
        with pytest.raises(TypeError):
            hash(VariableLookup.of_value("v"))


class TestDeclaredThreatModelBoundary:
    """LABELLED CONTROL — this documents a declared LIMIT, it is not a proof.

    The threat model covers honest-caller accident. A direct write to the
    private slot is deliberate circumvention and is declared OUT OF SCOPE,
    alongside `object.__setattr__` and module rebinding. This cell makes that
    boundary visible in the suite rather than only in prose: it asserts the
    circumvention SUCCEEDS today. Closing the hole later (a raising
    `__setattr__`, or a frozen dataclass — both priced and declined on
    measured cost) is a deliberate edit that flips this control, which is
    exactly the intent.
    """

    def test_control_private_slot_write_is_declared_out_of_scope(self):
        result = VariableLookup.of_value("v")
        result._value = "CIRCUMVENTED"
        assert result.value == "CIRCUMVENTED"
