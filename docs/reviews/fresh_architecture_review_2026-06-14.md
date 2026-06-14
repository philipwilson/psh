# Fresh Architecture Review

Date: 2026-06-14
Version inspected: v0.400.0
Scope: current `psh/` implementation, read directly. This review intentionally
does not use older review documents as evidence and does not rank or resolve the
R7 bash-fidelity bug queue.

## Executive Verdict

psh is now architecturally serious. The strongest parts are no longer just
"good for an educational shell"; several subsystems have explicit invariants,
named semantic phases, and testable seams:

- `Shell` is a lifecycle coordinator, not an execution engine
  (`psh/shell.py:39`).
- `Word.parts` is the authoritative command-word model, with derived string
  views rather than duplicated mutable argument state (`psh/ast_nodes/words.py:154`,
  `psh/ast_nodes/commands.py:18`).
- Expansion has named policies and a real intermediate representation
  (`WordExpansionPolicy`, `ExpandedSegment`) instead of flag soup
  (`psh/expansion/word_expander.py:49`, `psh/expansion/word_expander.py:121`).
- Redirection now has a shared planning/application layer for fd-level paths,
  while the Python-stream universe for in-process builtins is documented and
  frame-scoped (`psh/io_redirect/manager.py:1`, `psh/io_redirect/file_redirect.py:261`).
- Fork policy and child signal reset are centralized through `ProcessLauncher`
  and `child_policy` (`psh/executor/process_launcher.py:53`).

The project is not a clean textbook architecture yet. The remaining architectural
debt is concentrated in a few high-leverage seams:

1. Runtime alias expansion is still modeled as "join expanded argv, reparse as
   source", which crosses lexical and execution layers in the wrong direction.
2. Simple-command invocation still returns policy metadata as tuple side
   channels and does command resolution and invocation in the same strategy
   objects.
3. Control-flow execution repeats context/redirection scaffolding across many
   constructs.
4. `ShellState` remains a broad mutable state bag whose option names, stream
   override attributes, and execution flags are known by convention across
   subsystems.
5. The visitor/analysis stack still partly analyzes derived strings rather than
   the canonical `Word`/expansion AST model.
6. Type-checking coverage is wide but incomplete: 118 mypy file entries for 222
   source files, with whole important modules still outside the checked set.

Overall architecture grade: **A- for the core runtime path, B+ for the whole
repository**. The runtime has crossed into textbook territory in several
subsystems, but the repository as a whole still has educational/legacy surfaces
that are structurally below that bar.

## Current Shape

Approximate subsystem size from the live tree:

| Subsystem | Files | Lines | Architectural read |
| --- | ---: | ---: | --- |
| `parser/` | 38 | 10,314 | Large, but the production recursive-descent parser is decomposed; combinator backend remains a parallel educational surface. |
| `builtins/` | 35 | 8,344 | Broad feature surface; mixed quality by builtin; many modules still hand-own option parsing. |
| `expansion/` | 27 | 6,998 | Strong policy model and increasingly canonical Word pipeline. |
| `lexer/` | 28 | 5,904 | Modular recognizers and shared command-position helpers; still inherently context-heavy. |
| `executor/` | 15 | 5,247 | Good process/fork foundations; simple-command strategy layer remains dense. |
| `visitor/` | 12 | 3,901 | Useful tooling, but analysis model lags runtime AST discipline. |
| `interactive/` | 21 | 3,800 | Recently decomposed; line editor is a coordinator with well-named components. |
| `core/` | 11 | 2,446 | Scope/env invariants are strong; state container is broad. |
| `io_redirect/` | 5 | 1,397 | Strong conceptual model; remaining coupling mostly in builtin stream backend. |
| `scripting/` | 9 | 1,146 | Clear enough; source processor remains the main orchestration path. |
| `ast_nodes/` | 8 | 1,013 | One of the best-designed areas now. |

## Strong Architecture

### 1. Top-Level Lifecycle Is Explicit

`Shell.__init__` is organized as named phases: state creation, manager creation,
parent inheritance, shell-bound component creation, parser selection, traps, and
interactive setup (`psh/shell.py:49`). The important point is not just the
comments; each phase has a method and a narrow before/after contract.

This is good architecture because child-shell construction is hard in shells.
`Shell.for_subshell()` names the only construction path for isolated children
and documents exactly what is inherited (`psh/shell.py:72`). That gives
subshells, command substitution, process substitution, and env-style child
execution a shared mental model.

Remaining caveat: `Shell` also hosts cross-subsystem handoff APIs such as
`set_pending_array_inits()` and `pending_array_init()` (`psh/shell.py:189`).
Those APIs are explicit and documented, which is much better than ad hoc
attributes, but they show that `Shell` is still the integration bus for some
semantic data.

### 2. AST Words Are Finally Authoritative

`SimpleCommand.words` is the single source of truth for command arguments, and
`args` is derived (`psh/ast_nodes/commands.py:18`). `Word.quote_type` is also
derived from parts instead of stored redundantly (`psh/ast_nodes/words.py:180`).
This is a large architectural win: execution can reason about quote context,
expansion parts, array initializer metadata, and display/source text without
losing structure.

The model distinguishes:

- `source_text()` for debug/source rendering (`psh/ast_nodes/words.py:225`);
- `display_text()` for pre-expansion flattened text (`psh/ast_nodes/words.py:237`);
- `to_literal_string()` for quote removal with expansions left literal
  (`psh/ast_nodes/words.py:249`).

That is the right shape for a shell. The remaining problem is not the AST model;
it is that some non-runtime tooling and alias execution still consume derived
strings where they should consume structured words.

### 3. Expansion Has a Real Policy Table

`ExpansionManager` is now an orchestrator: it owns sub-expanders, recognizes
declaration builtins, picks a policy, and delegates to `WordExpander`
(`psh/expansion/manager.py:1`, `psh/expansion/manager.py:70`).

`WordExpansionPolicy` names the actual variation between contexts:
splitting, globbing, and assignment-value tilde expansion
(`psh/expansion/word_expander.py:49`). `ExpandedSegment` then carries quote,
split, and glob eligibility through the expansion pipeline
(`psh/expansion/word_expander.py:121`). This is close to textbook quality:
it turns shell folklore into explicit data.

The design also correctly keeps the scalar assignment-value walker separate
from the field-producing walker (`psh/expansion/word_expander.py:15`). That
separation is not over-abstraction; it preserves a real semantic distinction.

### 4. Redirection Has a Clear Two-Universe Model

`IOManager` explicitly documents the fd universe and Python stream universe
(`psh/io_redirect/manager.py:1`). That is the core problem in a Python shell:
external commands inherit descriptors, but in-process builtins write to Python
stream objects. The current design recognizes this and makes builtin
redirections frame-scoped (`BuiltinRedirectFrame`, `psh/io_redirect/manager.py:141`).

The recent fd-backend refactor improved the other half of the subsystem:
`FileRedirector.apply_fd_plan()` is now the shared fd-level application switch,
and `saved_fds_for_plan()` centralizes temporary fd save policy
(`psh/io_redirect/file_redirect.py:243`, `psh/io_redirect/file_redirect.py:261`).
Child redirection setup now delegates the actual fd operation and keeps only
child-specific error/exit behavior (`psh/io_redirect/manager.py:428`).

This is an example of the right compromise: shared classification and operation,
separate ownership/error behavior.

### 5. Process Launching and Child Signal Policy Are Real Abstractions

`ProcessLauncher` owns the fork, process-group setup, signal reset, optional IO
setup, execution callback, flush discipline, and `os._exit()` path
(`psh/executor/process_launcher.py:53`, `psh/executor/process_launcher.py:97`).
That is a strong centralization for a shell.

`ProcessConfig` makes process role, foreground/background state, process-group
membership, sync pipes, and shell-child status explicit
(`psh/executor/process_launcher.py:30`). The child setup path also names why it
is distinct from substitution-child helpers (`psh/executor/process_launcher.py:151`).

This is production-minded code. The weakness is not in the launcher itself; it
is in callers that still duplicate background job registration and child body
construction in strategies and subshell handling.

### 6. Interactive Editing Is Now Componentized

`LineEditor` presents itself as a coordinator over `KeyDecoder`, keybindings,
`EditBuffer`, history navigation/search, renderer, completion, and terminal
manager (`psh/interactive/line_editor.py:1`). The main read loop is still long,
but it is much less of a monolith than a classic terminal editor implementation.

The important architectural point: `KeyDecoder` owns reading, `LineRenderer`
owns ANSI repainting, and `EditBuffer` owns text/cursor state. That is the right
separation.

## Remaining Uglies

### Ugly 1: Alias Execution Crosses the Lexer/Executor Boundary Backwards

`AliasExecutionStrategy.execute()` builds a new command string from the alias
definition plus `' '.join(args)`, then tokenizes and parses it
(`psh/executor/strategies.py:345`, `psh/executor/strategies.py:372`). At that
point `args` are already expanded command arguments, not original lexical
tokens.

Architecturally, this is the largest remaining impurity in the command path:
runtime data is reconstructed as source code and handed back to the lexer/parser.
That makes alias behavior depend on lossy rendering and can turn data back into
syntax.

Recommended direction:

1. Move alias expansion to a lexical/parser boundary, before normal word
   expansion.
2. Represent alias expansion as token or word-stream transformation, not as
   joined argv text.
3. Keep a temporary runtime alias path only as a compatibility shim, with tests
   around whitespace, quotes, redirections, semicolons, and shell metacharacters
   in post-alias arguments.

### Ugly 2: Command Resolution and Invocation Are Still Entangled

`CommandExecutor._execute_with_strategy()` chooses a strategy, computes
redirection mode, invokes the strategy, and returns `(exit_code, is_special)`
(`psh/executor/command.py:465`). The boolean is then used by `_run_command()` to
decide whether prefix assignments persist (`psh/executor/command.py:335`).

This works, but policy metadata is being smuggled alongside a process status.
The strategy classes also mix concerns:

- builtin strategies execute builtins and background-fork builtins
  (`psh/executor/strategies.py:189`);
- function strategy creates a function executor and also forks background
  functions (`psh/executor/strategies.py:259`);
- external strategy resolves hashes, manages terminal title/control, launches,
  registers jobs, waits, and removes jobs (`psh/executor/strategies.py:402`);
- alias strategy reparses source (`psh/executor/strategies.py:334`).

Recommended direction:

1. Add `CommandResolution` with `kind`, `target`, and
   `prefix_assignments_persist`.
2. Add `ExecutionResult` with `status` plus optional job/process metadata.
3. Split "resolve command name" from "invoke target".
4. Keep job registration in a process/job runner rather than strategy classes.

This would make assignment persistence and command kind inspectable data, not
tuple convention.

### Ugly 3: Simple-Command Execution Is Improved but Still a Semantic Hub

`CommandExecutor._execute_command()` is now shorter than older versions and has
clear comments, but it still coordinates DEBUG traps, array assignments, raw
assignment extraction, command-substitution status, pure assignments, command
word slicing, backslash bypass, expansion, `$_`, prefix assignments, xtrace,
`exec`, array-init handoff, strategy dispatch, restoration, and exception
mapping (`psh/executor/command.py:134`, `psh/executor/command.py:215`).

The current code is readable, but the architecture still asks one class to know
too many shell phase-ordering rules.

Recommended direction:

1. Introduce `SimpleCommandPlan` for parse-time/extraction facts:
   raw assignments, command words, redirects, background, bypass flags, array
   initializer metadata.
2. Introduce `ExpandedCommandInvocation` for expansion results:
   command name, argv, prefix assignment outcome, pending declaration metadata.
3. Let `_execute_command()` become a visible pipeline of plan -> expand ->
   apply prefix -> resolve -> invoke -> cleanup.

The goal is not fewer lines by itself; it is to make the POSIX phase order
testable as data.

### Ugly 4: Control-Flow Executors Repeat Context and Redirection Scaffolding

`ControlFlowExecutor` repeatedly applies node redirections, saves/restores
`context.in_pipeline`, increments/decrements `loop_depth`, suppresses errexit
in conditions, and translates `LoopBreak`/`LoopContinue` levels
(`psh/executor/control_flow.py:53`, `psh/executor/control_flow.py:94`,
`psh/executor/control_flow.py:141`, `psh/executor/control_flow.py:172`,
`psh/executor/control_flow.py:288`).

The repeated code is not currently catastrophic, but it is the kind of
duplication that causes future semantic drift. For example, C-style loops do not
follow exactly the same `in_pipeline` save/restore shape as while/for/case.

Recommended direction:

- Add `compound_execution_context(node, context)` for redirection plus
  pipeline-context restoration.
- Add `loop_execution_context(context)` for loop depth.
- Add one helper for break/continue level decrement.
- Add focused tests that all compound commands apply redirects for their whole
  body and restore pipeline context afterward.

### Ugly 5: Pipeline Children Mutate Shared Visitor State

Pipeline child closures set `visitor.context = child_context` before visiting
their command (`psh/executor/pipeline.py:176`). Because this happens after
`fork()`, parent memory is isolated, but the object model is still awkward:
execution context is mutable state on a visitor object rather than an explicit
argument through the visit call.

Recommended direction:

1. Add `ExecutorVisitor.with_context(context)` or construct a child visitor in
   each forked child.
2. Longer term, move toward `visit(node, context)` style execution for runtime
   visitors, even if analysis visitors keep the current simpler interface.

This would reduce reliance on mutable visitor ambient state and clarify forked
execution boundaries.

### Ugly 6: `ShellState` Is Still a Broad Convention Container

`ShellState` holds environment, scope manager, command hash, options, history,
editing state, function/source stacks, `PIPESTATUS`, pid identity, errexit
eligibility, command-substitution status, forked-child flag, terminal
capabilities, trap handlers, and stream properties (`psh/core/state.py:12`).

Many invariants are documented well, especially the "read `os.environ` once"
policy (`psh/core/state.py:12`) and export observer (`psh/core/state.py:359`).
But the structure is still a mutable dictionary and attribute bag at important
seams:

- options are string-keyed (`psh/core/state.py:75`);
- stream overrides are dynamic `_custom_*` attributes (`psh/core/state.py:260`);
- `in_forked_child` is read across builtins/executor/io paths
  (`psh/core/state.py:183`);
- shell mode flags are recomputed and overwritten across construction phases.

Recommended direction:

- Split `ShellState` internally into typed sub-objects:
  `OptionState`, `StreamState`, `ExecutionStatus`, `TerminalState`,
  `HistoryState`.
- Keep the public facade stable while moving invariants into those sub-objects.
- Replace dynamic stream override attributes with a small `StreamBindings`
  object that can snapshot/restore custom streams explicitly.

### Ugly 7: Builtin Redirection Still Reaches Into FileRedirector Internals

The fd-level backend is much cleaner after `RedirectPlan`, but builtin stream
redirection still calls `FileRedirector` private primitives such as
`_redirect_input_from_file`, `_redirect_readwrite`, `_redirect_heredoc`,
`_redirect_herestring`, `_check_noclobber`, and `_noclobber_blocks`
(`psh/io_redirect/manager.py:314`, `psh/io_redirect/manager.py:357`,
`psh/io_redirect/manager.py:370`).

This is understandable because the builtin backend has genuinely different
stream behavior. But these methods are no longer purely private implementation
details; they are shared redirect primitives.

Recommended direction:

- Extract stable redirect operations into `redirect_ops.py` or make the
  intended primitive methods public and narrowly typed.
- Keep `FileRedirector` as an fd backend, not as an accidental primitive
  namespace for the stream backend.
- Preserve the current `RedirectPlan` layer; it is the correct foundation.

### Ugly 8: The Visitor Tooling Stack Lags the Runtime AST Model

`EnhancedValidatorVisitor` still does important checks by walking `node.args`
strings and regexing variable syntax (`psh/visitor/enhanced_validator_visitor.py:186`,
`psh/visitor/enhanced_validator_visitor.py:367`). Some checks use `Word`
structure, but the visitor often falls back to derived strings.

That is now architecturally behind the runtime. Since `Word` parts are
authoritative, validators and linters should inspect `ExpansionPart`,
`LiteralPart`, `ParameterExpansion`, and quote flags directly.

Recommended direction:

- Build reusable `WordAnalysis` helpers over the AST parts.
- Route validator/linter/security visitors through those helpers.
- Remove regex scans over rendered strings except as compatibility fallbacks for
  legacy/manual ASTs.

### Ugly 9: The Combinator Parser Is a Large Parallel Surface

The production parser is recursive descent. The combinator parser remains under
`psh/parser/combinators/` and contributes a large share of parser size. Some
production and tooling code still keeps compatibility branches for combinator
or manual AST outputs, such as case pattern fallback handling in
`ControlFlowExecutor.execute_case()` (`psh/executor/control_flow.py:329`).

An educational alternate parser is reasonable for this project, but it has an
architectural cost: it keeps fallback shapes alive and broadens the invariant
surface.

Recommended direction:

- Make the combinator parser's status explicit in code and docs:
  production-supported, experimental, or educational-only.
- If educational-only, isolate it from runtime invariants and reduce production
  fallback paths.
- If production-supported, require the same canonical AST invariants as the
  recursive-descent parser and test both through the same AST-contract suite.

### Ugly 10: Type Checking Is Broad but Not Yet an Architectural Guardrail

The current `pyproject.toml` config lists 118 mypy entries. The source tree has
222 Python files. Coverage has grown substantially, and the recently added
lexer/parser/expansion scopes are valuable, but major runtime files remain
outside or only partially checked:

- `psh/executor/command.py`, `strategies.py`, `pipeline.py`, `control_flow.py`;
- `psh/io_redirect/manager.py`, `file_redirect.py`, `process_sub.py`;
- much of `builtins/`;
- many visitor modules;
- `check_untyped_defs = false`.

Recommended direction:

1. Add `io_redirect/file_redirect.py`, `manager.py`, and `process_sub.py` next.
   They are small enough and now have clearer types.
2. Add executor files around the new planned dataclasses (`CommandResolution`,
   `ExecutionResult`, `SimpleCommandPlan`) so the refactor itself expands the
   type boundary.
3. Turn on `check_untyped_defs` only for new small modules first, not globally.

## What Is Textbook Quality Now?

These areas are good examples for future work:

- `ast_nodes/words.py`: derived quote/string views and structured parts.
- `expansion/word_expander.py`: named policies plus explicit segment IR.
- `io_redirect/manager.py` module model: fd vs stream universe and frame-scoped
  builtin redirections.
- `io_redirect/planner.py` plus fd backend application: shared resolve/plan
  before backend-specific ownership.
- `executor/child_policy.py` and `process_launcher.py`: named fork/signal
  invariants.
- `interactive/key_decoder.py` / `line_editor.py` decomposition: clear ownership
  of input decoding, buffer mutation, rendering, and coordination.

## What Is Not Textbook Yet?

These are not "bad code" in the sense of being careless; they are places where
too much shell semantics still relies on convention or hidden ordering:

- Runtime alias reparse in `AliasExecutionStrategy`.
- Tuple return `(exit_code, is_special)` for assignment persistence.
- Strategy classes as resolver + invoker + job runner.
- Repeated control-flow context scaffolding.
- Mutable visitor context in forked pipeline children.
- Broad `ShellState` option/stream/status bag.
- Builtin stream backend calling fd backend private helpers.
- Visitor analysis over derived strings.
- Unclear production status of the combinator parser.

## Recommended Architecture Roadmap

This roadmap deliberately avoids the R7 bash-bug list and targets structure.

### A1. Command Invocation Data Flow

Add three small dataclasses first, with minimal behavior change:

- `SimpleCommandPlan`
- `CommandResolution`
- `ExecutionResult`

Then refactor `CommandExecutor` so phase order becomes visible data:

```text
SimpleCommand AST
  -> SimpleCommandPlan
  -> ExpandedCommandInvocation
  -> CommandResolution
  -> InvocationResult
  -> cleanup / status update
```

Expected payoff: clearer assignment persistence, easier mypy adoption, and less
risk when adjusting dispatch semantics.

### A2. Resolver/Invoker Split

After A1, split strategy responsibilities:

- `CommandResolver`: special builtin, function, builtin, alias, external target.
- `CommandInvoker`: invoke a resolved target.
- `ProcessJobRunner`: foreground/background job registration and wait policy.

Alias expansion should be handled separately at the lexical/parser boundary, not
as a normal invocation strategy.

### A3. Control-Flow Context Helpers

Extract redirection/context/loop scaffolding in `ControlFlowExecutor`. This is a
low-risk cleanup with high drift-prevention value.

Suggested helpers:

- `compound_redirection_context(node, context)`
- `pipeline_context_disabled(context)`
- `loop_depth(context)`
- `translate_loop_control(exc, context)`

### A4. Redirect Primitive Boundary

Keep `RedirectPlanner` and `FileRedirector.apply_fd_plan()` as the foundation.
Then expose the primitive operations that the builtin stream backend legitimately
shares. This removes misleading underscore coupling without flattening the
necessary stream/fd distinction.

### A5. State Decomposition

Do not rewrite `ShellState` in one pass. First create internal typed wrappers:

- `OptionState`
- `StreamState`
- `ExecutionStatus`
- `TerminalState`

Move code behind compatibility properties gradually. The first useful target is
stream state, because fd/stream behavior is subtle and currently spans
`ShellState`, `IOManager`, builtins, and tests.

### A6. Visitor Analysis Over Word AST

Add a `visitor/word_analysis.py` helper layer and convert enhanced validator,
linter, and security checks from rendered-string regexes to structured Word
inspection. This aligns tooling with the runtime model and reduces false
positives.

### A7. Decide the Combinator Parser Contract

Pick one:

- **Educational-only:** isolate from runtime guarantees and delete production
  fallback accommodations over time.
- **Supported backend:** enforce the same AST canonical-invariant suite as the
  recursive-descent parser.

Ambiguity is the architectural problem; either decision can be clean.

### A8. Continue Type-Coverage Growth as Refactors Land

Use mypy as a ratchet, not a vanity metric. Each new architecture module should
enter the mypy list immediately. The best next scopes are:

1. `psh/io_redirect/file_redirect.py`, `manager.py`, `process_sub.py`;
2. new executor dataclasses and any extracted resolver/invoker modules;
3. `psh/executor/command.py` once the data-flow split reduces type complexity;
4. visitor word-analysis helpers.

## Bottom Line

psh's architecture is no longer dominated by accidental complexity. The best
parts now encode shell semantics as named data and explicit ownership models.
That is the right bar.

The next architectural gains should not be more broad subsystem splitting.
They should be targeted seam work:

1. make simple-command execution a typed data flow;
2. move alias handling out of runtime argv reparse;
3. extract repeated compound-command context scaffolding;
4. formalize state and redirect primitive boundaries;
5. bring static analysis and mypy up to the same canonical AST model the
   runtime now uses.

Those changes would move the repository from "several textbook subsystems" to a
more uniformly textbook architecture.
