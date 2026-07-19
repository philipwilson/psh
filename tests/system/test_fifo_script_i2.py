"""A script delivered through a FIFO is consumed ON DEMAND (campaign I2, H14).

The mandatory case: a producer that waits for the script's first SIDE EFFECT
before writing the rest must be served. An eager reader (base) drains the whole
FIFO before running line one, so the side effect never happens and the producer
never unblocks — a deadlock. The lazy reader runs line one, the side effect
fires, and the producer sends the rest.

Process/FIFO heavy -> serial + killpg cleanup.
"""
import os
import signal
import subprocess
import sys
import threading
import time

import pytest

pytestmark = pytest.mark.serial


def _run_fifo_script(tmp_path, chunks, sentinel_after_first=True, timeout=8.0):
    """Run `psh FIFO`, feeding `chunks` from a producer thread that waits for
    the script's sentinel side effect between chunk 0 and the rest.

    Returns (stdout, returncode, saw_sentinel_before_rest).
    """
    fifo = str(tmp_path / "p")
    sentinel = str(tmp_path / "ran")
    os.mkfifo(fifo)
    text = [c.replace("SENTINEL", sentinel) for c in chunks]
    state = {"saw": False}

    proc = subprocess.Popen(
        [sys.executable, "-m", "psh", fifo], cwd=str(tmp_path),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True,
        env=dict(os.environ, PYTHONPATH=str(_repo_root())))

    def produce():
        try:
            with open(fifo, "w") as wf:
                wf.write(text[0])
                wf.flush()
                if sentinel_after_first:
                    deadline = time.time() + timeout
                    while time.time() < deadline:
                        if os.path.exists(sentinel):
                            state["saw"] = True
                            break
                        time.sleep(0.01)
                for chunk in text[1:]:
                    wf.write(chunk)
                    wf.flush()
        except OSError:
            pass

    t = threading.Thread(target=produce)
    t.start()
    try:
        out, _err = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _err = proc.communicate()
        rc = 124
    t.join(timeout=2)
    return out.decode("utf-8", "surrogateescape"), rc, state["saw"]


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def test_producer_waits_for_first_side_effect(tmp_path):
    # Chunk 0 prints hi AND creates the sentinel; the producer only sends chunk
    # 1 after seeing the sentinel. An eager reader deadlocks (rc 124).
    out, rc, saw = _run_fifo_script(
        tmp_path, ["printf 'hi\\n'; : > SENTINEL\n", "printf 'bye\\n'\n"])
    assert rc == 0, f"deadlock/timeout (eager read?) out={out!r}"
    assert saw is True, "line-1 side effect did not run before the rest was sent"
    assert out == "hi\nbye\n"


def test_partial_line_across_chunks(tmp_path):
    # A physical line split across two writes (with the sentinel wait between)
    # is reassembled — the reader carries the partial tail.
    out, rc, saw = _run_fifo_script(
        tmp_path, ["printf 'first\\n'; : > SENTINEL\necho comp", "leted\n"])
    assert rc == 0
    assert saw is True
    assert out == "first\ncompleted\n"


def test_plain_full_script_runs(tmp_path):
    # No sentinel dependency: the whole script arrives, all of it runs.
    out, rc, _ = _run_fifo_script(
        tmp_path, ["echo a\necho b\necho c\n"], sentinel_after_first=False)
    assert rc == 0
    assert out == "a\nb\nc\n"


def test_eof_mid_construct_does_not_hang(tmp_path):
    # Producer closes mid-construct (an unterminated `if`). psh must reach EOF
    # and report a syntax error, not hang (rc != 124).
    out, rc, _ = _run_fifo_script(
        tmp_path, ["echo before\nif true; then\n"], sentinel_after_first=False)
    assert rc != 124, "hung on EOF mid-construct"
    assert "before\n" in out
