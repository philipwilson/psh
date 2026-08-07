# Slot 4B.3 — History state machine (MEDIUM-7 + carry #32) — third 4B slot

**Charter:** integrator plan §6 Wave 4 bullet 4B.3 + sequence §9 Package
4B item 4: *"Keep history file-read position independent from in-memory
deletion and apply the normal `HISTSIZE` policy to `history -s`."* Plus
**carry #32 closure** (LEDGER Part B row 32: `-a`/`-c`/`-n`
append/read-counter model — "CLOSE via slot 4B.3, same counter family as
MEDIUM-7"). Exit criterion (sequence §9): *"History `-r/-n/-d/-s/-a/-w`
state-machine sequences match Bash and respect memory limits without
duplicate file lines."*

**Base:** bd13b303 (v0.771.0 + 4B.2 addendum). Branch
`fix/remediation-4b-3`, worktree `/Users/pwilson/src/psh-r4b-3`.
**Base figures (you RE-DERIVE in your first gate run):** attestation
d5a4f30a-committed (gated ef5b5e7d): 23,698 passed / 1,620 skipped /
10 xfail; ruff clean; mypy clean; compare-bash 3,046/26 EXACT.

**This slot HAS shell-observable behavior deltas by design** — all
three defect legs are user-visible in interactive shells. Each flip is
a DECLARED toward-bash delta with red-on-base pins; anything ELSE
shell-observable that moves is a STOP. Expected compare-bash movement:
**+0** unless you pre-register otherwise (history is interactive-gated;
the golden/behavioral suites run `-c`/script modes) — if any golden
case you add CAN run under `--compare-bash`, count its nodes per the
4B.2 DEV-3 lesson (2 nodes per case) and pre-register the exact figure.

## The defects, integrator-probed at bd13b303

`tmp/w4b3-dispatch-probes/probe_medium7_history_cursors.py` (run at the
base checkout, discriminator verified; outputs verbatim; harness =
piped `--norc -i` subprocess, HISTFILE in probe-owned scratch —
REUSE THIS SHAPE for your cells):

1. **Leg A — cursor conflation** (`history_manager.py#delete_entry`,
   :328-338): seed file `seedA seedB seedC`; `history -d 1`;
   `echo seedD >> $HISTFILE` (external append); `history -n`; `history`.
   bash: `{seedA:0, seedB:1, seedC:1, seedD:1}` — the file counter
   stays 3, `-n` adds only seedD. psh: **seedC:2** — `delete_entry`
   decremented `_file_read_len` 3→2, `-n` re-read seedC. The finding's
   exact shape (r22 MEDIUM-7).
2. **Leg B — `-s` HISTSIZE bypass** (`history_manager.py#store_entry`,
   :249-255): HISTSIZE=3, HISTIGNORE=`history *:history` (so the
   probe's own invocations never record and `add_to_history`'s trim
   never masks the store); 5× `history -s sN`; `history`. bash: 3
   listing lines (`s3 s4 s5`). psh: **all 5** — `store_entry` appends
   with no cap ever applied.
3. **Leg C — carry #32 counter model** (`clear_history` resets
   `_file_read_len=0`): empty file; `echo seedX`; `-a`; `-c`; `-n`;
   `history`. bash: `echo seedX` ABSENT from the final listing (`-n`
   after `-c` re-reads nothing already consumed). psh: **re-materialized**.

## Integrator recon facts (verify, then lean on)

- The two markers (`history_manager.py` :47-55): `_file_synced_len` =
  in-memory entries already persisted (drives `-a`/exit-save slices);
  `_file_read_len` = default-file lines already consumed (drives `-n`).
  They are DIFFERENT quantities with different owners. MEDIUM-7's root
  cause: `delete_entry` and `clear_history` treat the READ cursor as if
  it were an index into the in-memory list. It is not — it is a
  position in the FILE, which memory operations do not move.
- `delete_entry`'s adjustment of `_file_synced_len` (the SYNC marker)
  is a separate question from the READ cursor: probe what bash's `-a`
  appends after a `-d` before deciding whether the sync-marker
  adjustment is also wrong or is psh-correct for its merge model.
- `store_entry` is called from the builtin's `-s` arm
  (`psh/builtins/shell_state.py`), AFTER the CV3 strip machinery has
  run. The CV3 strip family (B4/B5/R4/M3/H1 — line-scoped flag,
  single-physical gate, recording gate, delete-failure) is SETTLED and
  heavily pinned — the HISTSIZE cap goes in/around `store_entry`, never
  by touching `_strip_own_invocation`.
- `add_to_history`'s trim shifts `_file_synced_len` when it drops from
  the front (the v0.447 regression guard) — your `-s` cap must do the
  SAME marker maintenance or you recreate that regression under a new
  producer. Both cursors, not just one: derive what a front-drop does
  to `_file_read_len` from the bash model you probe in Phase A.
- bash's counter (its `history_lines_in_file`) semantics are SUBTLE —
  the carry #32 row says exactly that and declined to pin without the
  model. Your Phase A derives the model from PROBES of live bash
  5.2.26, op by op — never from theory or from bash source reading
  alone (source may inform WHERE to probe, probes are the evidence).
- Named-file operations (`history -r/-n/-a/-w otherfile`) deliberately
  leave the default-file markers alone (`_is_default_file`) — probe
  what bash does for named files (does ITS counter move?) before
  accepting or flipping that rule; it is currently load-bearing for
  the exit-save model.
- psh's exit save (`save_to_file`) is the v0.447 concurrency-safe
  append-merge under an exclusive lock — a DELIBERATE improvement over
  bash's last-shell-wins truncate. It is a must-hold, not a
  bash-parity surface. If the bash counter model you derive CONFLICTS
  with the merge model (e.g. bash semantics require truncate-on-exit
  or a different `-a` slice), that is a STOP-AND-PROPOSE with the
  probe row, never a silent regression of v0.447.

## Phase A must settle (probe, don't argue; bash 5.2.26 oracle)

1. **The bash counter-model table (ruling slot (a) — GO gate for
   Phase B).** For each op — startup load, `-r`, `-n`, `-a`, `-w`,
   `-c`, `-d` (single + range), `-s`, normal recording, exit save —
   probe what bash does to (i) the in-memory list, (ii) the file, and
   (iii) the read/append counters (observable via a subsequent `-n`
   and `-a`). Both default-file AND named-file variants where the op
   takes a filename. Sequences, not just single ops: the exit
   criterion says STATE-MACHINE SEQUENCES. Minimum sequence battery:
   the three probe legs; `-d` then `-a`; `-d` then exit-save; `-c`
   then `-r`; `-c` then `-a` (bash: what does `-a` append after
   clear?); `-r` twice (duplicates? — psh's `-r` re-appends, bash?);
   `-n` twice; `-w` then `-n`; `-a` to a NAMED file then `-n` default;
   external-truncate (file shrinks below counter) then `-n` — the
   underflow face; HISTSIZE trim colliding with both cursors.
2. **`-s` cap semantics.** Where does bash apply HISTSIZE for `-s` —
   at store, at next record, at listing? Probe with HISTIGNORE
   blocking the invocation record (the leg-B shape) AND without.
   Also: `-s` with multiple args (one joined entry — verify), `-s`
   under erasedups/ignoredups (does HISTCONTROL apply to `-s`? psh
   says no — verify vs bash), and `-s` when HISTSIZE=0 / negative
   (psh: negative = unlimited — must-hold unless bash disagrees).
3. **Interplay with the CV3 strip.** The leg-B harness used HISTIGNORE
   to suppress recording; WITHOUT it the strip fires first. Verify
   the composed order (record → strip → store → cap?) matches bash's
   observable listing for the plain interactive spelling.
4. **Carry sweep (STANDING dispatch-checklist item — 4B.2 lesson 7).**
   LEDGER Part B rows touching history: #29 (heredoc history trailing
   newline — RE-CARRIED cosmetic: state disposition, don't absorb
   unless trivially subsumed by a cell you already need), #32 (CLOSES
   here — its probe shape is leg C), #34 (PROMPT_COMMAND piped-`-i`
   artifact — MUST NOT "fix"; it constrains your harness reading, not
   your subject), #35 (eval'd outer-single `history -p` — expansion
   ENGINE, fenced out). Phase A table gets a disposition row for each.
5. **Piped-vs-PTY validity.** Carry #34 proves piped `-i` can be
   artifact-bearing. For each defect leg, state whether the piped
   harness is measuring the SUBJECT (history state machine) or could
   be measuring the harness. If any leg's bash behavior differs
   piped-vs-PTY, the PTY reading wins and the piped cell is labelled.
   (Expectation from the dispatch probes: the state machine is
   harness-independent — verify per leg, at minimum for leg C whose
   bash counter behavior is the subtlest.)

## Pins YOU create

Red-on-base (per-cell isolation — 4B.1 lesson 3): the three legs as
end-to-end piped-`-i` subprocess cells; the sequence battery cells
that the bash table shows diverging at base. Must-hold: the CV3 strip
family's existing pins stay green (named siblings below); the alias
contract (in-place mutation — every new marker-maintenance path uses
slice/del, never rebind); surrogateescape on all five file paths;
HISTFILESIZE=0 truncate guard; the v0.447 merge save (concurrent
two-shell append cell exists — find it, keep it green); erasedups'
`_file_synced_len` adjustment; `-w`/`-a` named-file behavior per the
probed bash table. M8 mutation locks (loud-diagnostics driver, fresh-
checkout certification with tmp/ ABSENT — 4B.2 lesson 2): cursor-
decrement-reintroduced (delete_entry), reset-to-zero-reintroduced
(clear_history), cap-dropped (store_entry), plus whatever Phase B's
design adds — each arm with a kill reason and a must-stay-green
discrimination row. Composition cells: `-d` × `-n` × external append
(leg A is one point — cover range-delete and delete-above/below-cursor);
`-c` × `-r` × `-a`; `-s` cap × front-drop marker maintenance ×
subsequent `-a` (no duplicate file lines — the exit criterion's last
clause); HISTSIZE trim × `-n`.

## Must-NOT-flip

- The CV3 strip family: `tests/conformance/bash/
  test_cv_carry_characterization.py` history rows,
  `test_history_p_interactive_conformance.py`, and the H1/R4/M3 pins —
  READ THEM FIRST (NAME-VS-BODY applies).
- The list-alias contract
  (`tests/unit/interactive/test_history_alias_contract.py`).
- Byte doctrine: surrogateescape on load/save/-w/-a/-r/-n.
- v0.447 concurrency-safe exit save (append-merge under lock;
  last-shell-wins must NOT return).
- HISTCONTROL/HISTIGNORE recording semantics (ignorespace/ignoredups/
  erasedups — including erasedups' sync-marker arithmetic).
- `history -p` expansion behavior (carry #35 stays carried).
- Everything 4B.1/4B.2 shipped (lookup + input-decoder suites) and all
  4A surfaces.
- compare-bash: EXACT-or-pre-registered (see the +0 expectation above).

## FENCES (stop-and-report BEFORE touching)

- **4B.4's subject**: InputCursor contract — untouched.
- **History EXPANSION engine** (`history_expansion.py`,
  `history_result.py`): carry #35's subject, fenced. Reading for the
  strip interplay is fine; editing = stop-and-propose.
- **The CV3 strip machinery** (`_strip_own_invocation` and the
  `_history_line_*` state flags): settled by the boundary campaign's
  closing verification — compose around it, never modify it.
- **`save_to_file`'s locking/merge model**: marker maintenance feeding
  it may change (that's the slot); the lock/merge/HISTFILESIZE
  mechanics themselves = stop-and-propose (see the v0.447 recon fact).
- **Line editor / HistoryNavigator**: consumes the list via the alias
  contract; no edits.
- D-4A.*, D-4B.1-s*, D-4B.2-s* successor rows and all D-3.x:
  MUST-NOT-ABSORB. In particular D-4B.2-s1/s2/s3 stay 4B.4/registered.

## Slot-specific test hygiene

- **Piped `-i` subprocess harness** (the dispatch-probe shape): every
  cell creates HISTFILE inside its OWN scratch (mktemp under the
  test's tmp; fresh-checkout leg is standing — no fixed names, no
  reliance on repo tmp/ existing: 4B.2 BL-1). Env scrubbed of HIST*
  and PROMPT* before setting the cell's own values.
- Interactive-family subprocess cells that only pipe stdin need no
  PTY and no serial marker unless they signal/job-control; PTY cells
  (if item-5 forces any) go through the `tests/conftest.py`
  interactive gate with inline justification (the 4B.2 precedent) and
  carry `assert_tree_under_test` (F-4 lesson: pexpect inherits cwd;
  the resolved `__file__` is the fact).
- History cells must not read the USER's real history: HISTFILE is
  always explicit; `--norc` always passed.
- Timing is not this slot's subject — no deadline cells expected; if
  any appear, 4B.2's timing-hygiene floor applies (measured deadlines
  ≥1s, hang detection ≥4×, serial where starved).

## Pre-declared ruling slots

- **(a)** Phase A bash counter-model table + sequence battery +
  carry-sweep dispositions (GO gate for Phase B).
- **(b)** Any conflict between the probed bash model and psh's
  deliberate improvements (v0.447 merge save; named-file marker rule)
  — stop-and-propose with the probe rows; the ruling picks
  bash-parity or documented-deviation per surface.
- **(c)** Anything pulling toward the expansion engine, the CV3
  strip, or 4B.4's contract — stop-and-propose with the census row.

## Rules

The FULL binding rule set is `docs/reviews/evidence/
boundary_remediation_2026-07/4a.1-rescue/brief.md` §Rules — binding
verbatim (never-touch list, dead-drop + ACK + md5 chain, mechanical
tip rule, ledger freeze + freeze-md5-in-declaration, per-hunk staging,
SHA paste-from-instrument, pre-registration + GO-binding citation,
RN-Cdoc, CERT-ROW-BEFORE-CLAIM, NAME-VS-BODY — your named siblings:
the CV3/history suites listed under Must-NOT-flip plus
`tests/unit/interactive/test_history*.py`: READ THEM FIRST —
instrument discipline, the 13 D-3.4 lessons + D-3.5 + 3.x sets, axis
quantification, discharge audit, gate rules (ONE heavy run
machine-wide, unpiped pgrep first, foreground, never shell-`&`, NEVER
`run_tests.py --compare-bash` — use `python -m pytest tests/behavioral
--compare-bash -n auto -q`), oracle rules (PATH bash
`/opt/homebrew/bin/bash` 5.2.26, explicit argv, never /bin/bash),
project tmp/ only, peer-escalation/permission-laundering wrapper).
PLUS the D-4A.1 additions (red-on-base re-derived at declared tip;
"all X except Y" as measured splits; test-created scratch dirs; no
glob-deletes outside own mktemp scratch). PLUS the 4A.2 lessons
(labelled controls for non-discriminating cells;
claim-boundaries-before-verdict; hostile-to-own-headline-cells). PLUS
the **11 banked 4B.1 lessons** (unpiped exit-status-bearing checks;
doc sweeps search the NAME; per-cell red-on-base; open-class boundary
declarations, demonstrated not enumerated; premise-before-figure for
any perf ruling; per-class split integrity; self-excluding manifests +
handoff-by-declaration; loud M8 companion diagnostics; standing
ARTIFACT-VERIFICATION release leg at the TAG; sign-off protocol
DEFINED BY YOU; CERT-ROW-BEFORE-CLAIM applies to integrator rows too).
PLUS the **11 banked 4B.2 lessons, all binding here**: (1) A/B probes
never let either side under test generate the stimulus; stimulus
scripts get a validity control; (2) PYTHONDONTWRITEBYTECODE=1 for
mutation-lock drivers; M8 drivers diagnose EVERY precondition loudly
incl. their scratch parent; M8 certification at a FRESH checkout with
tmp/ absent; (3) static-ratchet trips: rename the string, never
allowlist; (4) the search path is a request, the resolved `__file__`
is the fact (cwd outranks PYTHONPATH under `python -m`; pexpect
inherits cwd); (5) every hash/count/SHA in a handoff or certification
is GENERATED BY THE COMMAND that records it, and the RECEIVER
RECOMPUTES on receipt — both directions; (6) reconcile every sourced
number against every figure it bears on; (7) LEDGER carry sweep for
the slot's own name = standing dispatch-checklist item (done above —
verify it); (8) timing-hygiene floor applies to MEASURED deadlines;
(9) the SIX-LEG SIGN-OFF TEMPLATE is the STANDING shape for
behavior-changing slots — discriminator-first, per-cell defect legs,
must-hold, no-silent-change, M8-at-fresh-checkout, FALSIFICATION leg
(revert hunks → defect cells must fail), zero-flakes stated
explicitly; (10) a silently-dropped commitment is bounce-grade even
when the measurement behind it turns out fine; (11) no
replay/reconstruction of a compliant-looking record — the honest
violation + fault row IS the record.
New axes for this slot: **OP SEQUENCE × CURSOR STATE** (each
`-r/-n/-d/-s/-a/-w/-c`/load/save op × read-cursor and sync-marker
positions relative to the op's range: above/at/below/spanning) and
**FILE IDENTITY × MARKER OWNERSHIP** (default file vs named file vs
externally-mutated file × which markers each op may move).

Done = Phase A table + rulings + the three legs landed per the ruled
bash table with red-on-base pins flipped + carry #32 closure cell +
sequence battery green + M8 + composition cells + must-not-flip green
+ compare-bash movement = exactly the pre-registered figure + doc
sweep (`history_manager.py` module/method docstrings tell the
two-marker story truthfully; `interactive/CLAUDE.md` history rows
verified; user guide history section checked for claims needing
conformance backing) + green gate + ruff + mypy + discharge audit +
complete ledger → completion report with declared final tip + frozen
ledger.
