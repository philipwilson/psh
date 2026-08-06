# Slot 3.5 ledger — Typed expansion/arithmetic user-errors (MEDIUM-12b)

Dev: dev-3-5. Worktree `/Users/pwilson/src/psh-r3-5`, branch
`fix/remediation-3-5`. Charter: `/Users/pwilson/src/psh/tmp/remediation-ledgers/briefs/3.5.md`.
Dead-drop: `tmp/remediation-ledgers/INTEGRATOR-INBOX.md` (R0 live, ACKed round 0).

The ledger is the durable record; assume the transcript is lost. Every claim
row carries its instrument beside it. SHAs are PASTED from shown command
output, never typed.

---

## 0. Environment / base facts (round 0, 2026-08-06)

| Fact | Value | Instrument (output shown in transcript) |
|---|---|---|
| Base SHA | `963c6eabe4942b8e0034083f9a140d9602c54c6a` | `git rev-parse HEAD` in worktree |
| Branch | `fix/remediation-3-5` | `git branch --show-current` |
| Worktree clean at start | yes (no porcelain output) | `git status --porcelain=v1` |
| Oracle bash | GNU bash 5.2.26(1)-release (aarch64-apple-darwin23.2.0) | `/opt/homebrew/bin/bash --version \| head -1` |
| PATH `bash` resolves to oracle | `/opt/homebrew/bin/bash` | `which bash` |
| Python | 3.14.2 (v3.14.2:df793163d58, Dec 5 2025) | `python -c "import sys; print(sys.version)"` |

Base gate figures ASSERTED BY BRIEF (to be RE-DERIVED in my first gate run;
any difference = STOP-and-report): 23,289 passed / 0 failed / 1,609 skipped /
10 xfailed; collected 24,925. compare-bash base 3,024 passed / 26 skipped.
mypy file count 275.

---

## 1. Re-derived site census (round 0) — RAW grep, before classification

Instrument A: `grep -rn "except" psh/expansion --include="*.py"`
Instrument B: `grep -rn "except" psh/executor --include="*.py" | grep -Ei
"valueerror|typeerror|arithmetic|except Exception|BaseException|except:"`
(both run at base SHA above; full output in round-0 transcript)

### 1a. Brief-listed sites — CONFIRMED PRESENT, with LINE DRIFT noted

| Brief site | Brief's line | ACTUAL line at 963c6eab | Handler text |
|---|---|---|---|
| arith outer net | evaluator.py:797 | **evaluator.py:797** (exact) | `except (ValueError, TypeError) as e:` |
| PS4 fallback | manager.py:345 | **manager.py:345** (exact) | `except Exception:` |
| operators offset/length | operators.py:90 | **operators.py:90** (exact) | `except (ValueError, ArithmeticError):` |
| operators VE #2 | operators.py:144 | **operators.py:144** (exact) | `except ValueError as e:` |
| operators VE #3 | operators.py:396 | **operators.py:396** (exact) | `except ValueError as e:` |
| `[[ ]]` VT net | core.py:**133-area** | **core.py:576** — DRIFT, reported | `except (ValueError, TypeError, OSError) as e:` |
| `(( ))` NARROW_SAFE arith leg | core.py (unnumbered) | **core.py:517** | `except (ValueError, ArithmeticError) as e:` |
| brace int() legs | brace_expansion.py:503/:520 | **:503 / :520** (exact) | `except ValueError:` |
| control_flow NARROW_SAFE arith leg | control_flow.py (unnumbered) | see §1b — DRIFT, reported | (no VE/ArithmeticError arith handler found at base) |

### 1b. Brief statement my first look CONTRADICTS (stop-and-propose, round 0)

**(i) `[[ ]]` net line drift.** Brief site 4 says `psh/executor/core.py:133-area`.
At 963c6eab the `[[ ]]` net is at **core.py:576**, inside
`visit_EnhancedTestStatement`. Instrument: `grep -n "except (ValueError, TypeError, OSError)" psh/executor/core.py`.
Substance unaffected (same handler, same Q2 BROAD_MASKING row keyed
`("psh/executor/core.py", ("ValueError","TypeError","OSError"), ("TestExpressionEvaluator","evaluate"))`);
reported so the record does not carry a wrong pointer.

**(ii) `control_flow.py` arithmetic NARROW_SAFE leg appears ABSENT from the
source at base while its Q2 NARROW_SAFE entry still exists.** Brief site 5 says
`control_flow.py` + `core.py` both carry `evaluate_arithmetic` catch legs. The
Q2 ledger DOES carry the control_flow entry:

```
("psh/executor/control_flow.py",
 ("ReadonlyVariableError", "NamerefCycleError", "ValueError",
  "ArithmeticError"), ("evaluate_arithmetic",)):
    "evaluate_arithmetic's VE is a user-reachable arithmetic error ..."
```

but instrument B over `psh/executor/control_flow.py` returns only
`control_flow.py:635: except (OSError, ValueError):` (an fd/stream leg, not
arithmetic). PENDING VERIFICATION in Phase A round 1 (the Q2 NARROW_SAFE
matcher is line-independent and keyed on call names, so the entry may match a
handler my `grep -Ei` filter shape missed — I re-derive with the Q2 detector
itself, not with grep, before asserting the negative). **Lesson 9 applies:
publish the negative only after the cell arrives — this row is OPEN, not a
claim.**

---

## 2. Pre-registration blocks (heavy runs)

Every heavy run gets a numbered block HERE FIRST; the GO request cites it by
file+line. No block, no request (R0 §3, brief Rules).

### PRE-REG-1 — full local gate at the Phase-B tip (written 2026-08-06, BEFORE the run)

**Command:** `python -u run_tests.py --parallel > tmp/gate-1.txt 2>&1`
(ONE foreground call, ~7 min, timeout 600000). `pgrep -f pytest` unpiped with
exit-status branch immediately before.

**Tip under test:** ~~the 6 commits~~ → **7 commits** on
`fix/remediation-3-5` (CORRECTED 2026-08-06 per R4's registered dev fault #4:
the count was written before R3's conditions added the 7th commit and was not
re-derived after that edit; instrument `git rev-list --count 963c6eab..HEAD`
→ **7**). Struck through rather than overwritten, same reason the original
prediction figures are kept below. The SHA is pasted into §4 from
`git rev-parse HEAD` output shown beside it.

**Base figures (brief §6, from the certified 3.4 ship record at 963c6eab):**
23,289 passed / 0 failed / 1,609 skipped / 10 xfailed; collected 24,925.

**Predicted figures at tip — DERIVED from base + delta, not guessed:**

**REVISED 2026-08-06 after R3** (conditions (ii)+(iii) added 3 conformance rows
and 1 M8 lock AFTER this block was first written). Both the original and the
revised figures are recorded — the block is a prediction made before the run,
not a transcription after it, and revising it silently would destroy that
property. ORIGINAL: collected 25,044 / passed 23,399 (delta +119 / +110).
REVISED, and the figures the run is judged against:

| Quantity | Base | Delta | Predicted |
|---|---|---|---|
| collected | 24,925 | +123 | **25,048** |
| passed | 23,289 | +114 | **23,403** |
| failed | 0 | 0 | **0** |
| skipped | 1,609 | +9 | **1,618** |
| xfailed | 10 | 0 | **10** |

Delta composition (+123): **98** conformance rows
(`test_typed_expansion_errors_conformance.py` — 95, plus R3 (ii)'s collision
controls: `( exit 127 )`, the command-not-found 127 child, and a second
arbitrary-code row) + **7** M8 locks
(`test_typed_expansion_error_m8_locks.py` — 6, plus R3 (iii)'s
stamp-check-by-status collision mutation) + 18 golden rows (9 new cases × a psh
row and a bash-comparison row, the latter SKIPPED without `--compare-bash`).
Hence passed +114 (98+7+9) and skipped +9.

**Instrument for the derived `collected` figure** (D-3.4 lesson 5 — a derived
relation between two sourced numbers needs its own instrument):
`python -m pytest tests/ -q --collect-only` printed **`25044 tests collected`**
at the pre-R3 tip and **`25048 tests collected in 2.16s`** after the R3
additions — each matching the corresponding prediction exactly. The predictions
were computed from base+delta first and then confirmed, not read off the
collector.

**Named expected-RED pins: NONE.** A fully green gate is expected. Every pin I
added is green at tip AND was separately shown RED at base in a detached
worktree (43 failed / 52 passed there).

**De-risking already done, so the heavy run is not the first look:**
`tests/unit/{expansion,executor,core,tooling}` +
`tests/integration/test_fatal_expansion_model.py` → **4,535 passed / 17 skipped
in 145.66s**, after fixing the single failure it surfaced
(`test_doc_pointers.py` flagged `` `int()` `` in my new
`psh/expansion/CLAUDE.md` prose as an unresolvable symbol pointer — reworded,
guard re-run green at 15 passed). Also green: the 10-file sibling +
must-not-flip set (385), and the scoped `--compare-bash` golden check (18).

**If any figure differs from the prediction:** STOP-and-report before
proceeding (brief §6).

### PRE-REG-2 — compare-bash at the Phase-B tip (written 2026-08-06, BEFORE the run)

**Command:** `python -m pytest tests/behavioral --compare-bash -n auto -q`
(NEVER `run_tests.py --compare-bash` — the block-buffering stall).

**Base figures (brief §6):** 3,024 passed / 26 skipped.

**Predicted at tip:** **3,042 passed / 26 skipped** (+18: the 9 new golden
cases contribute BOTH their psh row and their bash row under this flag, so none
lands in skipped). EXACT required.

**Named expected-RED: NONE** — exactly these 18 rows already passed under
`--compare-bash` when run `-k`-filtered.

---

## 3. Phase A findings (round 1, 2026-08-06) — all at base 963c6eab

### 3.0 Instruments (all under project tmp/, all re-runnable)

| Instrument | Path | What it establishes |
|---|---|---|
| I1 census | `tmp/census-3-5/derive_census.py` | census via the RATCHETS' OWN detectors |
| I2 A10.1 matrix | `tmp/a10/matrix.py` (+ `matrix.json`) | 216 cells, class×boundary×channel×`-e` |
| I3 errexit probe | `tmp/a10/errexit_probe.py` | 25 cases isolating the errexit×`-c` cell |
| I4 forcing | `tmp/census-3-5/forcing.py` | per-leg reachability, REAL path, cp-restore |
| I5 corpus sweep | `tmp/census-3-5/corpus_sweep.py` | 200 user-reachable cells; deadness evidence |
| I6 site probes | `tmp/obs-3-5/site_probes.py` | `[[ ]]`, substring, PS4 observables + injection |
| I7 PS4 dry-run | `tmp/obs-3-5/ps4_narrow_dryrun.py` | narrowing is observably behaviour-preserving |

Every mutating instrument (I4, I6, I7) uses cp-backup → patch → run → restore →
**sha256 byte-identity assert** + `__pycache__` drop. `git checkout` never used.
Tree verified clean by `git status --porcelain=v1` (empty) after each.

### 3.1 OPEN CELL FROM §1b RESOLVED — the brief was right, MY GREP was wrong

`control_flow.py`'s arithmetic NARROW_SAFE entry IS live, at **three** handlers
(`control_flow.py:416` init, `:432` condition, `:457` update — the Q2 detector
is signature-keyed so all three collapse to one dict entry). Instrument: I1,
which re-derives with `q2.broad_vt_candidates` instead of my grep. My round-0
grep missed them because the handler wraps across two lines and the FIRST line
reads `except (ReadonlyVariableError, NamerefCycleError,` — no substring my
`-Ei "valueerror|typeerror|arithmetic"` filter could match.

**Recorded as a dev instrument fault (D-3.4 lesson 1).** I held it as OPEN
rather than publishing the negative (lesson 9); had I published, the record
would carry a false "stale Q2 entry" claim. I1 also confirms the Q2 ledger is
fully reconciled at base: 23 live candidates, 23 classified, **0 NEW, 0 STALE**.

### 3.2 A10.1 matrix — 216 cells, 24 DIVERGE, in TWO families (I2)

6 error classes × 6 boundaries × 3 channels × 2 errexit states. **Every
divergence is a STATUS-only divergence: the stderr message text matches bash
exactly (modulo program name) in all 24** (I3 prints both sides verbatim).

| Family | Cells | Shape |
|---|---|---|
| **A10.1 proper** (brief-predicted) | **9** | `-c`, errexit OFF, fork boundary (`( )`/`$( )`/backtick) × fatal class (`${x?}`/`${x:?}`/`@Z`): bash `after rc=1`, psh `after rc=127` |
| **A10.1 × errexit composition** | **9** | same, errexit ON: bash shell-rc 1, psh 127 |
| **ERREXIT × `-c` DIRECT** (**NOT predicted**) | **6** | `-c`, errexit ON, **NON-fork** boundary (direct, brace group) × same 3 classes: bash 1, psh 127 |

Never-diverging (must-not-flip baselines, now recorded both-sides): all 36
discard-family cells (`$((1/0))`, `${a[1//]}`); all 36 `badname` (`${}`) cells;
all script-file and stdin-pipe cells; all pipeline-segment cells.

### 3.3 The unpredicted family — STOP-AND-PROPOSE (evidence, not appetite)

`bash -c 'set -e; echo ${x?boom}'` → **rc 1**; psh → **rc 127**. This is a
DIRECT-channel row, which the brief's must-not-flip section calls shipped,
probe-verified, "A10.1 changes the SUBSHELL boundary rows only". The brief's
own reproduction was run WITHOUT `set -e`, so the cell was never in view.

I3's 25 cases pin the rule precisely — **13 independent confirmations**:

- It is the CURRENT errexit FLAG, not history: `set -e; set +e; …` → 127 both
  shells (A5, MATCH). `set -o errexit` spelling → same as `set -e` (A6).
- It is **NOT effective-errexit**: every suppression shape bash's substitution
  sibling cares about — `|| recover` (B1), `if` condition (B2), `!` (B3),
  `&&` non-final (B4), `while` condition (B5) — still gives **1**, and none of
  them recovers (no RECOVERED/TAIL printed). So the shell-exit is the fatal
  expansion's own, and errexit only changes its STATUS. **This is the OPPOSITE
  of `substitution_abort_status`, where errexit→2 AND suppression matters** —
  the analogy would have given the wrong answer; only the probe gives the right
  one.
- Applies to the whole shell-exit family: `${x:?}` (C1), `${v@Z}` (C2), `set -u`
  (C4), and through `eval` (E1). NOT to `badname` (C3, already 1) and NOT to
  the discard family (D1/D2, unchanged — errexit-immune as documented).

**Cost of pinning it toward bash: LOW, and it flips no existing pin.**
`tests/integration/test_fatal_expansion_model.py::TestShellExitFamily::test_c_mode_exits_127`
is the only pin on this status and it never sets errexit (instrument: read of
the file, lines 274-286). So this is a pure ADD, not a flip.

**My recommendation:** IN, as a fourth ruled item. It is the same observable
(exit status of the same typed-failure family), the same fix locus
(`fatal_expansion_status`, `core/internal_errors.py:74`), a one-line change,
and leaving it is an UNPINNED-TOWARD-BASH divergence I have now measured.
But it is OUT by the brief's letter, so it is the integrator's call, not mine.
**I will not touch it without a ruling.**

**D-3.4-s3 FENCE CHECK (explicit):** s3 is rc 1-vs-127 on the POSIX
SPECIAL-BUILTIN READONLY abort. Every cell above is an unset/null/`@Z`/`set -u`
expansion failure with NO readonly prefix and NO special builtin; the diagnostic
text is `x: boom` / `bad substitution` / `unbound variable`, never a readonly
refusal. Different raise site, different message, different trigger — same rc
pair only. I am not in s3's territory.

### 3.4 Forked-child status has NO errexit branch (design cell, probed)

The sibling `substitution_child_abort_status` keeps an errexit branch (1→2) and
its docstring warns the status is "NOT a flat constant". **For fatal expansion
it IS flat.** Probe (transcript round 1, bash 5.2.26), reading the child's own
status through a suppressing `||`:

| script | bash child rc | psh child rc |
|---|---|---|
| `( echo ${x?boom} ) \|\| echo "child rc=$?"` | 1 | **127** |
| `set -e; ( echo ${x?boom} ) \|\| …` | 1 | **127** |
| `set -e; if ( echo ${x?boom} ); then :; else …` | 1 | **127** |
| `v=$( echo ${x?boom} ) \|\| …` | 1 | **127** |
| `set -e; v=$( echo ${x?boom} ) \|\| …` | 1 | **127** |
| `( set -e; echo ${x?boom} ) \|\| …` (errexit INSIDE the fork) | 1 | **127** |
| `( echo $((1/0)) ) \|\| …` (discard family control) | 1 | 1 ✔ |
| `set -e; ( echo $((1/0)) ) \|\| …` | 1 | 1 ✔ |

So `fatal_expansion_child_status(state)` is **1**, unconditionally — errexit
outside the fork, inside the fork, and suppression all leave it 1.

**Decomposition, verified at base:** psh's errexit exit already carries the
child's status verbatim (`set -e; ( exit 5 )` → 5; `( exit 42 )` → 42). So the
9 errexit×fork composition cells are fixed by the CHILD-status change alone;
only the 6 DIRECT cells need the §3.3 change. The two changes are independent
and their composition cell is exactly those 9 — **pre-registered as a required
matrix row (lesson 3), not to be inferred.**

### 3.5 CENSUS DISPOSITION TABLE (ruling (a) — one row per leg)

`RC` = reachability class: **U**ser-reachable / **I**nternal-only / **D**ead.

| # | Site (base line) | Leg | RC | Instrument | Proposed action |
|---|---|---|---|---|---|
| 1a | `evaluator.py:797` `except (ValueError, TypeError)` | `ValueError` | **D** | I5: 0/200 hits; I4: only an injected VE *outside* the inner try reaches it, and no production VE source exists there (`:752` converts the inner ones) | **DELETE** (whole net) |
| 1b | `evaluator.py:797` | `TypeError` | **I** | I4: `FORCETE` reaches it → "unexpected arithmetic error"; I5: 0/200 user-reachable | **DELETE** — the charter's core instance |
| 2 | `manager.py:345` `except Exception` (PS4) | all | **breadth** | I6 injection: an internal `TypeError` is swallowed into raw-PS4 fallback **even under `PSH_STRICT_ERRORS=1`**; I7: 7/7 rows byte-identical under `except PshError` | **NARROW** to `PshError` (+ one import line) |
| 3a | `operators.py:90` `except (ValueError, ArithmeticError)` | `ValueError` | **D** | as 1a (guards `evaluate_arithmetic`; body's only other call is `.strip()`) | **DROP the VE**, keep `ArithmeticError` |
| 3b | `operators.py:90` | `ArithmeticError` | **U** | `ShellArithmeticError` ⊂ builtin `ArithmeticError` (`arithmetic/errors.py`) — the live user path | **KEEP** |
| 3c | `operators.py:144`, `:396` `except ValueError` | `ValueError` | **U** | sole raiser `parameter_expansion.py:458` `"{length}: substring expression < 0"`; I6: psh matches bash rc AND text on both | **TYPE AT DETECTION POINT** — see scope note below |
| 4a | `core.py:576` `[[ ]]` `except (VE,TE,OSError)` | `ValueError` | **U+I mixed** | 4 bare-VE raisers in `enhanced_test_evaluator.py`: `:183` invalid regex = **U** (I6: matches bash, rc 2); `:58` unknown expr type, `:206` unknown binary op, `:357` unknown compound op = **I** (can't-happen branches) | **RULING (b)** — recommend IN |
| 4b | `core.py:576` | `TypeError` | **I** | I4: `[[ ]]` is the **ONLY** context on the whole path that masks an injected TypeError (rc 2, "psh: [[: FORCED-TE"); every other context propagates | **RULING (b)** — recommend IN |
| 4c | `core.py:576` | `OSError` | **not user-reachable, but EXPECTED-class** | I8 (see §3.5.1) | **KEEP the leg** |
| 5a | `core.py:517` `(( ))` `except (ValueError, ArithmeticError)` | `ValueError` | **D** | as 1a | **DROP the VE** |
| 5b | `control_flow.py:416/432/457` `except (RVE,NCE,ValueError,ArithmeticError)` | `ValueError` | **D** | as 1a | **DROP the VE** (×3) |
| 5c | 5a/5b | `ArithmeticError`,`RVE`,`NCE` | **U** | live typed arms | **KEEP** |
| 6 | `brace_expansion.py:503/:520` `except ValueError` around `int()` | `ValueError` | **U, narrow by design** | Q2 NARROW_SAFE; bash treats a non-numeric range as literal text | **UNTOUCHED** (stated with its probe, per brief) |

#### 3.5.1 Row 4c CLOSED IN PHASE A (was reported as pending) — instrument I8

`tmp/census-3-5/oserror_leg.py`, two halves:

- **Forcing** (sentinel-gated `OSError(99)` raised on the real path at the top
  of `TestExpressionEvaluator.evaluate`, cp-restore, sha256-verified): the leg
  **DOES** fire — `psh: [[: [Errno 99] FORCED-OSERROR`, rc 2 — identically in
  default and strict modes. Not dead code.
- **User-reachability** (12 forms whose primitives are the only plausible
  OSError sources — `-f`/`-r`/`-x`/`-e`/`-N`/`-nt`/`-ef` on missing, empty,
  bad-`/dev/fd` and 5000-char paths, `-t` on a bad fd, and a locale `<`
  comparison — under `PSH_STRICT_ERRORS=1`): **12/12 match bash, zero psh
  stderr.** No user-reachable form delivers an OSError to the net.

**Disposition: KEEP, and this row is NOT like the VE/TE rows.** `OSError` is a
member of `_EXPECTED_SHELL_ERRORS` (`core/internal_errors.py:71`), so it can
never be the internal-defect masking the charter targets — deleting it would
not un-mask a Python bug, it would merely re-route a genuine OSError from the
`[[` convention (rc 2, `psh: [[: …`) to `report_internal_defect`'s expected-error
path (rc 1), i.e. change a user-observable for no defect-visibility gain. That
is precisely the brief's rail "your deletions must not accidentally convert an
EXPECTED error into a propagating defect", read in the other direction.

**Consequence for ruling (b):** the narrowed net is
`except (<typed test error>, OSError)`, not `except <typed test error>` — the
VE/TE masking goes, the expected-error leg stays. Its Q2 `BROAD_MASKING` row
still deletes, because the entry is keyed on the VT names.

**The deadness argument in one line, with its instrument:** every leg marked
**D** guards a call to `evaluate_arithmetic`, whose body outside
`_evaluate_arithmetic_inner`'s try contains no `ValueError` source, and whose
inner try converts `(ValueError, OverflowError, MemoryError)` into
`ShellArithmeticError` at `:752`. I5 tests the consequence across 20
error-producing expressions × 10 calling contexts under `PSH_STRICT_ERRORS=1`:
**0 hits on the 797 message, 0 generic "unexpected error", 0 escaped
tracebacks.** I4 separately proves each leg WOULD fire if a VE arrived, so the
legs are live code guarding an empty class — not unreachable branches.

**Real Q2-ledger shrink now available (the brief's two named places):**
dropping the VE from 5a/5b changes those handlers' signatures, so the two
`evaluate_arithmetic` NARROW_SAFE entries must be rewritten — forced by
`test_classification_has_no_stale_entries`, not optional.

### 3.6 Findings OUTSIDE my charter — reported, NOT chased

| Finding | Instrument | Why not mine |
|---|---|---|
| `(( 1<<-1 ))`: bash rc 0, psh rc 1 (3 contexts) | I5 rcdiff | arithmetic SEMANTICS, not error typing |
| `${a[]}` empty subscript: bash rc 1, psh yields `X1Y` rc 0 | I5 rcdiff | subscript ACCEPTANCE (2.3/A10.3 family) |
| `a[]=9` empty subscript: bash rc 1, psh rc 0 | I5 rcdiff | same |
| PS4 + bad subscript: bash falls back and continues (rc 0), psh ABORTS (rc 1) | I6 | at MY site, but a different defect: a `TopLevelAbort` (a **BaseException**, confirmed by I7 part (a)) escapes the PS4 net. Narrowing to `PshError` neither fixes nor worsens it (I7: that row is byte-identical). Fixing it RESHAPES the user-observable the brief told me to preserve → needs a ruling or a successor row. |

### 3.7 Base-green check on the sibling + must-not-flip pin files

Instrument: `python -m pytest <10 files> -q`, run at base in this worktree.
**385 passed in 52.35s**, covering `test_fatal_expansion_model.py`,
`test_child_policy.py`, the Q2 ledger, the 2.3 ratchet,
`test_child_exit_taxonomy_centralized.py`, `test_substitution_abort_guards.py`
(note: under `tests/unit/tooling/`, not `tests/integration/` — my first path
guess was wrong and the run errored; corrected), the enhanced-test arith
operands + conformance, and the 3.4 family
(`test_resolution_timing_conformance.py` + `test_resolution_timing_ratchet_3_4.py`).

---

## 3.8 Proposed design (Phase B, NOT implemented — awaiting GO)

### D1 — A10.1 child status, through the ONE taxonomy (ruling (c))

The blocker is *where* the status is decided. `fatal_expansion_status`
(`core/internal_errors.py:74`) computes it AT RAISE TIME from
`state.options['command_mode']` — which a forked child inherits — and bakes it
into `TopLevelAbort(code)`; `map_child_exception` then returns `exc.status`
verbatim. The sibling does the opposite: `SubstitutionSyntaxAbort` propagates
as its OWN class and the status is decided AT THE BOUNDARY.

I cannot copy the sibling exactly, because the exception reaching the child
boundary here is `TopLevelAbort`, which is **also** the readonly-assignment
discard's carrier — blanket-remapping it would flip D-3.4-s3's pins. So the
channel-dependence must be STAMPED, not inferred:

1. `TopLevelAbort` gains a stamp marking "this status came from the
   fatal-expansion CHANNEL rule" (set only where `fatal_expansion_status`
   applies the `command_mode` branch).
2. New `fatal_expansion_child_status(state)` in `core/internal_errors.py`,
   beside its sibling, documenting the probed model: drops the channel rule
   (child exits 1 inside a `-c` shell) and — **unlike the sibling** — has NO
   errexit branch (§3.4's 8 rows).
3. `map_child_exception` gains one arm: a stamped `TopLevelAbort` returns
   `fatal_expansion_child_status(state)`; an unstamped one keeps `exc.status`.
   The change lands INSIDE the one taxonomy, so
   `test_child_exit_taxonomy_centralized.py` keeps policing it.

Unstamped `TopLevelAbort`s (readonly discard, `set -e` discard, the discard
family's `errexit_immune=True`) are untouched by construction — that is the
D-3.4-s3 fence, enforced by the code shape rather than by care.

**D1 PRECISION (round 1b, read-only prep) — the stamp site is structurally
unique.** Instrument: `grep -rn "TopLevelAbort(" psh/ --include="*.py"` →
**12 construction sites**. Exactly ONE is the fatal-expansion CHANNEL branch:
`core/internal_errors.py:122` (`raise TopLevelAbort(code)`, reached only for
`FatalExpansionError`/`UnboundVariableError` after the `command_mode` branch
has computed a channel-dependent `code`). Every other site builds a
channel-INDEPENDENT abort:

- `internal_errors.py:128` discard-line family (`errexit_immune=True`),
  `:244`, `:266` — other chokepoints;
- `expansion/word_expander.py:689`, `expansion/arithmetic/evaluator.py:792`
  (readonly-in-`$(( ))`), `executor/command.py:563`,
  `executor/command_assignments.py:370` and `:375` (**the readonly-assignment
  aborts — D-3.4-s3's own raise sites**), `executor/function.py:87`, `:187`.

So the stamp is a ONE-SITE change and the s3 fence needs no guard clause: s3's
aborts are built at `command_assignments.py:370/375` and never pass through
`:122`, so they cannot acquire the stamp. Fence enforced by topology.

Corollary already covered by the matrix: the script-file channel needs no
change — `fatal_expansion_status` raises `SystemExit(code)` at `:120` when
`state.is_script_mode`, `code` is already 1 outside `command_mode`, and
`map_child_exception`'s `SystemExit` arm returns it unchanged. That is why all
72 script-file and stdin-pipe cells match at base.

**Taxonomy-guard compatibility:** `test_child_exit_taxonomy_centralized.py`
fingerprints the string `\.exit_status\s+or\s+0` and asserts every occurrence
is inside `child_policy.py`. The new arm neither adds nor moves that
fingerprint, and lives in `child_policy.py` regardless — guard stays green,
and it keeps policing the arm I add.

### D2 — the errexit×`-c` direct rows (§3.3), ONLY IF RULED IN

One branch inside `fatal_expansion_status`'s existing `command_mode` arm: the
status is 1 when the errexit FLAG is set, else the error's own `exit_code`.
Raw flag, not effective errexit — §3.3's B1-B5 are the evidence, and the
comment will say so and name the sibling it deliberately differs from.

### D3 — leg dispositions

Delete `evaluator.py:797` entirely; drop the dead `ValueError` from
`operators.py:90`, `core.py:517`, `control_flow.py:416/432/457`; narrow
`manager.py:345` to `PshError`.

### D4 — typed raises at detection points

- `parameter_expansion.py:458` — raise the typed expansion failure instead of a
  bare `ValueError`; `operators.py:144/:396` catch the typed class.
  **SCOPE NOTE (stop-and-propose):** the brief's scope list names
  `operators.py` but NOT `parameter_expansion.py`. Typing a failure "at its
  detection point" is impossible without the one-line change at the detection
  point. Requesting explicit scope for `parameter_expansion.py:458`; if
  refused, the fallback is to keep the VE and catch it narrowly (worse, but
  in-fence).
- `enhanced_test_evaluator.py` (only if ruling (b) = IN) — `:183` invalid regex
  becomes the typed user error; `:58`/`:206`/`:357` become `RuntimeError`,
  exactly the pattern `evaluator.py:757` already documents for the arithmetic
  evaluator's can't-happen branches. `core.py:576` then catches the typed class
  and its Q2 BROAD_MASKING row is DELETED — the second real Q2 shrink.

### D5 — ratchet shape (ruling (c) second half)

GROW `test_subscript_no_broad_except.py`'s `GUARDED` set (NAME-VS-BODY: read
first — it is GROW-only by design, `except PshError` is the widest allowed,
and its detector is self-tested against synthetic offenders). Candidates my
census clears of broad handlers **after** D3:
`psh/expansion/manager.py` (the only broad handler in `psh/expansion/` at base
— I1 §2 confirms the rest of the subsystem is already clean) and
`psh/expansion/arithmetic/evaluator.py` (already has zero broad handlers; it
enters for the RATCHET value, locking the deletion).

`psh/executor/` is NOT proposed for GUARDED: I1 §2 finds 9 broad handlers there
(`child_policy.py` ×4, `command.py:289`, `command_assignments.py:445`,
`function.py:188`, `process_launcher.py:374`, `strategies.py:270`), several of
which are 5C's or documented policy chokepoints (`command.py:752-755`). Adding
the module would either fail immediately or force out-of-charter edits.

**Sibling detector for VT-typed nets: I recommend NO.** The Q2 ledger already
keys VT nets and its stale-entry check already forces my edits; a second
detector over the same signatures is the "instrument whose evidence trail
becomes its own input" shape (lesson 13). I would rather spend the ratchet
budget on the M8 mutation lock, which fails for a behavioural reason.

## 3.9 Pin plan + pre-registered runtime budget

| Pin | Location | Rows | Red-on-base? |
|---|---|---|---|
| P1 A10.1 conformance | `tests/conformance/bash/test_typed_expansion_errors_conformance.py` (shell_oracle) | 9 divergent fork rows + 8 matching baseline rows (§3.4 table) | **9 RED** |
| P2 errexit×`-c` | same file (only if D2 ruled in) | 6 direct + 9 composition | **15 RED** |
| P3 typed-observables | `tests/unit/expansion/` + `tests/integration/` | per touched site: message, rc, consequence | green (no-regression) |
| P4 ratchet growth | `test_subscript_no_broad_except.py` GUARDED | +2 modules | RED before D3 |
| P5 Q2 ledger | `test_broad_valueerror_catch_q2.py` | rewritten NARROW_SAFE ×2 (+ BROAD_MASKING −1 if (b) IN) | forced by stale-entry check |
| P6 M8 mutation lock | new tooling test | ≥1 re-introduced broad net caught by a NAMED default-run pin failing for its OWN reason | n/a |
| P7 goldens | `tests/behavioral/golden_cases.yaml` | promoted probes | — |

**Runtime budget (pre-registered, derived not guessed):** the 10-file sibling
set measures 385 tests / 52.35s (§3.7). P1+P2 are ~40 oracle rows; the nearest
comparable in-tree battery is `test_resolution_timing_conformance.py` (233 rows,
inside that 52s). Estimated added default-run cost **< 25s**; I will report the
measured figure, not this estimate.

## 3.10 Recommendation

Take D1, D3, D4-substring, D5 as the core; take **(b) `[[ ]]` IN** (it is the
single richest instance of the chartered defect: the only remaining TypeError
masker on the path, 3 of its 4 VE raisers internal, and it deletes a real Q2
BROAD_MASKING row); take **D2 IN** as a fourth ruling (measured, unpinned,
one-line, flips nothing). Defer 4c (`OSError`) to a Phase-B forcing probe and
report rather than guess. Everything in §3.6 stays reported, not chased.

---

## 4. Certification rows (post-state) — written BEFORE any discharge claim

**Tip at time of writing:** `791ebf0c0f2cd04cfa7a72d15856fab8d34efede`
(pasted from `git rev-parse HEAD`). **NOT a final-tip declaration** — the gate
and compare-bash are pending integrator GO (§2 PRE-REG-1/2).

Counts below are DERIVED (`pytest --collect-only` per file, `git diff | grep -c`
for the goldens), never hand-tallied. Every row asserts the POST-state.

### 4a. Per-commit accounting (7 commits, base `963c6eab`)

Instrument: `git log 963c6eab..HEAD --reverse --format=... --name-only`.
Every file in every commit was named in that commit's own message — **no
undeclared file or hunk in any commit; zero boundary slips.**

| # | SHA | Files | Ruling / purpose |
|---|---|---|---|
| 1 | `5b9573f7` | 6 prod | (a) leg dispositions |
| 2 | `0a52e437` | 4 prod | (b) `[[ ]]` net + `TestExpressionError` |
| 3 | `5eba4a5f` | 3 prod | (c) A10.1 stamp + (d) errexit override |
| 4 | `d7bbeb7e` | 4 test | pins: battery, ratchet, Q2 shrink, M8 |
| 5 | `a2ce2122` | 3 doc + 2 test | doc sweep + goldens |
| 6 | `3ea8f5fc` | 1 doc | doc-pointer nit |
| 7 | `791ebf0c` | 1 doc + 2 test | R3 conditions (ii)+(iii) + hierarchy list |

### 4b. Disposition certification — CODE half and PIN half both get a row

| Disposition | POST-state (code) | Instrument | PIN half | Instrument |
|---|---|---|---|---|
| 797 net DELETED | `arithmetic_expansion_value` has 2 arms (`ReadonlyVariableError`, `ShellArithmeticError`); no VT arm | `git show 791ebf0c:psh/expansion/arithmetic/evaluator.py` | M8 `test_m8_restored_797_net_is_a_broad_except_when_spelled_broadly`; ratchet GUARDED entry | `test_typed_expansion_error_m8_locks.py` (7 tests) |
| PS4 NARROWED | `except PshError:` at `_expand_ps4`; `PshError` imported | `git show` at tip | M8 `test_m8_ps4_rewidened_is_caught_by_the_broad_except_ratchet`; GUARDED entry | ratchet (6 tests) |
| operators VE dropped | `except ArithmeticError:` (module alias = `ShellArithmeticError`) | `git show` at tip | corpus sweep 0/200; battery substring rows | battery (98 tests) |
| substring TYPED at detection point | `parameter_expansion.py` raises `ExpansionError`; both `operators.py` sites catch it and bare-`raise` | `git show` at tip | golden `substring_negative_length_is_typed_at_detection_point`; battery rows | goldens (9 added) |
| four-site dead-VE dropped | `core.py` `(( ))` + `control_flow.py` ×3 catch `ArithmeticError` w/o VE | `git show` at tip | M8 `test_m8_restored_dead_ve_leg_is_caught_by_the_q2_ledger` | M8 |
| `[[ ]]` net narrowed | `except (TestExpressionError, OSError)`; 3 can't-happen → `RuntimeError`; 1 typed raise | `git show` at tip | M8 `test_m8_rewidened_enhanced_test_net_is_caught_by_the_q2_ledger`; battery regex rows | M8 + battery |
| A10.1 stamp (c) | stamp set at ONE origin, on BOTH carriers; one arm in `map_child_exception` | `git show` at tip | battery `TestA101ForkBoundaryChildStatus` (+ the NoFork counter-class); M8 `a101_systemexit_carrier_unstamped`, `stamp_check_by_status_collision` | battery + M8 |
| errexit override (d) | errexit branch inside `fatal_expansion_status`'s channel arm ONLY | `git show` at tip | battery `TestErrexitOverridesChannelStatus` + BOTH must-hold direction classes | battery |
| Q2 ledger SHRUNK | 3 entries removed (1 BROAD_MASKING + 2 NARROW_SAFE) | `test_broad_valueerror_catch_q2.py` (10 tests) green | its own stale-entry check forces it | same file |
| ratchet GROWN | GUARDED 2 → 4 modules | `test_subscript_no_broad_except.py` (6 tests) green | detector self-tests unchanged | same file |
| brace_expansion UNTOUCHED | `git diff 963c6eab..HEAD -- psh/expansion/brace_expansion.py` is EMPTY | stated negative, with its instrument | — | — |

### 4c. Red-on-base certification (the battery is a prover, not a passenger)

Instrument: detached worktree at `963c6eab` (`git worktree add --detach`),
discriminator-verified (`psh.__file__` under the base worktree, version
0.766.0, and the removed 797 net still PRESENT there — 2 grep hits), battery
file copied in, run, worktree removed.

**Result at base: 43 failed / 52 passed.** Breakdown by class (instrument:
`grep "^FAILED" | sed | sort | uniq -c`): 19 `TestA101ForkBoundaryChildStatus`,
19 `TestErrexitOverridesChannelStatus`, 5 `TestErrexitIsRawFlagNotEffective`.
At tip the same file is **98 passed**. (The 98-vs-95 difference is R3 (ii)'s
three collision rows, added after the base run; they are PARITY rows —
`( exit 127 )` passes on both sides — so they do not change the 43.)

### 4d. Tip re-verification of ruling (a)'s condition (deletions re-proved AT TIP)

| Evidence | At base | At tip | Instrument |
|---|---|---|---|
| user-reachable corpus reaching the 797 net | 0 / 200 | **0 / 200** | `tmp/census-3-5/corpus_sweep.py` |
| escaped tracebacks under strict | 0 | **0** | same |
| forced VE in `$(( ))` | masked: "unexpected arithmetic error" | **propagates** (ValueError under strict) | `tmp/census-3-5/forcing.py` |
| forced TE in `[[ ]]` | masked: `psh: [[:` rc 2 | **propagates** | same |
| A10.1 matrix (216 cells) | 24 DIVERGE | **0 DIVERGE** | `tmp/a10/matrix.py` |
| errexit battery (25 cases) | 15 DIVERGE | **0 DIVERGE** | `tmp/a10/errexit_probe.py` |

All mutating instruments restored and sha256-verified byte-identical; tree
clean after each (`git status --porcelain=v1`).

### 4e. Must-not-flip certification

| Family | Status | Instrument |
|---|---|---|
| 3.4 family (`test_resolution_timing_conformance` 233 + ratchet 11) | green | 10-file run: 385 passed / 52.35s |
| 2.3 family (subscript ratchet + keying battery + route audit) | green | same + `test_subscript_no_broad_except` 6 |
| fatal-model direct rows (`test_fatal_expansion_model.py`) | green | de-risk run 4,535 passed |
| child-exit taxonomy guard | green | 10-file run |
| substitution-abort guards | green | 10-file run |
| `test_doc_snippets.py` registry | untouched (its 1 entry is `signal_manager.py`) | grep |
| D-3.4-s3 readonly-abort statuses | unchanged | battery `test_readonly_assignment_abort_child_status_is_untouched` + golden |
| `exit` builtin child status | unchanged incl. the 127 collision | battery ×4 rows |

### 4f. Runtime budget — MEASURED, replacing the estimate

| Artifact | Measured | Pre-registered estimate |
|---|---|---|
| conformance battery (98) | 18.23s at 95 rows; 26.16s measured with the doc guard alongside | — |
| M8 locks (7) | 1.50s | — |
| **total added default-run cost** | **< 25s** | "< 25s" — held |

### 4g. Discharge audit (rows, not yet a discharge CLAIM)

| Required-work item (brief §Required work) | State | Blocking |
|---|---|---|
| 1 red-on-base census + A10.1 matrix + observables | DONE (§3, §4c) | — |
| 2 stage-gate reported, GO + rulings received | DONE (R2/R2b/R3) | — |
| 3 fix landed per ruled table | DONE (§4b) | — |
| 4 pins in-slot red→green, runtime reported | DONE (§4c, §4f) | — |
| 5 doc sweep, post-state certified | DONE (§4a #5-7) | — |
| 6 full gate green + compare-bash EXACT + ruff + mypy | **PENDING** | integrator GO (§2) |
| discharge audit + bounced-rows replay at final tip | PENDING | after 6 |

**Bounced-rows replay: NO ROWS BOUNCED TO DATE.** No verify round has run, so
the replay set is empty by construction — recorded as a stated negative, not an
omission. Three DEV INSTRUMENT FAULTS are registered (all instrument-class,
zero code faults): #1 single-line grep blind spot (self-caught in design,
externally resolved by R1); #2 the vacuous PS4 dry-run measuring a NameError
(self-caught, disclosed, fixed + guarded); #3 the Phase-A channel trace from a
hand-built in-process `Shell()` (caught by the observable matrix, not review;
R3 turned it into a binding rule).

### 4h. Gate status — RUN UNDER R4 GO, both match prediction EXACTLY

Machine verified idle before each (`pgrep -f pytest`, unpiped, exit-status
branch → "NO pytest running"). One foreground call each, back to back.

**PRE-REG-1 — full local gate.** Command
`python -u run_tests.py --parallel > tmp/gate-1.txt 2>&1`, EXIT=0.
Transcript: `tmp/gate-1.txt` (full pytest transcript at
`tmp/last-test-run.txt`). Tail: `Combined across 2 phase(s) (from phase
manifests): 23403 passed, 1618 skipped, 10 xfailed` / `✅ All test phases
PASSED`. Parallel phase line: `collected 25048 items / 24070 deselected / 978
selected`. Serial phase: `976 passed, 24070 deselected, 2 xfailed in 316.36s`.

| Quantity | Predicted (§2 PRE-REG-1) | ACTUAL | Match |
|---|---|---|---|
| collected | 25,048 | **25,048** | ✅ |
| passed | 23,403 | **23,403** | ✅ |
| failed | 0 | **0** | ✅ |
| skipped | 1,618 | **1,618** | ✅ |
| xfailed | 10 | **10** | ✅ |

Zero-failure instrument: `grep -c "FAILED\|ERROR" tmp/gate-1.txt` → **0**.

**PRE-REG-2 — compare-bash.** Command
`python -m pytest tests/behavioral --compare-bash -n auto -q`, EXIT=0.
Transcript: `tmp/compare-bash-1.txt`. Tail: `3042 passed, 26 skipped in
42.50s`. Predicted **3,042 / 26 EXACT** → ACTUAL **3,042 / 26**. ✅

**R4 condition (iv) — the R3-condition rows named, by node id, all PASSED**
(instrument: targeted `pytest -v`, 4 passed in 1.54s):

- `…::TestUntouchedFamilies::test_exit_127_in_a_subshell_is_the_collision_control` PASSED
- `…::TestUntouchedFamilies::test_exit_127_from_a_command_not_found_child` PASSED
- `…::test_m8_behavioural_mutation_regresses_the_named_pin[stamp_check_by_status_collision]` PASSED
- `…::test_m8_behavioural_mutation_regresses_the_named_pin[a101_systemexit_carrier_unstamped]` PASSED

| Gate | State | Figure |
|---|---|---|
| `ruff check psh tests tools` | **GREEN** | "All checks passed!" |
| `mypy` | **GREEN** | **275** source files (= base figure) |
| full local gate | **GREEN** | 23,403 / 0 / 1,618 / 10; collected 25,048 |
| compare-bash | **EXACT** | 3,042 passed / 26 skipped |
| working tree at tip | clean | `git status --porcelain=v1` empty |

§4g item 6 is hereby DISCHARGED; the discharge audit above is complete apart
from the final-tip row, recorded in §5.

---

## 5. FINAL TIP DECLARATION (2026-08-06)

**FINAL TIP: `791ebf0c0f2cd04cfa7a72d15856fab8d34efede`**
(pasted from `git rev-parse HEAD`), **7 commits** over base
`963c6eabe4942b8e0034083f9a140d9602c54c6a` (`git rev-list --count
963c6eab..HEAD` → 7). Working tree clean (`git status --porcelain=v1` empty).

**SCRIPTED VALUE-ALLOWLIST SHA SWEEP — the LAST edit before this declaration.**
Instrument: `tmp/remediation-ledgers/sha_sweep_3_5.py`, run against this file.
Result: **PASS**, exit 0 — 11 SHA-like tokens seen, all resolving to one of 19
allowlist values, every one of them DERIVED in-process (base and HEAD via
`rev-parse`, the 7 branch commits via `rev-list`, their short forms via
`rev-parse --short`, the one foreign prior-art SHA verified with `cat-file -e`,
and the CPython build id re-derived from `sys.version`).

The sweep BIT on its first run: it rejected `df793163d58`, the CPython build id
inside the environment table's interpreter string. Correctly so — that token is
not a psh object and could not be in a git allowlist. Fixed by DERIVING it from
`sys.version` at sweep time rather than whitelisting the literal, preserving
the property the sweep exists to enforce (no hex token enters the durable
record by hand). Recorded because a sweep that never fires proves nothing.

**DISCHARGE AUDIT — all 6 required-work items DISCHARGED** (§4g rows 1-5 plus
row 6 by §4h). **BOUNCED-ROWS REPLAY: the replay set is EMPTY** — no verify
round has run against this slot, so no row has been bounced. Stated as a
negative with its reason, not omitted.

**DEV FAULT REGISTER (4, all instrument- or citation-class; ZERO code faults):**
#1 single-line grep blind spot on the multi-line `control_flow.py` handlers
(self-caught in design — the plan already contained its own correction —
externally resolved by R1; the negative was withheld, per lesson 9).
#2 the PS4 narrowing dry-run measuring a `NameError` instead of the narrowing
(self-caught because the harness printed raw stderr; disclosed, fixed, and a
guard added that hard-fails on a leaked `NameError`).
#3 the Phase-A channel trace taken from a hand-built in-process `Shell()`,
which reproduced the wrong route and then confirmed the wrong belief with real
output (caught by the observable matrix AFTER implementing, not by review; R3
turned it into a binding rule — channel claims get subprocess probes).
#4 PRE-REG-2 cited at line 140 when it was at 151, and the block body saying
"6 commits" when the tip was 7 (both: a value not re-derived after an edit that
moved it; registered by R4, corrected in §2 by strike-through rather than
silent overwrite).

**LEDGER FROZEN from this declaration until the verdict.** Any correction after
this point is a SendMessage plus a new dated addendum section BELOW this one,
or a supervised edit under an explicit ruling — never an edit above.

---

## 6. ADDENDA (dated 2026-08-06, POST-VERDICT — written BELOW the frozen
## declaration in §5, never as edits above it)

R5 ruled round 1 a BOUNCE: 8 reported / 7 distinct / **7 REAL / 0 false**,
every one integrator-reproduced, **zero code defects**. I reproduced all seven
independently before writing anything here; each addendum states its own
instrument. Two doc blockers (B1/B2), the required NITs and the B7 pin landed
as commit `81d17996`; the rest are records, below.

### A1 (B3) — LINUX REASONING, and the battery's platform surface

**Owed by required-work item 4 + brief subtlety 8. Absent from round 1 —
REPRODUCED (`grep -ci linux` over the ledger → 0). My omission, not an
oversight of the brief: the brief asked for it explicitly.**

**Reasoning.** Nothing this slot changed has an expected platform surface.
The three behaviours are (i) which exception class a catch site names,
(ii) which typed class a detection point raises, and (iii) an exit-status
policy computed from shell options (`command_mode`, `interactive`, `errexit`)
and consumed at a fork boundary. None consults a syscall whose semantics
differ by platform, none is guarded by `sys.platform`, and none touches the
platform-divergent spots CLAUDE.md enumerates — real-time signals, the
macOS-only `/dev/fd` FIFO fallback in `process_sub.py`, glob/case-range locale
collation, or signal-name aliases. Instrument for the last clause:
`git diff --name-only 963c6eab..HEAD | grep -E "process_sub|locale|signal|glob"`
→ **no match** across the branch's 20 files.

The two platform-adjacent mechanisms the fix DOES rely on are POSIX-uniform:
`fork()` + `os._exit(status)` (the child-status route) and the
command-not-found convention of 127 (the collision control's natural route).

**One version-dependent cell, called out because it is NOT platform-dependent
and is easy to mistake for one:** CPython's str-to-int digit limit, which
supplies the user-reachable `ValueError` that makes the outer VE legs dead. It
varies by INTERPRETER version, not OS. The corpus records the interpreter
(3.14.2) beside the figure.

**The battery's platform surface is deliberately near-zero, and this is
instrumented, not asserted.** The rows are AGREEMENT-FORM — they compare psh
to the bash *on the same host*, so on Linux each row re-derives its expectation
from Linux bash rather than replaying a macOS number. Instrument over
`test_typed_expansion_errors_conformance.py`: **20** `_assert_agree(...)` calls
vs **3** direct `returncode ==` comparisons, and all three sit in
`TestDeclaredDivergences`, where pinning a DIFFERENCE makes agreement-form
impossible by construction and the fixed values are psh-side.

**Nightly expectation:** no Linux-specific failure predicted. If one appears it
would most plausibly be in bash-version drift on the oracle, not in this code.

### A2 (B4) — PARSER and INTERACTIVE verdicts (subtlety 7's two legs)

**Absent from round 1 — REPRODUCED (grep → 0/0). The gap was the RECORD: I ran
these as ad-hoc shell loops during the voluntary disclosure and never wrote a
verdict, and an ad-hoc loop is evidence that does not outlive its instrument.**
Both axes now have a durable, re-runnable instrument:
**`tmp/obs-3-5/axis_parser_interactive.py`** (discriminator-verified, bash
version recorded, agreement-form).

**PARSER verdict: NO SEAM — 11/11 rows agree, rd AND combinator both == bash.**
Rows: the A10.1 subshell and cmdsub markers, the child status through `||`, the
`( exit 127 )` collision control, the errexit×fork composition cell, the
discard-family control, the no-fork brace group, ruling (d)'s direct and
flag-off rows, the typed invalid-regex row, and the typed substring row.
Mechanism behind the verdict: error typing and both status rules are
POST-PARSE — the two front ends build the same AST and feed the same executor
path, so the seam the brief asked about ("where the seam warrants") does not
exist here. Round 1 recorded that judgment nowhere and instrumented it not at
all; it is now measured.

**INTERACTIVE verdict: FENCED — 6/6 rows agree with `bash -ic` on status.**
`fatal_expansion_status`'s channel branch is `command_mode AND NOT
interactive`, so ruling (d)'s errexit override cannot reach the interactive
family; `-ic` keeps the documented discard-with-status-1 model for `${x?}`,
`${x:?}`, unknown `@X`, `set -u`, and the errexit combinations. Probed on the
REAL entry path via subprocess, never a hand-built in-process `ShellState` —
the binding rule R3 §2 derived from my fault #3. No PTY harness was built
(brief subtlety 7 permits the documented-model citation; `-ic` needs no tty).

### A3 (B5) — TRANSCLUSION NEGATIVE, stated with its instrument

**Absent from round 1 — REPRODUCED (grep → 0). The brief's transclusion rule
requires the negative to be STATED, not merely true.**

Instrument: `grep -n "3\.5"
docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md` (full output, no
truncation) → **exactly 3 lines: 42, 192, 211.**

- **:42** — MEDIUM-12 Part A. **MINE** (the 3.5 clause; the 5C clause is not).
- **:192** — 3.3 successor rows; its item (d) is the A10.1 cell, marked "3.5
  neighborhood". **ABSORBED into this slot by R0/brief and discharged.**
- **:211** — D-3.4-lessons. Not a carry: a PROCESS row that happens to name 3.5
  (it records that from this slot the heavy-run GO requires a cited
  pre-registration block).

**Therefore: no OTHER Part B or Part D carry row names 3.5.** The negative
holds, and R5 records the verifier reaching the same three rows independently.

### A4 (B6) — §4e REGISTRY COUNT: my figure was FALSE; the verdict survives

**§4e claimed `test_doc_snippets.py`'s registry has "1 entry ... its 1 entry is
`signal_manager.py`". That is FALSE.** Correct instrument —
`grep '"source"' tests/unit/tooling/test_doc_snippets.py | grep -v src_path`
(the exclusion matters: a bare `grep -c '"source"'` returns **7** because it
also catches the CODE line `src_path = PROJECT_ROOT / entry["source"]`) →
**6 registry entries**:

| Line | Source | Kind |
|---|---|---|
| :43 | `psh/executor/process_launcher.py` | real |
| :56 | `psh/core/variables.py` | real |
| :69 | `psh/interactive/signal_manager.py` | real |
| :84 | `psh/core/state.py` | real |
| :138 | `psh/executor/process_launcher.py` | synthetic self-test |
| :153 | `psh/executor/does_not_exist_zzz.py` | synthetic self-test |

**The OPERATIVE verdict is unchanged and now properly evidenced: none of the
four real sources is touched by this branch.** Instrument:
`git diff --name-only 963c6eab..HEAD` → 20 files, none of which is
`process_launcher.py`, `core/variables.py`, `interactive/signal_manager.py` or
`core/state.py`. So no drift-locked snippet sits in any file I changed — the
claim §4e was making, reached by a wrong route.

**Fault mechanism, mine:** I ran the original check with `| head` and read
"exactly one entry" off a truncated window — a count taken from a display, not
from a counting instrument. R5 records that the integrator's R2b verification
of this same claim failed the SAME way (integrator fault #2). Two independent
checks sharing one blind spot is the 3.4 round-2 extraChecks lesson recurring
on both sides of the table: a verification instrument that mirrors the claim's
method cannot find the claim's error.

### A5 (B7) — UNDECLARED DEFAULT-MODE DELTA, now declared

**Round 1 recorded the deleted maskers' consequence class under
`PSH_STRICT_ERRORS=1` and, for §4d's `[[ ]]` row, did not qualify the mode.
The DEFAULT mode (strict unset/0) also changes, and that was undeclared.
Behaviour half reproduced by the harness's injection transcripts; record half
REPRODUCED (no tip-side default-mode row existed).**

All three are INJECTION-ONLY — no user-reachable route reaches them, which is
why they are declaratory rather than a regression. Corroborated by the 200-cell
corpus (`tmp/census-3-5/corpus_sweep.py`, 0 hits) and, independently, by the
harness's two 78-row corpora.

| Site | BASE default-mode | TIP default-mode | Instrument |
|---|---|---|---|
| (a) arith TE in `$(( ))` | "unexpected arithmetic error", line DISCARDED, rc 1 | generic internal-defect report, line CONTINUES (rc can flip 1→0) | `tmp/census-3-5/forcing.py` |
| (b) PS4 injected defect | silent raw-PS4 fallback, command RUNS, **rc 0** | per-command abort, **rc 1**, no output | `tmp/obs-3-5/ps4_default_mode.py` |
| (c) `[[ ]]` TE | `psh: [[: …`, **rc 2** | generic report, **rc 1** | `tmp/census-3-5/forcing.py` |

Row (b) is measured BOTH WAYS in one instrument: it copies the tree, injects
the defect, and runs with and without the narrowing —
`BASE rc=0 out='hi|TAIL'` vs `TIP rc=1 out=''`, in default AND strict mode
(base swallowed even under strict, which was the defect).

**§4d MODE QUALIFIER (correction to a frozen row, stated here rather than
edited above):** §4d's row "forced TE in `[[ ]]` — base: masked `psh: [[:` rc 2
→ tip: propagates" is true UNDER STRICT ERRORS. In DEFAULT mode the tip
observable is a generic internal-defect report at **rc 1** (not a propagating
traceback), and the base was rc 2. Read §4d's `[[ ]]` and `$(( ))` rows as
strict-mode rows, with this table as their default-mode counterpart.

**Locked, not merely described** (R5's requirement): commit `81d17996` adds
three rows to `tests/unit/expansion/test_arith_strict_errors_border.py` — the
strict-OFF and strict-ON PS4 siblings of the existing
`test_injected_internal_defect_swallowed_when_strict_off`, plus a COUNTER-PIN
that a PS4 failure for a SHELL reason still falls back and runs the command in
both modes. Without that third row the first two would be satisfied by deleting
the fallback outright.

### A6 — required NITs against the frozen record

- **§3.8 D1 count 12 → 11.** REPRODUCED: `grep -rn "TopLevelAbort(" psh/
  --include="*.py" | grep -v "class TopLevelAbort" | wc -l` → **11**. My 12
  counted the CLASS DEFINITION line (`class TopLevelAbort(BaseException):`) as
  a construction site — the grep pattern `TopLevelAbort(` matches it. The
  argument is unaffected and in fact slightly stronger: **1 of 11** sites
  stamps, not 1 of 12.
- **§3.8 D1 pointer.** The `SystemExit` route is at `internal_errors.py:119`
  at BASE (`if state.is_script_mode: raise SystemExit(code)`); §3.8 cited only
  the `TopLevelAbort` line. At tip that branch has moved (the stamp added
  lines) — the durable pointer is the SYMBOL,
  `core/internal_errors.py#fatal_expansion_status`, not the line.
- **43/52 → 43/55.** R5's replay figure supersedes mine for the TIP battery
  file: 43 failed / **55** passed. My 43/52 was measured before R3's three
  collision rows existed; those are PARITY rows (they pass on base too), so the
  RED count is unchanged at 43 and only the passed count moves. R5 confirms
  this corroborates my §4c parenthetical.

### A7 — remaining NITs that name the ledger

- **Border-test READ-VERDICT (deleted-decider discipline).**
  `tests/unit/expansion/test_arith_strict_errors_border.py` was READ before
  being touched, per the bash-verification workflow. Verdict: it does **NOT**
  pin old broken behaviour. Its two directions — a user-reachable `ValueError`
  becomes a clean `psh: arithmetic error:` (rejecting the `"unexpected"`
  marker), and an injected `RuntimeError` obeys the strict policy — are both
  still true at tip and the file passed UNCHANGED. Only its explanatory comment
  had rotted (it described discriminating against a fallback this slot
  deleted), so the change was comment-only + the three new B7 rows. The
  `"unexpected" not in stderr` assertions were KEPT deliberately: they now fail
  if any such fallback is re-introduced, which the M8 locks also cover.
- **§4e must-not-flip families — the full list**, with the run that covers
  each: 3.4 family (`test_resolution_timing_conformance` 233 +
  `test_resolution_timing_ratchet_3_4` 11), 2.3 family
  (`test_subscript_no_broad_except`, the subscript-keying conformance battery,
  `test_unlexable_subscript_route_audit`), the fatal-expansion model
  (`test_fatal_expansion_model.py`, incl. `test_errexit_immune` at :135 and
  `test_errexit_exits_shell` at :185 — R2's named (d) must-not-flip rows),
  `test_child_exit_taxonomy_centralized.py`, `test_substitution_abort_guards.py`,
  RESIDUAL_DIVERGENCES and the FLIP-PINS must-not-flip table. All green in the
  full gate (§4h: 23,403 passed / 0 failed).
- **USER-GUIDE NEGATIVE.** No user-guide sentence was added or changed —
  instrument: `git diff --name-only 963c6eab..HEAD | grep docs/user_guide` →
  **no match** — so the claims meta-test's "Full support" rule is not engaged.
  The meta-test is green regardless (`test_claims_have_tests.py`, 57 passed);
  as the brief notes, it polices over-claiming only.

### A8 — PRE-REG-3: full gate + compare-bash at the FIX-ROUND tip
### (written 2026-08-06 BEFORE the runs; placed here, in the addenda, so
### nothing above the frozen §5 declaration is edited)

**Commands.** (1) `python -u run_tests.py --parallel > tmp/gate-2.txt 2>&1`,
ONE foreground call, timeout 600000. (2) `python -m pytest tests/behavioral
--compare-bash -n auto -q > tmp/compare-bash-2.txt 2>&1`. `pgrep -f pytest`
unpiped with an exit-status branch immediately before each.

**Tip under test:** the fix-round tip on `fix/remediation-3-5`; commit count
from `git rev-list --count 963c6eab..HEAD` and the SHA from `git rev-parse
HEAD`, both re-derived AT REQUEST TIME and pasted into §7 (R4's rule, after my
fault #4).

**Predicted — DERIVED from the round-1 ACTUALS (§4h) plus the fix-round delta,
not re-guessed from base:**

| Quantity | Round-1 actual | Delta | Predicted |
|---|---|---|---|
| collected | 25,048 | +3 | **25,051** |
| passed | 23,403 | +3 | **23,406** |
| failed | 0 | 0 | **0** |
| skipped | 1,618 | 0 | **1,618** |
| xfailed | 10 | 0 | **10** |

Delta composition (+3): the three B7 pins added to
`tests/unit/expansion/test_arith_strict_errors_border.py` (5 → 8 rows,
instrument: `pytest --collect-only` on that file → `8 tests collected`).
Everything else in the fix round is documentation or ledger text, which the
collector does not see.

**Instrument for the derived `collected` figure:** `python -m pytest tests/ -q
--collect-only` → **`25051 tests collected in 2.12s`**, matching the
prediction computed from 25,048 + 3.

**compare-bash predicted: 3,042 passed / 26 skipped — UNCHANGED**, EXACT
required. No golden case was added in the fix round.

**Named expected-RED pins: NONE.**

**De-risking already performed:** `tests/unit/expansion tests/unit/tooling
tests/conformance/bash/test_typed_expansion_errors_conformance.py` →
**3,544 passed / 17 skipped in 123.04s**. Also green: the doc-pointer and
doc-snippet guards (22), and `test_claims_have_tests.py` (57).

**If any figure deviates:** STOP-and-report before anything else.

### A9 — PRE-REG-3 RESULTS (run under R6 GO, 2026-08-06)

Machine verified idle before each (`pgrep -f pytest`, unpiped, exit-status
branch). One foreground call each, back to back.

**Gate.** `python -u run_tests.py --parallel > tmp/gate-2.txt 2>&1`, EXIT=0.
Transcript `tmp/gate-2.txt` (full pytest transcript `tmp/last-test-run.txt`).
Tail: `Combined across 2 phase(s) (from phase manifests): 23406 passed, 1618
skipped, 10 xfailed` / `✅ All test phases PASSED`. Parallel phase:
`collected 25051 items / 24073 deselected / 978 selected`. Serial phase:
`976 passed, 24073 deselected, 2 xfailed in 312.87s`.

| Quantity | Predicted (A8) | ACTUAL | Match |
|---|---|---|---|
| collected | 25,051 | **25,051** | ✅ |
| passed | 23,406 | **23,406** | ✅ |
| failed | 0 | **0** | ✅ |
| skipped | 1,618 | **1,618** | ✅ |
| xfailed | 10 | **10** | ✅ |

`grep -c "FAILED\|ERROR" tmp/gate-2.txt` → **0**.

**compare-bash.** `python -m pytest tests/behavioral --compare-bash -n auto -q
> tmp/compare-bash-2.txt 2>&1`, EXIT=0. Tail: `3042 passed, 26 skipped in
42.69s`. Predicted 3,042 / 26 UNCHANGED → ACTUAL **3,042 / 26**. ✅

`ruff check psh tests tools` → "All checks passed!". `mypy` → **275** source
files. Working tree clean.

---

## 7. RE-DECLARATION (2026-08-06, after the R5 fix round)

**FINAL TIP: `81d1799672eac6b163d6f5dc7f7393545e405994`**
(pasted from `git rev-parse HEAD`), **8 commits** over base
`963c6eabe4942b8e0034083f9a140d9602c54c6a` (`git rev-list --count
963c6eab..HEAD` → 8, re-derived at declaration time). Working tree clean.

**Fix-round delta vs the §5 declaration: ONE commit, `81d17996`** — two doc
files (`psh/expansion/CLAUDE.md` B1+B2, `psh/core/CLAUDE.md` the `=channel`
NIT) and one test file (`tests/unit/expansion/test_arith_strict_errors_border.py`,
+3 B7 pins), plus ledger addenda §6 and two new instruments under `tmp/`.
**No production code changed in the fix round**, so R5's zero-code-defect
finding stands untouched. Every file was named in the commit's own message.

**All seven R5 blockers discharged:** B1 §6-commit, B2 §6-commit, B3 §6-A1,
B4 §6-A2, B5 §6-A3, B6 §6-A4, B7 §6-A5 + the three new pins. Required NITs:
the `=channel` correction (commit) and §6-A6 (D1 count 12→11, the durable
symbol pointer, 43/52→43/55). Remaining NITs naming the ledger: §6-A7.

**SCRIPTED SHA SWEEP — the LAST edit before this re-declaration.** Recorded
immediately below in §7a.

**DISCHARGE AUDIT: all 6 required-work items DISCHARGED** (§4g rows 1-5, row 6
by §4h for round 1 and §6-A9 for the fix round).

**BOUNCED-ROWS REPLAY — the set is no longer empty, and every row is replayed:**

| R5 row | Fix | Replay instrument / evidence |
|---|---|---|
| B1 dangling pointer | commit `81d17996` | `grep -n "manager.py#expand_ps4"` resolves to `def expand_ps4` at manager.py:322; doc guards green (22) |
| B2 false universal | commit `81d17996` | sentence scoped to five enumerated sites + `let_builtin.py:52` named as 5C residual; integrator grep at tip confirms the old universal is gone |
| B3 Linux absent | §6-A1 | reasoning + platform-surface instrument (20 agreement-form vs 3 declared-divergence rows; no platform-divergent file touched) |
| B4 parser/interactive absent | §6-A2 | `tmp/obs-3-5/axis_parser_interactive.py` — parser **11/11**, interactive **6/6** |
| B5 transclusion absent | §6-A3 | untruncated `grep -n "3\.5"` over LEDGER.md → rows 42/192/211 only |
| B6 false §4e count | §6-A4 | corrected to **6** entries with the precise instrument; operative verdict re-evidenced against the branch's 20 files |
| B7 undeclared default-mode delta | §6-A5 + 3 pins | three observables declared with instruments; `tmp/obs-3-5/ps4_default_mode.py` measures BASE vs TIP both ways; pins green |

**DEV FAULT REGISTER (5, all instrument-, record- or citation-class; ZERO code
faults across the whole slot).** #1 single-line grep blind spot. #2 vacuous PS4
dry-run measuring a NameError. #3 Phase-A channel trace from a hand-built
in-process `Shell()`. #4 stale citation line + commit count (R4). **#5 (R5-B6):
a count read off a `| head`-truncated display** — the joint lesson with
integrator fault #2, co-signed in R6: *a verification instrument that mirrors
the claim's method cannot find the claim's error.*

**LEDGER RE-FROZEN from this re-declaration until the verdict.** Corrections
follow the same rule: SendMessage plus a dated addendum BELOW this section,
never an edit above it.

### 7a — SHA sweep result (the LAST edit before the re-declaration above)

Instrument: `tmp/remediation-ledgers/sha_sweep_3_5.py`, run against this file
at the re-declared tip. **PASS, exit 0.** 13 SHA-like tokens seen, all
resolving to one of **21** allowlist values, every one DERIVED in-process:
base and HEAD via `rev-parse`, the 8 branch commits via `rev-list`, their short
forms via `rev-parse --short`, the one foreign prior-art SHA verified with
`cat-file -e`, and the CPython build id re-derived from `sys.version`.
Recorded output: `base 963c6eabe4942b8e0034083f9a140d9602c54c6a`,
`HEAD 81d1799672eac6b163d6f5dc7f7393545e405994`, `branch cmts 8`.

(The sweep fired for real in round 1 — it rejected the CPython build id, fixed
by DERIVING that value rather than whitelisting the literal. Noted again here
because a sweep whose only recorded history is PASS teaches the next reader
nothing about whether it can bite.)
