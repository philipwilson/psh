# Improvement Program 2026-09 — evidence

Program: [improvement_program_2026-09-06.md](../../improvement_program_2026-09-06.md).
Produced 2026-09-06 at HEAD `6459f1a6` (v0.779.0) against the oracle
`/opt/homebrew/bin/bash` = GNU bash 5.3.15(1)-release, by a 59-agent
orchestration (extract → dedup → verify → gate triage → planner panel →
judge → critic) followed by an integrator review pass.

| File | Contents |
|------|----------|
| `INVENTORY.json` | The 245-row canonical inventory C001–C245: every finding from the 14 reappraisal-#23 raw reports (`tmp/r23-reports/`, 332 raw records), the #23 synthesized report, and the fresh appraisal (F01–F16, D1–D4), merged by root cause. Each row carries `sources` (raw ids), `locations`, `repro`, `bash_expected`/`psh_observed` as reported, `fix_sketch`, and `verification` = the 2026-09-06 re-run at HEAD vs bash 5.3.15 (`live` / `fixed` / `not_reproducible` / `oracle_changed`; fresh-only rows were re-verified by the integrator session). Status is frozen at 2026-09-06; the program's `LEDGER.md` (Wave 0.1) tracks progress. |
| `gate_triage.json` | The 51 failing local-gate nodes at `6459f1a6`, each run and classified: `FORMAT` (22, bash 5.3 presentation), `SEMANTIC` (19, bash 5.3 semantics psh should follow), `PREMISE` (4, the test's bash-side premise changed), `ENV` (6, sandbox/process-state artifacts), with the exact proposed retune, effort, and any user-guide claim it backs. |
| `judge_scores.json` | The judge's scores for the three planner drafts and its ownership check (0 unowned). |
| `planner-drafts/` | The three independent programs the judge synthesized from: impact-first, root-cause-first, velocity-first. Kept for provenance; superseded by the program. |
| `critique_pass1.md` | The completeness critic's first pass on the synthesized draft (1 blocker, 7 majors, 4 minors). All twelve were verified against the tree and applied; the second-pass report is `critique_pass2.md`. |

Status tally of `INVENTORY.json`: 166 `live`, 74 `n/a` (design/theme/doc rows, not verifiable as defects), 2 `oracle_changed` (C153, C181), 2 `not_reproducible` (C114, C163), 1 `fixed` (C208).

Reproduce a verification: take a row's `repro`, run it from a fresh `mktemp -d` as
`env -u PWD -u OLDPWD /opt/homebrew/bin/bash -c '<repro>'` and
`env -u PWD -u OLDPWD PYTHONPATH=<repo> PSH_STRICT_ERRORS=1 python -m psh -c '<repro>'`
(psh trusts an inherited stale `$PWD`, hence the `env -u`).
