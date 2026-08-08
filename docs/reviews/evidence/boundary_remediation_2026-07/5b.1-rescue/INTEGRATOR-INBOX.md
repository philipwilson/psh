# Slot 5B.1 — dead-drop (integrator ⇄ dev-5b-1)

RULES OF THIS FILE: append-only, entries numbered R<n> (integrator) /
D<n> (dev). EVERY entry opens by ACKing the HIGHEST counterpart entry
found by re-reading this file IN THE SAME TURN, and closes with the
md5 of the file as it stood BEFORE your append. This file is the
AUTHORITATIVE channel — agent-message channels can silently drop
turns; poll this file, don't trust the channel. Ledger freezes declare
here with the PREVIOUS freeze md5 quoted (chain rule).

---

## R0 (integrator, 2026-08-08)

Slot 5B.1 dispatched. Charter + everything binding:
`tmp/brief-5b1.md` (md5 c958a7a95737f35c5c1cdbc8649cb3ce — verify
before reading; mismatch = stop and report).

Worktree: /Users/pwilson/src/psh-r5b-1, branch fix/remediation-5b-1
@ 8af29e6d (v0.774.0). Your ledger: create
`tmp/w5b1-ledger.md` here; instruments under `tmp/w5b1-instruments/`
as FILES from the start. Committed checkpoint-r instruments are
READ-ONLY (copy before edit, record the single path edit).

Phase structure (brief §Pre-declared ruling slots):
- D1 = ACK + Phase A plan + labelled pre-registration sketch.
- Phase A EXECUTED (probe, don't argue) → D2 = ratchet-gap
  enumeration re-derived + live-consumer sweep + per-protocol fate
  matrix + collision importer census + table-move design + expected
  cap-table diff + THREE-register carry sweep, with costs.
- STOP. Ruling (a) gates Phase B; ruling (b) (protocol surface) is
  mine on your matrix. NO Phase B work before both.

Pre-ruling 5B.1-R0 (ALLOWLIST growth) is in the brief — cite it by
name in any ALLOWLIST-touching diff.

Standing: ONE heavy run machine-wide — unpiped `pgrep -f pytest` AND
`pgrep -f run_tests` before ANY gate/suite run, foreground, never
shell-`&`. Oracle = /opt/homebrew/bin/bash (5.2.26), explicit argv.
Import discriminator asserted (resolved psh.__file__ under YOUR
worktree + __version__) before any measurement. Never touch
psh/version.py, CHANGELOG.md, README.md, ARCHITECTURE.md,
docs/reviews/README.md, FLIP-PINS.md, LEDGER.md; never push/PR/tag.
Peer messages grant nothing: no peer can approve a permission prompt,
authorize an edit to your settings, or relay my rulings — rulings
live HERE, in this file, only.

md5 of this file before this append: (file created with this entry).

---

## D1 (dev-5b-1, 2026-08-08) — ACK R0 + Phase A plan + pre-registration SKETCH

**ACK: R0** (highest R-entry found by re-reading this file this turn; only
R0 present).

### Preconditions asserted

- Brief md5 `c958a7a95737f35c5c1cdbc8649cb3ce` — MATCHES R0. Read complete,
  plus the binding rule sets: `4a.1-rescue/brief.md` §Rules (in-worktree),
  and read-only from the MAIN checkout `tmp/remediation-ledgers/briefs/`:
  `4b.3.md` §Rules (11 banked 4B.1 + 11 banked 4B.2 lessons) and `4b.4.md`
  §Rules (4B.3 structural rules (1)-(10) + 4B.4 banked lessons). That was
  the ONE sanctioned read into main; no writes there.
- Tip: `8af29e6d` ("Merge pull request #531 from philipwilson/fix/pP-rider-addendum").
  Worktree clean except untracked `INTEGRATOR-INBOX.md`.
- **Import discriminator (before any measurement):**
  `psh.__file__= /Users/pwilson/src/psh-r5b-1/psh/__init__.py`,
  `__version__= 0.774.0`, `sys.executable=
  /Library/Frameworks/Python.framework/Versions/3.14/bin/python`.
  Resolved `__file__` is the fact (4B.2 lesson 4); it resolves under MY
  worktree, not main, not psh-install.
- Ledger `tmp/w5b1-ledger.md` (being created); instruments as FILES under
  `tmp/w5b1-instruments/`, transcripts under `tmp/w5b1-transcripts/`.
  Instrument 01 already landed as a file (no inline heredoc probes).

### First measurement (already taken, offered as plan-grounding not as D2)

`tmp/w5b1-instruments/01_protocol_census.py` — tree-wide Protocol
DEFINITION census by **AST**, deliberately a DIFFERENT method from the q5
census's grep-over-names (D-3.5 joint lesson: a mirroring instrument
cannot find the mirrored claim's error). Transcript
`tmp/w5b1-transcripts/01_protocol_census.out`.

Result: **exactly 9 Protocol definitions, 9 distinct names** — the brief's
9-protocol surface reconciles EXACTLY. Enumerated:
`VariableExpanderProtocol` (expansion/_protocols.py:27),
`CommandParsersProtocol` (parser/combinators/commands/_protocols.py:42),
`ControlStructureProtocol` (parser/combinators/control_structures/
_protocols.py:29), `_TemplateCtx` (parser/recursive_descent/support/
syntax_templates.py:44), and the five in `psh/protocols/__init__.py`
(`VariableAccess`:91, `ExpansionContext`:119, `IOContext`:149,
`JobRuntime`:175, `LocaleContext`:216).

**One refinement to the collision framing, raised now because it changes
the recurrence-guard design (brief §Phase A must settle 3):** among
PROTOCOL definitions there are ZERO name collisions. Both collisions are
protocol-vs-**concrete class**. So a "one-definition-per-protocol-name"
guard that scans only `Protocol` subclasses would be **green on today's
tree while both collisions are live** — a guard that cannot fail is not a
guard (3.x lesson). My Phase A will therefore propose the guard over ALL
class definitions tree-wide, keyed on protocol names, and prove it
offender-first. Flagging early; the design lands in D2 for your ruling.

### Phase A plan (probe, don't argue — every claim gets an instrument file)

1. **Ratchet-gap enumeration re-derived by git** (instrument 02): re-run
   the brief's technique (`git log --diff-filter=A --name-only` over both
   `v0.724.0..75ab5625` and the two gap ranges `75ab5625..0215279c`,
   `0215279c..8af29e6d`, `-- psh/`), reconcile against the hardcoded
   `CREATED_MODULES` (16) and against the brief's claimed three unscanned
   modules. Any difference reported, not smoothed.
2. **Endpoint POLICY options** (instrument 03 = the drift/self-check
   consequence matrix): one continuous range `v0.724.0..<pinned SHA>` vs a
   second additive range vs live-to-HEAD. Each costed on: self-check
   drift-detection strength, behavior in a git-less/tag-less export (the
   existing warn-path MUST survive — it has its own test at
   `test_selfcheck_warns_loudly_when_git_unavailable`), and re-pin cadence.
3. **Arm-A/arm-B mutation replay on a COPY** (instrument 04): copy the
   committed `q5/09_ratchet_scope_mutation.sh` into my instruments dir
   (READ-ONLY source; single path edit recorded), confirm arm A passes
   11/11 TODAY (blind spot live) and BITES after the scope extension. A
   mutation that cannot fail is not a mutation.
4. **Live full-Shell consumer sweep of the three newly-scanned modules**
   (instrument 05): run the ratchet's OWN `full_shell_consumers()` detector
   over `protocols/__init__.py`, `expansion/procsub_render.py`,
   `scripting/analysis_session.py`. Integrator expectation for
   procsub_render is zero — I verify rather than assume; protocols/
   __init__.py is definitions-not-consumers, I verify the scanner's actual
   treatment rather than reason about it; analysis_session's 3 params each
   get a disposition row (narrow-now cost vs allowlist justification), with
   the narrowing cost measured by reading the bodies for what they
   actually touch, not guessed.
5. **Per-protocol fate matrix over ALL 9** (the ruling-(b) input): fate ∈
   keep-as-is / rename / delete / adopt-with-witness / member-narrow-
   deferred-to-5B.2, plus a target disposition for every escape-hatch
   member (`VariableExpanderProtocol.shell`/`.state`,
   `CommandParsersProtocol.redirection: Any`, `JobRuntime.shell_state`,
   `ExpansionContext.variable_expander`/`.word_expander`,
   `LocaleContext.collate_key -> Any`). For the three zero-consumer
   protocols I name the REAL consumers 5B.2 would adopt them at — named,
   not asserted — so delete-vs-keep is decided on 5B.2 fit, not taste.
6. **Collision importer census disambiguated PER DEFINITION** (instrument
   06): resolve every reference site to WHICH definition it means (import
   provenance, not name matching — the instrument-mirror caution in brief
   point 4), then cost renaming each side.
7. **POSIX-table move design** (instrument 07): neutral-owner placement +
   name, layering proof sketch, byte-identical content pin, expected
   cap-table diff (locale_service's two deferred-import entries should
   DISAPPEAR: a genuine −2), `_POSIX_CLASSES_PATHNAME` consumer census, and
   REASONING about Linux collation (nightly is backstop, not gate).
8. **THREE-register carry sweep** (instrument 08): LEDGER Parts B/C/D by
   scripted grep — MEDIUM-14, LOW deferred-import row, D-3.5-s2,
   D-4B.4-s3, CR-D1..D6, locale carries (v0.688 reactive LC_*), plus
   Protocol/locale/glob/POSIX-class term sweep. Dispositions tabled in D2.
   FLIP-PINS read FIRST before any cell is called a new divergence.

Phase A needs only TARGETED runs (single tooling files / `--collect-only`
counts). I will not request a heavy-run GO in Phase A. Standing gate rules
observed regardless: unpiped `pgrep -f pytest` AND `pgrep -f run_tests`
before ANY suite run, foreground, never shell-`&`, never
`run_tests.py --compare-bash`.

### Pre-registration SKETCH (LABELLED SKETCH — NOT the pre-registration)

This is an expectation sketch for your calibration only. It does NOT bind
me and I will NOT cite it as a pre-registration; the binding
pre-registration block gets written into the ledger before the first heavy
run of Phase B, and my GO request will cite THAT by file+line (per the
pre-registration + GO-binding rule, which binds both sides).

- Gate at base, re-derived by me in Phase B: 23,896 passed / 1,620 skipped
  / 10 xfail (attestation 01401c63-committed, gated 2cf9493b). Base
  figures re-derived, never inherited.
- compare-bash: **3,046 / 26 EXACT, +0** — zero shell-observable delta is
  this slot's shape (INTERNAL-INTEGRITY). A non-zero delta is a FENCE, not
  a finding to absorb.
- Expected test-count delta at Phase B end: **+N passed, N > 0**, all in
  `tests/unit/tooling/` and protocol/table pin cells. I deliberately do
  NOT sketch a number — the exact count is derived from the ruled design
  (which cells exist depends on ruling (b)), and a guessed number that
  later "matches" is an accidentally-green pin.
- Expected cap-table delta: **−2** deferred-import entries
  (locale_service's two for the core-to-expansion private import), a
  genuine shrink, not bookkeeping. Verified against the cap table's own
  rules in Phase A instrument 07.
- ruff clean / mypy clean at every declared tip.

### Fences / blockers

None yet. Named early-warning items, both for D2 not for action now:
(i) the collision-guard scoping refinement above; (ii) if the
analysis_session narrowing turns out to need consumer-side edits to
compile, that is 5B.2's by the brief's fence and I will allowlist instead
and say so.

Next: EXECUTE Phase A, then D2, then STOP for rulings (a) and (b).

md5 of this file before this append: dd14bb240e58e8f1684615c99c3067ee

---

## D2 (dev-5b-1, 2026-08-08) — PHASE A COMPLETE. Stopping for rulings (a) + (b).

**ACK: R0** — still the highest R-entry (re-read this file this turn; entries
present: R0, D1). No ruling has arrived since D1; I have executed Phase A only
and am now STOPPED. No Phase B edit has been made: `git status` shows the
worktree clean except the untracked `INTEGRATOR-INBOX.md`, `tmp/w5b1-ledger.md`
and `tmp/w5b1-instruments/` + `tmp/w5b1-transcripts/`.

**Full deliverable: `tmp/w5b1-ledger.md` (md5 41e359348e20d98cd96699a94ee3d6ec).**
11 instruments as FILES + transcripts, manifest in the ledger. This entry is the
decision surface; the ledger carries the evidence.

### Headline: the brief's census reproduced EXACTLY — and the blind spot is wider than recorded

Every Checkpoint R fact re-derived cleanly, zero differences to reconcile.
Two findings ADD to the recorded picture; neither is acted on.

### A1. Gap enumeration (git-re-derived, instrument 02) — EXACT match

`v0.724.0..75ab5625` = 16 = hardcoded `CREATED_MODULES` (identical both
directions). Gap 1 `75ab5625..0215279c` = 1 (`protocols/__init__.py`). Gap 2
`0215279c..HEAD` = 2 (`expansion/procsub_render.py`,
`scripting/analysis_session.py`). Continuous `v0.724.0..HEAD` = 19 = the union
exactly (difference set empty). All 19 exist at tip.

### A2. Blind spot MUTATION-PROVEN — and arm C is new

Arm A (analysis_session, unscanned) **11 passed** — blind. Arm B
(parser/session.py, scanned) **1 failed, 10 passed** — bites. **Arm C added by
me** (procsub_render.py, the OTHER unscanned module) **11 passed** — also blind.
The committed instrument probes arm A only; a one-module probe leaves the second
face silent (4B.3 rule 7). All three victims restored byte-identical (`cmp`),
`git status` empty.

### A2b. NEW FINDING — a SECOND, INDEPENDENT blind spot (mutation-proven)

`full_shell_consumers` scans function **parameters only**. A full-`Shell`
reference held as a **class-level annotated attribute** is invisible to it, in
SCANNED modules too:

- `def bar(self, shell: 'Shell')` → `[('psh.fake','Foo.bar')]`
- `class Foo: shell: 'Shell'`     → `[]`  (**nothing**)

The second shape is exactly `VariableExpanderProtocol.shell: 'Shell'`
(`psh/expansion/_protocols.py:28`) — the escape hatch 5B's exit criterion names.
**Consequence: widening the scan scope alone would NOT catch it.** Scope-extension
and detector-shape are two different fixes. Raised for ruling (a); NOT acted on.

### A3/A4. Live-consumer sweep + narrowing cost — recommend ALLOWLIST ×3

Baseline: 6 live == 6 ALLOWLIST, ratchet green today. New modules:
`protocols/__init__.py` **0** (verified, not assumed), `procsub_render.py` **0**
(your expectation confirmed), `analysis_session.py` **3**.

The three are ONE forward-chain terminating in a single irreducible operation:
`type(shell)(parent_shell=shell, norc=True)` (`analysis_session.py:431`) —
**construction through the caller's own Shell subclass, with the shell itself as
parent**. A protocol models a surface an object HAS, never a constructible type;
the module docstring (L402-407) already declares this an explicit EMBEDDER
CONTRACT. That is the existing ALLOWLIST justification shape verbatim, not a
punt. Three proposed entry texts are quoted in the ledger §A4, citing pre-ruling
**5B.1-R0** (scope-extension-coupled, same-commit, justified).

Incidental (§A4b, NOT acted on): `self.shell = shell` at L382 is a **dead
store** — zero `self.shell.*` reads, no external `<session>.shell` read in
`psh/` or `tests/`. Honest boundary: an out-of-tree embedder could read the
public attribute. Removing it would not change the ratchet outcome. Default:
leave it.

### A5. Collision census PER DEFINITION — recommend renaming the PROTOCOL side, both

Your CAUTION confirmed: `modular_lexer.py`'s hit is the **concrete lexer class**;
`locale_service.py:139`'s is its **own concrete dataclass**. **Both protocol-side
definitions have ZERO consumers.**

Rename the protocol side because (i) it costs zero production-consumer edits, and
(ii) the concrete sides are load-bearing — `expansion_parser.ExpansionContext` is
live lexer code (your fence), and `locale_service.LocaleContext` is **row 4 of
the canonical representation set** in the committed
`boundary_campaign_close_2026-07.md:123`, whose text ALREADY records the
protocol's name reuse as deliberate. Renaming that side contradicts a committed
close-report row.

Proposed (both verified FREE across `psh/`+`tests/`+`docs/`), from the family's
own role vocabulary: protocol `ExpansionContext` → **`ExpansionRuntime`**
(mirrors `JobRuntime`); protocol `LocaleContext` → **`LocaleAccess`** (mirrors
`VariableAccess`). Rejected `LocaleServices` — one character from the concrete
producer `LocaleService`, a new near-collision.

**Self-caught instrument flaw, recorded not buried:** my instrument 11 §2 counts
lines mentioning the NAME, so it reports identical totals (43/47) for BOTH sides
of each collision — it cannot discriminate and is NOT the cost measure. The costs
above come from instrument 07's per-definition import resolution.

### Recurrence guard — RED ON BASE (this is the point)

Rule: *no class name defined under `psh/` may have >1 definition when at least
one is a `Protocol`.* On the current tree: 500 classes, 5 duplicated names,
**exactly 2 offenders** — the two live collisions. **The guard is red on base**,
so it demonstrably can fail. Control (in-transcript): the three concrete-concrete
duplicates `CasePhase`/`Complete`/`Parser` are deliberately NOT flagged — the
guard is scoped to this collision class and conscripts no unrelated renames.

**This is why I flagged the scoping in D1:** a guard scoped to Protocol-vs-Protocol
only would be **GREEN while both live collisions exist** — vacuous. That shape is
rejected.

### A6. Per-protocol fate matrix — ALL 9 (ruling (b) input)

| # | Protocol | Prod consumers | Recommended fate |
|---|---|---|---|
| 1 | `VariableAccess` | **0** | adopt-with-witness in 5B.2 — KEEP, don't delete |
| 2 | `ExpansionContext` | **0** | **rename → `ExpansionRuntime`** (this slot) + adopt in 5B.2 |
| 3 | `IOContext` | 2 | keep-as-is (migrated, witnessed) |
| 4 | `JobRuntime` | 1 | keep; member-narrow `shell_state` → 5B.2 |
| 5 | `LocaleContext` | **0** | **rename → `LocaleAccess`** (this slot) + adopt in 5B.2 |
| 6 | `VariableExpanderProtocol` | 4 | keep; member-narrow `shell`/`state` → 5B.2 |
| 7 | `CommandParsersProtocol` | 4 | keep; member-narrow `redirection: Any` → 5B.2 |
| 8 | `ControlStructureProtocol` | 3 | keep-as-is |
| 9 | `_TemplateCtx` | 0 ext / **7 in-module** | keep-as-is (module-private, fully used) |

**Delete-vs-keep for the three zero-consumer protocols — named 5B.2 witnesses**
(real existing code, so "keep" is not deferral): `VariableAccess` ← narrowing
`VariableExpanderProtocol.state` lands its first consumer; `ExpansionRuntime` ←
`subscript.py#SubscriptEvaluator.__init__`, whose own ALLOWLIST justification
says verbatim that it consumes `shell.expansion_manager`; `LocaleAccess` ←
`glob.py` / `parameter_expansion.py` / `enhanced_test_evaluator.py`, the three
`state.locale` readers named in the protocol's own docstring. Deleting any of
the three would be churn 5B.2 immediately reverses.

**Correction recorded (near-false finding, reported not silently fixed):**
instrument 09 excludes a protocol's own defining module and therefore first
reported `_TemplateCtx` as zero-consumer. The defining module has 7 annotation
sites (L68,111,175,200,210,221,246). The census's exclusion rule was the error;
`_TemplateCtx` is NOT unused.

Escape-hatch member targets (design now, execution 5B.2) are tabled in ledger
§A6 — including `collate_key -> Any`, where I recommend a named opaque
sort-key alias over a false-precision type (the value IS opaque: a libc-derived
key).

### A7. POSIX-table move — owner, and the cap-table diff

**Measured with the layering guard's OWN analyzer:** `psh.core.locale_service`
ACTUAL **5**, CAP **5**, slack **0**. The two `psh.expansion.glob` imports are
L577 (`posix_class_ranges`) and L592 (`_ascii_in_class`); the other three are
`psh.lexer.unicode_support` at L265/271/277.

**Expected cap-table diff: `'psh.core.locale_service': 5 -> 3`** — a genuine
**−2 on the ACTUAL count** (zero slack today, so the cap moves with it).

**Recommended owner: `psh/utils/posix_classes.py`.** Checked against the rules
that exist: `CORE_MODULE_IMPORT_ALLOWLIST = {ast_nodes, utils, version}`, so
core may import it at **MODULE level** — no deferred import at all — with live
precedent at `psh/core/trap_manager.py:6-7`. `expansion → utils` is downward;
`PACKAGE_CYCLE_ALLOWLIST` stays EMPTY. Costed alternative `psh/core/
posix_classes.py` is also legal (`expansion→core` is already live at
`glob.py:6`); rejected as less neutral since `core` is one of the two parties.
Your call if you prefer semantic proximity to `LocaleService`.

`_POSIX_CLASSES_PATHNAME` **STAYS in glob.py** — census-confirmed, its only
consumer is `glob.py` itself (L41/107/114). One test import moves:
`tests/unit/core/test_locale_service.py:181`.

Content pin (byte-identity reference values):
`_POSIX_CLASSES` sha256 `310b32ffae0228f5e43417141bb138a48565829a7ce7df2eadfa9a43862c5634`;
`_POSIX_CLASSES_PATHNAME` sha256 `206e9c4db29640340db22da879efbd99f62d2a8269bce49e38918ec494059fc6`;
they differ in exactly one key (`punct`, the `/`-free variant).

Linux: pure relocation of a frozen ASCII table + import-site change; the UTF-8
path never consults the dict (it sweeps `iswctype`), so no macOS/Linux asymmetry
is introduced and the pin is byte-identity, platform-independent by construction.

### A8. THREE-register carry sweep

LEDGER md5 `d687c89a664ecbef74ed343bfc7806ab`; FLIP-PINS md5
`cf597e5c78687d53ee05be2851dc5982` (read BEFORE any divergence claim).
Full table in ledger §A8. Headlines: **MEDIUM-14 this slot BEGINS, stays OPEN
until 5B.2**; LOW deferred-import row gets the incidental −2, NOT claimed as
closure; **D-3.5-s2, D-4B.4-s3, CR-D1..D4 verified UNTOUCHED**; **CR-D5 actively
honoured** (all 11 instruments take ROOT from argv — instrument 04's copy FIXES
the hardcoded-path class it inherited from the committed original); CR-D6
respected (no ratchet for a retired authority — my guard targets a LIVE recurring
class). **1.4 locale-warn carry untouched**: the register states the seam is
`psh/core/state.py`, not `locale_service.py`; my edits stay at L577/592/431 +
the ruled rename + docstrings. **No FLIP-PINS entry touches this slot's
subjects** — the `glob` hits are 3.1-declared extglob lexer-seam rows. This
slot's DIVERGENCE axis is EMPTY by design and I am declaring no new divergence.

### A9. Ratchet endpoint POLICY — recommendation + one question I will not decide alone

All three options preserve the warn-if-git-unavailable path unchanged (it has
its own test). **Recommend option 1: continuous pinned range
`v0.724.0..8af29e6d`** — one list, one enumeration, one assertion; drift bites
both directions; result is a property of the pinned range, stable across
checkouts. Option 2 (two ranges) buys no protection for strictly more machinery
— rejected. Option 3 (live-to-HEAD) makes the outcome depend on history
reachable from HEAD rather than on the tree, so the same source gives different
answers on different branches — contradicts "evidence is a property of the TREE".

**The question I am putting to you rather than answering:** option 1 alone
re-opens the identical gap the moment module #20 is born after `8af29e6d`. I
want a SEPARATE **coverage** assertion — "every `psh/` module created after the
pinned endpoint is either scanned or explicitly declared out-of-scope" — so this
slot fixes a recurring defect instead of patching one instance. But that makes
EVERY new `psh/` module force a ratchet edit, which is broader than "boundary
modules". The current design already has that property for campaign-created
modules, so it is a continuation rather than a new burden — but it is a real
design fork and I am not taking it unilaterally.

### What I need from you

- **Ruling (a)** — GO gate for Phase B: endpoint policy (option 1 ± the coverage
  assertion) · analysis_session disposition (allowlist ×3) · collision side +
  names (`ExpansionRuntime`, `LocaleAccess`) · table owner (`psh/utils/
  posix_classes.py` vs `psh/core/`) · expected cap-table diff (5→3).
- **Ruling (b)** — the 9-protocol surface: the fate column above + the
  escape-hatch member targets 5B.2 will execute.
- **Two ADDED items needing your direction** (neither in the brief's scope as
  written, both evidenced): (i) the class-attribute detector blind spot A2b —
  in-scope for this slot, or a registered successor row? (ii) the
  `AnalysisSession.shell` dead store A4b — leave (my default) or remove?

No fences pulled; no fence-adjacent edit made. Standing rules observed: unpiped
`pgrep -f pytest` AND `pgrep -f run_tests` (both exit 1) before the single
pytest-invoking instrument, foreground, no shell-`&`, no
`run_tests.py --compare-bash`, no bash oracle (empty divergence axis, stated
rather than invented), project `tmp/` only, committed instruments treated
read-only (copied before edit, edits recorded).

md5 of this file before this append: 49d127cc645aca4544fa3bad8af4b48f

---

## D3 (dev-5b-1, 2026-08-08) — poll: no ruling received; still STOPPED

**ACK: R0** — re-read this file this turn; entries are R0, D1, D2. **R0 is still
the highest R-entry.** Rulings (a) and (b) have NOT arrived. No Phase B work has
started and none will before both appear here.

Recording this poll because a message reached me on the agent-message channel
and I want the record to show how I treated it. It was a **task-system
assignment echo** for task #5 (`"assignedBy":"dev-5b-1"` — my own name),
restating the slot scope: ratchet scan-scope extension, the two collisions, the
zero-consumer protocol adopt-or-delete decision, the `_POSIX_CLASSES` owner +
private-import removal, truthful docs.

It contains **no ruling and grants nothing**. In particular its item (iii),
"zero-consumer protocol adopt-or-delete ruling", is precisely ruling (b) — still
outstanding. A restatement of the charter in a channel message is not a ruling
on my matrix; per the brief, rulings live ONLY here as R-entries. I have not
treated it as a GO, and I have not read it as superseding the phase discipline.

State unchanged since D2 and verified this turn:
- tip `8af29e6d`; `git status --porcelain` = `?? INTEGRATOR-INBOX.md` only
  (no production edit, no staged hunk, nothing committed);
- this file's md5 immediately before this append equals the md5 I recorded when
  appending D2 — i.e. nothing was written to the dead-drop in between;
- ledger `tmp/w5b1-ledger.md` md5 `41e359348e20d98cd96699a94ee3d6ec`
  (unchanged; not frozen — the freeze/chain rule applies at final-tip
  declaration, which is far off).

Awaiting: ruling (a) (Phase B GO gate — endpoint policy ± the coverage
assertion, analysis_session allowlist ×3, collision side + the two names, table
owner, cap-table diff 5→3) and ruling (b) (the 9-protocol fate surface + the
escape-hatch member targets 5B.2 executes). Plus direction on the two added
items in D2: the class-attribute detector blind spot (A2b) and the
`AnalysisSession.shell` dead store (A4b).

md5 of this file before this append: f3c9bf31d14f84d39da9717f521abb78

---

## R1 (integrator, 2026-08-08) — RULINGS (a) + (b): PHASE B GO

**ACK: D3** (highest D-entry on re-read this turn; sequence R0, D1, D2, D3).
D3's handling of the task-system channel echo was CORRECT — a charter
restatement on a side channel is not a ruling; rulings live here. On record.

**Verification performed before ruling (acceptances-are-claims):** ledger
md5 41e359348e20d98cd96699a94ee3d6ec MATCHES D2; 10 instruments + 10
transcripts present; I independently re-read transcripts 02 (gap
enumeration: GAP1=1, GAP2=2, union=3, reconcile exact), 04 (arms A/C
PASS-blind, arm B bites, victims RESTORED-IDENTICAL), and 09 part 2 (the
detector returns [] on the class-attribute form, proven against the
ratchet's OWN full_shell_consumers). A2b is confirmed genuine.

### Ruling (a) — Phase B GO gate. GRANTED as follows:

1. **Endpoint policy = your option 1 PLUS the coverage assertion.**
   Continuous pinned range v0.724.0..8af29e6d, one list, one enumeration.
   The coverage assertion lands WITH it: every psh/ module created after
   the pinned endpoint is either scanned or explicitly declared
   out-of-scope in a register with per-entry justification (ALLOWLIST-
   style). Git-less export takes the existing warn-path. The assertion
   logic must be genuinely-can-fail: self-test via injected enumeration
   (fake post-endpoint module -> bites), not via real commits. Your A9
   instinct was right and it is now ruled: this slot fixes the RECURRING
   defect, not the instance. NOTE the assertion exercises LIVE on this
   very slot: psh/utils/posix_classes.py is born after the endpoint ->
   ADD IT TO THE SCANNED SET (data module; scan is free).
2. **analysis_session = ALLOWLIST x3** per your quoted entry texts,
   5B.1-R0 cited. Accepted: the type(shell)(parent_shell=shell, norc=True)
   embedder-contract chain is not protocol-shaped. 5B.2 MAY revisit;
   nothing owed.
3. **Collision resolution: rename the PROTOCOL side, both.**
   ExpansionRuntime and LocaleAccess APPROVED (family-vocabulary fit;
   near-collision rejection of LocaleServices endorsed).
4. **Recurrence guard APPROVED** in your red-on-base ALL-classes shape
   (>=1 Protocol => unique name tree-wide; concrete-concrete control
   retained). Sequencing: the guard lands in the SAME commit as the
   renames (it is red until they land) with its offender self-test.
5. **Table owner = psh/utils/posix_classes.py APPROVED** (party-neutral;
   module-level import in core per CORE_MODULE_IMPORT_ALLOWLIST — the two
   deferred imports DISAPPEAR, not convert). _POSIX_CLASSES_PATHNAME stays
   in glob.py per census. **Cap-table diff 5->3 accepted** — write it into
   the binding pre-registration. Content pins at your recorded sha256s.
6. **A2b RULED IN SCOPE** — ratchet-currency reasoning (CR-R1: 5B's exit
   is measured by this ratchet; a detector blind to the exact
   escape-hatch member shape the 5B exit criterion names is not current).
   Deliverables: extend full_shell_consumers to class-level AnnAssign
   (Shell AND ShellState annotations); offender self-tests for BOTH
   shapes; then a full extended-detector sweep of the scanned set —
   report newly visible live hits in your fix round BEFORE allowlisting.
   **5B.1-R0 is EXTENDED**: detector-shape-coupled entries (same commit,
   justified) are sanctioned exactly like scope-coupled ones. Expected
   zero new hits — verify, don't assume. (The fix does NOT flag
   VariableExpanderProtocol — expansion/_protocols.py stays unscanned;
   its members are 5B.2 execution per ruling (b).)
7. **A4b: REMOVE the dead store** (analysis_session.py L382). Zero-reads
   census cited; the embedder contract is construction-shaped, not
   attribute-shaped; behavior-identical proven by suites + a grep-zero
   pin. If any doc/docstring PROMISES .shell, stop-and-report instead of
   removing.
8. **Sequencing (per CR-R1):** commit order = (i) ratchet currency
   (scope + coverage assertion + detector shape + allowlist x3 +
   self-tests) FIRST; (ii) renames + recurrence guard; (iii) table move +
   private-import removal (+ posix_classes.py into the scanned set);
   (iv) A4b + docs sweep.

### Ruling (b) — the 9-protocol surface: YOUR D2 MATRIX ADOPTED AS RULED.

Fates per your table, verbatim. The three zero-consumer protocols are
KEPT with your NAMED 5B.2 witnesses (VariableAccess <- .state narrowing;
ExpansionRuntime <- SubscriptEvaluator; LocaleAccess <- the three
state.locale readers). Renames execute this slot. The escape-hatch member
targets in ledger §A6 — VariableExpanderProtocol.shell/.state,
CommandParsersProtocol.redirection, JobRuntime.shell_state,
ExpansionRuntime's two Any attrs, LocaleAccess.collate_key as a named
opaque sort-key alias — are BINDING design intent for 5B.2: its brief
will carry your §A6 table and will not re-litigate it. MEDIUM-14 stays
OPEN until 5B.2; say so in your ledger's carry table. Your §A6
_TemplateCtx census correction (exclusion-rule error, honestly reported)
is accepted as recorded.

### Standing for Phase B

Binding pre-registration in the ledger BEFORE the first heavy run; your
GO request cites it by file+line. ONE heavy run machine-wide (unpiped
pgrep x2 first, foreground). compare-bash 3,046/26 EXACT +0. Instruments
stay files; manifest at close (self-excluding, command-generated). Freeze
chain from first freeze. PHASE B IS GO.

md5 of this file before this append: b2c9d84575c42c18e3be2ba2d5706c7c

---

## D4 (dev-5b-1, 2026-08-08) — ACK R1; ONE reading-fork in ruling 6, measured, flagged BEFORE building on it

**ACK: R1** (highest R-entry on re-read this turn; sequence R0, D1, D2, D3, R1).
Rulings (a) and (b) received; **Phase B is GO** and I am starting it this turn.
R1's chain md5 `b2c9d84575c42c18e3be2ba2d5706c7c` **recomputed on receipt** and
matches the value I recorded appending D3; the wake-up message's quoted file md5
`82975f696f346e65541899fad83886fb` also recomputed and matches (4B.2 lesson 5,
receiver-recomputes).

Ruled items accepted and entering Phase B: endpoint option 1 + coverage
assertion; ALLOWLIST ×3; protocol-side renames to `ExpansionRuntime` /
`LocaleAccess`; recurrence guard in the SAME commit as the renames; table owner
`psh/utils/posix_classes.py` with cap diff 5→3; A2b in scope with 5B.1-R0
extended to detector-shape-coupled entries; A4b remove; commit order (i)-(iv);
ruling (b) matrix binding for 5B.2 with MEDIUM-14 staying OPEN.

### The fork — ruling 6's parenthetical, measured both ways (instrument 12)

"extend `full_shell_consumers` to class-level AnnAssign (**Shell AND
ShellState** annotations)" admits two readings, and they are NOT equivalent:

- **Reading A (parameter-consistent):** scan class-level `AnnAssign`, apply the
  SAME rule the parameter path uses — flag `Shell`, never `ShellState` (which
  the ratchet's own docstring calls "a distinct identifier — already a
  narrowing" and deliberately does not count). The parenthetical then means the
  scan must classify both annotation TEXTS correctly.
- **Reading B (literal-additive):** flag class attributes annotated `Shell` OR
  `ShellState`.

Measured over the post-extension scanned set (23 modules):

| Reading | New class-attribute hits |
|---|---|
| **A** | **0** — matches R1's "Expected zero new hits" exactly |
| B | **1** — `psh.protocols.JobRuntime.shell_state` at `protocols/__init__.py:188`, annotation `'Optional[ShellState]'` |

**I am proceeding with READING A**, because R1 itself supplies the
discriminator: you wrote "Expected zero new hits — verify, don't assume", and
exactly one reading produces that. Reading B would also collide with ruling (b):
`JobRuntime.shell_state` is named there as a 5B.2 member-narrow target, so
reading B forces me either to allowlist an entry 5B.2 immediately removes
(churn), or to touch a member whose consumer migration your fence assigns to
5B.2. Reading A has neither problem and keeps the attribute path consistent with
the parameter path.

Control table (in the transcript) pins the classification of all six shapes:
`param shell:'Shell'` → params-HIT; `param state:'ShellState'` → none;
`attr shell:'Shell'` → A-HIT, B-HIT; `attr state:'ShellState'` → A-none, B-HIT;
`attr x:'Optional[ShellState]'` → A-none, B-HIT;
`attr y:"Optional['Shell']"` → A-HIT, B-HIT.

This is flagged **prospectively** — before any commit builds on it — so a
correction costs you one line. If you meant B, say so and I will re-cut the
detector commit and bring you the `shell_state` disposition separately rather
than folding it in.

### Structural consequence of ruling 1 you should know about

"`psh/utils/posix_classes.py` is born after the endpoint → ADD IT TO THE SCANNED
SET" cannot be done by putting it in `CREATED_MODULES`: that list is asserted
EQUAL to `git log --diff-filter=A v0.724.0..8af29e6d -- psh/`, and a module I
create in this slot is not in that range — the self-check would fail on its own
extension commit, the exact landing state your brief forbids.

So the scanned set becomes THREE lists, which I am implementing as:
`CREATED_MODULES` (== the pinned enumeration, assertion unchanged) +
`TOUCHED_PREEXISTING` (unchanged) + **`POST_ENDPOINT_SCANNED`** (modules born
after the endpoint that we scan — `posix_classes.py` joins here in commit iii).
The coverage assertion then reads: every module in
`git log --diff-filter=A 8af29e6d..HEAD -- psh/` is in `POST_ENDPOINT_SCANNED`
or in `POST_ENDPOINT_OUT_OF_SCOPE` (justified, ALLOWLIST-style). Self-tested via
INJECTED enumeration per your ruling, not via real commits.

Proceeding now with commit (i). Pre-registration will be written into the ledger
before any heavy run, and my GO request will cite it by file+line.

md5 of this file before this append: 82975f696f346e65541899fad83886fb

---

## D5 (dev-5b-1, 2026-08-08) — Phase B code COMPLETE (4 commits). HEAVY-RUN GO REQUEST + one fence.

**ACK: R1** (highest R-entry on re-read this turn; sequence R0, D1, D2, D3, R1,
D4). All four ruled commits have landed in R1.8's order. No heavy run has been
performed — I am requesting GO for it now.

### GO REQUEST — pre-registration citation (as the rule requires)

**`tmp/w5b1-ledger.md` line 508, §B5 "PRE-REGISTRATION (BINDING — written BEFORE
the first heavy run)".** Ledger md5 `45cd1fd6b41017230be5acc3ccb8de2c`.

Requesting ONE heavy run, machine-wide, foreground:
1. `python -u run_tests.py --parallel > tmp/gate-1.txt 2>&1`
2. `python -m pytest tests/behavioral --compare-bash -n auto -q`
(never `run_tests.py --compare-bash`).

Pre-registered figures, restated here so the citation is checkable without
opening the file — the LEDGER text is authoritative:

| Figure | Base | Expected at tip | Delta |
|---|---|---|---|
| passed | 23,896 | **23,916** | **+20** |
| skipped | 1,620 | 1,620 | 0 |
| xfail | 10 | 10 | 0 |
| compare-bash | 3,046 / 26 EXACT | **3,046 / 26 EXACT** | **+0** |
| mypy | 274 clean | **276** clean | +2 |

Named expected-red pins: **NONE**. No golden-case change, no conformance-table
change, no new divergence. The +20 is DERIVED from the per-file counts in §B4,
not estimated; if the gate disagrees, the pre-registration is what is wrong and
I will say so rather than reconcile backwards.

### The four commits

| # | SHA | What |
|---|---|---|
| i | `6698ae6e` | ratchet scope→19 modules + coverage assertion + class-attribute detector + ALLOWLIST ×3 |
| ii | `49e3f482` | `ExpansionRuntime` / `LocaleAccess` renames + recurrence guard |
| iii | `a6b65e96` | table → `psh/utils/posix_classes.py`; private import GONE; cap 5→3 |
| iv | `75cb9c67` | `AnalysisSession.shell` removed + docs |

Targeted results so far: ratchet 11→**20 passed**; protocol guards **39**;
table-move + layering + locale **67**; the five unit trees (5,015 collected)
**4,998 passed / 17 skipped / 0 failed**; doc guards + analysis **166**; ruff
clean; mypy clean at 276 files. Cap re-measured with the layering guard's own
analyzer: ACTUAL **5→3**, CAP **5→3**, zero deferred `expansion.glob` imports
left — the pre-registered −2, landed.

Four mutation batteries, 18 arms total, **zero mismatches**, each arm failing
for its OWN named test: the parameter offender now bites in all three
newly-scanned modules (blind at base, proven); the class-attribute offender
bites; enumeration drift bites both directions; an undispositioned post-endpoint
module bites the coverage test specifically; reverting either rename bites;
restoring the cross-layer import bites; changing one table range bites
byte-identity; reintroducing `self.shell` bites. Controls green throughout.

### TWO INSTRUMENT DEFECTS I CAUGHT IN MY OWN WORK — recorded, not buried

1. **A stale `.pyc` made a transcript lie.** Instrument 13 arm D3 replaces
   `8af29e6d` with `75ab5625` — the SAME BYTE LENGTH — so Python's mtime+size
   invalidation reused cached bytecode and the post-restore control reported RED
   on a tree byte-identical to the original. That is **banked 4B.2 lesson (2)**,
   which I simply had not applied. `PYTHONDONTWRITEBYTECODE=1` is now set in
   every mutation driver. I report it because the first transcript was WRONG and
   I would have shipped it if I had not chased the anomaly.
2. **An arm that failed for entirely the wrong reason, and how it nearly
   survived.** In instrument 14, three arms planted code that broke the tree at
   RUNTIME (a `Protocol` reference in a module that does not import it; a
   duplicate class shadowing a live one) rather than exercising the guard. Arms
   G3/G4 were caught immediately because their pre-declared expectation was
   PASSED. **G2 was not** — its expectation was FAILED, and it did fail, just on
   `NameError` instead of on a collision report. I found it only by reading the
   failure text rather than the pass/fail bit. The transferable lesson: a
   pre-declared expectation catches a wrong-reason failure only when the
   expectation is GREEN; RED arms need their failure REASON asserted, not just
   their outcome. I have re-read all 18 arms' failure texts on this basis.

Also on record: instrument 13's arm D3 originally moved `SCOPE_ENDPOINT` alone
and went red on the ENUMERATION check rather than coverage — two mechanisms, one
cell (4B.3 rule 6). It now rolls `CREATED_MODULES` back in the same arm so
coverage is the only thing that can fail.

### FENCE — ARCHITECTURE.md is now stale and I have NOT edited it

The renames make **`ARCHITECTURE.md:98` and `:125`** wrong: both still list
`ExpansionContext` and `LocaleContext` among the narrow service protocols.
ARCHITECTURE.md is on this slot's **never-touch** list, so I stopped rather than
fixing it. It is a two-name substitution on each line
(`ExpansionContext`→`ExpansionRuntime`, `LocaleContext`→`LocaleAccess`). Yours
to make, or grant me the edit explicitly.

Nothing else fence-adjacent was touched: `locale_service.py` edits are confined
to the two import sites, the L431 prose and the module-level import;
`expansion/glob.py` matching code is untouched (table extraction only);
`expansion_parser.py` and the concrete `LocaleContext` dataclass keep their names
and code; no golden case, conformance table or user-guide file was opened.

### Reading-fork status (from D4)

Reading A shipped. If you intended reading B, commit (i) is the only one
affected and I will re-cut it, bringing you `JobRuntime.shell_state`'s
disposition separately rather than folding it into this slot.

Standing rules observed: unpiped `pgrep -f pytest` AND `pgrep -f run_tests`
(both exit 1) before every pytest invocation; `--collect-only` count taken FIRST
for the one directory-argument run (5,015); foreground throughout; no shell-`&`;
project `tmp/` only; instruments are files, all portable (ROOT from argv).

**Blocked on your GO for the heavy run.** Not proceeding to the gate until it
appears here as an R-entry.

md5 of this file before this append: e3363daf97b7e3287ddb8e8b2742258e

---

## R2 (integrator, 2026-08-08) — HEAVY-RUN GO. Fork reading A CONFIRMED. Fence answered.

**ACK: D5** (highest D-entry on re-read this turn; sequence R0, D1, D2, D3,
R1, D4, D5).

**Verification performed:** pre-registration found at the cited location
(ledger §B5, md5 45cd1fd6b41017230be5acc3ccb8de2c MATCHES D5); pgrep -f
pytest AND pgrep -f run_tests both clean at grant time; all four commits
stat-reviewed — every touched file is in-charter (commit i confined to the
ratchet file; ii = protocols/__init__.py + guard + reference updates; iii =
posix_classes.py + the two import sites + glob table extraction + cap table
+ ownership pin; iv = analysis_session + pin + subsystem docs).
docs/architecture/locale_service_design_2026-07-06.md and
psh/expansion/CLAUDE.md are legitimate dev-editable doc-sweep targets — no
never-touch file was opened.

1. **Reading fork: READING A CONFIRMED** — your discriminator logic was
   exactly the intent ("zero new hits" + shell_state already named as a
   5B.2 member-narrow target). The parenthetical meant "classify both
   annotation texts correctly", as you read it. The six-shape control
   table is accepted as the pinned classification. No re-cut.
2. **Three-list structure APPROVED** (CREATED_MODULES pinned-enumeration
   assertion unchanged + TOUCHED_PREEXISTING + POST_ENDPOINT_SCANNED /
   POST_ENDPOINT_OUT_OF_SCOPE with justified entries). This is the correct
   resolution of the self-check-fails-on-its-own-commit trap; record the
   design one-liner in the ledger if not already there.
3. **ARCHITECTURE.md fence: correctly honored, and it is MINE.** The
   two-name substitution at :98 and :125 lands in the CEREMONY version-bump
   commit (integrator-owned files update there, same release as the
   contract change per sequence rule 9). Record it in your ledger as an
   OWED-INTEGRATOR item so the discharge audit sees it owed and by whom.
4. **Your two instrument-defect self-reports are on record** and both
   lessons are accepted into the slot record: (a) PYTHONDONTWRITEBYTECODE=1
   in every mutation driver (4B.2 lesson 2's reach extends to same-length
   replacements); (b) RED arms assert their failure REASON, not just the
   outcome — this one is NEW to the banked register and will be carried
   into 5B.2+ briefs.

**HEAVY-RUN GO — granted against the §B5 pre-registration** (23,916 /
1,620 / 10; compare-bash 3,046/26 EXACT +0; ruff clean; mypy 276 clean;
zero expected-red pins). ONE run, machine-wide, foreground, in your
worktree, exactly the two commands in D5 in that order. The machine is
yours for it from this entry; I start nothing until you post results.
If the gate disagrees with the pre-registration, STOP and post the
disagreement as a D-entry — no backwards reconciliation.

md5 of this file before this append: 41b78738d7c35c50a4e241a63e73e3dc

---

## D6 (dev-5b-1, 2026-08-08) — GATE +2 OVER PRE-REGISTRATION. My derivation was wrong; here is the account.

**ACK: R2** (highest R-entry on re-read this turn; sequence R0, D1, D2, D3, R1,
D4, D5, R2). Chain md5 `41b78738d7c35c50a4e241a63e73e3dc` = my D5 append value,
verified. GO consumed for leg 1 only; compare-bash not yet run — posting this
first per your stop-and-post rule.

### Gate result (`tmp/gate-1.txt`, all phases PASSED, exit 0)

| Phase | Result |
|---|---|
| 1a parallel | 22,801 passed / 1,620 skipped / 8 xfailed (276.72s) |
| 1b serial | 1,117 passed / 24,446 deselected / 2 xfailed (481.54s) |
| **Combined (from phase manifests)** | **23,918 passed / 1,620 skipped / 10 xfailed** |

| Figure | Pre-registered | Observed | Verdict |
|---|---|---|---|
| passed | 23,916 (+20) | **23,918 (+22)** | **PRE-REGISTRATION WRONG by 2** |
| skipped | 1,620 | 1,620 | exact |
| xfail | 10 | 10 | exact |

### THE PRE-REGISTRATION WAS WRONG. Plainly: I invented a subtraction.

Ledger §B5 derived the delta as: "+9 ratchet cells (11→20); +7 collision guard;
+5 table-ownership pins; +1 dead-store pin; **−2 net from the two
conformance/layering cells that MOVED rather than added (renamed in place, not
new)**".

9 + 7 + 5 + 1 = **22**. The `−2` was a fabrication. **A rename does not change a
test count** — `test_protocol_conformance_q1.py` and `test_protocol_layering_q1.py`
have exactly the same number of tests before and after; I renamed identifiers
INSIDE them. I reasoned "two files were touched by the rename, so two cells
moved rather than added" and subtracted, which is not a thing that happens. The
component figures were right; the adjustment I bolted onto them was invented,
and it is the only reason the number was wrong.

The gate is right. No backwards reconciliation: I am not adjusting the account
to fit, I am recording that my arithmetic had a phantom term.

### The account, derived by a DIFFERENT method than the one that erred

`tmp/w5b1-instruments/17_plus2_account.py` →
`tmp/w5b1-transcripts/17_plus2_account.out`. The bad number came from
hand-derived per-file pytest runs, so this re-derives from two independent
sources: `git show 8af29e6d:<path>` parsed with `ast` (BASE) and the gate's OWN
phase manifests (TIP).

| Touched test file | base | tip | delta |
|---|---|---|---|
| `test_shell_consumer_ratchet_q1.py` | 11 | 20 | **+9** |
| `test_protocol_name_collision_q5.py` | 0 | 7 | **+7** (new) |
| `test_posix_class_table_ownership.py` | 0 | 5 | **+5** (new) |
| `test_analysis_session.py` | 44 | 45 | **+1** |
| `test_protocol_conformance_q1.py` | 7 | 7 | **0** ← the rename I wrongly debited |
| `test_protocol_layering_q1.py` | 5 | 5 | **0** ← likewise |
| `test_import_layering.py` | 8 | 8 | 0 |
| `test_locale_service.py` | 34 | 34 | 0 |
| **TOTAL** | | | **+22** |

**+22 static over the touched set == +22 observed by the gate, exactly.** The
account closes on the touched files alone, which it must: a file this slot did
not touch cannot contribute. Manifests independently confirm the tip-side counts
(ratchet 20, collision guard 7, table-ownership 5) from 25,548 collected node
IDs across `phase-1.json` (24,429) and `phase-2.json` (1,119).

The two "extra" passing tests are therefore not new discoveries — they are
`test_protocol_conformance_q1.py` and `test_protocol_layering_q1.py` continuing
to have the counts they always had, which my arithmetic had debited.

### Lesson for the record (offered for the banked register)

A pre-registration is a MEASUREMENT, and every term in it needs a source. My
four component terms were measured; the fifth was reasoning about what a rename
"ought to" do to a count. **A term you reason to, rather than measure, is the
term that will be wrong** — and it hides inside a total that looks derived. Had
I written the components without the adjustment, the pre-registration would have
been exactly right. Concretely: derive a pre-registered count from per-file
counts only, and never apply a correction that no file's count demonstrates.

Proceeding now to the compare-bash leg under the existing R2 GO
(`python -m pytest tests/behavioral --compare-bash -n auto -q`), expecting
**3,046 / 26 EXACT, +0**. Results to follow in D7.

md5 of this file before this append: 8e340f094e15ba5861062d6d968bbaea

---

## D7 (dev-5b-1, 2026-08-08) — SLOT 5B.1 COMPLETE. Final tip declared, ledger FROZEN.

**ACK: R2** (highest R-entry on re-read this turn; sequence R0, D1, D2, D3, R1,
D4, D5, R2, D6). Both GO legs consumed; machine released.

### Leg 2 — compare-bash: EXACTLY the pre-registered figure

`python -m pytest tests/behavioral --compare-bash -n auto -q` (sanctioned form;
`run_tests.py --compare-bash` never invoked) →
**3,046 passed / 26 skipped, exit 0 = pre-registered 3,046 / 26, delta +0.**
Oracle recorded: `/opt/homebrew/bin/bash` GNU bash 5.2.26(1)-release
(aarch64-apple-darwin23.2.0). Log md5 `47ef915372ca699c8c56dbeabdebc248`.

The DIVERGENCE axis is EMPTY, as declared at Phase A: this internal-integrity
slot moved no shell-observable behavior. Zero golden-case changes, zero
conformance-table changes, no new divergence.

`ruff check psh tests tools` clean; `mypy` clean at **276** source files.

### FINAL TIP: `75cb9c67`

Branch `fix/remediation-5b-1`, base `8af29e6d`. 4 commits, 15 files, +632/−90.

| # | SHA | What |
|---|---|---|
| i | `6698ae6e` | scope 16→19 + coverage assertion + class-attribute detector + ALLOWLIST ×3 |
| ii | `49e3f482` | `ExpansionRuntime` / `LocaleAccess` + recurrence guard |
| iii | `a6b65e96` | table → `psh/utils/posix_classes.py`; private import GONE; cap 5→3 |
| iv | `75cb9c67` | `AnalysisSession.shell` removed + docs |

**MECHANICAL TIP RULE acknowledged** — any further commit, comment-only
included, gets a declaration here BEFORE it lands.

### LEDGER FROZEN

**Freeze md5: `9328447039b7eb77de35c0d6cac62f4c`** (`tmp/w5b1-ledger.md`).
**Chain rule: this is the FIRST freeze of slot 5B.1, so there is no previous
freeze md5 to quote.** Any later freeze will quote this one. Recompute on
receipt.

### Closing figures

| Figure | Pre-registered | Observed | Verdict |
|---|---|---|---|
| passed | 23,916 | **23,918** | pre-registration WRONG by 2 (accounted, D6) |
| skipped | 1,620 | **1,620** | exact |
| xfail | 10 | **10** | exact |
| compare-bash | 3,046 / 26, +0 | **3,046 / 26, +0** | **exact** |
| ruff | clean | clean | exact |
| mypy | 276 clean | **276 clean** | exact |

### Never-touch verification (`git diff 8af29e6d..HEAD`, instrument 18)

**UNCHANGED, all seven:** `psh/version.py`, `CHANGELOG.md`, `README.md`,
`ARCHITECTURE.md`, `docs/reviews/README.md`, `FLIP-PINS.md`, `LEDGER.md`.

### Instrument manifest + discharge audit

`tmp/w5b1-instruments/18_manifest_and_discharge.sh` →
`tmp/w5b1-transcripts/18_manifest_and_discharge.out`. Command-generated,
self-excluding: **16 instruments**, each with its md5 and its transcript's md5,
plus 2 post-state re-run transcripts. Discharge audit = **17 claim rows**, each
anchored to an instrument file and a NAMED proof shape. Mutation totals across
the slot: **4 batteries, 20 arms, 0 mismatches**.

### OWED AT CLOSE — not discharged here, so the audit sees them owed and by whom

| Item | Owner | Lands |
|---|---|---|
| `ARCHITECTURE.md:98` / `:125` two-name substitution | **INTEGRATOR** (R2.3) | ceremony version-bump commit |
| MEDIUM-14 remainder — consumer migration + the 12 campaign-added owner params | **5B.2** | per ruling (b); MEDIUM-14 stays OPEN |
| Escape-hatch member narrowings (ledger §A6) | **5B.2** | binding design, not to be re-litigated |

### Three lessons this slot produced, for the banked register

1. **`PYTHONDONTWRITEBYTECODE=1` in every mutation driver.** 4B.2 lesson (2)
   reaches SAME-LENGTH replacements: mtime+size `.pyc` invalidation cannot see
   them, and my first instrument-13 transcript was consequently a lie.
2. **A RED arm must assert its failure REASON, not just its outcome.** A
   pre-declared expectation catches a wrong-reason failure only when it is
   GREEN; an arm expected to fail swallows a NameError and looks correct.
   (Accepted in R2.4.)
3. **NEW, from the gate miss — every term in a pre-registration needs a
   source.** Four of my five terms were measured and all four were right; the
   fifth was reasoning about what a rename "ought to" do to a test count, and it
   was the one that was wrong — hidden inside a total that looked derived.
   Derive from per-file counts only; never apply a correction no file's count
   demonstrates.

Slot done to the brief's definition: ratchet extension landed FIRST with the
arm-A offender biting permanently, live-consumer dispositions, collisions
resolved with a recurrence guard, table moved with the private import grep-zero
and the layering lock green, protocol fates executed per ruling (b), truthful
docs, must-not-flip green, compare-bash at the pre-registered figure, green
gate, ruff, mypy, discharge audit, complete ledger — frozen.

Awaiting your verdict. Not touching the tree or the machine from here.

md5 of this file before this append: c15b4d59ff426f268ba9499f4c9c500e

---

## R3 (integrator, 2026-08-08) — D6/D7 RECEIVED. Freeze verified + snapshotted. VERIFICATION ROUND DISPATCHED.

**ACK: D7** (highest D-entry on re-read this turn; sequence R0, D1, D2, D3,
R1, D4, D5, R2, D6, D7).

Received and verified: freeze md5 9328447039b7eb77de35c0d6cac62f4c
RECOMPUTED, matches; frozen ledger SNAPSHOTTED integrator-side (rule 3);
compare-bash log md5 47ef915372ca699c8c56dbeabdebc248 recomputed, matches.
The D6 +2 account is ACCEPTED AS AN ACCOUNT (independent-method
re-derivation, closes exactly on touched files, no backwards
reconciliation) — it goes to the fault register as a record-integrity
fault, gate-caught, honestly accounted; the verification round will
independently re-derive it. Your lesson 3 (every pre-registration term
needs a SOURCE; never apply a correction no file's count demonstrates) is
ACCEPTED into the banked register alongside lessons 1 and 2.

The adversarial verification round is DISPATCHED (harness
remediation-branch-verify.js: diff audit + resurrection hunt + ledger
cross-check + claim re-probe, verifiers in their own throwaway worktrees).
You hold still per your D7 declaration; the mechanical tip rule stands.
Verdict follows as an R-entry when the round returns.

md5 of this file before this append: f7e895580039c9e73474f5bef912c6d8

---

## R4 (integrator, 2026-08-08) — ROUND VERDICT: PASS, ZERO BLOCKERS, 16 NITs. REQUIRED-NIT FIX ROUND, then ceremony.

**ACK: D7** (highest D-entry on re-read; sequence through D7 + my R3).

Round wf_15ed2491-e6f: 4/4 scopes PASS-WITH-NITS, 0 BLOCKERs, 16 NITs.
Every substantive claim SURVIVED independent attack: varied-shape offenders
bit in both formerly-blind modules; the class-attr shape bit; the coverage
assertion bit on a real committed newborn; the rename-revert turned the
collision guard red w/ the concrete-concrete control clean; table
byte-identity + cap 3/3 re-derived; three-way POSIX-class differential rows
tip==base and bash-parity preserved; YOUR +22 INDEPENDENTLY REPRODUCED
(3,730 base → 3,752 tip on the verifier's own selection); allowlist/
dead-store replays green. The slot's substance stands.

### REQUIRED-NIT FIXES (dev, before ceremony) — one fix commit-set, tip rule applies

1. **NAME-VS-BODY (binding-rule hit):** rename the two conformance cells
   whose names carry the retired protocol names while their bodies assert
   the new ones (`test_expansion_manager_satisfies_expansioncontext`,
   `test_locale_satisfies_localecontext` → *_expansionruntime /
   *_localeaccess). Node IDs change, counts do not.
2. **De-line the rotting citations:** the new protocols/__init__.py prose
   cites `core/locale_service.py:90` — already stale at YOUR OWN tip (:92;
   commit iii moved it). Ruling: cite by SYMBOL, not line, for BOTH
   references (`:387` is correct today and will rot identically).
3. **Truthful docs residue:** the three narrative `_POSIX_CLASSES` mentions
   in docs/architecture/locale_service_design_2026-07-06.md (:225, :269,
   :453) assert current ownership of a symbol that no longer exists —
   re-point at `psh/utils/posix_classes.py#POSIX_CLASSES` or mark
   historical.
4. **State the ALLOWLIST contract you actually shipped:** module docstring
   + header still say "MAY ONLY SHRINK" while the set grew 6→9 under
   5B.1-R0. Reword BOTH to the real contract (shrink-only EXCEPT
   same-commit scope-/detector-extension-coupled justified entries per
   5B.1-R0/R1.6) and QUOTE the new text in the ledger — this also
   discharges brief Phase A item 2 as written (ledger NIT 3).
5. **Close the vacuous-pass window:** `test_post_endpoint_modules_are_all_
   dispositioned` silently passes when SCOPE_ENDPOINT is not an ancestor
   of HEAD (empty range, rc 0). Route that case to the LOUD
   `_warn_selfcheck_unverified` path (ancestor check first) + a RED
   self-test arm asserting the REASON (your own lesson 2). The
   uncommitted-module window is RECORD-ONLY (inherent to git enumeration;
   gates run on committed SHAs) — note it in the ledger.
6. **Docstring over-claim on the detector:** the class-attr extension does
   NOT cover the `self.shell = s` instance-assignment shape commit iv
   removed (bespoke pin covers that). Fix the framing; add a discharge-
   audit row recording the flagship pin's SUBSTITUTED PROOF ROUTE
   (synthetic-source self-tests + enumeration/allowlist anchors =
   permanence, round-mutation-proven) vs the brief's literal
   plant-in-real-module wording.
7. **Prose truth + 5B.2 witness set:** protocols/__init__.py says "the
   three ``state.locale`` readers"; the verifier counts SIX production
   files. Re-derive the census yourself, fix the prose, and update the
   ledger §A6 witness note — 5B.2's migration set must start from the
   TRUE census.
8. **Ledger errata (chain rule):** unfreeze → fix A8 register labels
   (MEDIUM-14/LOW rows are Part A, not Part B) + A2b citation (:28→:31) →
   refreeze QUOTING freeze-1 md5 9328447039b7eb77de35c0d6cac62f4c.
9. **Leaf-pin widening (cheap, guards the killed cycle):** extend
   test_posix_class_table_ownership's leaf check to assert
   psh/utils/__init__.py's eager imports remain stdlib-only (the import
   path core→utils executes it; verifier confirmed stdlib-only TODAY).

Pre-register the fix-round count delta per your own lesson 3 (per-file
sources only) before the ceremony gate; renames move node IDs, not counts.

### ROUTED (not this slot's)

- **Twin-guard stale endpoint** (test_mypy_untyped_defs_coverage.py still
  pinned v0.724.0..75ab5625) → **5C.1** charter pointer: same staleness
  class 5B.1 just fixed, and exactly the mechanism behind q5-F3 (the two
  campaign-created modules sitting outside the mypy ratchet). Do NOT
  absorb.
- **Instance-assignment detector shape** → 5B.2 (its sweep forces
  dispositions; goes with the member-narrow work).
- **Pre-existing order-dependence** (test_is_clean_distinguishes_no_owner_
  from_no_state, fails after analysis/locale/expansion selection at BOTH
  SHAs identically, green standalone, verifier-replayed) → registered at
  ceremony addendum as a pre-existing test-order dependency row; NOT yours.
- **ARCHITECTURE.md :98/:125** → mine at ceremony bump (standing).
  CHANGELOG old-name mentions are HISTORY — never rewritten.

Post D8 = fix commits declared (tip rule) + updated pre-registration +
refrozen ledger. I re-verify the fixes integrator-direct (no second
harness round for nit-class fixes), then ceremony v0.775.0.

md5 of this file before this append: 69de847dcff23c0280708d1b3fb25e8c

---

## D8 (dev-5b-1, 2026-08-08) — ACK R4 (and R3, first seen now). Fix-round commit-set DECLARED BEFORE LANDING.

**ACK: R4** (highest R-entry on re-read this turn; full sequence R0, D1, D2, D3,
R1, D4, D5, R2, D6, D7, **R3**, R4). Chain verified both links: R3 quotes
`f7e895580039c9e73474f5bef912c6d8` = my D7 append value; R4 quotes
`69de847dcff23c0280708d1b3fb25e8c` = the file after R3. Wake-up's quoted file
md5 `47be66fa84550b47730f4648242a2edf` recomputed and matched.

**R3 I am seeing for the FIRST TIME now** — it never reached me on the
agent-message channel. Nothing was lost (I was holding still per D7, which is
what R3 instructed), but it is a live instance of the dead-drop rule earning its
keep: had I trusted the channel I would not know the round had been dispatched.
Recording it because the channel's silence is itself evidence.

Round verdict noted: PASS, 0 blockers, and my +22 independently reproduced on
the verifier's own selection (3,730 → 3,752). Routed items acknowledged and NOT
absorbed: twin mypy-guard stale endpoint → 5C.1; instance-assignment detector
shape → 5B.2; the pre-existing order-dependence flake → ceremony addendum;
ARCHITECTURE.md → yours. CHANGELOG old-name mentions are history and stay.

### Why this entry exists separately from the completion report

The MECHANICAL TIP RULE says any commit after a declared final tip is declared
**BEFORE it lands**. R4 commissions the fix round and enumerates its content, so
you cannot be surprised by it — but "before" is the rule's word, so I am
declaring the commit-set here first and will report results in **D9** (updated
per-file-sourced pre-registration + refrozen ledger quoting freeze-1). Splitting
your requested D8 into declare-then-report rather than folding the declaration
into a post-hoc entry.

### DECLARED commit-set — ONE commit-set on top of `75cb9c67`

Planned as two commits (production/guard behavior vs pure doc-and-prose truth),
both landing before ceremony. If the shape changes I re-declare BEFORE landing.

**Commit A — guard + contract truth (nits 1, 4, 5, 6, 9)**
- Rename the two conformance cells whose NAMES carry retired protocol names
  (`..._satisfies_expansioncontext` → `..._expansionruntime`;
  `..._satisfies_localecontext` → `..._localeaccess`). Node IDs move, counts do
  not.
- Reword the ALLOWLIST contract in BOTH places (module docstring + the header
  above `ALLOWLIST`) from bare "MAY ONLY SHRINK" to the contract actually
  shipped: shrink-only EXCEPT same-commit scope-/detector-extension-coupled
  justified entries per 5B.1-R0 / R1.6. New text quoted verbatim in the ledger
  (also discharges brief Phase A item 2 as written).
- Close the vacuous-pass window in
  `test_post_endpoint_modules_are_all_dispositioned`: ancestor check FIRST, and
  route a non-ancestor `SCOPE_ENDPOINT` to the LOUD
  `_warn_selfcheck_unverified` path instead of an empty-range silent pass. Adds
  a RED self-test arm that asserts the REASON, not just the outcome — my own
  lesson 2, applied to my own guard.
- Fix the detector docstring's over-claim: the class-attribute extension does
  NOT cover the `self.shell = s` INSTANCE-assignment shape that commit iv
  removed (a bespoke pin covers that; the detector shape is 5B.2's).
- Widen the leaf pin to assert `psh/utils/__init__.py`'s eager imports stay
  stdlib-only — the `core → utils` import path executes it, so a non-stdlib
  import there would resurrect the cycle the move just killed.

**Commit B — doc + prose truth (nits 2, 3, 7)**
- De-line the rotting citations in `psh/protocols/__init__.py`: cite by SYMBOL,
  not line, for BOTH collision references. You are right that `:90` was stale at
  my own tip — commit iii moved it to `:92`. `:387` is correct today and rots
  identically, so both go.
- Re-point or mark-historical the three narrative `_POSIX_CLASSES` mentions in
  `docs/architecture/locale_service_design_2026-07-06.md` (:225, :269, :453),
  which currently assert present-tense ownership of a symbol that no longer
  exists.
- Re-derive the `state.locale` reader census MYSELF (not adopt the verifier's
  number), fix the "three readers" prose, and update ledger §A6's witness note
  so 5B.2's migration set starts from the TRUE census.

**Ledger errata (nit 8), after the commits:** unfreeze → correct the §A8
register labels (MEDIUM-14 / LOW deferred-import rows are **Part A**, not Part
B) and the §A2b citation (`_protocols.py:28` → `:31`) → **refreeze QUOTING
freeze-1 md5 `9328447039b7eb77de35c0d6cac62f4c`** per the chain rule.

### Pre-registration for the fix round — per lesson 3, sources only

Stated now, refined in D9 from per-file counts BEFORE any gate run. Expected
count delta: **0**. Renames move node IDs, not counts (nit 1). The new RED
self-test arm (nit 5) is **+1**. Leaf-pin widening (nit 9) — I will state
whether it is a new cell or an assertion inside the existing one from the file's
own count, not from intent. **No term will appear in the D9 pre-registration
that a per-file count does not demonstrate** — that is exactly the mistake that
made §B5 wrong, and I am not repeating its shape.

Nothing else touched. Never-touch list holds. Proceeding now; results in D9.

md5 of this file before this append: 47be66fa84550b47730f4648242a2edf

---

## D9 (dev-5b-1, 2026-08-08) — ALL 9 REQUIRED NITS FIXED. Ledger REFROZEN (freeze-2). Ready for ceremony.

**ACK: R4** (highest R-entry on re-read this turn; sequence R0, D1, D2, D3, R1,
D4, D5, R2, D6, D7, R3, R4, D8). Commit-set was declared in D8 BEFORE landing,
per the mechanical tip rule; it landed as declared, in the two commits declared.

**New final tip: `dc843423`.** 6 commits total on `8af29e6d`.

| SHA | Scope |
|---|---|
| `743159ab` | guard + contract truth (nits 1, 4, 5, 6, 9) — **no production code** |
| `dc843423` | doc + prose truth (nits 2, 3, 7) — **prose only** |

### The 9, each with what I actually did

1. **NAME-VS-BODY renames.** `..._satisfies_expansioncontext` →
   `..._expansionruntime`; `..._satisfies_localecontext` → `..._localeaccess`.
   Counts unchanged at 7, as you predicted.
2. **De-lined citations.** Both now cite by SYMBOL. You were right that `:90`
   was stale **at my own final tip** — commit iii of this slot moved it to `:92`.
   A citation that rots inside one slot rots again; `:387` went too.
3. **Doc residue.** The three narrative `_POSIX_CLASSES` mentions (:225, :269,
   :453) now name the current owner while preserving what the record said at the
   time. The reference-map file:line list is already covered by the dated note
   from commit iv.
4. **ALLOWLIST contract reworded in BOTH places**, and the new text is **quoted
   verbatim in ledger §B12.2** — which discharges brief Phase A item 2 as
   written. The docstring now also states WHY the exception must exist: an
   extension that cannot record what it finds either lands red or quietly
   narrows its own scope.
5. **Vacuous-pass window closed.** Ancestry tested FIRST; a non-ancestor
   endpoint routes to the loud `_warn_selfcheck_unverified` path. The RED
   self-test asserts the **REASON** — the warning must name the vacuity, the
   cause and the endpoint — plus a **control** asserting the endpoint IS an
   ancestor on a normal checkout, because a warn path that swallowed every
   invocation would otherwise leave both cells green. The uncommitted-module
   window is recorded as RECORD-ONLY in §B12.3.
6. **Detector over-claim fixed**, and §B12.4 adds the **substituted-proof-route**
   discharge row you asked for. Stated plainly there: the brief's literal
   "plant the offender in the real module and commit it" is not achievable — a
   committed real-module offender IS production code and would hold the ratchet
   permanently red. Permanence comes from the enumeration + ALLOWLIST anchors
   plus synthetic-source detector self-tests, with the real-module plant proven
   per-round by instrument 13.
7. **Census re-derived MYSELF** (instrument 19, AST) rather than adopting your
   number — and it confirms yours: **SIX files, 13 sites**. The omitted three
   are `core/scope.py`, `executor/array.py`, `expansion/operators.py`. Prose and
   ledger §A6 both corrected. Worth flagging for 5B.2: **`core/scope.py` is a
   CORE file reading the locale service**, so the three-file witness set would
   have sent 5B.2 past the one reader most likely to matter for layering.
8. **Ledger errata applied**, each verified by me before applying rather than
   taken on trust: Part A spans L14–51 and Part B starts at L52, so MEDIUM-14
   (L44) and the LOW row (L50) are indeed **Part A** — my mislabel; and
   `grep -n 'shell:' psh/expansion/_protocols.py` gives **`:31`**, not `:28`.
   Both were real errors of mine.
9. **Leaf pin widened** to `psh/utils/__init__.py`: importing the table executes
   the package `__init__` first, so an eager import reaching outside `psh.utils`
   would hand `psh.core` that dependency transitively and restore the killed
   cycle while the leaf module still looked innocent.

### LEDGER REFROZEN — freeze-2

**Freeze-2 md5: `876a2d86ec2f6baa5a2a3afccc576f6b`.**
**Chain rule: freeze-1 md5 was `9328447039b7eb77de35c0d6cac62f4c`** (quoted per
the rule). Recompute on receipt.

### FIX-ROUND PRE-REGISTRATION — per-file sources only (ledger §B12.6)

| File | before | after | delta |
|---|---|---|---|
| `test_shell_consumer_ratchet_q1.py` | 20 | **22** | **+2** |
| `test_posix_class_table_ownership.py` | 5 | **6** | **+1** |
| `test_protocol_conformance_q1.py` | 7 | 7 | 0 |
| `test_protocol_name_collision_q5.py` | 7 | 7 | 0 |
| **fix-round delta** | | | **+3** |

**Expected at ceremony: 23,921 passed / 1,620 skipped / 10 xfail;
compare-bash 3,046 / 26 at +0; ruff clean; mypy 276 clean.**

**Correction against my own D8 estimate, stated rather than quietly absorbed:**
D8 predicted "+1 for the RED self-test arm". The landed figure is **+2** for
that nit — I wrote the reason-asserting arm AND its control. D8 was an
intention; §B12.6 is a measurement, and every term there is a `--collect-only`
count of a named file. That is lesson 3 applied to the very entry that announced
it: **no term appears that a per-file count does not demonstrate.**

### Verification at the new tip

Targeted: `tests/unit/tooling` + `tests/unit/protocols` +
`test_locale_service.py` + `test_analysis_session.py` → **842 passed**.
`ruff check psh tests tools` clean. `mypy` clean, **276** files.
Never-touch re-verified across all 6 commits (`git diff 8af29e6d..dc843423`):
**UNCHANGED, all seven.** Manifest regenerated: **17 instruments**,
self-excluding, command-generated.

No heavy run performed in this round — I have not re-run the gate or
compare-bash since `75cb9c67`, and I am not doing so without a GO. The figures
above are the pre-registration for whatever gate the ceremony runs.

### Routed items — acknowledged, NOT absorbed (ledger §B12.8)

Twin mypy-guard stale endpoint → **5C.1**; instance-assignment detector shape →
**5B.2**; pre-existing order-dependence → ceremony addendum; ARCHITECTURE.md
:98/:125 → **yours** at the bump; CHANGELOG old-name mentions are HISTORY and
stay.

Holding here. Mechanical tip rule stands at `dc843423` — any further commit gets
declared before it lands.

md5 of this file before this append: bc678a6eb6cd5a2c4f6d46219bb50a52

---

## R5 (integrator, 2026-08-08) — FIX ROUND ACCEPTED. SLOT VERIFIED-COMPLETE. CEREMONY BEGINS (commits declared).

**ACK: D9** (highest D-entry on re-read; sequence through D9).

**Integrator-direct re-verify performed in MY OWN detached worktree at
dc843423 (B71; discriminator asserted):** 42 = 22+6+7+7 targeted greens
matching your §B12.6 per-file counts EXACTLY; old test names grep-zero,
new names present; protocols/__init__.py citation line-numbers grep-zero
(symbol-cited); ALLOWLIST contract reworded in BOTH places (docstring
"shrink-only WITH ONE NARROW EXCEPTION" + header "CONTRACT: shrink-only,
EXCEPT entries added in the SAME COMMIT..."); merge-base --is-ancestor
check present ahead of the warn route; state.locale census RECONCILED
(my 8 string-hit files = your 6 production readers + the service
definition + the protocol prose — exact). Freeze-2 md5
876a2d86ec2f6baa5a2a3afccc576f6b RECOMPUTED + SNAPSHOTTED. Your D8
declare-before-land reading of the tip rule, and the D8→D9 +1→+2
correction stated as measurement-over-intention, are both the record
working as designed. Fault register carries the §B5 phantom term as
gate-caught record-integrity; zero false findings either direction this
slot.

**SLOT 5B.1 = VERIFIED-COMPLETE at dc843423.** Your work is done; hold
still. The scope.py finding (a CORE reader the old witness prose would
have missed) is exactly why R4 item 7 existed — it rides into 5B.2's
brief.

**CEREMONY COMMITS DECLARED (mechanical tip rule, mine, landing on this
branch now):** (1) rescue tree 5b.1-rescue/ (brief + frozen ledger +
this inbox + 17 instruments + transcripts + manifest); (2) LEDGER.md
updates (MEDIUM-14 progress note — row stays OPEN; Part C W5-R1 +
5B.1 rulings; Part D registrations incl. the pre-existing
order-dependence row + routed pointers + banked lessons); (3) version
bump 0.775.0 (version.py + CHANGELOG + README + ARCHITECTURE incl. the
owed :98/:125 renames); (4) attestation FINAL after the gate at the
bump SHA in a fresh detached worktree (pre-registered per your §B12.6:
23,921 / 1,620 / 10). Then push → PR → merge → tag watch → post-merge
addendum (final inbox snapshot + sign-off record). Sign-off protocol:
after the tag mints I post the rescue-tree manifest md5s here; you
verify byte-exactness against your worktree copies and sign off in a
D-entry (4B.x precedent).

md5 of this file before this append: 3c94191164d65fcb87f6f71000a574e9
