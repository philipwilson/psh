"""Non-interactive job-state refresh (task #22 [#36], Tier-1).

bash refreshes job state before `jobs`/`fg` in EVERY shell mode, so a
non-interactive `-c`/script shell reflects an external `kill -STOP`/`-CONT`
and a background completion. psh gated this behind `interactive` (its poll
used `waitpid(-1)`), so non-interactive `jobs` showed a stale `Running` and
`fg` on an externally-stopped job returned 128+SIGSTOP leaving it stopped.

The refresh is now per-job-process-group (`waitpid(-job.pgid, ...)`), which is
safe in any mode: a background job has its own pgid while command/process
substitution children stay in the shell's pgid, so the refresh can never reap
a substitution child out from under its own wait. These pins run psh in a
subprocess (job control + signals) with a hard timeout; serial-by-path.

All behaviours verified against bash 5.2.26 (tmp/probes/probe_*.sh).
"""

import subprocess
import sys

TIMEOUT = 15


def _psh(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, timeout=TIMEOUT,
    )


# ---------------------------------------------------------------------------
# (d) non-interactive `jobs` reflects real state
# ---------------------------------------------------------------------------

def test_jobs_reflects_external_stop():
    """`kill -STOP` on a bg job → non-interactive `jobs` shows Stopped.

    A short settle lets the job finish setpgid before the STOP: a signal that
    lands mid-launch freezes the child in the shell's process group, where the
    per-pgid refresh can't see it (a launch-window race, not a steady-state
    one — a job running for more than a few ms is always in its own pgid).
    """
    r = _psh('set -m; sleep 3 & p=$!; sleep 0.15; kill -STOP "$p"; sleep 0.3; '
             'jobs; kill "$p" 2>/dev/null')
    assert 'Stopped' in r.stdout
    assert 'Running' not in r.stdout


def test_jobs_reflects_external_continue():
    """Full STOP→CONT cycle in one non-interactive listing pair: `jobs` shows
    Stopped after `kill -STOP`, then Running after `kill -CONT`.

    Anchored on the STOP step (red-on-base: base's stale table reads Running
    both times, so it never shows Stopped) so this genuinely exercises the
    refresh, not the coincidence that a continued job's real state is Running.
    macOS raises no SIGCHLD on continue, so only the WCONTINUED refresh sees it.
    """
    r = _psh('set -m; sleep 3 & p=$!; sleep 0.15; kill -STOP "$p"; sleep 0.2; '
             'echo "S:"; jobs; kill -CONT "$p"; sleep 0.2; '
             'echo "C:"; jobs; kill "$p" 2>/dev/null')
    stopped_block = r.stdout.split('S:', 1)[1].split('C:', 1)[0]
    cont_block = r.stdout.split('C:', 1)[1]
    assert 'Stopped' in stopped_block
    assert 'Running' in cont_block
    assert 'Stopped' not in cont_block


def test_jobs_suppresses_completed_job_in_c_mode():
    """In `-c` mode `jobs` does NOT list a completed job on stdout.

    bash reaps a finished job eagerly in `-c` (announcing it on stderr under
    monitor — the deferred -c+monitor boundary notice), so `jobs` stdout is
    empty. In script/stdin modes it IS listed once — see the mode matrix in
    test_jobs_completed_listing_modes.py. Both `set -m` and plain -c runs match
    bash's empty -c stdout here; the job is still reaped (next test).
    """
    for prefix in ('set -m; ', ''):
        r = _psh(prefix + 'false & sleep 0.3; echo "A:"; jobs; echo "B:"')
        lines = r.stdout.splitlines()
        between = lines[lines.index('A:') + 1:lines.index('B:')]
        assert between == [], (prefix, r.stdout)
        assert 'Exit' not in r.stdout and 'Done' not in r.stdout, (prefix, r.stdout)


def test_jobs_reaps_completion_for_later_wait():
    """Although unlisted, a finished job IS reaped by `jobs`: it does not linger
    as a stale Running entry and `wait` still returns its status."""
    r = _psh('false & p=$!; sleep 0.3; jobs >/dev/null; '
             'wait "$p"; echo "w=$?"')
    assert 'w=1' in r.stdout


def test_jobs_reap_remembers_status_for_later_wait():
    """`jobs` reaping a Done job retains its status for a later `wait <pid>`
    (bash: `(exit 7)& p=$!; sleep .3; jobs; wait $p` -> 7, repeatably)."""
    r = _psh('sleep 0.1 & p=$!; ( exit 7 ) & q=$!; sleep 0.3; '
             'jobs >/dev/null; wait "$q"; echo "r1=$?"; wait "$q"; echo "r2=$?"')
    assert 'r1=7' in r.stdout
    assert 'r2=7' in r.stdout


def test_bare_wait_after_jobs_reap_clears_remembered():
    """A bare `wait` after `jobs` reaped a job forgets its status → a later
    `wait <pid>` is 127 (bash: `jobs; wait; wait $p` -> 0 then 127)."""
    r = _psh('( exit 5 ) & p=$!; sleep 0.3; jobs >/dev/null; '
             'wait; echo "bare=$?"; wait "$p"; echo "again=$?"')
    assert 'bare=0' in r.stdout
    assert 'again=127' in r.stdout


def test_wait_n_after_jobs_reap_is_127():
    """`wait -n` after `jobs` removed the only job → 127 (a removed job is not
    a `wait -n` target; bash: `jobs; wait -n` -> 127)."""
    r = _psh('( exit 3 ) & sleep 0.3; jobs >/dev/null; wait -n; echo "wn=$?"')
    assert 'wn=127' in r.stdout


# ---------------------------------------------------------------------------
# (d) non-steal: the per-pgid refresh must never reap a substitution child
# ---------------------------------------------------------------------------

def test_refresh_does_not_steal_command_substitution_children():
    """A live bg job + repeated `jobs` refreshes must not corrupt command
    substitution output (the refresh waits per job pgid, not `waitpid(-1)`)."""
    r = _psh('set -m; sleep 3 & '
             'for i in 1 2 3 4 5 6 7 8; do '
             '  v=$(echo "val$i"); jobs >/dev/null 2>&1; '
             '  [ "$v" = "val$i" ] || { echo "CORRUPT $i:$v"; exit 1; }; '
             'done; echo ALLOK; kill %1 2>/dev/null')
    assert 'ALLOK' in r.stdout
    assert 'CORRUPT' not in r.stdout


def test_refresh_does_not_steal_process_substitution_children():
    """Same guarantee for process substitution: its child forks into the
    shell's pgid, so a per-pgid job refresh can't reap it."""
    r = _psh('set -m; sleep 3 & '
             'for i in 1 2 3 4 5 6; do '
             '  out=$(cat <(printf "psub%s" "$i")); jobs >/dev/null 2>&1; '
             '  [ "$out" = "psub$i" ] || { echo "CORRUPT $i:$out"; exit 1; }; '
             'done; echo ALLOK; kill %1 2>/dev/null')
    assert 'ALLOK' in r.stdout
    assert 'CORRUPT' not in r.stdout


# ---------------------------------------------------------------------------
# (g) stopped `fg` under monitor-on / no controlling terminal
# ---------------------------------------------------------------------------

def test_stopped_fg_no_tty_resumes_to_completion():
    """`fg` on an externally-stopped job (monitor on, no tty) resumes it to
    completion and returns 0 — not 128+SIGSTOP with the job left stopped."""
    r = _psh('set -m; sleep 1 & sleep 0.15; kill -STOP %1; sleep 0.2; '
             'fg %1; echo "fg-rc=$?"; echo "after:"; jobs')
    assert 'fg-rc=0' in r.stdout
    # Job resumed and completed → gone from the table.
    after = r.stdout.split('after:', 1)[1]
    assert 'Stopped' not in after
    assert '145' not in r.stdout


# ---------------------------------------------------------------------------
# (h) fg/bg end-of-options `--`
# ---------------------------------------------------------------------------

def test_fg_double_dash_jobspec():
    """`fg -- %1` treats `--` as end-of-options, not a jobspec."""
    r = _psh('set -m; sleep 0.3 & fg -- %1; echo "rc=$?"')
    assert 'rc=0' in r.stdout
    assert 'no such job' not in r.stderr


def test_fg_double_dash_alone_uses_current():
    """`fg --` with no jobspec falls back to the current job."""
    r = _psh('set -m; sleep 0.3 & fg --; echo "rc=$?"')
    assert 'rc=0' in r.stdout
    assert 'no such job' not in r.stderr


def test_bg_double_dash_jobspec():
    """`bg -- %1` treats `--` as end-of-options."""
    r = _psh('set -m; sleep 1 & sleep 0.15; kill -STOP %1; sleep 0.1; bg -- %1; '
             'echo "rc=$?"; wait')
    assert 'rc=0' in r.stdout
    assert 'no such job' not in r.stderr
