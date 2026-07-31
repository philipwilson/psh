# VERIFY-ROUND3 — slot 2.5, tip 6a70416e, verdict BOUNCE (3 blockers, 16 nits)

Full machine-readable copy: VERIFY-ROUND3-issues.json (same directory).

## BLOCKER 1 [diffAudit] — 

UNDECLARED BEHAVIOR DELTA + UNREACHABLE SHIPPED CODE: named-fd here-string `{v}<<<word`. The slot adds `('<<-', HEREDOC_STRIP)` and `('<<', HEREDOC)` to the NAMED-fd operator table in `psh/lexer/recognizers/operator.py#_try_var_fd_redirect` but NOT `('<<<', HERE_STRING)` — even though the DIGIT-fd table in the same file (lines ~212-220) already has `('<<<', TokenType.HERE_STRING)`. Consequence: `{v}<<<w` now lexes as `{v}<<` + `<w`, so its parse error changes. Simultaneously the diff ADDS a `<<<` arm to `psh/io_redirect/file_redirect.py#apply_var_fd_redirect` (`if rtype in ('<<', '<<-', '<<<')`) with a comment asserting the form is supported ("Here-document / here-string forms: `{v}<<EOF`, `{v}<<-EOF`, `{v}<<<w`"). That arm is UNREACHABLE — the lexer cannot emit a HERE_STRING token with `var_fd`, and RD `_parse_here_string` never sets `var_fd` — so the branch ships dead code carrying a false claim. There is no `{v}<<<` row in `tests/unit/io_redirect/test_named_fd_heredoc.py` and no `<<<` row anywhere in `tmp/remediation-ledgers/2.5.md` (grepped `{v}<<<`, `named-fd here`, `here-string`), so the delta is neither declared nor pinned — brief §7: 'Any behavior delta beyond the chartered fix ... DECLARED + PINNED (an unpinned improvement is still a bounce)'. This is the same fd-kind axis that produced round-2 blocker R7-A; it was closed for `<<`/`<<-` and left open for `<<<`.

### Evidence
```
REPLAYED, clean detached worktrees (vf-base e36116c3, vf-tip 6a70416e; discriminator: psh.__file__ under each tree), oracle /opt/homebrew/bin/bash 5.2.26.
Script: `exec {v}<<<hello` / `cat <&$v` / `echo FD=$v`
  bash 5.2.26 : `hello|FD=10|` rc=0
  base e36116c3: `psh: -c:1: Parse error (line 1, column 10): Expected file name` rc=2
  tip  6a70416e: `psh: -c:1: Parse error (line 1, column 11): Expected delimiter after here document operator` rc=2   <-- message AND column changed
Control (digit fd, unchanged): `cat 0<<<hello` -> bash `hello` rc0, base `hello` rc0, tip `hello` rc0.
Unreachability proven by direct call at tip: `FileRedirector.apply_var_fd_redirect(Redirect(type='<<<', target='hello', var_fd='v'))` -> succeeds, sets v=10; but no parse path can build that node (`exec {v}<<<hello` errors at parse time, above).
Files: psh/lexer/recognizers/operator.py:286-293 (named-fd table, no `<<<`); psh/io_redirect/file_redirect.py:537-546 (the `<<<` arm + false comment); psh/parser/recursive_descent/parsers/redirections.py#_parse_here_string (no var_fd).
```

## BLOCKER 2 [diffAudit] — 

ANTI-BYPASS GUARD DOES NOT BITE ON THE NAMED-FD AXIS, and the committed invariant text is false for it. The MEDIUM-10a triad claims (psh/ast_nodes/redirects.py module docstring: 'a structurally-heredoc plain `Redirect` that reaches execution raises the typed ... NonExecutableRedirectError'; psh/io_redirect/CLAUDE.md: 'Both backends route executable heredocs by `isinstance` ... and give the parse-state value an EXPLICIT arm raising ... NonExecutableRedirectError'). Both explicit arms live in `apply_fd_plan` and `setup_builtin_redirections`, but a plain `Redirect` carrying `var_fd` is routed to `apply_var_fd_redirect` BEFORE either arm is reached, where the new `<<`/`<<-` branch does a bare `redirect.heredoc_content` read and dies with a raw `AttributeError`. This value shape is one THIS BRANCH newly created: the diff adds `var_fd=token.var_fd` to RD's bare-parse arm (psh/parser/recursive_descent/parsers/redirections.py), and the operator-table change makes `cat {v}<<EOF` parse at all — at base the same source raised ParseError, so the shape did not exist. Both of the dev's synthetic-offender tests (tests/unit/io_redirect/test_heredoc_executable_type.py::test_synthetic_offender_raises_the_typed_error_at_the_fd_backend and ::test_synthetic_offender_raises_at_the_BUILTIN_STREAM_backend) construct `Redirect(type='<<', target='EOF')` with NO var_fd, so the guard's universe does not cover the class it claims (brief: 'executable anti-bypass guard RUN against a synthetic offender'; AXIS-QUANTIFICATION rule — the fd-kind axis is unvaried in the guard, exactly the R7-A lesson).

### Evidence
```
REPLAYED at tip 6a70416e in a clean detached worktree (psh.__file__ verified under the tree):
  parse(tokenize('cat {v}<<EOF')) -> Redirect type='<<' var_fd='v'      [tip]
  parse(tokenize('cat {v}<<EOF')) -> ParseError 'Expected file name'    [base e36116c3 — shape did not exist]
Feeding that offender to execution at tip:
  file_redirector.apply_var_fd_redirect(Redirect(type='<<',target='EOF',var_fd='v'))
      -> AttributeError: 'Redirect' object has no attribute 'heredoc_content'
  io_manager.apply_redirections([offender])
      -> AttributeError: 'Redirect' object has no attribute 'heredoc_content'
  io_manager.setup_builtin_redirections(SimpleCommand(words=[Word(parts=[])], redirects=[offender]))
      -> AttributeError: 'Redirect' object has no attribute 'heredoc_content'
Expected per the committed docs in this diff: NonExecutableRedirectError in all three. Sites: psh/io_redirect/file_redirect.py:496-546 (apply_var_fd_redirect, reached from file_redirect.py:780, :1082 and manager.py:529, :1047 — all four ahead of the guarded arms at file_redirect.py:713-737 and manager.py:628-640).
```

## BLOCKER 3 [resurrection] — 

UNDECLARED, UNPINNED behavior delta on `{v}<<<WORD` (named-fd here-string). Commit ab6528d9 added `('<<-', HEREDOC_STRIP)` and `('<<', HEREDOC)` to the longest-first operator table in `psh/lexer/recognizers/operator.py#_try_var_fd_redirect` but NO `<<<` entry, so `{v}<<<hello` now mis-lexes as HEREDOC + REDIRECT_IN + WORD instead of base's REDIRECT_IN + rest. The user-visible diagnostic (message text AND error column) changes on both parsers and all three non-interactive channels. Nothing in the tree references `{v}<<<` (grep over tests/ for `{v}<<<` and for var_fd near here-string: zero hits), the ledger's R7-A/B33 section never mentions the spelling, and brief §7 requires any behavior delta beyond the chartered fix to be DECLARED + PINNED.

### Evidence
```
REPLAYED, 6 cells per SHA (parser rd|combinator x channel -c|file|stdin), throwaway detached worktrees.
BASE e36116c3: rc=2, stderr `psh: -c:1: Parse error (line 1, column 10): Expected file name` (Context: `exec < -> HERE <- hello ; cat`)
TIP  6a70416e: rc=2, stderr `psh: -c:1: Parse error (line 1, column 11): Expected delimiter after here document operator` (Context: `exec << -> HERE <- hello ; cat`)
bash 5.2.26 (/opt/homebrew/bin/bash --norc -c 'exec {v}<<<hello; cat <&$v'): rc=0, stdout `hello`.
Token dump at TIP: `tokenize('exec {v}<<<hello')` -> WORD 'exec' | HEREDOC '<<' var_fd='v' | REDIRECT_IN '<' | WORD 'hello'.
BOUNDED: the eight other `{v}` spellings (>, >>, <, <>, >|, >&1, <&0, <<) are byte-identical base/tip/bash (matrix in /Users/pwilson/src/psh/tmp/verif-t2-matrix.sh). Session completeness for `cat {v}<<<hello` is Complete at BOTH SHAs, so no PS2/phantom-body class is introduced -- the delta is confined to the diagnostic.
```

## NIT 1 [diffAudit] — 

Out-of-charter doc churn in `docs/architecture/tour_of_psh_internals.md`: the `--debug-ast=pretty` example block is replaced wholesale (54 lines changed). Brief §6 scopes doc work to subsystem CLAUDE.md invariant prose + pointers. I verified the replacement is ACCURATE and that the old block was already stale at base — so this is pre-existing-rot repair, not a behavior claim, but it is outside the slot's declared doc scope and enlarges the diff a reviewer must audit.

```
`python -m psh --norc --debug-ast=pretty -c 'echo "Hello, $USER" | wc -c > out.txt'` run at BOTH SHAs in clean worktrees: base e36116c3 and tip 6a70416e emit byte-identical output, and it matches the NEW doc block (indented tree beginning `=== AST Debug Output (recursive_descent) ===` / `Program:` / `  statements: [`), not the old one-line `SimpleCommand(args=[...])` form the doc previously showed.
```

## NIT 2 [diffAudit] — 

Unmigrated consumer of the removed field: `tests/unit/tooling/test_parser_contract_guards_s4.py:246-248` still does `if isinstance(node, Redirect) and node.type == "<<": heredoc_bodies.append(node.heredoc_content)`. With `heredoc_content` gone from the base class, this only survives because that test's fixtures always parse with collected bodies (so every `<<` node is a HeredocRedirect); a bare-parse AST reaching that walker raises AttributeError. The file is untouched by the diff even though six other consumer sites were migrated to `isinstance(node, HeredocRedirect)`.

```
git grep -n heredoc_content <tip> -- tests/ -> tests/unit/tooling/test_parser_contract_guards_s4.py:249 uses the attribute guarded only by `isinstance(node, Redirect) and node.type == "<<"`, i.e. by the OPERATOR STRING, which is precisely the discriminator the slot replaced everywhere else.
```

## NIT 3 [diffAudit] — 

Undeclared (but non-observable) continuation-hint change for `cat <<-` with no delimiter: the session's hint kind/detail moves from HEREDOC/'-' to INCOMPLETE_STRUCTURE/None. I probed all three non-interactive channels and found no observable delta, so this is hint-internal only — recording it because it is a session-answer change outside the three declared deltas.

```
REPLAYED. CommandAccumulator.feed('cat <<-'): base e36116c3 -> ('NEEDMORE','HEREDOC','-'); tip 6a70416e -> ('NEEDMORE','INCOMPLETE_STRUCTURE',None). Observable behaviour identical at both SHAs for -c, script-file and stdin: `Parse error (line 1, column 8): Expected delimiter after here document operator`, rc=2 (bash 5.2.26 errors differently at both SHAs: `syntax error near unexpected token 'newline'`, rc=2 — pre-existing divergence, unchanged).
```

## NIT 4 [diffAudit] — 

Ordering change in `psh/parser/session.py#feed`: the single lex now happens at step 2, BEFORE the history-reference check (step 4), where base only lexed inside `_trial_parse` after that check. The exception is captured and re-raised so the error path keeps its position, and my 61-row session corpus showed no delta — but a history-bearing line is now lexed where base never lexed it, which is an unpinned ordering change (ops.lex_calls bookkeeping and any lexer-side diagnostics for such lines). Not probed with history expansion enabled; flagged for the integrator, no red/green claim made.

```
psh/parser/session.py: step 2 `unit, lex_error = self._lex_preview(preview)` now precedes `if self.inputs.detects_history_reference(preview)`. Base ordering: contains_heredoc regex -> history check -> _trial_parse (which lexed).
```

## NIT 5 [diffAudit] — 

EVIDENCE-HYGIENE WARNING for other verifiers/the integrator (not a defect in the branch): the shared session scratchpad worktree `.../scratchpad/v3-tip` (checked out at branch tip 6a70416e) carries an UNCOMMITTED mutation of `psh/lexer/recognizers/operator.py` that deletes `('<<-', HEREDOC_STRIP)` and `('<<', HEREDOC)` from BOTH the digit-fd and named-fd tables — a prior round's mutation experiment left in place. Any base-vs-tip red/green measured in that tree is false. My first probe run in it produced fabricated 'regressions' for `cat 0<<EOF`, `cat 2<<EOF`, `cat 9<<EOF`, `cat {v}<<EOF`; all vanished on clean worktrees. Every claim in this report was re-derived in fresh detached worktrees created and removed for this audit.

```
`git -C .../scratchpad/v3-tip status --porcelain` -> ` M psh/lexer/recognizers/operator.py`; `git diff` there shows the two table entries removed at both tables. Clean re-run (vf-base/vf-tip) reduced my 61-row session differential from 10 differing rows to 4 — the 4 real ones being the two declared deltas (`cat <<$(x)`, `echo $(cat <<EOF`), the MEDIUM-3 fix (`echo \<<EOF`), and the `cat <<-` hint nit above.
```

## NIT 6 [resurrection] — 

DEAD PRODUCTION CODE advertised as live: the `<<<` arm the branch added to `FileRedirector.apply_var_fd_redirect` (`if rtype in ('<<', '<<-', '<<<')` -> `redirect_herestring_content(...)`) is UNREACHABLE. `var_fd` is set only at `psh/lexer/recognizers/operator.py:275` and `:300`, and that table has no `<<<` entry, so no `Redirect(type='<<<', var_fd=...)` can be produced by either parser. The comment above the arm advertises `{v}<<<w` as supported, and `redirect_herestring_content` was extracted specifically to serve it. Tied to the blocker above: adding `<<<` to the table would make this arm live and immediately expose a second asymmetry -- the combinator's here-string path passes `var_fd` (`combinators/commands/redirections.py:146`) while RD's `_parse_here_string` does not (`recursive_descent/parsers/redirections.py:184-190`), so `{v}<<<w` would work on one parser and silently drop the fd on the other.

```
grep --include=*.py 'var_fd=' psh/ -> only operator.py:275,300 emit it on a Token. Token dump proves the `<<<` var-fd token is unconstructible (see blocker evidence). grep for `{v}<<<` across tests/ -> zero hits, so the arm has no coverage.
```

## NIT 7 [resurrection] — 

Stale module docstring in `psh/utils/heredoc_detection.py` after the one-grammar fix. Lines 5-7 still assert the module is "the single source of truth for heredoc line-gathering, consumed by the shared completeness oracle (`scripting/command_accumulator.py`) that both the script/-c/stdin path and the interactive multiline path drive", and lines 22-24 still list "the completeness oracle here (:func:`open_heredoc_specs`) and in the CommandAccumulator" among the layers delegating close decisions. After slot 2.5 the completeness oracle derives pending heredocs from lexer events (`session.py#_lexer_pending_heredocs`) and no longer calls `open_heredoc_specs`; `command_accumulator.py` imports nothing from this module. This is subsystem-doc-grade prose stating a consumer relationship that no longer exists.

```
grep for open_heredoc_specs/contains_heredoc in psh/ (excluding heredoc_detection.py) -> live consumers are only `scripting/lex_parse.py:41,110`, `interactive/history_expansion.py:20,175`, `interactive/line_editor_helpers.py:31,61,66,75`. grep 'heredoc' psh/scripting/command_accumulator.py -> no heredoc_detection import; it delegates to ParseSession.
```

## NIT 8 [resurrection] — 

Out-of-scope file touched: `docs/architecture/tour_of_psh_internals.md` (+54/-... lines) is not in the brief's Scope list and is not a subsystem CLAUDE.md (brief item 6 names only those). It is NOT on the NEVER-TOUCH list and the edit is doc-truth-improving (retires RichToken prose, replaces a stale --debug-ast=pretty sample), so this is a note rather than a bounce -- but it was not declared. Related: the RichToken cleanup is partial, leaving `docs/architecture/lexer_architecture.md:262` ("Token Parts: composite token support built-in (`RichToken`, also frozen)") and `docs/architecture/ast_data_flow.md:52,62` still naming the retired class.

```
git diff --stat origin/main...fix/remediation-2-5 lists docs/architecture/tour_of_psh_internals.md | 54 +++-. git grep RichToken on the branch still hits docs/architecture/lexer_architecture.md:262 and docs/architecture/ast_data_flow.md:52,62.
```

## NIT 9 [ledgerCheck] — 

ruff/mypy have no anchor at the final tip 6a70416e: the last recorded runs (ruff-final.txt, mypy-final.txt, ledger B28) are at the DISSOLVED tip 575291a1, and production changed afterward (ab6528d9 touched psh/io_redirect/file_redirect.py, psh/lexer/recognizers/operator.py, psh/parser/recursive_descent/parsers/redirections.py; f68449d7 touched psh/visitor/debug_ast_visitor.py). gate-6 is a two-phase pytest gate and does not run ruff/mypy. The B40 discharge audit simply omits the row, and this contradicts the slot's own B28-stated standard ('an anchor stamped at an earlier commit is stale by the same rule that produced R4-D'). Not a bounce because the underlying fact is true — I ran both at 6a70416e in the dev worktree: ruff 'All checks passed!', mypy 'Success: no issues found in 274 source files' (base count 274). Integrator should have the dev re-stamp the anchors.

```
git log --name-only 575291a1..6a70416e -- psh/ shows 4 production files changed after the last ruff/mypy anchors; tmp/gate-6.txt contains only Phase 1/Phase 1b pytest phases; my re-runs at 6a70416e both clean.
```

## NIT 10 [ledgerCheck] — 

The round-2 fix round has no per-file/per-commit test delta accounting: B12 (+918 at 063815ad) and B28 (+646 at 575291a1, 'derived and exactly reconciled') set the slot's own standard, but the +227 growth from 575291a1 to the final tip (23,369 -> 23,596 collected) is never decomposed in the ledger — B38 gives gate totals only and there is no collect anchor at 6a70416e (only collect-tip-575291a1.txt exists in tmp/r2-5-probes/). I reconciled it myself: tip collects 23,596 = base 22,723 + 873 = gate passed-delta (21,979 - 21,106) with skips (1,590) and xfails (10) unchanged; collection-id diff shows ZERO removed tests; the growth localizes to the expected round-2 files (equivalence corpus 551->731, test_named_fd_heredoc.py +16 new, test_heredoc_declared_deltas_noninteractive.py +12 new, PTY module 42->52, test_heredoc_executable_type.py 15->16, test_ast_coverage_matrix.py dispatch-guard rows). Numbers are sound; the ledger record is incomplete.

```
My full --collect-only at 6a70416e: 23,596; grep -c '::' on recorded collect-base.txt = 22,723 and collect-tip-575291a1.txt = 23,369; comm diff of sorted collection ids base vs tip: REMOVED-COUNT 0; per-file collects at tip: 16/12/52/93/16/42/731.
```

## NIT 11 [ledgerCheck] — 

B22 claims 'The brief's must-not-flip set, named and executed' but its named table omits one set the brief lists explicitly: 2.2's 82-param lockstep parity corpus (tests/parser_differential/test_input_contract_parity.py). It is covered implicitly by the green full gate at 6a70416e, and I ran it by name at tip: 82 passed. Also note B22 itself was executed at dfe68ed5, before the round-2 production commits — the final-tip coverage of the must-not-flip sets rests on gate-6 + compare-bash-4 rather than a by-name re-run; my by-name replays at tip (golden heredoc_nested_error_reports_absolute_line: 1 passed 1 skipped [the compare-bash-gated variant]; test_divergence_heredoc_body_cmdsub_stays_runtime: 1 passed; lockstep corpus: 82 passed) confirm nothing flipped.

```
grep of the slot ledger has no '82-param'/lockstep row in B22; my runs at 6a70416e: pytest tests/parser_differential/test_input_contract_parity.py -q -> 82 passed; golden and divergence pins pass by name.
```

## NIT 12 [reprobe] — 

Script-file channel of the declared-deltas pin is missing while ledger B34 claims 'pinned per channel AND per parser'. R7-B(2) required the non-interactive halves pinned per-channel; tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py parametrizes channel over ["dash_c", "stdin"] only, so the 4 script-file rows of the 12 declared identity deltas have no committed pin. Substantively covered — the identity instrument's script rows differ from its stdin rows only by the psh:/<SCRIPT>: message prefix (same buffered source path), stdin==bash IS pinned, and my live probes at tip show script==bash for both shapes on both parsers — but the B34 sentence overstates the committed pin's channel axis. Cure is one parametrize value (write the bytes to a temp file) or a scoped B34 sentence at ceremony.

```
Pin file :56 `@pytest.mark.parametrize("channel", ["dash_c", "stdin"])` with a docstring naming all three channels; tmp/r2-5-probes/base-tip-identity-6a70416e.txt script-vs-stdin rows identical modulo <SCRIPT> prefix. REPLAYED: pin at base e36116c3 = 10 failed / 2 passed (all 8 differential rows + both rd warning legs fail; both combinator warning legs pass exactly as the per-parser-honest docstring declares), at tip 6a70416e = 12 passed. Round-2 blocker-4/5 evidence already showed tip==bash on mode=file for both shapes.
```

## NIT 13 [reprobe] — 

The corrected census instrument's (C) mirror-detector still emits one mis-describing fixed label: it prints 'says it MIRRORS the heredoc scanner' for psh/io_redirect/process_sub.py and psh/parser/combinators/commands/redirections.py, but process_sub's comment mirrors 'the anonymous-temp-file pattern used for heredocs' (cleanup, not a grammar) and the combinator comment 'mirrors the recursive descent parser's _parse_heredoc' (parser symmetry, not a scanner copy) — so 'TOTAL DISTINCT SITES: 15' counts 2 non-grammar sites. Over-inclusion is the conservative direction for a census whose failure mode was under-enumeration, and each hit prints its match reason, but after the N7 'a census that invents particulars' lesson the fixed label is still a mild invented particular. The genuine mirror (history_expansion.py#_scan_line_markers_ctx) is correctly found and the round-2 :13 false particular is verified gone (input_preprocessing.py has no re.compile'd '<<' — only docstring prose at :26).

```
My re-run of tmp/r2-5-probes/second_grammar_census.py is byte-identical to second-grammar-census-6a70416e.txt (SHA header 6a70416e). Contexts read at tip: psh/io_redirect/process_sub.py:183-184; psh/parser/combinators/commands/redirections.py:58,72. Detector regex `[Mm]irrors?\b.{0,60}heredoc` with re.S at second_grammar_census.py:99.
```

## NIT 14 [reprobe] — 

B40's discharge audit has no ruff/mypy row stamped at the final tip: the newest committed-quality anchors (ruff-final.txt / mypy-final.txt, mtime 14:23) predate the five round-2 commits ab6528d9..6a70416e (15:16-15:49), which touched production files (lexer/recognizers/operator.py, io_redirect/manager.py, six visitors). I ran both at 6a70416e in a discriminator-verified worktree: ruff check psh tests tools -> 'All checks passed!'; mypy -> 'Success: no issues found in 274 source files' (base count 274). Substance clean; record gap only — the same B7-anchor class round-1 nit 11 flagged once already, so worth a fresh anchor at ceremony.

```
tmp/r2-5-probes/ruff-final.txt + mypy-final.txt mtimes 31 Jul 14:23 vs commit times ab6528d9 15:16:06 .. 6a70416e 15:49:18; my clean runs at the tip worktree (Position/TokenPart frozen=True confirmed live in the same interpreter).
```

## NIT 15 [reprobe] — 

Universe boundary of the base-identity oracle row, recorded so B42's table is read correctly: base_tip_identity.py's universe is the 22 inputs/*.in case files, which contain no named-fd {v}<< shape — the branch's largest behavior change (the R8-A improvement-beyond-base) is invisible to the 'nothing changed that was not declared' instrument and is instead covered by declaration (B33) plus bash-differential pins. The instrument's docstring states its universe honestly, and my independent widening found nothing: 9 novel shapes (exec {v}<<EOF + cat <&$v, {v}<<- with tab-indented body, {v}<<'Q', {v}<< EOF with space, the {v}<<$(x) named-fd x substitution-delimiter cross, 2<&- adjacency, heredoc-after-| continuation, escaped \<< and true-heredoc controls) x 3 channels x 2 parsers x {base, tip, bash}: every base->tip delta was the declared named-fd family (base rc=2 'Expected file name' on ALL named-fd rows — confirming R8-A's base-parse-error evidence), zero undeclared deltas, tip==bash byte-identical (modulo program-name prefix) on every row.

```
ls tmp/r2-5-probes/inputs/ = 22 files, none containing '{v}'; my ni_probe3.py run (individual-run, od-verified script bytes, cwd-pinned PYTHONPATH discriminators): exec_named_use/named_dash_tab/named_quoted/named_space/named_subst_delim each 6/6 base->tip deltas all rc=2 'Expected file name' at base and tip==bash 0 mismatches; close_fd_adj/heredoc_pipe/escaped_control/true_control 0 deltas. Independent identity re-run: rows=132 identical=114 differ=18, DELTA rows byte-identical to the dev anchor (diff clean).
```

## NIT 16 [reprobe] — 

INFO — clean-replay record (no defect; recorded so the integrator need not re-derive). ALL round-3 attack priorities reproduced at 6a70416e: (1) NAMED-FD CLOSURE: round-2 blocker-1's exact PTY sequence (true {v}<<EOF / body / EOF / echo MARK""ER) -> PS2,PS2,PS1,PS1 + MARKER on rd AND combinator == bash 5.2.26; mutation removing ('<<', HEREDOC) from _try_var_fd_redirect -> EXACTLY 8 PTY + 12 non-interactive pin failures as declared (both entries removed -> 10 + 14); restored -> 68 passed; fd pin asserts semantics (>=10 + same-host bash differential), NO ==10 literal anywhere. (2) IDENTITY: header line states base-vs-tip identity; 132/114/18 reproduced; all 18 map to the declared set (12 = two declared shapes, 6 = B20 unclosed-$( delta); no 19th found. (3) RED-ON-BASE: declared-deltas pin 10F/2P at base (combinator warning legs = documented per-parser control) / 12P at tip; named-fd pin 14F/2P at base / 16P at tip. (4) VISITOR GUARD: per-visitor alias-removal -> matrix red with the dev's exact counts (security 1, validator 1, metrics 2, debug 1, linter 1, formatter 2), restored 93P; all 7 comment sites true; validator NOTE-orphaning fixed; builtin-stream arm mutation -> committed offender test bites (1F/15P), restored green. (5) R7-D: deleting {v}<< from the live axis list -> exactly TWO guards red (bounced-row + axis-varied), restored green; census replay identical, :13 particular gone. (6) TYPED RUNNER: resolve_bash at import in both new differential modules, run_psh pins PYTHONPATH to the tree under test, is_comparable asserted before every comparison; spawn ratchet 41P and oracle-resolution ratchet 15P at tip; PTY_REGISTRY + _EXPECTED_PTY_SITES additions are the full two-place edit with owner=slot2.5 + scoped reason, load-bearing; test_bash_oracle_resolution.py untouched vs base. (7) DELTA: collection-id diff 22,723 -> 23,596 = +873 added / 0 removed, per-file counts identical to B42 (731/52/24/16/16/12/8/4/4/3/2/1); +227 vs round-2's +646 = equivalence +180, PTY +10, named-fd +16, executable-type +1, declared-deltas +12, coverage-matrix +8. (8) RECORDS: all five final anchors self-stamp 6a70416e with mtimes 15:58-16:01 AFTER the 15:49:18 tip commit; 6 STRUCK rows preserved with strike-not-erase pointers (B6->B17, B14->B21, B27, B30->B36); 8 discharge rows spot-replayed; three docstrings (PTY module, conftest allowlist, PTY_REGISTRY) verified scoped to the escaped spelling with pointers to the non-interactive pins. (9) MUST-NOT-FLIP BY NAME: golden heredoc_nested_error_reports_absolute_line exit_code 127 in yaml, 1P; test_divergence_heredoc_body_cmdsub_stays_runtime 1P; 2.2 lockstep corpus 82P; 2.1 totality battery + walk-schema 100P + schema guard 94P; C1 both-backend arms 58P; integration named-fd 17P (R8-A cond. 4); tests/behavioral, tests/conformance, FLIP-PINS.md, golden_cases.yaml absent from the 43-file diff; forbidden and parallel-session never-touch files absent. (10) FRESH PTY SPOT ROWS: cat 0<<EOF, escaped \<<EOF, multi-line true heredoc, {v}<<EOF full sequence (plus exec-use, <<-, quoted-delimiter) — psh rd and combinator == bash 5.2.26 on every prompt sequence and output. Gate/compare-bash anchors read at tip: 21,979/1,590/10 and 2,986/26 EXACT (not re-run — one-heavy-run-machine-wide rule; targeted suites replayed instead). Housekeeping: both throwaway worktrees removed; zero probe orphans (the long-lived /Library/.../bin/psh processes are the user's 7-10-day-old installed sessions, untouched); a stray out.txt in my tip worktree was proven an artifact of my own mutation runs, not of the branch.

```
Final SHA 6a70416e242100d6cd84af879152e3566a3688b7; base e36116c30d12d1305f163fd6d8eaada8d72b1116; oracle /opt/homebrew/bin/bash GNU bash 5.2.26(1)-release aarch64-apple-darwin23.2.0; probe scripts + outputs preserved at /private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/{pty_probe3.py,ni_probe3.py,identity-replay.txt,census-replay.txt,collect-base-clean.txt,collect-tip.txt,added2.txt}.
```
