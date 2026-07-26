# Boundary Remediation Campaign — Unified Ledger

- **Created:** 2026-07-24 (Wave 0 launch). Maintained by the campaign integrator.
- **Launch base:** `0215279c` (v0.750.0).
- **This is THE registry** (integrator plan amendment A2): it merges reappraisal
  #22's findings with the predecessor campaign's 35-row carry register. A row
  leaves this ledger only as CLOSED (probe + flipped/added pin + guard),
  DE-SCOPED (ruled out in writing before implementation), or RE-CARRIED
  (explicit reason + successor owner). "Partial" is not a terminal state.
- Base results reference the integrator's verification of 2026-07-21 (every #22
  HIGH/MEDIUM discriminator reproduced at `0215279c`; probe scripts in
  `wave0-base-probes/`) and the Wave 0 baseline legs (`wave0-legs/` summaries).

## Part A — Reappraisal #22 findings

Status codes: OPEN (awaiting its wave), CLOSED, DE-SCOPED.
All rows OPEN at Wave 0 close unless marked otherwise.

| Finding | Wave/slot | Base result (2026-07-21 verification) | Intended closure evidence |
|---|---|---|---|
| HIGH-1 oracle false-green + bypass | 1.1 + 1.2 | CONFIRMED: `yes` → both rc −9, 8 MB truncated, verdict IDENTICAL; ~30 direct-subprocess differential modules | **CLOSED** v0.751.0 (typed outcomes; `is_comparable` sole authority; forgery-proof frozen+slots) + v0.752.0 (92-module runner migration; AST guard w/ site budgets + PTY registry + offenders; committed replayable audits). Evidence: `1.1-rescue/`, `1.2-rescue/`, `tests/harness/oracle_migration_census.md` |
| HIGH-2 traversal misses executable syntax | 2.1 | CONFIRMED: 4/4 probes report "No security issues found!" (redirect-only, redirect target, for/case subjects) | **CLOSED v0.756.0**: `TotalTraversalVisitor` — framework-owned total child enumeration (mechanical from AST schema, one authority, exactly-once per node incl. the S3 template-carrier fields the old S5 exception never descended into); all 5 analysis visitors migrated; generated sentinel-child battery (node×edge×visitor) + anti-bypass guard proven vs synthetic offenders; the 4 probes flip to reporting findings, promoted to committed tests. Security gains a no-false-clean-claim policy (UNANALYZED_REGION for backtick/heredoc/flat-`[[`-operand executable regions, keyed to psh execution). 4 verification rounds (double-visit exponential regression, backtick coverage loss, prefixed-assignment double-read, B11 scanner contract — each a seam the new reach exposed, zero framework regressions); executable 99-cell reference-coverage suite pins base⊆tip. Evidence: `2.1-rescue/`. |
| HIGH-3 resolution before prefix side effects | 3.4 | CONFIRMED: bash BUILTIN / psh FN, both `$((POSIXLY_CORRECT=1))` and `${POSIXLY_CORRECT:=1}` | A8 ordering matrix green vs bash; single-resolution guard |
| HIGH-4 subscript procsub identity/timing | 2.3 | CONFIRMED: psh keys `/dev/fd/…` for `a[<(printf x)]=v`; `a[<(if)]` runs where bash rejects the unit | literal-key + read-time-rejection parity pins; raw re-lex deleted |
| HIGH-5 combinator drops ParseInputs | 2.2 | CONFIRMED: nested `@(a\|b)` in `$()` rejected by combinator only; facade wrapper discards source/options | one `parse(tokens, inputs)` entry; lockstep corpus + location parity |
| HIGH-6 operand `$@` flatten | 3.3 | CONFIRMED: `<a b>` vs bash `<a><b>` | flip `test_divergence_operand_at_flattens` (4 params) to equality; operator/quoting matrix vs bash |
| HIGH-7 pattern negation/nullable + quadratic | 3.1 (semantics), 3.2 (perf/immutability) | CONFIRMED: 3/3 `[[` rows diverge; `matching_starts` 4×/doubling (1.45 s @ N=8000) | finite-alphabet differential battery; linear transition counts; frozen cache |
| HIGH-8 lease rollback incomplete | 4A.1 | CONFIRMED by fault injection + AMPLIFIED: orphan lease poisons later unrelated shells (spurious competing-owner LeaseError); `release_owner` never sweeps | fault battery incl. multi-shell poisoning + transfer-rollback scenarios |
| HIGH-9 substitution-origin fact unconsumed | 2.4 | CONFIRMED: rc 2 vs 127; `AFTER` runs after `eval 'echo $(if)'` | flip the 6-way `test_divergence_c_mode_exit_code_is_127_in_bash`; frame-abort timing pins |
| HIGH-10 closure artifact defects | 0, 1, C | CONFIRMED (all seven particulars at v0.750.0) | Wave 0: A4 corrections + governing docs committed + evidence tree (this commit); Wave 1: durable oracle evidence; C: self-contained close |
| MEDIUM-1 EXIT-trap bypasses shutdown work | 4A.2 | CONFIRMED structurally: trap SystemExit skips job disposition (only history-save skip documented) | PTY probes: HUP/reap/history under `trap 'exit 7' EXIT` |
| MEDIUM-2 UTF-8 decoder seam | 4B.2 | CONFIRMED end-to-end: split é → two surrogates (FIFO + `read -t` timeout repro) | every 2/3/4-byte split pinned; char identity + byte round-trip |
| MEDIUM-3 escaped `\<<` heredoc misdetect | 2.5 | CONFIRMED — INTERACTIVE-ONLY (latent in `-c`: flush re-lexes correctly); psh drops to PS2, swallows next line | PTY pin (A5: `-c` pin would be green-on-base); lexer/session equivalence property tests |
| MEDIUM-4 raw bracket extent / locations | 2.3 | CONFIRMED: `a["]"]=ok` rejected by both psh parsers; bash prints ok | quote-aware extent scanner; absolute SourceSpan pins |
| MEDIUM-5 mutable VariableLookup/_MISSING | 4B.1 | CONFIRMED both parts: readonly bypass via `.binding.value`; `_MISSING` poisoning | frozen lookup + immutable view; mutation-attempt pins |
| MEDIUM-6 mutable pattern cache | 3.2 | CONFIRMED: cache poisoning makes `'a'` match `'b'`, incl. through live `case` | frozen node graph; poisoning attempt fails |
| MEDIUM-7 history cursor conflation | 4B.3 | CONFIRMED: `-d` decrements `_file_read_len` → `-n` duplicates C; `-s` bypasses HISTSIZE | `-r/-n/-d/-s/-a/-w` state-machine vs bash (closes carry #32 too) |
| MEDIUM-8 signal dispositions outlive close | 4A.1 | CONFIRMED (audit code refs verified in HIGH-8 injection work) | handlers under component leases; restore-exact-prior pins |
| MEDIUM-9 analysis under initial options | 2.6 | CONFIRMED: extglob script executes but fails `--validate` | state-aware analysis session; mode-composition ruling |
| MEDIUM-10 shallowly-valid heredoc/lexed values | 2.5 | CONFIRMED: `heredoc_content: Optional` with documented-representable invalid state; RD `:156` constructs None | non-optional executable body type; frozen token parts |
| MEDIUM-11 parser lifecycle vs docs | 2.2 | CONFIRMED: second `.parse()` returns empty program | enforced single-use or reusable grammar; contract test |
| MEDIUM-12 broad exception nets | 2.3 (subscript), 3.5 (expansion/arith), 5C (rest) | CONFIRMED: `except Exception` at subscript.py:129,144 (v0.750.0) | typed user-error variants; Q2 masker ledger shrinks |
| MEDIUM-13 race-dependent background test | 1.3 | CONFIRMED structurally (pass-without-assertion path; also 1 flake in #22's fresh run) | **CLOSED** v0.753.0: subprocess route + job-API `wait` + unconditional asserts (existence, exact bash bytes, clean stdout); vacuity replayed at base; 2 discriminating mutations; 50 seq + 25 shuffled green; state-guarded-assert census 1 → 0 tree-wide. Evidence: `1.3-rescue/` |
| MEDIUM-14 protocol boundaries incomplete | 5B | CONFIRMED: 2 migrated, 3 defined-unused; both name collisions live | per Checkpoint R re-scope |
| MEDIUM-15 complexity/hubs; O(k²) session | 5C (hubs); 5A DE-SCOPED (see ruling R1) | CONFIRMED: 54 fns ≥100 lines (exact) | hub decomposition per named transactions |
| MEDIUM-16 incomplete boundary signatures | 5C | CONFIRMED magnitude (510–623 by methodology) | boundary seams annotated first, then per-package |
| LOW printf `%a/%A` precision + `#` flag | Wave 5 rider (declared here per sequence §13) | CONFIRMED: `%.2a` full-precision vs bash `0x1.92p+1` | float-format conformance rows |
| LOW STD_FDS lease retained on failed exec | 4A.1 | CONFIRMED by injection (+ same poisoning consequence) | rollback releases lease; injection pin |
| LOW skip-on-failure tests | 1.3 | CONFIRMED verbatim in both cited files | **CLOSED** v0.753.0: both named sites + census (14 true instances fixed incl. a 100%-dead NameError-swallowing test; 13 env gates + 1 corpus filter stay, per-hit table); 9 silent-skip oracle modules loud (base: exit-0 w/ 191 differentials skipped); mutation-proven conversions. Evidence: `1.3-rescue/` |
| LOW deferred-import/Q2 debt ledgers | 5B/5C | CONFIRMED (ratchets are inventories, not closures) | caps materially shrink |

## Part B — Predecessor carry register (35 rows): dispositions

| # | Carry | Wave 0 disposition |
|---|---|---|
| 1 | Q2 retained oracles | Already CLOSED (Q3). No action. |
| 2 | F9 git-range self-check | Already CLOSED (Q3). No action. |
| 3 | empty-arith-subscript | Register wording CORRECTED at Wave 0 (A4). Divergence itself RE-CARRIED (deliberate, both-sides-pinned, psh-cleaner ruling stands); slot 2.3 MAY revisit if subscript rework makes parity cheap — revisit is optional, not owed. |
| 4 | operand-`$@` flatten | CLOSE via slot 3.3 (= HIGH-6). Flip-pin obligation recorded. |
| 5 | F6.6 definition-rejection | RE-CARRIED (orthogonal to #22; successor queue). |
| 6 | exec-builtin message wording | RE-CARRIED (cosmetic wording). |
| 7 | RANDOM-in-prefix | ATTACHED to slot 3.4's A8 ordering matrix as a mandatory probe row; close there if the transactional prefix expansion resolves it, else explicit re-carry with the matrix evidence. |
| 8 | timeformat `%P` flake | **CLOSED** v0.753.0 (root-caused: shape helper pinned %P digit WIDTH vs a 10 ms accounting tick; base 4/60 → tip 0/60+0/25). The %P VALUE defect is a separate Part D row below. |
| 9 | plain-expansion echo stream | RE-CARRIED (orthogonal). |
| 10 | history `-p` failed-arg wording | RE-CARRIED (message wording only, both rc 1). |
| 11 | trailing-redirect-at-EOF | RE-CARRIED; slot 2.5 optional revisit. |
| 12 | general async reaper (H19 residual) | RE-CARRIED to successor (with #16); NOT owed by 4A (which owes EXIT-trap/lease paths only). |
| 13 | stopped-fg-subshell not recorded | RE-CARRIED. |
| 14 | procsub-`$!`-wait | RE-CARRIED. |
| 15 | tcsetattr-drain probe note | NOTE only (probe construction), remains recorded. |
| 16 | RESUMABLE-PARSER (H15) | RE-CARRIED as SUCCESSOR CAMPAIGN per ruling R1 (5A OUT). |
| 17 | J1 Linux-nightly watch (MUST) | **RECLASSIFIED — CANNOT be discharged as green: the nightly has been RED since 2026-07-02** (23 consecutive failures; last green `b314064c` 2026-07-01, first red `a0e99959` 2026-07-02). Latest census (2026-07-24, at `0215279c`): full-suite job 24 failed / 21,746 passed (16 parallel + 8 serial) incl. the J1-family signal/trap/procsub-reap/pipeline-death tests #17 was watching, plus history-outcome[6], locale-provenance, protocol-freeze, PTY tab-completion; conformance job 54 failed / 2,600 passed dominated by syntax-template `-file`-channel arith rows (oracle = Linux bash 5.2.21 vs local 5.2.26). Multiple accretion layers (several failing tests postdate 2026-07-02). Full record: `nightly-status.md`. **CLOSED v0.755.0 (slot 1.4): nightly GREEN — first since 2026-07-02, three consecutive green dispatch runs (30171120171, 30172534890, 30175067149 @ cdff0704); conformance 54→0 (2,671 passed), parallel 26→0 (21,873 passed). Census: 30 rows classified (i)=46-conformance+PTY-xfail-family /(ii)=13 /(iii)=1 /(iv)=13 /(v)=2 — every J1-family row root-caused, none quarantined. The J1 watch's real defects: `bg` stale-state SIGCONT gap (fg-mirror refresh, deterministic red-on-base pin) + locale reactive over-warn (LC_ALL reset path silenced per bash's per-trigger rule, both-direction mutation pins) + the harness cap/timeout kill missing escaped process groups — a runaway `yes` filling unlinked capture files at ~480MB/s that killed BOTH the Linux nightly ([Errno 28]) and this macOS host's gates (the months-old "external consumer"). Descendants-first sweep, gated to live-leader kills, synthetic escaped-offender pin. Evidence: `1.4-rescue/` (slot ledger 1,226 lines + integrator inbox + probes). Standing rule: first SCHEDULED nightly post-merge must be verified green (wave-close checklist).** |
| 18 | posix special-builtin redirect fatality | RE-CARRIED (both-sides-pinned). |
| 19 | `$'\xNN'` byte model | RE-CARRIED (pinned). |
| 20 | key_decoder replace-decode | REMAINS sanctioned terminal-UI non-goal. |
| 21 | `read -N` mixed valid+malformed hybrid | ATTACHED to slot 4B.2: the decoder-seam fix touches this code — 4B.2 must re-rule (close or re-carry) with fresh probes; silent behavior change forbidden. |
| 22 | S3→I3 substitution-origin not consumed | CLOSE via slot 2.4 (= HIGH-9). Flip-pin obligation recorded. |
| 23 | nested-quote arith carriers | RE-CARRIED (B1 model limit; #31 contract-reshape family). |
| 24 | two-tier introspection + 126 wording | RE-CARRIED (resolver candidate-model flag; not in #22 scope). |
| 25 | `history -ps` clustered flag | ATTACHED to slot 4B.3 as a rider (trivial option-scan fix while history builtin is open). |
| 26 | cmdsub-with-`;` in arith subscript | NOTE only (no divergence). |
| 27 | sticky-hash of non-exec lose-on | RE-CARRIED (deliberate, risk-ruled, pinned). |
| 28 | nested-subscript assignment extractor | ATTACHED to slot 2.3: the subscript/extent rework covers this shape — close or re-carry with evidence. |
| 29 | heredoc history trailing newline | RE-CARRIED (cosmetic). |
| 30 | executable special-file earlier (FIFO/SOCKET) | REMAINS sanctioned DESIRABLE deviation (do not "fix" back). |
| 31 | `[[` operand arith provenance (+ composed read/write) | RE-CARRIED to successor campaign (whole-contract reshape, with #16). |
| 32 | `history -a/-c/-n` counter model | CLOSE via slot 4B.3 (same counter family as MEDIUM-7). |
| 33 | CRLF in piped `-i` | RE-CARRIED; slot 4B.2 optional revisit (input-layer adjacency). |
| 34 | PROMPT_COMMAND piped `-i` only | REMAINS recorded piped-harness artifact (PTY-proved working). |
| 35 | eval'd outer-single `history -p "!!"` | RE-CARRIED (expansion-engine reconstruction; pinned). |

## Part C — Wave 0 rulings

**R1 (5A / H15, plan A7):** Package 5A (resumable lexer/parser transaction) is
**OUT of this campaign's closure scope**, recorded as the successor
RESUMABLE-PARSER CAMPAIGN together with carries #16, #31, #12, and the other
Part B re-carries. Reason: campaign-scale by prior ruling (I3 Option B); under
sequence success criteria 1+6 a late deferral would make this campaign
permanently unclosable. Wave 5 here = 5B + 5C (+ Checkpoint R amendments).
MEDIUM-15's O(k²) `ParseSession` element follows 5A out; its hub-decomposition
element stays (5C).

**R2 (InputCursor gaps, plan 4B.4):** cross-fd dup sharing and
temporary-redirect isolation are **DE-SCOPED from closure** — slot 4B.4 becomes
a contract-narrowing documentation task (explicit contract statement + user-
guide difference note + ledger row), executed BEFORE 4B implementation begins,
satisfying the sequence doc's "narrow the contract explicitly before work
begins" branch. Both re-carry to the successor queue.

**R3 (nightly, plan amendment AM-1):** Wave 1 gains slot **1.4 — Linux nightly
recovery** (see `nightly-status.md`). Rationale: the nightly is the Linux
observation channel; Wave 1's charter is evidence trust, and a 23-day-red
backstop is an evidence-trust failure exactly like HIGH-1 (nobody looked at
run RESULTS — the repo's own CI-green lesson). Exit for 1.4: nightly green on
Linux, or every red row explicitly classified (Linux-genuine → fixed or
wave-assigned; oracle-version → handled by the Wave 1 oracle policy;
env/infra → fixed) with the run link recorded. Carry #17's J1 rows are
discharged INSIDE 1.4.

**R4 (LOW printf):** declared a Wave 5 rider now (satisfying sequence §13's
"declared at Wave 0"), not a follow-on: it is user-visible float formatting
with a one-file blast radius.

## Part D — New facts registered at Wave 0

| Item | Detail | Owner |
|---|---|---|
| Nightly red 23 days | See carry #17 row + `nightly-status.md` — **CLOSED v0.755.0 (slot 1.4)**: green since 2026-07-25, 3 consecutive dispatch runs; first-SCHEDULED-green check owed at Wave 1 exit | 1.4 ✅ |
| `read -t X -N n` hangs | `-N` path passes no deadline to `read_limited` (found 2026-07-21, verified end-to-end) | 4B.2 rider |
| Lease-poisoning amplification | Orphaned component lease breaks LATER shells' activation; `release_owner` early-return never sweeps | 4A.1 (exit criteria include it) |
| gh account-switch hazard | Active gh account found switched to a READ-only account 2026-07-24; ceremony pre-flight now includes `gh auth status` | ceremony checklist |
| **psh EXIT-trap output MISDIRECTED on fatal-signal death (top-level shell)** | **OPEN after v0.754.0** — the rider closed THREE provable windows (drain-before-trap; pop-after-restore w/ stream-level `streams_restored`; mid-SETUP fd-0 ambiguity → explicit `fd0_was_closed`), four mutation replays pin them, and the rate did NOT separably move: base ~1.08% (5/464) → post-A ~0.14% (1/700) → post-B ~0.60% (3/500) — statistically inseparable (dev retracted its own '~10x' read). CORRECTED MECHANISM (proven by sentinel-file capture): output is not lost — it is written INTO the live per-command redirect target. Mechanism misdiagnosed TWICE (dead-binding story; teardown-sliver hypothesis FALSIFIED by (B) at N=500). CHARACTERIZATION: fires in file-mode 1/25 and stdin-mode 1/25, -c 0/25 (verifier, tip); face (b) wrong-exit observed 1/100 independently. OBSERVATION LIMIT: every fd-write trace hides the window (0/400 traced vs ~3/500 untraced). **ENTRY REQUIREMENT for successor: non-perturbing observation (pre-allocated in-process ring buffer sampled at death, or external record) as FIRST deliverable.** GATE CLASSIFICATION: sentinel tests `test_exit_in_exit_trap_matches_bash_sigterm` (face a) and `test_exit0_in_exit_trap_command_mode_dies_by_signal` (face b) stay un-quarantined by ruling — classify their rare failures against THIS row. The interactive SIGHUP death path DELIBERATELY retains pre-1.3b behavior (no drain, old swallow — exposure exists there; successor inherits). RULINGS RECORDED (2026-07-25, integrator): slot retitled 'signal-window hardening'; in-tree statistical oracle WAIVED (would permanently flake the gate); ONE-tripwire rule. | successor queue; re-eval at Checkpoint R (w/ %P rider) |
| Redirect-frame teardown atomicity (CLASS) | 1.3b closed the EXIT-trap instance + pop-order instance + mid-SETUP fd-0 instance; the CLASS question (any writer landing in a frame window inherits a dying/foreign binding) remains — audit = successor row. Also: doc-pointer guard validates only the PATH half of file#symbol cites (tooling carry, found 1.3b round-2) | successor queue |
| psh `TIMEFORMAT %P` absurd values | `time true`: psh `R=0.000 U=0.010 S=0.000 P=11934.31` vs bash `P=2.02` — 10 ms accounting tick / 84 µs elapsed ≈ 11930 (mechanism verified arithmetically); 2/30 idle-host rate; CLI-reachable. 1.3's test fix makes the suite deliberately magnitude-blind, so nothing in the tree notices this until fixed. | successor queue; CANDIDATE QUICK RIDER at Checkpoint R |
| Backgrounded-subshell redirect bypassed when `sys.stdout` ≠ fd 1 | In-process harness only (file created EMPTY, output to captured stdout); foreground twin, bg simple command, and subprocess psh all CORRECT → internal inconsistency in the bg child-runner path (`psh/executor/subshell.py#_execute_background_subshell` shares streams :254-256 as does fg :144-146 — divergence is in the surrounding runner). CLI-unreachable. Characterization pin added v0.753.0 (both capture regimes). 5-row evidence matrix in `1.3-rescue/`. | successor queue; discharge trigger: any slot touching `_execute_background_subshell`/`run_background_shell_child` |
| `try_resolve_bash` dead inventory | After 1.2's 11 + 1.3's 9 loudness conversions, zero consumers outside its own definition/self-test/gen_census pattern string — the exact referenced-only-by-its-own-test shape F2 outlawed for the catalog | successor queue (delete or re-justify) |
| F1: documented-difference matching is BEHAVIOR-BLIND | Found by 1.2's FLIP-PINS audit, verified twice: `_is_documented_difference` is `command in catalog` with both observed results unused — a forged nonsense psh stdout for `echo $$` still classifies DOCUMENTED_DIFFERENCE, so those pins cannot fail for the right reason (HIGH-1 family). Closure = typed expected-shape per catalog entry + shape-validating classifier + forged-output discriminator red-on-base | **1.3 — CLOSED** v0.753.0: per-side expected shapes + validating classifier; forged stdout AND exit-status discriminators red-on-base (4 failed/3 passed); right-reason by mutation (PSH_BUG at tip, no-change at base); vacuous-expected hole closed BOTH halves (runtime + meta-test) with offender. |
| F2: difference catalog rot | 4 of 7 entries (HELP_BUILTIN, PUSHD_BEHAVIOR, PUSHD_CWD_DIFFERENCE, POPD_BEHAVIOR) referenced by ZERO tests; PUSHD_CWD_DIFFERENCE documents a HARNESS artifact as a shell difference. Closure = every entry test-referenced or deleted + zero-dead-entries meta-test | **1.3 — CLOSED** v0.753.0: 4 dead entries deleted w/ live probes (pushd family CONTRADICTED by test_bash_compatibility identity assertion; harness artifact confirmed); 1 REAL divergence registered shape-carrying (BUILTIN_LONG_HELP_OPTION); zero-dead-entries meta-test, resurrection-proven. |
| 1.2-era flake queue additions | `test_complex_pipeline_background` (1x under load); `TestExitTrapOnFatalSignal::test_command_mode_fires_exit_trap` (1x under load, 3/3 isolated); `timeformat %P` recurrence (= carry #8); malformed-bytes `mapfile_read_all` (1-of-9) | **1.3 — DISPOSED** v0.753.0: pipeline + exit-trap-command-mode NOT REPRODUCED (80-90 runs each incl. load), hardened not quarantined; %P root-caused (carry #8 row); mapfile not reproduced (80 runs), hardened w/ absolute expected-bytes pins; exit-trap family root-caused to the REAL race (row below → 1.3b) |
| Runner default-timeout exposure | 1.2's migration gave 296 runner call sites in 53 migrated modules the 10s default where base was untimed (loud Timeout → non-comparable, never false-green); fresh flake surface under load — per-case explicit timeouts, not a global bump. 1.3: tested and ruled OUT as mechanism for every queued flake | 1.3 → standing watch |
| 9 pre-existing silent-skip oracle modules | `try_resolve_bash`+skipif modules predating 1.2 (enumeration in 1.2-rescue/slot-ledger) silently skip w/o bash oracle; loudness ruling applies | 1.3 |
| 1.4 carry: locale warn wider surface | Seven psh-vs-bash divergence rows OUTSIDE the fixed LC_ALL reset path (probe matrix in `1.4-rescue/slot-ledger.md`): bash SILENT / psh WARNS on `LANG=<bad>` (assign, assign+unset, temp-env prefix, startup) and startup `LC_COLLATE=<bad>`; REVERSE direction on `unset` of already-bogus LC_CTYPE (bash warns, psh silent) — **a blanket silencing pass would make this worse, forbidden**; plus warn SHAPE (bash 1 line naming LC_ALL, psh per-category lines). Fix seam: `psh/core/state.py` (NOT locale_service.py — the v0.755.0 fix landed there; ruling #1's file name was wrong) | successor queue |
| 1.4 carry: `bg` on RUNNING job silent | psh returns 0 silently where bash prints "bg: job N already in background"; pre-existing, out of 1.4's minimal-diff ruling | successor queue |
| 1.4 carry: benchmark tier baselines | 3 absolute-threshold rows (~24% over on shared runners, pass locally) made non-gating per ruling #4 (workflow comment + artifact trail + this row = the visibility conditions); owed: measured runner baselines | Checkpoint R / Ceremony C |
| 1.4 carry: second-sweep blindness | Timeout path's second `_killpg_sigkill` cannot see descendants (leader reaped ⇒ children reparented to init, pid/ppid links gone); first call's enumerate-before-kill does the real work; §7(1) producer bound covers the cap-disabled residual | recorded limit |
| 1.4 carry: bg PTY manifestation unpinned | Ruling #2's deterministic pin construction is -c/file/stdin-mode; the load-dependent interactive-PTY manifestation stays covered only by pre-existing `test_pty_smoke` row (sanctioned) | flake watch |
| 1.4 carry: nightly instrumentation expiry | Sampler + fd snapshots + PSH_DISK_WATCH + core_pattern normalization stay as relapse watch; REMOVAL CRITERION (in workflow comment): several consecutive green SCHEDULED nightlies, zero ENOSPC, no trips | Wave 2+ close checks |
| 1.4 carry: StopIteration one-off | `test_argument_less_builtin_has_no_trailing_space_script` StopIteration in 30143337081, never recurred; now reports the listing on failure. Procsub zombie rows: fixed `sleep 0.2` settle accepted; bounded reap-poll PRE-RULED APPROVED if either row flakes on a scheduled run | flake watch |
| 2.1 carry: `[[ ]]` operand execution divergences | THREE psh-vs-bash execution divergences found while building the security scanner, all in `[[ ]]` flat-text operand quoting (bash 5.2.26 oracle, marker-file verified): (1) escaped backtick `[[ "\`cmd\`" == x ]]` — psh EXECUTES, bash treats literal; (2) `[[ "\\$(cmd)" == x ]]` — bash EXECUTES, psh does not (lexer collapses `\\$(`→`\$(`); (3) `[[ $'$(cmd)' == x ]]` — psh expands the substitution in `$'...'`, bash does not. Scanner flags per PSH's own execution ("opener live unless immediately preceded by a backslash"); the DIVERGENCES themselves (a parser/lexer question) are for a successor slot. Exact spellings + root causes in `2.1-rescue/slot-ledger.md` §11. | successor queue |
| 2.1 carry: `[[ ]]` double-quoted operand flattening | A double-quoted `[[ ]]` operand parses to a Word with a bare LiteralPart (no ExpansionPart), so a live `$()` inside it has no structural node — the security scanner's UNANALYZED_REGION flag is the only coverage. Real fix is a parser change (give the operand real expansion parts), out of 2.1's visitor scope. | successor / parser slot |
| 2.1 lesson (cross-slot): generate over the SPACE | The slot's most transferable output. A hand-built 19-shape corpus reported "zero losses" and was wrong; the adversarial harness's 105 generated scripts found 8; the dev's COMBINATORIAL 81-shape matrix found 12 (two whole families the harness missed); the integrator's user-facing gate found 1 more (the `$@` advisory no count-level check could see). Each layer caught what the others could not. Durable form: an executable coverage-SPACE suite (`test_reference_coverage_space.py`) whose claim is "generated over {families}×{positions}, domain stated." Ask of any base⊆tip claim: generated over what space, and where is the domain stated? | banked |
| 2.1 lesson (cross-slot): instrument discipline binds BOTH directions | 10 instrument faults surfaced (7 dev, 3 integrator). A verifier's instrument fails toward "dev claim wrong" as easily as a dev's fails toward "all clear" — the integrator's broken `grep -c "...'$y'"` ($ = regex anchor → false 0) and byte-mangled `printf` each nearly recorded a CORRECT dev claim as false. Rule: state the instrument, show its output, change the instrument on challenge; for finding counts use `grep -F`; write `[[ ]]`/`$'...'` probes byte-exact from files (`od -c` verified), never via `-c`/printf. | banked |
