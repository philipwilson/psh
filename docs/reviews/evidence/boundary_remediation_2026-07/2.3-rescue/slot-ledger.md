# Slot 2.3 ledger — Subscript syntax identity (HIGH-4 + MEDIUM-4 + MEDIUM-12a)

- **Worktree:** /Users/pwilson/src/psh-r2-3, branch `fix/remediation-2-3`
- **Base:** 4c319a04 (merge of PR #506 = v0.757.0; `psh/version.py` = 0.757.0, verified)
- **Bash oracle:** /opt/homebrew/bin/bash (PATH bash; version recorded below at first probe)
- **Brief:** tmp/remediation-ledgers/brief-2.3.md (read in full 2026-07-26)
- **Governing rows read:** LEDGER.md Part A HIGH-4, MEDIUM-4, MEDIUM-12 (2.3 owns
  the subscript half = 12a); Part B row 3 (empty-arith-subscript, RE-CARRIED,
  optional revisit WITH ruling only); Part B row 23 (nested-quote arith carriers,
  RE-CARRIED B1-model-limit — must NOT flip); LEDGER row "2.2 carry: combinator
  arrays.py word-builder seam (FULL reach)" (successor-owned; partial threading =
  STOP-and-report); FLIP-PINS.md must-flip rows owned by 2.3 (procsub_read_time +
  adjacent family, quote_blind_extent K1, sq_inside_dq) and the full must-NOT-flip
  table.

## Status

- [x] Brief + LEDGER + FLIP-PINS read
- [x] Red-on-base reproduction (HIGH-4, MEDIUM-4, MEDIUM-12a relocation)
- [x] Design note
- [x] Implementation (D1-D5; commits 21a7e1bc, b04b24a1, bf657d6f)
- [x] Pin flips in-slot (D6, 8339959b) + g-matrix pins (ec1d53c2)
- [x] ruff (tree-wide) + mypy (273 files) clean at ec1d53c2
- [ ] BLOCKED on integrator: builtins ACK (drafted patches below); g6/g8
      ruling; targeted-pytest GO; full gate + compare-bash GO
- [ ] Full gate green + compare-bash EXACT (after GO)
- [ ] Completion report with declared final tip

## Orientation notes (code read at base, before any probe)

- `psh/expansion/subscript.py` (225 lines at base): the W2 keying authority.
  The two MEDIUM-12a catch sites at v0.750.0 (`:129,144`) are at base
  **subscript.py:129 and :144** still — `except Exception` in
  `word_from_text` around (a) `tokenize(raw)` and (b)
  `WordBuilder.build_word_from_token(...)`; both degrade to an unquoted
  literal part. (Line drift check done by reading the file; re-verified below.)
- `associative_key(raw)` -> `word_from_text(raw)` re-lexes RAW subscript text at
  keying time -> `expand_assignment_value_word(word)`. A `<(...)` in raw re-lexes
  to a procsub token part => the procsub RUNS at keying time. This is the HIGH-4
  mechanism (to be confirmed by probe).
- `build_subscript_spec` (`psh/parser/recursive_descent/support/syntax_templates.py:220`)
  scans with `allow_procsub=False` => `<(if)` in a subscript is never read-time
  validated (no read-time rejection parity). `_scan` records `NestedSub` spans
  relative to the subscript text (base=0) — the "absolute SourceSpan" charter item.
- RD extent scan: `parsers/arrays.py#_candidate_single_token_element` uses
  `value.index(']')` on `_unquoted_leading_literal(token)` (the UNQUOTED leading
  literal run) — a quoted `]` TERMINATES the leading literal, so `a["]"]=ok`
  never classifies as an element assignment. Combinator twin:
  `combinators/arrays.py#is_element_head` + `parse_element_assignment` same
  `value.index(']')` pattern.
- Combinator `parse_element_assignment` builds `index_spec=build_subscript_spec(subscript)`
  with NO ctx — that is inside the 2.2 arrays-seam carry (successor-owned;
  partial threading = STOP-and-report).
- SubscriptSpec type: `psh/ast_nodes/syntax_templates.py:139` (frozen dataclass,
  text + subs tuple of NestedSub with spans).
- Keying call sites (whole tree, grep `associative_key\|indexed_index\|subscript\.evaluate\|word_from_text\|raw_has_source_quote`):
  executor/array.py:163,260,269; expansion/arrays.py:76,145,209,211;
  expansion/variable.py:182; expansion/operators.py:185;
  expansion/arithmetic/evaluator.py:231,237; builtins/test_command.py:39-41;
  builtins/environment.py:740. Builtin sites pass ALREADY-argument-expanded
  strings (not parser-built) — any design must keep a text entry point for them.

## Red-on-base evidence (COMPLETE 2026-07-26)

- **Probe corpus:** `tmp/probes-2.3/*.sh` — byte-exact FILES, every one od -c
  verified in-transcript at creation. Results (full rc/stdout/stderr byte
  reprs, all three shells, discriminator `psh.__file__` printed per harness
  run): `RESULTS-base.txt` (22 probes), `RESULTS-base-2.txt` (+19),
  `RESULTS-base-3.txt` (8), `RESULTS-base-4.txt` (16), `RESULTS-base-modes.txt`
  (7 shapes x -c/stdin modes), `RESULTS-0215279c-drift.txt` (5 shapes at the
  campaign launch base, probe-grade detached worktree
  /Users/pwilson/src/psh-r23-baseprobe, discriminator-verified, since removed).
- **Oracle:** GNU bash 5.2.26(1)-release aarch64-apple-darwin23.2.0 =
  /opt/homebrew/bin/bash = PATH bash (both verified in transcript).
- Both parsers behave IDENTICALLY on every probe (rd/comb columns equal
  everywhere except cosmetic parse-error wording in s2).

### HIGH-4 (procsub identity/timing) — CONFIRMED, both parsers

| Probe | bash | psh (rd = comb) |
|---|---|---|
| h4_assoc_procsub_key `declare -A a; a[<(printf x)]=v` | key `<(printf x)` LITERAL | key `/dev/fd/3` (procsub RAN) |
| h4b_side_effect `a[<(echo RAN > f)]=v` | NO_SIDE_EFFECT | SIDE_EFFECT (body executed at keying) |
| h4b_literal_key_read `a['<(printf k)']=v; ${a[<(printf k)]}` | `read=v` (literal key lookup) | `read=` (ran procsub, missed) |
| h4b_unset_literal `unset -v 'a[<(printf x)]'` | removes literal key | silent no-op (key stays) |
| h4b_testv_literal `test -v 'a[<(printf x)]'` | rc 0 | rc 1 |
| h4_dead_branch `true \|\| a[<(if)]=1; echo ran` (file) | rc 2 read-time, whole buffer | runs `ran` rc 0 |
| h4b_direct_invalid `declare -A a; a[<(if)]=1; echo after` | rc 2 read-time | runs `after` |
| h4b_mid_invalid `true \|\| a[1<(if)]=x` | rc 2 read-time (mid-subscript spelling also validated) | runs |
| h4_outsub_invalid `a[>(if)]` | rc 2 read-time | runs |
| h4_read_side_invalid `true \|\| echo "${a[<(if)]}"` | rc 2 read-time | runs |
| h4_arith_control `a[1<(2)]=x` | `[1]="x"` (arith) | `[1]="x"` PARITY |
| h4b_cmdsub_dead_parity `true \|\| a[$(if)]=1` (file) | rc 2 | rc 2 PARITY (cmdsub scan already lands) |
| h4b_arith_ctx `true \|\| : $((a[<(if)])); echo ran` | runs `ran` rc 0 — arith ctx NOT read-time validated | runs PARITY |
| d15 `(( a[<(if)] ))` | RUNTIME arith error, FATAL to script | runtime arith error, NON-fatal — arith-FATALITY family (B#3-adjacent), OUT OF SCOPE, do not touch |
| h4b_backtick `a[\`printf k\`]=v` | key `k` (backtick RUNS) | PARITY — keep executing |
| h4_assoc_cmdsub `a[$(printf k)]=v` | key `k` (cmdsub RUNS) | PARITY — keep executing |
| h4b_dq_procsub_key `a["<(printf x)"]=v` | literal key | PARITY (quoted spelling fine at base) |
| d5 `a[x<(y)]=v` | key `x<(y)` literal | `x/dev/fd/3` + `y: command not found` (RAN) |
| d6/d7 `"${a["<(if)"]}"` / `"${a['<(if)']}"` dead branch | defers (runs) | PARITY — quoted procsub spelling never read-time validated |
| h4b_read_undecl_procsub `${a[<(printf k)]}` undeclared | runtime arith err rc 1 | runtime arith err rc 1 — wording family only |

- **-c mode note:** bash gives rc 127 for the read-time rejection in -c mode
  (`h4_dead` -c: bash 127 vs psh 0-at-base; psh's EXISTING cmdsub rejection
  gives rc 2 in -c). The 2/127 -c divergence is slot 2.4's charter (its 6-param
  pin includes `a[$(if)]=v`). MY pins use file/stdin mode (bash rc 2 there);
  the new procsub rejection must route through the SAME SubstitutionSyntaxError
  path as the cmdsub one so 2.4's fix covers both spellings at once.

### MEDIUM-4 (extent) — CONFIRMED, both parsers; LEDGER prose imprecise

**Signature correction (documented, not a scope change):** LEDGER Part A says
`a["]"]=ok` is "rejected by both psh parsers". LIVE at BOTH 0215279c
(RESULTS-0215279c-drift.txt) and my base 4c319a04: NOT rejected — ACCEPTED
with the WRONG KEY (`declare -A a=(["\""]="ok" )`, key = `"`), because the
head scan truncates the subscript at the first `]` and the keying engine's
broad catch (MEDIUM-12a!) turns the un-lexable fragment `"` into a literal
key. The divergence itself is exactly as charted (bash `["]"]="ok"`); only
the psh-side failure MODE in the prose is stale. The committed flip-pin
(`test_divergence_quote_blind_extent_in_assignment_word`, `a["a]b"]=1`)
asserts the mis-key inequality and is consistent with live behavior.

| Probe | bash | psh (rd = comb) |
|---|---|---|
| k1_dq_rbracket `a["]"]=ok` | key `]` | key `"` (truncated extent -> broad-catch literal) |
| k1_dq_embedded `a["a]b"]=1` | key `a]b` | key `"a` |
| k1_sq_rbracket `a[']']=x` | key `]` | key `'` |
| k1_backslash `a[\]]=x` (declare -A) | key `]` | key `\` |
| d9 ansi-c `a[$']']=x` | key `]` | key `\$'` |
| d13 `a["+="]=v` | key `+=` val `v` | key `+=` val `"]=v` (mangled; `'+=' in value` matched the QUOTED +=) |
| d14 `a[']'x]=v` | key `]x` | key `'` |
| d16 `c[b[i]]=N` (indexed, nested unquoted brackets) | `[8]="N"` | `b[i: bad array subscript` rc 1 (first-`]` truncation) |
| d10 `a[$(echo "]")]=c` | key `]` (cmdsub runs) | rc 2 `Unclosed " quote` — truncated extent `$(echo "` cascades into nested read-time validation. LEXER IS INNOCENT: `tokenize('declare -A a; a[$(echo "]")]=c; declare -p a')` yields clean tokens (verified in transcript) — the failure is the PARSER extent scan |
| k2_read `${a["]"]}` / `${a[']']}` (+unquoted-outer) | reads key | rc 1 `bad substitution` (param_parser `_subscript_end` quote-blind) |
| d3 `${a["]"]:-d}` | `V` | rc 1 bad substitution (`_scan_operator` quote-blind) |
| d4 `${#a["]"]}` | `5` | rc 1 bad substitution (`_is_param_spec` via `_subscript_end`) |
| d11 read `${a[$(echo "]")]}` | `read=R` | rc 2 (same cascade as d10) |
| d1 `unset -v 'a["]"]'` | rc 0 removes key `]` | key stays (DOWNSTREAM of write mis-key: builtin path splits `a` + `"]"` fine and keys `]`; the STORED key was wrong) |
| d2 `test -v 'a["]"]'` | rc 0 | rc 1 (same downstream cause) |
| k1_init `declare -A a=(["]"]=I)` and `a+=(["]"]=J)` | key `]` | PARITY — the INIT element path is already quote-aware (Word parts); not part of the fix surface |
| k1_indexed_dq `b["0"]=z` | `[0]="z"` | PARITY |
| k2_arith `$((a["]"]))` | error rc 1 (bash arith is ALSO quote-limited: `a[]]`) | error rc 1 — PARITY of outcome, wording family; arith ctx NOT a fix target |
| d8 indexed `b[\]]=x` | runtime arith err rc 1 (token `\]`) | runtime arith err rc 1 (on truncated `\`) — outcome parity, wording family; after extent fix psh errors on `\]` (stays in family) |
| d12 `${a["]}` unbalanced | rc 2 lexer-level | rc 2 lexer-level PARITY (wording differs) |

### sq-inside-dq pin (s2 family) — STAGE PARITY ALREADY HOLDS AT BASE

- s1 ok-case `"${h['k']}"` -> `v` all three shells, all modes. PARITY.
- s2 `echo "${h['$(if)']}"`: bash rc 1, stdout empty; psh rc 1, stdout empty
  (BOTH parsers, file/-c/stdin all consistent). BOTH shells are RUNTIME-stage:
  the discriminating probe s4 (`true || echo "${h['$(if)']}"` dead branch)
  runs `ran` rc 0 SILENTLY in bash AND psh — no read-time validation on either
  side. s3 (next line) continues in both. Remaining divergence = stderr
  WORDING ONLY (bash: `command substitution: line 2: syntax error near ')'`
  from its runtime cmdsub whose extent ran to EOF; psh: nested `<command>`
  parse error + `Unexpected character ''' at position 0` arith error).
- Verified IDENTICAL at 0215279c (drift file): the pin docstring's "psh
  rejects at parse time" claim was ALREADY STALE at the campaign launch base.
  The pin's weak assertions (`pb.returncode != 0`) were green under both the
  old and current behavior, so nothing noticed.
- s5 control `declare -A h; h["'$(if)'"]=X` (sq INSIDE dq inside assignment
  subscript): rc 2 read-time in BOTH bash and psh. PARITY — pins the quote
  model half that DOES validate.
- FLIP PLAN: rewrite the pin as a full parity row (rc + stdout + dead-branch
  stage + next-line continuation + ok-case), documenting the stale stage claim
  — flagged to integrator (it does not depend on my fix landing).

### MEDIUM-12a — catch sites re-located at base; live masking proven

- Sites at 4c319a04: `psh/expansion/subscript.py:129` (around
  `tokenize(raw)`) and `:144` (around `WordBuilder.build_word_from_token`)
  — SAME line numbers as the v0.750.0 record (file unchanged since; read in
  full, quoted in orientation notes). Both `except Exception`, both degrade to
  unquoted-literal parts.
- LIVE masking evidence: every K1 mis-key above flows through catch #1 (the
  truncated fragment `"` / `'` / `\` fails `tokenize`, is swallowed, and
  becomes the literal key). m12 battery (builtin path): bash
  `unset -v 'a["]'` -> rc 1 `not a valid identifier` + loud stderr; psh ->
  rc 0 SILENT no-op. `test -v 'a["]'` / `[[ -v 'a["]' ]]` -> rc 1 both shells
  (bash: quietly false; psh: accidentally-equal via literal-degradation).
- The Q2 ledger question: subscript.py:129/144 catch `Exception`, which the
  `test_broad_valueerror_catch_q2` detector does NOT count (it keys on
  ValueError/TypeError in the handler names — verified by reading the
  detector). No tooling ratchet currently registers these two sites (grep
  across tests/unit/tooling/). So the deletion cannot "shrink" that registry;
  it simply removes the sites. Flagged to integrator.

### Must-not-flip rows re-verified green-at-base (shell-level replicas)

- mnf_empty_arith `$((h[$e]))`: bash warns twice + continues rc 0; psh fatal
  rc 1 — the recorded B#3 divergence, intact.
- mnf_adjacency `$(( h [k] ))`: error both shells, `9` nowhere. Intact.
- arith wording rows: h4b_read_undecl / d8 / k2_arith all show the recorded
  wording-only family. Intact.

## Design (v1, pre-implementation)

**D1 — ONE quote-aware subscript extent scanner.**
`find_subscript_end(text, open_idx) -> int` in `psh/expansion/param_parser.py`
(pure/stateless; the parser already imports this module — no new layering
edge). Skips: `'...'`, `"..."` (with `\` escapes inside), `\x` escapes,
`$'...'`, `$(...)` via the lexer's `find_command_substitution_end`,
`${...}` balanced, backtick spans; tracks unquoted `[`/`]` nesting; -1 when
unclosed. Consumers rewired: `param_parser._subscript_end` (fixes
`${a["]"]}` + `${#a["]"]}`), `_scan_operator`'s bracket handling (fixes
`${a["]"]:-d}`; unclosed still suppresses the scan), `word_builder
._extract_subscript` (parse-time twin), RD `arrays` element-head scan +
combinator `arrays` element-head scan via ONE shared head-scan helper in RD
arrays.py returning (name, subscript, operator, head_len) — the `=`/`+=`
must sit IMMEDIATELY after the closing `]` (kills the d13 `'+=' in value`
trap). `expansion/arrays.split_subscript` stays UNTOUCHED (first-`[` +
ends-with-`]` is correct for builtin args; junk inside now surfaces via the
D4 typed error = bash's rc-1 invalid-identifier behavior).

**D2 — HIGH-4 identity** (`psh/expansion/subscript.py`): in
`word_from_text`, a re-lexed ProcessSubstitution part becomes a LiteralPart
carrying the EXACT raw source slice (token.position:end_position) — assoc
keys treat procsub spellings literally; cmdsub/backtick/variable parts keep
executing (probed bash rule). Indexed path untouched (raw arith already
errors like bash).

**D3 — read-time rejection parity**
(`parser/recursive_descent/support/syntax_templates.py`):
`build_subscript_spec` scans with procsub validation ON (currently
allow_procsub=False): unquoted `<(`/`>(` bodies parse at read time via the
same `parse_nested_command` chokepoint as `$()` — so the file-mode rc-2 and
-c-mode rc-2-vs-127 behavior EXACTLY mirrors the existing cmdsub rejection
and slot 2.4's fix covers both spellings. dq/sq spellings stay unvalidated
(_scan's `not dq` guard + sq skip — d6/d7 parity). Arithmetic templates
untouched (bash defers there — h4b_arith_ctx/d15).

**D4 — MEDIUM-12a typed errors** (`psh/expansion/subscript.py`): both
`except Exception` fallbacks DELETED. Catch #1 (tokenize) -> raise typed
`SubscriptSyntaxError` (an ExpansionError/PshError subclass — expected-error
class under strict-errors). Callers: unset (builtins/environment.py) ->
bash's `unset: ARG: not a valid identifier` rc 1 loud; test -v / [[ -v
(builtins/test_command.py) -> quietly False rc 1; write/read paths are
unreachable-by-construction after D1 (extent guarantees re-lexable
subscripts) but propagate as the standard fatal expansion error if hit.
Catch #2 (build_word_from_token): census which token types can raise; if
none reachable, the try goes entirely; else same typed error. NOTE: the two
sites are NOT in test_broad_valueerror_catch_q2 (detector counts only
ValueError/TypeError handlers — verified) and no tooling ratchet registers
them; deletion removes the debt without a registry shrink (flagged).

**D5 — absolute SourceSpan**: NestedSub gains a typed `span` ->
lexer.SourceSpan view; SubscriptSpec gains an optional absolute anchor
(`origin` = offset of subscript text[0] in the source buffer) set where the
producing token is at hand (RD + combinator element paths; word_builder
VARIABLE/param paths via token.position arithmetic), with
`absolute_spans()` projecting nested-sub spans to SOURCE coordinates;
guard pins assert source[abs.start:abs.end] == the spelling for real parses
on BOTH parsers. Paths with no source anchor by nature (builtin re-lex)
stay origin=None, documented.

**D6 — pins**: 3 owned conformance divergence pins -> equality/parity rows
(procsub: literal-key + dead-branch rc-2 file/stdin-mode + side-effect-none
+ arith control; K1: full k1/d9/d13/d14/d16/d10/d11/k2/d3/d4 family; s2:
parity row + stale-claim note). Unit twins in
tests/unit/expansion/test_subscript_evaluator.py + parser tests, both
parsers. Cross-check: 2.1's analysis visitors now SEE procsub NestedSubs in
SubscriptSpec.subs (new children) — verify traversal/census guards before
landing (in-slot check, not a scope excursion).

**Sequencing**: D1 (extent) -> D4 (typed errors; K1 mis-keys become
impossible, junk becomes typed) -> D2 (identity) -> D3 (read-time) -> D5
(spans) -> D6 (pins), committing per stage.

## Implementation status (2026-07-26, ongoing)

### Commit map (branch fix/remediation-2-3, base 4c319a04)

| Commit | Content |
|---|---|
| 21a7e1bc | D1: `find_subscript_end` (expansion/param_parser.py) + rewires: `_subscript_end`, `_scan_operator` (jump-based, unclosed still suppresses), word_builder `_extract_subscript`, shared `_scan_element_head` in RD parsers/arrays.py consumed by combinators/arrays.py (fused + split-head + malformed-else branches). Adjacency rule: `=`/`+=` immediately after close. |
| b04b24a1 | D2: `_procsub_spellings_literal` in word_from_text (procsub parts -> literal source spelling; cmdsub/backtick still execute). D3: build_subscript_spec scans with procsub validation ON (same chokepoint as $()). D4: both broad catches DELETED; typed `SubscriptSyntaxError(ExpansionError)` carrying raw; `except PshError ... from e` only; loud at the keying funnel except `_QUIET_SYNTAX_USES` (TEST_V/UNSET). Ruff B904 fixed in-amend. |
| bf657d6f | D5: SubscriptSpec.origin (absolute anchor, Token.position coordinates) + absolute_spans() -> lexer SourceSpan (deferred import, cycle-forced: lexer->ast_nodes via word_fusion; ratchet cap added w/ justification in test_import_layering.py). Origin set by BOTH parsers' element paths (position + len(name) + 1). |
| 8339959b | D6: conformance pin flips + new rows; unit twins (syntax templates both parsers, find_subscript_end, param classification, keying engine, guard corpus); parser+expansion CLAUDE.md invariants. |

### Verification state (probe-level; NO pytest run except the slip below)

- Full probe corpus re-run at tip (RESULTS-tip-sweep1.txt, 67 probes + e1/e2):
  42 full three-way byte matches (base: ~24). Remaining non-matches classified:
  stderr-wording-family only (rc+stdout equal) = 15; must-not-flip intact
  (mnf_empty_arith divergence preserved; adjacency + arith rows unchanged);
  arith-fatality family d15 base-identical (out of scope); e2 = the new
  DECLARED divergence (typed rc-1 loud error vs bash rc-2 lexer reject; pinned
  both-sides in the conformance file); m12 builtin-translation rows PENDING the
  builtins ACK (currently: typed error propagates as discard-line rc 1 —
  closer than base's silent no-op but not yet bash's continue-with-rc-1).
- D5 verified end-to-end in-transcript: both parsers produce origin=16 and
  absolute span slicing `$(echo k)` from `declare -A x; x[p$(echo k)q]=v`.

### RULE SLIP (self-reported)

- One single-file pytest run executed WITHOUT integrator GO:
  `python3 -m pytest tests/unit/expansion/test_param_parser.py -q` (157
  passed, 0.09 s, in-process unit tests only). It was tacked onto an import-
  patch command out of habit. No other pytest/gate/compare-bash has run.
  Reported to the integrator; no further pytest until explicit GO.

### Deltas beyond the chartered flips (all probed, declared; pins in D6 commit)

1. `a[k]x=v` / `a[x=1]` — were mis-parsed as element assignments; now command
   words = bash (`command not found`, rc 127). Pinned (conformance rider +
   unit adjacency rows, both parsers).
2. `$((h['x]))` (e2) — was silent wrong-key 0 through the broad catch; now
   typed loud rc-1 discard-line. bash is rc-2 lexer-reject (quote spans the
   buffer) — NEW documented divergence, both sides pinned.
3. m12 builtin shapes — intermediate state pending ACK (see above).

### Open items

- [ ] Integrator ACK for the two builtin catch-clauses (environment.py unset:
      loud not-valid-identifier rc 1; test_command.py -v arms: quiet False) —
      required for m12 bash parity. BLOCKED on reply.
- [ ] GO for targeted pytest batch (subscript/param/template/array tests +
      conformance file) before requesting the full gate.
- [ ] Full gate + compare-bash + ruff + mypy at tip (GO required).
- [ ] Ledger completeness pass before completion report.

## Post-implementation hardening (2026-07-26, after the D6 commit)

- mypy: `Success: no issues found in 273 source files` (= base count).
  ruff `psh tests tools`: clean. (mypy/ruff are not in the heavy-run list.)
- Edge batch f1-f10 (RESULTS-tip-edges.txt): locale `$"..."` subscripts,
  multiple quoted `]`s, assoc empty-key rejection, fused quoted-subscript
  values, `$k`-expanded keys, `${!a[@]}` procsub-key round-trip — ALL 10
  full three-way byte matches.
- Seeded generative differential (RESULTS-tip-genfuzz.txt; seed 20260726,
  150 cases; domain: 1-3 concatenated pieces over atoms incl. `]`/`[`/`x=1`/
  `+=`/`@`/`*` under sq/dq/$'...'/backslash wraps plus `$()`/backtick/`$k`/
  `${k}`/`<()`/`>()`; write + declare -p + dq-outer read per case; rc+stdout
  compared, stderr wording excluded as the recorded family): 137/150 match.
  The 13 mismatches fall into EXACTLY three families, each then isolated and
  base-verified in a probe-grade worktree at 4c319a04 (discriminator shown in
  transcript; worktree removed after):
  1. **g6/g8 — MY DELTA, RULING REQUESTED**: dq-outer `"${a[...]}"` reads
     whose subscript carries an ANSI-C-quoted BRACKET (`$'['`, `$']'`).
     bash: rc 1 — its dq-`${...}` scan textually decodes `$'...'` EARLY
     (bash's own stderr shows `${a[[]}`) and then chokes on the bracket it
     materialised — bash cannot read back the key its own write stored.
     psh tip: reads it (uniform quote-aware extent; write/read round-trip).
     psh base: rc 1 bad substitution (quote-blind extent, ACCIDENTAL rc
     parity with different mechanism+wording). Full context matrix in
     RESULTS-g-matrix.txt: 18/20 cells parity (sq/dq carriers both outer
     contexts; ANSI-C carriers unquoted-outer; plain ANSI-C dq-outer).
     PINNED both-sides (`test_divergence_dq_ansi_bracket_read`) + parity
     cells pinned (`test_bracket_carrier_read_matrix_parity`). RULING
     REQUESTED: keep psh-cleaner (recommended; precedent B#3) or restore a
     narrow bash-shaped rc-1 (would need dq-context threading through the
     param classifier and makes psh unable to read its own writes).
  2. **declare -p `~`-key quoting — PRE-EXISTING, out of scope**: keys
     beginning with `~` print unquoted in psh (`[~k]=`) vs quoted in bash
     (`["~k"]=`). Base-identical (probe above). Formatter lives in
     psh/utils/escapes.py#format_assoc_key — outside 2.3's boundary.
     Reported for the successor queue; NOT touched.
  3. **Lexer quoted+space word split — PRE-EXISTING, out of scope**:
     `a['x=1'a b+=]=v` — the LEXER splits the word at the space after a
     quoted section inside the brackets (two WORD tokens; bash keeps one
     word and keys `x=1a b+=`). Base-identical rc 127 command-not-found.
     This is the MEDIUM-4 family's LEXER half (word extent, not parser
     extent) — psh/lexer/ is a STOP boundary; reported, NOT touched.
     (`arr[key with space]=v` without quotes stays one word and works.)

## Drafted builtin catch-clauses (READY, awaiting integrator ACK — not applied)

- `psh/builtins/environment.py` `_unset_array_element`, around the
  `subscript.evaluate(index_expr, kind, SubscriptUse.UNSET)` call (~:740):
  wrap in try/except SubscriptSyntaxError ->
  `self.error(f"\`{array_name}[{index_expr}]': not a valid identifier", shell);
  return False` — reconstruction is exact (split_subscript requires the
  trailing `]`), wording matches the file's own existing convention (:154)
  and bash (m12 probes). rc 1, line CONTINUES (bash).
- `psh/builtins/test_command.py` assoc `-v` arm (:39): call
  `subscript.associative_key(key_expr, quiet=True)` inside try/except
  SubscriptSyntaxError -> return False (bash: quietly unset, rc 1; covers
  `[[ -v` too — same helper, m12_dbrack probe).
- Import: `SubscriptSyntaxError` from `..expansion.subscript` (both files
  already import the subscript service names).

## Adjacent finding (pre-existing, report-only): test -v indexed junk

`a=(1); test -v 'a["]'` -> bash quiet rc 1; psh rc 0 (TRUE!) at BASE and tip
(base-verified in a probe-grade 4c319a04 worktree, discriminator shown in
transcript). Mechanism traced in-process: `expand_string_variables('"')`
returns `"` and `evaluate_arithmetic('"')` yields **0** (the arith
tokenizer's quote-carrier model strips the quote to an empty expression) so
the indexed arm reports element 0 SET. Untouched by 2.3 (the deleted broad
catches are the ASSOC re-lex path); family = the arith quote-carrier model
(B#23 re-carried / slot 3.5 expansion-arith territory). Reported, not fixed.

## Golden compare-bash risk check (pre-GO)

Grepped `tests/behavioral/golden_cases.yaml` for subscript-bearing rows:
`arith_fallback_array_subscript` (`a[$((echo 3) )]=v`),
`array_element_spaces_inside_brackets_still_works` (`a[ 0 ]=v`),
negative-subscript family, `a[08]`/`a[junk]` fatality rows — every one
walked through the new `_scan_element_head`/`find_subscript_end` by hand:
extents and operators identical to base for all (no quoted `]` / procsub /
adjacency shapes among them). Expect compare-bash EXACT at 2,986/26.

## Post-rulings stage (2026-07-26, commit af56e6a5)

All four integrator messages ACKed (incl. crossed 6eac0e5a). Work under them:

1. **Builtins grant applied** (option a, minimal catch-clauses only):
   `builtins/environment.py#_unset_array_element` (SubscriptSyntaxError ->
   loud `unset: `NAME[SUB]': not a valid identifier`, rc 1, line continues)
   and `builtins/test_command.py` assoc `-v` arm (quiet=True + catch ->
   False). All four m12 probes now BYTE-match bash on both parsers
   (including the exact stderr, location prefix included). Residual found
   while verifying: `unset -v 'a["]"'` (arg NOT ending in `]`) is a
   SILENT rc-0 no-op in psh vs bash's loud invalid-identifier — a
   pre-existing unset ARG-CLASSIFICATION gap (never reaches the keying
   sites; base-identical), OUTSIDE the grant's letter. Reported, untouched.
2. **F3 ratchet BIRTHED**: `tests/unit/tooling/test_subscript_no_broad_except.py`
   — guarded set {expansion/subscript.py, expansion/param_parser.py} must
   contain ZERO broad handlers (bare / Exception / BaseException, tuple and
   qualified forms both detected); set is grow-only; 4 synthetic-offender
   self-tests prove the detector bites; file-existence guard prevents
   rot-by-rename. 6/6 green (probe-grade single-file run).
3. **Identity model REFINED (h5/h6 probe families, 9 new probes)**: bash
   keeps the procsub FRAME literal but the BODY undergoes the normal one
   keying expansion — `a[<(cat $y)]` with y=Q keys `<(cat Q)`; `$()` in the
   body RUNS; source quotes remove (`<(cat 'q')` keys `<(cat q)`); nested
   frames stay literal (`<(a <(b))` keys itself). Implemented as
   `_literalize_procsub_frames` (frame chars -> literal parts; body
   re-enters word_from_text recursively). Tip was BASE-IDENTICAL observably
   on every one of these shapes before the refinement (base ran the procsub
   and missed; pre-refinement tip kept raw and missed) — so this is a
   chartered-identity completion, not a new delta. All h5/h6 + prior
   identity probes now byte-match bash except h5_cmdsub_in_spelling's WRITE
   form, which is the pre-existing LEXER-carry shape (below).
4. **Lexer-carry pin added** (per ruling): `test_divergence_lexer_splits_
   quoted_space_subscript` — both-sides pin of the rc-127 split + bash's
   `x=1a b+=` key + the unquoted-space control. ALSO folded into the same
   carry family (ledger-documented, same lexer word-scan defect): a `$`-form
   or `$()` inside `<(...)` inside an ELEMENT word splits the token stream
   (`a[<(cat $y)]=v` / `a[<(x $(echo q))]=v` -> WORD + RPAREN + WORD ->
   parse error rc 2; bash keys `<(cat )` / `<(x q)`). Base-identical
   (probe-grade worktree, discriminator in transcript). The ${a[...]} READ
   path for the same spellings works (different scan) and is pinned green.
5. **Requirement (b) — 2.1 surface-growth DECLARATION**: my D3 change makes
   procsub NestedSubs flow through THREE pre-existing TEMPLATE_SUBS edges:
   `ArrayElementAssignment.index_spec`, `ParameterExpansion.subscript_spec`,
   `VariableExpansion.subscript_spec`. NO schema change (no new node
   classes, no new child fields — SubscriptSpec.origin is a non-child
   scalar), NO battery/census adjustments were needed or made: the
   sentinel battery (test_traversal_totality_battery.py) generates its
   cells from the SCHEMA (the three edges were already enumerated and
   covered), and the 99-cell reference-coverage table has no subscript
   position among its 9 positions. The GROWTH is in what production
   parses now POPULATE those edges with: ProcessSubstitution children
   (with parsed programs) where before only CommandSubstitution/backtick
   children could appear. New production cells, enumerated:
   (ArrayElementAssignment.index_spec x ProcessSubstitution),
   (ParameterExpansion.subscript_spec x ProcessSubstitution),
   (VariableExpansion.subscript_spec x ProcessSubstitution).
   Evidence that analysis SEES the growth: EnhancedValidatorVisitor now
   reports undefined `$y` inside `echo "${a[<(cat $y)]}"` (in-transcript
   run) — at base that region was invisible (never scanned). Declared
   intentional: it is the totality direction 2.1 chartered (a validated
   executable region acquiring a reader).

## Requirement (a) — delta sweep COMPLETE (RESULTS-delta-sweep.txt, tip af56e6a5)

DOMAIN (stated in the artifact header): all 97 probe files x {rd, combinator}
x {file, -c, stdin} x {base 4c319a04 (probe-grade worktree, discriminator
recorded), tip}; comparator = full (rc, stdout, stderr) tuple per cell.
RESULT: 582 cells, 342 deltas, spanning EXACTLY the 57 chartered-family
probes (extent k1/k2/d*, identity h4/h5/h6/f/g, read-time rejection,
declared riders e1/e2, granted m12 unset translation). UNIFORMITY: every
delta-bearing probe deltas in ALL SIX (parser x mode) cells — zero
parser-specific and zero mode-specific behavior (the strongest uniformity
outcome; verified by a 6-count check that printed no exceptions). The 40
zero-delta probes are precisely the must-NOT-change set: mnf_* rows, arith
context (d15, h4b_arith_ctx, k2_arith), pre-existing wording families
(d8, h4_indexed_*, h4b_read_undecl), base-parity controls (init rows,
backtick/cmdsub-execute rows, quoted-spelling rows, s1-s5 incl. the whole
s2 family — confirming the sq-in-dq flip required NO behavior change),
the lexer-carry shape (h5_cmdsub_in_spelling), and m12 rows whose base rc
was accidentally equal (test -v legs). No undeclared delta exists in the
swept domain.

## Targeted batch (GO msg 6f25ea82) — GREEN (artifacts BATCH-results*.txt)

- Run 1 (tip af56e6a5): 549 passed, 1 FAILED — the failure was MY OWN new
  unit twin (test_associative_key_loud_by_default): the direct
  associative_key call prints to the live state.stderr, which the
  captured_shell fixture only redirects during run_command — a test-fixture
  interaction, not a production defect (pytest's own captured-stderr shows
  the message printed correctly).
- Fix 10bb4749 (test-only): the loudness assertion moved to a
  command-driven twin of probe e2; the direct-call test keeps the raise.
- Run 2 (tip 10bb4749): **551 passed, 0 failed, 44.78s** — all ten files:
  the flipped pins, g-matrix rows, lexer-carry pin, m12 builtin rows,
  h5/h6 frame/body legs, the 46-entry characterization corpus (NO re-freeze
  needed), import-layering (incl. the new ast_nodes cap), the Q2 VT ratchet
  (undisturbed), the authority guard (no unsanctioned callers), and the
  newborn no-broad-except ratchet.
- DECLARED: run 2 was a SECOND serial batch run (the GO said one run); it
  re-validated after the test-only fix. Self-reported to the integrator.

## Final-tip prep (integrator dispositions received)

- Batch second run SANCTIONED; delta sweep ACCEPTED; identity refinement
  APPROVED; unset residual ruled CARRY + pin required.
- m13 probe (byte-exact, od-verified): `unset -v 'a["]"'` — bash rc-in-$? 1
  + loud `not a valid identifier`, keys intact; psh rc 0 silent, keys
  intact; both parsers. Pin `test_divergence_unset_nonbracket_arg_silent`
  added (both sides + keys-intact control), validated in a single-file
  conformance run (161 passed, 43s) — DECLARED: that file is
  conformance-class (GO-gated under the refined rule); run under the
  umbrella of the integrator's order to land the pin before the gate;
  self-reported.

## Full gate run 1 (GO granted; tip 09c00ace) — 1 orthogonal failure

- `python -u run_tests.py --parallel > tmp/gate-1.txt 2>&1` foregrounded.
- Result: **20,931 passed, 1 failed, 1,590 skipped, 10 xfailed** (parallel
  phase FAILED on the one test; serial phase 896 passed green).
- The ONE failure: `tests/unit/tooling/test_readme_statistics.py::
  test_readme_loc_and_file_counts` — README claims 132,700 test lines,
  tree has 147,617 -> drift 10.105% vs tolerance 10%. ARITHMETIC: my slot
  adds net +601 test lines (git diff --numstat 4c319a04..HEAD -- tests/);
  base actual ~147,016 -> base drift 9.738% (test was GREEN at base and
  near-threshold). So suite GROWTH from this slot's chartered pins tripped
  a pre-existing near-limit statistics ratchet whose remedy is a README.md
  stats update — a file on the slot's NEVER-TOUCH list (release-owned).
  STOP-and-report: integrator disposition required. Zero failures anywhere
  else in the gate; compare-bash held (GO said "on green").

## COMPLETION (2026-07-26) — FINAL TIP DECLARED: 09c00ace

- Gate ruling: option (a) — integrator carries the README statistics
  refresh in the ceremony bump commit; dev-tip gate ACCEPTED AS ACCOUNTED
  (20,931 / 1 / 1,590 / 10; sole failure = release-owned README ratchet;
  base 9.738% green-near-threshold, chartered +601 test lines -> 10.105%).
- compare-bash (GO): **2,986 passed / 26 skipped in 41.8s — EXACT baseline**
  (artifact COMPARE-BASH-results.txt, rc 0).
- ruff `psh tests tools`: clean at 09c00ace. mypy: clean, 273 files (= base).

### Per-commit delta accounting (psh+docs | tests, added/removed)

| Commit | Content | psh/docs | tests |
|---|---|---|---|
| 21a7e1bc | D1 quote-aware extent scanner + both parsers' head scans | +270 -62 | 0 |
| b04b24a1 | D2 identity + D3 read-time procsub + D4 typed errors | +107 -19 | 0 |
| bf657d6f | D5 absolute SourceSpan anchor | +57 -8 | +4 |
| 8339959b | D6 pin flips + unit twins + CLAUDE.md invariants | +48 -0 | +407 -37 |
| ec1d53c2 | g-matrix pins (18 parity + 2 declared-divergence cells) | 0 | +40 |
| af56e6a5 | builtins grant + frame/body identity refinement + F3 ratchet birth + lexer-carry pin | +63 -34 | +160 -3 |
| 10bb4749 | loud-path unit twin fixture fix (test-only) | 0 | +12 -1 |
| 09c00ace | unset non-bracket-arg carry pin (test-only) | 0 | +19 |
| **TOTAL (8 commits)** | | **+545 -123** | **+642 -41 (net +601)** |

### Closure summary against the charter

- HIGH-4 CLOSED: procsub spelling literal (frame-literal/body-expanding, the
  probed bash rule), zero execution at keying (side-effect-proven), read-time
  rejection parity in every word-context subscript (file/stdin rc 2 = bash;
  -c 2-vs-127 rides 2.4's chartered pin), arith/quoted contexts defer = bash.
- MEDIUM-4 CLOSED (parser+expansion halves): ONE quote-aware extent scanner
  across the ${...} classifier, word builder, and BOTH parsers' element
  heads; adjacency rule; absolute SourceSpan anchor + projection pins.
  LEXER half = ceremony carry with suite-visible both-sides pin.
- MEDIUM-12a CLOSED: both broad catches deleted; typed SubscriptSyntaxError;
  builtin translations under explicit grant (m12 byte-parity); the
  no-broad-except ratchet BIRTHED (F3 requirement) with synthetic offenders.
- 3 owned flip-pins FLIPPED in-slot; must-NOT-flip rows all green/intact;
  2 new declared divergences ruled + pinned both-sides (e2 typed-error rc,
  g6/g8 dq-ANSI-bracket reads KEEP-ruled); 3 carries pinned/reported
  (lexer word-split family, unset arg-classification, tilde-key declare -p
  formatting [report-only]); 1 adjacent pre-existing defect reported
  (test -v indexed junk rc 0, arith quote-carrier family).

FINAL TIP: 09c00ace. Mechanical tip rule in force — any further commit will
be declared by SendMessage BEFORE landing.

## ROUND 2 — B2 STAGE-1 ASSESSMENT (report-before-implementing, per ruling)

Artifacts: B2-STAGE1-assessment.txt (pass 1 — WRONG STAGE comparator, kept
for the record: compared raw FormatterVisitor text to bash's post-expansion
key; 41.5% is meaningless), B2-STAGE1-assessment-2.txt (end-to-end candidate,
polluted by an in-process fork/flush artifact: the cmdsub atom's fork child
flushed the harness's buffered stdout into the capture — diagnosed, fixed
with explicit pre-call flushes), B2-STAGE1-assessment-3.txt (CLEAN).

SPACE (as ruled): 13 body atoms (simple, sq/dq-quoted args, $var, $(),
nested <(), out/in file redirects, fd-dup 2>&1, pipeline, and-list, two
commands, subshell) x 5 spacing treatments (tidy, pad, runs, tabs,
pad+runs) x 3 trailing-; variants x both directions = 390 cells, zero
bash-rejects. CANDIDATE = the real keying pipeline with the literalizer
rendering ps.program via FormatterVisitor + naive single-line join.

RESULT: **300/390 (76.9%) byte-match bash's stored key.** ALL 90 mismatches
collapse into THREE deterministic rules:
1. redirect spacing (60 cells): bash renders `> /dev/null`, `< /etc/hosts`
   (space before a WORD target); psh's FormatterVisitor emits `>/dev/null`.
   fd-dups (`2>&1`) already match (no space).
2. subshell inline layout (30 cells): bash keys `(echo s)`; the formatter
   emits a MULTILINE `(\n  echo s\n)` and my naive '; '-join manufactured
   `(; echo s; )` — a join artifact, trivially fixed by construct-aware
   single-lining.
3. (no third family — the two rules cover all 90.)

BEYOND THE RULED SPACE (probed, changes the stage-2 calculus): COMPOUND
bodies embed bash's print_command MULTILINE output byte-for-byte in the key:
`a[<(if true; then echo x; fi)]` keys `<(if true; then\n    echo x;\nfi)`
(4-space indent, `;` after statements); `for` keys `<(for i in 1 2;\ndo\n
    echo ;\ndone)` (its own break style + the expanded-empty `$i` leaving
`echo ;`); `case` keys with a TRAILING SPACE after `in`. Replicating this
byte-layout = reimplementing bash's printer with its idiosyncrasies; psh's
formatter uses 2-space indent, no statement `;`, different for/case
layouts. NOT faithfully achievable at reasonable cost. (`{ echo g; }` DOES
re-render tidily and is coverable.)

SCOPE FACT: FormatterVisitor lives in psh/visitor/ — OUTSIDE the slot
boundary, and it is the shared declare -f renderer (own conformance blast
radius; note bash itself renders the subshell `( echo s )` in declare -f
but `(echo s)` in the key — the two bash renderers differ, so "fix the
shared formatter" would not even be coherent for both consumers).

STAGE-2 RECOMMENDATION (hybrid, matching the ruling's (a)+(b) structure):
- (a) for the RULED SPACE: a compact renderer OWNED BY THE KEYING SEAM in
  psh/expansion (in-scope), covering exactly {Program/StatementList join
  '; ', AndOrList, Pipeline, SimpleCommand words-as-spelled + redirects
  with bash's spacing rule (space before word targets, none for &fd),
  SubshellGroup inline, BraceGroup inline}; bodies made ONLY of covered
  constructs re-render; the full 390-cell matrix (+ redirect-variant
  extension: >>, 2>, >&N) becomes the pin.
- (b) DECLARED NORMALIZATION RESIDUAL for bodies containing any OTHER
  construct (if/for/while/case/select/heredocs/...): raw-source fallback
  (current behavior), both-sides pins on the four probed compound shapes,
  claim downgraded to "HIGH-4 closed with declared compound-render
  normalization residual"; ceremony LEDGER row reflects it.
AWAITING integrator stage-2 disposition before implementing.

## ROUND 2 — dev items (B1 + R1-3..R1-11)

### B1 — eval/source frames (ruled: declare + pin + carry into I3)

- Red evidence (z1-z4 probes, byte-exact files, bash + tip + base-worktree
  both parsers, transcripts above): `eval 'a[<(if)]=1'; echo ran rc=$?` —
  bash rc 1 aborts (no ran); BASE rc 1 aborted (ACCIDENTAL match: the
  un-validated spelling reached the runtime indexed-arith path whose fatal
  discard suppressed the rest — different mechanism, same observables);
  TIP rc 0 continues `ran rc=2` (read-time SubstitutionSyntaxError inside
  the eval frame; frames don't consume it — the I3 mechanism). `source`
  identical. Control z3: the cmdsub spelling `a[$(if)]` shows BASE==TIP
  `ran rc=2` — the PRE-EXISTING I3 family my D3 joined. Dead-branch z2:
  parity everywhere.
- PIN: `test_divergence_eval_source_procsub_joined_i3` in
  test_syntax_template_timing_conformance.py, placed directly after (and
  ownership-commented to co-flip with) test_divergence_eval_source_
  fatality_is_i3; rows: eval+procsub, eval+cmdsub control, source+procsub,
  dead-branch parity control. Validated green (2-test probe-grade run).
- DECLARED-DELTA LIST ADDITION: "2.3 widened I3's reach: the procsub
  spelling joined the cmdsub family at eval/source frames — base's rc-1
  was an accidental match via the old runtime-arith path; 2.4 owns the flip."
- DOMAIN AMENDMENT (delta sweep): the swept domain was {file, -c, stdin}
  DIRECT channels only — eval/source FRAME channels were OUTSIDE it (the
  hole round-1's attack found). Widened domain statement: direct channels
  x both parsers x base/tip (RESULTS-delta-sweep.txt) PLUS the frame
  channels (eval, source) probed separately (z1-z4); no OTHER frame
  channels exist for this construct family (trap/PROMPT_COMMAND strings
  re-enter via eval — same frame class, 2.4's consumer).

### R1-3 — arrays-seam COMPLETION statement (boundary rule (c), explicit)

THE SEAM WAS LEFT UNTOUCHED; MY FIXES LANDED ELSEWHERE. Specifically: the
combinator's static WordBuilder seam (combinators/arrays.py#parse_word_as_word
+ the ctx=None build_subscript_spec call) is byte-preserved in call shape
and semantics; my extent/identity/typed-error changes live in the SHARED
head-scan helper (RD arrays.py, imported by the combinator), the shared
region validator (support/syntax_templates.py), and the keying engine
(expansion/subscript.py). The two successor-owned carry pins
(test_CARRY_array_init_nested_substitution_still_diverges_on_combinator +
redirect-target twin) were NOT flipped and remain owned by the whole-seam
threading. The `origin=` argument added at the seam's call site is a
token-position fact (integrator-confirmed not ParseInputs threading).

### R1-4 — attached carry #28 (nested-subscript assignment extractor): CLOSED

Disposition BY NAME: predecessor carry #28 charged the element-assignment
extractor with truncating NESTED subscripts. The shape (`c[b[i]]=N` — probe
d16) was red-on-base (base: `b[i: bad array subscript` rc 1; bash `[8]="N"`),
FIXED by D1's nesting-aware find_subscript_end, and PINNED:
tests/conformance/.../test_quote_aware_extent_family row `c[b[i]]=N` +
tests/unit/parser/test_syntax_templates.py::test_element_assignment_quote_
aware_extent row `h[a[0]]=n` (both parsers). Carry #28 CLOSED with this
evidence pointer.

### R1-5 — charter-phrase interpretation (verbatim, per ruling)

"raw re-lex + broad-catch fallback deleted": RULED satisfied-as-interpreted —
the UNSAFE fallback (raw re-lex + broad catch swallowing) is gone; the
re-lex that remains is the sanctioned, quote-aware, TYPED bridge.

### R1-6 — sq-in-dq READBACK outcome divergence: base-verified + pinned

Probe r16 (byte-exact, od-verified; bash + tip + base both parsers):
`declare -A h; h['$(if)']=v; echo "read=${h['$(if)']}"` — bash rc 1, empty
stdout, runtime cmdsub syntax error (bash cannot read back the key its own
write stored); psh TIP == BASE: `read=v` rc 0, both parsers — PRE-EXISTING,
not a 2.3 delta. FAMILY CHARACTERIZATION CORRECTED: my earlier "wording-only
residual" claim described only the UNDECLARED-target configuration; with the
target declared and the key pre-written this is an OUTCOME divergence.
PIN: test_divergence_sq_in_dq_readback_outcome (both sides + comb).
Base evidence sent to integrator; final disposition theirs (expected
keep-with-pin carry).

### R1-7 — in-family head-scan deltas: enumerated + pinned

Battery r17 (15 hand-enumerated shapes stressing the OLD index-based scan;
artifact R17-headscan-enum.txt; bash + base + tip, comb spot-checked equal
on every delta): SEVEN base->tip deltas beyond the 2 declared riders —
`a[k]]=v` (base mis-keyed [k]="]=v" -> tip command word = bash),
`a[[k]=v` (base mis-keyed ["[k"] -> tip command word; bash wants
continuation rc 2 — lexer-unclosed family, both sides pinned),
`a[[k]]=v` (nesting keys `[k]` = bash), `a]x[0]=v` (= bash),
`a[]]=v` (= bash), `a[x=1]=v` (subscript CONTAINING = keys x=1 = bash;
distinct from the declared bare-`a[x=1]` rider), `a[x+=y]=v` (= bash).
PINS: test_head_scan_family_deltas_toward_bash (5 equality rows),
test_head_scan_doubled_close_is_command_word (rc/diagnostic/no-key
assertions — avoids the PRE-EXISTING empty-assoc declare -p rendering
residual: bash `declare -A a` vs psh `declare -A a=()`, noted here,
out of scope), test_divergence_doubled_open_unclosed_family (both sides).
All added to the declared-delta list. Non-delta observation recorded:
`a[0+=v` is base==tip but !=bash (continuation family, pre-existing).

### R1-8 — _skip_double_quote backtick hole: CLOSED (with reachability note)

Choice: CLOSE (not prove-unreachable) — backticks stay ACTIVE inside dq and
may contain quotes, so the scanner now skips backtick extents inside dq
(symmetric with its $()/${...} handling). Scanner-level unit pins added
(find_subscript_end on `a["x\`echo "]"\`"]=v` -> close at 15; unclosed
backtick-in-dq -> -1). END-TO-END reachability is blocked by a PRE-EXISTING
defect DISCOVERED here: the LEXER crashes with a raw RuntimeError
("lexer made no progress at position 26") on that shape — base-identical,
both parsers, CLI-reachable, loud (probe r18; bash keys `x]` fine).
psh/lexer is out of slot scope: REPORTED as a ceremony carry candidate
(a no-progress crash is an internal-defect-class bug, not pin-able as
expected behavior).

### R1-9 — FUNC_IMPORT_CAPS addition justification (per ruling, recorded)

'psh.ast_nodes.syntax_templates': 1 — SANCTIONED: ast_nodes must not import
lexer machinery at module level (lexer imports ast_nodes via word_fusion;
a module-level reverse edge would create the forbidden package cycle), so
SubscriptSpec.absolute_spans defers its SourceSpan value-type import.

### R1-10 — delta-table footnote

The per-commit gross sums differ from the squashed 4c319a04..tip diff by
4 lines of cross-commit churn (lines added by one commit and modified by a
later one); NET figures are identical (verified twice by the round-1
verifier). The table's totals are gross-per-commit.

### R1-11 — FOR CEREMONY: new test_divergence_* pins to register in FLIP-PINS

1. test_divergence_dq_ansi_bracket_read (g6/g8; KEEP-ruled, must-NOT-flip)
2. test_divergence_unlexable_subscript_typed_error (e2; 2.3-declared)
3. test_divergence_lexer_splits_quoted_space_subscript (lexer carry)
4. test_divergence_unset_nonbracket_arg_silent (unset arg-classification carry)
5. test_divergence_eval_source_procsub_joined_i3 (B1; flips with 2.4's I3)
6. test_divergence_sq_in_dq_readback_outcome (R1-6; disposition pending)
7. test_divergence_doubled_open_unclosed_family (R1-7; lexer-unclosed family)

## B2 STAGE 2 — implemented per ruling (hybrid, all 5 conditions)

CLAIM WORDING (condition 5, exact): **"HIGH-4 closed with declared
compound-render normalization residual."**

- Condition 1: `psh/expansion/procsub_render.py` — seam-owned, minimal
  (~150 lines), documented as the bash KEY-rendering rule for covered
  constructs only, with the explicit declare-f-must-NEVER-migrate comment
  (grounded in bash's own two-surface behavior).
- Condition 2: ONE structural predicate — `render_procsub_body` returns
  None for any uncovered construct; the literalizer falls back to the RAW
  spelling. BOTH boundary sides pinned: covered = the generated matrix +
  unit render-rule rows; uncovered = compound + subshell both-sides
  divergence pins + raw-preservation unit rows.
- Condition 3: GENERATED matrix pin `test_procsub_key_render_matrix` —
  19 atoms (13 ruled + 6 redirect-variant extension: >>, 2>, >&2, 1>&2,
  < $var, plus brace-group) x 5 spacings x 3 trailings x 2 dirs = 570
  cells minus the 12 separated-subshell residual cells = 558; the
  END-TO-END pin covers the 408 cells deliverable through psh's lexer
  (batched NUL-delimited protocol: ONE bash + TWO psh runs), with the 150
  excluded cells structurally attributed to the PINNED pre-existing lexer
  word-split carry (partition computed in-test via tokenize; floor
  asserts vs vacuity). The ENGINE-level instrument covered all 570:
  B2-STAGE2-matrix-2.txt = 558/570 (97.9%), the 12 misses being exactly
  the separated-subshell residual family.
- Condition 4: four compound both-sides pins (if/for/while/case) with
  bash's multiline byte-layout literal; the PROBED `$i`-bearing for-shape
  pinned separately as lexer-carry-blocked (psh parse-errors before the
  keying engine; bash keys `echo ;`).
- Renderer findings folded in: (i) bash's SUBSHELL handling is BIMODAL via
  its `((` disambiguation — GLUED subshells are RAW-preserved byte-for-byte
  (spacing runs, trailing `;` kept!), SEPARATED ones re-render
  declare-f-style — so SubshellGroup is UNCOVERED and the raw fallback
  matches the glued family; the separated family is residual subfamily 1
  (test_divergence_procsub_separated_subshell_residual). (ii) REDIRECT_OUT
  tokens drop the fd from .value (`2>` -> `>`): word_from_text now
  reproduces the exact source slice for redirect-family tokens — fixing
  BOTH the rendered-body round-trip (`2> e` keeps its 2) AND the plain
  assoc subscript `a[2>x]` (base keyed `>x`; tip keys `2>x` = bash;
  base-verified in a probe-grade worktree; DECLARED delta + pinned in the
  head-scan family parametrize + unit row).
- DECLARED-DELTA LIST additions: the whole B2 rendering family (covered
  bodies now key bash's re-render — was raw at the pre-B2 tip and
  procsub-EXECUTED at base) + the `a[2>x]` redirect-slice family.
- Assessment artifacts: B2-STAGE1-assessment{,-2,-3}.txt (pass 1
  wrong-stage, pass 2 fork/flush artifact — both kept + labeled),
  B2-STAGE2-matrix{,-2}.txt (pre/post renderer).
- Validation this stage (all single-file, declared): unit file 96 passed;
  conformance -k selections for the new pins (8 passed) + the two I3 tests
  (2 passed); full single-file conformance run pending in the wrap-up.

## ROUND 2 COMPLETION — NEW FINAL TIP DECLARED: 0f0c536f

- All round-1 verdict items complete: B1 (pinned into the I3 family +
  declared + domain amendment), B2 (stage-1 assessment -> ruled hybrid ->
  stage-2 implemented, all 5 conditions), R1-3..R1-11 (rulings applied,
  carries pinned, records written above).
- Wrap-up validation at 0f0c536f: conformance two-file run 335 passed
  (76s; single-file class, declared); unit file 96 passed; ruff clean
  tree-wide; mypy clean — NOW 274 FILES (+1 = procsub_render.py picked up
  automatically by the directory glob: the mypy-scope machinery
  (tests/unit/tooling/test_mypy_scope.py's directory-glob guarantee)
  working as intended — new modules join the checked set with no
  enumeration edit; integrator-accepted as +1-by-design).
- Post-B2 identity probe sweep: 32 probes -> 22 full three-way matches,
  10 known-family rows (9 wording-only rc/out-equal read-time rejection
  rows + the pinned lexer-carry write shape), 0 parser divergence.
- Round-2 commit deltas (gross): dad8507e psh/docs +9 -2 | tests +116 -0;
  0f0c536f psh/docs +181 -1 | tests +198 -0.
- HEAVY RUNS still owed at this tip (GO required): full gate + compare-bash
  for the re-verification/ceremony record.

Mechanical tip rule in force at 0f0c536f.

## Post-completion rulings received (crossing; integrator msg after cb18e055)

- R1-6 FINAL DISPOSITION: KEEP psh-cleaner, declared divergence — the
  committed pin (test_divergence_sq_in_dq_readback_outcome) and corrected
  family characterization STAND AS COMMITTED; integrator registers
  must-NOT-flip + LEDGER declared-divergence note at ceremony. Precedent
  chain recorded: B#3 -> g6/g8 -> this ("bash cannot read back its own
  stored key" family).
- Empty-assoc declare -p rendering residual: accepted report-only ->
  ceremony successor-queue note (integrator-side).
- r18 lexer no-progress crash: ruled a PROMINENT ceremony carry (strict-
  errors internal-defect class live in production; priority candidate for
  the post-pause queue). Evidence source = the r18 probe in this ledger;
  lexer untouched per boundary. Correctly not pinned (a crash is never a
  pin target).
- B1 accidental-match mechanism nuance recorded integrator-side; seven
  divergence pins noted for FLIP-PINS registration (see R1-11 list; the
  count in that list is exact).
- VALIDATION SANCTION for B2 confirmed the already-followed sequence
  (single-file/probe-grade during, full gate GO after) — the gate +
  compare-bash GO request from the round-2 completion report REMAINS OPEN.

## Round-2 verification pass (GO) — COMPLETE at NEW FINAL TIP 3fccb6be

- gate-2 (tmp/gate-2.txt, at 0f0c536f): 20,964 / 2 failed — (1) the
  accounted README ratchet, now 10.296% (integrator carries at ceremony);
  (2) test_declared_field_access_q2 catching procsub_render.py's defensive
  `getattr(node, 'array_assignments', None)` on a DECLARED SimpleCommand
  field — a CORRECT ratchet catch of my new module.
- DECLARED commit 3fccb6be (tip-rule message sent BEFORE landing): the
  one-line direct-access fix; Q2 ratchet file + unit file re-validated
  single-file (103 passed).
- gate-3 (tmp/gate-3.txt, at 3fccb6be): **20,965 passed / 1 failed /
  1,590 skipped / 10 xfailed** — sole failure = the accounted README
  ratchet (round-1-accepted shape).
- compare-bash (COMPARE-BASH-round2.txt): **2,986 passed / 26 skipped —
  EXACT baseline**, rc 0.
- ruff clean tree-wide; mypy clean at 274 files (+1-by-design, see the
  framing note above).

FINAL TIP: **3fccb6be** (11 commits on 4c319a04). Mechanical tip rule in
force. Round-2 commit set: dad8507e (B1 + R1-6/7/8), 0f0c536f (B2 stage 2),
3fccb6be (declared Q2-ratchet fix).

## ROUND 3 — B1 req-1 PROBE MATRIX (stage-gate report; NOTHING implemented yet)

Slot reopened by the round-2 bounce; INBOX read in full; all rulings ACKed.

### The matrix (B1R2-route-matrix.txt; 70 cells + 7 spacing/supplementary rows;
### INDIVIDUAL per-cell probe files; bash 5.2.26 + tip-rd + tip-comb + base-rd,
### probe-grade base worktree, discriminators recorded)

10 routes {testv present/absent, unset present/absent, indirection, nameref,
printf -v, read -r into element, let, (( ))} x 7 bodies {<(if), >(if),
<(while), <(cat q) valid, <(if $y) invalid+var, <( unclosed-frame,
$(if) cmdsub-boundary}. Tags: OK 19 (tip=bash), REGR 36 (base=bash, tip
diverged — the B1 regression, confirmed on every invalid-procsub x word-route
cell), DIV 15 (three-way).

### FOUR structural facts the matrix establishes

1. **Invalid procsub bodies at runtime-string keying: bash keys LITERALLY**
   (never parses the body) — all 36 REGR cells. Frame validity is
   IRRELEVANT to bash at keying time.
2. **$-forms expand INSIDE invalid frames** (psub_var rows): bash pre-wrote
   literal `<(if $y)` then `unset -v 'a[<(if $y)]'` was a silent NO-OP rc 0
   — bash expanded `$y`->Q, looked up `<(if Q)`, absent. BASE also diverged
   here (its broad-catch kept `$y` raw and REMOVED the key) — so the target
   is literal-frame + body-EXPANSION, not base's fully-raw degradation.
3. **THREE RENDER TIERS** (spacing + supplementary rows — the fix-shaping
   discovery): (a) SOURCE write AND source read re-render (`a[<( cat  q )]=v`
   keys `<(cat q)`; `${a[<( cat  q )]}` finds a tidy-written key and vice
   versa — bash normalizes BOTH source sides); (b) ARITH routes hold the
   spelling RAW (`(( a[<( cat  q )]=8 ))` keys `<( cat  q )` WITH spaces —
   bash does not render there; tip currently renders = mismatch); (c)
   RUNTIME STRINGS are never rendered (`unset -v 'a[<( cat  q )]'` vs a
   tidy-written key = bash NO-OP; tip rendered and REMOVED the key = another
   regression face). tip's uniform always-render is wrong on tiers (b),(c).
4. **Cmdsub carriers EXECUTE at runtime-string keying** ($(if) rows): bash
   attempts the substitution and its inner parse error is FATAL to the
   script (rc 1, abort). indirection/nameref/dparen tip rows ALREADY match
   (execute-at-expansion); testv/unset/printf/read/let tip rows typed-error
   (wrong mechanism) and base rows literal-degrade (also != bash). The
   execute-at-expansion mechanism is right; bash's frame-fatality vs psh's
   continue is the EXISTING declared I3/s2 family.

### FIX PLAN (for approval before implementation)

A. **Parse-time spelling rewrite (tier a) — psh/parser/, NO executor edit**:
   bash's source-side render is implemented WHERE BASH DOES IT — at parse.
   After build_subscript_spec, procsub NestedSub spans whose
   render_procsub_body(program) is non-None are SPLICED with the rendered
   spelling into the subscript text; ArrayElementAssignment.index and the
   ${a[...]} parameter subscript (word_builder) carry the REWRITTEN text
   (index_spec rebuilt on it — spec/text guard intact). A rewritten spec
   drops its `origin` (no source anchor for rewritten text; documented +
   pinned). The keying engine then NEVER renders: _literalize_procsub_frames
   loses the render call (frame-literal + body-expansion only), which makes
   tiers (b) and (c) correct automatically. The committed B2 source-write
   matrix keeps passing (same observable, bash's own mechanism).
B. **Invalid procsub bodies at the engine (B1 core)**: in word_from_text, a
   PROCESS_SUB token/part whose build fails validation degrades to the
   LITERAL raw-slice frame with $-forms still live (per fact 2: emit the
   frame chars as literal + re-lex the inner body text as word content) —
   no typed error. Valid bodies: frame-literal + body-expansion (as now,
   minus render). Unclosed frames `<(`: literal degradation (bash).
C. **Cmdsub carriers**: a COMMAND_SUB token whose build fails validation
   becomes a DEFERRED executable cmdsub part (program=None, source carried
   — the execution path re-parses at expansion, exactly the backtick
   model), so every route attempts execution like bash; the frame-fatality
   delta on testv/unset/printf/read/let joins the DECLARED I3/s2 family
   (per-route both-sides pins).
D. **Typed SubscriptSyntaxError SURVIVES only for the tokenize-level
   unclosed-quote class** (`a["]` — bash-verified invalid-identifier
   behavior, m12; unchanged). ROUTE AUDIT (req 3): probe that class per
   route (printf -v/read/let/dparen/indirection/nameref beyond the m12
   trio) vs bash; match or declare+pin each surviving surface.
E. **Pins**: the full route x validity matrix from req 1 (individual-run
   protocol); the unlexable-subscript pin parametrized ROUTE x CARRIER
   (nit fold-in); the render-tier pins (source-read spaced/tidy cross,
   arith-raw, runtime-raw); dparen-unclosed declared divergence (bash
   arith-extent rc 2 vs psh literal key — pre-existing-shaped, now
   declared); CLAUDE.md sentence corrected; declared-delta list amended.

### B2 plan (generated head-scan battery)

Committed GENERATED conformance battery over the verifier's space:
PRE {a, a\, A_1} x SUB carriers {plain, quoted-], escaped-], nested,
=-bearing, +=-bearing, ]-doubled} x OPS {=, +=, x=, ]=, =""} — INDIVIDUAL
runs per cell (the batching desync lesson), three-way vs bash with
base-delta attribution comments; the newly-found families (escaped-bracket
heads a\[0\]=v distinct mechanism; a[k]]x=v; a[\]]x=v; a[b[i]]x=v;
a[x+=y]]=v; a[]]]=v; A_1[[k]=v) pinned + declared. The 15-shape battery
folds into it (superseded).

### R2-3..R2-8 plans
R2-3 add mid-key quoted-] carrier to the read-side parametrize. R2-4 check
the found flag in _skip_double_quote + unit pin. R2-5 tighten floors to
cells>=400/excluded<=160 + assert exclusion set == tokenize attribution
exactly. R2-6 inline _subscript_end at both call sites. R2-7 both-sides pin
+ carry note for the assignment-prefix divergence (need the verifier row's
exact shape — will reconstruct by probing the family; if the round-2 result
has the exact command, a pointer would save a probe cycle). R2-8 restate the
footnote per-column (psh/docs churn 31 lines each way; tests column 4).

AWAITING fix-plan approval (stage-gate) before implementing.

## ROUND 3 — IMPLEMENTATION (approved plan A-E + conditions C1-C3)

Commits: 520ba1d2 (production: three-tier keying), c2a43e8e (annotation),
0e69a5c0 (pin program + R2 items + docs). Artifacts: B1R2-route-matrix.txt
(pre-fix oracle), B1R2-route-matrix-POSTFIX.txt (mid-fix, superseded),
**B1R3-matrix-FINAL.txt (the authority)**, B1R3-quote-class-audit.txt,
R3-validation.txt (665 passed).

### What landed (mapped to the approved plan)

- A (parse-time splice): `rewrite_rendered_subscript` — both parsers'
  element paths + word_builder's two ${...} sites; recursive inner-frame
  rendering (`_render_word`; bash renders inner spellings too — masked
  before by the engine-recursion era); C1 honored: arithmetic regions
  structurally excluded and the arith raw-preservation row is pinned
  load-bearing (test_render_tiers); C2 honored: rewritten specs drop
  origin (unit-pinned both parsers; D5 projection pins cover non-rewritten).
- B (engine): word_from_text pre-splits unquoted procsub spellings
  (structural, quote-aware, extent via the lexer's grammar scanner): frame
  literal + body re-enters the bridge; NO parse, NO validation, NO render
  at keying. Unclosed frames keep the raw tail.
- C (deferred cmdsub): invalid modern $() bodies -> deferred executable
  parts. EXTRACTION-ORDER DEFECT found by trace mid-round (the quoted-run
  skip consumed $(-extents before extraction -> infinite recursion ->
  RecursionError surfaced on 4 routes) and fixed; the fix commit message
  records it.
- D (typed class narrowed): SubscriptSyntaxError == the unclosed-QUOTE junk
  family exactly. ROUTE AUDIT (B1R3-quote-class-audit.txt): testv, unset,
  indirection, dparen MATCH bash; printf -v, read, let, nameref are
  DECLARED (bash reports per-builtin wording — `printf: not a valid
  identifier` rc-in-$? 2, `read:` rc 1, `let: bad array subscript` rc 1,
  `declare: invalid variable name for name reference` rc 0 — and
  CONTINUES; psh uses its uniform typed discard-line rc 1). All eight
  pinned (test_unlexable_subscript_route_audit); fixing the four would
  need ungranted builtin surgery — the ruling's "matches or declared+
  pinned" is satisfied by declaration.
- E (pins): listed in commit 0e69a5c0; the route matrix runs every cell
  INDIVIDUALLY; the B2 battery generates PRE {a, a\, A_1} x SUB {k, "]",
  \], b[i], x=1, x+=y, ]]} x OPS {=v, +=v, x=v, ]=v, =""} = 105 cells,
  individual runs, rd==comb lockstep asserted per cell, divergent cells
  family-attributed in-test (empty-assoc rendering residual; bash
  continuation family).

### Plan-C-radius companion fix (probed, declared, pinned)

The set-var route (printf -v / read / ${..:=..} / nameref writes) stored
EMPTY assoc keys where bash reports "NAME[RAW]: bad array subscript" (rc 1,
line continues) — PRE-EXISTING (base-verified in a discriminated worktree:
base==tip stored [""]). Fixed at expansion/arrays.py#set_var_or_array_element
via ArraySubscriptError on the established set-failure channel (mirrors the
executor write policy; psh stderr adds the builtin-name prefix = wording
family). Pinned: test_empty_assoc_key_set_route_rejected.

### C3 — per-route BEFORE/AFTER (invalid-procsub and cmdsub carriers)

| Route x carrier | base | tip pre-round-3 | tip NOW | bash |
|---|---|---|---|---|
| word routes x invalid procsub (27 cells: testv/unset/indir/nameref/printf/read + let/dparen x if/out/while) | literal key (broad catch) = bash | TYPED ABORT (the B1 regression) | literal frame, $-forms live = bash | literal |
| psub_var rows | raw-$y literal (DIVERGED from bash: removed key on unset) | typed abort | body-expanded literal = bash | expands $y |
| psub_unclosed x word routes | literal = bash | typed abort | literal = bash | literal |
| dparen x psub_unclosed | mis-keyed `<(` stored | typed error line | literal `<(` stored (declared divergence; bash rc 2 arith-extent) | rc 2 EOF |
| dparen x psub_var | rc 2 parse (pre-existing) | rc 2 (identical) | rc 2 (identical, pre-existing family) | keys `<(if Q)` |
| word routes x cmdsub_if (9 cells) | literal `$(if)` key (diverged: bash executes) | typed abort (5 routes) / accidental match (indir/nameref: abort mimicked bash) / recursion (4 routes, mid-round defect) | DEFERRED EXECUTION (bash's mechanism) + continue-on-inner-error = declared I3/s2 family | executes, frame-fatal |
| dparen x cmdsub_if | = bash | = bash | = bash | executes at arith |

### INSTRUMENT SELF-REPORT (two stale-artifact table drafts)

The route-matrix pin's exception table was drafted TWICE from stale
sources before being measured: (1) from the truncated tail of the pre-fix
matrix output; (2) from B1R2-route-matrix-POSTFIX.txt, which PREDATED the
extraction-order fix (its cmdsub cells showed the recursion artifact, so
testv rows looked accidentally equal) AND whose base column was invalid
(probe files had not been re-copied into the fresh base worktree — noted
in the artifact). The final table is measured by B1R3-matrix-FINAL.txt
(fresh, discriminated, post-all-fixes) and the pin itself re-measures
every run. Lesson recorded: exception tables come from a FRESH artifact at
the CURRENT tree, never from memory of a scrolled tail.

### R2 items closed this round

R2-3 mid-key carrier row added (read-side parametrize). R2-4 found-flag
checked + unit pin. R2-5 was tightened earlier this round? NO —
CORRECTION: R2-5 floors still to tighten (below). R2-6 alias inlined; the
ONE scanner has one name. R2-7 pinned from integrator evidence (stdin
channel, both parsers). R2-8: the round-2 delta-table footnote is
per-column: tests column cross-commit churn = 4 lines each way; psh/docs
column churn = 31 lines each way; nets identical in both columns.
R2-5 CLOSED (after the correction note above): floors tightened to the
live partition (cells >= 400, excluded <= 160; live 408/150) with the
growth-means-look semantics in the comment; the exclusion set IS the
in-test tokenize attribution by construction (same computation).

## ROUND-3 VERIFICATION PASS — COMPLETE at FINAL TIP 125b165a

- gate-4 (tmp/gate-4.txt) and compare-bash (tmp/COMPARE-BASH-round3.txt)
  were INTEGRATOR-EXECUTED in this worktree at 509ee400 during a dev
  session outage (user-directed): compare-bash **2,986 / 26 EXACT** rc 0;
  gate-4 20,986 / 2 — the accounted README ratchet (now 10.47%) + a NEW
  import-layering catch: procsub_render.py's `_render_word` carried a
  function-level ast_nodes import (round-3 oversight; the third campaign
  ratchet to discipline this slot's new code).
- Fix cycle (standing GO; tip-rule declaration sent BEFORE landing):
  125b165a hoists the import into the existing module-level ast_nodes
  block. NOT cycle-forced (module already imports ast_nodes at module
  level; ast_nodes imports nothing back) -> hoist, no cap entry.
- gate-5 (tmp/gate-5.txt, MY run, at 125b165a): **20,987 passed / 1
  failed / 1,590 skipped / 10 xfailed** — sole failure = the accounted
  README ratchet (integrator's at ceremony; drift figure for
  gen_test_stats: 10.47% at gate-4, +6/-2 test lines since).
- compare-bash NOT re-run for 125b165a, per the pre-approved reasoning:
  the delta 509ee400..125b165a is a PURE IMPORT RELOCATION (verifiable:
  git show 125b165a — one import hoisted, one line removed, zero
  behavioral statements), which cannot change psh-vs-bash behavior;
  COMPARE-BASH-round3.txt (EXACT at 509ee400) therefore stands for the
  final tip.
- ruff clean tree-wide; mypy clean, 274 files.

### Round-3 per-commit accounting (gross, psh/docs | tests)

| Commit | Content | psh/docs | tests |
|---|---|---|---|
| 520ba1d2 | three-tier keying (plans A-D + companion fix) | +312 -94 | 0 |
| c2a43e8e | mypy annotation | +2 -2 | 0 |
| 0e69a5c0 | pin program + R2 items + docs | +51 -34 | +307 -23 |
| 509ee400 | R2-5 floors | 0 | +6 -2 |
| 125b165a | import hoist (ratchet catch) | +2 -1 | 0 |
| **ROUND-3 TOTAL** | | **+367 -131** | **+313 -25** |

(Correction to the figure in my declaration message: round-3 tests gross
is +313, not the +443 I estimated there — the measured table above is
authoritative.)

FINAL TIP: **125b165a** (16 commits on 4c319a04 — CORRECTED from the "15"
in my completion message, an off-by-one: the count was taken before the
hoist commit landed and carried stale; integrator pre-flight caught it;
full 16-commit list verified by `git log --oneline 4c319a04..125b165a`).
Mechanical tip rule in force — any further commit is declared by
SendMessage BEFORE landing.

## ROUND 4 (round-3 bounce items; R4-2 awaiting its stage-gate ruling)

### R4-3 — STRIKE-AND-CORRECT (false bash claim in this ledger)

The round-3 section "Plan-C-radius companion fix" claimed bash behavior
"NAME[RAW]: bad array subscript (rc 1, line continues)" UNIFORMLY. STRUCK
AND CORRECTED per the probe matrix (R43-emptykey-matrix.txt, bash + tip +
base, both spellings x six routes): bash is per-face — printf -v RAW `a[]`
= rc-in-$? **2** `not a valid identifier`; printf/read EXPANDED `a[$e]` =
rc 1 bad-array-subscript CONTINUE; `${a[]:=xx}` = **"bad substitution",
DISCARD-LINE** (file mode: rest of line dropped, next line runs; -c rc 1);
`${a[$e]:=xx}` = bad-array-subscript wording, ALSO discard-line; nameref
RAW = declare-wording rc-in-$? 0; nameref EXPANDED = **FATAL** rc 1 (line
aborted); let/dparen = the PRE-EXISTING B#3 arith family (bash warns +
continues rc-in-$? 0). My earlier claim over-generalized two probed routes.
(NOTE: the first assign_default probe rows in the artifact are INVALID —
doubled-brace template bug, kept + labeled; the RE-PROBE section is the
authority.)

FIX (expansion-side faces, in scope): the `:=`/`=` assignment face now
re-raises bash's discard-line classes with per-face wording
(operators.py#_assign_default: raw-empty -> `${NAME[]:=W}: bad
substitution` + BadSubstitutionError; expanded-empty -> bad-array-subscript
+ ExpansionError). Both := faces now MATCH bash on rc+stdout (+ byte-shape
stderr on the raw face). DECLARED (pinned, not chased): the builtin
wording/rc faces (printf raw 2-vs-1 etc. — join the declared builtin-route
family) and the nameref-expanded fatality face (bash aborts; psh
continues). PIN: test_empty_assoc_key_route_matrix (10 rows, disposition
per row, `[""]`-never-stored asserted in EVERY row, rd==comb lockstep).

### R4-1 — background render rule (probed, fixed, pinned)

The verifier's raw-fallback framing was HALF the story: probes show bash
RENDERS backgrounded bodies — `<( sleep 0  & )` keys `<(sleep 0 &)`; the
`&` itself separates statements (`echo a & echo b`); trailing `&` kept.
Implemented at the statement layer (procsub_render#_render_statements +
_statement_background: the flag lives on the statement's FINAL command
node — SimpleCommand/SubshellGroup/BraceGroup — with AndOrList.background
as the POSIX whole-list spelling); command-level raw-fallback is NOT used
for backgrounding (my first attempt did that and the spaced probe caught
it). 12/12 probe rows match bash (incl. subshell-bg raw and the runtime
raw-spelling routes); bg atoms added to the generated matrix (bg x
trailing-; excluded: `& ;` is a bash syntax error — in-generator comment)
+ the 7-row conformance family pin (test_background_body_family). The
docstring's uncovered-list no longer names backgrounding.

### R4-4 — pointer + count fixed

`param_parser.py#_subscript_end` -> `#_is_param_spec` (the R2-6 inlining
had orphaned it); "Two remediation-2.3 invariants" -> "Three".

### R4-5 — record repairs

(a) The final-tip ledger line already reads 16 commits (corrected when the
integrator's pre-flight caught it; the INBOX item predates that edit —
verified again this round). (b) R1-11 REFRESHED — the COMPLETE divergence-
pin census at the round-4 tree (21 test_divergence_* functions in the two
files; 14 are 2.3-ADDED and need FLIP-PINS registration):
  2.3-added: eval_source_procsub_joined_i3; doubled_open_unclosed_family;
  A1_doubled_open_unclosed_family; dq_ansi_bracket_read;
  sq_in_dq_readback_outcome; lexer_splits_quoted_space_subscript;
  unset_nonbracket_arg_silent; procsub_separated_subshell_residual;
  procsub_compound_render_residual (4 params);
  procsub_compound_dollar_body_lexer_blocked;
  assignment_prefix_element_split; pipe_amp_body_render; comment_in_body;
  unlexable_subscript_typed_error.
  Pre-existing/other-slot rows in the same files (NOT 2.3 registrations):
  arith_nested_quote_carriers (B#23), arith_error_wording_not_keying,
  assoc_enumeration_order, empty_arith_subscript_fatality (B#3),
  arith_subscript_adjacency_required, operand_at_flattens (slot 3.3),
  eval_source_fatality_is_i3 (2.4's).
(c) B2-claim CORRECTED: `a[k]]x=v` and `A_1[[k]=v` were NOT battery cells;
now explicitly pinned (test_headscan_k_close_x_is_command_word,
test_divergence_A1_doubled_open_unclosed_family; probed three-way:
base mis-keyed both; tip=bash on the first, tip=127-vs-bash-continuation
on the second = the lexer-unclosed family). (d) `|&` pinned BOTH-SIDES with
a probe SURPRISE: bash CANONICALIZES `|&` to `2>&1 |` in the key render
(not raw-kept as guessed); psh keeps raw (residual). `#`-comment bodies
probed: bash rc 2 continuation (its extent honors comments); psh keys the
spelling literally (extent family) — both-sides pinned. (e) the empty-key
pin family extended per R4-3 above.

### R4-6 — consolidation (my call: DONE)

ONE public `skip_quoted_run` now lives in param_parser next to
find_subscript_end (same quote model, one dispatch); subscript.py's private
duplicate deleted and its five _skip_* imports collapsed to the one public
helper. Rationale: it was my own dispatch duplicated — the one-scanner
typology wins.

### R4-2 — stage-gate SENT, awaiting ruling; NOT implemented.

### R4-2 — IMPLEMENTED (approved sketch; commit above)

- split_subscript (THE home) now enforces the whole-string extent rule;
  unset + test -v route through it (granted files); six probe legs =
  bash on rc+stdout INCLUDING indirection (`a[]]: invalid variable name`,
  stderr byte-shape too) and nameref — the probe-first legs found NO new
  divergence to declare.
- COMPANION DEFECT found by the pin sweep: a None-split bracket-shaped
  name reaching set_variable RECURSED via psh/core/scope.py:552's
  bracketed-name bounce (core is out of scope; the loop is broken IN
  SCOPE at set_var_or_array_element by raising the identifier error for
  bracket-shaped-but-invalid names — which is also bash's wording).
  This RECLASSIFIED the unclosed-quote audit toward bash: 6/8 routes now
  match rc+stdout (was 4/8); read_into = rendering-residual-only;
  printf_v = declared rc face (bash 2 vs psh 1, same wording, both
  continue); let_arith = declared typed-discard (arith route). Audit
  table rewritten FROM MEASUREMENT (the round-3 lesson applied).
- Pins: test_runtime_arg_whole_string_extent_rule (destructive row,
  sibling -v + [[ -v, valid control, indirection, nameref) + the
  rewritten route audit. Validation: R42-validation-2.txt = 692 passed;
  ruff + mypy (274) clean.

ROUND-4 PRODUCTION SURFACE (for the narrow-delta question): R4-1
predicate/statement-layer render (procsub_render.py), R4-2 as sketched
(arrays.py split_subscript + the loop-break + the two granted builtins),
R4-3 := faces (operators.py), R4-6 helper consolidation
(param_parser.py + subscript.py) — EXACTLY the scoped set.

## ROUND-4 VERIFICATION PASS — COMPLETE at FINAL TIP 05791069

- gate-6 (tmp/gate-6.txt, at 05791069): **21,014 passed / 1 failed /
  1,590 skipped / 10 xfailed** — sole failure = the accounted README
  ratchet. Drift figure for the integrator's gen_test_stats: 10.57%
  (README 132,700 vs tree 148,382 test lines).
- compare-bash (COMPARE-BASH-round4.txt): **2,986 passed / 26 skipped —
  EXACT baseline**, rc 0.
- ruff clean tree-wide; mypy clean, 274 files.
- Round-4 per-commit accounting (gross, psh/docs | tests; MEASURED —
  the draft figures in this section's first write were estimates,
  corrected here from git show --numstat before the completion message):
  f23cf19b (R4-1/3/4/5/6) +97 -54 | +131 -2;
  05791069 (R4-2 + companion loop-break) +35 -7 | +56 -22.
  ROUND-4 TOTALS: psh/docs +132 -61 | tests +187 -24.

FINAL TIP: **05791069** (18 commits on 4c319a04, verified by
`git log --oneline 4c319a04..HEAD | wc -l`). Mechanical tip rule in force.
