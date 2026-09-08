"""File redirection implementation."""
import copy
import errno
import fcntl
import os
import resource
import stat
import sys
import weakref
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TextIO, Tuple, cast

from ..ast_nodes import (
    ExpansionPart,
    HeredocRedirect,
    ProcessSubstitution,
    Redirect,
)
from ..core.process_lease import ComponentKind, get_coordinator
from .planner import RedirectPlan, RedirectPlanner
from .redirect_program import (
    RedirectOp,
    RedirectOpKind,
    is_self_dup,
    target_fd_of,
)

if TYPE_CHECKING:
    from ..core.state import ShellState
    from ..shell import Shell


#: The ONE user-facing explanation for a here-document whose body was never
#: collected. Every arm below appends it, so the diagnosis lives in one place.
#:
#: WHY IT NAMES ALIASES. Round-8 verification found the live route this module
#: previously called impossible: alias substitution happens AFTER the line has
#: been lexed, so an alias whose expansion introduces ``<<EOF`` puts a heredoc
#: operator into the token stream that heredoc collection never saw. bash
#: gathers such a body at expansion time; psh cannot yet, and the user who
#: typed the alias deserves to be told which construct is unsupported rather
#: than shown a Python repr plus an assurance that this cannot happen.
_ALIAS_HEREDOC_HINT = (
    "psh could not collect the here-document body. The usual cause is an "
    "ALIAS whose expansion introduces the `<<` operator: aliases are "
    "substituted after the line is lexed, so the body was never gathered and "
    "its lines will be read as commands. Write the here-document directly "
    "rather than through an alias.")


class NonExecutableRedirectError(RuntimeError):
    """A non-executable redirect parse state reached execution.

    Raised when a plain :class:`~psh.ast_nodes.redirects.Redirect` carrying a
    heredoc operator type — the INCOMPLETE parse state a bare token-level
    parse produces, with the bodies still in the token stream — is handed to
    the fd universe.

    REACHABILITY, corrected at round-8 verification. Every heredoc-aware parse
    path that COLLECTED the bodies builds a
    :class:`~psh.ast_nodes.redirects.HeredocRedirect` instead. The known live
    route to THIS class is ALIAS SUBSTITUTION, which happens after the lex: an
    alias expanding to ``cat <<EOF`` hands the parser a heredoc operator whose
    body was never gathered. So this is a SUPPORTED-INPUT LIMITATION reachable
    from ordinary user input, not an internal defect — the previous docstring
    claimed the opposite and ``alias foo='cat <<EOF'; foo`` falsifies it.

    Deriving from ``RuntimeError`` keeps it in the strict-errors-LOUD class of
    the expected-error taxonomy (``psh/core/CLAUDE.md``), so a genuinely
    INTERNAL arrival still fails the suite loudly instead of silently opening a
    file named after the delimiter. On the alias route the redirect layer
    catches and reports it, so the user sees the message and the script carries
    on — measured with strict-errors both on and off, identically.
    """


#: First fd slot for long-lived STD_FDS lease backups. Above the >=10
#: per-command save area (bash-pinned `{v}>file` numbering expects
#: first-free->=10), below nothing a user can't also claim — hence the
#: relocation protocol below when a user redirect targets a parked slot.
_PARKING_BASE = 63

#: Lowest fd the lease may ever park in. bash's ``{v}>file`` returns 10 at
#: EVERY RLIMIT_NOFILE (measured against bash 5.2.26 across limits 24-256:
#: its named-fd numbering does NOT degrade), so parking into the >=10 save
#: area would break a parity bash itself maintains.
_PARKING_FLOOR = 10

#: Slots the lease needs: CLOEXEC backups of fds 0, 1 and 2.
_PARKING_SLOTS = 3

#: Spare slots kept ABOVE the parked backups. The relocation protocol moves a
#: backup out of the way when a user redirect claims its fd, and that move is
#: a fresh ``F_DUPFD_CLOEXEC`` from the same base — so it needs somewhere to
#: land. Parking flush against the limit left nowhere: measured at
#: ``ulimit -n 50``, ``exec 3>f; exec 47>f2`` succeeds in bash and failed
#: EMFILE in psh. Three spares let all three backups relocate once.
_PARKING_SPARE = 3


def _parking_base() -> int:
    """The fd to park this process's std-fd backups at or above.

    ``_PARKING_BASE`` whenever the fd table is big enough — every ordinary
    process. Under a LOW ``RLIMIT_NOFILE`` there is no usable slot there:
    measured, at soft <= 63 the dup fails EINVAL (minfd at or beyond the
    limit) and at soft == 64 the first dup takes fd 63 and the next two fail
    EMFILE, because that window holds exactly one slot. NEITHER errno means
    the table is exhausted; both report that the parking base is too high
    for this limit, which is a configuration fact.

    Reading them as exhaustion made every permanent redirect fail under
    ``ulimit -n <= 64`` while bash succeeded (R8 BL-1). Parking as high as
    the limit allows, MINUS room for the relocation protocol to move a
    displaced backup, preserves every parity at once: the redirect works,
    user fds still start at 10, and a user redirect into the parking range
    can still displace what it finds there.
    """
    try:
        soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (OSError, ValueError):     # pragma: no cover - exotic platform
        return _PARKING_BASE
    if soft in (resource.RLIM_INFINITY, -1):
        return _PARKING_BASE
    return min(_PARKING_BASE,
               max(_PARKING_FLOOR, soft - _PARKING_SLOTS - _PARKING_SPARE))


class _StdStreamBaseline:
    """The restorable pre-permanent-redirect state of fds 0/1/2 + streams.

    Captured by ``FileRedirector._acquire_permanent_stream_lease`` as the
    STD_FDS component lease's baseline (campaign F2): CLOEXEC high dups of
    the standard descriptors (or None where a descriptor was closed), the
    ``sys.std*`` stream objects, and the shell's stream-override snapshot.
    ``restore`` — the lease's release hook — closes whatever streams the
    shell's permanent redirects installed (releasing their dup'd fds), puts
    the original ``sys.std*`` objects and override state back, and dup2s the
    saved descriptors onto 0/1/2 (re-closing one that was closed at
    baseline). Best-effort per step so one failed restore cannot strand the
    rest.

    Parked backups are USER-DISPLACEABLE (bash's model — internal saves get
    out of the user's way): a user redirection targeting a parked slot
    (``exec 63>f``, ``exec 64>&-``) must call :meth:`relocate_away_from`
    BEFORE mutating the fd, which moves the backup to a fresh CLOEXEC slot;
    without that, the user's dup2/close would silently replace the backup
    and the shutdown restore would install the USER'S file as the host's
    std fd (the F2 bounce blocker). ``active`` flips False at restore so a
    stale baseline (already released, or copied into a forked child) never
    relocates.
    """

    __slots__ = ('fds', 'sys_streams', 'overrides', '_state_ref', 'active',
                 '__weakref__')

    def __init__(self, fds: Dict[int, Optional[int]],
                 sys_streams: Tuple[Any, Any, Any],
                 overrides: Tuple[Any, Any, Any],
                 state: 'ShellState') -> None:
        self.fds = fds
        self.sys_streams = sys_streams
        self.overrides = overrides
        # WEAK: ComponentLease requires a restore callable that does not pin
        # the owning shell, and this baseline is reached from the coordinator
        # through the lease's restore. Holding `state` strongly kept a shell
        # dropped WITHOUT close() alive inside the coordinator's own
        # component list, so it never collected and its leases rejected every
        # later shell (slot 4A.1 probe B-01). The strong half was only ever
        # needed for the shell's own stream OVERRIDES, which are moot once
        # the shell is unreachable; the fd and sys.std* restore below is
        # what the hosting process actually needs back, and it runs either
        # way.
        self._state_ref: 'weakref.ref[ShellState]' = weakref.ref(state)
        self.active = True

    def relocate_away_from(self, target_fds) -> None:
        """Move any parked backup sitting on one of *target_fds*.

        Called by the redirect application paths BEFORE they dup2/close a
        user-chosen fd. The displaced backup keeps its open file description
        (``F_DUPFD_CLOEXEC`` from the parking base — first free slot, which
        skips both other parked fds and user-held fds) and the registry
        (``self.fds``) is updated, so the shutdown restore still finds the
        HOST's descriptors wherever they now live. An ``OSError`` from the
        dup (fd-table exhaustion) propagates: the user redirect then fails
        cleanly BEFORE any mutation, with the baseline intact.
        """
        if not self.active:
            return
        wanted = set(target_fds)
        for std_fd, saved in self.fds.items():
            if saved is not None and saved in wanted:
                # Same adaptive base as acquisition: relocating under a low
                # RLIMIT must land where a slot actually exists, or a user
                # redirect into the parking range would fail where bash's
                # succeeds.
                moved = fcntl.fcntl(saved, fcntl.F_DUPFD_CLOEXEC,
                                    _parking_base())
                self.fds[std_fd] = moved
                try:
                    os.close(saved)
                except OSError:
                    pass

    def restore(self) -> None:
        self.active = False
        # Streams first: flush + close any object a permanent redirect
        # installed (each owns a dup of the redirect target), then put the
        # baseline objects back.
        for name, baseline_stream in zip(('stdin', 'stdout', 'stderr'),
                                         self.sys_streams, strict=True):
            current = getattr(sys, name, None)
            if current is not None and current is not baseline_stream:
                for op in ('flush', 'close'):
                    try:
                        getattr(current, op)()
                    except Exception:
                        pass
            setattr(sys, name, baseline_stream)
        # Descriptors: dup2 the saved originals back (closing the backups);
        # a descriptor that was CLOSED at baseline is closed again.
        for fd, saved in self.fds.items():
            if saved is None:
                try:
                    os.close(fd)
                except OSError:
                    pass
                continue
            try:
                os.dup2(saved, fd)
            except OSError:
                pass
            try:
                os.close(saved)
            except OSError:
                pass
        # The shell's own stream overrides, only if the shell is still
        # reachable — restoring attributes of a collected shell is moot, and
        # the fd/sys.std* work above (what the HOSTING process needs back)
        # has already happened unconditionally.
        state = self._state_ref()
        if state is not None:
            state.streams.restore(self.overrides)


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
        #: Live STD_FDS baseline while this shell holds the lease (None
        #: otherwise): the relocation protocol's registry, cleared when a
        #: failed exec releases a lease it had just acquired.
        self._std_baseline: Optional[_StdStreamBaseline] = None

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
        target_fd = target_fd_of(redirect)
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

    def _content_to_free_fd(self, content: str) -> int:
        """Materialize `content` on a FRESH fd >= 10 and return the number.

        The `{v}<<EOF` twin of :meth:`_content_to_fd`: same unlinked-temp-file
        reasoning, but the body lands on a shell-allocated descriptor instead
        of a caller-named one, matching bash's named-fd allocation contract
        (lowest free fd >= 10, permanent until the user closes it).
        """
        import tempfile
        tmp = tempfile.TemporaryFile()
        tmp.write(content.encode('utf-8', errors='surrogateescape'))
        tmp.flush()
        tmp.seek(0)
        newfd = fcntl.fcntl(tmp.fileno(), fcntl.F_DUPFD, 10)
        tmp.close()
        return newfd

    @staticmethod
    def _heredoc_fd(redirect) -> int:
        """Target fd for a heredoc/here-string: explicit prefix or stdin (0)."""
        return target_fd_of(redirect)

    def redirect_heredoc(self, redirect: 'HeredocRedirect'):
        """Point the redirect's fd (default stdin) at the heredoc content.

        Shared redirect primitive (fd backend and builtin stream backend).
        Returns the expanded content.

        Takes a :class:`~psh.ast_nodes.redirects.HeredocRedirect`, whose body
        is non-optional — so "reached execution with no collected body" is not
        a state this function can be handed (remediation 2.5). The old
        late-discovery ``RuntimeError`` here is replaced by that type plus the
        explicit non-executable arm in :meth:`apply_fd_plan`."""
        if not isinstance(redirect, HeredocRedirect):
            # DIRECT-CALL boundary: the dispatchers gate on the type, but this
            # primitive is public and a caller can reach it with the
            # non-executable parse state. Same typed error as every other seam
            # (round-4 nits 11/18, the R9-B class) rather than a raw
            # AttributeError from the missing body field.
            raise NonExecutableRedirectError(
                f"here-document `{redirect.type}{redirect.target}` was never "
                f"collected (redirect_heredoc). {_ALIAS_HEREDOC_HINT}")
        content = self._heredoc_expanded_content(redirect)
        self._content_to_fd(content, self._heredoc_fd(redirect))
        return content

    def _heredoc_expanded_content(self, redirect: 'HeredocRedirect') -> str:
        """The heredoc body after expansion — THE one place that decides it.

        Shared by the stdin/explicit-fd path (:meth:`redirect_heredoc`) and the
        named-fd path (:meth:`apply_var_fd_redirect`), so `{v}<<EOF` cannot
        drift from `<<EOF` on quoting or expansion rules.
        """
        content = redirect.heredoc_content
        if content and not redirect.heredoc_quoted:
            # Heredoc bodies are a dquote-like context for nested
            # ${x:-word} operands (bash keeps the quotes of ${x:-'q'});
            # $'...' stays literal there (DQ_STRING, not DQ_WORD).
            from ..expansion.operands import DQ_STRING
            content = self.shell.expansion_manager.expand_string_variables(
                content, quote_ctx=DQ_STRING)
        return content

    def redirect_herestring(self, redirect):
        """Point the redirect's fd (default stdin) at the here-string content.

        Shared redirect primitive (fd backend and builtin stream backend).
        Returns the content."""
        content = self._herestring_expanded_content(redirect)
        self._content_to_fd(content, self._heredoc_fd(redirect))
        return content

    def _herestring_expanded_content(self, redirect) -> str:
        """The here-string content after expansion — THE one place that
        decides it, shared with the named-fd path."""
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
        return expanded + '\n'

    def _redirect_output_to_file(self, target, redirect):
        """Open file for output and dup2 to target fd. Returns target_fd."""
        target_fd = target_fd_of(redirect)
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

    def _publish_named_fd(self, name: str, newfd: int,
                          dup_fd: Optional[int] = None) -> None:
        """Record a freshly allocated named fd: the variable, then the cursor.

        The allocation contract shared by every ``{varname}`` form that
        produces an fd — open-a-file, dup, and heredoc/here-string alike. It
        lives in one place because the fd NUMBER only exists at apply time, so
        the variable that publishes it and the cursor facts about it must be
        written together; three copies of that pairing is three chances for a
        new form to publish the number and forget the registry.

        ``dup_fd`` is passed only by the dup form, which has a second
        cursor fact to record.
        """
        self.shell.state.set_variable(name, str(newfd))
        registry = self.shell.state.input_cursors
        # If this allocation belongs to a temporary frame, it is the frame's
        # to clean up — nothing earlier could scope it, since the redirect
        # node carries no fd for a named-fd spelling. HYGIENE, with no
        # reachable shell-level observable and so no M8 arm: a frame-scoped
        # allocation cannot be READ inside its own command (the variable
        # holding the number is set at apply time, after the command's words
        # were expanded), so the stale binding this prevents only becomes
        # wrong bytes if a later allocation reuses the number. Cheap, correct,
        # and declared rather than claimed to be load-bearing.
        registry.scope_fd(newfd)
        if dup_fd is not None:
            # A dup names the SAME open file description as its source, so it
            # shares that description's cursor — a byte already consumed
            # through the source is gone from the shared kernel offset, and a
            # fresh cursor here would leave it reachable through neither fd.
            registry.bind_dup(newfd, dup_fd)

    def apply_var_fd_redirect(self, redirect):
        """Allocate (or close) a named file descriptor for ``{varname}>...``.

        bash semantics: the shell allocates a free fd >= 10, performs the
        redirect onto it, and stores the number in ``redirect.var_fd``. The
        allocation is PERMANENT (parent-side, not part of any command's
        save/restore window) — the user closes it with ``{varname}>&-``, which
        closes the fd named by the variable (the variable keeps its value).
        Reached from all FOUR redirect-application paths: the in-process
        builtin path (``manager.py#IOManager.setup_builtin_redirections``),
        the forked-child path
        (``manager.py#IOManager.setup_child_redirections``),
        the fd-level save/restore window
        (_apply_redirections here, via IOManager.apply_redirections /
        guarded_redirections), and the exec path (apply_permanent_redirections
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
            self._publish_named_fd(name, newfd, dup_fd=dup_fd)
            return

        # Here-document / here-string forms: `{v}<<EOF`, `{v}<<-EOF`, `{v}<<<w`.
        # The content is materialized on a fresh fd >= 10 rather than on stdin,
        # and the number lands in the variable — the same allocation contract as
        # the open-a-file forms below, with the body as the source.
        #
        # The non-executable parse state gets the SAME typed error here as at
        # the two operator-string arms. This route reaches the fd universe
        # BEFORE either of those (var_fd is dispatched first), so without this
        # the value died on a raw AttributeError from the missing body field —
        # and it is a shape this slot CREATED: before the named-fd heredoc
        # fix, `cat {v}<<EOF` failed at parse time and no such value existed.
        if rtype in ('<<', '<<-') and not isinstance(redirect, HeredocRedirect):
            raise NonExecutableRedirectError(
                f"here-document `{{{name}}}{rtype}` was never collected. "
                f"{_ALIAS_HEREDOC_HINT}")
        if rtype in ('<<', '<<-', '<<<'):
            if rtype == '<<<' and redirect.target is None \
                    and getattr(redirect, 'target_word', None) is None:
                # The here-string twin of the arm above: an operand-less
                # `{v}<<<` reaching execution is the same non-executable parse
                # state, and died on a raw AttributeError from the None target.
                raise NonExecutableRedirectError(
                    f"here-string `{{{name}}}{rtype}` has no operand, so there "
                    "is nothing to redirect from.")
            content = (self._herestring_expanded_content(redirect)
                       if rtype == '<<<' else self._heredoc_expanded_content(redirect))
            newfd = self._content_to_free_fd(content)
            self._publish_named_fd(name, newfd)
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
        self._publish_named_fd(name, newfd)

    @staticmethod
    def _bad_dup_source_error(redirect: Redirect) -> OSError:
        """The one ``Bad file descriptor`` shape for an invalid dup SOURCE.

        bash names the SOURCE fd for the static spelling (``4>&9`` ->
        ``9: Bad file descriptor``) but the TARGET fd for the dynamic spelling
        (``4>&$x`` with x=9 -> ``4: Bad file descriptor``) — probe-verified,
        both directions.  A dynamically resolved redirect is recognizable
        post-resolution: ``resolve_dynamic_dup`` fills ``dup_fd`` on a COPY
        that keeps the expandable ``target`` text, while a static dup parses
        with ``target=None``.
        """
        was_dynamic = redirect.target not in (None, '', '-')
        name = redirect.fd if was_dynamic else redirect.dup_fd
        return OSError(f"{name}: Bad file descriptor")

    def _redirect_dup_fd(self, redirect):
        """Handle >&/<& fd duplication (and the move form). Validates source fd.

        ``n>&n`` (post-resolution) is bash's success no-op — see
        ``redirect_program.is_self_dup``; nothing is validated or changed.
        """
        if is_self_dup(redirect):
            return
        if redirect.fd is not None and redirect.dup_fd is not None:
            if not self.dup_fd_valid(redirect.dup_fd):
                raise self._bad_dup_source_error(redirect)
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
        target_fd = target_fd_of(redirect)
        fd = os.open(target, REDIRECT_OPEN_FLAGS['<>'], 0o644)
        _dup2_preserve_target(fd, target_fd)
        return target_fd

    def _redirect_clobber(self, target, redirect):
        """Force overwrite (>|), ignoring noclobber."""
        target_fd = target_fd_of(redirect)
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
        """Validate the source fd for >&/<& before saving target fds.

        ``n>&n`` skips validation entirely (bash's success no-op)."""
        if is_self_dup(redirect):
            return
        if (redirect.fd is not None and redirect.dup_fd is not None
                and not self.dup_fd_valid(redirect.dup_fd)):
            raise self._bad_dup_source_error(redirect)

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
            if is_self_dup(redirect):
                return []  # bash's n>&n success no-op: nothing changes,
                #            so nothing is saved or restored.
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

    def apply_plan_saving(self, plan: RedirectPlan,
                          saved_fds: List[Tuple[int, int | None]]) -> None:
        """Apply one ALREADY-RESOLVED plan in the temporary (save/restore) window.

        The three steps a temporary redirect owes its plan, in the one order
        that is correct: displace any parked STD_FDS backup off the fds this
        plan will take, take the fd backups, then apply. The backups are
        appended to *saved_fds* BEFORE ``apply_fd_plan`` runs, so an apply that
        fails still leaves the caller a complete restore list.

        The single entry point for applying a resolved plan temporarily, shared
        by the fd backend (``_apply_redirections``) and the in-process builtin
        backend (``IOManager._builtin_redirect_fd_level``). Taking the PLAN and
        not the ``Redirect`` is what makes the plan-once invariant structural:
        a caller holding a resolved plan has no way to ask for a second
        resolution, so a redirect target's command substitutions run once and
        its process substitutions fork once (C031). Process-substitution
        cleanup is NOT done here — it belongs to the caller, which alone knows
        whether the read end dies with the redirect (``plan.close_procsub``) or
        must outlive it (``plan.hand_procsub_to_scope``).
        """
        self._clear_user_fds_from_parking(plan)
        saved_fds.extend(self.saved_fds_for_plan(plan))
        self.apply_fd_plan(plan)

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
        elif isinstance(redirect, HeredocRedirect):
            self.redirect_heredoc(redirect)
        elif redirect.type in ('<<', '<<-'):
            # Structurally a heredoc, but the INCOMPLETE PARSE STATE (a bare
            # token-level parse, bodies still in the token stream) — never
            # executable. Explicit arm on purpose: without it this would fall
            # through the type-string chain and end up opening a file named
            # after the delimiter. Strict-errors-LOUD class so a genuinely
            # INTERNAL arrival still fails the suite (psh/core/CLAUDE.md's
            # expected-error taxonomy) -- but the message is written for the
            # user, because the alias route makes this reachable from ordinary
            # input (round-8 blockers 1+2).
            raise NonExecutableRedirectError(
                f"here-document `{redirect.type}{redirect.target}` was never "
                f"collected. {_ALIAS_HEREDOC_HINT}")
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
        """Apply redirections, appending (fd, saved_fd) pairs to saved_fds.

        One typed, source-ordered program applied left-to-right (the fd
        universe of the shared applicator) — the save/restore window backend.
        """
        program = self.planner.plan_program(redirects)

        def apply_one(op: RedirectOp) -> None:
            redirect = op.redirect
            if op.kind is RedirectOpKind.VAR_FD:
                # Named-fd redirect ({fd}>file): allocate a persistent fd >= 10
                # in THIS process and store its number in the variable. Not
                # added to saved_fds — it is never restored after the command
                # (bash keeps it open; the user closes it with {fd}>&-).
                self.apply_var_fd_redirect(redirect)
                return
            plan = self.planner.plan(redirect)
            op.plan = plan
            applied = False

            try:
                # Parking-clear, save, apply — the shared temporary-window
                # sequence (``apply_plan_saving``): a parked STD_FDS backup on
                # this plan's target fd moves out of the way BEFORE the save
                # (the vacated fd then saves as was-not-open, so the window's
                # restore simply re-closes it).
                self.apply_plan_saving(plan, saved_fds)
                applied = True
            finally:
                plan.close_procsub(applied=applied)

        program.apply_in_order(apply_one)
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

        The dup is ``F_DUPFD_CLOEXEC`` with a floor of 3, never a bare
        ``os.dup``: a bare dup takes the LOWEST free slot, and after a
        source-ordered ``1>&-``/``2>&-`` in the same command that slot is a
        std fd — the internal stream would occupy the very descriptor the
        user closed (a child would see it open, and the frame restore would
        later close the restored descriptor out from under the shell — the
        R1 bounce blocker).  CLOEXEC matches ``os.dup``'s PEP-446
        non-inheritability, so exec'd children never see the internal dup.

        surrogateescape keeps non-UTF-8 shell bytes transparent, matching the
        sys.std* byte policy set at psh's entry point.
        """
        dup = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 3)
        return cast(TextIO, os.fdopen(dup, mode, buffering=buffering,
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

    def _acquire_permanent_stream_lease(self) -> bool:
        """Acquire the STD_FDS component lease before the first permanent
        redirect (campaign F2). Returns True iff THIS call created the lease.

        The return value is the discrimination the failed-exec rollback needs
        (slot 4A.1): only a lease this command newly took may be released
        when the redirect then fails — an earlier successful ``exec >f``
        legitimately holds one, and a later failing ``exec >/bad`` must not
        release it.

        Captures the restorable baseline — CLOEXEC high dups of fds 0/1/2
        (``F_DUPFD_CLOEXEC``: a later successful ``os.exec`` must not leak
        the backups into the new image — bash-pinned by the exec-CLOEXEC
        test), the current ``sys.std*`` objects, and the shell's stream
        overrides — and registers ONE lease with the process coordinator.
        Idempotent: repeated permanent redirects (``exec >f1`` then
        ``exec >f2``) keep the FIRST baseline, so deactivation restores the
        pre-exec state, not an intermediate one. Permanent redirects remain
        permanent INSIDE the active shell (nothing restores between
        commands); the restore runs only when the owning shell deactivates
        (``Shell.close()``/``shutdown()``) — which for an EMBEDDED shell
        hands the hosting process its descriptors and streams back
        (continuation finding B), and for the ``python -m psh`` process is
        moot (the fd table dies with it).
        """
        coordinator = get_coordinator()
        state = self.state
        if coordinator.find_component(state, ComponentKind.STD_FDS) is not None:
            return False
        baseline_fds: Dict[int, Optional[int]] = {}
        parking_base = _parking_base()
        try:
            for fd in (0, 1, 2):
                try:
                    # High, NOT 10: the per-command save area starts at 10 and
                    # bash-pinned `{v}>file` allocations expect the first free
                    # fd >= 10 — long-lived lease backups parked at 10-12 would
                    # shift every later named-fd number (bash similarly parks
                    # its own long-lived internals high). F_DUPFD picks the
                    # first FREE slot, so acquisition automatically avoids fds
                    # the user already holds in the range; the reverse
                    # direction (a LATER user redirect targeting a parked slot)
                    # is the relocation protocol on _StdStreamBaseline. The
                    # base ADAPTS to RLIMIT_NOFILE (see _parking_base): under a
                    # low limit there is simply no slot at 63, and failing the
                    # redirect there diverged from bash.
                    baseline_fds[fd] = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC,
                                                   parking_base)
                except OSError as exc:
                    # ONLY a genuinely closed descriptor records None. That
                    # encoding is what `restore` reads as "this fd was closed
                    # at baseline, close it again", so it must not double as
                    # "we could not dup it": otherwise every dup failing
                    # recorded None, the exec still reported success, and
                    # close() then closed the HOST's fds 0/1/2 (R8 BL-1's
                    # predecessor defect). Any other errno means the baseline
                    # is unknowable and the acquisition aborts transactionally
                    # through the handler below — but only AFTER the adaptive
                    # base has been tried, since EINVAL/EMFILE at a too-high
                    # base is a configuration fact, not exhaustion.
                    if exc.errno != errno.EBADF:
                        raise
                    baseline_fds[fd] = None  # fd closed at baseline
            baseline = _StdStreamBaseline(
                fds=baseline_fds,
                sys_streams=(sys.stdin, sys.stdout, sys.stderr),
                overrides=state.streams.snapshot(),
                state=state,
            )
            coordinator.acquire_component(
                state, ComponentKind.STD_FDS, restore=baseline.restore,
                description='standard fds/streams (permanent exec redirects)',
                on_grant=state._on_activation_grant)
            # Live registry for the relocation protocol: every redirect
            # application consults it before taking a user-chosen fd.
            self._std_baseline = baseline
            return True
        except BaseException:
            # Failed acquisition rolls back completely: close the dups we
            # took so nothing is half-acquired (coordinator state untouched).
            for saved in baseline_fds.values():
                if saved is not None:
                    try:
                        os.close(saved)
                    except OSError:
                        pass
            raise

    def _release_permanent_stream_lease(self) -> None:
        """Release a STD_FDS lease THIS command acquired (failed exec).

        The lease is taken from the redirect list's SHAPE, before anything is
        known about whether the redirect can succeed (probe B-14: acquisition
        precedes the target open). When the redirect then fails, fds 0/1/2
        were never changed — but the lease, its parked backups and the
        ``_std_baseline`` registration were all retained, so a shell that
        redirected nothing still claimed the process's standard descriptors
        and rejected unrelated shells (slot 4A.1 probes B-05 / B-11).

        Only ever called with a lease this command created; an earlier
        successful ``exec >f`` keeps its own (B-06/B-12). Releasing runs the
        baseline restore, which closes the parked dups and puts the streams
        back — harmless after the caller has already rolled the fds back,
        since the baseline describes exactly that state.
        """
        lease = get_coordinator().find_component(self.state,
                                                 ComponentKind.STD_FDS)
        self._std_baseline = None
        if lease is not None:
            lease.release()

    @staticmethod
    def _fds_claimed_by_plan(plan: RedirectPlan) -> set:
        """The fd numbers this redirect will WRITE (dup2) or CLOSE.

        The relocation protocol's input: any parked STD_FDS backup sitting
        on one of these must move first. Covers the combined form (1 and 2),
        close forms (explicit or default fd), dup destinations plus the
        move form's closed source, and every open/heredoc form's target fd.
        Read-only uses of an fd (a dup SOURCE that stays open) claim
        nothing.
        """
        redirect = plan.redirect
        if redirect.combined:
            return {1, 2}
        if redirect.type in ('>&-', '<&-'):
            return {target_fd_of(redirect)}
        claimed = {plan.target_fd}
        if (redirect.type in ('>&', '<&') and redirect.move
                and redirect.dup_fd is not None):
            claimed.add(redirect.dup_fd)   # move form closes its source
        return claimed

    def _clear_user_fds_from_parking(self, plan: RedirectPlan) -> None:
        """Displace parked STD_FDS backups from fds this plan will take.

        Called BEFORE ``saved_fds_for_plan``/``apply_fd_plan`` in both the
        temporary and the permanent application loop, so a user redirect
        targeting the parking range (``exec 63>f``, ``echo x 63>f``,
        ``exec 64>&-``) never silently replaces a host-fd backup (the F2
        bounce blocker: the shutdown restore would have installed the
        user's file as the host's std fd). No-ops when no live baseline
        exists in THIS process — a forked child's copied baseline is stale
        (its coordinator pid-reset the lease) and must not be shuffled.
        """
        baseline = self._std_baseline
        if baseline is None or not baseline.active:
            return
        if get_coordinator().find_component(
                self.state, ComponentKind.STD_FDS) is None:
            return  # stale (forked child / already released)
        baseline.relocate_away_from(self._fds_claimed_by_plan(plan))

    def _relocate_reserved_script_fd(self, plan: RedirectPlan) -> None:
        """Relocate the lazy SCRIPT_FILE reader off any fd this PERMANENT
        redirect will seize (campaign I2).

        Called from ``apply_permanent_redirections`` BEFORE the user's
        dup2/close, so ``exec 255>f`` / ``exec 255<&-`` (whatever high fd the
        reader landed on) moves the script descriptor to a fresh slot instead of
        clobbering the running script — bash owns its fd 255 the same way (probe
        O1). Only the permanent path calls this: a temporary redirect's
        save/restore already preserves the descriptor (and bash does not
        relocate for temp redirects). No-op when no script reader is registered
        (source/rc are eager; a forked child's map is empty)."""
        reserved = self.state.reserved_script_fds
        if not reserved:
            return
        for fd in self._fds_claimed_by_plan(plan):
            reader = reserved.get(fd)
            if reader is not None:
                reader.relocate_away_from(fd)

    def apply_permanent_redirections(self, redirects: List[Redirect]):
        """Apply redirections permanently (for exec builtin).

        Output branches do the fd-level redirect first, then rebind the
        Python-level stream onto the SAME open file description via
        _rebind_output_stream() — never a second independent open().

        All-or-nothing: if any redirect in the list fails, EVERY redirect
        already applied is rolled back (fds and Python streams restored) before
        the error propagates — bash undoes a failed exec's entire redirection
        list, so `exec 3>ok 4>/bad/x` leaves fd 3 closed, not pointing at ok.

        Permanent redirects mutate the PROCESS (fds 0/1/2, ``sys.std*``), so
        the first one acquires the coordinator's STD_FDS baseline lease
        (campaign F2; see ``_acquire_permanent_stream_lease``). A list of
        ONLY named-fd redirects (``exec {v}>file``) allocates user fds
        without touching the standard descriptors/streams and takes no
        lease — user fds are the user's to manage (bash: they survive
        ``exec`` and are closed explicitly), and the allocation numbering
        stays exactly bash's first-free->=10.
        """
        program = self.planner.plan_program(redirects)
        lease_acquired_here = False
        if any(op.kind is not RedirectOpKind.VAR_FD for op in program):
            lease_acquired_here = self._acquire_permanent_stream_lease()
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

        def apply_one(op: RedirectOp) -> None:
            redirect = op.redirect
            if op.kind is RedirectOpKind.VAR_FD:
                # Named-fd redirect under `exec`: same persistent allocation
                # (already permanent, so no stream rebind needed).
                self.apply_var_fd_redirect(redirect)
                return
            plan = self.planner.plan(redirect)
            op.plan = plan
            redirect = plan.redirect
            # Displace any parked STD_FDS backup this redirect targets
            # (user fds in the parking range must win — bounce blocker).
            self._clear_user_fds_from_parking(plan)
            # Relocate the lazy script descriptor off this fd if the user's
            # permanent redirect targets it (campaign I2 — cannot clobber).
            self._relocate_reserved_script_fd(plan)
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
                if op.kind is RedirectOpKind.COMBINED:
                    self._rebind_output_stream(1)
                    self._rebind_output_stream(2)
                elif op.kind in (RedirectOpKind.DUP_FD, RedirectOpKind.CLOSE_FD):
                    if is_self_dup(redirect):
                        pass  # bash's n>&n success no-op: streams untouched
                        #       (`exec 1>&1` after `exec 1>&-` stays closed).
                    elif redirect.fd is not None and redirect.dup_fd is not None:
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

        try:
            program.apply_in_order(apply_one)
        except Exception:
            self._rollback_std_streams(saved_streams)
            self.restore_redirections(saved_fds)
            if lease_acquired_here:
                # This command's own acquisition, and its redirect failed:
                # fds 0/1/2 are back at the values the lease was meant to
                # protect, so the lease describes nothing and must go
                # (slot 4A.1 / charter item 5). A lease an EARLIER exec took
                # is untouched — lease_acquired_here is False then.
                self._release_permanent_stream_lease()
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
