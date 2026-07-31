# VERIFY-ROUND1 — slot 2.5, tip 063815ad, verdict BOUNCE (5 blockers, 16 nits)

Full machine-readable copy: VERIFY-ROUND1-issues.json (same directory).

## BLOCKER 1 [diffAudit] — Value graph not fully frozen: TokenPart.start_pos/end_pos writable

MEDIUM-10b is NOT closed as claimed: the lexical value graph reachable from a real LexedUnit is still writable, and three production doc sites assert the opposite. `TokenPart.start_pos` / `TokenPart.end_pos` are `psh/lexer/position.py#Position` — a plain `@dataclass` (NOT frozen) — so a caller can still rewrite a lexed value after the lexer returned it. This is the IDENTICAL shape MEDIUM-10b named (container frozen, contents mutable), reproduced one level down: v0.681 froze `Token` and left `parts` mutable; 2.5 freezes `parts`/`TokenPart` and leaves the `Position` values mutable. The dev's guard `tests/unit/lexer/test_lexical_value_graph_frozen.py` enumerates `dataclasses.fields(TokenPart)` but only asserts that REBINDING an attribute raises `FrozenInstanceError`; it never asserts that a field's VALUE is immutable, so its universe is 'TokenPart attribute rebinding', not 'every edge in the value graph' as the brief requires ('a census instrument whose universe is the CLASS ... every container edge in the value graph'). The over-claims that a 3-line probe refutes: psh/lexer/CLAUDE.md:238 '**Every edge of the graph reachable from a `LexedUnit` is now immutable**'; psh/lexer/token_parts.py:24 'Every edge of that graph is now immutable, enforced over the CLASS — every field, every container edge, discovered at runtime rather than hand-listed'; psh/lexer/token_types.py:114 'The freeze reaches the WHOLE value graph'. Fix = freeze `Position` (or an equivalent value-graph-transitive census that the guard actually runs), or narrow all three claims to what is enforced.

### Evidence
```
REPLAYED at tip 063815ad (/private/tmp/remv-tip-2500, discriminator psh.__file__=/private/tmp/remv-tip-2500/psh/__init__.py, version 0.760.0):

  u = HeredocLexer('echo "a$b"c', warn_unterminated=False).tokenize_with_heredocs()
  tok = next(t for t in u.tokens if t.parts); p = tok.parts[0]
  p.start_pos.offset = 999; p.start_pos.line = 42
  -> 'MUTATED nested Position OK -> line 42, column 0'
  re-read through the unit: 'line 42, column 0'   (the write is visible on the stored value)

Transitive census over the live graph (universe = every object reachable from LexedUnit.tokens/.heredocs, flagging non-frozen dataclasses), source 'echo "a$b"c $(x) ${y:-d} <<E\nbody\nE\n':
  MUTABLE NODE CLASSES: {'Position': 4}
    Position unit.tokens[1].parts[0].start_pos
    Position unit.tokens[1].parts[0].end_pos
    Position unit.tokens[1].parts[1].start_pos
    Position unit.tokens[1].parts[1].end_pos

Same probe at base e36116c3 (/private/tmp/remv-base-2500): 'base: nested Position writable -> 999' — i.e. the residue is pre-existing and simply NOT closed, while the docs say it is.

psh/lexer/position.py:17-22:  @dataclass\nclass Position:  (no frozen=True)
```

## BLOCKER 2 [diffAudit] — 2 undeclared/unpinned interactive behavior flips (delimiter, quote)

TWO user-observable INTERACTIVE behavior changes ship undeclared and unpinned. Brief §7 is explicit: 'Any behavior delta beyond the chartered fix: probed vs live bash, both parsers, versions recorded, DECLARED + PINNED (an unpinned improvement is still a bounce).' Both deltas are improvements (tip == bash where base diverged), which is exactly the case the rule names. Neither appears in the ledger (grep of tmp/remediation-ledgers/2.5.md for 'unclosed'/'$(x)'/'delimiter substitution' finds nothing; B0/B6/B12 declare no behavior delta beyond `\<<`), and neither axis exists in either new corpus. (1) SUBSTITUTION-BEARING HEREDOC DELIMITER: `cat <<$(x)` — base cooks the delimiter to `$` (regex scanner stops at `(`), tip cooks it to `$(x)` (lexer spec). This changes WHICH physical line terminates the here-document interactively. The new property test's delimiter axis is `_DELIMITERS = ["EOF", "'EOF'", '\"EOF\"', r"\\EOF", 'E\"O\"F']` — quoting only, no substitution — so the row that would have been RED ON BASE is absent. (2) HEREDOC + UNCLOSED QUOTE ON ONE LINE: moving the heredoc decision after the lex (session.py step 2/3, gated on `if unit is not None`) makes the unclosed-quote outcome win over the heredoc outcome. `cat <<EOF "abc` / `EOF` / `def"` executes at line 3 on base but stays incomplete on tip (= bash). The equivalence corpus cannot express this axis at all (its helper `_lexer_says_pending` would raise), and the PTY corpus has no unclosed-quote row.

### Evidence
```
ORACLE: PATH bash 5.2.26(1)-release aarch64-apple-darwin23.2.0 (/opt/homebrew/bin/bash). BASE e36116c3, TIP 063815ad. Instrument A = real-PTY probe (pexpect, TERM=dumb, PS1='P1> ' PS2='P2> ', sync'd with `echo REA""DY`), recording PS1/PS2 after EACH physical line. Rows are NEW (not in the dev's suite).

row                                bash            psh BASE            psh TIP (rd AND combinator)
'cat <<$(x)','hi','$'              PS2,PS2,PS2     PS2,PS2,**PS1**     PS2,PS2,PS2   (=bash)
'cat <<$(x)','hi','$(x)'           PS2,PS2,PS1     PS2,PS2,**PS2**     PS2,PS2,PS1   (=bash)
'cat <<EOF "abc','EOF','def"'      PS2,PS2,PS2     PS2,PS2,**PS1**     PS2,PS2,PS2   (=bash)
controls that did NOT move: 'cat <<${V}'/'`x`'/'$V' delimiters, 'cat <<EOF "abc','def"','body','EOF', 'cat <<EOF )', 'cat <<EOF $(', 'cat <<EOF ((', 'cat <<EOF; echo "x', 'cat <<E"O"F', 'cat <<\\EOF' — bash == base == tip on all of them (no regression found).

Instrument B (structural, agrees with A) — CommandAccumulator traces:
  base: 'cat <<$(x)' -> HEREDOC detail '$'    ; seq ['cat <<$(x)','hi','$']    -> Complete
  tip : 'cat <<$(x)' -> HEREDOC detail '$(x)' ; seq ['cat <<$(x)','hi','$(x)'] -> Complete
  base: 'cat <<EOF "abc' -> HEREDOC 'EOF' ; tip -> UNCLOSED_QUOTE '\"'

Instrument C — the dev's OWN equivalence helpers run at BASE prove the missing row would have been red-on-base:
  'cat <<$(x)'  lexer=('$(x)',)  session=('$',)  **DISAGREE**
  'cat <<`x`' / 'cat <<$V' / 'cat <<${V}'  AGREE

Grep for any existing pin on these shapes across tests/ ('<<$(', '<<`', '<<${'): none.
```

## BLOCKER 3 [ledgerCheck] — 

False/under-enumerated census claim with no recorded enumeration command: ledger B0/D1 claims 'Two regex-scanner consumers remain OUTSIDE the session path' (psh/scripting/input_preprocessing.py:115, psh/interactive/line_editor_helpers.py:61,75,96) and the R1-B ruling plus the STILL-OPEN boundary row were built on that census. A third regex-grammar consumer exists: psh/interactive/history_expansion.py imports HEREDOC_MARKER_RE (:16) and runs a mirror scanner _scan_line_markers_ctx (:147, docstring 'Mirrors heredoc_detection.scan_line_heredoc_markers'), consumed via expand_history:333 -> heredoc_body_spans -- which is invoked from command_accumulator._preprocess, i.e. ON the interactive session path (feed step 1). The mirror still misdetects the MEDIUM-3 spelling at tip: _scan_line_markers_ctx('echo \<<EOF', [], 0) returns spec 'EOF' (live probe in dev worktree, tree version 0.760.0). File is base-identical (no regression) and it decides history-suppression, not completeness, but the census as recorded is false at the grammar level, no enumeration command/output backs it in the ledger, and the boundary row the integrator ruled on under-states the remaining second-grammar surface. The B0 bounding argument (66/66 non-interactive parity) cannot bound this consumer -- history expansion is interactive-only.

### Evidence
```
git grep HEREDOC_MARKER_RE fix/remediation-2-5 -- psh/ -> history_expansion.py:16,147 (plus utils). expand_history at history_expansion.py:294 calls heredoc_body_spans at :333. detects_history_reference/_preprocess wiring at psh/scripting/command_accumulator.py:205-233. Live probe output: 'echo \<<EOF' -> mirror specs: ['EOF'].
```

## BLOCKER 4 [ledgerCheck] — 

Record-integrity: the two 'tip' evidence anchors were produced BEFORE any branch commit and are self-stamped with the BASE SHA, contradicting the ledger. pty-matrix-tip.txt (mtime 12:11, header '# SHA: e36116c3...') and noninteractive-tip.txt (11:57, same base-SHA header) predate the first commit a274338c (12:18:12) -- they measured uncommitted working-tree code, yet B14 asserts 'Every row below was re-checked at the FINAL TIP 063815ad'. Additionally B6 claims '42 rows (14 cases x {bash, psh-rd, psh-combinator})' while the anchor contains 48 RESULT rows across 16 cases (11 base + 3 posix + 2 nested = 16, not 14), and the B14 discharge audit reports 'Rows audited: 22. Discrepancies found: 0' -- a false audit result. Substance is independently safe: the committed 32-test PTY pin and compare-bash ran inside gate-2 (12:42) and compare-bash-1 (12:44), both AFTER the final tip 063815ad (12:33:36), and I replayed the session-level red->green flip at base (psh-install @ e36116c3) vs tip. But the discharge audit is an acceptance condition and it contains claims its own anchors contradict; the tip matrix should be re-run at 063815ad and B6/B14 corrected.

### Evidence
```
run_pty_matrix.sh stamps git rev-parse HEAD; file mtimes vs git log --format='%h %ci' (first commit 12:18:12); grep -c '^RESULT' pty-matrix-tip.txt = 48; awk case enumeration = 16 distinct cases; gate-2.txt mtime 12:42 with '22024 passed, 1590 skipped, 10 xfailed'; compare-bash-1.txt 12:44 with '2986 passed, 26 skipped'.
```

## BLOCKER 5 [ledgerCheck] — 

Brief item silently dropped: the brief's PTY-pin spelling axis explicitly enumerates adjacent operators as '<<<, <<-, <&, digit-prefixed fds', but '<&' appears NOWHERE -- not in the 16-case PTY corpus (case list enumerated from the tip matrix and the committed test), not in the equivalence corpus (_OPERATORS = ['<<', '\\<<', '<\\<', '\\\\<<', '<<-', '<<<', '0<<']), and not in the ledger's axis lists (A3 spelling-axis paragraph, equivalence-test GENERATED DOMAIN docstring). The omission is never declared, unlike the Phase A option/nested-axis gaps which were declared and later closed under R1-E. One corpus row (e.g. 'cat <&0'-family adjacency) or an explicit declared-omission line would cure it.

### Evidence
```
git grep '<&' fix/remediation-2-5 -- tests/system/interactive/test_heredoc_detection_interactive_pty.py tests/unit/parser/test_session_lexer_heredoc_equivalence.py -> no matches; brief 'Pins YOU create' bullet lists '<&' explicitly; ledger A3/B6 axis lists omit it without declaration.
```

## NIT 1 [diffAudit] — expansion/procsub_render.py touched, undeclared in ledger scope audit

Out-of-scope production file touched without the brief's STOP-and-report: `psh/expansion/procsub_render.py`. The brief's Rules/Scope paragraph names `expansion` in the STOP-and-report list, and the ledger's B8 diff-scope audit only checks that FORBIDDEN files are absent — it never declares this file. The change itself is forced by Shape A (the base line `node.heredoc_content is not None` would AttributeError on every non-heredoc Redirect once the field moved) and is behavior-neutral (`isinstance(node, HeredocRedirect)` is true exactly where `heredoc_content is not None` was), so this is a declaration gap rather than a semantic one. The six visitor aliases are covered by ruling R2-A ('visit_* methods needed: 6'), and io_redirect/manager.py by R3-A/C1; this file is covered by neither.

```
git diff origin/main...fix/remediation-2-5 -- psh/expansion/procsub_render.py
  -    if node.heredoc_content is not None or node.move or node.combined:
  +    if isinstance(node, HeredocRedirect) or node.move or node.combined:

grep -n 'procsub_render|expansion/' tmp/remediation-ledgers/2.5.md -> no matches (ledger B4/C3 disposition tables cover test files and the six visitors only).
```

## NIT 2 [diffAudit] — Alias inserted mid-method, orphaning an indented NOTE comment

`visit_HeredocRedirect = visit_Redirect` was inserted INSIDE `ValidatorVisitor.visit_Redirect`'s body region, orphaning the trailing 8-space-indented `# NOTE:` block that documented the removed '>|' advisory. The file still parses (comments are invisible to the INDENT/DEDENT tokenizer) and ruff is clean, but the result reads as a comment block indented under a class-level assignment and the NOTE no longer attaches to any method. Move the alias below the orphaned comment.

```
psh/visitor/validator_visitor.py (tip):
    def visit_Redirect(self, node: Redirect) -> None:
        ...
            )

    # Executable heredocs are a SUBCLASS ...
    visit_HeredocRedirect = visit_Redirect

        # NOTE: a "consider '>|' or '>>'" advisory used to fire on EVERY `>`
        # whose target was not /dev/null. ...

    def visit_EnhancedTestStatement(...)
```

## NIT 3 [diffAudit] — Vacuous/dead rows in three new or changed tests

Three weak rows in the new/changed tests. (a) `test_heredoc_body_line_costs_no_lex` parametrizes n in [50,100,200] but compares against `_feed_heredoc_body(Shell(), 50)`, so the n=50 row asserts a value against itself (vacuous). (b) `test_the_typed_error_is_the_strict_errors_loud_class` contains a dead one-element loop `for expected_class in (Exception,)`. (c) `test_every_container_edge_rejects_a_write` accepts `AttributeError` in its raises-tuple, so a typo'd attribute name in a future edge row would still pass as 'rejected'.

```
tests/unit/parser/test_session_linearity_i3.py: `assert ops.lex_calls == _feed_heredoc_body(Shell(), 50).lex_calls` under `@pytest.mark.parametrize("n", [50, 100, 200])`.
tests/unit/io_redirect/test_heredoc_executable_type.py: `for expected_class in (Exception,): assert issubclass(...)`.
tests/unit/lexer/test_lexical_value_graph_frozen.py: `pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError))`.
```

## NIT 4 [diffAudit] — Equivalence corpus's posix axis unused on the lexer/oracle side

The equivalence property test's OPTION-STATE axis is not varied on the oracle side: `_lexer_says_pending(line, posix)` accepts `posix` and ignores it (it always builds `HeredocLexer(line, config=None, ...)`), while the module docstring's domain statement says 'OPTION STATE: default and posix (the session lexes with the shell's live option dict, so the option axis is a real input to the grammar)'. The assertion is still conservative (a posix-dependent session answer would fail against the default-option lexer answer), so it is not wrong — but the corpus does not exercise the axis its own domain statement quantifies over, which is the AXIS-QUANTIFICATION rule's shape.

```
tests/unit/parser/test_session_lexer_heredoc_equivalence.py:
  def _lexer_says_pending(line, posix):
      unit = HeredocLexer(line, config=None, warn_unterminated=False).tokenize_with_heredocs()
  # `posix` unused in the body.
```

## NIT 5 [resurrection] — 

Dangling reference to the deleted `Redirect.heredoc_content` field in a LIVE architecture doc: ARCHITECTURE.md:1052 carries a code sketch of `redirect_heredoc` reading `content = redirect.heredoc_content or ''` and `getattr(redirect, 'heredoc_quoted', False)`. The attribute no longer exists on `Redirect`. NOT the dev's to fix — ARCHITECTURE.md is on the brief's NEVER-TOUCH list — so this is an INTEGRATOR action at ceremony. Held to NIT rather than BLOCKER because the sketch was already drifted at base (base code was `content = redirect.heredoc_content` + `if content is None: raise`, i.e. neither `or ''` nor the getattr matched), so the diff makes pre-existing rot worse rather than creating it. Recommend the integrator replace the sketch with invariant prose + a `file.py#symbol` pointer per the project's own no-sketch rule.

```
git show fix/remediation-2-5:ARCHITECTURE.md | sed -n '1049,1056p' ->
```python
def redirect_heredoc(self, redirect):
    """Point stdin at the heredoc content. Returns the expanded content."""
    content = redirect.heredoc_content or ''
    if content and not getattr(redirect, 'heredoc_quoted', False):
```
vs branch psh/io_redirect/file_redirect.py:371-382 `def redirect_heredoc(self, redirect: 'HeredocRedirect')` / `content = redirect.heredoc_content` / `if content and not redirect.heredoc_quoted:`. Field-deletion proof: `dataclasses.fields(Redirect)` no longer contains `heredoc_content` (pinned by the branch's own tests/unit/io_redirect/test_heredoc_executable_type.py:57).
```

## NIT 6 [resurrection] — 

Dangling reference in docs/architecture/tour_of_psh_internals.md:253 — the doc prints, as the claimed output of `python -m psh --debug-ast=pretty -c 'echo "Hello, $USER" | wc -c > out.txt'`, a repr `Redirect(type='>', target='out.txt', fd=None, dup_fd=None, heredoc_content=None, quote_type=None, heredoc_quoted=False, combined=False)`. `heredoc_content` is now gone from `Redirect`. This file IS in the dev's scope (docs/architecture is not on the never-touch list) and three subsystem CLAUDE.md files were updated in the same diff, so the miss is a real gap. Held to NIT because I REPLAYED the command at BOTH SHAs and the snippet was already fictional at base — `--debug-ast=pretty` prints an indented tree, never a dataclass repr — so this is pre-existing drift the diff worsens by one token, not drift the diff created. (The same paragraph also still says 'the RichToken's parts', retired long ago.)

```
REPLAY at base e36116c3: `python -m psh --debug-ast=pretty -c 'echo "Hello, $USER" | wc -c > out.txt' | grep -i redirect` -> `redirects: [` / `Redirect:` (tree form, no repr, no heredoc_content). REPLAY at tip 063815ad: same tree form. Neither matches the doc's repr line. Doc line: docs/architecture/tour_of_psh_internals.md:253.
```

## NIT 7 [resurrection] — 

Class-name-keyed registry not extended for the new node class: psh/parser/visualization/dot_generator.py:47 `type_colors` has a `'Redirect': '#FFF8E1'` row but no `'HeredocRedirect'` row, so executable heredoc redirects now render with the unknown-node fallback grey `#F0F0F0` in `--debug-ast=dot`. Cosmetic and unpinned (the visualization_corpus goldens contain no heredoc, which is why nothing went red), but it is exactly the exact-class-name registry class the dev correctly handled in visitor/traversal.py#AstChildSchema and the six visitors — this one was missed.

```
REPLAY at tip in a detached worktree, heredoc probe file (od -c verified: `cat <<EOF\nbody\nEOF\n`):
`python -m psh --debug-ast=dot probe.sh | grep -i redirect` ->
`    node5 [label="HeredocRedirect", shape=box, style=filled, fillcolor="#F0F0F0"];`
vs base e36116c3 -> `node5 [label="Redirect", ..., fillcolor="#FFF8E1"];`. Source: psh/parser/visualization/dot_generator.py:47 (map) and :63 (`self.type_colors.get(node_type, '#F0F0F0')`).
```

## NIT 8 [resurrection] — 

Unpinned user-visible output delta of a documented debug flag, surfaced during the hunt (flagging so it is not an undeclared delta): all five `--debug-ast` formats (tree, compact, pretty, sexp, dot) now label an executable here-document redirect `HeredocRedirect` where base printed `Redirect`. This is an inherent consequence of the chartered MEDIUM-10a type split, not a defect, but I found no pin asserting the new label — the visualization_corpus goldens contain no heredoc, so nothing in the suite would catch a future regression of the label. Integrator should confirm the ledger DECLARES it.

```
A/B REPLAY, same od -c-verified probe file `cat <<EOF\nbody\nEOF\n`, both worktrees:
base e36116c3 `--debug-ast`      -> `└── Redirect`
tip  063815ad `--debug-ast`      -> `└── HeredocRedirect`
tip `--debug-ast=sexp`           -> `:redirects (HeredocRedirect`
tip `--debug-ast=pretty`         -> `HeredocRedirect:`
tip `--debug-ast=dot`            -> `label="HeredocRedirect"`
No grep hit for `HeredocRedirect` in tests/unit/parser/visualization_corpus/.
```

## NIT 9 [resurrection] — 

Comment-orphaning at the alias insertion point: in psh/visitor/validator_visitor.py the `visit_HeredocRedirect = visit_Redirect` alias (line 460) was inserted BETWEEN `visit_Redirect`'s body and the multi-line trailing NOTE that documents `visit_Redirect` (the reappraisal-#19-T10 dropped `>|` advisory). The NOTE now sits at 8-space method-body indentation after a class-level statement, reading as documentation of the alias. Syntactically legal (comments emit no INDENT) and ruff+mypy are clean, but in an educational codebase it misattributes the history. The other five visitors placed the alias cleanly. Suggest moving the alias below the NOTE block.

```
git show fix/remediation-2-5:psh/visitor/validator_visitor.py | sed -n '446,466p' ->
```
    def visit_Redirect(self, node: Redirect) -> None:
        ...
    # Executable heredocs are a SUBCLASS ...
    visit_HeredocRedirect = visit_Redirect

        # NOTE: a "consider '>|' or '>>'" advisory used to fire on EVERY `>`
        # whose target was not /dev/null. ... dropped in reappraisal #19 T10.

    def visit_EnhancedTestStatement(...)
```
```

## NIT 10 [ledgerCheck] — 

Ledger A1 states the probe instruments are 'all committed under tmp/r2-5-probes/' -- they are NOT committed: tmp/ is gitignored (git check-ignore confirms) and no tmp/ path appears in the branch diff; the instruments exist only as untracked worktree files. The discharge-audit rule accepts transcript paths, so the anchors function, but the word 'committed' is false and the evidence will not survive worktree removal unless the integrator rescues it at ceremony (as the brief provides for the ledger itself).

```
git -C /Users/pwilson/src/psh-r2-5 check-ignore tmp/r2-5-probes/pty_probe.py -> IGNORED; git diff --name-status origin/main fix/remediation-2-5 contains no tmp/ paths.
```

## NIT 11 [ledgerCheck] — 

B7 (scoped tip verification: ruff, mypy, 4,516 scoped tests) is absent from the B14 discharge-audit table and its ruff/mypy claims carry no anchor files. I replayed both at the dev worktree tip: ruff check psh tests tools -> 'All checks passed!'; mypy -> 'Success: no issues found in 274 source files' (matches the base count 274). Claims true; audit-row and anchors missing.

```
B14 table rows list A1-A8, B1, B4, B5, B6, B8-B13 -- no B7 row; my replay outputs above.
```

## NIT 12 [ledgerCheck] — 

No explicit must-not-flip verification row in the slot ledger (the brief names golden heredoc rows incl. heredoc_nested_error_reports_absolute_line, the 2.3/2.4 timing/divergence pins, 2.2's lockstep corpus, 2.1's sentinel battery). Coverage is real but implicit: tests/behavioral and tests/conformance are untouched on the branch (verified via git diff --name-only), the timing pin file test_nested_substitution_timing_conformance.py is present and unmodified, and gate-2 + compare-bash (2,986/26, composition identical to base) ran after the final tip. The 2.1 battery's +1 sentinel row is declared and accounted in B12. An explicit row naming the must-not-flip set would close the gap.

```
git diff --name-only origin/main fix/remediation-2-5 -- tests/behavioral tests/conformance -> empty; compare-bash-1.txt totals identical to base figures in the brief.
```

## NIT 13 [reprobe] — 

Ledger B6 (echoed in discharge-audit row B14) states the tip PTY matrix anchor is '42 rows (14 cases x {bash, psh-rd, psh-combinator})', but the anchor tmp/r2-5-probes/pty-matrix-tip.txt actually contains 48 RESULT rows over 16 cases (including the two nested_cmdsub cases B6 itself describes). Stale hand-carried count, contrary to the counts-are-DERIVED rule. Error is in the conservative direction: coverage exceeds the claim and I replayed zero divergence across all 16 cases.

```
grep -c '^RESULT' pty-matrix-tip.txt = 48; 16 distinct case names incl. nested_cmdsub_heredoc/nested_cmdsub_escaped/posix_*; my per-case agreement check: cases=16, divergent=0. Ledger 2.5.md B6: '42 rows (14 cases...)'.
```

## NIT 14 [reprobe] — 

Frozen-graph census gap (inert): TokenPart.start_pos/end_pos hold MUTABLE Position objects (psh/lexer/position.py Position is an unfrozen dataclass), so part.start_pos.offset = 99999 succeeds on a real lexed value — a nested-object edge the runtime field census (setattr-based) cannot see. Inert today: grep shows no production reader of TokenPart.start_pos/end_pos (only history_nav's unrelated int attr), so behavior cannot be poisoned. Token.array_init (typed Any, never populated by the lexer) is the same class of future risk. Worth a successor note / Position freeze.

```
At tip 063815ad: Position frozen? False; ATTACK part.start_pos.offset: WRITABLE Position(offset=6,...) -> Position(offset=99999,...). grep -rn '.start_pos' psh/ finds no TokenPart.start_pos consumer outside construction.
```

## NIT 15 [reprobe] — 

The STILL-OPEN boundary row (ledger B0) under-enumerates remaining heredoc_detection scanner-family consumers: besides the two R1-B sites, psh/interactive/history_expansion.py:175 calls contains_heredoc and maintains a LOCAL mirror of scan_line_heredoc_markers (history-expansion quoting context, outside the session completeness path), and psh/scripting/lex_parse.py:110 uses contains_heredoc as the plain-vs-heredoc-aware lex gate (safe: documented one-directional substring over-approximation, '<<' in s). Also has_unclosed_heredoc is now export-only dead (zero callers). None affects the one-grammar charter — session.py has zero live scanner calls — but the boundary enumeration should name them.

```
grep at tip: session.py imports only HeredocTermination; open_heredoc_specs/scan_line_heredoc_markers live callers = input_preprocessing.py:115 + line_editor_helpers.py:61,75,96 only; contains_heredoc extra callers = lex_parse.py:110, history_expansion.py:175; has_unclosed_heredoc callers = none outside utils/__init__ export.
```

## NIT 16 [reprobe] — 

Cosmetic: in tests/unit/visitor/test_analysis_visitors.py::test_quoted_heredoc_body_not_expanded the continuation line 'heredoc_quoted=True)' kept the old Redirect-call indentation after the rename to HeredocRedirect (misaligned with the other kwargs). ruff-clean, purely cosmetic.

```
Branch diff hunk shows heredoc_quoted=True) left at the previous indent depth while the two lines above were re-indented for HeredocRedirect(.
```
