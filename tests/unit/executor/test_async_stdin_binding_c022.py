"""Unit pins: the ONE fd-0 answer the async policy consumes (C022).

``psh/core/stdin_binding.py#StdinBinding`` answers a single question — is fd 0
still the shell's own stdin, or did a pipeline / an enclosing COMPOUND
command's redirect supply it to this frame? ``AsyncJobPolicy.for_launch`` takes
that answer as its third input and drops the POSIX async ``/dev/null`` when it
is False, so ``echo hi | { cat & wait; }`` reads the pipe (bash 5.3.15).

The end-to-end bytes live in
``tests/conformance/bash/test_async_stdin_inheritance_conformance.py``; these
pin the decision table and the wiring that feeds it.

The wiring pins run a compound in-process and record what the BODY saw, using a
spy on the ``true`` builtin — the observation has to happen inside the body,
and a background child would carry it off into a forked process.
"""

import pytest

from psh.core.stdin_binding import StdinBinding
from psh.executor.process_launcher import AsyncJobPolicy, ProcessRole

# The wiring rows rebind fd 0 — and one of them fd 3 — in THIS process (saved
# and restored around each compound's body). Under xdist an fd >= 3 is the
# worker's execnet channel, so this module never shares a worker.
pytestmark = pytest.mark.serial


# ---- the owner: one question, one answer ----------------------------------

def test_fresh_shell_owns_its_stdin():
    assert StdinBinding().is_shell_stdin is True


def test_compound_scope_that_rebinds_fd0_takes_the_answer_away():
    """An fd-0 entry in the scope's saved-fd list IS the binding."""
    binding = StdinBinding()
    saved = [(0, 11)]
    binding.note_compound_applied(saved)
    assert binding.is_shell_stdin is False
    binding.note_compound_restored(saved)
    assert binding.is_shell_stdin is True


@pytest.mark.parametrize("saved", [
    [],                      # a compound with no redirects at all
    [(1, 12)],               # `{ ...; } > out`
    [(2, 12), (1, 13)],      # `{ ...; } > out 2> err`
])
def test_compound_scope_without_fd0_leaves_the_answer_alone(saved):
    binding = StdinBinding()
    binding.note_compound_applied(saved)
    assert binding.is_shell_stdin is True
    binding.note_compound_restored(saved)
    assert binding.is_shell_stdin is True


def test_nested_compound_scopes_unwind_in_order():
    """`{ { cat & wait; } < inner; } < outer`: the answer stays False until the
    OUTERMOST fd-0 scope ends."""
    binding = StdinBinding()
    outer, inner = [(0, 11)], [(0, 12)]
    binding.note_compound_applied(outer)
    binding.note_compound_applied(inner)
    binding.note_compound_restored(inner)
    assert binding.is_shell_stdin is False
    binding.note_compound_restored(outer)
    assert binding.is_shell_stdin is True


def test_pipe_binding_is_never_undone():
    """A pipeline member's fd 0 lasts for the life of its forked child."""
    binding = StdinBinding()
    binding.note_pipe_stdin()
    assert binding.is_shell_stdin is False
    # An unrelated compound window inside the member does not release it.
    saved = [(1, 11)]
    binding.note_compound_applied(saved)
    binding.note_compound_restored(saved)
    assert binding.is_shell_stdin is False


def test_child_inherits_the_binding_with_the_descriptor():
    binding = StdinBinding()
    binding.note_pipe_stdin()
    child = binding.copy_for_child()
    assert child.is_shell_stdin is False
    # ...and is independent: the child's own scopes do not reach the parent.
    child.note_compound_applied([(0, 11)])
    child.note_compound_restored([(0, 11)])
    child.note_compound_restored([(0, 11)])
    assert binding.is_shell_stdin is False
    assert StdinBinding().copy_for_child().is_shell_stdin is True


# ---- the consumer: the async decision table -------------------------------

@pytest.mark.parametrize("background", [True, False])
@pytest.mark.parametrize("job_control_off", [True, False])
@pytest.mark.parametrize("stdin_is_shell_own", [True, False])
def test_async_policy_decision_table(background, job_control_off,
                                     stdin_is_shell_own):
    """C022: the /dev/null half needs all THREE facts; the signal half two.

    The third input gates ONLY the stdin half — a background command reading a
    pipe still ignores INT/QUIT, it just keeps the input it was given.
    """
    policy = AsyncJobPolicy.for_launch(
        background=background, job_control_off=job_control_off,
        stdin_is_shell_own=stdin_is_shell_own)
    active = background and job_control_off
    assert policy.ignore_int_quit is active
    assert policy.redirect_stdin_from_devnull is (active and stdin_is_shell_own)


def test_async_policy_stdin_half_still_needs_role_single():
    """The role gate is a SEPARATE bash fact, not a second copy of this one.

    bash applies the async ``/dev/null`` to a lone command, never to an async
    PIPELINE: ``cat | cat &`` leaves the leader on the real stdin while
    ``cat &`` gets ``/dev/null`` (bash 5.3.15).
    """
    policy = AsyncJobPolicy.for_launch(
        background=True, job_control_off=True, stdin_is_shell_own=True)
    assert policy.redirect_stdin_from_devnull is True
    wants = {role: policy.redirect_stdin_from_devnull and role is ProcessRole.SINGLE
             for role in ProcessRole}
    assert wants[ProcessRole.SINGLE] is True
    assert wants[ProcessRole.PIPELINE_LEADER] is False
    assert wants[ProcessRole.PIPELINE_MEMBER] is False


# ---- the wiring: which redirect lists report to the owner ------------------

@pytest.fixture
def body_sees(isolated_shell_with_temp_dir, monkeypatch):
    """Run a script and return what ``true`` saw for each of its invocations."""
    shell = isolated_shell_with_temp_dir
    with open("in", "w") as fh:
        fh.write("payload\n")
    seen = []
    builtin = shell.builtin_registry.get("true")
    original = builtin.execute

    def spy(args, spied_shell):
        seen.append(spied_shell.state.stdin_binding.is_shell_stdin)
        return original(args, spied_shell)

    monkeypatch.setattr(builtin, "execute", spy)

    def run(script):
        seen.clear()
        assert shell.run_command(script) == 0, script
        return list(seen)

    return run


@pytest.mark.parametrize("script,expected", [
    # The shell's own stdin, untouched.
    ("true", [True]),
    # COMPOUND redirect lists supply fd 0 to the whole body.
    ("{ true; } < in", [False]),
    ("if :; then true; fi < in", [False]),
    ("while :; do true; break; done < in", [False]),
    ("for i in 1; do true; done < in", [False]),
    ("case a in a) true;; esac < in", [False]),
    ("{ { true; } < in; }", [False]),
    ("{ true; } <<< herestring", [False]),
    # A compound that redirects no INPUT fd supplies nothing.
    ("{ true; } > out", [True]),
    ("{ true; } 2> err", [True]),
    # ...and neither does an input redirect on a fd that is NOT 0. The binding
    # follows the fd the scope actually rebound, so `3< in` supplies fd 3 and a
    # named fd is allocated at >= 10. (bash's own classifier is fd-BLIND for
    # the file-opening input forms — `stdin_redirection` in redir.c returns 1
    # for `<` whatever the redirector — so it suppresses here and lets the
    # background reader keep the shell's stdin; a declared divergence.)
    ("{ true; } 3< in", [True]),
    ("{ true; } {v}< in", [True]),
    # A read-write open of fd 0 IS a binding.
    ("{ true; } <> in", [False]),
    # A SIMPLE command's own redirect list has no reach — including a function
    # CALL's (bash: `f() { cat & wait; }; f < file` prints nothing).
    ("f() { true; }; f < in", [True]),
    ("true < in", [True]),
    # ...but a function's DEFINITION-attached list is its body's compound list
    # (bash: `f() { cat & wait; } < file; f` prints the file).
    ("f() { true; } < in; f", [False]),
    # `exec` rebinds the shell's OWN stdin rather than supplying a frame's.
    ("exec 3< in; true", [True]),
    # The binding is released with the compound that made it.
    ("{ true; } < in; true", [False, True]),
    ("{ true; } < in\ntrue", [False, True]),
])
def test_only_compound_redirects_bind_the_frames_stdin(body_sees, script,
                                                       expected):
    """C022: which redirect lists reach a command the body backgrounds."""
    assert body_sees(script) == expected, script
