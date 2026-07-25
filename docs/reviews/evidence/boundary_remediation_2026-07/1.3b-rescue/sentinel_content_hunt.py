"""Where does the trap's output GO on a losing run?

If the mechanism is 'misdirected into the live redirect target' rather than
'lost to a closed stream', the sentinel file will contain `cleanup`.
"""
import os, signal, subprocess, sys, tempfile, time
SCRIPT = 'trap "echo cleanup; exit 0" EXIT\n: > "{ready}"; sleep 0.5\n'
N = int(sys.argv[1]) if len(sys.argv) > 1 else 400
losses = 0
with tempfile.TemporaryDirectory(dir="tmp") as tmpd:
    for i in range(N):
        ready = os.path.join(tmpd, f"r{i}")
        path = os.path.join(tmpd, f"s{i}.sh")
        with open(path, "w") as f:
            f.write(SCRIPT.format(ready=ready))
        p = subprocess.Popen([sys.executable, "-m", "psh", path],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        dl = time.time() + 10
        while time.time() < dl:
            if os.path.exists(ready) or p.poll() is not None: break
            time.sleep(0.001)
        try: os.kill(p.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        out, err = p.communicate(timeout=20)
        rc = p.returncode
        if not (rc == -signal.SIGTERM and out == "cleanup\n"):
            losses += 1
            sentinel = ""
            try:
                with open(ready) as fh: sentinel = fh.read()
            except Exception as e: sentinel = f"<unreadable: {e}>"
            print(f"LOSS #{losses} iter {i}: rc={rc} stdout={out!r} stderr={err[:50]!r}")
            print(f"    SENTINEL FILE CONTENTS: {sentinel!r}")
            if losses >= 3: break
print(f"losses {losses} / {i+1}")
