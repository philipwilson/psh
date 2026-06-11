# Ground-Up Reappraisal #2 — 2026-06-11 (v0.287.0)

> **⚡ STATUS (2026-06-11, as of v0.298.0) — PROGRAM COMPLETE.** All three
> tiers of §7 shipped across 11 releases, all as GitHub PRs:
> **Tier A** v0.288.0–v0.290.0 (PRs #19–#21): process-sub fd/zombie
> reaping (H1, plus two latent bugs the same design fixed); behavior batch
> (M1, M2, M4, M5); run_tests.py 45-test hole (H2) + user-guide truth
> sweep (H3 — 17 false claims fixed, 23 conformance tests added).
> **Tier B** v0.291.0–v0.296.0 (PRs #22–#27): alias rewrite + printf \e;
> exec single-open + noclobber + dual-universe docs; keyword
> case-sensitivity (M6); error channels (job notices→stderr); PTY
> framework prompt-sync off-by-one fixed (M8 — tier green); one slice
> engine (M10, 4 copies→1, 8 bash divergences fixed) + arithmetic
> double-expansion deleted + v0.286 prune finished.
> **Tier C** v0.297.0–v0.298.0 (PRs #28–#29): 47-file archive sweep +
> guide banners; CLAUDE.md/ARCHITECTURE fix-in-place + M7 documented.
> Suite at close: 4,608 passed / 4,878 collected; ruff + mypy in CI.
> Known leftovers (small, found during the program): sparse array literal
> `b=([2]=x [5]=y)` doesn't parse; `}` reserved-word rc divergence
> (`:; }` → psh 127 vs bash 2).

**Scope:** full re-review of every major subsystem, the test framework, and all
documentation, one day after the first reappraisal program
(`ground_up_reappraisal_2026-06-10.md`) closed with v0.287.0.

**Method:** six parallel review agents (lexer/parser, executor/io_redirect,
expansion/core, builtins/interactive/visitor, test suite, documentation), each
required to verify every claim with file:line evidence, grep for callers before
declaring code dead, and probe behavior against bash 5.2. The two
highest-severity new findings were independently re-verified by the
orchestrator (the process-substitution zombie leak reproduces: three `<defunct>`
children after three `cat <(echo x)` commands; the `run_tests.py` exclusions
are exactly as described at `run_tests.py:212-216` / `:265-269`).

**Baseline:** main @ 26988de, v0.287.0. 192 source files, 47,177 LOC.
Suite: 4,310 passed / 269 skipped / 1 xfailed of 4,625 collected, ~60 s
parallel wall, zero failures. `ruff` and `mypy` clean and CI-enforced.

---

## 1. Scorecard

| Subsystem | 2026-06-10 | Now | Direction |
|---|---|---|---|
| Parser (recursive descent) | A− | **A** | ↑ dead machinery pruned; residue is trivia |
| Executor (incl. job control) | B+ | **A−** | ↑ single fork path, signal-race fix is teaching-grade |
| Core | B+ | **A−** | ↑ rename done, exception root real, mypy-clean |
| Interactive | B+ | **A−** | ↑ all five ranked findings resolved or settled |
| Visitor | (light) | **A−** | solid; doc nits only |
| ast_nodes.py | (flagged) | **A−** | legacy fields fenced with named consumers |
| Test framework | B+ | **A−** | ↑ structural debt gone; two holes found (§5) |
| Lexer | B− | **B+** | ↑ all five findings addressed, −588 lines |
| Expansion | B− | **B+** | ↑ facade + one pattern engine; parsing still tripled |
| Builtins | B− | **B+** | ↑ 8/10 sampled error cases now match bash exactly |
| Parser (combinator) | B− | **B** | ↑ drift fixed and pinned; still not combinator-style |
| io_redirect | B+ | **B** | ↓ untouched by the program; new high-sev leak found |
| Documentation | C | **B** | ↑ everything swept is accurate; docs/guides+architecture mass unswept |

The program demonstrably worked: ten of thirteen grades rose. The two
non-risers are exactly the areas the thirteen releases didn't touch
(io_redirect code, the docs/guides + docs/architecture mass) — and one of them
was hiding a real correctness bug.

---

## 2. High-severity findings (new)

### H1 — Process substitutions leak fds and zombies for the life of the session
`IOManager.cleanup_process_substitutions` (`psh/io_redirect/manager.py:316`)
has **zero callers**; `shell._process_sub_fds` / `_process_sub_pids` are
written (`psh/expansion/manager.py:70-71`) but never read. After an external
command uses `<(...)`/`>(...)`, the parent-side fds stay open and the children
are never reaped — cleanup happens only as a side effect of the *next
builtin's* `restore_builtin_redirections`. Verified: three
`cat <(echo x) >/dev/null` commands leave three `<defunct>` children and fds
3–7 open. Bash reaps these. The dead method is the fossil of an
intended-but-missing executor call. The io_redirect CLAUDE.md's own pitfall #7
("must wait for process substitution PIDs to prevent zombies") is currently
aspirational.

### H2 — `run_tests.py` silently never runs 45 tests, including in CI
`run_tests.py:212-216` excludes the whole of
`tests/integration/functions/test_function_advanced.py` and
`tests/integration/variables/test_variable_assignment.py` from Phases 1/1b in
every smart mode; Phase 3 (`:265-269`) re-runs only **2** named tests from
them. The other 45 are executed by nothing — CI runs `--quick`, so they're
invisible there too. The carve-out is obsolete: both files pass under normal
capture today (45 passed, 1 xfailed, 1 xpassed in 1.8 s), consistent with the
v0.195.0 subshell fd fix. Fix: drop the two ignores and Phase 3 entirely.

### H3 — `docs/user_guide/` asserts features are "not supported" that work
Verified by execution: `!` pipeline negation (`10_pipelines_and_lists.md:416`),
`|&` (`:418`), `exec 3<> file` (`09_io_redirection.md:459`), `>|` (`:716`),
bitwise assignment ops (`07_arithmetic.md:331`), and `BASH_REMATCH` groups
(`16_advanced_features.md:259`) all work in v0.287.0 but are documented as
unsupported. 23 limitation notes are pinned to "PSH v0.187.1" (100 releases
ago) and `docs/user_guide/README.md:48` claims v0.187.1/~93%. The
conformance meta-test polices only the ch17 compatibility table (which IS
current) — not these inline notes. This is the highest-stakes doc rot because
the user guide is the conformance anchor.

---

## 3. Medium-severity findings (new)

| # | Finding | Evidence |
|---|---|---|
| M1 | Associative-array keys containing `,` or `^` fail to expand: `declare -A a; a[x,y]=hi; echo "${a[x,y]}"` → bash `hi`, psh empty. The case-modification exclusion at `psh/expansion/variable.py:66-68` misroutes the subscript. | probe |
| M2 | `command -v` doesn't find shell functions (bash prints the name, rc 0; psh rc 1) and `command_builtin.py:106` hardcodes the prefix `bash: type:` — wrong shell *and* wrong command name. | `psh/builtins/command_builtin.py:81-107` |
| M3 | `alias` is the one builtin the v0.284 sweep never reached: no `-p`, options treated as names (rc 1 instead of bash's rc 2), raw `print` + hasattr dance, and a post-tokenization cross-argument quote-rejoin scanner that is conceptually wrong teaching code. | `psh/builtins/aliases.py:27-80` |
| M4 | Four dead `set -o` options accepted silently and advertised in `set` help — `validate-context`, `validate-semantics`, `analyze-semantics`, `enhanced-error-recovery` — zero consumers; orphaned by the v0.286 parser pruning. | `psh/core/state.py:87-90`, `psh/builtins/environment.py:473-476` |
| M5 | In-pipeline command-not-found prints a raw Python OSError (`psh: nosuchcmd: [Errno 2] ...`) instead of "command not found", because the inline-exec branch lacks the fork path's FileNotFoundError/127 handling. | `psh/executor/strategies.py:390-392` vs `:426-435` |
| M6 | Keyword matching is case-insensitive — `IF true; then echo y; fi` runs in psh, is a syntax error in bash. Undocumented divergence; the lexer's worst remaining defect. | `psh/lexer/keyword_normalizer.py:41`, `keyword_defs.py:49,59` |
| M7 | `$(case x in x) ...;; esac)` is a parse error in both parsers (bash accepts): `find_balanced_parentheses` counts parens instead of recursively lexing. Not documented as a known limitation. | `psh/lexer/expansion_parser.py:111` |
| M8 | The opt-in PTY test tier is rotting: 6 reproducible failures in `tests/system/interactive/test_interactive_features.py` (fragile raw-PTY output parsing, not product bugs); nothing runs `--run-interactive` in CI so decay is invisible. The newer `test_pty_smoke.py` (34 tests) passes. | agent run |
| M9 | `docs/guides/` + `docs/architecture/` (~70 files) describe pre-v0.275 architecture — 11 non-archive docs reference module paths deleted by the v0.285 relocation; `parser_architecture.md`/`parser_api.md` document `validation.py`/`ParserFactory` removed in v0.256; `docs/posix/posix_compliance_summary.md` is pinned to v0.57.3/"~93-95%". No historical markers. | §6 archive plan |
| M10 | Slice-operand parsing is still tripled with subtly different edge handling (`operators.py:40-64`, `:178-205`, `fields.py:108-151`); `${...}` is still parsed in three places (147-line `parse_expansion`). The prior memo's one structural expansion finding that remains. | `psh/expansion/` |

---

## 4. Low-severity findings (selected; full lists in agent reports)

- **Executor:** job state notifications (`[1]+ Done ...`) go to stdout; bash
  uses stderr (`job_control.py:226,284,511` — the launch notice at `:275` is
  already correct). `_visitor` backchannel survives (`core.py:83`).
  `ExternalExecutionStrategy.execute` is still two programs in one 123-line
  function; `_execute_pipeline` still 158 lines. `TestExpressionEvaluator`
  name risks pytest collection. Dangling `'SignalManager'` forward ref in
  `process_launcher.py:80` will bite when executor joins the mypy scope.
- **io_redirect (all carried over, untouched since the first memo):**
  120-line dual-universe `setup_builtin_redirections`; triple-open in
  `apply_permanent_redirections` (`file_redirect.py:318-367` — `exec &>file`
  in `w` mode gives stdout/stderr separate offsets that overwrite each other);
  IOManager↔FileRedirector underscore-private cross-class contract; hidden
  `_saved_fds_list` accumulator.
- **Lexer:** ~12 lines of error-recovery config remnants contradict
  `ParserConfig`'s "only fields actually read" docstring
  (`parser/config.py:21,40`, `context.py:140-150`); `DOUBLE_QUOTE_ESCAPES`
  dead-by-shadowing (`pure_helpers.py:250-256`); `process_sub.py:63-99` still
  hand-rolls quote scanning; `tokenize`/`tokenize_with_heredocs` duplicate the
  post-lex pipeline; two "Phase 3" codenames remain.
- **Expansion:** the two arithmetic pre-expansion scanners
  (`manager.py:703-811`) were never rebased on `_expand_one_dollar`;
  `manager.py` (811), `brace_expansion.py` (844), `arithmetic.py` (1,116
  — cohesive, reads as a textbook chapter) exceed 800 lines; escaped-`!`
  strip duplicated ×4 without explanation.
- **Core:** `MinimalShell` near-dead fallback with stale comment
  (`scope.py:346-388`); stdio properties still say "for test compatibility"
  with `hasattr` idiom (`state.py:179-215`); `$*` joined with hardcoded space
  in `state.get_special_variable` (`state.py:309-310`) vs the IFS-aware
  separator in `variable.py:112-113` — two sources of truth for special vars.
- **Builtins:** error-channel stragglers in `command_builtin.py`,
  `aliases.py`, `function_support.py:116-140`, `read_builtin.py:57,127`,
  `environment.py:430`; `unset` help omits `-v/-n`; `_declare_variables` is
  170 lines.
- **Interactive:** `line_editor.py:200` calls nonexistent
  `self.terminal.restore()` on the EIO path (masked by the `with` block);
  `_update_context_stack` still 172 lines; `tab_completion.py:5` docstring
  cites the pre-v0.285 path; `line_editor.py` at 1,061 lines is the only
  \>800 file in its scope.
- **Tests:** one stale XPASS (`test_function_with_background_job`); nested
  `tests/system/interactive/pytest.ini` hijacks rootdir and its skip-comment
  is stale; tracked generated JSON under
  `tests/conformance/conformance_results/`; empty `tests/integration/lexer/`;
  untracked husk dirs `contract_tests_draft/`, `test_invalid/`;
  `test_migration.yml` filename is a historical misnomer.
- **Combinator parser:** control structures remain 100–161-line imperative
  token-slicers with hand-rolled nesting counters and no rationale for not
  using the package's own primitives; message style never standardized.

**Disproved-before-claiming this round** (the verify-first rule keeps paying):
`handle_ansi_c_escape` looked caller-less but is live via
`handle_escape_sequence`; `ErrorContext.suggestions` re-confirmed live;
`is_array_expansion`/`expand_array_to_list`/`UnboundVariableError` all have
real callers; `env` builtin's child-Shell design is now documented rationale,
not a smell.

---

## 5. Test framework health (B+ → A−)

- **Run:** zero failures across all phases; ~60 s parallel wall. 269 skips all
  attributable to two documented opt-in gates (149 `--compare-bash`, ~93+27
  PTY/terminal). Conformance: POSIX 100.0% (162/162), bash 99.0% (200/202),
  meta-test enforcing 38 user-guide claims via 39 mapped tests — all green.
- **All seven 2026-06-10 findings resolved** except the Phase-3 hardcoding,
  which turned out to be worse than reported (H2).
- **Coverage by subsystem:** expansion and builtins strong; parser/lexer/
  executor adequate; interactive transformed (76 always-on unit tests) but
  still the weakest always-on coverage; visitor/core thin in isolation but
  ubiquitously exercised.
- CI matches the documented gate (`ruff` + `mypy` + `--quick` + conformance
  smoke) — modulo the H2 hole, which CI inherits.

---

## 6. Documentation (C → B) and the archive plan

**Accurate (verified claim-by-claim):** README.md, ARCHITECTURE.md,
ARCHITECTURE.llm, root CLAUDE.md, and all nine subsystem CLAUDE.mds in
substance — the v0.278/v0.285/v0.286 sweeps held up. Specific small defects
to fix: executor CLAUDE.md (4: phantom `builtin_base` import, pipefail
"first failure" wording, member-setpgid description, missing `job_control.py`
row), lexer CLAUDE.md (4: phantom `_tokenize_next`, wrong recognizer
registration site, phantom keyword-recognizer priority, constants.py claim),
visitor CLAUDE.md (nonexistent test file cited; `traversal.py` and
`analysis_helpers.py` missing from its table — the one CLAUDE.md never
refreshed), README internal counts (4,550/220/185 → 4,625/223/192),
ARCHITECTURE.md:1082 "4,550+".

**Archive plan (move to `docs/archive/`, no content changes):**
1. `docs/LEXER_DIFFERENCES.md`, `docs/MODULAR_LEXER_GUIDE.md` (document the
   long-deleted StateMachineLexer), `docs/parser_combinator_guide.md`
   (superseded by `docs/guides/combinator_parser_guide.md`).
2. `docs/architecture/` — all except `lexer_architecture.md`,
   `recursive_descent_refactoring_status.md`,
   `bash_vs_psh_lexer_comparison.md` (~30 files of completed plans,
   phase-summaries, and docs for removed subsystems).
3. `docs/posix/` — all except `posix_spec_reference.md` (4 v0.57-era files).
4. `docs/guides/` point-in-time reviews (~10 files: `*_code_quality_review*`,
   `*_implementation_review*`, `parser_feature_gap_analysis.md`, …) →
   `docs/reviews/` or archive.

**Fix in place:** user-guide chapters 7/9/10/11/16 + README.md:48 (H3);
`docs/subsystem_internals.md:426` path; the remaining `docs/guides/*_guide.md`
+ `*_public_api*.md` either get the v0.285 paths batch-fixed or a dated
"describes the tree as of v0.27x" banner.

**Fine as-is:** `docs/reviews/`, user-guide ch 1/4/17/18,
`docs/testing_source_of_truth.md`, `docs/test_pattern_guide.md`,
`docs/keyword_helper_cookbook.md`, `docs/archive/`.

---

## 7. Recommended program

Smaller than last time — the structure is sound; this is correctness residue
plus an archival sweep.

### Tier A — correctness (user-visible bugs and the test hole)
1. **Process-substitution reaping** (H1): wire or replace the dead
   `cleanup_process_substitutions` after external commands; delete the dead
   shell attributes or make them the mechanism.
2. **run_tests.py 45-test hole** (H2): drop the two file ignores and Phase 3.
   Also remove the stale XPASS while in there.
3. **User-guide false claims** (H3): fix the six confirmed-false "not
   supported" notes, replace v0.187.1 pins, update README.md:48.
4. **`command -v` functions + wrong prefix** (M2).
5. **Assoc-array keys with `,`/`^`** (M1).
6. **In-pipeline command-not-found message** (M5) — share the fork path's
   error handling; opportunity to split the two-program `execute` (low-risk
   half of the prior finding).
7. **Dead `set -o` options** (M4): delete from state + help.

### Tier B — consistency and structure
1. `alias` rewrite to conventions (`-p`, rc 2 on bad options, `write_line`,
   delete the quote-rejoin scanner) (M3).
2. io_redirect: fix the permanent-redirection triple-open via `os.fdopen`
   (the `>&` branch already shows the pattern); decide on the
   builtin-redirection dual universe (fix or document as design).
3. Keyword case-sensitivity (M6): match bash (likely a one-line
   `lower()` removal + test sweep) or document the divergence.
4. Job-state notifications → stderr; error-channel stragglers (builtins +
   arithmetic errors in control_flow.py).
5. PTY tier triage (M8): port the 6 failing tests to the smoke-test framework
   or xfail with references; delete the nested pytest.ini (N3).
6. Finish the v0.286 prune: error-recovery config remnants,
   `DOUBLE_QUOTE_ESCAPES`, "Phase 3" codenames, `terminal.restore()` call.
7. Expansion: unify slice-operand parsing (M10, the highest-value remaining
   dedup); rebase the two arithmetic pre-expansion scanners on
   `_expand_one_dollar`.

### Tier C — documentation and archival
1. Execute the §6 archive plan (~45 file moves, content untouched).
2. Fix-in-place list: subsystem_internals path, the 8–10 CLAUDE.md defects,
   README/ARCHITECTURE count reconciliation, guides banner-or-fix decision.
3. `$(case ...)` limitation (M7): document as known limitation (a recursive-
   lexing fix is real work; the documentation is the Tier C part).

Items explicitly **not** recommended: rewriting the combinator control
structures as combinators (the honest-experiment framing now does its job);
splitting `arithmetic.py` (cohesive, reads as a chapter); further `state.py`
stdio surgery beyond renaming the misleading docstrings.
