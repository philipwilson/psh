"""Where the current execution frame's fd 0 came from.

One question, one answer: is fd 0 still the SHELL'S OWN standard input, or was
it supplied to the frame the shell is running right now — by a pipeline, or by
the redirect list of an enclosing compound command?

The answer gates exactly one rule: the POSIX default that an ASYNCHRONOUS
command reads ``/dev/null`` when job control is off
(``executor/process_launcher.py#AsyncJobPolicy``). bash applies that default
only while the shell still owns fd 0, so ``echo hi | { cat & wait; }`` prints
``hi`` and ``{ cat & wait; } < file`` prints the file, while a top-level
``cat & wait`` reads nothing.
"""

from typing import Optional, Sequence, Tuple

# The (fd, saved_fd) pairs a redirect scope records for its own restore.
SavedFds = Sequence[Tuple[int, Optional[int]]]


class StdinBinding:
    """Whether fd 0 is the shell's own stdin, or a frame's inherited input.

    Exactly two things rebind fd 0 for a whole frame, and both report here:

    * a COMPOUND command's redirect list — ``{ } < f``, ``( ) < f``,
      ``while ...; done < f``, ``if``/``case``/``for``, and any input form on
      them (``<<<``, a heredoc, ``< <(cmd)``, ``<&3``). Those lists are applied
      through ``io_redirect/manager.py#IOManager.apply_compound_redirections``
      and undone through ``restore_compound_redirections``, which is where the
      two ``note_compound_*`` calls live: an fd-0 entry in the scope's saved-fd
      list IS the fact that this scope rebound fd 0.
    * a pipeline member's incoming pipe, wired onto fd 0 by
      ``executor/pipeline.py#PipelineExecutor._setup_pipeline_redirections`` in
      the member's own forked child.

    Two neighbours deliberately do NOT report, because bash keeps sending the
    async child to ``/dev/null`` for both (probed against bash 5.3.15):

    * a SIMPLE command's own redirect (``cat < file &``, and a function call's
      ``f < file``) — the async policy runs BEFORE the child's own redirects,
      so an explicit ``< file`` on the background command itself still wins
      fd 0 without any help from here, and ``f() { cat & wait; }; f < file``
      prints nothing in bash;
    * ``exec < file``, which rebinds the shell's own stdin rather than
      supplying one to a frame: ``exec < file; cat & wait`` prints nothing in
      both shells. So this is NOT "fd 0 still points at the original open file
      description" — it is "no frame supplied fd 0 to the command being
      launched".

    A forked child inherits fd 0 at the OS level, so it inherits this binding
    (``ShellState.clone_for_child``): the reader inside
    ``echo hi | ( cat & wait )`` is two forks below the pipe.

    The binding is SCOPED to the frame that made it — it ends when that
    compound's redirects are undone, and an inner construct never releases an
    outer one's. bash approximates the same fact with a single global flag that
    the innermost redirect-bearing construct overwrites, so a few deeply nested
    shapes differ; psh keeps the binding in every one of them, which is the
    direction that does not lose the input (the divergences are pinned as
    declared, psh-only behavioral rows).

    Reproduce (bash 5.3.15 vs psh, C022)::

        echo hello | { cat & wait; }      # hello
        { cat & wait; } < file            # the file's bytes
        cat & wait                        # nothing: the shell owns fd 0
    """

    def __init__(self) -> None:
        # How many enclosing frames supplied this process's fd 0. Zero means
        # the shell's own stdin is still on fd 0.
        self._frames = 0

    @property
    def is_shell_stdin(self) -> bool:
        """True when no pipeline or compound redirect supplied fd 0."""
        return self._frames == 0

    @staticmethod
    def _rebinds_stdin(saved_fds: SavedFds) -> bool:
        """True when a redirect scope's saved-fd list shows it took over fd 0.

        The saved list is the scope's own restore plan, so it names the fds it
        actually rebound — a named-fd redirect (``{v}<file``, allocated at
        fd >= 10 and never restored) contributes no entry, and neither does a
        list that only touches output fds.
        """
        return any(fd == 0 for fd, _ in saved_fds)

    def note_compound_applied(self, saved_fds: SavedFds) -> None:
        """A compound command's redirect list has been applied."""
        if self._rebinds_stdin(saved_fds):
            self._frames += 1

    def note_compound_restored(self, saved_fds: SavedFds) -> None:
        """That compound command's redirect list has been undone."""
        if self._rebinds_stdin(saved_fds) and self._frames > 0:
            self._frames -= 1

    def note_pipe_stdin(self) -> None:
        """This process is a pipeline member reading the previous member's pipe.

        Never undone: the member's child process runs its whole body on that
        pipe and then exits.
        """
        self._frames += 1

    def copy_for_child(self) -> "StdinBinding":
        """The binding a child process starts with — this one, unchanged."""
        child = StdinBinding()
        child._frames = self._frames
        return child
