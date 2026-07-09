# Changelog

All notable changes to PSH (Python Shell) are documented in this file.

Format: `VERSION (DATE) - Title` followed by bullet points describing changes.

## 0.674.0 (2026-07-09) - A trailing backslash at EOF now ends like bash: dropped in streams, literal in strings
- A dangling line continuation at end of input was mishandled in every input mode: a script file ending `echo hi \` printed `hi \` in psh but `hi` in bash. Three root causes fixed: the command accumulator's newline rstrip stranded `cmd \<LF>` before execution (bash joins the continuation with the empty remainder in ALL modes); the true-EOF dangling backslash follows bash's STREAM-vs-STRING rule — stream inputs (script file, stdin script, process substitution) DROP it, string inputs (`-c`, `eval`, and `source`/`.`) keep it LITERAL — where psh treated every mode like `-c`; and the same rstrip ate trailing empty body lines of EOF-delimited heredocs.
- The `source`-keeps-it-literal half was discovered by probe (the campaign brief guessed the other way); live bash 5.2.26 arbitrated. Mode knowledge threads through the existing `InputSource` abstraction (no lexer special-casing), and `--validate`/analysis modes see execution-identical text.
- Truth-tabled 31 shapes × 6 input modes = 186 rows vs bash: 85 diverging before, 180/186 exact after; the 6 residuals are one ledgered unterminated-heredoc corner where psh is now strictly closer to bash (half of it is bash's own 0xFF EOF-sentinel leak, deliberately not chased).
- No regressions to the v0.648 linear-heredoc path, v0.666 lazy stdin (a trailing continuation does not force a drain — explicitly re-proven), `read`/`mapfile`, or interactive PS2 accumulation (full PTY suite re-run green by the verifier).
- Independently verified: 224-row adversarial matrix across 8 modes with ZERO net-regression rows, 4 mutations each killed by specific pins (the stream/string mode split is pinned in BOTH directions), red-on-base recounted exactly (36 red / 14 controls). Suite grows to 14,290 gate-passed (+50), compare-bash phase 1,202 with 16 `contcarry_*` golden cases.

## 0.673.0 (2026-07-08) - POSIX mode exits like POSIX: special-builtin errors end a non-interactive shell — with bash's exact suppression rules
- Implements the deferred POSIX-mode special-builtin EXIT-on-error matrix (docs/reviews/posix_special_builtin_exit_matrix_2026-07-07.md, re-derived live against bash 5.2.26): with `set -o posix`, a NON-interactive shell now exits — later lines never run — when a special builtin hits a usage/syntax error (invalid option to set/export/readonly/unset/trap/exec, `return` at top level, `. /nonexistent`, an `eval`/`.` syntax error, assignment to a readonly), carrying the builtin's own status (2 for usage/syntax, 1 for the readonly/dot cases). Operand/semantic errors (`export 1bad=x`, `trap 'x' NOSUCHSIG`, `unset` of a readonly) correctly do NOT exit, and `break`/`continue` at top level are bash's silent rc-0 no-ops in posix mode.
- One typed outcome, one policy: special builtins raise `SpecialBuiltinUsageError` at explicitly classified sites (no rc-based heuristics), and a single executor policy converts it to a shell exit in POSIX + non-interactive context. `command`/`builtin` prefixes strip the exit; fork boundaries (subshells, command substitution, pipelines, background) contain it; a sourced file's error exits the whole shell; the EXIT trap fires on the way out — each bash-exact.
- Bash's two exit classes are faithfully implemented (found adversarially, verified against 39 + 14 independent probe rows): invalid-option/return exits are SUPPRESSED in errexit-suppressed contexts (`if`/`while` conditions, left of `&&`/`||`, after `!` — including through functions, brace groups, and subshell interiors), while eval/dot syntax errors, missing sourced files, and readonly-assignment exit even when guarded; `eval`/`.` boundaries reset suppression on their inner text.
- Bash-faithful fixes to pre-existing both-modes divergences found by the probe batteries: `return 3 4`/`break 1 2`/`continue 1 2` now discard the input unit instead of hard-exiting the shell, and `trap` rejects leading-dash non-option words. The matrix doc's one wrong cell (top-level `return` in default mode is rc 2, not 1) is corrected.
- Independently verified end-to-end: 147-row Phase-1 probe battery plus a 39-row fix battery and 14 boundary rows, six mutations each killed by their intended pins, red-on-base/red-on-tip reconciled exactly, non-posix byte-identity confirmed, and the merged tree (with v0.672.0) gate-verified with `set -o`/`$-` surfaces identical to both parents. Suite grows to 14,240 gate-passed (+213), compare-bash phase 1,186 with 44 `posixexit_*` golden cases.

## 0.672.0 (2026-07-08) - set +B means it now: the braceexpand option actually disables brace expansion
- The `braceexpand` shell option was registered (on by default, `B` in `$-`) but consumed by NOTHING — `set +o braceexpand; echo {a,b}` still printed `a b` (bash: `{a,b}`), `{1..3}` still expanded, and the `set -B`/`+B` short flags were rejected as invalid. Discovered by the v0.669.0 option-consumer meta-test; that meta-test now records braceexpand as consumed.
- Brace expansion (tokenize-time in psh) now seeds from the live option, and a command-position `set ±B` / `set ±o braceexpand` scanner — mirroring the same-stream alias absorption — makes straight-line toggles (`set +B; echo {a,b}`) match bash within a single parse unit: the toggle applies after `set`'s own words, is discarded for pipeline/background segments, and is scoped across `( )` subshells. Alias values expand with the caller's option state, and `psh -B/+B` invocation flags match bash.
- Truth-tabled against bash 5.2.26: 38/40 main-battery rows match (the 2 remainders are the pre-existing `shopt -o` gap, ledgered as follow-up work along with `SHELLOPTS`); same-parse-unit edge cases of the tokenize-time model (toggles in not-taken branches, function bodies baking expansion at definition, a later-pipeline-segment or function-shadowed `set`) are documented in the expander's ledger docstring — all self-heal on the next parse unit, and the real fix (Word-stage brace expansion) is ledgered.
- Adversarially verified: four design mutations each kill specific pins, 17 unit pins + 17 golden rows demonstrated red-on-base independently by the verifier, the default-ON hot path is byte-identical to v0.671.0, and no row moved farther from bash than the base was. Suite grows to 14,027 gate-passed (+47), compare-bash phase 1,142 with 20 `braceexp_*` golden cases.

## 0.671.0 (2026-07-08) - The gate runs in a third of the time — same proofs, measured
- Test-runtime optimization (from the measured performance appraisal): the full local gate drops from ~310s to ~217s and gate+compare-bash from ~539s to ~232s (2.3× faster), measured single-tenant on the merged tree with IDENTICAL outcomes — no test lost, no assertion weakened, no subprocess-by-design test converted.
- The compare-bash phase is 14× faster: it runs only the bash-comparison variants in parallel (`-n auto`) — the psh-side expectation checks already run in every main gate, so re-running them serially was pure duplication. NEW RECONCILIATION ANCHOR: the compare-bash phase now reports 1,122 passed / 0 failed / 23 skipped (was 2,267 under the old double-counting); the runner banner states the change and rationale.
- The serial phase shrinks from 73% of the gate to ~60% at less than two-thirds the time: 362 individually-audited xdist-safe redirection tests (81% of the directory) join the parallel phase via an explicit allowlist — new files in the directory still default to serial (safe-by-default, adversarially probed); and the exit-trap signal tests use event-based child-readiness instead of fixed sleeps (58.9s → 13.9s for the file, MORE load-robust: signalling can no longer race trap installation).
- Verified end-to-end by an independent two-phase verification: counting integrity proven by collection arithmetic, 8-of-22 allowlist files re-audited adversarially, the (c) speedup reproduced commit-vs-commit, per-anchor reconciliation exact on the merged tree. The `run_tests.py --compare-bash` flag combination remains discouraged (it still runs the full gate first with capture-at-end output); the fast path is the runner's own compare-bash phase or the direct pytest form.
- Remaining gap ledgered honestly: the gate's floor is the genuinely serial PTY/signal tier (~130s); reaching lower needs PTY-tier work, out of scope.

## 0.670.0 (2026-07-08) - Job control: %+ survives foreground commands — kill %+, wait %+, bare fg/bg work like bash
- Any foreground external or pipeline used to STEAL the current-job pointer (%+) from a running background job and never return it — after which `kill %+`/`%%`/`%-` reported "no such job", `wait %+` failed with 127, bare `fg`/`bg` said "no current job", and `jobs` showed blank +/- markers (bash keeps the background job current throughout). Foreground tracking is now decoupled from the current/previous rotation: `%+`/`%-` hold only background and stopped jobs, a foreground command that runs to completion never enters the rotation, and a foreground job stopped with Ctrl-Z takes `%+` (bash's stopped-job priority — behavior-preserving, it already worked).
- The background-completion notice now renders bash's true job marker: `+` when the finished job is the current job, blank otherwise (never `-`) — the strict xfail that pinned this divergence since v0.667.0 is now a real passing test, and the user-guide ledger row is retired.
- Ledgered pre-existing cosmetics (unchanged by this fix): foreground externals consume job numbers so `jobs` ids can drift from bash; `jobs` command text omits redirections; bare `fg` on the no-job-control path echoes the command before the capability error.
- Suite grows to 13,980 gate-passed (+10; one deliberate xfail retired), compare-bash 2,267 with 3 `jobcur_*` golden cases that target via `%+`/`%-`/`%%` resolution.

## 0.669.0 (2026-07-08) - Core-state Phase 4 — one environment interface, temp-env overlays, options that enforce
- Core-state appraisal Phase 4 (H3): all environment mutation now routes through one materializer — `state.env` is written only by `_materialize_env_name`, with a fixed precedence of command overlay > exported variable > opaque base > absent, and the opaque base (invalid-identifier inherited entries) is an explicit typed store. The 12 remaining direct env pokes (pushd/popd/cd `PWD`/`OLDPWD`, `export -n`, exec-env, and the temp-env save/restore cluster) are gone.
- Command-prefix assignments (`VAR=x cmd`) are a materialization-time OVERLAY instead of mutate-then-rollback: the literal wins (`RANDOM=5 cmd` passes 5; `a+=z cmd` appends element 0), teardown drops the overlay with no per-name env snapshots, and POSIX-mode special-builtin persistence commits cleanly (no stale literal after a later reassignment). The refactor is provably behavior-preserving — a 27-case prefix truth table matches bash before and after, with the discriminating rows committed as golden pins.
- Fixed: with a readonly `OLDPWD`, `cd` no longer leaks the stale old value into child environments (bash keeps the frozen value; psh's raw poke wrote through the readonly rejection). Pinned with a discriminating direct-`printenv` test after verification showed the first pin was masked by command substitution.
- Option registry enforces: option values are type-checked on write and keys cannot be deleted; the inert `collect_errors` and phantom `parser-mode` options are retired from `set +o` (bash has neither); a consumer meta-test requires every registered option to be read-for-behavior or explicitly allowlisted — and immediately found that `set +o braceexpand` is a no-op (tracked follow-up).
- Ledgered (user guide §17): prefix variables appear in `set`/`export -p` enumerations where bash's separate temporary_env is lookup-only — three esoteric divergences deferred to a dedicated campaign with a committed 16-case visibility battery.
- Suite grows to 13,970 gate-passed (15,194 collected); compare-bash 2,261 with 17 new `corestate4_*` golden cases.

## 0.668.0 (2026-07-08) - Closed-then-reopened output no longer leaks buffered builtin bytes
- I/O-redirect appraisal MED-1: after a permanent `exec >&-` (or `2>&-`), a builtin's failed write no longer lingers in a Python stream buffer to be flushed into a later-reopened fd at shutdown (`exec 3>&1; exec >&-; echo LEAK; exec >&3 3>&-; echo end` printed `end` then `LEAK`; bash prints only `end`). A transparent, unbuffered `_RawFdStream` now backs BOTH permanent-close paths (natural and with-override), unifying the two divergent treatments; the false "a later fd-level reopen heals it" premise and its branch are gone. `_ClosedStream` remains for temporary per-command closes, where it is correct.
- Why not a closed-stream sentinel everywhere: compound and function redirects (`f 1>&2`, `{ …; } >file`, `&>file`) reopen the fd at the descriptor level and rely on the Python stream transparently following the fd — an opaque sentinel severs them (proven by mutation: it breaks exactly the four tests pinning that behavior). Transparency and non-buffering are independent requirements; the raw stream satisfies both.
- Ledgered deliberate divergence (user guide §17.3): bash's C-stdio resurrects buffered stderr *diagnostics* (e.g. a `cd` error) across a stderr close+reopen; psh discards them cleanly — the divergence is bash's buffering artifact, and psh additionally drops a spurious `[Errno 9]` message the old code leaked. Every normal-output close/reopen shape matches bash byte-for-byte (verified across a 24-row + independent 18-row differential battery).
- Suite grows to 13,927 gate-passed (+20; 15 subprocess leak/transparency pins + 5 `ioleak_*` golden compare-bash cases).

## 0.667.0 (2026-07-08) - Interactive notify works — set -b emits background Done notices; Ctrl-R executes on Enter
- Interactive-appraisal HIGH: `set -b`/`set -o notify` no longer silently drops every background-job completion notice (the REPL skipped the only reaping path under notify; completed jobs also leaked as stale DONE entries) — notices now print once at the next reaping opportunity and the job is reaped. Ledgered timing gap (user guide §17): bash prints mid-idle via async SIGCHLD; psh emits at the next prompt because the line editor's select() does not watch the SIGCHLD pipe.
- Ctrl-R reverse search executes the recalled command on a single Enter like readline/bash (previously Enter only accepted the text and the next command concatenated onto it); the search label is bash's `(reverse-i-search)` family; Ctrl-D at the prompt prints `exit` to stderr before exiting; a failed history substitution reports bash's `substitution failed` (with the full `:s/…/…` spec) instead of the wrong `bad word specifier` class.
- Done-notice format: the stray leading blank line is gone. The current-job marker stays a hardcoded `+` — correct for the dominant single-background-job case; the exact bash rule (`+` for the current job, blank otherwise) is blocked by a JobManager divergence (foreground commands clobber `%+`), pinned by a strict xfail with root cause and tracked as follow-up work.
- Interactive subsystem guide aligned to shipped behavior (notify flow, labels, Ctrl-R semantics, notice format). Suite grows to 13,907 gate-passed (+3, +1 deliberate xfail).

## 0.666.0 (2026-07-08) - Scripts on stdin read lazily — in-script stdin consumers work like bash
- Scripting-appraisal HIGH: a script delivered on standard input (`cmds | psh`, `psh < file`, `psh -s`) is no longer slurped whole at startup — a lazy `StdinInput` reads one line at a time via a new additive `InputReader.read_record_bytes` (one owner of fd-byte reads, shared with `read`/`mapfile`), so `read`, `cat`, `mapfile`, and external commands inside the script consume the remaining stdin exactly like bash (pipes and seekable files alike; heredocs and multi-line constructs still parse across reads; `exec < file` mid-script switches the source because the reader consumes fd 0 by number). Script-file arguments and `-c` were already correct and are pinned.
- The byte model is preserved: raw non-UTF-8 bytes on the command stream round-trip via surrogateescape (`café` as raw latin-1 echoes byte-identically to bash); the reader's two decode policies (incremental replace for `read`/`mapfile` records, batch surrogateescape for command lines) are deliberate and documented.
- `--validate`/analysis modes read script files like the executor: a non-UTF-8 script that runs fine now validates instead of crashing, a missing file reports 127 and a directory 126 (matching `bash -n` shapes); runaway `source` recursion reports a resource-limit diagnostic instead of an internal error.
- Ledgered deliberate divergence (docs/user_guide/17 §17.3): bash's `mapfile` on a *seekable* stdin reads from EOF — inconsistent with bash's own `read`/`cat`/`read -d ''` and its own pipe-`mapfile`; psh keeps fd-position consistency. Trailing backslash-newline at EOF is deferred with a full diagnosis (accumulator continuation-carry).
- Test environments strip `DISPLAY`/`XAUTHORITY` (conftest + conformance framework + a canary test): on macOS the inherited XQuartz launchd socket let any X11-capable test-spawned client auto-start XQuartz mid-run. Suite grows to 13,902 gate-passed (+54).

## 0.665.0 (2026-07-08) - Core-state Phase 3 — one special-parameter registry, opaque environment entries
- Core-state appraisal Phase 3 (H1): a declarative special-parameter registry (`psh/core/special_registry.py` — one `SpecialVarSpec` table + typed `SpecialParameterState`) replaces three frozensets and an if-chain in `scope.py` (net −225 lines). Computed specials now have real lifecycles: `readonly RANDOM/SECONDS/BASHPID` is enforced (assignment fatal, blocks `unset`, like bash); `export RANDOM` materializes a seeded snapshot into the environment with bash-exact values (`export RANDOM=7` → 19344 in both shells); `unset EPOCHSECONDS/EPOCHREALTIME/LINENO` genuinely deactivates; named `declare -p RANDOM` lists the variable; `SECONDS` uses a monotonic clock.
- `set -a` (allexport) seeds but does not export a computed special, matching bash — a divergence the campaign itself introduced and caught before review, pinned by regression tests; command-prefix `RANDOM=5 cmd` passes the literal value through.
- Phase 3 (H3): environment entries whose names are not valid shell identifiers (`bad-name=x`, `a.b=y`) stay OPAQUE like bash — visible to `printenv`, children, subshells, and command substitutions, but no longer imported as shell variables (previously they appeared in `set` and `declare -p` output). The full env-mutation consumer map for Phase 4's overlay redesign is documented in `psh/core/CLAUDE.md`.
- Ledgered (pre-existing): bulk no-argument `declare -p` and `compgen -v` still omit computed specials; `declare -p FUNCNAME/BASH_COMMAND` still report not-found. Suite grows to 13,848 gate-passed (+72; 15,049 collected); compare-bash 2,217 with 14 new `corestate3_*` golden cases.

## 0.664.0 (2026-07-08) - Tests and docs tell the exact truth — claims requalified, probes assert, a real --quick tier
- Tests/documentation-appraisal campaign: public claims now state their oracle honestly — the unproven "POSIX ~98%" percentages are gone from README/ARCHITECTURE/user guide, replaced with "verified against live bash" language; five bash-ism tests moved out of the POSIX conformance tree (guarded against recurrence); the local-gate contract is documented as it actually works (per-PR CI intentionally disabled; the gate is local, the nightly is the backstop).
- Conformance probes assert: the eight assertion-free `check_behavior()` calls in the bash-compatibility suite were converted to `assert_identical_behavior` (each verified against bash 5.2.26 first); a tooling guard now bans assertion-free probes in conformance-counted files.
- Fixtures tell the truth: `clean_shell` really clears state and `shell_with_temp_dir` reports a truthful `$PWD` — the old code wrote to the *derived* `state.variables` dict, silently doing nothing (and `clean_shell` leaked the entire ambient environment); a guard now bans writes to `state.variables` in tests and docs.
- A genuine `--quick` tier: ~8,300 in-process tests in ~20 seconds (no serial/subshell/compare-bash phases), with an honest "not the release gate" banner; the old `--quick` deselected a single test.
- Generated statistics: `tools/gen_test_stats.py` computes test/file/LOC counts; the README's four contradictory test counts are replaced by one script-maintained set, enforced by an extended statistics meta-test.
- Runner hardening: Ctrl-C during a test phase now kills the child process group (previously only timeouts did); `docs/subsystem_internals.md` archived as historical; the reviews index is complete and meta-tested — every review document in `docs/reviews/` must be indexed, including the fourteen 2026-07-05/06/07 subsystem appraisals committed with this release.

## 0.663.0 (2026-07-07) - Builtins contracts — set/shift/exit policy, reusable serialization, transactional dir stack
- Builtins-appraisal findings 6/9/11/12: `set ""` no longer crashes (was an IndexError on an empty operand); `set -`/`set +` and `set - a b` match bash; `shift`/`exit` validate the first operand before the count and, on too-many-arguments, report the error and discard the rest of the current input unit *without* exiting the shell — one shared typed `special_builtin_usage_discard` executor policy, verified identical across `-c` strings, script files, `eval`, `source`, subshells, `set -e`, and POSIX mode.
- Reusable serialization: one shell-word serializer (extending the v0.633 `formatter_quoting` authority) now backs `set`, `declare -p`, and `hash -l` — output is byte-identical to bash (single-quote form, `$'…'` for control characters) and round-trips through a fresh psh *and* a fresh bash across a hostile corpus.
- Directory-stack transactions: `pushd`/`popd` mutate the stack only after a successful `chdir`, so a failed directory change leaves the stack and cwd unchanged (the `stack[0]==cwd` invariant holds); `cd` updates `PWD`/`OLDPWD` independently so a readonly `OLDPWD` no longer blocks a `PWD` update; `pushd +N` on a too-small stack uses bash's "directory stack empty" wording.
- Output-failure propagation: a builtin writing to a bad/closed fd now propagates the failure into its exit status (`print -u99` → rc 1, was rc 0) through a shared partial-write-safe `write_all_fd` helper swept across every builtin write path.
- Nameref riders (from the varstore verification): arithmetic on an associative-array key *through* a nameref now writes the named key rather than element `[0]`, and `unset "ref[k]"` through a nameref unsets the target element.
- Also: the `TIMEFORMAT %P` test is hardened against multi-digit integer parts under parallel load (closes the long-standing flake). Two follow-ups are ledgered with a committed bash truth table (POSIX-mode special-builtin exit-on-error matrix) and an xfail pin (explicit-index array `declare -p` re-parse of an escaped `$`).
- Suite grows to 13,761 (+118 over the input service, +1 xfail for the ledgered array pin); 14 new `bcontract_*` golden compare-bash cases.

## 0.662.0 (2026-07-07) - One streaming input service — read/mapfile UTF-8 fidelity, no input draining
- Builtins-appraisal findings 4+7: one record-oriented input service (`psh/builtins/input_reader.py` — incremental UTF-8 decoding, monotonic TOTAL `-t` deadline, injectable source/echo streams, typed DATA/EOF/TIMEOUT/ERROR outcomes) now backs both `read` and `mapfile` (the only stdin data consumers in builtins).
- Multibyte fidelity on real fds: `read -N1`/`-n1` and plain `read` no longer mangle multibyte UTF-8 to U+FFFD, and `read -N1` no longer leaves an orphaned continuation byte in the stream — all bash-identical now. (The bug lived only on the raw `os.read` path; in-process text-layer probes structurally could not see it, which is why an earlier appraisal probe reported no repro.)
- `mapfile -n N` no longer drains the remaining input into a hidden userspace buffer — like bash, the next consumer (builtin or external) sees the unconsumed lines, on pipes and regular files alike; `mapfile -u` with a bad fd now fails with rc 1, and negative/non-numeric `-n`/`-s`/`-O`/`-u` operands get bash's error messages.
- `read -t` timeout is a monotonic total deadline (not reset per byte), pinned by a deterministic fake-clock test after adversarial mutation testing showed the property unpinned.
- Ledgered divergence: `read -d DELIM` is character-oriented in psh vs byte-oriented in bash — identical for all ASCII delimiters (docs/user_guide/17_differences_from_bash.md). Invalid/truncated UTF-8 input still follows psh's shell-wide U+FFFD replace policy.
- Suite grows to 13,643 (+44, including 8 input_* golden compare-bash cases).

## 0.661.0 (2026-07-07) - JobManager transactions — jobspec fidelity, wait -p, transactional pipeline launch
- Executor-appraisal findings 11–14 + builtins jobspec cluster: `kill %job` signals the process group ONCE via `killpg` (was per-member); jobspec resolution returns typed results so `jobs %999`, invalid specs, and `%ambiguous` produce bash's errors and exit codes; `disown -a`/`-r` on an empty job table match bash; `bg` accepts multiple jobspecs; `fg` reclaims the terminal in a `try/finally` (a dying foreground job can no longer strand the shell without terminal control).
- `wait -p VAR` is bash-faithful: VAR is unset up front and set only when a child is actually reported — non-child pids, invalid/nonexistent jobspecs, bare `wait`, and `wait -n` with nothing to reap all leave VAR truly UNSET (the truth table showed bash unsets rather than leaves-unchanged).
- F13 (transactional partial launch): a pipeline that fails mid-launch now kills and reaps the already-started members BEFORE releasing the launch gate — no orphaned half-pipelines (mutation-verified ordering).
- Continued-job tracking (`WCONTINUED`) with a platform finding: macOS delivers no SIGCHLD when a stopped child continues, so continue-detection polls in interactive job control on macOS (Linux uses SIGCHLD); documented in the job-control internals.
- JobManager gains an O(1) pid→job index and a `ProcessState` enum replacing string states; deliberate divergence ledgered: bash reports `jobs %amb` ambiguity inconsistently between `-c` and interactive modes — psh pins the interactive behavior (docs/user_guide/17_differences_from_bash.md).
- Docs: `psh/builtins/CLAUDE.md` resolver prose now names the real `CandidateKind` members (`HASHED`/`EXTERNAL`). Suite grows to 13,599 (+38, including 3 jobmgr golden compare-bash cases).

## 0.660.0 (2026-07-07) - Refactor: one CommandResolver — command -p, hash visibility, empty PATH components, env re-search
- Builtins-appraisal finding 5: one typed resolver (`psh/executor/command_resolver.py` — search_path / resolve(query) / resolve_for_exec, CandidateKind ALIAS/KEYWORD/FUNCTION/BUILTIN/HASHED/EXTERNAL) now backs the executor's external path, `command`, `type`, `hash`, and `exec -c`; the duplicated `_find_in_path` is deleted. The consumer map REFUTED one appraisal claim — tab completion does no command-name resolution (there were four implementations plus an uncounted sixth consumer, not five).
- **Fixes (bash-pinned):** `command -p` keeps builtin/function selection — `-p` only changes the PATH used for EXTERNAL search (`command -p cd /` now changes the shell's directory; was forced-external) — and no longer corrupts the CHILD's PATH (`command -p sh -c 'echo $PATH'` shows the real PATH; psh previously leaked `/usr/bin:/bin` into the environment). `hash -p /path name` is now visible to `command -v`/`-V` and `type -P` (was: only `type -p`); `type -a` ignores the hash like bash. Empty PATH components (`PATH=:/usr/bin`) denote the current directory, and slash-names render as-given (`type -P ./prog` → `./prog`, not an absolute path). The v0.656-deferred D3 edge is closed: `env PATH=/override cmd` re-searches the overridden PATH instead of exec'ing the shell's hashed path (the env_command docstring now tells the truth).
- Executor strategy DISPATCH deliberately not rebuilt (deviation, verifier-confirmed): function/special-builtin/builtin precedence carries heavy pinned behavior (v0.652 posix ordering, v0.656 env-external) and its membership checks cannot drift; only the PATH-walk + hash consult were unified. Preserved bash divergences ledgered as future rows: `type -f` over-suppression, `type -P` not-found verbosity, degenerate `PATH=`.
- Verifier verdict: PASS (evidence-complete; formal report follows) — independent truth tables for all 4+2 fixes bite main; refutation confirmed by its own grep; 4/4 mutations bite; rows C/D/E confirmed pre-existing; gate + compare-bash reproduced exactly. Suite 13,561 passed / 0 failed; compare-bash 2,139 (+7 golden `resolver_*`).

## 0.659.0 (2026-07-07) - Feat: substitutions carry parsed Programs — nested syntax errors reject the whole buffer
- The flagship of the appraisal roadmap (parser finding 1 ≡ expansion finding 7): `CommandSubstitution`/`ProcessSubstitution` now carry a `Program` parsed at the OUTER parse (plus the raw `source`). `echo before; echo $(if); echo after` rejects the entire buffer before anything executes (rc=2, like bash) — previously `before` and `after` both ran and the buffer exited 0. Same for `<(…)`/`>(…)`, nested substitutions, and every Word-AST position (assignments, prefixes, redirect targets, case subjects, headers, never-executed branches). Analysis visitors now descend into substitution bodies: `--validate` catches `$(if)` at validate time; the security and lint visitors see inside `$()`.
- **The design deviation that decided the architecture** (probe-driven, verifier re-derived independently): bash DOUBLE-PARSES — an alias-free syntax validation at read time plus a runtime re-parse with the live alias table at expansion (the decisive row: a function body's `$(alias-name)` resolves aliases defined AFTER the function). So the stored `Program` is the validation/tooling view, and execution keeps bash-style runtime re-parse of `source`. The expansion plan's "stop reconstructing and reparsing" is formally REFUTED for command/process substitutions — noted for the typed-fragments campaign. Backticks are excluded by evidence (bash genuinely defers their parsing — `` `broken-alias-syntax` `` is accepted where `$(…)` is rejected; ledgered).
- Nested parsing is injected into WordBuilder (context-bound helper: line offsets for in-substitution errors, heredoc-aware, shell lexer options threaded — extglob inside `$()` re-lexes correctly, regression-pinned on both parse paths after the verifier proved the fix unpinned). Nesting depth capped at 100 with a clean bounded error (interim extract-and-reparse is O(n²); bash accepts deeper — ledgered; the lexer program's token-level recursion is the successor). Combinator parser in full lockstep (direct AST parity; its shallow substitution validator removed — it wrongly rejected function definitions bash allows).
- Documented runtime-timing divergences (raw-string operand territory, pinned + ledgered): `${x:-$(if)}`, `$(( $(if) ))`, and heredoc bodies still error at expansion; bash's `-c`-only exit-127 quirk noted.
- Verification: dev 63-case timing conformance + 42-lock battery; adversarial verifier PASS-WITH-NITS — 13-row alias table independently re-derived (CONFIRMED-CORRECT incl. the $()-eager/backtick-deferred asymmetry), 34-row error-timing battery, re-frozen corpora audited clean, both nits closed with self-mutation-confirmed pins. Merge with v0.658.0 validated (session-crash recovery: merge phase re-run cleanly — BLOB-UNION golden resolution, seam battery incl. the extglob-inside-$() double seam, merged gate exact). Suite 13,505 passed / 0 failed; compare-bash 2,125 (+13 golden `nprog_*`).

## 0.658.0 (2026-07-07) - Perf: one compiled pattern engine — exponential extglob eliminated
- Expansion-plan finding 6 (Phase 4), consuming the v0.655 locale-service predicates as designed (Stage 5). The audit-first pass found not one but TWO exponential backends: the regex path (catastrophic backtracking on ambiguous repetition) and a reachable-set backtracker that had the right semantics but no memoization. Both replaced by one engine: `psh/expansion/pattern_engine.py` — patterns parsed ONCE into an AST (Sequence/Literal/AnyChar/Star/Bracket/Extglob) and matched by a memoized reachable-positions matcher (each state evaluated at most once per subject position). Old backtracking matcher deleted.
- **All pattern consumers flipped**: `case`, `[[ == ]]`, `${var#/##/%/%%}` removal, ALL `${var/…}` substitution operators (including `/#` and `/%` anchored forms — the suffix operator was initially missed on a wrong gate flag, caught by the verifier and fixed), and pathname extglob components. The plain-glob pathname fast path deliberately stays on the linear converter. Bracket/class membership keeps the v0.655 host-faithful locale path exactly.
- **Performance**: the exponential repro (`${x/%*(a|aa)c/R}` at N=38) went 7.2s → milliseconds; at N=60 psh now completes in ~100ms where bash 5.2 itself times out. Complexity is guarded deterministically (state-count bounds, not wall-clock) — verifier-proven load-bearing via memo-neutering (514 → 2,031,613 states).
- Behavior proven preserved: ~1,039 independent differential rows vs bash (every psh-vs-bash difference is pre-existing on main); 153,477 fresh-seed property cases against BOTH old backends with zero mismatches; the full glob/extglob/case/param-pattern corpus unchanged.
- New pre-existing divergences found and pinned (exposed, not introduced): `${s/#?(x)/Z}` on an empty subject emits `Z` where bash suppresses the zero-width match (the `/#` sibling of the known `?()` quirk; `/%` agrees with bash) — in KNOWN_DIVERGENCES; bracket+extglob adjacency (`[ab]@(a|b)`) parse-errors in `[[ ]]`/`case` while the same pattern WORKS in `${v##…}` — a parser gap (matcher proven correct), folded into the escaped-metachar parser task.
- Verifier verdict: **PASS** — every headline number independently reproduced; suffix-fix addendum 5/5; nothing refuted. Suite 13,420 passed / 0 failed (+105); compare-bash 2,099 (+12 golden `pateng_*`).

## 0.657.0 (2026-07-07) - Refactor: authoritative VariableStore + one declaration engine
- The build both remaining appraisals converge on (core-state Phase 2 ≡ builtins finding 3, built once): `psh/core/variable_store.py` — every variable mutation (assign/append/set_element/unset_element/unset/attribute changes) is ONE transaction: nameref resolution (with per-operation policy) → target-scope selection → readonly validation BEFORE any mutation → subscript resolution (the single sparse-aware formula) → value computed on a copy → atomic commit → env/PATH observer notification. `declare`/`export`/`readonly` are now thin adapters over one typed `DeclarationRequest` engine (`psh/builtins/declaration_engine.py`); `local`'s scalar path deliberately stays on `create_local` (its redeclare-merge/tombstone semantics are not the generic contract — Phase-4 item, locks prove byte-identical).
- **Four probe-verified declaration-drift fixes** (all now match bash): `declare -i n=2; export n+=3` → 5 (was textual `23`); `declare -A` on an existing indexed array → rc=1 with the array PRESERVED, even when empty (was: converted, rc=0 — the code comment claiming bash converts was wrong); `declare -g x+=A` through a local shadow reads the GLOBAL base (`GA`, integer variant `100+=5` → `105`; was `LA`/string-concat); `declare -pn` lists namerefs only (was: full dump).
- **Beneficial collateral fix** (bash-matching, golden-pinned): arithmetic element assignment through a nameref (`declare -n r=arr; (( r[0]=9 ))`) now sets the element in place — previously it replaced the whole array, dropping the other elements.
- External mutation sites routed through the store (expansion array/arithmetic element writes, `unset` element paths, `export -n`); an architectural write-ban test keeps `.value`/`.attributes` writes confined to the store and scope-manager authority files (textual scan; its one blind spot — the aliased mutation pattern in `executor/array.py` — is allowlisted, verifier-proven readonly-guarded on all 10 probe paths, and honestly documented).
- Verifier verdict: PASS-WITH-NITS — 94 lock rows held with zero unintended deltas; alias-bypass hunt found ZERO unguarded sites; 5/5 mutations bite; counts exact. Nits ledgered: the store reaches 5 private ScopeManager members (disclosed Phase-4 coupling debt); two pre-existing nameref edges confirmed out of scope (assoc-key arithmetic through namerefs writes `[0]`; `unset 'r[1]'` through a nameref refuses) — both candidates for the builtins-contracts pass. Suite 13,315 passed / 0 failed (+87); compare-bash 2,075 (+5 golden `varstore_*`).

## 0.656.0 (2026-07-07) - Fix: exact child-state cloning, external env, atomic array mutation, trap/getopts state
- Core-state Phase 1 (docs/reviews/core_state_subsystem_appraisal_2026-07-06.md C1/C2/H2/A3/E1–E3 + the absorbed builtins-appraisal P0/P1.2; all defects probe-verified before work). Every commit flipped its strict-xfail regressions; 26/26 flipped by the end.
- **Exact child cloning** (`ShellState.clone_for_child` replaces construct-plus-overlay): a child's variable/env keysets are exactly the parent's — `unset HOME; (echo ${HOME+set})` no longer resurrects HOME from `os.environ`, seeded defaults (PS4) stay unset, and the discarded fresh-initialization work is gone. Arrays and function metadata are deep-cloned across the child boundary (shared-identity leaks fixed); every state component carries an explicit copy policy (share-immutable / clone-mutable / reset-process-local / recompute-derived), enforced by graph-independence tests that walk parent/child object graphs against an allowlist. Child semantics verified 38/38 vs bash ($$/BASHPID/RANDOM-reseed/subshell trap-reset/…).
- **`env` executes externally** (builtins-appraisal P0, release-blocker class): the in-process "child shell" could be terminated by `env exit 7`, replaced by `env exec`, and its `cd`/`umask`/`ulimit`/`trap` mutated the parent process. Standard `env` now builds the exact child environment and delegates argv directly to the external launcher (no builtin/function resolution — matching /usr/bin/env; the builtins-through-env extension is dropped and ledgered; the one test pinning it pinned divergent behavior). Known bounded edge documented in-code: a previously-hashed command with `env PATH=override` execs the hashed path (CommandResolver campaign owns the fix).
- **Atomic array mutation invariants**: a failed operation no longer mutates — readonly arrays survive `unset 'a[0]'`, `declare a+=(…)`, `local` append, and `mapfile -O` byte-for-byte (build-into-copy, committed after the readonly check); negative-subscript `unset` uses the same sparse-aware index resolution as reads/writes (`unset 'a[-2]'` on indices 5,10 is a no-op like bash, was removing index 5).
- **Signal-disposition lease**: process-global handlers installed by trap management are snapshotted and restored on `Shell.close()` (defense-in-depth for future in-process shells — the observable USR1-leak fix came with env going external). `trap -p` output is now reusable shell input (proper single-quote escaping via one shared helper — three byte-identical quoting copies deduplicated); pending traps use a deque.
- **Typed `GetoptsState`**: cursor bound to argument source, word, and an OPTIND-write generation — changing the argument list (or rewriting OPTIND, even to the same value) resets the within-word cursor instead of crashing (`string index out of range`).
- **Sparse array enumeration is O(stored)** (was O(max_index) — a DoS surface: `a[10000000]=x; "${a[*]}"`), with an operation-count guard test.
- Adversarial verifier verdict: PASS-WITH-NITS — copy-policy map re-derived complete, deep graph-independence attack (including containers the dev's walker skips) clean, 38-row child battery, 20-case env table, 5/5 mutations bite, exact count reconcile. Nit: the env/PATH hash edge (documented, deferred to #56). Suite 13,228 passed / 0 failed (+69); compare-bash 2,065 (+16 golden `cstate_*`).

## 0.655.0 (2026-07-06) - Feat: locale service — collation, locale-gated case, host-faithful character classes
- Implements Stages 1–3 of docs/architecture/locale_service_design_2026-07-06.md (promoted with this release from the investigation pass; expansion-plan finding 5). Backend decision (user-approved): host-libc `iswctype` via ctypes with a pure-Python fallback — byte-faithful to whichever bash runs on the host, so conformance stays `assert_identical` on macOS AND the Linux nightly, including places platforms genuinely disagree (macOS counts `٣`/`３` as `[[:digit:]]`; glibc doesn't).
- **New `psh/core/locale_service.py`**: effective LC_CTYPE/LC_COLLATE computed at startup via bash's `LC_ALL > LC_* > LANG` precedence (empty skipped, unusable warned→C like bash); `setlocale` only when non-C resolves.
- **Collation** (`strxfrm`/`strcoll`): glob-result ordering and `[[ < ]]`/`[[ > ]]` now match bash per locale — the investigation disproved the in-code claim that macOS collation ≈ codepoint order (`echo *` under en_US.UTF-8 is dictionary-ordered: `٣ _x 3 a B e é z`); `test`/`[` `<` deliberately stays byte-order (bash's own behavior in every locale — direct evidence overrode the design prose). Deleted the false glob.py comment.
- **Locale-gated case conversion**: `^^`/`,,`/`~~`, `declare -u/-l`, and `${x@U/@L/@u}` are C-mode ASCII-gated like bash (`café^^` → `CAFé` under C); fixes the pre-existing `${x@U}` ß→`SS` bug (now `ß`, routed through the length-safe mapping).
- **Host-faithful POSIX character classes**: `[[:alpha:]]` etc. in `[[ == ]]`, `case`, `${var#pat}`, `[[ =~ ]]`, and pathname expansion resolve via lazy per-class iswctype sweeps compiled to cached regex ranges (~0.35s first use, ~ms cached, C-locale fast path untouched — 1.04× vs old). `[[ é == [[:alpha:]] ]]` is true under UTF-8 locales, matching bash. `shopt globasciiranges` recognized (default on; `-u` semantics ledgered as deferred).
- Suite hygiene: conftest pins the suite to LC_ALL=C (ambient-deterministic — verified identical under en_US.UTF-8 and empty ambient); ~45 locale conformance tests control their own env; conformance-framework decode fixed to utf-8/surrogateescape (symmetric for psh and bash).
- Deliberate limitations ledgered (§ Locale Support): startup-only locale (Stage 4 deferred), `shopt -u globasciiranges` off-behavior, 8-bit locales, the pre-existing C-locale byte-vs-character model — **and the verifier-found PEP 538 caveat**: in *unpinned* bare-C environments CPython coerces LC_CTYPE to UTF-8 before psh reads it, so character classes behave UTF-8 where bash-C would not (explicit LC_ALL=C is fully faithful); the module's "nothing set = C mode" claim was corrected and coercion detection deferred to Stage 4.
- Adversarial verifier verdict: PASS-WITH-NITS — ~110-row independent truth tables (0 mismatches vs host bash in every explicitly-set locale), ctypes fallback/garbage-locale/astral attack clean, 4/4 mutations bite, conftest-pin audit clean (decode fix proven symmetric), merge with v0.654 validated (zero conflicts, 8-case seam battery). Suite 13,159 passed / 0 failed on the merged tree; compare-bash 2,033 (no golden — locale tests are conformance-tier).

## 0.654.0 (2026-07-06) - Refactor: honest parser configuration, typed heredoc attachment, unified diagnostics
- Parser Campaign 2 (docs/reviews/parser_subsystem_appraisal_2026-07-05.md findings 2/3/9/10/11/13 — the "remove dishonest configuration and recovery" cluster). Deletion-heavy; every removal backed by a grep-verified consumer map, independently re-derived by the adversarial verifier (no missed consumer found).
- **Honest parser configuration**: the never-consulted feature gates (`parsing_mode`, `enable_arithmetic`, `allow_bash_*`) and their dead guard methods are deleted — grammar dispatch never read them ([[ ]] and (( )) were always parsed; POSIX restrictions are runtime/lexer concerns). `ParserConfig` remains as a deliberately empty extension point; `clone()` now rejects unknown fields (was: silent typo-to-noop). The parser factory validates parser names (`--parser bogus` fails cleanly; `rd`/`recursive_descent`/`combinator` accepted explicitly). The `parser-config`/`parser-mode` builtins are trimmed to their honest subset — which also fixed a latent crash (`parser-config enable arrays` died on an unregistered option).
- **Error-collection mode removed**: `collect_errors` could return fabricated, executable ASTs for invalid input (a missing `fi` yielded a completed conditional); nothing on any live path ever set or harvested it. `consume()` now always raises; new regression tests pin that a syntax error can never produce a Program that executes. The `set -o collect_errors` option name stays registered (round-trip surface) but is inert.
- **Typed heredoc attachment**: heredoc bodies attach when the `Redirect` node is constructed (heredoc map threaded through the parser context), replacing a 26-complexity `hasattr()` tree-walk with delimiter-guessing fallback. Fail-loud on missing keys; the fallback was proven unreachable from production (64-probe battery incl. eval/source/interactive-accumulator paths, byte-identical).
- **One ParseError interface**: `summary` (short reason) vs `render()` (rich, with caret); `str()` == `render()`. Execution error output byte-identical (43-input battery); analysis modes (`--validate` etc.) deliberately upgraded from bare one-liners to the rich diagnostic (source-line caret in analysis awaits finding 12's source threading).
- **AST pretty printer rewritten** (was rotted: probed obsolete node fields, printed raw dataclass reprs): now generic dataclass-field traversal, rot-proof by construction; structural tests replace substring asserts. Tree/dot/sexp renderers untouched (76-comparison scoping proof). Known cosmetic gap: raw lexer-Token reprs for array-subscript indices (strictly better than before; ledgered).
- Docs truth-up: parser/CLAUDE.md, user guide, ARCHITECTURE.md, and (verifier nit) the fictional §2.5/2.6 of docs/subsystem_internals.md — which described error-recovery modes and config fields that never existed.
- Verifier verdict: PASS — repaired the one missing per-commit gate (clean), re-derived all consumer maps, confirmed all 6 dev deviations, exact count reconcile (+8 net; compare-bash exactly baseline). Suite 13,076 passed / 0 failed.

## 0.653.0 (2026-07-06) - Fix: collision-safe fd remapping + O(1) rolling pipelines
- The shared fd campaign — the work item BOTH the execution plan (findings 5/6, Phase 4) and the expansion plan (finding 2) specified as one utility, built once. All four verified defects fixed byte-matching bash 5.2.26.
- **New `psh/io_redirect/fd_remap.py::remap_fds(mappings, owned=, protected=)`** — collision-safe child descriptor wiring (two-phase: dup sources to CLOEXEC high temps, then place onto destinations; handles src==dst, cross-mapped destinations, cycles, `|&` fan-out; closes owned fds except protected destinations; closes everything on any failure). Now the single source for child fd setup across pipelines, command substitution, and process substitution.
- **Pipelines survive closed standard descriptors** (`exec 0<&-; printf x | cat` → `x`, PIPESTATUS `0 0` like bash; closed-stdout variant likewise) — previously `os.pipe()` handing back fd 0/1 met a no-op dup2 plus a blanket close loop that destroyed the live endpoint. 40/40 closed-fd combinations match bash. (Verifier finding, noted in-code: rolling construction's sync-pipe-first ordering is co-responsible for the fix; the remap is kept as the explicit guarantee.)
- **Rolling pipeline construction**: one pipe per boundary, parent closes as it advances — parent holds ≤3 data descriptors regardless of pipeline length (was 2·(N−1) → EMFILE at ~130 commands under the default fd limit; a 300-stage pipeline now succeeds under `ulimit -n 128`, matching bash). Child close-work drops O(N)→O(1). The leader/member process-group and sync-pipe protocol is preserved verbatim (60-case choreography battery: zero deltas vs the old implementation).
- **Command substitution survives closed 0/1** (`exec 0<&- 1>&-; x=$(printf x)` → `<x>` rc 0 like bash), and its child lifecycle is hardened: the child is reaped even when reading fails, SIGCHLD handling and pipe fds are restored/closed on fork-failure paths, and a signalled child yields 128+signal.
- **Process substitution had the same hazard on both sides** (found by the campaign's audit): read-side endpoint landing on a closed fd 1 and write-side FIFO opening as fd 0 both fixed via the shared utility; file-redirect dup paths audited clean.
- Adversarial verifier verdict: PASS-WITH-NITS — 92-check utility attack with step-level fault injection, independent 40+8+17-combo closed-fd matrices, 60-case choreography battery (0 deltas), EMFILE/O(1)/zombie reproduction, and the racy-PIPESTATUS normalization proven genuine (bash itself flakes middle-stage 141 under load) and unable to mask real defects. Nits: the pipeline remap is defense-in-depth no test isolates (documented in-code); the cmdsub failure-path reap is correct but only reachable under injected failures. Suite 13,068 passed (+68); compare-bash 2,033 (+4 golden `fdremap_*`).

## 0.652.0 (2026-07-06) - Fix: executor dispatch, redirection ownership, assignment status, POSIX builtins, jobs, TIMEFORMAT
- Executor Phase-1a (docs/reviews/execution_subsystem_improvement_plan_2026-07-05.md findings 1–4, 7–10, 15–16; all 12 behavioral probes verified at v0.650; truth-tabled vs bash 5.2.26).
- **Dispatch**: a quoted empty command (`''`, `"$empty"`) now performs command lookup → `command not found`, exit 127, and a prefix assignment before it no longer persists (was: silently treated as no-command, exit 0, prefix persisted). Backslash-quoting (`\f`) no longer bypasses function lookup — it only suppresses aliases, like bash (the executor bypass was provably dead for alias purposes: the lexer preserves the backslash in the token).
- **Redirection ownership**: background builtins and functions no longer evaluate redirections twice (the parent installed them, then the child re-installed — duplicating command substitutions, file opens, and side effects); background placement now selects child-deferred setup, and background builtins route through the shared shell-child runner (restoring EXIT-trap behavior in `eval '…' &`). Compound-command redirections now cover header expansion: `for x in $(cat); do …; done < file`, `case $(cat) in … esac < file`, `select`, and C-style-for initializers all read the redirected input (and a failed redirect skips header expansion, like bash).
- **Assignments**: array assignments join the normal status/transaction model — `a[0]=$(false)` → 1, `a=($(exit 7))` → 7, background assignment status observable via `wait`, first-failure stops later assignments, and prefix-position array syntax (`a[0]=x cmd`) diagnoses an invalid identifier without creating the array. Prefix array `+=` is now pure and env-safe: the array is snapshotted and restored, the child environment sees the scalar view, and no array object can reach `execve` (was: a raw Python type error leaked to the user AND the array stayed mutated).
- **POSIX special builtins**: complete registry (adds `.` and `times`), mode-aware — prefix assignments persist for special builtins ONLY in posix mode (default mode now matches bash: `X=new :` leaves X unset — this deliberately FLIPS a previously documented psh divergence), and special builtins take lookup precedence over functions in posix mode, re-resolved live when the option toggles.
- **Jobs**: a pipeline with completed + stopped members is now classified Stopped (was Running), so `%+` promotion and `jobs` output match bash.
- **`TIMEFORMAT`** implemented: `%R/%U/%S/%P`, `%%`, precision 0–3, `l` long form; unset → bash default shape; empty → no report; `time -p` unchanged.
- Deliberate divergences (documented): integer-array `+=` prefix — bash 5.2.26 emits a garbled control-byte syntax error (verified by od), psh runs the command sanely (psh_only golden); malformed TIMEFORMAT directives render literally where bash errors.
- Reported (pre-existing, not fixed): parser doesn't recognize `a[0]=2` as an assignment in non-first bare-assignment position; posix mode doesn't reject *defining* a function named after a special builtin (lookup precedence is correct).
- Adversarial verifier verdict: PASS-WITH-NITS — independent per-finding batteries all bash-matching, 5/5 mutation tests bite, both divergences confirmed with raw evidence, cross-campaign golden edit audited legitimate, merge with v0.651.0 validated (7/7 seam-interaction battery, BLOB-UNION golden resolution). Suite 13,000 passed (+135); compare-bash 2,025 (+45 golden `exec_p1a_*`). README project statistics refreshed (14,104 collected / 538 test files).

## 0.651.0 (2026-07-06) - Fix: expansion byte policy, brace sentinels/budget, tilde extent
- Expansion Phase-1a (docs/reviews/expansion_subsystem_improvement_plan_2026-07-05.md findings 1/3/4/10, all probe-verified at v0.650; truth-tabled vs bash 5.2.26).
- **Command substitution byte policy**: NUL bytes are stripped before decode with one bash-style warning per substitution (`warning: command substitution: ignored null byte in input`); captured output decodes with `surrogateescape` instead of lossy replacement, and the output/exec/redirect boundaries re-encode symmetrically (forked-builtin `os.write`, stream reconfigure at entry, redirect/heredoc wrappers; `execve` already round-trips via `fsencode`). All 255 non-NUL byte values now round-trip byte-exactly through cmdsub → stdout / files / argv / env / here-strings, matching bash (verified per-byte across 5 sinks). Known residual (pre-existing, out of scope): psh's `printf '\xff'` renders a codepoint, not a raw byte; `read`/`mapfile` input paths still decode with replacement.
- **Brace expansion no longer corrupts private-use Unicode**: the in-band placeholder scheme now allocates placeholders per expansion, skipping every code point present in the input — a literal U+F8FF is preserved (was deleted) and a literal U+E000 no longer decodes as phantom quoted content. Interim design, documented in-module; the structured Word-stage relocation remains the long-term plan.
- **Brace expansion budget is preemptive and loud**: sequence/product cardinality is computed before generation (`{1..1000000000}` now fails in ~0.2s — bash itself grinds >30s), the limit is raised 10,000 → 100,000 so everyday large ranges like `{1..20000}` expand byte-identically to bash, and exceeding the budget is a loud syntax-class error (exit 2) instead of the old silent literal restore. Deliberate divergence (bash has no limit) documented in docs/user_guide/17_differences_from_bash.md §17.3.
- **Tilde expansion identifies its extent within a word**: `HOME=/h; X=hello; echo ~:$X` now prints `/h:$X` like bash — a colon-bounded tilde prefix expands and the remainder of the tilde word is kept verbatim (unexpanded), while a slash-bounded prefix resumes normal expansion; quotes/backslashes anywhere in the tilde word disable it. 56-row verifier truth table green except one cosmetic residual (`~:${X}` renders `$X` without braces — parser folds bare `${NAME}` ≡ `$NAME`; documented).
- Adversarial verifier verdict: PASS-WITH-NITS (the tilde residual only; 4/4 mutation tests bite; 22-case PU-allocator attack and 255×5 byte matrix all byte-exact vs bash; count arithmetic reconciled exactly). Suite 12,865 passed (+68); compare-bash 1,936 (+12 golden `expn_p1a_*`).

## 0.650.0 (2026-07-06) - Fix: parser hardening + five bash grammar boundaries
- Parser-appraisal Campaign 1 (docs/reviews/parser_subsystem_appraisal_2026-07-05.md findings 4/6/14 + 5a–5e, all probe-verified before work). Truth-tabled against bash 5.2.26 throughout; grammar fixes mirrored in the combinator where parity is pinned.
- **Hardening:** a sentinel-free token list no longer hangs `Parser.parse()` forever (out-of-range peek → stable synthetic EOF, timeout-protected regression test); standalone parser use (no `Shell`) converts `RecursionError` to a clean "input too deeply nested" `ParseError` under the default interpreter limit (shell-context behavior and `MAX_NESTING_DEPTH` untouched); the parser no longer mutates caller-owned lexer tokens (post-pipe `TIME` demotion now builds a local WORD copy — both parsers; token-snapshot test).
- **Grammar (each previously accepted where bash rejects, or vice versa):** C-style `for` body must be `do … done` OR a brace group `{ … }` — `do` is no longer silently optional, and the bash brace-body form `for ((…)) { … }` is now supported; array initializers and element values require lexical adjacency (`a= (x y)`, `a += (x y)` → syntax error like bash; `a[0]= v` no longer swallows the non-adjacent word); `[[ x =~ … ]]` operands get an explicit policy (unquoted `;`/`&`/redirect operators and unbalanced parens are parse errors — bash-measured, including inside `[…]` brackets; alternation `|`, quoted/escaped metacharacters, POSIX classes stay legal); empty case-pattern alternatives (`x|)`, `(|x)`, `()`) are rejected (quoted-empty `''` patterns stay legal).
- Frozen array characterization corpus: exactly 6 entries surgically re-captured — they pinned the very divergences fixed here (each re-verified against bash; other 40 byte-identical; verifier audited the diff line-by-line).
- Two PRE-EXISTING combinator gaps surfaced, documented (not fixed — educational parser, own future campaign) in docs/guides/combinator_parser_remaining_failures.md: word-then-`(subshell)` juxtaposition accepted as two statements (`echo (x)`); `[[ =~ ]]` single-token operand boundary (rejects legal multi-token regexes, over-accepts illegal single tokens). RD-side test pins `echo (x)` → ParseError.
- Documented residuals (both shells error, different phase): `a =(1 2)` bash parse-error vs psh command-not-found; `=~ a>b` accepted (lexer folds one WORD; bash rejects); lone-`|` regex differences are engine-level (Python `re` vs `regcomp`).
- Adversarial verifier verdict: PASS-WITH-NITS (2 cosmetic doc nits, fixed at integration; 4/4 mutation tests bite; compare-bash arithmetic reconciled exactly). Suite 12,797 passed (+154); compare-bash 1914 (+25 golden `parsefix_*`).

## 0.649.0 (2026-07-05) - Fix: lexer command-position, shell whitespace, and POSIX option propagation
- Lexer Phase-1 (docs/reviews/lexer_implementation_improvement_plan_2026-07-05.md defects 1–3, re-verified live at v0.647; all fixes truth-tabled against bash 5.2.26 before coding).
- **Keyword-looking arguments no longer flip lexer command position** (`psh/lexer/modular_lexer.py`): `echo if [[ x` now prints `if [[ x` like bash instead of a parse error. `_update_command_position_context` captures the prior command position and gates both the keyword-value transition and the `case` case-depth transition on it — an argument that merely spells `if`/`while`/`case` can no longer enable reserved syntax for the next token. KeywordNormalizer already gated correctly; the observable bug was the lexer/normalizer disagreement. `for`/`case` subject-position handling already matched bash observably (probed; the full lexical-state machine remains future work).
- **Shell whitespace, not Python whitespace** (`operator.py`, plus required companions `literal.py`, `comment.py`): operator decisions now use the canonical `is_whitespace()` (space/tab/newline) instead of `str.isspace()`. Fixes the `!<NBSP>false` exit-status INVERSION (psh returned 0 where bash returns 127), `{<NBSP>…` brace-group misclassification, and CR-before-`#` comment swallowing (`echo a<CR>#b` kept intact like bash). New guardrail test bans `.isspace()` from lexer production code.
- **`posix` shell option now reaches the lexer** (`psh/lexer/__init__.py::_make_config`, `visitor_modes.py`): `LexerConfig.posix_mode` is set from shell options, activating the previously-dead lexer-internal POSIX paths (`$var` name extraction, named-fd `{NAME}>` redirects, assignment-shape checks). posix OFF is byte-identical (verified over 77-source token-stream diff); posix ON now matches `bash --posix` where comparable (e.g. `exec {ünïfd}>f` fails cleanly in both). No double-gating with the v0.629 executor-level identifier policy — the layers own distinct positions (verified byte-identical error surfaces). The legacy `strict` tokenize parameter is confirmed a no-op (batch/interactive configs identical) and retained for API stability.
- Verification: dev batteries 65+128 probes (14 and 26 pre-fix divergences → 0); adversarial verifier PASS — independent 81+86-case batteries, deviation refute-attempts (the `literal.py` companion proven required via hunk-revert → fail-loud RuntimeError), T2-C pins unregressed, posix double-gating audit clean, merge with v0.648.0's incremental heredoc discovery verified with a 15-case interaction battery. Suite 12,643 passed (+51 unit, +19 golden `lexfix_*`); compare-bash 1864 green.
- Reported (pre-existing, not fixed): the input layer splits `-c` strings on a leading bare CR (bash treats `\r#b` as one word, exit 127); `POSIXLY_CORRECT=1` doesn't set the posix option at `-c` tokenize time.

## 0.648.0 (2026-07-05) - Perf: heredoc tokenization is linear (was quadratic in preceding lines)
- Lexer Phase-2 (docs/reviews/lexer_implementation_improvement_plan_2026-07-05.md defect 4). `HeredocLexer.tokenize_with_heredocs` re-lexed the whole accumulated command prefix through a fresh `ModularLexer` for every physical line, making any script with a heredoc O(N²) in the lines preceding it (measured 5.3s CPU at 800 lines). Discovery is now incremental: each logical command is tokenized once, seeded with the `LexerContext` the previous command ended in (new optional `ModularLexer(initial_context=…)` + `LexerContext.copy()`); the inter-command newline is replayed so the command-position transition still fires. Measured after: 30ms at 800 lines, chars-lexed ratio flat at ~2.0 (was growing 51→401).
- Deliberately NOT the review doc's growing-input `LexerSession`: a growing input rebuilds the assignment-prefix map (keyed on input identity) per line — a second hidden quadratic. Per-command carry avoids both.
- ZERO tokenization change: returned tokens still come from the unchanged full-text pass; 64-source dev lock + 67-case adversarial verifier corpus (201 A/B runs incl. base_line/source_name variants, warning line numbers, error-surfacing timing) byte-identical; frozen token-stream characterization corpus passes UNCHANGED (no re-freeze). Adversarial verifier verdict: PASS (context-carry deviation confirmed-safe — `LexerContext` is all-scalar, no aliasing possible).
- New deterministic scaling guard `tests/unit/lexer/test_heredoc_scaling.py` (chars-lexed ≤ 3×source length; proven to fail on the old implementation; no wall-clock, xdist-safe). Suite 12,573 passed (+2).

## 0.647.0 (2026-07-05) - Refactor: canonical `Program` AST root (root-shape compatibility layer removed)
- Implements docs/reviews/rd_parser_root_shape_compatibility_analysis_2026-07-04.md (committed with this release). Both parsers now return one stable `Program` root for every parse (empty input included); the RD parser's content-dependent `Union[CommandList, TopLevel]` and its reverse-structural unwrapping (`_simplify_result` / `_bare_top_level_compound` / `_BARE_TOP_LEVEL_TYPES`) are deleted. Bare compounds keep normal `AndOrList → Pipeline` ancestry; nested bodies remain `StatementList`.
- Executor: the old `visit_TopLevel`/`visit_StatementList` loops consolidated onto one `_execute_sequence` with an explicit `SequenceContext` — the exact root-vs-nested deltas (KeyboardInterrupt catch; out-of-loop `break`/`continue` announce/continue vs silent/stop) are now named flags with dedicated tests (`tests/unit/executor/test_execute_sequence.py`), not container-identity accidents. `Shell.execute_program()` replaces the root-type branch in source processing.
- Combinator parser aligned: returns `Program`, and its own bare-compound unwrapping (two sites in `pipelines.py`) removed — RD and combinator ASTs now compare directly with NO root normalization in the differential tests (`_program_items`/`_normalize_wrappers` deleted).
- Formatter derives layout from statements (single-`\n` join; the old `TopLevel` `\n\n` paragraph branch was proven unreachable from real parser output). `TopLevel` and the `CommandList = StatementList` alias are fully removed; architecture guardrail tests pin the new contract (`tests/unit/parser/test_root_contract.py`, adapted top-level grammar guardrails).
- Lexer: recognizer registry re-raises `RecursionError` (an EXPECTED shell error per the core taxonomy) instead of masking it as an internal defect — keeps the `maximum function nesting level exceeded` conversion working now that `_execute_sequence` adds a frame to eval-recursion depth.
- Behavior: locked on 113-script + 41-formatter-golden dev batteries AND an independent adversarial 270-run A/B battery (0 diffs); compare-bash 1828 green. ONE intended pathological delta: a trap action running `break`/`continue` against an executing top-level loop now announces and continues, closer to bash (`trap 'break' DEBUG; for i in 1 2 3; do echo $i; done; echo done` → prints `done`, exit 0; previously silent exit 1). `--debug-ast` renders show the new root shape by design.
- Suite +147 tests (12,571 passed / 0 failed). Adversarial verifier verdict: PASS-WITH-NITS (the delta above, documented here; mutation tests confirm the new guardrail and executor tests bite).

## 0.646.0 (2026-07-05) - Fix: combinator parser parity + randomized RD-vs-combinator differential (reappraisal #18 Tier-2 T2-H)
- TIER-2 cluster — closes combinator-only parser divergences and adds a drift-detector. Combinator-only source changes; RD/default parser untouched. Adversarial verifier PASS-WITH-NITS (2 doc-accuracy nits, fixed before merge); full local gate green; ruff + mypy clean. Final Tier-2 release.
- **Mid-pipeline `time` (M-p4):** `echo a | time cat` was rejected by the combinator ("Expected command"); RD and bash treat a non-leading `time` as the external `time` command. `time` lexes as a TIME token in every position, but the combinator only consumed it as a leading prefix. Fix: demote a post-`|` TIME token to WORD in the combinator pipeline loop, mirroring RD's `parse_pipeline_component`. `psh/parser/combinators/commands/pipelines.py`.
- **Permissive function names (M-p5):** the combinator rejected `9()`, `123abc()`, `a.b()`, `a+b()`, `[x()`, `echo:()`, etc.; bash and RD accept any name-able token composite that isn't an assignment or reserved word. Rebuilt the combinator's function-name parser on the shared `peek_composite_sequence` machinery and moved assignment(`ASSIGNMENT_WORD_RE`)/keyword rejection into the POSIX-form commit gate, mirroring RD's `is_function_def`. Preserves `arr=()`→array-init and `a=b()`/`a[0]=b()`→syntax error. `psh/parser/combinators/control_structures/structures.py`.
- **C-for empty-middle (M-p3):** confirmed ALREADY fixed by the Tier-1 T1-5 collector consolidation — no combinator code changed; `for ((i=0;;i++))` / `((;;))` / `((;i<3;))` match RD==combinator==bash at behavior and AST level. Pinned in the parity corpus.
- **Randomized RD-vs-combinator differential (drift-detector both parser auditors asked for):** new `tests/parser_differential/test_combinator_random_differential.py` — a grammar fuzzer that asserts RD and combinator produce equivalent ASTs (up to an inert single-element `AndOrList→Pipeline` wrapper normalization, proven not to mask content divergences) or matching parse-error outcomes. Rides the local gate at a fast default (150 snippets, ~0.3s); the nightly runs it at 40,000 snippets with a per-run rotating seed (`github.run_number`). Seed/iters are env knobs (`PSH_DIFFERENTIAL_SEED`/`_ITERS`), echoed and embedded in any failure for one-line reproduction. Verified 0 divergences across 40,000 snippets / 80 seeds, and mutation-tested: reverting either new fix turns the differential RED at the default seed.
- Locked by 19 parity-corpus entries + 4 updated/added combinator unit tests + 9 golden cases (`r18t2_combinator_*`, `--compare-bash`; the timing-nondeterministic `time` cases are correctly excluded from golden and pinned by the differential/parity instead). Five pre-existing parity gaps the fuzzer surfaced (compound as a non-leading pipeline stage; `time` on a compound; composite `case` subject; `${…}` in for-items/case-subject; bare `]` as a command name) are documented and excluded from the fuzzer grammar as candidates for a future parity cluster.

## 0.645.0 (2026-07-05) - Fix: interactive cluster — monitor $-, PROMPT_COMMAND, bg completion notices, completion (reappraisal #18 Tier-2 T2-F)
- TIER-2 interactive cluster (5 items), pinned to bash 5.2.26 (pty-verified where needed). Adversarial verifier PASS-WITH-NITS; the one nit (a factually-wrong SIGPIPE claim) fixed before merge (see below). Full local gate green; ruff + mypy clean.
- **`$-`/`set -o monitor` now on in an interactive job-control shell (M-i1):** an interactive psh with job control now carries `m` in `$-` and reads `set -o monitor` as on (`bash -i` → `himBHs`, matched exactly); `-c`/scripts stay off. Cosmetic — the only reader of the `monitor` option is the `set -o` display; real job control keys off tty/job-control support, so this is side-effect-free.
- **`PROMPT_COMMAND` implemented (M-i2):** run before each PS1 (not PS2) — string form and the bash-5.x array form (each element in order); preserves the user's `$?` across the hook; excluded from history; runs before the first prompt like bash.
- **Background completion notices no longer mislabel as "Done" (M-i3):** a killed/terminated/nonzero-exit bg job now shows the correct state (`Terminated: 15`, `Killed: 9`, `Interrupt: 2`, `Hangup: 1`, `Quit: 3`, `Exit N`, `(core dumped)` when applicable), byte-exact field width and `[N]+ ` prefix. A new `background_completion_label()` names every state (the bg path announces SIGINT and needs Done/Exit-N logic the foreground diagnostic lacks, so it's a sibling of `abnormal_termination_message`, not a reuse).
  - **SIGPIPE (fixed after verification):** `background_completion_label()` names `Broken pipe: 13` like any other signal; the notice is withheld ONLY in an INTERACTIVE shell (where bash treats a broken pipe at the terminal as benign) — a non-interactive script announces it. This corrects the original commit, which stayed silent for SIGPIPE unconditionally and whose comment/tests wrongly claimed bash agrees; bash 5.2.26 announces `Broken pipe: 13` for a non-interactive bg SIGPIPE. The foreground diagnostic stays silent for SIGINT and SIGPIPE (unchanged, matching bash). The job is reaped either way.
- **Completion doc truth-up (M-i4):** psh completion is path-only; the command-completion claims in user-guide ch14 & ch17 were corrected to match reality (a genuine command-completion engine is a larger feature, deferred). No `CLAIM_TESTS` dangle (Programmable completion is a No-row).
- **Trailing space after a unique completion (M-i5):** a unique file completion now ends with a space and a unique directory keeps `/` (no space), matching bash.
- Locked by unit tests for the bg-notice label matrix + interactive/non-interactive SIGPIPE policy, pty end-to-end tests (isolated HISTFILE, stable ×3), and 3 golden cases (`r18t2_interactive_*`, `--compare-bash`). Pre-existing out-of-scope items noted: `psh -c` from a tty wrongly setting `i` in `$-`; `<subshell>` command text in bg notices; quoted-completion space; and psh's notification-timing model (async `set -b` notices in a non-interactive `-c` fire at reap points, not truly asynchronously).

## 0.644.0 (2026-07-05) - Feat: ulimit builtin + history file-sync flags; honest mapfile -C/-c (reappraisal #18 Tier-2 T2-G)
- TIER-2 builtins feature cluster ("full where tractable" per the campaign scope). Adversarial verifier PASS-WITH-NITS, tests mutation-proven non-vacuous (the exit-persistence false-green trap was specifically checked). Full local gate green; ruff + mypy clean. Combined B∩G `shell_state.py` behavior verified after merge (B's `local` attr-merge / append-fold coexist with G's history dispatch).
- **`ulimit` implemented as a real builtin** (`psh/builtins/limits.py`, registered in `builtins/__init__.py`). Root cause of the prior gap: psh had no `ulimit` builtin, so it fell through to the external `/usr/bin/ulimit` — which runs in a child (so `ulimit -n 512; ulimit -n` never persisted) and doesn't exist on Linux. It now calls `resource.setrlimit` on the psh process itself (inherited by children), matching bash's shell-builtin semantics. Full support for every resource Python's `resource` exposes (`-c/-d/-f/-l/-m/-n/-s/-t/-u/-v`, plus Linux `-e/-i/-q/-r/-x`), soft/hard via `-S/-H`, `-a`, the `unlimited`/`hard`/`soft` keywords, and correct 512-byte block-factor scaling on both GET and SET. `ulimit -a` is byte-identical to bash 5.2 except the pipe-size line (see honest errors).
- **`history` file-sync/edit flags implemented** (`shell_state.py` dispatch + new `HistoryManager` methods): `-w` (write all), `-r` (read/append), `-a` (append only entries new since last sync — no duplication across repeated calls), `-n` (read only unread), `-d offset` (1-based, negative-from-end, and start-end ranges), `-s` (store one entry without executing); `-c` already existed. Previously all of these were misreported as "numeric argument required". Also fixed two latent divergences: bare `history` now lists the whole history (was hardcoded to the last 10), and `-5` is now an invalid option (was mis-parsed as a count).
- **`mapfile`/`readarray -C callback` / `-c quantum`: honest `rc2` "not supported"** — verified to error BEFORE reading stdin (no silent input consumption; the array is never created), and the rest of `mapfile` (`-t/-n/-s/-O/-d`) is unchanged. (The brief's worry about silent consumption was already handled; this release locks it with regression tests.)
- **Honest `rc2`/`rc1` where a feature can't be faithfully implemented** (per "full where tractable"): `ulimit -p` (pipe size — bash itself can't set it and there's no portable Python API; the sole `ulimit -a` divergence), `history -p` (needs the interactive `!`-expansion engine), and — on macOS only — setting `RLIMIT_STACK` (Python's `resource` raises even for values bash accepts; surfaced as an honest error rather than silent-wrong; works on the Linux nightly, so stack-SET is not conformance-tested).
- Docs: `ulimit builtin` added as a "Full support" row in ch17 §17.5 with a mapped conformance test (`tests/conformance/bash/test_ulimit_conformance.py`) + `CLAIM_TESTS` entry (claims-have-tests meta-test passes); `ulimit` removed from the pinned-builtins `BASH_SCOPED_EXTRAS` allowlist; `history` row/prose updated. Locked by golden cases (`r18t2_builtins_*`, `--compare-bash`). 3 stale `history` xfails un-marked (their "not implemented" reasons are now false) and 3 vacuous ones rewritten to use `history -s`.

## 0.643.0 (2026-07-05) - Fix: core state — temp-env scoping, id vars, attribute/append plumbing (reappraisal #18 Tier-2 T2-B)
- TIER-2 cluster, each item pinned to bash 5.2.26. Adversarial verifier PASS-WITH-NITS ("temp-env layer airtight, ship it"; one informational nit — HOSTTYPE/OSTYPE *values* derive live from `os.uname()` vs bash's build-time triplet, an improvement over the prior absent state, no test pins exact values). Full local gate green; ruff + mypy clean. The D∩B case-fold overlap (declare -u/-l) was verified byte-identical to bash after the merge (İ→i, ß unchanged, append-fold →THREE all hold).
- **temp-env prefix + `declare -g`/`export` now survives function return (M-c4):** modelled as bash's temporary-variable-context — `command.py` pushes a dedicated *exported* temp-env scope (`is_temp_env`) under the function's locals before applying a prefix assignment, and pops it in `finally` (LIFO with the function frame, exception/return-safe). A body's `declare -g X=…` writes the global and an `export X=…` writes past the temp layer (both survive return); a plain body write lands on the temp layer and is discarded on return; the temp value is temporary like bash (`a=(1 2 3); a=x true; echo "${a[@]}"` → `1 2 3`). Local-shadow, nested/recursive functions, subshell-in-function, early return, trap-firing-mid-function, and errexit bodies all match bash.
- **`UID`/`EUID`/`PPID` are now readonly (M-c5)** — seeded `declare -ir` at startup; assignment and `unset` error like bash; shown in `declare -p`/`readonly -p`.
- **New special variables (M-c6):** `BASHPID` and `SRANDOM` as computed-on-read specials (assignment ignored, `unset` deactivates) — `BASHPID` differs from `$$` inside a subshell/command-sub, `SRANDOM` yields a fresh 32-bit value each read and is not affected by the `RANDOM` seed; `HOSTNAME`/`OSTYPE`/`MACHTYPE`/`HOSTTYPE` as `os.uname()`-derived ordinary startup variables (inherited values preserved).
- **T1-3 leftovers, all pinned to bash:** `local` re-declaration now merges existing attributes (`local -u x=ab; local x+=cd` → `ABCD`; `local -i n=5; local n+=3` → `8`; a value-less `local x` no longer tombstones an existing local; a fresh `local x` ignores an outer `x`'s attributes); array-element case/integer transform applied on append (`declare -u a; a+=(three)` → `THREE`, indexed and associative); nameref scalar-prefix no longer leaks `export` (`declare -n r=a; r=x true; declare -p a` → `declare --`); integer-array element-0 `+=` arithmetic-adds (`declare -ai a=(1 2 3); a+=10` → `11 2 3`).
- Locked by `tests/unit/core/test_r18t2_corestate.py` (41 cases) + 10 golden cases (`r18t2_corestate_*`, `--compare-bash`). Three out-of-scope items confirmed genuinely pre-existing on main and deferred: nameref-to-array-*element* prefix leak; `declare -p BASHPID`→not-found (uniform across ALL computed specials — `RANDOM`/`SECONDS`/`LINENO`/`EPOCHSECONDS` too); Turkish `İ` under `declare -l` (now fixed by T2-D, which integrates ahead of this).

## 0.642.0 (2026-07-05) - Fix: arithmetic/eval error-path edges (reappraisal #18 Tier-2 T2-A)
- TIER-2 bug-fix cluster (5 items), each pinned to bash 5.2.26. Adversarial verifier PASS-WITH-NITS — both routing deviations VINDICATED (see below); the one nit (recursion off-by-one) fixed to exact parity before merge. Full local gate green; ruff + mypy clean.
- **Compound-assign reads LHS before evaluating RHS:** `$((c=1, c+=c++))` gave 3, bash gives 2 — the current LHS value must be read once at the start of the compound-assign, before the RHS (with its `c++`) is evaluated. Fixed for scalars, indexed- and associative-array elements, across the whole `+= -= *= /= %= <<= >>= &= |= ^=` family (`evaluator.py` `_eval_assignment`/`_eval_array_assignment`), including `a[i]+=a[i++]`.
- **readonly-in-`$(( ))` now discards the rest of the current line (was: only the command failed).** `execute_arithmetic_expansion` catches `ReadonlyVariableError`, prints the error, and raises an errexit-eligible `TopLevelAbort(1)` (contained at eval/command-sub/process-sub/subshell/pipeline boundaries). **Deliberate deviation from the plan, verifier-VINDICATED:** the plan suggested routing via `fatal_expansion_status`, but that path forces `errexit_immune=True`, whereas readonly-in-`$(( ))` is errexit-SENSITIVE in bash — it must EXIT under `set -e` (while `$((1/0))` stays immune). The plain `TopLevelAbort(1)` matches bash exactly in both `set -e` states, single/multi-line `-c`, script, `source`, and `eval`.
- **Self-referential expression variable no longer leaks a Python `RecursionError`.** `x="x+1"; ((x))` produced an internal "unexpected error" and aborted; bash gives a bounded "expression recursion level exceeded" (rc1) and continues. A re-entrancy depth counter (`ShellState._arith_recursion_depth`, wrapper + `_evaluate_arithmetic_inner`) trips at bash's boundary. Exact-parity fix: trips at `depth >= EXPR_NEST_MAX` — psh now works at a 1022-deep self-reference chain and trips at 1023, byte-identical to bash (the counter increments one level ahead of bash's internal `expr_depth`, cancelled by `>=`). Boundary tests pin 1022-ok / 1023-trips so the off-by-one can't silently return.
- **Bad subscript on an UNSET array is now validated (fatal), not silently empty.** `${a[1//]}` (and `${a[1//]:-def}`, `${a[x y]}`, etc.) arith-evaluate the subscript and error like bash, on unset/set/scalar-holding names. Carve-out (matches bash): `${#name[sub]}` on an unset name stays 0 without validating (the one operator bash doesn't validate), but validates on a set name.
- **Multi-line `eval` discards only the offending line.** `Shell.run_command` gained a `line_oriented` flag and `StringInput` a `split_lines` flag; `eval` now processes physical-line-by-line like `source`, so a word-arith error on one line (e.g. the readonly case above) discards only that line rather than the whole `eval` string — matching bash. Verified non-invasive: only `eval` passes `line_oriented=True`; every other caller is unchanged; multi-line eval with `if/for/while`, heredocs, here-strings, quoted newlines, and line-continuations all still work; `$LINENO` inside eval is unchanged.
- Locked by `test_arith_compound_assign_order.py`, `test_arith_recursion_variable_eval.py` (+ exact boundary tests), `test_eval_line_discard.py`, subscript-validation + readonly-word-discard test classes, and 22 golden cases (`r18t2_arith_*`, `--compare-bash`). One pre-existing test that pinned old broken behavior was re-verified against bash and renamed (`[[ $((r=9)) ]]` with r readonly DOES discard the word in bash). Out-of-scope pre-existing items (eval `$LINENO`, trap single-chunk, `readonly -a a=(...); a[0]=9` over-discard) confirmed identical on main and deferred.

## 0.641.0 (2026-07-05) - Fix: glue/traps/CLI/scripting cluster — 6 bash divergences (reappraisal #18 Tier-2 T2-E)
- TIER-2 bug-fix cluster (6 items), each pinned to bash 5.2.26. Adversarial verifier PASS-WITH-NITS (nits are obscure invocation-option edges only, filed as follow-ups); full local gate green; ruff + mypy clean; guards mutation-proven.
- **Pending signal trap dropped at EOF when no EXIT trap (M-cc2):** a script whose last statement is `kill -TERM $$` (with a TERM trap installed) dropped the pending trap at EOF unless an EXIT trap happened to force a boundary. `SourceProcessor.execute_as_main` now runs `run_pending_traps()` before the EXIT trap, inside the try so a trap that does `exit N` is honored (N wins; the EXIT trap still fires). Verified for script file, `-c`, and stdin, with TERM/HUP/USR1/INT.
- **PS4 never expanded (M-s1):** `PS4` was emitted verbatim at the ~5 xtrace sites; bash expands it. New `ExpansionManager.expand_ps4()` helper, routed through all 5 sites. xtrace is suppressed *during* PS4 expansion so a `PS4='$(cmd)'` does not infinitely recurse (running the command-sub would otherwise re-trigger xtrace → re-expand PS4); the cmd-sub side effect still fires exactly once, matching bash. `print_xtrace` takes `shell`; `set_options` is an ordered `(name, enable)` list.
- **Analysis modes skipped line-continuation preprocessing (M-v1):** `--validate`/`--debug-ast`/`--debug-tokens` reported false syntax errors on valid scripts using backslash-newline continuations (notably after `then` and inside `[[ ]]`). `visitor_modes._parse_for_analysis` now runs `process_line_continuations` first (quote-aware); a genuinely-invalid script still errors rc2 on both parsers, matching `bash -n`.
- **Invocation option-parser gaps (M-s3):** added `-o/+o NAME`, `+`-clusters (disable), `-c` inside a cluster (`-xc 'cmd'`), `-eo pipefail`, and attached `-oNAME`. `set_options` became an ordered `List[(name, enable)]` so `-x +x` resolves last-wins like bash. Bad `-o` name → rc2; no crash on malformed input.
- **`cd ""` (M-b3):** psh errored (rc1); bash treats an empty operand as a no-op (rc0, stays in cwd). Fix runs the CDPATH search FIRST and no-ops only if nothing is found — so `CDPATH=/usr cd ""` still cd's to `/usr` (a naive short-circuit would have regressed that). Pinned by a dedicated regression-guard test.
- **`source`/`.` of a directory or unreadable file returned 126 (LOW):** bash returns 1. `SourceBuiltin` now remaps directory/unreadable → rc1, keeps binary → 126; the shared `validate_script_file` (used by the `psh <file>` invocation path, which correctly wants 126/127) is unchanged.
- Locked by 4 new test files + edits, PS4/LINENO conformance (`test_set_options_conformance.py`, mapped to the existing `set -x` CLAIM_TESTS entry), and 4 golden cases (`r18t2_glue_*`, `--compare-bash`). Out-of-scope pre-existing items (trailing-slash PWD on CDPATH resolution, `psh:` vs `bash:` error prefix, tiny-NUL-file source detection) confirmed identical on main and deferred.

## 0.640.0 (2026-07-05) - Fix: ${x~}/${x~~} case-toggle operators + length-safe Unicode case mapping (reappraisal #18 Tier-2 T2-D)
- TIER-2 cluster, pinned to bash 5.2.26. Implements the `~`/`~~` case-toggle parameter-expansion operators (fully) and makes the `^`/`^^`/`,`/`,,`/`declare -u`/`-l` case-modification length-safe. Adversarial verifier PASS-WITH-NITS (deviation vindicated by a 1,738-codepoint sweep; see below). No regressions; tests mutation-tested; meta-tests pass.
- **`${x~}` / `${x~~}` / `${x~pat}` / `${x~~pat}` case-TOGGLE (M-ex1):** previously a fatal "bad substitution". `${x~}` toggles the first character (pattern-gated), `${x~~}` toggles all matching characters; both accept an optional bash-glob single-char pattern. Works on scalars, indexed/associative arrays (`${a[@]~~}`, `${a[*]~~}`, `${m[k]~~}`), positional params (`${@~~}`, `${1~~}`), indirection (`${!ref~~}`), and variable-valued patterns (`${x~~$p}`). The `^ ^^ , ,,` siblings are unchanged. Adding `~`/`~~` to the operator tables introduced no parser conflicts (`${x:-~}`, `${x/~/_}`, `${#x}` all still match bash). Files: `expansion/param_parser.py`, `expansion/operators.py`, `expansion/parameter_expansion.py`.
- **length-safe Unicode case mapping (M-ex2):** `x=straße; echo ${x^^}` gave `STRASSE` (ß→SS, length grew) vs bash `STRAßE`. bash's case-mod is 1 codepoint → 1 codepoint. New `simple_upper`/`simple_lower`/`toggle_case` in `lexer/unicode_support.py` map a codepoint only when its full mapping is exactly one codepoint (plus the sole `İ`→`i` special case — U+0130 is provably the only codepoint whose full-lowercase expands to >1 char that bash single-maps). `^^`/`,,`/`declare -u`/`-l`/array-element case attrs all route through these. `ß`, ligatures (ﬀ), and other multi-char-expansion codepoints are left unchanged, matching bash.
- **Deliberate deviation from the campaign's prescribed routing, verifier-VINDICATED:** the plan called for an empirical macOS exclusion set; the implementation instead uses a platform-independent Unicode-simple mapping. A 1,738-cased-codepoint sweep confirmed this is correct — macOS's frozen libc has an actual case-mapping bug (`Ώ`→`Ϗ`, U+03CF garbage) that an exclusion set would have replicated and that would diverge from Linux/glibc bash (the nightly). The simple mapping matches bash on ASCII/Latin-1/accented/Greek/Cyrillic on both platforms.
- **Known limitation (documented, deferred):** 27 polytonic-Greek iota-subscript codepoints (U+1F80–U+1FF3) that bash titlecases on all platforms are left unchanged by psh (Python exposes only full, multi-codepoint mappings; a proper fix needs Unicode *simple* case tables). Non-regressive — strictly better than the prior multi-codepoint growth. The `unicode_support.py` comment documents these accurately.
- Locked by `tests/unit/expansion/test_case_toggle.py`, `tests/unit/lexer/test_case_mapping.py` (incl. an exhaustive length-safety guard over all 0x110000 codepoints), `tests/conformance/bash/test_case_toggle_conformance.py`, and 9 golden cases (`r18t2_expansion_*`, `--compare-bash`). User-guide ch05/ch17 updated (row kept descriptive, not "Full support", given the exotic-codepoint locale divergence — no CLAIM_TESTS entry required). ruff + mypy clean.

## 0.639.0 (2026-07-05) - Fix: lexer/parser narrow bash-conformance cluster (reappraisal #18 Tier-2 T2-C)
- TIER-2 bug-fix cluster (4 brief items + 1 surfaced bug), each pinned to bash 5.2.26 on BOTH the recursive-descent and combinator parsers. Verifier PASS-WITH-NITS (all nits pre-existing on main / out of this narrow scope); full suite 11,060 passed / 0 failed; all 5 fixes mutation-tested (each revert reintroduces failures).
- **case pattern starting with a POSIX char-class mis-lexed (M-cc1):** `case $c in [[:alpha:]]) …` on its own line lexed the leading `[[` as the `[[` conditional operator. Mirrored the `[` recognizer's `in_case_pattern` guard onto the `[[` branch in `lexer/recognizers/operator.py`. Fixes `[[:alpha:]]`/`[[:digit:]]`/`[[:upper:][:lower:]]`/nested classes as any case arm; a genuine `[[ … ]]` conditional at command position is unaffected.
- **`[!…]` negated bracket split by the operator-debris recognizer (surfaced during probing):** `[!x]` was tokenized as `[` `!x` `]` (a combinator-only symptom; RD re-joined). Fixed at the root in `lexer/recognizers/operator_debris.py` — a `!` immediately after a bracket `[` is kept as the negation marker, so `[!abc]`/`[!a-z]` lex as one WORD on both parsers, matching `[abc]`.
- **empty/degenerate `[[ ]]` accepted (M-p1):** `[[ ]]`, `[[ ! ]]`, `[[ x || ]]`, `[[ x && ]]` were silently accepted (rc0/1); now fall through to the existing "Expected test operand" error (rc2, matching bash). Removed the empty-operand fallback in `parser/recursive_descent/parsers/tests.py`. Valid forms (`[[ "" ]]`, `[[ -n x ]]`, `[[ ! -f /x ]]`, `[[ a && b ]]`) are unaffected.
- **`function NAME <compound>` rejected for non-brace bodies (M-p2):** `function f for …; do …; done` / `function f ( echo x )` / `function f if …` — bash accepts any compound as a function body; psh only accepted a brace group. Root cause was lexer command-position state not being reset after the `function NAME` prefix: `lexer/keyword_normalizer.py` now sets command position on the token after `function NAME`, so the body's leading keyword is recognized; the RD function parser also treats a `(` with content as a subshell body. All of for/if/while/until/case/`(( ))`/subshell/brace/empty-`()` bodies now parse on both parsers.
- **C-for header with a nested `((` fused the body (T1-5 leftover):** `for ((i=0; i<((5)-1); i++)); do echo x; done` merged the trailing `do echo` into one WORD because the lexer counted arithmetic depth per `((`/`))` token; a bare nested `((5)` (closed by two single `)`) never returned depth to zero. `lexer/modular_lexer.py` now counts individual parens (matching `TokenStream.collect_arithmetic_expression`); removed the now-dead `enter/exit_arithmetic` from `state_context.py`. `$(( ))` is a single token and never hits this counter.
- Locked by 56 new unit cases (both parsers) in `tests/unit/parser/test_r18t2_lexparse_fixes.py` + 15 golden cases (`r18t2_lexparse_*`, all pass `--compare-bash`). No user-guide doc flip (C-style-for and `[[ ]]` are already "Full support" rows — these are conformance improvements). ruff + mypy clean.

## 0.638.0 (2026-07-05) - Refactor: unify glob->regex conversion onto one converter, drop fnmatch from glob.py (reappraisal #18 Elegance)
- ELEGANCE (zero behavior change; byte-identical psh-before==psh-after across 1,389 e2e cases + ~27k converter-differential pairs, 0 divergences). Final Elegance release. Reappraisal #18 elegance item "one glob→regex converter (`glob.py` still uses stdlib fnmatch + a parallel bracket table)" — resolves a "second divergent path".
- `glob.py` used stdlib `fnmatch.translate` (fed by the psh-maintained bracket table) while `pattern.py` / `[[ ]]` / parameter-expansion used the hand-written `glob_to_regex` converter. Deleted `import fnmatch` + both `fnmatch.translate` call sites from `glob.py`; the two psh-written per-component matchers (`_glob_nocase`, `_match_glob_component`) now route through a new `_compile_component` → the single `glob_to_regex_body` converter (kept as the more-complete base: POSIX classes, extglob, `\]`-escapes, nocase class protection). Every line of psh-written glob→regex conversion now flows through ONE converter; `normalize_bracket_expressions` is localized to its one remaining consumer (the stdlib `glob.glob` default-case directory walker).
- Deliberately NOT changed (would be behavior changes): the stdlib `glob.glob` default walker (reimplementing its `./`/`../`/trailing-slash/hidden/symlink walking can't be proven byte-identical on the macOS-only gate); the 3 peripheral `fnmatch` callers (`print -m`, `help <pat>`, HISTIGNORE — non-pathname matching). Pre-existing divergences PRESERVED (flagged Tier-2, not fixed): backslash literal(pathname)-vs-escape(case/`[[`), walker-vs-default directory walking, set-op bracket FutureWarning (suppressed to stay byte-identical).
- Pinned by `test_unified_glob_converter.py` (123 tests). Verifier ran an independent 168-command battery three ways (before/after swap, worktree-vs-main) + a 21-command normalize-removal supplement + 27,398 converter pairs — 0 divergences; mutations (drop IGNORECASE / backslash-doubling / `.fullmatch`) all caught. Gate green (11,952 in the worktree). The 10 whole-tree-single-process trap failures are pre-existing pollution — 0 under `run_tests.py --parallel`.

## 0.637.0 (2026-07-05) - Refactor: split _execute_buffered_command into orchestrator + phase helpers (reappraisal #18 Elegance)
- ELEGANCE (zero behavior change; byte-identical across a 382-case matrix). Reappraisal #18 elegance item "split `_execute_buffered_command` (258 lines, 8 except clauses)".
- The monolith that implements psh's error model is split into an orchestrator + four cohesive helpers, WITHOUT changing the exception taxonomy: `_execute_buffered_command` keeps the OUTER try skeleton (`except ParseError` → `except UnclosedQuoteError` → `except Exception`→classify — the clause order that IS the error model); `_preprocess_command` (line-continuations + history), `_parse_command` (the 3-branch tokenize+parse), `_dispatch_execution` (the INNER try verbatim: TopLevel/StatementList dispatch + LoopBreak/LoopContinue + TopLevelAbort + FunctionReturn), and `_classify_buffered_error` (the `except Exception` taxonomy body, same isinstance order). Each phase is a helper called from within the outer try, so every exception lands in exactly the same clause.
- The only code-level change is three bare `raise`→`raise e` (same caught object; classification is type-based with no `__cause__`/traceback dependency). No handler moved inner↔outer.
- Verified byte-identical (rc + stdout + stderr + does-the-next-line-run) across an independent 382-case matrix — 64 scenarios × {`-c`, script, piped stdin, source-nested} × strict {0,1} — plus heredoc and `--parser combinator` probes. Mutation-tested: swapping/dropping a handler diverges 60–120 lines (the matrix has teeth). scripting/strict-errors/fatal-expansion/eval-control-flow/source-return/trap suites (397) green.

## 0.636.0 (2026-07-05) - Refactor: trap-body defects via report_internal_defect + reject duplicate builtin registration (reappraisal #18 Elegance)
- ELEGANCE (two small cleanups; one narrow intended behavior change). Reappraisal #18 elegance items. NOTE: the third item ("delete the vestigial DebugASTVisitor") was investigated and NOT done — `DebugASTVisitor` is the LIVE `--debug-ast` fallback formatter (`ast_debug.py:74-80`, exercised when the primary renderer raises) with a direct test; the verifier confirmed it by triggering the fallback. Deleting it would be a behavior change, not elegance.
- **trap-body internal defects now route through `report_internal_defect`** (the shared strict-errors chokepoint), replacing an ad-hoc `except Exception: print("trap: error executing trap...")` in `trap_manager.execute_trap`. The `except (FunctionReturn, LoopBreak, LoopContinue): raise` above it is untouched. This is a NARROW, intended consistency fix: a genuine internal Python defect raised in a trap body under `PSH_STRICT_ERRORS=1` now RE-RAISES (propagates), matching how a non-trap internal defect behaves, instead of being swallowed behind a `trap:`-prefixed message. Every normal/expected-error trap (`false`, command-not-found, redirect OSError, `$((1/0))`, `set -u`, syntax error, and control-flow `return`/`break`/`continue`) is byte-identical vs bash + the prior release in both strict modes — those are absorbed by `run_command`'s guards and never reach this handler. (The internal-defect message prefix for that bug scenario changes from `trap: error executing trap …` to the consistent `psh: …` — cosmetic.)
- **`builtins/registry.register()` rejects duplicate registration** — raises `ValueError` on a duplicate primary name OR alias (was a silent overwrite), catching a future double-registration at import time. No real builtin double-registers: `import psh` is unaffected and the 63-entry name+alias map (incl. `readarray`→`mapfile`) is byte-identical.
- Verified: 13-scenario trap battery byte-identical in both strict modes; mutation-checked both new tests bite. `test_registry.py` + strict-errors + trap-actions suites green.

## 0.635.0 (2026-07-05) - Refactor: combinator heredoc_processor → visitor subclass + productions → genuine composition (reappraisal #18 Elegance)
- ELEGANCE (zero AST change; byte-identical AST dumps across a 70-case corpus + `parser_differential` RD≡combinator parity green). Teaching-quality cleanup of the parser-combinator parser (reappraisal #18 elegance items: "rewrite heredoc_processor as a thin visitor subclass" + "convert 2–3 showcase productions to genuine combinator composition").
- **`heredoc_processor.py` 383→121 lines:** `HeredocProcessor` is now a thin `ASTVisitor[None]` subclass. `generic_visit` populates a node's own heredoc redirects (the chokepoint), then `visit_children` recurses via the shared dataclass-field walk (the same traversal the metrics/security/linter visitors use); the only per-type override is `visit_IfConditional` (elif clauses are tuple-nested and skipped by the generic child iterator). Public API unchanged. Population is keyed + idempotent, so the generic walk reaching a superset of nodes is a no-op on non-heredoc-bearing ones.
- **Three "imperative loop that is really `many()`" productions** converted to genuine composition: `_parse_trailing_redirects` and `_collect_definition_redirects` → `many(redirection)`; the for/select `in`-list item collection → a shared `many(_loop_item)`, deduplicating two identical ~15-line loops and dropping a provably-dead lookahead. (Redirection never returns a committed failure, so `many()` is exactly equivalent.)
- Left imperative (correct — committed-error / context-sensitive): the case-pattern `|` list, pipeline/and-or loops, `build_statement_list` (diagnostic preservation), and the simple-command word loop.
- 4 files, +129/-389. Combinator-mode execution smoke (heredoc+arith, for-list, elif+heredoc, trailing-redirect-on-loop) correct. Flagged for a future cleanup: `do_separator`/`then_separator` parsers are wired but never consumed (dead) — left untouched (out of scope).

## 0.634.0 (2026-07-05) - Refactor: centralize assignment-word/shell-name ASCII regexes in core/assignment_utils.py (reappraisal #18 Elegance)
- ELEGANCE (zero behavior change; byte-identical 55-case battery). Reappraisal #18 elegance item "centralize the 8 copies of the shell-name/assignment-word regex". Distinct from Tier-3's identifier-NAME *policy* centralization (the Unicode-aware `is_valid_name`) — these are the ASCII `[A-Za-z_][A-Za-z0-9_]*` SHAPE regexes copy-pasted across lexer/parser-time sites.
- One definition of the char class — `SHELL_NAME` in `core/assignment_utils.py` — plus `NAME_RE` / `ASSIGNMENT_WORD_RE` / `ASSIGNMENT_PREFIX_RE` composed from it. Merged the genuinely-identical copies (the two byte-identical assignment-word regexes in the RD function parser + `brace_expansion_tokens` now share `ASSIGNMENT_WORD_RE`; brace's simple-name check → `NAME_RE`; `manager`'s prefix regex → `ASSIGNMENT_PREFIX_RE`, kept distinct as it has no subscript). `word_builder` and the C-for-init validator source the `SHELL_NAME` fragment.
- Deliberately NOT merged, proven non-equivalent and pinned by tests: printf's `_IDENTIFIER_RE` (`printf_formatter` is contractually free of shell-package imports) and `words.py`'s `_BARE_VAR_NAME` (anchors with `\Z` (absolute end), not `$` — matches differently on a trailing newline). Both kept local with a test pinning them against `SHELL_NAME` so they can't drift.
- Pinned by `test_assignment_regexes.py` (17 tests) guarding every routed site. (A separate `$VAR`-reference-extraction regex family in the analysis visitors is a different cluster, left for later.)

## 0.633.0 (2026-07-05) - Refactor: extract formatter escaping/quoting statics to formatter_quoting.py (reappraisal #18 Elegance)
- ELEGANCE (pure code-motion; zero behavior change, byte-identical verified). Reappraisal #18 elegance item "extract formatter escaping statics to `formatter_quoting.py`".
- The AST formatter's inline escaping helpers now live in a cohesive `psh/visitor/formatter_quoting.py`: `escape_double_quoted`, `escape_ansi_c` (`$'...'` re-encoding), `WORD_LIST_FORCE_QUOTE` + `format_word_list_item` (for/select `in` items), and `quote_scalar` (here-strings). `formatter_visitor` delegates to them from `_format_word`, `_format_loop_items`, and the here-string redirect branch. The `_format_word` orchestrator and `${x}`-vs-`$x` brace-disambiguation stay in the visitor (they're reconstruction/delimiting, not escaping).
- Verified byte-identical across three shasum-matched before/after batteries: the FormatterVisitor over ~140 snippets covering every quoting branch, `type`/`declare -f`/`trap -p` on 13 tricky-bodied functions + traps, and `--debug-ast` on a nested script. Pinned by a new `test_formatter_quoting.py` (25 cases); full `tests/unit/visitor/` + declare-f/type/trap consumers green.

## 0.632.0 (2026-07-05) - Docs: record why history/shopt deliberately avoid parse_flags (reappraisal #18 Elegance)
- ELEGANCE (comment-only; zero behavior change, byte-identical verified). Reappraisal #18 elegance item "finish parse_flags convergence (history/directory_stack/shell_options)" — INVESTIGATED AND DECLINED WITH RATIONALE.
- All three targets have option grammars the shared getopt-style `parse_flags` helper cannot express without changing observable behavior: `shopt` allows flags after operands, mutually-exclusive flags (exit 1), rejects clustering (`-sq` is "invalid option", not `-s -q`), and uses "invalid option: -x" (exit 2); `history` is a `[n] | -c` dispatch where a numeric operand isn't a flag and `--`/`-d`/`-w`/`-5` yield "numeric argument required" (exit 1), not parse_flags' "-X: invalid option" + usage (exit 2); `directory_stack` (`dirs`/`pushd`/`popd`) uses `+N`/`-N` numeric index/rotation args that collide with dash-flag syntax and interleave with flags (`dirs` already carried a maintainer note to this effect).
- Added concise `# NOTE: deliberately NOT parse_flags() — …` comments to `history` (`shell_state.py`) and `shopt` (`shell_options.py`), matching the existing `dirs` precedent, so a future elegance pass doesn't re-attempt the dead-end. Verified byte-identical via a 65-case flag battery (every flag/bad-flag/`--`/`+N`/`-N`/interleave edge across all five commands). This elegance item is now closed as declined-with-rationale.

## 0.631.0 (2026-07-05) - Chore: widen ruff (flake8-bugbear) + mypy disallow_untyped_defs on psh.lexer (reappraisal #18 Tier-3)
- CHORE (lint/type only; zero runtime behavior change — verifier confirmed byte-identical tokenization and error messages/exit codes across default and strict-errors modes). Reappraisal #18 Tier-3, the incremental "widen ruff/mypy" item, scoped tight to one rule-family and one package. Final Tier-3 release.
- **ruff: enabled `B` (flake8-bugbear).** Fixed 45 violations: B007 unused-loop-var (→`_`), B904 raise-without-from (chained `from e` where a cause is bound, `from None` otherwise — traceback metadata only, no type/message/control-flow change), B905 zip-without-strict (`strict=False` in production == bare `zip`; `strict=True` in one test whose lengths are asserted equal), B011 assert-False (→`raise AssertionError`), B017 blind-except (narrowed to `ParseError`). Narrowly ignored two rules, each justified in-config: **B010** (six sites are deliberate DYNAMIC attribute assignments — proven that a direct `obj.attr = v` fails mypy `attr-defined` while `setattr` does not) and **B024** (three intentional marker/shared-init ABCs where `@abstractmethod` would be semantically wrong).
- **mypy: enabled `disallow_untyped_defs` for `psh.lexer.*`.** Annotated 32 defs; deepening the lexer surfaced and fixed **3 latent type bugs** (two recognizers' `config` attribute was inferred as `None` → annotated `Optional[LexerConfig]`; `word_scanners`' cached-prefix-map indexed an Optional → narrowed via a local) — behavior-identical, and the payoff of the deepening. `test_mypy_scope` stays green (the files glob is not narrowed).
- Verified behavior-preserving via 28 byte-identical error-path comparisons (worktree vs main vs bash, default + strict-errors), a 16-case tokenization battery (byte-identical tokens), and a 5,900-test broad slice. Both ignored rules independently confirmed sound (not masking). Re-run against the fully-merged Tier-3 tree: ruff `B` clean and mypy lexer-override clean with no new violations from the intervening releases.

## 0.630.0 (2026-07-05) - Assurance: harden run_tests.py (timeout, no INTERNALERROR masking, tighter rc-3, stream-to-file) (reappraisal #18 Tier-3)
- ASSURANCE (test-runner only; no psh runtime change). Reappraisal #18 Tier-3, from the independent review's masking-mechanisms + dormant-hang-trap findings.
- **Subprocess timeout + process-group kill:** each phase runs via `Popen(preexec_fn=os.setpgrp)` + `wait(timeout)`; on timeout `os.killpg(SIGKILL)` reaps the whole group (xdist workers, spawned psh, leaked sleeps) and the phase FAILs with exit 124. Default 1800s/phase; `--timeout` override. Was completely untimed — a wedged child hung the run forever.
- **Root-fixed the disown-orphan hang:** child output now goes to a temp FILE, not an inherited PIPE. The hang was `communicate()` never seeing EOF while an orphan held the pipe write-end (specifically in the `-s` phases); a file fd never blocks the reader. Timeout is defense-in-depth on top.
- **Never masks crashes:** removed the old `INTERNALERROR>`-stripping filter — any `INTERNALERROR>` in the output forces FAILURE even if pytest exited 0.
- **Tightened exit-code translation** (`classify_phase_result`): rc 0 → PASS unless INTERNALERROR present; the rc-3 xdist teardown-race escape hatch translates to PASS ONLY when provably all-green — a clean passed summary (now counting a lone `1 error`/`1 failed` via `(\d+) errors?\b`), zero failed/errors, and NO line-anchored worker-loss marker (`node down`/`replacing crashed worker`/`worker gwN crashed`); a worker crash whose surviving summary shows only passes now FAILs. Every other nonzero, incl. rc 5 (no tests collected), → FAIL.
- **Streams the full transcript** to `tmp/last-test-run.txt` (`--results-file` override), flushed per write — failures inspectable without a re-run. Preserved the parallel/serial split, subshell/`--compare-bash` phases, and all CLI flags (`--` for pytest pass-through).
- Pinned by `test_run_tests_hardening.py` (26 tests), including two serial subprocess tests that exercise the real timeout/killpg/file-capture path (mutation-proven to catch a "remove the killpg" regression). Verifier confirmed it gates on every failure kind (plain fail, INTERNALERROR, hang, rc5) AND never false-fails a green run (benign teardown race + scary test names stay green).

## 0.629.0 (2026-07-05) - Fix: centralize identifier-name policy + gate on posix_mode (reappraisal #18 Tier-3)
- FIX (behavior change, posix-gated). Reappraisal #18 Tier-3, from the independent review: ~13 identifier-name-validation sites had drifted or were missing, and psh accepted non-ASCII identifiers (e.g. `é=1`) even under `set -o posix`, where bash restricts identifiers to ASCII `[A-Za-z_][A-Za-z0-9_]*`.
- **One authoritative rule** — `lexer/unicode_support.validate_identifier(name, posix_mode)`, exposed as `is_valid_name`. Assignment, `declare`/`export`/`readonly`/`local`, nameref targets, `read`, `for` loop-var, function definitions, `mapfile`/`readarray`, and `${!indirect}` all route to it and read `set -o posix` at RUNTIME. Parse-time sites (`{fd}` recognizer, `${...}` classification) use the lenient rule and are backstopped by the gated runtime sites.
- **posix ON restricts to ASCII, matching bash exactly** (exit code + message); **posix OFF keeps psh's lenient Unicode-name behavior — a deliberate, now-documented divergence** (new user-guide §17.3, tightened to note the default-mode report-and-continue parity; the parse-abort/exit-2 difference is posix-only). Default-mode behavior is otherwise unchanged (verifier confirmed zero ASCII regression).
- **Latent bugs fixed** (names invalid in BOTH bash modes that main wrongly accepted): `read`/`for`/`local` now reject `9x`/`a-b` in both modes, matching bash. `mapfile`'s ASCII-only regex was the one inconsistent outlier — it now follows the single rule (lenient in default like its siblings, ASCII under posix); the maintainer-noted default-mode Unicode acceptance is subsumed by the existing documented divergence.
- Pinned by `test_identifier_policy.py` (12 unit) + `test_identifier_policy_conformance.py` (21 conformance) + 9 golden pins (`--compare-bash`), each mutation-checked. Full conformance suite green (1,525). No unmapped "Full support" claim (documented as prose).

## 0.628.0 (2026-07-04) - Hygiene: Shell.close() + lazy signal-notifier allocation + close the env child (reappraisal #18 Tier-3)
- ASSURANCE/HYGIENE. Reappraisal #18 Tier-3, from the independent review's Shell-fd-lifecycle finding. No user-visible behavior change.
- Each `Shell` eagerly allocated two `SignalNotifier` self-pipes (4 fds) in `__init__`, even for the many transient/non-interactive shells (tests, the `env` builtin's child, subshell helpers); GC reclaimed them (a sawtooth) but nothing closed them explicitly, and the `env` child Shell was never closed at all.
- **Lazy allocation** (`signal_manager.py`): the notifiers start `None` and are created on first use, only in `_setup_interactive_mode_handlers` — which allocates them BEFORE installing the SIGCHLD/SIGWINCH handlers, so there is no window where a signal handler references a missing notifier (verifier-proven; the handlers also carry None-guards and never allocate in signal context). A fresh non-interactive shell now opens ZERO notifier fds.
- **`Shell.close()` + context-manager** (`shell.py`): idempotent, releases the self-pipes, and NEVER touches stdin/stdout/stderr (verified via fstat that fds 0/1/2 stay valid); the shell remains usable afterward (notifiers re-allocate on demand). `__enter__`/`__exit__` added.
- **`env` child closed** (`env_command.py`) in its existing `finally`; **`tests/conftest.py`** `_cleanup_shell` teardown routes through `shell.close()` (the old code poked the now-`None` notifier directly).
- fd count for 200 held transient shells: **4/shell → 0** (measured both trees). Pinned by a new `test_shell_fd_lifecycle.py` stress test (mutation-confirmed: reverting to eager allocation makes it fail with "800 fds / 4.000 per Shell"). Full gate green (11,765); interactive/job-control/signal delivery unchanged across a 3× pty run.

## 0.627.0 (2026-07-04) - Assurance: replace the conformance runner with pytest discovery + a gating JSON hook (reappraisal #18 Tier-3)
- ASSURANCE (test-tooling only; no psh runtime change). Reappraisal #18 Tier-3, the independent review's core contribution.
- The old `tests/conformance/run_conformance_tests.py` was untrustworthy: it ran a hardcoded subset (~364 of ~1,471 collected tests), its `main()` NEVER gated on defects (always exited 0, so a conformance failure couldn't fail the nightly), and it emitted stale frozen metrics. **Full replacement.**
- The new runner DISCOVERS every conformance test via an in-process `pytest.main` over the whole `tests/conformance/` tree (no hardcoded list), records per-test outcomes with a small `ConformanceReportPlugin`, and GATES: it exits non-zero on pytest's own failure exit AND independently on any failed/error outcome or an empty collection (belt-and-suspenders — the latter catches the class pytest's exit code covers, i.e. uncollectable files). `pytest.ini`'s `xfail_strict=true` means a stale absent-feature XPASS now fails the gate too. Emits a machine-readable JSON report (`success` bool as the CI gate, real counts, per-test outcomes, failures with tracebacks).
- Verified by injecting every failure kind (assertion, exception, real `assert_identical_behavior` divergence, setup/teardown error, strict-XPASS) — each drives exit non-zero — and by the false-green attacks (syntax/import-error uncollectable files → gate FAILS; empty selection → FAILS). Real counts match `pytest --collect-only` (1,515) exactly. The nightly's no-arg entry point (`nightly.yml`) is unchanged and now actually gates (previously always green). `run_tests.py` does not invoke this runner — no contract dependency.
- Preserved CLI: `--posix-only`/`--bash-only`/`--summary-only`/`--output-dir`; added `--json PATH` and pytest pass-through. `ConformanceTest` + the `assert_*` helpers and the "undocumented divergence == defect" policy are unchanged.

## 0.626.0 (2026-07-04) - Test: finally-based cleanup + exact-PID kills for disown/process-spawning tests (reappraisal #18 Tier-3)
- TEST-ONLY (zero production code change). Reappraisal #18 Tier-3 assurance, from the independent review's dormant "hang trap".
- The disown tests could orphan a long-lived `sleep` when an assertion failed: their cleanup was a trailing broad `pkill`/`kill %N` that was NOT in a `finally`, and `disown` REMOVES the job from `job_manager.jobs`, so the `_cleanup_shell` fixture teardown (which reaps only jobs still in the table) couldn't catch a disowned child. An orphaned child could later wedge an untimed `communicate()` in the runner after a prior failure.
- New `tests/unit/builtins/conftest.py` provides a `spawned_pids` fixture that SIGKILLs each tracked PID by EXACT id in a `finally` teardown (runs even when the test body fails) — never a broad pattern kill (which could hit unrelated processes, including sibling test workers). `test_disown_builtin.py` (17 spawning tests) and `test_job_control_builtins.py::test_disown_job` rewired to track the bg PID and drop the non-`finally` broad cleanup; happy-path assertions untouched.
- Verified: forcing an assertion failure after `disown` orphaned the exact PID before the fix and left no orphan after. Sibling process-spawning/PTY tests audited — already use `try/finally`/fixture teardown; only the two disown tests were the genuine gap.

## 0.625.0 (2026-07-04) - Docs: truth-up stale feature/difference docs + reconcile test counts (reappraisal #18 Tier-3)
- DOCS-ONLY (zero code change). Reappraisal #18 Tier-3 assurance, from the independent review.
- **`tests/conformance/differences/README.md` was spectacularly stale** — its "Not Implemented" section listed features psh has shipped for many versions. Every reclassification was proven with a probe: `[[ ]]`, `(( ))`, `declare -a`/`-A`, `${array[@]}`/`${#array[@]}`, `${var^^}`/`${var,,}`/`${var/pat/rep}`, process substitution `<()`/`>()`, extglob `?()/+()/@()/!()` (in globs, `case`, `[[ ]]`, and param patterns), `mapfile`/`readarray`, `local`, `shopt`, and history expansion. Restructured into "Features PSH Supports" / "Features PSH Does NOT Implement" / "Documented Behavioral Differences", and deleted a false "Known Limitations" section (heredoc var-expansion, `<<-` tab-strip, and fd manipulation are all implemented — probed). Genuinely-absent features kept honest (cross-checked against `test_absent_features.py`): `bind`, `compgen`, `complete`, `caller`, `enable`, `suspend`, `coproc`, `wait -f`, `jobs -x`, `shopt -s lastpipe`, and `set -H`/`+H`.
- **README carried three conflicting test counts** — reconciled to the real figures (12,686 collected tests / 485 `test_*.py` files, from `pytest --collect-only`): the `**Tests**:` header floor (`12,000+`), the Project Statistics block (`12,686 tests in 485 test files`), the LOC line, and a stale prose mention (`8,439 tests across 365 files`). The `test_readme_statistics.py` meta-test passes on the reconciled numbers.

## 0.624.0 (2026-07-04) - Fix: background-child trap discipline + POSIX async rules + wait remembered status (reappraisal #18 Tier-1)
- FIX. Reappraisal #18 Tier-1 executor cluster (T1-4, H2+H3 + POSIX-async MEDs). Final Tier-1 release. Pinned to bash 5.2 with marker-file-synchronized probes (no bare sleeps).
- **Traps set INSIDE backgrounded compound bodies now fire.** Previously a `trap` set inside a backgrounded subshell `( )&`, brace group `{ }&`, or function `f&` never installed an OS handler (TERM/INT/USR1/HUP/USR2 lost), and bg EXIT traps were dropped on both normal completion AND untrapped-fatal-signal death. One missing capability — added `child_policy.run_background_shell_child`, now used by all three bg-compound paths. It resets inherited parent traps to default (a parent trap must NOT fire in the child), re-arms the trap-checking OS handlers for a body-set trap, pumps the pending-trap queue, and runs the EXIT trap in a `finally` on both normal completion and fatal signal — **exactly once** (verifier-confirmed idempotency; true exit status 143/129 preserved, not the trap's).
- **POSIX async rules for non-job-control bg jobs** (`process_launcher.py`): stdin from `/dev/null` for role=SINGLE (a bg `read` no longer steals the script's stdin; pipeline members and explicit `<` redirects are untouched; correctly gated on job-control-OFF so interactive bg still gets the tty), and untrapped SIGINT/SIGQUIT ignored while TERM/HUP still kill.
- **`wait` remembered status** (`job_control.py`): a reaped known job's status is retained for a repeated EXPLICIT `wait <pid>`/`%jobspec` (bash parity, previously 127), while a bare `wait` (wait-for-all) both stops recording AND clears prior explicit retention — matched to bash across the full matrix (`bare,expl`→127; `expl,bare,expl`→5,0,127; signal-killed and multi-job edges included). Unknown pid still 127.
- Parent-set-trap-reset-in-child pinned as must-not-regress (the brace-group case was the regression this fixes). Pinned by `test_bg_child_trap_discipline.py` (33 tests, `@serial`, marker-file sync) + 7 golden pins (`--compare-bash`), each mutation-checked. Verifier confirmed fg/interactive blast radius unharmed and 28/28 core tests stable across 3 reruns.
- Pre-existing items confirmed not-worsened and queued for Tier-2: bg-compound trap latency for a single long external command; loop-of-short-commands untrapped TERM/HUP; `wait -n; wait $samepid` retention (LOW); fg-untrapped-INT-during-fg-child; `wait` error-message prefix.

## 0.623.0 (2026-07-04) - Fix: read -s canonical termios + read -t deadline (reappraisal #18 Tier-1)
- FIX. Reappraisal #18 Tier-1 (T1-7, H6 + a MED), pinned to bash 5.2 via pexpect pty + timed-pipe probes.
- **H6 — interactive `read -s`/`read -sp` hung on Enter and couldn't be interrupted.** `tty.setraw` cleared ICRNL (so Enter's CR never mapped to the `\n` delimiter), ISIG, and ICANON. For silent DELIMITER-terminated reads (no `-n`/`-N`), psh now stays in CANONICAL mode and clears only `ECHO|ECHONL` (bash's model): Enter terminates, line editing and Ctrl-D EOF work, and ISIG is preserved so Ctrl-C's SIGINT is delivered (terminating a `-c` read; the interactive REPL swallows Ctrl-C during a read like plain `read`, unchanged). Count reads (`-n`/`-N`) keep raw char-at-a-time mode. Terminal state is restored on every exit path (normal / Ctrl-C / Ctrl-D / timeout) — verified no leaked no-echo terminal.
- **MED — `read -t` abandoned its deadline after the first byte** on the non-tty path (measured ~5s vs bash ~0.3s, wrong rc). The remaining time budget is now threaded through the whole read loop, so the deadline holds across the entire read. On expiry the timeout falls through to normal assignment (partial input assigned and IFS-split, a preset variable cleared) with rc 142, matching bash — including the `-t 0` poll special case (returns immediately, non-consuming).
- Multibyte and `-N` count paths were explicitly out of scope and untouched (the pre-existing `read -N -t` timeout gap is queued for Tier-2).
- Pinned by a pexpect pty test (`TestPtyReadSilent`, 4 cases, `@serial`, isolated HISTFILE) + subprocess timeout tests (xdist-safe) + 3 golden pins (`--compare-bash`), each mutation-checked. Known accepted scope-cut: a silent read still emits a trailing newline (now `\r\n` via ONLCR, an improvement over the old raw-mode bare `\n` staircase) where bash emits none — queued for Tier-2 polish.

## 0.622.0 (2026-07-04) - Fix: CLOEXEC fd-inheritance + exec-close stream primitive (reappraisal #18 Tier-1)
- FIX. Reappraisal #18 Tier-1 io cluster (T1-6, H5 + a MED), pinned to bash 5.2.
- **H5 — redirect fds were CLOEXEC when `open()` landed on the target fd**, so children couldn't inherit them: `cat /dev/fd/3 3<data` gave EBADF where bash succeeds. `_dup2_preserve_target`'s `opened_fd == target_fd` shortcut skipped the `dup2` that clears `O_CLOEXEC`; it now calls `os.set_inheritable(target_fd, True)`, making the shortcut behaviorally identical. Fixes the fd 3/4 idioms, `exec` reopen-after-close, and child-inherited fds. The `{v}>` (F_DUPFD) named-fd path is immune and untouched.
- **MED — `exec >&-` after `exec >file` leaked into the old file** because closing the fd never reached the Python-level stream. Extracted ONE primitive — `IOManager.swap_output_stream_closed` (installs a `_ClosedStream` sentinel, returns the displaced stream) + an `output_close_fd` classifier — and call it from all THREE sites: the two that had ad-hoc copies and the previously-MISSING permanent-exec close branch in `apply_permanent_redirections`. `exec >f; exec >&-; echo two` now fails with a write error instead of leaking `two` into `f`.
- **Pre-existing bug fixed at true cause:** a `>&2`-to-closed-fd error routed through `report_internal_defect`, whose diagnostic write to the now-closed stderr itself escaped and aborted the command list. That write is now best-effort — the strict-errors re-raise for genuine internal defects runs FIRST (verifier confirmed defect reporting is byte-identical on working streams and still fails loudly), so only a write to a broken/closed fd is absorbed (rc 1, like bash). `exec 2>&-; echo x >&2; echo three` now prints `three`.
- Tests are subprocess-based with `PYTHONPATH` pinned to the repo root — the editable install otherwise imports the main tree (a campaign-wide gotcha; also fixed in the pre-existing `test_exec_permanent_redirect.py`). Pinned by `test_child_fd_inheritance.py` (7) + `TestExecCloseOutputFd` (6) + 3 golden pins (`--compare-bash`), each mutation-checked; 3-site routing confirmed with no 4th copy.
- Pre-existing residuals queued for Tier-2: builtin override-vs-fd-reopen (`f 1>&2` after close doesn't heal to stderr — but no longer leaks); `exec >f; exec 3>&-` emits a Python "Exception ignored while finalizing file" line (override-dup lands on fd 3).

## 0.621.0 (2026-07-04) - Fix: C-style-for parenthesized subexpressions — arith-collector consolidation (reappraisal #18 Tier-1)
- FIX. Reappraisal #18 Tier-1 (T1-5, H4). `for ((i=0; i<(n-1); i++))` failed to parse in the recursive-descent parser; the combinator only half-handled it and was never at true AST parity. Root: three arithmetic-section collectors with two different stop strategies.
- **Consolidated all collectors** — the three RD collectors AND both combinator scanners (C-for + arithmetic-command) — onto ONE depth-tracked discipline in `lexer/token_stream.collect_arithmetic_expression`: base depth 0, `(`/`((` open and `)`/`))` close; a section terminates only at a top-level `;`/`;;` (for-header) or a closing paren at depth 0, splitting a straddling `))` at depth 1. The signature changed from a `stop_condition` callback to a `stop_at_semicolon` bool; every caller was updated and the buggy `_double_rparen_stop` deleted. RD and combinator now share the collector and are locked together by the parity corpus.
- Fixes paren-in-init `for ((i=(1+1); …))`, parenthesized condition, and the `(i++))` update-straddle; preserves `while (( (i)<3 ))`, `$(( (1+2)*(3+4) ))`, `(( (1<3) ))`, and all empty-section forms.
- **Regression guard (verifier-caught):** the correct collector unmasked a latent orchestration bug — a one-semicolon header `for ((i=0; i<3))` parsed with an empty update section and infinite-looped. Made the second for-header semicolon MANDATORY in both orchestrations (`recursive_descent/parsers/control_structures.py` + `combinators/control_structures/loops.py`): such a header now rejects with rc 2 like bash. bash's C-for requires exactly two semicolons (any section may be empty).
- Pinned by `TestCStyleForParenthesizedSubexpr`, rejection/acceptance entries in the pure-parser parity corpus (`test_combinator_error_parity.py`), 7 combinator↔RD AST-parity params, and 9 golden pins (`--compare-bash`), each mutation-checked. Verifier re-ran a 36-case well-formed fuzz + 28 arity edge-cases on both pure parsers with 0 divergences.
- Corrected disposition: the `for ((i=0; i<((5)-1); i++))` case is a PRE-EXISTING lexer WORD-fusion bug (`do echo ` merged into one token) that already differed rd-vs-combinator on main — queued for Tier-2, not addressed here.

## 0.620.0 (2026-07-04) - Fix: test/[/[[ file-operator cluster (reappraisal #18 Tier-1)
- FIX. Reappraisal #18 Tier-1 `test`/`[`/`[[` file-operator cluster (T1-2 + a same-class fold-in), all pinned to bash 5.2. One shared `evaluate_unary` serves all three forms.
- **`-r`/`-w`/`-x` (and `-s`) no longer wrongly false for non-regular files, including directories.** An `os.path.isfile` guard made `[ -x /usr/bin ]`, `[ -w /tmp ]`, `[ -r /dev/null ]` and `[ -s DIR ]` all return false where bash returns true. Dropped the guard: `-r/-w/-x` use `os.access` alone (access(2) / real-uid semantics, matching bash); `-s` uses `stat().st_size > 0` for any file type. A full audit of the file-TYPE operators (`-f/-d/-e/-L/-h/-b/-c/-p/-S/-k/-u/-g/-O/-G/-N`) confirmed only the permission trio and `-s` carried the wrong guard — the type discriminators (`-f`=regular-only, `-d`=dir-only, etc.) were correct and are untouched.
- **`-nt`/`-ot` existence-asymmetry, deduplicated.** bash's rule (`f1 -nt f2` true iff f1-newer OR f1-exists-and-f2-missing; both-missing/equal → false) is now implemented ONCE in `utils/file_tests.py`; `test`/`[` delegates to it (its inline copy deleted) and `[[ ]]` already delegated — removing a verified duplicate-logic site. The rebuild idiom `[[ src -nt missing ]]` is now true.
- **POSIX 3-arg / 4-arg dispatch order.** The dispatch stripped leading `!`/`(` before checking whether `$2` was a binary primary. Rewritten to the POSIX algorithm: with 3 args a binary `$2` is evaluated first (`$1 op $3`); with 4 args a leading `!` negates the 3-arg result; rc 2 now propagates through negation. Truth table matches bash: `test ! = x`→1, `test "(" = ")"`→1, `test ! -eq x`→2, `test ! "(" = ")"`→0. Also fixed a print-error-yet-return-0 inconsistency.
- Pinned by a new conformance file (`test_test_file_operators_conformance.py`, 44 cases via `assert_identical_behavior`) + 21 unit tests + 17 golden pins (`--compare-bash`), each mutation-checked. Verifier fuzzed 10,152 `test`/`[` invocations against bash with 0 fix-caused divergences.
- Pre-existing out-of-scope items queued for Tier-2: deprecated unary `-a`=file-exists (psh rc 2); `!` vs `-a`/`-o` precedence in >4-arg expressions (needs a real precedence parser).

## 0.619.0 (2026-07-04) - Fix: array-scalar overwrite + assoc -aA leak + local case-transform (reappraisal #18 Tier-1)
- FIX. Reappraisal #18 Tier-1 core assignment/attribute cluster (T1-3), all pinned to bash 5.2 via a 37-case attribute matrix.
- **H1 array-wipe.** `a=x` on an existing array WIPED it into a corrupt ARRAY-scalar, and a temp-env prefix `a=x cmd` destroyed the array PERMANENTLY (bash's temp-env assignment is temporary and non-destructive). Fixed at one chokepoint — `core/scope.py` `set_variable`: when the existing value is an `IndexedArray`/`AssociativeArray` and the incoming value is a plain scalar, write element 0 / key "0" and PRESERVE the container. `a=(1 2 3); a=x` → `declare -a a=([0]="x" [1]="2" [2]="3")`; `a=(1 2 3); a=x true; echo "${a[@]}"` → `1 2 3`.
- **Temp-env sparse/assoc preservation (verifier-refuted the "single chokepoint suffices" claim).** The chokepoint alone fixes DENSE indexed temp-env, but the save side of `executor/command_assignments.py` `apply_prefix` snapshotted only element-0's string, so restore re-created a spurious `[0]=""` slot for SPARSE indexed and ASSOCIATIVE arrays. Fixed on the SAVE side (deep-copy the whole container up front; restore puts it back) — not `restore()`. Strict no-op for the common scalar/unset case; namerefs don't hit the path. `a=([1]=x [2]=y); a=z true` and `declare -A m=([k]=v); m=x true` now round-trip identically to bash.
- **Associative `-aA` leak.** Associative compound assignment passed `ARRAY|ASSOC_ARRAY`; now `ASSOC_ARRAY` only (`executor/array.py`). Invariant established: an associative array never carries the indexed-ARRAY bit. `declare -A m=([c]=3); declare -p m` → `declare -A` (was `declare -aA`) and re-imports cleanly into both shells.
- **`local -ul`/`-lu` case-transform + duplicate-code removal.** `local -ul x=Hello` wrongly uppercased. Root: a DUPLICATE `_apply_attributes` in `builtins/shell_state.py` (a "second divergent path"). Deleted it (and its pre-transform call); `local` now routes solely through the correct `ScopeManager._apply_attributes` chokepoint, with `-ul`/`-lu` cancelling to no net transform like bash. `declare`'s own case-transform path was always separate and is unaffected.
- Pinned by `tests/unit/core/test_array_scalar_overwrite.py` (14), `test_local_builtin.py` case-transform class (5), and 8 golden pins (`--compare-bash`), each mutation-checked. Verifier confirmed the deleted method had no orphaned callers.
- Adjacent pre-existing defects confirmed baseline and queued for Tier-2: `local` re-declaration doesn't merge existing attributes; array-element case-transform not applied on append; nameref temp-env export leak; integer-array element-0 `+=`.

## 0.618.0 (2026-07-04) - Fix: binary-stdin traceback + fd0-closed startup crash (reappraisal #18 Tier-1)
- FIX. Reappraisal #18 Tier-1 crash cluster (T1-1). Two crash-class defects where a raw Python traceback reached the user; both pinned to bash 5.2 (the requirement is graceful, no-traceback handling — output-byte divergence on undecodable input remains the documented byte-model choice).
- **Binary/undecodable stdin no longer tracebacks.** Both unguarded `sys.stdin.read()` sites in `__main__.py` (the non-interactive read and the visitor-mode read) now route through one `_read_all_stdin()` helper that reads raw bytes via `sys.stdin.buffer` and decodes with `errors='surrogateescape'` (matching the FileInput treatment in `input_sources.py`), with no newline translation (CR/CRLF byte-preserved, matching bash). All four channels — pipe, `-s`, `<`-redirect, visitor/analysis modes over stdin — stop tracebacking on garbage bytes; psh even matches bash's exit codes (127 command-not-found).
- **fd 0 already closed at startup no longer crashes.** psh launched with stdin closed (`sys.stdin is None`) raised `AttributeError: 'NoneType' … isatty`. Both `isatty()` interactive-detection sites — `shell.py` `_init_interactive` and `__main__.py` — now guard `None`/closed stdin (treat as non-interactive). Guarding only one merely moved the crash to the other; both were needed.
- **Companion isatty guard (verifier-caught).** With startup no longer crashing, the same unguarded-isatty idiom at `expansion/command_sub.py` became newly reachable in the command-substitution child under closed fd0 — `psh -c 'echo $(echo hi)'` returned empty + a graceful stderr error instead of bash's `hi`. Guarded with the same idiom; a full sweep of `.isatty()` sites confirmed this was the only other newly-reachable one. The whole "unguarded isatty under closed fd0" finding class is closed in one release.
- Pinned by `tests/system/test_stdin_startup_robustness.py` (12 subprocess tests, bash-compared, Linux-portable via `preexec_fn=os.close(0)`), each mutation-checked to go red on a reverted guard. (No `golden_cases.yaml` entries — its runner is `psh -c <command>` text-mode and cannot express binary stdin or a closed fd0; the subprocess suite is the durable pin.)
- Adjacent pre-existing output-encoding defect (a raw non-UTF-8 byte in a *command argument* → `UnicodeEncodeError` on write) confirmed present identically on the script-file path and NOT introduced here; queued as a Tier-2 output-layer item.

## 0.617.0 (2026-07-04) - Fix: trap actions — control flow unwinds, $BASH_COMMAND, RETURN trap (reappraisal #17 Tier-2)
- FIX. Reappraisal #17 Tier-2 scripting cluster (MED-1/2/3 + LOW-2), each pinned to bash 5.2 via truth tables. Final release of the Tier-2 serial integration train.
- **MED-1 control flow in trap actions no longer swallowed.** `TrapManager.execute_trap`'s blanket `except Exception` caught `FunctionReturn`/`LoopBreak`/`LoopContinue`, printing a spurious "trap: error executing trap" and running code the control flow should have skipped (`trap 'return 9' USR1` in a function ran `after` and returned 0; bash returns 9). Control-flow exceptions now re-raise and genuinely unwind from `run_pending_traps`: `return` exits the innermost function (or stops a sourced file), `break`/`continue`/`break N` act on the enclosing loop(s) with bash's exit-status semantics, and a `return` in a DEBUG action returns from the function being entered.
- **MED-3 `$BASH_COMMAND` wired** via one chokepoint (`TrapManager.set_bash_command`) at the executor dispatch sites — simple commands (formatter-rendered, quotes/redirects preserved), pipeline members (parent + child), for/case headers, each C-style-for step, and `(( ))`/`[[ ]]` commands (which now also fire DEBUG as bash does). Reads are a dynamic special variable; updates freeze while a trap action runs (DEBUG sees the upcoming command, ERR the failing one, signal/EXIT the interrupted one). **Lazy rendering (verifier repair):** the stamp is an AST-node attribute write; the text renders on first read and caches back — no per-command formatter cost (a no-trap 20k-iteration loop is within ±1% run noise; DEBUG-trap loops at parity; was +13% eager).
- **MED-2 RETURN trap implemented** (deferred since #14) with bash's observable HIDING model rather than a fire-time gate: accepted by the gates (`trap`/`trap -p`/`trap -l` ordering EXIT..DEBUG,ERR,RETURN), fired at every function return and end of `source` with FUNCNAME/locals still in place and `$?` = the pre-return status; hidden for a function's extent unless `set -T` functrace or the function's new `declare -ft` trace attribute; a trap the body sets fires at that function's return and persists. **Deliberate divergences:** `return N` in the action adopts N once (bash 5.2 recurses forever); at the end of `source` bash rejects the action's `return` while psh adopts N. `declare -ft` DEBUG inheritance (verifier repair) matches bash including the entry fire.
- **LOW-2** with `set -T`, DEBUG also fires on function ENTRY (bash fires twice for `f`: call site + entry).
- **Docs meta:** with RETURN now implemented, the v0.607 doc-staleness guard correctly forced the ch17 "DEBUG/ERR/RETURN traps" row from Partial to **Full support** — added a proving `TestReturnTrapConformance` class + `CLAIM_TESTS` mapping, removed the now-obsolete `PARTIAL_ROW_PROBES` entry, and swept the ch17 prose + appendix A pseudo-signal list.
- Pinned by `test_trap_actions.py` (56 subprocess cases) + 23 golden pins (`--compare-bash`) + the RETURN conformance class. Integration: merged cleanly atop the whole train (`command.py` 5-branch hotspot auto-merged; trap×arith interplay `trap 'x=$((1/0))' USR1` verified against bash).

## 0.616.0 (2026-07-04) - Fix: bash fatal expansion-error model + ternary-comma grammar (reappraisal #17 Tier-2)
- FIX. Reappraisal #17 Tier-2. Truth-tabled first against bash 5.2 (the author's normalized 440-cell battery — 11 error kinds × 10 contexts × 4 input modes, comparing exit code / which lines run / variable persistence, not psh's error-message wording): psh matched 232/440 pre-fix, 440/440 post-fix, plus 66 edge probes.
- **DISCARD-LINE family** (failed word arithmetic `$((1/0))`, arith syntax errors, bad-NAME substitution, failglob, substring/indirection errors): the rest of the current line dies, execution resumes at the next input line with `$?=1`, in every input mode. Contained at subshell/cmdsub **and** eval/source/trap-action boundaries (bash 5.2 contains the discard there; **v0.601's nested re-raise was bash-divergent and is removed**). Errexit-immune, except failglob which under `set -e` exits a non-interactive shell even from suppressed contexts.
- **ASSIGNMENT/SUBSCRIPT arith errors** (`declare/local -i` values, `-i` plain assignment, `${a[1//]}`, `a[1//]=x`, `unset 'a[08]'`): discard-line except under `-c`, where the rest of the `-c` string is abandoned (rc 1, passes through eval, contained at forks). **Verifier-corrected:** this family passes through eval/source containment in ALL modes (not just `-c`), re-raising at nested buffered boundaries (`TopLevelAbort.contain_nested=False`).
- **SHELL-EXIT family** (`${x:?}`, unknown `@X` transform on a SET variable, `set -u`): a non-interactive shell exits (the error's own status under `-c`: 127; 1 for file/piped stdin); interactive/embedded shells discard the line with status 1. Piped stdin now sets script mode like `-s` (bash treats `cmds | sh` as a script).
- **Mechanics:** `TopLevelAbort` gains `errexit_immune` and is caught at every buffered boundary; `GlobNoMatchError` deleted (failglob converts at the raise site); `local -i` no longer silently swallows arith errors to "0".
- **Grammar:** the ternary MIDDLE operand parses at comma level (`$((1?2,3:4))` = 3) in every consumer (`(( ))`, `let`, `$(( ))`); the FALSE operand stays at ternary level (`$((0?1:2,3))` = 3). **Verifier-corrected `++`/`--` lvalue boundary** (in the arith tokenizer, mirroring bash `expr.c`): a `++`/`--` pair is re-read as two unary signs ONLY when it is neither postfix (a variable/subscript precedes) nor prefix (an identifier follows, whitespace skipped) — so `$((3---x))` is `3 - --x` = -1 (decrements x), `$((5 ++ 3))` = 8, while `$((3++x))`, `$((x ++ 2))` are syntax errors.
- Bash quirks pinned: `${unset@Z}` silently empty (only a SET variable makes an unknown transform a fatal bad substitution); parse accepts any `@`-letter operand, application decides.
- Integration: merged cleanly with v0.615's assignment-before-redirect reorder (the `except ShellArithmeticError` handler grafted into the reordered `apply_pure` loop — value expansion precedes redirect; verified `x=5 > /bad/y` → `x=5 rc=1`) and v0.609's arith depth guard.
- Pinned by `test_fatal_expansion_model.py` (44 subprocess tests across families/modes) + 31 golden pins (`--compare-bash`) + ternary/incdec characterization rows.

## 0.615.0 (2026-07-04) - Fix: raw-repr diagnostic family + exec builtin + test too-many-args (reappraisal #17 Tier-2)
- FIX. Reappraisal #17 Tier-2 raw-Python-repr diagnostic cluster (io MED-1/LOW-3, builtins M2/M4, core trap-exec MED). Six bash-5.2-pinned fixes.
- **(a) FD_LEVEL_WINDOW repr leak.** The function/pipeline-builtin dispatch site applied redirects unguarded, leaking `psh: [Errno 21] Is a directory: 'd'` (e.g. `f > adir`, `echo x > /bad/y | cat`). **All** redirect sites in `executor/command.py` (FD_LEVEL_WINDOW, bare-array, no-command-word) now route through `guarded_redirections`, so the one-message-shape invariant holds on every dispatch site; the builtin in-process ladder folds into `format_redirect_error`.
- **(b) Empty-target `> ""`** used truthiness so `''` fell through to three malformed messages by path; now `is not None` → bash's `psh: : No such file or directory` everywhere.
- **Assignment-before-redirect ordering (probe-discovered).** Pure and bare-array assignments with a failing redirect now match bash's order — **assign first, then redirect** — so `x=5 > /bad/y` leaves `x=5` and fails rc 1, and `x=$(cat) < file` expands with the original stdin.
- **(c) ExecBuiltin diagnostics** use the shared `format_exec_failure`: `exec /no/such/x` → "No such file or directory" 127 (was "command not found"); `exec /etc` → bash's two-line "Is a directory" / "cannot execute" 126 (was raw `[Errno 13]`); bare name → `exec: NAME: not found`; `exec ""` → 127 (was a ValueError leak at rc 1).
- **(d) `trap ''` across DIRECT exec.** The v0.593 reconciliation lived only in the forked-child policy; `trap "" INT; exec cmd` lost the ignore for managed signals (the kernel resets Python handlers to DFL on exec). `SignalManager.exec_image_dispositions()` is now the single source of truth, shared by `reset_child_signals` and a new `prepare_signals_for_exec()` the exec builtin applies before `execvpe` (restoring on the exec-failed path); also stops leaking psh's own SIG_IGNs (TTOU/TTIN) and CPython's startup SIGXFSZ ignore.
- **(e) `read` after `exec 0<&-`** → bash's `read: read error: 0: Bad file descriptor` (was raw `[Errno 9]`); `read -u BADFD` gains the strerror tail.
- **(f) `test`/`[` too-many-arguments** now prints bash's `[: too many arguments` (rc 2 was already right). **Verifier repair:** removed the pre-existing 4-arg "split operator" hack that glued `test a ! = b` into `a != b` (and `= =`→`==`, `= ~`→`=~`) — bash 5.2 does no such reconstruction (every such form is "too many arguments", rc 2). The one real 4-arg form, POSIX leading-`!` negation (`test ! a = b`), is handled earlier and still works.
- Truth-tabled against bash 5.2; pinned by 14 golden pins (`--compare-bash`) + unit coverage.

## 0.614.0 (2026-07-04) - Fix: interactive policy + line-editor fidelity (reappraisal #17 Tier-2 interactive)
- FIX. Reappraisal #17 Tier-2 interactive cluster, PTY-truth-tabled against bash 5.2.
- **M2 `ignoreeof` was a silent no-op.** The REPL EOF branch now implements bash's `IGNOREEOF` counter: N consecutive Ctrl-Ds print `Use "exit" to leave the shell.` and the N+1st exits; empty/non-numeric = 10; `IGNOREEOF=0` exits on first EOF; the counter resets on a non-blank command. Coupling matches bash: `set -o ignoreeof` binds `IGNOREEOF=10` / `set +o` unbinds it, and the option flag tracks the variable via the ShellState observer (so `IGNOREEOF=n`/`unset` flip `set -o` too). With `ignoreeof` active, EOF at a PS2 prompt abandons the unfinished command and stays.
- **M3 no stopped-jobs exit guard.** One chokepoint, `JobManager.confirm_exit_with_stopped_jobs()`, is consulted by BOTH the exit builtin and the REPL EOF path: the first interactive attempt with stopped jobs warns `There are stopped jobs.` and stays (`$?=1` for exit; EOF leaves `$?` untouched); a second consecutive attempt proceeds; running background jobs never warn; non-interactive shells and forked children skip it.
  - **bash-exact `jobs` exemption (verifier-corrected):** an exit whose immediately preceding command was the `jobs` builtin exits with **no** warning even without a first strike (bash's `exit.def`); any other command word — builtin, function, or external — clears the exemption; blank lines and pure assignments don't; `jobs | cat` (subshell) never sets it. Implemented as bash's `last/this_shell_builtin` shift register on `JobManager` (`note_simple_command`), shifted before every top-level simple-command dispatch. **An `exit` in a sourced file bypasses the guard entirely** (`source_depth > 0`), matching interactive bash.
- **M4 kill-ring coalescing.** Consecutive emacs-mode kills merge into one ring entry: forward kills (`C-k`, `M-d`) append, backward kills (`C-w`, `C-u`, `M-DEL`) prepend — `echo alpha beta` `C-w C-w C-y` restores `alpha beta`. Movement/typing/yank break the chain; vi mode never coalesces (readline parity).
- **M5 meta word boundaries.** `M-f`/`M-b`/`M-d`/`M-DEL` now use readline's ALNUM word rules (UTF-8 accents kept in-word): `M-DEL` on `aa.bb` kills just `bb`, `M-f` lands at word end. `C-w` stays whitespace-based (unix-word-rubout); vi `w`/`b` unchanged. 17/17 rows match bash.
- **L1** double `^C` at the prompt no longer double-echoes (`$?` stays 130). **L2** PS1 `\j` (job count), `\l` (tty basename, `tty` fallback), `\D{format}` (strftime; empty = `%X`; unclosed brace formats the rest; bare `\D` literal) now render — pinned via `${PS1@P}`.
- Pinned by 3 unit files, a `TestPtyExitPolicy` PTY class + `TestPtyExitPolicy` jobs-exemption PTY pins (serial), prompt-escape unit tests, and 8 golden `@P`/policy entries verified against live bash.

## 0.613.0 (2026-07-04) - Fix: bare-} command position, recursive time/! prefixes, function-name validation, unified parse diagnostics (reappraisal #17 Tier-2 RD parser)
- FIX. Reappraisal #17 Tier-2 RD parser. 111-probe bash-5.2 truth table (108 exact matches; residuals are the `bash -c '++()'` startup confound and error-shape-only differences where both shells reject).
- **MED-1 bare `}` at command position** now rejected as a syntax error (rc 2, nothing runs) exactly like bash; `echo }` / `echo a } b` argument positions and real brace groups untouched.
- **LOW-1 `time`/`!` prefix ordering** now follows bash's recursive `pipeline_command` grammar: prefixes repeat and interleave (`! time cmd`, `time time cmd`, `time -p ! cmd`), each `!` toggling negation. A bare prefix is a complete empty pipeline only before bash's list_terminator (`;`, newline, EOF) — `!` alone → 1, `time !` → 1 — while `time &&`, `( ! )`, `{ time }`, `time ;;` now reject like bash (the old broad end-token set silently accepted them). `time` after `|` demotes to the external command. Empty pipelines execute with status 0 and honor negation/timing uniformly.
- **LOW-4 function-name validation (bidirectional):** an assignment word followed by `()` is a syntax error near `(` (`a=b()`, `a+=b()`, `a[0]=b()` — psh used to store a phantom function), while non-assignment names the lexer splits at operator candidates are rejoined and accepted (`foo+bar()`, `2=b()`, `[foo]()`, `function foo+bar`).
- **MED-2 diagnostics cluster:** one shared `TOKEN_DISPLAY_NAMES` map feeds every error path (no more `TokenType.THEN` enum leaks; `expect()` renders "Expected 'then', got end of input"); suggestions key on the structured expected token type; `create_parser` no longer drops `source_text` (root of the two-render-format split) so both source-processor print sites share one canonical `psh: <src>:<line>: <caret>` renderer; a threaded `line_offset` makes the prefix line and the embedded `(line N, column M)` ABSOLUTE for multi-line input.
- **Combinator diagnostic parity (educational parser):** error messages route through the shared `describe_token` (no raw enum-name leaks); a shared `unexpected_token_message()` renders EOF as bash's "syntax error: unexpected end of file" and NEWLINE as `newline`; the canonical renderer back-fills the caret's source line for the combinator. Two structurally-divergent parity cases (`function-body-if-missing-fi`, `function-body-while-missing-done` — the v0.607 bare-`}` fix moved RD toward bash's reject-at-`}` while the combinator keeps its EOF shape) moved to `KNOWN_DIVERGENT_DIAGNOSTICS` with a companion test pinning that both parsers still reject.
- Pinned by 21 golden pins (`--compare-bash`) + 96 regression tests; `parser_differential` full dir green.

## 0.612.0 (2026-07-04) - Fix: positional-$* per-element operators + tilde-prefix boundary (reappraisal #17 Tier-2 F1/F2/F3)
- FIX. Reappraisal #17 Tier-2. Truth-tabled against bash 5.2 (operator families × views × IFS; tilde prefix-kinds × followers × contexts).
- **F1 (leaned HIGH — silent corruption): value operators on the positional `*`/`@` scalar views applied to the IFS-joined string instead of per element.** Case modification (`^ ^^ , ,,`) and substitution (`/ // /# /%`) now route through the same per-element treatment as removal/slices, via a single `_expand_positional_view` helper keyed off `_VALUE_OPERATORS` — so no operator family can be forgotten for one view again. `set -- foo bar; "${*^}"` → `Foo Bar` (was `Foo bar`); `IFS=o; set -- fo of; "${*//o/_}"` → `f_o_f` (was `f___f`); `"${*/#ab/X}"` → `Xc Xd`. The `@` scalar view had the same bug in string contexts (here-docs).
- **F2 (under-expansion): a leading tilde-prefix is now terminated by `:` as well as `/`** (bash `tilde_additional_suffixes`) — `~:x`, `~root:x`, `~+:x` all expand. The boundary rule lives in one place (`TildeExpander.prefix_end`), shared by `expand()`, the word-leading decision, the assignment-value splitter, and the operand walkers.
- **F3 (over-expansion): a tilde word running into a quoted part or an expansion stays literal** — `~"x"` → `~x`, `~$USER` → `~user`, `~+"x"` → `~+x`, and escapes (`~\:x`, `~\/x`) stay literal. `_leading_tilde_expandable` requires the whole tilde word to be unquoted literal, matching bash 5.2.
- **Documented divergences (not parity):** for the WORD `~:$X`, bash pastes `$X` verbatim after expanding whereas psh keeps the tilde literal and expands `$X` normally; operand contexts otherwise reproduce bash's `tilde_find_word` verbatim-remainder semantics (`${u:-~:$X}` → `$HOME:$X` with `$X` literal/unsplit). Adjacent v0.606 disclosure: `${a[*]:-'p q'}` now returns a single field as-is (quote protection survives) rather than str.join-flattening it.
- Pinned by 27 golden pins (`--compare-bash`) + 73 unit tests.

## 0.611.0 (2026-07-04) - Fix: script-fd placement, heredoc delimiter/EOF edges, whitespace set (reappraisal #17 Tier-2)
- FIX. Reappraisal #17 Tier-2 — four input-layer clusters (io MED-2, lexer MED-1/MED-2 + round-2 addendum), each truth-tabled against bash 5.2 first.
- **(a) Script fd off user space.** `FileInput` now reads the whole script eagerly in `__enter__` and closes the descriptor before any command runs, **retiring the `_relocate_high` F_DUPFD hack** that parked it on fd 10 — exactly bash's `{var}` named-fd base. `exec {fd}>/dev/null` now answers 10 (was 11) in script mode, and a script using fd 10 itself no longer dies with a spurious EBADF at close.
- **(b) Heredoc delimiter word rules.** `HEREDOC_MARKER_RE` becomes a negated charclass — bash accepts almost any non-blank run (`E*F`, `A?B`, `AB[cd]`, `E.F`, `@X`, `{abc}`, `!`, `<< -EOF`); word ends at blanks/`|&;()<>`. The old `[A-Za-z0-9_$]` class **truncated the stored delimiter so the terminator never matched and the heredoc — plus everything after it — silently vanished at rc 0.** Also: `<<$(cmd)` delimiters taken literally; the delimiter word is never brace-expanded (`cat <<E{a,b}F`); empty delimiter no longer registered.
- **Behavior change:** `#` immediately after a redirect operator now starts a comment like bash — `cat <<#foo` and `echo x >#f` are rc-2 syntax errors (previously accepted).
- **(c) Unterminated heredoc = delimited by EOF** (was: silent drop, rc 0). The pending heredoc completes with the gathered lines and psh prints bash's exact `warning: here-document at line N delimited by end-of-file (wanted 'EOF')` with bash's line-number/multi-heredoc-promotion semantics; script-file stderr matches bash byte-for-byte. `<<-` with a space-indented terminator now recovers like bash instead of vanishing.
- **(d) Word separators are space/tab(+newline) only** (`SHELL_WHITESPACE` frozenset; `WORD_TERMINATORS` aligned). CR/FF/VT and Unicode Z\* (NBSP, EN SPACE, IDEOGRAPHIC SPACE) are word characters like bash — `echo a<NBSP>b` is one word (copy-paste hazard fixed). Line-ending CR handling stays at the line-reading layer; the v0.600 CRLF-heredoc pins stay green and the frozen lexer corpus needed no changes.
- Pinned by 13 golden pins (`--compare-bash`), 8 lexer/scripting unit tests, 5 script-fd subprocess tests, `test_unterminated_heredoc.py` (12, stderr byte-equal), `test_word_separator_bytes.py` (10 raw-byte cases).

## 0.610.0 (2026-07-04) - Fix: r17t2 grab bag — combinator parity, globstar symlinks, pipeline signal death, declare -n validation
- FIX. Reappraisal #17 Tier-2 grab bag — four small file-disjoint fixes, each pinned against bash 5.2 by a truth table.
- **(a) Combinator parser parity (F1/F2).** `f() [[ ... ]]` non-brace function bodies now parse (the guard tuple gains `DOUBLE_LBRACKET`); `! ! cmd` repeated negation parses with parity toggling (negated = count % 2), mirroring the RD parser's loop. 15/15 three-way probes (bash / rd / combinator) agree, incl. if-conditions, pipelines, brace groups, `time ! ! true`. Compound `[[ a && b ]]` bodies keep the documented educational-scope honest-reject.
- **(b) Globstar `**` no longer descends through symlinked dirs (P-MED-1).** `expansion/glob.py` routes any pattern with a bare `**` component (under `shopt -s globstar`) to a new symlink-aware walker (`_expand_globstar`/`_walk_no_follow`) instead of `glob.glob(recursive=True)`, which followed symlinks and blew up on loops (`ln -s . loop`). bash 4.3+ semantics: symlinks listed as leaves, never entered; explicit/wildcard-matched symlink components ARE followed; `**/` keeps symlinks-to-dirs; bash-verbatim zero-match text; dotglob honored. 24 base + 21 corner probes byte-identical. Bonus: `extglob`+globstar patterns (`**/@(x|z).txt`) now recurse via the same walker.
- **(c) Foreground-pipeline signal death announced (MED-2).** `_wait_for_foreground_pipeline` reports the member whose status becomes the pipeline's exit status (last member normally, rightmost failing member under `pipefail`). `true | sh -c 'kill -TERM $$'` now prints `Terminated: 15` like bash (rc 143 unchanged). SIGINT/SIGPIPE and substitutions stay silent; non-TERM signals keep psh's bare-message form (documented job-table difference).
- **(d) `declare -n` target validation (core MED).** `builtins/function_support.py` validates the nameref target's shape at declare time with both bash messages: empty → `` `': not a valid identifier ``; invalid shape → `` `VALUE': invalid variable name for name reference `` (rc 1, nameref not created). Valid = identifier + optional balanced-to-end `[subscript]`. 17/17 normalized probes match. (`local -n` has a separate duplicated path, ledgered.)
- Pinned by 9 combinator three-way tests + `TestPipelineNegationRuns`, `test_globstar_symlinks.py` (22), `test_pipeline_signal_death.py` (11, serial), `TestNamerefTargetValidation` (30 params), and 15 golden pins (green under `--compare-bash`).

## 0.609.0 (2026-07-04) - Fix: raise recursion ceiling + clean depth guards (reappraisal #17 Tier-2)
- FIX. Reappraisal #17 Tier-2 (executor MED-1 / scripting MED-4 / rdparser MED-3 / crosscut M3). Four coordinated fixes for the recursion cliff: function recursion died at ~50 shell calls (bash: 5000+) because the recursive visitor burns ~18 CPython frames per call against the default 1000-frame limit, surfacing as a misleading "arithmetic error: expression too deeply nested" or a raw traceback; deep compounds (~90 levels) crashed the RD parser.
- **Startup recursion limit raised** (`RECURSION_LIMIT=40,000`, raise-only/idempotent in `psh/shell.py`) → ~2,200 shell-call and ~3,300 nested-compound depth. This relies on CPython ≥ 3.12's heap-allocated frames + C-stack guard (psh already requires Python ≥ 3.12; **not** a new requirement) — verified no segfault driving runaway recursion up to a 60,000 limit even under `ulimit -s 512`; runaway errors out in ~0.4s.
- **FUNCNEST diagnostic at the function-call boundary** (`executor/function.py`): `RecursionError` there becomes bash's `NAME: maximum function nesting level exceeded`, aborts the current top-level command via `TopLevelAbort`, shell survives (message/rc/next-line resume all match `FUNCNEST=N`; bare bash segfaults). `command.py` / guarded builtins / the nested-source guard re-raise `RecursionError` so it reaches that boundary (covers recursion through `eval`).
- **`RecursionError` joins `_EXPECTED_SHELL_ERRORS`** (`core/internal_errors.py`) so function-less runaway paths (deep `eval` chains, compound nesting at exec time) report cleanly under `PSH_STRICT_ERRORS=1` instead of tracebacking.
- **Explicit parser depth guards** replace the blanket catch: `ParserContext.nesting_depth` (`MAX_NESTING_DEPTH=1000`, checked at the single compound-dispatch chokepoint) → clean `ParseError "commands nested too deeply"` (bash parity to 1000; 1001 errors cleanly rc 2); arithmetic gets `ArithParser.MAX_DEPTH=1024` in `parse_ternary`/`parse_unary`, replacing the `RecursionError`→"expression too deeply nested" catch that mislabeled shell-stack exhaustion as an arithmetic problem.
- Pinned by `test_recursion_depth.py`, `test_nesting_depth_guard.py`, `test_arith_depth_guard.py`, a taxonomy case in `test_strict_internal_errors.py`, and 4 golden pins (3 bash-compared).

## 0.608.0 (2026-07-04) - Fix: echo -e / printf %b escape dialects — one left-to-right scanner (reappraisal #17 Tier-2 M3)
- FIX. Reappraisal #17 Tier-2 M3. Pinned byte-exact to bash 5.2 by a 216-row truth table (every escape × {`echo -e`, plain echo, `printf %b`, printf FORMAT}).
- **`\c` short-circuit fixed.** The old helper cut the string at the first `\c` *before* processing, so escapes ahead of it stayed raw (`echo -e 'a\tb\cd'` printed a literal `\t`; bash prints `a<TAB>b` and stops). It also mis-terminated on `\\c`, whose backslash bash pairs with the preceding `\\`.
- **Octal dialects de-conflated.** One echo-shaped regex served both `echo -e` and `printf %b`, wrong in both directions — `%b` lost the POSIX bare `\ddd` form (`\1`, `\41`, `\777`, `\0` all left literal; bash emits bytes mod-256), while `echo -e` wrongly accepted `\ddd` (`\101`→`A`; bash keeps it literal, the leading `0` is required) and dropped `\0`/`\0777`.
- **Rewrote `psh/utils/escapes.py`** from a multi-pass `str.replace` helper (with a `\x01BACKSLASH\x01` placeholder hazard that collapsed `echo -e '\x01BACKSLASH\x01'` to a single backslash) into **one left-to-right scanner**, dialect-parameterized on the octal grammar only: `process_echo_escapes` = `\0` + up to 3 octal digits (mod 256); `process_percent_b_escapes` = additionally bare `\ddd` (1–3 digits, mod 256). Both now decode short `\uH{1,4}`/`\UH{1,8}` like bash; `printf %b` no longer routes through the echo dialect.
- **FORMAT-string dialect** (separate by design): `\?` drops its backslash, `\u`/`\U` accept short forms, and an unknown escape now emits only the backslash so `\%` feeds `%` back to conversion parsing (bash prints `\`, then "missing format character", exit 1).
- **Byte-model divergence (documented, not bash parity):** surrogate / beyond-U+10FFFF `\u`/`\U` values now emit *nothing* instead of crashing the output encoder — bash writes raw bytes there, which are unrepresentable in a Python `str`; this remains the documented UTF-8 byte-model limitation (`\0777`→0xFF stays UTF-8-encoded). Guarded so the surrogate case no longer raises.
- Doc-drift swept: `appendix_d_ascii_chart.md` `echo -e "\101"` corrected to `\0101` (bare `\101` is now literal, matching bash). Repo hygiene: removed a stray scratch `file` that slipped into the tree.

## 0.607.0 (2026-07-04) - Docs: truth-up FUNCNAME/aliases/coproc + extend doc-staleness guard to Partial rows (reappraisal #17 Tier-2 M1/M4/L5/L6)
- DOCS + TESTS ONLY. Reappraisal #17 Tier-2 docs/meta cluster. Zero `psh/` source changes; every claim re-probed against live bash before editing.
- **M1a FUNCNAME row corrected to Full support.** The ch17 compatibility row claimed "[0] only; full call stack not populated" — false: `a->b->c` yields `c b a`, identical to bash under `-c`. Flipped to Full support with the honest caveat that bash's `main`/`source` base frames (the BASH_SOURCE/BASH_LINENO cluster) are absent — in a script *file* bash prints `c b a main` where psh prints `c b a`. Added proving conformance tests (`TestFuncnameNotes`, including a divergence pin for the main-frame caveat) plus the `CLAIM_TESTS` mapping the meta-test contract requires; 17.2 prose and the 17.7 checklist updated to match.
- **M1b (root cause): the doc-staleness meta-test now guards Partial rows.** `test_claims_have_tests.py` guarded Yes rows (`CLAIM_TESTS`) and No rows (`NO_ROW_PROBES`) but not Partial rows — exactly how FUNCNAME rotted. New `PARTIAL_ROW_PROBES`: every "Yes | Partial" row must map to a probe demonstrating the claimed-missing sub-behavior still diverges from bash (`test_every_partial_row_has_a_probe` + parametrized `test_partial_row_gap_still_diverges`), with a shared `_runs_identically` predicate and a self-test proving the guard isn't vacuous. All four remaining Partial rows verified still-divergent (RETURN trap, `shopt lastpipe`, `read -e`, `TIMEFORMAT`).
- **M4 expand_aliases documented.** psh deliberately keeps aliases ON non-interactively (bash defaults OFF) — new 17.3 "Alias Expansion in Scripts" section, compatibility-table row, migration notes, and ch04 coverage, pinned by a documented-difference catalog entry (`ALIAS_EXPANSION_NONINTERACTIVE`) and identical-behavior pins for the `shopt -u/-s expand_aliases` toggle.
- **L5 coproc roadmap** added to `docs/missing_features.md` (bash semantics probed live: `NAME[0]/NAME[1]/NAME_PID`, subshell fd invisibility, still-exists warning, NAME-vs-simple-command rule; implementation plan against ProcessLauncher/JobManager; edge cases; test plan).
- **L6 stale xfail reasons** in `tests/integration/interactive/test_history.py` rewritten to the honest non-interactive-stdin form (history expansion and `history -c` are implemented; no test logic or statuses changed).
- shopt row note refreshed to the actual supported set (adds `checkhash`, `expand_aliases`, `failglob`, `nocasematch`).

## 0.606.0 (2026-07-04) - Fix: parameter-expansion value-word quoting + backtick escapes in double quotes (reappraisal #17 H5+H6)
- FIX. Reappraisal #17 Tier-1 H5+H6.
- **(H5) Value-word quote/escape removal in `${x:-w}` families.** The value
  operand of `${x:-w}` / `${x:=w}` / `${x:+w}` / `${x:?w}` — and the no-colon
  `${x-w}` / `${x+w}` forms — previously had quotes removed **only when a single
  quote pair wrapped the whole operand**. Anything else leaked: embedded quotes
  (`${x:-a"b"c}`) passed through into the output, single-quoted segments were
  still `$`-expanded instead of taken literally, backslash escapes went
  unprocessed, and — worst — `${x:="a"b}` **STORED the corrupted text** into the
  variable (silent data corruption on every subsequent read).
- **Root cause / fix.** Value operands now go through a quote-aware walk that
  was **converged with the pattern-operand walker that was already correct**
  (shared logic rather than a second divergent path), with the enclosing
  double-quote context threaded through. Inside `"..."` the bash rule inverts:
  single quotes are literal, double quotes are stripped. Heredoc bodies,
  `$(( ))`, and `[[ ]]` string parts all follow double-quote semantics — so
  `$(( ${u:-'5'} ))` now errors like bash (single quotes literal → non-numeric)
  while `$(( ${u:-"5"} ))` works. Field/glob protection is honored per bash:
  `${x:-'a b'}` is one field, `${x:-'*'}` never globs, but `${x:-*}` still globs.
  The `:=` store now writes the clean, quote-removed value.
- **(H6) Backtick `\"` unescape inside double quotes.** A backtick command
  substitution inside double quotes now strips `\"` per POSIX
  (`echo "`echo \"q\"`"` prints `q`). The lexer had been ignoring its
  `quote_context` for backticks. Bare backticks (`echo `echo \"q\"``) and the
  `$(...)` form are unchanged — they keep the escaped quote.
- **Tests.** New `tests/unit/expansion/test_value_operand_quoting.py` and
  `tests/unit/lexer/test_backtick_dquote_escapes.py`; 29 `value_operand_*` /
  `backtick_*` / `cmdsub_*` golden cases pinned in
  `tests/behavioral/golden_cases.yaml` (re-run against real bash under
  `--compare-bash`). Pattern operands verified untouched (53/53 pattern cases
  still pass); the `:=` store semantics and the `"${x:-a"$y"c}"` name-scan quirk
  were confirmed to reproduce bash exactly.
- **Honest residual disclosures (per-field protection granularity — tracked as
  reappraisal-#17 ledger items, not fixed here):**
  1. The mixed protected/unprotected glob corner `${x:-'*'x*}` changed failure
     shape: main leaked quotes; this now pathname-expands where bash keeps it
     literal (affects both scalars and array views).
  2. `${a[*]:-'p q'}` splits into two fields where bash keeps one — the `[*]`
     view joins to a plain string that drops the per-segment protection
     (pre-existing array-view model gap).
  3. `[[ ]]` / `case` PATTERN contexts ignore operand protection (pre-existing).

## 0.605.0 (2026-07-04) - Fix: no brace expansion inside [[ ]] — regex intervals work (reappraisal #17 H4)
- FIX. Reappraisal #17 Tier-1 H4. **Brace expansion ran inside `[[ ]]`**, so the
  ubiquitous regex-interval idiom `[[ $x =~ ^[0-9]{1,3}$ ]]` — and any
  brace-expandable construct there (`{1,3}`, `{1..3}`, `a{b,c}`) — hard-failed
  with a parse error, because expanding `{1,3}` split the word and broke the
  `]]` parse. **bash performs NO brace expansion inside the `[[ ]]` conditional
  expression:** regex intervals and brace-shaped patterns stay literal.
- **Root cause / fix.** The token-stream brace expander
  (`psh/expansion/brace_expansion_tokens.py`) already tracked a command-prefix
  (assignment-allowed) zone; it now additionally tracks a
  `DOUBLE_LBRACKET..DOUBLE_RBRACKET` region and passes those tokens through
  untouched. `]]` reopens the command prefix (like `)`/`}` end their compounds).
  Because the fix is at the shared token level, **both parsers** (recursive
  descent and combinator) benefit.
- **Lexer safety invariants (verified in source).** The lexer only emits
  `DOUBLE_LBRACKET` at command position and `DOUBLE_RBRACKET` only at bracket
  depth > 0, so the region flag cannot be forged from argument-position text:
  `echo [[ a{1,2} ]]` still brace-expands normally. `[[ ]]` does not nest (an
  inner `[[` lexes as a WORD), so a single flag suffices.
- **Unchanged behavior.** Case patterns and assignment words — which already
  matched bash — are untouched.
- **Tests.** `tests/unit/expansion/test_brace_expansion.py` gains coverage for
  the suppressed-region behavior and its boundaries; 10 `dbracket_*` golden
  cases pinned in `tests/behavioral/golden_cases.yaml` (re-run against real bash
  via `--compare-bash`). ~75 fresh probes on both parsers all match bash.
- **Pre-existing residuals for the ledger (NOT this fix):** `[[ x == x]]`
  (missing whitespace before `]]`) is accepted; `case [[ in` mis-lexes; case
  patterns are still brace-expanded (`case a1a2 in a{1,2})` matches in psh, not
  bash); `[[ x =~ a{1..3} ]]` returns rc1 vs bash rc2 on the invalid-interval
  regcomp error.

## 0.604.0 (2026-07-04) - Fix: HISTCONTROL=ignorespace works on the real command path (reappraisal #17 H7)
- FIX (privacy-relevant). Reappraisal #17 Tier-1 H7. **`HISTCONTROL=ignorespace`
  was silently a no-op on the path real commands take.** Typing a space-led
  command (` echo secret`) still recorded it in history, defeating the whole
  point of the option. The source processor pre-stripped the command string
  before handing it to the history manager, so the manager's leading-space
  check never saw the space. The existing unit tests drove the leaf
  `add_to_history` method directly with an already-spaced argument, so they
  passed as a **false positive** while the real entry path leaked.
- **Root cause / fix.** `scripting/source_processor.py` called
  `self.shell.add_history(command_string.strip())`; it now passes the command
  **RAW**. bash 5.2 (truth-tabled via `--noediting` HISTFILE round-trips) stores
  the line verbatim and every filter decides on that unmodified text:
  - lines are stored **verbatim** — leading and trailing whitespace preserved;
  - `ignorespace` fires only on a literal leading **space** (a leading **tab** is
    kept and stored verbatim);
  - `ignoredups` compares verbatim (` echo a` differs from `echo a`);
  - `HISTIGNORE` matches the verbatim line (`HISTIGNORE=ls` keeps ` ls`);
  - a space-led multi-line compound drops the **whole** logical command.
- **Deliberate divergence kept:** whitespace-only lines are still not recorded
  (bash records them).
- **Tests.** `tests/unit/interactive/test_histcontrol_histignore.py` rewritten to
  drive `shell.run_command` (the full source-processor path) instead of the leaf
  method, with verbatim-storage, tab/`ignoredups`/`HISTIGNORE`-verbatim,
  multi-line, and HISTFILE round-trip pins; two PTY smoke tests pin the live
  interactive path (ignorespace drop + verbatim leading-space storage). The
  false-positive kill was mutation-tested: re-introducing the old `.strip()`
  fails 11 of the 22 rewritten tests.

## 0.603.0 (2026-07-04) - Fix: analysis modes on stdin analyze instead of executing; one visitor-mode chokepoint (reappraisal #17 H2)
- FIX (security-relevant). Reappraisal #17 Tier-1 H2. **Piping a script into any
  analysis mode EXECUTED the input instead of analyzing it.** `cat script | psh
  --security` ran the very (untrusted) commands it was asked to inspect — same
  for `--format`, `--validate`, `--lint`, and `--metrics`. The stdin branch of
  `__main__.main()` never checked `visitor_mode`, so piped/typed input fell
  straight through to the normal execution path.
- **One chokepoint for every input channel.** `-c` command strings, script
  files, and piped stdin now all route through the single new function
  `scripting/visitor_modes.handle_visitor_mode_for_content(shell, content,
  location)`, which parses (heredoc-aware) and analyzes identical content
  identically — same output, same exit codes — and never executes it.
  `handle_visitor_mode_for_command` and `handle_visitor_mode_for_script` are now
  thin wrappers over it; `location` only labels diagnostics (`-c`, the script
  path, or `<stdin>`).
- **Deleted the divergent second `--validate` implementation.** A separate
  line-by-line validator baked into the execution loop
  (`scripting/source_processor.py`) printed the syntax error AND a contradictory
  "No issues found - AST is valid!" summary, exiting 0. It is removed; `--validate`
  now reports consistent exit codes on every channel: **0** when clean, **2** on a
  syntax error.
- **Deliberate behavior changes:** (1) `psh --validate` at a TTY now reads stdin
  to EOF and analyzes it (the shape of `bash -n`) instead of running the old
  validate-REPL; (2) empty piped stdin under an analysis mode analyzes the empty
  program rather than doing nothing.
- Verification: independently rebuilt 60-cell truth table (5 modes x 4 channels
  including `--format < file` x 3 payloads) — byte-identical output across
  channels, zero side effects, plain-stdin-still-executes confirmed, REPL
  unaffected via PTY. New regression coverage in
  `tests/system/test_visitor_stdin.py`.
- Known pre-existing residual (NOT this fix, ledgered): binary/non-UTF-8 stdin
  under any mode (including plain execution) tracebacks with `UnicodeDecodeError`
  at `sys.stdin.read()` — the r12 surrogateescape fix covered `FileInput` only.

## 0.602.0 (2026-07-04) - Fix: break/continue reset $? like bash; until-condition continue no longer hangs (reappraisal #17 H3)
- FIX. Reappraisal #17 Tier-1 H3. **A successful `break`/`continue` is a command
  that resets `$?` to 0**, but psh raised `LoopBreak`/`LoopContinue` without a
  status, so a loop fell back to the *previous iteration's* status. The extremely
  common `[ cond ] && break` idiom therefore made a loop exit 1 after any earlier
  failing iteration where bash reports 0: `for i in 0 1 2 3; do [ $i -ge 2 ] &&
  break; done; echo $?` printed `1` in psh, `0` in bash. This bit every loop type
  (`for`/`while`/`until`/C-style `for`/`select`) whenever the signal was taken via
  `&&` or `||` on a non-first iteration after a failure.
- Root cause: `BreakBuiltin` raised `LoopBreak` with `exit_status=None` (executors
  fell back to the stale body status) and `LoopContinue` carried no status at all.
  Fix: `core/exceptions.py` — `LoopContinue` gains `exit_status` (default 0),
  `LoopBreak`'s 0/1/None-sentinel semantics documented; `builtins/loop_control.py`
  — both `_transfer` methods raise with `exit_status=0` (out-of-range `break 0`/
  `continue 0` still carry 1); `executor/control_flow.py` — `_signal_status`
  generalizes the old `_break_status` so every body except-handler across all five
  loop types applies the signal's status (a manually raised signal with
  `exit_status=None` still keeps the body status), and `_reraise_loop_control`
  carries `exit_status` outward for nested loops.
- **Mirrored CONDITION-position semantics** (empirically pinned): a successful
  `break` in a `while` condition resets the loop status to 0, but a failed `break 0`
  there keeps the last body status; the `until` condition is the polarity mirror
  (a successful `break` keeps the body status, a failed `break 0` reports its
  failure).
- **ALSO FIXES A HANG.** `until continue; do :; done` looped forever in psh — a
  `continue` in an `until` condition now terminates the loop (keeping the last body
  status) like bash.
- **Correct child statuses at fork boundaries.** `executor/pipeline.py`,
  `process_launcher.py`, `child_policy.py`: a signal escaping a forked child
  (pipeline member, background, substitution) now exits the child with the signal's
  own status, so `x=$(break 0)` and `... | break 0` report 1 like bash.
- Bash-verified against **bash 5.2** (the project oracle), pinned by a truth table
  in `tmp/probes-r17t1-break/`. Known divergence: bash 3.2 differs on
  until-condition-`continue` list-abandonment (it does not abandon the list there);
  psh follows 5.2 (noted in the code comments). A pre-existing `! break` negation
  divergence surfaced during verification and is NOT a regression from this fix —
  it is recorded on the reappraisal #17 follow-up ledger.
- Tests: 36 regression tests in
  `tests/integration/control_flow/test_loop_status_reset.py` plus 12
  `tests/behavioral/golden_cases.yaml` pins (green under `--compare-bash`).

## 0.601.0 (2026-07-04) - Fix: readonly enforcement in arithmetic + assignment-error taxonomy (reappraisal #17 H1)
- FIX. Reappraisal #17 H1. **Readonly array elements were silently writable
  through every arithmetic entry point.** `readonly -a a=(1 2); (( a[0]=9 ))`
  (and `echo $((a[0]=9))`, `let 'a[0]=9'`; indexed and associative; all mutation
  forms `=`, `+=`, `++`, prefix `++`) wrote the element with no error — the
  arithmetic evaluator's `set_array_element` (`psh/expansion/arithmetic/evaluator.py`)
  mutated the variable's value directly and never checked `is_readonly`, while the
  parallel `SimpleCommand` assignment path (`executor/array.py`) did. It now raises
  `ReadonlyVariableError` at that chokepoint, flowing exactly like the
  already-correct scalar arithmetic path in every consumer.
- **Assignment-error taxonomy for arithmetic contexts.** A `ReadonlyVariableError`
  (or nameref-cycle error) raised from `(( r=9 ))`, `[[ $((r=9)) -eq 9 ]]`, a
  C-style `for` header expression, or a `for` loop-variable binding used to escape
  the handlers' narrow `(ValueError, ArithmeticError)` catch and surface as
  `psh: -c:1: unexpected error: ...`, **aborting the rest of a `-c` list**. A new
  shared helper `report_assignment_error()` (`executor/strategies.py`, beside
  `report_unbound_variable`) now renders the failure bash-style (message + status
  1) and the surrounding list/loop continues, matching bash. Routed from
  `visit_ArithmeticEvaluation`, `visit_EnhancedTestStatement`, the three C-style
  `for` sites (init returns 1; cond/update stop the loop), and the `for`
  loop-variable binding (which also gained the missing `NamerefCycleError` catch;
  the readonly message now names the resolved nameref target, like bash).
- **Cyclic-nameref writes inside arithmetic follow bash's warn-and-drop model.**
  A circular name-reference write now warns (`circular name reference`) and drops
  the assignment; evaluation continues (`(( na=5 ))` is status 0, `(( na=0 ))`
  status 1), handled at the evaluator's two write chokepoints. A cyclic-nameref
  `for`-loop binding remains an error (warn + status 1 + loop abandoned).
- **`(( ... ))` diagnostics honour the command's redirections.**
  `visit_ArithmeticEvaluation`'s error reporting moved inside the
  `guarded_redirections` scope, so a div-by-zero/readonly message respects
  `(( ... )) 2>/dev/null` like bash (matching the `visit_EnhancedTestStatement`
  sibling; previously the message leaked past the redirect).
- Bash-verified against bash 5.2: all command-context rows in
  `tmp/probes-r17t1-readonly/truth_table.py` match. Known residual (deliberately
  deferred to the Tier-2 arithmetic-error-model item): bash's discard-rest-of-line
  semantics after a failed `$(( ))` *expansion* on the same line — e.g. one-line
  `readonly r=1; echo $((r=9)); echo after` forms — still diverge; this cluster
  fixes the command-context (`(( ))`, `let`, `for`, `[[ ]]`) paths, not the
  same-line expansion-discard behaviour.
- Tests: 62 new (`tests/unit/expansion/test_arith_readonly_nameref.py`,
  `tests/integration/test_arith_readonly_continue.py`) plus 12
  `tests/behavioral/golden_cases.yaml` pins (green under `--compare-bash`).

## 0.600.0 (2026-07-03) - Fix: source/$0/LINENO/CR + POSIX short options; CRLF-file heredocs terminate (reappraisal #16 Tier 2 scripting cluster)
- FIX. Reappraisal #16 Tier 2, scripting cluster: a set of script-invocation and
  script-input defects, each pinned to bash 5.2. New/updated tests:
  `tests/system/test_r16_scripting.py`, `tests/system/test_cli_argument_parsing.py`,
  `tests/system/test_lineno_script_file.py`, `tests/unit/test_main_parse_args.py`,
  and two new golden cases in `tests/behavioral/golden_cases.yaml`.
- **`$0` is left unchanged inside a sourced file.** `source`/`.` no longer
  overwrites the caller's `$0` for the duration of the sourced script.
- **`$LINENO` no longer drifts per preceding line-continuation.** Each
  backslash-newline continuation used to subtract 1 from every later `$LINENO`;
  the value (and the line number in error messages) is now correct.
- **`set -- ARGS` inside a no-argument `source` persists to the caller.** A
  sourced file invoked without its own positional arguments that runs
  `set --` now updates the caller's positional parameters, matching bash.
- **`source` searches `PATH` before the current directory**, per POSIX, instead
  of preferring `./name`.
- **Carriage-return bytes in quoted script data are preserved.** Script files
  are opened with universal-newline translation off, so a literal CR inside
  quoted data survives instead of being rewritten to LF.
- **POSIX short invocation options accepted.** `-e`, `-u`, `-x`, `-v`, `-n`,
  `-f`, `-C`, and `-s` (read commands from stdin) are now recognized on the psh
  command line. Coverage supersedes the removed short-option absence entries in
  `tests/conformance/bash/test_absent_features.py`.
- **Follow-up: CRLF-line-ending script files with heredocs terminate.** The
  CR-preservation change regressed heredoc termination on CRLF files; a single
  shared heredoc-terminator matcher (which strips only one trailing carriage
  return) is now routed through all five heredoc-gathering layers
  (`heredoc_detection.py`, `command_accumulator.py`, `input_preprocessing.py`,
  lexer `heredoc_collector.py`, `cmdsub_scanner.py`), so a `<<EOF` delimiter on
  a CRLF line matches and later commands run.

## 0.599.0 (2026-07-03) - Fix: combinator named-fd redirects + honest [[ ]] compound rejection (reappraisal #16 Tier 2 combinator-parser cluster)
- FIX. Reappraisal #16 Tier 2, combinator-parser cluster (the combinator is
  educational-only; the recursive descent parser is production): two MED
  findings, each pinned to bash 5.2.26 and to the recursive descent parser.
  New/updated tests:
  `tests/integration/parser/test_combinator_parity_regressions.py` (named-fd
  three-way parity) and `tests/unit/parser/combinators/test_special_commands.py`
  (`[[ ]]` rejection classes).
- **Named-fd `{var}>fd` redirect no longer silently dropped (silent
  misexecution).** The combinator read `op_token.fd` but never `op_token.var_fd`,
  so `exec {fd}>/dev/null` parsed as a plain `exec >/dev/null` — permanently
  clobbering the shell's own stdout and leaving `$fd` unset. The bare dynamic-dup
  form `>&$var` was mis-composed too (`echo hi >&$v` leaked the `$var` target
  into the command, printing `hi1`). `_parse_redirection` now reads `var_fd` and
  carries it onto every Redirect it builds (heredoc, here-string, normal, and —
  via `_parse_dup_redirection` — every fd-duplication form), and the bare-dup
  operator with a separate dynamic target token (`>&`/`N>&` + expansion) is
  handled via `_FD_DUP_BARE_RE`, mirroring the recursive descent parser. All
  named-fd forms (`{fd}>`/`>>`/`<`/`<>`/`>|`/`>&`/`<&`/`>&-`/`{fd2}>&$fd`) now
  match bash and rd exactly.
- **`[[ ]]` boolean-compound / grouping / regex-parens fallback now rejects
  honestly instead of returning a plausible-but-wrong exit status.** The old
  `len>=3` fallback flattened the tokens with a lossy space-join, so
  `[[ a == a && b == b ]]` evaluated `a == "a && b == b"` (rc1, bash rc0) and
  `[[ ! a == a && b == b ]]` returned rc0 vs bash rc1. The combinator now
  HARD-REJECTS the constructs it cannot model (`&&`/`||`, grouping parens,
  multi-token `=~` regexes) with a committed parse error (exit 2) rather than
  shipping a silently-wrong status. Simple negation/unary/binary/single-operand
  tests and single-token regexes (`^a`, `[0-9]+`) still parse. Removed the
  now-dead `_operand_word`/`_format_test_operand` helpers.
- DELIBERATE divergence (documented educational-scope gap): bash/rd accept the
  rejected `[[ ]]` compounds (rc0/rc1); the combinator's exit-2 rejection is
  honest failure over silently-wrong, as the finding requires. Out of scope
  (bash accepts, but rd ALSO rejects, so not combinator-specific): `>& word`
  csh-style combined redirect.

## 0.598.0 (2026-07-03) - Fix: signal-death diagnostic for foreground externals + slash-path exec wording (reappraisal #16 Tier 2 executor-diagnostics cluster)
- FIX. Reappraisal #16 Tier 2, executor-diagnostics cluster: two bash 5.2
  divergences in the executor's failure diagnostics, each pinned to a live-bash
  probe. Exit codes were already correct and are unchanged; only the stderr
  text is new. New tests:
  `tests/integration/job_control/test_signal_killed_diagnostic.py` (serial,
  subprocess; expected wording computed via `signal.strsignal` for portability),
  `tests/integration/command_resolution/test_exec_failure_wording.py`, and seven
  promotable rows in `tests/behavioral/golden_cases.yaml`
  (verified `--compare-bash`).
- **Signal-killed foreground external now announced.** When a foreground
  external command dies by a signal other than SIGINT/SIGPIPE, bash prints a
  bash-style abnormal-termination line to stderr — "Terminated: 15",
  "Segmentation fault: 11", etc. — even non-interactively, then continues; psh
  was silent. Added `abnormal_termination_message()` (decodes a raw wait status
  via `signal.strsignal`, the same libc text bash uses, so wording tracks the
  host: "Terminated: 15" on macOS, "Terminated" on Linux, appending
  "(core dumped)" when a core was written) and
  `JobManager.report_abnormal_termination()`, called from the single foreground
  external wait path in `ExternalExecutionStrategy`. SIGINT/SIGPIPE deaths stay
  silent (bash parity).
- **Suppressed inside command/process substitution, reported in subshells.**
  bash suppresses the diagnostic inside command/process substitution but NOT in
  a `( )` subshell. A new `in_substitution` flag on `ExecutionState` is set at
  the `run_child_shell` substitution chokepoint (which serves exactly cmdsub +
  procsub, never subshells) and copied through subshell adoption so a subshell
  nested in a substitution stays silent too; the diagnostic is gated on it.
  Deliberate documented divergences: for signals other than SIGTERM bash adds a
  verbose "bash: line N: PID ... CMD" job header (psh emits just the signal
  description); and psh has no exec-last-command optimization, so a signal death
  that is the shell's LAST action, and pipeline-member deaths, differ from bash's
  exec-optimization / column job-notification machinery.
- **Slash-path missing command says "No such file or directory".** A nonexistent
  command given as a PATHNAME (a name containing a slash) said "command not
  found"; bash says "No such file or directory" (still exit 127).
  `report_exec_failure` now reports a slash-containing pathname that ENOENTs as
  "No such file or directory", reserving "command not found" for a bare
  unresolved name. This is the shared chokepoint, so the in-pipeline inline-exec
  path and the `command NAME` path get it too.

## 0.597.0 (2026-07-03) - Fix: fd-move [n]>&m-, csh >&word, exec all-or-nothing rollback, ANSI-C trailing \c (reappraisal #16 Tier 2 I/O + lexer cluster)
- FIX. Reappraisal #16 Tier 2, I/O-redirect + lexer cluster: four bash 5.2
  divergences, each pinned to a live-bash probe and captured as golden cases
  plus dedicated unit/integration suites
  (`tests/unit/lexer/test_ansi_c_quoting.py`,
  `tests/integration/redirection/test_fd_move_and_csh_redirect.py`). Both
  parsers (recursive-descent and combinator) were updated.
- **fd-move `[n]>&m-` / `[n]<&m-` (dup m onto n, then close source m)** was
  silently mis-parsed — the trailing `-` leaked as a command ARGUMENT, so no
  move happened and the wrong output resulted. The lexer now consumes the `-`
  into a single `REDIRECT_DUP` token and a new `Redirect.move` flag drives
  dup-then-close in `_redirect_dup_fd` (bash keeps the fd open when `m == n`).
  The builtin path decomposes a move into its dup plus a deferred source close,
  reusing the `>&-` stream-swap machinery so `echo x 3>&1-` reports a write
  error like bash. `saved_fds_for_plan` also backs up the source fd so a
  temporary move restores both fds.
- **csh-style `>&word` (fd omitted, non-numeric non-dash target)** is now the
  combined redirect `&>word` (both streams to the file), including the space
  form `>& word`, quoted words, and digit-prefixed non-numeric words (`>&2x` is
  one filename, not a dup plus argument). The lexer emits a bare `>&`/`<&`
  operator for a filename target; the parser classifies it
  (dup / close / combined / ambiguous). `resolve_dynamic_dup` skips combined
  redirects so the `>&` type is not mistaken for a dynamic fd dup.
- **`exec` with multiple redirects now rolls back all-or-nothing on partial
  failure**, matching bash. `apply_permanent_redirections` snapshots the fds
  and Python streams before applying; any failure restores every applied
  redirect and closes what this call opened, so `exec 3>ok 4>/nonexistent/x`
  leaves fd 3 closed and `ok` empty. Successful lists close the fd backups so
  they do not leak.
- **Trailing `\c` in a `$'...'` ANSI-C string** no longer over-consumes the
  closing quote (was: "Unclosed $' quote"). `handle_ansi_c_escape` takes the
  string's closing delimiter and leaves `\c` literal when no control char
  remains before the quote — bash finds the closing quote before decoding
  escapes. The `${var@E}` path (no delimiter) still consumes the next char.
- **Docs truth-up (reappraisal #16 H7 stale-negative)**: removed the two
  now-false claims in `docs/user_guide/09_io_redirection.md` that the csh-style
  `>& file` syntax is unsupported, since this release implements it.
- **Disclosed residuals**: a *temporary* (non-`exec`) fd-move restores the
  closed source fd for later commands where bash leaves it closed (minor);
  `>&$var` with a non-numeric value keeps psh's dynamic-fd-dup semantics
  (reports "ambiguous redirect") rather than bash's combined-redirect reading;
  and `exec` rolls back before printing its diagnostic, so when stderr itself
  is a rolled-back fd the message lands on the restored stderr.

## 0.596.0 (2026-07-03) - Fix: colon-operators test joined-nullness on @/* views; @A/@a strip subscript; reject positional/special :=/= (reappraisal #16 Tier 2 expansion-operators cluster)
- FIX. Reappraisal #16 Tier 2, expansion-operators cluster: three parameter-
  expansion defects on multi-element views, each pinned to bash 5.2 and
  captured as golden cases plus a dedicated unit suite
  (`tests/unit/expansion/test_view_operators_joined_nullness.py`).
- **Colon operators on `@`/`*` views test the JOINED view for null, not the
  element count**: `${a[@]:-D}`, `${a[@]:+X}`, `${a[*]:+X}`, `${@:-D}`, and
  `${@:+X}` (and their `*` analogues) now decide "null" by whether the *joined*
  view is empty — a space join for `@` views, IFS[0] for `*` views — matching
  bash, instead of psh's old element-count test. So `a=("")` yields
  `${a[@]:+X}` -> `` (joined view is null) while `a=("" "")` yields `X` (the
  joined view is a single space). The non-colon variants (`${a[@]+X}`) still
  test set-ness. A new `OperatorOpsMixin._view_conditional` is the single
  authority both the quoted-fields path (`fields.py`) and the whole-array path
  (`variable.py`) route through.
- **`@A`/`@a` on a single array element report the array, not the element**:
  `${a[1]@A}` now prints an assignment to the array NAME (`declare -a a='2'`)
  and `${a[1]@a}` reports the array's flags, exactly as bash does (a subscript
  reference carries the whole array's attributes). Associative elements
  (`${m[k]@A}` -> `declare -A m='v'`) behave the same.
- **`:=`/`=` on a positional or special parameter is rejected like bash**:
  `${1:=x}`, `${@:=x}`, `${*:=x}`, `${#:=x}` etc. now abort with
  `$N: cannot assign in this way` (exit 1) rather than silently returning the
  default. Assign/`:=` on an `@`/`*` array view likewise raises bash's
  `name[@]: bad array subscript`, since such a view can never be assigned.
- **Truth-up (no behavior change)**: `GlobExpander` now carries an accurate
  comment that glob results are sorted in byte (C-locale) order, a deliberate,
  documented divergence from bash's `strcoll`-in-`LC_COLLATE` sort — the same
  known limitation as `[[ < ]]`/`[ < ]` collation, not fixed here.
- **Disclosed residual**: `@A` on an *unset* array element still diverges from
  bash (out of scope for this cluster).

## 0.595.0 (2026-07-03) - Fix: mypy gate hole, expand_aliases toggle, HISTFILESIZE/HISTSIZE, validator/formatter (reappraisal #16 Tier 2 tooling cluster)
- FIX. Reappraisal #16 Tier 2, tooling/cross-cutting + visitor cluster: five
  defects in the type gate, the alias-expansion option, history-size handling,
  the `--validate` pass, and the `--format` pass, each pinned to bash 5.2 and
  captured as golden cases / regression tests.
- **mypy gate hole closed**: `[tool.mypy].files` enumerated `psh/builtins` and
  `psh/parser/recursive_descent/parsers` file-by-file, so campaign-added modules
  (`loop_control.py`, `base.py`) escaped the type gate. The `files` list is now
  a single `psh` directory glob — mypy checks all 240 source files and stays
  clean, and the CLAUDE.md "new modules are auto-picked-up by the package globs"
  claim is now literally true. A new meta-test
  (`tests/unit/tooling/test_mypy_scope.py`) asserts every `psh/**/*.py` is inside
  the mypy scope, so a module can never again slip the gate.
- **`shopt -u expand_aliases` now gates alias expansion**: the option was
  registered but never read (accept-and-ignore). `Shell.expand_aliases` is now
  the single lex→parse-boundary gate that the four scripting call sites route
  through, so disabling the option suppresses expansion of subsequently-parsed
  commands. psh keeps the option ON by default in every mode (bash defaults it
  OFF non-interactively) so alias-reliant `-c`/script tests keep working — a
  documented divergence, as is the same-line `shopt -u`/use case (psh expands the
  whole logical command at once).
- **`HISTFILESIZE` is honored**: previously ignored (the file was trimmed to
  `HISTSIZE`). `HistoryManager.save_to_file` now trims the FILE to
  `$HISTFILESIZE`, distinguishing unset (fall back to `$HISTSIZE`), empty /
  negative / non-numeric (inhibit truncation → unlimited), `0` (truncate to an
  empty file), and `N` (last N lines) exactly as bash-5.2.26 does. `HISTFILESIZE=0`
  emptying the file is pinned as a regression test (the naive `combined[-0:]`
  slice had kept the whole list).
- **`HISTSIZE` negative means unlimited**: a negative `HISTSIZE` now reports
  `sys.maxsize` rather than capping at the 1000 default.
- **`--validate` no longer false-warns undefined-variable for assigning
  builtins**: `printf -v VAR`, `mapfile`/`readarray`, and `getopts` (plus its
  `OPTARG`/`OPTIND`) now record the variables they define.
- **`--format` idempotent for a backgrounded top-level item**: `echo a & echo b`
  had formatted with a blank line after `&` that a re-format removed; a
  `&`-terminated top-level item now joins its successor with a single newline so
  `format(format(x)) == format(x)`.
- Deliberate residuals (report-only, tracked): a sibling `HISTSIZE=0` load-path
  slice, and the append-only history-persistence design not modeling bash's
  truncate-on-assignment.

## 0.594.0 (2026-07-03) - Fix: secondary builtin flags (reappraisal #16 Tier 2 builtins-flags cluster)
- FIX. Reappraisal #16 Tier 2, builtins-flags cluster: a set of secondary
  flags on existing builtins that psh silently ignored or mishandled, each
  pinned against bash 5.2 and captured as golden cases (verified with
  `--compare-bash`).
- **`[[ -o OPTNAME ]]` / `[ -o OPTNAME ]` shell-option test**: both bracket
  forms now evaluate `-o` as a unary shell-option predicate (true when the
  named `set -o` option is on, false when off or unknown), matching bash.
- **`[[ -R NAME ]]` nameref test**: the `-R` unary operator is true only when
  NAME is a set nameref variable (false for a plain variable or a missing
  name). The recursive-descent test parser gained `-R` recognition.
- **`exec -a NAME` / `exec -c` / `exec -l`**: `exec` now honours the bash flags
  — `-a NAME` sets argv[0] of the replacement process, `-c` runs it in an empty
  environment, and `-l` prepends `-` to argv[0] to launch a login shell.
- **`pushd -n` / `popd -n`**: the `-n` flag manipulates the directory stack
  without changing the current directory (push/pop the entry only).
- **`unset -vf`**: passing both `-v` and `-f` is now rejected with bash's
  "cannot simultaneously unset a function and a variable" error (status 1).
- **`type` consults the command hash table**: a hashed command reports as
  `NAME is hashed (PATH)` and `type -t` reports `file`, matching bash.
- **`printf '%()T'`**: an empty time conversion uses a default format instead
  of erroring.
- **`umask -S MODE`**: `umask -S` with a MODE operand echoes the symbolic
  result (e.g. `u=rwx,g=rx,o=rx`) rather than applying it silently.
- Deliberate residuals (edge/pre-existing, tracked): `pushd -n` with no operand
  prints extra dirs, `pushd -n` path normalization, `type -P` on a
  hashed-but-not-in-PATH name, `[[ -o ]]` on options psh does not model, and
  the cosmetic `psh:` error prefix.

## 0.593.0 (2026-07-03) - Fix: core/options bash divergences (reappraisal #16 Tier 2 core/options cluster)
- FIX. Reappraisal #16 Tier 2, core/options cluster: seven bash-5.2
  divergences in the shell-state / options surface, each probe-pinned via a
  bash-vs-psh truth table and captured as golden cases (verified with
  `--compare-bash`).
- **`declare -g NAME=val` now forces the GLOBAL scope past a same-named local
  shadow** instead of writing the local. `ScopeManager.set_variable` gained a
  `global_scope` flag that targets `scope_stack[0]` for the value write and the
  existence / readonly / attribute-merge checks. Covers `-g`, `-gi`, `-gx`, and
  the `-gA` / `-ga` array forms, plus the bare-name attribute path
  (`declare -gr`/`-gx NAME`) via a global-only lookup in
  apply_/remove_attribute. The export->env observer reflects the innermost
  EXPORTED instance, so `declare -gx x` under a non-exported local keeps the
  global's env entry.
- **`set +o` output is now reusable.** Bare `set +o` had dumped every registry
  option, so `eval "$(set +o)"` spewed "invalid option name". It now emits only
  reusable SET-category boolean names; underscore-named SET options round-trip.
- **Readonly-declaration errors are one clean bash-word-order message** instead
  of being double/triple-wrapped through the declaration builtins. Still
  non-fatal — the command list keeps running.
- **`local -` implemented**: it snapshots the SET-category options and edit mode
  onto the function scope and restores them on function return (options changed
  via `set` in the body revert; `shopt` does not).
- **`set -o` lists `emacs` and `vi` once each** (the separate edit-mode block
  that printed them a second time with clashing values is gone).
- **INTERNAL-category options (`interactive`, `stdin_mode`, `command_mode`) are
  rejected by name** — `set -o interactive` no longer corrupts `$-` with a
  spurious `i`.
- **An ignored (`trap '' SIG`) disposition is inherited across `exec` by
  external children (POSIX)**: reset_child_signals keeps a parent's `SIG_IGN`
  instead of forcing `SIG_DFL`; a signal trapped WITH an action still resets to
  default in the exec'd child.
- Remaining deliberate residuals (ledgered): `declare -g NAME+=value` over a
  local shadow reads the local base (narrow adjacent), and `readonly` inside an
  arithmetic `(( ))` assignment is a pre-existing fatal-vs-continue path.

## 0.592.0 (2026-07-03) - Fix: lexer command-position feeding + parser one-liners (appraisal #16 follow-up ledger g)
- FIX. Reappraisal #16 follow-up ledger, item (g), plus three same-area parser
  one-liners. The lexer's command-position machinery is now fed the grammar
  contexts it was missing. All bash-pinned against 5.2; both parsers verified.
- **g1 — `f() [[ ... ]]` and `[[` at the start of a case body were rejected.**
  After `)` the lexer reset command position, so the following `[[` lexed as a
  plain WORD (parser: "Expected '{' for function body" / "[[: command not
  found"). A `)` now returns the lexer to command position, mirroring the
  keyword normalizer. The function-body parser's DOUBLE_LBRACKET branch was
  already wired — it just never received the token.
  - The `)` -> command-position transition is scoped to **outside** a
    `[[ ... ]]` conditional (guarded by `bracket_depth == 0`). Inside a
    conditional a `)` is part of the operand — e.g. the group close in
    `=~ ([[:alpha:]]+)[[:space:]]+([[:alpha:]]+)` — and must not flip command
    position, or the following `[[` is mis-lexed as the DOUBLE_LBRACKET
    operator.
- **g2 — the POSIX no-`in` for/select form (`for x do` / `for x; do`) was
  rejected.** `do` closing a no-`in` loop header lexed as a WORD. The normalizer
  now converts it to DO and clears the pending-`in` state — also plugging a
  latent leak where `for x; do echo in; done` mis-read the body's `in` as the
  loop keyword — and is made idempotent across the normalizer's two passes.
- **Parser one-liners:**
  - `time <lone compound>` dropped its timing report: the bare-top-level-compound
    unwrap guarded `negated` but not its `timed` sibling.
  - `! ! cmd` double-negation was rejected: the single negation consume is now a
    loop toggling negation (`! ! true` -> 0, `! ! ! true` -> 1).
  - consecutive `;` (`echo a; ; echo b`) ran both commands: the interstatement
    separator skip now leaves a second `;` for the parser to reject, matching
    bash in every command-list context.
- **Deferred (documented):** the STRETCH `((echo a); echo b)` disambiguation —
  bash re-reads `((` as nested subshells `( (` when the content is not valid
  arithmetic — needs speculative parse-with-backtrack and is honestly deferred.
- Frozen lexer-corpus: one row updated surgically (the degenerate `a[$(x])]=v`
  now lexes `]` as RBRACKET after `)`; both shells reject the input). New tests:
  `test_command_position_feeding.py`, `test_r16_command_position.py`, extended
  `test_bang_prefix_compound.py` / `test_statement_separators.py` /
  `test_time_keyword.py`, and 8 `golden_cases.yaml` entries.

## 0.591.0 (2026-07-03) - Fix: extglob alternation is leftmost-longest in substitution operators (appraisal #16 ledger f)
- FIX. Reappraisal #16 follow-up ledger, item (f).
- **extglob alternation matched Python-`re` leftmost (first alternative that
  succeeds) instead of bash leftmost-longest.** The unanchored
  parameter-substitution operators `${v/pat/r}`, `${v//pat/r}`, and `${v/#pat/r}`
  routed non-negation extglob patterns through a Python `re`, whose alternation
  commits to the first alternative that lets the overall regex succeed and never
  extends to the longest. So the prefix-anchored `${v/#@(a|aa)/Z}` on `aaX` gave
  `ZaX` (matched the short `a`) where bash gives `ZX` (matched `aa`), and
  `@(a|ab)b` on `abb` stopped at the first success instead of extending the group
  to `ab` to match the whole string.
  - **Fix.** Reordering alternatives longest-first cannot fix this — the winning
    length is input-dependent and `re` returns on first success regardless of
    order (the truth table ruled that out). The three unanchored operators now
    route non-negation extglob through the existing backtracking matcher
    (`extglob_match_at`), which enumerates every reachable end index and takes the
    maximum — POSIX leftmost-longest. That matcher was already used, and correct,
    for negation patterns.
  - The removal (`#`/`##`/`%`/`%%`), suffix-substitution (`/%`), and
    case-modification operators were already correct (they scan every candidate
    length, end-anchor, or match a single char) and are unchanged.
  - Empty-match semantics are preserved exactly: `substitute_all` gets a
    matcher-based scan mirroring `_substitute_all_empty_aware`, and
    `substitute_first` suppresses the zero-width end-of-subject match only for
    negation. bash's separate per-quantifier suppression of the empty match for
    `?(x)` on an *empty value* is a pre-existing divergence not derivable from
    the match extent (the plain-regex path diverged there too); it is left as-is.
  - Truth table (bash 5.2) covers prefix/first/all, order-independence, nested
    `@(a|@(b|bb))`, backtrack-forced-by-trailing-literal, empty-capable
    alternation, and empty-value regressions. Tests: a unit class in
    `test_patsub_nocase_and_anchoring` plus five golden cases (verified with
    `--compare-bash`). The fix reuses the existing (unmodified) `extglob_match_at`
    from `extglob.py`; the only production change is in `parameter_expansion.py`.

## 0.590.0 (2026-07-03) - Fix: arithmetic number literals and test integer operands match bash (appraisal #16 ledger c + d)
- FIX. Reappraisal #16 follow-up ledger, items (c) and (d).
- **(c) arithmetic number tokenizer left a stray trailing token on out-of-base
  digits.** The number reader stopped at the first character invalid for the
  base and left the rest as a separate token, so `$((0xffg))` reported
  `Unexpected token after expression: g` instead of bash's
  `value too great for base`; `00x`, `07x`, `0a`, `5a`, and `123abc` behaved the
  same way. The #16 H5 fix had already corrected this for `base#number`
  literals, but the hex, octal, and decimal readers were untouched.
  - **Fix.** Hex, octal, decimal, and `base#number` now all go through one
    `_read_digits()` chokepoint, which consumes the whole based-number run
    (`[0-9a-zA-Z@_]`, bash's alphabet) and raises
    `value too great for base (error token is ...)` on any digit out of range —
    matching bash's single-token error and message exactly. A bare `0x`/`0X`
    with no hex digits now yields `0`, matching bash. The now-unused
    `read_decimal()` was removed.
- **(d) `test`/`[` accepted integer operands outside signed 64-bit.** The
  integer comparisons (`-eq`/`-ne`/`-lt`/`-le`/`-gt`/`-ge`) converted operands
  with Python's arbitrary-precision `int()`, so `test 9223372036854775808 -gt 5`
  returned 0 where bash, using `intmax_t`, rejects it (exit 2,
  `integer expression expected`).
  - **Fix.** A new `_to_int64()` parses base-10 like bash and rejects a
    non-numeric OR out-of-64-bit operand, so the six comparison ops report
    `TOKEN: integer expression expected` exactly like bash. In-range comparisons
    (including the exact +/- 2**63 boundaries) are unchanged.
- Verified against a 40-probe bash-vs-psh truth table (arithmetic `$(( ))`,
  `let`, `declare`, hex/octal/decimal edges, and `test`/`[` across the 64-bit
  boundary); every case matches bash in stdout, exit code, and stderr presence.
  Added hex/octal/decimal error + empty-hex characterization tests,
  `test`/`[` int64-range unit tests, and 9 golden cases (`--compare-bash`).
  - Documented residuals (pre-existing, out of scope): `declare -i x=0xffg`
    now emits the bash arith message but psh's builtin guard converts the error
    to exit 1 and continues where bash aborts the command list — that is the
    assignment-vs-`let` fatal-error routing in the builtin guard, not the
    tokenizer. `test` also still accepts Python underscore digit separators.

## 0.589.0 (2026-07-03) - Fix: nocasematch keeps upper/lower classes case-sensitive in [[/case; POSIX classes in the =~ regex operator (appraisal #16 ledger b + e)
- FIX. Reappraisal #16 follow-up ledger, items (b) and (e). Two fixes wiring
  the pattern engine (made ignorecase-ready by #16 H6) correctly into the
  test/case evaluators.
- **(b) `nocasematch` over-folded `[[:upper:]]`/`[[:lower:]]`.** Under
  `shopt -s nocasematch`, bash folds literals, ranges, and character sets but
  keeps the `[[:upper:]]` and `[[:lower:]]` POSIX classes case-SENSITIVE. H6
  taught `shell_pattern_to_regex` to protect those two classes with a scoped
  `(?-i:...)` group, but `match_shell_pattern` applied `re.IGNORECASE` WITHOUT
  forwarding `ignorecase` to the builder, so the protection never engaged.
  Probe: `shopt -s nocasematch; [[ h == [[:upper:]] ]]` wrongly matched (rc 0)
  under psh but is false (rc 1) under bash.
  - **Fix.** Forward the `ignorecase` flag through `match_shell_pattern` — the
    ready chokepoint — so the scoped-non-ignorecase protection H6 already built
    engages. One-line forward fixes both the `[[ ]] ==` and `case` paths;
    `control_flow.py` already passed `ignorecase` and is untouched.
- **(e) `=~` did not translate POSIX bracket classes and leaked a
  `FutureWarning`.** The `=~` regex path built a Python regex without
  translating POSIX bracket classes, so `[[:punct:]]` reached `re` as a nested
  set — wrong match plus `FutureWarning: Possible nested set` on stderr in
  default mode.
  - **Fix.** Share the glob engine's class table via a new
    `translate_posix_classes()` in `glob.py` — classes only, since `=~` is an
    ERE not a glob (no glob-metacharacter handling). All 12 POSIX classes now
    match bash ERE with zero warning leaks. Under `nocasematch` bash's `=~`
    uses `REG_ICASE`, which folds `[[:upper:]]`/`[[:lower:]]` too (unlike
    `==`/`case`), so no case protection is applied on the `=~` side — matches
    bash.
  - Also fixes a pre-existing parse error for POSIX classes inside `=~` capture
    groups: `([[:alpha:]])` lexed with the inner `[[`/`]]` mis-tokenized as
    double brackets, and `_parse_regex_operand` stopped at the FIRST `]]`.
    Paren depth is now tracked so a `]]` only terminates the test at group
    depth 0, enabling the documented `([[:alpha:]]+)([[:digit:]]+)`
    `BASH_REMATCH` idiom (appendix_c).
  - **Deliberate residual:** a `=~` operand containing a double-open-bracket
    that is NOT one of the 12 recognized classes can still leak the internal
    warning (pre-existing, low-frequency). The educational combinator parser
    also flattens a grouped `=~` operand with spaces so the class can't
    translate — a documented limitation, and outside the production bar.
- Verified against a 151-case bash-vs-psh truth table across all 12 POSIX
  classes in `[[ ==`, `case`, and `=~` (quoted/unquoted, negated, combined,
  grouped) with zero `FutureWarning` leaks (checked under
  `-W error::FutureWarning`); H6 patsub/glob nocasematch re-confirmed intact.
  Pinned by unit, integration, conformance, and golden-case tests.
  Files: `pattern.py`, `enhanced_test_evaluator.py`, `glob.py`, `tests.py`.

## 0.588.0 (2026-07-03) - Fix: temporary-redirect fd backups saved high so closed std fds stay closed (appraisal #16 ledger a)
- FIX. Reappraisal #16 follow-up ledger, item (a). A redirected
  function/compound body run after `exec 1>&-` closed fd 1 leaked its stdout to
  the shell's real stderr and returned rc 0, instead of failing with EBADF like
  bash. Probe: `exec 1>&-; f(){ echo OUT; }; f 2>/dev/null` printed `OUT` on the
  real stderr under psh (rc 0) but is silent with rc 1 under bash.
  - **Root cause.** `FileRedirector.saved_fds_for_plan` backed up a temporary
    redirect's fd with a plain low `os.dup`. After `exec 1>&-` freed fd 1, that
    `os.dup` landed the backup in the freed fd-1 slot — a slot the stale
    `sys.stdout` wrapper still names — so a builtin's write to `sys.stdout`
    flowed into the backup (the shell's real stderr) instead of hitting a closed
    descriptor and failing EBADF.
  - **Fix.** Save every temporary-redirect backup on a HIGH fd via
    `_save_fd_high` (`fcntl F_DUPFD`, floor 10), matching bash's practice of
    keeping internal saved descriptors above fd 10 — the same reasoning already
    used for the combined `&>` save. Applied at the single shared chokepoint,
    this repairs the function, brace-group, `if`/`while`/`for`, and
    forked-subshell paths together. The now-dead `_save_fd` helper was removed.
  - The #16 H1 builtin path in `io_redirect/manager.py` is untouched (only a
    one-word docstring reference updated) and its pins still pass.
  - Pinned by four new `tests/behavioral/golden_cases.yaml` cases
    (redirected function body, nested functions, brace group all silent with
    rc 1; plus a `f 1>&2` reopen case that still writes, guarding against
    over-severing) and a new
    `tests/unit/io_redirect/test_builtin_dup_source_reassigned.py`.

## 0.587.0 (2026-07-03) - Fix: multi-line paste, Ctrl-R inclusive re-search, @P marker strip (appraisal #16 H8 + MED)
- FIX (HIGH). Reappraisal #16 finding H8 (interactive line editing), three
  defects, all pinned to bash 5.2:
  - **Multi-line paste merged commands.** LF/Ctrl-J (`0x0a`) was unbound in the
    line editor, so pasting a two-line block (`echo one<LF>echo two`) dropped
    the newline and ran the single corrupt command `echo oneecho two` — bash
    runs both. LF/Ctrl-J are now bound to `accept_line` in the emacs and both vi
    keymaps (matching readline). Binding LF alone was insufficient: the greedy
    `os.read()` pulls the whole paste into the `KeyDecoder` buffer and a fresh
    decoder per read discarded the tail past the newline, so the second command
    vanished. `KeyDecoder.take_buffered()`/`seed()` now carry the unconsumed
    tail across reads, so the paste's later commands run in turn. Multi-line
    *construct* paste (`if/then/fi`) still accumulates via the
    `CommandAccumulator`; a single Enter (CR) still accepts.
  - **Ctrl-R incremental search recalled the wrong (older) entry.**
    `HistorySearch._perform` always searched strictly before the current
    position, so extending a still-matching pattern jumped to an older entry and
    flashed a spurious "failed". Refining a pattern that still matches now
    re-searches from the current entry *inclusive* (readline semantics); only an
    explicit Ctrl-R/Ctrl-S step moves off the current match.
- FIX (MED). `${var@P}` leaked readline non-printing markers. `expand_full`
  turned `\[ \]` into `0x01`/`0x02` and returned them un-stripped; the renderer
  strips them for PS1 *display* but the `@P` *operator* value kept them. bash's
  `@P` yields a plain string with the brackets removed. `readline_markers` is
  now threaded through `expand_full`/`expand_prompt_segments`/`_expand_escape`
  and the `@P` call site passes `readline_markers=False`, so `\[ \]` decode to
  nothing. Literal `0x01`/`0x02` bytes and octal `\001` escapes already in the
  value are preserved (bash), and PS1/PS2 rendering is unchanged (still emits
  the markers).
- Tests: `HistorySearch` inclusive re-search pins (the tests that pinned the old
  strictly-before quirk were re-verified against bash and updated), LF→
  `accept_line` keybinding pins, `KeyDecoder` carry-over pins, `@P` marker-strip
  pins (in-process + bash-parity subprocess), two golden cases (`@P` bracket
  strip / octal keep), and a PTY class covering paste + LF + Ctrl-R. Full local
  gate green (9970 passed, 558 skipped, 13 xfailed); ruff and mypy clean.

## 0.586.0 (2026-07-03) - Docs: ch17/README stale-negative truth-up + proving conformance tests (appraisal #16 H7)
- DOCS (HIGH). Reappraisal #16 finding H7 — the ch17 compatibility tables and
  the README prose misclaimed several working, bash-matching features as
  unsupported. The positive-claim meta-test only guarded rows marked "Full
  support", so these false NEGATIVES went undetected for many releases. Each
  suspect row was probed against live bash first; only the genuinely-full rows
  were flipped to "Full support" with new bash-verified conformance tests plus
  `CLAIM_TESTS` mappings:
  - **History expansion** (`!!`, `!n`, `!-n`, `!string`, `!?string?`, word
    designators `!$`/`!^`/`!*`/`!!:n`/`!!:n-m`, the `:h`/`:t`/`:r`/`:e`/`:s`/
    `:g&`/`:p` modifiers, and `^old^new`) — new
    `tests/conformance/bash/test_history_expansion_conformance.py`.
  - **`${!prefix*}` / `${!prefix@}` variable-name prefix matching** and the
    **associative `${var@K}` / `${var@k}` uppercase/lowercase-key transforms** —
    new probes in `tests/conformance/bash/test_user_guide_notes_conformance.py`.
- DOCS. Removed a stale contradiction in ch17's "Other Missing Features" that
  still said `${!PATH*}` "lists ALL variables" (a bug that was already fixed),
  and corrected ch05's note claiming `"${!prefix@}"` collapses to one word
  (it expands to one word per name, matching bash).
- DOCS (kept honest). `read` stays **Partial**: its `-e`/`-i` readline-editing
  options are genuinely unsupported. History expansion's `:q`/`:x` word-quoting
  modifiers and the `!#` current-line designator are enumerated in the Notes so
  the flipped row is honest rather than over-claiming.
- META-TEST. Added a symmetric stale-NEGATIVE guard to
  `tests/conformance/test_claims_have_tests.py`: every `Yes | No` row now needs
  a `NO_ROW_PROBES` entry (a command that diverges from bash *because* psh lacks
  the feature). If psh ever grows the feature, the probe starts matching bash
  and fails, forcing whoever shipped it to flip the row and add a proving test.
- **Scope.** Docs + conformance/meta tests only — no `psh/` source change.
  Verified: meta-test green, 122 conformance tests passed, 131 history tests
  passed; full local gate green.

## 0.585.0 (2026-07-03) - Fix: POSIX bracket classes punct/cntrl/graph/print + no FutureWarning leak; nocasematch/extglob patsub (appraisal #16 H6 + 3 MED)
- FIX (HIGH). Reappraisal #16 cluster H6 — `punct`, `cntrl`, `graph`, and
  `print` were absent from `_POSIX_CLASSES`, so the literal `[:class:]` text
  reached Python `re`/stdlib `fnmatch` as a nested set: the match was wrong AND
  a `FutureWarning: Possible nested set` leaked to stderr in default mode. Added
  the four ranges (`psh/expansion/glob.py`), each written to embed safely in
  BOTH a Python `re` character class and `fnmatch` (no leading `!`/`^`, no bare
  `]`/`\`). `glob.glob` splits on `/` before matching, so the pathname engine
  uses a `punct` variant with `/` dropped (`_POSIX_CLASSES_PATHNAME`) — a
  filename can never contain `/`, so the match set is identical. The fix reaches
  every site: `[[ ]]`, `case`, prefix/suffix removal, and pathname globbing.
- FIX (MED, `nocasematch` in patsub). `shopt -s nocasematch` was honored by
  `case`/`[[` but never threaded into `${v/pat/r}` (nor its `/#` and `/%`
  forms). Following bash, it now applies to substitution — folding literals,
  explicit ranges (`[A-Z]`), and sets (`[abc]`) — but NOT to `#`/`%` removal or
  case modification. The `[:upper:]`/`[:lower:]` POSIX classes are kept
  case-SENSITIVE (bash does not fold them) by emitting only those two inside a
  scoped `(?-i:...)` group; a new `ignorecase` flag threads through the single
  shared converter chain (`shell_pattern_to_regex` →
  `glob_to_regex_body`/`extglob_to_regex` → `_convert_pattern` →
  `_bracket_to_regex`) and the backtracking matcher. The `ignorecase=False`
  path is byte-for-byte identical to before, so the change is confined to the
  nocase+bracket slice; only the four patsub `substitute_*` callers opt in.
- FIX (MED, front-anchored patsub with extglob). `substitute_prefix` requested
  an anchored regex, but the extglob converter appends a trailing `$`, so `/#`
  demanded a full-string match and `${v/#+(a)/Z}` on `aaXaa` left the value
  unchanged. It now anchors at the start only (as the suffix path already did),
  so the unanchored body matches a real prefix.
- FIX (MED, extglob non-final path). `_expand_extglob` ran the matcher only on
  the basename, leaving a leading extglob component literal
  (`@(d1|d2)/file`). It now walks the pattern one path component at a time,
  matching extglob, plain-glob, and literal components per level.
- **Verification.** Pinned to bash 5.2.26 (C locale) with a truth table before
  fixing (12 POSIX classes × ASCII chars × `[[ ]]`/`case`/removal). Full gate
  green (9,894 passed), ruff and mypy clean; new golden cases pass under
  `--compare-bash`.
- **Deliberate remaining divergences (pre-existing sibling paths, NOT this
  fix):** `case`/`[[` + `nocasematch` + `[:upper:]`/`[:lower:]` share the same
  over-fold — the shared converter chokepoint is now ready to close it later;
  the `=~` regex-match operator's POSIX classes leak a `FutureWarning` at a
  separate site (`enhanced_test_evaluator.py`); extglob patsub leftmost-longest
  alternation (`${v/#@(a|aa)/Z}`) is a Python-`re` alternation-ordering limit.
- **Tests.** `tests/unit/expansion/test_posix_char_classes.py`,
  `test_patsub_nocase_and_anchoring.py`,
  `tests/integration/test_extglob_nonfinal_path.py`, plus new golden cases in
  `tests/behavioral/golden_cases.yaml`.

## 0.584.0 (2026-07-03) - Fix: wrap arithmetic literals to signed 64-bit; negative-shift masking; base-N literal errors (appraisal #16 H5 + 2 MED)
- FIX (HIGH). Reappraisal #16 cluster H5 — integer **literals** at or above
  `2**63` were not wrapped to signed 64-bit. Every arithmetic *operation*
  wrapped via `_to_signed64`, but a bare/assigned/compared/subscript literal did
  not, so `$((9223372036854775808))` kept the unsigned value where bash gives
  `-9223372036854775808`, and `[[ 9223372036854775808 -eq -9223372036854775808 ]]`
  wrongly compared unequal. Fed to an array subscript, the huge value made
  `all_elements()` iterate `range(2**63)` and HANG.
  - **Fix (`psh/expansion/arithmetic/evaluator.py`).** Wrap at the three leaf
    value sources the evaluator funnels every operand through: `NumberNode`
    literals, the `get_variable` plain-decimal fast path, and `_string_to_int`.
    All literal forms (decimal/hex/octal/`base#n`) become `NumberNode`, so one
    wrap there covers them; the two variable-value `int()` paths cover assigned
    literals read back from storage. A literal is now wrapped exactly like an
    operation result, matching bash across arithmetic-expand, `let`, `declare -i`,
    C-`for`, the arithmetic command, `test -eq`, substring offset, and array
    subscript. A wrapped-negative subscript then hits the existing out-of-range
    check and reports bash's "bad array subscript" instead of hanging.
- FIX (MED, negative shift). The `LSHIFT`/`RSHIFT` handlers raised a spurious
  "negative shift count" via a guard sitting immediately in front of the already
  present `& 63` mask. bash masks the count to 6 bits on x86-64
  (`1<<-1 == 1<<63 == -9223372036854775808`, `256>>-1 == 0`, `1<<-64 == 1`), so
  the guard is removed and the mask now yields bash's answer directly.
- FIX (MED, base-N literal). A `base#n` literal with an out-of-range digit
  stopped at the first bad digit, leaving trailing chars as stray tokens
  ("Unexpected token after expression: 2"). The tokenizer
  (`psh/expansion/arithmetic/tokenizer.py`) now consumes the whole base-digit
  run (`[0-9a-zA-Z@_]`, bash's based-number alphabet) before validating and
  raises a "value too great for base" error, mirroring the octal reader.
- **Verification.** A bash-vs-psh truth table across `$(( ))`, `(( ))`, `let`,
  `declare -i`, C-`for`, `a[expr]`, substring offset, and `[[ -eq ]]` — all 44
  probes match bash in stdout, exit code, and stderr presence. Full gate green
  (9,819 passed), ruff and mypy clean.
- **Deliberate remaining divergences (pre-existing sibling paths, not H5):** the
  hex reader has the same stray-token class; the `test` builtin does not wrap
  literals; substring-offset error wording differs. Left for separate findings.
- **Tests.** Updated the negative-shift characterization test (it pinned the old
  error behavior; bash masks) plus bare-literal / negative-shift / base-N-error
  coverage in `tests/unit/expansion/test_arithmetic_characterization.py`; 11 new
  arithmetic golden cases in `tests/behavioral/golden_cases.yaml` (pass under
  `--compare-bash`).

## 0.583.0 (2026-07-03) - Fix: seed `IFS` as a real shell variable (appraisal #16 H3)
- FIX (HIGH). Reappraisal #16 cluster H3 — psh never seeded `IFS` as a real
  variable. It only used the default `<space><tab><newline>` as an internal
  word-splitting FALLBACK, so the `IFS` *parameter* itself read EMPTY: `$IFS`
  expanded to nothing, `declare -p IFS` reported "not found", and `${IFS+set}`
  was empty.
  - **Broke the ubiquitous save/restore idiom.** `OLD=$IFS; IFS=,; ...;
    IFS=$OLD` saved an empty string and then restored `IFS` to EMPTY — which
    means "no splitting" — silently corrupting all later word-splitting.
  - **Fix (`psh/core/state.py`).** Seed `IFS` to the default
    `<space><tab><newline>` as a real shell variable at `ShellState` init, in
    one chokepoint: after the environment-import loop and after the export
    observer is wired. Seeding with no explicit attributes means an inherited
    exported `IFS` keeps its EXPORT attribute (`declare -x`) with its value
    reset to the default, while a non-inherited `IFS` is a plain variable
    (`declare --`) — both matching bash 5.2, which resets `IFS`'s VALUE at
    startup regardless of the inherited value. The `set_variable` observer
    re-syncs the export. `unset IFS` still falls back to default whitespace
    splitting (unchanged `get_variable` default).
  - **Deliberate remaining divergence (pre-existing, not H3):** `declare -p`
    still renders control-char values (tab/newline) with double quotes and
    literal bytes where bash uses ANSI-C `$'...'` quoting; the value itself is
    correct. Left for a separate finding.
  - **Tests.** `tests/unit/core/test_ifs_seed.py` (seeded value, not exported,
    `+set`, length, `declare -p` prefix, save/restore round-trip, unset/empty
    splitting, exported-env value-reset-but-export-kept); six new IFS golden
    cases in `tests/behavioral/golden_cases.yaml` verified with `--compare-bash`.

## 0.582.0 (2026-07-03) - Fix: pipeline-tail `[[ ]]` crash + prefix-names expansion formatter corruption (appraisal #16 H2 + H4)
- FIX (HIGH). Reappraisal #16 cluster H2 + H4 — two file-disjoint AST-node
  defects fixed together.
  - **H2 (`psh/ast_nodes/tests.py`): pipeline-tail enhanced-test crash.**
    `EnhancedTestStatement` was the ONLY compound-command AST subclass missing
    the `background` field that the pipeline executor reads off the last
    command in a pipeline. A `[[ ]]` test as the TAIL of a pipeline
    (`true | [[ -n y ]]`) therefore crashed with an internal `AttributeError`
    instead of running. Added the `background: bool = False` field so the
    enhanced-test statement matches every other compound command; the test's
    truth value now becomes the pipeline status, matching bash
    (`true | [[ -n y ]]; echo rc=$?` → `rc=0`).
  - **H4 (`psh/ast_nodes/words.py`): prefix-names expansion formatter
    corruption.** `ParameterExpansion.__str__` rendered the two-part
    prefix-names operator (`${!prefix@}` / `${!prefix*}`) as a pure SUFFIX
    (`${prefix!@}`) instead of a leading-bang PREFIX. The bang landing after
    the name is a different, broken construct, so the prefix-names expansion
    was silently corrupted through both `--format` and `declare -f`; a function
    using `${!ab_@}` round-tripped through `declare -f`/`eval` into a
    `bad substitution` error. Fixed the rendering to emit the bang as a prefix
    (`${!prefix@}` / `${!prefix*}`) while leaving every other expansion form
    intact.
  - **Tests.** New unit pins for the AST repr/formatter of both prefix-names
    forms (`tests/unit/parser/test_expansion_ast_nodes.py`), a `declare -f`
    round-trip pin (`tests/integration/functions/test_declare_f_roundtrip.py`),
    pipeline-tail enhanced-test coverage
    (`tests/integration/pipeline/test_pipeline_execution.py`), and three
    bash-compared golden cases (`enhanced_test_pipeline_tail`,
    `prefix_names_declare_f_roundtrip`, `prefix_names_both_forms`).

## 0.581.0 (2026-07-03) - Fix: builtin output no longer misrouted when a dup source fd is reassigned (appraisal #16 H1 + exec-close sibling)
- FIX (HIGH). Reappraisal #16 cluster H1 — a live REGRESSION introduced by the
  v0.576 Cluster-C commit. A builtin doing `1>&2` or `2>&1` aliased the
  `sys.stdout`/`sys.stderr` STREAM OBJECT (still backed by real fd 2), so a
  later `2>file` (`os.dup2(file, 2)`) clobbered the backing out from under it
  and the builtin's own output followed fd 2 into the file. `echo hi 1>&2 2>err`
  put "hi" INTO `err` (bash: to the terminal's stderr), and the documented swap
  idiom `echo hi 3>&1 1>&2 2>&3 3>&-` on a bare builtin went to stdout not stderr.
  bash makes fd n a snapshot of m's CURRENT target, so a later reassignment of m
  leaves n alone.
  - **Fix (`psh/io_redirect/manager.py`).** Fold `1>&2`/`2>&1` into the same
    snapshot path the `m>=3` dups already used — an fd-level dup (independent
    duplicate of m's target, inherited by children) plus a stream bound to
    `os.dup(m)` (a fresh snapshot of m's open file description), never an alias
    of the stream object. The C-cluster's own pin (`echo out 2>&1 1>/dev/null`)
    exercised only a stdout write, so it never caught this; the new pins vary
    which fd the command writes to, including a builtin writing to BOTH streams
    (`type name nosuch 2>&1 1>/dev/null`).
  - **Executor sibling (exec-close).** After `exec 1>&-`, `echo X 2>g` leaked
    stdout into `g` with rc 0 (bash: write error, rc 1). Python's `open()` takes
    the lowest free fd, so `2>g` reallocated the freed fd 1 and the stale
    `sys.stdout` wrapper (still naming fd 1) wrote there; the frame's backup
    `os.dup(2)` likewise squatted fd 1. Fix: open a builtin's output target off
    fds 0/1/2 (`F_DUPFD >= 3`, as bash does) and force the frame backup onto a
    high fd (`F_DUPFD >= 10`, like `FileRedirector._save_fd_high`). fd 1 now
    stays closed, so the write fails EBADF and the diagnostic follows fd 2 into
    `g` — while a redirect that legitimately REOPENS fd 1 (`echo a > f`,
    `{ echo a; } &> f`) still lands its output. This makes the documented
    fd-swap-chain claim at `docs/user_guide/09_io_redirection.md` true.
  - **Verification.** Truth table (bash 5.2 vs psh) covers all H1 probes, the
    swap idiom, the exec-`1>&-` sibling, and the must-stay-correct regressions
    (`> f 2>&1`, `2>&1 > f`, `command ls >/dev/null`, eval-pipe-to-file,
    builtin-in-pipeline, fd>=3 no-leak, external `ls 1>&2 2>err`); all match
    modulo psh's write-error message never carrying bash's `bash: line N:`
    prefix. New `tests/integration/redirection/test_builtin_dup_source_reassigned.py`
    (serial subprocess), 5 golden cases (`--compare-bash`), and one pre-existing
    arithmetic-fd test rewritten from `capsys` (a sys-level capturer that cannot
    observe fd-level output) to a subprocess.

## 0.580.0 (2026-07-03) - Test: tighten conformance meta-test + clear no-op debt; completes Tier-1 campaign (appraisal #15 Tier 1, Cluster M)
- TEST-INFRASTRUCTURE (Cluster M). Completes the reappraisal #15 Tier-1 fix
  campaign (releases v0.560–v0.580).
- **M1 — conformance-claims meta-test hardened.** Replaced the substring matcher
  in `tests/conformance/test_claims_have_tests.py` with an AST-based one that
  only counts a user-guide "Full support" claim as proven when its mapped test
  genuinely asserts about the feature. All 34 prior markers were vacuous —
  class-name or assert-free substring matches that proved nothing. Re-pointed
  every one of the 37 `CLAIM_TESTS` mappings at a test that actually exercises
  the claim, and wrote new bash-verified conformance tests for constructs that
  had no real coverage: `disown`, `set -x`/`set -v` (xtrace/verbose), subshell
  isolation, and the `pushd`/`popd`/`dirs` directory stack. Broadened the Notes
  matcher to accept the `Full support (incl. ...)` form.
- **M2 — no-op test debt cleared.** Implemented 16 placeholder tests as genuine
  pins and deleted 14 dead stubs across the unit and integration trees; zero
  pure placeholder tests remain.

## 0.579.0 (2026-07-02) - Fix: run EXIT trap on untrapped fatal-signal death (appraisal #15 Tier 1, Cluster F3)
- FIX (HIGH). Reappraisal #15 cluster F3. A non-interactive psh dying from an
  untrapped fatal signal (SIGTERM/SIGHUP/SIGINT/SIGQUIT) now runs its EXIT trap
  before dying, then restores the default disposition and re-raises the signal
  so the parent sees a true 128+N wait status — matching bash. Previously psh
  died silently at rc=143 (etc.) without running the trap.
  - **Routed through the existing idempotent EXIT-trap chokepoint.** The
    signal-death path now reuses `TrapManager.execute_exit_trap()` — the same
    firing `SourceProcessor.execute_as_main` uses on the EOF / `set -e` / `exit`
    paths — so the trap fires exactly once with no duplicated logic. Buffered
    stdout/stderr are flushed before the `os.kill` re-raise (which bypasses
    CPython's atexit flush and would otherwise drop the trap's output).
  - **Non-interactive disposition matches bash.** SIGQUIT is ignored (bash's
    default disposition for a non-interactive shell); INT/TERM/HUP terminate and
    fire the EXIT trap. The interactive REPL keeps its own fatal-signal behavior.
  - **Signal death always wins over the EXIT trap body.** A follow-up ensures
    that when the EXIT trap itself calls `exit N`, the escaping `SystemExit` (or
    any other exception from the body) is swallowed so it can no longer bypass
    the restore-default + re-raise — the parent still sees the 128+N signal
    death, as in bash. The trap still fires exactly once (idempotency flag is
    set before the body runs).
  - Covers script, `-c`, and piped-stdin modes; substitution/subshell children
    continue to fire their own EXIT traps.
  - **Deliberate remaining divergences (all pre-existing / out of scope):**
    (a) a signal-trap whose body calls `exit` does not additionally fire the
    EXIT trap (bash runs both); (b) untrapped SIGUSR1/USR2 do not fire the EXIT
    trap (psh installs non-interactive handlers only for INT/TERM/HUP/QUIT);
    (c) SIGINT delivered while a foreground external command runs is not masked
    by psh as bash masks it (a deeper pre-existing job-control item).

## 0.578.0 (2026-07-02) - Fix: formatter round-trip cluster J — time, heredoc trailers, arrays, [[ ]] parens, for-no-in, $'..' in assignment (appraisal #15 Tier 1, Cluster J)
- FIX (HIGH). Reappraisal #15 cluster J closes six ways `--format` silently
  emitted a DIFFERENT program. All now round-trip (verified vs bash 5.2 over a
  truth table + corpus: `--format` succeeds, output reparses, formatting is
  idempotent, and original/formatted scripts produce identical stdout/stderr/rc).
  - **J1 `time`/`time -p` dropped.** `visit_Pipeline` never read
    `Pipeline.timed`/`time_posix`, and `--format -c time` crashed (IndexError on
    the empty timed pipeline). Emit the `time [-p]` prefix (bash order
    `[time [-p]] [!]`), handle the empty-commands case, and surface the fields in
    the debug AST visitor.
  - **J2 heredoc trailers misplaced/dropped.** The five scattered trailer
    rendering sites are consolidated into ONE seam: a command REGISTERS its
    heredoc body+delimiter (`_register_heredocs`) and the physical-line boundary
    FLUSHES them (`_flush_line`). Fixes `cat <<EOF && echo x` (was `EOF && echo x`
    on the delimiter line), if/while conditions (was `EOF; then`), and heredocs on
    `[[ ]]`/`(( ))` (were dropped — now route through the shared
    `_append_redirects`). The v0.547 pipeline cases stay fixed.
  - **J3 array assignments corrupted values.** `visit_ArrayInitialization`/
    `visit_ArrayElementAssignment` re-wrapped flat element strings in the legacy
    quote sidecar. Render from the Word layer via `_format_word`, so `a=($'x\ty')`,
    `a[3]=$'x\ty'`, `a=("x\"y")`, and `m=([k]="v 1")` round-trip; argument-position
    `declare -A m=(...)` renders from its array_init element Words too.
  - **J4 `[[ ]]` grouping parens never re-emitted.** `[[ ( a || b ) && c ]]`
    flattened to `[[ a || b && c ]]`, flipping the rc. Parenthesize a compound
    operand whose operator binds looser than the context.
  - **J5 `for x; do`/`select x; do` implicit list rendered UNQUOTED** (`in $@`),
    changing word splitting. Render the item Words the parser already stores (the
    implicit `"$@"`), preserving quoting.
  - **J6 (lexer root) `$'...'` lost quote context in assignment/concatenation.**
    The literal recognizer decoded it inline into a flat, quote-less WORD, so
    `v=$'l1\nl2'` formatted to a value that re-ran `l2` as a command. Removing the
    inline ANSI-C special case lets `$'...'` end the literal like any quote — it
    lexes as its own `$'`-typed STRING token and the parser re-joins adjacent
    tokens into one composite Word (mirroring `"..."`). Runtime value is unchanged;
    only the lost metadata is restored. Bonus: a quote in an assignment NAME
    (`v$'a'=x`) now correctly makes the word a command, not an assignment.
  - Probes pinned in `tests/behavioral/golden_cases.yaml` (`--compare-bash`
    clean); the lexer-stream corpus rows affected by J6 were re-verified against
    bash and regenerated. Deliberate remaining divergences (Tier 2 parser
    findings): `! time cmd` is a psh parse error, and sole-statement
    `time <compound>` drops timing at runtime — the formatter round-trips whatever
    AST it is given.

## 0.577.0 (2026-07-02) - Fix: flat-string AST sweep — case subject, [[ ]] unary operand, here-string carry Words (appraisal #15 Tier 1, Cluster G1)
- FIX (HIGH). Reappraisal #15 cluster G1 retires the flat-string-AST defect
  family: three sites that flattened a parsed Word into a string and then
  re-expanded (or corrupted) the quoted text are migrated to the Word layer in
  one sweep, so per-part quote context survives and each site matches bash 5.2.
  - **case SUBJECT.** `CaseConditional` gained `subject_word`; the executor
    expands it via the new `ExpansionManager.expand_word_as_subject`
    (tilde-leading + parameter/command/arithmetic + quote removal, NO
    splitting/globbing — the new `CASE_SUBJECT` policy). `case '$x' in` now
    stays literal, `case '$(cmd)' in` no longer EXECUTES the single-quoted
    command substitution, composites (`case "$x"y`) stop corrupting, and
    backtick/tilde subjects expand. `expr` is retained as display text for the
    analysis/debug visitors and manual-AST fallback.
  - **`[[ ]]` UNARY operand.** `UnaryTestExpression` gained `operand_word`,
    routed through the same quote-aware path binary operands use, so
    `x=; [[ -n '$x' ]]` now tests the literal `$x` (true) instead of the
    re-expanded empty value. `operand` becomes a derived read-only property;
    the dead `_expand_operand` flatten path is removed.
  - **HERE-STRING target.** The redirect now carries a Word (mirroring
    filename targets) and `redirect_herestring` expands it via
    `expand_assignment_value_word` (all expansions, value-tilde, quote removal,
    NO split/glob), so `cat <<< foo$v"dq"` honors the quote boundary and
    `<<< a\ b` drops the backslash. The legacy flat-string path stays as the
    no-Word fallback.
  - Both parsers (recursive-descent and combinator) updated; the formatter
    renders the case-subject and unary-operand from the Words, fixing their
    `--format` round-trip breaks (`[[ -z "" ]]`, empty/semicolon case subjects,
    composite here-strings). Headline probes pinned in
    `tests/behavioral/golden_cases.yaml` (verified with `--compare-bash`); the
    two documented combinator composite-word parity gaps are unchanged.

## 0.576.0 (2026-07-02) - Fix: redirect visibility on in-process builtins + redirect-failure on compounds (appraisal #15 Tier 1, Cluster C)
- FIX (HIGH). Reappraisal #15 cluster C — three related redirect defects,
  fixed as one family so every redirect-visibility and redirect-failure site
  behaves like bash 5.2.
  - **C1 — redirections on in-process builtins were invisible to the children
    they spawn.** A `> file` / `2> file` / `2>&1` on `eval`/`source`/`command`
    was applied as a Python-stream swap ONLY, so a child the builtin spawned
    (an external command, a pipeline, a sourced file's commands) inherited the
    shell's real fd 1/2 and leaked. stdin already got the fd-level treatment
    for exactly this; fd 1/2 now do too — a per-command `dup2` that shares the
    opened file's open description (no re-truncation) and is saved/restored on
    the builtin frame. New `IOManager._dup_output_fd_for_children`, wired into
    `_builtin_redirect_output_file`, `_builtin_redirect_combined`, and
    `_builtin_redirect_dup`. `command ls / > /dev/null` is now silent,
    `eval "cmd | cmd" > f` fills `f`, and `source f 2>/dev/null` matches bash.
  - **C2 — `command`/`builtin` inner invocations now route through
    `execute_builtin_guarded`** (uniform broken-pipe/OSError/defect handling)
    instead of a raw `.execute()`; the C1 fd-level fix already cures the
    observable `command EXT > f` symptom (the outer builtin's redirect now
    reaches the forked external rather than being dropped).
  - **C3 — a redirect-setup failure on any of the 9 in-process COMPOUND
    commands** (`{ }`, `if`, `for`, `while`, `until`, `case`, `select`,
    `[[ ]]`, `(( ))`) raised an uncaught `OSError` that reached the generic
    "unexpected error" handler, so `|| fallback` was skipped. One new
    chokepoint `IOManager.guarded_redirections` prints bash's diagnostic, does
    not run the body, and returns 1 (so `|| fallback` runs and `set -e` still
    aborts). The `OSError` message shape is now unified across the simple-,
    compound-, forked-subshell and function-call redirect-failure sites via a
    shared `format_redirect_error` (`psh: TARGET: STRERROR`). Also fixes a raw
    `os.dup` in the combined `&>` save path (`exec 1>&-; { echo a; } &> f` used
    to crash `EBADF`; the fd-2 backup now dups to a high fd so the redirect's
    own low-fd open cannot clobber it).
  - Verified with a 29/29 bash-parity truth table across every C1 reproducer,
    each compound type with a bad target under `|| fallback` / if-conditions /
    `set -e` / `exec 1>&-`, and the simple-command / function / subshell paths.
    Regression tests in `tests/integration/redirection/` and 11 golden cases
    in `tests/behavioral/golden_cases.yaml` (verified via `--compare-bash`).
  - Known follow-ups (deliberate, out of scope here): three simple-command
    redirect-failure sub-paths still emit the older raw message shape; and a
    separate pre-existing external-command redirect-after-closed-fd bug.

## 0.575.0 (2026-07-02) - Fix: unset follows bash dynamic-scope value-stack semantics (appraisal #15 Tier 1, Cluster D1)
- FIX (HIGH). Reappraisal #15 cluster D1 — `unset` did not honor bash's
  per-name dynamic-scope value stack. `unset_variable` (`psh/core/scope.py`)
  now removes the innermost *visible* instance of a name wherever it lives, so:
  - **Unsetting a global from inside a function deletes the global** (not a
    function-local shadow), and a later assignment writes the global again —
    fixing the silent-vanish bug: `x=1; f(){ unset x; x=new; }; f; echo $x`
    now prints `new` (previously the value vanished).
  - **A caller's local is revealed when a deeper scope unsets the name**:
    `x=global; f(){ local x=f; g; }; g(){ unset x; echo ${x-U}; }; f` prints
    `global`, and a subsequent `x=...` in `g` writes that revealed instance.
  - A **tombstone (bash "local and unset") is planted ONLY when removing a
    local from its own declaring scope**: `f(){ local x=2; unset x; echo
    ${x-U}; }` prints `U` while the outer `x` stays intact. `unset` strips the
    local's attributes (`local -i x=5; unset x` → `declare -- x`).
  - `set_variable` binds an assignment to the innermost scope that already
    holds an instance (including a declared-unset cell), matching bash.
  - `get_declared_variable_object` returns plain tombstones so `declare -p x`
    prints `declare -- x` for a local-and-unset name.
  - The `unset` builtin (`psh/builtins/environment.py`) no longer pops
    `shell.env` directly: the scope observer re-derives the environment entry,
    so unsetting an exported local correctly *reveals* (reappears) an exported
    outer instance. The readonly-refusal message now matches bash.
  - `psh/core/CLAUDE.md` "Unset Tombstones" section rewritten (it had
    documented the old, wrong rule as if intended). 12 probes promoted to the
    `unset_*` cases in `tests/behavioral/golden_cases.yaml` (`--compare-bash`).
  - Deliberate remaining divergence: bash's no-argument `declare -p` lists
    shadowed instances at every visible scope; psh's listing stays
    shadow-resolved (a named `declare -p x` matches bash).

## 0.574.0 (2026-07-02) - Fix: bash-valid function names + break/continue/return de-keyworded (appraisal #15 Tier 1, Cluster D2)
- FIX (HIGH). Reappraisal #15 cluster D2 — function-name policy and the
  break/continue/return keyword split. Two parts:
  - **Function names.** `FunctionManager.RESERVED_WORDS` wrongly rejected the
    builtins `true`/`false`/`exit`/`return`/`break`/`continue`, and
    `_is_invalid_name` demanded identifier characters. bash accepts all of
    `my-func`, `.dot`, `f.g`, `1fn`, `a@b`, `[`, and lets a function shadow a
    builtin (even a POSIX special one) in default-mode lookup. `FunctionManager`
    now accepts any non-empty single word; reserved words still fail at
    **parse** time (`rc=2`, like bash) because keyword tokens never match the
    name rule. Command lookup order is now functions > special-builtins >
    builtins > external (bash default mode); `command`/`builtin` still bypass
    functions, and `exec`'s dispatch defers to a user `exec()` function. A
    rejected name now surfaces as a proper `FunctionDefinitionError` (reported,
    execution continues) instead of aborting the whole input as an
    "psh: unexpected error:".
  - **break/continue/return de-keyworded** (the principled fix; collapses the
    parser's two-path statement split). Removed from the lexer `KEYWORDS` /
    `KEYWORD_TYPE_MAP`; the `BREAK`/`CONTINUE`/`RETURN` token types are gone and
    they lex as plain WORDs. New `psh/builtins/loop_control.py` provides
    `BreakBuiltin`/`ContinueBuiltin` (POSIX special builtins) that carry the
    bash-matched diagnostics and raise `LoopBreak`/`LoopContinue`; `return`
    likewise raises `FunctionReturn`. Consequences (all bash-verified):
    `break()`/`return()` are definable, redirects on `break` are honored
    (`break 2>/dev/null`), and `break | cat` / `break && echo` compose like
    ordinary commands. `while break; do …` now exits the loop `rc=0`. The
    break/continue level matrix and cross-fn/pipeline scoping are intact.
  - **Follow-up:** backgrounded `break`/`continue`/`return` no longer leak an
    empty `psh: error:` line — the escape is swallowed at the ProcessLauncher
    child chokepoint — and stale `BreakStatement`/`ContinueStatement` doc
    references were refreshed.
  - Deliberate remaining divergences: `a+b(){ :; }` is still a parse error (a
    pre-existing lexer quirk that splits `a+` looking for `a+=`), and
    `{ break; } | cat` inside a loop stays silent where bash prints a warning
    (the bare `break | cat` form matches bash). Known follow-up (not this
    release): the combinator parser and `--validate` still reject digit-first
    function names (RD/combinator parity gap).
  - Truth table (`tmp/truth_d2.py`): 100/101 cases match bash 5.2 across `-c`,
    stdin, and script-file modes.

## 0.573.0 (2026-07-02) - Fix: line-continuation preprocessing is comment- and heredoc-aware (appraisal #15 Tier 1, Cluster A5)
- FIX (HIGH). Reappraisal #15 cluster A5 — `process_line_continuations` in
  `psh/scripting/input_preprocessing.py` (the pre-lexer stage every input mode
  shares: script files, `-c` strings, slurped stdin, `run_command`, interactive)
  joined backslash-newline with only single/double-quote tracking, so:
  - (a) a comment ending in a backslash silently swallowed the next command line
    (`# c \` followed by `echo survived` printed nothing);
  - (b) a QUOTED heredoc body lost literal trailing backslashes (`<<'EOF'` /
    `<<"EOF"` / `<<\EOF` / `<<-'EOF'` with body `a\` + `b` printed `ab`,
    corrupting embedded sed/awk/usage text);
  - (c) an apostrophe in a comment or heredoc body poisoned the carried quote
    state, suppressing later legitimate joins.
- Rewritten as a line-based state machine aware of the three contexts: comments
  (the newline ends the comment, never a continuation — comment position shared
  with the lexer's `is_comment_start`, plus a raw-text `${#...}` guard), heredoc
  bodies (quoted delimiter = verbatim; unquoted still joins, fusing even a
  next-line terminator, exactly like bash), and carried quote state computed
  from command text only.
- Shared helpers `scan_line_heredoc_markers` / `eol_backslash_is_literal` live in
  `psh/utils/heredoc_detection.py` and are reused by `open_heredoc_delimiters`,
  so a heredoc marker inside a comment (`echo hi # <<EOF`) no longer registers a
  phantom heredoc that swallowed the rest of the input.
- Follow-up: `_quote_flags` is now backtick-aware. bash does NOT honor `#` (or a
  single quote) inside an unclosed `` `...` `` during the continuation-join
  decision, so `` echo `echo a # c \ `` / `echo b\`` now splices to bash's `a`
  (was `a b`); `$( )` is deliberately left honoring an interior comment (bash
  does too). Matches bash 5.2 across script, `-c`, and stdin modes.
- Deliberate remaining divergences (pre-existing on main, out of A5 scope,
  unchanged): an unterminated heredoc at EOF (bash executes body-to-EOF with a
  warning; psh drops the command per the existing accumulator EOF policy), and a
  lone trailing backslash at script/stdin EOF (bash drops it; psh keeps it —
  known LOW divergence).
- Tests: unit pins on the function and the shared marker scan, integration
  parity across script/`-c`/stdin, and 10 promoted golden cases in
  `tests/behavioral/golden_cases.yaml` (verified with `--compare-bash`).

## 0.572.0 (2026-07-02) - Fix: command substitution resets `set -e` like bash; `inherit_errexit` shopt added (appraisal #15 Tier 1, Cluster F1)
- FIX (HIGH). Reappraisal #15 cluster F1 — command-substitution children now
  clear `set -e` the way bash does, while `( )` subshells and process
  substitutions keep inheriting it.
- `$( )` and backtick children no longer abort on the first failing command:
  `set -e; x=$(false; echo hi)` now captures `hi` and continues (was: aborted
  before `echo`). The child's `$-` also drops `e` inside the substitution,
  matching bash.
- `shopt -s inherit_errexit` (and POSIX mode, `set -o posix`) restores
  inheritance so the substitution child aborts on the first failure, exactly as
  bash does. `inherit_errexit` is now a registered SHOPT-category option.
- The errexit-*suppressed* state of the forking context (an `if`/`while`
  condition, a non-final `&&`/`||` member, a `!`-negated command) still crosses
  the fork into the substitution child, matching bash's memory-copy semantics —
  which also repaired the identical divergence for process substitutions
  (`if cat <(false; echo hi); then …`).
- The substitution's exit *status* still drives the parent's errexit: `set -e;
  x=$(false)` alone aborts, and `exit 5` in the body propagates as rc=5.
- One chokepoint: `run_child_shell()` in `child_policy.py` gained a
  `reset_errexit` knob and now seeds `_errexit_suppress_seed` the way
  `SubshellExecutor` already did; `command_sub.py` opts in, subshells/procsubs
  do not.
- Tests: new live-bash conformance matrix in
  `tests/conformance/bash/test_cmdsub_errexit_conformance.py`; 10 golden cases
  promoted to `tests/behavioral/golden_cases.yaml` (verified with
  `--compare-bash`, 91/91 probes match bash 5.2); registry drift-locks and user
  guide ch17 (strict-mode note + shopt lists) updated. No deliberate divergences
  remain in this area.

## 0.571.0 (2026-07-02) - Fix: combinator parser parity — `time` keyword, live heredocs, and-or backgrounding (appraisal #15 Tier 1, Cluster L)
- FIX (HIGH). Reappraisal #15 cluster L — the educational combinator parser
  regained parity with the recursive-descent (RD) parser on three fronts.
- L1: the `time [-p]` pipeline prefix (added to RD in v0.558) never reached the
  combinator, so `--parser combinator -c 'time echo hi'` was a hard rc=2 parse
  error. The pipeline parser now mirrors the RD grammar: `time [-p]` precedes
  `!`, times the whole pipeline, and bare `time` is a complete empty timed
  pipeline.
- L2: heredoc bodies now flow through the combinator instead of being
  structurally dropped and silently masked. (a) The redirection builder carries
  `heredoc_key`/`heredoc_quoted` and consumes composite delimiters (`<<E"O"F`),
  mirroring RD's `_parse_heredoc`. (b) `HeredocProcessor` understands the
  lexer's live `{'content','quoted'}` heredoc map entries and populates every
  node's redirects at ONE chokepoint in `_traverse_node`, fixing compound
  trailing heredocs like `done <<EOF` that the per-node handling missed.
  (c) `source_processor` no longer silently falls back to the RD parser for
  heredoc input under `--parser combinator`; `parse_with_heredocs` takes the
  ACTIVE parser and dispatches honestly.
- L3: a trailing `&` backgrounded only the last pipeline (`a && b &` ran `a` in
  the FOREGROUND). The `&` is consumed at the and-or list level with the RD
  parser's `_apply_background` semantics, so `a && b &` backgrounds the whole
  list and junk sequences `& |`, `& &&`, `& ;` are rejected (bash rc=2).
- Stretch goals (each verified against a bash truth table): function
  definitions accept any compound body (`f() if ...`, `f() (sub)`, `f() for ...`,
  `f() ((...))`); unclosed expansions (`echo ${`, `$(`, backtick, `$((`, `<(`)
  are syntax errors at word-consumption time (were accepted as literal words;
  the backtick form hit a swallowed `RecursionError`); `UntilLoop` added to both
  compound-unwrap `isinstance` tuples for consistency.
- Deliberate divergences: `echo x | time cat` and `f() (echo s) &` stay rc=2 —
  the RD parser diverges from bash identically on both (documented RD MED
  follow-ups: `time` in a pipeline tail; function-definition composability), and
  the combinator now matches RD there. Truth table: 59/61 three-way cases match
  bash, the 2 remaining being those two RD-parity bars.

## 0.570.0 (2026-07-02) - Fix: unclosed `$((` falls back to command substitution with a subshell (appraisal #15 Tier 1, Cluster A4)
- FIX (HIGH). Reappraisal #15 cluster A4 — `$((` that never closes with `))`
  now re-reads as a `$(` command substitution whose body starts with a
  subshell, per the POSIX/bash disambiguation rule. `echo $((echo a); echo b)`
  prints `a b` (was rc=2 "unclosed arithmetic expansion"; the double-quoted
  form `"$((echo a); echo b)"` even reported an unclosed quote). `$(( is an
  arithmetic expansion only when the paren group opened by its second `(`
  closes with another `)` immediately following; psh had committed greedily to
  arithmetic.
- Core: new three-way scanner `scan_double_paren_arithmetic`
  (CLOSED / NOT_ARITHMETIC / UNCLOSED) in `psh/lexer/pure_helpers.py`,
  replacing a scan that let paren depth go negative (so
  `$((echo a) + (echo b))` was misread as arithmetic and could match a later
  `))`). Every extent-scanning sibling was updated to the corrected rule: the
  lexer expansion parser chokepoint (`_parse_arithmetic_expansion` ->
  cmdsub, covering unquoted and double-quoted words), both cmdsub-scanner
  branch pairs via a new shared `_skip_dollar_paren` helper,
  `validate_brace_expansion`, and `skip_expansion_region`.
- Input ending exactly at the inner group's `)` stays UNCLOSED so the next
  character decides — preserving incomplete-input gathering for multi-line
  `$(( 1 +\n2 ))` while making multi-line `$((echo a)\n)` resolve to a command
  substitution like bash. True arithmetic with balanced `))` is unchanged
  (`$((1+2))`, `$((ls))`, `$( (echo x) )`, `(( ))` command, nested `$(($((1+1)))
  + 1)`).
- Truth-table pinned: 55 paired probes vs bash 5.2 across `-c`, script, and
  stdin all match. Tests: unit (three-way scan + token classification +
  at-eof), integration (execution incl. combinator parser, quoting,
  assignment, subscript, multi-line stdin), a conformance suite, and 9 golden
  cases. Two deliberate divergences remain (both marked KNOWN): a
  case-pattern-inside-`$(( ))` corner where psh is more permissive than bash's
  fallback re-read (bash accepts the identical body standalone), and the
  `((`-command-vs-nested-subshell parser gap that already fails identically on
  the standalone form.

## 0.569.0 (2026-07-02) - Fix: `&` and `|&` set command position (appraisal #15 Tier 1, Cluster A2)
- FIX (HIGH). Reappraisal #15 cluster A2 — reserved words, `[[`, and `!` lost
  command position after `&`: `true & if true; then echo B; fi` was a syntax
  error (rc=2) where bash runs it, and likewise after `|&`. Added `AMPERSAND`
  and the sibling-defect `PIPE_AND` to the shared `STATEMENT_SEPARATORS` set
  consumed by both broken command-position machines — the lexer pass and the
  keyword normalizer (the cmdsub scanner already treated `&` as a separator);
  the transition tables in `docs/architecture/command_position.md` were
  updated to match.
- Composed with the v0.560.0 statement-boundary guard this also unlocks `&`
  directly before a closing construct keyword: `{ echo a & }`,
  `if ...; then cmd & fi`, `while ...; do cmd & done`, and
  `case x in x) cmd & esac` now all parse and background the command.
- Verified against bash probes; pinned by a lexer unit suite
  (`tests/unit/lexer/test_command_position_after_amp.py`), an integration
  suite (`tests/integration/parsing/test_amp_command_position.py`), and 9
  golden cases (including `true & echo if`, where `if` stays an argument).

## 0.568.0 (2026-07-02) - Fix: trap accepts POSIX numeric forms and every platform signal name (appraisal #15 Tier 1, Cluster F2)
- FIX (HIGH). Reappraisal #15 cluster F2 — `trap` signal-spec parsing now
  routes through `psh/utils/signal_utils` (the same tables `trap -l`/`kill -l`
  list) as the single source of truth, replacing TrapManager's 13-name
  whitelist. Verified against bash 5.2 probes; new conformance suite in
  `tests/conformance/bash/test_trap_signal_spec_conformance.py` plus
  golden-case pins.
  - `trap 'cmd' 0` (the POSIX numeric EXIT form) sets the EXIT trap; every
    platform signal works by name (WINCH, SEGV, VTALRM, KILL, ...) or number,
    case-insensitively, with the `SIG` prefix optional (`sigusr1`, `Usr1`,
    `10` all canonicalize to `USR1`), so a trap set under any spelling is
    found by the name-keyed dispatch in SignalManager.
  - Reset forms parse like bash: a first operand that is an unsigned decimal
    naming a valid signal makes ALL operands conditions to reset
    (`trap 2 15`, `trap 0` — POSIX), and a single signal-name operand resets
    too (`trap USR1`); previously these were rejected or mis-read as actions.
  - `set_trap` continues past an invalid spec like bash — it reports each bad
    spec on stderr and returns 1, but still processes the remaining signals
    (previously it aborted the whole command at the first bad spec).
  - `trap -p BOGUS` reports `invalid signal specification` with rc=1 instead
    of silently printing nothing with rc=0, and `trap -p -- INT` consumes the
    leading `--` like the set form (regression-fixed on-branch);
    `show_traps` now returns `(display, invalid_specs)` so the builtin does
    the stderr reporting.
  - Bare `trap`/`trap -p` listing uses bash's numeric order (EXIT first, then
    signals by number, then DEBUG/ERR) directly from storage; numerically-set
    traps display canonically (`trap ... 15` prints `SIGTERM`).
  - `exit N` inside a substitution child's EXIT trap now sets the child's
    exit status (bash semantics) instead of unwinding past the trap runner
    (builds on v0.561.0's substitution-children-fire-EXIT-traps model).
  - Deliberate divergence kept: RETURN traps remain unimplemented, so
    `trap 'cmd' RETURN` is still rejected as an invalid spec.

## 0.567.0 (2026-07-02) - Fix: evaluation engines — [[ ]] arithmetic operands, bracket-pattern crashes, integer division, fatal subscripts (appraisal #15 Tier 1, Cluster H)
- FIX (HIGH). Reappraisal #15 cluster H — four bash-5.2-pinned fixes to the
  evaluation engines, verified by a 94-case bash-vs-psh truth table
  (18/70 matched at baseline, 93/94 after).
  - H1: `[[ ]]` numeric operators (`-eq` etc.) now ARITHMETIC-EVALUATE their
    operands through the real engine: `[[ 1+1 -eq 2 ]]`, recursive name
    resolution (`x=y; y=5; [[ x -eq 5 ]]`), base/hex literals (`2#101`,
    `0x10`), array elements (`a[0]`), and assignment side effects all work.
    Uses a new `expand=False` mode of `evaluate_arithmetic` so
    already-expanded text is not rescanned (a literal `$` stays a syntax
    error, as in bash). Evaluation failures (`[[ 08 -eq 8 ]]`) print the
    arithmetic error and fail with status 1 (previously status 2 as
    "integer expression expected"). The `test`/`[` builtin is deliberately
    unchanged — bash does not evaluate arithmetic there.
  - H2: invalid bracket patterns (`[z-a]`, `[a\]b]`, `[\x]`) no longer crash
    as internal defects (uncaught `re.error`) — they quietly match/not-match
    like bash across `[[ ]]`, `case`, `${v#pat}`, `${v/pat}`, and globs. The
    two duplicated bracket scanners are consolidated (`_bracket_end` +
    shared `_bracket_to_regex`); a set that cannot compile matches NOTHING,
    or negated (`[!z-a]`) matches ANY one char (both probed in bash 5.2),
    with `shell_pattern_to_regex` validating its final regex as the
    last-resort chokepoint.
  - H3: arithmetic `/` and `%` use exact integer math with C
    truncate-toward-zero semantics (new `_trunc_div` replaces
    `int(left/right)`, which lost precision beyond 2**53 —
    `$((9223372036854775807/3))` was off by 170). Identical across `$(( ))`,
    `(( ))`, `let`, and `declare -i`.
  - MED: bad array subscripts are FATAL like bash instead of silently
    corrupting index 0 — `a[08]=Q` used to OVERWRITE `a[0]`; now it prints
    "value too great for base" and aborts the command (read, write, and
    init-list paths all raise `ExpansionError`). Associative arrays still
    take the literal key; an evaluable unset-name subscript still addresses
    index 0 (`a[junk]`).
  - Deliberate remaining divergence: `[[ a[08] -eq 7 ]]` fails with status 1
    but does not abort the script (bash aborts); distinguishing it needs
    subscript context inside the arithmetic tokenizer.
  - Tests: `tests/unit/expansion/test_arithmetic_division_semantics.py`,
    `tests/unit/expansion/test_bracket_pattern_edge_cases.py`,
    `tests/integration/test_enhanced_test_arith_operands.py`; the old
    `test_array_index_arith_errors.py` pinned the broken index-0 fallback
    and was rewritten with bash-verified pins; 13 golden bash-compare cases
    in `tests/behavioral/golden_cases.yaml`.

## 0.566.0 (2026-07-02) - Fix: read gives the last variable the raw remainder (appraisal #15 Tier 1, B4)
- FIX (HIGH). Reappraisal #15 cluster B4 — with more fields than variables,
  `read` re-joined the leftover fields with IFS[0], collapsing interior
  whitespace runs (`read x y` on `  a  b  c ` gave y=`b c` instead of
  `b  c`) and dropping repeated non-whitespace delimiters (`IFS=: read a b`
  on `x:y::` gave b=`y:` instead of `y::`).
  - Now the last variable receives the raw remainder of the line per bash
    read.def (`get_word_from_string`) semantics: interior delimiters and
    spacing verbatim, trailing unprotected IFS whitespace stripped — EXCEPT
    when extracting one more word plus its delimiter would consume the
    remainder entirely, in which case the last variable gets just that word
    (`x:y:` -> y=`y`, but `x:y::` -> y=`y::`).
  - Chokepoint fix: `_split_with_ifs` grows a `max_fields` parameter and
    `_assign_to_variables` becomes plain positional assignment. Unifying the
    single-variable path through the same splitter also fixed the latent
    single-variable analog (`IFS=: read a` on `x:` kept the trailing colon;
    bash drops it) and retired the now-unused `_trim_ifs_whitespace` helper.
    `read -a` and the `-d`/`-n`/`-N`/`-t` machinery are untouched.
  - Verified against a 39-case bash 5.2 truth table (27/39 -> 39/39, no
    deliberate divergences). Tests: 34 new unit tests
    (`tests/unit/builtins/test_read_remainder.py`) + 5 golden bash-compare
    pins in `tests/behavioral/golden_cases.yaml`.

## 0.565.0 (2026-07-01) - Fix: interactive history alias contract + lexer-driven cmdhist joining (appraisal #15 Tier 1, K1+K2)
- FIX (HIGH). Reappraisal #15 cluster K1 — up-arrow/Ctrl-R were dead for any
  session starting with an EMPTY history (every fresh install): LineEditor did
  `HistoryNavigator(history or [])`, so a falsy empty `state.history` was
  silently replaced by a private list and recall never saw a recorded command.
  The alias also broke mid-session: HistoryManager REBOUND `state.history` to
  a new list at three sites (erasedups, the HISTSIZE trim, the load-time
  trim), detaching every live navigator.
  - Fixed with an identity check (`history if history is not None else []`)
    and in-place mutation (slice assignment / `del`) at all three rebind
    sites. The "one shared list object for the whole session" contract is now
    documented on HistoryManager and enforced by object-identity pins in
    `tests/unit/interactive/test_history_alias_contract.py` plus a PTY
    end-to-end recall test with a fresh empty HOME (the old recall test was
    masked by a shared `.psh_history`).
- FIX (HIGH). Reappraisal #15 cluster K2 — the keyword-whitelist
  `convert_multiline_to_single` joiner corrupted recorded commands into parse
  errors: `until`/`select` loops recorded as `until false do break done`
  (unparseable on recall, persisted to HISTFILE), `case` emitted
  `case x in; ...;;; esac`, and function-brace bodies emitted `f() { {`.
  - Replaced with ONE lexer/parser-driven joiner (the same oracle
    CommandAccumulator uses): newlines stay verbatim inside quotes, heredocs,
    and unclosed expansions (matching bash cmdhist); backslash-newline
    continuations splice; a bare space follows tokens that reject `;`
    (`then`/`do`/`else`/`in`/`;;`/`&&`/`{`/`(`, case-pattern `)`, `f()`,
    `function NAME`, inside `name=(...)`); `; ` otherwise.
  - Recall (`HistoryNavigator._editable`) now uses the same rules — recalled
    heredoc and quoted-newline entries are no longer space-joined into
    corruption, and mixed commands match bash per-newline instead of the old
    all-or-nothing gate.
  - Pinned to interactive bash 5.2 recordings (`bash --norc -i` + `fc -ln`)
    by a 44-case truth table in `tests/unit/test_line_editor_helpers.py`
    (byte-for-byte, plus reparse-equivalence and recall-idempotence checks).
    Documented divergences: `((1 +\n2))` records as `((1 +; 2))` exactly like
    bash's own corrupted recording; bash's cosmetic space after a heredoc
    terminator and its `;; esac` re-join are not imitated (both forms reparse
    identically). Two old tests that pinned pre-fix corrupted joins were
    rewritten against bash-verified expectations.

## 0.564.0 (2026-07-01) - Fix: CLI arg parsing stops at first operand; non-seekable scripts run (appraisal #15 Tier 1, I1+I2)
- FIX (HIGH). Reappraisal #15 cluster I1 — `parse_args` stripped psh's own
  flags from ANYWHERE in argv via `args.remove`: `psh script.sh -i --norc foo`
  handed the script only `foo`; `--parser bar` as a `-c` operand killed psh
  itself with exit 2; `--debug-ast` as a script argument silently activated
  AST debugging; even `psh -- script.sh -i` lost the `-i`.
  - `parse_args` is now a single left-to-right chokepoint that stops at the
    first non-option operand, exactly like bash: flags before the operand are
    psh's own (value flags consume the next token only there), `--` or the
    historical lone `-` ends options explicitly, an unknown option in flag
    position exits 2, and the first operand plus everything after it pass
    through untouched as the script/command operands.
  - The rewrite deletes `main()`'s duplicated pre-construction mode sniffing
    and the `sys.argv` mutation hack; `--version`/`--help` exit before a Shell
    is constructed (no rc sourcing just to print a version); `psh -c` with no
    command string reports "option requires an argument" like bash; a piped
    bare `psh --` reads stdin like bash instead of starting the interactive
    loop without a tty.
- FIX (HIGH). Reappraisal #15 cluster I2 — script validation pre-read 1KB for
  a binary sniff before `FileInput` re-opened the file, consuming non-seekable
  sources: `psh <(echo cmd)`, piped `psh /dev/stdin`, `source /dev/stdin`, and
  `source <(...)` (the completion-loading idiom) all silently no-oped rc=0,
  and a FIFO script deadlocked. It also counted every byte >= 0x80 as
  non-printable, so a CJK-comment UTF-8 script was rejected as "cannot execute
  binary file" rc=126.
  - Only regular files are sniffed now (via stat, so a writer-less FIFO is
    never even opened), and binary means bash's rule exactly: a NUL byte
    before the first newline. High bytes are not binary markers. The sniff
    rewinds after reading because a macOS `/dev/fd` path opens as a dup()
    sharing the original descriptor's offset.
  - Truth table: 34/34 bash-5.2 cases match (procsub/pipe/`/dev/stdin`/fifo
    execution and sourcing, CJK, NUL binary 126, missing 127, directory 126,
    unreadable 126). Documented divergences by design: psh's option SET
    differs from bash's (`psh -c -x cmd` rejects `-x`), psh does not strip NUL
    words from executed input, and psh's `source` still applies the binary
    check.
  - Tests: `tests/system/test_cli_argument_parsing.py`,
    `tests/unit/test_main_parse_args.py`,
    `tests/system/test_script_input_sources.py`, and new cases in
    `tests/unit/scripting/test_script_validator.py`.

## 0.563.0 (2026-07-01) - Fix: declare -f via the maintained formatter; delete rotted shell_formatter (appraisal #15 Tier 1, D3)
- FIX (HIGH). Reappraisal #15 cluster D3 — `psh/utils/shell_formatter.py` was a
  rotted duplicate of the maintained `FormatterVisitor`: it crashed
  (`AttributeError`) on any function containing `case`, dropped heredoc bodies
  and definition-attached redirects, and emitted nested function definitions
  without braces — so the canonical serialization idiom
  `src=$(declare -f f); unset -f f; eval "$src"` failed for whole families of
  functions. `type f` and `command -V f` crashed the same way.
  - **Deleted the module** (and its unit-test file); `declare -f`/`typeset -f`,
    `type`, `command -V`, and `export -f` now all route through one maintained
    chokepoint: `format_function_definition()` in
    `psh/visitor/formatter_visitor.py`. Output is the canonical `f() {` form —
    re-parses to the same program (the contract the tests pin), though not
    byte-identical to bash's `f ()` layout by design.
  - **Adjacent (bash-verified):** `export -f` with no names now lists each
    exported function's full definition followed by its `declare -fx` line, so
    `saved=$(export -f); eval "$saved"` restores exported functions;
    `declare -fx`/`-fr NAME` now applies the export/readonly attribute to the
    named function instead of printing it; no-name `-f`/`-F` listings carry
    per-function attribute flag strings and `-fx`/`-Fr` filter on the attribute.
  - Truth table: 61 bash-vs-psh cases, 41/56 → 59/61 matching (the 2 remaining
    divergences are one pre-existing `[ ... ] && break` exit-status bug in the
    break/continue cluster, identical before/after round-trip).
  - Tests: new round-trip suite
    `tests/integration/functions/test_declare_f_roundtrip.py` (case arms, 4
    heredoc forms, ANSI-C quoting, nested defs, attached redirects), attribute
    flag coverage in `test_readonly_export_attribute_flags.py`, 4 probes
    promoted to `tests/behavioral/golden_cases.yaml`, unique old-formatter
    coverage ported to `tests/unit/visitor/test_formatter_visitor.py`; mypy
    files list updated for the deleted module.

## 0.562.0 (2026-07-01) - Fix: brace expansion preserves adjacent quoted expansions + bash-order name fusion (appraisal #15 Tier 1, B1+B2)
- FIX (HIGH). Reappraisal #15 cluster B1+B2 — composite brace words destroyed
  adjacent quoted expansions, and an over-broad name-fusion guard left common
  brace-delimited forms unexpanded. One chokepoint fix in
  `psh/expansion/brace_expansion_tokens.py`.
  - **B1 — quoted expansions survive brace adjacency:**
    `TokenBraceExpander._expand_composite` encoded quoted STRING tokens
    char-by-char from `.value` and rebuilt them as plain literal TokenParts,
    destroying expansion-part metadata — `cp "$f"{,.bak}` passed a LITERAL
    `$f` to cp, and `"$f"{1,2}` printed `$f1 $f2`. Quoted tokens are now
    encoded per TokenPart (literal parts char-by-char as before, each
    expansion part as ONE opaque placeholder), so the rebuilt STRING tokens
    carry the original expansion metadata and downstream expansion still sees
    `"$f"`, `"$(...)"`, `"$((...))"`, `"$@"`. Bonus: a quoted token that
    encodes to nothing gets a quoted-empty marker, so `{a,""}` keeps its
    empty word (bash-verified).
  - **B2 — bash-order name fusion instead of the documented bail:** the old
    guard bailed on ANY variable followed by a name char, so forms that can
    never fuse (`${v}{1,2}`, `${a[0]}{x,y}`, `{a,${f}}b`, `${v:-D}{1,2}`)
    stayed unexpanded. Bash brace-expands BEFORE parameter expansion, so
    unquoted `$v{1,2}` re-forms the names `v1`/`v2` — psh now implements that
    fusion for simple-name VARIABLE tokens (folding trailing unquoted name
    chars), while delimited forms (`${v}`, `$?`, `$1`, subscripts, operators)
    never fuse and simply participate in adjacency. The unit test that pinned
    the old documented divergence now pins the bash-verified fusion.
  - **Backticks and process substitutions glue too:** `COMMAND_SUB_BACKTICK`
    and `PROCESS_SUB_IN/OUT` joined the word-like set — `` `echo x`{1,2} ``
    and `<(cmd){a,b}` previously split the brace word into its own run
    (producing `x1 2`).
  - **Verification:** 62-probe truth table vs bash 5.2 (was 21 pass / 30 fail
    before the fix, 11 probes added after) now 62/62; 18 key probes promoted
    to `tests/behavioral/golden_cases.yaml`; unit coverage for the
    quoted-adjacency / delimited-adjacency / fusion classes in
    `tests/unit/expansion/test_brace_expansion.py`; integration coverage for
    the `cp "$f"{,.bak}` idiom in
    `tests/integration/test_brace_adjacency_idioms.py`.

## 0.561.0 (2026-07-01) - Fix: ShellState.adopt() completeness — subshell state inheritance (appraisal #15 Tier 1, E1)
- FIX (HIGH). Reappraisal #15 cluster E1 — seven `ShellState.__init__` fields
  were never copied to subshell-style children (`( )`, `$( )`, `<( )`, the env
  builtin's child), so a whole family of state silently vanished across the
  boundary. Fixed at one chokepoint in `ShellState.adopt()`; verified against
  bash 5.2 (48/48 truth-table probes).
  - **What adopt() now copies:** `script_name` — `$0` in subshells/command
    substitutions (headline: `$(dirname "$0")` returned `.`);
    `function_stack` — `FUNCNAME` was empty in children; `source_depth` —
    `(return N)` in a sourced file/function errored instead of exiting N
    (child `FunctionReturn` now maps to the exit status); trap handlers;
    `directory_stack` (new `DirectoryStack.copy` — `(dirs)` sees pushd state);
    `history_state` (new `HistoryState.copy`; child appends don't leak back);
    the getopts cursor (`_getopts_charpos`/`_optind` — a child getopts no
    longer restarts a cluster walk); and ScopeManager SECONDS state via a new
    `adopt_special_state` (`SECONDS=500; (echo $SECONDS)` printed 0; RANDOM
    deliberately stays fresh — bash reseeds in children).
  - **Faithful bash trap model:** inherited traps are LISTABLE (`saved=$(trap)`
    idiom, `trap -p`) but never FIRE; the child's first trap modification drops
    all inherited entries; empty-action (`''`) ignores are genuinely in effect
    and survive; ERR/DEBUG stay live under `set -E`/`set -T`;
    process-substitution children carry no listing (`cat <(trap)` prints
    nothing, per bash); trap listing order now matches bash (EXIT, signals by
    number, DEBUG, ERR). Substitution children now fire their OWN EXIT trap
    (`x=$(trap 'echo bye' EXIT)` captures `bye`).
  - **Forked-child disposition sync is explicit at fork sites** (repair for a
    pid-inference regression found on-branch): `TrapManager` no longer infers
    forked-ness from `os.getpid()`; the fork sites (SubshellExecutor fg/bg,
    `child_policy.run_child_shell`) call `sync_forked_child_dispositions()`
    directly, so an in-process child Shell (env builtin inside a subshell)
    can't reset the enclosing forked shell's live handlers to SIG_DFL.
  - **Drift-lock:** `tests/unit/core/test_state_adopt_completeness.py` fails
    if a new `__init__` field is neither handled in `adopt()` nor justified on
    an explicit exclusion list — new state can't silently skip adopt() again.
  - Tests: `tests/unit/core/test_state_adopt.py` (unit),
    `tests/integration/subshells/test_state_inheritance.py` (integration incl.
    the regression probes), 13 behavioral golden cases pinning the bash
    comparison.

## 0.560.0 (2026-07-01) - Fix: parser statement-separator guard + and-or-level backgrounding (appraisal #15 Tier 1, A1+A3)
- FIX (HIGH). Reappraisal #15 cluster A1+A3 — two statement-boundary holes in
  the recursive-descent parser. Verified against bash 5.2.
  - **A1 missing separator validation:** after parsing a statement the parser
    never checked what came next, so junk between statements was silently
    treated as a new statement — ``echo (ls)`` EXECUTED both ``echo`` and the
    ``(ls)`` subshell (bash: syntax error, rc=2). Fixed at one chokepoint:
    ``StatementParser._require_statement_boundary`` requires a separator
    (``;``/newline/``&``), the enclosing construct's terminator, or end of
    input after every statement, raising bash's ``syntax error near
    unexpected token '...'`` (rc=2) otherwise. (``break >f``'s established
    trailing-redirect shape remains exempt, matching the pinned
    REDIRECT_EXEMPT behavior.)
  - **A3 `&` consumed at the wrong grammar level:** subshell and brace groups
    consumed a trailing ``&`` themselves, so ``(a) && (b) &`` backgrounded
    only ``(b)`` instead of the whole and-or list, and junk after ``&``
    (``(a) & | cat``, ``a & ; b``) parsed instead of erroring. ``&`` is now
    owned exclusively by the and-or-list level (POSIX grammar):
    ``(a) && (b) &`` backgrounds the entire list, and ``&`` followed by
    ``&&``/``||``/``|``/``|&``/``;`` is a syntax error while legal
    continuations (``a & b``, ``& fi``, ``& }``, ``;;``) still parse.
  - Tests: new ``tests/integration/parsing/test_statement_separators.py``
    (12 tests) plus 8 behavioral golden cases pinning the bash comparison.

## 0.559.0 (2026-06-23) - Fix: `set -x` quotes args & traces compound headers (appraisal #14 Tier 2)
- FIX (MED). ``set -x`` joined trace words unquoted and omitted compound-command
  headers. Now matches bash. Found in ground-up reappraisal #14; verified vs bash 5.2.
  - **Arg quoting:** a traced word that is empty or contains a shell
    metacharacter is single-quoted — ``echo "a b" c`` traces ``+ echo 'a b' c``,
    ``[ 0 -lt 2 ]`` traces ``+ '[' 0 -lt 2 ']'``, ``echo ""`` traces ``+ echo ''``.
    A new ``xtrace_quote`` helper (``core/options.py``) implements bash's
    safe-character rule, shared by the command trace and the assignment traces.
  - **Compound headers:** ``for`` re-traces ``+ for VAR in WORDS`` each iteration
    and ``case`` traces ``+ case WORD in`` (``while``/``until``/``if`` get no
    header — only their condition commands, which were already traced, now quoted).
  - **Assignments:** pure (``x=v``) and command-prefix (``x=5 cmd``) assignments
    trace with the VALUE quoted (``+ x='a;b'``); the prefix form is now traced at
    all (``+ x=5`` before ``+ cmd``).
  - DEFERRED (flat-string AST limitations): the ``[[ ... ]]`` test command is not
    traced, and a QUOTED ``for``/``case`` item is shown single-quoted (``'a b'``)
    where bash echoes the source double-quote style (``"a b"``) — both
    semantically equivalent.

## 0.558.0 (2026-06-23) - Feature: `time` reserved word (appraisal #14 Tier 2)
- FEATURE (MED). ``time`` was not a reserved word — ``time cmd`` became
  ``argv[0]`` and ran the external ``/usr/bin/time`` (BSD format, couldn't time
  pipelines/compounds/builtins). Implemented bash's ``time`` keyword. Found in
  ground-up reappraisal #14; verified against bash 5.2.
  - **`time [-p] PIPELINE`** times the WHOLE pipeline and reports real/user/sys
    to stderr — bash's default ``\nreal\t<m>m<s>.<ms>s`` format, or the
    space-separated 2-decimal POSIX format with ``-p``. user/sys include forked
    children's CPU (``os.times()`` deltas). ``time`` with no command times an
    empty pipeline (status 0); ``time ! cmd`` and a multi-stage ``time a | b``
    work; the timed pipeline's status flows to ``$?``.
  - **Lexer/parser:** ``time`` is now a reserved word (``TokenType.TIME``,
    KEYWORDS, KEYWORD_TYPE_MAP) recognized only at command position — so
    ``echo time``, ``time=5``, ``for time in …`` keep ``time`` literal (bash).
    It is a pipeline prefix (``parse_pipeline``) and keeps command position
    (``PIPELINE_PREFIX_TOKENS`` / ``LEXER_COMMAND_POSITION_WORDS``), which also
    resolves the deferred ``time while …`` / ``time [[ … ]]`` parse from M1.
    ``Pipeline`` gained ``timed`` / ``time_posix`` fields (the array-assignment
    characterization corpus was regenerated for the new repr — only those fields
    changed). ``TIMEFORMAT`` is not yet honored (default & ``-p`` only).
  - Doc: the differences-from-bash table now marks ``time`` Partial and ``wait
    -n`` supported.

## 0.557.0 (2026-06-23) - Feature: `wait -n` / `wait -p VAR` (appraisal #14 Tier 2)
- FEATURE (MED). ``wait -n`` was rejected as ``-n: not a valid process id``.
  Implemented bash's ``wait -n``: return when the NEXT single job completes,
  reporting that job's exit status (the FIRST to finish, not the first started);
  with operands, wait for the first of those jobs/PIDs; with nothing to wait for,
  return 127. ``-p VAR`` stores the finished job's PID. Found in ground-up
  reappraisal #14; verified against bash 5.2.
  - **Implementation:** ``WaitBuiltin`` parses leading ``-n``/``-p VAR`` options
    and a new ``_wait_for_next`` reaps children via ``waitpid(-1)`` until a
    matching JOB completes (an already-reaped DONE job counts as the next to
    report). Removed the now-stale ``wait -n`` entry from the absent-feature
    ledger; coverage moved to ``tests/integration/functions/test_wait_n.py``.

## 0.556.0 (2026-06-23) - Fix: FUNCNEST limits function-call nesting (appraisal #14 Tier 2)
- FIX (MED). ``FUNCNEST`` was ignored — deep/infinite recursion ran to Python's
  recursion limit (caught as a generic defect) instead of bash's clean nesting
  limit. Now a function call is refused once the call stack is already
  ``FUNCNEST`` deep: the body does not run, ``NAME: maximum function nesting
  level exceeded (N)`` is reported, and the current top-level command is aborted
  (execution resumes at the next input line, status 1). ``FUNCNEST`` unset or
  ``<= 0`` means no limit. Found in ground-up reappraisal #14; verified against
  bash 5.2.
  - **Implementation:** ``FunctionOperationExecutor._check_funcnest`` raises the
    command-abort signal on entry. That signal — added for the H6 assignment-error
    abort — is **generalized and renamed ``AssignmentAbort`` → ``TopLevelAbort``**
    (it now serves both readonly/nameref-cycle assignment errors and FUNCNEST),
    keeping its BaseException unwind-to-the-top-level-command behavior and its
    catch sites (``_execute_buffered_command``, subshell ``execute_fn``,
    ``run_child_shell``).

## 0.555.0 (2026-06-23) - Fix: `"${!ref}"` indirection to an `[@]` array yields fields (appraisal #14 Tier 2)
- FIX (MED). A quoted indirect expansion whose reference names an
  ``[@]``-subscripted array (``ref="a[@]"; "${!ref}"``) collapsed to a single
  IFS-joined field instead of one field per element: ``for w in "${!ref}"``
  saw ``<p q r>`` rather than ``<p> <q> <r>``, and ``set -- "${!ref}"`` gave
  ``$#`` = 1 not 3. Found in ground-up reappraisal #14; verified against bash 5.2.
  - **Fix:** ``FieldExpansionMixin.expand_to_fields`` (``expansion/fields.py``)
    now handles plain ``!`` indirection: when ``ref`` is a plain variable whose
    value is ``name[@]``-shaped, it expands the named array to fields. A scalar
    or ``[*]`` target, a positional/special source, an invalid name
    (``${!1abc}`` → bad substitution), or an unset ref all return ``None`` so
    the scalar path handles them — the error-raising resolver is deliberately
    NOT called here (it would mis-report and could double-print). An
    associative ``[@]`` target also now yields fields (its element order follows
    the same non-portable hash/insertion order as ``${m[@]}``).

## 0.554.0 (2026-06-22) - Fix: here-string performs tilde expansion (appraisal #14 Tier 2)
- FIX (MED). An unquoted here-string (``<<<``) expanded variables, command
  substitution and arithmetic but NOT tilde, so ``cat <<<~`` produced ``~``
  instead of the home directory (``cat <<<~/foo``, ``cat <<<~root`` likewise).
  Found in ground-up reappraisal #14; verified against bash 5.2.
  - **Fix:** ``redirect_herestring`` (``io_redirect/file_redirect.py``) now
    applies bash's value-context tilde rule to an UNQUOTED here-string before
    variable expansion (POSIX order) — a ``~``/``~user`` prefix at the start and
    after each ``:`` (``<<<~:~`` -> both), leaving a mid-word ``~`` (``x~y``)
    untouched. A double- or single-quoted here-string stays literal. Exposed via
    new ``ExpansionManager.expand_string_tildes`` /
    ``WordExpander.expand_value_tildes`` (reusing the existing assignment-value
    tilde engine).

## 0.553.0 (2026-06-22) - Fix: `export -p` lists declared-but-unset exports (appraisal #14 Tier 2)
- FIX (MED). ``export -p`` (and bare ``export``) iterated the live environment
  dict, so an exported-but-unset variable — ``export NOVAL`` with no value, which
  has the EXPORT attribute but no env entry — was omitted, even though
  ``declare -p NOVAL`` correctly showed ``declare -x NOVAL``. Found in ground-up
  reappraisal #14; verified against bash 5.2.
  - **Fix:** a new ``ScopeManager.all_exported_variables()`` returns the exported
    Variable OBJECTS (shadow-resolved), including an ``EXPORT|UNSET``
    declared-but-unset export (a plain ``UNSET`` tombstone — ``unset`` in a
    function — instead hides an outer export; arrays are excluded, as bash does
    not list them). ``export -p`` now renders each via the shared
    ``format_declaration`` (the same formatter ``declare -p`` uses), so valueless
    exports show as ``declare -x NAME`` and multi-attribute exports keep their
    full flags (``declare -ix N="5"``).

## 0.552.0 (2026-06-22) - Fix: `set -u` is enforced inside arithmetic (appraisal #14 Tier 2)
- FIX (MED). With ``set -u`` an unset variable referenced in an arithmetic
  context silently evaluated to 0 instead of erroring like a bare ``$undef``:
  ``set -u; echo $(( undefined + 1 ))`` printed ``1``, ``(( z + 1 ))`` ran, and
  ``for ((i=n;...))`` looped — all should abort with ``NAME: unbound variable``
  (bash). Found in ground-up reappraisal #14; verified against bash 5.2.
  - **Fix:** the arithmetic evaluator's ``get_variable``/``get_array_element``
    (``expansion/arithmetic/evaluator.py``) now call the shared
    ``OptionHandler.check_unset_variable`` before defaulting, raising
    ``UnboundVariableError`` for an unset name (at each step of a reference
    chain). A set-but-empty variable and an unset element of a SET array stay
    exempt (bash).
  - The arithmetic-COMMAND paths now report this uniformly: a new
    ``report_unbound_variable`` helper (``executor/strategies.py``) centralizes
    the bash-faithful "print once, abort non-interactive shell (127 for ``-c``,
    1 for a script)" handling, shared by the simple-command path
    (``command.py``), the ``(( ))`` command (``core.py``), and the C-style
    ``for`` loop — so ``(( undef ))`` no longer surfaced as
    ``unexpected error:``.

## 0.551.0 (2026-06-22) - Fix: a literal `}`/`]` suffix on a brace group attaches (appraisal #14 Tier 2)
- FIX (MED). A literal ``}``/``]`` immediately after a brace group was treated
  as a detachable shell operator, so the items were space-joined instead of
  carrying the suffix: ``echo arr[{1,2}]`` gave ``arr[1 2]`` (bash:
  ``arr[1] arr[2]``); likewise ``[{1,2}]``, ``{a,b}]``, ``{{a,b}}``,
  ``x{1..3}]``. Found in ground-up reappraisal #14; verified against bash 5.2.
  - **Root cause / fix:** a vestigial "detach" mechanism
    (``_split_detachable_suffix``/``_combine`` + ``_DETACH_*`` operator sets in
    ``brace_expansion.py``) left over from before brace expansion moved onto the
    token stream. Brace expansion now runs per-WORD, so a real operator
    (``;``/``|``/``)``/...) is always a SEPARATE token and can never be a word
    suffix — the mechanism only ever mis-fired on legitimate literal-brace
    suffixes. Deleted it; ``_expand_one_brace`` now always attaches the whole
    suffix to each item (an escaped operator like ``{a,b}\;`` correctly attaches
    too, matching bash). The fix removes code.

## 0.550.0 (2026-06-22) - Test: isolate flaky `test_if_with_file_test` (xdist filename collision)
- TEST-ONLY. ``test_if_with_file_test`` created fixed-name ``testfile``/``testdir``
  in the shared cwd via the plain ``shell`` fixture, so two xdist workers running
  it (or a sibling) concurrently raced on those names — an intermittent
  ``'file exists' in 'is directory'`` failure surfaced once during the Tier 2
  campaign. Switched it to ``isolated_shell_with_temp_dir`` (per-test cwd), per
  the parallel-safety rule for file-creating tests. No source/behavior change.

## 0.549.0 (2026-06-22) - Fix: `${...}` extent stops at the first `}` (literal `{` no longer nests) (appraisal #14 Tier 2)
- FIX (MED). A bare ``{`` inside a ``${...}`` body was counted toward brace
  nesting depth, so the lexer ran past the intended closing ``}``:
  ``echo "${x:-/path/{a,b}/c}"`` printed ``/path/{a,b}/c`` instead of bash's
  ``/path/{a,b/c}``, and ``echo "[${u:-a{b}]"`` ran off the end into a spurious
  ``syntax error: Unclosed " quote``. bash ends a ``${...}`` at the first
  unescaped ``}`` that is not inside a NESTED expansion. Found in ground-up
  reappraisal #14; verified against bash 5.2.
  - **Fix:** ``validate_brace_expansion`` (``lexer/pure_helpers.py``) now skips a
    nested ``${...}`` via a recursive call (the only way ``}`` nests, alongside
    the existing ``$(...)``/``$((...))`` skips) and no longer increments depth on
    a bare ``{`` — so the first unescaped ``}`` closes. Nested
    ``${a:-${b:-${c:-x}}}`` and ``${x:-$(echo hi)}`` still parse correctly.

## 0.548.0 (2026-06-22) - Fix: `!` before a compound command keeps command position (appraisal #14 Tier 2)
- FIX (MED). A ``!`` (pipeline negation) before a compound command reset the
  lexer's command position, so the following reserved word lexed as a plain
  WORD and the parser reported ``Expected command`` (or ``[[: command not
  found``): ``! while false; do echo x; done``, ``! if ...; fi``, ``! case ...
  esac``, ``! for ...``, ``! [[ -z x ]]`` all failed (bash accepts them). Found
  in ground-up reappraisal #14; affected BOTH parsers. Verified against bash 5.2.
  - **Fix:** a new ``PIPELINE_PREFIX_TOKENS`` vocabulary (``command_position.py``,
    currently ``EXCLAMATION``) is consulted by both command-position machines —
    the lexer pass (``modular_lexer._update_command_position_context``) and the
    keyword normalizer (``keyword_normalizer._next_command_position``) — so the
    token after ``!`` stays at command position and its keyword / ``[[`` is
    recognized. ``! { ... }``, ``! ( ... )`` and ``! pipeline`` (already correct)
    are unaffected. (``time`` is the other pipeline prefix, but it is a
    WORD-keyword the parser does not yet consume; it is handled with the ``time``
    reserved-word implementation.)

## 0.547.0 (2026-06-22) - Fix: `--format` round-trip fidelity on 8 constructs (appraisal #14 Tier 1, H8)
- FIX (HIGH). The ``--format`` pretty-printer was lossy on a cluster of
  constructs — several re-parsed to a DIFFERENT program or a parse error. Found
  in ground-up reappraisal #14; each is now a behavior-preserving round-trip,
  pinned in ``tests/unit/visitor/test_formatter_roundtrip.py``:
  - **Subscripted variable expansion** ``${arr[@]}`` / ``${arr[0]}`` rendered as
    ``$arr[@]`` (braces dropped → element 0 + literal ``[@]``).
    ``VariableExpansion.__str__`` now emits ``${name}`` when the name is not a
    bare identifier / special parameter.
  - **Process-substitution redirect target** ``> >(cat)`` / ``< <(cmd)`` glued
    to ``>>(cat)`` / ``<<(cmd)`` (append-operator + parse error). ``visit_Redirect``
    now emits a space before a ``<(``/``>(`` target.
  - **``|&``** silently downgraded to ``|`` — ``visit_Pipeline`` honors
    ``Pipeline.pipe_stderr`` and joins those stages with ``|&``.
  - **Escaped ``$`` in double quotes** ``"a\\$b"`` became a live expansion: the
    re-escaper no longer blanket-doubles backslashes (which turned the kept
    ``\\$`` into ``\\`` + ``$expansion``); it only doubles a backslash that would
    pair with the following emitted character.
  - **ANSI-C ``$'...'``** was re-emitted from its DECODED value (so ``$'q\\'x'``
    became ``$'q'x'`` — an unclosed quote); a new ``_escape_ansi_c`` re-encodes
    backslash, ``'`` and control characters.
  - **Named file descriptor** ``{fd}>file`` (the v0.539 feature) was dropped;
    ``visit_Redirect`` now emits the ``{var_fd}`` prefix.
  - **for/select ``in`` list items**: items with operator metacharacters
    (``"a;b"``) were emitted unquoted → parse error, while glob items (``*.md``)
    were quoted → globbing suppressed. A shared ``_format_word_list_item`` now
    quotes only metacharacter/whitespace items and leaves glob/expansion items
    unquoted.
  - **Heredoc inside a multi-stage pipeline** ``cat <<EOF | grep h`` placed the
    ``| grep h`` on the ``EOF`` terminator line (breaking termination →
    re-running printed nothing); ``visit_Pipeline`` now renders the full
    pipeline header first and appends the heredoc bodies after it.
  - DEFERRED: ``for x in '$lit'`` (single-quoted literal vs ``$expansion``)
    cannot be distinguished from the flat-string ``ForLoop.items`` and still
    round-trips as an expansion — fixing it needs migrating the loop-item field
    to the Word layer (a follow-up, as flagged in the reappraisal report).

## 0.546.0 (2026-06-22) - Feature: HISTCONTROL / HISTIGNORE; history dedup matches bash (appraisal #14 Tier 1, H7)
- FIX/FEATURE (HIGH). psh had no ``HISTCONTROL``/``HISTIGNORE`` support and
  UNCONDITIONALLY dropped a command equal to the immediately previous one —
  but bash records EVERY line by default (no dedup) and only filters when these
  variables ask. Found in ground-up reappraisal #14. ``HistoryManager.add_to_history``
  now matches bash:
  - default (``HISTCONTROL`` unset): every line recorded, including consecutive
    duplicates (the previous always-dedup was the divergence);
  - ``ignorespace``: a line beginning with a space is not recorded;
  - ``ignoredups``: a line equal to the previous entry is not recorded;
  - ``ignoreboth``: shorthand for both of the above;
  - ``erasedups``: all prior copies of the line are removed before it is added
    (in-session; the append-only history file is not rewritten);
  - ``HISTIGNORE``: colon-separated glob patterns (whole-line match, ``&`` =
    the previous line); a matching line is not recorded, checked after
    HISTCONTROL.
  Unknown HISTCONTROL tokens are ignored (bash). The concurrency-safe
  persistence marker (``_file_synced_len``) is adjusted when ``erasedups``
  removes already-persisted entries, preserving the v0.447 append-only invariant.

## 0.545.0 (2026-06-22) - Fix: fatal assignment error aborts the current command, not the whole shell (appraisal #14 Tier 1, H6a)
- FIX (HIGH). A readonly-variable or circular-nameref assignment error did
  ``sys.exit(1)`` in script mode, killing the entire shell — so a script that
  hit such an error mid-way silently died and lost every subsequent line. bash
  reports the error, unwinds the WHOLE current top-level command (the rest of
  the command list and any enclosing ``if``/loop/function/subshell on the same
  input), then RESUMES at the next top-level command. Found in ground-up
  reappraisal #14; verified against bash 5.2 across one-line, multi-line,
  if-body, loop-body, function-body, subshell, command-substitution, and
  two-consecutive-errors cases.
  - **Fix:** a new ``AssignmentAbort`` control-flow signal (derives from
    ``BaseException`` like ``SystemExit``, so it unwinds past the executor's
    ``except Exception`` guards without being mistaken for an internal defect).
    ``CommandAssignments.apply_pure`` raises it (after printing the error)
    instead of ``sys.exit``/``return 1``; it is caught at the top-level command
    boundary (``SourceProcessor._execute_buffered_command``, which resumes the
    next command) and at the child-shell boundaries (subshell ``execute_fn`` and
    ``run_child_shell``, which exit the child with status 1). The one-liner
    ``readonly r=1; r=2; echo X`` still aborts the whole list (X skipped, rc=1)
    exactly like bash.
  - DEFERRED (H6b/H6c): the integer-arithmetic assignment-error ``-c``-vs-script
    fatality nuance, and the misleading ``unexpected error:`` prefix on a
    ``readonly -f`` function redefinition, remain follow-ups.

## 0.544.0 (2026-06-22) - Fix: scalar/integer `+=` through a nameref appends to the target's value (appraisal #14 Tier 1, H5)
- FIX (HIGH). A scalar or integer ``+=`` append through a name reference
  appended to the nameref's OWN value — the literal target name — instead of
  the target variable's value:
  - ``n=5; declare -n r=n; r+=3; echo $n`` gave ``n3`` (bash: ``53``);
  - ``declare -i n=5; declare -n r=n; r+=3`` gave ``0`` (bash: ``8``);
  - ``declare -u u=x; declare -n r=u; r+=world`` gave ``UWORLD`` (bash: ``XWORLD``).
  (Array nameref ``+=(...)`` already worked.) Found in ground-up reappraisal #14;
  verified against bash 5.2.
  - **Fix:** ``resolve_append_assignment`` now resolves the nameref to its final
    target (``resolve_nameref_name``) BEFORE reading the old value and the
    integer/array attributes, so the append uses the target's value and the
    target's attributes. A non-nameref name resolves to itself (no change to the
    common case); the write side still re-resolves the nameref.

## 0.543.0 (2026-06-22) - Fix: bare `declare NAME` inside a function is local (appraisal #14 Tier 1, H4)
- FIX (HIGH). A bare ``declare NAME`` (or ``declare -ATTR NAME``, no value)
  inside a function found and mutated an OUTER-scope variable instead of
  creating a function-local shadow, so ``g=glob; f(){ declare g; g=x; }; f``
  leaked ``g=x`` to the global scope (bash keeps the outer ``g=glob`` — a bare
  ``declare NAME`` is equivalent to ``local NAME``). ``declare -i g`` /
  ``declare -x g`` / ``declare -r g`` inside a function likewise wrongly changed
  the outer variable's attributes/value. Only the no-value forms were affected;
  ``declare g=value`` and ``local g`` were already correct. Found in ground-up
  reappraisal #14; verified against bash 5.2.
  - **Fix:** the bare-name scalar path now resolves the variable in the scope
    ``declare`` writes to (a new ``_declared_in_target_scope`` helper — current
    scope only inside a function, mirroring the array path's
    ``_existing_in_target_scope`` but INCLUDING declared-but-unset tombstones so
    repeated attribute declares still accumulate). When the name is not present
    in that scope, a fresh local declared-but-unset shadow is created instead of
    reaching up to the outer variable.

## 0.542.0 (2026-06-22) - Fix: exec on fd 3 no longer corrupts the script-reading fd (appraisal #14 Tier 1, H3)
- FIX (HIGH). In script/``source`` mode a plain ``open()`` landed the script
  file on the lowest free descriptor (typically fd 3), so a script doing
  ``exec 3>&-`` — or the classic ``exec 3>&1 1>&2 2>&3 3>&-`` stdout/stderr
  swap idiom — clobbered the very fd psh was reading the script from. At
  end-of-file ``FileInput.__exit__`` then failed to close it and printed a
  spurious ``psh: <script>: [Errno 9] Bad file descriptor`` with exit 1.
  (``-c`` was immune; only fd 3 broke — ``exec 4>&-`` … ``9>&-`` were fine.)
  Found in ground-up reappraisal #14; verified against bash 5.2.
  - **Fix:** ``FileInput.__enter__`` now relocates the script-reading
    descriptor to the lowest free fd ``>= 10`` via ``fcntl(F_DUPFD_CLOEXEC,
    10)`` (close-on-exec set, so it does not leak to child processes), exactly
    as bash keeps its own script fd out of the user-visible 0–9 range. A script
    can now freely ``exec`` on fds 3–9.

## 0.541.0 (2026-06-22) - Fix: ERR/DEBUG traps no longer over-fire inside functions; add errtrace/functrace (appraisal #14 Tier 1, H2)
- FIX (HIGH). ERR and DEBUG traps were inherited into function bodies and
  re-fired through every brace-group layer, with no notion of bash's
  ``errtrace``/``functrace`` options. Found in ground-up reappraisal #14.
  Verified against bash 5.2 with a side-effect counter.
  - ``trap 'c=$((c+1))' ERR; f(){ false; }; f`` fired the ERR trap **twice**
    (once for the inner ``false``, once for ``f`` returning non-zero at top
    level); bash fires it **once** — the ERR trap is not run inside a function
    unless ``set -o errtrace`` (``set -E``).
  - ``trap 'echo E' ERR; { { false; }; }`` fired **three** times (once per
    enclosing brace group) where bash fires once — a brace group is transparent,
    so the failing leaf command owns the single fire.
  - DEBUG fired before every command inside a function body; bash does not run
    DEBUG inside a function unless ``set -o functrace`` (``set -T``).
  - **New options** ``errtrace`` (``-E``) and ``functrace`` (``-T``) added to the
    option registry, including their ``$-`` letters (``E``/``T``) and ``set -o``
    listing. Off by default (bash default).
  - **Fix:** ``TrapManager`` now gates ERR firing on ``errtrace`` and DEBUG
    firing on ``functrace`` while ``function_stack`` is non-empty (a single
    ``_inherited_into_function`` helper covers the one ERR and six DEBUG firing
    sites). The executor skips the redundant ERR fire at a brace-group pipeline
    level, since the failing leaf inside already fired. Top-level firing is
    unchanged.
  - NOTE: ``trap … RETURN`` and exact ``functrace=on`` DEBUG fire-counts remain
    follow-ups (see H2 in the reappraisal report).

## 0.540.0 (2026-06-22) - Fix: EXIT trap fires on every shell-exit path (appraisal #14 Tier 1, H1)
- FIX (HIGH). The EXIT trap was wired only into the ``exit`` builtin, so it was
  silently DROPPED on three other ways the shell (or a subshell) finishes — a
  silent failure of the universal ``trap cleanup EXIT`` idiom. Found
  independently by three subsystem auditors in ground-up reappraisal #14
  (``docs/reviews/ground_up_reappraisal_14_2026-06-22.md``). Verified against
  bash 5.2.
  - **Script reaching EOF** — the guard at ``script_executor.py`` was
    ``old_script_mode != True``, but ``Shell(script_name=...)`` sets
    ``is_script_mode`` at construction, so the captured ``old_script_mode`` was
    already ``True`` and the trap never fired. (e.g. ``trap "echo BYE" EXIT;
    true`` in a script printed nothing.)
  - **``set -e`` abort** — the executor raises ``SystemExit`` directly
    (``core.py``), a ``BaseException`` that propagated past the trap-firing call
    sites. (e.g. ``trap cleanup EXIT; set -e; false`` skipped cleanup.)
  - **Background subshell** — ``( trap ... EXIT; ... ) &`` omitted the
    ``execute_exit_trap()`` that the foreground subshell path already had.
  - **Fix:** a single chokepoint, ``SourceProcessor.execute_as_main``, now
    fronts every non-interactive whole-shell run (``-c``, script file, piped
    stdin): it recovers the status from a ``SystemExit`` and fires the EXIT trap
    exactly once (the existing ``_exit_trap_executed`` idempotency guard means
    the ``exit`` builtin's own firing is not double-counted). Firing is NOT
    swallowed, so ``exit N`` inside the trap still overrides the status, and the
    trap reads the correct ``$?``. The background-subshell body fires its own
    EXIT trap, mirroring the foreground path. This removes two redundant
    trap-firing call sites in ``__main__.py``.

## 0.539.0 (2026-06-21) - Feature: named file descriptors {varname}>file (appraisal Tier 3, M2)
- FEATURE (MED). Implemented bash's named-file-descriptor redirections:
  ``{varname}>file``, ``{varname}<file``, ``{varname}>>file``,
  ``{varname}<>file``, ``{varname}>|file``, and the dup/close forms
  ``{varname}>&N`` / ``{varname}<&N`` / ``{varname}>&-``. The shell allocates a
  free file descriptor >= 10, performs the redirect onto it, and stores the
  number in the variable (e.g. ``exec {fd}>log; echo hi >&$fd``). Spans lexer,
  AST, parser, and executor:
  - **Lexer** (``recognizers/operator.py``): ``{NAME}`` followed by a redirect
    operator is recognized as a named-fd prefix ONLY at word-start, with a
    valid identifier and no spaces — so brace groups ``{ cmd; }``, brace
    expansion ``{a,b}``, a literal ``{fd}``, and a prefixed ``a{fd}`` are all
    untouched (bash-pinned). The variable name rides on a new ``var_fd`` token
    field; ``Redirect`` gets a matching ``var_fd``.
  - **Executor** (``io_redirect``): a new ``FileRedirector.apply_var_fd_redirect``
    allocates the fd via ``fcntl(F_DUPFD, 10)`` (or closes the fd named by the
    variable for ``>&-``) and assigns the variable. Each redirect-application
    path applies it in the right process: parent-side and PERSISTENT for
    non-forked commands (builtins, functions, ``exec``, compound groups — the fd
    is not auto-closed, matching bash); child-side for forked commands (external
    programs, subshells), so the parent's variable stays unset and no fd leaks,
    exactly as bash behaves.

## 0.538.0 (2026-06-21) - Fix: heredoc inside process substitution (appraisal Tier 3, M8)
- BUGFIX (MED). A heredoc inside ``<(...)`` / ``>(...)`` —
  ``cat <(cat <<EOF`` … ``EOF`` … ``)`` — failed two ways: the outer parse
  errored ("Expected file name"), and once that was past, the heredoc body
  lines leaked out as top-level commands (``hello: command not found``). Three
  fixes, all so the inner heredoc stays nested exactly as it does inside
  ``$(...)``:
  - **Lexer** (``recognizers/process_sub.py``): an unclosed ``<(``/``>(`` now
    takes everything to end of input as one (incomplete) process-substitution
    token, instead of returning ``None`` and degrading to a bare ``<`` redirect
    — which let the inner ``<<EOF`` escape as a SEPARATE top-level heredoc whose
    body the heredoc lexer then stripped, breaking the later full tokenization.
  - **Parser** (``recursive_descent/parsers/commands.py``): an unclosed
    process-substitution token (value not ending in ``)``) raises an
    incomplete-input (``at_eof``) error, so interactive/script line-gathering
    keeps reading until the matching ``)`` arrives — mirroring ``$(``'s
    ``command_unclosed`` handling. A genuinely unclosed ``<(`` at EOF now
    reports a clean "unclosed process substitution" error instead of a runaway.
  - **Executor** (``io_redirect/process_sub.py``): the substitution body now
    runs through the unified ``child.run_command`` path (heredoc-aware), like
    command substitution, instead of a bare ``tokenize``/``parse`` with no
    heredoc support.

## 0.537.0 (2026-06-21) - Fix: interactive PS1/PS2 perform $-expansion (appraisal Tier 3, M12)
- BUGFIX (MED). In the interactive REPL, PS1/PS2 were rendered through the
  escape-ONLY path (``\u``, ``\h``, ``\w``…), so ``$``/``$(...)``/``$((...))`` in a
  prompt were printed literally instead of expanded. bash applies its default
  ``promptvars`` — backslash escapes THEN parameter / command / arithmetic
  expansion. ``MultiLineInputHandler._get_prompt`` now renders through the shared
  ``PromptManager`` (``expand_full``), so ``PS1='[$FOO-$(echo CMD)]\$ '`` expands
  exactly as in bash. The non-printing markers (``\[``/``\]``) and escape-output
  protection are preserved (a ``\$``-produced ``$`` does not start a command
  substitution; an escape's value is not re-interpreted).
- ELEGANCE (paired). ``PromptManager`` was constructed and wired to
  ``repl_loop.prompt_manager`` but never used for rendering — the REPL rendered via
  a second, escape-only ``PromptExpander`` owned by ``MultiLineInputHandler``. The
  handler now delegates to the shared ``PromptManager``, making it the single
  live prompt-rendering authority and removing the duplicate expander instance.

## 0.536.0 (2026-06-21) - Fix: composite / $-containing heredoc delimiters (appraisal Tier 3, M1)
- BUGFIX (MED). A heredoc delimiter that spans several tokens — ``<<E$X``,
  ``<<E"O"F``, ``<<$VAR`` — was truncated to its LEADING token, so the body never
  terminated (``<<E$X`` returned empty) and the trailing parts were parsed as
  command arguments (``<<E"O"F`` ran ``cat OF``). bash takes the whole delimiter
  word LITERALLY (no expansion). Now the three places that recover a heredoc
  delimiter agree on the full word:
  - the lexer (body terminator) recovers it from the raw source span of the
    delimiter's adjacent tokens (``HeredocLexer._delimiter_from_source``);
  - the parser consumes ALL adjacent word/expansion tokens (so trailing parts
    are not command args) and sets ``heredoc_quoted`` from any quoted/escaped
    part (``_parse_heredoc``, now also accepting a ``$VAR``-leading delimiter);
  - the line-gathering detector's ``HEREDOC_MARKER_RE`` now includes ``$`` as a
    literal delimiter char (``utils/heredoc_detection.py``).
- A subtle bug found and fixed along the way: the lexer recovers the delimiter
  from the body-STRIPPED command text the tokens came from, NOT ``self.source``
  (whose offsets include the removed body lines) — otherwise a SECOND heredoc's
  delimiter was sliced from the wrong offset.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, M1). New
  ``tests/integration/redirection/test_heredoc_composite_delimiter.py`` (14
  cases, bash-compared).

## 0.535.0 (2026-06-21) - Fix: set -u exit status is 1 for a script file, 127 only for -c (appraisal Tier 3, M13)
- BUGFIX (MED). A ``set -u`` unbound-variable abort exited with status 127 in
  EVERY non-interactive mode, but bash uses 127 only for ``-c`` — a script file
  (and a non-interactive shell otherwise) exits 1. The status is now
  command-mode-dependent (``executor/command.py``): ``-c`` → 127, script file →
  1. Both still abort the shell.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, M13). New
  ``tests/integration/scripting/test_set_u_exit_code.py`` (5 cases); a
  conformance test that pinned the old 127 was corrected to the bash-true 1.
  (Two related M13 sub-items remain: a piped-stdin shell should ABORT on the
  violation rather than continue, and script-mode shell errors still lack the
  ``scriptname: line N:`` prefix.)

## 0.534.0 (2026-06-21) - Fix: honor $HISTFILE / $HISTSIZE (appraisal Tier 3, M14)
- BUGFIX (MED). psh hardcoded ``~/.psh_history`` and a 1000-entry cap and ignored
  the ``HISTFILE`` / ``HISTSIZE`` shell variables — even though the user guide
  tells users to set them. ``ShellState.history_file`` / ``max_history_size`` now
  read those variables DYNAMICALLY (bash): ``HISTFILE`` (tilde-expanded) overrides
  the file path, ``HISTSIZE`` (a non-negative integer) the entry cap; invalid /
  unset values fall back to the defaults. The setters still work for the
  default fallback, so a script setting ``HISTSIZE=50`` now actually trims what
  ``HistoryManager`` persists. ``core/state.py``.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, M14). New
  ``tests/unit/core/test_histfile_histsize_vars.py`` (8 cases).

## 0.533.0 (2026-06-21) - Fix: FUNCNAME is the full call stack, not just the current function (appraisal Tier 3)
- BUGFIX (MED). ``FUNCNAME`` is an ARRAY in bash — ``[0]`` is the running
  function, ``[1]`` its caller, and so on — but psh returned only a SCALAR (the
  current function), so ``${FUNCNAME[1]}`` (the caller's name) and
  ``${#FUNCNAME[@]}`` beyond 1 were empty. It is now built as an indexed array
  from ``function_stack`` reversed (innermost first), in
  ``ScopeManager`` special-variable resolution (``core/scope.py``). ``$FUNCNAME``
  and ``${FUNCNAME[0]}`` are unchanged; outside a function it is still empty.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``). New
  ``tests/unit/core/test_funcname_call_stack.py`` (12 cases) and a bash-compared
  golden case.

## 0.532.0 (2026-06-21) - Fix: explicit-fd heredoc/here-string no longer self-closes (appraisal Tier 3, M6)
- BUGFIX (MED). An explicit-fd heredoc / here-string (``cat 3<<EOF <&3``,
  ``cat 5<<<word <&5``) lost its body with ``Bad file descriptor`` whenever the
  anonymous temp file ``_content_to_fd`` used happened to land ON the target fd
  (the lowest free fd). The old code skipped the ``dup2`` when the fds matched
  and then ``tmp.close()`` closed the very fd holding the body. The existing
  conformance test used fds 5/10 (too high to collide), so it never caught it.
- Fix: deliver the body through the shared fd-preserving primitive — ``os.dup``
  the temp fd FIRST, so closing the temp object can never reclaim the target fd
  (``io_redirect/file_redirect.py``, addressing elegance finding E-IO's
  ``_content_to_fd`` / ``_dup2_preserve_target`` duplication at the same time).
- Side effect: ``read -u 3 line 3<<< data`` now matches bash (it relied on a
  here-string on an explicit fd), so its strict-xfail conformance test was
  converted to a passing parity test.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, M6). New
  ``tests/integration/redirection/test_explicit_fd_heredoc_no_self_close.py``
  (6 cases, fds 3/4/5 that collide) and a bash-compared golden case. (M7 — the
  builtin ``>&2`` stream-object aliasing — is deferred: its fix is entangled with
  the in-process stream-vs-fd capture model.)

## 0.531.0 (2026-06-21) - Fix: backgrounded assignment runs in a subshell; DEBUG trap before loops/case (appraisal Tier 3, M4/M5)
- BUGFIX (MED, M4). A backgrounded pure or bare-array assignment (``x=5 &``,
  ``a[0]=v &``) mutated the PARENT shell (``x=5 & wait; echo $x`` printed ``5``).
  bash runs ``x=5 &`` in a forked subshell, so the assignment is discarded with
  the child and the parent is untouched; ``$!`` is still set and a job
  registered. The assignment is now routed to a background subshell BEFORE any
  array element is applied to the parent (``executor/command.py``,
  ``_run_background_assignment`` via ``ProcessLauncher.launch_background_job``).
- BUGFIX (MED, M5). The DEBUG trap did not fire before ``for`` / C-style-``for``
  iterations or before a ``case`` statement (it fired only for the body's simple
  commands). bash fires DEBUG before binding each ``for`` loop variable, before
  the ``case`` subject, and before each arithmetic step (init/cond/update) of a
  C-style ``for``. Added those firing points (``executor/control_flow.py``); the
  counts now match bash exactly for ``for``/``while``/``until``/``if``/``case``/
  C-style-``for``. (``select`` + DEBUG, an exotic combination, is left as a known
  minor gap.)
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, M4/M5). New
  ``tests/integration/control_flow/test_tier3_executor_fixes.py`` (14 cases) and
  three bash-compared golden cases.

## 0.530.0 (2026-06-21) - Fix: support the deprecated `$[expr]` arithmetic form (appraisal Tier 3, M3)
- BUGFIX (MED). ``$[expr]`` — bash's deprecated spelling of ``$((expr))`` — was
  passed through verbatim (``echo $[1+2]`` printed ``$[1+2]``). The lexer's
  expansion dispatch and the literal recogniser's ``can_start_expansion`` did not
  recognise ``$[``. Both now do: the expansion parser rewrites ``$[expr]`` to the
  canonical ``$((expr))`` token (balancing ``[]`` so subscripts like
  ``$[a[0]+1]`` work, and recursively rewriting nested ``$[...]`` so
  ``$[2*$[3]]`` works), so the whole arithmetic pipeline downstream is unchanged.
  ``psh/lexer/expansion_parser.py`` + ``recognizers/word_scanners.py``.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, M3). New
  ``tests/unit/expansion/test_dollar_bracket_arithmetic.py`` (12 cases) and a
  bash-compared golden case.

## 0.529.0 (2026-06-21) - Fix: three builtin/array bugs — read -p tty, declare -i array, unset arr[@] (appraisal Tier 3)
- BUGFIX (MED, M9). ``read -p`` wrote its prompt unconditionally, so a
  ``read -p`` from a pipe / here-string / redirected file leaked the prompt into
  the captured stream. bash writes the prompt only when the input is a terminal;
  the prompt is now gated on the read source being a tty
  (``read_builtin.py``, new ``_read_input_is_tty``).
- BUGFIX (MED, M10). ``declare -i a`` (integer attribute on a not-yet-existing
  array) left the FIRST element assignment UNEVALUATED — ``a[0]=2+3`` stored the
  literal ``2+3`` while later elements evaluated. The ``declare -i a`` tombstone
  reads as unset (so the pre-creation lookup was ``None``); the element writer
  now reads the attribute from the variable AS IT EXISTS after the array is
  created, where set_variable has merged the declared INTEGER attribute
  (``executor/array.py``). Applies to ``-i``/``-u``/``-l`` and indexed/assoc.
- BUGFIX (MED, M11). ``unset 'arr[@]'`` / ``'arr[*]'`` removed a single element
  (subscript ``@`` evaluated as index 0) instead of the WHOLE array. It now
  removes the whole INDEXED array; for an ASSOCIATIVE array ``@``/``*`` is a
  literal key (bash — the array is not cleared), and a scalar reports
  "not an array variable" (``builtins/environment.py``).
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, M9/M10/M11). New
  ``tests/unit/builtins/test_tier3_builtin_array_fixes.py`` (11 cases) and four
  bash-compared golden cases.

## 0.528.0 (2026-06-21) - Test: serial-mark the signal-delivering trap conformance suite
- TEST-INFRA (no psh change). ``tests/conformance/bash/test_trap_signal_spec_conformance.py``
  traps AND delivers signals (``kill -N $$``) while comparing against live bash,
  but was not ``serial``-marked, so it ran in the xdist parallel phase where the
  signal dispositions race with sibling workers — it flaked intermittently in the
  parallel phase while always passing in isolation / serially. Added it to
  ``conftest.py``'s ``serial_path_markers`` so it runs in the serial phase, like
  the other signal/job-control suites. (The other occasionally-seen flakes —
  ``test_signal_killed_exit_status.py`` and ``test_reappraisal6...`` — are already
  serial via the ``job_control`` path marker and a module ``pytestmark``; their
  earlier failures were from concurrent test invocations, not a marking gap.)
  Keeps the local ``--parallel`` gate (the release gate) reliable.

## 0.527.0 (2026-06-21) - Docs: correct the `[ < ]` / `[[ < ]]` collation comments (appraisal Tier 4)
- TRUTH-UP (comments only; zero behavior change). The ``[ < ]`` comment in
  ``builtins/test_command.py`` claimed psh's ``[[ ]]`` "uses locale collation" —
  it does NOT: ``[[ < ]]`` (``enhanced_test_evaluator``) compares by Unicode
  codepoint order, exactly like ``[ < ]``. Corrected both comments to state the
  real behavior and the resulting known divergence (bash's ``[[ < ]]`` honours
  LC_COLLATE in a non-C locale; psh does not). No code changed. Addresses the
  misleading-comment half of elegance finding E-Builtins/correctness-#7 in the
  2026-06-21 appraisal (``docs/reviews/ground_up_appraisal_2026-06-21.md``,
  Tier 4); implementing locale collation itself remains a deferred LOW item.

## 0.526.0 (2026-06-21) - Refactor: one background-launch helper for cmd & (appraisal Tier 4)
- REFACTOR (executor; zero behavior change). The four ``cmd &`` paths —
  backgrounded builtins and functions (``strategies.py``) and backgrounded
  subshells and brace groups (``subshell.py``) — each repeated the same launch
  boilerplate: build ``ProcessConfig(SINGLE, foreground=False[, is_shell_process])``,
  ``launcher.launch(...)``, ``job_manager.launch_background(...)``, ``return 0``.
  Hoisted that into one ``ProcessLauncher.launch_background_job(execute_fn,
  command_string, proc_label, *, is_shell_process=False)`` helper the four sites
  now call; only the per-case ``execute_fn`` and the ``is_shell_process`` flag
  differ.
- Zero behavior change: full suite green (8,389, unchanged); backgrounded
  builtin/function/subshell/brace-group all still set ``$!``, register as jobs,
  and are reaped by ``wait`` identically. Addresses elegance finding E-Exec in
  the 2026-06-21 appraisal (``docs/reviews/ground_up_appraisal_2026-06-21.md``,
  Tier 4).

## 0.525.0 (2026-06-21) - Refactor: lexer dead-field + can_start_expansion name collision (appraisal Tier 4)
- REFACTOR (lexer; zero behavior change). Two elegance cleanups from finding
  E-Lexer:
  - Removed ``QuoteRules.allows_nested_quotes`` — a field set on all four quote
    rules but never read anywhere (``quote_parser.py``).
  - Two different functions were both named ``can_start_expansion``: the weak
    ``ExpansionParser.can_start_expansion`` (just ``char in ('$', '`')``) and the
    strict ``word_scanners.can_start_expansion`` (validates the ``$`` actually
    begins an expansion). Same name, different semantics, different callers — a
    teaching trap. Renamed the weak one to ``ExpansionParser.is_expansion_sigil``
    and documented the distinction; the strict one (used by the literal
    recognizer for word boundaries) keeps the name.
- Zero behavior change: full suite green (8,389, unchanged), 656 lexer tests
  pass, ``ruff`` + ``mypy`` clean. Addresses elegance finding E-Lexer in the
  2026-06-21 appraisal (``docs/reviews/ground_up_appraisal_2026-06-21.md``,
  Tier 4). (The three expansion-extent scanners and the position-setter
  backward branch noted there are left for a follow-up — unifying the scanners is
  behavior-adjacent, not a pure cleanup.)

## 0.524.0 (2026-06-21) - Refactor: drop hand-rolled traversal the visitor base provides (appraisal Tier 4)
- REFACTOR (visitor; zero behavior change). The security and metrics analysis
  visitors hand-rolled ``visit_TopLevel``/``visit_StatementList``/
  ``visit_AndOrList`` methods that just re-implemented the descent the shared
  ``generic_visit`` -> ``visit_children`` default already provides (the
  dataclass-field walk in ``traversal.py``). Deleted the 5 pure-traversal
  duplicates (3 in ``security_visitor.py``, 2 in ``metrics_visitor.py``);
  ``MetricsVisitor.visit_AndOrList`` and ``LinterVisitor.visit_TopLevel`` are
  kept because they add real per-node work (cyclomatic count, unused-var check).
- Zero behavior change: full suite green (8,389, unchanged), the AST coverage
  matrix test still passes, and ``--security``/``--metrics`` over a nested
  ``for``/``if``/pipeline/``&&`` script produce identical findings and counts.
  Addresses elegance finding E-Visitor in the 2026-06-21 appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, Tier 4). (The
  ``CaseConditional`` pattern-traversal asymmetry noted there is left as-is — it
  would change analysis output, so it is a correctness item, not Tier 4.)

## 0.523.0 (2026-06-21) - Refactor: one source of truth for value-level ${...} operators (appraisal Tier 4)
- REFACTOR (expansion; zero behavior change). The value-level parameter
  operators (``#``/``##``/``%``/``%%``, ``/``/``//``/``/#``/``/%``, ``^``/``^^``/
  ``,``/``,,``) were spelled out TWICE — once in the scalar dispatch
  (``_apply_operator``) and once in the per-element array dispatch
  (``_apply_op_per_element``), so adding/changing one meant editing both (the
  embedded-extglob patsub fix had to be re-checked in both ladders). They now
  live in one ``_value_op`` table (keyed by ``_VALUE_OPERATORS``) that both
  drivers consume. ``psh/expansion/operators.py``.
- REFACTOR (expansion). Dropped a redundant ``sorted()`` in
  ``word_expander._glob_words``: ``glob_expander.expand()`` already returns
  sorted results, so the results were sorted twice.
- Zero behavior change: full suite green (8,389, unchanged) and a
  bash-comparison battery over scalar + per-element operator forms is identical.
  Addresses the elegance finding E-Expansion in the 2026-06-21 appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, Tier 4).

## 0.522.0 (2026-06-21) - Fix: a Ctrl-Z'd foreground job stays the current job (%+) (appraisal H9)
- BUGFIX (HIGH). A foreground job stopped by Ctrl-Z (SIGTSTP) was demoted out of
  ``%+``: the foreground teardown called ``set_foreground_job(None)``, which
  pushed the still-current stopped job to ``%-`` and cleared ``%+``. So the stop
  notice printed ``[1]-  Stopped`` instead of bash's ``[1]+``, and a bare ``bg``
  or ``fg`` (which resolve ``%+``) failed with ``%+: no such job``. bash keeps a
  stopped foreground job as the current job so it resumes with no argument.
- Fix: ``JobManager.finish_foreground_job`` takes the job and, when it is
  ``STOPPED``, re-promotes it to ``%+`` after the teardown — keeping the job that
  was current before it as ``%-`` (``job_control.py``; both the external-command
  and pipeline foreground paths pass the job through). Completed jobs are
  unaffected (they are removed by the caller).
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, finding H9). New
  ``tests/integration/job_control/test_stopped_job_current_marker.py`` (4 cases:
  single stop → ``%+``, the ``+`` notice marker, a second stop demoting the first
  to ``%-``, and completion not becoming current).

## 0.521.0 (2026-06-21) - Fix: ~/.pshrc no longer sourced for -c / scripts under a tty (appraisal H8)
- BUGFIX (HIGH). ``_init_interactive`` decides at construction whether to source
  ``~/.pshrc`` (and load history / enable line editing), gating on
  ``is_script_mode`` — but ``__main__`` set ``is_script_mode`` / ``command_mode``
  AFTER constructing the shell. So whenever stdin was a terminal (the normal case
  at a prompt), EVERY ``psh -c '...'`` and ``psh script.sh`` sourced the user's rc
  file first, polluting the command/script with the user's aliases, functions and
  exports. bash never sources rc for ``-c`` or scripts.
- Fix: ``__main__`` determines the run-mode from argv BEFORE constructing the
  shell and passes it in (new ``Shell(command_mode=...)`` parameter; script files
  pass ``script_name``). ``_init_interactive`` now computes a single
  ``noninteractive_mode`` (script OR command) and only sources rc / loads history /
  enables emacs+histexpand for a genuinely interactive shell. (This also corrects
  history-loading and ``$-`` ``H``/emacs flags for ``psh -c`` under a tty, which
  had the same root.)
- The pre-existing ``test_rc_file_not_loaded_in_script_mode`` gave false
  confidence: it constructs ``Shell(script_name=...)`` directly (a path that sets
  the flag early, which the real entry points never take). New
  ``tests/system/initialization/test_rc_not_loaded_for_command_or_script.py``
  drives the REAL ``python -m psh`` entry point with a real tty on fd 0, covering
  ``-c``, a script file, and the rc-IS-sourced interactive direction.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, finding H8).

## 0.520.0 (2026-06-21) - Fix: --format round-trip losses + analysis-mode crash on syntax error (appraisal H10/H11)
- BUGFIX (HIGH). ``--format`` was lossy in four behavior-changing ways (distinct
  from the four fixed in v0.505): each produced output that re-parsed to
  DIFFERENT — sometimes INVALID — shell.
  - A bare ``$var`` before a name-continuation char dropped its disambiguating
    braces: ``echo ${x}there`` → ``echo $xthere`` (references a different
    variable); ``${x}0`` → ``$x0``.
  - ``case`` patterns lost their quotes: ``"a b")`` → ``a b)`` (a quoted literal
    silently became two glob words). Root: ``visit_CaseItem`` used the flat
    ``pattern`` string instead of the quote-preserving ``CasePattern.word``.
  - The ``case`` subject lost its quotes: ``case "a b" in`` → ``case a b in``
    (a SYNTAX ERROR on re-parse). The subject is a flat quote-stripped string;
    it is now re-quoted when it contains whitespace.
  - Embedded quotes/backticks in a double-quoted literal were not re-escaped:
    ``echo "say \"hi\""`` → ``echo "say "hi""``. ``_format_word`` now re-escapes
    ``\``/``"``/`` ` `` when re-wrapping a double-quoted literal.
- BUGFIX (HIGH). All five analysis modes (``--validate``/``--format``/
  ``--metrics``/``--security``/``--lint``) crashed with an uncaught Python
  traceback on a syntax error — defeating the whole point of ``--validate``.
  ``visitor_modes.py`` caught only ``(ValueError, TypeError)``, but
  ``ParseError``/``LexerError``/``UnclosedQuoteError`` derive from
  ``PshError``/``SyntaxError``. They are now caught and reported as a one-line
  ``psh: <loc>: <message>`` diagnostic with exit 2 (matching bash ``-n`` and the
  execution path).
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, findings H10/H11). New
  ``tests/unit/visitor/test_formatter_losses_and_analysis_crash.py`` (21 cases,
  incl. behavior-preservation round-trips and all five modes on parse+lexer
  errors).

## 0.519.0 (2026-06-21) - Fix: readonly -a/-A and export -f accepted (appraisal H6/H7)
- BUGFIX (HIGH, two related). Two declaration builtins hand-rolled incomplete
  flag parsers that rejected everyday attribute/function flags bash accepts —
  fatal under ``set -e``.
  - H6: ``readonly -a`` / ``readonly -A`` printed ``readonly: invalid option:
    -a`` (exit 2); the "readonly array" idiom (``readonly -a arr=(1 2 3)``)
    failed outright. ``readonly`` now forwards ``-a``/``-A`` to the ``declare
    -r`` delegation it already uses (``ReadonlyBuiltin._parse_readonly_options``,
    ``function_support.py``), so the array is created readonly.
  - H7: ``export -f funcname`` printed ``export: -f: invalid option`` (exit 2);
    scripts that export functions broke. ``export`` now accepts ``-f``: a named
    function gains an export attribute (exit 0); a non-function name is a usage
    error (exit 1, "not a function"), and ``export -fn`` clears it. (psh does
    not serialise functions into the environment for EXTERNAL children, so the
    attribute is observable via ``export -f`` listing rather than in
    subprocesses — a documented limitation, not the bug being fixed.) New
    ``Function.exported`` attribute + ``FunctionManager.set_function_exported``.
- Both shared one root (elegance finding E-Builtins): three divergent
  declaration-flag parsers, two silently incomplete. ``declare`` (the complete,
  table-driven one) is unchanged.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, findings H6/H7). New
  ``tests/unit/builtins/test_readonly_export_attribute_flags.py`` (12 cases) and
  five bash-compared golden cases.

## 0.518.0 (2026-06-21) - Fix: break/continue/return don't cross function or pipeline-subshell scope (appraisal H3/H4)
- BUGFIX (HIGH, two related). A function body and each pipeline component are a
  fresh control-flow scope, but ``loop_depth`` was inherited across both
  boundaries.
  - H3: a function called from inside a loop saw the caller's loop nesting, so a
    ``break``/``continue`` in the function body (POSIX: "not meaningful")
    terminated the CALLER's loop. ``f() { break; }; for i in 1 2 3; do echo $i;
    f; done`` printed only ``1`` instead of ``1 2 3``. ``execute_function_call``
    also explicitly re-raised ``LoopBreak``/``LoopContinue`` into the caller.
  - H4: ``return`` (or a ``break N`` exceeding the subshell's own loops) inside a
    pipelined compound leaked the control-flow exception out of the forked
    pipeline child to the generic handler, printing a spurious ``psh: error:``
    and forcing exit 1. ``f() { echo a | while read x; do return 5; done; echo
    "after=$?"; }; f`` printed ``psh: error:`` + ``after=1`` instead of
    ``after=5``.
- Fix: ``execute_function_call`` (``function.py``) saves/resets ``loop_depth`` to
  0 around the body (in-function loops re-increment) and no longer re-raises
  break/continue across the boundary; the forked pipeline child (``pipeline.py``)
  resets ``loop_depth`` to 0 and converts an escaping ``FunctionReturn`` to the
  subshell's exit code and ``LoopBreak``/``LoopContinue`` to a clean subshell
  exit — matching the plain-subshell path and bash. (The error-MESSAGE prefix
  for out-of-loop break/continue still differs from bash — that's the separate
  script-error-prefix finding.)
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, findings H3/H4). New
  ``tests/integration/control_flow/test_loop_control_scope_boundary.py`` (9
  cases) and five bash-compared golden cases.

## 0.517.0 (2026-06-21) - Fix: embedded extglob negation `!(...)` matches per-span (appraisal H5)
- BUGFIX (HIGH). Embedded extglob negation — ``a!(P)b`` (anything other than a
  standalone top-level ``!(P)``) — matched per-CHARACTER instead of per-SPAN, so
  it over-rejected any span that merely CONTAINED a character starting an
  alternative. ``[[ xfoox == x!(o)x ]]`` was false, ``case xfoox in x!(o)x)``
  didn't match, ``${s/x!(o)y/_}`` didn't replace, and ``echo !(foo).txt`` dropped
  files like ``xfoox.txt``. One root, wide blast radius: ``case``, ``[[ == ]]``,
  the ``${v#pat}``/``${v/pat/r}`` operators, and pathname globbing all funnel
  through the same converter.
- Root cause: ``extglob.py`` emitted ``(?:(?!(?:alt).*).)*`` for embedded
  negation. Python's ``re`` fundamentally CANNOT express this — the negation is a
  property of the whole consumed span ("the span is not P"), which needs a
  variable-width lookbehind ``re`` lacks. Fix: a small backtracking matcher
  (``_extglob_consume`` / ``extglob_fullmatch`` / ``extglob_match_at``) that is
  correct for standalone AND embedded negation, validated against a 39-case bash
  truth table plus operator semantics. All matching paths (``pattern.py`` for
  ``case``/``[[ ]]``, the removal/substitution operators in
  ``parameter_expansion.py``, and ``expand_extglob`` for globbing) route negation
  patterns to the matcher; the fast regex path is unchanged for the ~99% of
  patterns without ``!()``. The substitution matcher reproduces bash's
  empty-match-suppressed-at-end semantics. The now-dead
  ``_is_standalone_negation`` helper was removed.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, finding H5). New
  ``tests/unit/expansion/test_extglob_negation.py`` (37 cases incl. the existing
  false-positive shape that masked the bug) and five bash-compared golden cases.

## 0.516.0 (2026-06-21) - Fix: reject empty compound bodies/conditions at parse time (appraisal H1)
- BUGFIX (HIGH). The recursive-descent parser silently accepted empty
  compound-command bodies and conditions that bash rejects as a syntax error
  (exit 2). The worst case was an INFINITE LOOP: ``while true; do done`` (an
  empty ``do`` body with a true condition) hung forever; ``until false; do done``
  likewise. Empty ``then``/``elif``/``else`` bodies (``if true; then fi``),
  empty loop/if conditions (``if then echo x; fi``, ``while do echo x; done``),
  empty ``for``/``select``/C-style-``for`` bodies, and empty function bodies
  (``f() { }``) were silently accepted as no-ops.
- Root cause: ``StatementParser.parse_command_list_until`` returns an empty
  ``CommandList`` when the terminator is already current, and no required-body
  caller checked for emptiness; ``functions.py`` re-implemented brace parsing
  without the empty-body guard that ``CommandParser.parse_brace_group`` already
  had. Fix: a new ``parse_required_command_list_until`` (the required-position
  twin, mirroring the brace-group guard) is used at every loop/if body and
  condition site and the function brace body. Empty ``case`` (``case x in esac``)
  and empty ``case`` branches (``a) ;;``) stay legal, matching bash. Separator-
  only bodies (``do ; done``) were already rejected.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, finding H1). New
  ``tests/unit/parser/test_empty_compound_body_rejection.py`` (12 rejections +
  8 acceptances), no-separator forms added to the combinator error-parity
  corpus, two false-confidence function tests corrected to the bash-true
  behavior, and five bash-compared golden cases. The educational combinator
  parser still accepts a few of these (empty conditions/else/function body) — a
  documented out-of-scope gap, not a tracked defect.

## 0.515.0 (2026-06-21) - Fix: $-expansions corrupted in (( )) / C-for / while (( )) (appraisal H2)
- BUGFIX (HIGH). In the arithmetic COMMAND/loop forms — ``(( expr ))``,
  ``for ((init;cond;upd))``, and ``while (( expr ))`` — every ``$``-expansion was
  silently corrupted, because ``TokenStream.collect_arithmetic_expression``
  (``psh/lexer/token_stream.py``) rebuilt the expression text from raw
  ``token.value`` and the lexer strips the leading ``$`` from VARIABLE tokens
  (``$1`` → ``1``, ``$#`` → ``#``, ``${#a[@]}`` → ``{#a[@]}``). The reconstructed
  text therefore lost the expansion: ``(( $1 == 5 ))`` compared the literal ``1``,
  ``(( ${#arr[@]} > 0 ))`` raised ``((: Unexpected character '{'``, and
  ``((c[$w]++))`` incremented the key ``w`` instead of ``$w``'s value. The string
  is frozen onto the ``ArithmeticEvaluation`` node before evaluation, so the loss
  was permanent.
- The fix re-adds the ``$`` for VARIABLE tokens during reconstruction — mirroring
  the array-subscript reconstruction already in
  ``psh/parser/combinators/arrays.py``. The ``$((...))`` *expansion* form was never
  affected (it keeps its own single ARITH_EXPANSION token and a separate path),
  which is why the bug hid; the combinator parser was already correct.
- Found by the 2026-06-21 ground-up appraisal
  (``docs/reviews/ground_up_appraisal_2026-06-21.md``, finding H2 — ~12 everyday
  idiom forms collapsed to this one locus). New regression tests
  (``tests/unit/expansion/test_arithmetic_command_form_dollar.py``) plus four
  bash-compared golden cases in ``tests/behavioral/golden_cases.yaml``.

## 0.514.0 (2026-06-21) - Lexer stops guessing ${...} token kind (reassessment 2026-06-20, #2)
- REFACTOR (lexer; zero behavior change). The lexer classified a braced
  ``${...}`` as a ``VARIABLE`` or ``PARAM_EXPANSION`` token by scanning the whole
  text for operator substrings (``:-``, ``#``, ``/``, ...) — a heuristic the code
  itself labelled "FRAGILE" (``${x:-a/b}`` false-matched ``/``) and which was
  redundant: the parser's ``WordBuilder`` re-classifies a braced value precisely
  anyway (simple name → ``VariableExpansion``; operators → the shared
  ``param_parser``). The lexer now emits ONE ``VARIABLE`` token for every
  ``$``-variable form (braced value = the ``{...}`` text); the WordBuilder owns the
  classification. The substring scan is deleted.
- A spike confirmed this is behavior-preserving: 0 parser/executor/conformance
  failures, AST shapes unchanged, bash parity verified; only 12 lexer token-shape
  assertions (which pinned the old token kind) needed updating to the new contract.
- The ``PARAM_EXPANSION`` token type is now emit-dead (kept for the parser's
  acceptance lists); retiring it (and the combinator-parser matchers + the
  WordBuilder branch) is a documented follow-up.
- TESTS: updated `test_expansion_tokens.py` / `test_tokenizer_migration.py` to the
  new contract (braced ``${...}`` → one ``VARIABLE`` token, value ``{...}``); the
  precise classification stays covered by `test_param_parser.py`. Full suite green,
  ruff + mypy clean.

## 0.513.0 (2026-06-21) - Parser sub-parsers share a formal ParserSubcomponent base (reassessment 2026-06-20, #4)
- REFACTOR (parser; zero behavior change). The 8 recursive-descent sub-parsers
  (statements/commands/control_structures/tests/arithmetic/functions/redirections/
  arrays) followed an unwritten convention — each defined an identical
  ``__init__(self, main_parser)`` storing ``self.parser``. DECISION (the
  reassessment's #4 asked to make one and record it in code): formalize it with a
  ``ParserSubcomponent`` base (``recursive_descent/parsers/base.py``); all 8 now
  extend it and drop their duplicate ``__init__``.
- The base is deliberately minimal — it adds NO token-access delegation (no
  ``self.peek()`` forwarding); sub-parsers keep referencing ``self.parser.X``
  explicitly so the one shared ``Parser`` is always visible. The rationale lives
  in the base's module docstring (in code, not only in `CLAUDE.md`).
- Typing the base's ``main_parser: Parser`` (it was an untyped ``Any`` per
  sub-parser before) tightened ``self.parser`` to a concrete type, which surfaced
  a latent imprecision in ``functions.py`` (a subshell group / control structure —
  both ``CompoundCommand`` AND ``Statement`` at runtime — appended to a
  ``List[Statement]``); fixed with the same ``cast(Statement, …)`` the top-level
  parser already uses.
- TESTS: new ``tests/unit/parser/test_subparser_contract.py`` (all 8 extend the
  base, none re-rolls ``__init__``, the base stores the main parser, and it adds no
  token delegation). `psh/parser/CLAUDE.md` updated. Full suite green, ruff + mypy
  clean.

## 0.512.0 (2026-06-21) - Process-substitution fd ownership lives in RedirectPlan (reassessment 2026-06-20, #3)
- REFACTOR (io_redirect; zero behavior change). The in-process builtin redirect
  setup (`io_redirect/manager.py`) manually transferred a redirect-target process
  substitution's parent fd to the handler — `process_sub_handler.active_fds.append(...)`
  + nulling `plan.procsub.parent_fd` — while every other dispatch site used
  `plan.close_procsub(applied=)`. Two ownership models for the same resource.
- A redirect-target substitution's parent fd has exactly two fates, and both are
  now owned by `RedirectPlan`/`ProcessSubstitutionResource`:
  - **close after the redirect** — `close_procsub` → `close_parent_fd_for_redirect`
    (external/permanent paths, unless the dup2 made that fd the target); or
  - **hand to the enclosing `process_sub_scope()`** for deferred close — the NEW
    `RedirectPlan.hand_procsub_to_scope(handler)` → `ProcessSubstitutionResource.hand_off_to_scope()`
    (the builtin path, where the in-process builtin reads `/dev/fd/N`, and word
    expansion). `hand_off_to_scope` is now the SINGLE place that appends to
    `active_fds`; the word-expansion path (`create_for_expansion`) routes through
    it too, and `manager.py` no longer references `active_fds` at all.
- TESTS: new `tests/unit/io_redirect/test_procsub_ownership.py` (guards that
  `manager.py` doesn't poke `active_fds`, that the resource is the single
  appender, that `RedirectPlan` owns both transfer and close, and a builtin
  `< <(cmd)` fd-leak regression). Full suite green, ruff + mypy clean.

## 0.511.0 (2026-06-21) - Array-init handoff is an explicit BuiltinContext, not shell state (reassessment 2026-06-20, #1)
- REFACTOR (executor/builtins; zero behavior change). The structured array
  initializers the parser attaches to ``name=(...)`` arguments were delivered to
  the declaration builtins through a mutable shell side channel
  (``shell._pending_array_inits`` + ``set_/clear_/pending_array_init``, set/cleared
  around each builtin dispatch). The reassessment's #1 next step: make this an
  explicit parameter.
- NEW ``BuiltinContext`` (``psh/builtins/base.py``): a small per-invocation object
  carrying the array initializers (keyed by argv element). The executor builds it
  in ``CommandExecutor`` and threads it through ``execute_builtin_guarded`` to a
  new ``Builtin.execute_in_context`` hook; the default hook ignores it and calls
  ``execute()``, so ordinary builtins are untouched. The five declaration builtins
  (declare/typeset/local/export/readonly) override it and read
  ``context.array_init(arg)``. The ``export``→``declare`` and ``readonly``→``declare``
  delegations forward the same context explicitly (previously they relied on the
  shared shell map).
- The three side-channel methods and the ``_pending_array_inits`` field are
  removed from ``Shell`` — no mutable handoff state on the shell object. A spike
  confirmed the data flow is identical (``export e=(p q)`` etc. match bash).
- TESTS: new ``tests/unit/builtins/test_builtin_context.py`` (context lookup, the
  default-hook delegation, all five declaration builtins array-init via the
  context, and a guard that the shell side channel cannot be reintroduced). Full
  suite green, ruff + mypy clean.

## 0.510.0 (2026-06-21) - Command-position transition-table diagram (review 2026-06-18, Finding #5)
- DOCS. Closes the actionable part of the review's Finding #5. (The finding's
  refactor claims — "duplicated" command-position machines, "monolithic" literal
  recognizer — were overstated: the three machines already share one vocabulary
  module drift-locked by a test, and the literal recognizer already delegates to
  named scanners. What was genuinely missing was a single map of how the three
  command-position machines relate.)
- NEW `docs/architecture/command_position.md`: a pipeline-stage diagram plus a
  transition table for each of the three machines (cmdsub extent scanner, lexer
  pass, keyword normalizer), a table of the deliberate per-stage asymmetries
  between their vocabulary sets (the thing the review asked to make visible), and
  four worked examples (each verified against bash). Linked from
  `psh/lexer/CLAUDE.md` and the `command_position.py` module docstring, and added
  to the doc-pointer meta-test so its symbol/path references stay accurate.

## 0.509.0 (2026-06-20) - Curate docs for students: learning path + reviews index (review 2026-06-18, Finding #6)
- DOCS. Closes the 2026-06-18 review's Finding #6 ("curate the documentation set
  for students, not only maintainers") — a student no longer has to infer which
  documents are current.
- NEW `docs/learning_path.md`: the canonical reading route — README → run the
  `examples/` with the debug flags → `ARCHITECTURE.md` Quick Map → the end-to-end
  internals tour → the `Word` AST data-flow model → the per-subsystem `CLAUDE.md`
  notes → user guide / testing. Linked from `README.md` and `ARCHITECTURE.md`.
- NEW `docs/reviews/README.md`: a status index over the 40 review/design docs
  (Live / Completed / Historical), so the handful of live references stand out and
  the rest are clearly labeled development history (not a tutorial). Indexed in
  place rather than moved, to preserve the references from `CLAUDE.md`/`CHANGELOG`.
- `test_user_doc_links.py` now also guards `docs/learning_path.md` and
  `docs/reviews/README.md` (every backticked repo-path and Markdown link must
  resolve). Full suite green, ruff + mypy clean.

## 0.508.0 (2026-06-20) - Shell options: one registry, validated container (review 2026-06-18, Finding #4)
- REFACTOR (core; zero behavior change). `ShellState.options` was a bare 41-key
  `dict`, and "what options exist + how each behaves" was duplicated across the
  defaults dict (`state.py`), the `$-` letter map (`get_option_string`),
  `SetBuiltin.short_to_long`, and `ShoptBuiltin.SHOPT_OPTIONS`.
- NEW `psh/core/option_registry.py`: `OPTION_REGISTRY` is now the single source of
  truth (each option: default, value type, category, short flag, `$-` letter). The
  defaults, `SHORT_TO_LONG`, `SHOPT_OPTION_NAMES`, and the `$-` string are all
  derived from it; the duplicated maps in `state.py`/`environment.py`/
  `shell_options.py` are deleted.
- `ShellState.options` is now a `ShellOptions` — a registry-backed, dict-compatible
  (`MutableMapping`) container: the ~280 `state.options['key']`/`.get(...)` call
  sites are unchanged, but a write with an unregistered name now raises (typos fail
  loudly). A spike confirmed the swap is zero-call-site-churn and zero-behavior-change
  (full suite green); the reject-on-unknown policy proved the registry is complete
  (nothing writes an unregistered name). A few additive typed accessors
  (`options.errexit`, ...) were added for hot reads.
- The previously ad-hoc `command_mode` key (set in `__main__.py`, read by `$-`) is
  now a declared `INTERNAL` option.
- Note: this is NOT the "field-per-option dataclass" the review literally suggested —
  options are a dynamic, string-keyed surface (`set -o $name`, `shopt`, `$-`) with
  hyphenated names, so a registry-backed validated container is the right typed shape.
  Rationale recorded in `docs/reviews/options_typing_refactor_plan_2026-06-19.md`.
- TESTS: new `tests/unit/core/test_option_registry.py` (registry defaults/short-map/
  shopt-set/`$-`-order pins, ShellOptions dict-compatibility + reject-unknown, typed
  accessors, and a drift-lock enumerating the known option set). Full suite green,
  ruff + mypy clean.

## 0.507.0 (2026-06-19) - Unify top-level parsing onto one grammar path (review 2026-06-18, Finding #3)
- REFACTOR (parser; zero behavior change). `Parser._parse_top_level_item()` no
  longer special-cases control structures: it special-parsed a top-level
  `while`/`if`/`case`/... then hand-built `Pipeline`/`AndOrList` wrappers when one
  was followed by `|`/`&&`/`||`/`&` — a second grammar path for the same syntax.
  It now delegates to `parse_command_list`, so a control structure is just a
  pipeline component (`parse_pipeline_component`) like any other. `parser.py`
  builds no `Pipeline`/`AndOrList` by hand, and the now-dead
  `CommandParser.parse_pipeline_with_initial_component()` is deleted.
- Fixes an order-dependent grouping asymmetry: `while …; done; echo a` now groups
  the same as `echo a; while …; done` (one `CommandList` of two and-or lists);
  previously the former became `TopLevel[WhileLoop, CommandList]`.
- Root shape preserved (Option A): `_simplify_result` / the new
  `_bare_top_level_compound` keep the historical `TopLevel`-rooted shape for a
  program that is exactly one bare compound / function definition, so callers,
  the combinator-parity tests, and `$LINENO` stamping are unaffected. Spike
  measurement: the unwrap-free variant (everything `CommandList`) failed 18
  tests — 13 of them combinator-parity, because the combinator parser also emits
  unwrapped bare compounds — so preserving the shape is the low-cost path.
- Decision recorded in `docs/reviews/parser_top_level_control_structure_refactor_plan_2026-06-19.md`.
- TESTS: new `tests/unit/parser/test_top_level_control_structure_grammar.py` —
  root-shape characterization (bare compounds/function defs stay `TopLevel`;
  groups/simple commands stay `CommandList`), operator forms route through the
  normal and-or/pipeline machinery, the order-asymmetry regression, execution
  preservation (pipe/`&&`/`||`/background/redirection), and guardrails (parser.py
  builds no `Pipeline`/`AndOrList`; the special helper is gone). Full suite green,
  ruff + mypy clean.

## 0.506.0 (2026-06-19) - Subshell-style children no longer source rc files (review 2026-06-18, Finding #1)
- BEHAVIOR FIX (correctness + bash divergence). In an INTERACTIVE shell, a
  child shell built by `Shell.for_subshell(...)` whose stdin was still the
  parent tty looked interactive and sourced `~/.pshrc`. Two call sites passed
  `norc=False` (command substitution already used the `norc=True` default):
  - **Input process substitution `<(cmd)`** (`io_redirect/process_sub.py`): only
    stdout is rewired, so the child's stdin stayed the tty; worse, `run_child_shell`
    runs the pipe plumbing BEFORE building the child, so the rc file's output was
    captured INTO the substitution — `cat <(echo HI)` returned the user's `.pshrc`
    banner as data. (Both the input-pipe and write-FIFO paths fixed.)
  - **The `env CMD` builtin's in-process child** (`builtins/env_command.py`):
    `env echo hi` in an interactive shell sourced `~/.pshrc` once.
- bash sources rc once, at startup — never per subshell — but DOES keep the
  interactive flag in `$-` inside substitutions. Fix is `norc=True` at both
  sites (matching command substitution and `for_subshell`'s documented default):
  no rc sourcing, while `$-` still carries `i` inside `<(...)` (verified vs bash).
- Verified value-for-value vs bash (rc sourced 0× in the children; `$-` keeps
  `i`; `env X=1 sh -c 'echo $X'` still prints `1`).
- TESTS: new `tests/integration/test_interactive_child_rc_leak.py` (a tty-on-fd-0
  subprocess harness; asserts neither `<(cmd)` nor `env cmd` sources `~/.pshrc`,
  the substitution output isn't polluted, and `$-` keeps `i`). Confirmed to fail
  before the fix (rc sourced 3×) and pass after.

## 0.505.0 (2026-06-19) - Fix --format defects (control-structure indentation + lossy redirects)
- BEHAVIOR FIX (`psh --format` / `FormatterVisitor`). The formatter produced
  broken, sometimes non-re-parseable output. Found while adding runnable
  examples in v0.504.0. Fixes, with behavior-preservation pinned by new
  round-trip tests:
- Control-structure headers: `if`/`while`/`until` put the condition on its own
  line with a bare `then`/`do` (`if\n  cond\nthen`); now joined on one line
  (`if cond; then`, `while cond; do`), matching bash `declare -f`. `for`/C-style
  `for`/`select` likewise join `do` (`for x in …; do`).
- Nested indentation: every statement is wrapped `AndOrList → Pipeline → cmd`,
  and `visit_Pipeline` reset the indent to 0, stripped, then re-prepended indent
  to only the FIRST line — so a nested compound's inner lines (`else`/`fi`/
  `done`) collapsed to column 0. A single-command pipeline is now transparent
  (delegates to the command), preserving each block's indentation.
- Lossy redirects (formatted output silently changed/broke the script):
  - heredoc bodies were dropped entirely (`cat <<EOF` with no body/terminator);
    now emitted after the command (at column 0, where heredoc bodies must sit),
    including on compound commands (`while …; done <<EOF`) and groups;
  - a quoted heredoc delimiter `<<'EOF'` collapsed to `<<EOF` (re-enabling
    expansion); now preserved;
  - a quoted file target `> "my file"` lost its quotes (`>my file`); now formats
    the target Word with quoting;
  - a here-string `<<< "a b"` lost its quotes (`<<<a b`); now re-quoted.
  The 9 duplicated compound-redirect blocks are unified in one
  `_append_redirects` helper.
- BUGFIX (parser, pre-existing; surfaced by the above). `populate_heredoc_content`
  iterated a group node's `.statements` directly, but for a subshell/brace group
  that field is a `StatementList` wrapper, not a list — so `{ …; } <<EOF` (and
  `( … ) <<EOF`) raised `TypeError: 'StatementList' object is not iterable` at
  parse time, breaking BOTH execution and analysis. Now unwrapped like the
  sibling `commands` branch; `{ read a; read b; …; } <<EOF` matches bash.
- TESTS: new `tests/unit/visitor/test_formatter_roundtrip.py` (header shapes,
  nested-indent, idempotence, and behavior-preservation incl. heredocs/
  here-strings/quoted targets); updated the until-loop pin in
  `test_ast_coverage_matrix.py` to the corrected header.

## 0.504.0 (2026-06-19) - Doc-drift cleanup + runnable examples (review 2026-06-18, Finding #2)
- DOCS/TESTS (no production change). Acts on the highest-value finding of the
  2026-06-18 code/architecture/teaching-quality review: the first-contact docs
  were not as trustworthy as the internals (drifted stats, a referenced
  `examples/` tree that did not exist, a `tests/README.md` naming directories
  that were renamed away, and a testing doc that contradicted `CLAUDE.md`).
- NEW `examples/` tree — five curated, runnable, instructive scripts plus an
  index (`examples/README.md`): `shell_basics.sh` (expansion tour),
  `fibonacci.sh` (functions/recursion/iteration — the script the README's
  `--metrics` block prints), `control_structures.sh` (if/while/for/case, rich
  AST), `text_stats.sh` (a realistic `getopts`/`read`/`set -u` utility), and
  `security_demo.sh` (deliberately insecure input for `--security`/`--lint`).
  Every referenced analysis command was verified to produce the documented
  output; the flagship `fibonacci.sh` is `--validate`-clean.
- README: reconciled THREE conflicting test counts (`8,439` / `5,500+` /
  `4,235 passing`) — free-form mentions are now a rounded `8,400+`, the single
  machine-pinned exact count stays in Project Statistics; refreshed stale file
  counts (psh 229→238 files, tests 342→373 files) and the `--metrics` example
  block to real output; replaced the stale, 87-line "Recent Development"
  changelog dump (ended at v0.354, referenced the deleted
  `psh/expansion/arithmetic.py`) with a pointer to `CHANGELOG.md`/`docs/reviews/`.
- `docs/testing_source_of_truth.md`: rewritten to match reality — the gate is
  LOCAL (`run_tests.py --parallel` + `ruff` + `mypy`; per-PR CI disabled, nightly
  is a backstop), not the previously-claimed `run_tests.py --quick` "CI gate".
- `tests/README.md`: regenerated from the actual tree (it had named missing
  dirs/docs and omitted `behavioral/`, `framework/`, `parser_differential/`,
  `regression/`).
- NEW meta-tests in `tests/unit/tooling/`: `test_examples.py` (every example
  parses; the safe ones run clean; `--metrics` matches the README numbers;
  `--security` flags the demo) and `test_user_doc_links.py` (backticked
  repo-paths and Markdown links in README/tests-README/testing-doc/examples-README
  must resolve — the check the existing doc-pointer test skipped for these
  high-traffic docs, and which immediately caught the dead `arithmetic.py` link).

## 0.503.0 (2026-06-17) - [[ -v ]] on arrays tests element 0 (Tier R15.B)
- BUGFIX (test, reappraisal #13 MED). `[[ -v name ]]` / `test -v name` returned true whenever
  the array variable merely existed. bash's `-v name` on an array tests element 0
  (`-v name[0]`), so an EMPTY array — declared `declare -a a` or even assigned `=()` — is
  "unset", an indexed array with no `a[0]` (`a=([5]=z)`) is unset, and an associative array is
  keyed on `"0"`.
- Fix (`builtins/test_command.py` `variable_is_set`): for a bare array name, check element 0
  (index 0 / key "0") rather than the variable's existence. Scalars and explicit `name[key]`
  refs are unchanged.
- Verified value-for-value vs bash 5.2 (12 cases: declared/assigned-empty, populated, [5]-only,
  unset a[0], assoc key x vs 0, scalar set/unset, element present/absent, test-builtin form).
- TESTS: new `tests/conformance/bash/test_v_array_conformance.py` (12 cases).
- DEFERRED (separate, architectural, cosmetic): `declare -p` of a never-assigned array printing
  `declare -a a` vs an assigned-empty `declare -a a=()` needs an UNSET-array-state model (the
  item deferred since reappraisal #12).

## 0.502.0 (2026-06-17) - history word modifiers + quick substitution (Tier R15.B)
- FEATURE/BUGFIX (interactive, reappraisal #13 MED). History expansion now supports the `:`
  word modifiers and `^old^new` quick substitution; before, `!!:h`/`!!:s/...` etc. errored with
  "bad word specifier".
  - `:h` (head/dirname), `:t` (tail/basename), `:r` (root — remove `.suffix`), `:e` (ext) —
    operate on the whole selected text as a pathname and CHAIN (`:t:r`).
  - `:s/old/new/` (first match), `:gs/old/new/` global, any delimiter (`:s|o|0|`), `:&`
    (repeat the last substitution), chained subs.
  - `^old^new[^]` quick substitution on the previous command (`!!:s/old/new/`).
  - `:p` prints the expansion and suppresses execution (returns empty, like bash).
- Fix (`interactive/history_expansion.py`): `_apply_word_designator` now leaves a `:`-modifier
  for the new `apply_modifiers` engine instead of mis-parsing it as a (bad) word designator.
- Verified value-for-value vs bash's `history -p` across 19 modifier/quick-sub cases (pathname
  ops on slash/dot/leading-dot inputs, first/global/alt-delimiter subs, word-designator +
  modifier, chained subs, `^a^b`).
- TESTS: `tests/unit/interactive/test_history_modifiers.py` grew to 32 cases (+ `:p` print/
  no-execute, `:&` repeat, bad-modifier error). Completes R15.B item B6.

## 0.501.0 (2026-06-17) - history expansion in double quotes + backslash escape (Tier R15.B)
- BUGFIX (interactive, reappraisal #13 MED). History expansion (`!!`, `!n`, ...) was skipped
  inside double quotes and a backslash-escaped `!` was still expanded. bash expands `!` inside
  `"..."` (only single quotes and a preceding backslash suppress it).
- Fix (`interactive/history_expansion.py`): the scanner now tracks double-quote state instead of
  consuming `"..."` spans verbatim — `!` expands inside double quotes, a single quote inside
  `"..."` is literal (not a span start), single-quoted spans still suppress, and a backslash
  quotes the next char (`\!` is a literal `!`, no expansion; the backslash is kept, as bash's
  `history -p` does, and removed later by the lexer).
- Verified against bash's `history -p` (expand-and-print) as a live oracle across 10 cases:
  `echo "see !!"`, `echo "it's !!"`, `echo '!!'`, `echo \!!`, `echo "a\!b"`, `a!=b`, `${x} !!`.
- TESTS: new `tests/unit/interactive/test_history_modifiers.py` (10 parametrized cases vs
  `history -p`). Corrected a misleading comment in test_history_expansion_in_quotes (its
  non-interactive run has histexpand off, so it never exercised the quote path).

## 0.500.0 (2026-06-17) - prompts expand $()/$VAR/$(()) (Tier R15.B)
- BUGFIX (interactive, reappraisal #13 MED). PS1/PS2 (and the `${var@P}` operator) decoded only
  backslash escapes — `$(...)`, `$VAR`, and `$((...))` in a prompt were left literal. Now a prompt
  undergoes parameter / command / arithmetic expansion after escape decoding (bash's default
  `promptvars`), so `PS1='[\$(echo HI)]\$ '`... see below.
- Order & protection match bash (verified via `${var@P}`): escapes are decoded FIRST, then the
  `$`-pass runs, but escape output is PROTECTED — a `\$`-produced `$` does not start a command
  substitution (`\$(echo HI)` stays literal) and an escape's (or a variable's) value is not
  re-interpreted as a prompt escape (`X='\w'; PS1='$X'` → literal `\w`).
- Fix: `PromptExpander.expand_full` decodes escapes into protected/raw segments, replaces each
  escape-produced segment with a NUL sentinel, runs `expand_string_variables`, then restores the
  sentinels. PS1/PS2 (`prompt_manager`) AND the `@P` operator (`expansion/operators.py`) now share
  this one implementation, so they agree. A prompt expansion error never aborts the caller.
- TESTS: `tests/conformance/bash/test_prompt_expansion_conformance.py` (10 cases via `${var@P}`)
  + `tests/unit/interactive/test_prompt_dollar_expansion.py` (7 cases incl. the `\[`/`\]`
  readline markers, which `@P` omits).

## 0.499.0 (2026-06-16) - formatter preserves [[ ]] operand quoting (Tier R15.B)
- BUGFIX (formatter visitor, reappraisal #13 MED). `--format` dropped quoting on `[[ ]]` binary
  test operands because it emitted the derived (unquoted) display strings (`node.left`/`.right`)
  instead of the operand Words. This CHANGED MEANING: `[[ $x == "*.txt" ]]` (literal compare)
  became `[[ $x == *.txt ]]` (glob match), and `[[ $x == "a b" ]]` no longer re-parsed.
- Fix (`visitor/formatter_visitor.py` `visit_BinaryTestExpression`): format the operand Word
  nodes (`left_word`/`right_word`, which carry per-part quote context) via `_format_word`, so
  quotes are preserved and the output round-trips. Unary test operands are stored only as plain
  strings (no Word/quote context), but inside `[[ ]]` operands are not word-split, so a dropped
  quote there is cosmetic, not semantic (documented).
- TESTS: new `tests/unit/visitor/test_formatter_test_quoting.py` (7 cases, incl. round-trip
  stability).

## 0.498.0 (2026-06-16) - set -e brace-group exemption (Tier R15.B)
- BUGFIX (executor, reappraisal #13 MED). Under `set -e`, a brace group whose last statement
  was an `&&`/`||` list with an exempt failing member wrongly aborted: `set -e; { false && true; }`
  exited 1 instead of continuing. A brace group `{ ...; }` is TRANSPARENT to errexit — the
  exemption of a non-final `&&`/`||` member inside it carries out — but `visit_AndOrList`
  re-marked the whole single-member group eligible, clobbering the inner exemption.
- Fix (`executor/core.py`): `run_pipeline` now preserves the errexit eligibility the brace
  group's body established (via a new `_pipeline_is_brace_group` helper) instead of re-setting
  it. Subshells `( )` and functions are NOT transparent (a fresh errexit context — only the
  final status counts) and still abort, matching bash. The ERR trap fires under exactly the
  same conditions.
- Verified value-for-value vs bash 5.2 across a 14-case battery (subshell/function still abort,
  nested braces, ERR-trap exempt/fires, brace-then-real-failure, brace in a pipeline).
- TESTS: new `tests/conformance/bash/test_errexit_brace_group_conformance.py` (12 cases).

## 0.497.0 (2026-06-16) - read mixed-IFS field splitting (Tier R15.B)
- BUGFIX (read, reappraisal #13 MED). With a MIXED IFS (whitespace + non-whitespace), `read`
  did not fold IFS whitespace adjacent to a non-whitespace delimiter into one delimiter, so it
  emitted a spurious empty field: `IFS=": "` on `a : b` gave `[a, '', b]` instead of `[a, b]`.
  (psh's general word-splitter was already correct; only `read`'s splitter was wrong.)
- Fix (`builtins/read_builtin.py` `_split_with_ifs`): rewrote to the POSIX algorithm — a single
  delimiter is a run of IFS whitespace with at most ONE embedded IFS non-whitespace character,
  so whitespace is absorbed on both sides of a non-ws delimiter. Leading/doubled non-ws
  delimiters still produce empty fields (`:x`→['',x]; `x::y`→[x,'',y]); a trailing one does not
  (`x:`→[x]); pure-whitespace runs and leading/trailing whitespace trimming are unchanged.
- Verified value-for-value vs bash 5.2 across a 15-case battery (key:value, comma-space CSV,
  tabs, read -a counts, leftover-to-last-var, backslash protection).
- TESTS: new `tests/conformance/bash/test_read_ifs_split_conformance.py` (12 cases).
- KNOWN pre-existing (unchanged, out of scope): `read -a a <<< ":"` yields 0 fields vs bash 1
  (a single-empty-field `read -a` edge predating this fix).

## 0.496.0 (2026-06-16) - exec-failure messages match bash strerror (Tier R15.B)
- BUGFIX (executor, reappraisal #13 MED). A failed exec leaked Python's OSError repr —
  `psh: ./x: [Errno 13] Permission denied: './x'` — where bash prints the bare strerror
  `./x: Permission denied`. `report_exec_failure` (strategies.py) now emits `exc.strerror`
  (falling back to `str(exc)`), and special-cases a directory target as "Is a directory"
  (exec of a directory returns EACCES on macOS, but bash reports EISDIR). Exit codes are
  unchanged (126 not-executable / 127 not-found).
- Verified vs bash 5.2 (exit code + stderr substring; the `bash: line N:` prefix differs from
  psh's by design, and psh no longer leaks the `[Errno N] ...: '...'` repr).
- TESTS: new `tests/conformance/bash/test_exec_error_message_conformance.py` (3 cases).

## 0.495.0 (2026-06-16) - echo has no --, type prints function body (Tier R15.B)
- BUGFIX (echo, reappraisal #13 MED). bash's `echo` has NO `--` option terminator; psh treated
  `--` as end-of-options and dropped it, so `echo -- hi` printed `hi` instead of `-- hi`. Removed
  the `--` handling from echo's flag scan (io.py) — only -n/-e/-E (and clusters) are flags, and
  the first non-flag argument (including `--`) ends scanning and prints literally.
- BUGFIX (type, reappraisal #13 MED). `type <function>` printed only "NAME is a function" (a
  literal TODO), not the body. It now prints the body via the same `ShellFormatter` path
  `command -V` uses (type_builtin.py), so `type f` and `command -V f` agree. (psh's function-
  print brace placement still differs from bash's — a separate, pre-existing cosmetic shared by
  `command -V`/`declare -f`.)
- TESTS: `tests/conformance/bash/test_echo_double_dash_conformance.py` (echo `--`, value-for-value
  vs bash) + `tests/unit/builtins/test_type_function_body.py` (body content + consistency with
  `command -V`). Updated `test_echo_double_dash` which pinned the old (non-bash) `--`-as-terminator
  behavior, after re-verifying against bash 5.2.

## 0.494.0 (2026-06-16) - wait no-operand returns 0 + unset function fallback (Tier R15.A — standalones)
- BUGFIX (job control, reappraisal #13 HIGH). `wait` with no operands returned the last
  background job's exit status, so a failing background job leaked into `$?` and broke the
  common `cmd & …; wait; <check $?>` idiom (`(exit 42) & wait; echo $?` gave 42). POSIX/bash:
  a no-operand `wait` returns 0 once all children finish. Fix (`builtins/job_control.py`
  `_wait_for_all`): still reap/clean up every job, but return 0; only the operand form
  `wait PID`/`wait %job` reports a waited job's status (unchanged). Two existing tests pinned
  the old (non-bash) behavior and were updated after re-verifying against bash 5.2.
- BUGFIX (unset, reappraisal #13 HIGH). A bare `unset NAME` (no -v/-f) only ever unset a
  variable; it never fell back to unsetting a FUNCTION of that name (`f(){ :; }; unset f` left
  `f` callable). bash: `unset NAME` unsets the variable if one exists, else the function. Fix
  (`builtins/environment.py`): in the no-flag path, when no variable (or env entry) exists but
  a function does, undefine the function. An explicit `-v` restricts to variables (never falls
  back), and a variable still wins when both a variable and a function share the name.
- Verified value-for-value vs bash 5.2 (11 conformance cases). This is the LAST batch of Tier
  R15.A — every HIGH bug from reappraisal #13 is now fixed.
- TESTS: new `tests/conformance/bash/test_wait_unset_conformance.py` (11 cases).

## 0.493.0 (2026-06-16) - case attributes on array elements (Tier R15.A — attribute uniformity)
- BUGFIX (executor, reappraisal #13). The uppercase (-u) / lowercase (-l) attribute was applied
  to scalar writes and the integer (-i) attribute was applied to array elements, but case
  folding was NOT applied to array ELEMENT writes: `declare -au a; a[0]=foo` left `foo` instead
  of `FOO` (and `declare -al a; a[0]=HELLO` left `HELLO` instead of `hello`).
- Fix (`executor/array.py` `_compute_element_value`): after the integer/append computation,
  fold the element by the variable's UPPERCASE/LOWERCASE attribute — exactly like a scalar
  write. Integer (-i) still takes precedence (numeric value), `+=` folds the whole concatenated
  element, and array INITIALIZATION (which already folded) plus scalars are unchanged.
- Verified value-for-value vs bash 5.2: indexed/associative -u/-l element writes, -u append,
  -i precedence, -u/-l initializers, and the no-attribute case.
- TESTS: new `tests/conformance/bash/test_array_case_attr_conformance.py` (9 cases).
- This completes the R15.A attribute-uniformity cluster (set -u array elements v0.490,
  declare -a/-A content v0.491, array nameref += v0.492, case attrs here).

## 0.492.0 (2026-06-16) - array nameref += appends (Tier R15.A — attribute uniformity)
- BUGFIX (executor, reappraisal #13 HIGH). Whole-array append through a nameref replaced the
  target instead of appending: `a=(1 2 3); declare -n r=a; r+=(4)` gave `a=([0]="4")` instead
  of `([0]="1" [1]="2" [2]="3" [3]="4")`. `execute_array_initialization` used `node.name` (the
  nameref `r`) for the existing-contents lookup — whose value is the target NAME string, not an
  array — so `+=` started from a fresh array; the WRITE resolved the nameref, so the fresh
  array landed on the target.
- Fix (`executor/array.py`): resolve the nameref target up front (with cycle handling, the same
  pattern the element-write path already uses) and use the resolved name for both the existing-
  contents read and the write. The readonly-array error now names the variable as written (the
  nameref), matching bash.
- Verified value-for-value vs bash 5.2: indexed/associative append through a nameref appends;
  whole-array replace (`r=(...)`), element write (`r[i]=`), append to an empty target, and
  plain non-nameref append are unchanged.
- TESTS: new `tests/conformance/bash/test_nameref_array_append_conformance.py` (8 cases).
- KNOWN follow-up (separate code path, not this fix): scalar append through a nameref
  (`s=hi; declare -n r=s; r+=more`) does not resolve the target either — it goes through
  `resolve_append_assignment` in command_assignments, to be addressed separately.

## 0.491.0 (2026-06-16) - declare -a/-A preserves content (Tier R15.A — attribute uniformity)
- BUGFIX (declare/typeset, reappraisal #13 HIGH). A bare `declare -a`/`-A` installed a fresh
  EMPTY array, so it both DISCARDED an existing scalar's value (`x=foo; declare -a x` gave
  `()` instead of `([0]="foo")`) and WIPED an existing array's elements on re-declaration
  (`a=(1 2 3); declare -a a` gave `()`).
- Fix (`builtins/function_support.py` `_declare_bare_name`): match bash's actual rules —
  re-declaring an existing array (indexed or associative) keeps its elements; converting a
  GLOBAL scalar preserves its value at index 0 / key "0". Scoping is honored via two new
  helpers (`_existing_in_target_scope`, `_declare_target_is_local`): a bare `declare -a` in a
  function creates a fresh LOCAL array without pulling in an outer-scope variable, and a
  function-local scalar is NOT preserved (bash empties it) — only a global scalar is.
- Verified value-for-value vs bash 5.2: global scalar→indexed/assoc preserved (incl. empty
  string and integer attr); re-declared indexed/assoc arrays (local + global) keep contents;
  local scalar emptied; bare declare in a function doesn't capture an outer scalar.
- TESTS: new `tests/conformance/bash/test_declare_array_convert_conformance.py` (11 cases;
  empty-array cases checked by value, since rendering a never-assigned array as `declare -a a`
  vs `declare -a a=()` is a separate, still-open difference).

## 0.490.0 (2026-06-16) - set -u for array elements (Tier R15.A — attribute uniformity)
- BUGFIX (expansion, reappraisal #13 HIGH). `set -u` (nounset) was not enforced for array
  element reads: a bare `${arr[i]}` / `${arr[key]}` on an ABSENT element returned '' with
  exit 0, where bash errors `arr[idx]: unbound variable`. This is the array analog of the
  scalar `${var}` nounset bug fixed in v0.480 — the scalar path checked nounset, the array
  element path did not.
- Fix: `_expand_array_subscript` (expansion/arrays.py) now raises `UnboundVariableError`
  (`arr[idx]: unbound variable`) for an absent element when nounset is set — gated by a
  `check_nounset` flag that is True only for the BARE form. The value-substituting operator
  forms (`${a[i]:-d}`, `${a[i]:+s}`) and the length form (`${#a[i]}`) reuse the same evaluator
  to fetch the base value and stay exempt (False), and `${a[@]}`/`${a[*]}` on an unset array
  remain non-erroring — all matching bash.
- Verified value-for-value vs bash 5.2 (14 cases): absent indexed/assoc element errors with the
  right exit code; present (incl. empty) elements read fine; operator/length/whole-array forms
  exempt; no error without nounset.
- TESTS: new `tests/conformance/bash/test_nounset_array_conformance.py` (14 cases).

## 0.489.0 (2026-06-16) - analysis modes parse heredocs (Tier R15.A — heredoc cluster, visitors)
- BUGFIX (analysis modes, reappraisal #13 HIGH). The CLI analysis modes (`--validate`,
  `--format`, `--metrics`, `--security`, `--lint`) parsed input with a bare tokenize/parse
  that skips heredoc collection, so a heredoc BODY was analyzed as separate shell commands.
  A script with `rm -rf /` inside heredoc DATA was reported as a HIGH security risk (false
  positive); `--metrics` inflated command counts; `--validate` flagged heredoc-body variables
  as undefined.
- Fix: `scripting/visitor_modes.py` gains `_parse_for_analysis()`, which tokenizes/parses WITH
  heredoc collection (`tokenize_with_heredocs` + `parse_with_heredocs`) when the input contains
  a heredoc — mirroring the execution path — so a heredoc body is attached to its redirect.
  Both analysis entry points (`-c` command and script file) route through it.
- Verified: `--security` on a heredoc whose body is `rm -rf /` now reports no issues; `--metrics`
  counts only the real commands; a REAL `rm -rf /` (not in a heredoc) still flags. Completes
  the R15.A heredoc cluster (lexer + oracle landed in v0.488.0; this is the analysis half).
- TESTS: new `tests/system/test_visitor_heredoc.py` (4 cases, real CLI entry points).

## 0.488.0 (2026-06-16) - heredoc delimiter recognition (Tier R15.A — heredoc cluster, lexer + oracle)
- BUGFIX (lexer + completeness oracle, reappraisal #13). Escaped/quoted heredoc delimiters
  were mis-handled, and the terminator match was too loose:
  - `<<\EOF` (and `<<-\EOF`, `<<EO\F`) recorded the delimiter verbatim WITH the backslash,
    so the body terminator `EOF` never matched — the heredoc swallowed everything to EOF and
    produced EMPTY output. The backslash should quote the delimiter (literal body) and be
    removed. (real-lexer bug)
  - `<<"E F"` (a quoted delimiter containing a non-word char) was not recognized by the
    line-gathering completeness oracle (its regex captured only `\w+`), so the heredoc body
    was fed to the shell as separate commands. (oracle bug — the real lexer handled it)
  - the terminator line was compared after `.rstrip()`, so a body line like `EOF ` (trailing
    whitespace) wrongly ended the heredoc; bash requires an EXACT match (only `<<-` strips
    leading tabs).
- Fix: a new `lexer.heredoc_lexer.normalize_heredoc_delimiter()` recovers the literal
  delimiter text + quoted flag from the delimiter token (`\EOF`/`EO\F` → `EOF` quoted;
  `"E F"`/`'EOF'` → contents, quoted). The oracle's `HEREDOC_MARKER_RE` now captures the full
  delimiter (word chars, backslash escapes, and quoted segments) with a matching
  `heredoc_delimiter_word()` normalizer. Both the real lexer (`heredoc_collector`) and the
  oracle (`heredoc_detection`) compare the terminator EXACTLY (only `<<-` strips leading tabs).
- Verified value-for-value vs bash 5.2: `<<\EOF`, `<<-\EOF`, `<<EO\F`, `<<"E F"`, `<<'EOF'`,
  `<<"EOF"` all literal; trailing-whitespace terminator is body; plain `<<EOF` still expands;
  pipes/strip-tabs unaffected. 207 existing heredoc/detection tests still pass.
- TESTS: new `tests/conformance/bash/test_heredoc_delimiter_conformance.py` (10 cases).
- KNOWN limitation (rare, documented): a COMPOSITE multi-token delimiter spliced from quote
  segments in an unquoted word (`<<E"O"F`) is still not recovered — the parser consumes only
  one delimiter token. All single-token spellings work.

## 0.487.0 (2026-06-16) - trap signal-spec normalization (Tier R15.A — trap cluster)
- BUGFIX (trap, reappraisal #13 — two HIGH bugs). `trap` keyed handlers by the raw user
  spec, while the signal dispatch (SignalManager) looks them up by canonical name, so:
  (1) `trap 'cleanup' SIGINT` — the most common trap idiom — was REJECTED with "invalid
  signal specification" (the map keys are bare names like INT, and `int("SIGINT")` fails);
  (2) `trap 'handler' 2` (or 15/1/3) for a MANAGED signal (INT/TERM/HUP/QUIT) was accepted
  but NEVER FIRED — the shell died on the default action — because the handler was stored
  under key "2" while dispatch looked up `signal_names[2]` → "INT".
- Fix: a single `TrapManager._canonical_signal_key(spec)` resolves a `SIG`-prefixed name,
  a number, or a bare name to the one canonical key (the bare signal name, e.g. INT), used
  by `set_trap` (storage) and `show_traps` (queries). So `SIGINT`, `INT`, and `2` set, fire,
  and query interchangeably, and `trap -p SIGINT` / `trap -p 2` now find a trap set on INT.
- Verified value-for-value vs bash 5.2 (11 cases): SIG-prefixed names accepted (SIGINT,
  SIGUSR1, SIGTERM); numbered managed traps 2/15 fire; `trap -p` query by SIG-name / number /
  bare name; reset-then-query. `trap RETURN` still errors (psh does not implement RETURN
  traps — a documented, pinned limitation) and an unknown signal is still rejected.
- TESTS: new `tests/conformance/bash/test_trap_signal_spec_conformance.py` (11 cases).

## 0.486.0 (2026-06-16) - $LINENO in eval and trap actions (Tier R15.A — nested execution)
- BUGFIX (scripting, reappraisal #13 HIGH). `$LINENO` inside `eval` and inside DEBUG/ERR
  trap actions reset to 1 instead of anchoring at the invoking command's line. `eval` on
  line 3 reported 1/2 instead of 3/4; `trap 'echo at $LINENO' ERR` reported `at 1` instead
  of the failing command's line. Root cause: `eval`/trap actions run via `Shell.run_command`,
  whose `StringInput("<command>")` line counter always started at 1, so the per-statement
  absolute-line offset (v0.485) never fired for nested execution.
- This also corrects a FALSE POSITIVE in the v0.485 test suite: the eval `$LINENO`
  conformance case ran eval on line 1 (offset 0), so it passed by luck while the bug shipped.
- Fix: `Shell.run_command`/`ScriptManager.execute_from_source` gain a `base_line` parameter
  (default 1 = a fresh context, unchanged for normal sources). `eval` and ERR/DEBUG trap
  actions pass `scope_manager.get_current_line_number()`, so the nested text's line 1 anchors
  at the invoking command's line and subsequent lines increment from there — matching bash.
- Trap semantics verified value-for-value vs bash 5.2: ERR/DEBUG (synchronous, tied to a
  command) anchor at the current command line; EXIT and signal traps (asynchronous, no
  invoking command) count from the action's own line 1 — so those keep reporting 1, unchanged.
- TESTS: +7 conformance cases — eval at line 1 / eval anchored at the invoking line / eval
  multi-line string / eval inside a function, and a new `TestLinenoTrapConformance` (ERR,
  DEBUG, EXIT single + multi-line action). The old single-line-1 eval case was replaced.
- KNOWN remaining (separate, pre-existing — NOT this fix): the ERR trap fires INSIDE functions
  in psh (reporting a function-body line) where bash without `errtrace` fires it for the
  failing call-site command; command substitution still does not inherit the enclosing line.

## 0.485.0 (2026-06-16) - $LINENO per statement (absolute source lines)
- BUGFIX (scripting). `$LINENO` was set ONCE per buffered command to the construct's
  START line, so it was wrong in EVERY multi-line construct: statements inside
  `if`/`for`/`while`/`until`/`case` bodies, brace/subshell groups, and later pipelines
  of a multi-line `&&`/`||` chain all reported the construct's first line; statements
  inside a function reported the CALL-SITE line instead of the definition line; `-c`
  multi-line text, `eval`, and `source` were similarly off. Now each statement carries
  its absolute source line and `$LINENO` is re-stamped per statement (and per pipeline
  in an and-or chain) right before it runs. Verified value-for-value against bash 5.2.
- Mechanism: `ASTNode` gains an inert `line` class attribute (not a dataclass field —
  AST equality/repr are unaffected). The recursive-descent parser stamps each statement
  and pipeline with its first token's (buffer-relative) line; the source processor offsets
  those to absolute file/`-c`/`eval` lines once per buffer, recursing into function bodies
  so a body bakes in its DEFINITION-site lines (a call-site base would be wrong — a
  function defined in one buffer and called from another must report its def lines). The
  executor re-stamps `$LINENO` per statement in `visit_StatementList`/`visit_TopLevel`
  and per pipeline in `visit_AndOrList`; `source`/function-return restoration of `$LINENO`
  to the caller's line then falls out for free (the next statement re-stamps).
- Function `$LINENO` is now constant across call sites, `LINENO=N` reassignment still
  tracks from N, and `$((LINENO))` agrees — all matching bash.
- TESTS: 29 new (first-ever `$LINENO` coverage) — `tests/conformance/bash/
  test_lineno_conformance.py` (25 cases vs live bash: top-level, all compounds, and-or
  chains, function def-site, nested/mutually-recursive functions, eval, source
  reset+restore, reassignment) and `tests/system/test_lineno_script_file.py` (4 cases
  pinning the FileInput path incl. shebang-comment line accounting).
- KNOWN remaining divergences (pre-existing, orthogonal, NOT fixed here): command
  substitution does not inherit the enclosing line (`x=$(echo $LINENO)` → psh 1, bash 2);
  the physical line counter under-counts after a backslash-newline line continuation
  (continuations are collapsed before line counting). The combinator parser (educational)
  does not stamp lines, so `$LINENO` there falls back to the buffer's start line.

## 0.484.0 (2026-06-16) - Tier R14.C: dedup — visitor world-writable check + RD arith helper
- BUGFIX (analysis) + DEDUP. The `EnhancedValidatorVisitor` chmod check was a substring
  scan (`777`/`666`/`a+w`/`o+w`) that MISSED most world-writable octal modes (757, 776,
  737, ...). It now shares a single `is_world_writable_permission` helper (constants.py)
  with `SecurityVisitor` — an octal mode is world-writable iff the other-write bit is set in
  its last digit. Both visitors now flag the same set; the permission logic is single-sourced.
- DEDUP. The recursive-descent arithmetic parser defined the `))` stop-condition closure
  identically in two methods; extracted to one `_double_rparen_stop(stream)` helper.
- Found by reappraisal #12 (carry-over dedup items). Tier R14.C, batch 2. +1 test.
- Completes Tier R14.C.

## 0.483.0 (2026-06-16) - Tier R14.C: complete the mypy scope (truth-up) + docs + xfail_strict
- TYPING. `check_untyped_defs` / the mypy `files` scope now genuinely covers the WHOLE
  `psh/` tree (238/238 files). R13.C's "tree-complete" claim was overstated — four live
  modules sat outside scope: `parser/combinators/arrays.py` (which had 9 real type errors,
  now fixed via None-narrowing asserts, a `cast` around `ParseResult`'s invariance, and
  typed `words`/`parts` lists), `parser/combinators/diagnostics.py`,
  `expansion/brace_expansion_tokens.py`, `expansion/word_expansion_types.py`. Zero behavior
  change. Caught by reappraisal #12.
- DOCS. Corrected the CLAUDE.md type-checking section (it referenced the long-gone
  `psh/ast_nodes.py`, described the scope as "core/ + a few modules", and claimed "CI
  enforces it" when per-PR CI is disabled). Documented the macOS-local-gate vs Linux-nightly
  platform gap in "Known Test Issues" (the v0.472 RT-signal bug is the canonical case).
- TESTS. Enabled `xfail_strict = true`: a strict-xfail that unexpectedly XPASSES now fails
  the suite, so a feature implemented behind an xfail auto-flags its stale marker.
- Tier R14.C (typing/hygiene truth-up), batch 1.

## 0.482.0 (2026-06-16) - Tier R14.B (interactive): transpose-chars + Ctrl-U match readline
- BUGFIX (behavior). Ctrl-T (`transpose-chars`) now matches readline/bash: it drags the
  character BEFORE point forward over the character AT point and advances point (`abc` with
  point at 1 → `bac`, point 2); at end-of-line it transposes the two characters before point
  (`abc`→`acb`); at beginning-of-line it is a no-op (readline rings the bell). psh previously
  swapped the char at point with the next one and mishandled the BOL case.
- BUGFIX (behavior). Ctrl-U is now `unix-line-discard` (kill from the cursor back to the
  start of the line, KEEPING the text after the cursor), matching bash; it was bound to
  kill-whole-line. New `EditBuffer.kill_to_beginning()`; rebound in both emacs and vi-insert.
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 6. Updated the 2 tests
  that pinned the old transpose behavior; +3 tests.

## 0.481.0 (2026-06-16) - Tier R14.B (executor): break 0 / continue 0 exit all loops, status 1
- BUGFIX (behavior). `break 0`, `continue 0`, and negative counts now report "loop count
  out of range" AND exit ALL enclosing loops with status 1, matching bash. Previously psh
  exited only ONE loop and left status 0. `LoopBreak` gained an optional `exit_status`
  (None for ordinary breaks, which keep the body status); the out-of-range case raises
  `LoopBreak(loop_depth, exit_status=1)` so it propagates through every enclosing loop and
  the loop reports 1.
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 5. Updated the two R13
  tests that pinned the old one-level/status-0 behavior + added a nested-loops test.

## 0.480.0 (2026-06-16) - Tier R14.B (expansion): set -u operators + ${arr[i<<j]} heredoc misdetect
- BUGFIX (behavior). `set -u` (nounset) is now enforced for VALUE-substituting parameter
  operators on an unset variable, matching bash: `${#x}`, `${x#p}`, `${x%p}`, `${x/a/b}`,
  `${x^^}`, `${x,,}`, `${x:0:1}`, `${x@Q}`, etc. all raise "unbound variable" (exit 127)
  when `x` is unset. The set-testing operators (`${x-d}`, `${x:-d}`, `${x=d}`, `${x:=d}`,
  `${x+d}`, `${x:+d}`) remain exempt, a set-but-empty variable is fine, and an unset ARRAY
  ELEMENT (`${#arr[5]}`) stays exempt (bash's deliberate exception). Previously nounset was
  only checked on the plain `${x}` form, so every operator form silently treated unset as
  empty — this also backs the user-guide "set -u | Full support" claim with a proving test.
- BUGFIX (behavior). `${arr[i<<j]}` (a left-shift in an arithmetic array subscript) was
  misdetected as a heredoc operator by the line gatherer, silently swallowing the rest of
  the input. `is_inside_expansion` now recognizes `${...}` parameter expansions (with brace
  nesting), so `<<`/`>>` inside a subscript are arithmetic, not heredocs.
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 4. +13 tests.

## 0.479.0 (2026-06-16) - Tier R14.B (core): declare -i error propagation + declare -p assoc re-parseable
- BUGFIX (behavior). An `-i` (integer) assignment with a malformed RHS or division by zero
  now FAILS with the arithmetic-error message and status 1, instead of silently storing 0.
  `declare -i n; n=1/0` → error + exit 1 (was `n=0`, exit 0); `n=2+` likewise. The integer
  evaluator stopped swallowing `ShellArithmeticError`, so the `-i` path now behaves exactly
  like `$((...))`. An undefined variable (`n=abc`) still resolves to 0 (not an error), matching bash.
- BUGFIX (behavior). `declare -p` of an associative array is now re-parseable: keys that need
  quoting (spaces, `$`, etc.) are double-quoted with escaping (`["a b"]="v"`) — a bare
  `[a b]=` was not re-parseable — and bash's trailing space before `)` is emitted. Simple keys
  (`x`, `a.b`, `1`) stay bare, matching bash. (psh iterates keys sorted; bash uses hash order —
  an accepted deterministic divergence, so multi-key output is verified by round-trip.)
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 3. +8 tests.
- DEFERRED (separate follow-up): an associative-array key containing a literal `=` or `]`
  (`m["a=b"]=v`) is mis-split at parse time — the lexer's subscript map is correct, but a
  parser consumer splits on the inner `=`. Needs parser-level array-element-assignment work.

## 0.478.0 (2026-06-16) - Tier R14.B: history -c no longer drops post-clear commands
- BUGFIX (behavior). `history -c` cleared `state.history` directly, leaving the
  HistoryManager's file-sync marker (`_file_synced_len`) stale. Commands added AFTER the
  clear then fell outside the save slice (`history[_file_synced_len:]`) and were silently
  dropped from HISTFILE — data loss. The builtin now routes through
  `HistoryManager.clear_history()`, which resets the marker, so post-clear commands persist.
  (Same stale-index class as the v0.447 trim-path bug; the `-c` path was the remaining gap.)
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 2. +1 regression test.

## 0.477.0 (2026-06-16) - Tier R14.B: -c name args $0 + non-UTF-8 script no longer crashes
- BUGFIX (behavior). `psh -c COMMAND name arg1 arg2` now follows POSIX: the first operand
  after the command string is `$0` (the command name), and the rest are `$1`, `$2`, …
  (`-c '...' myname a b` → `$0=myname`, `$1=a`, `$#=2`). Previously psh made the name `$1`,
  corrupting `$0`/`$@`/`$#` together and breaking the `sh -c '...' progname` idiom.
- BUGFIX (robustness). A script containing a non-UTF-8 byte no longer crashes psh with an
  uncaught `UnicodeDecodeError` traceback (which also tripped the strict-errors guard).
  Script files are read with `errors='surrogateescape'` and the command-not-found
  diagnostic encodes leniently, so a stray byte becomes a clean "command not found" and
  execution continues — matching bash structurally (both run the surrounding commands,
  exit 0; only the byte's rendering differs, `$'\351'` vs the raw byte).
- Found by reappraisal #12. Tier R14.B (correctness cluster), batch 1. +3 tests.

## 0.476.0 (2026-06-16) - Tier R14.A: getopts positional-clobber fix + read -u/-t 0 (R14.A complete)
- BUGFIX (behavior). `getopts` no longer corrupts the positional parameters while parsing a
  clustered option. The old code rewrote `argv[i]` in place to track cluster progress, which
  aliased `state.positional_params` and left `$1` as `-bc` after `set -- -abc; getopts ab o`.
  The within-cluster character position is now tracked out-of-band on `ShellState` (like the
  shell's internal getopts cursor), so a cluster spans calls without mutating `$1..$n`.
- FEATURE. `read -u FD` reads from file descriptor FD (bash); an invalid spec or unopened fd
  reports an error with status 1.
- FEATURE. `read -t 0` is a non-consuming poll: status 0 if the fd is readable (data ready or
  at EOF), 1 if a read would block. Reads nothing, assigns no variables.
- Found by reappraisal #12. Completes Tier R14.A (the common-idiom Builtins cluster). +8 tests.
- KNOWN (separate, pre-existing, NOT R14.A): here-strings/heredocs redirected to an explicit
  non-zero fd (`3<<<x`, `exec 3<<<x`) do not materialize that fd — affects external commands
  too; `read -u 3` works with file-backed fds (`exec 3< file`). Noted for a future tier.

## 0.475.0 (2026-06-16) - Tier R14.A: exit status semantics + cd -L/-P
- BUGFIX (behavior). `exit` now matches bash on three points: (a) bare `exit` uses `$?`
  (the last command's status), not 0 — `false; exit` now exits 1; (b) a numeric argument
  wraps modulo 256 (`exit 257`→1, `exit -1`→255, `exit 300`→44) instead of erroring on
  out-of-range; (c) too many arguments reports "too many arguments" and does NOT terminate
  the shell (status 1, execution continues). A non-numeric argument still errors + exits 2.
- BUGFIX (behavior). `cd` now accepts the `-L` (logical, default) / `-P` (physical) options
  — previously a leading `-P`/`-L` was treated as a directory operand (`cd: -P: No such
  file or directory`). `cd -P` records the symlink-resolved physical path as `$PWD`. And
  `cd a b` is now "too many arguments" (status 1, no chdir) instead of silently cd-ing to
  the first operand.
- Found by reappraisal #12. +12 conformance tests.

## 0.474.0 (2026-06-16) - Tier R14.A: pwd logical default, type -p/-P bare-path output
- BUGFIX (behavior). `pwd` now prints the LOGICAL path by default (and with `-L`) — the
  shell's `$PWD`, which preserves the symlink-named path you cd'd through — matching bash;
  previously it always printed the physical (resolved) path. `-P` prints the physical path.
  Falls back to physical when `$PWD` is stale (no longer names the cwd). `pwd -L`/`-P` flags
  are now parsed (were previously treated as directory operands → error).
- BUGFIX (behavior). `type -p` / `type -P` now print the BARE path (`/bin/ls`) instead of
  the `ls is /bin/ls` banner, matching bash — `type -p NAME` is a common "get the path"
  idiom. `-p` still prints nothing for builtins/functions/keywords; `-P` forces PATH search.
- Found by reappraisal #12. +4 regression tests; the prior weak `type -p` test
  (`endswith('/ls')`, which the buggy banner also satisfied) was strengthened to pin the
  bare-path format.

## 0.473.0 (2026-06-16) - Tier R14.A: test/[ `==` synonym and 3-arg `-a`/`-o`
- BUGFIX (behavior). `test`/`[` now accepts `==` as a synonym for `=` (bash extension;
  literal string equality, NO globbing — unlike `[[ ]]`). `[ "$x" == foo ]` — an
  extremely common idiom — previously errored `[: ==: binary operator expected` (exit 2).
- BUGFIX (behavior). The 3-argument XSI binary primaries `-a`/`-o` now work:
  `[ s1 -a s2 ]` is the AND of the two operands' string non-emptiness, `[ s1 -o s2 ]`
  the OR (`[ a -a b ]` → 0, `[ "" -a b ]` → 1, `[ a -o "" ]` → 0). Previously errored
  `[: -a: binary operator expected`. The multi-arg `-a`/`-o` that combine whole
  expressions (`[ -f x -a -d y ]`) are unaffected (separate dispatch path).
- Found by reappraisal #12 (the two highest-impact common-idiom bugs). +11 conformance
  tests. (README test count corrected to the true collected total, 8,161 — reappraisal
  #12 noted a prior drift.)

## 0.472.0 (2026-06-16) - Fix: real-time signal listing on Linux (kill -l / trap -l)
- BUGFIX (behavior, Linux). `kill -l` and `trap -l` listed only `SIGRTMIN` (34) and
  `SIGRTMAX` (64), omitting the 29 intermediate real-time signals bash enumerates
  (`SIGRTMIN+1`..`SIGRTMIN+15`, `SIGRTMAX-14`..`SIGRTMAX-1`, numbers 35–63). Root cause:
  `signal_utils._build_number_to_name()` is built from Python's `signal.Signals` enum,
  which on Linux exposes only the two RT endpoints as members. The mapping now fills the
  whole `[SIGRTMIN, SIGRTMAX]` range using bash's `SIGRTMIN+n`/`SIGRTMAX-n` naming (names
  from whichever end is closer; tie → RTMIN side), so both listings (and name→number
  lookups like `kill SIGRTMIN+5`) match bash byte-for-byte. Guarded by `hasattr`, so
  macOS/BSD (no real-time signals) are unaffected.
- Caught by the nightly full+bash run on Linux (the local gate runs on macOS, where RT
  signals don't exist). +6 unit tests (RT-naming arithmetic pinned platform-independently;
  Linux-conditional table check).

## 0.471.0 (2026-06-16) - Tier R13.C: complete check_untyped_defs + dead-code/dup polish
- TYPING. `check_untyped_defs` now covers the LAST 11 in-scope modules (psh, __main__,
  shell, version, parser config/__init__/visualization), completing it across the entire
  mypy-checked tree. This surfaced a real latent type smell in `__main__.py` — argparse
  options live in a `Dict[str, object]` (its build loop assigns by dynamic key, so it
  cannot be a TypedDict) and were passed straight to `Shell`'s typed constructor params;
  fixed with explicit `_flag`/`_opt_str` converters at the call site.
- DEAD CODE. Removed unused lexer constants `VARIABLE_START_CHARS`/`VARIABLE_CHARS`
  (lexer/constants.py) and unused recursive-descent methods `Parser.create_with_config`,
  `Parser.from_context`, and `ContextBaseParser.previous` (no production or test callers —
  the similarly-named test exercises `create_context`, not the classmethod).
- DEDUP. `EnhancedValidatorVisitor`'s test-operator quoting heuristic now derives its
  `file_ops`/`string_ops` from the shared `FILE_TEST_OPERATORS`/`STRING_COMPARISON_OPERATORS`
  constants (plus its extra forms) instead of re-listing the operators.
- META-TEST. Added a `KEYWORDS` (lexer/constants.py) ↔ `KEYWORD_TYPE_MAP` (lexer/keyword_defs.py)
  sync test: adding a keyword to one table without the other now fails the suite.
- Found by reappraisal #11. Zero behavior change. +2 meta-tests. Completes Tier R13 (A+B+C).

## 0.470.0 (2026-06-16) - Tier R13.B: failglob, read EOF status, negative-array-read warning
- FEATURE. `shopt -s failglob` is now implemented: a pathname pattern with no matches
  fails the command with "no match: PATTERN" on stderr (status 1) instead of passing the
  pattern through, matching bash. It does not abort the shell (per-command failure) and
  does not affect assignment RHS (which is never globbed). New non-fatal `GlobNoMatchError`
  raised from the single `_glob_words` choke point; obsolete xfail ledger entry removed.
- BUGFIX (behavior). `read` now reports EOF-before-delimiter as failure (exit 1) on ALL
  paths while still assigning whatever was read, matching bash — previously only the
  empty-newline case returned 1, and a partial last line (`printf 'abc' | read x`), a
  custom `-d` delimiter, or `-n` hitting EOF all wrongly returned 0. Empty EOF now also
  CLEARS the target variable (bash) instead of leaving its prior value. The three readers
  were refactored to a shared `(data, status)` contract; timeout (142) is reserved for the
  budget actually expiring. 4 pinned-quirk tests updated to the bash-correct results.
- BUGFIX (behavior). An out-of-range NEGATIVE array read (`a=(1 2 3); ${a[-5]}`) now warns
  "bad array subscript" on stderr and expands to empty (exit status unaffected), matching
  bash; psh was silent. New `IndexedArray.negative_out_of_range` predicate gates the warning
  at the `${arr[i]}` expansion site (a positive out-of-range index stays a silent unset read).
- Found by reappraisal #11. +9 regression tests (failglob ×3, read EOF ×4 incl. var-clear/
  multivar, negative-array ×2).

## 0.469.0 (2026-06-16) - Tier R13.A (parser/executor): break/continue argument validation
- BUGFIX (behavior). `break`/`continue` silently dropped any non-digit argument: the
  parser only consumed the level token when it was `.isdigit()`, so `break foo` parsed
  as `break` plus a stray `foo` command, and `break $n` ignored the variable entirely
  (always broke one level). The level is now captured as argument Words and validated at
  RUNTIME, matching bash (16 probes):
  - non-numeric (`break foo`, `break ""`) → "break: ARG: numeric argument required",
    exit 128, and a non-interactive shell ABORTS (break/continue are POSIX special
    builtins);
  - `break $n` / `break "$n"` → expanded then applied (now breaks N levels);
  - `break 0` / negative → "loop count out of range", exits one loop level, status 0
    (bash quirk: `continue 0` also exits the loop);
  - `break 1 2` or a variable that word-splits to two fields → "too many arguments",
    exit 1, aborts;
  - a NEVER-EXECUTED bad argument (`if false; then break foo; fi`) is NOT an error
    (validation is at runtime, not parse time — bash-matched).
- AST: BreakStatement/ContinueStatement gain `level_words: List[Word]` (the int `level`
  field is kept for hand-built/combinator nodes); a shared `literal_loop_control_level`
  helper feeds the validator and the pretty-printers. The RD parser, executor
  (`_resolve_loop_control_level`), shell_formatter, formatter/validator/debug_ast visitors
  were updated; combinator parser behavior unchanged (educational).
- Found by reappraisal #11. +13 regression tests (TestBreakContinueArgumentValidation).
- Fifth batch of Tier R13.A.

## 0.468.0 (2026-06-16) - Tier R13.A (core/io/executor): readonly array writes, noclobber message, exec diagnostic
- BUGFIX (behavior). Writing an ELEMENT of a readonly array silently succeeded
  (`a=(1 2); readonly a; a[0]=X` set the element; bash errors with status 1 and
  leaves the array unchanged). `execute_array_element_assignment` now gates on
  `var_obj.is_readonly` before the write; the nameref/`set_var_or_array_element`
  path is gated too. Indexed and associative arrays both covered.
- BUGFIX (behavior). `+=` append to a readonly array printed the error but STILL
  mutated the array (`a=(1 2); readonly a; a+=(9)` left `a` as `1 2 9`). The append
  builds in-place into the existing array, so the mutation persisted before
  `set_variable` raised. `execute_array_initialization` now gates on readonly up
  front, before building.
- BUGFIX (cosmetic). noclobber diagnostic word order now matches bash:
  `TARGET: cannot overwrite existing file` (was `cannot overwrite existing file:
  TARGET`). All three raise sites (file/builtin/child backends) updated.
- BUGFIX (cosmetic). `exec >FILE` failing on an errno-less redirect error
  (noclobber/ambiguous/bad-fd) printed `psh: exec: None`; it now prints psh's own
  complete message (mirrors `setup_child_redirections`), e.g. `psh: FILE: cannot
  overwrite existing file`.
- Found by reappraisal #11. +4 regression tests (readonly array element/assoc/append,
  exec noclobber diagnostic).
- Fourth batch of Tier R13.A.

## 0.467.0 (2026-06-16) - Tier R13.A (core): declare -u/-l mutual exclusion + tombstone attribute mutation
- BUGFIX (behavior). `declare -u` and `declare -l` are mutually exclusive; psh kept both
  flags and folded by flag order. bash has two rules, all now matched (13/13 probes):
  - Both flags in ONE declaration cancel — apply NEITHER, and clear any case attribute the
    name already carried (`declare -ul y; y=HeLLo` → `HeLLo`; `declare -u y=X; declare -ul y`
    → unfolded). `_attributes_from_options` no longer does "last-wins"; both-flags now also
    add LOWERCASE|UPPERCASE to the removed set so a pre-existing case attr is cleared.
  - Across SEPARATE declarations the last wins (`declare -u y; declare -l y; y=HeLLo` →
    `hello`).
- BUGFIX (behavior). Attribute mutation silently no-op'd on declared-but-unset variables.
  `apply_attribute`/`remove_attribute` looked up the target via `get_variable_object`, which
  hides UNSET tombstones, so `declare -u y; declare -l y` (and even `declare -u y; declare
  +u y`) left the original flag stuck. New `ScopeManager._find_variable_for_mutation()` is
  tombstone-aware and used by both mutators; the declare dispatch now routes declared-but-unset
  names through them (via `get_declared_variable_object`). `_apply_attributes` also treats a
  both-case-bits value as a no-op defensively.
- Found by reappraisal #11. +7 conformance tests (TestDeclareCaseFlagMutualExclusion).
- Third batch of Tier R13.A.

## 0.466.0 (2026-06-16) - Tier R13.A (expansion): anchored empty-pattern substitution ${x/#/…}/${x/%/…}
- BUGFIX (behavior). `${x/#/PRE}` and `${x/%/SUF}` (anchored substitution with an EMPTY
  pattern) were no-ops; bash matches the empty string at the start/end and
  prepends/appends the replacement (`x=hello; ${x/#/PRE}` → `PREhello`,
  `${x/%/SUF}` → `helloSUF`, and on an empty value `${x/#/PRE}` → `PRE`).
  `operators._substitute` short-circuited `if not pattern: return value` for ALL four
  operators; the early-return is now gated to the unanchored `/` and `//` (which DO no-op
  on an empty pattern), so `/#` and `/%` fall through to substitute_prefix/substitute_suffix
  (already correct). Found by reappraisal #11. +2 regression tests.
- Second batch of Tier R13.A.

## 0.465.0 (2026-06-16) - Tier R13.A (builtins): test -v, getopts OPTARG, lone `test !` (reappraisal #11)
- BUGFIX (behavior). Three genuine bash divergences in the test/getopts builtins, found by
  reappraisal #11:
  - **`test -v VAR` / `[ -v VAR ]` now works** — it had NEVER worked (`evaluate_unary`
    returned the sentinel exit 2 for every name). Implemented via a shared `variable_is_set`
    helper (`test_command.py`) that the `[[ -v ]]` evaluator now also delegates to (dedup);
    supports `name` and `array[key]` (indexed/associative). `x=5; test -v x` → 0; unset → 1.
  - **`getopts` non-silent invalid option leaves `OPTARG` unset** (was set to the bad char);
    silent mode (`:abc`) still records the char — matching bash and the missing-arg branch.
  - **A lone `test !` / `[ ! ]` is the one-argument non-empty-string test (exit 0)**, not
    negation-of-empty (was exit 1); `!` still negates a following operand.
  - +regression tests (test_test_builtin: -v scalar/array, lone-bang; getopts conformance:
    loud-mode OPTARG-unset). Removed the now-obsolete `test_absent_features::test_test_dash_v`
    (was a strict-xfail "absent feature").
- First builtins batch of Tier R13.A. (Deferred within R13.A: `declare -p` on a bare empty
  array prints `=()` — the correct fix needs an UNSET-array-state model so a bare
  `declare -a a` is distinguished from `a=()`, which touches array set/unset semantics.)

## 0.464.0 (2026-06-16) - Tier R12.B finale: check_untyped_defs for the combinator parser (12/12 packages)
- TYPING (no behavior change). Enabled `check_untyped_defs = true` for the last package,
  `psh.parser.combinators.*` — mypy now body-checks **every package (12/12)**. Fixing the
  ~34 fallout errors was two kinds of change, both type-only:
  - `Parser.or_else` now types its alternative/result as the loose `Parser` rather than
    `Parser[T]`: the shell grammar composes ordered choice over *heterogeneous*
    productions (`arithmetic_command.or_else(enhanced_test_statement)` yields one node
    type OR another), which `Parser[T]` cannot express. Runtime behavior unchanged
    (the parity suite confirms).
  - Added `assert … is not None` narrowing after the `result.success` checks where the
    code reads `result.value.<attr>` (redirections, pipelines, simple-command, subshell/
    brace bodies, expansion-to-word, top-level wrap) — the same idiom used elsewhere; and
    loosely typed one heterogeneous parser list.
- Completes the Tier R12.B typing rollout (3/12 → 12/12) AND the last open thread from
  reappraisal #10. `tests/parser_differential` parity + full suite green.

## 0.463.0 (2026-06-15) - Tier R12.D.6: dedup RD array-initializer head detection (review M4/dedup) — R12.D complete
- REFACTOR (no behavior change). `CommandParser._check_array_initialization` (argument
  position, e.g. `declare -a a=(1 2)`) duplicated the `name=(...)`/`name+=(...)` head
  detection that `ArrayParser._candidate_initializer` (statement position, e.g. `a=(1 2)`)
  already performs. It now delegates detection to that single peek-only classifier (which
  reports `head_token_count`), then does its own token-consume + head-Token synthesis. The
  element-collection loop was already shared (`parse_array_init_elements`); this removes the
  last copy — head detection now lives in one place. Single-token, split, and spaced
  (`declare a = (...)`) forms all preserved; 804 array/declare/parser tests green.
- Sixth item of Tier R12.D. **Tier R12.D complete** (v0.458–463: combinator dedup, dead-code
  & stale-doc sweep, rm-rf security heuristic, io-redirect dispatch dedup, declare-method
  split, array-init dedup).

## 0.462.0 (2026-06-15) - Tier R12.D.5: split the 195-line declare `_declare_variables` method (review M4)
- REFACTOR (no behavior change). `_declare_variables` (builtins/function_support.py) — the
  longest method in the codebase (~195 lines, reappraisal #9 M4) — is now a small
  dispatcher over three extracted helpers: `_declare_list_all` (no-argument listing),
  `_declare_assignment` (`NAME=value`/`NAME+=value`: nameref, array-init, scalar-into-array,
  regular scalar), and `_declare_bare_name` (declare/modify by name only). The per-argument
  loop now reads `rc = self._declare_assignment(...)` / `_declare_bare_name(...)` and stops
  on the first non-zero (an invalid name / nameref self-ref), matching bash. Logic moved
  verbatim; all 1054 declare/array/builtin tests green.
- Fifth item of Tier R12.D.

## 0.461.0 (2026-06-15) - Tier R12.D.4: collapse apply_permanent_redirections dispatch (review M7)
- REFACTOR (no behavior change). `FileRedirector.apply_permanent_redirections` (the
  `exec`-redirection path) re-enumerated every `redirect.type` to choose a stream rebind
  even though the planner already computed `plan.target_fd`. Collapsed the seven-branch
  chain to direction-based dispatch: combined (`&>`) rebinds 1+2; a dup/close
  (`&` in the type) rebinds its own fd (close → nothing); input forms (`<` prefix)
  rebind stdin; output forms (`>`/`>>`/`>|`) rebind the target fd. The residual of
  reappraisal #9 M7. All 245 redirection tests green (including the `exec >&-` close-fd
  case that a first cut regressed and that now pins the dup-vs-close distinction).
- Fourth item of Tier R12.D.

## 0.460.0 (2026-06-15) - Tier R12.D.3: security visitor detects recursive+force rm in all flag spellings
- IMPROVEMENT (security analysis). `SecurityVisitor`'s dangerous-`rm` check matched only
  the literal `-rf` substring of the joined args, so `rm -r -f /`, `rm -fr /`,
  `rm --recursive --force /etc`, and `rm -rvf /var` went unflagged (and a filename
  containing `-rf` could false-match). It now inspects the actual argv flag tokens via a
  new `_rm_is_recursive_force` helper — recognising clustered (`-rf`/`-fr`/`-Rf`/`-rvf`),
  separate (`-r -f`), and long (`--recursive --force`) forms — and only flags a sensitive
  target (`/`, `/*`, `/bin`, `/usr`, `/etc`, `/var`, `/home`) when BOTH recursive and
  force are present. Found by reappraisal #10. +7 unit tests.
- Third item of Tier R12.D.

## 0.459.0 (2026-06-15) - Tier R12.D.2: dead-code & stale-doc sweep
- REFACTOR (no behavior change). Removed verified-dead code flagged by reappraisals
  #9/#10:
  - RD parser: `TokenGroups.COMMAND_LIST_END` (defined, never used);
    `WordBuilder.build_word_from_string` (a TODO stub with zero real callers — the
    similarly-named test exercises `build_word_from_token`, not this).
  - Visitor: the two `word_analysis` helpers with zero references anywhere
    (`has_process_substitution`, `expansion_source_text`); documented the remaining
    `has_*`/`referenced_*`/`is_*` helpers as an intended, tested Word-analysis library
    surface (review M6). Dropped the unreachable `'777'/'0777'` branch in
    `security_visitor._is_world_writable_permission` (the digit-regex branch above it
    already returns for those).
  - Scripting: the dead `InteractiveInput` class (`input_sources.py`; REPL input is
    handled by `psh/interactive/`); the write-only `_last_hint` field in
    `command_accumulator.py` (assigned three times, never read).
- DOCS. Fixed stale references: `docs/subsystem_internals.md` no longer lists the
  removed `AliasExecutionStrategy` as a live execution strategy (alias expansion moved to
  the lex→parse boundary in R8.6b); `psh/core/CLAUDE.md`'s Key Files table now lists the
  extracted sub-objects (`execution_state`/`history_state`/`terminal_state`/
  `stream_bindings`) and `internal_errors.py`.
- Second item of Tier R12.D.

## 0.458.0 (2026-06-15) - Tier R12.D.1: combinator dedup — drop dead pipeline/and-or duplicates, document the cut channel
- REFACTOR (no behavior change). Deleted the two dead module-level functions
  `parse_pipeline` / `parse_and_or_list` from `parser/combinators/commands/__init__.py`
  — independent reimplementations of the `PipelineMixin` methods that were exported but
  never called (the live parser uses the mixin; the parity tests use the full parser).
  Removed from both `__all__` lists. (`parse_simple_command` / `create_command_parsers`
  are kept — still used by tests / `parser.py`.)
- DOCS. Documented `ParseResult.committed` as reserved-but-inert: commitment is currently
  expressed by raising a `ParseError` via `raise_committed_error` (the imperative cut),
  while the in-algebra `committed` channel (honoured by `or_else`/`many`/`separated_by`)
  is kept ready for the eventual exception→return migration — wired-but-inert by design,
  not dead code (a reappraisal-#10 reviewer flag).
- First item of Tier R12.D (dedup/polish).

## 0.457.0 (2026-06-15) - Tier R12.C: extract ExecutionState from the ShellState god-object
- REFACTOR (no behavior change). Lifted the eight per-command execution-scratch fields
  off `ShellState` into a cohesive `ExecutionState` sub-object
  (`psh/core/execution_state.py`): `last_exit_code`, `last_bg_pid`, `foreground_pgid`,
  `command_number`, `pipestatus`, `errexit_eligible`, `last_cmdsub_status`,
  `in_forked_child`. `ShellState` keeps `self.execution` and exposes all eight as
  delegating properties, so every existing call site (`shell.state.last_exit_code`, …)
  is untouched — same "typed sub-object + delegating properties" pattern as
  `TerminalState`/`HistoryState`/`StreamBindings`. This is the twice-deferred #9 M1 /
  #10 finding; it shrinks the god-object and makes subshell adoption a single
  `parent.execution.copy_into(self.execution)` — so a new execution field can no longer
  be silently omitted from `adopt()` (the structural cause of the v0.453 `$!`-in-subshell
  bug). +5 unit tests. mypy/ruff clean; full suite green.
- Tier R12.C.

## 0.456.0 (2026-06-15) - Tier R12.B batch 3: check_untyped_defs for ast_nodes + recursive-descent parser (R12.B done)
- TYPING (no behavior change). Enabled `check_untyped_defs = true` for `psh.ast_nodes.*`
  and the PRODUCTION parser `psh.parser.recursive_descent.*` (both zero-fallout). mypy
  now body-checks **all production code**; the only package still not body-checked is the
  educational combinator parser `psh.parser.combinators.*` (~43 errors — deferred to a
  dedicated pass, since it's outside the production quality bar).
- **Tier R12.B substantially complete** (v0.454–456): the `check_untyped_defs` rollout
  went from 3/12 to 11/12 packages — every production subsystem is now body-checked — and
  along the way caught real `declare -f` formatter bugs (v0.455). The clearest A−→A lever
  from reappraisals #9/#10 is realized.

## 0.455.0 (2026-06-15) - Tier R12.B batch 2: check_untyped_defs for utils/interactive/scripting (+ found real declare -f bugs)
- TYPING + BUGFIX. Enabled `check_untyped_defs = true` for `psh.utils.*`,
  `psh.interactive.*`, `psh.scripting.*` — mypy now body-checks **10 of ~12** packages.
  Fixing the fallout surfaced two GENUINE latent bugs in `utils/shell_formatter.py`
  (the `ShellFormatter` used by `declare -f` / `type` to display function bodies):
  - **BUGFIX (behavior):** `declare -f` on a function containing a C-style `for ((;;))`
    loop raised `AttributeError: 'CStyleForLoop' object has no attribute 'init'` — the
    formatter referenced `.init`/`.condition`/`.update` instead of the real
    `.init_expr`/`.condition_expr`/`.update_expr`. Likewise `break`/`continue` with a
    level referenced `.levels` instead of `.level`. Both now format correctly.
  - The remaining fallout was type-only (annotations / None-guards in
    `scripting/input_sources.py`, `interactive/signal_manager.py`,
    `interactive/repl_loop.py`); no behavior change there.
  - +regression tests: formatter unit tests (C-style for, break/continue level) and
    `declare -f` integration tests; a `CaseItem`/`str` loop-variable type confusion in
    the formatter was also cleaned up.
- Second batch of Tier R12.B. (Remaining un-body-checked: parser + ast_nodes.)

## 0.454.0 (2026-06-15) - Tier R12.B: mypy check_untyped_defs for io_redirect/lexer/visitor/builtins (batch 1)
- TYPING (no behavior change). Enabled `check_untyped_defs = true` for four more
  packages — `psh.io_redirect.*`, `psh.lexer.*`, `psh.visitor.*`, `psh.builtins.*` —
  joining core/expansion/executor. mypy now body-checks **7 of ~12** packages and stays
  clean (these four had zero fallout: the annotation-unchecked notes were just notes,
  not errors). The clearest A−→A lever from reappraisals #9/#10; remaining:
  utils/interactive/scripting (small fallout to fix) and parser/ast_nodes.
- First batch of Tier R12.B.

## 0.453.0 (2026-06-15) - BUGFIX: sparse-array negative-index reads + `$!` subshell inheritance — R12.A (cluster complete)
- BUGFIX (behavior). Two core bugs found by reappraisal #10:
  - `IndexedArray.get()` resolved a negative subscript by indexing the list of *set*
    indices, which disagreed with the write path (`resolve_write_index`, "highest index
    + 1 + index") and with bash on SPARSE arrays. `${a[-2]}` on `a[0]=x; a[5]=y` gave
    `x` (bash: empty, slot 4 unset); `${a[-6]}` gave empty (bash: `x`, slot 0). `get()`
    now uses the same one-past-the-top mapping as writes, so reads and writes agree
    (bash-verified against real bash, including the unset-middle case). An out-of-range
    negative *read* expands to empty (bash warns + expands empty; only a bad *write*
    subscript is a hard error — that path is unchanged).
  - `$!` (last background PID) was not inherited by subshell-style children:
    `ShellState.adopt()` didn't copy `last_bg_pid`, so `$!` read empty inside `( … )`,
    `$( … )`, and the env builtin's child (bash inherits it). Added the copy.
  - +8 regression tests (IndexedArray negative-index unit tests; `$!`-in-subshell
    integration tests).
- Sixth and final item of Tier R12.A — **the reappraisal-#10 bug cluster is complete**
  (v0.448–453: history-trim regression, exec redirects, `(( ))`/`[[ ]]`-before-then/do,
  combinator line-continuation, ANSI-C in operands, and these two core bugs).

## 0.452.0 (2026-06-15) - BUGFIX: ANSI-C `$'...'` in parameter-expansion operands + full `${var@E}` — R12.A
- BUGFIX (behavior). Two related ANSI-C-quoting gaps, both fixed by routing through the
  single canonical decoder (`lexer/pure_helpers.handle_ansi_c_escape`):
  - `$'...'` was not decoded inside parameter-expansion operands — default values
    (`${x:-$'\t'}`), patterns (`${x#$'\t'}`, `${x/$'\t'/X}`), and replacements
    (`${x/b/$'\t'}`) all left it literal where bash decodes it. The three operand
    expanders (`operands.py`: `_expand_pattern_operand`, `_expand_replacement_operand`,
    `_expand_operand`) now decode an inline `$'...'` via the shared `scan_inline_ansi_c`
    scanner. (`$'...'` is intentionally NOT decoded by `expand_string_variables`, which
    also serves double-quoted content where it must stay literal — so each operand
    walker decodes it explicitly.)
  - `${var@E}` used a third, incomplete ANSI-C decoder (`operators.py:_ansi_c_expand`)
    missing octal `\NNN`, `\cX`, `\uHHHH`, `\UHHHHHHHH`; it now delegates to the
    canonical decoder, removing the duplication and the gaps.
  - Found by reappraisal #10. +9 conformance tests; ordinary operands (no `$'`) take an
    unchanged fast path.
- Fifth item of Tier R12.A.

## 0.451.0 (2026-06-15) - BUGFIX: combinator parser rejected line-continuation after a pipe/and-or operator — R12.A
- BUGFIX (combinator parser only). The combinator pipeline/and-or parsers did not skip
  a NEWLINE after `|`/`|&`/`&&`/`||`, so a command continued on the next line after the
  operator (`echo a |⏎cat`, `echo a &&⏎echo b`, `false ||⏎echo c`, multi-stage pipes)
  was rejected under `--parser combinator` with "Expected command", while bash and the
  recursive-descent parser accept it. Fix: skip NEWLINE tokens after the pipe operator
  and after the and-or operator before parsing the right-hand command
  (`commands/pipelines.py`). Found by reappraisal #10. +4 three-way (bash/rd/combinator)
  parity regression tests. (The duplicate module-level `parse_pipeline`/`parse_and_or_list`
  helpers in `commands/__init__.py` still carry the bug but are test-only and slated for
  removal in R12.D.)
- Fourth item of Tier R12.A.

## 0.450.0 (2026-06-15) - BUGFIX: `(( ))`/`[[ ]]` condition header before `then`/`do` with no separator — R12.A
- BUGFIX (behavior, both parsers). An arithmetic command or `[[ ]]` test used as a
  condition header followed DIRECTLY by `then`/`do` (no `;`/newline) was rejected:
  `if ((1)) then …`, `while ((x)) do …`, `for ((;;)) do …`, `if [[ a = a ]] then …`
  all errored (`do`/`then` lexed as a plain WORD) where bash accepts them. Root cause:
  `DOUBLE_RPAREN`/`DOUBLE_RBRACKET` were missing from the lexer's
  `RESET_TO_COMMAND_POSITION` (command_position.py), so the keyword normalizer never
  returned to command position after `))`/`]]` and the following `then`/`do` stayed a
  WORD. Fix: add the two compound-closer token types to that set (a fix in the shared
  lexer, so it applies to both the recursive-descent and combinator parsers).
  Separator forms (`if ((1)); then`, `[[ x = x ]] && …`) are unchanged. Found by
  reappraisal #10. +7 conformance tests + updated the command-position drift-lock tests.
- Third item of Tier R12.A.

## 0.449.0 (2026-06-15) - BUGFIX: `exec CMD` ignored its redirections — R12.A
- BUGFIX (behavior). `exec CMD args [redirects]` (the exec builtin WITH a command)
  silently ignored the redirections — `CommandExecutor._handle_exec_builtin`'s
  with-command branch handed off to the builtin's execvpe without applying
  `node.redirects` (only the no-command `exec >file` branch applied them). Probes vs
  bash: `exec printf out >file` wrote to the terminal instead of the file;
  `exec /no/such 2>/dev/null` printed the not-found error to the un-redirected stderr
  (bash is silent). Both exited with bash's code, so exit-code-only checks missed it.
  Fix: apply `node.redirects` permanently (via `apply_permanent_redirections`) before
  the exec — exec replaces the process image, so the redirected fds carry into the new
  program, and if the exec fails they stay in effect (matching bash). Found by
  reappraisal #10. +3 regression tests (`TestExecWithCommandRedirect`).
- Second item of Tier R12.A.

## 0.448.0 (2026-06-15) - BUGFIX: history save dropped new entries after an in-session trim (v0.447 regression) — R12.A
- BUGFIX (data loss; regression in v0.447). `HistoryManager._file_synced_len` (the
  count of history entries already persisted) is an index into `state.history`, but
  `add_to_history` trims the list from the FRONT once it exceeds `max_history_size`
  (default 1000). The marker was not adjusted for the trim, so after the list shifted,
  `save_to_file`'s `history[_file_synced_len:]` slice skipped genuinely-new commands
  (and could re-add already-saved ones). A session that ran more than
  `max_history_size` commands before exiting silently lost the entries between the
  stale index and the tail. Fix: when the front-trim drops N entries, decrement
  `_file_synced_len` by N (clamped at 0) so it keeps pointing at the first unsaved
  entry. Found by reappraisal #10. +1 regression test
  (`test_in_session_trim_does_not_lose_new_entries`).
- First item of Tier R12.A (the reappraisal-#10 bug cluster); memo at
  `docs/reviews/ground_up_reappraisal_10_2026-06-15.md`.

## 0.447.0 (2026-06-15) - BUGFIX: concurrency-safe history persistence (no more multi-terminal clobber)
- BUGFIX (data loss). Command history was lost when multiple psh sessions shared one
  history file — e.g. several terminal windows each auto-starting psh (`psh` as the last
  line of `.zshrc`). `HistoryManager.save_to_file` truncate-rewrote the whole file on
  exit, so the last shell to exit overwrote every other shell's commands
  (last-writer-wins). The file stayed near its loaded baseline and the loss appeared
  intermittent (it depended on exit ordering).
  - Fix: `save_to_file` now appends only THIS session's new entries under an exclusive
    `flock`, re-reading the current on-disk history first (picking up entries other
    shells appended since we loaded), merging, trimming to `max_history_size`, and
    writing the result back. Concurrent shells serialize on the lock instead of
    clobbering one another. `HistoryManager` tracks `_file_synced_len` (how many of
    `state.history`'s entries are already persisted) so only genuinely-new commands are
    added and loaded entries are never duplicated.
  - The history file is now created mode `0o600` (private), where the old
    `open(..., 'w')` left it at the umask default.
  - This also fixes sequential-session accumulation in non-interactive/piped mode (the
    merge keeps prior content instead of overwriting it).
  - +5 regression tests (`tests/unit/interactive/test_history_persistence.py`):
    roundtrip, sequential accumulation, the concurrent no-clobber case, append-only
    (no duplication of loaded entries), and max-size trimming.

## 0.446.0 (2026-06-15) - Tier R11.P4: document the combinator [[ ]]/arithmetic sublanguage boundary (R11 complete)
- DOCS (no behavior change). Final R11 phase: per the architecture review's Phase 4,
  the combinator parser's intentionally-shallow `(( ))` and `[[ ]]` sublanguages are
  now documented as a deliberate educational-scope boundary, and the "abandoned-work"
  comments that read like unfinished TODOs are replaced with honest boundary notes.
  - `SpecialCommandParsers` class docstring now states the boundary up front:
    `(( ))`/`[[ ]]` are recognised structurally but their inner grammars are shallow
    (arithmetic captured as a token string for the runtime evaluator, not an AST;
    `[[ ]]` handles negation + simple unary/binary/single-operand tests but not
    `&&`/`||` compounds, parenthesised grouping, per-operand quote context, or trailing
    redirections), with a pointer to the recursive descent parser as the full
    implementation.
  - Replaced `_build_arithmetic_command`'s "For now, skip redirection parsing to keep
    it simple", `_parse_test_expression`'s "This is simplified - full implementation
    would parse compound expressions", and `expansions._validate_command_substitution`'s
    "For now, accept if tokenization succeeded" with explicit educational-scope notes.
  - No `(( ))`/`[[ ]]` behavior change; full `tests/parser_differential` parity suite
    and whole suite green.
- **Tier R11 COMPLETE.** Elevated the combinator parser toward textbook FP across
  P1 (cleanup) → P2 (discriminated `ParseResult` + cut/farthest-error) → P3 (grammar
  simplification: recursion-only, build-once, modular) → P4 (documented sublanguage
  boundary). Source roadmap: `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`.

## 0.445.0 (2026-06-15) - Tier R11.P3(c): split the combinator commands module into a mixin package
- REFACTOR (no behavior change). The 816-line `psh/parser/combinators/commands.py`
  is now a `commands/` PACKAGE of focused mixin modules, mirroring the existing
  `control_structures/` precedent. `CommandParsers` is composed from four mixins:
  - `commands/redirections.py` — `RedirectionMixin` (`_parse_redirection`,
    `_parse_fd_dup_word`, `_parse_word_as_word`)
  - `commands/simple.py` — `SimpleCommandMixin` (simple-command word/redirect/array
    collection and Word-AST building)
  - `commands/pipelines.py` — `PipelineMixin` (pipeline + and-or list)
  - `commands/statements.py` — `StatementMixin` (statement + the
    `build_statement_list` recursion engine)
  - `commands/__init__.py` keeps the `CommandParsers` class shell (`__init__`,
    `_initialize_parsers`, the `set_command_parser`/`set_function_def` slot setters)
    and the module-level convenience functions; `commands/_constants.py` holds the
    shared `_FD_DUP_RE`/`_WORD_LIKE_TYPES`; `commands/_protocols.py` is a
    TYPE_CHECKING-only `CommandParsersProtocol` so each mixin type-checks in isolation
    (same pattern as `control_structures/_protocols.py`).
  - Public API unchanged: `from ..commands import CommandParsers,
    create_command_parsers, parse_simple_command, parse_pipeline, parse_and_or_list`
    all still resolve. mypy `files` list updated to the new modules. Methods moved
    verbatim; `tests/parser_differential` parity suite + whole suite green.
- Review Ugly #5 (Phase 3) from `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`.
  This completes Tier R11.P3 (grammar simplification): condition headers (P3.1),
  function body (P3a), build-once wiring (P3b), and module split (P3c) all shipped —
  the combinator parser no longer slices tokens, builds its grammar once, and is
  organized into focused modules.

## 0.444.0 (2026-06-15) - Tier R11.P3(b): combinator grammar built once (no post-construction patching)
- REFACTOR (no behavior change). The combinator grammar graph is now built exactly
  ONCE and never rebuilt or patched after construction (review Ugly #4). Net −98 lines.
  - `CommandParsers` builds `pipeline`/`and_or_list`/`statement`/`statement_list` once
    in `_initialize_parsers`, reading two mutable recursion *slots* at parse time:
    `_pipeline_element` (a single pipeline element — widened from a bare simple command
    to control-structure/special/simple during wiring) and `_function_def` (the
    function-definition head, tried before an ordinary statement). Wiring just fills the
    slots (`set_command_parser` / new `set_function_def`).
  - Deleted the ~50-line `set_command_parser` body that REBUILT the pipeline and and-or
    parsers from scratch (a near-duplicate of `_build_pipeline_parser` /
    `_build_and_or_list_parser` — also review Ugly #5), and the now-unnecessary
    reassignment of `commands.statement` / `commands.statement_list` in
    `parser._build_complete_parser`.
  - Removed the vestigial `ForwardParser` machinery that was never wired:
    `statement_forward`/`statement_list_forward` instances (commands.py +
    control_structures), and the dead `set_control_parsers`/`set_special_parsers`
    `hasattr` calls in parser.py (no such methods ever existed). The `ForwardParser`
    primitive itself is kept (a tested, exported combinator building block).
  - Also retired the separate `separated_by`-based `_build_statement_list_parser`; the
    top-level list is now `build_statement_list()` like every other statement list.
  - Full `tests/parser_differential` parity suite + whole suite green; behavior
    identical (compound-in-pipeline, function defs, and-or, negation all verified).
- Review Phase 3 item 3 from `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`.

## 0.443.0 (2026-06-15) - Tier R11.P3(a): function body parses by recursion (last slicer retired)
- REFACTOR (fixes a bash/rd divergence). `StructureParserMixin._parse_function_body`
  no longer collects the tokens between matching `{ }` by brace-counting and re-parses
  the slice. It parses the body on the real token stream via
  `build_statement_list()` (which stops at the `RBRACE` token; nested brace groups
  consume their own `}`), then expects `}`. This was the LAST place the combinator
  parser sliced tokens out of the stream — every compound header and body now parses
  by recursion.
  - Fixes a slicer divergence: a `}` that is merely an argument (`f() { echo }; }`)
    was mis-read as the body's closing brace; it is now consumed as a word, matching
    bash and the recursive-descent parser.
  - Missing-nested-terminator diagnostics (an `if`/loop inside the body without its
    `fi`/`done`) are preserved at end-of-input parity with rd by re-raising the
    committed `ParseError` at the last token (the same handling the old loop used).
  - +2 three-way parity regression tests (`}`-as-argument, nested brace group in a
    function body). Full `tests/parser_differential` parity suite green.
- Review Phase 3 item 2 from `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`.

## 0.442.0 (2026-06-15) - Tier R11.P3.1: combinator condition headers parse by recursion (closes H3)
- REFACTOR (fixes a bash/rd divergence). The `while`/`until`/`if`/`elif` CONDITION
  headers no longer slice tokens to the first `do`/`then` and re-parse the slice.
  They now parse on the real token stream via `build_statement_list(frozenset({'do'}))`
  / `build_statement_list(frozenset({'then'}))` — the same recursion engine the
  compound bodies use — stopping only at a *command-position* `do`/`then`.
  - Closes reappraisal #9 bug H3 (the unfinished tail of C3): a `do`/`then` that is
    merely an argument is now consumed as a word, matching bash and the recursive
    descent parser. Previously `while echo do; false; do echo body; done` and
    `if echo then; then echo hi; fi` failed/diverged under `--parser combinator`;
    all three shells now agree.
  - Deletes three hand-written condition token-slicer loops (and the special
    "`then` must be preceded by a separator" / "unexpected `fi`" message checks,
    which are now emergent from the recursion). The combinator parser no longer
    slices any compound header or body out of the token stream.
  - +5 three-way (bash/rd/combinator) parity regression tests in
    `TestKeywordSpelledArgumentInCondition`; full `tests/parser_differential`
    parity suite green.
- Review Phase 3 item 1 from `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`.

## 0.441.0 (2026-06-15) - Tier R11.P2.2: combinator core — farthest-error selection in or_else
- REFACTOR (improved diagnostics, parity-preserving). `Parser.or_else` no longer
  blindly returns the alternative's failure when both branches fail recoverably.
  It now applies the textbook *farthest-error* rule via a new `_farther_failure`
  helper: keep whichever failure consumed more input (higher `position` — the
  alternative that matched the most before giving up), and on a positional tie
  merge the two `expected` label sets (order-preserving, de-duplicated) so the
  diagnostic can name every token that could have continued the parse. Uses the
  `expected`/`position` channel added in P2.1.
- Behaviour is parity-preserving: accept/reject is unchanged (only the surfaced
  failure among already-failing alternatives changes), and the full
  `tests/parser_differential` diagnostic-position + exception-type parity suite
  stays green — the chosen positions still match the recursive-descent parser
  everywhere they are pinned.
- +3 core unit tests (farthest wins regardless of try-order; expected-label merge
  on tie). This is review Phase 2 item 3 (expected labels + farthest-error) from
  `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`. With P2.1
  (discriminated union + cut semantics) the review's Phase 2 is substantially done;
  the remaining item 5 (converting the ~50 `raise_committed_error` exception sites
  to committed `ParseFailure` returns) is deferred — exception propagation is a
  legitimate global-cut and a wholesale conversion is high-churn with debatable
  clarity gains.

## 0.440.0 (2026-06-15) - Tier R11.P2.1: combinator core — discriminated ParseResult + cut/expected error channel
- REFACTOR (no behavior change). Phase 2 of elevating the combinator parser to
  textbook FP begins with the result type. `ParseResult` is now a success/failure
  discriminated union with two explicit constructors:
  - `ParseSuccess(value, position)` and `ParseFailure(position, error, *, expected,
    committed)` (both `ParseResult` subclasses; the legacy
    `success`/`value`/`position`/`error` attribute surface is preserved so all ~150
    construction sites and ~400 field reads keep working during the migration).
  - The failure shape gains an FP error channel: `committed` (a *cut* — a committed
    failure is NOT retried by `or_else`, so commitment can live inside the combinator
    algebra instead of being raised as an exception) and `expected` (labels for
    same-position diagnostic merging, populated by `token`/`keyword`/`literal`).
  - `or_else`/`many`/`separated_by` now honour the cut: a committed failure
    propagates instead of being swallowed/retried. This is wired but a NO-OP until
    P2.2 starts constructing committed failures (every failure is recoverable today),
    so behavior is identical — verified by the full `tests/parser_differential`
    parity suite (AST + rejection + diagnostic-position + exception-type) and the
    whole suite (7712 passed).
  - The core combinators (`map`/`then`/`sequence`/`between`/`skip`/`token`/…) now
    construct via `ParseSuccess`/`ParseFailure`; failure-position semantics
    (atomic reset-to-entry where the old code reset) are preserved exactly.
  - +8 core unit tests pinning the constructors and the commitment short-circuit.
- This is review Phase 2 step 1 of
  `docs/reviews/parser_combinator_architecture_review_2026-06-15.md`. Next (P2.2):
  convert the `raise_committed_error` sites to committed `ParseFailure`s where
  practical, moving committed syntax errors out of exceptions.

## 0.439.0 (2026-06-15) - Tier R11.P1: combinator parser cleanup (dedup stale parsers, drop dead diagnostics)
- REFACTOR (no behavior change). Phase 1 of elevating the combinator parser toward
  textbook quality — pure deletion of stale/duplicate code, parity suites green.
  Net −415 production lines.
  - Removed the SECOND (dead) array parser from `special_commands.py`:
    `_build_array_initialization`, `_build_array_element_assignment`,
    `_detect_array_pattern`, `_build_array_assignment`, and the
    `_collect_element_value_word` helper (~370 lines). They were built but never
    composed into `special_command`, so they never ran in production. `arrays.py`
    (`ArrayParsers`, used by the live command path in `commands.py`) is now the sole
    array assignment/initialization parser.
  - Removed the orphaned process-substitution parser
    `ExpansionParsers._parse_process_substitution` (+ its `self.process_substitution`
    instance) — it was not wired into `self.expansion`; the live standalone-procsub
    parser is `SpecialCommandParsers._build_process_substitution`, and inline procsub
    goes through the shared WordBuilder path.
  - Deleted the dead function-body diagnostic remapping in `structures.py`: four
    `"expected 'fi'/'done'/'esac'/'then'"` substring rewrites that became unreachable
    after C3 (missing compound terminators inside a function body now RAISE via
    `raise_committed_error`, caught structurally by `is_missing_nested_terminator`,
    rather than returning a soft failure to be re-described by string-matching).
  - Pruned now-unused imports (`ArrayInitialization`/`ArrayElementAssignment`/
    `WordPart`/`Union`/`cast`/`format_token_value` in special_commands.py,
    `ProcessSubstitution` in expansions.py) and the corresponding dead tests
    (`TestArrayOperations` in test_special_commands.py, two procsub tests in
    test_expansions.py).
  - Documented `build_statement_list()` as the single compound-body engine in
    `psh/parser/CLAUDE.md` and corrected the combinator file table (arrays live in
    `arrays.py`, not `special_commands.py`).

## 0.438.0 (2026-06-15) - Tier R10.A: reappraisal #9 bug fixes (string-context `\$` escape, builtin I/O convention)
- BUGFIX (behavior). String-context `\$` now always drops its backslash, matching
  bash and the command-argument Word path. `VariableExpander._process_double_quote_escape`
  previously kept the backslash on `\$` unless it was immediately followed by a
  variable-name character, so double-quoted text in here-strings/documents, redirect
  targets, `[[ ]]` operands, and `${...}` operands diverged from bash:
  - `cat <<< "a\$ b"` → was `a\$ b`, now `a$ b` (bash).
  - `echo "${v:-a\$ b}"` → was `a\$ b`, now `a$ b` (bash).
  - `\$VAR` still shields the expansion (literal `$VAR`); `\\`, `\"`, `` \` `` and
    C-style `\n`/`\t` are unchanged. (`\<newline>` line continuation is handled
    upstream by the lexer and is intentionally not processed here.)
  - The stale "PS1 compatibility" justification was removed: PS1 expansion routes
    through `interactive/prompt.py`, not `expand_string_variables` (zero callers).
  - This is reappraisal #9's bug H1 — the genuine content of the previously deferred
    "D2" escape-processor item (the two processors differed because the string-context
    one was buggy, not "by design"). Pinned by the new
    `tests/conformance/posix/test_escaped_dollar_string_context_conformance.py`.
- CONSISTENCY (no observable change). `history` and `version` now emit through the
  v0.284 forked-child-aware `self.write_line()` helper instead of raw
  `print(file=shell.stdout)` — they were the last two builtins bypassing the
  error-channel convention every other builtin follows (reappraisal #9 bug H2). In
  psh's real forks `shell.stdout` is already bound to fd 1, so no divergence could be
  reproduced; the change removes the inconsistency and the unused `sys` import.
- DOCS. Reconciled the README test counts (the `**Tests**: total` line and the
  `**Test Coverage**:` line now agree) — a reappraisal #9 LOW finding.

## 0.437.0 (2026-06-15) - Tier R9.D6: executor seam fixes (drop [[ ]] backchannel, dedup procsub body)
- REFACTOR (no behavior change). Two executor/IO seams tidied:
  - `[[ ]]` no longer bounces through the shell. `ExecutorVisitor.visit_EnhancedTestStatement`
    now owns the evaluation directly (constructs the in-package
    `TestExpressionEvaluator`, applies redirections via its own `io_manager`).
    The `Shell.execute_enhanced_test_statement` method — which existed only to
    serve the executor — is removed, eliminating the executor→shell→evaluator
    backchannel (the executor already holds everything it needs).
  - Process substitution: the read-side `<(cmd)` child body inlined the same
    tokenize/parse/execute that the write-side already routed through the shared
    `_execute_process_substitution_body` helper. Both sides now call the helper.
- Full suite + ruff + mypy green. Completes Tier R9.D (and the reappraisal-#8
  R9 roadmap: A/B/C/D all shipped).

## 0.436.0 (2026-06-15) - Tier R9.D4: split the two ~900-line expansion files
- REFACTOR (no behavior change). Decomposed the two largest expansion modules
  along their natural seams:
  - `brace_expansion.py` (903 lines) → keeps `BraceExpander` (the textual
    per-word algorithm, now 629 lines); `TokenBraceExpander` (the token-stream
    pass that delegates to it) moves to the new `brace_expansion_tokens.py`.
  - `word_expander.py` (898 lines) → keeps the `WordExpander` engine (762
    lines); its data model — `WordExpansionPolicy` + the named policy instances
    (`COMMAND_ARGUMENT`, `LOOP_ITEM`, `DECLARATION_ASSIGNMENT`,
    `ARRAY_INIT_ELEMENT`, `ASSOC_INIT_ELEMENT`), `ExpandedSegment`, `_WalkState`
    — moves to the new `word_expansion_types.py` (pure data, no shell/AST deps).
- Importers updated to the canonical new locations (no re-export shims): the
  lexer's `TokenBraceExpander` import, and the policy imports in
  `expansion/manager.py`, `io_redirect/file_redirect.py`, `executor/array.py`,
  `executor/control_flow.py`, plus the affected tests.
- Pure code movement: every symbol kept verbatim. Full suite + ruff + mypy green.

## 0.435.0 (2026-06-15) - Tier R9.D1: converge getopt-shaped builtins onto parse_flags
- REFACTOR + BEHAVIOR (bash parity). `command`, `disown`, and `help` now parse
  their boolean options through the shared `Builtin.parse_flags` helper instead
  of hand-rolled loops. Two consequences match bash:
  - Clustered flags work: `command -vp`, `disown -ar`, `help -dm` (previously
    rejected as a single invalid token).
  - Invalid-option diagnostics match bash's format and exit code: e.g.
    `command: -x: invalid option` followed by `command: usage: command [-pVv]
    command [arg ...]`, exit 2 (`disown` previously exited 1 with
    `invalid option: -x`; `help` previously printed `invalid option -- 'x'` and
    a bespoke multi-line usage block).
- Removed the now-dead `HelpBuiltin._show_usage`.
- The other hand-rolled flag parsers are deliberate exceptions, not holdouts:
  `kill` (`-SIGNAL`/`-NUMBER`), `pushd`/`popd`/`dirs` (`+N`/`-N` stack indices),
  `read`/`mapfile`/`print` (many value flags), `getopts`/`shift`/`shopt`/`trap`/
  `set` (own option models) — their `-N`/`-NAME`/value-flag shapes conflict with
  getopt clustering.
- Pinned by new tests; full suite + ruff + mypy green. Zero change to recursive
  descent or any other subsystem.

## 0.434.0 (2026-06-15) - Tier R9.C3 COMPLETE: case bodies by recursion + unified statement-list engine
- REFACTOR (combinator parser). Finishes C3. The `case` item command bodies no
  longer slice tokens until a terminator with a hand-tracked `nesting_depth`
  (plus pattern/`(`-lookahead heuristics); they now parse by recursion via
  `build_statement_list(frozenset({'esac'}), <;; ;& ;;& token types>)`, mirroring
  recursive descent's `parse_command_list_until(*CASE_TERMINATORS, ESAC)`. A
  nested `case` is parsed whole by `self.statement` and consumes its own `esac`,
  so no nesting counter is needed.
- `build_statement_list` gained a `terminator_types` parameter (token-type
  terminators like `;;`) alongside the keyword `terminators`.
- CAPSTONE: the top-level statement list (in `parser.py._build_complete_parser`)
  is now `self.commands.build_statement_list()` — the same engine, with no
  terminator (stops at EOF / `)` / `}`). Brace and subshell groups reuse it
  directly. The duplicated committed-loop closure in parser.py is removed, so
  there is now ONE recursion-based statement-list engine; loops/if/case build
  terminator-specific variants of it. The reviewer's "central irony" is resolved:
  the grammar parses every compound body by recursion, not token-slicing.
- An `esac`-spelled argument in a case body (`a) echo esac;;`) is now a plain
  word (same statement-start-only terminator check as the loop/if fix); pinned
  in `test_combinator_parity_regressions.py`.
- All `tests/parser_differential` parity suites + full suite + ruff + mypy green.
  Zero change to recursive descent.

## 0.433.0 (2026-06-15) - Tier R9.C3 (part 1): loops & if parse bodies by recursion, not slicing
- REFACTOR (combinator parser; the reviewer's "central irony"). The compound-body
  parsers for `while`, `until`, `for`, C-style `for`, `select`, and `if`
  (then/elif/else) no longer slice the body token span out of the stream with a
  hand-tracked `nesting_level` and re-parse it. They now parse bodies by
  *recursion* via a new `CommandParsers.build_statement_list(terminators)` —
  a statement list that stops at (without consuming) its terminator keyword.
  Nested compounds consume their own `done`/`fi`, so the recursion *is* the
  nesting tracker. The `_collect_tokens_until_keyword` slicer is deleted.
- BEHAVIOR (bash divergence fix). An argument that merely spells like a
  terminator keyword inside a loop/if body is now a plain word, matching bash
  and the recursive-descent parser. Previously the by-value slicer mis-detected
  it as the terminator, so `while true; do echo done; break; done` and
  `if true; then echo fi; fi` failed under `--parser combinator`. New parity
  regressions in `test_combinator_parity_regressions.py` pin the fix.
- Once committed past `do`/`then`, a body syntax error now raises at the
  offending token (so `or_else` cannot swallow it and retry as a simple
  command), keeping diagnostics aligned with recursive descent — verified by
  the full `tests/parser_differential` parity suites (AST + error + diagnostic).
- Two isolated unit tests that fed raw (un-normalized) `WORD` tokens and pinned
  the old slicer's flattening artifact ("known limitation: 3 statements") were
  rewritten to parse real source and assert correct nesting (one nested node).
- Zero change to recursive descent (the default parser) or to `case` and
  function/brace/subshell bodies (the latter already parsed by recursion).
  Full suite + ruff + mypy green.

## 0.432.0 (2026-06-15) - Tier R9.D: `[` error messages use the `[` prefix (bash parity)
- BEHAVIOR (bash divergence fix). Errors from the `[` builtin now carry the `[`
  prefix (e.g. `[: 1: unary operator expected`) instead of `test:`, matching
  bash; `test` errors still say `test:`. Previously `[` delegated to a fresh
  `TestBuiltin()` instance, so its errors used that instance's `test` name.
- `BracketBuiltin` now subclasses `TestBuiltin` and evaluates through `self`
  (`self.evaluate_test(...)`), so `self.name == '['` flows to every `self.error`
  prefix. Verified against bash for unary/binary/integer operator errors.
- Added error-prefix tests to `tests/unit/builtins/test_test_builtin.py`.
- Gate: ruff + mypy clean, full suite 8,028 collected / all phases green.

## 0.431.0 (2026-06-15) - Tier R9.C2: combinator core-library hygiene
- ARCHITECTURE (combinator backend; zero behavior change). Cleaned up the
  parser-combinator core (`psh/parser/combinators/core.py`):
  - Removed the vestigial `ParseResult.remaining` field — it was only ever set
    (by `map()` propagating it to itself) and never read for any decision.
  - Unified the backtracking discipline: `Parser.then()` now resets to the
    start position on second-parser failure (atomic), matching `sequence()`;
    previously it leaked the first parser's end position. The only grammar use
    (`many1`) never triggers the branch (its second parser is `many`, which
    cannot fail), so behavior is unchanged — this removes a latent inconsistency.
- Added a unit test pinning the unified `then()` reset-on-failure.
- (Elevate path: the currently-unused combinator primitives — `between`,
  `lazy`, `literal`, etc. — are intentionally retained for the C3 grammar
  rewrite to consume.)
- Gate: ruff + mypy clean, full suite 8,026 collected / all phases green.

## 0.430.0 (2026-06-15) - Tier R9.C1: structured combinator nested-terminator dispatch
- ARCHITECTURE (combinator backend; zero behavior change). Replaced the fragile
  message-substring dispatch in `is_missing_nested_terminator()` with a
  structured `ParseError.missing_terminator` field (the closing keyword
  'fi'/'done'/'esac'), following the existing `at_eof`/`unclosed_expansion`
  structured-signal pattern. First step of elevating the combinator parser to
  first-class.
- `raise_committed_error()` gains a `terminator=` keyword that tags the raised
  `ParseError`; the six fi/done/esac raise sites (if/case in conditionals.py,
  the four loop forms in loops.py) pass it. `is_missing_nested_terminator()` now
  reads the tag instead of lower-casing and substring-matching the message, so a
  message reword can no longer silently break nested-error remapping.
- Updated `test_diagnostics.py` to pin the structured contract (tagged → True,
  untagged → False) rather than message text. Nested-terminator position parity
  with recursive descent is unchanged (verified end-to-end).
- Gate: ruff + mypy clean, full suite 8,025 collected / all phases green.

## 0.429.0 (2026-06-15) - Tier R9.B5: de-duplicate the array-init element loop
- REFACTOR (zero behavior change). The recursive-descent parser had two copies
  of the `name=(...)` element-collection loop — one for statement position
  (`arrays.py`) and one for argument position (`commands.py`, e.g.
  `declare a=(...)`). Extracted the shared loop into
  `CommandParser.parse_array_init_elements()` (plus `_serialize_array_element()`
  for the token-faithful flat-string fragments); both call sites now use it.
- Both paths already built an identical `ArrayInitialization`
  (`elements=[w.display_text() ...]`, `words=<element words>`); the only
  remaining difference (the argument path also rebuilds a token-faithful flat
  string for the argument's literal Word text) is preserved.
- Verified by bash-parity probes across statement/argument position, quoted
  elements, empty arrays, `+=` append, and `$`-expansions. Completes Tier R9.B.
- Gate: ruff + mypy clean, full suite 8,029 collected / all phases green.

## 0.428.0 (2026-06-15) - Tier R9.B3: complete the visitor Word-layer migration
- ARCHITECTURE. Finished routing the analysis visitors through the structured
  Word model (`word_analysis.py`) instead of regexing rendered argument
  strings — the subsystem's stated thesis, previously ~80% true.
- `metrics_visitor.py`: the `SimpleCommand`, `ForLoop`, and `SelectLoop` call
  sites now use a new `_analyze_word_features(word)` that reads the Word parts:
  each `CommandSubstitution` part counts once (so backtick subs no longer
  double-count and `$((...))` is correctly NOT counted as a command sub), and
  variable names come from `iter_variable_references`. `_analyze_string_features`
  is retained only for `CaseConditional.expr` (a plain string in the AST).
  `_count_commands_in_node` now reuses `traversal.iter_child_nodes` instead of a
  hand-rolled `__dict__` walk.
- `linter_visitor.py`: `_check_test_command`/`_check_file_command` take Words and
  detect unquoted variables via `has_unquoted_variable_expansion(word)` rather
  than `arg.startswith('$')` — more accurate (an embedded `pre$f` is now caught;
  quoted `"$f"` correctly is not). Behavior for recognized test operators is
  unchanged.
- These counts/warnings are not pinned by any prior test; the new behavior is
  strictly more accurate. Added `tests/unit/visitor/test_word_layer_migration.py`
  (8 tests) pinning it.
- Gate: ruff + mypy clean, full suite 8,029 collected / all phases green.

## 0.427.0 (2026-06-15) - Tier R9.B4: check_untyped_defs for expansion + executor
- TYPES (zero behavior change). Enabled `check_untyped_defs = true` for
  `psh.expansion.*` and `psh.executor.*` (joining `psh.core.*`), so mypy now
  type-checks the BODIES of un-annotated functions in all three packages — the
  reappraisal's "highest-leverage type win". Fixed the 13 surfaced errors:
  - `psh/expansion/_protocols.py`: added the four slice helpers
    (`_positional_slice_elements`, `_parse_slice_operand`, `_slice_elements`,
    `_slice_scalar_subscript`, defined on `OperatorOpsMixin`) to
    `VariableExpanderProtocol` so `FieldExpansionMixin` type-checks.
  - `psh/expansion/manager.py`: annotated the lazy
    `_evaluator: Optional['ExpansionEvaluator']`.
  - `psh/expansion/brace_expansion.py`: made `_emit_word`'s `segments` a
    uniform `List[Tuple[str, Any, Any]]` (the `'tok'` case is padded with
    `None`) so the heterogeneous discriminated tuples type-check — no behavior
    change (the consumer already branches on `seg[0]`).
  - `psh/executor/pipeline.py`: typed the `visitor` parameters as the concrete
    `ExecutorVisitor` (they always are) so `visitor.context` resolves.
  - `psh/shell.py`: initialized `_errexit_suppress_seed: int = 0` (the
    one-shot set -e suppression seed `SubshellExecutor` sets and
    `_execute_with_visitor` reads).
- The two errors that looked like possible latent bugs were verified benign: the
  brace-expansion tuple is a typing-model artifact (correctly discriminated at
  runtime), and `_errexit_suppress_seed` is a working dynamic seed (read at
  `shell.py` via `getattr`), not a dead write.
- Gate: ruff + mypy clean (227 files), full suite 8,021 collected / all phases
  green.

## 0.426.0 (2026-06-15) - Tier R9.B2: extract HistoryState from ShellState
- ARCHITECTURE (zero behavior change). Second increment of the ShellState
  decomposition. Grouped the command-history list and its persistence settings
  (`history`, `history_file`, `max_history_size`) into a new cohesive
  `psh/core/history_state.py::HistoryState`.
- `ShellState` now owns `self.history_state = HistoryState()` and exposes the
  three names as delegating properties (read + write). The `history` getter
  returns the list by reference, so HistoryManager's in-place
  `append()`/`clear()` and the tests' `state.history = [...]` reassignments
  both keep working — every call site is untouched.
- Added `tests/unit/core/test_history_state.py` (4 tests) pinning defaults,
  in-place mutation by reference, list reassignment, and file/size delegation.
- Gate: ruff + mypy clean (`psh.core.*` `check_untyped_defs=true`), full suite
  8,021 collected / all phases green.

## 0.425.0 (2026-06-15) - Tier R9.B1: extract TerminalState from ShellState
- ARCHITECTURE (zero behavior change). First real increment of the ShellState
  god-object decomposition (the headline gap from the reappraisal). Extracted
  the three controlling-terminal attributes (`is_terminal`, `terminal_fd`,
  `supports_job_control`) and the detection logic that populates them into a
  new cohesive `psh/core/terminal_state.py::TerminalState` — the same "typed
  sub-object" move proven by `StreamBindings`.
- `ShellState` now owns a `self.terminal = TerminalState()` and exposes the
  three attributes as delegating properties (read + write), so all ~23 call
  sites across the codebase are untouched. The old
  `ShellState._detect_terminal_capabilities()` moved to `TerminalState.detect()`
  (taking an explicit `debug` flag instead of reaching into `self.options`).
- Added `tests/unit/core/test_terminal_state.py` (5 tests) pinning the type's
  defaults, the three `detect()` paths (non-TTY, TTY+job-control, TTY-without),
  and the ShellState property delegation.
- Gate: ruff + mypy clean (`psh.core.*` is `check_untyped_defs=true`, so the new
  module is body-checked), full suite 8,017 collected / all phases green.

## 0.424.0 (2026-06-15) - Tier R9.A: dead-code & vestige sweep
- CLEANUP (zero behavior change). First tier of the 2026-06-15 ground-up
  reappraisal (`docs/reviews/ground_up_reappraisal_2026-06-15.md`): removed
  dead/vestigial code flagged across subsystems, each verified truly
  unreferenced before removal.
- Lexer: removed unused `Token.from_basic_token` and `Token.normalized_value`
  (`psh/lexer/token_types.py`).
- Executor: removed uncalled `ExecutionContext.in_loop()`/`in_function()`
  (`context.py`) and the unused `visitor` parameter of
  `SubshellExecutor.execute_subshell()` (subshells fork a fresh Shell and never
  use it; updated the lone call site in `core.py`).
- Expansion: removed dead `AliasManager.save_to_file()`/`load_from_file()`
  (`aliases.py`) and the always-`None` `quote_type` parameter of
  `WordExpander._split_with_ifs()` (updated its caller and the subsystem
  CLAUDE.md doc).
- Core: removed dead `ShellState.history_index`/`current_line` fields
  (`state.py`).
- Interactive: removed the base-class `multi_line_handler = None` field
  (only `REPLLoop` uses it, and sets its own) and the uncalled
  `LineEditor.save_undo_state()` wrapper.
- Parser (recursive descent): fixed a stale comment referencing the
  `array_init.py` module deleted in v0.349.
- Gate: ruff + mypy clean (225 files), full suite 8,012 collected / all phases
  green.

## 0.423.0 (2026-06-15) - Consolidate combinator nested-terminator helper
- PARSER (combinator backend, non-default; pure refactor, zero behavior
  change). Folded the three duplicated `_is_missing_nested_terminator()`
  copies (conditionals, loops, structures) into a single public
  `is_missing_nested_terminator()` in
  `psh/parser/combinators/diagnostics.py`, the shared home for the sibling
  `raise_committed_error()`/`error_context_for_token()` helpers. All
  compound-body parse boundaries now import the one definition.
- Added focused unit tests in
  `tests/unit/parser/combinators/test_diagnostics.py` pinning the helper's
  positive (`fi`/`done`/`esac` "to close") and negative (`then`, `do`,
  pipe, etc.) classifications, including case-insensitivity.
- Gate: ruff + mypy clean (225 files), full suite 8,012 collected / all
  phases green.

## 0.422.0 (2026-06-15) - Align combinator nested-terminator diagnostics
- PARSER (combinator backend, non-default; diagnostics only — accept/reject
  behavior unchanged). For crossed nested terminators (e.g.
  `if true; then while true; do echo x; fi`, `while true; do if true; then
  echo x; done`), the combinator parser now reports the same offending token
  as recursive descent: the missing nested-terminator error from a compound
  body is remapped to the outer terminator position at the if/else, loop,
  select, and case-item body parse boundaries.
- Missing nested terminators inside function bodies are remapped to EOF,
  matching recursive descent for function-body parsing (`f() { if true; then
  echo x; }`).
- Added diagnostic- and rejection-parity cases for crossed if/loop terminators
  and nested if/loop failures inside function bodies; narrowed the documented
  remaining drift (in
  `docs/reviews/combinator_diagnostic_characterization_2026-06-14.md`) to
  malformed case-item bodies and missing-`esac`-inside-body cases.
- Zero behavior change for the default recursive-descent parser; verified no
  accept regressions across a battery of valid nested constructs in if/loop/
  function bodies. Gate: ruff + mypy clean (225 files), full suite 8,004
  collected / all phases green.

## 0.421.0 (2026-06-15) - Expand combinator diagnostic corpus; reject empty compound bodies
- PARSER (combinator backend, non-default). The combinator parser now rejects
  empty compound *bodies* that are syntax errors in bash — empty `then` bodies
  (`if true; then; fi`), empty loop `do`/`done` bodies (`while`, `until`,
  `for`, C-style `for`, `select`), and the stray `;` after `case ... in`
  (`case x in ; esac`) — pointing at the same offending token as recursive
  descent. (These empty-body forms are bash errors in both their `;` and
  newline variants; recursive descent is more lenient on the newline form, so
  the combinator is now the closer match to bash here.)
- Accept/reject boundary preserved for `case`: an *empty case* with no patterns
  (`case x in esac`, including blank/comment-only lines before `esac`) is valid
  bash and remains accepted — only the stray `;` after `in` is rejected. Added
  an `ACCEPTANCE_CORPUS` parity gate in
  `tests/parser_differential/test_combinator_error_parity.py` pinning valid
  empty/zero-iteration constructs for both parsers.
- Broadened the recursive-descent vs combinator rejection and diagnostic-parity
  corpora with nested missing-terminator, separator-edge, and
  compound-trailing-redirection cases; refreshed
  `docs/reviews/combinator_diagnostic_characterization_2026-06-14.md`.
- Zero behavior change for the default recursive-descent parser. Gate: ruff +
  mypy clean (225 files), full suite 7,996 collected / all phases green.

## 0.420.0 (2026-06-15) - Normalize combinator diagnostic positions to source coordinates
- PARSER (combinator backend, non-default). Combinator `ParseError` sites now
  report source-character position, line, and column (from token metadata)
  instead of token-stream indexes, matching the recursive-descent parser.
- Added `error_context_for_token()` to `psh/parser/combinators/diagnostics.py`
  to build `ErrorContext` from a token's source coordinates; routed committed
  diagnostics, top-level combinator parser errors, and the remaining custom
  combinator `ParseError` sites (simple-command redirect, subshell/brace empty
  body) through it.
- Strengthened the recursive-descent vs combinator diagnostic-parity gate to
  assert position, line, and column in addition to exception type, EOF signal,
  and offending-token identity. Message text remains the only intentionally
  unaligned dimension (tracked as follow-up).
- Zero behavior change for the default recursive-descent parser. Gate: ruff +
  mypy clean (225 files), full suite 7,952 collected / all phases green.

## 0.419.0 (2026-06-15) - Centralize combinator committed-error diagnostics
- PARSER (combinator backend, non-default; zero behavior change). Consolidated
  the six duplicated `_raise_committed_error()` helpers (arrays, commands,
  conditionals, loops, structures, enhanced tests) into one shared primitive,
  `psh/parser/combinators/diagnostics.py::raise_committed_error()`, so future
  diagnostic work has a single behavior and type surface to update.
- The shared helper is typed `-> NoReturn` (an improvement over the old local
  `-> None` helpers) and takes `Sequence[Token]`; same EOF clamp
  (`min(pos, len-1)`) and `ErrorContext` construction as before.
- Specialized direct `ParseError`/`ErrorContext` call sites that emit custom
  unexpected-token diagnostics are intentionally left intact (e.g. two in
  `control_structures/structures.py`).
- Added `tests/unit/parser/combinators/test_diagnostics.py` covering
  committed-error token selection and EOF clamping. Gate: ruff + mypy clean
  (225 files), full suite 7,952 collected / all phases green.

## 0.418.0 (2026-06-15) - Combinator command-operator diagnostic alignment
- PARSER (combinator backend, non-default). Missing right-hand commands after
  committed binary command operators (`|`, `|&`, `&&`, `||`) now raise a hard
  `ParseError` carrying the EOF/offending-token diagnostic — matching what
  recursive descent already reports — instead of soft-stopping and letting the
  statement-list level blame the operator token.
- Replaced the soft `many(sequence(operator, command))` operator-loops in
  `psh/parser/combinators/commands.py` with explicit committed loops. Success
  paths are unchanged: each loop's RHS parser is the same parser as its LHS, as
  the old `many(sequence(...))` used.
- Expanded the recursive-descent vs combinator diagnostic-parity corpus with
  missing-RHS (`echo |`, `echo |&`, `echo &&`, `echo ||`) and missing-LHS
  (`|| echo`) cases; refreshed
  `docs/reviews/combinator_diagnostic_characterization_2026-06-14.md` to record
  that no diagnostic-summary drift remains in the starter rejection corpus.
- Zero behavior change for the default recursive-descent parser. Gate: ruff +
  mypy clean (225 files), full suite 7,950 collected / all phases green.

## 0.417.0 (2026-06-15) - Tier R8.6b: alias expansion moved to a token-stream transform
- ARCHITECTURE (review Ugly 1 / A2 — the fenced big-bang). Alias expansion no
  longer happens at runtime by re-lexing joined argv; it is now a TOKEN-STREAM
  transform at the lex→parse boundary, structurally eliminating the
  injection class (args are never reconstructed as source).
- `shell.alias_manager.expand_aliases(tokens)` runs immediately after
  tokenization at the two seams every path converges on:
  `scripting/source_processor.py` (execution parse) and
  `scripting/command_accumulator.py` (trial/completeness parse). Both parser
  backends are covered (transform is parser-agnostic; `-c`/script/stdin/REPL/
  `eval`/`source` all route through `SourceProcessor`).
- `AliasExecutionStrategy` fully removed from `strategies.py` and the
  `command.py` strategy list (no shim needed). The dead `AliasManager.
  expand_aliases` token transform is now live, with `_is_command_position`
  hardened to be keyword-aware so aliases expand in command position inside
  if/while/until/for/case/subshell/brace-group/`&&`/`||`/`|`/`;` and NOT as
  plain args, loop items, case patterns, or the loop var / case selector
  (verified vs bash).
- Decided behaviors (per maintainer): same-line `alias x=…; x` still expands
  (psh divergence kept, via a same-stream definition overlay); `shopt -s/-u
  expand_aliases` now ACCEPTED (recognized no-op gate; psh keeps always-expand);
  quoted command words (`'ll'`) are NOT expanded (bash parity); trailing-space
  chaining now works (bash parity). The deliberate always-expand-non-interactively
  divergence is preserved (pinned `assert_psh_extension` tests stay green).
- Tests: +`test_alias_token_transform_conformance.py` (29),
  +`test_alias_token_transform.py` (17), +9 golden; 3 stale tests that pinned the
  old runtime-strategy behavior updated (each verified vs bash first); the R8.6a
  injection conformance test still passes. Full gate green: ruff + mypy clean
  (225 files), `run_tests.py --parallel` 7613 passed, `--compare-bash` 470.

## 0.416.0 (2026-06-15) - Tier R8.6a: fix the alias-argument injection bug
- BUG FIX (bash-verified; SECURITY-relevant; interim fix ahead of the full
  alias-at-parse-time move). `AliasExecutionStrategy` expanded an alias at
  runtime by joining the already-expanded, quote-removed argv into a source
  string and re-lexing it — so any alias argument containing a shell
  metacharacter was reinterpreted as SYNTAX. `alias e=echo; e 'a; echo PWNED'`
  ran `echo PWNED` as a second command; `e '$(echo X)'`/`e '$FOO'`/`e '*.md'`
  re-expanded the data; `e '>zz'`/`e '|cat'`/`e 'a & b'` turned data into a
  redirect/pipe/background; `e 'a"b'` crashed with a syntax error; quoted
  spaces/tabs split into multiple args.
- Fix: `shlex.quote` each already-expanded argument before the join, so the
  re-lexer treats each as a single literal word. The alias VALUE stays raw (it
  is meant to be parsed as shell). All 10 injection cases now match bash exactly;
  value-is-shell aliases (`alias x='echo a; echo b'`, pipe/redirect in the value),
  recursion guard, bypasses, chains, and the deliberate always-expand behavior
  are unchanged.
- Known still-divergent (deferred to the full token-stream move): trailing-space
  chaining, same-line `alias x=…; x`, quoted-command-word bypass, `shopt -s
  expand_aliases`. The probe battery confirmed these are unchanged (not
  regressed).
- Tests: +`test_alias_argument_injection_conformance.py` (13, bash-pinned). Full
  gate green: ruff + mypy clean (225 files), `run_tests.py --parallel` 7558
  passed, `--compare-bash` 461 passed.

## 0.415.0 (2026-06-15) - Combinator parser: committed compound diagnostics (PR #150)
- REFACTOR (combinator backend only; recursive-descent default parser untouched).
  Follow-on to PR #149. The combinator parser recognized compound openers
  (if/case, while/until/for/select, function forms, brace/subshell groups,
  arrays, `[[ ]]`) but then fell back to GENERIC opening-token failures on
  malformed input. It now raises COMMITTED parse errors after the opener, so its
  diagnostics match recursive descent: EOF/offending-token errors for
  unterminated compounds, malformed case headers, missing function names,
  malformed `[[ … ]]`, and unterminated array initializers.
- `ParserCombinatorShellParser.can_parse()` stays a boolean probe by treating a
  committed `ParseError` as a parse failure (added to its caught exceptions).
- Expanded the RD-vs-combinator diagnostic parity corpus from 9 to 23 stable
  cases; refreshed `docs/reviews/combinator_diagnostic_characterization_2026-06-14.md`
  (remaining starter-corpus drift is now just missing-RHS-command after `|`/`&&`).
- Maintainer-authored (PR #150). Orchestrator added the one mypy narrowing the
  new code needed: the committed-error helper for `[[ ]]` is now typed
  `-> NoReturn` so `EnhancedTestStatement`'s expression narrows to non-None.
- Full gate green: ruff + mypy clean (225 files), `run_tests.py --parallel` 7545
  passed, `--compare-bash` 461 passed.

## 0.414.0 (2026-06-14) - Combinator parser: parity hardening (PR #149) + differential gates
- REFACTOR + TEST INFRA (combinator backend only; recursive-descent default
  parser untouched). Addresses the R8 review's Ugly 9 / A7 (combinator contract)
  by adding recursive-descent-vs-combinator differential gates and fixing the
  first AST/error/diagnostic parity gaps they exposed:
  - New focused combinator array parser `combinators/arrays.py`; bare array
    assignments route through `SimpleCommand.array_assignments` and
    `name=(...)` initializers through the shared `ArrayInitialization` contract
    (parity with the recursive-descent unified array-init), replacing the old
    synthetic-token hack.
  - Redirect target `Word` metadata preserved (`target_word=`, parity with the
    R7.9 ambiguous-redirect work); here-string redirect shape aligned with RD;
    `[[ ]]` operands built from source tokens (parity with the T3.1 per-part
    Word model).
  - Committed parser failures for empty groups, missing redirect operands, and
    statement lists (a committed loop replaces the failure-swallowing `many()`),
    so diagnostics aren't lost into generic top-level errors.
  - New differential suites: `tests/parser_differential/test_combinator_ast_parity.py`,
    `_error_parity.py`, `_diagnostic_parity.py` (+97 tests); remaining diagnostic
    drift documented in `docs/reviews/combinator_diagnostic_characterization_2026-06-14.md`.
- Maintainer-authored (PR #149). Orchestrator added the 10 missing mypy
  narrowings the PR's new combinator code needed (combinators are in mypy scope:
  `ParseResult.value` Optional-narrowing via asserts after success-checks, a
  re-typed init failure result, `setattr`/`getattr` for the dynamic
  `Token.array_init`) before shipping.
- Full gate green: ruff + mypy clean (225 files), `run_tests.py --parallel` 7531
  passed, `--compare-bash` 461 passed.

## 0.413.0 (2026-06-14) - Tier R8.7: check_untyped_defs for psh.core.* (type depth)
- TYPE-CHECKING DEPTH (zero behavior change; remaining review Ugly 10). mypy
  covers 100% of files but `check_untyped_defs` was off globally, so un-annotated
  function BODIES were unchecked. Enabled it for the foundational package via a
  `[[tool.mypy.overrides]]` block (`module = "psh.core.*"`,
  `check_untyped_defs = true`); the global default stays `false`.
- `psh/core/` was already body-clean (14 previously-unchecked bodies, now all
  checked — a strong signal of the package's invariants). The deeper checking
  caught ONE genuine latent type inconsistency, in a caller: `set -o` listing in
  `builtins/environment.py` assigned `dict_keys` in one branch and `list` in the
  other; wrapped the first in `list(...)` (both are only iterated/sorted, so
  runtime is identical).
- Full gate green: ruff + mypy clean (225 files), `run_tests.py --parallel` 7434
  passed, `--compare-bash` 461 passed.

## 0.412.0 (2026-06-14) - Tier R8.5 (1st increment): StreamBindings on ShellState
- REFACTOR (zero behavior change; review Ugly 6 / A5 — first increment, streams
  only). Replaced the ad-hoc dynamic `_custom_stdin`/`_custom_stdout`/
  `_custom_stderr` attributes on `ShellState` with one explicit typed
  `StreamBindings` object (`psh/core/stream_bindings.py`) owning the three stream
  overrides, with an opaque `snapshot()`/`restore(token)` API. `ShellState`'s
  `stdin`/`stdout`/`stderr` properties delegate to it; the public
  `shell.stdout`/`state.stdout` facade is byte-for-byte unchanged (no caller
  changed except the one executor seam that explicitly saves/restores override
  state — `command.py` `_execute_builtin_with_redirections` now uses
  `streams.snapshot()`/`restore()` instead of `getattr`/`setattr`/`delattr`
  juggling).
- Getter semantics preserved exactly: an override if set, else live `sys.std*`
  (so pytest's post-construction `sys.*` replacement is still seen). The
  io_redirect `_BuiltinStreamSnapshot`/`_ClosedStream` swaps (which act on
  `sys.std*` directly) are unaffected.
- An 11-scenario characterization harness (builtin redirect+restore, `exec >file`
  builtin/external interleave, `2>&1`, `1>&-` closed-fd, brace-group closed-fd,
  subshell/command-sub inheritance, `env` child streams, nested `eval`+`3>&1`)
  is byte-identical. Rest of `ShellState` (options/history/exec flags/terminal)
  untouched — later increments.
- Full gate green: ruff + mypy clean (225 files), `run_tests.py --parallel` 7434
  passed, `--compare-bash` 461 passed.

## 0.411.0 (2026-06-14) - Tier R8.4: visitor analysis over the Word AST
- REFACTOR + tooling-fidelity (review Ugly 8 / A6). The analysis visitors
  (enhanced-validator/linter/security) did variable-reference and word
  classification by regexing rendered `node.args` strings, even though
  `Word.parts` is authoritative. New `psh/visitor/word_analysis.py` provides
  structured helpers — `iter_variable_references(word)` (→ `VariableReference`
  with name/quoted/braced/array-subscript/default/part), `referenced_variable_
  names`, and classifiers (`has_command_substitution`/`has_arithmetic_expansion`/
  `is_arithmetic_only`/`has_unquoted_variable_expansion`/…). The three visitors
  now inspect the Word AST; regex helpers (`_extract_variable_name`,
  `var_patterns`, `_check_variable_usage`, the dead string `has_unquoted_expansion`)
  are deleted. A documented string fallback remains only for operator words
  (`${x:-$y}`) and `Redirect` target/heredoc strings.
- Diagnostic-output changes (all justified, ZERO regressions): removed false
  positives — `echo '$FOO'` (single-quoted, literal), `for f in $(ls)` /
  `` `ls` `` ("undefined var" on a command sub), bogus "unquoted $@" on
  `echo "$@"`. New genuinely-correct findings — `` `date` `` now flagged for
  word-splitting (parity with `$(date)`); `${FOO:-${BAR}}` reports `BAR`
  undefined.
- Tests: +`test_word_analysis.py` (34) +`TestWordAnalysisStructuralFindings`
  (12). Full gate green: ruff + mypy clean (224 files), `run_tests.py --parallel`
  7434 passed, `--compare-bash` 461 (no runtime regression).

## 0.410.0 (2026-06-14) - Tier R8.3: typed command-invocation data flow
- REFACTOR (zero behavior change; review Ugly 2/3 / A1). Replaced the
  `(exit_code, is_special)` tuple side-channel in simple-command execution with
  typed data in `psh/executor/command.py`:
  - `ExecutionResult(status, prefix_assignments_persist)` — `_execute_with_strategy`
    now returns this; `_run_command` reads the NAMED field instead of unpacking a
    positional boolean to decide prefix-assignment persistence.
  - `CommandResolution(strategy, prefix_assignments_persist)` — `_execute_with_strategy`
    is now a thin two-phase coordinator: `_resolve_command` (walks the
    priority-ordered strategies + `\cmd` bypass, computes the persistence policy
    once — previously an inline `isinstance(SpecialBuiltinExecutionStrategy)`)
    then `_invoke_resolution`. `strategies.py` untouched; the split sits above it.
- A 39-case frozen characterization harness (special-vs-normal prefix
  persistence for `:`/`.`/`eval`/`set`/`unset`/`export`/`readonly` vs normal
  builtins/functions/externals; normal/127 execution; pure/array assignments;
  `exec`/`set -e`/xtrace/`$_`/background) is byte-identical before/after.
- Deferred R8.3b: the deeper `_execute_command` phase pipeline + `SimpleCommandPlan`
  (extracting a plan risks reordering POSIX-sensitive steps). Noted (pre-existing,
  out of scope): psh persists `FOO=bar export X=1` where bash `-c` does not.
- Full gate green: ruff + mypy clean (223 files), `run_tests.py --parallel` 7387
  passed, `--compare-bash` 461 passed.

## 0.409.0 (2026-06-14) - Tier R8.2: redirect-primitive boundary (public shared surface)
- REFACTOR (zero behavior change; review Ugly 7 / A4). The builtin stream-redirect
  backend (`IOManager`) reached into `FileRedirector` PRIVATE methods that are
  actually shared redirect primitives. Promoted the 10 genuinely-shared ones to
  a documented public surface (dropping the leading underscore):
  `redirect_input_from_file`, `redirect_readwrite`, `redirect_heredoc`,
  `redirect_herestring`, `check_noclobber`, `noclobber_blocks`, `dup_fd_valid`,
  `expand_redirect_target`, `resolve_dynamic_dup` (was `_resolved`),
  `procsub_handler`. Methods used only inside `file_redirect.py` stay private; the
  `RedirectPlan`/`RedirectPlanner`/`apply_fd_plan` layer is untouched.
- Added a class docstring documenting the public-primitive vs private contract;
  updated `io_redirect/CLAUDE.md` (helper table split public/private) and the
  arch docs that named the old private methods.
- A characterization harness over builtin + external redirect paths (read-from-
  file, heredoc, here-string, `<>`, noclobber block/clobber/new, `>&-`, fd dup,
  `&>`, `2>&1`, dynamic dup, ambiguous redirect) is byte-identical before/after.
- Full gate green: ruff + mypy clean (223 files), `run_tests.py --parallel` 7387
  passed, `--compare-bash` 461 passed.

## 0.408.0 (2026-06-14) - Tier R8.1: control-flow context helpers (+2 latent bug fixes)
- REFACTOR (zero behavior change for the extracted scaffolding) + 2 latent bug
  fixes toward bash. `ControlFlowExecutor` repeated the same boilerplate across
  while/until/for/case/if/select/C-style. Extracted four helpers:
  `_compound_redirections(node)` (apply node redirects to the whole body,
  restore), `_pipeline_context_disabled(context)` (save/reset/restore
  `in_pipeline`), `_loop_depth(context)` (depth inc/dec), and
  `_reraise_loop_control(exc, context)` (shared `break N`/`continue N`
  level-decrement). Each construct now reads as its control logic, not a
  try/finally maze.
- A 41-case characterization harness (whole-body redirects, nested break/
  continue with levels, `set -e` failing-condition vs body, compound-as-pipeline
  member, exit codes) is byte-identical before/after.
- LATENT BUGS FIXED (the deliberate uniformity from the R8 review): C-style
  `for ((;;))` AND `select` omitted the `in_pipeline` reset, so a body with an
  EXTERNAL command exec-replaced the forked child and the loop ran ONCE when used
  as a pipeline member. `for ((i=0;i<3;i++)); do /bin/echo q$i; done | cat` was
  `q0` only, now `q0 q1 q2` (matches bash); same for `select`.
- Tests: +`test_compound_in_pipeline_conformance.py` (5). Full gate green: ruff
  + mypy clean (223 files), `run_tests.py --parallel` 7387 passed,
  `--compare-bash` 461 passed.

## 0.407.0 (2026-06-14) - Docs: Tier R8 architecture roadmap
- DOCS ONLY. Added the maintainer's `docs/reviews/fresh_architecture_review_
  2026-06-14.md` (a fresh structural review, inspected at v0.400) and
  `docs/reviews/tier_r8_architecture_roadmap_2026-06-14.md`, which reconciles it
  with the post-R7 tree and defines Tier R8 — targeted architectural seam work
  (not bug-fixing): R8.1 control-flow context helpers, R8.2 redirect-primitive
  boundary, R8.3 typed command-invocation data flow, R8.4 visitor analysis over
  the Word AST, R8.5 gradual ShellState decomposition, R8.6 resolver/invoker
  split + alias-at-parse-time (fenced big-bang), R8.7 `check_untyped_defs`
  deepening.
- Notes what the review already overtook post-v0.406: mypy file coverage is 100%
  (Ugly 10/A8 done bar `check_untyped_defs`); validator false positives fixed in
  R7.9 (Ugly 8 partial); combinator backend typed + declared educational.

## 0.406.0 (2026-06-14) - Tier R7: mypy now covers 100% of psh source files
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 lever — completed).
  Added the final 10 modules: `psh/__init__.py`, `psh/__main__.py`,
  `psh/interactive/__init__.py`, and the previously-deferred combinator
  command/control-structure mixins (`combinators/commands.py`, `parser.py`,
  `control_structures/{conditionals,loops,structures}.py` + `__init__`s).
  **mypy now type-checks ALL 222 `psh/` source files** (223 in scope incl. the
  new Protocol helper).
- The combinator mixins were unlocked with a `ControlStructureProtocol`
  (`combinators/control_structures/_protocols.py`) declaring the shared
  `commands`/`tokens`/`_parse_trailing_redirects`/`_collect_tokens_until_keyword`
  surface, mixed in ONLY under `if TYPE_CHECKING:` (the `_Base = Protocol if
  TYPE_CHECKING else object` idiom — zero runtime change), mirroring the
  expansion-mixin approach; cleared ~50 `attr-defined` errors. The wiring point
  bridges with a documented `cast` (runtime None-handling unchanged).
- Remaining type-checking depth (not file coverage): `check_untyped_defs` is
  still off globally, so untyped function BODIES aren't checked — a possible
  future per-package deepening.
- Reappraisal #7 mypy campaign summary: **scope grew 85 → 223 files** across
  v0.391–v0.406 (lexer, parser, expansion incl. mixins, io_redirect, executor,
  builtins, interactive, scripting, visitor, utils, core — everything).
- Full gate green: mypy clean (223 files), ruff clean, `run_tests.py --parallel`
  7382 passed.

## 0.405.0 (2026-06-14) - Tier R7: grow mypy scope into all of psh/builtins (177 → 212 files)
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 lever). Added the
  ENTIRE `psh/builtins/` package (all 35 modules) to the mypy `files` list; mypy
  now covers **212 source files** (~95% of the tree). Nothing deferred.
- Real bug caught by the wider scope: `read_builtin.py` used `Dict[str, any]`
  (the builtin `any`, not `typing.Any` — which wasn't even imported) on three
  method signatures; a meaningless annotation any type checker rejects. Fixed.
- Behavior-preserving type work: Optional-narrowing on registry/array `.get()`
  results (keys come from `indices()`/`keys()`, always present), renamed
  loop/branch vars whose inferred type changed mid-function, `setattr`/`getattr`
  for the dynamic `err.rc` attribute, a few `TYPE_CHECKING` imports, and a pure
  class-level `directory_stack: Any` annotation on `ShellState` (no runtime
  assignment — preserves the lazy hasattr-guarded creation).
- Full gate green: mypy clean (212 files), ruff clean, `run_tests.py --parallel`
  7382 passed.

## 0.404.0 (2026-06-14) - Tier R7.9: ambiguous redirect + validator false positives (clears R7 bug list)
- BUG FIX (bash-verified; reappraisal #7 L3 + the recorded ambiguous-redirect
  follow-up, and L7).
- L3 a redirect target that (unquoted) expands to zero or more than one word is
  now an `ambiguous redirect` (exit 1), matching bash — fixing both the doubled
  `psh: No such file or directory: …` message on an empty target (`> $undef`)
  and the silently-exit-0 multi-word case (`v="a b"; > $v`). Detection falls out
  of expansion: a parsed `Redirect.target_word` (new field) is run through
  `expand_word_to_fields` (full pipeline incl. splitting/globbing); ≠1 field →
  `OSError("{word.source_text()}: ambiguous redirect", errno=None)` via the
  existing parent-raise / child-exit error paths. Quoted `> "$v"`, single-word,
  single-match glob, no-match-literal, and process-substitution targets are
  unaffected.
- L7 `--validate`/`EnhancedValidatorVisitor` false positives removed: array
  assignments (`x=(…)`, `x+=(…)`, `arr[0]=…`) now register the name as defined;
  C-style `for ((i=0;…))` init vars are registered; `$((…))` arithmetic is no
  longer misclassified as an unquoted variable expansion. Genuine
  undefined-variable warnings are retained.
- Tests: +`test_reappraisal7_ambiguous_redirect_conformance.py` (15, builtin +
  forked-child),  +`TestFalsePositiveRegressions` (8). Full gate green: ruff +
  mypy clean, `run_tests.py --parallel` 7382 passed, `--compare-bash` 461 passed.
- This CLEARS the reappraisal #7 bug list: all 5 HIGH, 9 MEDIUM, 7 LOW fixed
  except M8 (NUL termination), deferred into the byte-model/surrogateescape work
  alongside M7-from-#6.

## 0.403.0 (2026-06-14) - Tier R7.8: four feature gaps (M9 !!:-n, @K/@k, read -N, set -o history)
- BUG FIX (bash-verified; reappraisal #7 M9/L4/L5/L6).
- M9 `!!:-n` history word designator aborted with "bad word specifier"; it now
  expands as `:0-n` (word 0 through word n), e.g. `!!:-2` → first three words.
  (`history_expansion.py`)
- L4 `${var@K}` / `${var@k}` transforms were silent no-ops; now match bash: `@K`
  → one string `key "value" …` (keys bare, values @A-escaped+quoted); `@k` →
  separate unquoted `key value …` fields; scalar/element → the @Q-quoted value.
  (`operators.py`, `variable.py`, `fields.py`, `arrays.py`) Only residual diff is
  assoc-array hash-vs-insertion key order (pre-existing, same as `@A`).
- L5 `read -N count` implemented: reads EXACTLY count chars ignoring the
  delimiter and IFS (vs `-n`'s at-most-with-delimiter), short EOF → rc 1.
  (`read_builtin.py`)
- L6 `set -o history` / `set +o history` were rejected ("invalid option name");
  now accepted and meaningfully wired — `set +o history` disables history
  recording, and `set -o` reflects the state. (`state.py`, `shell.py`)
- Tests: +`test_param_transform_keyvalue_conformance.py` (14),
  +`test_read_exact_chars_conformance.py` (7), +`test_set_o_history_conformance.py`
  (4), +M9 unit case. Full gate green: ruff + mypy clean, `run_tests.py
  --parallel` 7359 passed, `--compare-bash` 461 passed.

## 0.402.0 (2026-06-14) - Tier R7.7: two syntax-error LOWs (L1 unterminated quote, L2 empty groups)
- BUG FIX (bash-verified; reappraisal #7 L1/L2) — psh now reports a syntax error
  (exit 2) where bash does.
- L1 an unterminated quote (`echo 'abc`, `echo "abc`, `echo $'abc`) exited 1 with
  `unexpected error: Unclosed ' quote` (it was misrouted to the internal-defect
  handler because `UnclosedQuoteError` subclasses `SyntaxError`, not
  `ParseError`). `source_processor` now catches `UnclosedQuoteError` → `psh:
  <loc>: syntax error` exit 2, matching the already-correct `$((`/`$(`/`${`
  unterminated handling. Interactive multi-line continuation is unaffected.
- L2 an empty subshell `()` / brace group `{ }` (and whitespace/comment-only
  variants) silently succeeded (exit 0); bash requires ≥1 command → syntax error
  exit 2. `parse_subshell_group`/`parse_brace_group` now reject an empty inner
  command list. Non-empty groups, nested groups, command substitution `$()`
  (legitimately empty), and arithmetic `(())` are unchanged.
- Tests: +`test_reappraisal7_syntax_errors_conformance.py` (23, exit-code vs
  bash); updated `test_empty_subshell` which pinned the old exit-0 behavior;
  refreshed README Project-Statistics file counts (drifted past the meta-test's
  10% gate). Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7329
  passed, `--compare-bash` 461 passed.

## 0.401.0 (2026-06-14) - Tier R7: mypy scope — all of io_redirect + executor (177 files); +bug fix
- TYPE-CHECKING SCOPE (reappraisal #7 lever). Added 17 modules so the ENTIRE
  `psh/io_redirect/` and `psh/executor/` packages are now type-checked: mypy
  covers **177 source files** (~80% of the tree). Nothing deferred in these two
  packages.
- BUG FIX caught by the wider scope (bash-verified): `_execute_in_background`
  was called on `BuiltinExecutionStrategy` but the method is named
  `_execute_builtin_in_background`, so backgrounding a POSIX special builtin
  (`: &`) raised `AttributeError` instead of running silently (bash: exit 0, no
  output). Fixed + regression test in `test_background_jobs.py`.
- Behavior-preserving type work: TYPE_CHECKING-only `redirects`/`background`
  annotations on the base `Command`; `ShellState.set_variable(value: Any)` (it
  legitimately receives array objects on scalar-append-to-array); `@overload` on
  `job_control.wait_for_job`'s dual return; array element-assignment key
  narrowing (extracted `_compute_element_value`); pipeline `pgid`/`pids`
  narrowing; assorted local annotations.
- Full gate green: mypy clean (177 files), ruff clean, `run_tests.py --parallel`
  7306 passed, `--compare-bash` 461 passed.

## 0.400.0 (2026-06-14) - Tier R7.6: in-process builtin honors a closed output fd
- BUG FIX (bash-verified; reappraisal #7 M1). `echo hi 1>&-` leaked `hi` to real
  stdout (and the brace-group/function paths leaked too): a builtin writes
  through the Python `sys.stdout`/`shell.stdout` object, but `>&-` only closed
  fd 1 at the fd level. Now closing fd 1/2 for an in-process builtin swaps the
  matching Python stream to a `_ClosedStream` (writes raise `OSError(EBADF)`),
  recorded in the snapshot so restore reinstates the original.
- Centralized the write-error handling in `executor/strategies.py`
  `execute_builtin_guarded`: a builtin's `OSError(EBADF/EPIPE)` on write now
  becomes bash's `NAME: write error: <strerror>` (exit 1) for EVERY builtin
  (was previously misclassified as an internal defect; `pwd` etc. now correct,
  not just echo/printf).
- Also fixed a pre-existing freed-fd-reuse bug: `cmd 1>&- 2>FILE` opened FILE
  onto the just-freed fd 1 then corrupted the shell's stdout on restore; the
  fd-level close is now deferred until after the command's other redirects
  (bash opens targets on high fds for the same reason).
- `2>&-` (closes only stderr), `<&-` (input close), normal output, and
  restore-after (`echo hi 1>&-; echo back` → `back`) all verified correct.
- Tests: +`test_reappraisal7_close_output_fd_conformance.py` (16 subprocess),
  +7 golden. Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7305
  passed, `--compare-bash` 461 passed.

## 0.399.0 (2026-06-14) - Refactor: share the redirect fd-backend application
- REFACTOR (zero behavior change). Finishes the RedirectPlan work by removing the
  remaining duplication across the three redirect dispatch sites. Two new
  `FileRedirector` helpers: `apply_fd_plan(plan, *, check_noclobber=True)` (the
  single fd-universe application switch over all redirect types) and
  `saved_fds_for_plan(plan)` (centralized save-fd selection). `apply_redirections`,
  `apply_permanent_redirections`, and `setup_child_redirections` all route
  through `apply_fd_plan`, each keeping its own distinct responsibilities — the
  parent's transactional save/restore, the permanent path's stream rebinds, and
  the child's `os._exit`-based error reporting (errno-bearing OSErrors →
  `psh: TARGET: STRERROR`; psh's own `errno=None` noclobber/dup messages →
  `psh: {e}`). The ~50-line duplicated child block collapses to one call.
- Saved-fd annotations tightened to `Tuple[int, int | None]` to reflect the
  high-fd restore case (`7>file`) where the original fd was unopened — already
  handled by `restore_redirections` (closes what it opened).
- Net −39 lines. Authored by the maintainer (PR #134); shipped through the
  release ritual after orchestrator verification: child-path noclobber/bad-fd
  probes match bash (message body + exit code), ruff + mypy clean (160 files),
  `run_tests.py --parallel` 7282 passed, `--compare-bash` 447 passed.

## 0.398.0 (2026-06-14) - Tier R7: mypy scope — expansion mixins + last interactive (160 files)
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 lever). Added 7 more
  modules → mypy now covers **160 source files**:
  - The four expansion MIXINS `arrays.py`/`fields.py`/`operands.py`/
    `operators.py` via a new `psh/expansion/_protocols.py` `VariableExpanderProtocol`
    (a `typing.Protocol` declaring the shared `state`/`shell`/`param_expansion`
    surface + cross-mixin methods). Each mixin declares it as a base ONLY under
    `if TYPE_CHECKING:` (the `_Base = Protocol else object` idiom) — zero runtime
    MRO/behavior change; cleared ~80 `attr-defined` errors.
  - `psh/interactive/line_editor.py` and `psh/utils/signal_utils.py` — the last
    two flagged interactive/util gaps.
- Real fixes the wider scope surfaced (behavior-preserving): latent
  `Optional[str]` operand flows in `operators.py` narrowed with `assert operand
  is not None` (mirrors the existing `variable.py` pattern; `None` only occurs
  for the separately-handled `${#var}` length); `signal_utils.SIGNAL_NAMES`
  typed `Dict[int,str]` (was inferred `Dict[Signals,str]`, breaking int-keyed
  `.get`); `line_editor.key_handler` typed as the binding union.
- Full gate green: mypy clean (160 files), ruff clean, `run_tests.py --parallel`
  7282 passed, `--compare-bash` 447.

## 0.397.0 (2026-06-14) - Tier R7.5: ~+/~-/~N tilde + "${!prefix@}" field-split
- BUG FIX (bash-verified; reappraisal #7 M3/M2).
- M3 `~+`/`~-`/`~N`/`~+N`/`~-N` tilde forms now expand: `~+`→`$PWD`, `~-`→
  `$OLDPWD`, `~N`/`~+N`→`dirs +N`, `~-N`→`dirs -N`; out-of-range/invalid stays
  literal. Two-part fix: the lexer (`recognizers/literal.py`) no longer split
  `~+` into two words (the `+` terminator broke it into `~`→$HOME + `+`), and
  `tilde.py` gained dir-stack/PWD/OLDPWD prefix handling. `echo ~+` → was
  `/Users/pwilson+`, now `$PWD`. Quoted `"~+"` and non-word-start `x~+` stay
  literal.
- M2 `"${!prefix@}"` now field-splits (one field per matched name, like `"$@"`):
  `x1=a x2=b; printf "[%s]" "${!x@}"` → was `[x1 x2]`, now `[x1][x2]`; `set --
  "${!x@}"; echo $#` → 2. The quoted `@`-form was reaching the scalar
  (space-joined) path; `fields.py` now routes `!@` through
  `match_variable_names`, distributing affixes like `"${arr[@]}"`. The `"${!x*}"`
  join-form and unquoted forms (already correct) are unchanged.
- Tests: +`test_dirstack_tilde_conformance.py` (13),
  +`test_prefix_indirection_fields_conformance.py` (10), +4 golden. Full gate
  green: ruff + mypy clean, `run_tests.py --parallel` 7282 passed,
  `--compare-bash` 447 passed.

## 0.396.0 (2026-06-14) - Tier R7: grow mypy scope into psh/parser (122 → 153 files)
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 lever). Added 31
  `psh/parser/` modules to the mypy `files` list: the recursive_descent backend
  (all 8 sub-parsers + support/context/helpers + the main parser), the AST
  visualization renderers, and the combinator core/tokens/utils/expansions/
  special_commands/heredoc. mypy now covers **153 source files**.
- Real type-bug fixes the wider scope surfaced (behavior-preserving): in
  `ast_nodes/redirects.py`, `Redirect.target` retyped `Optional[str]` (None is
  the runtime value for `>&-`/`2>&1` fd-dup/close forms) and the dynamically-set
  `heredoc_key` made an explicit `Optional[str]` field; `EnhancedTestStatement`
  now inherits `(Statement, CompoundCommand)` to match its runtime placement in
  `Pipeline.commands`; `formatter_visitor` guards a `None` close-redirect target
  (was a latent `TypeError`); `combinators/core.ParseResult.remaining` implicit-
  Optional fixed.
- Deferred (too noisy — mixin self-type plumbing): `combinators/commands.py` and
  `combinators/control_structures/*` (the combinator parser is educational-only,
  outside the production bar) — a `Protocol` would unlock them later.
- Full gate green: mypy clean (153 files), ruff clean, `run_tests.py --parallel`
  7255 passed, `--compare-bash` 439.

## 0.395.0 (2026-06-14) - Tier R7.4: SECONDS= / RANDOM= assignment (computed specials)
- BUG FIX (bash-verified; reappraisal #7 M6/M7). `SECONDS` and `RANDOM` were
  computed on READ but assignment was silently dropped (the read interceptor
  shadowed any stored value). Added a settable-computed-variable mechanism in
  `psh/core/scope.py`: assignment to an active SECONDS/RANDOM is intercepted
  (coerced to a signed int; non-integer → 0, like bash), records a baseline/seed,
  and `unset` reverts the name to an ordinary variable.
- M6 `SECONDS=N` now honored: `SECONDS=100; echo $SECONDS` → `100` (was `0`);
  `SECONDS=0; sleep 1; echo $SECONDS` → `1`.
- M7 `RANDOM=N` now seeds — and matches bash VALUE-FOR-VALUE: implemented bash
  5.x's exact generator (Park-Miller minimal-standard with Schrage; result
  `((seed>>16) ^ (seed&0xFFFF)) & 0x7FFF`). `RANDOM=1; echo $RANDOM $RANDOM
  $RANDOM` → `16807 10791 19566`, identical to bash. (Also fixed a latent
  side effect: `resolve_nameref_name` no longer advances RANDOM when merely
  inspecting the nameref flag.)
- Tests: +`TestSecondsAssignment` (8, bounded timing), +`TestRandomSeeding` (9),
  +`test_computed_special_vars_conformance.py` (`assert_identical_behavior`),
  +5 golden. Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7255
  passed, `--compare-bash` 439 passed.

## 0.394.0 (2026-06-14) - Tier R7.3: signal name/number bugs (kill -l, trap -l)
- BUG FIX (bash-verified; reappraisal #7 M4/M5). Established a SINGLE SOURCE OF
  TRUTH for signal name↔number in `psh/utils/signal_utils.py`, built from
  Python's `signal.Signals` enum (platform-correct: SIGEMT=7/SIGINFO=29 on
  macOS, self-adjusting on Linux), and routed `kill` and `trap` through it; the
  two divergent hand-maintained tables in `kill_command.py` were deleted.
- M4 `kill -l N`/`NAME`: `kill -l 9` → was an error, now `KILL`; `kill -l KILL`
  → was an error, now `9`; `kill -l 15`→`TERM`, `kill -l TERM`→`15`, `kill -l
  137`→`KILL` (N-128), `kill -l 0`→`EXIT`.
- M5 `kill -l` / `trap -l` (no arg): were garbled — `kill -l` omitted SIGEMT/
  SIGINFO (`7) 7`) with a non-bash layout; `trap -l` lexically sorted a map with
  pseudo-signals + duplicate rows. Both now render byte-identical to bash (and to
  each other) via `list_all_signals()`. `trap -p` SIG-prefix and signal sending
  unaffected.
- Tests: +`test_signal_listing_conformance.py` (12, `assert_identical_behavior`
  so platform numbers self-adjust). Full gate green: ruff + mypy clean,
  `run_tests.py --parallel` 7224 passed, `--compare-bash` 429 passed.

## 0.393.0 (2026-06-14) - Tier R7: grow mypy scope into the whole lexer (94 → 122 files)
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 lever). Added the
  ENTIRE `psh/lexer/` package (28 modules — pure_helpers, position, recognizers,
  modular_lexer, heredoc, cmdsub_scanner, keyword_normalizer, command_position,
  …) to the mypy `files` list. The lexer was previously the single largest
  untyped area; mypy now covers **122 source files**.
- Mostly annotation-only. Real fixes the wider scope surfaced (behavior-
  preserving): whitespace/comment recognizers' `(None, pos)` skip sentinel now
  matches a widened `Optional[Tuple[Optional[Token], int]]` return contract;
  `Dict[str, any]` (builtin `any`) → `Dict[str, Any]` in the heredoc lexer;
  Optional defaults and TYPE_CHECKING forward-refs in the quote/expansion
  parsers; None-narrowing in `token_stream`/`cmdsub_scanner`. The
  `token.heredoc_key` dynamic-attribute signal was deliberately kept dynamic
  (its presence is load-bearing) with an explanatory comment.
- Full gate green: mypy clean (122 files), ruff clean, `run_tests.py --parallel`
  7212 passed.

## 0.392.0 (2026-06-14) - Tier R7.2: three HIGH bugs (keyword-as-arg, shebang, pipeline prefix-env)
- BUG FIX (bash-verified; reappraisal #7 H1/H4/H5).
- H1 a keyword used as a plain ARGUMENT caused a parse error: `echo if then` →
  was a parse error, now `if then` (also `echo while do done`, `cat -- if
  then`). `keyword_normalizer._next_command_position` kept "command position"
  whenever a WORD's *value* spelled `if`/`while`/`until`; removed that branch
  (a real control keyword already carries its own token type). Real control
  structures, `time`, function defs, and post-`;`/`|`/`&&` keyword recognition
  all unchanged.
- H4 `psh script.sh` honored the script's `#!shebang` (re-dispatching e.g. to
  python3) instead of treating it as a comment like bash/sh/dash. Removed the
  shebang dispatch from the explicit-FILE path and DELETED the now-unused
  `psh/scripting/shebang_handler.py`. The exec path (`psh -c './x.sh'`) still
  respects the shebang via the kernel (unaffected).
- H5 a prefix assignment wasn't in the environment of an external command:
  `FOO=bar env | grep ^FOO` → was empty, now `FOO=bar`. Root: `apply_prefix`
  set the var without the EXPORT attribute, so `sync_exports_to_environment`
  dropped it from `shell.env` (this affected the `env` builtin generally, not
  just pipelines). `apply_prefix` now sets EXPORT and `restore` removes it for a
  previously-unexported var; export status of pre-existing vars is preserved.
- Tests: +`test_keyword_as_argument_conformance.py` (20),
  +`test_script_shebang_is_comment.py` (6 subprocess), +10 prefix-assignment
  cases, +7 golden. Full gate green: ruff + mypy clean, `run_tests.py
  --parallel` 7212 passed, `--compare-bash` 429 passed.
- Known deferred (pre-existing): `time` before a COMPOUND command still
  parse-errors (psh only supports `time SIMPLE_COMMAND`).

## 0.391.0 (2026-06-14) - Tier R7: grow mypy scope (arithmetic + executor/io small modules)
- TYPE-CHECKING SCOPE (zero behavior change; reappraisal #7 quality lever).
  Expanded the mypy `files` list from 85 → **95 source files**, all 100% clean:
  added the whole `psh/expansion/arithmetic` subpackage (7 files; self-contained,
  no mixin-self-type problem) plus `psh/io_redirect/planner.py`,
  `psh/executor/child_policy.py`, `psh/executor/process_launcher.py`.
- The three executor/io modules were already annotation-clean (zero edits). The
  arithmetic subpackage needed minor behavior-preserving edits: a real
  same-name/two-types fix in `parser.py` (a local rebound to both `ArithToken`
  and `ArithTokenType` → renamed), 3 `cast(...)` narrowings where
  `ArithToken.value` (`Union[str,int]`) is type-guaranteed, and None-narrowing
  rewrites of 8 tokenizer scan loops (capture `current_char()` into a local) —
  identical runtime behavior.
- Full gate green: mypy clean (95 files), ruff clean, `run_tests.py --parallel`
  7169 passed.

## 0.390.0 (2026-06-14) - Tier R7.1: two HIGH expansion bugs (extglob #, nameref arrays)
- BUG FIX (bash-verified; reappraisal #7 H2/H3).
- H2 `${var#pat}` shortest-prefix removal was greedy/broken with extglob:
  `shopt -s extglob; v=ooo; echo "${v#+(o)}"` → was empty, now `oo`. Root: a
  naive `regex.replace('.*','.*?')` never touched extglob quantifiers and
  `extglob_to_regex(from_start=True)` emitted a `$`-anchored regex, so `#`
  behaved like `##` (and `##` itself was broken too). Rewrote
  `remove_shortest_prefix`/`remove_longest_prefix` to mirror the correct suffix
  path (scan prefix lengths, full-match each candidate). (`parameter_expansion.py`)
- H3 namerefs didn't dereference on ARRAY reads: `declare -a arr=(10 20 30);
  declare -n r=arr; echo "${r[@]}"` → was `arr`, now `10 20 30`; `${r[1]}`,
  `${#r[@]}`, `${!r[@]}`, associative namerefs, and slicing all fixed. Added a
  single nameref-aware array-name resolution point (`_resolve_array_name` in
  `ArrayOpsMixin`) and routed every array read/write site through it
  (`arrays.py`, `variable.py`, `fields.py`, `operators.py`,
  `executor/array.py`). Element-nameref `declare -n r=arr[1]` matches bash; the
  write path (`r[3]=x` → `arr[3]`) resolves too; non-nameref arrays unchanged.
- HYGIENE: added `.claude/` to `.gitignore` (worktrees + agent transcripts must
  never be committed).
- Tests: +`test_extglob_parameter_expansion_conformance.py` (33),
  +`test_nameref_array_conformance.py` (17); removed an obsolete xfail that
  pinned the old broken extglob behavior. Full gate green: ruff + mypy clean,
  `run_tests.py --parallel` 7169 passed, `--compare-bash` 415 passed.

## 0.389.0 (2026-06-14) - Docs: ground-up reappraisal #7 (post-R6 scorecard)
- DOCS ONLY. Added `docs/reviews/ground_up_reappraisal_7_2026-06-14.md`: a fresh
  five-cluster scorecard taken after the Tier R6 bug-fix campaign.
- Scorecard: overall **A−** (stable). Core/Builtins promoted B+→A− (R6 cleared
  its read/declare bug density); the other four clusters held A−. All R6 fixes
  verified clean with no regressions. mypy scope ~85/222 files (~38%).
- Deeper fresh-eyes probing found a NEW bash-verified bug list (not in #6): 5
  HIGH (keyword-as-arg `echo if then` parse error; `${var#}` shortest-prefix
  greedy with extglob; namerefs don't deref on array reads; `psh script.sh`
  honors a foreign shebang; prefix-assignment not exported to an external
  command in a pipeline), 9 MEDIUM, 7 LOW — plus the half-finished mypy lever.
  Defines the "Tier R7" worst-first bug-fix phase.

## 0.388.0 (2026-06-14) - Tier R6.10: history word designators (clears R6 bug list)
- BUG FIX (bash-verified; reappraisal #6 L10, the final R6 bug). History
  expansion only handled EVENT designators (`!!`, `!n`, `!string`); word
  designators were unimplemented, so `!$` returned event-not-found and `!!:1`
  left a literal `:1` garbage suffix on the command.
- Implemented bash word designators in `history_expansion.py`: `:0`, `:n`,
  `:^`, `:$`, `:*`, `:n-m`, `:n-`, `:n*`; the bare shorthands `!$`/`!^`/`!*`
  (default to the previous command) and `!:n`; attachable to any event
  (`!1:$`, `!echo:^`, `!-2:2`). Quote-aware word splitting; `!*` with no args →
  empty; out-of-range → `bad word specifier` — all matching bash. The
  documented user-guide `!$` example now works; added a "Word Designators"
  doc subsection.
- Deferred (recorded follow-up): the `:s/old/new/`, `:p`/`:h`/`:t`/`:r`/`:e`
  modifiers and `^old^new^` quick-substitution (lower-priority modifier class).
- Tests: +`tests/unit/interactive/test_history_word_designators.py` (39). Full
  gate green: ruff + mypy clean, `run_tests.py --parallel` 7135 passed,
  `--compare-bash` 415 passed.
- This clears the reappraisal #6 bug list: all 4 HIGH, 9 MEDIUM, and 11 LOW are
  fixed except M7 (high `\xHH`/`\NNN` byte-vs-codepoint), which remains deferred
  pending a dedicated output-encoding (surrogateescape) change.

## 0.387.0 (2026-06-14) - Tier R6.9: shopt nocasematch + query exit code
- BUG FIX (bash-verified; reappraisal #6 L6).
- `shopt -s nocasematch` is now supported and fully wired: `[[ ]]` `==`/`!=`/`=~`
  and `case` matching become case-insensitive (`re.IGNORECASE`) when set.
  `[[ ABC == abc ]]` → match; case-sensitive behavior unchanged when unset.
  (`state.py`, `shell_options.py`, `expansion/pattern.py`,
  `enhanced_test_evaluator.py`, `control_flow.py`)
- Also fixed the `shopt OPTION` / `shopt -p OPTION` QUERY exit code (was always
  0; now 1 when a named option is unset, matching bash — affected all options),
  and padded the option-listing name field to bash's width.
- Honesty preserved: genuinely-unimplemented bash options (`failglob`,
  `lastpipe`, `inherit_errexit`, `histappend`, …) still error rather than
  becoming fake no-ops.
- Tests: +`test_nocasematch_conformance.py` (14 `assert_identical_behavior`),
  +3 golden cases; updated one shopt unit test that pinned the old exit-0 query.
  Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7096 passed,
  `--compare-bash` 415 passed.

## 0.386.0 (2026-06-14) - Tier R6.8: metrics pipeline count + version-sync meta-test
- BUG FIX (reappraisal #6 L11). `MetricsVisitor` counted every `Pipeline` AST
  node, but psh wraps every command in a single-element Pipeline — so a script
  with no `|` reported "Pipelines: N". Now only genuine pipelines
  (`len(node.commands) > 1`) are counted (and contribute to max-pipeline-length).
  `metrics_visitor.py`; +regression test.
- TOOLING. Added `tests/unit/tooling/test_version_sync.py`: a meta-test that
  fails if `psh/version.py`'s `__version__` and the `**Current Version**:` lines
  in README.md/ARCHITECTURE.md drift apart, or if CHANGELOG.md lacks a `##
  <version>` entry — closing the one staleness gap the meta-test layer did not
  guard (CLAUDE.md mandates these match but nothing enforced it).
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` (all phases).

## 0.385.0 (2026-06-14) - Tier R6.7: io_redirect bugs (M9/L2/L4)
- BUG FIX (bash-verified; reappraisal #6 M9/L2/L4).
- M9 write-side `>(cmd)` leaked a `$TMPDIR/psh-psub-XXXX/` FIFO dir per run when
  the consumer ran in a pipeline (the pipeline child execs, so the parent's
  `process_sub_scope` cleanup never ran in it). The substitution worker now
  unlinks its own FIFO + temp dir right after opening it for read (an opened
  FIFO survives unlink — robust to the consumer's `os._exit`/exec). No leak in
  pipeline / non-pipeline / multiple-`>()` / nested forms; data delivery intact.
  (`process_sub.py`)
- L2 redirect-open failures leaked Python's `OSError` repr (`psh: error: [Errno
  2] ...: 'path'`); now emit bash's `psh: TARGET: STRERROR` (e.g. `psh:
  /badpath/nope: No such file or directory`) for both the forked-child and
  builtin redirect paths, exit code unchanged. psh's custom noclobber/ambiguous
  messages (errno is None) are preserved. (`manager.py`, `command.py`)
- L4 `exec 1>&-` then writing crashed with exit 120 + an "Exception ignored
  while flushing sys.stdout" finalizer leak. `echo`/`printf` now catch the
  write OSError and report `write error: <strerror>` returning 1 (like bash),
  and an atexit guard rebinds a closed std stream to /dev/null so the shutdown
  flush is a silent no-op. (`io.py`, `__main__.py`)
- Tests: +`TestWriteSideFifoFilesystemLeak` (4),
  +`test_reappraisal6_redirect_errors_conformance.py`. Full gate green: ruff +
  mypy clean, `run_tests.py --parallel` 7075 passed, `--compare-bash` 409.
- Noted out-of-scope (recorded): `echo hi > $v` with `v="a b"` (ambiguous
  redirect) returns 0 in psh vs bash's exit 1.

## 0.384.0 (2026-06-14) - Tier R6.6: lexer/parser bugs (M8/L1/L9; M7 deferred)
- BUG FIX (bash-verified; reappraisal #6 M8/L1/L9).
- M8 ANSI-C `$'\cX'` control-char escape now supported (`$'a\cIb'` → `a<TAB>b`).
  bash's mapping: `0x7f` for `\c?`, else `ord(X) & 0x1f` (so `\cI`→TAB, `\c@`→
  NUL, `\cA`→0x01); bare trailing `\c` stays literal. (`lexer/pure_helpers.py`)
- L1 `${}`/`${ }`/`${1abc}`/`${!.foo}` now correctly raise `bad substitution`
  (exit 1) at runtime, while valid forms (`${12}`, `${a-x}`, `${#}`, `${-}`,
  `${arr[0]}`, `${!ref:-d}`) still work. New `BadSubstitutionError`,
  `validate_parameter_expansion` in `param_parser.py` called at the two runtime
  expansion chokepoints. (`variable.py`, `evaluator.py`, `exceptions.py`)
- L9 parser ErrorContext "Context:" line was built backwards (following tokens
  before `-> HERE <-`, preceding after) and leaked raw `TokenType.EOF`. Now
  before/after are on the correct sides with `<EOF>`/`<newline>` placeholders.
  (`parser/recursive_descent/context.py`, `helpers.py`)
- M7 DEFERRED (documented): high `\xHH`/`\NNN` escapes emit Unicode codepoints
  not raw bytes (`$'\377'` → 2 UTF-8 bytes, bash 1). A correct fix requires
  flipping psh's entire output-encoding contract to `surrogateescape` (11
  encode sites + sys.stdout + file redirects + pytest capture) — deep regression
  risk; left for a dedicated change.
- Tests: +`test_ansi_c_control_escape_conformance.py` (11),
  +`test_bad_substitution_conformance.py`, +`test_error_context_format.py` (4).
  Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7063 passed,
  `--compare-bash` 409 passed.

## 0.383.0 (2026-06-14) - Tier R6.5: four builtin/state small bugs
- BUG FIX (bash-verified; reappraisal #6 M5/M6/L7/L8).
- M5 `unset -f NONEXISTENT` now silently returns 0 (was an error + exit 1),
  matching `unset -v`. (`environment.py`)
- M6 `test`/`[` gained the `<` / `>` string-comparison operators (ASCII order,
  not locale): `[ a \< b ]` → 0 (was "binary operator expected", exit 2).
  (`test_command.py`)
- L7 `trap -p` now prints the canonical signal name: real signals get the `SIG`
  prefix (`TERM`→`SIGTERM`, numeric `15`→`SIGTERM`), pseudo-signals
  (EXIT/ERR/DEBUG/RETURN) stay bare. (`trap_manager.py`)
- L8 `$-` now matches bash: it no longer includes `s` (stdin) in `-c` or
  script-file mode, the flag order is bash's (lowercase-then-uppercase
  alphabetical with invocation flags `c`/`s` appended last), and `H`
  (histexpand) is interactive-only. E.g. `psh -c 'echo $-'` → `hBc` (was
  `chsBH`). (`state.py`, `__main__.py`, `script_executor.py`, `shell.py`)
- Tests: +`test_reappraisal6_builtin_state_conformance.py` (32) +9 golden;
  updated two tests that pinned the old `$-`/histexpand behavior (verified vs
  bash). Full gate green: ruff + mypy clean, `run_tests.py --parallel` 7033
  passed, `--compare-bash` 409 passed.

## 0.382.0 (2026-06-14) - Tier R6.4: array-element-write bugs
- BUG FIX (bash-verified; reappraisal #6 M4 + a related follow-up).
- M4 negative array index was rejected on WRITE (reading already worked):
  `a=(1 2 3); a[-1]=X` now maps `-1` to the last element (was an error that even
  classified as an internal defect under strict-errors). Implemented bash's rule
  `-N → highest_index + 1 - N` (sparse-aware) in `IndexedArray.resolve_write_index`,
  covering all write paths: literal `a[-1]=`, `a[-1]+=`, and arithmetic
  `(( a[-1]=9 ))`. Out-of-range raises a new `ArraySubscriptError(PshError)`
  (`psh: NAME[SUB]: bad array subscript`, exit 1) instead of an internal defect;
  a failed `unset b; b[-1]=x` leaves `b` unset like bash. Negative subscripts on
  ASSOCIATIVE arrays remain literal keys (mapping applies to indexed only).
- Related follow-up: the integer (`-i`) attribute is now applied on subscript
  assignment too — `declare -ia v; v[0]=2+3` → `([0]="5")` (was `2+3`); `+=` does
  a numeric add. (declare-time element eval was fixed in v0.381; this is the
  later-assignment path.)
- Also: a bare `a[i]=v` assignment now propagates its exit status and a failed
  one aborts a non-interactive script (matching bash's assignment fatality).
- Tests: +`TestNegativeIndexWrite` (10) +`TestIntegerArrayElementAssignment` (5)
  conformance, +8 golden cases. Full gate green: ruff + mypy clean, `run_tests.py
  --parallel` 6991 passed, `--compare-bash` 391 passed.

## 0.381.0 (2026-06-14) - Tier R6.3: four declare/attribute bugs
- BUG FIX (bash-verified; reappraisal #6 M1/M2/M3/L5).
- M1 `declare -i` was ignored when combined with `-l`/`-u` (`declare -il v=5+3`
  → was `"5+3"`, now `"8"`). `scope.py:_apply_attributes` now evaluates the
  integer attribute FIRST, then case-folds the result (they were exclusive
  `if/elif`).
- M2 `declare -p` attribute-letter order was wrong. Empirically determined
  bash's order to be `a A i n r t x l u` (case-fold flags last) and fixed
  `declare_format.py:_FLAG_CHARS`: `declare -ix` now prints `-ix` (was `-xi`),
  `-ir`→`-ir`, `-irx`→`-irx`.
- M3 `-a`/`-A` combined with `-i`/`-l`/`-u` didn't actually make the var an array
  (`declare -ia v=1` → was scalar `="1"`, now `([0]="1")`); array elements now
  receive the integer/case attributes (`declare -ia v=(1+1 2+2)` → `([0]="2"
  [1]="4")`, `declare -al v=(ABC)` → `abc`). (`function_support.py`)
- L5 `declare -F name` printed `declare -f name`; now prints the bare function
  name (the no-arg `-F` listing form is unchanged). `-f`/`-F NAME` not-found is
  now silent with exit 1 (was printing an error).
- Known follow-ups (recorded, separate code paths): assoc-array `declare -p`
  trailing-space-before-`)`; element-level integer attr on direct subscript
  assignment (`v[0]=2+3`).
- Tests: +`tests/conformance/bash/test_declare_attributes_conformance.py` (24
  `assert_identical_behavior`). Full gate green: ruff + mypy clean, `run_tests.py
  --parallel` 6969 passed, `--compare-bash` 375 passed.

## 0.380.0 (2026-06-14) - Tier R6.2: read C-escapes + source positionals (HIGH)
- BUG FIX (bash-verified; reappraisal #6 H3/H4).
- H4 `source`/`.` with NO args wiped the caller's positional params:
  `set -- A B C; source f` (f: `echo "$@"`) → was empty, now `A B C`.
  `source_command.py` only overrides `$@` when extra args are actually given
  (`len(args) > 2`); `source f X Y` still sets `X Y` inside and restores `A B C`
  after. `.` (dot) fixed identically.
- H3 `read` (without `-r`) wrongly did C-style escape translation
  (`\t`→TAB, `\n`→newline). bash `read` only strips the backslash (next char
  literal), protects escaped IFS chars from splitting, and treats a trailing
  `\<newline>` as line continuation. Rewrote `read_builtin._process_escapes` to
  return (char, protected) pairs; added line-continuation re-reading
  (`_read_continuations`) and backslash-protected IFS splitting/trimming. `-r`
  stays fully literal. `a\tb`→`atb`, `a\ b`→one field `a b`, `a\`+newline+`b`→
  `ab`. Also fixed a related divergence: a defaulted `REPLY` (no var names) must
  NOT be IFS-whitespace-trimmed, while `read v`/`read REPLY` are.
- Known remaining follow-up (recorded): `read x < file_without_trailing_newline`
  returns rc 0 in psh vs 1 in bash (EOF-without-delimiter) — separate from
  escapes.
- Tests: +`tests/conformance/bash/test_read_escapes_conformance.py` (19
  `assert_identical_behavior`), +3 source conformance cases; rewrote one read
  unit test that pinned the old (wrong) line-continuation behavior. Full gate
  green: ruff + mypy clean, `run_tests.py --parallel` 6945 passed,
  `--compare-bash` 375 passed.

## 0.379.0 (2026-06-14) - Tier R6.1: three expansion bash-divergence bugs
- BUG FIX (bash-verified; reappraisal #6 H1/H2/L3).
- H1 `${var#}` (empty removal pattern) returned the LENGTH: `v=abc; echo
  "${v#}"` → was `3`, now `abc`. The parser already distinguished `${#v}`
  (operand `None` = length) from `${v#}` (operand `''` = empty pattern), but
  `node.word or ''` collapsed `None`→`''` at the call sites and the length
  branches used `not operand`. `None` is now preserved end-to-end and every
  length-vs-removal test uses `operand is None` (`evaluator.py`, `variable.py`,
  `operators.py`, `fields.py`). Also fixed a pre-existing `${*#a}` mis-handling.
- H2 extglob `!(pat)` negation failed when the subject STARTS with the pattern:
  `[[ foobar == !(foo) ]]` → was `N`, now `Y`; `${v##!(foo)}` on `foobar` → was
  `foobar`, now empty. A standalone `!(...)` now compiles to a whole-string
  negative lookahead `(?!(?:alts)$).*` (`extglob.py`), and the removal operators
  match-and-invert against the positive pattern span-by-span
  (`parameter_expansion.py`). Embedded `?()/*()/+()/@()` and `a!(b)c` unchanged.
- L3 zero-width extglob over-substituted in `${v//pat/repl}`: `v=xyz;
  "${v//*(q)/-}"` → was `-x-y-z-`, now `-x-y-z`. The global-substitution path
  now suppresses Python `re.sub`'s extra end-of-string empty match (only when
  the pattern can match empty; ordinary patterns keep the fast path).
- Known remaining follow-up (recorded): embedded `!()` in REMOVAL operators
  (`${v#a!(x)}`) still diverges — needs the span-search generalized to embedded
  position.
- Tests: +`TestStandaloneNegationExtglob`, +3 POSIX parameter-expansion methods,
  +13 golden cases. Full gate green: ruff + mypy clean, `run_tests.py
  --parallel` 6923 passed, `--compare-bash` 375 passed.

## 0.378.0 (2026-06-14) - Docs: ground-up reappraisal #6 (post-campaign scorecard)
- DOCS ONLY. Added `docs/reviews/ground_up_reappraisal_6_2026-06-14.md`: a fresh
  five-cluster scorecard taken after the #5 refactor campaign (v0.355–v0.377).
- Scorecard: Lexer/Parser/AST B+→A−, Executor/io_redirect B+→A−, Expansion A−
  (held), Interactive/Scripting/Visitor/Tooling A− (held), Core/Builtins B+
  (held). Overall **A−** — the campaign moved the grade up from #5's B+/A−;
  mypy scope grew ~21→85 files (~38%).
- The remaining gap to a clean A is now a concrete, bash-verified BUG LIST (not
  architecture): 4 HIGH (`${var#}` returns length; extglob `!(pat)` negation;
  `read` non-raw C-escapes; `source` no-args wipes positionals), 9 MEDIUM, 11
  LOW — plus finishing mypy coverage (lexer/parser, expansion mixins). Defines
  the "Tier R6" worst-first bug-fix phase.

## 0.377.0 (2026-06-14) - Behavior fix: extglob inside [[ ]] pattern operands
- BUG FIX (bash-verified; final recorded follow-up). `[[ abc == a@(b|x)c ]]`
  raised a parse error (`Expected DOUBLE_RBRACKET, got LPAREN`); psh now matches
  bash for extended-glob patterns (`?(...)`, `*(...)`, `+(...)`, `@(...)`,
  `!(...)`) in `[[ ]]` `==`/`!=` operands, including adjacent/nested groups and
  trailing globs.
- KEY INSIGHT: extglob in `[[ ]]` is UNCONDITIONAL in bash — it works whether or
  not `shopt -s extglob` is set (and `shopt` on the same `-c` line is lexed
  before it runs anyway). Fixes:
  - Lexer (`recognizers/literal.py`, `operator.py`): new shared predicate
    `extglob_active(config, context)` = `enable_extglob OR bracket_depth > 0`,
    used at the four extglob gates, so an unquoted extglob group is tokenized
    inside `[[ ]]` instead of leaking a stray `LPAREN`.
  - Evaluator (`enhanced_test_evaluator._pattern_match`): `[[ ]]` `==`/`!=`
    matches with extglob always enabled; quoted parts stay glob-escaped
    (`[[ abc == "a@(b|x)c" ]]` remains a literal non-match).
  - Both parser backends benefit (the lexer is shared).
- Adjacent paren constructs verified UNAFFECTED vs bash: `=~` regex grouping +
  `BASH_REMATCH`, `(( ))` arithmetic, `$(...)`, `( subshell )`, `case` patterns,
  and `[[ ( … ) && ( … ) ]]` test-grouping.
- Documented divergence left unchanged (low value, high regression risk): LHS
  extglob `[[ a@(b)c == abc ]]` — bash syntax-errors, psh parses to a non-match.
- Tests: new `tests/conformance/bash/test_double_bracket_extglob_conformance.py`
  (12 `assert_identical_behavior`) + 6 golden cases.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6901 passed,
  `pytest tests/behavioral --compare-bash` 349 passed.

## 0.376.0 (2026-06-14) - Docs: sync io_redirect/CLAUDE.md with the planner refactor
- DOCS ONLY. Updated `psh/io_redirect/CLAUDE.md` for the v0.375.0 planning
  refactor: added `planner.py` to the Key Files table and the architecture
  diagram, documented `ProcessSubstitutionResource` in `process_sub.py`, added a
  "Shared Planning Phase (`RedirectPlanner`/`RedirectPlan`)" pattern section
  (including the `try/finally: plan.close_procsub(applied=…)` fd-leak-safety
  invariant and `plan.target_fd` as the target-fd source of truth), and updated
  the "Adding a New Redirection Type" steps to go through `planner.plan()`.

## 0.375.0 (2026-06-14) - Redirection: unified RedirectPlan + ProcessSubstitutionResource
- REFACTOR + BUG FIX. Introduced a shared redirection "planning" phase so the
  four dispatch sites (`FileRedirector.apply_redirections`,
  `apply_permanent_redirections`, `IOManager.setup_builtin_redirections`,
  `setup_child_redirections`) stop duplicating resolve→expand→procsub logic:
  - New `psh/io_redirect/planner.py`: `RedirectPlan` (resolved redirect +
    target + optional procsub resource, with a `target_fd` property and
    `close_procsub(applied=)`) and `RedirectPlanner.plan()`.
  - New `ProcessSubstitutionResource` dataclass in `process_sub.py` encapsulates
    `(path, parent_fd, pid, cleanup_path)` with `register_with(handler)` and
    `close_parent_fd_for_redirect(redirect, applied=)`. `resolve_procsub_target`
    (bare tuple) → `resolve_procsub_resource` (object); the static
    `FileRedirector._close_procsub_parent_fd` and `IOManager.
    _builtin_procsub_target` are folded in and removed.
- BUG FIX (fd leak on failure): the old code closed a redirect-target process
  substitution's parent fd UNCONDITIONALLY after the if/elif chain, so if a
  LATER redirect in the same command failed (e.g.
  `cat < <(echo data) > /nonexistent/out`) the close was skipped and the parent
  fd leaked. Each redirect is now applied under `try/finally:
  plan.close_procsub(applied=…)`, guaranteeing cleanup on the failure path for
  both the per-command and permanent (`exec`) paths. +2 regression tests in
  `test_process_sub_cleanup.py`.
- `plan.target_fd` faithfully unifies the per-branch target-fd classification
  (verified identical to the old inline logic and `_heredoc_fd`). No stale
  callers of the removed methods remain; no runtime import cycle.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6883 passed.

## 0.374.0 (2026-06-14) - Lint fix: LinterVisitor now analyzes redirect targets
- BUG FIX (follow-up recorded during T2.7). `LinterVisitor` never traversed
  `node.redirects` in its explicit handlers and had no `visit_Redirect`, so all
  lint checks were blind to expansions inside redirect targets and heredoc
  bodies — `echo hello > $undefined.log` reported "No issues found!".
- Mixed in the shared `RedirectTraversalMixin` (matching security/validator/
  metrics), added `self._visit_redirects(node)` to `visit_SimpleCommand`,
  `visit_FunctionDef`, and `visit_IfConditional` (loops/groups already reach
  redirects via `generic_visit`), and added a `visit_Redirect` that runs
  `_check_variable_usage` on the target (skipping dup-fd synthetic `&1`) and on
  expandable heredoc bodies (skipping quoted heredocs/here-strings).
- Now correctly warns on undefined vars in redirect targets and records used
  vars there (no more spurious "defined but never used" for a var used only in a
  redirect). Verified NO false positives — redirect filenames are treated as
  words/expansions, never as commands; non-redirect output is unchanged.
- Added `TestLinterRedirectTargets` (7 tests). Full gate green: ruff + mypy
  clean, `run_tests.py --parallel` 6881 passed.

## 0.373.0 (2026-06-14) - Behavior fix: two brace-expansion divergences from bash
- BUG FIX (bash-verified; follow-ups recorded during T3.3). Two brace-expansion
  cases now match bash:
  - **Char-range backslash**: `echo {Z..a}` included a literal `\` (ASCII 92);
    bash emits an EMPTY word at the backslash position instead (kept, not
    dropped — unlike an empty list item `{a,,b}` which bash drops). Implemented
    with a private-use sentinel so the single-token path keeps the empty word
    while the empty-list filter still drops list empties, and the composite path
    (`x{Z..a}y`) strips it. `{A..z}`, `{a..Z}` (reverse), `{Z..a..2}` (step) all
    match bash now; pure-letter/pure-digit ranges unaffected.
  - **Stray-brace neighbors**: `echo }{a,b}{` was left literal; bash finds and
    expands the inner valid group → `}a{ }b{` (likewise `a}{b,c}d` → `a}bd
    a}cd`). Removed the all-or-nothing balance bail; the group finder now scans
    each `{` for its matching `}` (tracking nesting, skipping `${...}`) and
    treats truly stray/unmatched braces as literal. Valid groups, genuine
    non-groups (`{a,b` stays literal), `${...}`, and nesting are unchanged.
- Tests: +`TestCharRangeBackslash` (6) +`TestStrayBraceNeighbors` (9); new
  `tests/conformance/bash/test_brace_expansion_conformance.py` (17
  `assert_identical_behavior`); +5 golden cases; updated one relocation test to
  the corrected word count.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6874 passed,
  `pytest tests/behavioral --compare-bash` 337 passed.

## 0.372.0 (2026-06-14) - Tier T3.3: brace_expansion.py clarity refactor
- REFACTOR (zero behavior change). `psh/expansion/brace_expansion.py` was the
  last large file at the old altitude; reorganized into explicitly-named,
  top-to-bottom phases with per-phase docstrings: drive-to-fixed-point
  (`_expand_braces`/`_did_expand`), expand-leftmost-and-recombine
  (`_expand_one_brace` → `_generate_items`/`_split_detachable_suffix`/
  `_combine`), locate-a-group (`_find_brace_group` returning a frozen
  `_BraceGroup` dataclass; `${...}` skip extracted to
  `_skip_parameter_expansion`; validation split), lists (`_expand_list` +
  `_split_top_level_commas`), and sequences (`_try_numeric_sequence`/
  `_try_char_sequence` sharing new `_normalize_step` + `_format_padded` helpers).
  Magic operator strings named as module constants.
- Max body-nesting depth 6 → 4; removed an unreachable `isdigit` branch in the
  char-sequence path (digits always take the numeric path first).
- Two frozen characterization batteries (73-case: lists/sequences/nesting/
  escaping/degenerate/multi-word; 12-case: assignment-zone suppression, pipes,
  loops, background, quoting) are byte-identical before/after.
- Noted (pre-existing, NOT fixed): two brace-vs-bash divergences — `{Z..a}`
  backslash handling in the char range, and `}{a,b}{` (psh leaves literal, bash
  expands the inner group).
- Full gate green: ruff + mypy clean (file in scope), `run_tests.py --parallel`
  6837 passed.

## 0.371.0 (2026-06-14) - Tier T3.1: finish [[ ]] Word adoption (+ quoting fixes)
- REFACTOR + BEHAVIOR FIX (bash-verified). The `[[ ]]` binary-test operands are
  now genuine multi-part `Word`s carrying per-part quote context (like
  `SimpleCommand` words), and the evaluator decides pattern-vs-literal PER PART
  by reading those parts. The `right_quote_type` single-char sentinel (the last
  remnant of the pre-Word model, kept derived since v0.348) is deleted.
- Parser (`recursive_descent/parsers/tests.py` + combinator
  `special_commands.py`): `_parse_test_operand`/`_parse_regex_operand` build a
  `Word` with one `WordPart` per glued token, each carrying its own
  `quoted`/`quote_char`; all expansion kinds (not just `$x`) become real
  `ExpansionPart`s via the shared `WordBuilder.parse_expansion_token`. The
  flatten-to-single-`LiteralPart` helper is gone.
- Evaluator (`enhanced_test_evaluator.py`): new `_rhs_pattern`/`_rhs_regex`
  build the glob/regex from the RHS Word's parts — quoted parts contribute
  literal text (glob-escaped / `re.escape`'d), unquoted parts keep glob/regex
  power; quote-aware subject building replaces the old blanket backslash strip.
- Bash divergences FIXED (this is the behavior-fix item): per-part quoting
  `[[ abc == ab"?" ]]` (was wrongly 0 → now 1) and backslash-escaped regex
  metacharacters `[[ "axc" =~ a\.c ]]` (was wrongly 0 → now 1). Preserved
  out-of-scope: extglob inside `[[ ]]` (lexer doesn't tokenize it there).
- Tests: updated `test_enhanced_test_word_operands.py`; added
  `tests/conformance/bash/test_double_bracket_quoting_conformance.py` (12 tests,
  all `assert_identical_behavior`) and 4 golden cases (`--compare-bash`).
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6837 passed,
  `pytest tests/behavioral --compare-bash` 327 passed.

## 0.370.0 (2026-06-13) - Write-side process substitution via FIFO (macOS fix)
- BUG FIX (platform robustness). Write-side process substitution `>(cmd)` used a
  `/dev/fd/N` pipe path. On macOS, an external consumer (e.g. `tee >(cmd)`)
  reopening that write-only pipe through `/dev/fd` can fail with EPERM — so the
  two known `/dev/fd`-sandbox failures (`test_write_side_substitution_tee`,
  `test_dup_stdout_to_arithmetic_fd`) only passed in some environments.
- `>(cmd)` now uses a named FIFO (`tempfile.mkdtemp` + `os.mkfifo`) so consumers
  open a normal path; the substitution child reads the FIFO on stdin with a
  5-second SIGALRM open-timeout (falls back to `/dev/null` if nothing ever
  opens it, so the child never blocks forever). `create_process_substitution`
  now returns a 4-tuple `(parent_fd, path, pid, cleanup_path)` — `parent_fd` is
  `None` for FIFO-backed write side — and `ProcessSubstitutionHandler` tracks
  `active_paths`, unlinking the FIFO + its temp dir at scope exit. Read-side
  `<(cmd)` is unchanged (still a pipe).
- `file_redirect.py`: extracted `_rebind_input_stream(target_fd)` so the four
  permanent-input-redirect arms (`<`, `<>`, heredoc, here-string) share one
  fd-0-only stdin-rebind rule; `<>` now captures `target_fd` so it rebinds stdin
  only when fd 0 actually changed (matching `<`).
- Tests: `test_dup_stdout_to_arithmetic_fd` rewritten to write a `tmp_path` file
  instead of `/dev/stdout` (portable); added `TestExecStdinRedirect`
  (`exec <file` + `read`; `exec 5<file` must not replace stdin).
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6810 passed,
  `pytest tests/behavioral --compare-bash` 319 passed.

## 0.369.0 (2026-06-13) - Tier T3.2: separate-bracket array syntax matches bash
- BEHAVIOR FIX (bash-verified) + REFACTOR (−185 lines). `a [ 0 ] = v` (with
  spaces around the brackets) is NOT array-assignment syntax — bash parses it as
  the simple command `a` with args `[ 0 ] = v`. psh instead raised a parse error
  via ~185 lines of bespoke "separate-bracket" detection machinery in
  `psh/parser/recursive_descent/parsers/arrays.py`.
- The machinery was also OVER-EAGER: it fired on ANY identifier-named command
  word followed by `[`, so it broke real commands too — `echo [ 0 ] = v` and
  `a() { echo hi "$@"; }; a [ 0 ] = v` both raised parse errors in psh while bash
  runs them. Deleting the machinery makes all of these fall through to normal
  simple-command execution, matching bash (command-not-found 127 for `a`,
  correct output for real commands/functions).
- Valid array assignment is untouched: `a[0]=v`, `a[0]+=v`, `a[ 0 ]=v` (spaces
  only INSIDE the brackets), `declare -a`/`-A`, associative `m[k]=v` all behave
  exactly as before. (The combinator parser never had this bug.)
- Removed `_candidate_separate_bracket`, `_scan_bracket_assignment`,
  `_is_valid_variable_name`, `_parse_array_key_tokens`,
  `_parse_separate_bracket_element`, the `separate_bracket` field, and the two
  routing branches.
- Tests: flipped the 4 separate-bracket entries in the array-assignment
  characterization corpus from frozen-ERR to OK (verified vs bash); added 6
  `tests/behavioral/golden_cases.yaml` cases (pass under `--compare-bash`) and a
  `TestSeparateBracketIsNotAssignment` conformance class (7 tests).
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6808 passed,
  `pytest tests/behavioral --compare-bash` 319 passed.

## 0.368.0 (2026-06-13) - Tier T2.7: shared redirect-traversal mixin for visitors
- REFACTOR (zero behavior change). The analysis visitors each duplicated the
  skeleton that walks a command's `redirects` to dispatch into them. Extracted a
  `RedirectTraversalMixin._visit_redirects(node)` in
  `psh/visitor/analysis_helpers.py`; routed `SecurityVisitor`, `MetricsVisitor`,
  and `ValidatorVisitor` (and `EnhancedValidatorVisitor` transitively) through
  it, each keeping its own `visit_Redirect` action. Also collapsed an inline
  duplicate redirect loop in `ValidatorVisitor.visit_SimpleCommand`.
- `FormatterVisitor`/`DebugASTVisitor` were left alone (they render redirects,
  not recurse for analysis). Per the zero-behavior mandate, visitors that did
  not traverse redirects still don't — the hazard is closed for FUTURE code by
  giving everyone the shared correct helper, not by altering current output.
- LATENT BUG REPORTED (not fixed here, candidate for a separate behavior fix):
  `LinterVisitor` never analyzes redirect targets in the nodes it explicitly
  handles, so e.g. `$undefined` inside `cmd > $undefined.log` is invisible to
  the linter's variable checks.
- A 24-script redirect battery (`$(...)`, `${...}`, `2>&1`, glob targets,
  heredocs with `$var`, process-subs, fd dups, compound-command redirects)
  produced byte-identical output for every visitor.
- Full gate green: ruff + mypy clean (visitor package in scope), `run_tests.py
  --parallel` 6795 passed.

## 0.367.0 (2026-06-13) - Tier T2.6: formalize the pending-array-inits handoff
- REFACTOR (zero behavior change). Declaration builtins (`declare`/`typeset`/
  `local`/`export`/`readonly`) received array-initializer data from the executor
  via an ad-hoc shared-mutable attribute set with `getattr(shell,
  '_pending_array_inits', None)`. Replaced with a typed, single-owner API on
  `Shell`: `set_pending_array_inits()`, `pending_array_init(arg)` (non-consuming
  peek), `clear_pending_array_inits()`; the backing field is now declared and
  typed in `__init__` (`Optional[Dict[str, ArrayInitialization]]`).
- Lifetime invariant (documented + enforced at the one owner): the executor's
  `_run_command` installs the map immediately before the builtin and clears it
  in a `finally`; outside that window it is `None`. The peek is deliberately
  non-consuming to preserve the one nested re-read (`export NAME=(...)` delegates
  to `declare`, which reads the still-installed map). The set-if-non-None /
  clear-if-set guard is preserved, so an initializer-free command never picks up
  a stale map.
- A 14-case characterization (declare/typeset -a/-A, local-in-function, export,
  readonly, the B3 fidelity case `declare -a a=(${x}b "p""q")`, indexed/assoc
  `+=`, nested-function declarations, a partway-erroring declare, **no-stale-
  pickup** `declare -a noinit`) was byte-identical before/after.
- Full gate green: ruff + mypy clean (shell.py in scope), `run_tests.py
  --parallel` 6795 passed.

## 0.366.0 (2026-06-13) - Tier T2.5: unify glob-metacharacter detection
- REFACTOR (zero behavior change). The "does this string contain glob
  metacharacters" predicate was written inline `any(c in s for c in '*?[')` at
  7 sites (plus 2 per-char checks) across `glob.py` and `word_expander.py`.
  Collapsed to one source of truth in `psh/expansion/glob.py`:
  `GLOB_METACHARS = frozenset('*?[')` and `has_glob_metacharacters(s)`.
- No divergence: every site already used exactly `*?[` — the duplication was
  textual, not behavioral. The separate, already-centralized extglob predicate
  (`extglob.contains_extglob`) is untouched. Two visitor-layer sites are left
  as-is on purpose (a static-analysis visitor that shouldn't couple to the
  runtime expander, and a formatter that uses a different `*?[]` set for a
  quoting decision).
- A 24-word characterization harness (globs, bracket exprs, escaped/quoted,
  extglob `@()/?()/*()/+()/!()`, char classes, `**`, dotfiles) run through real
  globbing with extglob both off and on produced identical results before/after.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6795 passed.

## 0.365.0 (2026-06-13) - Tier T2.4: split environment.py (extract env builtin)
- REFACTOR (zero behavior change, registry-identical). The 671-line
  `psh/builtins/environment.py` held `export`, `set`, `unset`, and `env`. The
  `env` builtin — which carries its own fd-binding helpers (really an I/O
  concern) — moved to a new `psh/builtins/env_command.py` (208 lines) with
  `EnvBuiltin` + `_parse_invocation`, `_configure_child_export_attributes`,
  `_is_env_assignment`, `_print_environment`, `_bind_process_fds_to_streams`,
  `_restore_process_fds`. `environment.py` shrank to 483 lines (export/set/
  unset) with its now-unused imports trimmed.
- Wired `env_command` into `psh/builtins/__init__.py`'s import list so it
  self-registers. The registered-builtin name-set is byte-identical before and
  after (verified by registry dump diff), and a 7-case `env` characterization
  (`env`, `env FOO=bar`, `env FOO=bar cmd`, `env -i`, `env -u`, redirection to
  grandchild, no-leak) is identical.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6795 passed.

## 0.364.0 (2026-06-13) - Test isolation: per-test cwd for file `test`/`[` tests
- TEST FIX (no production change). `tests/unit/builtins/test_test_builtin.py`'s
  `TestFileTests` created fixed-name files/dirs (`testdir`, `regular.txt`, …) in
  the shared cwd and removed them by relative path. Under pytest-xdist these
  collided across workers (a `testdir` made by one test removed by another →
  intermittent `FileNotFoundError` on `os.rmdir`). Added an autouse
  `monkeypatch.chdir(tmp_path)` fixture giving each test its own working
  directory (CLAUDE.md parallel-safety rule 2). Verified stable under `-n 4`.

## 0.363.0 (2026-06-13) - Tier T2.3: split ast_nodes.py into a package
- REFACTOR (zero behavior change, zero import churn). The 766-line
  `psh/ast_nodes.py` became a package `psh/ast_nodes/` with cohesive
  submodules: `base.py` (ASTNode/Statement/Command bases), `redirects.py`,
  `words.py` (Word + expansion nodes), `arrays.py`, `commands.py`
  (SimpleCommand/Pipeline/AndOrList/StatementList/TopLevel), `tests.py`
  (`[[ ]]` nodes), `control.py` (loops/if/case/select/function def).
- `psh/ast_nodes/__init__.py` flat-re-exports every previously-public name
  (`__all__` parity verified by set-diff against the pre-split surface: 0 names
  lost), so every `from psh.ast_nodes import ...` / `from ..ast_nodes import`
  across the codebase is unchanged — NO other file touched its imports.
- Key subtlety: the coverage-matrix meta-test filters on
  `cls.__module__ == 'psh.ast_nodes'`. `__init__` runs `_reparent_to_package()`
  to rewrite `__module__` back to the package on every `ASTNode` subclass, so
  introspection (and `test_ast_coverage_matrix.py`) behaves identically.
- Updated the mypy scope entry `psh/ast_nodes.py` → `psh/ast_nodes` (mypy clean,
  85 files) and fixed stale `psh/ast_nodes.py` path references in 6 docs (forced
  by the `test_doc_pointers` meta-test).
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6794 passed.

## 0.362.0 (2026-06-13) - Tier T2.2: extract dense expansion helpers
- REFACTOR (zero behavior change, expansion hot path). Two dense regions in
  `psh/expansion/variable.py` lifted into named helpers:
  - `expand_parameter_direct`'s array branch → `_expand_array_parameter`
    returning `(handled, value)` (handled = whole-array `[@]`/`[*]` forms:
    count, slice, `@A`/`@Q`, conditional ops, per-element transforms; not
    handled = scalar element access that falls through to the shared
    `_apply_operator`). Parent body ~170 → ~90 lines; the array arm is now a
    6-line dispatch.
  - `expand_string_variables`'s escape loop → `_process_double_quote_escape`
    applying the `\\`, `\"`, `\$`, `` \` `` rules (incl. the unrecognized-escape
    fall-through) and returning `(piece, new_index)`. Parent body ~55 → ~25
    lines; the loop now reads as a clean three-way dispatch.
  - Special-char sets, the `\$`-shields-expansion check, IFS join behavior, and
    all early-return semantics are byte-identical.
- A 60-case characterization battery (array `[@]`/`[*]` quoted/unquoted,
  arith-index, `${#a[@]}`, `${!a[@]}` keys, sparse, associative, slices,
  per-element transforms, custom-IFS; plus the full escape set) matched the
  pre-refactor golden baseline AND real bash exactly.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6794 passed.

## 0.361.0 (2026-06-13) - Tier T2.1: decompose _execute_command
- REFACTOR (zero behavior change). `CommandExecutor._execute_command`
  (`psh/executor/command.py`) was a ~140-line method conflating two
  responsibilities. Split into a thin coordinator plus two focused methods:
  - `_execute_command` (~45 lines) — per-command preamble (DEBUG trap, array
    assignments, `assignments.extract`, the `last_cmdsub_status = None` reset
    that must precede expansion), pure-vs-command decision, and the single
    shared `try/except → _handle_execution_error`.
  - `_run_pure_assignment` (~12 lines) — the no-command-word path
    (`assignments.apply_pure`).
  - `_run_command` (~110 lines) — the command-word path: word expansion,
    redirect-only/words-vanish edges, prefix apply + `set -e` abort, xtrace,
    `exec` special case, array-init delivery, strategy dispatch, restore.
  - `last_cmdsub_status` reset, `_pending_array_inits` lifetime, `is_special`/
    `saved_vars` restore, and deferred-pure-on-words-vanish are all preserved
    exactly.
- A 36-case characterization harness (pure scalar/multi/chain/array/assoc/
  cmdsub-status/readonly/append; prefix external/builtin/function/special-
  persist/temp/chain; normal builtin/external/function/127/alias; empty/
  redirect-only/words-vanish; exec-assign; xtrace; set-e) matched the
  pre-refactor golden baseline byte-for-byte.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6794 passed.

## 0.360.0 (2026-06-13) - Tier T1.6: builtin output via base-class helpers + guard
- CONSISTENCY/HARDENING (zero behavior change, verified). Builtins that wrote
  output with raw `print(..., file=shell.stdout/stderr)` now use the base-class
  helpers (`self.write_line` for stdout, `self.write_error_line`/`self.error`
  for stderr), which are forked-child-aware (`os.write` in a child) and honor
  the flush discipline. Migrated `navigation.py` (cd CDPATH + `cd -` echo),
  `positional.py` (getopts errors), `shell_options.py` (shopt), `parse_tree.py`,
  `parser_control.py`, and `io.py` (echo debug-exec diagnostics).
- A bash-differential harness (`cd -`, CDPATH `cd`, `pwd`, getopts errors —
  standalone and in pipelines/redirects) confirmed byte-identical output before
  and after: `shell.stdout/stderr` were already redirect-aware, so this is a
  pure readability/consistency migration to the v0.284 error-channel convention.
- Added `tests/unit/builtins/test_no_raw_print.py`: a source-grep guard
  (parametrized over every `psh/builtins/*.py` except the sanctioned `base.py`)
  that fails on any new raw `print(..., file=...std...)` — so future builtins
  can't reintroduce output that may not honor fd-level redirection.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6794 passed.

## 0.359.0 (2026-06-13) - Tier T1.5: tooling honesty for the disabled CI workflow
- TOOLING (no code change). `.github/workflows/tests.yml` still declared
  `on: push/pull_request: [main]` while the workflow has been disabled
  (`disabled_manually`) in favor of the local gate — so the in-tree file
  misrepresented how the project is tested. Changed the triggers to
  `workflow_dispatch` only (the push/PR block is commented out, not active)
  and added a header comment explaining the local-gate policy and exactly how
  to restore per-PR CI (uncomment + `gh workflow enable tests.yml`). The
  nightly safety net and the auto-tagger are unaffected.

## 0.358.0 (2026-06-13) - Tier T1.4: unify expansion-delimiter stripping
- REFACTOR (zero behavior change, both parser backends). Three sites peeled
  the delimiters off an expansion's source text with their own inline
  strip-and-fallback blocks: `WordBuilder.parse_expansion_token`,
  `WordBuilder._parse_token_part_expansion`, and the combinator's
  `ExpansionParsers.build_word_from_token`. They now share four pure helpers
  in `word_builder.py`: `strip_command_sub` (`$(`…`)`), `strip_backtick`,
  `strip_arithmetic` (`$((`…`))`), `strip_process_sub` (`<(`/`>(`…`)`).
- Real divergences were found and PRESERVED, not silently unified: the
  combinator keeps its post-strip `_validate_command_substitution` check
  (recursive-descent has none); only the delimiter strip itself is shared.
  `$[...]` arithmetic and the combinator's standalone process-sub parser were
  confirmed out of scope and left untouched.
- A 29-input dual-backend characterization harness (nested cmd subs, backticks,
  `${...}` with `:-`/`[@]`/`##`/nesting, arithmetic, simple/special vars, mixed
  adjacency, quoted composites, process subs) dumped byte-identical ASTs under
  both `--parser rd` and `--parser combinator` before and after.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6760 passed.

## 0.357.0 (2026-06-13) - Tier T1.2: extract the redirection-mode policy
- REFACTOR (zero behavior change). `CommandExecutor._execute_with_strategy`
  (`psh/executor/command.py`) chose how to apply a matched command's
  redirections via inline nested `if/elif/else`. That decision is now a named
  `RedirectionMode` enum decided in one place (`_decide_redirection_mode`) and
  dispatched in one place, with each mode documented:
  - `BUILTIN_INPROCESS` — builtin not in a pipeline/forked child: Python-stream
    save/restore around the one command (does not persist).
  - `EXTERNAL_DEFERRED` — external command: redirections applied in the forked
    child only (applying them in the parent too would resolve `2>&1` against
    already-redirected fds and run heredoc/cmdsub twice).
  - `FD_LEVEL_WINDOW` — functions, aliases, and builtins in a pipeline/forked
    child: fd-level `os.dup2` save/restore window.
- The conditions are byte-for-byte the same booleans that were inline. A
  34-case characterization harness (builtin/special/external/function/alias
  redirects, pipeline members, background, heredocs/here-strings, persist-vs-
  restore, bad-fd/unwritable/missing-file errors) matched the pre-refactor
  golden baseline exactly.
- Full gate green: ruff + mypy clean, `run_tests.py --parallel` 6760 passed.

## 0.356.0 (2026-06-13) - Tier T1.1: grow mypy checked scope (21 → 78 files)
- TYPE-CHECKING SCOPE (textbook lever, zero behavior change). Expanded the
  mypy `files` list in `pyproject.toml` from ~21 to **78 source files**, all
  100% clean under the existing non-strict config. Added whole packages
  `psh/scripting` and `psh/visitor`, most of `psh/expansion` (15 modules),
  `psh/utils` (8 modules), and 14 more `psh/interactive` modules.
- Real type-bug fixes surfaced by the wider scope (all behavior-preserving):
  - `keybindings.py`: base `KeyBindings.bindings`/`get_action` were typed
    `Callable` but actually hold action-name **strings** (the subclass was
    already correct) — base annotation was simply wrong.
  - `security_visitor.py`: `Dict[str, any]` used the builtin `any` as a type →
    `typing.Any`.
  - `debug_ast_visitor.py`: `_visit_children(List[ASTNode])` rejected
    `list[Statement]` (List invariance) → `Sequence[ASTNode]`.
  - `shebang_handler.py`, `command_accumulator.py`: corrected `Optional`
    interpreter/AST types that allowed `None` to flow into `str`/`ASTNode` uses.
- Remaining annotation additions are container/`Optional` narrowing only.
  Deferred as too-noisy-for-a-minimal-pass: `expansion/{arrays,fields,operands,
  operators}.py` (mixin self-type plumbing), `interactive/line_editor.py`,
  `utils/signal_utils.py` — recorded for a future increment.
- Full gate green: `mypy` clean (78 files), `ruff check psh tests` clean,
  `run_tests.py --parallel` 6760 passed / 228 skipped / 19 xfailed.

## 0.355.0 (2026-06-13) - Docs: ground-up reappraisal #5 (textbook-grade scorecard)
- DOCS ONLY (no code change). Added
  `docs/reviews/ground_up_reappraisal_5_2026-06-13.md`: a fresh five-cluster
  scorecard graded against a strict textbook rubric (small/readable, single
  source of truth, narrow interfaces, invariants enforced, behavior proven).
- Scorecard: Expansion A−; Interactive/Scripting/Visitor/Tooling A−;
  Lexer/Parser/AST B+; Executor/io_redirect B+; Core/Builtins B+. Overall
  "B+/A− — production-minded, approaching textbook" (7,007 tests green).
- Defines the prioritized path to the textbook grade: Tier T1 (grow mypy
  scope, extract inline policies into tables/objects, unify small duplication
  clusters), Tier T2 (decompose the dense hubs), Tier T3 (finish the model).

## 0.354.0 (2026-06-13) - Behavior fix: explicit input fd for external commands
- BUG FIX (bash-verified; redirection/IO architecture review, Ugly 2): an
  explicit input-fd redirect (`cmd 5<file`) did not reach the named fd for
  external commands. `python3 -c 'os.read(5,...)' 5<file` raised
  `OSError: [Errno 9] Bad file descriptor` in psh; bash delivers fd 5.
- ROOT CAUSE: `_redirect_input_from_file(target, redirect=None)` already
  honored an explicit fd, and the parent (`exec`) path passed the redirect —
  but the forked-child path (`setup_child_redirections`) and the builtin
  stdin path called it with only `target`, defaulting to fd 0. The child
  `<` branch and the builtin `<` branch now pass `redirect` through, so
  `N<file` opens on fd N across all paths (output `N>file` already worked).
- 5 bash differential probes match (external read of fd 5/6, plain `<`,
  `0<` == `<`, `exec 6<`); +4 conformance tests
  (`tests/conformance/bash/test_explicit_input_fd_conformance.py`). Full
  suite green (6,760). ruff + mypy clean. Updated the `io_redirect/CLAUDE.md`
  helper-table signature.

## 0.353.0 (2026-06-13) - Behavior fix: fd-prefixed heredocs and here-strings
- BUG FIX (bash-verified; from the redirection/IO architecture review): an
  explicit file-descriptor prefix on a heredoc or here-string failed to PARSE.
  `cat 0<<EOF`, `cat 1<<EOF`, `cat 5<<EOF`, `cat 0<<-EOF`, `cat 0<<<word`,
  `cat 5<<<word` all raised `Parse error ... Expected file name`; bash accepts
  them. Now they parse and the body is materialized on the named fd.
- ROOT CAUSE: the lexer's operator recognizer attached numeric fd prefixes to
  `N>`/`N>>`/`N<`/`N<>` etc. but not to the heredoc/here-string operators
  `<<`/`<<-`/`<<<`, so `0<<` never formed a heredoc token and the parser fell
  through to the generic file-redirect branch. Fixed in
  `psh/lexer/recognizers/operator.py` (the fd-prefix matcher now includes
  `<<<`/`<<-`/`<<`, ordered longest-first so `5<<<` isn't split into `5<` `<<`);
  the parser already carried `token.fd`.
- Also fixes the heredoc/here-string MATERIALIZATION hardcoding fd 0
  (redirection review Ugly 2): `psh/io_redirect/file_redirect.py` /
  `manager.py` now honor `redirect.fd` (default 0) across the parent-fd,
  builtin-stream, and forked-child paths, so `5<<EOF` puts the body on fd 5.
- 19/19 bash differential probes match (fd0 == no-prefix, tab-strip `0<<-`,
  quoted delimiters, expansion, pipelines, multi-digit fd, `read` on fd5,
  `exec 5<<<word`). +21 tests (a `tests/conformance/bash/` suite + lexer unit
  tests). Full suite green (6,756). ruff + mypy clean. Zero change to plain
  (non-fd-prefixed) heredocs/here-strings.

## 0.352.0 (2026-06-13) - Test hygiene: arithmetic characterization fixtures
- TEST ONLY (no production change): the arithmetic characterization fixtures
  (`sh`, `assoc_sh` in `tests/unit/expansion/test_arithmetic_characterization.py`)
  constructed a bare `Shell()` and returned it with no teardown, leaking the
  shell's signal-notifier pipe FDs across the suite (flagged by the
  2026-06-13 expansion architecture review). They now build on the shared
  conftest `shell` fixture, whose `_cleanup_shell` teardown reaps jobs and
  closes those FDs. Dropped the now-unused `Shell` import. Full suite green
  (6,735); ruff + mypy clean.

## 0.351.0 (2026-06-13) - Prune docs/archive
- DOCS ONLY (no code change): removed 298 stale development-history files from
  `docs/archive/` — completed implementation plans, phase summaries, and
  point-in-time analyses accumulated through the project's development, with no
  live references from code, tests, or current docs. All are recoverable from
  git history.
- KEPT `docs/archive/CHANGELOG_history.md` (the pre-v0.200.0 version history),
  which `CHANGELOG.md` references live; the `pyproject.toml` ruff
  `extend-exclude = ["docs/archive"]` remains valid (still covers it).
- Verified: `ruff check .` passes, the doc-pointer and README-statistics
  meta-tests pass, the full suite is green (6,735), and the CHANGELOG pointer
  still resolves.

## 0.350.0 (2026-06-13) - Docs sync after reappraisal #4
- DOCS ONLY (no code change): brought the architecture/CLAUDE docs current
  after the reappraisal #4 program.
  - Root `CLAUDE.md` release workflow: GitHub's per-PR `tests.yml` is disabled;
    the **local** `run_tests.py --parallel` (+ ruff + mypy) is THE gate; merge
    immediately (no CI wait); `release-tag.yml` auto-creates the `vX.Y.Z` tag
    on a `psh/version.py` bump (no manual `git tag`).
  - Root `CLAUDE.md` Known Test Issues: documented that `strict-errors` is
    enabled suite-wide via `conftest.py` (`PSH_STRICT_ERRORS=1`) — a test
    hitting a genuine internal defect now fails loudly; a deliberate-defect
    test must disable it locally.
  - `psh/core/CLAUDE.md`: added `FunctionDefinitionError` to the `PshError`
    member list and documented the expected-error taxonomy
    (`report_internal_defect`: `PshError ∪ OSError ∪ SyntaxError` = expected;
    everything else = internal defect) and the `strict-errors` mechanism.
  - `README.md`: corrected the registered-builtin count (60 → 61; the
    enumerated list was already complete).
- Verified: the doc-pointer and README-statistics meta-tests pass; every
  symbol referenced in the new docs exists.

## 0.349.0 (2026-06-13) - Reappraisal #4 Tier C-B3: unified array-init path (+behavior fixes)
- REFACTOR + BEHAVIOR FIX (review Ugly 6): psh had TWO array-initialization
  implementations — the structured `ArrayInitialization`/`ARRAY_INIT_ELEMENT`
  path for bare `a=(...)`, and a separate serialize-then-`shlex`-reparse for
  declaration builtins (`declare`/`typeset`/`local`/`export`/`readonly`). They
  are now UNIFIED: declaration array-init flows through the same structured
  expansion via shared `ArrayOperationExecutor.build_indexed_array` /
  `build_associative_array` helpers (one implementation, used by both paths).
  The parser attaches the structured `ArrayInitialization` to the argument
  (`Word.array_init`); the executor hands it to the declaration builtin through
  a scoped `shell._pending_array_inits` (set/cleared around the single call,
  mirroring the `exec` node-passing precedent). The string-reparse module
  `psh/builtins/array_init.py` (132 lines) is DELETED — no real entry point
  needs it (`eval` re-parses to a structured init; dynamic `declare $x`
  word-splits and never array-ifies, like bash).
- This FIXES 9 bash divergences the old reparse got wrong (each bash-verified):
  adjacent-quote `declare -a a=("x""y")` → `xy` (was split); indexed `+=`
  append; associative `+=` append; bare assoc key/value pairs
  `declare -A m=(k1 v1 …)`; explicit indices `declare -a a=([2]=x [0]=y)`;
  tilde and command-substitution elements; `export e=(a b)` (now an indexed
  array with the export attribute, not a scalar string; arrays aren't exported
  to the env); and the WRONG array-ification of dynamic scalars (`declare
  a=$x` with `x='(1 2)'` is now a scalar, like bash). Also fixed `declare -a
  a+=(…)` parsing (the lexer splits `a+=` → `a` `+=`, previously misparsed).
- Also fixes the `+=` arg detection in `_check_array_initialization`.
- SAFETY NET: a value-based declaration-array conformance suite (17 cases via
  `declare -p`) + reworked legacy tests, all bash-verified; the bare-array
  path characterization is unchanged. Full suite green (6,735 passed). ruff +
  mypy clean. Docs updated (`ast_data_flow.md`, `builtins/CLAUDE.md`).
- PRE-EXISTING divergences confirmed UNCHANGED (present on main too, not
  regressions): unquoted assoc key containing a space (`[a b]=v`) reads empty
  (quoted `["a b"]=v` works); `declare -p` assoc display ordering; `declare -i`
  not applied to array elements.
- The token-payload rewrite (review Ugly 2/10, "E1") proved UNNECESSARY: the
  element Words already carry sufficient fidelity for the structured path, so
  B3 needed none of it. E1 remains unscheduled.

## 0.348.0 (2026-06-13) - Reappraisal #4 Tier C-D2: test operands in the Word model
- REFACTOR (zero behavior change, review Ugly 11): `[[ ]]`
  `BinaryTestExpression` stored operands as plain strings plus
  `left_quote_type`/`right_quote_type` side-channels — the last parser
  expression not using the `Word` model. Operands are now `left_word: Word` /
  `right_word: Word`:
  - `left_quote_type` DELETED (was dead — set by the parser, read nowhere).
  - `right_quote_type` is now a derived `@property` from `right_word.is_quoted`
    (it drives literal-vs-glob for `==`/`!=` and literal-vs-regex for `=~`);
    `is_quoted` reproduces the old stored boolean for every operand shape.
  - `.left`/`.right` retained as derived `display_text()` properties so
    formatter/debug consumers are unchanged.
  Both parser backends build operand Words; the evaluator expands the Words and
  reads `right_word.is_quoted`. `UnaryTestExpression` deliberately left as-is
  (no quote side-channel to remove; migrating it adds risk with no cleanup).
- SAFETY NET: a 37-case characterization
  (`tests/integration/test_enhanced_test_word_operands.py`) over every operator
  and quoting shape (glob/literal `==`, literal/regex `=~`, BASH_REMATCH
  capture, numeric, `-z`/`-f`, tilde, empty) plus the `is_quoted == old
  right_quote_type` equivalence — green before/after. 17 bash differential
  probes match. Full suite green (6,718 passed). ruff + mypy clean.
- PINNED (pre-existing, not fixed): a mixed-quote LHS pattern like `a"b"*`
  collapses to literal text with no per-part quote context (the old
  single-quote-type model was already lossy here); preserved exactly.

## 0.347.0 (2026-06-13) - Reappraisal #4 Tier C-D1: quote context in parts only
- REFACTOR (zero behavior change, review Ugly 3): `Word` stored a whole-word
  `quote_type` field that duplicated the per-part `quoted`/`quote_char` state.
  `Word.quote_type` is now a derived `@property` — a word is wholly quoted iff
  all its parts are quoted with the same quote char, which then is the type.
  `is_quoted`, `is_unquoted_literal`, and `effective_quote_char` now derive
  purely from parts. The Word construction sites (`from_string`, `word_builder`,
  the control-structure/loop parsers in both parser backends, `command.py`)
  drop the now-redundant `quote_type=` argument since the parts already carry
  the quote.
- SAFETY NET: a 128-case quote-derivation characterization
  (`tests/unit/parser/test_word_quote_derivation.py`, both parser backends)
  asserting the derived quote properties — green before/after. Characterization
  surfaced THREE shapes where the OLD stored `quote_type` disagreed with the
  parts (adjacent same-quote composites `"a""b"`, quoted case patterns, and a
  combinator `'mixed'` sentinel); all are verified behavior-neutral against
  bash AND pristine main (uniformly-quoted words expand identically through the
  whole-word vs composite dispatch branches; case patterns match via per-part
  quote context, never `quote_type`). Full suite green (6,681 passed); 12 bash
  quoting probes match. ruff + mypy clean.

## 0.346.0 (2026-06-13) - Reappraisal #4 Tier C-C3: operator-debris recognizer
- REFACTOR (zero behavior change, review Ugly 9): the lexer's step-4
  `_handle_fallback_word` — which collected operator-debris words (those
  starting with `]`, `+`, `=`, `[`, the only four classes a census found
  reach it) using a looser terminator set than the literal recognizer — is now
  a registered `OperatorDebrisWordRecognizer` (`recognizers/operator_debris.py`)
  at lowest priority (10), tried strictly last. The `tokenize()` loop no longer
  has a special fallback step: it is whitespace → quotes/expansions →
  recognizers (debris last) → fail-loud RuntimeError. These word forms are now
  honestly modeled as a grammar recognizer with an explicit `can_recognize`
  domain, not a fallback accident.
- SAFETY NET: a frozen token-stream characterization
  (`tests/unit/lexer/test_operator_debris_recognizer.py`, 20 tests) over every
  census case (`[ x = y ]`, `a=([1]=x z)`, `a]b`, `vars+=(x)`, `set +x`,
  `([a-z]+)`, `a=b=c`, `[0-9]*)`, …) plus "not stolen from operator/literal"
  pins (`[[ -f x ]]`) — byte-identical before/after (types, offsets,
  adjacency). 5 bash probes match. Full suite green (6,553 passed). ruff +
  mypy clean. CLAUDE.md flow/priority docs updated.

## 0.345.0 (2026-06-13) - Reappraisal #4 Tier C-C2: command-position drift-lock
- ASSESSMENT (review Ugly 8): the review recommended extracting one shared
  `CommandPositionMachine` for the three machines that track command position
  (lexer pass, keyword normalizer, cmdsub scanner). On inspection the codebase
  ALREADY realizes that intent better: `psh/lexer/command_position.py` is the
  single shared vocabulary all three consult, with a docstring explaining why
  their alphabets MUST differ (they run at different pipeline stages — raw
  text vs token types vs token stream). Forcing a unified state machine would
  add risk and contradict that design, so it is intentionally NOT extracted.
- TEST + DOC ONLY (no production logic change): added
  `tests/unit/lexer/test_command_position_consistency.py` (11 tests) locking
  the documented relationships so the vocabulary can't silently drift —
  keyword-valued set entries are real `KEYWORDS`; the documented asymmetries
  hold (openers set lexer command-position but closers are omitted;
  `RESET_TO_COMMAND_POSITION` types map to the intermediate+closer keywords);
  plus end-to-end keyword-recognition coverage (`then case …` recognizes
  `case`; `echo case` keeps it a WORD). Updated the `command_position.py`
  docstring to point at this guard. Full suite green (6,530 passed).

## 0.344.0 (2026-06-13) - Reappraisal #4 Tier C-C1: typed cmdsub scanner state
- REFACTOR (zero behavior change, review Ugly 7): `psh/lexer/cmdsub_scanner.py`
  tracked its `case`-statement scanning with 6 string phase constants and
  `[state, pattern_paren_depth]` lists. These are now a `CasePhase` enum and a
  `CaseScanState` dataclass (`case_stack: List[CaseScanState]`); all 24
  `top[0]`/`top[1]` access sites updated, transition logic byte-for-byte
  identical.
- NEW TEST (`tests/unit/lexer/test_cmdsub_scanner_vs_parser.py`, 61-body
  corpus + per-body double assertion): the scanner's chosen `$()` extent
  agrees with what the real parser accepts, and the lexer's COMMAND_SUB token
  spans exactly that extent. Covers nested subs, all quote forms, comments,
  heredocs, arithmetic, `case` in every form, `;;`/`;&`/`;;&`, compositions.
- The 103-case frozen scanner characterization harness stays byte-identical;
  6 bash probes match. Full suite green (6,519 passed). ruff + mypy clean.

## 0.343.0 (2026-06-13) - Reappraisal #4 Tier C-B2: array-assignment normalization
- REFACTOR (zero behavior change, review Ugly 5): `ArrayParser`
  (`psh/parser/recursive_descent/parsers/arrays.py`) detected/parsed array
  assignments by branching inline on ~6 raw tokenisation shapes. A 3,000+
  input fuzz census against the real `ModularLexer` established which shapes
  are actually reachable:
  - DELETED the dead "old-lexer" pattern (a bare name immediately followed by
    an `LBRACKET` token) — 0 of 3,240 inputs reach it; the current lexer never
    produces it.
  - NORMALIZED the live shapes behind a single `_normalize_assignment_head()
    -> AssignmentCandidate` seam; `is_array_assignment()` is now just
    `_normalize_assignment_head() is not None` (peek-only) and
    `parse_array_assignment()` dispatches on the candidate instead of
    re-inspecting raw tokens. Token-shape variance lives in ONE place.
- SAFETY NET: a 46-entry frozen AST characterization corpus
  (`tests/unit/parser/test_array_assignment_characterization.py` + sidecar
  JSON) — frozen from the original parser, byte-identical after. 12 bash
  differential probes match. A1 invariants hold. Full suite green
  (6,397 passed). ruff + mypy clean.
- PINNED (pre-existing, reported, not changed): the space-separated forms
  `a [ 0 ] = v` and `a[0] =v` / `a = (...)` diverge from bash (psh parse
  error / element-or-init vs bash command-not-found); preserved exactly.

## 0.342.0 (2026-06-13) - Reappraisal #4 Tier C-B1: Word text-method discipline
- REFACTOR (zero behavior change, review Ugly 4): `Word` now exposes explicit,
  named text methods instead of forcing callers to bypass `__str__`:
  - `source_text()` — flattened parts re-wrapped in the word's quote chars
    (the old `__str__` behavior; for debug/source rendering).
  - `display_text()` — flattened pre-expansion text, no whole-word re-wrap
    (what `''.join(str(p) for p in word.parts)` used to spell out).
  - `to_literal_string()` — unchanged (quote-removed literal).
  `__str__` now delegates to `source_text()` and is documented as
  debug/source-only.
- The 9 semantic `''.join(str(p) for p in word.parts)` call sites (array,
  control-structure, and redirection parsers + the combinator special-command
  parser) and the `SimpleCommand.args` derivation now call `display_text()`,
  so the flattening rule has ONE definition. Values byte-identical.
- New `Word`-method unit tests; full suite green (6,350 passed). ruff + mypy
  clean.

## 0.341.0 (2026-06-13) - Reappraisal #4 Tier C-A2: AST sidecar cleanup
- REFACTOR (zero behavior change): removes the parallel STORED quote/type
  sidecar fields that let an AST node hold two truths at once (review Ugly 1).
  - DELETED dead `ForLoop.item_quote_types` / `SelectLoop.item_quote_types`
    (zero readers anywhere) and their population in both parsers.
  - DERIVED, no longer stored: `ArrayInitialization.element_types` /
    `element_quote_types` and `ArrayElementAssignment.value_type` /
    `value_quote_type` are now `@property` computed from the canonical `Word`s,
    reproducing the parser's prior mapping exactly. Population removed from
    both the recursive-descent and combinator parsers. The only consumers
    (`formatter_visitor`, `validator_visitor`) are unchanged.
  - NON-OPTIONAL canonical fields: `ArrayElementAssignment.value_word: Word`
    (now required) and `ForLoop`/`SelectLoop.item_words: List[Word]`
    (default `[]`); the now-unreachable `value_word is None` guard in
    `executor/array.py` was removed (construction enforces it).
- SAFETY NET: a formatter/validator round-trip characterization
  (`tests/unit/visitor/test_formatter_array_roundtrip_characterization.py`,
  40 cases over both parsers) — green before and after, byte-identical on the
  production recursive-descent parser. A1 invariants still hold. User-visible
  array/loop output matches bash. Full suite green (6,346 passed). −33 net
  production lines. ruff + mypy clean.
- One pinned divergence: for `a=(p$x q)` the combinator parser (educational-
  only) previously emitted a spurious "mixed element types" validator info
  from tokenization artifacts; deriving from the (already-split) Words removes
  it. The production parser is byte-identical.

## 0.340.0 (2026-06-13) - Reappraisal #4 Tier C-A1: AST canonical invariant lock-down
- TESTS ONLY (no production change): a safety net for the upcoming AST field
  cleanup (Tier C-A2). New `tests/unit/parser/test_ast_canonical_invariants.py`
  (39 tests, 28-snippet corpus) parses representative scripts through the
  production recursive-descent parser and asserts every node carries its
  canonical `Word`-based fields, even when nested: `SimpleCommand.words` (with
  `args` derived from `words`), `ArrayInitialization.words`,
  `ArrayElementAssignment.value_word` (non-None), `ForLoop`/`SelectLoop.
  item_words` (non-None, consistent with `items`), and `CasePattern.word`.
- New `tests/unit/parser/test_legacy_field_isolation.py`: a static meta-test
  proving the executor and expansion packages never read the legacy quote/type
  sidecar fields (`element_types`, `element_quote_types`, `value_type`,
  `value_quote_type`, `item_quote_types`) — confirming the runtime path is
  already Word-only, so deleting/deriving those fields is safe.
- Findings (documented, not changed): `for x; do` (no `in`) is normalized by
  the parser to `for x in "$@"`, so every `ForLoop` has populated
  `item_words`; `for ((...))` is a distinct `CStyleForLoop` node. All
  invariants hold for current parser output. Full suite green (6,307 passed).
- DOCS: refreshed README Project Statistics (drifted >10%); recorded the
  lexer/parser/AST elegance plan as `docs/reviews/reappraisal_4_tier_c_lexer_parser.md`.

## 0.339.0 (2026-06-13) - Expected-error taxonomy; strict-errors enabled suite-wide
- TAXONOMY (B2-R2): the last-resort guard helper `report_internal_defect`
  (`psh/core/internal_errors.py`) now distinguishes EXPECTED shell errors from
  INTERNAL DEFECTS. Expected = `PshError ∪ OSError ∪ SyntaxError` (covers
  redirection failures, fork failures, lexer/parse errors, and arithmetic
  errors); these are handled normally (message + exit code) even under
  `strict-errors`. Only genuine Python-bug exceptions (`RuntimeError`,
  `AttributeError`, `TypeError`, `KeyError`, plain `ValueError`, …) are
  re-raised under strict.
- The function-name validation errors in `psh/core/functions.py` (reserved
  word / invalid name / readonly function) were mistyped as bare `ValueError`
  (a defect signal); they are now `FunctionDefinitionError(PshError)` with the
  exact same messages — so they classify as expected shell errors.
- PAYOFF: `strict-errors` is now ENABLED SUITE-WIDE — `conftest.py` sets
  `PSH_STRICT_ERRORS=1` for both in-process shells and subprocess `python -m
  psh`. A genuine internal defect (an unexpected Python exception) now fails
  the test suite loudly instead of being masked as exit-1; expected shell
  errors pass through unchanged. This completes the strict-errors program
  begun in v0.331.0 (B2).
- ZERO behavior change in non-strict mode (byte-identical messages/exit codes
  for the representative error paths, verified before/after). Full suite green
  with strict on (6,268 passed). Added taxonomy unit tests
  (PshError/OSError/SyntaxError pass through; RuntimeError/AttributeError/…
  re-raise). ruff + mypy clean.

## 0.338.0 (2026-06-13) - Behavior fix: $0 inside a function
- BUG FIX (bash-verified): `$0` inside a function now stays the script/shell
  name, instead of becoming the function name. Run by path,
  `f(){ echo "$0"; }; f` reports the script path in psh exactly as in bash;
  `${FUNCNAME[0]}` remains the function name. Previously psh reported the
  function name for `$0`.
- ROOT CAUSE: the function executor (`psh/executor/function.py`) mutated
  `state.script_name = name` on entry "for $0" (and restored it on exit).
  bash does not change `$0` on function entry — removed the mutation. The
  function name still lives on `function_stack` (drives `${FUNCNAME[@]}` and
  local-scoping), so nothing else changed.
- CLEANUP: with `$0` no longer function-aware, `_expand_special_variable`
  (`expansion/variable.py`) now delegates `$0` to
  `ShellState.get_special_variable` along with the other raw special vars —
  completing the B6 (v0.335.0) single-source consolidation.
- A script-file differential conformance test
  (`tests/conformance/bash/test_dollar_zero_conformance.py`) pins the
  behavior against real bash; the B6 characterization cases that pinned the
  old function-name behavior were corrected. Full suite green (6,262 passed).
  ruff + mypy clean.

## 0.337.0 (2026-06-13) - Behavior fix: associative arrays in arithmetic
- BUG FIX (bash-verified): associative-array elements now resolve inside
  arithmetic `$(( ))` / `(( ))`. Previously `declare -A m; m[k]=9; echo
  $(( m[k] ))` gave `0`; now `9`. Covers reads, expressions, compound
  assignment (`(( m[k] += 5 ))`), and new-key assignment (`(( m[new]=5 ))`).
- The subscript semantics match bash: for an ASSOCIATIVE array the subscript
  is the LITERAL key text (not arithmetic-evaluated) — `m[a]` with `a=k` reads
  key `a`, and `m[i]` reads key `i` — while INDEXED arrays still
  arithmetic-evaluate the subscript (`a[1+1]`). Implemented by threading the
  `$`-expanded source into `ArithParser`, storing the raw subscript text on
  `ArrayElementNode`/`ArrayAssignmentNode`, and deciding key type in the
  evaluator by the array's kind.
- Also fixes the related gap (found while probing): array-element pre/post
  increment/decrement `a[0]++`, `m[x]++`, `++a[i]` for BOTH indexed and
  associative arrays (previously a parse error).
- +21 bash-verified tests (arithmetic characterization assoc section + array
  increment cases) and 9 `golden_cases.yaml` rows. Full suite green
  (6,262 passed). ruff + mypy clean.
- KNOWN remaining gap (pre-existing tokenizer limitation, out of scope):
  associative keys containing spaces (`m[ab cd]`) still error in arithmetic.

## 0.336.0 (2026-06-13) - Reappraisal #4 Tier B7: process failure-path tests (TIER B COMPLETE)
- TESTS ONLY (no production change): 24 deterministic, parallel-safe tests
  for the process-creation / pipeline error paths the 2026-06-13 assessment
  flagged as undertested:
  - **fork failure** — inject `OSError(EAGAIN)` into `fork_with_signal_window`
    for single-command and pipeline launches; assert graceful error, nonzero
    exit, parent signal mask restored, shell survives (extends
    `test_fork_sigmask_restore.py`).
  - **redirect failure** — output/input/permission cases: nonzero exit, the
    command body does NOT run, error on stderr, and the shell's fds are
    restored (a following command writes correctly). Permanent-fd cases run
    psh in a subprocess. Exit codes matched to bash.
  - **signal-killed exit status** — child signals itself (no race): SIGINT→130,
    SIGTERM→143, SIGKILL→137, pipeline SIGPIPE→141; all matched to bash.
  - **stopped jobs** — a PTY test that `jobs` lists a Ctrl-Z'd job as Stopped.
  - **process-sub cleanup** — 20-iteration loop proving no `/dev/fd` leak and
    no zombie accumulation; write-side `>(...)` child reaped.
  - All paths behaved correctly (matched bash on every exit code and the
    body-skipped / fds-restored guarantees). The only divergence is cosmetic
    (Python-errno vs bash redirect-error wording); tests assert non-empty
    stderr rather than pinning it.
- This release COMPLETES reappraisal #4 Tier B (v0.329.0–v0.336.0): tooling
  honesty, CI health, strict internal-error mode, and the four
  decomposition/consolidation refactors (cmdsub scanner, arithmetic package,
  WordExpander segment-IR, single-authority state) — each zero-behavior-change
  and guarded by a frozen characterization harness. Full suite green
  (6,241 passed). See `docs/reviews/reappraisal_4_tier_b.md`.

## 0.335.0 (2026-06-13) - Reappraisal #4 Tier B6: single-authority state
- REFACTOR (zero behavior change), two halves:
  - **Forked-child flag**: removed the vestigial
    `ExecutionContext.in_forked_child` (dataclass field + `fork_context()` /
    `pipeline_context_enter()` constructors). Its only references were a
    `debug-exec` print and a stale comment in `executor/strategies.py`; every
    real reader (builtins, `command.py`) and writer (`child_policy.py`,
    `subshell.py`) uses `ShellState.in_forked_child`, now the sole authority.
    The strategies.py debug print/comment were corrected to name
    `shell.state.in_forked_child`.
  - **Special-variable lookup**: `_expand_special_variable` in
    `expansion/variable.py` re-implemented raw values that already lived in
    `ShellState.get_special_variable`. The 7 byte-identical raw lookups
    (`$?`, `$$`, `$!`, `$#`, `$-`, `$@`, `$*`) now delegate to that single
    source. The expander-only layering stays in the expander: `$0`
    (function-aware), digit positionals, and the `nounset` checks. (`$*`'s
    IFS join was traced to confirm both paths use `state.ifs_star_separator`
    before delegating.)
- SAFETY NET: a 49-case characterization harness
  (`tests/unit/expansion/test_special_var_lookup_characterization.py`) over
  every special var across contexts (incl. `$*` under varied IFS, `$0` inside
  nested functions, `nounset` digit out-of-range, and a forked-builtin
  fd-level-I/O sanity class) — green before and after. Full suite green
  (6,217 passed). ruff + mypy clean.
- PRE-EXISTING divergence confirmed and preserved (recorded for a future
  behavior release in `docs/reviews/reappraisal_4_tier_b.md`): `$0` inside a
  function returns the function name in psh vs the shell name in bash.

## 0.334.0 (2026-06-13) - Reappraisal #4 Tier B5: WordExpander segment-IR
- REFACTOR (zero behavior change): the word-expansion engine
  (`psh/expansion/word_expander.py`) accumulated each part onto a mutable
  `_WalkState` using a parallel `result_parts: List[str]` + `splittable_idx:
  Set[int]` plus scattered word-level flags. That implicit representation is
  replaced by an explicit intermediate representation: a list of
  `ExpandedSegment(text, quoted, splittable, glob_eligible)`. The part
  walkers append segments; the former word-level flags
  (`has_unquoted_expansion`, `has_unquoted_glob`, `all_parts_quoted`) are now
  read-only properties derived from the segment list.
- `_finish` now runs three VISIBLY SEPARATE passes over the segments —
  `_field_split_pass` (IFS-split only the splittable segments, edge-joining
  the rest), `_glob_pass` (pathname expansion, unified for the multi-field
  and single-word cases), then join. The splitting and globbing algorithms
  are preserved verbatim.
- SAFETY NET: a 94-case frozen characterization harness
  (`tests/unit/expansion/test_word_expander_characterization.py`) over every
  axis (quote types, composite joining, `$@`/`$*`/arrays quoted+unquoted with
  affixes, IFS variations, globbing, tilde, all four policies, escapes,
  empty/unset, process-sub paths) — written FIRST, green on the original
  engine, still green after. Plus 9 adversarial bash differential probes, all
  matching. Full suite green (6,168 passed). ruff + mypy clean. No latent
  divergences found.

## 0.333.0 (2026-06-13) - Reappraisal #4 Tier B4: arithmetic decomposition
- REFACTOR (zero behavior change): the 1,155-line `psh/expansion/arithmetic.py`
  is now a package, `psh/expansion/arithmetic/`:
  - `tokens.py` — `ArithTokenType`, `ArithToken`
  - `tokenizer.py` — `ArithTokenizer` (the 213-line `read_number` split into
    per-base helpers: `_read_based_number` / `_based_digit_value` /
    `_read_hex` / `_read_octal`)
  - `nodes.py` — the `ArithNode` AST hierarchy
  - `parser.py` — `ArithParser` (the precedence ladder)
  - `errors.py` — `ShellArithmeticError`/`ArithmeticError`, `_to_signed64`
  - `evaluator.py` — `ArithmeticEvaluator` + `evaluate_arithmetic` /
    `execute_arithmetic_expansion`
  - `__init__.py` — re-exports the full prior public surface, so every
    existing importer (`evaluate_arithmetic`, `execute_arithmetic_expansion`,
    `ArithmeticError`, the tokenizer/parser/nodes) keeps working unchanged.
- SAFETY NET: a 150-case frozen characterization harness
  (`tests/unit/expansion/test_arithmetic_characterization.py`) — all bases,
  every operator, full precedence/associativity, inc/dec, all compound
  assignments, variable/array reads, the error suite — written FIRST,
  confirmed green on the original module, still green after. Full suite green
  (6,074 passed). ruff + mypy clean. Two stale doc-pointers (ARCHITECTURE.md,
  expansion/CLAUDE.md) referencing the old path were updated.
- PRE-EXISTING bug confirmed during characterization (NOT introduced here,
  identical on pristine main; recorded in `docs/reviews/reappraisal_4_tier_b.md`
  for a future behavior release): associative-array elements don't resolve
  inside `$(( ))` (`m[k]*2` → 0 vs bash 18); indexed arrays work.

## 0.332.0 (2026-06-13) - Reappraisal #4 Tier B3: cmdsub scanner decomposition
- REFACTOR (zero behavior change): `psh/lexer/cmdsub_scanner.py`'s
  `find_command_substitution_end` was a single ~341-line function and a known
  correctness hotspot. It is now decomposed into a small `_CmdSubScanner`
  class with one handler method per construct — quotes (single/double/ANSI-C/
  locale), backslash escapes + line continuation, the five `$`-expansion
  forms, backticks, comments, parens (subshell / arithmetic / group),
  separators, redirections + heredoc queueing, and the `case`/`esac` state
  machine. The public function keeps its exact signature and contract; its
  body is now one delegating line (`return _CmdSubScanner(...).scan()`).
- SAFETY NET: a 103-case frozen characterization harness
  (`tests/unit/lexer/test_cmdsub_scanner_characterization.py`) was written
  FIRST, confirmed green against the original code, and still passes
  byte-for-byte after the refactor. No latent divergences were found;
  nothing was silently changed. Six live cmdsub-boundary probes (deep
  nesting, quote-embedded parens, heredoc-with-cmdsub, arithmetic, nested
  backticks, case+cmdsub) match bash. Full suite green (5,925 passed).

## 0.331.0 (2026-06-13) - Reappraisal #4 Tier B2: strict internal-error mode
- NEW OPTION `strict-errors` (off by default; `set -o strict-errors` /
  `set +o strict-errors`, and seeded from the `PSH_STRICT_ERRORS` env var
  the way `debug-exec` is a debug-family option — settable but not listed in
  `set -o`). When on, an UNEXPECTED exception escaping command execution is
  re-raised instead of being masked as a generic `psh: ...` exit-1, so a test
  harness can tell a genuine psh internal defect apart from an ordinary
  nonzero command exit.
- SINGLE SOURCE OF TRUTH: the four structurally-identical last-resort
  "internal defect" guards — `command.py` (`_handle_execution_error`),
  `strategies.py` (`execute_builtin_guarded`), `function.py` (function body),
  and `source_processor.py` (the outermost buffered-statement guard) — now
  all delegate to one helper, `psh.core.report_internal_defect`. The
  deliberate shell-semantics / control-flow exceptions each site already
  re-raises (FunctionReturn/LoopBreak/LoopContinue/SystemExit, readonly,
  unbound, ExpansionError, ...) are unchanged.
- ZERO BEHAVIOR CHANGE with the option off: the non-strict path is
  byte-identical (same messages, same exit codes, traceback still only under
  `--debug-exec`). Default suite stays green (5,822 passed; +7 new tests in
  `tests/unit/core/test_strict_internal_errors.py`).
- FOLLOW-UP (documented, not fixed here): the strict-mode sweep surfaced ~20
  legitimate shell-error paths (bad fd / noclobber / redirect-rollback
  `OSError`, division-by-zero `ShellArithmeticError`, unclosed-quote
  `UnclosedQuoteError`, invalid/readonly function-name `ValueError`) that
  currently flow through the internal-defect guard rather than being
  classified as deliberate shell semantics. Reclassifying them (a proper
  expected-error taxonomy) is the prerequisite to ever enabling strict mode
  suite-wide; recorded in `docs/reviews/reappraisal_4_tier_b.md`.

## 0.330.0 (2026-06-13) - Reappraisal #4 Tier B: CI health
- CI SPEED: the per-PR `tests.yml` gate now runs the **full** suite in
  parallel (`run_tests.py --parallel`) instead of `--quick --coverage`, and
  all three jobs use `cache: pip`. Coverage instrumentation (the dominant
  cost of the old gate) is dropped from the per-PR path. Net: the ~6–7 min
  cycle drops to roughly 2–3 min while testing *more* (full suite vs the
  quick subset). The "Quick Test Suite" job is renamed "Test Suite".
- COVERAGE: moved to the nightly run (`nightly.yml` now passes `--coverage`
  and uploads `coverage.xml`). It was already non-gating reporting, so the
  only change is cadence: coverage is reported daily rather than per-PR.
- RELEASE LOOP: new `release-tag.yml` workflow creates the annotated tag
  `vX.Y.Z` when a `psh/version.py` bump lands on main (skips if the tag
  exists; triggers only on `version.py` changes). This makes tagging
  automatic for asynchronous / auto-merged PRs. Repo "Allow auto-merge" was
  enabled so native `gh pr merge --auto` is available.
- No production code changed; behavior is identical.

## 0.329.0 (2026-06-13) - Reappraisal #4 Tier B1: tooling honesty
- TOOLING: a bare `ruff check .` now passes. `docs/archive` (retired,
  historically-preserved material) is excluded via `extend-exclude` in
  `pyproject.toml`, and the root `conftest.py` is import-clean (dropped an
  unused `import sys`, sorted the block). The strict production gate is
  unchanged: `ruff check psh tests` still lints both live trees with zero
  tolerance (CLAUDE.md).
- DOCS: filed the independent 2026-06-13 code-quality assessment into
  `docs/reviews/code_quality_assessment_2026-06-13.md`, and recorded its
  post-verification residue as `docs/reviews/reappraisal_4_tier_b.md` (the
  plan for this tier). Discarded recommendations that verification showed
  were already shipped (combinator-parser gating, the `ruff check psh tests`
  gate, debug-print gating) or environment-specific (the two quick-suite
  "failures" pass in isolation).
- No production code changed; behavior is identical.

## 0.328.0 (2026-06-13) - Textbook program Tier B10b (TEXTBOOK PROGRAM COMPLETE)
- THE BEHAVIOR FIX (B10a's pin-sweep finding, probed 22-case matrix
  vs bash 5.2 — 11 DIFFs before, 22/22 MATCH after): exported
  variables now sync to state.env through a second ScopeManager
  observer (alongside B10a's PATH hook) firing from set_variable /
  create_local / unset_variable / attribute changes / pop_scope —
  `export FOO=old; FOO=new; printenv FOO` finally shows new; `+=`,
  arithmetic/`${:=}`/read/for-loop/nameref writes, local-shadowing-
  an-export (children see the local, restored on return), unset
  removal, and arrays-never-exported all bash-exact. The fix forced
  out real declared-but-unset semantics (`export FOO` / `declare -i
  N` plant attributed-unset variables: reads as unset, attributes
  apply on first assignment, `declare -p NAME` displays them) and
  fixed `readonly R=1; export R` erroring (bash: metadata changes
  allowed). PWD/OLDPWD now carry EXPORT. 32 conformance pins; three
  accepted divergences documented.
- declare factoring: the two ~50-line attribute if-chains are one
  table; the reporting half is shared psh/builtins/declare_format.py
  (declare -p / readonly -p / export -p — which now escapes values,
  bash-verified; the throwaway-DeclareBuiltin delegation died).
  19-case declare -p matrix byte-identical. function_support 732→639.
- read factoring: three ~210-line loops → one _read_chars core +
  thin dispatchers; SIX unshared quirks discovered and pinned (not
  homogenized): newline-vs-custom-delimiter EOF status, -n -d empty
  rc 0, -t -n immediate-EOF→142, first-byte-only timeout bound,
  silent-mode newline suppression rule, -n 0 short-circuit.
  50-probe + PTY raw-mode batteries byte-identical. 630→576.
- io_redirect residue (verify-first: B3 had NOT touched these): one
  resolve_procsub_target() with the ownership contract documented
  (the builtin path's fd-lifetime difference preserved, not merged
  away); the write-only _saved_std* ritual deleted (probed guarding
  nothing, broken under nesting anyway). Net −38.
- core smalls (verify-first): the `$*` hardcoded-space join was a
  LIVE bug reachable through two duplicates (`IFS=:; echo "${*-def}"`
  gave a b) — one ifs_star_separator() source now, 14 probes match;
  MinimalShell deleted; function.py's "inert" special-var writes were
  worse than inert (leaked `#=0`, `@=[]` into set output) — deleted;
  a provably-dead unset_variable fallback branch removed.
- Net −93 production lines. Suite: 5,815 passed / 6,051 collected,
  0 failures; ruff + mypy (20 files) + doc-pointer clean.

## 0.327.0 (2026-06-13) - Textbook program Tier B10a: hash builtin + parity queue
- The hash builtin (closing the POSIX gap found in v0.308 when CI
  revealed psh's hash tests only passed via macOS's /usr/bin/hash
  stub): CommandHashTable on shell.state (statelessness contract
  honored), HashBuiltin reusing the type builtin's PATH walk,
  parent-side strategy consult pre-fork. Bash 5.2 semantics
  replicated from ~20 probes: hits\tcommand listing, -t/-d/-l/-p/-r,
  hit counts incremented on use AND on -t lookup, builtins/functions/
  slash-names silently skipped, empty-table -d quirk, set +h
  (hashcmds now defaults ON and appears in $-), subshell inheritance
  via adopt(). Probing OVERTURNED the assumed re-verify design: bash
  blind-execs a stale hashed path by default (127 naming the path,
  stale entry kept) — re-search only under shopt -s checkhash. psh
  implements both. PATH invalidation via one ScopeManager observer,
  fired on ANY PATH write (probe-pinned: PATH=$PATH clears; cd does
  not). 3 acceptance tests unskipped; the strict-xfail ledger entry
  flipped; 26 conformance + 27 unit + 5 integration tests.
- Parity queue flipped to bash: (a) assoc-init value-tilde
  (B4's pinned accident) — h=(P=~/x v) keeps the tilde literal;
  leading-tilde and explicit [k]=~ expansion preserved, 6 conformance
  pins. (b) prefix-restore unset (B2's pin) — W=1 true leaves W
  UNSET again (the snapshot now distinguishes unset from empty; the
  old None branch was provably dead code), 8 conformance pins.
  (c) Same-family bonus: no-split contexts join field expansions
  with single spaces like bash — h=($@), h=("$@"), affixed forms,
  and notably declare v="$@" which psh had truncating to the first
  field. 12 more pins.
- Pin-sweep inventory reported for follow-up: exported-variable env
  sync on plain reassignment (REAL: printenv sees stale values —
  queued into B10b), empty assoc keys accepted, hash listing order
  (cosmetic, documented), and the ledger's remaining 10 absent
  features.
- Suite: 5,768 passed / 6,004 collected, 0 failures; ruff + mypy +
  doc-pointer clean.

## 0.326.0 (2026-06-13) - Textbook program Tier B9: one completeness oracle
- CommandAccumulator (scripting/command_accumulator.py, 298 lines):
  feed(line) -> Complete | NeedMore(hint) — the single parser-driven
  answer to "is this command complete?", extracted from the v0.306
  trial-parse machinery, not reinvented. Structured channels replaced
  ALL string matching: UnclosedQuoteError carries quote_char;
  ParseError.unclosed_expansion names the kind;
  ParserContext.open_constructs is a write-only trail (10 parse
  methods push/retitle/pop; no parse decision reads it) snapshotted
  into hints on at_eof. Heredoc bodies tracked incrementally (O(1)
  per line — a first-cut full rescan regressed the large-heredoc test
  and was caught).
- The double parse is DEAD: Complete carries the trial's AST+tokens;
  verified one parse per executed command (was two). debug-tokens/
  debug-ast/--validate/set -v/combinator outputs diffed identical.
- multiline_handler: 515 → 90 lines. The three heuristic layers'
  funeral, each wrongness bash-adjudicated: `echo {a,`/`echo {1..`
  HUNG at PS2 (bash executes) — now execute; escaped-trailing-space
  `echo \ ` hung — now executes; `echo if ; while true` showed
  `if while> ` (only a while is open) — now `while> `; a data-word
  `done` popped the for context — fixed. All 22 previously-correct
  prompt shapes preserved exactly; one inherited improvement:
  successful history expansion re-checks completeness (`if !!; then`
  continues at PS2 instead of mis-executing).
- source_processor: 448 → 286 lines. _collect_heredoc_content died
  into the oracle; the 3 errexit copies + parse-error twin became one
  _should_exit_on_error with exactly 2 call sites; 7 of 9
  string-matched lexer patterns were proven DEAD and removed.
- Net −289 production lines in the two diseased files. 46 oracle
  unit tests + 13 rewritten handler tests + 4 PTY pins for the
  adjudicated fixes. PTY tier ×2: 60 passed. Suite: 5,681 passed /
  5,921 collected, 0 failures; conformance unchanged; ruff + mypy +
  doc-pointer clean.

## 0.325.0 (2026-06-13) - Textbook program Tier B8-R3: history components + dispatch table (zero behavior change)
- The LineEditor decomposition concludes. HistoryNavigator (owns
  pos/original_line; up/down/first/last -> Optional[str]) and
  HistorySearch (feed(char) -> SearchState, a frozen dataclass with
  prompt/line/cursor/status plus repaint and redispatch fields that
  reproduce the old machine exactly) extracted as PURE components in
  psh/interactive/history_nav.py (262 lines) — the editor renders
  returned states via the renderer's prompt-override and owns mode
  transitions. The search flow was mapped first and preserved
  verbatim, including two historical quirks now pinned by tests
  (strictly-before re-search showing failed-bck-i-search on the only
  match; repeated ^R double-decrement).
- The 80-line elif chain in _execute_action is a 31-action
  dict[str, Callable] dispatch table; the vi guard test became a
  full totality test (every name in all five binding tables
  resolves, both modes).
- R1's compatibility properties DELETED — ~140 consumer sites
  migrated mechanically to edit_buffer/renderer; four thin
  navigator-state properties kept deliberately (history's setter
  preserves list aliasing with shell state). Completion UI stays in
  the coordinator: its three methods are pure glue — a sixth module
  would move coordination, not narrow a contract.
- LineEditor is now a 753-line COORDINATOR (docstring states the
  five-component architecture); components: edit_buffer 265 +
  line_renderer 249 + key_decoder 292 + history_nav 262, all in
  mypy scope (19 files). interactive/CLAUDE.md rewritten for the
  five-component reality.
- 26 new tests (11 navigator, 14 search, the totality guard).
  PTY tier green ×2. Suite: 5,641 passed / 5,882 collected,
  0 failures; ruff + mypy + doc-pointer clean.

## 0.324.0 (2026-06-12) - Textbook program Tier B8-R2: KeyDecoder (zero behavior change)
- The decomposition's risk release: psh/interactive/key_decoder.py
  (292 lines) is now the ONLY reader of stdin — it owns the char
  buffer, the select() loop (now multiplexing the SIGWINCH self-pipe:
  readable → drain → Resize event; the three-parameter
  sigwinch_fd/drain/on_resize plumbing collapsed and SignalManager.
  drain_sigwinch_notifications was deleted with its sole caller),
  EIO propagation, full-CSI/SS3-sequence consumption, and pushback()
  for vi ESC-ESC.
- KeyEvent algebra: Char / Key(name) (name=None = complete-but-
  unrecognized, swallowed) / Meta / Escape / Resize / Eof. ^C stays
  Char('\x03') — it arrives as a byte in raw mode, not a signal;
  the old division preserved exactly.
- The ESC layering resolution: timing is a decoder KNOB
  (esc_timeout=0.05 in vi — the v0.283 constant, provenance now
  documented — vs None in emacs: block, ESC is only ever a prefix);
  meaning is editor POLICY (_dispatch_escape_event: Escape→normal
  mode in vi; Meta(c) in vi→normal mode then c as a normal-mode key
  with the second ESC pushed back for full re-disambiguation).
  Edge fidelity preserved: ESC-then-EOF divisions, Delete-on-empty-
  line never EOF, leftover-paste-tail discard. One documented
  micro-delta: emacs search-accept repaint timing on a lone ESC
  (byte→action mapping identical).
- 45 pipe-fed decoder cases (all table sequences, real-timing
  bare-ESC asserting the probe waits, partial-CSI completed
  cross-thread, resize coalescing/interleaving, UTF-8, EIO,
  pushback, the 50ms constant pinned) + 13 mode-policy dispatch
  tests. line_editor.py: 914 → 855 lines; decoder in mypy scope
  (18 files).
- PTY tier green ×2, no flakes. Suite: 5,616 passed / 5,856
  collected, 0 failures; ruff + mypy + doc-pointer clean (the
  meta-test caught a stale CLAUDE.md reference mid-work).

## 0.323.0 (2026-06-12) - Textbook program Tier B8-R1: EditBuffer + LineRenderer (zero behavior change)
- The LineEditor decomposition begins, contract-first: 36 snapshot
  tests pinning exact ANSI byte sequences (the wrap-boundary
  ' \r\x1b[K' commit, multi-row paints, cursor moves across wrapped
  rows, resize arithmetic incl. landing exactly on a boundary, color/
  OSC prompts, the funneled fast-path/^C/bell/clear/completion writes)
  were written against the PRE-SPLIT code and passed 30/30 before any
  extraction; after it they run against the renderer with an injected
  StringIO — the renderer's permanent unit tests.
- EditBuffer (psh/interactive/edit_buffer.py, 265 lines): the single
  source of truth for text+cursor — pure model with kill ring,
  undo/redo (live-buffer-as-implicit-top rule), word ops, transpose's
  exact 4-branch semantics, replace_all for history recall; mutators
  return True-if-changed (the editor's repaint signal). The editor's
  buffer/cursor_pos/kill_ring/undo/redo attributes are compatibility
  properties (R3 cleanup noted).
- LineRenderer (psh/interactive/line_renderer.py, 249 lines): the
  ONLY writer of ANSI — the memo's named leaks (insert fast path,
  accept \r\n, ^C, bell, clear-screen, completion columns, search-
  prompt repaint) all funneled in; output stream injectable.
  Grep proof: line_editor.py has ZERO .write()/.flush() calls; all
  25 sites live in the renderer. Search STATE stays in the editor
  for R3; only its writes moved.
- line_editor.py: 1,064 → 914 lines. Nothing blocks R2/R3 (input
  loop, dispatch, history, search untouched). The 47-test buffer
  battery passes byte-for-byte unchanged on the compatibility
  properties; PTY tier green twice (no flakes); both new modules
  fully typed and added to the mypy scope (17 files).
- Suite: 5,583 passed / 5,823 collected, 0 failures; ruff + mypy +
  doc-pointer clean.

## 0.322.0 (2026-06-12) - Textbook program Tier B7: args derived from words (zero behavior change)
- SimpleCommand.args is now a derived, read-only @property flattening
  words — the stored parallel list is GONE and the diseased state
  (args/words divergence) is unrepresentable by construction (pinned
  by test). 89 consumer hits re-measured (the memo's 67 was stale);
  producers in BOTH parsers now build words only; the executor's
  slice/length/backslash-bypass sites operate on words (the bypass
  provably only ever strips a LiteralPart's backslash); four
  redirect-carrier nodes in strategies.py stopped passing args they
  never read.
- The characterization harness ran BEFORE the deletion: 3,593-command
  corpus, 4,455 SimpleCommands, ZERO mismatches on the recursive-
  descent parser — the derived rule reproduces the old serialization
  byte-for-byte. The combinator parser had 33 tooling-only args-view
  divergences (stored `${y}` where RD stored `$y`); unification
  resolves them — execution always read words. The harness assertion
  is a permanent invariant test.
- Honest finding: _parse_array_initialization's token re-serialization
  is LIVE, not vestigial — the flat `arr=(1 2)` string is re-parsed
  quote-aware by the declaration builtins (array_init.py); element
  Words normalize source details that re-parse differently (`${y}b`,
  `"a""b"`). The misleading Old/New-lexer archaeology comments died;
  the docstring now states why the serialization exists and what
  would have to change to kill it (declaration builtins consuming
  element Words — future work).
- Test-construction decision: 10 explicit args= sites across 4 test
  files — fixed the tests rather than adding a constructor affordance
  (honesty over affordance).
- Perf: the property recomputes per access; measured within noise of
  baseline (0.772s vs 0.798s best-of-3 on an assignment-heavy loop) —
  no cache, no invalidation invariant.
- 17 probe anchors byte-identical incl. xtrace, $_, --debug-ast
  shapes, and all four analysis tools. Suite: 5,547 passed / 5,787
  collected, 0 failures; conformance identical to baseline;
  ruff + mypy + doc-pointer meta-test clean.

## 0.321.0 (2026-06-12) - Textbook program Tier B6: the lexer stops guessing
- literal.py 764 → 326 lines. The four retro-scanning heuristics
  (_is_in_variable_assignment_value's rfind, the "likely/probably"
  _is_in_string_concatenation, _looks_like_array_assignment_before_
  plus_equals, _is_potential_array_assignment_start) are DEAD,
  replaced by pure functions in recognizers/word_scanners.py (623
  lines: scan_glob_bracket / scan_extglob_group /
  scan_assignment_prefix / scan_inline_ansi_c) and an explicit
  forward WordShapeTracker (NEUTRAL → ASSIGN_NAME → ASSIGN_VALUE)
  fed per character — the lexer KNOWS what segment it is in. The
  action-tuple protocol is gone; its 'break' arm was dead code.
  The lexer-level assignment map is built once, cached on
  LexerContext, and consulted instead of re-derived; where it cannot
  be sole authority (boundary-anchored, escape-blind) the supplement
  is the module docstring's documented centerpiece with adversarial
  corners pinned.
- The tokenize loop is TOTAL: the silent char-drop stage is now a
  fail-loudly RuntimeError (census across 15k corpus + full suite +
  71k fuzz inputs: ZERO hits); the fallback word-collector stays —
  the census found it heavily live for exactly four word-start
  classes (']' 1,429 hits, '+' 705, '=' 400, '[' 225), all 11
  representative shapes bash-probed identical — with the census data
  and rationale in its docstring and pins in test_fallback_words.py.
- Packaging: find_command_substitution_end + helpers (519 lines) →
  psh/lexer/cmdsub_scanner.py with its Maintenance Contract intact;
  pure_helpers.py 1,097 → 574 (genuinely pure char-level helpers);
  one command-position vocabulary in command_position.py with the
  three-machines docstring and the fi/done/esac asymmetry documented
  and mechanically verified; tokenize/tokenize_with_heredocs share
  _post_lex.
- Safety: a 15,091-input characterization harness (golden cases +
  generated pathological matrix + 14k harvested literals) diffed
  ZERO token-stream changes after every step — it caught two
  transitional import stragglers mid-refactor. A 957-input
  frozen-stream corpus is now a permanent test.
- Net production diff: +345/−1,294. 53 new tests (scanner contracts
  incl. a retro-predicate oracle over ~3.4k prefixes, fallback pins,
  corpus). Suite: 5,543 passed / 5,783 collected, 0 failures;
  ruff + mypy + doc-pointer meta-test + CPU-perf guards clean.

## 0.320.0 (2026-06-12) - Textbook program Tier B5: ONE parameter-expansion parser
- The program's headline-risk release and its oldest structural
  finding, closed: expansion/param_parser.py's
  parse_parameter_expansion(content) is now the SINGLE ${...}
  grammar (228 lines, ~90 of them a grammar-reference docstring with
  the documented scan strategy: earliest position wins, longest
  operator at that position, bracket-depth-aware). All four sites
  unified: WordBuilder delegates (86→14 lines, covers the combinator
  too) and STOPS deferring subscripted forms — the AST no longer
  lies: ${arr[@]:1:2} is ParameterExpansion('arr[@]', ':', '1:2') at
  parse time (was parameter='arr[@]:1:2', operator=None);
  ParameterExpansion.parse_expansion (152 lines) DELETED;
  expand_variable's pre-dispatch ladder + _is_plain_subscript
  DELETED (string contexts keep their string ENTRY — now
  parse-then-evaluate through the same parser);
  fields._parse_trailing_op DELETED, plus 72 ladder-only lines.
  Net: −460/+112 production lines + the new module.
- The mandatory differential harness (737 distinct ${...} contents
  harvested from the corpus) found 19 divergences BETWEEN THE OLD
  PARSERS — each adjudicated by bash 5.2 probe. 18 behavior fixes
  ride along (presented honestly as fixes, not refactor): the
  ${a[@]:-def}/:=/:+ family after [@] (the := case CRASHED with
  "invalid offset or length"); non-colon operators after ] (
  ${arr[0]-d}, ${a[i+1]+x} were empty); scan-order ${v:-x@Q};
  ${#-} and ${#:-default} disambiguation; element indirection
  ${!a[0]}/${!h[k]}; scalar-subscript resolution unified (${#x[0]}
  was path-dependent 0-vs-5). All-paths-agreed psh↔bash gaps kept
  and documented (${##}, ${v~~}, assoc-slice ordering).
- The evaluator's operator-less round-trip branch instrument-verified
  unreachable for operator-bearing forms (plugin re-parsing every
  node across 1,487 tests: no violations) and narrowed.
- Permanent pins: the 737-row frozen expectation corpus
  (test_param_parser_differential.py — pinned against a frozen table
  with documented provenance, NOT the deleted code), 130+ grammar
  cases, 24 behavior-fix pins. Conformance: POSIX 162/162, bash
  210/217 (the 5 concerns are pre-existing printf message-prefix
  comparisons).
- Suite: 5,490 passed / 5,730 collected, 0 failures; ruff + mypy +
  doc-pointer meta-test clean.

## 0.319.0 (2026-06-12) - Textbook program Tier C1: the internals tour
- New docs/architecture/tour_of_psh_internals.md (516 lines): traces
  `echo "Hello, $USER" | wc -c > out.txt` through input processing →
  tokenization → keyword normalization → parsing → Word-AST expansion
  → pipeline execution → exit status. The defining property: every
  illustration is REPRODUCIBLE — real --debug-tokens/--debug-ast/
  --debug-expansion/--debug-exec output generated this session, with
  the exact regeneration command beside each artifact and trims
  marked. Flag gaps worked around honestly (RichToken parts shown via
  a 3-line public-API snippet; keyword normalization via a two-dump
  contrast). Ends with three trace-it-yourself variations (command
  substitution → run_child_shell; procsub expansion part + scope;
  for-loop keywords + LOOP_ITEM policy), each probe-verified.
- Reader paths wired: ARCHITECTURE.md's note line, the user guide's
  new "Going Deeper" section, root CLAUDE.md's orientation paragraph.
- The doc-pointer meta-test's file list extended to scan the tour —
  its references are enforced like every other load-bearing doc.
- Closes the teaching-mission gap reappraisal #3 graded C+ (the repo
  documented psh as a product; now it teaches it as a textbook).
- Quick gate: 5,324 passed, 0 failures; ruff + mypy clean.

## 0.318.0 (2026-06-12) - Textbook program Tier B3: shared forked-child runner (zero behavior change)
- run_child_shell(parent_shell, body, *, norc, io_setup, error_label)
  in executor/child_policy.py completes the P2 design: signal policy ->
  caller io_setup (BEFORE Shell construction — terminal detection
  inspects fds) -> Shell.for_subshell + in_forked_child -> body ->
  flush_child_streams -> os._exit, with SystemExit(n)->n and unexpected
  exceptions reported to FD 2 (not sys.stderr — the child's stream may
  be a parent-side capture object) -> exit 1.
- The before-tabulation showed how uneven the three child paths were:
  process_sub had NO flush, NO SystemExit mapping, and its signal-
  policy call outside any try; command_sub and ProcessLauncher each
  differed in error channel and flush set. Both substitution sites now
  share the runner; ProcessLauncher KEEPS its own child path
  (pgroup/sync-pipe setup, exec semantics, parent-Shell reuse) with
  the rationale in its docstring, but shares flush_child_streams and
  the fork/signal helpers as code, not copies.
- command_sub's parent-side SIGCHLD reset KEPT with the explanatory
  comment the memo asked for: the interactive SignalManager reaps via
  waitpid(-1, WNOHANG); the SIG_DFL span makes the substitution's
  status capture race-free (script mode: no-op). Proving it vestigial
  needs interactive race probes — deferred deliberately.
- ARCHITECTURE.md invariant #6 strengthened truthfully: One Fork
  Helper, One Child Signal Policy, One Substitution-Child Runner.
- 15-probe battery byte-identical; PTY tier green (56 passed — flush
  changes caused no timing regressions); 12 new tests incl. a
  subprocess driver pinning the runner's exit-code mapping through a
  real fork.
- Suite: 5,324 passed / 5,564 collected, 0 failures; ruff + mypy +
  doc-pointer meta-test clean.

## 0.317.0 (2026-06-12) - Textbook program Tier B4: WordExpander + named policies (zero behavior change)
- Every expansion context has a NAME: frozen WordExpansionPolicy
  (split/glob/assignment_tilde — a caller tabulation proved three
  axes cover every flag tuple in the tree) with named instances
  COMMAND_ARGUMENT, DECLARATION_ASSIGNMENT, LOOP_ITEM (an alias of
  COMMAND_ARGUMENT, by design), ARRAY_INIT_ELEMENT,
  ASSOC_INIT_ELEMENT, consumed by the new
  expansion/word_expander.py engine. The 238-line flag-multiplexed
  _expand_word is decomposed into named phases (expand → walk-literal
  / walk-expansion on a _WalkState → finish: join → split → glob).
  The suppress_split_glob→declaration_assignment ALIASING TRAP is
  dead: the parameter no longer exists; expand_word_to_fields takes a
  required named policy (TypeError pinned by test).
- The scalar assignment-value walker lives beside the policy table in
  the same module, with the docstring explaining why the two walkers
  stay separate. Escape processors moved with the engine (NOT to
  utils/escapes.py, per its dialect-map exclusion).
  _word_to_string became Word.to_literal_string() on the AST
  (could not reuse __str__ — it re-wraps quotes; divergences
  documented). The arithmetic adapter moved into arithmetic.py.
- ExpansionManager: 944 → 267 lines — expand_arguments, the
  declaration-builtin recognition, debug plumbing, and thin public
  delegates (every name ast_data_flow.md documents survives).
- Honest finding pinned under the zero-change contract: the aliasing
  accidentally re-enabled value-tilde in assoc initializers —
  `declare -A h; h=(P=~/x v)` expands the tilde where bash 5.2 keeps
  it literal. Pinned as a PINNED HISTORICAL ACCIDENT with probe/test
  coverage; the one-line bash-parity flip is queued as a future
  behavior fix. Also pinned: the standalone unquoted $@/${a[@]} fast
  path ignores policy split/glob (pre-existing).
- 26-probe battery byte-identical before/after; 20 new policy/engine
  tests. Suite: 5,320 passed / 5,560 collected, 0 failures; ruff +
  mypy (ast_nodes.py annotations extended) + doc-pointer meta-test
  clean.

## 0.316.0 (2026-06-12) - Textbook program Tier B2: CommandAssignments (zero behavior change)
- The assignment sub-domain (9 methods, ~260 lines — what NAME=value
  prefixes MEAN) extracted from CommandExecutor into
  executor/command_assignments.py: CommandAssignments(shell) with
  extract() / apply_pure() / apply_prefix() -> PrefixOutcome
  (saved/applied/failed NamedTuple — the dispatcher genuinely needs
  all three: exec persistence, errexit fatality) / restore().
  CommandExecutor: 724 → 477 lines; _execute_command reads as its
  dispatch shape. The module docstring states the POSIX ordering
  contract once, five probe-verified clauses (words-before-
  assignments, left-to-right value visibility, temporariness +
  special-builtin persistence, the cmdsub status rule, the readonly
  path split).
- Design choice proven by probe: the last_cmdsub_status CLEAR stays
  in the dispatcher (the read moved into apply_pure) — `V=v $(false);
  echo $?` → 1 in both shells because the determining substitution
  runs during command-word expansion before the empty result reroutes
  to the pure path. Moving the clear would have broken it.
- The _visitor backchannel is gone: CommandExecutor takes the visitor
  as a constructor parameter; no getattr-based hidden channels remain
  anywhere in psh/executor/ (repo-wide survey of the remaining 5
  getattr(self,'_...') patterns reported in the PR — all legitimate
  lazy-init flags outside the executor).
- Pre-existing quirk found and pinned (not fixed): prefix-assignment
  restore leaves a previously-UNSET variable set-but-empty
  (`W=1 true; echo ${W+yes}` → psh yes, bash nothing) — snapshot via
  get_variable's '' default; pre-dates this change; candidate for a
  future bash-parity fix.
- 22-probe battery byte-identical before/after (14 bash-exact, 6
  documented pre-existing diffs preserved verbatim). 12 new unit
  tests on the class's public surface.
- Suite: 5,300 passed / 5,540 collected, 0 failures; ruff + mypy +
  doc-pointer meta-test clean.

## 0.315.0 (2026-06-12) - Textbook program Tier C2: doc integrity
- New doc-pointer meta-test (tests/unit/tooling/test_doc_pointers.py):
  six high-precision rules resolving backticked paths and symbol
  references across ARCHITECTURE.md, ast_data_flow.md, and all nine
  CLAUDE.mds, with a commented exemption list for tutorial
  placeholders. Calibrated against pre-fix docs: it caught the known
  §5.3 expand_command_substitution ghost AND a previously unknown
  phantom lexer architecture in §2.1–2.4 (LexerState, StateManager,
  TokenMetadata, Token.add_context — none exist anywhere); §5.1's
  pre-Word-AST expand_argument ghost; a wrong §5.4 file marker.
  All rewritten to the real architecture. Docs can no longer
  reference code that doesn't exist without failing the suite.
- ARCHITECTURE.md truth pass: the One-Fork-Path invariant reworded to
  what is actually true (every fork via fork_with_signal_window() +
  apply_child_signal_policy(); job-controlled creation through
  ProcessLauncher; substitutions fork directly by design — same fix
  in root CLAUDE.md); §5.3 rewritten around the real
  CommandSubstitution.execute(); B1 staleness swept (7-phase Shell,
  for_subshell, visitor_modes.py); combinator "100%" parity and
  "state machine lexer" framings corrected.
- README statistics regenerated (~49,100 LOC / 193 files; ~59,500
  test lines / 262 files) and PINNED by a new tolerance test
  (±10%, including a live --collect-only count) so they fail loudly
  instead of silently lying.
- The three v0.286-frozen CLAUDE.mds refreshed via claim-by-claim
  subagent audits: core (+ShellState.adopt() section, for_subshell
  wording), builtins (+statelessness contract, printf_formatter
  extraction, SHELL_BUILTINS relationship, write_error_line),
  interactive (audit found ZERO wrong claims after 28 releases;
  v0.295/v0.300 sections added).
- Archive sweep: 30 stale files moved to docs/archive/guides/ (8
  bannered guides, 20 public-api point-in-time files, 2 unbannered
  2026-02 guides); docs/guides/ now holds only the two current
  combinator docs.
- CHANGELOG split: 122 pre-v0.200.0 entries moved to
  docs/archive/CHANGELOG_history.md (4,297 → ~2,490 lines) with
  pointer; verified nothing parses it programmatically.
- Probe-promotion convention added to the bash-verification workflow:
  surviving probes become golden_cases.yaml entries, not tmp/ debris.
- Suite: 5,528 collected (16 new tooling tests); quick gate green;
  ruff (psh+tests) + mypy clean.

## 0.314.0 (2026-06-12) - Textbook program Tier B1: Shell lifecycle (zero behavior change)
- Shell.__init__ is now 31 lines (was 122): seven named lifecycle
  phases, each docstringed with its before/after state —
  _create_state, _init_managers, _inherit_from_parent,
  _init_shell_components, _select_parser, _init_traps,
  _init_interactive. shell.py's module docstring finally answers
  "what is a Shell?" from the file itself.
- Shell.for_subshell(parent, *, norc=True) replaces the inline
  parent-inheritance block; the pure state-copying half lives in
  ShellState.adopt(parent_state). All five construction-with-parent
  sites migrated (foreground/background subshells, command
  substitution, process substitution, the env builtin — the last two
  keep their historical norc=False explicitly; quirk noted for a
  future look). 12 new tests pin exactly what a child inherits.
- The CLI analysis modes (--validate/--format/--metrics/--security/
  --lint, 77 lines) moved off Shell to scripting/visitor_modes.py;
  all five probed byte-identical.
- The forwarding magic is GONE: __getattr__/__setattr__/
  _setup_compatibility_properties deleted. Four explicit properties
  (stdout/stderr/stdin/env, with write-through setters — ~126 of the
  forwarding's production uses) remain as Shell's deliberate public
  face for builtins; the other 37 production + 8 test sites were
  rewritten to shell.state.X. A typo'd shell.attr now raises
  AttributeError instead of silently reading ShellState — pinned by
  test. One regression during the sweep (return builtin's
  function_stack read on a line that mixed both forms) was caught by
  the suite's 33 failures and root-fixed, then the sweep re-run with
  a per-occurrence regex: zero residuals.
- psh/shell.py joins the mypy files list (15 files now), fully
  annotated, zero ignores.
- Suite: 5,273 passed / 5,513 collected, 0 failures; ruff + mypy
  clean. Refactor contract: zero behavior change — subshell/procsub/
  cmdsub/env/source/rc-file/parser-selection batteries and all five
  analysis modes probed identical.

## 0.313.0 (2026-06-12) - Textbook program Tier A2: test/CI honesty (TIER A COMPLETE)
- Timing tests measure CPU time: test_lexer_performance.py and the
  benchmark helpers use time.process_time() + min-of-3 (preemption
  steals wall time, not CPU time). Regression sensitivity PROVEN by
  temporarily injecting an O(N²) loop (failed at ratio 4.0) and
  removing it. The xdist timing-flake class is closed.
- Skip-debt purge: the 5 legacy interactive files (53 dead skips with
  false reasons) deleted AFTER porting their 6 uncovered behaviors to
  the PTY smoke tier — Ctrl-R reverse search, unique-file and
  common-prefix tab completion (pass), command/variable completion
  (strict xfail: CompletionEngine is path-only — flips loudly when
  implemented), Ctrl-L screen clear, pipeline-in-PTY. The wrong
  subshell xfail rewritten to pin bash semantics (subshell exit 0 when
  the failing command isn't last — bash agrees). Census: 272 skips /
  1 xfail → 220 skips / 20 xfails, every reason now true and
  printable via the new --census flag.
- Absent-feature ledger (tests/conformance/bash/
  test_absent_features.py): 19 features probed firsthand against bash
  5.2.26 — 18 strict-xfail entries (coproc, wait -n/-f, read -u, bind,
  compgen, complete, caller, hash, enable, exec -a, lastpipe,
  failglob, ${a[@]@K}, extglob-in-param-expansion, jobs -x, suspend,
  test -v) + 1 documented-wontfix skip (history expansion). The two
  SILENT TRAPS are called out: @K degrades to plain values rc 0, and
  shopt -s extglob reports "on" while patterns are inert in parameter
  expansion. "98% compliance" now has an honest denominator;
  implementations flip entries loudly.
- visitor SHELL_BUILTINS documented as bash-scoped, 13 missing
  registry builtins added, and pinned in BOTH directions by a new
  test (registry ⊆ list; extras must be on an explicit allowlist that
  itself fails if psh implements one).
- Builtin statelessness enforced: ~60-command battery then
  vars(instance) == {} for every registered builtin; contract
  documented in base.py. Caught a real bug: an executor test fixture
  leaked its builtin instance into the registry process-wide.
- directory_stack/help channel-convention sweep (raw prints →
  write_line); probing fixed real divergences: dirs -p added,
  dirs/popd/pushd -N off-by-one corrected (bash counts from the
  right, 0-based), dirs -v uses bash's two-space separator.
- CI: quick-suite job uploads a non-gating coverage.xml artifact
  (run_tests.py --coverage threads cov args through every phase);
  new nightly.yml (cron 03:00 UTC + workflow_dispatch) runs the full
  parallel suite with --compare-bash --census plus the complete
  conformance suite, printing bash --version. run_tests.py prints
  combined cross-phase totals.
- Suite: 5,261 passed / 5,501 collected, 220 skipped, 20 xfailed;
  ruff (psh+tests) + mypy clean.

## 0.312.0 (2026-06-12) - Textbook program Tier A1: behavior batch
- printf: the ~550-line formatting engine extracted to pure
  utils/printf_formatter.py (format_printf(fmt, args) -> PrintfResult;
  no shell dependency; the builtin thins to ~50 lines; print -f
  migrated too). Fixed against a ~90-case bash 5.2 probe battery:
  `%*`/`%.*` width/precision from arguments (negative width
  left-justifies, negative precision omitted); `%n` assigns
  chars-written; `%p`/`%v` and bare `%` are bash-shaped fatal errors;
  integer parsing is strtoll base-0 (0x/0 prefixes, 'A char codes,
  trailing-junk warnings, 64-bit wrap for %u/%x/%o, overflow clamp at
  rc 0); `%c` takes the first character (psh's old chr() behavior was
  wrong — `printf '%c' 65` prints 6); `%b \c` terminates all output;
  length modifiers accepted; `printf --` handled. 59 engine tests +
  18 builtin tests + 4 conformance tests.
- All three fork sites now share fork_with_signal_window() in
  executor/child_policy.py — command_sub.py and process_sub.py never
  received the v0.300 lost-signal fix (latent race, found by
  reappraisal #3). Also: process_sub's temp shell now sets
  in_forked_child=True; command_sub's silent bare-except writes the
  exception to fd 2 before _exit.
- Readonly-prefix assignments match bash: `RO=2 cmd` reports the error
  and STILL RUNS the command (rc = command's); other prefix
  assignments apply-then-restore (also fixed a restore leak where
  `OK=5 RO=2 true` left OK set permanently); pure `RO=2` aborts rc 1;
  under errexit the error is fatal and the command does not run.
  25-case probe matrix; 10 conformance tests; 2 old tests pinned the
  anti-bash behavior and were updated after bash verification.
- os.environ is read-once at startup: state.env is authoritative and
  every child receives it explicitly (execvpe/shebang env=/parent_shell
  copy — verified). All four vestigial os.environ writes deleted
  (allexport, export_variable, the `FOO=bar exec` leak, export -n
  pop); zero writes remain in psh/. Policy documented in ShellState's
  docstring and core/CLAUDE.md. Corrected claim along the way: bash
  does not persist `FOO=bar exec` without a command; psh now matches.
- Dead code deleted (~135 lines, callers re-verified): arrays.
  is_array_expansion, CommandExecutor._extract_assignments/_is_exported
  + assignment_utils.extract_assignments/is_exported chain, manager.py
  dead public expand_variable()/execute_command_substitution().
- Suite: 5,249 passed / 5,522 collected; ruff (psh+tests) + mypy clean.

## 0.311.0 (2026-06-12) - ARCHITECTURE.llm retired (doc consolidation)
- ARCHITECTURE.llm moved to docs/archive/ (git mv, content untouched).
  Rationale: its LLM-orientation role is now better served by the
  subsystem CLAUDE.md network + docs/architecture/ast_data_flow.md,
  and the dual file was a proven drift surface (the v0.298 purge had
  to hit both files; v0.305 left three stale TokenTransformer
  references in the .llm alone).
- Its uniquely valuable content folded into ARCHITECTURE.md as a
  leading "Quick Map" section: component hierarchy tree (refreshed —
  visitor/ package added, pattern.py and the educational-only
  combinator status reflected), one-line-per-phase execution
  pipeline, architecture invariants (updated: One Fork Path and
  Fail Loudly added; stale arg_types history dropped), and a
  "Where do I change X?" table pointing at subsystem CLAUDE.mds.
- References updated: root CLAUDE.md release ritual now lists four
  version-stamped files (and now documents the PR + CI-green +
  tag workflow that has been practice since v0.279); six guide
  cross-references repointed; ARCHITECTURE.md's pointer note
  replaced with the orientation path (Quick Map → subsystem
  CLAUDE.md → ast_data_flow.md).
- One fewer drift surface; no content lost (archive retains the
  full historical file).

## 0.310.0 (2026-06-12) - Hygiene release: fallback audit, AST data-flow doc, scanner contract
- Every string-only legacy AST fallback audited and classified
  (reassessment next-steps #1/#2/#4): each site checked against every
  construction point in BOTH parsers plus direct test construction.
  Outcomes: (a) required-compatibility — for/select item_words=None
  manual-AST path, kept + tested; (b) migration bridge — combinator
  CasePattern(word=None) for exotic patterns, kept + tested with an
  AST-inspection canary that fires if the combinator gains support;
  (c) unreachable-defensive ×7 — replaced with internal-error raises
  per the v0.300 fail-loudly policy (incl. _expand_word's silent
  str(word) coercion and a fallback whose comment claimed a combinator
  edge that no longer exists); (d) dead ×2 — deleted (~106 lines incl.
  the whole legacy explicit-[i]=v string re-parser).
- The audit found a LIVE bash divergence in a "dead" fallback: the
  legacy explicit-element branch keyed on element_types and OVERRODE
  correct Word semantics — `a=("[0]"=x)` assigned a[0]=x where bash
  keeps the literal element `[0]=x`. Fixed by deletion;
  conformance-pinned.
- New docs/architecture/ast_data_flow.md (~200 lines, linked as
  ARCHITECTURE.md §3.13): the canonical build-site → expansion-policy →
  implementation pointer for command words, assignment values, array
  initializers/elements, for/select items, case subject/patterns,
  redirect targets/heredocs (the legitimate string contexts),
  process substitution, and compound-redirect visitor totality —
  with an "I want to change X → edit here" table. Every pointer
  verified against source.
- find_command_substitution_end gained a Maintenance Contract
  docstring block (parser-grammar changes touching case/heredoc/
  quoting/arithmetic must consider the scanner; owner tests listed);
  16 new bash-probed conformance cases (nested functions in $(),
  procsub inside $(), $(case) in heredoc bodies, quoted-paren
  patterns, arithmetic with case-like names, rc-pinned unclosed-EOF
  boundaries).
- 32 new tests. Suite: 5,151 passed / 5,424 collected;
  ruff (psh+tests) + mypy clean.

## 0.309.0 (2026-06-12) - Combinator parser declared educational-only
- Project decision (resolving a question raised by three successive
  external reviews): the combinator parser is EDUCATIONAL ONLY and
  outside the production quality bar. Parity regression tests continue
  to pin known-good behavior against drift, but documented gaps (e.g.
  composite words in some list contexts, `select` without `in`) are
  not tracked as defects, and conformance work does not target it.
  The decision may be revisited when dedicated time is available.
- Recorded everywhere the status is stated: the class docstring
  (combinators/parser.py), parser/CLAUDE.md (with a note that reviews
  should not count its gaps as findings), the combinator guide banner,
  ARCHITECTURE.md/.llm, parser-select help, and --parser CLI help.
- README's inaccurate parity claims corrected: "100% feature parity"
  (×2) and "Both parsers support all shell constructs" replaced with
  the accurate framing — these claims predated the parity-regression
  work and were verifiably false (the gaps are documented in the
  parity test files and reviews).
- No behavior changes; parser-select and --parser combinator work
  unchanged.

## 0.308.0 (2026-06-12) - CI green (first passing run in the workflow's history)
- The Tests CI workflow had NEVER passed — 190+ consecutive failures
  going back past v0.287. Two quality reviews verified the workflow
  CONFIGURATION matched the docs; nobody (reviewer or maintainer)
  checked an actual run result. Lesson recorded: "CI matches the
  documented gate" must mean a green run URL, not a config read.
- Quick-suite job: [dev] extras were missing pyyaml (behavioral
  golden-case loader) and pexpect (PTY-tier modules import it at
  collection time even though the tests are runtime-gated) — 6
  collection errors on every run. Added both.
- Lint job: CI runs `ruff check psh tests`; the documented local gate
  was `ruff check psh/` only. CLAUDE.md now mandates the CI command;
  the one outstanding test-tree lint error fixed.
- 17 environment-portability test bugs fixed once the suite actually
  ran on ubuntu (all test bugs, no product bugs): hardcoded
  /Users/pwilson cwd in the assoc-array regression file; a hardcoded
  '~/src/psh' fallback in 7 directory-stack assertions (replaced with
  an independent tilde-abbreviation helper — strictly stronger);
  BSD-vs-GNU ls exit codes pinned in 2 redirection tests (now derived
  from the local tool at runtime / switched to POSIX-pinned test -e);
  a 300KB script passed as one argv element (Linux MAX_ARG_STRLEN is
  128KiB — heredoc tests now run via script file).
- Product gap discovered: psh has NO hash builtin — the two hash
  tests only ever passed because macOS ships /usr/bin/hash, a 4-line
  sh stub that runs in a throwaway subprocess (they never exercised
  psh code). Skipped with the gap documented in the reason; implement
  hash to unskip.
- All three CI jobs green on PR #40 (Lint 16s, Conformance Smoke 39s,
  Quick Test Suite 4m56s); full local suite green; ruff + mypy clean.

## 0.307.0 (2026-06-12) - Visitor totality over the AST (reassessment Phase 3 — PHASE 3 COMPLETE)
- Finding #8 and Phase 3: the analysis visitors are now total over the
  AST, enforced by an introspective coverage-matrix test. The
  before-matrix found far more than the review's two examples:
  - Formatter: UntilLoop hit the unknown-node fallback (the repro);
    FunctionDef and ArithmeticEvaluation DROPPED their redirects;
    background `&` lost on AndOrList; no word-level methods. Now has
    an explicit visit method for all 36 concrete node classes, with
    reparse round-trip tests.
  - Security visitor: 6 of 13 redirect carriers (while/for/if/case/
    function/arithmetic) never inspected their redirects —
    `while ...; done >/etc/passwd` reported nothing. All carriers
    now flag sensitive writes via a shared _visit_redirects().
  - Validator: UntilLoop, SubshellGroup, BraceGroup, and
    ArithmeticEvaluation subtrees were SILENTLY SKIPPED entirely
    (`until ...; do break 5; done` and `( break )` produced zero
    diagnostics); compound redirects never validated. Fixed.
  - Metrics: redirections/heredocs counted only on SimpleCommand;
    debug-ast lost children of until/subshell/brace-group. Fixed.
  - Linter and the executor visitor verified total already (the
    executor raises on unknown nodes — no gaps).
- tests/unit/visitor/test_ast_coverage_matrix.py (85 tests):
  programmatic node inventory (36 concrete classes, 7 abstract
  bases); per-visitor totality assertions matching each visitor's
  documented generic_visit design; a redirects matrix proving every
  source-reachable carrier (13) is security-flagged,
  formatter-emitted, and metrics-counted. ALL exemption lists are
  EMPTY except REDIRECT_EXEMPT={Break,Continue} (their redirects
  fields are unreachable from source — both parsers parse `break >f`
  as two statements; pinned by a dedicated test). Adding a new AST
  node without visitor support now fails the suite loudly.
- visitor/CLAUDE.md: new "Totality Over the AST (enforced)" section;
  wrong example name fixed; new-node checklist points at the matrix.
- Suite: 5,122 passed / 5,392 collected; ruff + mypy clean.

## 0.306.0 (2026-06-12) - Grammar-aware command substitution (reassessment Phase 2, 2/2 — PHASE 2 COMPLETE)
- The long-standing Known Limitation is CLOSED: `$(case x in x) echo
  inner;; esac)` parses and runs (bash prints `inner`; psh errored at
  `;;` in both parsers since the paren-counting scanner predates the
  reappraisal programs). New pure scanner find_command_substitution_
  end() in pure_helpers.py models exactly the contexts where `)` is
  not a closer: quotes (incl. $'...' and nested-expansion rescan),
  backticks, ${...}, nested $(...), $(( ))/(( )) arithmetic with the
  lexer's greedy dispatch, # comments at word start, heredocs
  (pending-delimiter queue shared across nesting levels — bash reads
  bodies at the next physical newline regardless of depth, probed),
  group parens, and a case-statement state stack (case at command
  position → subject → in → pattern⇄body via ;;/;&/;;&, one unmatched
  `)` per pattern, esac pops). Design rationale lives in the
  docstring — it replaces ARCHITECTURE.md Known Limitation #2.
- All seven paren-counting consumers upgraded to the scanner:
  expansion_parser, process-sub recognizer (`<(case ...)` works),
  $((...)) extent, ${...} validation, array-word shapes, the
  execution-time operand scanner, and heredoc line-gathering's
  inside-expansion check.
- Three pre-existing multiline bugs fixed (exposed by the probe
  battery, all broken on main): unclosed-expansion ParseErrors now
  set at_eof=True so multiline `$(\necho hi\n)` gathers continuation
  lines; the source-processor completeness check uses
  tokenize_with_heredocs (a heredoc body line `)` was a bogus parse
  error); multi-line buffers starting with `#` were swallowed whole
  by two comment-skip checks.
- Probe battery 13/34 → 32/34 exact matches; the 2 remaining are
  deliberate documented divergences (escaped-paren pattern rejected
  by both shells with different wording; same-line shopt extglob
  timing where psh matches `bash -O extglob`).
- Docs: ARCHITECTURE.md limitation replaced with fixed-by note;
  user-guide ch6 note deleted, ch17 row note updated; call-site
  comment rewritten as design doc. Claims meta-test green.
- 85 new tests (51 scanner/lexer unit, 23 integration incl. both
  parsers and stdin/script modes, 11 conformance).
- Suite: 5,037 passed / 5,307 collected; ruff + mypy clean.

## 0.305.0 (2026-06-12) - Grammar boundaries: case subject, bracket quotes, TokenTransformer (reassessment Phase 2, 1/2)
- Finding #6: `case` now parses exactly one subject word before `in` —
  `case a b in ...` is a bash-shaped syntax error (was silently
  accepted, joining the words). Four adjacent divergences fixed by
  probing: `case in in ...` and `for in in ...` work (the token after
  case/for/select is never the `in` keyword), newlines allowed before
  `in` but rejected after `case`, and empty `case a in esac` is valid
  while `esac)` as a pattern is rejected — all bash-exact.
- Finding #5 (broader than stated): the lexer suppressed quote AND
  expansion parsing for any unmatched `NAME[` shape. Now only
  confirmed `NAME[...]=`/`+=` subscripts suppress; consequently
  unterminated quotes in bracket words are lexer errors
  (`echo x["unterm` was silently literal), and `x["ok"]`, `x[$v]`,
  `x[$((1+1))]` finally quote-remove/expand like bash. Escaped quotes
  in glob brackets preserved; assignment forms (`h["k 1"]=v`,
  `a[$(cmd)]=y`) probe-pinned. No lexer performance regression
  (benchmarked).
- Bonus fix required by the keep-working battery (broken on main):
  `${h["key"]}` returned empty — assignment stripped wrapping quotes
  but lookup didn't. New expand_assoc_key() applies the same quote
  removal at all five assoc lookup sites (`${h['k']}`, `${h["$k"]}`,
  `${#h["key"]}` all match bash now).
- Finding #9: TokenTransformer DELETED — verified every branch
  appended the original token unchanged (validation intended at
  v0.27.1, never implemented) and the parser already rejects
  misplaced `;;`/`;&`/`;;&` with bash-shaped errors. Docs updated
  (lexer CLAUDE.md pipeline, ARCHITECTURE.llm, guides).
- 77 new tests (case subject 26, misplaced terminators 10, bracket
  quotes 29, conformance 12).
- Suite: 4,954 passed / 5,224 collected; ruff + mypy clean.

## 0.304.0 (2026-06-12) - Array element values as Words (reassessment Phase 1, 3/3 — REASSESSMENT PHASE 1 COMPLETE)
- Finding #4, confirmed and worse than stated: the root cause was a
  layer below the executor — the lexer's _collect_array_assignment()
  swallowed the whole raw value as one opaque token (and terminated at
  `(`), so `a[0]=$(cmd)` and `a[0]=$((expr))` were mis-lexed into
  garbage, `a[0]='lit $x'` expanded inside single quotes, and tilde/
  ANSI-C/escape forms were all broken in element values.
- Fix: the lexer now stops right after `=`/`+=` so element values
  tokenize identically to scalar assignment values; ArrayElement-
  Assignment carries value_word (both parsers populate it); and ONE
  shared bash assignment-value policy — new ExpansionManager.
  expand_assignment_value_word() (all expansions, no split, no glob,
  tilde after =/:, quote-aware) — serves scalar assignments (the
  executor's 75-line loop now delegates), array element assignments,
  explicit [i]=v initializer elements, and assoc-initializer keys.
  Manual quote-stripping deleted.
- Explicit-initializer and assoc fixes that fell out, all bash-pinned:
  `a=([0]=$x [1]=*)` (values unsplit, globs literal), `[i]+=` append,
  `a=("[0]=x")` quoted form stays a literal element, and
  `declare -A h; h=([k]=v ...)` — previously the KEYS went to index 0;
  the alternating pair form `h=(k1 v1 k2 v2)` now works too.
- 63-probe battery matches bash 5.2 (4 pre-existing out-of-scope
  diffs recorded: `declare a[0]=v` subscripted declare args;
  bash's error-then-run on `a[0]= cmd` prefix forms).
- Test portability: the affixed write-side procsub test now probes
  bash itself for OS support of the `/.>(...)`  shape and skips with
  a clear reason where the OS forbids it (reassessment found a macOS
  environment where bash also fails it).
- 61 new tests (test_array_element_word_values.py).
- Suite: 4,877 passed / 5,147 collected; ruff + mypy clean.

## 0.303.0 (2026-06-12) - Word-splitting semantics: declaration policy + loop items (reassessment Phase 1, 2/3)
- Finding #2 (High): assignment-shaped ordinary arguments now
  word-split like bash — `x="a b"; printf "<%s>" foo=$x` gives
  `<foo=a><b>` (was one field). Suppression is now an explicit
  DECLARATION_BUILTINS policy (alias, declare, typeset, export, local,
  readonly) with bash's *syntactic* recognition, all probe-pinned:
  the command word must be an unquoted literal — `command export`,
  `builtin export`, `\export`, `"export"`, and `$d` (d=declare) all
  SPLIT in bash 5.2 and now in psh; `eval export` doesn't (re-parse).
  Declaration args also skip pathname expansion (`declare foo=*`
  stays literal). True command-prefix assignments were already
  stripped pre-expansion (verified, unchanged).
- Probes CORRECTED the review's tilde claim: bash does tilde-expand
  assignment-shaped ordinary args (`echo P=~/x` → expanded).
  Implemented bash's rule (after first `=` and each `:`, valid NAME
  only, `+=` form too, quoted prefix suppresses) — also fixing
  pre-existing bugs in real assignments (`P=a:~:b` colon-tilde,
  `P=~"x"` over-expansion). Array initializers don't expand
  (bash-verified).
- Adjacent gap closed: `NAME+=value` arguments now work for
  declare/typeset/readonly/local (export already did) via shared
  core/assignment_utils.resolve_append_assignment() — textual,
  integer (-i), and scalar-append-to-array (was leaking an
  IndexedArray repr).
- Finding #3 (Medium): for/select item lists route through
  expand_word_to_fields(). ForLoop/SelectLoop carry item_words
  (the RD parser already built the Words and flattened them; the
  combinator now builds them too, fixing its composite-item bug);
  the 60-line legacy item-expansion engine is DELETED. Fixes
  IFS-aware splitting of command subs (`IFS=:; for i in $(printf
  a:b)` → two items), unquoted `${a[@]}` debris, tilde items,
  arithmetic-result splitting. 28-case probe table matches on both
  parsers.
- 92 new tests (56 assignment-splitting/tilde/append unit tests,
  36 loop-item integration tests incl. select-via-stdin and
  combinator parity). Conformance unchanged: POSIX 162/162.
- Known pre-existing edges recorded, not fixed: `name+=(...)` not
  tokenized as one word at the lexer; `declare -ai` arithmetic
  append to array element; no failglob.
- Suite: 4,816 passed / 5,086 collected; ruff + mypy clean.

## 0.302.0 (2026-06-11) - Per-invocation builtin redirection frames (reassessment Phase 1, 1/3)
- High-severity Finding #1 from docs/reviews/code_quality_subsystem_
  reassessment_2026-06-11.md: nested builtin redirections restored the
  wrong state. setup_builtin_redirections kept per-invocation state on
  the SHARED manager — _saved_fds_list was drained wholesale by ANY
  restore (so an inner builtin's restore re-pointed the outer eval's
  fd 3 mid-body: `exec 3>f; eval "echo one >&3; echo two >&3" 3>&1`
  sent `two` to the file; bash sends both to stdout), and
  _opened_streams was reassigned per setup. (Correction to the claim:
  the v0.292 _BuiltinStreamSnapshot was already per-call.)
- Fix: new BuiltinRedirectFrame owns the snapshot, fd-level dup
  backups, and opened streams; setup returns the frame and restore
  takes it by identity. Innermost-first order is enforced by paired
  try/finally construction; out-of-order restore is tolerated (that
  frame's own state still restores — no leak) and documented.
  Transactional rollback rolls back only the partial frame — an inner
  failed redirection no longer corrupts the outer frame. Procsub
  registrations deliberately stay with process_sub_scope() (moving
  them would re-break the v0.288 function-argument case).
- Bonus fix (pre-existing, found by probing): `>&m` for m>=3
  (`eval "echo b >&3" >/dev/null`) was fd-level only — invisible when
  sys.stdout is a swapped stream. Now handled in both universes via
  the exec-style shared-fd dup pattern.
- Nesting entry points mapped and tested: eval, source, EXIT/DEBUG
  traps mid-frame, command substitution (forks — unaffected, pinned),
  three-deep mixed-universe nesting, partial-frame rollback. 16 new
  bash-pinned tests (test_builtin_redirect_nesting.py).
- Known out-of-scope DIFF recorded: assignment-only commands apply
  redirects before expanding their command substitution
  (`x=$(echo inner >&2) 2>/dev/null`); bash expands first.
  Pre-existing, unrelated to frame state.
- Suite: 4,724 passed / 4,994 collected; ruff + mypy clean.

## 0.301.0 (2026-06-11) - Embedded process substitution (quality assessment Phase 1, 3/3 — PHASE 1 COMPLETE)
- Correctness Risk #2: `echo pre<(echo hi)post` printed literal text;
  bash prints `pre/dev/fd/63post`. The lexer already tokenized procsub
  mid-word and the parser already merged composites — but WordBuilder
  had no PROCESS_SUB branch, so the token fell into the literal
  fallback. The whole-word case only worked via a string-sniffing
  pre-pass in ExpansionManager.
- ProcessSubstitution is now an Expansion subclass carried as an
  ExpansionPart inside Words, exactly like $(...): WordBuilder builds
  it (covers both parsers' composites), _expand_word performs the
  substitution inline and splices the /dev/fd/N path (exempt from IFS
  splitting and globbing, bash-verified), and the old pre-pass +
  _has_process_substitution are DELETED — whole-word is now just the
  one-part case of the same mechanism. No remaining duality for
  command words (redirect-target procsub keeps its separate,
  untouched path).
- Fixed as natural fallout: procsub in assignments (`x=<(echo hi)` was
  "command not found"; bash assigns the path) and in array
  initializers (rd parser); multiple substitutions per word get
  distinct fds; quoted forms stay literal; case patterns, heredocs,
  and arithmetic keep procsub literal like bash.
- Cleanup integrates with the v0.288 scope ownership: new
  create_for_expansion() registers fd+pid in the same active lists;
  fd and zombie censuses pass with embedded forms, including when the
  consumer command fails.
- 28 new tests (+2 combinator pins updated). Pre-existing gaps
  reported honestly, all verified identical on main: combinator
  case-pattern/array-element handling; string-context sites
  (for-in iterables, case subjects, [[ -p ]]) still don't perform
  procsub; `~<(x)` tilde divergence.
- Suite: 4,708 passed / 4,978 collected; ruff + mypy clean.

## 0.300.0 (2026-06-11) - Loud expansion errors + signal lifecycle (quality assessment Phase 1, 2/3)
- Correctness Risk #5: expand_expansion no longer catches (ValueError,
  AttributeError, TypeError) and returns str(expansion) — internal
  bugs surfaced as literal output. Git archaeology showed the catch
  was never driven by a user-input need (born as bare except in the
  Word-AST migration); the one genuine user-facing ValueError
  (substring < 0) was already converted to ExpansionError locally by
  the v0.296 slice work. A sibling same-shape catch in variable.py
  (silently degrading operator bugs to plain-${var}) also removed.
  Deliberate catches reviewed and kept (subscript int()→'0' etc. are
  bash semantics). 20-case probe battery: behavior unchanged for all
  user-facing errors; full suite green with the catches gone.
- ProcessLauncher.launch: fork sigmask restore wrapped in try/finally
  — if os.fork() raises (EAGAIN), the parent no longer keeps
  TERM/INT/HUP/QUIT blocked forever. Child path unaffected (never
  returns; unblocks via apply_child_signal_policy). Disproof recorded:
  command_sub.py and process_sub.py fork WITHOUT mask manipulation,
  so they had nothing to leak.
- Interactive signal lifecycle (assessment claim CONFIRMED):
  restore_default_handlers() had zero callers — handlers were never
  restored on any REPL exit path (matters for embedded Shell use,
  e.g. the test suite). run_interactive_loop now restores in
  try/finally on normal EOF, exit-builtin SystemExit, and exceptions.
  Two adjacent latent bugs fixed: double setup_signal_handlers()
  overwrote the true pre-psh originals (now setdefault-guarded), and
  SignalNotifier.close() wasn't idempotent (explicit close + __del__
  could close an unrelated reused fd). Self-pipes recreated on loop
  re-entry.
- 16 new tests (9 error-propagation, 2 sigmask with monkeypatched
  EAGAIN fork, 5 serial lifecycle tests incl. loop re-entrancy) —
  all verified red against unfixed main.
- Suite: 4,680 passed / 4,950 collected; ruff + mypy clean.

## 0.299.0 (2026-06-11) - Array initializers through the Word expansion engine (quality assessment Phase 1, 1/3)
- Correctness Risk #1 from docs/reviews/code_quality_subsystem_
  assessment_2026-06-11.md: `a=(...)` initializer elements were
  expanded with expand_string_variables + Python .split() + raw
  glob.glob(), bypassing quote context, IFS, and noglob/nullglob/
  dotglob. Verified divergences fixed: `a=("*.txt")` no longer globs a
  quoted pattern; `IFS=:; a=($x)` splits on IFS; `set -f` is honored;
  no-match globs stay literal (or vanish under nullglob);
  `b=("${a[@]}")` preserves elements; tilde and composite
  `pre"$x"post` elements expand correctly.
- The fix was architecturally cheap because the RD parser ALREADY
  built Word AST nodes for every element and discarded them:
  ArrayInitialization now carries `words`, both parsers populate it,
  and the executor expands each element via the new public
  ExpansionManager.expand_word_to_fields() — the same pipeline as
  command arguments, with one bash-verified context difference
  (initializers word-split `k=$x`; command args don't).
- Scalar contexts unchanged and probe-pinned: `a[0]=*` stays literal;
  explicit `[k]=v` initializer elements and `declare -A h=([k]=v)`
  keep their paths.
- Bonus fixes: newlines inside `a=(1
  2)` now parse (bash allows; was a parse error), and `$((...))`
  elements now parse in the combinator parser.
- Probe battery: 53/53 match bash 5.2 on the RD parser (was 34/53);
  combinator 49/53 (remaining 4 are its pre-existing composite-element
  limitation). 56 new tests (51 integration + 5 conformance).
- Suite: 4,664 passed / 4,934 collected; ruff + mypy clean.

## 0.298.0 (2026-06-11) - Doc fix-in-place pass (reappraisal #2 Tier C, 2/2 — REAPPRAISAL #2 COMPLETE)
- executor/CLAUDE.md: phantom builtin_base import fixed (real: .base +
  .registry); pipefail corrected to rightmost-non-zero; process-group
  description fixed (the PARENT setpgid's members while children block
  on the sync pipe); job_control.py added to Key Files; v0.288/v0.289
  drift incorporated (process_sub_scope wiring, report_exec_failure).
- lexer/CLAUDE.md: phantom _tokenize_next replaced with the real
  tokenize() loop; recognizer registration corrected to
  _setup_recognizers (recognizers/__init__.py only re-exports, and
  omits ProcessSubstitutionRecognizer); priorities fixed (no keyword
  recognizer exists — process_sub 160 / operator 150 / literal 70 /
  comment 60 / whitespace 30, all @property); RecognizerRegistry
  snippet fixed (register() takes no priority; method is recognize);
  constants.py row corrected; heredoc_collector.py added.
- visitor/CLAUDE.md (the one CLAUDE.md never refreshed): nonexistent
  test file replaced with the real two; traversal.py and
  analysis_helpers.py added with a visit_children example; examples
  fixed from alias-only visit_CommandList to visit_StatementList
  (dispatch uses the real class name, so the old example never fired);
  bonus defect fixed (IfConditional has no .body field).
- ARCHITECTURE.md/.llm: removed-machinery purge — §3.3/§3.6/§3.7/§3.10
  rewritten from parse_with_error_collection / RECOVER / PERMISSIVE /
  permissive() / ErrorCollector / panic-mode to the real ParserConfig
  (STRICT_POSIX/BASH_COMPAT, STRICT/COLLECT) and ParserContext
  error collection; §3.9 visualization snippet fixed to real names;
  test count 4,550+ → 4,800+ (collected: 4,878).
- M7 documented: $(case x in x) ...) is a parse error in both parsers
  (paren counting, not recursive lexing; bash accepts). Known
  Limitation #2 in ARCHITECTURE.md, code comment at the
  find_balanced_parentheses call site, user-guide ch. 6 note with the
  verified workaround $(case x in (x) ...) — leading paren form works.
- Gates: claims meta-test 39 passed; quick suite green; ruff clean.

## 0.297.0 (2026-06-11) - Docs archive sweep (reappraisal #2 Tier C, 1/2)
- 47 stale documentation files moved to docs/archive/ via git mv
  (content untouched), per the 2026-06-11 reappraisal §6 plan with
  per-file re-verification: 3 root docs (StateMachineLexer-era lexer
  docs, superseded combinator guide), 31 of 33 docs/architecture/
  files (completed parser-combinator plans/phase summaries, docs for
  removed ParserFactory/validation.py; the status doc was reclassified
  stale on verification — it documents a package layout that no longer
  exists), 4 of 5 docs/posix/ (v0.57-era analyses claiming trap/shift/
  exec are missing), 9 point-in-time quality reviews from docs/guides/.
- Kept after verification: lexer_architecture.md and
  bash_vs_psh_lexer_comparison.md (all module references check out),
  posix_spec_reference.md (timeless), combinator_parser_remaining_
  failures.md (current since its v0.276 rewrite).
- 12 surviving guides got dated staleness banners (only files with
  grep-verified stale content: pre-v0.285 module paths or removed
  RECOVER/PERMISSIVE parser modes); 17 guides verified clean, no
  banner. subsystem_internals.md paths fixed (psh/expansion/
  arithmetic.py, psh/lexer/token_types.py). 5 dangling links fixed.
- docs/architecture/ and docs/posix/ now contain only verified-current
  material. No production or test changes; suite quick-gate green.

## 0.296.0 (2026-06-11) - Slice/arithmetic unification + prune remnants (reappraisal #2 Tier B, 6/6 — TIER B COMPLETE)
- M10: `${var:offset:length}` slicing unified on one canonical engine
  in operators.py (_parse_slice_operand/_slice_elements/
  _slice_scalar_subscript) — the review found 3 copies; verification
  found a 4th (arrays.py:_expand_array_slice). The ~60-case probe
  battery exposed 8 real bash divergences, all fixed: empty-present
  length (`${a[@]:1:}` → empty), sparse arrays slice by index not
  position, resolved-negative starts (`${@: -99}` → empty, was
  clamped to everything), negative array length aborts like bash,
  out-of-range + negative length is empty without error, invalid
  arithmetic in operands aborts the command (exit 1), scalar-with-[@]
  subscript string semantics. 50 new tests pin the battery.
- Arithmetic pre-expansion scanners DELETED (~110 lines): probing
  showed evaluate_arithmetic already expands $-constructs via the
  v0.279 shared scanner, so the manager's two bespoke scanners were a
  redundant second pass — and the source of real divergences, all
  fixed by deletion: `$12` now means `${1}2` like bash (was `${12}`),
  empty values no longer 0-padded before evaluation, and variables
  holding `$(...)` text are no longer rescanned and EXECUTED by
  arithmetic (bash: syntax error). 24 new tests; 25/25 probes match.
- v0.286 parser prune finished: ErrorHandlingMode.RECOVER,
  enable_error_recovery, error_recovery_mode and the recovery method
  family removed (the review's `can_recover` is actually
  should_attempt_recovery, and base_context had one more dead
  delegate). ParserConfig's "only fields actually read" docstring is
  true again. Two test files updated; parser CLAUDE.md snippets fixed.
- Lexer smalls: DOUBLE_QUOTE_ESCAPES (dead-by-shadowing — its only
  lookup sat in an unreachable elif) deleted with its rationale
  comment moved to the live branch; both "Phase 3/4" plan codenames
  replaced with self-contained prose.
- interactive: line_editor EIO path called nonexistent
  terminal.restore() inside an except clause that also missed
  termios.error (not an OSError subclass) — fixed both; new interface
  guard test asserts every self.terminal.<attr> reference exists.
- Suite: 4,608 passed / 4,878 collected; ruff + mypy clean.

## 0.295.0 (2026-06-11) - PTY-tier repair + test debris (reappraisal #2 Tier B, 5/6)
- M8: the 6 reproducible failures in the opt-in PTY tier were NOT
  product bugs and NOT mere assertion fragility — the pty framework's
  initial-prompt sync was off by one, so every run_command returned the
  PREVIOUS command's output window (several "passing" tests passed
  spuriously on the echoed command). Fixed in pty_test_framework.py:
  sentinel prompt (PS1='PSH$ ', the proven test_pty_smoke convention),
  arithmetic-sentinel initial sync, stale-output drain per command,
  PS2 continuation handling, strip_ansi() + CR-overwrite normalization.
  No test logic changed; one stale Ctrl-C xfail removed (now passes
  deterministically). Opt-in tier: 86 passed, 0 failed × 3 runs.
- Nested tests/system/interactive/pytest.ini deleted (it hijacked
  pytest rootdir, breaking direct invocation with --run-interactive;
  its skip-comment referenced a removed README and an unused marker).
  Both invocation styles verified working.
- Debris: tracked broken-symlink conformance results git-rm'd and the
  results dir gitignored (runner recreates on demand — verified,
  162/162 POSIX); five legacy non-test files removed from
  tests/system/interactive/ (references checked; dir README updated,
  stale "can't handle escapes" known-issue dropped); empty
  tests/integration/lexer/ and untracked husk dirs removed;
  test_codex_review_findings.py docstring corrected (bugs fixed,
  no xfails remain).
- CI workflow renamed test_migration.yml → tests.yml (historical
  misnomer; `name: Tests CI` already accurate).
- Suite: 4,533 passed / 4,803 collected; PTY tier green ×3;
  ruff + mypy clean.

## 0.294.0 (2026-06-11) - Error/notification channel unification (reappraisal #2 Tier B, 4/6)
- Job-state notifications now go to stderr like bash (verified by
  pty.fork probe with the shell's own fds redirected): Done, Stopped,
  and `set -b` notices via new JobManager._notification_stream();
  the launch notice (already stderr since v0.276) uses the same helper.
  The `jobs` builtin's listing stays on stdout (command output).
- Arithmetic errors (`((1/0))`, C-style for init/cond/update) now write
  to state.stderr instead of bare sys.stderr (control_flow.py ×3,
  core.py), making them forked-child-aware like command errors.
- Builtin stragglers converted to base-class helpers preserving exact
  text/rc: function_support (declare/readonly listings, function
  printing — print+hasattr dance removed), read (error() for option
  errors), environment ("Valid options:"), help (usage), debug_control
  (14 sites to write_line). New Builtin.write_error_line() for
  unprefixed stderr diagnostics. aliases/command verified already clean.
- process_launcher: shadowing `import sys` in launch() removed;
  dangling 'SignalManager' annotation got its TYPE_CHECKING import.
- 18 new tests incl. a pty end-to-end pin that notices land on stderr
  with stdout clean, and channel pins for arithmetic/read/help errors.
- Suite: 4,533 passed / 4,803 collected; ruff + mypy clean.

## 0.293.0 (2026-06-11) - Keyword case-sensitivity (reappraisal #2 Tier B, 3/6)
- M6: shell reserved words are now matched case-sensitively like bash.
  `IF true; then echo y; fi` executed in psh (bash: syntax error);
  `FOR`/`WHILE`/`CASE`/`UNTIL`/`SELECT` likewise (uppercase SELECT even
  hung on stdin). Now: uppercase keywords are ordinary words — lone `IF`
  → command not found rc 127, `IF=3; echo $IF` → 3, mid-construct
  uppercase (`THEN`, `ELIF`, `IN`) → syntax error, all matching bash.
- Folding removed at every keyword site: keyword_normalizer.py (KEYWORDS
  lookup + _next_command_position), keyword_defs.py matches_keyword_type
  / matches_keyword / KeywordGuard (this one fix covers the entire
  combinator parser — all its keyword checks funnel through
  matches_keyword), token_types.py normalized_value (now a no-op).
  The rd parser needed no change (it matches token types, which the
  normalizer now only assigns to exact-lowercase words). Non-keyword
  case handling (unicode opt-in identifiers, hex, ${var,,}) untouched.
- Zero existing tests pinned the old behavior (swept). 10 new lexer
  unit tests + 6 conformance tests (~20 commands) in
  tests/conformance/bash/test_keyword_case_conformance.py.
- Suite: 4,515 passed / 4,785 collected; ruff + mypy clean.

## 0.292.0 (2026-06-11) - io_redirect: exec single-open, noclobber, dual-universe docs (reappraisal #2 Tier B, 2/6)
- Triple-open in apply_permanent_redirections fixed: `exec &>file` (and
  `>`, `>>`, `>|`, `2>file`) opened up to three independent file objects
  with separate offsets, so builtin and external output overwrote each
  other (`exec >f; echo b1; /bin/echo e1; echo b2` lost b1). All output
  branches now do a single fd-level open + dup2, then rebind sys.stdout/
  stderr via os.fdopen(os.dup(fd), buffering=1) — one shared open file
  description, line-buffered for bash-like interleaving. 17 probes match.
- noclobber now blocks `>` only for existing regular files (and dangling
  symlinks, matching bash's O_EXCL EEXIST); devices and FIFOs are
  exempt — `set -o noclobber; echo x 2>/dev/null` works again.
  Rule verified by probe across all four enforcement paths.
- The builtin-redirection "dual universe" (Python stream swap for fds
  1/2, real dup2 for fd>=3) was deliberately KEPT — unification is not
  viable because builtin output may target non-fd-backed streams
  (StringIO under test capture) — but the 120-line function is now a
  ~25-line dispatcher over five named, docstringed helpers with a
  module-level design explanation; first-touch-wins backups extracted
  into an explicit _BuiltinStreamSnapshot. Rollback semantics unchanged.
- io_redirect/CLAUDE.md refreshed: expansion-in-targets table corrected,
  real debug output, pitfall #7 rewritten for the v0.288 procsub scope
  mechanism, new two-universes and exec single-open sections.
- 31 new tests (15 subprocess exec tests, 10 noclobber targets,
  6 predicate units).
- Suite: 4,499 passed / 4,769 collected; ruff + mypy clean.

## 0.291.0 (2026-06-11) - alias/unalias rewrite + printf \e (reappraisal #2 Tier B, 1/6)
- M3: aliases.py rewritten to the builtins conventions (the one file the
  v0.284 sweep never reached). `alias -p` supported; invalid options now
  rc 2 with a usage line via parse_flags; output uses bash's `'\''`
  quoting for embedded single quotes; `unalias` with no args rc 2;
  `alias -- x=v` works; raw print + hasattr dance replaced with
  write_line()/error(). 37-case probe battery matches bash 5.2.
- The cross-argument quote-rejoin scanner was live but WRONG in every
  reachable case, not dead as the review guessed: it stripped quotes
  bash keeps literal (`alias x="'echo hi'"`) and glued separate operands
  (`alias x=\'foo bar\'` — bash defines `x`=`'foo` and errors on
  `bar'`). Deleted; operands are now independent, matching bash.
  Bash source quirks replicated: `-p` with empty table returns 0 and
  skips operands; `unalias -a` ignores operands; `=foo` is a lookup.
- printf now interprets `\e`/`\E` (escape) in its format string — added
  to printf's own escape dialect in io.py, not the shared echo dialect
  (which already had it; `$'\e'`, `echo -e '\e'`, `printf '%b'` were
  already correct).
- 33 new tests (29 alias/unalias conformance, 4 printf escapes).
- Suite: 4,469 passed / 4,739 collected; ruff + mypy clean.

## 0.290.0 (2026-06-11) - Test-runner hole + user-guide truth sweep (reappraisal #2 Tier A, 3/3 — TIER A COMPLETE)
- H2: run_tests.py no longer silently skips 45 tests. The whole-file
  ignores of test_function_advanced.py and test_variable_assignment.py
  (obsolete since the v0.195.0 subshell fd fix) are removed and the
  2-test Phase 3 deleted; both files verified xdist-safe (4× under
  -n 4, no serial markers needed). CI (--quick) now runs them too.
- Two stale xfails fixed in test_function_advanced.py:
  test_function_with_background_job xpassed (marker deleted);
  test_function_with_here_document's feature works — the test was
  rewritten to file redirection per the project's capture rules.
- H3: user-guide truth sweep — every limitation note re-probed against
  bash and current psh (~30 probes). 17 false "not supported" claims
  corrected (`!` negation, `|&`, PIPESTATUS, `exec 3<>`, fd swaps, `>|`,
  five bitwise assignment ops, BASH_REMATCH ×3, `[[ ! ]]`,
  read -n/-t/-s, `${!prefix*}`, `${!varname}`, `${@:off:len}`,
  `${array[@]#pat}`, $'\NNN' octal, $"...").
  10 still-true limitations kept and unversioned (csh `>& file`,
  `<< \EOF`, `~+`/`~-`, `$(< file)`, multi-line declare -A init,
  bind, wait -n, extglob `@()`, printf "%d" "'A", read -u).
  All "PSH v0.187.1" pins removed (grep-clean);
  docs/user_guide/README.md now version-agnostic at ~98%.
- 23 new conformance tests (tests/conformance/bash/
  test_user_guide_notes_conformance.py) pin the corrected claims that
  had zero prior conformance coverage; claims meta-test green.
- Suite: 4,436 passed / 4,706 collected (+68: 45 reclaimed + 23 new);
  ruff + mypy clean.
- Side findings recorded for follow-up: noclobber wrongly blocks
  redirects to existing device files (`2>/dev/null` under
  `set -o noclobber`; bash exempts non-regular files); psh printf
  doesn't interpret `\e` (bash does).

## 0.289.0 (2026-06-11) - Behavior-bug batch (reappraisal #2 Tier A, 2/3)
- M1: associative-array keys containing `,` or `^` now expand:
  `declare -A a; a[x,y]=hi; echo "${a[x,y]}"` → `hi` (was empty). Two-part
  root cause: variable.py excluded any `${...}` containing case-mod chars
  from the subscript path, AND parse_expansion's case-mod scan split at
  `,`/`^` inside `[...]`. Fixed with a structural `_is_plain_subscript()`
  check (balanced-bracket, handles nested `arr[arr[0]+1]`) and a bracket
  guard in the operator scan. `${a[x,y]^^}` and all case-mod forms
  (`${v^^}`, `${v^^[a-m]}`, `${arr[@]^^}`) verified against bash.
  18 new tests (test_assoc_array_special_keys.py).
- M2: `command -v`/`-V` now finds aliases, keywords, functions, and
  builtins in bash's lookup order with bash output formats (`-v`: alias
  definition line / name / path; `-V`: "is a function" + body via the
  shared ShellFormatter, "is aliased to", "is a shell builtin/keyword")
  and bash rc semantics (multi-name rc 0 if any found; `-v` silent rc 1
  on miss; bare `command` rc 0). The hardcoded `bash: type:` error prefix
  is gone; raw prints converted to write_line()/error() per convention.
  PATH probing shared with type via TypeBuiltin._find_in_path.
  19 new tests (test_command_builtin.py).
- M4: deleted four dead `set -o` options (validate-context,
  validate-semantics, analyze-semantics, enhanced-error-recovery) from
  core/state.py and `set` help — zero consumers (orphaned by the v0.286
  parser pruning); they now error rc 2 like any unknown option. 4 tests.
- M5: command-not-found inside a pipeline now prints
  `psh: name: command not found` and exits 127 (non-executable → 126)
  instead of a raw Python OSError with the PATH-probe path. Extracted
  module-level report_exec_failure() shared by the inline-exec and fork
  paths; pipeline diagnostics byte-identical to single-command ones.
  5 subprocess tests (test_pipeline_exec_errors.py).
- Suite: 4,368 passed / 4,683 collected; ruff + mypy clean.

## 0.288.0 (2026-06-11) - Process-substitution fd/zombie reaping (reappraisal #2 Tier A, 1/3)
- Fixed (high severity, found by the second ground-up reappraisal): process
  substitutions used by external commands leaked parent-side fds and left
  zombie children for the life of the session — `IOManager.
  cleanup_process_substitutions` had ZERO callers and `shell._process_sub_fds/
  _process_sub_pids` were written but never read. Three `cat <(echo x)`
  commands left three `<defunct>` children; bash leaves none.
- Design: scoped LIFO ownership on ProcessSubstitutionHandler. `scope()`
  (via `io_manager.process_sub_scope()`) closes only the fds registered
  inside the scope on exit and moves its pids to a pending list polled with
  `os.waitpid(pid, WNOHANG)` — specific pids only, never -1, so JobManager
  statuses can't be stolen. Still-running children (`echo >(sleep 3)`) are
  parked and reaped opportunistically by later commands, matching bash.
  The dead method and dead shell attributes were deleted, not wired — the
  blanket-cleanup semantics they implied were themselves wrong (see below).
- Two additional latent bugs fixed by the same design (both bash-verified):
  `echo >(sleep 3)` blocked ~3s (blocking waitpid in the builtin-restore
  path; bash returns immediately), and `f() { cat "$1"; }; f <(echo a)`
  failed with "Bad file descriptor" (any builtin's restore blanket-closed
  ALL active procsub fds, including the enclosing function call's).
- Redirect-target procsubs (`< <(cmd)`) now close the parent fd eagerly
  after dup2, with a guard for the fd-number-collision case
  (`exec 3< <(cmd)` where the pipe end happens to be fd 3).
- Wire points cover all consumers: CommandExecutor.execute wraps every
  simple command; IOManager.with_redirections wraps compound/function
  redirects; `[[ ]]` redirects now route through with_redirections
  (shell.execute_enhanced_test_statement simplified).
- 13 new tests in tests/integration/redirection/test_process_sub_cleanup.py
  (zombie census, fd-slot census, non-blocking timing, opportunistic reap,
  and output-correctness pins incl. function args, `exec 3< <(...)`,
  `tee >(...)`); the four defect tests fail on unfixed main.
- Suite: 4,323 passed / 4,638 collected; ruff + mypy clean.
- Also adds docs/reviews/ground_up_reappraisal_2026-06-11.md — the second
  ground-up reappraisal memo (six-agent review; scorecard, findings H1-H3
  and M1-M10, three-tier follow-up program).

## 0.287.0 (2026-06-11) - Mypy adoption + interactive unit tests (reappraisal Tier C, 3/3 — REAPPRAISAL PROGRAM COMPLETE)
- Type checking is now enforced: `[tool.mypy]` in pyproject.toml (3.12,
  non-strict, files-driven scope) covering psh/core/ (8 modules),
  ast_nodes.py, version.py, and the pure showcases
  expansion/pattern.py / utils/escapes.py / interactive/line_layout.py —
  14 files, zero issues. The 5 errors mypy found were FIXED with real
  annotations (an implicit-Optional in trap_manager; a None-sentinel loop
  in scope.py refactored to a typed Optional branch) — no `# type: ignore`
  anywhere. CI's lint job runs mypy; CLAUDE.md documents the
  grow-the-scope convention.
- The interactive layer finally has fast in-process unit tests: 76 new
  tests in tests/unit/interactive/ (xdist-safe, 0.07s total, no PTY):
  - line-editor buffer ops (insert/delete boundaries, kill/yank
    round-trips, transpose, word motion, history navigation preserving
    the in-progress line, undo/redo — including a documented dedupe
    quirk in the redo stack)
  - the v0.283 escape reader fed synthetic byte streams: every CSI/SS3
    variant, unknown-sequence full consumption (nothing leaks as typed
    text), EOF mid-sequence, vi bare-ESC vs sequence via the mockable
    `_input_pending` probe
  - completion candidates against tmp_path fixtures (partial/unique/
    dir/hidden/subdir), find_word_start quote/operator cases, tab-apply
    paths with space escaping. One test documents that command-position
    completion does not exist (CompletionEngine is purely path-based) —
    an honest feature gap, not a regression.
- tests/unit/interactive/ exempted from the PTY skip-by-default marker
  (these tests are terminal-free).
- Full suite green: 4,310 passed / 4,625 collected (+76).
- This closes the ground-up reappraisal program
  (docs/reviews/ground_up_reappraisal_2026-06-10.md): Tier A
  v0.275–v0.278, Tier B v0.279–v0.284, Tier C v0.285–v0.287 —
  13 releases across every recommendation, with each inaccurate review
  claim verified and documented rather than blindly executed.

## 0.286.0 (2026-06-11) - Parser pruning + subsystem CLAUDE.md refresh (reappraisal Tier C, 2/3)
- Dead rd-parser error-recovery machinery deleted after a reachability
  audit: `parse_with_error_collection` / `MultiErrorParseResult` /
  `_try_statement_recovery` and their private support had no production
  caller (--validate runs a normal parse; the parser-config builtin's
  option never reached ParserConfig). Their 14-test file went with them.
  The review's claim that ErrorContext.suggestions was dead proved WRONG —
  it's populated by ParserContext and user-visible in error output; kept.
  Also deleted: `error_code`, `related_errors`, `add_suggestion`,
  `show_error_suggestions`, ParsingMode.EDUCATIONAL/PERMISSIVE,
  `permissive()`. ParserContext-level error collection (the live library
  surface) remains.
- Vestigial AST quote-type fields audited (the removed arg_types pattern
  by another name): all five field groups traced to real consumers in
  expansion/execution semantics — converting them is Word-AST migration
  work, not pruning. Each is now marked legacy-pending-migration at the
  definition; `BinaryTestExpression.left_quote_type` found to have ZERO
  consumers and flagged as a removal candidate. Stale "dual
  Statement/Command types" comment fixed.
- Parser error messages standardized on lowercase "syntax error" (bash's
  style; one golden-case pin updated after bash verification);
  `_raise_unclosed_expansion_error` renamed `_raise_syntax_error` (it was
  used for generic syntax errors); the 25-line backslash-parity scanner
  in parse_pipeline_component extracted into a documented helper;
  pure-delegation `parse_command_list_until_top_level` inlined away.
- Five subsystem CLAUDE.mds verified claim-by-claim against current code
  and refreshed (expansion, parser, core, builtins, interactive): ~32
  corrections (wrong APIs, phantom components, stale tables/samples) and
  ~13 new short sections for v0.266–v0.285 machinery (expansion mixins +
  pattern.py, ${!name}, PATSUB_MATCH, namerefs + tombstones, PshError
  family, parse_flags + error-channel conventions, the line editor and
  its centralized escape parser, history single-writer, entry-point-only
  signal setup).
- Net −108 lines of dead parser machinery (+docs). Full suite green:
  4,234 passed / 4,549 collected (−15: the deleted dead-surface tests).

## 0.285.0 (2026-06-11) - Top-level module relocation + scope rename (reappraisal Tier C, 1/3)
- The 19 orphan top-level modules (15% of the tree) moved into their
  packages via `git mv`, so the layout finally matches the documented
  architecture. Top level is now exactly: shell.py, __main__.py,
  ast_nodes.py, version.py (+ __init__.py).
  - lexer/: token_types.py, token_stream.py, token_transformer.py
  - expansion/: arithmetic.py, brace_expansion.py, aliases.py
  - executor/: job_control.py
  - core/: functions.py
  - scripting/: input_sources.py, input_preprocessing.py
  - interactive/: line_editor.py, line_editor_helpers.py, line_layout.py,
    tab_completion.py, prompt.py, keybindings.py, multiline_handler.py,
    history_expansion.py
- No compatibility shims (pre-1.0 educational software; this entry is the
  record). 87 psh/ files + 31 test files had imports rewritten by a
  resolution-aware script (relative imports resolved to absolute targets
  first, so the parser's own local functions.py/arithmetic.py were
  correctly untouched). No string/importlib references existed.
- One import cycle surfaced and was fixed at the root: executor modules
  imported FunctionReturn from psh.builtins (a re-export), creating
  builtins → executor → builtins at startup once job_control moved.
  Executor now imports it from its true home, core.exceptions, severing
  the executor → builtins import-time edge entirely.
- `core/scope_enhanced.py` renamed to `core/scope.py` and
  `EnhancedScopeManager` to `ScopeManager` — there was never a
  non-enhanced version to be enhanced relative to. Full reference update,
  no alias kept (only 4 files referenced it).
- ~26 doc path references updated (ARCHITECTURE.md/.llm component tree,
  seven subsystem CLAUDE.mds).
- Pure relocation: zero behavior change; full suite green at exact
  baseline (4,249 passed / 4,564 collected), PTY smoke 34/34.

## 0.284.0 (2026-06-11) - Builtins consistency (reappraisal Tier B, 6/6 — Tier B complete)
- Option parsing converged selectively (not blindly): `type` converted to
  the shared parse_flags helper, fixing 3 bash-pinned divergences
  (clustered `type -af` accepted; `type -` is an operand, rc 1; invalid
  option message + rc 2 + bare `type` rc 0). `jobs` converted alongside
  the `jobs -l` work. Deliberately NOT converted, each verified: declare
  (needs `+x` removal flags — its custom parser instead table-driven,
  98 → 60 lines, identical semantics), getopts (the "122-line parser" IS
  the POSIX getopts semantics, not self-option parsing — review claim
  inaccurate), cd (parses no options today; conversion would invent
  errors), test/[ (positional expression syntax), read/echo (pinned).
- Error channels unified: 33 raw `print(file=sys.stderr)` sites converted
  to the forked-child-aware `self.error()` / `self.write_line()` —
  type (the 12× hasattr-stdout dance), kill (14), fg/bg/wait, source,
  return, trap, set, debug_control. Three messages improved to bash's
  shape along the way (`.`/source filename-required, kill usage, trap
  usage).
- unset's inline subscript parsing and "looks arithmetic" heuristic
  replaced by the canonical `_eval_array_index` path (v0.279.0). An
  11-probe bash battery now matches exactly, fixing 4 divergences:
  `unset 'a[-1]'` removes the last element; out-of-range negative reports
  "bad array subscript" rc 1; scalar `x[0]` unsets x; missing-array
  unset is silent rc 0.
- `jobs -l` implemented (the last honest TODO in builtins), bash-pinned:
  `[1]+ 12345 Running   sleep 10 &`; pipeline jobs list extra PIDs on
  continuation lines; `-p` wins over `-l` as in bash.
- env builtin: review's "doing executor work" claim was stale — the fd
  juggling was already in named private methods; docstrings expanded to
  explain WHY env must dup2 process-level fds (forked grandchildren
  inherit fds, not Python stream objects). `set` help no longer lists
  the nonexistent enhanced-parser options.
- 18 new bash-pinned tests (type ×6, unset ×10, jobs -l ×2). Full suite
  green: 4,249 passed / 4,564 collected.

## 0.283.0 (2026-06-11) - Interactive/line-editor cleanup (reappraisal Tier B, 5/6)
- Vi-mode arrow keys fixed: CSI parsing lived only in the emacs branch, so
  in vi insert mode an Up-arrow became ESC→normal-mode + stray 'A' →
  append-at-end, corrupting the edit state. Escape handling is now
  centralized ABOVE the mode split: `_read_escape_sequence` is the single
  input-side ANSI parser, yielding symbolic keys ('up'...'delete') that one
  shared table maps identically in emacs and both vi modes (bare ESC vs
  sequence distinguished via a 50ms pending probe — terminals send
  sequences in one burst). Also fixed a pre-existing gap the work exposed:
  `set -o vi` never reached the live LineEditor (mode was frozen at REPL
  setup); the editor now syncs from state.edit_mode per read. 5 vi-mode
  PTY tests added.
- History single-writer: both LineEditor.read_line and source_processor
  recorded history (multiline commands landed as physical lines AND the
  joined form). source_processor is now the sole writer (recording before
  parse so syntax errors stay recallable, as bash does); multiline
  commands store as ONE joined entry (`for i in 1; do echo $i; done`)
  while quoted newlines stay verbatim — both PTY-pinned against real
  bash. The vestigial `import readline` history mirror is gone. 3 history
  PTY tests added.
- Dead DSR machinery deleted: `_prompt_draw_row` was written but never
  read (redraw uses pure line_layout math), and `_query_cursor_row` +
  `_drain_stale_cpr` existed only to feed it — psh no longer writes
  ESC[6n at all, removing a whole class of PTY races.
- `__main__.main` (~279 lines) decomposed: data-driven `parse_args()` +
  `print_help()` (help output diff-identical); main() is ~115 lines of
  orchestration. Flag battery verified (-c, --norc, piped stdin, -i,
  --parser=X, --validate, --debug-ast=compact, --version, error exits).
- `TerminalManager` moved from tab_completion.py to its natural home,
  psh/interactive/terminal.py (re-exported for compatibility).
  read_builtin's raw-mode block deliberately NOT unified: it operates on
  an arbitrary fd (redirected stdin, read -u) with an explicit echo flag —
  different semantics, now documented.
- Minor: CompletionEngine.find_word_start public (alias kept);
  line_layout imports hoisted; stale base.py comment fixed.
- line_editor.py 1089 → 1061 lines; __main__.py 291 → 258. Full suite
  green: 4,231 passed / 4,546 collected (8 new PTY tests).

## 0.282.0 (2026-06-11) - Executor cleanup + signal-loss race fix (reappraisal Tier B, 4/6)
- THE RACE, root-caused — and it wasn't where the reappraisal guessed.
  `sleep 5 & kill %1 && wait %1` intermittently reported rc=0 instead of
  143 under load (11/320 in a parallel stress harness). Suspected
  wait_for_job bookkeeping was innocent: failing runs took the full 5s —
  the SIGTERM was being LOST. A signal delivered in the child's fork→exec
  window was consumed by the inherited Python-level trap handler and
  discarded across exec(), so sleep never received it. Fix:
  ProcessLauncher blocks SIGTERM/SIGINT/SIGHUP/SIGQUIT across fork
  (pthread_sigmask; parent restores immediately); the child unblocks only
  after apply_child_signal_policy resets handlers to SIG_DFL, so a
  window signal stays kernel-pending and kills the child with the right
  status; SIGTERM/SIGHUP added to reset_child_signals (children must not
  inherit trap handlers — bash semantics). Stress: 960/960 clean after
  (0/320 before-fix failures remained); 30× bash-pins rc=143 and rc=5.
  wait_for_job additionally hardened (ECHILD distinguished and orphaned
  processes marked completed so the stored-status fallback always runs;
  EINTR retried). 3 regression tests added
  (tests/integration/job_control/test_kill_wait_race.py, auto-serial).
- `JobManager.launch_background(pgid, command, processes)` extracted: the
  create-job/add-process/register/notice block was duplicated across 6
  sites (strategies.py ×3, subshell.py ×2, pipeline.py). The notice is
  unified on bash's format — PTY-verified that bash prints the LAST
  process's pid (== $!), not the pipeline leader's pgid, which
  pipeline.py had been printing.
- CommandExecutor.execute (191 lines) split: `_strip_backslash_bypass()`
  and `_handle_execution_error()` extracted; execute() reads as the
  orchestration narrative.
- Near-duplicate code factored: the ~40-line builtin exception policy
  shared by Special/regular builtin strategies → `execute_builtin_guarded()`;
  the two WIFEXITED blocks in wait_for_job → `exit_status_from_wait_status()`
  (builtins' `_extract_exit_status` delegates).
- Dead code removed: `process_metrics` hooks (object never created),
  `_execute_pipeline` indirection; function.py "Phase 7" docstring fixed.
- All 20 opaque plan-codename comments (H3/H4/H5/C1...) replaced with
  self-contained explanations; `job.state.name == 'DONE'` string compare
  → JobState enum; error output unified on state.stderr where equivalent.
- Full suite green: 4,223 passed / 4,538 collected (3 new race tests).

## 0.281.0 (2026-06-11) - Lexer cleanup (reappraisal Tier B, 3/6)
- literal.py's quadratic string-archaeology fixed — but not the way the
  review prescribed: instrumentation proved `_is_inside_array_assignment`
  and the lexer-level array-assignment map are NOT equivalent (the helper
  fires for glob char-classes like `*[[:upper:]]*`, which the map can't
  represent). The per-character full re-scan is replaced by an incremental
  `_ArrayAssignmentTracker` running the identical quote-aware bracket
  automaton — O(n) by construction, zero behavior change. A 128k-char word
  lexes in 0.079s vs 0.202s (now linear). The forward-lookahead helpers
  (`_is_potential_array_assignment_start`, `_collect_array_assignment`)
  are genuinely needed and kept; the rare-trigger value scans kept.
- Dead config flags deleted: 12 never-set `enable_*` flags removed from
  LexerConfig along with their 8-branch feature-disable ladders in
  literal.py (including 13 unreachable lines) and operator.py
  (`_is_operator_enabled` deleted whole). `enable_extglob`, `posix_mode`,
  and `case_sensitive` kept (really used). ProcessSubstitutionRecognizer
  registered unconditionally.
- Duplication removed: comment-start logic unified on one module-level
  `is_comment_start()` (the wider set in comment.py was provably
  unreachable — LiteralRecognizer outprioritizes it; bash-verified);
  backtick parsing deduplicated (quote_parser delegates to
  ExpansionParser; the contract difference on unclosed backticks is
  unobservable since an enclosing unclosed quote errors first);
  `_parse_fd_duplication` 93 → 56 lines via a shared tail helper.
- Dead code deleted (zero production callers, verified):
  `parse_simple_quoted_string`, `extract_quoted_content`,
  `get_operator_type`, `_is_identifier`, `pure_helpers.is_comment_start`,
  `WORD_TERMINATORS`/`WORD_TERMINATORS_IN_BRACKETS` constants,
  `create_expansion_parser`, registry test-only surface (`unregister`,
  `get_stats`, `default_registry`, `setup_default_recognizers`), orphaned
  `QuoteParsingContext` and `_create_error_part`. 15 tests that pinned
  only the deleted surface were removed; registry tests rewritten against
  the production-built `ModularLexer.registry`.
- Fragilities documented in place (PARAM_EXPANSION substring
  classification, silent unmatched-char drop); `heredoc_already_collected`
  initialized before its loop (latent NameError trap).
- Lexer package 4,913 → 4,448 lines (−588 net with tests). Full suite
  green: 4,220 passed / 4,535 collected (15 dead-surface tests removed).

## 0.280.0 (2026-06-10) - Pattern/escape/exception consolidation (reappraisal Tier B, 2/6)
- ONE pattern engine: new `expansion/pattern.py` is the canonical home of
  `PatternMatcher` + module-level `match_shell_pattern()`. The two fnmatch
  paths are gone: `case` legacy matching (control_flow.py's
  `_match_case_pattern` + the 65-line `_convert_case_pattern_for_fnmatch`
  heuristic, deleted) and `[[ == ]]` (`enhanced_test_evaluator._pattern_match`)
  both delegate to the shared engine, so case / `[[ ]]` / `${var#pat}` can
  no longer drift. parameter_expansion.py re-exports PatternMatcher for the
  existing import sites.
- Real bug fixed by the consolidation: the shared glob→regex converter's
  bracket scanner stopped at the first `]`, so POSIX classes
  (`[[ a == [[:alpha:]] ]]`, `case B in [[:upper:]])`, `${x#*[[:digit:]]}`)
  only worked in the constructs that still used fnmatch. The converter now
  scans `[:name:]` correctly and translates POSIX classes to re ranges —
  verified against bash across all constructs (8-probe battery).
- New `utils/escapes.py` houses the shared escape/quote helpers with the
  dialect map documented: `process_echo_escapes` (echo -e/print),
  `quote_printf_q` (printf %q: `a\ b`), `quote_at_q` (${var@Q}: `'a b'`).
  The two quoters were flagged as duplicates by the review but produce
  deliberately different formats in bash itself (verified) — consolidated
  by location and documentation, not falsely unified. printf/read/[[ ]]
  escape dialects remain in place, each documented as intentionally distinct.
- Exception hierarchy rooted: new `PshError` base in core/exceptions.py;
  ShellArithmeticError, BraceExpansionError, LexerError, ParseError,
  PrintOptionError, ExpansionError, UnboundVariableError,
  ReadonlyVariableError, NamerefCycleError all derive from it (callers can
  finally catch "any psh error"). `FunctionReturn` moved to
  core/exceptions.py beside its control-flow siblings LoopBreak/LoopContinue
  — the control-flow family deliberately does NOT derive from PshError, and
  the module docstring explains why. function_support.py re-exports
  FunctionReturn for existing importers.
- Full suite green at unchanged counts (4,235 passed / 4,550 collected).

## 0.279.0 (2026-06-10) - expansion/variable.py decomposition (reappraisal Tier B, 1/6)
- The 1,644-line `expansion/variable.py` grab-bag — the worst file in the
  reappraisal — is decomposed by concern into four mixins, with
  `VariableExpander` as the facade (no call-site changes anywhere):
  - `arrays.py` (307 lines) — subscripts, slices, lengths, array assignment
  - `operators.py` (352) — ${var<op>operand} operator application
  - `operands.py` (238) — pattern/replacement operand mini-expansion
  - `fields.py` (133) — multi-field expansion (${arr[@]}, $@ with operators)
  - `variable.py` (382) — entry points, name resolution, specials, ${!name}
- The six copy-pasted array-element resolution blocks (the
  eval-index-with-ArithmeticError→0 dance, plus 10 repeated local arithmetic
  imports) are replaced by one canonical `_eval_array_index()` helper with
  the bash subscript rule documented once.
- `expand_string_variables` (118 lines) rewritten as a thin wrapper over
  `_expand_one_dollar` — the shared $-scanner also used for operator
  operands — so recognized constructs can't drift between contexts; only
  the double-quote escape rules remain in the wrapper (~70 duplicated
  lines gone). The two arithmetic-context scanners in manager.py were
  examined and deliberately NOT unified: arithmetic substitutes value
  *text* (empty→0, recursively evaluable), a genuinely different rule set.
- `_glob_escape` renamed to public `glob_escape` (manager.py was using it
  cross-class as a de-facto API).
- Pure refactor: zero behavior change intended; full suite green at the
  same counts (4,235 passed / 4,550 collected).

## 0.278.0 (2026-06-10) - Meta-documentation sweep (reappraisal Tier A, 4/4 — Tier A complete)
- ARCHITECTURE.md: sections describing removed subsystems deleted or repointed
  (parser validation/SemanticAnalyzer → psh/visitor/ validators; ParserFactory,
  ParserContext profiler, dead config fields pruned); brace-expansion location,
  heredoc implementation (FileRedirector, not a heredoc.py), combinator file
  list, recognizer list, and scope module name corrected; ~93% POSIX claim
  reconciled with README's ~98%; "3,400+ tests" → 4,550+; two fixed issues
  removed from Known Limitations; ~60 lines of v0.103/v0.104 ProcessLauncher
  release archaeology collapsed to a present-tense description + CHANGELOG
  pointer; stale exact line counts dropped.
- ARCHITECTURE.llm: file map rewritten against the real tree (10+ deleted
  files removed: pipeline/builder.py, six purged lexer modules,
  parser/validation/, support/factory.py, io_redirect/heredoc.py,
  executor/test_evaluator.py); recipes and quick-reference repointed to the
  current locations instead of deleted ones; testing conventions point at the
  real tests/ layout; subshell `-s` limitation removed.
- README.md: false "trap builtin not yet implemented" claim replaced with the
  real gaps (RETURN traps; history word designators/modifiers — `!!`/`!n`
  themselves ARE supported); broken TODO.md link fixed; Built-in Commands list
  regenerated from the registry (59 builtins, grouped); LOC claim recomputed
  with a stated basis (~47.7k production / ~53.6k tests); Recent Development
  trimmed from ~80 bullets to the last 10 versions + CHANGELOG pointer; test
  statistics refreshed (4,235 passing); nonexistent run_tests.sh reference
  fixed; Python 3.12+ requirement stated.
- Root CLAUDE.md: stale "Version: 0.237.0" line replaced with a pointer to
  psh/version.py (numbers there go stale); duplicated v0.195.0 subshell notes
  collapsed to one sentence; "NEW in v0.103.0" dropped; the bash-verification
  probe workflow and the branch/merge/tag release workflow are now documented.
- Subsystem CLAUDE.md API corrections (executor, io_redirect): ProcessLauncher
  .launch signature fixed (execute_fn, config) -> (pid, pgid) with caller-owned
  job registration; ProcessRole values corrected; CommandExecutor/
  PipelineExecutor method names fixed; fork-path table corrected to the real
  3 paths; I/O integration section now names the real IOManager API; heredoc/
  here-string docs now describe the deliberate unlinked-temp-file design (not
  a pipe); test paths fixed; enhanced_test_evaluator.py added to key files.
- docs/ top level decluttered: 33 completed plans, dated analyses, and one-off
  summaries moved to docs/archive/ — what remains at top level is current
  reference material (guides, test docs, user_guide/, reviews/, architecture/).
- AGENTS.md: legacy conformance_tests/ reference fixed; stale subshell `-s`
  guidance corrected. Leftover empty conformance_tests/ dir removed.
- Known flake recorded: tests/conformance/posix/...::test_wait_after_kill_
  reports_signal_status failed once under xdist load (psh reported rc=0 vs
  bash's 143 — a job-status bookkeeping race in wait_for_job's ECHILD path);
  not reproducible in 70 standalone/loaded attempts, passes in re-runs.
  Follow-up tracked for the Tier B executor work.

## 0.277.0 (2026-06-10) - Test-tree cleanup (reappraisal Tier A, 3/4)
- Legacy trees deleted: root `conformance_tests/` (123 files — a second,
  golden-file conformance system superseded by the live psh-vs-bash suite in
  tests/conformance/, including tracked debug junk), `contract_tests_draft/`
  (unreferenced; scenarios duplicated by test_pty_smoke.py and the fd/jobs
  conformance tests), dead `tests/framework/conformance.py` and `base.py`
  (zero importers; interactive.py/pty_test_framework.py kept — still used),
  and four empty dirs.
- Before deleting, the five feature areas only the legacy tree covered were
  folded into the live suite as 30 new conformance tests
  (posix/test_source_cd_scripts_conformance.py): source/., cd semantics,
  backslash-newline line continuation, declare -i/-l/-u/-r/-x, and real
  script-file execution ($0, ${10}, exit codes, ENOEXEC, noexec perms).
- The fold-in probes uncovered and fixed TWO REAL BUGS (bash-pinned):
  - cd used os.environ instead of the HOME/OLDPWD *shell variables* —
    `HOME=/x; cd` went to the real home, and bare `cd` with HOME unset
    silently went to / instead of erroring (bash: "cd: HOME not set", rc 1).
  - psh lacked the POSIX ENOEXEC fallback: an executable text file without
    a shebang failed with "Exec format error" (rc 126) instead of being run
    as a shell script. exec_external() in executor/strategies.py now re-execs
    such files through psh, with PATH-correct resolution.
- Conformance framework now pins LC_ALL=C/LANG=C in run_in_shell so sort
  order, error text, and glob ranges can't drift by machine.
- Fixed-`/tmp` paths removed from 7 test files (xdist collision risk and a
  violation of the project's own tmp/ rule) — converted to temp_dir/tmp_path
  fixtures; test_pushd_logical_paths now reads PWD from captured stdout.
- Stale test metadata corrected: "History/Tab completion not implemented yet"
  xfail reasons rewritten honestly (the features exist; those tests feed
  non-interactive stdin which cannot exercise them); the
  isolated_shell_with_temp_dir docstring no longer warns about the `-s` flag
  (fixed in v0.195.0); reset_environment's hardcoded env-var list dropped
  (superseded by the _restore_os_environ autouse fixture, now cwd-only).
- References updated: AGENTS.md and the CLAUDE.md development principle now
  name `tests/conformance/` explicitly, and the principle documents the
  enforcing claims meta-test.

## 0.276.0 (2026-06-10) - Behavior bugs from the reappraisal (Tier A, 2/4)
- read builtin: option parsing rewritten getopt-style, pinned to bash with a
  17-probe battery. Fixes: combined options no longer abandon the option loop
  (`read -rs -p "" x` and `read -rs y x` lost everything after the cluster —
  the cluster even became a *variable name*); attached option values now work
  (`-rn3`, `-rp prompt`); `--` ends options; `read -n 0` reads nothing and
  succeeds (was rc 1); invalid option *values* exit 1 while invalid options
  exit 2, matching bash's distinction.
- Background-job notices: the three `[N] pid` sites in executor/strategies.py
  printed to stdout; now stderr, consistent with pipeline.py/subshell.py and
  bash.
- Last pytest sniff removed from production code: expansion/command_sub.py
  gated child-stdin protection on PYTEST_CURRENT_TEST; replaced with a real
  capability check (`os.isatty(0)` — only protect stdin when it actually is
  the terminal).
- Combinator parser drift fixed (found by the reappraisal, regressions from
  rd fixes in v0.266–v0.269): function-definition trailing redirects now
  attach to FunctionDef and apply per call in all three definition forms
  (was: applied at definition time); case patterns now carry per-part quote
  context via Word AST (was: quoted glob chars stayed active, so
  `case ab in "a*")` wrongly matched).
- New tests: tests/unit/builtins/test_read_option_parsing.py (13) and
  tests/integration/parser/test_combinator_parity_regressions.py (9,
  three-way bash/rd/combinator parity). Suite: 4,520 collected, 4,205 passed.
- docs/guides/combinator_parser_remaining_failures.md: stale "0 failures as
  of v0.171.0" replaced with an honest drift caveat and the parity-test
  convention for future rd fixes.

## 0.275.0 (2026-06-10) - Packaging truth + whole-tree lint hygiene (reappraisal Tier A, 1/4)
- Packaging now tells the truth about Python support: `requires-python = ">=3.12"`
  (the tree already required 3.12 in fact — a PEP 701 nested-quote f-string in
  `visitor/debug_ast_visitor.py` is a SyntaxError on 3.11 and below); classifiers
  trimmed to 3.12–3.14; ruff `target-version` bumped py38 → py312.
- Whole production tree and test tree are now ruff-clean: 36 violations in `psh/`
  (27 unused imports, 9 unsorted import blocks) and 50 in `tests/` auto-fixed;
  one F841 fixed by strengthening the test to assert the exit code
  (`test_readwrite_creates_file_if_missing` now checks `returncode == 0`);
  stray mis-indented import in `parser/recursive_descent/parser.py` fixed.
- CI (`.github/workflows/test_migration.yml`) bumped 3.11 → 3.12 in all three
  jobs so the lint job, quick suite, and conformance smoke all run at the new
  floor (3.11 CI would now fail `pip install` against `requires-python`).
- CLAUDE.md lint guidance widened from `ruff check psh/parser/combinators/` to
  `ruff check psh/` — the whole tree must stay clean from here on.
- First release of the Tier A program from the ground-up reappraisal
  (docs/reviews/ground_up_reappraisal_2026-06-10.md).

## 0.274.0 (2026-06-10) - Conformance expansion + claims meta-test (review Tier 3, phase 8 — campaign complete)
- 98 new conformance tests filling the thin areas the review flagged:
  getopts (silent/loud modes, clustering, --, local OPTIND), select
  (choices, REPLY, EOF status), traps (EXIT/ERR/DEBUG/signals/ignore),
  heredocs (quoting forms, <<-, pipelines, sequences, redirect targets),
  fd duplication (exec open/dup/close for read and write, swap order,
  unopened fds), non-interactive job control (wait statuses, kill, $!),
  C-style for, control structures in pipelines, and eval.
- The claims META-TEST (tests/conformance/test_claims_have_tests.py)
  makes the project principle checkable: every "Full support" row in the
  user guide's compatibility table must map to existing conformance
  evidence; new claims without proof fail the suite. It immediately
  caught three unproven claims (C-style for loops, control structures in
  pipelines, eval) — all three now have conformance tests.
- Real bugs the new tests surfaced, all fixed:
  - `$$` returned the CHILD's pid in subshells, command substitutions
    and forked redirect-target expansion (POSIX: the original shell's
    pid everywhere). Captured once at startup, inherited like $PPID.
  - `exec 5<file` clobbered stdin instead of opening fd 5 (input
    redirects ignored their explicit fd); `read <&5` then failed.
  - Signal traps for signals psh doesn't otherwise manage (USR1, USR2,
    ALRM, ...) never installed an OS handler — the shell simply died on
    delivery. trap now installs queueing handlers (actions run at
    command boundaries) and SIG_IGN/SIG_DFL for ''/'-' forms.
  - Subshells now run their own EXIT trap: (trap 'echo bye' EXIT; ...).
  - Background-job notices ([1] 1234) printed in non-interactive shells;
    bash prints them only interactively. Now gated on interactive mode.
  - select's EOF newline goes to stdout (bash), exec's open errors no
    longer leak Python errno reprs.
- Stale user-guide claim corrected: DEBUG/ERR traps are supported (since
  v0.263); RETURN is not.
- Final architecture-review annotation: ALL FOUR TIERS RESOLVED across
  37 releases (v0.238.0-v0.274.0); the remaining bash differences are
  deliberate and documented. Suite: 3,979 → 4,499 tests over the
  campaign.

## 0.273.0 (2026-06-10) - Multi-row line-editor rendering (review Tier 3, phase 7)
- The line editor renders wrapped lines correctly. Every mutating edit
  operation (insert, delete, kills, yank, transpose, history nav,
  search, undo/redo, completion) now funnels through ONE wrap-aware
  repaint (_redraw/_paint), and pure cursor movement uses wrap-aware
  relative positioning (_move_cursor_to). The old per-operation
  backspace + ESC[K arithmetic — which corrupted the display the moment
  prompt+input exceeded the terminal width, since \b never moves up a
  row — is gone (zero raw '\b' writes remain).
- The auto-wrap "pending" state (content ending exactly at the right
  margin) is committed deterministically, so relative cursor math never
  drifts by a row at wrap boundaries. Typing at end of line keeps a
  fast path (echo one char) when no boundary is involved.
- Prompt width is measured correctly: a new pure module (line_layout)
  understands readline's \x01/\x02 invisibility markers (from \[ \]
  in PS1) and OSC title sequences in addition to bare CSI colors — the
  old _visible_length only stripped CSI, so colored/marked prompts threw
  off all cursor math. Marker bytes are also no longer written raw to
  the terminal.
- 16 unit tests on the pure layout computation (prompt measurement,
  wrap positions, boundary handling) and 5 new PTY tests editing in a
  40-column terminal: mid-line insert on a wrapped line, backspace
  across the wrap boundary, ctrl-a/ctrl-k on a wrapped line, history
  recall of a wrapped command, and editing under a colored \[ \]
  prompt. PTY smoke suite is now 26 passing tests.

## 0.272.0 (2026-06-10) - Lexer quote-state consolidation (review Tier 3, phase 6)
- Killed the quadratic backward scan: _is_inside_potential_array_assignment
  walked backward from EVERY quote/expansion character to the previous
  command separator, making a single line of N quoted words lex in
  O(N^2) — 3.8s for 4,000 words. The answer for every position is now
  precomputed in one lazy O(n) forward pass (quote state + bracket
  stack); the same line lexes in 0.039s (~97x) and scaling is linear.
- literal.py's inline ANSI-C quote parser (a duplicate escape-sequence
  implementation) now delegates to the UnifiedQuoteParser, so $'...'
  escape semantics live in exactly one place.
- New lexer performance regression tests (absolute bound + doubling
  ratio) pin the linear behavior — the review's "no performance tests"
  gap for the lexer.
- Assessed the case-pattern `)` inside `$(...)` limitation (stretch
  goal): `$(case x in (x) ...)` parses (use the POSIX paren form);
  making find_balanced_parentheses understand an unparenthesized
  pattern's `)` mid-scan requires keyword-aware parsing, documented as
  a known difference rather than special-cased.

## 0.271.0 (2026-06-10) - Terminal control without test-awareness (review Tier 3, phase 5)
- **Ctrl-C and Ctrl-Z now work on foreground jobs under any PTY.** Three
  real bugs found and fixed:
  1. tcsetattr with TCSADRAIN/TCSAFLUSH (the tty.setraw default) blocks
     until the terminal's output queue drains — which never happens on a
     pty whose master isn't being read. The shell wedged entering/leaving
     raw mode and restoring job terminal modes. All terminal-mode changes
     now use TCSANOW (line editor raw mode, job-control mode save/restore,
     read -s). bash stays responsive in this state; now psh does too.
  2. restore_shell_foreground restored terminal MODES before reclaiming
     terminal OWNERSHIP, so the tcsetattr could block against the dead
     job's process group. Order flipped: tcsetpgrp first.
  3. The PTY smoke xfails for SIGINT/SIGTSTP-to-foreground-job are now
     passing tests, plus a new fg-resume test (21/21, zero xfails).
- One shared `shell.process_launcher` replaces five ad-hoc
  ProcessLauncher constructions across pipeline/subshell/strategies —
  removing the executor→interactive layering reach the review flagged.
- All `'pytest' in sys.modules` gates removed from production code:
  - pipeline/external/subshell terminal control now uses a real
    capability check, JobManager.terminal_pgid_if_owned() (tty present,
    job control supported, AND this shell is the foreground process
    group). Under a test runner that's naturally None.
  - Process-global signal handlers are installed at psh's own entry
    points (__main__ for all modes; the interactive loop re-runs setup
    and claims the foreground) instead of at InteractiveManager
    construction behind a pytest gate. In-process embedders/test shells
    construct Shell directly and never touch process signal state — a
    structural guarantee instead of runner sniffing. The
    PSH_IN_FORKED_CHILD env marker became dead and is removed.
- StringIO type-sniffing removed from the builtin stream-restore path.
  Root cause fixed instead: Shell.__init__ no longer snapshots
  sys.stdout/stderr into the custom-stream overrides (which froze
  init-time objects and defeated the live-tracking ShellState
  properties); the builtin path now saves/restores the override STATE.
- Full suite green (4,063 passed / 4,378 collected); PTY smoke suite
  3x stable at 21/21.

## 0.270.0 (2026-06-10) - PTY test rehabilitation (review Tier 3, phase 4)
- New deterministic pexpect smoke suite (test_pty_smoke.py, 18 passing +
  2 specific xfails) covering the real interactive surface: prompt,
  command execution, state across commands, exit/ctrl-d EOF, ctrl-c at
  the prompt, backspace, arrow-key cursor editing, ctrl-a/k/u/w, history
  recall, PS2 continuation, long (wrapped) lines, background job
  notices, jobs, wait, fg, disown. It REPLACES the two blanket-xfail PTY
  suites (test_pty_line_editing.py, test_pty_job_control.py — deleted),
  whose "pexpect doesn't work under pytest" premise no longer holds.
- The smoke suite runs BY DEFAULT in the standard test run (exempt from
  the --run-interactive gate); the legacy interactive tests stay opt-in.
  Until now the whole interactive directory was silently skipped in
  suite runs — zero interactive coverage in CI.
- Root-caused the old PTY-test folklore (documented in
  README_PEXPECT_ISSUE.md): the line editor's raw mode means Enter is
  CR (pexpect sendline's LF is not accept-line); the DSR cursor query
  (ESC[6n) appears in output; matching must use sentinels that never
  appear in the typed text; and every send must wait for the prompt.
- Fixed module-level sys.modules['termios']=Mock() poisoning in two
  line-editor unit files: it executed at COLLECTION time and broke
  ptyprocess/pexpect for the entire process in whole-tree runs.
- Two genuine gaps carry specific xfails and are the target of the next
  phase (terminal control / is_pytest removal): SIGINT and SIGTSTP
  delivered to a RUNNING foreground job do not return the prompt under
  a pexpect PTY.

## 0.269.0 (2026-06-10) - Parser correctness sweep (review Tier 3, phase 3)
- `f() ( ... )` keeps its subshell semantics: the parser preserves the
  SubshellGroup node instead of unwrapping it, so each call forks.
  Variable writes, `cd` and even `exit` inside the body no longer leak
  into (or kill) the calling shell.
- `f() { ...; } > file` redirections attach to the function definition
  and are applied at each CALL (bash). Previously the redirect parsed as
  a separate empty command, creating/truncating the file once at
  definition time and never during calls. FunctionDef and Function carry
  a redirects list; execute_function_call wraps the body with them.
- Quoted case patterns match literally: CasePattern now carries a Word
  AST with per-part quote context, expanded by the same quoting rule as
  ${x#pat} operands (quoted text and quoted-expansion results are
  escaped; unquoted text and expansion results keep glob power). Fixes
  `case ab in 'a*')` wrongly matching, `"$p"` patterns staying
  glob-active, and `h"*"llo` style mixed patterns. Matching for the Word
  path uses the shared glob->regex converter (handles backslash escapes,
  which fnmatch cannot); the legacy fnmatch path remains for the
  combinator parser.
- `select` returns status 1 when the read hits EOF (bash).
- Dedup: the `&& pipeline / || pipeline` chain loop existed in three
  copies (statements.py, parser.py, commands.py) — now one
  parse_and_or_tail helper; the _FD_DUP_RE regex was defined twice in the
  recursive descent parser (a third lives in the deliberately
  self-contained combinator parser) — now imported from redirections.py.
- Test-infrastructure: an autouse fixture now rolls back os.environ
  after every test, eliminating the export-leak pollution class for
  good. It exposed two tests whose expectations only held because of
  leaked exports (double-quoted `$VAR` handed to an inner `sh -c`
  expands in the OUTER shell, before prefix assignments apply); both
  fixed with escaped dollars after bash verification.
- Still open (pre-existing, unchanged): `\[)` and extglob `@(...)`
  inside case patterns are parse errors; for/select items keep their
  legacy string+quote-type representation (behavior verified correct
  against bash; the Word AST conversion is deferred cleanup).
- 25 new bash-pinned tests (test_function_bodies_and_case_patterns.py).

## 0.268.0 (2026-06-10) - Executor/builtin correctness sweep (review Tier 3, phase 2)
- `f &` runs a function in the background by forking a subshell (bash).
  psh previously rejected it with "functions cannot be run in background".
  Arguments, `wait %1` exit status, redirections and parent-state isolation
  all behave like bash; the child is marked a shell process (keeps SIGTTOU
  ignored) since the function body may run pipelines.
- Circular namerefs (`declare -n a=b; declare -n b=a`) get bash's
  diagnostics: creating the cycle is fine; WRITING through it warns
  "circular name reference" and fails (aborting a non-interactive shell
  with status 1, like other assignment errors); READING warns and expands
  empty (status unchanged); `unset` warns but succeeds. New
  NamerefCycleError raised by resolve_nameref_name and handled per-path.
  The declare-time self-reference error now names the variable.
- `declare -u/-l/-i` no longer transform the EXISTING value — bash applies
  the attribute to future assignments only (`u=abc; declare -u u` leaves
  $u as abc; `x="2+3"; declare -i x` leaves $x as 2+3).
- `type`/`type -t` report shell keywords (if, while, for, case, time,
  `{`, `[[`, ... ) — previously rc 1/no output for `type -t if`.
- `$"..."` locale strings are lexed as plain double-quoted strings in all
  contexts (standalone, assignments, composite words), matching bash
  without a message catalog. The token spans the `$` so composite-word
  adjacency is preserved.
- `$_` tracks the last argument of the previous simple command
  (`true x y; echo $_` prints y); previously it leaked the inherited
  environment value (the Python interpreter path).
- Fixed another env-pollution bug: test_export_builtin exported the
  generic name V into the test runner's environment.
- 50 new bash-pinned tests (test_builtin_correctness_sweep.py,
  test_background_functions.py).

## 0.267.0 (2026-06-10) - Expansion correctness sweep (review Tier 3, phase 1b)
- `${!name}` indirection resolves through the full parameter namespace:
  positionals (`n=2; ${!n}` -> `$2`), array elements (`ref='a[1]'`,
  `ref='a[@]'`, assoc keys), special parameters (`${!#}` -> last
  positional, `ref='@'`) and operators after indirection apply to the
  target (`${!ref%pat}`, `${!n:-d}`). bash diagnostics: an unset source is
  "invalid indirect expansion" and a malformed target name is "invalid
  variable name" (both status 1, the error beating any `:-` default);
  out-of-range positional sources are plain unset.
- Arithmetic uses bash's textual/recursive variable resolution: `$(($x))`
  with `x='2 + 2'` is 4 (the value text is substituted, not coerced to 0),
  reference chains resolve (`y=z; z=42; x=y; $(($x))` -> 42), and circular
  references now raise "expression recursion level exceeded" (status 1)
  instead of silently yielding 0.
- Tilde expansion reads the shell's HOME variable (`HOME=/xyz; echo ~` ->
  `/xyz`), not the inherited environment.
- `$0` works in parameter expansion: `${0##*/}`, `${0:-x}`, `${#0}`.
- POSIX field splitting: only unquoted-expansion text can split. Escapes
  in literal word text are protected structurally (`pre\ post$x` stays one
  field -- previously split) while backslashes in expansion data are plain
  characters (`x='a\ b'; $x` is two fields `a\` and `b` -- previously
  glued). Composite words merge fields across part boundaries with
  delimiter-edge awareness (`pre$x` with `x=':a'` and IFS=: is
  `pre`, `a`). Quoted text adjacent to an expansion no longer splits
  (`"a b"$x`).
- POSIX expansion ordering for command-prefix assignments: the command's
  own words are expanded BEFORE the temporary assignments take effect
  (`V=v echo $V` prints V's prior value -- psh printed `v` and the
  conformance suite documented bash's correct behavior as "a bash bug";
  that inverted verdict is removed from psh_bash_differences.json).
  Assignments apply sequentially, each value seeing those to its left
  (`A=1 B=$A cmd` gives B=1), and when the command words expand to
  nothing the assignments affect the current shell (`V=v $EMPTY`).
- Fixed cross-test pollution: an env-builtin test exported generic names
  (A/B) into the test runner's environment, breaking the conformance
  assignment probe in combined runs.
- 45 new bash-pinned tests (test_expansion_correctness_sweep.py); 5 tests
  updated from old-behavior pins to bash-verified expectations.

## 0.266.0 (2026-06-10) - Pattern-operator operand expansion (review Tier 3, phase 1a)
- Pattern operands of `${x#pat}`, `${x##pat}`, `${x%pat}`, `${x%%pat}`,
  `${x/pat/repl}` and the case-mod operators now undergo variable, command
  and arithmetic expansion with one level of quote removal, matching bash.
  Previously `$var` in these operands was matched as the four literal
  characters `$var`, so the everyday `${f%$ext}` / `${f#$prefix}` idioms
  silently failed; quoted operands (`${f#'a'}`) kept their quotes.
- Quoting controls glob power exactly as in bash: unquoted text and
  unquoted-expansion results keep glob meaning (`p='*'; ${x/$p/Z}` matches
  everything), while quoted text and quoted-expansion results match
  literally (`${x/"$p"/Z}` looks for a literal star).
- Replacements are inserted literally via a callable, never interpreted as
  a regex template: `${x/b/\1}` no longer crashes with "invalid group
  reference" and `${x//X/\n}` no longer injects newlines.
- bash 5.2 patsub_replacement semantics: an unquoted `&` in the replacement
  (even one produced by an expansion) stands for the matched text; `\&`,
  `"&"` and `'&'` are literal; an unquoted backslash escapes the next
  character and is removed; backslashes inside expansion results stay
  literal.
- Pattern/replacement splitting is now quote- and construct-aware, so a
  `/` inside quotes, `${...}`, `$(...)` or `$((4/2))` no longer splits the
  operand early. Empty patterns are a no-op (`${x///Z}` returned
  `ZaZbZcZ`-style corruption before; bash returns the value unchanged).
- Case modification matches bash's per-character rule: `${v^pat}` tests
  only the FIRST character against the pattern (`${v^b}` on `abc` is now a
  no-op) and `${v^^pat}` examines each character individually, so
  multi-character patterns like `${v^^bc}` never match.
- All of the above applies per element to array expansions
  (`${a[@]%$ext}`, `${a[@]/$p/X}`).
- 44 new bash-pinned tests (tests/unit/expansion/test_pattern_operand_expansion.py).

## 0.265.0 (2026-06-10) - Heredoc lexing redesign + lexer correctness (review Tier 2, phase 6)
- HeredocLexer rewritten: lines are classified (command text vs heredoc
  body) and the joined command text is tokenized in ONE ModularLexer pass,
  so cross-line lexer state survives. The old design re-lexed each physical
  line with a fresh lexer, breaking any multi-line construct sharing a
  command with a heredoc — `cat <<EOF && echo "two\n...words"` died with
  "Unclosed quote"; it now matches bash exactly (incl. bash's rule that
  mid-construct lines are command continuation, so the body region follows
  the COMPLETED command). Heredoc operators are found from tokens, so a
  quoted "<<EOF" is never a heredoc.
- source_processor no longer tokenizes heredoc-containing commands twice.
- The textual unclosed-heredoc detector (line buffering) is quote-aware
  with quote state carried ACROSS command lines: `echo "<<EOF" ok` no
  longer buffers forever waiting for a delimiter.
- validate_brace_expansion is quote- and $()-aware: `echo ${x:-"}"}`,
  `${x:-'}'}` and `${x:-$(echo "}")}` no longer die with "Unclosed quote"
  (POSIX 2.6.2).
- Conditional-operator operands remove one level of quotes like bash:
  `${u:-"quoted def"}` prints `quoted def`, not `"quoted def"`; single
  quotes keep operands literal; applies to scalar and array-field paths.
  One test expectation that encoded the old quote-retaining behaviour was
  updated to the bash-verified output.
- First unit tests for the heredoc modules (previously 0% coverage):
  tests/unit/lexer/test_heredoc_lexer.py (11 cases).

## 0.264.0 (2026-06-10) - POSIX & grammar + structural EOF detection (review Tier 2, phase 5)
- `&` is parsed at the and-or-list level per the POSIX grammar:
  `a && b &` backgrounds the WHOLE list (previously the list ran
  synchronously with only its tail backgrounded), and control structures
  can be backgrounded (`while ...; done &`, `if ...; fi &` were parse
  errors). `echo a & && b` is now a syntax error like bash. Single
  simple-command and single-pipeline cases keep the existing direct
  job-control paths; everything else runs in a background subshell
  (AndOrList.background + ExecutorVisitor._execute_background_list).
- POSIX linebreak-after-pipe: `echo hi |` followed by a newline continues
  onto the next line.
- ParseError carries a structural `at_eof` flag (the parse failed at end
  of input, so more lines could complete it). Script line-continuation
  (source_processor) and interactive multi-line detection
  (multiline_handler) key off it, replacing ~70 fragile error-message
  patterns between them — which also fixes scripts with lines ending in
  `&&`/`||`.
- New tests in tests/unit/parser/test_background_lists.py (12 cases pinned
  to bash 5.2).

## 0.263.0 (2026-06-09) - DEBUG/ERR traps + deferred signal traps (review Tier 2, phase 4)
- DEBUG and ERR traps now FIRE. They were stored, documented in `trap`
  help, and silently never dispatched (execute_debug_trap/execute_err_trap
  had zero call sites). DEBUG runs before each simple command; ERR runs
  after eligible failures with exactly the set -e exemptions (reusing the
  v0.253.0 errexit_eligible machinery), sees the failing status in $?, and
  fires before an errexit abort, like bash. A re-entrancy guard keeps
  DEBUG/ERR actions from re-triggering themselves.
- Signal trap actions no longer execute inside the Python signal handler
  (where they could re-enter the parser/executor mid-command, contradicting
  the shell's own self-pipe design). The handler queues the trap and the
  executor runs it at the next command boundary — bash's documented
  behaviour — preserving output ordering.
- Also lands the unreachable empty-action branch removal in
  TrapManager.execute_trap that the v0.258.0 notes claimed but whose edit
  was never written to disk.
- docs/user_guide/17_differences_from_bash.md updated (only RETURN traps
  remain unsupported); new tests in
  tests/integration/job_control/test_debug_err_traps.py (11 cases).

## 0.262.0 (2026-06-09) - Scripting idioms (review Tier 2, phase 3c)
- Scalar `+=` append assignment: `x+=b` appends (previously "command not
  found"); integer (-i) variables add arithmetically (declare -i n=1;
  n+=2 -> 3); works for pure assignments, command-prefix assignments
  (temporary), and `export NAME+=value`; readonly `+=` aborts like any
  readonly assignment. The golden case that encoded the old failure was
  updated to bash's behaviour.
- `printf -v var format args` stores the result in var (array elements
  supported) instead of printing; `printf '%(datefmt)T'` formats an epoch
  argument with strftime (missing/-1 = now).
- A quoted right-hand side of `[[ =~ ]]` is matched LITERALLY, like bash:
  `[[ abc =~ "a.c" ]]` no longer matches. Unquoted and variable patterns
  remain regexes; BASH_REMATCH unchanged.
- New `builtin` builtin: runs a shell builtin bypassing function lookup,
  so wrapper functions (cd() { builtin cd "$@"; ... }) work instead of
  recursing to "command not found".
- New tests in tests/integration/test_scripting_idioms.py (24 cases).

## 0.261.0 (2026-06-09) - Special variables (review Tier 2, phase 3b)
- PIPESTATUS: every foreground pipeline records its members' exit statuses
  (the waiter now always collects them, not only under pipefail); a single
  command records a one-element list, matching bash.
- $PPID (captured at startup; stable across subshells like bash), $UID and
  $EUID, $EPOCHSECONDS, and $EPOCHREALTIME (microsecond precision) as
  dynamic special variables.
- $- includes 'c' when the shell was started with -c.
- New tests in tests/unit/expansion/test_special_variables.py (10 cases).

## 0.260.0 (2026-06-09) - umask and times builtins (review Tier 2, phase 3a)
- New POSIX-required builtins in psh/builtins/system_builtins.py, built on
  the v0.259.0 base helpers:
  - umask: display (plain/-S symbolic/-p reusable), octal set, and symbolic
    set (u+rwx,g-w,o=,a=rx — clauses operate on the allowed-permission
    complement per POSIX), with bash's error messages and exit codes.
    Previously /usr/bin/umask ran as an external command on macOS, so
    `umask 077` silently did nothing — files were still created 644.
  - times: shell and children user/system CPU times in bash's
    NmN.NNNs format.
- New tests in tests/unit/builtins/test_system_builtins.py (11 cases incl.
  verifying the mask actually applies to created files).

## 0.259.0 (2026-06-09) - Builtin infrastructure (review Tier 2, phase 2)
- New shared helpers on the Builtin base class:
  - write()/write_line(): one implementation of the forked-child fd-level
    vs parent shell.stdout output routing that echo/printf/pwd/declare -p/
    env/export/set each carried a private copy of; error() is now also
    forked-child aware. Migrated the seven copied sites.
  - parse_flags(): getopt-style option parsing (clusters, attached or
    separate option values, --, invalid options exit 2 with a usage line).
    unset migrated to it.
- One associative-array initializer parser
  (array_init.parse_assoc_array_entries) replaces the two divergent copies
  in local/declare, fixing three bash divergences: declare -A values
  containing $expansions now expand ([k]=$x), quoted values with spaces work
  under local -A ([k]="x y" no longer truncates), and dynamic keys expand
  ([$k]=v). Single-quoted values stay literal.
- Usage-error exit codes match bash: declare/local/readonly invalid options
  exit 2 (was 1); `unset` with no operands succeeds silently (bash, was rc
  1) and invalid unset options exit 2. Two declare tests updated to the
  bash-verified status.
- New tests: tests/unit/builtins/test_builtin_base_helpers.py (12 cases).

## 0.258.0 (2026-06-09) - Executor/builtins/vi scraps purge (review Tier 2, phase 1c)
- Remove dead ProcessLauncher.launch_job (zero callers; contained a fragile
  command_str.split() re-parse) and the dead DeclareBuiltin._apply_attributes
  (the scope manager applies attribute transforms).
- trap_manager: remove the unreachable empty-action branch and replace the
  install-and-restore signal probing of numbers 1-31 with
  signal.valid_signals().
- Rename psh/executor/test_evaluator.py -> enhanced_test_evaluator.py
  (source files must not start with test_, per the project's own pytest
  collection rules).
- vi editing: the keymap now matches actual behavior. Removed ~30 bindings
  (registers, motions d/c/y/p/r, visual mode, search, '.') that
  _execute_action never dispatched — silent no-ops since they were added —
  plus the orphaned state behind them (vi_pending_motion, vi_registers,
  vi_last_change, vi_mark_start, kill_ring_pos, EditMode.VI_VISUAL). The
  ViKeyBindings docstring documents the implemented subset.
- vi undo/redo are now REAL: 'u' and Ctrl-R dispatch to the existing
  (previously unreachable) undo()/redo() implementations; key_handler.mode
  is synced on mode switches so control-key normal-mode bindings resolve
  correctly; undo() treats the live buffer as the implicit stack top so the
  most recent edit is not skipped. New tests include a guard asserting every
  bound action is dispatched, so phantom bindings cannot reappear.
- psh/executor/CLAUDE.md strategy-order snippet corrected to the code's
  actual POSIX order (special builtins > functions > builtins).

## 0.257.0 (2026-06-09) - Lexer dead-code purge (review Tier 2, phase 1b)
- Remove ~680 lines of lexer fiction flagged by the architecture review:
  - The dead OPERATORS_BY_LENGTH table in constants.py — it had drifted from
    the live table (OperatorRecognizer.OPERATORS) and psh/lexer/CLAUDE.md
    told contributors to edit it; the doc now points at the real table.
  - LexerErrorHandler + RecoverableLexerError (type-hinted a nonexistent
    StateMachineLexer; never instantiated) and the LexerState enum (every
    member except NORMAL unused; the state field itself was never consulted).
  - 28 never-read LexerConfig fields (error-recovery, performance, debugging,
    zsh/sh compatibility, memory management) plus the unused
    create_performance_config/create_debug_config/create_posix_config presets
    and to_dict/from_dict. Re-judged from the earlier "keep tested
    infrastructure" decision: unread configuration misleads readers about how
    the lexer works. create_interactive_config/create_batch_config remain as
    the public entry points and are documented as currently identical.
  - QUOTE_RULES escape maps replaced by an honest processes_escapes boolean:
    the '"' map declared C-style escapes (\n → newline) that are wrong per
    bash AND were never read (only tested for truthiness before delegating to
    pure_helpers.handle_escape_sequence, which is bash-correct).
  - Seven unused LexerContext fields (state, paren_depth, quote_stack,
    heredoc_delimiters, brace_depth, token_start_offset, current_token_parts,
    after_regex_match) and ~16 unused methods incl. the lossy copy();
    CLAUDE.md's LexerContext listing now matches reality and explains why
    quote state is not cross-token state.
  - Four unused pure_helpers functions (read_until_char, find_word_boundary,
    scan_whitespace, find_operator_match) and their tests.
- No behaviour change (full suite + conformance green).

## 0.256.0 (2026-06-09) - Parser dead-machinery purge (review Tier 2, phase 1a)
- Remove ~850 lines of parser machinery that production never read, all
  flagged by the 2026-06-09 architecture review:
  - The ParserContext state flags (in_test_expr, in_arithmetic,
    in_case_pattern, in_function_body, in_command_substitution,
    in_process_substitution) and the save/restore context manager that
    existed only to restore them — written by four sub-parsers, read by
    nothing. psh/parser/CLAUDE.md documented the pattern as a core
    convention; it now documents that grammar context lives in the
    recursive call structure, not in flags.
  - The execution_context AST field (STATEMENT/PIPELINE) and the ~25
    _parse_X_neutral / parse_X_statement / parse_X_command wrapper
    triplets that existed solely to set it. Each construct now has one
    parse_X_statement method; ExecutionContext was removed from
    ast_nodes (the executor's ExecutionContext is unrelated and intact).
  - ParserProfiler (~105 lines) and the enter_rule/exit_rule/parse_stack
    rule-tracking hooks: re-judged from the earlier "keep tested
    infrastructure" decision (v0.231.0 era) because the hooks were never
    called during production parsing, so the profiler could not measure
    anything real and its tests tested fiction.
  - The phantom `debug-parser` option / ParserConfig.trace_parsing chain:
    it claimed to enable parser tracing but the tracing hook was never
    invoked. Removed end-to-end (set -o entry, debug builtin, parser-mode
    educational no longer claims "with debugging").
  - scope_stack/loop_depth/function_depth/conditional_depth counters,
    the ctx heredoc trackers + HeredocInfo, get_state_summary/reset_state,
    and the duplicate Parser.parse_with_heredocs method (production uses
    the module-level function, which the regression tests now target).
- tests/unit/parser/test_parser_context.py rewritten to cover the
  context's real responsibilities; three tests retargeted from removed
  APIs to their live equivalents. No behaviour change (full suite +
  conformance green; control-structure/pipeline smoke battery vs bash
  unchanged).

## 0.255.0 (2026-06-09) - Process substitutions preserve sibling quoting (review Tier 1 E)
- When any argument was a process substitution, ALL of the command's words
  were rebuilt from plain strings, discarding quote context — a quoted "*"
  glob-expanded and a quoted "$x" containing spaces split into fields. Only
  the process-substitution words are replaced with their /dev/fd/N paths
  now; every other word keeps its Word AST.
- The command node is no longer mutated in place, so a command re-executed
  in a loop re-creates its substitutions instead of reusing a stale fd path.
- New tests in tests/unit/expansion/test_process_sub_quoting.py (7 cases).

## 0.254.0 (2026-06-09) - Multi-field quoted array expansion (review Tier 1 D)
- Quoted @-subscripted expansions now produce one field per element, the
  central bash array semantic: "${a[@]}", "${@:2}", "${a[@]:1:2}",
  "${a[@]#pat}", "${a[@]/p/r}", "${a[@]^^}", "${a[@]@Q}",
  "${a[@]:-default}" etc. Previously only "$@" was special-cased and
  everything else collapsed into ONE word, silently corrupting array
  elements containing whitespace.
- Implemented as VariableExpander.expand_to_fields() (resolves the base
  fields, parses operators baked into bracketed parameter text, slices
  positionals/arrays — indexed arrays slice by INDEX like bash — and
  applies value operators per element) plus a generalized affix walker in
  ExpansionManager that distributes prefix/suffix text across fields and
  supports multiple field expansions per word.
- Empty "$@"/"${a[@]}" yields ZERO fields (was one empty field):
  `set --; set -- "$@"; echo $#` now prints 0.
- Unquoted $@/${a[@]} expand to fields before IFS splitting, so parameter
  and element boundaries survive a custom IFS
  (`set -- "a b" c; IFS=:; printf '[%s]' $@` → [a b][c]).
- printf with no arguments now applies the format once with missing
  arguments as ''/0 (`printf '[%s]'` prints `[]`), per POSIX — previously
  the format string was echoed with the bare %s intact.
- "${a[*]}" and ${#a[@]} keep their scalar semantics; ${a[@]@A} keeps the
  whole-array assignment form.
- New tests: tests/unit/expansion/test_multi_field_expansion.py (23
  field-count-pinned cases) and a TestArrayFieldExpansion conformance class
  (8 cases). The for-loop array path in control_flow.py is retained until
  for-loop items carry Word AST (parser limitation).

## 0.253.0 (2026-06-09) - Context-aware errexit + subshell inheritance + readonly fatality (review Tier 1 C)
- set -e now honours the POSIX exemptions exactly as bash: failures in
  if/elif/while/until conditions, in non-final members of && / || lists,
  and under ! negation do not exit the shell; everything else does
  (plain failures, functions, final && members, last pipeline element,
  subshells). Implemented as an errexit_suppress counter on
  ExecutionContext (conditions, non-final/negated pipelines) plus a
  per-AndOrList eligibility flag consumed by the statement-level checks
  and the three source_processor exit sites. Because nested execution
  shares the context (and forked subshells seed it), the exemption
  extends through functions, groups, eval, and subshells, as in bash.
- Subshells inherit the parent's shell options (set -e, pipefail, ...) and
  $?: `set -e; (false; echo no)` aborts inside the subshell and
  `false; (echo $?)` prints 1.
- Assignment exit status matches bash: a pure assignment reports 0 unless a
  command substitution ran while expanding its value (then that status) —
  previously it re-reported the previous command's status, which broke
  `v=$(false) || v=default` under set -e.
- Assignment to a readonly variable aborts a non-interactive shell with
  status 1 (command-prefixed `RO=v cmd` fails with rc 1 but continues,
  like bash).
- New tests: tests/conformance/posix/test_errexit_conformance.py (21 cases
  — the suite previously had zero errexit conformance tests despite the
  user guide's "Full support" claim) and
  tests/integration/shell_options/test_errexit_script_mode.py (8 cases,
  incl. an end-to-end `set -euo pipefail` strict-mode script). The
  differences doc's strict-mode workaround section was replaced with the
  bash-identical guidance.

## 0.252.0 (2026-06-09) - External redirections applied once (review Tier 1 B)
- External-command redirections were applied TWICE — by the parent
  (with_redirections) and again by the forked child
  (setup_child_redirections). Consequences fixed: `cmd 2>&1 >f` resolved
  `2>&1` against the already-redirected fd 1 and sent stderr into f (bash:
  to the original stdout), and command substitutions in heredoc bodies and
  redirect targets executed twice. The parent now skips fd-level
  application for ExternalExecutionStrategy; the child path already handles
  every redirect type (incl. process-substitution targets, dynamic fd dups,
  noclobber, heredocs).
- New side-effect-counting and ordering tests in
  tests/integration/redirection/test_external_redirect_once.py (10 cases
  pinned to bash 5.2).

## 0.251.0 (2026-06-09) - Large heredocs via temp file (review Tier 1 A3)
- Heredoc and here-string content used to be written in full into an
  os.pipe() before any reader existed, deadlocking the shell for bodies
  larger than the kernel pipe buffer (~64KB; verified hang at 130KB).
  Content now goes through an anonymous unlinked temp file dup2'd to stdin
  — the same approach bash uses — shared by both helpers
  (FileRedirector._stdin_from_content).
- New tests in tests/integration/redirection/test_large_heredoc.py
  (8 cases incl. 300KB bodies, content integrity, expansion behaviour).

## 0.250.0 (2026-06-09) - return works in sourced files (review Tier 1 A2)
- `return N` inside a sourced script stops executing the file and becomes the
  exit status of `source`/`.`, like bash (previously: "can only return from a
  function" error and the rest of the file kept executing). Implemented with
  a source-nesting counter on ShellState; nested sourcing returns one level.
- `return` inside a function in a sourced file still exits the function only.
- Exit-code fixes pinned to bash: top-level `return` is rc 2 (was 1), and
  `return abc` prints the numeric-argument error but still returns from the
  function/file with rc 2 (was: continued executing the function body).
- New tests in tests/unit/builtins/test_source_return.py (8 cases).

## 0.249.0 (2026-06-09) - exec failure exits non-interactive shell (review Tier 1 A1)
- `exec missing_command` now exits a non-interactive shell with status 127
  (126 for found-but-not-executable), per POSIX and bash, instead of
  printing the error and continuing with rc 0. Interactive shells survive
  and report the status.
- New tests in tests/unit/builtins/test_exec_builtin.py (4 cases).

## 0.248.0 (2026-06-09) - set -u message and fatality (review Tier 0 #11)
- `set -u` violations printed "psh: psh: $x: unbound variable": the expansion
  code wrapped the message in a "psh: " prefix that the printing handler
  added again. The wrappers are gone; the message now matches bash's format
  exactly (`x: unbound variable`; positionals keep the `$`).
- A non-interactive shell now aborts with status 127 on a nounset violation,
  like bash, instead of continuing with rc 0. Interactive shells report the
  error and continue.
- Out-of-range positional parameters (`echo $5`) now trigger the nounset
  check (previously silently expanded empty).
- New subprocess tests in
  tests/integration/shell_options/test_nounset_script_mode.py (8 cases).

## 0.247.0 (2026-06-09) - Control flow propagates through eval (review Tier 0 #10)
- `eval break` / `eval continue` / `eval return N` now act on the enclosing
  loop/function instead of printing "only meaningful in a loop" (or
  "unexpected error") and being converted to exit status 1. Three causes
  fixed: nested execution (eval, source, trap actions) reuses the caller's
  ExecutorVisitor via Shell._execute_with_visitor so loop depth and function
  context carry through; the broad exception guards in executor/strategies.py
  re-raise LoopBreak/LoopContinue/UnboundVariableError (matching
  command.py's handling); and source_processor re-raises control-flow
  exceptions when execution is nested instead of reporting them.
- Top-level `break`/`continue` outside any loop now warn once and continue
  executing with status 0, like bash (previously: warning printed twice,
  status 1, remaining statements skipped). Two legacy tests asserting the
  non-bash exit code were updated to the bash-verified behaviour.
- New tests in tests/integration/control_flow/test_eval_control_flow.py
  (9 cases pinned to bash 5.2).

## 0.246.0 (2026-06-09) - Transactional redirection save/restore (review Tier 0 #9)
- `builtin 2>&1` no longer kills the shell's stdout: restore used to close
  whatever object was in sys.stderr (after 2>&1 that IS the real stdout),
  breaking every later builtin with "I/O operation on closed file". Restore
  now closes exactly the files setup opened, tracked per call.
- Same fd redirected twice (`echo hi >c >d`, `{ cmd; } >e >f`) restores the
  ORIGINAL stream/fd afterwards: fd-level restore iterates in reverse (as the
  io_redirect CLAUDE.md always documented) and builtin stream backups are
  recorded first-touch-wins instead of being overwritten.
- A redirect failing part-way (`echo hi >a >/bad/x`) rolls back the
  redirections already applied — both the builtin stream path and the
  fd-level apply_redirections — instead of leaving the shell's stdout
  hijacked for the rest of the session.
- New subprocess regression tests in
  tests/integration/redirection/test_redirection_restore.py (12 cases pinned
  to bash 5.2 behaviour).

## 0.245.0 (2026-06-09) - Brace expansion on heredoc lines (review Tier 0 #8)
- tokenize_with_heredocs() omitted the TokenBraceExpander pass that
  tokenize() performs, so any command line containing a heredoc silently
  lost brace expansion (`cat <<EOF; echo {a,b}` printed `{a,b}`; bash: `a b`).
  Heredoc bodies remain literal, as in bash.
- First unit tests touching the heredoc lexer path
  (tests/unit/lexer/test_heredoc_brace_expansion.py, 6 cases).

## 0.244.0 (2026-06-09) - trap -- handling (review Tier 0 #7)
- `trap -- 'action' SIGNAL` works: a leading `--` ends option processing per
  POSIX instead of being taken as the action ("invalid signal
  specification"). Bare `trap --` lists traps like bare `trap` (bash).
- New tests in tests/unit/builtins/test_signal_builtins.py (4 cases).

## 0.243.0 (2026-06-09) - export option parsing and validation (review Tier 0 #6)
- `export` now parses options: `-p` prints exports (optionally filtered by
  name) instead of creating a variable literally named `-p`; `-n` removes the
  export attribute (keeping the variable, with optional assignment); `--`
  ends option processing; unknown options exit 2.
- Invalid identifiers are rejected with rc 1 (`export 1bad=x`), and like
  bash the remaining arguments are still processed.
- New tests in tests/unit/builtins/test_export_builtin.py (12 cases pinned
  to bash 5.2 behaviour).

## 0.242.0 (2026-06-09) - set builtin option parsing (review Tier 0 #5)
- `set` no longer returns after the first `-o`/`+o`: `set -o errexit -o
  pipefail` and mixed forms like `set -o pipefail -x foo bar` now apply every
  option before collecting positional parameters.
- `set -euo pipefail` works: a trailing `o` in a short-option cluster consumes
  the next argument as a long option name, like bash. The corresponding
  "Combined Short Option Parsing" difference was removed from
  docs/user_guide/17_differences_from_bash.md and is backed by new
  conformance tests.
- `set -o vi`/`set -o emacs` are silent (bash prints nothing), and bare `set`
  no longer emits a non-bash `edit_mode=...` line.
- Invalid options ("set -q", "set -o badname") now exit 2 with bash-style
  messages; `+o badname` errors instead of silently succeeding.
- New tests: tests/unit/builtins/test_set_builtin.py (14 cases) and 3
  conformance tests in tests/conformance/bash/test_bash_compatibility.py.

## 0.241.0 (2026-06-09) - UNSET tombstones hidden from variable listings (review Tier 0 #4)
- `get_all_variables()`/`all_variables_with_attributes()` no longer include
  UNSET tombstones: after `f(){ unset HOME; ...}` the variable disappeared
  from lookups but still showed as `HOME=` in `set` output (bash shows
  nothing). Tombstones in inner scopes now also remove the shadowed
  outer-scope name from listings, matching lookup semantics.
- First direct unit tests for EnhancedScopeManager tombstone visibility
  (tests/unit/core/test_scope_tombstones.py, 9 cases pinned to bash 5.2).

## 0.240.0 (2026-06-09) - Fix ${!prefix@}/${!prefix*} prefix matching (review Tier 0 #3)
- `${!prefix@}`/`${!prefix*}` passed the (always-empty) operand instead of the
  variable name as the prefix, so they listed EVERY shell+environment
  variable. They now match only names with the given prefix.
- Names are no longer emitted with literal `"` quote characters (bash never
  does this), and quoted `${!prefix*}` joins with the first character of IFS,
  consistent with `$*`.
- Tightened the integration tests whose substring assertions masked the bug
  and added no-match and IFS-join cases (exact-match assertions, pinned to
  bash 5.2).

## 0.239.0 (2026-06-09) - Fix local double-expansion injection (review Tier 0 #2)
- `local v='$(cmd)'` no longer executes the command: LocalBuiltin re-expanded
  its already-executor-expanded scalar value, so single-quoted `$`-text was
  expanded a second time (a correctness and injection defect). The value is
  now used as received.
- Array initializers for `local`/`declare` are parsed by one shared
  quote-aware helper (psh/builtins/array_init.py): single-quoted elements
  stay literal, double-quoted elements expand without word splitting, and
  unquoted elements expand with word splitting — matching bash. Previously
  `local` expanded even single-quoted elements and `declare` never expanded.
- Fix the parser's array-initializer reconstruction dropping `$` from
  VARIABLE tokens (`local arr=(one $x)` produced element "x" instead of the
  value of `$x`).
- New tests in tests/unit/builtins/test_local_builtin.py (14 cases pinned to
  bash 5.2 behaviour).

## 0.238.0 (2026-06-09) - Fix break N / continue N beyond loop depth (review Tier 0 #1)
- Fix a crash when `break N`/`continue N` exceeded the enclosing loop depth:
  function-local `import sys` statements in `ExecutorVisitor.visit_TopLevel`/
  `visit_StatementList` shadowed the module-level import, so the
  `except LoopBreak` handler died with UnboundLocalError
  (`while true; do break 2; done` → "cannot access local variable 'sys'").
- Match bash semantics for out-of-range levels: `break N` with N greater than
  the number of enclosing loops now exits all enclosing loops with status 0,
  and `continue N` resumes the outermost loop, instead of escaping to the top
  level as an error. Applied uniformly across while/until/for/C-style-for/select.
- New regression tests in tests/integration/control_flow/test_break_continue_levels.py
  (subprocess-based, pinned to verified bash 5.2 behaviour).
- First fix from the 2026-06-09 architecture & feature review
  (docs/reviews/architecture_feature_review_2026-06-09.md, Tier 0 list).

## 0.237.0 (2026-06-07) - Extract pure multiline helper from LineEditor (§1.5)
- Move the 93-line, state-free `LineEditor._convert_multiline_to_single` to a
  standalone pure function `psh/line_editor_helpers.convert_multiline_to_single`
  (callers and the existing test updated; new focused unit tests added). Trims
  `line_editor.py` 1301->1209 lines and isolates testable pure logic. The rest of
  LineEditor is left cohesive by design (heavy shared editor state). No behaviour
  change.

## 0.236.0 (2026-06-06) - Shell.active_parser property + Shell.add_history() (§1.1 E)
- Add a public `Shell.active_parser` property (get/set) and `Shell.add_history()` method, and route all external callers through them instead of reaching into the private `_active_parser` field or walking `interactive_manager.history_manager.add_to_history`: source_processor, ast_debug, parser_experiment (`parser-select`), __main__, and print -s. Phase 2 study §1.1. No behaviour change.

## 0.235.0 (2026-06-06) - Drop ineffective shell.variables[] mutation in rc_loader (§1.1 C)
- rc_loader's $0 save/restore assigned `shell.variables['0']`, but `state.variables` is a snapshot dict so the writes were no-ops. Remove the dead block — eliminating the direct state-dict mutation flagged in §1.1 — with no behaviour change (rc files already ran in the shell's own $0 context).

## 0.234.0 (2026-06-06) - TrapManager.get_handler() instead of reaching into trap_handlers (§1.1 B)
- Add `TrapManager.get_handler(signal_spec)` and use it in `SignalManager` instead of reaching into `trap_manager.state.trap_handlers`. Phase 2 study §1.1. No behaviour change.

## 0.233.0 (2026-06-06) - Public array accessors instead of ._elements reaches (§1.1 A)
- Add narrow public accessors to the array types — `IndexedArray.next_index()`, `IndexedArray.__contains__`, `AssociativeArray.__contains__` — and route the external callers through them instead of reaching into `._elements`: array append (`executor/array.py`), declare indexed→assoc conversion (`function_support.py`, now via `isinstance`+`indices()`/`get()`), and `[[ -v arr[i] ]]` membership (`test_evaluator.py`). Phase 2 study §1.1. No behaviour change.

## 0.232.0 (2026-06-06) - Remove dead QuoteParsingContext methods (lexer)
- Remove the unused `QuoteParsingContext.parse_quote_at_position` (0 callers; also carried a `parser._create_literal_part` private reach) and `get_quote_rules` (0 callers). `is_quote_character` is kept (used by the lexer). Phase 2 study §1.4. No behaviour change.

## 0.231.0 (2026-06-06) - Remove dead visitor state/stubs (arithmetic-suppression toggle, curl|sh stub)
- Remove never-enabled validator state: `_in_arithmetic_context` / `_in_test_context` toggles, the `ignore_undefined_in_arithmetic` config field, and their always-False branches (the arithmetic-suppression feature was never wired on). Remove the SecurityVisitor `_is_piped_to_shell` permanent-False stub and its never-firing curl/wget-piped-to-shell check. Phase 2 study §1.4. No behaviour change (the removed branches were unreachable). `SecurityIssue.node` is kept (plausible result-object API).

## 0.230.0 (2026-06-06) - Remove dead scripting scaffolding (base.execute, forwarders, expansion_manager)
- Remove the never-invoked abstract `ScriptComponent.execute` and the four dead subclass `execute` forwarders (ScriptExecutor/ShebangHandler/SourceProcessor/ScriptValidator) — callers use the concrete domain methods (run_script, execute_with_shebang, execute_from_source, validate_script_file) directly. Drop the unused `ScriptComponent.expansion_manager`. Phase 2 study §1.4. No behaviour change.

## 0.229.0 (2026-06-06) - Remove dead state fields & unreachable branch (core/interactive/executor)
- Remove unused dead state: `ShellState._original_signal_handlers`, `SignalManager._interactive_mode` (write-only) and its never-called `get_sigchld_fd()`, and the unreachable `CommandList` branch in `ExecutorVisitor.generic_visit` (no such AST node). Dead-code cleanup from Phase 2 study §1.4. No behaviour change.

## 0.228.0 (2026-06-06) - Remove dead HeredocHandler + _saved_fds (io_redirect)
- Remove the never-called `HeredocHandler` class (`io_redirect/heredoc.py`) and its import/instantiation in IOManager — heredoc content is handled by `FileRedirector._redirect_heredoc`. Also drop the unused `IOManager._saved_fds` attribute. Dead-code cleanup from Phase 2 study §1.4. No behaviour change.

## 0.227.0 (2026-06-06) - Public cross-builtin helpers (study #21)
- Promote the builtin methods reached across components to public API:
  `TestBuiltin.evaluate_test` / `evaluate_unary` (used by `[` and the executor's
  test evaluator), `ParserConfigBuiltin.set_mode` (used by `parser-select`), and
  `PrintfBuiltin.process_format_string_posix` (used by `print`). Removes the
  builtins-call-siblings'-privates leak tracked as Phase 2 study finding #21.
  No behaviour change.
- This closes the last of the five private-API-leak items from the Phase 2
  architecture study (#14, #15, #18, #20, #21 now all resolved).

## 0.226.0 (2026-06-06) - Public WordBuilder decomposition API (study #20)
- Promote `WordBuilder._has_decomposable_parts` and `_token_part_to_word_part`
  to public `has_decomposable_parts` / `token_part_to_word_part`. The combinator
  parser now builds the shared Word AST via public API instead of reaching into
  recursive-descent privates (Phase 2 study finding #20). No behaviour change.

## 0.225.0 (2026-06-06) - Slim builtin-redirection setup (study #18)
- Refactor `IOManager.setup_builtin_redirections`: extract the triplicated
  "output fd -> file" branch (`>`, `>>`, `>|`) into a shared
  `_redirect_builtin_output_file` helper (swap sys.stdout/stderr for fd 1/2,
  delegate fd>=3 to FileRedirector), and document why the `>&` 2>&1 / 1>&2 cases
  swap Python stream objects while other dups go to the fd level. Addresses the
  oversized/duplicated `setup_builtin_redirections` finding (#18). No behaviour
  change. (The unrelated pre-existing `builtin >&2 2>file` "lost sys.stderr"
  quirk is untouched.)

## 0.224.0 (2026-06-06) - Public expansion helpers (study #15)
- Promote `ExpansionManager._expand_expansion` and `_process_dquote_escapes` to
  public `expand_expansion` / `process_dquote_escapes`. The executor's
  assignment-value builder now uses the public API instead of reaching into
  private methods (Phase 2 study finding #15). No behaviour change.

## 0.223.0 (2026-06-06) - First-class in_forked_child state (study #14)
- Promote the private `ShellState._in_forked_child` to the public, always-present
  `ShellState.in_forked_child`. Readers across builtins/executor/expansion now
  access it directly instead of via defensive `hasattr`/`getattr`, removing the
  private-API leak tracked as Phase 2 study finding #14. No behaviour change.

## 0.222.0 (2026-06-06) - Promote array-element setter to public API
- Internal cleanup (no behaviour change): the nameref array-element write path
  added in 0.221.0 reached into a private `VariableExpander._set_var_or_array_element`
  from the scope manager. That helper is now the public
  `VariableExpander.set_var_or_array_element()` / `ExpansionManager.set_var_or_array_element()`,
  so the scope manager routes subscripted nameref writes through public API
  instead of a private method (avoids adding a new instance of the private-API /
  layering smells tracked in the Phase 2 architecture study).
- Refreshed `docs/reviews/codebase_study_2026-06-05_phase2_architecture.md` to
  reflect review against v0.221.0.

## 0.221.0 (2026-06-06) - Namerefs Phase 2: array-element targets
- **Namerefs whose target is an array element** now work, e.g.
  `arr=(p q r); declare -n e=arr[1]`:
  - read-through (`$e` → `q`, `${e^^}`, `${#e}`) and write-through
    (`e=Q` sets `arr[1]`); associative-array elements too (`declare -n e=m[k]`);
    `local -n el="a[0]"` pass-by-reference into a function.
  - `${!e}` yields the subscripted target name (`arr[1]`).
  - Implemented by resolving the nameref *name* at the expansion read helpers
    (so a subscripted target flows into the existing array-element branch) and by
    delegating subscripted writes from `set_variable` to the array-element setter.
  - Minor documented difference: bash's `${#e}` returns 0 for a
    nameref-to-element (a bash quirk); psh returns the element value's length.

## 0.220.0 (2026-06-06) - Name references (declare -n / local -n), Phase 1
- **Namerefs** with scalar targets, matching bash:
  - `declare -n ref=target` / `local -n ref=$1` create a name reference.
  - Read-through (`$ref` → target's value) and write-through (`ref=v` sets the
    target, creating it if unset); nameref chains resolve transitively.
  - `local -n` provides pass-by-reference into functions.
  - `unset ref` unsets the *target*; `unset -n ref` unsets the nameref.
  - `${!ref}` yields the target *name*; `declare -p ref` prints `declare -n ref="target"`.
  - Self-references (`declare -n r=r`) are rejected; cycles are guarded.
  - Deferred target: `declare -n r; r=x` sets r's target to x.
- **`${!var}` indirect expansion** (scalar) is now implemented as part of this:
  for a non-nameref, `${!var}` yields the value of the variable named by `$var`.
- Resolution hooks live at the scope-manager read/write chokepoints
  (`get_variable`/`set_variable` via a new `resolve_nameref_name`), with
  introspection paths (`declare -p`, `${var@a}`, `unset -n`) using raw lookup.
- Not yet supported (Phase 2): namerefs whose target is an array element
  (`declare -n e=arr[1]`).
- Added `tests/unit/core/test_nameref.py` (27 tests, incl. bash parity); the
  previously-xfail `test_declare_nameref_attribute` now passes. Refreshed the
  differences-from-bash chapter.

## 0.219.0 (2026-06-06) - let builtin
- **`let arg [arg ...]`** evaluates arithmetic expressions, equivalent to
  `((arg))` for each argument. Side effects apply (`let x=5+3`, `let ++x`,
  `let "x+=2"`). Exit status is 0 when the last expression is non-zero, 1 when
  it is zero or on an invalid expression; no arguments → "expression expected"
  (exit 1). Reuses the shared arithmetic evaluator.
- Added `tests/unit/builtins/test_let.py` (22 tests, incl. bash parity).
  Refreshed the differences-from-bash chapter.

## 0.218.0 (2026-06-06) - mapfile / readarray builtin
- **`mapfile` (alias `readarray`)** reads lines from input into an indexed
  array, matching bash:
  - `-t` strip the trailing delimiter; `-d delim` use a custom delimiter
    (first char; empty = NUL); `-n count` read at most COUNT lines;
    `-O origin` assign from index ORIGIN without clearing the array;
    `-s count` skip leading lines; `-u fd` read from a file descriptor.
  - Default array is `MAPFILE`; clustered flags (`-tn2`) work; an unset/extra
    second argument is ignored (bash-compatible); the `-C`/`-c` callback
    options are not supported.
- `type` now recognises aliased builtin names (so `type readarray` reports a
  shell builtin), via `BuiltinRegistry.has()` instead of the primary-name list.
- Added `tests/unit/builtins/test_mapfile.py` (26 tests, incl. bash parity).
  Refreshed the differences-from-bash chapter.

## 0.217.0 (2026-06-06) - Parameter transformation operators ${var@OP}
- **`${var@OP}` transformation operators** implemented for scalars, arrays, and
  positional parameters, matching bash:
  - `@Q` quote for reuse as input (single-quote form; `$'...'` for control
    chars; unset → empty)
  - `@U` / `@u` / `@L` uppercase-all / uppercase-first / lowercase-all
  - `@E` expand ANSI-C backslash escapes (`\n`, `\t`, `\xHH`, …)
  - `@P` prompt-string expansion (`\u`, `\h`, …)
  - `@A` assignment/`declare` form (`x='a b'`, `declare -i n='5'`,
    `declare -a a=([0]="x" [1]="y z")`)
  - `@a` attribute-flag letters (e.g. `airx`)
  - `${arr[@]@OP}` applies per element; `${arr[@]@A}` emits a full `declare`
    statement; `${@@Q}` quotes each positional parameter.
- Parsed in both the recursive-descent Word AST path (`WordBuilder`) and the
  string path (`parameter_expansion.parse_expansion`); the trailing-position
  check keeps the array-subscript `@` in `${arr[@]}` from being mistaken for a
  transform.
- Not implemented: `@K` / `@k` (associative key/value display).
- Added `tests/unit/expansion/test_parameter_transform.py` (31 tests, incl. a
  bash-parity parametrization). Refreshed the differences-from-bash chapter.

## 0.216.0 (2026-06-06) - Brace expansion of expansion items; arithmetic fd-dup targets
- **Brace list expansion now carries expansion items** (`{$((1)),$((2)),$((3))}`
  → `1 2 3`; also `{$(cmd),...}` and `{$a,$b}`). Brace expansion is textual and
  runs before parameter/command/arithmetic expansion, so the token-level
  `TokenBraceExpander` now treats `$((..))`/`$(..)`/`$var` tokens as opaque units
  in a composite run instead of refusing to expand any list containing a `$`.
  The one case the token model cannot reproduce — bash re-forming a variable
  *name* out of brace text (`$x{1,2}` → `$x1 $x2`) — is detected and left
  unexpanded (documented divergence). Brace *ranges* with `$`-endpoints stay
  literal, matching bash.
- **Arithmetic/variable fd-duplication targets** (`>&$((1+1))`, `2>&$fd`,
  `<&$n`). The lexer emits a bare `N>&`/`>&`/`<&` operator when the target is an
  expansion; the parser keeps the expansion as the dup target; and
  `FileRedirector._resolved` expands it to an integer fd at execution time
  (raising "ambiguous redirect" for a non-numeric value). A shallow-copy
  resolution keeps the AST node unmutated so re-execution in a loop re-resolves.
- Added regression tests (brace expansion with arithmetic/command-sub/variable
  items and name-fusion divergence; dynamic fd-dup targets). Both were previously
  documented `xfail`s in the advanced-arithmetic suite, now passing.

## 0.215.0 (2026-06-06) - Stop hiding defects in executor error guards
- **Executor broad-except guards** (study triage #13) — tightened the executor's
  `except Exception` boundaries so internal defects are no longer silently
  reported as `psh: <msg>` (exit 1):
  - The two `set_variable` guards in `command.py` (standalone and command-prefix
    assignments) now catch only `ReadonlyVariableError` instead of any exception.
  - The genuine last-resort guards (simple-command boundary, both builtin-exec
    strategies, function-body boundary) keep the broad catch for REPL resilience
    but now print the traceback under `--debug-exec`, matching the
    ProcessLauncher and source-processor guards. Control-flow exceptions still
    propagate.
- Added regression tests (readonly assignment paths; an injected builtin defect
  is reported without a traceback by default and with one under `--debug-exec`).
  This was the last of the study's high/medium triage items.

## 0.214.0 (2026-06-06) - Narrow array-index exception handling
- **Stop swallowing defects in array subscripts** (study triage #4) — the
  remaining four array-index sites in `expansion/variable.py` (subscript
  read/set, new-array creation, and `_param_is_set`) caught a bare
  `except Exception` around `evaluate_arithmetic`, defaulting the index to 0 and
  masking any non-arithmetic defect. Narrowed all four to `except ArithmeticError`,
  matching the sites already fixed in the v0.x safety pass. Invalid *arithmetic*
  subscripts are still handled gracefully (→ index 0); genuine defects now
  propagate. Added 5 regression tests.
- Study triage #5 (broad except relabeling control-flow as "unexpected error" in
  `scripting/source_processor.py`) was verified already resolved — `break`/
  `continue` outside a loop and `return` outside a function produce their proper
  messages, and the inner handler catches only `LoopBreak`/`LoopContinue`.

## 0.213.0 (2026-06-06) - Remove dead OptionHandler policy methods
- **Trimmed `OptionHandler`** (study triage #16) — two of its four methods were
  dead with zero callers because the executor implements those policies itself:
  `should_exit_on_error` (errexit is enforced structurally at the statement-list
  level) and `get_pipeline_exit_code` (pipefail is computed inline in the
  pipeline executor). Removed both; kept the two live methods,
  `check_unset_variable` (nounset) and `print_xtrace` (set -x, used via the
  executor since v0.205.0). All four option behaviors (nounset/xtrace/errexit/
  pipefail) verified unchanged.

## 0.212.0 (2026-06-06) - Trim dead ExecutionContext factories and fields
- **Removed dead `ExecutionContext` machinery** (study triage #17) — about half
  the module was unused: factory methods `subshell_context`, `loop_context_enter`,
  `function_context_enter`, `with_pipeline_context`, `with_background_job`, and
  `should_use_print`, plus fields `in_subshell`, `pipeline_context` (write-only),
  `background_job`, `suppress_function_lookup`, and `exec_mode`. Kept the four
  live fields (`in_pipeline`, `in_forked_child`, `loop_depth`, `current_function`)
  and four live methods (`fork_context`, `pipeline_context_enter`, `in_loop`,
  `in_function`). `loop_depth`/`current_function` are mutated in place, which is
  why the matching `*_context_enter` factories were dead. context.py 189 -> 60
  lines; behavior unchanged (covered by the existing executor suite).

## 0.211.0 (2026-06-06) - Remove the vestigial readline CompletionManager
- **Dropped `CompletionManager`** (study triage #7) — the readline-based tab
  completion manager was dead: `setup_readline()` registered a readline completer,
  but psh reads interactive input through its own `LineEditor` (raw mode) with its
  own `CompletionEngine`, so the readline completer was never invoked and the
  `complete_*` / `get_completions` methods had no callers. Removed the class
  (`completion_manager.py`) and all wiring (`base.py`, `repl_loop.py`,
  `interactive/__init__.py`, docs). Tab completion is unaffected — it lives in
  `LineEditor`/`CompletionEngine`. ~142 fewer lines.

## 0.210.0 (2026-06-06) - Flush buffered output in command-substitution children
- **`$(...)` now captures stream-writing builtins** — the command-substitution
  child exits with `os._exit()`, which does not flush Python-level buffers. So a
  builtin that writes to the Python stream rather than `os.write` (e.g.
  `parser-mode`, `parser-config`, `debug`) produced empty output inside
  `$(...)`, while `echo` (fd-level) worked. Added a buffer flush before
  `os._exit` in `expansion/command_sub.py`, mirroring the ProcessLauncher
  child-exit flush. Only command substitution was affected — pipelines,
  subshells, and background jobs already flush.
- Added subprocess-based regression tests (the forked child's `sys.stdout` under
  pytest in-process capture is not the pipe, so the real fd-1 path must be
  exercised via a subprocess).

## 0.209.0 (2026-06-06) - Fix formatter output for subshells, brace groups, [[ ]]
- **Formatters no longer emit `# Unknown node` for real node types** (study
  triage #6). Two formatters were affected:
  - `FormatterVisitor` (behind `psh --format`) had no `visit_SubshellGroup` /
    `visit_BraceGroup`, so subshells and brace groups fell through to
    `generic_visit` and produced a `# Unknown node: ...` comment instead of
    shell. Added both (shared `_format_group` helper) → `( ... )` / `{ ... }`.
  - `ShellFormatter` (used by `type` / `declare -f`) was missing `SubshellGroup`,
    `BraceGroup`, and `EnhancedTestStatement`; added them plus a recursive
    `_format_test_expression` for `[[ ]]` (unary/binary/negated/compound).
- Output is valid shell and round-trip stable (format → parse → format is
  idempotent). Added 33 tests across both formatters, which previously had no
  direct coverage.

## 0.208.0 (2026-06-06) - Remove the test-only pipeline path (eval_test_mode)
- **Dropped `eval_test_mode`** (study triage #1) — the pipeline executor carried
  an entire alternate, no-fork execution path (`_execute_simple_pipeline_in_test_mode`
  and helpers, ~161 lines) gated on `state.eval_test_mode`, plus matching branches
  in `echo`/`printf`/`pwd` (`io.py`) and `print`. That flag was enabled by exactly
  one test and never in production, so the path was test-only code embedded in the
  production executor (and its behavior diverged from the real forking path).
- The one dependent test (`test_eval_pipe`) now uses `capfd`, capturing the real
  forking pipeline at the file-descriptor level. The flag, the no-fork pipeline
  cluster, the `io.py`/`print_builtin.py` branches, and the `state.py`
  property/methods are removed. Production behavior is unchanged (it never set the
  flag); net ~187 fewer lines.
- (The narrow `is_pytest` terminal-control guard in the forking path is a
  separate, legitimate no-controlling-terminal guard and was left in place.)

## 0.207.0 (2026-06-06) - Route builtin output through shell.stdout
- **Builtins no longer use bare `print()`** (study triage #2) — `parser-config`/
  `parser-mode`, `debug`/`debug-ast`, `kill -l`, `jobs`/`fg`/`bg`/`wait`,
  `cd -`, and `parse-tree`/`show-ast` wrote output with bare `print()`, sending
  it to `sys.stdout` instead of `shell.stdout`. That leaked output past
  in-process capture / redirection (e.g. builtin-to-builtin pipelines in test
  mode, which capture the first command via `shell.stdout`). All 47 such calls
  across the six affected builtins now pass `file=shell.stdout`; `kill -l` gained
  `shell` threading so its lister can reach the stream.
- Behavior-preserving for fd-level cases (`>`, external pipelines) where
  `shell.stdout` already aliases `sys.stdout`. (Separately noted, not fixed here:
  command substitution loses buffered builtin output across `os._exit` — a flush
  issue independent of stream routing.)
- Added `tests/unit/builtins/test_builtin_stdout_routing.py` (6 tests) asserting
  output lands on `shell.stdout` and does not leak to `sys.stdout`.

## 0.206.0 (2026-06-06) - Fix two analysis-visitor bugs (until loops, brace groups)
- **`until` loops now counted in metrics** — `MetricsVisitor` had `visit_WhileLoop`
  but no `visit_UntilLoop`, so `until` loops were not counted in `total_loops`
  (or `loop_types`). Added `visit_UntilLoop` mirroring `visit_WhileLoop`; an
  `until` loop now counts identically to a `while` loop.
- **Brace group in a pipeline no longer crashes analysis** — `--metrics` /
  `--security` on e.g. `{ echo a; } | tee log` raised `'StatementList' object is
  not iterable`. This was resolved by the v0.205.0 traversal unification; this
  release adds regression tests pinning it (metrics/security no longer crash and
  the group's inner commands are counted).
- Both fixes covered by new tests in `tests/unit/visitor/test_analysis_visitors.py`.

## 0.205.0 (2026-06-06) - Unify analysis-visitor traversal and shared checks
- **Visitor traversal unified (Phase 2 study §1.3, #19)** — the metrics,
  security, and linter visitors each had their own `generic_visit`. Two walked
  only one of `items`/`statements`/`body` (silently skipping children of any
  other shape); the third did a dataclass-field walk. All three now use one
  shared traversal in `psh/visitor/traversal.py` (`iter_child_nodes` /
  `visit_children`).
- **Latent bug fixed** — because the metrics/security traversal under-walked,
  nodes without a dedicated visitor (e.g. `until` loops) had children skipped:
  `until [ -e f ]; do …` did not count the `[ -e f ]` condition command. The
  shared traversal is a strict superset of the old coverage (findings/counts can
  only become more complete, never lost); `until`-loop conditions are now
  traversed like `while`-loop conditions. (Two unrelated pre-existing analysis
  bugs remain noted but unfixed: `until` not counted in `total_loops`, and
  `--metrics`/`--security` crashing on brace-group pipelines.)
- **Shared check vocabulary (B-light)** — the unquoted-expansion predicate
  (`has_unquoted_expansion`, in new `analysis_helpers.py`) and the test-operator
  classifications (`NUMERIC_COMPARISON_OPERATORS`, `TEST_OPERATORS`, in
  `constants.py`) replace inline copies across the security/validator/linter
  visitors. Each visitor keeps its own policy (contexts, severities, messages);
  only the shared predicate/data is centralized.
- **Coverage** — added 11 tests for the previously-untested analysis visitors
  (traversal, metrics, security).

## 0.204.0 (2026-06-06) - Unify command-position classification across lexer passes
- **Command-position tracking unified (Phase 2 study §1.3, Tier C)** — the lexer
  (which tracks command position during tokenization, on `WORD`-valued keywords)
  and the keyword normalizer (which tracks it afterward, on typed keywords) are
  two distinct passes, but both classify which tokens return to command
  position. That classification now lives once in `psh/lexer/command_position.py`
  (`STATEMENT_SEPARATORS`, `CASE_TERMINATORS`, `RESET_TO_COMMAND_POSITION`,
  `COMMAND_GROUP_OPENERS`); both passes reference it.
- **Dead code removed** — the lexer's command-position set listed reserved-word
  token *types* (`IF`/`WHILE`/`THEN`/…) it can never receive (keywords are still
  `WORD` tokens during tokenization; it relies on a value-based check). These
  were removed. Behavior-preserving: token streams verified identical across a
  control-structure/case/function/`[[`/heredoc corpus.

## 0.203.0 (2026-06-06) - Unify glob→regex conversion; fix leading `]` in classes
- **Glob→regex conversion unified (Phase 2 study §1.3, Tier C)** — the
  parameter-expansion pattern operators (`#`/`##`/`%`/`%%`/`/`/`//`) and the
  extglob matcher carried two char-by-char glob→regex converters. They now share
  one implementation: `psh/expansion/extglob.py` exposes `glob_to_regex_body()`
  (the recursive converter gained an `extglob` toggle so it also handles plain
  globs), and `PatternMatcher.shell_pattern_to_regex` delegates to it while
  keeping its own anchoring contract. ~48 fewer lines in `parameter_expansion.py`.
- **Leading `]` in a character class (bug fix)** — a class beginning with `]`
  (e.g. `[]]`, `[]ab]`) is a literal-member class in POSIX; the former inline
  converter produced an invalid empty class and pattern operators raised
  "unterminated character set". Now handled correctly (verified against bash).
  6 regression tests added.

## 0.202.0 (2026-06-06) - Unify heredoc detection; fix `<<-` indented delimiter
- **Heredoc detection unified (Phase 2 study §1.3, Tier C #11)** — the
  script/`-c`/stdin path and the interactive multiline path carried two diverged
  copies of `_has_unclosed_heredoc`/`_is_inside_expansion` with *different* bugs:
  the interactive copy matched `<<` inside a `<<<` here-string (hanging waiting
  for a delimiter), and the script copy treated `<< 2` in bare `(( x << 2 ))`
  arithmetic as a heredoc (masked only by its caller's `contains_heredoc`
  guard). Both now use one authoritative implementation in
  `psh/utils/heredoc_detection.py` (`has_unclosed_heredoc`, `is_inside_expansion`)
  that rejects here-strings, excludes `<<` inside `$((`/bare `((`/`$(`/backticks,
  and handles `<<-` tab stripping and multiple/mixed heredocs. 20 new unit tests;
  net ~64 fewer lines.
- **`<<-` indented closing delimiter (bug fix)** — `<<-` now strips leading tabs
  from the *delimiter* line as well as the content (bash behavior). Previously a
  tab-indented delimiter (e.g. `\tEOF`) was never matched, so the heredoc body
  was silently lost. Fix in `psh/lexer/heredoc_collector.py`; regression test
  added.

## 0.201.0 (2026-06-06) - De-duplicate divergent reimplementations (Tier A + B)
- Consolidated same-logic copies flagged in the Phase 2 architecture study
  (§1.3). Behavior-preserving except for one bug fix noted below.
- **History-reference detection** — one `HISTORY_REFERENCE_RE` +
  `contains_history_reference()` in `history_expansion.py` replaces four
  byte-identical inline regex copies (source_processor ×2, multiline_handler,
  line_editor).
- **`parser-config` feature map** — extracted `_FEATURE_MAP` / `_POSITIVE_OPTIONS`
  class constants and a shared `_set_feature()`, collapsing two duplicated
  10-entry maps and their near-identical enable/disable bodies.
- **Foreground-job teardown** — new `JobManager.finish_foreground_job()` replaces
  the duplicated terminal-restore if/else in `pipeline.py` and `strategies.py`.
- **dirs/pushd/popd `~` display (bug fix)** — the three `_format_directory`
  copies are unified into one `format_directory_for_display()`. The two naive
  pushd/popd copies used `startswith(home)`, which mangled a sibling like
  `/home/userfoo` into `~foo`; the unified helper uses `home + os.sep`. Added
  regression tests.
- **xtrace** — executor `_print_xtrace` now delegates to
  `OptionHandler.print_xtrace`, making core the single source of truth (and
  reviving the previously-dead canonical method).

## 0.200.0 (2026-06-06) - Positional/array slicing and EXIT-trap edge cases
- **`${@:off:len}` / `${*:off:len}` / `${arr[@]:off:len}` slicing** — these now
  select elements with bash semantics instead of doing substring on the joined
  string (the old behavior only happened to match for `${@:n}` without a length).
  A shared `_slice_sequence()` helper applies arithmetic offset/length, treats a
  negative offset as counting from the end, and reports a negative length as an
  error (`@`/`*`/array slices, unlike scalar substrings, disallow from-the-end
  lengths). Positional slices index as `[$0, $1, …]` so `${@:0}` includes `$0`.
  Both the AST and string expansion paths route through the one helper.
- **Parser: `${arr[@]:1:-1}` no longer mis-parses** — the `:-` inside a slice
  operand was being matched as the use-default operator. Any operator following a
  closed array subscript is now left to the string-path parser, which resolves
  the subscript before applying the operator (also covers `${arr[0]:-def}`,
  `${arr[i+1]:-x}`, case-mod patterns, etc.).
- **EXIT trap now runs for `-c`, piped stdin, and interactive Ctrl-D** — it
  previously fired only via an explicit `exit` builtin or at the end of a script
  file. `execute_exit_trap()` is now idempotent so it fires exactly once across
  all exit paths.
- **Tests** — the four tracked edge xfails (EXIT trap, positional slice length,
  variable offset, negative array offset) are fixed and promoted to passing
  conformance cases, plus regression coverage for slice/default disambiguation
  and trap single-firing. Bash conformance: 197/199 (99.0%).

---

Entries older than v0.200.0 are archived in
`docs/archive/CHANGELOG_history.md`.
