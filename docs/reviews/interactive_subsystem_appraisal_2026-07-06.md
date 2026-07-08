# Interactive Subsystem Appraisal — 2026-07-06

## Scope

This is a fresh appraisal of the interactive shell subsystem, graded for:

- correctness, especially terminal ownership and job-control behavior;
- textbook-quality line editing, history, prompt, and completion design;
- architectural elegance and maintainability;
- efficiency and Unicode correctness; and
- test quality and production readiness.

The review covered:

- `psh/interactive/`;
- the REPL and interactive orchestration paths;
- signal handling and terminal process-group integration;
- line editing, rendering, key decoding, and layout;
- command accumulation and multiline input;
- history storage, expansion, persistence, and builtins;
- prompt and terminal-title expansion;
- tab completion;
- interactive PTY, job-control, conformance, and unit tests; and
- representative behavioral probes and complexity checks.

## Executive Judgment

The subsystem has a sound high-level decomposition and an unusually substantial
interactive test suite for a custom shell. Its separation of key decoding,
editing, rendering, layout, history navigation, command accumulation, and job
management provides a credible base for further work.

It is not yet at a production or textbook-quality bar.

Two defects are production-critical:

1. a shell started in the background can seize the controlling terminal instead
   of stopping until its process group is foregrounded; and
2. prompts and line-editor control sequences are written to standard output,
   corrupting redirected command output.

Several other issues are architectural rather than cosmetic. Immediate job
notifications are not integrated into the input event loop, undo history leaks
across commands and has quadratic storage cost, history expansion is based on
backward textual heuristics rather than shell lexical state, history event
numbers are not stable, prompt expansion changes `$?`, UTF-8 and terminal-cell
width are handled incorrectly, and completion remains path-only.

Overall grade: **C+**.

## Grades

| Dimension | Grade | Assessment |
| --- | --- | --- |
| Typical foreground-session correctness | B | Ordinary foreground editing and command execution are generally reliable. |
| Full terminal/job-control correctness | C | The background-start terminal acquisition defect is a release blocker. |
| Line-editor design | B- | Good decomposition, but state lifetime, Unicode, paste handling, and undo cost need redesign. |
| History correctness | C | Useful feature breadth, but lexical interpretation and event numbering diverge materially from Bash. |
| Prompt handling | B- | Broad expansion support, but output routing, status preservation, and edge cases are incorrect. |
| Completion | D+ | Path completion works, but shell-aware completion architecture and contexts are largely absent. |
| Architecture | B- | Boundaries are visible, though event handling and terminal ownership are still fragmented. |
| Efficiency | C | Common inputs are acceptable; undo snapshots and repeated multiline parsing have quadratic behavior. |
| Testing | B+ | Strong PTY and focused coverage, weakened by legacy tests that encode incompatible assumptions. |
| Textbook quality | C+ | A credible foundation with several violations of standard terminal and shell algorithms. |

## Validation

### Focused interactive validation

The focused interactive, multiline, prompt, and history selection passed:

```text
python -m pytest \
  tests/unit/interactive \
  tests/unit/multiline \
  tests/unit/test_line_editor_multiline.py \
  tests/unit/test_tab_completion_tilde.py \
  tests/integration/interactive \
  tests/integration/multiline \
  tests/integration/test_multiline_history.py \
  tests/conformance/bash/test_history_expansion_conformance.py \
  tests/conformance/bash/test_prompt_expansion_conformance.py \
  tests/conformance/bash/test_set_o_history_conformance.py -q

480 passed, 47 skipped
```

### Opt-in PTY validation

The canonical system PTY tier passed all 96 tests.

Running both the system tier and the older integration selection together gave:

```text
python -m pytest \
  tests/integration/interactive \
  tests/system/interactive \
  --run-interactive -q

115 passed, 16 failed, 12 xfailed
```

The 47 integration cases account for the remaining 19 passes, 16 failures, and
12 expected failures. The failures are dominated by command-completion gaps and
older pipe-based helpers that treat a shell as interactive without providing a
controlling PTY. Some of those helpers also report the status of the final
failed command as though it were a harness failure.

These tests should be repaired or retired. A terminal shell cannot be validated
faithfully through ordinary pipes alone.

### Job-control and terminal validation

```text
python -m pytest \
  tests/unit/builtins/test_job_control_builtins.py \
  tests/integration/job_control \
  tests/integration/subshells/test_subshell_terminal_control.py -q

273 passed in 86.39s
```

This is strong coverage of established execution paths. It does not exercise
the critical case where PSH itself is launched as a background process group
under another interactive shell.

### Static analysis

```text
ruff check psh/interactive
```

was clean. The repository's normal mypy configuration was also clean.

A strict `--disallow-untyped-defs` run found 99 missing annotations in the
interactive surface and related integration code.

Optional complexity analysis found eight significant `C901` hotspots:

| Function | Complexity |
| --- | ---: |
| `HistoryExpander.expand_history` | 31 |
| `HistoryExpander._apply_word_designator` | 21 |
| `HistoryExpander._resolve_event` | 20 |
| REPL `run` path | 15 |
| `LineEditor.read_line` | 14 |
| history `_separator` handling | 13 |
| path completion | 12 |
| completion word-start detection | 11 |

The main history expansion routine also has approximately 35 branches and 106
statements. That complexity is evidence that the representation and parsing
model need improvement, not merely that the function should be split.

### Edit-buffer scaling

The undo implementation stores a complete buffer snapshot for each character
edit. A representative insertion benchmark produced:

| Characters typed | Total characters retained in undo snapshots |
| ---: | ---: |
| 1,000 | 500,000 |
| 2,000 | 2,000,000 |
| 4,000 | 8,000,000 |
| 8,000 | 32,000,000 |

This is quadratic storage and copying behavior.

## What Is Already Strong

### Clear editor decomposition

The subsystem separates:

- byte/key decoding;
- editable buffer state;
- key bindings;
- screen rendering;
- terminal layout;
- history navigation; and
- command completion state.

That is substantially better than a monolithic `read_line` loop. In
particular, central escape-sequence decoding and table-driven key dispatch make
the editor understandable and testable.

### Shared command accumulation

Interactive and multiline paths use the parser-backed
`CommandAccumulator`. This is the right direction: completeness should be
derived from shell grammar, not from counting quotes and braces independently
inside the editor.

### Coherent history ownership

The subsystem has a single history writer and deliberately preserves shared
list identity between consumers. That avoids a common class of stale-reference
bugs.

### Deliberate signal lifecycle

Signal self-pipes are created lazily and handler installation is paired with
restoration. The code demonstrates awareness that Python signal handlers,
blocking input, and terminal process groups require explicit lifecycle
management.

### Centralized foreground transfers

Terminal process-group transfers are concentrated in `JobManager`, rather than
being scattered throughout individual builtins and execution paths. This is a
good ownership boundary even though initial foreground acquisition currently
uses it incorrectly.

### Substantial PTY coverage

The project already tests EOF handling, stopped jobs, terminal control,
multiline interaction, prompt behavior, and a range of Bash-compatible history
features through real PTYs. This test foundation should make the required
redesign safer.

## Findings

### 1. P0: A background shell can steal the controlling terminal

Relevant flow:

- `InteractiveManager.run_interactive_loop` installs interactive signal policy
  and then calls foreground acquisition;
- `SignalManager._setup_interactive_mode_handlers` ignores `SIGTTIN`,
  `SIGTTOU`, and `SIGTSTP`; and
- `SignalManager.ensure_foreground` creates or joins the shell process group
  and unconditionally transfers the terminal to it.

This reverses the standard interactive-shell startup algorithm. A shell that
starts in a background process group must stop itself with `SIGTTIN` until its
parent places it in the foreground. Ignoring `SIGTTIN` before checking terminal
ownership disables precisely that protection.

A direct PTY probe under Bash reproduced the defect:

```sh
python -m psh --norc &
echo WHO=$0
```

The `echo` input was consumed by PSH and printed:

```text
WHO=psh
```

PSH had seized the parent's terminal.

#### Required correction

Use the standard sequence:

1. determine the shell's process group;
2. while `tcgetpgrp(tty_fd) != getpgrp()`, send `SIGTTIN` to the shell process
   group;
3. place the shell in its own process group if necessary;
4. transfer the terminal to that process group;
5. save the shell's terminal modes; and only then
6. install the interactive policy that ignores job-control stop signals in the
   shell itself.

Add a PTY regression in which Bash remains the parent interactive shell,
launches PSH with `&`, verifies that PSH is stopped, foregrounds it with `fg`,
and only then expects PSH to read terminal input.

### 2. P0: Prompts and editor display corrupt redirected standard output

`LineRenderer._out` defaults to `sys.stdout`. Prompt text, ANSI cursor movement,
and editor echo therefore share the command-output stream.

The behavior is directly observable:

```sh
python -m psh --norc > output-file
```

The terminal showed no prompt. The redirected file contained a colored PS1,
cursor-control bytes, the typed `exit`, and a newline, equivalent to:

```python
'\x1b[32m...$ \n\x1b[39Cexit\n'
```

Bash sends interactive prompts and editing display to the terminal-facing
diagnostic stream, conventionally standard error, so redirecting standard
output does not capture them.

#### Required correction

Introduce an injected terminal-session abstraction with distinct:

- input file descriptor;
- display stream or display file descriptor;
- saved terminal modes;
- raw-mode lifecycle; and
- terminal-size access.

Route PS1, PS2, completion listings, editor redraws, interactive history
expansion echo, Ctrl-C/EOF feedback, and terminal-control sequences through the
display channel. Command output must remain on standard output.

Audit title updates separately because they are terminal control rather than
diagnostics.

### 3. P1: Immediate job notification (`set -b`) is ineffective while idle

The key reader waits on standard input and the `SIGWINCH` self-pipe only. It does
not wait on a `SIGCHLD` event source. Meanwhile, the REPL suppresses normal
between-command notification when the `notify` option is enabled, on the
assumption that notification happened immediately.

The result is a gap: neither layer prints the completion.

The following remained silent both while idle and after the next command:

```sh
set -b
sleep .2 &
```

#### Required correction

Create a unified input event loop that waits on:

- terminal input;
- `SIGWINCH`;
- `SIGCHLD`; and
- any explicit wakeup source used for shutdown or traps.

On `SIGCHLD`, reap children, update job state, print pending notifications to
the display stream, and repaint the current prompt and buffer without losing
the cursor position. Keep signal handlers minimal; complex state transitions
and I/O belong in ordinary event-loop code.

### 4. P1: Undo state crosses command boundaries and scales quadratically

`EditBuffer.reset` clears the current text and cursor but intentionally
preserves undo state. A direct buffer test demonstrated:

1. enter `echo one`;
2. reset for the next command;
3. invoke undo;
4. observe `echo on` from the previous command.

That is the wrong state lifetime. Undo and redo belong to one editing session.
The kill ring may reasonably span sessions; undo history should not.

Each edit also saves the complete buffer string. Per-character insertion
therefore performs quadratic copying and retains quadratic data.

#### Required correction

- Clear undo and redo stacks at the beginning of each `read_line` session.
- Keep only intentionally cross-session state, such as the kill ring, outside
  that reset.
- Represent edits as bounded deltas: insertion/deletion range, replaced text,
  and cursor state.
- Coalesce adjacent typing and adjacent deletion into logical undo groups.
- Enforce a configurable memory or operation bound.

### 5. P1: History expansion is not based on shell lexical state

The expander scans backward through raw text to infer whether `!` lies inside
constructs such as bracket expressions, `${...}`, or `$((...))`. This produces
false suppression.

For example, after adding `echo OLD` to history:

```sh
echo '[' !!
```

Bash expands `!!`; PSH leaves it unchanged. Equivalent discrepancies occur
after quoted text resembling `${` or `$((`.

Word designators have a related defect. The internal word splitter does not
honor shell escaping:

```sh
echo a\ b c
!!:1
```

Bash selects `a\ b`; PSH selects only `a\`.

These are not isolated missing cases. They follow from using textual heuristics
where the feature requires a lexical model.

#### Required correction

Implement history expansion as a one-pass scanner with explicit states for:

- unquoted text;
- single quotes;
- double quotes;
- escapes;
- command substitutions;
- parameter expansions;
- arithmetic contexts; and
- history event, word-designator, and modifier syntax.

Use typed results for parsed event selectors, word designators, and modifiers.
Use the same scanner for `contains_history_reference`; a separate regular
expression will inevitably disagree with the real expander.

For event word selection, either reuse the shell lexer with the required
history-specific preservation rules or build a small dedicated lexer whose
escaping and quoting behavior is tested differentially against Bash.

### 6. P1: History event numbers are list indexes, not stable event IDs

History is stored as `List[str]`. Absolute event lookup derives its number from
the current position in that list.

After trimming with `HISTSIZE=2`, Bash preserves monotonic event IDs. If three
entries have been accepted, their visible IDs remain 2 and 3: `!1` fails, `!2`
selects the second event, and `!3` selects the third. PSH renumbers retained
entries to 1 and 2, so the same expressions select the wrong events or fail at
the wrong number.

This also makes `history` output and the `\!` prompt escape incorrect after
trimming.

#### Required correction

Replace raw strings with a model such as:

```python
@dataclass(frozen=True)
class HistoryEntry:
    event_id: int
    text: str
    timestamp: float | None = None
```

Maintain a monotonic `next_event_id`. Trimming removes entries but never
renumbers survivors. Resolve absolute designators by event ID, relative
designators by position relative to the current event, and render `history` and
`\!` from the same model.

### 7. P1: Prompt expansion changes the shell's observable status

Prompt expansion invokes the general expansion machinery. A command
substitution inside PS1 can therefore overwrite `$?`.

The following probe differs from Bash:

```sh
PS1='$(false)P> '
echo STATUS=$?
```

Bash reports `STATUS=0` after successfully displaying the prompt. PSH reports
`STATUS=1`, leaking the status of `false` from prompt expansion into the next
command.

#### Required correction

Snapshot and restore all shell-observable status that prompt evaluation may
modify. At minimum this includes `$?`; audit `PIPESTATUS`, the last command
substitution status, and any other execution metadata exposed through
expansion.

Prompt expansion also needs:

- a `promptvars` option and the corresponding disabled behavior;
- correct home-directory boundary checks rather than plain
  `cwd.startswith(home)`;
- graceful handling when the current directory has been deleted; and
- cell-width-aware multiline prompt geometry.

### 8. P1: UTF-8 decoding and terminal-cell measurement are incorrect

`KeyDecoder._read_char` decodes each `os.read` result independently with
replacement enabled. If a multibyte UTF-8 character is split across reads, it
becomes multiple replacement-character events.

Layout and rendering use Python character counts as terminal columns. That is
wrong for:

- wide East Asian characters;
- emoji;
- combining marks;
- zero-width joiners; and
- many modern grapheme clusters.

For example, `界` and many emoji occupy two terminal cells despite a Python
length of one, while `e` followed by a combining acute accent has a Python
length of two but commonly occupies one cell.

#### Required correction

- Use an incremental UTF-8 decoder across reads.
- Treat editor movement and deletion in grapheme-cluster units.
- Measure display layout in terminal cells using a maintained `wcwidth`
  implementation.
- Cache or incrementally update width metadata for long buffers.
- Replace front-removal from lists with `collections.deque`; current `pop(0)`
  usage creates avoidable linear shifts.

### 9. P1: Completion is path-only and loses shell context

The current completer is primarily a filesystem path completer. It does not
provide a production shell's key completion sources:

- builtins;
- functions;
- aliases;
- executable commands from `PATH`;
- variables and special parameters;
- context after pipes, command separators, assignments, and redirections;
- quoting-aware insertion;
- configured completion behavior; or
- cycling/menu semantics.

The word-start detector treats escaped spaces as separators. For example,
`cat foo\ ba` identifies the wrong completion prefix. User-directory
completion also expands `~pwilson` into a plain path fragment and loses the
tilde spelling.

#### Required correction

Define an explicit context model:

```python
@dataclass(frozen=True)
class CompletionContext:
    start: int
    prefix: str
    quote_mode: QuoteMode
    command_position: bool
    redirection_position: bool
    assignment_position: bool
```

Build providers for commands, variables, users, shell symbols, and paths.
Provider results should be semantic candidates; a separate quoting layer should
insert them safely into the current lexical context.

Use lexer/parser information where possible instead of reconstructing shell
syntax from whitespace.

### 10. P1: Bracketed paste is absent

Without bracketed-paste handling, pasted multiline text arrives as ordinary
keystrokes. Embedded newlines can execute commands incrementally instead of
allowing the user to inspect the complete pasted text.

#### Required correction

Enable terminal bracketed-paste mode while the editor is active, recognize the
start and end control sequences, collect pasted bytes without interpreting
bindings, and insert the paste as one edit transaction. Define and test the
policy for embedded newlines before enabling command execution.

Disable bracketed-paste mode during all exit and exceptional-restoration paths.

### 11. P2: Terminal-title updates allow control-sequence injection

The title path places current-directory or command text directly inside an OSC
sequence. Untrusted text containing BEL, ESC, or other C0 controls can terminate
or alter that sequence.

#### Required correction

Sanitize title content before encoding it. Remove or escape BEL, ESC, C0
controls, and terminal string terminators. Keep title rendering on the terminal
display channel rather than standard output.

### 12. P2: Terminal restoration can obscure the original exception

`TerminalManager.__exit__` may raise while restoring state. If the body is
already unwinding due to an error, a restoration failure can mask the original
cause.

#### Required correction

Attempt every restoration step independently, clear internal ownership state
in `finally`, and preserve the primary exception. Restoration errors should be
reported as secondary diagnostics unless no earlier exception exists.

### 13. P2: Multiline input is reparsed and its completed parse is discarded

The multiline handler uses parser-backed completeness, but after obtaining a
complete result it returns text and the command path accumulates and parses the
same input again. Each additional physical line can also cause the entire
growing buffer to be reparsed.

This loses a useful architectural benefit and gives long multiline constructs
quadratic parsing behavior.

#### Required correction

Return a typed result containing both source text and the completed parse:

```python
@dataclass(frozen=True)
class AcceptedInput:
    source: str
    ast: Program
```

Execute that AST directly. If the parser supports resumable state, preserve it
between continuation lines; otherwise document the reparse cost and impose
reasonable interactive input limits.

### 14. P2: Error boundaries are too broad

The REPL catches broad `Exception` categories around substantial orchestration
blocks. This can turn programming defects into user-facing command errors and
leave partially updated terminal, history, or job state.

#### Required correction

Catch only expected shell-domain failures at the layer that can recover from
them. Put terminal restoration and essential process cleanup in narrow
`finally` blocks. Let unexpected exceptions retain tracebacks in development
and test configurations.

### 15. P2: Interactive dependencies are mutated after construction

Some public components receive dependencies through post-construction
assignment. This permits temporarily invalid objects and makes lifecycle
requirements harder to reason about.

#### Required correction

Use constructor injection for terminal session, renderer, signal source,
history service, completion service, and execution callback. Where cycles
exist, replace them with small protocols or callbacks rather than mutable
backreferences.

### 16. P2: RC-file safety and history persistence need stronger protocols

RC-file validation and opening are separate operations, leaving a time-of-check
to time-of-use window. The policy also permits group-writable startup files.

History append and rewrite operations do not consistently use one locking and
atomic-replacement protocol, so concurrent interactive shells can lose updates.

#### Required correction

- Open startup files first with appropriate no-follow semantics where
  available, then validate the opened descriptor with `fstat`.
- Define and document whether group-writable files are trusted; a production
  default should be conservative.
- Use one history persistence service for append, merge, lock, rewrite, and
  atomic replace.
- Add concurrent-shell tests for `history -a`, `history -w`, truncation, and
  shutdown.

### 17. P2: Several Bash interaction details are incomplete

Additional gaps include:

- ambiguous job-prefix matching and missing `%?substring` job specifications;
- unsupported `history -p`;
- no `fc` builtin;
- contextual continuation prompts that intentionally replace, rather than
  expand, PS2;
- absent `promptvars` option;
- codepoint-based alignment in completion listings; and
- setup paths that can allocate interactive signal resources before a
  pipe-driven invocation has conclusively been classified as noninteractive.

Not all of these must be implemented for a deliberately smaller shell, but each
supported surface should be explicit. Unsupported syntax should fail clearly
rather than partially resemble Bash.

## Architectural Direction

The central improvement is to make terminal interaction one coherent service
rather than a set of cooperating loops with separate wakeup and output rules.

A suitable shape is:

```text
InteractiveSession
├── TerminalSession
│   ├── input_fd
│   ├── display_fd
│   ├── foreground ownership
│   ├── saved modes
│   └── raw/bracketed-paste lifecycle
├── EventLoop
│   ├── input readiness
│   ├── SIGCHLD readiness
│   ├── SIGWINCH readiness
│   └── shutdown/trap wakeups
├── LineEditor
│   ├── grapheme-aware EditBuffer
│   ├── bounded delta undo
│   ├── renderer
│   └── completion service
├── InputCompiler
│   ├── command accumulation
│   └── one completed parse
└── HistoryService
    ├── stable event IDs
    ├── lexical expansion
    └── locked persistence
```

This gives terminal ownership, display routing, asynchronous notifications, and
restoration one lifecycle. It also keeps parsing and execution out of signal
handlers and editor internals.

## Prioritized Remediation Plan

### Phase 0: Correct terminal safety

1. Implement standard foreground acquisition before ignoring job-control
   signals.
2. Introduce an injected terminal display channel and route editor output to
   standard error or the controlling terminal.
3. Preserve shell status around prompt expansion.
4. reset undo and redo for every accepted or abandoned input line;
5. add PTY regressions for all four behaviors.

No interactive release should be considered production-safe before this phase
is complete.

### Phase 1: Unify the interactive event loop

1. Poll terminal input, `SIGWINCH`, and `SIGCHLD` together.
2. Reap and notify from normal code, then repaint the current edit state.
3. Queue trap and shutdown work rather than performing it in handlers.
4. Give one terminal-session object ownership of raw mode and restoration.
5. Test idle notification, resize during editing, stopped jobs, disconnect, and
   exceptions.

### Phase 2: Correct the text model

1. Add incremental UTF-8 decoding.
2. Store and edit grapheme clusters.
3. measure every prompt and buffer segment in terminal cells;
4. replace snapshots with bounded, coalesced edit deltas;
5. replace front-shift lists with deques; and
6. implement bracketed paste and explicit escape-sequence timeouts.

### Phase 3: Rebuild history around explicit semantics

1. Add stable event IDs and a monotonic counter.
2. Replace backward heuristics with a one-pass lexical scanner.
3. Implement shell-aware word designators.
4. Return typed event/designator/modifier results.
5. centralize locked, atomic persistence; and
6. derive listing and prompt numbering from the same history model.

### Phase 4: Raise completion and prompt quality

1. Define `CompletionContext`.
2. Add command, variable, function, alias, user, and path providers.
3. Make insertion quoting-aware.
4. Add and honor `promptvars`.
5. Correct home and deleted-directory handling.
6. Sanitize terminal-title content.

### Phase 5: Simplify orchestration

1. Make the line editor the single interactive input source.
2. Preserve and execute the completed parse instead of parsing twice.
3. Narrow exception boundaries.
4. Centralize shutdown, terminal restoration, trap dispatch, and history save.
5. Complete strict typing across the interactive surface.

## Production Acceptance Gates

The subsystem should not be called production-ready until automated tests
demonstrate all of the following:

- a background-started PSH stops and waits to be foregrounded;
- redirecting standard output captures no prompt, typed input, or ANSI editor
  control sequences;
- `set -b` reports completed jobs while idle and preserves the current buffer
  and cursor;
- prompt evaluation does not alter `$?`;
- undo cannot restore text from a previous input line;
- long-line editing has linear or amortized-linear memory growth;
- split UTF-8 input and wide/combining characters edit and render correctly;
- history event IDs survive trimming and file operations;
- supported history expansion passes differential Bash cases involving quotes,
  escapes, parameters, arithmetic, and word designators;
- bracketed multiline paste cannot execute incrementally;
- completion distinguishes command, argument, assignment, quoting, and
  redirection contexts;
- EOF, terminal disconnect, exceptions, and suspension restore terminal state;
- all terminal semantics are tested under real PTYs; and
- the 47 legacy integration cases are repaired, reclassified, or removed so
  that the opt-in interactive suite has one trustworthy meaning.

## Final Assessment

The interactive subsystem is neither a toy nor a production-quality terminal
shell. Its decomposition and test investment put it in a good position, but the
remaining defects sit in foundational contracts: who owns the terminal, where
interactive display is written, how asynchronous events reach the editor, what
constitutes one editing session, and how shell text is lexed.

The correct next step is not to add more isolated key bindings or completion
special cases. First repair foreground acquisition and output routing, then
unify event handling and establish a correct Unicode/text model. Once those
contracts are sound, history, prompt, and completion features can be improved
without compounding the current complexity.
