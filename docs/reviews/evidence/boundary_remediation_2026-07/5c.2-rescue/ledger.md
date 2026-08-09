# Slot 5C.2 — slot ledger (hub decomposition + dead API)

**Base** `3a3e0782` (v0.777.0 + 5C.1 addendum). **Branch**
`fix/remediation-5c-2`. Charter: sequence §11 Package 5C (second half),
Checkpoint R ruling CR-R1, Wave 5 slot map W5-R1, plus the D-5B.2-dead row
registered by 5B.2 for this slot.

Every claim row below carries its instrument anchor and the commit that
discharges it. Counts are DERIVED by the named instrument, never hand-tallied.

---

## Part 1 — the finding that shaped the slot

The campaign's function-length census counts raw source lines, and the slot
brief treated its 60 rows as 60 hubs and two of them as "campaign growers".
Measured (`A9_hub_anatomy.py`, confirmed independently by the integrator's own
probe on 6 rows):

| claim | measured |
|---|---|
| census rows below 100 EXECUTABLE lines | **58 of 60** |
| rows ≥100 executable AND non-nested | **2** (`expand_history` 101, `_build_if_statement` 100) |
| rows that are a nested def inside ANOTHER row | **3** ⇒ distinct bodies **57**, not 60 |
| `ShellState.__init__` | 323 nominal = **94 executable + 191 comment** |
| `ReadBuiltin.execute` v0.776→v0.777 | nominal **+11**, executable **−3**, comment **+14** |
| `ParseTreeBuiltin.execute` v0.776→v0.777 | nominal **+6**, executable **−3**, comment **+9** |

Both named "growers" had SHRUNK in code and grown in provenance comments.
Verified two ways sharing no machinery: `A9` classifies per-line from the AST
at each SHA; `A10b` classifies the diff itself. They agree exactly.

**Consequence, ruled (c) and binding:** the hub ledger's threshold is
EXECUTABLE lines. A ratchet on the nominal metric would have fired on slot
5C.1 for narrowing an exception net and documenting why — a
documentation-suppression device aimed at the practice this campaign enforces.

---

## Part 2 — discharge audit

| row | disposition | commit | evidence |
|---|---|---|---|
| **MEDIUM-15** (hub decomposition element) | hub ledger landed with all 60 base rows dispositioned; ruled set of 6 executed; growth ratchet live. **The O(k²) `ParseSession` element is OUT by ruling R1**, following 5A to the RESUMABLE-PARSER successor campaign | `d68572d9` + vii–xv | `A9`, `A14`, `B3` |
| **D-4B.4-s3** `IOManager.with_redirections` | **DELETED** | `2c3efce7` | census `A8`/`A11`; 146 occurrences / 43 the different symbol / **0** call sites |
| **D-5B.2-dead** `state.foreground_pgid` | **DELETED, full chain** (3 writes, property, protocol member, Q2 rows, tests, docs) | `59fcb26b` | `B1` three-arm parity: 392/392 identical, RED control names its own suite |
| **four zero-witness members** | **DELETED** | `cfa01dd1` | `A11` (112 defs scanned); `git log -S` provenance splits them |
| **`try_resolve_bash`** (LEDGER L301) | **DELETED**, detection branches pruned | `3bd46cf7` | `A8` cell; zero real consumers |
| **`AliasManager.has_alias`** | **KEPT** — test-only API, not dead code (ruled) | — | `A11b` (0 production / 4 test refs) |
| **D-5C.1-s1** Q2 subclass edges | **CLOSED** | `e6d4cbc0` | drift enumerated: exactly ONE new candidate, NARROW_SAFE'd; 2 offenders + 2 controls |
| **D-5C.1-s2** sub-expander typing | **CLOSED** | `f863d5e5` | `B11` mypy-load-bearing per member, control measured |
| **D-5C.1-s3** | POINTER ONLY — verified untouched (post-campaign owner) | — | — |
| **D-5B.1-s1** (flake) | not tripped this slot | — | — |
| **CR-D1..CR-D6** | none touched — verified | — | — |
| **MEDIUM-16** | not regressed; sig census IMPROVED 633/478 → **632/477** | `5472078d` | `A4` at tip |

---

## Part 3 — the six seams

Each flipped its own hub-ledger row in the same commit. Zero-delta proven per
seam against a materialised base checkout.

| seam | commit | nominal | ledger row | A/B cases |
|---|---|---|---|---|
| `ParseTreeBuiltin.execute` | `1dd4871b` | 106 → 44 | removed | 18 |
| ↳ **the one NON-pure-move edit in the six** | | | | this seam also added a `ValueError` where the format chain previously fell through to a write with `output` UNBOUND. Unreachable through the shell (the scan rejects any other format with rc 2), so zero-delta holds vacuously on that arm — but it IS a semantic edit, not a move, and a discharge-audit reader must see it here rather than infer it. Pinned by a direct-call test (`e6d4cbc0`), forcing-proven by `B10`, and the pin was corrected in the fix round to pass a real `Program` |
| `TestBuiltin.evaluate_unary` | `8f774d49` | 136 → 57 | removed | **525** |
| `PrintBuiltin._parse_options` | `a683730c` | 102 → 88 | removed | 38 |
| `OperatorRecognizer.recognize` | `31a760c0` | 101 → 67 | removed | 32 |
| `parse_invocation` | `8f3a232b` | 130 → **116** | **STAYS**, disposition → DECOMPOSED-THIS-SLOT | 34 × 16 fields |
| `apply_var_fd_redirect` | `cd782fe8` | 107 → 83 | removed | 15 |

`parse_invocation` was the pre-registered borderline; it resolved to the
*stays* branch, giving the final ledger **55 = 52 + 3 POINTER**.

**The M8 re-point (seam 6).** The extraction made a 4B.4 mutation lock stop
biting for its own reason: the anchored line survived verbatim but became the
sole statement of its `if`, so DELETING it left an empty block and the arm
failed with `IndentationError`. Fenced, ruled, re-pointed — find UNCHANGED,
`breaks`/`stays_green` UNCHANGED, seeded meaning UNCHANGED; only the
mutation's spelling of "this statement does not run" changed.

---

## Part 4 — faults: seven self-caught, two integrator-caught, one verifier-caught

The original heading here read "all self-caught". That was false as written —
rows 1 and 8 were caught by the integrator, and the blocker below by the verify
round. Corrected rather than quietly softened, because a fault table that
overstates its own self-discipline is the same class of defect as the ones it
records.

| # | fault | caught by | repair |
|---|---|---|---|
| 1 | D2's ACK and chain md5 STALE (composed early, appended late) | integrator | owned, not rewritten; **mechanical fix: self-guarding append** that aborts on a moved file — it then caught two real crossings |
| 2 | `@overload` key collision + a too-thin ledger reason | **the ledger's own arms, on its author** | causes fixed, assertions untouched |
| 3 | moved-key enumeration missed MUTATION ANCHORS as a category | seam-6 execution | category sweep `B12`: 87 literals, exactly ONE mutation-shaped |
| 4 | fully-annotated pin violated in vii/viii; sig census drifted 632→635 | `A4` census | `5472078d`. **A green NON-STRICT mypy says nothing about annotation coverage** |
| 5 | "200 passed" in a commit message where the run said 121 | self, pre-proceed | amended |
| 6 | `B13` A/B arms shared a fixture dir — manufactured a false divergence | the probe's own first run | per-arm fixture isolation |
| 7 | `B14` counted base by grep and tip by collect-only — invented a `+9` | self, pre-table | one method both sides |
| 8 | fn total omitted from the code-complete report | integrator | re-derived **3,236**, matching |
| 9 | scratch file written to system `/tmp` | self | reported; project `tmp/` only |
| 10 | **the gate-wait deadlocked on a `pgrep` that matched itself** — and the deeper error is that I waited on PROCESS ABSENCE when the STATE was in the file the whole time | integrator | bracket-form patterns that cannot self-match; verify from the summary line. **REPEAT OF A BANKED LESSON** (5B.2 lesson 5): carried in my own rules chain, quoted in D2.1, not applied at authoring time |
| 11 | **BLOCKER: a dangling `with_redirections` cite left in a LIVE orientation doc** (`ast_data_flow.md:252`) — D1 called the residue "prose in `docs/`" and stopped, bucketing by DIRECTORY instead of dispositioning per file | **verify round** (3 of 4 verifiers, independently) | one-word fix, sentence verified TRUE at the code; both-sides fault — the integrator's R2 accepted the doc-set census without demanding per-file disposition |

**Lesson candidates banked:** a guard that never bit its author is a guard
nobody has tested · anchor-present ≠ arm-functional · a green instrument is
not an observed property · an A/B whose arms share mutable state manufactures
its finding · two methods on the two sides of a delta is the D-3.5 error ·
**verify from STATE, not process absence — liveness is a proxy, and one that
can self-match** · **a census bucketed by DIRECTORY is not a census: `docs/`
holds both frozen records and live orientation docs, and only per-file
disposition tells them apart.**

---

## Part 5 — the five FILE-growers (ruled in R2; the file half, discharged here)

The fn-growers are dispositioned as ledger rows. The five grown FILES are
dispositioned here, because a committed ledger must discharge that half on its
own rather than by pointing at a dead-drop entry.

Measured `53253642` (v0.750.0, campaign start) → base, by `A10b`:

| file | at v0.750.0 | at base | net code | net comment | disposition |
|---|---|---|---|---|---|
| `pattern_engine.py` | 742 | 1,681 (+939) | **+665** | +181 | **COHESIVE AS-IS, ledger the fns.** The +665 is the glibc `sm_loop.c` matcher port that REPLACED a regex approximation — growth by design, not accretion. Its one ≥100 fn (`_BashMatcher._match`) is JUSTIFIED-KEEP: the control flow IS the ported semantics |
| `operands.py` | 529 | 811 (+282) | **+205** | +44 | **COHESIVE AS-IS.** **ZERO** fns ≥100 — a large file of small functions, which is the shape decomposition produces |
| `file_redirect.py` | 1,140 | 1,422 (+282) | **+151** | +107 | **COHESIVE AS-IS, ledger the fns.** Two ≥100 fns, one of them decomposed this slot (`apply_var_fd_redirect`), the other (`apply_permanent_redirections`) JUSTIFIED-KEEP as an fd transaction with lease rollback |
| `command_assignments.py` | 592 | 823 (+231) | **+165** | +38 | **COHESIVE AS-IS, ledger the fns.** One ≥100 fn (`commit_prefix`), JUSTIFIED-KEEP: the `_pop_staging_scope` ordering is load-bearing |
| `manager.py` | 1,003 | 1,204 (+201) | **+134** | +54 | **COHESIVE AS-IS.** **ZERO** fns ≥100 |

Unlike the fn-growers, these grew in real CODE. File growth is not per se a
defect, and the two files with zero ≥100 functions are the argument: size
without hubs is the outcome decomposition aims at.

---

## Part 6 — gate and final figures

Gate and compare-bash ran at **`a35edb3f`**; the fix round moved the tip
afterwards and gate-2 re-ran (see the completion report for the final SHA).

| cell | pre-registered | measured | verdict |
|---|---|---|---|
| gate passed / skipped / xfail | 24,003 / 1,620 / 10 | 24,003 / 1,620 / 10 | EXACT |
| compare-bash | 3,046 / 26, +0 | 3,046 / 26 | EXACT |
| fn total | 3,236 | 3,236 | EXACT |
| fns ≥100 nominal | 55 | 55 | EXACT |
| hub-ledger entries | 55 = 51 + 1 + 3 | 55 | EXACT |
| sig census A / B | 632 / 477 | 632 / 477 | EXACT |
| ALLOWLIST | 8 | 8 | EXACT |
| caps floor | 66 / 177 | 66 / 177 | EXACT |
| conformance · golden · never-touch ×7 | zero diff | zero diff | EXACT |

---

## Part 7 — corrections and environment notes

**A10's first two cells are SUPERSEDED by `A10b`.** `A10_growth_kind.sh` piped
a diff into `python - <<'PY'`, where the heredoc claims stdin — so the
classifier read an EMPTY stream and printed all-zero counts. The committed
`.out` retains those zeros: **an executed transcript is evidence and is never
edited after the fact**. `A10b_diff_classify.py` is the corrected instrument
(it runs `git diff` itself) and its figures are the ones every claim uses. The
zeros are a record of the fault, not a measurement.

**Canonical-metric correction (fix round, N13).** The Phase A survey
instrument `A9` counted a code line carrying a TRAILING comment as a comment
line. The guard's canonical `executable_lines` does not. Where this ledger and
the early dead-drop entries said **58 of 60** below 100 executable, **2** rows
≥100, and `ShellState.__init__` **94/191**, the canonical figures are **57 of
60**, **3**, and **95/190**. Both grower deltas (−3/+14, −3/+9) are unchanged,
and so is every conclusion. The guard's docstring now carries the canonical
numbers and names the discrepancy.

**Environment note (verify round N4).** A verifier reproducing this branch in a
worktree under system `/tmp` saw 16 failures that do not occur in a project-tree
checkout. Recorded as an environment property, not a branch defect: psh's
suites create fixtures under the project tree and some resolve paths relative
to it. The gate figures in Part 6 are from a project-tree run.

