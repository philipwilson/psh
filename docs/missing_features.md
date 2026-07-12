# Missing Features — Design Notes & Roadmap

This document captures **deferred features** that are large enough to deserve
their own focused implementation session rather than being squeezed into a
mixed bug-fix release. Each entry records the bash semantics we must match,
what psh does today, an integration plan against the current architecture, the
edge cases that will bite, and a rough effort estimate.

These grew out of the ground-up reappraisal #14 (2026-06-22,
`docs/reviews/ground_up_reappraisal_14_2026-06-22.md`). The MED-severity
findings that were quick, localized fixes shipped in v0.540–v0.559; what
remains here are the standalone features and one cosmetic-but-broad item.
Later reappraisals add entries as gaps are confirmed (`coproc`, #17).

Status legend: **Deferred** = agreed worth doing, not yet scheduled.

---

## 1. `BASH_SOURCE` / `BASH_LINENO` (call-stack introspection arrays)

**Status: Deferred.** Genuinely useful (error handlers, library-style
sourced scripts, `trap ... ERR` diagnostics). Needs a real per-frame
source + call-line stack — more than the flat name stack `FUNCNAME` uses.

### Bash semantics

`FUNCNAME`, `BASH_SOURCE`, and `BASH_LINENO` are three **parallel arrays**
describing the current call stack, innermost frame first. They only carry
meaning together:

- `FUNCNAME[i]` — name of function at stack frame `i` (`FUNCNAME[0]` = the
  currently-executing function).
- `BASH_SOURCE[i]` — the source file in which `FUNCNAME[i]` was **defined**
  (for the bottom frame, the file bash is currently reading; `main` for the
  top-level of an interactive shell or `-c` string).
- `BASH_LINENO[i]` — the line number **in `BASH_SOURCE[i+1]`** at which
  `FUNCNAME[i]` was **called**. Note the off-by-one: `BASH_LINENO[i]` is the
  call site of frame `i`, which lives in frame `i+1`'s source. `${BASH_LINENO[0]}`
  is the line in the caller that invoked the current function.

Worked example (`lib.sh` sourced from `main.sh`):

```bash
# lib.sh
greet() {                      # defined in lib.sh
  echo "${FUNCNAME[@]}"        # -> greet main
  echo "${BASH_SOURCE[@]}"     # -> lib.sh main.sh
  echo "${BASH_LINENO[@]}"     # -> 4 (the line in main.sh calling greet)
}
# main.sh
source lib.sh
greet                          # <- this is line 4 of main.sh
```

Key rules to match:

- Outside any function, `FUNCNAME` is unset/empty, but `BASH_SOURCE[0]` is the
  current file and `BASH_LINENO` is `(0)` / current line context.
- `source`/`.` pushes a frame whose `FUNCNAME` entry is `source`.
- The **bottom** of `BASH_SOURCE` is the top-level script name (or `main`);
  `$0` is unchanged inside functions (psh already gets this right —
  `function.py:124`).
- Arrays shrink/grow exactly in step with function entry/exit and
  source-nesting.

### Current state in psh

- `state.function_stack` is a flat `list[str]` of function names, pushed on
  entry / popped on exit (`executor/function.py:129,167`).
- `FUNCNAME` is synthesized on read by reversing that list
  (`core/scope.py:604-617`) — so it already exists and is correct.
- `Function` objects have a placeholder `self.source_location = None  # Could
  add file:line info later` (`core/functions.py:25`) — **nothing populates it.**
- Current line is tracked for `$LINENO` via
  `scope_manager.set_current_line_number()` (called from
  `scripting/source_processor.py:194` and `executor/core.py:118,163,215`), but
  only a single scalar "current line," not a per-frame call-line.
- `state.script_name` / `state.is_script_mode` (`core/state.py:90-91`) and
  `state.source_depth` (`core/state.py:143`) exist but there is no stack of
  source-file names.
- `visitor/enhanced_validator_visitor.py:69` already whitelists `BASH_SOURCE`
  and `BASH_LINENO` as known variable names, so the validator won't flag them
  — reads today just return empty.

### Implementation plan

The core work is turning the flat name stack into **frame records** carrying
three facts, then synthesizing the arrays the same lazy way `FUNCNAME` is
today.

1. **Frame record.** Replace (or shadow) `state.function_stack: list[str]`
   with a stack of small frame objects, e.g.
   `CallFrame(func_name, source_file, call_line)`. Keep a `FUNCNAME`-compatible
   view so existing reads don't churn. `func_name` = `source` for a
   `source`/`.` frame.
2. **Populate `source_location` at definition.** When
   `FunctionManager.define_function` runs, stamp the function with the file it
   was defined in (bottom frame's current `BASH_SOURCE`). This is `BASH_SOURCE[i]`
   for that function's frame.
3. **Capture the call line at call time.** In
   `executor/function.py:execute_function_call`, before pushing the frame,
   read the current line (`scope_manager.get_current_line_number()`) and the
   current source name — that pair becomes the new frame's `call_line` and the
   caller's context. This is where the `BASH_LINENO` off-by-one is realized.
4. **Push a frame for `source`/`.`** in the source builtin so sourced files
   appear in `BASH_SOURCE` with a `source` entry in `FUNCNAME`, incrementing
   `source_depth` as it already does.
5. **Synthesize the arrays** in `core/scope.py` alongside `FUNCNAME` (same
   `IndexedArray` + `VarAttributes.ARRAY` pattern, frames reversed
   innermost-first). Add `BASH_SOURCE` and `BASH_LINENO` cases to the special-
   variable dispatch.
6. **Base frame.** When the stack is empty, `BASH_SOURCE[0]` = current script
   name (or `main` for `-c`/interactive), `BASH_LINENO` = `(0)`.

### Edge cases / gotchas

- The `BASH_LINENO[i]` vs `BASH_SOURCE[i+1]` off-by-one is the whole ballgame —
  build a bash truth table across (script calls fn), (fn calls fn), (sourced
  lib calls fn), (trap handler), (`-c` string) **before** coding.
- Line numbers under `eval`/`trap` are already anchored to the invoking
  command's line (the v0.485 `LINENO` fix, `scope.py:625` comment) — reuse that
  anchoring for `call_line`, don't reset to 1.
- Subshells inherit a **copy** of the stack (`ShellState.clone_for_child`) — make sure
  the frame stack is deep-copied there.
- `${BASH_SOURCE}` (no index) = `${BASH_SOURCE[0]}` (bash scalar-of-array rule
  psh already implements for arrays).
- macOS-vs-Linux: none expected; this is pure bookkeeping.

### Test plan

Conformance tests under `tests/conformance/bash/` comparing the three arrays
against live bash across the truth-table scenarios above; a sourced-library
fixture; a `trap ... ERR` handler reading `BASH_SOURCE`/`BASH_LINENO`.
Remember: any user-guide "Full support" claim needs a mapped conformance test
(`test_claims_have_tests.py`).

### Effort

Medium. The array synthesis is easy (mirror `FUNCNAME`); the frame-record
refactor and getting the call-line/off-by-one exactly bash-correct is the real
work. ~1 focused session.

---

## 2. `complete` / `compgen` / `compopt` (programmable completion)

**Status: Deferred.** The **largest** remaining item — it's an entire
subsystem (a completion spec registry + the generators + wiring into the
line editor), not a bug fix.

### Bash semantics (scope to match)

- **`compgen`** — write candidate completions to stdout (no UI). Supports
  generator actions: `-A function|command|file|directory|variable|alias|
  builtin|keyword|...`, the convenience flags `-c -a -b -f -d -v -k -e -j -s`,
  a word list `-W 'a b c'`, a glob `-G`, prefix/suffix `-P`/`-S`, and filtering
  against the current word. `compgen -W 'foo bar baz' ba` → `bar baz`.
- **`complete`** — register a completion **spec** for a command:
  `complete -F _myfunc git`, `complete -W 'start stop' svc`,
  `complete -A directory cd`. `complete -p` prints specs; `complete -r` removes;
  `-o` options (`default`, `nospace`, `filenames`, `bashdefault`, ...) and `-D`
  (default spec) / `-E` (empty-line spec).
- **`compopt`** — modify options of the spec being used, from inside a
  completion function.
- **The `-F` function protocol** — the completion function is called with the
  words `$1`=command, `$2`=current word, `$3`=preceding word, and reads
  `COMP_WORDS` (array), `COMP_CWORD` (index), `COMP_LINE`, `COMP_POINT`; it
  fills the `COMPREPLY` array with candidates. This is what bash-completion
  scripts in the wild depend on.

A realistic minimum-viable target: `compgen` generators + `complete -F/-W/-A`
+ `COMP_WORDS`/`COMP_CWORD`/`COMPREPLY` so common `_command` completion
functions run. `compopt` and the full `-o` matrix can be a second increment.

### Current state in psh

- Tab completion is **path-only**: `CompletionEngine` (`tab_completion.py`)
  does file/dir completion via `_get_path_completions`; it is owned by the
  `LineEditor` (`line_editor.py:66`) and invoked from the editor's own
  completion-UI glue (psh does **not** use readline).
- There is **no** `complete`, `compgen`, or `compopt` builtin (confirmed by
  grep — nothing registers those names).
- No completion-spec registry, no `COMP_*` variables, no `COMPREPLY`
  consumption.

### Implementation plan

1. **CompletionSpec registry** — a new component (e.g.
   `psh/completion/spec_registry.py` or under `interactive/`) mapping command
   name → spec (`{action, wordlist, function, options}`), plus the `-D`/`-E`
   defaults. Owned by the shell so builtins and the editor share it.
2. **`compgen` builtin** — pure generator: parse the action/flags, produce
   candidates from shell state (functions from `FunctionManager`, builtins from
   the registry, variables from `ScopeManager`, aliases from `AliasManager`,
   files/dirs by reusing `CompletionEngine._get_path_completions`), filter by
   the current word, apply `-P`/`-S`. No UI. This is the foundational piece and
   is independently testable with `captured_shell`.
3. **`complete` builtin** — register/print/remove specs in the registry.
4. **`-F` invocation bridge** — the hard part: when the editor completes a
   command that has an `-F` spec, set `COMP_WORDS`/`COMP_CWORD`/`COMP_LINE`/
   `COMP_POINT`, call the shell function via the normal executor, then read the
   `COMPREPLY` array back out. Requires splitting the current input line into
   COMP_WORDS the way bash does (its own word-split, not full expansion).
5. **Editor wiring** — `LineEditor`'s completion glue consults the registry
   first (command-name position → command completion; argument position →
   look up the command's spec; fall back to path completion). Keep
   `CompletionEngine` as the default/path generator.
6. **`compopt`** — modify the in-use spec's options (second increment).

### Edge cases / gotchas

- **Word splitting for `COMP_WORDS`** must match bash's completion tokenizer
  (respects quotes, splits on `COMP_WORDBREAKS`) — not the same as the shell's
  full word-splitting. Get a truth table first.
- `compgen -W` runs its wordlist through expansion (so `-W '$(...)'` works).
- The editor runs in **raw mode**; invoking a user completion function
  re-enters the executor mid-line-edit — be careful about terminal state and
  re-entrancy (the completion UI already toggles raw mode around listing).
- `-o filenames` / `-o nospace` affect how the editor appends the completion
  (trailing space, slash on dirs) — that's editor-side, not `compgen`-side.
- This subsystem is interactive-only for the `-F` bridge, but `compgen` itself
  is testable non-interactively (bash allows `compgen` in scripts).

### Test plan

- Unit tests for `compgen` generators with `captured_shell` (each `-A` action,
  `-W`, `-P`/`-S`, current-word filtering) vs bash.
- Unit tests for `complete`/`complete -p`/`complete -r` spec bookkeeping.
- A `COMPREPLY` round-trip test (register `-F`, drive the split→call→read
  bridge, assert candidates) — can be exercised without a PTY by calling the
  bridge directly.
- Optional PTY tier (`--run-interactive`) for end-to-end tab behavior.

### Effort

Large — realistically split into increments: (a) `compgen` generators, (b)
`complete` registry + `-W`/`-A` wiring into the editor, (c) the `-F` /
`COMP_*` / `COMPREPLY` bridge, (d) `compopt` + full `-o` matrix. Two to three
focused sessions.

---

## 3. `coproc` (coprocesses)

**Status: Deferred.** (Entry added by reappraisal #17 — the feature was
confirmed unimplemented and documented as such in ch17, but had no roadmap
section here.) A whole new execution form: an asynchronous command wired to
the parent shell through a two-way pipe exposed as shell variables. Less
commonly used than the two items above; scripts in the wild usually reach
for named pipes or process substitution instead.

### Bash semantics

`coproc [NAME] command [redirections]` runs *command* asynchronously in a
subshell, with a two-way pipe established between it and the calling shell:

- `NAME` defaults to `COPROC`. `NAME` may only be given for a **compound**
  command — with a simple command the word is interpreted as the command
  itself (verified live: `coproc NAMED sleep 5` leaves `NAMED_PID` unset and
  tries to run `NAMED`).
- `NAME[0]` is a file descriptor from which the shell **reads the coproc's
  stdout**; `NAME[1]` is a descriptor **writing to its stdin**. Usage shape:
  `echo req >&"${NAME[1]}"; read -r resp <&"${NAME[0]}"`.
- `NAME_PID` holds the coproc's PID (`wait $NAME_PID` reaps it and returns
  its exit status).
- The descriptors are **not available in subshells** (verified:
  `( read <&"${CAT[0]}" )` → "Bad file descriptor") and are not inherited by
  child processes — they must be `exec`-dup'd to a plain fd first.
- Starting a second coproc while one is active prints
  `warning: execute_coproc: coproc [PID:NAME] still exists` but proceeds.
- `coproc` itself returns 0 immediately (async, like `&`); the coproc shows
  up in job control.

### Current state in psh

- Not a keyword, not a builtin: `coproc COP { echo hi; }` produces
  `psh: coproc: command not found` (and the stray `}` then also fails) —
  exit 127. There is no parser, executor, or state support of any kind.
- ch17 documents it as unimplemented (compatibility-table "No" row plus the
  17.2 section), and the row is pinned by a `NO_ROW_PROBES` staleness probe
  in `tests/conformance/test_claims_have_tests.py` — implementing coproc
  will make that probe fail, forcing the docs flip.
- The building blocks all exist: `fork_with_signal_window()` /
  `apply_child_signal_policy()` (`executor/child_policy.py`),
  `ProcessLauncher` for job-controlled background processes, `JobManager`,
  and `IndexedArray` + `VarAttributes.ARRAY` for the `NAME` variable.

### Implementation plan

1. **Parser.** Recognize `coproc` in command position (both parsers — RD and
   combinator): an optional `NAME` word followed by a compound command, or a
   simple command with no NAME. New AST node `CoprocCommand(name, body,
   redirects)`; `--format`/visitor support (formatter, validator) in the
   same change.
2. **Executor.** Create two `os.pipe()` pairs, fork the body via
   `ProcessLauncher` as a background job (own process group, no terminal),
   child dup2s one pipe end onto stdin and the other onto stdout; parent
   keeps the opposite ends.
3. **Variable wiring.** In the parent, publish `NAME` as an `IndexedArray`
   (`[read_fd, write_fd]`) and `NAME_PID`; set close-on-exec on both fds so
   external children do not inherit them (bash behavior above).
4. **Job integration.** Register with `JobManager` so `jobs`/`wait` see it;
   emit the bash "still exists" warning when a live coproc is already
   registered.
5. **Docs truth-up.** Flip the ch17 row (Full-support conformance test +
   `CLAIM_TESTS` mapping), delete the `NO_ROW_PROBES` entry, update the 17.2
   section and the migration-guide greps, and remove this section.

### Edge cases / gotchas

- The NAME-vs-simple-command parsing rule (word is the command unless the
  body is compound).
- fd bookkeeping across nested redirections — the coproc fds must survive
  per-command redirect save/restore but stay invisible to subshells and
  exec'd children (close-on-exec, plus explicit removal in `ShellState.clone_for_child`
  for forked subshell copies).
- Deadlock is user-visible behavior: the pipe buffers are finite, and bash
  makes no attempt to prevent write-write deadlock — match that (do not add
  hidden buffering).
- Reaping: after `wait $NAME_PID`, bash leaves `NAME` set but the fds closed
  once the coproc exits and its output is drained — pin exact lifecycle
  against live bash before coding (truth-table first, per the H5 lesson).

### Test plan

Conformance tests under `tests/conformance/bash/`: the echo-through-`cat`
round trip; `COPROC` default naming; `NAME_PID` + `wait` exit status;
fd-invisibility in subshells (the verified probes above, promoted). Golden
cases in `tests/behavioral/golden_cases.yaml` for the async/exit-status
shape. The meta-test wiring in step 5 keeps ch17 honest automatically.

### Effort

Medium-large. The parser and variable wiring are straightforward; the fd
lifecycle (close-on-exec, subshell invisibility, reap semantics) is the real
work. ~1 focused session, after building the bash truth table.

---

## Appendix — other deferred items (smaller)

Tracked here so the reappraisal-#14 backlog lives in one place. These are
smaller than the two projects above but were still left for later:

- **Script error prefix `scriptname: line N:`** — bash prefixes runtime
  diagnostics with source+line; psh uses a flat `psh:` prefix. Deferred as
  **cosmetic and broad**: ~39 `psh:` diagnostic sites plus the forked-child
  error path, and exit codes already match. The reappraisal's own comparison
  method treats the error-prefix as an intentional difference. Low value-to-risk.
- **`mapfile -C callback` / `-c quantum`** — documented gap in the `mapfile`
  builtin; the callback-every-N-lines feature is unimplemented.
- **SIGHUP-on-exit / `huponexit` (and `disown -h`)** — psh does not send
  SIGHUP to its jobs when the shell exits, so there is no `huponexit` shopt
  and `disown -h` is accepted only for compatibility (it leaves the job in
  the table but marks nothing). Implementing this needs an exit-time hangup
  pass over the job table plus the per-job no-hup flag.
- **Tier-1 follow-ups deferred during v0.540–547** (see CHANGELOG and
  `memory/psh-reappraisal-14.md`):
  - `trap ... RETURN` pseudo-signal + exact `functrace=on` DEBUG fire-counts (H2c).
  - Arithmetic assignment-error `-c`-vs-script fatality nuance (H6b).
  - `readonly` function-redefine "unexpected error:" wording (H6c).
  - `for x in '$lit'` literal-vs-expansion in `--format` output — needs
    `ForLoop.items` migrated from flat strings to the Word layer (H8 root cause:
    flat-string AST fields are the formatter's weak spot).
- **`set -x` for `[[ ... ]]`** and source-quote-style preservation of quoted
  `for`/`case` items — both limited by the same flat-string AST fields (M12,
  documented in `tests/integration/test_xtrace_format.py`).
- **Byte-model `\xff` → UTF-8** (reappraisal M8) — architectural; deferred
  across multiple rounds.
