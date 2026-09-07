"""Process substitution implementation.

A process substitution is ONE pipe plus one forked shell running the body.
The shell keeps one end of the pipe and hands the consuming command the path
``/dev/fd/N`` naming it; the substitution child wires the other end onto the
descriptor its body uses — stdout for ``<(cmd)``, stdin for ``>(cmd)``. Both
directions therefore share a single acquisition, a single child runner and a
single release path; there is no named-FIFO variant and no rendezvous timeout
on any platform, matching bash wherever ``/dev/fd`` exists.

That matters for a consumer that opens the path LATE. The descriptor already
exists when the path is handed out, so an open seconds later still finds it
and every byte reaches the body::

    psh -c 'bash -c "sleep 6; printf \\"1\\\\n2\\\\n3\\\\n\\" > \\$1" _ \\
            >(wc -l >n); sleep 1; wait; cat n'      # -> 3

Acquisition is all-or-nothing. Every descriptor and the forked child are
registered with ONE ``ExitStack`` the moment they exist, and ownership passes
to the caller only on the success path, so a failure at any step — the pipe,
the promotion above the standard descriptors, the close-on-exec change, the
fork — releases everything the shell had taken and leaks no descriptor or
process.
"""
import fcntl
import os
import signal
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from ..ast_nodes import ProcessSubstitution, Redirect
    from ..shell import Shell


def _close_quietly(fd: int) -> None:
    """Close ``fd``, ignoring an already-closed / invalid descriptor."""
    try:
        os.close(fd)
    except OSError:
        pass


def _reap_abandoned_child(pid: int) -> None:
    """Kill and reap a substitution child whose acquisition then failed.

    Registered with the acquisition stack right after the fork, so a failure
    between the fork and the ownership transfer cannot orphan the child.
    """
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass


#: The shell's end of a substitution pipe is moved to the highest free
#: descriptor below this limit — bash's own choice for process substitution
#: (``subst.c``: ``move_to_high_fd (fd, 1, 64)``), which is why bash hands out
#: ``/dev/fd/63``.
HIGH_FD_LIMIT = 64


def _fd_is_free(fd: int) -> bool:
    """True when *fd* is not open in this process."""
    try:
        fcntl.fcntl(fd, fcntl.F_GETFD)
    except OSError:
        return True
    return False


def _move_to_high_fd(fd: int) -> int:
    """Move *fd* to the highest free descriptor below :data:`HIGH_FD_LIMIT`.

    The number IS the handed-out name (``/dev/fd/N``), and the consuming
    command redirects descriptors of its own, so a low number is a collision:
    with the shell's end on fd 3, ``cat <(echo a) 3>f`` gives the consumer a
    ``/dev/fd/3`` that its own ``3>f`` has already replaced. Keeping the end
    just below 64, as bash does, puts it clear of the numbers scripts use.

    Falls back to the lowest free descriptor above 2 when nothing below the
    limit can be taken — fd 0/1/2 must never hold it either, because when they
    began closed (``exec 1>&-``) ``/dev/fd/1`` would alias the closed shell
    stdout and the consumer's open would fail. Raises ``OSError`` only when
    even that fallback fails, leaving *fd* for the caller to release.
    """
    for candidate in range(HIGH_FD_LIMIT - 1, 2, -1):
        if not _fd_is_free(candidate):
            continue
        try:
            os.dup2(fd, candidate)
        except OSError:
            break
        _close_quietly(fd)
        return candidate
    if fd > 2:
        return fd
    promoted = fcntl.fcntl(fd, fcntl.F_DUPFD, 3)
    _close_quietly(fd)
    return promoted


def _pipe_endpoints(direction: str) -> Tuple[int, int]:
    """Create the substitution pipe; return ``(parent_fd, child_fd)``.

    Nothing is owned by the caller until this returns: a failure inside closes
    whatever it had already taken.
    """
    read_fd, write_fd = os.pipe()
    # <(cmd): the shell reads what the child writes. >(cmd): the reverse.
    parent_fd, child_fd = ((read_fd, write_fd) if direction == 'in'
                           else (write_fd, read_fd))
    try:
        parent_fd = _move_to_high_fd(parent_fd)
    except OSError:
        _close_quietly(parent_fd)
        _close_quietly(child_fd)
        raise
    return parent_fd, child_fd


def create_process_substitution(
        cmd_str: str, direction: str,
        shell: 'Shell', *,
        for_expansion: bool = False
        ) -> Tuple[int, str, int]:
    """Create a process substitution, returning ``(parent_fd, path, pid)``.

    Args:
        cmd_str: The command string to execute (without the <()/>() wrapper).
        direction: 'in' for <(cmd) (parent reads), 'out' for >(cmd) (parent
            writes).
        shell: The parent shell instance.
        for_expansion: True when the substitution is created while expanding a
            WORD rather than while resolving a redirect target.

    Returns:
        ``(parent_fd, path, child_pid)``. ``path`` is ``/dev/fd/<parent_fd>``,
        the name the consuming command opens.

    Raises:
        OSError: an acquisition step failed; nothing is left acquired.
    """
    with ExitStack() as acquisition:
        parent_fd, child_fd = _pipe_endpoints(direction)
        acquisition.callback(_close_quietly, parent_fd)
        acquisition.callback(_close_quietly, child_fd)

        # The shell's end must survive exec: an EXTERNAL consumer
        # (`tee >(cmd)`, `cat <(cmd)`) opens /dev/fd/N and can only do so if
        # it inherited descriptor N.
        flags = fcntl.fcntl(parent_fd, fcntl.F_GETFD)
        fcntl.fcntl(parent_fd, fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)

        # Fork the child with termination signals blocked across the fork
        # window (the lost-signal race fix; the child unblocks them in
        # apply_child_signal_policy after resetting handlers to SIG_DFL).
        from psh.executor import expansion_child_suppression, fork_with_signal_window, run_child_shell
        pid = fork_with_signal_window()
        if pid == 0:  # Child — run_child_shell never returns.
            def _io_setup() -> None:
                # Wire our pipe end onto the descriptor the body uses (stdout
                # for <(cmd), stdin for >(cmd)) and drop the shell's end, so a
                # `>(cmd)` body sees EOF once the consumer and the shell have
                # both released their copies. remap_fds handles the case where
                # fd 0/1 began closed and os.pipe() returned an endpoint AS
                # that descriptor, which the naive dup2-then-close recipe
                # destroyed.
                from .fd_remap import remap_fds
                body_fd = 1 if direction == 'in' else 0
                remap_fds({child_fd: body_fd}, owned=[parent_fd, child_fd])

            def _body(child_shell: 'Shell') -> int:
                return _execute_process_substitution_body(cmd_str, child_shell)

            run_child_shell(
                shell, _body,
                # Substitution children never source rc files (bash sources rc
                # once, at startup — not per subshell). Without this, an
                # interactive `<(cmd)` builds an interactive child (stdin is
                # still the parent tty) that sourced ~/.pshrc, leaking its
                # output into the substitution. Matches command_sub's default.
                norc=True,
                io_setup=_io_setup,
                # bash does not keep parent traps listable in a
                # process-substitution child (unlike $(trap)).
                inherit_traps=False,
                errexit_suppress_override=(
                    expansion_child_suppression(shell._current_executor)
                    if for_expansion else None),
                error_label='process substitution',
            )

        acquisition.callback(_reap_abandoned_child, pid)

        # Success: the caller owns parent_fd and the child from here.
        acquisition.pop_all()

    # The shell never uses the child's end, and holding it would keep a
    # `<(cmd)` consumer from ever seeing EOF.
    _close_quietly(child_fd)
    return parent_fd, f"/dev/fd/{parent_fd}", pid


def _execute_process_substitution_body(cmd_str: str, child_shell: 'Shell') -> int:
    # Route through the unified input path (like command substitution's
    # child.run_command) so the body gets heredoc-aware lexing, line
    # continuations, etc. A bare tokenize()/parse() here has no heredoc
    # support, so a heredoc inside the substitution (`<(cat <<EOF ... EOF)`)
    # leaked its body lines as separate commands.
    return child_shell.run_command(cmd_str, add_to_history=False)


@dataclass
class ProcessSubstitutionResource:
    """One process substitution created for a redirect target."""
    path: str
    parent_fd: Optional[int]
    pid: int

    def register_with(self, handler: 'ProcessSubstitutionHandler') -> None:
        handler.active_pids.append(self.pid)

    def close_parent_fd_for_redirect(
            self, redirect: 'Redirect', *, applied: bool) -> None:
        """Close the parent fd unless successful dup2 made it the target fd."""
        if self.parent_fd is None:
            return
        if applied and self.parent_fd in self._target_fds(redirect):
            return
        _close_quietly(self.parent_fd)
        self.parent_fd = None

    def hand_off_to_scope(self, handler: 'ProcessSubstitutionHandler') -> None:
        """Transfer the parent fd to the enclosing ``process_sub_scope()`` for
        deferred close, relinquishing this resource's ownership of it.

        Used where the fd must outlive a single redirect rather than being
        closed right after the dup2 (the alternative,
        ``close_parent_fd_for_redirect``): word-expansion substitutions, and
        the in-process builtin redirect path (the builtin reads ``/dev/fd/N``,
        so the descriptor must stay open until the consuming command finishes
        — for ``>(cmd)`` it is the last write end, and closing it early would
        end the body's read before the consumer wrote anything).
        The scope closes it on exit.
        """
        if self.parent_fd is not None:
            handler.active_fds.append(self.parent_fd)
            self.parent_fd = None

    @staticmethod
    def _target_fds(redirect: 'Redirect') -> Tuple[int, ...]:
        if redirect.combined:
            return (1, 2)
        if redirect.fd is not None:
            return (redirect.fd,)
        return (0,) if redirect.type.startswith('<') else (1,)


class ProcessSubstitutionHandler:
    """Handles process substitution <(...) and >(...)."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

        # Track process substitution resources for the scope currently
        # being executed (see scope()).
        self.active_fds: List[int] = []
        self.active_pids: List[int] = []
        # Children whose consuming command has finished but which had not
        # exited yet (e.g. `echo >(sleep 3)`). They are re-polled
        # non-blockingly at every scope exit so they are reaped soon after
        # they exit, without ever making the shell wait for them (bash
        # behaves the same: the substitution may outlive its command).
        self.pending_pids: List[int] = []

    def create_for_expansion(self, direction: str, command: str) -> str:
        """Create one process substitution during word expansion.

        Used by the expansion manager for ProcessSubstitution word parts —
        both whole-word (``<(cmd)``) and embedded (``pre<(cmd)post``) forms.
        The parent fd and child pid are registered with the handler so the
        enclosing scope() closes the fd and reaps the child when the
        consuming command finishes.

        Args:
            direction: 'in' for <(cmd), 'out' for >(cmd).
            command: The command text (without the <()/>()} wrapper).

        Returns:
            The /dev/fd/N path to splice into the word.
        """
        fd, path, pid = create_process_substitution(
            command, direction, self.shell, for_expansion=True)
        resource = ProcessSubstitutionResource(path, fd, pid)
        # The consuming command opens /dev/fd/N, so the parent fd must outlive
        # this expansion — hand it to the scope for deferred close.
        resource.hand_off_to_scope(self)
        resource.register_with(self)
        return path

    def resolve_procsub_resource(
            self, node: 'ProcessSubstitution'
            ) -> Tuple[str, ProcessSubstitutionResource]:
        """Resolve a redirect-target process substitution NODE to a resource.

        The planner has already determined STRUCTURALLY (from the Word AST) that
        this redirect's target is a whole-word process substitution, and hands
        us the node. We create the substitution from the node's RAW body text
        (``node.source``) — never from a re-expanded or re-sniffed string — so a
        `<(echo $x)` body is expanded exactly once, by the substitution's own
        child, matching bash. Returns ``(/dev/fd/N path, resource)``.
        """
        parent_fd, fd_path, pid = create_process_substitution(
            node.source, node.direction, self.shell)
        resource = ProcessSubstitutionResource(fd_path, parent_fd, pid)
        resource.register_with(self)
        return fd_path, resource

    @contextmanager
    def scope(self):
        """Own the substitutions created while the scope is active.

        On exit, the parent-side fds registered inside the scope are
        closed and their children reaped non-blockingly; children that
        are still running are parked in pending_pids for later polling.
        Scopes nest (a command inside a redirected loop body only cleans
        up its own substitutions, not the loop's `< <(cmd)`).
        """
        fd_mark = len(self.active_fds)
        pid_mark = len(self.active_pids)
        try:
            yield
        finally:
            self._cleanup_from(fd_mark, pid_mark)

    def _cleanup_from(self, fd_mark: int, pid_mark: int):
        """Release substitutions registered at or after the given marks."""
        # Close the parent-side fds. Consumers hold their own references
        # (a forked child inherited the fd; a redirect dup2'd it), so this
        # only releases the shell's copy — which for a `>(cmd)` is the last
        # write end, and is what ends the body's read.
        for fd in self.active_fds[fd_mark:]:
            _close_quietly(fd)
        del self.active_fds[fd_mark:]

        # Never block on substitution children: a >(cmd) child may outlive
        # the command that spawned it (bash returns immediately too).
        self.pending_pids.extend(self.active_pids[pid_mark:])
        del self.active_pids[pid_mark:]
        self.reap_pending()

    def reap_pending(self):
        """Reap any finished substitution children without blocking.

        Only the recorded substitution pids are waited on (never -1), so
        this can never steal an exit status from the job manager.
        """
        still_running = []
        for pid in self.pending_pids:
            try:
                wpid, _status = os.waitpid(pid, os.WNOHANG)
            except OSError:
                # Already reaped (e.g. by a waitpid(-1) elsewhere) — drop it.
                continue
            if wpid == 0:
                still_running.append(pid)
        self.pending_pids[:] = still_running
