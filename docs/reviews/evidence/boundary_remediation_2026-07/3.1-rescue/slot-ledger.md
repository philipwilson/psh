# Slot 3.1 ledger — Pattern correctness (HIGH-7 semantics half, Wave 3 opener)

- **Agent:** dev-3-1
- **Base:** origin/main `29456fdc` (v0.762.0; verified in worktree `/Users/pwilson/src/psh-r3-1`, branch `fix/remediation-3-1`, clean tree at slot start)
- **Evidence SHA convention:** every measurement row names the SHA of the tree it was taken against (`base=29456fdc` or the tip commit SHA), the cwd, and the import discriminator (`psh.__file__`) for any in-process psh run. Oracle rows name the binary + version: PATH bash `/opt/homebrew/bin/bash` (5.2.26 — to be re-verified below before first use). NEVER `/bin/bash`.
- **Brief:** `tmp/remediation-ledgers/briefs/3.1.md` (read in full 2026-08-01). Inbox R0 read; ACK pending in first SendMessage.
- **Stage-gate:** Phase A report BEFORE implementation; WAIT for GO + KNOWN_DIVERGENCES ruling.
- **A9:** semantics only; no algorithm rewrite/cache/perf. Incidental complexity changes DECLARED.

## Turn log

- 2026-08-01 T1: slot open. Read INTEGRATOR-INBOX (R0), brief, project CLAUDE.md, psh/expansion/CLAUDE.md. Verified base SHA + branch. Created this ledger. Beginning Phase A: red-on-base probes (H7a/H7b/H7c), engine read, consumer census, corpus design.
- 2026-08-01/02: Phase A executed end-to-end: anchors + consumer propagation (A1), consumer census (A2), defect localization (A3), corpus1+corpus2 + EXACT model (A4, 0/65,625), per-consumer grid + substitution consumer-layer mechanisms + KNOWN_DIVERGENCES measurements (A5), parse-side STOP-item (A6), pin-interaction constraints (A7), guide claims census (A8), perf baseline for 3.2 (A9), Phase B design (A10). bash-5.2 source (sm_loop.c/gm_loop.c/glob.c/gmisc.c/subst.c + full tarball) cached under tmp/slot31/ as model-derivation evidence; corpus remains the oracle. No heavy runs (no pytest; largest single run = one 52k-line bash -c script). NO implementation.
- 2026-08-02: PHASE A REPORT SENT to integrator (msg 172c3569, ACK R0; inbox re-read immediately before send — still R0 only). WAITING for GO + KNOWN_DIVERGENCES ruling + rulings on declared items (regex-oracle corpus narrowing; parse-side quoted-alt lexer item).
- 2026-08-02: **R1-R4 RECEIVED (inbox read in full) + ACKed (msg bd6648a8). PHASE B GO** under R1 (design accepted; corpus one-command replayable for verifiers; state-count guard failure must name the pattern), R2 (CLOSE all four KNOWN_DIVERGENCES via measured mechanisms (i)-(iii) respecting (iv), conditions a-e binding), R3 (regex-oracle narrowing approved, conditions a-d: predicate IS the flag, docstring why + covering oracle, derived excluded-count cert row, Q3 oracle untouched), R4 (lexer quoted-chars item = SUCCESSOR, conditions a-c: divergent-direction residual rows + engine-level agreement rows, token dump ledgered, never weaken a row). Phase B order: engine → consumer seam → pins/battery → docs → gates (per-run GO).
- **One-command corpus repro for verifiers (R1):** `cd <worktree>/tmp/slot31/neutral && PYTHONPATH=<worktree> python3 ../corpus1.py` then `python3 ../corpus2.py` (corpus2 also re-validates the model via `import bash_model`). Deterministic generators (corpus v1 = the literal constant lists in each file, no randomness); oracle binary literal `/opt/homebrew/bin/bash`; outputs `corpus[12]_results.tsv` + census on stdout. Model re-validation alone: `python3 ../bash_model.py ../corpus1_results.tsv`.

- 2026-08-02: Phase B complete at tip 7bec085c (six commits; B1-B6 below). Mutation-proofs M1-M5 run and reverted (tree clean). GATE GO REQUESTED (msg 5d69b2d1; inbox re-read first — still R0-R4). WAITING for per-run GO before the full gate + compare-bash.
- 2026-08-02: R5 received (heavy-run GO) → gate run 1: FALSE RED (stale-pyc, B7); diagnosis reported (msg 15bd6e4d), rerun GO requested. R6 received (rerun GO + sequence): gate rerun **GREEN 22,832/1,590/10** (+12 derived-reconciled), compare-bash **EXACT 2,986/26**. Mutation replay made one-command with cache hygiene (`tmp/slot31/replay_mutations.sh`, verified at tip). **FINAL TIP DECLARED 7bec085c** (mechanical tip rule in force). COMPLETION REPORT SENT (msg 674159de; inbox re-read immediately before — through R6). Standing by for verification round 1.

## Phase A evidence

### A1 — Red-on-base anchors (H7a/H7b/H7c) + per-consumer propagation

- **Instrument:** `tmp/slot31/probe_anchor.py` + `probe_anchor2.py`; transcripts
  `tmp/slot31/anchor_results_base.txt` / `anchor_results_base2.txt`.
- **Ceremony:** oracle = PATH bash `/opt/homebrew/bin/bash` **5.2.26(1)-release
  (aarch64-apple-darwin23.2.0)**, `--norc`, LC_ALL=C. psh: base **29456fdc**,
  discriminator `psh.__file__ = /Users/pwilson/src/psh-r3-1/psh/__init__.py`,
  version 0.762.0, neutral cwd `tmp/slot31/neutral/`, PYTHONPATH=worktree.
  Both parsers (`--parser rd` / `--parser combinator`) — identical psh results
  in every cell.

| Row | Cell | bash | psh (rd = comb) | Status |
|---|---|---|---|---|
| H7a | `[[ "" == *@(a|*) ]]` (eg on AND off) | rc=1 | rc=0 | RED (DIFF) |
| H7b | `[[ a == *!(a) ]]` (eg on AND off) | rc=1 | rc=0 | RED |
| H7c | `[[ "" == *!(*) ]]` (eg on AND off) | rc=0 | rc=1 | RED |
| case_H7b | `case a in *!(a))` | N | M | RED |
| case_H7a | `case "" in *@(a|*))` | N | M | RED |
| case_H7c | `case "" in *!(*))` | M | N | RED |
| rem_H7b | `v=a; ${v#*!(a)} / ${v##*!(a)}` | `[a][a]` | `[a][]` | RED (## leg) |
| rem_H7b_sfx | `${v%*!(a)} / ${v%%*!(a)}` | `[a][a]` | `[a][]` | RED (%% leg) |
| rem_H7a | `v=""; ${v#*@(a|*)} / ##` | `[][]` | `[][]` | same (control) |
| sub_H7b | `v=a; ${v/*!(a)/X} / ${v//…}` | `[Xa][Xa]` | `[X][X]` | RED (transformed bytes) |
| sub_H7a | `v=""; ${v/*@(a|*)/X} / //` | `[][]` | `[X][X]` | RED |
| sub_H7c | `v=""; ${v/*!(*)/X} / //` | `[X][X]` | `[][]` | RED |
| glob_negA | files {a,ab,b}: `*!(a)` | `ab b` | `a ab b` | RED |
| glob_negStar | `*!(*)` | literal (no match) | literal | same (control) |
| glob_atStar | `*@(a|*)` | `a ab b` | `a ab b` | same (control) |

- **Findings:** (1) `[[` treats extglob patterns as extglob regardless of the
  shopt in BOTH shells — extglob-off is not a divergence axis for `[[` anchors.
  (2) Probe-harness rule: `shopt -s extglob` must be on its OWN LINE for
  case/glob cells (`;`-joined = one parse unit, extglob not yet on — both
  shells identically rc=2, itself a control row). (3) bash `${v/*!(a)/X}` on
  `a` = `Xa` (zero-width match at 0) — `*!(a)` matches "" but not "a" in bash:
  direct evidence of continuation-sensitivity, not span complement.

### A2 — Derived consumer census (imports/call sites of engine surface, at 29456fdc)

Instrument: grep over `psh/` for `pattern_engine`, `match_shell_pattern`,
`extglob_fullmatch|extglob_match_at|_extglob_consume|expand_extglob|
compile_protected|compile_cached|contains_extglob` (transcript in turn log).

1. `[[ == / != ]]` — `psh/executor/enhanced_test_evaluator.py:310` → `match_shell_pattern`
2. `case` — `psh/executor/control_flow.py:759-767` → `match_shell_pattern`
3. removal `${v#/##/%/%%}` — `psh/expansion/parameter_expansion.py` (`matching_ends`/`matching_starts`)
4. substitution `${v/ // /# /%}` — `parameter_expansion.py` (`span_at`/`spanner`/`matching_spans`); NOTE existing consumer-level negation rule `_neg` (parameter_expansion.py:81-93): end-of-subject zero-width suppression for `!(...)` patterns
5. case modification `${v^…}` — `parameter_expansion.py` (per-char full_match)
6. pathname glob — `psh/expansion/glob.py`: TWO entries into the one engine: `_component_matcher` (glob.py:147, `PatternCompiler` + `pathname_profile`) and `_expand_extglob` (glob.py:439→473-481 → `extglob.expand_extglob` → `extglob_fullmatch`)
7. name filters — `print -m` (`psh/builtins/print_builtin.py:79`), `help` (`psh/builtins/help_command.py:50`), HISTIGNORE (`psh/interactive/history_manager.py:88`) → `match_shell_pattern`
8. encoder-only: `word_expander.py:712` (`runs_to_pattern_string`) — not a matcher consumer

Test-side: `extglob_to_regex` regex oracle cross-check
(`test_pattern_engine_matcher.py`) — corpus constraint to check (regex model
diverges from bash on star∘nullable-group composition).

### A3 — engine defect localization (read at 29456fdc)

- `pattern_engine.py:529-539` (`_Matcher._element_ends`, `op == '!'`): local
  span complement — returns every extent whose span fails all alternatives,
  then the DP freely continues. bash negation is NOT this relation.
- `pattern_engine.py:461-515` (`_ends` DP) + `:400-457` (`_full_simple`
  two-pointer): star composes with following nullable extglobs by plain
  reachability — H7a shows bash restricts a star's continuation positions.

### A4 — Generated finite-alphabet corpus + EXACT measured semantic model

- **Corpus instruments:** `tmp/slot31/corpus1.py` (deterministic enumeration:
  3,453 patterns = context(8 pre × 7 post) × op(5) × alt-list(12, incl. empty
  alt, nullable alts, depth-2 nesting) + plain controls + two-group chains;
  15 subjects = all strings over {a,b} len 0–3; **51,795 cells**) and
  `tmp/slot31/corpus2.py` (hardening shapes: two-group chains with pre/post,
  nested star-adjacent alternatives `@(*!(a))` etc., wildcard runs;
  922 patterns, **13,830 cells**). ONE bash spawn per corpus (batched script
  `corpus1_bash.sh`/`corpus2_bash.sh`); oracle PATH bash /opt/homebrew/bin/bash
  5.2.26 --norc LC_ALL=C; psh side through the exact `[[` path
  (`match_shell_pattern`, worktree import asserted) with a 55-cell end-to-end
  `[[` sample cross-check: **0 mismatches** (engine API ≡ `[[` consumer).
  Results: `tmp/slot31/corpus1_results.tsv`, `corpus2_results.tsv`.
- **Base divergence census (psh 29456fdc vs bash):** corpus1 **750/51,795**,
  corpus2 **283/13,830**. Distribution (corpus1, by shape): divergence is
  ZERO outside wildcard∘group-adjacent shapes — plain 0/645, non-adjacent
  posgroup 0/13,995, non-adjacent negation 0/5,280; star-adjacent
  482 (270 neg + 212 posgroup), `?`-adjacent 268. psh's span-complement
  `!()` with DP continuation AGREES with bash everywhere except
  wildcard-adjacency and the nested-negation rule.
- **MEASURED SEMANTIC MODEL — `tmp/slot31/bash_model.py` v4: EXACT
  (0/51,795 + 0/13,830 = 0/65,625)**, a C-faithful port of bash-5.2
  `lib/glob/sm_loop.c` (raw source fetched from savannah, cached at
  `tmp/slot31/sm_loop_5.2.c`; EXTMATCH verified verbatim L823-950; GMATCH
  star case L147-332). The rules (each pinned by the corpus cells named):
  1. **Main-loop group dispatch RETURNS extmatch's result** (L89-100) — a
     group not preceded by a wildcard composes by plain continuation
     (corpus: 0 divergence in non-adjacent shapes).
  2. **Star case** (L147-332): after collapsing consecutive `*`/`?`:
     a. `?(...)` directly in the wildcard run (L183-198): extmatch tried at
        the CURRENT position only; on failure the group is SKIPPED and the
        run continues (`*?(a)` ≡ try group here, else behave as `*` —
        pins: `*?(a)` matches "" AND "b"; `*?(a)a`≡`*a` on "b"→0).
     b. `*(...)` directly in the run (L211-231): extmatch tried at every
        position STRICTLY before subject end; on failure SKIPPED
        (pins: `**(a)@(a|*)` vs "" → 0; `**(a)` vs "" → 1 via skip+trailing).
     c. Pattern exhausted by the run (incl. after skips) → MATCH
        (trailing-wildcard rule L240-257; pin: `*?(a)` vs "b").
     d. **End-of-string negation special** (L259-268): remainder empty AND
        next element `!(...)` → MATCH **iff the negation group is not
        enclosed in any outer group in the full physical pattern text**;
        rest after the group IGNORED (pins: H7c `*!(*)` vs ""→1; `*!(a)`
        vs ""→1; `*!(a)b` vs ""→1; nested `@(*!(a))` vs ""→0,
        `!(*!(a))` vs ""→1). MECHANISM: glob_patscan is NUL-driven, not
        pe-bounded — from `!` (depth pre-set 1) it reaches depth 0 only via
        an ENCLOSING `)`; unenclosed → PATSCAN NULL → EXTMATCH degenerates
        to STRCOMPARE(≠) → the `!` arm INVERTS failure to success; enclosed
        → vacuous success → inverted to failure. In AST terms this is the
        compile-time property "negation node is a direct element of the
        root sequence".
     e. General loop (L284-331): rest tried at every position STRICTLY
        before subject end (first-char check is pure optimization) — kills
        empty-remainder matches of `@`/`+`-headed rests (pin: H7a
        `*@(a|*)` vs ""→0, `*@()` vs any→0-unless-parens-consumed).
  3. **EXTMATCH** (L823-950): `*` zero-instance try; `*`/`+` = one alt-span
     then rest OR whole-group-again (progress-guarded, srest>s); `?`/`@`
     trailing srest-starts-at-se optimization (semantically neutral); `!` =
     per-split complement (si..se) AND rest — continuation-sensitive,
     matching psh's current model in non-adjacent contexts.
  H7b mechanism: `*!(a)` on "a": general loop tries `!(a)`-dispatch at
  n=0 only (extmatch '!': split 0 rest-fails, split 1 complement-fails) —
  never at the empty remainder (strict bound), and the special requires
  n==se at star time → NOMATCH; psh's DP freely reaches end via
  complement-of-∅ at position 1 → MATCH. (H7b = rule 2e + 2d interplay.)

  Mechanism for 2d verified in source: `PATSCAN` (= glob_patscan, template
  in `sm_loop.c:697-780`) is NUL-driven (`for (s = string; c = *s; s++)`)
  with `if (s >= end) return (s)` — a top-level trailing `!(...)` scan hits
  NUL → NULL → EXTMATCH degenerates to STRCOMPARE (fails vs empty remainder)
  → the `!` arm of L265-267 INVERTS to MATCH; an alt-slice scan reaches the
  slice end → non-NULL → EXTMATCH runs on a garbage parse (single alt
  `(a`-style literal text, rest beyond slice ⇒ vacuously matched) →
  SUCCESS → inverted to NOMATCH. Hence "enclosed ⇒ no special".

### A5 — Per-consumer grid + substitution consumer-layer mechanism (MEASURED)

- **Instrument:** `tmp/slot31/probe_consumers.py`; transcript
  `consumer_grid_summary.txt`; tables `consumer_grid.tsv` (294 rows:
  14 patterns × 5 subjects × {`[[`, case, 4 removal legs, 4 substitution
  legs} + 9 quoted rows + 5 extglob-off controls) and `glob_grid.tsv`
  (12 patterns, fixture files a ab b ba .ha sub/a sub/ab). End-to-end both
  shells (bash --norc 5.2.26 vs psh -c at base), LC_ALL=C, neutral cwd.
  **DIFF: 61/294 string rows, 1/12 glob rows.** Combinator parser:
  byte-identical psh output on the full string grid (parser axis closed).
  extglob-off controls: 5/5 SAME (off surface agrees at base; must stay so).
- **Removal ops are pure slice-booleans**: every removal DIFF is exactly
  predicted by the boolean model applied to prefix/suffix slices
  (e.g. `${v#*@(a|*)}` on `a`: bash removes ALL — k=0 fails H7a, k=1
  matches; `${v##*!(a)}` on `a`: ends={0} only → `[a]`). No consumer-layer
  rules observed for removal.
- **Substitution has a measured consumer layer** (bash `subst.c`, fetched
  full 5.2 tarball → `tmp/slot31/bash-5.2/`): the psh-vs-bash substitution
  grid is FULLY explained by four mechanisms on top of the boolean engine:
  1. **`pat_subst` empty-subject single-shot** (subst.c:8959): on an empty
     subject every form reduces to ONE `match_pattern` call → rep or ''.
  2. **`match_upattern` pre-test** (subst.c:5361-5416): the pattern is
     wrapped (`*`-prepended unless already `*`-headed-non-`*(`;
     `*`-appended unless MATCH_END / already `*`-tailed) and strmatch'd
     against the whole remaining string; failure suppresses the whole
     operation. The wrapper INHERITS the star∘group quirks — measured pin:
     `${v/%!(a)/Z}` on `a` → bash `a` (pre-test `*!(a)` fails per H7b),
     psh `aZ`.
  3. **`match_pattern_char` position gate** (gm_loop.c:44-71): a scan
     position at end-of-string is eligible ONLY if the pattern head is a
     literal `*` (`if (*string == 0) return (*pat == '*')`). This is the
     entire "operator-and-anchor-specific empty-subject quirk": `?(x)`/
     `!(x)`/`@(|a)` heads are gated off on empty subjects for `/`,`//`,`/#`
     while `*!(a)`-headed patterns pass — measured pins: p0s0_sub all-Z vs
     p11s0/p12s0/p13s0 signatures.
  4. **`pat_subst` loop condition `while (*str)`** (subst.c:8967): the
     global-replace loop never scans the end-of-subject position (psh's
     matching_spans end-policy already models this).
- **KNOWN_DIVERGENCES measurements (for the integrator's re-ruling):**
  all four keys reproduced at base (q4_sub1/2/3 = `?(x)` on '' via
  `/`,`//`,`/#` → bash '' / psh 'Z'; neg7_sub3 = `!(x)` on '' via `/#` →
  same signature; q4_sub4 control `/%` → both 'Z'). The old rationale
  ("not derivable from the match extent") is SUPERSEDED: each key is now
  mechanically DERIVED from mechanisms 1+3 above (single-shot + end-position
  gate). The wider grid adds new same-family cells: `!(x)` on '' `/`+`//`
  (already agreeing because psh's `_neg` rule accidentally coincides),
  `@(|a)` on '' all four legs (bash: gate + pre-test both kill it),
  `${v/%@(|a)/Z}` on 'b' → bash 'b' / psh 'bZ' (pre-test), and
  `${v/%!(a)/Z}` on 'a' → bash 'a' / psh 'aZ' (pre-test). PROPOSAL (ruling
  is the integrator's): implement mechanisms 1-3 at the consumer seam
  (`parameter_expansion.py`) → ALL FOUR keys CLOSE (equality lock), plus
  the new cells; `_neg` becomes a DELETED-DECIDER (its input space is
  subsumed by the measured gate — census in Phase B).

### A6 — STOP-AND-REPORT: parse-side contributor (quoted parts inside extglob bodies)

- **Finding:** `[[ a == !("a") ]]` → bash 1 / psh 0; `[[ '*' == !("*") ]]`
  → bash 1 / psh 0; `${v/*!("a")/Z}` on 'a' → bash `Za` / psh `Z`
  (grid rows q1/q3/q7).
- **Localization: NOT the engine.** Engine-level checks (in-process,
  discriminator-verified): `match_shell_pattern('a', '!(a)')` → False ✓;
  `compile_protected` on `!(`+protected-`a`+`)` → False ✓; protected-`*`
  variant correct both ways ✓.
- **Root cause is parse-side:** the lexer emits `!("a")` inside `[[ ]]` as
  ONE unquoted WORD token whose single `LiteralPart` carries the RAW text
  `!("a")` — the quote characters never become part-level protection
  (token dump in turn log; `parts=()`, LiteralPart text `!("a")`,
  quoted=False). The `[[` seam (`_rhs_walk`) then treats the whole spelling
  as live pattern text, so the alt is the three-character literal `"a"`.
  Same class presumably affects case/glob words (unverified — needs its own
  probe battery if pursued).
- **Per the brief this is the lexer's extglob SYNTAX handling → NOT mine to
  touch.** Reported for ruling: assign to a successor (r18-lexer
  neighborhood) or rule a scope extension. Until ruled, these rows go into
  the battery's successor-visible residual-divergence structure.

### A7 — Existing-pin interactions (design constraints)

- `test_pattern_engine_matcher.py:139`
  (`test_new_fullmatch_agrees_with_regex_converter_on_nonneg`): the regex
  reference oracle CANNOT express bash's star∘group composition (its model
  is the clean closure semantics). The corpus filter must additionally
  exclude patterns where a wildcard-run is immediately followed by an
  extglob group (measured predicate = the engine's new compile-time flag);
  the generated bash-corpus battery replaces coverage there with a STRONGER
  oracle (live bash). Q3 ruling (oracle is PERMANENT) is respected — the
  oracle itself is untouched; only the agreement corpus is narrowed, with
  the narrowing documented. Declared here for the GO.
- The three `_extglob_consume`-equality tests in the same file compare the
  engine to itself post-W3 (both route to `pattern_engine`) — unaffected.
- `parameter_expansion._neg` (end-of-subject zero-width suppression for
  negation): subsumed by the measured `match_pattern_char` gate —
  DELETED-DECIDER protocol applies in Phase B (census + re-decide).
- Existing ~100-row battery + qm*/c2* + adv rows: all in non-quirk shapes
  (verified by the corpus census: 0 divergence in their classes) — expected
  to stay green unchanged; gate + battery enforce.
- Conformance extglob files (`test_double_bracket_extglob_conformance.py`,
  `test_extglob_parameter_expansion_conformance.py`): no
  documented-difference pins (grep silent); they cover psh==bash cells at
  base, so the fix (which only flips psh≠bash cells) should keep them
  green — Phase B greps their row lists for quirk shapes anyway.

### A8 — User-guide claims census

- `docs/user_guide/17_differences_from_bash.md:59` prose ("Extended glob
  patterns are supported once extglob is enabled, in globbing, [[ ]], and
  case") and `:950` table row "Extended glob patterns | Yes | Yes | ?() *()
  +() @() !()". No CLAIM_TESTS entry exists for the row (the meta-test
  polices "Full support" note spellings; this row's note is the operator
  list); conformance tests exist (`test_double_bracket_extglob_conformance`,
  `test_extglob_parameter_expansion_conformance`). The fix makes the claims
  MORE true; no new claim rows added → no CLAIM_TESTS change expected.
  `16_advanced_features.md:230` states extglob is NOT supported in a
  specific context (comment in an example) — Phase B checks whether that
  comment describes programmable completion (out of scope) before touching.

### A9 — Perf baseline (3.2 handoff, MEASUREMENT ONLY, zero perf code)

At base 29456fdc (in-process, discriminator-verified):
`CompiledPattern('*b').matching_starts('a'*N)`: N=500: 0.006s; 1000:
0.023s; 2000: 0.090s; 4000: 0.452s; 8000: 1.424s (quadratic doubling ≈4×,
matching the brief's figures). Left AS-IS per A9; 3.2 owns it.

## Phase B record (commits at tip 7bec085c; evidence SHA per row)

### B1 — Commit log (base 29456fdc → tip 7bec085c, six commits)

1. `1c9bf6cc` engine: `Extglob.enclosed` + `_seq_bash_quirk` (transitive) +
   `_BashMatcher` + per-slice relation routing. +339/-12 in
   `pattern_engine.py` only. Existing `_Matcher`/`_full_simple`/`_ends`
   bodies UNTOUCHED (byte-for-byte; verify: `git show 1c9bf6cc` has no hunk
   inside them).
2. `4a1d412c` consumer layer: `_sub_machinery`/`_any_match` + the four
   substitute_* ops rebuilt on the measured mechanisms; `_neg` +
   `_substitute_scan` DELETED; KNOWN_DIVERGENCES emptied + retired test
   replaced by `test_former_known_divergences_now_match_bash`; two
   `?()`-on-empty characterization rows flipped to live-bash values.
3. `3e636607` battery `test_pattern_bash_composition_differential.py`
   (12 tests) + regex-oracle corpus narrowing via the flag.
4. `fb2f1a33` doc sweep (pattern_engine narrative, matching_spans,
   _extglob_consume, expansion CLAUDE.md).
5. `af236478` recursion-contract pin made limit-relative (psh raises the
   process limit to 40,000 at activation — process_lease.py; fixed-size
   raises-arm completed under it in full-suite runs; found by the full
   expansion-dir run, fixed same turn).
6. `7bec085c` user-guide `[[` example: stale "extglob not supported" note
   replaced with a verified extglob example (both shells, both parsers,
   shopt on AND off).

### B2 — Certification rows (post-state; instrument + since-SHA both ends)

| # | Claim | Instrument (post-state check) | Result |
|---|---|---|---|
| C1 | Engine == bash on the full evidence corpus at tip | offline replay of `corpus1_results.tsv`+`corpus2_results.tsv` bash columns vs `match_shell_pattern` (in-process, discriminator asserted), turn log 2026-08-02 | 65,625 cells, 0 mismatches, 0.29s |
| C2 | The three `[[` anchors green at tip, BOTH parsers, extglob on/off | `probe_anchor.py` rerun at af236478 (ceremony block records tree SHA + discriminator + bash 5.2.26) | 6/6 cells == bash (was 0/6 at base) |
| C3 | Consumer grid closed | `probe_consumers.py` rerun at tip (`consumer_grid_tip.txt`) | DIFF 61→2; survivors = lex_q1/lex_q3 (R4 successor family); glob 12/12 |
| C4 | Red-on-base DEMONSTRATED for new/flipped pins | detached base worktree `tmp/slot31/basecheck` @29456fdc (discriminator printed), new test files copied in: `test_former_known_divergences_now_match_bash` FAILED, both `?()`-on-empty rows FAILED (base emits `[-]`); transcript in turn log | red at base, green at tip (suite run below) |
| C5 | R2c collected-proof | `pytest --collect-only -q` on both differential files at tip | retired name collected **0** times; replacement + all 12 battery tests collected (17 total; transcript in turn log) |
| C6 | R2d stale-rationale sweep | phrase-family greps over psh/ + tests/ (fixed list: "not derivable from the match extent", "pre-existing `?()`", "negation suppresses", "_substitute_scan", "def _neg(", "KNOWN_DIVERGENCES = {") | all 0 (the `def _neg` grep's one hit is `test_command.py#_negate`, unrelated); new-invariant vocabulary present (\_seq_bash_quirk ×19, SLICE-END-RELATIVE, match_pattern_char, empty-subject single-shot) |
| C7 | R2e residual structure empty of the q4/neg7 keys | `RESIDUAL_DIVERGENCES` in the battery contains ONLY lex_q1/lex_q3 (read `git show 7bec085c:tests/unit/expansion/test_pattern_bash_composition_differential.py`) | ✓ |
| C8 | R3c narrowing derived counts + coverage transfer | derivation script (turn log): 6,000 cases → 3,624 previously eligible → **267 excluded (237 distinct patterns)**; excluded group-ops {*,+,?,@} ⊆ battery flagged ops {!,*,+,?,@} | ✓ derived, never hand-tallied |
| C9 | Suite-level green at tip | `pytest tests/unit/expansion/ -q` at af236478 | 2,768 passed / 17 skipped |
| C10 | Battery runtime budget | module run at 3e636607 | 12 tests in ~2.1s (<20s budget) |
| C11 | ruff + mypy | at every commit | clean; mypy 275 files |
| C12 | Claims meta-test after guide edit | `pytest tests/conformance/test_claims_have_tests.py -q` at tip | 57 passed |

### B3 — DELETED-DECIDER census (R2b): `_neg` + `_substitute_scan` end-policy

Deleted deciders and their whole input space, re-decided by the measured
mechanisms (grid `consumer_grid.tsv`/`consumer_grid_tip.txt` is the
cell-level evidence):

| Input class | Old decision | New decider | Outcome |
|---|---|---|---|
| `//`, non-empty subject, zero-width at end (any pattern) | suppressed (n>0 arm) | mechanism 4 (loop never scans end) | SAME |
| `//`/`/` empty subject, non-negation nullable, `*`-headed (`*(q)`, `*!(x)`) | emitted | gate: head-char-star ⇒ eligible | SAME for `*(q)`; `*!(x)` all-four-legs now Z (bash-verified, was psh-divergent) |
| `//`/`/` empty subject, non-`*`-headed nullable (`?(x)`, `@(|a)`, `+()`) | emitted (DIVERGENT from bash) | gate blocks | CHANGED → bash-equal (q4 closure) |
| `//`/`/` empty subject, negation `!(x)` | suppressed via `_neg` | gate blocks (`!` head) | SAME outcome, one general mechanism |
| `/` end-of-subject zero-width, negation | suppressed via `suppress_end_empty` | gate | SAME |
| `/#`/`/%` legs (never covered by `_neg`) | no rule (DIVERGENT: `${v/%!(a)/Z}` on a → aZ) | pre-test + gate | CHANGED → bash-equal |
| sibling-table check | `_neg`/`_substitute_scan` callers censused (grep): only the two in-file sites; no other module imported them | — | ✓ no orphaned caller |
| created-shape check | `_sub_machinery` wrapper Sequences share element nodes, fresh Sequence per call; `compile_cached` untouched (no cache contract change) | — | ✓ |

### B4 — Mutation-proof table (each class fails for its OWN reason; all reverted)

| Mutation | Instrument that noticed | Failure reason (verbatim class) |
|---|---|---|
| M1 engine: enclosed rule → `return True` | corpus test | "corpus divergences" listing exactly the enclosure cells (`@(*!(a))` family) |
| M2 consumer: suffix pre-test deleted | consumer-family test | `('pretest_end', 'psh!=bash', '[a]', '[aZ]')` + pretest_end2 |
| M3 consumer: end gate forced open | consumer-family + q4-closure tests | `('emptysub_q', 'psh!=bash', '[][][][Z]', '[Z][Z][Z][Z]')` etc. |
| M4 engine: memo disabled | state guard | "pattern '**(a)b' on 'a'*16: 985 states (bound 324)" — NAMES the pattern (R1) |
| M5 battery: residual bash value corrupted | residual test | `('lex_q1', 'oracle drift', '1')` — drift arm, distinct from the psh arm |

### B5 — Declared engineering facts

- **A9 complexity declaration:** non-flagged patterns byte-identical paths
  (commit-1 has no hunk in `_Matcher`); flagged patterns: per-k slice
  booleans for set relations; measured state growth linear for single
  trailing groups (`*!(a)`: 259 states at N=128) and ~N²/2 for `**(a)b`
  (8,386 at N=128) — bounds pinned in the battery with pattern-naming
  failures. NEW recursion dimension DECLARED: flagged patterns recurse per
  star-run/group dispatch (pattern-structure-bounded, never subject length);
  contract pinned limit-relative (100-unit chain fine; limit-many units =
  clean RecursionError, an expected shell error). `matching_starts`
  quadratic untouched (3.2's; baseline in A9 above). No cache/mutability
  changes.
- **`matching_spans` is now a test-pinned generic relation** (substitution
  uses the bash loop at the seam); docstring updated, relation kept.
- **Guide fix (7bec085c)** verified live: `[[ "document.pdf" ==
  @(*.pdf|*.doc) ]]` → "Document" in bash 5.2.26 AND psh, shopt on/off.

### B6 — Remaining for done (pending integrator GO, one heavy run at a time)

1. Full local gate `python -u run_tests.py --parallel` (base figure to beat:
   22,820 passed / 1,590 skipped / 10 xfailed).
2. compare-bash EXACT `python -m pytest tests/behavioral --compare-bash -n
   auto -q` (base 2,986 passed / 26 skipped).
3. Discharge audit + bounced-rows replay (no bounced rows exist this slot —
   will state the negative), final-tip declaration, completion report.

### B7 — Gate run 1 (R5 GO): FALSE RED, diagnosed + neutralized (2026-08-02)

- `python -u run_tests.py --parallel > tmp/gate-1.txt` at 7bec085c:
  **22,831 passed / 1 failed / 1,590 skipped / 10 xfailed** (+11 passed vs
  base; delta reconciliation at final declaration). The single failure:
  `test_residual_divergences_still_divergent`, asserting `'1' == '0'` where
  the failing side was the row CONSTANT `bash_val` — while the on-disk file
  says `"1"` (git diff clean; bash itself answered '1', i.e. correctly).
- **Root cause: stale pytest assertion-rewrite cache from the M5 mutation
  cycle.** The M5 mutation (`"1", "0"` → `"0", "0"`) is byte-length-neutral,
  and the mutated compile + `git checkout` revert landed within the same
  mtime second, so the mtime+size source-validation header still matched and
  BOTH cached `.pyc`s (pytest-rewritten + plain) kept serving the MUTATED
  module. Reproduced serially (not an xdist effect); a byte-equivalent
  fresh-file test passed — module identity was the discriminator.
- Fix: removed
  `tests/unit/expansion/__pycache__/test_pattern_bash_composition_differential*`;
  module then 12/12 under `-n 2` AND serially. NO source change.
- **HARNESS LESSON (campaign mutation protocol):** after reverting a
  same-length source mutation, drop the target's `__pycache__` entries (or
  `touch` into a new second) — a same-second same-size revert is invisible
  to mtime+size validation.
- Reported (msg 15bd6e4d); gate RERUN GO requested per the per-run rule.

### B8 — FINAL: gate rerun + compare-bash GREEN; tip DECLARED (2026-08-02, R6)

- **Gate rerun** (`tmp/gate-2.txt`, tree 7bec085c, R6 GO):
  **22,832 passed / 1,590 skipped / 10 xfailed — ALL PHASES PASSED.**
  Delta vs base (22,820/1,590/10): **+12 passed, DERIVED reconciliation**:
  +12 battery tests (`--collect-only` C5 transcript) +1
  `test_former_known_divergences_now_match_bash` −1 retired
  `test_known_divergences_are_still_divergent` = +12 ✓ exact (matches R6's
  predicted figure).
- **compare-bash** (`tmp/compare-bash-1.txt`, same sequence):
  **2,986 passed / 26 skipped — EXACT base composition** (no behavioral/
  golden rows added, as declared).
- **M5-replay one-command (R6 verifier note):**
  `sh tmp/slot31/replay_mutations.sh` from the worktree root — runs all
  five mutation classes WITH cache hygiene (clean_caches after every
  revert), prints each class's own failure reason, ends with tree-clean +
  module-green. Verified at 7bec085c: M1 corpus-names-enclosure-cells,
  M2 pretest_end bytes, M3 emptysub family, M4 pattern-naming state bound,
  M5 oracle-drift arm; post-replay 12/12 green, 0 dirty files.
- **DISCHARGE AUDIT (all claim rows):** Phase A rows A1-A9 anchored to
  `tmp/slot31/` instruments (probe scripts + transcripts + TSVs + cached
  bash source); Phase B rows B1-B7 anchored to commits (git show), cert
  table C1-C12, census B3, mutation table B4 (+ the replay script above).
  Totals: 12 cert rows + 8 census classes + 5 mutation classes, all
  instrument-anchored; counts derived from producing scripts (corpus sizes,
  narrowing counts, gate deltas), none hand-tallied.
- **BOUNCED-ROWS REPLAY: no bounced rows exist this slot** (no verifier
  round has run; the two in-slot self-caught issues — the recursion-limit
  flake and the stale-pyc false red — are recorded at B1-5 and B7 with
  their fixes and are covered by the replay instruments).
- **FINAL TIP DECLARED: `7bec085c`** (six commits over 29456fdc).
  MECHANICAL TIP RULE in force from this declaration: any further commit —
  even comment-only — will be declared by SendMessage BEFORE landing.

### A10 — Phase B design (proposed; awaiting GO)

**Key structural insight:** the quirk rules are SLICE-END-RELATIVE (the
star-case bounds and the end-of-string special depend on where the matched
slice ends), so for affected patterns "pattern matches text[i:k]" is a per-
(i,k) boolean, NOT expressible by one forward reachability pass. Membership
of k in `matching_ends` must be evaluated per-k for affected patterns.

1. **Engine (`pattern_engine.py`), flag-gated additive path — no rewrite:**
   - Compile-time: per-Sequence flag `bash_composition` = the sequence (or
     any nested alt) contains a wildcard-run element (Star/AnyChar run)
     immediately followed by an Extglob, OR a trailing-after-star negation;
     plus per-Extglob `enclosed` (inside any alt) for rule 2d. Non-flagged
     patterns (all plain globs, all non-adjacent groups — 100% of the
     existing battery/adv/qm/c2 rows) keep TODAY'S code paths byte-for-byte
     (`_full_simple` / `_ends` DP).
   - Flagged patterns: new iterative evaluator implementing the measured
     model (bash_model.py v4 semantics) on the compiled AST: backward
     element-indexed DP with memo on (element, position) per fixed slice
     end; wildcard runs processed as units (iterative, no per-star
     recursion — preserves the 50k-star guarantee); recursion ONLY into
     extglob alternatives (compile-bounded, same contract as today);
     alt-span matches memoized per (alt, start, end). Complexity DECLARED:
     flagged patterns pay O(n) per-k evaluations for set relations (worst
     ~O(nodes·n³) nested); deterministic state-count guard added for the
     new path (per the existing count_states pattern). Non-flagged
     complexity UNCHANGED. No cache/mutability changes (3.2 owns freezing).
   - for_pathname arms ported from the C (slash checks in star case,
     general-loop slash bound); leading-dot policy stays in glob.py.
2. **Consumer seam (`parameter_expansion.py`), substitution only:**
   empty-subject single-shot; pre-test with wrapped compiled pattern
   (Star-prepend/append per measured head/tail rules); end-position gate
   (head-is-Star rule) replacing the blanket end-policy; `_neg` deleted
   under DELETED-DECIDER (input space censused, re-decided by the gate).
   Removal ops unchanged (pure slice-booleans, now correct via engine).
3. **Pins/battery:** three `[[` H7 rows + per-consumer propagation pins
   (case, `#`/`##`/`%`/`%%`, `/`/`//`/`/#`/`/%` with TRANSFORMED BYTES,
   glob fixture) as red-on-base equality pins; generated battery lands
   default-run (corpus generator + ONE bash spawn per bucket + in-process
   engine cells + reduced per-consumer end-to-end cross; runtime budget
   measured and reported; targets <20s); KNOWN_DIVERGENCES per ruling;
   regex-agreement corpus narrowed per A7; extglob-off control rows;
   quoted-part rows (engine-level TRUE pins + the parse-side rows as
   documented residuals per A6 ruling).
4. **Docs:** pattern_engine module narrative + psh/expansion/CLAUDE.md
   engine section sweep (the "reachable-end set serves the four relations"
   teaching must be qualified by the bash-composition path; state the
   slice-relative invariant, point at code; no sketches).

## Hold state (verification round 1)

- 2026-08-02 (later): integrator confirms completion figures ACCEPTED;
  **VERIFICATION ROUND 1 RUNNING** (4 agents in their own detached
  worktrees; they read this ledger + tmp/slot31/ but never measure in my
  worktree). **HOLD**: tip verified still 7bec085c, tree clean (0 dirty
  files); no commits of any kind without a prior declared SendMessage, and
  none intended until the round returns. Any correction noticed while
  waiting gets written HERE as a note + messaged, never landed. Inbox
  polled: numbered rulings unchanged through R6.

## Phase C (R7 BOUNCE: 3 blockers, 14 nits) — 2026-08-02

### C-0 — R7 received (read in full); reproduction + true mechanism

- Convention note: R7's replay numbers are **rc** (0=match); my TSVs use
  match-booleans (1=match). Both blocker cells reproduced in a FRESH
  detached tip worktree (tmp/slot31/tipcheck, discriminator asserted,
  removed after): `[[ aa == *a*!(a) ]]` bash NO-match / tip MATCH (B-2:
  base also wrongly... base NO-match per R7 — tip introduced nothing here,
  the class was never closed); `[[ aa == *a*!(a)?a ]]` bash NO-match / tip
  MATCH (B-1 regression: base matched bash); removal
  `matching_ends('aa')` for `*a*!(a)` = {1,2} at tip (bash: {} of matches
  ending... bash's ##-removal gives 'a' ⇒ slice-boolean at k=1 only).
- **TRUE MECHANISM (from the cached sm_loop.c, not cell-fitting): the
  glibc star-jump.** The star case's general loop calls the inner GMATCH
  with `&end` (L313); the inner call, on REACHING ANOTHER STAR, returns
  success immediately recording (pattern, string) (L150-155); the outer
  loop then COMMITS to that position (`p = end.pattern; n = end.string;
  continue`, L324-329) and never retries earlier stars. Consequences:
  (1) between consecutive stars, a SIMPLE-element segment (literals/
  brackets/?) is placed at its LEFTMOST match, deterministically;
  (2) a later wildcard-run's ENTRY position is that committed position;
  (3) the end-of-subject negation special (L262) fires only when the
  ENTRY position == se — so `*a*!(a)` on "aa" commits the segment at
  n=0, enters star2 at n=1 ≠ se, the special is DEAD, and the general
  loop's extmatch fails → bash NO-match. My port searched ALL positions
  (no jump), reached star2 at n=2==se, and fired the special → tip
  wrongly MATCHES. The jump is invisible to plain patterns (a later
  star's scan covers all later positions — why corpus1/2 and every
  existing suite stayed green) and to group-containing segments
  (EXTMATCH's continuations pass NULL ends, L869/877/907/943 — no jump
  through groups). The blind spot is EXACTLY star-simple-segment-star.
- bash_model.py v4 shares the missing-jump defect (its general loop is a
  plain positional search) — corpus1/2 never exercised the difference.
  Model v5 (with jump) + widened corpus3 next; engine fix mirrors.

### C-1 — Widened corpus (corpus3) + model v5: EXACT

- **Instrument:** `tmp/slot31/corpus3.py` (deterministic; star-literal-star
  PREs, post-negation continuations, group-in-segment, multi-run chains;
  alphabets {a,b} AND disjoint {a,c}; subjects len 0-4). One bash spawn per
  run (script file; 372,187 lines, bash chews it in 1.27s measured).
  **372,186 cells, 10,186 distinct patterns.** Results
  `tmp/slot31/corpus3_results.tsv`.
- **Model v5** (`bash_model.py`, star-jump added; header records v5):
  **0 mismatches on corpus3 at FIRST validation** (mechanism-derived, not
  cell-fitted) and 0 on corpus1/2 (regression-checked after fixing one port
  bug: `_segment` passed the alt-start index where extmatch expects the
  `(` index — caught by the corpus1 re-validation, 4,612 mismatches, fixed
  before any engine work). One-command replay:
  `cd tmp/slot31/neutral && PYTHONPATH=<worktree> python3 ../corpus3.py`.
- Jump-model prediction `*a*!(a)` vs "ba" = MATCH confirmed by corpus3
  (bash 1) — the special DOES fire when the committed entry equals se.

### C-2 — Engine star-jump fix: 0 mismatches over the FULL union

- `_BashMatcher._match` star case restructured: star-entry loop re-entered
  on jump commits; general scan walks `_segment` (the GMATCH-with-&end
  port: 1=full, 2=jump-at-star with committed position, 0=fail; groups
  jump-opaque). Star-run scanning + jump commits ITERATIVE (the old
  per-star general-loop recursion is gone; recursion = group dispatches +
  alt nesting only).
- **Validation: corpus1 0/51,795; corpus2 0/13,830; corpus3 0/372,186 —
  UNION 0/437,811 in 2.14s in-process** (discriminator-verified). Blocker
  cells: `*a*!(a)` vs aa → no-match ✓, `*a*!(a)?a` vs aa → no-match ✓,
  `*a*!(a)` vs ba → match ✓ (all bash-equal).
- **Battery grammar v2**: `widened_patterns(second)` (corpus3 generator
  mirrored) × {a,b} len≤4 + {a,c} len≤4 mirror joins the corpus test (ONE
  bash spawn, 436,761 cells DERIVED in the failure message); B1/B2/B2b
  anchor rows (both-sides pinned); rem_jump/sub_jump/subc_jump/case_jump
  consumer rows (bytes measured both shells, byte-identical at tip);
  lex_case_q1 residual row (N13, bash N / psh M measured); flag-predicate
  rows extended. Battery 15 tests, **5.9s** (budget held).
- **Count reconciliation (N4/N12), all derived:** 65,625 = corpus1+corpus2
  SUM (70 patterns generated by both, double-counted ×15 subjects =
  1,050); 64,575 = deduped battery-v1; 372,186 = corpus3/widened; battery
  grammar-v2 = 64,575 + 372,186 = **436,761**; evidence-TSV union =
  436,761 + 1,050 = **437,811**. Every prior "65,625"/"64,575" claim now
  scoped in docstrings/CLAUDE.md to its corpus.

### C-3 — INCIDENT: replay-script git-checkout wiped uncommitted Phase C state (recovered; two harness lessons)

- Running the mutation replay mid-Phase-C, its `revert()` — `git checkout
  --` on the three target files, written when the tree was CLEAN — DISCARDED
  the uncommitted Phase C edits (engine jump fix, battery widening, memo).
  Caught immediately: post-replay battery ran 12 tests (not 15) and marker
  greps (`_segment`/`widened_patterns`/`_sub_machinery_cached`) came back 0.
- Recovery: scripted, idempotence-checked re-application —
  `tmp/slot31/restore_phase_c.py` + `restore_battery.py` (now permanent
  instruments; each replacement asserts uniqueness). Re-validated after:
  union 0/437,811, expansion suite 2,771 passed, ruff+mypy clean.
- Replay script hardened: file-copy backup/restore (`backup()`/`revert()`
  via `cp`, never git) — first hardening attempt had the `backup` CALL
  before its shell function DEFINITION (silently "not found" under plain
  `sh`; reverts then had no backup and mutations persisted — diagnosed via
  marker greps + `end_eligible = True` residue and repaired by the same
  restoration scripts). Final replay (fixed script): all five mutation
  classes fail for their OWN reasons (M1 now reported by the widened
  corpus itself: "37 divergences over 436761 grammar-v2 cells"), post-state
  15/15 green, diffs intact.
- **LESSONS (campaign):** (1) mutation tooling must NEVER revert via
  `git checkout` — file-copy backups only (the reappraisal-#18 rule applies
  to tooling, not just hands); (2) plain-sh functions must be DEFINED
  before their call site — a missing function is a swallowed error, so
  verify the backup EXISTS before mutating (the hardened script now runs
  `backup` after all definitions).

### C-4 — B-3 corrections (A9 declaration RESTATED + measurements + 3.2 handoff)

- **B5's "non-flagged patterns byte-identical" was true of the ENGINE, false
  of the SLOT** (R7 B-3): the substitution wrapper `*`-wraps unanchored/
  anchored patterns, so ANY extglob-headed pattern becomes quirk-flagged and
  substitution runs `_BashMatcher` per remaining-suffix — quadratic
  full-match per position, cubic under O(n) matches. CORRECTED DECLARATION:
  the consumer layer's bash-faithful mechanics carry bash-shaped costs on
  extglob substitutions; plain-glob (non-extglob) substitution patterns
  wrap to plain-glob wrappers and keep the fast paths.
- **Measurement table** (in-process `r=${v//+([[:space:]])/-}` on
  word-space text, this tree, Phase C tip): n=300: 453 ms; 600: 457 ms;
  1200: 1,848 ms; 2400: 7,405 ms (~×4 per doubling at the top).
  Attributed verifier/integrator end-to-end figures (R7): base 0.47s vs
  round-1 tip 2.76s at n=1200; verifier in-process 12.5ms→18,370ms at
  n=1600. Mitigation (R7, attributed): tip still beats live bash on the
  idiom (bash itself is cubic there).
- **Wrapper memo (N3)** implemented (`_sub_machinery_cached`, lru 512,
  keyed pattern/anchor/extglob): measured 50k hits = 3 ms vs 50k rebuilds
  = 38 ms (~0.7 µs/call saved — construction only; the dominant matching
  cost is unchanged, as declared in its docstring). Broader fast-path NOT
  taken (would need corpus-proven equivalence per R7 item 7) — handed off.
- **3.2 HANDOFF ROW (named exit criterion):** restore linear substitution
  scanning UNDER the bash-mechanics semantics (pre-test, end gate,
  single-shot, suffix-loop) — baselines: the table above + A9's
  matching_starts quadratic (0.006→1.424s, N=500→8000).

### C-5 — Nit dispositions (fix-in-slot set)

- **N1** matching_spans: census = zero production callers (grep transcript
  in turn log); RECOMMENDATION: KEEP as labelled PERMANENT test-pinned
  relation oracle (extglob_to_regex precedent) — it is the only direct pin
  of the walk algebra spanner/span_at compose into. Docstring + CLAUDE.md
  updated accordingly.
- **N2/N5** _contains_negation: census = test-only (regex-oracle negation
  exclusion); labelled in its docstring, same precedent.
- **N3** wrapper memo: C-4 above.
- **N8** guide 17_differences_from_bash.md extglob sentence rewritten:
  globbing/case need the shopt at parse time; `[[ ]]` recognizes extglob
  regardless — now agrees with the guide-16 example (both bash-verified).
- **N9** CLAUDE.md four-relations bullet: span_at/spanner are the
  substitution primitives; matching_spans labelled test-only oracle.
- **N13** lex_case_q1 added to RESIDUAL_DIVERGENCES (measured: bash N /
  psh M), divergent-direction with the engine-truth rows unchanged.
- **N14** CLAUDE.md recursion sentence now limit-relative (matches the
  battery pin + af236478).
- **N10 ERRATA:** ledger C6's ABSENT-check listed the phrase family as
  `def _neg(`; the grep ACTUALLY RUN was fixed-string `def _neg` (its one
  hit, `test_command.py#_negate`, was dismissed by inspection as a
  different symbol). The instrument of record is the actual spelling; C6's
  row should be read with this erratum.
- **N7 NOTE:** the grammar-v2 battery is intentionally NOT collectable at
  base (it imports `_seq_bash_quirk`, which does not exist there); the
  red-on-base instruments for its rows are the Phase A/C probe harnesses
  (`probe_anchor*.py`, `probe_consumers.py`, corpus drivers) plus the
  detached-worktree runs recorded at B-4/C-0 — three-point replayability
  lives in those instruments, not in running the battery at base.
- **C-0 ERRATUM:** C-0 said B-2's base read "NO-match"; in rc terms R7's
  "base 0" = rc 0 = base MATCHED (wrongly). The corrected triple for
  `[[ aa == *a*!(a) ]]`: bash NO-match, base match, round-1-tip match,
  Phase-C tip NO-match (bash-equal).

### C-6 — Phase C verification at the new state (pre-commit)

- Expansion suite **2,771 passed / 17 skipped**; battery **15 passed,
  5.9s**; claims meta-test 57 passed; ruff + mypy clean (275 files);
  corpus union **0/437,811**; mutation replay one-command
  (`sh tmp/slot31/replay_mutations.sh`), five classes, own reasons, state
  preserved, cache hygiene + cp-backups.

### C-7 — Phase C commits landed (declared first, msg ab2ffdee)

- `8713f7e0` star-jump + grammar-v2 battery (+303/−118: pattern_engine,
  battery, CLAUDE.md).
- `b49b8e9c` B-3 declaration + nits N1-N3/N5/N8 (+45/−21:
  parameter_expansion, extglob, guide 17).
- Candidate round-2 tip: **b49b8e9c** (8 commits over base). Tree clean.
  Awaiting fresh heavy-run GO (R7) for gate + compare-bash; final-tip
  declaration after both are green.

### C-8 — R8 received (read in full); binding notes applied

- Commits approved as declared; landed exactly as scoped (C-7).
- **N3/MEDIUM-6 (R8 note 2) — 3.2 HANDOFF ROW AMENDED:** the round-2
  `_sub_machinery_cached` lru(512) is a NEW cache of `CompiledPattern`
  objects (wrapped Sequences sharing element nodes). 3.2's freeze charter
  (MEDIUM-6, writable cached pattern ASTs) must cover: `compile_cached`
  (lru 4096, pre-existing) AND `_sub_machinery_cached` (lru 512, this
  slot). Named here as a 3.2 exit-criterion input alongside the linear-
  substitution-scanning criterion and the perf baselines (C-4/A9).
- **Detached-worktree runnability (R8 note 3):** `restore_phase_c.py` /
  `restore_battery.py` operate on RELATIVE paths (run from any worktree
  root); `replay_mutations.sh` resolves the worktree from its own location
  (`cd "$(dirname $0)/../.."`) — both runnable as-is from a verifier's
  detached copy. Corpus drivers (`corpus1/2/3.py`) now honor a
  `PSH_WORKTREE` env override (default = this worktree) so a verifier can
  aim them at their checkout: `PSH_WORKTREE=<wt> PYTHONPATH=<wt> python3
  corpus3.py` from any neutral cwd (the driver asserts the discriminator).
- N1 KEEP accepted (note 4); jump-mechanism account accepted (note 1) —
  replay stays current; sequence GO pre-granted (note 5) — executing now
  with the pgrep precondition recorded below.

### C-9 — FINAL (round 2 candidate): sequence GREEN; tip DECLARED b49b8e9c

- Precondition recorded: `pgrep -f pytest` → CLEAR before the sequence.
- **Gate** (`tmp/gate-3.txt`, tree b49b8e9c): **22,835 passed / 1,590
  skipped / 10 xfailed — ALL PHASES PASSED.** Delta vs the round-1 figure
  (22,832): **+3, DERIVED** = the three new anchor params (battery
  test_double_bracket_anchor_rows 3→6 rows; battery module 12→15 tests;
  no other collection changes — `--collect-only` on the battery names
  exactly B1/B2/B2b as the additions). Vs base: 22,820 + 12 (round 1)
  + 3 (round 2) = 22,835 ✓ exact.
- **compare-bash** (`tmp/compare-bash-2.txt`): **2,986 passed / 26
  skipped — EXACT base composition** (no behavioral/golden rows added
  either round).
- Post-state checks at the landed tip preceded the sequence: pattern
  modules 109 passed; ruff + mypy clean; corpus drivers now
  PSH_WORKTREE-overridable (C-8).
- **FINAL TIP DECLARED: `b49b8e9c`** (8 commits over 29456fdc: 1c9bf6cc,
  4a1d412c, 3e636607, fb2f1a33, af236478, 7bec085c, 8713f7e0, b49b8e9c).
  MECHANICAL TIP RULE remains in force: any further commit is declared by
  SendMessage BEFORE landing. Standing by for verification round 2.

### C-10 — Procedural fault acknowledged (R4-C poll-before-send slip)

- My GO-request message (f2746198) went out WITHOUT re-polling the inbox:
  R8 (which pre-granted that very sequence) was already on file, and the
  message neither ACKed it nor used its grant. The subsequent turn read R8
  in full, applied its notes (C-8), ran the sequence under the pre-grant,
  and ACKed R8 in the figures report (d578e70c) — but the request itself
  was a poll-before-send violation. Logged as a fault against me; the
  R4-C rule exists precisely because the channel crosses (it did, twice
  this slot). Re-affirmed practice: EVERY SendMessage is preceded by an
  inbox read in the SAME turn, including requests.

## Hold state (verification round 2)

- R9 received (read in full): **ROUND 2 RUNNING** against b49b8e9c
  (wf_278fd24b-a62, 4 agents, detached worktrees; scope: three-point
  anchor replays, fresh third-alphabet corpus beyond grammar-v2,
  star-jump implementation audit, B-3 discharge re-measure, recovery
  completeness incl. the hardened replay script, all 14 nit discharges,
  diff scope). C-10 closes the R4-C matter; N3/N1 confirmations accepted.
- **HOLD verified:** tip b49b8e9c, tree clean (0 dirty), no runs in
  flight. No commits without a prior declared message; wait-time
  observations go HERE, not the tree. R9 ACK rides my next send (the
  round-2 verdict response).

## Phase D record (R10 BOUNCE: 2 blockers, 15 nits)

### D-0 — R10 received (read in full); replays

Both blockers reproduced before fixing. Convention: R10 replay numbers are
rc; TSV values are match-booleans.

### D-1 — B2-1: the RAW-CHAR wrap guard (measured, implemented, pinned)

- **Instrument:** `tmp/slot31/corpus4.py` — backslash/escaped-metachar axis
  (27 all-context + 4 substitution-only patterns × 18 subjects with literal
  metachars × {`[[`, case, 4 removal legs, 4 substitution anchors} =
  **2,016 cells**), end-to-end both shells. At the round-2 tip: **DIFF 7,
  all substitution** — six `*…\*`-family cells (the R10 45-cell class) +
  ONE paren-pun cell (`${v/%(a)/Z}` on `(a)`: bash's STRING-built wrapper
  `*`+`(a)` parses as the `*(a)` GROUP and suppresses; my element-built
  wrapper could not pun). `[[`/case/removal: **0 DIFF over the whole axis**
  (engine escape handling bash-equal; axis coverage recorded).
- **Mechanism** (subst.c `match_upattern`, cached source): the OUTER guard
  is a raw-char both-ends test — head raw `*` (non-`*(`) AND last char `*`
  (EVEN escaped) ⇒ NO wrapper, the pre-test is the raw pattern itself;
  otherwise npat is built as a STRING (prepend rule; append unless tail is
  a `*` not escaped by an ODD backslash run), preserving the paren pun.
  Implemented verbatim in `_sub_machinery_cached` (string-compiled
  wrapper); `end_eligible` also raw-char now (`pattern.startswith('*')` —
  equivalent on the old corpus, exact on this axis).
- **Result:** corpus4 re-run → **0/2,016**. NO survivors → nothing new in
  RESIDUAL_DIVERGENCES from this class. Red-on-base: the family was
  divergent at BASE and at the round-2 tip (R10 replay + the corpus4
  round-2-tip transcript in the turn log = the red side; the battery rows
  are the green pins).
- **Battery:** `test_escaped_metachar_axis` (bs_* rows, measured bash
  bytes both-sides-pinned; incl. controls). Two of my hand-written control
  expectations were WRONG (bs_ctl3, bs_rem) — bash's measured values
  differ; corrected to measured with comments (the measured-not-assumed
  discipline applied to myself, recorded).

### D-2 — B2-2: errata + Path A (measured, proven, landed)

- **ERRATA ROW (replacing ledger C-4's mitigation sentence, as R10
  directs):** the sentence "(R7, attributed): tip still beats live bash on
  the idiom (bash itself is cubic there)" is WITHDRAWN. Shape-scoped
  measurements of `r=${v//+([[:space:]])/-}` (this machine; bash =
  end-to-end `TIMEFORMAT=%R`; psh = in-process op timing):

  | shape | N | bash | psh base | psh round-2 tip | psh tip+Path A |
  |---|---|---|---|---|---|
  | consecutive spaces | 400 | 0.000s | ~0.002s* | 0.550s | ~0.002s* |
  | consecutive spaces | 1600 | 0.001s | 0.004s | 3.105s | 0.004s |
  | consecutive spaces | 3200 | 0.001s | 0.008s | 12.811s | 0.007s |
  | word-spaced (`x `×) | 400 | 0.547s | 0.002s | 0.278s | 0.002s |
  | word-spaced | 1600 | 34.169s | 0.007s | 4.372s | 0.007s |
  | word-spaced | 3200 | 285.356s | 0.014s | 17.466s | 0.013s |

  (*first-call rows carry ~0.35-0.55s interpreter warmup; steady-state
  shown elsewhere.) bash is FLAT on consecutive runs and worse-than-cubic
  on word-spaced; round-2 psh was quadratic on BOTH; base was linear on
  both; Path A restores base linearity on both. The false generalization
  ("the idiom") was the INTEGRATOR'S (R10: fault tallied, 3.1 fault #1,
  R21-C class — subject SHAPE is an axis); I carried it attributed, and
  this row notes the fault is theirs per their direction.
- **Path A:** `pattern_engine.sub_fast_eligible` (AST-derived: every group
  at any depth non-negation AND non-nullable; `_seq_nullable` helper;
  lazily cached `Sequence.sub_fast`) × wrapper-REDUNDANCY (raw-char, in
  the machinery: NOT the odd-escaped-`\*`-tail outer-guard shape, NOT the
  `(`-head pun shape) = `fast_ok`, the dispatch gate. Eligible ops run the
  linear direct scans (`_substitute_first_fast`/`_substitute_all_fast` +
  inline fast branches for `/#`,`/%`).
- **The AST-only gate was WRONG for one turn and MY OWN battery caught
  it:** the new bs_fix rows failed under the first fast path (the
  suppressor shapes are group-free, hence AST-eligible; corpus5-v1 could
  not see it — no backslashes in the union). fast_ok added; rows green.
- **EQUIVALENCE PROOF** (`tmp/slot31/corpus5_equiv.py`): union of
  corpus1/2/3 cells + the backslash axis = 428,144 distinct cells; 2,799
  of 14,517 patterns fast_ok-eligible → **85,459 eligible cells × 4
  operators = 341,836 comparisons, 0 disagreements** — with REAL forcing
  (see D-3b). Battery: `test_fast_path_eligibility_boundary` (predicate
  pins incl. fast_ok raw-char rows + deterministic two-path sample).
- **3.2 handoff row (final form):** restore linear substitution scanning
  under the bash-mechanics semantics for the INELIGIBLE class (the
  eligible/common class is linear again in-slot); baselines = the table
  above + A9's matching_starts quadratic. The MEDIUM-6 freeze must cover:
  `compile_cached` (lru 4096), `_sub_machinery_cached` (lru 512, now
  4-tuple), the lazy `Sequence` bits (`has_extglob`/`bash_quirk`/
  `sub_fast`), and the `Extglob.enclosed` contract (N8 invariant test
  `test_extglob_enclosed_compile_invariant` pins the compiler as the
  reference).

### D-3 — Two in-phase incidents (self-caught; instruments hardened)

- **(a) checkout-slip #2:** verifying M6 manually, I reverted
  `parameter_expansion.py` with `git checkout` over uncommitted Phase D
  work — the SAME class as C-3's lesson, this time by hand. One file;
  caught instantly (the Phase C restore script's idempotence asserts
  refused to run against the mixed state). Rebuilt via the session's
  proven edit contents; the byte-exact instrument is now a git patch:
  `tmp/slot31/phase_d_parameter_expansion.patch` (apply with `git apply`
  from b49b8e9c; replaces the fragile text-substitution restore script).
  LESSON REINFORCED: no `git checkout` ANYWHERE in mutation/verify loops —
  hands included; cp/patch only.
- **(b) the forcing void:** the FIRST extended equivalence run compared
  fast-vs-fast — the machinery pass patched `px.sub_fast_eligible` but the
  lru-cached machinery tuples still carried `fast_ok=True` from the real
  predicate, so BOTH passes dispatched fast. Discovered because the M6
  mutation did NOT fail the boundary test (a mutation-proof catching a
  broken PROVER — the discipline working as designed). Fixed: both provers
  clear `_sub_machinery_cached` around the patch; proof re-run (the
  341,836/0 above is the VALID run); M6 added as a permanent replay class
  and verified to fail for its own reason
  (`('*', 'a', 'substitute_all', 'ZZ', 'Z')`). LESSON: when forcing a
  dispatch arm for an A/B proof, clear every memo between arms — a cached
  decider launders arm A into arm B; and keep one mutation class pointed
  at the PROVER itself.

### D-4 — NIT-9: deleted-decider census (`_neg` vs `end_eligible` vs bash)

Quadrants of the two deciders' input space, measured cells:

| quadrant | `_neg` (contains `!()` anywhere) | head-shape gate | bash (measured) |
|---|---|---|---|
| `!`-containing, `*`-headed (`*!(a)` on `''`, all four anchors) | suppress | eligible | SUBSTITUTES (emptysub_star all-Z) → head-shape |
| `!`-containing, non-`*`-headed (`!(x)` on `''`) | suppress | gate off | suppresses (agree; undiscriminating) |
| `!`-free, `*`-headed (`*(q)`/`*` on `''`) | emit | eligible | emits (agree; undiscriminating) |
| `!`-free, non-`*`-headed (`?(x)`/`@(|a)` on `''`) | emit | gate off | SUPPRESSES (q4/emptysub_q/emptysub_at) → head-shape |

On every discriminating cell bash sides with the HEAD-SHAPE decider;
`_neg`'s negation axis was a proxy that coincided on two quadrants only.
The replacement decider is bash's own (match_pattern_char), raw-char form.

### D-5 — R10 nit discharges

- N1 B2b relabelled CONTROL (battery comment + docstring). N2/N6/N14
  matching_spans sweep COMPLETE (module docstring four-relations sentence,
  CLAUDE.md Key-Files row; grep for unlabelled mentions clean). N3
  `_seq_bash_quirk` docstring scoped (no bare counts; scope statement
  added). N7 file renamed `test_substitution_scan_unified.py` →
  `test_substitution_empty_match_pins.py` (+ function renamed);
  COLLECTED-PROOF: 20 collected before, 20 after under the new path, old
  path absent. N8 `test_extglob_enclosed_compile_invariant` added +
  3.2-handoff naming (D-2). N10 (ledger row): the verifier's independent
  re-verification of "H7 rows unpinned at base" — their grep over the base
  tree, attributed to round-2 diffAudit — is adopted into the record
  alongside my A-phase fixed-string grep. N11 (ledger row): the Linux
  reasoning, now WRITTEN: the corpora use portable {a,b}/{a,c} alphabets
  (no locale-collation surface); extglob.py changes are docstring-only;
  the battery's bash-side rows are agreement-form or both-sides-pinned
  with oracle-drift arms (a Linux bash behaving differently fails as
  oracle drift, loudly); the UTF-8/locale rows of the ROWS battery are
  untouched; no signal/fd/path behavior is involved — nightly risk is
  bounded to oracle-version drift, which the drift arms surface. N12: the
  formal totals ride the next tip declaration. N4/N13/N15 noted (no
  action); N5 integrator's at ceremony.

### D-6 — Phase D pre-commit verification

- corpus4 **0/2,016**; equivalence **0/341,836** (valid forcing); battery
  **18 passed ~6s**; expansion suite **2,774 passed / 17 skipped**; ruff +
  mypy clean (275 files); replay: SIX mutation classes, each its own
  reason, cp-backups, state preserved; perf tables in D-2.

### D-7 — Commits landed (declared, msg cea2275f) + one packaging deviation

- `a55651e0` round-3 fix commit (+378/−60) — CONTAINS THE N7 RENAME: the
  earlier `git mv` was already staged, so `git add <4 files>` + commit
  swept the rename in. `43df27ac` then carries only the in-file function
  rename (+1/−1). ALL content was declared before landing; the DEVIATION
  is packaging only (the rename was declared as commit 10). Disclosed to
  the integrator in the tip declaration; no history rewrite attempted.

### D-2a — Perf-table measurement basis (R11 note 4, explicit)

All psh columns in the D-2 table are IN-PROCESS operation timings (one
persistent Shell per tree; `time.perf_counter()` around
`sh.run_command('r=${v//+([[:space:]])/-}')`; no interpreter startup) —
mutually comparable across base/round-2-tip/tip+PathA. The bash column is
END-TO-END (`bash --norc -c` with `TIMEFORMAT=%R`), which INCLUDES ~3-5 ms
of bash startup — negligible at the magnitudes shown (its flat rows are
0.000-0.001s TOTAL, so bash's matcher cost is bounded above by those
values; the comparison direction is unaffected). psh tip+PathA beating
base absolutes is real but within-noise equality: both are the same
linear scan (the fast path IS the base algorithm behind the fast_ok
gate); differences of ±1 ms are run-to-run jitter. First-call rows
(~0.35-0.55s) include lazy-import warmup and are marked in D-2. Round 3
re-measures on its own basis.

### D-8 — FINAL (round 3 candidate): sequence GREEN pre-stall; tip DECLARED 43df27ac; N12 FORMAL TOTALS

- **Stall + resume record:** the session hit its usage limit AFTER the
  sequence completed and DURING this ledger write (the D-8 append errored;
  nothing else was in flight). State-check-first resume (R12): tip
  43df27ac (committed 03:56:48+01:00), tree clean, pgrep clear;
  `tmp/gate-4.txt` (mtime 04:05) and `tmp/compare-bash-3.txt` (04:06)
  post-date the tip commit at the clean tree — the artifacts ARE this
  tip's sequence. No re-run performed (duplicate of a green sequence);
  offered to the integrator on request.
- Precondition was recorded pre-run: `pgrep -f pytest` → CLEAR.
- **Gate** (`tmp/gate-4.txt`, tree 43df27ac): **22,838 passed / 1,590
  skipped / 10 xfailed — ALL PHASES PASSED.** Delta +3 vs round-2's
  22,835, DERIVED: the three new battery tests (escaped-metachar axis,
  fast-path boundary, enclosed invariant); chain: base 22,820 +12 (r1)
  +3 (r2) +3 (r3) = 22,838 ✓ exact. **compare-bash**
  (`tmp/compare-bash-3.txt`): **2,986 / 26 — EXACT** (no behavioral rows
  in any round).
- **FINAL TIP DECLARED: `43df27ac`** (10 commits over 29456fdc: 1c9bf6cc,
  4a1d412c, 3e636607, fb2f1a33, af236478, 7bec085c, 8713f7e0, b49b8e9c,
  a55651e0, 43df27ac). Mechanical tip rule in force.
- **R11 notes discharged:** (1) the pun + raw-char rules are TAUGHT in
  `_sub_machinery_cached`'s docstring (the measured rule, incl. the pun
  cell and the 45-cell family) with the method docstring pointing there;
  the corpus4 7th cell + my two corrected-to-measured control
  expectations remain visible in D-1. (2) M6 is a permanent replay class;
  the forcing is real (cache-clear in both provers; M6 verified to fire:
  `('*', 'a', 'substitute_all', 'ZZ', 'Z')`). (3) checkout posture
  BINDING acknowledged — cp/patch instruments only, hands included; third
  slip = stop-and-talk. (4) D-2a above. (5) this declaration.
- **N12 FORMAL DISCHARGE-AUDIT TOTALS:** phase records A1-A10, B1-B8
  (cert rows C1-C12), C-0..C-10, D-0..D-8 — every claim row
  instrument-anchored (tmp/slot31 instruments + git-show'able commits);
  every count DERIVED by its producing script: corpora 51,795 + 13,830 +
  372,186 (evidence TSVs), 2,016 (backslash axis), battery grammar-v2
  436,761, TSV union 437,811, equivalence union 428,144 distinct cells /
  85,459 eligible / 341,836 comparisons / 0 disagreements; battery 18
  tests ~6s; SIX mutation classes each failing for its own reason
  (cp/patch-backed one-command replay `sh tmp/slot31/replay_mutations.sh`).
- **N12 BOUNCED-ROWS REPLAY TOTALS:** Round-1 (3 blockers, 14 nits):
  B-1/B-2 fixed by the star-jump port, re-verified at THIS tip by the
  battery anchors (B1/B2/B2b) + the grammar-v2 corpus; B-3 re-opened by
  R10 → discharged via Path A (0-disagreement proof + perf tables);
  round-1 nits: 8 fixed-in-slot (verified clean by round-2 verifiers), 3
  ledger rows, 2 noted, N6 ceremony. Round-2 (2 blockers, 15 nits):
  B2-1 replayed at this tip — corpus4 0/2,016 + bs_* battery rows green
  (was 7 divergent); B2-2 replayed — shape-scoped perf at four trees +
  the valid-forcing proof + boundary test; round-2 nits: 6 fixed-in-slot
  (N1, N2/N6/N14, N3, N7, N8), 3 ledger rows (N10, N11, N12=this), 3
  noted (N4, N13, N15), N5 ceremony. Faults on record: integrator 1
  (R10 B2-2, theirs, errata in D-2); mine 4 (R4-C slip C-10, checkout
  slips C-3/D-3a, forcing void D-3b) — all self-caught, all with
  hardened instruments.

## Hold state (verification round 3)

- R11 (commits approved, five binding notes) + R12 (stall-resume point)
  received and ACKed. Resume was STATE-CHECK-FIRST: the sequence had
  completed pre-stall (artifact mtimes post-date the tip commit at a
  clean tree); only the D-8 ledger write was interrupted — completed on
  resume, no re-run of the green sequence (offered on request).
- ROUND-3 TIP DECLARED 43df27ac with the N12 formal totals (msg
  32dd5bef). HOLD: tree clean, no runs in flight, mechanical tip rule +
  BINDING checkout posture in force (cp/patch instruments only; a third
  checkout slip = stop-and-talk). Wait-time observations go here.

- R13 flagged: the channel message citing "R13" (provenance accepted;
  round 3 RUNNING against 43df27ac; hold; clean → straight to ceremony)
  has NO matching inbox section (latest on file = R12). Flagged per
  protocol (msg 3202db0f) without inferring unseen content; acting on the
  channel text as written. HOLD re-verified: tip 43df27ac, tree clean, no
  runs in flight.

- R13 now LANDED in the inbox (content identical to the channel text +
  the integrator's own note recording the cite-without-landing slip as
  theirs — INTEGRATOR PROCEDURAL NOTE #2 for the fault register; same
  drift class the dead-drop exists to prevent; my flag posture confirmed
  correct). Fault register update: integrator entries now 2 (R10 B2-2
  false generalization; R13 channel-cite-without-inbox-landing). HOLD
  unchanged at 43df27ac. R13 ACK rides my next send (the verdict
  response).

## Phase E (R14: round-3 PASS, 0 blockers, 14 nits) — final cleanup

### E-1 — Ledger errata/additions (R14, no commit)

- **A4 erratum ("55-cell e2e sample"):** the sample size is STATE-
  DEPENDENT — `corpus1.py` samples `rows[::1300] + div[:15]`, i.e. 40
  stride cells + min(15, |divergent|): at BASE (750 divergent) it printed
  55; re-run at a fixed tree (0 divergent) it prints 40. The count is
  DERIVED by the script per run; A4's "55" was the base-run value.
- **Union wording erratum:** "437,811" is the ROW SUM of the three
  evidence TSVs (corpus1 51,795 + corpus2 13,830 + corpus3 372,186,
  duplicates counted per file); the DISTINCT (pattern, subject) union is
  **427,586**; +558 distinct backslash-axis cells = **428,144** (the
  equivalence-proof universe) — reconciles exactly.
- **A9/matching_starts wording:** the per-start-position evaluation SHAPE
  is preserved from base; the slot's routing hunk (8713f7e0) is required
  for suffix-removal consumers and was verified in rounds 1-2. The
  quadratic remains 3.2's.
- **3.2 handoff additions (attributed to the round-3 verifier):**
  FULL_MATCH on flagged patterns is a 3.2 OPENER PRIORITY — `**(a)b` on
  'a'*N: base ~×4/doubling vs tip ~×8/doubling, ~85× base at N=400
  (script-visible); matching_ends `*!(a)`: ~17× base at N=200. These join
  the D-2 substitution table and A9's matching_starts baseline as the
  named 3.2 perf-restoration inputs.
- **R14 confirmations on record:** (a) consumer layer + lru(512) +
  fast_ok = deliberate, ruled (R2/R7-7/R10/R8/R11), ceremony LEDGER row
  states it; (b) `_BashMatcher` is a per-pattern-class evaluator inside
  the ONE engine (R1's accepted A10; the "no second matcher" prohibition
  targets per-consumer forks); 3.2 notes the evaluators as unification
  candidates. golden_cases.yaml:10218 comment fix is the INTEGRATOR'S at
  ceremony.

### E-2 — Commit 11 contents (verifier-anchored; measured where pinned)

- guide-17 ¶71 scoped to globbing/case (agrees with the ¶59-62 claim the
  verifier confirmed with 90 cells). extglob.py `_neg` reference marked
  RETIRED-and-deleted. Battery hygiene: recursion-limit snapshot/restore
  around the boundary test's Shell() (kills the invisible order coupling
  with the recursion-contract test); B1 relabelled THREE-POINT
  (base-green / 7bec085c-red / tip-green), subc_jump THREE-POINT,
  case_jump red-on-base, case_jump2 CONTROL; regex-oracle docstring
  carries the DERIVED narrowing chain — re-derived myself before pinning:
  6,000 → 1,687 negation-excluded → 689 extglob-free → 267 flag-excluded
  → 3,357 kept (matches R14's numbers exactly). NEW residual row
  `opx_slash` (operand-extent family, PRE-EXISTING, round-3 find,
  3/3,888 verifier cells): `v=""; "${v/*!(/)/Z}"` → bash `[)/Z]` / psh
  `[]` — MEASURED this turn, pinned divergent-direction (FLIP-PINS
  successor entry is the integrator's at ceremony). Instrument cleanups
  (no commit): replay header M1-M6; corpus5_equiv dead assignment
  dropped.

### E-3 — CEREMONY TIP: cced9aca; final sequence GREEN

- Commit 11 landed as declared (msg 8d062f55): `cced9aca` (+37/−8,
  4 files). Precondition recorded: `pgrep -f pytest` → CLEAR.
- **Gate** (`tmp/gate-5.txt`, tree cced9aca): **22,838 passed / 1,590
  skipped / 10 xfailed — ALL PHASES PASSED** — exactly as derived (no
  collection delta: labels/docstrings/one residual data row only).
  Chain: base 22,820 +12 (r1) +3 (r2) +3 (r3) +0 (cleanup) = 22,838 ✓.
- **compare-bash** (`tmp/compare-bash-4.txt`): **2,986 / 26 — EXACT**
  (no behavioral rows in any round).
- **CEREMONY TIP DECLARED: `cced9aca`** (11 commits over 29456fdc:
  1c9bf6cc, 4a1d412c, 3e636607, fb2f1a33, af236478, 7bec085c, 8713f7e0,
  b49b8e9c, a55651e0, 43df27ac, cced9aca). Mechanical tip rule remains
  in force until ceremony completes. N12 totals of D-8 carry forward
  unchanged except: battery now 18 tests + the opx_slash residual row
  (residual structure = lexer-seam ×3 + operand-extent ×1, each
  divergent-direction with measured bytes); fault register final:
  integrator 2 procedural notes + 1 tallied fault; mine 4, all
  self-caught. Slot handed to the integrator for ceremony (evidence
  rescue, v0.763.0, doc metadata, FLIP-PINS + LEDGER closures incl.
  renames, nightly-status, attestation, PR, merge, tag, smoke).

## Hold state (ceremony)

- CEREMONY TIP cced9aca declared (msg 9bfdd693); slot handed to the
  integrator. HOLD: tree clean, no runs in flight; mechanical tip rule +
  binding cp/patch posture in force until ceremony completes. Dev work on
  slot 3.1 is COMPLETE pending ceremony outcome.

- R15 received (landed in inbox, read, ACKed) — crossed with my ceremony
  declaration (9bfdd693). Everything R15 directs was already done:
  cced9aca landed, sequence green (gate-5 22,838/1,590/10;
  compare-bash-4 2,986/26 EXACT), ceremony tip declared. Crossing
  resolved per the established posture (msg bef6ac5b); no re-run. HOLD
  unchanged at cced9aca awaiting ceremony.
