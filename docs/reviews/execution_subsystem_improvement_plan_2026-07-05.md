# Execution Subsystem Appraisal and Improvement Plan

Date: 2026-07-05  
Version reviewed: PSH 0.646.0

## Summary

Overall assessment:

- Correctness: **B**
- Architecture: **B**
- Worst-case efficiency: **C+**

The executor has an unusually strong process-control foundation. Fork masking,
child signal policy, process groups, terminal ownership, prefix-assignment
ordering, errexit, traps, functions, and control-flow semantics are all much
more thoroughly implemented and tested than in a typical educational shell.

It is not yet textbook-quality because assignments, redirection ownership, and
process placement are decided independently. That separation produces concrete
correctness defects:

- A quoted empty command is mistaken for no command.
- Backslash quoting incorrectly bypasses functions.
- Background builtins and functions evaluate redirections twice.
- Several compound commands install their redirections after expanding their
  headers.
- Pipeline descriptor remapping is unsafe when descriptors 0 or 1 begin
  closed.
- Long pipelines retain O(N) descriptors and fail under ordinary descriptor
  limits.
- Array assignments bypass the normal assignment and status model.
- POSIX special-builtin behavior is only partially mode-aware.
- Mixed completed/stopped pipelines are classified as running.

The most useful architectural improvement is to compile every command into one
typed execution plan before performing effects. That plan should decide:

- Command resolution.
- Current-process, forked-child, or exec placement.
- Assignment mode and rollback.
- Which process owns redirection setup.
- Process-group and foreground/background behavior.
- Status and resource collection.

## Validation performed

The following checks were run during this appraisal:

```text
python -m pytest tests/unit/executor -q
  183 passed

python -m pytest tests/integration -q
  2,463 passed, 48 skipped

python -m pytest tests/system/interactive/test_pty_smoke.py -q
  78 passed, 2 expected failures

ruff check psh/executor
  clean

python -m mypy psh/executor
  clean under the configured rules
```

A stricter mypy audit using `--disallow-untyped-defs` found 53 missing
annotation errors.

The executor implementation contains approximately 6,811 lines.

The large passing baseline is meaningful evidence. However, the suites do not
currently cover several distinctions exercised by this appraisal:

- Zero fields versus one empty command-name field.
- Alias quoting versus function lookup.
- Redirection side effects on background commands.
- Compound-header substitution under compound redirection.
- Pipelines with initially closed standard descriptors.
- Pipelines large enough to approach `RLIMIT_NOFILE`.
- Array assignment command-substitution status.
- Mixed completed/stopped job state.

## Strengths to preserve

### 1. Central child signal policy

`child_policy.py` gives the fork paths a single signal discipline:

- Termination signals are blocked across `fork()`.
- The parent's signal mask is restored even if `fork()` fails.
- Children reset inherited handlers before unblocking.
- Shell-process and leaf-process `SIGTTOU` behavior is distinguished.
- Shared child runners map shell control-flow exceptions to statuses.
- Python streams are flushed before `os._exit()`.

This is strong systems programming. Any process-launch redesign should keep
these invariants centralized.

### 2. Explicit process roles and process groups

`ProcessRole` makes standalone commands, pipeline leaders, and pipeline members
explicit. Parent-side `setpgid()` and synchronization pipes eliminate several
common process-group races.

Terminal transfer is capability-based through `terminal_pgid_if_owned()`
rather than test-runner detection. That is the correct abstraction.

### 3. Visible redirection modes

`RedirectionMode` distinguishes:

- In-process builtin stream redirection.
- Deferred external-child redirection.
- File-descriptor-level windows for functions and forked contexts.

Although one dimension is missing—background process placement—having this
policy named and centralized is a good foundation.

### 4. Documented assignment ordering

`command_assignments.py` clearly states and implements the major ordering
contract:

1. Command words expand before prefix assignments apply.
2. Assignment values expand left to right.
3. Temporary assignments restore after the command.
4. Pure assignment status can come from command substitution.
5. Readonly failures differ between pure and prefix assignments.

The scalar path is substantially cleaner than it was historically.

### 5. Function temporary scopes

Function-prefix assignments use a temporary exported scope instead of ad hoc
save-and-restore writes. This correctly models interactions with ordinary
function assignments, `local`, `declare -g`, and export state.

### 6. Strong control-flow scaffolding

`ControlFlowExecutor` centralizes:

- Compound-command redirection windows.
- Pipeline-context neutralization.
- Loop-depth tracking.
- Multi-level break/continue propagation.
- Errexit suppression for conditions.

The detailed loop status behavior and trap handling are strongly
characterized.

### 7. Typed command-resolution results

`CommandResolution` and `ExecutionResult` replace an earlier positional tuple
and make prefix-assignment persistence a named policy. The recommended
`ExecutionPlan` should extend this direction rather than replace it with loose
flags.

### 8. Broad process and shell-semantics coverage

The subsystem has strong tests for:

- Foreground and background jobs.
- `SIGINT`, `SIGTSTP`, and abnormal termination.
- Pipeline status and `pipefail`.
- Process substitution cleanup.
- Function scope and recursion.
- Errexit and fatal expansion behavior.
- DEBUG, ERR, RETURN, and EXIT traps.
- Redirect restoration.
- Interactive terminal transfer.

## Priority findings

### 1. A quoted empty command is incorrectly treated as no command

`CommandExecutor._run_command()` currently checks:

```python
if not expanded_args or not expanded_args[0]:
```

Those conditions have different shell meanings.

An unquoted empty expansion can vanish completely:

```sh
empty=
$empty
```

That produces zero fields and therefore no command.

A quoted empty word produces one field whose text is empty:

```sh
''
""
"$empty"
```

That is an attempted invocation of a command with an empty name. Bash performs
normal command lookup, reports “command not found,” and returns 127.

Confirmed:

```sh
''; printf 'rc=%s\n' "$?"
```

Observed behavior:

| Shell | Result |
|---|---|
| Bash | Diagnostic for an empty command name; status 127 |
| PSH | No diagnostic; status 0 |

The defect is more serious when prefix assignments are present:

```sh
unset X
X=v ''
printf 'rc=%s X=<%s>\n' "$?" "${X-unset}"
```

Observed behavior:

| Shell | Status | `X` afterwards |
|---|---:|---|
| Bash | 127 | unset |
| PSH | 0 | `v` |

PSH misclassifies the command invocation as a pure assignment and persists the
prefix.

#### Repair

Only `not expanded_args` means the command words produced zero fields.

If `expanded_args == ['']`, proceed through normal command resolution. The
external fallback will fail lookup and produce status 127.

Add separate tests for:

```text
unquoted unset/empty command word -> zero fields, status 0
quoted empty literal             -> one empty field, status 127
quoted empty variable            -> one empty field, status 127
prefix assignment + empty word   -> temporary assignment, status 127
```

### 2. Backslash quoting incorrectly bypasses function lookup

`_strip_backslash_bypass()` treats a leading backslash as bypassing both alias
and function resolution.

That is not Bash semantics. Quoting the command word prevents alias expansion,
but after quote removal the resulting name still participates in function
lookup.

Confirmed:

```sh
f() { echo FUNC; }
\f
```

Observed behavior:

| Shell | Result |
|---|---|
| Bash | Calls `f`, printing `FUNC` |
| PSH | Attempts an external `f`, status 127 |

The same defect affects functions shadowing builtins:

```sh
echo() { printf 'FUNCTION\n'; }
\echo hi
```

Bash invokes the function; PSH invokes the builtin.

It can also alter state:

```sh
export() { echo FUNCTION; }
\export X=y
```

Bash calls the function and does not export `X`; PSH invokes the builtin and
sets `X`.

#### Repair

- Alias eligibility should be decided during the lexical alias-expansion
  stage.
- Quote removal should produce the command name without changing function
  lookup.
- Remove function bypass from the backslash path.
- Reserve function bypass for the `command` and `builtin` builtins.
- Consider removing executor-level alias-bypass state entirely now that aliases
  are a pre-parser token transformation.

### 3. Background builtins and functions evaluate redirections twice

The redirection-mode decision does not include whether the command is
backgrounded.

For a background builtin:

1. `_execute_builtin_with_redirections()` installs the redirection in the
   parent.
2. `BuiltinExecutionStrategy` forks.
3. The child calls `setup_child_redirections()` for the same redirect.

For a background function, the outer file-descriptor window installs the
redirect in the parent and the child function path installs it again.

Confirmed:

```sh
echo hi > "$(echo MARK >&2; echo out)" &
wait
cat out
```

Observed behavior:

| Shell | `MARK` count |
|---|---:|
| Bash | 1 |
| PSH | 2 |

The same duplication occurs with `:`, functions, and other background
non-external commands.

This is not merely duplicate computation. It can duplicate:

- Command substitutions.
- Process substitutions.
- Variable mutations inside redirect expansion.
- File opens and truncation.
- FIFO or device interactions.
- Diagnostics and exit-status changes.

#### Repair

Any background command must defer redirection setup to the child that executes
the command.

Add an explicit placement/redirection mode such as:

```python
RedirectionOwner.CURRENT_PROCESS_WINDOW
RedirectionOwner.FORKED_CHILD
RedirectionOwner.EXEC_REPLACEMENT
RedirectionOwner.PERMANENT_CURRENT_PROCESS
```

The execution planner should select one owner. Strategies must not independently
decide to install the same redirects again.

### 4. Compound-command redirections are installed too late

Redirections attached to a compound command apply to the complete construct,
including header expansion and evaluation.

The current code gets this right for `if`, `while`, and `until`, but not for:

- `for` item expansion.
- `select` item expansion.
- `case` subject expansion.
- C-style `for` initialization.

Those operations happen before `_compound_redirections()` is entered.

#### `for` reproduction

```sh
printf 'item\n' > input
for x in $(cat); do
    printf '<%s>\n' "$x"
done < input
```

Observed behavior:

| Shell | Output |
|---|---|
| Bash | `<item>` |
| PSH | No loop iterations |

The command substitution in Bash reads from `input`. PSH expands the item list
before installing the redirect, so `cat` reads the original stdin.

#### `case` reproduction

```sh
printf 'item\n' > input
case "$(cat)" in
    item) echo yes ;;
    *) echo no ;;
esac < input
```

Bash prints `yes`; PSH prints `no`.

#### C-style `for`

The initializer is likewise evaluated before the loop redirect is installed.
A command substitution in the arithmetic initializer therefore sees the wrong
stdin.

#### Repair

Make the redirection context the outermost execution scope for every compound
construct:

```text
install compound redirects
  -> DEBUG trap for construct/header
  -> expand/evaluate header
  -> execute conditions/body
restore redirects
```

Use one helper that receives a body callback so a construct cannot accidentally
perform header work outside the redirect scope.

### 5. Pipeline descriptor remapping is unsafe

`PipelineExecutor._setup_pipeline_redirections()`:

1. Uses `dup2()` to map pipe endpoints to descriptors 0 and 1.
2. Closes every stored pipe descriptor unconditionally.

This fails when a pipe endpoint already has a destination descriptor number.

#### Closed stdin

```sh
exec 0<&-
printf x | cat
printf 'rc=%s pipe=%s\n' "$?" "${PIPESTATUS[*]}" >&2
```

Observed behavior:

| Shell | Output | `PIPESTATUS` |
|---|---|---|
| Bash | `x` | `0 0` |
| PSH | `cat: stdin: Bad file descriptor` | `0 1` |

If the pipe read end is descriptor 0, `dup2(0, 0)` is a no-op and the later
close loop closes stdin.

#### Closed stdout

When descriptor 1 begins closed, one pipe endpoint can become descriptor 1.
The upstream pipeline command then loses its pipe output descriptor during the
close loop and fails unnecessarily.

#### Repair

Implement one shared descriptor-remapping utility:

```text
input mappings: source fd -> destination fd
protected set: final destination fds
owned set: temporary/internal fds
```

It should:

- Promote internal descriptors above 2.
- Resolve remapping cycles safely.
- Preserve sources that are also destinations until no longer needed.
- Never close a final destination.
- Set close-on-exec deliberately.
- Close each owned descriptor independently.
- Be shared by pipelines, command substitution, process substitution, and
  redirection.

Test every combination in which descriptors 0, 1, and 2 begin open or closed.

### 6. Pipelines pre-open every pipe and exhaust descriptor limits

For an N-command pipeline, `PipelineExecutor` creates all N-1 pipes before
forking the first child.

The parent therefore retains approximately:

```text
2 * (N - 1) pipeline descriptors
+ synchronization descriptors
+ shell/runtime descriptors
```

Under the current soft `RLIMIT_NOFILE` of 256:

| Pipeline length | Bash | PSH |
|---:|---|---|
| 100 commands | succeeds | succeeds |
| 130 commands | succeeds | fails with `EMFILE` |

PSH reports:

```text
psh: -c:1: unexpected error: [Errno 24] Too many open files
```

This is both an efficiency defect and an observable correctness limit.

#### Repair

Construct pipelines incrementally:

1. Keep the previous command's read end.
2. Create one pipe for the next command.
3. Fork the current command.
4. Close descriptors the parent no longer needs.
5. Advance to the next command.

The parent then retains O(1) pipeline descriptors instead of O(N).

Each child should inherit only the endpoints it requires. This also reduces
the close-loop work in every child from O(N) to O(1).

### 7. Array assignments bypass the normal assignment status model

Array assignments are executed in an early `CommandExecutor` preamble before:

- `last_cmdsub_status` is cleared.
- The command is fully classified as pure assignment versus invocation.
- The scalar assignment transaction is selected.

That separate path creates several correctness failures.

#### Command-substitution status is lost

```sh
a[0]=$(false)
echo "$?"
```

| Shell | Status |
|---|---:|
| Bash | 1 |
| PSH | 0 |

The same occurs for whole-array initialization:

```sh
a=($(sh -c 'exit 7'))
echo "$?"
```

Bash reports 7; PSH reports 0.

#### Background assignment status is discarded

`_run_background_assignment()` invokes the assignment operation but then
unconditionally returns 0.

```sh
x=$(false) &
p=$!
wait "$p"
echo "$?"
```

Bash prints 1; PSH prints 0.

Similarly:

```sh
a[-1]=x &
p=$!
wait "$p"
echo "$?"
```

PSH prints the subscript diagnostic but records a successful background job.

#### A later success overwrites an earlier failure

```sh
unset a b
a[-1]=x b[0]=y
```

Bash aborts at the first invalid subscript. PSH:

- Prints the first error.
- Continues.
- Assigns `b[0]=y`.
- Returns the later status 0.

#### Prefix-position array syntax mutates the parent

```sh
unset a
a[0]=x echo RAN
declare -p a
```

Bash diagnoses `a[0]` as an invalid command-prefix assignment identifier,
runs `echo`, and does not create `a`.

PSH creates and retains the array before running the command.

#### Repair

Unify all assignment forms under one structured model:

```python
ScalarAssignment
IndexedElementAssignment
AssociativeElementAssignment
ArrayInitialization
```

Every assignment must also have a syntactic role:

```python
PURE_ASSIGNMENT
COMMAND_PREFIX
DECLARATION_ARGUMENT
```

The executor should then apply one shared policy for:

- Left-to-right expansion.
- Command-substitution status.
- Error fatality.
- Whether later assignments execute after a failure.
- Current-shell versus child-shell placement.
- Temporary application and rollback.
- Environment export.

### 8. Prefix `+=` on arrays mutates before snapshot and breaks `execve`

`resolve_append_assignment()` mutates an existing array in place before
`CommandAssignments.apply_prefix()` snapshots it.

Confirmed:

```sh
a=(x y)
a+=z /usr/bin/true
printf 'rc=%s\n' "$?"
declare -p a
```

Expected Bash behavior:

- The command succeeds.
- Its environment sees the scalar view `a=xz`.
- The original array is restored to `(x y)`.

PSH behavior:

- Places an `IndexedArray` object into `shell.env`.
- `execve` rejects the environment value with a Python type error.
- The array remains mutated as `(xz y)`.

The regular `env` builtin can return success while still leaving the array
mutated.

The associative-array path has the same structural problem.

#### Repair

- Make append resolution pure.
- Snapshot the original variable before computing the new value.
- Perform array append on a copy.
- Keep shell-state value and environment value as separate typed fields.
- Serialize the environment view explicitly through the variable's scalar
  representation.
- Apply and restore through an `AssignmentTransaction`.
- Never use a type-only `cast(str, value)` where runtime values can be arrays.

### 9. POSIX special-builtin semantics are inconsistent

The static `POSIX_SPECIAL_BUILTINS` strategy:

- Gives special builtins prefix-assignment persistence in default mode.
- Does not give them lookup precedence in POSIX mode.
- Omits the `.` and `times` special builtins.

#### Default-mode over-persistence

```sh
unset X
X=new :
printf '<%s>\n' "${X-unset}"
```

Observed behavior:

| Shell | Result |
|---|---|
| Bash default mode | `<unset>` |
| Bash POSIX mode | `<new>` |
| PSH | `<new>` in both modes |

#### Missing POSIX persistence for `.`

```sh
unset X
X=new . /dev/null
printf '<%s>\n' "${X-unset}"
```

Bash POSIX mode prints `<new>`; PSH prints `<unset>` because `.` is not in the
special-builtin set.

#### Missing POSIX lookup precedence

If a function named `export` is defined before POSIX mode is enabled, Bash
subsequently resolves `export` to the special builtin. PSH continues to call
the function because its strategy order is always:

```text
functions
special builtins
regular builtins
external commands
```

#### Repair

Make resolution mode-aware:

| Mode | Lookup order | Prefix persistence |
|---|---|---|
| Bash/default | functions, builtins, external | prefix is temporary unless the builtin itself changes state |
| POSIX | special builtins, functions, regular builtins, external | prefix persists for special builtins |

Create one complete special-builtin registry including:

```text
.
:
break
continue
eval
exec
exit
export
readonly
return
set
shift
times
trap
unset
```

The registry should provide policy data rather than relying on
`isinstance(strategy, SpecialBuiltinExecutionStrategy)`.

### 10. The job state model mishandles completed-plus-stopped pipelines

`Job.update_state()` currently marks a job stopped only when:

```python
all(p.stopped for p in self.processes)
```

A completed process has `stopped=False`. Therefore a pipeline with one
completed process and one stopped process is classified as running even though
none of its remaining live processes is running.

Confirmed:

```sh
set -m
true | sh -c 'kill -STOP $$'
jobs
```

Observed behavior:

| Shell | Job state |
|---|---|
| Bash | Stopped |
| PSH | Running |

The stopped pipeline is consequently not promoted correctly to the current
job `%+`.

#### Repair

The state rule should be:

```text
if every process is completed:
    DONE
elif every non-completed process is stopped:
    STOPPED
else:
    RUNNING
```

Use explicit process states rather than two correlated booleans:

```python
ProcessState.RUNNING
ProcessState.STOPPED
ProcessState.COMPLETED
```

### 11. Continued-process events are not represented

Both the interactive SIGCHLD processing path and foreground wait path use
`WUNTRACED` but not `WCONTINUED`.

Consequences:

- A job resumed outside `fg`/`bg` can remain marked stopped.
- `jobs` can report stale state.
- State correction depends on the specific builtin that issued `SIGCONT`.

#### Repair

- Request `WCONTINUED` where the platform supports it.
- Teach `Process.update_status()` to recognize `WIFCONTINUED`.
- Mark resumed processes running.
- Reset job notification state on stop/continue transitions.
- Add PTY tests for `kill -STOP %job`, `kill -CONT %job`, `jobs`, `fg`, and
  `bg`.

### 12. Jobspec signalling should target the process group once

The `kill` builtin resolves a jobspec into every recorded process PID and
signals each PID separately.

For a pipeline whose leader has already exited but another member remains
stopped or running, this produces a spurious “No such process” diagnostic for
the completed member even though the live job member is signalled
successfully.

Bash signals the process group represented by the jobspec.

#### Repair

Preserve target type during parsing:

```python
PidTarget(pid)
ProcessGroupTarget(pgid)
JobTarget(job)
```

`kill %1` should call:

```python
os.killpg(job.pgid, signal_number)
```

once.

The jobspec parser should also distinguish:

- No matching job.
- Ambiguous command-prefix match.
- Invalid syntax.
- Current/previous job unavailable.

Returning only `Optional[Job]` cannot express these diagnostics.

### 13. Partial pipeline launch is not transactional

If a later `fork()` or process-group operation fails after some pipeline
children have launched, the current exception path:

- Closes synchronization descriptors.
- Closes pipeline descriptors.
- Restores terminal ownership.

It does not:

- Terminate already launched children.
- Reap them.
- Prevent them from running an incomplete pipeline.
- Remove provisional job/process records.

Parent-side `setpgid()` failures are also broadly ignored without verifying
the child's actual process group.

#### Repair

Introduce a `ProcessGroupBuilder` transaction:

```text
begin provisional process group
for each child:
    fork
    register pid immediately
    assign and verify process group
commit:
    release synchronization gate
    publish Job
rollback:
    close gates/pipes
    signal partial process group
    reap all launched children
    restore terminal
    remove provisional records
```

Only specifically expected `setpgid()` race errors should be ignored.

### 14. Job lookup and status updates are O(N²)

Several hot job-control paths use linear searches:

- `JobManager.get_job_by_pid()` scans every process in every job.
- `Job.update_process_status()` scans every process in the job.
- `wait_for_job()` scans the process list again to find the status index.
- `Job.update_state()` scans the complete process list.

For a long pipeline, processing N child-status events can therefore perform
O(N²) work.

#### Repair

Maintain:

```python
pid_index: dict[int, tuple[Job, int]]
running_count
stopped_count
completed_count
```

A wait event can then update the correct process and job counters in O(1).

Remove index entries when a job is fully retired, while retaining the separate
bounded remembered-status table required by `wait`.

### 15. `time` ignores `TIMEFORMAT`

`ExecutorVisitor._execute_timed_pipeline()` always emits a hard-coded default
report.

Confirmed:

```sh
TIMEFORMAT='elapsed=%R'
time true
```

Bash prints the selected format. PSH prints its default three-line report.

An empty `TIMEFORMAT` suppresses Bash's report:

```sh
TIMEFORMAT=
time true
```

PSH still prints timing information.

The `time -p` format matches in the tested case.

#### Resource accounting

The implementation calculates child CPU time using global `os.times()` deltas.
Child activity from concurrently reaped background jobs can contaminate a
timed foreground pipeline.

#### Repair

- Implement Bash's `TIMEFORMAT` directives.
- Honor an empty format.
- Preserve `time -p` as a separate POSIX format.
- Collect per-child resource usage with `wait4()` where available.
- Aggregate resource usage into the job outcome.
- Define a portable fallback for platforms without `wait4()`.

### 16. Background builtin children bypass the shared shell-child runner

Background subshells, brace groups, and functions use
`run_background_shell_child()`. Background builtins do not: they directly call
the builtin inside a generic launcher child.

This loses shell-process exit behavior for builtins capable of executing shell
code.

Confirmed:

```sh
eval 'trap "echo bye" EXIT; echo body' &
p=$!
wait "$p"
echo "rc=$?"
```

Bash prints:

```text
body
bye
rc=0
```

PSH drops the EXIT trap and prints only:

```text
body
rc=0
```

The direct background builtin path also bypasses
`execute_builtin_guarded()` and `execute_in_context()`.

#### Repair

Treat a background builtin as a forked shell-process command:

- Use `run_background_shell_child()`.
- Use `execute_builtin_guarded()`.
- Preserve `BuiltinContext`.
- Apply redirections once in the child.
- Mark it `is_shell_process=True`.

The shared runner already implements the appropriate asynchronous-list signal
defaults and EXIT-trap behavior.

## Architectural issues

### 1. Execution decisions are split across too many layers

Command execution currently distributes policy across:

- `CommandExecutor`
- `RedirectionMode`
- Individual strategies
- `ProcessLauncher`
- `PipelineExecutor`
- `SubshellExecutor`
- `CommandAssignments`
- `ArrayOperationExecutor`
- `JobManager`

For example, background placement is decided inside a strategy, after
`CommandExecutor` has already selected and applied a foreground-style
redirection mode. That is the direct cause of duplicate background
redirections.

The executor needs one planning boundary before effects begin.

### 2. `ExecutionResult` is too narrow

`ExecutionResult` contains:

```python
status
prefix_assignments_persist
```

Execution also produces:

- `PIPESTATUS`.
- Background job handles.
- Process group IDs.
- Resource usage.
- Stop/continue state.
- Command-substitution status interactions.
- Assignment commit/rollback policy.

These are currently communicated through mutable shell state and side effects.

### 3. Execution context remains scattered

`ExecutionContext` contains:

- `in_pipeline`
- `loop_depth`
- `current_function`
- `errexit_suppress`

Related execution state lives elsewhere:

- `state.in_forked_child`
- `state.in_substitution`
- `state.errexit_eligible`
- `state.last_cmdsub_status`
- `state.function_stack`
- `state.source_depth`
- foreground process-group state
- trap inheritance state

The context object therefore only partially replaces scattered state.

A frame stack should distinguish:

```text
shell-global mutable state
lexical execution frame
function/source frame
forked-process frame
job/process outcome
```

### 4. Unexpected-defect handling is inconsistent

Several boundaries convert unexpected `Exception` instances to status 1 and
continue. Others print through `sys.stderr`, shell streams, or raw descriptor
2. Some EXIT/trap cleanup paths silently swallow all ordinary exceptions.

Forked children must map defects to a status rather than return into the parent
stack, but current-process execution should have one clear defect policy:

- Expected shell errors become typed outcomes.
- Control-flow signals propagate to their owner.
- Internal defects either re-raise in strict/development mode or pass through
  one report boundary.

### 5. Large modules hide independent state machines

The largest executor modules are:

```text
command.py             928 lines
job_control.py         811 lines
control_flow.py        729 lines
strategies.py          597 lines
array.py               526 lines
core.py                520 lines
```

Line count alone is not a defect, but these files contain multiple independent
state machines:

- Resolution.
- Placement.
- Redirection ownership.
- Assignment transaction.
- Process lifecycle.
- Job status.
- Terminal lifecycle.
- Jobspec parsing.

The recommended types below provide better module boundaries than splitting by
line count.

## Recommended target architecture

### 1. Compile a typed execution plan

```python
@dataclass(frozen=True)
class ExecutionPlan:
    resolution: CommandResolution
    placement: ProcessPlacement
    assignments: AssignmentPlan
    redirections: RedirectionPlan
    job_policy: JobPolicy
    trap_policy: TrapPolicy
```

Suggested placement values:

```python
CURRENT_PROCESS
FORKED_SHELL_CHILD
FORKED_EXEC_CHILD
PIPELINE_CHILD
EXEC_REPLACEMENT
```

The plan must decide redirection ownership before any target expansion or file
open occurs.

### 2. Use one execution outcome

```python
@dataclass(frozen=True)
class ExecutionOutcome:
    status: int
    pipeline_statuses: tuple[int, ...] = ()
    job: JobHandle | None = None
    resource_usage: ResourceUsage | None = None
```

The caller applies the outcome to shell-visible state:

```text
$?
PIPESTATUS
$!
job table
timing report
```

This removes several hidden status side channels.

### 3. Introduce assignment transactions

```python
@dataclass
class AssignmentTransaction:
    evaluated: list[EvaluatedAssignment]
    snapshots: dict[VariableTarget, VariableSnapshot]
    environment: dict[str, str]
    last_substitution_status: int | None

    def apply(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

Assignment targets should remain typed:

```python
ScalarTarget
IndexedElementTarget
AssociativeElementTarget
WholeArrayTarget
```

No array object should ever be placed directly into an environment mapping.

### 4. Introduce a process supervisor

The supervisor should own:

- Collision-safe descriptor remapping.
- Rolling pipeline creation.
- Fork and process-group setup.
- Immediate child registration.
- Terminal transfer.
- Wait and resource collection.
- Partial-launch rollback.
- Reaping guarantees.

Suggested lifecycle:

```text
ProcessGroupBuilder
  -> launch children provisionally
  -> verify process group
  -> publish JobHandle
  -> release synchronization gate
  -> wait or return background handle
```

### 5. Give jobs explicit indexed state

```python
class ProcessState(Enum):
    RUNNING = ...
    STOPPED = ...
    COMPLETED = ...

@dataclass
class ProcessRecord:
    pid: int
    state: ProcessState
    wait_status: int | None
    resource_usage: ResourceUsage | None
```

`JobManager` should maintain a direct PID index and state counters.

Jobspec parsing should return a result type capable of carrying ambiguity and
diagnostics.

## Target execution flow

```text
AST command
    |
    v
Resolve command and syntactic assignment roles
    |
    v
Build ExecutionPlan
  - command kind
  - placement
  - assignment transaction
  - redirection owner
  - process-group/job policy
    |
    v
Execute plan exactly once
  - apply/evaluate redirects in their owner process
  - apply assignments in their owner scope
  - launch or invoke command
    |
    v
ExecutionOutcome
  - status
  - pipeline statuses
  - job handle
  - resource usage
    |
    v
Commit/rollback assignment transaction
Update shell-visible status and job state
```

The central invariants should be:

1. Redirections execute exactly once.
2. Every effect has one owning process.
3. Parent state is never mutated for child-only commands.
4. Every temporary assignment is rolled back.
5. Every environment entry is a valid string/byte value.
6. Every launched child is registered and eventually reaped.
7. Descriptor remapping is collision-safe.
8. Pipeline parent descriptor usage is O(1).
9. Job state reflects active processes, not completed historical members.
10. Status is returned through a typed outcome rather than reconstructed from
    scattered mutable fields.

## Staged implementation plan

### Phase 1: Pin confirmed correctness defects

Add regression tests for:

1. `''`, `""`, and `"$empty"` as command names.
2. Prefix assignments before an empty quoted command.
3. `\function` and functions shadowing builtins.
4. Background builtin/function redirect substitutions executing once.
5. `for`, `select`, `case`, and C-style `for` header substitutions under input
   redirection.
6. Pipelines with descriptors 0, 1, and 2 independently closed.
7. A pipeline long enough to exceed the all-pipes-open design.
8. Array-element and whole-array command-substitution status.
9. Background assignment job status.
10. Multiple array assignments where an early assignment fails.
11. Array-subscript syntax before a command word.
12. Prefix array `+=` for builtins and external commands.
13. Default versus POSIX special-builtin behavior.
14. A pipeline containing completed and stopped members.
15. Background `eval` setting an EXIT trap.
16. Custom and empty `TIMEFORMAT`.

Then make the smallest local corrections necessary to turn those tests green.

### Phase 2: Unify assignments

1. Define typed assignment targets and roles.
2. Move array assignments out of the early command preamble.
3. Make append resolution pure.
4. Create `AssignmentTransaction`.
5. Separate shell-state values from environment serialization.
6. Return command-substitution status from every pure assignment form.
7. Apply first-failure and fatality rules consistently.
8. Delete duplicated array-specific assignment status logic.

### Phase 3: Introduce plan-based redirection ownership

1. Add `ProcessPlacement`.
2. Add `RedirectionOwner`.
3. Extend `CommandResolution` into `ExecutionPlan`.
4. Make background placement visible before redirection setup.
5. Remove child-side reapplication from individual strategies.
6. Put compound headers inside compound redirect scopes.
7. Add an architecture test that counts redirect-target expansion and asserts
   one evaluation per command.

### Phase 4: Replace pipeline descriptor handling

1. Implement the shared descriptor-remapping utility.
2. Promote internal descriptors away from 0/1/2.
3. Convert pipeline construction to rolling pipes.
4. Make pipe ownership explicit through small RAII/context-manager objects.
5. Add failure injection for `pipe()`, `fork()`, `setpgid()`, and `dup2()`.
6. Implement process-group rollback and child reaping.
7. Stress-test pipeline lengths around the active descriptor and process
   limits.

### Phase 5: Rebuild job state around indexed events

1. Replace process booleans with `ProcessState`.
2. Add `pid_index`.
3. Add state counters.
4. Handle `WCONTINUED`.
5. Correct completed-plus-stopped classification.
6. Return typed jobspec-resolution errors.
7. Signal jobspecs with `killpg()`.
8. Add mixed pipeline PTY tests.

### Phase 6: Extend outcomes and resource accounting

1. Add `ExecutionOutcome`.
2. Move `PIPESTATUS` updates to the outcome boundary.
3. Return background `JobHandle` rather than mutating `$!` deep in launch code.
4. Collect per-process resource usage.
5. Implement `TIMEFORMAT`.
6. Remove global `os.times()` child-delta accounting.

### Phase 7: Complete static and module-quality work

1. Close the 53 strict annotation gaps while replacing affected APIs.
2. Move jobspec parsing into a focused module.
3. Move descriptor planning into a focused module shared with `io_redirect`.
4. Reduce strategy method signatures by passing `ExecutionPlan`.
5. Replace repeated shell component lookups with explicit constructor
   dependencies.
6. Centralize unexpected-defect reporting.
7. Update `CLAUDE.md` and architecture documentation.

## Tests and quality gates to add

### Dispatch tests

- Zero-field and one-empty-field command words are never conflated.
- Quoting affects aliases but not functions.
- Default and POSIX lookup orders are separately pinned.
- Every POSIX special builtin appears in one authoritative registry.

### Assignment tests

- Every assignment form propagates the last substitution status.
- Background assignment status is observable through `wait`.
- An early failure prevents forbidden later effects.
- Temporary scalar and array assignments restore exact value and attributes.
- No non-string value reaches `execve`'s environment.
- Prefix array syntax follows Bash's contextual legality.

### Redirection tests

- Redirect targets expand exactly once.
- Compound redirects cover header and body evaluation.
- Parent-only and child-only effects occur in the correct process.
- Nested eval/source/function redirects restore in LIFO order.

### Descriptor tests

- All eight open/closed combinations for descriptors 0, 1, and 2.
- Source descriptor equal to destination.
- One pipe endpoint equal to another mapping's destination.
- Cyclic remapping.
- Failure during remap closes owned descriptors without closing destinations.
- No descriptor growth across repeated pipelines.

### Process lifecycle tests

- Inject failure after each pipeline child launch.
- No partial child remains running, stopped, or zombie.
- Process-group setup failures are reported or recovered explicitly.
- Foreground terminal ownership is restored after every failure point.

### Job tests

- Completed plus stopped members produce `STOPPED`.
- Continued events produce `RUNNING`.
- Jobspec ambiguity is diagnosed.
- `kill %job` signals the group once.
- PID lookup and status processing remain linear for long pipelines.

### Performance tests

- Pipeline parent descriptor count stays bounded as length increases.
- Status collection for N-process pipelines is O(N), not O(N²).
- Long command lists remain iterative.
- Resource-usage collection is isolated to the timed job.

## Final assessment

The execution subsystem has a strong low-level foundation and excellent
behavioral coverage. Its main weakness is not lack of process-control
knowledge; it is that command resolution, process placement, assignments, and
redirection ownership are selected at different times by different layers.

That makes individually reasonable components compose incorrectly:

- A foreground redirection mode is chosen before a strategy decides to fork.
- Array assignments execute before command shape and status policy are known.
- Pipe closure does not know which descriptors became final destinations.
- Job state examines historical completed members as though they were still
  active.

The highest-value sequence is:

1. Fix empty command, backslash/function, redirection ordering, and array
   status defects.
2. Make pipeline descriptor handling collision-safe and O(1).
3. Make special-builtin behavior mode-aware.
4. Introduce transactional assignments.
5. Compile a complete `ExecutionPlan` before performing effects.
6. Make process launch and job state transactional and indexed.

The governing principle should be:

> Resolve ownership before performing effects—one process owns each
> assignment, redirection, descriptor, child, and status transition.
