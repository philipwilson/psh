"""Slot 1.3b oracle — EXIT-trap-on-fatal-signal race, BOTH symptom faces.

Extends slot 1.3's `trap_race_probe.py`, which counted only face (a). The 1.3
round-2 verifier found a sibling face the original oracle was blind to, so a
fix could close (a) and still leave the defect live.

The script installs an EXIT trap that prints and then `exit 0`, writes a
readiness sentinel, and sleeps. The harness waits for the sentinel and sends
SIGTERM to the SHELL pid only.

bash's contract (the oracle): stdout is exactly `cleanup\n` and the wait
status is death by SIGTERM (rc -15). The trap's `exit 0` never wins.

Faces counted independently:
  (a) LOST_OUTPUT   — rc is -15 (correct death) but stdout lacks `cleanup`
  (b) WRONG_EXIT    — the trap's `exit 0` won: rc is 0, not -15
  (c) OTHER         — anything else (recorded, never silently bucketed)

Usage:
    python tmp/trap_race_oracle.py [N] [--shell psh|bash|both]
"""
import argparse
import os
import signal
import subprocess
import sys
import tempfile
import time

SCRIPT = 'trap "echo cleanup; exit 0" EXIT\n: > "{ready}"; sleep 0.5\n'
BASH = "/opt/homebrew/bin/bash"
EXPECTED_STDOUT = "cleanup\n"
EXPECTED_RC = -signal.SIGTERM


def run_once(shell_argv, tmpd, i):
    """One trial. Returns (face, rc, stdout, stderr, waited_seconds)."""
    ready = os.path.join(tmpd, f"r{i}")
    path = os.path.join(tmpd, f"s{i}.sh")
    with open(path, "w") as f:
        f.write(SCRIPT.format(ready=ready))

    p = subprocess.Popen(shell_argv + [path], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True)
    start = time.time()
    deadline = start + 10
    exited_early = False
    while time.time() < deadline:
        if os.path.exists(ready):
            break
        if p.poll() is not None:
            exited_early = True
            break
        time.sleep(0.001)
    waited = time.time() - start

    try:
        os.kill(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    out, err = p.communicate(timeout=20)
    rc = p.returncode

    # Where did the output GO? The sentinel is itself a redirect target,
    # so its contents distinguish MISDIRECTION from true loss.
    sentinel_contents = ""
    try:
        with open(ready) as fh:
            sentinel_contents = fh.read()
    except Exception:
        pass
    if rc == EXPECTED_RC and out == EXPECTED_STDOUT:
        face = "OK"
    elif rc == EXPECTED_RC:
        face = "LOST_OUTPUT"          # face (a)
    elif rc == 0:
        face = "WRONG_EXIT"           # face (b)
    else:
        face = "OTHER"
    if exited_early:
        face += "+EXITED_BEFORE_SENTINEL"
    return face, rc, out, err, waited, sentinel_contents


def run_batch(label, argv, n):
    counts = {}
    samples = {}
    with tempfile.TemporaryDirectory(dir="tmp") as tmpd:
        for i in range(n):
            face, rc, out, err, waited, sent = run_once(argv, tmpd, i)
            counts[face] = counts.get(face, 0) + 1
            if face != "OK" and face not in samples:
                samples[face] = (rc, out, err, waited, sent)
    ok = counts.get("OK", 0)
    print(f"{label}: OK {ok}/{n}", end="")
    for face in sorted(k for k in counts if k != "OK"):
        print(f" | {face} {counts[face]}", end="")
    print()
    for face, (rc, out, err, waited, sent) in sorted(samples.items()):
        print(f"    [{face}] rc={rc} stdout={out!r} stderr={err[:60]!r} "
              f"wait={waited:.3f}s SENTINEL={sent!r}")
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=120)
    ap.add_argument("--shell", default="both", choices=["psh", "bash", "both"])
    args = ap.parse_args()

    shells = []
    if args.shell in ("psh", "both"):
        shells.append(("psh", [sys.executable, "-m", "psh"]))
    if args.shell in ("bash", "both"):
        shells.append(("bash", [BASH]))

    failures = 0
    for label, argv in shells:
        counts = run_batch(label, argv, args.n)
        if label == "psh":
            failures = sum(v for k, v in counts.items() if k != "OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
