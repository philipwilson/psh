# Ground-Up Reappraisal #21 — Textbook-Quality Edition: psh at v0.724.0

**Date:** 2026-07-12
**Baseline:** v0.724.0 (main @ `d1b8ef35`, read from a pinned detached-worktree snapshot; gate 18,254 passed /
0 failed / 10 xfail / 1,574 skip at release; goldens 1,505; mypy clean across all 258 production files;
`ruff check psh tests` 0). This is the first ground-up round after the reappraisal-#19 campaign closed —
32 releases (v0.693–v0.724) that dismantled most of the twin-defect factory r19 named.
**Method:** 16 independent per-subsystem auditors, each reading **every file in its scope in full** (the 16
scopes tile all 258 files under `psh/` plus test infrastructure and cross-cutting concerns), followed by
**16 adversarial verifiers** — one per report — who re-read every HIGH/MED at the cited `file:line`,
**re-ran every behavioral probe from scratch** against live bash 5.2.26 (never trusting archived output),
grepped for dynamic dispatch before accepting any dead-code claim, ran meta-guards against synthetic
offenders, and then read the files the auditor under-visited. Capped by a completeness critic that verified
scope tiling and computed whole-tree metrics. **Verdicts: 232 CONFIRMED, 13 ADJUSTED, 0 REFUTED**, plus 12
verifier-added findings. Per-subsystem prose reports with verification addenda preserved under
`tmp/appraisal-r21-reports/`; every behavioral probe transcript under `tmp/appraisal-r21-reports/probes/`.
**Focus:** Like r19, this round does **not** grade bash feature parity. It grades **textbook quality**
along three axes — **elegance** (one chokepoint per concern, composition, no dead code, no divergent twins),
**clarity** (naming, docstring honesty, teaching narrative, doc accuracy), **efficiency** (accidental
algorithmic waste only) — plus **correctness of implemented features**: internal defects where a feature
contradicts its own documentation, tests, or itself. Bash is used only as a probe oracle to expose those
self-contradictions, never as a missing-feature checklist.

---

## Verdict

**The r19 campaign worked, and it is visible in the grades. Elegance rose across nearly every subsystem as
the divergent-twin factory was dismantled: the arithmetic engine, the executor's fork/pipeline core, the
redirect engine, scripting, and the test-infrastructure tier all now grade A-range on elegance, and the
registry-plus-meta-test discipline r19 prescribed is demonstrably load-bearing. But the binding constraint
has moved, not vanished. It is now correctness of implemented features — and this round, probing harder
than any before it, found roughly 30 live, probe-confirmed defects in which a shipped feature disagrees with
its own contract or with a sibling code path. These are not the three graded axes; they are orthogonal to
them, which is why a tree that reads better than v0.687 also has a longer live-defect list.**

Two results define the round. **First, the associative-array subscript is the single most cross-cutting
defect in the tree**: four independent scopes (arithmetic, expansion, core, lexer) each found one facet of a
keying rule that is implemented six different ways across write, read, unset, is-set, arithmetic-subscript,
and `$'...'`-key paths — the write path stores the literal key `k`, the read and unset paths resolve `k`
through a same-named variable, the `+`/`-`/`?` operators use a third expansion, and an unsubscripted
`$assoc` returns empty instead of `${assoc[0]}`. It is the "same rule implemented N times, drifted" pattern
of r19 applied to a *single feature* spread across *six modules*, and no auditor saw the whole of it. It
needs a named cross-package owner.

**Second, the controlled experiment r19 ran on the codebase reproduced exactly.** Every chokepoint enforced
by a registry plus a drift-lock meta-test held under adversarial re-derivation — the option registry, the
computed-specials table, the env materializer, the import-layering ratchet (regenerated to `205 = 205`, zero
slack), the doc-snippet drift-lock, the AST totality matrix, the `$'...'` encoder, the heredoc
delimiter/terminator rule, the single `os.fork()` site. Every chokepoint enforced by *prose alone* was found
violated somewhere: `VariableStore`'s "every write goes through one operation" (dead facade methods plus
eleven direct callers), `with_redirections` "the live path" (zero callers, a dead twin still taught in three
documents), `HISTORY_REFERENCE_RE` "the single source of truth" (a quote-blind twin that silently loses user
history), `target_fd` "the single source of truth" (re-derived at seven sites), `command_resolver`'s "every
`$PATH` scan" (a `shutil.which` fallback), and `pattern.py`'s "every construct" (three `fnmatch` sites). The
cure remains the same: extend the project's own proven pattern to the chokepoints still held together by
comments.

The live behavioral defects, unlike r19's, do not share one root shape — they are feature-clustered rather
than mechanism-clustered. But two familiar structural classes recur: **analysis/diagnostic sidecars run a
full grade below the execution path** (a clean `set -eu` `for`/`read` script fails `--lint` with exit 1; the
combinator's default `--debug-ast` renders `if/elif` as raw dataclass repr), and **`ARCHITECTURE.md` is
again the worst single teaching liability** — though now narrowly, because the CLAUDE.md drift-lock r19
installed kept every subsystem doc accurate while the flagship guide, which escapes that guard, drifted on
three load-bearing sketches (an inverted command-strategy precedence, phantom AST field names, and a
"limitation" the code already fixed).

## Grade table

Prior column: reappraisal #19's textbook grades (v0.687). Movement is the campaign's effect on the three
*graded* axes; the correctness defects this round surfaced sit outside these axes and are captured in the
findings, not the letters.

| Subsystem | Eleg | Clar | Eff | Prior (r19) | Headline |
|-----------|------|------|-----|-------------|----------|
| Lexer | B+ | A− | A | B+/A−/A− | Verified chokepoints (heredoc rule, dispatch order, command-position vocabulary); one proven-drifted `${...}` extent twin + a heredoc-driver completeness hole, both probed |
| Parser (RD) | B+ | A− | A | B+/A−/A− | Publishable depth-guard totality + structured errors; two live defects in string-scanning corners (array-head scan, backtick counting) |
| Parser (combinator) | B | B+ | A− | B−/B/A− | **Riser.** Strong RD parity (87/89 AST-identical); two grammar divergences, repr-garbage `elif` rendering in 3 of 4 renderers, ghost parser layer |
| Expansion | B+ | A− | A− | A−/A−/B+ | Excellent policy/segment/engine architecture; systemic assoc-array keying hole + an affix path bypassing split/glob |
| Arithmetic | A− | A− | A | B+/A−/A− | **Riser.** Table-driven tokenizer, reified LValue, grep-verified chokepoints; the assoc literal-key mechanism is the one defect cluster |
| Executor | A− | A− | A | B+/B+/A− | **Riser.** Single fork chokepoint, one child-exit taxonomy, O(1) pipelines; two `command.py` pre-resolution shortcuts answer "what resolves?" wrongly |
| Core/State | B+ | A− | A− | B+/A−/A | Registry chokepoints all verify; two probed defects break its own contracts (nameref-blind attribute ops, `export -n +=` append bypass) |
| Builtins (decl) | B+ | A− | A | B+/B+/A | **Clarity riser.** Genuinely converged family; `-p`-with-operands and `export -n +=` are live chokepoint bypasses |
| Builtins (io/jobs) | B+ | A− | A− | B/B+/A | **Riser.** Well-chokepointed; three probed defects (`printf -vx`, `read -N` voiding `-t`/`-s`, `wait` WNOHANG pid/status conflation) |
| I/O Redirect | A− | B+ | A | B+/A−/A | **Elegance riser.** Textbook `fd_remap`; a dead `with_redirections` twin taught as live + a prefix-divergent error path drop clarity |
| Interactive | B+ | A | A | B+/A−/A− | **Clarity riser.** Showcase component split; dead vi repeat-count, quote-blind history regex losing entries, `!0` off-by-one |
| Scripting + entry | A− | A | A | B+/A−/B+ | **Riser.** One genuine lex→parse pipeline + honest oracle; one HIGH (`!!` short-circuit ungated by mode) exposing a syntax-abort twin |
| Visitor | B+ | A− | A | B/B+/A− | **Riser.** Publishable formatter + totality matrix; advisory sidecars still carry divergent rule copies (7+ false-fire/no-op) |
| AST + utils | A− | A− | A | B+/A−/A | **Riser.** Derived-property doctrine + dialect-map essay hold; heredoc oracle closes out of order, `printf '%-%'` prints `%` |
| Test infrastructure | A− | A− | A | B/B+/A− | **Big riser.** Guard-the-guard everywhere + pure pinned runner classifier; stale mypy override glob + unenforced bash-oracle chokepoint |
| Cross-cutting | A− | B+ | A− | B+/B+/A− | Acyclic top-level graph, exactly-tight import ratchet, `PshError`-rooted taxonomy; `ARCHITECTURE.md` drifted on 3 load-bearing sketches |

## What is already textbook-grade

A book reviewer would accept these chapters today (auditors named strengths; verifiers seconded them and, in
several cases, subjected them to independent adversarial fuzzing that they passed):

- **`psh/expansion/arithmetic/`** — a complete interpreter in 1,588 lines: a table-driven maximal-munch
  tokenizer with only the one context-sensitive `++`/`--` rule isolated; a reified `LValue` giving one
  evaluator per mutation (`_write_lvalue` grep-verified the sole write path); a coherent four-net recursion
  guard; and strict-errors borders (cant-happen branches raise `RuntimeError`, the user-reachable `ValueError`
  kept and mutation-pinned). Ten of eleven findings probed, zero refuted.
- **`psh/executor/child_policy.py` + `pipeline.py`** — one `os.fork()` in the whole tree (grep-verified),
  one `map_child_exception()` taxonomy behind every fork, and rolling O(1) pipe construction with transactional
  rollback whose kill-before-release-sync ordering is argued in place.
- **`psh/io_redirect/fd_remap.py`** — a 137-line implementation matching its own first-principles narrative of
  the two collision failure modes; three production callers, a chokepoint that holds.
- **`psh/expansion/pattern_engine.py`, `param_parser.py`, `word_expansion_types.py`** — parse-once pattern AST
  with `count_states()` as an assertable complexity guard; the one `${...}` classifier whose docstring *is* the
  grammar; the three-axis expansion-policy table as data.
- **`psh/lexer/cmdsub_scanner.py` + `command_position.py`** — the `$(...)` extent-problem chapter (bash
  `xparse_dolparen` comparison, named owner tests) and the three-machines non-unification essay, both still
  accurate against the code.
- **`psh/utils/escapes.py`** — the "do NOT deduplicate" dialect-map essay; the verifier re-checked all 26
  behavioral deltas it claims against live bash and every one held.
- **`psh/core/special_registry.py` / `option_registry.py` / `_materialize_env_name`** — the three registry
  chokepoints, each drift-lock-guarded; `$RANDOM` reproduced value-for-value against bash.
- **`psh/builtins/input_reader.py`** — one streaming input service behind `read` and `mapfile`, with the
  two-decode-policy rationale as model teaching prose.
- **`psh/interactive/key_decoder.py` / `edit_buffer.py` / `line_renderer.py`** — a closed KeyEvent algebra,
  pure models with zero terminal knowledge, and the single ANSI-writer chokepoint (grep-verified).
- **`psh/scripting/lex_parse.py` + `command_accumulator.py`** — the genuinely single lex→parse pipeline (the
  three-caller claim grep-verifies) and the real-parser completeness oracle with an honest O(N²) bound.
- **`run_tests.py#classify_phase_result`** — a pure pass/fail function that never translates an abnormal exit
  into a pass, pinned by 30+ synthetic cases; and the **guard-the-guard tier** in `tests/unit/tooling/`, where
  nearly every meta-guard drives a synthetic offender and asserts it fires.
- **`psh/core/internal_errors.py` + `exceptions.py`** — one `report_internal_defect` chokepoint deciding
  internal-defect vs expected-shell-error for all seven guards; every shell error roots at `PshError`.
- **`tests/unit/tooling/test_import_layering.py`** — AST import graph + Tarjan SCC + a per-module deferred-import
  ratchet, regenerated to exactly tight this round.

---

## Findings

Thirty HIGH findings, clustered by theme. Every HIGH is probe-confirmed live unless marked structural.
MED (101) and LOW (119) are summarized by class after. All counts are post-verification; 0 findings were
refuted.

### HIGH (30)

#### A. Associative-array subscript keying — one feature, six inconsistent implementations (the cross-cutting defect)

**A1 (EXPAN-1) — read/unset paths resolve a bare-name assoc key through a same-named variable; the write path
does not.** `psh/expansion/arrays.py:311-318`. `expand_array_index`'s bare-name fallback substitutes a
variable's *value* for the literal subscript. Probed: `declare -A h; h[k]=1; k=other; h[other]=X; echo ${h[k]}`
→ bash `1`, psh `X`; and `declare -A h; k=other; h[k]=5; echo ${h[k]}` → bash `5`, psh **empty** — psh's own
write (stores literal `k`) and read (keys `other`) disagree. `unset "h[k]"` removes nothing via the same helper.
**Fix:** delete the bare-name fallback; assoc keys are literal strings.

**A2 (EXPAN-2) — `_param_is_set` uses a different assoc-key expansion than the read path.**
`psh/expansion/operators.py:185` calls `expand_array_index` (no quote removal) where the read path calls
`expand_assoc_key` (strips one quote pair). Probed: `declare -A h; h["k 1"]=v; echo ${h["k 1"]+SET} ${h["k 1"]}`
→ bash `SET v`, psh ` v` — the `+` operator sees unset while the bare read sees the value, inside one command.

**A3 (ARITH-1) — the assoc literal-key contract is broken: unlexable keys hard-error, whitespace keys silently
mis-key.** `psh/expansion/arithmetic/parser.py:340-353`. The subscript must tokenize and parse *as arithmetic*
before the stored "verbatim" `index_text` is ever consulted, and `_parse_subscript` `.strip()`s it. Probed:
`h["a b"]=4; echo $((h[a b]))` → bash `4`, psh `arithmetic error: Expected RBRACKET, got IDENTIFIER`;
`h[foo]=1; echo $((h[ foo ]))` → bash `0` (literal key `" foo "`), psh `1` (stripped) — the "verbatim" docstring
falsified by the strip.

**A4 (LEX-5 / cross to expansion) — assoc subscript `$'...'` / `$"..."` keys are not decoded.** Probed:
`declare -A a; a[$'k']=1` → bash key `k`, psh key `$'k'`. The lexer collects the subscript literally (correct);
the downstream key evaluation never runs the ANSI-C/locale quote removal ordinary word expansion applies.

**A5 (CORE-V1, verifier-added) — unsubscripted `$assoc` returns empty; bash expands it as `${assoc[0]}`.**
`psh/core/variables.py:318`, `AssociativeArray.as_string()` returns `""` behind a false comment ("Bash doesn't
allow `${assoc}` without subscript"). Probed: `declare -A a=([0]=zero [x]=y); echo "[$a]"` → bash `[zero]`, psh
`[]`. `IndexedArray.as_string` already implements exactly this rule for index 0.

#### B. Builtin option-parse and chokepoint bypasses — live state loss in POSIX special builtins

**B1 (BD-H1) — `export -p` with operands silently drops the assignment, and its print branch is an
attribute-dropping twin — and the suite pins BOTH contracts.** `psh/builtins/environment.py:189-193`. With `-p`
and names, psh prints from the live env dict and `continue`s past any assignment: `export -p A=5` leaves `A`
unset and unexported (bash: `A=5` exported). Two conformance tests contradict each other on this
(`test_export_env_sync_conformance.py:197` vs `test_export_builtin.py:44`), the first accidentally green because
its variable is unset.

**B2 (BD-H2) — `readonly -p Z=1` silently skips the operand; the variable is never made readonly.**
`psh/builtins/function_support.py:837-845`. Probed: bash assigns `Z=1` and marks it readonly (later `Z=2` fails);
psh leaves `Z` unset and writable and dumps the whole readonly listing. A user who ran `readonly -p SECRET=x`
believes the protection applied; it did not.

**B3 (BD-H3 / CORE-2) — `export -n NAME+=value` bypasses the one append engine — the FIX1 defect resurrected on
the `-n` path.** `psh/builtins/environment.py:199-201` hand-rolls `(get_variable(key) or '') + value`. Probed:
`declare -i n=2; export -n n+=3` → psh `n=23`, bash `n=5`. The plain-export path routes through
`DeclarationEngine.commit_scalar` precisely to avoid this.

**B4 (CORE-1) — attribute add/remove skips nameref resolution: `export`/`readonly` through a nameref hit the
wrong variable and leak the target name into the environment.** `psh/core/scope.py:1087` (`apply_attribute`),
`:1142` (`remove_attribute`). Probed: `x=1; declare -n r=x; export r; printenv r` prints **`x`** (the nameref
cell is exported, its value being the target *name*); `declare -n r=x; readonly r; x=2` succeeds where bash
errors. Directly contradicts `variable_store.py`'s "cannot be bypassed" contract for attribute ops. The
verifier found a third affected surface (`declare -i r` stamps `-i` on the nameref, not the target).

**B5 (BIO-1) — `printf -vx` (attached option-arg) is treated as the format string; the variable is never set.**
`psh/builtins/io.py:148` accepts only the exact word `-v`. Probed: `printf -vx %s hi; echo "<$x>"` → bash `<hi>`,
psh prints `-vx` and `<>`. Every `parse_flags` user gets `-vx`/`-v x` equivalence for free; this hand-rolled walk
does not.

**B6 (BIO-2) — `read -N` silently discards `-t` (and `-s`).** `psh/builtins/read_builtin.py:122-123, 685-728`.
`_read_exact` never consults `timeout`/`silent`. Probed: `(sleep 2; echo abcde) | { read -t 0.5 -N 3 x; }` →
bash rc 142 after the timeout with `x` empty; psh blocks the full 2s, rc 0, `x=abc`. The deadline plumbing and
echo flag already exist — a pure dispatch gap.

**B7 (BIO-3) — `wait`'s WNOHANG check tests the returned *status* instead of the returned *pid*; an exited-0
child is double-reaped into "not a child of this shell".** `psh/builtins/job_control.py:673-677`. `waitpid`
signals "still running" via a returned pid of 0, not a zero status. Probed: `sh -c "exit 0" & p=$!; disown;
wait $p` → psh `wait: pid NNN is not a child of this shell` rc 127; the exit-3 twin returns rc 3. bash: rc 0 in
both. Self-contradiction independent of bash — two children differing only in exit status take wildly different
paths.

#### C. Command-resolution pre-shortcuts answer "what will this resolve to?" differently than the resolver

**C1 (EXEC-1) — POSIX-mode prefix persistence is silently lost when a function shadows a special builtin.**
`psh/executor/command.py:489-498, 566-570`. `is_function_call` is decided by a bare pre-resolution lookup, then
the `finally` pops the temp-env scope with the comment "Special builtins never take the function path" — false
under `set -o posix`, where `_resolve_command` gives the special builtin precedence and returns
`prefix_assignments_persist=True`. Probed: `times(){ :; }; set -o posix; V=v times; echo ${V-unset}` → bash `V=v`,
psh `V=unset`.

**C2 (EXEC-2) — the backslash-strip on the command word is quote-blind: `"\echo" hi` runs echo instead of failing
127.** `psh/executor/command.py:602, 613`. `_strip_backslash_bypass` never checks `not first_part.quoted`; the
backslash-is-a-quote rule applies only to an *unquoted* backslash. Probed: `"\echo" hi` and `'\echo' hi` → bash
rc 127 `\echo: command not found`, psh prints `hi` rc 0.

#### D. History references — a quote-blind twin that loses user data, and a mode-ungated oracle short-circuit

**D1 (INTER-2) — the shared history-reference regex is a drifted twin of the expander; it silently drops
legitimate lines from history.** `psh/interactive/history_expansion.py:16-23`, consumed at
`psh/scripting/source_processor.py:438-441`. The regex both misses what the expander expands (`!$`, `!^`, `!*`,
`^old^new^`) and matches what the expander suppresses. Probed via the real preprocessor: `echo 'oops !cmd here'`
— single quotes suppress expansion correctly, but the quote-blind regex matches, so the recording gate skips
`add_history` and **the command vanishes from history**; bash records it. Same with histexpand off. All under a
"single source of truth" banner.

**D2 (SCRIPT-1) — the completeness oracle's history-reference short-circuit is not gated on interactive mode.**
`psh/scripting/command_accumulator.py:231-233`. Unlike the silent-expansion step directly above it (gated on
`not is_script_mode`), step 3 returns `Complete` unparsed whenever `contains_history_reference` matches — in
script/`-c`/stdin mode, where `!` is literal. Probed: `for x in !! b; do echo "got:$x"; done` → bash prints
`got:!!`/`got:b` rc 0; psh emits two parse errors, runs the body as a stray command, rc 2 (or rc 0 in the
two-line variant — see D3).

**D3 (SCRIPT-2) — twin syntax-error paths with divergent non-interactive abort policy.**
`psh/scripting/source_processor.py:367-373` vs `:180-187`. A trial-detected syntax error aborts the source
immediately; the same error class from the execution parse merely returns 2 and the loop continues. Probed: a
syntax error → the *following* command executes → final rc **0** (bash: abort, rc 2). Reachable via D2 and
independently whenever the RD trial accepts what the active combinator parser rejects.

**D4 (INTER-1) — the vi repeat count is entirely dead: the dispatch branch is unreachable.**
`psh/interactive/line_editor.py:442-455`. `_dispatch_char` dispatches any bound key immediately, so
`_handle_vi_normal_char` is reached only for *unbound* keys and then re-queries the same dict — its `if action:`
loop can never fire. Probed: in vi normal mode, `3x` deletes one char and leaves `vi_repeat_count='3'` forever.
A ghost feature the class docstring advertises as owned state.

**D5 (INTER-3) — `!0` / `!-0` resolve to the oldest history entry; bash: "event not found".**
`psh/interactive/history_expansion.py:364-373`. `num = 0` falls into the `else` arm where `abs(0) <= len` is
always true and `history[0]` returns. Probed against bash 5.2's `!0: event not found`.

#### E. Parser string-scanning corners and lexer completeness

**E1 (PRD-1) — `_candidate_single_token_element` parses `arr[…]=v` heads with first-occurrence scans — three
live wrong results.** `psh/parser/recursive_descent/parsers/arrays.py:152-173`. Name/operator/subscript are
derived from the *first* `=`/`+=`/`]`, with no bracket-depth anchoring. Probed: `a[i=1]=v` → psh `a[1]` = `1]=v`;
`a[b[0]]=x` → psh rc 1 `Expected RBRACKET, got EOF`; `a[0]=x+=y` → psh value `+=y`. psh contradicts itself:
`a[b[c]]` is a valid subscript shape elsewhere in the declaration family.

**E2 (PRD-2) — unclosed-backtick detection is a backtick-count heuristic; an escaped backtick defeats it and psh
executes incomplete input.** `psh/parser/recursive_descent/parsers/commands.py:120-123` plus
`support/word_builder.py:51-56` (silent raw-value fallback). Probed: `` echo `foo\`bar` `` → bash rc 2 "unexpected
EOF"; psh rc 0, runs `foo` and `bar` as commands. Backtick is the one expansion kind with no structured
`*_unclosed` marker; the `strip_backtick` "shouldn't happen" fallback passes the garbage on silently.

**E3 (LEX-1) — the heredoc driver treats a command ending in an unclosed expansion as complete; following lines
are eaten as body.** `psh/lexer/heredoc_lexer.py:124-138`. The completeness test keys only on `SyntaxError`
(unclosed quote), but unclosed `$(`, backtick, and `${` emit `*_unclosed` parts and tokenize "successfully".
Probed: a `cat <<EOF $(echo` / `hi)` / `body` / `EOF` script → bash prints `body` rc 0; psh errors rc 2. The
docstring's "following lines are command continuation, like bash" is true only for the SyntaxError subset.

**E4 (LEX-2) — two `${...}` extent rules; the assignment-map side disagrees with the real lexer rule, breaking
assoc-array assignments with brace-containing keys.** `psh/lexer/recognizers/word_scanners.py:102`
(`find_closing_delimiter`, nests on every bare `{`) vs `psh/lexer/pure_helpers.py:546-554`
(`validate_brace_expansion`, nests only on `${` — the bash rule). Probed: `a[${v:-{]}]=1` → bash key `{]`, psh
`command not found` (never classified as an assignment); `a[${v:-{y}b}]=1` → bash key `{yb}`, psh key `{y}b` — the
two layers commit to different readings of the same text.

#### F. Combinator grammar and visualization renderers

**F1 (PC-1) — the combinator rejects `do` as a for/select in-list item; bash and the RD parser accept it.**
`psh/parser/combinators/control_structures/loops.py:47-59`. Probed: `for i in do; do echo $i; done` prints `do`
in bash and psh-RD; the combinator raises "Expected command" rc 2. Not in the parity corpus, not xfailed, not in
the documented-gaps list — silent drift, and the docstring asserts a list-ending rule bash does not have.

**F2 (PC-2) — `elif_parts` renders as raw dataclass repr in 3 of 4 AST renderers, including the default
`--debug-ast` tree.** `IfConditional.elif_parts` is a list of `(condition, body)` tuples; only `ASTPrettyPrinter`
handles tuples. Probed CLI output for `if/elif`: `AsciiTreeRenderer` prints the condition's full dataclass repr
as a label, `SExpressionRenderer` dumps `str(tuple)`, `ASTDotGenerator` drops the subgraphs entirely. `if/elif`
is a common construct; the flagship debugging surface emits garbage for it.

#### G. Heredoc-oracle ordering and printf format contract (utils)

**G1 (HD-1 / ASTUTIL) — the heredoc completeness oracle closes pending heredocs out of order.**
`psh/utils/heredoc_detection.py:420-428`, twinned in `psh/scripting/command_accumulator.py:265-271`. Both loops
test each incoming line against *every* unclosed delimiter and close whichever matches; bash consumes bodies
strictly in order. Probed (file and stdin modes): `cat <<A; cat <<B` / `B` / `A` / `tail-body` / … → bash reads
`A`'s body as `"B"`; psh closes `B` early and later executes body lines as commands. The lexer's own body
collector gets the ordering right — it is purely the oracle terminating the buffer early.

**G2 (PF-1 / ASTUTIL) — `printf '%-%'` prints `%` (rc 0); bash 5.2 errors — and the comment asserts the false
bash behavior.** `psh/utils/printf_formatter.py:151-155`. `_CONVERSIONS` includes `%`, so any `%` reached
through `_parse_spec` (with flags/width between) emits a literal `%`. Probed: `%-%`, `%5%`, `% %`, `%.2%` all
print `%` rc 0 in psh; bash errors ``invalid format character`` rc 1 for all four. The inline comment states the
opposite of the pinned oracle.

### MED (101) — clustered

**Analysis & visualization sidecars run a grade below the execution path (the single largest MED class).**
The linter lacks the variable-definition knowledge its sibling has — a clean `set -eu` script using
`for f in a b` and `read -r line` fails `--lint` with rc 1 (LINT-1, HIGH-adjacent, graded HIGH in VISIT). Beyond
it: a stale string-twin `_has_parameter_default` overrides the structural per-ref default flag so one defaulted
expansion suppresses undefined-warnings for every other reference in the word (VAL-1); redirect analysis regexes
raw strings while `target_word` sits unused, flagging a single-quoted here-string `<<< '$X'` as an undefined
variable (LINT-2); metrics counts a bare assignment `n=$(date)` as an external command (MET-1);
`visit_word_substitution_bodies` names four consumers but only two call it, so `--validate` misses typos inside
`$(...)` that `--lint` catches (TRAV-1); a deprecation/typo advisory lives in three drifting tables producing
duplicate and mislabeled output and flagging `dc` (a real utility) as a typo of `cd` (VAL-2); one unknown command
is reported twice, once mislabeled "Function" (LINT-3); and the existence-test suppression is dead for its
canonical target while firing on fuzzy substring matches — exactly backwards (VER-1). The combinator's `select`
loop breaks the commitment discipline its sibling loops establish and rejects the valid no-`in` form (PC-3, PC-4);
three renderers re-introduce hand-kept field lists `node_fields` was built to kill, silently dropping the
`background` marker (PC-8). **Prescription unchanged from r19:** harness these visitors (goldens + strict-errors +
self-tests) or delete them; the middle path produces confidently wrong output under flags that advertise rigor.

**Chokepoint prose that greps false (the twin-divergence residue).** `VariableStore`'s "single transaction
boundary … every write" is contradicted by eleven direct `scope_manager` callers, and `store.unset`/`add_attributes`
have zero callers (CORE-5); `with_redirections` is dead code taught as the live path in three documents while
`guarded_redirections` duplicates its body (IORED-1, EXEC-7); `format_redirect_error`'s "no longer diverge"
docstring is violated by a `line N:` prefix split within one error class (IORED-2); `target_fd` "the single source
of truth" is re-derived at seven sites plus a full `_target_fds` twin (IORED-5); `REDIRECT_OPEN_FLAGS`'s "single
edit" excludes the builtin backend's second mode encoding (IORED-6); `command_resolver`'s "every `$PATH` scan"
has a `shutil.which` fallback with different empty-component rules (EXEC-5); the parser's "single chokepoint"
sentence names the wrong function in two places after the H12 guard move (PRD-4); and both the accumulator and
`input_preprocessing` carry a private copy of the trailing-backslash-continuation rule (SCRIPT-7). The affix path
`_expand_at_with_affixes` bypasses the expansion engine's split/glob passes entirely (EXPAN-3); `local`'s final
commit still runs on `create_local` (the declaration engine's own documented "Phase 4 work").

**strict-errors taxonomy erosion at the same borders.** Bare `ValueError`/`TypeError` used as an expected-error
signal or swallowed as one: the arithmetic evaluator's last-resort `TypeError` arm masks internal defects
(ARITH-4, demonstrated with a synthetic offender); `[[ ]]` raises bare `ValueError` for its four expected errors,
forcing `core.py` to catch `(ValueError, TypeError, OSError)` (EXEC-4); `let` and `(( ))` relabel internal
defects as user errors (BD-M8); `read`/`parse-tree`/`kill` swallow or abuse the internal-defect classes (BIO-8);
`define_alias` raises plain `ValueError` for an expected user error (EXPAN-12); the combinator's `can_parse`
catches `AttributeError/IndexError/TypeError` and relabels them "can't parse" (PC-13). Each quietly weakens the
suite-wide guarantee.

**hasattr/getattr guards on always-present fields (the silent-drift class, found by nearly every scope).**
Reads of dataclass or `Shell` fields that always exist, via `getattr(..., default)` — so a future rename
degrades silently instead of failing loud under strict-errors: IORED-7 (five `Redirect` fields), EXEC-12 (AST
node fields + `ShellState` properties), CORE-7/12, INTER-10, SCRIPT-5 (`history_expander`, which would silently
disable history expansion *and* recording), PRD-6 (four `Token` fields), LEX-10, ASTUTIL WRD-1 (six `WordPart`
guards), BIO-9 (`trap_manager`/`interactive_manager` — a rename would silently skip EXIT traps), VISIT VAL-L9.
**This is a candidate for a single tooling guard** (flag `getattr(node/shell/state, 'literal', default)` on known
dataclass fields), which would close the whole class the way the import-layering ratchet closed cycles.

**Dead / ghost surface (referenced only by its own tests = dead, per the tree's own rule).** `JobManager.list_jobs`
(EXEC-6, a stale rendering twin); the combinator's ~21-attribute `TokenParsers` shelfware and the ghost
convenience layer of free functions the `__all__` advertises (PC-5, PC-6); `Token.span`/`SourceSpan` and
`TokenPart.error_message` in the lexer (LEX-3, LEX-4); `VariableTracker.mark_local`/`get_current_scope_vars` plus
the write-only `is_exported`/`is_readonly` flags (EV-2); `has_unclosed_heredoc`, `is_inside_expansion`,
`set_signal_registry` in utils (DEAD-1); `BuiltinRegistry.all()` and `InputSource.get_location` (BD-LOW, SCRIPT-LOW).

**Live edge-correctness MEDs worth their own lines.** `select` runs its body on an empty input line instead of
redisplaying the menu, and re-displays the menu before every prompt (EXEC-V1/V2); `history -d` shifts the file
read cursor so a following `history -n` duplicates entries (INTER-4); the KeyDecoder corrupts a UTF-8 character
split across the 4096-byte read boundary (INTER-5); quick substitution `^old^new^` never echoes its expansion
while the `!`-path does (INTER-6); `HistoryNavigator.first()` leaks raw newlines into the single-line EditBuffer
(INTER-7); `mapfile` has no read-error handler so a closed stdin surfaces as "write error" (BIO-4); `pwd -P -L`
ignores last-flag-wins order (BIO-6); `wait`/`disown` still use the deprecated jobspec shim with hand-rolled
diagnostics (BIO-5); the `SignalRegistry.register` failure paths corrupt the record store (SIG-1); `>&$v` with a
non-numeric expansion errors where bash writes a file (IORED-3); `PSH_AST_FORMAT` from the environment is
clobbered at init (AD-1); `command declare -a x=(1 2)` corrupts the value because the wrappers drop the
`BuiltinContext` (BD-M4); getopts accepts `:` as a valid option character (BD-M5); the `history` builtin handles
one option token and discards the rest (BD-M1); alias name validation rejects names bash accepts (EXPAN-5); nounset
does not cover `$!` (CORE-3); `set -H`/`+H` is rejected though the registry reserves the `$-` letter (CORE-4).

**Monoliths (the size-findings map, unchanged in shape from r19).** 91 functions exceed 80 lines (3.2%). Nine of
the ten longest drew explicit findings: `ShellState.__init__` 272 (linear wiring), `_execute_pipeline` 201 (hot
path), `_run_command` 191 (holds EXEC-1/-3), `main` 177, `ReadBuiltin.execute` 175, `expand_history` 173,
`set_variable` 171 (the next drift bug's hiding place — the readonly check appears twice inside it),
`ExternalExecutionStrategy.execute` 157, `_declare_assignment` 151, `apply_prefix` 151. 26 modules exceed 600
lines. The critic notes CORE under-engaged the size axis on its two 1,100+-line files.

**Test-infrastructure and doc MEDs.** The mypy `check_untyped_defs` override glob is stale — `psh.parser` (no
`.*`) matches only the package `__init__`, so `array_flat_text.py` silently escapes deep checking, unguarded
(TESTINF-1); the `find_bash()` oracle chokepoint is documented but unenforced, with ~15 files hardcoding
`/opt/homebrew/bin/bash` or using a bare `bash` (three with no fallback → `FileNotFoundError` on the Linux
nightly), and no tooling guard forbids it (TESTINF-2). `ARCHITECTURE.md` teaches an inverted command-strategy
precedence and omits a whole strategy (XCUT-1, probed: a function shadows a builtin, the opposite of the sketch),
names phantom `IfConditional.then_stmt`/`else_stmt` fields (XCUT-2), and states a caret-rendering "limitation"
the code already fixed with a dangling "see appraisal finding 12" reference (XCUT-3) — all three escaping the
doc-snippet drift-lock, which covers CLAUDE.md and only def/class names.

### LOW (119 — sample)

Stringly enum comparison `job.state.name == 'RUNNING'` (BIO-LOW); ten identical `os.stat` copies in `test`/`[`
(BIO-LOW); `_ClosedStream` missing `fileno()`/`isatty()` where its sibling has them (IORED-15); `exec {v}>&-` with
unset `v` silently succeeds where bash errors (IORED-11); a `%` inflating the redirect-flags table; the sexp
renderer mapping any non-`&&` operator to `||`; `--debug-ast` node headers naming `ArithmeticCommand`/`CaseStatement`
where the classes are `ArithmeticEvaluation`/`CaseConditional` (DBG-L8); `\w` prompt contraction prefix-matching
sibling directories of `$HOME` (INTER-8); `Word.source_text()` malformed for ANSI-C words (ASTUTIL-LOW);
`ArrayInitialization.elements` a stored dual-truth straggler whose documented keeper (`executor/array.py`) no
longer reads it (ARR-1, MED-borderline); `CasePattern` and `Program` docstrings teaching an obsolete parser
asymmetry and aspirational fields; two `CasePhase` enums and two `Parser` classes in `psh/lexer` and `psh/parser`
(XCUT-7/8); three `fnmatch` sites outside the pattern-engine chokepoint (XCUT-9); `LexerContext` documented as a
"backward-compatible alias" while being the dominant name across 12 recognizer files (XCUT-5); root `CLAUDE.md`
mypy "240 files" now 258 (XCUT-10); the `interactive` pytest marker help and `BASH_SPECIFIC` dead enum member
(TESTINF-3/4); `import sys`/`import os`/`import re` inside hot methods across several scopes; and the perennial
`__all__`-vs-imports census gaps.

---

## Cross-package defect ledger

Duplication and divergence that structurally evade per-scope review, each needing a named owner because no
subsystem sees the whole:

| Concern | Sites | Status |
|---------|-------|--------|
| **Assoc-array subscript keying** | `expansion/arrays.py:311` (read/unset), `operators.py:185` (is-set), `arithmetic/parser.py:340` (arith), lexer subscript collection + assoc `$'...'` decode, `core/variables.py:318` (unsubscripted) | **Six inconsistent implementations of one feature** — write stores literal, read/unset resolve through a variable, is-set uses a third expansion, arith must parse-as-arithmetic, `$'...'` keys undecoded, `$assoc` returns empty |
| `+=` / append engine | `core/variable_store.py:116` (the one engine) vs `builtins/environment.py:200` (`export -n` hand-roll) | **Diverged** (`-i n+=3` → 23 vs 5) |
| Attribute ops vs nameref resolution | `core/scope.py:1087/1142` (attribute) vs the nameref-resolving write path | **Diverged** (export/readonly/`-i` through a nameref hit the wrong variable) |
| History-reference grammar | `interactive/history_expansion.py:16` (quote-blind regex) vs `expand_history` (the real expander) | **Diverged, loses user history** |
| `with_redirections` vs `guarded_redirections` | `io_redirect/manager.py:289` (dead) vs `:309` (live, duplicated body) | Dead twin taught as live in 3 docs |
| `target_fd` classification | `io_redirect/file_redirect.py:709` (claim) vs ≥7 re-derivations + `process_sub.py:246` twin | Re-derived, agree today, unenforced |
| Redirect-error `line N:` prefix | `io_redirect/manager.py:192` vs the errno-None escape at `command.py:921` | **Diverged within one error class** |
| Child command-word resolution | `executor/command.py:489/537/602` (pre-shortcuts) vs `_resolve_command` | **Diverged** (posix prefix persist; quoted `\echo`; `exec` shadowing) |
| PATH walk | `command_resolver.search_path` vs `strategies.py:75` (`shutil.which`) | Diverged empty-component rules |
| Heredoc-close ordering | `utils/heredoc_detection.py:420` vs `command_accumulator.py:265` | **Diverged** (out-of-order close, both modes) |
| Trailing-backslash-continuation | `command_accumulator.py:345` vs `input_preprocessing.py:116` | Twin, agree today |
| `${...}` extent | `word_scanners.py:102` (bare-`{` nesting) vs `pure_helpers.py:546` (`${`-only) | **Diverged** (brace-key assoc assignments) |
| Analysis is-assignment / definition sources | `linter` vs `enhanced_validator` vs `metrics` | **Diverged** (definition knowledge, assignment counting) |
| `VariableStore` transaction boundary | docstring claim vs 11 direct `scope_manager` callers + dead facades | Prose contract false; element/append chokepoints real |

## Themes

1. **The r19 prescription is proven, not just adopted.** Every chokepoint guarded by a registry plus a
   drift-lock meta-test survived adversarial re-derivation; every prose-only "single source of truth" drifted.
   The import-layering ratchet is *exactly* tight (205 = 205), the CLAUDE.md drift-lock kept all nine subsystem
   docs accurate, and the guard-the-guard tier is now the tree's most exemplary infrastructure. The cure for
   what remains is not new discipline — it is extending this pattern to `ARCHITECTURE.md`'s fenced blocks, to the
   `find_bash()` oracle, to the hasattr-guard class, and to the help-synopsis family.

2. **The binding constraint moved from elegance to correctness.** r19's #1 defect was divergent twins; the
   campaign healed most, and elegance rose tree-wide (the median is now A−, the floor B). What deeper probing
   surfaced is ~30 live defects where an *implemented* feature contradicts its own contract — orthogonal to the
   graded axes, which is why the letters improved while the live-defect list grew. These are correctness debts,
   not missing features.

3. **Associative-array subscript keying is the round's signature finding** — one feature, six inconsistent
   implementations across six modules, found in fragments by four scopes and whole by none. It is the exact
   "same rule implemented N times, drifted" pattern of r19, but concentrated in a single feature rather than
   spread across a mechanism. It deserves a dedicated cross-package campaign with a bash-pinned key-semantics
   suite as its spine.

4. **Analysis/diagnostic sidecars remain a full grade below the execution path** — the identical r19 result.
   Seven-plus verified false-fire/no-op advisories, `--lint` exiting 1 on clean idiomatic scripts, `--debug-ast`
   rendering `if/elif` as raw repr. They have no oracle and almost no tests. Same fork: harness them like the
   execution path or delete them.

5. **strict-errors erosion recurs at the same borders** — bare `ValueError`/`TypeError` as expected-error
   signals in arithmetic, `[[ ]]`, `let`, `read`, `kill`, `define_alias`, and the combinator. Each is a small,
   local re-typing; jointly they make the suite-wide guarantee quietly weaker than documented in ~6 subsystems.

6. **`ARCHITECTURE.md` is again the worst single doc liability, but now narrowly.** The drift-lock r19 installed
   held for the subsystem docs; the flagship guide escapes it (only def/class names checked) and drifted on three
   load-bearing sketches. Extending the snippet drift-lock to its fenced blocks closes the last teaching gap the
   campaign left open.

7. **Efficiency is a solved culture.** No algorithmic cliff was found by any of 33 agents (the critic confirms).
   The residue is a couple of documented, bounded O(n²) paths (`${x#pat}` prefix strip, the accumulator re-parse)
   and per-prompt/per-keystroke churn — nothing worse than r19 found.

## Recommended next tier

**Tier 1 — HIGH, roughly file-disjoint campaign clusters** (each ends with bash-verified pins per the standard
workflow):

1. **Associative-array keying (the cross-package spine):** unify the key rule — literal-string keys on
   write/read/unset/is-set (EXPAN-1/2), lazy/tolerant arithmetic subscripts without the `.strip()` (ARITH-1),
   `$'...'`/`$"..."` decode (LEX-5), and `$assoc` → `${assoc[0]}` (CORE-V1). One `assoc_key()` chokepoint,
   one bash-pinned key-semantics suite.
2. **Core mutation authority:** nameref-resolve attribute add/remove (CORE-1), route `export -n +=` through the
   append engine (CORE-2/BD-H3), and reword the `VariableStore` transaction docstring to what is true (CORE-5).
3. **Declaration `-p`/operand semantics:** `export -p`/`readonly -p` with operands must process operands, not
   drop them (BD-H1/H2), and re-pin the contradictory conformance tests with a *set* variable.
4. **Builtin option-parse convergence:** migrate `printf -v` (BIO-1), `read -N` timeout/silent plumbing
   (BIO-2), and the `wait` WNOHANG pid/status fix (BIO-3); adopt `parse_flags(_ordered)` for `pwd`, `env`,
   `signals`, `parse-tree`, and the `jobs` re-walks (BIO-6/10/12).
5. **Executor resolution shortcuts:** make the temp-scope, `exec`, and backslash-strip decisions ask the same
   question `_resolve_command` answers (EXEC-1/2/3); add the `map_child_exception` and xtrace-emit chokepoints
   the twins bypass (EXEC-10/11).
6. **History-reference unification:** one quote-aware scanner shared by `expand_history` and the recording gate,
   gated on interactive mode + histexpand (INTER-2, SCRIPT-1/2); fix `!0` and the dead vi repeat count
   (INTER-1/3).
7. **Parser/lexer string corners:** bracket-depth array-head scan (PRD-1), structured `*_unclosed` marker for
   backticks + raising `strip_*` fallbacks (PRD-2, LEX-1), and the one `${...}` extent rule (LEX-2).
8. **Heredoc-oracle ordering + printf:** head-of-queue close policy shared by the two oracle copies (HD-1) and
   dropping `%` from `_CONVERSIONS` (PF-1).
9. **Analysis-sidecar fork:** the fix-or-delete decision for the ~10 false-fire/no-op advisories and the
   combinator `elif`/`do`/`select` renderer+grammar defects (LINT-1, VAL-1/2, MET-1, TRAV-1, PC-1/2/3/4/8).

**Tier 2 — MED clusters:** the dead-API deletion sweep under "test-only = dead" (JobManager.list_jobs, combinator
shelfware + ghost convenience layer, lexer `span`/`error_message`, utils orphans, VariableTracker write-only
flags); a single hasattr-guard tooling guard closing the silent-drift class tree-wide; the strict-errors
re-typing pass (arithmetic TypeError arm, `[[ ]]`/`let`/`read`/`kill`/`define_alias` typed errors); the
`with_redirections`/`target_fd`/`REDIRECT_OPEN_FLAGS` chokepoint consolidation; the help-synopsis registry for
the hand-rolled-parse family (BD-M7); the `ARCHITECTURE.md` drift-lock extension + the three drifted sketches;
the mypy override-glob fix + guard and the `find_bash()` oracle guard (TESTINF-1/2); the monolith reads
(`set_variable`, `_run_command`, `ShellState.__init__`); and the edge-correctness MEDs (`select` empty-line,
`history -d` cursor, UTF-8 boundary decode, `mapfile` read-error shape).

**Explicitly not prescribed:** micro-optimizations anywhere (efficiency is solved); unification of the three
command-position tracking machines (the non-unification essay is correct and exemplary); deduplication of the
five escape dialects (`escapes.py`'s "do NOT deduplicate" analysis stands, re-verified 26/26 this round);
combinator-parser productionization (educational scope is documented — it needs the two grammar fixes and the
renderer repair, not feature work).

## Coverage & method summary

33 agents (16 auditors + 16 adversarial verifiers + 1 completeness critic), ~7.6M subagent tokens across the
run, ~2,000 tool invocations, all reads from the pinned snapshot at `d1b8ef35`. Scope tiling verified by the
critic: all 258 `psh/**/*.py` files map to exactly one code scope (TESTINF and XCUT are intentional non-exclusive
overlays over test files and whole-tree concerns). Whole-tree metrics (AST-measured, independently reproduced):
70,089 LOC, 2,820 functions, 91 over 80 lines (3.2%), 26 modules over 600 lines, module-docstring coverage
258/258 = 100% — flat against r19's 70,133 / 2,865 / 94 / 25 / 100%, confirming the campaign added correctness
pins and chokepoints without bloat. Verification: every HIGH/MED re-read at the cited line by an independent
agent instructed to refute; every behavioral probe re-run from scratch against live bash 5.2.26 (never trusting
archives); dead-code claims re-grepped against dynamic dispatch; meta-guards run against synthetic offenders.
**Verdict distribution — 232 CONFIRMED / 13 ADJUSTED (mostly severity-down or scope-sharpening) / 0 REFUTED**,
with all 13 adjustments incorporated above and 12 verifier-added findings folded in. Per-subsystem prose reports
with verification addenda: `tmp/appraisal-r21-reports/`.

**Known coverage gaps (deliberate):** the ~105-file `docs/` prose tree beyond `ARCHITECTURE.md` and the nine
subsystem `CLAUDE.md`s was not audited; `.github/workflows/` (the release-gate machinery); `examples/`;
`tools/`; the *content* of the ~640 ordinary test files (test-infra graded infrastructure only);
`tests/parser_differential/` and `tests/performance/benchmarks/` harness internals; and real-PTY interactive
rendering and signal-delivery paths (read-verified only). This is a point-in-time appraisal, not a compatibility
promise or an implementation plan already completed. Earlier reviews (including the parallel `#20` draft at
v0.698) were not consulted as evidence: every defect above is tied to the current code at `d1b8ef35` and, where
behavioral, to a fresh reproducer.
