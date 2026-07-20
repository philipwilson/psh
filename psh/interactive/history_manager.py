"""Command history management."""
import fcntl
import os
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
    ``_file_synced_len`` tracks how many of ``state.history``'s entries are
    already on disk.

    Every file path (load/save/-w/-a/-r/-n) opens with
    ``encoding='utf-8', errors='surrogateescape'`` (campaign I4; I1 byte
    doctrine) so arbitrary bytes round-trip: a malformed byte loads as a lone
    surrogate and re-encodes to the same byte on write, never raising
    ``UnicodeDecodeError``.
    """

    def __init__(self, shell: 'Shell') -> None:
        super().__init__(shell)
        # Count of state.history entries already persisted to the file
        # (entries loaded from it at startup, plus whatever we've since saved).
        self._file_synced_len = 0
        # Count of the default history file's lines already consumed into the
        # in-memory list (startup load + `history -r`/`-n` of the default
        # file). `history -n` uses this to append only lines it hasn't read yet.
        self._file_read_len = 0

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

        Adjusts the persisted-length marker by however many removed entries
        were before it, so save_to_file's ``history[_file_synced_len:]`` slice
        still starts at a genuinely-new entry (the file is append-only, so the
        on-disk copies of erased dups remain — erasedups is in-session here)."""
        hist = self.state.history
        removed_before_sync = sum(
            1 for i, h in enumerate(hist) if h == command and i < self._file_synced_len)
        hist[:] = [h for h in hist if h != command]
        self._file_synced_len = max(0, self._file_synced_len - removed_before_sync)

    def add_to_history(self, command: str) -> None:
        """Add a command to history.

        A multi-line command becomes ONE entry, joined into its
        single-line ``; `` form like bash's cmdhist option (the joiner
        itself preserves newlines inside quoted strings, heredocs and
        command substitutions verbatim, also matching bash).

        HISTCONTROL / HISTIGNORE filtering matches bash: by default EVERY line
        is recorded (no dedup); ``ignorespace`` drops a line beginning with a
        space, ``ignoredups`` drops a line equal to the previous entry,
        ``erasedups`` removes all prior copies first, and HISTIGNORE drops lines
        matching its glob patterns.
        """
        histcontrol = self._histcontrol_options()
        # ignorespace: a line beginning with a space is not recorded (checked on
        # the raw line, before the multi-line join).
        if 'ignorespace' in histcontrol and command[:1] == ' ':
            return
        if '\n' in command:
            command = convert_multiline_to_single(command)
        # HISTIGNORE: drop lines matching any colon-separated glob pattern.
        if self._histignore_matches(command):
            return
        if 'erasedups' in histcontrol:
            self._erase_duplicates(command)
        elif 'ignoredups' in histcontrol:
            # Drop a line identical to the immediately previous entry.
            if self.state.history and self.state.history[-1] == command:
                return
        self.state.history.append(command)
        # Trim history if it exceeds max size. The trim drops entries from
        # the FRONT, so the persisted-length marker (an index into the list)
        # must shift by the same amount — otherwise save_to_file's
        # history[_file_synced_len:] slice would skip genuinely-new entries
        # (the v0.447 regression: a session exceeding max_history_size before
        # saving silently lost the commands between the stale index and the
        # tail).
        if len(self.state.history) > self.state.max_history_size:
            dropped = len(self.state.history) - self.state.max_history_size
            del self.state.history[:dropped]
            self._file_synced_len = max(0, self._file_synced_len - dropped)

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
        # Everything loaded is already on disk; only entries added after this
        # point are new and need appending on save.
        self._file_synced_len = len(self.state.history)
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
        new_entries = self.state.history[self._file_synced_len:]
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
            self._file_synced_len = len(self.state.history)
        except OSError:
            # Silently ignore history file errors
            pass

    def clear_history(self) -> None:
        """Clear command history (in-memory)."""
        self.state.history.clear()
        # The list is now empty; nothing is "already on disk" relative to it,
        # so subsequent commands append from the start.
        self._file_synced_len = 0
        self._file_read_len = 0

    # -- `history` file-sync operations -------------------------------------
    # These back the `history -w/-r/-a/-n` builtin flags. The two markers above
    # track our position relative to the DEFAULT history file ($HISTFILE):
    # `_file_synced_len` = in-memory entries already written to it,
    # `_file_read_len`   = its lines already read into memory. An operation on
    # an explicitly-named other file leaves both markers alone (that file is
    # unrelated to $HISTFILE's sync state).

    def _is_default_file(self, path: str) -> bool:
        try:
            return os.path.abspath(path) == os.path.abspath(self.state.history_file)
        except OSError:
            return False

    def store_entry(self, command: str) -> None:
        """`history -s`: add *command* as one entry without executing it.

        Stored verbatim (no HISTCONTROL/HISTIGNORE filtering — bash keeps an
        explicit `-s` entry) via in-place mutation to preserve the list-alias
        contract."""
        self.state.history.append(command)

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
        # The whole list is now flushed to a file, so the exit-time save and a
        # subsequent `-a` won't re-emit it (bash marks it written regardless of
        # which file). Only reads of the DEFAULT file move the read cursor.
        self._file_synced_len = len(self.state.history)
        if self._is_default_file(target):
            self._file_read_len = len(self.state.history)
        return True

    def append_history(self, path: Optional[str] = None) -> bool:
        """`history -a`: append entries added since the last write/append to
        *path* (default $HISTFILE)."""
        target = path or self.state.history_file
        new_entries = self.state.history[self._file_synced_len:]
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8',
                           errors='surrogateescape') as f:
                if new_entries:
                    f.write('\n'.join(new_entries) + '\n')
        except OSError:
            return False
        # Advance the written cursor for ANY target (bash's `-a` marker is
        # session-global), so the next `-a`/exit-save won't duplicate them.
        self._file_synced_len = len(self.state.history)
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
        if self._is_default_file(target):
            # These lines already live in the default file; don't re-append
            # them on save, and advance the read cursor past them.
            self._file_synced_len = len(self.state.history)
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
        if default:
            self._file_synced_len = len(self.state.history)
            self._file_read_len = len(lines)
        return True

    def delete_entry(self, first: int, last: int) -> None:
        """`history -d`: delete the entries at 1-based positions [first, last].

        Callers validate the range. Deletions before the sync/read cursors
        shift them so the append/read slices still start at the right place."""
        lo, hi = first - 1, last  # 0-based half-open slice
        del self.state.history[lo:hi]
        before_sync = max(0, min(hi, self._file_synced_len) - lo)
        before_read = max(0, min(hi, self._file_read_len) - lo)
        self._file_synced_len = max(0, self._file_synced_len - before_sync)
        self._file_read_len = max(0, self._file_read_len - before_read)

    def _read_file_lines(self, path: str) -> Optional[List[str]]:
        """Non-empty, newline-stripped lines of *path*; None on OSError."""
        try:
            with open(path, 'r', encoding='utf-8',
                      errors='surrogateescape') as f:
                return [ln.rstrip('\n') for ln in f if ln.strip()]
        except OSError:
            return None
