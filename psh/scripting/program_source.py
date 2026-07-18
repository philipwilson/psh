"""The one sourced-program service: typed program-text normalization (F3).

``ProgramSource`` is the single normalization boundary through which every
piece of PROGRAM TEXT enters parsing: script-file arguments, scripts on
stdin, ``-c`` command strings, in-process command text (``run_command`` /
``eval`` / trap actions), ``source``/``.`` targets, and rc files.  It carries
the source kind and diagnostic name, the byte/NUL policy, the line origin,
and — for the descriptor-backed kinds — which descriptor is read.  The
per-channel parse policies that used to be ad-hoc attribute pokes at call
sites (``history_expansion_eligible``, ``eof_drops_dangling_continuation``,
``posix_syntax_exit``) are decided HERE, from one channel table.

``execute_sourced_file(shell, SourceRequest)`` is the one sourced-file
executor: ``SourceBuiltin`` (``source``/``.``) and rc loading
(``psh/interactive/rc_loader.py``) both call it — rc is NOT a second source
dialect (reappraisal-20-continuation medium 2).  It owns source depth,
optional positionals (with bash's ``set``-persistence rule), ``FunctionReturn``
handling, RETURN-trap firing, and restoration on both normal and exception
exits.

NUL and invalid-byte policy is decided ONCE, in this module (continuation
medium 5).  Ground truth is the LIVE bash 5.2.26 oracle (probe battery
``tmp/boundary-ledgers/F3-probes/``); the bash C sources
(``builtins/evalfile.c`` / ``general.c`` / ``shell.c``) served as
commentary for the mechanisms and are NOT authoritative — the unpatched
5.2 tarball's shebang sniff differs from the patched 5.2.26 the oracle
ladder resolves (see ``looks_binary_sample``), so every rule below is
pinned by behavioral probes against the resolved oracle:

* Invalid UTF-8 bytes are never a policy question: every channel decodes
  with ``errors='surrogateescape'`` so raw bytes round-trip (bash reads
  bytes; a stray byte just becomes part of a word).
* STREAM channels (a script-file argument, a script on stdin) DELETE every
  NUL byte: bash's ``shell_getc`` layer discards them one at a time, so
  ``e\\0cho hi`` runs ``echo hi`` and ``magic\\0\\0\\0tail`` becomes
  ``magictail``.
* STRING-READ channels (``source``/``.`` and the rc file — bash reads the
  whole file via ``_evalfile``) run bash's exact NUL-strip loop: each NUL is
  deleted and the byte that shifts into its place is SKIPPED unexamined, so
  an isolated NUL vanishes while the second NUL of an adjacent pair
  survives; ``parse_and_execute`` then treats the result as a C string, so a
  surviving NUL truncates the program there (``echo A\\0B`` prints ``AB``;
  ``echo A\\0\\0B`` runs only ``echo A`` and drops the rest of the FILE).
  For the ``source`` builtin only (``FEVAL_BUILTIN``), more than 256 deleted
  NULs refuses the file: ``cannot execute binary file``, status 126 — the
  rc path (bash ``maybe_execute_file``) has NO such limit.
* The content SNIFF (``check_binary_file``: ELF magic; otherwise a NUL
  before the first newline — or before the SECOND newline when the first
  line is ``#!``; sample = first 80 bytes) applies ONLY to the script-file
  INVOCATION channel (and its analysis twin ``--validate`` etc., which must
  agree with ``bash -n``).  ``source`` never content-sniffs (bash 5.2 sets
  ``FEVAL_CHECKBINARY`` nowhere), and neither do stdin or rc.
* ``-c`` operands cannot contain NUL at all (execve forbids NUL in argv),
  and in-process command text comes from shell values, which are already
  NUL-free — both are VERBATIM channels (N/A rows in the matrix).
"""
import sys
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple

from ..core import FunctionReturn
from .input_sources import FileInput, InputSource, StdinInput, StringInput

if TYPE_CHECKING:
    from ..shell import Shell


class SourceChannel(Enum):
    """The channels program text can arrive through (one policy row each)."""
    SCRIPT_FILE = "script-file"     # psh FILE argument
    STDIN_SCRIPT = "stdin-script"   # script delivered on fd 0
    COMMAND_STRING = "-c"           # the -c operand
    COMMAND_TEXT = "command-text"   # run_command / eval / trap-action text
    SOURCED_FILE = "sourced-file"   # source/. target
    RC_FILE = "rc-file"             # interactive-startup rc file


class BinaryProgramText(Exception):
    """A string-read channel refused its file as binary (>256 deleted NULs).

    Raised only for the SOURCED_FILE channel (bash's ``FEVAL_BUILTIN``
    limit); the rc channel has no limit.  Resolved by
    :func:`execute_sourced_file` into bash's ``cannot execute binary file``
    diagnostic with status 126.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(path)


# Bash's _evalfile refuses a source'd file after this many DELETED NULs
# ("more than 256 null characters -- that probably indicates a binary
# file", builtins/evalfile.c).
_EVALFILE_NUL_LIMIT = 256

# Bash's binary sniff examines at most this many leading bytes
# (shell.c open_shell_script: char sample[80]).
BINARY_SNIFF_WINDOW = 80


def strip_nul_stream(text: str) -> str:
    """STREAM-channel NUL policy: delete every NUL (bash ``shell_getc``)."""
    return text.replace('\x00', '')


def evalfile_nul_filter(text: str, *, limited: bool = False,
                        path: str = "") -> str:
    """STRING-READ-channel NUL policy: bash 5.2's exact ``_evalfile`` loop.

    Each NUL is deleted and the character that shifts into its place is
    retained UNEXAMINED (bash's ``for`` loop advances past the ``memmove``),
    so an isolated NUL disappears while the second of an adjacent pair
    survives.  The parse then consumes the result as a C string, so a
    surviving NUL truncates the program there — reproduced by cutting at the
    first retained NUL.  With ``limited`` (the ``source`` builtin), more
    than 256 deleted NULs raises :class:`BinaryProgramText`.
    """
    if '\x00' not in text:
        return text
    out = []
    i = 0
    n = len(text)
    deleted = 0
    while i < n:
        ch = text[i]
        if ch == '\x00':
            deleted += 1
            if limited and deleted > _EVALFILE_NUL_LIMIT:
                raise BinaryProgramText(path)
            if i + 1 < n:
                out.append(text[i + 1])
            i += 2
        else:
            out.append(ch)
            i += 1
    filtered = ''.join(out)
    cut = filtered.find('\x00')
    return filtered if cut < 0 else filtered[:cut]


def looks_binary_sample(sample: bytes) -> bool:
    """The live oracle's ``check_binary_file`` on a leading sample.

    The caller passes at most :data:`BINARY_SNIFF_WINDOW` bytes.  Rules
    (probe-pinned against the RESOLVED bash oracle, 5.2.26): an ELF magic
    is binary; otherwise a NUL before the FIRST newline is binary — except
    that a ``#!`` first line extends the scan to the SECOND newline (the
    interpreter line is allowed, the first script line is still sniffed).
    A sample that runs out before the deciding newline is scanned to its
    end.  Applies ONLY to the script-file invocation channel and its
    analysis twin — never to source/rc/stdin.

    TRAP (bounce blocker 1): the unpatched bash-5.2 TARBALL memchrs the
    WHOLE sample for ``#!`` files; the patched 5.2.26 the oracle ladder
    resolves checks only before the second newline
    (``#!/bin/sh\\nx=1\\necho a\\0b`` RUNS).  Behavioral probes against the
    resolved oracle are the authority here — C-source citations are
    commentary, and can cite the wrong dialect.  Probes: F3-probes/
    bounce-base-shebang-5c997ac1.txt (sb1-sb7).
    """
    if len(sample) >= 4 and sample[:4] == b"\x7fELF":
        return True
    newline_budget = 2 if sample[:2] == b"#!" else 1
    for byte in sample:
        if byte == 0x0A:
            newline_budget -= 1
            if newline_budget == 0:
                return False
        elif byte == 0x00:
            return True
    return False


# Per-channel policy table: the SINGLE place the per-channel parse policies
# are decided.  Columns: content filter applied to file text (None = raw /
# handled elsewhere), history-expansion eligibility (F1: `-i script.sh`
# expands its own lines; -c strings, sourced files and rc files never
# expand — probes C1/C3), stream-vs-string dangling-backslash rule, and
# whether a FunctionReturn escaping the file's top level stops the file
# (the sourced-program channels; see InputSource.stops_on_function_return).
_STREAM = "stream"
_STRING_READ = "string-read"
_STRING_READ_LIMITED = "string-read-limited"
_VERBATIM = "verbatim"

_CHANNEL_POLICY = {
    #                       nul-policy             hist   eof_drops  stops_ret
    SourceChannel.SCRIPT_FILE:    (_STREAM,              True,  True,  False),
    # NOTE: the STDIN row's _STREAM nul-policy is APPLIED inside
    # StdinInput.read_line (per-record strip), not via a content_filter —
    # the lazy fd read has no whole-content seam. Editing this row alone
    # will NOT change stdin behavior; change StdinInput.read_line with it
    # (mirror comment there).
    SourceChannel.STDIN_SCRIPT:   (_STREAM,              True,  True,  False),
    SourceChannel.COMMAND_STRING: (_VERBATIM,            False, False, False),
    SourceChannel.COMMAND_TEXT:   (_VERBATIM,            True,  False, False),
    SourceChannel.SOURCED_FILE:   (_STRING_READ_LIMITED, False, False, True),
    SourceChannel.RC_FILE:        (_STRING_READ,         False, False, True),
}


@dataclass(frozen=True)
class ProgramSource:
    """One typed description of program text about to enter parsing.

    ``name`` is the diagnostic label (``-c``, the file path, ``<stdin>``,
    ``<command>``).  ``path``/``text``/``fd`` carry the actual origin —
    exactly one is meaningful per kind (files own their path and read it
    eagerly on open; the stdin kind owns fd 0 and reads it lazily, one line
    at a time).  Line origin is NOT carried here: nested command text
    anchored at an invoking line (eval, trap actions) threads ``base_line``
    through ``execute_from_source`` at execution time — the field joins
    this type when I2/I3 make it live.  Construct via the per-channel
    classmethods only.
    """
    kind: SourceChannel
    name: str
    path: Optional[str] = None
    text: Optional[str] = None
    fd: Optional[int] = None
    line_oriented: bool = True
    posix_syntax_exit: bool = True

    # -- constructors (one per channel) --------------------------------

    @classmethod
    def script_file(cls, path: str) -> 'ProgramSource':
        """A script-file argument (``psh FILE``) — bash stream input."""
        return cls(kind=SourceChannel.SCRIPT_FILE, name=path, path=path)

    @classmethod
    def stdin_script(cls, fd: int = 0, name: str = "<stdin>") -> 'ProgramSource':
        """A script delivered on fd 0 (``cmds | psh``, ``psh < file``)."""
        return cls(kind=SourceChannel.STDIN_SCRIPT, name=name, fd=fd)

    @classmethod
    def command_string(cls, command: str) -> 'ProgramSource':
        """The ``-c`` operand: line-oriented, never history-expanded."""
        return cls(kind=SourceChannel.COMMAND_STRING, name="-c", text=command)

    @classmethod
    def command_text(cls, text: str, name: str = "<command>",
                     line_oriented: bool = False,
                     posix_syntax_exit: bool = True) -> 'ProgramSource':
        """In-process command text (``run_command``/eval/trap actions)."""
        return cls(kind=SourceChannel.COMMAND_TEXT, name=name, text=text,
                   line_oriented=line_oriented,
                   posix_syntax_exit=posix_syntax_exit)

    @classmethod
    def sourced_file(cls, path: str) -> 'ProgramSource':
        """A ``source``/``.`` target — bash string-read input."""
        return cls(kind=SourceChannel.SOURCED_FILE, name=path, path=path)

    @classmethod
    def rc_file(cls, path: str) -> 'ProgramSource':
        """The startup rc file — string-read input, no NUL limit."""
        return cls(kind=SourceChannel.RC_FILE, name=path, path=path)

    # -- the normalization boundary ------------------------------------

    def _content_filter(self):
        """The NUL-policy content filter for this channel's file text."""
        policy = _CHANNEL_POLICY[self.kind][0]
        if policy == _STREAM:
            return strip_nul_stream
        if policy == _STRING_READ:
            return evalfile_nul_filter
        if policy == _STRING_READ_LIMITED:
            path = self.path or self.name
            return lambda text: evalfile_nul_filter(text, limited=True,
                                                    path=path)
        return None  # _VERBATIM

    def make_input_source(self) -> InputSource:
        """Build the InputSource for this program, policies applied.

        This is the ONLY place InputSource objects are constructed for
        program text (guarded by
        tests/unit/tooling/test_program_source_guard.py); the per-channel
        flags come from the one policy table above instead of ad-hoc
        attribute pokes at call sites.
        """
        _, hist, eof_drops, stops_ret = _CHANNEL_POLICY[self.kind]
        source: InputSource
        if self.kind is SourceChannel.STDIN_SCRIPT:
            assert self.fd is not None
            source = StdinInput(fd=self.fd, name=self.name)
        elif self.path is not None:
            source = FileInput(self.path,
                               eof_drops_dangling_continuation=eof_drops,
                               content_filter=self._content_filter())
        else:
            assert self.text is not None
            split = (True if self.kind is SourceChannel.COMMAND_STRING
                     else self.line_oriented)
            source = StringInput(self.text, self.name, split_lines=split)
        source.history_expansion_eligible = hist
        source.posix_syntax_exit = self.posix_syntax_exit
        source.stops_on_function_return = stops_ret
        return source

    def read_text(self) -> str:
        """The full normalized program text (for the analysis modes).

        Reads a file kind exactly as execution would — same decode, same
        CRLF handling, same NUL policy — so ``--validate`` and friends see
        the text execution would run.  Command kinds return their text
        verbatim.  (The stdin kind is lazily line-read at execution time;
        analysis of stdin reads the descriptor itself and applies
        :func:`strip_nul_stream` — see ``psh/__main__.py``.)
        """
        if self.path is not None:
            file_input = self.make_input_source()
            with file_input:
                return '\n'.join(file_input.lines)  # type: ignore[attr-defined]
        assert self.text is not None
        return self.text


@dataclass(frozen=True)
class SourceRequest:
    """One request to execute a sourced program in the current shell.

    ``args`` is None when no positionals were given (the file SHARES the
    caller's positionals — a ``set --`` inside persists); a tuple (possibly
    empty) temporarily replaces them, restored afterwards unless the file
    ran ``set`` (bash's ``pop_dollar_vars`` rule — probes D4-D5g).
    """
    path: str
    kind: SourceChannel = SourceChannel.SOURCED_FILE
    args: Optional[Tuple[str, ...]] = None


def execute_sourced_file(shell: 'Shell', request: SourceRequest) -> int:
    """THE sourced-file executor: ``source``/``.`` and rc loading (F3).

    Owns, for both channels:

    * **source depth** — ``state.source_depth`` is incremented for the
      file's extent, so ``return`` is legal inside (the rc previously
      bypassed this and diagnosed a top-level return, unlike bash —
      continuation medium 2).  Runaway ``source`` recursion surfaces as
      Python's RecursionError and is reported as a clean resource-limit
      diagnostic at the top level (bash 5.2 SEGFAULTS there — probe D10;
      deliberate divergence).
    * **positionals** — swapped for the extent when ``args`` were passed,
      restored on BOTH normal and exception exits UNLESS the file ran
      ``set`` AND the boundary sits OUTSIDE any shell function
      (``state.positionals_changed_by_set`` + empty ``function_stack`` —
      bash's ``maybe_pop_dollar_vars`` persists only at
      ``variable_context == 0``, so ``g(){ . ./s a b; }`` restores the
      function's positionals even after a ``set`` in ``s``; probes
      D5/D5c/D5d/D5g and fc1/fc2/fc3, bounce blocker 2; ``shift`` does
      not count — D5b).
    * **FunctionReturn** — ``return N`` stops the file.  For ``source`` the
      status becomes the builtin's status (probe D8); for the rc bash
      DISCARDS N — ``$?`` at the first prompt keeps the last pre-return
      command's status and no diagnostic is printed (probes B1/B12/B13).
    * **RETURN trap** — fires when a ``source`` completes (normal end or
      ``return``), with the sourced context still in place; a ``return`` in
      the action overrides the status (TrapManager.execute_return_trap).
      The rc never fires it (bash — probes B3/B6).
    * **binary refusal** — the ``source`` channel's >256-NUL rule renders
      bash's ``cannot execute binary file`` with status 126 (probe A13);
      the rc channel has no limit.

    OSError from opening/reading the file propagates to the caller (the
    source builtin and rc loader render their own diagnostics); restoration
    still runs via ``finally``.
    """
    state = shell.state
    if request.kind is SourceChannel.RC_FILE:
        program = ProgramSource.rc_file(request.path)
    else:
        program = ProgramSource.sourced_file(request.path)

    has_args = request.args is not None
    if has_args:
        old_positional = state.positional_params.copy()
        prev_changed = state.positionals_changed_by_set
        state.positionals_changed_by_set = False

    state.source_depth += 1
    try:
        if has_args:
            state.positional_params = list(request.args or ())
        try:
            with program.make_input_source() as input_source:
                exit_code = shell.script_manager.execute_from_source(
                    input_source, add_to_history=False)
        except BinaryProgramText:
            print(f"psh: {request.path}: cannot execute binary file",
                  file=sys.stderr)
            return 126
        except FunctionReturn as ret:
            if request.kind is SourceChannel.RC_FILE:
                # bash discards the rc's return status; $? keeps the last
                # pre-return command's status (probes B12/B13). The caller
                # ignores this value; last_exit_code is deliberately not
                # touched.
                exit_code = state.last_exit_code
            else:
                # `return N` inside the sourced file: stop executing the
                # file and make N the exit status of `source` itself (bash).
                exit_code = ret.exit_code
        if request.kind is not SourceChannel.RC_FILE:
            # The RETURN trap fires each time a sourced file finishes —
            # whether by end-of-file or an explicit `return` — with $? =
            # the last command's status from before the return (bash).
            # Unlike functions, `source` never hides the trap (it fires
            # without set -T). A `return` in the action overrides the
            # exit status (see TrapManager.execute_return_trap). The rc
            # file never fires it (bash: probes B3/B6).
            override = shell.trap_manager.execute_return_trap()
            if override is not None:
                exit_code = override
        return exit_code
    finally:
        state.source_depth -= 1
        if has_args:
            # Persist set-assigned positionals ONLY outside shell functions
            # (bash source.def maybe_pop_dollar_vars: variable_context == 0
            # AND ARGS_SETBLTIN). Inside a function, the caller's
            # positionals are restored even after a `set` in the sourced
            # file (probes fc1/fc2 — bounce blocker 2).
            persist = (state.positionals_changed_by_set
                       and not state.function_stack)
            if not persist:
                state.positional_params = old_positional
            state.positionals_changed_by_set = prev_changed
