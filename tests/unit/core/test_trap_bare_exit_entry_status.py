"""The owner of "what does a bare ``exit``/``return`` resolve to in a trap".

``TrapManager.bare_status_entry_value`` is the single query behind bash 5.3's
rule (CHANGES 5.3-beta section 3 item q, line 277; NEWS item uu, line 141;
POSIX interp 1602 -- and, for ``return``, CHANGES 5.3-alpha item y, line 370):
a bare ``exit`` or ``return`` at the TOP LEVEL of a trap action resolves to
``$?`` as of trap ENTRY, not to the action's current ``$?``.  The end-to-end
behaviour is pinned against live bash by
``tests/conformance/bash/test_exit_trap_status_precedence_conformance.py``;
these tests drive the owner DIRECTLY with synthetic depths, so the halves of
the rule -- which trap kinds record a status, where "top level" ends, what a
forked compound child does, and that BOTH consumers ask the owner -- stay
pinned even for shapes that are awkward to provoke through a real signal, and
without needing the bash 5.3 oracle.

Closes gate-triage rows G32-G35 (FLIP-PINS slot 2.1, Wave 2).
"""
import pytest


@pytest.fixture
def traps(shell):
    """The TrapManager under test, with no trap action running."""
    tm = shell.trap_manager
    assert tm.bare_status_entry_value is None
    return tm


def _depths(shell):
    return len(shell.state.function_stack), shell.state.source_depth


# --------------------------------------------------------------------------
# Which trap kinds record an entry status
# --------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["EXIT", "USR1", "INT", "ERR", "RETURN"])
def test_status_owning_trap_kinds_record_the_entry_status(traps, kind):
    """EXIT, signal, ERR and RETURN actions all resolve a bare exit to entry.

    bash 5.3.15, three input modes: ``trap 'false; exit' USR1`` /
    ``trap '{ true; exit; }' ERR`` / ``set -T; trap 'false; exit' RETURN``
    each exit with the ENTRY status, not the body's current ``$?``.
    """
    traps._push_trap_action_frame(kind, 7)
    assert traps.bare_status_entry_value == 7


def test_debug_action_keeps_the_current_status(traps):
    """DEBUG is outside interp 1602: a bare exit there keeps ``$?``.

    bash 5.3.15: ``trap 'echo d=$?; true; exit' DEBUG; (exit 4)`` prints d=4
    and exits 0 -- the entry status 4 is visible but does not win.
    """
    traps._push_trap_action_frame("DEBUG", 4)
    assert traps.bare_status_entry_value is None


def test_no_running_action_means_no_entry_status(traps):
    """Outside any trap action a bare exit is plain ``$?``."""
    assert traps.bare_status_entry_value is None


# --------------------------------------------------------------------------
# Where "top level" ends: function depth and source depth
# --------------------------------------------------------------------------

def test_signal_action_at_recorded_depths_is_top_level(traps, shell):
    """Same depths as at entry: compound commands and ``eval`` stay top level.

    ``if`` / ``{ }`` / loops / ``case`` / ``eval`` push neither a function
    frame nor a source frame, so they cannot move this query.
    """
    traps._push_trap_action_frame("USR1", 0)
    assert _depths(shell) == (0, 0)
    assert traps.bare_status_entry_value == 0


def test_function_frame_leaves_a_signal_actions_top_level(traps, shell):
    """A function called FROM the action is not the action's top level.

    bash 5.3.15: ``f() { false; exit; }; trap f USR1; kill -USR1 $$`` exits 1
    (the body's current ``$?``), not the entry status.
    """
    traps._push_trap_action_frame("USR1", 0)
    shell.state.function_stack.append("f")
    try:
        assert traps.bare_status_entry_value is None
    finally:
        shell.state.function_stack.pop()
    assert traps.bare_status_entry_value == 0


def test_source_depth_leaves_a_signal_actions_top_level(traps, shell):
    """A file sourced FROM the action is not the action's top level.

    bash 5.3.15: ``trap '. ./s.sh' USR1`` with ``s.sh`` = ``false; exit``
    exits 1.
    """
    traps._push_trap_action_frame("ERR", 9)
    shell.state.source_depth += 1
    try:
        assert traps.bare_status_entry_value is None
    finally:
        shell.state.source_depth -= 1
    assert traps.bare_status_entry_value == 9


def test_top_level_is_relative_to_the_depths_at_entry(traps, shell):
    """A trap entered INSIDE a function still has a top level of its own.

    The comparison is against the depths recorded at entry, never against
    zero. bash 5.3.15: ``g() { kill -USR1 $$; sleep 0.2; }; trap 'false; exit'
    USR1; g; exit 3`` exits 0 -- the action runs at function depth 1 and its
    own top level is that same depth.
    """
    shell.state.function_stack.append("g")
    shell.state.source_depth += 1
    try:
        traps._push_trap_action_frame("USR1", 0)
        assert traps.bare_status_entry_value == 0
        shell.state.function_stack.append("inner")
        assert traps.bare_status_entry_value is None
        shell.state.function_stack.pop()
        assert traps.bare_status_entry_value == 0
    finally:
        shell.state.function_stack.pop()
        shell.state.source_depth -= 1


def test_returning_below_the_entry_depth_is_not_top_level(traps, shell):
    """Unwinding PAST the entry depth is not the action's top level either.

    An exact match is the invariant, not "at most the entry depth": a bare
    exit reached after the frame's own function has already been left cannot
    be the action's top level.
    """
    shell.state.function_stack.append("outer")
    try:
        traps._push_trap_action_frame("USR1", 0)
        assert traps.bare_status_entry_value == 0
        shell.state.function_stack.pop()
        assert traps.bare_status_entry_value is None
    finally:
        if shell.state.function_stack:
            shell.state.function_stack.pop()


# --------------------------------------------------------------------------
# The EXIT trap ignores those depths
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bump", ["function", "source"])
def test_exit_action_ignores_function_and_source_depth(traps, shell, bump):
    """EXIT is the exception to the top-level restriction.

    bash 5.3.15, three input modes: ``f() { false; exit; }; trap f EXIT;
    exit 3`` exits 3, and the sourced-file spelling exits 3 too -- an EXIT
    action's bare exit resolves to the entry status wherever it sits.
    """
    traps._push_trap_action_frame("EXIT", 3)
    if bump == "function":
        shell.state.function_stack.append("f")
    else:
        shell.state.source_depth += 1
    try:
        assert traps.bare_status_entry_value == 3
    finally:
        if bump == "function":
            shell.state.function_stack.pop()
        else:
            shell.state.source_depth -= 1


# --------------------------------------------------------------------------
# Nesting: the innermost running action answers
# --------------------------------------------------------------------------

def test_signal_action_nested_in_an_exit_action_takes_the_signal_rule(traps):
    """The innermost frame wins, and popping restores the outer one.

    bash 5.3.15: ``trap 'echo E-entry=$?; kill -USR1 $$; sleep 0.2; exit'
    EXIT; trap 'echo S-entry=$?; false; exit' USR1; exit 3`` prints
    ``E-entry=3`` then ``S-entry=0`` and exits 0 -- the signal action's entry
    status, not the EXIT action's.
    """
    traps._push_trap_action_frame("EXIT", 3)
    traps._push_trap_action_frame("USR1", 0)
    assert traps.bare_status_entry_value == 0
    traps._trap_action_frames.pop()
    assert traps.bare_status_entry_value == 3
    traps._trap_action_frames.pop()
    assert traps.bare_status_entry_value is None


def test_debug_nested_in_a_signal_action_keeps_the_current_status(traps):
    """A DEBUG frame must not inherit the signal action's entry status."""
    traps._push_trap_action_frame("USR1", 5)
    traps._push_trap_action_frame("DEBUG", 5)
    assert traps.bare_status_entry_value is None
    traps._trap_action_frames.pop()
    assert traps.bare_status_entry_value == 5


def test_execute_trap_pops_its_frame_even_when_the_action_exits(shell):
    """The frame stack is balanced across a real action, exception or not.

    A leaked frame would silently rewrite the status of every later bare
    ``exit`` in the shell, so the pop lives in a ``finally``.
    """
    tm = shell.trap_manager
    shell.run_command("trap 'true' USR1")
    shell.state.last_exit_code = 6
    tm.execute_trap("USR1")
    assert tm._trap_action_frames == []
    assert tm.bare_status_entry_value is None

    shell.run_command("trap 'nosuchcommand_psh_2_1' USR1")
    tm.execute_trap("USR1")
    assert tm._trap_action_frames == []


# --------------------------------------------------------------------------
# "Not in a subshell": a forked COMPOUND child forgets the frames
# --------------------------------------------------------------------------

def test_forked_compound_child_drops_every_frame(traps):
    """The two forks that reuse the PARENT Shell object clear the stack.

    bash 5.3.15, entry status 5: ``trap '{ true; exit; } & wait $!;
    echo c=$?' USR1`` prints c=0 and ``trap 'false | { true; exit; };
    echo after=$?' USR1`` prints after=0 -- a forked COMPOUND cannot end the
    parent's trap action, so interp 1602's "not in a subshell" excludes it.
    A forked SIMPLE command keeps the entry status, which is why this is a
    targeted call and not part of enter_subshell_trap_environment.
    """
    traps._push_trap_action_frame("EXIT", 3)
    traps._push_trap_action_frame("USR1", 5)
    traps.drop_trap_action_frames_in_forked_compound()
    assert traps._trap_action_frames == []
    assert traps.bare_status_entry_value is None
    # Idempotent: a fresh-Shell fork may call it with nothing to drop.
    traps.drop_trap_action_frames_in_forked_compound()
    assert traps.bare_status_entry_value is None


# --------------------------------------------------------------------------
# Both consumers ask the owner (and a ZERO entry status must survive)
# --------------------------------------------------------------------------

def _stub_owner(monkeypatch, shell, value):
    """Make the owner answer *value* without needing a real trap action."""
    monkeypatch.setattr(type(shell.trap_manager), "bare_status_entry_value",
                        property(lambda self: value))


def test_exit_builtin_takes_a_zero_entry_status_over_a_nonzero_dollar_query(
        shell, monkeypatch):
    """Entry status 0 must WIN over ``$?`` 1 -- truthiness would drop it.

    A consumer written ``if entry_status:`` passes every cell whose entry
    status is non-zero and silently fails the common one (a signal trap
    entered after a successful command). Stubbing the owner pins the consumer
    without the 5.3 oracle.
    """
    from psh.builtins.core import ExitBuiltin
    shell.state.last_exit_code = 1
    _stub_owner(monkeypatch, shell, 0)
    monkeypatch.setattr(shell, "shutdown", lambda *a, **k: None)
    with pytest.raises(SystemExit) as excinfo:
        ExitBuiltin().execute(["exit"], shell)
    assert excinfo.value.code == 0


def test_exit_builtin_falls_back_to_dollar_query_when_no_frame(shell,
                                                               monkeypatch):
    """None means "use ``$?``" -- the other half of the consumer contract."""
    from psh.builtins.core import ExitBuiltin
    shell.state.last_exit_code = 1
    _stub_owner(monkeypatch, shell, None)
    monkeypatch.setattr(shell, "shutdown", lambda *a, **k: None)
    with pytest.raises(SystemExit) as excinfo:
        ExitBuiltin().execute(["exit"], shell)
    assert excinfo.value.code == 1


def test_return_builtin_asks_the_same_owner_query(shell, monkeypatch):
    """``ReturnBuiltin`` is the second consumer, with the same zero rule.

    bash 5.3 changed bare ``return`` for the same interpretation (CHANGES
    5.3-alpha item y): ``f() { kill -USR1 $$; sleep 0.2; }; trap 'false;
    return' USR1; f; echo after=$?`` prints after=0, not after=1.
    """
    from psh.builtins.function_support import ReturnBuiltin
    from psh.core.exceptions import FunctionReturn
    shell.state.function_stack.append("f")
    shell.state.last_exit_code = 1
    _stub_owner(monkeypatch, shell, 0)
    try:
        with pytest.raises(FunctionReturn) as excinfo:
            ReturnBuiltin().execute(["return"], shell)
        assert excinfo.value.exit_code == 0
    finally:
        shell.state.function_stack.pop()


def test_return_builtin_falls_back_to_dollar_query_when_no_frame(shell,
                                                                 monkeypatch):
    """None means "use ``$?``" for ``return`` too."""
    from psh.builtins.function_support import ReturnBuiltin
    from psh.core.exceptions import FunctionReturn
    shell.state.function_stack.append("f")
    shell.state.last_exit_code = 1
    _stub_owner(monkeypatch, shell, None)
    try:
        with pytest.raises(FunctionReturn) as excinfo:
            ReturnBuiltin().execute(["return"], shell)
        assert excinfo.value.exit_code == 1
    finally:
        shell.state.function_stack.pop()


def test_return_builtin_explicit_operand_ignores_the_owner(shell, monkeypatch):
    """``return N`` is unaffected, exactly like ``exit N``."""
    from psh.builtins.function_support import ReturnBuiltin
    from psh.core.exceptions import FunctionReturn
    shell.state.function_stack.append("f")
    shell.state.last_exit_code = 1
    _stub_owner(monkeypatch, shell, 0)
    try:
        with pytest.raises(FunctionReturn) as excinfo:
            ReturnBuiltin().execute(["return", "7"], shell)
        assert excinfo.value.exit_code == 7
    finally:
        shell.state.function_stack.pop()


def test_return_consumer_agrees_with_a_real_return_trap_frame(shell):
    """The RETURN frame kind and the ``return`` consumer agree end to end.

    No stub: a real RETURN frame is pushed, and the builtin resolves from it.
    """
    from psh.builtins.function_support import ReturnBuiltin
    from psh.core.exceptions import FunctionReturn
    tm = shell.trap_manager
    # The action runs at the depth the trap was ENTERED at, and `return` sits
    # at that same depth -- push the function frame first, as a real RETURN
    # trap firing inside a function does.
    shell.state.function_stack.append("f")
    tm._push_trap_action_frame("RETURN", 6)
    shell.state.last_exit_code = 0
    try:
        assert tm.bare_status_entry_value == 6
        with pytest.raises(FunctionReturn) as excinfo:
            ReturnBuiltin().execute(["return"], shell)
        assert excinfo.value.exit_code == 6
    finally:
        shell.state.function_stack.pop()
        tm._trap_action_frames.pop()
