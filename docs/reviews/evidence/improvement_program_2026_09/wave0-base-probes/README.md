# Wave 0 base probes — the 2026-09-06 re-verification transcripts (imported)

Imported at Wave 0.1 (package D, program §6 0.1 item 7) from the orchestration scratch
under `tmp/program-2026-09/` on the integrator's machine; that directory is gitignored, so
this copy is the committed provenance for `INVENTORY.json`'s `verification` fields and for
the critic passes recorded in `../critique_pass1.md` / `../critique_pass2.md`. Text only
(JSON, markdown, shell/python probe scripts and their `.out` transcripts, 432 KB); nothing
here is re-run by the suite. Every verify probe ran from a fresh `mktemp -d` with
`PWD`/`OLDPWD` unset, `PSH_STRICT_ERRORS=1`, against `/opt/homebrew/bin/bash`
5.3.15(1)-release and psh at `6459f1a6` (v0.779.0) — see each batch's `meta` block.

## `verify/` — per-cid re-verification batches (28 files, 137 results, 137 distinct cids)

Each file is `{"meta": {head, psh_version, oracle, python, date, probe_harness}, "results": [{cid, status, bash53_output, psh_output, note}…]}`
(all batches share the shape);
`INVENTORY.json` rows carry the same `verification` objects, merged by cid (fresh-only rows
F01–F16 / D1–D4 were re-verified by the integrator session and are not in a batch).

| file | results | cids | run |
|---|---:|---|---|
| `verify/batch-0.json` | 4 | C001…C005 | 2026-09-06 @ `6459f1a6` |
| `verify/batch-1.json` | 4 | C006…C009 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-2.json` | 1 | C010…C010 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-3.json` | 4 | C011…C014 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-4.json` | 4 | C015…C018 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-5.json` | 4 | C019…C022 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-6.json` | 4 | C023…C026 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-7.json` | 4 | C027…C030 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-8.json` | 4 | C031…C034 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-9.json` | 4 | C035…C038 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-10.json` | 4 | C039…C042 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-11.json` | 6 | C046…C056 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-12.json` | 6 | C057…C062 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-13.json` | 6 | C063…C068 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-14.json` | 6 | C069…C074 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-15.json` | 6 | C075…C080 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-16.json` | 6 | C081…C086 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-17.json` | 3 | C088…C097 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-18.json` | 6 | C103…C118 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-19.json` | 6 | C120…C128 | 2026-09-06 @ `6459f1a6` |
| `verify/batch-20.json` | 6 | C130…C147 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-21.json` | 6 | C151…C157 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-22.json` | 3 | C158…C163 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-23.json` | 6 | C164…C172 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-24.json` | 6 | C174…C183 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-25.json` | 6 | C184…C194 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-26.json` | 6 | C195…C206 | (no meta block; same harness, per the batch RESUME) |
| `verify/batch-27.json` | 6 | C207…C214 | (no meta block; same harness, per the batch RESUME) |

## `dedup/groups.json`

The dedup stage's merge groups (raw report ids → canonical cid), a dict with 1 top-level entries; the builder
script (`dedup/build.py`, 46 KB of Python) is deliberately not imported — the groups file
is its complete output.

## `critic/` and `recritic/` — the two critic passes' own probes

- `critic/`: first completeness-critic pass on the synthesized draft — `critique.md` (the
  report that became `../critique_pass1.md`), `evidence_failed.txt` and `triage_nodes.txt`
  (its census of the red gate), `own.py`, `probe2.sh`, `probe3.sh` (its independent
  probes).
- `recritic/`: second pass on the revision — `report.md` (→ `../critique_pass2.md`),
  `own2.py`, `probes.sh`…`probes4.sh` with their `.out` transcripts (R1–R8 corrections).

`../wave0-legs/` (the three seeded gates, conformance, compare-bash, benchmarks at the 0.3
tree) is the integrator's and is filled at the Wave 0 gate, not here.
