# PSH Executor: Programmer's Guide

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> references pre-relocation paths such as `psh/job_control.py` (now `psh/executor/job_control.py`), `psh/arithmetic.py` (now `psh/expansion/arithmetic.py`), and `psh/token_types.py` (now `psh/lexer/token_types.py`).
> See the subsystem CLAUDE.md files for current structure.

This guide covers the executor package in detail: its external API, internal
architecture, and the responsibilities of every source file.  It is aimed at
developers who need to modify the executor, add new command types, or
understand how an AST becomes executed commands.

## 1. What the Executor Does

The executor walks the AST produced by the parser and carries out the
commands it describes.  It handles simple commands (builtins, functions,
external programs), pipelines, control flow (loops, conditionals, case),
subshells, brace groups, array operations, and function definitions.

The executor does **not** tokenise or parse input.  It receives a fully
constructed AST from the parser and produces side effects (process
execution, variable assignment, I/O operations) and exit status codes.

## 2. External API

The public interface is defined in `psh/executor/__init__.py`.  The declared
`__all__` contains five items: `ExecutorVisitor`, `ExecutionContext`,
`ExternalExecutionStrategy`, `apply_child_signal_policy`, and
`TestExpressionEvaluator`.  See `docs/guides/executor_public_api.md` for full
signature documentation and API tiers.

### 2.1 `ExecutorVisitor`

```python
from psh.executor import ExecutorVisitor

visitor = ExecutorVisitor(shell)
exit_code = visitor.visit(ast)
```

The main entry point.  Inherits from `ASTVisitor[int]`, meaning every
`visit_*` method returns an integer exit status.  The visitor constructs six
specialised sub-executors and delegates to them based on AST node type.

### 2.2 `ExecutionContext`

```python
from psh.executor import ExecutionContext

ctx = ExecutionContext()
forked_ctx = ctx.fork_context()
loop_ctx = ctx.loop_context_enter()
```

Dataclass with 9 fields tracking execution state (pipeline membership, loop
depth, function name, etc.).  Factory methods create derived contexts for
entering pipelines, loops, subshells, and functions.

### 2.3 `ExternalExecutionStrategy`

```python
from psh.executor import ExternalExecutionStrategy

strategy = ExternalExecutionStrategy()
exit_code = strategy.execute(cmd_name, args, shell, context)
```

Strategy for launching external programs.  The only execution strategy with
callers outside the executor package (used by `command_builtin.py`).

### 2.4 `apply_child_signal_policy()`

```python
from psh.executor import apply_child_signal_policy

apply_child_signal_policy(signal_manager, state, is_shell_process=False)
```

Single source of truth for child process signal setup.  Called in all 5 fork
paths across the codebase.  Resets signals to SIG_DFL and optionally keeps
SIGTTOU ignored for shell processes that need `tcsetpgrp()`.

### 2.5 `TestExpressionEvaluator`

```python
from psh.executor import TestExpressionEvaluator

evaluator = TestExpressionEvaluator(shell)
result = evaluator.evaluate(expr)  # returns bool
```

Evaluates `[[ ]]` test expressions: binary comparisons, unary file/string
tests, compound `&&`/`||`, and negation.  Used exclusively by `shell.py`.

### 2.6 Convenience imports (not in `__all__`)

The following are importable from `psh.executor` but are not part of the
declared public API.  They are internal implementation details kept as
convenience imports to avoid churn.  New code should prefer the canonical
submodule paths.

**Sub-executors** (from individual modules):
`CommandExecutor`, `PipelineExecutor`, `PipelineContext`,
`ControlFlowExecutor`, `FunctionOperationExecutor`,
`ArrayOperationExecutor`, `SubshellExecutor`

**Strategy classes** (from `psh.executor.strategies`):
`ExecutionStrategy`, `BuiltinExecutionStrategy`,
`FunctionExecutionStrategy`

**Submodule-only** (not importable from `psh.executor`; import from
their defining modules):
`ProcessLauncher`, `ProcessConfig`, `ProcessRole`,
`SpecialBuiltinExecutionStrategy`, `AliasExecutionStrategy`,
`POSIX_SPECIAL_BUILTINS`


## 3. Architecture

### 3.1 Execution pipeline

```
AST
 │
 ▼
ExecutorVisitor.visit(node)
 │
 ├─ dispatch based on node type:
 │   ├─ TopLevel/StatementList/AndOrList → iterate, handle errexit/&&/||
 │   ├─ Pipeline → PipelineExecutor
 │   ├─ SimpleCommand → CommandExecutor
 │   │   └─ strategy chain:
 │   │       ├─ SpecialBuiltinExecutionStrategy  (: break eval exec ...)
 │   │       ├─ BuiltinExecutionStrategy         (cd echo pwd test ...)
 │   │       ├─ FunctionExecutionStrategy        (user functions)
 │   │       ├─ AliasExecutionStrategy           (aliases)
 │   │       └─ ExternalExecutionStrategy        (external programs)
 │   ├─ IfConditional/WhileLoop/... → ControlFlowExecutor
 │   ├─ SubshellGroup/BraceGroup → SubshellExecutor
 │   ├─ FunctionDef → FunctionOperationExecutor
 │   ├─ ArithmeticEvaluation → evaluate_arithmetic()
 │   ├─ EnhancedTestStatement → TestExpressionEvaluator
 │   └─ ArrayInitialization/ArrayElementAssignment → ArrayOperationExecutor
 │
 ▼
Exit status (int)
```

### 3.2 Visitor pattern

`ExecutorVisitor` extends `ASTVisitor[int]` from the visitor package.  The
base class provides `visit(node)`, which looks up `visit_{NodeTypeName}` via
a method cache and dispatches.  Each `visit_*` method returns an integer
exit code.

```python
class ExecutorVisitor(ASTVisitor[int]):
    def visit_SimpleCommand(self, node: SimpleCommand) -> int:
        return self.command_executor.execute(node, self.context)

    def visit_Pipeline(self, node: Pipeline) -> int:
        return self.pipeline_executor.execute(node, self.context, self)
```

The visitor holds an `ExecutionContext` instance that tracks loop depth,
pipeline membership, and other state.  Sub-executors receive this context
and create derived contexts for nested scopes.

### 3.3 Strategy pattern for commands

`CommandExecutor` dispatches simple commands through a chain of strategies,
tried in order until one claims the command:

```python
# In command.py
EXECUTION_ORDER = [
    SpecialBuiltinExecutionStrategy(),  # : break continue eval exec exit ...
    BuiltinExecutionStrategy(),          # cd echo pwd test [ ...
    FunctionExecutionStrategy(),         # User-defined functions
    AliasExecutionStrategy(),            # Aliases
    ExternalExecutionStrategy(),         # External programs (fallback)
]
```

Each strategy implements:

- `can_execute(cmd_name, shell) -> bool` &mdash; whether this strategy
  handles the command.
- `execute(cmd_name, args, shell, context, redirects, background, visitor)
  -> int` &mdash; execute and return exit status.

`ExternalExecutionStrategy.can_execute()` always returns `True`, making it
the catch-all fallback.

### 3.4 Unified process creation

All forked processes go through `ProcessLauncher`:

```python
class ProcessLauncher:
    def launch(self, child_action: Callable, config: ProcessConfig) -> Tuple[int, int]:
        """Fork and execute with proper job control.

        Returns (pid, pgid).
        """
```

`ProcessConfig` specifies the process's role (`SINGLE`, `PIPELINE_LEADER`,
`PIPELINE_MEMBER`), process group ID, foreground status, sync pipes, and
I/O setup callback.

In the child, `ProcessLauncher`:

1. Sets up the process group (`os.setpgid()`).
2. Applies `apply_child_signal_policy()`.
3. Runs the I/O setup callback (if any).
4. Signals the parent via sync pipe.
5. Calls the child action.

In the parent, `ProcessLauncher`:

1. Waits for the sync pipe signal.
2. Records the child's PID and process group.
3. Returns `(pid, pgid)` for job tracking.

### 3.5 Child signal policy

`apply_child_signal_policy()` in `child_policy.py` is the single source of
truth for signal setup after `fork()`.  It:

1. Marks `state._in_forked_child = True`.
2. Temporarily ignores SIGTTOU.
3. Resets all signals to SIG_DFL.
4. If `is_shell_process=True`, re-ignores SIGTTOU (so the process can call
   `tcsetpgrp()` without being stopped).

The `is_shell_process` flag distinguishes:

- **Shell processes** (`True`): subshells, brace groups, command/process
  substitution children &mdash; they run shell commands and may need
  terminal control.
- **Leaf processes** (`False`): external commands about to `exec()` &mdash;
  they inherit default signal dispositions.

### 3.6 Pipeline execution

`PipelineExecutor` handles multi-command pipelines:

1. Create `PipelineContext` with a `JobManager` reference.
2. Set up pipes between commands (`os.pipe()`).
3. Fork each command via `ProcessLauncher`:
   - First command: `PIPELINE_LEADER` (creates process group).
   - Subsequent commands: `PIPELINE_MEMBER` (joins leader's group).
4. Close parent-side pipe FDs.
5. Wait for all processes.
6. Return exit status (last command, or first failure if `pipefail`).

`PipelineContext` tracks pipes, process PIDs, and the associated job.

### 3.7 Control flow execution

`ControlFlowExecutor` handles all control structures:

| Method | Structure |
|--------|-----------|
| `execute_if(node, ctx, visitor)` | `if`/`elif`/`else`/`fi` |
| `execute_while(node, ctx, visitor)` | `while`/`do`/`done` |
| `execute_until(node, ctx, visitor)` | `until`/`do`/`done` |
| `execute_for(node, ctx, visitor)` | `for`/`in`/`do`/`done` |
| `execute_c_style_for(node, ctx, visitor)` | `for ((init; cond; update))` |
| `execute_case(node, ctx, visitor)` | `case`/`esac` |
| `execute_select(node, ctx, visitor)` | `select`/`in`/`do`/`done` |
| `execute_break(node, ctx)` | `break [n]` |
| `execute_continue(node, ctx)` | `continue [n]` |

Loop methods create a derived context with `loop_context_enter()` (which
increments `loop_depth`), then iterate the loop body using `visitor.visit()`.
`break` and `continue` raise `LoopBreak` and `LoopContinue` exceptions,
caught by the enclosing loop method.

### 3.8 Subshell and brace group execution

`SubshellExecutor` handles:

- **Subshells** `(commands)` &mdash; fork a child process, execute the body
  in the child, wait for it, return exit status.  The child gets its own
  copy of shell state.
- **Brace groups** `{ commands; }` &mdash; execute the body in the current
  shell.  For background brace groups, fork a child.

Both use `ProcessLauncher` for forking and handle redirections and
background execution.

### 3.9 Function execution

`FunctionOperationExecutor` handles:

- **Function definition** (`visit_FunctionDef`) &mdash; registers the
  function body in the `FunctionManager`.
- **Function calls** (`execute_function_call`) &mdash; sets up positional
  parameters, creates a local scope, executes the function body, and
  restores the previous scope.  Catches `FunctionReturn` to implement the
  `return` builtin.

### 3.10 Array operations

`ArrayOperationExecutor` handles:

- **Array initialisation** &mdash; `arr=(a b c)` for indexed arrays,
  `arr=([key]=val ...)` for associative arrays.  Supports append mode
  (`arr+=(...)`) and glob expansion within elements.
- **Element assignment** &mdash; `arr[i]=value` for indexed arrays,
  `arr[key]=value` for associative arrays.

### 3.11 Test expression evaluation

`TestExpressionEvaluator` evaluates `[[ ]]` expressions recursively:

- **Binary**: string/arithmetic/file comparisons, regex/pattern matching.
- **Unary**: file tests (`-f`, `-d`, `-e`, ...), string tests (`-n`, `-z`),
  variable existence (`-v`).
- **Compound**: `&&` (short-circuit AND), `||` (short-circuit OR).
- **Negated**: `!` prefix.

Variable expansion is applied to operands before evaluation.  Pattern
matching supports extglob when the `extglob` option is enabled.


## 4. Source File Reference

All files are under `psh/executor/`.  Line counts are approximate.

### 4.1 Package entry point

#### `__init__.py` (~47 lines)

Defines `__all__` with 5 public items.  Re-exports public API and
convenience imports.  Module docstring lists all submodules.

### 4.2 Core execution

#### `core.py` (~320 lines)

The `ExecutorVisitor` class.  Instantiates six sub-executors, provides 20+
`visit_*` methods, and handles top-level iteration (errexit, `&&`/`||`).
The `generic_visit` fallback handles `CommandList` as `StatementList`.

#### `context.py` (~190 lines)

The `ExecutionContext` dataclass.  9 fields, 7 factory methods for derived
contexts, and 3 query methods.  Immutable-by-convention: factory methods
return new instances rather than mutating.

### 4.3 Command execution

#### `command.py` (~610 lines)

`CommandExecutor` &mdash; handles `SimpleCommand` nodes.  Responsibilities:

- Extract and apply variable assignments.
- Expand arguments via `ExpansionManager`.
- Apply redirections via `IOManager`.
- Dispatch to the strategy chain (special builtins > builtins > functions >
  aliases > externals).
- Handle `xtrace` (`set -x`) output.
- Handle assignment-only commands (no command name, just `VAR=value`).

#### `strategies.py` (~425 lines)

Five strategy classes implementing the Strategy pattern:

| Strategy | Priority | `can_execute()` |
|----------|----------|-----------------|
| `SpecialBuiltinExecutionStrategy` | 1st | Command is in `POSIX_SPECIAL_BUILTINS` set and registered. |
| `BuiltinExecutionStrategy` | 2nd | Command is registered and NOT a special builtin. |
| `FunctionExecutionStrategy` | 3rd | Command is a defined function. |
| `AliasExecutionStrategy` | 4th | Command is a defined alias (not escaped with `\`). |
| `ExternalExecutionStrategy` | 5th | Always `True` (fallback). |

Also defines `POSIX_SPECIAL_BUILTINS` set and the `ExecutionStrategy` ABC.

### 4.4 Pipeline execution

#### `pipeline.py` (~500 lines)

`PipelineContext` &mdash; tracks pipes, processes, and the associated job
for a running pipeline.

`PipelineExecutor` &mdash; orchestrates multi-command pipelines: creates
pipes, forks commands via `ProcessLauncher`, manages process groups, waits
for completion, and handles `pipefail`.

### 4.5 Control flow

#### `control_flow.py` (~650 lines)

`ControlFlowExecutor` &mdash; implements `if`, `while`, `until`, `for`
(standard and C-style), `case`, `select`, `break`, and `continue`.

Key patterns:

- Loops increment `loop_depth` via `context.loop_context_enter()`.
- `break`/`continue` raise `LoopBreak`/`LoopContinue` exceptions with a
  level count.
- `case` pattern matching uses `fnmatch` for glob patterns and `re` for
  extglob.
- `for` loops expand the word list through `ExpansionManager`.
- C-style `for` uses `evaluate_arithmetic()` for init, condition, and
  update expressions.

### 4.6 Function execution

#### `function.py` (~140 lines)

`FunctionOperationExecutor` &mdash; function definition (registers body in
`FunctionManager`) and function calls (scope setup, positional parameters,
body execution, `FunctionReturn` handling).

### 4.7 Subshell execution

#### `subshell.py` (~310 lines)

`SubshellExecutor` &mdash; subshell and brace group execution.  Subshells
fork via `ProcessLauncher` with process isolation.  Brace groups execute
in-process but can fork for background execution.  Both handle redirections
and the `background` flag.

### 4.8 Array operations

#### `array.py` (~280 lines)

`ArrayOperationExecutor` &mdash; array initialisation (`arr=(...)` for
indexed and associative arrays, with append mode) and element assignment
(`arr[i]=value`).  Uses `evaluate_arithmetic()` for index evaluation and
`ExpansionManager` for element expansion.

### 4.9 Process management

#### `process_launcher.py` (~345 lines)

`ProcessRole` enum (`SINGLE`, `PIPELINE_LEADER`, `PIPELINE_MEMBER`).

`ProcessConfig` dataclass (role, pgid, foreground, sync pipes, I/O setup
callback, `is_shell_process` flag).

`ProcessLauncher` &mdash; centralised fork/exec with process group setup,
sync pipe coordination, and signal policy application.

#### `child_policy.py` (~45 lines)

`apply_child_signal_policy()` &mdash; single source of truth for child
signal setup.  See section 3.5 above.

### 4.10 Test evaluation

#### `test_evaluator.py` (~200 lines)

`TestExpressionEvaluator` &mdash; evaluates `[[ ]]` expressions.  Handles
binary, unary, compound, and negated test expressions.  Delegates unary
file tests to `TestBuiltin` and uses `fnmatch`/`re` for pattern matching.


## 5. How the Shell Calls the Executor

In `psh/shell.py`, the execution path:

1. Tokenise and parse the input (see parser guide).
2. Create an `ExecutorVisitor`:
   ```python
   from psh.executor import ExecutorVisitor
   visitor = ExecutorVisitor(self)
   ```
3. Walk the AST:
   ```python
   exit_status = visitor.visit(ast)
   ```
4. Update `$?` with the exit status.

For `[[ ]]` test statements, `shell.py` has a dedicated method that
creates a `TestExpressionEvaluator` directly:

```python
from psh.executor import TestExpressionEvaluator
evaluator = TestExpressionEvaluator(self)
result = evaluator.evaluate(test_stmt.expression)
```


## 6. Common Tasks

### 6.1 Adding a new control structure

1. **AST node** &mdash; create a dataclass in `psh/ast_nodes.py`, inheriting
   from `UnifiedControlStructure`.
2. **Token types** &mdash; add keyword token types in `psh/token_types.py`.
3. **Parser** &mdash; add parsing in
   `psh/parser/recursive_descent/parsers/control_structures.py`.
4. **Visitor method** &mdash; add `visit_MyStructure()` in `core.py`:
   ```python
   def visit_MyStructure(self, node: MyStructure) -> int:
       return self.control_flow_executor.execute_my_structure(node, self.context, self)
   ```
5. **Executor method** &mdash; add `execute_my_structure()` in
   `control_flow.py`.
6. **Tests** &mdash; add tests in `tests/integration/control_flow/`.

### 6.2 Adding a new execution strategy

1. Create a class inheriting from `ExecutionStrategy`:
   ```python
   class MyStrategy(ExecutionStrategy):
       def can_execute(self, cmd_name, shell):
           return ...  # True if this strategy handles the command

       def execute(self, cmd_name, args, shell, context,
                   redirects=None, background=False, visitor=None):
           # Execute and return exit code
           return 0
   ```
2. Add an instance to the `EXECUTION_ORDER` list in `command.py` at the
   appropriate priority position.
3. Add tests.

### 6.3 Modifying process creation

All process creation goes through `ProcessLauncher`.  To modify:

1. Add configuration to `ProcessConfig`:
   ```python
   @dataclass
   class ProcessConfig:
       role: ProcessRole
       # ... existing fields ...
       my_new_field: bool = False
   ```
2. Handle the new field in `ProcessLauncher.launch()` or
   `ProcessLauncher._child_setup_and_exec()`.

### 6.4 Adding a new array operation

1. Add an AST node in `psh/ast_nodes.py`.
2. Add parsing in `psh/parser/recursive_descent/parsers/arrays.py`.
3. Add a visitor method in `core.py`:
   ```python
   def visit_MyArrayOp(self, node: MyArrayOp) -> int:
       return self.array_executor.execute_my_array_op(node)
   ```
4. Add the executor method in `array.py`.

### 6.5 Debugging execution

```bash
# Show process creation, signals, job control
python -m psh --debug-exec -c "echo hello | cat"

# Show variable and command substitution
python -m psh --debug-expansion -c "echo $HOME"

# Show AST before execution
python -m psh --debug-ast -c "for i in 1 2 3; do echo \$i; done"
```


## 7. Design Rationale

### Why a visitor pattern instead of methods on AST nodes?

Putting execution logic on AST nodes would couple the data model to the
execution engine.  The visitor pattern keeps the AST as pure data
(dataclasses) and lets the executor be one of several visitors (alongside
the metrics visitor, linter visitor, and formatter visitors in the visitor
package).

### Why delegate to six sub-executors?

A single monolithic `ExecutorVisitor` would be thousands of lines.
Delegating to focused sub-executors keeps each file manageable:
`command.py` handles command dispatch, `pipeline.py` handles pipe/fork
orchestration, `control_flow.py` handles loops and conditionals, etc.

### Why a strategy chain instead of a switch statement?

The Strategy pattern for command dispatch makes the priority order explicit
and extensible.  Adding a new command type (e.g. a plugin system) only
requires adding a new strategy &mdash; no existing code changes.  The
POSIX-mandated priority (special builtins > functions > builtins) is
encoded in the chain order.

### Why a unified `ProcessLauncher`?

Before `ProcessLauncher`, each fork path (pipelines, external commands,
background builtins, subshells) had its own fork/exec logic with
duplicated process group setup, signal handling, and job control.
`ProcessLauncher` consolidates this into a single component, ensuring
consistency and eliminating ~130 lines of duplicated code.

### Why a single `apply_child_signal_policy()` function?

Child signal setup is safety-critical &mdash; incorrect signal disposition
after fork can cause processes to ignore Ctrl+C, fail to stop on SIGTTOU,
or leave zombie processes.  Having a single function that all 5 fork paths
call ensures the policy is consistent and bugs are fixed in one place.

### Why is `ExecutionContext` immutable-by-convention?

Factory methods like `loop_context_enter()` return new instances rather
than mutating the existing context.  This prevents accidental state leaks
between nested scopes (e.g. a loop incrementing `loop_depth` and
forgetting to decrement it).


## 8. Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Misuse of builtin |
| 126 | Command not executable |
| 127 | Command not found |
| 128+N | Killed by signal N (e.g. 130 = SIGINT) |


## 9. File Dependency Graph

```
__init__.py
├── core.py  (ExecutorVisitor)
│   ├── command.py  (CommandExecutor)
│   │   └── strategies.py  (5 strategies, POSIX_SPECIAL_BUILTINS)
│   │       └── process_launcher.py  (ProcessLauncher, ProcessConfig, ProcessRole)
│   ├── pipeline.py  (PipelineContext, PipelineExecutor)
│   │   └── process_launcher.py
│   ├── control_flow.py  (ControlFlowExecutor)
│   ├── function.py  (FunctionOperationExecutor)
│   ├── subshell.py  (SubshellExecutor)
│   │   └── process_launcher.py
│   ├── array.py  (ArrayOperationExecutor)
│   └── context.py  (ExecutionContext)
├── child_policy.py  (apply_child_signal_policy)
└── test_evaluator.py  (TestExpressionEvaluator)

External dependencies (outside the executor package):
- psh/ast_nodes.py       — AST node dataclasses
- psh/visitor/           — ASTVisitor base class
- psh/core/state.py      — ShellState, variables, options
- psh/expansion/         — ExpansionManager for argument expansion
- psh/io_redirect/       — IOManager for redirections
- psh/job_control.py     — JobManager, Job, JobState
- psh/builtins/          — BuiltinRegistry, individual builtins
- psh/arithmetic.py      — evaluate_arithmetic() for (( )) and C-style for
- psh/core/exceptions.py — LoopBreak, LoopContinue, ReadonlyVariableError
```
