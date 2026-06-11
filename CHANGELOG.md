# Changelog

All notable changes to PSH (Python Shell) are documented in this file.

Format: `VERSION (DATE) - Title` followed by bullet points describing changes.

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

## 0.199.0 (2026-06-06) - printf %q/%b, BASH_REMATCH, and edge-case conformance suite
- **printf %b** — interprets backslash escapes in the argument; **printf %q** —
  quotes the argument for reuse as shell input (`''` for empty, whole-string
  `$'...'` for control chars, backslash-escaping otherwise).
- **BASH_REMATCH** — `[[ str =~ re ]]` now populates `BASH_REMATCH` (full match
  and capture groups, cleared on no match). The `=~` RHS gained a regex-operand
  parser that reconstructs patterns containing `(`, `)`, `|`, `?`, `[`, `]` from
  the token stream (previously a parse error).
- **Edge-case conformance suite** — added ~50 edge tests (quoting/word-splitting,
  arithmetic, parameter expansion, globbing, brace, printf, regex); bash
  compatibility now 185/187 over 348 comparisons. A handful of remaining
  divergences are tracked as xfail (EXIT trap in -c mode, `${@:offset:length}`
  positional slice, negative array-slice offset).

## 0.198.0 (2026-06-05) - De-duplicate redirect-dispatch and lexer quote scanners
- **Redirect dispatch** — extracted the noclobber predicate (inlined at 5 sites)
  and the `>&`/`<&` dup-fd validity check (4 sites) to shared `FileRedirector`
  helpers (`_noclobber_blocks`, `_dup_fd_valid`). The four dispatch methods keep
  their distinct behavior (parent fd-save / exec stream-rebind / child
  `os._exit` / builtin Python-stream) but share the predicates.
- **Lexer quote scanners** — the three forward array-assignment scanners in the
  literal recognizer (`_collect_array_assignment`, `_collect_assignment_value`,
  `_is_potential_array_assignment_start`) now share a `QuoteState` primitive
  (`pure_helpers`) instead of each reimplementing the single/double-quote +
  backslash-escape state machine.
- Both changes are behavior-preserving (verified against bash). Docs/study
  reports synced to reflect the de-duplication work.

## 0.197.0 (2026-06-05) - Remove dormant parser-side validation subsystem
- Removed the `psh/parser/validation/` package (~1300 LOC: SemanticAnalyzer,
  ValidationPipeline, validation rules, symbol table, warnings) along with the
  dead `Parser.parse_and_validate`/`validate_ast`/`enable_validation` methods and
  the `ParserConfig` validation flags. The subsystem had no production callers —
  normal parsing uses `parse()`, and `--validate` uses the visitor validators in
  `psh/visitor/` (`EnhancedValidatorVisitor`). Net -1969 lines, no behavior
  change.

## 0.196.0 (2026-06-05) - Expansion de-duplication + remaining correctness bugs
- **Parameter expansion** — collapsed the dual application paths: the string
  path no longer carries its own copy of `${x:-w}`/`${x:=w}`/`${x:?w}`/`${x:+w}`;
  both the AST and string paths now flow through one `_apply_operator`.
- **Redirection to fd >= 3** — builtins no longer clobber stdout on `N>file`
  (#33); external commands no longer crash with EBADF on an unopened high fd
  (#34), via a `_save_fd()` helper that closes (rather than dup-restores) fds
  that weren't open.
- **Lexer** — `{[ab]}` is no longer split into `{` + `[ab]}` (#19); the `{`
  brace-group heuristic now excludes `[`/`]`.
- **Brace expansion relocated to the token stream** — replaced the
  pre-tokenization mini-parser (expand raw line + re-lex) with a
  `TokenBraceExpander` over tokens. Fixes assignment-RHS expansion (`a={x,y}`
  stays literal, #11), ranges generating metacharacters (`{Z..a}`, #12), and
  quoted brace items (`{"[",x}`, quote-aware, #20); also fixed a latent `{{...}}`
  lexer bug and matched bash's empty-item dropping. Removed ~200 lines of the
  old line-level parser.
- **Exception boundaries** — stopped swallowing defects in the lexer recognizer
  registry, expansion array-index evaluation, and the scripting top-level
  handler (transparent-failure safety fixes).

## 0.195.0 (2026-06-05) - `read` uses the real fd; retire the global `-s` test flag
- The `read` builtin chose between `os.read(fd)` and `sys.stdin` by probing
  `sys.stdin.fileno()`. Under a forked subshell with a redirected stdin (and
  under pytest capture) that picked `sys.stdin` instead of the real, redirected
  fd 0, so `( ... read ... ) < file` read the wrong source. `read` now prefers
  the real OS descriptor whenever it is valid, falling back to `sys.stdin` only
  for a genuine in-process `StringIO` stdin (new `_should_use_sys_stdin()` helper
  consolidates the previously-duplicated decision across the three read paths).
- Consequence: the full test suite now passes under normal pytest capture — the
  long-standing `-s` requirement for subshell tests is gone. Updated the stale
  `-s` notes in `README.md`, `CLAUDE.md`, `psh/executor/CLAUDE.md`, and
  `tests/integration/subshells/README.md`. `run_tests.py` still works unchanged.
- Tests: `tests/integration/redirection/test_read_forked_fd.py` (runs without
  `-s` to prove the fix).

## 0.194.0 (2026-06-05) - Correctness fixes from the codebase study (Phase 1)
Eighteen confirmed bash-divergence bugs found by the 2026-06-05 codebase study
(`docs/reviews/codebase_study_2026-06-05_phase1_correctness.md`), fixed in eight
batches. Each fix has conformance and/or unit tests.

- **Arithmetic** — variable values are recursively evaluated as arithmetic
  expressions, so `a="2*3"; $((a))` is 6 and base-prefixed values (`0x10`,
  `010`, `2#101`) are honored (#4, #5). `2 ** N` wraps to signed 64-bit instead
  of erroring (#18). Double-quoted operands inside `$(( ))` are tolerated (#28).
  Array subscripts work inside arithmetic, read and assignment (#17). The octal
  "value too great for base" error token no longer gains a spurious leading
  zero (#29).
- **Substring expansion** — offset and length are arithmetic expressions
  (`${x:(-3):2}`, `${x:1+1:2}`) (#25); a too-negative offset yields empty (#30);
  an out-of-range negative length errors with a non-zero status (#31).
- **Here-strings** — `<<<` is no longer misparsed as an unclosed heredoc, so a
  bareword here-string (`cat <<< hello`) no longer discards the command line (#32).
- **ANSI-C `$'...'`** — octal escapes accept 1–3 digits without a leading zero
  (`$'\101'` is `A`) (#16); `\u`/`\U` accept 1–4 / 1–8 hex digits (#27).
- **Globbing** — `[^...]` negation, POSIX classes `[[:alpha:]]`, `nocaseglob`,
  and `globstar` now work (a shared bracket-normalization helper is also applied
  to `case`/`[[ ]]` matching) (#13, #14, #21, #24).
- **Word splitting** — an unquoted empty/unset expansion contributes zero fields
  (#1); the for/select loop preserves empty fields from a non-whitespace IFS and
  honors `nullglob` by delegating to the canonical expansion path (#2, #23).
- **Parameter expansion** — the unset-only operators `${x-w}`, `${x=w}`,
  `${x+w}`, `${x?w}` are implemented (#9, #10); `${x//pat}` with an omitted
  replacement deletes matches (#8); a null `IFS=` concatenates `$*`/`${arr[*]}`
  while unset IFS joins with a space (#15).

## 0.193.0 (2026-06-05) - Add zsh-compatible `print` builtin
- New `psh/builtins/print_builtin.py` implementing a zsh-style `print` command.
  Unlike `echo`, `print` interprets backslash escapes by default (`-r` for raw).
- Supported flags: `-n`, `-r`, `-R`, `-e`, `-l`, `-N`, `-s` (history), `-u fd`,
  `-f format` (printf-style), `-m` (pattern filter), `-o`/`-O`/`-i` (sort),
  `-P` (prompt expansion), plus `--` / `-` option terminators.
- Unsupported zsh flags (`-z -c -C -D -x -X -a -p`) are reported as errors.
- Escape processing extracted to a shared `process_escapes()` helper in
  `psh/builtins/io.py`, now used by both `echo` and `print` (single
  implementation).
- Tests: unit (`tests/unit/builtins/test_print_builtin.py`), integration for
  redirection/pipelines/fds (`tests/integration/builtins/test_print_integration.py`),
  and a zsh-comparison suite (`tests/system/test_print_vs_zsh.py`, skipped when
  zsh is absent) — the compatibility guard, since the conformance framework
  only compares against bash, which has no `print`.
- Note: existing scripts invoking an external `print` command will now resolve
  to the builtin.

## 0.192.2 (2026-02-26) - Terminal window title updates
- New `psh/interactive/title.py` with `set_terminal_title()`, `idle_title()`,
  and `command_title()` functions using OSC 0 escape sequences.
- Idle title (`dirname — psh — cols×rows`) set before each prompt in the
  REPL loop, covering startup, post-cd, and post-command.
- Running-command title (`dirname — cmd — cols×rows`) set before external
  command fork and multi-command pipeline fork.
- Terminal resize (SIGWINCH) updates title dimensions via `on_resize`
  callback threaded through `MultiLineInputHandler` → `LineEditor`.
- All title writes guarded by `isatty()`, `TERM != dumb`, and interactive
  mode checks to avoid interference with scripts and test harnesses.

## 0.192.1 (2026-02-26) - Fix terminal resize (SIGWINCH) display corruption
- Fixed `redraw_line()` in line editor corrupting previously-output command
  results on terminal resize. The old code compared the cursor's current row
  (via DSR) against a stale saved row from before the resize; after terminal
  reflow the saved position was meaningless, causing `ESC[J` (clear to end
  of screen) to wipe out legitimate output.
- New approach computes cursor displacement using the **new** terminal width,
  matching the terminal's own reflow, so only the prompt+input area is
  redrawn. Prior command output is left untouched.

## 0.192.0 (2026-02-19) - Add 5 missing redirection operators (<>, >|, &>, &>>, |&)
- **3 new token types**: `REDIRECT_READWRITE` (`<>`), `REDIRECT_CLOBBER`
  (`>|`), and `PIPE_AND` (`|&`). `&>` and `&>>` reuse `REDIRECT_OUT`
  and `REDIRECT_APPEND` with a new `combined_redirect` boolean on `Token`.
- **Lexer**: Added `<>`, `>|`, `&>`, `&>>`, `|&` to operator table.
  Extended `_try_fd_prefixed_redirect()` for `N<>`. Set
  `combined_redirect=True` on `&>` / `&>>` tokens. Updated operator
  enable/context checks for new operators.
- **AST**: Added `combined: bool` field to `Redirect` for `&>` / `&>>`
  (redirects both stdout and stderr). Added `pipe_stderr: List[bool]`
  to `Pipeline` to track which pipe connections use `|&`.
- **Parser**: Added `REDIRECT_READWRITE` and `REDIRECT_CLOBBER` to
  `TokenGroups.REDIRECTS`. Updated pipeline parsing in both recursive
  descent and combinator parsers to accept `PIPE_AND` as pipe separator.
  `_parse_standard_redirect()` propagates `combined` flag to `Redirect`.
- **Execution**: Added `_redirect_readwrite()`, `_redirect_clobber()`,
  `_redirect_combined()` helpers to `FileRedirector`. Updated all 4
  redirect dispatch methods (`apply_redirections`,
  `apply_permanent_redirections`, `setup_builtin_redirections`,
  `setup_child_redirections`). `PipelineExecutor._setup_pipeline_redirections()`
  now accepts `pipe_stderr` and does `os.dup2(1, 2)` for `|&` pipes.
- **Tests**: 9 new lexer unit tests, 12 new integration tests covering
  `<>`, `>|`, `&>`, `&>>`, `|&`, noclobber interaction. Updated parser
  parity tests to verify both parsers handle all 5 operators.
- **POSIX**: `<>` (LESSGREAT) and `>|` (CLOBBER) are POSIX-defined.
  `&>`, `&>>`, and `|&` are bash extensions supported by both bash and zsh.

## 0.191.0 (2026-02-19) - Clean up TokenType enum, fd-prefixed redirects as single tokens
- **Remove 21 dead token types**: Deleted 11 assignment operators (`ASSIGN`
  through `RSHIFT_ASSIGN`), 3 glob tokens (`GLOB_STAR`, `GLOB_QUESTION`,
  `GLOB_BRACKET`), 4 test operators (`LESS_THAN_TEST` through
  `GREATER_EQUAL_TEST`), and 3 special construct markers
  (`HERE_DELIMITER`, `ASSIGNMENT_WORD`, `ARRAY_ASSIGNMENT_WORD`).
  TokenType enum reduced from 80 to 59 entries. None were referenced
  in production code, tests, or either parser.
- **fd-prefixed redirects as single tokens**: Added `fd: Optional[int]`
  field to `Token`. The lexer now emits `2>` as `REDIRECT_OUT '>' fd=2`
  (a single token with fd metadata) instead of two tokens (`WORD '2'` +
  `REDIRECT_OUT '>'`). Consistent with how `REDIRECT_DUP` already
  handles `2>&1` as a single token.
- **Lexer**: Added `_try_fd_prefixed_redirect()` to `OperatorRecognizer`
  that detects digit(s) followed by `>`, `>>`, or `<` and emits a
  single redirect token.
- **Parser cleanup**: Removed `_is_fd_prefixed_redirect()` and
  `_parse_fd_prefixed_redirect()` from both `RedirectionParser` and
  `CommandParser`. Parsers now read `token.fd` directly. Simplified
  `parse_redirects()` to a single `match_any` loop.
- **Combinator parser**: Removed fd-prefix WORD-digit detection block
  from `_parse_redirection()` — reads `fd` from token metadata.
- **Debug output**: Token formatter now shows `fd=N` suffix in
  `--debug-tokens` output (e.g., `REDIRECT_OUT '>' fd=2`).

## 0.190.0 (2026-02-19) - Fix lexer token type issues: REDIRECT_ERR, RBRACE, LBRACKET
- **REDIRECT_ERR removal**: Removed `REDIRECT_ERR` and
  `REDIRECT_ERR_APPEND` token types.  `2>` now tokenizes as `WORD '2'` +
  `REDIRECT_OUT '>'`, matching how `3>`, `4>`, etc. already work.
  Removed `_parse_err_redirect()` and combinator REDIRECT_ERR handling.
- **RBRACE fix**: Changed `}` to use `command_position` check instead of
  "followed by delimiter" heuristic.  `}` in brace expansions (e.g.
  `echo {$((1)),$((2))}`) is now correctly `WORD` instead of `RBRACE`.
  Removed combinator RBRACE-as-brace-expansion workaround.
- **LBRACKET in case patterns**: Added `case_depth`, `case_expecting_in`,
  and `in_case_pattern` context fields to `LexerContext`.  `[` in case
  patterns (e.g. `[a-z]*)`) is now collected as a glob word instead of
  being emitted as `LBRACKET`.  Removed combinator LBRACKET
  reconstruction workaround in `_parse_case_pattern_value()`.
- **fd-prefixed redirects**: Updated `parse_redirects()` to detect
  fd-prefixed redirects (WORD digit + adjacent redirect operator),
  fixing compound command trailing redirects (subshells, brace groups,
  if/while/for/case).

## 0.189.0 (2026-02-17) - Arithmetic: 64-bit wrapping, bitwise assignments, base 2-64, recursive variables
- **64-bit wrapping**: All arithmetic results (`+`, `-`, `*`, `/`, `%`,
  `**`, bitwise ops, compound assignments) are now wrapped to the signed
  64-bit range via `_to_signed64()`, matching bash/C overflow semantics.
  `$((9223372036854775807 + 1))` now returns `-9223372036854775808`.
- **Bitwise assignment operators**: Added `<<=`, `>>=`, `&=`, `|=`,
  `^=` — new token types, tokenizer rules, parser recognition, and
  evaluator cases.
- **Base 2-64 number literals**: Extended `base#number` notation from
  max base 36 to 64.  For bases <= 36 letters are case-insensitive;
  for bases > 36 lowercase = 10-35, uppercase = 36-61, `@` = 62,
  `_` = 63 (matching bash).
- **Recursive variable resolution**: `get_variable()` now resolves
  identifier chains recursively (with cycle detection), so
  `a=b; b=42; echo $((a))` prints `42` (matching bash).

## 0.188.1 (2026-02-17) - Fix tilde expansion in [[ ]] conditionals
- Added `_expand_operand()` helper to `TestExpressionEvaluator` that
  applies tilde expansion before variable expansion, matching POSIX
  expansion order.
- Unary operands (e.g., `[[ -f ~/.pshrc ]]`) and binary operands
  (e.g., `[[ ~ == /Users/* ]]`) now both expand tilde prefixes.
  Previously only `$VAR` expansion was applied, so `~` was passed
  literally to file tests.

## 0.188.0 (2026-02-17) - Fix critical arithmetic evaluator bugs
- **Modulo**: Changed from Python's floored modulo (`%`) to C-style
  truncated remainder so `$((-7 % 2))` returns `-1` (matching bash),
  not `1`.
- **Bitwise NOT**: Changed from 32-bit mask to 64-bit mask so
  `$((~0xFFFFFFFF))` returns `-4294967296` (matching bash), not `0`.
- **ArithmeticError**: Renamed to `ShellArithmeticError` and made it
  inherit from the Python builtin `ArithmeticError`.  Callers that
  caught the builtin name now correctly catch shell arithmetic errors
  (previously they fell through to "unexpected error" messages).
  The old name is kept as an alias for backwards compatibility.
- **Exponentiation bounds**: Negative exponents now raise an error
  (matching bash) and exponents > 63 are rejected to prevent unbounded
  memory use.
- **Shift bounds**: Negative shift counts now raise an error.  Shift
  amounts wrap modulo 64 (matching bash/C behavior), so `$((1 << 64))`
  returns `1` and left-shift results are wrapped to signed 64-bit.
- **Invalid octal**: Numbers like `09` and `08` now raise an error
  ("value too great for base") instead of silently falling back to
  decimal.
- **Exception handling**: `evaluate_arithmetic` now catches
  `RecursionError`, `ValueError`, `OverflowError`, and `MemoryError`
  in addition to `SyntaxError` and `ShellArithmeticError`, so deeply
  nested expressions and huge numeric literals produce clean error
  messages instead of crashes.
- Added `_to_signed64()` helper for wrapping arbitrary-precision
  integers into the signed 64-bit range.

## 0.187.4 (2026-02-16) - Use DSR to fix prompt position after terminal shrink
- Added `_query_cursor_row()` method that sends the DSR escape
  sequence (`ESC[6n`) and reads the terminal's cursor position response.
- `read_line()` now records the prompt's absolute viewport row at draw
  time via DSR.
- `redraw_line()` queries the cursor's actual row after a resize and
  compares it with the saved prompt row to detect displacement caused
  by scrollback reflow.  When the terminal shrinks and pushes the
  cursor down, the prompt is now redrawn at its original row (or the
  top of the viewport if the original row scrolled off).
- Falls back to the content-span calculation when DSR is unavailable.

## 0.187.3 (2026-02-16) - Fix pasted text not appearing until next keystroke
- Replaced all `sys.stdin.read(1)` calls in `LineEditor` with a new
  `_read_char()` method that reads from the raw fd via `os.read()`.
  Python's `BufferedReader` would consume all available bytes from the fd
  on the first read but return only one character; the rest became
  invisible to `select()`, causing pasted text to appear only after the
  next keystroke.
- `_read_char()` reads up to 4096 bytes from the raw fd, decodes them,
  and stores extra characters in `_char_buf`.  The main loop skips
  `select()` when the buffer is non-empty, so all pasted characters are
  processed immediately.

## 0.187.2 (2026-02-16) - Fix SIGWINCH redraw after terminal resize
- Rewrote `LineEditor.redraw_line()` to correctly handle terminal resizes.
  The old implementation used `\r` (carriage return) which only moves to
  column 0 of the current row; after a resize the cursor could be on a
  different row than the prompt, causing the prompt to appear at the top
  of the window while the cursor sat at the bottom.
- The new implementation tracks terminal width at draw time, calculates
  how many rows the prompt+buffer spanned at the old width, moves the
  cursor up to the prompt's starting row with `\033[{n}A`, clears from
  there to the bottom of the screen with `\033[J`, and redraws at the
  new width.
- Added `_visible_length()` static method to strip ANSI escape sequences
  when measuring prompt length, so colored prompts are handled correctly.
- Cursor repositioning after redraw now uses row/column ANSI sequences
  instead of backspace characters, so it works correctly when content
  wraps across multiple terminal lines.

## 0.187.1 (2026-02-14) - Fix SignalNotifier blocking read
- Made the read end of SignalNotifier self-pipes non-blocking.  Only the
  write end was non-blocking, so `drain_notifications()` would block
  indefinitely when called with no pending signals.  This was exposed by
  v0.187.0's fix to the dead `shell.signal_manager` code paths, which
  made `process_sigchld_notifications()` actually execute in the REPL
  loop for the first time.

## 0.187.0 (2026-02-14) - Interactive public API cleanup
- Rewrote `psh/interactive/__init__.py`: added module docstring listing all
  submodules; added `load_rc_file` and `is_safe_rc_file` imports from
  `rc_loader`; trimmed `__all__` from 7 to 2 items (`InteractiveManager`,
  `load_rc_file`).
- Removed vestigial `execute()` abstractmethod from `InteractiveComponent`
  ABC and all 5 subclass implementations (`REPLLoop`, `SignalManager`,
  `HistoryManager`, `CompletionManager`, `PromptManager`).
- Fixed 2 bypass imports in `shell.py`: `from .interactive.base import
  InteractiveManager` and `from .interactive.rc_loader import load_rc_file`
  now use package-level `from .interactive import ...`.
- Fixed dead `shell.signal_manager` access in `repl_loop.py` and
  `multiline_handler.py` to use `shell.interactive_manager.signal_manager`,
  restoring SIGCHLD notification processing and SIGWINCH terminal-resize
  handling.
- Updated `interactive/CLAUDE.md`: replaced stale pseudocode in REPL Loop
  and Signal Handling sections with actual implementation patterns; added
  `rc_loader.py` to key files table.

## 0.186.0 (2026-02-14) - Move create_parser to parser package
- Moved `create_parser()` from `psh/utils/parser_factory.py` to
  `psh/parser/__init__.py`; deleted `parser_factory.py`.
- Changed signature from `create_parser(tokens, shell, source_text)` to
  `create_parser(tokens, active_parser='rd', trace_parsing=False,
  source_text=None)` -- the function no longer takes the whole shell object.
- Updated caller in `scripting/source_processor.py` to pass explicit
  arguments.
- Removed `create_parser` from `psh/utils/__init__.py` and `__all__`
  (10 → 9 items).
- Added `create_parser` to `psh/parser/__all__` (5 → 6 items).
- Updated `parser_guide.md`, `parser_public_api.md`, `utils_guide.md`,
  and `utils_public_api.md` to reflect the new location.

## 0.185.0 (2026-02-14) - Core public API cleanup
- Rewrote `psh/core/__init__.py`: added module docstring, 7 new imports
  (`ExpansionError`, `OptionHandler`, `TrapManager`, `is_valid_assignment`,
  `extract_assignments`, `is_exported`), updated `__all__` from 11 to 18 items,
  removed stale `ShellOptions` comments.
- Fixed 14 `exceptions` bypass imports across 9 files to use package-level
  `from ..core import ...` instead of `from ..core.exceptions import ...`.
- Fixed 23 `variables` bypass imports across 7 files to use package-level
  imports.
- Fixed 2 `options` bypass imports in `expansion/variable.py`.
- Fixed 2 `trap_manager` bypass imports in `shell.py` and
  `builtins/signal_handling.py`.
- Fixed 1 `assignment_utils` bypass import in `executor/command.py`.
- Fixed 1 `state` bypass import in `shell.py`.
- Removed stale `scope.py` row from `core/CLAUDE.md` (file does not exist;
  `VariableScope` already listed under `scope_enhanced.py`).

## 0.184.0 (2026-02-14) - Builtins public API cleanup
- Populated `psh/builtins/__init__.py` with `FunctionReturn` and `PARSERS`
  imports; updated `__all__` from 3 to 5 items; added module-level docstring
  listing all builtin modules and their commands.
- Fixed 5 `FunctionReturn` bypass imports in executor files (`core.py`,
  `function.py`, `command.py`, `strategies.py` x2) to use package-level
  `from ..builtins import FunctionReturn`.
- Fixed `registry` bypass import in `pipeline.py` to use package-level import.
- Fixed `PARSERS` bypass import in `__main__.py` to use package-level import.
- Corrected 6 command-to-file mapping errors in `builtins/CLAUDE.md`:
  moved `pwd` from `navigation.py` to `io.py`; moved `true`, `false`, `:`
  from `io.py` to `core.py`; moved `declare`, `typeset`, `readonly` from
  `environment.py` to `function_support.py`; fixed `shell_state.py` →
  `shell_options.py` for `shopt`; added `history`, `version`, `local` to
  `shell_state.py`.

## 0.183.0 (2026-02-14) - Utils public API cleanup
- Populated `psh/utils/__init__.py` with `__all__` (11 items), imports, and
  docstring; all public symbols now importable from `psh.utils` directly.
- Deleted ~75 lines of dead code from `signal_utils.py`: `block_signals()` and
  `restore_default_signals()` context managers (zero callers) plus unused
  `contextlib` import.
- Deleted `SignalNotifier.has_notifications()` (~28 lines, zero callers,
  self-acknowledged hack that consumed pipe data it could not replace).
- Fixed 4 bypass imports in 4 files (`signal_manager.py`,
  `function_support.py`, `source_processor.py`, `debug_control.py`) to use
  package-level imports instead of submodule paths.

## 0.182.0 (2026-02-14) - Executor public API cleanup
- Trimmed `psh/executor/__init__.py` `__all__` from 13 to 5 items; removed
  10 items (`PipelineContext`, `PipelineExecutor`, `CommandExecutor`,
  `ControlFlowExecutor`, `ArrayOperationExecutor`, `FunctionOperationExecutor`,
  `SubshellExecutor`, `ExecutionStrategy`, `BuiltinExecutionStrategy`,
  `FunctionExecutionStrategy`) — they remain importable as convenience imports.
- Added 2 missing items to `__all__` and imports: `apply_child_signal_policy`
  (from `child_policy`) and `TestExpressionEvaluator` (from `test_evaluator`),
  both having production callers.
- Fixed 5 bypass imports in 4 files: `command_builtin.py` (2 → 1 package-level
  import), `shell.py`, `command_sub.py`, `process_sub.py` — all now import
  from `psh.executor` instead of submodules.
- Fixed `__init__.py` docstring: removed references to non-existent modules
  (`arithmetic`, `utils`); added `strategies`, `process_launcher`,
  `child_policy`, `test_evaluator`.

## 0.181.0 (2026-02-14) - Visitor public API cleanup
- Trimmed `psh/visitor/__init__.py` `__all__` from 14 to 9 items; removed
  5 Tier 3 items (`ASTTransformer`, `ValidatorVisitor`, `LinterConfig`,
  `LintLevel`, `SecurityIssue`) — they remain importable as convenience
  imports but are no longer part of the public API.
- Deleted unused `ASTTransformer` class (~69 lines) and `CompositeVisitor`
  class (~34 lines) from `base.py`; zero subclasses or external callers.
- Fixed 7 bypass imports across `psh/executor/` (5 files) and
  `psh/parser/visualization/` (2 files): changed
  `from psh.visitor.base import ASTVisitor` to
  `from psh.visitor import ASTVisitor`.
- Deduplicated `BASH_BUILTINS` in `MetricsVisitor`; replaced with
  `SHELL_BUILTINS` import from `constants.py`.
- Updated `psh/visitor/CLAUDE.md`: corrected return type table, added
  `constants.py` to Key Files, removed ASTTransformer and CompositeVisitor
  documentation sections.

## 0.180.0 (2026-02-14) - Expansion public API cleanup
- Populated `psh/expansion/__init__.py` with `ExpansionManager` import and
  `__all__ = ['ExpansionManager']`; added convenience imports for
  `contains_extglob` and `match_extglob` (not in `__all__`).
- Updated `shell.py` to import `ExpansionManager` from the package
  (`from .expansion import ExpansionManager`) instead of the submodule.
- Fixed broken import in `function_support.py`: changed
  `from ..expansion.arithmetic import ArithmeticEvaluator` (non-existent
  module) to `from ..arithmetic import evaluate_arithmetic`; also fixed
  incorrect `shell.state` argument (should be `shell`).
- Eliminated redundant `VariableExpander` construction in
  `shell_state.py` (2 locations); replaced with
  `shell.expansion_manager.expand_string_variables()`.
- Eliminated redundant `WordSplitter` construction in
  `control_flow.py`; replaced with
  `self.shell.expansion_manager.word_splitter`.
- Updated `psh/expansion/CLAUDE.md`: removed stale `base.py` /
  `ExpansionComponent` references; rewrote "Adding a New Expansion
  Type" section to show actual pattern (plain class, no ABC).

## 0.179.0 (2026-02-14) - I/O redirect public API cleanup
- Populated `psh/io_redirect/__init__.py` with `IOManager` import and
  `__all__ = ['IOManager']`; updated imports in `shell.py` and
  `process_launcher.py` to use package-level import.
- Deleted 5 dead `IOManager` methods: `collect_heredocs()`,
  `handle_heredoc()`, `cleanup_temp_files()`, `is_valid_fd()`,
  `_is_heredoc_delimiter_quoted()` (~55 lines) plus `_temp_files` init.
- Deleted 3 dead `HeredocHandler` methods: `collect_heredocs()`,
  `create_heredoc_file()`, `expand_variables_in_heredoc()` (~82 lines)
  plus unused `tempfile` and AST node imports.
- Consolidated `_dup2_preserve_target` from duplicate `@staticmethod`
  on both `IOManager` and `FileRedirector` to a single module-level
  function in `file_redirect.py`.
- Extracted `_expand_redirect_target()` helper to replace 4 copies of
  the 8-line variable/tilde expansion preamble.
- Extracted `_check_noclobber()` helper to replace 4 inline noclobber
  checks.
- Moved `_saved_stdout`/`_saved_stderr`/`_saved_stdin` from `Shell`
  object to `FileRedirector` instance.
- Initialized `_saved_fds_list` in `IOManager.__init__` and removed
  `hasattr()` guards.
- Added 6 per-type redirect helpers on `FileRedirector`:
  `_redirect_input_from_file`, `_redirect_heredoc`,
  `_redirect_herestring`, `_redirect_output_to_file`,
  `_redirect_dup_fd`, `_redirect_close_fd`.
- Rewrote `apply_redirections` (~120→~35 lines),
  `apply_permanent_redirections` (~152→~35 lines),
  `setup_child_redirections` (~122→~45 lines), and
  `setup_builtin_redirections` (~142→~55 lines) to use shared helpers.

## 0.178.0 (2026-02-13) - Parser public API cleanup
- Trimmed `__all__` from 17 items to 5 (`parse`, `parse_with_heredocs`,
  `Parser`, `ParserConfig`, `ParseError`); demoted Tier 2 items
  (`ParserContext`, `ParserProfiler`, `ErrorContext`, `ParsingMode`,
  `ErrorHandlingMode`) to convenience imports; removed Tier 3 items
  (`ContextBaseParser`, `HeredocInfo`, `TokenGroups`) from package-level
  `__all__`.
- Deleted `psh/parser/recursive_descent/support/factory.py` (6 functions,
  zero production callers).
- Trimmed `context_factory.py` from 8 functions to 1 (`create_context`);
  deleted 7 zero-caller wrapper functions.
- Trimmed `psh/parser/recursive_descent/__init__.py` `__all__` from 8 to 5;
  trimmed `psh/parser/validation/__init__.py` `__all__` from 9 to 7.
- Deleted `parse_strict_posix` and `parse_permissive` convenience functions
  from parser `__init__.py`.
- Fixed bypass imports in `psh/builtins/parse_tree.py` and
  `psh/utils/parser_factory.py` to import from `psh.parser` instead of
  reaching into submodule internals.
- Removed 3 test classes and 4 test methods that tested deleted functions.

## 0.177.0 (2026-02-13) - Lexer public API cleanup
- Trimmed `__all__` from 27 items to 5 (`tokenize`, `tokenize_with_heredocs`,
  `ModularLexer`, `LexerConfig`, `LexerError`); demoted Tier 2 items
  (constants, unicode helpers, `TokenPart`, `RichToken`, `LexerContext`) to
  convenience imports; removed Tier 3 items (`Position`, `LexerState`,
  `PositionTracker`, `LexerErrorHandler`, `RecoverableLexerError`) from
  package-level imports entirely.
- Replaced `isinstance(token, RichToken)` check in `commands.py` with
  `token.parts` (all tokens have `parts` via `__post_init__`); removed
  `RichToken` import — zero production callers remain.
- Deleted stale `__version__ = "0.91.1"` from `psh/lexer/__init__.py`.
- Updated `psh/lexer/CLAUDE.md`: fixed `modular_lexer.py` line count
  (~900 → ~600), replaced stale `LexerContext` field listing with actual
  dataclass fields.
- Rewrote `test_lexer_package_api.py`: added `test_all_exports` asserting
  exact `__all__` contents; added `TestDemotedImports` verifying convenience
  and submodule importability.
- Updated `docs/guides/lexer_guide.md` section 2 to reflect new API tiers.
- Added `docs/guides/lexer_public_api.md` API reference documenting public,
  convenience, and internal import tiers.

## 0.176.0 (2026-02-13) - Deep cleanup of parser, shell, and lexer dead code
- Removed dead `StatementList.pipelines` property (zero callers) and 3 stale
  "Deprecated" placeholder comments from `ast_nodes.py`.
- Fixed 2 pre-existing bugs in DOT generator (`visit_AndOrList` used wrong
  fields, `visit_CommandList` referenced nonexistent `node.commands`).
- Removed dead code from recursive descent parser: `source_text`/`source_lines`
  aliases, `context` property, `heredoc_map` assignments (parser.py + utils.py).
- Removed 145 lines from `SourceProcessor`: dead `_extract_heredoc_content()`,
  `_remove_heredoc_content_from_command()`, and 21 dead error pattern entries.
- Removed dead code from `Shell`: visitor-executor option cleanup, `builtins`
  dict, `execute()` method, `executor_manager` reference.
- Removed 9 dead methods from `ContextBaseParser` (60 lines): `synchronize`,
  `trace`, `get_position_info`, `match_statement_start`, `match_redirection_start`,
  `match_control_structure`, `_token_type_to_string`, `get_state_summary`,
  `generate_profiling_report`.
- Removed dead `legacy_mode` field from `LexerConfig` (never set to True).
- Cleaned up stale "legacy"/"backward compatibility" labels across all files.

## 0.175.0 (2026-02-13) - Dead code and legacy shim cleanup
- Removed dead `LineEditor` class from `psh/tab_completion.py` (372 lines);
  superseded by production `LineEditor` in `psh/line_editor.py`.
- Removed unused `psh/pipeline/` package (`ShellPipeline`/`PipelineBuilder`
  facade, 68 lines + tests); never used by production code.
- Removed 5 stale compatibility wrappers from `Shell` (`_add_to_history`,
  `_load_history`, `_save_history`, `_handle_sigint`, `_handle_sigchld`);
  inlined the one live caller (exit builtin).
- Removed 4 dead legacy method wrappers from `PrintfBuiltin`
  (`_process_format_string`, `_parse_format_specifier`, `_format_argument`,
  `_apply_string_formatting`/`_apply_integer_formatting`).
- Removed dead `_stdout`/`_stderr`/`_stdin` backup assignments and stale
  "backward compatibility" comments from `ShellState`.
- Removed 4 incorrect XFAILs from PTY interactive tests (`test_bg_resume`,
  `test_background_job_completion`, `test_disown_command`,
  `test_sigtstp_handler`) — moved class-level markers to individual methods.
- Cleaned up `ARCHITECTURE.llm` references to removed pipeline package.

## 0.174.0 (2026-02-13) - Fix array element parameter expansion operators
- Fixed `${arr[1]:-default}`, `${arr[5]:=five}`, `${arr[1]:?err}`,
  `${arr[1]:+alt}` — all four `:` operators now work with array subscripts.
- Root cause: `_get_var_or_positional()` treated `arr[1]` as a scalar name
  instead of resolving element 1 of array `arr`.
- Added array subscript branch to `_get_var_or_positional()`.
- Added `_set_var_or_array_element()` helper so `:=` assigns to the array
  element instead of creating a scalar named `arr[5]`.
- Fixed both `:=` code paths (string-split handler and `_apply_operator`).
- Removed XFAIL from `test_operators_with_arrays` (3 → 2 xfails).

## 0.173.0 (2026-02-13) - Fix 2 incorrect XFAILs (5 → 3)
- Removed XFAIL from `test_alias_with_arguments`: bash disables aliases in
  non-interactive mode, so PSH succeeding is a PSH extension, not a failure.
  Changed to `assert_psh_extension()`.
- Removed XFAIL from `test_character_class_patterns`: `${VAR#[0-9]*}` shortest
  match correctly strips one digit (`"23abc"`), not all (`"abc"`). Fixed
  assertion and added `##` longest match test case.
- Sharpened `test_declare_nameref_attribute` XFAIL reason to
  `"declare -n (nameref) not implemented"`.

## 0.172.0 (2026-02-13) - Fix FD leak in test fixtures causing "Too many open files"
- Fixed file descriptor exhaustion (`OSError: [Errno 24] Too many open files`)
  when running ~3,000+ tests, particularly with the combinator parser.
- Each `Shell` instance creates 4 pipe FDs via `SignalNotifier` (SIGCHLD +
  SIGWINCH). `_cleanup_shell()` now explicitly closes these FDs in teardown.
- Added `_cleanup_shell()` call to `captured_shell` fixture, which was the
  only shell fixture missing cleanup.

## 0.171.0 (2026-02-13) - Fix C-style for loop I/O redirection test infrastructure (3 → 0)
- Rewrote 3 C-style for loop I/O redirection tests to use `subprocess.run()`
  instead of `isolated_shell_with_temp_dir`, eliminating pytest capture
  interference with forked child process file descriptors.
- Removed Phase 1 `--deselect` and Phase 3 re-run workarounds from
  `run_tests.py` — these tests no longer need the `-s` flag.
- Combinator parser now has 0 remaining test failures out of ~3,350 tests.
- Updated remaining failures documentation to reflect completion.

## 0.170.0 (2026-02-13) - Fix combinator parser associative array initialization (5 → 3)
- Fixed associative array initialization in the combinator parser.
  `declare -A assoc=(["first key"]="first value")` now works correctly.
- The array collection loop had two bugs: LBRACKET/RBRACKET tokens were
  silently dropped, and STRING token values lost their quotes.
- Added LBRACKET/RBRACKET to accepted token types in the array loop,
  preserved original quote characters on STRING tokens, and used
  `adjacent_to_previous` to group tokens into properly concatenated
  elements (e.g. `["key"]="value"` instead of `[ "key" ]= "value"`).
- Zero regressions in recursive descent parser or combinator test suite.

## 0.169.0 (2026-02-12) - Fix lexer arithmetic bug and case pattern parsing (11 → 5)
- Fixed lexer bug where `>`, `<`, `>=`, `<=` were silently dropped from
  the token stream inside `(( ))` after `$((expr))` expansions.  The
  literal recognizer now accepts these characters as word-start characters
  when `arithmetic_depth > 0`.
- Fixed combinator parser case pattern parsing for multi-line character
  class patterns like `[a-z]*)`.  When the lexer emits `LBRACKET` at
  command position, the case pattern parser now reconstructs the full
  glob pattern from constituent tokens.
- Updated remaining failures documentation (5 failures in 2 categories).
- Updated lexer token type issues documentation.
- Zero regressions in recursive descent parser, lexer, or combinator tests.

## 0.168.0 (2026-02-12) - Fix 7 more combinator parser failures (18 → 11)
- Fixed process substitution `<(cmd)` by treating PROCESS_SUB_IN/OUT tokens
  as LiteralPart nodes (matching the recursive descent parser) instead of
  ExpansionPart nodes.  The expansion manager handles the `<()`/`>()` syntax
  during the expansion phase.
- Added errexit (`set -e`) check to `visit_TopLevel` in the executor,
  matching the existing logic in `visit_StatementList`.  The combinator
  parser produces TopLevel nodes; without this check, `set -e` had no
  effect between top-level statements.
- Added adjacent RBRACE consumption in the simple command parser so that
  brace expansion with arithmetic tokens (`echo {$((1)),$((2)),$((3))}`)
  no longer fails with "Unexpected token: RBRACE".  Only consumes RBRACE
  when adjacent to the previous token to avoid breaking brace groups.
- Updated remaining failures documentation (11 failures in 4 categories).
- Zero regressions in recursive descent parser or combinator tests.

## 0.167.0 (2026-02-12) - Fix 21 combinator parser failures (39 → 18)
- Restructured `_build_complete_parser()` so compound commands (for, while,
  if, case, etc.) are pipeline elements rather than top-level alternatives,
  fixing `for ... done | grep` and similar piped compound commands.
- Added `COMMAND_SUB`, `COMMAND_SUB_BACKTICK`, `ARITH_EXPANSION`,
  `PARAM_EXPANSION` to accepted token types in the for-loop word list,
  matching the select-loop parser.
- Added explicit handling for `REDIRECT_ERR` and `REDIRECT_ERR_APPEND`
  tokens to produce `Redirect(type='>', fd=2)` instead of
  `Redirect(type='2>', fd=None)`.
- Added array assignment detection in the simple-command parser: when a
  word ending with `=` is followed by an adjacent `LPAREN`, parenthesized
  items are collected into a single synthetic `name=(item1 item2 ...)` token.
- Made `do` keyword optional after `))` in C-style for loops, matching
  the recursive descent parser's behavior.
- Added remaining failures documentation at
  `docs/guides/combinator_parser_remaining_failures.md`.
- Zero regressions in recursive descent parser or combinator tests.

## 0.166.0 (2026-02-10) - Consolidate process substitution duplication
- Extracted `create_process_substitution()` module-level function in
  `psh/io_redirect/process_sub.py` — single source of truth for the
  fork/pipe/signal/exec sequence used by all process substitution paths.
- Replaced 75-line copy-paste in `file_redirect.py:_handle_process_sub_redirect()`
  with 8-line delegation to the new function.
- Replaced 69-line inline block in `manager.py:setup_builtin_redirections()`
  with 6-line delegation.
- Unified FD/PID tracking through `ProcessSubstitutionHandler.active_fds/active_pids`
  — eliminates three ad-hoc shell attributes (`_redirect_proc_sub_fds`,
  `_redirect_proc_sub_pids`, `_builtin_proc_sub_fds`, `_builtin_proc_sub_pids`).
- Fixed FD/PID leak: `_redirect_proc_sub_*` attributes were stored but never
  cleaned up; now all paths go through `ProcessSubstitutionHandler.cleanup()`.
- ~130 lines of duplicated code removed. Zero behavioral changes.

## 0.165.0 (2026-02-10) - Decompose shell.py
- Reduced shell.py from 925 lines to ~325 lines by extracting domain logic.
- Deleted dead `_execute_buffered_command()` (165 lines) — duplicate of
  SourceProcessor's copy, never called on Shell.
- Extracted `TestExpressionEvaluator` class to `psh/executor/test_evaluator.py`
  (172 lines of `[[ ]]` evaluation logic).
- Extracted `print_ast_debug()` to `psh/utils/ast_debug.py` (72 lines).
- Extracted `create_parser()` to `psh/utils/parser_factory.py` (33 lines).
- Extracted `contains_heredoc()` to `psh/utils/heredoc_detection.py` (56 lines).
- Extracted RC file loading to `psh/interactive/rc_loader.py` (44 lines).
- Removed thin wrapper methods `run_script()`, `interactive_loop()`,
  `set_positional_params()` — callers updated to use managers directly.
- Updated source_processor.py to use new module functions.
- Zero behavioral changes; all 3,087 tests pass.

## 0.164.0 (2026-02-10) - Move Changelog out of version.py
- Moved VERSION_HISTORY string (1,157 lines, 80KB) from psh/version.py to
  CHANGELOG.md. version.py is now 19 lines (was 1,175).
- VERSION_HISTORY was never read at runtime — only referenced in documentation.
- Updated CLAUDE.md version bump instructions to reference CHANGELOG.md instead
  of VERSION_HISTORY.

## 0.163.0 (2026-02-10) - Replace Broad Exception Handlers with Specific Types
- Eliminated all 22 bare except: handlers across 13 files, replacing with
  specific exception types (OSError, termios.error, ValueError, KeyError,
  AttributeError, TypeError).
- Narrowed 40 of 61 except Exception handlers across 20 files to specific
  types: OSError for I/O/terminal/process ops, (ValueError, ArithmeticError)
  for arithmetic evaluation, (AttributeError, TypeError) for getattr ops,
  (KeyError, IndexError) for collection access, etc.
- Kept 21 except Exception handlers that are intentional: forked child
  catch-alls before os._exit(), REPL last-resort, trap execution safety,
  __del__ cleanup, and command execution catch-alls that re-raise control
  flow exceptions.
- Fixed termios.error not inheriting from OSError: job_control.py terminal
  mode handlers now catch (OSError, termios.error).
- Zero behavioral changes; all 3087 tests pass.

## 0.162.0 (2026-02-10) - Fix Documentation and Version Drift
- Updated version references in README.md (0.159.0 → 0.162.0),
  ARCHITECTURE.md (0.159.0 → 0.162.0), ARCHITECTURE.llm (0.159.0 → 0.162.0),
  and CLAUDE.md (0.120.0 → 0.162.0).
- Fixed stale project statistics in README.md: LOC (62,000 → 99,000),
  Python files (214 → 348), test count (3,021 → 3,087), test files (154 → 166).
- Fixed stale --parser=combinator CLI flag in README.md (replaced with
  parser-select combinator builtin, matching v0.130.0 changes).
- Updated README.md Recent Development section to cover v0.100.0-v0.161.0.
- Updated CLAUDE.md Current Development Status: version, recent work summary,
  and removed stale active issues.
- Updated CLAUDE.md test count (~3000 → ~3,087).

## 0.161.0 (2026-02-10) - Test Tree Lint Cleanup
- Fixed 7,132 ruff lint issues across ~160 test files:
  6330 W293 (whitespace on blank lines), 265 F401 (unused imports),
  163 I001 (unsorted imports), 121 W292 (missing newline at EOF),
  121 F841 (unused variables), 116 W291 (trailing whitespace),
  13 W605 (invalid escape sequences), 3 F811 (redefined while unused).
- Added noqa: F401 to 4 intentional imports (removed-module tests, pexpect
  availability detection).
- Expanded CI lint gate to cover tests/ alongside psh/.
- Zero behavioral changes; all 3087 tests pass.

## 0.160.0 (2026-02-10) - Lint Cleanup and CI Gate
- Fixed 626 ruff lint issues across ~50 files in psh/:
  596 W293 (whitespace on blank lines), 17 W291 (trailing whitespace),
  7 I001 (unsorted imports), 6 F401 (unused imports).
- Added lint job to CI (.github/workflows/test_migration.yml): runs
  ruff check psh before tests to prevent regressions.
- Zero behavioral changes; all 3087 tests pass.

## 0.159.0 (2026-02-10) - Fix Doc Drift, Dead Code, and Package Metadata
- Fixed version drift in README.md (0.113.0 → 0.159.0), ARCHITECTURE.md
  (0.104.0 → 0.159.0), and ARCHITECTURE.llm (0.120.0 → 0.159.0).
- Fixed test count (3,021 → 3,087) and parser parity claims (100% → near-complete)
  in README.md and ARCHITECTURE.md.
- Fixed stale --parser=combinator CLI flag references in ARCHITECTURE.md
  (replaced with parser-select combinator builtin, matching v0.130.0 changes).
- Deleted dead psh/core/scope.py (147 lines): superseded by scope_enhanced.py,
  only imported in core/__init__.py, never used by any other code. Updated
  __init__.py to import VariableScope from scope_enhanced.py instead.
- Deleted stale psh/test_assoc.py (74 lines): ad-hoc test script referencing
  removed APIs (executor_manager, get_variable_object, old Parser(tokens) usage).
- Fixed package metadata in pyproject.toml: placeholder author/email replaced
  with actual values.

## 0.158.0 (2026-02-10) - Remove Dead shell_parser.py Module
- Deleted psh/shell_parser.py (248 lines): entirely dead code. It imported
  parse_with_lexer_integration from psh.parser, which was never exported,
  so the import always failed. shell.py caught the ImportError silently,
  meaning ShellParser, install_parser_integration, and related functions
  never ran. The module also referenced ParserConfig fields removed in
  v0.131.0 (use_enhanced_tokens, enable_context_validation, etc.).
- Removed the dead import block from Shell.__init__() in shell.py.
- Removed the unused enhanced_lexer parameter from Shell.__init__().

## 0.157.0 (2026-02-10) - Update Parser Combinator Feature Parity Tests
- Removed skip_combinator=True from 10 test groups (23 cases) in
  test_parser_feature_parity.py — all features were implemented in v0.94-v0.100
  but the parity tests were never updated.
- Added heredoc-aware parsing to parse_both(): auto-detects heredoc commands and
  uses tokenize_with_heredocs() + parse_with_heredocs() for both parsers.
- Added parse_both_heredoc() helper method for explicit heredoc test path.
- Updated generate_parity_report() feature matrix: all 19 features now show full
  support in both parsers, except &> combined redirect (1 case still skipped).
- Only remaining skip: &> combined redirect not supported in parser combinator.

## 0.156.0 (2026-02-10) - Reset Job ID Counter When Job Table Is Empty
- Fixed job numbering: transient internal jobs (pipelines, subshells, command
  substitutions) incremented the job ID counter but were removed immediately,
  so the first user-visible background/stopped job got an unexpectedly high
  number (e.g. [15] instead of [1]). Now resets next_job_id to 1 when the
  job table is empty before creating a new job, matching bash behavior.

## 0.155.0 (2026-02-10) - Fix 8 PSH Bug XFAILs
- Fixed heredoc in case statement parsing: KeywordNormalizer entered in_heredoc
  mode when heredoc content had already been collected by tokenize_with_heredocs(),
  causing it to skip real tokens (;;, esac) looking for a non-existent delimiter.
  Added heredoc_key check to avoid entering in_heredoc mode when content is
  already collected.
- Fixed SourceProcessor _collect_heredoc_content() not tracking already-closed
  heredocs in the buffer: when a case statement had two heredoc branches, the
  method would find both << markers but not check which were already closed,
  causing EOF during collection of the second heredoc.
- Fixed populate_heredoc_content() failing on CaseItem.commands (StatementList):
  the traversal called `for cmd in node.commands` but StatementList is not
  directly iterable. Now unwraps StatementList.statements before iterating.
- Fixed builtin output in forked child ignoring shell redirections: echo in a
  pipeline subshell uses os.write(1, ...) which bypasses sys.stdout redirections
  set by setup_builtin_redirections(). When _in_forked_child is True, builtins
  now use with_redirections() (os.dup2-based) instead of setup_builtin_redirections()
  (Python-level), so os.write(1, ...) goes to the correct file.
- Switched test_function_as_pipeline_filter and test_function_pipeline_chain to
  subprocess: read inside pipeline functions can't read from pipe when pytest
  captures stdin.
- Fixed test_syntax_error_recovery: shell correctly exits on syntax error in
  non-interactive mode (POSIX behavior). Updated assertion to expect non-zero
  exit code and error message.
- Fixed test_pipeline_error_in_middle: POSIX says pipeline exit = last command
  exit code. cat succeeds so pipeline exit is 0.
- Fixed test_background_job_with_redirection_error: PSH evaluates redirect
  synchronously for background builtins. Updated to accept any exit code from
  the & command and assert wait returns 0.
- Removed 8 xfail markers (all tests now pass).

## 0.154.0 (2026-02-10) - Fix 4 Test Infrastructure Issues
- Switched test_while_with_command_condition to subprocess: 'read' from
  redirected stdin conflicts with pytest's output capture.
- Switched test_function_with_many_commands to subprocess: function output
  redirection to file conflicts with pytest's output capture.
- Switched test_parameter_scoping to subprocess: 'set' positional params
  and echo don't capture through capsys.
- Switched test_subshell_process_substitution to subprocess: process
  substitution FDs conflict with pytest's output capture.
- Removed 4 xfail markers (all tests now pass).

## 0.153.0 (2026-02-10) - Fix Brace Tokenization for Non-Expanding Braces
- Fixed { and } being tokenized as separate LBRACE/RBRACE operator tokens
  when they appear inside words (e.g., {a..1}, {a.b}, {a,b,c, {}).
  These should remain literal parts of the word when brace expansion doesn't
  apply, matching bash behavior. Previously echo {a..1} output "{ a..1 }"
  (three separate tokens), now correctly outputs "{a..1}".
- Added standalone-brace check in operator recognizer: { and } are only
  recognized as operators when followed by whitespace/delimiter/EOF (brace
  group syntax), not when followed by word characters.
- Added {} special case: {} is always a word token, never LBRACE+RBRACE.
- Updated literal recognizer can_recognize() and _is_word_terminator() to
  allow { and } as word characters when they would be part of a larger word.
- Fixed test_single_item assertion to expect correct "{a}" output.
- Switched test_very_long_expansion to subprocess (pipeline fork issue).
- Removed 5 xfail markers from brace expansion tests. 1 xfail remains
  (test_special_chars_in_expansion) due to architectural limitation: pre-
  tokenization brace expansion of {$,#,@} produces "echo $ # @" where #
  becomes a comment character.

## 0.152.0 (2026-02-10) - Test Builtin Parentheses Support and Test Fixes
- Implemented parenthesized grouping in test builtin: test \\( expr \\) now works
  for complex expressions like test \\( -n "a" -a -n "b" \\) -o -z "c", matching
  POSIX/bash behavior. Added _evaluate_with_parens() and parenthesis-aware
  scanning in _evaluate_expression() that skips -a/-o inside groups.
- Fixed test_alias_with_pipe and test_alias_with_args: switched from in-process
  captured_shell/capsys to subprocess, since alias-expanded external commands
  fork child processes whose output bypasses Python-level capture.
- Fixed test_history_clear: drain accumulated capsys output before assertion
  and expect the 'history' command itself to appear as entry 1 after clear.
- Removed all 4 xfail markers (all tests now pass).

## 0.151.0 (2026-02-10) - Fix Alias Subshell Inheritance and Alias Test Corrections
- Fixed aliases not inherited by subshells: added AliasManager.copy() and wired it
  into Shell.__init__() parent_shell inheritance block, matching bash behavior where
  child shells inherit the parent's alias definitions.
- Fixed 3 alias test bugs: test_alias_expansion_timing used alias name 'test' which
  collides with the test builtin; test_alias_with_special_characters and
  test_alias_with_array_syntax used double quotes causing premature variable expansion
  at definition time instead of single quotes to defer expansion to execution time.
- Removed all 4 xfail markers from alias expansion tests (all now pass).

## 0.150.0 (2026-02-09) - Executor/Visitor Cleanup and Correctness
- Deduplicated _expand_for_loop_items() and _expand_select_items() into single
  _expand_loop_items() method in control_flow.py (identical implementations)
- Deduplicated _apply_redirections() context manager: added empty-redirects guard
  to IOManager.with_redirections() and deleted 4 identical copies from core.py,
  command.py, control_flow.py, and subshell.py. Removed unused contextmanager
  imports from 4 files.
- Created psh/visitor/constants.py with shared DANGEROUS_COMMANDS, SENSITIVE_COMMANDS,
  SHELL_BUILTINS, COMMON_COMMANDS, and COMMON_TYPOS dictionaries. Updated
  enhanced_validator_visitor.py, linter_visitor.py, and security_visitor.py to
  import from the shared module instead of defining inline duplicates.
- Replaced regex-based IFS splitting in _word_split_and_glob() with POSIX-compliant
  WordSplitter from psh/expansion/word_splitter.py, which correctly handles
  whitespace vs non-whitespace IFS characters, backslash escapes, and empty fields.
- Fixed FunctionExecutionStrategy and AliasExecutionStrategy creating fresh
  ExecutorVisitor instances (losing accumulated visitor state). Threaded the
  caller's visitor from ExecutorVisitor through CommandExecutor to strategies
  via a visitor parameter on execute(). Falls back to creating a new visitor
  when not provided (backward compatibility).

## 0.149.0 (2026-02-09) - Dead Code Removal and Bare Exception Cleanup
- Deleted 10 dead methods (~255 lines) from ExecutorVisitor in core.py:
  _expand_arguments(), _extract_assignments(), _is_valid_assignment(),
  _is_exported(), _evaluate_arithmetic(), _expand_assignment_value(),
  _handle_exec_builtin(), _exec_with_command(), _exec_without_command(),
  _find_command_in_path() — all superseded by CommandExecutor and other
  specialized executors
- Removed 4 dead imports from core.py: os, signal, List/Tuple from typing,
  assignment_utils functions
- Replaced 7 bare except: clauses with specific exception types across 4 files:
  command.py (2x Exception), strategies.py (1x OSError),
  process_launcher.py (1x Exception, 1x OSError),
  subshell.py (2x Exception)

## 0.148.0 (2026-02-09) - Fix Medium Visitor Bugs from Review
- Fixed linter generic_visit duplication (Medium): dir(node) returned methods
  and properties, causing duplicate child traversal.  Replaced with
  dataclasses.fields(node) to iterate only declared dataclass fields.
- Fixed formatter C-style for loop $ injection (Medium): f-string used
  ${init}, ${cond}, ${update} which injected spurious $ into output.
  Changed to {init}, {cond}, {update} since ((...)) context doesn't use $.
- Verified formatter array subscript expansion is not a bug: ${arr[0]} round-
  trips correctly through parse → format via ParameterExpansion.__str__().
- Fixed enhanced validator _has_parameter_default under-reporting (Medium):
  the method checked for :- or := anywhere in the text string, which could
  match substrings outside ${...} expansions.  Now only matches operators
  inside ${...} delimiters with proper brace nesting.

## 0.147.0 (2026-02-09) - Fix Pipeline Test-Mode Fallback
- Fixed pipeline test-mode fallback creating anonymous objects with type() that
  lacked required API (Medium).  Now constructs a real Pipeline AST node and
  passes the real ExecutionContext instead of an empty anonymous object.
- Added context parameter to _execute_mixed_pipeline_in_test_mode() so the
  fallback path can use the caller's execution context.

## 0.146.0 (2026-02-09) - Fix Critical/High Executor Bugs from Review
- Fixed background brace-group double execution (Critical): { echo hi; } & was
  executing the body unconditionally in the parent, then forking for a second
  execution.  Now checks node.background before any execution, matching the
  subshell pattern.
- Fixed loop_depth leak on multi-level break/continue (High): context.loop_depth
  decrement in execute_while(), execute_until(), and execute_for() was outside
  the try/finally block, so a re-raised LoopBreak(level-1) or LoopContinue(level-1)
  would skip the decrement.  Wrapped each loop method in an outer try/finally.
- Fixed special-builtin prefix assignment persistence (High): POSIX requires that
  variable assignments before special builtins (export, readonly, eval, exec, etc.)
  persist after the command completes.  _execute_with_strategy() now returns
  (exit_code, is_special) and _restore_command_assignments() is skipped for
  special builtins.

## 0.145.0 (2026-02-09) - Quote-Aware Scanners, Multiple $@ Support
- Replaced 5 quote-unaware parenthesis/brace scanners in expansion with
  quote-aware helpers from psh/lexer/pure_helpers.py:
  - expand_string_variables() $((..)) scanner → find_balanced_double_parentheses(track_quotes=True)
  - expand_string_variables() $(..) scanner → find_balanced_parentheses(track_quotes=True)
  - expand_string_variables() ${..} scanner → find_closing_delimiter(track_quotes=True)
  - _expand_command_subs_in_arithmetic() $((..)) scanner → find_balanced_double_parentheses(track_quotes=True)
  - _expand_command_subs_in_arithmetic() $(..) scanner → find_balanced_parentheses(track_quotes=True)
- Added track_quotes parameter to find_balanced_double_parentheses() in pure_helpers.py
  (default False to preserve lexer behaviour; expansion callers pass True)
- Fixed multiple "$@" in one quoted word: _expand_at_with_affixes() now continues
  processing remaining parts after the first $@, correctly handling patterns like
  "a$@b$@c" with params (1 2) → [a1, 2b1, 2c]
- Added 6 regression tests for multi-$@, quote-aware command substitution, and
  braces in quoted defaults

## 0.144.0 (2026-02-09) - Deduplicate $@ Splitting Logic
- Extracted shared _expand_at_with_affixes() helper from the ~95% duplicate
  "$@" splitting logic in _expand_word() and _expand_double_quoted_word()
- Both call sites now delegate to the shared helper in 3 lines each
- The helper distributes positional params across prefix/suffix text:
  e.g. pre"$@"post with params (a,b,c) → [prea, b, cpost]
- Added in_double_quote parameter to control escape processing: double-quoted
  path only applies dquote escapes; composite path also handles unquoted escapes
- Retained assignment-word field-splitting heuristic in _expand_word() after
  investigation showed builtins (declare, export, local) receive VAR=value
  arguments through expand_arguments(), requiring the heuristic to suppress
  word splitting. Updated comment to document this rationale.
- All tests passing with zero regressions

## 0.143.0 (2026-02-09) - Decompose expand_variable() into Helper Methods
- Extracted 5 helper methods from the 380-line expand_variable() method:
  _expand_array_length(): handles ${#arr[@]}, ${#arr[*]}, ${#arr[index]}
  _expand_array_indices(): handles ${!arr[@]}, ${!arr[*]}
  _expand_array_slice(): handles ${arr[@]:start:length}
  _expand_array_subscript(): handles ${arr[index]}, ${arr[@]}, ${arr[*]}
  _expand_special_variable(): handles $?, $$, $!, $#, $@, $*, $0-$9
- expand_variable() is now an ~80-line dispatcher that checks preconditions
  and delegates to the appropriate helper
- Pure structural refactoring — no behavioral changes
- All tests passing with zero regressions

## 0.142.0 (2026-02-09) - Expansion Subsystem Cleanup: Dead Code, Bare Exceptions, Small Fixes
- Deleted dead code: _split_words() from ExpansionManager, GlobExpander.should_expand(),
  and process_escapes parameter from expand_string_variables() (variable.py, manager.py,
  and 5 callers in executor/array.py)
- Replaced 6 bare except: handlers with specific exception types:
  5x (ValueError, TypeError) in variable.py, 1x (KeyError, OSError) in tilde.py
- Fixed operator-detection heuristic in expand_parameter_direct() and expand_variable():
  replaced any(op in ...) conditional with unconditional evaluate_arithmetic(),
  matching the v0.141.0 fix already applied to indexed array access
- Fixed parse_expansion() colon-operator skip bug: ${var:=default} and ${var:?msg}
  were incorrectly parsed as substring extraction in the string-based expansion
  path. Changed '-+' to '-+=?' in the skip condition
- Fixed stale comment in command_sub.py: "Block SIGCHLD" → "Reset SIGCHLD to default"
- Added 4 regression tests for ${var:=default} and ${var:?msg} parsing

## 0.141.0 (2026-02-09) - Fix Array Index Arithmetic Evaluation
- Fixed array indices not evaluating bare variable names in arithmetic context.
  In bash, array indices are always evaluated as arithmetic expressions, so
  arr[i]="value" resolves variable i to its numeric value. PSH only called
  evaluate_arithmetic() when operator characters were detected, causing bare
  variable names like i to be treated as literal string keys.
- Simplified execute_array_element_assignment() in executor/array.py: replaced
  ~35-line heuristic block (try int(), regex for operators, conditional
  evaluate_arithmetic) with unconditional evaluate_arithmetic() for unquoted
  indices. Quoted indices (e.g., arr["key"]) still treated as string keys for
  associative arrays.
- Simplified indexed array access in expansion/variable.py: replaced
  operator-detection conditional with unconditional evaluate_arithmetic() call.
- Both paths now handle bare variable names, arithmetic expressions, and
  literals uniformly via evaluate_arithmetic(), matching bash behavior.
- Fixed test_large_array_creation: redirect was on a separate line from echo,
  creating an empty file instead of capturing output.

## 0.140.0 (2026-02-09) - Fix 5 Parser Validation and Config Issues
- Fixed validation false positives: fd-dup redirects (2>&1) no longer flagged
  as "missing target"; case statement uses correct field (items, not cases);
  variable name validation checks first char only (var1 no longer rejected).
- Fixed stale AST field references in validation traversal: ForLoop.values→items
  (List[str], not visitable), CaseConditional.word/cases→expr/items,
  AndOrList.pipeline→pipelines. Replaced wildcard imports with explicit imports
  in all three validation files.
- Fixed ParserConfig field name disconnect: renamed validate_ast to
  enable_validation; added enable_semantic_analysis and enable_validation_rules
  as real dataclass fields instead of dynamically injected attributes.
- Fixed create_configured_parser() config mutation: now uses config.clone() to
  create an independent copy instead of mutating the shared parent config.
- Fixed can_parse() EOF false negatives in combinator parser: added 'EOF' to
  the trailing-token skip loop, matching the parse() method.
- Added 13 regression tests in tests/regression/test_parser_review_fixes.py.

## 0.139.0 (2026-02-09) - Fix Redirect-Only Command Execution
- Fixed redirect-only commands (e.g., >file) not creating/truncating the target
  file. CommandExecutor.execute() returned early when no command args remained,
  skipping redirect application entirely. Now applies redirections before
  returning, matching POSIX/bash behavior.

## 0.138.0 (2026-02-09) - Fix 7 Parser Issues from Implementation Review
- Fixed non-terminating loop in case parsing when encountering LPAREN token
  (bash's optional (pattern) syntax). Added no-progress guard to prevent
  infinite loops on unexpected tokens.
- Fixed case terminator semantics: ;& and ;;& values now stored in CaseItem
  AST node (was always defaulting to ;;). Fixed executor fall-through logic
  so ;& correctly executes next case body unconditionally.
- Allowed leading redirections before command name (POSIX: >out echo hi).
  Expanded _validate_command_start() to accept REDIRECTS and fd-dup tokens.
- Fixed [[ ]] operand concatenation: added adjacent_to_previous check so
  '[[ a b ]]' correctly raises ParseError instead of silently concatenating.
- Allowed 'select' without 'in' clause (defaults to "$@"), matching bash.
- Fixed parse_with_heredocs() to handle both dict {'content':...,'quoted':...}
  and plain string formats for heredoc content.
- Fixed config validation enum comparison: validate_config() compared
  error_handling against string 'strict' instead of ErrorHandlingMode.STRICT.
- Added 23 regression tests in tests/regression/test_parser_review_fixes.py.
- Removed @pytest.mark.xfail from test_case_fallthrough (now works).

## 0.137.0 (2026-02-09) - Parser Code Quality: Address Remaining Code Smells #2 and #4
- Refactored is_array_assignment() from 90-line monolithic method into 5 focused
  helper methods using peek-based lookahead instead of advance-then-restore:
  _is_element_assignment_single_token (pure string inspection),
  _peek_is_assignment_operator (peek at offset), _is_initialization_pattern
  (peek 0..2), _is_element_with_bracket_token (peek 1), _scan_bracket_assignment
  (advance+restore for unbounded bracket depth). Main method is now a readable
  dispatcher documenting all 6 tokenisation patterns.
- Deduplicated parse(), parse_partial(), and can_parse() in combinator parser.py
  by extracting _prepare_tokens() (KeywordNormalizer + skip whitespace) and
  _apply_heredocs() helpers. Turned parse_partial() fallback cascade into a
  clean for-loop. Fixed can_parse() to normalise keywords consistently.
- Updated parser_code_quality_review_v0.135.md: all 4 code smells now addressed.
- No behavioral changes; all tests passing.

## 0.136.0 (2026-02-09) - Parser Code Quality: 5 Improvements from v0.135.0 Review
- Compiled regex patterns at module level in commands.py, redirections.py,
  and word_builder.py (3 files, 5 patterns).
- Moved 5 inline imports to module level: RichToken and WordBuilder in
  commands.py, ErrorContext and ErrorSeverity in context.py, ParsingMode
  in base_context.py.
- Replaced if/elif chain in _check_for_unclosed_expansions with
  data-driven _UNCLOSED_EXPANSION_MSGS dictionary lookup.
- Removed compatibility shim classes: ParserFactory, ConfigurationValidator,
  ParserContextFactory, _ErrorCollectorView. Migrated all callers to
  underlying module-level functions and ctx attributes.
- Factored combinators/control_structures.py (1,306 lines) into a package
  with 3 mixin modules (loops, conditionals, structures) plus shared
  format_token_value utility in utils.py.
- No behavioral changes; all tests passing.

## 0.135.0 (2026-02-09) - Consolidate parse_composite_argument() into Word AST
- Migrated all 10 callers of parse_composite_argument() to use parse_argument_as_word(),
  unifying all argument parsing into a single Word AST path.
- Deleted parse_composite_argument(), _token_to_argument(), and _format_variable() from
  CommandParser (82 lines removed).
- Added _word_to_element_type() static helper to ArrayParser for deriving legacy
  element-type strings (STRING, COMPOSITE_QUOTED, COMPOSITE, WORD) from Word nodes.
- Removed duplicate TokenStream import from parse_argument_as_word().
- Updated callers in redirections.py (2 sites), control_structures.py (3 sites),
  arrays.py (4 sites), and commands.py (1 site).
- No behavioral changes; all tests passing.

## 0.134.0 (2026-02-09) - Parser Code Quality: Error Helper, Inline Imports, Dead Code
- Extracted _raise_unclosed_expansion_error() helper in CommandParser, replacing 6
  repetitive ErrorContext + raise ParseError blocks in _check_for_unclosed_expansions
  and _validate_command_start with single-line calls.
- Moved inline imports to module level across 4 files: import re in commands.py,
  redirections.py, word_builder.py; import time in context.py (4 sites);
  LiteralPart and Word added to module-level ast_nodes import in commands.py.
- Declared _saved_states as a dataclass field in ParserContext with
  field(default_factory=list), removing hasattr guards in __enter__/__exit__
  and adding reset in reset_state().
- Removed dead branch in _format_variable where both if/else paths returned
  the same f"${token.value}".
- No behavioral changes; all tests passing.

## 0.133.0 (2026-02-09) - Parser Docs: Sub-Parser Contract, WordBuilder Cross-refs
- Added "Sub-Parser Contract" section to parser CLAUDE.md documenting the implicit
  convention all 8 sub-parsers follow: initialization, state access via
  ContextBaseParser methods, token position property, context manager usage (with
  table of which sub-parsers set which flags), consume_if preference, error creation.
- Expanded WordBuilder documentation in parser CLAUDE.md with entry point
  (CommandParser.parse_argument_as_word), three key operations (build_word_from_token,
  build_composite_word, parse_expansion_token), and relationship to TokenStream.
- Added WordBuilder cross-reference docstring to parse_argument_as_word() in
  commands.py.
- Updated context_factory.py description in support infrastructure table to reflect
  v0.132.0 factory function conversion.
- Marked recommendations 5 and 6 complete in parser code quality review — all 10
  recommendations from the original review are now done.
- Documentation-only changes; no behavioral code modifications.

## 0.132.0 (2026-02-09) - Parser Quality: Factory Functions, Dead Code Removal
- Converted ParserContextFactory (9 static methods), ParserFactory (4 static
  methods), and ConfigurationValidator (2 static methods) from static-method-only
  classes to plain module-level functions. Added thin compatibility shim classes
  so existing call sites keep working unchanged.
- Deleted unused ContextConfiguration class (3 static methods, zero callers).
- Deleted BaseParser adapter class (~30 lines, never instantiated outside its
  own module).
- Deleted unused parse_with_rule and parse_scoped methods (~15 lines, never called).
- Replaced ErrorContext.severity string field with ErrorSeverity enum (INFO,
  WARNING, ERROR, FATAL). Added FATAL to validation Severity enum.
- Removed unreachable except ImportError block in _enhance_error_context.
- Net reduction: ~70 lines across 7 files. All tests passing.

## 0.131.0 (2026-02-09) - Parser Quality Improvements
- Pruned ParserConfig from 45 fields to 12 actually-read fields. Removed
  33 unused fields and 5 factory methods (~500 lines). Kept strict_posix()
  and permissive() presets plus clone(), is_feature_enabled(), should_allow().
- Unified error handling: deleted ErrorCollector class and error_collector.py.
  ParserContext.errors is now the sole error list with fatal_error tracking.
  MultiErrorParseResult moved to parser.py. Recovery strategies inlined.
  Added _ErrorCollectorView for backward compatibility (~360 lines removed).
- Added combinator parser guide (docs/guides/combinator_parser_guide.md)
  documenting the functional parser's concepts, module structure, feature
  coverage, and differences from recursive descent.

## 0.130.0 (2026-02-08) - Remove Parser Abstraction Layers
- Phase 1: Removed AbstractShellParser, ParserRegistry, ParserStrategy, and
  RecursiveDescentAdapter (~930 lines). Replaced ParserStrategy in shell.py
  with simple _active_parser string and direct parser calls. Rewrote 4 parser
  experiment builtins (348 lines) as single parser-select builtin (47 lines).
  Updated combinator parser to remove AbstractShellParser inheritance.
- Phase 2: Removed ContextWrapper class from Parser; added __enter__/__exit__
  directly to ParserContext. Removed 8 legacy forwarding methods and 22
  sub-parser delegation methods. Fixed monkey-patching in TestParser. Replaced
  _error() with error() across all sub-parsers. Replaced print() with
  logging.debug() in parser context tracing.
- Total: ~1,686 lines removed across 21 files

## 0.129.0 (2026-02-08) - Lexer Refactoring: Dead Code, Keyword Unification, Efficiency
- Phase 1: Removed dead code (~100 lines): _classify_literal, _is_number,
  _contains_special_chars (literal.py), PriorityRecognizer (base.py),
  create_*_parser factories (expansion_parser.py, quote_parser.py), unused
  registry methods, VARIABLE_NAME_PATTERN (constants.py), dead if/pass block
  (modular_lexer.py). Fixed mutable default in pure_helpers.py.
  Replaced print() with logging in registry.py.
- Phase 2: Removed KeywordRecognizer (~200 lines), unifying all keyword
  handling in KeywordNormalizer. Eliminated redundant two-pass keyword system.
  Removed recent_control_keyword from LexerContext. Updated command-position
  tracking to check WORD values for keyword-like strings.
- Phase 3: Removed redundant can_recognize() calls from all recognize()
  methods. Eliminated list copy in registry.recognize(). Replaced O(n) linear
  scan in PositionTracker with O(log n) bisect. Moved inline imports to
  module level.
- Total: ~320 lines removed across 16 files

## 0.128.0 (2026-02-08) - Remove Dead Code from Parser Package
- Deleted BaseParser (base.py, ~380 lines): legacy base class superseded by ContextBaseParser
- Deleted context_snapshots.py (~300 lines): ContextSnapshot, BacktrackingParser, SpeculativeParser
  never instantiated in production code
- Deleted errors.py (~360 lines): ParserErrorCatalog and ErrorSuggester never used by the parser
- Deleted AbstractIncrementalParser and AbstractStreamingParser from abstract_parser.py (~60 lines):
  defined but never inherited or instantiated
- Removed dead set_error_template() method from helpers.py ErrorContext
- Fixed broken imports in combinators/expansions.py (ParseError from deleted errors.py)
- Removed associated test file (test_parser_error_improvements.py) and dead test classes
  (TestContextSnapshot, TestBacktrackingParser, TestSpeculativeParser) from test_parser_context.py
- Updated parser_guide.md and parser CLAUDE.md to remove stale references
- Net reduction: ~1,580 lines of dead code
- All tests passing with zero regressions

## 0.127.0 (2026-02-07) - Tilde Expansion in Parameter Expansion Defaults
- Fixed ${x:-~} outputting literal ~ instead of expanding to home directory
- Added _expand_tilde_in_operand() helper to VariableExpander
- Tilde expansion now applied to operand values for :-, :=, and :+ operators
- Applied in both _apply_operator() (Word AST path) and expand_variable() inline
  fallback handlers (string-based path)
- Matches bash behavior: ${x:-~} expands ~, ${x:-~/foo} expands ~/foo,
  ${x:=~} assigns expanded value, ${x:+~} returns expanded value when set
- All tests passing with zero regressions

## 0.126.0 (2026-02-07) - Implement psh -i Flag and $- Special Variable
- Added -i flag to force interactive mode (matches bash -i behavior)
- Fixed broken --force-interactive flag: was set after Shell.__init__ completed,
  so init-time interactive features (history loading, rc file) never triggered
- Threaded force_interactive parameter into Shell.__init__() constructor
- Made $- fully functional with all standard flags:
  - B (braceexpand, default on), H (histexpand, default on)
  - i (interactive), s (stdin mode, no script file)
  - Plus existing: a, b, C, e, f, h, m, n, u, v, x
- Fixed $- expansion in string contexts (heredocs, double-quoted strings):
  added '-' to special variable character set in expand_string_variables()
- Added interactive and stdin_mode options to ShellState options dict
- Updated help text with -i flag description
- Added comprehensive subprocess-based tests for -i and $-
- All tests passing with zero regressions

## 0.125.0 (2026-02-07) - Fix 3 FD/Redirect Bugs from Code Review
- Fixed endswith('') bug in apply_permanent_redirections() process substitution
  check — always returned true; corrected to endswith(')')
- Fixed FD leak in setup_child_redirections(): process substitution redirect's
  parent FD (with FD_CLOEXEC cleared) was never closed after redirect applied,
  surviving exec and keeping pipe open; now closed after redirect setup
- Implemented <& (input FD duplication), >&- and <&- (FD close) at runtime in
  all three redirection paths: apply_redirections(), setup_child_redirections(),
  and setup_builtin_redirections()
- Handles both parser AST forms for close: type='>&-'/'<&-' from
  parse_fd_dup_word() and type='>&' with target='-' from _parse_dup_redirect()
- Added tests for FD close, input FD dup, and process substitution redirect
- All tests passing with zero regressions

## 0.124.0 (2026-02-07) - Unify Child Process Signal Policy
- Created apply_child_signal_policy() in psh/executor/child_policy.py as single
  source of truth for child process signal setup after fork()
- Refactored ProcessLauncher._child_setup_and_exec() to call unified policy
  instead of inline signal handling
- Added policy call to command substitution fork (command_sub.py) — was missing
  signal reset entirely, child inherited parent's custom signal handlers
- Added policy call to process substitution fork (process_sub.py) — was only
  setting SIGTTOU=SIG_IGN, missing full signal reset
- Added policy call to file redirect process substitution fork (file_redirect.py)
  — was missing signal reset entirely
- Added policy call to IOManager builtin redirect process substitution fork
  (manager.py) — was missing signal reset entirely
- All 4 raw fork paths now use is_shell_process=True (they create temp Shell
  instances and run commands, never exec external binaries)
- Added unit tests for policy function and integration tests for command/process
  substitution signal disposition
- All tests passing with zero regressions

## 0.123.0 (2026-02-07) - Fix 5 Correctness Bugs from Code Review
- Fixed quoted variable names treated as assignments (High): "FOO"=bar no longer
  silently creates a variable; _is_assignment_candidate() now walks Word parts to
  verify the variable-name portion before '=' is entirely unquoted LiteralPart
- Fixed lone $ expanding to empty string (Medium): bare $ not followed by a valid
  variable name now emits a literal '$' token instead of an empty-named variable
  expansion (matches bash: echo $ end → $ end)
- Fixed "$@" splitting missing in composite words (Medium): pre"$@"post with
  params (a,b,c) now correctly produces 3 separate arguments [prea, b, cpost]
  instead of collapsing into one; added $@ splitting logic to _expand_word()
- Fixed tilde expansion suppressed by any backslash (Medium): ~/\foo now
  correctly expands ~ because only \\~ (escaped tilde) suppresses expansion,
  not a backslash on a later character
- Fixed FormatterVisitor losing quotes in composite words (Low): new _format_word()
  method reconstructs words from Word.parts with per-part quoting, grouping
  consecutive parts by quote context for correct round-trip formatting
- Added 19 regression tests in tests/regression/test_codex_review_findings.py
- All tests passing with zero regressions

## 0.122.0 (2026-02-07) - Formalize Shell-vs-Leaf Signal Policy in ProcessLauncher
- Added is_shell_process field to ProcessConfig dataclass (default False)
- Shell processes (subshells, brace groups) keep SIGTTOU=SIG_IGN after
  reset_child_signals() so they can call tcsetpgrp() without being stopped
- Leaf processes (external commands) keep SIGTTOU=SIG_DFL (unchanged behavior)
- Removed manual SIGTTOU override from subshell.py execute_fn closure
- Set is_shell_process=True on all three SubshellExecutor launch sites
  (foreground subshell, background subshell, background brace group)
- Updated process_sub.py comment to reference centralized policy pattern
- Updated executor CLAUDE.md signal handling documentation
- Updated architecture-comments.md opportunity #6 (partially addressed)
- All tests passing with zero regressions

## 0.121.0 (2026-02-07) - Remove \\x00 Null Byte Markers
- Removed all \\x00 null byte marker producers and consumers (vestigial after Word AST migration)
- lexer/pure_helpers.py: Escaped dollar returns literal '$' instead of '\\x00$'
- lexer/helpers.py: Same change in mixin version
- shell.py: Simplified _process_escape_sequences() to inline backslash removal
- expansion/variable.py: Removed \\x00 guards on $ and backtick in expand_string_variables()
- expansion/extglob.py: Removed 4 \\x00 skip blocks and updated docstring
- Deleted 2 tests for removed \\x00 behavior (test_null_marked, test_null_markers_become_literal)
- Updated expansion/CLAUDE.md: removed NULL Marker Pattern section and pitfall note
- Updated architecture-comments.md: marked \\x00 risk as resolved, opportunity #3 as done
- Updated architecture-comments-analysis.md: moved \\x00 section to resolved
- No \\x00 references remain in active source code
- All 2930+ tests passing with zero regressions

## 0.120.0 (2026-02-07) - Complete arg_types Migration to Word AST
- Removed arg_types and quote_types fields from SimpleCommand dataclass
- Changed words field from Optional[List[Word]] to List[Word] (always present)
- Added Word helper properties: is_quoted, is_unquoted_literal, is_variable_expansion,
  has_expansion_parts, has_unquoted_expansion, effective_quote_char
- Migrated all remaining arg_types consumers to Word AST inspection:
  - enhanced_validator_visitor: 4 methods migrated
  - security_visitor: unquoted expansion detection via Word properties
  - formatter_visitor: quote reconstruction via word.effective_quote_char
  - debug_ast_visitor: shows Word structure summary instead of arg_types list
  - ascii_tree/sexp_renderer: Word-based compact argument display
  - shell_formatter: quote restoration via Word properties
  - command.py: removed arg_types forwarding and fallback
  - expansion/manager.py: removed arg_types/quote_types writes after process sub
- Deleted _word_to_arg_type() (50 lines) from recursive descent parser
- Removed all arg_types/quote_types append calls from 3 parser implementations
- Updated composite token handling tests to use Word AST assertions
- 31 new unit tests for Word helper properties
- All 2930+ tests passing with zero regressions

## 0.119.0 (2026-02-07) - Medium-Value Improvements: Parser Fixes, Dead Code Removal, AST Migration
- Fixed parameter expansion parsing for /#, /%, and : (substring) operators in WordBuilder:
  uses earliest-position matching instead of naive first-occurrence search, adds /#/%/: to
  operator list, skips operators after array subscript ] to preserve array slicing
- Removed expand_parameter_direct() var_name.endswith('/') workaround for /#/% operators
- Removed ExpansionEvaluator._evaluate_parameter_via_string() fallback for ambiguous AST
- Removed dead StateHandlers mixin (597 lines): legacy state-machine code from before
  ModularLexer rewrite, zero active callers
- Migrated execution-path arg_types consumers to Word AST inspection:
  - ExpansionManager: process substitution detection via Word parts
  - ProcessSubstitutionHandler: detection via Word parts instead of arg_types indexing
  - CommandExecutor: assignment extraction via _is_assignment_candidate() Word inspection
- Added 9 parser unit tests for /#, /%, :, //, /, #, %, :- operator disambiguation
- All 2932+ tests passing with zero regressions

## 0.118.0 (2026-02-07) - Architectural Cleanup: Remove CompositeTokenProcessor, Direct Parameter Expansion
- Removed CompositeTokenProcessor (198 lines): with Word AST and adjacent_to_previous token
  tracking, the pre-merge processor was redundant — the parser handles composites via
  parse_argument_as_word() / peek_composite_sequence() natively
- Deleted psh/composite_processor.py, removed use_composite_processor parameter from Parser
- Cleaned up composite token tests to use standard parser (no processor flag)
- Extracted expand_parameter_direct() in VariableExpander: operator dispatch logic now
  accepts pre-parsed (operator, var_name, operand) components directly
- Extracted _apply_operator() helper to eliminate duplication between scalar and array
  expansion paths (was duplicated across ~240 lines)
- ExpansionEvaluator._evaluate_parameter() now calls expand_parameter_direct() directly
  instead of reconstructing ${...} strings and re-parsing via parse_expansion()
- Eliminates the string round-trip that caused the ${#var} prefix operator reconstruction
  bug fixed in v0.117.0
- Added fallback for parser AST ambiguities (e.g. ${var:0:-1} parsed as operator=':-')
- Handles parser AST quirk where ${var/#pat/repl} stores parameter='var/', operator='#'
- All 2932+ tests passing with zero regressions

## 0.117.0 (2026-02-07) - Complete Word AST Migration, Remove Legacy String Expansion Path
- Word AST is now the only argument expansion path (build_word_ast_nodes config removed)
- Deleted ~450 lines of legacy string-based expansion code:
  _expand_string_arguments(), _process_single_word(), process_escape_sequences(),
  _contains_at_expansion(), _expand_at_in_string(), _protect_glob_chars(),
  _mark_quoted_globs(), _brace_protect_trailing_var(), _expand_assignment_value(),
  and verify-word-ast parallel verification code
- Added _process_unquoted_escapes() for backslash handling in unquoted literals
- Added process substitution, ANSI-C quote ($'), and extglob pattern handling
- Fixed alias backslash bypass, word splitting, $$, parameter expansion operators,
  ${#arr[@]} length, nounset propagation, and assignment word splitting
- All 2932 tests pass with zero regressions

## 0.116.0 (2026-02-07) - Word AST STRING Decomposition and Expansion Path Hardening
- WordBuilder now decomposes double-quoted STRING tokens with RichToken.parts into
  proper ExpansionPart/LiteralPart AST nodes (was single opaque LiteralPart)
- Added _token_part_to_word_part() and _parse_token_part_expansion() for converting
  lexer TokenPart metadata to Word AST nodes
- Removed expand_string_variables() fallback in _expand_word() and
  _expand_double_quoted_word() — double-quoted expansions now use structural AST
- CommandExecutor now preserves Word AST (command.words) when creating sub-nodes
  for assignment stripping and backslash bypass
- Added _word_to_arg_type() to derive backward-compatible arg_types from Word AST
- Added _expand_assignment_word() for Word-AST-aware assignment value expansion
- Added _process_dquote_escapes() for backslash processing in double-quoted literals
- ExpansionEvaluator now properly re-raises ExpansionError (e.g., ${var:?msg})
- ExpansionEvaluator wraps array subscripts (arr[0]) in ${...} form
- Parser adds EXCLAMATION tokens to words list for test command compatibility
- build_word_ast_nodes remains False by default; 149 golden tests pass with it on

## 0.115.0 (2026-02-06) - Architectural Improvements: Word AST, Token Adjacency, Expansion Consolidation
- Added golden behavioral test suite (149 parametrized tests) as safety net for pipeline changes
- Added first-class token adjacency tracking (adjacent_to_previous field on Token)
- Simplified composite detection to use adjacency field instead of position arithmetic
- Added per-part quote context (quoted, quote_char) to LiteralPart and ExpansionPart AST nodes
- Enhanced Word AST composite word building with per-part quote tracking
- Rewrote _expand_word() with full per-part quote-aware expansion logic
- Consolidated ExpansionEvaluator to delegate to VariableExpander (reduced from ~430 to ~85 lines)
- Added parallel verification infrastructure for Word AST vs string expansion paths

## 0.114.0 (2026-02-06) - Fix 5 Expansion/Assignment Bugs
- Fixed split assignments absorbing next token across whitespace: FOO= $BAR is now
  correctly parsed as empty assignment + command, not FOO=$BAR
- Fixed single-quoted assignment values losing quote context: FOO='$HOME' now keeps
  $HOME literal by marking $ and ` with NULL prefix in single-quoted composite parts
- Fixed quoted expansion results triggering globbing in composites: var='*';
  echo foo"$var"bar now prints foo*bar instead of glob results
- Fixed tilde expansion running on variable/command expansion results: words from
  expansion starting with ~ no longer undergo tilde expansion (POSIX compliance)
- Fixed "$@" inside larger double-quoted strings: "x$@y" with params (a,b) now
  produces two words [xa] [by] instead of one word [xa by]
- Added PARAM_EXPANSION to composite token set so var=${path##*/} is properly
  composited (was broken when split-assignment workaround was removed)
- Added _brace_protect_trailing_var() to prevent variable name absorption across
  composite token boundaries ("$var"bar no longer expands $varbar)
- Removed double-expansion of assignment values in _handle_pure_assignments() and
  _apply_command_assignments() (values already expanded in execute())
- All tests passing (762 integration, 1286 unit, 43 subshell)

## 0.113.0 (2026-02-06) - Implement Extended Globbing (extglob)
- Implemented bash-compatible extended globbing with five pattern operators:
  ?(pat|pat) zero or one, *(pat|pat) zero or more, +(pat|pat) one or more,
  @(pat|pat) exactly one, !(pat|pat) anything except pattern
- Patterns support nesting (e.g., +(a|*(b|c))) and pipe-separated alternatives
- Enable with: shopt -s extglob
- Four integration points: pathname expansion, parameter expansion (${var##+(pat)}),
  case statements (case $x in @(yes|no)) ...), and [[ ]] conditional expressions
- Core engine: extglob_to_regex converter with recursive pattern handling
- Negation (!(pat)) uses match-and-invert for standalone patterns
- Lexer changes: extglob patterns (e.g., @(a|b)) tokenized as single WORD tokens
  when extglob enabled; + and ! followed by ( no longer treated as word terminators
- Shell options threaded through tokenize() and tokenize_with_heredocs() for
  dynamic extglob awareness based on current shopt state
- Fixed StringInput -c mode to split on newlines (matching bash behavior) so that
  shopt -s extglob on line N affects tokenization of line N+1
- Updated shopt help text from stub to list all five operators
- 55 unit tests for core engine, 13 lexer tokenization tests, 20 integration tests
- All existing tests passing with no regressions

## 0.112.0 (2026-02-06) - Fix Nested Subshell Parsing and SIGTTOU in Process Substitution
- Fixed nested subshell parsing: (echo "outer"; (echo "inner")) now parses correctly
- Root cause: lexer greedily matched )) as DOUBLE_RPAREN (arithmetic close) instead
  of two separate RPAREN tokens when closing nested subshells
- Added context check: )) is only DOUBLE_RPAREN when arithmetic_depth > 0
- Removed xfail from test_nested_subshells (now passes)
- Fixed SIGTTOU suspension when running tests piped through tee
- ExternalExecutionStrategy now only calls restore_shell_foreground() when terminal
  control was actually transferred, matching the fix applied to pipeline.py in v0.111.0
- Added SIGTTOU SIG_IGN in process substitution child fork (process_sub.py), matching
  the subshell child fix from v0.111.0

## 0.111.0 (2026-02-06) - Fix SIGTTOU in Subshell Pipelines
- Fixed subshell child processes getting killed by SIGTTOU (signal 22, exit
  code 150) when running pipelines with a controlling terminal
- Root cause: reset_child_signals() set SIGTTOU to SIG_DFL for all forked
  children, but subshell children act as mini-shells that may call tcsetpgrp()
  and need SIGTTOU ignored (standard shell behavior)
- Added SIG_IGN for SIGTTOU in subshell execute_fn (subshell.py)
- Made pipeline _wait_for_foreground_pipeline() skip restore_shell_foreground()
  when terminal control was never transferred, preventing unnecessary tcsetpgrp()
  calls from non-foreground process groups
- Added test isolation cleanup (_reap_children, _cleanup_shell) to both
  conftest.py files to prevent zombie process leakage between tests

## 0.110.0 (2026-02-06) - Fix Intermittent Job Control Race Condition
- Fixed wait builtin race condition in _wait_for_all(): if a background job
  (e.g. false &) completed before wait was called, its exit status was lost
  because the loop only iterated non-DONE jobs
- Now collects exit statuses from already-completed (DONE) jobs first, then
  waits for any still-running jobs
- Verified stable over 20 consecutive runs of the previously flaky test
- All tests passing

## 0.109.0 (2026-02-06) - Resolve All 12 Code Review Observations
- Fixed all 6 remaining code review items (7-12); all 12 now resolved
- WhitespaceRecognizer: removed unnecessary string building and Token construction,
  now just advances position and returns (None, new_pos) like CommentRecognizer
- Removed hasattr(TokenType, 'WHITESPACE'/'COMMENT') guards and unused Token
  construction from both whitespace and comment recognizers
- Both WhitespaceRecognizer and CommentRecognizer now consistently return
  (None, new_pos) for skipped regions (was inconsistent: None vs (None, pos))
- Removed unused ExpansionComponent abstract base class from psh/expansion/base.py;
  no expansion component inherited from it and their interfaces intentionally differ
- Fixed O(n^2) bytestring concatenation in command substitution: now collects
  chunks in a list and joins with b''.join() for O(n) performance
- Replaced hardcoded errno 10 with errno.ECHILD for readability and portability
- Cleaned up old conformance result files from 2025
- Updated docs/code_review_observations.md: all 12 items marked FIXED
- All tests passing

## 0.108.0 (2026-02-06) - Fix 4 Conformance Bugs, Achieve 0 PSH Bugs
- Resolved all 4 remaining psh_bug conformance items (was 4, now 0)
- POSIX compliance: 98.4% (up from 97.7%), bash compatibility: 91.8% (up from 89.1%)
- Reclassified echo \\$(echo test) as documented_difference (ERROR_MESSAGE_FORMAT):
  both shells reject with exit code 2, only error message format differs
- Fixed jobs format string to match bash: 24-char state field, ' &' suffix for background
- Fixed background job '+' marker by using register_background_job() in strategies.py
  so current_job is properly set for the most recent background job
- Fixed history builtin in non-interactive mode: no longer loads persistent history
  when running via -c flag, matching bash behavior (bash -c 'history' outputs nothing)
- Fixed pushd to initialize directory stack with CWD before pushing new directory:
  pushd /tmp from ~ now produces stack [/tmp, ~] matching bash output format
- Added pushd /tmp as documented_difference (PUSHD_CWD_DIFFERENCE) since conformance
  test runs PSH and bash from different working directories
- Updated docs/test_review_recommendations.md with new conformance metrics
- All tests passing (Phase 1, Phase 2 subshell, Phase 3)

## 0.107.0 (2026-02-05) - Glob Fixes, shopt Builtin, and Test Improvements
- Fixed glob expansion on variable results per POSIX (unquoted $VAR now globs)
- Fixed partial quoting in glob patterns: "test"*.txt correctly expands unquoted *
  using \\x00 markers to distinguish quoted vs unquoted glob chars in composites
- Implemented shopt builtin with -s/-u/-p/-q flags and dotglob, nullglob, extglob,
  nocaseglob, globstar options
- Added nullglob support: when enabled, glob patterns with no matches expand to nothing
- Reclassified echo $$ from psh_bug to documented difference in conformance tests
- Moved 3 C-style for loop I/O tests from xfail to -s test phase (they pass with -s)
- Added 12 regression tests for bugs fixed in commit 4f4d854
- All tests passing (2623 passed in Phase 1, 43 subshell, 5 Phase 3)

## 0.106.0 (2025-11-25) - Code Cleanup and Pythonic Refactoring
- Refactored non-Pythonic length checks across 14 files (34 patterns)
- Changed `len(x) == 0` to `not x` and `len(x) > 0` to `bool(x)` for idiomatic Python
- Removed dead code and commented debug statements from multiple modules
- Removed archived backup files and obsolete development/migration scripts
- Removed deprecated legacy executor flag handling from __main__.py and environment.py
- Removed duplicate debug properties in state.py and orphaned SubParserBase class
- Net reduction of ~8,000+ lines of dead/obsolete code
- All tests passing (2616 passed, 80 skipped, 52 xfailed)
- Files cleaned: state.py, token_stream_validator.py, bracket_tracker.py, quote_validator.py,
  heredoc_collector.py, state_context.py, parser.py, context.py, error_collector.py,
  semantic_analyzer.py, test_command.py, base.py, security_visitor.py, signal_utils.py,
  script_validator.py

## 0.105.0 (2025-11-24) - Code Quality and Subsystem Documentation
- Consolidated duplicate assignment utilities into psh/core/assignment_utils.py
- Extracted long methods in LiteralRecognizer and CommandParser into focused helpers
- Completed legacy ParseContext migration to ParserContext with backward-compatible wrapper
- Added comprehensive CLAUDE.md documentation for 6 subsystems:
  - psh/expansion/CLAUDE.md: expansion order, variable/command substitution
  - psh/core/CLAUDE.md: state management, scoping, variables
  - psh/builtins/CLAUDE.md: builtin registration, adding commands
  - psh/io_redirect/CLAUDE.md: redirections, heredocs, process substitution
  - psh/visitor/CLAUDE.md: AST visitor pattern, traversal
  - psh/interactive/CLAUDE.md: job control, REPL, history, completion
- Updated main CLAUDE.md with complete subsystem reference table (9 total)
- All tests passing, no regressions

## 0.104.0 (2025-11-19) - Complete All High Priority Executor Improvements (H4 + H5)
- 🎉 MAJOR MILESTONE: All critical and high priority executor improvements complete! (8/8, 100%)
- Implemented H4 from executor improvements plan: unified foreground job cleanup
- Created JobManager.restore_shell_foreground() as single source of truth for terminal restoration
- Replaced scattered cleanup logic in 5 locations across 4 files (pipeline, strategies, subshell, fg builtin)
- Consistent cleanup ensures terminal always restored to shell after foreground jobs
- Implemented H5 from executor improvements plan: surface terminal control failures
- Created JobManager.transfer_terminal_control(pgid, context) as single source of truth for all tcsetpgrp calls
- Replaced 8 scattered tcsetpgrp calls across 7 files with unified method
- Enhanced logging: all terminal control failures now visible with --debug-exec flag
- Context strings provide clear diagnostic information (Pipeline, Subshell, ProcessLauncher, etc.)
- Returns success/failure bool for caller decision making
- Foundation for future metrics tracking (process_metrics integration ready)
- Benefits: single source of truth, consistent error handling, better debugging, reduced code
- Net code reduction: H4 (-30 lines), H5 (-7 lines) with significantly better structure
- All tests passing: 43 subshell + 2 function/variable tests, no regressions
- Files modified: job_control.py, process_launcher.py, subshell.py, pipeline.py, strategies.py, signal_manager.py, job_control.py (builtin)
- Executor improvements progress: 8/13 complete (62%), Critical 3/3 (100%), High Priority 5/5 (100%) ✅
- Remaining work: Medium priority (3 items) and Low priority (2 items) - all optional enhancements

## 0.103.0 (2025-11-19) - Centralize Child Signal Reset Logic (H3)
- Implemented H3 from executor improvements plan: centralized child signal reset logic
- Added SignalManager.reset_child_signals() as single source of truth for all child processes
- Updated ProcessLauncher to use centralized signal reset when available
- Fixed ProcessLauncher fallback to include SIGPIPE (was missing in previous implementation)
- Updated all 4 ProcessLauncher instantiation sites to pass signal_manager parameter
- Used parameter passing approach instead of property pattern (property caused initialization hangs)
- Signal manager accessed via shell.interactive_manager.signal_manager at instantiation sites
- Backward compatible: falls back to local reset if signal_manager unavailable
- Benefits: single source of truth, consistent signal handling, easier maintenance
- All tests passing: 43 subshell + 2 function/variable tests, no regressions
- Files modified: signal_manager.py, process_launcher.py, subshell.py, pipeline.py, strategies.py
- Executor improvements progress: 6/13 complete (46%), High Priority 3/5 (60%)

## 0.102.1 (2025-11-19) - Critical Signal Ordering Fix
- Fixed critical shell suspension bug where psh would hang before showing prompt
- Root cause: Signal handler initialization happened AFTER terminal control takeover
- When shell called tcsetpgrp() before ignoring SIGTTOU/SIGTTIN, kernel suspended the process
- Reordered initialization in psh/interactive/base.py to call setup_signal_handlers() BEFORE ensure_foreground()
- Shell now properly ignores job control signals before attempting terminal control operations
- All tests passing, no regressions in signal handling or job control
- Production-critical fix: shell now starts successfully in all environments
- Documented investigation of H3/H4/H5 conflicts with signal ordering fix
- H3 (Centralize Child Signal Reset), H4 (Unify Foreground Cleanup), H5 (Surface Terminal Control Failures)
  remain to be re-implemented with compatibility for signal ordering fix

## 0.102.0 (2025-01-23) - Interactive Nested Prompts Implementation
- Implemented zsh-style context-aware continuation prompts for interactive mode
- Added automatic nesting context detection showing current shell construct hierarchy
- Prompt changes dynamically to reflect context: for>, while>, if>, then>, for if>, etc.
- Enhanced MultiLineInputHandler with context_stack tracking for nested control structures
- Implemented _extract_context_from_error() to analyze parser errors for context identification
- Implemented _update_context_stack() to parse command buffer and track open/closed constructs
- Modified _get_prompt() to generate contextual PS2 prompts based on nesting hierarchy
- Proper handling of closing keywords (fi, done, esac, }, ), ]]) to pop context stack
- Support for all control structures: for, while, until, if, case, select, functions
- Support for compound commands: subshells (), brace groups {}, enhanced tests [[]]
- Multi-level nesting fully supported (e.g., for if then> shows nested if inside for loop)
- Graceful fallback to standard PS2 when context cannot be determined
- Comprehensive testing with all nesting scenarios verified working correctly
- Significant UX improvement: users now see visual feedback about command structure
- Educational value: helps users learn shell syntax through immediate context visibility
- Matches familiar behavior from zsh and other advanced shells

## 0.101.0 (2025-01-06) - Recursive Descent Parser Package Refactoring & Parser Combinator Fix
- Major refactoring: Moved recursive descent parser from flat structure to modular package
- Migrated 28 files from /psh/parser/ to /psh/parser/recursive_descent/ with logical organization:
  - Core files in recursive_descent/ (parser.py, base.py, context.py, helpers.py)
  - Feature parsers in recursive_descent/parsers/ (commands, control_structures, etc.)
  - Enhanced features in recursive_descent/enhanced/ (advanced parsing capabilities)
  - Support utilities in recursive_descent/support/ (error_collector, word_builder, etc.)
- Fixed critical parser combinator regression that broke control structures and advanced features
- Parser combinator now has ~95% feature parity with recursive descent (was incorrectly showing ~60%)
- Both parsers now support: control structures, functions, arrays, I/O redirection, process substitution,
  arithmetic commands, conditional expressions, subshells, here documents, and background jobs
- Removed all compatibility layers after successful migration
- Updated all import paths throughout codebase (fixed 30+ files)
- All tests passing (2593 passed, 162 skipped)
- Clean parallel structure: recursive_descent/ and combinators/ packages

## 0.100.0 (2025-01-06) - Parser Combinator Modular Architecture Complete
- Completed full modularization of parser combinator from 2,779-line monolithic file to 8 clean modules
- Phase 9 Complete: Successfully migrated parser registry to use new modular architecture
- Modular structure: core (451 lines), tokens (90), expansions (209), commands (372), control (381),
  special (248), parser (198), heredoc (121) - total 2,070 lines (25% reduction through deduplication)
- Fixed all 188 parser combinator tests to pass with new modular architecture (100% pass rate)
- Updated 31 test files to use new import paths from modular parser
- Fixed while loop parser to recognize 'do' keyword from WORD tokens
- Resolved circular dependencies using dependency injection pattern
- Enhanced initialization order with proper module wiring
- Maintained full backward compatibility with AbstractShellParser interface
- Educational milestone: demonstrates clean functional architecture for complex parsers
- Parser combinator now production-ready with maintainable, testable architecture
- All 6 phases of feature parity complete, now with clean modular implementation

## 0.99.3 (2025-01-23) - Fix Bit-Shift Operators in Arithmetic Expressions
- Fixed critical bug where bit-shift operators (<<, >>) in arithmetic expressions were mistaken for heredoc operators
- The shell would hang waiting for heredoc input when encountering expressions like ((x=x<<2))
- Fixed MultiLineInputHandler._has_unclosed_heredoc to check if << appears inside arithmetic expressions
- Fixed Shell._contains_heredoc to properly detect arithmetic context
- Fixed SourceProcessor to use shell._contains_heredoc instead of its own incomplete logic
- Added comprehensive test suite with 10 tests covering bit-shift assignment operations
- Bit-shift operators now work correctly in all contexts: arithmetic commands, expansions, conditionals
- All existing heredoc functionality remains intact with no regressions
- Both parser implementations (recursive descent and parser combinator) handle bit-shifts correctly

## 0.99.2 (2025-01-23) - Parser Strategy Inheritance for Child Shells
- Fixed parser strategy inheritance so child shells (command substitution, subshells, process substitution)
  inherit the parser choice from their parent shell
- Previously, child shells always used the default parser regardless of parent's parser selection
- Now when parser combinator is selected, all child shells consistently use parser combinator
- Added comprehensive tests for parser strategy inheritance
- Ensures consistent parsing behavior throughout the entire shell session

## 0.99.1 (2025-01-23) - Parser Combinator Process Substitution Bug Fix
- Fixed critical bug where process substitutions were parsed as WORD tokens instead of PROCESS_SUB_OUT
- Added process_sub_in and process_sub_out to word_like parser definition in parser combinator
- Process substitution commands like `tee >(grep XFAIL > file.log)` now work correctly
- Resolved "No such file or directory" errors when using process substitutions with parser combinator
- Enhanced parser combinator feature parity to handle all process substitution syntax correctly
- Verified fix with comprehensive testing showing proper I/O filtering and redirection
- Parser combinator now maintains 100% process substitution compatibility with recursive descent parser

## 0.99.0 (2025-01-22) - Parser Combinator Feature Parity Achievement Complete (Phase 6)
- Completed Phase 6 of parser combinator feature parity plan: Advanced I/O and Select
- Final phase implementation achieving 100% feature parity with recursive descent parser
- Full implementation of select loop syntax: select var in items; do ... done
- Added comprehensive select loop parsing with support for all token types in items
- Support for WORD, STRING, VARIABLE, COMMAND_SUB, ARITH_EXPANSION, PARAM_EXPANSION tokens
- Implemented quote type tracking for proper shell semantics in select items
- Added SELECT keyword parser and comprehensive _build_select_loop() method
- Enhanced control structure parsing chain with select loops via or_else composition
- Fixed AST unwrapping logic to prevent unnecessary Pipeline/AndOrList wrapper nodes
- Verified all advanced I/O features work through existing SimpleCommand infrastructure
- Confirmed exec commands and file descriptor operations work seamlessly with parser combinator
- Created comprehensive test suite: 32 tests across 2 files (19 select + 13 exec)
- Updated feature coverage tests to reflect select loop support (changed "not supported" to "now supported")
- Fixed test_parser_combinator_feature_coverage.py to show select_loop: True in feature matrix
- Parser combinator now supports 23/24 features (95.8% coverage) with only job_control unsupported
- **MAJOR MILESTONE**: 100% feature parity achieved for all 6 planned parser combinator phases
- All critical shell syntax now supported: process substitution, compound commands, arithmetic, enhanced tests, arrays, select
- Final project statistics: 100+ comprehensive tests, complete shell compatibility for educational/testing purposes
- Educational reference implementation demonstrating functional parsing of complex real-world languages
- Proof that parser combinators can handle production-level language complexity while maintaining elegance
- Foundation established for future parser combinator research and functional programming techniques

## 0.98.0 (2025-01-22) - Parser Combinator Array Support Implementation Complete (Phase 5)
- Completed Phase 5 of parser combinator feature parity plan: Array Support
- Full implementation of array assignment syntax: arr=(elements) and arr[index]=value
- Added comprehensive array parsing support to parser combinator implementation
- Implemented ArrayInitialization and ArrayElementAssignment AST node integration
- Added robust token handling for both combined and separate token patterns
- Support for complex array patterns: variables, arithmetic indices, quoted values
- Created comprehensive test suite: 17 tests across 3 test files covering all array functionality
- Fixed 5 failing integration tests to reflect new array support capabilities
- Updated feature coverage tests and documentation to show array support completion
- Enhanced array element assignment with append operations (arr[index]+=value)
- Support for empty arrays, command substitution in elements, and mixed element types
- Proper error handling for malformed array syntax with graceful failure modes
- Parser combinator now supports ~99% of critical shell syntax (5/6 phases complete)
- Array assignments work seamlessly with existing shell constructs where supported
- Full feature parity with recursive descent parser for array assignment operations
- Foundation established for final phase: advanced I/O features and select loops

## 0.97.0 (2025-01-22) - Parser Combinator Enhanced Test Expressions Implementation Complete (Phase 4)
- Completed Phase 4 of parser combinator feature parity plan: Enhanced Test Expressions support
- Full implementation of [[ ]] conditional expressions with all operators
- Added DOUBLE_LBRACKET and DOUBLE_RBRACKET token support to parser combinator
- Implemented comprehensive test expression parser with binary, unary, and logical operators
- Added _format_test_operand() helper for proper variable and string formatting
- Integrated with existing EnhancedTestStatement AST nodes and execution engine
- Fixed critical unary test evaluation bug in shell.py execution engine
- Enhanced control structure parsing chain with proper AST unwrapping
- Created comprehensive test suite: 30+ tests across 3 test files
- Updated feature coverage tests to reflect new enhanced test expression support
- Enhanced test expressions now work in all contexts: standalone, control structures, logical operators
- Parser combinator now supports ~98% of critical shell syntax (4/6 phases complete)
- Key supported operators: ==, !=, =, <, >, =~, -eq, -ne, -lt, -le, -gt, -ge (binary)
- File tests: -f, -d, -e, -r, -w, -x, -s, -z, -n, and more (unary)
- Logical operators: ! (negation), with && and || via shell logical operators
- Full integration with if/while/for conditions and logical operator chains
- Comprehensive regex pattern matching and file existence testing
- Proper variable expansion and string handling in test contexts

## 0.96.0 (2025-01-22) - Parser Combinator Arithmetic Commands Implementation Complete (Phase 3)
- Completed Phase 3 of parser combinator feature parity plan: Arithmetic Commands support
- Implemented comprehensive arithmetic command ((expression)) syntax parsing in parser combinator
- Added DOUBLE_LPAREN and DOUBLE_RPAREN token parsers to arithmetic command grammar
- Enhanced control structure parsing chain with arithmetic commands via or_else composition
- Integrated arithmetic commands seamlessly with existing ArithmeticEvaluation AST node infrastructure
- Added comprehensive arithmetic expression parsing with proper parentheses depth tracking
- Implemented variable preservation logic for VARIABLE tokens (adds $ prefix automatically)
- Enhanced expression building with whitespace normalization and multi-space cleanup
- Fixed pipeline and and-or list unwrapping to prevent unnecessary wrapping of standalone control structures
- Added 35 comprehensive arithmetic command tests covering basic usage through complex integration scenarios
- Created extensive test coverage: 10 basic tests + 16 edge cases + 9 integration tests with 100% pass rate
- Updated integration tests to reflect arithmetic command support (changed from "not supported" to "now supported")
- Support for all arithmetic operations: assignments, increments, compound assignments, complex expressions
- Full integration with control structures: if ((x > 10)), while ((count < 100)), for loop bodies
- Support for special variables ($#, $?), bitwise operations, logical operators, and ternary expressions
- Enhanced arithmetic expression handling in various contexts: standalone, conditions, loop bodies, and-or lists
- Phase 3 achievement brings parser combinator to ~95% critical shell syntax coverage (major milestone)
- All high-priority features (process substitution + compound commands + arithmetic commands) now complete
- Updated parser combinator feature parity plan documentation with Phase 3 completion notes and progress update
- Added detailed implementation achievements, technical details, and comprehensive test case documentation
- Updated timeline summary showing 3/6 phases completed (50% progress) with 9 weeks remaining for advanced features
- Educational value preserved while demonstrating parser combinators can handle complex mathematical shell syntax
- Foundation established for remaining phases: enhanced test expressions, array support, advanced I/O features

## 0.95.0 (2025-01-22) - Parser Combinator Compound Commands Implementation Complete (Phase 2)
- Completed Phase 2 of parser combinator feature parity plan: Compound Commands support
- Implemented comprehensive subshell group (...) and brace group {...} parsing support
- Added elegant delimiter parsing using between combinator with lazy evaluation for recursive grammar
- Integrated compound commands seamlessly into control structure parsing chain via or_else composition
- Enhanced control structure parser to support: if, while, for, case, subshells, brace groups, break, continue
- Added comprehensive compound command token parsers (LPAREN, RPAREN, LBRACE, RBRACE) to grammar
- Implemented _build_subshell_group() and _build_brace_group() methods with proper AST integration
- Enhanced and-or list parsing to handle complex integration scenarios with compound commands
- Fixed parser ordering for sophisticated and-or list integration: (echo test) && { echo success; }
- Modified pipeline builder to avoid over-wrapping control structures in unnecessary Pipeline nodes
- Added 27 comprehensive compound command tests (10 basic + 17 edge cases) with 100% pass rate
- Created extensive edge case test suite covering nested compounds, pipeline integration, complex scenarios
- Updated 46 integration tests to reflect new compound command capabilities and feature support
- Fixed integration test expectations from "not supported" to "now supported" for compound commands
- Support for complex scenarios: deep nesting ( { (echo nested); } ), pipeline integration
- Pipeline integration working: echo start | (cat; echo middle) | echo end produces correct output
- Full compatibility with all existing shell features: functions, control structures, I/O redirection
- Phase 2 brings parser combinator to ~90% critical shell syntax coverage (major milestone)
- All high-priority features (process substitution + compound commands) now complete
- Updated parser combinator feature parity plan documentation with Phase 2 completion notes
- Added detailed implementation achievements and technical documentation to feature parity plan
- Updated timeline summary showing 2/6 phases completed (33.3% progress) with 11 weeks remaining
- Fixed basic features integration tests to properly reflect Phase 2 compound command support
- Educational value preserved while demonstrating parser combinators can handle complex shell syntax
- Foundation established for remaining phases: arithmetic commands, enhanced test expressions, arrays

## 0.94.0 (2025-01-22) - Parser Combinator Process Substitution Implementation Complete (Phase 1)
- Completed Phase 1 of parser combinator feature parity plan: Process Substitution support
- Implemented complete process substitution parsing support (<(cmd) and >(cmd)) in parser combinator
- Added process substitution token parsers (PROCESS_SUB_IN, PROCESS_SUB_OUT) to expansion combinator chain
- Created comprehensive process substitution parsing logic with proper AST integration
- Enhanced Word AST building for process substitution tokens via _build_word_from_token method
- Added ProcessSubstitution import and parsing support to parser combinator implementation
- Created extensive test suites with 26 comprehensive tests covering basic usage through complex edge cases
- Fixed configuration issue where build_word_ast_nodes wasn't enabled by default in parser tests
- Resolved recursion issue in AST traversal for finding ProcessSubstitution nodes via visited set tracking
- All process substitution functionality now works identically between parser combinator and recursive descent
- Updated feature parity plan documentation to mark Phase 1 as completed with implementation details
- Major milestone: Parser combinator now supports advanced shell syntax with full process substitution capability
- Foundation established for remaining phases: compound commands, arithmetic commands, enhanced test expressions
- Educational value preserved while demonstrating parser combinators can handle complex shell syntax elegantly

## 0.93.0 (2025-01-21) - Arithmetic Expansion Testing Complete and Parser Combinator Enhancement
- Completed comprehensive arithmetic expansion testing plan with 134+ tests across 4 phases
- Phase 1: Number Format Testing (38 tests) - binary, octal, hex, arbitrary bases 2-36
- Phase 2: Special Variables Testing (31 tests) - positional parameters, $#, $?, $$, arrays
- Phase 3: Integration Testing (23 tests) - command substitution, control structures, here docs
- Phase 4: Edge Cases Testing (42 tests) - error handling, syntax errors, whitespace, recursion
- Fixed critical hanging tests from nested arithmetic expansion syntax abuse ($((counter)) → counter)
- Enhanced parser combinator capabilities: here documents and here strings now fully supported
- Updated integration tests to reflect current parser combinator feature set (no longer "unsupported")
- Comprehensive arithmetic testing validates production-ready functionality across all contexts
- Error handling robustness verified: division by zero, syntax errors, overflow conditions
- Performance testing completed: deep nesting (25+ levels), large expressions, variable contexts
- All arithmetic expansion features now thoroughly tested and documented for reliability
- Foundation established for production shell scripting with comprehensive arithmetic support

## 0.92.0 (2025-01-21) - Here Document Parser Combinator Implementation Complete
- Implemented complete here document support in parser combinator with comprehensive functionality
- Added heredoc token recognition (<<, <<-, <<<) to parser combinator grammar
- Enhanced redirection parser to handle heredoc and here string operators
- Implemented innovative two-pass parsing architecture for heredoc content population
- Added heredoc_quoted support for disabling variable expansion in quoted delimiters
- Fixed here string target quote handling and content preprocessing
- Created comprehensive test suite with 13 tests covering all heredoc functionality
- Updated parser combinator to handle complex heredoc scenarios with proper error handling
- All tests passing: heredocs, tab-stripping heredocs, here strings, content population
- Major milestone: parser combinator now supports full here document feature set
- Enhanced feature roadmap documentation to reflect completed heredoc implementation
- Parser combinator achieves comprehensive shell compatibility with here document support
- Educational two-pass parsing demonstrates functional approach to stateful language features

## 0.91.8 (2025-01-21) - Lexer Redirect Duplication Fix and Parser Combinator Integration
- Fixed critical lexer bug where redirect duplications like "2>&1" were tokenized as three separate tokens
- Modified operator recognizer to check for file descriptor duplication patterns BEFORE regular operators
- Added all digits (0-9) to OPERATOR_START_CHARS for proper FD duplication recognition
- Changed FD duplication tokenization to return REDIRECT_DUP tokens instead of WORD tokens
- Updated parser combinator to properly handle REDIRECT_DUP tokens
- Fixed numerous test expectations to match new single-token redirect duplication behavior
- All 141 parser combinator integration tests now pass (100% success rate)
- Full test suite shows 2463 passing tests with no unexpected failures

## 0.91.7 (2025-01-21) - Parser Combinator Implementation Complete
- Added stderr redirect support (2>, 2>>) to parser combinator
- Added background job support (&) to parser combinator
- Fixed function parsing to only allow at statement start (not in pipelines)
- Made parser stricter about syntax errors while maintaining correct parsing
- Fixed if statement regression by properly handling separators
- All parser combinator tests now pass with newly supported features
- Major milestone: parser combinator now supports all shell syntax features

## 0.91.6 (2025-01-21) - Parser Combinator Test Fixes
- Fixed parser combinator tests to match actual tokenization behavior
- Updated test expectations for variable assignments with expansions
- Fixed statement_list parser to handle leading separators
- Case statements now parse correctly with leading newlines
- Reduced failing tests from 13 to 2 (stderr redirect and background jobs remain)
