"""Direct repro of the EXIT-trap-output-lost-on-SIGTERM race (no pytest)."""
import os, signal, subprocess, sys, tempfile, time

SCRIPT = 'trap "echo cleanup; exit 0" EXIT\n: > "{ready}"; sleep 0.5\n'

def run_once(shell_argv, tmpd, i):
    ready = os.path.join(tmpd, f"r{i}")
    path = os.path.join(tmpd, f"s{i}.sh")
    with open(path, "w") as f:
        f.write(SCRIPT.format(ready=ready))
    p = subprocess.Popen(shell_argv + [path], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.time() + 10
    while time.time() < deadline:
        if os.path.exists(ready):
            break
        if p.poll() is not None:
            break
        time.sleep(0.001)
    try:
        os.kill(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    out, err = p.communicate(timeout=20)
    return out, p.returncode

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    for label, argv in (("psh", [sys.executable, "-m", "psh"]),
                        ("bash", ["/opt/homebrew/bin/bash"])):
        empties = 0
        rcs = {}
        with tempfile.TemporaryDirectory(dir="tmp") as tmpd:
            for i in range(n):
                out, rc = run_once(argv, tmpd, i)
                rcs[rc] = rcs.get(rc, 0) + 1
                if out != "cleanup\n":
                    empties += 1
        print(f"{label}: lost-trap-output {empties}/{n}  returncodes={rcs}")

main()
