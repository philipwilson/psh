# Ground-Up Reappraisal #15 — psh v0.559.0

**Date:** 2026-07-01
**Method:** 13 parallel per-subsystem auditors, each grading Correctness
(bash-conformance of implemented behavior) and Textbook Quality (elegance,
clarity, efficiency). Every claimed behavior divergence was pinned with an
actually-run probe against GNU bash 5.2.26 on the same host (~2,900 paired
probes total; artifacts under `tmp/appraisal15/`). Unimplemented bash
features were **excluded by instruction** (they are tracked in
`docs/missing_features.md`), as were the known-deferred items from
reappraisal #14.
**Baseline:** 240 Python files, ~57.7K LOC, ~9,100 collected tests.
**Prior round:** #14 (2026-06-22, v0.539) found 8 HIGH + ~22 MED; all 8 HIGH
and 11 of the MEDs shipped as v0.540–559.

---

## Executive summary

**Overall: Correctness B+, Elegance A− (both holding from #14) — but the
subsystem floor dropped and the yield ROSE.** This round surfaced **~35
HIGH-severity findings** (vs. 8 in #14), concentrated in paths no prior round
adversarially probed: statement boundaries, brace-expansion adjacency, the
function-serialization formatter, entry-point argument parsing, subshell
state inheritance, and the interactive history plumbing. The audited-and-fixed
areas from rounds 13–14 (errexit matrix, trap firing counts, PIPESTATUS,
heredoc core, extglob core, attribute-application matrix, fd machinery)
**held clean under re-probing** — the fixes are durable; the frontier simply
moved.

| Subsystem | Correctness | Elegance | One-line verdict |
|---|---|---|---|
| Lexer | B+ | A− | Core strong; `&` cmd-position, `$((` fallback, line-continuation contexts |
| Parser (RD) | B+ | A− | Grammar clean; silent-misexecution cluster at statement boundaries |
| Parser (combinator) | B− | B | Feature-parity drift (`time`, heredocs, `&`); dead surface |
| Expansion | B+ | A− | Operator matrix excellent; brace-adjacency and operand quoting broken |
| Executor | B+ | A− | Reworked core held; builtin-redirect visibility is the gap |
| Core/State | B | A− | unset model wrong vs bash; trap surface gaps; adopt() drift |
| Builtins | B+ | B+ | Option matrices clean; 5 HIGHs in everyday idioms |
| I/O Redirect | B+ | A− | fd machinery bash-exact; compound redirect-failure path uncaught |
| Interactive | B− | B+ | History recall dead on fresh installs; cmdhist corrupts entries |
| Scripting/Entry | B− | B+ | Flag stealing from script args; non-seekable scripts swallowed |
| Visitor/Formatter | **C+** | A− | Six fresh HIGH round-trip breaks; validators/infra solid |
| Engines (arith+pattern) | B+ | A− | Consistent across sites; 3 HIGHs incl. crash + precision loss |
| Cross-cutting | B+ | A− | Docs truthful, hygiene excellent; adopt() drift-lock missing |

---

## Recurring themes (what keeps generating the bugs)

1. **New-feature integration drift.** The v0.558 `time` keyword shipped
   correct in the RD parser + executor but never reached the combinator
   parser (hard parse failure), the formatter (silently dropped), the
   debug visitor, or the bare-top-level compound unwrap (sole-statement
   `time if ...` times nothing). A new AST field or keyword needs a
   **consumer checklist**: both parsers, formatter, debug visitors,
   xtrace, characterization corpora. The coverage-matrix test enforces a
   `visit_X` per node *class* — new *fields* on existing nodes slip through.
2. **The second (and third) divergent code path — still the #1 bug factory.**
   This round's instances: `psh/utils/shell_formatter.py` is a rotted
   duplicate of the maintained formatter visitor (→ 2 HIGHs);
   command-position is three machines and only one handles `&`; heredoc
   terminator matching exists in 3–4 copies, two of them wrong (rstrip);
   group-`&` is consumed in two places with different semantics;
   break/continue parse via two paths (one rejects `break | cat`); the
   expansion `@`/`*`/`arr[@]` operator logic is triplicated (the `*` copy
   misses per-element ops); stdin got fd-level builtin redirects, stdout/
   stderr didn't.
3. **Flat-string AST fields remain a defect magnet** (the #14 H8 root,
   still unpaid): the `case` *subject* (re-expands quoted text — even
   executes a single-quoted `$(...)`; found independently by three
   auditors), `[[ ]]` *unary* operands, here-string targets, `ForLoop.items`
   in xtrace, array-assignment formatter paths, `$'...'` in assignment
   position (loses quote context in the lexer before the AST exists).
4. **Missing drift-locks.** `ShellState.adopt()` silently omits 7 fields
   added to `__init__` since it was written (`ExecutionState.copy_into`
   was built precisely to prevent this — the lesson wasn't generalized);
   the conformance-claims meta-test accepts vacuous evidence (a class-name
   substring match); ~46 no-op tests, one of which was green over a live
   drift bug.
5. **Silent failure where bash is noisy.** Unterminated heredoc at EOF →
   command dropped (bash warns and runs); non-seekable script → empty
   no-op rc=0; history records silently skipped; `fi(uname)` executes;
   `a[08]=Q` corrupts `a[0]`. When psh cannot honor input, it should say so.

---

## Tier 1 — HIGH findings (clustered)

### Cluster A — Silent misexecution at statement boundaries (lexer/parser)

- **A1. Missing statement-separator validation: `echo (ls)` EXECUTES both
  commands** (bash: rc=2 syntax error). Also `echo foo(bar)`, `x=1 (echo sub)`,
  `if true; then echo hi (uname); fi`, `fi(uname)`. The top-level and
  `parse_command_list_until` loops re-enter `parse_statement` without
  requiring a separator. `psh/parser/recursive_descent/parser.py:127-141`,
  `parsers/statements.py:80-91`. One shared "statement must end at
  separator" guard fixes it at a chokepoint.
- **A2. Reserved words / `[[` / `!` lose command position after `&`**:
  `true & if true; then echo B; fi; wait` → rc=2 (bash: runs).
  `STATEMENT_SEPARATORS` omits AMPERSAND (`psh/lexer/command_position.py:45-51`);
  the architecture doc says `&` sets command position and the cmdsub scanner
  implements it — the other two machines don't.
- **A3. Subshell/brace groups consume `&` themselves** (a redundant second
  background path): `(a) && (b) &` runs the first group in the FOREGROUND;
  `(echo a) & | cat` is accepted and executed (bash rc=2).
  `parsers/commands.py:524-527,561-564` vs the already-correct
  `_apply_background` (`statements.py:151-168`).
- **A4. `$((` never falls back to `$( (subshell)`**: `echo $((echo a); echo b)`
  → rc=2 (bash prints `a b`). `psh/lexer/expansion_parser.py:141-184`.
- **A5. Line-continuation preprocessing joins `\<newline>` inside comments
  and quoted heredoc bodies**: a comment ending in `\` silently swallows the
  next command line; a `<<'EOF'` body loses literal trailing backslashes.
  `psh/scripting/input_preprocessing.py:9-112`.

### Cluster B — Everyday expansion breakage

- **B1. Brace expansion destroys quoted expansions in composite words**:
  `cp "$f"{,.bak}` passes **literal `$f`** to cp; `"$f"{1,2}` → `$f1 $f2`.
  Placeholder re-encoding loses expansion-part metadata.
  `psh/expansion/brace_expansion_tokens.py:158-279`.
- **B2. `${v}{1,2}` never brace-expands** (name-fusion guard over-broad —
  `${v}`/`${a[0]}` cannot fuse): `${v}{1,2}` → `V{1,2}` (bash `V1 V2`).
  Same file, :203-214.
- **B3. Conditional-operator operands are quote-context-blind**
  (`psh/expansion/operands.py:38-79`): `${v:-'a b'}` splits into 2 fields;
  `"${v:-~}"` tilde-expands (bash: literal); `"${v:-'a b'}"` strips quotes
  bash keeps; `${v:='a b'}` stores the wrong value.
- **B4. `read x rest` rewrites the remainder**: last variable gets fields
  re-joined with `IFS[0]` instead of the original text (`'a  b  c'` →
  `b c`; `IFS=: read a b` on `x:y::` → `y:` not `y::`).
  `psh/builtins/read_builtin.py:334-341`.

### Cluster C — Redirect visibility and failure handling

- **C1. Redirections on in-process builtins are invisible to children they
  spawn**: `command ls / > /dev/null` prints everything;
  `eval "ls | head -1" > f` leaks to tty; `source s 2>/dev/null` leaks
  stderr. Stream-level swap only — stdin was given fd-level treatment for
  exactly this scenario (`psh/io_redirect/manager.py:248` docstring);
  fd 1/2 were not. `psh/executor/command.py:683-708`.
- **C2. `command EXT > f` drops redirects entirely** —
  `_execute_external_command` builds a fresh strategy with `redirects=None`.
  `psh/builtins/command_builtin.py:130-146`. (Same family as C1, distinct
  mechanism; `command`/`builtin` also bypass `execute_builtin_guarded` and
  `BuiltinContext`.)
- **C3. Redirect failure on in-process compound commands raises uncaught
  OSError**: `{ echo a; } > /bad/f || echo fallback` skips the fallback and
  reports "unexpected error" (bash: diagnostic + fallback runs). Affects
  `{ }`, `if`, `for`, `while`, `until`, `case`, `[[ ]]`, `(( ))`. Redirect-
  error handling is per-dispatch-site: 5 sites format OSError 4 ways, 3
  compound sites forgot entirely. `psh/executor/control_flow.py:66-73`,
  `core.py:405-445`, `subshell.py` brace path.

### Cluster D — Scope/function model (core)

- **D1. The `unset` tombstone model is wrong for non-local variables.**
  Bash semantics: `unset` in a function removes the visible variable and
  *reveals* the next-outer one; a subsequent assignment writes where bash's
  scope walk lands. psh plants a current-scope tombstone even for outer
  variables, so `x=1; f(){ unset x; x=new; }; f` leaves `x` **unset**
  (assignment became function-local and vanished). Four probe shapes
  diverge; `psh/core/scope.py:421-473`, and `psh/core/CLAUDE.md` documents
  the wrong rule as intended.
- **D2. Valid bash function names rejected**: `true(){ ...; }`, `exit()`,
  `my-func()`, `.dot()` all fail (`RESERVED_WORDS` wrongly includes
  builtins; identifier-only name rule; errors route through "unexpected
  error"). `psh/core/functions.py:32-38,122-136`. Related: `break`/
  `continue`/`return` are lexed as reserved words (bash: ordinary
  builtins), so `break()` is a parse error and `break 2>/dev/null` prints
  its message despite the redirect (`psh/lexer/constants.py:9-18`).
- **D3. `declare -f` crashes on any function containing `case`**
  (`'|'.join` over CasePattern objects) **and drops heredoc bodies**,
  breaking the `src=$(declare -f f); eval "$src"` round-trip (rc=127).
  Root: `psh/utils/shell_formatter.py` is a rotted duplicate of the
  maintained formatter visitor. `shell_formatter.py:310-325`. Fix by
  deleting it and routing `declare -f`/`type`/`command -V` through
  `formatter_visitor`.

### Cluster E — Subshell state inheritance

- **E1. `ShellState.adopt()` 7-field drift** — fields in `__init__` never
  copied to `( )`/`$( )`/`<( )`/env-builtin children: `script_name`
  (**`$(dirname "$0")` returns "." — breaks a top-5 script idiom**),
  `function_stack` (FUNCNAME empty in subshells), `trap_handlers` (the
  POSIX `saved=$(trap)` idiom returns nothing; `trap ''` ignores not
  inherited), `source_depth` (`(return 7)` in sourced file misbehaves),
  `directory_stack`, `history_state`, `_getopts_charpos`. Also ScopeManager
  computed-special state (`SECONDS`/seeded-`RANDOM` reset in children).
  `psh/core/state.py:187-226`. **Fix as a chokepoint + add a
  field-completeness meta-test** (the `ExecutionState.copy_into` pattern,
  generalized).

### Cluster F — errexit / traps

- **F1. Command substitution inherits `set -e`** (bash: `$( )` resets it):
  `set -e; x=$(false; echo hi)` → psh aborts, bash sets `x=hi`.
  `inherit_errexit` shopt also unknown. Fork seam in
  `psh/expansion/command_sub.py` / `Shell.for_subshell` option copy.
- **F2. POSIX numeric trap forms rejected**: `trap 'cmd' 0` (the portable
  cleanup idiom) → "invalid signal specification"; `trap 2` (reset) →
  usage error and the trap stays. `psh/core/trap_manager.py:110-124`,
  `psh/builtins/signal_handling.py:116-118`. Adjacent MED: only 13
  hardcoded signal names accepted (`WINCH`/`SEGV`/... rejected) while
  `trap -l` lists them all — parser should use `signal_utils`.
- **F3. EXIT trap not fired on untrapped-signal death** (SIGTERM to a
  script: bash runs the EXIT trap, rc=143; psh silent). The v0.540
  chokepoint covers EOF/`set -e`/`exit` but not the signal path.
  `psh/interactive/signal_manager.py:127-133`. (Found independently by two
  auditors.)

### Cluster G — `case` subject is a flat string (3 independent reports)

- **G1.** Quoted subjects re-expand: `case '$x' in '$x')` matches the
  *expanded* arm; `case '$(echo hi)' in` **executes the single-quoted
  command substitution**. Composites corrupt (`case "$x"y` → expands `$xy`);
  backtick and tilde subjects never expand (`if '$' in expr` gate).
  `CaseConditional.expr: str` + `psh/executor/control_flow.py:352-355`,
  `parsers/control_structures.py:344-356`. The patterns got Word AST in a
  past fix; the subject didn't. Same family: `[[ ]]` unary operands
  (`[[ -n '$x' ]]` re-expands; `parsers/tests.py:114-118`) and here-string
  targets (`<<< foo$v"dq"` mis-expands; `parsers/redirections.py:122-137`).

### Cluster H — Evaluation engines

- **H1. `[[ x -eq 7 ]]` doesn't arithmetic-evaluate operands** (bash runs
  full arithmetic on `-eq/-lt/...` operands: `[[ 1+1 -eq 2 ]]`,
  `x=3+4; [[ $x -eq 7 ]]`). `psh/executor/enhanced_test_evaluator.py:171-182`.
- **H2. Valid bash bracket patterns crash as INTERNAL DEFECTS** (uncaught
  `re.PatternError`): `[[ b == [z-a] ]]`, `[a\]b]`, `[\x]` — in `[[ ]]`,
  `case`, and `${v#pat}` sites (bash: quietly no-match). Bracket scan
  doesn't honor `\]`; `pattern.py:68` lacks the `re.error` guard that
  `match_extglob` has. `psh/expansion/extglob.py:202-315`.
- **H3. Arithmetic `/` and `%` via float division** — silently wrong for
  |operands| ≥ 2^53: `$((9223372036854775807/3))` off by 170.
  `psh/expansion/arithmetic/evaluator.py:322,327`. Adjacent MED: literals
  and variable values not wrapped to signed 64-bit (operations wrap;
  sources don't).

### Cluster I — Entry points (scripting)

- **I1. psh's flags are stolen from script/`-c` operand positions**:
  `psh script.sh -i --norc foo` → script sees only `foo`; `--parser bar`
  as a script arg kills psh itself; `--debug-ast` as an arg activates
  debugging; `--` does not protect. `parse_args` scans all of argv with
  `args.remove(flag)`. `psh/__main__.py:129-138`. Fix: left-to-right
  parse, stop at first operand (also deletes the duplicated mode-sniffing).
- **I2. Non-seekable script sources silently swallowed**: `psh <(echo cmd)`,
  `psh /dev/stdin` (piped), `source <(...)`, `source /dev/stdin` all no-op
  rc=0 — the binary-sniff read consumes the pipe before the real open.
  `psh/scripting/script_validator.py:38-46`. Adjacent: UTF-8-heavy scripts
  false-positive as binary (CJK comments → rc=126).

### Cluster J — Formatter (`--format`) round-trip: six fresh breaks

All in `psh/visitor/formatter_visitor.py`; every one silently produces a
*different program* (verified in both psh and bash):

- **J1.** `time`/`time -p` dropped entirely (v0.558 fields unknown to the
  whole visitor package; `--format -c 'time'` crashes with IndexError).
- **J2.** Heredoc trailer misplaced when the line continues: `cat <<EOF &&
  echo AFTER` puts `&& echo AFTER` on the delimiter line; if/while
  conditions inline the trailer into the header (v0.547 fixed pipelines
  only). Heredocs on `[[ ]]`/`(( ))` are dropped entirely (hand-joined
  redirects skip `_append_redirects`).
- **J3.** Array assignments corrupt values 4 ways (`a=($'x\ty')` injects a
  literal `$`; `a[3]=$'x\ty'` re-parse **executes `y` as a command**;
  embedded `"` unescaped; composite assoc values lose quotes) — handlers
  still use legacy flat strings, not the required `words`/`value_word`.
- **J4.** `[[ ( a || b ) && c ]]` loses parens → silent rc flip; unary
  operand quote loss makes `[[ -z "" ]]` a parse error.
- **J5.** `for x; do` / `select x; do` format to **unquoted** `in $@`,
  changing word splitting (the quoted Word exists in the AST and is ignored).
- **J6.** (Lexer root) `v=$'l1\nl2'` in assignment position loses all quote
  context before the AST — formatted output runs `l2` as a command.
  Heredoc-trailer logic lives in 5 sites — consolidate to one seam.

### Cluster K — Interactive history

- **K1. History recall/search dead for any session starting with empty
  history** (every fresh install): `HistoryNavigator(history or [])`
  allocates a NEW list when `state.history` is empty, so the editor's alias
  to shell state never forms — up-arrow/Ctrl-R read a private empty list
  forever. `psh/interactive/line_editor.py:64`. Same alias breaks
  mid-session when erasedups/HISTSIZE-trim **rebind** `state.history`
  (`history_manager.py:93,137,151`). Enforce the alias contract (mutate in
  place, or route editor reads through state).
- **K2. cmdhist joining corrupts recorded commands**: `until`/`select`
  missing from the keyword whitelist (`until false do break done` —
  unparseable on recall, persisted to HISTFILE); case joins emit `;;; esac`;
  `f()\n{...}` emits `f() { {;`. The string heuristic sits beside the
  parser-driven CommandAccumulator it should use.
  `psh/interactive/line_editor_helpers.py`.

### Cluster L — Combinator parser parity drift

- **L1.** `time` never reached it: `--parser combinator -c 'time true'` →
  rc=2. No TIME handling anywhere in the package.
- **L2.** Heredocs: the combinator drops `token.heredoc_key` (bodies can
  never populate) — masked because `source_processor.py:246-257` silently
  routes ALL heredoc input to the RD parser even under `--parser
  combinator` (the debug header still says "combinator"). 418-line heredoc
  processor is dead code in the live path.
- **L3.** `a && b &` backgrounds only the last pipeline (left side runs
  foreground). Plus: function bodies must be `{ }` (bash: any compound);
  `(( ))`/`[[ ]]` trailing redirects misparse into a separate command
  (exit-code corruption); accepts `${`; RecursionError at ~25 nesting
  levels.

### Cluster M — Meta / process

- **M1. The conformance-claims meta-test accepts vacuous evidence** —
  marker is a substring match; `disown` maps to a class whose file never
  mentions disown; `pushd/popd` maps to an assert-free probe. Tighten to
  real assertions; also the regex only matches Notes == exactly
  "Full support" and misses prose claims.
- **M2. ~46 no-op tests** (12 docstring+pass placeholders, ~34 assert-free),
  including `test_trap_inheritance_in_subshells` which was green while the
  E1 trap-inheritance bug was live. Delete or implement.

---

## Tier 2 — MED findings (compact, by subsystem)

**Lexer:** cmdsub scanner matches heredoc terminators with `rstrip()` (its
"always agree" comment is false; the authoritative collector is exact);
unterminated heredoc at EOF silently yields an EMPTY body (bash: warn + use
partial body — the scripting auditor found the command dropped entirely at
the source-processor level); trailing digits of a word stolen as fd prefix
for `>&` (`echo hi3>&2` redirects fd 3 — overlapping tokens in the dump);
`2>& 1` / `>& /dev/null` space forms rejected; `$'\cX'` mishandles
quote/backslash targets; `NAME["k"]=` quote-removal suppressed at argument
positions (`declare h["a b"]=v` fails); `posix_mode` threading is
production-dead.

**Parser (RD):** `time` follow-ups (`! time`, `time time`, `time` before
`&&`, `time -p if`, `time` in pipeline tail, sole-statement `time <compound>`
drops timing via `_bare_top_level_compound` — plus `--format` interactions,
see J1); function defs not composable (`f() {...; } && echo ok`, `| cat`,
`&` — all valid bash, psh rc=2); break/continue two-path split (`break | cat`
rejected, `cat | break` accepted); `>&file` form is a parse error (bash:
`&>file` equivalent when word is non-numeric); fd-move `[n]>&m-` silently
absorbs `-` as an argument; `arr=(...)` accepted as argument to ANY command
(bash: declaration builtins only); function-body/keyword-form coverage holes
(`f() [[ ... ]]`, `function f if`, `function f (subshell)`); POSIX
`for x do` rejected; over-lenient acceptances (empty `[[ ]]`, `; ;`,
newlines in `[[ ]]`, `(( 1+2 ) )`); `}`/`{` at command position run as
commands rc=127 (bash rc=2).

**Expansion:** `${*/pat/rep}` and `${*^}`-family not per-element (the `*`
branch; `@` and `[*]` copies are right); set-but-empty scalar treated as
unset in array-view paths (`x=''; "${x[@]}"` vanishes; `${#x[@]}`→0; ×7
`var.value`-truthiness sites); `:-`/`-` on `"$@"`/arrays tests field-count
not joined-nullness (`set -- ""; "${@:-d}"` → bash `d`, psh empty); extglob
only in final pathname component (also engines); patsub `\&`/`\\` in
expansion results not processed (docstring pins the wrong rule as
"verified"); failglob doesn't abort the statement list; tilde-prefix ignores
following quoted/expansion parts (`~"/sub"` wrongly expands; the assignment
walker has the guard, the field engine doesn't); glob results sorted in C
locale (host bash: locale collation); `${1:=d}` on unset positional silently
succeeds (bash: error); `${a[@]:=d}`/`${a[@]:?}` never error; `$!` treated
as always-set; `set -u; ${#a[@]}` on unset array prints 0 (bash errors);
malformed `@`-transform on unset var errors (bash: empty); un-enabled
extglob `@(a|b).txt` executes as commands (parser-adjacent).

**Executor:** command word expanding to nothing drops exit status and
redirects when no assignments precede (`$(false); echo $?` → 0, bash 1);
`\cmd` wrongly bypasses functions (backslash defeats only aliases);
`|&` implicit `2>&1` applied before (not after) explicit redirects; `wait`
on reaped `$!` → 127 instead of remembered status (POSIX requires memory;
also `wait -f` missing); no signal-death notice for foreground jobs
(`Segmentation fault` etc. never printed); xtrace: for-header traces
expanded items (bash: source words) and no PS4 depth-doubling in cmdsub;
`set -u` arith error message escapes the command's stderr redirect; `time`
ignores TIMEFORMAT; 3-way fd swap `3>&1 1>&2 2>&3` produces wrong routing
at execution (AST is correct — executor/io seam).

**Core/State:** trap surface (13-name whitelist; traps invisible to
`trap`/`trap -p` in subshells/cmdsub; `trap ''` ignore not inherited by
external children for managed signals; `trap -p` output unquotable with
embedded `'`; alphabetical not numerical order); `declare -g` with existing
local writes the LOCAL (global never created); `declare NAME=v` in function
inherits outer attributes into the local (bash: only export); `readonly` in
function creates a vanishing local (bash: global-persistent); `set -o`
can't set underscore-named options and `set +o` output not re-input-able
(POSIX); computed-special coverage (LINENO/EPOCHSECONDS not unsettable;
UID/EUID not readonly-guarded; phantom stored `UID=5`); for-loop nameref
control var writes through instead of re-binding; nameref validation gaps
(`declare -in`, `-n` with invalid name); FUNCNAME set-but-empty outside
functions, no `source` frames, invisible to `declare -p`; `env` builtin
in-process child leaks array mutations (shallow `Variable.copy`);
`local -` accepted but not implemented (leaks options); arithmetic
readonly-assign fatal + "unexpected error" (H6-family).

**Builtins:** `test -o optname` / `test -R` missing; `set -m` doesn't
enable job control in scripts (`fg` fails); `exec -a/-l/-c` missing
("For now" scaffolding); aliases expand non-interactively (bash gates on
`expand_aliases`; also undocumented); `read`/`printf -v` missing identifier
validation (creates unaddressable `a b` variable); `read -d X` drops a
backslash-escaped delimiter; `cd ~/..` leaves un-normalized logical PWD;
`jobs` ignores jobspec operands, lacks `-r/-s/-n`; `history` builtin
skeletal (`-d` broken; `-w/-a/-r/-n/-s` missing; HISTTIMEFORMAT
unsupported; HISTFILESIZE ignored — file trimmed to HISTSIZE); `umask -S
022` silent; `echo -e '\101'` interprets octal without `\0` (contradicts
its own help); `pushd -n` unsupported.

**I/O:** `>&word` non-numeric form (see parser MED); fd-move mangling;
`{fd}>&-` with unset var silently succeeds (bash: ambiguous redirect);
POSIX-mode special-builtin redirect failure should exit.

**Scripting:** CR/CRLF universal-newlines translation rewrites script bytes
(lone `\r` becomes command boundary; bash preserves); LINENO off by one per
preceding line continuation (whole-file pre-join then renumber); stdin-mode
slurps all of stdin (script can't `read` its own remaining stdin as data —
bash shares the fd incrementally); `set --` inside a sourced file reverted
on return (bash: persists); `psh --` with piped stdin enters the REPL and
executes nothing; `source` PATH-search order inverted (cwd before PATH);
`$0` changes inside sourced files (bash: unchanged); `-i -c` doesn't load
rc / `$-` missing `H`; assorted rc divergences (`source unreadable` 126 vs
1; `psh -` unsupported; backslash-at-EOF kept; `--validate` missing-file
rc).

**Visitor/validators:** `--validate` ERRORs on valid static `break N` >
nesting (bash/psh both run it); enhanced validator numeric-comparison
suppression checks the wrong operand side (`[ $x -eq 5 ]` warns — the most
common test idiom); getopts/`printf -v`/mapfile unknown to undefined-var
analysis; non-idempotent blank line after `&`; comment-stripping
undocumented (`--format f.sh > f.sh` is destructive); DebugASTVisitor is
439 lines of fallback-only dead code presented as the live debug formatter.

**Engines:** array-subscript arithmetic errors silently swallowed → index 0
(**`a[08]=Q` overwrites `a[0]`** — write-path data corruption; bash is
fatal); int-literal 64-bit wrap missing (sources vs operations
inconsistent); assoc keys that don't tokenize as arithmetic rejected
(`$((m["k 1"]))`); `nocasematch` not honored by patsub (both auditors);
POSIX classes `punct/cntrl/graph/print` unsupported everywhere + Python
`FutureWarning` leaks to stderr (also hits `[[ =~ [[:space:]] ]]` —
untranslated for Python `re`); `${v/#pat/r}` broken for extglob (the
removal path already solved it; sibling didn't); `++3`/`3++4` not
re-parsed as double unary; `$((0x))`, `$(("16#"ff))` edge literals;
`patsub_replacement` shopt unknown.

**Interactive:** LF/Ctrl-J unbound → multi-line paste merges commands
(pexpect `sendline` hangs); history-reference regex drops legitimate
commands from history (quote/option-blind, checks post-expansion text);
Ctrl-R narrowing skips the current entry; vi-mode counts never work and
accumulate; `len()`-based layout math (no wcwidth — CJK/emoji cursor
desync); `first()`/search return raw multi-line entries the renderer can't
show; `:p` prints 3× and doesn't record; vi Ctrl-D not EOF; Ctrl-C erases
the line + double `^C`; `\w` home-prefix boundary bug (`~2`); prompt escape
gaps (`\j`, `\l`, `\D{}`, 1-2-digit octal); `^old^new` doesn't echo; `:q`/
`:x`/`&`-in-`:s` gaps; split UTF-8 across reads corrupts (needs incremental
decoder); `~` completion → relative `username/`; no emacs undo binding
(infra exists); undo history survives across reads.

**Cross-cutting:** `set -o interactive` (and other INTERNAL options)
user-settable, corrupting `$-` and flipping interactive code paths;
`parser-config enable/disable` writes unregistered names (KeyError under
strict-errors — proving zero coverage) for toggles that never did anything;
accept-and-ignore options (`monitor`, `ignoreeof`, `expand_aliases`,
`parser-mode`, write-only `emacs`/`vi`); README stats stale (8,439/365 vs
actual 9,124/404; LOC/file counts); stale-negative docs cluster (README
claims history designators/modifiers unsupported — they work; ch17
contradicts itself on traps/history; claims `read -u`, `${!prefix*}`,
`@K/@k` unsupported — all work); 51 interactive-dir tests never run in the
gate (3 fail when run, stale xfail reasons); DEBUG trap missing the
function-entry fire under `set -T`; same-line alias define+use expands
(bash: doesn't); `_cleanup_shell` kills only RUNNING not STOPPED jobs;
shadowed duplicate `shell` fixture with the old slow teardown.

---

## Tier 3 — Elegance / dead code (no behavior change)

- **Delete-or-unify list:** `psh/utils/shell_formatter.py` (rotted duplicate
  → D3); heredoc delimiter/terminator logic (3–4 copies, 2 wrong);
  do/then-separator logic ×3 in combinators; combinator dead surface
  (~200-line unused core combinators, unused token parsers, dead
  `parse_partial`/`can_parse`/`explain_parse`, double `configure()` build,
  418-line dead heredoc processor); parser dead error-collection machinery
  (`ErrorHandlingMode`, `ErrorContext.expected`, FATAL severity,
  `create_configured_parser`, unwired STRICT_POSIX); DebugASTVisitor
  fallback-only; `InputSource.get_location`; `PromptManager` getters +
  `REPLLoop.prompt_manager` wiring; `CTRL_UNDERSCORE`; lexer
  `is_inside_expansion`/`normalize_heredoc_delimiter`/`KeywordGuard`/dead
  `PARAM_EXPANSION`; core `_random_last_value`, `ScopeManager.has_variable`;
  expansion `match_extglob` export; `apply_fd_plan(check_noclobber)` dead
  param; `_redirect_clobber` duplicate; PipelineContext write-only state.
- **Structural consolidations suggested:** one heredoc header/trailer seam
  in the formatter; one redirect-error chokepoint (fixes C3 and unifies 4
  message formats); one statement-separator guard (fixes A1); expansion
  `@`/`*`/array operator triple → single per-element engine (fixes the
  `${*}` family); `parse_subshell_group`/`parse_brace_group` copy-paste
  twins; background builtins through `execute_builtin_guarded`; exec's
  duplicated OSError block; `select` writing to `sys.stderr` directly;
  navigation.py mock-defensive try/excepts; `trap_manager` raw `print`.
- **Praise (genuinely textbook):** the option registry + drift-lock test;
  `command_assignments.py`/`child_policy.py` docstring discipline;
  `CommandAccumulator` + `execute_as_main`; `word_expansion_types.py`
  policy table; `param_parser.py` grammar docstring; the arithmetic
  package; the B8 editor decomposition (EditBuffer/KeyDecoder/renderer/
  layout); RedirectPlan/BuiltinRedirectFrame; the combinator `core.py`
  algebra; visitor base/traversal/word_analysis; fork discipline (verified:
  every fork site through the one helper + policy).

---

## Suggested remediation roadmap

**Tier 1 (correctness, ordered by user impact × fix leverage):**
1. **A1+A3** statement-separator guard + group-`&` unification (silent
   misexecution, chokepoint fix).
2. **E1** `adopt()` chokepoint + field-completeness meta-test (`$0` idiom,
   FUNCNAME, traps — seven bugs, one fix).
3. **B1/B2** brace-expansion adjacency (everyday `"$f"{,.bak}`).
4. **D3** delete `shell_formatter.py`, route through formatter visitor
   (declare -f crash + round-trip).
5. **C1/C2/C3** redirect-visibility family + redirect-error chokepoint.
6. **I1/I2** entry-point argument parsing + non-seekable scripts.
7. **K1/K2** history alias contract + parser-driven cmdhist join.
8. **B4** read remainder; **F2** trap 0/N; **G1** case-subject Word
   migration (+ [[ ]] unary operand + here-string target — one Word-layer
   sweep, retires the whole flat-string family incl. #14 H8 leftovers).
9. **H1/H2/H3** engines: `[[ -eq ]]` arithmetic, bracket-pattern crash
   guard, integer division.
10. **F1** cmdsub errexit; **F3** EXIT-on-signal; **A2** `&` command
    position; **A4** `$((` fallback; **A5** line-continuation contexts.
11. **J1–J6** formatter tier (+ regenerate corpora); **L1–L3** combinator
    parity (or narrow its documented scope honestly).

**Tier 2:** the MED lists above, batched by subsystem (trap surface, declare
scope targeting, wait memory, `${*}` per-element, empty-scalar array views,
extglob-in-path, stdin sharing, CR handling, LINENO continuation).

**Tier 3 (process):** M1 meta-test tightening; M2 no-op test deletion;
docs truth-up (stale negatives, README stats); add the new-AST-field
consumer checklist to CLAUDE.md; interactive test tier into the gate or
explicit exclusion note.

---

## Probe coverage note

~2,900 paired probes. Areas re-verified CLEAN this round (fixes from #13/#14
holding): errexit 30-probe matrix, ERR/DEBUG/EXIT fire counts (±errtrace),
PIPESTATUS/pipefail, `time` output format, heredoc core matrix, extglob core
zoo (incl. past-bug adjacents), attribute-application matrix across all 8
assignment paths, seeded RANDOM (value-exact), fd dup/close/swap chains,
noclobber, named-fd `{var}` lifecycle, process-substitution fd hygiene,
history designator/modifier matrix, HISTCONTROL/HISTIGNORE, KeyDecoder
sequences, IFS/field splitting, substrings/slices, indirection, arithmetic
operator zoo + set-u across 7 sites, getopts/read/printf/test option
matrices, source basics, EXIT-trap on 6 normal exit paths, rc-loading
matrix, alias lex-boundary architecture. The known-deferred M8
(heredoc-in-procsub) was **verified fixed** and is removed from the deferred
ledger.
