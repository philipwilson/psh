"""`wait -n` — return when the NEXT single job completes (reappraisal #14 Tier 2).

bash's `wait -n` waits for any one of the shell's jobs (or, with operands, the
first of those) to finish and returns that job's status; with no jobs to wait
for it returns 127. `-p VAR` stores the finished job's PID. psh used to reject
`-n` as "not a valid process id". Verified against bash 5.2.
"""

import subprocess
import sys


def _psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


def test_basic_returns_zero():
    r = _psh('sleep 0.1 & sleep 0.2 & wait -n; echo "rc=$?"')
    assert r.stdout == 'rc=0\n'


def test_returns_single_job_status():
    r = _psh('(exit 7) & wait -n; echo "got $?"')
    assert r.stdout == 'got 7\n'


def test_returns_first_finisher_status():
    # The job that finishes FIRST determines the status (bash), not the first
    # started: the quick exit-4 job wins over the slow exit-3 one.
    r = _psh('(sleep 0.25; exit 3) & (sleep 0.02; exit 4) & wait -n; echo "first=$?"')
    assert r.stdout == 'first=4\n'


def test_no_jobs_returns_127():
    r = _psh('wait -n; echo "rc=$?"')
    assert r.stdout == 'rc=127\n'


def test_then_wait_for_rest():
    r = _psh('sleep 0.03 & sleep 0.06 & wait -n; wait; echo all done')
    assert r.stdout.strip().endswith('all done')


def test_operand_waits_for_that_job():
    r = _psh('(sleep 0.2; exit 1) & a=$!; (exit 5) & b=$!; wait -n "$b"; echo "rc=$?"')
    assert r.stdout == 'rc=5\n'


def test_dash_p_stores_pid():
    r = _psh('(exit 0) & p=$!; wait -n -p done; [ "$done" = "$p" ] && echo match')
    assert r.stdout == 'match\n'


def test_plain_wait_unaffected():
    r = _psh('sleep 0.03 & wait; echo "rc=$?"')
    assert r.stdout == 'rc=0\n'


def test_wait_pid_unaffected():
    r = _psh('(exit 4) & p=$!; wait "$p"; echo "rc=$?"')
    assert r.stdout == 'rc=4\n'
