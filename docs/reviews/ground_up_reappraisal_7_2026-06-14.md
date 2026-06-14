# Ground-Up Reappraisal #7 — Textbook Grade Scorecard

Date: 2026-06-14 (at v0.388.0)

Method: five parallel fresh-read assessments (one per subsystem cluster),
graded against the same textbook rubric, each required to confirm any suspected
behavior bug against real bash before reporting it. Taken immediately after the
Tier R6 bug-fix campaign (v0.378–v0.388) cleared the reappraisal #6 list.

## Scorecard

| Cluster | #6 | #7 | Movement |
|---------|----|----|----------|
| Lexer / Parser / AST | A− | **A−** | held (R6 fixes confirmed; fresh probes found new edge bugs) |
| Expansion | A− | **A−** | held (architecture textbook; new operator/feature bugs) |
| Executor / io_redirect | A− | **A−** | held (R6 fixes confirmed clean; one new data-integrity bug) |
| Core / Builtins | B+ | **A−** | ↑ R6 cleared the read/declare bug density; now held by dynamic-var bugs |
| Interactive / Scripting / Visitor / Tooling | A− | **A−** | held, on the cusp of A |

**Overall: A− — stable and broad.** The R6 campaign's fixes all verified clean
with no regressions, and Core/Builtins was promoted B+→A−. The grade is steady
rather than rising because deeper fresh-eyes probing surfaced a NEW batch of
bash divergences (every cluster is "textbook architecture, bug list is what
holds A"). mypy scope is still ~85/222 files (~38%); the structural items from
#6 (lexer/parser untyped, expansion mixins, `_run_command` size) are unchanged.

## Confirmed NEW bugs (bash-verified; not in the #6 list) — priority work

### HIGH (orchestrator-reconfirmed)
- **H1 keyword-as-argument parse error.** `echo if then` → bash `if then`, psh
  **parse error**. Also `echo if fi`, `echo while do done`, `cat -- if then`.
  Root: `lexer/keyword_normalizer.py:_next_command_position` keeps "command
  position" whenever a WORD's *value* is `if`/`while`/`until`, so the next word
  is wrongly promoted to a keyword token. (Lexer)
- **H2 `${var#pat}` shortest-prefix removal is GREEDY with extglob.** `shopt -s
  extglob; v=ooo; echo ${v#+(o)}` → bash `oo`, psh empty. Root:
  `parameter_expansion.py:remove_shortest_prefix` does a naive
  `regex.replace('.*','.*?')` and uses a `$`-anchored extglob regex, so `#`
  behaves like `##`. The suffix path iterates positions and is correct — copy
  it. (Expansion)
- **H3 namerefs don't dereference on ARRAY reads.** `declare -a arr=(10 20 30);
  declare -n r=arr; echo "${r[@]}"` → bash `10 20 30`, psh `arr`. `${r[i]}`,
  `${#r[@]}`, `${!r[@]}` all broken; writes already deref. Root:
  `expansion/arrays.py` calls `get_variable_object(name)` which by contract does
  not follow namerefs (the scalar path does). (Expansion + Core)
- **H4 `psh script.sh` honors the script's shebang instead of treating it as a
  comment.** A `#!/usr/bin/python3` script run as `psh file` is re-dispatched to
  python3 (→ SyntaxError); bash/sh/dash treat `#!` as a comment. Root:
  `scripting/script_executor.py` calls `ShebangHandler` on the explicit-`psh
  FILE` path — wrong; the shebang is the kernel's exec mechanism, already
  handled. The dispatch (untested, security-sensitive) should be deleted.
  (Scripting)
- **H5 prefix assignment not exported to an external command IN A PIPELINE.**
  `FOO=bar env | grep ^FOO` → bash `FOO=bar`, psh empty. Single-command
  `FOO=bar env` works; only the pipeline-member path drops the temp env.
  (Executor/pipeline)

### MEDIUM
- **M1 in-process builtin ignores a closed output fd; data leaks.** `echo hi
  1>&-` → bash empty (write error), psh prints the write-error message BUT also
  leaks `hi` to real stdout (the builtin writes via `sys.stdout`, still bound;
  `>&-` only closed the fd). Affects builtin + function paths. (io_redirect)
- **M2 `"${!prefix@}"` does not field-split** — `x1=a x2=b; printf "[%s]"
  "${!x@}"` → bash `[x1][x2]`, psh `[x1 x2]`. Quoted `@`-form must yield one
  field per name. (Expansion)
- **M3 `~+` / `~-` / `~N` unimplemented and half-expand** — `echo ~+` → psh
  `/Users/pwilson+` (expands `~` then appends `+`); bash `$PWD`. (Expansion)
- **M4 `kill -l N` / `kill -l NAME` broken/reversed** — `kill -l 9` → bash
  `KILL`, psh "Exit status 9 not from signal"; `kill -l KILL` → bash `9`, psh
  error. (Builtins)
- **M5 `kill -l` / `trap -l` listings garbled** — `kill -l` omits SIGEMT(7)/
  SIGINFO(29) (`7) 7`); `trap -l` lexically sorts a map with pseudo-signals +
  duplicates. Both maintain their own signal tables instead of `signal.Signals`.
  (Builtins/Core)
- **M6 `SECONDS=N` assignment ignored** — read-only computed interceptor with no
  write path (`scope.py`). (Core)
- **M7 `RANDOM=N` doesn't seed** — same root cause as M6. (Core)
- **M8 `$'a\x00b'` NUL doesn't terminate the string** — bash truncates at NUL;
  psh keeps `a\0b`. Sibling of the deferred byte-vs-codepoint M7-from-#6; fold
  into that fix. (Lexer)
- **M9 `!!:-n` history word designator aborts the command** — `!!:-2` (the
  `0-n` abbreviation) → "bad word specifier" + exit 1; a gap in the v0.388 L10
  work. (Interactive)

### LOW
- **L1 unclosed quote exits 1 ("unexpected error") not 2 ("syntax error").**
  `UnclosedQuoteError(SyntaxError)` isn't a `ParseError`, so it routes to the
  generic handler. (Lexer/scripting)
- **L2 empty `()` subshell and `{ }` brace group accepted silently** (bash:
  syntax error exit 2). (Parser)
- **L3 empty redirect target → doubled message** `psh: No such file or
  directory: No such file or directory` (empty-filename sub-case of the recorded
  ambiguous-redirect issue, surfaced by the L2 fix). (io_redirect)
- **L4 `${var@K}` / `@k` transforms unimplemented** (silent no-op). (Expansion)
- **L5 `read -N count` unimplemented** (only `-n`). (Builtins)
- **L6 `set +o history` rejected** (bash accepts). (Builtins)
- **L7 validator false positives** — array assignments (`x=(1 2)` then `${x[@]}`
  → "undefined variable"), C-style `for ((i=0;...))`, and `$((...))`
  misclassified as variable expansion. (Visitor)

## Top quality issues (cross-cluster, ranked)

1. **Finish mypy coverage** (unchanged from #6, now with detail): lexer/ and
   parser/ entirely out (~16k lines; would likely have caught H1 at type-check);
   executor/ and io_redirect/ entirely out (`planner.py`, `child_policy.py`,
   `process_launcher.py` are small/annotated/low-risk first targets); the
   `arithmetic/` subpackage is self-contained with NO mixin problem — a cheap
   independent win; the four expansion mixins need a `VariableExpanderProtocol`;
   `interactive/line_editor.py` + `utils/signal_utils.py` have 11 real errors
   (the last interactive gap); `core/` is in scope but `check_untyped_defs=false`
   so method bodies aren't checked.
2. **Single source of truth for signal name↔number** — `kill -l` and `trap -l`
   keep separate, incomplete tables (root of M4/M5); use `signal.Signals`.
3. **Dynamic-variable write paths** — SECONDS/RANDOM are read interceptors with
   no setter (M6/M7); needs a small "settable computed var" abstraction.
4. **Nameref-aware array lookup helper** — every `arrays.py` access site must
   remember to resolve namerefs; three forgot (H3). One helper makes it an
   invariant.
5. **`command.py::_run_command` ~124 lines**; pipeline child mutates
   `visitor.context`; `_decide_redirection_mode` reads `state.in_forked_child`
   not the passed context. (all #6, unchanged)
6. **Small duplications** — special-var classification ×2; two paren scanners;
   `operands.py` 3 near-identical scan loops; the expansion error-emit triad ×5
   (a `self._fail()` helper); dead `build_word_from_string`;
   `_reparent_to_package` `__module__` mutation.
7. **Redirect-error wording** — centralize through one bash-shaped formatter
   (`psh: TARGET: STRERROR`), fixing L3 + the noclobber/order divergences.

## Bottom line

The R6 campaign held: every fix verified clean, no regressions, and
Core/Builtins climbed to A−. psh is a stable, broad A− across all five clusters
— the architecture is textbook and the bash-fidelity surface is very wide. What
remains is, again, a concrete bash-verified bug list (5 HIGH / 9 MEDIUM / 7 LOW)
plus the half-finished mypy lever. Recommended "Tier R7": fix worst-first (H1
keyword-as-arg, H2 shortest-prefix extglob, H3 nameref arrays, H4 shebang
deletion, H5 pipeline prefix-env), then the MEDIUMs, each bash-probe-pinned;
and in parallel keep growing mypy scope (arithmetic subpackage and the small
executor modules are the cheap independent wins). The two byte-model items
(deferred M7-from-#6 and M8 here) should be done together as the dedicated
surrogateescape change.
