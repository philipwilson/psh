# Ground-Up Reappraisal #14 — psh @ v0.539.0 (2026-06-22)

A fresh, independent code-quality + correctness review of every subsystem, graded on
two axes: **(1) correctness vs bash** and **(2) textbook-quality elegant/efficient
code** (psh is a teaching codebase). Conducted by 10 parallel per-subsystem auditors;
every correctness finding below was pinned with a live `bash`-vs-`psh` probe on the
macOS host. Read-only — no source was modified.

> Method: bash-verification discipline throughout —
> `b=$(bash -c "$cmd" 2>&1; echo rc=$?); p=$(python -m psh -c "$cmd" 2>&1; echo rc=$?)`.
> Cosmetic-only diffs (the `psh:` vs `bash: line N:` error prefix, error-message
> wording with matching exit codes, non-portable assoc-array hash ordering) are
> excluded as intentional/known throughout. Prior-round (#13/v0.514) fixes were
> re-confirmed intact in passing and are not re-reported.

---

## Overall verdict

**Correctness: B+ / A−.**  **Elegance: A−.**

psh remains an exceptional teaching artifact. The recognizer-registry lexer, the
fork/signal-policy executor, the combinator parser's discriminated-`ParseResult` core,
the arithmetic recursive-descent package, the RedirectPlan ownership model, and the
visitor double-dispatch infrastructure are all at or near textbook quality. As in every
prior round, yield is **non-diminishing**: this pass surfaced a fresh cluster of
**8 HIGH-severity** correctness issues plus ~22 MED and a tail of LOW/elegance items.

The single dominant theme is **trap-firing fragility**: three independent auditors found
the **EXIT trap silently dropped on three different exit paths**, and two found
**ERR/DEBUG traps over-firing inside functions**. Every HIGH below is, once again, the
recurring pattern — *"a second divergent code path for what psh already does right
elsewhere."* The EXIT trap fires from the `exit` builtin but not on script-EOF, `set -e`
abort, or background-subshell completion; `set -u` is honored for `$x` but not inside
`$(( ))`; ERR/DEBUG fire correctly at shell level but inherit wrongly into functions; the
brace-expansion "detach" path is dead-but-harmful. These are concentrated, mechanical
fixes with high payoff.

### Per-subsystem grades

| Subsystem | Correctness | Elegance | Headline issue |
|-----------|:-----------:|:--------:|----------------|
| Lexer | A− | A− | `${...}` extent over-consumes on a literal `{` → spurious "Unclosed quote" (MED) |
| Parser (rd) | A− | A | `!`/`time` prefix breaks keyword/`[[` recognition on following compound (MED) |
| Parser (combinator) | B+ | A | documented `[[ && ]]` shallow-grammar boundary (known) |
| Executor | A− | A | **ERR/DEBUG traps over-fire inside functions; no `errtrace`/`functrace` (HIGH)** |
| Expansion | A− | A | brace-expand literal `}`/`]`/`)` suffix space-joins (MED, dead "detach" path) |
| Core/State | A− | A | **bare `declare NAME` in fn mutates outer var; scalar nameref `+=` (HIGH×2)** |
| Builtins | A− | A− | **EXIT trap dropped on `set -e` abort (HIGH)** |
| I/O redirect | A− | A− | **`exec 3>&-` corrupts script-reading fd in script mode (HIGH)** |
| Visitor infra | — | A− | exemplary double-dispatch + coverage matrix |
| Visitor `--format` | B− | (B+) | **8 lossy round-trip defects (HIGH cluster)** |
| Interactive | B | A− | **`HISTCONTROL`/`HISTIGNORE` unsupported (HIGH)** |
| Scripting / cross-cutting | B+ | A− | **EXIT trap not fired at script EOF (HIGH)** |
| Arithmetic evaluator | A− | A | `0x`/leading-zero-base literal edge cases (LOW) |

---

## HIGH-severity findings

### H1. EXIT trap silently dropped on three exit paths (script EOF, `set -e` abort, background subshell) — Scripting / Builtins / Executor
The EXIT trap is wired into the **`exit` builtin** only (`builtins/core.py:52-53`). Every
*other* way the shell or a subshell terminates skips it. Three auditors independently hit
three facets:

```
# (a) script reaches EOF — the overwhelmingly common case
printf 'trap "echo BYE" EXIT\ntrue\n' > tmp/a.sh
bash tmp/a.sh  → BYE        psh tmp/a.sh  → (nothing)

# (b) set -e aborts the shell
printf 'trap "echo CLEANUP" EXIT\nset -e\nfalse\necho after\n' > tmp/b.sh
bash tmp/b.sh  → CLEANUP    psh tmp/b.sh  → (nothing)   # trap skipped, rc=1 both

# (c) background subshell completes
( trap "echo subbye" EXIT; sleep 0.05 ) & wait; echo main
bash → subbye / main        psh → main                 # subbye missing
```
**Root causes:** (a) `script_executor.py:47` guards the `execute_exit_trap()` call behind
`old_script_mode != True`, but `Shell(script_name=path)` already sets `is_script_mode=True`
at construction (`state.py:91`), so the guard always skips. (b) the `set -e` path raises
`SystemExit` directly (`executor/core.py:128-129`), a `BaseException` that propagates past
the `except Exception/OSError` handlers and past the callers' `execute_exit_trap()` calls.
(c) `_execute_background_subshell` (`executor/subshell.py:194-227`) omits the
`execute_exit_trap()` that the foreground path at `:147-150` has.
**Fix direction (one structural fix covers all three):** fire the EXIT trap at a *single
chokepoint* — wrap the top-level run in `try/.../finally: execute_exit_trap()` in
`__main__.py`/`script_executor.py` (the existing `_exit_trap_executed` idempotency guard
prevents double-firing), catch `SystemExit` there, and add the same call to the background
subshell body. This removes the duplicated trap-firing in the `exit` builtin. **Highest-value
fix in the report** — silent failure of the universal `trap cleanup EXIT` idiom.

### H2. ERR / DEBUG traps over-fire inside function bodies; no `errtrace`/`functrace` — Executor (confirmed by Scripting)
bash does **not** run ERR/DEBUG/RETURN traps inside a function unless `set -o errtrace`/`-E`
(ERR) or `functrace`/`-T` (DEBUG/RETURN) is set. psh has no such concept and fires at every
nesting level. Verified with a side-effect counter (observable behavior, not stdout ordering):
```
c=0; trap 'c=$((c+1))' ERR; f(){ false; }; f; echo "fired=$c"
  bash: fired=1        psh: fired=2          # fires for inner false AND f's return
trap 'echo E' ERR; { { false; }; }
  bash: E              psh: E E E            # one extra fire per brace-group layer
trap 'echo D' DEBUG; f(){ echo a; echo b; }; f
  bash: D a b          psh: D D a D b
```
The flat top-level case is correct (`false;false;false` → `fired=3` both). **Root cause:**
`run_pipeline` fires `execute_err_trap` at every `visit_AndOrList` level (`executor/core.py:236-238`)
and `execute_debug_trap` fires unconditionally per simple command (`command.py:202`,
`control_flow.py:*`), with no function-depth/option gate. Note the adjacent `errexit_eligible`
logic at `core.py:229-233` *already* implements brace-group transparency — the ERR-trap firing
beside it does not (the textbook "second code path" smell). **Fix direction:** add `errtrace`/
`functrace` options (H2b: `set -E`/`-T`/`set -o errtrace` currently error) and a RETURN
pseudo-signal to trap (H2c: `trap … RETURN` is rejected though `_PSEUDO_SIGNALS` half-lists it),
then gate ERR/DEBUG firing on function depth + the relevant option.

### H3. `exec` on fd 3 corrupts the script-reading fd in script/source mode — I/O redirect
```
# script: "exec 3>&-\necho hi"
bash → hi (rc=0)    psh → hi / psh: <script>: [Errno 9] Bad file descriptor (rc=1)
# the classic stdout/stderr swap idiom, in a script file:
# "exec 3>&1 1>&2 2>&3 3>&-"
bash → (silent rc=0)    psh → psh: <script>: [Errno 9] Bad file descriptor (rc=1)
```
Only **fd 3** breaks (`exec 4>&-`…`9>&-` are fine) — it is the descriptor `FileInput.__enter__`
(`scripting/input_sources.py:63`) lands on via plain `open()`. A user `exec 3>&-` closes it; at
`__exit__`, `self.file.close()` raises EBADF → spurious error + exit 1. **Fix direction:** after
`open()`, relocate the script fd to ≥ 10 via `fcntl(fileno, F_DUPFD, 10)` (mirroring
`apply_var_fd_redirect`'s own allocation), exactly as bash protects its script fd.

### H4. Bare `declare NAME` (no value) inside a function mutates the outer variable — Core/State
```
g=glob; f(){ declare g; g=x; }; f; echo "$g"
  bash: glob   (declare g is local, like `local g`)    psh: x   (mutated the GLOBAL)
```
`local g` and `declare g=value` both shadow correctly; only the bare-`declare`, no-value,
name-already-exists case is wrong. **Root cause:** for empty `attributes`,
`DeclareBuiltin` (`builtins/function_support.py:430-437`) finds the global via the scope chain
and runs a no-op `apply_attribute`, never routing through `_set_variable_with_attributes`
(which sets `local=bool(function_stack)`), so no local shadow is created. **Fix direction:**
in a function without `-g`, a bare `declare NAME` must create a local UNSET-tombstone shadow
(as `local NAME` already does via `ScopeManager.create_local`).

### H5. Scalar/integer `+=` through a nameref appends to the target *name*, not its value — Core/State
```
n=5;            declare -n r=n; r+=3;     echo $n   bash: 53      psh: n3
declare -i n=5; declare -n r=n; r+=3;     echo $n   bash: 8       psh: 0
declare -u u=x; declare -n r=u; r+=world; echo $u   bash: XWORLD  psh: UWORLD
```
Array nameref `+=` (the prior-round fix) still works. **Root cause:** `resolve_append_assignment`
(`core/assignment_utils.py:50-78`) strips `+`, looks up `r` (the nameref, whose `.value` is the
literal target-name string `"n"`), and computes `"n"+"3"="n3"` *before* resolving the nameref.
**Fix direction:** resolve the nameref to its target name first (`resolve_nameref_name`) before
reading `old`/attributes and before the integer/array branches.

### H6. Inconsistent fatal-vs-continue policy for assignment errors (script vs `-c`) — Core/State
A readonly-reassignment or nameref-cycle error **aborts a whole script file** (psh
`sys.exit(1)`), but bash reports it and continues:
```
# script file: "readonly r=1\nr=2\necho REACHED"
bash → r: readonly variable / REACHED (rc=0)    psh → r: readonly variable (rc=1, aborts)
```
The *inverse* gap (H6b): a `declare -i x; x=3/0` arithmetic error fails to abort a `-c` string
(psh prints error + `REACHED` rc=0; bash treats it as fatal to the `-c` string). **Root cause:**
`command_assignments.py:204-214` does `if is_script_mode: sys.exit(1)` for readonly/nameref-cycle
(wrong for files), while `ShellArithmeticError` isn't caught there at all. Also H6c: redefining a
`readonly -f` function reaches the generic guard and prints the misleading `unexpected error:`
prefix then aborts (`executor/function.py:46`). **Fix direction:** pick one policy and apply it
uniformly to all three error classes — the cleanest framing is *fatal-to-the-current-command in
`-c`, report-and-continue in scripts* (drop the `sys.exit`, return 1, let the source processor
advance line-by-line). Catch `FunctionDefinitionError` at its site and print `psh: NAME: readonly
function`.

### H7. `HISTCONTROL` / `HISTIGNORE` entirely unsupported; dedup itself diverges — Interactive
(PTY-verified.) `HISTCONTROL=ignorespace` still records ` echo secret`; `erasedups` keeps older
dups; `HISTIGNORE='ls:history*'` records both. **And** psh's *unconditional* consecutive-dedup
diverges: with no `HISTCONTROL`, typing `echo dup` twice keeps one entry, but bash keeps both
(bash dedups only when `HISTCONTROL` contains `ignoredups`/`erasedups`). **Root cause:**
`history_manager.py:54/66` hardcodes a previous-line dedup and never reads `HISTCONTROL`/`HISTIGNORE`
(grep count = 0). **Fix direction:** consult `HISTCONTROL` (space/dup variants) and `HISTIGNORE`
(colon-separated globs) in `add_to_history`; gate the existing dedup behind `ignoredups`/`erasedups`.

### H8. `--format` pretty-printer is lossy on 8 constructs — Visitor
The visitor *infrastructure* is textbook (double-dispatch + `_method_cache` + coverage matrix), but
the `--format` round-tripper produces output that re-parses to a **different program** or a **parse
error** across at least 8 constructs (input → formatted → semantic break):

| Input | Formatted | Break |
|-------|-----------|-------|
| `echo ${arr[@]}` | `echo $arr[@]` | braces dropped → element 0 + literal `[@]` |
| `echo hi > >(cat)` | `echo hi >>(cat)` | **parse error** (`>>` + `(cat)`) |
| `ls \|& grep x` | `ls \| grep x` | stderr no longer piped |
| `echo "a\$b"` | `echo "a\\$b"` | escaped `$` becomes a live expansion |
| `$'a\b'` / `$'q\'x'` | `$'a\b'` / `$'q'x'` | value change / **unclosed-quote error** |
| `echo {fd}>file` | `echo >file` | **named fd dropped** (new v0.539 feature) |
| `for x in *.md` / `"a;b"` | `for x in "*.md"` / `a;b` | glob suppressed / **parse error** |
| `cat <<EOF \| grep h` | terminator glued to `\| grep h` | heredoc termination broken → prints nothing |

**Root-cause theme (also the elegance fix):** the remaining *flat-string* AST fields —
`VariableExpansion.name` with a subscript, `ForLoop.items`/`SelectLoop.items`,
`CaseConditional.expr`, `UnaryTestExpression.operand`, and the ANSI-C re-wrap — are where every
round-trip bug lives, because the formatter must *guess* quoting for them. The Word-based paths
(`_format_word`) are correct. **Fix direction:** push these fields onto the Word layer (as
`SimpleCommand.words` and `Redirect.target_word` already are) so one correct `_format_word` handles
all quoting; immediate point fixes: `${name}` when name has non-identifier chars, space before a
`<(`/`>(` target, `|&` join when `pipe_stderr[i]`, emit `{var_fd}` prefix, re-escape `$'...'` and
escaped-backslash-in-`"..."`, render pipeline-header-then-heredoc-bodies.

---

## MED-severity findings

**Parser**
- `!`/`time` prefix loses command position → `! while …; do …; done`, `! if …`, `! case …`,
  `time while …`, `! [[ … ]]` all parse-error or mis-dispatch (bash accepts). Both parsers.
  `EXCLAMATION`/`time` aren't treated as command-position-preserving in
  `keyword_normalizer.py:127-172` / `modular_lexer.py:246-256`. (`! { … }`, `! ( … )`, `! pipeline`
  of simple commands all work.) Fix: add `!`/`time` to the command-position-preserving set in both
  state machines.

**Lexer**
- `${...}` extent over-consumes on a literal `{` in the body: `echo "[${u:-a{b}]"` → spurious
  *"Unclosed quote"* parse error; `echo "${x:-/path/{a,b}/c}"` → wrong output. `validate_brace_expansion`
  (`pure_helpers.py:522-526`) counts bare `{` toward nesting depth; bash ends at the first unescaped
  `}` (nested `$`-expansions already skipped separately). Fix: drop the bare-brace depth counting.
- `$'\0'` / `\x00` not C-string-truncated (psh keeps bytes after NUL; bash truncates). Word model is
  Python `str`; decoders emit `chr(0)`.
- `$'\xff'` / `\377` and `printf '\xff'` emit UTF-8 of the codepoint, not a raw byte — the known
  deferred **byte-model gap (M8)**; surfaces in `lexer/pure_helpers.py` and `utils/escapes.py:64-103`.
  Recommend an explicit documented-divergence conformance test if it stays deferred.

**Executor / Scripting (trap & options cluster — see H2)**
- `time` reserved word is **not implemented**: lexed as a keyword and `type time` claims it's one,
  but the parser builds no time node, so it's exec'd as `/usr/bin/time` — can't time pipelines/
  subshells/`!`-lists, ignores `TIMEFORMAT`, emits BSD format. (`strategies.py:380`.)
- `FUNCNEST` ignored — deep recursion runs to Python's limit (caught as exit 1, but the documented
  limit is non-functional). `function.py:104`.
- `wait -n` / `wait -p VAR` unsupported (treated as a PID → error 127). Documented limitation.
- `set -u` not enforced inside arithmetic: `set -u; echo $(( undefined + 1 ))` → psh `1`, bash aborts.
  `expansion/arithmetic/evaluator.py:50,115`.
- `BASH_SOURCE` / `BASH_LINENO` arrays always empty (FUNCNAME/LINENO work). Common in error-reporting
  idioms. Never populated.
- Script runtime errors lack the `scriptname: line N:` prefix (documented goal); syntax errors get a
  prefix but the parenthetical `(line N, column M)` is relative to the parse unit, not the file.
- `set -x` xtrace omits compound-command headers (`+ for i in 1 2`, `+ case x in`) and bash-style
  arg-quoting (`+ '[' 0 -lt 2 ']'`).

**Expansion**
- Brace expansion with a literal `}`/`]`/`)` suffix space-joins items: `echo arr[{1,2}]` → `arr[1 2]`
  (bash `arr[1] arr[2]`); also `[{1,2}]`, `{a,b}]`, `{{a,b}}`. Root cause is a **dead "detach"
  mechanism** (`brace_expansion.py:59,161,192`) left over from the token-stream migration — real
  operators are now separate tokens, so the path only mis-fires on legitimate literal-brace suffixes.
  Fix deletes code and fixes the bug.
- `"${!ref}"` indirection to an `a[@]` target loses multi-field semantics (`<p q r>` vs `<p> <q> <r>`).
  `expansion/fields.py:19` never re-checks the resolved target for `[@]` shape on the field path.

**Builtins**
- `export -p` omits exported-but-unset variables (`export NOVAL; export -p` shows nothing; `declare -p
  NOVAL` correctly shows `declare -x NOVAL`). Iterates the live env dict instead of variable objects.
  `environment.py:186-191`.
- `complete`/`compgen`/`compopt` unimplemented (rc 127) — and not listed as a limitation in the
  user-guide compat table (unlike `wait -n`/`mapfile -C`).
- `mapfile -C callback`/`-c quantum` rejected (documented).

**I/O redirect**
- Here-string skips tilde expansion: `cat <<<~` → psh `~`, bash `/Users/pwilson`. Variable/cmdsub/
  arith/glob-suppression all match; only `~`. `file_redirect.py:206-217`.

**Core/State**
- (H6b/H6c folded above.)

---

## LOW / elegance findings

**Correctness LOWs**
- Parser: `echo a; ; echo b` (space-separated double separator) over-accepted; bash errors rc 2
  (`statements.py:56-66` — `skip_separators` eats the run). `function while { … }` reserved-word name
  rejected, with an rd(rc1)/combinator(rc2) exit-code divergence.
- Arithmetic: `$((0x))` → error (bash `0`); `$((016#5))`/`$((08#5))` leading-zero base silently
  accepted (bash rejects). `arithmetic/tokenizer.py:127-128,47-54`.
- Core: bare `${assoc}` doesn't resolve key `"0"` (`variables.py:291` hardcodes `""`).
- I/O: `{undefvar}>&-` close doesn't error (bash: ambiguous redirect); `{fd}<<EOF`/`{fd}<<<` named-fd
  prefix rejected before heredoc/here-string; bare `{fd}>file` with no command sets the var (bash
  doesn't).
- Interactive: `history -a/-r/-w/-d` unsupported; PS4 not run through prompt-escape expansion under
  `set -x` (`PS4='[\t] '` → literal); prompt `\j`/`\l`/`\D{fmt}` unsupported; `%?str` job spec and
  ambiguous-`%prefix` detection missing; `^old^new` quick-sub doesn't echo the expansion; `fc` not
  implemented.
- Builtins: `declare -f` puts `{` on the `()` line vs bash's canonical multi-line layout.

**Elegance**
- **Lexer:** three near-identical quote handlers (`_handle_quote`/`_handle_locale_string`/
  `_handle_ansi_c_quote`, ~37 lines each) — collapse into one parameterized helper. Dead
  backward-seek branch in the `position` setter (`modular_lexer.py:104-113`) — all assignments move
  forward.
- **Parser (combinator):** the `committed` field in `ParseResult` is "wired-but-inert" (commitment
  still expressed by raising `ParseError`) — two mechanisms for one concept, acknowledged in
  `core.py:19-30`. The array grammar exists twice (rd + combinator, ~292 lines each); parity verified
  today but it's two implementations to keep in sync.
- **Core:** wrong "Python dict matches bash" comment on assoc-array ordering (`variables.py:265-276`)
  — bash uses unspecified hash order; reword. Dead `VariableScope.parent` field (`scope.py:41`) — set,
  never read.
- **Builtins:** `parse_flags(value_flags=…)` used by only one builtin while the same cluster-scan is
  hand-rolled 4× (`read`/`mapfile`/`print`); `read -p` prompt written via raw `sys.stderr.write`,
  violating the forked-child-aware-helper convention; misc (sibling builtins instantiated directly vs
  via registry; three help-text sources; `parser_experiment.py` misnames a shipped feature).
- **Visitor:** `word_analysis.py` exposes 6 public predicates with zero production callers (~40% of the
  module) — defensible as a "coherent tested set" but trim or mark illustrative for a teaching codebase.
- **Interactive:** dead prompt wiring — `REPLLoop.prompt_manager` is assigned/type-hinted but never
  read; `PromptManager.get_primary_prompt`/`get_continuation_prompt`/`set_prompt` have zero callers
  (the M12 fix left these residuals).
- **I/O:** the `redirect.fd if … is not None else 0/1` default-fd derivation is repeated ~10× despite
  `RedirectPlan.target_fd` being the "single source of truth" (documented boundary; mild redundancy).
- **Scripting:** redundant duplicate assignment after the pseudo-signal early-return in
  `trap_manager.py:134-138,159-163`.

---

## Recurring themes & recommended fix order

1. **Trap-firing is wired per-exit-site, not at a chokepoint.** H1 (EXIT on EOF / `set -e` /
   bg-subshell) + H2 (ERR/DEBUG in functions) + the missing `errtrace`/`functrace`/RETURN options are
   one coherent trap-subsystem hardening pass — the highest-value cluster. Do **H1 first** (one-line
   guard removal + a `finally` chokepoint; silent data-loss-class bug).
2. **"Honored on path A, ignored on path B."** `set -u` honored for `$x` but not arithmetic;
   command-position preserved after most tokens but not `!`/`time`; brace suffix attaches normally but
   space-joins on `}`/`]`/`)`; nameref `+=` correct for arrays but not scalars. Each is a localized
   second-path fix.
3. **Flat-string AST fields are the formatter's Achilles heel.** Migrating `ForLoop.items`,
   `CaseConditional.expr`, `UnaryTestExpression.operand`, and subscripted `VariableExpansion` onto the
   Word layer retires the `--format` quoting heuristics and most of H8 at once.
4. **Dead-but-harmful code = bug + cleanup.** The brace-expansion detach mechanism and the
   `VariableScope.parent` field are both removable.

Suggested tiering for a fix campaign:
- **Tier 1 (HIGH):** H1 → H2(+errtrace/functrace/RETURN) → H3 → H4 → H5 → H6 → H7 → H8.
- **Tier 2 (MED):** parser `!`/`time` position; lexer `${...}` extent; brace-suffix detach removal;
  `time` reserved word; `set -u` in arithmetic; `export -p` unset; `BASH_SOURCE`/`BASH_LINENO`;
  here-string tilde; indirection-to-`[@]`; xtrace compound headers; `FUNCNEST`; `wait -n`.
- **Tier 3 (LOW + elegance):** the LOW correctness tail + the elegance cleanups; truth-up README/docs.

Every HIGH and MED above is bash-pinned; the byte-model items (M8) remain architecturally deferred.
