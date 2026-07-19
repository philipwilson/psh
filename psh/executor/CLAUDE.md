# Executor Subsystem

This document provides guidance for working with the PSH executor subsystem.

## Architecture Overview

The executor transforms AST nodes into executed commands using a **visitor pattern** with delegation to specialized executors. All process creation goes through a unified `ProcessLauncher`.

```
AST → ExecutorVisitor → Specialized Executors → ProcessLauncher → OS
              ↓
    ┌─────────┼──────────┬──────────┬──────────┐
    ↓         ↓          ↓          ↓          ↓
Command  Pipeline  ControlFlow  Function  Subshell
Executor  Executor   Executor   Executor  Executor
```

## Key Files

| File | Purpose |
|------|---------|
| `core.py` | `ExecutorVisitor` - main visitor coordinating all execution |
| `command.py` | `CommandExecutor` - simple command dispatch (expansion, one resolution, redirections). Normalizes the command word, builds the overlay, and resolves ONCE (`resolve_command`) BEFORE any scope/prefix decision, then drives the scope model / `exec` shortcut / POSIX prefix-error branch / persistence from the returned `ResolvedCommand` (never a raw-name recompute — #20 H10) |
| `command_resolution.py` | `NormalizedCommandName` / `CommandEnvOverlay` / `ResolvedCommand` + `resolve_command` (R3). The SOLE mode-aware dispatch reader of the function/builtin registries; the raw `get_function`/`POSIX_SPECIAL_BUILTINS` dispatch recomputes are gone (guarded by `tests/unit/tooling/test_command_resolution_ratchet_r3.py`). The overlay carries the resolution-relevant prefix facts — notably `has_posix_override`: a `POSIXLY_CORRECT=` prefix (name-level, nameref-resolved, readonly-blocked excluded) resolves ITS OWN command in posix mode, since bash installs assignments before lookup. Values expand later in `apply_prefix` (expanding early would reorder `A=$(c1) PATH=$(c2)` side effects); the command hash/PATH stay with `command_resolver.py`, whose deferred external search reads the live environment the installed prefix determines |
| `command_assignments.py` | `CommandAssignments` - the `NAME=value` sub-domain (extract/build_overlay/apply_pure/apply_prefix/restore/commit); its module docstring states the POSIX assignment-ordering-and-persistence contract (persistence only in POSIX mode) |
| `pipeline.py` | `PipelineExecutor` - pipeline and process group management |
| `control_flow.py` | `ControlFlowExecutor` - loops, conditionals, case |
| `function.py` | `FunctionOperationExecutor` - function calls and scope |
| `subshell.py` | `SubshellExecutor` - subshells and brace groups |
| `array.py` | `ArrayOperationExecutor` - array initialization |
| `process_launcher.py` | `ProcessLauncher` - unified process creation |
| `child_policy.py` | The "becoming a healthy child process" chapter: `fork_with_signal_window()`, `apply_child_signal_policy()`, `map_child_exception()` (the ONE child-exit taxonomy), `run_child_body()` (shared child-Shell body runner), `run_child_shell()` (substitution-child runner, built on `run_child_body`), `flush_child_streams()` |
| `job_control.py` | `JobManager`, `Job`, `Process` - job table and waiting (moved into the package in v0.285). The shared value vocabulary `JobState`/`JobSpecOutcome`/`JobSpecResult`/`jobspec_error_messages`/`exit_status_from_wait_status` lives in `psh/core/job_state.py` (so the job builtins need not import the executor — P4) and is re-exported here for existing callers |
| `strategies.py` | Execution strategies for different command types, plus shared helpers `report_exec_failure()` and `execute_builtin_guarded()` |
| `command_resolver.py` | `CommandResolver` - the ONE command-name resolution service (PATH walk, ordered typed candidates, executor exec resolution). Consumed by the external strategy and by `command`/`type`/`hash`; see `psh/builtins/CLAUDE.md` "Command resolution" |
| `enhanced_test_evaluator.py` | `[[ ]]` test expression evaluation |
| `context.py` | `ExecutionContext` - execution state |

## Core Patterns

### 1. Visitor Pattern

`ExecutorVisitor` dispatches to `visit_*` methods based on AST node type:

```python
class ExecutorVisitor:
    def visit(self, node):
        method = getattr(self, f'visit_{type(node).__name__}', None)
        if method:
            return method(node)
        raise NotImplementedError(f"No visitor for {type(node)}")

    def visit_SimpleCommand(self, node): ...
    def visit_Pipeline(self, node): ...
    def visit_IfConditional(self, node): ...
```

### 2. Strategy Pattern for Commands

Commands are dispatched through execution strategies whose order is
**mode-aware**, decided once in `command_resolution.py#resolve_command`
from `set -o posix`:

- **Default (bash) mode:** functions > (special | regular) builtins >
  external. Functions shadow even POSIX special builtins. A `NAME=value`
  prefix before a special builtin is TEMPORARY, like any builtin.
- **POSIX mode:** special builtins > functions > regular builtins >
  external. Special builtins take precedence over functions, and a prefix
  before one PERSISTS.

The strategy instances live on `CommandExecutor.strategies` in
default-mode order (`FunctionExecutionStrategy`,
`SpecialBuiltinExecutionStrategy`, `BuiltinExecutionStrategy`,
`ExternalExecutionStrategy`); `resolve_command` moves special builtins to
the front when `posix` is set and returns a `ResolvedCommand` whose
`assignments_persist` (True only for a special builtin under `posix`),
`uses_temp_env_scope` (function → temp-env scope), and `is_exec_special`
fields the dispatcher consumes — computed ONCE, before the scope/prefix
decision, so a POSIX special builtin shadowed by a same-named function is no
longer misclassified as a function (H10).

Aliases are NOT a runtime strategy. They are expanded as a token-stream
transform at the lex→parse boundary (`AliasManager.expand_aliases`, wired
in `psh/scripting/source_processor.py` and `command_accumulator.py`), so by
the time a command reaches the executor its command word is already the
alias-expanded token. This is the R8.6b architecture (replacing the old
runtime `AliasExecutionStrategy`).

### 3. Unified Process Creation

All forked processes go through the single shared instance
`shell.process_launcher`:

```python
class ProcessLauncher:
    def launch(self, execute_fn: Callable[[], int],
               config: ProcessConfig) -> Tuple[int, int]:
        """Fork and run execute_fn in the child; returns (pid, pgid).

        Handles fork, child signal policy, process-group setup, and
        optional sync pipes (when config requests them). The CALLER is
        responsible for creating the Job, registering it, and waiting —
        see strategies.py / pipeline.py for the pattern.
        """
```

### 4. Process Roles

```python
class ProcessRole(Enum):
    SINGLE = "single"                    # Standalone command
    PIPELINE_LEADER = "pipeline_leader"  # First in pipeline (creates pgroup)
    PIPELINE_MEMBER = "pipeline_member"  # Subsequent pipeline processes
```

## Execution Flow

### Simple Command Execution

```
SimpleCommand AST
    ↓
CommandExecutor.execute()
    ↓ (wraps everything in io_manager.process_sub_scope(), which closes
       parent-side fds and reaps process-substitution children on exit)
1. Extract NAME=value prefix words (CommandAssignments.extract; pure
   assignments — no command word — short-circuit via apply_pure)
2. Expand command arguments (variables, globs, etc. — BEFORE the
   assignments apply, per POSIX; see command_assignments.py docstring)
3. Apply prefix assignments (CommandAssignments.apply_prefix)
4. Try each execution strategy in order
5. Restore assignments (CommandAssignments.restore) — unless, in POSIX
   mode, the command was a POSIX special builtin, where they persist
   instead (CommandAssignments.commit)
    ↓
BuiltinExecutionStrategy.execute()  -- or --  ExternalExecutionStrategy.execute()
    ↓                                              ↓
Builtin.execute()                        ProcessLauncher.launch()
    ↓                                              ↓
Exit code                                   fork() + execvp()
```

### Pipeline Execution

```
Pipeline AST
    ↓
PipelineExecutor.execute()
    ↓
1. Create pipes between commands
2. Fork each command:
   - First: PIPELINE_LEADER (creates process group)
   - Rest: PIPELINE_MEMBER (joins process group)
3. Wait for all processes
4. Return exit code (last command; with pipefail, the rightmost non-zero
   status, or 0 if all succeeded)
```

## Common Tasks

### Adding a New Builtin

1. Create builtin in `psh/builtins/mybuiltin.py`:
```python
from .base import Builtin
from .registry import builtin

@builtin
class MyBuiltin(Builtin):
    name = "mybuiltin"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        # args[0] is the command name
        # Return exit code (0 = success)
        return 0
```

2. The `@builtin` decorator auto-registers it

3. Add tests in `tests/unit/builtins/`

### Adding a New Control Structure

1. Add AST node in the `psh/ast_nodes/` package (control structures go in
   `psh/ast_nodes/control.py`)

2. Add parser support in `psh/parser/`

3. Add visitor method in `core.py`:
```python
def visit_MyStructure(self, node):
    return self.control_flow.execute_my_structure(node)
```

4. Add execution in `control_flow.py`:
```python
def execute_my_structure(self, node) -> int:
    # Execute the structure
    return exit_code
```

### Modifying Process Creation

All process creation goes through `ProcessLauncher`. To modify:

1. Add configuration to `ProcessConfig`:
```python
@dataclass
class ProcessConfig:
    role: ProcessRole
    pgid: Optional[int] = None
    foreground: bool = True
    # Add new fields here
```

2. Handle in `ProcessLauncher._child_setup_and_exec()`

## Key Implementation Details

### Signal Handling

All fork sites fork via `fork_with_signal_window()` in `child_policy.py`,
which blocks SIGTERM/SIGINT/SIGHUP/SIGQUIT across the fork window (the
v0.300 lost-signal race fix; the parent's mask is restored even when
fork() raises). All forked children then apply the unified signal policy
via `apply_child_signal_policy()` — the single source of truth for child
signal setup:

1. Set `state.in_forked_child = True`
2. Temporarily ignore SIGTTOU (prevents STOP during setup)
3. Reset all signals to SIG_DFL via `signal_manager.reset_child_signals()`
4. If `is_shell_process=True`: re-ignore SIGTTOU
5. Unblock the termination signals blocked by `fork_with_signal_window()`
   (a signal that arrived in the window now takes its default action)

The `is_shell_process` flag controls SIGTTOU disposition:

- **Shell processes** (`is_shell_process=True`): Keep SIGTTOU=SIG_IGN so they
  can call `tcsetpgrp()` for job control (subshells, brace groups, command
  substitution children, process substitution children).
- **Leaf processes** (`is_shell_process=False`, default): SIGTTOU=SIG_DFL,
  appropriate for external commands that don't manage terminal control.

All 3 fork paths use this policy (file_redirect.py and io_redirect/manager.py
no longer fork — they delegate to `process_sub.create_process_substitution`):

| Fork Path | File | is_shell_process | Child body |
|-----------|------|-----------------|------------|
| ProcessLauncher | `process_launcher.py` | `config.is_shell_process` | own path: `_child_setup_and_exec` |
| Command substitution | `expansion/command_sub.py` | `True` | `run_child_shell()` |
| Process substitution | `io_redirect/process_sub.py` | `True` | `run_child_shell()` |

### The Shared Child-Body Runner (`run_child_shell`)

Both substitution fork sites run their child branch through
`child_policy.run_child_shell(parent_shell, body, *, norc, io_setup,
error_label)`, which owns everything generic about being a forked psh
child — the semantic boundary is "becoming a healthy child" (runner) vs
"what this child does" (caller):

1. `apply_child_signal_policy(..., is_shell_process=True)`
2. the caller's `io_setup` hook — its pipe/dup2 plumbing (runs BEFORE
   the child Shell is built, because Shell construction inspects fds
   via isatty)
3. `Shell.for_subshell(parent, norc=norc)` + `state.in_forked_child = True`
4. `run_child_body(child_shell, body, ...)` — the shared MIDDLE every
   child-Shell fork performs (also used by `SubshellExecutor`'s foreground
   `( )` body): fork-child flags, the fresh-fork trap-disposition sync (and
   inherited-trap drop for process substitution), errexit-suppression
   seeding (+ errexit-option reset for command substitution), body
   execution, and the child's EXIT trap. A body-level control-flow / exit
   exception maps through `map_child_exception` — the ONE taxonomy
   (`TopLevelAbort`→`.status`, `FunctionReturn`→`.exit_code`,
   `LoopBreak`/`LoopContinue`→`.exit_status or 0`, `SystemExit`→its code,
   `SystemExit(None)`→0): substitutions/subshells run in a subshell, so
   `exit`/`break`/`return` must not unwind the parent.
5. `flush_child_streams(child.stdout, child.stderr, sys.stdout, sys.stderr)`
6. `os._exit(exit_code)`; any other exception → `psh: {error_label}
   error: ...` on fd 2, then `os._exit(1)`

ProcessLauncher's `_child_setup_and_exec` deliberately does NOT use
`run_child_body`/`run_child_shell` (see its docstring): launcher children
need process-group and sync-pipe setup, may exec an external binary (so
`KeyboardInterrupt`→130 is a launcher-local arm), and reuse the parent Shell
object in the forked copy instead of building a child Shell. The shared
pieces ARE shared as code, not copies: `fork_with_signal_window()`,
`apply_child_signal_policy()`, `flush_child_streams()`, and — for the
exit-code mapping every fork site needs — `map_child_exception()`
(guarded single-source by `tests/unit/tooling/test_child_exit_taxonomy_centralized.py`).

Note: `expansion/command_sub.py` keeps a documented parent-side SIGCHLD
reset (SIG_DFL around the fork/waitpid) so the interactive SIGCHLD
notification path can't steal the substitution child's exit status.

### Process Group Management

- Pipeline leader creates new process group: `os.setpgid(0, 0)` in the child
  (the parent also calls `os.setpgid(pid, pid)` — whichever runs first wins)
- Members never call `setpgid` themselves: the **parent** assigns them with
  `os.setpgid(pid, leader_pgid)` while each member blocks on the sync pipe,
  so no member runs before the group exists
- Foreground processes get terminal: `tcsetpgrp()`

### Expansion Order

POSIX-compliant expansion order:
1. Brace expansion (non-POSIX)
2. Tilde expansion
3. Parameter/variable expansion
4. Command substitution
5. Arithmetic expansion
6. Word splitting (on unquoted results)
7. Pathname expansion (globbing)
8. Quote removal

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Misuse of builtin |
| 126 | Command not executable |
| 127 | Command not found |
| 128+N | Killed by signal N |

## Testing

```bash
# Run executor tests (integration tests)
python -m pytest tests/integration/ -v

# Test specific control structure
python -m pytest tests/integration/control_flow/ -v

# Test pipelines (requires special handling)
python run_tests.py  # Uses smart test runner

# Debug execution
python -m psh --debug-exec -c "echo hello | cat"
```

## Common Pitfalls

1. **Fork in Tests**: Subshell tests run fine under normal pytest capture (no `-s` needed, as of v0.195.0). Forked children operate at the fd level — stdout via `os.write(1)` and stdin via `os.read(fd)` after `os.dup2` — so pytest's `sys.stdout`/`sys.stdin` replacement doesn't interfere.

2. **Signal Safety**: Don't call non-async-signal-safe functions after `fork()` before `exec()`.

3. **Process Group Timing**: Use sync pipes to ensure process group is set up before parent continues.

4. **Expansion Context**: Some expansions (like `$@`) behave differently in quotes vs unquoted.

5. **Exit Code Propagation**: Control structures must properly propagate exit codes from their bodies.

## Debug Options

```bash
python -m psh --debug-exec      # Process creation, signals, job control
python -m psh --debug-expansion # Variable and command substitution
```

## Integration Points

### With Shell State (`psh/core/state.py`)

- Variables: `shell.state.variables`
- Exit code: `shell.state.last_exit_code`
- Options: `shell.state.options` (errexit, pipefail, etc.)

### With Job Control (`psh/executor/job_control.py`)

- Job table: `shell.job_manager`
- Background jobs: `Job` objects with process group info

### With I/O Manager (`psh/io_redirect/`)

- Per-command redirections: `io_manager.with_redirections(redirects)`
  (context manager) or `apply_redirections()` / restore
- Builtin stream redirections: `io_manager.setup_builtin_redirections(command)`
  returns a per-invocation `BuiltinRedirectFrame`; pass it to
  `restore_builtin_redirections(frame)` (frames nest — eval/source/traps)
- Forked-child redirections: `io_manager.setup_child_redirections(command)`
