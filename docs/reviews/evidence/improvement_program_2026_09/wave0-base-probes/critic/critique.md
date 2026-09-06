# Completeness critique — Improvement Program 2026-09 (synthesized draft)

Critic run 2026-09-06 at HEAD 6459f1a6 (v0.779.0), oracle /opt/homebrew/bin/bash = GNU bash 5.3.15(1)-release (aarch64-apple-darwin25.4.0). Every claim below was checked against the real files or a live probe; probe scripts are in this directory (`own.py`, `probe2.sh`, `probe3.sh`, `evidence_failed.txt`, `triage_nodes.txt`).

## Verdict

NOT READY. One blocker (Wave 0 as three releases contradicts the attestation/tag ceremony: the gate is red at the 0.1 and 0.2 trees, `write_attestation` only writes on a fully green gate, and `release-tag.yml` refuses to tag without it), plus seven majors: stale-PWD/OLDPWD startup divergence unregistered; W0-N1 repro mis-described (green on base as written); the cross-entry-point matrix ships last instead of first; user-guide "Full support" rows that inventory items falsify are not named for Waves 1/3/4; Wave 0 → Wave 4 slot cross-references point at the wrong slots (N2/N3/N5/N6 + signal-death FLIP-PIN); the "Wave 1 and 2 are file-disjoint" claim is false; and the "under-claims are fixed by hand" statement misreads the meta-test (it does police stale No/Partial rows). The ownership map itself is clean (245 rows, 0 double-owned, 0 unowned, nothing fixed/not_reproducible queued).

## Check-by-check

### (1) Inventory ownership — PASS with one routing defect (major)

`own.py` against `../judge/inventory.json` and the §16 map: 245 distinct cids mapped, sum 245, no double ownership, no unknown cid, none of C114/C163/C208 queued, the two `oracle_changed` rows (C153, C181) owned by Wave 0. The seven `live` Park rows (C171, C172, C120, C165, C190, C196, C186) each have a §15 ruling and successor.

Defect: the W0-N side-finding routing in §6 disagrees with the slot numbering in §10 (see gap G5).

### (2) Wave 0 restores a green gate — PASS on coverage, FAIL on ceremony (blocker)

- The evidence dir's failure list (`docs/reviews/evidence/fresh_appraisal_2026_09_06/`, 52 `FAILED` lines) is exactly the 51 triage nodes + `tests/unit/tooling/test_reviews_index.py::test_every_review_file_is_indexed` (comm on `evidence_failed.txt` vs `triage_nodes.txt`: only the procsub-render parametrize id differs). Every one of the 51 is placed in 0.1/0.2/0.3 (counted: 0.1 = 14 incl. the 5 ENV rows; 0.2 = 4+5+7+2+1+1 = 20; 0.3 = 17). The index failure: `test_reviews_index.py` uses `os.listdir` (line 38), so both untracked reports count, and the parallel session's uncommitted `docs/reviews/README.md` edit indexes ONLY the fresh appraisal — the failing file is `ground_up_reappraisal_23_correctness_textbook_2026-08-09.md`; 0.1 item 7 covers it but should name that row.
- Attestation records the oracle: covered by 0.1 item 2 (schema 1→2, `oracle.{path,version}`, verifier `REQUIRED_KEYS`). Note the program header's "Attestation on record … oracle bash 5.2.26" is a memory-derived coordinate — the schema-1 file (`gate_attestation.json`) records no oracle at all.
- Ceremony contradiction: `run_tests.py#write_attestation` ("Write ATTESTATION_FILENAME for a fully green gate"), the SKILL step 2/5, and `release-tag.yml` ("no attestation, no tag") mean a release requires a green gate at the version-bump commit. After 0.1 alone, at least 37 triaged nodes are still red (trap ×4, shopt ×5, jobs ×9, cd/exit ×2, trap-status ×4, posix-special ×5, function-name, hash, declare -i, fd0, PATH ×2); after 0.2, the 17 flip-pin nodes of 0.3 are still red. So v0.780.0 and v0.781.0 cannot be attested or tagged, and merging them to main violates CLAUDE.md "a green run_tests.py --parallel … your responsibility before merging". Launch checklist item 4 ("nightly … observed green" after 0.1) fails for the same reason on the pinned 5.3.15.

### (3) Linux nightly — PASS (with two notes)

Confirmed from `gh run view 34008477403`: both jobs failed; the failed rows are exactly the 7 `test_printf_float_format_conformance.py` cells in both jobs; one cell shows `PSH: '0x1.92p+1'` vs `Bash: '0xc.8fp-2'` for `printf '%.2a' 3.14` — x87 long-double form, so the `oracle_feature('x87_long_double')` classification is correct. `nightly.yml` has no `BASH_PATH` and runs `bash --version` only; `resolve_bash()` (shell_oracle.py:252) honours `BASH_PATH` and both `run_conformance_tests.py` (line 75/220) and the golden phase use it, so the pin plan works. GNU has `bash53-001 … bash53-015` (ftp.gnu.org listing fetched). Notes: (a) `tools/verify_gate_attestation.py` runs under bare `python3` on the tag job — the schema-2 verifier must stay stdlib-only (no import of `tests/harness/oracle_policy.py`); (b) once pinned, the nightly never exercises 5.2.21 again — intended, but say so in `nightly-status.md`.

### (4) User-guide over-claims — FAIL (major)

`test_claims_have_tests.py` maps `CLAIM_TESTS` by (file, marker) not node id, so the Wave 0 renames are safe. But the table (`17_differences_from_bash.md`) has "Full support" rows that inventory items in later waves falsify, and the program names only :957/:961 (Wave 1), §8.4 (Wave 3), :504-540 + `04_builtin_commands.md:1107` (Wave 0):

| Row | Line | Falsified by | Slot that must name it |
|---|---|---|---|
| Tilde expansion / case-esac | :934 / :941 | C042 | 1.11 |
| Arithmetic expansion | :931 | C007 | 3.4b |
| select | :942 | C015, C017, C064 | 4.1 / 4.11 |
| wait builtin | :953 | C067, C078, C182 | 4.13 / 4.8 |
| printf builtin (incl. %q) | :976 | C029, C089 | 4.7 / 4.8 |
| History expansion (!!, !n) | :983 | C034 | 4.18 |
| ulimit builtin | :990 | C030 | 1.14 |
| DEBUG/ERR/RETURN traps | :968 | "bash 5.2 recurses forever" — probed on 5.3.15: `f(){ :; }; trap "return 3" RETURN; f; echo rc=$?` → bash `rc=0`, psh `rc=0`; with `return 5` in the body both print `rc=5`. The "deliberate divergence" sentence is now false provenance | 2.1 |
| `set -o noexec` listed as supported | :25 | C040 | 1.10 |

Also the program's "under-claims are fixed by hand" is wrong: the meta-test has `NO_ROW_PROBES`/`PARTIAL_ROW_PROBES` staleness guards (`test_no_row_feature_still_unsupported`, `test_partial_row_gap_still_diverges`) that FAIL when psh starts matching bash on a No/Partial row — any slot that converts such a row must flip the probe in the same diff.

### (5) Release-ceremony constraints — FAIL (the blocker in (2)) plus minors

- SKILL: no manual tag ✓; attestation FINAL commit ✓; `--write-attestation` flag exists ✓; `--quick`/`--benchmarks`/`--compare-bash` exist ✓.
- Integrator plan §7 is "Release ceremony (per slot)"; the program's "the integrator may pair two S slots in one release" is a delta not listed in §4 — needs a D-number or removal.
- The D5 marker `@pytest.mark.oracle_min("5.3")` and `min_bash: "5.3"` contain the very literal the 0.1 ratchet ("forbids bash-version literals used as predicates in test code") would flag; the ratchet must whitelist the marker/golden-key forms. `pytest.ini` has `xfail_strict = true` and a `markers` list — the new marker must be registered there.

### (6) Park register — PASS

§15 rows each carry a reason and successor; excluded rows carry the verify note. C169 confirmed absent (`ls f f1 f2` → no such file).

### (7) Design §1 cross-entry-point matrix — FAIL on placement (major)

Fresh appraisal §"Design Improvements" 1 (line 256-262) asks for a matrix over ordinary assignment, arithmetic, declare/local, nameref writes, read/mapfile, scope exit, asserting values, flags, effective lookup, external environment, executable dispatch. The program owns it in slot 1.18 (`tests/unit/core/test_write_authority_matrix.py`) with the right axes — but 1.18 is the last-but-one Wave 1 slot while 1.4/1.5/1.15/1.16/1.17 migrate write-site consumers earlier, and the §17 risk row says "the C226 matrix ships before consumers migrate". By 1.18 the matrix cells for C044/C027/C028/C090 are green on base (violates §3 outcome 5 / D3 red-on-base). Nameref cells for C071 (4.9) and C130 (4.5) have no stated treatment.

### (8) Harness-masked divergences — FAIL (major)

`hermetic_shell_env` (shell_oracle.py:312-313) pops `PWD`/`OLDPWD` and `run_shell_case` (line 471-476) sets a truthful `PWD` — so no pin in the tree sees psh's startup behaviour. Probed (fresh `mktemp -d`):

- `env PWD=$PWD/../other psh -c 'echo $PWD; pwd; cd .. && pwd'` → psh `PWD=/var/.../real/../other`, `pwd` `/private/var/.../real`, after `cd ..` `/var/.../tmp.X` (non-canonical, derived from the fabricated PWD); bash 5.3 prints the validated `/private/var/.../real` in every position.
- `env PWD=/nonexistent/zz psh -c 'echo $PWD'` → psh `/nonexistent/zz`; bash → the real cwd.
- `env OLDPWD=/nonexistent/q sh -c 'echo "[$OLDPWD]"; cd -'` → bash `[]` + `cd: OLDPWD not set` rc 1; psh `[/nonexistent/q]` + `cd: /nonexistent/q: No such file or directory` rc 1.

Seeding site: `psh/core/state.py:227-228` (`if 'PWD' not in self.env: set PWD = os.getcwd()`) — no validation. Not in the inventory, not in the program, not in `17_differences_from_bash.md` (no `PWD` mention). Since the program already pins `pwd -P`/`os.getcwd()` as actual targets in 1.4, this belongs there.

## Gaps (ranked)

### G1 — BLOCKER — Wave 0 as three attested releases is impossible under the ceremony
Fix: make Wave 0 ONE release branch (`fix/wave0-oracle-5.3`) landing 0.1+0.2+0.3 as ordered commits, gate once at the 0.3 tree, one `gate_attestation.json` FINAL commit, one tag (v0.780.0). If the user wants three PRs, then 0.1 and 0.2 must be explicitly ruled "red-gate merge exemption, no version bump" in §4 as a D-number (release-tag.yml ignores them since `psh/version.py` is untouched), and CLAUDE.md's merge rule is amended for that window only. Renumber §5 (Wave 0 releases: 1), launch checklist items 4–5 (nightly dispatch at the 0.3 tree, tags v0.780.0 only), and Wave 1 starting version.

### G2 — MAJOR — Stale `$PWD` / bogus `OLDPWD` startup handling unregistered (check 8)
Fix: register `W0-N7` in 0.3 ("startup imports `PWD` unvalidated and `OLDPWD` unchecked; bash uses inherited PWD only if it names the cwd (same dev/ino) else `getcwd()`, and drops an OLDPWD that is not a directory") → slot 1.4, owner `psh/core/state.py#ShellState.__init__` PWD/OLDPWD seeding (or a `navigation.py#seed_cwd_variables` the state calls). Pins in three modes with explicit `case_env={'PWD': stale}` / `{'OLDPWD': bogus}` (the harness docstring says a caller-supplied value wins), asserting `$PWD`, `pwd`, `pwd -P`, `cd -` target and a file placed after `cd ..` (D3). Add one sentence to `shell_oracle.py:297` pointing at the pin, and a §17 row until closed.

### G3 — MAJOR — W0-N1 repro is wrong; the 3.8 pin would be green on base
Observed: `psh -c 'read x <&-; echo rc=$?'` → `psh: line 1: read: read error: 0: Bad file descriptor`, `rc=1`, no traceback. The traceback is `ValueError: InputCursor needs exactly one of fd or stream` and occurs when fd 0 is closed at STARTUP: `psh -c 'read x' <&-` and `psh s.sh <&-` (both modes). Fix: rewrite W0-N1 as "read with fd 0 closed at startup (`sys.stdin is None`) escapes as `ValueError` from `InputCursor`", pin both `-c` and script modes with fd 0 closed on the psh process, expected `read: read error: 0: Bad file descriptor` rc 1 (bash 5.3 `-c 'echo hi' <&-` runs normally, so `-c` must not exit 126 — consistent with 0.3's "only the no-`-c`/no-script path").

### G4 — MAJOR — Cross-entry-point matrix ships last, contradicting D3 and the risk register (check 7)
Fix: hoist the matrix into a new opening slot **1.0 Write-authority matrix (C226, half of C244; S, 1 d)** that lands before 1.4; cells for later slots ship as `xfail(strict=True, reason="C0xx → slot y")` so each subsequent slot flips its cells red→green (red-on-base demonstrated by the xfail strictness). Cells for C071/C130 (Wave 4) carry the same xfail form. 1.18 then extends the matrix with array cells rather than owning it.

### G5 — MAJOR — Wave 0 → Wave 4 slot cross-references are wrong
§6 says: signal-death FLIP-PIN "owned by slot 4.15 (C065 job text)"; `W0-N5` → 4.12; `W0-N2` → 4.15; `W0-N3` → 4.8; `W0-N6` → 4.9; unset-readonly-function wording → 4.9. §10 actually places: C065/W0-N2 in **4.12**, W0-N3 in **4.6**, W0-N6 + unset-readonly wording in **4.7**, W0-N5 in **4.9**; 4.15 is combinator parity. Fix: correct the six references in §6 (0.1 item 6, 0.3 bullets 1 and 4) and the Wave 4 exit-criteria sentence; have the ledger generator derive slot ids from §10 headings so this cannot drift.

### G6 — MAJOR — "Wave 1 and 2 are file-disjoint" is false
From the program's own briefs: 2.3 edits `psh/builtins/navigation.py:103` which 1.4 rewrites; 2.4 edits `scope.py#apply_attribute/remove_attribute` while 1.5 edits `scope.py#_notify_path_changed/pop_scope` and 1.16 edits `ScopeManager.set_variable/create_local`; 2.2 edits `environment.py` Export/Unset while 1.16 touches the declaration builtins; 2.1 edits `builtins/core.py:39-41` while 1.14 edits `core.py:51`. Fix: replace "file-disjoint" with an explicit ordering rule on the merge train (2.3 before 1.4, 2.4 before 1.5/1.16/1.18, 2.1 before 1.14, 2.2 before 1.16) or state that Wave 2 worktrees rebase onto the train tip before verification and the verifier re-runs at the rebased SHA.

### G7 — MAJOR — User-guide "Full support" rows falsified by owned items are not named (check 4)
Fix: add the nine rows in the table above to the named slots' briefs and exit criteria (1.10, 1.11, 1.14, 2.1, 3.4b, 4.1/4.11, 4.7/4.8, 4.13, 4.18), each corrected in the same diff (outcome 6). Replace "under-claims are fixed by hand" with "No/Partial rows are policed by `NO_ROW_PROBES`/`PARTIAL_ROW_PROBES`; a slot that makes psh match on such a row flips the row and its probe in-slot".

### G8 — MINOR — 0.1 item 7 should name the failing index row
The uncommitted README edit indexes only the fresh appraisal; the red test is the r23 file. Say so, and keep the "Current appraisal" table as the parallel session wrote it.

### G9 — MINOR — Header provenance
"Attestation on record … oracle bash 5.2.26" — the schema-1 attestation records no oracle; phrase it as "oracle at gate time (memory/CHANGELOG): 5.2.26".

### G10 — MINOR — Marker/ratchet interaction and verifier portability
Register `oracle_min` in `pytest.ini` `markers`; make the 0.1 "no version literal as predicate" ratchet allow the `oracle_min("…")` / `min_bash:` forms; keep `tools/verify_gate_attestation.py` stdlib-only (release-tag runs it with bare `python3`, no `pip install`).

### G11 — MINOR — "Pair two S slots per release" is an undocumented delta
Integrator plan §7 is per slot. Add it as D16 or drop it.

### G12 — MINOR — D14 evidence and scope
Probed: `export HOME=/probe-home; echo ~` on the Homebrew bash still prints `/Users/pwilson` — even an exported in-script HOME is ignored by `~` (env-supplied HOME works). D14 is correct; note that `export` does not help and that 1.4's empty-HOME pins (`cd` reads `$HOME` directly, unaffected) and 1.11's tilde-pattern pins (affected) must both use `env=`.

## Verified-true claims (no action)
- `trap -P` on 5.3.15: synopsis `trap [-Plp] [[action] signal_spec ...]`; `trap -P` → `trap: -P requires at least one signal name` rc 2; `trap -p -P INT` → `cannot specify both -p and -P` rc 2; `trap -P INT` prints the bare action.
- `exit abc; echo rc=$?` → `exit: abc: numeric argument required`, `rc=2`, continues (both `-c` and script) — W0-N4 correct.
- `bash -c 'set -m; sleep 0.01 & wait'` → no output — C181 closed as stated.
- `hash -d nosuch` on an empty table → `hash: nosuch: not found` rc 1 — 0.2 correct.
- `bash <&-` → `error creating buffered stream: Bad file descriptor` rc 126; `bash -c 'echo hi' <&-` → `hi` rc 0; `python -c 'import sys;print(sys.stdin)' <&-` → `None` — 0.3 fd-0 plan correct.
- `${ echo fs; }` → `fs`; `${ }` → empty rc 0 — funsub pin premise correct.
- All line pointers spot-checked exist as described (strategies.py:148, navigation.py:103, hash_builtin.py:80-83, builtins/job_control.py:96-98, executor/job_control.py:279/280/683, function.py:47-55, signal_handling.py:24, trap_manager.py:449-451, scope.py:1290/1363, process_sub.py:32-34, input_reader.py:429, 17.md:504, 04_builtin_commands.md:1107, 08_quoting:267).
- CHANGES items exist for: posix function names (line 275), `trap -P` (830), special-builtin posix exits (399/633).
