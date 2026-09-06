# Ground-Up Reappraisal #23 — Correctness & Textbook Quality (v0.779.0)

**Date:** 2026-08-09
**Baseline:** v0.779.0, commit `6459f1a6` (post Boundary Remediation Campaign close)
**Oracle:** `/opt/homebrew/bin/bash` 5.2.26 (PATH bash), macOS
**Method:** 12 subsystem reviewers (recursive-descent parser, combinator parser, and the
lexer each reviewed independently *twice* for cross-validation) plus one black-box
behavioral battery, ~2,000 differential probes total. Every correctness claim was
reproduced against live bash before it was recorded; every headline P0/P1 was
**independently re-verified by the synthesizer** (see §9). No repository file was
modified during the review.

---

## 1. Executive summary

psh at v0.779.0 is a genuinely strong educational shell. Across ~2,000 black-box
differential cells and full line-by-line reads of all ~130k lines, the hard machinery
is bash-faithful: the `$( )` extent scanner, heredoc transaction, `set -e` family (18/18
cells), PIPESTATUS/pipefail, namerefs, computed specials, the POSIX word-expansion
algebra, `[[ =~ ]]` with BASH_REMATCH, extglob, process-substitution fd hygiene, and the
whole redirect-ordering universe all match bash exactly. Textbook quality is the
codebase's standout strength — docstrings routinely state an invariant, name the naive
recipe that violates it, and cite the falsifying input.

The appraisal nonetheless found **8 P0 (user-visible correctness) defects** and roughly
**30 P1 defects**, concentrated in a handful of recurring patterns. The three most serious
are **silent data loss**:

- A function/eval/source body running as a pipeline member drops every command after its
  first *external* command (`f(){ /bin/echo A; echo B; }; f | cat` prints only `A`).
- An in-process compound that closes then reopens fd 1 in one redirect list writes nothing
  (`{ echo hi; } 1>&- 1>f` → empty file, EBADF).
- Redirect targets for fd ≥ 3 on in-process builtins are expanded *twice*, so
  command substitutions run twice and the file actually opened can differ from the one
  `noclobber` checked.

None of these is in the divergence register; all are new. The good news is that most of
the finding count collapses into six **systemic patterns** (§5) with shared, mechanical
fixes — and several patterns have no tooling guard today, which is exactly why they drift
back.

Zero internal defects surfaced under `PSH_STRICT_ERRORS=1` across the entire behavioral
battery — with one exception the lexer reviewer found by construction (`$'\ud800'`, P0-6).

---

## 2. Grades

| Dimension | Overall | Notes |
|---|---|---|
| **Correctness** | **B+** | Main-path parity is A−; pulled down by a tail of silent-data-loss bugs and the combinator parser. |
| **Textbook quality** | **A−** | Best-documented codebase of its kind I have reviewed; deductions are doc/comment drift, not missing explanation. |
| **Pythonic elegance** | **A−** | Frozen dataclasses, typed sums, declarative tables throughout; a few façade/duplication warts. |
| **Efficiency** | **B+** | Linear on realistic input almost everywhere; two reachable super-linear cliffs (lexer heredoc O(n²), combinator ~4^n on invalid input). |

### Per-subsystem (correctness / textbook / pythonic / efficiency)

| Subsystem | Corr. | Text. | Pyth. | Eff. | Headline |
|---|---|---|---|---|---|
| Lexer (2 reviews) | B–B+ | A–A− | A− | C+–B+ | fd-digit theft; `((cmd);cmd)`; `#` comment rule; O(n²) heredoc re-lex |
| Parser — recursive descent (2) | A− | A− | A | A | alias→`for` corrupts loop var (P0); `a[0]=(…)` parse-time rejection |
| Parser — combinator (2) | C+–B− | B–B− | B–B+ | C-–B | `(( ))`/`[[ ]]` trailing redirect inverts exit status; ~4^n on invalid input |
| Executor | B | A− | A− | A | **function-in-pipeline drops commands (P0, silent data loss)** |
| Expansion | A− | A | A− | B+ | unquoted `$*`/`${a[*]}` under empty IFS; `\}` in DQ; value-operand O(n²) |
| Core / state | A− | B+ | B+ | B | `set -u` env fallback; `set -a` misses declaration builtins |
| Builtins | B+ | A | B+ | A- | `printf` option parsing; `int()` acceptance leak (umask stores wrong value) |
| I/O redirect | A− | A | B+ | A− | close-then-reopen EBADF; fd≥3 double-expansion (both silent) |
| AST / visitor / protocols | A− | A | A | A− | formatter drops `${v}` braces → `declare -f` round-trip changes semantics |
| Interactive | B | A− | A− | A− | history numbering positional; tab-completion can't round-trip its own escaping |
| Top-level / utils / scripting | A− | B+ | A− | B | continuation-line `$LINENO`; `-opipefail` invocation parsing; 79% of `--version` startup avoidable |

---

## 3. P0 findings — user-visible correctness (all reproduced and re-verified)

### P0-1 · Executor · A function/eval/source body in a pipeline drops every command after its first external command
`psh/executor/strategies.py:605` (exec branch); root cause `psh/executor/function.py:196`
(`_function_frame` does not save/clear `context.in_pipeline`).

`in_pipeline` means "this process has nothing left to do, exec in place." Only the
control-flow and brace-group frames clear it; function bodies, `eval` text, and sourced
files inherit `in_pipeline=True`, so the first external command `execve()`s over the
pipeline-member process and everything after it is lost — no diagnostic, and the exit
status becomes that command's.

```
$ bash -c 'f(){ /bin/echo A; echo B; }; f | cat'   → A / B
$ psh  -c 'f(){ /bin/echo A; echo B; }; f | cat'   → A          (B lost)
$ psh  -c 'set -o pipefail; f(){ /bin/echo A; false; }; f | cat; echo rc=$?'
        bash rc=1  psh rc=0    (false never ran)
```
Reproduces in `-c`, script, and stdin modes; also via `eval` and `.`/`source`. The
reviewer proved the fix by monkeypatch (`in_pipeline=False` around the body restores all
behaviors). No test pins it — the one function-in-pipeline test uses a single-`echo` body.
**Fix:** clear/restore `in_pipeline` in `_function_frame` and the eval/source frames, or
make the flag one-shot at the member's own dispatch.

### P0-2 · Lexer · `((cmd); cmd)` is mis-lexed as an arithmetic command and poisons the rest of the token stream
`psh/lexer/recognizers/operator.py:53,451`

`((` is matched as `DOUBLE_LPAREN` with no check that a matching `))` exists, so a nested
subshell written without a space mis-lexes, and `arithmetic_depth` never returns to 0 —
so spaces stop terminating words for the entire remainder of the input.

```
$ bash -c '((echo 3); echo 4)'   → 3 / 4
$ psh  -c '((echo 3); echo 4)'   → Parse error (line 1, column 10): Expected ')'
```
psh already implements this disambiguation correctly twice (`scan_double_paren_arithmetic`
for `$((`, and `cmdsub_scanner`), just not in the operator recognizer.
**Fix:** apply the same `))`-lookahead before accepting `((`; emit a single `LPAREN` on
failure. Separately clamp `arithmetic_depth` to 0 on NEWLINE/SEMICOLON so a future mis-lex
cannot corrupt an unbounded suffix.

### P0-3 · Lexer · `#` comment detection keys on the preceding character and is wrong in both directions
`psh/lexer/recognizers/comment.py:26`

`_COMMENT_PRECEDING_OPS` is missing `)` (a metacharacter, so `#` after it *is* a comment)
and wrongly includes `{` (a reserved word, not a metacharacter).

```
$ bash -c '(echo a)#c'   → a          $ psh -c '(echo a)#c'   → Parse error   (valid bash rejected)
$ bash -c 'echo a{#b'    → a{#b       $ psh -c 'echo a{#b'    → a{            (text silently dropped)
```
The `$( )` scanner already uses the correct at-word-start model. **Fix:** adopt it — drop
`{`, add `)`, and consult the predicate only when the collect loop's value is still empty.

### P0-4 · Lexer · An fd-prefix digit is stolen from inside a word after a quote or expansion
`psh/lexer/recognizers/operator.py:438`

fd-prefix redirects are recognized on `isdigit()` with no word-start check, so a digit
glued to the end of a quoted/expanded word is taken as an IO_NUMBER.

```
$ bash -c 'echo "x"2>k; cat k'   → x2
$ psh  -c 'echo "x"2>k; cat k'   → x
```
Same for `${u-x}2>k`, `` `echo x`2>k ``, `"a"{v}>g`. The `>&` variant is worse — it
backtracks *into* the previous token, emitting overlapping spans. **Fix:** gate fd-prefix
recognition on the previous character being a blank/newline/metacharacter; delete the
backtracking branch.

### P0-5 · Lexer · `$(( ))` extent scanning is quote-blind; a quoted paren in a subscript ends the arithmetic early
`psh/lexer/expansion_parser.py:164`

Four lexer call sites of `scan_double_paren_arithmetic` pass the default `quote_aware=False`
even though the helper's own assertion says "expansion callers pass True."

```
$ bash -c 'declare -A m; m[")"]=7; echo $(( m[")"] ))'   → 7
$ psh  -c 'declare -A m; m[")"]=7; echo $(( m[")"] ))'   → (empty) + "m[)]: command not found"
```
**Fix:** pass `True` at all four sites and delete the parameter.

### P0-6 · Lexer · `$'\uXXXX'` / `$'\UXXXXXXXX'` with a surrogate raises `UnicodeEncodeError` — an internal defect under strict-errors
`psh/lexer/pure_helpers.py:414,435`

`chr()` is called with no surrogate guard, and `chr(0xD800)` does not raise `ValueError`,
so the surrounding guard never fires and the lone surrogate escapes to raise at write time.

```
$ bash -c "echo \$'\ud800'" | xxd   → eda0 800a
$ psh  -c "echo \$'\ud800'"          → echo: 'utf-8' codec can't encode character '\ud800'
$ PSH_STRICT_ERRORS=1 psh -c "…"     → Traceback / UnicodeEncodeError
```
psh already owns the correct guarded helper (`psh/utils/escapes.py:53`,
`unicode_escape_char`). **Fix:** route both branches (and `\x`) through it — a one-import
change that also deletes a worse-behaved duplicate.

### P0-7 · Lexer · A `)` closing a function-definition header drops command position, breaking a `case` in the function body inside `$( )`
`psh/lexer/cmdsub_scanner.py:570`

```
$ bash -c 'echo $(f() { case a in a) echo MATCHED;; esac; }; f)'   → MATCHED
$ psh  -c 'echo $(f() { case a in a) echo MATCHED;; esac; }; f)'   → Parse error (rc 127)
```
(The reviewer's original evidence used a non-matching `case x in a)`, which prints empty in
bash — the divergence is genuine either way; the synthesizer re-verified with a matching
subject.) The scanner sets `command_position = False` on the header close, where the
lexer's own transition function sets it *True* precisely because a `)` may close a function
header. **Fix:** set `True` on the depth>0 close; extend the named cmdsub-case conformance
test.

### P0-8 · Recursive-descent parser · An alias that expands to a `for`/`select` header corrupts the loop variable
`psh/parser/recursive_descent/parsers/control_structures.py:220`

`_parse_loop_variable` returns a raw slice of `ctx.source_text`, but alias-body tokens
carry positions in the *alias* text while `source_text` is the pre-expansion line, so the
slice returns unrelated characters that become the loop variable's actual name.

```
$ printf 'shopt -s expand_aliases\nalias beg="for i in 1 2; do"\nbeg echo "i=[$i]"; done\n' | bash   → i=[1] / i=[2]
$ … | psh   → i=[] / i=[]
```
The value is semantically live (`set_variable(node.variable, item)`). **Fix:** store the
token's own `value` as the variable and keep the source slice only for the diagnostic.

---

## 4. Selected P1 findings — latent or narrower correctness

Grouped by subsystem; each was reproduced. Full inventory in §8.

**Silent data loss / wrong value (highest-impact P1s):**
- **I/O `1>&- 1>f` in any in-process compound writes nothing** (`manager.py:518`): the stream
  half installs an opaque EBADF stream over a fd the fd-universe left open. `{ echo hi; }
  1>&- 1>f` → empty, rc 1. Fix: use `_RawFdStream` (reopenable) not `_ClosedStream`.
- **I/O fd≥3 redirect targets expanded twice** (`manager.py:955`): command substitutions run
  twice and `noclobber` checks a different file than the one opened. Fix: apply the
  already-resolved plan instead of re-entering the planner.
- **Builtins `int()` acceptance leak** (`test_command.py:425` + 7 sites): `umask 0_2` *sets the
  mask to 0002*, `umask 0o755` sets 0755, `ulimit -c 1_0` sets 10 — bash rejects all and
  leaves state unchanged. Fix: one `legal_number` helper (base-10, sign, whitespace only).
- **Combinator `(( ))`/`[[ ]]` trailing redirect inverts exit status** (`special_commands.py:161`):
  `(( 0 )) > /dev/null; echo $?` → 0 (bash 1); wrong branch taken in `if`, non-terminating
  `while`. Fix: consume trailing redirects after `))`/`]]`.

**Parser correctness:**
- `for i in 1 2; { echo $i; }` (brace body) rejected (`control_structures.py:186`).
- `echo a=(1)` accepted as an argument to any command (`commands.py:182`).
- `for\ni in …` accepted where bash rejects the newline (`control_structures.py:153`).
- `a[0]=(1 2)` rejected at parse time in a dead branch, where bash defers to runtime.

**Core / expansion / behavioral (the `error_location_prefix` and Python-semantics clusters — see §5):**
- `set -u` re-adds the env fallback the subsystem documents as removed: a declared-unset
  local shadowing an exported outer variable is silently "set" (`core/options.py:78`).
- `set -a` exports only plain assignments, not `declare`/`local`/`readonly`/`typeset`
  (`core/state.py:1047`).
- Unquoted `$*`/`${a[*]}` is join-then-split, diverging under empty IFS
  (`word_expander.py:882`).
- `\}` inside `"${x:-\}}"` keeps the backslash — and stores it for `:=` (`operands.py:466`).
- IFS-whitespace hardcoded `' \t\n'`, missing `\v\f\r` (`word_splitter.py:47`, duplicated in
  `read`).
- `set -n` (noexec) is inert mid-string in `-c` mode; commands keep executing
  (`source_processor.py:523`).
- A bare command substitution does not set `$?` (`$(exit 5); echo $?` → 0).
- Tilde is not expanded in `case` patterns → wrong branch silently taken.

**Interactive:**
- History numbers are list positions, not bash's absolute number, so `!n` selects the
  wrong command after any `$HISTSIZE` trim.
- Tab completion cannot re-complete a path it just escaped (second Tab on any path with a
  space fails).
- Under `set -o vi`, Ctrl-D cannot exit the shell (unbound in both vi tables).
- `\w`/`\W` read the *process* `HOME` and match it as a bare string prefix (also backs
  `${var@P}`, so observable non-interactively). **Security-adjacent:** the terminal-title
  writer (F5) interpolates `$PWD`/command text into an OSC-0 sequence unsanitized, so
  `cd`-ing into a directory whose name contains a BEL + escape hands the terminal a chosen
  sequence. Recommend sanitizing at the single write site.

**AST/visitor:**
- The formatter drops `${v}` braces before a brace expansion, so `${v}{1,2}` round-trips
  through `declare -f`→`eval` as `$v{1,2}` and reads different variables — a real
  `declare -f` contract violation.

---

## 5. Cross-cutting themes (where the finding count actually collapses)

Most of §3–§4 reduces to six systemic patterns. Fixing the *pattern* — and adding the
guard that would keep it fixed — is higher-leverage than fixing findings one at a time.

**T1 — `error_location_prefix()` has drifted back, with no guard.** The v0.690.0 invariant
("one prefix on all non-interactive diagnostics") is violated at **15 executor sites**,
**3 expansion sites**, and shows up in behavioral N5 (10 of 38 divergent cells). The
messages are otherwise byte-correct; they only lose the `<file>: line N:` prefix. Three
independent reviewers found this. There is **no tooling guard** enumerating raw `psh: `
literals, which is exactly why it drifted. *Fix once, add a ratchet.*

**T2 — Python stdlib semantics leaking where bash's C semantics are required.** `int()`
accepts `1_0`/`0o755` (8 builtins, silently wrong values); `chr()` produces a codepoint
where bash produces a byte and admits surrogates (lexer `$'\NNN'`/`\x`/`\u`, P0-6); the
IFS-whitespace class hardcodes `' \t\n'` instead of C `isspace()` (`\v\f\r`, expansion +
`read`). Each is one small helper.

**T3 — Multiple `${…}`/`$((…))` extent scanners that disagree.** `validate_brace_expansion`
(correct: bare `{` does not nest) vs `find_closing_delimiter` (wrong) reachable from
`skip_expansion_region` → the assignment-prefix map; the quote-blind `$((` scan (P0-5).
Both lexer reviewers found the brace-extent disagreement independently. *Route every
`${…}` extent decision through the one authority.*

**T4 — Silent data loss from ordering/re-entry bugs.** The executor pipeline P0, both I/O
P1s, and the combinator trailing-redirect P1 all share a shape: a second pass (re-exec,
re-plan, list-wide stream scan) contradicts a first pass that was correct. These are the
most dangerous findings because they produce a wrong answer with rc 0.

**T5 — Duplicated logic that has drifted.** The combinator's four "word-like" token sets
(none matching the shared `TokenGroups.WORD_LIKE`); the I/O double-plan; `read`'s
stdin-source decision duplicated from `input_reader`; `_evaluate_binary`'s six copy-pasted
try/excepts. The project's own design principle ("a drifted copy hides among its siblings")
predicts exactly these.

**T6 — Documentation/comment drift (the textbook-quality tax).** Ten in-code evidence
citations point into gitignored `tmp/` (five already deleted); ~96 opaque campaign IDs are
unresolvable from the repo; several comments assert the *opposite* of the code
(`arithmetic.py:26` "legacy tokenization", `printf_formatter.py:152` "bash prints '%'",
`create_parser` "zero production callers"). The toplevel reviewer's sharpest point: the
dead `tmp/` citations are *the mechanism by which two false claims in the code survived*.
The project already mandates the fix for subsystem `CLAUDE.md` files (promote probes to
`golden_cases.yaml`, state the invariant not the campaign ID) — apply it to source comments.

---

## 6. What is exemplary (keep and imitate)

The reviewers were unanimous that this is a top-tier teaching codebase. Standouts:

- **`cmdsub_scanner.py`** — the `$( )` extent problem (where does it end when case patterns
  contain unmatched `)`?) solved with an explicit grammar model and a "Maintenance contract"
  docstring naming the owner tests a grammar change must extend.
- **The whole-graph immutability guard** (`test_lexical_value_graph_frozen.py`) — walks the
  live object graph from a real LexedUnit rather than enumerating field names, so it covers
  node types nobody has written yet.
- **Executor process management** — `PipelineContext`'s rolling O(1)-fd construction (with
  the EMFILE story it replaced), `child_policy.map_child_exception`'s taxonomy with a bash
  probe per arm, and `foreground_session.py` opening by naming the drift it prevents.
- **Core's tri-state variable lookup** — making "no cell" vs "declared-but-valueless" a
  *type* is what let the env fallback be deleted from `get_variable` (the one place P1
  quietly re-added it notwithstanding).
- **Expansion's `OperandValue` refusing to be a string** (`__str__` raises `TypeError`, and
  the comment explains why `TypeError` over `PshError` — strict-errors would swallow the
  latter).
- **I/O `fd_remap.py`** — names the two concrete failure modes, then gives the textbook
  two-phase relocation; a student who reads only that file understands why `dup2`+blanket-
  close is wrong.
- **Traversal totality** (`visitor/traversal.py`) — empirically total: a dangerous command
  planted in 11 structurally distinct nested regions is reached in all 11.

---

## 7. Recommended remediation queue

Ordered by user impact × fix cost. All are localized; none requires an architecture change.

**Wave A — silent data loss (do first):**
1. Executor P0-1 (function/eval/source in pipeline) — clear `in_pipeline` in the body frames.
2. I/O P1-2 (`1>&- 1>f`) — `_RawFdStream` not `_ClosedStream`.
3. I/O P1-1 (fd≥3 double-expansion) — apply the resolved plan; add a "plan-once" guard.
4. Combinator P1 (`(( ))`/`[[ ]]` trailing redirect) — consume trailing redirects.

**Wave B — lexer P0 cluster (six small, mostly one-site fixes):**
5. `((cmd);cmd)` (P0-2), `#` comment rule (P0-3), fd-digit theft (P0-4), `$((` quote-blind
   (P0-5), surrogate crash (P0-6), cmdsub function-header case (P0-7). Several share the
   "adopt the model the `$( )` scanner already uses" fix.

**Wave C — systemic patterns with a guard each:**
7. T1: route the 18 drifted diagnostics through `error_location_prefix()`, add a ratchet
   forbidding raw `psh: ` literals in `psh/executor/` and `psh/expansion/`.
8. T2: one `legal_number` helper (builtins), route `chr()` through `unicode_escape_char`
   (lexer), one `IFS_WHITESPACE` constant (expansion + read).
9. T3: route `skip_expansion_region`'s `${` branch through `validate_brace_expansion`.

**Wave D — parser & core conformance:**
10. RD parser: alias-loop-var P0-8, `for`/`select` brace body, `a=(…)`-as-argument gate,
    `for`+newline, `a[0]=(…)` runtime deferral.
11. Core: `set -u` env fallback, `set -a` declaration builtins (both contradict a declared
    invariant; each has an over-claiming "Full support" user-guide row to correct too).

**Wave E — interactive & polish:** history absolute numbering, tab-completion escaping,
vi Ctrl-D, `\w` HOME + the OSC-0 title sanitization (security-adjacent), the formatter
`${v}`-brace fix, and the T6 documentation cleanup.

Deferred / by-design (documented, not queued): the combinator parser's constant 4–6× cost
and double-parse; `$(< file)` shortcut; alias-in-scripts default; the printf `%a` subnormal
divergence; byte-model `\xff` in the escape decoders (LEDGER carry #19). The combinator's
under-acceptance findings are all shielded at the CLI by the RD completeness trial — real
only at the direct API — so they are correctness-relevant for the library, not the shell.

---

## 8. Full finding inventory

Per-subsystem reports with complete evidence and fixes are banked under
`tmp/r23-reports/` (`lexer.md`, `lexer2.md`, `parser-rd.md`, `parser-rd2.md`,
`combinator.md`, `executor.md`, `expansion.md`, `core.md`, `builtins.md`, `io.md`,
`ast-visitor.md`, `interactive.md`, `toplevel.md`, `behavioral.md`, plus
`VERIFICATION-NOTES.md`). Counts: 8 P0, ~30 P1, ~70 P2/P3. The lexer, RD parser, and
combinator parser were each reviewed twice; overlapping findings are noted as
cross-validated in the banked reports (e.g. the dead fd-dup WORD path and the mislabeled
`((…))` "legacy" comment were found independently by both RD reviewers; the `${…}`
brace-extent disagreement by both lexer reviewers; the `(( ))` trailing-redirect P1 by both
combinator reviewers).

**Previously registered (not re-counted as new):** the lexer no-progress crash (confirmed
still live at this commit); the combinator no-`.line` stamping; ParseSession O(k²) /
RESUMABLE-PARSER; the async-reaper family (CR-D1); byte-model `\xff` (LEDGER carry #19);
`exec {v}>&-` with unset `v` (D-5C.2-d2); printf `%a` subnormal (D-5R-d1). Where a reviewer
touched one of these, the note is in the banked report.

---

## 9. Verification & methodology

Every P0 and every headline P1 in §3–§4 was re-run by the synthesizer against
`/opt/homebrew/bin/bash` 5.2.26 before inclusion; all reproduced. One evidence correction
was made during verification: combinator/lexer P0-7's reviewer used a non-matching `case`
subject whose bash output was empty rather than the stated `A` — the divergence is genuine
(psh cannot parse the construct at all) and was re-verified with a matching subject
(`case a in a)` → bash `MATCHED`, psh parse error). This is the one instance where
adversarial re-verification changed a reviewer's stated evidence; no finding was withdrawn.

Reviewers ran read-only; scratch was confined to gitignored `tmp/`. Coverage gaps stated
honestly across the reports: Linux-only paths (local oracle is macOS bash — the I/O
process-substitution FIFO/alarm finding and locale/collation behavior need a Linux oracle
before their bash side is proven), interactive/PTY rendering beyond targeted pty probes,
and wide-character display columns. These are the appropriate targets for the nightly and
for a follow-up interactive-focused pass.

*— Reappraisal #23, synthesized from 12 subsystem reviews + 1 behavioral battery.*
