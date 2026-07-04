# Deep Codebase Appraisal — PSH v0.617.0 (2026-07-04)

Overall grade: **6.8/10**. The architecture is substantially better than the
current reliability and assurance story. The codebase has strong subsystem
boundaries and unusually thorough design documentation, but it is not
release-ready while the canonical gate fails and hangs.

Scope reviewed: 241 production modules / 62,264 lines, 488 test modules /
94,491 lines, and 12,415 collected tests. The worktree was clean when the
appraisal began and remained clean through the read-only review.

## Executive findings

### 1. Blocker: `Shell` does not own its resources explicitly

Every `Shell` eagerly constructs two signal self-pipes—four file descriptors—
even for non-interactive shells
([signal_manager.py](../../psh/interactive/signal_manager.py#L18),
[signal_utils.py](../../psh/utils/signal_utils.py#L156)). Cleanup exists only
on the notifier or when interactive signal handlers are restored; there is no
`Shell.close()` or context-manager contract.

The test fixture manually closes private notifier fields
([conftest.py](../../tests/conftest.py#L60)), but tests constructing `Shell`
directly bypass this. Garbage collection is delayed by shell/component
reference cycles.

Observed result from the canonical gate:

- 10,570 passed, 867 skipped, and 10 xfailed.
- 5 failed and 1 errored with `OSError: [Errno 24] Too many open files`.
- The subsequent serial phase hung on an orphaned background process.

Improvement:

- Allocate signal pipes lazily when signal handling is actually enabled.
- Add idempotent `Shell.close()`, `SignalManager.close()`, and
  `Shell.__enter__/__exit__`.
- Close in-process child shells, notably the `env` child.
- Make notifier construction exception-safe.
- Add a stress test that repeatedly constructs and closes thousands of shells
  while checking FD counts.

### 2. High: pipelines break when standard descriptors begin closed

The child duplicates pipe endpoints onto stdin/stdout and then
indiscriminately closes every pipe descriptor
([pipeline.py](../../psh/executor/pipeline.py#L372)). If `os.pipe()` returned
descriptor 0 or 1 because that standard descriptor was closed, the active
descriptor is immediately closed.

Reproduction:

| Command condition | Bash | PSH |
|---|---:|---:|
| stdin closed before `printf x \| cat` | `x`, statuses `0 0` | `cat: stdin: Bad file descriptor`, statuses `0 1` |

Additionally, parent cleanup puts both closes inside one `try`, so failure
closing the first endpoint skips the second
([pipeline.py](../../psh/executor/pipeline.py#L51)).

Improvement: implement collision-safe FD remapping, exclude active standard
targets from the close set, and close endpoints independently. Add tests with
descriptors 0, 1, and 2 closed before pipeline construction.

### 3. High: two correctness defects in `read`

The non-TTY timeout path intentionally bounds only the first byte and then
reads indefinitely
([read_builtin.py](../../psh/builtins/read_builtin.py#L706)).

A delayed pipe gives:

- Bash: `read -t 0.1` returns 142 with partial value `x`.
- PSH: waits for the later newline and returns 0.

Character mode also decodes each individual byte as UTF-8
([read_builtin.py](../../psh/builtins/read_builtin.py#L554)). Consequently:

- Bash reading `éz` with two `read -n 1` calls produces `é`, then `z`.
- PSH produces two replacement characters.

Improvement: use one monotonic absolute deadline throughout the complete read
loop and an incremental locale-aware decoder that counts decoded characters
rather than bytes.

### 4. High: child-shell array isolation is shallow

`Variable.copy()` copies the mutable array object by reference and even notes
that deep copying is required
([variables.py](../../psh/core/variables.py#L107)). `ShellState.adopt()` relies
on that method for inherited scopes
([state.py](../../psh/core/state.py#L230)).

The `env` builtin promises an isolated in-process child
([env_command.py](../../psh/builtins/env_command.py#L54)), but:

```sh
a=(x)
f(){ a[0]=y; }
env f
echo "${a[0]}"
```

prints `y`; the parent should retain `x` under PSH's stated isolation contract.

Improvement: give mutable variable values an explicit `clone()` protocol and
test identity and mutation isolation for global, local, indexed, associative,
and nameref variables.

### 5. High: the test gate can both mask failures and hang

`run_tests.py` captures all subprocess output without a timeout
([run_tests.py](../../run_tests.py#L25)). A failed disown test left `sleep 300`
alive because cleanup is not in `finally` and targets process names rather
than exact PIDs
([test_disown_builtin.py](../../tests/unit/builtins/test_disown_builtin.py#L393)).
The orphan retained the output pipe, so `subprocess.run(...).communicate()`
never reached EOF.

The runner also removes `INTERNALERROR` output and can translate
pytest-xdist exit code 3 into success merely because an earlier summary
contains “passed” ([run_tests.py](../../run_tests.py#L45)). That can conceal
worker loss or incomplete execution.

Improvement:

- Never translate an internal pytest error into success.
- Add runner timeouts and process-group termination.
- Track exact spawned PIDs independently of the shell job table.
- Put process cleanup in fixtures or `finally`.
- Stream output or capture it in a temporary file rather than an inherited
  pipe.

### 6. High: conformance reporting is not trustworthy

The custom conformance runner hardcodes selected test classes and directly
invokes methods, bypassing pytest discovery, fixtures, parametrization, and
strict-xfail behavior
([run_conformance_tests.py](../../tests/conformance/run_conformance_tests.py#L33)).
Unexpected xpass is informational, and `main()` exits successfully even when
results contain PSH defects or test errors
([run_conformance_tests.py](../../tests/conformance/run_conformance_tests.py#L400)).

Its latest report, dated 12 June, claims 100% POSIX and 99% Bash compatibility
from only 364 comparison results. These percentages should not be presented as
release metrics.

Replace this runner with pytest discovery plus a JSON/JUnit reporting hook,
and fail on any unexpected difference, test error, or XPASS.

### 7. Medium: analysis modes do not use the selected parser

The visitor path directly calls the default parser and does not pass
`shell.active_parser`
([visitor_modes.py](../../psh/scripting/visitor_modes.py#L16)).

With `--parser combinator`, a `select` construct rejected by normal execution
is accepted by `--validate`, proving that validation analyzes a different
grammar.

The enhanced validator also does not register `SelectLoop` variables in its
own variable tracker, producing a false undefined-variable warning
([enhanced_validator_visitor.py](../../psh/visitor/enhanced_validator_visitor.py#L257),
[validator_visitor.py](../../psh/visitor/validator_visitor.py#L382)).

Improvement: introduce one shell parsing service used by execution,
validation, formatting, metrics, and linting. It should own parser selection,
shell options, aliases, heredocs, and source locations.

### 8. Medium: identifier policy is duplicated and inconsistent

A correct POSIX-aware identifier policy exists in
[unicode_support.py](../../psh/lexer/unicode_support.py#L7), but assignment,
builtin, arithmetic, expansion, and lexer paths independently use
`isalpha()` and `isalnum()`.

Thus, after `set -o posix`, PSH accepts `é=1`; Bash/POSIX does not. Some
subsequent builtins then disagree about whether the same variable name is
valid.

Improvement: centralize all identifier validation and normalization behind one
mode-aware API and remove string-level reclassification after the AST has
already identified an assignment.

### 9. Medium: interactive layout assumes one code point equals one column

Prompt and buffer layout use `len()` and raw code-point positions
([line_layout.py](../../psh/interactive/line_layout.py#L34)). This is wrong for
CJK characters, combining marks, emoji, and grapheme clusters, causing cursor
and wrapping corruption.

Use a centralized `wcwidth`/grapheme-aware display model with prefix-width
calculations and PTY tests.

## Subsystem scorecard

| Subsystem | Grade | Assessment |
|---|---:|---|
| Shell/scripting | 7/10 | Clear construction phases; lacks lifecycle ownership and unified parsing |
| Core/state | 7/10 | Strong centralized model; mutable copying semantics are unsafe |
| Lexer | 8/10 | Well decomposed scanners and strong edge-case reasoning; identifier policy drifts |
| Production parser | 8.5/10 | Modular and well guarded; historical root-shape compatibility adds complexity |
| Combinator parser | 5.5/10 | Useful educational implementation, correctly documented as outside the production bar |
| Expansion | 7.5/10 | Word AST and named policies are excellent; matcher and identifier paths remain complex |
| Executor/job control | 6.5/10 | Good centralized process/signal policy; low-FD pipeline bug is fundamental |
| I/O redirection | 8/10 | Transactional nested frames are among the strongest parts of the design |
| Builtins | 6.5/10 | Broad coverage and stateless registry; `read`, `env`, and hand-written option parsing need work |
| Interactive | 6/10 | Clean component split; lifecycle and terminal-width correctness are weak |
| Visitors/tooling | 6/10 | Good visitor coverage; parsing integration and dataflow accuracy are insufficient |
| Tests/CI/docs | 5.5/10 | Exceptional volume, but the release gate and reported metrics are currently unreliable |

## Textbook-quality improvements

The strongest architectural choices should be retained:

- Structured `Word` AST as the expansion source of truth.
- Named expansion policies.
- Centralized fork and child-signal policy.
- Transactional redirection frames.
- Explicit production/educational parser boundary.
- Subsystem documentation and strong Bash-based behavioral probes.

The main simplifications should be:

1. Replace variable AST roots (`StatementList` versus `TopLevel`) and the
   `__module__` rewriting mechanism with one stable `Program` root and explicit
   node registration
   ([ast_nodes/__init__.py](../../psh/ast_nodes/__init__.py#L96)).

2. Replace the process-wide recursion limit of 40,000 with explicit shell
   recursion budgets and progressively iterative evaluators
   ([shell.py](../../psh/shell.py#L48)).

3. Make builtin registration reject duplicate primary names or aliases instead
   of silently overwriting them
   ([registry.py](../../psh/builtins/registry.py#L15)).

4. Move versioned reappraisal history and long probe narratives from production
   comments into ADRs. Preserve local comments for invariants and non-obvious
   reasoning.

5. Split the remaining 700–940-line modules by responsibility, particularly
   formatter, function support, command execution, word expansion, scope, line
   editor, `read`, and validator.

## Assurance and performance

Configured Ruff and mypy both pass, but the configured quality bar is
permissive:

- Ruff checks only a small subset of failures/import/whitespace rules
  ([pyproject.toml](../../pyproject.toml#L57)). A broader diagnostic produced
  2,115 findings, mostly annotation modernization but also complexity and
  exception-handling issues.
- Mypy checks function bodies but permits missing/incomplete annotations; a
  strict diagnostic found 602 untyped-definition errors.
- Performance coverage is one parsing/tokenization file: 8 passed, 1 xfailed.
  There are no scaling tests for expansion, execution, substitutions, process
  creation, or resource lifetimes.
- Extglob conversion can emit catastrophic-backtracking regexes such as
  `(?:a|aa)*b` ([extglob.py](../../psh/expansion/extglob.py#L158)). A memoized
  matcher or explicit resource budget is preferable.
- Per-PR CI is deliberately disabled
  ([tests.yml](../../.github/workflows/tests.yml#L3)). Given that the local gate
  currently fails, this leaves no dependable merge barrier.

Documentation also needs regeneration:
[README.md](../../README.md#L7) contains several conflicting test counts,
while the differences document still lists arrays, `[[ ]]`, process
substitution, extglob, `declare`, `local`, `mapfile`, and `shopt` as
unimplemented
([differences/README.md](../../tests/conformance/differences/README.md#L20)).

## Recommended order of work

1. Fix `Shell` lifecycle, process cleanup, and the test runner; restore a
   trustworthy green gate.
2. Fix pipeline descriptor collisions, `read`, and variable cloning.
3. Unify parsing and identifier policy; repair visitor scope tracking.
4. Replace the custom conformance runner and enable PR CI.
5. Add Unicode terminal layout and runtime/resource performance tests.
6. Tighten linting and typing incrementally, then simplify AST and large
   modules.

## Validation performed

- `python run_tests.py --parallel`
  - Parallel phase: 10,570 passed, 867 skipped, 10 xfailed, 5 failed, 1 error.
  - Failures traced to signal-notifier FD exhaustion.
  - The following serial phase hung on an orphaned `sleep 300` retaining the
    captured output pipe and was interrupted after diagnosis.
- `ruff check psh tests`: passed.
- `mypy`: passed across 241 production modules.
- Broader Ruff diagnostic (`E,F,I,W,B,UP,SIM,C4,PIE,RUF`): 2,115 findings.
- Strict mypy missing-annotation diagnostic: 602 findings.
- `python -m pytest tests/performance/ -q`: 8 passed, 1 xfailed.
- Direct Bash comparison probes reproduced the pipeline, timeout, multibyte
  input, POSIX identifier, parser-selection, validator, and array-isolation
  findings above.
