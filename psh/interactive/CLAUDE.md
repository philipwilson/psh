# Interactive & Job Control Subsystem

This document provides guidance for working with the PSH interactive shell and job control subsystem.

## Architecture Overview

The interactive subsystem handles the shell's REPL loop, history, completion, and job control for managing background processes.

```
InteractiveManager (base.py)
       ↓
┌──────┴──────┬──────────┬──────────┐
↓             ↓          ↓          ↓
REPL       History    Prompt     Signal
Loop       Manager    Manager    Manager
  ↓                                  ↓
Line Editor                    Job Control
(CompletionEngine inside)   (executor/job_control.py)
```

Tab completion is NOT a separate manager: it is `CompletionEngine`
(`tab_completion.py`), owned by the `LineEditor`.

## Key Files

### Interactive (`psh/interactive/`)

| File | Purpose |
|------|---------|
| `repl_loop.py` | `REPLLoop` - main Read-Eval-Print Loop |
| `eof_policy.py` | `ignoreeof_limit` - bash ignoreeof/IGNOREEOF EOF policy (shared by REPL + PS2 handler) |
| `line_editor.py` | `LineEditor` - coordinator: mode policy, the action dispatch table, completion UI |
| `edit_buffer.py` | `EditBuffer` - single source of truth for text + cursor, kill ring, undo/redo |
| `line_renderer.py` | `LineRenderer` - the ONLY writer of ANSI to the terminal |
| `key_decoder.py` | `KeyDecoder` - the ONLY reader of stdin; decodes bytes into `KeyEvent`s |
| `history_nav.py` | `HistoryNavigator` (up/down/first/last) + `HistorySearch` (the Ctrl-R state machine) |
| `line_layout.py` | Pure layout math (row/col positions, prompt width, wrapping) |
| `line_editor_helpers.py` | `convert_multiline_to_single()` - cmdhist-style joining |
| `keybindings.py` | `EditMode`, `EmacsKeyBindings`, `ViKeyBindings` |
| `multiline_handler.py` | `MultiLineInputHandler` - PS2 loop; completeness decided by the shared `CommandAccumulator` (`psh/scripting/command_accumulator.py`) |
| `tab_completion.py` | `CompletionEngine` - path completion (used by LineEditor) |
| `terminal.py` | `TerminalManager` - raw-mode enter/exit context manager |
| `history_manager.py` | `HistoryManager` - command history storage/persistence |
| `history_expansion.py` | `HistoryExpander` - `!!`, `!n`, `!string` expansion |
| `prompt_manager.py` | `PromptManager` - PS1/PS2 retrieval and expansion |
| `prompt.py` | `PromptExpander` - `\u`, `\h`, `\w`... escape expansion |
| `signal_manager.py` | `SignalManager` - signal handling, SIGCHLD/SIGWINCH self-pipes |
| `title.py` | Terminal title (`set_terminal_title`, `idle_title`, `command_title`) |
| `rc_loader.py` | `load_rc_file` / `is_safe_rc_file` - startup RC loading |
| `base.py` | `InteractiveComponent` base class, `InteractiveManager` orchestrator |

### Job Control (`psh/executor/job_control.py`)

| Class | Purpose |
|-------|---------|
| `JobState` | Enum: RUNNING, STOPPED, DONE |
| `Process` | Individual process in a job |
| `Job` | Pipeline or single command |
| `JobManager` | Central job management |

## Core Patterns

### 1. Job State Machine

```python
class JobState(Enum):
    RUNNING = "running"   # Job is executing
    STOPPED = "stopped"   # Job suspended (Ctrl+Z)
    DONE = "done"         # Job completed
```

State transitions:
```
RUNNING → STOPPED (SIGTSTP)
STOPPED → RUNNING (fg/bg)
RUNNING → DONE (exit/signal)
STOPPED → DONE (kill)
```

### 2. Process Group Management

```python
class Job:
    def __init__(self, job_id: int, pgid: int, command: str):
        self.job_id = job_id
        self.pgid = pgid          # Process group ID
        self.command = command
        self.processes = []       # List of Process
        self.state = JobState.RUNNING
        self.foreground = True
        self.notified = False
        self.tmodes = None        # Terminal modes when suspended
```

### 3. Job Manager

```python
class JobManager:
    def __init__(self):
        self.jobs: Dict[int, Job] = {}
        self.next_job_id = 1
        self.current_job = None    # Most recent job (%)
        self.previous_job = None   # Previous job (%-)
        self.shell_pgid = os.getpgrp()
        self.shell_tmodes = None   # Shell's terminal modes (saved at init)
        self.shell_state = None    # Set by shell via set_shell_state()
```

## Job Specification Parsing

| Spec | Meaning |
|------|---------|
| `%n` | Job number n |
| `%+` or `%%` | Current job |
| `%-` | Previous job |
| `%string` | Job whose command starts with string |
| `pid` | Bare number: job containing that PID |

```python
def parse_job_spec(self, spec: str) -> Optional[Job]:
    """Parse job specification like %1, %+, %-, %string."""
    if not spec:
        return self.current_job
    if not spec.startswith('%'):
        try:
            return self.get_job_by_pid(int(spec))  # bare PID
        except ValueError:
            return None
    spec = spec[1:]
    if spec in ('+', '', '%'):
        return self.current_job
    elif spec == '-':
        return self.previous_job
    elif spec.isdigit():
        return self.get_job(int(spec))
    else:  # match by command prefix
        for job in self.jobs.values():
            if job.command.startswith(spec):
                return job
        return None
```

## Interactive Components

### REPL Loop

```python
class REPLLoop(InteractiveComponent):
    def run(self):
        self.setup()  # Creates LineEditor + MultiLineInputHandler

        while True:
            try:
                # 1. Process pending SIGCHLD notifications (self-pipe pattern)
                if hasattr(self.shell, 'interactive_manager'):
                    self.shell.interactive_manager.signal_manager.process_sigchld_notifications()

                # 2. Notify completed/stopped background jobs
                if not self.state.options.get('notify', False):
                    self.job_manager.notify_completed_jobs()
                self.job_manager.notify_stopped_jobs()

                # 3. Idle terminal title, then read a (possibly multi-line) command
                set_terminal_title(idle_title(self.shell))
                on_resize = lambda: set_terminal_title(idle_title(self.shell))
                command = self.multi_line_handler.read_command(on_resize=on_resize)

                if command is None:  # EOF (Ctrl-D)
                    # ignoreeof/IGNOREEOF: swallow up to N consecutive
                    # EOFs with 'Use "exit" to leave the shell.'
                    # (eof_policy.ignoreeof_limit), then apply the
                    # stopped-jobs guard — the first exit attempt with
                    # stopped jobs warns and stays
                    # (JobManager.confirm_exit_with_stopped_jobs, shared
                    # with the exit builtin).
                    ...
                    print()
                    break

                # 4. Execute via unified input system (a non-blank
                # command resets the EOF counter and re-arms the
                # stopped-jobs warning)
                if command.strip():
                    self.shell.run_command(command)

            except KeyboardInterrupt:
                # The line editor already echoed ^C (show_interrupt);
                # printing it again here would duplicate it (r17 L1).
                self.multi_line_handler.reset()
                self.state.last_exit_code = 130  # 128 + SIGINT(2)
                continue
            except EOFError:
                print()
                break

        # Run the EXIT trap (e.g. on Ctrl-D), then save history on exit
        if hasattr(self.shell, 'trap_manager'):
            self.shell.trap_manager.execute_exit_trap()
        self.history_manager.save_to_file()
```

### Line Editor

`line_editor.py` is the core of the subsystem: a raw-mode editor with
emacs and vi modes (no readline). Fully decomposed per Textbook B8
(three releases) into five components, each with a narrow contract;
`LineEditor` itself is the COORDINATOR — it owns mode state (emacs /
vi-insert / vi-normal, the vi repeat count), the dispatch table mapping
action names to operations, and the completion-UI glue, and it wires
the components together:

- **Buffer model**: `EditBuffer` (`edit_buffer.py`) is the single
  source of truth for text + cursor, the kill ring, and undo/redo.
  Every mutating operation returns True when state changed — exactly
  the editor's repaint signal. (The editor's old `buffer`/`cursor_pos`
  compatibility properties were removed in R3; use
  `editor.edit_buffer.chars` / `.cursor` / `.kill_ring` directly.)
- **Rendering**: `LineRenderer` (`line_renderer.py`) is the ONLY
  writer of ANSI to the terminal (`paint`, `redraw`,
  `redraw_after_resize`, `move_cursor_to`). All geometry (rows/columns
  for a given prompt length, buffer position, and terminal width) is
  pure math in `line_layout.py` (`position()`, `total_rows()`,
  `at_row_boundary()`), so wrapping logic is unit-testable without a
  tty. Pinned by snapshot tests.
- **Input decoding**: `KeyDecoder` (`key_decoder.py`) is the ONLY
  reader of stdin. `read_key()` returns one `KeyEvent` — `Char(c)`,
  `Key(name)` for full CSI/SS3 sequences (`'up'`, `'down'`, `'left'`,
  `'right'`, `'home'`, `'end'`, `'delete'`; `Key(None)` for a complete
  but unrecognized sequence), `Meta(c)`, `Escape` (bare ESC), `Resize`
  (the SIGWINCH self-pipe, multiplexed into the decoder's `select()`),
  and `Eof`. Sequences are always consumed in full, so partial CSI
  bytes never leak into the buffer. The 50 ms ESC-disambiguation
  window (`ESC_FOLLOWER_TIMEOUT`, v0.283) is a decoder timing knob:
  vi mode probes it (bare ESC is a key), emacs mode blocks (ESC is
  only a prefix). What an event MEANS is mode policy in the editor
  (`_dispatch_escape_event`): vi turns bare ESC into normal mode and
  `Meta(c)` into "enter normal mode, run c"; emacs maps `Meta(c)`
  through `meta_bindings`. Pinned by pipe-fed byte-stream tests
  (`tests/unit/interactive/test_key_decoder.py`).
- **History navigation & search**: `history_nav.py` (R3). Both classes
  are PURE against the injected history list (which aliases shell
  state and grows between reads) — they compute what the buffer should
  show, never touching the terminal. `HistoryNavigator` owns the
  browse position and the stashed in-progress line; `up()/down()/
  first()/last()` return the text to display or None for "no move",
  and the editor applies it via `EditBuffer.replace_all` + repaint
  (up/down join multi-line entries to their single-line editable
  form). `HistorySearch` is the Ctrl-R incremental-search state
  machine: one instance per session; `feed(char)` returns a
  `SearchState` (search prompt, line, cursor, status ∈
  active/accepted/aborted, plus repaint/redispatch flags) that the
  editor renders via the renderer's prompt-override repaint. Ctrl-R/
  Ctrl-S continue backward/forward, Ctrl-G aborts (restoring the
  pre-search line), Enter accepts the match into the buffer (a second
  Enter executes), and any other control character accepts AND is
  re-dispatched normally. The editor exposes `history`/`history_pos`/
  `original_line`/`search_mode` as properties delegating to these
  components. Pinned by `tests/unit/interactive/test_history_nav.py`
  and the PTY ctrl-r test (which pins the `(bck-i-search)` prompt).
- **Key dispatch**: `keybindings.py` maps keys to action names
  (`EmacsKeyBindings`, `ViKeyBindings`, selected via `EditMode` /
  `set -o vi`). The editor's `_build_action_table()` maps every action
  name to a handler (`dict`, not an elif chain since R3);
  `_execute_action()` is a table lookup. A totality guard test asserts
  every name bound in `keybindings.py` (and `ESCAPE_KEY_ACTIONS`)
  resolves to a callable in the table.
- **Completion**: `CompletionEngine` (`tab_completion.py`) does path
  completion; the editor owns the instance. The completion UI (tab
  handling, applying a completion, listing candidates around a
  raw-mode toggle) deliberately stays in the coordinator: it is pure
  glue between `CompletionEngine`, `TerminalManager` and the renderer.
- **Raw mode**: `TerminalManager` (`terminal.py`) is a context manager
  for termios raw-mode enter/exit.
- **Multi-line input**: `MultiLineInputHandler` (`multiline_handler.py`)
  wraps the editor, prompting with PS2 until a complete logical command
  is read. It does NOT decide completeness itself: every line is fed to
  the shared `CommandAccumulator`
  (`psh/scripting/command_accumulator.py`) — the same parser-driven
  oracle the script/`-c` reader uses — which answers
  `Complete | NeedMore(hint)`. The hint carries what the lexer/parser
  actually know (pending heredoc delimiter, open quote character,
  unclosed expansion kind, and the parser's open-construct trail), and
  the handler renders the construct trail as the contextual
  continuation prompt (`if> `, `for then> `; plain PS2 otherwise).
  The handler keeps only the interactive glue: prompt rendering, the
  read_line loop, and the Ctrl-C `reset()`.

### History: Single Writer

History has exactly ONE writer (v0.283): the source processor
(`psh/scripting/source_processor.py`) calls `shell.add_history()` with the
complete logical command — the line editor records nothing itself.
`HistoryManager.add_to_history()` joins a multi-line command into its
single-line `; ` form via `convert_multiline_to_single()` (bash cmdhist).
The joiner is lexer/parser-driven (reappraisal #15 K2): each newline is
decided per-position — verbatim inside quotes, heredocs and unclosed
expansions, spliced for backslash continuations, a space after tokens
that reject a following `;` (`then`, `do`, `;;`, a case pattern's `)`,
function-definition parens, ...), `; ` otherwise — pinned byte-for-byte
to bash 5.2 by
`tests/unit/test_line_editor_helpers.py`. Recording happens before
parsing, so syntactically invalid commands are still recallable for
editing.

ALIAS CONTRACT (reappraisal #15 K1): the editor's `HistoryNavigator`
holds the `state.history` list OBJECT for the whole session — every
HistoryManager operation mutates it in place (slice assignment / `del`),
never rebinds it, and the editor never substitutes a private list for an
empty one. Pinned by `tests/unit/interactive/test_history_alias_contract.py`.

### Signal Handling

**Where handlers are installed**: process-global signal handlers are set
up at the two entry points only — `psh/__main__.py` (script/`-c` modes)
and `InteractiveManager.run_interactive_loop()` (`base.py`) — NOT at
manager construction. Every `Shell` builds an `InteractiveManager`, but an
in-process test shell or library embedder must not take over the process's
signal dispositions, so `SignalManager.__init__` only creates the
self-pipes; `setup_signal_handlers()` is called explicitly at the entry
points (it picks script-mode vs interactive-mode handler sets via
`state.is_script_mode`).

**Lifecycle symmetry (v0.300)**: `run_interactive_loop()` wraps the REPL
in try/finally and calls `restore_default_handlers()` on EVERY exit path
(EOF, the exit builtin's SystemExit, exceptions) — an embedded Shell no
longer leaves psh handlers installed in the host process. Supporting
guarantees in `signal_manager.py`: the pre-psh original handlers are
saved only by the FIRST `setup_signal_handlers()` call (a second setup
must not overwrite them with psh's own handlers), `SignalNotifier.close()`
is idempotent (no double-close of a reused fd), and the self-pipes are
recreated if the loop is re-entered after a restore. Pinned by the serial
lifecycle tests added in v0.300.

```python
class SignalManager(InteractiveComponent):
    def __init__(self, shell):
        super().__init__(shell)
        # SignalNotifier wraps a self-pipe (os.pipe()) for async-signal-safe notification
        self._sigchld_notifier = SignalNotifier()
        self._sigwinch_notifier = SignalNotifier()
        self._in_sigchld_processing = False  # reentrancy guard

    def setup_signal_handlers(self):
        """Configure signal handlers based on shell mode."""
        if self.state.is_script_mode:
            self._setup_script_mode_handlers()
        else:
            self._setup_interactive_mode_handlers()

    def _handle_sigchld(self, signum, frame):
        # Async-signal-safe: just writes a byte to the pipe
        self._sigchld_notifier.notify(signal.SIGCHLD)

    def process_sigchld_notifications(self):
        # Called from REPL loop — drains pipe, then reaps children
        # (waitpid WNOHANG|WUNTRACED loop, updating job states) outside
        # signal-handler context, guarded against reentrancy.
        ...
```

## Common Tasks

### Adding a Job Control Builtin

1. Create builtin in `psh/builtins/`:
```python
@builtin
class MyJobBuiltin(Builtin):
    @property
    def name(self) -> str:
        return "myjob"

    def execute(self, args, shell):
        job_manager = shell.job_manager

        # Parse job spec ('' → current job)
        job = job_manager.parse_job_spec(args[1] if len(args) > 1 else '')

        if not job:
            self.error("no such job", shell)
            return 1

        # Do something with job
        return 0
```

### Foreground a Job

The `fg` sequence lives in `FgBuiltin` (`psh/builtins/job_control.py`),
built from `JobManager` primitives. Terminal-mode restores use `TCSANOW`
(v0.271 — the drain variants block on a pty whose master isn't being
read):

```python
# From FgBuiltin.execute (trimmed):
self.write_line(job.command, shell)

# Give it terminal control FIRST, before SIGCONT — a resumed job that
# reads the terminal before the transfer would be stopped by SIGTTIN.
shell.job_manager.set_foreground_job(job)   # restores job.tmodes (TCSANOW)
job.foreground = True
if not shell.job_manager.transfer_terminal_control(job.pgid, "fg builtin"):
    shell.job_manager.finish_foreground_job(False, job)  # undo the promotion
    ...error...

try:
    if job.state == JobState.STOPPED:
        job.mark_running()          # counter-aware: STOPPED procs -> RUNNING
        job.state = JobState.RUNNING
        os.killpg(job.pgid, signal.SIGCONT)
    exit_status = shell.job_manager.wait_for_job(job)
finally:
    # Reclaim the terminal even if the wait was interrupted.
    shell.job_manager.restore_shell_foreground()
```

### Background a Job

From `BgBuiltin.execute` (trimmed — bg accepts multiple jobspecs, one resumed
per operand):

```python
if job.state == JobState.STOPPED:
    job.mark_running()              # counter-aware: STOPPED procs -> RUNNING
    job.state = JobState.RUNNING
    job.foreground = False
    os.killpg(job.pgid, signal.SIGCONT)
    self.write_line(f"[{job.job_id}]+ {job.command} &", shell)
```

## Key Implementation Details

### Terminal Control Transfer

`JobManager.transfer_terminal_control()` is the single source of truth
for ALL `tcsetpgrp()` calls — every executor that hands the terminal to a
foreground job (or reclaims it) goes through here, so capability checks
and debug logging live in one place:

```python
def transfer_terminal_control(self, pgid: int, context: str = "") -> bool:
    """Transfer terminal control to a process group.

    Returns True if transfer was successful, False otherwise.
    Skips (returns False) when shell_state.supports_job_control is off.
    """
```

The shell-side counterpart is `restore_shell_foreground()`: reclaim the
terminal, restore the shell's terminal modes, clear foreground
bookkeeping (in that order — restoring modes while another process group
owns the terminal blocks).

### Reaping Children

Reaping happens in `SignalManager.process_sigchld_notifications()`
(called from the REPL loop, outside signal-handler context):

```python
while True:
    try:
        pid, status = os.waitpid(-1, os.WNOHANG | os.WUNTRACED)
        if pid == 0:
            break
        job = self.job_manager.get_job_by_pid(pid)
        if job:
            job.update_process_status(pid, status)
            job.update_state()
            if job.state == JobState.STOPPED and job.foreground:
                job.notified = False
                # Foreground job stopped — take the terminal back
                self.job_manager.transfer_terminal_control(
                    os.getpgrp(), "SignalManager:SIGCHLD")
    except OSError:
        break  # No more children
```

### Job Notification

```python
def notify_completed_jobs(self):
    """Print notifications for completed background jobs."""
    completed = []
    for job_id, job in list(self.jobs.items()):
        if job.state == JobState.DONE and not job.notified and not job.foreground:
            print(f"\n[{job.job_id}]+  Done                    {job.command}")
            job.notified = True
            completed.append(job_id)
    # Remove completed jobs after notification
    ...
```

## Testing

```bash
# Run job control tests (serial-marked; don't run under bare -n auto)
python -m pytest tests/unit/builtins/test_job_control_builtins.py tests/integration/job_control/ -v

# Line editor unit tests (no tty needed — layout math is pure)
python -m pytest tests/unit/test_line_editor_unit.py tests/unit/test_line_editor_multiline.py -v

# In-process interactive/system tests (run in the normal suite)
python -m pytest tests/system/interactive/ -v

# Opt-in PTY tier: real pseudo-terminal end-to-end tests, skipped unless
# --run-interactive is given. The harness is
# tests/framework/pty_test_framework.py — repaired in v0.295 (sentinel
# PS1 prompt sync, stale-output drain per command, PS2 handling,
# strip_ansi normalization; previously every run_command returned the
# PREVIOUS command's output window).
python -m pytest tests/system/interactive/test_interactive_features.py --run-interactive -v

# Test interactively
python -m psh
$ sleep 10 &
[1] 12345
$ jobs
[1]+  Running  sleep 10 &
$ fg %1
```

There is deliberately no nested pytest.ini under `tests/system/interactive/`
(removed in v0.295 — it hijacked the pytest rootdir and broke direct
invocation with `--run-interactive`).

## Common Pitfalls

1. **Terminal Control**: Only the foreground process group can read from terminal.

2. **Signal Safety**: Only use async-signal-safe functions in signal handlers.

3. **Process Group Setup**: Child must call `setpgid()` before parent continues.

4. **Terminal Modes**: Save/restore terminal modes when suspending/resuming.

5. **Zombie Prevention**: Always reap children with `waitpid()`.

6. **Race Conditions**: Use self-pipe pattern for signal handling.

## Debug Options

```bash
python -m psh --debug-exec  # Debug process groups and signals
```

## Integration Points

### With Executor (`psh/executor/`)

- `ProcessLauncher` creates process groups
- Jobs registered with `JobManager` after fork
- Terminal control transferred for foreground jobs

### With Shell State (`psh/core/state.py`)

- `state.last_bg_pid` updated for `$!`
- `state.supports_job_control` checked before terminal ops
- `state.options['notify']` (-b) enables immediate job-completion notifications;
  `state.options['monitor']` (-m) is job control mode

### With Builtins (`psh/builtins/`)

- `jobs`, `fg`, `bg`, `wait`, `disown`, `kill` interact with `JobManager`
- Access via `shell.job_manager`
