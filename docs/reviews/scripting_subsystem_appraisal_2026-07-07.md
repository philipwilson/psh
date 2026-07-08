# Scripting Subsystem Appraisal — 2026-07-07

## Scope

A fresh, probe-verified appraisal of psh's **scripting / non-interactive
execution** subsystem, graded for:

- correctness against Bash 5.2 for script semantics;
- POSIX non-interactive shell semantics;
- robustness under malformed, truncated, and pathological input;
- testability and architectural clarity; and
- documentation accuracy.

The review covered:

- `psh/scripting/` — `source_processor.py`, `command_accumulator.py`,
  `input_sources.py`, `input_preprocessing.py`, `script_executor.py`,
  `script_validator.py`, `visitor_modes.py`, `base.py`;
- the non-interactive entry paths in `psh/__main__.py` and `psh/shell.py`
  (`run_command`, `_init_interactive`);
- the `source`/`.`/`eval` builtins (`psh/builtins/source_command.py`,
  `psh/builtins/eval_command.py`);
- script-file execution, `-c` string mode, stdin-as-script, `-s`, and the
  `--validate`/`--format`/`--lint`/`--security`/`--metrics` analysis modes;
- shebang handling, `source`/`eval` positional-parameter and `return`
  semantics, special parameters (`$0`/`$1..`/`$#`/`$@`/`$*`/`$?`/`$-`/`$_`);
- multi-line/line-continuation accumulation, comment/blank handling,
  `$LINENO`, heredoc-at-EOF; and
- `set -e`/`-u`/`-o pipefail`/`-x` behavior, exit-status propagation,
  exit-on-error input abandonment, and EXIT/RETURN trap firing.

**Oracle:** `/opt/homebrew/bin/bash` = GNU bash 5.2.26. **psh under test:**
main at `968a3af4` (v0.662.0), confirmed via `psh.__main__.__file__` and
`git rev-parse`. Every behavioral claim below was run in BOTH shells, as a
`-c` string AND as a script file (and as stdin where relevant), with the
`(rc, stdout, stderr)` delta recorded. Probe scripts live under
`tmp/scripting_probe/`.

## Executive Judgment

This is a **strong, carefully-built subsystem** — the best-graded of the
recent appraisal wave. The line-gathering design is genuinely good: a single
completeness oracle (`CommandAccumulator`) is shared by the script reader and
the interactive PS2 loop, both driven by the *real* lexer/parser rather than
keyword heuristics; execution reuses the trial-parse AST instead of parsing
twice; and every whole-shell run funnels through one chokepoint
(`execute_as_main`) that fires the EXIT trap exactly once. Dozens of subtle
Bash behaviors reproduce **byte-for-byte**: `$LINENO` in functions defined and
called at different lines, the unterminated-heredoc "delimited by
end-of-file" warning, `set -e` POSIX exemptions, `set -e` cleared inside
command substitution, source positional-parameter save/restore, `return`/EXIT
status propagation, and the errexit input-abandonment vs. containment split
between `-c` and script files.

The subsystem has **one architectural gap** that produces silent wrong output:
a script delivered *on stdin* drains fd 0 up front, so `read` (and any command
that reads stdin) inside the script cannot consume subsequent input the way
Bash does. This is the single highest-value finding. The remaining findings
are a small `--validate` file-handling cluster (MED) and two LOW edges.

Overall grade: **A−**.

## Grades

| Dimension | Grade | Assessment |
| --- | --- | --- |
| Correctness vs Bash (script files, `-c`) | A | Dozens of subtle cases match exactly; no defect found in the file/`-c` paths. |
| POSIX non-interactive semantics | B+ | One real gap: the stdin script source is not shared with runtime stdin. |
| Robustness | A− | Graceful on infinite `source` recursion where **bash segfaults**; surrogateescape byte-transparency; closed-fd handling; binary/FIFO sniff guards. |
| Analysis-mode fidelity (`--validate` &c.) | B− | Its own file reader diverges from the execution path (encoding, error codes). |
| Testability | B+ | Excellent factoring and single chokepoints, but the stdin-as-script path has no differential test. |
| Architecture & clarity | A | Shared oracle, single chokepoints, accurate and generous docstrings. |
| Documentation accuracy | B+ | Ch. 17 is thorough; the two real gaps here are undocumented. |

## What Is Already Strong

### One completeness oracle, shared and honest

`CommandAccumulator` (`command_accumulator.py`) is the single answer to "is
this command complete?", consumed by both the script/`-c`/stdin reader and the
interactive PS2 loop. Crucially the decision comes from the **real lexer and
parser** — an `UnclosedQuoteError`, a `ParseError` with `at_eof=True`, and the
parser's `open_constructs` trail — not from string-matching error messages.
Heredoc bodies are tracked incrementally (`_close_heredocs_matching`, O(1) per
body line) so a body line like `)` is never shown to the parser as command
text. This is textbook-quality.

### Parse-once execution

When the recursive-descent parser is active, the accumulator's trial-parse AST
and token stream are handed to the execution path and *reused*, provided the
execution-side preprocessing reproduces the trial's source text
(`_parse_command`, `source_processor.py:369`). The subsystem never parses the
same text twice on the common path.

### One EXIT-trap chokepoint

`execute_as_main` (`source_processor.py:48`) is the single funnel for every
non-interactive whole-shell run (`-c`, script file, piped stdin). It fires the
EXIT trap exactly once no matter how the run ends — normal EOF, `set -e`
abort (recovered from `SystemExit`), or explicit `exit` (idempotent
`execute_exit_trap`) — and correctly lets an `exit N` *inside* the trap
override the status. It also runs a signal trap queued by the final statement
before the EXIT trap, matching bash.

### Faithful error-model boundary

`_execute_buffered_command` (`source_processor.py:216`) has a genuinely
well-reasoned try/except structure with a documented clause order that *is*
the semantics: `ParseError`/`UnclosedQuoteError` → exit 2; `TopLevelAbort`
containment (fatal expansion / readonly / failglob discards, with the
`contain_nested` / `errexit_immune` distinctions probe-verified against bash);
control-flow signals routed to enclosing frames; `RecursionError` unwound to
the FUNCNEST boundary; internal-defect guard last. The comments cite the exact
bash behaviors and the probe directories that established them.

### Byte-transparent, crash-resistant input

`FileInput` (`input_sources.py:48`) reads the whole script eagerly with
`errors='surrogateescape'` and `newline=''`, then closes the fd *before any
command runs* — sidestepping the fd-collision hazards (`exec 3>&-`, `{var}`
allocation at fd 10) that a held-open script fd would create, and letting a
non-UTF-8 script byte round-trip instead of crashing the shell. `__main__`
mirrors this for stdin (`_read_all_stdin`, surrogateescape) and reconfigures
the output streams to match (`_enable_byte_transparent_output`), plus a
shutdown-flush guard for scripts that close fd 1/2 themselves
(`_neutralize_closed_std_streams`).

### Graceful on runaway recursion

Infinite `source` self-recursion returns rc 1 with a diagnostic in psh; the
same script **segfaults bash** (rc 139). psh degrades where the C shell
crashes.

### Faithful reproduction (representative, all probe-verified MATCH)

`$LINENO` across blank lines and inside functions; the unterminated-heredoc
warning (byte-identical to bash including the script-name prefix); `set -e`
POSIX exemptions and errexit-in-function; `set -e` cleared in `$(...)`; `set
-o pipefail`; `set -x` trace (byte-identical); `set -u` fatal status;
`source` `$0`-unchanged + positional save/restore + shared-positionals +
`return N`; `eval` multi-line with per-line discard containment and `$LINENO`
anchoring; `$_`; process substitution and `/dev/stdin` as script arguments;
NUL-byte binary rejection (126); directory (126) / not-found (127) invocation
codes; shebang-as-comment plus real shebang re-exec via the external path;
top-level `return`/`break`/`continue` diagnostics; unclosed-quote-at-EOF
(exit 2); and the errexit input-abandonment (`-c`) vs. containment (file)
split.

## Critical Findings

### 1. HIGH — A script delivered on stdin drains fd 0, so `read` (and any stdin-reading command) inside it cannot consume subsequent input

**Files:** `psh/__main__.py:273-291` (`_read_all_stdin`, which does
`buffer.read()` — the *entire* stream) consumed at `psh/__main__.py:462-486`
(the non-interactive stdin branch builds a `StringInput` from the slurped
text) and the `-s` path at `psh/__main__.py:445-448`.

**Status: CONFIRMED.**

When psh's command source *is* stdin — bare `cmds | psh`, `psh < file`, or
`psh -s` — psh reads **all** of fd 0 into a string and executes it as an
in-memory `StringInput`. fd 0 is therefore empty for the duration of the run,
so `read`, `mapfile`, `cat`, or any external command that reads stdin sees
immediate EOF. Bash reads its stdin script *lazily* (byte-at-a-time for
`read`), so the script text and the runtime input share the same
fd and a `read` consumes the next physical line. POSIX requires the
shell's command input and the `read`/data stream to be the same lazily-consumed
stream when the shell reads from standard input.

This produces **silent wrong output**, not an error, and is general — it
affects `cat` and every stdin consumer, not just `read`.

Repro (general case — `cat` inside a piped script):

```sh
$ printf '%s\n' 'echo START' 'cat' 'echo END' | bash
START
echo END          # cat consumed the 'echo END' line as data; never executed

$ printf '%s\n' 'echo START' 'cat' 'echo END' | python -m psh
START
END               # cat saw EOF (fd 0 drained); psh ran 'echo END' from its buffer
```

Repro (`read`, the common idiom):

```sh
$ printf '%s\n' 'read a' 'read b' 'echo "a=[$a] b=[$b]"' 'X' 'Y' | bash
a=[read b] b=[]   # read a consumed the next script line as data
$ printf '%s\n' 'read a' 'read b' 'echo "a=[$a] b=[$b]"' 'X' 'Y' | python -m psh
a=[] b=[]         # read a saw EOF
```

Scope is precise and worth stating plainly, because it bounds the blast
radius. The gap appears **only when the script itself arrives on stdin**:

| Invocation | fd 0 for `read` | Result |
| --- | --- | --- |
| `cmds \| psh` / `psh < file` / `psh -s` | drained buffer | **DIVERGES** (this finding) |
| `psh script.sh` (+ separate `\| psh script.sh`) | the real pipe/tty | MATCH (probe CASE A) |
| `psh -c '...'` (+ separate piped stdin) | the real pipe/tty | MATCH (probe control) |

The real-world cases this breaks are `curl … | psh` install scripts that
`read` a confirmation from the same stream, and `psh < script` where the
script consumes its own trailing data.

**Fix direction.** Replace the stdin slurp with a lazy line-reading input
source over fd 0 that does *not* read ahead past the current logical command —
the shell reads one command's worth of lines and leaves the rest of the fd
intact for `read`/`cat`. The codebase already has the needed primitive: the
streaming, one-record-at-a-time descriptor reader in
`psh/builtins/input_reader.py` (built for the `mapfile -n1` drain fix) reads a
non-seekable source without over-consuming. A `StdinInput(InputSource)` that
reads fd 0 line-by-line through that reader (rather than
`buffer.read()` into a `StringInput`) would restore Bash's read-sharing while
keeping the accumulator interface unchanged. Note the interaction with
history-less non-interactive mode is nil (no history recorded on this path
already). No test currently pins either the correct or the current behavior;
add a differential test for `read`/`cat`-consumes-stdin under `| psh`,
`psh < file`, and `psh -s`.

## Medium / Low Findings

### 2. MED — Analysis-mode (`--validate` &c.) file reading diverges from the execution path

**File:** `psh/scripting/visitor_modes.py:93-105`
(`handle_visitor_mode_for_script`).

**Status: CONFIRMED.** Two sub-issues, both because the analysis modes read
the script through a bare `open(script_path, 'r')` (default UTF-8-strict,
universal newlines) instead of the execution path's
`errors='surrogateescape'` `FileInput`.

**(a) Non-UTF-8 script cannot be validated even though it executes fine.**

```sh
$ printf 'echo caf\xe9\n' > s.sh
$ python -m psh s.sh;            echo rc=$?     # executes fine
caf<e9>
rc=0
$ python -m psh --validate s.sh; echo rc=$?
Error processing script: 'utf-8' codec can't decode byte 0xe9 in position 8: invalid continuation byte
rc=1
```

The `--validate` promise ("check for parse errors") fails on a script that
parses and runs. `UnicodeDecodeError` is caught as a `ValueError` at
`visitor_modes.py:101` and reported as a generic processing error. Fix: read
with `errors='surrogateescape'` (and ideally reuse `FileInput`'s reader) so
analysis sees exactly the bytes the executor would.

**(b) Missing-file exit code is 1, not Bash's/execution's 127.**

```sh
$ python -m psh /no/such.sh;            echo rc=$?   # 127 (matches bash)
$ bash -n /no/such.sh;                  echo rc=$?   # 127
$ python -m psh --validate /no/such.sh; echo rc=$?   # 1  (visitor_modes.py:98-99)
```

The `FileNotFoundError → return 1` branch diverges from the execution path
(`ScriptValidator` returns 127) and from `bash -n`. Note that psh's own
`-n`/`noexec` path is correct (it goes through normal execution and returns
127) — the divergence is specific to the psh-only `--validate` family.

### 3. LOW — A trailing backslash-newline continuation at the end of a buffered command is not removed

**Files:** `psh/scripting/command_accumulator.py:293-305` (`_complete` stores
`text=raw.rstrip('\n')`) and `psh/scripting/source_processor.py:305-352`
(`_preprocess_command` re-runs `process_line_continuations` on that raw
`text`); the join in `psh/scripting/input_preprocessing.py:71-75` requires a
*following* line, which the stripped newline has removed.

**Status: CONFIRMED.**

```sh
$ printf 'echo end\\\n' > s.sh   # last line is: echo end\<newline><EOF>
$ bash s.sh          # end
$ python -m psh s.sh # end\
```

Mechanism: the accumulator's *trial* preview correctly drops the trailing
continuation (it parses `echo end`), but `_complete` hands execution the raw
`text` (`echo end\`) with its terminating newline `rstrip`-ped away. Because
`text != source`, the AST is not reused, and execution's own
`process_line_continuations('echo end\\')` cannot recognise a trailing
backslash with no following line as a continuation, so the lexer keeps it as a
literal. Bash removes the backslash-newline even at end-of-input. The case is
narrow (a script/`-c`-stdin whose *final* logical line ends in a dangling
continuation) and mid-command continuations are unaffected. Not in the
differences ledger. `-c 'echo end\'` (no newline) matches bash in both shells,
so only the file/stdin-with-terminating-newline form diverges.

### 4. LOW — Infinite `source` recursion is reported through the internal-defect channel

**File:** `psh/scripting/source_processor.py:527-543`
(`_classify_buffered_error`: a non-nested `RecursionError` falls through to
`report_internal_defect` with the `"unexpected error: "` prefix).

**Status: CONFIRMED.** `source`-ing a self-referential file prints
`psh: -c:1: unexpected error: maximum recursion depth exceeded` (rc 1). The
*behavior* is good — bash segfaults (rc 139) — but `RecursionError` is a
documented *expected* error (see the strict-errors taxonomy in
`psh/core/CLAUDE.md`), so framing it as an "unexpected error" is mildly
self-contradictory. A dedicated resource-limit diagnostic (as the
FUNCNEST/recursion depth path uses elsewhere) would read better. Purely
cosmetic; no correctness impact.

## Non-Findings (verified, and worth recording so they are not re-flagged)

- **`$0` for `-c` is `psh`, not the interpreter path.** Cosmetic; bash uses
  its `argv[0]`. Both set `$0` to the script path for a script file. Not a
  defect.
- **CRLF line endings**: psh strips one trailing CR per line (`one\ntwo`);
  bash keeps the CR. This is the **documented** divergence
  (`input_sources.py:88`, ch. 17.3) — not re-flagged.
- **Alias expansion in non-interactive mode**: deliberate, ledgered
  divergence (ch. 17.3).
- **`noclobber` "double error" across a psh-then-bash probe** was a shared
  file-state artifact (psh's run created the target the bash run then saw);
  isolated, both shells behave identically.
- **`--validate` on a valid script, `-n`/noexec, empty/whitespace input,
  process-substitution and `/dev/stdin` script args, binary/FIFO sniff
  guards** — all correct.

## Recommended Improvement Plan

### Phase 1 — Restore stdin script/read sharing (the one that matters)

1. Add a `StdinInput(InputSource)` that reads fd 0 lazily, one logical
   command's lines at a time, through `psh/builtins/input_reader.py`'s
   non-over-consuming reader — replacing the `_read_all_stdin()` slurp +
   `StringInput` in the non-interactive stdin and `-s` branches of
   `__main__.main`.
2. Preserve the surrogateescape byte model and the closed-fd guards already
   present.
3. Add differential tests: `read`/`cat`/`mapfile` consuming stdin under
   `cmds | psh`, `psh < file`, and `psh -s` — asserting the next-line
   consumption and the residual-input hand-off, against live bash. Promote to
   `tests/behavioral/golden_cases.yaml` so `--compare-bash` pins it.

### Phase 2 — Make analysis modes read like the executor

1. Route `handle_visitor_mode_for_script` through the same reader `FileInput`
   uses (`errors='surrogateescape'`, `newline=''`), so `--validate` accepts
   every script the executor would run.
2. Align the missing-file exit code with the execution path / `bash -n` (127),
   or document the analysis-mode codes explicitly.
3. Add a test: `--validate` on a non-UTF-8-but-valid script returns 0; on a
   missing file returns the same code as `psh script.sh`.

### Phase 3 — Small correctness/clarity edges

1. Remove a trailing backslash-newline continuation at end-of-buffer (carry
   the continuation decision from the accumulator's preview into `text`, or
   have `_preprocess_command` treat a lone trailing backslash on the final
   line as a continuation to an empty line). Add a golden case.
2. Report `RecursionError` at the top-level buffered boundary through a
   resource-limit diagnostic rather than the `"unexpected error"` prefix.

## Checks-Run Appendix

All probes run with `cwd = /Users/pwilson/src/psh`, psh at `968a3af4`
(v0.662.0), oracle `/opt/homebrew/bin/bash` 5.2.26. Each probe had a 10s
process-group-killing timeout; an orphan sweep
(`ps -axo pid,ppid,%cpu,command | awk '$2==1 && $3>50'`) ran after every batch.
Harness and scripts are under `tmp/scripting_probe/`.

Per-machine-discipline note: no full `pytest`, `run_tests.py`, or
`--compare-bash` was run (a release wave is active on this host). A recurring
external `cat f` at 100% CPU (PPID 1) appeared during several sweeps; it is
**not** produced by these probes (confirmed by argument mismatch — the harness
runs bare `cat`, never `cat f`) and is attributed to the concurrent wave. The
final sweep was clean; these probes leave no orphans.

Probe batches executed (each psh-vs-bash, `-c` and file where relevant):

1. Special/positional params: `$0`, `$-` (incl. `set -e` → `ehBc`), `$#`,
   `$@`, `$*`, `-c name a b` → `$0/$1/$#`. **MATCH** (`$0`-for-`-c` cosmetic).
2. Syntax-error input abandonment (`for`, `if then`) + `set -e` in file/`-c`.
   **MATCH** (rc 2, correct partial output).
3. Line continuations (single, multi, inside comment), blank/comment
   interleaving, comment-only script, dangling-backslash-at-EOF. **MATCH**
   except finding #3.
4. `set -u`, `set -o pipefail`, `set -x` (stderr byte-identical), errexit in a
   called function. **MATCH**.
5. `--validate` valid/invalid, `-n`/noexec valid/invalid, stdin-as-script,
   `-s` with args. **MATCH** (surfaced finding #2 on the analysis path).
6. `source` `$0`/positionals/`return 42`/shared-positionals/missing-file;
   `eval` multi-line discard containment. **MATCH**.
7. Exit status = last command; bare `exit`; `$LINENO` across blanks; `exit`
   inside sourced file exits shell. **MATCH**.
8. Readonly-assignment and special-builtin fatal-error abandonment (`-c`) vs
   containment (file); assignment-prefix to readonly; `unset` readonly. **MATCH**.
9. Process substitution / `/dev/stdin` as script arg; CRLF (documented
   divergence); NUL-byte binary rejection (126). **MATCH**.
10. Heredoc-delimited-by-EOF warning (byte-identical); multi-line function;
    nested if/for; indented/inline comments; heredoc across a `-c` string.
    **MATCH**.
11. `read` consuming subsequent stdin script lines (piped, plain and
    while-read). **DIVERGES → finding #1**.
12. Invocation errors (not-found 127, directory 126); EXIT trap fires once
    (`-c`, stdin); EXIT-trap status. **MATCH**.
13. Empty/whitespace input; `exec` replacing the process; `set -e` in `$(...)`;
    `$_`. **MATCH**.
14. `$LINENO` inside a function; top-level `return`/`break`/`continue`;
    EOF-in-incomplete-construct (rc 2); shebang re-exec via external path.
    **MATCH**.
15. Unclosed-quote-at-EOF (rc 2); `source` self-recursion (psh rc 1 vs **bash
    segfault rc 139**); 5000-line script (0.93s); 150-deep nested `if`
    (**MATCH**, rc 0).
16. `--validate` on non-UTF-8 (crash) and missing file (rc 1 vs 127); CRLF
    validate; `-n` on missing file (127). **finding #2**.
17. stdin-drain generality (`cat`) + controls (`-c` and script-FILE with
    separate piped stdin both **MATCH**). Confirms finding #1 scope.
