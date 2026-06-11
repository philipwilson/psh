# PSH Interactive Subsystem: Programmer's Guide

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> references pre-relocation top-level paths (`psh/tab_completion.py`, `psh/prompt.py`, `psh/line_editor.py`, `psh/multiline_handler.py`, `psh/keybindings.py`, `psh/job_control.py`); these now live under `psh/interactive/` (job-control logic under `psh/executor/job_control.py`).
> See the subsystem CLAUDE.md files for current structure.

This guide covers the interactive subsystem in detail: its external API,
internal architecture, and the responsibilities of every source file.  It is
aimed at developers who need to modify the REPL loop, add new key bindings,
change signal handling, or understand how the shell's interactive mode works.

## 1. What the Interactive Subsystem Does

The interactive subsystem manages everything that happens when the user runs
`python -m psh` without a script argument.  It provides:

- A **read-eval-print loop** (REPL) with multi-line input support.
- **Command history** (in-memory and on-disk persistence).
- **Tab completion** via a custom readline integration.
- **Prompt expansion** (PS1/PS2 escape sequences like `\u`, `\h`, `\w`).
- **Signal handling** using the self-pipe pattern for async-signal-safe
  SIGCHLD and SIGWINCH processing.
- **Job control integration** (foreground/background process groups,
  terminal control transfer).
- **Line editing** with vi and emacs key bindings, undo/redo, kill ring, and
  incremental history search.
- **RC file loading** (`~/.pshrc`) at startup.

The interactive subsystem does **not** parse or execute commands.  The REPL
delegates parsing to the lexer/parser and execution to
`shell.run_command()`, which uses the unified input system.


## 2. External API

The public interface is defined in `psh/interactive/__init__.py`.  The
declared `__all__` contains two items: `InteractiveManager` and
`load_rc_file`.  See `docs/guides/interactive_public_api.md` for the full
API reference including tiers and import guidance.

### 2.1 `InteractiveManager`

```python
from psh.interactive import InteractiveManager

manager = InteractiveManager(shell)
manager.run_interactive_loop()
```

The central orchestrator.  Instantiates and wires together five components
(`HistoryManager`, `PromptManager`, `CompletionManager`, `SignalManager`,
`REPLLoop`), sets up signal handlers and foreground process-group ownership,
and exposes facade methods for the shell.

Key methods:

| Method | Description |
|--------|-------------|
| `run_interactive_loop()` | Start the REPL.  Does not return until the user exits (Ctrl-D or `exit`). |
| `setup_readline()` | Configure readline tab-completion bindings. |
| `load_history()` | Load history from disk. |
| `save_history()` | Save history to disk. |

### 2.2 `load_rc_file()`

```python
from psh.interactive import load_rc_file

load_rc_file(shell)
```

Loads `~/.pshrc` (or `shell.rcfile`) into the shell.  Checks file
permissions via `is_safe_rc_file()` before sourcing.  Called by
`Shell.__init__()` for interactive non-`--norc` sessions.

### 2.3 Convenience imports (not in `__all__`)

The following are importable from `psh.interactive` but are not part of the
declared public API.  They are internal implementation details kept as
convenience imports to avoid churn.  New code should prefer the canonical
submodule paths.

**Components** (from their respective submodules):
`InteractiveComponent`, `REPLLoop`, `SignalManager`, `HistoryManager`,
`CompletionManager`, `PromptManager`, `is_safe_rc_file`


## 3. Architecture

### 3.1 Component overview

```
Shell.__init__()
       |
       v
InteractiveManager
       |
       ├── HistoryManager     (history_manager.py)
       ├── PromptManager      (prompt_manager.py)
       ├── CompletionManager   (completion_manager.py)
       ├── SignalManager       (signal_manager.py)
       └── REPLLoop            (repl_loop.py)
               |
               ├── MultiLineInputHandler   (multiline_handler.py)
               └── LineEditor              (line_editor.py)
                       |
                       ├── CompletionEngine    (tab_completion.py)
                       ├── TerminalManager     (tab_completion.py)
                       └── KeyBindings         (keybindings.py)
```

All five interactive components inherit from `InteractiveComponent` (in
`base.py`), which provides `self.shell`, `self.state`, and
`self.job_manager`.  The `InteractiveManager` sets cross-component
references (e.g. `repl_loop.history_manager = self.history_manager`) during
construction.

### 3.2 Initialisation sequence

When `Shell.__init__()` creates `InteractiveManager(self)`:

1. Instantiate all five components.
2. Wire cross-component dependencies (`REPLLoop` receives references to the
   history, prompt, and completion managers).
3. Skip signal setup if running under pytest or in a forked child.
4. Otherwise:
   a. `signal_manager.setup_signal_handlers()` -- install handlers for
      SIGINT, SIGCHLD, SIGWINCH, SIGTSTP, etc.
   b. `signal_manager.ensure_foreground()` -- put the shell in its own
      process group and claim the foreground.

After `InteractiveManager` is constructed, `Shell.__init__()` also calls
`interactive_manager.load_history()` and (if not `--norc`)
`load_rc_file(shell)`.

### 3.3 REPL loop flow

`REPLLoop.run()` is the main loop.  Its structure:

```
run()
  |
  ├── setup()
  |     ├── completion_manager.setup_readline()
  |     ├── Create LineEditor (vi or emacs mode)
  |     └── Create MultiLineInputHandler
  |
  └── while True:
        |
        ├── Process pending SIGCHLD notifications
        |     └── shell.interactive_manager.signal_manager
        |           .process_sigchld_notifications()
        |
        ├── Notify completed/stopped jobs
        |     ├── job_manager.notify_completed_jobs()
        |     └── job_manager.notify_stopped_jobs()
        |
        ├── Read command (possibly multi-line)
        |     └── multi_line_handler.read_command()
        |           └── line_editor.read_line(prompt, sigwinch_fd, sigwinch_drain)
        |
        ├── Execute command
        |     └── shell.run_command(command)
        |
        └── Handle exceptions
              ├── KeyboardInterrupt → print ^C, reset, continue
              ├── EOFError → break (exit)
              └── OSError (EIO) → break (terminal disconnected)
```

On exit, `history_manager.save_to_file()` is called.

### 3.4 Multi-line input handling

`MultiLineInputHandler` (in `psh/multiline_handler.py`) handles
continuation across multiple lines.  For each line entered, it checks
whether the accumulated input is a syntactically complete command:

1. **Line continuation** -- trailing `\` means "read another line".
2. **Unclosed heredoc** -- `<<EOF` without a matching delimiter line.
3. **Trailing operators** -- `|`, `||`, `&&` at end of line.
4. **Parse test** -- tokenise and parse the accumulated buffer.  If the
   parser raises `ParseError` with messages like "Expected 'fi'" or
   "Expected 'done'", the command is incomplete.  The handler updates a
   context stack to generate context-aware continuation prompts (e.g.
   `for> `, `then> `).

The handler also passes SIGWINCH notification file descriptors to the line
editor so terminal resizes can trigger display redraws.

### 3.5 Signal handling

`SignalManager` uses the **self-pipe pattern** for async-signal-safe
notification:

```
Signal handler (async context)         Main loop (sync context)
─────────────────────────────          ──────────────────────────
_handle_sigchld(signum, frame)         process_sigchld_notifications()
  └── _sigchld_notifier.notify()         ├── drain pipe
        └── os.write(pipe_fd, ...)       └── waitpid() loop
                                               └── update job states

_handle_sigwinch(signum, frame)        line_editor.read_line()
  └── _sigwinch_notifier.notify()        ├── select([stdin_fd, sigwinch_fd])
        └── os.write(pipe_fd, ...)       └── if sigwinch_fd readable:
                                               sigwinch_drain()
                                               redraw_line()
```

Two `SignalNotifier` instances manage the self-pipe pairs:

| Notifier | Signal | Consumer |
|----------|--------|----------|
| `_sigchld_notifier` | SIGCHLD | `process_sigchld_notifications()` in the REPL loop |
| `_sigwinch_notifier` | SIGWINCH | `line_editor.read_line()` via `select()` |

Signal handlers only call `os.write()` (async-signal-safe).  All real work
(waitpid, job state updates, terminal redraws) happens in the main loop.

`SignalManager` also handles:

- **SIGINT** -- checks for user-defined traps, then either terminates
  (script mode) or prints a newline (interactive mode).
- **SIGTSTP, SIGTTOU, SIGTTIN** -- ignored in the interactive shell (the
  shell itself cannot be stopped).
- **SIGTERM, SIGHUP, SIGQUIT** -- check for traps, then default behaviour.
- **Child process reset** -- `reset_child_signals()` restores all signals
  to `SIG_DFL` in forked children.

### 3.6 Line editing

`LineEditor` (in `psh/line_editor.py`) provides a custom line editor with:

- **Vi and Emacs key bindings** -- switchable via `set -o vi` / `set -o emacs`.
- **History navigation** -- up/down arrows, `Ctrl-R` incremental search.
- **Kill ring** -- `Ctrl-K`, `Ctrl-W`, `Ctrl-Y` (emacs) or `dd`, `yy`, `p`
  (vi normal mode).
- **Undo/redo** -- state saved before each edit.
- **Tab completion** -- delegates to `CompletionEngine`.
- **SIGWINCH support** -- accepts `sigwinch_fd` and `sigwinch_drain` parameters
  for select-based terminal resize detection.

The editor uses raw terminal mode via `TerminalManager` and handles all
character input directly (no readline dependency for the editing loop
itself).

### 3.7 Tab completion

`CompletionManager` sets up readline's completer function and delegates to
`CompletionEngine` (in `psh/tab_completion.py`) for actual completion
logic.  `CompletionEngine` provides:

- **File/directory completion** -- path-aware, with proper escaping.
- **Command completion** -- builtins, functions, commands in `$PATH`.
- **Variable completion** -- `$VAR` names from shell state and environment.
- **Common prefix calculation** -- for multi-match display.

### 3.8 Prompt expansion

`PromptManager` delegates to `PromptExpander` (in `psh/prompt.py`) which
handles bash-compatible prompt escape sequences:

| Escape | Expansion |
|--------|-----------|
| `\u` | Username |
| `\h` | Hostname (short) |
| `\H` | Hostname (full) |
| `\w` | Working directory (with `~` substitution) |
| `\W` | Basename of working directory |
| `\$` | `#` for root, `$` otherwise |
| `\d` | Date in "Weekday Month Date" format |
| `\t` | Time in HH:MM:SS format |
| `\n` | Newline |
| `\[`, `\]` | Non-printing character delimiters |
| `\e` | ASCII escape (033) |
| `\a` | ASCII bell (07) |

### 3.9 History management

`HistoryManager` provides in-memory history with file-backed persistence:

- **`add_to_history(command)`** -- adds to the in-memory list and readline,
  skipping duplicates of the immediately previous command.  Trims to
  `max_history_size`.
- **`load_from_file()`** -- reads `~/.psh_history` line by line into memory
  and readline.
- **`save_to_file()`** -- writes the most recent `max_history_size` entries
  to `~/.psh_history`.

### 3.10 RC file loading

`rc_loader.py` provides two functions:

- **`load_rc_file(shell)`** -- the main entry point (see section 2.2).
- **`is_safe_rc_file(filepath)`** -- returns `False` if the file is
  world-writable (`mode & 0o002`) or not owned by the current user or root.


## 4. Source File Reference

### 4.1 Package (`psh/interactive/`)

#### `__init__.py` (~25 lines)

Package entry point.  Declares `__all__` (2 items), imports all component
classes as convenience imports, and imports `load_rc_file` and
`is_safe_rc_file` from `rc_loader`.

#### `base.py` (~75 lines)

Defines `InteractiveComponent` (ABC with `shell`, `state`, `job_manager`
attributes) and `InteractiveManager` (the orchestrator that creates and
wires all components).

#### `repl_loop.py` (~90 lines)

`REPLLoop` -- the main interactive loop.  `setup()` creates the
`LineEditor` and `MultiLineInputHandler`.  `run()` implements the
read-eval-print loop with SIGCHLD processing, job notification, and
exception handling.

#### `signal_manager.py` (~295 lines)

`SignalManager` -- signal handling with the self-pipe pattern.  Key methods:

| Method | Description |
|--------|-------------|
| `setup_signal_handlers()` | Install handlers for all relevant signals (mode-dependent). |
| `process_sigchld_notifications()` | Drain SIGCHLD pipe and reap children with `waitpid()`. |
| `get_sigwinch_fd()` | Return the SIGWINCH notification file descriptor. |
| `drain_sigwinch_notifications()` | Drain SIGWINCH pipe, return whether any were pending. |
| `ensure_foreground()` | Put the shell in its own process group and claim the terminal. |
| `restore_default_handlers()` | Restore original signal handlers and close pipes. |
| `reset_child_signals()` | Reset all signals to `SIG_DFL` in a forked child. |

#### `history_manager.py` (~55 lines)

`HistoryManager` -- command history with `add_to_history()`,
`load_from_file()`, `save_to_file()`, `get_history()`, `clear_history()`.

#### `completion_manager.py` (~140 lines)

`CompletionManager` -- readline integration.  `setup_readline()` registers
the completer function.  `get_completions()` delegates to
`CompletionEngine`.  Also provides `complete_command()`,
`complete_path()`, and `complete_variable()` methods.

#### `prompt_manager.py` (~30 lines)

`PromptManager` -- thin wrapper around `PromptExpander`.  Provides
`get_primary_prompt()` (PS1), `get_continuation_prompt()` (PS2),
`expand_prompt()`, and `set_prompt()`.

#### `rc_loader.py` (~55 lines)

`load_rc_file()` and `is_safe_rc_file()`.  See section 3.10.

### 4.2 Related modules (outside the package)

These modules live directly under `psh/` but are integral to interactive
operation.

#### `multiline_handler.py` (~630 lines)

`MultiLineInputHandler` -- multi-line command support.  Accumulates input
lines and checks completeness by tokenising and parsing.  Provides
context-aware continuation prompts.  Handles line continuation (`\`),
unclosed heredocs, trailing operators, and incomplete control structures.

#### `line_editor.py` (~1,095 lines)

`LineEditor` -- custom line editor with vi/emacs key bindings, history
search, tab completion, kill ring, undo/redo, and SIGWINCH-aware redraw.
Operates in raw terminal mode via `TerminalManager`.

Key method: `read_line(prompt, sigwinch_fd, sigwinch_drain)` -- reads a
single line with full editing support and terminal-resize handling.

#### `keybindings.py` (~210 lines)

`EditMode` enum and key binding implementations:

- `EmacsKeyBindings` -- standard Ctrl-A/E/K/W/Y, Meta-B/F/D bindings.
- `ViKeyBindings` -- insert-mode and normal-mode bindings.

#### `prompt.py` (~195 lines)

`PromptExpander` -- expands bash-compatible prompt escape sequences
(`\u`, `\h`, `\w`, `\$`, `\d`, `\t`, etc.).

#### `tab_completion.py` (~200 lines)

`CompletionEngine` -- file, command, and variable completion logic.
`TerminalManager` -- raw-mode terminal context manager.

#### `history_expansion.py` (~255 lines)

`HistoryExpander` -- bang-style history expansion (`!!`, `!n`, `!string`,
`!?string?`).  Called during command execution, not during line editing.

#### `job_control.py` (~415 lines)

`JobManager`, `Job`, `Process`, `JobState` -- job control infrastructure.
Not part of the interactive package but tightly integrated through
`InteractiveComponent.job_manager` and `SignalManager`.


## 5. Common Tasks

### 5.1 Adding a new key binding

1. Add the binding constant to `KeyBindings` in `keybindings.py`.
2. Add the mapping in the appropriate bindings dict (`EmacsKeyBindings.bindings`,
   `.meta_bindings`, or `ViKeyBindings.normal_bindings`).
3. Add an action handler in `LineEditor._execute_action()` in
   `line_editor.py`.
4. Add tests.

### 5.2 Adding a new prompt escape sequence

1. Add the escape character handling in `PromptExpander.expand_prompt()` in
   `prompt.py`:

   ```python
   elif char == 'x':
       result.append(self._get_my_value())
   ```

2. Add a `_get_my_value()` helper method if needed.
3. Add tests.

### 5.3 Adding a new completion source

1. Add a completion method in `CompletionEngine` in `tab_completion.py`:

   ```python
   def _complete_aliases(self, text, line, cursor_pos):
       # Return list of matching alias names
       ...
   ```

2. Wire it into `get_completions()` in the appropriate context.
3. Add tests.

### 5.4 Adding a new signal handler

1. Add the handler method in `SignalManager`:

   ```python
   def _handle_my_signal(self, signum, frame):
       # Async-signal-safe: use SignalNotifier.notify() only
       self._my_notifier.notify(signum)
   ```

2. Register it in `_setup_interactive_mode_handlers()`:

   ```python
   self._original_handlers[signal.MYSIG] = self._signal_registry.register(
       signal.MYSIG, self._handle_my_signal, "SignalManager:interactive"
   )
   ```

3. Add the signal to `reset_child_signals()`.
4. Process notifications in the main loop or an appropriate consumer.
5. Add tests.

### 5.5 Modifying the REPL loop

The REPL loop is in `REPLLoop.run()` in `repl_loop.py`.  The structure is
straightforward:

1. Signal processing and job notification happen **before** reading input.
2. `multi_line_handler.read_command()` blocks until a complete command is
   entered.
3. `shell.run_command()` executes the command.
4. Exceptions are caught per-iteration.

To add pre-command or post-command hooks, insert logic before or after the
`shell.run_command()` call.

### 5.6 Debugging interactive mode

```bash
# Debug process groups and signals
python -m psh --debug-exec

# Debug with AST display
python -m psh --debug-ast
```


## 6. Design Rationale

### Why a component-based architecture?

Each interactive concern (history, completion, signals, prompts) is
independent.  Putting them in separate classes makes testing
straightforward -- each component can be instantiated in isolation with a
mock shell.  `InteractiveManager` handles the wiring.

### Why the self-pipe pattern for signals?

Signal handlers run asynchronously and can interrupt any Python code.
Calling `waitpid()` or updating complex data structures inside a signal
handler causes race conditions.  The self-pipe pattern (write a byte to a
pipe in the handler, read it in the main loop) keeps signal handlers
async-signal-safe and moves all real work to a predictable execution
context.

### Why two self-pipes (SIGCHLD and SIGWINCH)?

SIGCHLD requires `waitpid()` and job-state updates in the REPL loop.
SIGWINCH requires a terminal redraw in the line editor's `select()` loop.
These are consumed in different places, so separate notification channels
avoid coupling.

### Why a custom line editor instead of readline?

Python's readline module has limited support for custom key bindings,
vi mode, and terminal resize handling.  The custom `LineEditor` provides
full vi/emacs key bindings, `select()`-based SIGWINCH integration, and
direct control over terminal I/O, while still using readline for history
and completion registration.

### Why is RC file loading outside InteractiveManager?

`load_rc_file()` is a stateless function that sources a file into the
shell.  It doesn't need access to interactive components and can be tested
independently.  Keeping it separate also allows `Shell.__init__()` to
control the exact timing of RC loading (after history is loaded but before
the REPL starts).

### Why skip signal setup under pytest?

Signal handlers installed during tests interfere with subprocess creation
and can cause test hangs.  The `pytest` detection guard and the
`PSH_TEST_SIGNALS` override provide a clean separation between test and
production signal handling.


## 7. File Dependency Graph

```
psh/interactive/
├── __init__.py
│   ├── base.py
│   │   └── InteractiveComponent (ABC)
│   │   └── InteractiveManager (orchestrator)
│   ├── repl_loop.py
│   │   ├── line_editor.py ─── keybindings.py
│   │   │                  └── tab_completion.py
│   │   └── multiline_handler.py
│   │       ├── lexer (tokenize)
│   │       ├── parser (parse, ParseError)
│   │       └── prompt.py
│   ├── history_manager.py
│   ├── completion_manager.py ── tab_completion.py
│   ├── prompt_manager.py ────── prompt.py
│   ├── signal_manager.py ────── utils (SignalNotifier, get_signal_registry)
│   │                        └── job_control (JobState)
│   └── rc_loader.py
│       └── input_sources (FileInput)

External dependencies (outside the interactive package):
- psh/shell.py          — Shell (back-reference, owns InteractiveManager)
- psh/core/state.py     — ShellState (options, variables, history)
- psh/job_control.py    — JobManager, Job, Process, JobState
- psh/utils/            — SignalNotifier, get_signal_registry
- psh/lexer/            — tokenize (used by MultiLineInputHandler)
- psh/parser/           — parse, ParseError (used by MultiLineInputHandler)
- psh/prompt.py         — PromptExpander
- psh/tab_completion.py — CompletionEngine, TerminalManager
- psh/keybindings.py    — EditMode, EmacsKeyBindings, ViKeyBindings
- psh/line_editor.py    — LineEditor
- psh/input_sources.py  — FileInput (used by rc_loader)
```
