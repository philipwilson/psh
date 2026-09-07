# Fresh Codebase Appraisal: Correctness and Textbook Quality

Date: 2026-09-06. Revision: `6459f1a6e48b9f2cee4cda6d3b778f65ea2a417f` (v0.779.0).

Scope: all implementation subsystems, their contracts, representative tests, and development tooling. This is a fresh, risk-directed appraisal, not a reclassification of previous review findings. Previous appraisal contents were not used to generate the findings. No production code was changed.

## Prioritized Findings

These are reproduced defects, not speculative style complaints. P1 means address before relying on the affected workflow; P2 means a substantive correctness or efficiency defect; P3 means a lower-impact defect. Priorities describe impact, not how often every user will encounter the input.

There are **3 P1, 12 P2, and 1 P3 findings**. The evidence runner and raw observations are in [the evidence directory](evidence/fresh_appraisal_2026_09_06/README.md). Shell examples below run in disposable directories through that runner, not in the repository working directory.

### F01 [P1] Logical `cd` can enter a different directory from the one it reports

Location: [navigation.py:168](../../psh/builtins/navigation.py#L168), especially `os.chdir(actual_path)` at line 175.

```sh
mkdir -p real/child logical
ln -s ../real/child logical/link
cd logical/link
cd ..
p=$(pwd -P)
printf '%s %s\n' "${PWD##*/}" "${p##*/}"
```

Bash prints `logical logical`; PSH prints `logical real`. The implementation computes the logical destination but passes the unnormalized path to `chdir`, so the kernel follows the physical symlink ancestry. Publishing the logical destination afterward does not correct the actual working directory. Subsequent relative writes can affect the wrong files.

Improvement: derive the actual `chdir` operand from the logical destination in `-L` mode, preserving the distinct physical `-P` path. Test actual file placement and `os.getcwd()`/`pwd -P`, not just `$PWD`. Include relative and absolute `..`, symlinks, and `CDPATH`.

Adjacent, lower-impact defect: `CDPATH=:/nonexistent; cd child` prints the destination in PSH, although finding a directory through the empty `CDPATH` component should not trigger that output. Evidence: `cd_logical_parent`, `cd_empty_cdpath`.

### F02 [P1] Returning from a function can leave executable resolution using its local `PATH`

Location: [scope.py:331](../../psh/core/scope.py#L331), `pop_scope`; compare its notifications with `_notify_path_changed` at line 156.

```sh
mkdir a b
printf '#!/bin/sh\necho A\n' > a/probe
printf '#!/bin/sh\necho B\n' > b/probe
chmod +x a/probe b/probe
PATH=$PWD/a
f(){ local PATH=$PWD/b; probe; }
f
probe
```

Bash prints `B` then `A`; PSH prints `B` twice. Scope exit notifies the generic variable observer but does not invalidate the separate command hash. The visible variable is restored while the cached executable remains from the discarded scope.

Improvement: make effective-binding changes on scope exit invoke the same PATH-cache policy as assignment and unset. Test nested scopes, early `return`, failing function bodies, temporary environments, and actual dispatch rather than only the restored string value. Evidence: `path_scope_dispatch`, `path_scope_hash`.

### F03 [P1] Formatting and function serialization change executable semantics

Locations: [words.py:143](../../psh/ast_nodes/words.py#L143), [formatter_visitor.py:120](../../psh/visitor/formatter_visitor.py#L120).

```sh
v=X; v1=A; v2=B; printf '%s\n' ${v}{1,2}
```

The original prints `X1` and `X2`. `psh --format` emits `$v{1,2}`, whose brace expansion instead produces `$v1` and `$v2`, printing `A` and `B`. This is not confined to an optional display mode: defining the same body in `f`, then running `eval "$(declare -f f)"; f`, also changes the function's behavior in PSH.

The AST stores `VariableExpansion.braced`, but `__str__` discards it. The formatter only restores braces when the following character looks like part of a variable name. Furthermore, `braced` is excluded from dataclass equality, so an AST-equality round trip can miss the defect.

Improvement: preserve source braces in executable rendering, or implement a genuinely semantics-preserving canonical renderer. Add execution-equivalence tests for formatted scripts and `declare -f` output, including adjacent brace expansions. Idempotence and AST equality are useful but insufficient. Evidence: `format_roundtrip` records.

### F04 [P2] `mapfile` consumes input before rejecting its destination and can corrupt array attributes

Locations: [mapfile_builtin.py:125](../../psh/builtins/mapfile_builtin.py#L125), `_assign` at [line 223](../../psh/builtins/mapfile_builtin.py#L223).

```sh
printf 'one\ntwo\n' > data
exec 3<data
readonly a
mapfile -u 3 a
read -u 3 line
printf '<%s>\n' "$line"
```

Bash leaves `one` available to `read`; PSH has consumed the entire input despite rejecting the readonly assignment. Separately, `declare -A a=([x]=old); mapfile -t a <<< new; declare -p a` leaves the associative array intact in Bash, but PSH replaces it and prints the incompatible attribute combination `declare -aA`.

Improvement: resolve the final nameref destination and validate writability and indexed-array compatibility before reading. Centralize valid type/attribute transitions so callers cannot create an indexed value retaining the associative flag. Test descriptor position and preexisting contents after rejection, not just return codes. Evidence: `mapfile_readonly_consumption`, `mapfile_assoc_target`.

### F05 [P2] Process-substitution acquisition leaks resources when `fork` fails

Locations: [process_sub.py:62](../../psh/io_redirect/process_sub.py#L62), write-side acquisition at [line 144](../../psh/io_redirect/process_sub.py#L144).

Injecting `OSError(EAGAIN)` at `fork_with_signal_window` leaves both previously acquired pipe descriptors open on the read side. The equivalent write-side failure leaves its FIFO on disk. These are direct fault-injection observations: two acquired/two leaked descriptors, and an extant FIFO after failure.

The outer resource-scope abstraction cannot clean an acquisition that failed before returning and registering its resources.

Improvement: own every resource immediately after acquisition with local `try/finally` or `ExitStack`, transferring ownership only on success. Exercise failures at pipe creation, flag changes, FIFO creation, fork, and subsequent setup. This should complement, not replace, the existing process-substitution scope. Evidence: `procsub_fork_failure`, `procsub_write_fork_failure`.

### F06 [P2] A script-file read error is silently converted to EOF

Location: [input_sources.py:545](../../psh/scripting/input_sources.py#L545), `LazyFileInput._read_line_block`.

Every `OSError` from `os.read` becomes `block = b''`, which follows the true-EOF branch. Injected `EIO` returns `None` without an exception. The caller cannot distinguish a successfully exhausted script from an interrupted read, so remaining commands can be silently skipped; a buffered partial line can also be treated as complete.

Improvement: reserve EOF for an actual empty read and propagate/report read failures through the scripting error boundary. Test failure before input, after complete commands, and with a partial buffered command. The evidence proves the reader's incorrect result; a full script-driver fault-injection regression should also establish the required exit status. Evidence: `script_read_eio`.

### F07 [P2] Arithmetic promotion from scalar to array discards the scalar value

Location: [variable_store.py:225](../../psh/core/variable_store.py#L225), scalar branch of `set_element`.

```sh
a=7; (( a[2]=9 )); declare -p a
```

Bash preserves `[0]="7"` and adds `[2]="9"`; PSH retains only index 2. The supposedly guarded mutation primitive constructs a fresh indexed array without seeding element zero from the scalar. Other assignment paths implement their own conversion behavior.

Improvement: establish one scalar-to-indexed conversion rule used by arithmetic and normal element writes, preserving set/unset distinctions, empty values, attributes, and nameref targeting. Evidence: `arithmetic_scalar_promotion`.

### F08 [P2] Explicit array indices incorrectly set a high-water mark for subsequent elements

Location: [array.py:172](../../psh/executor/array.py#L172).

```sh
a=([5]=five [1]=one next); declare -p a
```

Bash puts `next` at index 2; PSH puts it at index 6. The builder uses `max(previous_next, explicit_index + 1)` rather than advancing from the most recent explicit assignment. The append form `a=([5]=five); a+=([1]=one next)` fails similarly.

Improvement: separate the initial append starting point from the current initializer cursor. Resolve negative indices before advancing that cursor; the evidence includes a passing negative-index control that a repair must preserve. Evidence: `array_descending_index`, `array_append_explicit_index`, `array_negative_initializer`.

### F09 [P2] Integer-array initialization applies attributes at the wrong phase

Locations: [array.py:93](../../psh/executor/array.py#L93), `_apply_declared_case_integer` at line 99, explicit-element append at line 165.

```sh
declare -ia a; a=(1 'a[0]+1'); declare -p a
declare -ia b=(1); b+=([0]+=2); declare -p b
```

The first operation stores index 1 as `1` in PSH instead of Bash's `2`: attribute evaluation cannot see the preceding newly assigned element. The second stores `12` instead of `3`: the builder concatenates strings before applying integer conversion.

Improvement: model shell expansion, attribute evaluation, and element commit as distinct phases, sharing integer append semantics with scalar/element assignment. Do not indiscriminately interleave all expansion with assignment: the control `a=(old); a=(new "${a[0]}")` correctly retains `old` as the second value today. Add evaluation-order, self-reference, partial-failure, and declaration-versus-bare-assignment cases. Evidence: `integer_array_read_previous`, `integer_array_append`, and the passing self-reference controls.

### F10 [P2] Associative initializers accept invalid empty keys and mixed forms

Location: [array.py:179](../../psh/executor/array.py#L179), `build_associative_array`.

```sh
declare -A a; a=([""]=bad); declare -p a; echo survived
declare -A b=([x]=one two three); declare -p b
```

PSH stores an empty associative key in the first case and silently combines subscripted and alternating key/value initializer forms in the second. The measured Bash oracle rejects both with status 1. The builder independently chooses a mode for each word, and neither it nor the container rejects the empty key.

Improvement: select the initializer form once and enforce its rules; validate expanded keys before mutation. Preserve the target Bash version's expansion order, diagnostics, and partial-state behavior rather than treating validation as necessarily all-or-nothing. Evidence: `assoc_empty_initializer`, `assoc_mixed_initializer`.

### F11 [P2] Completion does not reliably preserve filenames as literal shell words

Locations: [tab_completion.py:33](../../psh/interactive/tab_completion.py#L33), [line_editor.py:770](../../psh/interactive/line_editor.py#L770).

For `cat some\ fi`, the word-start finder selects only `fi`, losing the escaped-space path prefix. Inside double quotes, `_apply_completion` inserts a filename such as `report$HOME.txt` without escaping `$`. The resulting command expands the variable: with `HOME=/review-home`, the actual argument is `report/review-home.txt`, not the filename.

This is more than imperfect display: completion can turn filename characters into executable shell syntax. The evidence uses harmless variable expansion, not an injected command.

Improvement: represent completion context as raw replacement span, decoded lookup text, and quote mode; encode the selected filename for that context. Include escaped spaces, quotes, dollar signs, backticks, backslashes, and cursor-in-the-middle cases. The direct editor test proves insertion behavior; add real PTY tests for the complete workflow. Evidence: `completion_boundary`, `quoted_completion`.

### F12 [P2] Terminal input and layout conflate bytes, code points, and display columns

Locations: [key_decoder.py:285](../../psh/interactive/key_decoder.py#L285), [line_layout.py:43](../../psh/interactive/line_layout.py#L43).

Delivering the valid UTF-8 encoding of `U+00E9` in two reads (`b'\xc3'`, then `b'\xa9'`) produces two replacement characters. Each `os.read` chunk is independently decoded with `errors='replace'`; kernel read boundaries need not coincide with character boundaries.

Separately, prompt width uses `len`: a typical two-column CJK character measures as one, while `e` plus a combining acute accent measures as two rather than one. Cursor and wrap calculations therefore become unreliable for ordinary Unicode text.

Improvement: retain an incremental UTF-8 decoder across reads and preserve its pending state across editor/paste handoffs. Keep edit offsets separate from terminal cell positions, using a defined width/grapheme policy. Test split multibyte reads, malformed input, wide and combining characters, multiline prompts, and resize. These observations are unit-level, not a claim that a fresh full PTY matrix was run. Evidence: `split_utf8_input`, `prompt_columns`.

### F13 [P2] Invalid `read` options escape through Python numeric/platform exceptions

Locations: [read_builtin.py:543](../../psh/builtins/read_builtin.py#L543), descriptor preflight at [line 98](../../psh/builtins/read_builtin.py#L98).

```sh
read -t inf x < /dev/null; echo status:$?
read -u 999999999999999999999 x; echo status:$?
```

With `PSH_STRICT_ERRORS=1`, both expose an `OverflowError` traceback and abort before the trailing `echo`; Bash diagnoses the invalid operand and continues. A `nan` timeout also passes numeric parsing but reaches the wrong error path. The timeout check rejects negative numbers but not nonfinite floats; `fstat` can raise `OverflowError`, not just `OSError`, for a Python integer outside the platform descriptor range.

Improvement: validate finite timeout values and representable descriptor operands at option parsing/preflight. Catch expected conversion failures at the narrow boundary, not with a new catch-all around builtin execution. The strict-errors qualification matters: the evidence does not claim default mode always exposes a traceback. Evidence: `read_infinite_timeout`, `read_huge_fd`, `read_nan_timeout`.

### F14 [P2] Static security analysis loses the command behind assignment prefixes and wrappers

Location: [security_visitor.py:152](../../psh/visitor/security_visitor.py#L152).

Analysis of `eval "$payload"` reports high-severity issues, but `X=1 eval "$payload"` and `command eval "$payload"` both produce `No security issues found!` with status 0. These probes run `--security`, never the analyzed command.

The visitor uses `node.args[0]` as the executable even though the AST still contains assignment-prefix words, then dispatches checks on that string. Related visitors independently make the same command-head assumption. The baseline also labels a quoted variable as unquoted, illustrating precision problems alongside the false negatives.

Improvement: provide a shared structural command-head analysis that skips assignment prefixes, accounts conservatively for known wrappers, and represents dynamic/unknown cases explicitly. Use the existing typed words and quoting helpers; do not execute expansions during analysis. Describe a clean result as no findings from the implemented rules, not a security guarantee. Evidence: `security_analysis`.

### F15 [P2] Collecting one long unquoted literal has avoidable quadratic copying

Location: [literal.py:190](../../psh/lexer/recognizers/literal.py#L190), nested `take` and its `nonlocal value` concatenation.

The recognizer repeatedly appends characters to an immutable string held in a closure cell. Measuring tokenization of `echo ` followed by one literal gives these median CPU times across three samples on this host:

| Literal characters | Seconds |
| ---: | ---: |
| 10,000 | 0.0066 |
| 20,000 | 0.0142 |
| 40,000 | 0.0351 |
| 80,000 | 0.1189 |
| 160,000 | 0.4057 |

The final doublings cost about 3.4 times as much, consistent with the repeated prefix-copy cost. These are local microbenchmarks, not end-to-end shell throughput numbers or a cross-interpreter performance promise.

Improvement: accumulate segments and join once, tracking the few needed shape facts separately (`last character`, tilde-only prefix, assignment state). Preserve the already-useful forward shape/bracket trackers. Add long-single-word tests and copied-character/operation accounting so this cost is not hidden by benchmarks dominated by many short words. Evidence: `long_literal_lexing`.

### F16 [P3] Metrics undercount command substitutions nested in parameter templates

Location: [metrics_visitor.py:461](../../psh/visitor/metrics_visitor.py#L461).

`echo $(true)` reports one command substitution; `echo ${x:-$(true)}` reports zero. In both cases the traversal sees two commands, so this is not a missing nested program in the AST. Counting direct word features duplicates part of the traversal and misses the template route.

Improvement: count substitution nodes in their visitor method, with an explicit separate policy for genuine text-only syntax. Avoid double-counting by removing the corresponding direct-word increments. Include nested parameter operands and process substitutions in the expected metrics. Evidence: `metrics_analysis`.

## Grades and Overall Judgment

**Overall: B-.** This is a substantial, unusually well-tested shell implementation with several excellent internal designs. It is not yet a textbook reference implementation: important state transitions disagree across entry points, two basic workflows can act on the wrong directory or executable, and executable serialization is unsafe for a valid input.

These grades are qualitative engineering judgments, not percentages inferred from test counts.

| Dimension | Grade | Reason |
| --- | --- | --- |
| Correctness | C+ | Broad successful behavior, but the confirmed defects include wrong targets, input loss, and changed program semantics. |
| Architecture | B | Real subsystem boundaries, typed intermediate forms, and useful ownership abstractions; policy duplication remains beneath some central facades. |
| Textbook clarity and Python style | B- | Mostly readable, conventional Python, but large coordinators and extensive historical commentary obscure the operative algorithm. |
| Efficiency | B- | Strong targeted algorithms and descriptor discipline; avoidable literal copying and acknowledged quadratic multiline parsing remain. |
| Verification engineering | B | Extensive live-oracle, regression, fault, and operation-count tests; the local gate is not green and some missing tests concern basic cross-path invariants. |

### Subsystem Scorecard

Grades summarize the inspected design and evidence, not equal-depth certification of every function. Physical lines include comments, docstrings, and blanks. The census is **276 Python files, 84,506 lines, and 3,249 function/method definitions** in `psh/`.

| Subsystem | Files / lines | Grade | Appraisal and next improvement |
| --- | ---: | --- | --- |
| Entry points and orchestration | 5 / 1,638 | B+ | Pure invocation parsing into a frozen config is a good boundary; startup ordering is explicit. Keep `Shell` as composition/orchestration and gradually retire duplicate legacy configuration paths. |
| AST | 9 / 1,458 | B | Structured words and nested programs retain information needed downstream. F03 shows that source provenance excluded from equality may still be semantically necessary for rendering. Specify separate structural and executable-round-trip contracts. |
| Lexer | 29 / 6,964 | B | Contextual recognizers, quote rules, word fusion, forward shape tracking, and fail-loudly progress checks are sensible. Fix F15 and make command-position/quote-state ownership easier to follow without historical context. |
| Parser, including combinators | 54 / 11,587 | B | Production recursive descent and typed complete/incomplete/invalid outcomes provide a sound base. Combinators have useful commitment and farthest-error behavior, but two grammar implementations impose real parity maintenance. Keep educational status explicit and retain differential tests. |
| Expansion, arithmetic, patterns | 32 / 12,310 | B+ | Protected/splittable field runs are the right abstraction, not gratuitous machinery. Exact integer division, short-circuit arithmetic, immutable compiled patterns, and transition instrumentation are strengths. Fix assignment-boundary defects without flattening this information-rich model. |
| Executor | 18 / 9,212 | B- | Rolling pipelines, explicit foreground-job sessions, and staged prefix assignment are good designs. Array construction has multiple semantic errors; command dispatch remains a long, flag-heavy transaction. |
| I/O redirection | 8 / 3,691 | B | Source-ordered planning and collision-safe descriptor remapping handle genuinely difficult ownership. Complete acquisition rollback in F05; distinguish resource acquisition, fd application, Python-stream rebinding, and permanent-baseline ownership in the large redirector. |
| Core state | 24 / 8,107 | B- | Set/unset distinctions, sparse arrays, observers, and process leases are useful foundations. F02/F07 show that neither cache invalidation nor conversion invariants are enforced on every mutation path. |
| Builtins | 39 / 11,985 | C+ | Registry and shared declaration/input helpers are useful, but builtin behavior remains uneven. Navigation, `mapfile`, numeric parsing, and declaration/array interactions need stronger shared contracts. |
| Scripting | 12 / 3,549 | B- | Unified source processing and lazy input support meaningful script/stdin distinctions. Fix false EOF in F06; preserve decoder and descriptor ownership, then address long-line and open-command costs. |
| Interactive | 23 / 5,889 | C+ | Separating editing, decoding, rendering, completion, and history improves testability. The filename and Unicode defects affect normal terminal use; validate them through a focused real-PTY matrix after unit fixes. |
| Visitors and analysis | 14 / 5,346 | C | Shared traversal is valuable, but formatting, command-head analysis, and feature counting each discard or reconstruct information incorrectly. Consolidate these specific semantic views. |
| Utilities | 8 / 2,356 | B+ | Focused helpers such as fd remapping and printf support are preferable to duplicating their rules. No additional standalone defect was confirmed in the inspected utilities; continue boundary/fault tests. |
| Protocols | 1 / 414 | B | Small role protocols help isolate some ownership. Others expose concrete `ShellState` and subsystem implementations, so a protocol annotation alone does not establish a narrow dependency boundary. |

## Design Improvements Beyond Individual Bugs

### 1. Enforce mutation invariants where the write happens

`VariableStore` is a useful API direction, but stores, scope operations, declaration helpers, and array builders still independently decide conversions, attributes, and notifications. The defects above arise from that duplication, not from a shortage of type names or manager classes.

Define the contract for each actual transition: scalar-to-array promotion; indexed versus associative representation; attribute application; append computation; nameref resolution; effective-binding restoration; and derived cache/environment updates. Put each rule in one appropriate owner and make callers use it. Do not assume every shell assignment is an all-or-nothing transaction: Bash exposes ordered side effects and partial failures in some forms.

A compact cross-entry-point test matrix should cover ordinary assignment, arithmetic, `declare`/`local`, nameref writes, `read`/`mapfile`, and scope exit. Assert values, flags, effective lookup, external environment, and executable dispatch as appropriate. This is more valuable than another structural guard asserting that a particular helper name appears in source.

### 2. Preserve the good typed models; simplify coordinators around them

Keep the field-run expansion model, typed parse outcomes, resolved command values, resource leases, and source-ordered redirect programs. They encode distinctions that shell semantics genuinely require.

The main opportunities are concrete: [command.py:381](../../psh/executor/command.py#L381) spans 263 physical lines in `_run_command`; [state.py:101](../../psh/core/state.py#L101) has a 323-line constructor; `scope.set_variable` spans 172 lines; and `file_redirect.py` is 1,431 lines. Size alone is not a bug, but these sites combine multiple lifecycle phases and unwind flags.

Extract named phases only when their inputs, outputs, and cleanup obligations become simpler. Replace a bundle of transaction flags with one small state/ownership object where it makes invalid combinations impossible. Do not split every branch into a forwarding method or introduce another generic framework.

For the educational combinator parser, a typed union from heterogeneous `or_else` would communicate more than the current loose `Parser` return. Treat that as a teaching-quality improvement, not a production correctness emergency.

### 3. Separate algorithm explanation from development history

Many comments correctly explain non-obvious shell rules. Keep those, especially examples that distinguish quote protection, expansion timing, fd ownership, and error propagation.

However, repeated campaign identifiers, former bug stories, and uppercase claims of a sole authority make parts of the code read like an audit ledger. The [variable_lookup.py](../../psh/core/variable_lookup.py) module's long microbenchmark/history preamble and the many similar coordinator comments increase the effort needed to find the current invariant. F02 and F07 demonstrate why saying an API is central does not establish that every path uses its policy.

Prefer a short contract, the surprising semantic rule, and one example near the implementation. Move historical rationale and benchmark receipts to linked design notes. Review documentation indexes for stale claims of which appraisal or campaign is "latest" or "active"; do not confuse an old closure record with current correctness evidence.

Pythonic modernization is secondary: built-in generic types and `X | None` are appropriate for the declared Python baseline, but opportunistic adoption is preferable to a large cosmetic rewrite. Improving data invariants and exception boundaries matters much more.

### 4. Target demonstrated costs, not an indiscriminate rewrite

- Fix F15's repeated literal-prefix copying first: it is narrow and measured.
- [ParseSession](../../psh/parser/session.py) explicitly reparses a growing non-heredoc logical command on every input line, giving quadratic aggregate work. This is an acknowledged limitation, not a newly discovered omission. Immediate syntax-error reporting is required; quadratic reparsing is a consequence of the current non-resumable implementation, not an inherent requirement of shell grammar. A resumable lexer/parser is a larger, separately budgeted project.
- Preserve the existing linear handling of complete-command streams and incremental heredoc bodies. Characterization tests of quadratic behavior should become upper-bound/improvement-aware tests when that implementation changes, not prevent a speedup.
- `LazyFileInput._read_line_block` also repeatedly concatenates and rescans the growing tail of a very long physical line. Consider a chunk accumulator and scanning only newly arrived bytes. This is a static cost observation; no separate reader benchmark was measured here.
- `mapfile`'s unbounded read path holds the whole input and then split records. After preflight correctness is fixed, incremental record processing can reduce peak duplication, even though the destination array must still hold its contents.
- Keep sparse-array operations proportional to stored elements, bounded pattern caches, iterative plain-glob matching, exact integer arithmetic, and rolling pipeline descriptor use. These are already good algorithmic choices.

## Verification and Limits

Environment: macOS, Python 3.14.7, Bash `/opt/homebrew/bin/bash` version `5.3.15(1)-release`. Many existing oracle comments target Bash 5.2. This review reports the measured oracle version and does not silently attribute every version-sensitive difference to a new PSH regression.

Completed checks:

- `ruff check psh tests tools`: passed.
- `mypy`: passed for 276 source files.
- Evidence runner: 65 JSON records, including 37 differential cases; 15 differ in stdout and/or exit status. Other records cover formatting, fault injection, analysis, terminal helpers, and timings. Passing controls cover short-circuit arithmetic, IFS splicing, quoted patterns, redirection order, pipeline status, source positionals, RETURN status, and readonly-array expansion suppression.
- The comparison flag intentionally checks stdout/status only; raw stderr and typed process outcomes are preserved. Equal flags do not certify identical diagnostics, filesystem side effects, or timing.
- No new coverage percentage was measured. The canonical run includes passing PTY smoke and focused interactive tests, but no additional comprehensive PTY matrix was run for this appraisal. No fresh Linux run, extended randomized parser campaign, or full benchmark tier was performed. The targeted lexer CPU measurements are not that benchmark tier.

Full canonical gate and permission-sensitive rerun results are recorded in [validation.md](evidence/fresh_appraisal_2026_09_06/validation.md), with the [full transcript](evidence/fresh_appraisal_2026_09_06/canonical-tests.txt). The gate is not green: **23,985 passed, 52 failed, 1,631 skipped, and 10 xfailed** across the two standard phases. Both phases completed; neither timed out.

Four initial permission-sensitive failures (socket setup, escaped-process cleanup, history output through `/dev/stdout`, and the process-state precondition of a `bg` test) pass in explicit unsandboxed reruns. One index failure concerns the pre-existing untracked `ground_up_reappraisal_23_correctness_textbook_2026-08-09.md`, which this review leaves untouched. The other failures require oracle-version/platform/behavior triage; they are not all independent newly confirmed defects.

The existing suite is a significant strength: isolated shell outcomes, live comparisons, strict internal-error detection, fault injection, and operation-count guards test more than happy-path output. Its limits are equally important. Structural representation tests cannot substitute for executable round trips; setter tests cannot substitute for scope restoration; return-code tests cannot detect consumed input or a wrong cwd. The nightly workflow adds Linux coverage, extended parser differential testing, and a benchmark tier, but it is not evidence that those checks passed in this review. A fast automated pre-merge smoke check would provide useful protection alongside the documented local gate and nightly workflow.

This was an all-subsystem risk-directed review with targeted source reading and experiments, not a line-by-line proof of all 84,506 lines. In particular, untested signal schedules, terminal behavior, locales, filesystem races, and platform variations remain residual risks.

## Recommended Sequence

1. Fix F01-F03 first, with actual-target and execution-equivalence regressions. These address wrong directory, wrong executable, and changed serialized program behavior.
2. Repair `mapfile` preflight, process-substitution acquisition cleanup, and script-read error propagation (F04-F06). Add fault and side-effect assertions at the ownership boundary.
3. Consolidate array conversion/initializer semantics and land the F07-F10 matrix together with narrowly scoped implementation changes.
4. Fix completion, Unicode handling, and numeric input validation (F11-F13), then run focused PTY and strict-errors tests across the supported Python/platform matrix.
5. Correct structural command analysis and visitor counting (F14/F16). Separately make the narrow lexer optimization (F15), then consider resumable parsing only with a measured cost target.
6. Establish a green, version-identified oracle baseline. Classify retained divergences by Bash version and platform, and distinguish unsupported/skipped cases from correctness passes.
7. Simplify large coordinators and historical commentary after their behavioral contracts are pinned. Grade the result by whether a new reader can explain state transitions and cleanup from the code, not by module count or the number of introduced abstractions.

Bottom line: retain the architecture's strongest ideas, but make the implementation earn its centralization and ownership claims on every route. The largest improvement in both correctness and elegance will come from fewer independently implemented semantic rules, backed by observable cross-path invariants.
