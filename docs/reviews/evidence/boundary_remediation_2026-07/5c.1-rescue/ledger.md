# Slot 5C.1 — typed errors + boundary signatures — DEV LEDGER

- **Base:** `d0956bed` (v0.776.0 + 5B.2 addendum). Branch `fix/remediation-5c-1`,
  worktree `/Users/pwilson/src/psh-r5c-1`. Verified at first turn:
  `git rev-parse HEAD` → `d0956bed36ab766ee05d0f0f13d121c9ce617b90`;
  `git status --porcelain` → only `?? INTEGRATOR-INBOX.md`.
- **Brief:** `/Users/pwilson/src/psh/tmp/remediation-ledgers/briefs/5c.1.md`,
  md5 `ef2be2b93304d8452031f664c42cc985` — **matches R0's declared md5 exactly**
  (`md5 -q`, verified before reading a line of it).
- **Import discriminator asserted (memory gotcha: the editable install resolves
  to MAIN):** from this worktree
  `python -c "import psh, os; print(os.path.dirname(psh.__file__))"` →
  `/Users/pwilson/src/psh-r5c-1/psh`. From `$HOME` the SAME command resolves to
  `/Users/pwilson/src/psh/psh`. Therefore **every** driver in this slot sets
  `PYTHONPATH` explicitly and asserts the resolved path in-process before
  measuring, and every instrument takes ROOT from `argv` (CR-D5 portability).
- **Bash oracle asserted:** `which bash` → `/opt/homebrew/bin/bash`,
  `GNU bash, version 5.2.26(1)-release (aarch64-apple-darwin23.2.0)`.
  Never `/bin/bash`; recorded in every probe transcript.
- **Phase A status:** IN PROGRESS. No production file modified —
  `git diff` is EMPTY (re-asserted at every ledger append).

## Phase A — instrument manifest (running)

Instruments are FILES under `tmp/w5c1-instruments/` from the start. Committed
instruments under `docs/reviews/evidence/` are READ-ONLY: they were **copied**
(`*_COPY.py`, byte-identical — no edit at all was needed, both already take
ROOT from `argv[1]`), never edited in place.

| # | File | What it measures |
|---|---|---|
| — | `06_broad_except_ast_COPY.py` | READ-ONLY copy of `checkpoint-r/instruments/q5/06_broad_except_ast.py` (byte-identical) |
| — | `05_sig_census_COPY.py` | READ-ONLY copy of `checkpoint-r/instruments/q5/05_sig_census.py` (byte-identical) |
| — | `00_discriminator_COPY.py` | READ-ONLY copy of the CR import discriminator |

Transcripts: `A1_broad_except_BASE_d0956bed.out`,
`A2_sig_census_BASE_d0956bed.out`.

---

## A1. Census reconciliation at base — BOTH RECONCILE EXACTLY

`06_broad_except_ast_COPY.py` at `d0956bed`
(→ `tmp/w5c1-instruments/A1_broad_except_BASE_d0956bed.out`):

| Figure | Brief / CR tip | Base `d0956bed` | Verdict |
|---|---|---|---|
| `except Exception` handlers | 24 | **24** | RECONCILES |
| bare `except:` handlers | 0 | **0** | RECONCILES |

`05_sig_census_COPY.py` at `d0956bed`
(→ `tmp/w5c1-instruments/A2_sig_census_BASE_d0956bed.out`):

| Figure | Brief / CR tip | Base `d0956bed` | Verdict |
|---|---|---|---|
| total defs | — | 3,245 | (context) |
| Method A incomplete | 648 | **648** | RECONCILES |
| Method B denominator | — | 2,920 | (context) |
| Method B incomplete | 488 | **488** | RECONCILES |

Method A by package at base: interactive 102, parser 87, expansion 78, core 75,
executor 69, io_redirect 68, visitor 53, builtins 49, scripting 28, utils 17,
lexer 11, ast_nodes 8, (top) 3. Sums to 648 (derived, not hand-tallied).

### A1.1 Handler LINE drift vs the brief's CR-tip list — 4 lines, 3 files, sourced

The SET OF FILES and the COUNT are identical; four line numbers moved between
the Checkpoint R tip and base. Per-file sources (`git log a03226d3..d0956bed -- <file>`):

| Handler | Brief (CR tip) | Base `d0956bed` | Moved by |
|---|---|---|---|
| `psh/core/locale_service.py` | 488 | **492** | `a6b65e96` "core: move the POSIX class table below both readers (5B.1, commit iii)" |
| `psh/core/locale_service.py` | 502 | **506** | `a6b65e96` (same) |
| `psh/scripting/analysis_session.py` | 487 | **490** | `75cb9c67` "scripting: drop the unread AnalysisSession.shell field (5B.1, commit iv)" |
| `psh/scripting/source_processor.py` | 545 | **554** | `862bfabc` "protocols: adopt the 5B witnesses and narrow the escape-hatch members (5B.2)" |

The other 20 handler lines are unchanged. Not an erratum — the brief instructed
"re-run at base, reconcile"; recorded here with sources so the 24-row
classification table keys off BASE lines, not CR-tip lines.

## A2. Q2 BROAD_MASKING ledger — 7 keys confirmed by reading

`tests/unit/tooling/test_broad_valueerror_catch_q2.py` `BROAD_MASKING` has
exactly **7** entries at base, matching the brief's enumeration:
`directory_stack.py` popd VE net, `directory_stack.py` dirs -N VE net,
`disown.py` VE net, `parse_tree.py` VE/TE/AE pipeline net, `read_builtin.py`
whole-record-engine VE net, `combinators/parser.py` can_parse AE/IE/TE/ParseError
net, `utils/ast_debug.py` formatter-selection VE/TE/AE net.
(Suite-green confirmation pending — see A-TODO.)

## A3. Twin-guard (D-5B.1-s2) — growth set and incomplete-def count RE-DERIVED

Integrator dispatch measured THREE campaign-created modules. Re-derived at base:

```
git log --diff-filter=A --pretty=format: --name-only v0.750.0..d0956bed -- 'psh/'
  → psh/expansion/procsub_render.py
    psh/scripting/analysis_session.py
    psh/utils/posix_classes.py
```

**CONFIRMS the integrator's figure of THREE.** Incomplete-def count, derived by
TWO INDEPENDENT METHODS (D-3.5 joint lesson — never verify with the method that
produced the number):

| Module | defs | incomplete (AST, Method-A rule) | mypy `--disallow-untyped-defs --disallow-incomplete-defs` |
|---|---|---|---|
| `psh/expansion/procsub_render.py` | 10 | 3 (`_render_statements:57`, `_render_command:123`, `_render_word:178` — all missing PARAM annotations only) | 3 errors, same lines, `[no-untyped-def]` |
| `psh/scripting/analysis_session.py` | 14 | 1 (`_directive_commands:354` — missing RETURN annotation only) | 1 error, same line |
| `psh/utils/posix_classes.py` | **0** | 0 | 0 |
| **total** | 24 | **4** | **4** |

Both methods agree at 4. Added fact the brief's "q5-F3 counted TWO with 4
incomplete private defs" did not carry: **`posix_classes.py` contains ZERO
function definitions at all** (it is a pure data table), so the third module
adds nothing to the completion workload. The "4" figure is unchanged by its
arrival — the completion list is 3 param annotations + 1 return annotation.

## A4. Twin-guard staleness — TWO facts beyond the brief's characterisation

**(i) The guard has ALREADY been hand-patched around its own stale endpoint.**
`MIGRATED_MODULES` is 17 entries, but the pinned enumeration
`v0.724.0..75ab5625` yields only **16**. The 17th, `psh.protocols`, is injected
by the self-check itself (`created.add("psh.protocols")`,
test_mypy_untyped_defs_coverage.py:309) because `psh/protocols/__init__.py` was
created at `4f0bff09` (2026-07-20), which is AFTER `75ab5625`. So the staleness
D-5B.1-s2 names is not latent — it has already forced one manual workaround
into the guard's source. Advancing the endpoint retires that workaround, which
is a currency win the design should bank rather than preserve.

Post-`75ab5625` created set (four): `procsub_render.py`, `protocols/__init__.py`,
`analysis_session.py`, `posix_classes.py` — i.e. the git enumeration at a
current endpoint yields `MIGRATED_MODULES` + the 3 growth modules with NO manual
`.add()`.

**(ii) A bare-vs-star asymmetry inside the guard's own subject.**
`pyproject.toml` covers protocols TWICE with different shapes:

- line 169: `module = "psh.protocols.*"` → `check_untyped_defs = true` (STARRED)
- line 221: `"psh.protocols"` inside the disallow block → BARE

Measured with the guard's OWN resolution model (`_resolves_flag`):

| module | check_untyped_defs | disallow_untyped_defs | disallow_incomplete_defs |
|---|---|---|---|
| `psh.protocols` | True | True | True |
| `psh.protocols.future_submodule` | True | **False** | **False** |

This is precisely the TESTINF-1 bare-vs-star shape the twin guard exists to
police, sitting unpoliced inside the twin guard's own list: a future
`psh/protocols/foo.py` would silently escape BOTH disallow flags, and
`test_migrated_modules_have_complete_signatures` would still pass because it
only resolves the hardcoded dotted names, never the package's submodules.
Candidate for the currency work (proposal in D2).

---

## A5. Guard suites GREEN at base (the A2 confirmation)

`pytest tests/unit/tooling/{test_broad_valueerror_catch_q2,
test_mypy_untyped_defs_coverage, test_shell_consumer_ratchet_q1,
test_import_layering, test_subscript_no_broad_except, test_protocol_layering_q1,
test_mypy_scope}.py -q` → **68 passed in 3.15s**. So the Q2 ledger's 7 keys are
live (`test_broad_masking_only_shrinks` + `test_classification_has_no_stale_entries`
both green), and the caps floor / layering lock are green before I touch
anything.

## A6. D-3.5-s2 — `let` per-leg forcing: the ValueError leg is DEAD

Instrument `A4_let_leg_forcing.py` (transcript `A4_let_leg_forcing_BASE.out`).
METHOD, deliberately not the one that produced the claim: drive a corpus
through the REAL `evaluate_arithmetic(expr, shell, arith_source_quotes=False)`
— the exact call `let` makes — and classify the raised type against the two
legs by real `isinstance`, rather than reading the evaluator and arguing.

AXIS-QUANTIFICATION: the first corpus (34 cells) varied expression SHAPE only
— syntax / div-zero / exponent / base / subscript / recursion / unset /
overflow. Adding the **OPTION axis** (a second corpus with `set -u`, `readonly`,
nameref-cycle, `set -o posix` setups, each on a FRESH shell) changed the
answer materially, which is why it is here.

| Outcome | Cells |
|---|---|
| corpus cells | **42** |
| no exception (control) | 16 |
| raised | 26 |
| → taken by the **ValueError leg ONLY** | **0** |
| → taken by the ArithmeticError leg only | 20 (all `ShellArithmeticError`) |
| → both legs | 0 |
| → **ESCAPE both legs** | **6** |

Distinct raised types across the whole corpus: `ShellArithmeticError`,
`UnboundVariableError`, `ReadonlyVariableError`.

**VERDICT — the ValueError leg is DEAD**, forcing-proven on the real path, and
the 3.5 deadness argument therefore TRANSFERS as the LEDGER predicted. The
SEEDED CONTROL arm confirms the instrument can see a live VE (a bare
`ValueError` raised into the same handler shape is caught), so the zero is a
property of the production path, not of an inert probe (D-3.4 lesson 7).

**NEW FACT the LEDGER row did not carry: 6 cells escape the handler ENTIRELY.**
`set -u` on an unset name raises `UnboundVariableError` and a `readonly`
target raises `ReadonlyVariableError` — both `PshError`, NEITHER a
`ValueError` nor an `ArithmeticError` — so they propagate past `let` today and
are handled by the top-level PshError path. Narrowing the handler does not
change them (they already escape); recorded because a deadness verdict that
did not enumerate the escapes would have been quantifying over the wrong space.

### A6.0 Can a RAW Python ArithmeticError escape? — NO (the D2 hedge closed)

D2 recommended `except ArithmeticError` and explicitly declined the tighter
`except ShellArithmeticError`, because a raw `ZeroDivisionError`/`OverflowError`
escaping the evaluator would then propagate and "my corpus produced no such
cell either way" — i.e. the tighter narrowing rested on ABSENCE of evidence,
the weakest possible basis and exactly what this campaign polices. Measured
instead, two ways.

**STATIC — count at the ONE DOOR.** `_apply_binary_op` (`evaluator.py:472`) is
the single door for raw arithmetic: plain binary ops reach it at `:424`,
compound assignments at `:454` via the `DIVIDE_ASSIGN → DIVIDE` map at
`:328-329` (the code says so itself — "compound assignments reuse
_apply_binary_op() without duplication"). Inside that door every raw operation
is guarded: DIVIDE and MODULO check `right == 0` → typed
`ShellArithmeticError`; POWER checks `right < 0` → typed; POWER uses modular
`pow(base, right, 1 << 64)` so no huge intermediate is built; shifts mask the
count `& 63`, so a negative shift cannot raise. The only bare `//` in the
package (`_trunc_div`, `:57`) is reachable only past the zero guard.

**FORCING — instrument `A16_raw_arith_escape.py`** (transcript
`A16_raw_arith_BASE.out`). AXIS: OPERATOR (divide/modulo/power/lshift/rshift)
× FORM (plain / compound-assign) × DANGER VALUE (by-zero, zero-by-zero,
neg-by-zero, INT64_MIN by −1 — the C-overflow shape, negative exponent, huge
exponent, negative shift, huge shift, huge-by-huge) = **90 cells**.

| Outcome | Cells |
|---|---|
| no exception | 66 |
| raised `ShellArithmeticError` | **24** |
| raised **anything else** | **0** |

CONTROL: the probe observes a real `1 // 0` as `ZeroDivisionError` with
`isinstance(…, ShellArithmeticError) == False`, so the classifier is not
vacuous.

**VERDICT: no raw Python `ArithmeticError` can escape `evaluate_arithmetic`.**
The tighter narrowing to `except ShellArithmeticError` is therefore supported
by MEASUREMENT rather than by absence of evidence — D2's hedge is withdrawn
and the recommendation upgraded (D3). Total forced corpus for the `let`
question is now 42 + 90 = **132 cells**.

### A6.1 `let` diagnostics vs bash, BOTH SIDES (base record)

Instrument `A4b_let_bash_battery.sh` (transcript `A4b_let_bash_BASE.out`);
oracle `/opt/homebrew/bin/bash` 5.2.26 asserted in the transcript, `/bin/bash`
refused by construction; discriminator asserted before measuring.

22 cells: **9 IDENTICAL, 13 RC-SAME/TEXT-DIFF, 0 DIVERGENT.**
**Every cell's exit code matches bash.** The 13 text-diffs are the pre-existing
arithmetic-diagnostic wording class (bash `1/0: division by 0 (error token is
"0")` vs psh `1/0: Division by zero`) plus psh prefixing `let:` on the
readonly diagnostic where bash does not. NONE of these is created or altered by
the narrowing — this is the BASE record the Phase B re-run gets diffed against
(REGRESSION axis must come back EMPTY).

**INSTRUMENT DEFECT FOUND AND FIXED, recorded not buried.** The first version
normalised bash's prefix with a literal `^bash: `, but bash prefixes
diagnostics with its full argv[0] (`/opt/homebrew/bin/bash: line 1: …`), so the
prefix never stripped and cells whose MESSAGE was byte-identical
(`escape/nounset`, `ok/no-args`) were reported as TEXT-DIFF. Under-stripping
inflates the divergence count — the direction in which a real regression can
hide inside a wall of false diffs. Fixed to strip both shells' prefixes, path
and all; 4 cells moved from TEXT-DIFF to IDENTICAL as a result.

## A7. Boundary signatures — the USAGE censuses (ruling (e) input)

Instrument `A5_shell_usage_census.py` (transcript `A5_shell_usage_BASE.out`).

**INSTRUMENT DEFECT FOUND AND RECORDED (the 5B.2-lesson-1 trap, walked).** The
first version censused only defs taking a `shell` PARAMETER. It reported 5
member chains for the arithmetic package and **ZERO for `PromptExpander`** — a
class that takes the shell in `__init__` and then uses it as `self.shell.<x>`
throughout. A zero from an instrument blind to the dominant shape measures the
instrument, not the surface. The same blindness reduced `ArithmeticEvaluator`
to an opaque forward. A STORED-FIELD arm was added; both subjects then
measured properly. (A first-pass shell grep also produced a PHANTOM member,
`shell.RECURSION_LIMIT` — it is a prose mention of `psh.shell.RECURSION_LIMIT`
in a comment, collapsed by the grep's own `sed`. There is no such member access;
the AST census is right and the grep was the misleading one.)

**Subject 1 — `evaluate_arithmetic` (module functions + `ArithmeticEvaluator`,
which `evaluate_arithmetic` constructs):**

| Reached through | Members actually used |
|---|---|
| `.state` | `get_variable`, `set_variable`, `scope_manager` (`get_variable_object`, `warn_nameref_cycle`, `resolve_nameref_name`, `store.set_element`), `error_location_prefix`, `_arith_recursion_depth` |
| `.expansion_manager` | `expand_string_variables` (×3), `subscript` (×1) |

**Subject 2 — `PromptExpander` (`self.shell`, 5 chains):**

| Reached through | Members actually used |
|---|---|
| `.state` | `command_number`, `history` |
| `.expansion_manager` | `expand_string_variables` (×1) |

PromptExpander's need is a strict SUBSET of evaluate_arithmetic's.

### A7.1 The nine-hop family RE-MEASURED at base — matches D-5B.2-s2 exactly

Code hops only (a `shell.expansion_manager.subscript` occurrence in
`subscript.py:155` is a DOCSTRING mention, and one in `expansion/CLAUDE.md` is
prose — both correctly excluded):

| File | `.subscript` | `.command_sub` | `.execute_arithmetic_expansion` | `.tilde_expander` |
|---|---|---|---|---|
| `arrays.py` | 3 | | | |
| `operands.py` | | 2 | 1 | 1 |
| `operators.py` | 1 | | | |
| `fields.py` | — | — | — | — |
| `variable.py` (the ninth, pre-existing) | 1 | | | |
| **total** | **5** | **2** | **1** | **1** |

**= 9 hops; 8 in the four pinned consumer files + the ninth in concrete
`VariableExpander`. `.subscript ×4+1` reconciles exactly.** I checked whether
"four pinned mixin files" was an error given only THREE carry hops — it is NOT:
the pin (`tests/unit/expansion/test_variable_expander_reach_5b2.py`) scans four
files and `fields.py` legitimately contributes zero. Reported as verified, not
as an erratum.

The same pin records the OTHER half of why `.shell` survives: **THREE
whole-shell forwards, all in `operators.py`** — `evaluate_arithmetic(expr,
self.shell)` ×2 and `PromptExpander(self.shell)` ×1. So `.shell` exists for
exactly (8 hops + 3 forwards) = the 11 sites the pin asserts.

### A7.2 The design — COMPOSITION, not widening (so the fence is not pulled)

The brief flags "growing the new manager-surface protocol beyond the measured
hop usage" as a FENCE. The union the three subjects need is
{`subscript`, `command_sub`, `execute_arithmetic_expansion`, `tilde_expander`}
∪ {`expand_string_variables`} — and the second set is already declared by the
EXISTING `ExpansionRuntime`. So the union is reachable by COMPOSING two
measured protocols instead of widening either:

```
ExpansionSubExpanders(Protocol)   # the FOUR measured hop members, read-only props
ExpansionSurface(ExpansionRuntime, ExpansionSubExpanders, Protocol)   # 0 new members
ExpansionHost(Protocol)          # {state: ShellState, expansion_manager: ExpansionSurface}
```

No member is invented; `ExpansionSurface` declares nothing of its own. Members
are read-only PROPERTIES per the 5B.2 invariance lesson (a mutable protocol
attribute is invariant, and `ExpansionManager` holds concrete subtypes).

**If this is ruled, `VariableExpanderProtocol.shell` can retire COMPLETELY** —
the 8 hops type through `ExpansionHost.expansion_manager`, and the 3 whole
forwards type because both callees take `ExpansionHost`. That would discharge
D-5B.2-s2 in full rather than partially.

### A7.3 FEASIBILITY PROVEN, not asserted (5B.2 lesson 4)

Instrument `A6_protocol_feasibility.py` — the actual protocol declarations
checked by a real mypy run against the real `Shell` / `ExpansionManager`, with
the assignments Phase B would make. `mypy --follow-imports=silent` → **exit 0,
zero errors** for all six claims: C1 `ExpansionManager` satisfies
`ExpansionSubExpanders`; C2 satisfies the composed `ExpansionSurface`; C3
`Shell` satisfies `ExpansionHost`; C4 all eight hop reaches type-check; C5
evaluate_arithmetic's measured usage type-checks; C6 PromptExpander's does.

MUTATION-PROVEN (`A6b_mutation_driver.py`, anchored `count=1` replaces per
5B.2 lesson 6; RED arms assert the FAILURE REASON per 5B.1 lesson 2) —
**4 of 4 arms bite for their OWN reason**, control still clean:

| Arm | mypy says |
|---|---|
| M1 unknown manager member | `"ExpansionSurface" has no attribute "no_such_member"` |
| M2 member absent from host | `"ExpansionHost" has no attribute "job_manager"` |
| M3 producer loses a protocol member | `Incompatible return value type (got "ExpansionManager", expected "ExpansionSubExpanders")` + missing-member note |
| M4 host member typed wrong | `Incompatible return value type (got "Shell", expected "ExpansionHost")` + conflicts note |

So the design is mypy-LOAD-BEARING: a re-widening or a wrong type bites.

---

## A9. Masker reachability — BOTH open maskers proven DEFECT-ONLY

Instrument `A9_masker_reachability.py` (transcript `A9_masker_reach_BASE.out`).
The brief's fence asks whether anything NON-DEFECT ever flowed through the
broad catch. Method: run a hostile user-input corpus in-process under
`coverage.py` and report whether the handler's own body line executed.

| Masker | Corpus | Handler body EXECUTED |
|---|---|---|
| `read_builtin.py:236` | 19 cells — 7 malformed-UTF-8 shapes (lone/truncated/mid-string/surrogate) × the OPTION axis (`-N`, `-n`, `-d X`, `-r`, `-a`, `IFS=:`, `-s`), plus NUL byte, CRLF, EOF-continuation, no-newline, empty, long line | **False** |
| `parse_tree.py:136` | 124 cells = 4 formats × 31 inputs (valid, invalid, unclosed quotes, `$(((((`, `${!x}`, `${x@Q}`, `;;`, `&&`, `!`, process sub, assoc arrays, ANSI-C) | **False** |

**SEEDED CONTROL: True.** Injecting a `ValueError` into `_read_normal` makes
the read handler body execute and prints `psh: line 1: read: seeded defect
inside the read record engine` — so the two Falses are properties of the
production path, not of an inert probe. The seeded defect is monkeypatched and
REVERTED in the same run; nothing is left in the tree.

Both are therefore NARROW-safe: no fence pull.

### A9.1 A FALSE "load-bearing" reading, caught by a second method

**Recorded because it nearly produced a wrong fence report.** The first version
of this instrument keyed on the `except …:` CLAUSE line (`read 235` /
`parse_tree 135`) and reported **`parse_tree.py:135 EXECUTED=True`** — which
reads exactly like the brief's fence case ("the defect path was LOAD-BEARING").
Before reporting it I ran a DIFFERENT method: a direct subprocess scan of the
same inputs grepping for the handler's own `visualization error` diagnostic. It
found **zero** hits, contradicting the coverage verdict.

Cause: CPython traces an `except` clause when it is TESTED for a match, not
only when it matches. `parse_tree`'s try has a PRECEDING `except ParseError`
handler, so every ParseError-raising input (most of the invalid corpus) marks
the *next* clause's line as executed although its body never runs. A line-level
probe was answering a branch-level question — an instrument-kind mismatch.
Re-keyed on the handler BODY line, both maskers report False.

This is the D-3.5 joint lesson doing its job: the verification method differed
from the method that produced the number, and it caught the error.

## A10. Boundary-seam set — OPERATIONAL definition (ruling (d) input)

Instrument `A10_seam_census.py` (transcript `A10_seam_census_BASE.out`). The
brief asks the seam enumeration to be derivable, not curated, so the definition
is a predicate over the tree. A def is a BOUNDARY SEAM iff:

- **S1** it is incomplete under Method A (the census's own rule);
- **S2** it is PUBLIC — neither the def nor any enclosing scope starts with `_`
  (a private helper is per-package depth, which §11 defers post-campaign);
- **S3** it is top-level or a method of a top-level class (a closure is not an
  importable surface);
- **S4** its defining module is imported by at least one module in a DIFFERENT
  top-level `psh` package — the cross-package half, measured from the real AST
  import graph, so the set moves with the code.

**Result: 648 Method-A incomplete = 80 BOUNDARY SEAMS + 568 residue.**

| Package | Seams |
|---|---|
| core | 24 |
| executor | 18 |
| interactive | 11 |
| io_redirect | 7 |
| parser | 7 |
| utils | 6 |
| scripting / visitor / version.py | 2 each |
| expansion | 1 |

Per-file (21 files): `core/state.py` 16, `executor/job_control.py` 11,
`executor/strategies.py` 7, `interactive/signal_manager.py` 7,
`io_redirect/manager.py` 7, `core/variables.py` 6, `parser/__init__.py` 4,
`parser/…/word_builder.py` 3, `utils/signal_utils.py` 3, then 12 files with 1–2.

**INSTRUMENT DEFECT FOUND AND FIXED (recorded).** The first version recursed
only through `ClassDef`/`FunctionDef` children, so a def nested inside an
`if`/`try`/`with` block was never visited: the total came to **643** against
the reference census's **648**. A 5-def blind spot could have hidden a seam.
The reference instrument uses `NodeVisitor`/`generic_visit`, which descends
through every statement; A10 now does the same and the totals reconcile
EXACTLY at 648. (The seam count was 80 both before and after — the 5 missed
defs were all non-seams — but the number is only trustworthy now that the
denominator reconciles.)

## A11. Bare-vs-star sweep across the WHOLE override set (R1 item 5)

Instrument `A7_bare_star_sweep.py`. 39 override patterns; **3** name a real
PACKAGE with a BARE (unstarred) spelling; **2** have a genuine submodule hole.
Resolution measured with the guard's own `_resolves_flag`:

| Package | Parent resolves | A hypothetical submodule resolves | Hole | Disposition |
|---|---|---|---|---|
| `psh.protocols` | check✓ disallow_untyped✓ disallow_incomplete✓ | check✓ disallow_untyped**✗** disallow_incomplete**✗** | **YES** | **FIX (E-3)** — no guard catches it |
| `psh` | check✓ | check**✗** | YES, but **already guarded** | RECORD ONLY |
| `psh.parser.visualization` | check✓ | check✓ (a `.*` twin exists) | no | none |

The `psh` hole is real but NOT silent: `test_every_psh_module_has_check_untyped_defs`
asserts every psh module resolves true, so a new top-level `psh/foo.py` fails
that test loudly and forces an explicit edit — which is what the pyproject
comment at :180–188 says it intends. Broadening it to `psh.*` would also change
resolution for many modules via the later-wildcard-wins rule. **Recommend
record-only, no edit.** The `psh.protocols` hole IS silent, because
`test_migrated_modules_have_complete_signatures` only resolves the hardcoded
dotted names and never a submodule.

## A12. The 24 terminal handlers — classification (ruling (c) input)

Instrument `A8_handler_dump.py` (transcript `A8_handler_dump_BASE.out`) dumps
each handler with enclosing function, try-body call targets, whether it
re-raises, and what the handler does. **6 of the 24 RE-RAISE** — they are not
maskers at all.

| Class | N | Handlers (BASE lines) | Mechanism that makes it terminal |
|---|---|---|---|
| ROLLBACK-AND-RERAISE | 4 | `file_redirect.py:913`, `:1327`, `manager.py:673`, `strategies.py:270` | undo partial fd/redirection state, then re-raise — the error still surfaces |
| TRANSLATE-AND-RAISE | 2 | `lexer/recognizers/registry.py:78` (→`RuntimeError`), `analysis_session.py:490` (→`AnalysisSyntaxError`) | converts to a typed error; still surfaces |
| FORK BOUNDARY (`os._exit` discipline) | 5 | `child_policy.py:366`, `:374`, `:452`, `:582`, `process_launcher.py:374` | a child must NEVER propagate past the fork; 1.3b territory — signature-only changes |
| DEFECT-REPORTED | 3 | `trap_manager.py:480`, `function.py:188`, `visitor_modes.py:90` | routes to `report_internal_defect` — surfaces under `PSH_STRICT_ERRORS`, so not a silent mask |
| ERROR-PATH GLUE | 3 | `command.py:290` (`_handle_execution_error`), `source_processor.py:554` (`_classify_buffered_error`), `rc_loader.py:48` | a broken rc file / classified execution error must not kill the shell |
| DESTRUCTOR / RELEASE | 2 | `signal_utils.py:258` (`__del__`), `process_lease.py:565` (collects release errors and continues) | a `__del__` must not raise; a release loop must release the REST |
| OPTIONAL-CAPABILITY PROBE | 2 | `locale_service.py:492`, `:506` | libc/ctypes probing — absence degrades, never crashes (reactive LC_* machinery, a must-not-flip) |
| REPL SURVIVAL | 1 | `repl_loop.py:145` | the interactive session must survive a defect (must-not-flip; narrowing needs the strongest justification) |
| PROMPT SURVIVAL | 1 | `prompt.py:135` | a prompt-expansion failure must not break the prompt |
| FD RESTORE | 1 | `file_redirect.py:212` | restore path in a `finally`-like position |
| **total** | **24** | | |

### A12.1 Proposed self-maintaining mechanism

`tests/unit/tooling/test_terminal_except_ledger_5c1.py`, in the Q2 shape:

- **Detector**: AST over `psh/**.py`; every `ExceptHandler` whose type mentions
  `Exception` (plus bare `except:`), matching the CR instrument's rule so the
  24/0 figure stays the same subject.
- **Key**: `(relpath, enclosing-function, tuple-of-try-body-call-names)` —
  **LINE-INDEPENDENT**, exactly the Q2 idiom. My §A1.1 line-drift finding (4 of
  24 lines moved in one wave) is the direct evidence that a line-keyed ledger
  rots.
- **Registry**: key → `(CLASS, specific reason naming the mechanism)`, CLASS
  drawn from the closed vocabulary above.
- **Cells**: no unclassified handler; no stale entries (forces the registry to
  shrink with the tree); every reason ≥40 chars AND naming its mechanism; CLASS
  ∈ vocabulary; detector-not-vacuous.
- **Offender arms** (RED asserts the REASON, 5B.1 lesson 2): a synthetic
  unclassified `except Exception` BITES; a stale entry BITES; **control** — a
  classified handler passes and a narrow `except OSError` is not a candidate.

## A13. Carry sweep — THREE registers

| Row | Register | Disposition in 5C.1 |
|---|---|---|
| MEDIUM-12 | Part B | **CLOSES with this slot** if all 7 maskers are dispositioned per ruling (b) and the let residue lands. Closure needs: 7 rows ruled, Q2 ledger shrunk by every narrowed entry, forcing instruments two-axis |
| MEDIUM-16 | Part B | **PARTIAL.** 5C.1 lands the seam SET (80, derivable) + the ruled reduction + twin-guard currency. Row stays OPEN: the 568-def residue is per-package depth, post-campaign |
| D-3.5-s2 | Part D | **DISCHARGED** — VE leg forcing-proven dead (§A6); narrowing designed |
| D-5B.1-s2 | Part D | **DISCHARGED** — twin-guard currency (§A4, §A11) |
| D-5B.2-s2 | Part D | **DISCHARGED IN FULL if ruling (e) takes the composition design** (§A7.2/A7.3): `.shell` retires completely. If a narrower ruling lands, the remainder is named explicitly |
| D-5B.2-s1 | Part D | **DESIGN INPUT ONLY** — cited in the protocol design; the preserved 11-member/47-site variable census is NOT re-opened |
| D-5B.2-dead (`foreground_pgid`) | Part D | **5C.2's** — verified untouched (`git diff` EMPTY) |
| D-4B.4-s3 (`with_redirections`) | Part D | **5C.2's** — verified untouched |
| D-5B.1-s1 | Part D | Order-dependence flake — known; record-and-route if tripped, never fix here |
| CR-D1..D6 | Part C | None touched — verified untouched |
| 1.3b child-status / exit-trap | Part B | The 5 fork-boundary handlers are classified only; NO semantic change |
| strict-errors taxonomy | Part B | Frame for every narrowing; no semantics changed |

## A14. Twin-guard currency design (D-5B.1-s2 + E-3)

The 5B.1 three-list model, ADAPTED (not copied blind — the twin's subject is
per-module mypy FLAG coverage, not a consumer allowlist):

1. **Endpoint advanced + the hand-patch retired.** `v0.724.0..75ab5625` →
   a current endpoint. `MIGRATED_MODULES` becomes the git enumeration over the
   new range with **no `created.add("psh.protocols")` injection** — `protocols`
   is derived like everything else (R1 item 4). Growth: 16 hardcoded + the
   injected 1 → **20** (the four post-`75ab5625` modules join naturally).
2. **Coverage assertion with ancestor-checked loud vacuity**, mirroring
   `test_post_endpoint_modules_are_all_dispositioned`: every psh module born
   after the endpoint must be either IN `MIGRATED_MODULES` or in a new
   `POST_ENDPOINT_OUT_OF_SCOPE` register with a justification. Decision logic
   as a PURE function self-tested against an INJECTED enumeration, never real
   commits (the 5B.1 rule that keeps the self-test's subject from moving).
3. **E-3 fix — normalize the SPELLING, and teach the guard the CLASS.** Both,
   with distinct jobs, and neither is sufficient alone:
   - *Spelling*: `"psh.protocols"` → `"psh.protocols.*"` in the disallow block
     (pyproject :221). This is what actually closes the hole, and it makes the
     disallow block agree with how :169 already spells the same package for
     `check_untyped_defs`. Preferred over teaching the guard to "resolve
     submodule coverage" for the parent, because that would encode a *model* of
     coverage the config does not have — the config would still be wrong.
   - *Guard*: for every `MIGRATED_MODULES` entry that is a real PACKAGE, assert
     a hypothetical submodule ALSO resolves true on both disallow flags. This
     generalizes the fix so the next migrated package cannot repeat it.
     Offender arm: the probe BITES at the base (bare) spelling and PASSES at
     the fixed spelling; control arm: a properly covered module still passes;
     RED arm asserts the failure REASON.
4. **`_warn_selfcheck_unverified` dedup — PROPOSE: do NOT dedup.** The two
   copies differ in signature (the ratchet's takes a range argument; the twin's
   hardcodes its range in the message template) and, more importantly, each
   guard's own warn-path self-test must stay independent — a shared helper
   makes one test's green depend on the other module's source. The brief
   explicitly says "don't force it". I propose keeping them separate and
   instead making the twin's message carry its range the same way, so the two
   are UNIFORM in shape without being COUPLED in code.
5. **`posix_classes.py` prose (R1 item 3):** it joins `MIGRATED_MODULES` and
   gets override coverage even though it has zero defs today — the guard prose
   must say the coverage exists for the FIRST def anyone adds, so a later
   reader does not "clean up" an apparently pointless entry.
6. **Completion list (4 defs, §A3):** `procsub_render.py` `_render_statements:57`,
   `_render_command:123`, `_render_word:178` (param annotations) +
   `analysis_session.py` `_directive_commands:354` (return annotation).

## A15. Proposed census reduction target (ruling (d)), per-file SOURCES

Every term sourced; no term is an estimate.

| Source | Method-A defs removed | Where |
|---|---|---|
| Twin-guard completion list (§A3) | 4 | procsub_render 3, analysis_session 1 |
| `evaluate_arithmetic` signature (D-5B.2-s2 step a) | 1 | `arithmetic/evaluator.py:677` (`shell` param) |
| `PromptExpander.__init__` (step b) | 1 | `interactive/prompt.py:26` (`shell` param) |
| **pre-registered total** | **6** | 648 → **642** Method A |

Method B: `evaluate_arithmetic` and `PromptExpander.__init__` are non-nested;
`__init__` is a dunder and so is OUTSIDE Method B's denominator. The three
`procsub_render` defs and `_directive_commands` are private but non-dunder,
non-nested, so they ARE in Method B. Method B: 488 → **483** (−5).

These are the floor, not a ceiling: adopting the ruling-(e) protocol may type
further seam defs, and any additional reduction will be reported with its own
per-file terms rather than folded silently into this figure.

## A8. Masker designs (all 7 — rows 4 and 5 now measured)

| # | Site (BASE lines) | Design | Diagnostic delta |
|---|---|---|---|
| 1 | `directory_stack.py:440` popd | NARROW to `try: index = int(arg)` only — **the codebase's own correct form already exists as the sibling `_popd_no_cd` (`:466`)**; everything after the conversion dedents out of the try | NONE (int() is the only VE source; `popd letters` prints the same "invalid index argument") |
| 2 | `directory_stack.py:556` dirs -N | NARROW identically — wrap only `int(arg)`; the range check + `self.error` leave the try | NONE |
| 3 | `disown.py:103` | NARROW — wrap only `int(spec)`; `get_job_by_pid`/`_disown_job` leave the try | NONE |
| 6 | `combinators/parser.py:377` can_parse | **JUSTIFIED-KEEP candidate with a corrected reason.** Measured: `can_parse` has **NO production caller** (its own docstring says so; the only callers are `tests/unit/parser/combinators/test_parser_integration.py` and `tests/regression/test_parser_review_fixes.py`). The current reason cites the combinator parser being outside the production quality bar; the HONEST reason is that this is a test-facing probe API whose contract IS "return False rather than raise" | n/a (no production path) |
| 7 | `utils/ast_debug.py:77` | NARROW by TYPING THE RAISE SITE. **The VE leg here is NOT dead — it is the module's own `raise ValueError(f"unknown AST format {format_type!r}")` at `:75`**, reachable by `PSH_AST_FORMAT=bogus`. Introduce a typed error for that self-raise and catch only it; the TypeError/AttributeError legs (which mask real formatter defects) go. The user-visible "Warning: AST formatting failed (…), using default format" + fallback is preserved exactly for the unknown-format path | NONE on the unknown-format path (must be pinned); a formatter DEFECT now surfaces instead of silently falling back — which is the point |

| 4 | `parse_tree.py:135` | **NARROW — delete the VT/AE leg.** Measured defect-only (§A9: 124 cells, body never executes). The `except ParseError` leg above it already handles every user-input error; the VT/AE net only ever downgrades a tokenizer/parser/visitor DEFECT to "visualization error". Removing it lets the defect surface under the strict-errors taxonomy | NONE measured (no user input reaches it) |
| 5 | `read_builtin.py:235` | **NARROW — delete the VE leg.** Measured defect-only (§A9: 19 hostile cells incl. 7 malformed-UTF-8 shapes × the option axis; body never executes; seeded control proves the probe can see a hit). The Q2 reason ("no int()/documented-VE source in the body") is CORRECT, and I can now say WHY rather than assert it: the one plausible user-reachable VE source is `UnicodeDecodeError` (a `ValueError` subclass) from the record engine's UTF-8 decoding, and the cursor's decoder is `codecs.getincrementaldecoder('utf-8')('surrogateescape')` (`input_reader.py:158`), which by construction does not raise on malformed bytes — bash reads stdin bytes leniently and psh matches. The `except OSError` leg above it keeps the real `read error:` diagnostic | NONE measured |

Note on row 5's reason: the reading alone would NOT have been enough — the
brief's fence about a load-bearing defect path is exactly this shape, so the
verdict rests on the forced corpus, with the reading as the explanation of the
measurement rather than a substitute for it.

---

# PHASE B (ruling (a) GO received in R2)

## B0. Pre-registration of every countable movement (R2 standing requirement)

Written BEFORE the commits that move them. Every term sourced; no reasoned-to
terms (5B.1 lesson 3).

| Quantity | Base | Target at tip | Source of the delta |
|---|---|---|---|
| Q2 `BROAD_MASKING` entries | 7 | **1** | 6 narrowed (rows 1–5, 7); row 6 `can_parse` stays with a corrected reason |
| Q2 `NARROW_SAFE` entries | ~~14~~ **13** (corrected, see B0.1) | **13** | no site migrates into NARROW_SAFE |
| `except Exception` handlers | 24 | **24** | ruling (c): NO narrowings among the 24 |
| bare `except:` | 0 | **0** | untouched |
| `MIGRATED_MODULES` | 17 (16 git + 1 injected) | **20** | +procsub_render, +analysis_session, +posix_classes; the injected `psh.protocols` becomes git-derived |
| Method A incomplete | 648 | **642** | 4 twin completions + `evaluate_arithmetic.shell` + `PromptExpander.__init__.shell` |
| Method B incomplete | 488 | **483** | same minus `__init__` (a dunder, outside Method B's denominator) |
| `psh.protocols.__all__` | 4 | **5** | +`ExpansionHost` only (see B1.3) |
| `VariableExpanderProtocol.shell` reach | 11 sites | **0** | member retires entirely |
| compare-bash | 3,046/26 EXACT | **3,046/26 EXACT +0** | internal-integrity slot |
| `FUNC_IMPORT_CAPS` floor | 66/177/177/0 | **unchanged** | fence: no deferred import may move |

New guard file: `tests/unit/tooling/test_terminal_except_ledger_5c1.py` (24
classified handlers + offender/control/RED arms).

## B1. Ruling (e) requirement 1 — the protocol HOME, declared

**HOME = `psh/protocols/__init__.py`.** Reasons, in order of weight:

1. **Cross-package consumption forces it.** `ExpansionHost` is consumed by
   `psh/expansion/_protocols.py`, `psh/expansion/arithmetic/evaluator.py` AND
   `psh/interactive/prompt.py` — two top-level packages. The alternative home
   `psh/expansion/_protocols.py` would make `psh/interactive` import a PRIVATE
   module of `psh/expansion` — a new cross-package edge into a private surface,
   which is the shape this campaign removes (5B.1 deleted exactly such an edge
   when `_POSIX_CLASSES` moved to `psh/utils/posix_classes.py`).
2. **`ExpansionSurface` composes `ExpansionRuntime`, which already lives here.**
   Composing from another package would invert the dependency.
3. **Layering route:** `psh.protocols` imports NOTHING from `psh` at runtime —
   every producer/value type it names is imported under `TYPE_CHECKING` with
   PEP-563 string annotations, and `test_protocol_layering_q1.py::
   test_protocol_modules_have_no_runtime_impl_imports` enforces it. `ShellState`
   is therefore imported **TYPE_CHECKING-only**, exactly as the existing
   protocols do. Consumers narrow via string annotations, so **no new runtime
   import edge** is created in either direction — which is also why the
   `FUNC_IMPORT_CAPS` floor cannot move (the caps fence stays un-pulled).
4. **Disallow coverage:** home = `psh.protocols`, so the **E-3 starred fix
   (`"psh.protocols"` → `"psh.protocols.*"`) covers the new members** on both
   `disallow_untyped_defs` and `disallow_incomplete_defs`. No additional
   override is needed — stated explicitly per R2 requirement 1.

### B1.3 EXPORT SET — a constraint found by reading the pins, not by design

NAME-VS-BODY (grep the pins BEFORE encoding a rule) turned up a real constraint
that changes the shape of the deliverable:

- `test_protocol_layering_q1.py::test_protocols_package_exports_its_protocol_set`
  asserts `set(__all__)` equals an EXACT four-name set.
- `test_protocol_adoption_census_5b2.py::test_every_exported_protocol_has_a_
  production_consumer` requires every **exported** protocol to have a
  production consumer, resolved PER DEFINITION (imported from the defining
  module and used in an annotation or as a base). Its
  `ZERO_CONSUMER_PENDING_RULING` register is deliberately EMPTY — "and that is
  the point".

`ExpansionSubExpanders` and `ExpansionSurface` are referenced only from INSIDE
`psh/protocols/__init__.py` (as `ExpansionSurface`'s bases and `ExpansionHost`'s
member type). A module does not import from itself, so if they were EXPORTED
they would have **zero production consumers** and would either fail 5B's
defined-but-unused exit criterion or force entries into a register whose
emptiness is its whole value.

**Therefore: export ONLY `ExpansionHost`** (`__all__` 4 → 5). The other two stay
module-internal composition pieces. This is not a workaround — it is the honest
classification: they are not independently consumable service surfaces, they
are the structure of `ExpansionHost`'s manager member. The module prose will
say so. `ExpansionHost` itself has THREE production consumers, so the census
cell passes for the right reason.

## B2. Ruling (e) requirement 2 — pin census for `VariableExpanderProtocol.shell`

Every live pin referencing the member, to be retired WITH ITS SUCCESSOR in the
same commit (never silently weakened):

| Pin | What it asserts today | Successor in the same commit |
|---|---|---|
| `tests/unit/expansion/test_variable_expander_reach_5b2.py` — `test_shell_member_hop_census` | per-file `self.shell.<attr>` hop counts (arrays 3, fields 0, operands 4, operators 1) | host-adoption census: the same per-file counts now reached through `self.host.expansion_manager`, plus grep-zero on `self.shell` |
| same — `test_shell_member_reaches_only_the_expansion_manager` | only `expansion_manager` hop kind survives | subsumed by grep-zero (no `self.shell` at all) |
| same — `test_whole_shell_forwards_are_exactly_three` | 3 whole-shell forwards, all operators.py | forwards now pass `ExpansionHost`; cell becomes "zero WHOLE-`Shell` forwards remain" |
| same — `test_total_reach_is_eleven_sites` | headline 11 | **0**, with the 11 accounted as 8 hops migrated + 3 forwards retyped |
| same — `test_the_locale_read_no_longer_goes_through_shell` | 5B.2's migrated site | UNCHANGED (still valid, different member) |
| same — `test_scanner_detects_a_synthetic_new_hop` | guard-the-guard | UNCHANGED (retargeted at the successor field) |
| `tests/unit/protocols/test_protocol_adoption_census_5b2.py` | `__all__` protocols all have consumers | grows by `ExpansionHost` + its 3 consumers |
| `tests/unit/tooling/test_protocol_layering_q1.py` | exact `__all__` set (4) | 5 names, same commit |
| `tests/unit/tooling/test_shell_consumer_ratchet_q1.py` | full-`Shell` consumers ALLOWLIST | `SubscriptEvaluator.__init__` entry may become stale if it migrates — check and retire if so |


### B0.1 CORRECTION to my own pre-registration — `NARROW_SAFE` was 13, not 14

Self-caught while verifying the commit-2 shrink. My B0 table pre-registered
`NARROW_SAFE` at **14** at base. The DERIVED figure is **13**:

```
python3 -c "import importlib.util; s=importlib.util.spec_from_file_location(
  'q2','tmp/base-probe/tests/unit/tooling/test_broad_valueerror_catch_q2.py');
  m=importlib.util.module_from_spec(s); s.loader.exec_module(m);
  print(len(m.BROAD_MASKING), len(m.NARROW_SAFE))"
  -> 7 13     (at the base-probe checkout of d0956bed)
```

**The substantive claim is unaffected** — the register is 13 at base and 13 at
tip, i.e. UNCHANGED, which is what the row asserts. What was wrong was the
figure itself: I wrote 14 from having read the file rather than from counting
it. That is precisely the failure 5B.1 lesson 3 names — *every pre-registration
term needs a SOURCE* — and I did not source this one. Recorded rather than
quietly edited, and the superseded value stays visible (W0-R2 precedent).

Every other B0 term was derived from an instrument before it was written; this
is the only eyeballed one, and it is now derived too.

## B3. Commit 2 — popd / dirs / disown narrowings, TWO-AXIS proven

Sites (BASE lines): `directory_stack.py:440` popd, `:556` dirs -N,
`disown.py:103`. Each try body now wraps ONLY its `int()` conversion.

**AXIS 1 — REGRESSION, must be EMPTY.** Instrument
`B1_masker_two_axis.sh`, run at a detached probe worktree of `d0956bed` and at
tip, **32 cells** covering valid input, invalid input (`popd letters`,
`popd +letters`, `popd +99`, `dirs +letters`, `dirs -99`, `disown notanumber`,
`disown %bogus`, empty and bare `+`/`-` operands), the `-n` variants, and live
background-job disown by `%1` and by PID.

```
diff BASE TIP  ->  (no output)
*** AXIS 1 EMPTY — zero shell-observable delta across all 32 non-defect cells ***
```

Instrument note: the first run showed four `dirs` cells differing — the two
trees print their own cwd. That is a diff I would have had to explain away,
which is the shape this axis must never produce, so the probe now runs from a
FIXED neutral cwd identical on both sides and EMPTY means empty.

**AXIS 2 — RECLASSIFICATION.** Instrument `B2_forced_defect.py` seeds a
`ValueError` inside each FORMER try body (never in the documented `int()`):

| Seed | BASE (masked) | TIP (surfaced) |
|---|---|---|
| `DirectoryStack.pop` via `popd +0` | `psh: line 1: popd: invalid index argument: +0`, rc=1 | **SURFACED** `ValueError: seeded defect in DirectoryStack.pop` |
| `DirectoryStack.size` via `dirs +0` | `psh: line 1: dirs: invalid index argument: +0`, rc=1 | **SURFACED** `ValueError: seeded defect in DirectoryStack.size` |
| `get_job_by_pid` via `disown 123` | `psh: line 1: disown: 123: not a valid job specification or process id`, rc=1 | **SURFACED** `ValueError: seeded defect in get_job_by_pid` |

Unseeded CONTROL rows on the same three cells behave as ordinary user errors at
both SHAs. All seeds are monkeypatches applied and reverted in-process —
nothing is left in the tree.

**INSTRUMENT DEFECT FOUND AND FIXED (recorded).** The first popd seed targeted
`_chdir_or_error`, which `pushd` also calls — so the seeded error fired during
the cell's own `pushd /usr` SETUP, outside popd's try entirely, and SURFACED at
BASE as well as TIP. A cell showing the same result on both sides proves
nothing about the narrowing; it was measuring the setup line. Re-seeded on
`DirectoryStack.pop`, which only popd reaches and only from inside the former
try, the cell discriminates correctly. This is the second time this slot that a
probe looked like it was answering the question while measuring something else.

Suites: Q2 10/10 green with `BROAD_MASKING` 7 → 4; directory-stack/disown
selection 158 passed, 11 skipped.

## B4. Commit vii pre-state — ALLOWLIST expected final count (R4 item 3)

Stated BEFORE the commit, as required.

Consumer-ratchet `ALLOWLIST` at base and now: **9 entries**. Expected after
commit vii: **8**.

The entry that goes stale is `("psh.expansion.subscript",
"SubscriptEvaluator.__init__")`. Its justification reads "forwards `shell` to
evaluate_arithmetic(expr, shell) … but the arithmetic forward forces the full
Shell". Once `evaluate_arithmetic` takes `ExpansionHost`, **that sentence stops
being true**, so leaving the entry in place would leave a FALSE justification
sitting in a ratchet — the same defect I corrected for `can_parse` in commit
iv. Measured usage confirms it can narrow: `subscript.py` reaches
`self.shell.state` (:163), `self.shell.expansion_manager` (:176) and forwards
to `evaluate_arithmetic` (:383) — nothing else, and all three are
`ExpansionHost` members.

**The field must be RENAMED, not merely retyped.** The ratchet's
instance-assignment arm (D-5B.1-s3) is keyed on the assignment TARGET: it flags
`self.shell = <bare name>` regardless of the annotation. So a narrow
`shell: ExpansionHost` that still assigns `self.shell` remains a detector hit
and would still need an allowlist entry. Renaming to `self.host = host` is what
actually retires the reach, and it is also what makes the B2 successor pin
(`grep-zero on self.shell`) meaningful rather than cosmetic.

Same treatment for `PromptExpander` (`self.shell` ×3 → `self.host`) and for the
four `VariableExpanderProtocol` mixin consumers.

The other 8 entries are untouched: 3 × `child_policy` (fork-boundary child
runners), `command_resolution.resolve_command`, 3 × `analysis_session`
(embedder-contract chain), `program_source.execute_sourced_file`.

## B6. Census at tip — BEATS the ruled floor; every extra term sourced

Reference instruments (the CR copies) at tip:

| Figure | Base | Ruled FLOOR | **Tip** |
|---|---|---|---|
| Method A incomplete | 648 | 642 | **633** |
| Method B incomplete | 488 | 483 | **478** |
| `except Exception` / bare | 24 / 0 | 24 / 0 | **24 / 0** |
| Boundary seams | 80 | — | **80** |

Ruling (d) allows beating the floor ONLY with per-file terms declared before
the gate. Instrument `B5_census_delta.py` diffs the def-level census between a
detached base checkout and tip; `B5_census_delta.out` is the transcript.

**15 defs completed, 0 regressed, 0 removed-while-incomplete, 0 new-incomplete.**

| File | Defs completed | Method B | Pre-registered? |
|---|---|---|---|
| `expansion/procsub_render.py` | `_render_statements:57`, `_render_command:123`, `_render_word:179` | 3 | **yes** (twin-guard) |
| `scripting/analysis_session.py` | `_directive_commands:362` | 1 | **yes** (twin-guard) |
| `expansion/arithmetic/evaluator.py` | `evaluate_arithmetic:682` | 1 | **yes** (D-5B.2-s2 step a) |
| `interactive/prompt.py` | `PromptExpander.__init__:29` | 0 (dunder) | **yes** (step b) |
| `expansion/arithmetic/evaluator.py` | `_arith_source_round1:640`, `_arith_preexpand:658`, `_evaluate_arithmetic_inner:713`, `arithmetic_expansion_value:767`, `execute_arithmetic_expansion:813`, `ArithmeticEvaluator.__init__:75` | 5 | **no — additional** |
| `expansion/subscript.py` | `SubscriptEvaluator.__init__:157` | 0 (dunder) | **no — additional** |
| `expansion/variable.py` | `VariableExpander.__init__:42` | 0 (dunder) | **no — additional** |
| `expansion/parameter_expansion.py` | `ParameterExpansionOps.__init__:146` | 0 (dunder) | **no — additional** |
| **total** | **15** | **10** | 6 pre-registered + **9 additional** |

6 + 9 = 15 = 648 − 633 ✓, and the 10 Method-B terms = 488 − 478 ✓. The five
`__init__` completions are dunders and so sit outside Method B's denominator —
which is exactly why the two deltas differ, as predicted in B0.

**Every one of the 9 additional completions is a def the composition work
TOUCHED ANYWAY** — the case ruling (d) explicitly anticipated. Six are the
arithmetic evaluator's internal `shell` parameters: annotating
`evaluate_arithmetic` without annotating the functions it forwards to would
have left the module half-typed for no reason. The other three are the
constructors narrowed to `ExpansionHost` (`SubscriptEvaluator`,
`VariableExpander`, `ParameterExpansionOps`). None is an opportunistic sweep of
unrelated files.

Also new: **6 protocol member defs, all COMPLETE** — they add to the
denominator (3,245 → 3,251 total defs) and nothing to the incomplete count.

### B6.1 Limitation of the delta instrument, stated rather than hidden

`B5_census_delta.py` keys defs by `(relpath, qualname)`, so two defs sharing a
qualified name in one file (e.g. `@overload` stubs) COLLAPSE into one entry.
Its absolute totals are therefore 6 lower than the reference census on both
sides (642/627 vs 648/633). **The DELTA is unaffected** — the collapse is
identical at both SHAs, and 642−627 = 648−633 = 15, with Method B agreeing at
10 both ways. The reference instrument remains the authority for the figures;
this one is used only for the per-file attribution, which is what ruling (d)
asked it for.

Seams stay at **80**: the defs completed here were private helpers and dunders
(not seams by S2/S3), and the 6 new protocol members are complete (not seams by
S1). So the seam set is stable across the slot rather than accidentally moved.

## B7. Doc drift I CANNOT fix — ARCHITECTURE.md (never-touch list)

`ARCHITECTURE.md` enumerates the protocol set in TWO places and both are now
stale by one name:

- **line 98**: `protocols/  # Narrow runtime service protocols (Q1):
  ExpansionRuntime/IOContext/JobRuntime/LocaleAccess — a true leaf…`
- **line 125**, invariant 9: "…depend on the narrow `psh/protocols` interfaces
  (`ExpansionRuntime`, `IOContext`, `JobRuntime`, `LocaleAccess`)…"

Both should also name **`ExpansionHost`**, and invariant 9 could note that the
full-`Shell` consumer set shrank 9 → 8 with this slot.

`ARCHITECTURE.md` is on the dev never-touch list (4A.1 §Rules), so I have NOT
edited it. **Flagged for the integrator to land at ceremony**, with the exact
text above. Recorded here rather than left for a verifier to find, because a
doc that lists four of five protocols is the drift class this campaign polices.

## B8. Gate pre-registration (cited in the GO request)

Base attestation (committed, gated `d8166242`): 23,941 passed / 1,620 skipped /
10 xfail; ruff clean; mypy clean; compare-bash 3,046/26 EXACT.

**Every term below is from a per-file `--collect-only` count on BOTH sides**
(tip in this worktree, base in the detached probe checkout of `d0956bed`) —
never an estimate. My first draft of this table was written from memory and
said "+22", then "+29"; both were wrong, which is exactly why the rule says
collect-only ONLY. The superseded figures are recorded here rather than
quietly replaced.

| File | BASE cells | TIP cells | Δ |
|---|---|---|---|
| `tests/unit/tooling/test_mypy_untyped_defs_coverage.py` | 9 | 20 | **+11** |
| `tests/unit/tooling/test_terminal_except_ledger_5c1.py` | 0 (new file) | 13 | **+13** |
| `tests/unit/protocols/test_expansion_host_witness_5c1.py` | 0 (new file) | 7 | **+7** |
| `tests/unit/expansion/test_variable_expander_reach_5b2.py` | 6 | 7 | **+1** |
| `tests/unit/tooling/test_broad_valueerror_catch_q2.py` | 10 | 10 | 0 |
| `tests/unit/tooling/test_protocol_layering_q1.py` | 5 | 5 | 0 |
| `tests/unit/protocols/test_protocol_conformance_q1.py` | 6 | 6 | 0 |
| `tests/unit/tooling/test_shell_consumer_ratchet_q1.py` | 28 | 28 | 0 |
| `tests/unit/protocols/test_protocol_conformance_q1.py` | 6 | 7 | **+1** (commit ix) |
| **net** | | | **+33** |

| Figure | Base | Expected at tip |
|---|---|---|
| passed | 23,941 | **23,974** (= 23,941 + 33) |
| skipped | 1,620 | **1,620** (no cell added a skip; `importorskip("mypy")` resolves — mypy is installed) |
| xfail | 10 | **10** |
| ruff | clean | **clean** (verified after every commit) |
| mypy | clean, 276 files | **clean, 276 files** (verified after every commit) |
| compare-bash | 3,046/26 EXACT | **3,046/26 EXACT +0** |

**Named expected-red pins: NONE.** Every suite touched is green in this
worktree already; the whole `tests/unit` tree ran clean at commit vii
(14,670 passed / 19 skipped).

Other pre-registered figures, all already verified at tip:
Q2 `BROAD_MASKING` **1** (from 7), `NARROW_SAFE` **13** (flat, corrected in
B0.1), `except Exception` **24** / bare **0** (flat), `MIGRATED_MODULES` **20**
(injection retired), Method A **633** / Method B **478** (beats the 642/483
floor, accounted per file in B6), `__all__` **5**, `self.shell` reach in the
expansion consumers **0**, `FUNC_IMPORT_CAPS` floor **66/177/177/0 unchanged**,
consumer ratchet `ALLOWLIST` **8** (from 9).

## B9. Commit v — the caps-fence episode (recorded at R5 item 2's request)

Evidence that the zero-slack cell earns its keep, for the LOW-row successor.

Commit v's first form imported `ShellArithmeticError` as a SECOND deferred
import in `let_builtin.py`. The ratchet failed on the spot:

```
psh.builtins.let_builtin: 2 deferred psh import(s) > cap 1
FAILED tests/unit/tooling/test_import_layering.py::test_function_level_import_ratchet
```

The cap was NOT raised. `psh/expansion/arithmetic/__init__.py` already
re-exports `ShellArithmeticError` (its `__all__`), and the ratchet counts
import STATEMENTS rather than names, so both names come through the ONE
existing statement at `let_builtin.py:48`. Floor **66/177/177/0 unchanged**;
layering suite 9/9 green.

The general point, which is the reason to write it down: the zero-slack
property is what made this visible AT ALL. Under the pre-5B.2 table
`let_builtin` carried a cap with headroom, the second import would have slipped
in under it, and nobody would have been asked to justify anything. The fence
turned a lazy cap bump into a visible decision — and the right answer cost
nothing, which is the usual case once someone is made to look.

## B10. Commit ix — a consistency defect I introduced, self-caught pre-gate

While waiting on gate GO I re-read the protocols module against its own stated
invariants, which is the check a verify round would run.

`psh/protocols/__init__.py` line 50 states: *"The protocols are
``@runtime_checkable`` so that conformance test can ``isinstance``."* All four
previously exported protocols carry the decorator AND an isinstance pin in
`test_protocol_conformance_q1.py`. **`ExpansionHost` had neither**, so commit
vii made that sentence false for one of the five exports — doc-vs-code drift,
created inside the slot whose job is to remove it.

Fixed by restoring the invariant, not by weakening the prose: `@runtime_checkable`
is back on, and `test_shell_satisfies_expansionhost` joins its four siblings.

The pin earns its place independently. It is the BEHAVIOURAL-INERTNESS check
for the whole slot: `evaluate_arithmetic`, `PromptExpander`,
`SubscriptEvaluator` and the four mixins all narrowed `Shell` → `ExpansionHost`,
and every one of those is annotation-only PRECISELY BECAUSE the `Shell` handed
to them already satisfies `ExpansionHost`. mypy checks the annotations agree;
this checks the producer really does have the surface, which is the question a
reader cares about.

**Pre-registration amended BEFORE the gate: +32 → +33**
(`test_protocol_conformance_q1.py` 6 → 7), so expected passed becomes
**23,974**. §B8 updated in place with this row.

---

# GATE RESULTS — final tip `cf48fb15`

Run under R7's extended GO, binding §B8-AS-AMENDED. `pgrep -f pytest` and
`pgrep -f run_tests` both UNPIPED and empty immediately before; foreground
`python -u run_tests.py --parallel > tmp/test-results-5c1.txt 2>&1`, moved to
background only after exceeding the foreground window (never stopped, never
shell-`&`); ONE heavy run machine-wide.

## G1. Every pre-registered term, verified at the final tip

| §B8 term | Pre-registered | **Measured** | ✓ |
|---|---|---|---|
| passed | 23,974 | **23,974** | ✓ |
| skipped | 1,620 | **1,620** | ✓ |
| xfail | 10 | **10** | ✓ |
| ruff | clean | **All checks passed!** | ✓ |
| mypy | clean, 276 files | **no issues found in 276 source files** | ✓ |
| compare-bash | 3,046/26 EXACT +0 | **3,046 passed, 26 skipped** | ✓ |
| expected-red pins | NONE | **none** | ✓ |

Gate transcript tail: `tmp/w5c1-instruments/GATE_tail.txt`
(`✅ All test phases PASSED`, 479.59s across 2 phases).
compare-bash transcript: `tmp/w5c1-instruments/COMPARE_BASH.out` (43.74s).

## G2. Every other pre-registered figure, at the final tip

| Figure | Base | Pre-registered | **Measured** | ✓ |
|---|---|---|---|---|
| Q2 `BROAD_MASKING` | 7 | 1 | **1** | ✓ |
| Q2 `NARROW_SAFE` | 13 | 13 flat | **13** | ✓ |
| `except Exception` / bare | 24 / 0 | 24 / 0 | **24 / 0** | ✓ |
| `MIGRATED_MODULES` | 17 (1 injected) | 20, injection retired | **20** | ✓ |
| Method A incomplete | 648 | ≤642 (floor) | **633** | ✓ beats |
| Method B incomplete | 488 | ≤483 (floor) | **478** | ✓ beats |
| boundary seams | 80 | 80 | **80** | ✓ |
| `psh.protocols.__all__` | 4 | 5 | **5** (`ExpansionHost` + the four) | ✓ |
| consumer ratchet `ALLOWLIST` | 9 | 8 | **8** | ✓ |
| `self.shell` in expansion consumers | 11 sites | 0 | **0** (grep-zero) | ✓ |
| `FUNC_IMPORT_CAPS` floor | 66/177/177/0 | unchanged | **66 entries, cap 177, actual 177, slack 0** | ✓ |

## G3. Discharge audit — every claim row, anchored

| Claim | Evidence anchor | Verified at |
|---|---|---|
| MEDIUM-12 fully dispositioned (7/7) | Q2 register = 1 + commits ii–iv | `cf48fb15` |
| popd/dirs/disown narrowed, zero observable delta | `B1_masker_two_axis.sh` → AXIS 1 diff EMPTY, 32 cells | commit ii |
| …defect reclassified | `B2_forced_defect.py` → 3/3 masked-at-base, surfaced-at-tip | commit ii |
| parse_tree + read defect-only | `A9_masker_reachability.py` → 124 + 19 cells, body never executed; seeded control True | commit iii |
| ast_debug: VE leg ALIVE, typed instead of deleted | `B3_astdebug_two_axis.py` → AXIS 1 warning byte-identical, AXIS 2 surfaced | commit iv |
| can_parse justified-keep, reason corrected | grep census: zero production callers | commit iv |
| D-3.5-s2: VE leg dead | `A4_let_leg_forcing.py` → 0/42 cells; seeded control fires | commit v |
| …and no raw ArithmeticError escapes | `A16_raw_arith_escape.py` → 0/90 cells; control non-vacuous | commit v |
| `let` diagnostics unchanged vs bash | `A4b_let_bash_battery.sh` → BASE and TIP transcripts share md5 `568924a5…` | commit v |
| 24 handlers classified, mechanism-named | `test_terminal_except_ledger_5c1.py` 13 cells; `B4_terminal_ledger_offender.py` 2/2 arms bite own reason | commit vi |
| D-5B.2-s2 discharged in full | grep-zero `self.shell` = 0; reach pin successors green | commit vii |
| protocol design mypy-load-bearing | `test_expansion_host_witness_5c1.py` — 4 mutation arms, each own error | commit vii |
| D-5B.1-s2 twin currency + E-3 | `test_mypy_untyped_defs_coverage.py` 20 cells; offender bites at bare spelling | commit i |
| census beats floor, accounted | `B5_census_delta.py` → 15 completed / 0 regressed, per-file | §B6 |
| behavioural inertness | `test_shell_satisfies_expansionhost` (isinstance at runtime) | commit ix |

**Previously-bounced rows: NONE** — this slot had no bounced row to replay.

## G4. FINAL TIP DECLARED + FIRST FREEZE

**Final tip: `cf48fb15`** (`protocols: make ExpansionHost runtime_checkable,
with its conformance pin (5C.1, commit ix)`), nine commits on
`fix/remediation-5c-1` from base `d0956bed`.

**LEDGER FROZEN at this line.** First freeze of this slot, so the freeze
declaration quotes NO prior freeze md5 (chain rule). Any correction after this
point is a SendMessage + dated addendum after the verdict, or a supervised edit
under an explicit ruling — never an in-place edit.

Mechanical tip rule now in force: any further commit, even comment-only, gets a
declaration BEFORE it lands.

---

# FIX ROUND (R9 BOUNCE) — UNFREEZE RECORDED

**UNFREEZE** at integrator instruction (R9). Freeze-1 md5 was
`66a893cfdcd6f7d9d6990489ae7e8b16`, snapshotted by the integrator at main
`tmp/remediation-ledgers/5c1-ledger-freeze1-snapshot.md`. Everything above this
line is the frozen-1 record and is NOT edited — corrections appear below as
addenda, per the chain rule.

Verdict: BOUNCE, 3 blockers + 25 nits, **record/doc layer — the code substance
held everywhere** (350 fresh non-defect cells base-vs-tip EMPTY, 9-symbol
deletion diff with ZERO resurrections, inertness and every red-claim replayed,
both censuses reproducing exactly). I take that distinction seriously rather
than as consolation: what the verifiers found is that several of my RECORDS
claimed more than my TREE enforced, which is the same failure the campaign
polices in others.

## F0. Addendum to frozen §A8 row 7 (N-25) — the reach route was imprecise

Frozen §A8 said the `ast_debug` unknown-format raise is "reachable by
`PSH_AST_FORMAT=bogus`". That is true ONLY via the in-session SHELL variable
(an assignment on a preceding line, under `--debug-ast`). Setting it in the
process ENVIRONMENT of a `-c` invocation silently resolves to the default
`tree` with no warning, at BOTH SHAs — `print_ast_debug` reads
`shell.state.scope_manager.get_variable('PSH_AST_FORMAT')`, not `os.environ`.

I hit this myself during Phase B (my first probe used the env var and produced
no warning) and corrected the PROBE without correcting the PROSE. The
substantive claim is unaffected; the phrasing could have misled the next person
writing a probe, which is exactly what it did to me for one round.

## F1. §B8 SECOND AMENDMENT — pre-registered BEFORE the fix-round commits

Per-file `--collect-only`, measured now, against the FIRST gate's 23,974.

| File | At gate-1 | **Now** | Δ |
|---|---|---|---|
| `tests/unit/utils/test_ast_debug_format_fallback_5c1.py` | 0 (new, BL-3) | 9 | **+9** |
| `tests/unit/tooling/test_terminal_except_ledger_5c1.py` | 13 | 15 | **+2** (N-1/N-24 multiplicity arm, N-2 stale-entry arm) |
| `tests/unit/expansion/test_variable_expander_reach_5b2.py` | 7 | 7 | 0 (N-5 widens an existing cell's sweep, N-6 is a cleanup) |
| `tests/unit/tooling/test_broad_valueerror_catch_q2.py` | 10 | 10 | 0 (N-3 is header prose) |
| `tests/unit/protocols/test_protocol_conformance_q1.py` | 7 | 7 | 0 |
| `tests/unit/tooling/test_protocol_layering_q1.py` | 5 | 5 | 0 |
| `tests/unit/protocols/test_expansion_host_witness_5c1.py` | 7 | 7 | 0 |
| **net** | | | **+11** |

| Figure | Gate-1 | **Expected gate-2** |
|---|---|---|
| passed | 23,974 | **23,985** (= 23,974 + 11) |
| skipped | 1,620 | **1,620** |
| xfail | 10 | **10** |
| ruff / mypy | clean / clean 276 | **clean / clean 276** |
| compare-bash | 3,046/26 EXACT | **3,046/26 EXACT +0** |

**Named expected-red pins: NONE.** All other pre-registered figures are
unchanged by the fix round — no production LOGIC changed, so Q2 **1**,
handlers **24/0**, `MIGRATED_MODULES` **20**, Method A/B **633/478**, seams
**80**, `__all__` **5**, ALLOWLIST **8**, `self.shell` reach **0**, caps floor
**66/177/177/0** all stand.

**N-15 help-text safety checked BEFORE committing** rather than discovering it
at the gate: no test or doc pins the old string (`grep "visualization error"`
over `tests/` and `docs/` returns nothing), and the three help-oracle suites
(`test_builtin_help_sync`, `test_help_transcript_matches_guide`,
`test_claims_have_tests`) are green at 66 cells with the new wording.

## F2. Fix-round evidence

**BL-1/BL-2** — the rename in both docs. `_protocols.py`'s MODULE docstring
said the mixins reference `self.shell` "set in `VariableExpander.__init__`",
twenty lines above the declaration this slot rewrote, and the reach-test's
table comment said the same. Both now read `self.host`. This is the defect I
was least entitled to: my own commit-vii message argues that a false
justification in a ratchet "is worse than a missing one", and I then shipped a
false statement in the header of the file I was rewriting.

**BL-3** — the pin exists now:
`tests/unit/utils/test_ast_debug_format_fallback_5c1.py`, 9 cells, two-axis.
AXIS 1: the exact warning line + `DebugASTVisitor` fallback, plus a
four-format CONTROL so a handler that warned on everything could not pass.
AXIS 2: seeded `TypeError` in `ASTPrettyPrinter.visit` and seeded
`AttributeError` in `AsciiTreeRenderer.render` must both PROPAGATE.
Red-on-base is established behaviourally by `B3_astdebug_two_axis.py`, now
committed as transcripts on BOTH sides (N-20):

| | BASE `d0956bed` | TIP |
|---|---|---|
| AXIS 1 warning line | identical | identical |
| AXIS 2 seeded formatter defect | **masked** as `Warning: AST formatting failed (seeded defect inside ASTPrettyPrinter.visit), using default format` | **SURFACED** `TypeError` |

(The test FILE cannot run at base at all — `UnknownASTFormat` does not exist
there — so the module-level import error is not a meaningful RED. The
behavioural red-on-base is the instrument's, above. Stating that rather than
claiming a cell-level red I did not have.)

**N-1/N-24** — the ledger key now carries an occurrence index within its
`(file, fn, calls)` group, so a colliding second handler keys separately and
stays unclassified. Offender arm asserts BOTH that two handlers are reported
and that they do not collapse. Line-independence is preserved and still
asserted.

**N-2** — stale-entry offender arm committed, driven against a COPY of the
registry so the real one is untouched, with a control asserting the live
registry has no stale rows.

**N-5** — grep-zero extended from `CONSUMERS + variable.py` to a declared
`RENAMED_HOLDERS` list adding `subscript.py`, `parameter_expansion.py` and
`interactive/prompt.py`. **Offender-proven**: regrowing `self.shell` in
`prompt.py` (the holder with no other coverage) makes the cell fail naming
`prompt.py`; file restored and md5-verified.

**N-3** — the subclass-typed-catch evasion is now RECORDED in Q2's header as a
third out-of-scope shape, with the reason for not fixing it here stated
plainly: widening a detector in the same slot that created its first instance
is how a guard gets tuned to accept what its author just wrote. Successor row
requested.

**N-6, N-14, N-15, N-16/N-7** — dead tuple-unpack removed; the false
`--debug-ast=bogus` route replaced by the ONE true route with both false ones
named (and the env-var negative now pinned as a cell, because that route cost
me a round of my own Phase B); three help strings de-claim the deleted leg;
the protocols header gains its `ExpansionHost` row and its
"every EXPORTED protocol" correction.

### F2.1 Disclosure the verifiers did not raise

`ArithmeticEvaluator` (`expansion/arithmetic/evaluator.py:77`) still names its
field `self.shell` while holding an `ExpansionHost`. It is outside the consumer
ratchet's scanned set and outside N-5's named holders, so no pin is weakened
and nothing claims otherwise — but it IS the same naming inconsistency I
corrected elsewhere in this slot, and I would rather record it than have it
found. Not renamed here: the fix round has a defined charter and a 20-site
rename inside it is scope growth. Successor-row candidate alongside N-4/N-21.

## F3. FIX-ROUND TIP DECLARED + REFREEZE (freeze-2)

Fix-round commits:

| # | SHA | What |
|---|---|---|
| x | `6b9843c4` | record-layer docs: BL-1/BL-2 rename, N-14 false route, N-15 help wording, N-16/N-7 protocols header |
| xi | `3fe48475` | the missing pins: BL-3 two-axis ast_debug cell, N-1/N-24 multiplicity, N-2 stale-entry arm, N-5 grep-zero scope, N-3 evasion recorded, N-6 cleanup |

**New tip: `3fe48475`** — eleven commits on `fix/remediation-5c-1` from base
`d0956bed`.

**REFREEZE (freeze-2).** Per the chain rule this declaration quotes the
previous freeze: **freeze-1 md5 was `66a893cfdcd6f7d9d6990489ae7e8b16`**
(integrator-snapshotted). The ledger is frozen again at this line; corrections
after this point are a SendMessage + dated addendum, or a supervised edit under
an explicit ruling.

Instrument manifest regenerated (N-23): **18 instruments, 19 transcripts**, now
including `A10_seam_census.py` + its transcript (the ruling-(d) 80-seam input)
and `B3_astdebug_BASE.out` / `B3_astdebug_TIP.out` (N-20's missing pair).
