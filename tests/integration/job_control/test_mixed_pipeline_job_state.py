"""End-to-end: a pipeline with a completed + stopped member is Stopped (F10).

`set -m; true | sh -c 'kill -STOP $$'` produces a pipeline whose first member
(true) completes and whose second member (sh) stops. bash reports the job as
Stopped and promotes it to the current job (%+); psh used to report it Running
because the completed member kept the all-stopped check false.

Runs psh in a subprocess (real job control) and SIGKILLs the stopped member in
the same script so no stopped process leaks. Path-marked serial.
"""

import subprocess
import sys


def _run(script: str):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def test_completed_plus_stopped_pipeline_reports_stopped():
    # The final `kill -KILL %1` reaps the stopped `sh` so nothing leaks.
    script = (
        "set -m; true | sh -c 'kill -STOP $$'; jobs; "
        "kill -KILL %1 2>/dev/null; wait 2>/dev/null")
    out, _, rc = _run(script)
    # The pipeline job is Stopped (not Running) and current (%+).
    assert "Stopped" in out
    assert "[1]+" in out
    assert "Running" not in out
