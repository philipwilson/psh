# Slot 3.2 instruments (rescued from `tmp/slot32/` at ceremony)

Everything here re-runs against a checkout; the three bulk `.jsonl`
files were NOT rescued (568M total, all regenerable):

- `corpus_cells.jsonl` (9.7M): regenerate with `extract_cells.py` — it
  executes the committed 3.1 generators
  (`../../3.1-rescue/instruments/corpus*.py`) down to their bash-spawn
  boundary and reads their own `CELLS`. Expected censuses
  51,795 / 13,830 / 372,186; distinct union 428,144 (= 427,586 + 558
  per the 3.1 E-1 erratum).
- `arm_base.jsonl` / `arm_tip.jsonl` (292M each): produced by
  `equiv_arm.py`, one process per arm, each in its own detached
  worktree (`PSH_ROOT`/`PYTHONPATH` set; every instrument asserts its
  import discriminator and aborts on the wrong tree).

Key entry points:

| instrument | purpose |
|---|---|
| `equiv_prove.py --cells corpus_cells.jsonl` | full equivalence proof (428,144 cells × 27 relations/operators); self-tests: `--inject-arm tip` (must report exactly 1 disagreement, exit 1), `--blind` (must wrongly pass), `--same-tree` (must report 0) |
| `mutate.py [M<n>]` | replays all eight mutation classes (cp-backup, `filecmp`-verified byte-identical restore, `__pycache__` dropped after every revert); M8 re-introduces the round-1 blocker (ungated pre-filter) and is caught by the gate pin |
| `extract_cells.py` | regenerates the corpus universe from the committed 3.1 generators |
| `b1_repro.py` | round-1 blocker B1 reproduction at detached checkouts of both SHAs |
| `base_sub_perf.py` | the substitution perf table harness (D-2a basis: in-process op timing, one persistent Shell, compile outside the timer, steady state) |
| `base_mutability.py` | the MEDIUM-6 poisoning demos (red arm of the immutability pins) |
| `proto_design.py` | Phase A prototypes P1 (backward all-start DP) + P2 (memoized ok-table), correctness-gated 1,078 cells |
| `counter_gap.py` / `b3_blindspot.py` | the count_states/count_transitions blindness probes (round-1 B3) |

**Exhibits (do not regenerate — they are deliberately stale):**
`tip_sub_perf_out.txt` and `tip_sub_perf2_out.txt` are the two
LIVE-WORKTREE measurements behind dev fault #1 (slot-ledger §F1): both
predate the eager pre-filter (mtimes 12:52:01 / 12:55:47 vs all four
round-1 commits at 13:26) and show the eligible consecutive row LINEAR
where the committed round-1 tip measured 12.6s QUADRATIC. Preserved
under ruling R5(4) as the per-table-provenance lesson's evidence.

Perf figures throughout are in-process operation timings (D-2a basis);
the claims are ratio CLASSES per doubling, not absolute seconds.
Transition-count figures are deterministic integers (machine- and
load-independent), which is why tight bounds (4.6 on a measured
3.97–3.99) are safe there and would be flake generators on wall clock.
