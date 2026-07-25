# Oracle-migration census (remediation slot 1.2, campaign HIGH-1)

**Frozen at:** base `e52957d4` (v0.751.0), the tip of slot 1.1's merge.
**Oracle:** PATH bash `/opt/homebrew/bin/bash` `5.2.26(1)-release` (never `/bin/bash`).
**Purpose:** freeze the offender list BEFORE any migration so the batches are
mechanical and auditable. This file is the authority the anti-spawn guard
(`tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py`) and its
allowlist trace back to.

Reappraisal #22 HIGH-1 is two defects: (1) the oracle could classify two
harness failures as IDENTICAL conformance (fixed structurally in slot 1.1 —
typed `ShellRunResult` + `is_comparable`), and (2) ~30 differential modules
BYPASS the runner entirely by spawning bash/psh with raw `subprocess`, so the
1.1 safety net never sees them. This slot closes (2): every differential
launch in the guard-bearing set routes through `run_shell_case`, enforced by a
static guard.

## Method / enumeration commands (replayable at the base SHA)

```
# (a) every module under tests/ with a direct process spawn
grep -rlE 'subprocess\.(run|Popen|call|check_output|check_call)|os\.system|os\.popen' \
     tests/ --include='*.py' | sort | wc -l        # -> 294

# (b) the shell_oracle import surface — see the three-measure table below;
#     the authoritative form is the SHA-pinned pathspec, NOT a cwd grep:
git grep -l 'shell_oracle' e52957d4 -- tests/ | wc -l              # -> 108 files

# (c) the guard-bearing set + spawner subset, by the guard's OWN AST predicates:
python tests/harness/census_replay.py <tree>/tests   # -> 181 / 182 / 96 / 245 (see below)

# per-module + per-spawn-site classification (bash / psh / python / var-argv):
python tests/harness/gen_census.py   # AST walk: resolves each module's
#   bash-path variable, labels every subprocess argv[0] by what it launches
```

`os.system` / `os.popen`: **zero** occurrences in the guard-bearing set (the
E2 resolution ratchet already forbade them).

**CORRECTION (round 3).** This section previously claimed "PTY / `os.fork` /
`pexpect`: **zero** in the migration set" — that claim was FALSE and rested on
no enumeration command. Verification found a PTY bash-differential sitting
inside the bearing set. The corrected, ENUMERATED position:

```
# non-subprocess process creation (pexpect / pty / os.fork|posix_spawn|exec*)
# across the BEARING SET — the family a subprocess-only scan cannot see:
python tests/harness/census_replay.py <tree>/tests     # census + pty_audit
```

At base `e52957d4` that audit prints exactly **2 sites in 1 module**:

```
system/interactive/test_multiline_immediate_error_i3.py:78: pexpect.spawn
system/interactive/test_multiline_immediate_error_i3.py:92: pexpect.spawn
TOTAL non-subprocess spawn sites in the BEARING SET: 2
```

confirming that module is the **SOLE** instance. (At tip the audit additionally
lists the two deliberate offender FIXTURES under `oracle_spawn_fixtures/`, which
exist to prove each guard face fires.)

**PTY-INFRA class** — `tests/system/interactive/test_multiline_immediate_error_i3.py`:
oracle-bearing (`from shell_oracle import try_resolve_bash`), it drives psh AND
the resolved bash oracle through `pexpect.spawn` over a pseudo-terminal
(`TERM=xterm`) and compares the LINE INDEX at which each reports a mid-construct
syntax error. It is a genuine bash differential but is **NOT migrated**: PTY
interactivity IS its subject, and the run-to-completion runner has no terminal.
It is CLASSIFIED and REGISTERED in the guard's `PTY_REGISTRY` (owner + reason +
removal condition, frozen membership pin, and its own hygiene test keyed on the
PTY detector rather than the subprocess one) — registration is what keeps it
visible. Its `try_resolve_bash()` + in-test `pytest.skip` silent-skip is left
as-is and carried to slot 1.3 with the other pre-existing silent-skip modules.

The interactive-family rows that ARE migrated (`bash -i`,
`test_history_p_interactive`) never needed a PTY: they drive the shell with a
**stdin pipe + `TERM=dumb`**, which `run_shell_case(..., stdin_data=...,
stdin_mode='pipe')` serves directly.

## Census (a) — direct spawns tree-wide

- **294** modules call `subprocess.*` directly. The overwhelming majority spawn
  **only psh** (`python -m psh …`) for legitimate non-differential reasons
  (fd-isolation, permanent-`exec` redirection that must not rewrite the test
  runner's own fds, process-lifecycle). Those are **PSH-ONLY, out of scope for
  the oracle contract**: they never compare two shells, so HIGH-1's false-green
  cannot arise, and they are not oracle-bearing (they do not import
  `shell_oracle`). They keep their direct `subprocess` calls.
- The oracle contract governs only the **guard-bearing set** (below).

## Census (b) — shell_oracle import surface

Three DIFFERENT measures, each stated explicitly (round-1 verification flagged
the original bare "107" as ambiguous). All at base `e52957d4`:

| Measure | Count | How |
|---|---|---|
| Files MENTIONING `shell_oracle` (textual, incl. docstrings) | **108** | `git grep -l 'shell_oracle' e52957d4 -- tests/` |
| Files with a REAL import (AST `Import`/`ImportFrom`) — the runtime surface | **105** | AST walk (the guard's `_imports_shell_oracle`) |
| Import-STATEMENT lines | **102** | `git grep -hE '^\s*(from .*shell_oracle import\|import .*shell_oracle)' e52957d4 -- tests/` |

The 3-file gap (108 − 105) is docstring/comment/string mentions only. The
earlier single figure **107** was a grep of import-*like* lines: it matched
in-string references while missing other mentions, so it equals neither the file
set (108) nor the runtime surface (105) — superseded by this table.

By imported symbol (import statements):

| Import | Count |
|---|---|
| `from shell_oracle import resolve_bash` | 85 |
| `from shell_oracle import try_resolve_bash` | 4 (+2 noqa) |
| `from shell_oracle import Completed, hermetic_shell_env, run_shell_case, try_resolve_bash` | 4 |
| `from shell_oracle import Completed, hermetic_shell_env, resolve_bash, run_shell_case` | 3 |
| `from shell_oracle import (` multi-line | 3 |
| `from shell_oracle import resolve_bash` (noqa) | 2 |
| relative/absolute-path variants (`tests.harness.`, `harness.`) | 2 |
| in-string / comment references (not runtime imports) | 4 |

## Guard-bearing set (the anti-spawn guard's scope) — AST measures, replayable

**Structural definition (what the guard actually implements):** a module is
*oracle-bearing* iff it really IMPORTS `shell_oracle` (AST `Import`/`ImportFrom`
— not a docstring mention) **or** lives under `tests/conformance/` **or** under
`tests/harness/`.

**Replay command** (this is the authority; it re-derives every number below at
any SHA):

```
rm -rf tmp/basetree && mkdir -p tmp/basetree \
  && git archive e52957d4 tests | tar -x -C tmp/basetree \
  && python tests/harness/census_replay.py tmp/basetree/tests
```

Output at base `e52957d4`:

| Set | Modules | Spawners | Non-spawners | Spawn sites |
|---|---|---|---|---|
| imports ∪ conformance | **181** | 95 | 86 | — |
| **guard scope** (that ∪ `harness/`) | **182** | **96** | 86 | **245** |

The guard's scope is the **182**-module set. Its 96 spawners are
`harness/shell_oracle.py` (the runner itself, 2 sites: the `Popen` plus the
`_bash_version` probe) **plus the 95 migration targets with 243 sites** — the
per-module table below. Containment is exact: census-95 == guard-scope spawners
− `shell_oracle.py`, and 245 − 2 == 243.

**Superseded measure (kept only to explain an earlier figure):** an earlier
draft counted *textual mentions* ∪ conformance and reported **183 / 88 / 95**.
That set is not what the guard scans (it counts docstring mentions and omits
`harness/`), and 183 was moreover a TIP-time count printed against the frozen
base. The AST numbers above supersede it; the spawner subset (95) is unchanged
either way, which is why the target list never moved.

Within the guard-bearing set every differential run needs BOTH sides typed
(HIGH-1: a runaway psh is as dangerous as a runaway bash), so the migration
routes **bash, psh, and python-helper spawns alike** through `run_shell_case`.
Note the scoping distinction used throughout this file: **"95/95 differential"
describes the SPAWNER SUBSET**, not the 182-module bearing set (most bearing-set
modules never spawn directly at all — they go through the framework).

### PRIMARY CLASSIFICATION — differential vs psh-only (integrator ruling)

The migration set is the **BASH-DIFFERENTIAL** class ONLY (tree-wide, not
conformance-only): a module that spawns bash — directly, via a var-argv helper
parameterised over psh+bash, or via the `ConformanceTest` framework — to COMPARE
behavior. A **PSH-ONLY** module (launches only psh, no bash comparison — the
`subprocess.run([sys.executable, '-m', 'psh', ...])` lifecycle/fd/exec pattern
sanctioned by CLAUDE.md) is NOT this slot's defect (it cannot produce a false
IDENTICAL) and is NOT migrated; a psh-only raw spawner in scope would instead be
frozen in the anti-spawn guard's shrink-only PSH-ONLY registry.

**The split of the 95 spawner modules (verified per-module, not assumed):**

**MODULE class vs SPAWN-SITE class — read the two tables with this distinction**
(round-1 verification flagged the apparent contradiction): the classification
that governs scope is per MODULE. A module is BASH-DIFFERENTIAL if it compares
psh against bash *anywhere* (directly, via a var-argv helper, or via the
`ConformanceTest` framework). Two such modules additionally contained ONE
psh-only SPAWN SITE each — a byte/mode check bash cannot mirror inside an
otherwise bash-comparing module. The per-module table below therefore tags them
`PSH-ONLY-SITE`, meaning "differential module, psh-only site", NOT "psh-only
module". Neither is a PSH-ONLY MODULE, so the module-level count of psh-only
modules is 0.

| Class (per MODULE) | Count | Breakdown | Disposition |
|---|---|---|---|
| **BASH-DIFFERENTIAL** | **95 (all)** | 36 conformance + 59 shell_oracle importers | migrate (both sides) to the runner |
| **PSH-ONLY** | **0** | — | (would be registered, not migrated) |

(of which **2** differential modules carry a psh-only *spawn site*:
`test_ansi_c_control_escape_conformance.py`, `test_keyword_word_boundary_conformance.py`
— both otherwise drive `ConformanceTest` bash comparisons; their psh-only sites
were migrated too, for uniformity and to satisfy the guard.)

Every one of the 59 non-conformance importers references bash (`run_bash` /
`resolve_bash` / a `[BASH …]` argv) — none is psh-only. So the bearing set is
**100% differential**, and the guard's PSH-ONLY registry is **empty**. The
CLAUDE.md psh-only lifecycle pattern DOES exist tree-wide (**70 modules**), but
every one is OUTSIDE the bearing set (does not import `shell_oracle`, not under
conformance) and so was never in the guard's scope, never a migration or
registry candidate.

**Reconciliation of the "~30" vs 95 framing** (kept here per the ruling so the
next reader need not re-derive it): the v0.749 audit's "~30" is the
`tests/conformance/` bash-differential subset (36 direct-spawn conformance
modules here, ~30 excluding meta/psh-only-site). The full guard-bearing
migration set is ~3× that because the other 59 differential callers live in
`tests/integration|system|unit` as `shell_oracle` importers — a differential
caller in `tests/system` carries the same HIGH-1 false-green risk as one in
`tests/conformance`. A10's "thousands of cases" (95 modules × ~30 cases) fits
the tree-wide set.

### Allowlist (anti-spawn guard) — two parts

**(a) NAMED (harness + genuinely un-runnerable), 4 entries:** the harness
(`shell_oracle.py`, owns the one real `Popen`) plus three DIFFERENTIAL harnesses
the run-to-completion runner cannot express — `test_exit_trap_paths.py`
(mid-run signal to a running psh AND bash), `test_script_input_sources.py`
(concurrent bash fifo writer), `test_stdin_startup_robustness.py`
(`preexec_fn=os.close(0)` / live file object). Each carries owner + reason +
removal. Membership is pinned literally in the guard
(`_EXPECTED_NAMED_ALLOWLIST`), so growth is a visible two-place change.

`test_stdin_script_lazy_read.py` (pipe vs seekable-file stdin) WAS a fifth
entry and has since **left the allowlist**: its recorded removal condition —
"the runner gains a non-seekable/pipe stdin mode" — was met by
`run_shell_case(..., stdin_mode='pipe'|'file')`, so the module migrated fully
and the guard shrank. That is exactly the lifecycle
`test_allowlist_entries_still_spawn` forces.

**Outcome arithmetic (95 migration targets):** **92 migrated + 3 allowlisted**.
`shell_oracle.py` is the 4th ALLOWLIST entry but was never a migration target
(it is the runner, and has no `shell_oracle` import of its own) — so
allowlist entries (4) ≠ allowlisted targets (3).

**(b) FROZEN PSH-ONLY REGISTRY: empty** — no psh-only raw spawner exists in the
bearing set (see split above). The structure is kept for future debt.

**Two "special case" modules RULED runner-capable and fully migrated (not
allowlisted):**

- `tests/system/test_read_malformed_bytes_i1.py` (brief's known special case):
  raw-byte comparison. `run_shell_case` captures bytes losslessly (UTF-8 +
  `surrogateescape`); `Completed.stdout.encode("utf-8", "surrogateescape")`
  recovers the exact bytes. Its "decoded-text policy would hide byte-level
  facts" comment predated the surrogateescape capture and is corrected.
- `tests/integration/redirection/test_std_fd_lease_f2.py`: its `python -c`
  fd-harness runs its fd operations in its OWN process; with `close_fds` the
  child sees only fds 0/1/2 exactly as under raw subprocess, so the fd-lease
  facts survive the runner. **Branch taken: migrated** (not allowlisted); the
  exec/CLOEXEC differential also routes through `run_psh`/`run_bash`.

### Migration targets (95 modules, 243 spawn sites)

By top directory: conformance 36, integration 35, system 12, unit 12.

| Module | Class | # spawns | spawn kinds |
|---|---|---|---|
| tests/conformance/bash/test_ansi_c_control_escape_conformance.py | PSH-ONLY-SITE | 1 | psh×1 |
| tests/conformance/bash/test_bad_substitution_conformance.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/conformance/bash/test_compound_in_pipeline_conformance.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/conformance/bash/test_cv_carry_characterization.py | BASH-DIFFERENTIAL | 5 | bash×2, psh×2, var×1 |
| tests/conformance/bash/test_declare_attributes_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_dollar_zero_conformance.py | BASH-DIFFERENTIAL | 5 | psh×2, bash×2, var×1 |
| tests/conformance/bash/test_error_prefix_conformance.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/conformance/bash/test_exec_error_message_conformance.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/conformance/bash/test_exit_cd_options_conformance.py | BASH-DIFFERENTIAL | 6 | psh×3, bash×3 |
| tests/conformance/bash/test_function_def_pipeline_component_conformance.py | BASH-DIFFERENTIAL | 4 | var×4 |
| tests/conformance/bash/test_heredoc_transaction_conformance.py | BASH-DIFFERENTIAL | 4 | psh×2, other×2 |
| tests/conformance/bash/test_history_expansion_conformance.py | BASH-DIFFERENTIAL | 1 | bash×1 |
| tests/conformance/bash/test_history_outcomes_i4.py | BASH-DIFFERENTIAL | 3 | psh×1, bash×1, var×1 |
| tests/conformance/bash/test_history_p_interactive_conformance.py | BASH-DIFFERENTIAL | 1 | other×1 |
| tests/conformance/bash/test_identifier_policy_conformance.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/conformance/bash/test_keyword_word_boundary_conformance.py | PSH-ONLY-SITE | 1 | psh×1 |
| tests/conformance/bash/test_nested_substitution_timing_conformance.py | BASH-DIFFERENTIAL | 5 | psh×2, bash×2, var×1 |
| tests/conformance/bash/test_nounset_arithmetic_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_nounset_array_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_nounset_operators_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_parse_continuation_s4_conformance.py | BASH-DIFFERENTIAL | 3 | var×3 |
| tests/conformance/bash/test_reappraisal6_builtin_state_conformance.py | BASH-DIFFERENTIAL | 4 | psh×3, bash×1 |
| tests/conformance/bash/test_reappraisal6_redirect_errors_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_reappraisal7_ambiguous_redirect_conformance.py | BASH-DIFFERENTIAL | 9 | psh×7, bash×2 |
| tests/conformance/bash/test_reappraisal7_close_output_fd_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_reappraisal7_syntax_errors_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_set_o_history_conformance.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/conformance/bash/test_set_options_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_signal_listing_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_subscript_keying_conformance.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/conformance/bash/test_syntax_template_timing_conformance.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/conformance/bash/test_trap_flags_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_trap_signal_spec_conformance.py | BASH-DIFFERENTIAL | 4 | psh×2, bash×2 |
| tests/conformance/bash/test_user_guide_notes_conformance.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/conformance/bash/test_variable_projection_reads_conformance.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/conformance/test_claims_have_tests.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/integration/command_resolution/test_exec_failure_wording.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/control_flow/test_loop_control_scope_boundary.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/control_flow/test_tier3_executor_fixes.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/functions/test_funcnest.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/functions/test_recursion_depth.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/job_control/test_bg_child_trap_discipline.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/integration/job_control/test_debug_err_traps.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/job_control/test_exit_trap_paths.py | BASH-DIFFERENTIAL | 4 | psh×2, bash×1, var×1 |
| tests/integration/job_control/test_jobs_completed_listing_modes.py | BASH-DIFFERENTIAL | 5 | bash×2, psh×2, var×1 |
| tests/integration/job_control/test_pending_signal_trap_eof.py | BASH-DIFFERENTIAL | 3 | psh×2, bash×1 |
| tests/integration/job_control/test_pipeline_signal_death.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/job_control/test_signal_killed_diagnostic.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/job_control/test_signal_killed_exit_status.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/job_control/test_trap_ignore_inherit_exec.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/parser/test_combinator_parity_regressions.py | BASH-DIFFERENTIAL | 2 | bash×1, psh×1 |
| tests/integration/parsing/test_bang_prefix_compound.py | BASH-DIFFERENTIAL | 2 | var×1, bash×1 |
| tests/integration/parsing/test_brace_extent_literal_brace.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/parsing/test_r16_command_position.py | BASH-DIFFERENTIAL | 2 | var×1, bash×1 |
| tests/integration/redirection/test_compound_redirect_failure.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/redirection/test_explicit_fd_heredoc_no_self_close.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/redirection/test_here_string_tilde.py | BASH-DIFFERENTIAL | 1 | other×1 |
| tests/integration/redirection/test_heredoc.py | BASH-DIFFERENTIAL | 8 | psh×7, bash×1 |
| tests/integration/redirection/test_heredoc_composite_delimiter.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/redirection/test_input_cursor_identity_i1.py | BASH-DIFFERENTIAL | 4 | bash×3, psh×1 |
| tests/integration/redirection/test_process_sub_embedded.py | BASH-DIFFERENTIAL | 3 | psh×2, bash×1 |
| tests/integration/redirection/test_redirect_failure_paths.py | BASH-DIFFERENTIAL | 5 | bash×3, psh×2 |
| tests/integration/redirection/test_script_fd_ownership_i2.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/redirection/test_script_fd_relocation.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/redirection/test_std_fd_lease_f2.py | BASH-DIFFERENTIAL | 2 | python×1, var×1 |
| tests/integration/scripting/test_set_u_exit_code.py | BASH-DIFFERENTIAL | 4 | psh×2, bash×2 |
| tests/integration/subshells/test_env_isolation_p1.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/integration/test_assignment_error_abort.py | BASH-DIFFERENTIAL | 3 | psh×2, bash×1 |
| tests/integration/test_ps4_expansion.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/test_time_keyword.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/integration/test_xtrace_format.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/system/test_lazy_script_source_i2.py | BASH-DIFFERENTIAL | 4 | var×1, psh×1, bash×1, python×1 |
| tests/system/test_lineno_script_file.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/system/test_posix_invocation.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/system/test_r16_scripting.py | BASH-DIFFERENTIAL | 7 | bash×4, psh×2, var×1 |
| tests/system/test_read_malformed_bytes_i1.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/system/test_script_input_sources.py | BASH-DIFFERENTIAL | 5 | bash×3, var×2 |
| tests/system/test_script_shebang_is_comment.py | BASH-DIFFERENTIAL | 3 | psh×2, bash×1 |
| tests/system/test_source_error_rc.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/system/test_stdin_script_lazy_read.py | BASH-DIFFERENTIAL | 7 | psh×3, var×2, bash×2 |
| tests/system/test_stdin_startup_robustness.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/system/test_unterminated_heredoc.py | BASH-DIFFERENTIAL | 7 | psh×4, bash×3 |
| tests/system/test_word_separator_bytes.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/unit/builtins/test_bcontract_serialization.py | BASH-DIFFERENTIAL | 3 | var×1, bash×1, psh×1 |
| tests/unit/builtins/test_declare_bare_name_locality.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/unit/builtins/test_let.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/unit/builtins/test_mapfile.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/unit/builtins/test_read_mapfile_streaming.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/unit/core/test_funcname_call_stack.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/unit/core/test_nameref.py | BASH-DIFFERENTIAL | 3 | bash×2, psh×1 |
| tests/unit/core/test_tempenv_visibility_ledger.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/unit/executor/test_command_resolution_r3.py | BASH-DIFFERENTIAL | 4 | psh×2, bash×2 |
| tests/unit/expansion/test_parameter_transform.py | BASH-DIFFERENTIAL | 2 | psh×1, bash×1 |
| tests/unit/expansion/test_pattern_engine_differential.py | BASH-DIFFERENTIAL | 1 | var×1 |
| tests/unit/interactive/test_history_modifiers.py | BASH-DIFFERENTIAL | 1 | bash×1 |

(`var` = the argv is a helper parameter (`argv`/`shell_argv`/`shell_cmd`)
applied to BOTH psh and bash prefixes — a differential dispatcher; `other` =
a helper-returned prefix, e.g. `[*exe, cmd]` / `[self._bash(), …]`; `python` =
a `python -c` helper.)

## Consumer unification (item 3)

Nine `run_shell_case` consumers gate their comparison on
`isinstance(result, Completed)` rather than the sole authority `is_comparable`.
They are semantically identical today; routing them through `is_comparable`
keeps the authority sole (a future third comparable outcome would be added in
one place):

1. tests/integration/pipeline/test_pipeline_closed_fds.py:88
2. tests/integration/pipeline/test_long_pipeline_fd_limit.py:44
3. tests/integration/redirection/test_process_sub_closed_fds.py:54
4. tests/integration/redirection/test_process_sub_closed_fds.py:72
5. tests/system/invocation/test_invocation_matrix.py:42
6. tests/system/invocation/test_startup_order.py:34
7. tests/system/invocation/test_startup_order.py:43
8. tests/system/source_service/test_source_service_matrix.py:46
9. tests/system/source_service/test_nul_channel_matrix.py:77

(The `isinstance(_, Completed)` occurrences in
`tests/unit/tooling/test_shell_oracle_harness.py` deliberately assert the
runner's return TYPE — they stay isinstance. Count corrected in round 3: **6 at
base `e52957d4`**, **21 at this tip** (the slot's new runner pins — stdin_mode,
$PWD, natural-exit cap, Timeout provenance — assert the returned type directly);
the earlier "three" was simply wrong. Replay:
`grep -o 'isinstance([a-zA-Z_0-9]*, *Completed)' <file> | wc -l`.
The `is_comparable` definition itself lives in `shell_oracle.py` — cite it by
symbol, not by a line number that moves with every edit.)
