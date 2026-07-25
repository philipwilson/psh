"""Slot 1.3b: a fatal signal must not leave the EXIT trap writing into the
interrupted command's redirect target.

MECHANISM (proven at v0.753.0 by capturing the redirect target's CONTENTS on
losing runs): a per-command redirect points ``sys.stdout`` at that command's
file for the duration of the command. A fatal signal delivered inside that
window runs the EXIT trap with the binding still installed, so the trap's
output goes into the interrupted command's FILE while the shell's stdout stays
empty. Three independent losses at base, each with the redirect target holding
``cleanup\\n`` and stdout holding nothing (~1 run in 120; bash 0/120 — bash's
EXIT trap on a signal writes to the SHELL's stdout, never to a command
redirect).

The output is MISDIRECTED, not lost, so the pins assert BOTH faces: it must
arrive on the shell's stdout AND the redirect target must contain only what
the command itself wrote.

Withdrawn approach, recorded so it is not retried: an earlier fix repaired a
DEAD ``state.stdout`` binding. It passed its own pins and fixed nothing — the
``echo`` builtin writes through ``sys.stdout``, so a dead ``state.stdout``
cannot lose the output. Building that fix's own red-on-base replay is what
exposed it.
"""

import io

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.shell import Shell


@pytest.fixture
def shell():
    sh = Shell()
    yield sh
    sh.close()


def _redirected_command(script):
    """The SimpleCommand node for a one-command script, via the real parser.

    Descends the Program -> AndOrList -> Pipeline -> SimpleCommand spine by
    following whichever child list a node exposes, so the helper does not
    hard-code the wrapper chain. Built from real parser output rather than
    hand-assembled AST nodes, so it cannot drift from the grammar.
    """
    node = parse(tokenize(script))
    for _ in range(10):
        if hasattr(node, 'redirects'):
            return node
        for attr in ('statements', 'commands', 'pipelines', 'and_or_lists'):
            kids = getattr(node, attr, None)
            if kids:
                node = kids[0]
                break
        else:
            break
    raise AssertionError('no redirect-bearing command found in %r' % script)


# --------------------------------------------------------------------------
# THE DEFECT — misdirection into the interrupted command's target.
# --------------------------------------------------------------------------

def test_restore_returns_zero_with_no_active_frame(shell):
    """Strict no-op when nothing is redirected (ruling condition (b))."""
    assert shell.io_manager.restore_active_builtin_redirections() == 0


def test_restore_with_no_frame_leaves_the_shell_usable(shell, capsys):
    """The no-op must not disturb the shell's own bindings."""
    shell.interactive_manager.signal_manager._restore_active_redirections()
    shell.run_command('echo still-working')
    assert 'still-working' in capsys.readouterr().out


def test_exit_trap_output_goes_to_stdout_not_the_redirect_target(
        shell, capsys, tmp_path):
    """BOTH FACES of the misdirection (ruling condition (e)).

    Establishes exactly the state a signal finds mid-command — a live
    per-command redirect frame — then runs the death path's ordering:
    restore, fire the EXIT trap, flush.

    RED ON BASE: without the restore, ``cleanup`` lands in ``target`` and the
    shell's stdout is empty.
    """
    target = tmp_path / 'redirect_target.txt'
    shell.run_command('trap "echo cleanup" EXIT')

    frame = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % target))
    try:
        # What the interrupted command itself writes belongs in the target.
        print('command-output', flush=True)

        sm = shell.interactive_manager.signal_manager
        sm._restore_active_redirections()        # <- the fix under test
        shell.trap_manager.execute_exit_trap()
        sm._flush_before_death()
    finally:
        # The fix already restored it; this is the paired teardown a real
        # caller would run, and it must stay harmless (see the LIFO/pop note
        # in restore_active_builtin_redirections).
        if frame in getattr(shell.io_manager, '_builtin_frame_stack', []):
            shell.io_manager.restore_builtin_redirections(frame)

    # FACE 1 — the trap's output reached the SHELL's stdout.
    assert 'cleanup' in capsys.readouterr().out

    # FACE 2 — the target holds ONLY what the command wrote.
    contents = target.read_text()
    assert 'command-output' in contents
    assert 'cleanup' not in contents, (
        "trap output contaminated the interrupted command's redirect "
        "target: %r" % contents)


def test_restore_drains_nested_frames_innermost_first(shell, tmp_path):
    """Nesting is real (eval/source/trap bodies redirect inside a redirect).

    All live frames must be restored, and the drain must terminate.
    """
    outer = tmp_path / 'outer.txt'
    inner = tmp_path / 'inner.txt'
    f_outer = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % outer))
    f_inner = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % inner))
    assert len(shell.io_manager._builtin_frame_stack) == 2

    restored = shell.io_manager.restore_active_builtin_redirections()

    assert restored == 2
    assert shell.io_manager._builtin_frame_stack == []
    assert f_outer is not None and f_inner is not None


def test_frame_leaves_the_stack_only_after_its_streams_are_restored(
        shell, tmp_path):
    """The (B) invariant: no instant where the stack and the streams disagree.

    Popping the frame FIRST left a sliver in which the stack said "nothing is
    redirected" while ``sys.stdout`` was still the command's file — the signal
    path had nothing to find, and an EXIT trap firing in that sliver wrote
    into the file. The frame must stay listed until its restore completes.
    """
    target = tmp_path / 'ordering.txt'
    frame = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % target))

    assert frame in shell.io_manager._builtin_frame_stack
    assert frame.streams_restored is False

    shell.io_manager.restore_builtin_redirections(frame)

    assert frame.streams_restored is True
    assert frame not in shell.io_manager._builtin_frame_stack


def test_drain_skips_a_frame_whose_restore_is_past_its_streams(
        shell, tmp_path):
    """Condition (b): the hazard the (B) reorder creates, closed and pinned.

    With the pop moved last, a signal landing mid-teardown finds the frame
    still on the stack. Re-running that restore would repeat the fd-0 step,
    which is NOT idempotent — it clears ``snapshot.stdin_fd``, so a second
    pass takes the else-branch and closes fd 0 out from under the shell.

    The drain skips frames already marked ``streams_restored``; that is safe
    precisely because the marker means the streams are correct, which is all
    the signal path needs. The mid-restore state is reproduced here by marking
    the frame while leaving it on the stack.
    """
    target = tmp_path / 'midrestore.txt'
    frame = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % target))
    try:
        frame.streams_restored = True
        assert shell.io_manager.restore_active_builtin_redirections() == 0, (
            "the drain re-entered a mid-restore frame; the fd-0 step would "
            "run twice and close fd 0")
        assert frame in shell.io_manager._builtin_frame_stack
    finally:
        frame.streams_restored = False
        shell.io_manager.restore_builtin_redirections(frame)


def test_fd0_survives_a_drain_over_a_mid_restore_frame(shell, tmp_path):
    """The consequence the skip prevents, asserted on fd 0 itself."""
    import os
    target = tmp_path / 'fd0.txt'
    frame = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % target))
    try:
        frame.streams_restored = True
        shell.io_manager.restore_active_builtin_redirections()
        os.fstat(0)  # OSError(EBADF) if fd 0 had been closed
    finally:
        frame.streams_restored = False
        shell.io_manager.restore_builtin_redirections(frame)


def test_restoring_an_already_restored_frame_is_not_attempted(shell, tmp_path):
    """Ruling condition (c) — the no-double-restore invariant, pinned.

    Per-frame restore is NOT idempotent: its fd-0 branch clears
    ``snapshot.stdin_fd``, so a second call would take the else-branch and
    close fd 0. The drain is safe because a frame is popped from the stack
    BEFORE any of its stream/fd work, so a frame that is being (or has been)
    torn down is no longer visible to the drain.
    """
    target = tmp_path / 'once.txt'
    frame = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % target))

    assert shell.io_manager.restore_active_builtin_redirections() == 1
    assert frame not in shell.io_manager._builtin_frame_stack
    # A second drain finds nothing to do — it cannot re-restore that frame.
    assert shell.io_manager.restore_active_builtin_redirections() == 0


# --------------------------------------------------------------------------
# INDEPENDENT HARDENING — the narrowed flush swallow (ruling item 2).
# Not the fix; it is the visibility guard that hid this class.
# --------------------------------------------------------------------------

def _dead_stream():
    """A closed stream whose flush RAISES, like a closed real file.

    ``TextIOWrapper``, not ``StringIO``: a closed StringIO's ``flush()``
    returns quietly, so using one would make the strict-errors test pass
    against a stream that cannot fail.
    """
    w = io.TextIOWrapper(io.BytesIO())
    w.close()
    return w


def test_flush_raises_on_a_dead_binding_under_strict_errors(shell):
    """Flushing psh's OWN closed binding is an internal-defect class error.

    Swallowing it unconditionally kept this class invisible for the whole
    1.3b investigation: the flush failed silently on every losing run. Under
    strict-errors — which the suite runs — it must raise.
    """
    shell.state.options['strict-errors'] = True
    shell.state.stdout = _dead_stream()

    with pytest.raises(ValueError):
        shell.interactive_manager.signal_manager._flush_before_death()


def test_flush_stays_quiet_on_a_dead_binding_without_strict_errors(shell):
    """...and stays silent in production, where death semantics come first."""
    shell.state.options['strict-errors'] = False
    shell.state.stdout = _dead_stream()

    shell.interactive_manager.signal_manager._flush_before_death()  # no raise


def test_flush_swallows_OSError_in_every_mode(shell):
    """A broken pipe / closed fd at death is a legitimate world-state.

    bash prints nothing for ``exec >&-`` plus a signal, so neither do we —
    even under strict-errors, which is why the taxonomy separates OSError
    from the internal-defect classes.
    """
    class BrokenPipe(io.StringIO):
        def flush(self):
            raise OSError(32, 'Broken pipe')

    shell.state.options['strict-errors'] = True
    shell.state.stdout = BrokenPipe()

    shell.interactive_manager.signal_manager._flush_before_death()  # no raise
