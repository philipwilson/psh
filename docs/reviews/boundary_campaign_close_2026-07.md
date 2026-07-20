# Boundary Integrity Campaign — Closing Report

**Campaign:** Boundary Integrity (executing reappraisal #20's thesis: semantic
information loss at subsystem boundaries). Operating brief:
`docs/reviews/boundary_campaign_briefs_2026-07-16.md`.
**Span:** v0.725.0 – v0.748.0 (24 releases, PRs #471–#494), plus this closing
slot Q3 (v0.749.0, PR TBD).
**This report:** the §15 closing report — final boundary ledger, 27-type
representation/consumer census, deliberate-loss registry, post-campaign carry
audit, H1–H19+C1 closure table, exact commands, and public-API changes.

**RELEASE-SHA:** the `gated_commit` recorded in the committed `gate_attestation.json` attesting version 0.749.0 (the v0.749.0 bump commit, tagged `v0.749.0` on merge). Report content finalized at `378bfd1b` + this ceremony fixup.

Working ledgers and probe transcripts referenced below live under
`tmp/boundary-ledgers/` (per-slot `<SLOT>.md` + `<SLOT>-probes/`); this committed
report and the pins/manifests it names are the durable evidence (§15).

---

## (a) Final boundary ledger — per package

Verify scorecard at close (from campaign memory): **24 dev slots → 16 bounces +
8 clean passes; 44/44 distinct verifier-found blockers real, 0 false.** Every
package landed attestation-gated per E4; compare-bash stayed 2,986/24 EXACT
throughout; conformance grew monotonically to 2,539.

**Closing-verification slot (dev-cv, v0.750.0):** a fresh closing verification
(4,253 probes / 68 composed cases / 103 strength attacks) found and
dispositioned **3 production blockers + 17 nits**. The three blockers were REAL
divergences that refuted shipped claims — CV1 (W2 arith-context quote
provenance), CV2 (R2/H13 PATH/CDPATH projection-vs-variable reads, converged
across 6 consumer faces by integrator ruling), CV3 (I4 interactive `history -p`/
`-s` invocation removal) — each now fixed and pinned red-on-base. The 17 nits are
guard gaps (F8/F5/construction-purity), record defects (this report, the conftest
docstring), and the W3 probe-harness patch. *(The integrator fills the final
frozen scorecard line — updated slot/bounce totals — at ceremony.)*

| Rel | PR | Pkg | Outcome (one line) |
|-----|----|-----|--------------------|
| 0.725.0 | #471 | E1+E4 | Structured phase-manifest gate (no nonzero exit → success; complexity/benchmark tiers split); SHA-attestation gating `release-tag.yml` (ancestor + attestation-only-diff checks). |
| 0.726.0 | #472 | E2+E3 | ONE bash-oracle runner (`tests/harness/shell_oracle.py`, typed failures, killpg+byte-cap); 73 offenders migrated + ratchet; LC_CTYPE provenance; suite hermeticity fixture. |
| 0.727.0 | #473 | Phase-E close | Three seeded gates → identical censuses; committed exit manifest `docs/boundary_phase_e_exit_2026-07-17.md`; ceremony gates hermetic. |
| 0.728.0 | #474 | F1 | Frozen `InvocationConfig` before `Shell`; `-ic` family; bash-faithful sign policy; closes r21 CORE-4 + #20 H17. |
| 0.729.0 | #475 | F3 | `ProgramSource` 6-channel boundary + `execute_sourced_file`; NUL policy probed to live bash; positional gate. |
| 0.730.0 | #476 | F2 | `ProcessLeaseCoordinator` / `ActivationLease`; construction-pure `Shell`; LIFO std-fd leases with user-redirect relocation; `Shell.shutdown` sole path; closes #20 H18. |
| 0.731.0 | #477 | S1 | Fusion-FIRST lexer; keyword-prefix promotion deleted (killed a live `while$x` infinite-loop); `LexicalWord` realized as invariants over Token+parts. |
| 0.732.0 | #478 | S2 | Heredoc transaction `HeredocSpec`/`CollectedHeredoc`/FIFO collector; `$'EOF'` cooking; closes #20 H1/H3 + r21 G1. |
| 0.733.0 | #479 | S3 | Typed `WordTemplate`/`ArithmeticTemplate`/`SubscriptSpec`; read-time nested-grammar validation, lazy arithmetic; closes #20 H2. |
| 0.734.0 | #480 | S4 | `ParseInputs`/`ParserState` split; typed `Complete|Incomplete|Invalid`; 3 combinator algebra laws fixed; caret one coordinate system. |
| 0.735.0 | #481 | S5 | `PipelineComponent` typed sum (FunctionDef joins); `walk_ast`+`AstChildSchema` sole traversal; closes #20 H9. |
| 0.736.0 | #482 | W1 | `ExpandedWord`/`ExpandedField`/`FieldRun` IR; ONE field-splicing algebra; no flatten; closes #20 H5. |
| 0.737.0 | #483 | W2 | ONE `SubscriptEvaluator` (r21 signature closed: 6 impls → 1); indexed-vs-assoc by target kind. |
| 0.738.0 | #484 | W3 | ONE iterative `CompiledPattern` engine, four relations; regex matching path DELETED; closes #20 H7 (exponential case dead). |
| 0.739.0 | #485 | R2 | Tri-state `VariableLookup` (MISSING/PRESENT_UNSET/VALUE); env-fallback deleted; nameref/tempvar model; closes #20 H13. |
| 0.740.0 | #486 | R1 | Source-ordered `RedirectProgram`, ONE applicator at all 4 sites; deferred-close deleted; ONE heredoc file description; closes #20 H4+H8. |
| 0.741.0 | #487 | R3 | Resolve-once `ResolvedCommand`/`NormalizedCommandName`/`CommandEnvOverlay`; 3 recompute sites deleted; `effective_path` deleted; closes #20 H10. |
| 0.742.0 | #488 | I1 | Surrogateescape `InputCursor`; replace-decode deleted (byte-identical round-trip); owned open-file-description identity + registry; closes #20 H16. |
| 0.743.0 | #489 | I2 | Lazy `ProgramSource` (`LazyFileInput`, block-buffer/never-over-read); memory bounded; fd-255 convention; closes #20 H14. |
| 0.744.0 | #490 | I3 | `ParseSession` = ONE completeness engine (accumulator = thin adapter); comb-vs-rd outcome converged; #20 H15 PARTIALLY closed (Option A, oracle-forced). |
| 0.745.0 | #491 | I4 | Typed `HistoryExpansionResult`; `:p`→stderr, heredoc-body suppression, `history -p` wired; 5 byte paths surrogateescape. |
| 0.746.0 | #492 | J1 | ONE job lifecycle: `AsyncJobPolicy` every-member, `ForegroundJobSession` with die-by-signal announce; typed `no_hup`/huponexit/reap; closes #20 H11+H12; H19 PARTIAL (ruling 2 — substantially closed, residual + Linux-nightly watch carried). |
| 0.747.0 | #493 | Q1 | Five narrow `psh/protocols` (VariableAccess/ExpansionContext/IOContext/JobRuntime/LocaleContext); IOContext+JobRuntime migrated; shrink-only full-Shell ratchet. |
| 0.748.0 | #494 | Q2 | Nine cross-cutting ratchets landed sequentially (option walkers, getattr/hasattr on declared fields, broad VT catches, registry-outside-resolution, redirect re-derivation, oracle bypass, syntax-bearing raw fields, visitor recursion, incomplete signatures). |
| 0.749.0 | this release | Q3 | This slot — documentation closure + dead-surface sweep + closing report (see below). |

---

## (b) Representation and consumer census (27 canonical types)

Producers located by `grep -rn --include='*.py' "^class <T>"` (Union/Dict/data
for the four typed-sum/schema/invariant cases); consumer inventories derived by
`tmp/boundary-ledgers/Q3-probes/census.sh` (`grep -rln "\b<T>\b" psh/` minus the
producer file), archived in `Q3-probes/census-consumers.txt`. **Every type has
ONE named producer and no second semantic implementation outside a justified
terminal adapter (§15.2).**

| # | Type | Producer (`file.py#symbol`) | Production consumers (grep-derived) |
|---|------|-----------------------------|-------------------------------------|
| 1 | ShellRunResult | `tests/harness/shell_oracle.py#run_shell_case` (Union `Completed\|SpawnFailure\|Timeout\|DecodeFailure`) | TEST-tree type (the oracle-runner contract): 12 test files CALL `run_shell_case` (the census methodology subtracts the producer file `tests/harness/shell_oracle.py` itself from the 13 grep hits); not a `psh/` production type by design. |
| 2 | InvocationConfig | `psh/invocation.py#parse_invocation` | `__main__.py`, `shell.py`. |
| 3 | ActivationLease | `psh/core/process_lease.py#ProcessLeaseCoordinator.activate` | `core/state.py`, `shell.py`. |
| 4 | LocaleContext | `psh/core/locale_service.py#LocaleContext` (frozen; on `LocaleService.profile`) | shell instance via `state.locale`; pattern engine/case/collation. **Name note:** a Q1 `psh/protocols#LocaleContext` *Protocol* reuses the name (interface, NOT a 2nd impl); `LocaleProfile` is a documented dead rename alias (0 consumers). |
| 5 | ProgramSource | `psh/scripting/program_source.py#ProgramSource` (classmethod channels) | `__main__.py`, `input_sources.py`, `script_executor.py`, `visitor_modes.py`, `shell.py`. |
| 6 | LexicalWord | INVARIANTS realization (sanctioned declared deviation) over the lexer Token+parts; authority `psh/lexer/__init__.py#_post_lex` (`fuse_words` then classify) | KeywordNormalizer, WordBuilder, both parsers. |
| 7 | HeredocSpec | `psh/utils/heredoc_detection.py#HeredocSpec` | `lexer/heredoc_collector.py`, `heredoc_lexer.py`, `cmdsub_scanner.py`, `interactive/history_expansion.py`, `utils/__init__.py`. |
| 8 | CollectedHeredoc | `psh/utils/heredoc_detection.py#CollectedHeredoc` | `lexer/heredoc_collector.py`, `heredoc_lexer.py`, `utils/__init__.py`. |
| 9 | ParseInputs | `psh/parser/parse_inputs.py#ParseInputs` | `parser/__init__.py`, `recursive_descent/context.py`, `combinators/{arrays,expansions,parser}.py`, `support/syntax_templates.py`. |
| 10 | ParserState | `psh/parser/parse_inputs.py#ParserState` | `parser/__init__.py`, `recursive_descent/context.py`, `support/syntax_templates.py`. |
| 11 | WordTemplate | `psh/ast_nodes/syntax_templates.py#WordTemplate` | `ast_nodes/__init__.py`, `words.py`, `support/syntax_templates.py`. |
| 12 | ArithmeticTemplate | `psh/ast_nodes/syntax_templates.py#ArithmeticTemplate` | `ast_nodes/{__init__,control,words}.py`, `support/syntax_templates.py`. |
| 13 | SubscriptSpec | `psh/ast_nodes/syntax_templates.py#SubscriptSpec` (interpreted by `expansion/subscript.py#SubscriptEvaluator`) | `ast_nodes/{__init__,arrays,words}.py`, `support/syntax_templates.py`. |
| 14 | PipelineComponent | `psh/ast_nodes/__init__.py#PipelineComponent` (Union) | `ast_nodes/{commands,control}.py`, `combinators/commands/statements.py`, `recursive_descent/parsers/{commands,statements}.py`. |
| 15 | AstChildSchema | `psh/visitor/traversal.py#AstChildSchema` (Dict; consumed by `walk_ast`) | `ast_nodes/__init__.py`; `walk_ast` is the sole traversal for all production visitors. |
| 16 | ExpandedWord | `psh/expansion/word_expansion_types.py#ExpandedWord` | `expansion/word_expander.py`. |
| 17 | ExpandedField | `psh/expansion/word_expansion_types.py#ExpandedField` | `expansion/word_expander.py`. |
| 18 | CompiledPattern | `psh/expansion/pattern_engine.py#CompiledPattern` (via `PatternCompiler.compile`) | `expansion/parameter_expansion.py` + the `pattern.py` facade (all 4 relations). |
| 19 | RedirectProgram | `psh/io_redirect/redirect_program.py#RedirectProgram` | `io_redirect/planner.py` (+ ONE applicator at 4 dispatch sites). |
| 20 | NormalizedCommandName | `psh/executor/command_resolution.py#NormalizedCommandName` | `executor/command.py`. |
| 21 | CommandEnvOverlay | `psh/executor/command_resolution.py#CommandEnvOverlay` | `executor/command_assignments.py`, `command.py`. |
| 22 | ResolvedCommand | `psh/executor/command_resolution.py#ResolvedCommand` | `executor/command.py`. |
| 23 | VariableLookup | `psh/core/variable_lookup.py#VariableLookup` | `core/scope.py`, `executor/command_resolution.py`, `protocols/__init__.py`. |
| 24 | InputCursor | `psh/builtins/input_reader.py#InputCursor` | `builtins/{read_builtin,mapfile_builtin}.py`, `core/state.py`, `executor/command.py`, `io_redirect/input_cursor.py`, `scripting/input_sources.py`, `protocols/__init__.py`. |
| 25 | ForegroundJobSession | `psh/executor/foreground_session.py#ForegroundJobSession` | `executor/{job_control,pipeline,strategies,subshell}.py`, `protocols/__init__.py`. |
| 26 | AsyncJobPolicy | `psh/executor/process_launcher.py#AsyncJobPolicy.for_launch` | ProcessLauncher's per-member launch path (in-module; self-contained per-launch policy). |
| 27 | HistoryExpansionResult | `psh/interactive/history_result.py#HistoryExpansionResult` | `builtins/shell_state.py`, `interactive/history_expansion.py`, `scripting/{command_accumulator,source_processor}.py`. |

**Justified terminal adapters (the only sanctioned "second surfaces", §15.2):**
`command_accumulator.CommandAccumulator` (scripting↔parser; I3 Option-A —
docstring now names owner + permanent status); `LexicalWord`-as-invariants
(declared deviation over Token+parts, S1); `parse()` as the terminal materialize
over `parse_outcome()` (S4); `expansion/arrays.py#_eval_array_index` thin
adapter over `SubscriptEvaluator` (W2). Plus the two PERMANENT reference oracles
(see WP3 / part (c)).

**Q1 dependency direction:** migrated boundaries depend on the narrow
`psh/protocols` interfaces; the import edge is one-way (implementations import a
protocol, a protocol never imports an implementation), a true leaf — stated in
`psh/protocols/__init__.py`, `ARCHITECTURE.md` Invariant #9, and enforced by
`tests/unit/tooling/test_protocol_layering_q1.py`; the full-`Shell` consumer set
only shrinks (`tests/unit/tooling/test_shell_consumer_ratchet_q1.py`).

---

## (c) Deliberate-loss / documented-divergence registry

Assembled from the archived slot ledgers (`tmp/boundary-ledgers/*.md`). Each is
a sanctioned, pinned divergence — psh behaves deliberately (bash-verified), not
accidentally.

| Origin | Deliberate loss / divergence | Where recorded / pinned |
|--------|------------------------------|-------------------------|
| F1 | Text-level invocation differences (usage wording, `--` handling) | F1.md §"Documented text-level differences"; invocation matrix rows. |
| F2 | `cwd` (`cd` persistence) + recursion-limit are PROCESS-OWNED shell semantics, never restored on lease release (§16) | `ProcessBaselines` docstring; `test_process_lease.py`. |
| F3 | `ProgramSource` line-origin NOT carried at parse time (threaded at execution); rc return-status discarded; D10 `bash` SEGFAULTs where psh fails clean at the recursion limit | F3.md ledger; `test_program_source_guard.py`; NUL channel matrix. |
| I1 | SCOPED byte-cursor deliberate-loss registry: (a) the malformed-multibyte count-boundary family — including the MIXED valid+malformed `read -N` case, whose count boundary matches NEITHER the UTF-8 nor the C-locale bash oracle (a HYBRID model, not merely "mbrtowc quirks"; carry #21) — and (b) inherited-fd 0/1/2 with unknowable aliases, are documented losses, not chased | I1.md §"Deliberate-loss registry"; `I1-probes/deliberate-loss-probes.txt`. |
| I2 | Lazy source BLOCK SIZE is a documented deliberate loss (a mid-block edit before the block is read is not seen) | I2.md; `small_append`/`big_append` red-on-base pins + `truncate_self`/`rewrite_ahead` controls. |
| I3 | Full linear completeness on a single open construct is O(k²) (bash's PTY-proven immediate mid-construct errors force per-feed parsing) — CHARACTERIZED, not eliminated; the full fix is a resumable lexer+parser (see carry register) | I3.md Option-A ruling; `test_session_linearity_i3.py` (doubling-ratio characterization). |
| S3→I3 | Substitution-body syntax error in a STRING channel (`-c`/`eval`/`source`): bash exits fatally with **rc 127 AND aborts the enclosing eval/source frame**; psh gives uniform **rc 2** and does NOT frame-abort. Both halves (the rc-127 channel split AND the eval/source frame-abort) travel together as ONE family. S3 shipped the typed producer contract (`SubstitutionSyntaxError` / `is_substitution_origin`, raised at the `parse_nested_command` chokepoint) and HANDED the consumption to I3; **I3 never consumed it**, so the contract is inert and this remains a LIVE documented divergence (see carry #22). | S3.md "Design + declared deviations (all ruled by integrator)" DEVIATION 1 + "New handoffs → To I3 (PRODUCER CONTRACT)"; 6-way green pin `tests/conformance/bash/test_nested_substitution_timing_conformance.py::test_divergence_c_mode_exit_code_is_127_in_bash` (parametrized: operand `$(if)`, procsub `<(if)`, param `${x:-$(if)}`, arith `$(($(if)+1))`, subscript-read `${a[$(if)]}`, subscript-write `a[$(if)]=v`). |
| S4→I3 (**CLOSED — historical, not a live loss**) | The unclosed-expansion parser OUTCOME briefly differed (combinator=Invalid, rd=Incomplete) when disclosed in S4; **I3 CLOSED it** — the shared `detect_unclosed_expansion` producer now feeds BOTH parsers, so both classify an unclosed expansion at EOF as Incomplete. Listed only for provenance; there is no live divergence and no both-ways pin. | `tests/unit/parser/test_parse_outcome_s4.py::test_unclosed_expansion_outcome_parity` (both parsers Incomplete). |
| W2 | ARITH-context associative-subscript keying — BOTH halves, stated precisely (updated by CV1, v0.750.0): **(1) the `$`-half** — a substituted `$`-form's SOURCE SPELLING is kept and NEVER re-expanded (`k='$x'; (( h[$k]=1 ))` keys the literal `$x`; `$(echo hi)` in a value keys literally) — is **bash-EXACT doctrine, NOT a divergence**. **(2) the quote-provenance half** — quote/escape removal applies to SOURCE-spelled subscript characters only, never to characters that ARRIVED via substitution (`k='"q"'; (( h[$k]=1 ))` keys `"q"`, not `q`) — was a REAL divergence (psh quote-removed substituted text); **CLOSED by CV1**, so it is no longer a live loss. This row is retained for provenance; neither half is now a live divergence. | brief §9 amendment + W2.md; CV1 pins `tests/unit/expansion/test_subscript_evaluator.py::TestArithAssociativeKeyProvenance` + `tests/conformance/bash/test_subscript_keying_conformance.py::TestArithSubscriptProvenance` (9 live-bash rows); `psh/expansion/CLAUDE.md` arith-keying prose (both halves). |
| R1 | Heredoc substrate: psh uses a temp file for the heredoc body's shared file description where bash may use a pipe — documented deliberate loss next to the H8 pins (lseek discriminator; BSD-probed) | R1.md §"Heredoc substrate"; `test_heredoc_shared_cursor_r1.py`. |
| R2 | bash tempvar/nameref provenance model realized as psh's; `shell.env` structural realization sanctioned (env -i constraint) | R2.md; `test_variable_lookup.py`. |
| J1 | huponexit LOGIN-narrowing: psh has no login-shell concept, so the exit-HUP gate is `interactive + huponexit` (not bash's `interactive login`) — SANCTIONED deliberate difference | J1.md §H19; `docs/user_guide/17_differences_from_bash.md` §17; `test_pty_huponexit_j1.py`. |
| J1 | SIGHUP/interactive-signal facts are python-pty PROBE-construction-dependent (a realistic-terminal leg is required) — caveat recorded so future probes don't regress | J1.md; caveat in `psh/executor/CLAUDE.md`. |
| E23 | psh installs a script-mode SIGINT handler where POSIX/bash differ — noted as a psh-vs-POSIX divergence (originally flagged for J1) | E23.md §"Deliberate-loss register". |

---

## (d) Post-campaign carry register — audit

One row per registered carry with disposition (CLOSED-with-pointer, or
CARRIED-with-description). Items #1-2 are CLOSED by the Q3 slot; rows #18-22 were
added by the closing-verification slot (dev-cv, v0.750.0) — five carries the
fresh closing verification surfaced (#18/#19 now both-sides characterization-
pinned, #20/#21 registered residuals, #22 the S3→I3 unconsumed producer contract).

| # | Carry | Disposition |
|---|-------|-------------|
| 1 | Q2 retained oracles (extglob_to_regex/_convert_pattern; normalize_bracket_expressions/_POSIX_CLASSES_PATHNAME) | **CLOSED (Q3 WP3).** Integrator RULED permanent reference oracles; deferred-deletion stigma removed; documented as PERMANENT with test sites named. Both oracle tests verified live (105 passed / 16 param-skipped, 0 xfail). |
| 2 | F9 git-range self-check silent skip on gitless checkouts | **CLOSED (Q3 WP5).** `test_migrated_modules_are_the_campaign_created_set` (and its Q1 twin `test_created_modules_match_enumeration`) now WARN loudly (naming the lost protection) before skipping; +2 self-tests; green-repo behavior unchanged. |
| 3 | empty-arith-subscript (warn-continue) | CARRIED. Both-sides-pinned pre-existing divergence (psh warns and continues on an empty arithmetic subscript); W2 carry. |
| 4 | operand-`$@` flatten | CARRIED. W1/W3 flip-pins record the pre-existing divergence. |
| 5 | F6.6 definition-rejection | CARRIED. F-phase definition-rejection edge, documented. |
| 6 | exec-builtin message | CARRIED. R3-noted message-wording divergence. |
| 7 | RANDOM-in-prefix | CARRIED. `RANDOM` in a command prefix-assignment, documented edge. |
| 8 | timeformat `%P` flake | CARRIED (to test-flake queue). W2-noted flaky `time` format `%P` case. |
| 9 | plain-expansion echo stream | CARRIED. I4-noted plain-expansion echo stream edge. |
| 10 | history `-p` failed-arg wording | CARRIED. I4-noted `history -p` failed-argument message wording. |
| 11 | trailing-redirect-at-EOF | CARRIED. I3-noted new pre-existing divergence (trailing redirect at EOF). |
| 12 | general async reaper (prompt-reap) | CARRIED. J1-noted — the general async-reaper/prompt-reap path (H19 residual). |
| 13 | stopped-fg-subshell not recorded | CARRIED. J1-noted foreground-subshell stop-recording edge. |
| 14 | procsub-`$!`-wait | CARRIED. J1-noted process-substitution `$!`/`wait` interaction. |
| 15 | tcsetattr-drain probe note | CARRIED. J1 probe note (terminal-drain probe construction). |
| 16 | RESUMABLE-PARSER CAMPAIGN (full #20 H15) | CARRIED as a future campaign. I3 ruling: full linear completeness needs a resumable lexer+parser (campaign-scale, Option B recorded); H15 is PARTIALLY closed + characterized (part (g)). |
| 17 | J1 Linux-nightly watch (amended J1 ruling — a MUST) | **CARRIED — NOT yet discharged as of this report.** The first `nightly.yml` run after the J1 merge must be checked for the new monitor-mode rows in `tests/unit/executor/test_boundary_j1_job_lifecycle.py` and the promoted PTY signal fan-out tests — macOS (the local gate host) has a signal/pgroup coverage gap, so Linux-vs-bash for these is exercised only in the nightly. Recorded here because `tmp/` ledgers are scaffolding; this durable row keeps the obligation from being lost. |
| 18 | R3 posix-mode special-builtin redirect-error fatality | **CARRIED (registered by dev-cv, v0.750.0).** In POSIX mode a redirection error on a POSIX SPECIAL builtin is FATAL in bash (the shell exits mid-line); psh reports the error and CONTINUES (both agree in default mode). Now BOTH-SIDES characterization-pinned: `tests/conformance/bash/test_cv_carry_characterization.py::TestPosixSpecialBuiltinRedirectFatality`. |
| 19 | `$'\xNN'` (NN >= 0x80) escape byte model | **CARRIED (registered by dev-cv).** bash emits the RAW byte 0xNN; psh emits the UTF-8 ENCODING of codepoint U+00NN (`$'\xff'` → `c3 bf`, not `ff`) — a pre-existing byte-model divergence. Characterization-pinned both sides: `test_cv_carry_characterization.py::TestAnsiCHighEscapeByteModel`. |
| 20 | interactive `key_decoder` replace-decode | **CARRIED (registered by dev-cv).** The interactive line editor's `KeyDecoder` decodes stdin bytes with `errors='replace'` (a malformed byte becomes U+FFFD on screen), unlike the I1 surrogateescape READ path — a criterion-4 residual scoped as a terminal-UI NON-GOAL (a keystroke that can't be decoded is not data to round-trip; the fix would degrade the interactive editor with no bash-parity gain). Registered so the residual is not re-discovered; no pin (terminal-UI, PTY-only). |
| 21 | I1 mixed valid+malformed `read -N` count-boundary | **CARRIED (registered by dev-cv).** A `read -N` spanning a mix of VALID and MALFORMED multibyte bytes lands on a count boundary that matches NEITHER the UTF-8 nor the C-locale bash oracle — a HYBRID model, not "just mbrtowc quirks" (the part (c) I1 row is corrected accordingly). Documented loss, not chased; `I1-probes/deliberate-loss-probes.txt`. |
| 22 | S3→I3 substitution-origin producer contract NOT consumed | **CARRIED (registered by dev-cv).** S3 shipped the typed `SubstitutionSyntaxError`/`is_substitution_origin` PRODUCER CONTRACT (at the `parse_nested_command` chokepoint) and handed the mapping to I3; **I3 never consumed it**, so it is inert and the rc-127 channel split + eval/source frame-abort remain a LIVE documented divergence family (part (c) S3→I3 row; 6-way green pin `test_nested_substitution_timing_conformance.py::test_divergence_c_mode_exit_code_is_127_in_bash`). |

---

## (e) Exact commands and numbers at the close

Dev-complete gate run @ `59324a55` (this branch, at the commit BEFORE this report
file — a clean full-suite run; the report adds 0 tests, and the only delta at the
report SHA is the index self-reference documented below, which the ceremony
resolves):

```
python run_tests.py --parallel
  → 20190 passed, 1590 skipped, 10 xfailed   (parallel 19,298 + serial 892)
ruff check psh tests tools   → All checks passed!
mypy                         → Success: no issues found in 274 source files
```

- **Gate baseline** (committed `gate_attestation.json` @ 11cd8284, v0.748.0):
  19,296 + 892 = **20,188**. **Q3 adds exactly +2** (the two WP5 loud-skip
  self-tests, both in the parallel phase) → **20,190**. Pre-registered = actual.
- **conformance:** unchanged at 2,539/1/8xf (Q3 added no conformance tests).
- **compare-bash:** expected **2,986/24 EXACT** — Q3 is behavior-inert (docs,
  docstrings, a dead-alias deletion with test rename, and a loud-skip warning).
  NOT re-run here (the `--compare-bash` block-buffering hazard); the integrator
  verifies EXACT at the ceremony SHA.
- **mypy:** **274** files (unchanged; no modules added or removed).
- **Index self-reference (ceremony item):** re-running the gate at the SHA that
  INCLUDES this report file trips one meta-test —
  `tests/unit/tooling/test_reviews_index.py::test_every_review_file_is_indexed`,
  which requires every `docs/reviews/*.md` to be linked from
  `docs/reviews/README.md`. This report is the sole unindexed file. Q3 leaves
  `README.md` untouched by charter (a parallel session owns it); the integrator
  adds one index row for this file at ceremony, which restores the gate to
  20,190. This is a coordination item, not a behavioral regression.

Probe transcripts (Q3 slot): `tmp/boundary-ledgers/Q3-probes/` —
`census.sh` + `census-consumers.txt` (27-type census), `hpin-verification.txt`
(H-pin existence/xfail check — reconciled by the closing-verification slot, see
below), `gate-devcomplete.txt` (the gate transcript). Closing-verification slot
(v0.750.0) probes: `tmp/boundary-ledgers/CV-probes/` — `cv1_matrix.sh`,
`cv2_matrix.sh` + `cv2_hash_exec_source.sh`, `cv3_bash.sh` (three-way blocker
matrices), `cv-hpin-verification.txt` (the reconciled H-pin re-run), and
`w3-fixed/` (the six W3 harnesses patched to honor `$W3_PSH_ROOT` with a
validated fallback — the integrator swaps them into the archive at ceremony).
Archived per-slot ledgers and probes for E1..Q2 live beside them.

---

## (f) Public-API changes across the campaign

psh is a shell application, not a library, so "public API" here means
module-level symbols an out-of-tree consumer could import. Summarized from
`CHANGELOG.md` v0.725.0–v0.748.0 (see the changelog for full detail):

- **New typed public surfaces** (the 27 canonical types above) replaced ad-hoc
  strings/flags/caller-owned state at each boundary — see the per-package ledger.
- **`InvocationConfig`** parses invocation before `Shell` construction (F1);
  `Shell` construction is now process-pure with an explicit `ActivationLease`
  activation step (F2).
- **Removed / superseded internal surfaces:** `effective_path` (R3),
  deferred-close redirect representation (R1 H4), the glob→regex matching path
  (`extglob_to_regex` demoted to a production-dead permanent oracle, W3),
  replace-decode of runtime bytes (I1 H16), `report_abnormal_termination` (J1),
  `extglob.glob_to_regex_body` + `InputCursorRegistry.reset` (Q2 dead-code
  deletions), and the six inconsistent subscript implementations → one
  `SubscriptEvaluator` (W2).
- **Q3 (this slot):** the `InputReader` → `InputCursor` back-compat rename alias
  (`psh/builtins/input_reader.py`) is **removed** — it had zero production
  consumers; its only two test consumers were migrated to `InputCursor` (inert).
  *Integrator: add a v0.749.0 CHANGELOG note recording this public-symbol
  removal.* The `LocaleProfile = LocaleContext` pre-campaign alias is retained
  but now documented with owner/reason/removal-condition (0 consumers).

---

## (g) #20 H1–H19 + C1 closure table

Every named pin was collected AND run. The closing-verification slot RE-RAN a
reproducible selection — the 21 closure-table pin FILES below — at the final SHA:
**604 passed, 0 skipped, 0 xfailed** (`CV-probes/cv-hpin-verification.txt`, exact
command recorded). This reconciles the stale Q3 figure: `Q3-probes/hpin-
verification.txt` claimed **591** at `59324a55`, but that "217 unit + 369
conf/sys/int + 5 H7-diff" bucket selection was not preserved; running the 21
closure-table FILES gives **603** for the pre-slot file contents, and this slot's
construction-purity fix added ONE test to the H18 pin file
(`test_construction_purity_f2.py::test_construction_writes_nothing_to_os_environ`),
so the reconciled count is **603 + 1 = 604**. The suite's 23 xfail markers are all
in unrelated files (phase-manifest plugin, interactive history/completion, pty
smoke, benchmarks, absent-features ledger) — none an H-pin. H15/H19 remain PARTIAL
by ruling (their pins pass; the partiality is scope, not a skip). This table feeds
the integrator's §15.1 closing verification.

| Finding | Status | Pinning test (`file::function`, verified present, not skip/xfail) |
|---------|--------|-------------------------------------------------------------------|
| C1 | pinned (held) | `tests/unit/tooling/test_redirect_program_guard_r1.py::test_no_procsub_prefix_sniffing_anywhere` |
| H1 | closed | `tests/conformance/bash/test_heredoc_transaction_conformance.py::test_two_operators_one_command` |
| H2 | closed | `tests/unit/parser/test_syntax_templates.py::test_template_types_are_frozen_and_named` (+ `tests/conformance/bash/test_nested_substitution_timing_conformance.py`) |
| H3 | closed | `tests/unit/utils/test_heredoc_detection.py::test_rule` (+ heredoc-transaction conformance) |
| H4 | closed | `tests/unit/io_redirect/test_redirect_program_r1.py::test_classify_covers_every_operator` |
| H5 | closed | `tests/conformance/bash/test_field_splicing_conformance.py::test_at_suffix_unquoted_splits` |
| H6 | closed | `tests/unit/expansion/test_pattern_relations.py::test_full_match` |
| H7 | closed | `tests/unit/expansion/test_pattern_engine_differential.py::test_string_consumers_match_bash` |
| H8 | closed | `tests/integration/redirection/test_heredoc_shared_cursor_r1.py::test_heredoc_read_then_cat_shares_offset` |
| H9 | closed | `tests/conformance/bash/test_function_def_pipeline_component_conformance.py::test_function_def_pipeline_component_matches_bash` |
| H10 | closed | `tests/conformance/bash/test_command_resolution_conformance_r3.py::test_h10_headline_eval` |
| H11 | closed | `tests/unit/executor/test_boundary_j1_job_lifecycle.py::test_async_policy_stdin_is_single_only_but_signal_is_every_member` |
| H12 | closed | `tests/unit/tooling/test_foreground_session_sole_owner_j1.py::test_signal_death_reporting_has_one_chokepoint` |
| H13 | closed | `tests/conformance/bash/test_variable_truth_conformance.py::test_declared_unset_local_default_operator` |
| H14 | closed | `tests/unit/scripting/test_lazy_script_reader_unit_i2.py::test_reads_physical_lines_with_trailing_empty` |
| H15 | **PARTIAL** (oracle-forced; characterized) | `tests/unit/parser/test_session_linearity_i3.py::test_heredoc_body_line_is_o1` (linear paths pinned; the O(k²) single-open-construct residual is characterized — full closure = the RESUMABLE-PARSER carry, part (d) #16) |
| H16 | closed | `tests/unit/builtins/test_input_cursor_i1.py::test_malformed_lead_before_ascii_round_trips` (+ `tests/system/test_read_malformed_bytes_i1.py::test_read_malformed_matches_c_locale_bash`) |
| H17 | closed | `tests/system/invocation/test_invocation_matrix.py::test_matrix_row` (parametrized `ic_*`/`i_script_*`/`i_s_piped_*` rows) |
| H18 | closed | `tests/unit/core/test_construction_purity_f2.py::test_second_shell_construction_changes_nothing_utf8_first` |
| H19 | **PARTIAL** (J1 ruling 2 — substantially closed; prompt-reap/general-reaper residual carried, part (d) #12; Linux-nightly watch, part (d) #17) | `tests/unit/executor/test_boundary_j1_job_lifecycle.py::test_hangup_jobs_conts_stopped_before_hup` |

**Summary:** C1 held; H1–H14, H16–H18 closed with Bash-pinned tests. **TWO
findings are PARTIAL:** **H15** (oracle-forced per the I3 Option-A ruling,
characterized; full fix scoped as the post-campaign RESUMABLE-PARSER campaign)
and **H19** (J1 ruling 2 — substantially closed, one prompt-reap/general-reaper
residual carried plus the Linux-nightly watch obligation). The remaining
findings are closed.
