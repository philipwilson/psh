# Changelog

All notable changes to PSH (Python Shell) are documented in this file.

Format: `VERSION (DATE) - Title` followed by bullet points describing changes.

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
