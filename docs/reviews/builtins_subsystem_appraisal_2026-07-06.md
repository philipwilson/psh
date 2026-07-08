# Builtins Subsystem Appraisal — 2026-07-06

## Scope

This is a fresh appraisal of the builtins subsystem, graded for:

- shell correctness and status semantics;
- POSIX and Bash compatibility;
- process, variable, directory, and job-state isolation;
- textbook-quality architecture and maintainability;
- efficiency and resource safety; and
- test quality and production readiness.

The review covered:

- all modules under `psh/builtins/`;
- builtin registration and invocation;
- special-builtin integration with the executor;
- shell-variable and environment operations;
- declarations, attributes, arrays, and readonly enforcement;
- input, output, formatting, and descriptor behavior;
- navigation and directory stacks;
- command resolution and command introspection;
- job control and signals;
- functions, evaluation, sourcing, and control transfer;
- shell options, positional parameters, and history;
- system and resource-limit builtins;
- focused, integration, Bash, and POSIX tests;
- static analysis and focused coverage; and
- representative differential runtime probes against Bash 5.2 and zsh.

## Executive Judgment

The subsystem has broad functionality, strong focused testing, and several good
architectural foundations. It remains below the production and textbook bar
because process isolation, readonly enforcement, input consumption, command
resolution, and state mutation are not consistently authoritative.

The most serious defect is `env`: its supposed child shell runs in the same OS
process. Consequently:

- `env exit 7` terminates PSH;
- `env exec ...` replaces PSH's process image;
- `env cd` changes the parent process's real cwd; and
- `env umask` changes the parent shell's umask.

Several other failures are systemic rather than isolated option quirks:

- mutable arrays can be changed before readonly checks run;
- `mapfile -n` drains the complete remaining input;
- declaration-family builtins implement overlapping semantics differently;
- command resolution is independently reimplemented by `command`, `type`,
  `hash`, and the executor;
- `read` decodes UTF-8 one byte at a time;
- directory-stack mutations are not transactional; and
- job builtins parse some arguments that they then ignore.

Overall grade: **C+**.

## Grades

| Dimension | Grade | Assessment |
| --- | --- | --- |
| Functional breadth | B+ | 63 primary builtins plus `readarray`; most common shell functionality exists. |
| Correctness on tested paths | B+ | The focused and conformance suites are green. |
| Full Bash/POSIX correctness | C | Numerous ordinary edge cases remain incorrect. |
| Process/state isolation | D+ | `env` is a release-blocking violation. |
| Architecture | B- | Good registry and state boundaries, but duplicated semantic services undermine them. |
| Efficiency | C | `read` performs byte-at-a-time syscalls; `mapfile -n` reads the entire stream. |
| Maintainability | C+ | Large branch-heavy implementations and repeated option/declaration logic. |
| Testing | B+ | Exceptional volume, but important invariants are absent from the test matrix. |
| Textbook quality | C+ | Strong foundations, but mutation and isolation contracts are not enforced centrally. |

## Validation

### Focused builtin validation

```text
python -m pytest tests/unit/builtins tests/integration/builtins -q

1232 passed in 20.87s
```

### Bash and POSIX conformance

```text
python -m pytest tests/conformance/bash tests/conformance/posix -q

1506 passed, 1 skipped, 10 xfailed in 193.63s
```

The ten expected failures represent features deliberately recorded in the
absent-feature ledger. The green result does not cover the additional
differential failures reproduced in this review.

### Focused coverage

```text
python -m pytest \
  tests/unit/builtins \
  tests/integration/builtins \
  -q \
  --cov=psh.builtins \
  --cov-report=term-missing:skip-covered

TOTAL: 73%
```

Notable module coverage:

| Module | Coverage |
| --- | ---: |
| `job_control.py` | 34% |
| `mapfile_builtin.py` | 61% |
| `read_builtin.py` | 63% |
| `directory_stack.py` | 64% |
| `environment.py` | 88% |
| `env_command.py` | 94% |

`env_command.py` demonstrates why line coverage is not a correctness proof: it
has high focused coverage while its fundamental isolation model is unsafe.

### Static analysis

```text
ruff check psh/builtins
```

was clean. The repository's normal mypy configuration was also clean.

A strict run:

```text
python -m mypy --disallow-untyped-defs psh/builtins
```

found 52 errors in 15 files.

Optional complexity analysis found 40 `C901` violations. Selected hotspots:

| Function | Complexity |
| --- | ---: |
| `TestBuiltin.evaluate_unary` | 37 |
| `TypeBuiltin.execute` | 32 |
| `CdBuiltin.execute` | 28 |
| `PrintBuiltin._parse_options` | 28 |
| `LocalBuiltin.execute_in_context` | 27 |
| `ExportBuiltin.execute_in_context` | 25 |
| `TestBuiltin._evaluate_binary` | 22 |
| `WaitBuiltin._wait_for_specific` | 20 |
| `MapfileBuiltin.execute` | 20 |

Some complexity is inherent in operator dispatch, especially in `test`, but
many other hotspots correspond directly to duplicated policy and reproduced
correctness defects.

## What Is Already Strong

### Collision-safe registration

`psh/builtins/registry.py` rejects duplicate primary names and aliases at
registration time. That turns import-order shadowing into an immediate
programming error.

The registry also returns copies of its public name map and exposes unique
instances separately from aliases.

### Explicit singleton statelessness

Builtin instances are process-wide singletons, and `Builtin` documents the
requirement that they retain no invocation or shell state. A representative
cross-registry test verifies `vars(instance) == {}` after exercising nearly
every builtin.

This is a useful and unusually explicit lifecycle contract.

### Explicit invocation context

`BuiltinContext` replaced the former mutable pending-array-initializer side
channel. Structured array initializers now flow from the parser through the
executor as an explicit invocation parameter.

That is a sound design. It should be generalized for future typed invocation
metadata and propagated through every delegated builtin path.

### Shared output helpers

The base class provides:

- normal stdout writes;
- line writes;
- prefixed diagnostics;
- unprefixed diagnostic lines; and
- forked-child fd-level output.

This has removed a substantial amount of repeated and inconsistent stream
handling from individual builtins.

### Central shell-option registry

The option registry is an effective source of truth for:

- default values;
- short-option mappings;
- `$-` rendering;
- `set` versus `shopt` categorization; and
- internal/debug options.

This is the model the builtin registry and declaration subsystem should
emulate.

### Pure formatting engines

`printf` delegates its format language to a pure reusable formatter. Echo
escape processing is likewise shared.

Keeping complicated text transformation independent of shell state makes it
far easier to test exhaustively.

### Serious `test` implementation

The `test`/`[` implementation uses the POSIX argument-count algorithm before
falling back to Bash-style multi-argument expressions. It centralizes file
comparison helpers and handles many non-obvious argument-count cases.

Although the dispatch tables are large, the underlying semantic approach is
substantially better than treating `test` as a conventional infix expression
grammar.

### Detailed shell behavior work

The implementation demonstrates substantial Bash-informed work around:

- exec signal disposition and failure status;
- source positional parameters and `return`;
- trap rendering and pseudo-signals;
- declaration attributes and array formatting;
- command hashing;
- `read` IFS behavior;
- stopped-job exit handling; and
- job-status retention for repeated `wait`.

### Strong compatibility-test investment

The test suite contains more than a thousand focused builtin cases, a broad
Bash/POSIX conformance tier, an absent-feature ledger, differential tests, and
subprocess coverage of descriptors and process state.

The weakness is not lack of test volume. It is that several foundational
invariants are not represented in the test matrix.

## Findings

### 1. P0: `env` does not isolate process state

`psh/builtins/env_command.py` creates `Shell.for_subshell(...)` but executes the
new shell in the current OS process.

A new Python object isolates Python-owned state only. It does not isolate:

- current working directory;
- umask;
- resource limits;
- signal dispositions;
- process-level file descriptors; or
- process replacement and termination.

#### Reproduced behavior

| Probe | Bash 5.2 | PSH |
| --- | --- | --- |
| `env exit 7; echo after` | `env` cannot find external `exit`; shell continues | PSH exits 7 |
| `env exec /bin/echo inner; echo after` | shell continues | PSH is replaced; `after` never runs |
| `env cd /tmp; pwd` | parent cwd unchanged | real cwd becomes `/tmp`, cached `$PWD` remains old |
| `env umask 077; umask` | original mask | `0077` |

`env ulimit` can similarly change limits inherited by the surviving shell, and
may make an irreversible hard-limit reduction.

The implementation also temporarily replaces process fds 0, 1, and 2 to align
them with the nested shell's stream objects. If one replacement fails after
earlier descriptors have changed, the method can exit before it has returned
the backup list required for restoration. Process-global fd replacement is
also inherently unsafe in the presence of concurrent threads.

#### Required correction

Implement standard `env` command mode as external execution:

1. parse `env` options and `NAME=VALUE` entries;
2. construct the exact child environment;
3. retain command arguments as an argv list;
4. pass the argv and environment directly to the normal external launcher;
5. search according to the required `env`/`execvp` policy; and
6. return 126/127 through the shared external-execution diagnostics.

Do not quote the argv into source text and reparse it.

If invoking shell builtins through `env` is intentionally retained as a PSH
extension, it must run in a real forked process. Standard `env` should not
resolve shell builtins at all.

### 2. P1: Mutable arrays bypass readonly enforcement

Readonly checking occurs when a variable is committed through the scope
manager. Several builtins mutate the existing array object before that commit.

For example:

```sh
readonly -a a=(x y)
unset 'a[0]'
```

Bash reports failure and preserves `a=(x y)`. PSH returns success and leaves
`a=(y)`.

The same defect appears in:

- indexed and associative element removal by `unset`;
- `declare a+=(...)`, which passes an existing array as the `into` object;
- the corresponding `local` array append path; and
- `mapfile -O`, which overlays the existing array before `set_variable`
  rejects the readonly assignment.

Representative results:

```text
readonly -a a=(x); declare a+=(y)

Bash: failure, unchanged
PSH:  failure, but value becomes (x y)
```

```text
readonly -a a=(old); mapfile -t -O 1 a <<< new

Bash: failure, a[1] remains absent
PSH:  failure, but a[1] becomes "new"
```

This violates a fundamental state invariant: a failed operation must not
change a readonly value.

#### Required correction

Fix this at the variable-store boundary:

- do not expose mutable stored values for unrestricted modification;
- use immutable values or copy-on-write arrays;
- provide authoritative `unset_element`, `append_array`, `replace_array`, and
  `overlay_array` operations;
- check attributes before mutation;
- commit the completed replacement atomically; and
- ensure nameref resolution and target-scope selection occur before the
  attribute check.

Add a matrix covering every mutation mechanism against readonly indexed
arrays, associative arrays, and nameref targets.

### 3. P1: Declaration semantics are duplicated and have drifted

`declare`, `local`, `readonly`, and `export` share most concepts but do not use
one declaration engine.

#### Integer append through export

```sh
declare -i n=2
export n+=3
```

Bash produces `5`; PSH produces `23`.

`ExportBuiltin` performs textual concatenation and only later applies existing
attributes. It does not use the canonical append-assignment semantics.

#### Incompatible array conversion

```sh
a=(x y)
declare -A a
```

Bash reports failure, returns 1, and preserves the indexed array. PSH reports
an error, returns 0, and converts it to an associative array.

The implementation comment explicitly describes the incorrect conversion as
Bash behavior.

#### Global append through a local shadow

```sh
x=G
f() {
    local x=L
    declare -g x+=A
}
f
```

Bash produces global `GA`; PSH produces global `LA`. The append reads through
the current local scope even though `-g` targets the global scope.

#### Nameref filters

`declare -pn` should list namerefs only. PSH also prints ordinary variables
because nameref is omitted from the declaration filter table.

#### Required correction

Parse declaration-family commands into a typed model such as:

```python
@dataclass(frozen=True)
class DeclarationRequest:
    target_scope: TargetScope
    assignments: tuple[DeclarationAssignment, ...]
    add_attributes: VarAttributes
    remove_attributes: VarAttributes
    array_kind: ArrayKind | None
    print_mode: PrintMode | None
```

One declaration service should:

1. resolve the target scope;
2. resolve namerefs according to operation policy;
3. read the existing value from that same target scope;
4. validate incompatible attributes and conversions;
5. calculate the complete new value without mutation; and
6. commit it once.

`local`, `export`, and `readonly` should adapt target and diagnostic policy, not
reimplement declaration mechanics.

### 4. P1: `mapfile` consumes more input than requested

`MapfileBuiltin` reads all remaining input before applying `-s` and `-n`.

```sh
exec 3<<<$'a\nb\n'
mapfile -t -n1 -u3 a
read -r -u3 rest
```

Bash leaves `b` for the following `read`. PSH has already consumed it, so the
second read reaches EOF.

Other reproduced defects:

- `mapfile -u 99` silently succeeds with an empty array;
- negative `-n` succeeds rather than reporting an invalid line count;
- negative `-O` reaches a later bad-subscript error instead of being rejected
  as an invalid origin;
- `mapfile -O` can mutate a readonly array before reporting failure; and
- memory use is proportional to the complete remaining stream even for
  `mapfile -n 1`.

#### Required correction

Implement a streaming record reader that:

- validates descriptors and numeric options before consuming input;
- consumes only the skipped records plus the requested count;
- stops without draining subsequent input;
- reports read errors distinctly from EOF;
- incrementally decodes UTF-8;
- handles delimiter boundaries across chunks; and
- builds a replacement array before one atomic commit.

Be careful with buffering: reading beyond the final requested record into a
private userspace buffer can hide those bytes from a subsequent external
command. A shell-wide fd input service or conservative record-boundary reads
are required.

### 5. P1: Command resolution has multiple inconsistent implementations

Resolution is independently implemented by:

- the command executor;
- `command`;
- `type`;
- `hash`; and
- interactive completion.

This has produced observable policy drift.

#### `command -p` bypasses builtins

```sh
command -p cd /tmp
```

Bash still invokes the `cd` builtin and changes the shell's cwd. PSH forces
external execution, so an external `cd` may run but cannot change the shell.

Similarly, `command -p shopt ...` returns 127 in PSH instead of invoking the
builtin.

The `-p` option changes the search path used for external utilities. It does
not remove builtins from the normal resolution order.

#### Hash inconsistency

```sh
hash -p /tmp/custom-path customcmd
command -v customcmd
```

Bash prints the hashed path. PSH returns failure, even though `type -p
customcmd` finds the same hash entry.

#### Empty PATH components

An empty PATH component denotes the current directory. `TypeBuiltin` skips
empty components, so `type -P` and `command -v` cannot find an executable in
the current directory through `PATH=:/usr/bin`.

#### Required correction

Create one `CommandResolver` that returns typed candidates:

```text
Alias
Keyword
Function
Builtin
HashedExternal
PathExternal
NotFound
```

Resolver parameters should control:

- alias participation;
- function bypass;
- builtin participation;
- hash-table use;
- default versus shell PATH;
- first versus all matches; and
- executable-path rendering.

`command`, `type`, `hash`, the executor, and completion should render or act
on this shared result.

Do not implement `command -p` by temporarily mutating `shell.env["PATH"]`.

### 6. P1: `set` mishandles valid positional inputs and emits non-reusable output

`SetBuiltin.execute` indexes `arg[0]` without handling an empty operand:

```sh
set ""
```

Bash sets one empty positional parameter. PSH reports:

```text
psh: set: string index out of range
```

and leaves the positional parameters unchanged.

A lone:

```sh
set -
```

should apply Bash's option behavior without installing `-` as `$1`. PSH sets
the positional parameter list to `["-"]`.

Variable listing is also not reusable:

```sh
x='a b'
set
```

Bash emits:

```text
x='a b'
```

PSH emits:

```text
x=a b
```

Plain `declare` has the same quoting problem despite the module's claim that
declaration rendering is shared. `hash -l` likewise emits unquoted paths:

```text
builtin hash -p /tmp/a b x
```

instead of a reusable quoted command.

#### Required correction

- Handle empty operands before inspecting their first character.
- Model lone `-`, lone `+`, `--`, and option clusters explicitly.
- Use one shell-word serializer for every reusable-output promise.
- Add round-trip tests using `eval "$(set)"`, plain `declare`, `hash -l`,
  aliases, empty strings, newlines, control characters, and shell
  metacharacters.

### 7. P1: `read` is not Unicode-safe and bypasses injected streams

`ReadBuiltin._read_chars` performs:

```python
os.read(fd, 1).decode("utf-8", errors="replace")
```

This decodes each byte independently.

```sh
read -r -N1 x <<< 'é'
```

Bash assigns `é`; PSH assigns the Unicode replacement character.

The implementation also:

- performs one syscall per byte;
- uses wall-clock `time.time()` for timeout budgets;
- writes prompts through raw `sys.stderr`;
- writes terminal echo and silent-input newlines through raw `sys.stdout`;
- checks and reads global `sys.stdin` instead of consistently using
  `shell.stdin`; and
- converts several read errors into EOF inside the low-level loop.

These violate the subsystem's own injected-I/O convention and can bypass
redirection or capture.

#### Required correction

Introduce a shared descriptor reader with:

- an incremental byte decoder;
- monotonic absolute deadlines;
- injected input and display streams;
- explicit `DATA`, `DELIMITER`, `LIMIT`, `EOF`, `TIMEOUT`, and `ERROR`
  outcomes;
- terminal-mode ownership; and
- bounded buffering.

`read` and `mapfile` should share this service.

### 8. P1: `getopts` cursor state is insufficiently identified

`GetoptsBuiltin` stores a character position and the associated `OPTIND`, but
not the current argument source or current option word.

```sh
OPTIND=1
getopts ab x -ab
getopts ab x -b
```

Bash returns `b` on the second call. PSH indexes beyond the new word and
reports:

```text
psh: getopts: string index out of range
```

#### Required correction

Bind getopts continuation state to:

- the current positional/explicit argument source;
- the current `OPTIND`;
- the current option word; and
- the within-word cursor.

Reset when the source word changes, and validate the cursor before indexing.
Prefer a small typed `GetoptsCursor` on shell state over two dynamically added
private attributes.

### 9. P1: Directory-stack updates are not transactional

`pushd`, `popd`, and rotation paths mutate the stack before attempting
`chdir`.

For example, a missing directory can be inserted with `pushd -n`, after which
plain `pushd` swaps it to the top and fails to change directory. PSH leaves the
invalid entry at `stack[0]` while the real cwd remains unchanged.

This breaks the core invariant:

```text
directory_stack[0] == logical current working directory
```

`cd` has a related ordering problem:

1. it calls `chdir`;
2. directly updates `shell.env`;
3. updates `PWD` and `OLDPWD` through the scope manager; and
4. may then encounter a readonly-variable error.

With readonly `PWD` or `OLDPWD`, PSH returns failure after the real cwd has
changed and leaves cached state inconsistent. Bash has its own specific
diagnostic behavior but does not report the directory change itself as a
failed `cd`.

#### Required correction

Centralize directory changes in a service that owns:

- logical and physical resolution;
- CDPATH lookup;
- cwd transition;
- PWD/OLDPWD policy;
- directory-stack mutation;
- display policy; and
- failure repair.

Calculate stack changes without mutating, perform the required cwd transition,
and commit a consistent state. Where the OS cwd changes but a secondary cache
update fails, repair caches from `getcwd` rather than returning with
contradictory state.

Assert the stack/cwd invariant after every navigation operation.

### 10. P1: Job builtins omit operands and cleanup guarantees

`JobsBuiltin` parses jobspec operands and then ignores them:

```sh
sleep .3 &
jobs %999
```

Bash reports no such job and returns 1. PSH lists every job and returns 0.

Additional issues:

- `wait -p var pid` parses `-p` but assigns the variable only when `-n` is
  also present;
- `disown -a` and `disown -r` fail when the job table is empty, while Bash
  succeeds;
- `bg` handles only one jobspec;
- `fg` terminal reclamation is not protected by `finally`;
- failed terminal transfer leaves foreground bookkeeping partially updated;
  and
- `kill %job` expands a job to tracked member PIDs instead of representing the
  process-group operation directly.

#### Required correction

Move the following into `JobManager` transactions:

- jobspec parsing and ambiguity reporting;
- operand selection;
- current/previous marker updates;
- state transition;
- process-group signalling;
- terminal transfer;
- wait and stop handling;
- restoration; and
- completed-job cleanup.

The `fg` builtin should use a `try/finally` guard that always attempts terminal
reclamation and restores foreground bookkeeping.

### 11. P1: Argument and abort policy is inconsistent

#### Shift

```sh
set -- a b c
shift 1 2
```

Bash reports too many arguments. PSH ignores the extra operand, shifts, and
returns success.

#### Exit validation order

```sh
exit abc 7
```

Bash processes the invalid first argument and exits 2. PSH checks the operand
count first, reports only "too many arguments", returns 1, and may continue.

#### Command-string abort behavior

For:

```sh
exit 7 8; echo survived
```

Bash's `-c` processing abandons the remainder of that input line after the
special-builtin error. PSH runs the following `echo`.

The implementation already has several distinct policies for scripts,
interactive input, sourced files, functions, traps, and command strings.
Individual builtins currently encode portions of those policies with
`sys.exit`, return codes, or control-flow exceptions.

#### Required correction

Use typed builtin outcomes or exceptions for:

- normal status;
- function return;
- loop break/continue;
- shell exit;
- fatal special-builtin failure; and
- discard-current-input-unit.

One executor policy should interpret those outcomes according to interactive,
script, `-c`, function, source, and trap context.

### 12. P2: Output failures are not uniformly reflected in status

The zsh-compatible `print` builtin reports a bad descriptor but still returns
zero:

```sh
print -u99 hi
```

zsh returns 1. PSH prints:

```text
print: -u: 99: Bad file descriptor
```

and returns 0 because `_write` catches the exception without returning an
error result.

The base forked-child writer also calls `os.write` once and ignores its return
count. A partial write can silently truncate large output.

#### Required correction

- Provide one write-all operation that loops until every byte is written.
- Return or raise a typed output failure.
- Require every output-producing builtin to propagate that failure.
- Keep diagnostic failure handling separate so a closed stderr does not mask
  the original output error.

### 13. P2: Registry metadata is too weak

The registry knows only:

- primary name;
- aliases; and
- singleton instance.

Other classifications are maintained separately:

- POSIX special builtins in the executor;
- Bash builtin names in visitor constants;
- help information on the instances;
- absent features in the conformance ledger;
- experimental status only in prose; and
- documentation lists in README and subsystem notes.

A production registry should describe:

- standard versus extension status;
- POSIX special versus regular;
- state effects;
- aliases;
- accepted contexts;
- synopsis and help;
- experimental visibility;
- parser or executor dependencies; and
- implementation availability.

The executor's special-builtin set, help output, analysis visitors, and
documentation should derive from this metadata where their semantics overlap.

Developer commands such as parser selection, AST visualization, and debug
control should be classified separately from the user-facing shell language.
In particular, the normal production registry exposes a builtin that can
select the educational-only combinator parser.

### 14. P2: Feature and documentation claims need qualification

The absent-feature ledger correctly records:

- `bind`;
- `compgen`;
- `complete`;
- `caller`;
- `enable`;
- `suspend`;
- `jobs -x`;
- `wait -f`;
- `coproc`; and
- `lastpipe`.

Other production-shell features such as `fc`, `compopt`, and a programmable
completion model remain absent or outside the ledger.

If the README retains its "POSIX-compliant shell" wording, every applicable
required surface needs either implementation and conformance evidence or an
explicit qualification. `fc` is particularly relevant because it is
inherently tied to shell history.

The README also says:

```text
All 61 registered builtins
```

while the registry currently contains 63 primary names.

### 15. P2: Expected errors and internal defects are not cleanly separated

`execute_builtin_guarded` converts most ordinary exceptions into an internal
defect status. Some expected domain failures, such as readonly declaration
errors, are therefore allowed to escape from builtin code and rely on the
defect reporter to produce the desired observable message.

Conversely, actual programming errors such as `set ""` are converted into a
clean shell diagnostic and status 1 by default, making them easy to miss.

#### Required correction

Define a small exception/result taxonomy:

- usage error;
- operational builtin failure;
- assignment/declaration failure;
- output failure;
- shell control transfer; and
- unexpected internal defect.

Expected errors should be rendered centrally without being classified as
defects. Unexpected exceptions should retain tracebacks in tests and
development mode and be impossible to mistake for ordinary command failure.

### 16. P2: Invocation context is not preserved through every delegation

The executor invokes builtins through `execute_in_context`, but some nested and
background paths call `execute` directly.

Examples include:

- `command` delegating to another builtin;
- `builtin` delegating to another builtin; and
- background builtin execution.

The currently visible loss is mostly limited because Bash rejects unquoted
array-initialization syntax after `command`/`builtin`. Architecturally, though,
the explicit context contract is incomplete: any future invocation metadata
will silently disappear on these paths.

Use one `BuiltinInvocation` object and one guarded invocation function for
direct, delegated, pipeline, and background execution.

## Why the Green Tests Did Not Expose These Problems

The suite is broad but often tests local output rather than cross-cutting
invariants.

### Env tests check only Python-owned state

The env tests verify that:

```sh
env TEMP=1 export INNER=42
```

does not leak `INNER` into the parent variable store.

They do not test:

- cwd;
- umask;
- resource limits;
- signals;
- file descriptors;
- `exit`;
- `exec`; or
- whether standard `env` incorrectly resolves shell builtins.

This gives false confidence in the phrase "in-process child Shell."

### Mapfile tests check the result, not the remaining input

`mapfile -n 2` is tested by inspecting the resulting array. No test follows it
with another read from the same fd.

The implementation can therefore drain the complete stream and still pass.

### Readonly tests do not enumerate mutation paths

Readonly scalar assignment is covered well, but no systematic matrix applies:

- scalar assignment;
- element assignment;
- element unset;
- array append;
- `mapfile -O`;
- arithmetic assignment;
- declaration conversion; and
- nameref mutation

to both indexed and associative arrays.

### Command tests do not treat resolution as a shared contract

`command`, `type`, and `hash` have strong individual tests, but few tests seed
one resolution mechanism and query it through all the others.

### Failure tests do not always validate post-failure state

Directory and declaration tests often assert status and diagnostics without
asserting that every affected state component remained unchanged or was
repaired consistently.

### High test count masks modest focused coverage

The focused selection reaches only 73% of builtin statements despite 1,232
tests. The least-covered modules include precisely the stateful paths where
post-failure invariants matter most.

## Architectural Direction

The registry and base class can remain. The main improvement is to move
semantics that are currently repeated across builtins into authoritative
services:

```text
BuiltinRegistry
├── BuiltinSpec
│   ├── name / aliases
│   ├── standard / extension / experimental
│   ├── special / regular
│   ├── state effects
│   └── help metadata
├── BuiltinInvoker
│   ├── typed invocation context
│   ├── output/error conversion
│   └── control-transfer policy
├── CommandResolver
│   ├── alias / keyword / function
│   ├── builtin
│   ├── hash
│   └── PATH
├── VariableMutationService
│   ├── declaration
│   ├── attribute changes
│   ├── scalar/array append
│   └── atomic element mutation
├── ShellInputService
│   ├── incremental decoding
│   ├── records and character counts
│   ├── deadlines
│   └── fd errors
├── DirectoryService
│   ├── logical/physical resolution
│   ├── PWD/OLDPWD
│   └── stack transactions
└── JobManager
    ├── jobspec resolution
    ├── state transitions
    ├── process-group signalling
    └── terminal transactions
```

Builtins should then become thin adapters:

1. parse command-specific options;
2. build a typed request;
3. call the authoritative service;
4. render its typed result; and
5. return its status.

## Prioritized Remediation Plan

### Phase 0: Restore process and state safety

1. Replace in-process `env` command execution with direct external argv
   execution.
2. Prevent raw mutation of stored array values.
3. Make every readonly failure leave state unchanged.
4. Add subprocess regressions for cwd, umask, limits, `exit`, `exec`, fds, and
   signals.

These are release blockers.

### Phase 1: Establish semantic authorities

1. Build the shared command resolver.
2. Build the declaration/mutation service.
3. Route `command`, `type`, `hash`, execution, and completion through the
   resolver.
4. Route `declare`, `local`, `export`, `readonly`, `unset`, `read -a`, and
   `mapfile` through the mutation service.

### Phase 2: Correct input handling

1. Introduce incremental decoding and monotonic deadlines.
2. Share the fd reader between `read` and `mapfile`.
3. Make `mapfile -n/-s` preserve unread input.
4. Eliminate raw `sys.stdin`/`stdout`/`stderr` accesses from builtins.
5. Add PTY and pipe tests for UTF-8, timeout, silent input, prompts,
   descriptors, and remaining input.

### Phase 3: Make state transitions transactional

1. Centralize directory changes and enforce the stack/cwd invariant.
2. Centralize jobspec selection and terminal transitions.
3. Add `try/finally` restoration around foreground jobs.
4. Repair `wait -p`, jobspec filtering, multi-job `bg`, and empty `disown`.

### Phase 4: Normalize command contracts

1. Repair `set`, `getopts`, `shift`, and `exit` edge cases.
2. Introduce typed option results instead of untyped dictionaries.
3. Introduce typed shell control outcomes.
4. Use one shell serializer for reusable output.
5. Make output failures propagate uniformly.

### Phase 5: Improve maintainability and feature accounting

1. Add `BuiltinSpec` metadata.
2. Separate production, extension, developer, and experimental builtins.
3. Derive overlapping help/visitor/executor documentation from the registry.
4. Complete strict typing.
5. Reduce complexity by removing duplicated policy, not by cosmetically
   splitting switch statements.
6. Expand the absent-feature ledger and qualify compatibility claims.

## Production Acceptance Gates

The subsystem should not be called production-ready until automated tests
demonstrate all of the following:

- `env` cannot alter parent cwd, umask, limits, signals, fds, or process image;
- standard `env` command mode resolves external programs rather than shell
  builtins;
- every readonly mutation attempt leaves state byte-for-byte unchanged;
- `mapfile -n/-s` leaves unread records available to subsequent builtins and
  external commands;
- split UTF-8 input decodes correctly for `read` and `mapfile`;
- `command`, `type`, `hash`, execution, and completion consume the same
  resolution result;
- `command -p` retains builtin selection and changes only external PATH search;
- `set`, declaration, alias, trap, and hash reusable output round-trip through
  the parser;
- empty positional parameters and explicit getopts argument lists cannot
  trigger internal exceptions;
- declaration append reads from the scope it will modify;
- incompatible array conversions fail without mutation;
- directory-stack and cached-cwd invariants survive every failed `chdir`;
- jobspec operands are honored and foreground restoration is exception-safe;
- expected user errors never travel through the internal-defect path;
- output-producing builtins report partial/failed writes;
- state-changing builtins have differential tests across global, local,
  nameref, readonly, exported, array, pipeline, background, source, function,
  and trap contexts; and
- feature and compliance claims are mechanically tied to conformance evidence
  or an explicit difference ledger.

## Final Assessment

The builtins subsystem is not a collection of toy implementations. It contains
substantial feature work, a disciplined registry, explicit statelessness,
strong focused tests, and many carefully reproduced Bash details.

Its remaining weaknesses sit below individual command syntax. The subsystem
does not yet have one authoritative answer for:

- what constitutes process isolation;
- how a variable is mutated atomically;
- how commands are resolved;
- how bytes become shell input;
- how directory and job transitions commit or roll back; and
- how builtin control effects cross executor contexts.

The correct next step is not another sequence of isolated builtin patches.
First repair `env` and readonly mutation, then establish shared services for
resolution, declaration, input, directories, and jobs. Once those contracts
are authoritative, most of the current complexity and many compatibility
defects disappear together.
