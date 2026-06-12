# Executor Public API Reference

**As of v0.182.0** (post-cleanup)

This document describes the public API of the `psh.executor` package: the
items declared in `__all__`, their signatures, and guidance on internal
imports that are available but not part of the public contract.

## Public API (`__all__`)

The declared public API consists of five items:

```python
__all__ = [
    'ExecutorVisitor',
    'ExecutionContext',
    'ExternalExecutionStrategy',
    'apply_child_signal_policy',
    'TestExpressionEvaluator',
]
```

### `ExecutorVisitor`

```python
from psh.executor import ExecutorVisitor

visitor = ExecutorVisitor(shell: Shell)
exit_status = visitor.visit(ast_node)
```

The main entry point for AST execution.  `ExecutorVisitor` is an
`ASTVisitor[int]` that walks AST nodes and returns integer exit status
codes.  It is the facade for the entire execution engine.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `shell` | `Shell` | The shell instance providing access to state, managers, and I/O. |

#### How it works

On construction, `ExecutorVisitor` creates six specialised sub-executors
and wires them together:

| Sub-executor | Handles |
|-------------|---------|
| `CommandExecutor` | Simple commands (builtins, functions, externals). |
| `PipelineExecutor` | Pipelines and process group management. |
| `ControlFlowExecutor` | `if`, `while`, `until`, `for`, `case`, `select`, `break`, `continue`. |
| `FunctionOperationExecutor` | Function definitions and calls. |
| `ArrayOperationExecutor` | Array initialisation and element assignment. |
| `SubshellExecutor` | Subshells `(...)` and brace groups `{ ...; }`. |

External code does not interact with these sub-executors directly.  The
visitor dispatches to them via `visit_*` methods:

```python
from psh.executor import ExecutorVisitor

visitor = ExecutorVisitor(shell)
exit_code = visitor.visit(ast)  # walks the entire AST
```

#### Visitor methods

| Method | AST Node | Delegates to |
|--------|----------|-------------|
| `visit_TopLevel` | `TopLevel` | Iterates items, handles errexit. |
| `visit_StatementList` | `StatementList` | Iterates statements. |
| `visit_AndOrList` | `AndOrList` | Short-circuit `&&` / `||`. |
| `visit_Pipeline` | `Pipeline` | `PipelineExecutor` |
| `visit_SimpleCommand` | `SimpleCommand` | `CommandExecutor` |
| `visit_IfConditional` | `IfConditional` | `ControlFlowExecutor` |
| `visit_WhileLoop` | `WhileLoop` | `ControlFlowExecutor` |
| `visit_UntilLoop` | `UntilLoop` | `ControlFlowExecutor` |
| `visit_ForLoop` | `ForLoop` | `ControlFlowExecutor` |
| `visit_CStyleForLoop` | `CStyleForLoop` | `ControlFlowExecutor` |
| `visit_CaseConditional` | `CaseConditional` | `ControlFlowExecutor` |
| `visit_SelectLoop` | `SelectLoop` | `ControlFlowExecutor` |
| `visit_BreakStatement` | `BreakStatement` | `ControlFlowExecutor` |
| `visit_ContinueStatement` | `ContinueStatement` | `ControlFlowExecutor` |
| `visit_SubshellGroup` | `SubshellGroup` | `SubshellExecutor` |
| `visit_BraceGroup` | `BraceGroup` | `SubshellExecutor` |
| `visit_FunctionDef` | `FunctionDef` | `FunctionOperationExecutor` |
| `visit_ArithmeticEvaluation` | `ArithmeticEvaluation` | Inline (calls `evaluate_arithmetic`). |
| `visit_EnhancedTestStatement` | `EnhancedTestStatement` | `shell.execute_enhanced_test_statement()` |
| `visit_ArrayInitialization` | `ArrayInitialization` | `ArrayOperationExecutor` |
| `visit_ArrayElementAssignment` | `ArrayElementAssignment` | `ArrayOperationExecutor` |
| `generic_visit` | Any unknown node | Fallback; handles `CommandList` as `StatementList`. |

### `ExecutionContext`

```python
from psh.executor import ExecutionContext

ctx = ExecutionContext()
```

Dataclass that encapsulates execution state for parameter passing between
sub-executors.  Replaces scattered instance variables with a structured
approach.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `in_pipeline` | `bool` | `False` | Currently inside a pipeline. |
| `in_subshell` | `bool` | `False` | Currently in a subshell. |
| `in_forked_child` | `bool` | `False` | Currently in a forked child process. |
| `loop_depth` | `int` | `0` | Current loop nesting depth. |
| `current_function` | `Optional[str]` | `None` | Name of the currently executing function. |
| `pipeline_context` | `Optional[PipelineContext]` | `None` | Active pipeline state. |
| `background_job` | `Optional[Job]` | `None` | Background job reference. |
| `suppress_function_lookup` | `bool` | `False` | Skip function lookup (for `command` builtin). |
| `exec_mode` | `bool` | `False` | In `exec` builtin mode. |

#### Factory methods

Each method returns a new `ExecutionContext` with specific fields adjusted:

| Method | Returns | Purpose |
|--------|---------|---------|
| `fork_context()` | `ExecutionContext` | Context for a forked child (`in_subshell=True`, `in_forked_child=True`). |
| `subshell_context()` | `ExecutionContext` | Context for subshell execution. |
| `pipeline_context_enter()` | `ExecutionContext` | Context with `in_pipeline=True`. |
| `loop_context_enter()` | `ExecutionContext` | Context with `loop_depth` incremented. |
| `function_context_enter(name)` | `ExecutionContext` | Context with `current_function` set. |
| `with_pipeline_context(ctx)` | `ExecutionContext` | Context with a specific `PipelineContext`. |
| `with_background_job(job)` | `ExecutionContext` | Context with a background job reference. |

#### Query methods

| Method | Returns | Description |
|--------|---------|-------------|
| `in_loop()` | `bool` | Whether `loop_depth > 0`. |
| `in_function()` | `bool` | Whether `current_function` is set. |
| `should_use_print()` | `bool` | Whether builtins should use `print()` vs raw FD writes. |

### `ExternalExecutionStrategy`

```python
from psh.executor import ExternalExecutionStrategy

strategy = ExternalExecutionStrategy()
if strategy.can_execute(cmd_name, shell):
    exit_code = strategy.execute(cmd_name, args, shell, context,
                                  redirects=None, background=False,
                                  visitor=None)
```

Strategy for executing external commands.  This is the fallback strategy
in the command dispatch chain — its `can_execute()` always returns `True`.

Used outside the executor package by `builtins/command_builtin.py` to run
external commands directly, bypassing function/alias lookup.

| Parameter | Type | Default | Meaning |
|-----------|------|---------|---------|
| `cmd_name` | `str` | — | The command name. |
| `args` | `List[str]` | — | Command arguments (excluding the command name). |
| `shell` | `Shell` | — | Shell instance. |
| `context` | `ExecutionContext` | — | Current execution context. |
| `redirects` | `Optional[List[Redirect]]` | `None` | Redirections to apply. |
| `background` | `bool` | `False` | Run in background. |
| `visitor` | — | `None` | Unused by this strategy. |

For pipeline commands (`context.in_pipeline`), the strategy calls
`os.execvpe()` directly to replace the current process.  For standalone
commands, it uses `ProcessLauncher` to fork, exec, and manage job
control.

### `apply_child_signal_policy()`

```python
from psh.executor import apply_child_signal_policy

apply_child_signal_policy(signal_manager, state, is_shell_process=False)
```

The single source of truth for child process signal setup.  Must be
called in every child process immediately after `os.fork()`.

| Parameter | Type | Default | Meaning |
|-----------|------|---------|---------|
| `signal_manager` | `SignalManager` | — | Provides `reset_child_signals()`. |
| `state` | `ShellState` | — | Sets `_in_forked_child` flag. |
| `is_shell_process` | `bool` | `False` | `True` for subshells, command/process substitution children that run shell commands. `False` for leaf processes that will exec. |

Steps performed:

1. Set `state._in_forked_child = True`.
2. Temporarily ignore SIGTTOU (prevents STOP during setup).
3. Reset all signals to SIG_DFL via `signal_manager.reset_child_signals()`.
4. If `is_shell_process`: re-ignore SIGTTOU so the process can call
   `tcsetpgrp()` for job control.

All 5 fork paths in the codebase use this function:

| Fork path | File | `is_shell_process` |
|-----------|------|--------------------|
| ProcessLauncher | `executor/process_launcher.py` | `config.is_shell_process` |
| Command substitution | `expansion/command_sub.py` | `True` |
| Process substitution | `io_redirect/process_sub.py` | `True` |
| File redirect proc-sub | `io_redirect/file_redirect.py` | `True` |
| IOManager builtin proc-sub | `io_redirect/manager.py` | `True` |

### `TestExpressionEvaluator`

```python
from psh.executor import TestExpressionEvaluator

evaluator = TestExpressionEvaluator(shell)
result: bool = evaluator.evaluate(test_expression)
```

Evaluates `[[ ]]` enhanced test expressions.  Takes a `TestExpression`
AST node and returns a boolean result.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `shell` | `Shell` | Shell instance for variable expansion and file tests. |

The evaluator handles:

- **Binary tests**: string comparisons (`=`, `==`, `!=`, `<`, `>`),
  arithmetic comparisons (`-eq`, `-ne`, `-lt`, `-le`, `-gt`, `-ge`),
  file comparisons (`-nt`, `-ot`, `-ef`), regex matching (`=~`),
  pattern matching (`==` with unquoted RHS).
- **Unary tests**: file tests (`-f`, `-d`, `-e`, ...), string tests
  (`-n`, `-z`), variable tests (`-v`).
- **Compound tests**: logical operators (`&&`, `||`).
- **Negated tests**: `!` prefix.

Used by `shell.py` in `execute_enhanced_test_statement()`.

## Convenience Imports (not in `__all__`)

The following items are importable from `psh.executor` for convenience but
are **not** part of the declared public contract.  They are internal
implementation details whose signatures may change without notice.

Existing code that imports these will continue to work; the imports are
kept specifically to avoid churn.  New code should prefer the submodule
import paths listed below.

### Sub-executors

| Import | Canonical path | Purpose |
|--------|---------------|---------|
| `CommandExecutor` | `psh.executor.command` | Simple command execution (builtins, functions, externals). |
| `PipelineExecutor` | `psh.executor.pipeline` | Pipeline execution and process group management. |
| `PipelineContext` | `psh.executor.pipeline` | Pipeline state management (pipes, processes, job). |
| `ControlFlowExecutor` | `psh.executor.control_flow` | Control structures (if, while, for, case, select). |
| `FunctionOperationExecutor` | `psh.executor.function` | Function definition and execution. |
| `ArrayOperationExecutor` | `psh.executor.array` | Array initialisation and element operations. |
| `SubshellExecutor` | `psh.executor.subshell` | Subshell and brace group execution. |

### Strategy classes

| Import | Canonical path | Purpose |
|--------|---------------|---------|
| `ExecutionStrategy` | `psh.executor.strategies` | ABC for command execution strategies. |
| `BuiltinExecutionStrategy` | `psh.executor.strategies` | Regular builtin command execution. |
| `FunctionExecutionStrategy` | `psh.executor.strategies` | Shell function execution. |

## Submodule-Only Imports

These classes have zero callers outside the executor package and are not
importable from `psh.executor`.  Import them from their defining module:

```python
from psh.executor.process_launcher import ProcessLauncher, ProcessConfig, ProcessRole
from psh.executor.strategies import SpecialBuiltinExecutionStrategy, AliasExecutionStrategy
from psh.executor.strategies import POSIX_SPECIAL_BUILTINS
```

| Class / Constant | Purpose |
|------------------|---------|
| `ProcessLauncher` | Unified process creation with fork, job control, and signal setup. |
| `ProcessConfig` | Dataclass configuring process launch (role, pgid, foreground, sync pipes, I/O setup). |
| `ProcessRole` | Enum: `SINGLE`, `PIPELINE_LEADER`, `PIPELINE_MEMBER`. |
| `SpecialBuiltinExecutionStrategy` | POSIX special builtins that take precedence over functions. |
| `AliasExecutionStrategy` | Alias expansion and re-execution. |
| `POSIX_SPECIAL_BUILTINS` | `set` of POSIX special builtin names (`:`, `break`, `eval`, `exec`, ...). |

## API Tiers Summary

| Tier | Scope | How to import | Stability guarantee |
|------|-------|---------------|-------------------|
| **Public** | `ExecutorVisitor`, `ExecutionContext`, `ExternalExecutionStrategy`, `apply_child_signal_policy`, `TestExpressionEvaluator` | `from psh.executor import ...` | Stable.  Changes are versioned. |
| **Convenience** | Sub-executors (`CommandExecutor`, `PipelineExecutor`, etc.) and strategy classes (`ExecutionStrategy`, `BuiltinExecutionStrategy`, `FunctionExecutionStrategy`) | `from psh.executor import ...` (works) or `from psh.executor.<module> import ...` (preferred) | Available but not guaranteed.  Prefer submodule paths. |
| **Internal** | `ProcessLauncher`, `ProcessConfig`, `ProcessRole`, `SpecialBuiltinExecutionStrategy`, `AliasExecutionStrategy`, `POSIX_SPECIAL_BUILTINS` | `from psh.executor.<module> import ...` | Internal.  May change without notice. |

## Typical Usage

### Execute a parsed AST

```python
from psh.executor import ExecutorVisitor

visitor = ExecutorVisitor(shell)
exit_code = visitor.visit(ast)
```

This is the primary usage pattern.  `shell.py` creates an
`ExecutorVisitor` and calls `visit()` for every command the user enters.

### Run an external command directly (bypassing function/alias lookup)

```python
from psh.executor import ExecutionContext, ExternalExecutionStrategy

context = ExecutionContext()
strategy = ExternalExecutionStrategy()
exit_code = strategy.execute('ls', ['-la'], shell, context)
```

This is used by the `command` builtin to run external commands without
alias or function expansion.

### Set up child signal policy after fork

```python
from psh.executor import apply_child_signal_policy

pid = os.fork()
if pid == 0:
    apply_child_signal_policy(
        shell.interactive_manager.signal_manager,
        shell.state,
        is_shell_process=True,
    )
    # ... execute child logic ...
```

### Evaluate a [[ ]] test expression

```python
from psh.executor import TestExpressionEvaluator

evaluator = TestExpressionEvaluator(shell)
result = evaluator.evaluate(test_stmt.expression)
exit_code = 0 if result else 1
```

## Related Documents

- `docs/guides/executor_guide.md` -- Full programmer's guide (architecture,
  file reference, design rationale)
- `docs/guides/executor_public_api_assessment.md` -- Analysis that led to
  this cleanup
- `psh/executor/CLAUDE.md` -- AI assistant working guide for the executor
  subsystem
