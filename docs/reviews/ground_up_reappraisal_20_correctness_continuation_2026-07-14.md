# Ground-Up Reappraisal #20: Correctness Continuation

**Date:** 2026-07-14
**Snapshot:** PSH 0.724.0, commit `d1b8ef35`
**Scope:** correctness revalidation of every critical/high finding from #20,
plus startup, multi-shell state, parser-combinator contracts, analysis modes,
test infrastructure, CI/release evidence, and performance-test blind spots
**Method:** static review, fresh differential probes against bash 5.2.26,
complexity instrumentation, focused suites, the excluded performance suite,
Ruff, mypy, and the canonical gate
**Overall grade:** **B-**

This is the current correctness supplement to
[`ground_up_reappraisal_20_correctness_textbook_2026-07-11.md`](ground_up_reappraisal_20_correctness_textbook_2026-07-11.md).
It also complements the independent
[`ground_up_reappraisal_21_textbook_2026-07-12.md`](ground_up_reappraisal_21_textbook_2026-07-12.md),
which grades elegance, clarity, and efficiency but deliberately does not grade
bash feature parity and lists workflows, most test content, performance-harness
internals, and live PTY behavior as coverage gaps.

## Executive assessment

The v0.699-v0.724 work materially improved the codebase. The critical redirect
code/data boundary violation from #20 is fixed; direct nested substitutions are
parsed earlier; newline glob semantics and adversarial extglob matching are
better; the top-level import graph is now acyclic and ratcheted; the executor,
redirect, arithmetic, and scripting packages contain several publishable
components. The current tree is 258 production Python files / 70,089 lines and
668 test-side Python files / 120,853 lines. Ruff and mypy are clean.

That progress does not yet make the interpreter textbook-correct. All nineteen
high-severity categories from #20 retain a live defect at v0.724; two are
partially repaired, while the rest reproduce without qualification. Fresh work
also exposed independent defects in invocation construction, multi-`Shell`
resource ownership, the public parser-combinator algebra, reusable combinator
heredoc state, and the evidence chain used to call a release green.

The recurring problem remains **semantic facts being decided before the system
has the authoritative context**:

- startup files run before parser, options, mode, and positional parameters are
  fully installed;
- command assignment scope is chosen from a raw-name prelookup rather than the
  final command resolution;
- quote and field metadata is collapsed before splitting and globbing;
- analysis parses a whole file under its initial shell options rather than the
  state transitions execution observes;
- each `Shell` independently claims process-global signals, cwd, locale, and
  descriptors;
- test classifiers infer success from text summaries after pytest has already
  returned an internal-error status.

Those are model defects, not a request for more local conditionals.

### Scorecard

| Dimension | Grade | Current assessment |
| --- | --- | --- |
| Semantic correctness | **C+** | No current critical injection issue, but every #20 high category still has a live residual, including syntax timing, field boundaries, descriptors, signals, input bytes, and scope. |
| Architecture | **B** | Import layering and several engines improved substantially; startup ordering and process-global ownership still lack explicit models. |
| Clarity and teaching value | **B+** | Strong subsystem prose and ratchets; several comments and tests now confidently describe properties the probes disprove. |
| Elegance | **B** | Good local abstractions coexist with duplicated cursors, pre-resolution shortcuts, stateful parser reuse, and lossy expansion joins. |
| Efficiency | **C+** | O(1) pipeline and memoized extglob work is strong; plain glob matching remains exponential and interactive accumulation is intentionally quadratic. |
| Tests | **B** | 19,838 collected cases and strong differential coverage; normal gates exclude performance and 63 PTY cases, four tests hardcode a macOS-only bash path, and two harnesses can report false success. |
| Documentation | **A-** | Extensive and candid overall; the standard-tier phase description and several performance/test-runner claims are false. |
| Tooling/release discipline | **B-** | Ruff/mypy and the local gate are serious; PR CI is disabled and version bumps auto-tag without an enforced green dependency. |

## Verification

All behavioral results below were re-run at `d1b8ef35`; archived output was not
used as proof.

| Check | Result |
| --- | --- |
| `ruff check psh tests` | Passed |
| `mypy` | Passed over 258 source files |
| `python run_tests.py --quick` | 11,924 passed, 4 skipped in 25.54s |
| `python run_tests.py --parallel` | **Failed:** 18,232 passed, 21 failed, 1,575 skipped, 10 xfailed |
| `python -m pytest tests/performance -q` | 17 passed, 1 xfailed in 47.85s; this tree is excluded from normal pytest and the canonical gate |
| Parser/analysis/heredoc focused suites | 116 passed in 8.89s |
| Test-runner hardening suite | 28 passed in 3.13s, despite the uncovered mixed-`INTERNALERROR` counterexample below |
| Test census | 19,838 collected; 147 interactive, of which 63 remain opt-in; 18 performance cases |
| Release-snapshot gate recorded by #21 | 18,254 passed, 0 failed, 10 xfailed, 1,574 skipped |

The 21 full-gate failures split into two independent results. The three dynamic
locale failures reproduce alone (`3 failed, 16 passed`) and are current product
failures. The history case, all 11 process-substitution cases, and all 36
fatal-signal/EXIT-trap cases pass when their files are rerun independently.
Those 18 are evidence of a non-hermetic aggregate gate, not 18 independently
broken product behaviors. A release snapshot reported green while the same
commit's current gate is red; without hermetic execution, neither transcript is
an authoritative release oracle.

## Delta from #20

### Resolved: expanded redirect text is no longer reinterpreted as syntax

The former critical C1 is fixed. The redirect planner now obtains process
substitution from the AST rather than recognizing `<(...)` in expanded text.
At v0.724:

```sh
x='<(touch marker)'
printf DATA > "$x"
```

creates the literal file `<(touch marker)`, does not create `marker`, and exits
zero, matching bash. This restores the central code/data boundary.

### Partially resolved: nested parsing and pattern matching

Direct command and process substitutions now parse eagerly through
[`word_builder.py:122`](../../psh/parser/recursive_descent/support/word_builder.py#L122)
and [`nested_parse.py:43`](../../psh/parser/recursive_descent/support/nested_parse.py#L43).
Deferred raw-string regions still delay errors in parameter operands,
arithmetic expressions, array subscripts, and C-style loop expressions.

Newline matching and adversarial extglob groups are fixed, but plain glob
patterns still compile to Python regex at
[`pattern.py:88`](../../psh/expansion/pattern.py#L88). Thus #20 H7 remains open
on complexity even though its newline-semantic half is repaired.

## Revalidated #20 ledger

| Finding | v0.724 status | Current evidence |
| --- | --- | --- |
| C1 expanded redirect data executed as syntax | **Resolved** | Literal `<(touch marker)` filename created; no command execution. |
| H1 multiple heredocs close out of order | **Live** | Both completeness oracles search all delimiters before the collector enforces queue order: [`heredoc_detection.py:417`](../../psh/utils/heredoc_detection.py#L417), [`command_accumulator.py:264`](../../psh/scripting/command_accumulator.py#L264). |
| H2 invalid nested substitutions run before late error | **Partly resolved, live residual** | Parameter operands, arithmetic, array subscripts, and C-style expressions remain raw strings; `${x:-$(if)}` still runs surrounding commands and exits zero. |
| H3 heredoc delimiter representation is lossy | **Live** | `$'EOF'` is decoded as `$EOF`, consumes the terminator and following command: [`heredoc_detection.py:44`](../../psh/utils/heredoc_detection.py#L44). |
| H4 builtin fd closes violate left-to-right order | **Live** | `: 1>&- 2>&1` returns zero instead of a bad-fd error; close is deferred at [`manager.py:485`](../../psh/io_redirect/manager.py#L485). |
| H5 composite expansion loses field boundaries | **Live** | `"$@"$x` produces `a`, `bc d` instead of `a`, `bc`, `d`: [`word_expander.py:846`](../../psh/expansion/word_expander.py#L846). |
| H6 glob protection is word-wide | **Live** | `"*"*` and `a\*b*` overmatch after segment metadata is collapsed: [`word_expander.py:191`](../../psh/expansion/word_expander.py#L191), [`word_expander.py:948`](../../psh/expansion/word_expander.py#L948). |
| H7 pattern semantics/complexity | **Partly resolved, live residual** | Newlines/extglob improved; plain-glob regex is exponential and the public engine recurses on 1,500 literals. |
| H8 heredoc input has two cursors | **Live** | `eval 'read x; cat' <<EOF` replays bytes already consumed by `read`: [`file_redirect.py:207`](../../psh/io_redirect/file_redirect.py#L207), [`manager.py:545`](../../psh/io_redirect/manager.py#L545). |
| H9 function definitions excluded from ordinary grammar | **Live** | Both parsers reject a function in `&&`, a pipeline, background list, or `!`: [`statements.py:28`](../../psh/parser/recursive_descent/parsers/statements.py#L28). |
| H10 POSIX special resolution is inconsistent | **Live** | Resolver picks `eval`, but raw-name function preclassification later discards its persistent prefix assignment: [`command.py:481`](../../psh/executor/command.py#L481), [`command.py:562`](../../psh/executor/command.py#L562). |
| H11 background pipeline signals | **Live** | Background pipeline member inherits the wrong SIGINT behavior and returns 130 where bash returns zero: [`process_launcher.py:258`](../../psh/executor/process_launcher.py#L258), [`pipeline.py:261`](../../psh/executor/pipeline.py#L261). |
| H12 foreground subshell lifecycle | **Live** | Direct foreground subshell wait/report bypasses the common lifecycle and omits the shell diagnostic on signal death: [`subshell.py:177`](../../psh/executor/subshell.py#L177). |
| H13 shadowing unset local falls through to env | **Live** | Tombstone becomes `None`, then lookup consults exported `env`: [`scope.py:389`](../../psh/core/scope.py#L389), [`state.py:854`](../../psh/core/state.py#L854). |
| H14 script files eagerly read to EOF | **Live** | `FileInput` reads all content before yielding; a FIFO command does not execute until the writer closes: [`input_sources.py:93`](../../psh/scripting/input_sources.py#L93). |
| H15 multiline completeness is quadratic | **Live, documented as accepted** | Accumulator reparses the whole growing buffer: [`command_accumulator.py:174`](../../psh/scripting/command_accumulator.py#L174); `HeredocLexer` also rejoins/relexes pending lines. |
| H16 malformed UTF-8 corrupts later records | **Live** | `c3 41 0a 42 0a` cascades replacement characters and consumes the second record: [`input_reader.py:291`](../../psh/builtins/input_reader.py#L291). |
| H17 `-ic` suppresses interactive startup | **Live** | Interactive flags are present but rc loading is gated away for command mode at [`shell.py:286`](../../psh/shell.py#L286). |
| H18 locale behavior is process-global | **Live, broader** | The newest service becomes module-global and calls libc `setlocale`: [`locale_service.py:107`](../../psh/core/locale_service.py#L107), [`locale_service.py:279`](../../psh/core/locale_service.py#L279). |
| H19 `disown -h`/detached reaping | **Live** | `-h` remains an acknowledged no-op and a completed disowned child can remain defunct: [`disown.py:107`](../../psh/builtins/disown.py#L107). |

The important result is not the count alone. Twenty-five releases removed the
critical issue and improved several components, yet none of the high categories
was fully retired. A release campaign should close findings with executable
regression pins, not infer closure from nearby refactoring.

## Newly sharpened high findings

### A. Startup input runs before invocation configuration is complete

[`__main__.py:376`](../../psh/__main__.py#L376) constructs `Shell`, which loads
an rc file, before `main()` has applied all invocation options at line 398,
selected and validated the parser at line 402, or installed `-s` positional
parameters at line 457. Fresh probes show:

- under `--rcfile probe -u -i -s`, bash exposes `u` in the rc and body; PSH
  exposes it only in the body;
- under `--parser combinator`, the rc reports recursive descent while the body
  reports combinator;
- under `-i -s A B`, the rc sees no positional parameters while the body sees
  `A B`;
- an invalid parser name still runs the rc before PSH exits 2.

This is an object-construction bug. Parse and validate an immutable
`InvocationConfig`, seed parser/options/mode/`$0`/positionals, then construct or
start a shell. No startup input should observe a half-configured invocation.

### B. Multiple `Shell` instances cannot own process-global resources safely

The public object model permits multiple shells, but each instance independently
leases resources that are process-global:

- overlapping trap leases restore out of order at
  [`trap_manager.py:115`](../../psh/core/trap_manager.py#L115);
- `exec >file` rebinds fd 1 and `sys.stdout` process-wide at
  [`file_redirect.py:615`](../../psh/io_redirect/file_redirect.py#L615), so a
  second shell writes to the first shell's file, and `close()` intentionally
  does not restore streams at [`shell.py:334`](../../psh/shell.py#L334);
- `cd` calls `os.chdir` at
  [`navigation.py:173`](../../psh/builtins/navigation.py#L173), leaving another
  shell with stale `PWD`;
- locale construction mutates libc and a module-global active service, so
  constructing a C-locale shell changes an existing UTF-8 shell's character
  class results.

Choose and enforce one contract. Either `Shell` is single-active and rejects a
second live instance, or process resources require an owner/coordinator with
stack-safe leases. Independent instance-local managers cannot make global state
composable.

### C. The parser facade drops context and reusable combinator parsers leak state

[`parse_with_heredocs()`](../../psh/parser/__init__.py#L70) accepts
`lexer_options` but drops them on the combinator branch; `create_parser()` drops
`source_text`, `line_offset`, and `lexer_options` at
[`parser/__init__.py:93`](../../psh/parser/__init__.py#L93). A command
substitution containing extglob parses under recursive descent but fails under
the combinator because nested `WordBuilder` falls back to no options and offset
zero.

Separately, `ParserCombinatorShellParser` retains `heredoc_contents` on the
instance at [`parser.py:48`](../../psh/parser/combinators/parser.py#L48). Reuse
after `parse_with_heredocs()` lets a later plain parse with the same generated
key receive the first parse's body. An empty heredoc map is silently accepted,
where recursive descent rejects the missing body.

The facade should carry one immutable `ParseContext`, and heredoc contents must
be a per-call input consumed transactionally and cleared in `finally`.

### D. The educational combinator algebra violates its own laws

In [`combinators/core.py`](../../psh/parser/combinators/core.py), `map()` and
`then()` reset failure position rather than preserving the deepest failure;
`optional()` converts committed failure to success; and `many()` has no
success-without-progress guard. `many(optional(token("WORD")))` on empty input
does not terminate.

These are latent rather than common production-path faults, but they are high
for a codebase graded as textbook-quality: the public primitives teach invalid
parser laws and can hang any future grammar using an ordinary composition.
Pin algebraic law tests before extending the combinator grammar.

### E. Plain glob matching remains exponentially backtracking

[`pattern.py:85`](../../psh/expansion/pattern.py#L85) describes the plain regex
path as fast; the performance test at
[`test_pattern_engine_performance.py:91`](../../tests/performance/benchmarks/test_pattern_engine_performance.py#L91)
uses only the easy pattern `a*b` and calls it linear. The adversarial plain
pattern `("*a" * n) + "b"` against `"a" * (2*n)` measured:

```text
n=10   0.0045s
n=12   0.0732s
n=14   1.1624s
```

The memoized engine solved extglob's cliff, not plain glob's. Route all shell
patterns through an iterative state machine and add adversarial scaling, not
only long easy inputs. Also remove recursion from
[`pattern_engine.py:224`](../../psh/expansion/pattern_engine.py#L224); the public
extglob matcher raises `RecursionError` on 1,500 literals.

### F. The green-evidence chain can still report false success

`classify_phase_result()` explicitly says no unrelated internal error may be
accepted, but the xdist exception at
[`run_tests.py:199`](../../run_tests.py#L199) checks only that the known
`cannot send (already closed?)` substring is present and a clean summary exists.
This transcript returns success:

```text
==== 10 passed in 0.1s ====
INTERNALERROR> ... cannot send (already closed?)
INTERNALERROR> RuntimeError: unrelated collection failure
```

The 28-test hardening suite passes because it covers the benign race and a bare
internal error separately, not their combination. Do not translate pytest exit
3 to zero. If the exception must remain, parse and reject every additional
internal-error block rather than relying on a summary line.

The governance layer compounds this: per-PR CI is explicitly disabled at
[`tests.yml:3`](../../.github/workflows/tests.yml#L3), while a version bump on
main is tagged unconditionally by
[`release-tag.yml:9`](../../.github/workflows/release-tag.yml#L9). The project
may intentionally use a local gate, but the release workflow has no machine
check that the claimed gate ran or passed.

### G. Conformance infrastructure can call identical harness failures conformant

[`run_in_shell()`](../../tests/conformance/conformance_framework.py#L125) catches
any exception and converts it to exit 127 plus `Execution error`. The analyzer
checks byte-for-byte identity before error status at
[`conformance_framework.py:239`](../../tests/conformance/conformance_framework.py#L239).
Two synthetic `[Errno 24] Too many open files` results therefore classify as
`IDENTICAL`.

Represent harness failure as a distinct tagged result or raise it. Timeouts,
spawn failures, decode failures, and missing executables are not shell behavior
and must be rejected before comparison.

### H. Locale initialization strips genuine inherited state

[`state.py:978`](../../psh/core/state.py#L978) deletes
`LC_CTYPE=C.UTF-8` whenever Python UTF-8 mode is set, treating that combination
as proof of PEP 538 coercion. With explicit `LC_ALL=C`, however, the inherited
`LC_CTYPE=C.UTF-8` is genuine. PSH removes it; bash preserves it, and later
unsetting `LC_ALL` therefore produces different character-class behavior.

This is the source of the three independently reproducible gate failures. The
conformance harness makes it host-sensitive by copying every inherited locale
variable at
[`conformance_framework.py:133`](../../tests/conformance/conformance_framework.py#L133)
and overwriting only `LC_ALL` and `LANG`. Preserve `LC_CTYPE` whenever a
nonempty `LC_ALL` proves coercion could not have supplied it, and construct a
hermetic test environment by removing all inherited `LC_*` variables before
adding the case-specific values.

## Additional medium findings

1. **Invocation short options are contradictory.**
   [`__main__.py:47`](../../psh/__main__.py#L47) hardcodes only `euxvnfCB`
   although the option registry contains `a`, `b`, `h`, `m`, `E`, and `T`;
   `+i` forces interactivity, `-s/+s` is lost with `-c`, and PSH reserves `-h`
   for help where bash treats it as `hashall`. Derive the surface from the
   registry plus an explicit invocation-only sign table.

2. **Rc execution is not sourced-file execution.**
   [`rc_loader.py:25`](../../psh/interactive/rc_loader.py#L25) calls the generic
   source pipeline without source depth, `FunctionReturn`, or `RETURN`-trap
   handling. `return 7` in an rc diagnoses a top-level return and then executes
   the rest, unlike bash. Share one sourced-file execution service.

3. **Multiple analysis flags silently suppress work.**
   `--format --security` formats and returns zero on an unsafe script because
   [`visitor_modes.py:152`](../../psh/scripting/visitor_modes.py#L152) chooses a
   fixed first mode. Reject conflicting modes or run and aggregate all requested
   modes.

4. **Analysis uses initial-state syntax for the whole file.**
   [`visitor_modes.py:18`](../../psh/scripting/visitor_modes.py#L18) parses one
   buffer. A first-line `shopt -s extglob` enables line two during execution,
   but `--validate` rejects line two. Analysis needs a state-transition model or
   a documented syntax-only option policy.

5. **NUL source handling differs by channel.** Binary detection examines only
   the prefix before the first newline; later NUL reaches execution, validation,
   and formatting with three different outcomes. Normalize program bytes once
   for file, stdin, source, rc, and analysis paths.

6. **Dynamic special variables bypass lexical scopes.** Special-first lookup at
   [`scope.py:371`](../../psh/core/scope.py#L371) makes `local SECONDS=x`
   unreachable and allows `local SHELLOPTS=x` despite readonly semantics.
   Dynamic specials need scope-aware cells, not a global prelookup.

7. **`$!` is always considered set.** Raw expansion returns empty and bypasses
   nounset, while parameter operators report set at
   [`operators.py:162`](../../psh/expansion/operators.py#L162). Store absence as
   absence and apply the ordinary setness rules.

8. **Associative scalar view ignores key `0`.**
   [`AssociativeArray.as_string()`](../../psh/core/variables.py#L318) always
   returns empty, although bash treats `$assoc` as `${assoc[0]}`. This is also
   independently identified in #21's associative-array cluster.

9. **`export -f` reports success without exporting.** Function metadata records
   the flag, but child environments never serialize/import functions. Implement
   a validated protocol or reject the unsupported operation.

10. **Alias validation and same-line extraction disagree.** Digit/keyword names
    accepted by bash are rejected at
    [`aliases.py:329`](../../psh/expansion/aliases.py#L329), while a dotted alias
    accepted on one line is mis-extracted as `=echo` at
    [`aliases.py:179`](../../psh/expansion/aliases.py#L179).

11. **`printf %a/%A` ignores precision.**
    [`printf_formatter.py:425`](../../psh/utils/printf_formatter.py#L425) says so
    explicitly: `printf '%.2a' 3.14` emits the full mantissa instead of bash's
    rounded `0x1.92p+1`.

12. **Four live-bash tests hardcode `/opt/homebrew/bin/bash`.** The files are
    collected by the Ubuntu nightly with no skip, so they fail before testing
    behavior. Use the shared `find_bash()` fixture in process-substitution,
    closed-pipeline, long-pipeline, and env-isolation tests.

13. **Golden bash comparison ignores stderr.** It compares stdout and status at
    [`test_golden_behavior.py:139`](../../tests/behavioral/test_golden_behavior.py#L139),
    even though both runners capture stderr. Compare normalized diagnostics or
    qualify the feature as stdout/status-only.

14. **Normal and nightly gates omit meaningful suites.** `pytest.ini` ignores
    all 18 performance tests; 63 interactive tests require
    `--run-interactive`, which nightly never supplies. The explicit performance
    run is green, but the pathological parsing case is one xfail containing
    three sequential checks, and the classes named `TestMemoryUsage` do not
    measure memory.

15. **Testing documentation names a nonexistent subshell phase.**
    [`testing_source_of_truth.md:32`](../testing_source_of_truth.md#L32) says the
    standard tier has parallel, serial, and subshell phases. The runner has only
    Phase 1 and Phase 1b; subshell tests are ordinary collected tests.

16. **The runner uses `python`, not its own interpreter.**
    [`run_tests.py:495`](../../run_tests.py#L495) should use `sys.executable`.
    Its positional `pytest_args` is also misleading: documented-looking
    `--quick -k expr` is rejected unless the caller knows to insert `--`.

## Architectural remediation

### P0: restore trustworthy evidence

1. Remove the exit-3-to-success translation and tag conformance harness errors.
2. Replace hardcoded bash paths and run the Linux nightly configuration locally
   or in a required CI job.
3. Make auto-tagging depend on an attested green gate; add the omitted
   performance and PTY tiers on an appropriate schedule.
4. Add regression pins for every #20 high category before declaring it closed.

### P1: repair semantic models

1. Introduce immutable `InvocationConfig` and finish configuration before rc or
   history input.
2. Carry one structured expansion IR with field identity and per-character
   quote/glob protection through splitting and pathname expansion.
3. Resolve a command once into a typed result containing precedence, kind,
   assignment persistence, and execution strategy.
4. Replace duplicate heredoc input representations with one cursor and enforce
   delimiter FIFO in one collector.
5. Preserve program-source structure for every nested grammar region; do not
   defer syntax-bearing text as raw strings.
6. Decide whether `Shell` is single-active or implement a process-wide resource
   coordinator for signals, cwd, locale, and permanent descriptors.

### P2: make secondary implementations honest

1. Carry `ParseContext` through both parser implementations and make parser
   calls stateless.
2. Fix and law-test combinator primitives before using them as an educational
   API.
3. Route plain glob through the iterative memoized engine and add adversarial
   scaling/recursion guards to the normal gate.
4. Either run analysis through stateful logical units or explicitly limit it to
   an option-independent grammar.
5. Converge rc/source, option registries/CLI parsing, and byte normalization on
   one implementation each.

## Final judgement

PSH is a strong and unusually ambitious shell implementation with multiple
textbook-grade chapters. The v0.724 tree is cleaner than v0.698 and no longer
contains the critical redirect injection defect. It is still **B- overall** as
a combined correctness/textbook artifact because high-impact semantics remain
wrong across syntax timing, expansion boundaries, descriptor order, process
ownership, input bytes, and job control, while the release evidence can mask
or omit failures.

The route to an A is not broader feature work. It is to make the existing
semantic boundaries authoritative, composable, and executable as regression
contracts.

## Review-index validation

This report, #20, and #21 are registered in `docs/reviews/README.md`.
`git diff --check` and the reviews-index meta-test passed. The quick tier passed;
the full canonical gate failed as recorded above, and its four affected files
were rerun independently to classify the failures.
