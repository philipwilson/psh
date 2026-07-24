# Ground-Up Reappraisal #22: Correctness and Textbook Quality at v0.749.0

- **Date:** 2026-07-20
- **Audited release:** PSH 0.749.0, tag commit `31aab012`; release attestation gates
  `f0aeda29`. The audit used a clean detached checkout of that tag.
- **Campaign under review:**
  [`boundary_campaign_briefs_2026-07-16.md`](boundary_campaign_briefs_2026-07-16.md),
  implemented across v0.725.0-v0.749.0.
- **Scope:** all production subsystems, their cross-subsystem contracts, tests,
  tooling, documentation, release evidence, and the campaign's own exit criteria.
- **Method:** independent syntax/expansion, execution/I/O, and core/contract
  audits; root-level integration review; static inventories; focused and broad
  test runs; fault injection; complexity measurements; PTY probes; and fresh
  differential probes against GNU Bash 5.2.26. Findings below are based on the
  tagged tree, not on archived campaign transcripts.

> **Snapshot caveat.** The ordinary working tree was still at v0.748.0 and
> contained unrelated uncommitted review files, so the tagged production tree
> was reviewed in a clean v0.749.0 checkout. Most validation also ran there; the
> table below explicitly labels two focused v0.748.0 runs whose relevant code
> was unchanged after review of the v0.749.0 diff. The campaign brief itself is
> not in the v0.749.0 tag; it exists only in the review working tree.

---

## Verdict

**Overall: B-. Correctness B-; elegance B; clarity B-; efficiency B-.**

The campaign was a substantial and worthwhile architectural advance. It added
real semantic representations rather than a layer of compatibility switches:
`LexedUnit`, `SyntaxTemplate`, `ExpandedField`, `RedirectProgram`,
`ResolvedCommand`, `VariableLookup`, `InputCursor`, `ParseInputs`, typed parse
outcomes, lifecycle leases, and structured shell-oracle outcomes. Several of
those boundaries are already good enough to teach: fusion-first keyword
lexing, ordered redirect IR, one fork policy, lazy program sourcing, invocation
parsing before shell construction, and phase-manifest-based gate accounting.

**The completed work is not satisfactory as a closed campaign under the
campaign's own contract.** It is satisfactory as a major intermediate release.
The distinction matters. The plan requires lossless boundaries, one authority,
exhaustive consumers, executable guards, all H1-H19 closed, final-SHA evidence,
and a self-contained closing record. Fresh probes found live losses in every
major semantic layer, including false-green differential tests, false-negative
security traversal, command dispatch decided before assignment side effects,
field flattening, process-substitution reinterpretation, and incomplete
lifecycle rollback. The close report itself marks H15 and H19 partial, while
the brief admits no partial state at exit.

The dominant diagnosis from #20 therefore still holds:

> Semantic information is now preserved at more boundaries, but several new
> canonical types are shallow, mutable, bypassable, or introduced before all
> consumers have migrated. The remaining defects are mostly authority-timing,
> traversal-totality, and lifetime-ownership failures.

### Grade summary

| Area | Correctness | Elegance | Clarity | Efficiency | Assessment |
|---|---:|---:|---:|---:|---|
| Lexer and lexical transactions | B+ | A- | A- | A- | Fusion-first work is strong; interactive heredoc detection still has a divergent raw-text grammar. |
| AST and recursive-descent parser | B- | B | B | B- | Typed outcomes and templates help, but executable AST invalid states, raw extent scans, retained parser state, and O(k^2) sessions remain. |
| Combinator parser | C+ | C+ | B- | B | It silently drops `ParseInputs` and context in nested paths, so its claimed parity boundary is not real. |
| Expansion and patterns | C+ | B- | B | C+ | One subscript service and pattern AST are good moves; field identity, procsub timing, extglob semantics, cache immutability, and all-start complexity are unresolved. |
| Executor and command resolution | B- | B+ | B+ | B+ | Typed resolution is valuable, but resolution occurs before prefix-value side effects establish the authoritative option state. |
| I/O redirection | B+ | A- | B+ | A- | `RedirectProgram` and fd-remap ownership are strong; failed permanent acquisition still has a lease rollback edge. |
| Core variables and process state | C+ | B- | B | B | Tri-state lookup and activation ownership are sound ideas; their read and rollback surfaces are not actually immutable/transactional. |
| Builtins | B | B | B+ | B | Broadly modular and well tested; input decoding, history cursors, `history -s`, and float formatting have confirmed gaps. |
| Scripting, invocation, and input | B- | B | B | C+ | Source execution and invocation are good; analysis uses stale option state and `ParseSession` retains quadratic and duplicate-grammar paths. |
| Interactive, signals, and jobs | B- | B | B | B | Foreground transactions improved; EXIT-trap control flow, managed-signal restoration, and general reaping are incomplete. |
| Visitors and analysis tools | C | C+ | B- | B | Shared helpers exist, but recursion remains visitor-owned and demonstrably misses executable syntax. |
| Protocols and dependency direction | C+ | C+ | B | B | Useful scaffolding; only two boundaries migrated, broad owner types and `Any` still cross the new interfaces. |
| Tests, tooling, and release evidence | C+ | B | B- | B | Scale and structured manifests are excellent; the supposedly universal oracle is bypassed and can certify two killed writers as identical. |
| Documentation | C+ | B | C | A | Rich rationale, but the shipped close record is incomplete and overstates several closures. |

---

## Ranked findings

### HIGH-1 - The differential oracle can certify two harness failures as identical

**Boundary:** E2, test infrastructure, release evidence.

**Evidence:** `tests/harness/shell_oracle.py:291-338`,
`tests/conformance/conformance_framework.py:202-236`,
`tests/unit/tooling/test_shell_oracle_harness.py:87-97`.

An output-cap breach kills the process group, but `run_shell_case` returns
`Completed` with a negative signal status and truncation flags. The conformance
adapter treats every `Completed` as behavior and discards those flags. Two
runaway commands that emit the same prefix are therefore classified as
`IDENTICAL`.

Fresh discriminator:

```text
ConformanceTestFramework().compare_behavior("yes", timeout=5)
  conformance = IDENTICAL
  psh  = rc -9, stdout bytes 8,388,608, truncated
  bash = rc -9, stdout bytes 8,388,608, truncated
```

The unit test explicitly requires the cap-killed run to be `Completed`, so
this is specified behavior rather than an incidental branch.

The second half of E2 is also false. Thirty-three Python modules under
`tests/conformance/` call `subprocess.run` or `Popen` directly; thirty are Bash
differential callers that resolve Bash and then bypass `run_shell_case`.
Examples include
`tests/conformance/bash/test_bad_substitution_conformance.py:30` and the
nounset, heredoc, history, option, and syntax timing suites. The guard in
`tests/unit/tooling/test_bash_oracle_resolution.py:119-180` checks *resolution*
of the Bash binary, not execution through the runner; its accepted-use fixture
at `:228-235` blesses exactly `subprocess.run([resolve_bash().path, ...])`.

**Impact:** differential results can be false green, and direct callers lose
the central timeout, output cap, temporary cwd, process-group cleanup, typed
failure, and provenance policy. This invalidates the campaign's "all Bash and
PSH differential execution" claim.

**Fix:** make output-cap termination a distinct `OutputLimitExceeded` failure;
reject truncation before comparison; expose only a higher-level comparison API
to conformance tests; and add an AST guard that rejects direct process creation
in every oracle-bearing module. Migrate the live census before deleting the
allowlist.

### HIGH-2 - The exhaustive security traversal still omits executable syntax

**Boundary:** S5, AST/visitor.

**Evidence:** `psh/visitor/security_visitor.py:89-92,166-170,209-274`,
`psh/visitor/traversal.py:177-199`,
`tests/unit/visitor/test_ast_coverage_matrix.py:227`.

`SecurityVisitor.visit_SimpleCommand` returns immediately when `args` is
empty, before visiting redirects. Shared word traversal inspects only direct
`Word` children and excludes backtick/template substitution bodies. Custom
loop and case visitors bypass subject words as well.

These commands all report `No security issues found!`:

```sh
>/etc/passwd
echo >$(rm -rf /tmp/psh-never-created)
for x in "$(rm -rf /tmp/psh-never-created)"; do :; done
case "$(rm -rf /tmp/psh-never-created)" in x) :;; esac
```

Direct `echo $(rm -rf ...)` is detected. The matrix uses `echo x
>/etc/passwd`, so it never exercises the redirect-only node shape.

The amended S5 brief sanctions not descending into `SyntaxTemplate.subs`.
That exception does not rescue S5: redirect targets and loop/case subject words
are registered AST children, yet visitor-owned recursion still skips them. The
template exception separately conflicts with the campaign-wide exhaustive
analysis and traversal-authority goals.

**Impact:** the analysis mode makes a positive safety claim after skipping
executable regions. The schema-declared `walk_ast` iterator still exists; the
counterexamples disprove total production-visitor coverage and S5's
consumer-migration claim.

**Fix:** make child enumeration framework-owned and total. Every semantic AST
field, every `SyntaxTemplate.subs` element, and every redirect target must be
enumerated by one traversal protocol. Generate sentinel-node tests for every
child field and run every production visitor over them.

### HIGH-3 - Command dispatch is resolved before prefix expansion establishes option state

**Boundary:** R3/H10, executor/core.

**Evidence:** `psh/executor/command.py:480-509`,
`psh/executor/command_assignments.py:187-207`,
`psh/executor/command_resolution.py:230-263`.

The executor constructs a name-only overlay and resolves the command before it
expands prefix-assignment values. Those values can mutate shell state. In
particular, arithmetic and parameter-assignment side effects can enable POSIX
mode, which changes special-builtin/function precedence.

```sh
eval(){ echo FN; }
unset POSIXLY_CORRECT
A=$((POSIXLY_CORRECT=1)) eval "echo BUILTIN"
```

Bash 5.2 prints `BUILTIN`; PSH prints `FN`. Replacing the arithmetic expression
with `${POSIXLY_CORRECT:=1}` gives the same split.

**Impact:** the typed `ResolvedCommand` is computed once, but at the wrong
authority time. Scope selection, assignment persistence, and dispatch then
consistently execute the wrong answer. H10 is not closed.

**Fix:** transactionally expand prefix values left to right into an isolated
command environment, commit their permitted shell side effects, then resolve
once against the resulting authoritative option state. Resolution must remain
single-shot; its input must become complete.

### HIGH-4 - Subscript parsing loses process-substitution identity and timing

**Boundary:** S3/W2.

**Evidence:**
`psh/parser/recursive_descent/support/syntax_templates.py:220-237`,
`psh/expansion/subscript.py:101-151,154-172`,
`tests/conformance/bash/test_subscript_keying_conformance.py:540-568`.

Every `SubscriptSpec` is initially built with `allow_procsub=False`, before the
array kind is known. The associative path later re-lexes raw text and performs
ordinary assignment-word expansion, turning syntax that Bash preserves as an
associative key into an executing process substitution.

Fresh direct probe:

```sh
declare -A a; a[<(printf x)]=v; declare -p a
```

Bash stores the literal key `<(printf x)`; PSH stores a `/dev/fd/...` pathname.
For `declare -A a; echo before; a[<(if)]=x; echo after`, Bash rejects the
complete `-c` unit before execution, while both PSH parsers print `before` and
`after` and return 0. The cited conformance test records the latter invalid
process-substitution timing divergence; it does not cover the valid literal-key
probe.

**Impact:** syntax timing and key identity are lost exactly at the new typed
boundary. This is not a small compatibility edge: source spelling is executed
after the authority needed to interpret it has changed.

**Fix:** represent process-substitution syntax in `SubscriptSpec` without
deciding its meaning. After target-kind resolution, preserve literal spelling
and quote removal for associative keys and apply arithmetic semantics only to
indexed subscripts. Delete the catch-all raw-string fallback.

### HIGH-5 - The combinator facade accepts `ParseInputs` and then drops it

**Boundary:** S4, parser parity.

**Evidence:** `psh/parser/__init__.py:140-153`,
`psh/parser/combinators/arrays.py:246-254`.

The public combinator factory accepts `source_text`, `line_offset`, and
`lexer_options`; its wrapper calls only `self._parser.parse(self.tokens)`.
Array element assignment separately passes `ctx=None`. Consequences verified
at v0.749.0:

- after `shopt -s extglob`, nested `@(a|b)` inside `$()` parses in Bash and RD
  but is rejected by the combinator;
- the heredoc-aware path preserves lexer options for ordinary expansion paths,
  but still loses source context and array-assignment context;
- a nested multiline syntax error is reported on line 5 by RD and line 4 by
  the combinator.

**Impact:** the public signature promises a typed context that consumers do not
receive. Parser lockstep tests cannot establish parity where context is absent.

**Fix:** give both parsers one `parse(tokens, inputs)` entry point and carry the
same immutable input snapshot through every nested combinator and depth-budget
path. Delete overloads that cannot honor the contract.

### HIGH-6 - W1 still flattens `$@` fields inside parameter-operator operands

**Boundary:** W1/H5, expansion.

**Evidence:** `psh/expansion/operands.py:49-64`,
`psh/expansion/word_expander.py:490-541`,
`tests/conformance/bash/test_subscript_keying_conformance.py:571-587`.

`OperandResult` carries one string plus protected text runs. It cannot encode
field boundaries. The walker can reconstruct quote/protection runs but cannot
recover the multiple fields produced by `"$@"`.

```sh
unset x; set -- a b; printf '<%s>' "${x:-"$@"}"
```

Bash prints `<a><b>`; PSH prints `<a b>`. A conformance test currently pins the
PSH result instead of treating the difference as failure.

**Impact:** the campaign's field-preserving expansion target and H5 closure
claim are false. Downstream split/glob policy cannot restore information that
the operand boundary discarded.

**Fix:** carry `ExpandedField` boundaries in the operand IR. Make scalar
projection an explicit terminal operation used only by consumers whose shell
semantics demand one string.

### HIGH-7 - The pattern engine is neither semantically complete nor linear for key relations

**Boundary:** W3/H7, expansion/efficiency.

**Evidence:** `psh/expansion/pattern_engine.py:517-539,639-675`,
`psh/expansion/parameter_expansion.py:107-149,200-212`,
`tests/unit/expansion/test_pattern_engine_differential.py:98-110,177-195`.

The engine has two related sequence defects: nullable extglobs compose
incorrectly beside wildcards, and `!(...)` is implemented as a local span
complement even though Bash negation is continuation-sensitive. Fresh matches
returned these statuses:

| Probe | Bash | PSH |
|---|---:|---:|
| `[[ "" == *@(a|*) ]]` | 1 | 0 |
| `[[ a == *!(a) ]]` | 1 | 0 |
| `[[ "" == *!(*) ]]` | 0 | 1 |

The negation error propagates into `case`, `${v##pattern}`, and substitution.
The exact three `[[` rows above are absent from the differential matrix; four
related empty-subject substitution rows are explicitly excluded at the cited
test locations.

Separately, `matching_starts` and the global-substitution spanner rerun the
relation from every subject position. On the no-match pattern `*b` over
`"a" * N`, measured `matching_starts` times were 0.006, 0.027, 0.099, 0.466,
and 2.02 seconds for N=500, 1k, 2k, 4k, and 8k. The scaling is quadratic and
contradicts the module's O(nodes x positions) narrative.

**Fix:** make negation continuation-aware and compute an all-start relation in
one reverse DP/NFA-style pass. Add generated finite-alphabet differential tests
for nullable extglobs adjacent to `*`, across every consumer, plus deterministic
transition-count scaling assertions for suffix removal and global substitution.

### HIGH-8 - F2's lifecycle transaction does not roll back component acquisition

**Boundary:** F2/H18, core/process-global state.

**Evidence:** `psh/core/state.py:449-505`,
`psh/core/process_lease.py:239-265,314-330,384-415`.

Locale activation appends a `LOCALE` component lease and then calls
`ensure_applied`. If application fails, `activate` rolls back the activation
stack and owner but not the newly appended component. Fault injection left
`owner=None`, activation depth 0, one live component, and no restore call.
Moreover, force release clears ownership and components after a restore raises,
so the process can be left mutated with no remaining owner capable of repair.

**Impact:** construction purity is improved, but the stronger "partial
acquisition rolled back completely" contract is false. Embedded use can leak
libc/process state after an exceptional activation.

**Fix:** checkpoint component depth at transaction entry and restore every
newly acquired component before owner rollback. Attempt all restores and
surface an aggregate internal failure; if restoration cannot be established,
retain or quarantine ownership rather than representing the process as clean.

### HIGH-9 - Substitution syntax errors carry origin but lose fatal-frame semantics

**Boundary:** I3, parser/scripting.

**Evidence:** `psh/parser/recursive_descent/helpers.py:225-239`,
`psh/scripting/source_processor.py:379-386`.

`SubstitutionSyntaxError` records that a parse failure originated inside a
modern command/process substitution and its producer documentation says the
consumer must map that fact to fatal frame termination with status 127. The
source processor catches the base `ParseError`, ignores `substitution_origin`,
and uniformly returns 2.

```text
                         Bash 5.2                 PSH
echo $(if)               rc 127, no execution     rc 2
eval 'echo $(if)'; echo AFTER
                         rc 127, frame abort       prints AFTER, rc 0
```

**Impact:** the new typed fact reaches its consumer and is discarded. In
`eval` and sourced/string-execution frames, commands after a read-time fatal
syntax error can run. The close report discloses this as a deliberate current
behavior, but disclosure does not complete the producer/consumer contract.

**Fix:** handle `SubstitutionSyntaxError` before generic `ParseError`; map it
through an explicit source-frame outcome that aborts `-c`, `eval`, and source
at the correct level with 127. Pin top-level, nested, dead-branch, and
already-executed-prefix timing against Bash.

### HIGH-10 - The campaign's closure artifact fails its own exit criteria

**Boundary:** Q3/documentation/release.

**Evidence:** campaign brief sections 3, 13, and 15; tagged
`docs/reviews/boundary_campaign_close_2026-07.md:5-24,138-195,231-267`;
`gate_attestation.json`.

The implementation close report is candid in several places, but its headline
closure does not meet the operating brief:

1. The brief requires C1/H1-H19 closed without deferral. The close table marks
   H15 and H19 `PARTIAL` and carries both into future work.
2. The brief requires standard gate, live Bash comparison, conformance,
   deterministic complexity, nightly deltas, and final-SHA verification. The
   close report says `--compare-bash` was **not** rerun there, records the gate
   at a pre-report SHA, leaves the Linux-nightly obligation open, and provides
   no benchmark comparison.
3. The durable close report points its ledgers and probe transcripts at
   `tmp/boundary-ledgers/`; that directory is absent from the tag.
4. The report links the operating brief, but the brief is absent from the tag.
   The report itself still says `PR: TBD`.
5. Fresh probes directly falsify E2's universal invariant and the H5, H7, and
   H10 closure claims. S3-S5 and R2 also violate broader work-package and exit
   invariants, even where an original H-pin or amended residue statement is
   narrower.
6. The brief in the working tree still says "implementation has not started",
   contradicting the shipped state. This appraisal's index update corrects the
   index description, not the underlying brief.
7. The carry registry reverses the empty-arithmetic-subscript divergence: it
   says PSH warns and continues, while the pinned test at
   `tests/conformance/bash/test_subscript_keying_conformance.py:508-516` and a
   fresh probe show Bash warning/continuing with status 0 and PSH aborting the
   line with status 1. It also omits the process-substitution timing carry and
   the W3 nullable-extglob divergences found above.

The committed release attestation is useful and internally structured: it
records 19,298 parallel and 892 serial passes, 1,590 skips, 10 xfails, Ruff
clean, and mypy over 274 files at gated commit `f0aeda29`. It does not supply
the missing campaign-specific evidence above.

**Impact:** a reader cannot reproduce the campaign's closure from the tagged
artifact, and "completed" means something weaker than the plan defined.

**Fix:** reclassify v0.749.0 as the campaign's implementation milestone, not
its closure. Commit the governing brief and durable evidence, correct the
carry registry, rerun every required command at one tree, attach benchmark
deltas, and issue a closure addendum only after the findings in the P0/P1 plan
below are either fixed or explicitly removed from a revised scope before work
begins.

---

## Medium findings

### MEDIUM-1 - EXIT-trap control flow bypasses mandatory shutdown work

`psh/shell.py:452-485` executes the EXIT trap before history persistence and
job disposition. `trap 'exit 7' EXIT` raises `SystemExit`; the `finally` calls
`close`, but history save, `hangup_jobs`, and `reap_detached` are skipped. A
PTY probe with `huponexit` left the background child alive, while a Bash login
shell hung it up. Make job disposition and other mandatory cleanup independent
finally phases; define explicitly which status wins when the trap exits.

### MEDIUM-2 - A valid UTF-8 character split across cursor and bulk drain is corrupted

`psh/builtins/input_reader.py:181-216` finalizes the incremental decoder with
empty input, then decodes the remaining bytes with a fresh decoder. Splitting
UTF-8 `C3 A9` at that seam yields two surrogate characters rather than `e` with
acute, although byte round-trip happens to survive. Feed the tail through the
existing decoder with `final=True`; pin both character identity and byte
round-trip for every split of 2-, 3-, and 4-byte sequences.

### MEDIUM-3 - Interactive heredoc completeness still uses a second regex grammar

`psh/parser/session.py:65-69,296-307` seeds pending heredocs from
`psh/utils/heredoc_detection.py:549-590` before invoking the real lexer.
`ParseSession.feed("echo \\<<EOF")` incorrectly returns an incomplete
`SessionStep` with a `HEREDOC` hint for `EOF`; the lexer sees escaped `<` plus
ordinary input redirection and Bash considers the line complete. This changes streaming
execution timing: the session consumes later physical lines as a nonexistent
heredoc body and can block indefinitely on an interactive or FIFO-backed input.
Derive pending heredocs from canonical lexer events and property-test
lexer/session equivalence over escaped, quoted, and adjacent operator spellings.

### MEDIUM-4 - Parser extent and location logic is still raw-text based

`psh/parser/recursive_descent/support/word_builder.py:213-246` counts raw square
brackets inside quoted and nested content. Both parsers reject the valid Bash
case `declare -A a; a[']']=ok; echo "${a[$(printf ']')]}"`. Nested template
diagnostics also receive only the enclosing offset at
`psh/parser/recursive_descent/support/syntax_templates.py:67-82`, producing
wrong line numbers. Reuse one quote/expansion-aware extent scanner and attach
absolute source spans to nested substitutions.

### MEDIUM-5 - The tri-state lookup exposes mutable live state

`psh/core/variable_lookup.py:55-72,97-110` exposes writable slots and returns a
shared mutable `_MISSING`. `psh/core/scope.py:356-382` places the live mutable
`Variable` cell in `binding`. Mutating `lookup(name).binding.value` changes
subsequent shell reads but not the exported environment and bypasses readonly,
nameref, observer, and `VariableStore` rules; mutating `_MISSING` poisons every
future miss. Return a frozen lookup and immutable `VariableView`, or omit the
binding where no production consumer needs it.

### MEDIUM-6 - Cached pattern ASTs are mutable shared state

`psh/expansion/pattern_engine.py:69-136,216-220,263-285` caches AST nodes whose
attributes remain writable even though sequence/alternative collections are
tuples. Rebinding the root returned by `compile('a')` poisons later
compilations and can make `'a'` match `'b'`. Use frozen node dataclasses and
compute derived metadata eagerly or outside the cached node.

### MEDIUM-7 - History file and memory cursors are conflated

`psh/interactive/history_manager.py:232-335` defines `_file_read_len` as the
number of default-file lines already consumed, but `history -d` decrements it
when deleting an in-memory entry. After reading a file `A B C`, deleting entry
1, appending `D` externally, and running `history -n`, Bash adds `D`; PSH adds
`C D`, duplicating `C`. Keep the file cursor independent of memory indices.
`history -s` at `:246-252` also appends without applying the normal `HISTSIZE`
cap.

### MEDIUM-8 - Managed interactive signal dispositions outlive `SignalManager.close`

`psh/interactive/signal_manager.py:62-138` installs process-global handlers;
`:162-173` closes notifier fds but does not restore the handlers. A probe left
`SIGTERM` bound to a closed shell after `Shell.close()`. Put managed handlers
under the same activation/component lease model as trap-installed dispositions
and restore the exact prior handlers on release.

### MEDIUM-9 - Analysis parses the whole file under initial option state

`psh/scripting/visitor_modes.py:18-55` parses once before executing option
changes. A script that enables extglob on line 1 and uses `+(...)` on line 2
executes but fails `--validate`. `psh/invocation.py:85` retains multiple
analysis modes, while `psh/shell.py:90` collapses them to booleans and
`visitor_modes.py:152` silently chooses a fixed priority. Use an incremental,
state-aware analysis session and either compose modes explicitly or reject
conflicting modes at invocation parsing.

### MEDIUM-10 - The executable heredoc and lexed-unit types are only shallowly valid

`psh/ast_nodes/redirects.py:23-47` permits an executable heredoc with
`heredoc_content=None`; RD constructs it at
`psh/parser/recursive_descent/parsers/redirections.py:141`, and the combinator
falls back to it when an operator ID is missing at
`psh/parser/combinators/commands/redirections.py:94`. Execution discovers the
invalid state only in `psh/io_redirect/file_redirect.py:355`. Live
heredoc-aware parser paths reject missing IDs/bodies; the defect is that the
executable type and bare token-level/unit-test parsing can represent the
invalid state. Separate incomplete parse state from
`HeredocRedirect(body: str)`.

`LexedUnit.tokens` is a tuple and its heredoc map is read-only, but each frozen
`Token` transitively contains mutable `parts: List[TokenPart]`, and `TokenPart`
is mutable (`psh/lexer/heredoc_lexer.py:43-55`,
`psh/lexer/token_types.py:103-126`, `psh/lexer/token_parts.py:11-22`). Freeze
the complete lexical value graph.

### MEDIUM-11 - `ParseInputs` and the RD parser lifecycle are less immutable than documented

`psh/parser/parse_inputs.py:22-27` says a parser retains neither inputs nor
state after return. `psh/parser/recursive_descent/parser.py:32-48` permanently
owns its context; after one parse, the cursor is consumed and a second parse
returns an empty program. `ParseInputs.lexer_options` is caller-owned mutable
state at `parse_inputs.py:61`. Either document and enforce a single-use parser,
or make grammar objects reusable with an ephemeral per-call context; snapshot
options immutably.

### MEDIUM-12 - Broad exception nets still convert internal defects into user errors

`psh/expansion/subscript.py:101-151` catches any `Exception` during raw source
reparse and literalizes it. Injecting `RuntimeError` produced a literal
`'$(x)'`. `psh/expansion/arithmetic/evaluator.py:567-605` can relabel internal
`TypeError` as a user expansion error. The Q2 guard detects only selected
`ValueError`/`TypeError` shapes and intentionally freezes eight broad maskers in
`tests/unit/tooling/test_broad_valueerror_catch_q2.py:101-151`; it therefore
cannot establish the general "internal defects remain internal" claim. Carry
typed user-syntax failures and catch only those.

### MEDIUM-13 - The background-subshell integration test is race-dependent and can pass without testing

`tests/integration/subshells/test_subshell_basics.py:161-176` launches a
background command, has an empty "give it time" section, and immediately reads
the output file if it exists. If the file does not exist, the test performs no
content assertion and passes; if it exists but is still empty, it fails. It was
one of two failures in a fresh canonical run and passed immediately in
isolation. Wait through the shell's job API with a bounded deadline, then
assert file existence and exact content unconditionally.

### MEDIUM-14 - Q1 is scaffolding, not the promised narrow dependency boundary

`psh/protocols/__init__.py:53-67` explicitly says only `IOContext` and
`JobRuntime` migrated. `VariableAccess`, `ExpansionContext`, and
`LocaleContext` remain post-campaign. The former flattens tri-state lookup, the
second exposes `Any` sub-expanders, `JobRuntime` leaks `Optional[ShellState]`,
and locale callers still use ambient state. The six full-`Shell` consumers are
frozen in `tests/unit/tooling/test_shell_consumer_ratchet_q1.py:107-136` rather
than removed. Continue the migration with capability-sized methods and values;
do not call the boundary complete merely because the allowlist cannot grow.
The vocabulary also collides: lexer parse state at
`psh/lexer/expansion_parser.py:387` and the protocol at
`psh/protocols/__init__.py:119` are both named `ExpansionContext`, while
`psh/core/locale_service.py:90` and `psh/protocols/__init__.py:216` define
different `LocaleContext` types. Core locale code at
`psh/core/locale_service.py:565-594` lazily imports a private table from
`psh/expansion/glob.py`, which imports core in return. Rename protocols to
capability nouns and move shared POSIX tables to a neutral owner.

### MEDIUM-15 - Complexity and module size remain concentrated

The production tree has 274 Python files and about 76,960 lines, but 54
functions are at least 100 lines. The largest include
`ShellState.__init__` (303 lines), `CommandExecutor._run_command` (211),
`PipelineExecutor._execute_pipeline` (200), history expansion (194), and
`ReadBuiltin.execute` (178). Files such as `core/state.py` (1,384 lines),
`core/scope.py` (1,351), `executor/job_control.py` (1,169),
`io_redirect/file_redirect.py` (1,140), and `executor/command.py` (1,060)
remain ownership hubs.

`ParseSession.feed` explicitly retains O(k^2) reparsing for an open k-line
construct at `psh/parser/session.py:250-260`. This was honestly carried as H15,
but it prevents a textbook efficiency grade. Build a resumable lexer/parser
transaction rather than adding another completeness pre-scan.

### MEDIUM-16 - Type checking is broad but not yet deep enough to prove boundaries

Mypy includes all 274 production modules. Body checking is deepened through
package/module overrides rather than the global default, while
`pyproject.toml:98-111` still globally allows untyped and incomplete
definitions. Only the lexer and 17 named campaign modules prohibit incomplete
signatures. Static inventory found 623 of 3,073 functions without complete
parameter and return annotations. Complete signatures matter most at the exact
producer, adapter, and consumer seams the campaign is trying to protect.

### LOW residue

- `psh/utils/printf_formatter.py:408-438,505-518` ignores `%a/%A` precision and
  the alternate-form `#` flag for float conversions.
- A failed permanent-redirect acquisition can retain a newly acquired
  `STD_FDS` component lease (`psh/io_redirect/file_redirect.py:982,1050-1055`).
- The review tree contains skip-on-failure tests, including
  `tests/unit/lexer/test_modular_lexer_integration.py:144-163` and permissive
  arithmetic integration checks at
  `tests/unit/expansion/test_arithmetic_integration.py:17-67`. Supported
  behavior should fail, not skip, when its assertion is false.
- The import-time graph is acyclic, but 183 deferred imports across 67 modules
  are accepted by caps totaling 206 in
  `tests/unit/tooling/test_import_layering.py:217-307`. The ratchet stops growth;
  it does not by itself establish directed conceptual ownership.
- Q2 explicitly freezes 26 defensive accesses to declared fields and eight
  broad exception maskers. These are useful anti-regression ledgers, but they
  are debt inventories rather than closure evidence.

---

## Campaign closure matrix

The labels below compare implementation with the campaign brief, not merely
with each work package's later narrowed charter.

| Package | Verdict | What held | What prevents closure |
|---|---|---|---|
| E1 gate evidence | **Satisfied** | Phase manifests, abnormal-exit classification, canonical commands, and release attestation are substantial improvements. | Fresh local runs exposed one race, but the evidence design itself is sound. |
| E2 one Bash oracle | **Failed** | Binary resolution is centralized and typed outcomes exist. | Output-limit kills are `Completed`; 30 differential callers bypass the runner; static guard blesses the bypass. |
| E4 attestation | **Satisfied** | Tagged attestation is structured, versioned, and records gate/Ruff/mypy state. | It is not a substitute for campaign-specific final-SHA conformance, compare-Bash, and benchmark evidence. |
| F1 invocation | **Partial** | Invocation is parsed before shell construction and source selection is explicit. | Conflicting analysis modes are accepted into an ordered tuple, then silently collapsed under fixed downstream priority. |
| F2 process ownership | **Partial** | Construction purity and single-owner leases are meaningful. | Component rollback, restore-failure ownership, managed signals, and EXIT-trap cleanup are incomplete. |
| F3 source execution | **Satisfied** | One sourced-program service and lazy input policy held under review. | Static analysis still parses under initial options, outside the execution service's evolving state. |
| S1 lexical fusion | **Satisfied** | Fusion-first keyword classification and the focused lexical corpus held. | No blocker found in the S1 scope itself. |
| S2 heredoc identity | **Partial** | Operator IDs/FIFO body attachment improved live heredoc-aware paths. | The executable type and bare parsing permit missing bodies, lexical values are transitively shallow-mutable, and session completeness retains a duplicate delimiter grammar. |
| S3 syntax templates | **Failed** | Named templates preserve more nested syntax than raw strings did. | Subscript procsub meaning/timing is lost; raw bracket extent and location math remain. |
| S4 parser context/outcomes | **Failed** | Parse outcome algebra is useful and RD paths consume it. | Combinator drops `ParseInputs`; parser lifecycle and option snapshots contradict the stated contract. |
| S5 traversal | **Partial** | The sole structural iterator, function grammar, shared substitution helper, and coverage matrix are useful gains. | Visitor adoption is not total: overrides miss registered redirect and loop/case children; the sanctioned backtick/template exclusion also falls short of the campaign-wide exhaustive-analysis goal. |
| W1 field IR | **Partial** | Ordinary expansion carries structured fields farther. | Operator operands flatten multi-field `"$@"`. H5 is not closed. |
| W2 subscript service | **Partial** | Six inconsistent implementations converged on one named evaluator. | The evaluator reparses raw strings, broadly catches defects, and executes associative procsub spelling. |
| W3 pattern engine | **Partial** | One parsed engine serves several consumers. | Nullable sequence composition and negation semantics are wrong, related rows are excluded, cached ASTs are writable, and suffix/global scans are quadratic. |
| R1 redirect IR | **Partial** | Ordered typed operations and fd-remap ownership are among the campaign's best results. | One permanent-acquisition lease rollback edge remains. |
| R2 variable truth | **Partial** | Missing/present-unset/value behavior fixes the original lookup bug. | Mutable singleton and live binding bypass the write authority; value-only protocol flattens the tri-state. |
| R3 resolution | **Failed** | One immutable result now drives most dispatch. | It is computed before prefix expansion establishes authoritative POSIX state. |
| I1 input cursor | **Partial** | Same-fd cursor persistence and surrogateescape byte preservation are strong. | Valid UTF-8 is corrupted at the cursor/bulk-drain seam; cross-fd dup sharing and temporary-redirect isolation hooks remain absent. |
| I2 lazy scripts | **Satisfied** | Physical-line laziness and source policy held in focused review. | No campaign-blocking defect found. |
| I3 parse session | **Partial** | Typed incomplete/invalid outcomes and O(1) heredoc-body feeding help. | Duplicate heredoc regex, O(k^2) open-command reparsing, and the unconsumed fatal-substitution origin remain; full H15 is carried. |
| I4 history outcome | **Partial** | Print-only/error/execute history outcomes are clearer. | History file cursor mutation and the `history -s` `HISTSIZE` bypass remain. |
| J1 jobs/signals | **Partial** | Foreground session and HUP policy are much more explicit. | EXIT-trap bypass, general prompt reaper carry, managed dispositions, and undischarged Linux watch remain. |
| Q1 protocols | **Partial** | Two real migrations and shrink-only census. | Three advertised protocols are unused or broad; six full-`Shell` consumers remain. |
| Q2 ratchets | **Satisfied** | Guards make several debt sets non-growing. | Frozen debt must not be described as removed debt. |
| Q3 closure | **Failed** | The close report contains useful ledgers and candid carry rows. | It contradicts the no-partials exit rule, omits durable evidence and benchmark comparison, and overstates live closures. |

---

## What is already textbook-quality

The negative findings should not obscure the parts worth preserving:

- `RedirectProgram` separates classification from ordered execution and makes
  fd ownership explicit. Its value model and the shared `fd_remap` engine are a
  strong architectural center.
- `InvocationConfig` and `ProgramSource` move startup/source policy ahead of
  mutable shell execution. Their tables make otherwise implicit dialect rules
  inspectable.
- `ResolvedCommand`, `VariableLookup`, `ParseOutcome`, `HistoryExpansionResult`,
  and shell-oracle outcomes are the right *kinds* of values. Most fixes above
  deepen or correctly time those values rather than abandon them.
- Fusion-first lexing removed several downstream reconstructions, and the
  function-definition grammar held in adversarial pipeline and extension
  probes.
- The executor retains one `os.fork()` policy and structured child exception
  mapping; pipeline construction remains bounded in live descriptors.
- `run_tests.py` phase manifests are machine-readable and reject nonzero pytest
  exits. The release attestation records the exact gated tree and tool results.
- Static ratchets commonly include synthetic offender tests. That is the right
  discipline; the E2 and S5 guards need their scope expanded, not discarded.
- Documentation near the new types is unusually explicit about ownership and
  deliberate loss. Where those claims are accurate, the code is genuinely
  teachable.

---

## Recommended remediation campaign

The maintained implementation sequence for this recommendation is
[`boundary_remediation_campaign_sequence_2026-07-21.md`](boundary_remediation_campaign_sequence_2026-07-21.md).

### P0 - Restore trust in answers and shutdown

1. **E2 oracle integrity:** add `OutputLimitExceeded`, reject all truncation,
   migrate every direct differential subprocess, and ratchet process creation.
2. **S5 traversal totality:** introduce one generated child-enumeration contract
   and migrate all production visitors before retaining any positive security
   wording.
3. **R3 authority timing:** expand prefix assignments transactionally before
   the single resolution decision; differential-test every option-changing
   side effect.
4. **F2/J1 shutdown:** make job disposal, history policy, lease restoration,
   and handler restoration independent cleanup phases that all run even when
   an EXIT trap exits or a restore fails.

**Exit:** the `yes` discriminator is `TEST_ERROR`; zero direct Bash oracle
process calls outside the harness; generated traversal sentinels reach every
visitor; the two POSIX prefix probes match Bash; fault/PTY cleanup probes leave
no child, component, fd, locale, or signal disposition behind.

### P1 - Finish the semantic representations

1. Carry field vectors through all parameter-operator operands.
2. Replace raw subscript text reinterpretation with a target-kind-aware parsed
   algebra; preserve procsub spelling until authority is known.
3. Make pattern negation continuation-aware, freeze cached ASTs, and compute
   all-start relations once.
4. Freeze `VariableLookup` and return immutable binding views.
5. Repair incremental UTF-8 finalization, history file cursors, and executable
   heredoc validity.
6. Give RD and combinator parsers the same required `ParseInputs` value and
   source spans.
7. Consume substitution-origin parse failures as fatal typed frame outcomes.

**Exit:** every externally observable discriminator in HIGH-4 through HIGH-7,
HIGH-9, and MEDIUM-2 through MEDIUM-7 is Bash-pinned; internal value integrity
is mutation/invariant-pinned; no expected divergence encodes a campaign target;
cached/read values cannot be poisoned; suffix/global relation counts are linear
in subject positions for a fixed AST.

### P2 - Complete dependency and incremental-processing architecture

1. Build a resumable lexer/parser transaction and delete raw heredoc and extent
   scanners as decision authorities.
2. Replace full-`Shell`, `ShellState`, and `Any` protocol members with narrow
   value/capability ports; migrate all current consumers.
3. Decompose the largest ownership hubs around already named transactions:
   shell-state construction, command preparation/dispatch, job lifecycle,
   history expansion, and input execution.
4. Require complete annotations package by package, beginning with boundary
   producers/adapters/consumers.
5. Replace broad exception families with typed user-error variants.

**Exit:** no protocol is defined but unused; full-`Shell` consumer allowlist is
empty or contains only a documented orchestration root; open-command feed has a
deterministic linear work counter; no production function over 150 lines unless
an explicit cohesion review approves it; all public boundary signatures are
complete.

### P3 - Make closure evidence self-contained

1. Commit the operating brief before implementation begins and preserve
   ledgers/probe outputs under a durable documentation/evidence path.
2. Separate `closed`, `partial`, `sanctioned divergence`, and `carried` in both
   headline and tables; never redefine exit criteria in the close report.
3. Run the standard gate, Ruff, mypy, live conformance, compare-Bash, complexity
   counters, and benchmark deltas against one final tree; record exact commands,
   versions, SHA, environment, and outcomes.
4. Remove skip-on-failure tests and repair race-dependent process tests.

**Exit:** a clean checkout of the tagged commit contains every linked plan,
ledger, probe, comparison, and benchmark; every command is reproducible from
`docs/testing_source_of_truth.md`; the reviews index has one unambiguous current
appraisal and campaign state.

---

## Validation record

### Tagged release evidence

`gate_attestation.json` for v0.749.0 records:

```text
gated commit  f0aeda29db32556a6b634f5cb5496cd1691305ef
parallel      19,298 passed; 1,590 skipped; 8 xfailed
serial           892 passed;     0 skipped; 2 xfailed
ruff          clean
mypy          clean across 274 source files
```

### Fresh audit runs

| Command/scope | Result |
|---|---|
| `ruff check psh tests tools` | pass |
| `mypy` | pass, 274 source files |
| E2 oracle/guard + I3 session focused suite | 37 passed |
| S1-S5/I3 focused syntax suite | 653 passed |
| expansion/core/protocol/ratchet focused suite | 3,614 passed, 17 skipped |
| builtins + printf formatter focused suite | 1,638 passed |
| execution campaign-focused suite (v0.748.0; relevant v0.749.0 diff inspected) | 274 passed |
| invocation/source/lazy/redirection suite (v0.748.0; relevant v0.749.0 diff inspected) | 352 passed |
| two initially failing tests rerun in isolation | 2 passed |
| `python -m pytest tests/conformance -q` | 2,539 passed, 1 skipped, 8 xfailed in 547.31s |
| live golden comparison phase (`--compare-bash`, xdist) | 1,481 passed, 24 skipped in 24.39s |

The first fresh standard gate in the existing v0.748.0 worktree completed with
20,176 passes, 1,600 skips, 10 xfails, and two failures. Both failures passed
immediately together in isolation; one is the race in MEDIUM-13. A second full
gate against the clean v0.749.0 checkout was invalidated at 73% by host
`ENOSPC` (21 failures and 17 errors dominated by errno 28); its outcome is not
attributed to PSH. These runs do not supersede the release attestation, but they
do show why deterministic process tests and bounded test artifacts remain part
of correctness.

Focused-suite counts overlap and must not be summed. The live golden phase was
run directly, without redundantly repeating the standard suite:

```bash
python -m pytest tests/behavioral/test_golden_behavior.py \
  -k test_golden_bash_comparison --compare-bash -n auto -q
```

Every behavioral finding above was also run as a direct discriminator; green
broad suites do not refute a missing row or a test that encodes the divergent
result.

---

## Final assessment

v0.749.0 is better architected than the v0.724.0 baseline. The campaign chose
the right general remedy and landed enough infrastructure that the next phase
can repair contracts rather than start over. The central mistake was declaring
canonical *names and carriers* sufficient before proving total production
adoption, immutability, authority timing, and failure behavior.

Do not revert the architecture. Tighten it. Treat the v0.749.0 close report as
an implementation checkpoint, execute P0 and P1, and require the P3 evidence
ceremony before using "closed" again. On that basis the codebase can plausibly
move from B- to A-range without another broad rewrite.
