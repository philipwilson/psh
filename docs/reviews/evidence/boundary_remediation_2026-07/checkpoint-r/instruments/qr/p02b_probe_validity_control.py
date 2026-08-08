#!/usr/bin/env python3
"""Validity control for p02 — proves the p02 classifier can report a non-OK
face (evidence rule 7: an instrument must be able to fail in both directions).

Same harness shape, but the script's EXIT trap prints NOTHING, so stdout lacks
'cleanup' while the death status is still -SIGTERM: every trial MUST classify
LOST_OUTPUT. 2 file-mode trials (outside the p02 sampling budget; this is an
instrument control, not characterization sampling).
"""
import os
import signal
import subprocess
import sys
import tempfile
import time

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/qr/wt"
SCRIPT = 'trap "" EXIT\n: > "{ready}"; sleep 0.5\n'
EXPECTED_STDOUT = "cleanup\n"
EXPECTED_RC = -signal.SIGTERM

assert os.path.realpath(os.getcwd()) == os.path.realpath(WT), "cwd must be the worktree"

ok = True
with tempfile.TemporaryDirectory(dir=os.path.join(WT, "tmp")) as tmpd:
    for i in range(2):
        ready = os.path.join(tmpd, f"r{i}")
        path = os.path.join(tmpd, f"s{i}.sh")
        with open(path, "w") as f:
            f.write(SCRIPT.format(ready=ready))
        p = subprocess.Popen([sys.executable, "-m", "psh", path], cwd=WT,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        deadline = time.time() + 10
        while time.time() < deadline:
            if os.path.exists(ready) or p.poll() is not None:
                break
            time.sleep(0.001)
        try:
            os.kill(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        out, err = p.communicate(timeout=20)
        rc = p.returncode
        # p02's classifier, verbatim:
        if rc == EXPECTED_RC and out == EXPECTED_STDOUT:
            face = "OK"
        elif rc == EXPECTED_RC:
            face = "LOST_OUTPUT"
        elif rc == 0:
            face = "WRONG_EXIT"
        else:
            face = "OTHER"
        print(f"trial {i}: rc={rc} stdout={out!r} -> face={face}")
        if face != "LOST_OUTPUT":
            ok = False
print("CONTROL", "PASS — classifier reports non-OK faces" if ok else "FAIL")
