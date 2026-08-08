# dev-4b-4 SIGN-OFF — tag v0.773.0

Protocol pre-registered at D10 BEFORE the tag existed. Seven legs, every one
run at a FRESH DETACHED CHECKOUT of the tag (`/Users/pwilson/src/psh-tag-773`,
created from `v0.773.0`, removed after). Oracle: `/opt/homebrew/bin/bash`
5.2.26.

## Leg 1 — DISCRIMINATOR-FIRST: **PASS**
- `git rev-parse 'v0.773.0^{commit}'` -> `919935d83f4590bdde7a35a8bb324eb6ed6aac82`,
  equal to the declared SHA (recomputed by me, not accepted from the message).
- `git cat-file -t v0.773.0` -> `tag` (annotated).
- `git merge-base --is-ancestor 05d416e5 919935d8` -> true: my reviewed tip is
  an ancestor of the tag.
- Parent `import psh` AND child `python -c 'import psh'` both resolve to
  `/Users/pwilson/src/psh-tag-773/psh/__init__.py`.

## Leg 2 — PER-CELL DEFECT LEGS: **PASS**
`instr11` retargeted to the tag: **13 MATCH / 1 DIVERGE of 14**.
The single divergence is `BL1-N4` (move form `true 3<&0-`): psh `b=<A>`,
bash-C `b=<>`. That is the DECLARED pre-existing residue (bash's move closes
the source; psh restores fd 0 after the per-command frame) — an fd-lifetime
difference behind the redirect-restore fence, NOT a cursor defect: the held
byte is correctly preserved. Declared in ledger §17 and D9 before the tag.

Leg 2b, the slot's original faces run explicitly: **12/12 PASSED** — legs A
and B, both temp-frame directions, nested frames, and all three
node-derivable dup spellings.

## Leg 3 — MUST-HOLD: **PASS**
152/152 across the contract suite, the I1 identity suite, the registry unit
suite, `test_input_cursor_i1`, both 4B.2 pin files, `record_bytes`, and the
system end-to-end seam file.

## Leg 4 — NO-SILENT-CHANGE: **PASS**
`git diff --name-only e3924ed3..919935d8` yields exactly my 20 declared
production/test/doc files, plus `psh/version.py` and the integrator's ceremony
paths. Explicit check for any path outside those two sets: **none**.
`psh/version.py` was last touched by `cc476e91` (the integrator's release
bump), not by me — verified by `git log -1 -- psh/version.py`.

## Leg 5 — M8 AT A FRESH CHECKOUT: **PASS**
Precondition asserted before running: `tmp/` **ABSENT** in the tag checkout.
Both lock sets, `PYTHONDONTWRITEBYTECODE=1`: **19 passed**.

## Leg 6 — FALSIFICATION: **PASS**
Each production hunk reverted ONE AT A TIME in a scratch copy of the tag, with
the unmutated cell required to pass first:

| Hunk | unmutated | reverted | verdict |
|---|---|---|---|
| `_release` reference check | rc=0 | rc=1 | FALSIFIED |
| named-fd `var_fd` skip | rc=0 | rc=1 | FALSIFIED |
| compound dup aliasing | rc=0 | rc=1 | FALSIFIED |

Every hunk is load-bearing; no cell passes without the code it claims to pin.

## Leg 7 — ARTIFACT VERIFICATION: **PASS, with one NOTE**
- `psh/version.py` `__version__ = "0.773.0"`; CHANGELOG has the 0.773.0
  entry; README and ARCHITECTURE both stamp 0.773.0.
- `gate_attestation.json` is the FINAL commit of the branch (`a53ef7d5`,
  reached as `919935d8^2`), `gated_commit = cc476e91`.
- Attestation figures reconcile with my gate 3: phase 1 22,775 + phase 1b
  1,117 = **23,892 passed**, 1,620 skipped; `ruff: True`; `mypy_files: 275`.
- Rescue tree present with ledger, inbox, brief, ROUNDS-AND-ERRATA, both
  verify verdicts, the I1 excerpt, and instruments.
- Committed manifest md5 `df6ced954af8156d838313e917404d25` — **EXACT match**
  to the manifest I declared at D9.
- **33 of 38 manifest entries verified byte-for-byte against the committed
  instruments; 0 mismatched.**
- Row (d)'s citation RESOLVES in-tree: the I1 deliberate-loss registry
  excerpt is committed and contains the "builtin->external" row.

**NOTE (my defect, not the integrator's).** The remaining 5 manifest entries
— `tmp/gate-1.txt`, `gate-2.txt`, `gate-3.txt`, `compare-bash-1.txt`,
`compare-bash-2.txt` — do NOT exist in the tagged tree. They are heavy-run
transcripts under gitignored `tmp/`, listed in my manifest under their own
"heavy-run transcripts" header. So the committed manifest names five paths a
reader holding only the tag cannot resolve. That is the RN-4 failure shape one
level over — a citation whose source the tree cannot resolve — and it is MY
artifact that carries it. It does not affect any figure (every instrument
verifies, and the run figures are recorded in the ledger and the attestation),
so it is not a blocker to signing; it is a recommendation: either commit the
five transcripts beside the instruments, or annotate those lines in the
manifest as deliberately-uncommitted with their figures cited where they live.

## Zero flakes
No leg was re-run. Nothing failed and then passed. Every figure above is from
a first and only execution.

## VERDICT

**SIGNED.** Tag `v0.773.0` @ `919935d83f4590bdde7a35a8bb324eb6ed6aac82`
verifies on all seven legs, with the one leg-7 note recorded above and the
one declared residue (the move-form fd-lifetime divergence) re-confirmed as
declared rather than newly discovered.
