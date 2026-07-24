# Boundary Integrity Campaign

- **Date:** 2026-07-16
- **Status:** Active architecture plan; implementation has not started
- **Correctness baseline:**
  [`ground_up_reappraisal_20_correctness_textbook_2026-07-11.md`](ground_up_reappraisal_20_correctness_textbook_2026-07-11.md),
  PSH 0.698.0 at `8d1cb9f6`
- **Current revalidation:**
  [`ground_up_reappraisal_20_correctness_continuation_2026-07-14.md`](ground_up_reappraisal_20_correctness_continuation_2026-07-14.md),
  PSH 0.724.0 at `d1b8ef35`
- **Authorization:** bold architectural work is explicitly in scope
- **Amended:** 2026-07-17 — R3 command-environment overlay, I1 open-description identity, durable Phase-E
  evidence, E4 release attestation, S1 re-pin note, #21-residue ownership (from an external adversarial review
  plus integrator follow-up)

## 1. Mission

The campaign executes the central diagnosis from reappraisal #20:

> The dominant problem is semantic information loss at subsystem boundaries.

The goal is not to add compatibility conditionals around the reported examples. The goal is to make the semantic
facts named by the report survive, with enough fidelity and ownership information, until the last consumer that
needs them.

The campaign closes #20 C1/H1-H19 and the continuation's directly related evidence and ownership findings. It also
implements every item in #20's target architecture:

- lossless heredoc identity and content;
- field-preserving expansion;
- typed, ordered redirection operations over owned resources;
- one command-resolution result;
- tri-state variable lookup;
- one exhaustive AST traversal;
- narrow runtime protocols instead of broad `Shell` injection.

This is a bounded claim. It does not claim to close every medium or low item in reappraisals #20 and #21. Adjacent
items may ride only when they consume the same new representation and do not enlarge its responsibility.

Named residue deliberately left outside these packages — the #21 builtin option-parse family (`printf -v`
attached form, `read -N` combined with `-t`/`-s`, `pwd -L -P` ordering, `history` multi-option dispatch) and the
`export -p`/`readonly -p` operand-handling defects — must be either declared as riders on R2/Q2 at launch or
queued as an explicit follow-on wave. It does not silently vanish between the two appraisals' queues.

## 2. What "textbook-clean" means

A boundary is clean only when all of the following hold:

1. **Fidelity:** the representation can encode every distinction still needed downstream. Quote/protection runs,
   explicit empty fields, syntax timing, source order, cursor identity, setness, and resource ownership are data,
   not comments or parallel booleans.
2. **Authority timing:** a decision is made only after its authoritative context exists. Array type precedes
   subscript interpretation; normalized command identity precedes resolution; invocation parsing precedes startup;
   monitor mode precedes asynchronous signal policy.
3. **Single decision:** one named chokepoint computes each semantic answer. Consumers receive the answer rather than
   re-deriving it from strings, registry reads, environment snapshots, or AST shape guesses.
4. **Explicit lifetime:** state with continuity belongs to the lifetime that needs it. Input pushback belongs to an
   input cursor, not one `read` call. Process-global mutations belong to an activation lease, not construction.
5. **Total outcomes:** success, failure, incomplete input, missing value, harness failure, and print-only history
   expansion are explicit variants. Sentinel strings and exception swallowing are not outcome types.
6. **Directed dependency:** producers do not import their consumers. Runtime components receive narrow protocols;
   no new service-locator dependency on the whole `Shell` is allowed.
7. **Executable guard:** the representation, sole chokepoint, and consumer census are protected by a behavioral pin
   and a static or synthetic-offender guard.

Flattening is permitted only at a terminal boundary such as `argv`, an environment vector, a pathname syscall, or
display output. A deliberate-loss exception must name that terminal consumer, explain why no later semantic
consumer needs the fact, and link to a pin. "Reparse it later" is not a deliberate-loss exception.

## 3. Standing implementation rules

Every work package follows the same ceremony:

1. Re-locate every cited symbol at the branch's current HEAD and reproduce the defect before editing.
2. Record a boundary ledger in `tmp/boundary-ledgers/<ID>.md` with columns:
   `fact | producer | old loss point | canonical type | authority | consumers | guard`.
3. Pre-register the Bash 5.2 probe and PSH regression. Demonstrate every live behavioral pin red on the base SHA.
   The already-resolved C1 pin stays green and must fail under a synthetic resurrection of string reinterpretation.
4. Land the canonical type and its invariant tests before migrating consumers.
5. Migrate every inventoried consumer. Temporary adapters may expose derived strings only to terminal consumers;
   they may not feed flattened data back into syntax, expansion, matching, lookup, or resolution.
6. Delete the superseded semantic path in the same package. A compatibility adapter must have an owner and removal
   wave.
7. Add a guard that fails on a synthetic second implementation, bypass, or unhandled variant.
8. Run the targeted suite, `ruff check psh tests`, `mypy`, and the current wave gate before integration.

Probe harnesses must start a new process session, kill the whole process group on timeout, cap output, and remove
temporary resources. Behavioral cases run through `-c`, file, and stdin only where those modes are semantically
equivalent. Interactive, rc, job-control, and source-specific cases use an applicability table with explicit `N/A`
reasons instead of meaningless mode duplication.

Shared golden and conformance catalogs are integrator-owned. A work package first lands a dedicated regression
module; the integrator promotes stable cases after merging, avoiding concurrent edits to one catalog.

## 4. Coverage map

| Source finding | Owning package | Canonical correction |
| --- | --- | --- |
| C1 expanded redirect syntax origin, fixed at v0.724 | R1 | Preserve the structural-origin fix and add a no-string-reinterpretation guard. |
| H1/H3 heredoc order and delimiter loss | S2 | `HeredocId` plus one pending-to-collected transaction. |
| H2 late nested-syntax failure | S3 | Typed syntax templates with Bash-correct validation timing. |
| H4/H8 redirection order and duplicate cursors | R1 | One ordered `RedirectProgram` and one here-input open description. |
| H5/H6 field-boundary and protection loss | W1 | `ExpandedWord` containing explicit `ExpandedField` values and protected runs. |
| H7 pattern semantics and complexity | W3 | One iterative, offset-aware pattern relation. |
| H9 function definitions outside normal grammar | S5 | A typed `PipelineComponent` contract and context-aware execution. |
| H10 repeated command resolution | R3 | `NormalizedCommandName` followed by one `ResolvedCommand`. |
| H11/H12/H19 job signals, foreground lifecycle, detach/reap | J1 | Job policy, foreground transaction, shutdown, and reap ownership. |
| H13 unset shadow falls through to environment | R2 | `VariableLookup` and explicit environment materialization. |
| H14 eager script input | I2 | Lazy `ProgramSource` with an owned, protected script descriptor. |
| H15 quadratic completeness | I3 | Resumable lexer/parser session; no whole-buffer trial parse. |
| H16 malformed-byte cascade | I1 | Byte-preserving, source-lifetime `InputCursor`. |
| H17 forced-interactive startup | F1 | Frozen `InvocationConfig` before pure shell construction. |
| H18 process-global locale | F2 | Instance `LocaleContext` under one process activation owner. |
| Continuation A/B | F1/F2 | Construction after configuration; explicit process-global ownership. |
| Continuation C/D | S4 | Immutable parse inputs, per-call state, and honest combinator laws. |
| Continuation E | W3 | Iterative matcher and deterministic complexity guards. |
| Continuation F/G/H | E1-E3 | Honest phase results, typed oracle failures, and hermetic locale/isolation. |

### Current ownership map

These are launch-time ownership areas, not permanent package boundaries. Each work package must re-run its consumer
inventory at the current SHA; shared files are an integration dependency, not evidence that two branches are safe
to merge independently.

| Package | Primary current ownership |
| --- | --- |
| E1-E3 | `run_tests.py`, `pytest.ini`, `pyproject.toml`, `tests/conftest.py`, `tests/conformance/conformance_framework.py`, behavioral/oracle tooling tests |
| F1/F3 | `psh/__main__.py`, `psh/shell.py`, `psh/interactive/rc_loader.py`, `psh/scripting/`, `psh/builtins/source_command.py` |
| F2 | `psh/shell.py`, `psh/core/locale_service.py`, `psh/core/trap_manager.py`, `psh/io_redirect/file_redirect.py`, navigation/exit lifecycle callers |
| S1/S2 | `psh/lexer/`, `psh/ast_nodes/redirects.py`, both parser redirection paths, `psh/scripting/command_accumulator.py`, formatter heredoc paths |
| S3/S4 | `psh/ast_nodes/words.py`, `psh/ast_nodes/arrays.py`, `psh/ast_nodes/control.py`, both parser implementations, `psh/expansion/param_parser.py`, arithmetic evaluation |
| S5 | command/control AST modules, both command grammars, `psh/executor/pipeline.py`, `psh/visitor/` |
| W1 | `psh/expansion/word_expander.py`, `psh/expansion/word_expansion_types.py`, word-expansion consumers |
| W2 | array/operator/arithmetic expansion, core variables, array executor, declaration/unset/`test -v` builtins |
| W3 | `psh/expansion/pattern_engine.py`, `pattern.py`, `extglob.py`, `glob.py`, parameter expansion, pattern consumers such as history |
| R1 | `psh/io_redirect/`, redirect execution in `psh/executor/command.py`, redirect AST/origin guards |
| R2/R3 | core scope/state/variable/special-registry modules, variable expansion/operators, environment builtins, executor command/strategy modules |
| I1-I4 | input reader plus `read`/`mapfile`, I/O fd ownership, scripting input sources/accumulator, interactive key/history modules |
| J1 | executor launcher/pipeline/subshell/job-control modules, job-control/disown/exit builtins, REPL and source shutdown callers |
| Q1-Q3 | touched constructors/protocols, tooling ratchets, `ARCHITECTURE.md`, subsystem guides, public package exports |

## 5. Canonical representation set

These names are campaign contracts. Minor field-name changes are allowed during implementation review; collapsing
one of these types back into raw strings, word-wide flags, or caller-owned state is not.

| Type | Minimum semantic content | Sole authority |
| --- | --- | --- |
| `ShellRunResult` | completed process data or typed spawn, timeout, and decode failure | oracle runner |
| `InvocationConfig` | source kind, interactive request, ordered option transitions, parser, `$0`, positionals, startup policy | `parse_invocation()` |
| `ActivationLease` | shell owner token, nesting depth, locale/signal/cwd/std-fd baselines, LIFO state | `ProcessLeaseCoordinator` |
| `LocaleContext` | per-shell classification, collation, and case-mapping policy | shell instance |
| `ProgramSource` | source kind/name, byte policy, line origin, descriptor ownership | source service |
| `LexicalWord` | typed parts, homogeneous protection runs, exact source span | word scanner |
| `HeredocSpec` | stable id, raw/cooked delimiter, quote and tab policy, source span | heredoc delimiter scanner |
| `CollectedHeredoc` | spec id, body, terminator or EOF outcome, body span | FIFO collector |
| `ParseInputs` / `ParserState` | immutable caller context separated from per-call cursor/open state | parser driver |
| `WordTemplate` | typed word parts and nested programs, never an expansion-bearing raw string | parser word builder |
| `ArithmeticTemplate` | literal arithmetic fragments plus nested expansion nodes; lazy arithmetic parse | arithmetic evaluator |
| `SubscriptSpec` | structured word template interpreted only after target type is known | `SubscriptEvaluator` |
| `PipelineComponent` | exhaustive command/compound/function variants plus execution context | parser and executor contract |
| `AstChildSchema` | exhaustive structural child fields and supported containers | `walk_ast()` |
| `ExpandedWord` | zero or more explicit fields | word expander |
| `ExpandedField` | ordered protected/active runs, split eligibility, origin, explicit-empty identity | field algebra |
| `CompiledPattern` | syntax tree/NFA built directly from protected runs and a consumer profile | pattern compiler |
| `RedirectProgram` | source-ordered `Open`, `Dup`, `Close`, and `HereInput` operations with owned resources | redirect planner |
| `NormalizedCommandName` | post-quote-removal spelling and bypass provenance | command-word normalizer |
| `CommandEnvOverlay` | fully expanded prefix assignments as an immutable environment view; PATH/hash policy input | prefix-assignment expander |
| `ResolvedCommand` | dispatch kind/target, POSIX status, assignment persistence, strategy, exec/redirection policy | command resolver |
| `VariableLookup` | `MISSING`, `PRESENT_UNSET`, or `VALUE` plus binding metadata | scope lookup |
| `InputCursor` | owned open-file-description identity, refcounted fd bindings, raw pushback, decoder state, decoded queue, EOF | I/O resource layer |
| `ForegroundJobSession` | job registration, process group, terminal state, wait/report/cleanup state | job runtime |
| `AsyncJobPolicy` | stdin and INT/QUIT policy derived from monitor/background state | job launcher |
| `HistoryExpansionResult` | `NONE`, `EXPANDED`, `PRINT_ONLY`, or `ERROR`, text and source spans | history scanner/expander |

## 6. Phase E: trustworthy evidence first

No semantic package begins until Phase E passes. The campaign cannot grade architectural work with a runner that
can bless an internal error or a conformance harness that can compare two crashes as equal.

### E1. Structured gate results

**Decision:** no nonzero pytest exit is translated to success. The xdist teardown race is fixed, avoided by a
different runner configuration, or remains a failed gate; transcript recognition is not evidence of completion.

`run_tests.py` consumes a structured phase manifest containing collected node ids and counts for passed, failed,
errored, skipped, xfailed, xpassed, and deselected tests. Worker loss, timeout, missing manifest, and any
`INTERNALERROR` are failures independent of the summary text.

The standard tier runs deterministic complexity invariants such as state/transition counts. CPU and wall-time
microbenchmarks run in a separate serial/nightly tier with recorded baselines. Removing the global performance
ignore must not silently import millisecond thresholds into xdist.

**Guards:** synthetic internal error, truncated manifest, worker loss, collection loss, and unexpected skip/xfail
fixtures; a test proves the classifier cannot return success for any nonzero exit.

### E2. One oracle runner

All Bash and PSH differential execution uses:

```text
resolve_bash() -> BashOracle(path, version)
run_shell_case(...) -> Completed | SpawnFailure | Timeout | DecodeFailure
```

Harness failures are rejected before stdout/status/stderr comparison. Two equal failures are never conformance.
The runner owns process-group timeout cleanup, bounded output, a temporary cwd, explicit UTF-8 plus
`surrogateescape`, and a hermetic environment builder. An AST/static ratchet rejects bare `bash` and hard-coded
Homebrew paths outside the resolver.

### E3. Hermetic process and locale state

Harness environments remove inherited `LC_*` and `LANG` before applying each case. PEP 538 handling is tested
against `LC_ALL`, an explicitly supplied `LC_CTYPE`, `PYTHONUTF8`, `PYTHONCOERCECLOCALE`, and `-X utf8`; where
startup provenance is unknowable, PSH keeps the value and documents the conservative rule.

Signal dispositions, cwd, standard descriptors, and locale are snapshotted and restored per owning test. Tests
whose inner shell already uses `subprocess.run` are not described as fixed by "another subprocess". Isolation is
at the pytest-worker/process-group boundary, and the contaminating predecessor or leaked resource must be named
and fixed.

### E4. Same-SHA release attestation

**Campaign decision:** the local-gate fast loop is retained — no required PR CI — but `release-tag.yml` stops
tagging unattested commits. A green standard gate writes a compact SHA-stamped attestation (result counts,
platform, gate command) committed with the version bump; the tag workflow verifies the attestation matches the
tagged SHA before creating the tag, and a version bump without a matching attestation fails the workflow loudly
instead of tagging silently.

**Phase-E exit:** at one SHA, three standard runs under three serial-order seeds have exit zero and identical
collection/outcome censuses; one `--compare-bash` run and the full conformance suite pass; `ruff check psh tests`
and `mypy` pass. Working transcripts live in `tmp/boundary-ledgers/E/`; the exit manifest itself (SHA, censuses,
seeds, exact commands, transcript hashes) is committed with the Phase-E close so the criterion's evidence
survives clones, branches, and routine `tmp/` cleanup.

## 7. Phase F: invocation, source, and process ownership

### F1. `InvocationConfig` before `Shell`

`parse_invocation(argv)` is pure and returns a frozen configuration before any shell is constructed. It validates
the parser, analysis mode, source kind, positionals, and ordered option transitions. Interactive-family state is
independent of input source: `-ic` performs interactive startup while taking commands from `-c`.

The short-option surface is registry-derived. Invocation-only options are an explicit table. **Campaign decision:**
`-h` means Bash `hashall`; `--help` displays help. **Sign policy (corrected 2026-07-18 by F1 probes — bash 5.2
ground truth outranks this document's original "+i/+s/+c sign-aware" assumption):** `+i` IS sign-aware
(cancels interactive); `+s` and `+c` are sign-accepted-but-BLIND (`+` behaves like `-` — `bash +c 'echo hi'`
runs the command). All three pinned in the invocation matrix with the probe transcripts
(`tmp/boundary-ledgers/F1-probes/`). Bare trailing `-o`/`+o` prints the `set -o`/`+o` listing (rc 0) and
continues, per bash; `-H`/`+H` join the registry surface (closes reappraisal-21 CORE-4, both invocation and
`set` paths pinned).

`Shell(config)` is construction-pure. It does not read rc/history, call `setlocale`, install signal handlers, change
cwd, or rebind descriptors. `Shell.for_subshell()` clones runtime state without repeating startup.

### F2. One process activation owner **[BOLD]**

A minimal process-wide `ProcessLeaseCoordinator` enforces one active shell owner. `Shell.activate()` obtains an
owner token and LIFO `ActivationLease`; nested activation by the same owner is counted, competing owners fail
before mutation, and partial acquisition rolls back.

Locale matching is instance-owned through `LocaleContext`. libc locale, signal dispositions, and the
standard-fd baseline are component leases requiring the active token. **Amended 2026-07-18 (F2 ruling):** the
cwd baseline is RECORDED in `ProcessBaselines` but deliberately never restored — `cd` persistence is shell
semantics and the process owns its cwd, per §16; the original sentence's letter listed cwd as a restoring
lease, which contradicted §16 and the guard list. Permanent `exec` redirection remains
permanent inside the active shell and restores only when an embedded shell deactivates. Successful `os.exec`
closes backup descriptors through CLOEXEC.

`Shell.shutdown(reason)` is idempotent and is the only top-level cleanup path. Exit builtin, REPL EOF, startup
failure, and normal source completion all call it.

**Guards:** construction purity; second-owner rejection; same-owner nesting; out-of-order release; failed-acquire
rollback; locale behavior of one constructed shell unchanged by a second construction; repeated permanent
redirects; every shutdown route.

### F3. One sourced-program service

`ProgramSource` carries source name, source kind, byte/decoding policy, line origin, and ownership. Script files,
stdin scripts, rc files, `source`, validation, and analysis enter parsing through this normalization boundary.
NUL and invalid-byte policy is decided once.

`execute_sourced_file(SourceRequest)` owns source depth, optional positionals, `FunctionReturn`, RETURN traps, and
restoration. `SourceBuiltin` and rc loading call the same service; rc execution is not a second source dialect.

## 8. Phase S: syntax remains syntax

### S1. Complete lexical words before keyword classification

The scanner constructs one `LexicalWord(parts, span)`. Literal runs carry `UNQUOTED`, `ESCAPED`, `SINGLE`,
`DOUBLE`, or `ANSI_C` protection. The parser recognizes a reserved word only when the complete lexical word is an
exact unquoted literal in a grammar position. **Amended 2026-07-18 (S1 ruling):** realized as disciplined
invariants over the existing Token+parts model (fusion-first ordering, complete-word eligibility gate,
span/protection-integrity pins) rather than a new type — a sanctioned declared deviation; all §5 contract
facts (typed parts, homogeneous protection runs, exact span) are carried and pinned.

Delete keyword-before-fusion behavior and any post-token word fusion that can discard quote or source-span facts.
The existing pin that locks the old promotion order (`test_post_lex_fusion_order_b3.py`) documents a deliberate
divergence being retired here: it is re-pinned to the bash behavior in the same package, demonstrated red-on-base.
Guards cover quoted keywords, composite words such as `then$x`, and case/loop grammar positions.

### S2. One heredoc transaction **[BOLD]**

The delimiter scanner creates `HeredocSpec(HeredocId, raw, cooked, quoted, strip_tabs, span)`. The collector owns a
`deque[PendingHeredoc]` and compares input only with its head. It produces `CollectedHeredoc(spec_id, body,
termination, span)`. Duplicate delimiters remain distinct because identity is ordinal/source-based, not textual.

The lexer/parser boundary returns an immutable `LexedUnit(tokens, heredocs)`. Redirect AST nodes reference the
stable id; executable ASTs never carry a pending or optional body. Trial input returns typed `Incomplete`, while
true EOF returns an EOF termination and diagnostic. Delete parallel heredoc maps, string-derived keys, attachment
walks, and duplicate delimiter scanners.

### S3. Structured syntax with Bash-correct timing **[BOLD]**

Parameter operands, array subscripts, arithmetic expansions, and C-style loop clauses become `WordTemplate`,
`SubscriptSpec`, and `ArithmeticTemplate` values. Modern command/process substitutions carry parsed `Program`
nodes. Generic `word: str`, `index: str`, and `expression: str` fields stop being semantic authorities.

The outer parser validates nested shell grammar at read time, including `$()` inside parameter operands,
arithmetic templates, and subscripts. It does **not** eagerly parse arithmetic grammar. Arithmetic is parsed only
when evaluation reaches that expression, after nested expansions; dead `&&` branches, unselected parameter
operands, and unexecuted loop updates retain Bash's lazy diagnostic timing. Dynamically generated arithmetic syntax
therefore remains valid.

Legacy backticks receive a typed `DeferredBacktickTemplate` with an explicit Bash-pinned timing policy; they are
not smuggled through a generic raw string or incorrectly forced into modern `$()` timing. Each syntax-bearing
region names its grammar and validator. There is no generic "parse every raw region as a shell program" helper.
**Amended 2026-07-18 (S3 ruling 2):** the deferred-backtick contract is realized as a NAMED, GUARDED invariant
over the existing typed node (`CommandSubstitution(backtick_style=True, program=None)`) rather than a new node
type — a sanctioned declared deviation (S1 precedent). Conditions: one named policy predicate as the sole
validation-path seam (no scattered flag checks); a synthetic-offender guard (backtick-with-program fires;
forcing backticks into the eager validator turns timing pins red); the full bash timing tuple pinned from
probe evidence (non-fatal, empty expansion, surrounding command still executes, rc 0, stderr diagnostic).
**Amended 2026-07-18 (S3 ruling 1, revised same day):** nested-substitution rejection keeps psh's uniform
rc 2; bash's 127-vs-2 channel split AND the eval/source frame-abort fatality are ONE bash mechanism
(command-substitution-specific — plain syntax errors in eval/source are non-fatal in both shells; probed)
and travel together as a carry to I3 (driver/channel work, F1/F3-owned files). S3's contribution: direct
channels (-c/file/stdin) fully close the whole-buffer rejection timing, and the read-time validator raises
a distinctly TYPED substitution-origin ParseError subclass — behaviorally inert now, minimal fields, the
declared I3 producer contract (I3 maps tag → fatal + 127 in string channels) — with a structural-identity
pin that operand-family errors are type-identical to top-level `$()` errors.

### S4. Honest parser calls and resumable-ready outcomes

Immutable `ParseInputs(source, line_offset, lexer_options, heredocs)` are separate from mutable, per-call
`ParserState(cursor, nesting, substitution_depth, open_constructs)`. Parser instances retain neither after return;
there is nothing to clear in `finally`.

Both parser implementations return `Complete[Program] | Incomplete[ExpectedInput] | Invalid[Diagnostic]`.
Combinator `optional` preserves committed failure, `then`/`map` preserve failure position, and `many` rejects
success without progress. These are algebra-law tests, not examples only.
**Amended 2026-07-18 (S4 rulings — three sanctioned declared deviations, S1/S3 precedent):** (1) the outcome sum
is realized as `parse_outcome()` on both parsers over the single `outcome_from_parse` classifier, with the raising
`parse()` retained unchanged as the terminal materialize adapter (§16 sanctions leaving executor call sites);
(2) `ParseInputs`/`ParserState` are realized as a typed split composed by `ParserContext` (frozen inputs + mutable
state) with the flat accessor surface preserved as delegating properties — sole construction sites guarded;
(3) "nothing to clear in `finally`" holds for the RD driver (sole surviving `finally` is the balanced nesting
counter, guarded); the build-once combinator keeps guarded per-call `finally` clears/restores at its THREE entry
points (`parse` install/clear, `parse_with_heredocs` save/restore, test-facing `parse_partial` install/clear —
count corrected from "ONE" per verify nit; all clear the same two per-call slots) — the mechanism that makes
retains-nothing true for a shared instance — declared as the sanctioned exception with a post-parse snapshot
guard + offender (verifier additionally probed `parse_partial` incl. raising paths: no retention). Handoff-4 note corrected: the `$'E\nF'` cooked delimiter inside command
substitution is NOT a divergence (bash rc 2 nested, matching psh; the earlier "bash rc 0" observation was the
top-level EOF-delimit case — dev probe matrix + integrator re-probe agree).

### S5. Ordinary pipeline components and exhaustive traversal

`PipelineComponent` is a typed sum covering simple commands, compound commands, and `FunctionDef`. The executor
receives an explicit parent/child execution context. A standalone definition updates the parent function table;
pipeline and background definitions execute in child contexts, return zero on successful definition, and do not
leak into the parent.

`walk_ast(node)` becomes the sole structural traversal. AST child fields are schema-declared; compatibility views
are derived and cannot be traversed as second authorities. Every visitor uses the walker or its callback protocol.
**Amended 2026-07-18 (S5 rulings):** (1) H9 narrowed honestly — psh's divergence was a pure GRAMMAR gap
(FunctionDef was Statement-only; both parsers rejected defs at pipeline/list/negation/time/background positions)
while execution already had bash-correct leak semantics per context; the fix is AST-type + both grammars, ZERO
executor changes. (2) Option A SANCTIONED (byte-identical precedent): a standalone top-level def keeps its bare
`Program.statements[0] = FunctionDef` shape; only a def composed into a pipeline/list/negation/time/background
wraps through the and-or machinery — both shapes pinned; full-uniformity Option B declined (would churn every
standalone def's documented shape for zero behavior). (3) walk_ast does NOT descend S3 template `subs` —
excluded from AstChildSchema by construction, matching the CommandSubstitution.program opt-in-helper precedent;
guarded three ways. (4) The old reflection walker's silent skip of `IfConditional.elif_parts` was a latent
traversal bug fixed by the schema walker (sole corpus diff = MetricsVisitor elif counts; pinned).
A synthetic AST node with one child in each supported container shape proves traversal totality.

## 9. Phase W: expansion and pattern semantics

### W1. `ExpandedWord` and field-splicing algebra **[BOLD]**

```text
FieldRun(text, protection=ACTIVE|PROTECTED, split=NEVER|IFS_ELIGIBLE, origin)
ExpandedField(runs)       # empty runs can mean one explicit empty field
ExpandedWord(fields)      # empty fields tuple means word elision
```

Runs are homogeneous, so mixed text such as `a\*b*` retains different protection for the two `*` characters.
The word walker performs field splicing: a multi-field expansion attaches its first field to the active prefix,
commits its middle fields, and leaves its final field active for suffix attachment. `"$@"`, array `[@]`, explicit
empty values, IFS splitting, and affixes all use the same algebra.

No walker returns `str | list[str]`, no `$@` shortcut bypasses later passes, and no string join occurs before field
splitting and pathname generation. Materialization is terminal.

### W2. One subscript authority

`SubscriptEvaluator.evaluate(spec, target_kind, use)` interprets a structured `SubscriptSpec` only after lookup
knows whether the target is indexed or associative. Indexed targets expand then lazily parse arithmetic.
Associative targets perform one word/quote expansion under an `ASSOCIATIVE_SUBSCRIPT` policy with no splitting or
pathname generation. Composite quoting such as `h['a''b']=v` is therefore representable.

Assignment, lookup, unset, `test -v`, declaration, arithmetic lvalue, and parameter expansion all call this
service. Delete raw quote-pair stripping, consumer-specific `int()`, and `assoc_key(raw_text)` implementations.
**Amended 2026-07-19 (W2 rulings — integrator re-probed the load-bearing claims incl. `$(( a[] ))`
warn-twice-continue and arith-key no-re-expansion):** (1) the service API takes the subscript's raw TEXT
rather than the SubscriptSpec object — SANCTIONED: builtins (`unset`, `test -v`) receive already-expanded
argument strings where no spec exists, and parser-side consumers pass `node.index` which S3's consistency
guard holds identical to `index_spec.text`; a future spec-carrying overload remains open. (2) Empty-arith-
subscript continuation (bash warns twice + continues rc 0; psh fatal-discards) — ACCEPTED as a documented+
pinned divergence, both sides pinned; the warn-continue machinery is runtime-truth territory, CARRIED to
the R-phase. (3) `unset 'a[@]'` empties-not-removes — NOT scope creep: the brief's probe matrix explicitly
covered the special subscripts in every use; shipped as a probed bash-5.2 correctness fix. Probe-derived
doctrine recorded: in ARITH context the associative key receives quote/escape removal but NO `$`-re-expansion
(the arith pre-pass already substituted; bash never rescans) — `associative_key(raw, expand_dollar=False)`.

### W3. One iterative pattern relation **[BOLD]**

`PatternCompiler` consumes protected `FieldRun` values directly. The iterative engine exposes the relations its
consumers actually need:

```text
full_match(text)
matching_ends(text, start)
matching_starts(text, end)
matching_spans(text)
```

Prefix removal uses matching ends; suffix removal uses matching starts; substitution uses spans. Pathname
expansion layers slash-component and leading-dot policy over the same engine. Consumer profiles cover pathname,
`case`, `[[ ]]`, parameter removal/substitution, and `HISTIGNORE`; a use is not exempt merely because it is called
a "name filter".
**Amended 2026-07-19 (W3 rulings):** (1) the matcher is MEMOIZED RECURSION with iterative literal-chain
advancement, not a fully-iterative worklist — SANCTIONED: the fully-iterative design measured 2–12× slower
(bounce-grade under the W1 perf precedent) while the memoized form closes both STATED H7 defects (no
RecursionError on deep literal chains to 20,000; polynomial matching via the count_states guard) at
base-comparable speed; recursion depth is bounded by the pattern's branch-construct count, subject to
verification's adversarial-pattern attack. The §W3 word "iterative" is honored at the defect level, recorded
here as a declared realization. (2) `glob_to_regex_body`/`extglob_to_regex`/`_convert_pattern` are
production-dead but test-oracle-referenced — DEFERRED-DELETION sanctioned (census entry recorded; deletion
routed to the Q-phase cleanup rather than end-of-slot test surgery); `_bracket_to_regex`/`_bracket_match`
remain live engine components.

Primary complexity guards assert visited-state/transition bounds and absence of Python recursion. Timing tests are
nightly backstops. The protected-run interface lands before the matcher migration, so W1 and W3 are not concurrent
contract authors.

## 10. Phase R: runtime decisions and resources

### R1. Ordered `RedirectProgram` **[BOLD]**

The planner emits source-ordered `OpenFile`, `DupFd`, `CloseFd`, and `HereInput` operations with typed targets,
flags, source locations, and owned resources. One semantic applicator executes operations immediately in order;
fd and Python-stream adapters may differ mechanically but interpret the same program. Internal descriptors are
relocated rather than allowing semantic closes or dups to be postponed.

Here-input content is materialized once into one open file description shared by builtin and child consumers.
Open flags, atomic noclobber, target fd, rollback, and diagnostic source are computed once. Temporary redirects use
one guarded transaction; permanent redirects require the active process owner.

The resolved C1 fix receives a structural-origin guard: expanded redirect text can never be reclassified as
process-substitution syntax.
**Amended 2026-07-19 (R1 ruling):** the redirect-diagnostic `line N:` prefix fix is IN SCOPE — §R1's
"diagnostic source computed once" covers it, and the errprefix convention (v0.690.0: ALL non-interactive
runtime diagnostics carry `psh: line N:`) made the bare `format_redirect_error` output an inconsistency, not
a choice; routed through `error_location_prefix()` with the two affected pin files updated to bash-verified
prefixed forms. Integrator re-probed H4 with the discriminating fd3-open precondition (deferral bug fires
only when the dup source is inherited-open — environment-sensitive row, worth its own pin note), H8 replay,
C1, and the prefix row three-way: all confirmed.

### R2. Variable truth and environment materialization **[BOLD]**

`ScopeManager.lookup()` returns `VariableLookup(MISSING | PRESENT_UNSET | VALUE, binding)`. A declared-unset local
stops lookup. Environment input is imported atomically into exported variable cells; `shell.env = {...}` performs
that import rather than creating a second lookup authority. Child environments are materialized from visible
exported cells.

One mutation engine owns set, append, attributes, unset, redeclare, temporary promotion, and array-element writes.
Attribute changes resolve namerefs except when modifying the nameref attribute itself. Dynamic specials consult
lexical scope, and `$!` absence remains absence.

The guard observes mutation routing across operation, variable kind, scope, nameref, readonly, dynamic special,
and environment replacement.
**Amended 2026-07-19 (R2 rulings — integrator re-probed 6 load-bearing rows three-way incl. the guard-caught
seventh masking site):** (1) the `shell.env = {...}` atomic-import sentence is realized STRUCTURALLY rather
than in the setter: post-H13, lookup NEVER consults `state.env` (the second-lookup-authority hazard the
sentence exists to close — deleted and guard-locked), startup env input imports atomically into exported
cells, and child environments are pure projections of visible exported cells; the raw setter remains a
projection write because its only consumers (the env builtin's deliberate scoped swap — where importing
would make `env -i` unset parent variables — and a lifecycle identity pin) must NOT import. SANCTIONED as
the correct reading of intent over letter; a future import-API, if ever needed, gets its own probe-backed
slot. (2) `VariableLookup` as slots-non-frozen — RATIFIED on the W1 FieldRun precedent (hot-path
construction cost; allocate-fresh-never-mutate; slots guard pinned).

### R3. Normalize, expand assignments, then resolve once

Command-word normalization produces `NormalizedCommandName`; it cannot consume a result that does not yet exist.
Prefix assignments are expanded left-to-right BEFORE resolution into an immutable `CommandEnvOverlay` — a typed
view of the command's effective environment that never mutates live scope. `resolve_command(name, overlay,
context)` is then the sole reader of function, builtin, hash, and PATH registries; PATH search and hash policy
consult the overlay, so `PATH=/only cmd` resolves against the temporary PATH and a stale hash entry the
temporary PATH excludes is rejected — exactly the behavior the current code already gets right. It returns
`ResolvedCommand` with dispatch target, precedence, POSIX-special status, prefix-assignment persistence,
execution strategy, and `exec`/permanent-redirection policy.

Scope creation and pop/promote happen only after resolution, driven by the overlay plus the resolution — never
recomputed from raw names. A static ratchet rejects registry reads and raw-name dispatch decisions outside the
resolver. The behavior matrix spans command kind, POSIX mode, prefix assignment (temporary-PATH hit, miss, and
stale-hash rows; left-to-right assignment expansion order), `exec`, and quoted/backslash spellings.
**Amended 2026-07-19 (R3 rulings):** (1) the overlay carries FACTS, not expanded values — `CommandEnvOverlay
(assignment_names, has_path_override, has_posix_override)`; prefix VALUES expand in `apply_prefix` AFTER
resolution (pre-expanding only PATH would reorder `A=$(c1) PATH=$(c2) cmd` side effects), and the deferred
external search reads the live environment the installed prefix determines — RATIFIED as the correct reading
of intent over letter (shell.env precedent); the brief's `effective_path` was DELETED per ruling option (b)
after shipping with zero consumers. (2) The bounce-derived POSIXLY_CORRECT rule: prefix posix-override
detection is NAME-LEVEL (any value incl. empty flips; nameref write-through counts; readonly POSIXLY_CORRECT
blocks the flip — the overlay performs the same readonly walk the installer performs, predicting the install
outcome exactly); posix is the only resolution input a prefix can mutate. (3) The `set -o | grep` subshell
construction masks persistence in BOTH shells — non-subshell (`shopt -qo posix`) constructions are the
persistence oracle; recorded as a pin-construction rule.

## 11. Phase I: input, history, and streaming

### I1. Source-lifetime byte cursor **[BOLD]**

`InputCursor` belongs to the I/O resource layer and is keyed by an owned open-file-description identity — the
kernel object that carries the shared offset — never by an individual fd binding. Duplicating an fd
(`exec 3<&0`) shares the existing cursor; opening or rebinding creates a new one; closing one binding decrements
ownership and invalidates nothing while another binding remains. `read`, `mapfile`, and script input borrow the
cursor; it owns raw pushback, decoder state, decoded queue, record state, and EOF across builtin calls. This is
the same open-description ownership rule R1 applies to here-input content; the two packages share one identity
type. Descriptions inherited from outside the shell with unknowable aliases are a documented deliberate-loss
entry, not silent behavior.

Runtime shell data uses bytes plus UTF-8 `surrogateescape`; malformed bytes round-trip. Replacement decoding is
limited to explicitly lossy terminal display. The never-over-read discipline (record reads on unseekable sources,
seek-back on seekable ones) remains the primary contract; a replaying fd view for handing buffered bytes to an
external child is built only if a probed case survives that discipline's design review.

**Amended 2026-07-19 (I1 rulings):** (1) the "same identity type R1 applies to here-input" premise was FALSE —
R1 shipped here-input sharing behaviorally (F_DUPFD shared kernel offset) with no identity type; I1 CREATES the
owned-description identity type, designed for R1's later adoption. (2) The surrogateescape model is the clean
hybrid the section text prescribes; bash's UTF-8-locale mbrtowc quirks (incomplete-lead delimiter swallowing,
`read -N` over-read on trailing incomplete lead) are libc/platform-dependent and are documented deliberate
divergences pinned against the psh model (C-locale bash expected to match; recorded per row). (3) Ownership
depth is SCOPED: same-fd cursor persistence keyed by the identity type; dup-cross-fd and temp-redirect decoder
carryover are recorded with discriminating probes — under strict never-over-read bash itself carries NO
cross-call decoder state (the kernel offset is the complete shared state in both shells), so those entries are
parity-via-different-mechanism, not loss; FULL weaving through R1's save-restore paths is declined as risk
without an oracle. The registry keying must keep FULL purely additive (guarded).

Guards use deterministic chunk sources plus end-to-end pipes: malformed lead before ASCII/newline, every UTF-8
split point, `read -> read`, `read -> mapfile`, builtin -> external, fd rebinding, and alternating reads through
dup aliases (`read <&0` vs `read <&3` after `exec 3<&0`) with chunk splits and malformed bytes.

### I2. Lazy `ProgramSource` for scripts **[BOLD]**

Script files and FIFOs are consumed on demand. The script descriptor is relocated to a high CLOEXEC fd and owned
by the source/activation lifecycle so user redirects cannot clobber it. The producer-waits-for-first-side-effect
FIFO case must pass, and memory use is bounded independently of file size.

### I3. Resumable completeness and parsing **[BOLD]**

`ParserDriver.start_session(inputs)` returns an incremental session whose `feed(bytes)` lexes only new input and
advances persistent grammar state. It returns the same `Complete | Incomplete | Invalid` outcome as one-shot
parsing. Heredoc queue state and open expansion markers are inputs to that session, not separate regex or
whole-buffer oracles.

Both selectable parser implementations must honor the session contract for interactive/script accumulation, or a
parser must be explicitly unavailable for that mode. A one-shot adapter that reparses the growing buffer is not a
completion. Operation-count tests prove linear work over multiline and heredoc-heavy input; timing is secondary.
**Amended 2026-07-19 (I3 post-build rulings):** (a) multi-command linearity is realized by
RESET-PER-COMMAND (prior commands never re-lexed) rather than carried `LexicalState` — SANCTIONED: the
condition's intent was the pinned LINEAR property, which holds; carrying state adds nothing in the
one-command-at-a-time model and threading `initial_context` through the lexer entry points grazes the S1
fence (recorded as the mechanism if a future slot needs cross-command lexer state). (b) A NEW pre-existing
divergence found during PTY probing: a trailing redirect operator at EOF inside an open construct
(`if true; then` + `echo <`) — psh classifies Incomplete (awaits target), bash errors immediately; probed,
documented, added to the post-campaign carry register (completeness-classification family).
**Amended 2026-07-19 (I3 ruling — stop-and-report, Option A sanctioned):** dev spike proved a fundamental
incompatibility: bash reports mid-construct syntax errors IMMEDIATELY (PTY-proven: `if true; then echo )` errors
at that line, not at `fi`), which REQUIRES parsing each feed; linear single-open-construct completeness requires
NOT parsing each feed; only a resumable parser gets both, and psh's RD (unlike bash's yacc machine) is not
resumable — nor is the whole-string lexer mid-construct (the S1 fence). SANCTIONED REALIZATION: a genuine typed
session (ONE completeness engine; heredoc-queue state O(1)/line; LexicalState carried across complete-command
boundaries; both-parser outcome-class parity after the S4 divergence closed as I3 work-item 1) with op-count
LINEARITY PINS for the linear families, a doubling-ratio CHARACTERIZATION pin documenting the single-open-
construct O(k²) residual with its oracle-derived rationale, and bash-immediate-error PARITY pins locking the
behavior that forces the residual. #20 H15 is reclassified PARTIALLY CLOSED — full closure requires a
resumable-lexer/parser campaign, recorded on the post-campaign register (Option B); deliberate bash divergence
(Option C) was rejected on oracle supremacy.

### I4. Typed history expansion

The quote-aware scanner and resolver return `HistoryExpansionResult`. Recording and diagnostics consume that
result, not a regex and not `expanded_text != original_text`. A syntactically live reference can fail, print only,
or expand to identical text; those remain distinct outcomes.

History activation consumes F1's interactive-family and `histexpand` state, never `is_script_mode`. `-ic`,
`set +/-H`, `!0`, quick substitution, print-only modifiers, and quoted suppression are pinned. History files use
explicit UTF-8 plus `surrogateescape` for startup, save, append, read-new, and rewrite paths.
**Amended 2026-07-19 (I4 rulings):** (1) the `:p` modifier's output stream moves stdout→STDERR — SANCTIONED
CONDITIONALLY on verification's PTY re-derivation of the bash stream fact (bash parity outranks psh's
historical stdout convention; the integrator's own -ic probe construction was inconclusive and is recorded as
such); `history -p` (the builtin) stays stdout per bash, wired as the declared second typed-result consumer
with force=True bypassing `set +H`. (2) The two heredoc-body corpus goldens pinning the old expansion bug were
regenerated bash-verified. (3) The heredoc history-dump trailing-newline residual is verified pre-existing and
history-independent — carried (cmdhist/line-editor territory).

## 12. Phase J: jobs, signals, and shutdown

### J1. One job lifecycle **[BOLD]**

`AsyncJobPolicy(stdin_policy, int_quit_policy)` is computed once from background status and monitor/job-control
mode, then passed to every member. Non-monitor asynchronous jobs and interactive job-control process groups do not
share an unconditional signal disposition.

Commands, pipelines, and foreground subshells run through `ForegroundJobSession`, which owns registration,
process-group setup, terminal transfer/capture/restore, waiting, signal-death reporting, current-job rotation, and
exception cleanup.

Job-table visibility, HUP policy, and child-reap ownership are separate facts. `Job.no_hup` is honored by the one
`Shell.shutdown(reason)` path, while a disowned child remains in the reap registry until collected. `wait` tests the
returned pid separately from status.

The acceptance matrix covers monitor on/off, single command/pipeline, INT/QUIT, explicit stdin, stop/continue,
terminal modes, every shutdown route, disown-then-zombie-while-shell-lives, and login/interactive HUP behavior.

**Amended 2026-07-20 (J1 rulings):** (1) Login-gate narrowing SANCTIONED as a documented deliberate
divergence: psh has no login-shell concept, so the `huponexit` exit-HUP gate is `interactive + huponexit`
(every psh interactive shell is login-like for this option). Conditions: a documented-differences entry plus a
pin recording the psh model; claims must never state bash parity for the interactive NON-login row (bash would
not HUP there); no login-shell flag lands in J1; the underlying bash login-only fact is conditioned on
verification's re-derivation from the archived probe transcripts. (2) The prompt-reap residual is ACCEPTED as
a declared handoff: typed reap/job-table separation, `disown -h`/`no_hup`, and shutdown-time collection ship
in J1; the general signal-safe SIGCHLD reaper for transient zombies while the shell lives goes to the
POST-CAMPAIGN CARRY REGISTER (risk: stealing command-substitution statuses). H19 is therefore PARTIALLY
closed and all claims (ledger header, subsystem docs) must say so explicitly. (3) Received-SIGHUP fan-out —
FINAL RULING 2026-07-20 (third state; supersedes both the original ruling and the same-day reversal). The
fact proved CONSTRUCTION-DEPENDENT: in python-pty-family constructions (dev's trap harness, integrator's
pty.fork probe with disposition/mask resets, verifier's pexpect replication) interactive bash 5.2.26 neither
exits nor fans out on programmatic `kill -HUP`; in the verifier's tmux-hosted realistic-terminal
construction bash EXITS AND FANS OUT, 3/3 trials, matching the manual. The reversal's premise ("refuted by
two independent constructions") was unsound — both constructions sat in the same family; the tmux result is
the realistic-terminal oracle and the manual is on its side. RULING: psh IMPLEMENTS the manual-conformant
model — an interactive shell receiving untrapped SIGHUP resends HUP to jobs (SIGCONT first to stopped ones,
`Job.no_hup` honored) and exits through THE shutdown path, with the shutdown reason distinguishing
hangup (unconditional fan-out) from normal exit (interactive+huponexit gate). Non-interactive receipt stays
no-fan-out (all constructions agree). The former "kill-HUP parity" pin is REWRITTEN to pin the fan-out
model. The python-pty anomaly is recorded as a probe-construction caveat (with pointers to all three probe
sets), NOT as a parity fact. The disconnect-fan-out carry is expected to COLLAPSE (a real disconnect
delivers SIGHUP to the session leader, landing on the new path) — the dev must re-probe disconnect after
implementing and close or restate that carry. Ledger must record the full three-state ruling history, the
F3-class lesson (both the integrator's citation-first ruling AND the probe-family blindness), and the
Linux-nightly watch item.

## 13. Phase Q: dependency direction and drift prevention

### Q1. Narrow runtime protocols

After the canonical values stabilize, touched components accept `VariableAccess`, `ExpansionContext`, `IOContext`,
`JobRuntime`, and `LocaleContext` protocols rather than the complete `Shell`. The campaign does not attempt a
single-shot rewrite of every package dependency, but no migrated boundary may retain a broad service-locator
parameter when its actual needs fit a protocol.

A constructor/import ratchet records the remaining full-`Shell` consumers and can only shrink. Protocol modules
must not import their implementations.

### Q2. Cross-cutting ratchets

Land tree-wide ratchets only after semantic repairs, sequentially:

- option walkers versus justified hand-written parsers;
- `getattr`/`hasattr` on declared fields;
- broad `ValueError`/`TypeError` catches used as expected control flow;
- command-registry reads outside resolution;
- redirect target/flag re-derivation;
- Bash-oracle bypasses;
- syntax-bearing raw AST fields;
- visitor recursion outside `walk_ast`;
- incomplete public signatures in migrated packages.

Every allowlist is justified, shrinking, and tested with a synthetic offender.

### Q3. Documentation and dead surfaces

Architecture diagrams and subsystem guides are updated when each old representation is deleted, not in one stale
cleanup at the end. Executable documentation fences are opt-in and language-tagged; diagrams and pseudocode are
not forced through source checks.

"Test-only" is not synonymous with dead. Deletion checks exports, `__all__`, documented imports, entry points,
reflection, serialization, and dynamic dispatch. Public APIs are deprecated or intentionally broken with release
notes; absence of an internal caller is insufficient.

## 14. Dependency-driven merge train

This table states semantic dependencies, not optimistic filename disjointness. Parallel work is allowed only after
the integrator inventories actual files and shared tests at the launch SHA.

| Train | Work | Required predecessor |
| --- | --- | --- |
| 0 | E1 with E4 attestation, then integrated E2/E3 | none; E2/E3 share harness environment ownership |
| 1 | F1 invocation, then F3 source service contract | Phase E |
| 2 | F2 process owner and pure lifecycle | F1 |
| 3 | S1 lexical words, then S2 heredoc transaction | F3 |
| 4 | S3 structured templates, then S4 parser-call contract | S1/S2 |
| 5 | S5 pipeline component and `walk_ast` | S3/S4 |
| 6 | W1 field IR, then W2 subscript authority | S3 |
| 7 | W3 matcher; R2 variable truth | W1; S3 respectively |
| 8 | R1 redirects, then R3 command resolution | F2/S2; R2 respectively |
| 9 | I1 byte cursor, then I2 lazy source | R1/F2; F3/I1 |
| 10 | I3 resumable parser; I4 history | S2-S4/I2; F1/I1 |
| 11 | J1 jobs/signals/shutdown | F2/R1/R3 |
| 12 | Q1 protocols, then Q2 ratchets and Q3 final docs | all semantic packages |
| 13 | closing verification | all work |

Contract producers land before consumers. In particular: heredoc ownership precedes parser-context cleanup;
invocation semantics precede history; field protection precedes the pattern compiler; variable truth precedes
command resolution; process ownership and redirection precede jobs; tree-wide ratchets run after repairs.

## 15. Campaign exit criteria

The campaign is complete only when all of the following are true at one final SHA:

1. C1 remains pinned, and H1-H19 each have a Bash-pinned behavioral test with no strict xfail or deferral.
2. Every canonical type in section 5 has one named producer, a complete consumer inventory, and no second semantic
   implementation outside a justified terminal adapter.
3. No expansion-bearing parameter operand, subscript, arithmetic expression, or loop clause is represented only by
   an untyped semantic string.
4. No word is flattened before field splitting and pattern compilation; no runtime shell byte is irreversibly
   replacement-decoded.
5. Shell construction is process-pure, and all process-global mutations require the active owner token.
6. `walk_ast` is exhaustive and is the only structural traversal used by production visitors.
7. The standard gate, live Bash comparison, conformance suite, ruff, and mypy meet the Phase-E exit at the final
   SHA; deterministic complexity guards pass and nightly benchmark deltas are recorded; release tagging is
   attestation-gated per E4.
8. A fresh adversarial verifier re-runs every closure probe, tests at least one composed case per package, and
   attacks a claimed strength rather than only the original defect.
9. Architecture and subsystem documentation name the final representations and dependency direction; superseded
   comments and compatibility adapters are gone or have explicit owners and removal dates.

The closing report contains the final boundary ledger, probe transcripts, exact commands, final SHA, representation
and consumer census, deliberate-loss registry, benchmark comparison, and any public API changes. It is committed
to `docs/reviews/` — working ledgers in `tmp/` are scaffolding; the committed pins, manifests, and this report are
the durable evidence.

## 16. Explicit non-goals

- Simultaneous active shells sharing one Python process are not supported. The coordinator enforces this rather
  than leaving behavior undefined.
- The mechanical fd and Python-stream redirect adapters may remain separate; their semantic program, ordering,
  modes, ownership, and errors may not diverge.
- Legacy backticks are not forced into modern command-substitution timing when Bash differs; their typed deferred
  policy is deliberate and pinned.
- Escape dialects with genuinely different grammars are not unified merely to reduce line count.
- Full combinator-parser productionization and a whole-repository SCC rewrite are not prerequisites. Honest parser
  outcomes, context handling, laws, and narrow protocols at migrated boundaries are prerequisites.
- Terminal grapheme/cell rendering is a separate UI model campaign. This campaign touches terminal decoding only
  where required for lossless input ownership.
