# Boundary Remediation Campaign Sequence

- **Date:** 2026-07-21
- **Status:** Active implementation roadmap; work has not started
- **Planning baseline:** PSH 0.749.0 at `31aab012`
- **Source appraisal:**
  [`ground_up_reappraisal_22_correctness_textbook_2026-07-20.md`](ground_up_reappraisal_22_correctness_textbook_2026-07-20.md)
- **Purpose:** close the live boundary defects from reappraisal #22 without a
  monolithic rewrite or isolated subsystem fixes that lose the end-to-end
  semantic contract

---

## 1. Decision

Execute a **sequential boundary-remediation campaign**. Do not run one giant
"fix the whole review" pass, and do not assign findings to subsystems that work
in isolation.

Each wave is a vertical semantic slice:

```text
producer -> canonical value -> authority decision -> every consumer -> guard
```

This shape follows the central finding from reappraisals #20 and #22: most live
defects are not local algorithm mistakes. They arise when a fact is created in
one subsystem, flattened or interpreted too early at a boundary, and then
reconstructed differently by downstream consumers.

The sequence restores test trust first, repairs user-visible semantic
boundaries next, completes lifetime ownership after that, and only then takes
on broad dependency and decomposition work. A short whole-tree checkpoint
after Wave 4 catches replacement twins before the textbook-architecture wave.

## 2. Campaign outcome

The campaign succeeds when:

1. Every HIGH and MEDIUM finding in reappraisal #22 is closed or explicitly
   removed from scope before implementation begins. A later transfer may be
   recorded, but it keeps this campaign open and does not satisfy success.
2. Every changed boundary has one lossless representation, one authority, a
   complete consumer census, and an executable anti-bypass guard.
3. Externally observable behavior is differential-pinned to GNU Bash 5.2.26
   where Bash compatibility is the contract.
4. Internal invariants are fault-, mutation-, complexity-, or ownership-pinned
   rather than forced into inappropriate Bash comparisons.
5. A clean checkout of the final commit contains the plan, ledgers, essential
   probe evidence, benchmark comparison, exact validation commands, and close
   report.
6. No item described as `partial`, `carried`, `watch`, `TBD`, or "future
   campaign" is counted as closed.

This campaign is not a feature-parity sweep. Unrelated missing Bash features,
cosmetic message differences, and refactors without a #22 boundary or measured
maintenance payoff remain outside scope.

## 3. Standing implementation rules

Every wave follows these rules:

1. Rebase the finding onto the wave's actual base commit. Re-locate cited
   symbols and reproduce the defect before editing; v0.749.0 line numbers are
   historical coordinates, not permission to assume the code is unchanged.
2. Create a durable boundary ledger under
   `docs/reviews/evidence/boundary_remediation_2026-07/`. Record the semantic
   fact, producer, old loss point, canonical representation, authority,
   consumers, deliberate terminal projections, probes, and guards.
3. Demonstrate the behavioral or invariant pin failing on the wave base.
   Existing green tests that encode the divergent PSH result do not count.
4. Land the canonical representation and its invariant tests before migrating
   consumers. A new type name without complete adoption is not closure.
5. Inventory and migrate every production and test consumer. Temporary
   adapters may project to terminal strings, argv, environment vectors,
   pathnames, syscalls, or display output; they may not feed flattened data
   back into semantic processing.
6. Delete the superseded decision path in the same wave. A compatibility
   adapter must have a named owner, consumer census, removal condition, and
   anti-expansion guard.
7. Prefer generated or static guards that prove the negative claim: no direct
   subprocess oracle, no unvisited AST child, no second resolution, no raw
   subscript reparse, no unmanaged process-global mutation.
8. Run focused tests while developing, then the standard gate, Ruff, and mypy
   at the wave's final tree. Run live Bash and complexity/fault/PTY legs when
   the wave requires them.
9. Update architecture and user-facing difference documentation in the same
   change as the contract. Do not leave the close report to reinterpret an
   implementation that has already shipped.
10. An adversarial verifier who did not implement the wave reruns the headline
    probes, attempts one synthetic bypass per guard, and checks the consumer
    census before the wave closes.

Bulky full-suite transcripts may remain build artifacts, but the repository
must contain the structured outcome, command, environment, commit, artifact
identity, and the compact evidence needed to reproduce every closure claim.

## 4. Status and dependency order

| Order | Wave | Status | Depends on |
|---:|---|---|---|
| 0 | Launch and revalidation | Not started | None |
| 1 | Restore evidence trust | Not started | Wave 0 |
| 2 | Syntax identity and analysis totality | Not started | Wave 1 |
| 3 | Expansion semantics and command authority | Not started | Wave 2 |
| 4 | Lifetime and state ownership | Not started | Wave 3 |
| R | Whole-tree boundary checkpoint | Not started | Wave 4 |
| 5 | Textbook dependency and incremental architecture | Not started | Checkpoint R |
| C | Final evidence and closure | Not started | Wave 5 |

Wave N+1 does not merge until Wave N satisfies its exit criteria. Work inside a
wave may be split into small commits or pull requests, but its producer,
representation, consumers, deletion, and guards close as one reviewed unit.

---

## 5. Wave 0 - Launch and revalidation

### Scope

- Commit this roadmap and its source appraisal before production work begins.
- Select and record the real implementation base, which may be newer than
  v0.749.0.
- Re-run every HIGH discriminator and a representative MEDIUM discriminator
  from #22 against that base.
- Convert the finding map in section 13 into a live ledger with one owner and
  one disposition per row.
- Establish a clean validation baseline using
  [`docs/testing_source_of_truth.md`](../testing_source_of_truth.md).
- Create the durable evidence directory and a machine-readable wave manifest.

### Exit criteria

- Every #22 HIGH/MEDIUM has an owner, wave, base result, and intended closure
  test.
- No owner is `TBD`; no finding silently disappears because code moved.
- Baseline test failures, skips, xfails, platform constraints, and benchmark
  results are recorded before implementation.
- The roadmap and evidence schema exist in the same committed tree used to
  begin Wave 1.

---

## 6. Wave 1 - Restore evidence trust

### Owned findings

- HIGH-1: false-green differential oracle and direct subprocess bypasses.
- HIGH-10: durable evidence and closure-artifact defects, for the evidence
  infrastructure portion.
- MEDIUM-13: race-dependent background-subshell test.
- LOW test residue: skip-on-failure tests and oracle/guard blind spots.

### Architecture target

There is one shell-case runner and one comparison policy. Process spawn,
temporary cwd, stdin, timeout, output limit, process-group termination,
decoding, provenance, and cleanup are inseparable parts of a typed harness
outcome. `Completed` means the command completed without a harness-enforced
termination or truncated observation.

### Required work

1. Add `OutputLimitExceeded` or an equivalent non-`Completed` outcome carrying
   capped output, configured limit, duration, and termination details.
2. Reject every truncated or harness-terminated result before behavioral
   comparison. Preserve `Timeout`, `SpawnFailure`, and decode failures as
   non-comparable outcomes.
3. Migrate the full direct-process census. The v0.749.0 baseline contained 30
   Bash differential modules that resolved Bash and then bypassed the runner;
   the wave closes the current census, not only that historical number.
4. Replace the binary-resolution-only ratchet with an AST guard that rejects
   direct `subprocess`, `os.system`, `os.popen`, and hidden helper launch paths
   in oracle-bearing modules. Guard the guard with synthetic offenders.
5. Replace timing races with bounded synchronization through the shell's job
   API. Assertions must run unconditionally after completion.
6. Convert supported-feature tests that skip on assertion failure into hard
   failures with precise diagnostics.
7. Start the durable campaign evidence manifest here; every later wave depends
   on this trusted observation layer.

### Exit criteria

- Comparing `yes` with `yes` under a small output limit produces `TEST_ERROR`
  or the equivalent harness-failure result, never `IDENTICAL`.
- The current test tree has zero unapproved Bash differential process launches
  outside the runner, proven by a synthetic-offender guard.
- Timeout, output-limit, child/grandchild cleanup, decode, stdin, cwd, and
  provenance cases are typed and independently pinned.
- The background-subshell test waits deterministically and asserts exact
  output on every run; repeated and shuffled runs remain green.
- Standard gate, live conformance, live golden comparison, Ruff, and mypy pass
  at the Wave 1 final tree.

---

## 7. Wave 2 - Syntax identity and analysis totality

### Owned findings

- HIGH-2: production visitors do not consume the complete AST child set.
- HIGH-4: subscript process-substitution identity and timing loss.
- HIGH-5: combinator `ParseInputs` context loss.
- HIGH-9: substitution-origin errors do not abort the correct source frame.
- MEDIUM-3, MEDIUM-4, MEDIUM-9, MEDIUM-10, and MEDIUM-11.
- The subscript raw-reparse portion of MEDIUM-12.

### Architecture target

Syntax is parsed once into immutable, source-located values. One structural
child schema owns traversal. Both parsers receive the same immutable
`ParseInputs`; target-kind authority decides subscript semantics only after the
syntax representation has preserved every relevant distinction.

### Required work

1. Make framework-owned child enumeration total for every registered AST
   field. Migrate all production visitors; remove early returns and manual
   recursion that bypass redirect targets, loop/case words, backticks, or
   nested templates.
2. Generate sentinel-child coverage for every node field and every production
   visitor. Security mode must not make a clean claim if any executable region
   is intentionally opaque.
3. Define one parser entry point that requires `ParseInputs` and carries lexer
   options, source text, line offset, depth budget, and heredoc identity through
   RD, combinator, and every nested parse.
4. Replace raw square-bracket extent counting with one quote- and
   expansion-aware scanner or parser production. Attach absolute `SourceSpan`
   values to nested substitutions.
5. Represent subscript syntax without deciding indexed versus associative
   runtime meaning. Preserve process-substitution spelling and read-time
   validity; remove later raw-string re-lexing.
6. Separate incomplete heredoc syntax from executable
   `HeredocRedirect(body: str)`. Freeze token parts and the transitive lexical
   value graph.
7. Derive interactive pending heredocs from canonical lexer events. Delete the
   regex delimiter grammar as a decision authority.
8. Consume `SubstitutionSyntaxError` through a typed source-frame outcome that
   aborts `-c`, `eval`, and source at the correct level and status.
9. Make analysis state-aware across option-changing input, and either compose
   multiple requested analysis modes explicitly or reject the combination at
   invocation parsing.

### Exit criteria

- Generated traversal sentinels reach every production visitor; the #22
  redirect-only, loop, case, backtick, and template security probes are found.
- RD and combinator receive identical `ParseInputs`, agree on the campaign
  corpus, and report the same source locations for nested failures.
- Associative process-substitution spelling remains literal; invalid syntax is
  rejected at Bash-compatible read time; indexed semantics remain arithmetic.
- Escaped/quoted heredoc-operator equivalence holds between lexer and session,
  including `echo \\<<EOF`; no duplicate delimiter grammar remains authoritative.
- Substitution-body syntax failures abort every applicable execution frame and
  do not run later commands.
- Executable AST and lexical values reject or prevent mutation into invalid
  states.

---

## 8. Wave 3 - Expansion semantics and command authority

### Owned findings

- HIGH-3: resolution before side-effecting prefix expansion.
- HIGH-6: parameter-operator operand field flattening.
- HIGH-7: nullable extglob composition, negation semantics, and quadratic
  all-start relations.
- MEDIUM-6: writable cached pattern ASTs.
- Remaining expansion/arithmetic exception-boundary work from MEDIUM-12.

### Architecture target

Expansion values retain field, quote, protection, and syntax identity until a
named terminal projection. Pattern matching is one immutable compiled relation
with continuation-correct semantics and bounded work. Command resolution runs
once, after every fact that affects precedence exists.

### Required work

1. Replace scalar `OperandResult` projection with a field-vector representation
   capable of preserving multiple `"$@"` fields and explicit empties through
   `:-`, `:+`, `:=`, and related operands.
2. Inventory every scalar projection. Retain it only for a terminal consumer
   whose semantics explicitly require one string.
3. Implement continuation-aware extglob sequence and negation semantics across
   `[[ ]]`, `case`, pathname contexts, parameter removal, and substitution.
4. Freeze cached pattern nodes and derived metadata. A caller must be unable to
   mutate the result of one compile and affect later matches.
5. Compute suffix starts and global-substitution spans in one all-start
   relation per subject instead of restarting dynamic programming at every
   position.
6. Expand prefix assignments left to right in a transactional command
   environment, establish permitted shell side effects, then create exactly
   one `ResolvedCommand` from the authoritative option state.
7. Replace broad internal `Exception`/`TypeError` conversion with typed
   user-syntax and expansion failures.

### Exit criteria

- `unset x; set -- a b; printf '<%s>' "${x:-"$@"}"` prints `<a><b>` and the
  complete operator/quoting/empty-field matrix matches Bash.
- The three #22 nullable/extglob discriminators and generated finite-alphabet
  cases agree with Bash in every consumer.
- Mutation attempts cannot alter compiled pattern values or later cache hits.
- Deterministic transition counts for suffix and no-match substitution are
  linear in subject positions for a fixed pattern AST; benchmark deltas are
  recorded.
- Arithmetic and `${...:=...}` side effects that enable POSIX mode produce the
  same single dispatch decision as Bash.
- Static guards find no semantic scalar re-entry, second command resolution,
  or raw subscript/pattern reinterpretation.

---

## 9. Wave 4 - Lifetime and state ownership

### Owned findings

- HIGH-8: incomplete activation/component rollback.
- MEDIUM-1, MEDIUM-2, MEDIUM-5, MEDIUM-7, and MEDIUM-8.
- The permanent-redirection lease rollback item from LOW residue.
- Full-contract `InputCursor` gaps: cross-fd dup sharing and temporary-redirect
  isolation, revalidated against the implementation base.

### Architecture target

Process-global mutations belong to one recoverable activation transaction.
Shutdown consists of independent mandatory phases. Read views are immutable;
input decoding and history/file cursors belong to the lifetime that owns their
continuity.

### Package 4A - Process lifetime

1. Checkpoint component depth on activation/acquisition and restore all newly
   acquired components before rolling back owner metadata.
2. Attempt every LIFO restore even if one fails. Surface an aggregate internal
   error and retain/quarantine ownership if the process cannot be proven clean.
3. Put managed interactive signal dispositions under component leases and
   restore the exact previous handlers on close.
4. Split shutdown into mandatory phases so EXIT-trap `SystemExit` cannot bypass
   job disposition, detached reaping, required history policy, or resource
   restoration. Specify exit-status precedence.
5. Release newly acquired `STD_FDS` state when permanent redirect acquisition
   fails.

### Package 4B - Semantic state lifetimes

1. Make `VariableLookup` immutable, eliminate the mutable missing singleton,
   and return an immutable binding snapshot or capability-free `VariableView`.
   All writes continue through `VariableStore` by identifier.
2. Finalize incremental UTF-8 decoding by feeding remaining bytes through the
   existing decoder. Pin character identity and byte round-trip at every
   multibyte split.
3. Complete the cursor ownership model for dup-related descriptors and
   temporary redirect frames, or narrow the contract explicitly before work
   begins and leave the campaign open for the omitted behavior.
4. Keep history file-read position independent from in-memory deletion and
   apply the normal `HISTSIZE` policy to `history -s`.

### Exit criteria

- Fault injection at every acquisition and restore boundary leaves the prior
  owner/component/process state intact, or a visible quarantined owner when
  restoration genuinely fails.
- PTY tests prove EXIT-trap exits still apply HUP/reap/history policy and leave
  no child, handler, terminal state, fd, or lease behind.
- Variable lookup values and bindings reject mutation; readonly, nameref,
  observer, and exported-environment coherence remain intact.
- Every split of valid 2-, 3-, and 4-byte UTF-8 input yields the original
  character sequence; malformed bytes still round-trip under surrogateescape.
- History `-r/-n/-d/-s/-a/-w` state-machine sequences match Bash and respect
  memory limits without duplicate file lines.

---

## 10. Checkpoint R - Whole-tree boundary reappraisal

After Waves 1-4, run a short independent whole-repository appraisal. This is a
checkpoint, not another open-ended review campaign.

### Questions

1. Do all original #22 HIGH and user-visible MEDIUM discriminators now pass?
2. Did any adapter, raw-string fallback, visitor override, subprocess helper,
   or service-locator path recreate a deleted boundary?
3. Are the new representations transitively immutable and authority-timed?
4. Did the work introduce new dependency cycles, deferred-import caps, broad
   owner parameters, complexity cliffs, process leaks, or flaky tests?
5. Is Wave 5 still the right architecture backlog, or did Waves 1-4 remove or
   reshape some of it?

### Exit criteria

- An independent report records confirmed closures, new blockers, and an
  updated Wave 5 scope.
- No unresolved correctness or evidence-trust blocker is deferred into
  textbook cleanup.
- Wave 5 begins from a freshly verified consumer/import/typing/complexity
  census rather than the historical v0.749.0 counts.

---

## 11. Wave 5 - Textbook dependency and incremental architecture

### Owned findings

- MEDIUM-14: incomplete and ambiguous protocol boundaries.
- MEDIUM-15: quadratic parse sessions and oversized ownership hubs.
- MEDIUM-16: incomplete boundary signatures.
- Remaining broad exception maskers, deferred-import debt, defensive declared
  field access, and cohesion work from LOW residue.
- Any architecture-only findings accepted by Checkpoint R.

### Package 5A - Resumable parsing

Build a resumable lexer/parser transaction for open interactive commands.
Delete full-buffer reparsing and raw completeness scanners as authorities.
Prove linear work with deterministic operation counters, including nested open
constructs and heredoc transitions.

### Package 5B - Capability boundaries

Replace full `Shell`, `ShellState`, and `Any` protocol members with narrow
capabilities or immutable context values. Migrate all consumers. Resolve
`ExpansionContext` and `LocaleContext` naming collisions, move shared POSIX
tables to a neutral owner, and remove the core-to-expansion private import.

### Package 5C - Cohesion, errors, and typing

Decompose large ownership hubs around named transactions rather than arbitrary
line counts: state construction, command preparation/dispatch, job lifecycle,
history expansion, input execution, and redirect acquisition. Replace broad
exception nets with typed user failures. Require complete annotations first at
boundary producers, adapters, protocols, and consumers, then deepen by package.

### Exit criteria

- Open-command feed has a deterministic linear work bound and no duplicate
  completeness grammar.
- No protocol is defined but unused. Full-`Shell` consumers are eliminated or
  limited to a reviewed orchestration root; protocol members contain no broad
  owner escape hatch.
- Runtime imports remain acyclic and deferred-import caps materially shrink.
- Every public boundary signature is complete and mypy checks its body.
- Broad exception and defensive-access ratchets shrink to zero or retain only
  individually justified terminal-boundary cases.
- Large functions/files have explicit cohesive owners; decomposition is
  measured by responsibility and testability, not cosmetic extraction.

---

## 12. Final evidence and closure ceremony

Closure runs against one final source tree. Documentation-only and attestation
commits may follow only under the repository's same-tree release rules.

Required commands and evidence:

```bash
python run_tests.py --parallel
ruff check psh tests tools
mypy
python -m pytest tests/conformance -q
python run_tests.py --compare-bash
python run_tests.py --benchmarks
```

Also required:

1. Rerun every #22 discriminator and every wave-composed case at the final
   tree, including PTY, fault-injection, mutation, and complexity legs.
2. Run at least three declared shuffle seeds with identical phase censuses.
3. Compare deterministic counters and benchmark results with the Wave 0
   baseline; explain every material regression.
4. Run every static guard against at least one synthetic offender.
5. Commit the final boundary ledger, consumer census, deliberate terminal-loss
   registry, API changes, exact tool versions, commands, results, final commit,
   and evidence manifest.
6. Produce a close report whose headline agrees with its tables. A partial
   finding keeps the campaign open; it does not become a successful carry.
7. Update this document's status and the reviews index only after the evidence
   is present in a clean checkout.

---

## 13. Finding ownership map

| #22 finding | Primary wave | Closure owner |
|---|---:|---|
| HIGH-1 oracle false green/bypass | 1 | Test evidence boundary |
| HIGH-2 visitor coverage | 2 | AST traversal and analysis |
| HIGH-3 prefix-resolution timing | 3 | Command preparation/resolution |
| HIGH-4 subscript procsub identity | 2 | Syntax-to-subscript boundary |
| HIGH-5 combinator context loss | 2 | Parser input contract |
| HIGH-6 operand field flattening | 3 | Expansion field IR |
| HIGH-7 pattern semantics/complexity | 3 | Pattern relation engine |
| HIGH-8 lease rollback | 4A | Process activation ownership |
| HIGH-9 fatal substitution outcome | 2 | Parse-to-source-frame outcome |
| HIGH-10 closure evidence | 0, 1, C | Campaign integrator |
| MEDIUM-1 EXIT-trap cleanup | 4A | Shutdown transaction |
| MEDIUM-2 UTF-8 decoder seam | 4B | Input cursor |
| MEDIUM-3 duplicate heredoc grammar | 2 | Lexer/session contract |
| MEDIUM-4 extent/source locations | 2 | Parser source model |
| MEDIUM-5 mutable variable read | 4B | Variable read/write authority |
| MEDIUM-6 mutable pattern cache | 3 | Pattern compiler/cache |
| MEDIUM-7 history cursors | 4B | History state machine |
| MEDIUM-8 signal disposition leak | 4A | Process activation ownership |
| MEDIUM-9 stale/conflicting analysis | 2 | Invocation and analysis session |
| MEDIUM-10 invalid/shallow syntax values | 2 | Lexer/parser value model |
| MEDIUM-11 parser lifecycle | 2 | Parser input contract |
| MEDIUM-12 broad semantic catches | 2, 3, 5C | Typed error boundaries |
| MEDIUM-13 background-test race | 1 | Test evidence boundary |
| MEDIUM-14 incomplete protocols | 5B | Capability architecture |
| MEDIUM-15 complexity/ownership hubs | 5A, 5C | Parser and subsystem owners |
| MEDIUM-16 incomplete signatures | 5C | Boundary type contracts |
| LOW printf formatting | Follow-on or Wave 5 rider declared at Wave 0 | Builtin formatting |
| LOW redirect lease rollback | 4A | Redirect/process lease ownership |
| LOW skip-on-failure tests | 1 | Test evidence boundary |
| LOW deferred imports/Q2 debt | 5B, 5C | Dependency and type architecture |

A split row still has one integrator. Package owners may implement separate
pieces, but no package closes the row until the composed end-to-end probe and
anti-bypass guard pass.

## 14. Recommended release cadence

- **Wave 0:** documentation/evidence bootstrap only.
- **Wave 1:** one release; later semantic work must rely on its runner.
- **Wave 2:** small producer-first commits, one composed closure release.
- **Wave 3:** field IR, pattern relation, and resolution may use separate pull
  requests, but close together only after cross-composition probes.
- **Wave 4:** land 4A before 4B so fault tests run under the corrected process
  ownership model; close one wave after combined PTY/resource verification.
- **Checkpoint R:** report only, followed by Wave 5 scope amendment.
- **Wave 5:** incremental packages 5A-5C; each may release independently, while
  campaign closure waits for all three.
- **Ceremony C:** final evidence and close report at one verified tree.

The implementation order may change only through a committed amendment that
states the dependency reason, updates the ownership map, and preserves Wave 1
as the first production change.
