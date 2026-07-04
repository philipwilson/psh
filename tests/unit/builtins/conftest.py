"""Shared fixtures for builtin unit tests."""

import os
import signal

import pytest


@pytest.fixture
def spawned_pids():
    """Track exact PIDs of background jobs a test spawns and guarantee they are
    SIGKILLed on teardown — even when the test fails mid-way.

    ``disown`` REMOVES a job from the shell's job table, so the ``shell``
    fixture's ``_cleanup_shell`` teardown (which only reaps jobs still in the
    table) does NOT catch a disowned child. Without this net, an assertion
    failure before a test's own cleanup line orphans a long-lived ``sleep``
    that survives the test process and can later wedge an untimed
    ``communicate()`` in the runner.

    Kills are by EXACT PID (``os.kill(pid, SIGKILL)``), never a broad
    ``pkill -f sleep`` — a pattern kill could hit an unrelated process (e.g. a
    sibling xdist worker's own ``sleep``). Each spawner appends
    ``shell.state.last_bg_pid`` right after ``cmd &``.
    """
    pids: list = []
    try:
        yield pids
    finally:
        for pid in pids:
            if not pid:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass  # already gone (ESRCH) — nothing to do
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass  # not our child / already reaped (ECHILD)
