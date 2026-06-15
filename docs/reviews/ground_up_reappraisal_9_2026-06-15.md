# Ground-Up Reappraisal #9 — psh v0.437.0 (2026-06-15)

Run via 10 parallel subsystem reviewers (read-only), synthesized here.
Baseline: reappraisal #8 (`ground_up_reappraisal_2026-06-15.md`, v0.423.0, overall
**A−**) followed by the full Tier R9 program (v0.424–437: dead-code sweep,
ShellState decomposition started, combinator parser elevated, expansion files
split, builtins `parse_flags` convergence, executor seam fixes).

## Overall grade: **A−**, trending A

Functionally healthy, 100% mypy *file* coverage, ruff clean, near-zero TODO
debt, versions in sync, strong meta-test scaffolding. Half the subsystems are
now solidly **A**; the rest are **A−** with clear, bounded paths up. Tier R9
delivered real, verifiable improvements with no regressions. What keeps the
overall grade at A− is a small set of concrete items — including two genuine
**behavior bugs** the reviewers surfaced — plus the still-rolling
`check_untyped_defs` and ShellState-decomposition themes.

## Subsystem scorecard (vs #8)

| Subsystem | #8 | #9 | Movement |
|-----------|----|----|----------|
| Lexer | A | **A** | held; dead `Token` methods gone |
| RD parser | A− | **A−** | held |
| Combinator parser | B | **B** | bodies fixed (C3) but condition-headers still slice |
| Executor | A | **A** | D6 backchannel removed; resolver/invoker split clean |
| Expansion | A | **A−** | ↓ a latent `\$` bug is now demonstrated, not assumed-benign |
| Core/State | A− | **A−** | TerminalState/HistoryState/StreamBindings extracted; ShellState still ~36 attrs |
| Builtins | A− | **A−** | D1 convergence good; one raw-print fd bug found |
| I/O Redirect | A | **A** | D6 procsub dedup landed; minor dispatch duplication |
| Visitor | A− | **A−** | B3 migration done; left an unused helper API |
| Interactive | A | **A** | now 100% in mypy `files`; one dead class |
| Scripting | A | **A−** | dead `InputSource` subclass + write-only field |
| Cross-cutting | A− | **A−** | mypy file-complete; 3 pkgs lack check_untyped_defs |

## HIGH findings (genuine bugs / top value)

- **H1 — Expansion: string-context `\$` escape diverges from bash (real bug).**
  `variable.py:_process_double_quote_escape` keeps the backslash on `\$` unless
  it shields a variable; the Word-path processor always drops it (bash-correct).
  Probes: `cat <<< "a\$ b"` → bash `a$ b`, psh `a\$ b` (also `"a\$.b"`, `"a\$"`).
  Affects heredocs/here-strings/redirect-targets/`[[ ]]`/array subscripts. The
  "PS1 compatibility" justification is **stale** — PS1 routes through
  `interactive/prompt.py`, not `expand_string_variables` (zero callers). Fix:
  always drop `\$` (match the Word path). This is the real content of the
  deferred "D2" item — not "differ by design," but "the string-context one is
  buggy." Bash-probe + conformance test. Effort ~1–2h.
- **H2 — Builtins: `history`/`version` use raw `print(file=shell.stdout)`**
  (`shell_state.py:49,81,85`), bypassing the v0.284 forked-child-aware
  `self.write_line()`. In a forked child (`history | cat`, `version &`) these
  write to the Python stream, not fd 1, so fd-level redirections misbehave —
  the exact bug the helpers exist to prevent. Drop-in fix. Effort ~15m.
- **H3 (combinator only, "educational") — condition-header slicing breaks the
  command-position keyword rule.** while/until/if conditions still collect
  tokens to the first `do`/`then` regardless of position:
  `while echo do; false; do echo body; done` fails under `--parser combinator`
  but works under RD and bash. This is the unfinished tail of C3: parse the
  condition with `build_statement_list(frozenset({'do'/'then'}))` exactly as
  bodies now do, deleting 4 collector loops. Correctness debt, not a release
  blocker (combinator is "educational only" per parser/CLAUDE.md). Effort ~M.

## MED findings (structure / consistency)

- **M1 — Core: extract an `ExecutionState` sub-object from ShellState.** The
  most cohesive remaining cluster (`last_exit_code`, `last_bg_pid`,
  `foreground_pgid`, `command_number`, `pipestatus`, `errexit_eligible`,
  `last_cmdsub_status`, `in_forked_child`) — all per-command executor scratch.
  Follows the proven TerminalState/HistoryState pattern; shrinks the ~36-attr
  god-object and tidies `adopt()`. (CallContext = function_stack+source_depth and
  ProcessIdentity = shell_pid+initial_ppid are smaller follow-ons.) Effort ~1d.
- **M2 — Cross-cutting: extend `check_untyped_defs` to the next package.**
  Done for core/expansion/executor. Next: **`psh.io_redirect.*`** (smallest
  surface; only `manager.py` flags 26 `annotation-unchecked` notes), then
  `psh.utils.*`, then `psh.visitor.*`. The clearest A−→A lever.
- **M3 — Combinator: dedup the three near-identical loop parsers** (while/until
  line-for-line duplicates; for partly) via `_build_keyword_loop(kw, node_cls)`,
  and collapse the 3 copies of `set_command_parser`/`parse_and_or_list` +
  the compound-isinstance tuple in `commands.py`. ~75+ lines. Effort ~M.
- **M4 — Builtins: `function_support.py:_declare_variables` is ~195 lines** —
  the longest method in the codebase; extract per-flag / array-vs-scalar
  helpers. Effort 1–2h (declare has many bash corners).
- **M5 — Executor: the `pending_array_inits` shell slot** (`shell.py:178-213`,
  `command.py:367-381`) is the last executor↔shell value-passing channel that
  isn't an arg/return. Thread it through the strategy `execute()` signature or a
  builtin-invocation record. Effort ~M.
- **M6 — Visitor: 8 unused `word_analysis` public helpers** (tested but no
  production caller) — delete or document as intended library API. Effort ~1h.
- **M7 — I/O Redirect: `apply_permanent_redirections` re-implements its own
  per-type dispatch** instead of the `plan.target_fd` pattern the other 3
  dispatch sites share; two small mirror-duplications (`_swap_closed_output_streams`
  vs `_builtin_redirect_close`). Effort ~1h.

## LOW findings (polish)

- **Docs**: `docs/subsystem_internals.md:527` still lists the removed
  `AliasExecutionStrategy` (v0.417) as a live 5th strategy — most stale doc found.
  README line-7 "8,035" vs line-245 "8,028" test counts disagree (within meta
  tolerance but should match).
- **Lexer**: duplicated quote-toggle loops (the `QuoteState` helper exists but is
  underused); vestigial `is_inside_expansion`/single-paren `find_balanced_parentheses`;
  unreachable `position` backward-reset branch; possibly-dead `TokenType.COMPOSITE`.
- **Scripting/Interactive**: dead `InteractiveInput` class (`input_sources.py:145`);
  write-only `_last_hint` (`command_accumulator.py`); fragile string-equality
  AST-reuse guard (`source_processor.py:182`); add interactive/scripting to
  `check_untyped_defs` (likely near-zero fallout — both fully annotated).
- **Builtins**: `echo`'s private `_parse_flags` is a legit exception but
  undocumented (unlike kill/read); stale `'0.54.0'` fallback in help.
- **Visitor/Security**: `'-rf' in ' '.join(args)` substring check is fragile;
  inline command/perm lists duplicated across 3 visitors vs `constants.py`.
- **Core**: `options` is a 40-key stringly-typed dict (a `ShellOptions`
  dataclass/TypedDict would type it); `edit_mode` duplicates `options['emacs'/'vi']`.

## Proposed Tier R10 roadmap

- **R10.A — the two real bugs first** (highest value, small): H1 (`\$` escape) +
  H2 (raw-print fd bug). Bash-probe + conformance/regression tests.
- **R10.B — typing rollout**: M2 — `check_untyped_defs` for `io_redirect`, then
  `utils`, then `visitor`/`interactive`/`scripting` (one release each).
- **R10.C — ShellState decomposition**: M1 ExecutionState extraction (+ smaller
  CallContext/ProcessIdentity follow-ons).
- **R10.D — consistency/dedup polish**: M3 (combinator loop dedup), M4 (declare
  split), M5 (pending_array_inits), M6 (visitor dead API), M7 (redirect
  dispatch), and the LOW doc/lexer/scripting items batched.
- **R10.E (optional) — finish combinator C3**: H3 condition-header recursion
  (educational-grade; nice for completeness/parity, not production-critical).

Recommended order: R10.A (bugs) → R10.B (typing) → R10.C → R10.D → R10.E.
