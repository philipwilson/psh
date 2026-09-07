# Improvement Program Feedback

Date: 2026-09-06.

Reviewed plan: [Improvement Program 2026-09](improvement_program_2026-09-06.md). Section and line references identify the revision reviewed; this feedback does not launch or amend the program.

**I would approve the direction, but not launch this exact revision.** The harm ordering and actual-effect tests are sound; several prescriptions need correction.

## Findings

### 1. [P1] The proposed arithmetic reset introduces regressions

[Slot 3.4](improvement_program_2026-09-06.md#L204) resets arithmetic depth on every newline/semicolon, including valid C-style `for` headers. I tested that change in memory:

```sh
for ((i=0; i<<2; i++)); do :; done
```

This currently parses and succeeds in Bash, but the reset reclassifies `<<` as a heredoc and causes a parse error. Recovery must distinguish malformed constructs from valid arithmetic boundaries.

### 2. [P2] Two required numeric-error statuses are wrong

[Slot 1.14](improvement_program_2026-09-06.md#L152) specifies status **2** for `read -t inf` and an oversized `read -u` operand. I reran both against the pinned Bash 5.3.15: both return **1**. Correct these acceptance criteria before implementation.

### 3. [P2] The oracle check will not produce the promised single failure

[D1](improvement_program_2026-09-06.md#L45) adds a failing unit test, but other conformance tests would still execute and potentially fail too. Make oracle validation a gate preflight, before the test phases. Also reconcile the exact-5.3.15 contract with the explicitly permitted patch-version drift.

### 4. [P2] Do not turn an internal invariant failure into an ordinary syntax error

[Slot 3.2](improvement_program_2026-09-06.md#L202) proposes converting the lexer's no-progress guard to `LexerError`. Fix the recognizer's handling of malformed input, but retain a loud internal guard when no recognizer advances. Otherwise strict-errors testing can mistake a new implementation defect for successful input rejection.

### 5. [P2] Tighten the milestone accounting

[Wave 0](improvement_program_2026-09-06.md#L123) requires matching local/Linux censuses while deliberately adding Linux-only skips. Require an explained platform delta instead. Similarly, [slot 1.0](improvement_program_2026-09-06.md#L138) creates expected failures owned by Wave 4; Wave 1's exit criteria should explicitly permit those.

## Engineering Judgment

The strongest parts are the single inventory, explicit treatment of divergences, tests of actual destinations and consumed input, and independent adversarial verification. Those address the appraisal's central concerns.

My larger concern is **over-prescription**. Some requirements specify implementation spelling before establishing the complete invariant. For example, the [IFS literal ban](improvement_program_2026-09-06.md#L157) must distinguish `DEFAULT_IFS` from the broader whitespace classification: those are different rules. Structural guards should enforce ownership without forcing unrelated semantics into one helper.

Finally, **75 releases and 101 dev-days are a roadmap, not yet a dependable estimate**. Verification rounds, rebases, and integration need their own allowance. I would make the proposed checkpoint after Wave 3 mandatory, then reauthorize and estimate Waves 4-6 from the resulting tree. Keep later implementation sketches provisional.

The plan was left unchanged during this review.
