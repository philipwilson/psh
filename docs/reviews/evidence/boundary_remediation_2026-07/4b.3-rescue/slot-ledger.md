# SLOT LEDGER — 4B.3 (history state machine; MEDIUM-7 + carry #32)

**Dev:** dev-4b-3. **Worktree:** `/Users/pwilson/src/psh-r4b-3`.
**Branch:** `fix/remediation-4b-3`. **Base/tip at open:** `bd13b303567188246cc75e7fc5f02914a50f32ab`.
**Oracle:** `/opt/homebrew/bin/bash` — GNU bash, version 5.2.26(1)-release
(aarch64-apple-darwin23.2.0), recorded by `bash --version` in every probe
transcript.

Format follows the 3.4/3.5 property-bound shape: disposition table,
pre-registrations, certification rows (instrument-file anchor + evidence SHA,
counts DERIVED not hand-tallied), discharge audit, bounced-rows replay.

---

## §0 — Round 1 (D1) opening record

### §0.1 Hash chain (both directions; 4B.2 lesson 5)

| Artifact | Declared to me | Recomputed by me (`md5 -q`) | Verdict |
|---|---|---|---|
| `INTEGRATOR-INBOX.md` (at R0) | `fc0c4c0b67a628735f808d22a278eafb` | `fc0c4c0b67a628735f808d22a278eafb` | MATCH |
| `tmp/brief-4b3.md` (worktree copy) | `30215199226a7bb423a189b30bb4d7dc` | `30215199226a7bb423a189b30bb4d7dc` | MATCH |
| `tmp/remediation-ledgers/briefs/4b.3.md` (canonical, MAIN checkout) | (brief asserts identical) | `30215199226a7bb423a189b30bb4d7dc` | MATCH — canonical == worktree copy |
| `tmp/w4b3-dispatch-probes/probe_medium7_history_cursors.py` (MAIN) | — | `215163db3831118cfb1a948f40bbbe16` | recorded for provenance |

### §0.2 Dispatch-probe reproduction AT THIS WORKTREE

Instrument: `tmp/w4b3-probes/probe_repro_dispatch.py` (faithful re-run of the
integrator probe with `REPO` = this worktree and the discriminator ASSERTED,
not merely printed). Transcript: `tmp/w4b3-probes/repro_dispatch.txt`.

```
DISCRIMINATOR: /Users/pwilson/src/psh-r4b-3/psh/__init__.py
ORACLE: GNU bash, version 5.2.26(1)-release (aarch64-apple-darwin23.2.0)
TIP: bd13b303567188246cc75e7fc5f02914a50f32ab
A bash: {'seedA': 0, 'seedB': 1, 'seedC': 1, 'seedD': 1}
A psh : {'seedA': 0, 'seedB': 1, 'seedC': 2, 'seedD': 1}

B bash: {'s1': 0, 's2': 0, 's3': 1, 's4': 1, 's5': 1}  (listing lines: 3)
B psh : {'s1': 1, 's2': 1, 's3': 1, 's4': 1, 's5': 1}  (listing lines: 5)

C bash: 'echo seedX' in final listing: 0
C psh : 'echo seedX' in final listing: 1
```

**All three legs reproduce at my tip, figure-for-figure identical to the
integrator's dispatch declaration.** Leg A seedC:2 (psh) vs 1 (bash);
leg B 5 listing lines (psh) vs 3 (bash); leg C seedX re-materialized (psh)
vs absent (bash).

### §0.3 NAME-VS-BODY findings (named siblings read BEFORE planning)

| # | Claim in brief | Body as read | Disposition |
|---|---|---|---|
| N1 | must-not-flip: `tests/conformance/bash/test_cv_carry_characterization.py` **history rows** | That file contains carries #18/#19/#21/#24/#27/#30/#31 and **ZERO** history rows (`grep -c history` → `0`) | Brief pointer is WRONG. The CV3 strip family's pins live ONLY in `tests/conformance/bash/test_history_p_interactive_conformance.py` (sole tree-wide match for `_history_line_pending_strip` / `single_physical` / `_history_recording_active` / `CV3`). Must-not-flip obligation stands at the REAL location; recorded, not silently reinterpreted. |
| N2 | (unstated) | `_file_read_len` — MEDIUM-7's own subject — has **ZERO** references anywhere in `tests/` (`grep -rn _file_read_len tests/` → no matches). Only `_file_synced_len` is pinned (`test_history_persistence.py`). | The READ-cursor model is entirely UNPINNED at base. This is the gap the slot fills; it also explains how the conflation survived. |
| N3 | named siblings list | The suites that actually exercise `-w/-r/-a/-n/-d/-s` are **not** in the brief's list: `tests/unit/builtins/test_history_flags.py` (the file-sync-flag suite), `tests/integration/interactive/test_history.py`, `tests/unit/interactive/test_history_files_surrogateescape_i4.py`, plus 3 rows in `tests/behavioral/golden_cases.yaml`. | Read/treated as named siblings for NAME-VS-BODY purposes; they are the real must-hold surface for this slot. |

### §0.4 Carry sweep — VERIFICATION of the brief's sweep (4B.2 lesson 7)

Instrument: `grep -in "histor" docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md`.
The brief's Phase A item 4 enumerates #29 / #32 / #34 / #35. The sweep of the
LEDGER's own Part B finds **two further history rows the brief omits**:

| Row | LEDGER text | In brief? | My proposed disposition |
|---|---|---|---|
| 25 | `history -ps` clustered flag — **"ATTACHED to slot 4B.3 as a rider (trivial option-scan fix while history builtin is open)"** | **NO** | **OWED RIDER — ruling requested.** The LEDGER attaches it to THIS slot by name. Probed red-on-base (§0.5). Proposal: take it, with its own probed bash semantics (the `-p`/`-s` precedence is a real question, not a pure option-scan edit). |
| 10 | history `-p` failed-arg wording — RE-CARRIED (message wording only, both rc 1) | **NO** | **STAYS CARRIED.** Cosmetic wording on the `-p` path; `-p`'s engine family is fenced (#35). Not absorbed; disposition stated so it is not silently dropped. |
| 29 | heredoc history trailing newline — RE-CARRIED (cosmetic) | yes | Disposition at D2 per brief (state, don't absorb unless trivially subsumed). |
| 32 | `history -a/-c/-n` counter model — CLOSE via 4B.3 | yes | CLOSES here; probe shape = leg C. |
| 34 | PROMPT_COMMAND piped-`-i` only — recorded harness artifact | yes | MUST NOT "fix". Constrains harness reading (item-5 piped-vs-PTY validity), not the subject. |
| 35 | eval'd outer-single `history -p "!!"` — RE-CARRIED | yes | Expansion engine — FENCED. |

### §0.5 Rider #25 characterization (red-on-base, at my tip)

Instrument: `tmp/w4b3-probes/probe_rider_carry25.py`; transcript
`tmp/w4b3-probes/rider_carry25.txt`. Piped `--norc -i`, HISTFILE in
probe-owned scratch, discriminator asserted.

| Case | bash 5.2.26 | psh @ bd13b303 |
|---|---|---|
| `history -ps hello` then `history` | listing `1 hello / 2 history` (the `-s` store happened; invocation stripped) | `-ps: invalid option`, rc 2; listing shows the raw invocation |
| `history -sp hello` then `history` | same as `-ps` | `-sp: invalid option`, rc 2 |
| `history -ps hello; echo rc=$?` | `rc=0` | `rc=2` |
| `history -p hello` (control) | `hello` | `hello` — MATCH |
| `history -s hello` (control) | listing `1 hello` | listing `1 hello` — MATCH |

Note the self-inconsistency at base: psh's own usage string already advertises
`history -ps arg [arg...]` while the hand dispatch rejects the clustered form.
Note also that bash's `-ps` performed the STORE and produced no separate `-p`
print line — the flag precedence under clustering is a probed question for
Phase A, not an assumption.

---

## §0.6 — Phase A plan (see inbox D1)

Executed before D2; results land in §1 below as the bash counter-model table,
the sequence-battery results, the carry dispositions and the proposed design.

---

## §1 — PHASE A RESULTS (executed 2026-08-07, tip bd13b303)

Instruments (all under `tmp/w4b3-probes/`, all piped `--norc -i` unless the
row says PTY, all with the discriminator ASSERTED and `bash --version`
recorded in the transcript):

| Instrument | Transcript | Subject |
|---|---|---|
| `hlib.py` | — | shared harness |
| `probe_repro_dispatch.py` | `repro_dispatch.txt` | the three dispatch legs at my tip |
| `probe_rider_carry25.py` | `rider_carry25.txt` | carry #25 (`-ps`) |
| `probe_a1_ops.py` | `a1_ops.txt` | per-op observable triple |
| `probe_a1b_counters.py` | `a1b_counters.txt` | per-op counter measurement |
| `probe_a1c_pending.py` | `a1c_pending.txt` | pending-for-append after a read |
| `probe_a3_scap.py` | `a3_scap.txt` | `-s` cap semantics |
| `probe_a3b_frontdrop.py` | `a3b_frontdrop.txt` | **VOID read-counter column** (see FAULT F-1) |
| `probe_a3c_frontdrop_fixed.py` | `a3c_frontdrop.txt` | front-drop vs counters, corrected |
| `probe_a2_sequences.py` | `a2_sequences.txt` | 17-cell sequence battery |
| `probe_a4_stripinterplay.py` | `a4_strip.txt` | CV3 strip × `-s` × cap |
| `probe_a4b_producers.py` | `a4b_producers.txt` | producer × cap |
| `probe_a5_pty.py` | `a5_pty.txt` | piped-vs-PTY validity |

### §1.1 INSTRUMENT FAULT F-1 (self-disclosed)

The read-counter instrument derives the counter from
`post_mem[len(pre_mem):]`. That identity holds only while nothing trims the
list. Under a small `HISTSIZE` the marker pull is itself trimmed, so `post` is
the list's TAIL and the subtraction is meaningless. This produced bogus bash
counters — ">=6" in `probe_a3_scap.py` §4 and "23"/"24" in
`probe_a3b_frontdrop.py`. **Both columns are VOID and are not used in any
table below.** Corrected in `probe_a3c_frontdrop_fixed.py` by raising HISTSIZE
to 500 immediately before the marker write (HISTIGNOREd so the raise is not
itself recorded), with a control cell proving the corrected instrument reads a
known counter of 3. A1/A1b/A1c ran at the DEFAULT HISTSIZE where no trim
fires; those measurements stand.

### §1.2 THE BASH COUNTER MODEL (measured, bash 5.2.26)

bash keeps ONE global read counter (its `history_lines_in_file`) and one
append marker. Measured effects:

| op | READ counter | APPEND marker / pending slice |
|---|---|---|
| startup load | := lines loaded | loaded entries NOT pending |
| normal recording | unchanged | entry becomes pending |
| `history -s` | unchanged | entry becomes pending |
| `-r FILE` (default or named) | **:= that FILE's line count** | read lines NOT pending |
| `-n FILE` (default or named) | **:= that FILE's line count** | **read lines ARE pending** |
| `-a FILE` (default or named) | **+= lines written** | pending slice consumed |
| `-w FILE` (default or named) | **unchanged** | **NOT consumed** |
| `-c` | **unchanged** | consumed (list empty) |
| `-d` any range | **unchanged** | **decremented by one per deleted entry, regardless of which** |
| HISTSIZE front-drop | **unchanged** | shifts with the drop |
| external file shrink | unchanged (may exceed file length; harmless) | — |

Two consequences worth stating because they contradict the exit criterion's
own "without duplicate file lines" clause: bash's `-n` then `-a` writes the
just-read line to the file a SECOND time (`a2_sequences.txt`, "-n then -a"),
and so does `-n` then exit-save; and bash's `-w` then `-n` re-reads the
just-written entries into memory.

### §1.3 THE THREE CHARTERED LEGS — precise measurements

| leg | bash | psh @ bd13b303 |
|---|---|---|
| **A** `-d` then `-n` | read counter unchanged at 3 for `-d 1`, `-d 1-2`, `-d 3` | counter 3→2, 3→1, 3→2 respectively; `-n` re-reads deleted-past lines |
| **B** `-s` under HISTSIZE | capped at store (HISTSIZE=3, 5 stores → `s3 s4 s5`; HISTSIZE=1 → `s3`; HISTSIZE=0 → nothing stored) | no cap ever applied |
| **C** `-c` then `-n` | counter unchanged → nothing re-read | counter reset to 0 → whole file re-materialised |

### §1.4 LEG B IS WIDER THAN THE CHARTER'S WORDS

`a3_scap.txt` / `a3b_frontdrop.txt`: bash's `history -s` goes through the
SAME recording policy as a typed command, not merely the HISTSIZE cap —

| filter | bash applies to `-s`? | psh |
|---|---|---|
| `ignorespace` | YES (` spaced` not stored) | stores it |
| `ignoredups` | YES (2nd `dup` dropped) | stores both |
| `erasedups` | YES (prior `aaa` erased) | keeps both |
| HISTIGNORE | YES, matched against the STORED text (`s*` blocks `-s s1`) | stores it |
| HISTSIZE cap | YES, at store | never |

psh's `store_entry` docstring asserts the opposite ("no HISTCONTROL/HISTIGNORE
filtering — bash keeps an explicit `-s` entry"): **measured FALSE**.
(No contradiction with the dispatch probe's leg B, which used
`HISTIGNORE='history *'`: that pattern matches the INVOCATION text, while
HISTIGNORE is applied to the STORED text `s1`.)

### §1.5 PRODUCER × CAP (`a4b_producers.txt`) — "respect memory limits"

| producer | bash | psh |
|---|---|---|
| startup load | capped | capped — MATCH |
| normal recording | capped | capped — MATCH |
| `history -s` | capped | **NOT capped** (leg B) |
| `history -r` | capped | **NOT capped** (10 lines into a HISTSIZE=4 list) |
| `history -n` | capped | **NOT capped** (11 entries at HISTSIZE=4) |
| lowering `HISTSIZE` | trims retroactively at once | **does not** (10 entries kept at HISTSIZE=3) |

`a4_strip.txt` explains why leg B is not visible in ordinary interactive use:
the NEXT recorded command's `add_to_history` trim drags the list back to the
cap, so all five plain-spelling cells MATCH. The divergence needs recording
suppressed (HISTIGNORE/HISTCONTROL) — which is exactly the dispatch probe's
shape and a common real configuration.

### §1.6 TWO DATA-INTEGRITY FACES FOUND OUTSIDE THE THREE LEGS

Same counter family, on the brief's own FILE IDENTITY × MARKER OWNERSHIP axis;
in BOTH, psh is worse than bash:

- **`-w NAMED` then exit-save loses the session's new command.** psh's
  `write_history` advances `_file_synced_len` for ANY target, so after
  `history -w otherfile` the pending entry is never written to $HISTFILE.
  bash saves it. (`a2_sequences.txt` "-w NAMED then exit-save"; PTY-confirmed.)
  The docstring's justification — "bash marks it written regardless of which
  file" — is **measured FALSE**.
- **`-r NAMED` leaks the other file's lines into $HISTFILE.** psh's
  `read_history` leaves `_file_synced_len` alone for a named target, so those
  lines look new and a later `-a`/exit-save appends them to $HISTFILE. bash
  marks `-r`'s lines non-pending for every target. (`a2_sequences.txt`
  "-r NAMED then -a default"; PTY-confirmed.)

### §1.7 WHERE psh IS BETTER THAN BASH (ruling slot (b) candidates)

| face | bash | psh | recommendation |
|---|---|---|---|
| `-n` then `-a` | writes the read line to the file AGAIN (duplicate) | does not | KEEP psh — the exit criterion says "without duplicate file lines" |
| `-w` then `-n` | re-reads the just-written entries into memory | does not | KEEP psh |
| `-d` of a SYNCED entry while another is pending | drops the pending entry from the save (data loss) | saves it | KEEP psh — v0.447 no-data-loss family |
| named-file read setting the DEFAULT counter | one global counter; `-r other` corrupts the default cursor | per-default-file cursor (`_is_default_file`) | KEEP psh |

### §1.8 PIPED-VS-PTY VALIDITY (`a5_pty.txt`)

All three chartered legs AND both new data-integrity faces AND the `-r` cap
face reproduce under a REAL pty (pexpect, `dimensions=(40,200)`, explicit
`PS1`) in the SAME direction as the piped harness. No leg's bash behaviour
differs piped-vs-PTY, so the piped cells are measuring the SUBJECT, not the
harness. Carry #34's artifact does not reach this state machine.

### §1.9 CARRY DISPOSITIONS

| row | disposition |
|---|---|
| #25 `history -ps` | red-on-base (§0.5); RULING REQUESTED — the LEDGER attaches it to this slot, the brief omits it |
| #29 heredoc history trailing newline | STAYS CARRIED — cosmetic, not subsumed by any cell this slot needs |
| #32 `-a/-c/-n` counter model | CLOSES here — leg C measured precisely (§1.2/§1.3); bash's `-c` leaves the counter |
| #34 PROMPT_COMMAND piped-`-i` | NOT touched; used only as the reason for the §1.8 PTY validity leg |
| #35 eval'd outer-single `history -p` | FENCED (expansion engine) |
| #10 history `-p` failed-arg wording | STAYS CARRIED — cosmetic; `-p` family fenced |

### §1.10 MUST-HOLD INVENTORY (located before proposing — claim-boundaries-before-verdict)

| must-hold | where pinned |
|---|---|
| v0.447 concurrent two-shell append | `tests/unit/interactive/test_history_persistence.py::test_concurrent_sessions_do_not_clobber` |
| in-session trim does not lose new entries (v0.447 marker) | same file, `::test_in_session_trim_does_not_lose_new_entries` |
| `-c` marker reset keeps post-clear commands | same file, `::test_history_dash_c_does_not_lose_subsequent_commands` |
| surrogateescape on ALL FIVE paths | `tests/unit/interactive/test_history_files_surrogateescape_i4.py` (load/save/-w/-a/-r/-n cells present) |
| HISTFILESIZE=0 truncate guard + HISTSIZE edges | `tests/unit/core/test_histfile_histsize_vars.py` |
| HISTCONTROL/HISTIGNORE recording semantics | `tests/unit/interactive/test_histcontrol_histignore.py` — pins `add_to_history` ONLY; no cell pins `-s`, so routing `-s` through the filters flips nothing here |
| list-alias contract | `tests/unit/interactive/test_history_alias_contract.py` |
| CV3 strip family | `tests/conformance/bash/test_history_p_interactive_conformance.py` (NOT `test_cv_carry_characterization.py` — finding N1) |
| file-sync flags | `tests/unit/builtins/test_history_flags.py` |
| golden rows | `tests/behavioral/golden_cases.yaml`:6658/6664/6678 |

---

### §1.11 RIDER BATTERY (carry #25, ruled IN by R1(a))

Instruments: `probe_a6_rider.py` / `a6_rider.txt`,
`probe_a6b_rider_rc.py` / `a6b_rider_rc.txt`. Plain spelling (no HISTIGNORE):
the CV3 strip is part of the subject.

**INSTRUMENT FAULT F-2 (self-disclosed).** The first `probe_a6b_rider_rc.py`
wrote `history ...; echo "===RC==="; echo "$?"`, so `$?` was the MARKER echo's
status, not the builtin's. Every row printed rc=0 — including `-pz`, which
both shells reject with 2. Caught because that known-2 row read 0. Corrected
to capture `rc=$?` on the same line as the builtin; the transcript now
discriminates 9 of 13 rows.

| spelling | bash 5.2.26 | psh @ bd13b303 |
|---|---|---|
| `history -ps hello` | rc 0; STORES `hello`, invocation stripped, **no `-p` print** | rc 2, `-ps: invalid option` |
| `history -sp hello` | **identical to `-ps`** | rc 2 |
| `history -ps` (no operand) | rc 0, no store | rc 2 |
| `history -p -s hello` (separate option WORDS) | rc 0; same as `-ps` — bash keeps parsing options | rc 0 but PRINTS `-s` and `hello` (psh stops option parsing at the first word) |
| `history -s -- x` | rc 0; stores `x` (`--` ends options) | rc 0; stores `-- x` |
| `-cw` / `-ca` / `-cd 1` | rc 0, both ops performed | rc 2 |
| `-an` / `-rw` / `-nr` | rc 1 (accepted, op failed) | rc 2 (rejected) |
| `-pz` / `-zs` | rc 2 — MUST-HOLD control | rc 2 — MATCH |

Two derived facts the rider design needs:

- **bash applies clustered flags in a FIXED INTERNAL ORDER, not left-to-right**:
  `-ps` and `-sp` are byte-identical in every observable, and in both the
  `-s` behaviour wins (store, no print).
- **Under a cluster the `-s` strip semantics apply**: the same-line cell
  `history -ps a; history -s b` leaves bash holding BOTH `a` and `b` — exactly
  matching the `history -s a; history -s b` control — so the cluster CONSUMED
  the line-scoped strip flag the way a bare `-s` does, and `-p`'s keep-the-flag
  rule does not apply. (Control `history -p a; history -s b` MATCHES between
  the shells and behaves differently, proving the cell discriminates.)

NON-DISCRIMINATING cells, labelled: A6's `-an` and `-rw` listing/file cells
produced identical observables in both shells despite bash accepting and psh
rejecting the spelling; only the A6b rc rows discriminate those two. A6's
`-ps`/`-sp` no-operand cells match on the listing and diverge only on rc.

---

## §2 — PROPOSED DESIGN (ruling-slot-(a) submission; posted as D2)

Every row cites the measured bash behaviour it implements.

| # | Change | Locus | Measured basis |
|---|---|---|---|
| P1 | Delete the `_file_read_len` adjustment | `history_manager.py#delete_entry` | bash's `-d` leaves the read counter at 3 in all three shapes (§1.2/§1.3) |
| P2 | Delete the `_file_read_len = 0` reset (keep the `_file_synced_len = 0` reset) | `#clear_history` | bash's `-c` leaves the read counter; the sync reset is what keeps post-clear commands persisting, and that cell MATCHES bash |
| P3 | Route `-s` through the ONE recording pipeline (`add_to_history`) | `#store_entry` | bash's `-s` applies ignorespace/ignoredups/erasedups/HISTIGNORE AND the cap AND the front-drop marker maintenance (§1.4) |
| P4 | Apply the cap + marker maintenance after the read paths' `extend` | `#read_history`, `#read_new_history` | bash trims after `-r`/`-n` (§1.5) |
| P5 | Advance `_file_synced_len` only for the DEFAULT target | `#write_history` | bash's `-w other` does NOT consume the pending slice; psh's does and LOSES the entry (§1.6) |
| P6 | Advance `_file_synced_len` for ANY target on `-r` | `#read_history` | bash marks `-r`'s lines non-pending for every target; psh's named-target path leaks them into $HISTFILE (§1.6) |

Deliberately NOT changed (declared deviations, both-sides pinned — ruling (b)):
psh's `-n` non-pending rule (bash duplicates the line into the file), psh's
`-w` read-cursor advance (bash re-reads), psh's `-d` sync-marker precision
(bash drops the pending entry), psh's per-default-file cursor (bash has ONE
global counter that a named-file read overwrites).

Out of slot (recommended successor row): bash trims retroactively when
`HISTSIZE` is LOWERED; psh does not. That is a variable-assignment hook in
`core/state.py`, not the history state machine.

## §3 — Pre-registrations

### §3.1 PRE-REGISTRATION FOR GATE RUN 1 (written BEFORE the run)

**Tip declared for this run:** see §3.2 (recorded at request time).
**Base figures** (brief, attestation `d5a4f30a`-committed, gated `ef5b5e7d`):
23,698 passed / 1,620 skipped / 10 xfail; ruff clean; mypy clean;
compare-bash 3,046/26 EXACT.

**Node-count delta — DERIVED, not estimated.** Collected with
`pytest --collect-only -q` at the tip and at a detached base worktree:

| set | tip | base | delta |
|---|---|---|---|
| 3 NEW files (unit 55 + conformance 51 + M8 11) | 117 | 0 | **+117** |
| 4 MODIFIED test files | 59 | 57 | **+2** |
| **total** | | | **+119** |

**Expected gate result:** **23,817 passed** (23,698 + 119) / 1,620 skipped /
10 xfail. No existing node changes status: the four modified files' pre-existing
cells all still pass (one was RENAMED and re-asserted to the bash-verified
value, which is a same-count replacement, not a delta).

**Expected-red pins: NONE.** Every cell is expected GREEN at the tip; the
red-on-base evidence is recorded separately in §3.3 from a detached base
worktree, not from this run.

**compare-bash: +0 — FIRM.** 3,046/26 EXACT expected unchanged. No golden case
added. Reasoning: history is interactive-gated and the behavioural suites run
`-c`/script mode; the three existing golden history rows
(`golden_cases.yaml`:6658/6664/6678) run at the default `max_history_size`
1000 with HISTCONTROL/HISTIGNORE unset, so neither the new `-s` policy nor the
cap can fire on them.

**ruff:** clean over `psh tests tools`. **mypy:** clean, 275 files.

**Flake watch:** the exit-trap family lives near the 4A.2 surfaces, not this
slot's; if THIS run flakes on that family it is instance 3 under the
third-instance-investigates rule and I report it immediately rather than
re-running (4a.1 brief §Rules, subtlety 8).

### §3.3 RED-ON-BASE EVIDENCE (measured at a detached base worktree, NOT at the tip)

Instrument: `git worktree add --detach /tmp/psh-4b3-base bd13b303`, new pin
files copied in, `PYTHONPATH` pinned to that tree, discriminator verified as
`/private/tmp/psh-4b3-base/psh/__init__.py`; worktree removed after.

| suite | red at base | green at base (declared must-hold controls) |
|---|---|---|
| unit (55 cells) | **34** — of which **13 BEHAVIOURAL** and **21 API-ABSENT** (the pending accessor does not exist at base) | 21 |
| conformance (51 cells) | **35** | 16 |

The 13/21 split is DERIVED by classifying each base failure's message, not
hand-tallied: an `AttributeError` naming `_pending*` is API-absent, anything
else is behavioural. **Stated explicitly because it matters to the claim:** an
API-absent failure is NOT behavioural red-on-base evidence, so the behavioural
case for the pending-set work rests on the 13 unit cells plus the 35
conformance cells, all of which fail at base on an assertion about behaviour.

### §3.4 PIN-COUNT RE-REVISION (all four figure sets labelled)

| stage | figure | why it moved |
|---|---|---|
| D1 SKETCH | ~40–55 | pre-Phase-A guess |
| D2 FIRM | 84 | after the bash table, the two data-integrity faces, the rider battery |
| D3 FIRM | 90 | + the R2-F2 swallow face |
| D5 firm | 117 nodes (115 new + 2 net-new in modified files) | parametrisation expands cells into nodes (e.g. 3 delete shapes, 3 HISTSIZE values, 11 cluster rc rows); the D2/D3 figures counted CELLS as written, this counts NODES as collected |
| **D6 ACTUAL** | **119 nodes** (117 new + 2 net-new) | + b5's two cells, required by R4-1 |

The unit + conformance CELL count is 106 (55 + 51), against a D3 commitment of
90; the 16 above it are the cluster rc matrix rows, the delete-shape
parametrisations that the rider and leg-A work turned out to need, and b5.
M8 arms: **10**, as pre-registered.

### §3.5 b5 — REGISTERED per R4-1 (declaration debt, not a defect)

The DEFAULT-file `-w` then `-a` face. Measured both sides
(`probe b5_default_w_a.txt`; integrator probe
`integrator_verify_d4_claims.py` md5 `5f4b28fcd27345657f6ac512ca704a98`,
equal to its source at MAIN):

| cell | bash 5.2.26 | psh |
|---|---|---|
| `-s x; -w; -a` (default file) | `['x','x']` | `['x']` |
| same, seeded $HISTFILE | `['S1','S2','x','x']` | `['S1','S2','x']` |
| typed command instead of `-s` | duplicated | single |
| **CONTROL** `-s x; -a; -a` (no `-w`) | `['x']` | `['x']` — **MATCH** |

The control matters: it shows b5 is specific to `-w` failing to consume bash's
counter, NOT a general "bash duplicates on every append" claim.

**b5 disposition: KEEP psh** (no-duplicate family, same exit-criterion clause
as b1). Both-sides pinned at
`test_history_state_machine_conformance.py::TestDeclaredDeviations::
test_write_then_append_on_the_DEFAULT_file_bash_duplicates` plus its control.
Both cells are GREEN AT BASE and that is CORRECT: psh's behaviour here is ruled
correct and unchanged by this slot — b5 was a missing DECLARATION, not a
missing fix. Recorded so the green-at-base status is never mistaken for a
vacuous pin.

### §3.6 DECLARED-DEVIATION REGISTER (complete, for the Part D wording)

| id | face | bash | psh | status |
|---|---|---|---|---|
| b1(i) | `-n` then `-a` | duplicates the read line into the file | does not | KEEP psh |
| b1(ii) | pending swallowed by a read | — | was dropping typed commands | **FIXED** (defect) |
| b2 | `-w` then `-n` | re-reads the just-written entries into memory | does not | KEEP psh |
| b3 | `-d` while another entry is pending | drops the pending entry from the save | keeps it | KEEP psh |
| b4 | named-file read vs the DEFAULT cursor — **TWO observables**, see §7.10 | one global counter: a named read corrupts the default cursor (FORWARD), and an already-advanced counter suppresses a named read (MIRROR) | per-default-file cursor does neither | KEEP psh |
| **b5** | `-w` then `-a` on the DEFAULT file | writes the entries twice | writes once | KEEP psh |

Exit-criterion resolution (Part D wording): *"match Bash" binds the
state-machine observables — the in-memory list, cursor behaviour and exit
status — and every read-free composition. The FILE-WRITE model keeps v0.447's
no-loss/no-duplicate guarantee as the ruled deviation family, because bash's
own positional `-a` both loses typed commands and leaks read ones whenever a
read or a `-d` falls between recording and saving.*


## §4 — Certification rows

## §5 — Discharge audit

## §6 — Bounced-rows replay

### §2.1 Doc-sweep reconnaissance (read-only, before Phase B)

| surface | state at bd13b303 | obligation |
|---|---|---|
| `history_manager.py#store_entry` docstring | claims "no HISTCONTROL/HISTIGNORE filtering — bash keeps an explicit `-s` entry" — **measured FALSE** (§1.4) | correct in Phase B |
| `history_manager.py#write_history` docstring | claims "bash marks it written regardless of which file" — **measured FALSE** (§1.6) | correct in Phase B |
| `history_manager.py#append_history` comment | claims "bash's `-a` marker is session-global" — **measured TRUE** (bash's `-a NAMED` advances the marker) | keep |
| `history_manager.py` class docstring + the `-w/-r/-a/-n` section comment (:235-241) | tells the two-marker story; the read-cursor half becomes accurate only after P1/P2 | update to the measured model |
| `psh/interactive/CLAUDE.md` "History: Single Writer" (:286-301) | asserts history has exactly ONE writer via `add_to_history` — **already inaccurate at base**, because `store_entry` is a second, unfiltered writer | P3 makes the existing documented invariant TRUE; note it in the sweep rather than rewriting the invariant |
| `psh/interactive/CLAUDE.md` five-file-path surrogateescape row (:43) | accurate | keep green |
| `docs/user_guide/04_builtin_commands.md` "history - Command History" (:1254-1283) | documents `history`, `history N`, `history -c` ONLY — no compatibility-table "Full support" row for the file-sync flags or `-s` | no new conformance-backing obligation is triggered; do NOT add a claim without its conformance test (`test_claims_have_tests.py` CLAIM_TESTS has one history entry, for expansion only) |
| `docs/user_guide/14_interactive_features.md` | mentions `history -c` and `HISTSIZE` in prose, no support claim | verify only |

### §2.2 Must-hold BASELINE at bd13b303 (pre-Phase-B)

`python -m pytest tests/unit/interactive/test_history_persistence.py
tests/unit/interactive/test_history_alias_contract.py
tests/unit/interactive/test_history_files_surrogateescape_i4.py
tests/unit/builtins/test_history_flags.py
tests/unit/interactive/test_histcontrol_histignore.py
tests/unit/core/test_histfile_histsize_vars.py -q`
→ **91 passed in 0.26s** (targeted subset, no gate token needed).

---

## §3 — ROUND 3: A1' RE-DERIVATION (R2-F1 bounce accepted)

Instrument: `probe_a1prime_model.py` / `a1prime_model.txt`. Integrator probes
copied and hash-verified BOTH directions:
`integrator_verify_d2_claims.py` md5 `f8b5c8e287d2a3a511aaa3a6f47f12a7`,
`integrator_verify_d2_p6_sharp.py` md5 `ad4d1cd1dafade3ae2b67d841722d062`
(each equals its source at the MAIN checkout).

### §3.1 BOUNCE ACCEPTED — my D2 `-a` row was WRONG

R2-F1 is right. My D2 table said "`-r FILE`: read lines NOT pending", framing
`-a` as an identity-keyed marker. Every A1c cell was consistent with BOTH that
model and a tail-count model, so the cell set could not discriminate — exactly
the D-3.5 instrument-mirror failure, in the form "a composition that cannot
separate two hypotheses is not evidence for either".

### §3.2 THE RE-DERIVED MODEL — bash's `-a` is a POSITIONAL TAIL WINDOW

    N = 0
    recorded command       -> N += 1
    `history -s` store     -> N += 1
    `-n` reading L lines   -> N += L        (read lines DO count)
    `-r` reading L lines   -> N += 0        (read lines do NOT count)
    `-d` deleting D        -> N -= D        (whichever entries)
    `-c`                   -> N = 0
    `-w`                   -> N unchanged
    `-a`                   -> writes history[len(history)-N:] BY POSITION,
                              then N = 0

Identity plays NO role. Encoded as code in the probe so it must predict every
cell; **it predicted all 9 pre-stated cells exactly** and cells 8 and 11
decided the two open rows (`-c` RESETS N; `-a` zeroes N).

The discriminating cells (tail window != identity set):

| cell | bash `-a` wrote | identity model would have written |
|---|---|---|
| K=2 typed, then `-r` 4 lines | `[R3, R4]` | `[true t1, true t2]` |
| K=4 typed, then `-r` 2 lines | `[true t3, true t4, Q1, Q2]` (a MIX) | the 4 typed |
| K=2 typed, then `-r` 2 lines | `[Q1, Q2]` | the 2 typed |
| typed, `-r` 2, typed, `-r` 2 | `[Q1, Q2]` | `[true a1, true b1]` |
| `-r` 4 FIRST, then 2 typed | `[true t1, true t2]` | same — **LABELLED CONTROL, does not discriminate** |

### §3.3 CONSEQUENCE — bash's own model BOTH LOSES AND LEAKS

In cell 1 bash wrote `[R3, R4]` to $HISTFILE: the other file's lines LEAKED in
and the session's two typed commands were LOST. The positional heuristic is
simply wrong whenever a read interleaves with pending entries. Three-way:

| model | typed commands kept? | read lines leaked? |
|---|---|---|
| bash (positional tail) | **NO — lost** | **YES** |
| psh @ base (single sync index) | YES | **YES** |
| correct identity model | YES | NO |

### §3.4 R2-F2 INDEPENDENTLY REPRODUCED — psh's read paths SWALLOW pending entries

A1' cells 6 and 7 reproduce it without being designed for it: after
`K typed; -n pulling L`, psh's `-a` wrote **`[]`** — `read_new_history` sets
`_file_synced_len := len(history)`, marking the still-pending typed entries as
synced, so they never reach the file. Cell 10 reproduces the P5 `-w NAMED`
loss the same way. So psh's "no duplicate" cleanliness on that composition is
PARTLY PRODUCED BY DATA LOSS, exactly as R2-F2 says.

### §3.5 ROOT CAUSE OF THE SWALLOW — a single index cannot express the state

After `S1 S2 S3` (synced), `t1 t2` (pending typed), `-n` appending `N1 N2`
(already on disk), the synced set is `{S1,S2,S3,N1,N2}` and the pending set is
`{t1,t2}` — **non-contiguous**. `_file_synced_len` is a contiguous-prefix
length, so it cannot represent this at all: advancing it swallows `t1,t2`; not
advancing it re-appends `N1,N2`. Every option below follows from that.

### §3.6 b1–b4 RE-CHARACTERIZED under the re-derived model

| id | face | status now |
|---|---|---|
| b1 | `-n` then `-a` | **SPLIT per R2-F2.** (i) "psh does not duplicate the read line" — candidate KEEP; (ii) "psh drops the pending typed line" — **DEFECT, fix**. The two were conflated in D2. |
| b2 | `-w` then `-n` | read-cursor question — HELD for R3 |
| b3 | `-d` of a synced entry while another is pending | recommendation KEEP psh, now with the correct mechanism: bash's `-d` decrements N positionally (cell 9 confirms), so deleting an UNRELATED old entry silently drops a pending one from the save |
| b4 | named-file read setting the DEFAULT counter | read-cursor question — HELD for R3 |

---

# §7 — ROUND-2 CORRECTIONS (2026-08-07, freeze LIFTED by R8)

Struck-and-corrected, never silently rewritten: the original text stays visible
with its correction beside it. Freeze at round 1 was
`c05102c0f67c81b118b3eae22e62bcf6`; a new freeze-md5 is declared with the
round-2 tip.

## §7.1 — BL-3: §1.11's action-selection rows were FALSE

**STRUCK (§1.11):** *"`-cw` / `-ca` / `-cd 1` | rc 0, both ops done"*.

**CORRECTED:** bash performs the clear/delete but SUPPRESSES the file
operation — when `-d` is present, or when `-c` is present WITHOUT a filename
operand. With an operand the file op runs. Measured
(`probe_bl3b_actionmodel.py`, `probe_bl3c_cw_asymmetry.py`,
`probe_bl3d_suppression.py`):

| cell | bash | reading |
|---|---|---|
| `history -cw` (no operand) | $HISTFILE untouched `['S1','S2']` | write SUPPRESSED |
| `history -cw "$HISTFILE"` | file truncated `[]` | write RAN — operand-sensitive |
| `history -cr` (no operand) | memory `[]` | read SUPPRESSED (the sharpest cell) |
| `history -cr "$HISTFILE"` | memory `['S1','S2']` | read RAN |
| `history -wd 3` | file untouched, entry deleted | write SUPPRESSED by `-d` |
| `history -cs STORED` | memory `['STORED']` | `-s` NOT suppressed |
| CONTROL `-c` ; `-w` (separate) | file truncated | proves the suppression is per-INVOCATION |

**Why the original was wrong — the same instrument failure a THIRD time.**
`a7_order.txt`'s `-cw` cell wrote to a NAMED file created EMPTY, so
"cleared then wrote an empty list" and "the write never ran" are the same
observable, and the base psh column matched vacuously because base rejected all
clusters. Every round-2 cell seeds a SENTINEL so untouched / written-empty /
rewritten are three distinct readings. Banked: **an instrument whose "after"
state is empty cannot distinguish "wrote nothing" from "did nothing" — seed the
target.**

## §7.2 — BL-2 / RN-15: the `-anrw` rc row was incomplete

**STRUCK (§1.11):** *"`-an` / `-rw` / `-nr` | rc 1 (accepted, op failed)"*.

**CORRECTED:** bash REJECTS the combination outright with
`bash: history: cannot use more than one of -anrw` on stderr; no op is
attempted. The rc-1 half was right, the characterisation was not, and shipping
it as "rc 1, no message" produced a silent-failure regression away from bash.
Instrument defect behind it (**FAULT F-6**): `probe_a7b_clustererr.py` filtered
stderr to lines containing `history`/`psh`/`bash` and then took `[:2]` — the two
job-control warnings that piped `-i` always emits occupy those slots, so the
real diagnostic was truncated out of the transcript. **A head-limited filter is
a silent evidence filter.**

## §7.3 — BL-1: the pending-set mechanism was a REGRESSION

**STRUCK (§2, P-row and the O3 description):** *"Pending is a MULTISET VIEW of
memory ... an entry that leaves `state.history` by ANY route thereby leaves
pending, so nothing is ever resurrected"*.

**CORRECTED:** text-keyed resolution let a surviving same-text entry satisfy a
deleted entry's debt, so a `-d`'d command WAS resurrected into $HISTFILE as a
duplicate — and the base was correct here. Owed is now one flag per
`state.history` POSITION (`_owed`), reconciled against outside tail deletions by
`_sync_owed`. R3's O3 ruling stands; the mechanism failed invariant 4 and was
replaced, not the ruling.

## §7.4 — RN-10: duplicate section numbering

**STRUCK:** two `## §3` sections (Pre-registrations at line 336, ROUND-3 A1'
re-derivation at line 486) with colliding subsection numbers, and §3.1's
forward reference *"Tip declared for this run: see §3.2"* pointing at a §3.2
that does not exist in that section.

**CORRECTED:** the A1' section is **§5** for all citation purposes
(`§5.1`–`§5.6` = its former `§3.1`–`§3.6`); the Pre-registration section keeps
`§3`. The tip declaration lives in inbox D6/D7 (`bc280e8f` at round 1), not in
a §3.2 — that forward reference is struck. The R6 token citation "§3.4/§3.5"
resolves to the PRE-REGISTRATION section and is unaffected.

## §7.5 — RN-11: the ledger's own promised sections were empty

**STRUCK:** `## §4 Certification rows`, `## §5 Discharge audit`,
`## §6 Bounced-rows replay` shipped as empty headers while the header block
promised all three.

**CORRECTED, with locations rather than duplicated content:**
- Certification rows → §3.3 (red-on-base split) and §3.4 (pin-count history).
- Discharge audit → inbox **D7**, table "DISCHARGE AUDIT", every row derived
  from the tree. R7 ruled gate figures stay OUT of the frozen ledger, so this
  is a pointer by ruling, not an omission.
- Bounced-rows replay → §5 (the A1' re-derivation, replaying R2-F1) and §7
  (this section, replaying the round-1 bounce).
**Part D at ceremony must draw on the inbox as well as this ledger.**

## §7.6 — RN-12: brief Phase-A sub-items without a named verdict

Probed and pinned all along, but never row-reported. Recorded now:

| brief item | verdict | pin |
|---|---|---|
| `-s` with multiple args = ONE joined entry | MATCHES bash (`echo hello world`) | `::test_multiple_args_become_one_entry` |
| `-s` under `HISTSIZE=0` | MATCHES (nothing stored) | `::test_histsize_caps_the_store[0-…]` |
| `-s` under NEGATIVE HISTSIZE = unlimited | MATCHES (must-hold held) | `::test_negative_histsize_is_unlimited` |
| `-r` twice | MATCHES (re-appends; no dedup) | `::test_read_twice_appends_twice` |
| `-n` twice | MATCHES (idempotent) | `::test_read_new_twice_is_idempotent` |

## §7.7 — RN-13: SHA anchors for the DELETED/FLIPPED verdicts

| verdict | commit |
|---|---|
| P1/P2 read-cursor adjustments DELETED | `ed326216` |
| `-s` routed through the recording policy | `6189fc7c` |
| P5 + the flipped `test_write_then_append_no_duplication` pin | `7fd43586` |
| rider P7 (cluster dispatch) | `b124e187` |
| `_file_synced_len` RETIRED under O3 | `47077827` |
| pin suites + M8 | `49fa33ea` |
| docs | `f825216c` |
| b5 registration | `bc280e8f` |
| **round-2 bounce fixes (BL-1..BL-4, RN-1/7/8/14)** | `8bb139ee` |

## §7.8 — Deviation register, ROUND-2 state

b1(i), b2, b3, b4, b5 KEEP-psh; b1(ii) FIXED. **No new deviation is added by
the round-2 fixes** — BL-2 and BL-3 moved psh TOWARD bash, and BL-1 restored a
property the base already had. The exit-criterion resolution sentence in §5.6
(formerly §3.6) is unchanged.

## §7.9 — INSTRUMENT FAULTS, cumulative

| id | fault |
|---|---|
| F-1 | read-counter delta arithmetic invalid under a trim; two columns VOID, re-measured with a control |
| F-2 | rc probe captured the marker `echo`'s status |
| F-6 | `probe_a7b_clustererr.py` head-limited its stderr filter, truncating bash's real diagnostic out of the transcript (behind BL-2) |
| F-7 | `probe_bl3_actionmodel.py`'s first detector inferred "delete fired" from the absence of the typed entry, which a CLEAR also produces — the `-cr`/`-cs` rows of `bl3_actionmodel.txt` are VOID; corrected in `probe_bl3b_actionmodel.py` with two orthogonal typed entries |
| F-8 | the empty-named-file confound in `a7_order.txt` (behind BL-3) — the round-1 form of F-7's family |

Process faults F-3 (unauthorised heavy run), F-4 and F-5 (dead-drop read-skips)
are recorded in the inbox at D4/D6/D7 and are unchanged.

---

## §3.7 — PRE-REGISTRATION FOR GATE RUN 2 (written BEFORE the run; R9 fast path)

**Tip:** `8bb139eefbdb0efe51acb6260330da22c090b355` (9 commits over
`bd13b303`). **Base figures** (attestation `d5a4f30a`-committed, gated
`ef5b5e7d`): 23,698 passed / 1,620 skipped / 10 xfail; ruff clean; mypy clean;
compare-bash 3,046/26 EXACT.

**Node delta — DERIVED by `--collect-only`, not estimated.**

| set | tip | base | delta |
|---|---|---|---|
| 3 NEW 4B.3 files (unit 58 + conformance 61 + M8 14) | 133 | 0 | **+133** |
| 4 MODIFIED test files | 59 | 57 | **+2** |
| **total** | | | **+135** |

Round-1 comparison, labelled: the delta was +119; round 2 adds **+16** nodes
(BL-1's four multiset cells net +3, BL-2's two channel cells, BL-3's seven
action-selection cells, BL-4's b4 both-sides cell, RN-4's two, and three new M8
arms), all listed in D9.

**Expected gate result: 23,833 passed** (23,698 + 135) / **1,620 skipped** /
**10 xfailed**. No existing node changes status; one class was RENAMED
(`TestClearResetsMarkers` → `TestClearResetsOwedEntries`) and one pin cell
renamed, both same-count replacements.

**Expected-red pins: NONE** at the tip. Red-on-base evidence is measured at a
DETACHED base worktree, never from this run.

**compare-bash: +0 — FIRM, unchanged.** 3,046/26 EXACT expected; no golden case
added in either round. The round-2 fixes are interactive-gated cluster and
owed-flag behaviour, none of which the `-c`-mode behavioural suites reach.

**ruff:** clean over `psh tests tools`. **mypy:** clean, 275 files.

**Pre-run evidence already in hand at this tip:** the 8,415-test targeted sweep
of `tests/unit/interactive/`, `tests/unit/builtins/`, `tests/conformance/bash/`
and `tests/unit/tooling/` passed 8,415 / 1 skipped / 8 xfailed (the run
disclosed as fault F-9).

**Flake watch:** unchanged — if THIS run flakes on the exit-trap family it is
instance 3 under the third-instance-investigates rule and I report immediately
rather than re-running.

---

## §7.10 — b4's MIRROR FACE, named and pinned (R12 required item)

**Previous freeze:** `75bb049538a56e019fa0393e0de07a8c` (freeze-chain rule,
adopted at R11). New freeze declared with the D13 tip.

b4's register text and cells covered ONE observable of bash's single global
read counter: a NAMED read overwrites it, so a later default `-n` re-reads
consumed lines. The integrator's re-verify attack (`-cn FILE`, a composition
absent from my suite) surfaced the SAME mechanism from the other side, and a
deviation face that lives in one probe is one probe away from being silent.

**MIRROR FACE:** because the startup load has already advanced the global
counter, bash's `history -n OTHER` resumes at that offset INSIDE the named
file — and can therefore read NOTHING. psh's per-default-file cursor starts a
named read at 0 and reads it.

Measured (`probe_b4_mirror.py` / `b4_mirror.txt`; integrator instrument
`integrator_reverify_operand_attack.py` md5
`618ba981b64fc9b9bd591ef15b41f3ad`, equal to its source at MAIN):

| default seed | named file | bash memory | psh memory |
|---|---|---|---|
| 1 line | 1 line | `['D1']` — read NOTHING | `['D1','O1']` |
| 1 line | 2 lines | `['D1','O2']` — resumed at offset 1 | `['D1','O1','O2']` |
| 2 lines | 3 lines | `['D1','D2','O3']` — offset 2 | all three |
| **0 lines (CONTROL)** | 2 lines | `['O1','O2']` | `['O1','O2']` — **MATCH** |

The zero-seed control is load-bearing: it proves the divergence is an OFFSET
into the named file, NOT a blanket suppression of named reads, and it blocks
the over-broad reading a single mirror cell would have licensed.

**Disposition: same as b4 — KEEP psh, declared deviation, both sides pinned**
(`TestNamedReadCursorDeviation::
test_named_read_new_resumes_at_the_global_offset_in_bash` plus
`::test_an_unadvanced_counter_reads_the_whole_named_file_in_both`). No design
change: psh's behaviour is the ruled per-default-file cursor operating exactly
as intended, and the mirror face is a second consequence of bash's model, not a
psh defect.
