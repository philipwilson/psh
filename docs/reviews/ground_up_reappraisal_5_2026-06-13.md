# Ground-Up Reappraisal #5 — Textbook Grade Scorecard

Date: 2026-06-13

Method: five parallel fresh-read assessments (one per subsystem cluster),
each grading against a strict **textbook** rubric — small & readable, single
source of truth, narrow interfaces, abstractions that match the problem,
invariants explicit-and-enforced (not "carefully preserved quirks"), and
tests that prove behavior. Each agent read the current tree with fresh eyes
(recent review docs available only as context). This memo synthesizes them
and defines the path to the textbook grade.

## Scorecard

| Cluster | Grade | One-line verdict |
|---------|-------|------------------|
| Lexer / Parser / AST | **B+** | Two jewels (cmdsub scanner = A, AST single-source lockdown); held back by triplicated expansion-delimiter stripping, half-Word `[[ ]]` operands, one pinned latent bug, 766-line `ast_nodes.py` |
| Expansion | **A−** | Policy table + `ExpandedSegment` IR + single `${...}` parser + arithmetic package are textbook; debt is two dense methods and the un-refactored 844-line `brace_expansion.py` |
| Executor / io_redirect | **B+** | `command_assignments`, `child_policy`, the io two-universe frame model are textbook; held back by inline redirection-mode policy, the 140-line `_execute_command` hub, the `_pending_array_inits` side channel, runtime alias reparse |
| Core / Builtins | **B+** | `core/` state model is textbook (single-source ownership, observer-wired sync, clean error taxonomy); `builtins/` solid but ~half hand-roll option parsing despite a shared `parse_flags`, plus oversized multi-builtin files |
| Interactive / Scripting / Visitor / Tooling | **A−** | The strongest cluster: pure-where-possible editor, real completeness oracle, thin `shell.py` facade, and a meta-test layer that prevents staleness; only ~10% of code is in mypy scope |

**Overall: B+ / A− — "production-minded, approaching textbook."** psh is
functionally healthy (7,007 tests green) and several subsystems genuinely
reach the bar. The gap to a clean textbook grade is **concentrated and
addressable**: a handful of dense methods/files, a few inline policies that
want to be tables/objects, two shared-mutable side channels, and — the single
biggest lever — type-checking coverage at ~10%.

## Cross-cutting themes (what recurs across clusters)

1. **A few big methods/files remain "not small"** — `_execute_command` (140-line
   method), `expand_parameter_direct` array branch (~80 lines), `ast_nodes.py`
   (766), `brace_expansion.py` (844), `environment.py`/`function_support.py`
   (~670 each), `read_builtin.py` (576), two analysis visitors (~610-662).
2. **Inline policy that should be a table/object** — redirection-mode selection
   inline in `_execute_with_strategy`; builtin option parsing hand-rolled in
   ~half the builtins despite the shared `parse_flags`.
3. **Shared-mutable side channels** — `shell._pending_array_inits`; the pipeline
   child repointing `visitor.context`.
4. **Type-checking coverage ~10%** (mypy `files` ≈ 21 of 213). A textbook
   codebase type-checks the bulk of itself; many already-annotated modules
   (line_editor, scripting, visitor/base) are low-risk to add.
5. **Small duplication clusters** — expansion-delimiter stripping in 3 places;
   glob detection in 2; special-var classification in 2-3.
6. **A few honest pins / deferrals** — the separate-bracket array latent bug;
   `[[ ]]` operands only half-Word; runtime alias reparse; the `tests.yml`
   in-tree-vs-disabled drift.

## Roadmap to textbook (prioritized; each item tagged + rough effort)

### Tier T1 — cheap, high-value, low-risk (the fast textbook lift)
- **T1.1 Grow mypy scope** toward already-annotated modules: `interactive/
  line_editor.py`, all of `scripting/`, `visitor/base.py`+`traversal.py`, then
  outward. *(tooling; biggest single textbook lever; ~1-2h per module, mostly
  already typed.)*
- **T1.2 Extract redirection-mode policy** from `_execute_with_strategy` into a
  named `RedirectionMode` decision + single dispatch. *(zero-change; ~1-2h.)*
- **T1.3 Migrate pure-flag builtins to `parse_flags`** (readonly, command,
  disown, help, shell_options). *(zero-change; ~½ day.)*
- **T1.4 Unify the 3 expansion-delimiter-stripping copies** into one WordBuilder
  helper; route the second WordBuilder method + the combinator through it.
  *(zero-change; ~½ day.)*
- **T1.5 Tooling honesty** — make `tests.yml` reflect its disabled state in-tree
  (gate on `workflow_dispatch`, or a header comment) so the file matches the
  README. *(tooling; ~30m.)*
- **T1.6 Replace raw `print(..., file=shell.std*)`** in `navigation.py`/
  `positional.py` with base-class helpers; add a grep guard. *(behavior-fix,
  small; cd/`cd -` echo has real pipeline exposure; ~1-2h.)*

### Tier T2 — medium (decompose the dense hubs)
- **T2.1 Decompose `_execute_command`** into `_run_pure_assignment` +
  `_run_command` under a thin coordinator. *(zero-change; ~½ day.)*
- **T2.2 Extract `expand_parameter_direct`'s array branch** + lift the
  `expand_string_variables` escape loop into named helpers. *(zero-change; ~½ day.)*
- **T2.3 Split `ast_nodes.py` into a package** (expansions/words/commands/
  control/tests + flat re-export). *(zero-change; ~½ day.)*
- **T2.4 Split `environment.py`** — extract `EnvBuiltin` (+ its fd-binding
  helpers, really an io concern) into its own module. *(low-risk; ~½ day.)*
- **T2.5 Unify glob detection** through one `GlobExpander` entry point.
  *(zero-change; ~1-2h.)*
- **T2.6 Make `_pending_array_inits` an explicit parameter** to declaration
  builtins (behind a small `BuiltinInvocation`/adapter). *(touches builtin
  plumbing; ~½ day.)*
- **T2.7 Shared `_visit_redirects` mixin** for analysis visitors (closes the
  redirect-loss hazard structurally; shrinks the two largest visitors).
  *(zero-change; ~2-3h.)*

### Tier T3 — larger / behavior (finish the model)
- **T3.1 Finish `[[ ]]` Word adoption** — real multi-part operand Words; delete
  the `right_quote_type` sentinel; evaluator reads part quoting. *(behavior-fix;
  bash probe battery; ~1-2 days.)*
- **T3.2 Fix + delete the pinned separate-bracket array bug** (`a [ 0 ] = v` →
  match bash command-not-found; remove ~55 lines of error-preserving machinery).
  *(behavior-fix; ~½ day.)*
- **T3.3 `brace_expansion.py` IR-style pass** — bring the one un-refactored
  844-line file up to the package's altitude. *(large; ~1 day.)*
- **T3.4 Alias expansion at parse time** (or cache the parsed AST) — removes the
  runtime reparse + the injection-class metacharacter bug. *(large/risky;
  entangled with psh's deliberate non-interactive alias-expansion divergence.)*
- **T3.5 Trim `ShellState` god-object tendency** — document/extract the
  non-variable fields (history, editor, terminal). *(large, low priority.)*

## Bottom line

The functional health is real and the architecture is serious. To earn the
textbook grade the work is NOT a rewrite — it is: type-check the bulk (T1.1),
turn the last few inline policies into tables/objects (T1.2-T1.4, T2.6),
decompose the four or five dense hubs (T2.1-T2.4), and close the handful of
honest pins (T3.1-T3.2). Tier T1 alone would move the two B+ clusters toward
A−. Recommend starting with T1 (highest value-per-risk), then T2.
