"""Drift-lock: ForegroundJobSession is the sole owner of the foreground-launch
transaction (campaign J1 / #20 H12).

A command, a pipeline, and a foreground subshell each launch a process group
and then run the SAME transaction (register the foreground job, transfer the
terminal, wait, report a signal death, reclaim the terminal, drop the DONE
job). That transaction lived in three open-coded copies and the subshell copy
had silently drifted (no foreground registration, no signal-death diagnostic,
no stopped-job promotion, no exception cleanup). It now lives once in
``psh/executor/foreground_session.py``.

This guard fails the moment a launch path re-open-codes any transaction
primitive instead of routing through ForegroundJobSession — the exact drift
that produced the silent-subshell bug. (The ``fg``/``bg`` builtins are a
SEPARATE transaction — they RESUME an existing job rather than launch one — so
they legitimately call the primitives; they are not launch paths.)
"""
import pathlib
import re

_PSH = pathlib.Path(__file__).resolve().parents[3] / "psh"

# The three foreground *launch* modules that must delegate to the session.
_LAUNCH_MODULES = [
    _PSH / "executor" / "strategies.py",
    _PSH / "executor" / "pipeline.py",
    _PSH / "executor" / "subshell.py",
]

# Transaction primitives that belong to the session (or the fg/bg resume path),
# never to a launch module directly.
_PRIMITIVES = (
    "finish_foreground_job",
    "report_signal_death_at",
    "report_abnormal_termination",
    "set_foreground_job",
    "wait_for_job",
)

_CALL = re.compile(r"\.(" + "|".join(_PRIMITIVES) + r")\(")


def _code_lines(path: pathlib.Path):
    """Yield (lineno, text) for lines that are not pure-comment lines. (Docstring
    bodies in these files do not contain the ``.<primitive>(`` call shape, so a
    simple comment strip is sufficient and robust.)"""
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        yield i, line


def test_launch_modules_do_not_open_code_the_transaction():
    offenders = []
    for path in _LAUNCH_MODULES:
        for lineno, line in _code_lines(path):
            if _CALL.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "foreground-launch module calls a foreground-job transaction primitive "
        "directly instead of routing through ForegroundJobSession (campaign J1 "
        "H12 — this is exactly how the subshell path drifted into silent signal "
        "deaths). Route it through the session:\n  " + "\n  ".join(offenders))


def test_every_launch_module_uses_the_session():
    for path in _LAUNCH_MODULES:
        text = path.read_text(encoding="utf-8")
        assert "ForegroundJobSession" in text, (
            f"{path.name} launches a foreground job but does not use "
            f"ForegroundJobSession — it must open a session for the transaction.")


def test_signal_death_reporting_has_one_chokepoint():
    """report_signal_death_at is the single signal-death reporter; the only
    caller of the wrapper report_abnormal_termination is its own definition and
    the session (no path re-implements the abnormal_termination_message print)."""
    printers = []
    for path in _PSH.rglob("*.py"):
        if path.name == "job_control.py":
            continue  # the definitions live here
        text = path.read_text(encoding="utf-8")
        # a foreground signal-death print reconstructed outside the chokepoint
        if "abnormal_termination_message(" in text and "print(" in text:
            # allow the foreground_session module to reference it in prose only
            for lineno, line in _code_lines(path):
                if "abnormal_termination_message(" in line and "import" not in line:
                    printers.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not printers, (
        "a module reconstructs the foreground signal-death diagnostic instead "
        "of routing through JobManager.report_signal_death_at:\n  "
        + "\n  ".join(printers))
