# I/O Redirection Subsystem Appraisal — 2026-07-07

## Scope

A fresh, probe-verified appraisal of psh's I/O redirection subsystem at
`main` @ `968a3af4` (v0.662.0), graded for:

- correctness against Bash 5.2 (`/opt/homebrew/bin/bash`, 5.2.26);
- POSIX and Bash redirection semantics;
- robustness (fd leaks, partial-failure rollback, zombie reaping);
- testability, clarity, and documentation accuracy.

Modules covered:

- `psh/io_redirect/manager.py` — `IOManager`, the two-universe orchestrator;
- `psh/io_redirect/file_redirect.py` — `FileRedirector`, the fd-universe backend
  plus the shared redirect primitives;
- `psh/io_redirect/planner.py` — `RedirectPlanner`/`RedirectPlan`, the shared
  resolve→expand→procsub planning phase;
- `psh/io_redirect/process_sub.py` — `ProcessSubstitutionHandler`,
  `ProcessSubstitutionResource`, and the macOS FIFO write-side fallback;
- `psh/io_redirect/fd_remap.py` — collision-safe fd remapping for forked children;
- the executor seam (`psh/executor/command.py`, `strategies.py`,
  `control_flow.py`, `subshell.py`, `function.py`) where redirections are
  dispatched.

Operators and behaviors exercised: `>`, `>>`, `<`, `<>`, `>|`, `N>`, `N>&M`,
`&>`/`&>>`, `>&`/`<&`, `N>&-`/`N<&-`, the move form `N>&M-`, csh-style `>&word`;
`noclobber` (`set -C`, regular/symlink/dangling/device targets); heredocs
(`<<`, `<<-`, quoted vs unquoted delimiter, expansion/command-sub/arith inside
bodies, explicit-fd `N<<`, large >64 KB bodies); here-strings (`<<<`, explicit
fd, quoting); process substitution `<(…)`/`>(…)` (read side, write-side FIFO,
nesting, loop input, function-argument scoping, cleanup/leak); per-command fd
save/restore; permanent fd redirection (`exec N>…`, `exec <…`, close, restore,
all-or-nothing rollback); redirection ordering; and the error paths (bad fd,
unwritable dir, EISDIR, ambiguous redirect, EACCES-style).

## Method

Every behavioral claim below was verified differentially: the same script was
run in Bash 5.2 and psh, each in its own process group (killed on timeout so a
runaway oracle can never leak a CPU orphan), with psh imported from this
worktree (`python -c "import psh.__main__"` → the worktree path; cwd pinned to
the repo). Permanent-fd probes (`exec >file`, `exec 3>&1`) ran psh in a
**subprocess** so they could never rewrite the harness's own descriptors.
Roughly 100 differential cases were run across five batteries (operators,
permanent-exec, semantics, advanced, and targeted single probes). The probe
harness and case files live under `tmp/ioredir/`.

Reproductions cite exact `file:line`. Findings are graded HIGH/MED/LOW and
labelled **CONFIRMED** (reproduced in both shells) or **PLAUSIBLE**.

## Status of the 2026-06-13 review

The prior review (`docs/reviews/redirection_io_architecture_review_2026-06-13.md`)
is now **substantially superseded**. Its two live test failures and most of its
nine "Uglies" have been fixed in the intervening ~150 releases. Re-verified
against current `main`:

| 2026-06-13 item | Status now | Evidence |
| --- | --- | --- |
| **Failure 1** — dynamic dup to `/dev/stdout` (`exec 3>/dev/stdout; echo hi >&$((1+2))`) | **FIXED** | Both shells: `hi`, rc 0, MATCH |
| **Failure 2** — write-side procsub `tee >(cat > f)` EPERM on `/dev/fd/N` | **FIXED** (v0.370.0 FIFO fallback) | Both shells write `data` to the file, MATCH |
| **Ugly 1** — redirect dispatch duplicated across 4 paths | **Partially addressed** | Shared *planning* extracted to `planner.py` (v0.375.0); the four *apply* backends still exist (inherent to the two-universe model) — see LOW-1 |
| **Ugly 2** — explicit input-fd (`5<file`) diverges across paths | **FIXED** | `redirect_input_from_file(target, redirect)` + `_heredoc_fd`; explicit-fd external/`read -u`/heredoc probes all MATCH |
| **Ugly 3** — `IOManager` reaches into `FileRedirector` privates | **FIXED** (v0.409.0) | Shared primitives are now a documented public surface (no leading underscore) |
| **Ugly 4** — procsub ownership is a raw int + comments | **FIXED** (v0.375.0) | `ProcessSubstitutionResource` with `close_parent_fd_for_redirect`/`hand_off_to_scope` |
| **Ugly 5** — procsub fd leaks on redirect-setup failure | **FIXED** | `plan.close_procsub(applied=…)` in `finally`; `cat <(echo x) >/bad/f` leaves fd set `0 1 2` identical to bash — no leak |
| **Ugly 6** — permanent stdin redirect doesn't rebind `sys.stdin` | **FIXED** (v0.461.0) | `_rebind_input_stream` (`file_redirect.py:594`); `exec <f; read; head; read` all MATCH. **But** a *different* residual leak in the close+reopen path survives — see MED-1 |
| **Ugly 7/8** — builtin two-universe dispatch is prose, child paths duplicate diagnostics | **Improved** | `format_redirect_error`/`_redirect_error_name` centralize the message shape; dispatch is still per-backend code (LOW-1) |
| **Ugly 9** — `/dev/fd` assumed universal for procsub | **FIXED** (v0.370.0) | Read side uses `/dev/fd/N`; write side uses a named FIFO on macOS |

Net: the old review's structural recommendations (shared `RedirectPlan`,
explicit `ProcessSubstitutionResource`, an fd-remap utility, a portability
strategy for write-side procsub) were **implemented**. It should be treated as
historical; this appraisal supersedes it.

## Executive Judgment

This is the strongest subsystem I have appraised in psh. Across ~100
differential cases, the **only** behavioral divergence from Bash beyond the
deliberate, universal `psh:` diagnostic prefix is a single narrow edge case
(MED-1). fd-leak and rollback invariants were verified clean by direct fd-set
comparison, not merely asserted. The two-universe model (fd vs Python stream)
is correct, the frame-based builtin redirection is transactional and nesting-
safe, process-substitution ownership is now explicit, and the documentation is
genuinely excellent.

There are **no HIGH findings and no release blockers.** The one confirmed bug is
a MEDIUM data-leak in an unusual `exec`-close-then-reopen sequence. The residual
complexity — and the place the bug lives — is the permanent-`exec` stream
rebinding logic, which is the most intricate code in the package.

Overall grade: **A−**.

## Grades

| Dimension | Grade | Assessment |
| --- | --- | --- |
| Correctness vs Bash 5.2 | A− | ~100 probes; every case matches modulo the `psh:` prefix except MED-1 |
| POSIX/Bash semantics | A− | noclobber (incl. symlink/dangling/device), heredoc quoting, ordering, `<>`, move form, ambiguous-redirect all correct |
| Robustness (fd leaks / rollback) | A | No fd leaks (verified via `/dev/fd`); `exec` rollback is all-or-nothing; procsub ownership explicit; no zombies/FIFO-dir leaks |
| Testability | A− | 390 test functions across 37 redirect files, bash-pinned nesting battery; but the MED-1 path is untested |
| Clarity / maintainability | B+ | Superb docstrings; residual complexity is four apply-backends and the permanent-exec stream juggling |
| Documentation accuracy | A− | Module docstrings and CLAUDE.md are outstanding; one now-inaccurate "heals it" claim (tied to MED-1) |

## What Is Strong

### The two-universe model is correct and is the documented centerpiece

`IOManager` (`manager.py:1-64`) draws the load-bearing distinction: external
commands inherit **kernel fds** (redirected after fork in
`setup_child_redirections`), while in-process builtins write through **Python
stream objects** (`sys.stdout`/`shell.stdout`), which under pytest/embedding may
be `StringIO` not backed by fd 1 at all. `setup_builtin_redirections` dispatches
each redirect to the right universe — and, crucially, applies **both** for the
fd-1/2 cases so a child a builtin spawns (`eval`/`source`/`command ext`)
inherits the redirect too. The interleave probe
(`exec >f; echo b1; /bin/echo e1; echo b2; /bin/echo e2`) produced
`b1 e1 b2 e2` in exact bash order — the shared open file description
(`_stream_sharing_fd`, `_dup_output_fd_for_children`) keeps one offset.

### Frame-based builtin redirection is transactional and nesting-safe

`BuiltinRedirectFrame` (`manager.py:175`) records everything one setup changed —
the pre-redirect stream snapshot (first-touch-wins), the fd-level saves, and
exactly the files opened — so `eval "echo one >&3" 3>&1`, `source f 3>&1`, and
mid-builtin trap handlers nest correctly (the pre-v0.302 manager-level lists
conflated them). Restore is order-aware and closes exactly the files setup
opened, never "whatever happens to be in `sys.stdout`" (which after `cmd 2>&1`
is the shell's real stdout). A setup failure part-way through rolls back only
its own frame.

### fd-level backups go high, and rollback is all-or-nothing

`_save_fd_high` (`file_redirect.py:410`) forces every temporary backup onto
fd ≥ 10 — matching bash — so a stale `sys.stdout` wrapper naming fd 1 after
`exec 1>&-` can't have a backup land under it. `apply_permanent_redirections`
(`file_redirect.py:623`) snapshots both fds and Python streams and, on any
failure in the list, restores the whole list: my `exec 3>f 4>/bad/g` probe left
fd 3 **closed** (`3: Bad file descriptor`) and `f` empty — bash-identical.

### Process-substitution ownership is explicit and leak-free

`ProcessSubstitutionResource` (`process_sub.py:204`) owns one substitution's
`(path, parent_fd, pid, cleanup_path)` with exactly two fates —
`close_parent_fd_for_redirect` (external/permanent) or `hand_off_to_scope`
(word-expansion and the in-process builtin path). Verified: `cat <(echo x)`,
nested `<( <( ) )`, loop input `< <(…)`, and function-argument `f <(…)` all
match bash; a redirect-setup failure after a procsub leaves no leaked fd; the
write-side FIFO leaves no `psh-psub-*` temp dir behind; `reap_pending`
(`process_sub.py:360`) only ever waits on recorded pids, so it can never steal
the job manager's status.

### The macOS write-side FIFO fallback is a real portability fix

`_create_write_process_substitution` (`process_sub.py:121`) uses a named FIFO
because reopening a write-only pipe through `/dev/fd/N` fails EPERM for external
consumers like `tee` on macOS — the exact 2026-06-13 Failure 2. The child
unlinks the FIFO once its read end is open (surviving unlink, POSIX), with a
5 s `SIGALRM` guard so an unopened path never blocks forever.

### `remap_fds` is a textbook two-phase algorithm

`fd_remap.py` solves the "source already sits on its destination" and
"remapping cycle" hazards (both surfacing only when fd 0/1/2 begin closed) by
relocating every source above all destinations before placing them —
close-on-exec on temporaries, inheritable on destinations, owned endpoints
closed exactly once, everything closed on failure. The 10-stage pipeline and
repeated-procsub fd-set probes confirm no leak.

### Documentation is a model for the rest of the codebase

The `manager.py` module docstring and `io_redirect/CLAUDE.md` explain *why* each
universe exists, the exact dispatch table, the nesting rationale, and the
deferred-close reasoning. This is the kind of prose that makes a hard subsystem
maintainable.

## Critical Findings (HIGH)

**None.** No release blocker, no fd leak, no crash, no rollback violation was
reproduced. The single confirmed correctness bug is MEDIUM.

## Medium Findings

### MED-1 (CONFIRMED): a builtin's buffered output leaks across `exec >&-` close + reopen

**Where:** `file_redirect.py:709-747` `_rebind_closed_output_stream`,
specifically the "no override" early return at `file_redirect.py:737-738`,
interacting with the stream rebind in `apply_permanent_redirections`
(`file_redirect.py:673-684`).

When a permanent `exec >&-` (or `2>&-`) closes fd 1/2 **and there was no prior
`exec >file` override**, the code deliberately leaves `sys.stdout` as the
natural `TextIOWrapper` still wrapping the now-closed fd — the docstring's
reasoning is that "a later fd-level reopen heals it, exactly as bash does."
But if an in-process builtin **writes** between the close and the reopen, its
bytes are buffered in that stale wrapper. The write's `flush()` correctly raises
EBADF (bash's `write error: Bad file descriptor` is emitted), but the buffered
bytes are **not discarded** — when the fd is later reopened and the wrapper is
displaced, those bytes survive and flush to the *reopened* destination at
interpreter shutdown.

**Repro (subprocess; builtin write, reopen via saved fd):**

```sh
exec 3>&1; exec >&-; echo LEAK; exec >&3 3>&-; echo end
```

| | stdout | stderr |
| --- | --- | --- |
| bash | `end` | `echo: write error: Bad file descriptor` |
| psh | `end`**`LEAK`** | `echo: write error: Bad file descriptor` |

**The "healing" reopen the comment claims is safe leaks too:**

```sh
exec 3>&1; exec 1>&-; echo LEAK; exec 1>&2; echo end >&2
# bash stderr:  <error>\nend
# psh  stderr:  <error>\nend\nLEAK      ← LEAK leaks onto fd 2
```

Confirmed with `printf` as well (`… printf LEAK …` → psh stdout `end`**`LEAK`**).
It is specifically the **in-process builtin** path: an external command
(`/bin/echo`) writes through the raw fd, gets EBADF immediately, buffers
nothing, and matches bash.

**Blast radius (bounded):** The leak requires the exact sequence *permanent
close of a standard fd with no prior `exec >file`* → *builtin write* → *reopen
of that fd*. The two paths that do **not** leak, verified:

- the **with-override** branch (`exec >f; exec >&-; echo …`) installs the
  `_ClosedStream` sentinel (`manager.py:293`), which raises EBADF without
  buffering — no leak, bash-identical;
- the **per-command** builtin close (`{ echo LEAK; } 1>&-`) also uses
  `_ClosedStream` — no leak (`A\nB`, bash-identical).

So this is a narrow, correctly-diagnosed-but-data-leaking edge, not a broad
output-integrity problem. It is **not** in the differences ledger
(`docs/user_guide/17_differences_from_bash.md`).

**Why the tests missed it:** `test_exec_permanent_redirect.py` exercises close
and reopen, but never *writes through a builtin while the std fd is closed and
then reopens it and inspects the reopened stream* — the invariant "bytes written
to a closed fd never reappear" is not in the matrix.

**Fix direction:** on `exec >&-`/`2>&-` of a natural (non-override) std fd,
either (a) install the `_ClosedStream` sentinel as the override path already
does, and make the fd-level reopen path replace the sentinel with a fresh
`_stream_sharing_fd` (so "healing" still works but no buffering wrapper is left
live); or (b) when rebinding fd 1/2 in `apply_permanent_redirections`, *discard*
(not flush) the displaced stale wrapper's buffer before dropping it. Update the
`_rebind_closed_output_stream` docstring's "heals it, exactly as bash does"
claim, which is inaccurate once a buffered builtin write intervenes.

## Low Findings

### LOW-1 (observation): four apply-backends still re-dispatch on `redirect.type`

The 2026-06-13 review's Ugly 1 is only partially closed. The *planning* phase
(`resolve_dynamic_dup` → `expand_redirect_target` → procsub) is now shared in
`planner.py`, but the *application* still lives in four separate type-dispatch
sites: `FileRedirector.apply_fd_plan` (external/temporary),
`apply_permanent_redirections` (exec), `IOManager.setup_builtin_redirections`
(builtins), and `setup_child_redirections` (forked children). This is largely
**inherent** to the two-universe model — each backend legitimately does
different things (raise vs `os._exit`, stream-swap vs pure fd) — and each is
well documented and tested, so this is a clarity/maintainability note, not a
defect. Adding a redirect form still means touching four dispatchers. A data-
driven per-form policy table (as the old review sketched) would help, but the
cost/benefit is marginal now that planning is shared.

### LOW-2 (platform, PLAUSIBLE): write-side procsub uses a FIFO + 5 s SIGALRM only on the fork-child path

`_create_write_process_substitution` (`process_sub.py:121`) is the macOS
workaround for `/dev/fd/N` write EPERM. On Linux, bash and psh can both use
`/dev/fd/N` write ends, so the FIFO path is macOS-divergent behavior that the
**local gate never exercises for Linux** (the nightly is the backstop). The
5 s `SIGALRM` "nobody opened the FIFO" guard installs a handler inside the
substitution child before the body runs; it is cleared before `run_child_shell`
executes the body, so a body that itself uses `SIGALRM` is not affected in the
common case — but this interaction is subtle and untested on Linux. Flagged as
platform-sensitive; not reproduced as a bug.

### LOW-3 (observation): the permanent-exec stream logic is the complexity hotspot

`_rebind_closed_output_stream`, `_snapshot_std_streams`, `_rollback_std_streams`,
and the `closed_dups` bookkeeping in `apply_permanent_redirections` are the most
intricate code in the package, tracking three parallel stream slots
(`sys`/`shell`/`state`) plus orphaned dups. It is exactly where MED-1 lives.
This is the highest-value target for the next simplification pass: a single
"std-stream binding" object that owns the fd, the wrapper, and the override
would make the close/reopen state machine explicit and testable.

## Recommended Improvement Plan

Campaign-sized, in priority order:

### Phase 1 — Fix the exec-close output leak (MED-1)

1. Make a permanent `exec >&-`/`2>&-` of a natural std fd install a sentinel (or
   discard the displaced wrapper's buffer on reopen) so a builtin write between
   close and reopen cannot resurface.
2. Correct the `_rebind_closed_output_stream` docstring.
3. Add a differential regression asserting the "bytes written to a closed std fd
   never reappear on the reopened stream" invariant, for both `echo` and
   `printf`, across (a) reopen via saved fd (`exec >&3`) and (b) the `exec 1>&2`
   "healing" reopen. Promote the probe to `tests/behavioral/golden_cases.yaml`.

### Phase 2 — Consolidate the permanent-exec stream binding (LOW-3)

Introduce one object owning the `(fd, wrapper, override)` triple for stdout,
stderr, and stdin, with explicit `bind`, `close`, `reopen`, and `snapshot/
rollback` operations. Route `apply_permanent_redirections` and
`_rebind_closed_output_stream` through it; the close/reopen state machine (and
MED-1's fix) then lives in one place instead of being spread across four helpers
and a `closed_dups` list.

### Phase 3 — Optional: data-drive the backend dispatch (LOW-1)

If a future redirect form is added, factor the per-form fd/stream actions into a
table each backend interprets, keeping the backend-specific error policy
(raise vs `os._exit`) as a parameter. Marginal now; revisit on the next new
operator.

### Phase 4 — Close the Linux platform gap (LOW-2)

Ensure the nightly Linux run has an explicit write-side-procsub test that
exercises the `/dev/fd/N` path (not the FIFO fallback) and a body-uses-SIGALRM
case, so the two transports are both pinned on their respective platforms.

## Production Acceptance Gates

The subsystem is already close. To call the permanent-`exec` path fully
production-hardened, add automated tests demonstrating:

- bytes written by a builtin to a std fd closed via permanent `exec >&-` never
  reappear on any later reopen of that fd (MED-1);
- `exec` rollback leaves the entire redirect list undone on any member's failure
  (already true — pin it);
- no fd is leaked after redirect-setup failure with a process substitution
  present (already true — pin it via `/dev/fd` count);
- explicit source fds (`5<file`, `read -u5`, `5<<EOF`) behave identically across
  the external, builtin, and permanent paths (already true — pin the matrix).

## Final Assessment

psh's I/O redirection subsystem is correctness-oriented, well-architected, and
unusually well documented. The 2026-06-13 review's failures and structural
debts have been paid down; process-substitution ownership, fd-remap safety, and
permanent stdin rebinding are all now sound, and I verified the fd-leak and
rollback invariants directly rather than trusting the code's own claims. The one
confirmed defect is a narrow, correctly-diagnosed-but-data-leaking edge in the
`exec`-close-then-reopen sequence, whose fix and the surrounding stream-binding
simplification are the natural next campaign. Graded **A−**, with a clear,
small path to A.

## Checks-Run Appendix

- **Environment:** `main` @ `968a3af4` (v0.662.0); oracle Bash 5.2.26
  (`/opt/homebrew/bin/bash`); macOS (Darwin 25.5.0), Python 3.14.
  `python -c "import psh.__main__"` confirmed the worktree path; every probe ran
  with cwd = repo root and its own process group (SIGKILL on timeout).
- **Discipline:** no `run_tests.py`, no full `pytest`, no `--compare-bash` were
  run (active release wave). Per-probe timeouts killed the process group; a
  post-battery `ps` sweep found no runaway orphans.
- **Batteries (all independent per-case bash+psh pairs):**
  - operators (39 cases): all match modulo the `psh:` diagnostic prefix — `>`
    `>>` `<` `<>` `>|` `N>` `N>&M` `&>`/`&>>` csh `>&file`, close/move,
    noclobber (block/force/append/devnull/new), heredoc (basic/expand/quoted/
    dash/fd), here-string (plain/expand/fd5), procsub (in/two/out/diff),
    save-restore, nested braces, error paths (bad fd, unwritable dir, EISDIR,
    ambiguous, empty-target).
  - permanent-exec (18 cases, all subprocess): output/append/err rebind, stdin
    rebind (`read`/`cat`/`head`), save-restore, `{var}>` named fds
    (open/read/high/value-kept), close, **rollback** — all match except MED-1's
    close+reopen.
  - semantics (19 cases): ordering (`2>&1 >f` vs `>f 2>&1`, `2>&1 1>&3`), `|&`,
    `<>` in-place, large >64 KB heredoc (no deadlock), heredoc
    cmdsub/arith/backslash/quoted, here-string empty/newline/special, multi
    same-fd, noclobber symlink/dangling, pipe-member redirect — all match.
  - advanced (19 cases): explicit `5<file` external + `read -u`, explicit-fd
    heredoc, subshell redirect + inheritance, compound (`while`/`if`/`for`/
    `case`/`(( ))`) redirect incl. guarded error fall-through, `&>` in pipeline,
    10-stage pipeline, procsub as function arg, heredoc-in-procsub, function-
    call redirect, multi-dup, `/dev/stdout`, `/dev/stderr` — all match.
  - targeted singles: interleave ordering, tilde-in-target, move form `1>&3-`,
    `set -e` compound-redirect abort, fd-set leak comparison via `/dev/fd`,
    repeated-procsub leak, FIFO temp-dir cleanup, Ugly-5 setup-failure leak, the
    two 2026-06-13 failures, and MED-1's isolation (with/without override,
    per-command vs permanent, echo vs printf, external vs builtin).
- **Only divergences found:** the deliberate `psh:` vs
  `/opt/homebrew/bin/bash: line N:` diagnostic prefix (universal, not a bug),
  and MED-1.
- **Static test surface:** 390 test functions across 37 redirect-related test
  files (`tests/unit/io_redirect/`, `tests/integration/redirection/`).
