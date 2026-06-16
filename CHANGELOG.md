# Changelog

All notable changes to PSH (Python Shell) are documented in this file.

Format: `VERSION (DATE) - Title` followed by bullet points describing changes.

## 0.485.0 (2026-06-16) - $LINENO per statement (absolute source lines)
- BUGFIX (scripting). `$LINENO` was set ONCE per buffered command to the construct's
  START line, so it was wrong in EVERY multi-line construct: statements inside
  `if`/`for`/`while`/`until`/`case` bodies, brace/subshell groups, and later pipelines
  of a multi-line `&&`/`||` chain all reported the construct's first line; statements
  inside a function reported the CALL-SITE line instead of the definition line; `-c`
  multi-line text, `eval`, and `source` were similarly off. Now each statement carries
  its absolute source line and `$LINENO` is re-stamped per statement (and per pipeline
  in an and-or chain) right before it runs. Verified value-for-value against bash 5.2.
- Mechanism: `ASTNode` gains an inert `line` class attribute (not a dataclass field —
  AST equality/repr are unaffected). The recursive-descent parser stamps each statement
  and pipeline with its first token's (buffer-relative) line; the source processor offsets
  those to absolute file/`-c`/`eval` lines once per buffer, recursing into function bodies
  so a body bakes in its DEFINITION-site lines (a call-site base would be wrong — a
  function defined in one buffer and called from another must report its def lines). The
  executor re-stamps `$LINENO` per statement in `visit_StatementList`/`visit_TopLevel`
  and per pipeline in `visit_AndOrList`; `source`/function-return restoration of `$LINENO`
  to the caller's line then falls out for free (the next statement re-stamps).
- Function `$LINENO` is now constant across call sites, `LINENO=N` reassignment still
  tracks from N, and `$((LINENO))` agrees — all matching bash.
- TESTS: 29 new (first-ever `$LINENO` coverage) — `tests/conformance/bash/
  test_lineno_conformance.py` (25 cases vs live bash: top-level, all compounds, and-or
  chains, function def-site, nested/mutually-recursive functions, eval, source
  reset+restore, reassignment) and `tests/system/test_lineno_script_file.py` (4 cases
  pinning the FileInput path incl. shebang-comment line accounting).
- KNOWN remaining divergences (pre-existing, orthogonal, NOT fixed here): command
  substitution does not inherit the enclosing line (`x=$(echo $LINENO)` → psh 1, bash 2);
  the physical line counter under-counts after a backslash-newline line continuation
  (continuations are collapsed before line counting). The combinator parser (educational)
  does not stamp lines, so `$LINENO` there falls back to the buffer's start line.

## 0.484.0 (2026-06-16) - Tier R14.C: dedup — visitor world-writable check + RD arith helper
- BUGFIX (analysis) + DEDUP. The `EnhancedValidatorVisitor` chmod check was a substring
  scan (`777`/`666`/`a+w`/`o+w`) that MISSED most world-writable octal modes (757, 776,
  737, ...). It now shares a single `is_world_writable_permission` helper (constants.py)
  with `SecurityVisitor` — an octal mode is world-writable iff the other-write bit is set in
  its last digit. Both visitors now flag the same set; the permission logic is single-sourced.
- DEDUP. The recursive-descent arithmetic parser defined the `))` stop-condition closure
  identically in two methods; extracted to one `_double_rparen_stop(stream)` helper.
- Found by reappraisal #12 (carry-over dedup items). Tier R14.C, batch 2. +1 test.
- Completes Tier R14.C.

## 0.483.0 (2026-06-16) - Tier R14.C: complete the mypy scope (truth-up) + docs + xfail_strict
- TYPING. `check_untyped_defs` / the mypy `files` scope now genuinely covers the WHOLE
  `psh/` tree (238/238 files). R13.C's "tree-complete" claim was overstated — four live
  modules sat outside scope: `parser/combinators/arrays.py` (which had 9 real type errors,
  now fixed via None-narrowing asserts, a `cast` around `ParseResult`'s invariance, and
  typed `words`/`parts` lists), `parser/combinators/diagnostics.py`,
  `expansion/brace_expansion_tokens.py`, `expansion/word_expansion_types.py`. Zero behavior
  change. Caught by reappraisal #12.
- DOCS. Corrected the CLAUDE.md type-checking section (it referenced the long-gone
  `psh/ast_nodes.py`, described the scope as "core/ + a few modules", and claimed "CI
  enforces it" when per-PR CI is disabled). Documented the macOS-local-gate vs Linux-nightly
  platform gap in "Known Test Issues" (the v0.472 RT-signal bug is the canonical case).
- TESTS. Enabled `xfail_strict = true`: a strict-xfail that unexpectedly XPASSES now fails
  the suite, so a feature implemented behind an xfail auto-flags its stale marker.
- Tier R14.C (typing/hygiene truth-up), batch 1.

## 0.482.0 (2026-06-16) - Tier R14.B (interactive): transpose-chars + Ctrl-U match readline
- BUGFIX (behavior). Ctrl-T (`transpose-chars`) now matches readline/bash: it drags the
  character BEFORE point forward over the character AT point and advances point (`abc` with
  point at 1 → `bac`, point 2); at end-of-line it transposes the two characters before point
  (`abc`→`acb`); at beginning-of-line it is a no-op (readline rings the bell). psh previously
  swapped the char at point with the next one and mishandled the BOL case.
- BUGFIX (behavior). Ctrl-U is now `unix-line-discard` (kill from the cursor back to the
  start of the line, KEEPING the text after the cursor), matching bash; it was bound to
  kill-whole-line. New `EditBuffer.kill_to_beginning()`; rebound in both emacs and vi-insert.
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 6. Updated the 2 tests
  that pinned the old transpose behavior; +3 tests.

## 0.481.0 (2026-06-16) - Tier R14.B (executor): break 0 / continue 0 exit all loops, status 1
- BUGFIX (behavior). `break 0`, `continue 0`, and negative counts now report "loop count
  out of range" AND exit ALL enclosing loops with status 1, matching bash. Previously psh
  exited only ONE loop and left status 0. `LoopBreak` gained an optional `exit_status`
  (None for ordinary breaks, which keep the body status); the out-of-range case raises
  `LoopBreak(loop_depth, exit_status=1)` so it propagates through every enclosing loop and
  the loop reports 1.
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 5. Updated the two R13
  tests that pinned the old one-level/status-0 behavior + added a nested-loops test.

## 0.480.0 (2026-06-16) - Tier R14.B (expansion): set -u operators + ${arr[i<<j]} heredoc misdetect
- BUGFIX (behavior). `set -u` (nounset) is now enforced for VALUE-substituting parameter
  operators on an unset variable, matching bash: `${#x}`, `${x#p}`, `${x%p}`, `${x/a/b}`,
  `${x^^}`, `${x,,}`, `${x:0:1}`, `${x@Q}`, etc. all raise "unbound variable" (exit 127)
  when `x` is unset. The set-testing operators (`${x-d}`, `${x:-d}`, `${x=d}`, `${x:=d}`,
  `${x+d}`, `${x:+d}`) remain exempt, a set-but-empty variable is fine, and an unset ARRAY
  ELEMENT (`${#arr[5]}`) stays exempt (bash's deliberate exception). Previously nounset was
  only checked on the plain `${x}` form, so every operator form silently treated unset as
  empty — this also backs the user-guide "set -u | Full support" claim with a proving test.
- BUGFIX (behavior). `${arr[i<<j]}` (a left-shift in an arithmetic array subscript) was
  misdetected as a heredoc operator by the line gatherer, silently swallowing the rest of
  the input. `is_inside_expansion` now recognizes `${...}` parameter expansions (with brace
  nesting), so `<<`/`>>` inside a subscript are arithmetic, not heredocs.
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 4. +13 tests.

## 0.479.0 (2026-06-16) - Tier R14.B (core): declare -i error propagation + declare -p assoc re-parseable
- BUGFIX (behavior). An `-i` (integer) assignment with a malformed RHS or division by zero
  now FAILS with the arithmetic-error message and status 1, instead of silently storing 0.
  `declare -i n; n=1/0` → error + exit 1 (was `n=0`, exit 0); `n=2+` likewise. The integer
  evaluator stopped swallowing `ShellArithmeticError`, so the `-i` path now behaves exactly
  like `$((...))`. An undefined variable (`n=abc`) still resolves to 0 (not an error), matching bash.
- BUGFIX (behavior). `declare -p` of an associative array is now re-parseable: keys that need
  quoting (spaces, `$`, etc.) are double-quoted with escaping (`["a b"]="v"`) — a bare
  `[a b]=` was not re-parseable — and bash's trailing space before `)` is emitted. Simple keys
  (`x`, `a.b`, `1`) stay bare, matching bash. (psh iterates keys sorted; bash uses hash order —
  an accepted deterministic divergence, so multi-key output is verified by round-trip.)
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 3. +8 tests.
- DEFERRED (separate follow-up): an associative-array key containing a literal `=` or `]`
  (`m["a=b"]=v`) is mis-split at parse time — the lexer's subscript map is correct, but a
  parser consumer splits on the inner `=`. Needs parser-level array-element-assignment work.

## 0.478.0 (2026-06-16) - Tier R14.B: history -c no longer drops post-clear commands
- BUGFIX (behavior). `history -c` cleared `state.history` directly, leaving the
  HistoryManager's file-sync marker (`_file_synced_len`) stale. Commands added AFTER the
  clear then fell outside the save slice (`history[_file_synced_len:]`) and were silently
  dropped from HISTFILE — data loss. The builtin now routes through
  `HistoryManager.clear_history()`, which resets the marker, so post-clear commands persist.
  (Same stale-index class as the v0.447 trim-path bug; the `-c` path was the remaining gap.)
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 2. +1 regression test.

## 0.477.0 (2026-06-16) - Tier R14.B: -c name args $0 + non-UTF-8 script no longer crashes
- BUGFIX (behavior). `psh -c COMMAND name arg1 arg2` now follows POSIX: the first operand
  after the command string is `$0` (the command name), and the rest are `$1`, `$2`, …
  (`-c '...' myname a b` → `$0=myname`, `$1=a`, `$#=2`). Previously psh made the name `$1`,
  corrupting `$0`/`$@`/`$#` together and breaking the `sh -c '...' progname` idiom.
- BUGFIX (robustness). A script containing a non-UTF-8 byte no longer crashes psh with an
  uncaught `UnicodeDecodeError` traceback (which also tripped the strict-errors guard).
  Script files are read with `errors='surrogateescape'` and the command-not-found
  diagnostic encodes leniently, so a stray byte becomes a clean "command not found" and
  execution continues — matching bash structurally (both run the surrounding commands,
  exit 0; only the byte's rendering differs, `$'\351'` vs the raw byte).
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 1. +3 tests.

## 0.476.0 (2026-06-16) - Tier R14.A: getopts positional-clobber fix + read -u/-t 0 (R14.A complete)
- BUGFIX (behavior). `getopts` no longer corrupts the positional parameters while parsing a
  clustered option. The old code rewrote `argv[i]` in place to track cluster progress, which
  aliased `state.positional_params` and left `$1` as `-bc` after `set -- -abc; getopts ab o`.
  The within-cluster character position is now tracked out-of-band on `ShellState` (like the
  shell's internal getopts cursor), so a cluster spans calls without mutating `$1..$n`.
- FEATURE. `read -u FD` reads from file descriptor FD (bash); an invalid spec or unopened fd
  reports an error with status 1.
- FEATURE. `read -t 0` is a non-consuming poll: status 0 if the fd is readable (data ready or
  at EOF), 1 if a read would block. Reads nothing, assigns no variables.
- Found by reappraisal #12. Completes Tier R14.A (the common-idiom Builtins cluster). +8 tests.
- KNOWN (separate, pre-existing, NOT R14.A): here-strings/heredocs redirected to an explicit
  non-zero fd (`3<<<x`, `exec 3<<<x`) do not materialize that fd — affects external commands
  too; `read -u 3` works with file-backed fds (`exec 3< file`). Noted for a future tier.

## 0.475.0 (2026-06-16) - Tier R14.A: exit status semantics + cd -L/-P
- BUGFIX (behavior). `exit` now matches bash on three points: (a) bare `exit` uses `$?`
  (the last command's status), not 0 — `false; exit` now exits 1; (b) a numeric argument
  wraps modulo 256 (`exit 257`→1, `exit -1`→255, `exit 300`→44) instead of erroring on
  out-of-range; (c) too many arguments reports "too many arguments" and does NOT terminate
  the shell (status 1, execution continues). A non-numeric argument still errors + exits 2.
- BUGFIX (behavior). `cd` now accepts the `-L` (logical, default) / `-P` (physical) options
  — previously a leading `-P`/`-L` was treated as a directory operand (`cd: -P: No such
  file or directory`). `cd -P` records the symlink-resolved physical path as `$PWD`. And
  `cd a b` is now "too many arguments" (status 1, no chdir) instead of silently cd-ing to
  the first operand.
- Found by reappraisal #12. +12 conformance tests.

## 0.474.0 (2026-06-16) - Tier R14.A: pwd logical default, type -p/-P bare-path output
- BUGFIX (behavior). `pwd` now prints the LOGICAL path by default (and with `-L`) — the
  shell's `$PWD`, which preserves the symlink-named path you cd'd through — matching bash;
  previously it always printed the physical (resolved) path. `-P` prints the physical path.
  Falls back to physical when `$PWD` is stale (no longer names the cwd). `pwd -L`/`-P` flags
  are now parsed (were previously treated as directory operands → error).
- BUGFIX (behavior). `type -p` / `type -P` now print the BARE path (`/bin/ls`) instead of
  the `ls is /bin/ls` banner, matching bash — `type -p NAME` is a common "get the path"
  idiom. `-p` still prints nothing for builtins/functions/keywords; `-P` forces PATH search.
- Found by reappraisal #12. +4 regression tests; the prior weak `type -p` test
  (`endswith('/ls')`, which the buggy banner also satisfied) was strengthened to pin the
  bare-path format.

## 0.473.0 (2026-06-16) - Tier R14.A: test/[ `==` synonym and 3-arg `-a`/`-o`
- BUGFIX (behavior). `test`/`[` now accepts `==` as a synonym for `=` (bash extension;
  literal string equality, NO globbing — unlike `[[ ]]`). `[ "$x" == foo ]` — an
  extremely common idiom — previously errored `[: ==: binary operator expected` (exit 2).
- BUGFIX (behavior). The 3-argument XSI binary primaries `-a`/`-o` now work:
  `[ s1 -a s2 ]` is the AND of the two operands' string non-emptiness, `[ s1 -o s2 ]`
  the OR (`[ a -a b ]` → 0, `[ "" -a b ]` → 1, `[ a -o "" ]` → 0). Previously errored
  `[: -a: binary operator expected`. The multi-arg `-a`/`-o` that combine whole
  expressions (`[ -f x -a -d y ]`) are unaffected (separate dispatch path).
- Found by reappraisal #12 (the two highest-impact common-idiom bugs). +11 conformance
  tests. (README test count corrected to the true collected total, 8,161 — reappraisal
  #12 noted a prior drift.)

## 0.472.0 (2026-06-16) - Fix: real-time signal listing on Linux (kill -l / trap -l)
- BUGFIX (behavior, Linux). `kill -l` and `trap -l` listed only `SIGRTMIN` (34) and
  `SIGRTMAX` (64), omitting the 29 intermediate real-time signals bash enumerates
  (`SIGRTMIN+1`..`SIGRTMIN+15`, `SIGRTMAX-14`..`SIGRTMAX-1`, numbers 35–63). Root cause:
  `signal_utils._build_number_to_name()` is built from Python's `signal.Signals` enum,
  which on Linux exposes only the two RT endpoints as members. The mapping now fills the
  whole `[SIGRTMIN, SIGRTMAX]` range using bash's `SIGRTMIN+n`/`SIGRTMAX-n` naming (names
  from whichever end is closer; tie → RTMIN side), so both listings (and name→number
  lookups like `kill SIGRTMIN+5`) match bash byte-for-byte. Guarded by `hasattr`, so
  macOS/BSD (no real-time signals) are unaffected.
- Caught by the nightly full+bash run on Linux (the local gate runs on macOS, where RT
  signals don't exist). +6 unit tests (RT-naming arithmetic pinned platform-independently;
  Linux-conditional table check).

## 0.471.0 (2026-06-16) - Tier R13.C: complete check_untyped_defs + dead-code/dup polish
- TYPING. `check_untyped_defs` now covers the LAST 11 in-scope modules (psh, __main__,
  shell, version, parser config/__init__/visualization), completing it across the entire
  mypy-checked tree. This surfaced a real latent type smell in `__main__.py` — argparse
  options live in a `Dict[str, object]` (its build loop assigns by dynamic key, so it
  cannot be a TypedDict) and were passed straight to `Shell`'s typed constructor params;
  fixed with explicit `_flag`/`_opt_str` converters at the call site.
- DEAD CODE. Removed unused lexer constants `VARIABLE_START_CHARS`/`VARIABLE_CHARS`
  (lexer/constants.py) and unused recursive-descent methods `Parser.create_with_config`,
  `Parser.from_context`, and `ContextBaseParser.previous` (no production or test callers —
  the similarly-named test exercises `create_context`, not the classmethod).
- DEDUP. `EnhancedValidatorVisitor`'s test-operator quoting heuristic now derives its
  `file_ops`/`string_ops` from the shared `FILE_TEST_OPERATORS`/`STRING_COMPARISON_OPERATORS`
  constants (plus its extra forms) instead of re-listing the operators.
- META-TEST. Added a `KEYWORDS` (lexer/constants.py) ↔ `KEYWORD_TYPE_MAP` (lexer/keyword_defs.py)
  sync test: adding a keyword to one table without the other now fails the suite.
- Found by reappraisal #11. Zero behavior change. +2 meta-tests. Completes Tier R13 (A+B+C).

## 0.470.0 (2026-06-16) - Tier R13.B: failglob, read EOF status, negative-array-read warning
- FEATURE. `shopt -s failglob` is now implemented: a pathname pattern with no matches
  fails the command with "no match: PATTERN" on stderr (status 1) instead of passing the
  pattern through, matching bash. It does not abort the shell (per-command failure) and
  does not affect assignment RHS (which is never globbed). New non-fatal `GlobNoMatchError`
  raised from the single `_glob_words` choke point; obsolete xfail ledger entry removed.
- BUGFIX (behavior). `read` now reports EOF-before-delimiter as failure (exit 1) on ALL
  paths while still assigning whatever was read, matching bash — previously only the
  empty-newline case returned 1, and a partial last line (`printf 'abc' | read x`), a
  custom `-d` delimiter, or `-n` hitting EOF all wrongly returned 0. Empty EOF now also
  CLEARS the target variable (bash) instead of leaving its prior value. The three readers
  were refactored to a shared `(data, status)` contract; timeout (142) is reserved for the
  budget actually expiring. 4 pinned-quirk tests updated to the bash-correct results.
- BUGFIX (behavior). An out-of-range NEGATIVE array read (`a=(1 2 3); ${a[-5]}`) now warns
  "bad array subscript" on stderr and expands to empty (exit status unaffected), matching
  bash; psh was silent. New `IndexedArray.negative_out_of_range` predicate gates the warning
  at the `${arr[i]}` expansion site (a positive out-of-range index stays a silent unset read).
- Found by reappraisal #11. +9 regression tests (failglob ×3, read EOF ×4 incl. var-clear/
  multivar, negative-array ×2).

## 0.469.0 (2026-06-16) - Tier R13.A (parser/executor): break/continue argument validation
- BUGFIX (behavior). `break`/`continue` silently dropped any non-digit argument: the
  parser only consumed the level token when it was `.isdigit()`, so `break foo` parsed
  as `break` plus a stray `foo` command, and `break $n` ignored the variable entirely
  (always broke one level). The level is now captured as argument Words and validated at
  RUNTIME, matching bash (16 probes):
  - non-numeric (`break foo`, `break ""`) → "break: ARG: numeric argument required",
    exit 128, and a non-interactive shell ABORTS (break/continue are POSIX special
    builtins);
  - `break $n` / `break "$n"` → expanded then applied (now breaks N levels);
  - `break 0` / negative → "loop count out of range", exits one loop level, status 0
    (bash quirk: `continue 0` also exits the loop);
  - `break 1 2` or a variable that word-splits to two fields → "too many arguments",
    exit 1, aborts;
  - a NEVER-EXECUTED bad argument (`if false; then break foo; fi`) is NOT an error
    (validation is at runtime, not parse time — bash-matched).
- AST: BreakStatement/ContinueStatement gain `level_words: List[Word]` (the int `level`
  field is kept for hand-built/combinator nodes); a shared `literal_loop_control_level`
  helper feeds the validator and the pretty-printers. The RD parser, executor
  (`_resolve_loop_control_level`), shell_formatter, formatter/validator/debug_ast visitors
  were updated; combinator parser behavior unchanged (educational).
- Found by reappraisal #11. +13 regression tests (TestBreakContinueArgumentValidation).
- Fifth batch of Tier R13.A.

## 0.468.0 (2026-06-16) - Tier R13.A (core/io/executor): readonly array writes, noclobber message, exec diagnostic
- BUGFIX (behavior). Writing an ELEMENT of a readonly array silently succeeded
  (`a=(1 2); readonly a; a[0]=X` set the element; bash errors with status 1 and
  leaves the array unchanged). `execute_array_element_assignment` now gates on
  `var_obj.is_readonly` before the write; the nameref/`set_var_or_array_element`
  path is gated too. Indexed and associative arrays both covered.
- BUGFIX (behavior). `+=` append to a readonly array printed the error but STILL
  mutated the array (`a=(1 2); readonly a; a+=(9)` left `a` as `1 2 9`). The append
  builds in-place into the existing array, so the mutation persisted before
  `set_variable` raised. `execute_array_initialization` now gates on readonly up
  front, before building.
- BUGFIX (cosmetic). noclobber diagnostic word order now matches bash:
  `TARGET: cannot overwrite existing file` (was `cannot overwrite existing file:
  TARGET`). All three raise sites (file/builtin/child backends) updated.
- BUGFIX (cosmetic). `exec >FILE` failing on an errno-less redirect error
  (noclobber/ambiguous/bad-fd) printed `psh: exec: None`; it now prints psh's own
  complete message (mirrors `setup_child_redirections`), e.g. `psh: FILE: cannot
  overwrite existing file`.
- Found by reappraisal #11. +4 regression tests (readonly array element/assoc/append,
  exec noclobber diagnostic).
- Fourth batch of Tier R13.A.

## 0.467.0 (2026-06-16) - Tier R13.A (core): declare -u/-l mutual exclusion + tombstone attribute mutation
- BUGFIX (behavior). `declare -u` and `declare -l` are mutually exclusive; psh kept both
  flags and folded by flag order. bash has two rules, all now matched (13/13 probes):
  - Both flags in ONE declaration cancel — apply NEITHER, and clear any case attribute the
    name already carried (`declare -ul y; y=HeLLo` → `HeLLo`; `declare -u y=X; declare -ul y`
    → unfolded). `_attributes_from_options` no longer does "last-wins"; both-flags now also
    add LOWERCASE|UPPERCASE to the removed set so a pre-existing case attr is cleared.
  - Across SEPARATE declarations the last wins (`declare -u y; declare -l y; y=HeLLo` →
    `hello`).
- BUGFIX (behavior). Attribute mutation silently no-op'd on declared-but-unset variables.
  `apply_attribute`/`remove_attribute` looked up the target via `get_variable_object`, which
  hides UNSET tombstones, so `declare -u y; declare -l y` (and even `declare -u y; declare
  +u y`) left the original flag stuck. New `ScopeManager._find_variable_for_mutation()` is
  tombstone-aware and used by both mutators; the declare dispatch now routes declared-but-unset
  names through them (via `get_declared_variable_object`). `_apply_attributes` also treats a
  both-case-bits value as a no-op defensively.
- Found by reappraisal #11. +7 conformance tests (TestDeclareCaseFlagMutualExclusion).
- Third batch of Tier R13.A.

## 0.466.0 (2026-06-16) - Tier R13.A (expansion): anchored empty-pattern substitution ${x/#/…}/${x/%/…}
- BUGFIX (behavior). `${x/#/PRE}` and `${x/%/SUF}` (anchored substitution with an EMPTY
  pattern) were no-ops; bash matches the empty string at the start/end and
  prepends/appends the replacement (`x=hello; ${x/#/PRE}` → `PREhello`,
  `${x/%/SUF}` → `helloSUF`, and on an empty value `${x/#/PRE}` → `PRE`).
  `operators._substitute` short-circuited `if not pattern: return value` for ALL four
  operators; the early-return is now gated to the unanchored `/` and `//` (which DO no-op
  on an empty pattern), so `/#` and `/%` fall through to substitute_prefix/substitute_suffix
  (already correct). Found by reappraisal #11. +2 regression tests.
- Second batch of Tier R13.A.

## 0.465.0 (2026-06-16) - Tier R13.A (builtins): test -v, getopts OPTARG, lone `test !` (reappraisal #11)
- BUGFIX (behavior). Three genuine bash divergences in the test/getopts builtins, found by
  reappraisal #11:
  - **`test -v VAR` / `[ -v VAR ]` now works** — it had NEVER worked (`evaluate_unary`
    returned the sentinel exit 2 for every name). Implemented via a shared `variable_is_set`
    helper (`test_command.py`) that the `[[ -v ]]` evaluator now also delegates to (dedup);
    supports `name` and `array[key]` (indexed/associative). `x=5; test -v x` → 0; unset → 1.
  - **`getopts` non-silent invalid option leaves `OPTARG` unset** (was set to the bad char);
    silent mode (`:abc`) still records the char — matching bash and the missing-arg branch.
  - **A lone `test !` / `[ ! ]` is the one-argument non-empty-string test (exit 0)**, not
    negation-of-empty (was exit 1); `!` still negates a following operand.
  - +regression tests (test_test_builtin: -v scalar/array, lone-bang; getopts conformance:
    loud-mode OPTARG-unset). Removed the now-obsolete `test_absent_features::test_test_dash_v`
    (was a strict-xfail "absent feature").
- First builtins batch of Tier R13.A. (Deferred within R13.A: `declare -p` on a bare empty
  array prints `=()` — the correct fix needs an UNSET-array-state model so a bare
  `declare -a a` is distinguished from `a=()`, which touches array set/unset semantics.)

## 0.464.0 (2026-06-16) - Tier R12.B finale: check_untyped_defs for the combinator parser (12/12 packages)
- TYPING (no behavior change). Enabled `check_untyped_defs = true` for the last package,
  `psh.parser.combinators.*` — mypy now body-checks **every package (12/12)**. Fixing the
  ~34 fallout errors was two kinds of change, both type-only:
  - `Parser.or_else` now types its alternative/result as the loose `Parser` rather than
    `Parser[T]`: the shell grammar composes ordered choice over *heterogeneous*
    productions (`arithmetic_command.or_else(enhanced_test_statement)` yields one node
    type OR another), which `Parser[T]` cannot express. Runtime behavior unchanged
    (the parity suite confirms).
  - Added `assert … is not None` narrowing after the `result.success` checks where the
    code reads `result.value.<attr>` (redirections, pipelines, simple-command, subshell/
    brace bodies, expansion-to-word, top-level wrap) — the same idiom used elsewhere; and
    loosely typed one heterogeneous parser list.
- Completes the Tier R12.B typing rollout (3/12 → 12/12) AND the last open thread from
  reappraisal #10. `tests/parser_differential` parity + full suite green.

## 0.463.0 (2026-06-15) - Tier R12.D.6: dedup RD array-initializer head detection (review M4/dedup) — R12.D complete
- REFACTOR (no behavior change). `CommandParser._check_array_initialization` (argument
  position, e.g. `declare -a a=(1 2)`) duplicated the `name=(...)`/`name+=(...)` head
  detection that `ArrayParser._candidate_initializer` (statement position, e.g. `a=(1 2)`)
  already performs. It now delegates detection to that single peek-only classifier (which
  reports `head_token_count`), then does its own token-consume + head-Token synthesis. The
  element-collection loop was already shared (`parse_array_init_elements`); this removes the
  last copy — head detection now lives in one place. Single-token, split, and spaced
  (`declare a = (...)`) forms all preserved; 804 array/declare/parser tests green.
- Sixth item of Tier R12.D. **Tier R12.D complete** (v0.458–463: combinator dedup, dead-code
  & stale-doc sweep, rm-rf security heuristic, io-redirect dispatch dedup, declare-method
  split, array-init dedup).

## 0.462.0 (2026-06-15) - Tier R12.D.5: split the 195-line declare `_declare_variables` method (review M4)
- REFACTOR (no behavior change). `_declare_variables` (builtins/function_support.py) — the
  longest method in the codebase (~195 lines, reappraisal #9 M4) — is now a small
  dispatcher over three extracted helpers: `_declare_list_all` (no-argument listing),
  `_declare_assignment` (`NAME=value`/`NAME+=value`: nameref, array-init, scalar-into-array,
  regular scalar), and `_declare_bare_name` (declare/modify by name only). The per-argument
  loop now reads `rc = self._declare_assignment(...)` / `_declare_bare_name(...)` and stops
  on the first non-zero (an invalid name / nameref self-ref), matching bash. Logic moved
  verbatim; all 1054 declare/array/builtin tests green.
- Fifth item of Tier R12.D.

## 0.461.0 (2026-06-15) - Tier R12.D.4: collapse apply_permanent_redirections dispatch (review M7)
- REFACTOR (no behavior change). `FileRedirector.apply_permanent_redirections` (the
  `exec`-redirection path) re-enumerated every `redirect.type` to choose a stream rebind
  even though the planner already computed `plan.target_fd`. Collapsed the seven-branch
  chain to direction-based dispatch: combined (`&>`) rebinds 1+2; a dup/close
  (`&` in the type) rebinds its own fd (close → nothing); input forms (`<` prefix)
  rebind stdin; output forms (`>`/`>>`/`>|`) rebind the target fd. The residual of
  reappraisal #9 M7. All 245 redirection tests green (including the `exec >&-` close-fd
  case that a first cut regressed and that now pins the dup-vs-close distinction).
- Fourth item of Tier R12.D.

## 0.460.0 (2026-06-15) - Tier R12.D.3: security visitor detects recursive+force rm in all flag spellings
- IMPROVEMENT (security analysis). `SecurityVisitor`'s dangerous-`rm` check matched only
  the literal `-rf` substring of the joined args, so `rm -r -f /`, `rm -fr /`,
  `rm --recursive --force /etc`, and `rm -rvf /var` went unflagged (and a filename
  containing `-rf` could false-match). It now inspects the actual argv flag tokens via a
  new `_rm_is_recursive_force` helper — recognising clustered (`-rf`/`-fr`/`-Rf`/`-rvf`),
  separate (`-r -f`), and long (`--recursive --force`) forms — and only flags a sensitive
  target (`/`, `/*`, `/bin`, `/usr`, `/etc`, `/var`, `/home`) when BOTH recursive and
  force are present. Found by reappraisal #10. +7 unit tests.
- Third item of Tier R12.D.

## 0.459.0 (2026-06-15) - Tier R12.D.2: dead-code & stale-doc sweep
- REFACTOR (no behavior change). Removed verified-dead code flagged by reappraisals
  #9/#10:
  - RD parser: `TokenGroups.COMMAND_LIST_END` (defined, never used);
    `WordBuilder.build_word_from_string` (a TODO stub with zero real callers — the
    similarly-named test exercises `build_word_from_token`, not this).
  - Visitor: the two `word_analysis` helpers with zero references anywhere
    (`has_process_substitution`, `expansion_source_text`); documented the remaining
    `has_*`/`referenced_*`/`is_*` helpers as an intended, tested Word-analysis library
    surface (review M6). Dropped the unreachable `'777'/'0777'` branch in
    `security_visitor._is_world_writable_permission` (the digit-regex branch above it
    already returns for those).
  - Scripting: the dead `InteractiveInput` class (`input_sources.py`; REPL input is
    handled by `psh/interactive/`); the write-only `_last_hint` field in
    `command_accumulator.py` (assigned three times, never read).
- DOCS. Fixed stale references: `docs/subsystem_internals.md` no longer lists the
  removed `AliasExecutionStrategy` as a live execution strategy (alias expansion moved to
  the lex→parse boundary in R8.6b); `psh/core/CLAUDE.md`'s Key Files table now lists the
  extracted sub-objects (`execution_state`/`history_state`/`terminal_state`/
  `stream_bindings`) and `internal_errors.py`.
- Second item of Tier R12.D.

## 0.458.0 (2026-06-15) - Tier R12.D.1: combinator dedup — drop dead pipeline/and-or duplicates, document the cut channel
- REFACTOR (no behavior change). Deleted the two dead module-level functions
  `parse_pipeline` / `parse_and_or_list` from `parser/combinators/commands/__init__.py`
  — independent reimplementations of the `PipelineMixin` methods that were exported but
  never called (the live parser uses the mixin; the parity tests use the full parser).
  Removed from both `__all__` lists. (`parse_simple_command` / `create_command_parsers`
  are kept — still used by tests / `parser.py`.)
- DOCS. Documented `ParseResult.committed` as reserved-but-inert: commitment is currently
  expressed by raising a `ParseError` via `raise_committed_error` (the imperative cut),
  while the in-algebra `committed` channel (honoured by `or_else`/`many`/`separated_by`)
  is kept ready for the eventual exception→return migration — wired-but-inert by design,
  not dead code (a reappraisal-#10 reviewer flag).
- First item of Tier R12.D (dedup/polish).

## 0.457.0 (2026-06-15) - Tier R12.C: extract ExecutionState from the ShellState god-object
- REFACTOR (no behavior change). Lifted the eight per-command execution-scratch fields
  off `ShellState` into a cohesive `ExecutionState` sub-object
  (`psh/core/execution_state.py`): `last_exit_code`, `last_bg_pid`, `foreground_pgid`,
  `command_number`, `pipestatus`, `errexit_eligible`, `last_cmdsub_status`,
  `in_forked_child`. `ShellState` keeps `self.execution` and exposes all eight as
  delegating properties, so every existing call site (`shell.state.last_exit_code`, …)
  is untouched — same "typed sub-object + delegating properties" pattern as
  `TerminalState`/`HistoryState`/`StreamBindings`. This is the twice-deferred #9 M1 /
  #10 finding; it shrinks the god-object and makes subshell adoption a single
  `parent.execution.copy_into(self.execution)` — so a new execution field can no longer
  be silently omitted from `adopt()` (the structural cause of the v0.453 `$!`-in-subshell
  bug). +5 unit tests. mypy/ruff clean; full suite green.
- Tier R12.C.

## 0.456.0 (2026-06-15) - Tier R12.B batch 3: check_untyped_defs for ast_nodes + recursive-descent parser (R12.B done)
- TYPING (no behavior change). Enabled `check_untyped_defs = true` for `psh.ast_nodes.*`
  and the PRODUCTION parser `psh.parser.recursive_descent.*` (both zero-fallout). mypy
  now body-checks **all production code**; the only package still not body-checked is the
  educational combinator parser `psh.parser.combinators.*` (~43 errors — deferred to a
  dedicated pass, since it's outside the production quality bar).
- **Tier R12.B substantially complete** (v0.454–456): the `check_untyped_defs` rollout
  went from 3/12 to 11/12 packages — every production subsystem is now body-checked — and
  along the way caught real `declare -f` formatter bugs (v0.455). The clearest A−→A lever
  from reappraisals #9/#10 is realized.

## 0.455.0 (2026-06-15) - Tier R12.B batch 2: check_untyped_defs for utils/interactive/scripting (+ found real declare -f bugs)
- TYPING + BUGFIX. Enabled `check_untyped_defs = true` for `psh.utils.*`,
  `psh.interactive.*`, `psh.scripting.*` — mypy now body-checks **10 of ~12** packages.
  Fixing the fallout surfaced two GENUINE latent bugs in `utils/shell_formatter.py`
  (the `ShellFormatter` used by `declare -f` / `type` to display function bodies):
  - **BUGFIX (behavior):** `declare -f` on a function containing a C-style `for ((;;))`
    loop raised `AttributeError: 'CStyleForLoop' object has no attribute 'init'` — the
    formatter referenced `.init`/`.condition`/`.update` instead of the real
    `.init_expr`/`.condition_expr`/`.update_expr`. Likewise `break`/`continue` with a
    level referenced `.levels` instead of `.level`. Both now format correctly.
  - The remaining fallout was type-only (annotations / None-guards in
    `scripting/input_sources.py`, `interactive/signal_manager.py`,
    `interactive/repl_loop.py`); no behavior change there.
  - +regression tests: formatter unit tests (C-style for, break/continue level) and
    `declare -f` integration tests; a `CaseItem`/`str` loop-variable type confusion in
    the formatter was also cleaned up.
- Second batch of Tier R12.B. (Remaining un-body-checked: parser + ast_nodes.)

## 0.454.0 (2026-06-15) - Tier R12.B: mypy check_untyped_defs for io_redirect/lexer/visitor/builtins (batch 1)
- TYPING (no behavior change). Enabled `check_untyped_defs = true` for four more
  packages — `psh.io_redirect.*`, `psh.lexer.*`, `psh.visitor.*`, `psh.builtins.*` —
  joining core/expansion/executor. mypy now body-checks **7 of ~12** packages and stays
  clean (these four had zero fallout: the annotation-unchecked notes were just notes,
  not errors). The clearest A−→A lever from reappraisals #9/#10; remaining:
  utils/interactive/scripting (small fallout to fix) and parser/ast_nodes.
- First batch of Tier R12.B.

## 0.453.0 (2026-06-15) - BUGFIX: sparse-array negative-index reads + `$!` subshell inheritance — R12.A (cluster complete)
- BUGFIX (behavior). Two core bugs found by reappraisal #10:
  - `IndexedArray.get()` resolved a negative subscript by indexing the list of *set*
    indices, which disagreed with the write path (`resolve_write_index`, "highest index
    + 1 + index") and with bash on SPARSE arrays. `${a[-2]}` on `a[0]=x; a[5]=y` gave
    `x` (bash: empty, slot 4 unset); `${a[-6]}` gave empty (bash: `x`, slot 0). `get()`
    now uses the same one-past-the-top mapping as writes, so reads and writes agree
    (bash-verified against real bash, including the unset-middle case). An out-of-range
    negative *read* expands to empty (bash warns + expands empty; only a bad *write*
    subscript is a hard error — that path is unchanged).
  - `$!` (last background PID) was not inherited by subshell-style children:
    `ShellState.adopt()` didn't copy `last_bg_pid`, so `$!` read empty inside `( … )`,
    `$( … )`, and the env builtin's child (bash inherits it). Added the copy.
  - +8 regression tests (IndexedArray negative-index unit tests; `$!`-in-subshell
    integration tests).
- Sixth and final item of Tier R12.A — **the reappraisal-#10 bug cluster is complete**
  (v0.448–453: history-trim regression, exec redirects, `(( ))`/`[[ ]]`-before-then/do,
  combinator line-continuation, ANSI-C in operands, and these two core bugs).

## 0.452.0 (2026-06-15) - BUGFIX: ANSI-C `$'...'` in parameter-expansion operands + full `${var@E}` — R12.A
- BUGFIX (behavior). Two related ANSI-C-quoting gaps, both fixed by routing through the
  single canonical decoder (`lexer/pure_helpers.handle_ansi_c_escape`):
  - `$'...'` was not decoded inside parameter-expansion operands — default values
    (`${x:-$'\t'}`), patterns (`${x#$'\t'}`, `${x/$'\t'/X}`), and replacements
    (`${x/b/$'\t'}`) all left it literal where bash decodes it. The three operand
    expanders (`operands.py`: `_expand_pattern_operand`, `_expand_replacement_operand`,
    `_expand_operand`) now decode an inline `$'...'` via the shared `scan_inline_ansi_c`
    scanner. (`$'...'` is intentionally NOT decoded by `expand_string_variables`, which
    also serves double-quoted content where it must stay literal — so each operand
    walker decodes it explicitly.)
  - `${var@E}` used a third, incomplete ANSI-C decoder (`operators.py:_ansi_c_expand`)
    missing octal `\NNN`, `\cX`, `\uHHHH`, `\UHHHHHHHH`; it now delegates to the
    canonical decoder, removing the duplication and the gaps.
  - Found by reappraisal #10. +9 conformance tests; ordinary operands (no `$'`) take an
    unchanged fast path.
- Fifth item of Tier R12.A.

## 0.451.0 (2026-06-15) - BUGFIX: combinator parser rejected line-continuation after a pipe/and-or operator — R12.A
- BUGFIX (combinator parser only). The combinator pipeline/and-or parsers did not skip
  a NEWLINE after `|`/`|&`/`&&`/`||`, so a command continued on the next line after the
  operator (`echo a |⏎cat`, `echo a &&⏎echo b`, `false ||⏎echo c`, multi-stage pipes)
  was rejected under `--parser combinator` with "Expected command", while bash and the
  recursive-descent parser accept it. Fix: skip NEWLINE tokens after the pipe operator
  and after the and-or operator before parsing the right-hand command
  (`commands/pipelines.py`). Found by reappraisal #10. +4 three-way (bash/rd/combinator)
  parity regression tests. (The duplicate module-level `parse_pipeline`/`parse_and_or_list`
  helpers in `commands/__init__.py` still carry the bug but are test-only and slated for
  removal in R12.D.)
- Fourth item of Tier R12.A.

## 0.450.0 (2026-06-15) - BUGFIX: `(( ))`/`[[ ]]` condition header before `then`/`do` with no separator — R12.A
- BUGFIX (behavior, both parsers). An arithmetic command or `[[ ]]` test used as a
  condition header followed DIRECTLY by `then`/`do` (no `;`/newline) was rejected:
  `if ((1)) then …`, `while ((x)) do …`, `for ((;;)) do …`, `if [[ a = a ]] then …`
  all errored (`do`/`then` lexed as a plain WORD) where bash accepts them. Root cause:
  `DOUBLE_RPAREN`/`DOUBLE_RBRACKET` were missing from the lexer's
  `RESET_TO_COMMAND_POSITION` (command_position.py), so the keyword normalizer never
  returned to command position after `))`/`]]` and the following `then`/`do` stayed a
  WORD. Fix: add the two compound-closer token types to that set (a fix in the shared
  lexer, so it applies to both the recursive-descent and combinator parsers).
  Separator forms (`if ((1)); then`, `[[ x = x ]] && …`) are unchanged. Found by
  reappraisal #10. +7 conformance tests + updated the command-position drift-lock tests.
- Third item of Tier R12.A.

## 0.449.0 (2026-06-15) - BUGFIX: `exec CMD` ignored its redirections — R12.A
- BUGFIX (behavior). `exec CMD args [redirects]` (the exec builtin WITH a command)
  silently ignored the redirections — `CommandExecutor._handle_exec_builtin`'s
  with-command branch handed off to the builtin's execvpe without applying
  `node.redirects` (only the no-command `exec >file` branch applied them). Probes vs
  bash: `exec printf out >file` wrote to the terminal instead of the file;
  `exec /no/such 2>/dev/null` printed the not-found error to the un-redirected stderr
  (bash is silent). Both exited with bash's code, so exit-code-only checks missed it.
  Fix: apply `node.redirects` permanently (via `apply_permanent_redirections`) before
  the exec — exec replaces the process image, so the redirected fds carry into the new
  program, and if the exec fails they stay in effect (matching bash). Found by
  reappraisal #10. +3 regression tests (`TestExecWithCommandRedirect`).
- Second item of Tier R12.A.

## 0.448.0 (2026-06-15) - BUGFIX: history save dropped new entries after an in-session trim (v0.447 regression) — R12.A
- BUGFIX (data loss; regression in v0.447). `HistoryManager._file_synced_len` (the
  count of history entries already persisted) is an index into `state.history`, but
  `add_to_history` trims the list from the FRONT once it exceeds `max_history_size`
  (default 1000). The marker was not adjusted for the trim, so after the list shifted,
  `save_to_file`'s `history[_file_synced_len:]` slice skipped genuinely-new commands
  (and could re-add already-saved ones). A session that ran more than
  `max_history_size` commands before exiting silently lost the entries between the
  stale index and the tail. Fix: when the front-trim drops N entries, decrement
  `_file_synced_len` by N (clamped at 0) so it keeps pointing at the first unsaved
  entry. Found by reappraisal #10. +1 regression test
  (`test_in_session_trim_does_not_lose_new_entries`).
- First item of Tier R12.A (the reappraisal-#10 bug cluster); memo at
  `docs/reviews/ground_up_reappraisal_10_2026-06-15.md`.

## 0.447.0 (2026-06-15) - BUGFIX: concurrency-safe history persistence (no more multi-terminal clobber)
- BUGFIX (data loss). Command history was lost when multiple psh sessions shared one
  history file — e.g. several terminal windows each auto-starting psh (`psh` as the last
  line of `.zshrc`). `HistoryManager.save_to_file` truncate-rewrote the whole file on
  exit, so the last shell to exit overwrote every other shell's commands
  (last-writer-wins). The file stayed near its loaded baseline and the loss appeared
  intermittent (it depended on exit ordering).
  - Fix: `save_to_file` now appends only THIS session's new entries under an exclusive
    `flock`, re-reading the current on-disk history first (picking up entries other
    shells appended since we loaded), merging, trimming to `max_history_size`, and
    writing the result back. Concurrent shells serialize on the lock instead of
    clobbering one another. `HistoryManager` tracks `_file_synced_len` (how many of
    `state.history`'s entries are already persisted) so only genuinely-new commands are
    added and loaded entries are never duplicated.
  - The history file is now created mode `0o600` (private), where the old
    `open(..., 'w')` left it at the umask default.
  - This also fixes sequential-session accumulation in non-interactive/piped mode (the
    merge keeps prior content instead of overwriting it).
  - +5 regression tests (`tests/unit/interactive/test_history_persistence.py`):
    roundtrip, sequential accumulation, the concurrent no-clobber case, append-only
    (no duplication of loaded entries), and max-size trimming.

## 0.446.0 (2026-06-15) - Tier R11.P4: document the combinator [[ ]]/arithmetic sublanguage boundary (R11 complete)
- DOCS (no behavior change). Final R11 phase: per the architecture review's Phase 4,
  the combinator parser's intentionally-shallow `(( ))` and `[[ ]]` sublanguages are
  now documented as a deliberate educational-scope boundary, and the "abandoned-work"
  comments that read like unfinished TODOs are replaced with honest boundary notes.
  - `SpecialCommandParsers` class docstring now states the boundary up front:
    `(( ))`/`[[ ]]` are recognised structurally but their inner grammars are shallow
    (arithmetic captured as a token string for the runtime evaluator, not an AST;
    `[[ ]]` handles negation + simple unary/binary/single-operand tests but not
    `&&`/`||` compounds, parenthesised grouping, per-operand quote context, or trailing
    redirections), with a pointer to the recursive descent parser as the full
    implementation.
  - Replaced `_build_arithmetic_command`'s "For now, skip redirection parsing to keep
    it simple", `_parse_test_expression`'s "This is simplified - full implementation
    would parse compound expressions", and `expansions._validate_command_substitution`'s
    "For now, accept if tokenization succeeded" with explicit educational-scope notes.
  - No `(( ))`/`[[ ]]` behavior change; full `tests/parser_differential` parity suite
    and whole suite green.
- **Tier R11 COMPLETE.** Elevated the combinator parser toward textbook FP across
  P1 (cleanup) → P2 (discriminated `ParseResult` + cut/farthest-error) → P3 (grammar
  simplification: recursion-only, build-once, modular) → P4 (documented sublanguage
  boundary). Source roadmap: `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`.

## 0.445.0 (2026-06-15) - Tier R11.P3(c): split the combinator commands module into a mixin package
- REFACTOR (no behavior change). The 816-line `psh/parser/combinators/commands.py`
  is now a `commands/` PACKAGE of focused mixin modules, mirroring the existing
  `control_structures/` precedent. `CommandParsers` is composed from four mixins:
  - `commands/redirections.py` — `RedirectionMixin` (`_parse_redirection`,
    `_parse_fd_dup_word`, `_parse_word_as_word`)
  - `commands/simple.py` — `SimpleCommandMixin` (simple-command word/redirect/array
    collection and Word-AST building)
  - `commands/pipelines.py` — `PipelineMixin` (pipeline + and-or list)
  - `commands/statements.py` — `StatementMixin` (statement + the
    `build_statement_list` recursion engine)
  - `commands/__init__.py` keeps the `CommandParsers` class shell (`__init__`,
    `_initialize_parsers`, the `set_command_parser`/`set_function_def` slot setters)
    and the module-level convenience functions; `commands/_constants.py` holds the
    shared `_FD_DUP_RE`/`_WORD_LIKE_TYPES`; `commands/_protocols.py` is a
    TYPE_CHECKING-only `CommandParsersProtocol` so each mixin type-checks in isolation
    (same pattern as `control_structures/_protocols.py`).
  - Public API unchanged: `from ..commands import CommandParsers,
    create_command_parsers, parse_simple_command, parse_pipeline, parse_and_or_list`
    all still resolve. mypy `files` list updated to the new modules. Methods moved
    verbatim; `tests/parser_differential` parity suite + whole suite green.
- Review Ugly #5 (Phase 3) from `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`.
  This completes Tier R11.P3 (grammar simplification): condition headers (P3.1),
  function body (P3a), build-once wiring (P3b), and module split (P3c) all shipped —
  the combinator parser no longer slices tokens, builds its grammar once, and is
  organized into focused modules.

## 0.444.0 (2026-06-15) - Tier R11.P3(b): combinator grammar built once (no post-construction patching)
- REFACTOR (no behavior change). The combinator grammar graph is now built exactly
  ONCE and never rebuilt or patched after construction (review Ugly #4). Net −98 lines.
  - `CommandParsers` builds `pipeline`/`and_or_list`/`statement`/`statement_list` once
    in `_initialize_parsers`, reading two mutable recursion *slots* at parse time:
    `_pipeline_element` (a single pipeline element — widened from a bare simple command
    to control-structure/special/simple during wiring) and `_function_def` (the
    function-definition head, tried before an ordinary statement). Wiring just fills the
    slots (`set_command_parser` / new `set_function_def`).
  - Deleted the ~50-line `set_command_parser` body that REBUILT the pipeline and and-or
    parsers from scratch (a near-duplicate of `_build_pipeline_parser` /
    `_build_and_or_list_parser` — also review Ugly #5), and the now-unnecessary
    reassignment of `commands.statement` / `commands.statement_list` in
    `parser._build_complete_parser`.
  - Removed the vestigial `ForwardParser` machinery that was never wired:
    `statement_forward`/`statement_list_forward` instances (commands.py +
    control_structures), and the dead `set_control_parsers`/`set_special_parsers`
    `hasattr` calls in parser.py (no such methods ever existed). The `ForwardParser`
    primitive itself is kept (a tested, exported combinator building block).
  - Also retired the separate `separated_by`-based `_build_statement_list_parser`; the
    top-level list is now `build_statement_list()` like every other statement list.
  - Full `tests/parser_differential` parity suite + whole suite green; behavior
    identical (compound-in-pipeline, function defs, and-or, negation all verified).
- Review Phase 3 item 3 from `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`.

## 0.443.0 (2026-06-15) - Tier R11.P3(a): function body parses by recursion (last slicer retired)
- REFACTOR (fixes a bash/rd divergence). `StructureParserMixin._parse_function_body`
  no longer collects the tokens between matching `{ }` by brace-counting and re-parses
  the slice. It parses the body on the real token stream via
  `build_statement_list()` (which stops at the `RBRACE` token; nested brace groups
  consume their own `}`), then expects `}`. This was the LAST place the combinator
  parser sliced tokens out of the stream — every compound header and body now parses
  by recursion.
  - Fixes a slicer divergence: a `}` that is merely an argument (`f() { echo }; }`)
    was mis-read as the body's closing brace; it is now consumed as a word, matching
    bash and the recursive-descent parser.
  - Missing-nested-terminator diagnostics (an `if`/loop inside the body without its
    `fi`/`done`) are preserved at end-of-input parity with rd by re-raising the
    committed `ParseError` at the last token (the same handling the old loop used).
  - +2 three-way parity regression tests (`}`-as-argument, nested brace group in a
    function body). Full `tests/parser_differential` parity suite green.
- Review Phase 3 item 2 from `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`.

## 0.442.0 (2026-06-15) - Tier R11.P3.1: combinator condition headers parse by recursion (closes H3)
- REFACTOR (fixes a bash/rd divergence). The `while`/`until`/`if`/`elif` CONDITION
  headers no longer slice tokens to the first `do`/`then` and re-parse the slice.
  They now parse on the real token stream via `build_statement_list(frozenset({'do'}))`
  / `build_statement_list(frozenset({'then'}))` — the same recursion engine the
  compound bodies use — stopping only at a *command-position* `do`/`then`.
  - Closes reappraisal #9 bug H3 (the unfinished tail of C3): a `do`/`then` that is
    merely an argument is now consumed as a word, matching bash and the recursive
    descent parser. Previously `while echo do; false; do echo body; done` and
    `if echo then; then echo hi; fi` failed/diverged under `--parser combinator`;
    all three shells now agree.
  - Deletes three hand-written condition token-slicer loops (and the special
    "`then` must be preceded by a separator" / "unexpected `fi`" message checks,
    which are now emergent from the recursion). The combinator parser no longer
    slices any compound header or body out of the token stream.
  - +5 three-way (bash/rd/combinator) parity regression tests in
    `TestKeywordSpelledArgumentInCondition`; full `tests/parser_differential`
    parity suite green.
- Review Phase 3 item 1 from `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`.

## 0.441.0 (2026-06-15) - Tier R11.P2.2: combinator core — farthest-error selection in or_else
- REFACTOR (improved diagnostics, parity-preserving). `Parser.or_else` no longer
  blindly returns the alternative's failure when both branches fail recoverably.
  It now applies the textbook *farthest-error* rule via a new `_farther_failure`
  helper: keep whichever failure consumed more input (higher `position` — the
  alternative that matched the most before giving up), and on a positional tie
  merge the two `expected` label sets (order-preserving, de-duplicated) so the
  diagnostic can name every token that could have continued the parse. Uses the
  `expected`/`position` channel added in P2.1.
- Behaviour is parity-preserving: accept/reject is unchanged (only the surfaced
  failure among already-failing alternatives changes), and the full
  `tests/parser_differential` diagnostic-position + exception-type parity suite
  stays green — the chosen positions still match the recursive-descent parser
  everywhere they are pinned.
- +3 core unit tests (farthest wins regardless of try-order; expected-label merge
  on tie). This is review Phase 2 item 3 (expected labels + farthest-error) from
  `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`. With P2.1
  (discriminated union + cut semantics) the review's Phase 2 is substantially done;
  the remaining item 5 (converting the ~50 `raise_committed_error` exception sites
  to committed `ParseFailure` returns) is deferred — exception propagation is a
  legitimate global-cut and a wholesale conversion is high-churn with debatable
  clarity gains.

## 0.440.0 (2026-06-15) - Tier R11.P2.1: combinator core — discriminated ParseResult + cut/expected error channel
- REFACTOR (no behavior change). Phase 2 of elevating the combinator parser to
  textbook FP begins with the result type. `ParseResult` is now a success/failure
  discriminated union with two explicit constructors:
  - `ParseSuccess(value, position)` and `ParseFailure(position, error, *, expected,
    committed)` (both `ParseResult` subclasses; the legacy
    `success`/`value`/`position`/`error` attribute surface is preserved so all ~150
    construction sites and ~400 field reads keep working during the migration).
  - The failure shape gains an FP error channel: `committed` (a *cut* — a committed
    failure is NOT retried by `or_else`, so commitment can live inside the combinator
    algebra instead of being raised as an exception) and `expected` (labels for
    same-position diagnostic merging, populated by `token`/`keyword`/`literal`).
  - `or_else`/`many`/`separated_by` now honour the cut: a committed failure
    propagates instead of being swallowed/retried. This is wired but a NO-OP until
    P2.2 starts constructing committed failures (every failure is recoverable today),
    so behavior is identical — verified by the full `tests/parser_differential`
    parity suite (AST + rejection + diagnostic-position + exception-type) and the
    whole suite (7712 passed).
  - The core combinators (`map`/`then`/`sequence`/`between`/`skip`/`token`/…) now
    construct via `ParseSuccess`/`ParseFailure`; failure-position semantics
    (atomic reset-to-entry where the old code reset) are preserved exactly.
  - +8 core unit tests pinning the constructors and the commitment short-circuit.
- This is review Phase 2 step 1 of
  `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`. Next (P2.2):
  convert the `raise_committed_error` sites to committed `ParseFailure`s where
  practical, moving committed syntax errors out of exceptions.

## 0.439.0 (2026-06-15) - Tier R11.P1: combinator parser cleanup (dedup stale parsers, drop dead diagnostics)
- REFACTOR (no behavior change). Phase 1 of elevating the combinator parser toward
  textbook quality — pure deletion of stale/duplicate code, parity suites green.
  Net −415 production lines.
  - Removed the SECOND (dead) array parser from `special_commands.py`:
    `_build_array_initialization`, `_build_array_element_assignment`,
    `_detect_array_pattern`, `_build_array_assignment`, and the
    `_collect_element_value_word` helper (~370 lines). They were built but never
    composed into `special_command`, so they never ran in production. `arrays.py`
    (`ArrayParsers`, used by the live command path in `commands.py`) is now the sole
    array assignment/initialization parser.
  - Removed the orphaned process-substitution parser
    `ExpansionParsers._parse_process_substitution` (+ its `self.process_substitution`
    instance) — it was not wired into `self.expansion`; the live standalone-procsub
    parser is `SpecialCommandParsers._build_process_substitution`, and inline procsub
    goes through the shared WordBuilder path.
  - Deleted the dead function-body diagnostic remapping in `structures.py`: four
    `"expected 'fi'/'done'/'esac'/'then'"` substring rewrites that became unreachable
    after C3 (missing compound terminators inside a function body now RAISE via
    `raise_committed_error`, caught structurally by `is_missing_nested_terminator`,
    rather than returning a soft failure to be re-described by string-matching).
  - Pruned now-unused imports (`ArrayInitialization`/`ArrayElementAssignment`/
    `WordPart`/`Union`/`cast`/`format_token_value` in special_commands.py,
    `ProcessSubstitution` in expansions.py) and the corresponding dead tests
    (`TestArrayOperations` in test_special_commands.py, two procsub tests in
    test_expansions.py).
  - Documented `build_statement_list()` as the single compound-body engine in
    `psh/parser/CLAUDE.md` and corrected the combinator file table (arrays live in
    `arrays.py`, not `special_commands.py`).

## 0.438.0 (2026-06-15) - Tier R10.A: reappraisal #9 bug fixes (string-context `\$` escape, builtin I/O convention)
- BUGFIX (behavior). String-context `\$` now always drops its backslash, matching
  bash and the command-argument Word path. `VariableExpander._process_double_quote_escape`
  previously kept the backslash on `\$` unless it was immediately followed by a
  variable-name character, so double-quoted text in here-strings/documents, redirect
  targets, `[[ ]]` operands, and `${...}` operands diverged from bash:
  - `cat <<< "a\$ b"` → was `a\$ b`, now `a$ b` (bash).
  - `echo "${v:-a\$ b}"` → was `a\$ b`, now `a$ b` (bash).
  - `\$VAR` still shields the expansion (literal `$VAR`); `\\`, `\"`, `` \` `` and
    C-style `\n`/`\t` are unchanged. (`\<newline>` line continuation is handled
    upstream by the lexer and is intentionally not processed here.)
  - The stale "PS1 compatibility" justification was removed: PS1 expansion routes
    through `interactive/prompt.py`, not `expand_string_variables` (zero callers).
  - This is reappraisal #9's bug H1 — the genuine content of the previously deferred
    "D2" escape-processor item (the two processors differed because the string-context
    one was buggy, not "by design"). Pinned by the new
    `tests/conformance/posix/test_escaped_dollar_string_context_conformance.py`.
- CONSISTENCY (no observable change). `history` and `version` now emit through the
  v0.284 forked-child-aware `self.write_line()` helper instead of raw
  `print(file=shell.stdout)` — they were the last two builtins bypassing the
  error-channel convention every other builtin follows (reappraisal #9 bug H2). In
  psh's real forks `shell.stdout` is already bound to fd 1, so no divergence could be
  reproduced; the change removes the inconsistency and the unused `sys` import.
- DOCS. Reconciled the README test counts (the `**Tests**: total` line and the
  `**Test Coverage**:` line now agree) — a reappraisal #9 LOW finding.

## 0.437.0 (2026-06-15) - Tier R9.D6: executor seam fixes (drop [[ ]] backchannel, dedup procsub body)
- REFACTOR (no behavior change). Two executor/IO seams tidied:
  - `[[ ]]` no longer bounces through the shell. `ExecutorVisitor.visit_EnhancedTestStatement`
    now owns the evaluation directly (constructs the in-package
    `TestExpressionEvaluator`, applies redirections via its own `io_manager`).
    The `Shell.execute_enhanced_test_statement` method — which existed only to
    serve the executor — is removed, eliminating the executor→shell→evaluator
    backchannel (the executor already holds everything it needs).
  - Process substitution: the read-side `<(cmd)` child body inlined the same
    tokenize/parse/execute that the write-side already routed through the shared
    `_execute_process_substitution_body` helper. Both sides now call the helper.
- Full suite + ruff + mypy green. Completes Tier R9.D (and the reappraisal-#8
  R9 roadmap: A/B/C/D all shipped).

## 0.436.0 (2026-06-15) - Tier R9.D4: split the two ~900-line expansion files
- REFACTOR (no behavior change). Decomposed the two largest expansion modules
  along their natural seams:
  - `brace_expansion.py` (903 lines) → keeps `BraceExpander` (the textual
    per-word algorithm, now 629 lines); `TokenBraceExpander` (the token-stream
    pass that delegates to it) moves to the new `brace_expansion_tokens.py`.
  - `word_expander.py` (898 lines) → keeps the `WordExpander` engine (762
    lines); its data model — `WordExpansionPolicy` + the named policy instances
    (`COMMAND_ARGUMENT`, `LOOP_ITEM`, `DECLARATION_ASSIGNMENT`,
    `ARRAY_INIT_ELEMENT`, `ASSOC_INIT_ELEMENT`), `ExpandedSegment`, `_WalkState`
    — moves to the new `word_expansion_types.py` (pure data, no shell/AST deps).
- Importers updated to the canonical new locations (no re-export shims): the
  lexer's `TokenBraceExpander` import, and the policy imports in
  `expansion/manager.py`, `io_redirect/file_redirect.py`, `executor/array.py`,
  `executor/control_flow.py`, plus the affected tests.
- Pure code movement: every symbol kept verbatim. Full suite + ruff + mypy green.

## 0.435.0 (2026-06-15) - Tier R9.D1: converge getopt-shaped builtins onto parse_flags
- REFACTOR + BEHAVIOR (bash parity). `command`, `disown`, and `help` now parse
  their boolean options through the shared `Builtin.parse_flags` helper instead
  of hand-rolled loops. Two consequences match bash:
  - Clustered flags work: `command -vp`, `disown -ar`, `help -dm` (previously
    rejected as a single invalid token).
  - Invalid-option diagnostics match bash's format and exit code: e.g.
    `command: -x: invalid option` followed by `command: usage: command [-pVv]
    command [arg ...]`, exit 2 (`disown` previously exited 1 with
    `invalid option: -x`; `help` previously printed `invalid option -- 'x'` and
    a bespoke multi-line usage block).
- Removed the now-dead `HelpBuiltin._show_usage`.
- The other hand-rolled flag parsers are deliberate exceptions, not holdouts:
  `kill` (`-SIGNAL`/`-NUMBER`), `pushd`/`popd`/`dirs` (`+N`/`-N` stack indices),
  `read`/`mapfile`/`print` (many value flags), `getopts`/`shift`/`shopt`/`trap`/
  `set` (own option models) — their `-N`/`-NAME`/value-flag shapes conflict with
  getopt clustering.
- Pinned by new tests; full suite + ruff + mypy green. Zero change to recursive
  descent or any other subsystem.

## 0.434.0 (2026-06-15) - Tier R9.C3 COMPLETE: case bodies by recursion + unified statement-list engine
- REFACTOR (combinator parser). Finishes C3. The `case` item command bodies no
  longer slice tokens until a terminator with a hand-tracked `nesting_depth`
  (plus pattern/`(`-lookahead heuristics); they now parse by recursion via
  `build_statement_list(frozenset({'esac'}), <;; ;& ;;& token types>)`, mirroring
  recursive descent's `parse_command_list_until(*CASE_TERMINATORS, ESAC)`. A
  nested `case` is parsed whole by `self.statement` and consumes its own `esac`,
  so no nesting counter is needed.
- `build_statement_list` gained a `terminator_types` parameter (token-type
  terminators like `;;`) alongside the keyword `terminators`.
- CAPSTONE: the top-level statement list (in `parser.py._build_complete_parser`)
  is now `self.commands.build_statement_list()` — the same engine, with no
  terminator (stops at EOF / `)` / `}`). Brace and subshell groups reuse it
  directly. The duplicated committed-loop closure in parser.py is removed, so
  there is now ONE recursion-based statement-list engine; loops/if/case build
  terminator-specific variants of it. The reviewer's "central irony" is resolved:
  the grammar parses every compound body by recursion, not token-slicing.
- An `esac`-spelled argument in a case body (`a) echo esac;;`) is now a plain
  word (same statement-start-only terminator check as the loop/if fix); pinned
  in `test_combinator_parity_regressions.py`.
- All `tests/parser_differential` parity suites + full suite + ruff + mypy green.
  Zero change to recursive descent.

## 0.433.0 (2026-06-15) - Tier R9.C3 (part 1): loops & if parse bodies by recursion, not slicing
- REFACTOR (combinator parser; the reviewer's "central irony"). The compound-body
  parsers for `while`, `until`, `for`, C-style `for`, `select`, and `if`
  (then/elif/else) no longer slice the body token span out of the stream with a
  hand-tracked `nesting_level` and re-parse it. They now parse bodies by
  *recursion* via a new `CommandParsers.build_statement_list(terminators)` —
  a statement list that stops at (without consuming) its terminator keyword.
  Nested compounds consume their own `done`/`fi`, so the recursion *is* the
  nesting tracker. The `_collect_tokens_until_keyword` slicer is deleted.
- BEHAVIOR (bash divergence fix). An argument that merely spells like a
  terminator keyword inside a loop/if body is now a plain word, matching bash
  and the recursive-descent parser. Previously the by-value slicer mis-detected
  it as the terminator, so `while true; do echo done; break; done` and
  `if true; then echo fi; fi` failed under `--parser combinator`. New parity
  regressions in `test_combinator_parity_regressions.py` pin the fix.
- Once committed past `do`/`then`, a body syntax error now raises at the
  offending token (so `or_else` cannot swallow it and retry as a simple
  command), keeping diagnostics aligned with recursive descent — verified by
  the full `tests/parser_differential` parity suites (AST + error + diagnostic).
- Two isolated unit tests that fed raw (un-normalized) `WORD` tokens and pinned
  the old slicer's flattening artifact ("known limitation: 3 statements") were
  rewritten to parse real source and assert correct nesting (one nested node).
- Zero change to recursive descent (the default parser) or to `case` and
  function/brace/subshell bodies (the latter already parsed by recursion).
  Full suite + ruff + mypy green.

## 0.432.0 (2026-06-15) - Tier R9.D: `[` error messages use the `[` prefix (bash parity)
- BEHAVIOR (bash divergence fix). Errors from the `[` builtin now carry the `[`
  prefix (e.g. `[: 1: unary operator expected`) instead of `test:`, matching
  bash; `test` errors still say `test:`. Previously `[` delegated to a fresh
  `TestBuiltin()` instance, so its errors used that instance's `test` name.
- `BracketBuiltin` now subclasses `TestBuiltin` and evaluates through `self`
  (`self.evaluate_test(...)`), so `self.name == '['` flows to every `self.error`
  prefix. Verified against bash for unary/binary/integer operator errors.
- Added error-prefix tests to `tests/unit/builtins/test_test_builtin.py`.
- Gate: ruff + mypy clean, full suite 8,028 collected / all phases green.

## 0.431.0 (2026-06-15) - Tier R9.C2: combinator core-library hygiene
- ARCHITECTURE (combinator backend; zero behavior change). Cleaned up the
  parser-combinator core (`psh/parser/combinators/core.py`):
  - Removed the vestigial `ParseResult.remaining` field — it was only ever set
    (by `map()` propagating it to itself) and never read for any decision.
  - Unified the backtracking discipline: `Parser.then()` now resets to the
    start position on second-parser failure (atomic), matching `sequence()`;
    previously it leaked the first parser's end position. The only grammar use
    (`many1`) never triggers the branch (its second parser is `many`, which
    cannot fail), so behavior is unchanged — this removes a latent inconsistency.
- Added a unit test pinning the unified `then()` reset-on-failure.
- (Elevate path: the currently-unused combinator primitives — `between`,
  `lazy`, `literal`, etc. — are intentionally retained for the C3 grammar
  rewrite to consume.)
- Gate: ruff + mypy clean, full suite 8,026 collected / all phases green.

## 0.430.0 (2026-06-15) - Tier R9.C1: structured combinator nested-terminator dispatch
- ARCHITECTURE (combinator backend; zero behavior change). Replaced the fragile
  message-substring dispatch in `is_missing_nested_terminator()` with a
  structured `ParseError.missing_terminator` field (the closing keyword
  'fi'/'done'/'esac'), following the existing `at_eof`/`unclosed_expansion`
  structured-signal pattern. First step of elevating the combinator parser to
  first-class.
- `raise_committed_error()` gains a `terminator=` keyword that tags the raised
  `ParseError`; the six fi/done/esac raise sites (if/case in conditionals.py,
  the four loop forms in loops.py) pass it. `is_missing_nested_terminator()` now
  reads the tag instead of lower-casing and substring-matching the message, so a
  message reword can no longer silently break nested-error remapping.
- Updated `test_diagnostics.py` to pin the structured contract (tagged → True,
  untagged → False) rather than message text. Nested-terminator position parity
  with recursive descent is unchanged (verified end-to-end).
- Gate: ruff + mypy clean, full suite 8,025 collected / all phases green.

## 0.429.0 (2026-06-15) - Tier R9.B5: de-duplicate the array-init element loop
- REFACTOR (zero behavior change). The recursive-descent parser had two copies
  of the `name=(...)` element-collection loop — one for statement position
  (`arrays.py`) and one for argument position (`commands.py`, e.g.
  `declare a=(...)`). Extracted the shared loop into
  `CommandParser.parse_array_init_elements()` (plus `_serialize_array_element()`
  for the token-faithful flat-string fragments); both call sites now use it.
- Both paths already built an identical `ArrayInitialization`
  (`elements=[w.display_text() ...]`, `words=<element words>`); the only
  remaining difference (the argument path also rebuilds a token-faithful flat
  string for the argument's literal Word text) is preserved.
- Verified by bash-parity probes across statement/argument position, quoted
  elements, empty arrays, `+=` append, and `$`-expansions. Completes Tier R9.B.
- Gate: ruff + mypy clean, full suite 8,029 collected / all phases green.

## 0.428.0 (2026-06-15) - Tier R9.B3: complete the visitor Word-layer migration
- ARCHITECTURE. Finished routing the analysis visitors through the structured
  Word model (`word_analysis.py`) instead of regexing rendered argument
  strings — the subsystem's stated thesis, previously ~80% true.
- `metrics_visitor.py`: the `SimpleCommand`, `ForLoop`, and `SelectLoop` call
  sites now use a new `_analyze_word_features(word)` that reads the Word parts:
  each `CommandSubstitution` part counts once (so backtick subs no longer
  double-count and `$((...))` is correctly NOT counted as a command sub), and
  variable names come from `iter_variable_references`. `_analyze_string_features`
  is retained only for `CaseConditional.expr` (a plain string in the AST).
  `_count_commands_in_node` now reuses `traversal.iter_child_nodes` instead of a
  hand-rolled `__dict__` walk.
- `linter_visitor.py`: `_check_test_command`/`_check_file_command` take Words and
  detect unquoted variables via `has_unquoted_variable_expansion(word)` rather
  than `arg.startswith('$')` — more accurate (an embedded `pre$f` is now caught;
  quoted `"$f"` correctly is not). Behavior for recognized test operators is
  unchanged.
- These counts/warnings are not pinned by any prior test; the new behavior is
  strictly more accurate. Added `tests/unit/visitor/test_word_layer_migration.py`
  (8 tests) pinning it.
- Gate: ruff + mypy clean, full suite 8,029 collected / all phases green.

## 0.427.0 (2026-06-15) - Tier R9.B4: check_untyped_defs for expansion + executor
- TYPES (zero behavior change). Enabled `check_untyped_defs = true` for
  `psh.expansion.*` and `psh.executor.*` (joining `psh.core.*`), so mypy now
  type-checks the BODIES of un-annotated functions in all three packages — the
  reappraisal's "highest-leverage type win". Fixed the 13 surfaced errors:
  - `psh/expansion/_protocols.py`: added the four slice helpers
    (`_positional_slice_elements`, `_parse_slice_operand`, `_slice_elements`,
    `_slice_scalar_subscript`, defined on `OperatorOpsMixin`) to
    `VariableExpanderProtocol` so `FieldExpansionMixin` type-checks.
  - `psh/expansion/manager.py`: annotated the lazy
    `_evaluator: Optional['ExpansionEvaluator']`.
  - `psh/expansion/brace_expansion.py`: made `_emit_word`'s `segments` a
    uniform `List[Tuple[str, Any, Any]]` (the `'tok'` case is padded with
    `None`) so the heterogeneous discriminated tuples type-check — no behavior
    change (the consumer already branches on `seg[0]`).
  - `psh/executor/pipeline.py`: typed the `visitor` parameters as the concrete
    `ExecutorVisitor` (they always are) so `visitor.context` resolves.
  - `psh/shell.py`: initialized `_errexit_suppress_seed: int = 0` (the
    one-shot set -e suppression seed `SubshellExecutor` sets and
    `_execute_with_visitor` reads).
- The two errors that looked like possible latent bugs were verified benign: the
  brace-expansion tuple is a typing-model artifact (correctly discriminated at
  runtime), and `_errexit_suppress_seed` is a working dynamic seed (read at
  `shell.py` via `getattr`), not a dead write.
- Gate: ruff + mypy clean (227 files), full suite 8,021 collected / all phases
  green.

## 0.426.0 (2026-06-15) - Tier R9.B2: extract HistoryState from ShellState
- ARCHITECTURE (zero behavior change). Second increment of the ShellState
  decomposition. Grouped the command-history list and its persistence settings
  (`history`, `history_file`, `max_history_size`) into a new cohesive
  `psh/core/history_state.py::HistoryState`.
- `ShellState` now owns `self.history_state = HistoryState()` and exposes the
  three names as delegating properties (read + write). The `history` getter
  returns the list by reference, so HistoryManager's in-place
  `append()`/`clear()` and the tests' `state.history = [...]` reassignments
  both keep working — every call site is untouched.
- Added `tests/unit/core/test_history_state.py` (4 tests) pinning defaults,
  in-place mutation by reference, list reassignment, and file/size delegation.
- Gate: ruff + mypy clean (`psh.core.*` `check_untyped_defs=true`), full suite
  8,021 collected / all phases green.

## 0.425.0 (2026-06-15) - Tier R9.B1: extract TerminalState from ShellState
- ARCHITECTURE (zero behavior change). First real increment of the ShellState
  god-object decomposition (the headline gap from the reappraisal). Extracted
  the three controlling-terminal attributes (`is_terminal`, `terminal_fd`,
  `supports_job_control`) and the detection logic that populates them into a
  new cohesive `psh/core/terminal_state.py::TerminalState` — the same "typed
  sub-object" move proven by `StreamBindings`.
- `ShellState` now owns a `self.terminal = TerminalState()` and exposes the
  three attributes as delegating properties (read + write), so all ~23 call
  sites across the codebase are untouched. The old
  `ShellState._detect_terminal_capabilities()` moved to `TerminalState.detect()`
  (taking an explicit `debug` flag instead of reaching into `self.options`).
- Added `tests/unit/core/test_terminal_state.py` (5 tests) pinning the type's
  defaults, the three `detect()` paths (non-TTY, TTY+job-control, TTY-without),
  and the ShellState property delegation.
- Gate: ruff + mypy clean (`psh.core.*` is `check_untyped_defs=true`, so the new
  module is body-checked), full suite 8,017 collected / all phases green.

## 0.424.0 (2026-06-15) - Tier R9.A: dead-code & vestige sweep
- CLEANUP (zero behavior change). First tier of the 2026-06-15 ground-up
  reappraisal (`docs/reviews/ground_up_reappraisal_2026-06-15.md`): removed
  dead/vestigial code flagged across subsystems, each verified truly
  unreferenced before removal.
- Lexer: removed unused `Token.from_basic_token` and `Token.normalized_value`
  (`psh/lexer/token_types.py`).
- Executor: removed uncalled `ExecutionContext.in_loop()`/`in_function()`
  (`context.py`) and the unused `visitor` parameter of
  `SubshellExecutor.execute_subshell()` (subshells fork a fresh Shell and never
  use it; updated the lone call site in `core.py`).
- Expansion: removed dead `AliasManager.save_to_file()`/`load_from_file()`
  (`aliases.py`) and the always-`None` `quote_type` parameter of
  `WordExpander._split_with_ifs()` (updated its caller and the subsystem
  CLAUDE.md doc).
- Core: removed dead `ShellState.history_index`/`current_line` fields
  (`state.py`).
- Interactive: removed the base-class `multi_line_handler = None` field
  (only `REPLLoop` uses it, and sets its own) and the uncalled
  `LineEditor.save_undo_state()` wrapper.
- Parser (recursive descent): fixed a stale comment referencing the
  `array_init.py` module deleted in v0.349.
- Gate: ruff + mypy clean (225 files), full suite 8,012 collected / all phases
  green.

## 0.423.0 (2026-06-15) - Consolidate combinator nested-terminator helper
- PARSER (combinator backend, non-default; pure refactor, zero behavior
  change). Folded the three duplicated `_is_missing_nested_terminator()`
  copies (conditionals, loops, structures) into a single public
  `is_missing_nested_terminator()` in
  `psh/parser/combinators/diagnostics.py`, the shared home for the sibling
  `raise_committed_error()`/`error_context_for_token()` helpers. All
  compound-body parse boundaries now import the one definition.
- Added focused unit tests in
  `tests/unit/parser/combinators/test_diagnostics.py` pinning the helper's
  positive (`fi`/`done`/`esac` "to close") and negative (`then`, `do`,
  pipe, etc.) classifications, including case-insensitivity.
- Gate: ruff + mypy clean (225 files), full suite 8,012 collected / all
  phases green.

## 0.422.0 (2026-06-15) - Align combinator nested-terminator diagnostics
- PARSER (combinator backend, non-default; diagnostics only — accept/reject
  behavior unchanged). For crossed nested terminators (e.g.
  `if true; then while true; do echo x; fi`, `while true; do if true; then
  echo x; done`), the combinator parser now reports the same offending token
  as recursive descent: the missing nested-terminator error from a compound
  body is remapped to the outer terminator position at the if/else, loop,
  select, and case-item body parse boundaries.
- Missing nested terminators inside function bodies are remapped to EOF,
  matching recursive descent for function-body parsing (`f() { if true; then
  echo x; }`).
- Added diagnostic- and rejection-parity cases for crossed if/loop terminators
  and nested if/loop failures inside function bodies; narrowed the documented
  remaining drift (in
  `docs/reviews/combinator_diagnostic_characterization_2026-06-14.md`) to
  malformed case-item bodies and missing-`esac`-inside-body cases.
- Zero behavior change for the default recursive-descent parser; verified no
  accept regressions across a battery of valid nested constructs in if/loop/
  function bodies. Gate: ruff + mypy clean (225 files), full suite 8,004
  collected / all phases green.

## 0.421.0 (2026-06-15) - Expand combinator diagnostic corpus; reject empty compound bodies
- PARSER (combinator backend, non-default). The combinator parser now rejects
  empty compound *bodies* that are syntax errors in bash — empty `then` bodies
  (`if true; then; fi`), empty loop `do`/`done` bodies (`while`, `until`,
  `for`, C-style `for`, `select`), and the stray `;` after `case ... in`
  (`case x in ; esac`) — pointing at the same offending token as recursive
  descent. (These empty-body forms are bash errors in both their `;` and
  newline variants; recursive descent is more lenient on the newline form, so
  the combinator is now the closer match to bash here.)
- Accept/reject boundary preserved for `case`: an *empty case* with no patterns
  (`case x in esac`, including blank/comment-only lines before `esac`) is valid
  bash and remains accepted — only the stray `;` after `in` is rejected. Added
  an `ACCEPTANCE_CORPUS` parity gate in
  `tests/parser_differential/test_combinator_error_parity.py` pinning valid
  empty/zero-iteration constructs for both parsers.
- Broadened the recursive-descent vs combinator rejection and diagnostic-parity
  corpora with nested missing-terminator, separator-edge, and
  compound-trailing-redirection cases; refreshed
  `docs/reviews/combinator_diagnostic_characterization_2026-06-14.md`.
- Zero behavior change for the default recursive-descent parser. Gate: ruff +
  mypy clean (225 files), full suite 7,996 collected / all phases green.

## 0.420.0 (2026-06-15) - Normalize combinator diagnostic positions to source coordinates
- PARSER (combinator backend, non-default). Combinator `ParseError` sites now
  report source-character position, line, and column (from token metadata)
  instead of token-stream indexes, matching the recursive-descent parser.
- Added `error_context_for_token()` to `psh/parser/combinators/diagnostics.py`
  to build `ErrorContext` from a token's source coordinates; routed committed
  diagnostics, top-level combinator parser errors, and the remaining custom
  combinator `ParseError` sites (simple-command redirect, subshell/brace empty
  body) through it.
- Strengthened the recursive-descent vs combinator diagnostic-parity gate to
  assert position, line, and column in addition to exception type, EOF signal,
  and offending-token identity. Message text remains the only intentionally
  unaligned dimension (tracked as follow-up).
- Zero behavior change for the default recursive-descent parser. Gate: ruff +
  mypy clean (225 files), full suite 7,952 collected / all phases green.

## 0.419.0 (2026-06-15) - Centralize combinator committed-error diagnostics
- PARSER (combinator backend, non-default; zero behavior change). Consolidated
  the six duplicated `_raise_committed_error()` helpers (arrays, commands,
  conditionals, loops, structures, enhanced tests) into one shared primitive,
  `psh/parser/combinators/diagnostics.py::raise_committed_error()`, so future
  diagnostic work has a single behavior and type surface to update.
- The shared helper is typed `-> NoReturn` (an improvement over the old local
  `-> None` helpers) and takes `Sequence[Token]`; same EOF clamp
  (`min(pos, len-1)`) and `ErrorContext` construction as before.
- Specialized direct `ParseError`/`ErrorContext` call sites that emit custom
  unexpected-token diagnostics are intentionally left intact (e.g. two in
  `control_structures/structures.py`).
- Added `tests/unit/parser/combinators/test_diagnostics.py` covering
  committed-error token selection and EOF clamping. Gate: ruff + mypy clean
  (225 files), full suite 7,952 collected / all phases green.

## 0.418.0 (2026-06-15) - Combinator command-operator diagnostic alignment
- PARSER (combinator backend, non-default). Missing right-hand commands after
  committed binary command operators (`|`, `|&`, `&&`, `||`) now raise a hard
  `ParseError` carrying the EOF/offending-token diagnostic — matching what
  recursive descent already reports — instead of soft-stopping and letting the
  statement-list level blame the operator token.
- Replaced the soft `many(sequence(operator, command))` operator-loops in
  `psh/parser/combinators/commands.py` with explicit committed loops. Success
  paths are unchanged: each loop's RHS parser is the same parser as its LHS, as
  the old `many(sequence(...))` used.
- Expanded the recursive-descent vs combinator diagnostic-parity corpus with
  missing-RHS (`echo |`, `echo |&`, `echo &&`, `echo ||`) and missing-LHS
  (`|| echo`) cases; refreshed
  `docs/reviews/combinator_diagnostic_characterization_2026-06-14.md` to record
  that no diagnostic-summary drift remains in the starter rejection corpus.
- Zero behavior change for the default recursive-descent parser. Gate: ruff +
  mypy clean (225 files), full suite 7,950 collected / all phases green.

## 0.417.0 (2026-06-15) - Tier R8.6b: alias expansion moved to a token-stream transform
- ARCHITECTURE (review Ugly 1 / A2 — the fenced big-bang). Alias expansion no
  longer happens at runtime by re-lexing joined argv; it is now a TOKEN-STREAM
  transform at the lex→parse boundary, structurally eliminating the
  injection class (args are never reconstructed as source).
- `shell.alias_manager.expand_aliases(tokens)` runs immediately after
  tokenization at the two seams every path converges on:
  `scripting/source_processor.py` (execution parse) and
  `scripting/command_accumulator.py` (trial/completeness parse). Both parser
  backends are covered (transform is parser-agnostic; `-c`/script/stdin/REPL/
  `eval`/`source` all route through `SourceProcessor`).
- `AliasExecutionStrategy` fully removed from `strategies.py` and the
  `command.py` strategy list (no shim needed). The dead `AliasManager.
  expand_aliases` token transform is now live, with `_is_command_position`
  hardened to be keyword-aware so aliases expand in command position inside
  if/while/until/for/case/subshell/brace-group/`&&`/`||`/`|`/`;` and NOT as
  plain args, loop items, case patterns, or the loop var / case selector
  (verified vs bash).
- Decided behaviors (per maintainer): same-line `alias x=…; x` still expands
  (psh divergence kept, via a same-stream definition overlay); `shopt -s/-u
  expand_aliases` now ACCEPTED (recognized no-op gate; psh keeps always-expand);
  quoted command words (`'ll'`) are NOT expanded (bash parity); trailing-space
  chaining now works (bash parity). The deliberate always-expand-non-interactively
  divergence is preserved (pinned `assert_psh_extension` tests stay green).
- Tests: +`test_alias_token_transform_conformance.py` (29),
  +`test_alias_token_transform.py` (17), +9 golden; 3 stale tests that pinned the
  old runtime-strategy behavior updated (each verified vs bash first); the R8.6a
  injection conformance test still passes. Full gate green: ruff + mypy clean
  (225 files), `run_tests.py --parallel` 7613 passed, `--compare-bash` 470.

## 0.416.0 (2026-06-15) - Tier R8.6a: fix the alias-argument injection bug
- BUG FIX (bash-verified; SECURITY-relevant; interim fix ahead of the full
  alias-at-parse-time move). `AliasExecutionStrategy` expanded an alias at
  runtime by joining the already-expanded, quote-removed argv into a source
  string and re-lexing it — so any alias argument containing a shell
  metacharacter was reinterpreted as SYNTAX. `alias e=echo; e 'a; echo PWNED'`
  ran `echo PWNED` as a second command; `e '$(echo X)'`/`e '$FOO'`/`e '*.md'`
  re-expanded the data; `e '>zz'`/`e '|cat'`/`e 'a & b'` turned data into a
  redirect/pipe/background; `e 'a"b'` crashed with a syntax error; quoted
  spaces/tabs split into multiple args.
- Fix: `shlex.quote` each already-expanded argument before the join, so the
  re-lexer treats each as a single literal word. The alias VALUE stays raw (it
  is meant to be parsed as shell). All 10 injection cases now match bash exactly;
  value-is-shell aliases (`alias x='echo a; echo b'`, pipe/redirect in the value),
  recursion guard, bypasses, chains, and the deliberate always-expand behavior
  are unchanged.
- Known still-divergent (deferred to the full token-stream move): trailing-space
  chaining, same-line `alias x=…; x`, quoted-command-word bypass, `shopt -s
  expand_aliases`. The probe battery confirmed these are unchanged (not
  regressed).
- Tests: +`test_alias_argument_injection_conformance.py` (13, bash-pinned). Full
  gate green: ruff + mypy clean (225 files), `run_tests.py --parallel` 7558
  passed, `--compare-bash` 461 passed.

## 0.415.0 (2026-06-15) - Combinator parser: committed compound diagnostics (PR #150)
- REFACTOR (combinator backend only; recursive-descent default parser untouched).
  Follow-on to PR #149. The combinator parser recognized compound openers
  (if/case, while/until/for/select, function forms, brace/subshell groups,
  arrays, `[[ ]]`) but then fell back to GENERIC opening-token failures on
  malformed input. It now raises COMMITTED parse errors after the opener, so its
  diagnostics match recursive descent: EOF/offending-token errors for
  unterminated compounds, malformed case headers, missing function names,
  malformed `[[ … ]]`, and unterminated array initializers.
- `ParserCombinatorShellParser.can_parse()` stays a boolean probe by treating a
  committed `ParseError` as a parse failure (added to its caught exceptions).
- Expanded the RD-vs-combinator diagnostic parity corpus from 9 to 23 stable
  cases; refreshed `docs/reviews/combinator_diagnostic_characterization_2026-06-14.md`
  (remaining starter-corpus drift is now just missing-RHS-command after `|`/`&&`).
- Maintainer-authored (PR #150). Orchestrator added the one mypy narrowing the
  new code needed: the committed-error helper for `[[ ]]` is now typed
  `-> NoReturn` so `EnhancedTestStatement`'s expression narrows to non-None.
- Full gate green: ruff + mypy clean (225 files), `run_tests.py --parallel` 7545
  passed, `--compare-bash` 461 passed.

## 0.414.0 (2026-06-14) - Combinator parser: parity hardening (PR #149) + differential gates
- REFACTOR + TEST INFRA (combinator backend only; recursive-descent default
  parser untouched). Addresses the R8 review's Ugly 9 / A7 (combinator contract)
  by adding recursive-descent-vs-combinator differential gates and fixing the
  first AST/error/diagnostic parity gaps they exposed:
  - New focused combinator array parser `combinators/arrays.py`; bare array
    assignments route through `SimpleCommand.array_assignments` and
    `name=(...)` initializers through the shared `ArrayInitialization` contract
    (parity with the recursive-descent unified array-init), replacing the old
    synthetic-token hack.
  - Redirect target `Word` metadata preserved (`target_word=`, parity with the
    R7.9 ambiguous-redirect work); here-string redirect shape aligned with RD;
    `[[ ]]` operands built from source tokens (parity with the T3.1 per-part
    Word model).
  - Committed parser failures for empty groups, missing redirect operands, and
    statement lists (a committed loop replaces the failure-swallowing `many()`),
    so diagnostics aren't lost into generic top-level errors.
  - New differential suites: `tests/parser_differential/test_combinator_ast_parity.py`,
    `_error_parity.py`, `_diagnostic_parity.py` (+97 tests); remaining diagnostic
    drift documented in `docs/reviews/combinator_diagnostic_characterization_2026-06-14.md`.
- Maintainer-authored (PR #149). Orchestrator added the 10 missing mypy
  narrowings the PR's new combinator code needed (combinators are in mypy scope:
  `ParseResult.value` Optional-narrowing via asserts after success-checks, a
  re-typed init failure result, `setattr`/`getattr` for the dynamic
  `Token.array_init`) before shipping.
- Full gate green: ruff + mypy clean (225 files), `run_tests.py --parallel` 7531
  passed, `--compare-bash` 461 passed.

## 0.413.0 (2026-06-14) - Tier R8.7: check_untyped_defs for psh.core.* (type depth)
- TYPE-CHECKING DEPTH (zero behavior change; remaining review Ugly 10). mypy
  covers 100% of files but `check_untyped_defs` was off globally, so un-annotated
  function BODIES were unchecked. Enabled it for the foundational package via a
  `[[tool.mypy.overrides]]` block (`module = "psh.core.*"`,
  `check_untyped_defs = true`); the global default stays `false`.
- `psh/core/` was already body-clean (14 previously-unchecked bodies, now all
  checked — a strong signal of the package's invariants). The deeper checking
  caught ONE genuine latent type inconsistency, in a caller: `set -o` listing in
  `builtins/environment.py` assigned `dict_keys` in one branch and `list` in the
  other; wrapped the first in `list(...)` (both are only iterated/sorted, so
  runtime is identical).
- Full gate green: ruff + mypy clean (225 files), `run_tests.py --parallel` 7434
  passed, `--compare-bash` 461 passed.

## 0.412.0 (2026-06-14) - Tier R8.5 (1st increment): StreamBindings on ShellState
- REFACTOR (zero behavior change; review Ugly 6 / A5 — first increment, streams
  only). Replaced the ad-hoc dynamic `_custom_stdin`/`_custom_stdout`/
  `_custom_stderr` attributes on `ShellState` with one explicit typed
  `StreamBindings` object (`psh/core/stream_bindings.py`) owning the three stream
  overrides, with an opaque `snapshot()`/`restore(token)` API. `ShellState`'s
  `stdin`/`stdout`/`stderr` properties delegate to it; the public
  `shell.stdout`/`state.stdout` facade is byte-for-byte unchanged (no caller
  changed except the one executor seam that explicitly saves/restores override
  state — `command.py` `_execute_builtin_with_redirections` now uses
  `streams.snapshot()`/`restore()` instead of `getattr`/`setattr`/`delattr`
  juggling).
- Getter semantics preserved exactly: an override if set, else live `sys.std*`
  (so pytest's post-construction `sys.*` replacement is still seen). The
  io_redirect `_BuiltinStreamSnapshot`/`_ClosedStream` swaps (which act on
  `sys.std*` directly) are unaffected.
- An 11-scenario characterization harness (builtin redirect+restore, `exec >file`
  builtin/external interleave, `2>&1`, `1>&-` closed-fd, brace-group closed-fd,
  subshell/command-sub inheritance, `env` child streams, nested `eval`+`3>&1`)
  is byte-identical. Rest of `ShellState` (options/history/exec flags/terminal)
  untouched — later increments.
- Full gate green: ruff + mypy clean (225 files), `run_tests.py --parallel` 7434
  passed, `--compare-bash` 461 passed.

## 0.411.0 (2026-06-14) - Tier R8.4: visitor analysis over the Word AST
- REFACTOR + tooling-fidelity (review Ugly 8 / A6). The analysis visitors
  (enhanced-validator/linter/security) did variable-reference and word
  classification by regexing rendered `node.args` strings, even though
  `Word.parts` is authoritative. New `psh/visitor/word_analysis.py` provides
  structured helpers — `iter_variable_references(word)` (→ `VariableReference`
  with name/quoted/braced/array-subscript/default/part), `referenced_variable_
  names`, and classifiers (`has_command_substitution`/`has_arithmetic_expansion`/
  `is_arithmetic_only`/`has_unquoted_variable_expansion`/…). The three visitors
  now inspect the Word AST; regex helpers (`_extract_variable_name`,
  `var_patterns`, `_check_variable_usage`, the dead string `has_unquoted_expansion`)
  are deleted. A documented string fallback remains only for operator words
  (`${x:-$y}`) and `Redirect` target/heredoc strings.
- Diagnostic-output changes (all justified, ZERO regressions): removed false
  positives — `echo '$FOO'` (single-quoted, literal), `for f in $(ls)` /
  `` `ls` `` ("undefined var" on a command sub), bogus "unquoted $@" on
  `echo "$@"`. New genuinely-correct findings — `` `date` `` now flagged for
  word-splitting (parity with `$(date)`); `${FOO:-${BAR}}` reports `BAR`
  undefined.
- Tests: +`test_word_analysis.py` (34) +`TestWordAnalysisStructuralFindings`
  (12). Full gate green: ruff + mypy clean (224 files), `run_tests.py --parallel`
  7434 passed, `--compare-bash` 461 (no runtime regression).

## 0.410.0 (2026-06-14) - Tier R8.3: typed command-invocation data flow
- REFACTOR (zero behavior change; review Ugly 2/3 / A1). Replaced the
  `(exit_code, is_special)` tuple side-channel in simple-command execution with
  typed data in `psh/executor/command.py`:
  - `ExecutionResult(status, prefix_assignments_persist)` — `_execute_with_strategy`
    now returns this; `_run_command` reads the NAMED field instead of unpacking a
    positional boolean to decide prefix-assignment persistence.
  - `CommandResolution(strategy, prefix_assignments_persist)` — `_execute_with_strategy`
    is now a thin two-phase coordinator: `_resolve_command` (walks the
    priority-ordered strategies + `\cmd` bypass, computes the persistence policy
    once — previously an inline `isinstance(SpecialBuiltinExecutionStrategy)`)
    then `_invoke_resolution`. `strategies.py` untouched; the split sits above it.
- A 39-case frozen characterization harness (special-vs-normal prefix
  persistence for `:`/`.`/`eval`/`set`/`unset`/`export`/`readonly` vs normal
  builtins/functions/externals; normal/127 execution; pure/array assignments;
  `exec`/`set -e`/xtrace/`$_`/background) is byte-identical before/after.
- Deferred R8.3b: the deeper `_execute_command` phase pipeline + `SimpleCommandPlan`
  (extracting a plan risks reordering POSIX-sensitive steps). Noted (pre-existing,
  out of scope): psh persists `FOO=bar export X=1` where bash `-c` does not.
- Full gate green: ruff + mypy clean (223 files), `run_tests.py --parallel` 7387
  passed, `--compare-bash` 461 passed.

## 0.409.0 (2026-06-14) - Tier R8.2: redirect-primitive boundary (public shared surface)
- REFACTOR (zero behavior change; review Ugly 7 / A4). The builtin stream-redirect
  backend (`IOManager`) reached into `FileRedirector` PRIVATE methods that are
  actually shared redirect primitives. Promoted the 10 genuinely-shared ones to
  a documented public surface (dropping the leading underscore):
  `redirect_input_from_file`, `redirect_readwrite`, `redirect_heredoc`,
  `redirect_herestring`, `check_noclobber`, `noclobber_blocks`, `dup_fd_valid`,
  `expand_redirect_target`, `resolve_dynamic_dup` (was `_resolved`),
  `procsub_handler`. Methods used only inside `file_redirect.py` stay private; the
  `RedirectPlan`/`RedirectPlanner`/`apply_fd_plan` layer is untouched.
- Added a class docstring documenting the public-primitive vs private contract;
  updated `io_redirect/CLAUDE.md` (helper table split public/private) and the
  arch docs that named the old private methods.
- A characterization harness over builtin + external redirect paths (read-from-
  file, heredoc, here-string, `<>`, noclobber block/clobber/new, `>&-`, fd dup,
  `&>`, `2>&1`, dynamic dup, ambiguous redirect) is byte-identical before/after.
- Full gate green: ruff + mypy clean (223 files), `run_tests.py --parallel` 7387
  passed, `--compare-bash` 461 passed.

## 0.408.0 (2026-06-14) - Tier R8.1: control-flow context helpers (+2 latent bug fixes)
- REFACTOR (zero behavior change for the extracted scaffolding) + 2 latent bug
  fixes toward bash. `ControlFlowExecutor` repeated the same boilerplate across
  while/until/for/case/if/select/C-style. Extracted four helpers:
  `_compound_redirections(node)` (apply node redirects to the whole body,
  restore), `_pipeline_context_disabled(context)` (save/reset/restore
  `in_pipeline`), `_loop_depth(context)` (depth inc/dec), and
  `_reraise_loop_control(exc, context)` (shared `break N`/`continue N`
  level-decrement). Each construct now reads as its control logic, not a
  try/finally maze.
- A 41-case characterization harness (whole-body redirects, nested break/
  continue with levels, `set -e` failing-condition vs body, compound-as-pipeline
  member, exit codes) is byte-identical before/after.
- LATENT BUGS FIXED (the deliberate uniformity from the R8 review): C-style
  `for ((;;))` AND `select` omitted the `in_pipeline` reset, so a body with an
  EXTERNAL command exec-replaced the forked child and the loop ran ONCE when used
  as a pipeline member. `for ((i=0;i<3;i++)); do /bin/echo q$i; done | cat` was
  `q0` only, now `q0 q1 q2` (matches bash); same for `select`.
- Tests: +`test_compound_in_pipeline_conformance.py` (5). Full gate green: ruff
  + mypy clean (223 files), `run_tests.py --parallel` 7387 passed,
  `--compare-bash` 461 passed.

## 0.407.0 (2026-06-14) - Docs: Tier R8 architecture roadmap
- DOCS ONLY. Added the maintainer's `docs/reviews/fresh_architecture_review_
  2026-06-14.md` (a fresh structural review, inspected at v0.400) and
  `docs/reviews/tier_r8_architecture_roadmap_2026-06-14.md`, which reconciles it
  with the post-R7 tree and defines Tier R8 — targeted architectural seam work
  (not bug-fixing): R8.1 control-flow context helpers, R8.2 redirect-primitive
  boundary, R8.3 typed command-invocation data flow, R8.4 visitor analysis over
  the Word AST, R8.5 gradual ShellState decomposition, R8.6 resolver/invoker
  split + alias-at-parse-time (fenced big-bang), R8.7 `check_untyped_defs`
  deepening.
- Notes what the review already overtook post-v0.406: mypy file coverage is 100%
  (Ugly 10/A8 done bar `check_untyped_defs`); validator false positives fixed in
  R7.9 (Ugly 8 partial); combinator backend typed + declared educational.

## 0.406.0 (2026-06-14) - Tier R7: mypy now covers 100% of psh source files
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 lever — completed).
  Added the final 10 modules: `psh/__init__.py`, `psh/__main__.py`,
  `psh/interactive/__init__.py`, and the previously-deferred combinator
  command/control-structure mixins (`combinators/commands.py`, `parser.py`,
  `control_structures/{conditionals,loops,structures}.py` + `__init__`s).
  **mypy now type-checks ALL 222 `psh/` source files** (223 in scope incl. the
  new Protocol helper).
- The combinator mixins were unlocked with a `ControlStructureProtocol`
  (`combinators/control_structures/_protocols.py`) declaring the shared
  `commands`/`tokens`/`_parse_trailing_redirects`/`_collect_tokens_until_keyword`
  surface, mixed in ONLY under `if TYPE_CHECKING:` (the `_Base = Protocol if
  TYPE_CHECKING else object` idiom — zero runtime change), mirroring the
  expansion-mixin approach; cleared ~50 `attr-defined` errors. The wiring point
  bridges with a documented `cast` (runtime None-handling unchanged).
- Remaining type-checking depth (not file coverage): `check_untyped_defs` is
  still off globally, so untyped function BODIES aren't checked — a possible
  future per-package deepening.
- Reappraisal #7 mypy campaign summary: **scope grew 85 → 223 files** across
  v0.391–v0.406 (lexer, parser, expansion incl. mixins, io_redirect, executor,
  builtins, interactive, scripting, visitor, utils, core — everything).
- Full gate green: mypy clean (223 files), ruff clean, `run_tests.py --parallel`
  7382 passed.

## 0.405.0 (2026-06-14) - Tier R7: grow mypy scope into all of psh/builtins (177 → 212 files)
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 lever). Added the
  ENTIRE `psh/builtins/` package (all 35 modules) to the mypy `files` list; mypy
  now covers **212 source files** (~95% of the tree). Nothing deferred.
- Real bug caught by the wider scope: `read_builtin.py` used `Dict[str, any]`
  (the builtin `any`, not `typing.Any` — which wasn't even imported) on three
  method signatures; a meaningless annotation any type checker rejects. Fixed.
- Behavior-preserving type work: Optional-narrowing on registry/array `.get()`
  results (keys come from `indices()`/`keys()`, always present), renamed
  loop/branch vars whose inferred type changed mid-function, `setattr`/`getattr`
  for the dynamic `err.rc` attribute, a few `TYPE_CHECKING` imports, and a pure
  class-level `directory_stack: Any` annotation on `ShellState` (no runtime
  assignment — preserves the lazy hasattr-guarded creation).
- Full gate green: mypy clean (212 files), ruff clean, `run_tests.py --parallel`
  7382 passed.

## 0.404.0 (2026-06-14) - Tier R7.9: ambiguous redirect + validator false positives (clears R7 bug list)
- BUG FIX (bash-verified; reappraisal #7 L3 + the recorded ambiguous-redirect
  follow-up, and L7).
- L3 a redirect target that (unquoted) expands to zero or more than one word is
  now an `ambiguous redirect` (exit 1), matching bash — fixing both the doubled
  `psh: No such file or directory: …` message on an empty target (`> $undef`)
  and the silently-exit-0 multi-word case (`v="a b"; > $v`). Detection falls out
  of expansion: a parsed `Redirect.target_word` (new field) is run through
  `expand_word_to_fields` (full pipeline incl. splitting/globbing); ≠1 field →
  `OSError("{word.source_text()}: ambiguous redirect", errno=None)` via the
  existing parent-raise / child-exit error paths. Quoted `> "$v"`, single-word,
  single-match glob, no-match-literal, and process-substitution targets are
  unaffected.
- L7 `--validate`/`EnhancedValidatorVisitor` false positives removed: array
  assignments (`x=(…)`, `x+=(…)`, `arr[0]=…`) now register the name as defined;
  C-style `for ((i=0;…))` init vars are registered; `$((…))` arithmetic is no
  longer misclassified as an unquoted variable expansion. Genuine
  undefined-variable warnings are retained.
- Tests: +`test_reappraisal7_ambiguous_redirect_conformance.py` (15, builtin +
  forked-child),  +`TestFalsePositiveRegressions` (8). Full gate green: ruff +
  mypy clean, `run_tests.py --parallel` 7382 passed, `--compare-bash` 461 passed.
- This CLEARS the reappraisal #7 bug list: all 5 HIGH, 9 MEDIUM, 7 LOW fixed
  except M8 (NUL termination), deferred into the byte-model/surrogateescape work
  alongside M7-from-#6.

## 0.403.0 (2026-06-14) - Tier R7.8: four feature gaps (M9 !!:-n, @K/@k, read -N, set -o history)
- BUG FIX (bash-verified; reappraisal #7 M9/L4/L5/L6).
- M9 `!!:-n` history word designator aborted with "bad word specifier"; it now
  expands as `:0-n` (word 0 through word n), e.g. `!!:-2` → first three words.
  (`history_expansion.py`)
- L4 `${var@K}` / `${var@k}` transforms were silent no-ops; now match bash: `@K`
  → one string `key "value" …` (keys bare, values @A-escaped+quoted); `@k` →
  separate unquoted `key value …` fields; scalar/element → the @Q-quoted value.
  (`operators.py`, `variable.py`, `fields.py`, `arrays.py`) Only residual diff is
  assoc-array hash-vs-insertion key order (pre-existing, same as `@A`).
- L5 `read -N count` implemented: reads EXACTLY count chars ignoring the
  delimiter and IFS (vs `-n`'s at-most-with-delimiter), short EOF → rc 1.
  (`read_builtin.py`)
- L6 `set -o history` / `set +o history` were rejected ("invalid option name");
  now accepted and meaningfully wired — `set +o history` disables history
  recording, and `set -o` reflects the state. (`state.py`, `shell.py`)
- Tests: +`test_param_transform_keyvalue_conformance.py` (14),
  +`test_read_exact_chars_conformance.py` (7), +`test_set_o_history_conformance.py`
  (4), +M9 unit case. Full gate green: ruff + mypy clean, `run_tests.py
  --parallel` 7359 passed, `--compare-bash` 461 passed.

## 0.402.0 (2026-06-14) - Tier R7.7: two syntax-error LOWs (L1 unterminated quote, L2 empty groups)
- BUG FIX (bash-verified; reappraisal #7 L1/L2) — psh now reports a syntax error
  (exit 2) where bash does.
- L1 an unterminated quote (`echo 'abc`, `echo "abc`, `echo $'abc`) exited 1 with
  `unexpected error: Unclosed ' quote` (it was misrouted to the internal-defect
  handler because `UnclosedQuoteError` subclasses `SyntaxError`, not
  `ParseError`). `source_processor` now catches `UnclosedQuoteError` → `psh:
  <loc>: syntax error` exit 2, matching the already-correct `$((`/`$(`/`${`
  unterminated handling. Interactive multi-line continuation is unaffected.
- L2 an empty subshell `()` / brace group `{ }` (and whitespace/comment-only
  variants) silently succeeded (exit 0); bash requires ≥1 command → syntax error
  exit 2. `parse_subshell_group`/`parse_brace_group` now reject an empty inner
  command list. Non-empty groups, nested groups, command substitution `$()`
  (legitimately empty), and arithmetic `(())` are unchanged.
- Tests: +`test_reappraisal7_syntax_errors_conformance.py` (23, exit-code vs
  bash); updated `test_empty_subshell` which pinned the old exit-0 behavior;
  refreshed README Project-Statistics file counts (drifted past the meta-test's
  10% gate). Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7329
  passed, `--compare-bash` 461 passed.

## 0.401.0 (2026-06-14) - Tier R7: mypy scope — all of io_redirect + executor (177 files); +bug fix
- TYPE-CHECKING SCOPE (reappraisal #7 lever). Added 17 modules so the ENTIRE
  `psh/io_redirect/` and `psh/executor/` packages are now type-checked: mypy
  covers **177 source files** (~80% of the tree). Nothing deferred in these two
  packages.
- BUG FIX caught by the wider scope (bash-verified): `_execute_in_background`
  was called on `BuiltinExecutionStrategy` but the method is named
  `_execute_builtin_in_background`, so backgrounding a POSIX special builtin
  (`: &`) raised `AttributeError` instead of running silently (bash: exit 0, no
  output). Fixed + regression test in `test_background_jobs.py`.
- Behavior-preserving type work: TYPE_CHECKING-only `redirects`/`background`
  annotations on the base `Command`; `ShellState.set_variable(value: Any)` (it
  legitimately receives array objects on scalar-append-to-array); `@overload` on
  `job_control.wait_for_job`'s dual return; array element-assignment key
  narrowing (extracted `_compute_element_value`); pipeline `pgid`/`pids`
  narrowing; assorted local annotations.
- Full gate green: mypy clean (177 files), ruff clean, `run_tests.py --parallel`
  7306 passed, `--compare-bash` 461 passed.

## 0.400.0 (2026-06-14) - Tier R7.6: in-process builtin honors a closed output fd
- BUG FIX (bash-verified; reappraisal #7 M1). `echo hi 1>&-` leaked `hi` to real
  stdout (and the brace-group/function paths leaked too): a builtin writes
  through the Python `sys.stdout`/`shell.stdout` object, but `>&-` only closed
  fd 1 at the fd level. Now closing fd 1/2 for an in-process builtin swaps the
  matching Python stream to a `_ClosedStream` (writes raise `OSError(EBADF)`),
  recorded in the snapshot so restore reinstates the original.
- Centralized the write-error handling in `executor/strategies.py`
  `execute_builtin_guarded`: a builtin's `OSError(EBADF/EPIPE)` on write now
  becomes bash's `NAME: write error: <strerror>` (exit 1) for EVERY builtin
  (was previously misclassified as an internal defect; `pwd` etc. now correct,
  not just echo/printf).
- Also fixed a pre-existing freed-fd-reuse bug: `cmd 1>&- 2>FILE` opened FILE
  onto the just-freed fd 1 then corrupted the shell's stdout on restore; the
  fd-level close is now deferred until after the command's other redirects
  (bash opens targets on high fds for the same reason).
- `2>&-` (closes only stderr), `<&-` (input close), normal output, and
  restore-after (`echo hi 1>&-; echo back` → `back`) all verified correct.
- Tests: +`test_reappraisal7_close_output_fd_conformance.py` (16 subprocess),
  +7 golden. Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7305
  passed, `--compare-bash` 461 passed.

## 0.399.0 (2026-06-14) - Refactor: share the redirect fd-backend application
- REFACTOR (zero behavior change). Finishes the RedirectPlan work by removing the
  remaining duplication across the three redirect dispatch sites. Two new
  `FileRedirector` helpers: `apply_fd_plan(plan, *, check_noclobber=True)` (the
  single fd-universe application switch over all redirect types) and
  `saved_fds_for_plan(plan)` (centralized save-fd selection). `apply_redirections`,
  `apply_permanent_redirections`, and `setup_child_redirections` all route
  through `apply_fd_plan`, each keeping its own distinct responsibilities — the
  parent's transactional save/restore, the permanent path's stream rebinds, and
  the child's `os._exit`-based error reporting (errno-bearing OSErrors →
  `psh: TARGET: STRERROR`; psh's own `errno=None` noclobber/dup messages →
  `psh: {e}`). The ~50-line duplicated child block collapses to one call.
- Saved-fd annotations tightened to `Tuple[int, int | None]` to reflect the
  high-fd restore case (`7>file`) where the original fd was unopened — already
  handled by `restore_redirections` (closes what it opened).
- Net −39 lines. Authored by the maintainer (PR #134); shipped through the
  release ritual after orchestrator verification: child-path noclobber/bad-fd
  probes match bash (message body + exit code), ruff + mypy clean (160 files),
  `run_tests.py --parallel` 7282 passed, `--compare-bash` 447 passed.

## 0.398.0 (2026-06-14) - Tier R7: mypy scope — expansion mixins + last interactive (160 files)
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 lever). Added 7 more
  modules → mypy now covers **160 source files**:
  - The four expansion MIXINS `arrays.py`/`fields.py`/`operands.py`/
    `operators.py` via a new `psh/expansion/_protocols.py` `VariableExpanderProtocol`
    (a `typing.Protocol` declaring the shared `state`/`shell`/`param_expansion`
    surface + cross-mixin methods). Each mixin declares it as a base ONLY under
    `if TYPE_CHECKING:` (the `_Base = Protocol else object` idiom) — zero runtime
    MRO/behavior change; cleared ~80 `attr-defined` errors.
  - `psh/interactive/line_editor.py` and `psh/utils/signal_utils.py` — the last
    two flagged interactive/util gaps.
- Real fixes the wider scope surfaced (behavior-preserving): latent
  `Optional[str]` operand flows in `operators.py` narrowed with `assert operand
  is not None` (mirrors the existing `variable.py` pattern; `None` only occurs
  for the separately-handled `${#var}` length); `signal_utils.SIGNAL_NAMES`
  typed `Dict[int,str]` (was inferred `Dict[Signals,str]`, breaking int-keyed
  `.get`); `line_editor.key_handler` typed as the binding union.
- Full gate green: mypy clean (160 files), ruff clean, `run_tests.py --parallel`
  7282 passed, `--compare-bash` 447.

## 0.397.0 (2026-06-14) - Tier R7.5: ~+/~-/~N tilde + "${!prefix@}" field-split
- BUG FIX (bash-verified; reappraisal #7 M3/M2).
- M3 `~+`/`~-`/`~N`/`~+N`/`~-N` tilde forms now expand: `~+`→`$PWD`, `~-`→
  `$OLDPWD`, `~N`/`~+N`→`dirs +N`, `~-N`→`dirs -N`; out-of-range/invalid stays
  literal. Two-part fix: the lexer (`recognizers/literal.py`) no longer split
  `~+` into two words (the `+` terminator broke it into `~`→$HOME + `+`), and
  `tilde.py` gained dir-stack/PWD/OLDPWD prefix handling. `echo ~+` → was
  `/Users/pwilson+`, now `$PWD`. Quoted `"~+"` and non-word-start `x~+` stay
  literal.
- M2 `"${!prefix@}"` now field-splits (one field per matched name, like `"$@"`):
  `x1=a x2=b; printf "[%s]" "${!x@}"` → was `[x1 x2]`, now `[x1][x2]`; `set --
  "${!x@}"; echo $#` → 2. The quoted `@`-form was reaching the scalar
  (space-joined) path; `fields.py` now routes `!@` through
  `match_variable_names`, distributing affixes like `"${arr[@]}"`. The `"${!x*}"`
  join-form and unquoted forms (already correct) are unchanged.
- Tests: +`test_dirstack_tilde_conformance.py` (13),
  +`test_prefix_indirection_fields_conformance.py` (10), +4 golden. Full gate
  green: ruff + mypy clean, `run_tests.py --parallel` 7282 passed,
  `--compare-bash` 447 passed.

## 0.396.0 (2026-06-14) - Tier R7: grow mypy scope into psh/parser (122 → 153 files)
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 lever). Added 31
  `psh/parser/` modules to the mypy `files` list: the recursive_descent backend
  (all 8 sub-parsers + support/context/helpers + the main parser), the AST
  visualization renderers, and the combinator core/tokens/utils/expansions/
  special_commands/heredoc. mypy now covers **153 source files**.
- Real type-bug fixes the wider scope surfaced (behavior-preserving): in
  `ast_nodes/redirects.py`, `Redirect.target` retyped `Optional[str]` (None is
  the runtime value for `>&-`/`2>&1` fd-dup/close forms) and the dynamically-set
  `heredoc_key` made an explicit `Optional[str]` field; `EnhancedTestStatement`
  now inherits `(Statement, CompoundCommand)` to match its runtime placement in
  `Pipeline.commands`; `formatter_visitor` guards a `None` close-redirect target
  (was a latent `TypeError`); `combinators/core.ParseResult.remaining` implicit-
  Optional fixed.
- Deferred (too noisy — mixin self-type plumbing): `combinators/commands.py` and
  `combinators/control_structures/*` (the combinator parser is educational-only,
  outside the production bar) — a `Protocol` would unlock them later.
- Full gate green: mypy clean (153 files), ruff clean, `run_tests.py --parallel`
  7255 passed, `--compare-bash` 439.

## 0.395.0 (2026-06-14) - Tier R7.4: SECONDS= / RANDOM= assignment (computed specials)
- BUG FIX (bash-verified; reappraisal #7 M6/M7). `SECONDS` and `RANDOM` were
  computed on READ but assignment was silently dropped (the read interceptor
  shadowed any stored value). Added a settable-computed-variable mechanism in
  `psh/core/scope.py`: assignment to an active SECONDS/RANDOM is intercepted
  (coerced to a signed int; non-integer → 0, like bash), records a baseline/seed,
  and `unset` reverts the name to an ordinary variable.
- M6 `SECONDS=N` now honored: `SECONDS=100; echo $SECONDS` → `100` (was `0`);
  `SECONDS=0; sleep 1; echo $SECONDS` → `1`.
- M7 `RANDOM=N` now seeds — and matches bash VALUE-FOR-VALUE: implemented bash
  5.x's exact generator (Park-Miller minimal-standard with Schrage; result
  `((seed>>16) ^ (seed&0xFFFF)) & 0x7FFF`). `RANDOM=1; echo $RANDOM $RANDOM
  $RANDOM` → `16807 10791 19566`, identical to bash. (Also fixed a latent
  side effect: `resolve_nameref_name` no longer advances RANDOM when merely
  inspecting the nameref flag.)
- Tests: +`TestSecondsAssignment` (8, bounded timing), +`TestRandomSeeding` (9),
  +`test_computed_special_vars_conformance.py` (`assert_identical_behavior`),
  +5 golden. Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7255
  passed, `--compare-bash` 439 passed.

## 0.394.0 (2026-06-14) - Tier R7.3: signal name/number bugs (kill -l, trap -l)
- BUG FIX (bash-verified; reappraisal #7 M4/M5). Established a SINGLE SOURCE OF
  TRUTH for signal name↔number in `psh/utils/signal_utils.py`, built from
  Python's `signal.Signals` enum (platform-correct: SIGEMT=7/SIGINFO=29 on
  macOS, self-adjusting on Linux), and routed `kill` and `trap` through it; the
  two divergent hand-maintained tables in `kill_command.py` were deleted.
- M4 `kill -l N`/`NAME`: `kill -l 9` → was an error, now `KILL`; `kill -l KILL`
  → was an error, now `9`; `kill -l 15`→`TERM`, `kill -l TERM`→`15`, `kill -l
  137`→`KILL` (N-128), `kill -l 0`→`EXIT`.
- M5 `kill -l` / `trap -l` (no arg): were garbled — `kill -l` omitted SIGEMT/
  SIGINFO (`7) 7`) with a non-bash layout; `trap -l` lexically sorted a map with
  pseudo-signals + duplicate rows. Both now render byte-identical to bash (and to
  each other) via `list_all_signals()`. `trap -p` SIG-prefix and signal sending
  unaffected.
- Tests: +`test_signal_listing_conformance.py` (12, `assert_identical_behavior`
  so platform numbers self-adjust). Full gate green: ruff + mypy clean,
  `run_tests.py --parallel` 7224 passed, `--compare-bash` 429 passed.

## 0.393.0 (2026-06-14) - Tier R7: grow mypy scope into the whole lexer (94 → 122 files)
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 lever). Added the
  ENTIRE `psh/lexer/` package (28 modules — pure_helpers, position, recognizers,
  modular_lexer, heredoc, cmdsub_scanner, keyword_normalizer, command_position,
  …) to the mypy `files` list. The lexer was previously the single largest
  untyped area; mypy now covers **122 source files**.
- Mostly annotation-only. Real fixes the wider scope surfaced (behavior-
  preserving): whitespace/comment recognizers' `(None, pos)` skip sentinel now
  matches a widened `Optional[Tuple[Optional[Token], int]]` return contract;
  `Dict[str, any]` (builtin `any`) → `Dict[str, Any]` in the heredoc lexer;
  Optional defaults and TYPE_CHECKING forward-refs in the quote/expansion
  parsers; None-narrowing in `token_stream`/`cmdsub_scanner`. The
  `token.heredoc_key` dynamic-attribute signal was deliberately kept dynamic
  (its presence is load-bearing) with an explanatory comment.
- Full gate green: mypy clean (122 files), ruff clean, `run_tests.py --parallel`
  7212 passed.

## 0.392.0 (2026-06-14) - Tier R7.2: three HIGH bugs (keyword-as-arg, shebang, pipeline prefix-env)
- BUG FIX (bash-verified; reappraisal #7 H1/H4/H5).
- H1 a keyword used as a plain ARGUMENT caused a parse error: `echo if then` →
  was a parse error, now `if then` (also `echo while do done`, `cat -- if
  then`). `keyword_normalizer._next_command_position` kept "command position"
  whenever a WORD's *value* spelled `if`/`while`/`until`; removed that branch
  (a real control keyword already carries its own token type). Real control
  structures, `time`, function defs, and post-`;`/`|`/`&&` keyword recognition
  all unchanged.
- H4 `psh script.sh` honored the script's `#!shebang` (re-dispatching e.g. to
  python3) instead of treating it as a comment like bash/sh/dash. Removed the
  shebang dispatch from the explicit-FILE path and DELETED the now-unused
  `psh/scripting/shebang_handler.py`. The exec path (`psh -c './x.sh'`) still
  respects the shebang via the kernel (unaffected).
- H5 a prefix assignment wasn't in the environment of an external command:
  `FOO=bar env | grep ^FOO` → was empty, now `FOO=bar`. Root: `apply_prefix`
  set the var without the EXPORT attribute, so `sync_exports_to_environment`
  dropped it from `shell.env` (this affected the `env` builtin generally, not
  just pipelines). `apply_prefix` now sets EXPORT and `restore` removes it for a
  previously-unexported var; export status of pre-existing vars is preserved.
- Tests: +`test_keyword_as_argument_conformance.py` (20),
  +`test_script_shebang_is_comment.py` (6 subprocess), +10 prefix-assignment
  cases, +7 golden. Full gate green: ruff + mypy clean, `run_tests.py
  --parallel` 7212 passed, `--compare-bash` 429 passed.
- Known deferred (pre-existing): `time` before a COMPOUND command still
  parse-errors (psh only supports `time SIMPLE_COMMAND`).

## 0.391.0 (2026-06-14) - Tier R7: grow mypy scope (arithmetic + executor/io small modules)
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 quality lever).
  Expanded the mypy `files` list from 85 → **95 source files**, all 100% clean:
  added the whole `psh/expansion/arithmetic` subpackage (7 files; self-contained,
  no mixin-self-type problem) plus `psh/io_redirect/planner.py`,
  `psh/executor/child_policy.py`, `psh/executor/process_launcher.py`.
- The three executor/io modules were already annotation-clean (zero edits). The
  arithmetic subpackage needed minor behavior-preserving edits: a real
  same-name/two-types fix in `parser.py` (a local rebound to both `ArithToken`
  and `ArithTokenType` → renamed), 3 `cast(...)` narrowings where
  `ArithToken.value` (`Union[str,int]`) is type-guaranteed, and None-narrowing
  rewrites of 8 tokenizer scan loops (capture `current_char()` into a local) —
  identical runtime behavior.
- Full gate green: mypy clean (95 files), ruff clean, `run_tests.py --parallel`
  7169 passed.

## 0.390.0 (2026-06-14) - Tier R7.1: two HIGH expansion bugs (extglob #, nameref arrays)
- BUG FIX (bash-verified; reappraisal #7 H2/H3).
- H2 `${var#pat}` shortest-prefix removal was greedy/broken with extglob:
  `shopt -s extglob; v=ooo; echo "${v#+(o)}"` → was empty, now `oo`. Root: a
  naive `regex.replace('.*','.*?')` never touched extglob quantifiers and
  `extglob_to_regex(from_start=True)` emitted a `$`-anchored regex, so `#`
  behaved like `##` (and `##` itself was broken too). Rewrote
  `remove_shortest_prefix`/`remove_longest_prefix` to mirror the correct suffix
  path (scan prefix lengths, full-match each candidate). (`parameter_expansion.py`)
- H3 namerefs didn't dereference on ARRAY reads: `declare -a arr=(10 20 30);
  declare -n r=arr; echo "${r[@]}"` → was `arr`, now `10 20 30`; `${r[1]}`,
  `${#r[@]}`, `${!r[@]}`, associative namerefs, and slicing all fixed. Added a
  single nameref-aware array-name resolution point (`_resolve_array_name` in
  `ArrayOpsMixin`) and routed every array read/write site through it
  (`arrays.py`, `variable.py`, `fields.py`, `operators.py`,
  `executor/array.py`). Element-nameref `declare -n r=arr[1]` matches bash; the
  write path (`r[3]=x` → `arr[3]`) resolves too; non-nameref arrays unchanged.
- HYGIENE: added `.claude/` to `.gitignore` (worktrees + agent transcripts must
  never be committed).
- Tests: +`test_extglob_parameter_expansion_conformance.py` (33),
  +`test_nameref_array_conformance.py` (17); removed an obsolete xfail that
  pinned the old broken extglob behavior. Full gate green: ruff + mypy clean,
  `run_tests.py --parallel` 7169 passed, `--compare-bash` 415 passed.

## 0.389.0 (2026-06-14) - Docs: ground-up reappraisal #7 (post-R6 scorecard)
- DOCS ONLY. Added `docs/reviews/ground_up_reappraisal_7_2026-06-14.md`: a fresh
  five-cluster scorecard taken after the Tier R6 bug-fix campaign.
- Scorecard: overall **A−** (stable). Core/Builtins promoted B+→A− (R6 cleared
  its read/declare bug density); the other four clusters held A−. All R6 fixes
  verified clean with no regressions. mypy scope ~85/222 files (~38%).
- Deeper fresh-eyes probing found a NEW bash-verified bug list (not in #6): 5
  HIGH (keyword-as-arg `echo if then` parse error; `${var#}` shortest-prefix
  greedy with extglob; namerefs don't deref on array reads; `psh script.sh`
  honors a foreign shebang; prefix-assignment not exported to an external
  command in a pipeline), 9 MEDIUM, 7 LOW — plus the half-finished mypy lever.
  Defines the "Tier R7" worst-first bug-fix phase.

## 0.388.0 (2026-06-14) - Tier R6.10: history word designators (clears R6 bug list)
- BUG FIX (bash-verified; reappraisal #6 L10, the final R6 bug). History
  expansion only handled EVENT designators (`!!`, `!n`, `!string`); word
  designators were unimplemented, so `!$` returned event-not-found and `!!:1`
  left a literal `:1` garbage suffix on the command.
- Implemented bash word designators in `history_expansion.py`: `:0`, `:n`,
  `:^`, `:$`, `:*`, `:n-m`, `:n-`, `:n*`; the bare shorthands `!$`/`!^`/`!*`
  (default to the previous command) and `!:n`; attachable to any event
  (`!1:$`, `!echo:^`, `!-2:2`). Quote-aware word splitting; `!*` with no args →
  empty; out-of-range → `bad word specifier` — all matching bash. The
  documented user-guide `!$` example now works; added a "Word Designators"
  doc subsection.
- Deferred (recorded follow-up): the `:s/old/new/`, `:p`/`:h`/`:t`/`:r`/`:e`
  modifiers and `^old^new^` quick-substitution (lower-priority modifier class).
- Tests: +`tests/unit/interactive/test_history_word_designators.py` (39). Full
  gate green: ruff + mypy clean, `run_tests.py --parallel` 7135 passed,
  `--compare-bash` 415 passed.
- This clears the reappraisal #6 bug list: all 4 HIGH, 9 MEDIUM, and 11 LOW are
  fixed except M7 (high `\xHH`/`\NNN` byte-vs-codepoint), which remains deferred
  pending a dedicated output-encoding (surrogateescape) change.

## 0.387.0 (2026-06-14) - Tier R6.9: shopt nocasematch + query exit code
- BUG FIX (bash-verified; reappraisal #6 L6).
- `shopt -s nocasematch` is now supported and fully wired: `[[ ]]` `==`/`!=`/`=~`
  and `case` matching become case-insensitive (`re.IGNORECASE`) when set.
  `[[ ABC == abc ]]` → match; case-sensitive behavior unchanged when unset.
  (`state.py`, `shell_options.py`, `expansion/pattern.py`,
  `enhanced_test_evaluator.py`, `control_flow.py`)
- Also fixed the `shopt OPTION` / `shopt -p OPTION` QUERY exit code (was always
  0; now 1 when a named option is unset, matching bash — affected all options),
  and padded the option-listing name field to bash's width.
- Honesty preserved: genuinely-unimplemented bash options (`failglob`,
  `lastpipe`, `inherit_errexit`, `histappend`, …) still error rather than
  becoming fake no-ops.
- Tests: +`test_nocasematch_conformance.py` (14 `assert_identical_behavior`),
  +3 golden cases; updated one shopt unit test that pinned the old exit-0 query.
  Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7096 passed,
  `--compare-bash` 415 passed.

## 0.386.0 (2026-06-14) - Tier R6.8: metrics pipeline count + version-sync meta-test
- BUG FIX (reappraisal #6 L11). `MetricsVisitor` counted every `Pipeline` AST
  node, but psh wraps every command in a single-element Pipeline — so a script
  with no `|` reported "Pipelines: N". Now only genuine pipelines
  (`len(node.commands) > 1`) are counted (and contribute to max-pipeline-length).
  `metrics_visitor.py`; +regression test.
- TOOLING. Added `tests/unit/tooling/test_version_sync.py`: a meta-test that
  fails if `psh/version.py`'s `__version__` and the `**Current Version**:` lines
  in README.md/ARCHITECTURE.md drift apart, or if CHANGELOG.md lacks a `##
  <version>` entry — closing the one staleness gap the meta-test layer did not
  guard (CLAUDE.md mandates these match but nothing enforced it).
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` (all phases).

## 0.385.0 (2026-06-14) - Tier R6.7: io_redirect bugs (M9/L2/L4)
- BUG FIX (bash-verified; reappraisal #6 M9/L2/L4).
- M9 write-side `>(cmd)` leaked a `$TMPDIR/psh-psub-XXXX/` FIFO dir per run when
  the consumer ran in a pipeline (the pipeline child execs, so the parent's
  `process_sub_scope` cleanup never ran in it). The substitution worker now
  unlinks its own FIFO + temp dir right after opening it for read (an opened
  FIFO survives unlink — robust to the consumer's `os._exit`/exec). No leak in
  pipeline / non-pipeline / multiple-`>()` / nested forms; data delivery intact.
  (`process_sub.py`)
- L2 redirect-open failures leaked Python's `OSError` repr (`psh: error: [Errno
  2] ...: 'path'`); now emit bash's `psh: TARGET: STRERROR` (e.g. `psh:
  /badpath/nope: No such file or directory`) for both the forked-child and
  builtin redirect paths, exit code unchanged. psh's custom noclobber/ambiguous
  messages (errno is None) are preserved. (`manager.py`, `command.py`)
- L4 `exec 1>&-` then writing crashed with exit 120 + an "Exception ignored
  while flushing sys.stdout" finalizer leak. `echo`/`printf` now catch the
  write OSError and report `write error: <strerror>` returning 1 (like bash),
  and an atexit guard rebinds a closed std stream to /dev/null so the shutdown
  flush is a silent no-op. (`io.py`, `__main__.py`)
- Tests: +`TestWriteSideFifoFilesystemLeak` (4),
  +`test_reappraisal6_redirect_errors_conformance.py`. Full gate green: ruff +
  mypy clean, `run_tests.py --parallel` 7075 passed, `--compare-bash` 409.
- Noted out-of-scope (recorded): `echo hi > $v` with `v="a b"` (ambiguous
  redirect) returns 0 in psh vs bash's exit 1.

## 0.384.0 (2026-06-14) - Tier R6.6: lexer/parser bugs (M8/L1/L9; M7 deferred)
- BUG FIX (bash-verified; reappraisal #6 M8/L1/L9).
- M8 ANSI-C `$'\cX'` control-char escape now supported (`$'a\cIb'` → `a<TAB>b`).
  bash's mapping: `0x7f` for `\c?`, else `ord(X) & 0x1f` (so `\cI`→TAB, `\c@`→
  NUL, `\cA`→0x01); bare trailing `\c` stays literal. (`lexer/pure_helpers.py`)
- L1 `${}`/`${ }`/`${1abc}`/`${!.foo}` now correctly raise `bad substitution`
  (exit 1) at runtime, while valid forms (`${12}`, `${a-x}`, `${#}`, `${-}`,
  `${arr[0]}`, `${!ref:-d}`) still work. New `BadSubstitutionError`,
  `validate_parameter_expansion` in `param_parser.py` called at the two runtime
  expansion chokepoints. (`variable.py`, `evaluator.py`, `exceptions.py`)
- L9 parser ErrorContext "Context:" line was built backwards (following tokens
  before `-> HERE <-`, preceding after) and leaked raw `TokenType.EOF`. Now
  before/after are on the correct sides with `<EOF>`/`<newline>` placeholders.
  (`parser/recursive_descent/context.py`, `helpers.py`)
- M7 DEFERRED (documented): high `\xHH`/`\NNN` escapes emit Unicode codepoints
  not raw bytes (`$'\377'` → 2 UTF-8 bytes, bash 1). A correct fix requires
  flipping psh's entire output-encoding contract to `surrogateescape` (11
  encode sites + sys.stdout + file redirects + pytest capture) — deep regression
  risk; left for a dedicated change.
- Tests: +`test_ansi_c_control_escape_conformance.py` (11),
  +`test_bad_substitution_conformance.py`, +`test_error_context_format.py` (4).
  Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7063 passed,
  `--compare-bash` 409 passed.

## 0.383.0 (2026-06-14) - Tier R6.5: four builtin/state small bugs
- BUG FIX (bash-verified; reappraisal #6 M5/M6/L7/L8).
- M5 `unset -f NONEXISTENT` now silently returns 0 (was an error + exit 1),
  matching `unset -v`. (`environment.py`)
- M6 `test`/`[` gained the `<` / `>` string-comparison operators (ASCII order,
  not locale): `[ a \< b ]` → 0 (was "binary operator expected", exit 2).
  (`test_command.py`)
- L7 `trap -p` now prints the canonical signal name: real signals get the `SIG`
  prefix (`TERM`→`SIGTERM`, numeric `15`→`SIGTERM`), pseudo-signals
  (EXIT/ERR/DEBUG/RETURN) stay bare. (`trap_manager.py`)
- L8 `$-` now matches bash: it no longer includes `s` (stdin) in `-c` or
  script-file mode, the flag order is bash's (lowercase-then-uppercase
  alphabetical with invocation flags `c`/`s` appended last), and `H`
  (histexpand) is interactive-only. E.g. `psh -c 'echo $-'` → `hBc` (was
  `chsBH`). (`state.py`, `__main__.py`, `script_executor.py`, `shell.py`)
- Tests: +`test_reappraisal6_builtin_state_conformance.py` (32) +9 golden;
  updated two tests that pinned the old `$-`/histexpand behavior (verified vs
  bash). Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7033
  passed, `--compare-bash` 409 passed.

## 0.382.0 (2026-06-14) - Tier R6.4: array-element-write bugs
- BUG FIX (bash-verified; reappraisal #6 M4 + a related follow-up).
- M4 negative array index was rejected on WRITE (reading already worked):
  `a=(1 2 3); a[-1]=X` now maps `-1` to the last element (was an error that even
  classified as an internal defect under strict-errors). Implemented bash's rule
  `-N → highest_index + 1 - N` (sparse-aware) in `IndexedArray.resolve_write_index`,
  covering all write paths: literal `a[-1]=`, `a[-1]+=`, and arithmetic
  `(( a[-1]=9 ))`. Out-of-range raises a new `ArraySubscriptError(PshError)`
  (`psh: NAME[SUB]: bad array subscript`, exit 1) instead of an internal defect;
  a failed `unset b; b[-1]=x` leaves `b` unset like bash. Negative subscripts on
  ASSOCIATIVE arrays remain literal keys (mapping applies to indexed only).
- Related follow-up: the integer (`-i`) attribute is now applied on subscript
  assignment too — `declare -ia v; v[0]=2+3` → `([0]="5")` (was `2+3`); `+=` does
  a numeric add. (declare-time element eval was fixed in v0.381; this is the
  later-assignment path.)
- Also: a bare `a[i]=v` assignment now propagates its exit status and a failed
  one aborts a non-interactive script (matching bash's assignment fatality).
- Tests: +`TestNegativeIndexWrite` (10) +`TestIntegerArrayElementAssignment` (5)
  conformance, +8 golden cases. Full gate green: ruff + mypy clean, `run_tests.py
  --parallel` 6991 passed, `--compare-bash` 391 passed.

## 0.381.0 (2026-06-14) - Tier R6.3: four declare/attribute bugs
- BUG FIX (bash-verified; reappraisal #6 M1/M2/M3/L5).
- M1 `declare -i` was ignored when combined with `-l`/`-u` (`declare -il v=5+3`
  → was `"5+3"`, now `"8"`). `scope.py:_apply_attributes` now evaluates the
  integer attribute FIRST, then case-folds the result (they were exclusive
  `if/elif`).
- M2 `declare -p` attribute-letter order was wrong. Empirically determined
  bash's order to be `a A i n r t x l u` (case-fold flags last) and fixed
  `declare_format.py:_FLAG_CHARS`: `declare -ix` now prints `-ix` (was `-xi`),
  `-ir`→`-ir`, `-irx`→`-irx`.
- M3 `-a`/`-A` combined with `-i`/`-l`/`-u` didn't actually make the var an array
  (`declare -ia v=1` → was scalar `="1"`, now `([0]="1")`); array elements now
  receive the integer/case attributes (`declare -ia v=(1+1 2+2)` → `([0]="2"
  [1]="4")`, `declare -al v=(ABC)` → `abc`). (`function_support.py`)
- L5 `declare -F name` printed `declare -f name`; now prints the bare function
  name (the no-arg `-F` listing form is unchanged). `-f`/`-F NAME` not-found is
  now silent with exit 1 (was printing an error).
- Known follow-ups (recorded, separate code paths): assoc-array `declare -p`
  trailing-space-before-`)`; element-level integer attr on direct subscript
  assignment (`v[0]=2+3`).
- Tests: +`tests/conformance/bash/test_declare_attributes_conformance.py` (24
  `assert_identical_behavior`). Full gate green: ruff + mypy clean, `run_tests.py
  --parallel` 6969 passed, `--compare-bash` 375 passed.

## 0.380.0 (2026-06-14) - Tier R6.2: read C-escapes + source positionals (HIGH)
- BUG FIX (bash-verified; reappraisal #6 H3/H4).
- H4 `source`/`.` with NO args wiped the caller's positional params:
  `set -- A B C; source f` (f: `echo "$@"`) → was empty, now `A B C`.
  `source_command.py` only overrides `$@` when extra args are actually given
  (`len(args) > 2`); `source f X Y` still sets `X Y` inside and restores `A B C`
  after. `.` (dot) fixed identically.
- H3 `read` (without `-r`) wrongly did C-style escape translation
  (`\t`→TAB, `\n`→newline). bash `read` only strips the backslash (next char
  literal), protects escaped IFS chars from splitting, and treats a trailing
  `\<newline>` as line continuation. Rewrote `read_builtin._process_escapes` to
  return (char, protected) pairs; added line-continuation re-reading
  (`_read_continuations`) and backslash-protected IFS splitting/trimming. `-r`
  stays fully literal. `a\tb`→`atb`, `a\ b`→one field `a b`, `a\`+newline+`b`→
  `ab`. Also fixed a related divergence: a defaulted `REPLY` (no var names) must
  NOT be IFS-whitespace-trimmed, while `read v`/`read REPLY` are.
- Known remaining follow-up (recorded): `read x < file_without_trailing_newline`
  returns rc 0 in psh vs 1 in bash (EOF-without-delimiter) — separate from
  escapes.
- Tests: +`tests/conformance/bash/test_read_escapes_conformance.py` (19
  `assert_identical_behavior`), +3 source conformance cases; rewrote one read
  unit test that pinned the old (wrong) line-continuation behavior. Full gate
  green: ruff + mypy clean, `run_tests.py --parallel` 6945 passed,
  `--compare-bash` 375 passed.

## 0.379.0 (2026-06-14) - Tier R6.1: three expansion bash-divergence bugs
- BUG FIX (bash-verified; reappraisal #6 H1/H2/L3).
- H1 `${var#}` (empty removal pattern) returned the LENGTH: `v=abc; echo
  "${v#}"` → was `3`, now `abc`. The parser already distinguished `${#v}`
  (operand `None` = length) from `${v#}` (operand `''` = empty pattern), but
  `node.word or ''` collapsed `None`→`''` at the call sites and the length
  branches used `not operand`. `None` is now preserved end-to-end and every
  length-vs-removal test uses `operand is None` (`evaluator.py`, `variable.py`,
  `operators.py`, `fields.py`). Also fixed a pre-existing `${*#a}` mis-handling.
- H2 extglob `!(pat)` negation failed when the subject STARTS with the pattern:
  `[[ foobar == !(foo) ]]` → was `N`, now `Y`; `${v##!(foo)}` on `foobar` → was
  `foobar`, now empty. A standalone `!(...)` now compiles to a whole-string
  negative lookahead `(?!(?:alts)$).*` (`extglob.py`), and the removal operators
  match-and-invert against the positive pattern span-by-span
  (`parameter_expansion.py`). Embedded `?()/*()/+()/@()` and `a!(b)c` unchanged.
- L3 zero-width extglob over-substituted in `${v//pat/repl}`: `v=xyz;
  "${v//*(q)/-}"` → was `-x-y-z-`, now `-x-y-z`. The global-substitution path
  now suppresses Python `re.sub`'s extra end-of-string empty match (only when
  the pattern can match empty; ordinary patterns keep the fast path).
- Known remaining follow-up (recorded): embedded `!()` in REMOVAL operators
  (`${v#a!(x)}`) still diverges — needs the span-search generalized to embedded
  position.
- Tests: +`TestStandaloneNegationExtglob`, +3 POSIX parameter-expansion methods,
  +13 golden cases. Full gate green: ruff + mypy clean, `run_tests.py
  --parallel` 6923 passed, `--compare-bash` 375 passed.

## 0.378.0 (2026-06-14) - Docs: ground-up reappraisal #6 (post-campaign scorecard)
- DOCS ONLY. Added `docs/reviews/ground_up_reappraisal_6_2026-06-14.md`: a fresh
  five-cluster scorecard taken after the #5 refactor campaign (v0.355–v0.377).
- Scorecard: Lexer/Parser/AST B+→A−, Executor/io_redirect B+→A−, Expansion A−
  (held), Interactive/Scripting/Visitor/Tooling A− (held), Core/Builtins B+
  (held). Overall **A−** — the campaign moved the grade up from #5's B+/A−;
  mypy scope grew ~21→85 files (~38%).
- The remaining gap to a clean A is now a concrete, bash-verified BUG LIST (not
  architecture): 4 HIGH (`${var#}` returns length; extglob `!(pat)` negation;
  `read` non-raw C-escapes; `source` no-args wipes positionals), 9 MEDIUM, 11
  LOW — plus finishing mypy coverage (lexer/parser, expansion mixins). Defines
  the "Tier R6" worst-first bug-fix phase.

## 0.377.0 (2026-06-14) - Behavior fix: extglob inside [[ ]] pattern operands
- BUG FIX (bash-verified; final recorded follow-up). `[[ abc == a@(b|x)c ]]`
  raised a parse error (`Expected DOUBLE_RBRACKET, got LPAREN`); psh now matches
  bash for extended-glob patterns (`?(...)`, `*(...)`, `+(...)`, `@(...)`,
  `!(...)`) in `[[ ]]` `==`/`!=` operands, including adjacent/nested groups and
  trailing globs.
- KEY INSIGHT: extglob in `[[ ]]` is UNCONDITIONAL in bash — it works whether or
  not `shopt -s extglob` is set (and `shopt` on the same `-c` line is lexed
  before it runs anyway). Fixes:
  - Lexer (`recognizers/literal.py`, `operator.py`): new shared predicate
    `extglob_active(config, context)` = `enable_extglob OR bracket_depth > 0`,
    used at the four extglob gates, so an unquoted extglob group is tokenized
    inside `[[ ]]` instead of leaking a stray `LPAREN`.
  - Evaluator (`enhanced_test_evaluator._pattern_match`): `[[ ]]` `==`/`!=`
    matches with extglob always enabled; quoted parts stay glob-escaped
    (`[[ abc == "a@(b|x)c" ]]` remains a literal non-match).
  - Both parser backends benefit (the lexer is shared).
- Adjacent paren constructs verified UNAFFECTED vs bash: `=~` regex grouping +
  `BASH_REMATCH`, `(( ))` arithmetic, `$(...)`, `( subshell )`, `case` patterns,
  and `[[ ( … ) && ( … ) ]]` test-grouping.
- Documented divergence left unchanged (low value, high regression risk): LHS
  extglob `[[ a@(b)c == abc ]]` — bash syntax-errors, psh parses to a non-match.
- Tests: new `tests/conformance/bash/test_double_bracket_extglob_conformance.py`
  (12 `assert_identical_behavior`) + 6 golden cases.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6901 passed,
  `pytest tests/behavioral --compare-bash` 349 passed.

## 0.376.0 (2026-06-14) - Docs: sync io_redirect/CLAUDE.md with the planner refactor
- DOCS ONLY. Updated `psh/io_redirect/CLAUDE.md` for the v0.375.0 planning
  refactor: added `planner.py` to the Key Files table and the architecture
  diagram, documented `ProcessSubstitutionResource` in `process_sub.py`, added a
  "Shared Planning Phase (`RedirectPlanner`/`RedirectPlan`)" pattern section
  (including the `try/finally: plan.close_procsub(applied=…)` fd-leak-safety
  invariant and `plan.target_fd` as the target-fd source of truth), and updated
  the "Adding a New Redirection Type" steps to go through `planner.plan()`.

## 0.375.0 (2026-06-14) - Redirection: unified RedirectPlan + ProcessSubstitutionResource
- REFACTOR + BUG FIX. Introduced a shared redirection "planning" phase so the
  four dispatch sites (`FileRedirector.apply_redirections`,
  `apply_permanent_redirections`, `IOManager.setup_builtin_redirections`,
  `setup_child_redirections`) stop duplicating resolve→expand→procsub logic:
  - New `psh/io_redirect/planner.py`: `RedirectPlan` (resolved redirect +
    target + optional procsub resource, with a `target_fd` property and
    `close_procsub(applied=)`) and `RedirectPlanner.plan()`.
  - New `ProcessSubstitutionResource` dataclass in `process_sub.py` encapsulates
    `(path, parent_fd, pid, cleanup_path)` with `register_with(handler)` and
    `close_parent_fd_for_redirect(redirect, applied=)`. `resolve_procsub_target`
    (bare tuple) → `resolve_procsub_resource` (object); the static
    `FileRedirector._close_procsub_parent_fd` and `IOManager.
    _builtin_procsub_target` are folded in and removed.
- BUG FIX (fd leak on failure): the old code closed a redirect-target process
  substitution's parent fd UNCONDITIONALLY after the if/elif chain, so if a
  LATER redirect in the same command failed (e.g.
  `cat < <(echo data) > /nonexistent/out`) the close was skipped and the parent
  fd leaked. Each redirect is now applied under `try/finally:
  plan.close_procsub(applied=…)`, guaranteeing cleanup on the failure path for
  both the per-command and permanent (`exec`) paths. +2 regression tests in
  `test_process_sub_cleanup.py`.
- `plan.target_fd` faithfully unifies the per-branch target-fd classification
  (verified identical to the old inline logic and `_heredoc_fd`). No stale
  callers of the removed methods remain; no runtime import cycle.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6883 passed.

## 0.374.0 (2026-06-14) - Lint fix: LinterVisitor now analyzes redirect targets
- BUG FIX (follow-up recorded during T2.7). `LinterVisitor` never traversed
  `node.redirects` in its explicit handlers and had no `visit_Redirect`, so all
  lint checks were blind to expansions inside redirect targets and heredoc
  bodies — `echo hello > $undefined.log` reported "No issues found!".
- Mixed in the shared `RedirectTraversalMixin` (matching security/validator/
  metrics), added `self._visit_redirects(node)` to `visit_SimpleCommand`,
  `visit_FunctionDef`, and `visit_IfConditional` (loops/groups already reach
  redirects via `generic_visit`), and added a `visit_Redirect` that runs
  `_check_variable_usage` on the target (skipping dup-fd synthetic `&1`) and on
  expandable heredoc bodies (skipping quoted heredocs/here-strings).
- Now correctly warns on undefined vars in redirect targets and records used
  vars there (no more spurious "defined but never used" for a var used only in a
  redirect). Verified NO false positives — redirect filenames are treated as
  words/expansions, never as commands; non-redirect output is unchanged.
- Added `TestLinterRedirectTargets` (7 tests). Full gate green: ruff + mypy
  clean, `run_tests.py --parallel` 6881 passed.

## 0.373.0 (2026-06-14) - Behavior fix: two brace-expansion divergences from bash
- BUG FIX (bash-verified; follow-ups recorded during T3.3). Two brace-expansion
  cases now match bash:
  - **Char-range backslash**: `echo {Z..a}` included a literal `\` (ASCII 92);
    bash emits an EMPTY word at the backslash position instead (kept, not
    dropped — unlike an empty list item `{a,,b}` which bash drops). Implemented
    with a private-use sentinel so the single-token path keeps the empty word
    while the empty-list filter still drops list empties, and the composite path
    (`x{Z..a}y`) strips it. `{A..z}`, `{a..Z}` (reverse), `{Z..a..2}` (step) all
    match bash now; pure-letter/pure-digit ranges unaffected.
  - **Stray-brace neighbors**: `echo }{a,b}{` was left literal; bash finds and
    expands the inner valid group → `}a{ }b{` (likewise `a}{b,c}d` → `a}bd
    a}cd`). Removed the all-or-nothing balance bail; the group finder now scans
    each `{` for its matching `}` (tracking nesting, skipping `${...}`) and
    treats truly stray/unmatched braces as literal. Valid groups, genuine
    non-groups (`{a,b` stays literal), `${...}`, and nesting are unchanged.
- Tests: +`TestCharRangeBackslash` (6) +`TestStrayBraceNeighbors` (9); new
  `tests/conformance/bash/test_brace_expansion_conformance.py` (17
  `assert_identical_behavior`); +5 golden cases; updated one relocation test to
  the corrected word count.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6874 passed,
  `pytest tests/behavioral --compare-bash` 337 passed.

## 0.372.0 (2026-06-14) - Tier T3.3: brace_expansion.py clarity refactor
- REFACTOR (zero behavior change). `psh/expansion/brace_expansion.py` was the
  last large file at the old altitude; reorganized into explicitly-named,
  top-to-bottom phases with per-phase docstrings: drive-to-fixed-point
  (`_expand_braces`/`_did_expand`), expand-leftmost-and-recombine
  (`_expand_one_brace` → `_generate_items`/`_split_detachable_suffix`/
  `_combine`), locate-a-group (`_find_brace_group` returning a frozen
  `_BraceGroup` dataclass; `${...}` skip extracted to
  `_skip_parameter_expansion`; validation split), lists (`_expand_list` +
  `_split_top_level_commas`), and sequences (`_try_numeric_sequence`/
  `_try_char_sequence` sharing new `_normalize_step` + `_format_padded` helpers).
  Magic operator strings named as module constants.
- Max body-nesting depth 6 → 4; removed an unreachable `isdigit` branch in the
  char-sequence path (digits always take the numeric path first).
- Two frozen characterization batteries (73-case: lists/sequences/nesting/
  escaping/degenerate/multi-word; 12-case: assignment-zone suppression, pipes,
  loops, background, quoting) are byte-identical before/after.
- Noted (pre-existing, NOT fixed): two brace-vs-bash divergences — `{Z..a}`
  backslash handling in the char range, and `}{a,b}{` (psh leaves literal, bash
  expands the inner group).
- Full gate green: ruff + mypy clean (file in scope), `run_tests.py --parallel`
  6837 passed.

## 0.371.0 (2026-06-14) - Tier T3.1: finish [[ ]] Word adoption (+ quoting fixes)
- REFACTOR + BEHAVIOR FIX (bash-verified). The `[[ ]]` binary-test operands are
  now genuine multi-part `Word`s carrying per-part quote context (like
  `SimpleCommand` words), and the evaluator decides pattern-vs-literal PER PART
  by reading those parts. The `right_quote_type` single-char sentinel (the last
  remnant of the pre-Word model, kept derived since v0.348) is deleted.
- Parser (`recursive_descent/parsers/tests.py` + combinator
  `special_commands.py`): `_parse_test_operand`/`_parse_regex_operand` build a
  `Word` with one `WordPart` per glued token, each carrying its own
  `quoted`/`quote_char`; all expansion kinds (not just `$x`) become real
  `ExpansionPart`s via the shared `WordBuilder.parse_expansion_token`. The
  flatten-to-single-`LiteralPart` helper is gone.
- Evaluator (`enhanced_test_evaluator.py`): new `_rhs_pattern`/`_rhs_regex`
  build the glob/regex from the RHS Word's parts — quoted parts contribute
  literal text (glob-escaped / `re.escape`'d), unquoted parts keep glob/regex
  power; quote-aware subject building replaces the old blanket backslash strip.
- Bash divergences FIXED (this is the behavior-fix item): per-part quoting
  `[[ abc == ab"?" ]]` (was wrongly 0 → now 1) and backslash-escaped regex
  metacharacters `[[ "axc" =~ a\.c ]]` (was wrongly 0 → now 1). Preserved
  out-of-scope: extglob inside `[[ ]]` (lexer doesn't tokenize it there).
- Tests: updated `test_enhanced_test_word_operands.py`; added
  `tests/conformance/bash/test_double_bracket_quoting_conformance.py` (12 tests,
  all `assert_identical_behavior`) and 4 golden cases (`--compare-bash`).
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6837 passed,
  `pytest tests/behavioral --compare-bash` 327 passed.

## 0.370.0 (2026-06-13) - Write-side process substitution via FIFO (macOS fix)
- BUG FIX (platform robustness). Write-side process substitution `>(cmd)` used a
  `/dev/fd/N` pipe path. On macOS, an external consumer (e.g. `tee >(cmd)`)
  reopening that write-only pipe through `/dev/fd` can fail with EPERM — so the
  two known `/dev/fd`-sandbox failures (`test_write_side_substitution_tee`,
  `test_dup_stdout_to_arithmetic_fd`) only passed in some environments.
- `>(cmd)` now uses a named FIFO (`tempfile.mkdtemp` + `os.mkfifo`) so consumers
  open a normal path; the substitution child reads the FIFO on stdin with a
  5-second SIGALRM open-timeout (falls back to `/dev/null` if nothing ever
  opens it, so the child never blocks forever). `create_process_substitution`
  now returns a 4-tuple `(parent_fd, path, pid, cleanup_path)` — `parent_fd` is
  `None` for FIFO-backed write side — and `ProcessSubstitutionHandler` tracks
  `active_paths`, unlinking the FIFO + its temp dir at scope exit. Read-side
  `<(cmd)` is unchanged (still a pipe).
- `file_redirect.py`: extracted `_rebind_input_stream(target_fd)` so the four
  permanent-input-redirect arms (`<`, `<>`, heredoc, here-string) share one
  fd-0-only stdin-rebind rule; `<>` now captures `target_fd` so it rebinds stdin
  only when fd 0 actually changed (matching `<`).
- Tests: `test_dup_stdout_to_arithmetic_fd` rewritten to write a `tmp_path` file
  instead of `/dev/stdout` (portable); added `TestExecStdinRedirect`
  (`exec <file` + `read`; `exec 5<file` must not replace stdin).
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6810 passed,
  `pytest tests/behavioral --compare-bash` 319 passed.

## 0.369.0 (2026-06-13) - Tier T3.2: separate-bracket array syntax matches bash
- BEHAVIOR FIX (bash-verified) + REFACTOR (−185 lines). `a [ 0 ] = v` (with
  spaces around the brackets) is NOT array-assignment syntax — bash parses it as
  the simple command `a` with args `[ 0 ] = v`. psh instead raised a parse error
  via ~185 lines of bespoke "separate-bracket" detection machinery in
  `psh/parser/recursive_descent/parsers/arrays.py`.
- The machinery was also OVER-EAGER: it fired on ANY identifier-named command
  word followed by `[`, so it broke real commands too — `echo [ 0 ] = v` and
  `a() { echo hi "$@"; }; a [ 0 ] = v` both raised parse errors in psh while bash
  runs them. Deleting the machinery makes all of these fall through to normal
  simple-command execution, matching bash (command-not-found 127 for `a`,
  correct output for real commands/functions).
- Valid array assignment is untouched: `a[0]=v`, `a[0]+=v`, `a[ 0 ]=v` (spaces
  only INSIDE the brackets), `declare -a`/`-A`, associative `m[k]=v` all behave
  exactly as before. (The combinator parser never had this bug.)
- Removed `_candidate_separate_bracket`, `_scan_bracket_assignment`,
  `_is_valid_variable_name`, `_parse_array_key_tokens`,
  `_parse_separate_bracket_element`, the `separate_bracket` field, and the two
  routing branches.
- Tests: flipped the 4 separate-bracket entries in the array-assignment
  characterization corpus from frozen-ERR to OK (verified vs bash); added 6
  `tests/behavioral/golden_cases.yaml` cases (pass under `--compare-bash`) and a
  `TestSeparateBracketIsNotAssignment` conformance class (7 tests).
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6808 passed,
  `pytest tests/behavioral --compare-bash` 319 passed.

## 0.368.0 (2026-06-13) - Tier T2.7: shared redirect-traversal mixin for visitors
- REFACTOR (zero behavior change). The analysis visitors each duplicated the
  skeleton that walks a command's `redirects` to dispatch into them. Extracted a
  `RedirectTraversalMixin._visit_redirects(node)` in
  `psh/visitor/analysis_helpers.py`; routed `SecurityVisitor`, `MetricsVisitor`,
  and `ValidatorVisitor` (and `EnhancedValidatorVisitor` transitively) through
  it, each keeping its own `visit_Redirect` action. Also collapsed an inline
  duplicate redirect loop in `ValidatorVisitor.visit_SimpleCommand`.
- `FormatterVisitor`/`DebugASTVisitor` were left alone (they render redirects,
  not recurse for analysis). Per the zero-behavior mandate, visitors that did
  not traverse redirects still don't — the hazard is closed for FUTURE code by
  giving everyone the shared correct helper, not by altering current output.
- LATENT BUG REPORTED (not fixed here, candidate for a separate behavior fix):
  `LinterVisitor` never analyzes redirect targets in the nodes it explicitly
  handles, so e.g. `$undefined` inside `cmd > $undefined.log` is invisible to
  the linter's variable checks.
- A 24-script redirect battery (`$(...)`, `${...}`, `2>&1`, glob targets,
  heredocs with `$var`, process-subs, fd dups, compound-command redirects)
  produced byte-identical output for every visitor.
- Full gate green: ruff + mypy clean (visitor package in scope), `run_tests.py
  --parallel` 6795 passed.

## 0.367.0 (2026-06-13) - Tier T2.6: formalize the pending-array-inits handoff
- REFACTOR (zero behavior change). Declaration builtins (`declare`/`typeset`/
  `local`/`export`/`readonly`) received array-initializer data from the executor
  via an ad-hoc shared-mutable attribute set with `getattr(shell,
  '_pending_array_inits', None)`. Replaced with a typed, single-owner API on
  `Shell`: `set_pending_array_inits()`, `pending_array_init(arg)` (non-consuming
  peek), `clear_pending_array_inits()`; the backing field is now declared and
  typed in `__init__` (`Optional[Dict[str, ArrayInitialization]]`).
- Lifetime invariant (documented + enforced at the one owner): the executor's
  `_run_command` installs the map immediately before the builtin and clears it
  in a `finally`; outside that window it is `None`. The peek is deliberately
  non-consuming to preserve the one nested re-read (`export NAME=(...)` delegates
  to `declare`, which reads the still-installed map). The set-if-non-None /
  clear-if-set guard is preserved, so an initializer-free command never picks up
  a stale map.
- A 14-case characterization (declare/typeset -a/-A, local-in-function, export,
  readonly, the B3 fidelity case `declare -a a=(${x}b "p""q")`, indexed/assoc
  `+=`, nested-function declarations, a partway-erroring declare, **no-stale-
  pickup** `declare -a noinit`) was byte-identical before/after.
- Full gate green: ruff + mypy clean (shell.py in scope), `run_tests.py
  --parallel` 6795 passed.

## 0.366.0 (2026-06-13) - Tier T2.5: unify glob-metacharacter detection
- REFACTOR (zero behavior change). The "does this string contain glob
  metacharacters" predicate was written inline `any(c in s for c in '*?[')` at
  7 sites (plus 2 per-char checks) across `glob.py` and `word_expander.py`.
  Collapsed to one source of truth in `psh/expansion/glob.py`:
  `GLOB_METACHARS = frozenset('*?[')` and `has_glob_metacharacters(s)`.
- No divergence: every site already used exactly `*?[` — the duplication was
  textual, not behavioral. The separate, already-centralized extglob predicate
  (`extglob.contains_extglob`) is untouched. Two visitor-layer sites are left
  as-is on purpose (a static-analysis visitor that shouldn't couple to the
  runtime expander, and a formatter that uses a different `*?[]` set for a
  quoting decision).
- A 24-word characterization harness (globs, bracket exprs, escaped/quoted,
  extglob `@()/?()/*()/+()/!()`, char classes, `**`, dotfiles) run through real
  globbing with extglob both off and on produced identical results before/after.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6795 passed.

## 0.365.0 (2026-06-13) - Tier T2.4: split environment.py (extract env builtin)
- REFACTOR (zero behavior change, registry-identical). The 671-line
  `psh/builtins/environment.py` held `export`, `set`, `unset`, and `env`. The
  `env` builtin — which carries its own fd-binding helpers (really an I/O
  concern) — moved to a new `psh/builtins/env_command.py` (208 lines) with
  `EnvBuiltin` + `_parse_invocation`, `_configure_child_export_attributes`,
  `_is_env_assignment`, `_print_environment`, `_bind_process_fds_to_streams`,
  `_restore_process_fds`. `environment.py` shrank to 483 lines (export/set/
  unset) with its now-unused imports trimmed.
- Wired `env_command` into `psh/builtins/__init__.py`'s import list so it
  self-registers. The registered-builtin name-set is byte-identical before and
  after (verified by registry dump diff), and a 7-case `env` characterization
  (`env`, `env FOO=bar`, `env FOO=bar cmd`, `env -i`, `env -u`, redirection to
  grandchild, no-leak) is identical.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6795 passed.

## 0.364.0 (2026-06-13) - Test isolation: per-test cwd for file `test`/`[` tests
- TEST FIX (no production change). `tests/unit/builtins/test_test_builtin.py`'s
  `TestFileTests` created fixed-name files/dirs (`testdir`, `regular.txt`, …) in
  the shared cwd and removed them by relative path. Under pytest-xdist these
  collided across workers (a `testdir` made by one test removed by another →
  intermittent `FileNotFoundError` on `os.rmdir`). Added an autouse
  `monkeypatch.chdir(tmp_path)` fixture giving each test its own working
  directory (CLAUDE.md parallel-safety rule 2). Verified stable under `-n 4`.

## 0.363.0 (2026-06-13) - Tier T2.3: split ast_nodes.py into a package
- REFACTOR (zero behavior change, zero import churn). The 766-line
  `psh/ast_nodes.py` became a package `psh/ast_nodes/` with cohesive
  submodules: `base.py` (ASTNode/Statement/Command bases), `redirects.py`,
  `words.py` (Word + expansion nodes), `arrays.py`, `commands.py`
  (SimpleCommand/Pipeline/AndOrList/StatementList/TopLevel), `tests.py`
  (`[[ ]]` nodes), `control.py` (loops/if/case/select/function def).
- `psh/ast_nodes/__init__.py` flat-re-exports every previously-public name
  (`__all__` parity verified by set-diff against the pre-split surface: 0 names
  lost), so every `from psh.ast_nodes import ...` / `from ..ast_nodes import`
  across the codebase is unchanged — NO other file touched its imports.
- Key subtlety: the coverage-matrix meta-test filters on
  `cls.__module__ == 'psh.ast_nodes'`. `__init__` runs `_reparent_to_package()`
  to rewrite `__module__` back to the package on every `ASTNode` subclass, so
  introspection (and `test_ast_coverage_matrix.py`) behaves identically.
- Updated the mypy scope entry `psh/ast_nodes.py` → `psh/ast_nodes` (mypy clean,
  85 files) and fixed stale `psh/ast_nodes.py` path references in 6 docs (forced
  by the `test_doc_pointers` meta-test).
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6794 passed.

## 0.362.0 (2026-06-13) - Tier T2.2: extract dense expansion helpers
- REFACTOR (zero behavior change, expansion hot path). Two dense regions in
  `psh/expansion/variable.py` lifted into named helpers:
  - `expand_parameter_direct`'s array branch → `_expand_array_parameter`
    returning `(handled, value)` (handled = whole-array `[@]`/`[*]` forms:
    count, slice, `@A`/`@Q`, conditional ops, per-element transforms; not
    handled = scalar element access that falls through to the shared
    `_apply_operator`). Parent body ~170 → ~90 lines; the array arm is now a
    6-line dispatch.
  - `expand_string_variables`'s escape loop → `_process_double_quote_escape`
    applying the `\\`, `\"`, `\$`, `` \` `` rules (incl. the unrecognized-escape
    fall-through) and returning `(piece, new_index)`. Parent body ~55 → ~25
    lines; the loop now reads as a clean three-way dispatch.
  - Special-char sets, the `\$`-shields-expansion check, IFS join behavior, and
    all early-return semantics are byte-identical.
- A 60-case characterization battery (array `[@]`/`[*]` quoted/unquoted,
  arith-index, `${#a[@]}`, `${!a[@]}` keys, sparse, associative, slices,
  per-element transforms, custom-IFS; plus the full escape set) matched the
  pre-refactor golden baseline AND real bash exactly.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6794 passed.

## 0.361.0 (2026-06-13) - Tier T2.1: decompose _execute_command
- REFACTOR (zero behavior change). `CommandExecutor._execute_command`
  (`psh/executor/command.py`) was a ~140-line method conflating two
  responsibilities. Split into a thin coordinator plus two focused methods:
  - `_execute_command` (~45 lines) — per-command preamble (DEBUG trap, array
    assignments, `assignments.extract`, the `last_cmdsub_status = None` reset
    that must precede expansion), pure-vs-command decision, and the single
    shared `try/except → _handle_execution_error`.
  - `_run_pure_assignment` (~12 lines) — the no-command-word path
    (`assignments.apply_pure`).
  - `_run_command` (~110 lines) — the command-word path: word expansion,
    redirect-only/words-vanish edges, prefix apply + `set -e` abort, xtrace,
    `exec` special case, array-init delivery, strategy dispatch, restore.
  - `last_cmdsub_status` reset, `_pending_array_inits` lifetime, `is_special`/
    `saved_vars` restore, and deferred-pure-on-words-vanish are all preserved
    exactly.
- A 36-case characterization harness (pure scalar/multi/chain/array/assoc/
  cmdsub-status/readonly/append; prefix external/builtin/function/special-
  persist/temp/chain; normal builtin/external/function/127/alias; empty/
  redirect-only/words-vanish; exec-assign; xtrace; set-e) matched the
  pre-refactor golden baseline byte-for-byte.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6794 passed.

## 0.360.0 (2026-06-13) - Tier T1.6: builtin output via base-class helpers + guard
- CONSISTENCY/HARDENING (zero behavior change, verified). Builtins that wrote
  output with raw `print(..., file=shell.stdout/stderr)` now use the base-class
  helpers (`self.write_line` for stdout, `self.write_error_line`/`self.error`
  for stderr), which are forked-child-aware (`os.write` in a child) and honor
  the flush discipline. Migrated `navigation.py` (cd CDPATH + `cd -` echo),
  `positional.py` (getopts errors), `shell_options.py` (shopt), `parse_tree.py`,
  `parser_control.py`, and `io.py` (echo debug-exec diagnostics).
- A bash-differential harness (`cd -`, CDPATH `cd`, `pwd`, getopts errors —
  standalone and in pipelines/redirects) confirmed byte-identical output before
  and after: `shell.stdout/stderr` were already redirect-aware, so this is a
  pure readability/consistency migration to the v0.284 error-channel convention.
- Added `tests/unit/builtins/test_no_raw_print.py`: a source-grep guard
  (parametrized over every `psh/builtins/*.py` except the sanctioned `base.py`)
  that fails on any new raw `print(..., file=...std...)` — so future builtins
  can't reintroduce output that may not honor fd-level redirection.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6794 passed.

## 0.359.0 (2026-06-13) - Tier T1.5: tooling honesty for the disabled CI workflow
- TOOLING (no code change). `.github/workflows/tests.yml` still declared
  `on: push/pull_request: [main]` while the workflow has been disabled
  (`disabled_manually`) in favor of the local gate — so the in-tree file
  misrepresented how the project is tested. Changed the triggers to
  `workflow_dispatch` only (the push/PR block is commented out, not active)
  and added a header comment explaining the local-gate policy and exactly how
  to restore per-PR CI (uncomment + `gh workflow enable tests.yml`). The
  nightly safety net and the auto-tagger are unaffected.

## 0.358.0 (2026-06-13) - Tier T1.4: unify expansion-delimiter stripping
- REFACTOR (zero behavior change, both parser backends). Three sites peeled
  the delimiters off an expansion's source text with their own inline
  strip-and-fallback blocks: `WordBuilder.parse_expansion_token`,
  `WordBuilder._parse_token_part_expansion`, and the combinator's
  `ExpansionParsers.build_word_from_token`. They now share four pure helpers
  in `word_builder.py`: `strip_command_sub` (`$(`…`)`), `strip_backtick`,
  `strip_arithmetic` (`$((`…`))`), `strip_process_sub` (`<(`/`>(`…`)`).
- Real divergences were found and PRESERVED, not silently unified: the
  combinator keeps its post-strip `_validate_command_substitution` check
  (recursive-descent has none); only the delimiter strip itself is shared.
  `$[...]` arithmetic and the combinator's standalone process-sub parser were
  confirmed out of scope and left untouched.
- A 29-input dual-backend characterization harness (nested cmd subs, backticks,
  `${...}` with `:-`/`[@]`/`##`/nesting, arithmetic, simple/special vars, mixed
  adjacency, quoted composites, process subs) dumped byte-identical ASTs under
  both `--parser rd` and `--parser combinator` before and after.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6760 passed.

## 0.357.0 (2026-06-13) - Tier T1.2: extract the redirection-mode policy
- REFACTOR (zero behavior change). `CommandExecutor._execute_with_strategy`
  (`psh/executor/command.py`) chose how to apply a matched command's
  redirections via inline nested `if/elif/else`. That decision is now a named
  `RedirectionMode` enum decided in one place (`_decide_redirection_mode`) and
  dispatched in one place, with each mode documented:
  - `BUILTIN_INPROCESS` — builtin not in a pipeline/forked child: Python-stream
    save/restore around the one command (does not persist).
  - `EXTERNAL_DEFERRED` — external command: redirections applied in the forked
    child only (applying them in the parent too would resolve `2>&1` against
    already-redirected fds and run heredoc/cmdsub twice).
  - `FD_LEVEL_WINDOW` — functions, aliases, and builtins in a pipeline/forked
    child: fd-level `os.dup2` save/restore window.
- The conditions are byte-for-byte the same booleans that were inline. A
  34-case characterization harness (builtin/special/external/function/alias
  redirects, pipeline members, background, heredocs/here-strings, persist-vs-
  restore, bad-fd/unwritable/missing-file errors) matched the pre-refactor
  golden baseline exactly.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6760 passed.

## 0.356.0 (2026-06-13) - Tier T1.1: grow mypy checked scope (21 → 78 files)
- TYPE-CHECKING SCOPE (textbook lever, zero behavior change). Expanded the
  mypy `files` list in `pyproject.toml` from ~21 to **78 source files**, all
  100% clean under the existing non-strict config. Added whole packages
  `psh/scripting` and `psh/visitor`, most of `psh/expansion` (15 modules),
  `psh/utils` (8 modules), and 14 more `psh/interactive` modules.
- Real type-bug fixes surfaced by the wider scope (all behavior-preserving):
  - `keybindings.py`: base `KeyBindings.bindings`/`get_action` were typed
    `Callable` but actually hold action-name **strings** (the subclass was
    already correct) — base annotation was simply wrong.
  - `security_visitor.py`: `Dict[str, any]` used the builtin `any` as a type →
    `typing.Any`.
  - `debug_ast_visitor.py`: `_visit_children(List[ASTNode])` rejected
    `list[Statement]` (List invariance) → `Sequence[ASTNode]`.
  - `shebang_handler.py`, `command_accumulator.py`: corrected `Optional`
    interpreter/AST types that allowed `None` to flow into `str`/`ASTNode` uses.
- Remaining annotation additions are container/`Optional` narrowing only.
  Deferred as too-noisy-for-a-minimal-pass: `expansion/{arrays,fields,operands,
  operators}.py` (mixin self-type plumbing), `interactive/line_editor.py`,
  `utils/signal_utils.py` — recorded for a future increment.
- Full gate green: `mypy` clean (78 files), `ruff check psh tests` clean,
  `run_tests.py --parallel` 6760 passed / 228 skipped / 19 xfailed.

## 0.355.0 (2026-06-13) - Docs: ground-up reappraisal #5 (textbook-grade scorecard)
- DOCS ONLY (no code change). Added
  `docs/reviews/ground_up_reappraisal_5_2026-06-13.md`: a fresh five-cluster
  scorecard graded against a strict textbook rubric (small/readable, single
  source of truth, narrow interfaces, invariants enforced, behavior proven).
- Scorecard: Expansion A−; Interactive/Scripting/Visitor/Tooling A−;
  Lexer/Parser/AST B+; Executor/io_redirect B+; Core/Builtins B+. Overall
  "B+/A− — production-minded, approaching textbook" (7,007 tests green).
- Defines the prioritized path to the textbook grade: Tier T1 (grow mypy
  scope, extract inline policies into tables/objects, unify small duplication
  clusters), Tier T2 (decompose the dense hubs), Tier T3 (finish the model).

## 0.354.0 (2026-06-13) - Behavior fix: explicit input fd for external commands
- BUG FIX (bash-verified; redirection/IO architecture review, Ugly 2): an
  explicit input-fd redirect (`cmd 5<file`) did not reach the named fd for
  external commands. `python3 -c 'os.read(5,...)' 5<file` raised
  `OSError: [Errno 9] Bad file descriptor` in psh; bash delivers fd 5.
- ROOT CAUSE: `_redirect_input_from_file(target, redirect=None)` already
  honored an explicit fd, and the parent (`exec`) path passed the redirect —
  but the forked-child path (`setup_child_redirections`) and the builtin
  stdin path called it with only `target`, defaulting to fd 0. The child
  `<` branch and the builtin `<` branch now pass `redirect` through, so
  `N<file` opens on fd N across all paths (output `N>file` already worked).
- 5 bash differential probes match (external read of fd 5/6, plain `<`,
  `0<` == `<`, `exec 6<`); +4 conformance tests
  (`tests/conformance/bash/test_explicit_input_fd_conformance.py`). Full
  suite green (6,760). ruff + mypy clean. Updated the `io_redirect/CLAUDE.md`
  helper-table signature.

## 0.353.0 (2026-06-13) - Behavior fix: fd-prefixed heredocs and here-strings
- BUG FIX (bash-verified; from the redirection/IO architecture review): an
  explicit file-descriptor prefix on a heredoc or here-string failed to PARSE.
  `cat 0<<EOF`, `cat 1<<EOF`, `cat 5<<EOF`, `cat 0<<-EOF`, `cat 0<<<word`,
  `cat 5<<<word` all raised `Parse error ... Expected file name`; bash accepts
  them. Now they parse and the body is materialized on the named fd.
- ROOT CAUSE: the lexer's operator recognizer attached numeric fd prefixes to
  `N>`/`N>>`/`N<`/`N<>` etc. but not to the heredoc/here-string operators
  `<<`/`<<-`/`<<<`, so `0<<` never formed a heredoc token and the parser fell
  through to the generic file-redirect branch. Fixed in
  `psh/lexer/recognizers/operator.py` (the fd-prefix matcher now includes
  `<<<`/`<<-`/`<<`, ordered longest-first so `5<<<` isn't split into `5<` `<<`);
  the parser already carried `token.fd`.
- Also fixes the heredoc/here-string MATERIALIZATION hardcoding fd 0
  (redirection review Ugly 2): `psh/io_redirect/file_redirect.py` /
  `manager.py` now honor `redirect.fd` (default 0) across the parent-fd,
  builtin-stream, and forked-child paths, so `5<<EOF` puts the body on fd 5.
- 19/19 bash differential probes match (fd0 == no-prefix, tab-strip `0<<-`,
  quoted delimiters, expansion, pipelines, multi-digit fd, `read` on fd5,
  `exec 5<<<word`). +21 tests (a `tests/conformance/bash/` suite + lexer unit
  tests). Full suite green (6,756). ruff + mypy clean. Zero change to plain
  (non-fd-prefixed) heredocs/here-strings.

## 0.352.0 (2026-06-13) - Test hygiene: arithmetic characterization fixtures
- TEST ONLY (no production change): the arithmetic characterization fixtures
  (`sh`, `assoc_sh` in `tests/unit/expansion/test_arithmetic_characterization.py`)
  constructed a bare `Shell()` and returned it with no teardown, leaking the
  shell's signal-notifier pipe FDs across the suite (flagged by the
  2026-06-13 expansion architecture review). They now build on the shared
  conftest `shell` fixture, whose `_cleanup_shell` teardown reaps jobs and
  closes those FDs. Dropped the now-unused `Shell` import. Full suite green
  (6,735); ruff + mypy clean.

## 0.351.0 (2026-06-13) - Prune docs/archive
- DOCS ONLY (no code change): removed 298 stale development-history files from
  `docs/archive/` — completed implementation plans, phase summaries, and
  point-in-time analyses accumulated through the project's development, with no
  live references from code, tests, or current docs. All are recoverable from
  git history.
- KEPT `docs/archive/CHANGELOG_history.md` (the pre-v0.200.0 version history),
  which `CHANGELOG.md` references live; the `pyproject.toml` ruff
  `extend-exclude = ["docs/archive"]` remains valid (still covers it).
- Verified: `ruff check .` passes, the doc-pointer and README-statistics
  meta-tests pass, the full suite is green (6,735), and the CHANGELOG pointer
  still resolves.

## 0.350.0 (2026-06-13) - Docs sync after reappraisal #4
- DOCS ONLY (no code change): brought the architecture/CLAUDE docs current
  after the reappraisal #4 program.
  - Root `CLAUDE.md` release workflow: GitHub's per-PR `tests.yml` is disabled;
    the **local** `run_tests.py --parallel` (+ ruff + mypy) is THE gate; merge
    immediately (no CI wait); `release-tag.yml` auto-creates the `vX.Y.Z` tag
    on a `psh/version.py` bump (no manual `git tag`).
  - Root `CLAUDE.md` Known Test Issues: documented that `strict-errors` is
    enabled suite-wide via `conftest.py` (`PSH_STRICT_ERRORS=1`) — a test
    hitting a genuine internal defect now fails loudly; a deliberate-defect
    test must disable it locally.
  - `psh/core/CLAUDE.md`: added `FunctionDefinitionError` to the `PshError`
    member list and documented the expected-error taxonomy
    (`report_internal_defect`: `PshError ∪ OSError ∪ SyntaxError` = expected;
    everything else = internal defect) and the `strict-errors` mechanism.
  - `README.md`: corrected the registered-builtin count (60 → 61; the
    enumerated list was already complete).
- Verified: the doc-pointer and README-statistics meta-tests pass; every
  symbol referenced in the new docs exists.

## 0.349.0 (2026-06-13) - Reappraisal #4 Tier C-B3: unified array-init path (+behavior fixes)
- REFACTOR + BEHAVIOR FIX (review Ugly 6): psh had TWO array-initialization
  implementations — the structured `ArrayInitialization`/`ARRAY_INIT_ELEMENT`
  path for bare `a=(...)`, and a separate serialize-then-`shlex`-reparse for
  declaration builtins (`declare`/`typeset`/`local`/`export`/`readonly`). They
  are now UNIFIED: declaration array-init flows through the same structured
  expansion via shared `ArrayOperationExecutor.build_indexed_array` /
  `build_associative_array` helpers (one implementation, used by both paths).
  The parser attaches the structured `ArrayInitialization` to the argument
  (`Word.array_init`); the executor hands it to the declaration builtin through
  a scoped `shell._pending_array_inits` (set/cleared around the single call,
  mirroring the `exec` node-passing precedent). The string-reparse module
  `psh/builtins/array_init.py` (132 lines) is DELETED — no real entry point
  needs it (`eval` re-parses to a structured init; dynamic `declare $x`
  word-splits and never array-ifies, like bash).
- This FIXES 9 bash divergences the old reparse got wrong (each bash-verified):
  adjacent-quote `declare -a a=("x""y")` → `xy` (was split); indexed `+=`
  append; associative `+=` append; bare assoc key/value pairs
  `declare -A m=(k1 v1 …)`; explicit indices `declare -a a=([2]=x [0]=y)`;
  tilde and command-substitution elements; `export e=(a b)` (now an indexed
  array with the export attribute, not a scalar string; arrays aren't exported
  to the env); and the WRONG array-ification of dynamic scalars (`declare
  a=$x` with `x='(1 2)'` is now a scalar, like bash). Also fixed `declare -a
  a+=(…)` parsing (the lexer splits `a+=` → `a` `+=`, previously misparsed).
- Also fixes the `+=` arg detection in `_check_array_initialization`.
- SAFETY NET: a value-based declaration-array conformance suite (17 cases via
  `declare -p`) + reworked legacy tests, all bash-verified; the bare-array
  path characterization is unchanged. Full suite green (6,735 passed). ruff +
  mypy clean. Docs updated (`ast_data_flow.md`, `builtins/CLAUDE.md`).
- PRE-EXISTING divergences confirmed UNCHANGED (present on main too, not
  regressions): unquoted assoc key containing a space (`[a b]=v`) reads empty
  (quoted `["a b"]=v` works); `declare -p` assoc display ordering; `declare -i`
  not applied to array elements.
- The token-payload rewrite (review Ugly 2/10, "E1") proved UNNECESSARY: the
  element Words already carry sufficient fidelity for the structured path, so
  B3 needed none of it. E1 remains unscheduled.

## 0.348.0 (2026-06-13) - Reappraisal #4 Tier C-D2: test operands in the Word model
- REFACTOR (zero behavior change, review Ugly 11): `[[ ]]`
  `BinaryTestExpression` stored operands as plain strings plus
  `left_quote_type`/`right_quote_type` side-channels — the last parser
  expression not using the `Word` model. Operands are now `left_word: Word` /
  `right_word: Word`:
  - `left_quote_type` DELETED (was dead — set by the parser, read nowhere).
  - `right_quote_type` is now a derived `@property` from `right_word.is_quoted`
    (it drives literal-vs-glob for `==`/`!=` and literal-vs-regex for `=~`);
    `is_quoted` reproduces the old stored boolean for every operand shape.
  - `.left`/`.right` retained as derived `display_text()` properties so
    formatter/debug consumers are unchanged.
  Both parser backends build operand Words; the evaluator expands the Words and
  reads `right_word.is_quoted`. `UnaryTestExpression` deliberately left as-is
  (no quote side-channel to remove; migrating it adds risk with no cleanup).
- SAFETY NET: a 37-case characterization
  (`tests/integration/test_enhanced_test_word_operands.py`) over every operator
  and quoting shape (glob/literal `==`, literal/regex `=~`, BASH_REMATCH
  capture, numeric, `-z`/`-f`, tilde, empty) plus the `is_quoted == old
  right_quote_type` equivalence — green before/after. 17 bash differential
  probes match. Full suite green (6,718 passed). ruff + mypy clean.
- PINNED (pre-existing, not fixed): a mixed-quote LHS pattern like `a"b"*`
  collapses to literal text with no per-part quote context (the old
  single-quote-type model was already lossy here); preserved exactly.

## 0.347.0 (2026-06-13) - Reappraisal #4 Tier C-D1: quote context in parts only
- REFACTOR (zero behavior change, review Ugly 3): `Word` stored a whole-word
  `quote_type` field that duplicated the per-part `quoted`/`quote_char` state.
  `Word.quote_type` is now a derived `@property` — a word is wholly quoted iff
  all its parts are quoted with the same quote char, which then is the type.
  `is_quoted`, `is_unquoted_literal`, and `effective_quote_char` now derive
  purely from parts. The Word construction sites (`from_string`, `word_builder`,
  the control-structure/loop parsers in both parser backends, `command.py`)
  drop the now-redundant `quote_type=` argument since the parts already carry
  the quote.
- SAFETY NET: a 128-case quote-derivation characterization
  (`tests/unit/parser/test_word_quote_derivation.py`, both parser backends)
  asserting the derived quote properties — green before/after. Characterization
  surfaced THREE shapes where the OLD stored `quote_type` disagreed with the
  parts (adjacent same-quote composites `"a""b"`, quoted case patterns, and a
  combinator `'mixed'` sentinel); all are verified behavior-neutral against
  bash AND pristine main (uniformly-quoted words expand identically through the
  whole-word vs composite dispatch branches; case patterns match via per-part
  quote context, never `quote_type`). Full suite green (6,681 passed); 12 bash
  quoting probes match. ruff + mypy clean.

## 0.346.0 (2026-06-13) - Reappraisal #4 Tier C-C3: operator-debris recognizer
- REFACTOR (zero behavior change, review Ugly 9): the lexer's step-4
  `_handle_fallback_word` — which collected operator-debris words (those
  starting with `]`, `+`, `=`, `[`, the only four classes a census found
  reach it) using a looser terminator set than the literal recognizer — is now
  a registered `OperatorDebrisWordRecognizer` (`recognizers/operator_debris.py`)
  at lowest priority (10), tried strictly last. The `tokenize()` loop no longer
  has a special fallback step: it is whitespace → quotes/expansions →
  recognizers (debris last) → fail-loud RuntimeError. These word forms are now
  honestly modeled as a grammar recognizer with an explicit `can_recognize`
  domain, not a fallback accident.
- SAFETY NET: a frozen token-stream characterization
  (`tests/unit/lexer/test_operator_debris_recognizer.py`, 20 tests) over every
  census case (`[ x = y ]`, `a=([1]=x z)`, `a]b`, `vars+=(x)`, `set +x`,
  `([a-z]+)`, `a=b=c`, `[0-9]*)`, …) plus "not stolen from operator/literal"
  pins (`[[ -f x ]]`) — byte-identical before/after (types, offsets,
  adjacency). 5 bash probes match. Full suite green (6,553 passed). ruff +
  mypy clean. CLAUDE.md flow/priority docs updated.

## 0.345.0 (2026-06-13) - Reappraisal #4 Tier C-C2: command-position drift-lock
- ASSESSMENT (review Ugly 8): the review recommended extracting one shared
  `CommandPositionMachine` for the three machines that track command position
  (lexer pass, keyword normalizer, cmdsub scanner). On inspection the codebase
  ALREADY realizes that intent better: `psh/lexer/command_position.py` is the
  single shared vocabulary all three consult, with a docstring explaining why
  their alphabets MUST differ (they run at different pipeline stages — raw
  text vs token types vs token stream). Forcing a unified state machine would
  add risk and contradict that design, so it is intentionally NOT extracted.
- TEST + DOC ONLY (no production logic change): added
  `tests/unit/lexer/test_command_position_consistency.py` (11 tests) locking
  the documented relationships so the vocabulary can't silently drift —
  keyword-valued set entries are real `KEYWORDS`; the documented asymmetries
  hold (openers set lexer command-position but closers are omitted;
  `RESET_TO_COMMAND_POSITION` types map to the intermediate+closer keywords);
  plus end-to-end keyword-recognition coverage (`then case …` recognizes
  `case`; `echo case` keeps it a WORD). Updated the `command_position.py`
  docstring to point at this guard. Full suite green (6,530 passed).

## 0.344.0 (2026-06-13) - Reappraisal #4 Tier C-C1: typed cmdsub scanner state
- REFACTOR (zero behavior change, review Ugly 7): `psh/lexer/cmdsub_scanner.py`
  tracked its `case`-statement scanning with 6 string phase constants and
  `[state, pattern_paren_depth]` lists. These are now a `CasePhase` enum and a
  `CaseScanState` dataclass (`case_stack: List[CaseScanState]`); all 24
  `top[0]`/`top[1]` access sites updated, transition logic byte-for-byte
  identical.
- NEW TEST (`tests/unit/lexer/test_cmdsub_scanner_vs_parser.py`, 61-body
  corpus + per-body double assertion): the scanner's chosen `$()` extent
  agrees with what the real parser accepts, and the lexer's COMMAND_SUB token
  spans exactly that extent. Covers nested subs, all quote forms, comments,
  heredocs, arithmetic, `case` in every form, `;;`/`;&`/`;;&`, compositions.
- The 103-case frozen scanner characterization harness stays byte-identical;
  6 bash probes match. Full suite green (6,519 passed). ruff + mypy clean.

## 0.343.0 (2026-06-13) - Reappraisal #4 Tier C-B2: array-assignment normalization
- REFACTOR (zero behavior change, review Ugly 5): `ArrayParser`
  (`psh/parser/recursive_descent/parsers/arrays.py`) detected/parsed array
  assignments by branching inline on ~6 raw tokenisation shapes. A 3,000+
  input fuzz census against the real `ModularLexer` established which shapes
  are actually reachable:
  - DELETED the dead "old-lexer" pattern (a bare name immediately followed by
    an `LBRACKET` token) — 0 of 3,240 inputs reach it; the current lexer never
    produces it.
  - NORMALIZED the live shapes behind a single `_normalize_assignment_head()
    -> AssignmentCandidate` seam; `is_array_assignment()` is now just
    `_normalize_assignment_head() is not None` (peek-only) and
    `parse_array_assignment()` dispatches on the candidate instead of
    re-inspecting raw tokens. Token-shape variance lives in ONE place.
- SAFETY NET: a 46-entry frozen AST characterization corpus
  (`tests/unit/parser/test_array_assignment_characterization.py` + sidecar
  JSON) — frozen from the original parser, byte-identical after. 12 bash
  differential probes match. A1 invariants hold. Full suite green
  (6,397 passed). ruff + mypy clean.
- PINNED (pre-existing, reported, not changed): the space-separated forms
  `a [ 0 ] = v` and `a[0] =v` / `a = (...)` diverge from bash (psh parse
  error / element-or-init vs bash command-not-found); preserved exactly.

## 0.342.0 (2026-06-13) - Reappraisal #4 Tier C-B1: Word text-method discipline
- REFACTOR (zero behavior change, review Ugly 4): `Word` now exposes explicit,
  named text methods instead of forcing callers to bypass `__str__`:
  - `source_text()` — flattened parts re-wrapped in the word's quote chars
    (the old `__str__` behavior; for debug/source rendering).
  - `display_text()` — flattened pre-expansion text, no whole-word re-wrap
    (what `''.join(str(p) for p in word.parts)` used to spell out).
  - `to_literal_string()` — unchanged (quote-removed literal).
  `__str__` now delegates to `source_text()` and is documented as
  debug/source-only.
- The 9 semantic `''.join(str(p) for p in word.parts)` call sites (array,
  control-structure, and redirection parsers + the combinator special-command
  parser) and the `SimpleCommand.args` derivation now call `display_text()`,
  so the flattening rule has ONE definition. Values byte-identical.
- New `Word`-method unit tests; full suite green (6,350 passed). ruff + mypy
  clean.

## 0.341.0 (2026-06-13) - Reappraisal #4 Tier C-A2: AST sidecar cleanup
- REFACTOR (zero behavior change): removes the parallel STORED quote/type
  sidecar fields that let an AST node hold two truths at once (review Ugly 1).
  - DELETED dead `ForLoop.item_quote_types` / `SelectLoop.item_quote_types`
    (zero readers anywhere) and their population in both parsers.
  - DERIVED, no longer stored: `ArrayInitialization.element_types` /
    `element_quote_types` and `ArrayElementAssignment.value_type` /
    `value_quote_type` are now `@property` computed from the canonical `Word`s,
    reproducing the parser's prior mapping exactly. Population removed from
    both the recursive-descent and combinator parsers. The only consumers
    (`formatter_visitor`, `validator_visitor`) are unchanged.
  - NON-OPTIONAL canonical fields: `ArrayElementAssignment.value_word: Word`
    (now required) and `ForLoop`/`SelectLoop.item_words: List[Word]`
    (default `[]`); the now-unreachable `value_word is None` guard in
    `executor/array.py` was removed (construction enforces it).
- SAFETY NET: a formatter/validator round-trip characterization
  (`tests/unit/visitor/test_formatter_array_roundtrip_characterization.py`,
  40 cases over both parsers) — green before and after, byte-identical on the
  production recursive-descent parser. A1 invariants still hold. User-visible
  array/loop output matches bash. Full suite green (6,346 passed). −33 net
  production lines. ruff + mypy clean.
- One pinned divergence: for `a=(p$x q)` the combinator parser (educational-
  only) previously emitted a spurious "mixed element types" validator info
  from tokenization artifacts; deriving from the (already-split) Words removes
  it. The production parser is byte-identical.

## 0.340.0 (2026-06-13) - Reappraisal #4 Tier C-A1: AST canonical invariant lock-down
- TESTS ONLY (no production change): a safety net for the upcoming AST field
  cleanup (Tier C-A2). New `tests/unit/parser/test_ast_canonical_invariants.py`
  (39 tests, 28-snippet corpus) parses representative scripts through the
  production recursive-descent parser and asserts every node carries its
  canonical `Word`-based fields, even when nested: `SimpleCommand.words` (with
  `args` derived from `words`), `ArrayInitialization.words`,
  `ArrayElementAssignment.value_word` (non-None), `ForLoop`/`SelectLoop.
  item_words` (non-None, consistent with `items`), and `CasePattern.word`.
- New `tests/unit/parser/test_legacy_field_isolation.py`: a static meta-test
  proving the executor and expansion packages never read the legacy quote/type
  sidecar fields (`element_types`, `element_quote_types`, `value_type`,
  `value_quote_type`, `item_quote_types`) — confirming the runtime path is
  already Word-only, so deleting/deriving those fields is safe.
- Findings (documented, not changed): `for x; do` (no `in`) is normalized by
  the parser to `for x in "$@"`, so every `ForLoop` has populated
  `item_words`; `for ((...))` is a distinct `CStyleForLoop` node. All
  invariants hold for current parser output. Full suite green (6,307 passed).
- DOCS: refreshed README Project Statistics (drifted >10%); recorded the
  lexer/parser/AST elegance plan as `docs/reviews/reappraisal_4_tier_c_lexer_parser.md`.

## 0.339.0 (2026-06-13) - Expected-error taxonomy; strict-errors enabled suite-wide
- TAXONOMY (B2-R2): the last-resort guard helper `report_internal_defect`
  (`psh/core/internal_errors.py`) now distinguishes EXPECTED shell errors from
  INTERNAL DEFECTS. Expected = `PshError ∪ OSError ∪ SyntaxError` (covers
  redirection failures, fork failures, lexer/parse errors, and arithmetic
  errors); these are handled normally (message + exit code) even under
  `strict-errors`. Only genuine Python-bug exceptions (`RuntimeError`,
  `AttributeError`, `TypeError`, `KeyError`, plain `ValueError`, …) are
  re-raised under strict.
- The function-name validation errors in `psh/core/functions.py` (reserved
  word / invalid name / readonly function) were mistyped as bare `ValueError`
  (a defect signal); they are now `FunctionDefinitionError(PshError)` with the
  exact same messages — so they classify as expected shell errors.
- PAYOFF: `strict-errors` is now ENABLED SUITE-WIDE — `conftest.py` sets
  `PSH_STRICT_ERRORS=1` for both in-process shells and subprocess `python -m
  psh`. A genuine internal defect (an unexpected Python exception) now fails
  the test suite loudly instead of being masked as exit-1; expected shell
  errors pass through unchanged. This completes the strict-errors program
  begun in v0.331.0 (B2).
- ZERO behavior change in non-strict mode (byte-identical messages/exit codes
  for the representative error paths, verified before/after). Full suite green
  with strict on (6,268 passed). Added taxonomy unit tests
  (PshError/OSError/SyntaxError pass through; RuntimeError/AttributeError/…
  re-raise). ruff + mypy clean.

## 0.338.0 (2026-06-13) - Behavior fix: $0 inside a function
- BUG FIX (bash-verified): `$0` inside a function now stays the script/shell
  name, instead of becoming the function name. Run by path,
  `f(){ echo "$0"; }; f` reports the script path in psh exactly as in bash;
  `${FUNCNAME[0]}` remains the function name. Previously psh reported the
  function name for `$0`.
- ROOT CAUSE: the function executor (`psh/executor/function.py`) mutated
  `state.script_name = name` on entry "for $0" (and restored it on exit).
  bash does not change `$0` on function entry — removed the mutation. The
  function name still lives on `function_stack` (drives `${FUNCNAME[@]}` and
  local-scoping), so nothing else changed.
- CLEANUP: with `$0` no longer function-aware, `_expand_special_variable`
  (`expansion/variable.py`) now delegates `$0` to
  `ShellState.get_special_variable` along with the other raw special vars —
  completing the B6 (v0.335.0) single-source consolidation.
- A script-file differential conformance test
  (`tests/conformance/bash/test_dollar_zero_conformance.py`) pins the
  behavior against real bash; the B6 characterization cases that pinned the
  old function-name behavior were corrected. Full suite green (6,262 passed).
  ruff + mypy clean.

## 0.337.0 (2026-06-13) - Behavior fix: associative arrays in arithmetic
- BUG FIX (bash-verified): associative-array elements now resolve inside
  arithmetic `$(( ))` / `(( ))`. Previously `declare -A m; m[k]=9; echo
  $(( m[k] ))` gave `0`; now `9`. Covers reads, expressions, compound
  assignment (`(( m[k] += 5 ))`), and new-key assignment (`(( m[new]=5 ))`).
- The subscript semantics match bash: for an ASSOCIATIVE array the subscript
  is the LITERAL key text (not arithmetic-evaluated) — `m[a]` with `a=k` reads
  key `a`, and `m[i]` reads key `i` — while INDEXED arrays still
  arithmetic-evaluate the subscript (`a[1+1]`). Implemented by threading the
  `$`-expanded source into `ArithParser`, storing the raw subscript text on
  `ArrayElementNode`/`ArrayAssignmentNode`, and deciding key type in the
  evaluator by the array's kind.
- Also fixes the related gap (found while probing): array-element pre/post
  increment/decrement `a[0]++`, `m[x]++`, `++a[i]` for BOTH indexed and
  associative arrays (previously a parse error).
- +21 bash-verified tests (arithmetic characterization assoc section + array
  increment cases) and 9 `golden_cases.yaml` rows. Full suite green
  (6,262 passed). ruff + mypy clean.
- KNOWN remaining gap (pre-existing tokenizer limitation, out of scope):
  associative keys containing spaces (`m[ab cd]`) still error in arithmetic.

## 0.336.0 (2026-06-13) - Reappraisal #4 Tier B7: process failure-path tests (TIER B COMPLETE)
- TESTS ONLY (no production change): 24 deterministic, parallel-safe tests
  for the process-creation / pipeline error paths the 2026-06-13 assessment
  flagged as undertested:
  - **fork failure** — inject `OSError(EAGAIN)` into `fork_with_signal_window`
    for single-command and pipeline launches; assert graceful error, nonzero
    exit, parent signal mask restored, shell survives (extends
    `test_fork_sigmask_restore.py`).
  - **redirect failure** — output/input/permission cases: nonzero exit, the
    command body does NOT run, error on stderr, and the shell's fds are
    restored (a following command writes correctly). Permanent-fd cases run
    psh in a subprocess. Exit codes matched to bash.
  - **signal-killed exit status** — child signals itself (no race): SIGINT→130,
    SIGTERM→143, SIGKILL→137, pipeline SIGPIPE→141; all matched to bash.
  - **stopped jobs** — a PTY test that `jobs` lists a Ctrl-Z'd job as Stopped.
  - **process-sub cleanup** — 20-iteration loop proving no `/dev/fd` leak and
    no zombie accumulation; write-side `>(...)` child reaped.
  - All paths behaved correctly (matched bash on every exit code and the
    body-skipped / fds-restored guarantees). The only divergence is cosmetic
    (Python-errno vs bash redirect-error wording); tests assert non-empty
    stderr rather than pinning it.
- This release COMPLETES reappraisal #4 Tier B (v0.329.0–v0.336.0): tooling
  honesty, CI health, strict internal-error mode, and the four
  decomposition/consolidation refactors (cmdsub scanner, arithmetic package,
  WordExpander segment-IR, single-authority state) — each zero-behavior-change
  and guarded by a frozen characterization harness. Full suite green
  (6,241 passed). See `docs/reviews/reappraisal_4_tier_b.md`.

## 0.335.0 (2026-06-13) - Reappraisal #4 Tier B6: single-authority state
- REFACTOR (zero behavior change), two halves:
  - **Forked-child flag**: removed the vestigial
    `ExecutionContext.in_forked_child` (dataclass field + `fork_context()` /
    `pipeline_context_enter()` constructors). Its only references were a
    `debug-exec` print and a stale comment in `executor/strategies.py`; every
    real reader (builtins, `command.py`) and writer (`child_policy.py`,
    `subshell.py`) uses `ShellState.in_forked_child`, now the sole authority.
    The strategies.py debug print/comment were corrected to name
    `shell.state.in_forked_child`.
  - **Special-variable lookup**: `_expand_special_variable` in
    `expansion/variable.py` re-implemented raw values that already lived in
    `ShellState.get_special_variable`. The 7 byte-identical raw lookups
    (`$?`, `$$`, `$!`, `$#`, `$-`, `$@`, `$*`) now delegate to that single
    source. The expander-only layering stays in the expander: `$0`
    (function-aware), digit positionals, and the `nounset` checks. (`$*`'s
    IFS join was traced to confirm both paths use `state.ifs_star_separator`
    before delegating.)
- SAFETY NET: a 49-case characterization harness
  (`tests/unit/expansion/test_special_var_lookup_characterization.py`) over
  every special var across contexts (incl. `$*` under varied IFS, `$0` inside
  nested functions, `nounset` digit out-of-range, and a forked-builtin
  fd-level-I/O sanity class) — green before and after. Full suite green
  (6,217 passed). ruff + mypy clean.
- PRE-EXISTING divergence confirmed and preserved (recorded for a future
  behavior release in `docs/reviews/reappraisal_4_tier_b.md`): `$0` inside a
  function returns the function name in psh vs the shell name in bash.

## 0.334.0 (2026-06-13) - Reappraisal #4 Tier B5: WordExpander segment-IR
- REFACTOR (zero behavior change): the word-expansion engine
  (`psh/expansion/word_expander.py`) accumulated each part onto a mutable
  `_WalkState` using a parallel `result_parts: List[str]` + `splittable_idx:
  Set[int]` plus scattered word-level flags. That implicit representation is
  replaced by an explicit intermediate representation: a list of
  `ExpandedSegment(text, quoted, splittable, glob_eligible)`. The part
  walkers append segments; the former word-level flags
  (`has_unquoted_expansion`, `has_unquoted_glob`, `all_parts_quoted`) are now
  read-only properties derived from the segment list.
- `_finish` now runs three VISIBLY SEPARATE passes over the segments —
  `_field_split_pass` (IFS-split only the splittable segments, edge-joining
  the rest), `_glob_pass` (pathname expansion, unified for the multi-field
  and single-word cases), then join. The splitting and globbing algorithms
  are preserved verbatim.
- SAFETY NET: a 94-case frozen characterization harness
  (`tests/unit/expansion/test_word_expander_characterization.py`) over every
  axis (quote types, composite joining, `$@`/`$*`/arrays quoted+unquoted with
  affixes, IFS variations, globbing, tilde, all four policies, escapes,
  empty/unset, process-sub paths) — written FIRST, green on the original
  engine, still green after. Plus 9 adversarial bash differential probes, all
  matching. Full suite green (6,168 passed). ruff + mypy clean. No latent
  divergences found.

## 0.333.0 (2026-06-13) - Reappraisal #4 Tier B4: arithmetic decomposition
- REFACTOR (zero behavior change): the 1,155-line `psh/expansion/arithmetic.py`
  is now a package, `psh/expansion/arithmetic/`:
  - `tokens.py` — `ArithTokenType`, `ArithToken`
  - `tokenizer.py` — `ArithTokenizer` (the 213-line `read_number` split into
    per-base helpers: `_read_based_number` / `_based_digit_value` /
    `_read_hex` / `_read_octal`)
  - `nodes.py` — the `ArithNode` AST hierarchy
  - `parser.py` — `ArithParser` (the precedence ladder)
  - `errors.py` — `ShellArithmeticError`/`ArithmeticError`, `_to_signed64`
  - `evaluator.py` — `ArithmeticEvaluator` + `evaluate_arithmetic` /
    `execute_arithmetic_expansion`
  - `__init__.py` — re-exports the full prior public surface, so every
    existing importer (`evaluate_arithmetic`, `execute_arithmetic_expansion`,
    `ArithmeticError`, the tokenizer/parser/nodes) keeps working unchanged.
- SAFETY NET: a 150-case frozen characterization harness
  (`tests/unit/expansion/test_arithmetic_characterization.py`) — all bases,
  every operator, full precedence/associativity, inc/dec, all compound
  assignments, variable/array reads, the error suite — written FIRST,
  confirmed green on the original module, still green after. Full suite green
  (6,074 passed). ruff + mypy clean. Two stale doc-pointers (ARCHITECTURE.md,
  expansion/CLAUDE.md) referencing the old path were updated.
- PRE-EXISTING bug confirmed during characterization (NOT introduced here,
  identical on pristine main; recorded in `docs/reviews/reappraisal_4_tier_b.md`
  for a future behavior release): associative-array elements don't resolve
  inside `$(( ))` (`m[k]*2` → 0 vs bash 18); indexed arrays work.

## 0.332.0 (2026-06-13) - Reappraisal #4 Tier B3: cmdsub scanner decomposition
- REFACTOR (zero behavior change): `psh/lexer/cmdsub_scanner.py`'s
  `find_command_substitution_end` was a single ~341-line function and a known
  correctness hotspot. It is now decomposed into a small `_CmdSubScanner`
  class with one handler method per construct — quotes (single/double/ANSI-C/
  locale), backslash escapes + line continuation, the five `$`-expansion
  forms, backticks, comments, parens (subshell / arithmetic / group),
  separators, redirections + heredoc queueing, and the `case`/`esac` state
  machine. The public function keeps its exact signature and contract; its
  body is now one delegating line (`return _CmdSubScanner(...).scan()`).
- SAFETY NET: a 103-case frozen characterization harness
  (`tests/unit/lexer/test_cmdsub_scanner_characterization.py`) was written
  FIRST, confirmed green against the original code, and still passes
  byte-for-byte after the refactor. No latent divergences were found;
  nothing was silently changed. Six live cmdsub-boundary probes (deep
  nesting, quote-embedded parens, heredoc-with-cmdsub, arithmetic, nested
  backticks, case+cmdsub) match bash. Full suite green (5,925 passed).

## 0.331.0 (2026-06-13) - Reappraisal #4 Tier B2: strict internal-error mode
- NEW OPTION `strict-errors` (off by default; `set -o strict-errors` /
  `set +o strict-errors`, and seeded from the `PSH_STRICT_ERRORS` env var
  the way `debug-exec` is a debug-family option — settable but not listed in
  `set -o`). When on, an UNEXPECTED exception escaping command execution is
  re-raised instead of being masked as a generic `psh: ...` exit-1, so a test
  harness can tell a genuine psh internal defect apart from an ordinary
  nonzero command exit.
- SINGLE SOURCE OF TRUTH: the four structurally-identical last-resort
  "internal defect" guards — `command.py` (`_handle_execution_error`),
  `strategies.py` (`execute_builtin_guarded`), `function.py` (function body),
  and `source_processor.py` (the outermost buffered-statement guard) — now
  all delegate to one helper, `psh.core.report_internal_defect`. The
  deliberate shell-semantics / control-flow exceptions each site already
  re-raises (FunctionReturn/LoopBreak/LoopContinue/SystemExit, readonly,
  unbound, ExpansionError, ...) are unchanged.
- ZERO BEHAVIOR CHANGE with the option off: the non-strict path is
  byte-identical (same messages, same exit codes, traceback still only under
  `--debug-exec`). Default suite stays green (5,822 passed; +7 new tests in
  `tests/unit/core/test_strict_internal_errors.py`).
- FOLLOW-UP (documented, not fixed here): the strict-mode sweep surfaced ~20
  legitimate shell-error paths (bad fd / noclobber / redirect-rollback
  `OSError`, division-by-zero `ShellArithmeticError`, unclosed-quote
  `UnclosedQuoteError`, invalid/readonly function-name `ValueError`) that
  currently flow through the internal-defect guard rather than being
  classified as deliberate shell semantics. Reclassifying them (a proper
  expected-error taxonomy) is the prerequisite to ever enabling strict mode
  suite-wide; recorded in `docs/reviews/reappraisal_4_tier_b.md`.

## 0.330.0 (2026-06-13) - Reappraisal #4 Tier B: CI health
- CI SPEED: the per-PR `tests.yml` gate now runs the **full** suite in
  parallel (`run_tests.py --parallel`) instead of `--quick --coverage`, and
  all three jobs use `cache: pip`. Coverage instrumentation (the dominant
  cost of the old gate) is dropped from the per-PR path. Net: the ~6–7 min
  cycle drops to roughly 2–3 min while testing *more* (full suite vs the
  quick subset). The "Quick Test Suite" job is renamed "Test Suite".
- COVERAGE: moved to the nightly run (`nightly.yml` now passes `--coverage`
  and uploads `coverage.xml`). It was already non-gating reporting, so the
  only change is cadence: coverage is reported daily rather than per-PR.
- RELEASE LOOP: new `release-tag.yml` workflow creates the annotated tag
  `vX.Y.Z` when a `psh/version.py` bump lands on main (skips if the tag
  exists; triggers only on `version.py` changes). This makes tagging
  automatic for asynchronous / auto-merged PRs. Repo "Allow auto-merge" was
  enabled so native `gh pr merge --auto` is available.
- No production code changed; behavior is identical.

## 0.329.0 (2026-06-13) - Reappraisal #4 Tier B1: tooling honesty
- TOOLING: a bare `ruff check .` now passes. `docs/archive` (retired,
  historically-preserved material) is excluded via `extend-exclude` in
  `pyproject.toml`, and the root `conftest.py` is import-clean (dropped an
  unused `import sys`, sorted the block). The strict production gate is
  unchanged: `ruff check psh tests` still lints both live trees with zero
  tolerance (CLAUDE.md).
- DOCS: filed the independent 2026-06-13 code-quality assessment into
  `docs/reviews/code_quality_assessment_2026-06-13.md`, and recorded its
  post-verification residue as `docs/reviews/reappraisal_4_tier_b.md` (the
  plan for this tier). Discarded recommendations that verification showed
  were already shipped (combinator-parser gating, the `ruff check psh tests`
  gate, debug-print gating) or environment-specific (the two quick-suite
  "failures" pass in isolation).
- No production code changed; behavior is identical.

## 0.328.0 (2026-06-13) - Textbook program Tier B10b (TEXTBOOK PROGRAM COMPLETE)
- THE BEHAVIOR FIX (B10a's pin-sweep finding, probed 22-case matrix
  vs bash 5.2 — 11 DIFFs before, 22/22 MATCH after): exported
  variables now sync to state.env through a second ScopeManager
  observer (alongside B10a's PATH hook) firing from set_variable /
  create_local / unset_variable / attribute changes / pop_scope —
  `export FOO=old; FOO=new; printenv FOO` finally shows new; `+=`,
  arithmetic/`${:=}`/read/for-loop/nameref writes, local-shadowing-
  an-export (children see the local, restored on return), unset
  removal, and arrays-never-exported all bash-exact. The fix forced
  out real declared-but-unset semantics (`export FOO` / `declare -i
  N` plant attributed-unset variables: reads as unset, attributes
  apply on first assignment, `declare -p NAME` displays them) and
  fixed `readonly R=1; export R` erroring (bash: metadata changes
  allowed). PWD/OLDPWD now carry EXPORT. 32 conformance pins; three
  accepted divergences documented.
- declare factoring: the two ~50-line attribute if-chains are one
  table; the reporting half is shared psh/builtins/declare_format.py
  (declare -p / readonly -p / export -p — which now escapes values,
  bash-verified; the throwaway-DeclareBuiltin delegation died).
  19-case declare -p matrix byte-identical. function_support 732→639.
- read factoring: three ~210-line loops → one _read_chars core +
  thin dispatchers; SIX unshared quirks discovered and pinned (not
  homogenized): newline-vs-custom-delimiter EOF status, -n -d empty
  rc 0, -t -n immediate-EOF→142, first-byte-only timeout bound,
  silent-mode newline suppression rule, -n 0 short-circuit.
  50-probe + PTY raw-mode batteries byte-identical. 630→576.
- io_redirect residue (verify-first: B3 had NOT touched these): one
  resolve_procsub_target() with the ownership contract documented
  (the builtin path's fd-lifetime difference preserved, not merged
  away); the write-only _saved_std* ritual deleted (probed guarding
  nothing, broken under nesting anyway). Net −38.
- core smalls (verify-first): the `$*` hardcoded-space join was a
  LIVE bug reachable through two duplicates (`IFS=:; echo "${*-def}"`
  gave a b) — one ifs_star_separator() source now, 14 probes match;
  MinimalShell deleted; function.py's "inert" special-var writes were
  worse than inert (leaked `#=0`, `@=[]` into set output) — deleted;
  a provably-dead unset_variable fallback branch removed.
- Net −93 production lines. Suite: 5,815 passed / 6,051 collected,
  0 failures; ruff + mypy (20 files) + doc-pointer clean.

## 0.327.0 (2026-06-13) - Textbook program Tier B10a: hash builtin + parity queue
- The hash builtin (closing the POSIX gap found in v0.308 when CI
  revealed psh's hash tests only passed via macOS's /usr/bin/hash
  stub): CommandHashTable on shell.state (statelessness contract
  honored), HashBuiltin reusing the type builtin's PATH walk,
  parent-side strategy consult pre-fork. Bash 5.2 semantics
  replicated from ~20 probes: hits\tcommand listing, -t/-d/-l/-p/-r,
  hit counts incremented on use AND on -t lookup, builtins/functions/
  slash-names silently skipped, empty-table -d quirk, set +h
  (hashcmds now defaults ON and appears in $-), subshell inheritance
  via adopt(). Probing OVERTURNED the assumed re-verify design: bash
  blind-execs a stale hashed path by default (127 naming the path,
  stale entry kept) — re-search only under shopt -s checkhash. psh
  implements both. PATH invalidation via one ScopeManager observer,
  fired on ANY PATH write (probe-pinned: PATH=$PATH clears; cd does
  not). 3 acceptance tests unskipped; the strict-xfail ledger entry
  flipped; 26 conformance + 27 unit + 5 integration tests.
- Parity queue flipped to bash: (a) assoc-init value-tilde
  (B4's pinned accident) — h=(P=~/x v) keeps the tilde literal;
  leading-tilde and explicit [k]=~ expansion preserved, 6 conformance
  pins. (b) prefix-restore unset (B2's pin) — W=1 true leaves W
  UNSET again (the snapshot now distinguishes unset from empty; the
  old None branch was provably dead code), 8 conformance pins.
  (c) Same-family bonus: no-split contexts join field expansions
  with single spaces like bash — h=($@), h=("$@"), affixed forms,
  and notably declare v="$@" which psh had truncating to the first
  field. 12 more pins.
- Pin-sweep inventory reported for follow-up: exported-variable env
  sync on plain reassignment (REAL: printenv sees stale values —
  queued into B10b), empty assoc keys accepted, hash listing order
  (cosmetic, documented), and the ledger's remaining 10 absent
  features.
- Suite: 5,768 passed / 6,004 collected, 0 failures; ruff + mypy +
  doc-pointer clean.

## 0.326.0 (2026-06-13) - Textbook program Tier B9: one completeness oracle
- CommandAccumulator (scripting/command_accumulator.py, 298 lines):
  feed(line) -> Complete | NeedMore(hint) — the single parser-driven
  answer to "is this command complete?", extracted from the v0.306
  trial-parse machinery, not reinvented. Structured channels replaced
  ALL string matching: UnclosedQuoteError carries quote_char;
  ParseError.unclosed_expansion names the kind;
  ParserContext.open_constructs is a write-only trail (10 parse
  methods push/retitle/pop; no parse decision reads it) snapshotted
  into hints on at_eof. Heredoc bodies tracked incrementally (O(1)
  per line — a first-cut full rescan regressed the large-heredoc test
  and was caught).
- The double parse is DEAD: Complete carries the trial's AST+tokens;
  verified one parse per executed command (was two). debug-tokens/
  debug-ast/--validate/set -v/combinator outputs diffed identical.
- multiline_handler: 515 → 90 lines. The three heuristic layers'
  funeral, each wrongness bash-adjudicated: `echo {a,`/`echo {1..`
  HUNG at PS2 (bash executes) — now execute; escaped-trailing-space
  `echo \ ` hung — now executes; `echo if ; while true` showed
  `if while> ` (only a while is open) — now `while> `; a data-word
  `done` popped the for context — fixed. All 22 previously-correct
  prompt shapes preserved exactly; one inherited improvement:
  successful history expansion re-checks completeness (`if !!; then`
  continues at PS2 instead of mis-executing).
- source_processor: 448 → 286 lines. _collect_heredoc_content died
  into the oracle; the 3 errexit copies + parse-error twin became one
  _should_exit_on_error with exactly 2 call sites; 7 of 9
  string-matched lexer patterns were proven DEAD and removed.
- Net −289 production lines in the two diseased files. 46 oracle
  unit tests + 13 rewritten handler tests + 4 PTY pins for the
  adjudicated fixes. PTY tier ×2: 60 passed. Suite: 5,681 passed /
  5,921 collected, 0 failures; conformance unchanged; ruff + mypy +
  doc-pointer clean.

## 0.325.0 (2026-06-13) - Textbook program Tier B8-R3: history components + dispatch table (zero behavior change)
- The LineEditor decomposition concludes. HistoryNavigator (owns
  pos/original_line; up/down/first/last -> Optional[str]) and
  HistorySearch (feed(char) -> SearchState, a frozen dataclass with
  prompt/line/cursor/status plus repaint and redispatch fields that
  reproduce the old machine exactly) extracted as PURE components in
  psh/interactive/history_nav.py (262 lines) — the editor renders
  returned states via the renderer's prompt-override and owns mode
  transitions. The search flow was mapped first and preserved
  verbatim, including two historical quirks now pinned by tests
  (strictly-before re-search showing failed-bck-i-search on the only
  match; repeated ^R double-decrement).
- The 80-line elif chain in _execute_action is a 31-action
  dict[str, Callable] dispatch table; the vi guard test became a
  full totality test (every name in all five binding tables
  resolves, both modes).
- R1's compatibility properties DELETED — ~140 consumer sites
  migrated mechanically to edit_buffer/renderer; four thin
  navigator-state properties kept deliberately (history's setter
  preserves list aliasing with shell state). Completion UI stays in
  the coordinator: its three methods are pure glue — a sixth module
  would move coordination, not narrow a contract.
- LineEditor is now a 753-line COORDINATOR (docstring states the
  five-component architecture); components: edit_buffer 265 +
  line_renderer 249 + key_decoder 292 + history_nav 262, all in
  mypy scope (19 files). interactive/CLAUDE.md rewritten for the
  five-component reality.
- 26 new tests (11 navigator, 14 search, the totality guard).
  PTY tier green ×2. Suite: 5,641 passed / 5,882 collected,
  0 failures; ruff + mypy + doc-pointer clean.

## 0.324.0 (2026-06-12) - Textbook program Tier B8-R2: KeyDecoder (zero behavior change)
- The decomposition's risk release: psh/interactive/key_decoder.py
  (292 lines) is now the ONLY reader of stdin — it owns the char
  buffer, the select() loop (now multiplexing the SIGWINCH self-pipe:
  readable → drain → Resize event; the three-parameter
  sigwinch_fd/drain/on_resize plumbing collapsed and SignalManager.
  drain_sigwinch_notifications was deleted with its sole caller),
  EIO propagation, full-CSI/SS3-sequence consumption, and pushback()
  for vi ESC-ESC.
- KeyEvent algebra: Char / Key(name) (name=None = complete-but-
  unrecognized, swallowed) / Meta / Escape / Resize / Eof. ^C stays
  Char('\x03') — it arrives as a byte in raw mode, not a signal;
  the old division preserved exactly.
- The ESC layering resolution: timing is a decoder KNOB
  (esc_timeout=0.05 in vi — the v0.283 constant, provenance now
  documented — vs None in emacs: block, ESC is only ever a prefix);
  meaning is editor POLICY (_dispatch_escape_event: Escape→normal
  mode in vi; Meta(c) in vi→normal mode then c as a normal-mode key
  with the second ESC pushed back for full re-disambiguation).
  Edge fidelity preserved: ESC-then-EOF divisions, Delete-on-empty-
  line never EOF, leftover-paste-tail discard. One documented
  micro-delta: emacs search-accept repaint timing on a lone ESC
  (byte→action mapping identical).
- 45 pipe-fed decoder cases (all table sequences, real-timing
  bare-ESC asserting the probe waits, partial-CSI completed
  cross-thread, resize coalescing/interleaving, UTF-8, EIO,
  pushback, the 50ms constant pinned) + 13 mode-policy dispatch
  tests. line_editor.py: 914 → 855 lines; decoder in mypy scope
  (18 files).
- PTY tier green ×2, no flakes. Suite: 5,616 passed / 5,856
  collected, 0 failures; ruff + mypy + doc-pointer clean (the
  meta-test caught a stale CLAUDE.md reference mid-work).

## 0.323.0 (2026-06-12) - Textbook program Tier B8-R1: EditBuffer + LineRenderer (zero behavior change)
- The LineEditor decomposition begins, contract-first: 36 snapshot
  tests pinning exact ANSI byte sequences (the wrap-boundary
  ' \r\x1b[K' commit, multi-row paints, cursor moves across wrapped
  rows, resize arithmetic incl. landing exactly on a boundary, color/
  OSC prompts, the funneled fast-path/^C/bell/clear/completion writes)
  were written against the PRE-SPLIT code and passed 30/30 before any
  extraction; after it they run against the renderer with an injected
  StringIO — the renderer's permanent unit tests.
- EditBuffer (psh/interactive/edit_buffer.py, 265 lines): the single
  source of truth for text+cursor — pure model with kill ring,
  undo/redo (live-buffer-as-implicit-top rule), word ops, transpose's
  exact 4-branch semantics, replace_all for history recall; mutators
  return True-if-changed (the editor's repaint signal). The editor's
  buffer/cursor_pos/kill_ring/undo/redo attributes are compatibility
  properties (R3 cleanup noted).
- LineRenderer (psh/interactive/line_renderer.py, 249 lines): the
  ONLY writer of ANSI — the memo's named leaks (insert fast path,
  accept \r\n, ^C, bell, clear-screen, completion columns, search-
  prompt repaint) all funneled in; output stream injectable.
  Grep proof: line_editor.py has ZERO .write()/.flush() calls; all
  25 sites live in the renderer. Search STATE stays in the editor
  for R3; only its writes moved.
- line_editor.py: 1,064 → 914 lines. Nothing blocks R2/R3 (input
  loop, dispatch, history, search untouched). The 47-test buffer
  battery passes byte-for-byte unchanged on the compatibility
  properties; PTY tier green twice (no flakes); both new modules
  fully typed and added to the mypy scope (17 files).
- Suite: 5,583 passed / 5,823 collected, 0 failures; ruff + mypy +
  doc-pointer clean.

## 0.322.0 (2026-06-12) - Textbook program Tier B7: args derived from words (zero behavior change)
- SimpleCommand.args is now a derived, read-only @property flattening
  words — the stored parallel list is GONE and the diseased state
  (args/words divergence) is unrepresentable by construction (pinned
  by test). 89 consumer hits re-measured (the memo's 67 was stale);
  producers in BOTH parsers now build words only; the executor's
  slice/length/backslash-bypass sites operate on words (the bypass
  provably only ever strips a LiteralPart's backslash); four
  redirect-carrier nodes in strategies.py stopped passing args they
  never read.
- The characterization harness ran BEFORE the deletion: 3,593-command
  corpus, 4,455 SimpleCommands, ZERO mismatches on the recursive-
  descent parser — the derived rule reproduces the old serialization
  byte-for-byte. The combinator parser had 33 tooling-only args-view
  divergences (stored `${y}` where RD stored `$y`); unification
  resolves them — execution always read words. The harness assertion
  is a permanent invariant test.
- Honest finding: _parse_array_initialization's token re-serialization
  is LIVE, not vestigial — the flat `arr=(1 2)` string is re-parsed
  quote-aware by the declaration builtins (array_init.py); element
  Words normalize source details that re-parse differently (`${y}b`,
  `"a""b"`). The misleading Old/New-lexer archaeology comments died;
  the docstring now states why the serialization exists and what
  would have to change to kill it (declaration builtins consuming
  element Words — future work).
- Test-construction decision: 10 explicit args= sites across 4 test
  files — fixed the tests rather than adding a constructor affordance
  (honesty over affordance).
- Perf: the property recomputes per access; measured within noise of
  baseline (0.772s vs 0.798s best-of-3 on an assignment-heavy loop) —
  no cache, no invalidation invariant.
- 17 probe anchors byte-identical incl. xtrace, $_, --debug-ast
  shapes, and all four analysis tools. Suite: 5,547 passed / 5,787
  collected, 0 failures; conformance identical to baseline;
  ruff + mypy + doc-pointer meta-test clean.

## 0.321.0 (2026-06-12) - Textbook program Tier B6: the lexer stops guessing
- literal.py 764 → 326 lines. The four retro-scanning heuristics
  (_is_in_variable_assignment_value's rfind, the "likely/probably"
  _is_in_string_concatenation, _looks_like_array_assignment_before_
  plus_equals, _is_potential_array_assignment_start) are DEAD,
  replaced by pure functions in recognizers/word_scanners.py (623
  lines: scan_glob_bracket / scan_extglob_group /
  scan_assignment_prefix / scan_inline_ansi_c) and an explicit
  forward WordShapeTracker (NEUTRAL → ASSIGN_NAME → ASSIGN_VALUE)
  fed per character — the lexer KNOWS what segment it is in. The
  action-tuple protocol is gone; its 'break' arm was dead code.
  The lexer-level assignment map is built once, cached on
  LexerContext, and consulted instead of re-derived; where it cannot
  be sole authority (boundary-anchored, escape-blind) the supplement
  is the module docstring's documented centerpiece with adversarial
  corners pinned.
- The tokenize loop is TOTAL: the silent char-drop stage is now a
  fail-loudly RuntimeError (census across 15k corpus + full suite +
  71k fuzz inputs: ZERO hits); the fallback word-collector stays —
  the census found it heavily live for exactly four word-start
  classes (']' 1,429 hits, '+' 705, '=' 400, '[' 225), all 11
  representative shapes bash-probed identical — with the census data
  and rationale in its docstring and pins in test_fallback_words.py.
- Packaging: find_command_substitution_end + helpers (519 lines) →
  psh/lexer/cmdsub_scanner.py with its Maintenance Contract intact;
  pure_helpers.py 1,097 → 574 (genuinely pure char-level helpers);
  one command-position vocabulary in command_position.py with the
  three-machines docstring and the fi/done/esac asymmetry documented
  and mechanically verified; tokenize/tokenize_with_heredocs share
  _post_lex.
- Safety: a 15,091-input characterization harness (golden cases +
  generated pathological matrix + 14k harvested literals) diffed
  ZERO token-stream changes after every step — it caught two
  transitional import stragglers mid-refactor. A 957-input
  frozen-stream corpus is now a permanent test.
- Net production diff: +345/−1,294. 53 new tests (scanner contracts
  incl. a retro-predicate oracle over ~3.4k prefixes, fallback pins,
  corpus). Suite: 5,543 passed / 5,783 collected, 0 failures;
  ruff + mypy + doc-pointer meta-test + CPU-perf guards clean.

## 0.320.0 (2026-06-12) - Textbook program Tier B5: ONE parameter-expansion parser
- The program's headline-risk release and its oldest structural
  finding, closed: expansion/param_parser.py's
  parse_parameter_expansion(content) is now the SINGLE ${...}
  grammar (228 lines, ~90 of them a grammar-reference docstring with
  the documented scan strategy: earliest position wins, longest
  operator at that position, bracket-depth-aware). All four sites
  unified: WordBuilder delegates (86→14 lines, covers the combinator
  too) and STOPS deferring subscripted forms — the AST no longer
  lies: ${arr[@]:1:2} is ParameterExpansion('arr[@]', ':', '1:2') at
  parse time (was parameter='arr[@]:1:2', operator=None);
  ParameterExpansion.parse_expansion (152 lines) DELETED;
  expand_variable's pre-dispatch ladder + _is_plain_subscript
  DELETED (string contexts keep their string ENTRY — now
  parse-then-evaluate through the same parser);
  fields._parse_trailing_op DELETED, plus 72 ladder-only lines.
  Net: −460/+112 production lines + the new module.
- The mandatory differential harness (737 distinct ${...} contents
  harvested from the corpus) found 19 divergences BETWEEN THE OLD
  PARSERS — each adjudicated by bash 5.2 probe. 18 behavior fixes
  ride along (presented honestly as fixes, not refactor): the
  ${a[@]:-def}/:=/:+ family after [@] (the := case CRASHED with
  "invalid offset or length"); non-colon operators after ] (
  ${arr[0]-d}, ${a[i+1]+x} were empty); scan-order ${v:-x@Q};
  ${#-} and ${#:-default} disambiguation; element indirection
  ${!a[0]}/${!h[k]}; scalar-subscript resolution unified (${#x[0]}
  was path-dependent 0-vs-5). All-paths-agreed psh↔bash gaps kept
  and documented (${##}, ${v~~}, assoc-slice ordering).
- The evaluator's operator-less round-trip branch instrument-verified
  unreachable for operator-bearing forms (plugin re-parsing every
  node across 1,487 tests: no violations) and narrowed.
- Permanent pins: the 737-row frozen expectation corpus
  (test_param_parser_differential.py — pinned against a frozen table
  with documented provenance, NOT the deleted code), 130+ grammar
  cases, 24 behavior-fix pins. Conformance: POSIX 162/162, bash
  210/217 (the 5 concerns are pre-existing printf message-prefix
  comparisons).
- Suite: 5,490 passed / 5,730 collected, 0 failures; ruff + mypy +
  doc-pointer meta-test clean.

## 0.319.0 (2026-06-12) - Textbook program Tier C1: the internals tour
- New docs/architecture/tour_of_psh_internals.md (516 lines): traces
  `echo "Hello, $USER" | wc -c > out.txt` through input processing →
  tokenization → keyword normalization → parsing → Word-AST expansion
  → pipeline execution → exit status. The defining property: every
  illustration is REPRODUCIBLE — real --debug-tokens/--debug-ast/
  --debug-expansion/--debug-exec output generated this session, with
  the exact regeneration command beside each artifact and trims
  marked. Flag gaps worked around honestly (RichToken parts shown via
  a 3-line public-API snippet; keyword normalization via a two-dump
  contrast). Ends with three trace-it-yourself variations (command
  substitution → run_child_shell; procsub expansion part + scope;
  for-loop keywords + LOOP_ITEM policy), each probe-verified.
- Reader paths wired: ARCHITECTURE.md's note line, the user guide's
  new "Going Deeper" section, root CLAUDE.md's orientation paragraph.
- The doc-pointer meta-test's file list extended to scan the tour —
  its references are enforced like every other load-bearing doc.
- Closes the teaching-mission gap reappraisal #3 graded C+ (the repo
  documented psh as a product; now it teaches it as a textbook).
- Quick gate: 5,324 passed, 0 failures; ruff + mypy clean.

## 0.318.0 (2026-06-12) - Textbook program Tier B3: shared forked-child runner (zero behavior change)
- run_child_shell(parent_shell, body, *, norc, io_setup, error_label)
  in executor/child_policy.py completes the P2 design: signal policy ->
  caller io_setup (BEFORE Shell construction — terminal detection
  inspects fds) -> Shell.for_subshell + in_forked_child -> body ->
  flush_child_streams -> os._exit, with SystemExit(n)->n and unexpected
  exceptions reported to FD 2 (not sys.stderr — the child's stream may
  be a parent-side capture object) -> exit 1.
- The before-tabulation showed how uneven the three child paths were:
  process_sub had NO flush, NO SystemExit mapping, and its signal-
  policy call outside any try; command_sub and ProcessLauncher each
  differed in error channel and flush set. Both substitution sites now
  share the runner; ProcessLauncher KEEPS its own child path
  (pgroup/sync-pipe setup, exec semantics, parent-Shell reuse) with
  the rationale in its docstring, but shares flush_child_streams and
  the fork/signal helpers as code, not copies.
- command_sub's parent-side SIGCHLD reset KEPT with the explanatory
  comment the memo asked for: the interactive SignalManager reaps via
  waitpid(-1, WNOHANG); the SIG_DFL span makes the substitution's
  status capture race-free (script mode: no-op). Proving it vestigial
  needs interactive race probes — deferred deliberately.
- ARCHITECTURE.md invariant #6 strengthened truthfully: One Fork
  Helper, One Child Signal Policy, One Substitution-Child Runner.
- 15-probe battery byte-identical; PTY tier green (56 passed — flush
  changes caused no timing regressions); 12 new tests incl. a
  subprocess driver pinning the runner's exit-code mapping through a
  real fork.
- Suite: 5,324 passed / 5,564 collected, 0 failures; ruff + mypy +
  doc-pointer meta-test clean.

## 0.317.0 (2026-06-12) - Textbook program Tier B4: WordExpander + named policies (zero behavior change)
- Every expansion context has a NAME: frozen WordExpansionPolicy
  (split/glob/assignment_tilde — a caller tabulation proved three
  axes cover every flag tuple in the tree) with named instances
  COMMAND_ARGUMENT, DECLARATION_ASSIGNMENT, LOOP_ITEM (an alias of
  COMMAND_ARGUMENT, by design), ARRAY_INIT_ELEMENT,
  ASSOC_INIT_ELEMENT, consumed by the new
  expansion/word_expander.py engine. The 238-line flag-multiplexed
  _expand_word is decomposed into named phases (expand → walk-literal
  / walk-expansion on a _WalkState → finish: join → split → glob).
  The suppress_split_glob→declaration_assignment ALIASING TRAP is
  dead: the parameter no longer exists; expand_word_to_fields takes a
  required named policy (TypeError pinned by test).
- The scalar assignment-value walker lives beside the policy table in
  the same module, with the docstring explaining why the two walkers
  stay separate. Escape processors moved with the engine (NOT to
  utils/escapes.py, per its dialect-map exclusion).
  _word_to_string became Word.to_literal_string() on the AST
  (could not reuse __str__ — it re-wraps quotes; divergences
  documented). The arithmetic adapter moved into arithmetic.py.
- ExpansionManager: 944 → 267 lines — expand_arguments, the
  declaration-builtin recognition, debug plumbing, and thin public
  delegates (every name ast_data_flow.md documents survives).
- Honest finding pinned under the zero-change contract: the aliasing
  accidentally re-enabled value-tilde in assoc initializers —
  `declare -A h; h=(P=~/x v)` expands the tilde where bash 5.2 keeps
  it literal. Pinned as a PINNED HISTORICAL ACCIDENT with probe/test
  coverage; the one-line bash-parity flip is queued as a future
  behavior fix. Also pinned: the standalone unquoted $@/${a[@]} fast
  path ignores policy split/glob (pre-existing).
- 26-probe battery byte-identical before/after; 20 new policy/engine
  tests. Suite: 5,320 passed / 5,560 collected, 0 failures; ruff +
  mypy (ast_nodes.py annotations extended) + doc-pointer meta-test
  clean.

## 0.316.0 (2026-06-12) - Textbook program Tier B2: CommandAssignments (zero behavior change)
- The assignment sub-domain (9 methods, ~260 lines — what NAME=value
  prefixes MEAN) extracted from CommandExecutor into
  executor/command_assignments.py: CommandAssignments(shell) with
  extract() / apply_pure() / apply_prefix() -> PrefixOutcome
  (saved/applied/failed NamedTuple — the dispatcher genuinely needs
  all three: exec persistence, errexit fatality) / restore().
  CommandExecutor: 724 → 477 lines; _execute_command reads as its
  dispatch shape. The module docstring states the POSIX ordering
  contract once, five probe-verified clauses (words-before-
  assignments, left-to-right value visibility, temporariness +
  special-builtin persistence, the cmdsub status rule, the readonly
  path split).
- Design choice proven by probe: the last_cmdsub_status CLEAR stays
  in the dispatcher (the read moved into apply_pure) — `V=v $(false);
  echo $?` → 1 in both shells because the determining substitution
  runs during command-word expansion before the empty result reroutes
  to the pure path. Moving the clear would have broken it.
- The _visitor backchannel is gone: CommandExecutor takes the visitor
  as a constructor parameter; no getattr-based hidden channels remain
  anywhere in psh/executor/ (repo-wide survey of the remaining 5
  getattr(self,'_...') patterns reported in the PR — all legitimate
  lazy-init flags outside the executor).
- Pre-existing quirk found and pinned (not fixed): prefix-assignment
  restore leaves a previously-UNSET variable set-but-empty
  (`W=1 true; echo ${W+yes}` → psh yes, bash nothing) — snapshot via
  get_variable's '' default; pre-dates this change; candidate for a
  future bash-parity fix.
- 22-probe battery byte-identical before/after (14 bash-exact, 6
  documented pre-existing diffs preserved verbatim). 12 new unit
  tests on the class's public surface.
- Suite: 5,300 passed / 5,540 collected, 0 failures; ruff + mypy +
  doc-pointer meta-test clean.

## 0.315.0 (2026-06-12) - Textbook program Tier C2: doc integrity
- New doc-pointer meta-test (tests/unit/tooling/test_doc_pointers.py):
  six high-precision rules resolving backticked paths and symbol
  references across ARCHITECTURE.md, ast_data_flow.md, and all nine
  CLAUDE.mds, with a commented exemption list for tutorial
  placeholders. Calibrated against pre-fix docs: it caught the known
  §5.3 expand_command_substitution ghost AND a previously unknown
  phantom lexer architecture in §2.1–2.4 (LexerState, StateManager,
  TokenMetadata, Token.add_context — none exist anywhere); §5.1's
  pre-Word-AST expand_argument ghost; a wrong §5.4 file marker.
  All rewritten to the real architecture. Docs can no longer
  reference code that doesn't exist without failing the suite.
- ARCHITECTURE.md truth pass: the One-Fork-Path invariant reworded to
  what is actually true (every fork via fork_with_signal_window() +
  apply_child_signal_policy(); job-controlled creation through
  ProcessLauncher; substitutions fork directly by design — same fix
  in root CLAUDE.md); §5.3 rewritten around the real
  CommandSubstitution.execute(); B1 staleness swept (7-phase Shell,
  for_subshell, visitor_modes.py); combinator "100%" parity and
  "state machine lexer" framings corrected.
- README statistics regenerated (~49,100 LOC / 193 files; ~59,500
  test lines / 262 files) and PINNED by a new tolerance test
  (±10%, including a live --collect-only count) so they fail loudly
  instead of silently lying.
- The three v0.286-frozen CLAUDE.mds refreshed via claim-by-claim
  subagent audits: core (+ShellState.adopt() section, for_subshell
  wording), builtins (+statelessness contract, printf_formatter
  extraction, SHELL_BUILTINS relationship, write_error_line),
  interactive (audit found ZERO wrong claims after 28 releases;
  v0.295/v0.300 sections added).
- Archive sweep: 30 stale files moved to docs/archive/guides/ (8
  bannered guides, 20 public-api point-in-time files, 2 unbannered
  2026-02 guides); docs/guides/ now holds only the two current
  combinator docs.
- CHANGELOG split: 122 pre-v0.200.0 entries moved to
  docs/archive/CHANGELOG_history.md (4,297 → ~2,490 lines) with
  pointer; verified nothing parses it programmatically.
- Probe-promotion convention added to the bash-verification workflow:
  surviving probes become golden_cases.yaml entries, not tmp/ debris.
- Suite: 5,528 collected (16 new tooling tests); quick gate green;
  ruff (psh+tests) + mypy clean.

## 0.314.0 (2026-06-12) - Textbook program Tier B1: Shell lifecycle (zero behavior change)
- Shell.__init__ is now 31 lines (was 122): seven named lifecycle
  phases, each docstringed with its before/after state —
  _create_state, _init_managers, _inherit_from_parent,
  _init_shell_components, _select_parser, _init_traps,
  _init_interactive. shell.py's module docstring finally answers
  "what is a Shell?" from the file itself.
- Shell.for_subshell(parent, *, norc=True) replaces the inline
  parent-inheritance block; the pure state-copying half lives in
  ShellState.adopt(parent_state). All five construction-with-parent
  sites migrated (foreground/background subshells, command
  substitution, process substitution, the env builtin — the last two
  keep their historical norc=False explicitly; quirk noted for a
  future look). 12 new tests pin exactly what a child inherits.
- The CLI analysis modes (--validate/--format/--metrics/--security/
  --lint, 77 lines) moved off Shell to scripting/visitor_modes.py;
  all five probed byte-identical.
- The forwarding magic is GONE: __getattr__/__setattr__/
  _setup_compatibility_properties deleted. Four explicit properties
  (stdout/stderr/stdin/env, with write-through setters — ~126 of the
  forwarding's production uses) remain as Shell's deliberate public
  face for builtins; the other 37 production + 8 test sites were
  rewritten to shell.state.X. A typo'd shell.attr now raises
  AttributeError instead of silently reading ShellState — pinned by
  test. One regression during the sweep (return builtin's
  function_stack read on a line that mixed both forms) was caught by
  the suite's 33 failures and root-fixed, then the sweep re-run with
  a per-occurrence regex: zero residuals.
- psh/shell.py joins the mypy files list (15 files now), fully
  annotated, zero ignores.
- Suite: 5,273 passed / 5,513 collected, 0 failures; ruff + mypy
  clean. Refactor contract: zero behavior change — subshell/procsub/
  cmdsub/env/source/rc-file/parser-selection batteries and all five
  analysis modes probed identical.

## 0.313.0 (2026-06-12) - Textbook program Tier A2: test/CI honesty (TIER A COMPLETE)
- Timing tests measure CPU time: test_lexer_performance.py and the
  benchmark helpers use time.process_time() + min-of-3 (preemption
  steals wall time, not CPU time). Regression sensitivity PROVEN by
  temporarily injecting an O(N²) loop (failed at ratio 4.0) and
  removing it. The xdist timing-flake class is closed.
- Skip-debt purge: the 5 legacy interactive files (53 dead skips with
  false reasons) deleted AFTER porting their 6 uncovered behaviors to
  the PTY smoke tier — Ctrl-R reverse search, unique-file and
  common-prefix tab completion (pass), command/variable completion
  (strict xfail: CompletionEngine is path-only — flips loudly when
  implemented), Ctrl-L screen clear, pipeline-in-PTY. The wrong
  subshell xfail rewritten to pin bash semantics (subshell exit 0 when
  the failing command isn't last — bash agrees). Census: 272 skips /
  1 xfail → 220 skips / 20 xfails, every reason now true and
  printable via the new --census flag.
- Absent-feature ledger (tests/conformance/bash/
  test_absent_features.py): 19 features probed firsthand against bash
  5.2.26 — 18 strict-xfail entries (coproc, wait -n/-f, read -u, bind,
  compgen, complete, caller, hash, enable, exec -a, lastpipe,
  failglob, ${a[@]@K}, extglob-in-param-expansion, jobs -x, suspend,
  test -v) + 1 documented-wontfix skip (history expansion). The two
  SILENT TRAPS are called out: @K degrades to plain values rc 0, and
  shopt -s extglob reports "on" while patterns are inert in parameter
  expansion. "98% compliance" now has an honest denominator;
  implementations flip entries loudly.
- visitor SHELL_BUILTINS documented as bash-scoped, 13 missing
  registry builtins added, and pinned in BOTH directions by a new
  test (registry ⊆ list; extras must be on an explicit allowlist that
  itself fails if psh implements one).
- Builtin statelessness enforced: ~60-command battery then
  vars(instance) == {} for every registered builtin; contract
  documented in base.py. Caught a real bug: an executor test fixture
  leaked its builtin instance into the registry process-wide.
- directory_stack/help channel-convention sweep (raw prints →
  write_line); probing fixed real divergences: dirs -p added,
  dirs/popd/pushd -N off-by-one corrected (bash counts from the
  right, 0-based), dirs -v uses bash's two-space separator.
- CI: quick-suite job uploads a non-gating coverage.xml artifact
  (run_tests.py --coverage threads cov args through every phase);
  new nightly.yml (cron 03:00 UTC + workflow_dispatch) runs the full
  parallel suite with --compare-bash --census plus the complete
  conformance suite, printing bash --version. run_tests.py prints
  combined cross-phase totals.
- Suite: 5,261 passed / 5,501 collected, 220 skipped, 20 xfailed;
  ruff (psh+tests) + mypy clean.

## 0.312.0 (2026-06-12) - Textbook program Tier A1: behavior batch
- printf: the ~550-line formatting engine extracted to pure
  utils/printf_formatter.py (format_printf(fmt, args) -> PrintfResult;
  no shell dependency; the builtin thins to ~50 lines; print -f
  migrated too). Fixed against a ~90-case bash 5.2 probe battery:
  `%*`/`%.*` width/precision from arguments (negative width
  left-justifies, negative precision omitted); `%n` assigns
  chars-written; `%p`/`%v` and bare `%` are bash-shaped fatal errors;
  integer parsing is strtoll base-0 (0x/0 prefixes, 'A char codes,
  trailing-junk warnings, 64-bit wrap for %u/%x/%o, overflow clamp at
  rc 0); `%c` takes the first character (psh's old chr() behavior was
  wrong — `printf '%c' 65` prints 6); `%b \c` terminates all output;
  length modifiers accepted; `printf --` handled. 59 engine tests +
  18 builtin tests + 4 conformance tests.
- All three fork sites now share fork_with_signal_window() in
  executor/child_policy.py — command_sub.py and process_sub.py never
  received the v0.300 lost-signal fix (latent race, found by
  reappraisal #3). Also: process_sub's temp shell now sets
  in_forked_child=True; command_sub's silent bare-except writes the
  exception to fd 2 before _exit.
- Readonly-prefix assignments match bash: `RO=2 cmd` reports the error
  and STILL RUNS the command (rc = command's); other prefix
  assignments apply-then-restore (also fixed a restore leak where
  `OK=5 RO=2 true` left OK set permanently); pure `RO=2` aborts rc 1;
  under errexit the error is fatal and the command does not run.
  25-case probe matrix; 10 conformance tests; 2 old tests pinned the
  anti-bash behavior and were updated after bash verification.
- os.environ is read-once at startup: state.env is authoritative and
  every child receives it explicitly (execvpe/shebang env=/parent_shell
  copy — verified). All four vestigial os.environ writes deleted
  (allexport, export_variable, the `FOO=bar exec` leak, export -n
  pop); zero writes remain in psh/. Policy documented in ShellState's
  docstring and core/CLAUDE.md. Corrected claim along the way: bash
  does not persist `FOO=bar exec` without a command; psh now matches.
- Dead code deleted (~135 lines, callers re-verified): arrays.
  is_array_expansion, CommandExecutor._extract_assignments/_is_exported
  + assignment_utils.extract_assignments/is_exported chain, manager.py
  dead public expand_variable()/execute_command_substitution().
- Suite: 5,249 passed / 5,522 collected; ruff (psh+tests) + mypy clean.

## 0.311.0 (2026-06-12) - ARCHITECTURE.llm retired (doc consolidation)
- ARCHITECTURE.llm moved to docs/archive/ (git mv, content untouched).
  Rationale: its LLM-orientation role is now better served by the
  subsystem CLAUDE.md network + docs/architecture/ast_data_flow.md,
  and the dual file was a proven drift surface (the v0.298 purge had
  to hit both files; v0.305 left three stale TokenTransformer
  references in the .llm alone).
- Its uniquely valuable content folded into ARCHITECTURE.md as a
  leading "Quick Map" section: component hierarchy tree (refreshed —
  visitor/ package added, pattern.py and the educational-only
  combinator status reflected), one-line-per-phase execution
  pipeline, architecture invariants (updated: One Fork Path and
  Fail Loudly added; stale arg_types history dropped), and a
  "Where do I change X?" table pointing at subsystem CLAUDE.mds.
- References updated: root CLAUDE.md release ritual now lists four
  version-stamped files (and now documents the PR + CI-green +
  tag workflow that has been practice since v0.279); six guide
  cross-references repointed; ARCHITECTURE.md's pointer note
  replaced with the orientation path (Quick Map → subsystem
  CLAUDE.md → ast_data_flow.md).
- One fewer drift surface; no content lost (archive retains the
  full historical file).

## 0.310.0 (2026-06-12) - Hygiene release: fallback audit, AST data-flow doc, scanner contract
- Every string-only legacy AST fallback audited and classified
  (reassessment next-steps #1/#2/#4): each site checked against every
  construction point in BOTH parsers plus direct test construction.
  Outcomes: (a) required-compatibility — for/select item_words=None
  manual-AST path, kept + tested; (b) migration bridge — combinator
  CasePattern(word=None) for exotic patterns, kept + tested with an
  AST-inspection canary that fires if the combinator gains support;
  (c) unreachable-defensive ×7 — replaced with internal-error raises
  per the v0.300 fail-loudly policy (incl. _expand_word's silent
  str(word) coercion and a fallback whose comment claimed a combinator
  edge that no longer exists); (d) dead ×2 — deleted (~106 lines incl.
  the whole legacy explicit-[i]=v string re-parser).
- The audit found a LIVE bash divergence in a "dead" fallback: the
  legacy explicit-element branch keyed on element_types and OVERRODE
  correct Word semantics — `a=("[0]"=x)` assigned a[0]=x where bash
  keeps the literal element `[0]=x`. Fixed by deletion;
  conformance-pinned.
- New docs/architecture/ast_data_flow.md (~200 lines, linked as
  ARCHITECTURE.md §3.13): the canonical build-site → expansion-policy →
  implementation pointer for command words, assignment values, array
  initializers/elements, for/select items, case subject/patterns,
  redirect targets/heredocs (the legitimate string contexts),
  process substitution, and compound-redirect visitor totality —
  with an "I want to change X → edit here" table. Every pointer
  verified against source.
- find_command_substitution_end gained a Maintenance Contract
  docstring block (parser-grammar changes touching case/heredoc/
  quoting/arithmetic must consider the scanner; owner tests listed);
  16 new bash-probed conformance cases (nested functions in $(),
  procsub inside $(), $(case) in heredoc bodies, quoted-paren
  patterns, arithmetic with case-like names, rc-pinned unclosed-EOF
  boundaries).
- 32 new tests. Suite: 5,151 passed / 5,424 collected;
  ruff (psh+tests) + mypy clean.

## 0.309.0 (2026-06-12) - Combinator parser declared educational-only
- Project decision (resolving a question raised by three successive
  external reviews): the combinator parser is EDUCATIONAL ONLY and
  outside the production quality bar. Parity regression tests continue
  to pin known-good behavior against drift, but documented gaps (e.g.
  composite words in some list contexts, `select` without `in`) are
  not tracked as defects, and conformance work does not target it.
  The decision may be revisited when dedicated time is available.
- Recorded everywhere the status is stated: the class docstring
  (combinators/parser.py), parser/CLAUDE.md (with a note that reviews
  should not count its gaps as findings), the combinator guide banner,
  ARCHITECTURE.md/.llm, parser-select help, and --parser CLI help.
- README's inaccurate parity claims corrected: "100% feature parity"
  (×2) and "Both parsers support all shell constructs" replaced with
  the accurate framing — these claims predated the parity-regression
  work and were verifiably false (the gaps are documented in the
  parity test files and reviews).
- No behavior changes; parser-select and --parser combinator work
  unchanged.

## 0.308.0 (2026-06-12) - CI green (first passing run in the workflow's history)
- The Tests CI workflow had NEVER passed — 190+ consecutive failures
  going back past v0.287. Two quality reviews verified the workflow
  CONFIGURATION matched the docs; nobody (reviewer or maintainer)
  checked an actual run result. Lesson recorded: "CI matches the
  documented gate" must mean a green run URL, not a config read.
- Quick-suite job: [dev] extras were missing pyyaml (behavioral
  golden-case loader) and pexpect (PTY-tier modules import it at
  collection time even though the tests are runtime-gated) — 6
  collection errors on every run. Added both.
- Lint job: CI runs `ruff check psh tests`; the documented local gate
  was `ruff check psh/` only. CLAUDE.md now mandates the CI command;
  the one outstanding test-tree lint error fixed.
- 17 environment-portability test bugs fixed once the suite actually
  ran on ubuntu (all test bugs, no product bugs): hardcoded
  /Users/pwilson cwd in the assoc-array regression file; a hardcoded
  '~/src/psh' fallback in 7 directory-stack assertions (replaced with
  an independent tilde-abbreviation helper — strictly stronger);
  BSD-vs-GNU ls exit codes pinned in 2 redirection tests (now derived
  from the local tool at runtime / switched to POSIX-pinned test -e);
  a 300KB script passed as one argv element (Linux MAX_ARG_STRLEN is
  128KiB — heredoc tests now run via script file).
- Product gap discovered: psh has NO hash builtin — the two hash
  tests only ever passed because macOS ships /usr/bin/hash, a 4-line
  sh stub that runs in a throwaway subprocess (they never exercised
  psh code). Skipped with the gap documented in the reason; implement
  hash to unskip.
- All three CI jobs green on PR #40 (Lint 16s, Conformance Smoke 39s,
  Quick Test Suite 4m56s); full local suite green; ruff + mypy clean.

## 0.307.0 (2026-06-12) - Visitor totality over the AST (reassessment Phase 3 — PHASE 3 COMPLETE)
- Finding #8 and Phase 3: the analysis visitors are now total over the
  AST, enforced by an introspective coverage-matrix test. The
  before-matrix found far more than the review's two examples:
  - Formatter: UntilLoop hit the unknown-node fallback (the repro);
    FunctionDef and ArithmeticEvaluation DROPPED their redirects;
    background `&` lost on AndOrList; no word-level methods. Now has
    an explicit visit method for all 36 concrete node classes, with
    reparse round-trip tests.
  - Security visitor: 6 of 13 redirect carriers (while/for/if/case/
    function/arithmetic) never inspected their redirects —
    `while ...; done >/etc/passwd` reported nothing. All carriers
    now flag sensitive writes via a shared _visit_redirects().
  - Validator: UntilLoop, SubshellGroup, BraceGroup, and
    ArithmeticEvaluation subtrees were SILENTLY SKIPPED entirely
    (`until ...; do break 5; done` and `( break )` produced zero
    diagnostics); compound redirects never validated. Fixed.
  - Metrics: redirections/heredocs counted only on SimpleCommand;
    debug-ast lost children of until/subshell/brace-group. Fixed.
  - Linter and the executor visitor verified total already (the
    executor raises on unknown nodes — no gaps).
- tests/unit/visitor/test_ast_coverage_matrix.py (85 tests):
  programmatic node inventory (36 concrete classes, 7 abstract
  bases); per-visitor totality assertions matching each visitor's
  documented generic_visit design; a redirects matrix proving every
  source-reachable carrier (13) is security-flagged,
  formatter-emitted, and metrics-counted. ALL exemption lists are
  EMPTY except REDIRECT_EXEMPT={Break,Continue} (their redirects
  fields are unreachable from source — both parsers parse `break >f`
  as two statements; pinned by a dedicated test). Adding a new AST
  node without visitor support now fails the suite loudly.
- visitor/CLAUDE.md: new "Totality Over the AST (enforced)" section;
  wrong example name fixed; new-node checklist points at the matrix.
- Suite: 5,122 passed / 5,392 collected; ruff + mypy clean.

## 0.306.0 (2026-06-12) - Grammar-aware command substitution (reassessment Phase 2, 2/2 — PHASE 2 COMPLETE)
- The long-standing Known Limitation is CLOSED: `$(case x in x) echo
  inner;; esac)` parses and runs (bash prints `inner`; psh errored at
  `;;` in both parsers since the paren-counting scanner predates the
  reappraisal programs). New pure scanner find_command_substitution_
  end() in pure_helpers.py models exactly the contexts where `)` is
  not a closer: quotes (incl. $'...' and nested-expansion rescan),
  backticks, ${...}, nested $(...), $(( ))/(( )) arithmetic with the
  lexer's greedy dispatch, # comments at word start, heredocs
  (pending-delimiter queue shared across nesting levels — bash reads
  bodies at the next physical newline regardless of depth, probed),
  group parens, and a case-statement state stack (case at command
  position → subject → in → pattern⇄body via ;;/;&/;;&, one unmatched
  `)` per pattern, esac pops). Design rationale lives in the
  docstring — it replaces ARCHITECTURE.md Known Limitation #2.
- All seven paren-counting consumers upgraded to the scanner:
  expansion_parser, process-sub recognizer (`<(case ...)` works),
  $((...)) extent, ${...} validation, array-word shapes, the
  execution-time operand scanner, and heredoc line-gathering's
  inside-expansion check.
- Three pre-existing multiline bugs fixed (exposed by the probe
  battery, all broken on main): unclosed-expansion ParseErrors now
  set at_eof=True so multiline `$(\necho hi\n)` gathers continuation
  lines; the source-processor completeness check uses
  tokenize_with_heredocs (a heredoc body line `)` was a bogus parse
  error); multi-line buffers starting with `#` were swallowed whole
  by two comment-skip checks.
- Probe battery 13/34 → 32/34 exact matches; the 2 remaining are
  deliberate documented divergences (escaped-paren pattern rejected
  by both shells with different wording; same-line shopt extglob
  timing where psh matches `bash -O extglob`).
- Docs: ARCHITECTURE.md limitation replaced with fixed-by note;
  user-guide ch6 note deleted, ch17 row note updated; call-site
  comment rewritten as design doc. Claims meta-test green.
- 85 new tests (51 scanner/lexer unit, 23 integration incl. both
  parsers and stdin/script modes, 11 conformance).
- Suite: 5,037 passed / 5,307 collected; ruff + mypy clean.

## 0.305.0 (2026-06-12) - Grammar boundaries: case subject, bracket quotes, TokenTransformer (reassessment Phase 2, 1/2)
- Finding #6: `case` now parses exactly one subject word before `in` —
  `case a b in ...` is a bash-shaped syntax error (was silently
  accepted, joining the words). Four adjacent divergences fixed by
  probing: `case in in ...` and `for in in ...` work (the token after
  case/for/select is never the `in` keyword), newlines allowed before
  `in` but rejected after `case`, and empty `case a in esac` is valid
  while `esac)` as a pattern is rejected — all bash-exact.
- Finding #5 (broader than stated): the lexer suppressed quote AND
  expansion parsing for any unmatched `NAME[` shape. Now only
  confirmed `NAME[...]=`/`+=` subscripts suppress; consequently
  unterminated quotes in bracket words are lexer errors
  (`echo x["unterm` was silently literal), and `x["ok"]`, `x[$v]`,
  `x[$((1+1))]` finally quote-remove/expand like bash. Escaped quotes
  in glob brackets preserved; assignment forms (`h["k 1"]=v`,
  `a[$(cmd)]=y`) probe-pinned. No lexer performance regression
  (benchmarked).
- Bonus fix required by the keep-working battery (broken on main):
  `${h["key"]}` returned empty — assignment stripped wrapping quotes
  but lookup didn't. New expand_assoc_key() applies the same quote
  removal at all five assoc lookup sites (`${h['k']}`, `${h["$k"]}`,
  `${#h["key"]}` all match bash now).
- Finding #9: TokenTransformer DELETED — verified every branch
  appended the original token unchanged (validation intended at
  v0.27.1, never implemented) and the parser already rejects
  misplaced `;;`/`;&`/`;;&` with bash-shaped errors. Docs updated
  (lexer CLAUDE.md pipeline, ARCHITECTURE.llm, guides).
- 77 new tests (case subject 26, misplaced terminators 10, bracket
  quotes 29, conformance 12).
- Suite: 4,954 passed / 5,224 collected; ruff + mypy clean.

## 0.304.0 (2026-06-12) - Array element values as Words (reassessment Phase 1, 3/3 — REASSESSMENT PHASE 1 COMPLETE)
- Finding #4, confirmed and worse than stated: the root cause was a
  layer below the executor — the lexer's _collect_array_assignment()
  swallowed the whole raw value as one opaque token (and terminated at
  `(`), so `a[0]=$(cmd)` and `a[0]=$((expr))` were mis-lexed into
  garbage, `a[0]='lit $x'` expanded inside single quotes, and tilde/
  ANSI-C/escape forms were all broken in element values.
- Fix: the lexer now stops right after `=`/`+=` so element values
  tokenize identically to scalar assignment values; ArrayElement-
  Assignment carries value_word (both parsers populate it); and ONE
  shared bash assignment-value policy — new ExpansionManager.
  expand_assignment_value_word() (all expansions, no split, no glob,
  tilde after =/:, quote-aware) — serves scalar assignments (the
  executor's 75-line loop now delegates), array element assignments,
  explicit [i]=v initializer elements, and assoc-initializer keys.
  Manual quote-stripping deleted.
- Explicit-initializer and assoc fixes that fell out, all bash-pinned:
  `a=([0]=$x [1]=*)` (values unsplit, globs literal), `[i]+=` append,
  `a=("[0]=x")` quoted form stays a literal element, and
  `declare -A h; h=([k]=v ...)` — previously the KEYS went to index 0;
  the alternating pair form `h=(k1 v1 k2 v2)` now works too.
- 63-probe battery matches bash 5.2 (4 pre-existing out-of-scope
  diffs recorded: `declare a[0]=v` subscripted declare args;
  bash's error-then-run on `a[0]= cmd` prefix forms).
- Test portability: the affixed write-side procsub test now probes
  bash itself for OS support of the `/.>(...)`  shape and skips with
  a clear reason where the OS forbids it (reassessment found a macOS
  environment where bash also fails it).
- 61 new tests (test_array_element_word_values.py).
- Suite: 4,877 passed / 5,147 collected; ruff + mypy clean.

## 0.303.0 (2026-06-12) - Word-splitting semantics: declaration policy + loop items (reassessment Phase 1, 2/3)
- Finding #2 (High): assignment-shaped ordinary arguments now
  word-split like bash — `x="a b"; printf "<%s>" foo=$x` gives
  `<foo=a><b>` (was one field). Suppression is now an explicit
  DECLARATION_BUILTINS policy (alias, declare, typeset, export, local,
  readonly) with bash's *syntactic* recognition, all probe-pinned:
  the command word must be an unquoted literal — `command export`,
  `builtin export`, `\export`, `"export"`, and `$d` (d=declare) all
  SPLIT in bash 5.2 and now in psh; `eval export` doesn't (re-parse).
  Declaration args also skip pathname expansion (`declare foo=*`
  stays literal). True command-prefix assignments were already
  stripped pre-expansion (verified, unchanged).
- Probes CORRECTED the review's tilde claim: bash does tilde-expand
  assignment-shaped ordinary args (`echo P=~/x` → expanded).
  Implemented bash's rule (after first `=` and each `:`, valid NAME
  only, `+=` form too, quoted prefix suppresses) — also fixing
  pre-existing bugs in real assignments (`P=a:~:b` colon-tilde,
  `P=~"x"` over-expansion). Array initializers don't expand
  (bash-verified).
- Adjacent gap closed: `NAME+=value` arguments now work for
  declare/typeset/readonly/local (export already did) via shared
  core/assignment_utils.resolve_append_assignment() — textual,
  integer (-i), and scalar-append-to-array (was leaking an
  IndexedArray repr).
- Finding #3 (Medium): for/select item lists route through
  expand_word_to_fields(). ForLoop/SelectLoop carry item_words
  (the RD parser already built the Words and flattened them; the
  combinator now builds them too, fixing its composite-item bug);
  the 60-line legacy item-expansion engine is DELETED. Fixes
  IFS-aware splitting of command subs (`IFS=:; for i in $(printf
  a:b)` → two items), unquoted `${a[@]}` debris, tilde items,
  arithmetic-result splitting. 28-case probe table matches on both
  parsers.
- 92 new tests (56 assignment-splitting/tilde/append unit tests,
  36 loop-item integration tests incl. select-via-stdin and
  combinator parity). Conformance unchanged: POSIX 162/162.
- Known pre-existing edges recorded, not fixed: `name+=(...)` not
  tokenized as one word at the lexer; `declare -ai` arithmetic
  append to array element; no failglob.
- Suite: 4,816 passed / 5,086 collected; ruff + mypy clean.

## 0.302.0 (2026-06-11) - Per-invocation builtin redirection frames (reassessment Phase 1, 1/3)
- High-severity Finding #1 from docs/reviews/code_quality_subsystem_
  reassessment_2026-06-11.md: nested builtin redirections restored the
  wrong state. setup_builtin_redirections kept per-invocation state on
  the SHARED manager — _saved_fds_list was drained wholesale by ANY
  restore (so an inner builtin's restore re-pointed the outer eval's
  fd 3 mid-body: `exec 3>f; eval "echo one >&3; echo two >&3" 3>&1`
  sent `two` to the file; bash sends both to stdout), and
  _opened_streams was reassigned per setup. (Correction to the claim:
  the v0.292 _BuiltinStreamSnapshot was already per-call.)
- Fix: new BuiltinRedirectFrame owns the snapshot, fd-level dup
  backups, and opened streams; setup returns the frame and restore
  takes it by identity. Innermost-first order is enforced by paired
  try/finally construction; out-of-order restore is tolerated (that
  frame's own state still restores — no leak) and documented.
  Transactional rollback rolls back only the partial frame — an inner
  failed redirection no longer corrupts the outer frame. Procsub
  registrations deliberately stay with process_sub_scope() (moving
  them would re-break the v0.288 function-argument case).
- Bonus fix (pre-existing, found by probing): `>&m` for m>=3
  (`eval "echo b >&3" >/dev/null`) was fd-level only — invisible when
  sys.stdout is a swapped stream. Now handled in both universes via
  the exec-style shared-fd dup pattern.
- Nesting entry points mapped and tested: eval, source, EXIT/DEBUG
  traps mid-frame, command substitution (forks — unaffected, pinned),
  three-deep mixed-universe nesting, partial-frame rollback. 16 new
  bash-pinned tests (test_builtin_redirect_nesting.py).
- Known out-of-scope DIFF recorded: assignment-only commands apply
  redirects before expanding their command substitution
  (`x=$(echo inner >&2) 2>/dev/null`); bash expands first.
  Pre-existing, unrelated to frame state.
- Suite: 4,724 passed / 4,994 collected; ruff + mypy clean.

## 0.301.0 (2026-06-11) - Embedded process substitution (quality assessment Phase 1, 3/3 — PHASE 1 COMPLETE)
- Correctness Risk #2: `echo pre<(echo hi)post` printed literal text;
  bash prints `pre/dev/fd/63post`. The lexer already tokenized procsub
  mid-word and the parser already merged composites — but WordBuilder
  had no PROCESS_SUB branch, so the token fell into the literal
  fallback. The whole-word case only worked via a string-sniffing
  pre-pass in ExpansionManager.
- ProcessSubstitution is now an Expansion subclass carried as an
  ExpansionPart inside Words, exactly like $(...): WordBuilder builds
  it (covers both parsers' composites), _expand_word performs the
  substitution inline and splices the /dev/fd/N path (exempt from IFS
  splitting and globbing, bash-verified), and the old pre-pass +
  _has_process_substitution are DELETED — whole-word is now just the
  one-part case of the same mechanism. No remaining duality for
  command words (redirect-target procsub keeps its separate,
  untouched path).
- Fixed as natural fallout: procsub in assignments (`x=<(echo hi)` was
  "command not found"; bash assigns the path) and in array
  initializers (rd parser); multiple substitutions per word get
  distinct fds; quoted forms stay literal; case patterns, heredocs,
  and arithmetic keep procsub literal like bash.
- Cleanup integrates with the v0.288 scope ownership: new
  create_for_expansion() registers fd+pid in the same active lists;
  fd and zombie censuses pass with embedded forms, including when the
  consumer command fails.
- 28 new tests (+2 combinator pins updated). Pre-existing gaps
  reported honestly, all verified identical on main: combinator
  case-pattern/array-element handling; string-context sites
  (for-in iterables, case subjects, [[ -p ]]) still don't perform
  procsub; `~<(x)` tilde divergence.
- Suite: 4,708 passed / 4,978 collected; ruff + mypy clean.

## 0.300.0 (2026-06-11) - Loud expansion errors + signal lifecycle (quality assessment Phase 1, 2/3)
- Correctness Risk #5: expand_expansion no longer catches (ValueError,
  AttributeError, TypeError) and returns str(expansion) — internal
  bugs surfaced as literal output. Git archaeology showed the catch
  was never driven by a user-input need (born as bare except in the
  Word-AST migration); the one genuine user-facing ValueError
  (substring < 0) was already converted to ExpansionError locally by
  the v0.296 slice work. A sibling same-shape catch in variable.py
  (silently degrading operator bugs to plain-${var}) also removed.
  Deliberate catches reviewed and kept (subscript int()→'0' etc. are
  bash semantics). 20-case probe battery: behavior unchanged for all
  user-facing errors; full suite green with the catches gone.
- ProcessLauncher.launch: fork sigmask restore wrapped in try/finally
  — if os.fork() raises (EAGAIN), the parent no longer keeps
  TERM/INT/HUP/QUIT blocked forever. Child path unaffected (never
  returns; unblocks via apply_child_signal_policy). Disproof recorded:
  command_sub.py and process_sub.py fork WITHOUT mask manipulation,
  so they had nothing to leak.
- Interactive signal lifecycle (assessment claim CONFIRMED):
  restore_default_handlers() had zero callers — handlers were never
  restored on any REPL exit path (matters for embedded Shell use,
  e.g. the test suite). run_interactive_loop now restores in
  try/finally on normal EOF, exit-builtin SystemExit, and exceptions.
  Two adjacent latent bugs fixed: double setup_signal_handlers()
  overwrote the true pre-psh originals (now setdefault-guarded), and
  SignalNotifier.close() wasn't idempotent (explicit close + __del__
  could close an unrelated reused fd). Self-pipes recreated on loop
  re-entry.
- 16 new tests (9 error-propagation, 2 sigmask with monkeypatched
  EAGAIN fork, 5 serial lifecycle tests incl. loop re-entrancy) —
  all verified red against unfixed main.
- Suite: 4,680 passed / 4,950 collected; ruff + mypy clean.

## 0.299.0 (2026-06-11) - Array initializers through the Word expansion engine (quality assessment Phase 1, 1/3)
- Correctness Risk #1 from docs/reviews/code_quality_subsystem_
  assessment_2026-06-11.md: `a=(...)` initializer elements were
  expanded with expand_string_variables + Python .split() + raw
  glob.glob(), bypassing quote context, IFS, and noglob/nullglob/
  dotglob. Verified divergences fixed: `a=("*.txt")` no longer globs a
  quoted pattern; `IFS=:; a=($x)` splits on IFS; `set -f` is honored;
  no-match globs stay literal (or vanish under nullglob);
  `b=("${a[@]}")` preserves elements; tilde and composite
  `pre"$x"post` elements expand correctly.
- The fix was architecturally cheap because the RD parser ALREADY
  built Word AST nodes for every element and discarded them:
  ArrayInitialization now carries `words`, both parsers populate it,
  and the executor expands each element via the new public
  ExpansionManager.expand_word_to_fields() — the same pipeline as
  command arguments, with one bash-verified context difference
  (initializers word-split `k=$x`; command args don't).
- Scalar contexts unchanged and probe-pinned: `a[0]=*` stays literal;
  explicit `[k]=v` initializer elements and `declare -A h=([k]=v)`
  keep their paths.
- Bonus fixes: newlines inside `a=(1
  2)` now parse (bash allows; was a parse error), and `$((...))`
  elements now parse in the combinator parser.
- Probe battery: 53/53 match bash 5.2 on the RD parser (was 34/53);
  combinator 49/53 (remaining 4 are its pre-existing composite-element
  limitation). 56 new tests (51 integration + 5 conformance).
- Suite: 4,664 passed / 4,934 collected; ruff + mypy clean.

## 0.298.0 (2026-06-11) - Doc fix-in-place pass (reappraisal #2 Tier C, 2/2 — REAPPRAISAL #2 COMPLETE)
- executor/CLAUDE.md: phantom builtin_base import fixed (real: .base +
  .registry); pipefail corrected to rightmost-non-zero; process-group
  description fixed (the PARENT setpgid's members while children block
  on the sync pipe); job_control.py added to Key Files; v0.288/v0.289
  drift incorporated (process_sub_scope wiring, report_exec_failure).
- lexer/CLAUDE.md: phantom _tokenize_next replaced with the real
  tokenize() loop; recognizer registration corrected to
  _setup_recognizers (recognizers/__init__.py only re-exports, and
  omits ProcessSubstitutionRecognizer); priorities fixed (no keyword
  recognizer exists — process_sub 160 / operator 150 / literal 70 /
  comment 60 / whitespace 30, all @property); RecognizerRegistry
  snippet fixed (register() takes no priority; method is recognize);
  constants.py row corrected; heredoc_collector.py added.
- visitor/CLAUDE.md (the one CLAUDE.md never refreshed): nonexistent
  test file replaced with the real two; traversal.py and
  analysis_helpers.py added with a visit_children example; examples
  fixed from alias-only visit_CommandList to visit_StatementList
  (dispatch uses the real class name, so the old example never fired);
  bonus defect fixed (IfConditional has no .body field).
- ARCHITECTURE.md/.llm: removed-machinery purge — §3.3/§3.6/§3.7/§3.10
  rewritten from parse_with_error_collection / RECOVER / PERMISSIVE /
  permissive() / ErrorCollector / panic-mode to the real ParserConfig
  (STRICT_POSIX/BASH_COMPAT, STRICT/COLLECT) and ParserContext
  error collection; §3.9 visualization snippet fixed to real names;
  test count 4,550+ → 4,800+ (collected: 4,878).
- M7 documented: $(case x in x) ...) is a parse error in both parsers
  (paren counting, not recursive lexing; bash accepts). Known
  Limitation #2 in ARCHITECTURE.md, code comment at the
  find_balanced_parentheses call site, user-guide ch. 6 note with the
  verified workaround $(case x in (x) ...) — leading paren form works.
- Gates: claims meta-test 39 passed; quick suite green; ruff clean.

## 0.297.0 (2026-06-11) - Docs archive sweep (reappraisal #2 Tier C, 1/2)
- 47 stale documentation files moved to docs/archive/ via git mv
  (content untouched), per the 2026-06-11 reappraisal §6 plan with
  per-file re-verification: 3 root docs (StateMachineLexer-era lexer
  docs, superseded combinator guide), 31 of 33 docs/architecture/
  files (completed parser-combinator plans/phase summaries, docs for
  removed ParserFactory/validation.py; the status doc was reclassified
  stale on verification — it documents a package layout that no longer
  exists), 4 of 5 docs/posix/ (v0.57-era analyses claiming trap/shift/
  exec are missing), 9 point-in-time quality reviews from docs/guides/.
- Kept after verification: lexer_architecture.md and
  bash_vs_psh_lexer_comparison.md (all module references check out),
  posix_spec_reference.md (timeless), combinator_parser_remaining_
  failures.md (current since its v0.276 rewrite).
- 12 surviving guides got dated staleness banners (only files with
  grep-verified stale content: pre-v0.285 module paths or removed
  RECOVER/PERMISSIVE parser modes); 17 guides verified clean, no
  banner. subsystem_internals.md paths fixed (psh/expansion/
  arithmetic.py, psh/lexer/token_types.py). 5 dangling links fixed.
- docs/architecture/ and docs/posix/ now contain only verified-current
  material. No production or test changes; suite quick-gate green.

## 0.296.0 (2026-06-11) - Slice/arithmetic unification + prune remnants (reappraisal #2 Tier B, 6/6 — TIER B COMPLETE)
- M10: `${var:offset:length}` slicing unified on one canonical engine
  in operators.py (_parse_slice_operand/_slice_elements/
  _slice_scalar_subscript) — the review found 3 copies; verification
  found a 4th (arrays.py:_expand_array_slice). The ~60-case probe
  battery exposed 8 real bash divergences, all fixed: empty-present
  length (`${a[@]:1:}` → empty), sparse arrays slice by index not
  position, resolved-negative starts (`${@: -99}` → empty, was
  clamped to everything), negative array length aborts like bash,
  out-of-range + negative length is empty without error, invalid
  arithmetic in operands aborts the command (exit 1), scalar-with-[@]
  subscript string semantics. 50 new tests pin the battery.
- Arithmetic pre-expansion scanners DELETED (~110 lines): probing
  showed evaluate_arithmetic already expands $-constructs via the
  v0.279 shared scanner, so the manager's two bespoke scanners were a
  redundant second pass — and the source of real divergences, all
  fixed by deletion: `$12` now means `${1}2` like bash (was `${12}`),
  empty values no longer 0-padded before evaluation, and variables
  holding `$(...)` text are no longer rescanned and EXECUTED by
  arithmetic (bash: syntax error). 24 new tests; 25/25 probes match.
- v0.286 parser prune finished: ErrorHandlingMode.RECOVER,
  enable_error_recovery, error_recovery_mode and the recovery method
  family removed (the review's `can_recover` is actually
  should_attempt_recovery, and base_context had one more dead
  delegate). ParserConfig's "only fields actually read" docstring is
  true again. Two test files updated; parser CLAUDE.md snippets fixed.
- Lexer smalls: DOUBLE_QUOTE_ESCAPES (dead-by-shadowing — its only
  lookup sat in an unreachable elif) deleted with its rationale
  comment moved to the live branch; both "Phase 3/4" plan codenames
  replaced with self-contained prose.
- interactive: line_editor EIO path called nonexistent
  terminal.restore() inside an except clause that also missed
  termios.error (not an OSError subclass) — fixed both; new interface
  guard test asserts every self.terminal.<attr> reference exists.
- Suite: 4,608 passed / 4,878 collected; ruff + mypy clean.

## 0.295.0 (2026-06-11) - PTY-tier repair + test debris (reappraisal #2 Tier B, 5/6)
- M8: the 6 reproducible failures in the opt-in PTY tier were NOT
  product bugs and NOT mere assertion fragility — the pty framework's
  initial-prompt sync was off by one, so every run_command returned the
  PREVIOUS command's output window (several "passing" tests passed
  spuriously on the echoed command). Fixed in pty_test_framework.py:
  sentinel prompt (PS1='PSH$ ', the proven test_pty_smoke convention),
  arithmetic-sentinel initial sync, stale-output drain per command,
  PS2 continuation handling, strip_ansi() + CR-overwrite normalization.
  No test logic changed; one stale Ctrl-C xfail removed (now passes
  deterministically). Opt-in tier: 86 passed, 0 failed × 3 runs.
- Nested tests/system/interactive/pytest.ini deleted (it hijacked
  pytest rootdir, breaking direct invocation with --run-interactive;
  its skip-comment referenced a removed README and an unused marker).
  Both invocation styles verified working.
- Debris: tracked broken-symlink conformance results git-rm'd and the
  results dir gitignored (runner recreates on demand — verified,
  162/162 POSIX); five legacy non-test files removed from
  tests/system/interactive/ (references checked; dir README updated,
  stale "can't handle escapes" known-issue dropped); empty
  tests/integration/lexer/ and untracked husk dirs removed;
  test_codex_review_findings.py docstring corrected (bugs fixed,
  no xfails remain).
- CI workflow renamed test_migration.yml → tests.yml (historical
  misnomer; `name: Tests CI` already accurate).
- Suite: 4,533 passed / 4,803 collected; PTY tier green ×3;
  ruff + mypy clean.

## 0.294.0 (2026-06-11) - Error/notification channel unification (reappraisal #2 Tier B, 4/6)
- Job-state notifications now go to stderr like bash (verified by
  pty.fork probe with the shell's own fds redirected): Done, Stopped,
  and `set -b` notices via new JobManager._notification_stream();
  the launch notice (already stderr since v0.276) uses the same helper.
  The `jobs` builtin's listing stays on stdout (command output).
- Arithmetic errors (`((1/0))`, C-style for init/cond/update) now write
  to state.stderr instead of bare sys.stderr (control_flow.py ×3,
  core.py), making them forked-child-aware like command errors.
- Builtin stragglers converted to base-class helpers preserving exact
  text/rc: function_support (declare/readonly listings, function
  printing — print+hasattr dance removed), read (error() for option
  errors), environment ("Valid options:"), help (usage), debug_control
  (14 sites to write_line). New Builtin.write_error_line() for
  unprefixed stderr diagnostics. aliases/command verified already clean.
- process_launcher: shadowing `import sys` in launch() removed;
  dangling 'SignalManager' annotation got its TYPE_CHECKING import.
- 18 new tests incl. a pty end-to-end pin that notices land on stderr
  with stdout clean, and channel pins for arithmetic/read/help errors.
- Suite: 4,533 passed / 4,803 collected; ruff + mypy clean.

## 0.293.0 (2026-06-11) - Keyword case-sensitivity (reappraisal #2 Tier B, 3/6)
- M6: shell reserved words are now matched case-sensitively like bash.
  `IF true; then echo y; fi` executed in psh (bash: syntax error);
  `FOR`/`WHILE`/`CASE`/`UNTIL`/`SELECT` likewise (uppercase SELECT even
  hung on stdin). Now: uppercase keywords are ordinary words — lone `IF`
  → command not found rc 127, `IF=3; echo $IF` → 3, mid-construct
  uppercase (`THEN`, `ELIF`, `IN`) → syntax error, all matching bash.
- Folding removed at every keyword site: keyword_normalizer.py (KEYWORDS
  lookup + _next_command_position), keyword_defs.py matches_keyword_type
  / matches_keyword / KeywordGuard (this one fix covers the entire
  combinator parser — all its keyword checks funnel through
  matches_keyword), token_types.py normalized_value (now a no-op).
  The rd parser needed no change (it matches token types, which the
  normalizer now only assigns to exact-lowercase words). Non-keyword
  case handling (unicode opt-in identifiers, hex, ${var,,}) untouched.
- Zero existing tests pinned the old behavior (swept). 10 new lexer
  unit tests + 6 conformance tests (~20 commands) in
  tests/conformance/bash/test_keyword_case_conformance.py.
- Suite: 4,515 passed / 4,785 collected; ruff + mypy clean.

## 0.292.0 (2026-06-11) - io_redirect: exec single-open, noclobber, dual-universe docs (reappraisal #2 Tier B, 2/6)
- Triple-open in apply_permanent_redirections fixed: `exec &>file` (and
  `>`, `>>`, `>|`, `2>file`) opened up to three independent file objects
  with separate offsets, so builtin and external output overwrote each
  other (`exec >f; echo b1; /bin/echo e1; echo b2` lost b1). All output
  branches now do a single fd-level open + dup2, then rebind sys.stdout/
  stderr via os.fdopen(os.dup(fd), buffering=1) — one shared open file
  description, line-buffered for bash-like interleaving. 17 probes match.
- noclobber now blocks `>` only for existing regular files (and dangling
  symlinks, matching bash's O_EXCL EEXIST); devices and FIFOs are
  exempt — `set -o noclobber; echo x 2>/dev/null` works again.
  Rule verified by probe across all four enforcement paths.
- The builtin-redirection "dual universe" (Python stream swap for fds
  1/2, real dup2 for fd>=3) was deliberately KEPT — unification is not
  viable because builtin output may target non-fd-backed streams
  (StringIO under test capture) — but the 120-line function is now a
  ~25-line dispatcher over five named, docstringed helpers with a
  module-level design explanation; first-touch-wins backups extracted
  into an explicit _BuiltinStreamSnapshot. Rollback semantics unchanged.
- io_redirect/CLAUDE.md refreshed: expansion-in-targets table corrected,
  real debug output, pitfall #7 rewritten for the v0.288 procsub scope
  mechanism, new two-universes and exec single-open sections.
- 31 new tests (15 subprocess exec tests, 10 noclobber targets,
  6 predicate units).
- Suite: 4,499 passed / 4,769 collected; ruff + mypy clean.

## 0.291.0 (2026-06-11) - alias/unalias rewrite + printf \e (reappraisal #2 Tier B, 1/6)
- M3: aliases.py rewritten to the builtins conventions (the one file the
  v0.284 sweep never reached). `alias -p` supported; invalid options now
  rc 2 with a usage line via parse_flags; output uses bash's `'\''`
  quoting for embedded single quotes; `unalias` with no args rc 2;
  `alias -- x=v` works; raw print + hasattr dance replaced with
  write_line()/error(). 37-case probe battery matches bash 5.2.
- The cross-argument quote-rejoin scanner was live but WRONG in every
  reachable case, not dead as the review guessed: it stripped quotes
  bash keeps literal (`alias x="'echo hi'"`) and glued separate operands
  (`alias x=\'foo bar\'` — bash defines `x`=`'foo` and errors on
  `bar'`). Deleted; operands are now independent, matching bash.
  Bash source quirks replicated: `-p` with empty table returns 0 and
  skips operands; `unalias -a` ignores operands; `=foo` is a lookup.
- printf now interprets `\e`/`\E` (escape) in its format string — added
  to printf's own escape dialect in io.py, not the shared echo dialect
  (which already had it; `$'\e'`, `echo -e '\e'`, `printf '%b'` were
  already correct).
- 33 new tests (29 alias/unalias conformance, 4 printf escapes).
- Suite: 4,469 passed / 4,739 collected; ruff + mypy clean.

## 0.290.0 (2026-06-11) - Test-runner hole + user-guide truth sweep (reappraisal #2 Tier A, 3/3 — TIER A COMPLETE)
- H2: run_tests.py no longer silently skips 45 tests. The whole-file
  ignores of test_function_advanced.py and test_variable_assignment.py
  (obsolete since the v0.195.0 subshell fd fix) are removed and the
  2-test Phase 3 deleted; both files verified xdist-safe (4× under
  -n 4, no serial markers needed). CI (--quick) now runs them too.
- Two stale xfails fixed in test_function_advanced.py:
  test_function_with_background_job xpassed (marker deleted);
  test_function_with_here_document's feature works — the test was
  rewritten to file redirection per the project's capture rules.
- H3: user-guide truth sweep — every limitation note re-probed against
  bash and current psh (~30 probes). 17 false "not supported" claims
  corrected (`!` negation, `|&`, PIPESTATUS, `exec 3<>`, fd swaps, `>|`,
  five bitwise assignment ops, BASH_REMATCH ×3, `[[ ! ]]`,
  read -n/-t/-s, `${!prefix*}`, `${!varname}`, `${@:off:len}`,
  `${array[@]#pat}`, $'\NNN' octal, $"...").
  10 still-true limitations kept and unversioned (csh `>& file`,
  `<< \EOF`, `~+`/`~-`, `$(< file)`, multi-line declare -A init,
  bind, wait -n, extglob `@()`, printf "%d" "'A", read -u).
  All "PSH v0.187.1" pins removed (grep-clean);
  docs/user_guide/README.md now version-agnostic at ~98%.
- 23 new conformance tests (tests/conformance/bash/
  test_user_guide_notes_conformance.py) pin the corrected claims that
  had zero prior conformance coverage; claims meta-test green.
- Suite: 4,436 passed / 4,706 collected (+68: 45 reclaimed + 23 new);
  ruff + mypy clean.
- Side findings recorded for follow-up: noclobber wrongly blocks
  redirects to existing device files (`2>/dev/null` under
  `set -o noclobber`; bash exempts non-regular files); psh printf
  doesn't interpret `\e` (bash does).

## 0.289.0 (2026-06-11) - Behavior-bug batch (reappraisal #2 Tier A, 2/3)
- M1: associative-array keys containing `,` or `^` now expand:
  `declare -A a; a[x,y]=hi; echo "${a[x,y]}"` → `hi` (was empty). Two-part
  root cause: variable.py excluded any `${...}` containing case-mod chars
  from the subscript path, AND parse_expansion's case-mod scan split at
  `,`/`^` inside `[...]`. Fixed with a structural `_is_plain_subscript()`
  check (balanced-bracket, handles nested `arr[arr[0]+1]`) and a bracket
  guard in the operator scan. `${a[x,y]^^}` and all case-mod forms
  (`${v^^}`, `${v^^[a-m]}`, `${arr[@]^^}`) verified against bash.
  18 new tests (test_assoc_array_special_keys.py).
- M2: `command -v`/`-V` now finds aliases, keywords, functions, and
  builtins in bash's lookup order with bash output formats (`-v`: alias
  definition line / name / path; `-V`: "is a function" + body via the
  shared ShellFormatter, "is aliased to", "is a shell builtin/keyword")
  and bash rc semantics (multi-name rc 0 if any found; `-v` silent rc 1
  on miss; bare `command` rc 0). The hardcoded `bash: type:` error prefix
  is gone; raw prints converted to write_line()/error() per convention.
  PATH probing shared with type via TypeBuiltin._find_in_path.
  19 new tests (test_command_builtin.py).
- M4: deleted four dead `set -o` options (validate-context,
  validate-semantics, analyze-semantics, enhanced-error-recovery) from
  core/state.py and `set` help — zero consumers (orphaned by the v0.286
  parser pruning); they now error rc 2 like any unknown option. 4 tests.
- M5: command-not-found inside a pipeline now prints
  `psh: name: command not found` and exits 127 (non-executable → 126)
  instead of a raw Python OSError with the PATH-probe path. Extracted
  module-level report_exec_failure() shared by the inline-exec and fork
  paths; pipeline diagnostics byte-identical to single-command ones.
  5 subprocess tests (test_pipeline_exec_errors.py).
- Suite: 4,368 passed / 4,683 collected; ruff + mypy clean.

## 0.288.0 (2026-06-11) - Process-substitution fd/zombie reaping (reappraisal #2 Tier A, 1/3)
- Fixed (high severity, found by the second ground-up reappraisal): process
  substitutions used by external commands leaked parent-side fds and left
  zombie children for the life of the session — `IOManager.
  cleanup_process_substitutions` had ZERO callers and `shell._process_sub_fds/
  _process_sub_pids` were written but never read. Three `cat <(echo x)`
  commands left three `<defunct>` children; bash leaves none.
- Design: scoped LIFO ownership on ProcessSubstitutionHandler. `scope()`
  (via `io_manager.process_sub_scope()`) closes only the fds registered
  inside the scope on exit and moves its pids to a pending list polled with
  `os.waitpid(pid, WNOHANG)` — specific pids only, never -1, so JobManager
  statuses can't be stolen. Still-running children (`echo >(sleep 3)`) are
  parked and reaped opportunistically by later commands, matching bash.
  The dead method and dead shell attributes were deleted, not wired — the
  blanket-cleanup semantics they implied were themselves wrong (see below).
- Two additional latent bugs fixed by the same design (both bash-verified):
  `echo >(sleep 3)` blocked ~3s (blocking waitpid in the builtin-restore
  path; bash returns immediately), and `f() { cat "$1"; }; f <(echo a)`
  failed with "Bad file descriptor" (any builtin's restore blanket-closed
  ALL active procsub fds, including the enclosing function call's).
- Redirect-target procsubs (`< <(cmd)`) now close the parent fd eagerly
  after dup2, with a guard for the fd-number-collision case
  (`exec 3< <(cmd)` where the pipe end happens to be fd 3).
- Wire points cover all consumers: CommandExecutor.execute wraps every
  simple command; IOManager.with_redirections wraps compound/function
  redirects; `[[ ]]` redirects now route through with_redirections
  (shell.execute_enhanced_test_statement simplified).
- 13 new tests in tests/integration/redirection/test_process_sub_cleanup.py
  (zombie census, fd-slot census, non-blocking timing, opportunistic reap,
  and output-correctness pins incl. function args, `exec 3< <(...)`,
  `tee >(...)`); the four defect tests fail on unfixed main.
- Suite: 4,323 passed / 4,638 collected; ruff + mypy clean.
- Also adds docs/reviews/ground_up_reappraisal_2026-06-11.md — the second
  ground-up reappraisal memo (six-agent review; scorecard, findings H1-H3
  and M1-M10, three-tier follow-up program).

## 0.287.0 (2026-06-11) - Mypy adoption + interactive unit tests (reappraisal Tier C, 3/3 — REAPPRAISAL PROGRAM COMPLETE)
- Type checking is now enforced: `[tool.mypy]` in pyproject.toml (3.12,
  non-strict, files-driven scope) covering psh/core/ (8 modules),
  ast_nodes.py, version.py, and the pure showcases
  expansion/pattern.py / utils/escapes.py / interactive/line_layout.py —
  14 files, zero issues. The 5 errors mypy found were FIXED with real
  annotations (an implicit-Optional in trap_manager; a None-sentinel loop
  in scope.py refactored to a typed Optional branch) — no `# type: ignore`
  anywhere. CI's lint job runs mypy; CLAUDE.md documents the
  grow-the-scope convention.
- The interactive layer finally has fast in-process unit tests: 76 new
  tests in tests/unit/interactive/ (xdist-safe, 0.07s total, no PTY):
  - line-editor buffer ops (insert/delete boundaries, kill/yank
    round-trips, transpose, word motion, history navigation preserving
    the in-progress line, undo/redo — including a documented dedupe
    quirk in the redo stack)
  - the v0.283 escape reader fed synthetic byte streams: every CSI/SS3
    variant, unknown-sequence full consumption (nothing leaks as typed
    text), EOF mid-sequence, vi bare-ESC vs sequence via the mockable
    `_input_pending` probe
  - completion candidates against tmp_path fixtures (partial/unique/
    dir/hidden/subdir), find_word_start quote/operator cases, tab-apply
    paths with space escaping. One test documents that command-position
    completion does not exist (CompletionEngine is purely path-based) —
    an honest feature gap, not a regression.
- tests/unit/interactive/ exempted from the PTY skip-by-default marker
  (these tests are terminal-free).
- Full suite green: 4,310 passed / 4,625 collected (+76).
- This closes the ground-up reappraisal program
  (docs/reviews/ground_up_reappraisal_2026-06-10.md): Tier A
  v0.275–v0.278, Tier B v0.279–v0.284, Tier C v0.285–v0.287 —
  13 releases across every recommendation, with each inaccurate review
  claim verified and documented rather than blindly executed.

## 0.286.0 (2026-06-11) - Parser pruning + subsystem CLAUDE.md refresh (reappraisal Tier C, 2/3)
- Dead rd-parser error-recovery machinery deleted after a reachability
  audit: `parse_with_error_collection` / `MultiErrorParseResult` /
  `_try_statement_recovery` and their private support had no production
  caller (--validate runs a normal parse; the parser-config builtin's
  option never reached ParserConfig). Their 14-test file went with them.
  The review's claim that ErrorContext.suggestions was dead proved WRONG —
  it's populated by ParserContext and user-visible in error output; kept.
  Also deleted: `error_code`, `related_errors`, `add_suggestion`,
  `show_error_suggestions`, ParsingMode.EDUCATIONAL/PERMISSIVE,
  `permissive()`. ParserContext-level error collection (the live library
  surface) remains.
- Vestigial AST quote-type fields audited (the removed arg_types pattern
  by another name): all five field groups traced to real consumers in
  expansion/execution semantics — converting them is Word-AST migration
  work, not pruning. Each is now marked legacy-pending-migration at the
  definition; `BinaryTestExpression.left_quote_type` found to have ZERO
  consumers and flagged as a removal candidate. Stale "dual
  Statement/Command types" comment fixed.
- Parser error messages standardized on lowercase "syntax error" (bash's
  style; one golden-case pin updated after bash verification);
  `_raise_unclosed_expansion_error` renamed `_raise_syntax_error` (it was
  used for generic syntax errors); the 25-line backslash-parity scanner
  in parse_pipeline_component extracted into a documented helper;
  pure-delegation `parse_command_list_until_top_level` inlined away.
- Five subsystem CLAUDE.mds verified claim-by-claim against current code
  and refreshed (expansion, parser, core, builtins, interactive): ~32
  corrections (wrong APIs, phantom components, stale tables/samples) and
  ~13 new short sections for v0.266–v0.285 machinery (expansion mixins +
  pattern.py, ${!name}, PATSUB_MATCH, namerefs + tombstones, PshError
  family, parse_flags + error-channel conventions, the line editor and
  its centralized escape parser, history single-writer, entry-point-only
  signal setup).
- Net −108 lines of dead parser machinery (+docs). Full suite green:
  4,234 passed / 4,549 collected (−15: the deleted dead-surface tests).

## 0.285.0 (2026-06-11) - Top-level module relocation + scope rename (reappraisal Tier C, 1/3)
- The 19 orphan top-level modules (15% of the tree) moved into their
  packages via `git mv`, so the layout finally matches the documented
  architecture. Top level is now exactly: shell.py, __main__.py,
  ast_nodes.py, version.py (+ __init__.py).
  - lexer/: token_types.py, token_stream.py, token_transformer.py
  - expansion/: arithmetic.py, brace_expansion.py, aliases.py
  - executor/: job_control.py
  - core/: functions.py
  - scripting/: input_sources.py, input_preprocessing.py
  - interactive/: line_editor.py, line_editor_helpers.py, line_layout.py,
    tab_completion.py, prompt.py, keybindings.py, multiline_handler.py,
    history_expansion.py
- No compatibility shims (pre-1.0 educational software; this entry is the
  record). 87 psh/ files + 31 test files had imports rewritten by a
  resolution-aware script (relative imports resolved to absolute targets
  first, so the parser's own local functions.py/arithmetic.py were
  correctly untouched). No string/importlib references existed.
- One import cycle surfaced and was fixed at the root: executor modules
  imported FunctionReturn from psh.builtins (a re-export), creating
  builtins → executor → builtins at startup once job_control moved.
  Executor now imports it from its true home, core.exceptions, severing
  the executor → builtins import-time edge entirely.
- `core/scope_enhanced.py` renamed to `core/scope.py` and
  `EnhancedScopeManager` to `ScopeManager` — there was never a
  non-enhanced version to be enhanced relative to. Full reference update,
  no alias kept (only 4 files referenced it).
- ~26 doc path references updated (ARCHITECTURE.md/.llm component tree,
  seven subsystem CLAUDE.mds).
- Pure relocation: zero behavior change; full suite green at exact
  baseline (4,249 passed / 4,564 collected), PTY smoke 34/34.

## 0.284.0 (2026-06-11) - Builtins consistency (reappraisal Tier B, 6/6 — Tier B complete)
- Option parsing converged selectively (not blindly): `type` converted to
  the shared parse_flags helper, fixing 3 bash-pinned divergences
  (clustered `type -af` accepted; `type -` is an operand, rc 1; invalid
  option message + rc 2 + bare `type` rc 0). `jobs` converted alongside
  the `jobs -l` work. Deliberately NOT converted, each verified: declare
  (needs `+x` removal flags — its custom parser instead table-driven,
  98 → 60 lines, identical semantics), getopts (the "122-line parser" IS
  the POSIX getopts semantics, not self-option parsing — review claim
  inaccurate), cd (parses no options today; conversion would invent
  errors), test/[ (positional expression syntax), read/echo (pinned).
- Error channels unified: 33 raw `print(file=sys.stderr)` sites converted
  to the forked-child-aware `self.error()` / `self.write_line()` —
  type (the 12× hasattr-stdout dance), kill (14), fg/bg/wait, source,
  return, trap, set, debug_control. Three messages improved to bash's
  shape along the way (`.`/source filename-required, kill usage, trap
  usage).
- unset's inline subscript parsing and "looks arithmetic" heuristic
  replaced by the canonical `_eval_array_index` path (v0.279.0). An
  11-probe bash battery now matches exactly, fixing 4 divergences:
  `unset 'a[-1]'` removes the last element; out-of-range negative reports
  "bad array subscript" rc 1; scalar `x[0]` unsets x; missing-array
  unset is silent rc 0.
- `jobs -l` implemented (the last honest TODO in builtins), bash-pinned:
  `[1]+ 12345 Running   sleep 10 &`; pipeline jobs list extra PIDs on
  continuation lines; `-p` wins over `-l` as in bash.
- env builtin: review's "doing executor work" claim was stale — the fd
  juggling was already in named private methods; docstrings expanded to
  explain WHY env must dup2 process-level fds (forked grandchildren
  inherit fds, not Python stream objects). `set` help no longer lists
  the nonexistent enhanced-parser options.
- 18 new bash-pinned tests (type ×6, unset ×10, jobs -l ×2). Full suite
  green: 4,249 passed / 4,564 collected.

## 0.283.0 (2026-06-11) - Interactive/line-editor cleanup (reappraisal Tier B, 5/6)
- Vi-mode arrow keys fixed: CSI parsing lived only in the emacs branch, so
  in vi insert mode an Up-arrow became ESC→normal-mode + stray 'A' →
  append-at-end, corrupting the edit state. Escape handling is now
  centralized ABOVE the mode split: `_read_escape_sequence` is the single
  input-side ANSI parser, yielding symbolic keys ('up'...'delete') that one
  shared table maps identically in emacs and both vi modes (bare ESC vs
  sequence distinguished via a 50ms pending probe — terminals send
  sequences in one burst). Also fixed a pre-existing gap the work exposed:
  `set -o vi` never reached the live LineEditor (mode was frozen at REPL
  setup); the editor now syncs from state.edit_mode per read. 5 vi-mode
  PTY tests added.
- History single-writer: both LineEditor.read_line and source_processor
  recorded history (multiline commands landed as physical lines AND the
  joined form). source_processor is now the sole writer (recording before
  parse so syntax errors stay recallable, as bash does); multiline
  commands store as ONE joined entry (`for i in 1; do echo $i; done`)
  while quoted newlines stay verbatim — both PTY-pinned against real
  bash. The vestigial `import readline` history mirror is gone. 3 history
  PTY tests added.
- Dead DSR machinery deleted: `_prompt_draw_row` was written but never
  read (redraw uses pure line_layout math), and `_query_cursor_row` +
  `_drain_stale_cpr` existed only to feed it — psh no longer writes
  ESC[6n at all, removing a whole class of PTY races.
- `__main__.main` (~279 lines) decomposed: data-driven `parse_args()` +
  `print_help()` (help output diff-identical); main() is ~115 lines of
  orchestration. Flag battery verified (-c, --norc, piped stdin, -i,
  --parser=X, --validate, --debug-ast=compact, --version, error exits).
- `TerminalManager` moved from tab_completion.py to its natural home,
  psh/interactive/terminal.py (re-exported for compatibility).
  read_builtin's raw-mode block deliberately NOT unified: it operates on
  an arbitrary fd (redirected stdin, read -u) with an explicit echo flag —
  different semantics, now documented.
- Minor: CompletionEngine.find_word_start public (alias kept);
  line_layout imports hoisted; stale base.py comment fixed.
- line_editor.py 1089 → 1061 lines; __main__.py 291 → 258. Full suite
  green: 4,231 passed / 4,546 collected (8 new PTY tests).

## 0.282.0 (2026-06-11) - Executor cleanup + signal-loss race fix (reappraisal Tier B, 4/6)
- THE RACE, root-caused — and it wasn't where the reappraisal guessed.
  `sleep 5 & kill %1 && wait %1` intermittently reported rc=0 instead of
  143 under load (11/320 in a parallel stress harness). Suspected
  wait_for_job bookkeeping was innocent: failing runs took the full 5s —
  the SIGTERM was being LOST. A signal delivered in the child's fork→exec
  window was consumed by the inherited Python-level trap handler and
  discarded across exec(), so sleep never received it. Fix:
  ProcessLauncher blocks SIGTERM/SIGINT/SIGHUP/SIGQUIT across fork
  (pthread_sigmask; parent restores immediately); the child unblocks only
  after apply_child_signal_policy resets handlers to SIG_DFL, so a
  window signal stays kernel-pending and kills the child with the right
  status; SIGTERM/SIGHUP added to reset_child_signals (children must not
  inherit trap handlers — bash semantics). Stress: 960/960 clean after
  (0/320 before-fix failures remained); 30× bash-pins rc=143 and rc=5.
  wait_for_job additionally hardened (ECHILD distinguished and orphaned
  processes marked completed so the stored-status fallback always runs;
  EINTR retried). 3 regression tests added
  (tests/integration/job_control/test_kill_wait_race.py, auto-serial).
- `JobManager.launch_background(pgid, command, processes)` extracted: the
  create-job/add-process/register/notice block was duplicated across 6
  sites (strategies.py ×3, subshell.py ×2, pipeline.py). The notice is
  unified on bash's format — PTY-verified that bash prints the LAST
  process's pid (== $!), not the pipeline leader's pgid, which
  pipeline.py had been printing.
- CommandExecutor.execute (191 lines) split: `_strip_backslash_bypass()`
  and `_handle_execution_error()` extracted; execute() reads as the
  orchestration narrative.
- Near-duplicate code factored: the ~40-line builtin exception policy
  shared by Special/regular builtin strategies → `execute_builtin_guarded()`;
  the two WIFEXITED blocks in wait_for_job → `exit_status_from_wait_status()`
  (builtins' `_extract_exit_status` delegates).
- Dead code removed: `process_metrics` hooks (object never created),
  `_execute_pipeline` indirection; function.py "Phase 7" docstring fixed.
- All 20 opaque plan-codename comments (H3/H4/H5/C1...) replaced with
  self-contained explanations; `job.state.name == 'DONE'` string compare
  → JobState enum; error output unified on state.stderr where equivalent.
- Full suite green: 4,223 passed / 4,538 collected (3 new race tests).

## 0.281.0 (2026-06-11) - Lexer cleanup (reappraisal Tier B, 3/6)
- literal.py's quadratic string-archaeology fixed — but not the way the
  review prescribed: instrumentation proved `_is_inside_array_assignment`
  and the lexer-level array-assignment map are NOT equivalent (the helper
  fires for glob char-classes like `*[[:upper:]]*`, which the map can't
  represent). The per-character full re-scan is replaced by an incremental
  `_ArrayAssignmentTracker` running the identical quote-aware bracket
  automaton — O(n) by construction, zero behavior change. A 128k-char word
  lexes in 0.079s vs 0.202s (now linear). The forward-lookahead helpers
  (`_is_potential_array_assignment_start`, `_collect_array_assignment`)
  are genuinely needed and kept; the rare-trigger value scans kept.
- Dead config flags deleted: 12 never-set `enable_*` flags removed from
  LexerConfig along with their 8-branch feature-disable ladders in
  literal.py (including 13 unreachable lines) and operator.py
  (`_is_operator_enabled` deleted whole). `enable_extglob`, `posix_mode`,
  and `case_sensitive` kept (really used). ProcessSubstitutionRecognizer
  registered unconditionally.
- Duplication removed: comment-start logic unified on one module-level
  `is_comment_start()` (the wider set in comment.py was provably
  unreachable — LiteralRecognizer outprioritizes it; bash-verified);
  backtick parsing deduplicated (quote_parser delegates to
  ExpansionParser; the contract difference on unclosed backticks is
  unobservable since an enclosing unclosed quote errors first);
  `_parse_fd_duplication` 93 → 56 lines via a shared tail helper.
- Dead code deleted (zero production callers, verified):
  `parse_simple_quoted_string`, `extract_quoted_content`,
  `get_operator_type`, `_is_identifier`, `pure_helpers.is_comment_start`,
  `WORD_TERMINATORS`/`WORD_TERMINATORS_IN_BRACKETS` constants,
  `create_expansion_parser`, registry test-only surface (`unregister`,
  `get_stats`, `default_registry`, `setup_default_recognizers`), orphaned
  `QuoteParsingContext` and `_create_error_part`. 15 tests that pinned
  only the deleted surface were removed; registry tests rewritten against
  the production-built `ModularLexer.registry`.
- Fragilities documented in place (PARAM_EXPANSION substring
  classification, silent unmatched-char drop); `heredoc_already_collected`
  initialized before its loop (latent NameError trap).
- Lexer package 4,913 → 4,448 lines (−588 net with tests). Full suite
  green: 4,220 passed / 4,535 collected (15 dead-surface tests removed).

## 0.280.0 (2026-06-10) - Pattern/escape/exception consolidation (reappraisal Tier B, 2/6)
- ONE pattern engine: new `expansion/pattern.py` is the canonical home of
  `PatternMatcher` + module-level `match_shell_pattern()`. The two fnmatch
  paths are gone: `case` legacy matching (control_flow.py's
  `_match_case_pattern` + the 65-line `_convert_case_pattern_for_fnmatch`
  heuristic, deleted) and `[[ == ]]` (`enhanced_test_evaluator._pattern_match`)
  both delegate to the shared engine, so case / `[[ ]]` / `${var#pat}` can
  no longer drift. parameter_expansion.py re-exports PatternMatcher for the
  existing import sites.
- Real bug fixed by the consolidation: the shared glob→regex converter's
  bracket scanner stopped at the first `]`, so POSIX classes
  (`[[ a == [[:alpha:]] ]]`, `case B in [[:upper:]])`, `${x#*[[:digit:]]}`)
  only worked in the constructs that still used fnmatch. The converter now
  scans `[:name:]` correctly and translates POSIX classes to re ranges —
  verified against bash across all constructs (8-probe battery).
- New `utils/escapes.py` houses the shared escape/quote helpers with the
  dialect map documented: `process_echo_escapes` (echo -e/print),
  `quote_printf_q` (printf %q: `a\ b`), `quote_at_q` (${var@Q}: `'a b'`).
  The two quoters were flagged as duplicates by the review but produce
  deliberately different formats in bash itself (verified) — consolidated
  by location and documentation, not falsely unified. printf/read/[[ ]]
  escape dialects remain in place, each documented as intentionally distinct.
- Exception hierarchy rooted: new `PshError` base in core/exceptions.py;
  ShellArithmeticError, BraceExpansionError, LexerError, ParseError,
  PrintOptionError, ExpansionError, UnboundVariableError,
  ReadonlyVariableError, NamerefCycleError all derive from it (callers can
  finally catch "any psh error"). `FunctionReturn` moved to
  core/exceptions.py beside its control-flow siblings LoopBreak/LoopContinue
  — the control-flow family deliberately does NOT derive from PshError, and
  the module docstring explains why. function_support.py re-exports
  FunctionReturn for existing importers.
- Full suite green at unchanged counts (4,235 passed / 4,550 collected).

## 0.279.0 (2026-06-10) - expansion/variable.py decomposition (reappraisal Tier B, 1/6)
- The 1,644-line `expansion/variable.py` grab-bag — the worst file in the
  reappraisal — is decomposed by concern into four mixins, with
  `VariableExpander` as the facade (no call-site changes anywhere):
  - `arrays.py` (307 lines) — subscripts, slices, lengths, array assignment
  - `operators.py` (352) — ${var<op>operand} operator application
  - `operands.py` (238) — pattern/replacement operand mini-expansion
  - `fields.py` (133) — multi-field expansion (${arr[@]}, $@ with operators)
  - `variable.py` (382) — entry points, name resolution, specials, ${!name}
- The six copy-pasted array-element resolution blocks (the
  eval-index-with-ArithmeticError→0 dance, plus 10 repeated local arithmetic
  imports) are replaced by one canonical `_eval_array_index()` helper with
  the bash subscript rule documented once.
- `expand_string_variables` (118 lines) rewritten as a thin wrapper over
  `_expand_one_dollar` — the shared $-scanner also used for operator
  operands — so recognized constructs can't drift between contexts; only
  the double-quote escape rules remain in the wrapper (~70 duplicated
  lines gone). The two arithmetic-context scanners in manager.py were
  examined and deliberately NOT unified: arithmetic substitutes value
  *text* (empty→0, recursively evaluable), a genuinely different rule set.
- `_glob_escape` renamed to public `glob_escape` (manager.py was using it
  cross-class as a de-facto API).
- Pure refactor: zero behavior change intended; full suite green at the
  same counts (4,235 passed / 4,550 collected).

## 0.278.0 (2026-06-10) - Meta-documentation sweep (reappraisal Tier A, 4/4 — Tier A complete)
- ARCHITECTURE.md: sections describing removed subsystems deleted or repointed
  (parser validation/SemanticAnalyzer → psh/visitor/ validators; ParserFactory,
  ParserContext profiler, dead config fields pruned); brace-expansion location,
  heredoc implementation (FileRedirector, not a heredoc.py), combinator file
  list, recognizer list, and scope module name corrected; ~93% POSIX claim
  reconciled with README's ~98%; "3,400+ tests" → 4,550+; two fixed issues
  removed from Known Limitations; ~60 lines of v0.103/v0.104 ProcessLauncher
  release archaeology collapsed to a present-tense description + CHANGELOG
  pointer; stale exact line counts dropped.
- ARCHITECTURE.llm: file map rewritten against the real tree (10+ deleted
  files removed: pipeline/builder.py, six purged lexer modules,
  parser/validation/, support/factory.py, io_redirect/heredoc.py,
  executor/test_evaluator.py); recipes and quick-reference repointed to the
  current locations instead of deleted ones; testing conventions point at the
  real tests/ layout; subshell `-s` limitation removed.
- README.md: false "trap builtin not yet implemented" claim replaced with the
  real gaps (RETURN traps; history word designators/modifiers — `!!`/`!n`
  themselves ARE supported); broken TODO.md link fixed; Built-in Commands list
  regenerated from the registry (59 builtins, grouped); LOC claim recomputed
  with a stated basis (~47.7k production / ~53.6k tests); Recent Development
  trimmed from ~80 bullets to the last 10 versions + CHANGELOG pointer; test
  statistics refreshed (4,235 passing); nonexistent run_tests.sh reference
  fixed; Python 3.12+ requirement stated.
- Root CLAUDE.md: stale "Version: 0.237.0" line replaced with a pointer to
  psh/version.py (numbers there go stale); duplicated v0.195.0 subshell notes
  collapsed to one sentence; "NEW in v0.103.0" dropped; the bash-verification
  probe workflow and the branch/merge/tag release workflow are now documented.
- Subsystem CLAUDE.md API corrections (executor, io_redirect): ProcessLauncher
  .launch signature fixed (execute_fn, config) -> (pid, pgid) with caller-owned
  job registration; ProcessRole values corrected; CommandExecutor/
  PipelineExecutor method names fixed; fork-path table corrected to the real
  3 paths; I/O integration section now names the real IOManager API; heredoc/
  here-string docs now describe the deliberate unlinked-temp-file design (not
  a pipe); test paths fixed; enhanced_test_evaluator.py added to key files.
- docs/ top level decluttered: 33 completed plans, dated analyses, and one-off
  summaries moved to docs/archive/ — what remains at top level is current
  reference material (guides, test docs, user_guide/, reviews/, architecture/).
- AGENTS.md: legacy conformance_tests/ reference fixed; stale subshell `-s`
  guidance corrected. Leftover empty conformance_tests/ dir removed.
- Known flake recorded: tests/conformance/posix/...::test_wait_after_kill_
  reports_signal_status failed once under xdist load (psh reported rc=0 vs
  bash's 143 — a job-status bookkeeping race in wait_for_job's ECHILD path);
  not reproducible in 70 standalone/loaded attempts, passes in re-runs.
  Follow-up tracked for the Tier B executor work.

## 0.277.0 (2026-06-10) - Test-tree cleanup (reappraisal Tier A, 3/4)
- Legacy trees deleted: root `conformance_tests/` (123 files — a second,
  golden-file conformance system superseded by the live psh-vs-bash suite in
  tests/conformance/, including tracked debug junk), `contract_tests_draft/`
  (unreferenced; scenarios duplicated by test_pty_smoke.py and the fd/jobs
  conformance tests), dead `tests/framework/conformance.py` and `base.py`
  (zero importers; interactive.py/pty_test_framework.py kept — still used),
  and four empty dirs.
- Before deleting, the five feature areas only the legacy tree covered were
  folded into the live suite as 30 new conformance tests
  (posix/test_source_cd_scripts_conformance.py): source/., cd semantics,
  backslash-newline line continuation, declare -i/-l/-u/-r/-x, and real
  script-file execution ($0, ${10}, exit codes, ENOEXEC, noexec perms).
- The fold-in probes uncovered and fixed TWO REAL BUGS (bash-pinned):
  - cd used os.environ instead of the HOME/OLDPWD *shell variables* —
    `HOME=/x; cd` went to the real home, and bare `cd` with HOME unset
    silently went to / instead of erroring (bash: "cd: HOME not set", rc 1).
  - psh lacked the POSIX ENOEXEC fallback: an executable text file without
    a shebang failed with "Exec format error" (rc 126) instead of being run
    as a shell script. exec_external() in executor/strategies.py now re-execs
    such files through psh, with PATH-correct resolution.
- Conformance framework now pins LC_ALL=C/LANG=C in run_in_shell so sort
  order, error text, and glob ranges can't drift by machine.
- Fixed-`/tmp` paths removed from 7 test files (xdist collision risk and a
  violation of the project's own tmp/ rule) — converted to temp_dir/tmp_path
  fixtures; test_pushd_logical_paths now reads PWD from captured stdout.
- Stale test metadata corrected: "History/Tab completion not implemented yet"
  xfail reasons rewritten honestly (the features exist; those tests feed
  non-interactive stdin which cannot exercise them); the
  isolated_shell_with_temp_dir docstring no longer warns about the `-s` flag
  (fixed in v0.195.0); reset_environment's hardcoded env-var list dropped
  (superseded by the _restore_os_environ autouse fixture, now cwd-only).
- References updated: AGENTS.md and the CLAUDE.md development principle now
  name `tests/conformance/` explicitly, and the principle documents the
  enforcing claims meta-test.

## 0.276.0 (2026-06-10) - Behavior bugs from the reappraisal (Tier A, 2/4)
- read builtin: option parsing rewritten getopt-style, pinned to bash with a
  17-probe battery. Fixes: combined options no longer abandon the option loop
  (`read -rs -p "" x` and `read -rs y x` lost everything after the cluster —
  the cluster even became a *variable name*); attached option values now work
  (`-rn3`, `-rp prompt`); `--` ends options; `read -n 0` reads nothing and
  succeeds (was rc 1); invalid option *values* exit 1 while invalid options
  exit 2, matching bash's distinction.
- Background-job notices: the three `[N] pid` sites in executor/strategies.py
  printed to stdout; now stderr, consistent with pipeline.py/subshell.py and
  bash.
- Last pytest sniff removed from production code: expansion/command_sub.py
  gated child-stdin protection on PYTEST_CURRENT_TEST; replaced with a real
  capability check (`os.isatty(0)` — only protect stdin when it actually is
  the terminal).
- Combinator parser drift fixed (found by the reappraisal, regressions from
  rd fixes in v0.266–v0.269): function-definition trailing redirects now
  attach to FunctionDef and apply per call in all three definition forms
  (was: applied at definition time); case patterns now carry per-part quote
  context via Word AST (was: quoted glob chars stayed active, so
  `case ab in "a*")` wrongly matched).
- New tests: tests/unit/builtins/test_read_option_parsing.py (13) and
  tests/integration/parser/test_combinator_parity_regressions.py (9,
  three-way bash/rd/combinator parity). Suite: 4,520 collected, 4,205 passed.
- docs/guides/combinator_parser_remaining_failures.md: stale "0 failures as
  of v0.171.0" replaced with an honest drift caveat and the parity-test
  convention for future rd fixes.

## 0.275.0 (2026-06-10) - Packaging truth + whole-tree lint hygiene (reappraisal Tier A, 1/4)
- Packaging now tells the truth about Python support: `requires-python = ">=3.12"`
  (the tree already required 3.12 in fact — a PEP 701 nested-quote f-string in
  `visitor/debug_ast_visitor.py` is a SyntaxError on 3.11 and below); classifiers
  trimmed to 3.12–3.14; ruff `target-version` bumped py38 → py312.
- Whole production tree and test tree are now ruff-clean: 36 violations in `psh/`
  (27 unused imports, 9 unsorted import blocks) and 50 in `tests/` auto-fixed;
  one F841 fixed by strengthening the test to assert the exit code
  (`test_readwrite_creates_file_if_missing` now checks `returncode == 0`);
  stray mis-indented import in `parser/recursive_descent/parser.py` fixed.
- CI (`.github/workflows/test_migration.yml`) bumped 3.11 → 3.12 in all three
  jobs so the lint job, quick suite, and conformance smoke all run at the new
  floor (3.11 CI would now fail `pip install` against `requires-python`).
- CLAUDE.md lint guidance widened from `ruff check psh/parser/combinators/` to
  `ruff check psh/` — the whole tree must stay clean from here on.
- First release of the Tier A program from the ground-up reappraisal
  (docs/reviews/ground_up_reappraisal_2026-06-10.md).

## 0.274.0 (2026-06-10) - Conformance expansion + claims meta-test (review Tier 3, phase 8 — campaign complete)
- 98 new conformance tests filling the thin areas the review flagged:
  getopts (silent/loud modes, clustering, --, local OPTIND), select
  (choices, REPLY, EOF status), traps (EXIT/ERR/DEBUG/signals/ignore),
  heredocs (quoting forms, <<-, pipelines, sequences, redirect targets),
  fd duplication (exec open/dup/close for read and write, swap order,
  unopened fds), non-interactive job control (wait statuses, kill, $!),
  C-style for, control structures in pipelines, and eval.
- The claims META-TEST (tests/conformance/test_claims_have_tests.py)
  makes the project principle checkable: every "Full support" row in the
  user guide's compatibility table must map to existing conformance
  evidence; new claims without proof fail the suite. It immediately
  caught three unproven claims (C-style for loops, control structures in
  pipelines, eval) — all three now have conformance tests.
- Real bugs the new tests surfaced, all fixed:
  - `$$` returned the CHILD's pid in subshells, command substitutions
    and forked redirect-target expansion (POSIX: the original shell's
    pid everywhere). Captured once at startup, inherited like $PPID.
  - `exec 5<file` clobbered stdin instead of opening fd 5 (input
    redirects ignored their explicit fd); `read <&5` then failed.
  - Signal traps for signals psh doesn't otherwise manage (USR1, USR2,
    ALRM, ...) never installed an OS handler — the shell simply died on
    delivery. trap now installs queueing handlers (actions run at
    command boundaries) and SIG_IGN/SIG_DFL for ''/'-' forms.
  - Subshells now run their own EXIT trap: (trap 'echo bye' EXIT; ...).
  - Background-job notices ([1] 1234) printed in non-interactive shells;
    bash prints them only interactively. Now gated on interactive mode.
  - select's EOF newline goes to stdout (bash), exec's open errors no
    longer leak Python errno reprs.
- Stale user-guide claim corrected: DEBUG/ERR traps are supported (since
  v0.263); RETURN is not.
- Final architecture-review annotation: ALL FOUR TIERS RESOLVED across
  37 releases (v0.238.0-v0.274.0); the remaining bash differences are
  deliberate and documented. Suite: 3,979 → 4,499 tests over the
  campaign.

## 0.273.0 (2026-06-10) - Multi-row line-editor rendering (review Tier 3, phase 7)
- The line editor renders wrapped lines correctly. Every mutating edit
  operation (insert, delete, kills, yank, transpose, history nav,
  search, undo/redo, completion) now funnels through ONE wrap-aware
  repaint (_redraw/_paint), and pure cursor movement uses wrap-aware
  relative positioning (_move_cursor_to). The old per-operation
  backspace + ESC[K arithmetic — which corrupted the display the moment
  prompt+input exceeded the terminal width, since \b never moves up a
  row — is gone (zero raw '\b' writes remain).
- The auto-wrap "pending" state (content ending exactly at the right
  margin) is committed deterministically, so relative cursor math never
  drifts by a row at wrap boundaries. Typing at end of line keeps a
  fast path (echo one char) when no boundary is involved.
- Prompt width is measured correctly: a new pure module (line_layout)
  understands readline's \x01/\x02 invisibility markers (from \[ \]
  in PS1) and OSC title sequences in addition to bare CSI colors — the
  old _visible_length only stripped CSI, so colored/marked prompts threw
  off all cursor math. Marker bytes are also no longer written raw to
  the terminal.
- 16 unit tests on the pure layout computation (prompt measurement,
  wrap positions, boundary handling) and 5 new PTY tests editing in a
  40-column terminal: mid-line insert on a wrapped line, backspace
  across the wrap boundary, ctrl-a/ctrl-k on a wrapped line, history
  recall of a wrapped command, and editing under a colored \[ \]
  prompt. PTY smoke suite is now 26 passing tests.

## 0.272.0 (2026-06-10) - Lexer quote-state consolidation (review Tier 3, phase 6)
- Killed the quadratic backward scan: _is_inside_potential_array_assignment
  walked backward from EVERY quote/expansion character to the previous
  command separator, making a single line of N quoted words lex in
  O(N^2) — 3.8s for 4,000 words. The answer for every position is now
  precomputed in one lazy O(n) forward pass (quote state + bracket
  stack); the same line lexes in 0.039s (~97x) and scaling is linear.
- literal.py's inline ANSI-C quote parser (a duplicate escape-sequence
  implementation) now delegates to the UnifiedQuoteParser, so $'...'
  escape semantics live in exactly one place.
- New lexer performance regression tests (absolute bound + doubling
  ratio) pin the linear behavior — the review's "no performance tests"
  gap for the lexer.
- Assessed the case-pattern `)` inside `$(...)` limitation (stretch
  goal): `$(case x in (x) ...)` parses (use the POSIX paren form);
  making find_balanced_parentheses understand an unparenthesized
  pattern's `)` mid-scan requires keyword-aware parsing, documented as
  a known difference rather than special-cased.

## 0.271.0 (2026-06-10) - Terminal control without test-awareness (review Tier 3, phase 5)
- **Ctrl-C and Ctrl-Z now work on foreground jobs under any PTY.** Three
  real bugs found and fixed:
  1. tcsetattr with TCSADRAIN/TCSAFLUSH (the tty.setraw default) blocks
     until the terminal's output queue drains — which never happens on a
     pty whose master isn't being read. The shell wedged entering/leaving
     raw mode and restoring job terminal modes. All terminal-mode changes
     now use TCSANOW (line editor raw mode, job-control mode save/restore,
     read -s). bash stays responsive in this state; now psh does too.
  2. restore_shell_foreground restored terminal MODES before reclaiming
     terminal OWNERSHIP, so the tcsetattr could block against the dead
     job's process group. Order flipped: tcsetpgrp first.
  3. The PTY smoke xfails for SIGINT/SIGTSTP-to-foreground-job are now
     passing tests, plus a new fg-resume test (21/21, zero xfails).
- One shared `shell.process_launcher` replaces five ad-hoc
  ProcessLauncher constructions across pipeline/subshell/strategies —
  removing the executor→interactive layering reach the review flagged.
- All `'pytest' in sys.modules` gates removed from production code:
  - pipeline/external/subshell terminal control now uses a real
    capability check, JobManager.terminal_pgid_if_owned() (tty present,
    job control supported, AND this shell is the foreground process
    group). Under a test runner that's naturally None.
  - Process-global signal handlers are installed at psh's own entry
    points (__main__ for all modes; the interactive loop re-runs setup
    and claims the foreground) instead of at InteractiveManager
    construction behind a pytest gate. In-process embedders/test shells
    construct Shell directly and never touch process signal state — a
    structural guarantee instead of runner sniffing. The
    PSH_IN_FORKED_CHILD env marker became dead and is removed.
- StringIO type-sniffing removed from the builtin stream-restore path.
  Root cause fixed instead: Shell.__init__ no longer snapshots
  sys.stdout/stderr into the custom-stream overrides (which froze
  init-time objects and defeated the live-tracking ShellState
  properties); the builtin path now saves/restores the override STATE.
- Full suite green (4,063 passed / 4,378 collected); PTY smoke suite
  3x stable at 21/21.

## 0.270.0 (2026-06-10) - PTY test rehabilitation (review Tier 3, phase 4)
- New deterministic pexpect smoke suite (test_pty_smoke.py, 18 passing +
  2 specific xfails) covering the real interactive surface: prompt,
  command execution, state across commands, exit/ctrl-d EOF, ctrl-c at
  the prompt, backspace, arrow-key cursor editing, ctrl-a/k/u/w, history
  recall, PS2 continuation, long (wrapped) lines, background job
  notices, jobs, wait, fg, disown. It REPLACES the two blanket-xfail PTY
  suites (test_pty_line_editing.py, test_pty_job_control.py — deleted),
  whose "pexpect doesn't work under pytest" premise no longer holds.
- The smoke suite runs BY DEFAULT in the standard test run (exempt from
  the --run-interactive gate); the legacy interactive tests stay opt-in.
  Until now the whole interactive directory was silently skipped in
  suite runs — zero interactive coverage in CI.
- Root-caused the old PTY-test folklore (documented in
  README_PEXPECT_ISSUE.md): the line editor's raw mode means Enter is
  CR (pexpect sendline's LF is not accept-line); the DSR cursor query
  (ESC[6n) appears in output; matching must use sentinels that never
  appear in the typed text; and every send must wait for the prompt.
- Fixed module-level sys.modules['termios']=Mock() poisoning in two
  line-editor unit files: it executed at COLLECTION time and broke
  ptyprocess/pexpect for the entire process in whole-tree runs.
- Two genuine gaps carry specific xfails and are the target of the next
  phase (terminal control / is_pytest removal): SIGINT and SIGTSTP
  delivered to a RUNNING foreground job do not return the prompt under
  a pexpect PTY.

## 0.269.0 (2026-06-10) - Parser correctness sweep (review Tier 3, phase 3)
- `f() ( ... )` keeps its subshell semantics: the parser preserves the
  SubshellGroup node instead of unwrapping it, so each call forks.
  Variable writes, `cd` and even `exit` inside the body no longer leak
  into (or kill) the calling shell.
- `f() { ...; } > file` redirections attach to the function definition
  and are applied at each CALL (bash). Previously the redirect parsed as
  a separate empty command, creating/truncating the file once at
  definition time and never during calls. FunctionDef and Function carry
  a redirects list; execute_function_call wraps the body with them.
- Quoted case patterns match literally: CasePattern now carries a Word
  AST with per-part quote context, expanded by the same quoting rule as
  ${x#pat} operands (quoted text and quoted-expansion results are
  escaped; unquoted text and expansion results keep glob power). Fixes
  `case ab in 'a*')` wrongly matching, `"$p"` patterns staying
  glob-active, and `h"*"llo` style mixed patterns. Matching for the Word
  path uses the shared glob->regex converter (handles backslash escapes,
  which fnmatch cannot); the legacy fnmatch path remains for the
  combinator parser.
- `select` returns status 1 when the read hits EOF (bash).
- Dedup: the `&& pipeline / || pipeline` chain loop existed in three
  copies (statements.py, parser.py, commands.py) — now one
  parse_and_or_tail helper; the _FD_DUP_RE regex was defined twice in the
  recursive descent parser (a third lives in the deliberately
  self-contained combinator parser) — now imported from redirections.py.
- Test-infrastructure: an autouse fixture now rolls back os.environ
  after every test, eliminating the export-leak pollution class for
  good. It exposed two tests whose expectations only held because of
  leaked exports (double-quoted `$VAR` handed to an inner `sh -c`
  expands in the OUTER shell, before prefix assignments apply); both
  fixed with escaped dollars after bash verification.
- Still open (pre-existing, unchanged): `\[)` and extglob `@(...)`
  inside case patterns are parse errors; for/select items keep their
  legacy string+quote-type representation (behavior verified correct
  against bash; the Word AST conversion is deferred cleanup).
- 25 new bash-pinned tests (test_function_bodies_and_case_patterns.py).

## 0.268.0 (2026-06-10) - Executor/builtin correctness sweep (review Tier 3, phase 2)
- `f &` runs a function in the background by forking a subshell (bash).
  psh previously rejected it with "functions cannot be run in background".
  Arguments, `wait %1` exit status, redirections and parent-state isolation
  all behave like bash; the child is marked a shell process (keeps SIGTTOU
  ignored) since the function body may run pipelines.
- Circular namerefs (`declare -n a=b; declare -n b=a`) get bash's
  diagnostics: creating the cycle is fine; WRITING through it warns
  "circular name reference" and fails (aborting a non-interactive shell
  with status 1, like other assignment errors); READING warns and expands
  empty (status unchanged); `unset` warns but succeeds. New
  NamerefCycleError raised by resolve_nameref_name and handled per-path.
  The declare-time self-reference error now names the variable.
- `declare -u/-l/-i` no longer transform the EXISTING value — bash applies
  the attribute to future assignments only (`u=abc; declare -u u` leaves
  $u as abc; `x="2+3"; declare -i x` leaves $x as 2+3).
- `type`/`type -t` report shell keywords (if, while, for, case, time,
  `{`, `[[`, ... ) — previously rc 1/no output for `type -t if`.
- `$"..."` locale strings are lexed as plain double-quoted strings in all
  contexts (standalone, assignments, composite words), matching bash
  without a message catalog. The token spans the `$` so composite-word
  adjacency is preserved.
- `$_` tracks the last argument of the previous simple command
  (`true x y; echo $_` prints y); previously it leaked the inherited
  environment value (the Python interpreter path).
- Fixed another env-pollution bug: test_export_builtin exported the
  generic name V into the test runner's environment.
- 50 new bash-pinned tests (test_builtin_correctness_sweep.py,
  test_background_functions.py).

## 0.267.0 (2026-06-10) - Expansion correctness sweep (review Tier 3, phase 1b)
- `${!name}` indirection resolves through the full parameter namespace:
  positionals (`n=2; ${!n}` -> `$2`), array elements (`ref='a[1]'`,
  `ref='a[@]'`, assoc keys), special parameters (`${!#}` -> last
  positional, `ref='@'`) and operators after indirection apply to the
  target (`${!ref%pat}`, `${!n:-d}`). bash diagnostics: an unset source is
  "invalid indirect expansion" and a malformed target name is "invalid
  variable name" (both status 1, the error beating any `:-` default);
  out-of-range positional sources are plain unset.
- Arithmetic uses bash's textual/recursive variable resolution: `$(($x))`
  with `x='2 + 2'` is 4 (the value text is substituted, not coerced to 0),
  reference chains resolve (`y=z; z=42; x=y; $(($x))` -> 42), and circular
  references now raise "expression recursion level exceeded" (status 1)
  instead of silently yielding 0.
- Tilde expansion reads the shell's HOME variable (`HOME=/xyz; echo ~` ->
  `/xyz`), not the inherited environment.
- `$0` works in parameter expansion: `${0##*/}`, `${0:-x}`, `${#0}`.
- POSIX field splitting: only unquoted-expansion text can split. Escapes
  in literal word text are protected structurally (`pre\ post$x` stays one
  field -- previously split) while backslashes in expansion data are plain
  characters (`x='a\ b'; $x` is two fields `a\` and `b` -- previously
  glued). Composite words merge fields across part boundaries with
  delimiter-edge awareness (`pre$x` with `x=':a'` and IFS=: is
  `pre`, `a`). Quoted text adjacent to an expansion no longer splits
  (`"a b"$x`).
- POSIX expansion ordering for command-prefix assignments: the command's
  own words are expanded BEFORE the temporary assignments take effect
  (`V=v echo $V` prints V's prior value -- psh printed `v` and the
  conformance suite documented bash's correct behavior as "a bash bug";
  that inverted verdict is removed from psh_bash_differences.json).
  Assignments apply sequentially, each value seeing those to its left
  (`A=1 B=$A cmd` gives B=1), and when the command words expand to
  nothing the assignments affect the current shell (`V=v $EMPTY`).
- Fixed cross-test pollution: an env-builtin test exported generic names
  (A/B) into the test runner's environment, breaking the conformance
  assignment probe in combined runs.
- 45 new bash-pinned tests (test_expansion_correctness_sweep.py); 5 tests
  updated from old-behavior pins to bash-verified expectations.

## 0.266.0 (2026-06-10) - Pattern-operator operand expansion (review Tier 3, phase 1a)
- Pattern operands of `${x#pat}`, `${x##pat}`, `${x%pat}`, `${x%%pat}`,
  `${x/pat/repl}` and the case-mod operators now undergo variable, command
  and arithmetic expansion with one level of quote removal, matching bash.
  Previously `$var` in these operands was matched as the four literal
  characters `$var`, so the everyday `${f%$ext}` / `${f#$prefix}` idioms
  silently failed; quoted operands (`${f#'a'}`) kept their quotes.
- Quoting controls glob power exactly as in bash: unquoted text and
  unquoted-expansion results keep glob meaning (`p='*'; ${x/$p/Z}` matches
  everything), while quoted text and quoted-expansion results match
  literally (`${x/"$p"/Z}` looks for a literal star).
- Replacements are inserted literally via a callable, never interpreted as
  a regex template: `${x/b/\1}` no longer crashes with "invalid group
  reference" and `${x//X/\n}` no longer injects newlines.
- bash 5.2 patsub_replacement semantics: an unquoted `&` in the replacement
  (even one produced by an expansion) stands for the matched text; `\&`,
  `"&"` and `'&'` are literal; an unquoted backslash escapes the next
  character and is removed; backslashes inside expansion results stay
  literal.
- Pattern/replacement splitting is now quote- and construct-aware, so a
  `/` inside quotes, `${...}`, `$(...)` or `$((4/2))` no longer splits the
  operand early. Empty patterns are a no-op (`${x///Z}` returned
  `ZaZbZcZ`-style corruption before; bash returns the value unchanged).
- Case modification matches bash's per-character rule: `${v^pat}` tests
  only the FIRST character against the pattern (`${v^b}` on `abc` is now a
  no-op) and `${v^^pat}` examines each character individually, so
  multi-character patterns like `${v^^bc}` never match.
- All of the above applies per element to array expansions
  (`${a[@]%$ext}`, `${a[@]/$p/X}`).
- 44 new bash-pinned tests (tests/unit/expansion/test_pattern_operand_expansion.py).

## 0.265.0 (2026-06-10) - Heredoc lexing redesign + lexer correctness (review Tier 2, phase 6)
- HeredocLexer rewritten: lines are classified (command text vs heredoc
  body) and the joined command text is tokenized in ONE ModularLexer pass,
  so cross-line lexer state survives. The old design re-lexed each physical
  line with a fresh lexer, breaking any multi-line construct sharing a
  command with a heredoc — `cat <<EOF && echo "two\n...words"` died with
  "Unclosed quote"; it now matches bash exactly (incl. bash's rule that
  mid-construct lines are command continuation, so the body region follows
  the COMPLETED command). Heredoc operators are found from tokens, so a
  quoted "<<EOF" is never a heredoc.
- source_processor no longer tokenizes heredoc-containing commands twice.
- The textual unclosed-heredoc detector (line buffering) is quote-aware
  with quote state carried ACROSS command lines: `echo "<<EOF" ok` no
  longer buffers forever waiting for a delimiter.
- validate_brace_expansion is quote- and $()-aware: `echo ${x:-"}"}`,
  `${x:-'}'}` and `${x:-$(echo "}")}` no longer die with "Unclosed quote"
  (POSIX 2.6.2).
- Conditional-operator operands remove one level of quotes like bash:
  `${u:-"quoted def"}` prints `quoted def`, not `"quoted def"`; single
  quotes keep operands literal; applies to scalar and array-field paths.
  One test expectation that encoded the old quote-retaining behaviour was
  updated to the bash-verified output.
- First unit tests for the heredoc modules (previously 0% coverage):
  tests/unit/lexer/test_heredoc_lexer.py (11 cases).

## 0.264.0 (2026-06-10) - POSIX & grammar + structural EOF detection (review Tier 2, phase 5)
- `&` is parsed at the and-or-list level per the POSIX grammar:
  `a && b &` backgrounds the WHOLE list (previously the list ran
  synchronously with only its tail backgrounded), and control structures
  can be backgrounded (`while ...; done &`, `if ...; fi &` were parse
  errors). `echo a & && b` is now a syntax error like bash. Single
  simple-command and single-pipeline cases keep the existing direct
  job-control paths; everything else runs in a background subshell
  (AndOrList.background + ExecutorVisitor._execute_background_list).
- POSIX linebreak-after-pipe: `echo hi |` followed by a newline continues
  onto the next line.
- ParseError carries a structural `at_eof` flag (the parse failed at end
  of input, so more lines could complete it). Script line-continuation
  (source_processor) and interactive multi-line detection
  (multiline_handler) key off it, replacing ~70 fragile error-message
  patterns between them — which also fixes scripts with lines ending in
  `&&`/`||`.
- New tests in tests/unit/parser/test_background_lists.py (12 cases pinned
  to bash 5.2).

## 0.263.0 (2026-06-09) - DEBUG/ERR traps + deferred signal traps (review Tier 2, phase 4)
- DEBUG and ERR traps now FIRE. They were stored, documented in `trap`
  help, and silently never dispatched (execute_debug_trap/execute_err_trap
  had zero call sites). DEBUG runs before each simple command; ERR runs
  after eligible failures with exactly the set -e exemptions (reusing the
  v0.253.0 errexit_eligible machinery), sees the failing status in $?, and
  fires before an errexit abort, like bash. A re-entrancy guard keeps
  DEBUG/ERR actions from re-triggering themselves.
- Signal trap actions no longer execute inside the Python signal handler
  (where they could re-enter the parser/executor mid-command, contradicting
  the shell's own self-pipe design). The handler queues the trap and the
  executor runs it at the next command boundary — bash's documented
  behaviour — preserving output ordering.
- Also lands the unreachable empty-action branch removal in
  TrapManager.execute_trap that the v0.258.0 notes claimed but whose edit
  was never written to disk.
- docs/user_guide/17_differences_from_bash.md updated (only RETURN traps
  remain unsupported); new tests in
  tests/integration/job_control/test_debug_err_traps.py (11 cases).

## 0.262.0 (2026-06-09) - Scripting idioms (review Tier 2, phase 3c)
- Scalar `+=` append assignment: `x+=b` appends (previously "command not
  found"); integer (-i) variables add arithmetically (declare -i n=1;
  n+=2 -> 3); works for pure assignments, command-prefix assignments
  (temporary), and `export NAME+=value`; readonly `+=` aborts like any
  readonly assignment. The golden case that encoded the old failure was
  updated to bash's behaviour.
- `printf -v var format args` stores the result in var (array elements
  supported) instead of printing; `printf '%(datefmt)T'` formats an epoch
  argument with strftime (missing/-1 = now).
- A quoted right-hand side of `[[ =~ ]]` is matched LITERALLY, like bash:
  `[[ abc =~ "a.c" ]]` no longer matches. Unquoted and variable patterns
  remain regexes; BASH_REMATCH unchanged.
- New `builtin` builtin: runs a shell builtin bypassing function lookup,
  so wrapper functions (cd() { builtin cd "$@"; ... }) work instead of
  recursing to "command not found".
- New tests in tests/integration/test_scripting_idioms.py (24 cases).

## 0.261.0 (2026-06-09) - Special variables (review Tier 2, phase 3b)
- PIPESTATUS: every foreground pipeline records its members' exit statuses
  (the waiter now always collects them, not only under pipefail); a single
  command records a one-element list, matching bash.
- $PPID (captured at startup; stable across subshells like bash), $UID and
  $EUID, $EPOCHSECONDS, and $EPOCHREALTIME (microsecond precision) as
  dynamic special variables.
- $- includes 'c' when the shell was started with -c.
- New tests in tests/unit/expansion/test_special_variables.py (10 cases).

## 0.260.0 (2026-06-09) - umask and times builtins (review Tier 2, phase 3a)
- New POSIX-required builtins in psh/builtins/system_builtins.py, built on
  the v0.259.0 base helpers:
  - umask: display (plain/-S symbolic/-p reusable), octal set, and symbolic
    set (u+rwx,g-w,o=,a=rx — clauses operate on the allowed-permission
    complement per POSIX), with bash's error messages and exit codes.
    Previously /usr/bin/umask ran as an external command on macOS, so
    `umask 077` silently did nothing — files were still created 644.
  - times: shell and children user/system CPU times in bash's
    NmN.NNNs format.
- New tests in tests/unit/builtins/test_system_builtins.py (11 cases incl.
  verifying the mask actually applies to created files).

## 0.259.0 (2026-06-09) - Builtin infrastructure (review Tier 2, phase 2)
- New shared helpers on the Builtin base class:
  - write()/write_line(): one implementation of the forked-child fd-level
    vs parent shell.stdout output routing that echo/printf/pwd/declare -p/
    env/export/set each carried a private copy of; error() is now also
    forked-child aware. Migrated the seven copied sites.
  - parse_flags(): getopt-style option parsing (clusters, attached or
    separate option values, --, invalid options exit 2 with a usage line).
    unset migrated to it.
- One associative-array initializer parser
  (array_init.parse_assoc_array_entries) replaces the two divergent copies
  in local/declare, fixing three bash divergences: declare -A values
  containing $expansions now expand ([k]=$x), quoted values with spaces work
  under local -A ([k]="x y" no longer truncates), and dynamic keys expand
  ([$k]=v). Single-quoted values stay literal.
- Usage-error exit codes match bash: declare/local/readonly invalid options
  exit 2 (was 1); `unset` with no operands succeeds silently (bash, was rc
  1) and invalid unset options exit 2. Two declare tests updated to the
  bash-verified status.
- New tests: tests/unit/builtins/test_builtin_base_helpers.py (12 cases).

## 0.258.0 (2026-06-09) - Executor/builtins/vi scraps purge (review Tier 2, phase 1c)
- Remove dead ProcessLauncher.launch_job (zero callers; contained a fragile
  command_str.split() re-parse) and the dead DeclareBuiltin._apply_attributes
  (the scope manager applies attribute transforms).
- trap_manager: remove the unreachable empty-action branch and replace the
  install-and-restore signal probing of numbers 1-31 with
  signal.valid_signals().
- Rename psh/executor/test_evaluator.py -> enhanced_test_evaluator.py
  (source files must not start with test_, per the project's own pytest
  collection rules).
- vi editing: the keymap now matches actual behavior. Removed ~30 bindings
  (registers, motions d/c/y/p/r, visual mode, search, '.') that
  _execute_action never dispatched — silent no-ops since they were added —
  plus the orphaned state behind them (vi_pending_motion, vi_registers,
  vi_last_change, vi_mark_start, kill_ring_pos, EditMode.VI_VISUAL). The
  ViKeyBindings docstring documents the implemented subset.
- vi undo/redo are now REAL: 'u' and Ctrl-R dispatch to the existing
  (previously unreachable) undo()/redo() implementations; key_handler.mode
  is synced on mode switches so control-key normal-mode bindings resolve
  correctly; undo() treats the live buffer as the implicit stack top so the
  most recent edit is not skipped. New tests include a guard asserting every
  bound action is dispatched, so phantom bindings cannot reappear.
- psh/executor/CLAUDE.md strategy-order snippet corrected to the code's
  actual POSIX order (special builtins > functions > builtins).

## 0.257.0 (2026-06-09) - Lexer dead-code purge (review Tier 2, phase 1b)
- Remove ~680 lines of lexer fiction flagged by the architecture review:
  - The dead OPERATORS_BY_LENGTH table in constants.py — it had drifted from
    the live table (OperatorRecognizer.OPERATORS) and psh/lexer/CLAUDE.md
    told contributors to edit it; the doc now points at the real table.
  - LexerErrorHandler + RecoverableLexerError (type-hinted a nonexistent
    StateMachineLexer; never instantiated) and the LexerState enum (every
    member except NORMAL unused; the state field itself was never consulted).
  - 28 never-read LexerConfig fields (error-recovery, performance, debugging,
    zsh/sh compatibility, memory management) plus the unused
    create_performance_config/create_debug_config/create_posix_config presets
    and to_dict/from_dict. Re-judged from the earlier "keep tested
    infrastructure" decision: unread configuration misleads readers about how
    the lexer works. create_interactive_config/create_batch_config remain as
    the public entry points and are documented as currently identical.
  - QUOTE_RULES escape maps replaced by an honest processes_escapes boolean:
    the '"' map declared C-style escapes (\n → newline) that are wrong per
    bash AND were never read (only tested for truthiness before delegating to
    pure_helpers.handle_escape_sequence, which is bash-correct).
  - Seven unused LexerContext fields (state, paren_depth, quote_stack,
    heredoc_delimiters, brace_depth, token_start_offset, current_token_parts,
    after_regex_match) and ~16 unused methods incl. the lossy copy();
    CLAUDE.md's LexerContext listing now matches reality and explains why
    quote state is not cross-token state.
  - Four unused pure_helpers functions (read_until_char, find_word_boundary,
    scan_whitespace, find_operator_match) and their tests.
- No behaviour change (full suite + conformance green).

## 0.256.0 (2026-06-09) - Parser dead-machinery purge (review Tier 2, phase 1a)
- Remove ~850 lines of parser machinery that production never read, all
  flagged by the 2026-06-09 architecture review:
  - The ParserContext state flags (in_test_expr, in_arithmetic,
    in_case_pattern, in_function_body, in_command_substitution,
    in_process_substitution) and the save/restore context manager that
    existed only to restore them — written by four sub-parsers, read by
    nothing. psh/parser/CLAUDE.md documented the pattern as a core
    convention; it now documents that grammar context lives in the
    recursive call structure, not in flags.
  - The execution_context AST field (STATEMENT/PIPELINE) and the ~25
    _parse_X_neutral / parse_X_statement / parse_X_command wrapper
    triplets that existed solely to set it. Each construct now has one
    parse_X_statement method; ExecutionContext was removed from
    ast_nodes (the executor's ExecutionContext is unrelated and intact).
  - ParserProfiler (~105 lines) and the enter_rule/exit_rule/parse_stack
    rule-tracking hooks: re-judged from the earlier "keep tested
    infrastructure" decision (v0.231.0 era) because the hooks were never
    called during production parsing, so the profiler could not measure
    anything real and its tests tested fiction.
  - The phantom `debug-parser` option / ParserConfig.trace_parsing chain:
    it claimed to enable parser tracing but the tracing hook was never
    invoked. Removed end-to-end (set -o entry, debug builtin, parser-mode
    educational no longer claims "with debugging").
  - scope_stack/loop_depth/function_depth/conditional_depth counters,
    the ctx heredoc trackers + HeredocInfo, get_state_summary/reset_state,
    and the duplicate Parser.parse_with_heredocs method (production uses
    the module-level function, which the regression tests now target).
- tests/unit/parser/test_parser_context.py rewritten to cover the
  context's real responsibilities; three tests retargeted from removed
  APIs to their live equivalents. No behaviour change (full suite +
  conformance green; control-structure/pipeline smoke battery vs bash
  unchanged).

## 0.255.0 (2026-06-09) - Process substitutions preserve sibling quoting (review Tier 1 E)
- When any argument was a process substitution, ALL of the command's words
  were rebuilt from plain strings, discarding quote context — a quoted "*"
  glob-expanded and a quoted "$x" containing spaces split into fields. Only
  the process-substitution words are replaced with their /dev/fd/N paths
  now; every other word keeps its Word AST.
- The command node is no longer mutated in place, so a command re-executed
  in a loop re-creates its substitutions instead of reusing a stale fd path.
- New tests in tests/unit/expansion/test_process_sub_quoting.py (7 cases).

## 0.254.0 (2026-06-09) - Multi-field quoted array expansion (review Tier 1 D)
- Quoted @-subscripted expansions now produce one field per element, the
  central bash array semantic: "${a[@]}", "${@:2}", "${a[@]:1:2}",
  "${a[@]#pat}", "${a[@]/p/r}", "${a[@]^^}", "${a[@]@Q}",
  "${a[@]:-default}" etc. Previously only "$@" was special-cased and
  everything else collapsed into ONE word, silently corrupting array
  elements containing whitespace.
- Implemented as VariableExpander.expand_to_fields() (resolves the base
  fields, parses operators baked into bracketed parameter text, slices
  positionals/arrays — indexed arrays slice by INDEX like bash — and
  applies value operators per element) plus a generalized affix walker in
  ExpansionManager that distributes prefix/suffix text across fields and
  supports multiple field expansions per word.
- Empty "$@"/"${a[@]}" yields ZERO fields (was one empty field):
  `set --; set -- "$@"; echo $#` now prints 0.
- Unquoted $@/${a[@]} expand to fields before IFS splitting, so parameter
  and element boundaries survive a custom IFS
  (`set -- "a b" c; IFS=:; printf '[%s]' $@` → [a b][c]).
- printf with no arguments now applies the format once with missing
  arguments as ''/0 (`printf '[%s]'` prints `[]`), per POSIX — previously
  the format string was echoed with the bare %s intact.
- "${a[*]}" and ${#a[@]} keep their scalar semantics; ${a[@]@A} keeps the
  whole-array assignment form.
- New tests: tests/unit/expansion/test_multi_field_expansion.py (23
  field-count-pinned cases) and a TestArrayFieldExpansion conformance class
  (8 cases). The for-loop array path in control_flow.py is retained until
  for-loop items carry Word AST (parser limitation).

## 0.253.0 (2026-06-09) - Context-aware errexit + subshell inheritance + readonly fatality (review Tier 1 C)
- set -e now honours the POSIX exemptions exactly as bash: failures in
  if/elif/while/until conditions, in non-final members of && / || lists,
  and under ! negation do not exit the shell; everything else does
  (plain failures, functions, final && members, last pipeline element,
  subshells). Implemented as an errexit_suppress counter on
  ExecutionContext (conditions, non-final/negated pipelines) plus a
  per-AndOrList eligibility flag consumed by the statement-level checks
  and the three source_processor exit sites. Because nested execution
  shares the context (and forked subshells seed it), the exemption
  extends through functions, groups, eval, and subshells, as in bash.
- Subshells inherit the parent's shell options (set -e, pipefail, ...) and
  $?: `set -e; (false; echo no)` aborts inside the subshell and
  `false; (echo $?)` prints 1.
- Assignment exit status matches bash: a pure assignment reports 0 unless a
  command substitution ran while expanding its value (then that status) —
  previously it re-reported the previous command's status, which broke
  `v=$(false) || v=default` under set -e.
- Assignment to a readonly variable aborts a non-interactive shell with
  status 1 (command-prefixed `RO=v cmd` fails with rc 1 but continues,
  like bash).
- New tests: tests/conformance/posix/test_errexit_conformance.py (21 cases
  — the suite previously had zero errexit conformance tests despite the
  user guide's "Full support" claim) and
  tests/integration/shell_options/test_errexit_script_mode.py (8 cases,
  incl. an end-to-end `set -euo pipefail` strict-mode script). The
  differences doc's strict-mode workaround section was replaced with the
  bash-identical guidance.

## 0.252.0 (2026-06-09) - External redirections applied once (review Tier 1 B)
- External-command redirections were applied TWICE — by the parent
  (with_redirections) and again by the forked child
  (setup_child_redirections). Consequences fixed: `cmd 2>&1 >f` resolved
  `2>&1` against the already-redirected fd 1 and sent stderr into f (bash:
  to the original stdout), and command substitutions in heredoc bodies and
  redirect targets executed twice. The parent now skips fd-level
  application for ExternalExecutionStrategy; the child path already handles
  every redirect type (incl. process-substitution targets, dynamic fd dups,
  noclobber, heredocs).
- New side-effect-counting and ordering tests in
  tests/integration/redirection/test_external_redirect_once.py (10 cases
  pinned to bash 5.2).

## 0.251.0 (2026-06-09) - Large heredocs via temp file (review Tier 1 A3)
- Heredoc and here-string content used to be written in full into an
  os.pipe() before any reader existed, deadlocking the shell for bodies
  larger than the kernel pipe buffer (~64KB; verified hang at 130KB).
  Content now goes through an anonymous unlinked temp file dup2'd to stdin
  — the same approach bash uses — shared by both helpers
  (FileRedirector._stdin_from_content).
- New tests in tests/integration/redirection/test_large_heredoc.py
  (8 cases incl. 300KB bodies, content integrity, expansion behaviour).

## 0.250.0 (2026-06-09) - return works in sourced files (review Tier 1 A2)
- `return N` inside a sourced script stops executing the file and becomes the
  exit status of `source`/`.`, like bash (previously: "can only return from a
  function" error and the rest of the file kept executing). Implemented with
  a source-nesting counter on ShellState; nested sourcing returns one level.
- `return` inside a function in a sourced file still exits the function only.
- Exit-code fixes pinned to bash: top-level `return` is rc 2 (was 1), and
  `return abc` prints the numeric-argument error but still returns from the
  function/file with rc 2 (was: continued executing the function body).
- New tests in tests/unit/builtins/test_source_return.py (8 cases).

## 0.249.0 (2026-06-09) - exec failure exits non-interactive shell (review Tier 1 A1)
- `exec missing_command` now exits a non-interactive shell with status 127
  (126 for found-but-not-executable), per POSIX and bash, instead of
  printing the error and continuing with rc 0. Interactive shells survive
  and report the status.
- New tests in tests/unit/builtins/test_exec_builtin.py (4 cases).

## 0.248.0 (2026-06-09) - set -u message and fatality (review Tier 0 #11)
- `set -u` violations printed "psh: psh: $x: unbound variable": the expansion
  code wrapped the message in a "psh: " prefix that the printing handler
  added again. The wrappers are gone; the message now matches bash's format
  exactly (`x: unbound variable`; positionals keep the `$`).
- A non-interactive shell now aborts with status 127 on a nounset violation,
  like bash, instead of continuing with rc 0. Interactive shells report the
  error and continue.
- Out-of-range positional parameters (`echo $5`) now trigger the nounset
  check (previously silently expanded empty).
- New subprocess tests in
  tests/integration/shell_options/test_nounset_script_mode.py (8 cases).

## 0.247.0 (2026-06-09) - Control flow propagates through eval (review Tier 0 #10)
- `eval break` / `eval continue` / `eval return N` now act on the enclosing
  loop/function instead of printing "only meaningful in a loop" (or
  "unexpected error") and being converted to exit status 1. Three causes
  fixed: nested execution (eval, source, trap actions) reuses the caller's
  ExecutorVisitor via Shell._execute_with_visitor so loop depth and function
  context carry through; the broad exception guards in executor/strategies.py
  re-raise LoopBreak/LoopContinue/UnboundVariableError (matching
  command.py's handling); and source_processor re-raises control-flow
  exceptions when execution is nested instead of reporting them.
- Top-level `break`/`continue` outside any loop now warn once and continue
  executing with status 0, like bash (previously: warning printed twice,
  status 1, remaining statements skipped). Two legacy tests asserting the
  non-bash exit code were updated to the bash-verified behaviour.
- New tests in tests/integration/control_flow/test_eval_control_flow.py
  (9 cases pinned to bash 5.2).

## 0.246.0 (2026-06-09) - Transactional redirection save/restore (review Tier 0 #9)
- `builtin 2>&1` no longer kills the shell's stdout: restore used to close
  whatever object was in sys.stderr (after 2>&1 that IS the real stdout),
  breaking every later builtin with "I/O operation on closed file". Restore
  now closes exactly the files setup opened, tracked per call.
- Same fd redirected twice (`echo hi >c >d`, `{ cmd; } >e >f`) restores the
  ORIGINAL stream/fd afterwards: fd-level restore iterates in reverse (as the
  io_redirect CLAUDE.md always documented) and builtin stream backups are
  recorded first-touch-wins instead of being overwritten.
- A redirect failing part-way (`echo hi >a >/bad/x`) rolls back the
  redirections already applied — both the builtin stream path and the
  fd-level apply_redirections — instead of leaving the shell's stdout
  hijacked for the rest of the session.
- New subprocess regression tests in
  tests/integration/redirection/test_redirection_restore.py (12 cases pinned
  to bash 5.2 behaviour).

## 0.245.0 (2026-06-09) - Brace expansion on heredoc lines (review Tier 0 #8)
- tokenize_with_heredocs() omitted the TokenBraceExpander pass that
  tokenize() performs, so any command line containing a heredoc silently
  lost brace expansion (`cat <<EOF; echo {a,b}` printed `{a,b}`; bash: `a b`).
  Heredoc bodies remain literal, as in bash.
- First unit tests touching the heredoc lexer path
  (tests/unit/lexer/test_heredoc_brace_expansion.py, 6 cases).

## 0.244.0 (2026-06-09) - trap -- handling (review Tier 0 #7)
- `trap -- 'action' SIGNAL` works: a leading `--` ends option processing per
  POSIX instead of being taken as the action ("invalid signal
  specification"). Bare `trap --` lists traps like bare `trap` (bash).
- New tests in tests/unit/builtins/test_signal_builtins.py (4 cases).

## 0.243.0 (2026-06-09) - export option parsing and validation (review Tier 0 #6)
- `export` now parses options: `-p` prints exports (optionally filtered by
  name) instead of creating a variable literally named `-p`; `-n` removes the
  export attribute (keeping the variable, with optional assignment); `--`
  ends option processing; unknown options exit 2.
- Invalid identifiers are rejected with rc 1 (`export 1bad=x`), and like
  bash the remaining arguments are still processed.
- New tests in tests/unit/builtins/test_export_builtin.py (12 cases pinned
  to bash 5.2 behaviour).

## 0.242.0 (2026-06-09) - set builtin option parsing (review Tier 0 #5)
- `set` no longer returns after the first `-o`/`+o`: `set -o errexit -o
  pipefail` and mixed forms like `set -o pipefail -x foo bar` now apply every
  option before collecting positional parameters.
- `set -euo pipefail` works: a trailing `o` in a short-option cluster consumes
  the next argument as a long option name, like bash. The corresponding
  "Combined Short Option Parsing" difference was removed from
  docs/user_guide/17_differences_from_bash.md and is backed by new
  conformance tests.
- `set -o vi`/`set -o emacs` are silent (bash prints nothing), and bare `set`
  no longer emits a non-bash `edit_mode=...` line.
- Invalid options ("set -q", "set -o badname") now exit 2 with bash-style
  messages; `+o badname` errors instead of silently succeeding.
- New tests: tests/unit/builtins/test_set_builtin.py (14 cases) and 3
  conformance tests in tests/conformance/bash/test_bash_compatibility.py.

## 0.241.0 (2026-06-09) - UNSET tombstones hidden from variable listings (review Tier 0 #4)
- `get_all_variables()`/`all_variables_with_attributes()` no longer include
  UNSET tombstones: after `f(){ unset HOME; ...}` the variable disappeared
  from lookups but still showed as `HOME=` in `set` output (bash shows
  nothing). Tombstones in inner scopes now also remove the shadowed
  outer-scope name from listings, matching lookup semantics.
- First direct unit tests for EnhancedScopeManager tombstone visibility
  (tests/unit/core/test_scope_tombstones.py, 9 cases pinned to bash 5.2).

## 0.240.0 (2026-06-09) - Fix ${!prefix@}/${!prefix*} prefix matching (review Tier 0 #3)
- `${!prefix@}`/`${!prefix*}` passed the (always-empty) operand instead of the
  variable name as the prefix, so they listed EVERY shell+environment
  variable. They now match only names with the given prefix.
- Names are no longer emitted with literal `"` quote characters (bash never
  does this), and quoted `${!prefix*}` joins with the first character of IFS,
  consistent with `$*`.
- Tightened the integration tests whose substring assertions masked the bug
  and added no-match and IFS-join cases (exact-match assertions, pinned to
  bash 5.2).

## 0.239.0 (2026-06-09) - Fix local double-expansion injection (review Tier 0 #2)
- `local v='$(cmd)'` no longer executes the command: LocalBuiltin re-expanded
  its already-executor-expanded scalar value, so single-quoted `$`-text was
  expanded a second time (a correctness and injection defect). The value is
  now used as received.
- Array initializers for `local`/`declare` are parsed by one shared
  quote-aware helper (psh/builtins/array_init.py): single-quoted elements
  stay literal, double-quoted elements expand without word splitting, and
  unquoted elements expand with word splitting — matching bash. Previously
  `local` expanded even single-quoted elements and `declare` never expanded.
- Fix the parser's array-initializer reconstruction dropping `$` from
  VARIABLE tokens (`local arr=(one $x)` produced element "x" instead of the
  value of `$x`).
- New tests in tests/unit/builtins/test_local_builtin.py (14 cases pinned to
  bash 5.2 behaviour).

## 0.238.0 (2026-06-09) - Fix break N / continue N beyond loop depth (review Tier 0 #1)
- Fix a crash when `break N`/`continue N` exceeded the enclosing loop depth:
  function-local `import sys` statements in `ExecutorVisitor.visit_TopLevel`/
  `visit_StatementList` shadowed the module-level import, so the
  `except LoopBreak` handler died with UnboundLocalError
  (`while true; do break 2; done` → "cannot access local variable 'sys'").
- Match bash semantics for out-of-range levels: `break N` with N greater than
  the number of enclosing loops now exits all enclosing loops with status 0,
  and `continue N` resumes the outermost loop, instead of escaping to the top
  level as an error. Applied uniformly across while/until/for/C-style-for/select.
- New regression tests in tests/integration/control_flow/test_break_continue_levels.py
  (subprocess-based, pinned to verified bash 5.2 behaviour).
- First fix from the 2026-06-09 architecture & feature review
  (docs/reviews/architecture_feature_review_2026-06-09.md, Tier 0 list).

## 0.237.0 (2026-06-07) - Extract pure multiline helper from LineEditor (§1.5)
- Move the 93-line, state-free `LineEditor._convert_multiline_to_single` to a
  standalone pure function `psh/line_editor_helpers.convert_multiline_to_single`
  (callers and the existing test updated; new focused unit tests added). Trims
  `line_editor.py` 1301->1209 lines and isolates testable pure logic. The rest of
  LineEditor is left cohesive by design (heavy shared editor state). No behaviour
  change.

## 0.236.0 (2026-06-06) - Shell.active_parser property + Shell.add_history() (§1.1 E)
- Add a public `Shell.active_parser` property (get/set) and `Shell.add_history()` method, and route all external callers through them instead of reaching into the private `_active_parser` field or walking `interactive_manager.history_manager.add_to_history`: source_processor, ast_debug, parser_experiment (`parser-select`), __main__, and print -s. Phase 2 study §1.1. No behaviour change.

## 0.235.0 (2026-06-06) - Drop ineffective shell.variables[] mutation in rc_loader (§1.1 C)
- rc_loader's $0 save/restore assigned `shell.variables['0']`, but `state.variables` is a snapshot dict so the writes were no-ops. Remove the dead block — eliminating the direct state-dict mutation flagged in §1.1 — with no behaviour change (rc files already ran in the shell's own $0 context).

## 0.234.0 (2026-06-06) - TrapManager.get_handler() instead of reaching into trap_handlers (§1.1 B)
- Add `TrapManager.get_handler(signal_spec)` and use it in `SignalManager` instead of reaching into `trap_manager.state.trap_handlers`. Phase 2 study §1.1. No behaviour change.

## 0.233.0 (2026-06-06) - Public array accessors instead of ._elements reaches (§1.1 A)
- Add narrow public accessors to the array types — `IndexedArray.next_index()`, `IndexedArray.__contains__`, `AssociativeArray.__contains__` — and route the external callers through them instead of reaching into `._elements`: array append (`executor/array.py`), declare indexed→assoc conversion (`function_support.py`, now via `isinstance`+`indices()`/`get()`), and `[[ -v arr[i] ]]` membership (`test_evaluator.py`). Phase 2 study §1.1. No behaviour change.

## 0.232.0 (2026-06-06) - Remove dead QuoteParsingContext methods (lexer)
- Remove the unused `QuoteParsingContext.parse_quote_at_position` (0 callers; also carried a `parser._create_literal_part` private reach) and `get_quote_rules` (0 callers). `is_quote_character` is kept (used by the lexer). Phase 2 study §1.4. No behaviour change.

## 0.231.0 (2026-06-06) - Remove dead visitor state/stubs (arithmetic-suppression toggle, curl|sh stub)
- Remove never-enabled validator state: `_in_arithmetic_context` / `_in_test_context` toggles, the `ignore_undefined_in_arithmetic` config field, and their always-False branches (the arithmetic-suppression feature was never wired on). Remove the SecurityVisitor `_is_piped_to_shell` permanent-False stub and its never-firing curl/wget-piped-to-shell check. Phase 2 study §1.4. No behaviour change (the removed branches were unreachable). `SecurityIssue.node` is kept (plausible result-object API).

## 0.230.0 (2026-06-06) - Remove dead scripting scaffolding (base.execute, forwarders, expansion_manager)
- Remove the never-invoked abstract `ScriptComponent.execute` and the four dead subclass `execute` forwarders (ScriptExecutor/ShebangHandler/SourceProcessor/ScriptValidator) — callers use the concrete domain methods (run_script, execute_with_shebang, execute_from_source, validate_script_file) directly. Drop the unused `ScriptComponent.expansion_manager`. Phase 2 study §1.4. No behaviour change.

## 0.229.0 (2026-06-06) - Remove dead state fields & unreachable branch (core/interactive/executor)
- Remove unused dead state: `ShellState._original_signal_handlers`, `SignalManager._interactive_mode` (write-only) and its never-called `get_sigchld_fd()`, and the unreachable `CommandList` branch in `ExecutorVisitor.generic_visit` (no such AST node). Dead-code cleanup from Phase 2 study §1.4. No behaviour change.

## 0.228.0 (2026-06-06) - Remove dead HeredocHandler + _saved_fds (io_redirect)
- Remove the never-called `HeredocHandler` class (`io_redirect/heredoc.py`) and its import/instantiation in IOManager — heredoc content is handled by `FileRedirector._redirect_heredoc`. Also drop the unused `IOManager._saved_fds` attribute. Dead-code cleanup from Phase 2 study §1.4. No behaviour change.

## 0.227.0 (2026-06-06) - Public cross-builtin helpers (study #21)
- Promote the builtin methods reached across components to public API:
  `TestBuiltin.evaluate_test` / `evaluate_unary` (used by `[` and the executor's
  test evaluator), `ParserConfigBuiltin.set_mode` (used by `parser-select`), and
  `PrintfBuiltin.process_format_string_posix` (used by `print`). Removes the
  builtins-call-siblings'-privates leak tracked as Phase 2 study finding #21.
  No behaviour change.
- This closes the last of the five private-API-leak items from the Phase 2
  architecture study (#14, #15, #18, #20, #21 now all resolved).

## 0.226.0 (2026-06-06) - Public WordBuilder decomposition API (study #20)
- Promote `WordBuilder._has_decomposable_parts` and `_token_part_to_word_part`
  to public `has_decomposable_parts` / `token_part_to_word_part`. The combinator
  parser now builds the shared Word AST via public API instead of reaching into
  recursive-descent privates (Phase 2 study finding #20). No behaviour change.

## 0.225.0 (2026-06-06) - Slim builtin-redirection setup (study #18)
- Refactor `IOManager.setup_builtin_redirections`: extract the triplicated
  "output fd -> file" branch (`>`, `>>`, `>|`) into a shared
  `_redirect_builtin_output_file` helper (swap sys.stdout/stderr for fd 1/2,
  delegate fd>=3 to FileRedirector), and document why the `>&` 2>&1 / 1>&2 cases
  swap Python stream objects while other dups go to the fd level. Addresses the
  oversized/duplicated `setup_builtin_redirections` finding (#18). No behaviour
  change. (The unrelated pre-existing `builtin >&2 2>file` "lost sys.stderr"
  quirk is untouched.)

## 0.224.0 (2026-06-06) - Public expansion helpers (study #15)
- Promote `ExpansionManager._expand_expansion` and `_process_dquote_escapes` to
  public `expand_expansion` / `process_dquote_escapes`. The executor's
  assignment-value builder now uses the public API instead of reaching into
  private methods (Phase 2 study finding #15). No behaviour change.

## 0.223.0 (2026-06-06) - First-class in_forked_child state (study #14)
- Promote the private `ShellState._in_forked_child` to the public, always-present
  `ShellState.in_forked_child`. Readers across builtins/executor/expansion now
  access it directly instead of via defensive `hasattr`/`getattr`, removing the
  private-API leak tracked as Phase 2 study finding #14. No behaviour change.

## 0.222.0 (2026-06-06) - Promote array-element setter to public API
- Internal cleanup (no behaviour change): the nameref array-element write path
  added in 0.221.0 reached into a private `VariableExpander._set_var_or_array_element`
  from the scope manager. That helper is now the public
  `VariableExpander.set_var_or_array_element()` / `ExpansionManager.set_var_or_array_element()`,
  so the scope manager routes subscripted nameref writes through public API
  instead of a private method (avoids adding a new instance of the private-API /
  layering smells tracked in the Phase 2 architecture study).
- Refreshed `docs/reviews/codebase_study_2026-06-05_phase2_architecture.md` to
  reflect review against v0.221.0.

## 0.221.0 (2026-06-06) - Namerefs Phase 2: array-element targets
- **Namerefs whose target is an array element** now work, e.g.
  `arr=(p q r); declare -n e=arr[1]`:
  - read-through (`$e` → `q`, `${e^^}`, `${#e}`) and write-through
    (`e=Q` sets `arr[1]`); associative-array elements too (`declare -n e=m[k]`);
    `local -n el="a[0]"` pass-by-reference into a function.
  - `${!e}` yields the subscripted target name (`arr[1]`).
  - Implemented by resolving the nameref *name* at the expansion read helpers
    (so a subscripted target flows into the existing array-element branch) and by
    delegating subscripted writes from `set_variable` to the array-element setter.
  - Minor documented difference: bash's `${#e}` returns 0 for a
    nameref-to-element (a bash quirk); psh returns the element value's length.

## 0.220.0 (2026-06-06) - Name references (declare -n / local -n), Phase 1
- **Namerefs** with scalar targets, matching bash:
  - `declare -n ref=target` / `local -n ref=$1` create a name reference.
  - Read-through (`$ref` → target's value) and write-through (`ref=v` sets the
    target, creating it if unset); nameref chains resolve transitively.
  - `local -n` provides pass-by-reference into functions.
  - `unset ref` unsets the *target*; `unset -n ref` unsets the nameref.
  - `${!ref}` yields the target *name*; `declare -p ref` prints `declare -n ref="target"`.
  - Self-references (`declare -n r=r`) are rejected; cycles are guarded.
  - Deferred target: `declare -n r; r=x` sets r's target to x.
- **`${!var}` indirect expansion** (scalar) is now implemented as part of this:
  for a non-nameref, `${!var}` yields the value of the variable named by `$var`.
- Resolution hooks live at the scope-manager read/write chokepoints
  (`get_variable`/`set_variable` via a new `resolve_nameref_name`), with
  introspection paths (`declare -p`, `${var@a}`, `unset -n`) using raw lookup.
- Not yet supported (Phase 2): namerefs whose target is an array element
  (`declare -n e=arr[1]`).
- Added `tests/unit/core/test_nameref.py` (27 tests, incl. bash parity); the
  previously-xfail `test_declare_nameref_attribute` now passes. Refreshed the
  differences-from-bash chapter.

## 0.219.0 (2026-06-06) - let builtin
- **`let arg [arg ...]`** evaluates arithmetic expressions, equivalent to
  `((arg))` for each argument. Side effects apply (`let x=5+3`, `let ++x`,
  `let "x+=2"`). Exit status is 0 when the last expression is non-zero, 1 when
  it is zero or on an invalid expression; no arguments → "expression expected"
  (exit 1). Reuses the shared arithmetic evaluator.
- Added `tests/unit/builtins/test_let.py` (22 tests, incl. bash parity).
  Refreshed the differences-from-bash chapter.

## 0.218.0 (2026-06-06) - mapfile / readarray builtin
- **`mapfile` (alias `readarray`)** reads lines from input into an indexed
  array, matching bash:
  - `-t` strip the trailing delimiter; `-d delim` use a custom delimiter
    (first char; empty = NUL); `-n count` read at most COUNT lines;
    `-O origin` assign from index ORIGIN without clearing the array;
    `-s count` skip leading lines; `-u fd` read from a file descriptor.
  - Default array is `MAPFILE`; clustered flags (`-tn2`) work; an unset/extra
    second argument is ignored (bash-compatible); the `-C`/`-c` callback
    options are not supported.
- `type` now recognises aliased builtin names (so `type readarray` reports a
  shell builtin), via `BuiltinRegistry.has()` instead of the primary-name list.
- Added `tests/unit/builtins/test_mapfile.py` (26 tests, incl. bash parity).
  Refreshed the differences-from-bash chapter.

## 0.217.0 (2026-06-06) - Parameter transformation operators ${var@OP}
- **`${var@OP}` transformation operators** implemented for scalars, arrays, and
  positional parameters, matching bash:
  - `@Q` quote for reuse as input (single-quote form; `$'...'` for control
    chars; unset → empty)
  - `@U` / `@u` / `@L` uppercase-all / uppercase-first / lowercase-all
  - `@E` expand ANSI-C backslash escapes (`\n`, `\t`, `\xHH`, …)
  - `@P` prompt-string expansion (`\u`, `\h`, …)
  - `@A` assignment/`declare` form (`x='a b'`, `declare -i n='5'`,
    `declare -a a=([0]="x" [1]="y z")`)
  - `@a` attribute-flag letters (e.g. `airx`)
  - `${arr[@]@OP}` applies per element; `${arr[@]@A}` emits a full `declare`
    statement; `${@@Q}` quotes each positional parameter.
- Parsed in both the recursive-descent Word AST path (`WordBuilder`) and the
  string path (`parameter_expansion.parse_expansion`); the trailing-position
  check keeps the array-subscript `@` in `${arr[@]}` from being mistaken for a
  transform.
- Not implemented: `@K` / `@k` (associative key/value display).
- Added `tests/unit/expansion/test_parameter_transform.py` (31 tests, incl. a
  bash-parity parametrization). Refreshed the differences-from-bash chapter.

## 0.216.0 (2026-06-06) - Brace expansion of expansion items; arithmetic fd-dup targets
- **Brace list expansion now carries expansion items** (`{$((1)),$((2)),$((3))}`
  → `1 2 3`; also `{$(cmd),...}` and `{$a,$b}`). Brace expansion is textual and
  runs before parameter/command/arithmetic expansion, so the token-level
  `TokenBraceExpander` now treats `$((..))`/`$(..)`/`$var` tokens as opaque units
  in a composite run instead of refusing to expand any list containing a `$`.
  The one case the token model cannot reproduce — bash re-forming a variable
  *name* out of brace text (`$x{1,2}` → `$x1 $x2`) — is detected and left
  unexpanded (documented divergence). Brace *ranges* with `$`-endpoints stay
  literal, matching bash.
- **Arithmetic/variable fd-duplication targets** (`>&$((1+1))`, `2>&$fd`,
  `<&$n`). The lexer emits a bare `N>&`/`>&`/`<&` operator when the target is an
  expansion; the parser keeps the expansion as the dup target; and
  `FileRedirector._resolved` expands it to an integer fd at execution time
  (raising "ambiguous redirect" for a non-numeric value). A shallow-copy
  resolution keeps the AST node unmutated so re-execution in a loop re-resolves.
- Added regression tests (brace expansion with arithmetic/command-sub/variable
  items and name-fusion divergence; dynamic fd-dup targets). Both were previously
  documented `xfail`s in the advanced-arithmetic suite, now passing.

## 0.215.0 (2026-06-06) - Stop hiding defects in executor error guards
- **Executor broad-except guards** (study triage #13) — tightened the executor's
  `except Exception` boundaries so internal defects are no longer silently
  reported as `psh: <msg>` (exit 1):
  - The two `set_variable` guards in `command.py` (standalone and command-prefix
    assignments) now catch only `ReadonlyVariableError` instead of any exception.
  - The genuine last-resort guards (simple-command boundary, both builtin-exec
    strategies, function-body boundary) keep the broad catch for REPL resilience
    but now print the traceback under `--debug-exec`, matching the
    ProcessLauncher and source-processor guards. Control-flow exceptions still
    propagate.
- Added regression tests (readonly assignment paths; an injected builtin defect
  is reported without a traceback by default and with one under `--debug-exec`).
  This was the last of the study's high/medium triage items.

## 0.214.0 (2026-06-06) - Narrow array-index exception handling
- **Stop swallowing defects in array subscripts** (study triage #4) — the
  remaining four array-index sites in `expansion/variable.py` (subscript
  read/set, new-array creation, and `_param_is_set`) caught a bare
  `except Exception` around `evaluate_arithmetic`, defaulting the index to 0 and
  masking any non-arithmetic defect. Narrowed all four to `except ArithmeticError`,
  matching the sites already fixed in the v0.x safety pass. Invalid *arithmetic*
  subscripts are still handled gracefully (→ index 0); genuine defects now
  propagate. Added 5 regression tests.
- Study triage #5 (broad except relabeling control-flow as "unexpected error" in
  `scripting/source_processor.py`) was verified already resolved — `break`/
  `continue` outside a loop and `return` outside a function produce their proper
  messages, and the inner handler catches only `LoopBreak`/`LoopContinue`.

## 0.213.0 (2026-06-06) - Remove dead OptionHandler policy methods
- **Trimmed `OptionHandler`** (study triage #16) — two of its four methods were
  dead with zero callers because the executor implements those policies itself:
  `should_exit_on_error` (errexit is enforced structurally at the statement-list
  level) and `get_pipeline_exit_code` (pipefail is computed inline in the
  pipeline executor). Removed both; kept the two live methods,
  `check_unset_variable` (nounset) and `print_xtrace` (set -x, used via the
  executor since v0.205.0). All four option behaviors (nounset/xtrace/errexit/
  pipefail) verified unchanged.

## 0.212.0 (2026-06-06) - Trim dead ExecutionContext factories and fields
- **Removed dead `ExecutionContext` machinery** (study triage #17) — about half
  the module was unused: factory methods `subshell_context`, `loop_context_enter`,
  `function_context_enter`, `with_pipeline_context`, `with_background_job`, and
  `should_use_print`, plus fields `in_subshell`, `pipeline_context` (write-only),
  `background_job`, `suppress_function_lookup`, and `exec_mode`. Kept the four
  live fields (`in_pipeline`, `in_forked_child`, `loop_depth`, `current_function`)
  and four live methods (`fork_context`, `pipeline_context_enter`, `in_loop`,
  `in_function`). `loop_depth`/`current_function` are mutated in place, which is
  why the matching `*_context_enter` factories were dead. context.py 189 -> 60
  lines; behavior unchanged (covered by the existing executor suite).

## 0.211.0 (2026-06-06) - Remove the vestigial readline CompletionManager
- **Dropped `CompletionManager`** (study triage #7) — the readline-based tab
  completion manager was dead: `setup_readline()` registered a readline completer,
  but psh reads interactive input through its own `LineEditor` (raw mode) with its
  own `CompletionEngine`, so the readline completer was never invoked and the
  `complete_*` / `get_completions` methods had no callers. Removed the class
  (`completion_manager.py`) and all wiring (`base.py`, `repl_loop.py`,
  `interactive/__init__.py`, docs). Tab completion is unaffected — it lives in
  `LineEditor`/`CompletionEngine`. ~142 fewer lines.

## 0.210.0 (2026-06-06) - Flush buffered output in command-substitution children
- **`$(...)` now captures stream-writing builtins** — the command-substitution
  child exits with `os._exit()`, which does not flush Python-level buffers. So a
  builtin that writes to the Python stream rather than `os.write` (e.g.
  `parser-mode`, `parser-config`, `debug`) produced empty output inside
  `$(...)`, while `echo` (fd-level) worked. Added a buffer flush before
  `os._exit` in `expansion/command_sub.py`, mirroring the ProcessLauncher
  child-exit flush. Only command substitution was affected — pipelines,
  subshells, and background jobs already flush.
- Added subprocess-based regression tests (the forked child's `sys.stdout` under
  pytest in-process capture is not the pipe, so the real fd-1 path must be
  exercised via a subprocess).

## 0.209.0 (2026-06-06) - Fix formatter output for subshells, brace groups, [[ ]]
- **Formatters no longer emit `# Unknown node` for real node types** (study
  triage #6). Two formatters were affected:
  - `FormatterVisitor` (behind `psh --format`) had no `visit_SubshellGroup` /
    `visit_BraceGroup`, so subshells and brace groups fell through to
    `generic_visit` and produced a `# Unknown node: ...` comment instead of
    shell. Added both (shared `_format_group` helper) → `( ... )` / `{ ... }`.
  - `ShellFormatter` (used by `type` / `declare -f`) was missing `SubshellGroup`,
    `BraceGroup`, and `EnhancedTestStatement`; added them plus a recursive
    `_format_test_expression` for `[[ ]]` (unary/binary/negated/compound).
- Output is valid shell and round-trip stable (format → parse → format is
  idempotent). Added 33 tests across both formatters, which previously had no
  direct coverage.

## 0.208.0 (2026-06-06) - Remove the test-only pipeline path (eval_test_mode)
- **Dropped `eval_test_mode`** (study triage #1) — the pipeline executor carried
  an entire alternate, no-fork execution path (`_execute_simple_pipeline_in_test_mode`
  and helpers, ~161 lines) gated on `state.eval_test_mode`, plus matching branches
  in `echo`/`printf`/`pwd` (`io.py`) and `print`. That flag was enabled by exactly
  one test and never in production, so the path was test-only code embedded in the
  production executor (and its behavior diverged from the real forking path).
- The one dependent test (`test_eval_pipe`) now uses `capfd`, capturing the real
  forking pipeline at the file-descriptor level. The flag, the no-fork pipeline
  cluster, the `io.py`/`print_builtin.py` branches, and the `state.py`
  property/methods are removed. Production behavior is unchanged (it never set the
  flag); net ~187 fewer lines.
- (The narrow `is_pytest` terminal-control guard in the forking path is a
  separate, legitimate no-controlling-terminal guard and was left in place.)

## 0.207.0 (2026-06-06) - Route builtin output through shell.stdout
- **Builtins no longer use bare `print()`** (study triage #2) — `parser-config`/
  `parser-mode`, `debug`/`debug-ast`, `kill -l`, `jobs`/`fg`/`bg`/`wait`,
  `cd -`, and `parse-tree`/`show-ast` wrote output with bare `print()`, sending
  it to `sys.stdout` instead of `shell.stdout`. That leaked output past
  in-process capture / redirection (e.g. builtin-to-builtin pipelines in test
  mode, which capture the first command via `shell.stdout`). All 47 such calls
  across the six affected builtins now pass `file=shell.stdout`; `kill -l` gained
  `shell` threading so its lister can reach the stream.
- Behavior-preserving for fd-level cases (`>`, external pipelines) where
  `shell.stdout` already aliases `sys.stdout`. (Separately noted, not fixed here:
  command substitution loses buffered builtin output across `os._exit` — a flush
  issue independent of stream routing.)
- Added `tests/unit/builtins/test_builtin_stdout_routing.py` (6 tests) asserting
  output lands on `shell.stdout` and does not leak to `sys.stdout`.

## 0.206.0 (2026-06-06) - Fix two analysis-visitor bugs (until loops, brace groups)
- **`until` loops now counted in metrics** — `MetricsVisitor` had `visit_WhileLoop`
  but no `visit_UntilLoop`, so `until` loops were not counted in `total_loops`
  (or `loop_types`). Added `visit_UntilLoop` mirroring `visit_WhileLoop`; an
  `until` loop now counts identically to a `while` loop.
- **Brace group in a pipeline no longer crashes analysis** — `--metrics` /
  `--security` on e.g. `{ echo a; } | tee log` raised `'StatementList' object is
  not iterable`. This was resolved by the v0.205.0 traversal unification; this
  release adds regression tests pinning it (metrics/security no longer crash and
  the group's inner commands are counted).
- Both fixes covered by new tests in `tests/unit/visitor/test_analysis_visitors.py`.

## 0.205.0 (2026-06-06) - Unify analysis-visitor traversal and shared checks
- **Visitor traversal unified (Phase 2 study §1.3, #19)** — the metrics,
  security, and linter visitors each had their own `generic_visit`. Two walked
  only one of `items`/`statements`/`body` (silently skipping children of any
  other shape); the third did a dataclass-field walk. All three now use one
  shared traversal in `psh/visitor/traversal.py` (`iter_child_nodes` /
  `visit_children`).
- **Latent bug fixed** — because the metrics/security traversal under-walked,
  nodes without a dedicated visitor (e.g. `until` loops) had children skipped:
  `until [ -e f ]; do …` did not count the `[ -e f ]` condition command. The
  shared traversal is a strict superset of the old coverage (findings/counts can
  only become more complete, never lost); `until`-loop conditions are now
  traversed like `while`-loop conditions. (Two unrelated pre-existing analysis
  bugs remain noted but unfixed: `until` not counted in `total_loops`, and
  `--metrics`/`--security` crashing on brace-group pipelines.)
- **Shared check vocabulary (B-light)** — the unquoted-expansion predicate
  (`has_unquoted_expansion`, in new `analysis_helpers.py`) and the test-operator
  classifications (`NUMERIC_COMPARISON_OPERATORS`, `TEST_OPERATORS`, in
  `constants.py`) replace inline copies across the security/validator/linter
  visitors. Each visitor keeps its own policy (contexts, severities, messages);
  only the shared predicate/data is centralized.
- **Coverage** — added 11 tests for the previously-untested analysis visitors
  (traversal, metrics, security).

## 0.204.0 (2026-06-06) - Unify command-position classification across lexer passes
- **Command-position tracking unified (Phase 2 study §1.3, Tier C)** — the lexer
  (which tracks command position during tokenization, on `WORD`-valued keywords)
  and the keyword normalizer (which tracks it afterward, on typed keywords) are
  two distinct passes, but both classify which tokens return to command
  position. That classification now lives once in `psh/lexer/command_position.py`
  (`STATEMENT_SEPARATORS`, `CASE_TERMINATORS`, `RESET_TO_COMMAND_POSITION`,
  `COMMAND_GROUP_OPENERS`); both passes reference it.
- **Dead code removed** — the lexer's command-position set listed reserved-word
  token *types* (`IF`/`WHILE`/`THEN`/…) it can never receive (keywords are still
  `WORD` tokens during tokenization; it relies on a value-based check). These
  were removed. Behavior-preserving: token streams verified identical across a
  control-structure/case/function/`[[`/heredoc corpus.

## 0.203.0 (2026-06-06) - Unify glob→regex conversion; fix leading `]` in classes
- **Glob→regex conversion unified (Phase 2 study §1.3, Tier C)** — the
  parameter-expansion pattern operators (`#`/`##`/`%`/`%%`/`/`/`//`) and the
  extglob matcher carried two char-by-char glob→regex converters. They now share
  one implementation: `psh/expansion/extglob.py` exposes `glob_to_regex_body()`
  (the recursive converter gained an `extglob` toggle so it also handles plain
  globs), and `PatternMatcher.shell_pattern_to_regex` delegates to it while
  keeping its own anchoring contract. ~48 fewer lines in `parameter_expansion.py`.
- **Leading `]` in a character class (bug fix)** — a class beginning with `]`
  (e.g. `[]]`, `[]ab]`) is a literal-member class in POSIX; the former inline
  converter produced an invalid empty class and pattern operators raised
  "unterminated character set". Now handled correctly (verified against bash).
  6 regression tests added.

## 0.202.0 (2026-06-06) - Unify heredoc detection; fix `<<-` indented delimiter
- **Heredoc detection unified (Phase 2 study §1.3, Tier C #11)** — the
  script/`-c`/stdin path and the interactive multiline path carried two diverged
  copies of `_has_unclosed_heredoc`/`_is_inside_expansion` with *different* bugs:
  the interactive copy matched `<<` inside a `<<<` here-string (hanging waiting
  for a delimiter), and the script copy treated `<< 2` in bare `(( x << 2 ))`
  arithmetic as a heredoc (masked only by its caller's `contains_heredoc`
  guard). Both now use one authoritative implementation in
  `psh/utils/heredoc_detection.py` (`has_unclosed_heredoc`, `is_inside_expansion`)
  that rejects here-strings, excludes `<<` inside `$((`/bare `((`/`$(`/backticks,
  and handles `<<-` tab stripping and multiple/mixed heredocs. 20 new unit tests;
  net ~64 fewer lines.
- **`<<-` indented closing delimiter (bug fix)** — `<<-` now strips leading tabs
  from the *delimiter* line as well as the content (bash behavior). Previously a
  tab-indented delimiter (e.g. `\tEOF`) was never matched, so the heredoc body
  was silently lost. Fix in `psh/lexer/heredoc_collector.py`; regression test
  added.

## 0.201.0 (2026-06-06) - De-duplicate divergent reimplementations (Tier A + B)
- Consolidated same-logic copies flagged in the Phase 2 architecture study
  (§1.3). Behavior-preserving except for one bug fix noted below.
- **History-reference detection** — one `HISTORY_REFERENCE_RE` +
  `contains_history_reference()` in `history_expansion.py` replaces four
  byte-identical inline regex copies (source_processor ×2, multiline_handler,
  line_editor).
- **`parser-config` feature map** — extracted `_FEATURE_MAP` / `_POSITIVE_OPTIONS`
  class constants and a shared `_set_feature()`, collapsing two duplicated
  10-entry maps and their near-identical enable/disable bodies.
- **Foreground-job teardown** — new `JobManager.finish_foreground_job()` replaces
  the duplicated terminal-restore if/else in `pipeline.py` and `strategies.py`.
- **dirs/pushd/popd `~` display (bug fix)** — the three `_format_directory`
  copies are unified into one `format_directory_for_display()`. The two naive
  pushd/popd copies used `startswith(home)`, which mangled a sibling like
  `/home/userfoo` into `~foo`; the unified helper uses `home + os.sep`. Added
  regression tests.
- **xtrace** — executor `_print_xtrace` now delegates to
  `OptionHandler.print_xtrace`, making core the single source of truth (and
  reviving the previously-dead canonical method).

## 0.200.0 (2026-06-06) - Positional/array slicing and EXIT-trap edge cases
- **`${@:off:len}` / `${*:off:len}` / `${arr[@]:off:len}` slicing** — these now
  select elements with bash semantics instead of doing substring on the joined
  string (the old behavior only happened to match for `${@:n}` without a length).
  A shared `_slice_sequence()` helper applies arithmetic offset/length, treats a
  negative offset as counting from the end, and reports a negative length as an
  error (`@`/`*`/array slices, unlike scalar substrings, disallow from-the-end
  lengths). Positional slices index as `[$0, $1, …]` so `${@:0}` includes `$0`.
  Both the AST and string expansion paths route through the one helper.
- **Parser: `${arr[@]:1:-1}` no longer mis-parses** — the `:-` inside a slice
  operand was being matched as the use-default operator. Any operator following a
  closed array subscript is now left to the string-path parser, which resolves
  the subscript before applying the operator (also covers `${arr[0]:-def}`,
  `${arr[i+1]:-x}`, case-mod patterns, etc.).
- **EXIT trap now runs for `-c`, piped stdin, and interactive Ctrl-D** — it
  previously fired only via an explicit `exit` builtin or at the end of a script
  file. `execute_exit_trap()` is now idempotent so it fires exactly once across
  all exit paths.
- **Tests** — the four tracked edge xfails (EXIT trap, positional slice length,
  variable offset, negative array offset) are fixed and promoted to passing
  conformance cases, plus regression coverage for slice/default disambiguation
  and trap single-firing. Bash conformance: 197/199 (99.0%).

---

Entries older than v0.200.0 are archived in
`docs/archive/CHANGELOG_history.md`.
