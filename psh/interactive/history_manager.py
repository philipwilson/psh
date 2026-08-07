"""Command history management."""
import fcntl
import os
from collections import Counter
from typing import TYPE_CHECKING, List, Optional

from ..expansion.pattern import match_shell_pattern
from .base import InteractiveComponent
from .line_editor_helpers import convert_multiline_to_single

if TYPE_CHECKING:
    from ..shell import Shell


class HistoryManager(InteractiveComponent):
    """Manages command history.

    The SOLE history writer is shell.add_history → add_to_history, fed by
    the source processor with the complete logical command (the line
    editor records nothing itself). The command must arrive RAW — bash
    stores lines verbatim (leading/trailing whitespace included) and the
    HISTCONTROL/HISTIGNORE filters below decide on the unmodified text,
    so callers must not normalize first (reappraisal #17 H7: a caller-side
    .strip() silently disabled ignorespace).

    ALIAS CONTRACT: the line editor's HistoryNavigator holds a reference
    to the ``state.history`` LIST OBJECT for the whole session, so every
    operation here must mutate it in place — rebinding ``state.history``
    to a new list silently disconnects up-arrow/Ctrl-R from all further
    commands (reappraisal #15 K1). Pinned by
    tests/unit/interactive/test_history_alias_contract.py.

    Persistence is concurrency-safe (v0.447): ``save_to_file`` appends only
    THIS session's new entries under an exclusive file lock, merging with
    whatever other shells have written since we loaded — so several terminals
    sharing one history file no longer clobber each other (the old
    truncate-and-rewrite made the last shell to exit overwrite the rest).

    TWO INDEPENDENT QUANTITIES track our relationship to the history file, and
    conflating them was MEDIUM-7:

    * ``_pending`` — the entries RECORDED this session and not yet written.
      An entry is pending iff it entered memory through the recording pipeline
      (a typed line, or a ``history -s`` store) and has not since been written
      by ``-a``/``-w``/the exit save. Lines that entered via ``-r``/``-n`` or
      the startup load are NEVER pending: they are already in a file, and
      re-appending them was how another file's contents leaked into $HISTFILE.
      Pending is a MULTISET VIEW of memory, resolved by ``_pending_entries``:
      an entry that leaves ``state.history`` by ANY route — the HISTSIZE
      front-drop, ``-d``, ``-c``, erasedups, or the builtin's own CV3 strip —
      thereby leaves pending, so nothing is ever resurrected into the file
      after it is gone from memory.
    * ``_file_read_len`` — how many lines of the DEFAULT file have been
      consumed into memory (startup load, ``-r``/``-n`` of that file).
      ``history -n`` resumes from here. It is a position in the FILE, so
      memory-side operations (``-d``, ``-c``, the trim) never move it.

    This DELIBERATELY diverges from bash on interleaved compositions. bash's
    ``-a`` is not a marker at all: it writes the LAST N entries of the list by
    POSITION, where N counts session-recorded lines plus ``-n``-read lines, so
    a read or a ``-d`` between recording and saving makes bash write the wrong
    entries — losing typed commands and leaking read ones (measured against
    bash 5.2.26). psh keeps the v0.447 no-loss/no-duplicate guarantee instead;
    the state-machine observables (the in-memory list, cursor behaviour, exit
    status) still match bash.

    Every file path (load/save/-w/-a/-r/-n) opens with
    ``encoding='utf-8', errors='surrogateescape'`` (campaign I4; I1 byte
    doctrine) so arbitrary bytes round-trip: a malformed byte loads as a lone
    surrogate and re-encodes to the same byte on write, never raising
    ``UnicodeDecodeError``.
    """

    def __init__(self, shell: 'Shell') -> None:
        super().__init__(shell)
        # Entries recorded this session and not yet written to any file.
        # Resolved against memory by _pending_entries() before every write.
        self._pending: List[str] = []
        # Count of the default history file's lines already consumed into the
        # in-memory list (startup load + `history -r`/`-n` of the default
        # file). `history -n` uses this to append only lines it hasn't read yet.
        self._file_read_len = 0

    # -- the pending set (the ONE maintenance site) --------------------------

    def _pending_entries(self) -> List[str]:
        """The pending entries that are STILL in memory, in memory order.

        Pending is a multiset view rather than an index, so it survives every
        way an entry can leave ``state.history`` — including the history
        builtin's own CV3 strip, which deletes directly. Two identical pending
        entries resolve to two occurrences (and to one if only one survives),
        which is what keeps duplicate command strings saved exactly once each.
        """
        wanted = Counter(self._pending)
        out: List[str] = []
        for entry in self.state.history:
            if wanted[entry] > 0:
                wanted[entry] -= 1
                out.append(entry)
        return out

    def _prune_pending(self) -> None:
        """Re-resolve pending against memory after a mutation drops entries."""
        self._pending = self._pending_entries()

    def _mark_written(self) -> None:
        """Everything pending has just reached a file."""
        self._pending = []

    def _histcontrol_options(self) -> set:
        """The effective HISTCONTROL value set (``ignoreboth`` expanded)."""
        raw = self.state.get_variable('HISTCONTROL', '') or ''
        opts = {o for o in raw.split(':') if o}
        if 'ignoreboth' in opts:
            opts.update({'ignorespace', 'ignoredups'})
        return opts

    def _histignore_matches(self, command: str) -> bool:
        """True if *command* matches any HISTIGNORE pattern (bash).

        HISTIGNORE is a colon-separated list of glob patterns; a pattern must
        match the WHOLE line (no implicit ``*``). ``&`` matches the previous
        history line. Checked after the HISTCONTROL filters.

        Matching routes through the ONE shell pattern engine (not stdlib
        ``fnmatch``) so a HISTIGNORE pattern is not exempt from the shell's glob
        semantics: it honors ``\\`` escapes and — when ``shopt -s extglob`` is
        set — extglob groups (bash uses ``FNM_EXTMATCH`` there), and never
        backtracks exponentially. Case-sensitive (bash).
        """
        raw = self.state.get_variable('HISTIGNORE', '') or ''
        patterns = [p for p in raw.split(':') if p]
        if not patterns:
            return False
        extglob = self.state.options.get('extglob', False)
        prev = self.state.history[-1] if self.state.history else None
        for pat in patterns:
            if pat == '&':
                if command == prev:
                    return True
            elif match_shell_pattern(command, pat, extglob_enabled=extglob):
                return True
        return False

    def _erase_duplicates(self, command: str) -> None:
        """Remove every prior occurrence of *command* (HISTCONTROL erasedups).

        Erased copies leave memory, so they leave pending too — an erased entry
        must not be resurrected into the file by a later save. The file is
        append-only, so on-disk copies of erased dups remain: erasedups is
        in-session here."""
        hist = self.state.history
        hist[:] = [h for h in hist if h != command]
        self._prune_pending()

    def _ignorespace_blocks(self, command: str) -> bool:
        """HISTCONTROL ``ignorespace``: a line beginning with a space is not
        recorded. Checked on the RAW line, before any multi-line join."""
        return ('ignorespace' in self._histcontrol_options()
                and command[:1] == ' ')

    def _record(self, command: str) -> bool:
        """The ONE recording policy: HISTIGNORE + dup filtering + append + the
        HISTSIZE trim. Returns True iff an entry was appended.

        Both producers reach the list through here — a typed line (via
        ``add_to_history``) and an explicit ``history -s`` store (via
        ``store_entry``) — because bash applies the SAME policy to both:
        ignorespace/ignoredups/erasedups, HISTIGNORE matched against the
        STORED text, and the HISTSIZE cap all fire for ``-s`` exactly as they
        do for a typed command (probed against bash 5.2.26; the pre-4B.3 claim
        that ``-s`` was exempt was measured false). What ``-s`` does NOT get is
        the cmdhist join — see ``store_entry``.
        """
        histcontrol = self._histcontrol_options()
        # HISTIGNORE: drop lines matching any colon-separated glob pattern.
        if self._histignore_matches(command):
            return False
        if 'erasedups' in histcontrol:
            self._erase_duplicates(command)
        elif 'ignoredups' in histcontrol:
            # Drop a line identical to the immediately previous entry.
            if self.state.history and self.state.history[-1] == command:
                return False
        self.state.history.append(command)
        self._pending.append(command)
        self._trim_to_max()
        return True

    def _trim_to_max(self) -> None:
        """Enforce $HISTSIZE on the in-memory list, dropping from the FRONT.

        Dropped entries leave pending with them, so a trimmed-away command is
        never written later. (The v0.447 regression was the index form of this:
        a stale marker made the save slice skip genuinely-new entries. Pending
        being a view of memory removes the arithmetic that could go stale.)
        The READ cursor is deliberately NOT shifted: it is a position in the
        FILE, which a memory-side trim does not move (bash 5.2.26 leaves its
        file counter untouched across front-drops from either producer).
        """
        if len(self.state.history) > self.state.max_history_size:
            dropped = len(self.state.history) - self.state.max_history_size
            del self.state.history[:dropped]
            self._prune_pending()

    def add_to_history(self, command: str) -> bool:
        """Add a typed command to history; return True iff an entry was
        appended.

        A multi-line command becomes ONE entry, joined into its
        single-line ``; `` form like bash's cmdhist option (the joiner
        itself preserves newlines inside quoted strings, heredocs and
        command substitutions verbatim, also matching bash).

        Filtering matches bash: by default EVERY line is recorded (no dedup);
        ``ignorespace`` drops a line beginning with a space and the rest of the
        policy lives in ``_record``. The False return (line was filtered out) is
        what lets ``history -p``/``-s`` know NOT to strip a prior entry as if it
        were their own invocation (CV3).
        """
        if self._ignorespace_blocks(command):
            return False
        if '\n' in command:
            command = convert_multiline_to_single(command)
        return self._record(command)

    def load_from_file(self) -> None:
        """Load command history from file."""
        read = 0
        try:
            if os.path.exists(self.state.history_file):
                with open(self.state.history_file, 'r',
                          encoding='utf-8', errors='surrogateescape') as f:
                    for line in f:
                        line = line.rstrip('\n')
                        if line:
                            self.state.history.append(line)
                            read += 1
                # Trim to max size
                if len(self.state.history) > self.state.max_history_size:
                    del self.state.history[:-self.state.max_history_size]
        except OSError:
            # Silently ignore history file errors
            pass
        # Everything loaded is already on disk, so nothing is pending.
        self._pending = []
        # We have now consumed the whole file, so `history -n` starts from here.
        self._file_read_len = read

    def save_to_file(self) -> None:
        """Persist this session's new history entries (concurrency-safe).

        Rather than truncate-and-rewrite the whole file (which makes the last
        shell to exit clobber every other shell sharing the file), this holds
        an exclusive lock, re-reads the current on-disk history (picking up
        entries other shells appended after we loaded), appends only OUR new
        entries, trims to ``$HISTFILESIZE`` (bash; falling back to
        ``max_history_size`` when unset), and writes the merged result back.
        Concurrent shells therefore serialize on the lock instead of
        overwriting one another.
        """
        new_entries = self._pending_entries()
        if not new_entries:
            return
        # bash trims the FILE to $HISTFILESIZE (distinct from $HISTSIZE, which
        # caps the in-memory list); fall back to max_history_size when unset.
        file_limit = self.state.max_history_file_size
        if file_limit is None:
            file_limit = self.state.max_history_size
        try:
            # O_RDWR|O_CREAT so a missing file is created; 0o600 keeps history
            # private (the old open(,'w') left it at the umask default).
            fd = os.open(self.state.history_file,
                         os.O_RDWR | os.O_CREAT, 0o600)
            with os.fdopen(fd, 'r+', encoding='utf-8',
                           errors='surrogateescape') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    existing = [ln.rstrip('\n') for ln in f if ln.strip()]
                    combined = existing + new_entries
                    # HISTFILESIZE=0 truncates the file to empty (bash). Guard
                    # this explicitly: combined[-0:] is combined[0:], i.e. the
                    # WHOLE list, so the naive slice would keep everything.
                    # (Unset arrives as the max_history_size fallback and
                    # negative/unlimited as sys.maxsize, so file_limit is never
                    # negative here -- only 0 needs the special case.)
                    if file_limit <= 0:
                        combined = []
                    elif len(combined) > file_limit:
                        combined = combined[-file_limit:]
                    f.seek(0)
                    f.truncate()
                    if combined:
                        f.write('\n'.join(combined) + '\n')
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            self._mark_written()
        except OSError:
            # Silently ignore history file errors
            pass

    def clear_history(self) -> None:
        """Clear command history (in-memory only — the FILE is untouched)."""
        self.state.history.clear()
        # Nothing is left in memory, so nothing is pending (invariant: pending
        # is a view of memory). A cleared entry is not resurrected on save.
        self._pending = []
        # The READ cursor is NOT reset. It records how much of the FILE has
        # been consumed, and clearing memory does not un-read the file: bash
        # 5.2.26 leaves its counter across `-c`, so a following `history -n`
        # brings in only lines that arrived since, not the whole file again
        # (LEDGER carry #32 / MEDIUM-7 leg C).

    # -- `history` file-sync operations -------------------------------------
    # These back the `history -w/-r/-a/-n` builtin flags. Which of the two
    # quantities each one may move depends on the TARGET:
    #   `_pending`        is session-wide — `-a` consumes it whichever file it
    #                     wrote, but `-w` only does so for the DEFAULT file
    #                     (writing elsewhere leaves $HISTFILE's entries owed).
    #   `_file_read_len`  is a position in the DEFAULT file, so ONLY reads of
    #                     that file move it; a read of an explicitly-named
    #                     other file leaves it alone.

    def _is_default_file(self, path: str) -> bool:
        try:
            return os.path.abspath(path) == os.path.abspath(self.state.history_file)
        except OSError:
            return False

    def store_entry(self, command: str) -> None:
        """`history -s`: add *command* as one entry without executing it.

        Subject to the SAME recording policy as a typed line — ignorespace,
        ignoredups, erasedups, HISTIGNORE (matched against the STORED text, not
        the invocation) and the HISTSIZE cap — because that is what bash 5.2.26
        does. It is NOT subject to the cmdhist join: bash stores an embedded
        newline verbatim, so ``history -s $'a\\nb'`` stays one entry containing
        a newline rather than becoming ``a; b``.

        In-place mutation throughout (via ``_record``) preserves the list-alias
        contract."""
        if self._ignorespace_blocks(command):
            return
        self._record(command)

    def write_history(self, path: Optional[str] = None) -> bool:
        """`history -w`: write the ENTIRE in-memory list to *path* (default
        $HISTFILE), truncating it first."""
        target = path or self.state.history_file
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8',
                           errors='surrogateescape') as f:
                if self.state.history:
                    f.write('\n'.join(self.state.history) + '\n')
        except OSError:
            return False
        # Only a write of the DEFAULT file makes the list "already persisted".
        # Writing somewhere else leaves $HISTFILE's pending entries pending —
        # advancing the marker for ANY target silently DROPPED them, so
        # `history -w otherfile` made the session's commands never reach
        # $HISTFILE at all (bash 5.2.26 still saves them; the previous claim
        # that bash "marks it written regardless of which file" was measured
        # false).
        if self._is_default_file(target):
            self._mark_written()
            self._file_read_len = len(self.state.history)
        return True

    def append_history(self, path: Optional[str] = None) -> bool:
        """`history -a`: append entries added since the last write/append to
        *path* (default $HISTFILE)."""
        target = path or self.state.history_file
        new_entries = self._pending_entries()
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8',
                           errors='surrogateescape') as f:
                if new_entries:
                    f.write('\n'.join(new_entries) + '\n')
        except OSError:
            return False
        # `-a` consumes the pending set for ANY target (bash's `-a` likewise
        # zeroes its counter whichever file it wrote), so the next
        # `-a`/exit-save won't duplicate them.
        self._mark_written()
        if self._is_default_file(target):
            self._file_read_len += len(new_entries)
        return True

    def read_history(self, path: Optional[str] = None) -> bool:
        """`history -r`: append ALL lines of *path* (default $HISTFILE) to the
        in-memory list."""
        target = path or self.state.history_file
        lines = self._read_file_lines(target)
        if lines is None:
            return False
        self.state.history.extend(lines)
        # Read lines are NEVER pending — they already live in a file. Adding
        # them to the pending set was how another file's contents leaked into
        # $HISTFILE; marking the WHOLE list synced instead swallowed the typed
        # commands that were still waiting to be saved.
        self._trim_to_max()
        if self._is_default_file(target):
            self._file_read_len = len(lines)
        return True

    def read_new_history(self, path: Optional[str] = None) -> bool:
        """`history -n`: append only the lines of *path* (default $HISTFILE)
        not already read into this session."""
        target = path or self.state.history_file
        lines = self._read_file_lines(target)
        if lines is None:
            return False
        default = self._is_default_file(target)
        start = self._file_read_len if default else 0
        fresh = lines[start:]
        self.state.history.extend(fresh)
        # Read lines are NEVER pending (see read_history), and the in-memory
        # list still respects $HISTSIZE: bash trims after `-n` too.
        self._trim_to_max()
        if default:
            self._file_read_len = len(lines)
        return True

    def delete_entry(self, first: int, last: int) -> None:
        """`history -d`: delete the entries at 1-based positions [first, last].

        Callers validate the range. Deleted entries leave the pending set with
        them, so a deleted command is never written to the file afterwards.

        The READ cursor is deliberately NOT shifted. The two quantities are
        different: pending is a view of MEMORY, so a memory deletion prunes it;
        ``_file_read_len`` is a position in the FILE, and deleting from memory
        does not un-read a file line. Shifting
        it made `history -d` followed by `history -n` re-read lines that were
        already consumed, duplicating them in the list (MEDIUM-7 leg A). bash
        5.2.26 leaves its file counter untouched across `-d` for a single
        offset, a range, and a delete at the cursor alike."""
        lo, hi = first - 1, last  # 0-based half-open slice
        del self.state.history[lo:hi]
        self._prune_pending()

    def _read_file_lines(self, path: str) -> Optional[List[str]]:
        """Non-empty, newline-stripped lines of *path*; None on OSError."""
        try:
            with open(path, 'r', encoding='utf-8',
                      errors='surrogateescape') as f:
                return [ln.rstrip('\n') for ln in f if ln.strip()]
        except OSError:
            return None
