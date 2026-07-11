# Ground-Up Reappraisal #19 — Textbook-Quality Edition: psh at v0.687.0

**Date:** 2026-07-10
**Baseline:** v0.687.0 (main @ `8a622ff8`, read from a pinned detached-worktree snapshot because work
was ongoing in the main tree; gate 14,890 passed / 0 failed / 12 xfail at release; 16,300 collected;
compare-bash 1,307/0/23 over 1,330 goldens; mypy clean across all 255 production files; `ruff check psh` 0)
**Method:** 16 independent per-subsystem auditors, each reading **every file in its scope in full**
(the 16 scopes tile all 255 files under `psh/` plus test infrastructure and cross-cutting concerns),
followed by **16 adversarial verifiers** — one per report — who re-read every HIGH/MED at the cited
`file:line`, attempted to refute it (grepping for dynamic dispatch before accepting dead-code claims,
re-deriving complexity claims, running live probes from the snapshot), and then hunted the files the
auditor under-visited; capped by a completeness critic that verified scope tiling and computed
whole-tree metrics. Verdicts: **203 CONFIRMED, 18 ADJUSTED, 0 REFUTED**, plus 81 verifier-added
findings. Total: **362 findings — 22 HIGH, 125 MED, 215 LOW.** Per-subsystem prose reports with
verification addenda preserved under `tmp/appraisal-r19-reports/`.
**Focus:** Unlike reappraisals #1–#18, this round does **not** grade bash compatibility. It grades
**textbook quality**: could this codebase be published as a book on shell internals? Three axes —
**elegance** (one chokepoint per concern, composition, no dead code, no divergent twins), **clarity**
(naming, docstring honesty, teaching narrative, doc accuracy), **efficiency** (accidental algorithmic
waste and hot-path churn only; the project's clarity-over-performance stance respected). A handful of
live behavioral defects were found anyway — by reading, not probing — and are reported because each
is the *symptom* of a structural finding.

---

## Verdict

**psh is close to its textbook ambition, and the remaining distance is concentrated on a single axis.
Clarity grades A− at the median (floor B): the docstring culture — probe-cited invariants,
deliberate-divergence essays, named drift-lock tests — is the best any auditor had seen in this
codebase's class. Efficiency is essentially a solved problem tree-wide (median A−, floor B+): both
historical quadratic cliffs are fixed with documented O(n) designs, and nothing found this round is
worse than per-prompt or per-keystroke churn. Elegance is the binding constraint (median B+, floor
B−), and the deductions are strikingly uniform: divergent twin code paths and accreted dead API.**

Two numbers tell the story. **Eleven of the 19 auditor-reported HIGHs are divergent-duplicate
findings, and all 16 scopes reported at least one twin** — the project's self-named #1 defect factory
is not a local anecdote but the tree-wide binding constraint. And **roughly a quarter of all 362
findings are dead, vestigial, or ghost surface** — refactor waves ship replacements without deletions,
and unit tests keep the corpses warm ("kept alive only by its own unit tests" recurs in four scopes).

The most important *positive* result is a controlled experiment the codebase ran on itself:
**every chokepoint enforced by a registry plus drift-lock meta-test held; every chokepoint enforced
by prose ("MUST agree", "the ONE message shape", "single chokepoint") was found violated.** The cure
for most of what follows is not new discipline but wider application of the project's own proven
pattern.

Three live behavioral defects surfaced as symptoms of one structural class (re-deriving from strings
what an earlier stage knew structurally): a quoted literal `'<(echo x)'` redirect target *executes as
a command* (H1), a heredoc flanked by quoted parens executes its body as commands (H2), and
`case $'a\nb'` matches no branch (H3). A fourth, `local -r x=1; local x=2` silently bypassing
readonly (H7), fell out of the twin-mutation-path audit. All four should enter the normal
bash-verification workflow.

## Grade table

Prior column: most recent graded appraisal of that area (2026-07-05..07 subsystem appraisals where
they exist, else reappraisal #17/#18) — note those rounds graded correctness+architecture, so
movement is indicative, not arithmetic.

| Subsystem | Eleg | Clar | Eff | Prior | Headline |
|-----------|------|------|-----|-------|----------|
| Lexer | B+ | A− | A− | B− (07-05) | Best documentation culture in the tree (deliberate-non-unification essays); held back by dead public API tail + two triplication clusters |
| Parser (RD) | B+ | A− | A− | B+ (07-05) | Near-publishable; one demonstrable depth-guard bypass via a third compound dispatch + dead error machinery |
| Parser (combinator) | B− | B | A− | C−/B− (07-06) | Core/spine chapter-quality; thick ghost/dead stratum (fictitious token names, shelfware combinators); visualization pkg is the defect factory in miniature |
| Expansion | A− | A− | B+ | A−/A− (#17) | Strongest textbook candidate (param_parser, policy table, pattern engine); one newline-unsafe regex fast path breaks `case` on `$'\n'` |
| Arithmetic engine | B+ | A− | A− | A−/A− (#17) | A complete interpreter in 1,596 lines — ideal warm-up chapter; 218-line elif ladder + unreified lvalue are the debts |
| Executor | B+ | B+ | A− | B+/A− (#17) | child_policy/resolver/launcher architecture strong; the designated assignment contract docstring states the opposite of the code |
| Core/State | B+ | A− | A | C (07-06) | **Biggest riser.** Registry+meta-test chokepoints exemplary; two twin mutation paths remain, one hiding a readonly bypass |
| Builtins (decl) | B+ | B+ | A | C+ (07-06) | Infrastructure half (base/registry/engine/formatter) is A-grade; `local` is still a 158-line divergent twin of `declare` |
| Builtins (io/jobs) | B | B+ | A | C+ (07-06) | input_reader.py publishable as-is; ~6 hand-rolled clones of the option-parse walk the package's own docs mandate against |
| I/O Redirect | B+ | A− | A | A− (07-07) | Best invariant prose in the tree (fd-universe narrative); procsub target string-sniffing is the one HIGH, and it misfires |
| Interactive | B+ | A− | A− | B+ (07-07) | Line-editor core is showcase decomposition; history_expansion.py is a pre-textbook monolith (210 lines, nesting depth 10) |
| Scripting + entry | B+ | A− | B+ | A− (07-07) | command_accumulator is genuinely textbook; the lex→parse pipeline is hand-copied three times and the analysis copy drifted |
| Visitor | B | B+ | A− | A− (#17) | Infrastructure layer publishable; analysis visitors are an oracle-less sidecar with five verified false-positive/no-op advisories |
| AST + utils | B+ | A− | A | — (new) | ast_nodes' derived-property doctrine is meta-test-enforced and exemplary; utils is bimodal (escapes.py superb, heredoc_detection carries a quote-blind twin) |
| Test infrastructure | B | B+ | A− | B− (07-06) | run_tests classify + claims meta-test publishable; ~150 lines dead conftest surface, twin fixtures split 313/315, one born-vacuous guard |
| Cross-cutting | B+ | B+ | A− | B+/A− (#17) | Exception taxonomy + shell.py phases publishable; 2 runtime import cycles, 398 lazy imports, ARCHITECTURE.md teaches 4 retired designs |

## What is already textbook-grade

A book reviewer would accept these chapters today (auditors were asked to name strengths, and the
verifiers seconded all of these):

- **`psh/lexer/cmdsub_scanner.py`** — states the hard problem, contrasts the design with bash's
  `xparse_dolparen`, names its three owner test files as a maintenance contract.
- **`psh/lexer/command_position.py`** — defines the shared vocabulary once and explains why the three
  tracking machines are deliberately NOT unified, each asymmetry with its reason, locked by a
  consistency test. The rarest kind of design documentation.
- **`psh/expansion/param_parser.py`** — the `${...}` grammar has exactly one classifier and its
  docstring *is* the grammar reference; replaced four drifting parser copies.
- **`psh/expansion/pattern_engine.py`** — parse-once pattern AST + memoized matcher documenting both
  exponential predecessors, with `count_states()` as an assertable complexity guard.
- **`psh/expansion/word_expansion_types.py`** — the three-axis expansion-policy table with named,
  probe-cited instances; policy as data, not folklore.
- **`psh/executor/child_policy.py`** — one fork helper (grep-verified sole `os.fork()`), one child
  signal policy, the parent-mask-restored-even-on-EAGAIN invariant narrated.
- **`psh/io_redirect/fd_remap.py`** and **`manager.py`'s two-universes narrative** — motivates both
  collision failure modes with shell reproductions; the best orientation prose in the package.
- **`psh/core/option_registry.py` / `special_registry.py` / `_materialize_env_name`** — the three
  registry chokepoints, each guarded by a drift-lock meta-test — the pattern the rest of the tree
  should adopt.
- **`psh/builtins/input_reader.py`** — five stated design invariants, all real in the code; one core
  read loop behind `read`, `mapfile`, and stdin scripts. Publishable as-is.
- **`psh/utils/escapes.py`** — the best "do NOT deduplicate this" document in the codebase: maps all
  five escape dialects with the exact behavioral deltas justifying each chokepoint.
- **`psh/utils/printf_formatter.py`**, **`psh/ast_nodes/base.py`**, **ast_nodes' derived-property
  doctrine** (`SimpleCommand.args`, `Word.quote_type` — derived, never stored, meta-test-enforced).
- **`psh/scripting/command_accumulator.py`** — one real-parser-driven completeness oracle shared by
  script and interactive input, typed NeedMore/Complete results, trial-AST reuse.
- **`psh/interactive/key_decoder.py` / `edit_buffer.py` / `line_layout.py`** — pure state machines
  with the layering rule ("what the decoder does NOT know") stated; readline-accurate kill-ring
  coalescing implemented line-for-line from its stated invariant.
- **`psh/core/exceptions.py` + `internal_errors.py`** — errors-vs-control-flow taxonomy with one
  policy chokepoint; **`psh/shell.py`** — named construction phases 0–7 with Before/After contracts
  (its "no execution logic" claim verified true).
- **`run_tests.py`'s `classify_phase_result`** — failure-masking policy as a pure, unit-pinned
  decision function; **`tests/conformance/test_claims_have_tests.py`** — publishable meta-testing.

---

## Findings

### HIGH (22)

#### A. Re-deriving from strings what an earlier stage knew structurally — with live symptoms

**H1 — Procsub redirect targets are detected by string-sniffing the expanded target, and the sniff
misfires both directions.** `resolve_procsub_resource` tests
`target.startswith(('<(', '>(')) and endswith(')')` on a *post-expansion* string
(`psh/io_redirect/process_sub.py:302`) after `_word_is_process_sub`
(`psh/io_redirect/file_redirect.py:103`) had the fact structurally and dropped it. Probed live on the
snapshot: `cat < '<(echo SNIFFED)'` **executes the quoted literal filename as a command** (prints
SNIFFED, exit 0), and `x='$y'; y=secret; cat < <(echo $x)` double-expands via the legacy fallback
(prints `secret`). **Fix:** carry the `ProcessSubstitution` node on the `RedirectPlan` when
`_word_is_process_sub` is true; never sniff a string.

**H2 — `contains_heredoc` is a quote-blind naive twin of the module's own expansion scanner, and its
wrong `False` short-circuits the accurate path.** `psh/utils/heredoc_detection.py:373` pairs `((`
with `))` by list index, quote-blind, in the same module as the real scanners
(`_scan_arith_or_cmdsub`, `_quote_flags`). Demonstrated: a script line
`echo '((' ; cat <<EOF ...` — bash prints the heredoc body (exit 0); **psh executes the body and
`EOF` as commands** (exit 127). Verifier adjustment: the "accurate path" fails the same demo too
(`scan_line_heredoc_markers` returns `[]`), so the fix must feed `_quote_flags` into the region
scanners, not merely delete the fast path.

**H3 — The plain-glob regex fast path is newline-unsafe: two classic Python-regex porting mistakes.**
`_convert_pattern` emits `.`/`.*` compiled without `re.DOTALL` (`psh/expansion/extglob.py:146`), and
`psh/expansion/parameter_expansion.py:163/182/377` anchor with `'$'` instead of `\Z`. Measured:
`case $'a\nb' in *)` matches **no branch**; `[[ $'a\nb' == a?b ]]` is false; `${x//?/-}` skips
newlines. The memoized `pattern_engine` gets all of these right — this is exactly the
two-backends-drift its design claims to prevent. **Fix:** wrap converter output in `(?s:...)` and
replace every `'$'` end-anchor with `\Z`; add newline-subject pins.

**H4 (adjacent to this class) — Array element assignment leaks lexer Tokens into the executor.**
`ArrayElementAssignment.index` is `Union[str, List[Token]]`; both parsers emit a one-token list that
`psh/executor/array.py:253-264` unwraps via the stringly-typed
`str(token.type) == 'TokenType.VARIABLE'` — a branch that is dead for all real parser output.
**Fix:** type `index` as `str` (or a `Word`), delete the token-sniffing loop.

#### B. Divergent twin code paths (the #1 defect factory, structural)

**H5 — `local` is a 158-line divergent twin of `declare`.** `LocalBuiltin.execute_in_context`
(`psh/builtins/shell_state.py:240-397`, nesting depth 5) duplicates declare's copy-then-build `+=`
logic (330–355 vs `function_support.py:414-447`, same campaign comment in both), verbatim
`_build_indexed_array`/`_build_assoc_array` copies, and a 9-branch attribute if-chain where declare
has an `_OPTION_ATTRIBUTES` table; `local -n` lacks declare's target-shape check. The declaration
engine's own docstring defers this as "Phase 4 work". **Fix:** extract the shared array-init/attribute
pipeline into `declaration_engine.py`; leave only `create_local` scope semantics in `local`.

**H6 — Option parsing has no working chokepoint: ~6 hand-rolled clones of the `parse_flags` walk.**
`base.parse_flags` exists and `psh/builtins/CLAUDE.md:182` mandates it, yet `read`
(`read_builtin.py:432`), `mapfile`, `wait`, `trap`, `ulimit`, and `cd` each re-implement the
cluster/value/`--` walk with divergent rules — and trap's comments record a real bug the previous
hand-rolled parser caused (`signal_handling.py:90-92`). Two invalid-option message dialects coexist
(`"-x: invalid option"` vs `"invalid option: -x"`). **Fix:** extend `parse_flags` (validator hooks,
usage-exception mode, ordered-events variant), migrate the five; keep `print`/`kill`/`dirs`
hand-rolled with their existing justification comments.

**H7 — `create_local` bypasses readonly on same-scope redeclare** *(verifier-added, probed live)*.
The readonly guard at `psh/core/scope.py:623-625` checks only outer scopes; the redeclare path
(`:647-651`) overwrites `current_scope.variables[name]` unguarded.
`f(){ local -r x=1; local x=2; echo $x; }; f` → psh prints `2` rc 0 (bash: `local: x: readonly
variable`, keeps 1). Falsifies `variable_store.py`'s "readonly enforcement cannot be bypassed" claim;
no test pins it. **Fix:** check `existing_local.is_readonly` on both redeclare paths.

**H8 — Two live `+=` append engines.** `VariableStore.append` (`psh/core/variable_store.py:109-161`)
duplicates `assignment_utils.resolve_append_assignment` (same nameref resolve, same integer-append
formula, same array element-0 copy) — both live via different callers (declaration engine vs executor
prefix-assignments, plus a third caller the verifier found in `builtins/shell_state.py:370`), and the
store's docstring claims ALL appends go through it. Verifier adjustment: the observed
`copy()`-vs-`deepcopy` difference is textual, not yet behavioral — this is a drift *risk*, already
lied about, not yet a bug. **Fix:** one shared append-computation helper; make the docstring true.

**H9 — The inherited-traps rule is implemented twice with disagreeing exemption sets.**
`clone_for_child` (`psh/core/state.py:497-506`) exempts ERR-under-errtrace AND DEBUG-under-functrace;
`enter_subshell_trap_environment` (`psh/core/trap_manager.py:288-296`) exempts ERR only — while its
docstring claims it applies "the same" rule. A functrace DEBUG trap behaves differently between
`( )` and `{ ...; } &` children. **Fix:** one `compute_inherited_traps()` called from both sites.

**H10 — The child exception-to-exit-status taxonomy is hand-copied at five fork sites, and two
copies already disagree.** The TopLevelAbort/FunctionReturn/LoopBreak/SystemExit mapping is repeated
at `process_launcher.py:280-314`, `child_policy.py:185-193` and `:326-345`, `subshell.py:167-173`,
`pipeline.py:252-265`; `SystemExit(None)` maps to **1** in the launcher and **0** in child_policy.
**Fix:** `child_policy.map_child_exception(exc) -> int`, each site keeping only genuinely
site-specific arms.

**H11 — The heredoc-aware lex→parse pipeline is written out three times, and the analysis copy has
drifted.** `_trial_parse` (`command_accumulator.py:256`), `_parse_command`
(`source_processor.py:429`), `_parse_for_analysis` (`psh/scripting/visitor_modes.py:16-48`) — synced
only by mirror-comments; the third ignores `--parser` (so `--parser combinator --validate` validates
with the RD parser) and drops `lexer_options`. **Fix:** one shared `lex_and_parse()` helper in
`psh/scripting/` called by all three.

**H12 — Function bodies bypass the parser's documented single-chokepoint depth guard via a third
compound-command dispatch.** `commands.py:459-463` and `context.py:65-69` claim
`_parse_compound_component` is where `nesting_depth` accumulates;
`functions.parse_compound_command` (`psh/parser/recursive_descent/parsers/functions.py:132-159`)
hand-rolls brace parsing and dispatches via `parse_control_structure`. Verified: 1,200 nested brace
groups trip MAX_NESTING_DEPTH; 1,200 nested function bodies do not. **Fix:** route function bodies
through `_parse_compound_component`; delete `parse_control_structure`, whose if/elif chain exists
only for this call site.

#### C. Analysis & visualization sidecars (oracle-less, and it shows)

**H13 — The validator's 'useless use of cat' twin misfires on every bare `cat file`.**
`psh/visitor/validator_visitor.py:163` checks membership in `_in_pipeline`, which `visit_Pipeline`
sets for single-element pipelines too — verified: `psh --validate` on `cat file.txt` reports
"Useless use of cat"; direct visits TypeError on the dead `getattr` default. The linter's twin
(`linter_visitor.py:311`) is correct. **Fix:** delete the validator copy; the linter owns the check.

**H14 — The linter flags every bare assignment as an undefined function call** *(verifier-added,
probed)*. `visit_SimpleCommand` adds `cmd` to `used_functions` unguarded
(`psh/visitor/linter_visitor.py:211`); `psh --lint` on a script containing `FOO=bar` reports
"Function 'FOO=bar' is called but not defined" and exits 1. The existence check five lines later has
the `'=' in cmd` guard; this line doesn't. Together with H13, `set -eu` misdetection
(`:407` — told to add `set -e`), quoted-`"$@"` false positives
(`enhanced_validator_visitor.py:506`), `--metrics` always reporting 0 process substitutions
(`metrics_visitor.py:480`), `(( i = i + 1 ))` flagged as MEDIUM ARITHMETIC_INJECTION
(`security_visitor.py:221`), and `cd -P /tmp` flagged as too-many-arguments
(`validator_visitor.py:149`), the analysis layer holds **seven verified always-fire/never-fire
advisories**. **Fix (the fork):** harness these visitors (goldens + strict-errors + self-tests) or
delete them; the middle path is what produced this.

**H15 — The DOT generator silently renders wrong diagrams from AST fields that no longer exist.**
`visit_ForLoop` reads `node.iterable`; `visit_CStyleForLoop` reads `init/condition/update`;
`visit_SimpleCommand` reads `variable_assignments` — all hasattr-guarded, so the drift is silent
(`psh/parser/visualization/dot_generator.py:241/253/173`). `ast_formatter.py:1-14` documents fixing
this exact failure mode in its twin. **Fix:** the structure-driven `__dataclass_fields__` walk,
keeping per-node methods only for labels.

**H16 — Compact/Detailed ASCII renderers are no-ops: `render()` is a `@staticmethod` that hardcodes
the base class.** Verified `CompactAsciiTreeRenderer.render(ast) == AsciiTreeRenderer.render(ast)`
exactly (`psh/parser/visualization/ascii_tree.py:36`); the live `parse-tree` builtin's compact mode
does nothing. **Fix:** `@classmethod` + `cls(**kwargs)`, or delete the config-only subclasses.

**H17 — Ghost token vocabulary: parsers built for TokenType names that do not exist.**
`token('AND_IF')`/`token('OR_IF')` (load-bearing in the and-or grammar), `EQUALS`, `GLOB`,
`ASSIGNMENT`, `HEREDOC_DELIMITER` (`psh/parser/combinators/tokens.py:45/162-171`) reference names
absent from `TokenType` — they can never match, and readers learn a fictitious vocabulary. **Fix:**
delete; make `token()` validate names against `TokenType.__members__` at construction.

**H18 — Most of the combinator toolkit is shelfware, and the guide misdescribes the grammar**
*(verifier-added)*. `between`, `literal`, `lazy`, `try_parse`, `separated_by`,
`with_error_context`, `ForwardParser`: zero live-grammar call sites (`psh/parser/combinators/core.py:406`);
`docs/guides/combinator_parser_guide.md:173` claims "pipelines chain commands with `separated_by()`"
— `pipelines.py:104-143` is a manual while loop. **Fix:** delete or mark the unused algebra as
illustrative; correct the guide to the actual closure style.

#### D. Documentation contracts that state the opposite of the code

**H19 — The designated assignment-contract docstring asserts the persistence rule the code
deliberately does not implement.** `psh/executor/command_assignments.py:19` point 3 claims
unconditional POSIX persistence for `VAR=v special-builtin`; the code persists **only in POSIX mode**
(`command.py:785-787`, `strategies.py:277-280` — "ONLY in POSIX mode"), and
`psh/executor/CLAUDE.md:24` designates this docstring as THE contract. The verifier found the same
unconditional wording at five more sites in `command.py` (`:91`, `:114`, `:376`, `:544`, `:725`).
**Fix:** one sweep to the mode-aware wording across all seven locations.

**H20 — ARCHITECTURE.md teaches four retired designs and contradicts its own body.** COMPOSITE
tokens (§2.6, retired per `token_types.py:87-88`); stored `SimpleCommand.args` (§3.12 — violates the
doc's own Invariant 5); raw `os.fork()` pipelines (§4.4 — violates Invariant 6); brace expansion as
pre-lex (§1.3 + diagram — moved to the Word stage in v0.678, per the module's own docstring); plus a
tail claiming ParserConfig POSIX modes and multi-error recovery that §3.6/§3.10 document as removed,
and a "5,500+ tests" count (actual: 16,300 collected). The flagship orientation document is the worst
single teaching liability in the tree. **Fix:** rewrite the four sections from current code; delete
or regenerate the stale capabilities tail; sync counts.

#### E. Meta-test integrity

**H21 — The keyword-comparison guard has been vacuous since birth.** The regexes in
`tests/unit/tooling/test_keyword_comparisons.py:14` use doubled backslashes in raw strings
(`r"token\\.value\\s*=="`), so they require a literal backslash in scanned source and have never
matched anything (verified; introduced this way in `4efc0dd0`). It is the only tooling guard without
a self-test — proving the guard-the-guard idiom by exception. **Fix:** single-escape, add the
standard synthetic-offender self-test.

**H22 — `expand_history` is a pre-textbook monolith in a showcase subsystem.** 210 lines, measured
nesting depth 10, nested `while/else` where the `else` means "not inside `${...}`", and three O(prefix)
backward scans per `!` candidate — O(n²) worst case — while quote state is already tracked forward
(`psh/interactive/history_expansion.py:48-257`). The surrounding editor core (EditBuffer/KeyDecoder/
LineRenderer) is the best decomposition in the tree, which makes the contrast a teaching hazard.
**Fix:** track bracket/brace/arith depth forward beside `in_dquote`; split the scanner from the
already-decomposed resolvers.

### MED (125 — clustered)

**Dead/vestigial/ghost surface (~25% of all 362 findings; the largest single class).** Lexer:
unraisable-but-exported `LexerError` with a 25-line dead renderer (`position.py:98`), five unused
TokenStream methods with fake "quote tracking" (`token_stream.py:62`), dead
`normalize_heredoc_delimiter` cross-referenced by live docs (`heredoc_lexer.py:32`), dead
`is_inside_expansion` twin (`pure_helpers.py:596`) — the latter two have now outlived **two prior
review flags**. Parser: dead ErrorSeverity/`context_tokens`/CONTROL_KEYWORDS/`ErrorContext.expected`
(`helpers.py:11/169`), unreachable-and-broken `_candidate_split_element` (`arrays.py:182`).
Combinator: 14 dead keyword parsers + dead do/then separators implemented twice differently
(`control_structures/__init__.py:86`), three parallel test-only APIs in `tokens.py:204`. Core: dead
typed accessors with a false "hottest internal reads" rationale (`option_registry.py:222`).
Builtins: dead PrintMode/request fields (`declaration_engine.py:52`), `disown -h` writing a
`no_hup` attribute nothing declares or reads (`disown.py:111`), a 46-line trap help dead because the
property is named `help_text` not `help` (`signal_handling.py:31`). Visitor: write-only
`in_loop`/`function_stack`/`_in_subshell`/`total_lines` across three visitors plus a docstring
promising a break/continue check that cannot work (`validator_visitor.py:66`). Interactive: dead
accessor cluster + PromptManager getters with zero callers while the multiline handler re-implements
them divergently (`multiline_handler.py:95`). Tests: ~150 lines of dead isolation-era conftest
surface (`tests/conftest.py:240`), a dead quarter of the conformance framework
(`conformance_framework.py:402`), a second 421-line PTY harness serving only default-skipped tests.
**Policy fix:** dead-code passes must treat "referenced only from its own unit tests" as dead and
delete test+code together.

**Duplication beyond the HIGHs (each worth a dedicated fix).** Lexer: triplicated quote-lexing flow
(`modular_lexer.py:421/460/495`) and the triplicated heredoc-delimiter-unquoting rule held together
by "MUST agree" comments (`heredoc_lexer.py:211` — the verifier *proved it has already drifted*,
bash siding with one copy against another). Expansion: three sibling substitution scan loops
(`parameter_expansion.py:246-336`), legacy `expand_array_to_list` twin (`arrays.py:306`), subscript
splitting hand-rolled at ~9 sites. Arithmetic: 218-line operator elif ladder (`tokenizer.py:197`) and
the unreified lvalue (6 node classes, 6 evaluator methods, 3 parser forks for 3 concepts).
Combinator: three ~85%-identical function-def parsers (`structures.py:172`), while/until 60-line
clones, word-like token sets declared six times with undocumented variations, ~80 lines of
reflection duplicated between two renderers (four renderers, three field-enumeration strategies).
Executor: foreground-subshell child body re-implements `run_child_shell` steps 3–6
(`subshell.py:121`), `_rhs_pattern`/`_rhs_regex` twin skeletons with one recipe pasted three times
(`enhanced_test_evaluator.py:207`). Core: four hand-rolled shadow-resolution enumeration walks in
`scope.py`, twin temp-env binders with a nameref-policy divergence (`scope.py:190/238`). Builtins:
three divergent PWD/OLDPWD updaters of which only `cd` got the readonly fix
(`directory_stack.py:308`), `read`'s `_read_special`/`_read_with_timeout` twins, test/[ integer ops
pasted six times and the stat dance nine times (`test_command.py:479/334`), type/command -V pasting
the same six-way banner, `source` hand-rolling a third PATH walk with divergent empty-component
semantics against CLAUDE.md's explicit ban (`source_command.py:137`). I/O: the open-flags table
re-derived (`file_redirect.py:331`), a noclobber message hand-raised three times,
`setup_child_redirections` re-implementing the `format_redirect_error` chokepoint inline — three
message shapes in one function (`manager.py:869`). Visitor: three incompatible `is-assignment`
predicates, two always-defined-variable whitelists making `--lint` and `--validate` disagree about
`$HOSTNAME`, twin unquoted-in-test heuristics. Tests: verbatim twin AST analyzers across two guards,
twin temp-dir fixtures split 313/315 with no ratchet, 81 files on the deprecated capsys idiom vs 115
on the blessed one, golden harness and conformance framework resolving their bash oracle by two
different policies (PATH bash vs BASH_PATH→Homebrew — 26 golden cases use bash-4+ syntax that stock
macOS `/bin/bash` 3.2 rejects). Cross-package: **three divergent ANSI-C `$'...'` encoders with
verified three-way output disagreement** for `$'\x01\x1b'` across `@Q`/`%q`/`declare -p`
(`escapes.py:148/188` vs `formatter_quoting.py:123` — the probed authority).

**Doc drift (8 of 9 audited subsystem CLAUDE.mds; the visitor's is the lone accurate one).** The
worst drift is always an embedded code sketch: builtins CLAUDE.md inlines the pre-fix `write()` body
whose two bugs the code documents fixing (found independently by both builtins auditors);
io_redirect's backup and heredoc sketches teach the exact naive recipes `_save_fd_high` and
`_content_to_fd` forbid at length; core's CLAUDE.md snippets contradict the env-write invariant the
same document declares; executor's shows the pre-F9 strategy order and a nonexistent attribute;
lexer's pipeline diagram omits the word-fusion stage entirely; interactive's states lazy-allocation
and notification-marker claims that are both now false; parser's cites a token group with zero
references. Five core docstrings still cite the `adopt()` method removed in v0.656. **Fix:** either
snippet drift-locks (assert the quoted code appears in the module) or replace sketches with
invariant prose + pointers.

**Help/usage text is a distinct oracle-less drift class (5 scopes).** `unset`/`declare`/`local`
synopses omit `-n`; `read` omits `-u`; `pwd`/`cd` omit `-L/-P`; `wait` omits `-n/-p`; `exec` omits
`-a/-c/-l`; `shopt` help hardcodes 8 of 11 registry options; `help` falls back to a hardcoded
version "0.54.0" via a nonexistent attribute; two `-h` surfaces print `__doc__` instead of help;
debug builtin help advertises a phantom `parser` option while its real option map is pasted three
times; `__main__.py` HELP_TEXT omits `-o/+o` and `-B/+B`; `explain_parse()` is a 50-line hardcoded
narrative with stale claims. The registry+meta-test cure applied to options/specials/env was never
applied to help. **Fix:** generate synopses from the option tables, or a drift meta-test comparing
help text against each builtin's accepted flags — one mechanism closes the whole class.

**Strict-errors taxonomy erosion at subsystem borders.** The arithmetic evaluator relabels plain
`ValueError`/`TypeError` (the documented internal-defect class) as expected shell errors
(`evaluator.py:485/533` — verifier caution: plain ValueError is genuinely user-reachable there, so
the fix is to re-type the cant-happen branches, not narrow the catch); analysis modes swallow
internal defects with a bare `except (ValueError, TypeError)` (`visitor_modes.py:90`), so `--lint`
bugs misreport as parse errors even under strict-errors; `read` uses a private
`ValueError`+`setattr('rc')` dialect; `UnclosedQuoteError` escapes the documented PshError root.
Jointly, the suite-wide strict-errors guarantee is quietly weaker than documented in ~3 subsystems.

**Layering and import hygiene.** Two genuine runtime package cycles survive only via partial-init
semantics: `builtins↔executor` (`builtins/job_control.py:6` ↔ `executor/command.py:20`) and
`core→utils→lexer→core` (an 18-line TokenFormatter dragging the lexer into the leaf package —
`utils/token_formatter.py:2`). 398 function-level intra-psh imports (AST-counted), many not
cycle-forced, obscure the dependency structure. Data-vs-behavior name collisions:
`CommandSubstitution` and `ParameterExpansion` each exist as both AST node and engine, with adjacent
files importing opposite meanings. mypy config carries 14 redundant per-package overrides with one
enumeration hole (`array_flat_text.py` silently unchecked — benign today, the exact escape mode the
config's own comment warns against).

**Monolith functions (the size-findings map).** 8 of the 10 longest functions drew explicit
findings; the census: `ShellState.__init__` 266 (`core/state.py:93`), arithmetic `tokenize` 218,
`expand_history` 210, `_execute_pipeline` 206, `_run_command` 190, `main` 179, `set_variable` 171
(`core/scope.py:441` — one of two blind spots, in the tree's largest file), `ReadBuiltin.execute`
170, `CdBuiltin.execute` 169 (with a dead tilde branch behind an always-false hasattr),
`execute_function_call` 167 (`executor/function.py:90` — the other blind spot; function.py drew zero
findings). 94 of 2,865 functions exceed 80 lines (3.3%); 25 modules exceed 600 lines.

**Efficiency residue (all confirmed, none cliffs).** `CommandAccumulator.feed` re-preprocesses and
re-parses the whole buffer per physical line — O(N²) per multi-line construct on the main
script-reading path, the one item on a hot path (`command_accumulator.py:187`); case-mod operators
re-run the full glob→regex conversion once per character (`parameter_expansion.py:449`);
`PromptExpander._expand_escape` evaluates all ~25 expansions to select one, per escape character
(`prompt.py:170`); per-prompt full-variable-dict materialization via the `state.variables` property
(itself a snapshot masquerading as a live mapping — writes through it are silently discarded, a
documented past bug); per-iteration frozenset unions in the RD parser's argument loops; `KeyDecoder`
pops from a list head per keystroke.

**Miscellaneous verified MEDs worth their own lines.** `note_stdin`'s unguarded low-slot `os.dup(0)`
violates the subsystem's own backup doctrine (`exec 0<&-; read x < f` → spurious EBADF where bash
reads the file; `manager.py:228`); `output_close_fd` recognizes only the `>&-` spelling so `1<&-`
leaks buffered builtin output into the restored fd (`manager.py:351`); the builtin `<` path opens
the target twice with independent offsets against the output half's own documented rule (latent —
the input resolver currently prefers fd 0; `manager.py:554`); mock-defensive `hasattr`/`try-except`
guards in production navigation/print/signal code; `SignalManager` docstring claims interactive-only
while half the class is process-wide policy called from the executor; the untyped CLI-options blob
forcing three casts, two shims, and an 11-positional-arg (8 boolean) ShellState call; `--metrics`
double-counts backticks; evaluator round-trips AST→string→re-parse while CLAUDE.md claims "nothing
is re-parsed at runtime" (and the verifier proved bare-identifier resolution *re-$-expands stored
values* against the package's never-rescan invariant — plus an unguarded evaluator recursion on
25k-term flat chains that falsifies the documented RecursionError narrative); `ForLoop`/`SelectLoop`
still store `items`+`item_words` dual truth (verifier: so do CasePattern/CaseConditional/
ArrayInitialization — the doctrine's remaining stragglers); the root-repo `conftest.py` carries a
shadowed `shell` fixture re-teaching the retired wait-based teardown.

### LOW (215 — sample)

Stale "priority" docstrings in three lexer recognizers (the mechanism was removed); a per-token
`sorted()` of three constant keys; `case_sensitive` config knob never set False anywhere; dead
FI/DONE/ESAC branch in the keyword normalizer; `parse_statement` annotated `Optional` but never
returning None; 72 legacy `ParseResult(success=...)` sites vs the discriminated constructors in only
2 of 12 modules; sexp renderer silently mapping any non-`&&` operator to `||`; `psh/parser/__init__`
importing three names it neither uses nor exports; tilde local variable shadowing the `pwd` module;
`echo` leftover debug scaffolding; `dirs` validating the same index twice with two different errors;
`umask`'s set/restore dance duplicated; `TokenFormatter` a class wrapping one staticmethod; committed
6-byte junk file `test_` at the repo root (flagged independently by two scopes); MANIFEST.in
referencing two nonexistent files; `pytest.ini` `addopts -v` making every gate phase verbose;
marker registration split across three sources of truth; `docs/keyword_helper_cookbook.md`
recommending production-dead helpers.

---

## Cross-package twin ledger

Duplication that structurally evades per-scope review (nearly all surfaced in verifier missed-lists
or the crosscut scope). These need a named owner because no subsystem sees the whole pair:

| Twin | Sites | Status |
|------|-------|--------|
| ANSI-C `$'...'` encoders | `utils/escapes.py:148`, `:188`, `visitor/formatter_quoting.py:123` | **Diverged, output-visible** (3 different renderings of `$'\x01\x1b'`) |
| `is_inside_expansion` | `lexer/pure_helpers.py:596` (dead) vs `utils/heredoc_detection.py:185` (live) | Same name, different semantics |
| Heredoc delimiter unquoting | `heredoc_lexer.py:211`, `cmdsub_scanner.py:124`, `heredoc_detection.py:40` | **Drifted** (verifier probe: bash sides with the oracle against the lexer) |
| `+=` append engine | `core/variable_store.py:109` vs `core/assignment_utils.py:96` (3 caller families) | Textually drifted, behaviorally converged — for now |
| Inherited-traps exemptions | `core/state.py:497` vs `core/trap_manager.py:288` | **Diverged** (functrace DEBUG traps) |
| Child exit-status taxonomy | 5 fork sites | **Diverged** (`SystemExit(None)`: 1 vs 0) |
| lex→parse pipeline | accumulator / source_processor / visitor_modes | **Drifted** (analysis copy ignores `--parser`) |
| PATH walk | `CommandResolver.search_path` vs `source_command.py:137` (vs hash builtin) | Diverged empty-component semantics |
| bash oracle resolution | `conformance_framework.find_bash()` vs `test_golden_behavior._run_bash` | Diverged (BASH_PATH/Homebrew vs bare PATH) |
| `shell` pytest fixture | root `conftest.py:80` (shadowed, wait-teardown) vs `tests/conftest.py:110` | Root copy re-teaches the retired policy |
| Assignment predicates | 3 visitors + canonical `SHELL_NAME` | Diverged (one accepts hyphens) |
| 'Useless cat' check | validator vs linter | Validator copy misfires (H13) |

## Themes

1. **Registries with drift-lock meta-tests hold; prose contracts drift.** Everything auditors praised
   as accurate is machine-guarded (option registry, computed specials, env materializer, ast_nodes
   metadata, visitor totality matrix, conformance claims). Every "MUST agree" / "single chokepoint" /
   "the ONE message shape" / "every PATH scan uses search_path" prose invariant was found violated
   somewhere. The prescription is not more discipline; it is extending the project's own proven
   pattern to the chokepoints currently held together by comments.
2. **The twin-path defect factory is now the tree-wide binding constraint on elegance.** 11 of 19
   auditor HIGHs are divergent-duplicate findings; all 16 scopes reported at least one. Elegance is
   the only axis below A-range anywhere, and twins are most of why.
3. **Dead API accretes because refactor waves ship replacements without deletions — and unit tests
   keep corpses warm.** ~25% of the 362 findings are dead/vestigial/ghost surface; several items have
   outlived two prior review flags. "Referenced only by its own tests" must count as dead.
4. **Docs that quote code rot; docs that state invariants survive.** 8 of 9 subsystem CLAUDE.mds
   drifted, ARCHITECTURE.md teaches four retired designs, and in every case the worst rot is an
   embedded code sketch. The accurate CLAUDE.md (visitor's) is the one that quotes a 62-line file
   verbatim and pins the rest with a meta-tested matrix.
5. **Re-deriving from strings what an earlier stage knew structurally is the shared shape of every
   live behavioral defect found this round** (H1–H4, plus the evaluator round-trips). This is the
   class the v0.120 Word-AST migration eliminated for command arguments; these are its stragglers
   and should be campaigned as one class.
6. **Analysis/diagnostic sidecars run a full grade below the execution path because they have no
   oracle and almost no tests.** Seven verified false-positive/no-op advisories, silently-wrong DOT
   diagrams, a no-op compact renderer, a born-vacuous meta-guard. Either harness them like the
   execution path (goldens, strict-errors, self-tests) or delete them — the current middle path
   produces confidently wrong output under flags that advertise rigor (`--security`, `--lint`).
7. **Efficiency is a solved culture.** The two historical quadratic cliffs are not just fixed but
   documented as design narratives (`build_assignment_prefix_map`, `pattern_engine`); new findings
   are per-prompt/per-keystroke churn and one bounded accumulator quadratic. No new cliff was found
   by any of 32 agents.

## Recommended next tier

**Tier 1 — HIGH, roughly file-disjoint campaign clusters** (each ends with bash-verified pins per
the standard workflow):

1. **String-rederivation class:** H1 procsub node-carry (`io_redirect/process_sub.py`,
   `file_redirect.py`) + H2 quote-aware heredoc detection (`utils/heredoc_detection.py`) + H3
   newline-safe regex adaptation (`expansion/extglob.py`, `parameter_expansion.py`) + H4 Token leak
   (`executor/array.py`, both parsers). Four live-behavior fixes, one theme.
2. **Core mutation authority:** H7 create_local readonly guard + H8 single append engine + H9 one
   inherited-traps helper (`core/scope.py`, `variable_store.py`, `trap_manager.py`, `state.py`).
3. **Builtins convergence:** H5 local→declaration_engine + H6 parse_flags migration + PWD-updater
   unification (`builtins/shell_state.py`, `function_support.py`, `read_builtin.py`,
   `directory_stack.py`, `navigation.py`).
4. **Executor chokepoints:** H10 `map_child_exception` + H19 assignment-contract wording sweep
   (7 sites) + CLAUDE.md strategy-order fix.
5. **Parser guard:** H12 route function bodies through `_parse_compound_component`; delete
   `parse_control_structure` (`parser/recursive_descent/parsers/functions.py`).
6. **Scripting:** H11 one `lex_and_parse()` helper across the three copies.
7. **Analysis-sidecar fork:** fix-or-delete decision for the seven false-positive advisories
   (H13/H14 + the five MED-graded ones), visualization repairs (H15 dataclass-fields walk, H16
   classmethod render, H17 ghost-token deletion + `token()` validation, H18 shelfware pruning).
8. **Meta/doc integrity:** H21 keyword-guard fix + self-test; H20 ARCHITECTURE.md rewrite of the
   four retired-design sections; root-conftest fixture deletion.
9. **Interactive:** H22 expand_history forward-scan decomposition.

**Tier 2 — MED clusters:** the dead-API deletion sweep under the "test-only = dead" policy (biggest
single win, ~90 items, mostly mechanical); CLAUDE.md sync ×8 with snippet drift-locks; the help-text
oracle (registry-derived synopses or drift meta-test); ANSI-C encoder unification (one encoder in
`utils/escapes.py`, bash-verified); strict-errors border repairs (arithmetic cant-happen re-typing,
visitor_modes defect pass-through, read dialect, UnclosedQuoteError rooting); import hygiene (two
cycles, TokenFormatter relocation, lazy-import hoist with cycle-breaker comments, engine renames for
the AST/engine name collisions); lexer triplication pair (quote-lexing helper, heredoc-delimiter
unquote helper — the drifted one first); expansion twins (substitution-loop merge, subscript helper,
`expand_array_to_list` retirement); arithmetic maximal-munch table + LValue reification; core scope
enumeration walk + temp-env binder merge; io_redirect message-chokepoint adoption + open-flags
table + `<&-` spelling + note_stdin high-slot dup; builtins test/[ tables + read twins + banner
renderer + source PATH-walk delegation; interactive prompt thunks + `state.variables` snapshot
rename; efficiency nits (accumulator caching or documented bound, case-mod predicate compile,
frozenset hoists); tests-infra consolidation (conformance conftest, fixture ratchet, capsys ratchet,
golden-oracle unification, PTY harness convergence, compare-bash banner computed at runtime); mypy
global `check_untyped_defs=true`; the monolith blind spots (`set_variable`, `execute_function_call`)
get a read.

**Explicitly not prescribed:** micro-optimizations anywhere; unification of the three
command-position tracking machines (the lexer's non-unification essay is *correct* and exemplary);
deduplication of the five escape dialects (escapes.py's "do NOT deduplicate" analysis stands);
combinator-parser productionization (educational scope is documented and appropriate — it needs
deletion of fiction, not feature work).

## Coverage & method summary

33 agents (16 auditors + 16 adversarial verifiers + 1 completeness critic), ~3.0M tokens, 855 tool
invocations, all reads from the pinned snapshot at `8a622ff8`. Scope tiling verified by the critic:
all 255 `psh/**/*.py` files map to exactly one scope except the two trivial top-level modules
(`__init__.py` 6 lines, `version.py` 18). Whole-tree metrics (AST-measured): 70,133 LOC, 2,865
functions, 94 >80 lines (3.3%), 25 modules >600 lines, module-docstring coverage 255/255 = 100%.
Verification: every HIGH/MED re-read at the cited line by an independent agent instructed to refute;
dead-code claims re-grepped against dynamic dispatch (visit_* names, builtin registries, getattr);
live probes run from the snapshot for every behavioral claim (H1, H2, H3, H7, H13, H14, the ANSI-C
three-way divergence, the depth-guard bypass, and others). Verdict distribution — 203 CONFIRMED /
18 ADJUSTED / 0 REFUTED — with all 18 adjustments incorporated above.

**Known coverage gaps (deliberate):** the ~105-file `docs/` prose tree beyond ARCHITECTURE.md and the
nine subsystem CLAUDE.mds was not audited (the largest remaining hole — given that 8 of 9 audited
CLAUDE.mds had drifted, the user guide and architecture tour deserve their own round);
`.github/workflows/` (the release-gate machinery itself); `examples/`; `tools/`; the *content* of
~620 ordinary test files (tests-infra graded infrastructure only); `tests/parser_differential/` and
`tests/performance/benchmarks/` harness internals. Per-subsystem prose reports with verification
addenda: `tmp/appraisal-r19-reports/`.
