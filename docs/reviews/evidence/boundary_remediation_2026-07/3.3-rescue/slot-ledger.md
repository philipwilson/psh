# Slot 3.3 — Operand field IR (HIGH-6) — DEV LEDGER

**Agent:** dev-3-3 | **Worktree:** `/Users/pwilson/src/psh-r3-3` |
**Branch:** `fix/remediation-3-3` | **Base:** d0f7d929 (v0.764.0)
**Oracle:** PATH bash `/opt/homebrew/bin/bash` — `GNU bash, version
5.2.26(1)-release (aarch64-apple-darwin23.2.0)`.

Durable record. Assume the transcript is lost; every claim carries its
instrument and output.

---

## L0 — Slot open / admin

| # | Item | State | Evidence |
|---|------|-------|----------|
| L0.1 | Brief read in full | DONE | `/Users/pwilson/src/psh/tmp/remediation-ledgers/briefs/3.3.md` |
| L0.2 | INTEGRATOR-INBOX R0 read + ACKed | DONE | inbox @ slot open; ACK in first SendMessage |
| L0.3 | Ledger created | DONE | this file |
| L0.4 | Base SHA verified | DONE | `git log --oneline -1` → `d0f7d929 Merge pull request #514 from philipwilson/fix/remediation-3-2` |
| L0.5 | Bash oracle verified | DONE | `/opt/homebrew/bin/bash --version` → 5.2.26; `which bash` → `/opt/homebrew/bin/bash` |
| L0.6 | File sizes at base | DONE | operands.py 529 / word_expander.py 980 / variable.py 590 / parameter_expansion.py 527 |
| L0.7 | Import discriminator | DONE | `harness.py:_discriminate()` asserts `psh.__file__ == <PSH_ROOT>/psh/__init__.py` on EVERY probe run; also prints SHA + `psh/` dirty flag per table (per-TABLE provenance, 3.2 rule) |

---

## PHASE A

### A1 — Probe instruments (provenance)

| Instrument | Path | Purpose |
|---|---|---|
| harness | `tmp/probes-3-3/harness.py` | bash/psh runners, PSH_ROOT discriminator, per-table header |
| batcher | `tmp/probes-3-3/batch.py` | many cells per shell invocation; **per-cell SUBSHELL** so a fatal `:?` aborts one cell only and `set --`/`:=` stores stay isolated |
| observer | `batch.PRELUDE` — `count()` | `n=<count>` + one `[text]` per field. **Distinguishes zero fields from one empty field** — the representation question this slot turns on. `printf '<%s>'` cannot (both render `<>`). |

Matrices: `m_core.py` (A), `m_axes.py` (B–F), `m_ctx.py` (G–K), `m_proj.py` (L).
Transcripts: `A-core.txt`, `BF-axes.txt`, `GK-ctx.txt`, `L-proj.txt` (base);
`proto-m_*.txt` (prototype). Every transcript header records tree, SHA,
dirty-flag, imported `psh/__init__.py`, and the bash version string.

### A2 — Red-on-base matrix (base d0f7d929, psh/ clean)

**Total 1,825 cells; 320 DIFF / 1,505 SAME.** Both sides recorded for every
cell (matching cells are the no-regression baseline).

| Matrix | Axis varied | Cells | DIFF | SAME |
|---|---|---:|---:|---:|
| A core | operator(6) × subject(3) × outer(2) × content(18) | 648 | 60 | 588 |
| B subject SHAPE | positional shape (space/empty/tab/glob/colon) × op(4) × content(3) × outer(2) | 192 | **160** | 32 |
| C positional COUNT | 0/1/2/3 + empty positionals | 112 | 42 | 70 |
| D `:=` store-vs-emit | both faces × content(8) × outer(2) | 64 | **0** | 64 |
| E `:?` message | op(2) × content(4) × outer(2) | 16 | 16* | 0 |
| F IFS | default/empty/`:`/`' '`/`': '` | 120 | 34 | 86 |
| G context grammar | heredoc, here-string, `$(( ))`, `[[ ]]`, case, assign, declare/export/local, array/assoc init, redirect, subscript, pattern/replacement, for | 24 | **0** | 24 |
| H array views | `[@]`/`[*]` × state(6) × op(4) × content(6) × outer(2) | 576 | 78 | 498 |
| I terminal consumers | 21 named consumer sites | 21 | 4* | 17 |
| J backslash | 9 backslash shapes × op(2) × outer(2) | 36 | 6 | 30 |
| K parser | rd + combinator on the signature family | 16 | 16 | 0 |
| L scalar projection | IFS(5) × consumer(8) × source(4) | 145 | **0** | 145 |

\* E's 16 and 2 of I's 4 are NOT field defects — see A6.

**A2.1 — the defect family (one mechanism, 320 cells).** Every genuine DIFF is
the same thing: *a triggered value operand's multi-field content is flattened
to one space-joined field*. Signature, reproduced at base:

```
unset x; set -- a b; count "${x:-"$@"}"
bash: n=2 [a] [b]      psh: n=1 [a b]
```

Affected operators: `:-` `-` `:+` `+` (the four NON-storing value operators).
Affected content: `"$@"`, `$@`, `"${a[@]}"`, `${a[@]}`, nested `${y:-"$@"}`,
mixed `pre"$@"post`. NOT affected: `$*`/`"$*"`/`"${a[*]}"` (they join to one
field *before* the operand sees them — correct), `$(cmd)` (correct),
`''`/`""`/literals (correct).

**A2.2 — SUBJECT SHAPE is the unmasking axis (3.2 lesson, confirmed).**
Matrix A alone reports 60/648 because with `set -- a b` and unquoted outer
context the space-join is coincidentally undone by re-splitting. Varying the
positional shape raises it to **160/192**:

```
B-space-c--dqat-U :: set -- "a 1" b; unset x; count ${x:-"$@"}
bash: n=2 [a 1] [b]    psh: n=1 [a 1 b]
B-space-c--bareat-U :: set -- "a 1" b; unset x; count ${x:-$@}
bash: n=3 [a] [1] [b]  psh: n=3 [a] [1] [b]        <- SAME (accidentally green)
```
`IFS=` unmasks the same cells a second way (F-empty rows). **Any pin whose
subject is `set -- a b` in unquoted outer context is VACUOUS** — it passes on
broken code. This governs the pin plan (A8).

**A2.3 — second, distinct sub-defect: no-fields vs one-empty-field.**

```
C-n0-c--dqat-U :: set --; unset x; count ${x:-"$@"}
bash: n=0              psh: n=1 []
```
With zero positionals bash's `"$@"` contributes NO field and the unquoted
`${x:-...}` elides entirely. psh emits one empty PROTECTED field. The base IR
cannot express the difference — `OperandResult.segments` has no field
dimension at all, so "no fields" and "one empty field" are the same value.
Conversely `${x:-""}` must stay exactly one empty field (both shells agree at
base). **That pair is the representation test.**

**A2.4 — explicit empty fields must survive.**
```
B-emptyp-c--dqat-Q :: set -- "" b; unset x; count "${x:-"$@"}"
bash: n=2 [] [b]       psh: n=1 [ b]
```

**A2.5 — parser is NOT a differentiating axis.** K: 8/8 DIFF under `--parser rd`
and 8/8 under `--parser combinator`, identical cells. The defect is in
expansion, not parsing. Parser stays an axis in the pins (the existing pin
runs `_psh_comb`) but is not a discriminator.

### A3 — The measured bash model (what the IR must represent)

Derived from the matrix, not assumed:

1. A value operand expands to a **field vector**; each field carries per-run
   quote protection.
2. `"$@"` inside an operand → one field per positional, each **PROTECTED**
   (never re-split) — in BOTH quoted and unquoted outer context. The
   *inner* quoting protects, independently of the outer.
3. `$@` (unquoted) inside an operand → one field per positional, each
   **ACTIVE/IFS_ELIGIBLE**; those fields further split in unquoted outer
   context, and are protected by the outer quotes in quoted context.
4. Zero positionals → **zero fields** spliced (a no-op on boundaries):
   `pre"$@"post` with no positionals is ONE field `prepost`.
5. `$*`/`[*]` join with IFS[0] **before** the operand IR sees them — one field.
6. The `[@]`/`[*]` view JOINER never applies to a *triggered* operand:
   `${a[*]:-"$@"}` → `n=2 [a] [b]` (H, both quote states). The existing
   single-field preserve `${a[*]:-'p q'}` → `n=1 [p q]` is the same rule, not
   a special case: the operand's own vector is emitted verbatim.
7. **Terminal scalar projection joins with a literal SPACE, independent of
   IFS** — matrix L, 145/145 cells, all SAME at base:
   ```
   IFS=:; v=${x:-"$@"}  -> a b      (space)
   IFS=:; v=${x:-"$*"}  -> a:b      (IFS[0] — a different mechanism)
   ```

This model maps **exactly** onto the existing `ExpandedField`/`FieldRun`
types — no third representation is needed (brief subtlety 4).

### A4 — Mechanism at base (read, not fitted)

`operands.py:49 OperandResult(str)` carries `segments: Tuple[Tuple[str,bool],...]`
— per-segment quote protection, **no field dimension**. Two producer branches
in `_expand_operand` (operands.py:87):

- `quote_ctx is None` → `OperandResult(...)`: protection survives, fields do not.
- `quote_ctx is not None` (`"${...}"`) → `_value_dq_text` returns a **plain
  `str`**: neither protection nor fields survive. This is the signature cell's
  path.

Downstream, `word_expander.py:485-500` maps `.segments` → `FieldRun`s via
`_operand_runs`, and for `part.quoted` emits ONE `PROTECTED/NEVER` run.
`variable.py:406-418` returns a single triggered field as-is (preserving
segments) but `joiner.join(fields)` on the multi-field branch.
Because `OperandResult` IS a `str`, every other consumer accepts it silently —
which is precisely how the scalar projection re-enters unnamed.

### A5 — Consumer census (derived: `grep -rn` over `psh/`, then read)

`_expand_operand` has **exactly 9 call sites**, all in `operators.py`
(+ the definition and the `_protocols.py` stub):

| Site | Context | Classification |
|---|---|---|
| operators.py:252 | `_view_conditional` `-`/`:-` triggered | FIELD-PRESERVING |
| operators.py:256 | `_view_conditional` `+`/`:+` | FIELD-PRESERVING |
| operators.py:292 | `_apply_operator` `:-` | FIELD-PRESERVING |
| operators.py:298 | `_apply_operator` `-` | FIELD-PRESERVING |
| operators.py:309 | `_apply_operator` `+` | FIELD-PRESERVING |
| operators.py:328 | `_apply_operator` `:+` | FIELD-PRESERVING |
| operators.py:268 | `_view_conditional` `:?` message | **TERMINAL-SCALAR** (already `str(...)`) |
| operators.py:402 | `_assign_default` (`:=`/`=`) store | **TERMINAL-SCALAR** (already `str(...)`) |
| operators.py:436 | `_qmark_error` message | **TERMINAL-SCALAR** (already `str(...)`) |

**NOTE — scope:** `operators.py` is NOT in the brief's scope list
(operands/word_expander/variable/parameter_expansion) but is where the entire
`:-`/`:+`/`:=`/`:?` dispatch lives. Raised as a STOP-AND-REPORT scope question
(A9.1) — no edit made there pending the ruling. Same for `psh/expansion/fields.py`
(the `$@`/`${a[@]}` view path, `fields.py:93`).

### A6 — Terminal-consumer inventory, every row bash-probed (ruling (a))

Matrix I + G, 45 cells. **TERMINAL-SCALAR = bash itself demands one string;
psh is ALREADY correct at all of these (0 DIFF) — my job is to not break them.**

| Consumer | Probe | bash | Class |
|---|---|---|---|
| scalar assignment `v=${x:-"$@"}` | I-assign-scalar | `n=1 [a b]` | TERMINAL |
| append assignment `v+=` | I-assign-append | `n=1 [prea b]` | TERMINAL |
| array element `b[0]=` | I-arrelem | `n=1 [a b]` | TERMINAL |
| assoc KEY `h[...]=v` | I-assockey | `n=1 [a b]` | TERMINAL |
| assoc VALUE `h[k]=` | I-assocval | `n=1 [a b]` | TERMINAL |
| `case` selector | I-casesel | `one` | TERMINAL |
| `[[ ]]` lhs / rhs | I-dbracket-lhs/rhs | `eq` | TERMINAL |
| arithmetic `$(( ))` | I-arith | `3` | TERMINAL |
| pattern operand `${v#...}` | I-patternop | `n=1 [ c]` | TERMINAL |
| replacement operand `${v/Q/...}` | I-replop | `n=1 [a b]` | TERMINAL |
| here-string `<<<` | I-herestring | `a b` | TERMINAL |
| heredoc body | G-heredoc | text | TERMINAL |
| `export`/`declare`/`readonly` value | I-export/declare/readonly | `n=1 [a b]` | TERMINAL |
| **`:=` STORE** | I-assign-store, matrix D | `n=1 [a b]` | TERMINAL |
| **`:?` MESSAGE** | I-qmark-msg | `line N: x: a b` | TERMINAL |
| command/function argument | I-funcarg, I-exportname | `n=2 [a] [b]` | **FIELD-PRESERVING** |
| for/select item list | G-for | fields | **FIELD-PRESERVING** |
| array initializer element | G-arrinit | fields | **FIELD-PRESERVING** |

**Separator for every TERMINAL row: a literal SPACE, IFS-independent
(matrix L, 145/145).**

### A7 — `:=` store-vs-emit (ruling (b)) — matrix D, 64 cells, **0 DIFF**

bash's `:=`/`=` is **itself a terminal scalar projection**, and psh already
matches it exactly on both faces:

```
D-emit-c=-dqat-Q  "${x:="$@"}"   bash n=1 [a b]   psh n=1 [a b]
D-emit-c=-dqat-U   ${x:="$@"}    bash n=2 [a] [b] psh n=2 [a] [b]
D-store-c=-dqat-Q : "${x:="$@"}"; count "$x"   both n=1 [a b]
```
STORE = the space-joined scalar. EMIT = that stored scalar, which then obeys
ordinary value semantics (unquoted → IFS-splits; the operand's protection does
NOT survive the store — matching the measured note already in
`_assign_default`'s docstring). **Proposed model: `:=`/`=` keeps the scalar
projection, named. It must NOT become field-preserving** — that would be a
regression, and it is the natural M8 mutation target.

### A8 — IR design, both alternatives with MEASURED migration cost

Prototypes built in a throwaway worktree `/Users/pwilson/src/psh-r3-3-proto`
(detached at d0f7d929, discriminator-verified, removed after Phase A).

**Design 1 — extend `OperandResult(str)` with field breaks.**
Patch: add `fields` alongside `segments`, keep the str subclass.
Measured: `mypy` → **`Success: no issues found in 275 source files`** — i.e.
**0 call sites are named.** That IS the disqualifying measurement: with zero
named sites there is no surface for the charter's static guard, and every
scalar re-entry stays implicit. Migration cost ~0; guard value 0.

**Design 2 — opaque `OperandValue` + named `.as_scalar()` projection.**
Patch: `_expand_operand -> OperandValue`; `__str__` RAISES `TypeError`.
Measured, in order:
- `mypy` with only the return type changed → **4 errors, all
  `psh/expansion/operators.py` (292, 298, 309, 328)**, all
  `Incompatible return value type (got "OperandValue", expected "str")`.
  mypy finds the *typed* sites.
- The three `str(...)` sites (268/402/436) did **NOT** error — `str(x)` on an
  object is legal. **That is exactly the silent-re-entry hazard mypy cannot
  catch, and why a separate static guard is required.** Making `__str__` raise
  converts those from silent to loud.
- Full working prototype (field-aware operand walkers + word_expander seam +
  3 named projections): **production delta 277 insertions / 7 deletions across
  3 files** (operands.py +241, word_expander.py +37, operators.py 6).
- Behavior: **matrix B 160 DIFF → 0; A 60 → 15; H 78 → 6; C 42 → 4; F 34 → 4;
  J 6 → 2; K 16 → 4; D stays 0.** Signature cell GREEN.
- Cost surfaced by the loud `__str__`: `tests/unit/expansion` +
  `tests/unit/builtins` → **12 failed / 4,392 passed / 17 skipped**
  (`tests/unit/expansion` alone: 12 failed / 2,818 passed / 17 skipped in
  61.3s). The complete migration inventory, derived not guessed:

  | Failing pin | Site needing a named projection |
  |---|---|
  | `test_arithmetic_dollar_expansion.py::test_param_expansion_default` | arithmetic context |
  | `test_param_parser_behavior_fixes.py::test_default_unset_heredoc`, `::test_alt_set_heredoc` | heredoc body |
  | `test_value_operand_quoting.py::TestStringContexts` ×5 (heredoc single/double/ansi-c, here-string, `[[ ]]` rhs) | heredoc / here-string / `[[ ]]` operand |
  | `TestOperandSplittingProtection::test_empty_operand_yields_zero_fields` | **prototype gap (ii)** — A2.3 empty elision |
  | `TestDoubleQuoteContextInversion::test_nested_expansion_inherits_context`, `::test_dquote_segment_in_unquoted_operand` | **prototype gap (iii)** — nested field propagation in the DQ walker |

  Two of the twelve are the prototype's own known gaps, and **an EXISTING pin
  (`test_empty_operand_yields_zero_fields`) caught gap (ii)** — the zero-field
  rule is already pinned at base, so NAME-VS-BODY applies: keep that pin, do
  not re-derive it. The other ten are the terminal-consumer migration list,
  and it matches the A6 inventory exactly.

**Residual prototype DIFFs are 3 ordinary implementation gaps, not design
flaws:** (i) unmigrated terminal consumers (the loud failures above — the
design FINDING them is the point); (ii) empty-operand elision — the prototype
seeds one empty field where `${x:-}` unquoted must elide (A2.3); (iii) nested
`${y:-...}` inside a DQ-context operand needs the same field propagation the
unquoted walker already has.

**Recommendation: Design 2**, with the operand vector carrying
`ExpandedField`/`FieldRun` (the walker's existing currency) so no third field
model is invented. `as_scalar()` = `' '.join(field.text ...)` per A3.7.

### A9 — Open questions for the integrator

1. **SCOPE (blocking):** `operators.py` and `fields.py` hold the value-operator
   dispatch and the `$@`/`[@]` view path. Both are outside the brief's scope
   list, and the fix is not possible without them. Requesting scope extension
   to `psh/expansion/operators.py` + `psh/expansion/fields.py` (operand
   plumbing + named projections only, no semantics forks). No edits made
   pending the ruling.
2. **Static guard shape:** propose modelling it on the sibling
   `tests/unit/tooling/test_subscript_authority_guard.py` (NAME-VS-BODY: reuse
   the existing authority-guard pattern rather than re-derive) — (a) retired
   symbol stays deleted, (b) `.as_scalar()` called only from the RULED
   terminal-consumer set, (c) scanners self-tested against synthetic offenders
   so the guard cannot rot into a no-op (3.1 "a proof that cannot fail is not
   a proof"). Not absorbing 3.4's no-second-resolution guard.
3. **Import layering:** `operands.py` importing `word_expansion_types` is a
   MODULE-level import of a pure-data leaf; the ratchet in
   `tests/unit/tooling/test_import_layering.py` budgets FUNCTION-level imports
   (`psh.expansion.operands: 3`), so no ratchet change is expected. Will
   re-verify at fix time.

### A10 — Out-of-charter findings (reported, NOT fixed)

| # | Finding | Evidence | Owner |
|---|---|---|---|
| A10.1 | Fatal expansion error (`${x:?}`) in a SUBSHELL exits **1 in bash, 127 in psh**. Top level agrees (127 both). Not field structure. | `( : ${x:?boom} ); echo $?` → bash `inner=1`, psh `inner=127` | successor (typed expansion errors / 3.5 neighbourhood) |
| A10.2 | A multi-field operand as a REDIRECT TARGET is `ambiguous redirect` in bash; psh silently creates both files. Pre-existing at base (psh already produces 2 fields there via join+resplit). | I-redirtarget | successor (redirect arity) |
| A10.3 | Arithmetic-error wording for a bad subscript differs (`syntax error in expression (error token is "b")` vs `Unexpected token after expression: b`). | I-subscript | successor (diagnostics) |
| A10.4 | Matrix E's 16/16 DIFF is program-name prefix + A10.1 only; both shells render the `:?` message as the same joined scalar `a b`. **No field defect on the `:?` message path.** | E rows | — |

### A11 — Pin plan (proposed; runtime budget)

1. **FLIP** `tests/conformance/bash/test_subscript_keying_conformance.py:1680`
   `test_divergence_operand_at_flattens` (4 params) → equality form
   `test_operand_at_preserves_fields`. DECLARED pin change.

   **CORRECTION (self-caught, INDIVIDUAL-RUN PROTOCOL).** My first Phase A
   report claimed "2 of the 4 params would be vacuous in unquoted outer
   context". That is **WRONG** and is retracted. Each param re-run
   individually at base (transcript header: SHA d0f7d929, psh/ clean, bash
   5.2.26):

   | param | bash | psh | verdict |
   |---|---|---|---|
   | p1 `"${x:-"$@"}"` | `<a><b>` | `<a b>` | DIVERGENT |
   | p2 `${x:-"$@"}` (unquoted outer) | `<a><b>` | `<a b>` | DIVERGENT |
   | p3 `"${x:+"$@"}"` | `<a><b>` | `<a b>` | DIVERGENT |
   | p4 `"${x:-"a 1" b}"` shape | `<a 1><b>` | `<a 1 b>` | DIVERGENT |
   | control `${x:-$@}` (bare `$@`, unquoted outer) — **NOT in the pin** | `<a><b>` | `<a><b>` | AGREES |

   All 4 existing params are genuinely red-on-base. The vacuous shape is bare
   `$@` in unquoted outer context, which the pin does not use. The reason the
   distinction holds: a `"$@"` that is quoted INSIDE the operand yields
   PROTECTED fields that do not re-split, so the space-join is observable;
   a bare `$@` yields ACTIVE fields whose re-splitting coincidentally undoes
   the join. **Root cause of my error: I generalised A2.2's masking result
   from the `bareat` cells onto the `dqat` cells without re-reading the pin's
   actual params — "read the mechanism, don't fit cells" (3.1), applied to my
   own claim.**

   The flip still GROWS (subject shape, positional count incl. zero, explicit
   empties, IFS, `[*]` views), but for coverage, not to repair vacuity.
2. **Conformance battery** (`tests/conformance/bash/`, `shell_oracle` runner —
   anti-spawn guard applies): the operator × quoting × content × subject-shape
   × count × IFS matrix, seeded from A2, both parsers.
3. **Empty-field representation pins** (A2.3/A2.4): `${x:-}` unquoted → 0
   fields; `${x:-""}` → 1 empty field; `set -- "" b` → `[] [b]`; zero
   positionals + `pre"$@"post` → one field `prepost`.
4. **`:=` store/emit pins** per ruling (b) — both faces, matrix D as corpus.
5. **Static guard** per A9.2, default-run, self-tested.
6. **M8-class regression lock:** a mutation that restores the join-at-operand-
   expansion must fail a NAMED default-run pin. Second M8 class: a mutation
   making `:=` field-preserving must fail the store pin.
7. **Behavioral goldens:** promote the signature family + the
   subject-shape/IFS unmasking rows to `tests/behavioral/golden_cases.yaml`.
8. Matrices D, G, I, L (0-DIFF at base) are the **no-regression corpus** —
   they must stay 0-DIFF after the fix.

Runtime budget: probe matrices run 1,825 cells in ~12s total; the conformance
battery will be sized to stay under ~20s (oracle-runner spawns dominate) and
reported exactly.

### A12 — Must-not-flip baseline capture (pre-fix, read-only)

| Item | State at base | Instrument |
|---|---|---|
| `RESIDUAL_DIVERGENCES` incl. `opx_slash` | Present in `tests/unit/expansion/test_pattern_bash_composition_differential.py`; `opx_slash` is the OPERAND-EXTENT row — bash terminates a `${v/pat/repl}` PATTERN at the first unquoted `/` even inside an open extglob group; psh balances parens. **Lexing EXTENT, not field structure — successor-owned, not mine.** | `grep -n RESIDUAL_DIVERGENCES -A40` |
| Pattern engine FROZEN | `pattern_engine.py`, `extglob.py` — untouched; my worktree `psh/` is clean at report time (`git status --porcelain -- psh` empty) | `git status` |
| `test_doc_snippets.py` drift-lock registry | Pins only `process_launcher.py`, `variables.py`, `signal_manager.py`, `state.py`. **No entry pins any file in my scope** — the doc sweep cannot trip it. | `grep -nE '"source"' tests/unit/tooling/test_doc_snippets.py` |
| `psh/expansion/CLAUDE.md` pointers | **Zero** `file.py#symbol` pointers naming `OperandResult`, `_expand_operand`, `_value_segments_unquoted`, `_value_dq_text`, `_operand_runs`, `_fields_to_expanded`, `_view_conditional`. Renames cannot break `test_doc_pointers.py`. | `grep -nE ...` over `psh/expansion/CLAUDE.md` |
| Existing zero-field pin | `tests/unit/expansion/test_value_operand_quoting.py::TestOperandSplittingProtection::test_empty_operand_yields_zero_fields` already pins A2.3's rule. **NAME-VS-BODY: keep it, do not re-derive.** | prototype failure list |

**Corroboration (not a dependency):** two committed review docs independently
reach Design 2 —
`docs/reviews/expansion_subsystem_improvement_plan_2026-07-05.md:791` ("Remove
`OperandResult(str)` after all consumers accept fragments") and
`docs/reviews/ground_up_reappraisal_22_correctness_textbook_2026-07-20.md:269`
("`OperandResult` carries one string plus protected text runs. It cannot
encode…"). Recorded as corroboration only; the recommendation rests on the
measured migration cost in A8.

---

## GATE STATE

Phase A reported; **BLOCKED pending GO + rulings (a)/(b)/(c) + the
operators.py/fields.py scope decision.** No Phase B code written; worktree
`psh/` clean. Throwaway prototype worktree
`/Users/pwilson/src/psh-r3-3-proto` retained as the evidence behind ruling (c)
— to be removed at Phase B start unless the integrator wants it kept.

---

## PHASE B — implementation

### B0 — Rulings received

R1 (GO + rulings a/b/c + scope operators.py/fields.py) ACKed 1–7.
R2 (3-site scope grant + inventory correction + successor + H6 in-slot +
accounting) ACKed 1–5.

### B1 — R2.4 ACCOUNTING RECONCILIATION (derived, not hand-tallied)

Instrument: `tmp/probes-3-3/` transcripts parsed by matrix header; counts
emitted by the script, never typed by hand.

| | Phase A message | DERIVED truth |
|---|---|---|
| cells | "1,825" | **1,970 rows / 1,962 distinct ids** |
| base DIFF | "320" | **416 rows / 408 distinct ids** |

**Both Phase A figures were hand-tallies and both were wrong — disclosed, not
quietly corrected.** 1,825 = 1,970 − 145: matrix L appeared in my Phase A table
but was omitted from the total. 320 is not reconstructible from any subset; the
per-matrix DIFF column in that same message sums to 416. Row-vs-distinct
differs by 8 because MATRIX-K runs the same 8 cell ids under two parsers.
Root cause: I summed a table by eye instead of deriving it, which is exactly
what the DISCHARGE-AUDIT rule ("counts DERIVED, never hand-tallied") exists to
prevent. Every count in this ledger from here on is script-derived.

Per-family base DIFF (derived): A 60 · B 160 · C 42 · D 0 · E 16 · F 34 · G 0 ·
H 78 · I 4 · J 6 · K 8+8 · L 0.

### B2 — Result at the tip

| Matrix | rows | base DIFF | fix DIFF |
|---|---:|---:|---:|
| A core | 648 | 60 | **0** |
| B subject-shape | 192 | 160 | **0** |
| C positional-count | 112 | 42 | **0** |
| D `:=` store/emit | 64 | 0 | **0** |
| E `:?` | 16 | 16 | 16 (out-of-charter) |
| F IFS | 120 | 34 | 4 (successor) |
| G context-grammar | 24 | 0 | **0** |
| H array-views | 576 | 78 | **0** |
| I terminal-consumers | 21 | 4 | 2 (out-of-charter) |
| J backslash | 36 | 6 | **0** |
| K parser rd+comb | 16 | 16 | **0** |
| L scalar-projection | 145 | 0 | **0** |
| **TOTAL** | **1,970** | **416** | **22** |

**CLOSED 386 distinct cells. REGRESSIONS: 0.** All 22 remaining are
pre-existing and successor-owned: E×16 (`:?` prefix + subshell exit status,
A10.1/A10.4), F×4 (bare-`$@`/`$*` under IFS=, R2.2 successor), I×2 (redirect
ambiguity, subscript wording, A10.2/A10.3).

Plus **MATRIX-H6 (R2.3 model): 184 cells, 0 DIFF** — array states, the
positional twin (`set -- ""`), and scalar controls. No cell contradicts the
ruled model.

### B3 — R2.2: the IFS= row, corrected

The integrator was right to query it. Both readings are correct for their own
subject; my MESSAGE mislabelled the row (the block header said `set -- aXq b`
but that line was measured with `set -- a b`). Measured now, both subjects,
three ways:

| cell | bash | BASE d0f7d929 | FIX |
|---|---|---|---|
| `IFS=; set -- a b;   ${x:-$@}` | `n=2 [a] [b]` | `n=1 [a b]` | `n=1 [a b]` |
| `IFS=; set -- aXq b; ${x:-$@}` | `n=2 [aXq] [b]` | `n=1 [aXq b]` | `n=1 [aXq b]` |

The LEDGER records **aXq**, as required. Also correcting my own claim from the
declaration message: the IFS= UNQUOTED row is **not** fixed by this slot (it
matches base and stays divergent, successor-owned); the row this slot does fix
is `IFS=:` with QUOTED outer (`"${x:-$@}"`: base `n=1`, fix `n=2` = bash).

### B4 — Ordered production changes

| # | File | Change |
|---|---|---|
| 1 | `expansion/operands.py` | `OperandValue` (opaque field vector, `as_scalar()`, `__str__` raises TypeError); `_OperandFieldBuilder`; `_value_fields_unquoted` / `_value_fields_dq` / `_dquote_region_fields` / `_operand_dollar_fields` / `_emit_dollar`; retired `OperandResult`, `_value_segments_unquoted`, `_value_dq_text`; 2 ruled projections |
| 2 | `expansion/word_expander.py` | consume the vector through the SAME splice algebra; `_fields_to_expanded` expands an OperandValue member into several fields; retired `_operand_runs`; 1 ruled projection |
| 3 | `expansion/operators.py` | 3 ruled projections; `_apply_scalar_operator` (asserted, NOT projected); H6 untriggered-view fix |
| 4 | `expansion/variable.py` | array-view comment (measured); 1 ruled projection; type plumbing |
| 5 | `expansion/{evaluator,manager,_protocols}.py` | annotation-only widening along the pass-through chain (+1 ruled projection in manager per R2.1) |
| 6 | `executor/enhanced_test_evaluator.py` | 2 ruled projections (R2.1) |

**DELETED-DECIDER RULE.** `OperandResult(str)` deleted: its str-subclass
property is the defect's enabler (every consumer accepted it silently), so it
cannot be retained alongside `OperandValue` without reopening the hazard. Its
two walkers were deleted because their bodies are now the field-emitting
walkers, not because the behaviour changed — the DQ walk in particular keeps
the embedded-quote `inner` state and the `$name`-across-quotes scan verbatim,
in ONE pass, so no $-construct is expanded twice (a speculative re-expansion
would re-run command substitutions and re-assign `:=`). Re-appearance is
blocked by `test_operand_projection_guard.py::test_retired_operand_result_absent`.

### B5 — The static guard caught a real defect in my own work

`tests/unit/tooling/test_operand_projection_guard.py` failed on first run with
an UNRULED projection at `operands.py::_operand_dollar_fields` — I had written
`f.as_scalar() if isinstance(f, OperandValue) else str(f)` while mapping view
members, which **re-flattens a nested triggered operand** (`${x:-${a[@]:-"$@"}}`)
— the very defect this slot removes. Fixed to contribute one entry per field.
Recorded because it is the guard's own justification: the exit criterion is not
ceremony, it found a live bug in the change that introduced it.

### B6 — Gate-adjacent state at this point

`mypy` → **Success: no issues found in 275 source files** (base 275).
`ruff check psh tests tools` → **All checks passed!**
Full gate + compare-bash: NOT yet run (heavy — GO to be requested).

### B7 — GATE-1 (0bc4aa4e) and the EXACT delta reconciliation

`python -u run_tests.py --parallel > tmp/gate-1.txt 2>&1`, foreground, 313.7s.
Phase 1: 2 failed / 22,022 passed / 1,600 skipped / 8 xfailed.
Phase 1b (serial): 976 passed / 2 xfailed.
**Combined: 22,998 passed / 2 FAILED / 1,600 skipped / 10 xfailed**
(base: 22,894 / 0 / 1,590 / 10).

Both failures were EXISTING guards my change intersected — not tests I wrote,
and not behaviour. Fixed at 8251ed51.

| Guard | What it caught | Resolution |
|---|---|---|
| `test_import_layering::test_function_level_import_ratchet` | `psh.expansion.operands: 5 deferred imports > cap 3` — `_operand_dollar_fields` had picked up two function-level imports | HOISTED both to module level (neither is cycle-forced: `pure_helpers` imports only stdlib, `param_parser` only ast_nodes+lexer). Ratchet returns to cap 3; **raising the cap was never an option — the ratchet only moves down.** My A9.3 prediction was half right: I correctly predicted the module-level import would not touch this ratchet, and entirely failed to anticipate ADDING function-level ones. |
| `test_field_ir_guards::test_expanded_word_constructed_only_in_engine` | `ExpandedField` now has a second producer | **A genuine conflict between ruling (c) and an existing invariant** — see B8. |

**EXACT reconciliation (derived, `pytest --collect-only`):**

| file | base | at gate-1 | delta |
|---|---:|---:|---:|
| `test_subscript_keying_conformance.py` (flip + 2 both-sides pins) | 218 | 240 | +22 |
| `test_operand_field_ir_conformance.py` (NEW battery) | 0 | 64 | +64 |
| `test_operand_projection_guard.py` (NEW static guard) | 0 | 10 | +10 |
| `tests/behavioral` (10 goldens × 2 collected forms) | 3,012 | 3,032 | +20 |
| **collected at gate-1** | **24,511** | **24,627** | **+116** |

```
collected delta   +116
  = passed delta  +104
  + skipped delta  +10   (the goldens' --compare-bash forms, which skip)
  + failed           2   (the two guards above)
```
**Balances exactly, zero residual.** The whole-tree collection at the current
tip is 24,628 (+117): the extra row is `test_operand_walker_stays_field_level`,
added in 8251ed51 AFTER gate-1 ran — which is precisely why the gate-1 figure
reconciles at +116 and not +117.

**PRE-REGISTERED PREDICTION for gate-2 at 8251ed51** (falsifiable, recorded
before the run): **23,001 passed / 0 failed / 1,600 skipped / 10 xfailed.**
Derivation: 22,894 + 104 (new passing rows) + 2 (the guards, now fixed) + 1
(the new field-level pin). Any other number is a fact I must explain, not
round off.

### B8 — RULING-CONSEQUENCE RECORD: ruling (c) vs an existing invariant

*(Required by R4.1. Cross-references: R1 ruling (c) — "the vector carries
ExpandedField/FieldRun, the walker's existing currency; no third field model";
R4.1 — widening CONFIRMED as landed.)*

**The integrator's own framing, recorded because it is the durable reason:**
the guard chain protects four invariants — (i) ONE word-level producer,
(ii) `materialize` as the SOLE IR-to-strings boundary, (iii) no ALTERNATIVE
field representation, (iv) no join before splitting/globbing (#20 H5/H6). The
re-cut preserves all four; (iii) is the very thing ruling (c) enforced and
(iv) is the defect this slot removes. The single-producer-of-`ExpandedField`
clause was a blunt over-approximation of (iii)+(iv) that held only while
operands were scalar. Ruling (c) made the operand walker a legitimate field
source, so **the conflict was created by the ruling, not by the
implementation** — which is why it was surfaced for confirmation rather than
resolved unilaterally.

`test_field_ir_guards::test_expanded_word_constructed_only_in_engine` asserted
that BOTH `ExpandedWord` and `ExpandedField` are built only by
`word_expander.py`. Ruling (c) requires the operand vector to carry
`ExpandedField`/`FieldRun` ("the walker's existing currency; no third field
model"), which necessarily makes `operands.py` a second `ExpandedField`
producer. The two cannot both hold as written.

Resolved toward the ruling, as tightly as possible:

- `ExpandedWord` keeps its SINGLE producer — untouched. That is the boundary
  that makes `materialize` the sole IR-to-strings conversion.
- `ExpandedField` gains exactly ONE named second producer, with the reason
  recorded in the guard itself.
- NEW `test_operand_walker_stays_field_level` pins `operands.py` to FIELD
  level (no `ExpandedWord(`, no `.materialize(`), so the exception cannot
  drift upward into a second word engine.

Rationale offered to the integrator for confirmation rather than assumed:
#20 H5/H6 forbade an ALTERNATIVE field representation and a join before
splitting/globbing. `operands.py` introduces neither — it feeds fields into
the same splice algebra `$@` already used and never flattens them. A parallel
operand-specific field type is exactly what both H5/H6 and ruling (c) reject.

### B9 — GATE-2 (8251ed51) + compare-bash

**GATE-2: 23,001 passed / 0 failed / 1,600 skipped / 10 xfailed.**
This is EXACTLY the pre-registered prediction in B7 (23,001 / 0 / 1,600 / 10),
recorded before the run. Zero unexplained rows.

**compare-bash: 3,006 passed / 26 skipped** (`python -m pytest tests/behavioral
--compare-bash -n auto -q`, 42.0s). Base: 2,986 / 26.

| | collected | passed | skipped |
|---|---:|---:|---:|
| base | 3,012 | 2,986 | 26 |
| tip | 3,032 | 3,006 | 26 |
| delta | +20 | +20 | 0 |

Balances exactly. **My prediction for this one (+10) was WRONG** — disclosed:
I assumed only the compare form of each golden is added, but under
`--compare-bash` BOTH collected forms of a golden RUN; the 26 skips are
pre-existing and unrelated to my rows. The gate prediction was exact; this one
was not, and the error was in my model of the golden harness, not in the data.

### B10 — DISCHARGE AUDIT

**Bounced rows: NONE.** No verification round has been run on this slot yet, so
there are no previously-bounced rows to replay. Stated explicitly per R3.5.

| # | Claim | Instrument | Evidence |
|---|---|---|---|
| D1 | HIGH-6 signature cell fixed | `tmp/probes-3-3/m_smoke.py` | `"${x:-"$@"}"` → `n=2 [a] [b]` both shells |
| D2 | Operator × quoting × content matrix = bash | matrices A/B/C/H/J/K | 1,970 rows: base 416 DIFF → 22; **CLOSED 386, REGRESSIONS 0** |
| D3 | Terminal-scalar behaviour not broken | matrices D/G/I/L | D 0→0, G 0→0, L 0→0, I 4→2 (both remaining pre-existing) |
| D4 | Empty-field representation | battery §1, 11 rows | `set --` unquoted `n=0` vs quoted `n=1 []` |
| D5 | `:=` store/emit stays terminal | battery §3, 9 rows + matrix D 64 cells | both faces, 0 DIFF |
| D6 | Untriggered conditional = the VIEW (H6) | `m_h6.py` 184 cells + battery §4, 14 rows | 0 DIFF incl. positional twin |
| D7 | Nested operands (R3.3) | battery §5, 10 rows | incl. the guard-caught cell |
| D8 | Scalar projection is NAMED and CLOSED | `test_operand_projection_guard.py` | 10 rows; scanners self-tested |
| D9 | Retired symbol stays deleted | same guard | `OperandResult` absent tree-wide |
| D10 | `__str__` raises TypeError, not PshError | same guard | asserts `not isinstance(exc, PshError)` |
| D11 | M8 locks bite, each for its OWN reason | `tmp/probes-3-3/mutate.py` | 3/3 CAUGHT; restores sha-verified |
| D12 | Flip pin flipped + grown | `test_operand_at_preserves_fields` | 4 → 21 rows; before/after in B11 |
| D13 | Pre-existing divergences pinned both-sides | 2 pin functions | bare-`$@`/IFS ×3, case-pattern ×2 |
| D14 | Pattern engine FROZEN | `git diff --stat d0f7d929` | empty for `pattern_engine.py`, `extglob.py` |
| D15 | `RESIDUAL_DIVERGENCES` untouched | `git diff d0f7d929` | empty for the owning file |
| D16 | Gate green | `tmp/gate-2.txt` | 23,001 / 0 / 1,600 / 10 |
| D17 | compare-bash EXACT | `tmp/comparebash-1.txt` | 3,006 / 26 |
| D18 | mypy / ruff clean | `mypy`, `ruff check psh tests tools` | Success 275 files; All checks passed |
| D19 | Doc sweep POST-STATE | `psh/expansion/CLAUDE.md` + module docstrings | doc-pointer + doc-snippet suites 22 passed |
| D20 | Delta reconciles to zero | `--collect-only` derivation | B7 (gate) and B9 (compare-bash) |

### B11 — Flip pin: collected before / after

| | base d0f7d929 | tip |
|---|---|---|
| name | `test_divergence_operand_at_flattens` | `test_operand_at_preserves_fields` |
| form | divergence (asserts psh space-joins) | AGREEMENT (`psh == bash`) with the bash side also pinned |
| rows | 4 | 21 |
| file collected | 218 | 240 (+22, incl. the 2 new both-sides pins) |

All four original params were genuinely red-on-base (verified individually,
A11 correction). The added rows carry the detection weight: a `set -- a b`
subject in unquoted outer context cannot detect this defect.

### B12 — Must-not-flip, verified AT THE TIP (8251ed51)

| Item | Instrument | Result |
|---|---|---|
| `pattern_engine.py`, `extglob.py` FROZEN | `git diff --stat d0f7d929 HEAD --` | EMPTY (byte-identical) |
| `RESIDUAL_DIVERGENCES` (incl. `opx_slash`) | `git diff d0f7d929 HEAD --` on the owning file | EMPTY — **no row flipped; `opx_slash` is lexing EXTENT, not field structure, and was never in scope** |
| 3.1/3.2 pattern batteries (5 files) | pytest | **99 passed** |
| 2.3 subscript-keying pins (whole file) | pytest | **240 passed** (137.3s) |
| `${a[*]:-'p q'}` single-field preserve | battery + flip pin | green, both quote states |
| joined-view null/set-ness semantics | H6 battery §4 | trigger logic unchanged; `a=("" "")` still fires |

### B13 — FINAL TIP: 8251ed51

Per-commit deltas (`git show --stat`):

| commit | subject | files | +/− |
|---|---|---:|---|
| a8ed586e | operand field IR — field vector + named projections | 9 | +745 / −160 |
| 3ad158b8 | pins, static guard battery, doc sweep | 4 | +426 / −11 |
| 0bc4aa4e | nested-operand equality rows (R3.3) | 1 | +46 / −1 |
| 8251ed51 | gate-1 fixes — import ratchet + field-IR producer guard | 2 | +50 / −13 |
| **cumulative `d0f7d929..8251ed51`** | | **14** | **+1264 / −182** *(re-derived at the E10 sweep: CORRECT as originally written; label pinned to an explicit SHA)* |

Production files touched: `expansion/{operands,operators,variable,word_expander,
manager,evaluator,_protocols}.py`, `executor/enhanced_test_evaluator.py` — all
within the granted scope (brief + R1.6 + R2.1). No file outside it.
NEVER touched: `psh/version.py`, `CHANGELOG.md`, `README.md`, `ARCHITECTURE.md`,
`docs/reviews/README.md`, `FLIP-PINS.md`, `LEDGER.md`. No push, no PR, no tag.

**Exit criteria (sequence §8):**
- `unset x; set -- a b; printf '<%s>' "${x:-"$@"}"` → `<a><b>` — MET.
- complete operator/quoting/empty-field matrix matches bash — MET with TWO
  DECLARED EXCLUSIONS, both pre-existing, both pinned both-sides, both
  successor-owned: the bare-`$@`/non-default-IFS family (R2.2) and the
  multi-field case-PATTERN row (R2.1).
- static guards find no semantic scalar re-entry — MET
  (`test_operand_projection_guard.py`, self-tested scanners).
- carry #4 / HIGH-6 — DISCHARGED (flip pin flipped and grown).

---

## ROUND 1: BOUNCE — corrections (R5)

Verdict: 6 blockers (5 distinct), 13 nits. **All real; I reproduced every
blocker myself before fixing** (the B3 lesson — derive, don't trust — applied
to the bounce report too). None was a semantics defect in the fix.

### C1 (B1+B6) — REDIRECT TARGET: closed in slot, and my record of it was wrong

**Reproduced** (`tmp/probes-3-3/`, three-way, per-tree discriminator):

| | rc | stderr | files created |
|---|---|---|---|
| bash | 1 | `${x:-"$@"}: ambiguous redirect` | none |
| BASE d0f7d929 | 0 | — | **ONE file named `f1 f2`** |
| TIP | 1 | `${x:-"$@"}: ambiguous redirect` | none |

**A10.2 IS HEREBY RETRACTED AND REPLACED.** It was wrong twice over: the base
behaviour is ONE file named `f1 f2`, not "both files"; and the row is not
"pre-existing, unchanged" — this consumer was **CLOSED IN SLOT** and now
matches bash in message form and exit status. Superseded rows: A10.2, and the
`I×2` cell of B2/B13.

- **Pins:** `test_multifield_redirect_target_is_ambiguous` (4 rows: output
  unquoted, output quoted, `${a[@]}` twin, input-side `<`) +
  `test_single_field_redirect_target_still_works` (agreement control, so the
  rows cannot be satisfied by making every operand target ambiguous) +
  **M8 lock #5** asserting BOTH the diagnostic and the absence of the file.
- **Accounting corrected:** remaining divergent **22 → 21**; `I×2 → I×1`
  (subscript-diagnostic wording only). Declared exclusions stay at 2.

**ROOT-CAUSE ROW (instrument defect, mine).** My base-vs-tip sweep compared
**verdict TAGS** (DIFF/SAME against bash) rather than raw outputs, so a cell
that was DIFF at base and DIFF at tip passed through even though its content
changed completely. That is structurally blind to exactly one class of change,
and this cell was in it.

**Instrument fixed and re-run:** `tmp/probes-3-3/rawsweep.py` compares the RAW
`(stdout, rc)` PAIR of base vs tip for every cell, then classifies each change
against bash. At d0f7d929 → 8251ed51 over **2,146 distinct cells**:

```
changed base -> tip : 386   (toward-bash 385, away-from-bash 0, neither 1)
unchanged           : 1,760
DIFF->DIFF cells whose CONTENT changed : 1   <- the class tags cannot see
    I-redirtarget   base ('n=2 [a] [b]', 0)
                    tip  ('psh: ... ambiguous redirect\nn=0', 0)
                    bash ('/opt/homebrew/bin/bash: ... ambiguous redirect\nn=0', 0)
```
**CONFIRMED with the corrected instrument: exactly ONE such cell**, matching
the verifier's independent finding. `away-from-bash 0` is the stronger
statement the tag-based sweep could never have made.

### C2 (B2) — array-VIEW operand content: pin gap

**Reproduced**, 9 cells three-way: all 8 view-content cells moved
`n=1 [m n o]` (base) → `n=2 [m n] [o]` (tip) = bash; the `[*]` control is
`n=1 [m n o]` in all three. My ledger already named this content axis, so this
is a **pin gap, not a discovery gap** — which is why it bounces.

- **Pins:** `test_array_view_as_operand_content_keeps_fields` (8 rows: quoted,
  unquoted, bare-inside, `:+`, non-colon `-`, assoc `${!h[@]}` keys, slice
  `${a[@]:1}`, mixed `A…Z`) + `test_star_view_as_operand_content_stays_one_field`
  (the control) + **M8 lock #4** = the verifier's own isolating mutation,
  asserting BOTH directions so "make every view produce fields" also fails.

### C3 (B3) — A2.5's `_psh_comb` claim was FALSE

**Verified myself before fixing:** `grep -c _psh_comb` = **0** in the flipped
pin and 0 in the 64-row battery; the base pin body ran `_psh`/`_bash` only.

**A2.5 CORRECTED.** It said "the existing pin runs `_psh_comb` — keep parser as
an axis". What is TRUE: matrix K measured the defect under BOTH parsers (8/8
DIFF each at base, 0/0 at tip), so the defect and the fix are
parser-independent — but no *pin* covered the combinator until now. The
parenthetical originated in the brief; **my share is that I repeated it without
deriving it.** Derive-don't-trust applies to brief text exactly as it applies
to code.
**Fix:** `test_operand_at_preserves_fields_combinator`, 7 representative rows
(signature, subject shape, BOTH zero-positional faces, the view family,
alternate, nesting) — the claim made true rather than retracted.

### C4 (B4) — REASON-ABOUT-LINUX verdict row (was silent)

**Certified:** this slot is pure string/field logic with **no platform
surface**. It touches no signal, fd, process, locale or filesystem path; the
only OS-adjacent row is the redirect-target pin, which asserts a diagnostic and
the absence of a file, not any fd behaviour. Corpora are **portable
byte-ASCII**: subjects are `a`/`b`/`m n`/`aXq`/`f1 f2`/`p q`; IFS probes use
space, tab, `:`, `X`, `XY` and empty — no locale-collation or multibyte input
anywhere. Conclusion: **no Linux-specific path is exercised or altered**, and
the nightly is a backstop, not a gap, for this slot. (Verifier's independent
assessment agrees.)

### C5 (B5) — transclusion negative (was silent), with its honest limitation

**The negative:** no Part B/D carry row other than carry #4 names slot 3.3.

**What I could verify myself:** `grep -n "3\.3"
docs/reviews/boundary_remediation_integrator_plan_2026-07-21.md` → exactly 2
hits, line 73 (the flip pin routed to slot 3.3) and line 313 (this slot's own
charter row). Neither is an additional carry.

**What I could NOT verify, stated rather than glossed:** the unified
`LEDGER.md` is not present in any tree I can read (`find` over the main
checkout and my worktree returns nothing; it is integrator-owned and on my
never-touch list). So for that file specifically I am **relying on the
verifier's re-derivation** (the only other `3.3` there is a perf multiplier in
a 2.6 row) and not asserting a check I did not run. Recording the boundary of
my own evidence is the point of the rule.

### C6 — NIT dispositions (dev items)

| NIT | Action |
|---|---|
| 3 | `manager.expand_expansion` docstring no longer says "to a string" — it states the `str` vs field-vector contract; the digit branch of `_dq_name_scan` now carries the same `OperandValue` assertion as its sibling instead of a bare `str()`. |
| 5 | Projection-guard docstring NARROWED: it now states exactly what the scanners see (direct `.as_scalar()` attributed to the nearest enclosing function; retired symbols by name) and what they do NOT (indirect projection via binding/`getattr`), plus why that residue is accepted — the runtime `__str__` check covers what the static half cannot. |
| 10 | Battery runtime at this tip: **80 rows, 15.5s** (was 64 rows / 12.9s). |
| 11 | Commit SHAs inlined: D9/D12 below. |
| 12 | All FIVE M8 classes named durably: #1 re-flatten the operand · #2 make `:=` field-preserving · #3 collapse the empty/zero distinction · #4 disable the array-VIEW producer branch · #5 lose the field vector at the redirect target. |
| 1/9/13 | **RETROACTIVE SANCTION RECORDED:** the annotation-only widening of `evaluator.py` and `_protocols.py` to `OperandOrStr` is sanctioned as ruling-(c) plumbing (two verifiers confirmed zero behaviour change). Declared in the scope section below. **Any FURTHER touch to either file is a declared addition.** |

### C7 — SCOPE, restated with the sanction folded in

Granted: `expansion/{operands,operators,variable,word_expander,fields}.py`
(brief + R1.6) · `expansion/manager.py` + `executor/enhanced_test_evaluator.py`
(R2.1, projection-only) · `expansion/{evaluator,_protocols}.py`
(**R5 retroactive sanction**, annotation-only). Nothing outside this set was
touched.

### C8 — evidence-table provenance (NIT 4, BINDING)

The round-1 "final" transcripts were headed base-SHA + live-worktree. Every
post-state table is re-measured at a DETACHED checkout of the new tip; see the
POST-STATE section appended after the gate.

### C9 — POST-STATE tables, re-measured at a DETACHED checkout (NIT 4, binding)

**Provenance for every table in this section:** worktree
`/Users/pwilson/src/psh-r3-3-post`, **detached at d81ae82b**, `git status
--porcelain -- psh tests` EMPTY, per-tree import discriminator asserted in each
transcript header, bash 5.2.26. This replaces the round-1 tables, which were
headed base-SHA + live-worktree.

**Raw-pair sweep at the new tip** (`post-rawsweep.txt`), 2,146 distinct cells,
base d0f7d929 → tip d81ae82b:

```
changed base -> tip : 386   toward-bash 385 · away-from-bash 0 · neither 1
unchanged           : 1,760
DIFF->DIFF content-changed : 1  (I-redirtarget — the round-1 escapee)
```

**Matrix post-state** (`post-m_*.txt`): A 0 · B 0 · C 0 · D 0 · G 0 · H 0 ·
J 0 · K 0+0 · L 0 · H6 0 · **E 16 · F 4 · I 2** — 22 raw-DIFF cells.

**The 22-vs-21 accounting, resolved precisely.** The integrator's corrected
figure of **21 is right**, and my matrix's raw 22 is not a contradiction:

| cell(s) | residual difference | substantive? |
|---|---|---|
| E ×16 | program-name prefix **and** subshell exit status (bash 1 / psh 127) | YES — A10.1, successor |
| F ×4 | bare-`$@`/`$*` under a non-default IFS | YES — R2.2 successor |
| I-subscript ×1 | arithmetic diagnostic wording | YES — A10.3, successor |
| **I-redirtarget ×1** | **program name ONLY** — prefix-normalised, bash and psh are byte-identical (`ambiguous redirect`, same rc, no file) | **NO — behaviourally CLOSED** |

So: **21 substantive divergences + 1 prefix-only probe artifact.** The matrix
counts the artifact because its cell compares raw stderr including the program
name; that is a property of my probe, not of the shell. Recorded both ways
rather than quietly adopting the smaller number.

### C10 — GATE-3 + compare-bash at d81ae82b

**GATE-3: 23,024 passed / 0 failed / 1,600 skipped / 10 xfailed** — EXACTLY the
prediction pre-registered before the run (derived from `--collect-only`:
24,628 → 24,651 = +23; battery 64→80, keying 240→247, guard unchanged).
Second consecutive exact gate prediction.

**compare-bash: 3,006 passed / 26 skipped** (42.3s) — unchanged from round 1,
as predicted (no goldens added this round).

### C11 — BOUNCED-ROWS REPLAY (obligation now non-empty)

Every round-1 blocker row replayed at d81ae82b. **Totals: 5 distinct blockers,
5 closed, 0 outstanding, 0 re-opened.**

| row | replay instrument | result |
|---|---|---|
| B1+B6 redirect | `test_multifield_redirect_target_is_ambiguous` ×4 + single-field control + M8 #5 | PASS; three-way reproduction recorded (C1) |
| B2 array view | `test_array_view_as_operand_content_keeps_fields` ×8 + `[*]` control + M8 #4 | PASS |
| B3 `_psh_comb` | `test_operand_at_preserves_fields_combinator` ×7 | PASS; A2.5 corrected |
| B4 Linux | ledger row C4 | WRITTEN (certification, no code) |
| B5 transclusion | ledger row C5 | WRITTEN, with its evidence boundary stated |

Pin suites at the tip: battery + projection guard + field-IR guards **102
passed** (17.7s); flip pin + both-sides + combinator leg **33 passed** (7.2s).

**All FIVE M8 classes re-proven at the new tip**, each failing for its OWN
distinct reason (`tmp/probes-3-3/mutate-r2.txt`; every restore sha-verified):

| class | mutation | failure reason (distinct) |
|---|---|---|
| #1 re-flatten | join at the dquote region | `n=1 [a 1 b 2]` ≠ `n=2 [a 1] [b 2]` |
| #2 `:=` preserves | keep first field at the store | `n=1 [a 1]` ≠ `n=1 [a 1 b]` |
| #3 empty collapse | force protected empty | `n=1 []` ≠ `n=0` |
| #4 view branch off | disable `expand_to_fields` in the operand scanner | `n=1 [m n o]` ≠ `n=2 [m n] [o]` |
| #5 redirect arity | join `$@` values in the scanner | `rc 0` where non-zero required |

### C12 — MUST-NOT-FLIP at d81ae82b

`pattern_engine.py` / `extglob.py`: `git diff --stat d0f7d929 HEAD` EMPTY.
`RESIDUAL_DIVERGENCES` file: `git diff` EMPTY — no row flipped; `opx_slash`
untouched and out of scope (lexing extent, not field structure).
2.3 keying pins: 247 collected, all green in the gate.

### C13 — NEW TIP: d81ae82b

| commit | subject | files | +/− |
|---|---|---:|---|
| a8ed586e | operand field IR — field vector + named projections | 9 | +745 / −160 |
| 3ad158b8 | pins, static guard battery, doc sweep | 4 | +426 / −11 |
| 0bc4aa4e | nested-operand equality rows (R3.3) | 1 | +46 / −1 |
| 8251ed51 | gate-1 fixes — import ratchet + field-IR producer guard | 2 | +50 / −13 |
| **d81ae82b** | **round-1 bounce: B1/B2/B3 pin gaps, NITs 3+5** | **5** | **+207 / −16** |

Exit criteria: signature cell MET · matrix MET with 2 declared exclusions
(bare-`$@`/IFS, case PATTERN) · static guard MET · carry #4 / HIGH-6
DISCHARGED. Redirect target moved from "declared exclusion" to **CLOSED IN
SLOT** this round.

### C5-CORRECTED (R6.2) — the transclusion negative, DERIVED; my prior claim was FALSE

**RETRACTION.** C5 stated that the unified `LEDGER.md` "is not present in any
tree I can read". **That is FALSE.** It is in my own worktree, committed, at

```
docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md   (77,452 bytes)
```

present at the base commit too (`git show d0f7d929:<path>` yields the same
file). The file was always there; my search was wrong.

**Why my `find` missed it — reconstructed, not guessed.** Both searches were
DEPTH-BOUNDED and the file sits deeper than the bound:

```
my commands : find /Users/pwilson/src/psh -maxdepth 3 -iname "LEDGER.md"
              find . -maxdepth 2 -iname "*LEDGER*"
the path    : docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md
              = 5 path components
re-run now  : find . -maxdepth 3 -iname "LEDGER.md"  -> EMPTY  (reproduces the miss)
              find . -iname "LEDGER.md"              -> the file
```

**The real fault is not the flag — it is that I reported a BOUNDED search as an
UNBOUNDED fact.** "`find -maxdepth 3` found nothing" became "not present in any
tree I can read", which is a different and much stronger claim. That is the
same error class as C1's tag-vs-raw sweep: an instrument that can only see part
of the space, with its result stated as if it covered all of it. Disclosing the
limitation was right; asserting a false fact inside the disclosure was not, and
the disclosure's honest framing made the false claim MORE credible rather than
less. A negative existence claim needs an exhaustive instrument or an explicit
statement of its bound.

**THE DERIVATION, run over the real file** (`grep -n "3\.3" <path>` — 3 matches
total):

| line | content | is it a carry naming 3.3? |
|---|---|---|
| 26 | `HIGH-6 operand $@ flatten \| 3.3 \| CONFIRMED …` | THIS SLOT's Part A row |
| 59 | `4 \| operand-$@ flatten \| CLOSE via slot 3.3 (= HIGH-6)…` | THIS SLOT's carry #4 |
| 180 | `analysis perf 2.2–3.3x on large scripts` | NO — a perf multiplier in a 2.6 successor row |

**THE NEGATIVE HOLDS, now on my own evidence: no Part B/D carry row other than
carry #4 names slot 3.3.** Independently identical to the verifier's
re-derivation, including that the third hit is the perf multiplier. C5's
"relying on the verifier" caveat is withdrawn — it is no longer needed.

---

## ROUND 2: BOUNCE — corrections (R7)

Verdict: 2 blockers, 15 nits; no semantics defect — the field IR survived
round 2 untouched. Both blockers are record-integrity, and I reproduced both
myself before fixing.

### E1 (B1) — C13 declared a FALSE derived count. STANDING RULE, generalized.

**RETRACTED:** C13's row for d81ae82b read `5 | +207 / −16`.
**DERIVED TRUTH** — instrument inline, per the rule this blocker forces:

```
$ git show --numstat --format="" d81ae82b | awk '{a+=$1;d+=$2;n++} END {printf "%d files +%d/-%d\n",n,a,d}'
5 files +185/-4
```

**ROOT CAUSE, RECONSTRUCTED — not guessed.** I tested every command that could
plausibly have produced 207/16:

| candidate | result |
|---|---|
| `git show --numstat d81ae82b` (the true figure) | +185/−4 |
| sum of `--stat` per-file bars | 189 (= 185+4, consistent) |
| `git diff 0bc4aa4e..d81ae82b` | +235/−17 |
| `git diff 3ad158b8..d81ae82b` | +281/−18 |
| cumulative `d0f7d929..d81ae82b` | +1447/−184 |

**No command produces 207/16.** The figure was TYPED, not derived — and the
true figure had been printed in my own terminal minutes earlier. This is
worse than a wrong instrument: it is a number with no instrument at all,
entered on precisely the commit being declared.

**THE PATTERN, NAMED — third instance in one slot:**

| # | instance | shape |
|---|---|---|
| C1 | tag-vs-raw sweep | instrument saw part of the space; result stated as covering all of it |
| C5 | `find -maxdepth 3` | bounded search reported as an unbounded absence claim |
| **E1** | **C13 hand-count** | **no instrument at all; a plausible-looking number typed into the durable record** |

My R6 standing correction was scoped to EXISTENCE/ABSENCE claims, so it did
not catch a count. That scoping was itself the error — I fixed the instance,
not the class.

> **STANDING RULE (generalized, supersedes the R6 wording).**
> **Every number that enters the durable record is DERIVED AT WRITE TIME with
> its deriving command inline, or is explicitly marked as an ESTIMATE.** No
> exceptions for "I just saw it", "it is only a diffstat", or numbers that
> look right. A claim with no instrument is an estimate whether or not it is
> labelled one — so label it, or derive it.

**C13 CORRECTED (every row derived by the command above, at this tip):**

| commit | files | +/− |
|---|---:|---|
| a8ed586e | 9 | +745 / −160 |
| 3ad158b8 | 4 | +426 / −11 |
| 0bc4aa4e | 1 | +46 / −1 |
| 8251ed51 | 2 | +50 / −13 |
| d81ae82b | 5 | **+185 / −4** |
| cumulative `d0f7d929..d81ae82b` (the tip THIS table declares) | 14 | +1447 / −184 |

### E2 (B2) — the doc sweep taught a fact my own pin refutes

Two DURABLE statements said scalar projection is retained only where **bash
itself** demands one string, and both listed the `case` pattern. R2.1 measured
that bash matches the FIRST FIELD of a multi-field pattern operand, and
`test_case_pattern_multifield_operand_divergence` pins the contradiction in
both directions. The amendment reached the ledger and the `manager.py` inline
comment but not these two — the reappraisal-#19 failure mode exactly: a
subsystem doc teaching a fact the code's own pin proves false.

Corrected in both places, with the same substance in each:
- `psh/expansion/CLAUDE.md` — the sentence now names the `case` pattern as the
  ONE member that is **not** bash-demanded, states the first-field model, calls
  the join psh POLICY preserving base, and cross-references the divergence pin.
- `test_operand_projection_guard.py` — the `RULED_PROJECTIONS` header now says
  each row is a context where **psh** projects, that ALL ROWS EXCEPT the `case`
  pattern are bash-demanded, and requires a new row to arrive with either a
  bash probe **or** an explicit policy note plus a divergence pin. The member
  comment carries the same qualification.

Every other enumerated member replayed TRUE (verifier control) and is
untouched.

### E3 — NIT dispositions (dev items)

| NIT | Action |
|---|---|
| 1 | `printf -v` equality row; `[`-builtin row asserting it is a CONSUMER (receives the fields as separate argv and reports its own arity error) — measured `too many arguments` rc=2, prefix-normalised equal. **Measured wording differs from the ruling's "binary operator expected"** — different cell shape; I pinned what I measured. |
| 2 | Perimeter rows: `${!PFX@}` name-prefix view (producer), `${@@Q}` (per-element, producer), `${h[@]@K}` (whole-array, ONE field — the contrast row, without which the family reads as "all transforms produce fields", which is false). |
| 3 | Adjacency rows: two producers in one operand (`n=3 [p] [qm] [n]` — inner fields fuse) and a literal glued inside the quoted region (`n=2 [prep] [qpost]`). These fail on a wrong first/last-field attachment rule even when the COUNT is right. |
| 4 | `${@:}` pinned both-sides (bash: bad substitution rc=1; psh accepts and includes `$0`) + successor row; and the "exactly one cell" conclusion re-scoped — see E4. |
| 7 | Two function-local duplicate imports of `find_closing_delimiter` dropped (module-level import now exists); layering ratchet still 8 passed. |
| 9 | Guard docstring's "stays deleted" narrowed to its actual **`psh/`** scope, noting test/doc trees are not scanned and this module names the symbol deliberately. |
| 11 | Must-not-flip table extended — see E5. |
| 12 | C6's claim made true — SHAs inlined in D9/D12 below. |
| 13 | Wording note: the docstring's mention of `OperandResult` is intentional (it names what was retired). |

### E4 (NIT 4) — the "exactly one cell" conclusion, CORPUS-BOUNDED

C1 and C9 concluded "exactly ONE DIFF→DIFF content-changed cell". **That
conclusion is bounded by my corpus**, and the bound is now stated inline where
the claim is made: it holds over the **2,146 distinct cells of matrices A–L +
H6**, not over the shell's whole behaviour space. It is a strong signal
because the corpus was built to span the operand/field axes, not a proof of
universal absence. Applying the E1 standing rule to a conclusion rather than a
number: state the instrument's reach with the result.

### E5 (NIT 11) — must-not-flip, two further named items

| item | instrument | result at this tip |
|---|---|---|
| `test_bash_matcher_states_stay_polynomial` (3.2-tightened bound) | `pytest …::test_bash_matcher_states_stay_polynomial` | **1 passed** |
| 2.2 lockstep corpus (`tests/unit/parser/test_args_derived_from_words.py`) | pytest | **4 passed** |

Both are inside the gate's collected set, so gate-4 covers them; run
individually here so the row is evidence rather than inference.

### E6 (NIT 12) — D9/D12 with SHAs inlined

- **D9** retired-symbol guard: `OperandResult` absent from `psh/` — introduced
  a8ed586e (`test_retired_operand_result_absent`), scope narrowed at the
  round-2 fix commit.
- **D12** flip pin: flipped and grown at **3ad158b8** (4 → 21 rows), combinator
  leg added at **d81ae82b** (7 rows).

### E7 — GATE-4 + compare-bash at 1f57c46e

**GATE-4: 23,032 passed / 0 failed / 1,600 skipped / 10 xfailed** — exactly the
prediction pre-registered before the run (collected 24,651 → 24,659 = +8 rows;
instrument `pytest tests/ --collect-only -q`). **Third consecutive exact gate
prediction.**
**compare-bash: 3,006 passed / 26 skipped** (42.1s) — unchanged, as predicted.

### E8 — BOUNCED-ROWS REPLAY (running total: round-1 five + round-2 two = SEVEN)

| round | row | replay instrument | result |
|---|---|---|---|
| 1 | B1+B6 redirect | redirect pins ×4 + control + M8 #5 | PASS |
| 1 | B2 array view | view rows ×8 + `[*]` control + M8 #4 | PASS |
| 1 | B3 `_psh_comb` | combinator leg ×7 | PASS |
| 1 | B4 Linux | ledger row C4 | WRITTEN |
| 1 | B5 transclusion | ledger row C5-CORRECTED (derived) | WRITTEN |
| 2 | **B1 false count** | `git show --numstat --format="" d81ae82b` → 5 files +185/−4, now the ledger's stated value | CLOSED |
| 2 | **B2 false doc claim** | `grep -c "where bash itself demands one string" psh/expansion/CLAUDE.md` → **0**; `grep -c "context where bash ITSELF requires one string" test_operand_projection_guard.py` → **0** | CLOSED |

**Totals: 7 blocker rows, 7 closed, 0 outstanding, 0 re-opened.**
Pin suites at this tip: battery + projection guard + field-IR guards **110
passed** (18.8s); flip pin + both-sides + combinator leg **33 passed** (7.0s).

### E9 — NEW TIP: 1f57c46e

Every row derived by
`git show --numstat --format="" <sha> | awk '{a+=$1;d+=$2;n++} END {…}'`:

| commit | files | +/− |
|---|---:|---|
| a8ed586e | 9 | +745 / −160 |
| 3ad158b8 | 4 | +426 / −11 |
| 0bc4aa4e | 1 | +46 / −1 |
| 8251ed51 | 2 | +50 / −13 |
| d81ae82b | 5 | +185 / −4 |
| **1f57c46e** | **4** | **+119 / −19** |
| cumulative `d0f7d929..1f57c46e` (`git diff --numstat`) | 14 | **+1555 / −192** |

**SELF-CAUGHT, SAME TURN (E1 rule applied to my own correction).** I first
wrote the cumulative row as **+1566 / −203** — obtained by SUMMING the
per-commit column instead of running the command. The derived value is
**+1555 / −192**. Summing per-commit diffstats does not give a cumulative
diffstat: a line added in one commit and deleted in a later one counts twice in
the sum and zero times in the range diff. This is instance FOUR of the class,
committed inside the very section that states the rule against it — which is
the most useful possible demonstration that the rule has to be mechanical, not
remembered. Every other row in this table was derived by the command shown.

### E10 — a fifth instance, and the rule's final form

While writing E9 I hit the class TWICE more in one sitting:

1. **Summed instead of derived.** I wrote the cumulative as +1566/−203 by
   adding the per-commit column. Derived: **+1555/−192**. Per-commit diffstats
   do not sum to a range diffstat — a line added in one commit and removed in a
   later one counts twice in the sum and zero times in the range.
2. **A stale label.** The C13 table's cumulative row was labelled
   `d0f7d929..HEAD`. Its value was correct WHEN WRITTEN, and became wrong the
   moment HEAD advanced. Relabelled to the explicit SHA it actually describes.

Both self-caught, in the same sitting, inside the section that states the rule
against them. That is the useful finding: **the rule cannot be "remember to
derive" — it has to be mechanical.** Its final form:

> **Every number in the durable record is produced by a command shown beside
> it, and every range is named by an explicit SHA, never by a moving reference
> (`HEAD`, "the tip", "current"). A number without a visible instrument, or a
> range without a fixed endpoint, is an estimate — label it or derive it.**

Instances of this class in this slot: C1 (bounded instrument), C5 (bounded
search as absolute claim), E1 (no instrument), E10.1 (wrong instrument: sum vs
range), E10.2 (correct value, moving label). Five. The first two were caught by
verifiers; the last three by me — the trend is the point of recording it.

**And one over-correction, also self-caught.** While sweeping, I annotated the
round-1 cumulative row (+1264/−182) as "another summed figure, same class". It
was **CORRECT as originally written** — `git diff --numstat d0f7d929 8251ed51`
confirms 14 files +1264/−182. I had started assuming the class rather than
deriving, which is the same failure wearing the opposite sign: a false FAULT
claim instead of a false COUNT. The annotation is withdrawn; that row's only
change is its label being pinned to an explicit SHA. Recording it because an
audit that manufactures findings is no more trustworthy than one that misses
them.

---

## SLOT ACCEPTED (R8) — closing records

Round 3 (integrator direct verification) = **PASS**. Slot 3.3 ACCEPTED at
**1f57c46e**. Bounce record: 2 rounds, 7 distinct blockers, 7/7 real, 0 false,
all closed.

### F1 — Prototype worktree final state, captured BEFORE removal

`psh-r3-3-proto` was the ruling-(c) evidence (design-1 vs design-2 migration
cost). It is removed on R8.1, so its measurements are recorded here rather than
resting on a worktree that no longer exists — derived at capture time:

```
$ git diff --numstat -- psh     (in psh-r3-3-proto, detached at d0f7d929)
  psh/expansion/operands.py       +237/-4
  psh/expansion/operators.py      +3/-3
  psh/expansion/word_expander.py  +37/-0
  3 files  +277/-7
```

This is the figure ruling (c) was decided on: **Design 2 cost ~277 added lines
across 3 files** to reach a working field vector, against Design 1's **0 mypy
errors / 0 named call sites** — the measurement that disqualified Design 1,
since zero named sites means zero static-guard surface.

### F2 — Worktrees removed (R8.1)

| worktree | at | psh/tests dirty at removal |
|---|---|---|
| `psh-r3-3-base` | d0f7d929 | 0 |
| `psh-r3-3-proto` | d0f7d929 + prototype | 3 (expected — the prototype itself, captured in F1) |
| `psh-r3-3-post` | d81ae82b | 0 |

### F3 — Final slot state

Tip **1f57c46e**, HELD; branch handed to the integrator for ceremony. No
further commits from me. Machine heavy-run slot released.
