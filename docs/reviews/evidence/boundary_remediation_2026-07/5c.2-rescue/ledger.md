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

## Part 4 — faults, all self-caught

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

**Lesson candidates banked:** a guard that never bit its author is a guard
nobody has tested · anchor-present ≠ arm-functional · a green instrument is
not an observed property · an A/B whose arms share mutable state manufactures
its finding · two methods on the two sides of a delta is the D-3.5 error.
