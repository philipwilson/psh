#!/usr/bin/env python3
"""CONFIRMATION (2), strict instrument.

The Phase A battery's ``survived`` flag matched on the whole pty transcript,
which INCLUDES the terminal's echo of the typed input — so a dead shell could
still look "survived". This instrument changes the measurement: it feeds a
marker command whose OUTPUT is distinguishable from its echo
(``echo SURV$((6*7))`` echoes as the literal source but PRINTS ``SURV42``),
and separately reports whether the shell process actually exited.
"""
import os
import pty
import select
import sys
import time

BASH = "/opt/homebrew/bin/bash"
PSH_ROOT = "/Users/pwilson/src/psh-r2-4"

# The error line, then a marker whose OUTPUT differs from its echo.
CASES = {
    "direct_cmdsub": b"echo $(if)\necho SURV$((6*7))\n",
    "eval_cmdsub":   b"eval 'echo $(if)'\necho SURV$((6*7))\n",
    "source_cmdsub": b"source sub.sh\necho SURV$((6*7))\n",
    "procsub":       b"cat <(if)\necho SURV$((6*7))\n",
    "control_plain": b"if\necho SURV$((6*7))\n",
}


def drive(argv, script, cwd):
    env = dict(os.environ)
    env["PS1"] = "$ "
    env["PYTHONPATH"] = PSH_ROOT
    env.pop("DISPLAY", None)
    env.pop("PSH_STRICT_ERRORS", None)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.environ.clear()
        os.environ.update(env)
        os.execv(argv[0], argv)
    os.write(fd, script)
    out = b""
    deadline = time.time() + 6
    exited = None
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.3)
        if r:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        try:
            wpid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            exited = "gone"
            break
        if wpid == pid:
            exited = status
            break
    if exited is None:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
    try:
        os.close(fd)
    except OSError:
        pass
    return exited, out.decode(errors="replace")


def main():
    cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-itr")
    os.makedirs(cwd, exist_ok=True)
    with open(os.path.join(cwd, "sub.sh"), "wb") as f:
        f.write(b"echo IN-BEFORE\necho $(if)\necho IN-AFTER\n")
    print("marker OUTPUT 'SURV42' proves the REPL lived; its echo reads "
          "'SURV$((6*7))' so echo cannot fake it\n")
    for name, script in CASES.items():
        row = []
        for label, argv in (("bash", [BASH, "-i"]),
                            ("psh", [sys.executable, "-m", "psh", "-i"])):
            exited, out = drive(argv, script, cwd)
            row.append((label, "SURV42" in out,
                        "still-running" if exited is None else "EXITED"))
        agree = row[0][1] == row[1][1]
        print("  %-15s bash alive=%-5s (%s) | psh alive=%-5s (%s)   %s" % (
            name, row[0][1], row[0][2], row[1][1], row[1][2],
            "PARITY" if agree else "*** DIVERGE ***"))


if __name__ == "__main__":
    main()
