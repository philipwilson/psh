# VERIFY-ROUND9 — slot 2.5, tip 6965a079, verdict **PASS** (0 blockers, 11 nits)

Full machine-readable copy: VERIFY-ROUND9-issues.json (same directory).

## NIT 1 [diffAudit] — 

UNRULED SCOPE GROWTH (doc-only): docs/architecture/tour_of_psh_internals.md goes well beyond the change this slot forces. Only ONE line in that file was made false by the branch (the `Redirect(type='>', ..., heredoc_content=None, ...)` repr). The dev instead replaced the ENTIRE `--debug-ast=pretty` example with a 30-line indented-tree rendering and made four further unrelated edits (RichToken->Token in three places, and the Quick-Reference table row 'lexer internals (recognizers, quotes, RichToken)' -> 'token parts'). Those corrected staleness that PRE-EXISTS at origin/main: `=== AST Debug Output` is already emitted by psh/utils/ast_debug.py:20 on origin/main, and RichToken was retired long before this slot. So this is drive-by documentation work outside the slot charter (brief required-work item 6 covers subsystem CLAUDE.md, not docs/architecture/), and it is not covered by any ruling in INTEGRATOR-INBOX.md (greps for 'tour_of_psh', 'debug-ast', 'architecture/' return nothing). Zero behaviour risk, but it belongs in the DECLARATION SCOPE record. I also did NOT execute the new example block — it is plausible from ast_debug.py (ASTPrettyPrinter, show_positions=True) and `shell.py:271 self._active_parser = 'recursive_descent'` matches the header line, but its accuracy is unverified by me.

```
git show origin/main:psh/utils/ast_debug.py | sed -n '20p'  ->  print(f"=== AST Debug Output ({parser_name}) ===", file=sys.stderr)   [i.e. the OLD doc text was already stale at BASE]

diff hunk (docs/architecture/tour_of_psh_internals.md):
-SimpleCommand(args=['echo', 'Hello, $USER'], ...,
-  words=[Word(parts=[LiteralPart(text='echo', ...)], quote_type=None), ...
+=== AST Debug Output (recursive_descent) ===
+Program:
+  statements: [
+    AndOrList @line1:
...
-| lexer internals (recognizers, quotes, RichToken) | `psh/lexer/CLAUDE.md` |
+| lexer internals (recognizers, quotes, token parts) | `psh/lexer/CLAUDE.md` |
```

## NIT 2 [diffAudit] — 

RULING-COLLISION FILE IS TOUCHED (already adjudicated — recording it so the ceremony record is complete, not as a bounce). R1-B ordered: 'Your diff must not touch either file — the diff audit will check', naming psh/interactive/line_editor_helpers.py. The diff DOES touch it. R15-C then adjudicated the collision ('R14-B N10 supersedes R1-B for that docstring hunk ONLY; the dev followed the later ruling correctly'). I verified the touch is confined to the MODULE DOCSTRING: two hunks, both above the `from typing import List, Optional, Tuple` line; the three call sites R1-B fenced (lines 61/75/96 — open_heredoc_specs users) are byte-identical, and psh/scripting/input_preprocessing.py is entirely untouched. So the ruling's INTENT is honoured. Flagging only because the audit R1-B invoked is this one, and a reader of the diff alone would score it a violation.

```
git diff origin/main...fix/remediation-2-5 -- psh/interactive/line_editor_helpers.py  ->  2 hunks, @@ -4,8 +4,8 @@ and @@ -19,6 +19,16 @@, both inside the docstring; +12/-2 lines; last added line is '...closing it is a successor's job.' immediately preceding '"""'.
INTEGRATOR-INBOX.md:1112  'R1-B ordered "diff must not touch line_editor_helpers.py"; my R14-B N10 later ordered a docstring fix in that file and I never reconciled the two. ADJUDICATED: R14-B N10 supersedes R1-B for that docstring hunk ONLY'
```

## NIT 3 [diffAudit] — 

THREE NEW DIVERGENCE PINS ARE CREATED BY THIS SLOT AND FLIP-PINS.md CANNOT RECORD THEM (correctly — the dev is forbidden to touch it). The integrator must add the successor rows at ceremony, or the campaign's flip-pin inventory silently under-reports. All three are named to the campaign's enumeration convention (`def test_divergence_`), so the A3 grep will find them. The alias family in particular is asserted in psh/io_redirect/CLAUDE.md as a 'DECLARED DIVERGENCE with a successor row' — that row does not exist in any committed doc on this branch.

```
git diff origin/main...fix/remediation-2-5 | grep '^+.*def test_divergence' ->
+def test_divergence_plain_and_digit_degenerate_forms(line, parser, ...)      [test_heredoc_detection_interactive_pty.py]
+def test_divergence_null_command_named_fd_keeps_the_descriptor(label, script, ...) [test_named_fd_heredoc.py]
+def test_divergence_alias_heredoc_body_is_not_collected(label, script, parser)     [test_heredoc_alias_route.py]
FLIP-PINS.md at origin/main: no 2.5 rows in any section (must-flip / successor-owned / must-NOT-flip).
```

## NIT 4 [diffAudit] — 

REDUNDANT DOUBLE-FREEZE at two construction sites: modular_lexer.py:193 and word_fusion.py:154 now pass `parts=tuple(...)` explicitly, while Token.__post_init__ already coerces any iterable to a tuple via object.__setattr__. Two mechanisms enforcing one invariant is exactly the shape the campaign keeps removing elsewhere. Harmless, but the frozen-graph census guard (test_lexical_value_graph_frozen.py) is the single authority here, so the explicit tuple() calls could go — or the ledger should say why they stay (cheap belt-and-braces at the hot emission path is a legitimate answer).

```
psh/lexer/modular_lexer.py:  token = Token(..., adjacent, parts=tuple(self.current_parts))
psh/lexer/word_fusion.py:     parts=tuple(parts),
psh/lexer/token_types.py:     def __post_init__(self) -> None: ... if not isinstance(self.parts, tuple): object.__setattr__(self, 'parts', tuple(self.parts))
```

## NIT 5 [resurrection] — 

Dangling forward-reference to a not-yet-rescued evidence file. tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py:14 cites docs/reviews/evidence/boundary_remediation_2026-07/2.5-rescue/base_tip_identity.py, which does not exist anywhere in the branch tree (the 2.5-rescue directory itself does not exist; siblings 2.1-rescue .. 2.4-rescue do). The docstring self-documents this ('it is rescued to ... at ceremony ... citing that path would name a file the shipped tree does not contain'), so it is an accepted pattern, not a defect — but the pointer is dangling until the integrator actually performs the rescue at ceremony. Flagging so the rescue is not forgotten.

```
Extracted every psh/tools/docs path added by the diff (33 paths) and stat'ed each in a detached worktree at 6965a079: exactly one MISSING -> docs/reviews/evidence/boundary_remediation_2026-07/2.5-rescue/base_tip_identity.py. grep -rn 'base_tip_identity' psh/ tests/ docs/ tools/ -> tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py:14 (sole reference). ls docs/reviews/evidence/boundary_remediation_2026-07/ -> 1.2-rescue 1.3-rescue 1.3b-rescue 1.4-rescue 2.1-rescue 2.2-rescue 2.3-rescue 2.4-rescue FLIP-PINS.md LEDGER.md nightly-status.md wave-manifest.json wave0-base-probes wave0-legs wave0-legs-summary.md (no 2.5-rescue).
```

## NIT 6 [resurrection] — 

PRODUCTION source names a probe file that does not exist and gives no path at all. psh/utils/heredoc_detection.py:34 says the consumer list was 'enumerated from a census (``second_grammar_census.py``, rescued to ``docs/reviews/evidence/`` at ceremony)'. No file of that name exists in the branch, and unlike the test-side reference above it carries no resolvable path, so a reader of the shipped module cannot find the instrument that backs the census claim. Either rescue it to a concrete path and cite that path, or drop the filename and cite the LEDGER row.

```
grep -rn 'second_grammar_census' psh/ tests/ docs/ tools/ in a detached worktree at 6965a079 returns exactly one hit: psh/utils/heredoc_detection.py:34. No file by that name exists in the tree (find . -name 'second_grammar_census*' -> nothing).
```

## NIT 7 [resurrection] — 

Cross-module import of a module-private name: psh/io_redirect/manager.py imports _ALIAS_HEREDOC_HINT (leading underscore) from .file_redirect. It is intra-package and the import-layering guard passes, but the underscore signals module-private and the constant is now part of manager.py's contract; promoting it to a public module constant (or a small helper that formats the whole message) would keep the 'one place for the diagnosis' intent without the private-name reach-across.

```
psh/io_redirect/manager.py:73-77 -> 'from .file_redirect import (_ALIAS_HEREDOC_HINT, FileRedirector, NonExecutableRedirectError,)'. tests/unit/tooling/test_import_layering.py passes (165 passed across the doc/schema/import guard set), so this is style, not a layering violation.
```

## NIT 8 [resurrection] — 

Observation, verified benign and already pinned: the MEDIUM-10a type split changes user-visible --debug-ast output for collected heredocs (node label 'Redirect' -> 'HeredocRedirect', and heredoc_content moves after heredoc_id because it is now a kw_only field on the subclass). I confirmed this A/B and confirmed the dev declared and pinned it across all five formats, so it is NOT a blocker — recorded only so the integrator has the independent replay on file.

```
A/B on byte-exact probe file (od -c verified: 'cat <<EOF\nhi\nEOF\n'), detached worktrees at e36116c3 and 6965a079, PYTHONPATH pinned per tree, psh.__file__ discriminator checked. base: '└── Redirect / ├── type: "<<" / ├── target: "EOF" / ├── heredoc_content: "hi\n" / └── heredoc_id: 0'. tip: '└── HeredocRedirect / ├── type: "<<" / ├── target: "EOF" / ├── heredoc_id: 0 / └── heredoc_content: "hi\n"'. Pin: tests/unit/io_redirect/test_heredoc_executable_type.py:119 @pytest.mark.parametrize("fmt", ["tree", "compact", "pretty", "sexp", "dot"]) asserting 'HeredocRedirect' in dump plus the field-order half. Adjacent CLI analysis surfaces are UNCHANGED: --validate/--security/--format/--metrics over a heredoc script are byte-identical base-vs-tip on both parsers (--format md5 c7b1cd2d13aaf4a91190e1289084a6f5 in all four base/tip x rd/combinator cells).
```

## NIT 9 [ledgerCheck] — 

The committed campaign LEDGER.md MEDIUM-3 row (docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md:33, 'CONFIRMED — INTERACTIVE-ONLY (latent in -c...)') and the integrator plan :107 still carry the interactive-only latency claim that the branch's own B70 evidence proved over-claimed for the combinator (12 all-channel combinator deltas, red-on-base pinned). The dev correctly surfaced this as integrator-owned (both files are never-touch) at ledger B70; restating here so the ceremony edit is not lost — the row's confirm-time prose is now accurate for rd only.

```
git show origin/main:docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md line 33; dev ledger B70 (escaped-combinator-delta.txt, 12 combinator deltas, rd byte-identical); pin test_heredoc_declared_deltas_noninteractive.py present on branch (233 collected, all passing).
```

## NIT 10 [ledgerCheck] — 

psh/interactive/line_editor_helpers.py appears in the branch diff despite ruling R1-B's original 'diff must not touch either file'. Verified: the change is docstring-only (scopes the 'same oracle CommandAccumulator uses' claim and declares the joiner's heredoc half as a KNOWN DIVERGENCE; zero logic change), and the ledger records the superseding integrator adjudication (R14-B N10 supersedes R1-B for that hunk only, fault #6, ledger B94 nit 9). input_preprocessing.py, the other R1-B file, is untouched. Traceable and adjudicated — recorded for the audit trail only.

```
git diff origin/main...fix/remediation-2-5 -- psh/interactive/line_editor_helpers.py shows only module-docstring hunks; dev ledger B94 nit 9 names the ruling.
```

## NIT 11 [reprobe] — 

B92's claim that the alias-axis harness's "base discriminator asserts NonExecutableRedirectError is ABSENT there, so a mis-pointed PYTHONPATH cannot pass silently" overstates the instrument: tmp/r2-5-probes/alias_heredoc_axis.py only RECORDS the discriminator line into the transcript (L.append of DISCRIM stderr, lines 111-114); there is no assert/exit path that fails the run if the base tree resolves wrong. The recorded FACTS are correct (transcript header shows base=/Users/pwilson/src/psh-r25-base@e36116c3 -> False, tip@6965a079 -> True), a mis-point would also collapse TOTALS to 42-identical, and the committed pin file independently proves the base/tip split (my replay: 62F/30P at base), so nothing certified is false -- but the ledger sentence describes an asserting instrument the script is not. Record-only; no code change needed for closure.

```
grep 'assert|sys.exit|raise' over /Users/pwilson/src/psh-r2-5/tmp/r2-5-probes/alias_heredoc_axis.py returns only the __main__ sys.exit(main()); transcript alias-heredoc-axis.txt header lines 4-5 show the recorded discriminator values; my independent base replay of the committed pin reproduced the claimed 62 failed / 30 passed split exactly.
```
