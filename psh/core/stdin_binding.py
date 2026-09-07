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

class StdinBinding:
    """Whether fd 0 is the shell's own stdin, or a frame's inherited input.

    Exactly two things rebind fd 0 for a whole frame, and both report here:

    * a COMPOUND command's redirect list — ``{ } < f``, ``( ) < f``,
      ``while ...; done < f``, ``if``/``case``/``for``, and any input form on
      them (``<<<``, a heredoc, ``< <(cmd)``, ``<&3``). Those lists are applied
      through ``io_redirect/manager.py#IOManager.apply_compound_redirections``
      and undone through ``restore_compound_redirections``, which is where the
      two ``note_compound_*`` calls live. What counts as "supplied" is decided
      once, by ``io_redirect/redirect_program.py#supplies_frame_stdin``: an
      INPUT-direction redirect landing on fd 0. Direction and fd BOTH matter —
      ``{ cat & wait; } 0>&1`` hands fd 0 an output, so the async default must
      still apply (counting it left the reader blocked on a write-only fd 0),
      and ``3< file`` supplies fd 3.
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

    This class lives in ``psh/core`` rather than the io layer that reports to
    it because ``ShellState`` constructs it and the import-layering guard keeps
    ``psh.core`` near-leaf (it may not import ``psh.io_redirect``); the io layer
    is the REPORTER, not the owner.

    The binding is SCOPED to the frame that made it — it ends when that
    compound's redirects are undone, and an inner construct never releases an
    outer one's. bash approximates the same fact with a single global flag,
    assigned at three points and cleared once per top-level command, so it
    forgets a binding a nested frame reassigns and keeps a stale one after the
    compound ends. Every shape where the two models disagree is a DECLARED
    divergence (ruled W1-N80) with its own two-sided pin: psh either delivers
    input bash drops, or withholds the shell's own stdin from an async reader
    and leaves it readable by the shell.

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

    def note_compound_applied(self, supplied_stdin: bool) -> None:
        """A compound command's redirect list has been applied.

        *supplied_stdin* is ``list_supplies_frame_stdin`` for that list — the
        one classifier; this object never re-inspects redirect syntax.
        """
        if supplied_stdin:
            self._frames += 1

    def note_compound_restored(self, supplied_stdin: bool) -> None:
        """That compound command's redirect list has been undone."""
        if supplied_stdin and self._frames > 0:
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
