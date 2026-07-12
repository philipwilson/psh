"""File redirection implementation."""
import copy
import fcntl
import os
import stat
import sys
from typing import TYPE_CHECKING, List, TextIO, Tuple, cast

from ..ast_nodes import ExpansionPart, ProcessSubstitution, Redirect
from .planner import RedirectPlan, RedirectPlanner

if TYPE_CHECKING:
    from ..shell import Shell


def _dup2_preserve_target(opened_fd: int, target_fd: int):
    """dup2() helper that avoids closing target_fd when FDs already match."""
    if opened_fd == target_fd:
        # open() happened to land exactly on target_fd, so no dup2 is needed.
        # But dup2 is also what CLEARS O_CLOEXEC: Python opens fds
        # non-inheritable by default, so without dup2 the raw fd stays
        # CLOEXEC and a child (e.g. `cat /dev/fd/3 3<data`) can't inherit it —
        # it sees EBADF where bash succeeds. Clear CLOEXEC here so the shortcut
        # is behaviorally identical to the dup2 path (dup2 yields an
        # inheritable fd).
        os.set_inheritable(target_fd, True)
        return
    os.dup2(opened_fd, target_fd)
    os.close(opened_fd)


# The open(2) flags for each filename redirect type, in ONE place. Every path
# that opens a redirect target — the per-type `_redirect_*` helpers, the
# combined `&>`/`&>>` opener (which reuses the `>`/`>>` entries: a combined
# redirect truncates or appends exactly like plain output, and its type may be
# spelled `&>`/`&>>` or csh-style `>&`), and the named-fd `{v}>file` allocator
# (`apply_var_fd_redirect`) — reads flags from here, so changing a mode is a
# single edit. noclobber is orthogonal (a `>`/`&>` precondition), checked via
# `check_noclobber`, never encoded in these flags.
REDIRECT_OPEN_FLAGS: dict[str, int] = {
    '<':   os.O_RDONLY,
    '<>':  os.O_RDWR | os.O_CREAT,
    '>':   os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
    '>|':  os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
    '>>':  os.O_WRONLY | os.O_CREAT | os.O_APPEND,
}



class FileRedirector:
    """Handles file-based I/O redirections.

    FileRedirector is the fd-universe backend (`apply_fd_plan` and friends),
    but a subset of its methods are *shared redirect primitives* reused by the
    builtin stream-redirect backend in ``manager.py`` and by ``planner.py``.
    Those primitives carry no leading underscore — they are a deliberate,
    stable public surface (e.g. ``redirect_input_from_file``,
    ``redirect_heredoc``, ``redirect_herestring``, ``redirect_readwrite``,
    ``check_noclobber``, ``noclobber_blocks``, ``dup_fd_valid``,
    ``expand_redirect_target``, ``resolve_dynamic_dup``, ``procsub_handler``).
    Underscore-prefixed methods remain private to this module.
    """

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state
        self.planner = RedirectPlanner(self)

    def noclobber_blocks(self, target) -> bool:
        """True when noclobber forbids `>` to this target (bash semantics).

        noclobber protects only existing REGULAR files: `> /dev/null` and
        writes to FIFOs or other device files are always allowed, because
        opening a non-regular file for write destroys nothing. A dangling
        symlink also blocks — bash opens with O_CREAT|O_EXCL when the stat
        target is missing, and the link itself makes that open fail EEXIST.

        Shared redirect primitive: used by every redirect path (fd backend and
        the builtin stream backend); the response differs (raise in the parent,
        os._exit in a forked child), but the condition is one place.
        """
        if not self.state.options.get('noclobber', False):
            return False
        try:
            st = os.stat(target)  # follows symlinks, like bash's stat()
        except OSError:
            # Target doesn't stat: nonexistent (allowed — the redirect will
            # create it) unless it's a dangling symlink (blocked, see above).
            return os.path.islink(target)
        return stat.S_ISREG(st.st_mode)

    def dup_fd_valid(self, dup_fd: int) -> bool:
        """True when dup_fd is currently an open file descriptor (for >&/<&).

        Shared redirect predicate on the file-redirector's public surface,
        used to validate a ``>&``/``<&`` dup target.
        """
        try:
            fcntl.fcntl(dup_fd, fcntl.F_GETFD)
            return True
        except OSError:
            return False

    def check_noclobber(self, target):
        """Raise OSError if noclobber is set and target exists.

        Shared redirect primitive (fd backend and builtin stream backend).
        """
        if self.noclobber_blocks(target):
            raise OSError(f"{target}: cannot overwrite existing file")

    def _is_filename_redirect(self, redirect) -> bool:
        """True for redirects whose target names a file to open/create.

        These are subject to bash's "ambiguous redirect" rule. Heredoc/
        here-string/fd-dup forms are NOT (their targets mean something else).
        """
        return (redirect.type in ('<', '>', '>>', '<>', '>|')
                or redirect.combined)

    @staticmethod
    def _word_is_process_sub(word) -> bool:
        """True if the Word is a process-substitution target (`<(cmd)`/`>(cmd)`).

        Such a target is resolved to a `/dev/fd/N` path from its AST node by the
        ProcessSubstitutionHandler (via the planner), not by field expansion,
        and is always a single fd path — never ambiguous.
        """
        return (len(word.parts) == 1
                and isinstance(word.parts[0], ExpansionPart)
                and isinstance(word.parts[0].expansion, ProcessSubstitution))

    def redirect_procsub_node(self, redirect):
        """Return the `ProcessSubstitution` node when this redirect's target is
        a WHOLE-WORD process substitution (`< <(cmd)`, `> >(cmd)`), else None.

        Shared redirect primitive: the planner calls this to decide procsub-ness
        STRUCTURALLY, from the Word AST the parser already built — it never
        re-sniffs the expanded string. That layering fixed two bugs: a quoted
        literal `'<(echo x)'` was executed as a command (the sniff matched the
        post-expansion text), and a `<(echo $x)` body was variable-expanded
        once in the parent and again in the child. A redirect whose Word is not
        a whole-word procsub is a filename, full stop. Only filename-target
        redirects can carry one (heredoc/dup/close targets mean something else).
        """
        if not self._is_filename_redirect(redirect):
            return None
        word = getattr(redirect, 'target_word', None)
        if word is not None and self._word_is_process_sub(word):
            return word.parts[0].expansion
        return None

    def expand_redirect_target(self, redirect):
        """Expand a FILENAME redirect target, enforcing bash's "ambiguous
        redirect" rule.

        Shared redirect primitive: the planner calls this for every NON-procsub
        filename redirect, and ``apply_var_fd_redirect`` for ``{fd}>file``.
        Process-substitution targets never reach here — the planner detects them
        structurally (``redirect_procsub_node``) and resolves them from their
        AST node, so nothing re-sniffs the expanded string.

        For filename-target redirects (`<`/`>`/`>>`/`<>`/`>|`/`&>`/`&>>`) with
        a parsed Word, expand through the full command-argument pipeline
        (variable/command/arithmetic expansion, IFS word-splitting of unquoted
        expansions, and globbing — an EMBEDDED procsub like ``pre<(cmd)post``
        resolves to its ``/dev/fd/N`` path here). bash requires the result to be
        EXACTLY one word: zero words (unset/empty unquoted target) or more than
        one word (`$v` with v="a b", a glob matching ≥2 files) is an "ambiguous
        redirect" error — and NOTHING is opened. A quoted target suppresses
        splitting/globbing, so it always yields one field and is never
        ambiguous.

        Raised as an OSError with errno=None so the existing redirect-error
        formatters print it verbatim (`psh: <word>: ambiguous redirect`) in
        both the parent (raise → exit 1) and child (`os._exit(1)`) paths.
        """
        target = redirect.target
        if not self._is_filename_redirect(redirect):
            return target

        word = getattr(redirect, 'target_word', None)
        if word is None:
            # Synthesized redirect with no parsed Word (both parsers always
            # attach one for a real filename redirect): use the literal target.
            return target
        from ..expansion.word_expansion_types import COMMAND_ARGUMENT
        fields = self.shell.expansion_manager.expand_word_to_fields(
            word, COMMAND_ARGUMENT)
        if len(fields) != 1:
            # bash names the original (pre-expansion) target word.
            raise OSError(f"{word.source_text()}: ambiguous redirect")
        return fields[0]

    def redirect_input_from_file(self, target, redirect):
        """Open file for input and dup2 to the redirect's fd (default 0).

        Shared redirect primitive (fd backend and builtin stream backend).
        Honors an explicit source fd — ``exec 5<file`` must open fd 5,
        not clobber stdin. Returns the target fd.
        """
        target_fd = redirect.fd if redirect.fd is not None else 0
        fd = os.open(target, REDIRECT_OPEN_FLAGS['<'], 0o644)
        _dup2_preserve_target(fd, target_fd)
        return target_fd

    def _content_to_fd(self, content: str, target_fd: int):
        """Point `target_fd` at `content` via an anonymous (unlinked) temp file.

        A pipe would deadlock for content larger than the kernel pipe buffer
        (~64KB on most systems) because the whole body is written before any
        reader exists. Bash uses a temporary file for heredocs for the same
        reason.

        `target_fd` defaults to 0 (stdin) for plain `<<EOF`/`<<<word`, but an
        explicit fd prefix (`5<<EOF`, `5<<<word`) materializes the body on
        that fd instead, matching bash.
        """
        import tempfile
        tmp = tempfile.TemporaryFile()
        # surrogateescape so a heredoc/here-string body carrying non-UTF-8
        # bytes (surrogate escapes, e.g. a byte from `x=$(printf '\xff')`)
        # reaches the reader as its original byte, matching bash.
        tmp.write(content.encode('utf-8', errors='surrogateescape'))
        tmp.flush()
        tmp.seek(0)
        # Hand the body to target_fd through the shared fd-preserving primitive.
        # os.dup() FIRST gives an `opened` fd distinct from the temp object's own
        # fd, so closing the temp object can never reclaim target_fd — the bug
        # when tempfile happened to land ON target_fd (e.g. `cat 3<<EOF <&3`),
        # where the old "skip dup2 when fds match, then tmp.close()" closed the
        # very fd holding the body.
        opened = os.dup(tmp.fileno())
        tmp.close()
        _dup2_preserve_target(opened, target_fd)

    @staticmethod
    def _heredoc_fd(redirect) -> int:
        """Target fd for a heredoc/here-string: explicit prefix or stdin (0)."""
        return redirect.fd if redirect.fd is not None else 0

    def redirect_heredoc(self, redirect):
        """Point the redirect's fd (default stdin) at the heredoc content.

        Shared redirect primitive (fd backend and builtin stream backend).
        Returns the expanded content."""
        content = redirect.heredoc_content or ''
        if content and not getattr(redirect, 'heredoc_quoted', False):
            # Heredoc bodies are a dquote-like context for nested
            # ${x:-word} operands (bash keeps the quotes of ${x:-'q'});
            # $'...' stays literal there (DQ_STRING, not DQ_WORD).
            from ..expansion.operands import DQ_STRING
            content = self.shell.expansion_manager.expand_string_variables(
                content, quote_ctx=DQ_STRING)
        self._content_to_fd(content, self._heredoc_fd(redirect))
        return content

    def redirect_herestring(self, redirect):
        """Point the redirect's fd (default stdin) at the here-string content.

        Shared redirect primitive (fd backend and builtin stream backend).
        Returns the content."""
        word = getattr(redirect, 'target_word', None)
        if word is not None:
            # bash expands a here-string word like an assignment value: all
            # expansions, value-tilde (start + after each ':'), quote removal,
            # but NO word splitting and NO globbing. Per-part quoting is honored
            # (`foo$v"dq"` keeps the boundary; `'$v'` stays literal) instead of
            # flattening the word and re-expanding the joined text.
            expanded = self.shell.expansion_manager.expand_assignment_value_word(word)
        else:
            # Fallback for synthesized redirects without a parsed Word.
            quote_type = getattr(redirect, 'quote_type', None)
            if quote_type == "'":
                expanded = redirect.target
            else:
                target = redirect.target
                # An UNQUOTED here-string tilde-expands like a value (start +
                # after each ':'), BEFORE variable expansion (POSIX order). A
                # double-quoted here-string does not tilde-expand.
                if not quote_type:
                    target = self.shell.expansion_manager.expand_string_tildes(target)
                expanded = self.shell.expansion_manager.expand_string_variables(target)
        content = expanded + '\n'
        self._content_to_fd(content, self._heredoc_fd(redirect))
        return content

    def _redirect_output_to_file(self, target, redirect):
        """Open file for output and dup2 to target fd. Returns target_fd."""
        target_fd = redirect.fd if redirect.fd is not None else 1
        if redirect.type == '>':
            self.check_noclobber(target)
        fd = os.open(target, REDIRECT_OPEN_FLAGS[redirect.type], 0o644)
        _dup2_preserve_target(fd, target_fd)
        return target_fd

    def resolve_dynamic_dup(self, redirect):
        """Resolve a dynamic fd-dup target (e.g. ``>&$fd``, ``2>&$((n+1))``).

        Shared redirect primitive: the planner calls this for every backend.

        For ``>&``/``<&`` redirects whose source fd is given by an expansion,
        the parser leaves ``dup_fd=None`` and stores the (expandable) target
        string. Expand it now, parse it as an integer, and return a shallow
        copy carrying the resolved ``dup_fd`` so every existing dispatch path
        (which reads ``redirect.dup_fd``) works unchanged. The original AST node
        is not mutated, so re-execution (e.g. in a loop) re-resolves each time.

        Non-dup, static (``2>&1``), or close (``>&-``) redirects are returned
        unchanged. Raises OSError for a non-numeric target (bash: "ambiguous
        redirect").
        """
        if redirect.type not in ('>&', '<&') or redirect.combined:
            # A csh-style `>&word` combined redirect keeps type '>&' but is a
            # file target, not a dup — never resolve it as a dynamic fd.
            return redirect
        if redirect.dup_fd is not None or not redirect.target or redirect.target == '-':
            return redirect
        expanded = self.shell.expansion_manager.expand_string_variables(
            redirect.target).strip()
        try:
            fd = int(expanded)
        except ValueError:
            raise OSError(f"{expanded}: ambiguous redirect") from None
        resolved = copy.copy(redirect)
        resolved.dup_fd = fd
        return resolved

    def apply_var_fd_redirect(self, redirect):
        """Allocate (or close) a named file descriptor for ``{varname}>...``.

        bash semantics: the shell allocates a free fd >= 10, performs the
        redirect onto it, and stores the number in ``redirect.var_fd``. The
        allocation is PERMANENT (parent-side, not part of any command's
        save/restore window) — the user closes it with ``{varname}>&-``, which
        closes the fd named by the variable (the variable keeps its value).
        Reached from all FOUR redirect-application paths: the in-process
        builtin path (manager.py:501, IOManager.setup_builtin_redirections),
        the forked-child path (manager.py:895,
        IOManager.setup_child_redirections), the fd-level save/restore window
        (_apply_redirections here, via IOManager.apply_redirections /
        with_redirections), and the exec path (apply_permanent_redirections
        here).
        """
        name = redirect.var_fd
        rtype = redirect.type

        # Close form: {fd}>&- / {fd}<&- — close the fd named by the variable.
        if rtype in ('>&-', '<&-'):
            try:
                fdnum = int(self.shell.state.get_variable(name))
            except (TypeError, ValueError):
                return
            try:
                os.close(fdnum)
            except OSError:
                pass
            return

        # Duplicate form: {fd}>&N / {fd}<&N (incl. dynamic {fd}>&$x).
        if rtype in ('>&', '<&'):
            dup_fd = self.resolve_dynamic_dup(redirect).dup_fd
            if dup_fd is None or not self.dup_fd_valid(dup_fd):
                raise OSError(f"{dup_fd}: Bad file descriptor")
            newfd = fcntl.fcntl(dup_fd, fcntl.F_DUPFD, 10)
            self.shell.state.set_variable(name, str(newfd))
            return

        # Open-a-file forms: allocate the lowest free fd >= 10 (F_DUPFD).
        if rtype not in REDIRECT_OPEN_FLAGS:
            raise OSError(f"{rtype}: unsupported named-fd redirect")
        target = self.expand_redirect_target(redirect)
        if rtype == '>':
            self.check_noclobber(target)
        opened = os.open(target, REDIRECT_OPEN_FLAGS[rtype], 0o644)
        try:
            newfd = fcntl.fcntl(opened, fcntl.F_DUPFD, 10)
        finally:
            os.close(opened)
        self.shell.state.set_variable(name, str(newfd))

    def _redirect_dup_fd(self, redirect):
        """Handle >&/<& fd duplication (and the move form). Validates source fd."""
        if redirect.fd is not None and redirect.dup_fd is not None:
            if not self.dup_fd_valid(redirect.dup_fd):
                raise OSError(f"{redirect.dup_fd}: Bad file descriptor")
            os.dup2(redirect.dup_fd, redirect.fd)
            # Move form `[n]>&m-`: close the source m after duplicating it onto
            # n. bash keeps the fd open when source and destination coincide.
            if redirect.move and redirect.dup_fd != redirect.fd:
                try:
                    os.close(redirect.dup_fd)
                except OSError:
                    pass
        elif redirect.fd is not None and redirect.target == '-':
            try:
                os.close(redirect.fd)
            except OSError:
                pass

    def redirect_readwrite(self, target, redirect):
        """Open file for read-write (<>) and dup2 to target fd.

        Shared redirect primitive (fd backend and builtin stream backend).
        """
        target_fd = redirect.fd if redirect.fd is not None else 0
        fd = os.open(target, REDIRECT_OPEN_FLAGS['<>'], 0o644)
        _dup2_preserve_target(fd, target_fd)
        return target_fd

    def _redirect_clobber(self, target, redirect):
        """Force overwrite (>|), ignoring noclobber."""
        target_fd = redirect.fd if redirect.fd is not None else 1
        fd = os.open(target, REDIRECT_OPEN_FLAGS['>|'], 0o644)
        _dup2_preserve_target(fd, target_fd)
        return target_fd

    def _redirect_combined(self, target, redirect):
        """Redirect both stdout and stderr to file (&>, &>>, or csh-style >&).

        The type may be spelled `&>`/`&>>` or `>&` (csh `>&word`); only the
        `>>` suffix distinguishes append from truncate, so map onto the plain
        `>`/`>>` open flags.
        """
        is_append = redirect.type.endswith('>>')
        if not is_append:
            self.check_noclobber(target)
        fd = os.open(target, REDIRECT_OPEN_FLAGS['>>' if is_append else '>'],
                     0o644)
        _dup2_preserve_target(fd, 1)   # stdout
        os.dup2(1, 2)                  # stderr → stdout

    def _redirect_close_fd(self, redirect):
        """Handle >&-/<&- fd close."""
        if redirect.fd is not None:
            try:
                os.close(redirect.fd)
            except OSError:
                pass

    def _save_fd_high(self, fd: int):
        """Dup `fd` onto a HIGH fd (>= 10) so it can be restored later.

        Every temporary-redirect backup goes high, exactly as bash keeps its
        internal saved descriptors above fd 10. A plain ``os.dup`` takes the
        lowest free slot, which after ``exec 1>&-`` (or ``2>&-``) is fd 1 (or
        2) — a slot a stale ``sys.stdout``/``sys.stderr`` wrapper still names.
        The backup would then sit ON fd 1, so a builtin's write to
        ``sys.stdout`` lands in the backup (the shell's real stderr) instead
        of failing EBADF as bash does; and the freed low slot could not be
        reclaimed and re-closed by the redirect's own ``open()``. Forcing the
        backup to fd >= 10 keeps fds 0/1/2 out of its way (this is also why the
        combined ``&>`` save, which backs up BOTH 1 and 2, must go high).

        Returns the duplicate, or None if `fd` is not currently open (e.g. a
        high fd like `7>file`, or a low fd already closed by ``exec 1>&-`);
        restore then simply closes the fd again rather than restoring an
        original.
        """
        try:
            return fcntl.fcntl(fd, fcntl.F_DUPFD, 10)
        except OSError:
            return None

    def _validate_dup_source(self, redirect: Redirect) -> None:
        """Validate the source fd for >&/<& before saving target fds."""
        if (redirect.fd is not None and redirect.dup_fd is not None
                and not self.dup_fd_valid(redirect.dup_fd)):
            raise OSError(f"{redirect.dup_fd}: Bad file descriptor")

    def saved_fds_for_plan(self, plan: RedirectPlan) -> List[Tuple[int, int | None]]:
        """Return fd backups needed before applying a temporary plan.

        Every backup goes to a HIGH fd (``_save_fd_high``, see its docstring):
        a plain ``os.dup`` would land in a freed low slot (fd 1/2 after
        ``exec 1>&-``) that a stale ``sys.stdout``/``sys.stderr`` still aliases,
        so an in-process builtin's write would leak into the backup instead of
        failing EBADF like bash. ``_save_fd_high`` is tolerant: a closed fd
        yields None and restore closes it again.
        """
        redirect = plan.redirect
        if redirect.combined:
            return [(1, self._save_fd_high(1)), (2, self._save_fd_high(2))]
        if redirect.type in ('<', '<>', '<<', '<<-', '<<<',
                             '>|', '>', '>>'):
            return [(plan.target_fd, self._save_fd_high(plan.target_fd))]
        if redirect.type in ('>&', '<&'):
            self._validate_dup_source(redirect)
            saves: List[Tuple[int, int | None]] = []
            if (redirect.fd is not None
                    and (redirect.dup_fd is not None
                         or redirect.target == '-')):
                saves.append((redirect.fd, self._save_fd_high(redirect.fd)))
            # Move form also closes the source fd — back it up so a temporary
            # redirect (`echo x 3>&1-`) restores it after the command.
            if (redirect.move and redirect.dup_fd is not None
                    and redirect.dup_fd != redirect.fd):
                saves.append((redirect.dup_fd,
                              self._save_fd_high(redirect.dup_fd)))
            return saves
        if redirect.type in ('>&-', '<&-') and redirect.fd is not None:
            return [(redirect.fd, self._save_fd_high(redirect.fd))]
        return []

    def apply_fd_plan(self, plan: RedirectPlan) -> None:
        """Apply one resolved redirect plan in the fd universe."""
        redirect = plan.redirect
        target = plan.target

        if redirect.combined:
            self._redirect_combined(target, redirect)
        elif redirect.type == '<':
            self.redirect_input_from_file(target, redirect)
        elif redirect.type == '<>':
            self.redirect_readwrite(target, redirect)
        elif redirect.type in ('<<', '<<-'):
            self.redirect_heredoc(redirect)
        elif redirect.type == '<<<':
            self.redirect_herestring(redirect)
        elif redirect.type == '>|':
            self._redirect_clobber(target, redirect)
        elif redirect.type in ('>', '>>'):
            self._redirect_output_to_file(target, redirect)
        elif redirect.type in ('>&', '<&'):
            self._validate_dup_source(redirect)
            self._redirect_dup_fd(redirect)
        elif redirect.type in ('>&-', '<&-'):
            self._redirect_close_fd(redirect)

    def apply_redirections(self, redirects: List[Redirect]) -> List[Tuple[int, int | None]]:
        """Apply redirections and return list of (fd, saved_fd) for restoration.

        Transactional: if any redirect fails part-way through (e.g.
        `cmd >a >/bad/x`), the ones already applied are rolled back before
        the exception propagates, so the shell's fds are never left hijacked.
        """
        saved_fds: List[Tuple[int, int | None]] = []
        try:
            return self._apply_redirections(redirects, saved_fds)
        except Exception:
            self.restore_redirections(saved_fds)
            raise

    def _apply_redirections(self, redirects: List[Redirect],
                            saved_fds: List[Tuple[int, int | None]]) -> List[Tuple[int, int | None]]:
        """Apply redirections, appending (fd, saved_fd) pairs to saved_fds."""
        for redirect in redirects:
            if redirect.var_fd:
                # Named-fd redirect ({fd}>file): allocate a persistent fd >= 10
                # in THIS process and store its number in the variable. Not
                # added to saved_fds — it is never restored after the command
                # (bash keeps it open; the user closes it with {fd}>&-).
                self.apply_var_fd_redirect(redirect)
                continue
            plan = self.planner.plan(redirect)
            applied = False

            try:
                saved_fds.extend(self.saved_fds_for_plan(plan))
                self.apply_fd_plan(plan)
                applied = True
            finally:
                plan.close_procsub(applied=applied)

        return saved_fds

    def restore_redirections(self, saved_fds: List[Tuple[int, int | None]]):
        """Restore file descriptors from saved list.

        Restore in REVERSE order: with the same fd redirected twice
        (e.g. `{ cmd; } >a >b`), the first saved backup holds the
        original fd and must win, i.e. be restored last.
        """
        for fd, saved_fd in reversed(saved_fds):
            if saved_fd is None:
                # The fd wasn't open before we redirected it (e.g. 7>file);
                # close what we opened instead of restoring an original.
                try:
                    os.close(fd)
                except OSError:
                    pass
            else:
                os.dup2(saved_fd, fd)
                os.close(saved_fd)

    def dup_sharing_stream(self, fd: int, mode: str, *,
                           buffering: int = -1) -> TextIO:
        """A Python text stream that SHARES ``fd``'s open file description.

        Shared redirect primitive — the ONE dup+fdopen recipe for both
        universes. A builtin acts through the Python stream object while an
        external child (and any fd-level redirect) inherits the raw fd, so the
        two views MUST share one file offset. A second independent
        ``open(target, mode)`` would have its OWN offset (and would re-truncate
        in 'w' mode), making the writers/readers overwrite or restart each
        other. ``os.dup(fd)`` shares the open file description (offset and
        O_APPEND); the stream never owns ``fd`` itself, so replacing it later
        (a second ``exec >file``) closes only the dup.

        * OUTPUT (``mode='w'``, ``buffering=1``): after a permanent ``exec
          >file`` (``_rebind_output_stream``) or a builtin's ``n>&m`` dup —
          line-buffered so builtin writes interleave with fd-level writers like
          bash's unbuffered output.
        * INPUT (``mode='r'``/``'r+'``): a builtin's ``read`` and a child it
          spawns share ONE stdin position, so ``{ read a; read b; } < f`` and a
          mid-builtin child advance the same offset (a second open would
          restart at 0).

        surrogateescape keeps non-UTF-8 shell bytes transparent, matching the
        sys.std* byte policy set at psh's entry point.
        """
        return cast(TextIO, os.fdopen(os.dup(fd), mode, buffering=buffering,
                                      errors='surrogateescape'))

    def _rebind_output_stream(self, target_fd: int):
        """Point the shell's Python-level stdout/stderr at a redirected fd.

        Only fds 1 and 2 have Python stream counterparts; for any other fd
        (``exec 3>file``) the descriptor-level redirect is all there is.

        A permanent REOPEN after a permanent close also lands here, which
        replaces the ``_RawFdStream`` a permanent close installed. That swap
        is hygiene, not correctness — the raw stream would keep working
        (it follows the fd number) — but rebinding restores normal buffered
        block writes for the reopened stream.
        """
        if target_fd == 1:
            sys.stdout = self.dup_sharing_stream(1, 'w', buffering=1)
            self.shell.stdout = sys.stdout
            self.state.stdout = sys.stdout
        elif target_fd == 2:
            sys.stderr = self.dup_sharing_stream(2, 'w', buffering=1)
            self.shell.stderr = sys.stderr
            self.state.stderr = sys.stderr

    def _rebind_input_stream(self, target_fd: int):
        """Point the shell's Python-level stdin at redirected fd 0."""
        if target_fd == 0:
            sys.stdin = self.dup_sharing_stream(0, 'r')
            self.shell.stdin = sys.stdin
            self.state.stdin = sys.stdin

    def _snapshot_std_streams(self):
        """Capture sys/shell/state std streams for permanent-redirect rollback."""
        return (
            (sys.stdout, sys.stderr, sys.stdin),
            (self.shell.stdout, self.shell.stderr, self.shell.stdin),
            (self.state.stdout, self.state.stderr, self.state.stdin),
        )

    def _rollback_std_streams(self, snapshot):
        """Restore the streams captured by ``_snapshot_std_streams``, closing
        any stream this exec had newly rebound (so its dup'd fd is released)."""
        sys_streams, shell_streams, state_streams = snapshot
        for cur in (sys.stdout, sys.stderr, sys.stdin):
            if cur not in sys_streams:  # a stream this call rebound — close it
                try:
                    cur.close()
                except (OSError, ValueError):
                    pass
        sys.stdout, sys.stderr, sys.stdin = sys_streams
        self.shell.stdout, self.shell.stderr, self.shell.stdin = shell_streams
        self.state.stdout, self.state.stderr, self.state.stdin = state_streams

    def apply_permanent_redirections(self, redirects: List[Redirect]):
        """Apply redirections permanently (for exec builtin).

        Output branches do the fd-level redirect first, then rebind the
        Python-level stream onto the SAME open file description via
        _rebind_output_stream() — never a second independent open().

        All-or-nothing: if any redirect in the list fails, EVERY redirect
        already applied is rolled back (fds and Python streams restored) before
        the error propagates — bash undoes a failed exec's entire redirection
        list, so `exec 3>ok 4>/bad/x` leaves fd 3 closed, not pointing at ok.
        """
        # Pending buffered output belongs to the OLD destination; flush it
        # before the fd-level dup2 silently re-routes it to the new file.
        for stream in (self.state.stdout, self.state.stderr, sys.stdout, sys.stderr):
            try:
                stream.flush()
            except (OSError, ValueError):
                pass

        # Back up each fd and the Python streams before touching them, so a
        # later failure rolls the whole list back (bash semantics).
        saved_fds: List[Tuple[int, int | None]] = []
        saved_streams = self._snapshot_std_streams()
        # Streams an output-fd close (`exec >&-` after `exec >file`) orphaned:
        # dropped on SUCCESS only, so a later-redirect failure's rollback can
        # still restore them (symmetric with the saved_fds backups below).
        closed_dups: List[TextIO] = []
        try:
            for redirect in redirects:
                if redirect.var_fd:
                    # Named-fd redirect under `exec`: same persistent allocation
                    # (already permanent, so no stream rebind needed).
                    self.apply_var_fd_redirect(redirect)
                    continue
                plan = self.planner.plan(redirect)
                redirect = plan.redirect
                saved_fds.extend(self.saved_fds_for_plan(plan))
                applied = False

                try:
                    self.apply_fd_plan(plan)
                    # Rebind the Python-level stream onto the redirected fd.
                    # Dispatch by direction using the planner's target_fd (the
                    # single source of truth for which fd this redirect acts on)
                    # rather than re-enumerating every redirect.type: input forms
                    # (`<`, `<>`, `<<`, `<<-`, `<<<`) rebind stdin; output forms
                    # (`>`, `>>`, `>|`) rebind the target fd; `&>`/`&>>` rebind
                    # both 1 and 2; a `>&`/`<&` duplication rebinds its own fd;
                    # a `>&-` close of fd 1/2 points the stream at a sentinel.
                    if redirect.combined:
                        self._rebind_output_stream(1)
                        self._rebind_output_stream(2)
                    elif '&' in redirect.type:  # >& <& (dup) or >&- <&- (close)
                        if redirect.fd is not None and redirect.dup_fd is not None:
                            self._rebind_output_stream(redirect.fd)
                        else:
                            self._rebind_closed_output_stream(redirect, closed_dups)
                    elif redirect.type.startswith('<'):
                        self._rebind_input_stream(plan.target_fd)
                    else:  # '>', '>>', '>|'
                        self._rebind_output_stream(plan.target_fd)
                    applied = True
                finally:
                    plan.close_procsub(applied=applied)
        except Exception:
            self._rollback_std_streams(saved_streams)
            self.restore_redirections(saved_fds)
            raise

        # Success: the redirects are permanent. Close the fd backups so they
        # don't leak (they held the pre-exec descriptions, now superseded)...
        for _fd, saved in saved_fds:
            if saved is not None:
                try:
                    os.close(saved)
                except OSError:
                    pass
        # ...and drop any dup an output-fd close orphaned (the dup an earlier
        # `exec >file` had installed as sys.stdout/the state override).
        for dup in closed_dups:
            try:
                dup.close()
            except (OSError, ValueError):
                pass

    def _rebind_closed_output_stream(self, redirect: Redirect,
                                     closed_dups: List[TextIO]) -> None:
        """Reach the stream universe for a permanent ``>&-`` output-fd close.

        The fd-level close already happened (``apply_fd_plan`` →
        ``_redirect_close_fd``). But a builtin writes through the Python stream
        object, not the raw fd, so the stream half must be handled too. The
        stream left in ``sys.std*`` after the close is either:

        * the natural buffering ``TextIOWrapper`` that WRAPS the std fd (no
          prior ``exec >file`` override — the common case), or
        * a *dup* of an earlier ``exec >file`` target bound as
          ``sys.std*``/``state.std*`` (the with-override case).

        Both are wrong to leave in place. The natural wrapper BUFFERS a builtin's
        post-close write; its flush fails EBADF, but the retained bytes later
        flush into a REOPENED fd of the same number at shutdown (MED-1, the
        exec-close-then-reopen leak). The override dup does not reflect the
        fd-level close at all, so writes keep leaking into the old file
        (``exec >f; exec >&-; echo two`` → ``two`` into ``f``).

        Replace it with a ``_RawFdStream`` on the fd number (write→``os.write``):
        no buffer to leak, yet transparent — a compound/function body that
        re-points the fd at a live target at the fd level (``f 1>&2``,
        ``{ ...; } >g``) still lands, exactly as the natural wrapper did. A
        permanent reopen (``exec >&3``, ``exec >f``) routes through
        ``_rebind_output_stream`` and installs a normal buffered stream, dropping
        the raw one. Point the ``shell``/``state`` override at it too, so a
        builtin writing through ``state.std*`` behaves identically.

        The displaced stream is only handed to ``closed_dups`` (closed on
        success) when it was an override *dup* — that dup owns a descriptor that
        must not leak. The natural wrapper owns the std fd itself (already
        closed) and is kept alive by ``sys.__std*__`` until shutdown; closing it
        here could land an ``os.close`` on a same-``exec`` reopen of that fd
        number, and it is harmless (swapped out before any write, so empty), so
        leave it.

        Input closes (``<&-``) and closes of fd >= 3 have no output-stream
        counterpart: ``output_close_fd`` returns ``None`` and this is a no-op.
        """
        io = self.shell.io_manager
        target_fd = io.output_close_fd(redirect)
        if target_fd is None:
            return
        _, stdout_ov, stderr_ov = self.state.streams.snapshot()
        had_override = (stdout_ov if target_fd == 1 else stderr_ov) is not None
        displaced = io.swap_output_stream_reopenable(target_fd)
        # Point the shell/state override at the raw stream too (sys.std* now
        # holds it), so a builtin writing through state.stdout/stderr behaves
        # the same as one writing through sys.stdout/stderr.
        if target_fd == 1:
            self.shell.stdout = sys.stdout
        else:
            self.shell.stderr = sys.stderr
        if had_override:
            closed_dups.append(displaced)

    @property
    def procsub_handler(self):
        """The shell's ProcessSubstitutionHandler (resolves redirect targets).

        Shared redirect primitive (used by the planner for every backend).

        Looked up through shell.io_manager at call time because the IOManager
        constructs the FileRedirector before the handler exists.
        """
        return self.shell.io_manager.process_sub_handler
