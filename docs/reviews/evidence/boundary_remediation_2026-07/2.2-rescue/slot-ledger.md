# Slot 2.2 ledger — Parser input contract (HIGH-5 + MEDIUM-11)

Base: `db6dfb13` (v0.756.0 merge). Worktree `/Users/pwilson/src/psh-r2-2`,
branch `fix/remediation-2-2`. Bash oracle: `/opt/homebrew/bin/bash` 5.2.26.
Python 3.14.2, mypy 2.1.0.

## 1. Red-on-base evidence (at db6dfb13)

### HIGH-5 — combinator drops ParseInputs (lexer_options) on the nested re-lex

Byte-exact probe `tmp/r2-2-probes/extglob_nested.sh` (od -c verified):
```
shopt -s extglob\n
echo $(echo @(a|b))\n
```
Commands and outputs:
- `/opt/homebrew/bin/bash extglob_nested.sh` → `@(a|b)` exit 0
- `python -m psh extglob_nested.sh` (RD default) → `@(a|b)` exit 0
- `python -m psh --parser combinator extglob_nested.sh` →
  `psh: ...:1: Parse error (line 1, column 7): syntax error near unexpected token '('`
  (`echo @ -> HERE <- a | b`), exit 2.

**Isolation** (`tmp/r2-2-probes/extglob_toplevel.sh`: `shopt -s extglob\necho @(a|b)\n`):
- bash / RD / combinator ALL → `@(a|b)` exit 0.

So the combinator handles extglob when the OUTER lexer tokenized it (top-level),
and fails ONLY on the NESTED `$(...)` body, which is re-lexed at parse time. The
re-lex loses `lexer_options` (extglob) → the body `echo @(a|b)` re-lexes without
extglob → `@` word + `(` unexpected. This is exactly the LEDGER signature
"nested @(a|b) in $() rejected by combinator only; facade wrapper discards
source/options."

**Mechanism (traced in source):**
- Non-heredoc parse path: `scripting/lex_parse.py#parse_tokens` →
  `parser/__init__.py#create_parser`.
- `create_parser` RD branch threads all context:
  `Parser(tokens, config, source_text, line_offset, lexer_options)`.
- `create_parser` combinator branch builds a `_ParserWrapper` whose `.parse()`
  calls `pc.parse(tokens)` — dropping source_text, line_offset, lexer_options.
  The combinator's `_parse_inputs` stays None (only `parse_with_heredocs` sets it).
- At word-build time `combinators/expansions.py#build_word_from_token` passes
  `ctx=self.parse_ctx` (== `_parse_inputs`, None here) to
  `word_builder.py#parse_expansion_token` → `_nested_program`, where
  `lexer_options = getattr(ctx, 'lexer_options', None)` = None → nested body
  re-lexes WITHOUT extglob.

NOTE [STRUCK AND CORRECTED — round-1 B1: this was a FALSE claim]:
~~"the heredoc combinator path (parse_with_heredocs) already threads
lexer_options (campaign S4 handoff 3), so ONLY the plain create_parser
combinator path drops it — that facade wrapper is the defect."~~
CORRECTION: the combinator heredoc path did thread lexer_options, but the RD
HEREDOC path ALSO dropped context — `utils.parse_with_heredocs` hard-coded
source_text=None / line_offset=0, so the RD parser lost the caller's line_offset
on every heredoc-bearing command (this is exactly what surfaced as the B1
line-number improvement — see §7). So the facade wrapper was NOT the only
context-dropper; the word "ONLY" was wrong. Both the combinator create_parser
facade AND the RD utils.parse_with_heredocs path dropped context.

### MEDIUM-11 — RD Parser second .parse() returns empty

```
from psh.lexer import tokenize
from psh.parser.recursive_descent.parser import Parser
p = Parser(list(tokenize('echo hi')))
p.parse()   # -> 1 statement
p.parse()   # -> 0 statements (empty Program)
```
Reproduced at db6dfb13. Cause: `Parser.__init__` builds ONE `ParserContext`
(cursor) bound to the tokens given at construction; `parse()` advances the
cursor and never resets it, so the second `parse()` sees `at_end()` immediately.

Combinator is NOT affected (reusable): `ParserCombinatorShellParser(config)`
takes tokens per `parse(tokens)` call; repeated parses (same or different
tokens) each succeed. Verified live.

## 2. Caller census for the MEDIUM-11 lifecycle decision

[STRUCK AND CORRECTED — round-2 R3-2/BR2-2: this census was FALSE. It claimed
exactly 3 RD-Parser production sites; the TRUE base count is 7. Every missed
site is still fresh-instance/parse-once, so RULING 1 (single-use) STANDS, but the
record that justified it did not. Amended below with my own re-run instrument.]

~~"RD Parser production instantiation sites — ALL ... exactly once:
parser/__init__.py:64 parse(); parser/__init__.py:155 create_parser();
session.py:371."~~ — WRONG (3 of 7; missed parse_tree.py, line_editor_helpers.py,
nested_parse.py, utils.py).

RE-RUN INSTRUMENT (mine): `grep -rn "\bParser(" psh --include='*.py'` filtered to
exclude the combinator's own `Parser` primitive (everything under
`combinators/`), `ParserConfig`/`ParserContext`/`ParserState`/`ArithParser`, and
comment/docstring lines. (My round-1 instrument grepped `create_parser|
parse_with_heredocs|ParserCombinatorShellParser` — which structurally COULD NOT
see the four direct `Parser(...)` sites; that is the census gap. round-1 T3
endorsed it "all TRUE" — the endorsement was itself incomplete; both tallied.)

TRUE BASE (db6dfb13) census — 7 RD-Parser sites, EACH fresh-instance + parse-once
(verified by reading each call site; verifier round-2 independently confirmed):
1. `parser/__init__.py` `parse()` — `Parser(tokens, config).parse()`.
2. `parser/__init__.py` `create_parser()` — returns `Parser(...)`, caller `.parse()` once.
3. `parser/session.py:371` — `_trial_parse`: fresh `Parser(...)`, `.parse_outcome()` once.
4. `psh/builtins/parse_tree.py:88` — `Parser(tokens, source_text).parse()` once.
5. `psh/interactive/line_editor_helpers.py:159` — `Parser(tokens).parse_outcome()` once.
6. `parser/recursive_descent/support/nested_parse.py:74` — `Parser(...).parse()`
   once PER nested `$()`/`<()`/`>()` body (the substitution chokepoint; a fresh
   parser each nested call).
7. `parser/recursive_descent/support/utils.py:31` — `Parser(...).parse()` once
   [DELETED this slot].

TIP census — 4 sites (the one-entry consolidation removed 3): utils.py DELETED;
`parse()` is now a thin adapter and `create_parser` builds a `_DeferredParse`
handle, so both route through the SINGLE `Parser(...)` construction in
`parse_with_inputs` (parser/__init__.py:120); parse_tree.py now uses
`create_parser`. Remaining direct RD-Parser sites, all fresh + parse-once:
parse_with_inputs (the one entry), session.py:371, nested_parse.py:74,
line_editor_helpers.py:159.

(The many `Parser(...)` hits under `combinators/` are the combinator's OWN
`Parser` primitive class in `combinators/core.py`, unrelated to the RD Parser.)

Tests: grep of tests for again/second/twice/reuse `.parse()` → NONE. No test
relies on the empty-second-parse. The S4 state test
(`tests/unit/parser/test_parse_inputs_state_s4.py`) asserts per-INSTANCE
independence (fresh state per Parser instance), not single-instance reuse.

Docs contradiction: `parse_inputs.py` docstring says "a parser instance retains
neither [inputs nor state] after parse() returns" — implies a clean/reusable
instance, but the cursor persists, so a second parse is silently empty. That is
the MEDIUM-11 "docs imply reusability that does not hold."

## 3. HIGH-5 fix — one parse entry carrying ParseInputs (IMPLEMENTED)

New single entry `parser/__init__.py#parse_with_inputs(tokens, inputs,
active_parser='rd') -> Program`: threads the whole ParseInputs (source_text,
line_offset, lexer_options, heredocs, config) into BOTH parsers.
- Combinator: `ParserCombinatorShellParser.parse(tokens, inputs=None)` gained an
  optional `inputs` param that installs `self.heredocs`/`self._parse_inputs` for
  the duration (save/restore in finally, retains-nothing preserved). Its
  `parse_with_heredocs` now delegates to `parse(tokens, ParseInputs(...))`.
- RD: `Parser(tokens, config, source_text, line_offset, heredocs, lexer_options)
  .parse()` (unchanged constructor; the entry unpacks ParseInputs into it).
- Deleted the discarding `_ParserWrapper` facade in `create_parser`; replaced
  with a uniform `_DeferredParse` handle whose `.parse()` calls `parse_with_inputs`
  for BOTH parsers (so the combinator path no longer drops context).
- Module `parse_with_heredocs` and `create_parser` re-expressed as thin adapters
  over `parse_with_inputs`.
- `scripting/lex_parse.py#parse_tokens` now builds ONE ParseInputs (source_text +
  line_offset + lexer_options + heredocs) and calls `parse_with_inputs` for BOTH
  the heredoc and plain paths — collapsing the old two-branch dispatch.
- Guard update: `test_parser_contract_guards_s4.py` Guard 7 (ParseInputs
  construction sites) updated from {context.py, combinators/parser.py} to add
  {parser/__init__.py, scripting/lex_parse.py} — the deliberate one-entry
  architecture (callers bundle context into ParseInputs for the entry), with
  rationale. NOT a weakening: any 5th site still fails.

Verification: HIGH-5 probe flips (combinator now `@(a|b)` exit 0). Systematic
in-scope corpus: 5 extglob ops × 6 nesting shapes = 30 cases, ALL green on
RD+bash AND full AST parity RD↔combinator through the entry with extglob
threaded. Public API (`parse`, `create_parser`, `parse_with_heredocs`) still
returns Program; unknown parser still raises ValueError. ruff+mypy clean (274).

Lockstep corpus test: `tests/parser_differential/test_input_contract_parity.py`
(61 params): structure parity + nested-body `.line` location parity + the HIGH-5
flip (proving parity is contingent on threaded context). DOMAIN stated in the
module docstring.

### Scope finding — ArrayParsers ctx=None residual (OUT OF SCOPE, documented)

Full audit of combinator `WordBuilder` call sites: after the fix, EVERY
word-building path threads ctx via the shared `ExpansionParsers.parse_ctx`
EXCEPT three seams in `psh/parser/combinators/arrays.py`:
- L51 `parse_word_as_word` → static `WordBuilder.build_word_from_token(tok, qt)`
- L268 `_element_value_from_parts` → static `WordBuilder.build_word_from_token(head)`
- L254 `build_subscript_spec(subscript)` (element-assignment subscript;
  EXPLICITLY documented as an intentional residual at L246-254).

So `a=($(echo @(a|b)))` STILL diverges on the combinator (RD accepts). This is:
(a) PRE-EXISTING — red on base AND after the fix, IDENTICAL (verified);
(b) NOT the HIGH-5 entry-facade signature (it is a separate combinator seam that
    bypasses the shared ExpansionParsers via the STATIC builder, whose signature
    /decompose-branch logic differs — swapping is a non-trivial refactor with
    behavior-change risk, esp. subscript read-time validation);
(c) partly documented as "not chased, for the educational combinator".
DECISION: respect the documented residual; keep the fix on the entry facade +
shared word-building path (fully threaded); EXCLUDE array-init nested-substitution
from the required-parity corpus; state the domain precisely. Reported to
integrator in completion report.

## 4. MEDIUM-11 lifecycle — RULED (a) SINGLE-USE (IMPLEMENTED)

Integrator RULING 1 (inbox 2026-07-26): (a) single-use enforced, upheld.
Implementation:
- Guard in `recursive_descent/parser.py#Parser`: `self._parsed=False` set in
  `__init__`; `parse()` raises `RuntimeError("Parser is single-use: ...")` if
  already parsed, then sets `_parsed=True` BEFORE the parse body (so a FAILED
  parse also counts as used — the cursor is left mid-stream). The combinator is
  UNTOUCHED (stays reusable — takes tokens per parse(tokens) call).
- Exception type = plain `RuntimeError`. `ParseError` is a `PshError` (MRO:
  ParseError→PshError→Exception) = an "expected shell error" that
  passes-through/swallows, so it is NOT the loud programming-error the ruling
  requires. A non-recursion `RuntimeError` is the INTERNAL-DEFECT class that
  strict-errors RE-RAISES (core/CLAUDE.md internal_errors taxonomy) — loud under
  PSH_STRICT_ERRORS, DISTINCT from ParseError/SyntaxError, a Python builtin
  (nothing outside psh/parser touched → no STOP-and-report needed).
- `parse_outcome()` shares the budget: it routes through `parse()` exactly once
  via `outcome_from_parse(self.parse, ...)`, which catches only `ParseError`
  (parse_outcome.py L113) — so a single parse_outcome() works, and a second
  parse()/parse_outcome() raises the RuntimeError, which PROPAGATES uncaught
  (verified). Pinned in the contract test.
- Contract test (red-on-base): `tests/unit/parser/test_parse_inputs_state_s4.py`
  new section — second parse() raises single-use (was: empty Program); not a
  ParseError/PshError; parse_outcome shares budget; failed parse still consumes;
  fresh instance over same tokens parses fine. Module docstring updated.
- Docs: `parse_inputs.py` module docstring + `psh/parser/CLAUDE.md` S4 paragraph
  revised to state the single-use invariant instead of implying reusability
  (invariant prose + file#symbol pointer, no code sketch).

## 4b. RULING 2 — ArrayParsers ctx=None residual → CARRY (flip-pinned)

Integrator RULING 2: respect the documented residual, do NOT close it in-slot;
carry with a divergence pin.
- PROBE (byte-exact `tmp/r2-2-probes/array_nested.sh`, od -c earlier):
  `shopt -s extglob\na=($(echo @(a|b)))\necho "${a[@]}"\n`.
- PRE-EXISTING & UNTOUCHED proof: `git diff db6dfb13 -- psh/parser/combinators/
  arrays.py` = 0 bytes (byte-identical to base). Combinator error IDENTICAL at
  base AND at tip:
    base (db6dfb13, throwaway worktree):
      `psh: ...array_nested.sh:1: Parse error (line 1, column 7): syntax error
       near unexpected token '('`
    tip (after HIGH-5+MEDIUM-11): SAME line, verbatim.
  RD accepts it (matches bash) at both.
- MECHANISM: array-INIT element words are built by the STATIC
  `WordBuilder.build_word_from_token` in `combinators/arrays.py`
  (`parse_word_as_word` L51, `_element_value_from_parts` L268), bypassing the
  shared `ExpansionParsers` that carries the per-call ctx; the element-assignment
  subscript `build_subscript_spec` (L254) is the explicitly-documented residual
  (L246-254). So the `$()` element re-lexes WITHOUT extglob → combinator rejects.
- DIVERGENCE PIN (flip-pin): `test_input_contract_parity.py#
  test_CARRY_array_init_nested_substitution_still_diverges_on_combinator` — pins
  RD-accepts + combinator-raises; goes RED when a successor threads ctx into
  ArrayParsers and closes the residual. Corpus-domain exclusion stated in the
  module docstring. FOR INTEGRATOR: add LEDGER carry row + FLIP-PINS entry from
  this section at ceremony.

## 5. §3 lockstep parity corpus — design (space + domain)

`tests/parser_differential/test_input_contract_parity.py` — parses BOTH parsers
through the ONE `parse_with_inputs` entry with identical ParseInputs. Generated
over the SPACE (parser × construct × nesting × context-flag), NOT hand-picked:
- RE-LEX constructs × {@,!,*,+,?}: $() d1, $() d2 (nested), <(), ${..} operand,
  composite/fused word, double-quoted, arith $(( $() )). Each validated green on
  RD+bash 5.2.26 before pinning. (7 shapes × 5 ops = 35 params × 2 assertions.)
- HEREDOC PATH: `echo $(echo {op}(a|b)) <<END\nbody\nEND` × 5 ops via
  tokenize_with_heredocs (proves the entry threads options on the heredoc path).
- CONTEXT-FLAG: ordinary nested $() agrees with extglob ON and OFF.
- BACKTICKS = CONTROL: `...` is DEFERRED (program=None, raw source), NOT a
  parse-time re-lex path — parity holds independent of the flag; both keep
  program=None. Outside the HIGH-5 domain by design.
- STRUCTURE parity = whole canonical AST; LOCATION parity = nested-substitution
  body `.line` stamps (shared WordBuilder). Top-level statement `.line` is
  RD-only (documented combinator gap) — out of scope, stated.
- HIGH-5 flip test: without extglob threaded BOTH reject `echo $(echo @(a|b))`;
  with it threaded both accept + agree — proving parity is CONTINGENT on context.
82 params, all green (round-2 added the N8 redirect-target carry flip-pin).

## 6. Commit map / final state

- Base: db6dfb13 (v0.756.0 merge on origin/main).
- e1c98daf — HIGH-5: one parse(tokens,inputs) entry (parse_with_inputs) + facade
  delete (_ParserWrapper→_DeferredParse) + lex_parse reroute + lockstep corpus +
  Guard 7 update.
- d2c51be0 — MEDIUM-11 (a): RD Parser single-use RuntimeError guard + contract
  test + parse_inputs.py docstring + CLAUDE.md S4 paragraph (folds HIGH-5 prose)
  + expanded corpus (arith/heredoc/context-flag/backtick control) + CARRY flip-pin.
- e7b6a44b — HIGH-5 followup: heredoc-routing spy re-targeted at the one entry
  (parse(tokens,inputs) with inputs.heredocs) — stronger invariant.
- 3541520f — MEDIUM-11: explicit classifier pin
  (test_outcome_from_parse_does_not_swallow_the_single_use_runtimeerror) per
  integrator item-3 request — outcome_from_parse propagates the single-use
  RuntimeError rather than converting it to Invalid. Test-only, no production
  change. (Round-1 verification tip; SUPERSEDED by round-2 — see §8.)

APPROVED DEVIATION (integrator-blessed, recorded for verifier replay): the ruling
said "pick the exception type within the parser's existing taxonomy"; the taxonomy
CANNOT satisfy the "loud programming-contract error" contract (ParseError→PshError
is the swallowed/pass-through class). Plain RuntimeError is the internal-defect
class strict-errors RE-RAISES, and is a builtin (nothing outside psh/parser
touched). Integrator ruled RuntimeError as the correct resolution of the two
constraints.

### Gate results at ROUND-1 tip 3541520f (superseded by round-2, §8)
- Full gate `python -u run_tests.py --parallel` (tmp/gate-2.2-final2.txt): EXIT=0,
  20813 passed, 1589 skipped, 10 xfailed, 0 FAILED. (+1 vs prior gate = the new
  classifier pin.)
- compare-bash `python -m pytest tests/behavioral --compare-bash -n auto -q`
  (tmp/compare-bash-2.2b.txt): 2985 passed, 25 skipped, 0 divergence. EXACT — base
  db6dfb13 measured IDENTICAL (2985 passed / 25 skipped) in a throwaway worktree,
  so 0 behavioral delta. (Memory's "2,986" is earlier-campaign drift; the live
  db6dfb13 baseline is 2985.)
- ruff check psh tests tools: clean. mypy: clean (274 files). Working tree clean.
- Prior gate at e7b6a44b (tmp/gate-2.2-final.txt): 20812 passed, 0 FAILED.

### First-gate failure (fixed forward, recorded per instrument discipline)
The first full gate (tmp/gate-2.2.txt) had exactly ONE failure:
`test_combinator_parity_regressions.py::TestHeredocRoutingSpy::
test_heredoc_input_reaches_combinator_parser` — it spied on the combinator's
`parse_with_heredocs`, which the HIGH-5 reroute no longer uses for shell heredoc
input (now `parse(tokens, inputs)` with inputs.heredocs). The pinned INVARIANT
(heredoc reaches the combinator, not silently RD) still holds; only the mechanism
moved. Re-targeted the spy at `parse` and additionally asserted the heredoc map
arrived via ParseInputs (strictly stronger). Verified via live spy before editing.
Committed as e7b6a44b; re-ran the full gate → green.

ROUND-1 STATUS (superseded): shipped through 3541520f, then BOUNCED by
verification round-1 (2 blockers upheld + 12 required fixes). See §7/§8.

## 7. B1 — RD heredoc parse-error absolute-line improvement (declared + pinned)

CO-LANDED IMPROVEMENT (round-1 B1, upheld — declare+pin, NOT revert). Rerouting
the heredoc branch through `parse_with_inputs` threads line_offset/source_text
into the RD parser for the FIRST time; the deleted `utils.parse_with_heredocs`
hard-coded None/0. So a parse error in a nested `$()` of a heredoc-bearing
command now reports the ABSOLUTE line (= bash) instead of fragment-relative
line 1. (The false "ONLY the combinator path drops it" sentence in §2 is struck
and corrected there.)

DOMAIN — BOTH PARSERS (R3-4): the improvement manifests on `--parser rd` AND
`--parser combinator`. The erroring nested `$(if)` is parsed by the
recursive-descent parser via the shared nested-parse path (`nested_parse.py`)
even under the combinator, so the threaded line_offset reaches it on either
active parser. Verifier round-2 replayed both (pad base 1→tip 3; padded-function
base 2→tip 4; all modes; = bash); the pins now parametrize over both parsers.

PROBE BATTERY (byte-exact files in tmp/r2-2-b1/, od -c verified; bash =
/opt/homebrew/bin/bash 5.2.26; both parsers; file/-c/stdin modes):
GENUINE BASE OUTPUTS (integrator narrowed the hold to allow a throwaway base
worktree + single-command psh probes: `git worktree add --detach tmp/r2-2-base
db6dfb13`; discriminator verified `psh.__file__ = .../tmp/r2-2-base/psh/...`,
HEAD db6dfb13; worktree removed after). All three modes (file/-c/stdin):
- pad_heredoc.sh = `: p1\n: p2\necho $(if) <<EOF\nbody\nEOF\n` (erroring command
  on line 3):    BASE `line 1` → TIP `line 3` (prefix `:3:`, caret
  `(line 3, column 3)`) → bash 5.2.26 `line 3`. DELTA, tip matches bash.
- padfunc_heredoc.sh = `: p1\n: p2\nf() {\n  echo $(if) <<EOF\nbody\nEOF\n}\n`
  (function defined line 3, heredoc body command on line 4):
                   BASE `line 2` → TIP `line 4` → bash `line 4`. DELTA, matches.
  (A function at line 1 does NOT delta — its whole body is one command buffer, so
  the error line is already absolute at base; that shape was dropped as it is not
  red-at-base.)
- nopad_heredoc.sh = `echo $(if) <<EOF\nbody\nEOF\n` (CONTROL, line 1):
                   BASE `line 1` = TIP `line 1` = bash `line 1`. No offset, no delta.
CORROBORATION: (a) verification round-1 T1 independent replay (base line 1 / tip
line 3 / bash line 3; 15 RD deltas swept across file/-c/stdin, function bodies,
source, eval; 60-case success-parse control = 0 deltas); (b) in-process witness —
`parse_with_inputs` on the pad fragment with the OLD budget (line_offset=0,
source_text=None) → error_context.line == 1, threaded (line_offset=2) → 3.
EXIT-CODE DIVERGENCE (classified per round-2 note 2; instrument stated):
On the golden shape (pad_heredoc), bash's exit code is MODE-DEPENDENT:
  `bash -c` → 127 ; `bash file` → 2 ; `bash stdin` → 2   (bash 5.2.26)
  `psh` → 2 in ALL modes.
So psh(2) ↔ bash(127) diverge ONLY in `-c` mode. CAUSE (corrected per R3-5): this
is NOT a "heredoc quirk" — it is bash's NESTED-SUBSTITUTION -c error class. Proof:
`bash -c 'echo $(if)'` (NO heredoc) also exits 127 (verified), while file/stdin
give 2. It is the SAME family as FLIP-PINS' slot-2.4-owned
`test_divergence_c_mode_exit_code_is_127_in_bash` (the `$(if)` substitution-origin
-c syntax error). The integrator registers this golden row as a 2.4 co-flip at
ceremony (its `exit_code: 2` pin flips when 2.4 makes psh -c return 127 for
substitution-origin syntax errors).
PRE-EXISTING & UNCHANGED by this branch: genuine base-worktree probe (tmp/
r2-2-base2, discriminator-verified) → BASE `psh -c` exit=2, line 1; TIP `psh -c`
exit=2, line 3. Only the LINE number changed (the B1 improvement); the exit code
was 2 at base and tip. bash is external/unchanged. The golden is `psh -c`, so a
direct compare-bash of that row would hit the -c 127/2 divergence AND the caret-
format difference — hence psh_only; the divergence is recorded HERE, not hidden.
Instrument: `SCRIPT=$(cat tmp/r2-2-b1/pad_heredoc.sh); /opt/homebrew/bin/bash
-c "$SCRIPT"` (exit 127) vs `... bash file/stdin` (exit 2).

PINS: tests/integration/parser/test_heredoc_error_lineno.py (in-process exact
line + red-at-base witness + subprocess file/-c/stdin `:3:`+`line 3` for the pad
shape and `:4:`+`line 4` for the padded-function shape + no-pad control). Golden
row `heredoc_nested_error_reports_absolute_line` pins psh-side
`-c:3: Parse error (line 3, column 3)`, psh_only.

## 8. ROUND-2 remediation (dispositions + commits)

Commits on db6dfb13 (round-2 adds three on top of round-1's four):
- 955b08e4 — B3 cluster + N1/N2/N3/N4/N5 (delete utils.parse_with_heredocs;
  _DeferredParse single-use; context.py docstring; return annotations + registry;
  import cap 2→1; token-copy at entry; conditional heredoc override). + pins.
- f60b114e — B1 declare+pin (heredoc absolute-line pins + golden) + N8
  (redirect-target carry flip-pin, blast radius widened) + N9 (reword).
- fa40fe5a — B1 evidence upgrade: genuine base-worktree outputs replace the
  at-tip simulation; the not-red-at-base function-at-line-1 pin shape swapped for
  the padded-function shape (base line 2 → tip line 4) that actually deltas.

Disposition of each round-1 item:
- B1 → §7 above (declared + pinned + golden + false-sentence struck).
- B3 → utils.parse_with_heredocs DELETED (whole file; was its only content);
  create_parser + __init__.parse_with_heredocs kept as PUBLIC thin adapters over
  parse_with_inputs, docstrings reworded, zero production callers recorded
  (educational/public surface, kept deliberately per ruling). _DeferredParse
  handle SINGLE-USE (RuntimeError, both active_parser choices), pinned; combinator
  GRAMMAR instance stays reusable. CLAUDE.md states handle+RD single-use,
  combinator reusable.
- B2 → tip references reconciled (this rewrite): §6 3541520f demoted to "round-1
  verification tip, superseded"; the FINAL TIP is the round-2 tip (recorded at
  §9 after the gate). No remaining "e7b6a44b FINAL TIP" text.
- N1 done (context.py). N2 done (annotations + registry). N3 done (cap 2→1;
  verified psh/parser/__init__.py now has exactly 1 function-level import).
- N4 done. MECHANISM (honest): the caller list is ALREADY unmutated today —
  create_context does `normalizer.normalize(list(tokens))` (list() copy +
  normalize returns a NEW list via dataclasses.replace), so the time-slot rewrite
  hits create_context's internal copy, not the caller's list. The entry-level
  `list(tokens)` restores the old heredoc-path copy and makes the one entry
  self-sufficient; the pin is a regression guard (green at base too), not a
  red-on-base fix. ENUMERATION (N6): verified via
  `python -c` calling parse_with_inputs on `echo a | time cat` and comparing
  [(type,value)] and [id] before/after (test_parse_with_inputs_does_not_mutate_
  caller_token_list).
- N5 done: choice (i) conditional override (`if inputs.heredocs is not None`).
  Rationale: an inputs carrying no heredocs must not erase an __init__-supplied
  map; keeps the __init__ param. Pin: Guard 9 in test_parser_contract_guards_s4.
- N6 (census commands): grep patterns recorded inline where each census was made.
  CORRECTED per R3-2 — the round-1 §2 census used `grep -rn "create_parser|
  parse_with_heredocs|ParserCombinatorShellParser" psh` which STRUCTURALLY could
  not see the 4 direct `Parser(...)` sites → the census was incomplete (see the
  strike-and-correct in §2). The correct instrument is `grep -rn "\bParser(" psh
  --include=*.py` minus combinators/ + config/context/state/ArithParser +
  comment lines; TRUE base count 7, tip 4, all fresh+parse-once. The
  double-parse census used `grep -rn "\.parse()" tests` + again/second/twice/reuse.
- N7 BASELINE: compare-bash baseline is 2985 passed / 25 skipped at db6dfb13
  (NOT the campaign's stale "2,986"). CONFIRMED BY VERIFICATION ROUND-1 T3
  INDEPENDENT REPLAY. No new heavy run needed.
- N8 → §4b widened (full parse_word_as_word reach: array-init + element-assign +
  redirect targets) + second flip-pin
  (test_CARRY_redirect_target_nested_substitution_still_diverges_on_combinator).
- N9 → reworded "pre-existing (newly documented by this slot)".
- N10 → the approving message id for the RuntimeError deviation is ae50a337
  (cited here so approval is traceable in the durable ledger, not only
  integrator records).
- N11 → GUARD-7 WIDENING scope ruling, recorded verbatim per integrator:
  "The scripting/lex_parse.py production touch was integrator-approved: it is
  the seam caller of the facade the brief ordered deleted/fixed; approval
  recorded in resume message (commit instruction for e1c98daf) and
  INTEGRATOR-INBOX. — integrator, 2026-07-26".
- N12 → tip reconciliation done (B2 above).

## 9. FINAL STATE (round-2)

FINAL TIP: **2e1a5a61**. Round-2 commits (4, on round-1's 4):
955b08e4 (B3 cluster + N1-N5), f60b114e (B1 pins + golden + N8/N9),
fa40fe5a (B1 genuine base evidence), 2e1a5a61 (bash exit-code instrument).

GATE RESULTS AT 2e1a5a61 (integrator GO'd the single heavy run; machine clear):
- Full gate `run_tests.py --parallel` (tmp/gate-r2.txt): EXIT=0, 20828 passed,
  1590 skipped, 10 xfailed, 0 FAILED.
- compare-bash `pytest tests/behavioral --compare-bash -n auto -q`
  (tmp/compare-bash-r2.txt): 2986 passed, 26 skipped, 0 divergence.
- ruff clean; mypy clean (273 files — one fewer than round-1's 274, utils.py
  deleted); working tree clean.

DELTA ACCOUNTING (vs round-1 tip 3541520f = 20813 passed / 1589 skipped):
gate +15 passed, +1 skipped; compare-bash +1 passed, +1 skipped.
- 955b08e4 → +4 gate tests: test_deferred_parse_handle_is_single_use (×2,
  rd+combinator), test_parse_with_inputs_does_not_mutate_caller_token_list (N4),
  test_combinator_inputs_without_heredocs_keeps_init_map (Guard 9 / N5). (The
  program_root rd-test swap is net 0: −test_rd_parse_with_heredocs_returns_program,
  +test_parse_with_inputs_heredoc_returns_program.)
- f60b114e → +11: 9 in test_heredoc_error_lineno.py (2 in-process + 3 pad + 3
  padded-function + 1 no-pad control) + 1 redirect-target carry pin + 1 golden
  psh-side. The golden also contributes the +1 skip (its compare-bash variant is
  psh_only). In the --compare-bash phase the golden psh-side is the +1 passed and
  the bash-compare is the +1 skipped (2985/25 → 2986/26).
- fa40fe5a → +0 (test-only B1 shape correction). 2e1a5a61 → +0 (comment-only).

No version.py/CHANGELOG/README/ARCHITECTURE/docs-reviews touched; no
push/PR/merge/tag.

## 10. ROUND-3 remediation (narrow bounce — record/doc + 2 small production)

Round-2 verdict = narrow BOUNCE: ALL substance replayed clean (B1 red-at-base,
bash-127 three-mode, B3 deletion+single-use both parsers, N4 mechanism, N5
mutation check). 2 blockers were record/doc integrity + 2 small residual
context-drops. Dispositions:
- R3-1 (BR2-1) — psh/parser/CLAUDE.md support table listed the DELETED
  support/utils.py. Removed that row (replaced with the real syntax_templates.py,
  which was missing); reworded the historical pointer as prose ("not a live
  pointer … DELETED in this slot"); RIDER: added syntax_templates.py to
  support/__init__.py's docstring enumeration.
- R3-2 (BR2-2) — §2 caller census was FALSE (claimed 3, true base 7).
  Strike-and-corrected in §2 with my own re-run instrument, all 7 base sites +
  per-site fresh+once, tip=4, round-2 find cited; N6 (§8) corrected too.
- R3-3 — §5 count 81→82 (done above).
- R3-4 — B1 manifests on BOTH parsers: pins parametrized over rd+combinator
  (test_heredoc_error_lineno.py), §7 domain corrected to both parsers.
- R3-5 — causal fix: bash -c 127 is the NESTED-SUBSTITUTION -c error class
  (`bash -c 'echo $(if)'` no-heredoc = 127), same family as slot-2.4's
  test_divergence_c_mode_exit_code_is_127_in_bash — NOT a "heredoc quirk".
  Fixed in §7 + the golden comment, with the 2.4 cross-reference.
- R3-6 (SCOPE GRANTED) — two residual context-drops fixed:
  (a) psh/parser/__init__.py#parse(tokens, config) now a THIN ADAPTER over
      parse_with_inputs (was a direct Parser build).
  (b) psh/builtins/parse_tree.py:88 dropped lexer_options into the parser (the
      HIGH-5 defect class inside the builtin — nested `$()` re-lexed without
      extglob). Routed through the PUBLIC create_parser adapter (threads
      lexer_options via a ParseInputs constructed in __init__.py — the sanctioned
      site — so NO Guard-7 widening, staying within the granted one-site touch).
      Pin: test_parse_tree_respects_extglob_in_nested_substitution (red-at-base;
      base rejected `shopt -s extglob; parse-tree 'echo $(echo @(a|b))'` with a
      parse error near `(`; verified via base worktree tmp/r2-2-base3).
- R3-7 — Guard-7 synthetic offender added
  (test_parse_inputs_construction_sites_offender) — shows the site-matcher fires
  and a new site breaks the set-equality; typology completion.

CARRY CROSS-REF (ceremony item — combinator TOP-LEVEL line_offset): the
combinator ignores threaded line_offset for TOP-LEVEL statement `.line` stamps
(it does not stamp them at all — pre-existing gap, newly documented by this slot;
see §5 and test_input_contract_parity.py module docstring). NESTED-substitution
bodies ARE now correct on both parsers (§7, R3-4) because the nested parse is
recursive-descent via nested_parse.py. Integrator adds the explicit LEDGER carry
row at ceremony; this is the dev-side cross-reference to it.

## 11. FINAL STATE (round-3)

FINAL TIP: **8170cd17**. Round-3 commits (3, on round-2's 8):
- f1d0f9bc — R3-1 (doc integrity) + R3-6 (parse thin adapter + parse_tree
  lexer_options) + R3-7 (Guard-7 offender).
- f1c3acde — R3-4 (B1 combinator leg) + R3-5 (causal-attribution fix).
- 8170cd17 — gate-fix: broad-VT-catch classification registry updated for the
  R3-6b Parser→create_parser swap (test-only; the 3 first-gate failures were one
  stale registry entry — see below).
Ledger-only fixes (this file): R3-2 (§2 census strike-correct), R3-3 (§5 81→82),
§7/§8/§10 record updates.

GATE RESULTS AT 8170cd17 (integrator GO'd the heavy run):
- Full gate `run_tests.py --parallel` (tmp/gate-r3b.txt): EXIT=0, 20836 passed,
  1590 skipped, 10 xfailed, 0 FAILED.
- compare-bash (tmp/compare-bash-r3.txt): 2986 passed, 26 skipped, 0 divergence.
- ruff clean; mypy clean (273); tree clean.

DELTA (vs round-2 tip 2e1a5a61 = 20828 passed): gate +8; compare-bash unchanged
(2986/26 — round-3 added no golden; the R3-6b pin is in-process captured_shell,
the R3-5 golden change was comment-only).
- f1d0f9bc → +2: test_parse_tree_respects_extglob_in_nested_substitution (R3-6b)
  + test_parse_inputs_construction_sites_offender (R3-7).
- f1c3acde → +6: B1 pad/padded-function pins parametrized rd+combinator (3 each
  → 6 each). 8170cd17 → +0 (registry value change, no new test).

FIRST ROUND-3 GATE (tmp/gate-r3.txt) had 3 failures, ALL one root cause: the
R3-6b Parser→create_parser swap made parse_tree.py's entry in the broad-VT-catch
classification registry (test_broad_valueerror_catch_q2.py — it keys each
broad-catch by the names called inside its try block) stale. Test-only registry
update (8170cd17, DECLARED before landing); re-gate green. Catch + classification
comment unchanged.

No version.py/CHANGELOG/README/ARCHITECTURE/docs-reviews touched; no
push/PR/merge/tag.
