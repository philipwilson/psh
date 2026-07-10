"""jobs -r/-s state filters and bg resume-line marker (task #9 [#27+#28]).

Unit-level because a non-interactive `-c` shell cannot create a STOPPED job
(psh polls job state only interactively), so these construct the JobManager
directly and drive the builtins — the same pattern as
tests/integration/job_control/test_wait_disown_bg_fg.py.

bash-pinned (5.2.26):
- `jobs -r` lists only Running jobs; `jobs -s` only Stopped jobs.
- `bg`'s resume line uses the job's real marker at print time (`+` current,
  `-` previous, ` ` otherwise) — not a hardcoded `+`.
"""

import sys
import types

from psh.builtins.job_control import BgBuiltin, JobsBuiltin
from psh.executor.job_control import JobManager, JobState


def _shell(jm):
    return types.SimpleNamespace(
        job_manager=jm,
        stderr=sys.stderr,
        state=types.SimpleNamespace(
            options={"interactive": False, "monitor": True},
            in_forked_child=False,
            stdout=sys.stdout,
            stderr=sys.stderr,
        ),
    )


def _running(jm, pgid, command):
    job = jm.create_job(pgid=pgid, command=command)
    job.add_process(pgid, command)
    job.foreground = False
    job.update_state()
    assert job.state is JobState.RUNNING
    return job


def _stopped(jm, pgid, command):
    job = jm.create_job(pgid=pgid, command=command)
    job.add_process(pgid, command)
    job.foreground = False
    job.update_process_status(pgid, 0x7f)  # WIFSTOPPED
    job.update_state()
    assert job.state is JobState.STOPPED
    return job


# ---- jobs -r / -s state filters ---------------------------------------------

def test_jobs_r_lists_only_running(monkeypatch):
    jm = JobManager()
    _running(jm, 100, "sleep 5")
    _stopped(jm, 200, "sleep 6")
    shell = _shell(jm)

    lines = []
    builtin = JobsBuiltin()
    monkeypatch.setattr(builtin, "write_line", lambda msg, sh: lines.append(msg))
    rc = builtin.execute(["jobs", "-r"], shell)

    assert rc == 0
    assert any("sleep 5" in line for line in lines)
    assert not any("sleep 6" in line for line in lines)


def test_jobs_s_lists_only_stopped(monkeypatch):
    jm = JobManager()
    _running(jm, 100, "sleep 5")
    _stopped(jm, 200, "sleep 6")
    shell = _shell(jm)

    lines = []
    builtin = JobsBuiltin()
    monkeypatch.setattr(builtin, "write_line", lambda msg, sh: lines.append(msg))
    rc = builtin.execute(["jobs", "-s"], shell)

    assert rc == 0
    assert any("sleep 6" in line for line in lines)
    assert not any("sleep 5" in line for line in lines)


def test_jobs_r_combines_with_l(monkeypatch):
    # -r filter still honors -l long format (PID column).
    jm = JobManager()
    _running(jm, 100, "sleep 5")
    _stopped(jm, 200, "sleep 6")
    shell = _shell(jm)

    lines = []
    builtin = JobsBuiltin()
    monkeypatch.setattr(builtin, "write_line", lambda msg, sh: lines.append(msg))
    rc = builtin.execute(["jobs", "-rl"], shell)

    assert rc == 0
    assert any("sleep 5" in line and "100" in line for line in lines)
    assert not any("sleep 6" in line for line in lines)


# ---- bg resume-line marker ---------------------------------------------------

def _bg_line(monkeypatch, jm, spec):
    shell = _shell(jm)
    monkeypatch.setattr("os.killpg", lambda pgid, sig: None)
    lines = []
    builtin = BgBuiltin()
    monkeypatch.setattr(builtin, "write_line", lambda msg, sh: lines.append(msg))
    rc = builtin.execute(["bg", spec], shell)
    return rc, lines


def test_bg_marker_previous_job_is_dash(monkeypatch):
    jm = JobManager()
    j1 = _stopped(jm, 111, "sleep 4")
    j2 = _stopped(jm, 222, "sleep 5")
    jm.current_job = j2   # %+
    jm.previous_job = j1  # %-

    rc, lines = _bg_line(monkeypatch, jm, "%1")
    assert rc == 0
    assert lines == ["[1]- sleep 4 &"]
    assert j1.state is JobState.RUNNING


def test_bg_marker_current_job_is_plus(monkeypatch):
    jm = JobManager()
    j1 = _stopped(jm, 111, "sleep 4")
    j2 = _stopped(jm, 222, "sleep 5")
    jm.current_job = j1   # %+
    jm.previous_job = j2  # %-

    rc, lines = _bg_line(monkeypatch, jm, "%1")
    assert rc == 0
    assert lines == ["[1]+ sleep 4 &"]


def test_bg_marker_neither_is_space(monkeypatch):
    # A job that is neither current nor previous gets a blank marker.
    jm = JobManager()
    _stopped(jm, 111, "sleep 4")  # job 1 - the bg target, neither %+ nor %-
    j2 = _stopped(jm, 222, "sleep 5")
    j3 = _stopped(jm, 333, "sleep 6")
    jm.current_job = j2
    jm.previous_job = j3

    rc, lines = _bg_line(monkeypatch, jm, "%1")
    assert rc == 0
    assert lines == ["[1]  sleep 4 &"]
