"""Slot 1.3b: a fatal signal must not leave the EXIT trap writing into the
interrupted command's redirect target.

MECHANISM (proven at v0.753.0 by capturing the redirect target's CONTENTS on
losing runs): a per-command redirect points ``sys.stdout`` at that command's
file for the duration of the command. A fatal signal delivered inside that
window runs the EXIT trap with the binding still installed, so the trap's
output goes into the interrupted command's FILE while the shell's stdout stays
empty. Three independent losses at base, each with the target holding
``cleanup\\n`` and stdout holding nothing (~1 run in 120; bash 0/120).

The output is MISDIRECTED, not lost, so the pins assert BOTH faces.

TWO LEVELS, deliberately:
  * ``test_terminate_from_signal_*`` drive the REAL
    ``SignalManager._terminate_from_signal`` with ``os.kill`` stubbed. These
    are the WIRING pins — they go red if the drain call is removed from the
    death path, which the helper-level pins alone did not.
  * the rest pin the individual invariants (ordering, the mid-restore guard,
    the death-path failure taxonomy).

Withdrawn approach, recorded so it is not retried: an earlier fix repaired a
DEAD ``state.stdout`` binding. It passed its own pins and fixed nothing — the
``echo`` builtin writes through ``sys.stdout``, so a dead ``state.stdout``
cannot lose the output. Building that fix's own red-on-base replay exposed it.
"""

import contextlib
import io
import os
import signal
import sys

import pytest

import psh.interactive.signal_manager as signal_manager_module
from psh.lexer import tokenize
from psh.parser import parse
from psh.shell import Shell


@contextlib.contextmanager
def captured_real_stdout():
    """Capture what reaches the process's stdout, without pytest's fixture.

    CLAUDE.md's Output Capture Rules forbid pytest's capture fixture for tests
    that perform I/O redirection, and `test_fixture_ratchets` enforces it —
    these tests install real redirect frames, so that fixture is exactly the
    wrong instrument here. (The ratchet matches the bare fixture NAME anywhere
    in a file, so this docstring avoids spelling it; the rule is in CLAUDE.md
    under that name.)

    Swapping ``sys.stdout`` for a StringIO is also faithful to the subject:
    the redirect machinery snapshots whatever stdout it finds and restores to
    it, so the substitute plays the part of the shell's real stdout.
    """
    real = sys.stdout
    buf = io.StringIO()
    sys.stdout = buf
    try:
        yield buf
    finally:
        sys.stdout = real


@contextlib.contextmanager
def kill_stubbed():
    """Stub ``os.kill`` inside the signal manager so the process survives.

    Everything else on the death path — the drain, the trap, the flush, the
    SIG_DFL registration, and the ORDER between them — stays production code.
    Yields the list of ``(pid, signum)`` the code tried to kill with, so a
    test can assert the signal death still happens.
    """
    kills = []
    real_kill = signal_manager_module.os.kill
    signal_manager_module.os.kill = lambda pid, sig: kills.append((pid, sig))
    try:
        yield kills
    finally:
        signal_manager_module.os.kill = real_kill


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
    hand-assembled AST, so it cannot drift from the grammar.
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


def _dead_stream():
    """A closed stream whose flush RAISES, like a closed real file.

    ``TextIOWrapper``, not ``StringIO``: a closed StringIO's ``flush()``
    returns quietly, so using one would make these tests pass against a stream
    that cannot fail.
    """
    w = io.TextIOWrapper(io.BytesIO())
    w.close()
    return w


def _drop(io_manager, frame):
    """Tear a frame down if it is still live (test cleanup, fd-1 safety)."""
    if frame in io_manager._builtin_frame_stack:
        io_manager.restore_builtin_redirections(frame)


# --------------------------------------------------------------------------
# WIRING PINS — drive the REAL _terminate_from_signal.
#
# What the round-1 verifier's mutation proved missing: deleting the drain call
# from _terminate_from_signal left every helper-level pin green.
# --------------------------------------------------------------------------

@pytest.mark.parametrize('redirect', [
    'echo x > TARGET',    # truncating redirect
    'echo x >> TARGET',   # appending redirect
    ': > TARGET',         # the reproducer's own sentinel shape
])
def test_terminate_from_signal_does_not_misdirect_the_exit_trap(
        shell, tmp_path, redirect):
    """The death path itself must put the trap's output on the SHELL's stdout.

    RED ON BASE, and red again if the drain call is removed from
    ``_terminate_from_signal`` — the mutation that exposed the original pin
    battery as decorative.

    Every assertion is outside the try/finally that owns the frame: these
    install a real redirect over fd 1, and an assertion failing mid-frame
    would leave the xdist worker's fd 1 pointing at a temp file
    (CLAUDE.md parallel-safety rule 1).
    """
    target = tmp_path / 'target.txt'
    shell.run_command('trap "echo cleanup" EXIT')
    sm = shell.interactive_manager.signal_manager

    with captured_real_stdout() as shell_stdout, kill_stubbed() as kills:
        frame = shell.io_manager.setup_builtin_redirections(
            _redirected_command(redirect.replace('TARGET', str(target))))
        try:
            shell.run_command('echo command-output')
            sm._terminate_from_signal(signal.SIGTERM)
        finally:
            _drop(shell.io_manager, frame)

    contents = target.read_text()
    # FACE 1 — the trap's output reached the SHELL's stdout.
    assert 'cleanup' in shell_stdout.getvalue()
    # FACE 2 — the target holds only what the command wrote.
    assert 'cleanup' not in contents, (
        "EXIT-trap output was misdirected into the interrupted command's "
        "redirect target: %r" % contents)
    # And the shell still dies BY the signal.
    assert kills == [(os.getpid(), signal.SIGTERM)]


def test_terminate_from_signal_still_dies_by_signal_when_trap_exits_zero(shell):
    """``exit 0`` inside the EXIT trap must not convert the signal death.

    The trap raises SystemExit; the death path swallows it and re-raises the
    signal. Asserted through the REAL entry point so the containment cannot be
    refactored away unnoticed.
    """
    shell.run_command('trap "echo bye; exit 0" EXIT')
    sm = shell.interactive_manager.signal_manager

    with captured_real_stdout() as out, kill_stubbed() as kills:
        sm._terminate_from_signal(signal.SIGTERM)

    assert 'bye' in out.getvalue()
    assert kills == [(os.getpid(), signal.SIGTERM)]


def test_terminate_from_signal_dies_by_signal_even_if_a_binding_is_dead(shell):
    """An internal defect on the death path must not change the wait status.

    A dead stdout binding makes the flush fail. Under strict-errors that is
    now REPORTED, but it must not RAISE: an exception would escape before
    SIG_DFL/os.kill and turn a signal death into an ordinary exit — silently
    breaking the semantics this path exists to preserve.
    """
    shell.state.options['strict-errors'] = True
    shell.state.stdout = _dead_stream()
    sm = shell.interactive_manager.signal_manager

    with kill_stubbed() as kills:
        sm._terminate_from_signal(signal.SIGTERM)

    assert kills == [(os.getpid(), signal.SIGTERM)], (
        "the shell stopped dying by the signal when an internal defect was "
        "reported on the death path")


# --------------------------------------------------------------------------
# THE ORDERING INVARIANT — OBSERVED mid-restore, not inferred from pre/post.
# --------------------------------------------------------------------------

def test_frame_is_still_on_the_stack_while_its_streams_are_restored(
        shell, tmp_path):
    """Samples stack membership AT THE MOMENT the streams are put back.

    The round-1 version of this pin asserted only that the frame was listed
    before the restore and gone after — true of the BASE code too, which
    popped first, so reverting the pop left it green.

    Here the frame's snapshot is proxied so that reading ``.stdout`` — which
    the restore does while reinstalling the streams — records whether the
    frame is still on the stack at that instant. At tip it must be; with the
    pop back at the start it is already absent, which is precisely the sliver
    that let the trap misdirect.
    """
    target = tmp_path / 'observed.txt'
    io_manager = shell.io_manager
    frame = io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % target))
    observed = {}
    inner_snapshot = frame.snapshot

    class SamplingSnapshot:
        """Proxy recording stack membership when the restore reads stdout."""

        def __getattr__(self, name):
            if name == 'stdout' and 'on_stack' not in observed:
                observed['on_stack'] = frame in io_manager._builtin_frame_stack
            return getattr(inner_snapshot, name)

        def __setattr__(self, name, value):
            setattr(inner_snapshot, name, value)

    frame.snapshot = SamplingSnapshot()
    try:
        io_manager.restore_builtin_redirections(frame)
    finally:
        frame.snapshot = inner_snapshot
        _drop(io_manager, frame)

    assert observed.get('on_stack') is True, (
        "the frame had already left the stack while its streams were being "
        "restored — the base behavior fix (B) removed, and the sliver in "
        "which a fatal signal finds nothing to restore")


def test_frame_leaves_the_stack_once_its_restore_completes(shell, tmp_path):
    """The other half of the invariant: it must not stay listed forever."""
    frame = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % (tmp_path / 'ordering.txt')))
    try:
        on_stack_before = frame in shell.io_manager._builtin_frame_stack
        marked_before = frame.streams_restored
        shell.io_manager.restore_builtin_redirections(frame)
    finally:
        _drop(shell.io_manager, frame)

    assert on_stack_before is True
    assert marked_before is False
    assert frame.streams_restored is True
    assert frame not in shell.io_manager._builtin_frame_stack


def test_frame_leaves_the_stack_even_if_its_restore_raises(shell, tmp_path):
    """Pop-last must not mean pop-never (round-1 NIT 5/18).

    Base popped up front, so an exception mid-restore still removed the frame.
    With the pop moved last it lives in a ``finally``, or a raising restore
    would strand the frame and every later drain would retry a half-restored
    one.
    """
    frame = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % (tmp_path / 'raiser.txt')))
    real_snapshot = frame.snapshot

    class Boom:
        def __getattr__(self, name):
            raise RuntimeError('synthetic failure inside restore')

    frame.snapshot = Boom()
    try:
        with pytest.raises(RuntimeError):
            shell.io_manager.restore_builtin_redirections(frame)
        stranded = frame in shell.io_manager._builtin_frame_stack
    finally:
        frame.snapshot = real_snapshot
        _drop(shell.io_manager, frame)

    assert stranded is False, (
        "a restore that raised left the frame on the stack forever")


# --------------------------------------------------------------------------
# THE DRAIN — no-op safety, nesting, and the mid-restore guard.
# --------------------------------------------------------------------------

def test_restore_returns_zero_with_no_active_frame(shell):
    """Strict no-op when nothing is redirected."""
    assert shell.io_manager.restore_active_builtin_redirections() == 0


def test_restore_with_no_frame_leaves_the_shell_usable(shell):
    """The no-op must not disturb the shell's own bindings."""
    shell.interactive_manager.signal_manager._restore_active_redirections()
    with captured_real_stdout() as out:
        shell.run_command('echo still-working')
    assert 'still-working' in out.getvalue()


def test_restore_drains_nested_frames_innermost_first(shell, tmp_path):
    """Nesting is real (eval/source/trap bodies redirect inside a redirect)."""
    io_manager = shell.io_manager
    f_outer = io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % (tmp_path / 'outer.txt')))
    f_inner = io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % (tmp_path / 'inner.txt')))
    try:
        depth = len(io_manager._builtin_frame_stack)
        restored = io_manager.restore_active_builtin_redirections()
        remaining = list(io_manager._builtin_frame_stack)
    finally:
        for f in (f_inner, f_outer):
            _drop(io_manager, f)

    assert depth == 2
    assert restored == 2
    assert remaining == []


def test_drain_skips_a_frame_whose_restore_is_past_its_streams(shell, tmp_path):
    """The hazard fix (B) creates, closed and pinned.

    With the pop last, a signal landing mid-teardown finds the frame still on
    the stack. Re-running that restore would repeat the fd-0 step, which is
    NOT idempotent — it clears ``snapshot.stdin_fd``, so a second pass takes
    the else-branch and closes fd 0.

    The drain skips frames marked ``streams_restored``. That marker is
    STREAM-level: it means the shell's streams are correct — all the signal
    path needs — not that the frame is fully torn down.
    """
    frame = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % (tmp_path / 'midrestore.txt')))
    try:
        frame.streams_restored = True
        drained = shell.io_manager.restore_active_builtin_redirections()
        still_listed = frame in shell.io_manager._builtin_frame_stack
    finally:
        frame.streams_restored = False
        _drop(shell.io_manager, frame)

    assert drained == 0, (
        "the drain re-entered a mid-restore frame; the fd-0 step would run "
        "twice and close fd 0")
    assert still_listed is True


def test_fd0_survives_a_drain_over_a_mid_restore_frame(shell, tmp_path):
    """The consequence the skip prevents, asserted on fd 0 itself."""
    frame = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % (tmp_path / 'fd0.txt')))
    try:
        frame.streams_restored = True
        shell.io_manager.restore_active_builtin_redirections()
        fd0_alive = True
        try:
            os.fstat(0)
        except OSError:
            fd0_alive = False
    finally:
        frame.streams_restored = False
        _drop(shell.io_manager, frame)

    assert fd0_alive, "the drain closed fd 0 by re-running the fd-0 step"


def test_restoring_an_already_restored_frame_is_not_attempted(shell, tmp_path):
    """A drained frame is gone, so the drain cannot re-restore it."""
    frame = shell.io_manager.setup_builtin_redirections(
        _redirected_command(': > %s' % (tmp_path / 'once.txt')))
    try:
        first = shell.io_manager.restore_active_builtin_redirections()
        gone = frame not in shell.io_manager._builtin_frame_stack
        second = shell.io_manager.restore_active_builtin_redirections()
    finally:
        _drop(shell.io_manager, frame)

    assert (first, gone, second) == (1, True, 0)


# --------------------------------------------------------------------------
# INDEPENDENT HARDENING — the death-path failure taxonomy.
# Not the fix; it is the visibility guard that hid this class.
# --------------------------------------------------------------------------

def test_flush_reports_an_internal_defect_under_strict_errors(shell, capfd):
    """Loud where it protects us — and WITHOUT raising.

    Swallowing this unconditionally kept the class invisible for the whole
    1.3b investigation: the flush failed silently on every losing run. Under
    strict-errors it now writes a diagnostic to fd 2, then execution
    continues, so the shell still dies by the signal.
    """
    shell.state.options['strict-errors'] = True
    shell.state.stdout = _dead_stream()

    shell.interactive_manager.signal_manager._flush_before_death()  # no raise

    assert 'internal defect during stream flush' in capfd.readouterr().err


def test_flush_stays_silent_without_strict_errors(shell, capfd):
    """In production a signalled shell prints what bash prints."""
    shell.state.options['strict-errors'] = False
    shell.state.stdout = _dead_stream()

    shell.interactive_manager.signal_manager._flush_before_death()

    assert 'internal defect' not in capfd.readouterr().err


def test_flush_swallows_OSError_in_every_mode(shell, capfd):
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

    shell.interactive_manager.signal_manager._flush_before_death()

    assert 'internal defect' not in capfd.readouterr().err


def test_drain_reports_an_internal_defect_under_strict_errors(
        shell, capfd, monkeypatch):
    """The drain gets the same taxonomy as the flush — never a bare pass."""
    shell.state.options['strict-errors'] = True

    def boom():
        raise RuntimeError('synthetic drain failure')

    monkeypatch.setattr(shell.io_manager,
                        'restore_active_builtin_redirections', boom)

    shell.interactive_manager.signal_manager._restore_active_redirections()

    assert 'internal defect during redirect restore' in capfd.readouterr().err
