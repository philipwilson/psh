---
name: psh-release
description: Cut a psh release — version bump, local gate, attestation, PR, auto-tag. Use when shipping a completed enhancement, bumping psh/version.py, or preparing a vX.Y.Z tag.
---

# Release workflow (per completed enhancement)

The gate is **local** — GitHub's per-PR `tests.yml` workflow is intentionally
disabled (`gh workflow disable tests.yml`, state `disabled_manually`; re-enable
with `gh workflow enable tests.yml`). The nightly full+bash+coverage run
(`nightly.yml`) stays on as a safety net. `release-tag.yml` auto-creates the
annotated `vX.Y.Z` tag when `psh/version.py` changes on main, so tagging is
automatic — there is **no manual `git tag`** step.

1. Work on a `fix/<topic>` branch.
2. Full suite green LOCALLY: `python run_tests.py --parallel > tmp/test-results-N.txt 2>&1`
   (this is THE gate). Also `ruff check psh tests tools` and `mypy` clean.
3. Update `psh/version.py` (bump `__version__`) and add a `CHANGELOG.md` entry.
4. Update the version string in **all** of these files (they must always match):
   - `README.md` — the `**Current Version**:` line (also the `**Tests**:` and
     `**Test Coverage**:` counts and Recent Development when they changed)
   - `ARCHITECTURE.md` — the `**Current Version**:` line
5. **Attestation (campaign E4):** commit the version bump, then at that commit
   run `python run_tests.py --parallel --write-attestation > tmp/gate-attest.txt 2>&1`
   (on a green run it also runs ruff+mypy itself and writes
   `gate_attestation.json`). Commit `gate_attestation.json` as the FINAL
   commit — `release-tag.yml` verifies it before tagging (version matches
   HEAD's `psh/version.py`, gated commit is an ancestor, and nothing but the
   attestation changed since the gate ran) and FAILS loudly otherwise.
6. Push, open a PR (`gh pr create --head <branch>`),
   then merge immediately (`gh pr merge <n> --merge --delete-branch` — no CI to
   wait on). `release-tag.yml` creates the `vX.Y.Z` tag on the version bump
   (attestation-gated as above); verify with `git fetch --tags`.
