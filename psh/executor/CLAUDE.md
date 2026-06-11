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
| `command.py` | `CommandExecutor` - simple command execution |
| `pipeline.py` | `PipelineExecutor` - pipeline and process group management |
| `control_flow.py` | `ControlFlowExecutor` - loops, conditionals, case |
| `function.py` | `FunctionOperationExecutor` - function calls and scope |
| `subshell.py` | `SubshellExecutor` - subshells and brace groups |
| `array.py` | `ArrayOperationExecutor` - array initialization |
| `process_launcher.py` | `ProcessLauncher` - unified process creation |
| `child_policy.py` | `apply_child_signal_policy()` - single source of truth for child signal setup |
| `strategies.py` | Execution strategies for different command types |
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

Commands are dispatched through execution strategies in priority order:

```python
# In command.py — POSIX lookup order:
# special builtins > functions > builtins > aliases > external
strategies = [
    SpecialBuiltinExecutionStrategy(),  # : break continue eval exec exit export ...
    FunctionExecutionStrategy(),         # User-defined functions
    BuiltinExecutionStrategy(),          # cd echo pwd test [ ...
    AliasExecutionStrategy(),            # Aliases
    ExternalExecutionStrategy()          # External programs
]
```

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
    ↓
1. Expand assignments
2. Expand arguments (variables, globs, etc.)
3. Try each execution strategy in order
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
4. Return exit code (last command, or first failure if pipefail)
```

## Common Tasks

### Adding a New Builtin

1. Create builtin in `psh/builtins/mybuiltin.py`:
```python
from .builtin_base import Builtin, builtin

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

1. Add AST node in `psh/ast_nodes.py`

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

All forked child processes apply the unified signal policy via
`apply_child_signal_policy()` in `child_policy.py`. This is the single
source of truth for child signal setup:

1. Set `state.in_forked_child = True`
2. Temporarily ignore SIGTTOU (prevents STOP during setup)
3. Reset all signals to SIG_DFL via `signal_manager.reset_child_signals()`
4. If `is_shell_process=True`: re-ignore SIGTTOU

The `is_shell_process` flag controls SIGTTOU disposition:

- **Shell processes** (`is_shell_process=True`): Keep SIGTTOU=SIG_IGN so they
  can call `tcsetpgrp()` for job control (subshells, brace groups, command
  substitution children, process substitution children).
- **Leaf processes** (`is_shell_process=False`, default): SIGTTOU=SIG_DFL,
  appropriate for external commands that don't manage terminal control.

All 3 fork paths use this policy (file_redirect.py and io_redirect/manager.py
no longer fork — they delegate to `process_sub.create_process_substitution`):

| Fork Path | File | is_shell_process |
|-----------|------|-----------------|
| ProcessLauncher | `process_launcher.py` | `config.is_shell_process` |
| Command substitution | `expansion/command_sub.py` | `True` |
| Process substitution | `io_redirect/process_sub.py` | `True` |

### Process Group Management

- Pipeline leader creates new process group: `os.setpgid(0, 0)`
- Members join leader's group: `os.setpgid(0, leader_pid)`
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
- Exit code: `shell.state.last_exit_status`
- Options: `shell.state.options` (errexit, pipefail, etc.)

### With Job Control (`psh/executor/job_control.py`)

- Job table: `shell.job_manager`
- Background jobs: `Job` objects with process group info

### With I/O Manager (`psh/io_redirect/`)

- Per-command redirections: `io_manager.with_redirections(redirects)`
  (context manager) or `apply_redirections()` / restore
- Builtin stream redirections: `io_manager.setup_builtin_redirections(command)`
- Forked-child redirections: `io_manager.setup_child_redirections(command)`
