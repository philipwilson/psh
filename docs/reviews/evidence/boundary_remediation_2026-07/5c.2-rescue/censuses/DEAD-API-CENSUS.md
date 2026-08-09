# Slot 5C.2 — zero-witness dead-API censuses

**Committed BEFORE the deletions they justify** (the 5B.2 `VariableAccess`
model): the evidence for a removal must be in the history independently of the
removal, so a reviewer can judge the census without reading the diff that
relies on it.

Measured at base `3a3e0782` (v0.777.0 + 5C.1 addendum). Instruments and their
transcripts are in `../instruments/`. Every count below is pasted from executed
instrument output.

---

## Method, and its declared bias

A member is a DEAD CANDIDATE when it has **zero production references** in
`psh/` outside its own definition.

`A11_dead_public_api.py` counts references **generously** — attribute access
`.name` *without* requiring a following `(`, so property reads and callbacks
count, plus any quoted-string occurrence, so registry / `getattr`-by-literal
dispatch counts. Generosity biases the instrument **against** finding deadness,
which is the correct direction for a census that authorises deletion.

**Demonstrated false-negative (the control):** A11 does **not** flag
`IOManager.with_redirections`, because a *docstring* in
`psh/executor/command.py:108` contains the text `io_manager.with_redirections`.
So A11's finds are high-confidence and **its non-finds prove nothing**. Precise
call-site discrimination is `A8_dead_api_census.sh`'s job.

**NOT SCANNED** (declared, so no silent coverage claim): free functions,
non-manager classes, builtins, the lexer/parser/visitor trees, `tools/`, and any
member name assembled by string concatenation at runtime.

---

## 1. `IOManager.with_redirections` — D-4B.4-s3

Definition: `psh/io_redirect/manager.py:398`.

| cell | value |
|---|---|
| occurrences of the string in ALL tracked files (denominator) | **146** |
| of those, the DIFFERENT symbol `_execute_builtin_with_redirections` | **43** |
| attribute-call sites `.with_redirections(` in `psh/` + `tests/` + `tools/` | **0** |

The only `.with_redirections(` matches repo-wide are prose in `docs/` and two
Checkpoint-R probe scripts that *grep for* the name.

**Structural finding (the justification in one paragraph).**
`with_redirections` (`psh/io_redirect/manager.py:398-424`) and the live
`guarded_redirections` (`psh/io_redirect/manager.py:427-`) carry the SAME six
invariants, line for line: `process_sub_handler.scope()`,
`_scoped_input_cursors`, `apply_redirections` → `saved_fds`,
`alias_dup_input_cursors`, `_swap_closed_output_streams`, and
`finally: stream_restore(); restore_redirections(saved_fds)`. The only
difference is guarded's `except OSError` → bash diagnostic. Deleting the dead
twin therefore removes **no invariant the live twin does not carry**, and the
live twin has **9 call sites** (measured, definition excluded).

**Post-delete invariant coverage** (named, not asserted):

- `tests/unit/io_redirect/test_input_cursor_registry_4b4.py::TestFrames::test_frame_hides_the_outer_cursor_and_restores_it`
- `tests/unit/io_redirect/test_input_cursor_registry_4b4.py::TestFrames::test_apply_time_scoped_fd_does_not_dangle_after_pop`
- `tests/unit/io_redirect/test_input_cursor_registry_4b4.py::TestFrames::test_pop_drops_the_frames_own_cursor`
- `tests/unit/io_redirect/test_input_cursor_registry_4b4.py::TestFrames::test_frames_nest`
- `tests/unit/io_redirect/test_procsub_ownership.py::test_redirect_plan_owns_both_transfer_and_close`
- `tests/unit/io_redirect/test_procsub_ownership.py::test_builtin_procsub_read_does_not_leak_fds`
- `tests/unit/tooling/test_input_cursor_m8_locks_4b4.py::test_mutation_is_caught_for_its_own_reason`
- `tests/unit/tooling/test_input_cursor_m8_locks_4b4.py::test_every_arm_anchor_is_present_in_the_real_tree`

**PROOF SHAPE: by-elimination**, with the zero-witness census as the
elimination.

---

## 2. `state.foreground_pgid` — D-5B.2-dead

Full chain at base (every citation names its file):

| role | site |
|---|---|
| storage | `psh/core/execution_state.py:28`, `:44` |
| property + setter | `psh/core/state.py:872-878` (sole production read is the getter's own body) |
| **write 1** | `psh/executor/job_control.py:358` (in `publish_foreground_pgid`, def `:348`) |
| **write 2** | `psh/executor/job_control.py:989` (hasattr-guarded clear) |
| **write 3** | `psh/executor/job_control.py:1020` (second hasattr-guarded clear) |
| caller | `psh/executor/foreground_session.py:90` |
| protocol member | `psh/protocols/__init__.py:222` (+ docstring `:227`) |
| conformance row | `tests/unit/protocols/test_protocol_conformance_q1.py:53` |
| Q2 ledger rows | `tests/unit/tooling/test_declared_field_access_q2.py:230`, `:231` (one per hasattr site) |
| direct unit tests | `tests/unit/core/test_execution_state.py:17`, `:51`, `:63` |
| test double | `tests/integration/job_control/test_stopped_job_current_marker.py:25` |
| docs | `psh/core/CLAUDE.md:846`, `psh/core/execution_state.py:3` |

**Three write sites, not two.** The campaign LEDGER row D-5B.2-dead records
`:358/:989/:1020` correctly; the slot brief listed only two.

**Zero production reads outside the getter** ⇒ no fence.

**PROOF SHAPE: revert-proven (neuter-parity), three arms**, run at base under
`B1_neuter_parity_driver.py`. Selection `tests/integration/job_control` (**392**
collected — the recorded meaning of "the 392 set"), serial, foreground:

| arm | tree state | passed | failed | rc |
|---|---|---|---|---|
| A BASE | unmodified | 392 | 0 | 0 |
| B NEUTER | all three writes disabled | **392** | 0 | 0 |
| C RED CONTROL | `_promote_to_current` no-op (`psh/executor/job_control.py:991`) | 387 | **5** | **1** |

PARITY (A == B) **YES**; arm B additionally asserted that zero
`self.shell_state.foreground_pgid` assignments remained, so the parity is not an
artefact of a missed write. SENSITIVITY **YES** — arm C went red naming
`test_stopped_job_current_marker.py` (4 of 5 failures; the 5th is the same `%+`
promotion rule via a pipeline).

Arm C deliberately targets a **different symbol**: the claim is that
`foreground_pgid` is dead, so a control seeded there could never fire and would
prove nothing. Sensitivity has to be shown on a live sibling path.

Tree restored and verified byte-identical to base after the run.

---

## 3. Four zero-witness public members (bounded census)

`A11_dead_public_api.py` over the component-manager / boundary classes
ARCHITECTURE's Quick Map names: **112 public defs scanned**.

| member | definition | production refs | test refs | git provenance (`git log -S`, `psh/` only) | class |
|---|---|---|---|---|---|
| `JobManager.get_job_by_pgid` | `psh/executor/job_control.py:493` | 0 | 0 | born `3d1ae463` (v0.9.0); **1** commit ever touched the name | never-called-since-birth |
| `JobManager.list_jobs` | `psh/executor/job_control.py:836` | 0 | 0 | born `3d1ae463`; **6** commits touched the name | **orphaned-by-refactor** |
| `FunctionManager.is_function_readonly` | `psh/core/functions.py:99` | 0 | 0 | born `c1694fe9` (v0.81.5); **1** commit | never-called-since-birth |
| `FunctionManager.clear_functions` | `psh/core/functions.py:131` | 0 | 0 | born `d2139ac8`; **1** commit | never-called-since-birth |

The sole `list_jobs` match elsewhere is a **test name**,
`tests/unit/builtins/test_disown_builtin.py:233::test_disown_list_jobs` — a
different symbol, the same trap class as
`_execute_builtin_with_redirections`, verified by hand.

**Dynamic-dispatch hand-check.** `psh/core/functions.py` contains no
`getattr`/`setattr`/`__dict__`/`eval` at all. `psh/executor/job_control.py` uses
`getattr` only with **literal** attribute names on `state` (`in_forked_child`,
`source_depth`) — never on a `JobManager` member, never concatenated. A11
already counts quoted-literal references, so registry dispatch by literal name
is covered. **Residual risk = a name built by concatenation at runtime; zero
instances in either module.**

**PROOF SHAPE: by-elimination** (census) + grep-zero pin after the delete.

---

## 4. `try_resolve_bash` — LEDGER L301

Definition `tests/harness/shell_oracle.py:287`; exported at
`tests/harness/shell_oracle.py:105`.

Every occurrence in tracked `*.py`:

| site | kind |
|---|---|
| `tests/harness/shell_oracle.py:105` | `__all__` export |
| `tests/harness/shell_oracle.py:287` | definition |
| `tests/harness/gen_census.py:16` | docstring |
| `tests/harness/gen_census.py:21` | regex **pattern string** (detects the name in other files) |
| `tests/harness/gen_census.py:25` | literal string comparison |
| `tests/unit/tooling/test_shell_oracle_harness.py:42` | import |
| `tests/unit/tooling/test_shell_oracle_harness.py:59-60` | its **own self-test** |

**Zero real consumers** — exactly the referenced-only-by-its-own-test shape
L301 describes. Oracle-harness code is HIGH-1 territory, so the census was taken
before any touch.

**PROOF SHAPE: by-elimination.** The `gen_census.py:21/:25` detection branches
are pruned in the same commit: detection branches for a spelling that no longer
exists anywhere are instrument rot in a census generator.

---

## 5. NOT a deletion — `AliasManager.has_alias`

`psh/expansion/aliases.py:36`. **0 production references, 4 test references.**

This is **test-only API, not dead code** — observed code with a consumer.
Recorded here as test-only-consumer surface and explicitly **excluded from the
delete set**: removing it would rewrite 4 test sites to a less direct spelling
for zero production gain.

---

## Path-guess correction (recorded, since it changed the denominator)

A11's first pass targeted `psh/core/aliases.py` and `psh/scripting/__init__.py`
and found neither class. Both were **my guesses, not doc drift** —
ARCHITECTURE's Quick Map correctly lists `aliases.py` inside the `expansion/`
block, and names `scripting/` as a package without claiming a file. Re-pointed
to `psh/expansion/aliases.py` and `psh/scripting/base.py`; the scanned
denominator went 100 → **112** public defs.
