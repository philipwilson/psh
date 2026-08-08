#!/usr/bin/env python3
"""QR item 1 — EXIT-trap output misdirected on fatal-signal death: does the
Part D characterization stand at tip (ae871a16)?

FRESH equivalent of the committed 1.3b instruments (trap_race_oracle.py /
sentinel_content_hunt.py) — committed probes are never edited (D-4B.3-note
hazard). Three input modes per the recorded characterization
(file-mode 1/25, stdin-mode 1/25, -c 0/25):

  file-mode : psh script.sh
  stdin-mode: psh reading the script from a PIPED stdin
  -c mode   : psh -c '<script>' (ready-file injected)

Bounded sampling, <=200 runs TOTAL (80 file + 80 stdin + 40 -c), foreground.
Faces (from the committed oracle):
  OK          — rc == -SIGTERM and stdout == 'cleanup\n'
  LOST_OUTPUT — rc correct, stdout lacks cleanup (face a). Sentinel file
                contents recorded: 'cleanup' inside => MISDIRECTED (the
                corrected mechanism).
  WRONG_EXIT  — rc == 0 (face b: the trap's `exit 0` won)
  OTHER       — anything else, recorded verbatim.

Run with cwd INSIDE the worktree (cwd discipline selects the worktree psh).
"""
import os
import signal
import subprocess
import sys
import tempfile
import time

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/qr/wt"
SCRIPT = 'trap "echo cleanup; exit 0" EXIT\n: > "{ready}"; sleep 0.5\n'
EXPECTED_STDOUT = "cleanup\n"
EXPECTED_RC = -signal.SIGTERM
N_FILE, N_STDIN, N_C = 80, 80, 40

assert os.path.realpath(os.getcwd()) == os.path.realpath(WT), "cwd must be the worktree"

disc = subprocess.run(
    [sys.executable, "-c",
     "import psh, psh.version; print(psh.__file__); print(psh.version.__version__)"],
    cwd=WT, capture_output=True, text=True)
lines = disc.stdout.strip().splitlines()
assert len(lines) == 2 and lines[0].startswith(WT) and lines[1] == "0.773.0", disc.stdout
print(f"DISCRIMINATOR-OK {lines[0]} version={lines[1]}")


def one_trial(mode, tmpd, i):
    ready = os.path.join(tmpd, f"r_{mode}_{i}")
    body = SCRIPT.format(ready=ready)
    stdin = subprocess.DEVNULL
    stdin_data = None
    if mode == "file":
        path = os.path.join(tmpd, f"s_{mode}_{i}.sh")
        with open(path, "w") as f:
            f.write(body)
        argv = [sys.executable, "-m", "psh", path]
    elif mode == "stdin":
        argv = [sys.executable, "-m", "psh"]
        stdin = subprocess.PIPE
        stdin_data = body
    else:  # -c
        argv = [sys.executable, "-m", "psh", "-c", body.replace("\n", "; ").rstrip("; ")]

    p = subprocess.Popen(argv, cwd=WT, stdin=stdin,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if stdin_data is not None:
        p.stdin.write(stdin_data)
        p.stdin.flush()
        # keep the pipe OPEN: closing it would signal EOF; the script's own
        # `sleep 0.5` keeps the shell alive; ready-file is the sync point.
    deadline = time.time() + 10
    exited_early = False
    while time.time() < deadline:
        if os.path.exists(ready):
            break
        if p.poll() is not None:
            exited_early = True
            break
        time.sleep(0.001)
    try:
        os.kill(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if stdin_data is not None:
        try:
            p.stdin.close()
        except OSError:
            pass
    out, err = p.communicate(timeout=20)
    rc = p.returncode
    sentinel = ""
    try:
        with open(ready) as fh:
            sentinel = fh.read()
    except OSError:
        pass
    if rc == EXPECTED_RC and out == EXPECTED_STDOUT:
        face = "OK"
    elif rc == EXPECTED_RC:
        face = "LOST_OUTPUT"
    elif rc == 0:
        face = "WRONG_EXIT"
    else:
        face = "OTHER"
    if exited_early:
        face += "+EXITED_BEFORE_SENTINEL"
    return face, rc, out, err, sentinel


def batch(mode, n):
    counts = {}
    events = []
    with tempfile.TemporaryDirectory(dir=os.path.join(WT, "tmp")) as tmpd:
        for i in range(n):
            face, rc, out, err, sent = one_trial(mode, tmpd, i)
            counts[face] = counts.get(face, 0) + 1
            if face != "OK":
                events.append((i, face, rc, out, err[:80], sent))
    summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"{mode}-mode: n={n} {summary}")
    for i, face, rc, out, err, sent in events:
        misdir = "MISDIRECTED" if "cleanup" in sent else "not-in-sentinel"
        print(f"    iter {i}: {face} rc={rc} stdout={out!r} stderr={err!r} "
              f"SENTINEL={sent!r} [{misdir}]")
    return counts


os.makedirs(os.path.join(WT, "tmp"), exist_ok=True)
t0 = time.time()
c_file = batch("file", N_FILE)
c_stdin = batch("stdin", N_STDIN)
c_c = batch("c", N_C)
total = N_FILE + N_STDIN + N_C
print(f"TOTAL runs={total} elapsed={time.time()-t0:.0f}s")
