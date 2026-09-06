# Validation Record

Date: 2026-09-06. Production revision: `6459f1a6e48b9f2cee4cda6d3b778f65ea2a417f`, v0.779.0.

Host: macOS, Python 3.14.7. Oracle: `/opt/homebrew/bin/bash`, `5.3.15(1)-release`. Full runtime identification is also the first record of `observations.jsonl`.

## Canonical Gate

Exact command:

```sh
python run_tests.py --parallel 4 --results-file /tmp/psh-appraisal-2026-09-06-tests.txt > /tmp/psh-appraisal-2026-09-06-runner.txt 2>&1
```

Completed with exit status 1. The retained [canonical-tests.txt](canonical-tests.txt) contains the full phase output and all failed test identifiers.

| Phase | Passed | Failed | Skipped | Xfailed | Time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Regular, 4 xdist workers, `not serial and not benchmark` | 22,884 | 37 | 1,630 | 8 | 570.01 s |
| Serial, `serial and not benchmark` | 1,101 | 15 | 1 | 2 | 477.27 s |
| Combined manifest result | 23,985 | 52 | 1,631 | 10 | |

Both phases completed without timeout or collection error. These are the original run's results; targeted reruns below do not retroactively make that gate green. No production changes were made before or after it.

The standard serial phase includes actual PTY smoke, heredoc, immediate-error, shutdown, signal, and timed-input tests. It is not the entire opt-in interactive matrix. Neither `--benchmarks`, `--compare-bash`, nor `--coverage` was requested; ordinary conformance tests still compare against live Bash within the standard phase.

## Failure Triage

Four failures passed when explicitly rerun outside the filesystem/process sandbox:

- `TestExecutableSpecialFileEarlier::test_socket_earlier_bash_126_psh_runs_later`: initial Unix-domain socket bind raised `PermissionError`.
- `test_cap_kill_reaches_a_writer_that_left_the_process_group`: initial process-discovery/cleanup probe failed; the test's own final cleanup kills the writer before raising.
- Golden case `r18t2_builtins_history_write_to_stdout`: initial `/dev/stdout` output mismatch.
- `test_bg_actually_resumes_a_job_stopped_behind_the_shells_back`: initial `ps`-based precondition reported no state; the unsandboxed rerun established the stopped child and passed the resumption assertions.

Exact rerun commands:

```sh
python -m pytest -q tests/conformance/bash/test_cv_carry_characterization.py::TestExecutableSpecialFileEarlier::test_socket_earlier_bash_126_psh_runs_later tests/unit/tooling/test_shell_oracle_harness.py::test_cap_kill_reaches_a_writer_that_left_the_process_group tests/behavioral/test_golden_behavior.py -k 'socket_earlier or cap_kill_reaches or history_write_to_stdout'
python -m pytest -q tests/integration/job_control/test_bg_resume_refreshes_state.py::test_bg_actually_resumes_a_job_stopped_behind_the_shells_back
```

Results: **3 passed, 1 skipped, 3,070 deselected**; then **1 passed**.

One failure is pre-existing workspace metadata: `test_every_review_file_is_indexed` identifies the untracked `ground_up_reappraisal_23_correctness_textbook_2026-08-09.md`. That file was present before the appraisal and was left unchanged. The new report is indexed.

The remaining 47 failed test cases were inspected through their diagnostics, but were not individually rerun against a pinned Bash 5.2 installation. They are not 47 independent established PSH bugs. Examples of distinct triage categories:

| Category | Examples from the transcript | Interpretation |
| --- | --- | --- |
| Exact formatting/usage mismatch | `shopt` padding, `jobs` padding, `trap [-Plp]` versus `trap [-lp]` | Observed against Bash 5.3; separate output presentation from semantic differences and explicitly version the intended oracle. |
| Behavior/status mismatch | POSIX special-builtin exits, signal-trap exit status, completed-job listing in `-c`, `hash -d` for an absent command | Require deliberate compatibility decisions and pinned-version verification; do not dismiss them as whitespace. |
| Changed oracle expectation in characterization tests | `${ }` rejection, associative subscript readback, invalid-regex diagnostics | Some tests assert properties of Bash itself or retained divergences. A mismatch can mean the recorded oracle premise changed. |
| PSH-only serialized-output expectation | Process-substitution case-statement rendering | A snapshot mismatch must be checked for semantic loss versus harmless formatting; the independent F03 probe establishes a separate real semantic loss. |
| Platform/startup/error presentation | Closed fd 0, explicit empty PATH error wording | Keep platform and intended compatibility behavior explicit. |

No claim is made that all remaining failures disappear with Bash 5.2. The user-visible semantic defects in the main report have their own small reproductions or fault-injection observations rather than being inferred from this count.

## Static Checks and Review Artifacts

```sh
ruff check psh tests tools
mypy
ruff check psh tests tools docs/reviews/evidence/fresh_appraisal_2026_09_06/probes.py
python -m pytest -q tests/unit/tooling/test_reviews_index.py
git diff --check
```

Both Ruff invocations passed; mypy passed for 276 source files. The index module rerun produced **2 passed, 1 failed**, with only the same pre-existing untracked review file missing from the index. Whitespace checking passed. New report/evidence Markdown links were checked against local files.

The evidence script was import-sorted and formatted with Ruff. It is an observation runner, not a regression suite that asserts the current defects are desirable.

```sh
python docs/reviews/evidence/fresh_appraisal_2026_09_06/probes.py > docs/reviews/evidence/fresh_appraisal_2026_09_06/observations.jsonl
```

Result: exit status 0, 65 JSON records. There are 37 differential cases, with 15 stdout/status mismatches; additional records capture formatter round trips, resource faults, terminal helpers, static analysis, and lexer CPU samples. All outcomes and stderr remain available for inspection. The finite corpus is intentionally discriminating, not a statistical estimate of overall shell compatibility.

No fresh coverage report, Linux execution, full benchmark tier, or extended randomized parser run was performed. Historical coverage and campaign attestations are not substituted for those missing checks.
