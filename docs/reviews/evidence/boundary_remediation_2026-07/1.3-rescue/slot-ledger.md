# Slot 1.3 ledger — Test hygiene: races, skip-on-failure, flakes, documented-difference integrity

- **Worktree:** /Users/pwilson/src/psh-r1-3  **Branch:** fix/remediation-1-3
- **Base SHA:** `491b0e30` (v0.752.0, tip of slot 1.2 merge)
- **Oracle:** `/opt/homebrew/bin/bash` `5.2.26(1)-release` (PATH bash, never /bin/bash)
- **Discriminator verified:** from the worktree, `python -c 'import psh; print(psh.__file__)'`
  → `/Users/pwilson/src/psh-r1-3/psh/__init__.py`, version 0.752.0.
  (Counter-check: from a FOREIGN cwd the same import resolves
  `/Users/pwilson/src/psh/psh/__init__.py` — the MAIN tree. This bit item 2b;
  see the PYTHONPATH pin there.)

## Commits

| # | SHA | Item |
|---|---|---|
| 1 | `a8d51c67` | MEDIUM-13 background-subshell race |
| 2 | `ec97e318` | 2a — loud oracle resolution in 9 modules |
| 3 | `3546629a` | 2b — script-file cases off `<repo>/tmp` |
| 4 | `1090bc80` | 2b census — remaining `<repo>/tmp` dependants |
| 5 | `ac990f1a` | item 2 — skip-on-failure conversions |
| 6 | `624c74ea` | carry #8 — timeformat %P flake |
| 7 | `df46186a` | flake (d) — background-pipeline races |
| 8 | `17da560c` | flakes (b) and (c) — reproduction attempts + hardening |
| 9 | `9e5c002f` | F1 behavior-aware classification + F2 catalog hygiene |
| 10 | `de18ca4d` | keep F1's side lookups clear of the E2 oracle ratchet |
| 11 | `97b7c98d` | finish the OTHER-class census — 11 more vacuous guards |
| 12 | `5616001a` | round-1 bounce fixes — blockers 2/3/4 + 6-series |
| 13 | `7672b426` | probe-method audit — two conversion docstrings made precise |
| 14 | `a0afc9ed` | round-2 fixes — F1 anti-bypass hole + 6 nits |

**FINAL TIP: `a0afc9ed`** — 14 commits from base `491b0e30`.
Reproduce this list: `git log --oneline --reverse 491b0e30..HEAD`.

### Tip-discipline incident (round-1 blocker 1) — recorded, not glossed

Round 1 bounced partly because I declared "FINAL TIP `de18ca4d`, no
post-report commits" and then committed `97b7c98d` 23 minutes later. Every
number in that report (gate 3, the +12 delta, "census sweep closed") described
a SUPERSEDED tree, and the census claim was materially wrong: `97b7c98d` fixed
**11 more** vacuous guards, so the sweep was not closed when I said it was.

The rule I broke, restated: declared-final means final. If something surfaces
after the report, REPORT FIRST and commit only after acknowledgement. This is
the second slot in a row to hit it (1.2 bounced on the same thing), so it is a
campaign pattern, not a one-off slip. Full order:
`git log --oneline 491b0e30..HEAD`.

## ⇢ RESCUE-CARRY 1 — background-subshell redirect (campaign LEDGER Part D)

**INTEGRATOR RULING (received at the MEDIUM-13 milestone):** latent production
inconsistency, exposed by the harness, NOT reachable from the CLI (where
`sys.stdout` is always fd 1), and NOT this slot's to fix. To be registered as a
new campaign-LEDGER **Part D row** at ceremony. Owner: successor queue.
**Discharge trigger:** *any slot that touches `_execute_background_subshell` /
`run_background_shell_child` discharges or re-carries this with the evidence
matrix below.* The load-bearing fact for the row is the **foreground-vs-
background asymmetry** — two child paths sharing streams identically, only one
honoring dup2 — which makes it an internal inconsistency regardless of CLI
reachability.

Everything below is the verbatim evidence for the row.

Backgrounded SUBSHELL + redirect does not honour the redirect when the shell's
Python-level stdout is not bound to fd 1. Matrix, all replayed at base:

| Context | Command | Result |
|---|---|---|
| in-process, pytest fd capture ON | `(echo A; echo B) > f &` | f EXISTS but EMPTY; output in captured stdout — **WRONG** |
| in-process, capture ON | `(echo A; echo B) > f` | `A\nB\n` — right |
| in-process, capture ON | `echo A > f &` | `A\n` — right |
| in-process, capture OFF (`-s`) | `(echo A; echo B) > f &` | `A\nB\n` — right |
| real subprocess `psh -c '... & wait'` | `(echo A; echo B) > f &` | `A\nB\n`, stdout empty — right |

Reproduces only when `sys.stdout` is decoupled from fd 1, which in production
it never is — so "harness artifact" vs "latent production defect the harness
exposes" is a genuine judgement call, left to the integrator.

Pointer (a pointer, not a proven root cause):
`psh/executor/subshell.py#_execute_background_subshell` shares the parent's
Python stream objects with the child (`subshell.stdout = self.shell.stdout`,
:254-256); a dup2-based redirect on fd 1 is bypassed when that object is not
fd 1. The foreground twin `#_execute_foreground_subshell` shares streams
identically (:144-146) yet behaves correctly under the same capture, so the
divergence is in the surrounding child-runner path, not the sharing.

**Zero psh/ production changes in this slot.**

## ⇢ RESCUE-CARRY 2 — psh `%P` CPU percentage (campaign LEDGER Part D)

**INTEGRATOR RULING:** correctly NOT fixed in this slot. To be registered as a
campaign-LEDGER **Part D row** at ceremony; owner: successor queue, candidate
quick rider at Checkpoint R. **Priority: outranks Rescue-carry 1 — this one IS
CLI-reachable, via `TIMEFORMAT`.**

Verbatim captured evidence. Command (identical to both shells):

```
TIMEFORMAT="R=%R U=%U S=%S P=%P"; { time true; } 2>&1
```

| Shell | Observation |
|---|---|
| **psh** (exploding sample) | `R=0.000 U=0.010 S=0.000 P=11934.31` |
| **bash 5.2.26** | `R=0.000 U=0.000 S=0.000 P=2.02` (also 1.97, 2.44, 1.75, 2.55 over 5 runs) |

Rate, measured on an **idle** host — this is not a load artifact:

```
$ for i in $(seq 1 30); do python -m psh -c 'TIMEFORMAT="p=%P"; { time true; } 2>&1'; done | sort | uniq -c
  28 p=0.00
   1 p=11822.71
   1 p=11577.45
```

bash over the same 30 runs stays in a ~1.8–3.9 band and never exceeds one
digit before the decimal.

**Mechanism (arithmetic, not speculation):** `%P` is `(user+sys)/real*100`.
psh's user time is accounted in 10 ms ticks, so when a tick lands inside a
sub-millisecond `time true` the numerator is 0.010 against an elapsed of
~84 µs: `0.010 / 0.0000838 * 100 ≈ 11930`, matching the captured 11934.31.
bash reports `U=0.000` for the same command, so its ratio stays small.

**User-visible consequence:** any script reading `%P` from `TIMEFORMAT` can see
a CPU percentage wrong by four orders of magnitude. Nothing in this slot fixes
it; slot 1.3 only stopped the TEST from pinning the digit width (carry #8).

## Item 1 — MEDIUM-13 (commit `a8d51c67`)

Re-located at base: `tests/integration/subshells/test_subshell_basics.py:161-176`
(#22's coordinates held).

**RED-ON-BASE, REPLAYED.** Base body run verbatim under the tests tree with the
background subshell slowed so the race is lost deterministically:

```
$ python -m pytest tests/integration/subshells/test_zz_medium13_vacuity_demo.py -q -s
VACUITY-DEMO: file_existed=False content=''
1 passed in 0.03s
```

Passing while asserting nothing about the output IS the defect. (Demo file
removed after; body preserved at `tmp/medium13_vacuity_demo.py`.)

**Fix.** Subprocess; `wait` as the deterministic hand-off through the shell's
own job API, no sleeps; `@pytest.mark.timeout(60)` + a 30 s subprocess timeout
as the bounded deadline; assertions UNCONDITIONAL — file exists, content equals
bash's exact bytes, and `stdout == ""`.

> **DO NOT "SIMPLIFY" THIS BACK TO THE IN-PROCESS FIXTURE.** (Integrator ruling:
> "approved as executed… note that justification in the ledger explicitly, so a
> future reader doesn't simplify it back to in-process.") Two independent
> reasons: (1) a backgrounded subshell writing through a redirect is
> **process-lifecycle behavior**, which this project's own test-writing
> guidance puts in a subprocess; (2) the in-process fixture **cannot observe
> it at all** — under pytest's fd capture the output reaches the captured
> stream and the file is left EMPTY (Rescue-carry 1). An in-process version of
> this test can only be vacuous or wrong.

**Bounded-deadline check (integrator-requested — is the mark inert?).**
`pytest-timeout` is installed AND the mark genuinely binds; verified
empirically rather than by checking for the package, since a missing plugin
would make the mark silent decoration:

```
@pytest.mark.timeout(1)
def test_...(): time.sleep(5)
->  E   Failed: Timeout (>1.0s) from pytest-timeout.
    1 failed in 1.03s
```

So the mark is a REAL bound, not decoration, and it stays. The 30 s
`subprocess.run(timeout=...)` is the inner bound; the mark is the outer one.

Expected content pinned against live bash FIRST: both shells produce
byte-identical `background subshell\ndone\n` (`od -c`).

**NON-VACUITY, replayed by mutation against the real file:**

| Mutation | Result |
|---|---|
| drop the redirect | FAILS at `out_file.exists()` |
| wrong expected content | FAILS: `'background subshell\ndone\n' == 'WRONG\n'` |

Recorded because it would have been an easy false proof: my FIRST mutation
(removing `wait`) still PASSED (5.14 s) — psh `-c` waits for background jobs
before exiting, so that mutation does not discriminate.

**Exit criterion — repeated and shuffled runs (`tmp/m13_repeat.sh`):**
neither pytest-repeat nor pytest-randomly is installed here, so repetition is
process-level and shuffling permutes node IDs.

```
=== PHASE 1: 50 sequential module runs ===
PHASE 1 complete: 0 failure(s) in 50 runs
=== PHASE 2: 25 shuffled-order runs ===
collected 15 node ids
PHASE 2 complete
=== TOTAL FAILURES: 0 (0 = exit criterion met) ===
```

### Census — same pass-without-assertion shape

Tool: `tmp/census_guarded_assert.py` (AST). Flags asserts inside an `if` with
NO `else` whose predicate reads runtime state the code under test produces;
cleanup guards (`if exists(d): rmtree(d)`) contain no assert and are not
flagged, and an `else` means the negative path is handled.

```
$ python tmp/census_guarded_assert.py tests
[STATE] tests/integration/subshells/test_subshell_basics.py:172: test_subshell_with_background_jobs   if os.path.exists('bg_output.txt'):
--- STATE-guarded asserts: 1 ---
--- OTHER-guarded asserts: 40 ---
```

The STATE class has **exactly one member tree-wide** — MEDIUM-13 itself; that
sweep is closed. The 40 OTHER hits were hand-classified: see the full per-hit
table below. **14** were the same vacuous "only assert if it worked" shape and
were ALL converted — 3 in `ac990f1a` (item 2) and 11 in `97b7c98d`.

(An earlier revision of this ledger said "Four were converted", written when
only the first three plus one more had been done. It described a superseded
tree — the same tip-discipline failure recorded at the top. The table below is
the authority.)

**A number NOT to mistake for a finding:** a first, coarser census
(`tmp/census_conditional_assert.py`, "every assert in the function is
conditional") reported 211 + 226 hits. It flags loops over literal case
tables and is not a defect count. Recorded so it is not later cited as one.

### The 40 OTHER-guarded hits — full per-hit classification (integrator-requested)

Classes: **(i)** vacuous-supported-feature → FIXED; **(ii)** legitimate
conditional (environment/platform/API-shape gate) → left, reason given;
**(iii)** loop-over-case-table / data-driven false positive → left.

Base census output: `tmp/census-guarded-assert.txt`. Tip: `tmp/census-guarded-assert-tip.txt`.

| # | Site | Guard | Class | Verdict |
|---|---|---|---|---|
| 1 | `test_golden_behavior.py:99` | `if expected_stdout is not None:` | iii | YAML case may omit an expectation; `None` means "not pinned". |
| 2 | `test_golden_behavior.py:107` | `if expected_stderr is not None:` | iii | Same. |
| 3 | `test_reappraisal7_close_output_fd_conformance.py:149` | `if expect_out is not None:` | iii | Parametrized optional expectation. |
| 4 | `test_arrays_comprehensive.py:393` | `if result == 0:` | **i** | **FIXED** — C-style for loop matches bash; unconditional. |
| 5 | `test_arrays_comprehensive.py:509` | `if result == 0:` | **i** | **FIXED** — 100-element array; content pinned `== '100'`. |
| 6 | `test_while_loops.py:182` | `if exit_code == 0 and 'done' in out:` | **i** | **FIXED** — `break 2` matches bash; rc + output pinned. |
| 7 | `test_quoting_escaping.py:541` | `if result['success']:` | **i** | **FIXED** — arrays supported; `success` now asserted. |
| 8 | `test_word_splitting.py:333` | `if result['success']:` | **i** | **FIXED** — same. |
| 9 | `test_enhanced_test_word_operands.py:119` | `if setup:` | iii | Optional per-row setup command in the case table. |
| 10 | `test_enhanced_test_word_operands.py:165` | `if setup:` | iii | Same. |
| 11 | `test_multiline_history.py:72` | `if 'greet()' in cmd:` | iii | Selects the matching entry while walking history. |
| 12 | `test_enhanced_validator_comprehensive.py:532` | `if ast:` | **i** | **FIXED** — empty input parses to a Program; asserted. |
| 13 | `test_enhanced_validator_comprehensive.py:552` | `if result.ast:` | **i** | **FIXED — WAS 100% DEAD.** See the finding below. |
| 14 | `test_combinator_random_differential.py:356` | `if rd_kind == 'ok':` | iii | Branches on the generated case's own kind. |
| 15 | `test_parsing_performance.py:226` | `if size == 10000:` | iii | Loop over sizes; extra check at the largest. |
| 16 | `test_invocation_matrix.py:206` | `if psh_stderr_contains is not None:` | iii | Parametrized optional expectation. |
| 17 | `test_nul_channel_matrix.py:187` | `if psh_stderr_contains is not None:` | iii | Same. |
| 18 | `test_source_service_matrix.py:196` | `if psh_stderr_contains is not None:` | iii | Same. |
| 19 | `test_parser_visualization.py:238` | `if '├──' in line or ...:` | iii | Selects tree-branch lines while walking output. |
| 20 | `test_disown_builtin.py:85` | `if pid and pid.isdigit():` | ii | Guards on whether a real bg pid was captured — process-availability gate. |
| 21 | `test_disown_builtin.py:187` | `if exit_code == 0:` | **i** | **FIXED** — real rc is 2, so the guard NEVER fired and the test asserted nothing. Now pins rc 2 + usage text. |
| 22 | `test_disown_builtin.py:386` | `if '[1]' in out or '[2]' in out:` | ii | Job-table content depends on live jobs. |
| 23 | `test_disown_builtin.py:389` | `if fmt in ['%1','%+'] and ...:` | iii | Per-format branch inside the case loop. |
| 24 | `test_function_builtins.py:53` | `if exit_code != 0:` | **i** | **FIXED** — `return` outside a function: rc 2 + bash's exact message. |
| 25 | `test_function_builtins.py:146` | `if exit_code == 0:` | **i** | **FIXED** — `readonly -f`: refusal rc 1, original body survives. |
| 26 | `test_getopts_builtin_broken.py:24` | `if 'getopts' in output.lower():` | ii | Guard DOES fire today (psh prints usage), so the inner assertion is live — weak but not vacuous. Module is named `_broken` (known-weak); left alone deliberately rather than widen this slot's blast radius. |
| 27 | `test_getopts_builtin_broken.py:480` | `if result != 0:` | ii | Guard fires today (rc 1); assertion live. Same module note. |
| 28 | `test_executor_visitor_basic.py:185` | `if expected_output:` | iii | Parametrized optional expectation. |
| 29 | `test_parameter_expansion.py:312` | `if out != '${TEXT^}':` | **i** | **FIXED** — `${var^}` matches bash; asserted. |
| 30 | `test_parameter_expansion.py:322` | `if out != '${TEXT^^}':` | **i** | **FIXED** — `${var^^}`. |
| 31 | `test_parameter_expansion.py:332` | `if out != '${TEXT,}':` | **i** | **FIXED** — `${var,}`. |
| 32 | `test_parameter_expansion.py:342` | `if out != '${TEXT,,}':` | **i** | **FIXED** — `${var,,}`. |
| 33 | `test_frozen_token_and_sourcemap.py:64` | `if tok.type == WORD:` | iii | Token-kind dispatch while walking a token stream. |
| 34 | `test_modular_lexer_integration.py:198` | `if result is not None:` | ii | `registry.recognize()` legitimately returns `None`; the test asserts the negative case ("must NOT be DOUBLE_RBRACKET") only when a token came back. API-shape gate. |
| 35 | `test_token_recognizers_comprehensive.py:132` | `if result is not None:` | ii | Same API shape. |
| 36 | `test_token_recognizers_comprehensive.py:372` | `if result is not None:` | ii | Same API shape. |
| 37 | `test_ast_canonical_invariants.py:293` | `if isinstance(node, CasePattern):` | iii | Node-type dispatch while walking every AST node. |
| 38 | `test_function_def_as_pipeline_component.py:129` | `if p is rd:` | iii | Per-parser branch (RD vs combinator) inside the loop. |
| 39 | `test_run_tests_hardening.py:422` | `if shutil.which('pgrep'):` | ii | Missing-binary environment gate — exactly the kind that STAYS. |
| 40 | `test_formatter_roundtrip.py:85` | `if stripped in ('else','fi','done') ...:` | iii | Selects keyword lines while walking formatted output. |

**Totals: (i) 14 — ALL FIXED. (ii) 8 — left, reasons above. (iii) 18 — left.**

Census re-run at tip confirms the fixes landed and nothing regressed:

```
$ python tmp/census_guarded_assert.py tests
--- STATE-guarded asserts: 0 ---     (was 1 — MEDIUM-13)
--- OTHER-guarded asserts: 26 ---    (was 40 — the 14 class-(i) conversions)
```

#### Finding inside the census: a test that was 100% DEAD

`test_enhanced_validator_comprehensive.py::test_malformed_constructs` read
`result.ast` inside its loop, and `result` is **not defined in that scope**.
Every iteration raised `NameError` straight into `except Exception: pass`, so
the validator was **never invoked once**. Replayed:

```
'echo':   SWALLOWED NameError: name 'result' is not defined
'$':      SWALLOWED NameError: name 'result' is not defined
'echo $': SWALLOWED NameError: name 'result' is not defined
```

`ruff check` does NOT catch it (F821 undefined-name is not enabled in this
tree) — worth noting, since a linter rule would have. All three inputs parse
cleanly and the validator runs on them, so the swallowing handler is gone and
each case is asserted.


## Item 2a — silent skip on a missing oracle (commit `ec97e318`)

Re-enumerated at base — matches the 1.2-rescue record exactly:

```
$ grep -rln 'try_resolve_bash' tests/ --include='*.py'
tests/harness/gen_census.py                 (tool: pattern-matches the name)
tests/harness/shell_oracle.py               (DEFINES it)
tests/system/interactive/test_multiline_immediate_error_i3.py
tests/system/invocation/test_invocation_matrix.py
tests/system/invocation/test_startup_order.py
tests/system/source_service/test_nul_channel_matrix.py
tests/system/source_service/test_source_service_matrix.py
tests/system/test_posix_invocation.py
tests/unit/core/test_tempenv_visibility_ledger.py
tests/unit/executor/test_command_resolution_r3.py
tests/unit/expansion/test_pattern_engine_differential.py
tests/unit/tooling/test_shell_oracle_harness.py   (TESTS the resolver)
```
→ 12 files, of which **9 are the modules owed** (3 legitimate).

Also swept for the guard shape independently: **19 guard sites**, all inside
those same 9 modules — no others.

**Command CORRECTED (round-2 nit).** The single-line grep I first recorded
reproduces **18**, not 19: the guard at
`tests/unit/core/test_tempenv_visibility_ledger.py:27-28` is written across TWO
lines (`pytest.mark.skipif(` / `_ORACLE is None, reason=...`) and escapes any
line-oriented pattern. A multiline-aware count reproduces the recorded 19:

```
$ python - <<'EOF'   # per-file, regex spanning the line break
import subprocess, re
files = subprocess.run(['git','grep','-l','skipif','491b0e30','--','tests/'],
                       capture_output=True, text=True).stdout.split()
for ref in files:
    path = ref.split(':',1)[1]
    src = subprocess.run(['git','show',f'491b0e30:{path}'],
                         capture_output=True, text=True).stdout
    n = len(re.findall(r'skipif\(\s*(?:\n\s*)?(?:_ORACLE|BASH) is None', src))
    if n: print(f"{path}: {n}")
EOF
tests/system/invocation/test_invocation_matrix.py: 1
tests/system/invocation/test_startup_order.py: 8
tests/system/source_service/test_nul_channel_matrix.py: 1
tests/system/source_service/test_source_service_matrix.py: 1
tests/system/test_posix_invocation.py: 4
tests/unit/core/test_tempenv_visibility_ledger.py: 1
tests/unit/executor/test_command_resolution_r3.py: 2
tests/unit/expansion/test_pattern_engine_differential.py: 1
TOTAL oracle-absence skipif guards at base: 19
```

(The conversion itself removed 5 module guards + 14 decorators = 19, so the
count was right; only the recorded command was too narrow to show it.)

**RED-ON-BASE, REPLAYED.** Resolver ladder stubbed via `tmp/no_oracle_plugin.py`
(BASH_PATH cleared, Homebrew paths made non-files, `shutil.which('bash')`
→ None, cached resolution dropped):

```
$ PYTHONPATH=tmp:tests/harness python -m pytest -p no_oracle_plugin <the 8 marker modules> -q
29 passed, 191 skipped in 0.63s        <- EXIT 0. Green while 191 differentials never ran.
```

**TIP, same command, all 9 modules:**

```
9 errors in 0.16s
ERROR ... - shell_oracle.BashOracleUnavailable...
!!!!! Interrupted: 9 errors during collection !!!!!
```

Loud at import, as the 1.2 ruling requires.

Conversion: 5 module-scope `pytestmark` guards + 14 decorator guards removed;
`try_resolve_bash` → `resolve_bash`; the 9th module
(`test_multiline_immediate_error_i3`, in-test `pytest.skip`) hoisted to a
module-scope `_ORACLE = resolve_bash()` so ITS import raises too.

**No tests lost or gained:** collection is **225 at base and 225 at tip**
(`--collect-only`, oracle present); 225 pass at tip.

## Item 2b — repo-tmp fresh-worktree dependency (commits `3546629a` + census follow-up)

**REPRODUCED at base** in a genuinely fresh worktree (`git worktree add`, no
`tmp/` directory):

```
$ python -m pytest <the 2 timing-conformance modules> -q
46 failed, 202 passed in 38.78s
E   FileNotFoundError: [Errno 2] No such file or directory: '.../psh-r1-3-fresh/tmp/tmp7_e656zw.sh'
```

46 failures — matching the brief exactly.

**Fix:** each module takes a module-scoped, pytest-managed scratch dir
(`tmp_path_factory`). Module scope keeps one dir per module; xdist gives each
worker its own copy of the module, so parallel runs cannot collide.

### Census — other `<repo>/tmp` dependants (2 more found, and the masking cause)

```
$ grep -rnE "(_ROOT|PSH_ROOT|psh_root)[^)]*/ *['\"]tmp['\"]|os\.path\.join\([^)]*['\"]tmp['\"]" \
       tests/ --include='*.py' | grep -vE "tmp_path|tmpdir|mkdtemp|gettempdir"
tests/integration/redirection/test_advanced_redirection.py:346:        test_file = os.path.join(PSH_ROOT, 'tmp', 'rw_create_test.txt')
tests/integration/parsing/test_error_recovery.py:423:        tmp_dir = psh_root / 'tmp'
tests/conformance/bash/test_syntax_template_timing_conformance.py:50:   dir=os.path.join(_ROOT, "tmp")
tests/conformance/bash/test_nested_substitution_timing_conformance.py:76: dir=os.path.join(_ROOT, "tmp")
```

**CORRECTED in round 2 (round-1 blocker 1).** The command I first recorded did
not reproduce: it used `grep -rn` with `|` alternation but no `-E` (so the
alternation was a literal), and none of its branches matched the PATHLIB form
`psh_root / 'tmp'` at `test_error_recovery.py:423` — the very site the census
is credited with finding. Replayed at base `491b0e30` in a fresh worktree, the
command above returns all FOUR sites: the two timing modules from the brief
plus the two this census added.

These two explain why the whole family survived: `test_error_recovery.py` did
`tmp_dir.mkdir(exist_ok=True)` on `<repo>/tmp`, **creating the very directory
the other modules needed**. Whether they passed in a fresh checkout depended
on run order. Replayed in the fresh worktree:

```
$ python -m pytest tests/integration/redirection/test_advanced_redirection.py \
                   tests/integration/parsing/test_error_recovery.py -q
8 failed, 57 passed in 5.35s
$ ls -d tmp        # AFTER the run
tmp                # <- created by the run itself
```

Both converted to pytest temp dirs (9 subprocess sites + 1).

**Hazard caught while converting:** moving the redirection cases to a temp cwd
takes the child off the repo root, and `python -m psh` then resolves the
EDITABLE INSTALL. Verified: from a foreign cwd `import psh` gives
`/Users/pwilson/src/psh/psh/__init__.py` — the MAIN tree. Without a fix those
9 cases would have silently tested a different checkout and still passed.
Fixed with a `PYTHONPATH` pin plus a new discriminator,
`test_subprocess_runs_this_worktrees_psh`, which asserts the child's resolved
`psh.__file__` lies under this tree (version strings cannot discriminate —
checkouts share them).

**TIP replay, fresh worktree, no `tmp/`, all 4 affected modules:**

```
314 passed in 52.00s
$ ls -d tmp
ls: tmp: No such file or directory     <- and none is created
```

## Item 2 — skip-on-failure conversions (commit `ac990f1a`)

Both named sites confirmed verbatim at base.

**`tests/unit/lexer/test_modular_lexer_integration.py`** (base :144-163): the
whole body sat inside `except Exception: pytest.skip(...)`. All 4 commands
tokenize cleanly (3/5/5/6 tokens), so the handler could only ever swallow a
regression. Now parametrized with pinned token counts.

**MUTATION REPLAYED** (make one supported command raise, via an unterminated
quote — `tokenize` raises `UnclosedQuoteError`):

| | Result |
|---|---|
| BASE | `1 skipped` — SKIPPED [1] "…due to implementation: Unclosed \" quote…", **exit 0** |
| TIP | `1 failed, 3 passed` — `psh.lexer.position.UnclosedQuoteError` |

Note the second-order gain visible in those counts: at base ONE bad row
aborted the loop and hid the other three; parametrized, they still run.

**`tests/unit/expansion/test_arithmetic_integration.py`** (base :17-67): 4
skips across 2 tests. Probed against bash 5.2 BEFORE converting — all four
forms match exactly:

| command | bash | psh |
|---|---|---|
| `str="hello world"; echo "${str:3:4}"` | `lo w` | `lo w` |
| `str="hello world"; echo "${str:$((2+1)):$((2*2))}"` | `lo w` | `lo w` |
| `text="abcdefghijk"; echo "${text:4:4}"` | `efgh` | `efgh` |
| `text=…; start=2; len=3; echo "${text:$((start*2)):$((len+1))}"` | `efgh` | `efgh` |

Now hard assertions. Base behavior of these 3 tests was PASS (the skip paths
were dormant), so the conversion changes no outcome today — it removes the
ability to degrade silently.

### Census — tree-wide skip-on-failure

Tool `tmp/census_skip_on_failure.py`; full output `tmp/census-skip-on-failure.txt`.

```
--- BEHAVIOR (true skip-on-failure candidates): 15 ---
--- ENV (legitimate gates, stay): 11 ---
```

All 15 BEHAVIOR hits hand-classified. **13 are legitimate environment gates
that STAY**: locale unavailable (×6), no external `time` binary, OS forbids
the `/dev/fd` write shape, `RLIMIT_LOCKS` platform presence, git/base-tag
unavailable (×2), `--compare-bash` opt-in, `psh_only` case marking. One more
(`test_cmdsub_scanner_vs_parser.py:141`) is a corpus filter decided by the
INPUT shape, not by observed behavior — it stays.

**1 true instance**, `test_formatter_array_roundtrip_characterization.py:127`:
skipped `a=(p$x q)` as a combinator divergence "(pinned separately)".
Verified both halves of that justification:

```
$ grep -rn "a=(p\$x q)" tests/ --include='*.py'     # -> only this module
```
so nothing else pinned it — the claim was FALSE — and the divergence is GONE:

```
RD  mixed: True
CMB mixed: True
```

The skip outlived what it hid and cost coverage of a working case. Removed;
the row is asserted like every other. (Not xfail(strict): there is no longer
a divergence to expect.)

### Same-family vacuous guards (from the guarded-assert census), each probed first

| Site | Probe result | Conversion |
|---|---|---|
| `test_arrays_comprehensive.py` C-style for | psh == bash, rc 0 | unconditional |
| `test_function_builtins.py` `return` outside fn | both rc 2, identical message | rc + message pinned |
| `test_function_builtins.py` `readonly -f` | redefinition rc 1 both; original body survives | all three legs pinned |

#### The 11 ENV-bucket hits — per-hit classification (round-1 blocker 2)

Round 1 correctly objected that these were bucketed as a COUNT, not
classified. Each is now given a verdict; every "pinned separately" style
justification was VERIFIED rather than taken at face value, because exactly
that claim proved false in the formatter case.

| # | Site | Skip reason | Verdict |
|---|---|---|---|
| 1 | `test_claims_have_tests.py:351` | `{feature} is no longer a 'No' row` | **KEEP** — meta-test over the user-guide table; skips when the table row it polices no longer exists. Data-driven, not behavior. |
| 2 | `test_claims_have_tests.py:389` | `{feature} is no longer a 'Partial' row` | **KEEP** — same shape. |
| 3 | `test_analysis_mode_line_continuation.py:51` | `{key}: pinned combinator-parser gap (test_combinator_parity_regressions.py::TestEnhancedTestCompoundRejected::test_and_compound_rejected)` | **KEEP — reference VERIFIED REAL.** I checked the named pin rather than trusting the prose: `tests/integration/parser/test_combinator_parity_regressions.py::TestEnhancedTestCompoundRejected::test_and_compound_rejected` exists and PASSES. A genuine documented-gap filter, unlike the formatter case where the identical-sounding claim was false. |
| 4 | `test_option_parse_standardization.py:223` | `RLIMIT_LOCKS present on this platform` | **KEEP** — platform-capability gate. |
| 5 | `test_arithmetic_characterization.py:78` | `covered by error/edge cases` | **KEEP** — corpus de-duplication; the row is asserted elsewhere. |
| 6 | `test_unified_glob_converter.py:79` | `backslash contract changed: _component_matcher takes the canonical …` | **KEEP** — corpus filter on an intentional contract change. |
| 7 | `test_unified_glob_converter.py:82` | `engine keeps [[:upper:]]/[[:lower:]] case-sensitive (bug fix)` | **KEEP** — corpus filter recording a deliberate fix. |
| 8 | `test_shell_fd_lifecycle.py:42` | `no /dev/fd or /proc/self/fd on this platform` | **KEEP** — platform gate, in a helper (`_fd_count`). |
| 9 | `test_visualization_corpus.py:102` | `regenerated {golden.name}` | **KEEP** — fires only on the explicit golden-regeneration path. |
| 10 | `test_word_quote_derivation.py:232` | `combinator does not parse this corpus entry` | **CONVERTED (round 2)** — the true instance. See below. |
| 11 | `test_mypy_untyped_defs_coverage.py:307` | `{reason}` (git/base-tag unavailable) | **KEEP** — environment gate on git history availability. |

**Totals: 10 KEEP (environment/platform/corpus/data-driven), 1 CONVERTED.**

##### Hit 10 — the misclassification (round-1 blocker 2)

`test_comb_derived_equals_reported` wrapped its parse in
`except Exception: pytest.skip("combinator does not parse this corpus
entry")`. I bucketed it ENV on the reason text alone. It is the same shape as
the brief-named lexer site, and the justification for converting it is the one
I had already used for the arithmetic sites: **the skip path is DORMANT.**
Replayed:

```
CORPUS size: 32
combinator failures: 0
$ python -m pytest tests/unit/parser/test_word_quote_derivation.py -q
128 passed          <- 0 skips
```

No live gap, so the handler could only ever fire on a REGRESSION and report it
as a skip. Converted to a hard parse (`5616001a`). Hard assert rather than
xfail(strict): xfail would need a non-empty gap list, and the gap list is
empty.


### Probe-method audit (round-1 item 4 follow-up): rc-only vs full-output

The integrator asked which of my conversion probes compared full output rather
than rc only. The honest answer is **none of them compared the channels
separately**: round 1's probe was

```sh
b=$(bash -c "$cmd" 2>&1); p=$(python -m psh -c "$cmd" 2>&1); [ "$b" = "$p" ]
```

which MERGES stdout into stderr and ignores the exit status entirely. That is
precisely how the `disown --help` error got through — both shells exit 2, and
merging the streams hides that bash's text is on STDOUT while psh's is on
STDERR. A weak method, used uniformly, so every conversion needed re-checking
rather than just the one that was caught.

Re-verified ALL of them with `tmp/probe_audit.py`, comparing stdout bytes,
stderr bytes and rc INDEPENDENTLY:

| case | stdout | stderr | rc | verdict |
|---|---|---|---|---|
| arith substring literal | SAME | SAME | SAME | IDENTICAL |
| arith substring computed | SAME | SAME | SAME | IDENTICAL |
| arith offset/len literal | SAME | SAME | SAME | IDENTICAL |
| arith offset/len computed | SAME | SAME | SAME | IDENTICAL |
| case `^` | SAME | SAME | SAME | IDENTICAL |
| case `^^` | SAME | SAME | SAME | IDENTICAL |
| case `,` | SAME | SAME | SAME | IDENTICAL |
| case `,,` | SAME | SAME | SAME | IDENTICAL |
| c-style for + array index | SAME | SAME | SAME | IDENTICAL |
| large array 100 | SAME | SAME | SAME | IDENTICAL |
| `break 2` | SAME | SAME | SAME | IDENTICAL |
| array element quoting | SAME | SAME | SAME | IDENTICAL |
| array assignment splitting | SAME | SAME | SAME | IDENTICAL |
| `return` outside function | SAME | **DIFF** | SAME | DIVERGES |
| `readonly -f` redefine | SAME | **DIFF** | SAME | DIVERGES |
| `disown --help` | **DIFF** | **DIFF** | SAME | DIVERGES |

**13 of 16 identical on all three channels**, so the substantive conversions
were right despite the weak method. The 3 divergences all involve stderr —
exactly the channel a merged probe cannot resolve:

- **`return` outside function** and **`readonly -f`**: stdout and rc are
  byte-identical and the message TEXT matches; only the SHELL-NAME PREFIX
  differs (`/opt/homebrew/bin/bash: line 1: …` vs `psh: line 1: …`; psh also
  omits the line marker in the readonly case). Both tests already assert the
  diagnostic as a SUBSTRING, so **the tests were correct** — but my prose
  claimed they "match exactly", which overstates it. Both docstrings now state
  precisely what matches and what does not, and attribute the prefix
  difference to the campaign's existing error-wording carry family (Part B
  rows #6/#10/#24) rather than implying parity.
- **`disown --help`**: the real divergence, registered as
  `BUILTIN_LONG_HELP_OPTION` (see item 2 above).

Lesson worth carrying: an rc-only or stream-merged probe cannot certify
"matches bash". Compare stdout, stderr and status independently, or say
explicitly which channel was checked.

## Item 3 — flake queue

### (a) timeformat %P — carry #8 — ROOT-CAUSED AND FIXED (commit `624c74ea`)

Root cause reproduced, not guessed. `_psh_shape` normalized digits ONE FOR
ONE, so the assertion pinned the integer-digit WIDTH of `%P`:

```
$ for i in $(seq 1 30); do python -m psh -c 'TIMEFORMAT="p=%P"; { time true; } 2>&1'; done | sort | uniq -c
  28 p=0.00
   1 p=11822.71
   1 p=11577.45
```

**2 in 30 on an IDLE host** — never load-specific. Captured raw:
`R=0.000 U=0.010 S=0.000 P=11934.31`. `%P` is (user+sys)/real*100 and psh's
user time is accounted in 10 ms ticks; a tick landing inside a
sub-millisecond `time true` gives 0.010/~84µs ≈ 11900 %.

Fix: collapse an integer part to a single `N`, keep fractional digits
one-for-one. Precision — what the directive test exists to check — stays
pinned exactly; magnitude, a property of the machine, no longer is. Every
existing expected string is unchanged.

| | failures |
|---|---|
| BASE, 60 runs of `test_all_directives` | **4 / 60** |
| TIP, 60 runs | **0 / 60** |
| TIP, 25 whole-module runs | **0 / 25** |

**Production observation, reported not fixed:** bash for the same command
gives `R=0.000 U=0.000 S=0.000 P=2.02` and never explodes, so psh's `%P` can
be off by four orders of magnitude. Shell-behavior question, out of scope here.

### (b) golden `subshell_errexit_suppressed_in_if_condition` — NOT REPRODUCED

40 isolated runs + 40 under 8× CPU load → **0 failures**. Mechanism NOT
confirmed and deliberately not guessed. The timeout-default theory was tested
and RULED OUT: the case runs in 0.12–0.15 s idle and 0.13–0.15 s under 8× load
against the golden runner's 10 s timeout — ~70× headroom.

Not quarantined: it passes reliably, and quarantining without a demonstrated
defect would only hide the next occurrence. Hardened for diagnosis instead —
the harness-failure message now names the full argv and the timeout beside the
typed outcome, so a recurrence classifies itself (`Timeout(timeout=10, …)` vs
`SpawnFailure`) without needing a reproduction. Verified the typed repr is
informative by forcing a Timeout.

### (c) malformed-bytes `mapfile_read_all` — NOT REPRODUCED, hardened

40 isolated runs + 40 under load → **0 failures**. The 10 s runner-default
exposure does NOT apply — this module already passes an explicit
`timeout=15` on both sides — so that mechanism is ruled out rather than assumed.

Hardened against what WOULD have hidden it: the test only compared psh
against bash, so a harness fault degrading both streams identically (every
row is driven through a pipe with a writer thread) would compare equal and
PASS. Each row now also carries an absolute expected-bytes pin captured from
C-locale bash 5.2.26, plus `test_expected_output_covers_every_row` so no row
can be added without one. 0 failures / 30 runs under load after.

### (d) `test_complex_pipeline_background` — ROOT-CAUSED AND FIXED (commit `df46186a`)

Not reproducible in isolation (0 / 40 under 8× load), so the MECHANISM was
demonstrated directly instead of chased: with the pipeline slowed, the read
fails because the file is not there yet — the test had an empty "Wait and
check result" comment, i.e. the MEDIUM-13 shape again.

Swept the module rather than the one reported test: `test_pipeline_background_job`
had the identical empty-wait section, and `test_background_job_with_output`
had the fixed-path half. All three now hand off through `wait`, run in the
per-test temp dir instead of FIXED **system /tmp** paths shared with every
process on the host, and verify the file's CONTENT — each previously asserted
only that `cat` succeeded, under a comment saying output verification would
need capture. Values pinned against bash (`wc -l` → `3`).

Repetition at the fix commit: **0 failures / 40 module runs**.

### Standing exposure (watch, per brief)

The runner's 10 s default did not explain any queued flake: (c) overrides it,
(b) has ~70× headroom, (a) is not a runner case, (d) is an in-process race.
No per-case timeout changes were needed, and no global bump was made.

### (e) exit-trap family — BOTH cases (round-1 blocker 5; LEDGER row 134)

Row 134 assigns `TestExitTrapOnFatalSignal::test_command_mode_fires_exit_trap`
to 1.3, but my brief's queue substituted a different case, so neither my queue
nor round 1's ledger covered it. Both are covered here so row 134 can close.

Harness `tmp/exit_trap_repro.sh`. Load generators SELF-TERMINATE
(`timeout 300 sh -c 'while :; do :; done' &`) — see the incident note below.

| Batch | Result |
|---|---|
| A `test_normal_eof`, unloaded ×25 | **0 failures** |
| B `test_command_mode_fires_exit_trap`, unloaded ×25 | **0 failures** |
| A under 6× CPU load ×20 | **0 failures** |
| B under 6× CPU load ×20 | **0 failures** |
| **whole module ×12, clean host** | **1 failure** |

So neither NAMED case reproduces alone (90 runs between them), but the module
does — and the failure is a THIRD test in the family:

```
tests/integration/job_control/test_exit_trap_paths.py
  ::TestExitTrapOnFatalSignal::test_exit_in_exit_trap_matches_bash_sigterm
E   AssertionError: assert ('', -15) == ('cleanup\n', -15)
E     At index 0 diff: '' != 'cleanup\n'
```

psh produced NO stdout where bash produced `cleanup\n`; both died by SIGTERM
(`-15`), so the exit status is right and only the EXIT trap's OUTPUT is lost.

#### Root cause: a psh PRODUCTION race (reported, NOT fixed)

Reproduced OUTSIDE pytest entirely (`tmp/trap_race_probe.py` — plain
subprocess + sentinel + `os.kill`, no test framework), 120 runs per shell on
an idle host:

```
psh:  lost-trap-output 1/120  returncodes={-15: 120}
bash: lost-trap-output 0/120  returncodes={-15: 120}
```

Same harness, same script, same signal, same exit status — **psh
intermittently loses the EXIT trap's stdout when dying by a fatal signal;
bash never does.** ~0.8%, which matches the 1-in-12 module rate.

The test is CORRECT and psh is wrong: the flake is the bug announcing itself.
So it is NOT quarantined and NOT xfailed — it passes 119/120, so xfail(strict)
would fail, and quarantining a test that catches a real defect would hide
exactly what this campaign exists to surface.

#### The reproducer, embedded verbatim for rescue (integrator ruling)

`tmp/trap_race_probe.py` — no pytest, no project harness; plain subprocess +
sentinel + `os.kill`, so it survives independently of the test tree:

```python
"""Direct repro of the EXIT-trap-output-lost-on-SIGTERM race (no pytest)."""
import os, signal, subprocess, sys, tempfile, time

SCRIPT = 'trap "echo cleanup; exit 0" EXIT\n: > "{ready}"; sleep 0.5\n'

def run_once(shell_argv, tmpd, i):
    ready = os.path.join(tmpd, f"r{i}")
    path = os.path.join(tmpd, f"s{i}.sh")
    with open(path, "w") as f:
        f.write(SCRIPT.format(ready=ready))
    p = subprocess.Popen(shell_argv + [path], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 10
    while time.time() < deadline:
        if os.path.exists(ready):
            break
        if p.poll() is not None:
            break
        time.sleep(0.001)
    try:
        os.kill(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    out, err = p.communicate(timeout=20)
    return out, p.returncode

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    for label, argv in (("psh", [sys.executable, "-m", "psh"]),
                        ("bash", ["/opt/homebrew/bin/bash"])):
        empties = 0
        rcs = {}
        with tempfile.TemporaryDirectory(dir="tmp") as tmpd:
            for i in range(n):
                out, rc = run_once(argv, tmpd, i)
                rcs[rc] = rcs.get(rc, 0) + 1
                if out != "cleanup\n":
                    empties += 1
        print(f"{label}: lost-trap-output {empties}/{n}  returncodes={rcs}")

main()
```

Run as `python tmp/trap_race_probe.py 120` from the worktree root. Result on an
idle host, recorded above and repeated here so the script and its numbers
travel together:

```
psh:  lost-trap-output 1/120  returncodes={-15: 120}
bash: lost-trap-output 0/120  returncodes={-15: 120}
```

This becomes slot 1.3b's ORACLE: pre-fix it must show the 1/120-class loss,
post-fix 0/N for large N.

Pointer, deliberately shallow (production is out of scope for this slot):
`psh/executor/child_policy.py#die_by_signal` DOES flush
(`flush_child_streams(sys.stdout, sys.stderr)`) before `SIG_DFL` +
`os.kill(getpid())`, so the FORKED-CHILD path is sound. The failing case is
the TOP-LEVEL shell receiving SIGTERM, which is not a forked child and does
not obviously share that flush discipline. Locating the exact line is the
successor slot's job; the behavioral evidence above is decisive on its own.

#### Integrator ruling (received round 2) — disposition CONFIRMED and EXTENDED

1. **The test stays exactly as-is** — no quarantine, no xfail. Confirmed for
   the reasons given above.
2. **NEW Part D row** registered at ceremony: "psh loses EXIT-trap output on
   fatal-signal death of the top-level shell, ~1/120, CLI-reachable; bash
   0/120; forked-child path has flush discipline
   (`child_policy.py#die_by_signal`), top-level signal path does not obviously
   share it." Third production row from this slot; second CLI-reachable one.
3. **EXTENSION — it does NOT go to the successor queue.** Because it is
   CLI-reachable AND makes every future gate ~0.8%-flaky on this module, it
   becomes **WAVE-1 RIDER SLOT 1.3b**, immediately after v0.753.0 ships, with
   a production fix sanctioned for exactly this defect. Not started here:
   separate brief, separate branch cut from post-0.753.0 main. The reproducer
   above is its oracle; the 1/120 test remains the live sentinel.

Row 134 therefore closes completely: two named cases NOT reproduced (90 runs
between them, counts recorded), and the third family member root-caused to a
real production defect with an owner and a slot.

#### Incident: leaked load generators (my fault, recorded)

Round 1's reproduction batches used `for i in ...; do (while :; do :; done) &
done; ... kill $LOADPIDS`. `kill` hit the job's top-level PIDs; the
**subshells survived as orphans** — 20 spinners at ~99% CPU for ~40 minutes,
which is the campaign-memory killpg/orphan-sweep gotcha. The integrator swept
the host; I swept the remainder by PGID and then by PID, verified 0 remaining.

Fixed at source rather than by remembering to clean up: load generators are
now `timeout 300 sh -c '...' &`, so they self-terminate even if the harness
dies. Verified 0 stray spinners after every batch in this round.

## Item 4 — F1 behavior-aware documented differences (commit `9e5c002f`)

`_is_documented_difference` was `command in catalog["documented"]` with both
results unused.

**RED-ON-BASE, REPLAYED** against the unmodified framework
(`tests/conformance/test_documented_difference_shape.py`):

```
$ git checkout 491b0e30 -- tests/conformance/conformance_framework.py \
                           tests/conformance/differences/psh_bash_differences.json
$ python -m pytest tests/conformance/test_documented_difference_shape.py -q
4 failed, 3 passed
FAILED test_forged_psh_output_is_not_a_documented_difference     <- 'banana' ACCEPTED
FAILED test_forged_exit_status_is_not_a_documented_difference    <- forged rc 3 ACCEPTED
FAILED test_every_documented_entry_carries_an_expected_shape     <- all 7 entries shapeless
FAILED test_no_documented_entry_is_dead_inventory                <- 4 dead entries
```

**CORRECTED in round 2 (round-1 blocker 1).** I originally recorded
"3 failed / 3 passed". That was taken BEFORE `test_no_documented_entry_is_
dead_inventory` was added to the module, so it did not describe the module
that shipped. Re-replayed against the SHIPPED module with base framework +
base catalog: **4 failed / 3 passed**. The extra red is in my favour, which is
exactly why it needed correcting rather than leaving — the record must match
what ships.

The three "genuine divergence still classifies" tests passed at base too —
blind matching accepts everything, which is the point.

Triad: typed `expected` block per entry (per-side `exit_code` +
`stdout_pattern`/`stderr_pattern`, structured data); classifier validates the
observation against it, membership now necessary but not sufficient; an entry
with no shape cannot classify at all.

**TIP: 7 passed.**

**Live users pass FOR THE RIGHT REASON — proven by mutation, not asserted.**
`test_posix_compliance.py` ×2 + `test_user_guide_notes_conformance.py` ×1 →
112 passed. Breaking PROCESS_ID_DIFFERENCE's expected shape:

```
E   AssertionError: Expected documented difference PROCESS_ID_DIFFERENCE for: echo $$
E   Actual conformance: ConformanceResult.PSH_BUG
1 failed
```

At base that mutation changed nothing.

## Item 5 — F2 catalog hygiene (commit `9e5c002f`)

Each dead entry re-probed against live bash 5.2.26 from a SHARED cwd:

| Entry | Probe | Disposition |
|---|---|---|
| `PUSHD_BEHAVIOR` (`pushd`) | identical apart from the shell-name prefix (`pushd: no other directory`) | **DELETED** — not real |
| `POPD_BEHAVIOR` (`popd`) | identical (`popd: directory stack empty`) | **DELETED** — not real |
| `PUSHD_CWD_DIFFERENCE` (`pushd /tmp`) | identical from a shared cwd (`/tmp ~/src/psh-r1-3/tmp/f2probe`) | **DELETED** — confirmed a HARNESS artifact, exactly as the audit suspected |
| `HELP_BUILTIN` (`help`) | REAL formatting difference (PSH banner vs GNU banner) | **DELETED** — real but claimed nowhere in the user guide and referenced by no test |

**THE CONTRADICTION (the campaign-quality form of F2's "catalog rot" thesis
— integrator asked that this be stated explicitly).** These entries were not
merely unreferenced. The tree simultaneously contained *passing evidence that
they were false*:

- `tests/conformance/bash/test_bash_compatibility.py:664` asserts, and PASSES,
  that "pushd/popd/dirs manage the directory stack **IDENTICALLY to bash**";
- `tests/conformance/test_claims_have_tests.py:87` maps user-guide 17:893's
  `| pushd/popd/dirs | Yes | Yes | Full support |` row to that very test;
- my shared-cwd probes agree with both: byte-identical output.

So a **passing conformance test proving NO difference coexisted with three
catalog entries asserting one**, and nothing in the system noticed, because
nothing ever read the catalog entries — that is exactly what "inventory, not
closure" means. Dead entries do not merely fail to help; they accumulate
claims that contradict the tested truth. The zero-dead-entries meta-test
exists to make that state unreachable.

End state at the branch tip: **4 entries, 4 live users** — the three survivors
plus `BUILTIN_LONG_HELP_OPTION`, added by round 1's blocker-4 fix (the false
bash claim). Earlier revisions of items 4 and 5 said "3 entries / 3 users",
which was true before that fix and stale after it.

Every entry is test-referenced AND shape-carrying. Enforced by
`test_no_documented_entry_is_dead_inventory`, verified NON-VACUOUS by
resurrecting `POPD_BEHAVIOR`:

```
E   AssertionError: documented-difference entries referenced by NO test
    (dead inventory — give each a proving test or delete it): ['POPD_BEHAVIOR']
```

## Round-2 bounce fixes

### BLOCKER A — F1 anti-bypass hole (latent), CLOSED

A catalog entry whose `expected` block named no checkable key re-opened blind
classification. `_matches_side({}, result)` returned True — nothing to check,
so everything matched — and the meta-test only asserted `'expected' in entry`,
so a block containing nothing but prose satisfied it. Replayed at
`7672b426` before fixing:

```
_matches_side({}, ...) -> True
vacuous entry classifies nonsense -> True     # rc 99 vs 7, unrelated stdout
```

A guard present but empty: exactly the shape F1 exists to close, one level up.

Closed on BOTH halves, so a hand-edited catalog cannot bypass either:

* **Runtime** — `_matches_side` refuses a side that constrains nothing (it must
  pin at least one of `exit_code`, `stdout_pattern`, `stderr_pattern`).
* **Static** — `test_every_documented_entry_carries_an_expected_shape` now
  requires both a `psh` AND a `bash` side, each with a checkable key, instead
  of merely requiring the `expected` key to exist.
* **Offender replay** — `test_a_vacuous_expected_block_is_refused` injects the
  attack and asserts both halves refuse it, in both of its forms (prose-only
  block, and sides present but empty).

Replayed after the fix, including that the real entries are unaffected:

```
AFTER FIX — vacuous entry classifies nonsense: False
AFTER FIX — _matches_side({}, ...):            False
echo $$ :        True      # real divergences still classify
disown --help :  True
```

The framework docstring was ALSO corrected: it claimed the catalog-shape
meta-test kept the catalog from acquiring an unvalidatable entry, which
overstated what that test actually enforced.

### BLOCKER B — tip discipline (3rd campaign occurrence), acknowledged

`7672b426` landed mid-verification after I declared `5616001a` final. It was
accepted (docstring-only, claims replay true), but the rule is now MECHANICAL
for the rest of the campaign: **once a final tip is declared, any further
commit requires a SendMessage declaring it BEFORE the commit lands.** A
post-declaration commit without a prior declaration message is reverted at
integration regardless of content. When a follow-up arrives after my
declaration, the reply is a MESSAGE first; commits only after acknowledgement.

This round's commit was requested explicitly in the round-2 verdict, so it is
authorized; the next final-tip declaration is binding under the new rule.

### Nits — all verified before fixing, two of which were my own over-claims

| # | Nit | Verification + fix |
|---|---|---|
| 1 | The worktree discriminator could not fail for its claimed reason | CONFIRMED: repo-root `conftest.pytest_configure` pins the repo root into `os.environ['PYTHONPATH']` for the whole session, so the child resolved this tree with or without the helper. Now strips the ambient value (`monkeypatch.delenv`) and adds a NEGATIVE leg proving the probe can fail at all. Made discriminating — verified by neutering `_worktree_env`: the test then fails, naming `/Users/pwilson/src/psh/psh/__init__.py`. |
| 2 | Characterization pin errors under `--capture=sys` | CONFIRMED: `io.UnsupportedOperation: fileno`. Guarded — that regime makes the precondition UNMEASURABLE, not false, so it is a legitimate environment skip with a reason naming exactly that. All three modes now: default 16 passed, `-s` 16 passed, `--capture=sys` 15 passed + 1 skipped. |
| 3 | `%P` rate claim optimistic | CONFIRMED. My "roughly 1 run in 20" came from a 30-run sample (2 hits); an independent 120-run replay measured 0/120 idle and 1/120 loaded. Softened to "rare and load-sensitive" with both measurements cited; the MECHANISM statement (confirmed) stands, and the rate is explicitly not pinned. |
| 4 | `oracle_migration_census.md` describes the pre-1.3 state | CONFIRMED: it still said the silent-skip was "left as-is and carried to slot 1.3". Truth-up paragraph added recording the DISCHARGE, plus the inline import description. The base-SHA import TABLE is left alone — it is a frozen `e52957d4` snapshot and historically correct. |
| 5 | README over-claims pushd/popd "byte-for-byte" | CONFIRMED, and it was my own error from a merged-stream probe again. Per channel: successful operations (`pushd DIR`/`popd`/`dirs`) are byte-identical on stdout, stderr AND rc; the BARE-ERROR rows match on stdout and rc (both 1) but differ on stderr by the shell-name prefix. Sentence qualified precisely. |
| 6 | Ledger counts stale | CONFIRMED both: the catalog holds **4 entries / 4 live users** at tip (was 3/3 before blocker 4 added `BUILTIN_LONG_HELP_OPTION`), and the recorded guard-site command reproduces **18**, not 19, because a two-line `skipif` escapes any line-oriented pattern. Both corrected in place, with a multiline-aware command that reproduces 19. |

### Carry proposal (integrator ruling: record one line, no code change)

`try_resolve_bash()` is now DEAD INVENTORY: after 1.2 converted 11 modules and
1.3 converted the last 9, it has **zero consumers** in the test tree —
```
$ grep -rn 'try_resolve_bash' tests/ --include='*.py' \
    | grep -v 'shell_oracle.py|gen_census.py|test_shell_oracle_harness.py'
(no output)
```
It survives only where it is DEFINED (`harness/shell_oracle.py`), where it is
TESTED (`test_shell_oracle_harness.py`), and as a pattern string in
`gen_census.py`. Proposed for deletion by a successor slot, together with its
resolver test — deliberately NOT done here (it is an API removal, outside a
test-hygiene slot's scope, and the campaign has a live rule against
opportunistic widening).

## Gate / lint / types

**Gate 1** at `9e5c002f` — `python run_tests.py --parallel` (`tmp/gate1.txt`):
**20383 passed, 1 FAILED, 1589 skipped, 10 xfailed** (phase 1 3:27, phase 2 4:11).

The single failure was MINE and the gate is what caught it:

```
FAILED tests/unit/tooling/test_bash_oracle_resolution.py::test_no_bash_oracle_outside_resolver
E   bash oracle resolved outside tests/harness/shell_oracle.py.resolve_bash():
E       tests/conformance/conformance_framework.py:322: bare-bash-call-arg: 'bash'
```

F1's `expected.get("bash", {})` — a catalog KEY lookup — matched the E2
ratchet's `bare-bash-call-arg` shape (the string `"bash"` as a call's first
argument, which is what `shutil.which('bash')` / `Popen('bash …')` look like).
A false positive in intent, but the guard is correctly shape-based rather than
guessing intent, so the fix is mine to make, not the guard's to relax.

Rewritten as membership + subscript (`expected["bash"] if "bash" in expected
else {}`) — neither a call's first argument nor a list's first element —
with a comment recording why, so it does not get "simplified" back into a
violation. Commit `de18ca4d`.

Shape validation re-verified UNCHANGED after the rewrite by re-running the
mutation: breaking PROCESS_ID_DIFFERENCE's expected shape still fails the
live pin with `Actual conformance: ConformanceResult.PSH_BUG`.

**Gate 2** at `de18ca4d` (`tmp/gate2.txt`): phase 1 **PASSED** (the ratchet fix
held); phase 2 **3 failed + 1 errored**, combined 20380 passed.

All four classified individually rather than waved through as flakes — every
one is `OSError: [Errno 28] No space left on device`, and all four are in
`tests/integration/redirection/test_input_cursor_identity_i1.py`, a module
this slot NEVER TOUCHED (`git diff --name-only 491b0e30..HEAD` does not list
it). The tracebacks are `mkdtemp` / `write_bytes` / `make_numbered_dir`, not
behavior comparisons.

Same host condition slot 1.2 documented across six gate attempts. Evidence it
is not this branch:

- free space read **138 GB** immediately after the failing run (and before it)
  — a transient external consumer, not monotonic growth;
- **no leak**: only 2 stale `psh-oracle-*` dirs and 6 pytest dirs on the host;
- the module passes **9/9 in isolation** right after the failure.

**Gate 3** at `de18ca4d`, quiet host (`tmp/gate3.txt`): **EXIT 0 —
20384 passed, 1589 skipped, 10 xfailed, ZERO failures.** Both phases passed.

Corroborating the ENOSPC classification: the four gate-2 failures did not
recur, and nothing about the branch changed between gate 2 and gate 3.

**Gate 4** at `97b7c98d` (`tmp/gate4.txt`): phase 1 PASSED, phase 2 **1 failed**
— `test_exit_trap_paths.py::TestExitTrapCommandString::test_normal_eof`,
`assert r.stdout == "hi\nBYE\n"` observing `''` (EMPTY stdout, not a wrong
value). Module NOT touched by this slot.

Chased to a host condition, with the timeline as the evidence:

| When | df free | Observation |
|---|---|---|
| before gate 4 | 137 GB | fine |
| during/after gate 4 | **3.7 GB → 195 MB (100% full)** | the failure |
| module × 10, launched inside that window | 195 MB–1.9 GB | **1 / 10 failed** |
| after recovery | 138 GB | **0 / 12** module runs, **0 / 20** isolated runs of the failing test |

Empty stdout is the signature of a capture file that could not be written,
not of a trap that did not fire (a trap defect would give `hi\n` without
`BYE`). The same host swallowed 4 tests at gate 2 with explicit `[Errno 28]`.

**My footprint is not the cause, measured rather than assumed:** worktree
`tmp/` 2.8 MB, **0** stale `psh-oracle-*` dirs (no runner leak), pytest temp
1.1 MB — ~4 MB total against ~140 GB of churn. Nothing was deleted: the
consumer is outside this project, and the banked lesson ("don't panic on one
low df reading; re-check") proved right when space returned to 138 GB on its
own.

**Gate 5** at `97b7c98d`, recovered host (`tmp/gate5.txt`): EXIT 0 —
20384 passed, 1589 skipped, 10 xfailed, ZERO failures. Both phases passed.

**Gate 6 — ROUND-2 SUBMISSION, at the TRUE final tip `5616001a`**, clean host
(`tmp/gate6.txt`): **EXIT 0 — 20386 passed, 1589 skipped, 10 xfailed, ZERO
failures.** Both phases passed. This is the gate that counts: round 1's
numbers described a superseded tree (blocker 1).

20386 = gate 5's 20384 + 2, the two tests this round adds (the in-process
anomaly characterization and the BUILTIN_LONG_HELP_OPTION conformance pin),
matching the collected count below.
Nothing about the branch changed between gate 4 and gate 5; only the host's
free space did (195 MB → 138 GB), which is the classification.

Passed count at gate 5 was identical to gate 3 (20384) even though 11 more
guards were converted in between — correct: those conversions turn
`if X: assert` into `assert` INSIDE existing tests and add no new test
functions.

**Test-count delta at the TRUE tip** (round-1 blocker 1), re-measured with the
fresh detached-worktree method — an in-place `git checkout base -- tests/`
does NOT remove new files and gives a false number:

| | collected |
|---|---|
| base `491b0e30` (fresh worktree) | 21988 |
| tip `5616001a` | 22002 |
| delta | **+14** |

Accounted for with ZERO removals: 7 (F1/F2 shape module) + 1 (worktree
discriminator) + 1 (expected-output coverage) + 3 (lexer 1 → 4 parametrize)
+ 1 (in-process anomaly characterization, round 2) + 1
(BUILTIN_LONG_HELP_OPTION conformance pin, round 2). Skips 1590 → 1589: the
one formatter row whose stale skip was deleted now runs and passes.

**Gate 7/8/9 at `7672b426`** — three combined-run attempts, ALL defeated by
host ENOSPC, and this time MEASURED rather than inferred. I added a 3-second
disk sampler to the gate wrapper (`tmp/gate_with_sampler.sh`) so a failure can
be correlated with free space instead of argued about:

| run | result | disk low-water DURING the run |
|---|---|---|
| gate 7 | 30 failed + 30 errored (45 × `[Errno 28]`) | not sampled |
| gate 8 | 2 failed + 2 errored | **0.1 GiB** at 05:45:30 |
| gate 9 | 5 failed + 1 errored | **0.4 GiB** at 05:56:13 |

Recovery each time to ~137.7 GiB within about a minute, then steady. The
consumer is external, transient, and cycling every few minutes; my footprint
is ~4 MB with zero stale runner dirs (measured at gate 2).

**SUBMITTED GATE — SPLIT-PHASE at `7672b426`** (the campaign's documented
technique for an unstable host: run the phases separately so a transient
collapse costs one phase, not the whole run; each phase carries its own
sampler):

| phase | command | result | disk low-water |
|---|---|---|---|
| 1 | `pytest tests/ -m "not serial and not benchmark" -n auto -q` | **19492 passed, 1589 skipped, 8 xfailed — rc 0** | stable |
| 2 | `pytest tests/ -m "serial and not benchmark" -q` | **894 passed, 2 xfailed — rc 0** | **137.6 GiB** (no collapse) |

**Combined: 20386 passed, 1589 skipped, 10 xfailed, ZERO failures** —
identical to gate 6's combined run at `5616001a`, which is the corroboration:
the only commit between them (`7672b426`) is DOCSTRING-ONLY, verified by
`git diff 5616001a..7672b426` (one file, prose lines only, no assertion or
expression changed).

Phase 2's first attempt inside the split run DID hit the collapse (5 failures,
all carrying `Errno 28`, disk 0.1 GiB at 06:07:00); the retry on a healthy
host is the green recorded above, with the sampler proving free space never
left 137.6 GiB.

**GATE 10 — ROUND-2 SUBMISSION, at the final tip `a0afc9ed`**
(`tmp/gate10.txt`): **EXIT 0 — 20387 passed, 1589 skipped, 10 xfailed, ZERO
failures.** Both phases passed, in a single combined run.

20387 = gate 6's 20386 + 1, the new `test_a_vacuous_expected_block_is_refused`.

Notable: the sampler recorded the host collapsing to **0.1 GiB at 06:37:42**
DURING this run and the gate still passed — the collapse is brief enough that
it only bites when it coincides with a temp-dir-heavy test. That is consistent
with the earlier failures (all `[Errno 28]`, all in the most temp-dir-intensive
modules) and is further evidence the condition is external timing, not a
property of this branch.

**ruff check psh tests tools:** clean. **mypy:** clean, 274 source files.

### Anti-spawn guard + site budgets (integrator-requested confirmation)

This slot edited conformance modules and the conformance framework, so the
1.2-era guards must not have noticed anything:

```
$ python -m pytest tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py \
                   tests/unit/tooling/test_bash_oracle_resolution.py -q
50 passed
```

Both suites green — the AST anti-spawn guard (with its per-module site
budgets, frozen allowlist membership and PTY registry) and the E2 resolution
ratchet. Note the ratchet did NOT stay quiet earlier: it caught F1's
`expected.get("bash", {})` at gate 1, and the fix was mine (`de18ca4d`), not a
relaxation of the guard.

**Test-count delta, measured cleanly** (a fresh detached worktree at base, so
new files are genuinely absent — an in-place `git checkout base -- tests/`
does NOT remove them and gives a false number):

| | collected |
|---|---|
| base `491b0e30` | 21988 |
| tip `de18ca4d` | 22000 |
| delta | **+12** |

Fully accounted for, with **zero removals**: 7 (F1/F2 shape module) + 1
(worktree discriminator) + 1 (expected-output coverage) + 3 (the lexer test
parametrized 1 → 4). Skips went 1590 → 1589: the one formatter row whose
stale skip was deleted now runs and passes.

## Deviations / STOP-and-report

1. The background-subshell redirect finding above (reported to the integrator
   at the MEDIUM-13 milestone; zero production changes made).
2. MEDIUM-13's fix moved the test from the in-process fixture to a subprocess.
   This is a fixture change, not an assertion weakening — it is the only way
   to assert the redirect's effect at all, and it follows the project's own
   "system tests use subprocess" guidance for process-lifecycle behavior.
