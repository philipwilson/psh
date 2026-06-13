# Executor / Command Dispatch Architecture Review

Date: 2026-06-13

Scope: `psh/executor/`, with emphasis on command dispatch, process launch, pipelines, subshells, functions, control flow, and the assignment/dispatch boundary. I read the current subsystem code and `psh/executor/CLAUDE.md` for context, but this review is based on the implementation, not older review notes.

## Verification

Focused executor, pipeline, subshell, job-control, command-resolution, and redirection integration run:

```sh
python -m pytest tests/unit/executor tests/unit/io_redirect tests/integration/redirection tests/integration/pipeline tests/integration/subshells tests/integration/job_control tests/integration/command_resolution/test_hash_execution.py tests/regression/test_visitor_executor_review_fixes.py -q
```

Result:

```text
2 failed, 531 passed, 1 skipped in 24.88s
```

The executor-focused tests themselves passed. The two failures are redirection/process-substitution failures:

- `tests/unit/io_redirect/test_fd_operations.py::TestDynamicDupTarget::test_dup_stdout_to_arithmetic_fd`
- `tests/integration/redirection/test_process_sub_cleanup.py::TestProcessSubOutputCorrectness::test_write_side_substitution_tee`

Those are analyzed in the companion redirection/IO review.

## Executive Verdict

The executor is substantially better than a naïve shell interpreter. It has a real visitor layer, specialist executors, a centralized assignment policy module, an explicit strategy chain for command resolution, a unified `ProcessLauncher`, and a named child-signal policy. This is good production-minded architecture.

It is not textbook quality yet. The core semantics are spread across several correct but delicate orchestration paths. The main remaining uglies are not missing abstractions; they are places where policy, execution state, redirection mode, and shell compatibility exceptions still interleave in long methods and side channels.

Quality rating by area:

| Area | Rating | Direction | Short version |
| --- | --- | --- | --- |
| Visitor/delegation shape | Good | Stable | Clear top-level dispatcher, but statement-loop logic is duplicated. |
| Simple command orchestration | Adequate to good | Improving | Correct phase ordering, too much in one method. |
| Assignment prefix semantics | Good | Improved | Strong separation and strong documentation. |
| Command resolution strategies | Adequate | Stable | Useful pattern, but strategy classes still own too many execution details. |
| Process launch / child policy | Good | Improving | Centralized forking and signal discipline are strong. |
| Pipelines/job control | Solid but intricate | Stable | Correct-looking, hard to reason about due shared visitor mutation and low-level pgid/fd work. |
| Functions/subshells | Adequate | Stable | Semantics are explicit, but several forked-shell paths overlap. |
| Control flow | Adequate | Stable | Mostly clear, but repetitive context/redirection scaffolding. |

## What Is Strong

### 1. The visitor layer is a useful boundary

`ExecutorVisitor` delegates simple commands, pipelines, control flow, arrays, functions, and subshells to specialist executors (`psh/executor/core.py:81`). That keeps AST walking separate from the details of each execution domain.

This is the right direction for a shell: compound syntax should not be executed by one giant `if isinstance(...)` chain.

### 2. Command assignment semantics are now well isolated

`CommandAssignments` owns extraction, expansion, application, restoration, readonly behavior, and pure-assignment status (`psh/executor/command_assignments.py:1`). Its module docstring states the POSIX/bash ordering contract clearly. `CommandExecutor` now decides when those phases run rather than embedding all assignment details itself (`psh/executor/command.py:107`, `psh/executor/command.py:183`, `psh/executor/command.py:230`).

This is close to textbook quality for a hard shell subproblem.

### 3. Command resolution order is explicit

The strategy list encodes special builtins, functions, regular builtins, aliases, then external commands (`psh/executor/command.py:67`). This makes the resolution order discoverable and testable.

The special-builtin distinction also flows back to assignment persistence (`psh/executor/command.py:221`, `psh/executor/command.py:230`). That is a subtle POSIX rule, and it is at least visible in the dispatcher.

### 4. Process creation has a central launcher

`ProcessLauncher.launch()` owns fork setup, parent process-group assignment, child setup, signal reset, optional I/O setup, exception-to-status mapping, flushing, and `os._exit()` (`psh/executor/process_launcher.py:97`, `psh/executor/process_launcher.py:140`). Pipelines, external commands, background builtins/functions, and subshells call through it.

That is much better than ad hoc `os.fork()` calls scattered across every execution path.

### 5. Child signal policy is named and documented

`child_policy.py` is a strong piece of design. `fork_with_signal_window()` and `apply_child_signal_policy()` encode a specific race fix around inherited Python signal handlers and pending termination signals (`psh/executor/child_policy.py:29`, `psh/executor/child_policy.py:69`). `run_child_shell()` gives command/process substitution children a shared body runner (`psh/executor/child_policy.py:132`).

This is exactly the kind of low-level shell invariant that deserves a single module.

### 6. Pipeline execution has replaced timing hacks with synchronization

Pipeline members wait on a sync pipe until the parent has forked every process and established the process group (`psh/executor/pipeline.py:142`, `psh/executor/process_launcher.py:189`). This is a serious improvement over sleeps or polling.

## Remaining Uglies

### Ugly 1: `CommandExecutor._execute_command()` is still a multi-phase semantic hub

`_execute_command()` handles DEBUG traps, array assignments, raw assignment extraction, command-substitution status reset, pure assignments, command-node slicing, backslash bypass, argument expansion, empty-command fallback, `$_`, prefix assignments, readonly + `errexit`, xtrace, special `exec`, pending array initializer delivery, strategy execution, assignment restore, and exception mapping (`psh/executor/command.py:96`).

The ordering is carefully documented, but the method is still the place where too many concepts meet. This makes it hard to change one rule without breaking another phase.

Recommended change:

1. Introduce a `SimpleCommandPlan` produced before execution:
   - `raw_assignments`
   - `command_words`
   - `redirects`
   - `bypass_aliases`
   - `bypass_functions`
   - `declaration_eligible`
2. Introduce a `ResolvedSimpleCommand` after expansion:
   - `cmd_name`
   - `argv`
   - `prefix_outcome`
   - `pending_array_inits`
   - `resolution_flags`
3. Keep the existing phase order but move each phase into a named method that returns one of those objects.

The goal is not abstraction for its own sake; it is to make POSIX phase ordering inspectable without reading a 140-line nested try/finally block.

### Ugly 2: assignment persistence is communicated as a boolean side effect of dispatch

`_execute_with_strategy()` returns `(exit_code, is_special_builtin)` (`psh/executor/command.py:363`). The caller then decides whether to restore prefix assignments (`psh/executor/command.py:230`). This works, but it is brittle: special-builtin persistence is command-resolution metadata, and it is returned in the same tuple as process exit status.

Recommended change:

- Return an `ExecutionResult` object with:
  - `status`
  - `resolved_kind`
  - `prefix_assignments_persist`
  - possibly `job`
- Let strategies or a resolver produce a `CommandResolution` before execution.

That would prevent future dispatch paths from accidentally forgetting to communicate persistence.

### Ugly 3: redirection mode selection lives inside command dispatch

`_execute_with_strategy()` decides whether a command should use Python stream redirection, fd-level redirection, child redirection, or no parent redirection based on strategy type, `context.in_pipeline`, and `state.in_forked_child` (`psh/executor/command.py:392`). The comments are good, but this is a cross-subsystem policy living in command dispatch.

Recommended change:

- Add a `RedirectionMode` decision function, for example:
  - `BUILTIN_STREAM_FRAME`
  - `PARENT_FD_CONTEXT`
  - `CHILD_FD_ONLY`
  - `NONE`
- Make that function take `resolved_kind`, `in_pipeline`, `in_forked_child`, and `background`.
- Test it as a pure policy table.

That would make the hard rule visible without requiring readers to mentally execute the strategy loop.

### Ugly 4: declaration array initializers use a shell attribute side channel

Structured array initializers for declaration builtins are put on `shell._pending_array_inits` before strategy execution and cleared afterward (`psh/executor/command.py:215`). The comments make the scope discipline clear, but it is still an implicit channel between executor and builtins.

Recommended change:

- Add an execution metadata object passed into builtin execution, or let declaration builtins receive an optional structured-argument map through a formal API.
- If changing all builtins is too disruptive, start with a `BuiltinInvocation` object for declaration builtins only.

This would remove a hidden dependency from the shell object.

### Ugly 5: strategy classes mix resolution, execution, background forking, parsing, and job registration

The strategy pattern is useful, but the classes are not pure strategies. Examples:

- `AliasExecutionStrategy` expands, re-tokenizes, parses, manages recursion, and executes the resulting AST (`psh/executor/strategies.py:315`).
- `BuiltinExecutionStrategy` forks background builtins and registers jobs (`psh/executor/strategies.py:203`).
- `FunctionExecutionStrategy` creates a fresh `FunctionOperationExecutor` and also forks/registers background functions (`psh/executor/strategies.py:247`, `psh/executor/strategies.py:275`).
- `ExternalExecutionStrategy` resolves hashes, manages terminal title/control, launches the process, creates jobs, waits, and removes jobs (`psh/executor/strategies.py:383`).

Recommended change:

Separate command resolution from command invocation:

1. `CommandResolver.resolve(name, flags) -> CommandTarget`
2. `CommandInvoker.invoke(target, argv, invocation_context) -> ExecutionResult`
3. Keep background/job-control handling in an `AsyncCommandRunner` or in the process/job layer.

This would make strategies smaller and reduce the number of places that know about job registration.

### Ugly 6: alias expansion happens after expansion and reparses joined argv

`AliasExecutionStrategy` builds a new command string from the alias definition plus `' '.join(args)`, then tokenizes and parses that string (`psh/executor/strategies.py:345`, `psh/executor/strategies.py:349`, `psh/executor/strategies.py:357`). At this point `args` are already expanded command arguments, not original lexical words.

That is not how shell aliases are normally modeled. Aliases are lexical/parser-time substitutions before most expansion. Reconstructing source text from expanded data can make data become syntax, and it will mishandle arguments that originally contained whitespace, quotes, command separators, redirections, or other shell metacharacters.

Recommended change:

- Move alias expansion to the lexer/parser boundary, before word expansion.
- If runtime alias execution must remain temporarily, preserve structured `Word` tokens instead of joining expanded strings.
- Add tests proving that alias arguments containing semicolons, redirection tokens, quotes, and spaces are not reparsed as shell syntax unless they came from the alias definition itself.

### Ugly 7: top-level and statement-list execution duplicate the same loop policy

`visit_TopLevel()` and `visit_StatementList()` both run pending traps, visit items, update `$?`, and check `errexit` (`psh/executor/core.py:103`, `psh/executor/core.py:143`). They differ mostly in control-flow exception handling.

Recommended change:

- Extract a private `_execute_sequence(items, *, top_level: bool)` or a small `StatementRunner`.
- Make control-flow exception policy explicit in parameters.

This would reduce one of the easiest future drift risks.

### Ugly 8: pipeline execution mutates the shared visitor context in forked children

Each pipeline child sets `visitor.context = child_context` before visiting its command (`psh/executor/pipeline.py:176`). Because this happens after fork, parent memory is isolated, so it is probably safe. Still, it is conceptually awkward: a shared visitor object is being repointed rather than a child visitor or invocation context being passed down.

Recommended change:

- Add `visitor.with_context(child_context)` or construct a child visitor explicitly in the forked process.
- Longer term, make `visit(node, context)` explicit instead of storing execution context as mutable visitor state.

### Ugly 9: pipeline process-group setup is mostly parent-side and failures are swallowed

Pipeline leaders and single commands call `os.setpgid(0, 0)` in the child (`psh/executor/process_launcher.py:169`, `psh/executor/process_launcher.py:219`). Pipeline members wait for the sync pipe, but they do not call `os.setpgid(0, pgid)` themselves; the parent tries to assign the member to the process group and ignores `OSError` except for optional debug output (`psh/executor/process_launcher.py:189`, `psh/executor/process_launcher.py:291`).

The sync pipe reduces races, but if the parent-side `setpgid` genuinely fails, the pipeline member may remain in the shell's process group. That is a job-control correctness risk.

Recommended change:

- Have pipeline members attempt `os.setpgid(0, config.pgid)` in the child after synchronization when `config.pgid` is set.
- Treat parent-side `setpgid` failures as observable diagnostics or typed launch failures when they are not benign race outcomes.
- Add targeted tests or instrumentation for process groups in multi-stage foreground and background pipelines.

### Ugly 10: forked shell paths overlap but are not unified

`ProcessLauncher` deliberately does not use `run_child_shell()` because pipeline/external/subshell children need different setup (`psh/executor/process_launcher.py:151`). That distinction is valid. But subshell execution still constructs `Shell.for_subshell()` inside a launcher child (`psh/executor/subshell.py:91`), while process substitution uses `run_child_shell()` (`psh/executor/child_policy.py:132`, `psh/io_redirect/process_sub.py:69`).

Recommended change:

- Define named child-body types:
  - `ExecLeafChild`
  - `ShellBodyChild`
  - `SubstitutionChild`
- Let `ProcessLauncher` accept a child-body policy object instead of just `is_shell_process`.

This would preserve the necessary differences while making the taxonomy explicit.

### Ugly 11: control-flow executors repeat context and loop scaffolding

`execute_if`, `execute_while`, `execute_until`, `execute_for`, `execute_case`, and `execute_select` repeatedly apply redirections, save/restore `context.in_pipeline`, increment/decrement `loop_depth`, and handle `LoopBreak`/`LoopContinue` levels (`psh/executor/control_flow.py:29`).

Recommended change:

- Add helpers:
  - `compound_redirection_context(node, context)`
  - `loop_context(context)`
  - `handle_loop_control(exception, context)`
- Keep the shell semantics in the control-flow executor, but remove the repeated scaffolding.

## Suggested Refactor Sequence

1. Add `ExecutionResult`, `CommandResolution`, and `SimpleCommandPlan` dataclasses without changing behavior.
2. Extract redirection-mode selection from `_execute_with_strategy()` into a pure policy function with tests.
3. Split `_execute_command()` into plan, expand, apply assignments, dispatch, and cleanup phases.
4. Replace `shell._pending_array_inits` with formal invocation metadata for declaration builtins.
5. Move alias expansion out of runtime strategy dispatch, or preserve structured words while migrating it.
6. Make pipeline-member process-group setup two-sided and observable.
7. Extract common statement-list/top-level execution loop.
8. Later, split `strategies.py` into resolver and invoker layers.

## Bottom Line

The executor is architecturally serious and has improved in the right places. It is not yet elegant enough to call textbook quality because the most important path, simple-command execution, still coordinates too many semantic domains directly. The next quality jump should be to make command invocation a data flow through explicit plan/resolution/result objects, and to push redirection-mode and assignment-persistence policy out of ad hoc tuple/branch logic.
