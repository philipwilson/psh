#!/usr/bin/env python3
"""R6-D: the in-process embedding contract, measured at whatever tree it runs in.

Shell.run_command in SCRIPT MODE lets SubstitutionSyntaxAbort escape to the
caller; the interactive family gets a status. One Shell per interpreter (the
process-global lease makes a second construction an error), so every row is its
own subprocess — the individual-run protocol applied to an in-process API.

Prints one line per row: <mode> <command> -> RC n | RAISED <type>.
"""
import os
import subprocess
import sys

PSH_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROWS = [
    ("script", "echo $(if)"),
    ("script", "echo $(fi)"),
    ("script", "cat <(if)"),
    ("script", "if"),                 # CONTROL: ordinary syntax error
    ("interactive", "echo $(if)"),
    ("interactive", "echo $(fi)"),
]

DRIVER = """
import sys
sys.path.insert(0, {root!r})
from psh.shell import Shell
sh = Shell()
sh.state.is_script_mode = {script_mode}
try:
    rc = sh.run_command({command!r})
    print("RC", rc)
except BaseException as e:
    print("RAISED", type(e).__name__)
"""


def main():
    print("PSH_ROOT:", PSH_ROOT)
    disc = subprocess.run([sys.executable, "-c",
                           "import sys; sys.path.insert(0, %r); import psh;"
                           " sys.stdout.write(psh.__file__)" % PSH_ROOT],
                          capture_output=True, cwd=PSH_ROOT)
    print("discriminator:", disc.stdout.decode())
    for mode, command in ROWS:
        driver = DRIVER.format(root=PSH_ROOT, command=command,
                               script_mode=(mode == "script"))
        env = dict(os.environ)
        env.pop("PSH_STRICT_ERRORS", None)
        r = subprocess.run([sys.executable, "-c", driver], capture_output=True,
                           cwd=PSH_ROOT, env=env, timeout=60)
        out = r.stdout.decode().strip().splitlines()
        answer = out[-1] if out else f"(no output; rc={r.returncode})"
        print(f"{mode:11s} {command!r:14s} -> {answer}")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
