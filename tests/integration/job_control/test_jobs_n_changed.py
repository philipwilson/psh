"""`jobs -n` — list only jobs whose status changed since last notified.

bash's `-n` filters the listing to jobs the user has not yet been notified of
at their CURRENT status (the J_NOTIFIED flag). Any `jobs` listing — with or
without `-n` — marks the shown jobs notified; a status change (stop, continue,
completion) re-arms the flag so the job reappears once. Verified against bash
5.2.26 (tmp/probes/probe_a*.sh). Subprocess pins (job control); serial-by-path.
"""

import subprocess
import sys

TIMEOUT = 15


def _psh(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, timeout=TIMEOUT,
    )


def _block(out: str, start: str, end: str) -> str:
    return out.split(start, 1)[1].split(end, 1)[0]


def test_jobs_n_first_shows_all_then_empty():
    """First `jobs -n` lists every (un-notified) job; the second is empty."""
    r = _psh('set -m; sleep 5 & sleep 5 & '
             'echo "A:"; jobs -n; echo "B:"; jobs -n; echo "end"; '
             'kill %1 %2 2>/dev/null')
    first = _block(r.stdout, 'A:', 'B:')
    second = _block(r.stdout, 'B:', 'end')
    assert first.count('Running') == 2
    assert second.strip() == ''


def test_jobs_n_reshows_after_status_change():
    """A completion re-arms the flag: `jobs -n` shows the newly-Done job once,
    then nothing (the still-running job stays notified)."""
    r = _psh('set -m; sleep 5 & sleep 0.2 & '
             'echo "A:"; jobs -n; sleep 0.5; '
             'echo "B:"; jobs -n; echo "C:"; jobs -n; echo "end"; '
             'kill %1 2>/dev/null')
    first = _block(r.stdout, 'A:', 'B:')
    changed = _block(r.stdout, 'B:', 'C:')
    third = _block(r.stdout, 'C:', 'end')
    assert first.count('Running') == 2      # both un-notified initially
    assert 'Done' in changed                # the finished job, once
    assert 'Running' not in changed         # the live job stays notified
    assert third.strip() == ''              # nothing left to report


def test_plain_jobs_marks_notified_too():
    """A plain `jobs` (no -n) also marks jobs notified, so a following
    `jobs -n` omits them (bash)."""
    r = _psh('set -m; sleep 5 & '
             'echo "P:"; jobs; echo "N:"; jobs -n; echo "end"; '
             'kill %1 2>/dev/null')
    plain = _block(r.stdout, 'P:', 'N:')
    n = _block(r.stdout, 'N:', 'end')
    assert 'Running' in plain
    assert n.strip() == ''


def test_jobs_n_empty_with_no_jobs():
    """`jobs -n` with no jobs prints nothing and succeeds."""
    r = _psh('jobs -n; echo "rc=$?"')
    assert r.stdout == 'rc=0\n'
