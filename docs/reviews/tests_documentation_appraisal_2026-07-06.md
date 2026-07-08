# Tests and Documentation Appraisal — 2026-07-06

## Scope

This is a fresh appraisal of the test and documentation corpus, graded for:

- correctness of test oracles and assertions;
- alignment between tests, claims, and documented project status;
- determinism, isolation, timeout behavior, and process cleanup;
- efficiency of the developer and release test workflows;
- usefulness of test tooling and meta-tests;
- documentation accuracy, structure, maintainability, and drift resistance;
- textbook-quality writing and engineering communication.

The review covered `tests/`, `run_tests.py`, `pytest.ini`, `.github/workflows/`,
the README and architecture documents, user and developer documentation under
`docs/`, and existing review/index material. It also ran targeted checks for
tooling tests, conformance-claim tests, linting, performance tests, collection
count, and local Markdown link integrity.

## Executive Judgment

The project has substantial test breadth and several genuinely strong quality
ideas. The suite currently collects 14,176 pytest items, spans unit,
integration, regression, system, conformance, performance, and interactive
areas, and includes meaningful tooling tests around documentation claims and
statistics.

The main weakness is not lack of tests. The main weakness is trust alignment:
some tests, docs, and public claims describe stronger verification than the
repository currently provides.

The highest-impact issues are:

- POSIX conformance is compared primarily against default Bash behavior, not a
  POSIX oracle.
- Some conformance tests are probes with no behavioral assertion.
- The default pytest gate excludes `tests/performance`.
- `run_tests.py --quick` is not meaningfully quick; it deselects almost no tests.
- Many subprocess tests lack direct timeout enforcement.
- Some fixtures and test docs mutate `state.variables`, which is a derived
  dictionary rather than the source of truth.
- Documentation contains contradictory test counts, stale version/support
  claims, obsolete architecture references, and outdated testing guidance.

Overall grades:

| Area | Grade | Summary |
| --- | --- | --- |
| Test suite | B- | Broad and valuable, but the oracle layer and gates overclaim. |
| Documentation | C- | Useful prose exists, but semantic drift is substantial. |
| Combined trust/readiness | C+ | Good foundations, but the public truth surface needs tightening. |

For a textbook-quality project, the next step should not be simply “add more
tests.” The next step should be to make the tests and documentation tell the
exact truth about what is verified.

## What Is Strong

### Broad test coverage

The repository has unusually broad test coverage for a shell implementation:

- unit tests;
- integration tests;
- regression tests;
- system tests;
- interactive PTY-oriented tests;
- conformance tests;
- performance tests;
- tooling/meta-tests.

Collection currently reports 14,176 pytest items. That is a serious base to
build from.

### Useful meta-testing direction

The project already contains tooling tests that aim to keep documentation and
tests synchronized:

- `tests/conformance/test_claims_have_tests.py` checks that documented Bash
  compatibility claims have corresponding test coverage.
- `tests/unit/tooling/test_readme_statistics.py` checks selected README
  statistics against the repository.
- `tests/unit/tooling/test_user_doc_links.py` checks selected user-guide links.
- `tests/unit/tooling/test_doc_pointers.py` checks selected documentation
  references.

Those tests are conceptually good. The issue is that their current scope is too
narrow for the number of claims now present in the documentation.

### Good evidence of engineering intent

The testing infrastructure shows real attention to isolation, process cleanup,
capture behavior, and conformance tracking. `run_tests.py` has process-group
cleanup logic for timeouts, and `tests/conftest.py` contains multiple fixtures
intended to isolate shell state, environment, and temporary directories.

The docs also have strong local sections. The best writing explains rationale,
not just commands. The problem is drift, not uniformly poor writing.

## Critical Findings

### C1. POSIX conformance is not using a POSIX oracle

The conformance framework finds and invokes Bash by default:

- `tests/conformance/conformance_framework.py:143`
- `tests/conformance/conformance_framework.py:194`

`run_in_bash()` invokes Bash without `--posix` and without setting
`POSIXLY_CORRECT`. That makes Bash compatibility the primary oracle, not POSIX
conformance.

There are also Bash constructs inside the POSIX conformance tree. For example,
`tests/conformance/posix/test_test_file_operators_conformance.py:55` contains
`[[ ... ]]` tests under the POSIX category.

This matters because the documentation publishes POSIX-support-style claims.
Those claims are not defensible unless the denominator and oracle are explicit.

#### Recommendation

Split conformance into distinct oracle families:

1. POSIX conformance
   - Use `bash --posix`, `dash`, another POSIX shell, or a citation-backed
     expected-output matrix.
   - Do not include Bash-only syntax.
   - Attach POSIX references for subtle semantics.

2. Bash compatibility
   - Use default Bash as the comparison oracle.
   - Treat Bash extensions as Bash compatibility, not POSIX conformance.

3. PSH-defined behavior
   - Use direct expected-output/status assertions.
   - Use documented-difference IDs where PSH intentionally diverges.

Do not publish POSIX percentages unless they are generated from a mechanically
defined matrix.

### C2. Some conformance tests are probes, not assertions

Several Bash compatibility tests call `check_behavior()` without asserting
equivalence or expected behavior. Examples include tests around:

- `read`;
- nested brace expansion;
- extended globbing;
- history commands;
- here-documents;
- export behavior.

Representative locations:

- `tests/conformance/bash/test_bash_compatibility.py:79`
- `tests/conformance/bash/test_bash_compatibility.py:245`
- `tests/conformance/bash/test_bash_compatibility.py:298`
- `tests/conformance/bash/test_bash_compatibility.py:359`
- `tests/conformance/bash/test_bash_compatibility.py:444`
- `tests/conformance/bash/test_bash_compatibility.py:609`

The framework itself states that `check_behavior()` performs no assertion:

- `tests/conformance/conformance_framework.py:343`

That is acceptable for exploratory diagnostics, but not for tests counted as
passing conformance coverage.

#### Recommendation

Require every conformance test counted in a claim to assert one of:

- exact stdout, stderr, and exit status;
- equivalence to a declared oracle;
- a documented difference ID;
- an explicit `xfail` or unsupported reason.

Move assertion-free probes into a separate exploratory suite, or rename them so
they are not counted as conformance evidence.

### C3. The release gate is less complete than the docs imply

`pytest.ini:11` excludes `tests/performance` by default:

```ini
--ignore=tests/performance
```

The performance suite does run successfully when invoked explicitly, but it is
not part of the direct pytest default. That is fine only if the documentation
distinguishes between a core correctness gate and a full validation gate.

The quick path is also misleading. `run_tests.py --quick` is documented as a
fast iteration mode, but collection showed that it deselects only one slow test
from the main set. In practice, it is close to a full run rather than a small
developer smoke suite.

Relevant files:

- `pytest.ini:11`
- `docs/testing_source_of_truth.md:47`
- `run_tests.py:45`

#### Recommendation

Define three explicit gates:

| Gate | Intended use | Required content |
| --- | --- | --- |
| `quick` | Local iteration | Small deterministic smoke suite. |
| `standard` | Normal pre-PR validation | Unit, integration, regression, selected conformance. |
| `full` | Release/nightly validation | Standard plus full conformance, interactive, performance, coverage. |

The docs, `run_tests.py`, and CI should use these names consistently.

### C4. Runner cleanup is incomplete for interrupted runs

`run_tests.py` has useful process-group cleanup for timeout cases:

- `run_tests.py:198`
- `run_tests.py:228`

However, the cleanup path is centered on `subprocess.TimeoutExpired`. It does
not provide equivalent cleanup for `KeyboardInterrupt`, `SystemExit`, or other
early-exit paths. During previous runner use, interrupting a long test run left
child pytest/processes behind, which matches the code structure.

The runner also captures phase output and prints it after completion. That
keeps logs clean but gives little progress feedback during long phases.

#### Recommendation

Harden the runner:

- wrap active phase execution in `try/finally`;
- on `KeyboardInterrupt`, terminate the active process group before returning
  or re-raising;
- add periodic progress output for long phases;
- make timeouts phase-specific instead of relying mainly on the 1800-second
  default in `run_tests.py:45`.

### C5. Fixtures and docs mutate a derived variable dictionary

`ShellState.variables` is a derived dictionary:

- `psh/core/state.py:621`

Some fixtures and docs still mutate it directly:

- `tests/conftest.py:113`
- `tests/conftest.py:150`
- `docs/test_pattern_guide.md:52`
- `docs/test_pattern_guide.md:75`

Those writes do not update the authoritative variable store. This creates
dangerous false setup: a fixture can appear to configure shell state while
actually writing into a temporary derived object.

#### Recommendation

- Ban direct writes to `shell.state.variables`.
- Use the proper variable-setting API everywhere.
- Add a tooling test that detects assignment or mutation of `state.variables`.
- Update `docs/test_pattern_guide.md` to use the correct API.

### C6. Subprocess usage needs a timeout policy

A static AST scan found many `subprocess.run()` and `Popen()` calls in tests
without a direct timeout argument. Some may be wrapped safely by surrounding
logic, but the suite does not currently enforce a uniform policy.

For a shell project, unbounded subprocesses are a significant reliability risk.
They can make CI hangs nondeterministic and difficult to debug.

#### Recommendation

Create a blessed subprocess helper for tests, for example:

- `run_psh(...)`;
- `run_bash(...)`;
- `run_command_with_timeout(...)`.

Then add a tooling test that rejects raw `subprocess.run()` and `Popen()` calls
without:

- a timeout argument; or
- a documented helper exemption.

## Documentation Findings

### D1. Status and statistics are contradictory

The documentation repeats volatile statistics in many places, and those claims
have drifted apart.

Examples:

- `README.md:7` says “13,000+ tests.”
- `README.md:34` says “8,400+ tests.”
- `README.md:251` says “14,104 tests in 538 files.”
- `README.md:302` says “12,686 tests across 485 files.”
- `tests/README.md:9` contains stale suite-size language.
- Current collection reports 14,176 tests.

This makes the project look less disciplined than the underlying test effort
deserves.

#### Recommendation

Generate volatile statistics. Do not hand-maintain test counts, file counts, or
support percentages in multiple documents.

A better pattern:

- one generated status file;
- README links to that status file;
- architecture and user docs avoid duplicating the numbers;
- CI fails if generated status is stale.

### D2. Support claims are stronger than the verification model

Files such as `README.md`, `ARCHITECTURE.md`, and the user guide contain POSIX
or compatibility percentages and status claims. Examples include:

- `README.md:7`
- `ARCHITECTURE.md:1175`
- `docs/user_guide/01_introduction.md:14`
- `docs/user_guide/17_differences_from_bash.md:7`

Because POSIX conformance is not currently separated from default Bash
comparison, these claims are too strong.

#### Recommendation

Replace broad percentages with a support matrix:

| Feature | Status | Oracle | Test file | Known gaps |
| --- | --- | --- | --- | --- |
| POSIX parameter expansion | Supported / partial / unsupported | POSIX citation, dash, or `bash --posix` | Path | Notes |
| Bash arrays | Supported / partial / unsupported | Bash | Path | Notes |

This is more maintainable and more honest than a single percentage.

### D3. Some user-facing docs are stale

Examples:

- `docs/user_guide/01_introduction.md:52` uses a placeholder clone URL.
- `docs/user_guide/17_differences_from_bash.md:7` contains stale version/status
  language.
- `docs/user_guide/17_differences_from_bash.md:626` and nearby sections contain
  stale status references.

These are easy to miss because the docs are readable. The failure mode is not
bad prose; it is outdated facts.

#### Recommendation

Add a documentation freshness check for:

- placeholder domains and usernames;
- stale version strings;
- repeated test-count phrases;
- support percentages;
- “current status” blocks outside the generated status source.

### D4. Subsystem documentation contains obsolete architecture references

`docs/subsystem_internals.md` references structures that no longer match the
current tree. Examples include obsolete references to:

- `psh/lexer/state_machine.py`;
- `psh/ast_nodes.py`;
- outdated lexer size and architecture descriptions.

Representative locations:

- `docs/subsystem_internals.md:107`
- `docs/subsystem_internals.md:255`
- `docs/subsystem_internals.md:706`

The current AST nodes live under `psh/ast_nodes/`, not a monolithic
`psh/ast_nodes.py`.

#### Recommendation

Either regenerate this document from the current source layout or mark it as a
historical design note. Do not leave stale architecture prose in the active docs
tree without a warning.

### D5. Review index is stale

`docs/reviews/README.md:42` identifies an older ground-up appraisal as the
latest, even though later review files exist.

#### Recommendation

Treat the review index as generated or semi-generated:

- list review files by date;
- mark historical reviews explicitly;
- identify the current canonical appraisal for each subsystem;
- fail CI if the index omits newer review files.

## CI and Workflow Findings

`.github/workflows/tests.yml` exists but is configured for manual dispatch only.
The comments indicate that PR gating was intentionally disabled. The nightly
workflow runs broader validation, but the current workflow structure does not
make the core quality gate obvious from the repository alone.

The nightly workflow also duplicates some conformance work and does not appear
to run the full static/documentation quality set as a single clearly named
release gate.

#### Recommendation

Publish a clear CI contract:

- PR gate: quick or standard suite, plus lint/tooling checks.
- Nightly gate: full suite, full conformance, performance, coverage.
- Release gate: same as nightly, plus generated status verification.

Make the README and `docs/testing_source_of_truth.md` describe exactly those
same gates.

## Writing Quality Assessment

The best documentation is clear and pragmatic. The problem is that it frequently
mixes current facts, historical status, implementation commentary, and marketing
claims in the same documents.

For textbook-quality writing:

- user docs should say what users can rely on today;
- developer docs should state invariants, architecture, and extension points;
- historical reviews should be clearly marked as historical;
- generated facts should not be hand-maintained;
- claims should include their proof source.

The writing should move from promotional language to contract language. For
example, instead of:

> POSIX support is approximately 98%.

Use:

> The POSIX arithmetic expansion matrix has 42 cases. PSH passes 40, fails 1,
> and marks 1 unsupported. The oracle is `dash` plus the cited POSIX section.

That is less flashy and much more useful.

## Recommended Improvement Plan

### Phase 1 — Make claims honest

1. Split POSIX, Bash, and PSH-defined conformance categories.
2. Remove or qualify support percentages until generated from a defined matrix.
3. Convert assertion-free conformance probes into assertions, `xfail`s, or
   exploratory tests.
4. Fix contradictory README and user-guide test counts.
5. Update stale version, repository URL, and status references.

### Phase 2 — Make the gates match the docs

1. Define `quick`, `standard`, and `full` validation commands.
2. Make `run_tests.py --quick` genuinely small.
3. Decide whether performance belongs in full validation only or also in the
   default pytest path.
4. Update CI workflows to use the same gate names as the docs.
5. Add generated status verification.

### Phase 3 — Harden reliability

1. Add interrupt-safe cleanup to `run_tests.py`.
2. Enforce subprocess timeouts through helpers and tooling tests.
3. Fix fixtures that mutate `state.variables`.
4. Add a tooling test to ban direct `state.variables` mutation.
5. Expand flaky/interactive test documentation with exact CI status.

### Phase 4 — Raise documentation to textbook quality

1. Create one generated project-status document.
2. Replace broad support claims with feature matrices.
3. Archive or mark stale historical architecture/review docs.
4. Add all-doc Markdown and anchor checking, not just selected files.
5. Add executable or scanned examples for testing-guide snippets.

## Checks Run

The appraisal included these targeted checks:

```text
python -m pytest tests/unit/tooling -q
ruff check tests
python -m pytest tests/conformance/test_claims_have_tests.py -q
python -m pytest -o addopts='' tests/performance -q
python -m pytest tests/ --collect-only -q -p no:cacheprovider
python -m pytest tests/system/interactive --collect-only -q -p no:cacheprovider
```

Results:

- tooling tests: passed;
- Ruff over `tests`: passed;
- conformance claim tests: passed;
- performance tests: 8 passed, 1 xfailed;
- full pytest collection: 14,176 items;
- interactive collection: 96 items;
- local Markdown link scan: no meaningful broken local links found beyond false
  positives.

The passing tooling tests are useful, but they should not be interpreted as
proof that the documentation is fully current. They currently check selected
documents and selected claim patterns, while the drift is distributed across
README, architecture docs, user docs, review indexes, and testing guidance.

## Bottom Line

The tests and docs are good enough to support serious development, but not yet
good enough to support strong public claims without qualification.

The repository should prioritize truth-preserving infrastructure:

- generated status facts;
- precise conformance categories;
- assertion-bearing tests;
- honest validation gates;
- timeout-safe subprocess policy;
- current docs with historical material clearly separated.

Once those are in place, the existing breadth of the suite will become a much
stronger asset because the documentation and the tests will reinforce each other
instead of occasionally contradicting each other.
