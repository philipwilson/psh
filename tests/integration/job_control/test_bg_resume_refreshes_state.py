"""`bg` must refresh a job's state before deciding whether to send SIGCONT.

The bug: ``_resume_in_background`` gated everything on ``job.state ==
JobState.STOPPED`` without refreshing it. A non-interactive shell has no
SIGCHLD-driven reaper, so a job stopped from OUTSIDE the shell leaves that field
saying RUNNING; the gate is skipped, **no SIGCONT is sent**, and ``bg`` prints
nothing and returns 0 while the job stays stopped. ``fg`` already guarded this
exact hazard (``refresh_one_job(job, track_stops=True)``, with a comment saying
why); ``bg`` never did.

It surfaced on the Linux nightly as an intermittent PTY failure -- 9/10 under
load, 0/5 without -- because load is what makes the stop notification late. This
pin does NOT reproduce it that way. Nothing here sleeps to synchronise: the stop
is delivered by an EXTERNAL ``kill`` (so the shell cannot have observed it
through its own builtin) and the script BLOCKS until ``ps`` confirms the child
really is stopped, so ``job.state`` is deterministically stale by the time ``bg``
runs. The two outcomes are then qualitatively different -- resumed, or stopped
forever -- rather than fast versus slow.

Tracking the stop is correct on this path for the same reason it is in ``fg``:
``bg`` requires job control (both shells print "bg: no job control" and exit 1
without it), so the branch is only reachable under monitor mode.
"""

import os
import subprocess
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

# `set -m` gives job control without a terminal. The stop is delivered by the
# external kill(1), never psh's builtin, so the shell has no chance to record
# it. Both loops are bounded so a regression fails loudly instead of hanging.
SCRIPT = r'''
set -m
sleep 30 &
pid=$!
/bin/kill -STOP $pid
n=0
while [ "$n" -lt 500 ]; do
  case "$(ps -o stat= -p $pid 2>/dev/null)" in
    *T*) break ;;
  esac
  n=$((n+1))
done
echo "before_bg=$(ps -o stat= -p $pid 2>/dev/null | tr -d ' ')"
bg %1
echo "bg_rc=$?"
n=0
while [ "$n" -lt 500 ]; do
  case "$(ps -o stat= -p $pid 2>/dev/null)" in
    *T*) n=$((n+1)) ;;
    *)   break ;;
  esac
done
case "$(ps -o stat= -p $pid 2>/dev/null)" in
  *T*) echo "after_bg=STILL-STOPPED" ;;
  *)   echo "after_bg=RESUMED" ;;
esac
/bin/kill -CONT $pid 2>/dev/null
/bin/kill -TERM $pid 2>/dev/null
'''


def _run_psh(script):
    env = {**os.environ, 'PYTHONPATH': _REPO_ROOT}
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, timeout=60, env=env)


def test_bg_actually_resumes_a_job_stopped_behind_the_shells_back():
    """RED on base: bg returns 0, prints no resume line, job stays stopped."""
    r = _run_psh(SCRIPT)
    out = r.stdout

    assert 'before_bg=T' in out, (
        "harness precondition failed: the child was not stopped before `bg` "
        f"ran, so this row proves nothing.\nstdout={out!r}\nstderr={r.stderr!r}")

    assert 'after_bg=RESUMED' in out, (
        "`bg` did not resume the job: it is still stopped. bg gated on a stale "
        "job.state and never sent SIGCONT (it must refresh first, as fg does)."
        f"\nstdout={out!r}\nstderr={r.stderr!r}")

    # bash announces the resumed job; a bg that skipped its body prints nothing.
    assert 'sleep 30 &' in out, (
        "`bg` printed no resume line, so it took the skip path even if the job "
        f"happened to be running.\nstdout={out!r}")
    assert 'bg_rc=0' in out, out


def test_bg_without_job_control_still_errors():
    """Guard the precondition the refresh relies on: bg needs monitor mode."""
    r = _run_psh('sleep 5 & bg %1; echo rc=$?')
    assert 'no job control' in r.stderr, (r.stdout, r.stderr)
    assert 'rc=1' in r.stdout, (r.stdout, r.stderr)
