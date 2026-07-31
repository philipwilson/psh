#!/usr/bin/env python3
"""Phase A: interactive-REPL parity. bash's interactive loop does NOT die on
these errors; psh must not either (brief: a REPL that dies on `echo $(if)`
is a bounce). Driven over a pty so both shells take the interactive path."""
import os
import pty
import select
import subprocess
import sys
import time

BASH = "/opt/homebrew/bin/bash"
PSH_ROOT = "/Users/pwilson/src/psh-r2-4"

SCRIPTS = {
    "direct_cmdsub": b"echo BEFORE\necho $(if)\necho AFTER-STILL-ALIVE\nexit 7\n",
    "eval_cmdsub": b"echo BEFORE\neval 'echo $(if)'\necho AFTER-STILL-ALIVE\nexit 7\n",
    "source_cmdsub": b"echo BEFORE\nsource sub.sh\necho AFTER-STILL-ALIVE\nexit 7\n",
    "procsub": b"echo BEFORE\ncat <(if)\necho AFTER-STILL-ALIVE\nexit 7\n",
}


def drive(argv, script, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = PSH_ROOT
    env["PS1"] = "$ "
    env.pop("DISPLAY", None)
    env.pop("PSH_STRICT_ERRORS", None)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.environ.clear()
        os.environ.update(env)
        os.execv(argv[0], argv)
    out = b""
    os.write(fd, script)
    deadline = time.time() + 8
    reaped = None
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.3)
        if r:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break                      # slave side closed -> shell exited
            if not chunk:
                break
            out += chunk
        try:
            wpid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            reaped = "gone"
            break
        if wpid == pid:
            reaped = status
            break
    # KILL-ON-TIMEOUT: never block in waitpid on a still-live shell.
    if reaped is None:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        try:
            _, reaped = os.waitpid(pid, 0)
        except ChildProcessError:
            reaped = "gone"
        rc = "TIMEOUT-KILLED"
    elif reaped == "gone":
        rc = "?"
    else:
        rc = (os.waitstatus_to_exitcode(reaped)
              if os.WIFEXITED(reaped) else "sig%d" % os.WTERMSIG(reaped))
    try:
        os.close(fd)
    except OSError:
        pass
    return rc, out.decode(errors="replace")


def main():
    cwd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-itr")
    os.makedirs(cwd, exist_ok=True)
    with open(os.path.join(cwd, "sub.sh"), "wb") as f:
        f.write(b"echo IN-BEFORE\necho $(if)\necho IN-AFTER\n")
    for name, script in SCRIPTS.items():
        print("=" * 70)
        print("INTERACTIVE", name, repr(script))
        for label, argv in (("bash", [BASH, "-i"]),
                            ("psh ", [sys.executable, "-m", "psh", "-i"])):
            rc, out = drive(argv, script, cwd)
            alive = "AFTER-STILL-ALIVE" in out
            print("  %s rc=%-4s survived=%-5s exit7=%s" % (
                label, rc, alive, rc == 7))
            print("      transcript=%r" % (out[-400:],))


if __name__ == "__main__":
    main()
