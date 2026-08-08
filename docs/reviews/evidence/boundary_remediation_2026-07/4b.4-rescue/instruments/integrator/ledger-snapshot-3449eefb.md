# SLOT LEDGER — 4B.4 (InputCursor contract close-or-narrow)

Base **e3924ed3** (v0.772.0 + 4B.3 addendum). Branch `fix/remediation-4b-4`,
worktree `/Users/pwilson/src/psh-r4b-4`. Oracle: `/opt/homebrew/bin/bash`
5.2.26(1)-release (aarch64-apple-darwin23.2.0) — recorded in-band by every
instrument via `harness.discriminate()`.

Status: **Phase A COMPLETE at D2.** No production file has been edited
(`git status` shows only the untracked `INTEGRATOR-INBOX.md`). Every
measurement of a candidate design was made by injection (pytest `-p`
plugin / `sitecustomize` on `PYTHONPATH`), never by mutating the tree.

---

## §1 Instrument manifest (command-generated; see `tmp/w4b4/MANIFEST.txt`)

| Instrument | Purpose | Transcript |
|---|---|---|
| `tmp/w4b4/harness.py` | A0 marker-anchored two-phase feed; two-level discriminator | (library) |
| `tmp/w4b4/instr01_reproduce_v2.py` | Reproduce dispatch legs A/B at this worktree | `instr01.out` |
| `tmp/w4b4/instr02_pushback_census.py` | P1 `_pushback` static + dynamic census | `instr02.out` |
| `tmp/w4b4/instr03_census.py` | A1 census, R-MALFORMED row + controls | `instr03.out` |
| `tmp/w4b4/instr04_timeout_route.py` | A1 census, R-TIMEOUT row (marker-anchored) | `instr04.out` |
| `tmp/w4b4/s1_flush_plugin.py` | s1-toward-bash emulation (in-process, pytest `-p`) | — |
| (driver) | s1 COST against shipped 4B.2 pins | `instr05_s1_cost.out` |
| `tmp/w4b4/s1site/sitecustomize.py` | s1 emulation injected into a psh CHILD | — |
| `tmp/w4b4/instr06_s1_effect.py` | Does s1 alone close the faces? | `instr06.out` |
| `tmp/w4b4/closesite/sitecustomize.py` | CLOSE-design emulation (v2, redirect-scoped, tripwired) | — |
| `tmp/w4b4/instr07_close_effect.py` | Does CLOSE close the malformed faces? | `instr07.out` |
| `tmp/w4b4/instr08_close_timeout.py` | Legs A/B under CLOSE, s1 unchanged | `instr08.out` |

---

## §2 A1 — STRANDING ROUTE × CONTRACT SURFACE (the census)

Verdicts are vs the cell's NAMED oracle (A3): the MALFORMED route is scored
against **C-locale** bash per I1 DECISION 1; the TIMEOUT route feeds
WELL-FORMED bytes and is scored against **ambient UTF-8** bash.

| Route \ Surface | S-SAMEFD | S-TEMPFRAME fwd | S-TEMPFRAME rev | S-DUP | S-EXECREBIND | S-FORK / external |
|---|---|---|---|---|---|---|
| **R-TIMEOUT** (well-formed, `-t` expiry) | DIVERGE (= s1 only) | **DIVERGE — LEG A, corruption** | **DIVERGE — corruption** | **DIVERGE — LEG B, byte loss** | DIVERGE (s1 only; surface CLEAN) | DIVERGE (s1 only; surface CLEAN) |
| **R-MALFORMED** (`_decoded` surplus) | MATCH (I1 must-hold) | **DIVERGE — I1 (c')** | **DIVERGE — NEW FACE** | **DIVERGE — I1 (b)** | MATCH (hook works) | DIVERGE — I1 (d), declared |
| **R-ERROR** | not scriptable | not scriptable | not scriptable | not scriptable | — | — |
| **R-PUSHBACK** | UNREACHABLE (§4) | UNREACHABLE | UNREACHABLE | UNREACHABLE | — | — |
| **CONTROLS** (no stranding) | — | MATCH | MATCH | MATCH | — | — |

**Decomposition (the instrument-mirror discipline — a cell consistent with
two mechanisms is evidence for neither).** Every R-TIMEOUT cell diverges,
but not for one reason. Separating them:

- On **S-EXECREBIND** and **S-FORK** the ONLY difference is where the partial
  byte was assigned (`v`); the surface's own observable is byte-identical to
  bash (`b=FILELINE` both; `child=\xa9` both). Those surfaces are CLEAN and
  their divergence is 100% attributable to s1.
- On **S-TEMPFRAME** and **S-DUP** there is a divergence BEYOND s1: a byte
  crosses into a different source's read (leg A / reverse) or is delivered
  nowhere at all (leg B). Those two surfaces — the two with no lifecycle
  hook — are the contract gap.

**NEW FACE (not in the I1 registry, not pinned anywhere).** The temp-frame
leak is SYMMETRIC. I1 (c') documents stdin surplus leaking INTO a temp-frame
file read. The mirror also holds: `read -N 1 a < g.txt; read b` leaks the
FILE's surplus OUT into the next real-STDIN read —
psh `b=<ASTDIN1>` vs bash-C `b=<STDIN1>` (`instr03.out`). Proof-shape:
CHARACTERIZATION vs C-locale bash, with a no-surplus control MATCHING.

---

## §3 A2/A5 — THE COUPLING, measured (not argued)

### s1-toward-bash: what it CLOSES (`instr06.out`)

Emulation injected into the psh child; **validity control first** — the s1
cell itself must converge or every other row is meaningless. It converged
(`INJECTION PROVEN LIVE`).

| Cell | psh | psh+s1 | Verdict |
|---|---|---|---|
| R-TIMEOUT × S-SAMEFD (s1 itself) | DIVERGE | **MATCH** | s1 closes |
| **LEG A** (timeout × temp-frame) | DIVERGE | **MATCH** | **s1 alone closes it** |
| **LEG B** (timeout × dup) | DIVERGE | **MATCH** | **s1 alone closes it** |
| R-MALFORMED × temp-frame fwd | DIVERGE | DIVERGE | s1 cannot reach |
| R-MALFORMED × temp-frame rev | DIVERGE | DIVERGE | s1 cannot reach |
| R-MALFORMED × dup | DIVERGE | DIVERGE | s1 cannot reach |

So the brief's coupling is REAL and directional: **s1-toward-bash closes both
corruption faces**, and leaves exactly the ultra-rare malformed count-boundary
family — which is precisely the scope R2 de-scoped on. s1-toward-bash
*restores R2's falsified premise*.

### s1-toward-bash: what it COSTS (`instr05_s1_cost.out`)

Baseline: `test_input_decoder_seam_4b2.py` + `test_read_exact_timeout_4b2.py`
= **70 nodes, 70 passed**. Under the emulation: **34 failed, 36 passed.**

| Class | Nodes broken | Status in the brief |
|---|---|---|
| `TestResumeRoutesArePshContract` (×2 methods) | 12 | **DESIGNED to flip** — legitimate |
| `TestSplitCharIdentityAcrossSeam` | 6 | **MUST-NOT-FLIP** (4B.2's MEDIUM-2 headline) |
| `TestSeamControlsNoCompletion` | 6 | **MUST-NOT-FLIP** |
| `TestSeamControlsNonContinuation` | 6 | **MUST-NOT-FLIP** |
| `TestSeamControlsMalformed` | 3 | **MUST-NOT-FLIP** |
| `TestCursorStateCensus::…decoder_clean` | 1 | **MUST-NOT-FLIP** |
| | **22 must-not-flip** | |

**Substrate limitation, stated:** the plugin patches the IN-PROCESS
`InputCursor`, so subprocess-driven suites (`test_read_exact_timeout_4b2.py`
via `run_psh`, the end-to-end and PTY files) were NOT reached — 0 of their
nodes moved here. **22 is therefore a LOWER BOUND**; the designed s1 flips
also live in those files. Proof-shape: MUTATION-PROVEN with a named
substrate gap.

**Why the collateral is structural, not incidental.** `_strand_then_drain`
(the seam suite's shared setup) parks a partial sequence by letting a timed
read expire, and its MANDATORY anti-vacuity guard asserts the decoder still
HOLDS those bytes. Assigning at timeout empties the decoder, so the guard
fires. Deeper: the module docstring states "Only TIMEOUT and ERROR can strand
a partial sequence". Removing TIMEOUT leaves ERROR, which the census could
not reach from any script. **s1-toward-bash would leave 4B.2's MEDIUM-2 fix
with no script-reachable route** — un-shipping a closed defect one slot later.
This is a ruling-(c) fence interaction: the fence says contract work COMPOSES
with the seam and a design needing seam changes stops and proposes. **I am
stopping and proposing.**

### CLOSE: what it closes (`instr07.out`, `instr08.out`)

Emulation v2 = redirect-scoped frame push/pop + dup aliasing, injected via
`sitecustomize`, with stderr tripwires so a hook that never fires cannot
masquerade as a design that does not work.

| Cell | psh | psh+CLOSE | oracle |
|---|---|---|---|
| CTL temp-frame no surplus | MATCH | **MATCH** | holds |
| CTL dup alias no surplus | MATCH | **MATCH** | holds |
| CTL same-fd carryover (**I1 must-hold**) | MATCH | **MATCH** | holds |
| R-MALFORMED × temp-frame fwd (I1 (c')) | DIVERGE | **MATCH** | **FIXED** |
| R-MALFORMED × temp-frame rev (NEW) | DIVERGE | **MATCH** | **FIXED** |
| R-MALFORMED × dup (I1 (b)) | DIVERGE | **MATCH** | **FIXED** |

And on the TIMEOUT route with **s1 left untouched** (`instr08.out`):

- **LEG A:** `x` goes from `\303FILELINE` to `FILELINE` — the cross-source
  CONTAMINATION is gone. The partial stays pending on fd 0's own cursor.
- **LEG B:** psh+CLOSE emits **14 bytes, exactly bash's 14** — `y=\303\251Z`.
  The **byte loss is gone**; every fed byte is delivered. What remains is
  only WHERE the partial lands (bash `v=\303|y=\251Z`), i.e. s1's value split.

**So CLOSE removes both data-integrity defects while touching the 4B.2 seam
NOT AT ALL** — it composes, exactly as the fence requires, and every 4B.2
pin stays green because no decoder behavior changes.

### Two design findings the tripwires produced (both load-bearing)

1. **The registry is populated LAZILY**, so `bind_dup` at `exec 3<&0` time
   finds NO description for fd 0 (`bind_dup(3 <- 0) = False` on first try).
   The source description must be MATERIALIZED at dup time.
2. **`cursor_for_fd` currently OVERWRITES an existing description** when no
   cursor is attached to it yet — which would silently destroy the alias the
   dup just created. A real implementation must REUSE the description it
   finds. This is a 2-line change inside the registry, and it is REQUIRED,
   not optional.

Neither is visible from reading the docstring's "purely ADDITIVE" claim.

---

## §4 A4 — P1 `_pushback` disposition (`instr02.out`)

**STATIC (by-elimination, airtight).** 7 occurrences, all inside
`input_reader.py`; 0 elsewhere in `psh/`. Exactly one writes a non-empty
value — line 306, `self._pushback = bytearray(drained[split + 1:])` — whose
source `drained` is `bytes(self._pushback)` from line 302. The seed is empty
(line 138) and the only other writes are `.clear()`. By induction
`_pushback` is ALWAYS empty, so `drained` is always `b''`, so
`split = -1` always, so **lines 305-308 are unreachable**.

**DYNAMIC (characterization).** A tripwire recording every in-place mutation
AND every whole-object rebind, across 3 VALIDITY-CHECKED shell stimuli (all
three now agree byte-for-byte with bash) plus a direct in-process drive of
the byte path: **0 mutations, 0 non-empty rebinds**; `_pushback` empty after
a full drain.

**Cost of removal (NAME-VS-BODY — P1 already has pins).**

| Existing pin | What removal does to it |
|---|---|
| `test_input_decoder_seam_4b2.py::TestCursorStateCensus::test_pushback_is_never_populated_by_the_public_api` | becomes vacuous; replaced by an M8-style structural guard |
| `test_input_reader_record_bytes.py::TestPartialDrainHonorsDelimiter::test_delimiter_buffered_in_partial_is_honored` | pins the dead branch **by direct injection**; deleted with it |
| `test_input_decoder_seam_4b2.py::TestCursorStateCensus::test_read_all_merge_order_is_decoded_then_pushback_then_fd` | **wired into 4B.2's M8 lock file** as a `breaks` witness for arm `seam-merge-order-scrambled` AND a `stays_green` witness for arm `seam-fresh-decoder-reintroduced` — both witnesses need rewriting, i.e. removal reaches a 4B.2 shipped mutation-lock |

Recommendation in §5.

---

## §5 A5 — DECISION MATRIX and recommendation

| # | s1 disposition | Temp-frame | Dup | Legs A/B (well-formed) | Malformed faces (3) | 4B.2 pin cost | Seam fence |
|---|---|---|---|---|---|---|---|
| 1 | keep-psh | narrow | narrow | **UNFIXED + undeclared today** | unfixed | 0 | untouched |
| 2 | keep-psh | narrow | narrow (+declare) | unfixed, DECLARED | unfixed, declared | 0 | untouched |
| 3 | **toward-bash** | narrow | narrow | **FIXED** (measured) | unfixed (I1 scope restored) | **≥22 must-not-flip** | **BREACHED** |
| 4 | keep-psh | **CLOSE** | **CLOSE** | **corruption + loss FIXED** (measured) | **ALL 3 FIXED** (measured) | **0** | **untouched** |
| 5 | toward-bash | CLOSE | CLOSE | FIXED | FIXED | ≥22 + hooks | BREACHED |

**My recommendation: ROW 4 — CLOSE both surfaces, keep s1 as psh-contract
and DOCUMENT it** (discharging s1's absence-travels clause with a user-guide
note, not a behavior change).

Reasons, each measured rather than asserted:

1. Row 4 is the only row that fixes **all five** divergent faces at **zero**
   cost to already-shipped 4B.2 pins, because it changes no decoder behavior.
2. Row 3 buys the same two corruption faces by retiring the only
   script-reachable route to 4B.2's MEDIUM-2 fix — un-shipping a defect
   closed one slot earlier — and breaches the decoder-seam fence.
3. Row 4 turns the I1 registry's two deliberate LOSSES into CLOSED behavior
   with exact C-locale-bash parity, which is what the charter's "complete the
   cursor ownership model" branch actually asks for.
4. Rows 1-2 leave measured, well-formed-input data corruption in place. Row 1
   additionally leaves it undeclared, which the brief forbids outright.

s1 remains a genuine divergence under row 4 (where the partial lands). I
recommend it be **declared and documented**, not changed, because changing it
costs the seam fence for a value-placement difference that no longer loses or
corrupts data once the surfaces are closed.

**Cost of row 4, honestly bounded.** MEASURED to work for the builtin
redirect frame path and the `exec` dup path. **NOT measured, and required for
a real implementation:** `apply_redirections`/`restore_redirections`
(compound-command frames), `setup_child_redirections`, per-command non-exec
`n<&m`, `{v}<&n` named-fd dups, and fd-close lifecycle. Those are the real
work; my emulation deliberately covered only enough to make the OBSERVABLES
measurable. `I1 (d)` (stranded byte invisible to an external child) is NOT
fixed by row 4 and stays a declared loss.

---

## §6 A6 — carry sweep dispositions

Sweep now covers **three registers** per R1's new standing rule (Part B
carries, Part C rulings, Part D successors).

| Row | Register | Disposition |
|---|---|---|
| **R2** (InputCursor gaps) | Part C ruling | **SUPERSEDED** by R1 on premise-falsification. Amendment is the integrator's to write at ceremony (LEDGER is never-touch for me). |
| **D-4B.2-s1** | Part D successor | **DISCHARGES HERE.** Under my recommendation: declared + user-guide documented, I1-style pins RE-AFFIRMED (not flipped), FLIP-PINS updated accordingly. Under row 3/5 they flip as designed. |
| **P1** (`_pushback`) | charter | Resolved: provably-unreachable (§4). Recommend **REMOVE + M8-style reintroduction guard**, with the M8 witness rewrite costed above; **documented retention is the cheaper alternative** and I flag the choice as the integrator's. |
| **D-4B.2-s2** (`-N` count model) | Part D successor | **MUST-NOT-ABSORB.** Untouched; no cell of mine moves it. |
| **D-4B.2-s3** (`read -s -N` echo) | Part D successor | **MUST-NOT-ABSORB.** Untouched. |
| **D-4B.3-s1 / s2** | Part D successor | Not this slot's subject (history state machine). Verified untouched — no instrument or design here reaches `history_manager.py`. |
| **carry #21** (mixed valid+malformed `-N` boundary) | Part B carry | Adjacent, NOT absorbed. Row 4 does not change the count model; carry #21's characterization cells must stay green. |
| **I1 (b)/(c')** deliberate-loss rows | I1 registry | Row 4 CLOSES both; the registry text and `input_cursor.py` docstring become doc-sweep targets. |
| **I1 (d)** external/child loss | I1 registry | NOT closed by row 4; remains declared. |
| **R1 here-input `OpenDescription` adoption** | fence | OUT of slot; successor note. |

---

## §7 Doc-sweep targets identified (all still UNTOUCHED — no edit pre-ruling)

| File | Defect |
|---|---|
| `psh/builtins/input_reader.py:38-39` | claims the cursor is keyed "so `exec 3<&0` shares it" — FALSE today (no `bind_dup`); leg B measures the loss |
| `psh/io_redirect/input_cursor.py` docstring | "the kernel offset is the complete shared state in both shells" / dup+temp-frame fidelity "exceeds the oracle" — measured FALSE; also calls the extension "purely ADDITIVE" when it in fact requires a `cursor_for_fd` change (§3 finding 2) |
| `psh/builtins/CLAUDE.md`, `psh/io_redirect/CLAUDE.md` | describe the SCOPED contract |
| `docs/user_guide/17_differences_from_bash.md:596-598` region | where s1's documentation lands |
| I1 ledger deliberate-loss registry | scope framing ("ultra-rare malformed count boundary") under-states the timeout route |

---

## §8 Deviations / faults / instrument defects (self-disclosed, running)

| ID | Kind | Disclosure |
|---|---|---|
| ID-1 | instrument defect | `B-ctl` phase-2 anchor timing-marginal (parent wall clock vs child startup). Disclosed at D1 pre-reliance; replaced by the A0 marker-anchored harness. |
| ID-2 | instrument defect | INSTR02 v1 drove the byte path with a script whose `read` sat on its own line, so it consumed the CONSUMER line and never reached the data; stderr was discarded, so an empty stdout read as success. Caught by adding the validity control the 4B.2 lesson demands, which I had omitted on that arm. Fixed; all 3 stimuli now VALID and bash-agreeing. |
| ID-3 | instrument defect | CLOSE emulation v1 pushed/popped the WHOLE fd map on EVERY builtin frame — it broke the I1 same-fd must-hold control and "fixed" the temp-frame face by DESTROYING the surplus, while its dup half never fired at all (no tripwire, so silence looked like a negative result). **Invalid as evidence; discarded, not reported.** v2 is redirect-scoped and tripwired. The control catching it is why it never entered a claim. Made structural by R2 invariant 6 and landed as the 4B.4 M8 arm set. |
| F-1 | fault (unsupported figure) | The §10 pre-registration first claimed a mypy delta "base 274 → 275" and attributed it to a new module-level function. I had NOT run mypy at base, and the stated cause is impossible (a function cannot change a file count). Self-caught while re-reading the block before the GO request, i.e. before any GO cited it. Corrected in place with the strike recorded; no mypy delta is now claimed. Root cause: I wrote a *reconciliation* for a number instead of measuring it — exactly the D-3.4 lesson that a derived RELATION between two sourced numbers needs its own instrument. |
| D-1 | deviation (declared) | A stale mention of the removed `_pushback` survives at `psh/scripting/input_sources.py:516` ("no pending pushback/decoder state"). That file is FENCED for this slot (I2), so I did NOT edit it. The sentence remains substantively true (no pending decoder state between lines); only the term is stale. Proposed to the integrator rather than fixed. |

No deviations from the process rules to report. No production file edited; no
heavy run performed; no gate token requested.

---

## §9 Freeze chain

(no freeze yet — Phase A report only)

---

## §10 PRE-REGISTRATION — gate run 1 (Phase B tip 3d285b56)

Written BEFORE the run, as the binding block my GO request cites by
file+line. Every figure here is command-generated, not estimated.

### Collection delta (derived at BOTH ends, ONE DOOR)

| Tree | `pytest tests/ --collect-only -q` | Command |
|---|---|---|
| base e3924ed3 (detached probe worktree) | **25,482** | full-suite collect |
| tip 3d285b56 | **25,522** | full-suite collect |
| **delta** | **+40** | |

The +40 DECOMPOSES exactly — an unexplained residue would be a finding:

| Δ | File | Reason |
|---|---|---|
| +16 | `tests/integration/redirection/test_input_cursor_contract_4b4.py` | new behavioural pins |
| +17 | `tests/unit/io_redirect/test_input_cursor_registry_4b4.py` | new registry unit cells |
| +7 | `tests/unit/tooling/test_input_cursor_m8_locks_4b4.py` | 5 M8 arms + anchor check + P1 ratchet |
| +1 | `tests/integration/redirection/test_input_cursor_identity_i1.py` | the mirror-direction cell (10 total) |
| −1 | `tests/unit/builtins/test_input_decoder_seam_4b2.py` | `test_pushback_is_never_populated_by_the_public_api` removed with its subject (40 total) |
| 0 | `tests/unit/builtins/test_input_reader_record_bytes.py` | 1 cell replaced 1:1 |
| **+40** | | **sums to the measured delta** |

### Expected gate outcome

Base attestation (committed, gated edcf1ab6): **23,835 passed / 1,620
skipped / 10 xfail**. Expected at tip: **23,875 passed** (+40), skips and
xfail **unchanged** (+0/+0), **0 failed**.

- **No test is expected to be RED at the tip.** Every new cell is green here
  and 11 of the 16 behavioural ones were proven RED at base in a detached
  probe worktree (`tmp/w4b4/instr10_red_on_base.out`); the other 5 are
  controls/must-holds that must pass on BOTH sides.
- **Designed flips already applied** (so they are green at the tip, not red):
  the two I1 deliberate-loss rows now assert parity, and the three 4B.2 pins
  that referenced `_pushback` are rewired.
- **s1 pins are RE-AFFIRMED, not flipped** (ruling (b)): every
  `TestResumeRoutesArePshContract` and rider cell must stay green exactly as
  shipped. A flip there would mean I changed timeout behaviour, which ROW 4
  explicitly does not.

### compare-bash

Expected **3,046 / 26 EXACT, movement +0**. Reason: no golden case is added
or modified by this slot, and no behaviour reachable from a golden case
changes — the closed faces need a stranded surplus, which no golden case
constructs.

### ruff / mypy (already run at this tip, pre-declared here)

`ruff check psh tests tools` → **All checks passed**.
`mypy` → **Success: no issues found in 275 source files**.

*Correction, self-caught before the GO request.* This block first read
"(base 274; +1 because `input_cursor.py` gained a module-level function)".
Both halves were unsupported: I never ran mypy at base, and a new FUNCTION
cannot move a FILE count in any case. No mypy delta is claimed — the tip
figure above is the only mypy number I have measured, and this slot adds no
new module. Logged as fault F-1 in §8.

---

## §11 GATE RUN 1 — MISMATCH vs §10, stopped and reported

Ran at tip **78839d6f** (the D-1 doc hunk, per R3). Single foreground
`python -u run_tests.py --parallel`; it exceeded the 600s foreground window
and was MOVED TO BACKGROUND (the sanctioned handling), then awaited in-turn
with a bounded poll — the turn never ended with it in flight.

| Figure | §10 pre-registered | Gate run 1 | Verdict |
|---|---|---|---|
| passed | 23,875 | **23,873** | **MISMATCH (−2)** |
| failed | 0 | **2** | **MISMATCH** |
| skipped | 1,620 | 1,620 | match |
| xfailed | 10 | 10 | match |

STOPPED per R3 rather than reporting a green.

### The two failures — both MINE, both static ratchets, neither a defect

```
FAILED tests/unit/tooling/test_bash_oracle_resolution.py::test_no_bash_oracle_outside_resolver
FAILED tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py::test_no_direct_spawn_in_oracle_bearing_modules
```

Both name the same file and the same two cells:
`test_input_cursor_contract_4b4.py:248` hardcoded `/opt/homebrew/bin/bash`,
and `:214` used `subprocess.Popen`. Nothing about the CLOSE is implicated —
every behavioural pin and every must-hold passed.

**Root cause, stated honestly:** I built a bespoke two-phase feed harness
(threads + `Popen` + an explicitly-named oracle) because Phase A's probe
instruments legitimately work that way, and I carried that shape into the
PIN suite without checking what the repo already required of test modules.
`CLAUDE.md` documents the anti-spawn guard, and 4B.2's end-to-end suite had
already solved the identical "bytes must arrive AFTER the deadline" problem
inside the sanctioned runner. Phase A's instrument conventions are not the
test suite's conventions, and I did not re-derive which I was in.

### Fix — comply, never allowlist (4B.2 lesson 3)

Commit `2f355fc3`. Adopted the 4B.2 pattern: the delay lives INSIDE the
script under test (`{ cat head; sleep LATE; cat tail; } | ...`), so every
launch goes through `run_psh`/`run_bash`, the harness resolves the oracle,
and payload bytes come from files via `cat` rather than a shell `printf`
whose octal escapes differ between shells. Per-arm files.

The rewrite made leg B's assertion STRONGER: it now asserts the
CONCATENATION of what the three reads delivered is byte-identical between
psh and bash. That is exactly the property the defect violated — a lost byte
shows immediately, while the declared D-4B.2-s1 split-placement difference is
invisible to a concatenation. The previous form pinned an exact per-variable
split, which is more brittle and less to the point.

### §10 figures are UNCHANGED by the fix

- node count still **16** for that file (`--collect-only`), so the +40
  collection delta and the 23,875 expectation stand unamended;
- still **11 of 16 RED at base** e3924ed3, re-verified in a detached probe
  worktree after the rewrite (`tmp/w4b4/instr10_red_on_base.out`);
- both previously-failing ratchets now PASS, verified file-scoped;
- `ruff check psh tests tools` → All checks passed.

New tip for gate run 2: **2f355fc3**.

---

## §12 GATE RUN 2 — GREEN, exactly the pre-registered figures

Tip **2f355fc3**. Single run, awaited in-turn (exceeded the 600s foreground
window, moved to background per the sanctioned handling, polled to
completion; the turn never ended with it in flight).

| Figure | §10 pre-registered | Gate run 2 | Verdict |
|---|---|---|---|
| passed | 23,875 | **23,875** | **MATCH** |
| failed | 0 | **0** | **MATCH** |
| skipped | 1,620 | **1,620** | **MATCH** |
| xfailed | 10 | **10** | **MATCH** |

`grep -cE '^FAILED|^ERROR' tmp/gate-2.txt` → **0**. Both phases PASSED
(phase 1 parallel + phase 1b serial). Transcript `tmp/gate-2.txt`.

**Zero flakes**, stated explicitly: no test failed and was retried, and no
cell in this slot's suites is retried or tolerant. The two `serial`-marked
classes this slot adds (the timeout cells and the M8 arms) ran in phase 1b
without xdist, which is why their real deadlines cannot be starved by
siblings.

The +40 landed exactly where pre-registered: 23,835 + 40 = 23,875, with
skips and xfail unmoved — so nothing was skipped INTO existence to make the
number work, which a passed-count-only check could not tell apart.

### Not-yet-run at this point

compare-bash (`python -m pytest tests/behavioral --compare-bash -n auto -q`)
— the sanctioned form, token requested at D5, expectation **3,046/26 EXACT,
movement +0** per §10 line 335.

---

## §13 COMPARE-BASH — EXACT, movement +0

Sanctioned form only (never `run_tests.py --compare-bash`):
`python -m pytest tests/behavioral --compare-bash -n auto -q` at tip
`2f355fc3`. `--collect-only` count taken FIRST (the argument is a directory,
not a file/node-ID): **3,072 collected**, which reconciles exactly with
3,046 + 26.

| Figure | §10 line 335 | Measured | Verdict |
|---|---|---|---|
| passed | 3,046 | **3,046** | **EXACT** |
| skipped | 26 | **26** | **EXACT** |
| movement | +0 | **+0** | **EXACT** |

Transcript `tmp/compare-bash-1.txt`, exit 0. No golden case added, modified
or deselected — the pre-registered reason holds: the closed faces require a
stranded surplus, which no golden case constructs.

---

## §14 DISCHARGE AUDIT — every claim row against its evidence

Counts DERIVED from the artifacts named, never hand-tallied.

| # | Claim | Proof-shape | Evidence |
|---|---|---|---|
| 1 | Both dispatch corruption faces reproduce at this worktree | CHARACTERIZATION vs bash, two-level discriminator | `instr01.out` |
| 2 | Stranding routes = TIMEOUT, ERROR, malformed-split; `_pushback` unreachable | BY-ELIMINATION (static closed loop) + CHARACTERIZATION (tripwire, 0 hits) | `instr02.out` §STATIC/§DYNAMIC |
| 3 | The gap is the two UNHOOKED surfaces; rebind/fork surfaces are clean and diverge by s1 alone | CHARACTERIZATION, decomposed per cell | `instr03.out`, `instr04.out` |
| 4 | NEW symmetric face: a frame's surplus escapes INTO real stdin | CHARACTERIZATION vs C-locale bash, with no-surplus control | `instr03.out` |
| 5 | s1-toward-bash ALONE closes legs A/B; cannot reach the malformed route | MUTATION-PROVEN (injected emulation) with a live-injection validity control | `instr06.out` |
| 6 | s1-toward-bash costs ≥22 must-not-flip nodes | MUTATION-PROVEN, substrate limit STATED (in-process only ⇒ lower bound) | `instr05_s1_cost.out` |
| 7 | CLOSE fixes all faces with controls held | MUTATION-PROVEN (injected emulation v2, tripwired) | `instr07.out`, `instr08.out` |
| 8 | 9 red-on-base site/frame divergences → 0 | REVERT-PROVEN (base vs tip, same instrument) | `instr09_base.out` → `instr09_tip.out` |
| 9 | 11 of 16 new behavioural cells RED at base | REVERT-PROVEN at a detached base worktree | `instr10_red_on_base.out` |
| 10 | Every new hook regresses loudly if it stops firing | MUTATION-PROVEN, 5 arms each with a discrimination row | `test_input_cursor_m8_locks_4b4.py`, green in gate 2 |
| 11 | `_pushback` cannot return silently | static ratchet | same file, `test_pushback_buffer_is_not_reintroduced` |
| 12 | 4B.2 seam suites untouched | CHARACTERIZATION (70/70 file-scoped; whole set green in gate 2) | `tmp/gate-2.txt` |
| 13 | Gate EXACT vs pre-registration | measured, both-end derived | §12, `tmp/gate-2.txt` |
| 14 | compare-bash EXACT +0 | measured | §13, `tmp/compare-bash-1.txt` |

**Rows carrying a stated limit, so no reader infers more than was measured:**
row 6 (lower bound — the in-process plugin never reached the subprocess
suites); row 7 (the emulation covered the builtin-frame and exec-dup paths
only, which is why the LANDED code was then re-measured by rows 8-9); row 2's
dynamic half (characterization over the driven set, which is printed).

**I1 row (d) is NOT closed** and is not claimed to be: the stranded lookahead
byte remains invisible to a forked child. Pinned both-sides so it stays
visible.

---

## §15 FINAL TIP AND FREEZE

**FINAL TIP: `2f355fc3`** — `tests: route the timeout cells through the typed
shell-oracle runner`.

Ten commits, per-hunk:

| # | SHA | Kind |
|---|---|---|
| 1 | `c551fc73` | prod — the 2-line registry rule, its own declared hunk |
| 2 | `8517d70d` | prod — registry API (`bind_dup`, frame scoping, `dup_alias_fds`) + docstring |
| 3 | `43f17314` | prod — the hooks (frame scoping, all three dup sites) |
| 4 | `1a5c4baf` | prod — ruff import ordering (formatting only) |
| 5 | `feca9b60` | prod — P1 `_pushback` removal |
| 6 | `8560de3f` | **test-only, DECLARED** — 4B.2 pin rewiring incl. M8 witness rename |
| 7 | `09f57450` | test — new pin suites + 4B.4 M8 locks |
| 8 | `3d285b56` | docs — subsystem docs + user-guide note (D-4B.2-s1 discharge) |
| 9 | `78839d6f` | docs — the D-1 two-word hunk, under R3's fence lift |
| 10 | `2f355fc3` | test — ratchet compliance for the timeout cells |

MECHANICAL TIP RULE acknowledged: any further commit after this declaration,
even comment-only, gets a SendMessage declaring it BEFORE it lands.

**Instrument manifest:** `tmp/w4b4/MANIFEST.txt`, 29 entries, self-excluding
(`__pycache__` excluded as derived and environment-dependent), md5
`fb7b2ebd2da32b47a8b605a6fb8c8637`.

**FREEZE.** Previous freeze md5: **(none — first freeze of this ledger).**
This ledger is FROZEN as of the final-tip declaration above. Corrections
after this point are a SendMessage plus a dated addendum after the verdict,
or a supervised edit under an explicit ruling.
