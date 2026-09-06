# Flip-pin inventory — Improvement Program 2026-09

Declared-divergence pins that Wave 0.3 lands against bash **5.3.15** and that a later
slot MUST flip to an equality pin in its own diff (program §6 0.3, §8, §10 4.12; D5:
each carries `min_bash: "5.3"` / `@pytest.mark.oracle_min("5.3")` and asserts BOTH
sides' current output, so it goes red the moment either side moves). A row leaves this
table only when the owning slot flips it and names the release in `flipped in`.

Node names below are the names at `6459f1a6`; where 0.3 renames or splits a node,
package C hands the integrator the final id and the row is marked **node id to confirm**.
Two-sided values are the triage's probed outputs (`gate_triage.json`, 2026-09-06).

## Must-flip (a wave slot owns the fix)

| pin (test node) | bash 5.3.15 side | psh side (`6459f1a6`) | owner slot | flipped in |
|---|---|---|---|---|
| `tests/conformance/bash/test_exit_trap_status_precedence_conformance.py::test_bare_exit_in_a_signal_trap_still_uses_current_status` (the MUST-HOLD; 0.3 renames it `…uses_entry_status` — **node id to confirm**) | `trap 'echo entry=$?; false; exit' USR1; kill -USR1 $$; sleep 0.2; exit 3` → stdout `entry=0`, rc **0** (bare `exit` at the trap's top level takes the pre-trap `$?`; POSIX interp 1602, bash 5.3 NEWS uu / CHANGES 5.3-alpha q) | stdout `entry=0`, rc **1** (current `$?` from `false`; `psh/core/trap_manager.py:94-99` EXIT-only rule) | 2.1 |  |
| `…::test_exit_trap_status_matches_bash[disc-signal-trap-uses-current-status-command]` (cell id → `disc-signal-trap-uses-entry-status-command` — **node id to confirm**) | `entry=0` rc 0 | `entry=0` rc 1 | 2.1 |  |
| `…::test_exit_trap_status_matches_bash[disc-signal-trap-uses-current-status-script]` (→ `…-entry-status-script`, **node id to confirm**) | `entry=0` rc 0 | `entry=0` rc 1 | 2.1 |  |
| `…::test_exit_trap_status_matches_bash[disc-signal-trap-uses-current-status-stdin]` (→ `…-entry-status-stdin`, **node id to confirm**) | `entry=0` rc 0 | `entry=0` rc 1 | 2.1 |  |
| `tests/conformance/posix/test_posix_special_builtin_exit_conformance.py::TestPosixSpecialBuiltinNoExit::test_export_bad_identifier_survives` (0.3 may rename `…_exits` — **node id to confirm**) | `set -o posix; export 1bad=x; echo rc=$?` → stdout empty, shell **exits 1**, stderr ``export: `1bad=x': not a valid identifier`` (suppressible: `\|\| echo caught` continues; through `eval` and bare function calls; stripped by `command`/`builtin`; contained by a subshell) | stdout `rc=1`, exit 0 (continues) | 2.2 |  |
| `…::TestPosixSpecialBuiltinNoExit::test_readonly_bad_identifier_survives` (**node id to confirm**) | `readonly 1bad=x` → exits 1, ``readonly: `1bad=x': not a valid identifier`` (also `readonly 1bad`, `readonly é=1`; `readonly -f` operands exempt) | `rc=1`, exit 0 | 2.2 |  |
| `…::TestPosixSpecialBuiltinNoExit::test_unset_readonly_survives` (**node id to confirm**) | `readonly r=1; unset r` → exits 1, `unset: r: cannot unset: readonly variable` (same for `unset -f` on a readonly function: `cannot unset: readonly function`) | `rc=1`, exit 0; function wording `unset: f: readonly function` | 2.2 (wording half shared with 4.7) |  |
| `…::TestPosixSuppressibleExit::test_eval_boundary_not_suppressed` (0.3 pins the 5.3 shape — **node id to confirm**) | `set -o posix; eval 'set -q' \|\| echo caught; echo survived` → `caught` / `survived`, rc 0 (an OUTER guard suppresses across `eval` and `.`; HARD-class errors still exit) | stdout empty, exit 2 (`special_exit_floor` raised per nested run, `psh/scripting/source_processor.py:233-240`) | 2.2 |  |
| `tests/conformance/bash/test_identifier_policy_conformance.py::TestPosixRestrictsUnicodeLikeBash::test_declare_export_read_report_and_continue` — the `export é=1` half after the 0.3 split (new node, e.g. `test_export_readonly_unicode_exit…` — **node id to confirm**) | `set -o posix; export é=1; echo done` (UTF-8 locale) → stdout empty, exit 1, ``export: `é=1': not a valid identifier`` | prints `done`, exit 0 | 2.2 |  |
| `tests/conformance/bash/test_exit_cd_options_conformance.py::TestCdOptions::test_cd_too_many_arguments` | `cd a b; echo rc=$?` → `rc=2` (no chdir; `cd a b && echo tail` skips the tail) | `rc=1` (`psh/builtins/navigation.py:103`) | 2.3 |  |
| `…::TestExitStatus::test_exit_too_many_args_does_not_exit` | script `exit 1 2 3` / `echo after=$?` → `after=2`, process rc 0 (`-c 'exit 7 8; echo survived'` still abandons the string with rc 1 in both) | `after=1` | 2.3 |  |
| golden `bcontract_exit_bad_first_operand_exits_two` (`tests/behavioral/golden_cases.yaml`; W0-N4; 0.3 turns it into a `min_bash: "5.3"` declared-divergence row — **row name to confirm**) | `exit abc; echo rc=$?` → `rc=2` and CONTINUES (same in every mode) | exits 2 | 2.3 |  |
| `tests/conformance/bash/test_export_env_sync_conformance.py::TestExportAttributeLifecycle::test_declare_i_on_readonly_succeeds` (0.3 pins the refusal — **node id to confirm**) | `readonly R=1; declare -i R; echo rc=$?` → `declare: R: readonly variable`, `rc=1`, attribute NOT added (bash 5.3 CHANGES 5.3-alpha llllll; `-x/+x/-t/+t/-r/-g` still allowed) | rc 0, attribute added (`psh/core/scope.py#ScopeManager.apply_attribute:1290`) | 2.4 |  |
| `tests/unit/builtins/test_local_builtin.py::test_attrs_only_add_integer_allowed` (unit twin; 0.3 flips its expectation to the refusal — **node id to confirm**, e.g. `…_refused`) | `f(){ local -r x=1; local -i x; }` → `local: x: readonly variable` rc 1 | allowed | 2.4 |  |
| `tests/integration/job_control/test_pipeline_signal_death.py::TestPipelineLastMemberSignalDeath::test_sigterm_last_member_announced` (0.1 S path: `bash.stderr == strsignal(SIGTERM).ljust(27) + 'true \| sh -c "kill -TERM \\$\\$"\n'`, psh bare-form pin kept) | stderr `Terminated: 15             true \| sh -c "kill -TERM \$\$"` (27-column status field + re-printed job text) | stderr `Terminated: 15` (bare) | 4.12 (C065 job text) |  |
| `…::TestPipelineLastMemberSignalDeath::test_sigterm_no_trailing_command` (S path as above) | `Terminated: 15             echo hi \| sh -c "kill -TERM \$\$"` | `Terminated: 15` | 4.12 |  |
| `…::TestPipelineNonLastMemberSignalDeath::test_pipefail_announces_status_determining_member` (S path: `'Done'.ljust(27) + 'sh -c "kill -TERM \\$\\$" \| cat\n'`) | `Done                       sh -c "kill -TERM \$\$" \| cat` (status column shows the LAST member's label; announce decision still pipefail-driven) | `Terminated: 15` (names the status-determining member's signal) | 4.12 |  |
| `tests/integration/job_control/test_signal_killed_diagnostic.py::TestAbnormalTerminationDiagnostic::test_reported_in_explicit_subshell` (S path) | `Terminated: 15             ( sh -c "kill -TERM \$\$" )` | `Terminated: 15` | 4.12 |  |
| `…::TestAbnormalTerminationDiagnostic::test_sigterm_prints_bare_signal_description` (0.1 rewords: psh bare, bash 5.3 appends the padded job text — **node id to confirm** if renamed) | `Terminated: 15             sh -c "kill -TERM \$\$"` (pre-expansion AST re-print: whitespace collapsed, quotes verbatim, wrappers stripped) | `Terminated: 15` | 4.12 |  |

Plus (unit-level, same slots): any `tests/unit/**` twin that asserts the psh-divergent
result — the owning slot sweeps its own files (2.3: `tests/unit/builtins/test_navigation*`
/ `core.py:59-60` comment; 2.4: `test_local_builtin.py`; 2.2:
`tests/integration/test_posix_special_builtin_exit.py` SURVIVING→EXITING, golden
`posixexit_*`, matrix doc rows 48/49/51).

## Declared, NOT flipped by this program (noted; flips only with a written ruling)

| pin (test node) | bash 5.3.15 side | psh side | owner | note |
|---|---|---|---|---|
| funsub: `tests/conformance/bash/test_bad_substitution_conformance.py::TestBadSubstitutionRejected::test_rejected_cases_match_bash` loses `${ }` and `${ :-x}` from `BAD_CASES`; a NEW declared-divergence pin guarded by `oracle_feature('funsub')` (**node id to confirm**) | `echo ${ echo fs; }` → `fs`; `echo ${ }` → empty, rc 0; `echo ${ :-x}` → rc 2 `unexpected EOF while looking for matching '}'` (bash 5.3 NEWS s: `${ cmd; }` / `${\| cmd; }` function substitution) | `${ }` / `${ echo fs; }` → rc 1 `bad substitution` (no funsub support) | Park P-3 | not a program target; a pull-in needs a written ruling (§15) — the pin keeps the fact visible |
| `tests/conformance/bash/test_subscript_keying_conformance.py::test_divergence_sq_in_dq_readback_outcome` → parity pin `test_sq_in_dq_readback_round_trips` (0.1 PREMISE edit) | `declare -A h; h['$(if)']=v; echo "read=${h['$(if)']}"` → `read=v`, rc 0 (bash 5.3 CHANGES k: subscripts expanded once) | identical (`read=v`, rc 0; rd and combinator) | closed on the ORACLE side | no flip: the divergence ceased when the oracle moved; the 2026-07 KEEP ruling on the "bash cannot read its own writes" family is moot for this cell |
| `tests/conformance/bash/test_typed_expansion_errors_conformance.py::TestDeclaredDivergences::test_invalid_regex_diagnostic_is_psh_only` → both-diagnose wording pin (0.1 PREMISE edit; **node id to confirm**, e.g. `…_wording_differs`) | `[[ x =~ [ ]]` → rc 2, stderr `[[: invalid regular expression …: brackets ([ ]) not balanced` (bash 5.3 NEWS g) | rc 2, stderr `psh: [[: invalid regex: unterminated character set at position 0` | wording stays declared; W0-N3 (`a{1` rc 1 vs 2) → 4.6 | status parity holds; only wording differs |

## Inherited must-NOT-flip rows

The 2026-07 campaign's sanctioned divergences
([`../boundary_remediation_2026-07/FLIP-PINS.md`](../boundary_remediation_2026-07/FLIP-PINS.md)
"Must-NOT-flip" and the per-slot declared tables) stay in force. Slot 4.13 closes the
2026-07 LEDGER Part D successor rows it names (C067/C124/C182/C183/C184/C185) with pins;
any other inherited declared pin that a program slot wants to flip needs a ruling in
`LEDGER.md` Part D first — never a silent edit.
