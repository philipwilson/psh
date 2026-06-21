# Ground-Up Appraisal — psh @ v0.514.0 (2026-06-21)

A fresh, independent code-quality + correctness review of every subsystem, graded on
two axes: **(1) correctness vs bash** and **(2) textbook-quality elegant/efficient
code** (psh is meant to be a teaching codebase). Conducted by parallel per-subsystem
auditors; every correctness finding below was pinned with a live `bash`-vs-`psh` probe
on the macOS host. Read-only — no source was modified.

> Method: bash-verification discipline throughout —
> `b=$(bash -c "$cmd" 2>&1; echo rc=$?); p=$(python -m psh -c "$cmd" 2>&1; echo rc=$?)`.
> Cosmetic-only diffs (the `psh:` vs `bash: line N:` error prefix, error-message
> wording with matching exit codes) are excluded as intentional/known throughout.

---

## Overall verdict

**Correctness: B+ / A−.**  **Elegance: A−.**

psh remains an exceptional teaching artifact: the recognizer-registry lexer, the
fork/signal-policy executor, the Word-AST + derived-property design, the v0.508
option-registry and v0.512 RedirectPlan refactors are all at or near textbook
quality. But this round — like every prior reappraisal — found that yield is
**non-diminishing**: a genuine cluster of **11 HIGH-severity correctness bugs**
surfaced, several in everyday idioms, two of them serious (an empty-loop-body
**infinite hang** where bash gives a parse error, and silent corruption of `$`
expansions inside `(( ))`). The elegance findings are concentrated and almost all
take the form "two code paths for one job, one of them subtly wrong" — which is
exactly where the correctness bugs live.

### Per-subsystem grades

| Subsystem | Correctness | Elegance | Headline issue |
|-----------|:-----------:|:--------:|----------------|
| Lexer | A− | A− | heredoc delimiter with `$` truncated (MED); 3 expansion-extent scanners |
| Parser | B+ | A− | **empty compound bodies accepted → `while true; do done` HANGS (HIGH)** |
| Expansion | A− | A | **embedded extglob `!(...)` negation per-char not per-span (HIGH)** |
| Arithmetic (lexer↔parser seam) | B | — | **`$1`/`${#a[@]}` corrupted inside `(( ))` & C-for (HIGH)** |
| Executor | A− | A | **`break`/`return` leak across function & pipeline-subshell boundary (HIGH×2)** |
| I/O redirect | A− | A− | explicit-fd heredoc self-closes on fd collision (MED) |
| Core/State | A | A | only `[[ < ]]` locale collation (LOW) — essentially clean |
| Builtins | B+ | A− | **`readonly -a`/`export -f` rejected (HIGH×2)** |
| Interactive | B | A− | **rc sourced in `-c`/script under tty; stopped job loses `%+` (HIGH×2)** |
| Visitor / `--format` | B | B+ | **4 lossy `--format` defects + analysis modes crash on syntax error (HIGH)** |
| AST design | — | A | exemplary; minor string-field leakage (case subject, arith expr) |

---

## HIGH-severity correctness findings (11)

### H1. Empty compound-command bodies silently accepted; `while true; do done` HANGS — Parser
bash rejects an empty body/condition at **parse time**; psh accepts it, and when the
loop condition is true the empty body becomes an **infinite loop**.

```
$ python -m psh -c 'while true; do done'     # → HANGS (bash: syntax error, rc=2)
$ python -m psh -c 'until false; do done'    # → HANGS
$ python -m psh -c 'if true; then fi'        # → rc 0   (bash: rc 2)
$ python -m psh -c 'for i in 1 2; do done'   # → rc 0   (bash: rc 2)
$ python -m psh -c 'f() { }; echo done'      # → "done" (bash: rc 2)
$ python -m psh -c 'echo a; ; echo b'        # → a,b    (bash: syntax error)
```
**Root cause:** `parse_command_list_until()`
(`psh/parser/recursive_descent/parsers/statements.py:69-85`) returns an empty
`CommandList` when the first token is already the terminator, and no required-body
caller checks for emptiness (`control_structures.py` `_parse_loop_structure:165`,
`_parse_condition_then_block:120/124`, `parse_for_statement:215`,
`parse_select_statement:457`; `functions.py:75-87` re-implements brace parsing
**without** the empty-body guard that `CommandParser.parse_brace_group` already has at
`commands.py:512-514`). The **combinator parser rejects all of these correctly** — this
is a recursive-descent-only bug. The parity corpus
(`tests/parser_differential/test_combinator_error_parity.py`) only has the
semicolon forms (`do; done`), never the no-separator `do done`, which is why it was
missed.
**Fix direction:** add an opt-in "non-empty required" check at the
`parse_command_list_until` call sites for required-body positions; route function
braces through the guarded `parse_brace_group`; extend `REJECTION_CORPUS` with the
no-semicolon forms.

### H2. `$`-prefixed expansions silently corrupted inside `(( ))` / C-style `for` / `while (( ))` — Arithmetic (lexer↔parser seam)
The arithmetic **command/loop** forms lose the `$` on every expansion token, so
positional params, `$#`, `${#var}`, `${#arr[@]}`, and `$`-subscripts are mis-parsed —
often silently.

```
$ set -- 5;     (( $1 == 5 ))            && echo Y || echo N   # bash: Y   psh: N
$ arr=(a b c);  (( ${#arr[@]} > 0 ))     && echo y || echo n   # bash: y   psh: ((: Unexpected character '{'
$ for ((i=0;i<${#arr[@]};i++)); do :; done                     # bash: 3 iters  psh: parse error, 0 iters
$ declare -A c; w=foo; ((c[$w]++)); echo "${!c[@]}"            # bash: foo  psh: w   (wrong key)
$ s=hello;      (( ${#s} == 5 ))         && echo five          # bash: five  psh: parse error
```
**Root cause:** `collect_arithmetic_expression`
(`psh/lexer/token_stream.py:254-263`) rebuilds the expression string from raw
`token.value`, which for a `VARIABLE` token omits the leading `$` (and the `${`/`}`):
`$1`→`1`, `$#`→`#`, `${#arr[@]}`→`{#arr[@]}`. The string is frozen on the
`ArithmeticEvaluation` node before evaluation, so the `$` is gone permanently. The
`$(( ))` **expansion** form uses a different path and is unaffected (which hides the
bug); the **combinator parser is correct**. The exact correct reconstruction already
exists at `psh/parser/combinators/arrays.py:193`:
`f'${tok.value}' if tok.type.name == 'VARIABLE' else tok.value`.
**Blast radius:** ~12 distinct everyday idiom forms collapse to this one locus — the
single highest-value fix in this report.

### H3. `break` / `continue` inside a function leaks into the CALLER's loop — Executor
A function called from inside a loop inherits the caller's `loop_depth`, so a
`break`/`continue` in the function body (POSIX: a no-op error) terminates the
**caller's** loop.
```
$ f() { break; }; for i in 1 2 3; do echo $i; f; echo "after $i"; done; echo end
# bash: 1, <break-not-meaningful error>, after 1, 2, after 2, 3, after 3, end
# psh : 1, end          ← caller loop aborted by the function's break
```
**Root cause:** `execute_function_call`
(`psh/executor/function.py:50`) saves/restores `current_function` and
`positional_params` but never resets `context.loop_depth` to 0 around the body.
**Fix direction:** save `loop_depth`, set 0 before `visit(func_body)`, restore in
`finally` — symmetric with the existing `current_function` handling.

### H4. `return` / out-of-scope `break N` in a pipelined compound prints spurious `psh: error:` and wrong status — Executor
```
$ f() { echo a | while read x; do return 5; done; echo "after=$?"; }; f
# bash:  after=5            psh: "psh: error:" (empty msg) then after=1
$ for i in 1 2; do echo x | while read y; do break 2; done; echo i=$i; done
# bash:  i=1 i=2            psh: "psh: error:" before each line
```
**Root cause:** the forked pipeline child (`pipeline.py:160`) doesn't catch
`FunctionReturn`/`LoopBreak`/`LoopContinue`; they reach
`process_launcher.py:253` `except Exception` → prints `psh: error: {e}`
(FunctionReturn stringifies empty) and forces exit 1. The plain-subshell path
`( … )` is correct because it runs a fresh visitor with `loop_depth=0` — the
**asymmetry between the two subshell-entry paths** (`pipeline.py` reuses the parent
visitor via `fork_context()`; `subshell.py` builds a fresh `Shell`) is the shared
root of H3/H4 and an elegance smell (see E-Exec).
**Fix direction:** catch `FunctionReturn`→`exit_code` and `LoopBreak/Continue`→0 in
the pipeline child; unify the scope-reset into one "enter new shell execution scope"
helper used by function calls, pipeline children, and subshells.

### H5. Embedded extglob `!(...)` negation matches per-character, not per-span — Expansion
`!(P)` embedded in a larger pattern over-rejects. One root, wide blast radius
(`case`, `[[ == ]]`, `${v#pat}`/`${v/pat/r}`, and pathname globbing all funnel
through it).
```
$ shopt -s extglob
$ [[ xfoox == x!(o)x ]]        && echo y   # bash: y   psh: (no match)
$ case xfoox in x!(o)x) echo m;; esac      # bash: m   psh: (nothing)
$ s=xfooy; echo "${s/x!(o)y/_}"            # bash: _   psh: xfooy
$ echo !(foo).txt   # bash includes xfoox.txt; psh drops any name containing f/o/o
```
**Root cause:** `psh/expansion/extglob.py:182` emits a per-char negative lookahead
`(?:(?!(?:alt).*).)*` for the embedded case; bash's semantics are span-level ("the
whole consumed span ≠ the alternative"). The standalone top-level `!(P)` is correctly
special-cased (match-and-invert), which is why casual use looks fine. The existing
test `test_extglob.py:227` is a false-positive (its candidate happens to contain no
char starting the negated alternative).
**Fix direction:** generalize the existing standalone match-and-invert approach
(`parameter_expansion.py:_standalone_negation_inner`) to the embedded case instead of
the inline per-char regex.

### H6. `readonly -a` / `readonly -A` rejected — Builtins
```
$ readonly -a arr=(1 2 3); echo "${arr[@]}"   # bash: 1 2 3   psh: readonly: invalid option: -a
$ readonly -A m=([k]=v)                        # bash: ok      psh: invalid option: -A
```
**Root cause:** `ReadonlyBuiltin._parse_readonly_options`
(`psh/builtins/function_support.py:693-721`) hand-rolls a subset parser accepting
only `-f`/`-p`, even though it delegates to `declare -r`, which handles `-a`/`-A`.

### H7. `export -f funcname` rejected — Builtins
```
$ myfn() { echo hi; }; export -f myfn; echo rc=$?   # bash: rc=0   psh: export: -f: invalid option (rc 2)
```
**Root cause:** `ExportBuiltin.execute_in_context`
(`psh/builtins/environment.py:48-56`) rejects any flag other than `-p`/`-n`.
> H6 + H7 share a root with elegance finding E-Builtins: three divergent declaration-flag
> parsers, two of them silently incomplete.

### H8. `~/.pshrc` sourced in `-c` and script-file mode when stdin is a tty — Interactive
bash never sources rc for `-c`/script files; psh does whenever stdin is a terminal
(the normal interactive case), polluting every `psh -c`/`psh script.sh` with the
user's aliases/functions/exports.
**Root cause:** `Shell.__init__` runs `_init_interactive`
(`psh/shell.py:191-223`) at construction, gating rc-load on
`is_interactive and not is_script_mode` — but `is_script_mode` is still `False` then
(`__main__.py` sets it for `-c` only at line 226; the script path sets it later in
`scripting/script_executor.py:36`). The test
`tests/system/initialization/test_rc_file.py:35` constructs `Shell(script_name=...)`
(which sets the flag early, a path the real entry points never take) — so it is green
while the real flow is broken.
**Fix direction:** defer the rc-load decision until after the run-mode is known, or
pass the mode into the constructor.

### H9. A foreground job stopped by Ctrl-Z is demoted out of `%+`; bare `fg`/`bg` then fail — Interactive
```
$ sleep 5            (Ctrl-Z)   → psh: "[1]-  Stopped"   (bash: "[1]+  Stopped")
$ bg                            → bg: %+: no such job    (bash: resumes [1])
$ fg                            → fg: %+: no such job
```
`fg %1`/`bg %1` (explicit spec) work; only the no-arg form / `+` marker break.
**Root cause:** on stop, cleanup calls `set_foreground_job(None)`
(`job_control.py:418`), which (lines 190-200) demotes the still-current stopped job
to `%-` and clears `%+`. bash keeps a stopped foreground job as the current job.

### H10. `--format` is still lossy in four behavior-changing ways — Visitor
(Post-v0.505; these four are distinct from the four fixed then, and unpinned by any
test.)
```
$ printf '%s' 'x=hi; echo ${x}there' | python -m psh --format   # → echo $xthere   (refs undefined var)
$ ... 'case $x in "a b") echo M;; esac'                         # → pattern a b)   (quotes dropped)
$ ... 'echo "say \"hi\""'                                        # → "say "hi""     (escaping dropped)
$ ... 'case "a b" in "a b") echo M;; esac'                      # → case a b in    (SYNTAX ERROR on re-parse)
```
**Root causes** (all `psh/visitor/formatter_visitor.py`): C1 `_format_word`
(`:128-136`) renders `$var` with no disambiguating braces before a name-continuation
literal; C2 `visit_CaseItem` (`:358`) uses the flat `p.pattern` instead of
`_format_word(p.word)`; C3 `_format_word` doesn't re-escape `"`/`` ` ``/`\` when
re-wrapping a double-quoted literal; C4 `visit_CaseConditional` (`:340`) emits the
flat `node.expr` (and the case subject has no Word to consult — see AST finding).

### H11. All five analysis modes crash with an uncaught traceback on a syntax error — Visitor
```
$ python -m psh --validate -c 'if true; then echo x'   # → full Python traceback, not a clean diagnostic
```
Affects `--validate`, `--format`, `--metrics`, `--security`, `--lint` — defeating the
whole point of `--validate`.
**Root cause:** `psh/scripting/visitor_modes.py:44` and `:61` catch only
`(ValueError, TypeError, OSError)`, but `ParseError`/`LexerError` subclass
`PshError → Exception`, not `ValueError`, so they escape. Catch the shell's
parse/lex error types and print a one-line diagnostic.

---

## MED-severity correctness findings (14)

| # | Subsystem | Finding | Locus |
|---|-----------|---------|-------|
| M1 | Lexer | heredoc delimiter containing `$`/`` ` ``/`${...}` truncated to leading token (`cat <<E$X` loses the rest → never terminates) | `heredoc_lexer.py:117-140` |
| M2 | Lexer / IO | `{varname}>file` named-fd redirection (bash 4.1+) unrecognized; `{fd}` lexes as a plain word | lexer + `io_redirect` |
| M3 | Expansion | `$[...]` (deprecated arithmetic form) passed through verbatim | lexer/parser gap |
| M4 | Executor | backgrounded pure assignment mutates the parent (`x=5 & wait; echo $x` → `5`, bash empty) | `command.py:227` |
| M5 | Executor | DEBUG trap doesn't fire before loop compound statements (`for`/`while`/`until`/`select`) | `control_flow.py` |
| M6 | IO | explicit-fd heredoc/here-string self-closes when the temp fd collides with the target fd (`cat 3<<EOF <&3` → `Bad file descriptor`); data loss | `file_redirect.py:175-182` |
| M7 | IO | builtin `>&2`/`1>&2` aliases the Python stream object instead of dup'ing the fd; a later `2>&-` breaks it (wrong rc + spurious error) | `manager.py:416-421` |
| M8 | IO | heredoc inside process substitution fails to parse (`cat <(cat <<EOF …)`) | parser/procsub boundary |
| M9 | Builtins | `read -p` writes the prompt even when stdin is not a terminal (pollutes pipelines/here-strings) | `read_builtin.py:67-70` |
| M10 | Builtins | `declare -i arr` doesn't evaluate the FIRST array-element assignment (`declare -i a; a[0]=2+3` → `2+3`) | `executor/array.py:236,334` |
| M11 | Builtins | `unset 'arr[@]'`/`'arr[*]'` removes one element instead of the whole array | `environment.py:435-468` |
| M12 | Interactive | interactive PS1/PS2 don't perform `$`/command/arith expansion (default `promptvars`) | `multiline_handler.py:83,91` (correct path `prompt_manager.py:30` is dead) |
| M13 | Interactive | `set -u` violation exits 127 in script/stdin mode (bash: 1; 127 only for `-c`); also missing `scriptname: line N:` prefix on shell errors | `command.py:478-484` |
| M14 | Interactive | `$HISTFILE` / `$HISTSIZE` ignored (hardcoded `~/.psh_history`, 1000) — and the user guide tells users to set them | `core/history_state.py:25` |

Also MED, found in the cross-cutting sweep: **`FUNCNAME[1]`** (and deeper call-stack
entries) return empty — only `FUNCNAME[0]` is populated.

## LOW-severity / known / intentional (sample)

- Lexer: ANSI-C high-byte `$'\xff'` emits UTF-8 not a raw byte; embedded NUL not
  truncated — **known, deferred M8 byte-model** (not fresh).
- Lexer: Unicode identifiers accepted (`café=5`) — **intentional** non-POSIX feature,
  but **undocumented** as a deliberate bash divergence.
- Expansion / Core: glob result order and `[[ < ]]` ignore `LC_COLLATE` — **known**,
  pinned with `LC_ALL=C`. (Note: `test_command.py:358-360`'s comment claims `[[ ]]`
  *uses* locale collation — the comment is wrong; the code uses codepoint order.)
- Executor: `return` inside `( … )` nested in a function errors (bash: still "in the
  function").
- Builtins: `echo -e "\101"` evaluates bare-octal (bash requires `\0nnn`).
- IO: duplicate `write error` line on the exotic `2>&1 1>&-`.
- Interactive: bundled `-ic` flags unsupported; trailing backslash as final byte
  (no newline) kept.
- Cross-cutting: `[[ "" =~ "" ]]` returns 0 (bash: 2, empty-regex usage error)
  — `enhanced_test_evaluator.py`.

---

## Elegance / efficiency findings (the recurring shape: "two paths, one subtly wrong")

- **E-Lexer:** `literal.py:167-314` `_collect_literal_value` is the hardest-to-teach
  code in the package (~10 interleaved special cases + duplicated word-start logic
  between `can_recognize` and `_is_word_terminator`). Three independent
  expansion-extent scanners exist (`cmdsub_scanner` — the gold standard;
  `pure_helpers.find_balanced_*`; `is_inside_expansion` — naive backtick scan,
  latent fragility). Two `can_start_expansion` definitions with the same name and
  different semantics (`expansion_parser.py:259` vs `word_scanners.py:283`). Dead
  fields: `QuoteRules.allows_nested_quotes`, the `position`-setter backward-seek
  branch, emit-dead `PARAM_EXPANSION`.
- **E-Expansion:** operator dispatch duplicated between scalar `_apply_operator`
  (`operators.py:191`) and per-element `_apply_op_per_element` (`:411`) — a new
  operator must be added twice (this is *why* H5's extglob fix must touch two paths);
  redundant double-sort of glob results (`word_expander.py:755` re-sorts already-sorted
  output). Otherwise A-grade with exemplary date-stamped quirk comments.
- **E-Exec:** two subshell-entry paths with divergent scope-reset (`pipeline.py`
  reuses parent visitor + `fork_context`; `subshell.py` builds a fresh `Shell` with
  `loop_depth=0`) — the direct cause of H3/H4; `_child_setup_and_exec`'s
  `except Exception` swallows semantic control-flow as "error"; duplicated
  background-launch boilerplate across `strategies.py`/`subshell.py`. (`child_policy.py`
  + `process_launcher.py` remain a model fork/signal chapter.)
- **E-IO:** `_content_to_fd` reinvents the existing `_dup2_preserve_target` helper
  with the **inverse (buggy) guard** — fixing E-IO and M6 together is the right move;
  `target_fd` recomputed 9× despite `RedirectPlan.target_fd` being the documented
  single source of truth; `>&-` close-stream logic duplicated
  (`manager.py:201-232` vs `:439-468`).
- **E-Builtins:** three divergent declaration-flag parsers (`declare` table-driven and
  complete; `readonly` and `export` hand-rolled subsets that are silently incomplete —
  *exactly where H6/H7 live*). `BuiltinContext` (v0.511) and the option registry
  (v0.508) are exemplary; no change recommended.
- **E-Interactive:** the correct full-expansion prompt path (`PromptManager` →
  `expand_full`) is built and wired but **dead** — the REPL renders via the escape-only
  path (root of M12); job-notification format strings hand-rolled 4× bypassing the one
  correct `Job.get_status_string()` (`job_control.py:238,288,297,534`).
- **E-Visitor:** duplicated pure-traversal `visit_*` methods in security/metrics/linter
  visitors that the shared `visit_children` default already covers (one of them,
  `security_visitor.py:258`, silently skips `item.patterns`); the formatter applies
  two word-rendering strategies inconsistently (quote-aware `_format_word` vs naive
  string interpolation) — the inconsistency *is* H10/C2.
- **E-AST:** minor string-field leakage — `CaseConditional.expr`,
  `ArithmeticEvaluation.expression`, `UnaryTestExpression.operand`,
  `CStyleForLoop.*_expr` are flat `str` while their siblings carry Words; the case
  subject having no Word is the direct cause of H10/C4. Largely defensible (documented
  as "flat text by design") but worth a cross-reference comment. The Word AST itself is
  the strongest teaching artifact in the tree.

---

## Prioritized improvement list

**Tier 1 — HIGH correctness, do first (broad blast radius, single locus each):**
1. **H2** arithmetic `$`-reconstruction (`token_stream.py:254-263`) — one-line fix,
   ~12 idiom forms; reference `combinators/arrays.py:193`.
2. **H1** empty compound bodies / `while true; do done` hang
   (`statements.py` call sites + `functions.py` braces) — a true infinite loop is the
   worst failure mode here.
3. **H5** embedded extglob negation (`extglob.py:182`) — fix via the existing
   match-and-invert path; remove the false-positive test.
4. **H3 + H4** control-flow boundary leaks — unify into one scope-reset helper
   (`function.py:50`, `pipeline.py:160`, `process_launcher.py:253`).

**Tier 2 — HIGH correctness, contained:**
5. **H6 + H7** `readonly -a/-A` and `export -f` — give the two parsers bash's accepted
   flag sets and forward to the `declare` delegation they already do (fixes E-Builtins).
6. **H8** rc sourced in `-c`/script under tty (`shell.py:191-223`) — and fix the
   false-confidence test.
7. **H9** stopped-job `%+` demotion (`job_control.py:418/190`).
8. **H10 + H11** formatter losses + analysis-mode crash — route every word-bearing
   node through `_format_word`; widen the `except` in `visitor_modes.py`.

**Tier 3 — MED, by value:** M6 (+E-IO unify the fd primitive — data loss), M1 (heredoc
`$`-delimiter), M12 (prompt `$`-expansion — also retires dead code), M13 (`set -u`
exit code + script error prefix), M4, M10, M11, M9, M14, M7, M8, M2/M3, FUNCNAME stack.

**Tier 4 — elegance (zero-behavior-change):** unify the 3 expansion-extent scanners and
the 2 `can_start_expansion`; single op→callable table in expansion; delete dead
prompt/format/traversal paths; collapse the duplicated close-stream and
background-launch helpers; correct the `[[ < ]]` collation comment.

**Tier 5 — truth-up:** document the Unicode-identifier divergence; add the missing
no-separator forms to the parity `REJECTION_CORPUS`; pin every HIGH/MED above as a
`tests/behavioral/golden_cases.yaml` entry so the probes earn their keep.

---

### Recurring lesson (consistent with reappraisals #11–#13)
Every HIGH bug this round lived behind a **second, divergent code path** for a job the
codebase already does correctly somewhere else: arithmetic reconstruction
(expansion-form correct, command-form wrong), empty-body guard
(`parse_brace_group` correct, `functions.py`/loop callers missing it), extglob
negation (standalone correct, embedded wrong), subshell scope-reset (`subshell.py`
correct, `pipeline.py` wrong), declaration flags (`declare` correct, `readonly`/`export`
incomplete), prompt expansion (`PromptManager` correct, REPL path escape-only). The
elegance axis and the correctness axis are the same finding viewed twice — **collapsing
each duplicated path onto its correct sibling fixes the bug and improves the teaching
code simultaneously.**
