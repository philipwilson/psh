# Ground-Up Reappraisal #12 — psh v0.472.0 (2026-06-16)

12 parallel subsystem reviewers (read-only), synthesized here. Baseline: reappraisal
#11 (`ground_up_reappraisal_11_2026-06-16.md`, v0.464, overall **A− trending A**) followed
by the full Tier R13 program (v0.465–472: the ~8-bug R13.A cluster, R13.B small features
failglob/read-EOF/neg-array, R13.C typing+dead-code, plus the v0.472 Linux RT-signal fix).

All behavioral findings below were re-verified against live bash 5.2 before inclusion
(`bash -c` vs `python -m psh -c`, exit codes and stderr included).

## Overall grade: **A−** (holding; trending A but the floor showed cracks)

The structure remains A/A+ — the architecture, the visitor totality matrix, the
process/signal model, the typed ShellState decomposition, the combinator FP demonstration
are all excellent, and **every Tier R13 fix verified clean** against bash with no
regressions. Two subsystems *rose* (RD parser and Combinator → **A**).

But the pattern from every prior round repeated, harder: a deeper *functional* dig found
**more genuine bugs than R13 fixed** — and they cluster in user-facing, common-idiom
territory. Highlights:

- **Builtins stays B+** — the R13.A cluster is genuinely fixed, but a *comparable fresh
  cluster* appeared, including two ubiquitous idioms: `[ "$x" == "foo" ]` and
  `[ a -a b ]` both error in psh.
- **Three subsystems slipped to A−** (Core/State, Interactive, Scripting) on freshly-found
  MED/HIGH bugs the structure had been hiding.
- **Cross-cutting slipped to A−**: this round's own *predecessor* over-claimed — R13.C's
  "tree-complete `check_untyped_defs`" left **4 live modules outside mypy scope** (one with
  9 real type errors), and the README test count drifted.
- Two **HIGH** correctness bugs: scripting `$LINENO` is wrong inside every multi-line
  construct, and `psh -c CMD name args` mishandles `$0`/`$@`; plus an **uncaught
  traceback** on a non-UTF-8 script and a `history -c` persistence data-loss.

The architecture is A/A+; correctness is, again, the gap — and this round shows it is a
*deep* gap, not a shrinking one.

## Subsystem scorecard (vs #11)

| Subsystem | #11 | #12 | Movement |
|-----------|----|----|----------|
| Lexer | A | **A** | held; only LOW (byte-model escapes, export-surface, fragile classify) |
| RD parser | A− | **A** | ▲ break/continue arg capture correct & clean; only LOW edge cases |
| Combinator parser | A− | **A** | ▲ FP quality high; now beats RD on some error-rejection paths (educational) |
| Executor | A | **A** | held; one MED `break 0`/neg-N semantics bug (status + levels) |
| Expansion | A− | **A−** | held; `set -u` not enforced for `${var<op>}`, `${arr[i<<j]}` heredoc misdetect |
| Core/State | A | **A−** | ▼ 3 MED: `-i` swallows arith error, `declare -p` assoc-key quoting, assoc key `=`/`]` mis-store |
| Builtins | B+ | **B+** | held; R13 cluster fixed but a comparable fresh cluster found (test `==`, `-a`/`-o`, pwd, type -p…) |
| I/O Redirect | A | **A** | held; only LOW (`>&word` non-numeric) |
| Visitor | A | **A** | held; MED validator chmod false-negative (un-deduped perm check), LOW linter FPs |
| Interactive | A | **A−** | ▼ HIGH `history -c` data loss + MED transpose/Ctrl-U + doc drift |
| Scripting | A− | **A−** | held; HIGH `$LINENO` multi-line + HIGH `-c name args` `$0` + MED non-UTF-8 crash |
| Cross-cutting | A | **A−** | ▼ mypy scope over-claimed (4 modules out, 9 hidden errors), CLAUDE.md stale, test-count drift |

## HIGH findings — genuine bugs (verified vs bash)

1. **Builtins — `test`/`[` rejects `==`.** `test_command.py:330-405`. `x=foo; [ "$x" == "foo" ]`
   → bash exit 0, psh `[: ==: binary operator expected` exit 2. The 4-arg path recognizes
   `==` but the normal 3-arg path does not. Ubiquitous idiom.
2. **Builtins — 3-arg `-a`/`-o` not treated as AND/OR.** `test_command.py:140-143,156-174`.
   `[ a -a b ]` / `[ "$X" -o "$Y" ]` → bash treats as binary AND/OR on truthiness; psh
   `[: -a: binary operator expected` exit 2. The logical-op scan only runs for len>4.
3. **Scripting — `$LINENO` is wrong inside every multi-line construct.** `core/scope.py:614`
   + `scripting/source_processor.py:132-133`. LINENO is set once per buffered logical command
   to the construct's START line, never advanced per physical statement. Function body line 2
   reports 5; while body reports the loop's line; etc. Zero LINENO test coverage. (bash 2 vs
   psh 4 for a function-body echo.)
4. **Scripting — `psh -c CMD name a b` mishandles `$0`/`$@`.** `__main__.py:232-234`. POSIX:
   `$0`=name, `$1`=first arg. psh sets `$1`=name, `$0`=`psh`, `$#` off by one. bash
   `0=name 1=a #=2` vs psh `0=psh 1=name #=3`. Breaks `sh -c '...' progname`.
5. **Builtins — `exit N` does not wrap mod 256 / rejects out-of-range.** `core.py:35-40`.
   `exit 257`→bash 1, psh `exit: 257: numeric argument required` exit 2; `exit -1`→bash 255.
   (`return` already wraps; `exit` is the outlier.) Also `exit 1 2 3` should warn + not exit.
6. **Interactive — `history -c` loses post-clear commands from HISTFILE.**
   `builtins/shell_state.py:25` calls `state.history.clear()` directly instead of
   `HistoryManager.clear_history()`, leaving the `_file_synced_len` persistence marker stale;
   commands added after the clear are dropped by the save slice. Same stale-index class the
   campaign keeps re-finding (R12 fixed the trim path; the `-c` path was missed).
   `HistoryManager.clear_history()` already does it right but has zero production callers.

## MED findings (verified vs bash)

- **Builtins — `pwd` always physical.** `io.py:276-288`. `cd /tmp; pwd` → bash `/tmp` (logical),
  psh `/private/tmp`; `-L`/`-P` unparsed. (`dirs`/`pushd` already use `$PWD`; only `pwd` regressed.)
- **Builtins — `type -p`/`-P` format.** `type_builtin.py:107-116`. `type -p bash` → bash
  `/path`, psh `bash is /path`. Common idiom.
- **Builtins — `getopts` clobbers the positional params** during cluster parsing.
  `positional.py:141-152` mutates `argv[i]` which aliases `state.positional_params`.
  `set -- -abc; getopts abc o; echo $1` → bash `-abc`, psh `-bc`.
- **Builtins — `cd -P`/`-L` unsupported + no "too many arguments" check.** `navigation.py:21-134`.
- **Builtins — `read -u FD` unsupported** (`read_builtin.py:360`); `read -t 0` poll wrong.
- **Expansion — `set -u` (nounset) NOT enforced for any value-substituting `${var<op>...}`**
  on an unset var (`${#x}`, `${x#p}`, `${x^^}`, `${x:0:1}`, `${x@Q}`…). `variable.py:262-269`
  / `operators.py` — the nounset check lives only in the plain-`${var}` path.
  bash exit 127 "unbound variable" vs psh silent empty + exit 0. **Contradicts the user-guide
  `set -u | Full support` claim** (docs/user_guide/17_differences_from_bash.md:574) — the
  CLAIM_TESTS meta-test rule means this needs a proving conformance test that would now fail.
- **Expansion — `${arr[i<<j]}` misdetected as a heredoc.** `utils/heredoc_detection.py:84-109`
  `is_inside_expansion` excludes `<<` inside `$(())`/`$()`/backticks but NOT inside `${...}`,
  so `${arr[1<<1]}` makes the accumulator treat `<<1` as a heredoc and swallow input.
  `echo ${arr[1<<1]}` → bash `c`, psh empty (and in a script, swallows the next line).
- **Core — `declare -i n; n=1/0` silently swallows the arithmetic error.** `scope.py:500-537`
  catches `(ValueError, ArithmeticError)` and returns "0". bash errors + exit 1; psh n=0 exit 0.
  (`n=$((1/0))` and `let` correctly surface it — only the -i-on-assignment path masks it.)
- **Core — `declare -p` of an assoc array isn't re-parseable when a key needs quoting.**
  `declare_format.py:52-56`. psh `[a b]="v"`, bash `["a b"]="v" )` (quoted key + trailing space).
- **Core — assoc element assignment mis-stores keys containing `=` or `]`.** `m["a=b"]=v`
  stores key `a=b` value `b"]=v` (psh) vs key `a=b` value `v` (bash). Expansion-side subscript
  split, corrupts the core array model.
- **Executor — `break 0`/`continue 0`/negative-N wrong in two ways.** `control_flow.py:509-556`.
  bash sets `$?`=1 AND exits ALL enclosing loops; psh returns 0 and exits one level. (Distinct
  from `break 99` which both exit-all-with-0.) The R13 test pins the wrong behavior.
- **Scripting — non-UTF-8 script crashes with an uncaught traceback.** `input_sources.py:60,75`
  opens `encoding='utf-8'` + bare `.read()`; a stray non-UTF-8 byte → UnicodeDecodeError
  escapes (`run_script` only catches OSError). bash runs it fine. Should be a clean error.
- **Interactive — `transpose-chars` (Ctrl-T) and Ctrl-U diverge from readline.**
  `edit_buffer.py:198-223` transpose swaps the wrong pair (and at BOL); `keybindings.py:88`
  binds Ctrl-U to kill-whole-line instead of `unix-line-discard` (kill to BOL). Both pinned
  by tests asserting the wrong behavior.
- **Visitor — `chmod` world-writable check in the enhanced validator is a substring match**
  that misses `757`/`776`/`737`/… `enhanced_validator_visitor.py:576-587`. The SecurityVisitor
  does it correctly via octal bit-check — the #11 perm-list dedup carry-over: the logic is still
  duplicated AND the validator's copy is the buggy one. Lift the bit-check into a shared helper.
- **Cross-cutting — R13.C's "tree-complete check_untyped_defs" is overstated.**
  `pyproject.toml [tool.mypy] files` omits 4 live modules: `parser/combinators/arrays.py`
  (9 genuine mypy errors), `parser/combinators/diagnostics.py`, `expansion/brace_expansion_tokens.py`,
  `expansion/word_expansion_types.py`. mypy "234 files" = 238 − 4. CLAUDE.md:97-102 type section
  is also stale (references the non-existent `psh/ast_nodes.py`; says scope is "core/ + a few
  modules" and "CI enforces it" — tests.yml is disabled).

## LOW / hygiene (selected)

- README test count drift: claims 8,154; actual collection **8,150** (file count 342 correct).
- `pytest` `xfail_strict` not set — a flipped xfail (XPASS) won't auto-flag for removal.
- RD arithmetic `stop_at_double_rparen` still duplicated (`arithmetic.py:48,107`) — #11 carry-over.
- RD `create_configured_parser` is test-only (dead production); reserved closers `}`/`]]` accepted
  at command-start (bash syntax-errors); `2>& 1` spaced fd-dup drops the leading fd (lexer).
- Linter undefined-var check has false-positives (no for-loop-var / read-target / declare tracking).
- Interactive doc drift: history expansion IS implemented but docs say it isn't; tab completion
  is path-only but docs claim command/variable completion + a "(y or n)" prompt that never fires.
- Lexer: ANSI-C high-codepoint escapes (`$'\777'`) emit UTF-8 bytes not raw bytes (the M8 byte-model
  limitation); `KEYWORDS`/`SPECIAL_VARIABLES` importable but not in `__all__`.
- `RETURN` trap unsupported; `exec NAME` not-found wording; `read <&-` EBADF message format;
  glob sort is codepoint not `LC_COLLATE`; `${x~}`/`${x~~}` case-toggle unimplemented.
- DEFERRED (still): `declare -p` empty-array `=()` distinction (needs UNSET-array-state model) —
  NOTE: a reviewer reports bare `declare -a a=(); declare -p a` now matches bash; re-confirm scope.

## Proposed Tier R14 roadmap

- **R14.A — Builtins common-idiom cluster** (highest user impact; gets Builtins off B+):
  test `==`, 3-arg `-a`/`-o`, `pwd` logical + `-L`/`-P`, `type -p`/`-P`, `exit` mod-256 wrap +
  too-many-args, `getopts` positional-clobber, `cd -P`/`-L` + too-many-args, `read -u FD`/`-t 0`.
- **R14.B — correctness cluster**: scripting `$LINENO` per-statement (HIGH) + `-c name args` `$0`
  (HIGH) + non-UTF-8 crash; interactive `history -c` data loss (HIGH) + transpose/Ctrl-U; core
  `-i` error-swallow + `declare -p` assoc-key + assoc `=`/`]` mis-store; expansion `set -u`
  operators (+ the user-guide claim/meta-test) + `${arr[i<<j]}` heredoc; executor `break 0`.
- **R14.C — truth-up typing & hygiene**: add the 4 modules to mypy scope (fix arrays.py's 9
  errors), correct the CLAUDE.md type section, reconcile README test count, add `xfail_strict`,
  document the macOS↔Linux gap in "Known Test Issues", visitor chmod dedup, RD arithmetic dedup,
  linter definition-tracking.

Recommended order: **R14.A (idioms) → R14.B (correctness) → R14.C (truth-up)** — same shape as
R13, bugs first. The recurring lesson, again confirmed: each adversarial round digs a layer
deeper and finds a fresh cluster; the architecture is done, correctness is an ongoing campaign.
