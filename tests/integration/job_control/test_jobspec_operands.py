"""`jobs` honors jobspec operands + typed jobspec resolution (JobManager campaign item 1).

bash's `jobs` restricts its listing to the named jobspec and reports
"no such job" / "ambiguous job spec" for specs that do not resolve; psh used
to ignore the operand and list every job at rc=0. These run psh in a
subprocess (real background jobs) and pin the output against bash 5.2.26.
Each job is a short `sleep` reaped by the trailing `wait`, so nothing leaks.
Path-marked serial (tests/integration/job_control).
"""

import subprocess
import sys


def _psh(script: str):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def test_jobs_no_such_job_number():
    # bash: `jobs %999` -> "jobs: %999: no such job", rc=1.
    out, err, rc = _psh("sleep 0.3 & jobs %999; echo rc=$?; wait")
    assert "%999: no such job" in err
    assert "rc=1" in out


def test_jobs_no_such_job_prefix():
    out, err, rc = _psh("sleep 0.3 & jobs %nomatch; echo rc=$?; wait")
    assert "%nomatch: no such job" in err
    assert "rc=1" in out


def test_jobs_filters_to_named_job():
    # Two jobs; `jobs %1` must list ONLY job 1 (psh used to list both).
    out, err, rc = _psh(
        "sleep 0.3 & sleep 0.4 & jobs %1; echo rc=$?; wait")
    assert "sleep 0.3" in out
    assert "sleep 0.4" not in out
    assert "rc=0" in out


def test_jobs_current_and_previous_markers():
    # `%+` is the current (last-started) job, `%-` the previous one.
    out, err, rc = _psh(
        "sleep 0.3 & sleep 0.4 & jobs %+; jobs %-; echo rc=$?; wait")
    lines = [ln for ln in out.splitlines() if "sleep" in ln]
    assert len(lines) == 2
    assert "sleep 0.4" in lines[0]   # %+ is the most recent
    assert "sleep 0.3" in lines[1]   # %- is the previous


def test_jobs_bare_integer_is_job_number():
    # bash treats a bare integer operand to `jobs` as a job number: `jobs 1`
    # == `jobs %1`, and `jobs 2` (no job 2) -> "no such job".
    out, err, rc = _psh("sleep 0.3 & jobs 1; echo rc=$?; wait")
    assert "sleep 0.3" in out and "rc=0" in out
    out, err, rc = _psh("sleep 0.3 & jobs 2; echo rc=$?; wait")
    assert "2: no such job" in err and "rc=1" in out


def test_jobs_ambiguous_prefix():
    # Two jobs sharing the "sleep" prefix -> ambiguous. This DELIBERATELY pins
    # INTERACTIVE bash: `bash -i` prints both the "ambiguous job spec" and a
    # following "no such job" line and returns 1. Bash is mode-inconsistent
    # here — `bash -c` prints only the first line and returns 0 — so this is a
    # psh-only assertion (not a golden/compare-bash case, which would flake
    # against bash -c); psh renders the interactive-style diagnostic in every
    # mode. See docs/user_guide/17_differences_from_bash.md (Job Control).
    out, err, rc = _psh(
        "sleep 5 & sleep 6 & jobs %sleep; echo rc=$?; "
        "kill %1 %2 2>/dev/null; wait 2>/dev/null")
    assert "sleep: ambiguous job spec" in err
    assert "%sleep: no such job" in err
    assert "rc=1" in out


def test_jobs_substring_form():
    out, err, rc = _psh("sleep 0.3 & jobs '%?.3'; echo rc=$?; wait")
    assert "sleep 0.3" in out and "rc=0" in out


def test_jobs_current_unavailable():
    # `%+` / `%-` with no jobs -> "no such job", rc=1 (bash).
    out, err, rc = _psh("jobs %+; echo rc=$?")
    assert "%+: no such job" in err and "rc=1" in out
    out, err, rc = _psh("jobs %-; echo rc=$?")
    assert "%-: no such job" in err and "rc=1" in out
