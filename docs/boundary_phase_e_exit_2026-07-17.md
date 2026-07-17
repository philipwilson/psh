# Boundary Integrity Campaign — Phase E exit manifest

**Date:** 2026-07-17
**Exit SHA:** `a8105c13` (branch `fix/boundary-phase-e-close`, atop v0.726.0 @ `83c21a2b`)
**Criterion:** `docs/reviews/boundary_campaign_briefs_2026-07-16.md` §6, Phase-E exit (as amended
2026-07-17: working transcripts in `tmp/`, this manifest committed).

Phase E ("trustworthy evidence first") is **CLOSED**. The packages that establish it:

- **E1+E4** — v0.725.0 (PR #471): structured phase manifests; no nonzero pytest exit ever classifies
  success; performance tiers; mypy coverage guard; same-SHA release attestation (live in
  `release-tag.yml` since v0.725.0).
- **E2+E3** — v0.726.0 (PR #472): one typed bash-oracle runner (`tests/harness/shell_oracle.py`);
  harness failures rejected before comparison; LC_CTYPE provenance fix; suite-wide process-state
  hermeticity fixture; serial contaminator fixed at source.

## Exit evidence (all at `a8105c13`)

| Leg | Command | Result |
|---|---|---|
| Seeded gate 1 | `python run_tests.py --parallel --shuffle-seed 101` | exit 0 — 18,347 passed / 0 failed / 1,574 skipped / 10 xfailed |
| Seeded gate 2 | `python run_tests.py --parallel --shuffle-seed 202` | exit 0 — identical counts |
| Seeded gate 3 | `python run_tests.py --parallel --shuffle-seed 303` | exit 0 — identical counts |
| Census identity | manifest comparison across seeds | collected sets identical (19,931 ids); outcome counts identical |
| Live-bash comparison | `python -m pytest tests/behavioral --compare-bash -q` | 2,986 passed / 24 skipped |
| Conformance | `python -m pytest tests/conformance -q` | 1,893 passed / 1 skipped / 8 xfailed |
| Lint | `ruff check psh tests tools` | clean |
| Types | `python -m mypy` | Success, 258 source files |

Transcripts and per-seed phase manifests: `tmp/boundary-ledgers/E/` (sha256 in `hashes.txt` there):

```
5c9d2f353dd41f728a3c141b08eea2cc868cdbf8f633dca179c0c2237ff0583c  exit-compare-bash.txt
df14ba7f64a115e465f86a8535bd59e3808e2e15ab7f1ee4b3dde5be69dca146  exit-conformance.txt
4ce81e9a7e7f3fd7c26e4c6ddf406a1c39257b9c75240cf1b4175a5d555a7421  exit-mypy.txt
82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18  exit-ruff.txt
8d97998c17be562d5302dd4d90cbbd166038b2b551b5c5584039d76297d8826b  exit-seed101-red.txt
5c7104a26a7ffa8c5e933980b86dba78095849a475fa13c9ae9df9a7f5254bfa  exit-seed101-take2.txt
bd8fa3f4f0060baa84babeeba3c0887c7ce5474fbe75a879d0b915692a6bf275  exit-seed202.txt
9c27cd88f491a037b3cb187657e32b271c99ae6fae2a30116b46d5c7c2ea9b5d  exit-seed303.txt
```

## The catch the criterion exists for

The FIRST seeded run (seed 101 at v0.726.0, `exit-seed101-red.txt`) failed: E23's process-state
hermeticity pins were pollute-then-observe pairs that assumed pytest definition order, and E1's
deterministic shuffle reordered a pair — the first observed interaction between the two Train-0
packages. Fixed in this branch by redesigning the pins to be order-independent (every test asserts
its entry state equals the module-import baseline, then pollutes; any order proves the restore).
Standing lesson recorded in the campaign runbook: **test pins must be order-independent — the seeded
exit will shuffle them.**

## Consequences now in force

- No semantic package (Phases F/S/W/R/I/J/Q) was started before this close, per the campaign doctrine.
- Release tagging requires a same-SHA gate attestation (E4) — an unattested version bump on main fails
  `release-tag.yml` loudly.
- All bash/psh differential execution routes through the one oracle runner; the ratchet forbids bypasses.
- The gate classifier cannot translate any nonzero pytest exit into success.
