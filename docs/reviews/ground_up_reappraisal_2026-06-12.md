# Ground-Up Reappraisal #3 — 2026-06-12 (v0.311.0)

**Scope:** the third full reappraisal, one day after the second closed and
after 24 releases of quality work (v0.288–v0.311, PRs #19–#44). **The ruler
has changed**: previous programs graded subsystems against their own goals
plus bash conformance; this one grades against the full TEXTBOOK bar — clean,
elegant architecture a student could read as a reference implementation —
because functional health is now strong and the project has chosen to chase
that grade.

**Method:** six parallel review agents (lexer/parser, executor/io_redirect/
core/shell, expansion/utils, builtins/interactive/visitor/scripting, tests/CI,
docs), each required to measure rather than assume, verify every claim
(sizes via wc/AST, callers via grep, behavior via bash 5.2 probes), and —
the new requirement — produce CONCRETE refactor designs for every gap to an
A: the semantic boundary created, target structure with real names, the
existing test safety net, size/risk, and failure modes. Full agent reports
are preserved in this memo's companion sections below (§3–§8); §2 is the
synthesized roadmap.

**Baseline:** main @ 8e9ee83, v0.311.0. Suite: 5,151 passed / 5,424
collected, 0 failures, ~69 s phases. CI green 3-for-3 on main (verified by
run results). 17/17 cross-agent bash spot probes match, including every
"known leftover" from reappraisal #2 (sparse array literals and `$(case ...)`
are confirmed fixed).

---

## 1. Scorecard (textbook ruler) and the headline

| Area | 06-10 | 06-11 (#2) | ext. 06-12 | **Now (#3)** | To an A, in one line |
|---|---|---|---|---|---|
| RD parser | A− | A | B+ | **A−** | honest `${...}` AST + derived `args` + delete array-init re-serialization |
| io_redirect | B+ | B | A− | **A−** | one procsub resolver; delete write-only `_saved_std*` |
| core | B+ | A− | — | **A−** | one env story, one special-var source, no MinimalShell |
| visitor | — | A− | A− | **A−** | behavior-level outcome tests; registry-derived SHELL_BUILTINS |
| ast_nodes | — | A− | — | **A−** | `args` derived from `words`; ParameterExpansion can't lie |
| arithmetic.py | — | — | — | **A−** | dedicated ArithSyntaxError (do NOT split the file) |
| test framework | B+ | A− | A− | **A−** | CPU-time perf tests; every skip reason verifiably true |
| executor | B+ | A− | B | **B+** | extract the assignment engine; shared forked-child runner |
| lexer | B− | B+ | B+ | **B+** | literal.py mini-scanners; total recognizer registry |
| expansion | B− | B+ | B+ | **B+** | ONE `${...}` parser; named-policy WordExpander |
| builtins | B− | B+ | — | **B+** | printf engine extraction (+ verified bug fix); statelessness test |
| scripting | — | — | — | **B+** | one CommandAccumulator completeness oracle |
| coverage / CI | — | — | — | **B+ / B+** | xfail absent-feature ledger; nightly full suite + coverage artifact |
| interactive | B+ | A− | B− | **B** | the 3-release LineEditor decomposition |
| shell.py | — | — | — | **B−** | lifecycle phases; delete `__getattr__` forwarding |
| combinator (as edu artifact) | B− | B | — | **B−** | control structures in actual combinator style, or shrink to the honest subset |
| docs: reference / user guide / teaching | C→B | B | — | **B+ / A− / C+** | the narrative internals tour + doc-pointer meta-test |

**The headline:** correctness is essentially done — but this review's
deeper measurement still surfaced a short list of REAL items the bug-hunting
programs missed, all verified:

1. **printf `%*`/`%.*` is broken** (`printf '%*d' 5 42` → bash `   42`, psh
   `5\n42`; `%.*f` errors) — the builtin's own help advertises the feature.
2. **Two of three fork sites never received the v0.300 sigmask race fix**
   (command_sub.py, process_sub.py fork bare) — a latent lost-signal race.
3. **The `exec` env leak**: `FOO=bar exec` writes `os.environ` and never
   restores it; invisible only because no child inherits `os.environ`
   (psh already materializes child envs explicitly — see §2 Tier A).
4. **Readonly-prefix divergence**: `RO=2 true` — bash reports the error and
   still runs the command; psh skips it.
5. **`visitor/constants.py SHELL_BUILTINS` disagrees with the live registry
   in both directions**; one xfail pins anti-bash behavior
   (`test_subshell_implementation.py:577` — bash also exits 0 there).
6. **ARCHITECTURE.md's "One Fork Path" invariant is false as stated** (the
   true invariant is one child *signal-policy* path), and §5.3 shows a
   method that doesn't exist (`expand_command_substitution`) — survived
   three doc sweeps because nothing tests doc pointers.
7. **~120 of 272 skips are stale** (legacy interactive suites superseded by
   the repaired PTY smoke tier).

---

## 2. The Textbook Program — synthesized roadmap

Three tiers. Tier A is bug-and-honesty work in the established style.
Tier B is THE architecture program — the refactors that move grades, ordered
by risk and dependency. Tier C is teaching and infrastructure.

### Tier A — truth and small fixes (2 releases)

**A1 — behavior batch:** fix printf `%*`/`%.*` while extracting the ~550-line
printf engine to `utils/printf_formatter.py` (pure, unit-testable; the
builtin thins to ~70 lines); port the fork-window sigmask fix to
command_sub/process_sub (minimal form of B3); fix the readonly-prefix
divergence (probe first, pin conformance); delete the `exec` os.environ
write along with the rest of **the os.environ policy** — declare `shell.env`
authoritative, os.environ read-once-at-startup (psh already passes env
explicitly to every child: `execvpe(args, shell.env)`, shebang `env=`,
`Shell(parent_shell=…)`; the mutations are vestigial dual writes, and the
exec leak proves they're incoherent). Dead code: `is_array_expansion`
(zero callers), `CommandExecutor._extract_assignments`/`_is_exported` +
`assignment_utils.is_exported`, manager.py's dead `expand_variable`/
`execute_command_substitution` public API.

**A2 — test/CI honesty:** timing flakes fixed for good
(`time.process_time()` + min-of-3); skip-debt purge (delete the 5 superseded
legacy interactive files, rewrite the wrong subshell xfail); the
**absent-feature ledger** — one xfail conformance test per verified-absent
bash feature (coproc, wait -n, read -u, hash, caller, compgen/complete/bind,
lastpipe, failglob, `@K`, extglob-in-param-exp, jobs -x, test -v…) so the
"99%" number gets an honest denominator and features XPASS loudly when
implemented; SHELL_BUILTINS derived from the registry; builtin statelessness
meta-test + the last channel-convention stragglers (directory_stack, help);
CI: coverage artifact on the quick job (~7% overhead, measured) + a nightly
cron running the full parallel suite, full conformance, and the
`--compare-bash` golden phase; run_tests.py `--census` flag.

### Tier B — the architecture program (ordered; each release green; sizes S/M/L)

| # | Refactor | Semantic boundary created | Size/Risk |
|---|---|---|---|
| B1 | **Shell lifecycle + retire `__getattr__`** — named init phases, `Shell.for_subshell()` classmethod, CLI visitor-modes move to scripting/, four explicit stdout/stderr/stdin/env properties (143/180 uses), mechanically rewrite the remaining ~37+38 sites, delete `__getattr__`/`__setattr__`; shell.py joins mypy | "what is a Shell?" answerable from its file | M / low (mechanical, measured) |
| B2 | **CommandAssignments extraction** — the ~290-line assignment sub-domain (extract/expand/apply/restore + POSIX ordering contract) out of CommandExecutor; delete the `_visitor` backchannel | "what NAME=value means" vs "how commands dispatch" | M / med |
| B3 | **Shared forked-child runner** — `fork_with_signal_window()` + `run_child_shell()` in child_policy.py used by all three fork sites (fixes the sigmask gap, the in_forked_child inconsistency, the silent bare-except, the missing flush); substitutions deliberately stay out of ProcessLauncher (they're not jobs); then make ARCHITECTURE's invariant true as reworded | "becoming a healthy child" vs "what this child does" | M / med |
| B4 | **WordExpander + named policies** — `WordExpansionPolicy` frozen dataclass (split/glob/assignment_tilde) with named instances (COMMAND_ARGUMENT, DECLARATION_ASSIGNMENT, ARRAY_INIT_ELEMENT, ASSOC_INIT_ELEMENT…), the 238-line `_expand_word` decomposed into named phases in `expansion/word_expander.py`; kills the `suppress_split_glob→declaration_assignment` flag aliasing; manager.py slims to a ~250-line orchestrator (escape processors move with the walker; `_word_to_string` becomes AST methods; arithmetic adapter moves to arithmetic.py) | every expansion context has a NAME | M / low-med (1,001 unit tests pin it) |
| B5 | **ONE parameter-expansion parser** — `expansion/param_parser.py: parse_parameter_expansion(content) -> ParameterExpansion`, consumed by WordBuilder (stops deferring subscripted forms — the AST stops lying) and by the string entry (`expand_variable` becomes parse-then-evaluate; the pre-dispatch ladder, `ParameterExpansion.parse_expansion`, and `fields._parse_trailing_op` all die). Migration behind a differential harness (old vs new over every `${...}` in the corpus). The oldest structural finding in the project — four mutually-dependent parser copies, the source of the M1 bug | one grammar, one parser | L / med-high — the headline |
| B6 | **literal.py mini-scanners + total registry** — `recognizers/word_scanners.py` (scan_glob_bracket / scan_extglob_group / scan_assignment_prefix consulting the lexer's existing assignment map / scan_inline_ansi_c) + a forward `WordShape` state replacing the four retro-heuristics ("likely/probably" hedges); then make the tokenize loop total (fallback word-collector and silent char-drop become fail-loudly after an instrumented census); split `pure_helpers.py` (cmdsub scanner → `lexer/cmdsub_scanner.py`); one command-position vocabulary (lexer's private keyword set derived from command_position.py; case-state transitions shared) | the lexer always KNOWS what segment it's in, instead of guessing | M / med (characterization harness first) |
| B7 | **args/words dedup** — `SimpleCommand.args` becomes a derived property after migrating the few parallel mutators; delete `_parse_array_initialization`'s token re-serialization | one source of truth for arguments | M / med (67 consumer sites, whole suite as net) |
| B8 | **LineEditor decomposition, 3 releases** — R1: `EditBuffer` (pure model) + `LineRenderer` (sole ANSI writer; snapshot tests pinned against current `_paint` output FIRST); R2: `KeyDecoder` (sole stdin reader; `read_key() -> KeyEvent`; SIGWINCH folds into its fd set; the 50 ms ESC disambiguation is the risk); R3: HistoryNavigator/HistorySearch + dict-based action dispatch. Rule: every split narrows a contract, or it doesn't ship | only-reader-of-stdin / only-writer-of-ANSI / single-source-of-truth buffer | L / med (139 in-process tests + 40 PTY) |
| B9 | **CommandAccumulator** — one parser-driven completeness oracle (`feed(line) -> Complete|NeedMore`) shared by source_processor and multiline_handler, replacing the latter's three heuristic layers; dedupe source_processor's four errexit copies | one answer to "is this command complete?" | M / med |
| B10 | smaller seams as they're touched: declare table-driven attrs + `declare -p` formatter extraction; read's three loops → one `_read_chars`; `hash` builtin (one S release, unskips 3 tests); io_redirect residue (one procsub resolver, delete `_saved_std*`); core smalls (`$*` one source, MinimalShell, inert function.py special-var writes) | — | S each |

NOT recommended: splitting arithmetic.py (it IS the textbook chapter);
rewriting the combinator parser (educational-only decision stands — if
appetite ever exists, rewrite its control structures in actual combinator
style or shrink it; until then it stays as framed).

### Tier C — teaching and infrastructure (2 releases)

**C1 — the narrative tour** (the single biggest gap for the educational
mission, graded C+): `docs/architecture/tour_of_psh_internals.md` tracing
`echo "Hello, $USER" | wc -c > out.txt` through preprocessing → tokens
(real `--debug-tokens` output) → AST (`--debug-ast`) → expansion
(`--debug-expansion`) → fork/pipe/redirect → exit status, linking each stage
to its subsystem CLAUDE.md. Reproducible via the debug flags — that's the
textbook property.

**C2 — doc integrity:** the doc-pointer meta-test (backticked `psh/...`
paths and symbols in ARCHITECTURE.md + CLAUDE.mds must resolve — would have
caught both ghosts this review found); fix the One Fork Path wording (until
B3 makes it true) and the §5.3 ghost snippet; refresh the three CLAUDE.mds
frozen at v0.286 (core, builtins, interactive); archive the 8 bannered
guides + 20 public_api point-in-time files + the 2 unbannered stale guides
(keep combinator_parser_guide.md); README counts generated, not
hand-maintained; CHANGELOG: split pre-v0.200 entries to
docs/archive/CHANGELOG_history.md; probe batteries promoted from tmp/ into
golden_cases.yaml as part of the bash-verification workflow.

**Suggested overall sequence:** A1 → A2 → B1 → C2 → B2 → B4 → B3 → C1 →
B5 → B6 → B7 → B8(R1) → B9 → B8(R2,R3) → B10 items riding along throughout.
Roughly 15–18 releases at the established cadence.

---

---

## 3. Appendix — teaching-quality honor roll (per the six reviews)

The reviews graded files directly as teaching material. The pattern is
instructive: the BEST files are small, single-subject, and narrate the bug
or race their design prevents; the WORST are multi-concern files whose
comments are load-bearing because the structure isn't.

**Best in tree:**
`lexer/command_position.py` (the template micro-module — concept, why two
passes exist, per-set rationale); `lexer/heredoc_lexer.py`;
`find_command_substitution_end`'s Design/Maintenance-Contract docstring;
`executor/child_policy.py` (the whole fork/signal problem in 61 lines);
`io_redirect/manager.py`'s two-universes essay + BuiltinRedirectFrame;
`executor/process_launcher.py`; `expansion/arithmetic.py` (the textbook
interpreter chapter); `expansion/word_splitter.py`; `utils/escapes.py`
(teaches why NOT to deduplicate); `interactive/line_layout.py`;
`visitor/traversal.py` + `base.py` + the coverage matrix;
`builtins/base.py`; `core/exceptions.py`; `tests/conftest.py` (fixtures
that explain their own history).

**Most in need (each addressed by a Tier B item):**
`shell.py` (B1), `lexer/recognizers/literal.py` (B6),
`expansion/parameter_expansion.py:parse_expansion` (B5),
`executor/command.py` (B2), `interactive/line_editor.py` (B8),
`interactive/multiline_handler.py` (B9), `builtins/io.py` (A1),
`expansion/arrays.py` (A1 dead code + B10), `core/state.py` (A1/B10),
`lexer/pure_helpers.py` as packaging (B6),
`parser/combinators/control_structures/` (settled educational-only; the
files remain the one place the artifact undercuts its own thesis),
`utils/shell_formatter.py` (duplicates the visitor formatter — fold in
during C2/B10).

**Cross-cutting observations:**
- Every Tier B refactor has a dense existing test net (1,001 expansion unit
  tests, 139 in-process line-editor tests + 40 PTY, the full conformance
  batteries) — the campaign's test investment is what makes the
  architecture program tractable now.
- The expansion review's verdict on why the four-parser `${...}` problem
  survived four programs: the deferral chain is load-bearing (each parser
  relies on another's gaps), each accreted bug-pinned heuristics, and
  string contexts legitimately need a string ENTRY — which prior programs
  conflated with needing a second PARSER. B5's differential-harness
  migration is the answer.
- In-process coverage measured at 72% overall (lexer 86%, expansion 82% …
  io_redirect 50% with the fork-invisibility caveat); `psh/__main__.py` is
  0% covered in-process and `parser/visualization/sexp_renderer.py` is 0%
  (177 statements — audit in A2).
- The user guide grades A− as usage teaching; the missing piece for the
  educational mission is narrative internals (C1), not more reference.
