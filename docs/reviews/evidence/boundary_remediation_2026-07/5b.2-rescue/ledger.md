# Slot 5B.2 — consumer migration + caps — DEV LEDGER

- **Base:** `1c70dfbf` (v0.775.0 + 5B.1 addendum). Branch `fix/remediation-5b-2`,
  worktree `/Users/pwilson/src/psh-r5b-2`.
- **Brief:** `BRIEF-5B2.md`, md5 `e65a0a90089803361ca78e49797b55ad` —
  matches R0's declared md5 exactly (verified at first read).
- **Import discriminator asserted:** from this worktree
  `python -c "import psh, os; print(os.path.dirname(psh.__file__))"` →
  `/Users/pwilson/src/psh-r5b-2/psh`. From `$HOME` the same command resolves to
  `/Users/pwilson/src/psh/psh` (the editable install → MAIN), so **every**
  driver in this slot sets `PYTHONPATH` explicitly and every scratch-tree probe
  asserts the resolved path in-process before measuring.
- **Phase A status:** COMPLETE. All six "Phase A must settle" items measured.
  No production file has been modified: `git diff` at the end of Phase A is
  EMPTY (§A9), and mypy is back at its baseline 276 clean.

## Phase A — instrument manifest

All instruments are FILES under `tmp/w5b2-instruments/` with transcripts under
`tmp/w5b2-transcripts/`. Every one takes ROOT from `argv` (CR-D5 portability);
none hardcodes a worktree path. Committed 5B.1 instruments were treated as
READ-ONLY — instrument 19 was reproduced by transcription into instrument 02
(the single edit being ROOT-from-argv), never edited in place.

| # | File | What it measures |
|---|---|---|
| 01 | `01_protocol_consumer_census.py` | consumers PER DEFINITION for all 8 protocols + `self.shell`/`self.state` member reach in each `VariableExpanderProtocol` consumer |
| 02 | `02_locale_census_and_layering.py` | `state.locale` census by TWO methods + the `core/scope.py` adoption-route probe driven by the layering lock's own analyzer |
| 03 | `03_locale_member_usage.py` | which `LocaleAccess` members each of the six readers actually uses |
| 04 | `04_instance_assign_sweep.py` | D-5B.1-s3 shape grammar (5 offender arms, 4 control arms) + in-scope and tree-wide sweeps |
| 05 | `05_caps_classification.py` | per-entry cap-vs-actual table + hoist simulation (**superseded by 09**) |
| 06 | `06_hoist_reality_check.py` | real `import psh` with every candidate edge hoisted, in a scratch copy |
| 07 | `07_free_hoist_set.py` | partition of hoists by startup cost (**superseded by 09**) |
| 08 | `08_free_set_demonstration.py` | real import + timing of the "free" subset (**falsified its own input**) |
| 09 | `09_caps_target_corrected.py` | corrected predicate + target-triple menu + full defect chain |
| 10 | `10_twelve_param_matrix.py` | what each of the 12 campaign-added owner params touches |

Instrument defects found and recorded rather than buried: §A5.4 (a chain of
three, each caught by a real import contradicting a static verdict) and §A1's
alias blindness. Both are reported because the number they would have produced
was wrong, not because the fix was interesting.

---

## A1. Consumer census PER DEFINITION — §A6's counts INDEPENDENTLY REPRODUCED

Instrument 01. Resolution is by definition, not by name: a module consumes a
protocol only if it imports that name FROM the defining module and then uses it
as a class base or in an annotation.

| Protocol | Defined in | §A6 says | I measure |
|---|---|---|---|
| `VariableExpanderProtocol` | `expansion/_protocols.py` | 4 | **4** (arrays, fields, operands, operators) |
| `CommandParsersProtocol` | `parser/combinators/commands/_protocols.py` | 4 | **4** (pipelines, redirections, simple, statements) |
| `ControlStructureProtocol` | `.../control_structures/_protocols.py` | 3 | **3** (conditionals, loops, structures) |
| `VariableAccess` | `protocols/__init__.py` | 0 | **0** |
| `ExpansionRuntime` | `protocols/__init__.py` | 0 | **0** |
| `IOContext` | `protocols/__init__.py` | 2 | **2** (`builtins/input_reader.py:407`, `io_redirect/input_cursor.py:146`) |
| `JobRuntime` | `protocols/__init__.py` | 1 | **1** (`executor/foreground_session.py:51,63`) |
| `LocaleAccess` | `protocols/__init__.py` | 0 | **0** |

Eight of eight agree with the binding ruling-(b) table. This is a
re-derivation, not an adoption: the census was written before reading §A6's
counts back.

**Instrument defect, found before use (recorded per 4B.3 rule 6).** Version 1
matched a `ClassDef` base against the protocol NAME and reported **0** consumers
for the three mixin protocols §A6 records as 4/4/3. The real shape is a
TYPE_CHECKING alias — `_Base = VariableExpanderProtocol`, then
`class ArrayOpsMixin(_Base)` — so the base is the alias. A name-shaped census
would have reported every mixin protocol in the tree as unused, which is the
exact mirror of 5B.1's own caution. Version 2 follows module-level aliases
transitively; the corrected counts are above.

---

## A2. MEMBER × CONSUMER — the seven §A6 member rows, measured

Ruling (b) is BINDING and is not re-litigated here. Two rows are reported as
**FENCE ROUTES** because the measurement shows the ruled target cannot land as
written — which is the disposition the brief itself pre-describes for exactly
this case ("e.g. a consumer needs state members outside `VariableAccess`").
I have touched nothing on those rows.

### A2.1 `VariableExpanderProtocol.state: 'ShellState'` → `VariableAccess` — **FENCE**

`VariableAccess` declares exactly three members: `get_variable`,
`set_variable`, `get_special_variable`.

Measured `self.state.<member>` usage across all four consumers — **47 sites**,
of which **3** are in-surface and **44** are not:

| Member | Sites | In `VariableAccess`? |
|---|---|---|
| `get_variable` | 1 | yes |
| `set_variable` | 1 | yes |
| `get_special_variable` | 1 | yes |
| `scope_manager` | 12 | **no** |
| `last_exit_code` | 11 | **no** |
| `error_location_prefix` | 10 | **no** |
| `positional_params` | 5 | **no** |
| `stderr` | 3 | **no** |
| `options` | 1 | **no** |
| `ifs_star_separator` | 1 | **no** |
| `last_bg_pid` | 1 | **no** |

Per consumer: `arrays.py` 10 sites (scope_manager 7, set_variable 1, options 1,
stderr 1); `fields.py` 4 (scope_manager 2, get_variable 1, positional_params
1); `operands.py` 1 (positional_params 1); `operators.py` 32 (error_location_
prefix 10, last_exit_code 11, scope_manager 3, positional_params 3, stderr 2,
get_special_variable 1, ifs_star_separator 1, last_bg_pid 1).

**EIGHT members outside the declared surface, across 44 of 47 sites, in all four
consumers.** Narrowing the member as ruled makes mypy reject 44 sites. Widening
`VariableAccess` to cover them would import most of `ShellState` into a protocol
whose docstring's whole point is that it is *not* `ShellState` ("which also
carries options, execution state, streams, ..."). Widening is a ruling, not a
default (brief FENCES), so this stops here with the census row.

**Consequence for witness #1:** this row was `VariableAccess`'s only named
witness, so **`VariableAccess` cannot gain a consumer by the ruled route.**
Ruling needed — see §A8 request (c1).

### A2.2 `VariableExpanderProtocol.shell: 'Shell'` → REMOVE — **FENCE**

**12 sites** across the four consumers (`fields.py` has none):

| Use | Sites | Narrow surface that covers it |
|---|---|---|
| `self.shell.expansion_manager` | 8 | **`ExpansionRuntime`** (arrays 3, operands 4, operators 1) |
| `self.shell.state.locale` | 1 | `LocaleAccess` (operators.py:513) |
| `evaluate_arithmetic(expr, self.shell)` | 2 | **none** — operators.py:83, :87 |
| `PromptExpander(self.shell)` | 1 | **none** — operators.py:530 |

Nine of twelve sites are covered by narrower surfaces. The remaining **three
forward the whole `Shell` to a whole-shell consumer**: `evaluate_arithmetic`
(whose own `shell` parameter is unannotated and which reaches `shell.state` ×14
and `shell.expansion_manager` ×4 inside `arithmetic/evaluator.py` alone, before
any deeper forwarding) and `PromptExpander`. That is precisely the ALLOWLIST
justification shape already recorded for `SubscriptEvaluator` ("the arithmetic
forward forces the full Shell"). REMOVE cannot land while those three sites
exist; making them land would mean migrating `evaluate_arithmetic`'s and
`PromptExpander`'s own signatures, which is the broader full-Shell surface the
brief explicitly puts outside this slot (5C boundary signatures).

### A2.3 `CommandParsersProtocol.redirection: Any` → typed — **LANDS, with one call-site fix**

Probed by applying the type and running mypy (edit → measure → revert; §A9
verifies the revert). `redirection: "Parser[Redirect]"` produces **exactly one**
error, tree-wide:

```
psh/parser/combinators/commands/simple.py:61: error: Argument 1 to "append" of
"list" has incompatible type "Redirect | None"; expected "Redirect"
```

This is the gap the member's own comment predicts ("the parse closures append
`redirection.parse().value` to a `List[Redirect]`"). It is not a latent bug: the
site is already guarded by `if redir_result.success:`; it simply lacks the
None-narrowing that its own sibling branch **nine lines above** performs:

```python
if array_result.success:
    assert array_result.value is not None      # simple.py:53
    array_assignments.append(array_result.value)
```

Proposed landing: one `assert redir_result.value is not None` at simple.py:61,
matching the in-file idiom. Recommend EXECUTE.

### A2.4 `JobRuntime.shell_state: Optional[ShellState]` → `VariableAccess` **or** drop — **drop-route recommended**

The single consumer uses it at exactly two lines, `foreground_session.py:90-91`:

```python
if jm.shell_state is not None:
    jm.shell_state.foreground_pgid = pgid
```

The use is a **write of `foreground_pgid`**. `VariableAccess` has no such member
(and it is not a shell variable — it is terminal-handoff state), so §A6's first
option cannot land for the same reason as A2.1. §A6's SECOND option is the one
the measurement supports: the publish path takes the pgid directly. The whole
member exists to serve one write at one call site. Recommend the drop route;
the exact shape (a `JobRuntime` method vs. moving the write into
`transfer_terminal_control`) is a design choice I will not make unilaterally
because adding a protocol member is a widening (§A8 request (c2)).

### A2.5 `ExpansionRuntime.variable_expander: Any` → `VariableExpanderProtocol` — **LANDS CLEAN**

### A2.6 `ExpansionRuntime.word_expander: Any` → the word-expander surface — **LANDS CLEAN**

Both probed together: `variable_expander: "VariableExpanderProtocol"` and
`word_expander: "WordExpander"` (producers confirmed at
`expansion/manager.py:54,59`), imported under `TYPE_CHECKING` beside the
existing `Word`/`ShellState`/`Job` imports so the protocol package stays a
runtime leaf. **mypy: 0 errors, 276 files.** Both rows land with no consumer
change.

### A2.7 `LocaleAccess.collate_key -> Any` → named opaque alias — **proposal**

§A6 recommends a named alias over a false-precision type. Proposal:
`CollationKey = Any` declared in `psh/protocols/__init__.py` beside the
protocol, with `collate_key(self, s: str) -> "CollationKey"`. The value is a
libc-derived sort key that is only ever passed to `sorted(key=...)` and
compared — never inspected. The alias names the opacity instead of hiding it;
it changes no types, so there is nothing for mypy to reject.

---

## A3. Witness adoptions

### A3.1 `LocaleAccess` ← the SIX `state.locale` readers — **CLEAN, no fence**

Census REPRODUCED (instrument 02, method 19 transcribed): **6 files, 13 sites**,
byte-identical to §B12.5's binding table (`core/scope.py` 1, `executor/array.py`
2, `executor/enhanced_test_evaluator.py` 2, `expansion/glob.py` 1,
`expansion/operators.py` 1, `expansion/parameter_expansion.py` 6).

**Second method (D-3.5: verify by a DIFFERENT method than produced the claim).**
Method 19 filters to chains whose penultimate element is literally `state`. I
re-ran with NO base filter — every `.locale` attribute access in `psh/`. Result:
7 files / 21 sites. The difference is one file, `psh/core/state.py` (8 sites),
and it is correctly excluded: those are the OWNER's own sites
(`self.locale = LocaleService(...)`, `self.locale = parent.locale`,
`self.locale.reinit(...)`, `self.locale.pending_libc`), i.e. `ShellState`
holding and re-initialising the service, not a consumer reading through it.
`pending_libc`/`reinit` are not on the `LocaleAccess` surface at all, and this
is the reactive LC_* machinery (v0.688) the brief lists as must-not-flip. **The
SIX-file census stands, and now stands against a method that could have
disagreed.**

**Member usage (instrument 03): every reader is inside the declared surface.**
Used: `upper`, `lower`, `toggle`, `compare`, `collate_key`. Declared-but-unused
by these readers: `in_class`. Used-but-not-declared: **none** — no fence.
Five sites bind the service to a local (`loc = ...`) and the follow-on calls
were resolved too: all are `upper`/`lower`/`toggle`.

**Per-reader adoption route:**

| File | Site | Route |
|---|---|---|
| `core/scope.py` | L973 `loc = (self._shell.state.locale if … else active_locale())` | annotate the LOCAL, `Optional["LocaleAccess"]` — `active_locale() -> Optional[LocaleService]` and the code already guards `if loc else`; TYPE_CHECKING import |
| `executor/array.py` | L389, L391 | direct calls; annotate at the helper's own boundary |
| `executor/enhanced_test_evaluator.py` | L168, L170 | direct calls |
| `expansion/glob.py` | L200 | `sorted(key=…)` — the `collate_key` alias row (A2.7) is its natural pin |
| `expansion/operators.py` | L513 | `loc` local; note it reaches via `self.shell.state` (the A2.2 row's 1 locale site) |
| `expansion/parameter_expansion.py` | L509, L521, L533 (+3 direct) | `loc` locals |

### A3.2 `core/scope.py` layering route — **PROBED; the fence is NOT pulled**

`CORE_MODULE_IMPORT_ALLOWLIST = {psh.ast_nodes, psh.utils, psh.version}` does
not contain `psh.protocols`, so I asked the import-layering lock's OWN analyzer
(`analyze_source`) rather than reasoning from the rules:

| Route | runtime psh edges | deferred count | `test_core_is_near_leaf` |
|---|---|---|---|
| A: runtime module-level import | `['psh.protocols']` | 0 | **FAIL** |
| B: `if TYPE_CHECKING:` import | `[]` | 0 | **PASS** |
| C: function-body deferred | `[]` | 1 | PASS, but costs a cap |

**Route B is legal with zero cap cost and needs no `CORE_MODULE_IMPORT_ALLOWLIST`
change** — the analyzer excludes TYPE_CHECKING blocks from runtime edges by
construction, so the annotation import is invisible to the near-leaf rule. The
fence stays unpulled. Note `core/scope.py` has **no** TYPE_CHECKING block today
(its live runtime psh edges are six intra-`psh.core` imports, deferred count 2 =
its cap); the route ADDS one.

### A3.3 `ExpansionRuntime` ← `SubscriptEvaluator` — lands, but **the brief's pre-registration does not hold**

`SubscriptEvaluator.__init__(self, shell: 'Shell')` stores `self.shell` and
exposes two derived properties: `state` → `self.shell.state`, `_manager` →
`self.shell.expansion_manager`. The witness is real and minimal: `_manager`'s
return type becomes `"ExpansionRuntime"`, which is a genuine production
consumer of a currently-zero-consumer protocol.

**But the brief pre-registers that "the ALLOWLIST entry for subscript.py should
then SHRINK AWAY", and the measurement says it must NOT.** `subscript.py:374`
is `evaluate_arithmetic(expanded, self.shell)` — the full-Shell forward the
entry's own recorded justification names ("also consumes ExpansionRuntime +
state diagnostics, but the arithmetic forward forces the full Shell"). The
justification is accurate; the `shell` parameter cannot be removed, so the
ALLOWLIST stays at its current membership for this module. Pre-registering a −1
here would be pre-registering a figure the tree does not support. Flagged for
ruling (a) rather than quietly delivered as-is or quietly dropped.

---

## A4. PARAM × DISPOSITION — the 12 campaign-added owner params

Instrument 10 measures, per param, every member reached through it and every
place the whole object is passed on. None of the 12 lives in a module the
ratchet currently scans EXCEPT the three `analysis_session` ones, so 9 of them
carry no ALLOWLIST implication either way.

| # | Param | Reaches | Whole-object uses | Recommended disposition |
|---|---|---|---|---|
| 1 | `HistoryBuiltin._dispatch_options(shell)` | `shell.state` ×2 | 9 forwards to sibling methods | **justified-keep** |
| 2 | `HistoryBuiltin._display_operand(shell)` | — | `self.error`, `self._display` | **justified-keep** |
| 3 | `HistoryBuiltin._parse_options(shell)` | — | `self._usage_error` ×2 | **justified-keep** |
| 4 | `fatal_expansion_child_status(state)` | **none** | **none** | ruling — see below |
| 5 | `substitution_abort_status(state)` | `state.options` ×2 | — | **justified-keep** |
| 6 | `substitution_child_abort_status(state)` | `state.options` ×1 | — | **justified-keep** |
| 7 | `sync_child_status_for_exit_trap(state)` | `state.last_exit_code` ×1 | — | **justified-keep** |
| 8 | `map_child_exception(state)` | — | forwards to #4 ×2, #6 ×1 | **justified-keep** |
| 9 | `AnalysisSession.__init__(shell)` | `shell.analysis_mode` ×1 | `self._build_carrier(shell)` | **justified-keep** (recorded text SURVIVES) |
| 10 | `AnalysisSession._build_carrier(shell)` | `shell.state` ×3 | `type(shell)(parent_shell=shell, …)` | **justified-keep** (irreducible) |
| 11 | `parse_for_analysis(shell)` | — | `AnalysisSession(shell)` | **justified-keep** |
| 12 | `iter_command_units(shell)` **unannotated** | `shell.state` ×1 | `CommandAccumulator(shell)` | **ANNOTATE** as `'Shell'` |

**The `analysis_session` tension resolves in favour of the recorded
justification.** CR-R1 reshape 2 puts all three in the migration set; the
5B.1-R0 entries say the chain terminates in construction through the caller's
own `Shell` subclass. Measurement confirms it exactly: `_build_carrier` reaches
`type(shell)(parent_shell=shell, norc=True)` at L434, and `__init__` /
`parse_for_analysis` do nothing but feed that construction (plus one
`analysis_mode` read). A protocol models a surface an object HAS, never a type
that is constructible and accepts its own kind. The recorded justification
survives contact with the measurement; I recommend justified-keep for all three
and no ALLOWLIST movement.

**The History trio's forward chain bottoms out in the builtin BASE CLASS.**
`self.error` is `builtins/base.py:146 Builtin.error(self, message, shell:
'Shell')`, which reaches `shell.state.error_location_prefix()`,
`shell.state.in_forked_child` and `shell.stderr`; `_usage_error` and `_display`
are the same shape. Narrowing the trio therefore requires migrating the shared
builtin base-class surface (`base.py` alone declares 10 `shell: 'Shell'`
params) — every builtin in the tree. That is the broader full-Shell surface the
brief puts outside this slot and 5C's boundary-signature work owns it.

**#4 `fatal_expansion_child_status(state)` uses its parameter for NOTHING** —
the body is `return 1`. This is deliberate and documented, not an oversight;
the docstring says so in terms:

> Takes ``state`` for signature symmetry with the sibling and to keep the call
> site uniform; a future channel- or option-dependence would land here rather
> than at the boundary.

So the cheapest possible "migration" (delete the parameter) is available and
would cost two call-site edits in `map_child_exception`, at the price of
contradicting a documented deliberate choice and de-uniforming the fork
boundary. It is already `ShellState`, not `Shell`. I recommend **justified-keep
with the docstring as the justification** and put the delete option on the
record for ruling (e).

**#12 `iter_command_units(shell)` is the one honest defect in the twelve:** it
is UNANNOTATED, which is the ratchet's "smuggled reach with no type" shape. It
forwards to `CommandAccumulator(shell)`, which stores the whole shell
(`command_accumulator.py:123`), so it cannot narrow without that class
narrowing first. Annotating it `'Shell'` costs nothing, makes the reach
visible, and is strictly more honest than leaving it untyped. Recommend
EXECUTE.

**Net:** of the 12, one lands (annotate #12), ten are justified-keep on
measurement, one (#4) is a genuine ruling fork. `source_processor.py` and
`builtins/shell_state.py` are outside the ratchet's scan scope, so **no
ALLOWLIST growth is implied by any of this**.

---

## A5. Caps — enumeration, corrected target menu, and a three-defect chain

### A5.1 Base figures, re-derived with the guard's own analyzer

| Figure | Value | Source |
|---|---|---|
| `FUNC_IMPORT_CAPS` entries | **71** | the table |
| cap TOTAL | **198** | `sum(FUNC_IMPORT_CAPS.values())` |
| ACTUAL deferred psh imports | **177** across 66 modules | `python tests/unit/tooling/test_import_layering.py` |
| slack | **21** | 198 − 177 |

Matches the brief's expectation (~177 actual, slack ~21) and R0's declared
71/198 exactly.

### A5.2 Where the slack lives — MEASURED, not apportioned

| Class | Entries | Cap |
|---|---|---|
| **DEAD** (entry with actual 0) | **5** | **18** |
| **SLACK** (cap > actual > 0) | **2** | **3** |
| exact (cap == actual) | 64 | — |

The five dead entries are `psh.expansion.parameter_expansion` (cap 12!),
`psh.expansion.pattern` (2), `psh.lexer.cmdsub_scanner` (2),
`psh.lexer.heredoc_collector` (1), `psh.lexer.heredoc_lexer` (1). 18 + 3 = 21 =
the total slack, so the two classes account for it exactly. No module has
actual > 0 without a cap entry.

### A5.3 Achievable ACTUAL reduction — demonstrated by real import

Hoisting the candidate set removes **119 deferred sites** by adding **84
module-level imports across 51 modules**. Verified by building a scratch copy
with all 84 edges added and running it:

- `import psh; import psh.shell` → **IMPORT_OK**, discriminator asserted to the
  scratch tree in-process.
- `python -m psh -c 'echo hi; x=5; echo $((x+1)); a=(p q); echo ${a[1]};
  declare -A h; h[k]=v; echo ${h[k]}'` → `hi/6/q/v`, rc 0.

**Startup cost, measured apples-to-apples: `import psh` 66.2 ms → 73.2 ms
(median of 3, warm bytecode both sides) — ~+7 ms, 1.10×.**

### A5.4 DEFECT CHAIN — recorded in full, because it nearly produced a wrong ruling

This analysis was wrong three times, and each time only a REAL IMPORT caught it.

1. **v1 asked only the guard's package-cycle question** → 136/177 hoistable.
   Over-reported by construction: `package_edges` drops intra-package edges, so
   an intra-package hoist can never fail that test no matter what it does to the
   real import graph.
2. **v2 added "introduces no NEW module-level cycle"** → 119 hoistable. Still
   wrong: it SUBTRACTED pre-existing cycles, so an edge hoisted *into* an
   already-cyclic region passed because the cycle was not new. The full set
   happened to import; a 94-edge SUBSET of it did **not**
   (`ImportError: cannot import name 'ParseOutcome' from partially initialized
   module psh.parser.parse_outcome`). A subset failing where the superset
   succeeds is the tell that the predicate, not the set, was wrong.
3. **v3 expanded edges to ancestor packages** (importing `X.Y.Z` executes `X`
   and `X.Y`) → 0 hoistable, 177 forced. Over-corrected: with ancestors
   expanded, nearly everything reaches `psh/__init__` and lands in one giant
   SCC, so the predicate rejects edges the tree demonstrably tolerates.

**And a fourth, worse one — a measurement artifact that inverted the
recommendation.** The first timings showed `import psh` at 66 ms base vs 249 ms
hoisted and I was about to report a **3.4× startup regression** as the reason to
reject the hoist. That figure was almost entirely **cold bytecode compilation**:
the base tree had a warm `__pycache__` from earlier runs, every scratch copy was
freshly written with `PYTHONDONTWRITEBYTECODE=1`. Measured properly — an
UNMODIFIED control copy against the hoisted copy, both warmed — the real cost is
66.2 → 73.2 ms. **The instrument, not the tree, produced the 3.4×.** I record
this at length because the correct-looking version of this ledger would have
recommended against a hoist on the strength of a number that measured my own
scratch directory.

**Conclusion I draw from the chain:** static analysis is a candidate filter for
this question and nothing more; the REAL IMPORT is the decider, and the
verified-set property is JOINT, not per-edge (defect 2 proves subsets can fail
where the whole succeeds). Any tranche the ruling selects must be
import-verified as the tranche that actually lands.

### A5.5 Target triple menu — ruling (d) input

| Option | actual | cap | slack | entries | Risk |
|---|---|---|---|---|---|
| base | 177 | 198 | 21 | 71 | — |
| **(i) bookkeeping only** | 177 | **177** | **0** | **66** | **none** — no production change; delete 5 dead entries (−18), trim 2 slack entries (−3) |
| **(ii) + full verified hoist** | **58** | **58** | **0** | ~28 | 119 production edits; import-verified as a set; ~+7 ms startup |
| (iii) intermediate tranche | 58 < a < 177 | = actual | 0 | — | each tranche needs its OWN import verification (defect 2) |

**Recommendation: (ii), landed as (i) first.** Option (i) is a guaranteed,
zero-risk floor that already takes cap 198→177 and slack to 0, and it can land
independently of anything else in the slot. Option (ii) delivers what the LOW
row actually asks ("caps materially shrink"): a **genuine −119 on the ACTUAL
count**, not a cap trim — 177 → 58, a 67% reduction — for a measured ~7 ms of
startup and no behavior change. I recommend it, with the honest caveat that it
is a 119-site diff whose verification is joint, and that if the integrator wants
a smaller blast radius, (iii) is available at the cost of a separate
import-verification per tranche.

**Q2 second-cap-ledger sweep (brief item 4, last sentence):** the only other
ratchet-shaped inventory in the LOW row's scope is the broad-except ledger
(`test_subscript_no_broad_except.py`, MEDIUM-12), which is 5C.1's by W5-R1 and
counts exception handlers, not imports. No second CAP ledger exists. Nothing to
disposition.

---

## A6. D-5B.1-s3 — instance-assignment detector: grammar and PRE-BUILD sweep

### A6.1 Shape grammar — keyed on the SOURCE, not the attribute name

A hit is `self.<attr> = <value>` inside a method whose enclosing function has a
full-`Shell` parameter **by the shipped detector's own rules** (annotation
mentions `Shell`, or unannotated and named exactly `shell`), where `<value>`
resolves to that parameter.

Keying on the attribute NAME would be wrong, and not hypothetically:
`psh/core/scope.py:149` is `self._shell = shell`. A `self.shell`-only grammar
reports zero there while the service-locator reach is live one underscore away.

Arms (all self-tested, instrument 04, **9/9 as designed**):

| Arm | Shape | Fires? |
|---|---|---|
| 1 direct | `self.shell = shell` | yes |
| 2 renamed attr | `self._shell = shell` | yes |
| 3 annotated | `self.shell: 'Shell' = shell` | yes |
| 4 aliased | `s = shell; self.shell = s` | yes |
| 5 tuple | `self.shell, self.y = shell, y` | yes |
| A control | `self.state = state` (ShellState) | **no** |
| B control | `self.mgr = shell.expansion_manager` (a narrowing) | **no** |
| C control | `self.shell = None` | **no** |
| D control | `self.shell = other` (unrelated local) | **no** |

Control arm B matters most: the shape the campaign is trying to CREATE must not
be flagged as the shape it is trying to remove.

### A6.2 Sweep A — the ratchet's current scan scope (24 modules)

**Exactly one hit:** `psh.expansion.subscript.SubscriptEvaluator.__init__`,
`self.shell` @L159 [direct] — **already in ALLOWLIST** via its parameter.

**New unrecorded defs: 0. The detector extension therefore requires ZERO
ALLOWLIST additions**, so 5B.1-R0's growth exception is not exercised at all and
the ALLOWLIST stays at 9 entries. Pre-registered here before the arm is built.

### A6.3 Sweep B — tree-wide (information only, NOT this slot's migration set)

33 hits, 32 outside the current scan scope — the service-locator inventory in
instance-assignment form (executor ×8, expansion ×8, interactive ×5,
io_redirect ×3, scripting ×3, builtins ×1, core ×2 incl. the `_shell` rename
case). These are NOT dispositioned here: the brief's scope discipline is
explicit that 5B.2 does not migrate the tree-wide surface. Recorded so a future
scope extension meets an enumerated set rather than a surprise.

---

## A7. Carry sweep — THREE registers

`LEDGER.md` md5 `1313d9d93d39cc2351bf427d660c0655`; `FLIP-PINS.md` md5
`cf597e5c78687d53ee05be2851dc5982` (read before any divergence claim).

| Row | Register | Disposition |
|---|---|---|
| MEDIUM-14 protocol boundaries | Part A (L44) | **This slot ENDS it if its exit is met.** Closure requires: the seven §A6 member rows executed **or fence-resolved by ruling** (A2.1/A2.2 are fence routes — MEDIUM-14 cannot close on my authority while two ruled targets stand unexecuted), three witnesses landed with census pins, the 12 params dispositioned, D-5B.1-s3 discharged |
| LOW deferred-import/Q2 debt | Part A (L50) | **THIS slot's goal-shrink.** Menu in §A5.5; recommendation (ii) via (i) |
| D-5B.1-s1 order-dependence flake | Part D (L389) | MUST-NOT-ABSORB. Known: `test_is_clean_distinguishes_no_owner_from_no_state` after analysis/locale/expansion selections, pre-existing at BOTH 5B.1 SHAs. My selections may trip it; if so I RECORD (SHA, selection, both-SHA replay) and route — no fix here |
| D-5B.1-s2 mypy-guard stale endpoint | Part D (L390) | **5C.1's.** Verified untouched — I have not opened `test_mypy_untyped_defs_coverage.py` |
| D-5B.1-s3 instance-assignment detector | Part D (L391) | **THIS slot discharges it** — §A6 |
| D-3.5-s2 (`let_builtin.py:52`) | Part D (L301) | 5C's — untouched (no builtins edits) |
| D-4B.4-s3 (`IOManager.with_redirections`) | Part D (L367) | 5C's — untouched (no io_redirect edits) |
| CR-D1 … CR-D6 | Part D (L377-382) | **none touched.** CR-D5 portability actively honoured (all 10 instruments take ROOT from argv) |
| 1.4 carry: locale warn wider surface | Part C (L224) | **untouched.** §A3.1's second method confirms the reactive LC_* machinery lives in `core/state.py`, which the migration set deliberately EXCLUDES |
| FLIP-PINS | — | **No row touches this slot's subjects.** Grep over the register for protocol/locale/import/ratchet/param returns only 3.3/2.3/2.4/4B.2 divergence rows, all unrelated. **The DIVERGENCE axis is EMPTY this slot — proven by the sweep, not asserted** |

Term sweep over LEDGER.md: `protocol` 9, `Protocol` 2, `locale` 7, `ratchet` 17,
`caps` 4, `owner param` 2, `deferred-import` 1, `VariableAccess` 1,
`LocaleAccess` 3, `ExpansionRuntime` 3, `collate` 3, `shell_state` 1. Every hit
inspected; all resolve to rows already in the table above.

---

## A8. RULING REQUESTS

**(a) Phase A matrix** — this document. GO gate for Phase B.

**(c1) FENCE — `VariableExpanderProtocol.state` → `VariableAccess` (§A2.1).**
Cannot land as ruled: 8 members / 44 of 47 sites outside the declared surface,
in all four consumers. `VariableAccess` loses its only named witness with it.
Options, none taken: (1) widen `VariableAccess` — I recommend AGAINST, it would
absorb most of `ShellState` into the protocol that exists to not be
`ShellState`; (2) find `VariableAccess` a different witness elsewhere in the
tree (I have not searched — say the word and I will); (3) accept
`VariableAccess` as defined-but-unused for now and re-carry the witness, which
contradicts 5B's exit criterion; (4) keep `state: 'ShellState'` as-is and record
the measurement as the justification. **My recommendation: (2), and (4) for the
member row itself.**

**(c2) FENCE — `VariableExpanderProtocol.shell` REMOVE (§A2.2).** 9 of 12 sites
narrow cleanly; 3 forward the whole `Shell` to `evaluate_arithmetic` ×2 and
`PromptExpander` ×1. Options: (1) partial execution — introduce the narrow
member(s) for the 9 and keep `shell` for the 3, which is a protocol WIDENING and
so needs this ruling; (2) leave the row unexecuted with the census as the
justification; (3) migrate `evaluate_arithmetic`/`PromptExpander`, which is 5C
surface and I will not open it. **My recommendation: (1) if you will rule the
widening, else (2).**

**(c3) `JobRuntime.shell_state` (§A2.4)** — §A6's option 1 cannot land (same
reason as c1); option 2 (drop, publish the pgid directly) is supported by the
measurement but its shape adds a `JobRuntime` member = widening. Ruling please.

**(d) Caps target triple** — menu at §A5.5; **recommend (ii) landed via (i)**:
actual 177→58, cap→58, slack→0, entries 71→~28.

**(e) 12-param dispositions** — matrix at §A4: **annotate #12; justified-keep
×10; #4 is a genuine fork** (documented-unused param: keep the documented
symmetry, or delete the param and edit 2 call sites).

**Also for ruling (a):** the brief pre-registers that the `subscript.py`
ALLOWLIST entry SHRINKS AWAY on the `ExpansionRuntime` witness. It must not —
§A3.3. Please confirm the pre-registration is withdrawn rather than my
delivering a slot that misses a figure it was given.

---

## A9. Phase A hygiene

- **No production file modified.** The only Phase A edits were the three mypy
  tightening probes (§A2.3/A2.5/A2.6), applied and reverted in-turn. Verified at
  the end of Phase A: `git diff --stat` EMPTY; `git status --porcelain` shows
  only the two untracked slot documents (`BRIEF-5B2.md`, `INTEGRATOR-INBOX.md`);
  `mypy` back at **Success: no issues found in 276 source files**.
- **`PYTHONDONTWRITEBYTECODE=1`** set in every instrument invocation (5B.1
  lesson 1).
- **No heavy run performed.** `pgrep -f pytest` and `pgrep -f run_tests` checked
  UNPIPED before any measurement: both exit 1 (nothing running). No full suite,
  no compare-bash, no gate — those wait for Phase B and a GO.
- **Never-touch list intact**: `psh/version.py`, `CHANGELOG.md`, `README.md`,
  `ARCHITECTURE.md`, `docs/reviews/README.md`, `FLIP-PINS.md`, `LEDGER.md` all
  unmodified (empty `git diff` proves it). No push, no PR, no tag.
- **Provenance caveat (B71):** the §A5.3 timings are scratch copies under this
  worktree, not a detached checkout of a declared tip. They are Phase A decision
  probes; if ruling (d) turns on the 7 ms figure it gets re-measured detached in
  Phase B.
- **Main advance watch (5B.1 lesson 4):** none observed during Phase A; base
  still `1c70dfbf`.

## A10. Pre-registration (Phase B — BINDING once ruled)

Written before any Phase B work; every term traceable to a per-file measurement
or declared as pending.

| Term | Value | Source |
|---|---|---|
| ratchet ALLOWLIST entries | **9 → 9** (unchanged) | §A6.2 sweep: 0 new defs in scan scope |
| ratchet test count | 22 → 22 + N(detector arms) | pending per-file `--collect-only` before the commit |
| caps entries / cap / actual | per ruling (d) | §A5.5 |
| compare-bash | **3,046 / 26 EXACT, +0** | internal-integrity slot; pre-registered now |
| golden cases | **0 changes** | declaring one = fence |
| conformance | untouched | no user-visible change exists to document |


---

# PHASE B (under R1 rulings, md5 of inbox at GO `38ecb0fda63db5ad6e0d0bd3c4994ea4`)

## B1. Commits landed

| SHA | Scope |
|---|---|
| `2fc6c46d` | caps bookkeeping — ruling (d) option (i) |
| `862bfabc` | protocol witnesses + member narrowings — (c3), A2.3, A2.5/6/7, locale adoption, (e) #12 |
| `56dd3401` | ratchet instance-assignment arm — D-5B.1-s3 |

## B2. (c1) WITNESS SEARCH — ZERO, both arms. STOPPED per R1.

R1 authorized the search with a pre-ruled decision rule. Instrument 11 ran it
as specified, BOTH arms:

* **Arm A (parameters)** — every function taking a `ShellState`-typed
  parameter: **19 tree-wide** (this exactly reproduces the Checkpoint R census
  figure "255 Shell / 19 ShellState", so the scan is not under-finding), 13 of
  which use the binding at all. Sites whose usage is ⊆ {`get_variable`,
  `set_variable`, `get_special_variable`}: **0**. The single near miss is
  `executor/strategies.py:131 report_exec_failure`, which reads `get_variable`
  AND `error_location_prefix`.
* **Arm B (attributes)** — every class holding a `ShellState`-typed attribute,
  whose whole-class usage would have to fit for the attribute to be typed
  `VariableAccess`: **0**.

**ZERO clean sites across both arms → R1's stop branch.** Reported, not acted
on; no delete executed. `VariableAccess` remains defined-but-unused and is
registered as such in a committed shrink-only register
(`test_protocol_adoption_census_5b2.py#ZERO_CONSUMER_PENDING_RULING`), which
fails if it ever gains a consumer, so the entry cannot go stale. **R2 owes the
fate.**

## B3. (c2) FENCE — the ruled narrowing cannot land; ExpansionRuntime does not fit

R1 approved "at most ONE new narrow member typed `ExpansionRuntime`" to absorb
the eight `self.shell.expansion_manager` hops. Executed, and mypy refused it.
The two-level census I owed in Phase A and did not run:

| What the 8 hops actually call | Sites | In `ExpansionRuntime`? |
|---|---|---|
| `.subscript` | 4 | **no** |
| `.command_sub` | 2 | **no** |
| `.execute_arithmetic_expansion` | 1 | **no** |
| `.tilde_expander` | 1 | **no** |

`ExpansionRuntime` declares `expand_string_variables`,
`expand_assignment_value_word`, `variable_expander`, `word_expander` —
**overlap with the eight hops is ZERO**. The member would have served no site
at all, and the pinned "12 → exactly 3" reach was unreachable.

**My Phase A error, named:** §A2.2 measured the hops one level deep (that they
reach `expansion_manager`) and never asked what they call ON it. The ruling
rested on that gap.

The protocol is not wrong — its surface fits the SUBSCRIPT authority, which
consumes exactly three of its members and became its witness (`862bfabc`). It
does not fit these mixins, whose reaches are to the manager's sub-expanders.

Landed instead, within the ruling: the locale site migrated
(`self.shell.state.locale` → `self.state.locale`), taking `.shell` from 12
sites to **11**, pinned by `test_variable_expander_reach_5b2.py` (6 cells)
with the census in the member's docstring. The eight hops are D-5B.2-s2.

**Construction-order proof (R1 required it, instrument 12):** an eager
`self.expansion_runtime = shell.expansion_manager` would have raised —
`hasattr(shell, 'expansion_manager')` is **False** at `VariableExpander.
__init__` time, because `Shell.__init__` assigns it only after
`ExpansionManager.__init__` returns. Measured, not assumed; the property form
was the only viable shape.

## B4. (c3) executed — caller census decided the shape

Five call paths through `transfer_terminal_control` (`fg` builtin, two
SignalManager paths, JobManager's own restore, ForegroundJobSession) and only
ONE may publish. Moving the write in would have given four paths a write they
must not perform — two of them semantically wrong (SignalManager transfers to
the SHELL's pgid; JobManager's restore then sets `foreground_pgid = None`). So
R1's second branch: `publish_foreground_pgid(int)` on the producer,
`shell_state` deleted from the protocol. `EXPECTED_MEMBERS` updated (deliberate
ruled surface change).

## B5. Protocol-shape finding: mutable attributes are INVARIANT

A2.5 typed `ExpansionRuntime.variable_expander: "VariableExpanderProtocol"` and
Phase A measured it mypy-clean. That was clean only because the protocol had
ZERO consumers — nothing forced the structural check. The moment the
`SubscriptEvaluator` witness gave it one, mypy reported `ExpansionManager` as
non-conforming: a MUTABLE protocol attribute is invariant, so it demanded the
producer hold exactly `VariableExpanderProtocol` rather than the concrete
`VariableExpander` subtype. Both members are now read-only properties
(covariant); `get_protocol_members` still reports the same names, so the frozen
member set is unaffected. **A Phase A green that only meant "unobserved".**

## B6. D-5B.1-s3 — grammar CORRECTED, then landed

My Phase A design keyed the arm on the SOURCE (`self.<attr> = <full-Shell
param>`). Writing it exposed that this is **subsumed** by the shipped parameter
arm and can never fire independently: to assign `self.x = shell` the value must
BE a full-Shell parameter, and any function with one is already a hit.
Instrument 13 demonstrated it — 33 hits tree-wide, **0** of them new — and
showed the shape that IS invisible:

    def wire(self, s):     # unannotated AND not named 'shell' -> param arm silent
        self.shell = s     # only the FIELD's name reveals the reach

The landed arm keys on the assignment TARGET (attribute named `shell`/`_shell`,
bound to a bare NAME). The bare-name condition is what keeps
`self.mgr = shell.expansion_manager` and `self.state = shell.state` — the
migrations the campaign wants — from being flagged as the offence; that control
has its own cell.

Mutation battery (instrument 14, `PYTHONDONTWRITEBYTECODE=1`, every RED arm
asserting its REASON): **4/4 as designed** — A plant RED naming the def, B
narrowing GREEN, **C arm-neutered + offender GREEN** (proving A's red came from
this arm and not from something else), D `_shell` spelling RED. Files restored
byte-identical; post-restore ratchet green.

**ALLOWLIST 9 → 9 as pre-registered.** Test count 22 → 28.

## B7. CAPS — ruling (d)'s basis was FALSIFIED; (i) landed, (ii) NOT landed

**(i) landed** (`2fc6c46d`), exactly as pre-registered: 5 dead entries (−18
cap) + 2 slack trims (−3). entries 71 → **66**, cap 198 → **177**, actual 177,
slack 21 → **0**. Guard green.

**(ii) is STOPPED, because the verification I gave you did not cover the
change.** Instruments 06/09 verified hoistability by ADDING
`import psh.some.module` at module level. A real hoist MOVES the existing
statement, which is nearly always `from ..pkg.mod import Name` — and the two
differ exactly where it matters: `import X` tolerates a partially-initialised
X, `from X import Name` raises ImportError when `Name` is not yet bound. My
"ALL JOINTLY FEASIBLE" result was an artifact of the weaker form.

Instrument 15 performed the REAL edit (statements moved) for all 119: **the
tree does not import** — `cannot import name 'PatternCompiler' from partially
initialized module psh.expansion.pattern_engine`.

So **the approved figure (actual → 58) is wrong.** Re-derived empirically,
because no static predicate has survived contact with this question (five
attempts now):

| Measurement | Result |
|---|---|
| per-module, alone (instrument 16) | 50 of 51 modules feasible; only `psh.parser.parse_outcome` fails alone |
| all 119 together (instrument 15) | **fails** |
| maximal set by search (instrument 17) | exclude `psh.expansion.glob` (4 stmts) → **50 modules / 115 statements**, imports clean, shell smoke rc 0 |

**Achievable: actual 177 → 62** (not 58), cap → 62, slack 0.

Non-composition, demonstrated in BOTH directions: `parse_outcome` fails alone
yet succeeds inside the 115-set, and `glob` succeeds alone yet breaks the set.
This is exactly why R1's "the set that lands must BE the verified set" is the
right rule, and why I am not landing a 115-statement production change on a
basis that changed after the ruling.

**Timing (R1's stop condition, ~1.15×):** warm-vs-warm against an UNMODIFIED
control copy, median of 5 — control **69.1 ms**, hoisted **73.8 ms** =
**1.07×**. Under the line. (Still a live-worktree scratch measurement per B71;
re-measure detached if it is load-bearing.)

## B8. Pre-registration (per-file `--collect-only`, measured)

| File | before | after | delta |
|---|---|---|---|
| `test_shell_consumer_ratchet_q1.py` | 22 | **28** | **+6** |
| `test_import_layering.py` | 8 | 8 | 0 |
| `test_protocol_conformance_q1.py` | 7 | 7 | 0 |
| `test_protocol_adoption_census_5b2.py` | — | **5** | **+5** |
| `test_variable_expander_reach_5b2.py` | — | **6** | **+6** |
| **total** | | | **+17** |

Expected at the gate: **23,921 + 17 = 23,938** passed, 1,620 skipped, 10 xfail.
compare-bash **3,046 / 26 EXACT, +0**. ruff clean; mypy **276** clean.
(If caps (ii) lands, it adds NO tests — the figure is unchanged.)

## B9. Suites run so far (targeted, no gate yet)

| Selection | Result |
|---|---|
| `tests/unit/protocols tests/unit/tooling tests/unit/expansion` | 3510 passed, 17 skipped |
| `tests/unit/core tests/unit/executor tests/unit/scripting tests/unit/parser tests/integration/job_control` | **4202 passed**, 0 failed |
| `tests/unit/protocols tests/unit/tooling test_variable_expander_reach_5b2.py` (post-change) | 693 passed |

D-5B.1-s1 (the order-dependence flake): **not tripped** by any selection run.

## B10. Errata register

| # | Item |
|---|---|
| **I-1** | INTEGRATOR (R1, self-declared): the brief's subscript-ALLOWLIST "shrinks away" pre-registration was a reasoned-to figure. WITHDRAWN. |
| **D-1** | MINE: §A2.2 measured the `expansion_manager` hops one level deep and never asked what they call on it — the gap ruling (c2) rested on. |
| **D-2** | MINE: §A6's detector grammar was source-keyed and subsumed by the shipped param arm; it could not have reported anything new. |
| **D-3** | MINE: the caps hoist verification used `import X` where a real hoist uses `from X import Name`, so "all jointly feasible" did not cover the change. |
| **D-4** | MINE (Phase A, already recorded §A5.4): the 3.4× startup "regression" was cold bytecode compilation of a scratch copy, not hoisting. |
| **D-5** | MINE: A2.5's Phase A mypy-clean meant "unobserved" — the structural check only binds once the protocol has a consumer. |

---

# PHASE B PART 2 (under R2, inbox md5 at GO `bcf440509a97192e7e14a664f36ad527`)

## B11. CAPS (ii) — PRE-REGISTRATION, written BEFORE the commit (R2 condition 2)

Analyzer-derived from the VERIFIED tree (`tmp/maxhoist`), per-module terms
only — no reasoned-to figures (lesson 3). Full table:
`tmp/w5b2-transcripts/19_cap_diff_preregistration.out`.

| | entries | cap | actual | slack |
|---|---|---|---|---|
| before (at `56dd3401`) | 66 | 177 | 177 | 0 |
| **after** | **30** | **62** | **62** | **0** |
| delta | **−36** | **−115** | **−115** | 0 |

Composition of the entry delta, each term a per-module measurement:
**36 entries REMOVED** (their actual falls to 0), **14 LOWERED**, **16
UNCHANGED**. No module ends with `actual > 0` and no entry.

**R2 condition 1 (mechanical identity) — satisfied BOTH ways.** Instrument 18
re-runs instrument 17's transformation verbatim against the worktree and then
asserts every planned file is BYTE-IDENTICAL to the corresponding file in the
verified scratch tree, refusing to write if a single byte differs; after
applying it runs `diff -r` over the whole `psh/` tree as the second check.
Dry-run result: **50 modules / 115 statements, all byte-identical.**

**R2 condition 5 — the two deferred-on-purpose facts, recorded in the code**
where a future reader meets them: `psh.expansion.glob`'s 4 statements stay
deferred because hoisting them breaks the JOINT set (`ImportError: cannot
import name 'PatternCompiler' from partially initialized module
psh.expansion.pattern_engine`), and `psh.parser.parse_outcome` carries the
opposite note (fails ALONE, succeeds in-set) so nobody "fixes" it in isolation.

## B12. CAPS (ii) — **STOP LINE TRIPPED. Reverted. Caps stand at (i).**

R2 condition 4 was an automatic rule and it fired. Sequence, in full:

1. Instrument 18 dry-run: 50 modules / 115 statements, **every planned file
   byte-identical** to the verified tree. Condition 1 satisfied.
2. Cap-table diff pre-registered in §B11 BEFORE the commit. Condition 2
   satisfied.
3. Applied. `diff -r worktree/psh verified/psh` → **identical**, rc 0.
4. **SIXTH SURPRISE:** `ruff check psh tests tools` → **66 errors**. The
   mechanical move leaves imports at a position that violates the project's
   import ordering, and — worse — it strands the `# cycle-break:` comments that
   documented the very deferral it removed. `psh/parser/parse_outcome.py:106`
   was left asserting "Deferring the class import here keeps this peer outcome
   module import-clean" about an import now sitting at module level, plus a
   duplicate of that import under `TYPE_CHECKING`.

That is not a lint nit; it is the landing diff shipping documentation that has
become false. And repairing it is not available under the ruling: any fix makes
the landing diff NO LONGER byte-identical to the verified set, which condition
1 forbids. Verifying a repaired set would be the seventh attempt, which
condition 4 forbids by name.

**Reverted** — `git restore --source=HEAD --worktree` over exactly the 50
modified paths (enumerated from `git status --porcelain` first; list preserved
at `tmp/hoist-reverted-files.txt`). Post-revert: working tree clean of tracked
modifications, ruff clean, mypy 276 clean, layering guard 8/8, caps back at the
(i) floor — **entries 66, cap 177, actual 177, slack 0**.

**Caps delivery for this slot is option (i) only.** §B11's post-hoist table is
now a MEASUREMENT, not a pre-registration: it records that a 115-statement /
`actual → 62` hoist is available and import-verified, and that landing it needs
a step this slot did not have — a re-verified set that also carries the comment
and import-ordering repairs. That belongs to whoever owns the LOW row next.

**Honest note on the stop line's value:** the sixth surprise was found by a
lint run I would have made anyway, but the rule is what stopped me repairing
and re-verifying it on the spot. That would have been the seventh attempt in an
area where five of my six analyses had already been wrong.

## B13. (c1) DELETE executed — `403c8b01`

Protocol class + export removed; the interim zero-consumer register removed
with it (an empty register now means every exported protocol is genuinely
depended upon). Enumerating guards updated mechanically: protocol-layering
`__all__` set (5 → 4 names, test renamed off "five"), name-collision guard's
protocol set, conformance `EXPECTED_MEMBERS` + its `isinstance` cell, ratchet
docstring's protocol list, and both module docstrings de-named.

**Grep-zero pin committed** (`test_protocol_adoption_census_5b2.py`): zero
occurrences of the name anywhere under `psh/`, the protocol absent from
`__all__` and from the module namespace, plus a guard-the-guard cell proving the
same scan DOES find a live protocol name (so the pin cannot pass by not
reading). The name appears exactly once in the tree — in the pin that keeps it
gone. Committed evidence/CHANGELOG/LEDGER history untouched, per R2.
`ARCHITECTURE.md` NOT touched (integrator's at ceremony).

Design knowledge preserved per R2: the measured 11-member usage census lives in
`VariableExpanderProtocol.state`'s docstring, phrased without the deleted name,
pointing a future value-surface protocol at the real usage rather than the
three-member guess. Successor row D-5B.2-s1.

## B14. PRE-REGISTRATION — RECONCILED (per-file `--collect-only`, measured)

| File | before | after | delta |
|---|---|---|---|
| `test_shell_consumer_ratchet_q1.py` | 22 | 28 | **+6** |
| `test_import_layering.py` | 8 | 8 | 0 |
| `test_protocol_layering_q1.py` | 5 | 5 | 0 |
| `test_protocol_name_collision_q5.py` | 7 | 7 | 0 |
| `test_protocol_conformance_q1.py` | 7 | 6 | **−1** |
| `test_protocol_adoption_census_5b2.py` | — | 8 | **+8** |
| `test_variable_expander_reach_5b2.py` | — | 6 | **+6** |
| **net** | | | **+19** |

Supersedes §B8's +17: the (c1) delete removed the `isinstance` conformance cell
(−1) and the grep-zero pin added three cells to the census file (5 → 8). Every
term is a per-file count; none is reasoned-to.

**BINDING GATE PREDICTION: 23,921 + 19 = 23,940 passed, 1,620 skipped, 10
xfail.** compare-bash **3,046 / 26 EXACT, +0**. ruff clean; mypy **276** clean.
No golden-case or conformance change — this slot is annotations, signatures,
one moved write, and guards.

## B15. GATE + LEGS — all green, prediction EXACT

| Leg | Result |
|---|---|
| **Gate** (`tmp/gate-1.txt`, md5 `f1192da518be293ede75cdb6483cbedd`) | **23,940 passed / 1,620 skipped / 10 xfailed** — phase 1 parallel 22,823 + phase 1b serial 1,117. **Exactly the §B14 prediction (23,921 + 19).** |
| **compare-bash** (`tmp/compare-bash-1.txt`, md5 `3e69fba891321d0a6feeb771080123c6`) | **3,046 passed / 26 skipped** — EXACT, **+0**, as pre-registered |
| ruff (`psh tests tools`) | clean |
| mypy | **276** files clean |

ONE heavy run machine-wide: `pgrep -f pytest` and `pgrep -f run_tests` checked
UNPIPED before the gate and before compare-bash (both exit 1). The first gate
attempt was killed by the foreground limit mid-serial-phase and was RE-RUN to
completion in the sanctioned background-task form, not abandoned; the reported
figures are from the complete run.

**D-5B.1-s1** (order-dependence flake): NOT tripped — the gate is green and no
selection in this slot reproduced it.

**Divergence axis EMPTY, proven not asserted:** compare-bash moved by zero in
both directions, no golden case changed, no conformance file touched, and the
FLIP-PINS sweep (§A7) found no row touching this slot's subjects.

## B16. Never-touch verification (`git diff --name-only 1c70dfbf..HEAD`)

UNCHANGED, all seven: `psh/version.py`, `CHANGELOG.md`, `README.md`,
`ARCHITECTURE.md`, `docs/reviews/README.md`, `FLIP-PINS.md`, `LEDGER.md`.
The complete changed set is 21 files — 14 production, 7 test — and every one is
named in a commit above. No push, no PR, no tag.

## B17. Instrument manifest + discharge audit

Command-generated and self-excluding:
`tmp/w5b2-instruments/20_manifest_and_discharge.sh` →
`tmp/w5b2-transcripts/20_manifest_and_discharge.out`. **19 instruments**
(excluding self), each with its own md5 and its transcript's md5.

| Claim | Proof shape | Anchor |
|---|---|---|
| §A6 consumer counts (8 protocols) | census, per definition | instrument 01 |
| `state.locale` = 6 files / 13 sites | census × TWO independent methods | instrument 02 |
| all six readers inside `LocaleAccess` | census | instrument 03 |
| `core/scope.py` route needs no allowlist change | probe, guard's own analyzer | instrument 02 §3 |
| the 47-site / 11-member `.state` census | census | instrument 01 |
| the 12-site → 11 `.shell` census | census + committed pin | instrument 01, `test_variable_expander_reach_5b2.py` |
| eight hops call nothing in `ExpansionRuntime` | census (two-level) | §B3 |
| eager `expansion_runtime` attribute is impossible | live construction observation | instrument 12 |
| 12-param dispositions | measured per param | instrument 10 |
| `VariableAccess` has no possible adopter | census, both arms, denominator-checked | instrument 11 |
| s3 source-keyed grammar is subsumed | measured (33 hits, 0 new) + synthetic discriminator | instrument 13 |
| s3 arm bites, and its red comes from the arm | **mutation-proven 4/4, arm-neutered control** | instrument 14 |
| caps (i) figures | analyzer-derived, per-module | instrument 05/09 + guard |
| the 119-hoist set does NOT import | real-edit execution | instrument 15 |
| 115/62 set imports + runs | real-edit execution + smoke | instrument 17 |
| landing diff ≡ verified set | byte-identity + `diff -r` | instrument 18 |
| gate + compare-bash figures | run transcripts | `tmp/gate-1.txt`, `tmp/compare-bash-1.txt` |

## B18. Fault register (gap-free, all self-disclosed pre-verdict)

| # | Fault | Caught by | Corrected |
|---|---|---|---|
| D-1 | §A2.2 measured the manager hops one level deep; never asked what they call ON it — the gap ruling (c2) rested on | mypy, on executing the ruling | §B3; (c2) re-ruled as landed |
| D-2 | s3 detector grammar was source-keyed, subsumed by the shipped param arm | writing the real arm | re-keyed on the target; instrument 13 |
| D-3 | caps hoist verified with `import X` where the real edit is `from X import Name` | instrument 15 | re-derived; set falsified |
| D-4 | "3.4× startup regression" was cold bytecode compilation of a scratch copy | apples-to-apples re-measure | §A5.4 |
| D-5 | A2.5 "mypy-clean" meant UNOBSERVED (no consumer forced the check) | the witness landing | read-only properties |
| D-6 | the mechanically-hoisted tree fails ruff (66) and strands `# cycle-break:` comments that became false | ruff | **stop line tripped; reverted** |
| I-1 | INTEGRATOR: brief's subscript-ALLOWLIST "shrinks away" was reasoned-to | dev measurement | withdrawn in R1 |

Six of mine, all in instruments or analysis, none reaching a shipped artifact:
D-6 is the only one that reached the working tree, and it was reverted before
any commit.

## B19. Owed at close (NOT discharged by this slot)

| Item | Owner |
|---|---|
| `ARCHITECTURE.md` `VariableAccess` mentions (:98/:125 family) | **INTEGRATOR**, ceremony bump (R2) |
| D-5B.2-s1 — future value-surface protocol designs against the 11-member census | successor (5C+) |
| D-5B.2-s2 — the 8 manager hops WITH their member-call census + `evaluate_arithmetic`/`PromptExpander` signature migration | **5C.1** |
| LOW row remainder — the 115-statement / actual→62 hoist is available and import-verified; landing it needs the comment + import-ordering repairs and a re-verified set | successor owner of the LOW row |
| D-5B.1-s2 (mypy-guard stale endpoint) | 5C.1, untouched |

# B20. LEDGER FREEZE

This ledger is FROZEN at the final-tip declaration in D3.

**Chain rule:** this is the **FIRST freeze of slot 5B.2** — there is no previous
freeze md5 to quote. The freeze md5 is declared in D3 (a file cannot contain its
own hash).

---

# §B20 ADDENDUM (dated 2026-08-09) — LEDGER UNFROZEN UNDER R3, CORRECTED, REFROZEN

**Chain rule:** freeze-1 md5 was **`18609ed5bccedf7e1a74cb65d8e5fde8`** (declared
in D3). This ledger was unfrozen under R3 (BL-1 / RN-1), corrected as below, and
REFROZEN — freeze-2 md5 is declared in D5, quoting freeze-1 per the chain rule.

Verify-round outcome that occasioned it: 4 adversarial verifiers, verdict
**BOUNCE (narrow)** — diff-audit PASS, guards PASS, re-probe PASS, ledger
cross-check FAIL. The code substance stood: every published measurement
reproduced independently, every mutation bit for the right reason (including
shapes outside my battery), divergence axis empty on a 30-cell both-SHA bash
battery, zero false findings. **The bounce is entirely in this record layer,
and it is fair.**

## B20.1 BL-1 — §B18 called itself gap-free and was not. Corrected register.

§B18 summarised where it should have enumerated. Everything below was
self-disclosed in the ledger BODY before any verdict — §A5.4 admits the
predicate chain verbatim, §A1 names the alias blindness an instrument defect —
but a register that claims "gap-free" has to list rows, not gesture at prose it
sits above. The missing rows:

| # | Fault | Where it was already disclosed | Caught by | Corrected |
|---|---|---|---|---|
| **D-0** | **instrument 01 alias blindness** — the consumer census matched a `ClassDef` base against the protocol NAME and reported 0 consumers for three protocols §A6 records as 4/4/3. The real shape is the `_Base = Proto` TYPE_CHECKING alias | §A1, "Instrument defect, found before use" | disagreement with §A6's binding counts | alias resolution added; counts then reproduced 8/8 |
| **D-3a** | caps predicate **v1** — package-cycle question only; 136/177 "hoistable". Over-reports by construction: `package_edges` drops intra-package edges, so an intra-package hoist can never fail it | §A5.4 item 1 | implausible count | module-level cycle test added |
| **D-3b** | caps predicate **v2** — "introduces no NEW module-level cycle"; 119. Subtracted PRE-EXISTING cycles, so an edge hoisted INTO an already-cyclic region passed. A 94-edge SUBSET then failed to import where the full set had succeeded | §A5.4 item 2 | instrument 08's real import | ancestor expansion attempted |
| **D-3c** | caps predicate **v3** — ancestor-expanded; 0 hoistable, 177 forced. Over-corrected: with ancestors expanded almost everything reaches `psh/__init__` and lands in one SCC | §A5.4 item 3 | 0/177 result | predicate abandoned; empirical search adopted |

**Corrected arithmetic.** §B18's "six of mine" counted only the faults that had
register rows. The true count is **TEN of mine** — D-0, D-1, D-2, D-3a, D-3b,
D-3c, D-3 (the add-import-vs-move-import verification), D-4, D-5, D-6 — plus
**I-1** (integrator, withdrawn in R1). D3's separate phrasing "five of my six
analyses had already been wrong" was itself CONSISTENT (it counted analyses in
the caps area, not register rows); the register is what never caught up. Both
numbers now reconcile against this table.

**Nothing reached a shipped artifact.** Of the ten, nine were confined to
instruments or analysis; **D-6 alone reached the working tree and was reverted
before any commit**. That claim is unchanged by the correction — the correction
is to the count, not to the exposure.

**Post-freeze operational faults (folded in per R3 so the ceremony register can
cite ONE place):**

| # | Fault | Owner |
|---|---|---|
| **D-7** | **Watcher deadlock.** Two background waiters polled `[ -z "$(pgrep -f 'run_tests.py')" ]` while their own zsh command lines contained that literal string, so each kept the other's pattern matched — self-sustaining, neither able to observe its own exit condition. The gate was unaffected (it had already passed); only my observers hung, which is the worse shape because a stuck observer is indistinguishable from a running job. Integrator-diagnosed; PIDs killed. **Lesson: foreground what you wait on; when a poll is unavoidable, match the state you want, not the absence of a process your own watcher spells out.** | dev |
| **I-2** | **Stale-inbox crossing.** The unblocking nudge was composed against the post-R2 md5 while D3 was in flight, so it asked two questions D3 had already answered. Detected by md5 comparison at my end and corrected in D4. Self-disclosed by the integrator. | integrator |
| **D-8** | **RN-2 instrument seeding bug (this addendum's own round).** Arm B of instrument 21 seeded a dead cap entry with an unanchored `str.replace`, which also hit `print("FUNC_IMPORT_CAPS = {")` inside the file's regeneration block and produced a SyntaxError — pytest rc=4 (collection error), not the assertion failure the arm sought. **Caught precisely because the arm asserts its REASON rather than a non-zero exit** (5B.1 lesson 2 paying for itself); anchored to `\nFUNC_IMPORT_CAPS = {\n` with `count=1`, then 3/3. | dev |

## B20.2 RN-1 — §B17's instrument count contradicted its own anchor. Corrected.

§B17 said "**19 instruments** (excluding self)" while the anchor it cites prints
`instruments (excluding self): 18`. The anchor was right and the summary was
wrong: at the D3 tip `tmp/w5b2-instruments/` held 19 FILES, of which one is the
self-excluding manifest script itself, leaving **18**. All md5s were intact —
the verifier recomputed every one — so this was purely the summary layer
misreporting a truthful anchor.

**Two figures, because this addendum itself moved the number, and stating only
one would repeat the original error in the other direction:**

- **At the D3 tip (`403c8b01`), where §B17 sits: 18 excluding self** (19
  files). §B17's "19" was false there.
- **At this addendum's tip (`73b78983`): 19 excluding self** (20 files). RN-2's
  own RED demonstration added `21_zero_slack_cell_red_demo.py`, so the count
  legitimately rose by one. The manifest was REGENERATED after that commit and
  now prints `instruments (excluding self): 19`, which agrees.

The coincidence is worth naming so no future reader mistakes it for
vindication: §B17's "19" now matches the live count, but for a different reason
than the one it asserted, and it was false when written. Note also that the
numbering has a HOLE at 19 (see the provenance gap below), so instrument file
NUMBERS and file COUNTS do not correspond — which is part of how the original
miscount survived a glance.

**§B17's own text is deliberately left as it shipped.** The freeze forbids
in-place edits and R3 directed the correction here, so §B17 still reads "19
instruments (excluding self)" beside an anchor printing a different number.
That is not an oversight: this section is its correction of record, and a
struck-through history is worth more than a body that silently agrees with
itself. Same convention as the campaign's other struck-and-corrected rows.

Two provenance gaps in the same section, both now dispositioned:

- **`18_apply_hoist_to_worktree.py` has no transcript.** None exists, and the
  reason is substantive rather than an oversight: its output went to the
  terminal across a dry-run and an `--apply` run, and the change it applied was
  REVERTED under the R2 stop line, so no transcript could describe the tree that
  shipped. What survives is the evidence that matters — its byte-identity check
  against the verified tree and the post-apply `diff -r`, both quoted in §B11
  and §B12, and the revert totality (0 of 50 files modified) which the verify
  round independently reproduced. Recorded as transcript-less BY DISPOSITION.
- **`19_cap_diff_preregistration.out` has no generating instrument.** It was
  produced by an ad-hoc inline command, not a committed file — a violation of
  this campaign's "instruments are FILES from the start" rule, and I should have
  written it as one. The exact generating command is quoted below so the
  transcript is reproducible from the record:

      cd /Users/pwilson/src/psh-r5b-2 && PYTHONDONTWRITEBYTECODE=1 python - <<'PY' \
        > tmp/w5b2-transcripts/19_cap_diff_preregistration.out 2>&1
      # loads tests.unit.tooling.test_import_layering.{analyze_source,FUNC_IMPORT_CAPS},
      # walks tmp/maxhoist/psh/**/*.py, recomputes per-module deferred counts with the
      # guard's OWN analyzer, and prints the removed/lowered/unchanged split plus the
      # before/after entries-cap-actual-slack table.
      PY

  Its FIGURES were independently reproduced by the verify round (tip
  66/177/177/0, base 71/198/177 with the same five dead entries), so the
  provenance gap is a record defect, not a numbers defect.

## B20.3 RN-2 landed — the zero-slack property is now ENFORCED

`73b78983`. The docstring claimed every cap sits exactly on its module's count
while `test_function_level_import_ratchet` enforced only `count > cap`, so
headroom above a module's real count was invisible — a future deferred import
could reoccupy the drift this slot swept. Three verifiers converged on it
independently, and they were right: prose claiming what no guard enforces is
the NAME-VS-BODY family this campaign polices.

New cell `test_every_cap_equals_its_modules_actual_count` asserts `cap ==
actual` for every entry, splitting SLACK (cap > actual) from DEAD (module defers
nothing) so a failure names the module and the amount. RED-demonstrated in a
scratch copy, **3/3 arms reason-asserted** (instrument 21): cap 6→9 fails naming
the module and "slack 3"; a seeded dead entry fails naming it DEAD; the
unmodified control stays green. Per-file pre-registration taken BEFORE the
commit: `test_import_layering.py` **8 → 9 (+1)**, measured by `--collect-only`.
No new heavy run, per R3.

## B20.4 Carry wording corrected (no code)

- **D-5B.2-s2 is NINE manager hops, not eight.** The four mixin files hold 8 and
  the pin covers exactly those; `psh/expansion/variable.py:182` holds a NINTH in
  the concrete `VariableExpander` itself
  (`self.shell.expansion_manager.subscript.associative_key`), pre-existing at
  both SHAs and outside both the pin's four files and the ratchet's scan scope.
  Verified by tree-wide grep. The carry row states the family as **9**, with the
  pin's scope stated as the 8 mixin sites, so 5C.1 is not surprised by the
  ninth.
- **`state.foreground_pgid` is WRITE-ONLY in production.** Verified: writes at
  `job_control.py:358` (inside the new publish method), `:989` and `:1020` (the
  two reset-to-None paths); the only read is `ShellState.foreground_pgid`'s own
  property getter, which nothing calls. The verifier's neutering probe left 392
  job-control tests green — parity with base, which independently corroborates
  that the (c3) refactor is behavior-identical. Routed to **5C.2's dead-API
  census as a named candidate** (not acted on here; it is not this slot's).
- `ARCHITECTURE.md` :98/:125 stale name list: **integrator's** at the ceremony
  bump, re-confirmed by the verifier. Untouched by me.

## B20.5 REFREEZE

Frozen again at the state above. **Chain: freeze-1 md5 was
`18609ed5bccedf7e1a74cb65d8e5fde8`.** Freeze-2 md5 is declared in D5 (a file
cannot contain its own hash). Final tip after this round: **`73b78983`**.
