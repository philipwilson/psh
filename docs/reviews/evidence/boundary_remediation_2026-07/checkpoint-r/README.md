# Checkpoint R evidence (sequence §10 whole-tree reappraisal, 2026-08-08)

Tree appraised: `ae871a16` (v0.773.0). Verdict: clean bill, certified under
attack — see `report.md`.

Contents:
- `report.md` — the independent report (§10 exit deliverable): the five
  questions answered, the Wave 5 re-scope amendment (CR-R1), dispositions
  CR-R2..CR-R7, register rows CR-D1..CR-D6, convergence statement.
- `charter.md` — the dispatch charter both rounds ran under (md5
  `a08a9c1df086b1c128b8bce6772f1d57` at dispatch).
- `ROUND1-DIGEST.md` / `ROUND2-DIGEST.md` — per-agent results, mechanically
  generated from the workflow journals (jq over `journal.jsonl`; verdicts,
  findings, censuses, recommendations, not-checked lists verbatim).
- `round1-workflow.js` / `round2-workflow.js` — the exact orchestration
  scripts (6 scoped verifiers; 3 attack scopes).
- `instruments/{q1,q2,q3,q4,q5,qr,atk-a,atk-b,atk-c}/` — every probe file
  and transcript, per scope (275 files, copy verified md5-identical to the
  working set at staging).
- `MANIFEST.md5` — command-generated md5 manifest of every file in this
  directory (self-excluding).

**Path mapping (citation resolvability):** agent-authored digests and
transcripts cite instrument paths as `tmp/ckr-probes/<scope>/...` — the
working location at run time. Those files are committed here under
`instruments/<scope>/...`; substitute the prefix to resolve any citation
in-tree. (The digests are verbatim records and were deliberately not
rewritten.)

Round-1/round-2 workflow run IDs: `wf_f7c52bc5-09d` / `wf_de92254a-f5c`.
