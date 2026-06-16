# Ground-up reappraisal #13 — psh @ v0.485 (2026-06-16)

13th full audit. 12 parallel read-only subsystem reviewers, each anchored to its
prior (#12) grade and the v0.473–485 deltas, with the campaign's hard rule:
**every behavioral finding re-verified against live bash 5.2 before inclusion.**
All findings below were independently re-reproduced by the synthesizer (probe
batches in the session log) — none were over-reported this round, and one
finding lands against *this* campaign's own v0.485 `$LINENO` work.

Baseline: reappraisal #12 (`ground_up_reappraisal_12_2026-06-16.md`, A− holding)
+ Tier R14 (v0.473–485).

## Overall: A− holding — but the floor cracked in four subsystems

Structure remains A/A+ and every R14 fix verified clean (no regressions from
v0.473–485). But the deeper functional dig again out-yielded the fixes: **12
HIGH bugs**, clustered in three recurring themes (heredocs, traps, nested-
execution `$LINENO`) plus a variable-attribute-uniformity seam. Four subsystems
that were A at #12 drop to A− on genuine, common-idiom bugs; none rose.

| Subsystem | #12 | #13 | Movement |
|-----------|-----|-----|----------|
| Lexer | A | **A−** ▼ | `<<\EOF` literal heredoc broken; terminator match too loose |
| RD parser | A | **A** = | only a LOW (`; ;` accepted) |
| Combinator (educational) | A | **A** = | held; one cosmetic idiom-doc gap |
| Executor | A | **A−** ▼ | `wait` no-args `$?` corruption; set -e brace-group exemption |
| Expansion | A− | **A−** = | `set -u` unset array element; (locale collation known) |
| Core/State | A− | **A−** = | fresh attribute-uniformity cluster (3 HIGH) |
| Builtins | B+ | **B+** = | fresh `trap` cluster (2 HIGH) + read IFS, echo `--`, type body |
| IO Redirect | A | **A−** ▼ | heredoc quoted-delim-with-nonword-chars oracle bug |
| Visitor | A | **A−** ▼ | all analysis modes mis-parse heredocs (HIGH) |
| Interactive | A− | **A−** = | history-modifier cluster (`:p`/`:s`/`^a^b`), prompt expansion |
| Scripting | A− | **A−** = | eval/trap `$LINENO` reset-to-1 (2 HIGH — v0.485 gap) |
| Cross-cutting | A− | **A−** = | exec strerror leak; README file-count drift |

## HIGH bugs (all verified vs bash 5.2)

The three dominant clusters first, then standalones.

### Cluster A — heredocs (3 subsystems, very common construct)
1. **`<<\EOF` literal heredoc is broken** — `psh/lexer/heredoc_lexer.py:96-100`. The
   delimiter is recorded verbatim (`\EOF` keeps the backslash; partial-quote
   `<<E"O"F` keeps quote chars) and `quoted` is set only for whole-`STRING`
   delimiters. The recorded delimiter never matches the body's plain `EOF`, so
   the heredoc swallows to EOF and emits nothing.
   `printf 'x=V\ncat <<\\EOF\nval=$x\nEOF\n'` → bash `val=$x`; psh **empty**.
   Fix: one `normalize_heredoc_delimiter(token) -> (literal, was_quoted)` that
   strips backslash/quotes and sets `was_quoted` if ANY quoting/backslash present.
2. **Heredoc quoted delimiter with non-word chars mis-parsed by the completeness
   oracle** — `psh/utils/heredoc_detection.py:19` (`HEREDOC_MARKER_RE` captures
   `(\w+)`). `<<"E F"`, `<<'a|b'`, `<<"x>y"` aren't recognized as open heredocs,
   so the line-by-line `-c`/script/stdin path feeds the body as separate commands.
   `cat <<"E F"` / `content` / `E F` → bash `content`; psh `content: command not
   found`. (The *execution* lexer handles it; only the oracle regex is weak — a
   two-delimiter-parser seam.)
3. **All five analysis modes mis-parse heredocs** — `psh/scripting/visitor_modes.py:22-23,41-42`
   call bare `tokenize()`+`parse()` (not `tokenize_with_heredocs`/`parse_with_heredocs`),
   so a heredoc BODY is analyzed as shell commands. `--security` on a script whose
   heredoc body contains `rm -rf /` reports a HIGH `DANGEROUS_RM` **false positive**;
   `--metrics` counts 4 commands instead of 2; `--validate` flags `$danger` "undefined".
   Fix: route both functions through the heredoc-aware tokenize/parse pair (the
   same path `source_processor.py` already uses).

### Cluster B — `trap` signal-spec normalization (2 HIGH, Builtins/Core)
4. **`trap ... SIGINT` (SIG-prefixed name) rejected** — `psh/core/trap_manager.py:67-81`.
   `signal_map` keys are bare (`INT`); the SIG-prefixed form misses and falls to
   `int("SIGINT")` → "invalid signal specification". `trap 'echo x' SIGINT` (the
   single most common trap idiom) errors; bash accepts.
5. **Numbered trap for a managed signal (1/2/3/15) never fires; the shell dies on
   the default action** — `trap_manager.py:57-128` + `interactive/signal_manager.py:111-115`.
   `set_trap("...","2")` stores key `"2"`, but the SignalManager dispatch looks up
   by canonical NAME (`signal_names[2]`→`INT`), which never matches `"2"`.
   `trap 'echo GOT' 2; kill -2 $$; echo after` → bash `GOT`/`after`; psh **nothing**
   (exits 130). `trap -p` shows the trap, masking it.
   Both 4 & 5 share one root cause and one fix: a `_canonical_signal_key(spec)`
   helper (resolve number / strip `SIG`) used by `set_trap`, reset/ignore, `show_traps`,
   AND the SignalManager lookup so all sites agree on the key.

### Cluster C — nested-execution `$LINENO` (2 HIGH, Scripting — this campaign's v0.485 gap)
6. **`eval` `$LINENO` resets to 1 instead of anchoring at the eval command's line** —
   `eval_command.py:42` → `shell.run_command` → `StringInput("<command>")` whose
   `line_number` starts at 1, so the `start_line>1` offset never fires.
   `eval` on line 3 → bash reports the enclosing line; psh reports 1/2.
7. **DEBUG/ERR trap action `$LINENO` resets to 1** — `core/trap_manager.py:201`
   (`run_command(action)`), same root cause. `trap 'echo ERR at $LINENO' ERR` then
   `false` on line 3 → bash `ERR at 3`; psh `ERR at 1`. Very common debug idiom.
   **The v0.485 eval conformance case is a FALSE POSITIVE** — it ran eval on line 1
   (offset 0), so it passed by luck; the CHANGELOG's "verified value-for-value"
   over-claimed. Fix: thread a base-line into `run_command`/`execute_from_source`;
   nested executions (eval, traps) pass `scope_manager._current_line_number` so the
   buffer offsets from there. (`source` already uses its own FileInput base — leave
   it.) Reuses the existing `_offset_line_numbers` machinery.

### Standalone HIGH
8. **`wait` with no args returns a job's exit status instead of 0** —
   `psh/builtins/job_control.py:210` (`_wait_for_all`). POSIX/bash: no-operand
   `wait` always returns 0. `(exit 42) & wait; echo $?` → bash 0; psh 42 (and
   nondeterministic by job order). Breaks the ubiquitous `cmd & …; wait; check $?`
   pattern. Fix: reap all jobs but `return 0`; only the operand form returns a
   waited status. (Untested — the one no-arg test covers "no child launched".)
9. **`unset NAME` never falls back to unsetting a function** —
   `psh/builtins/environment.py:394-422`. POSIX/bash: `unset name` unsets the var
   if present, else the function. `f(){ echo hi; }; unset f; f` → bash `command not
   found`; psh runs `hi`. Fix: in the non-`-f`/non-`-n` path, fall back to
   `function_manager.undefine_function(name)` when no variable matched.
10. **`declare -a`/`-A` on an existing scalar discards the value** —
    `psh/builtins/function_support.py:362-388`. `x=foo; declare -a x; declare -p x`
    → bash `declare -a x=([0]="foo")`; psh `declare -a x=()`. Fix: seed the new
    array with the old scalar at index `0`/key `"0"`.
11. **Array nameref `r+=(...)` replaces instead of appending** —
    `a=(1 2 3); declare -n r=a; r+=(4); declare -p a` → bash `…[3]="4"`; psh
    `=([0]="4")`. Fix: route `+=(...)` on a nameref through `resolve_nameref_name()`
    (as `r[i]=` already is).
12. **`set -u` not enforced for unset array elements** —
    `psh/expansion/arrays.py:105-128` + `variable.py:153-161`. `set -u; a=(1 2 3);
    echo "${a[5]}"` → bash `a[5]: unbound variable` (exit 127); psh `''` (0). The
    array analog of the scalar `${var op}` nounset bug fixed in v0.480 (scalar path
    checks, array-element paths don't). Fix: check nounset in both element branches
    using the full subscript as the name; do NOT error on `${a[@]}`/`${a[*]}` or
    when a value-operator is present.

## MED findings (verified)
- **`read` mixed-IFS whitespace not absorbed around a non-ws delimiter** —
  `read_builtin.py:294-299`. `IFS=": "` on `"a : b"` → bash `[a][b][]`; psh
  `[a][][b]` (spurious empty field). psh's general word-splitter is correct; only
  `read`'s splitter is wrong.
- **`echo -- hi` strips `--`** — `io.py`. bash `echo` has no `--`; prints `-- hi`.
- **`type <function>` doesn't print the body** — `type_builtin.py:87` (literal
  `# TODO`); `command -V f` already prints it via the declare-f formatter — just wire it in.
- **Formatter drops `[[ ]]` operand quoting** — `formatter_visitor.py:486-492` emits
  pre-expansion unquoted operand strings. `[[ $x == "*.txt" ]]` → `[[ $x == *.txt ]]`
  (literal compare silently becomes a glob; `"a b"` → fails to re-parse). The Word
  nodes carry quote context; format `node.left_word`/`right_word` via `_format_word`.
- **`set -e` exemption lost across a brace group** — `core.py:194-249`. `set -e;
  { false && true; }; echo reached` → bash `reached`; psh aborts. The wrapping
  single-member AndOrList re-sets `errexit_eligible=True`, clobbering the inner
  exemption. (bash applies this through brace groups but NOT subshells/functions —
  psh matches there.) Contradicts user-guide "errexit honours the POSIX exemptions
  exactly as bash."
- **`declare -a a` (declared, never assigned) reports `-v` true and `declare -p`
  shows `=()`** — stores an empty array, can't distinguish declared-unset from
  assigned-empty. `[[ -v a ]]` → bash `unset`; psh `set`. Needs the UNSET-array
  tombstone model (#12's deferred item — now shown to have a `-v` consequence too).
- **`declare -u` (uppercase) not applied to array-element writes** —
  `declare -au a; a[0]=foo; echo "${a[@]}"` → bash `FOO`; psh `foo`. (`-i` IS applied
  to elements — only case-folding is skipped.)
- **History modifiers entirely unimplemented** — `interactive/history_expansion.py:344`.
  `:p`, `:s/a/b/`, `:gs//`, `:h:t:r:e`, `^old^new`, `!#` all error with a misleading
  "bad word specifier" and abort the line. Also: history expansion not done inside
  `"..."` (bash does it), and `\!` doesn't escape `!`. (One test pins the wrong
  dquote behavior — `test_history.py:219` — update vs bash when fixing.)
- **Prompt strings don't undergo `$()`/`$VAR`/`$(())` expansion** — `interactive/prompt.py`.
  `PS1='[$(echo HI)]> '` → bash `[HI]> `; psh literal. Breaks git-branch/`$PWD` prompts.
- **exec-failure messages leak Python's OSError repr** — `executor/strategies.py:80`
  uses `{exc}` not `{exc.strerror}`: `psh: ./x: [Errno 13] Permission denied: './x'`
  vs bash `Permission denied`. Exit codes correct (126/127). Sibling exec/redirect
  paths already use `.strerror` — one inconsistent site.

## LOW / known / discarded
- RD parser accepts consecutive `; ;` (suppresses a syntax error on malformed input;
  output never wrong) — `statements.py` separator loop.
- Lexer terminator match uses `.rstrip()` (`heredoc_collector.py:94`) — a body line
  `EOF ` wrongly ends the heredoc; bash requires exact match. (LOW; pairs with #1.)
- `3<<<x`/`exec 3<<<x` to an explicit fd ≥3 still doesn't materialize the fd —
  **confirmed DEFERRED from #12**, scope unchanged (builtin path routes to fd 0 +
  macOS `/dev/fd` quirk). Not a regression.
- `UID`/`EUID`/`PPID` writable (bash makes them readonly); `<<$DELIM` rejected;
  `declare -n` with no names dumps the whole env; glob locale collation (documented).
- README states 229 psh files / 342 test files (actual 238 / 355); LOC + test count
  within tolerance. Same file-count drift class #12 flagged.
- Discarded (verified non-bugs): error-message PREFIX/wording diffs with matching
  exit codes; extglob/`time`/`{fd}>` undocumented-unsupported features; background
  scheduling races; bash's own `-c 'a;b'` semicolon-abort quirk.

## Root-cause seams (where one fix closes several findings)
- **Two heredoc-delimiter parsers** (oracle regex vs real lexer) + **scattered
  delimiter unquoting** + **visitor bypasses heredoc-aware parse** = the heredoc
  cluster. A shared `normalize_heredoc_delimiter` + having the oracle reuse the
  lexer's recognition + routing `visitor_modes` through `parse_with_heredocs`.
- **Trap key inconsistency** (raw spec vs canonical name) = both trap HIGH bugs;
  one `_canonical_signal_key` helper.
- **No base-line on `run_command`/`StringInput`** = both nested-`$LINENO` HIGH bugs;
  thread a base-line param.
- **Attribute/type semantics centralized for scalars, skipped on array/conversion
  paths** = declare-`-a`/`-A`-scalar-loss + array-nameref-`+=` + `-u`-on-element +
  (set -u element). A single "apply attributes to value written to slot X of var V"
  helper. (Same gap #11/#12 chipped at via `declare -ul`, readonly-array-elem.)

## Proposed Tier R15 roadmap (bugs first, as every prior tier)
- **R15.A — HIGH cluster (12 bugs).** Order by shared root cause:
  A1 heredoc (delimiter normalize #1/#10-LOW; oracle regex #2; visitor parse #3),
  A2 trap (#4/#5 via canonical-key helper),
  A3 nested `$LINENO` (#6/#7 via base-line param — fixes the v0.485 false-positive too),
  A4 attribute uniformity (#10/#11/#12 + `-u`-on-element via shared write helper),
  A5 standalones (`wait` #8, `unset` fn-fallback #9).
- **R15.B — MED cluster:** read mixed-IFS, echo `--`, type body, `[[ ]]` formatter
  quoting, set -e brace-group, declared-empty-array tombstone (`-v`), history
  modifiers `:p`/`:s`/`^a^b`/dquote/`\!`, prompt expansion, exec strerror.
- **R15.C — truth-up:** README file counts; tighten the substring-match tests that
  masked exact-format divergences (exec strerror, eval `$LINENO`); add the missing
  regression pins (heredoc literal/quoted-delim, trap signals, `wait`, nested
  `$LINENO` at line>1, array nounset).

## Lesson (reconfirmed, sharper)
Adversarial functional yield is still non-diminishing at round 13: a single very
common construct — the **heredoc** — was broken in three independent subsystems
that 12 prior rounds never probed adversarially. And the campaign's "audit your
own completeness claims" rule bit its author: the v0.485 eval `$LINENO` conformance
test asserted correctness only at line 1, so a real reset-to-1 bug shipped under a
"verified value-for-value" banner. Nested-execution and array/attribute paths remain
the systematic blind spots — bugs fixed for the scalar/top-level path keep having
un-fixed analogs one level in.
