# PSH Codebase Study (2026-06-05)

> **Resolution status (updated 2026-06-05, through v0.197.0).** Most of this
> study has since been acted on:
> - **Phase 1 correctness:** all 23 confirmed bugs fixed (v0.193.0–v0.196.0).
> - **Phase 2 architecture:** the two biggest duplication hazards collapsed —
>   parameter-expansion dual application paths (v0.196.0) and brace expansion
>   relocated off the raw line (v0.196.0); the dormant parser-validation
>   subsystem removed (v0.197.0, ~1300 LOC); redirect-dispatch predicates
>   de-duplicated; and the flagged exception-boundary "swallowing" sites fixed.
> - **Phase 3 coverage:** the `read` fd fix retired the global `-s` test flag
>   (v0.195.0).
>
> Remaining open Phase 2 items include the 3× lexer quote scanners and the
> larger visitor-analysis overlap. See each phase report for per-finding status.

Repository: `/Users/pwilson/src/psh`
Scope (per request): **correctness/POSIX-bash conformance**, **architecture & code
quality**, **test coverage & quality**. Performance and docs are secondary.

This study extends — and re-validates — the prior
`docs/reviews/codebase_recommendations_2026-02-17.md` (which is itself untracked /
never committed).

---

## Phase 0 — Baseline (complete)

### Project scale
- ~48,200 lines of Python across **184 source files**, 11 subsystems under `psh/`.
- **155 test files**; full suite: **3110 passed, 309 skipped, 2 xfailed, 0 failed** (~3m18s).
- Largest modules (refactor candidates): `line_editor.py` (1302), `arithmetic.py`
  (986), `lexer/recognizers/literal.py` (910), `expansion/variable.py` (905),
  `builtins/function_support.py` (822), `brace_expansion.py` (784), `builtins/io.py`
  (778), `parser/combinators/special_commands.py` (704).

### Conformance baseline (framework: 238 curated tests)
- **POSIX compliance: 100.0% (127/127)**
- **Bash compatibility: 98.2% (109/111)**
- Overall: 230 identical (96.6%), 6 documented differences (2.5%), 2 psh extensions.
- Caveat: this is a *curated* suite, not exhaustive — 100% here ≠ full POSIX. Phase 1
  must probe beyond it.

### Test coverage baseline
- **Overall: 67%** (24,206 statements, 8,043 missed) via `pytest --cov=psh`.
- Caveat: this run was without `-s`, so 1 subshell test failed and subshell/process
  code paths are under-counted (3202 passed, 1 failed, 310 skipped, 5 xfailed).
- **Near-zero coverage — auxiliary/tooling** (lower priority): `__main__.py` (0%),
  `parser/visualization/sexp_renderer.py` (0%), `utils/ast_debug.py` (5%),
  `visitor/metrics_visitor.py` (14%), `visitor/debug_ast_visitor.py` (17%),
  `visitor/security_visitor.py` (18%), `utils/shell_formatter.py` (23%),
  `builtins/{help_command,parser_control,debug_control,parse_tree}.py` (16–28%).
- **Low coverage — runtime-relevant (Phase 3 priorities):**
  `io_redirect/process_sub.py` **19%** (process substitution is a real feature),
  `scripting/shebang_handler.py` **14%**, `interactive/signal_manager.py` **24%**.

### Skip inventory (309 runtime skips)
Static categorization of skip reasons — the large majority are **legitimately
environment-bound**:
- PTY / line-editor escape sequences (6+), `pexpect` not installed (4), tab
  completion needs raw terminal (3), job-control terminal handling, Unix
  signals/permissions, zsh not installed (1, from the new print suite).
- **Rotting / feature-gap skips to flag** (not environmental):
  - "Advanced parameter expansion not fully implemented yet"
  - "Background subshells not fully implemented"
  - "Line editing may not be fully supported yet"
- 36 `@pytest.mark.skip`/`pytest.skip` + 32 `xfail` markers total.

---

## Re-validation of the 2026-02-17 recommendations

| # | Recommendation | Status (2026-06-05) | Evidence |
|---|----------------|---------------------|----------|
| 1 | Parser `source_text` plumbing bug | **STILL OPEN (confirmed bug)** | `parser/__init__.py:88` `return Parser(tokens, config=config)` drops the `source_text` param accepted at `:54`; RD parser supports it (`recursive_descent/parser.py:86,105`). |
| 2 | Replace string-matching parse heuristics with error codes | **STILL OPEN** | `scripting/source_processor.py:168` `_is_incomplete_command` matches lexer text patterns (`:173-180`); `error_code` infra exists but unused here. |
| 3 | Remove silent expansion fallback | **PARTIALLY ADDRESSED** | `expansion/manager.py` now re-raises `ExpansionError`/`UnboundVariableError` and narrows the catch to `(ValueError, AttributeError, TypeError)`, but still `return str(expansion)` as a silent fallback. |
| 4 | Tighten broad exception boundaries | **STILL OPEN** | 21 `except Exception` in `psh/`; hot paths `executor/command.py:183`, `scripting/source_processor.py:381` remain. |
| 5 | Clean up I/O redirection layering | **STILL OPEN** | `io_redirect/manager.py` calls 8+ private `file_redirector._*` methods (`:72,99,104,109,114,128,198,213`). |
| 6 | Reduce orchestration complexity in largest modules | **STILL OPEN** | `line_editor.py` 1302L still largest; `shell.py`, `source_processor.py` broad. |
| 7 | Close active runtime TODOs | **STILL OPEN** | All 3 present and are the *only* TODOs in the codebase: `word_builder.py:288`, `job_control.py:31`, `type_builtin.py:90`. |
| 8 | Dev ergonomics / determinism | **STILL OPEN** | `run_tests.py:156` uses `['python', ...]` not `sys.executable`; `ruff` still absent from `pyproject.toml` dev extras (only `pytest`, `pytest-cov`) despite CI + `[tool.ruff]` config. |
| 9 | Resolve documentation status drift | **STILL OPEN** | `docs/improvement_recommendations.md:5` claims **51.9% (28/54)** POSIX while actual conformance is **100% POSIX / 96.6% identical** and README says ~98%. The 51.9% is stale (old 54-test methodology). |
| 10 | Add combinator-parser CI smoke lane | **STILL OPEN** | `.github/workflows/` (`test_migration.yml`, `claude.yml`) has no combinator/`--parser` lane. |

**Headline:** 8 of 10 prior items are fully open, 1 partially addressed (#3), 0 fully
resolved. The prior review was never committed, so its findings haven't been actioned.

---

## Phases 1–3 (complete — multi-agent workflow, 108 agents)

Full findings are in three companion reports; headlines and verification below.

### Phase 1 — Correctness & conformance → [`..._phase1_correctness.md`](codebase_study_2026-06-05_phase1_correctness.md)
Probed **beyond** the curated 238-test suite. **23 confirmed bugs** (8 high / 9
medium / 6 low) + 1 undocumented-intentional + 4 documented-as-designed. Several
contradict the user guide's own "full support" claims. Key clusters: variable values
not recursively evaluated as arithmetic; non-colon parameter operators (`${x-}`,
`${x+}`, `${x?}`) unimplemented; brace expansion runs pre-tokenization (corrupts
assignment RHS, re-lex crashes); glob delegates blindly to Python `glob.glob()`
(`[^...]`, POSIX classes, nocaseglob, globstar all broken); for-loop has a divergent
splitting/glob path; fd≥3 redirection broken for both builtins and externals;
here-string with a bareword operand silently discards the whole command line.

### Phase 2 — Architecture & code quality → [`..._phase2_architecture.md`](codebase_study_2026-06-05_phase2_architecture.md)
11 subsystems audited; ~75 findings in 7 cross-cutting themes: private-API leakage
(~15 sites), broad/silent exception handling (~16 sites), divergent duplication (dual
expansion engines, 3× lexer quote scanners, 4× redirect dispatch, diverged heredoc
detectors), dead/dormant subsystems (~1311 LOC parser validation, vestigial readline
path, dead HeredocHandler), oversized modules, bare `print()` bypassing `shell.stdout`
in 5 builtins, and layering inversions. Confirms 2 of the prior review's open items
(the two `except Exception` sites); the rest are new.

### Phase 3 — Test coverage & quality → [`..._phase3_coverage.md`](codebase_study_2026-06-05_phase3_coverage.md)
Runtime-critical coverage holes: `process_sub.py` (19%), `shebang_handler.py` (14%),
`signal_manager.py` (24%). Skip/xfail triage finds rotting "not implemented" labels on
features that now work (history, completion, background subshell, heredoc-in-function).
**Key result:** the global subshell `-s` workaround is **obsolete** — the suite passes
without `-s` except one test; root cause is `read_builtin.py:379-409` consulting
`sys.stdin` instead of the real redirected fd 0. 7 claimed-but-untested conformance
gaps (getopts, `=~`/BASH_REMATCH, `case ;&`/`;;&`, set -x, wait, trap, pipeline isolation).

## Verification of workflow findings
Independently reproduced (not just trusting the agents):
- **Phase 1:** 9/9 spot-checked high-severity bugs reproduce exactly vs bash (#1, #4,
  #5, #8, #11, #13, #18, #32, #33).
- **Phase 2:** confirmed bare `print()` in `debug_control.py` (15 calls, 0 `shell.stdout`),
  `registry.py:88` swallowing recognizer errors, `eval_test_mode` in production
  `pipeline.py:107`, and the `print_builtin.py:93` private-API leak (self-introduced).
- **Phase 3:** subshell suite without `-s` = exactly "1 failed, 47 passed" with the
  predicted `read`/stdin failure; stale background-subshell case works as claimed.

Note: the Phase 1 synthesis deduped 80 raw `real-bug` verdicts (overlapping across the
10 probe areas) into 23 distinct confirmed bugs — the 23 figure is authoritative.
