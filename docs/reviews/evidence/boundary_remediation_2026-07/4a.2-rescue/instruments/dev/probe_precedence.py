#!/usr/bin/env python3
"""4A.2 Phase A — exit-status precedence battery (EXIT ROUTE x TRAP DISPOSITION).

Runs every cell in BOTH shells across three non-interactive input modes
(-c string, script file, piped stdin) and prints an agreement table.

Oracle bash is the PATH bash (/opt/homebrew/bin/bash 5.2.26) by EXPLICIT
argv -- never /bin/bash.  Run from the repo root:
    python tmp/w4a2-probes/probe_precedence.py
"""
import os
import subprocess
import sys
import tempfile

BASH = "/opt/homebrew/bin/bash"
PSH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# --- discriminator: prove which psh tree we are exercising -------------------
DISCRIMINATOR = os.path.join(PSH_ROOT, "psh", "shell.py")

#: (id, script text).  Every cell is written so BOTH shells can run it.
CELLS = [
    ("no-trap/exit-3",            "exit 3"),
    ("no-trap/end",               "true"),
    ("trap-noexit/exit-3",        "trap ':' EXIT; exit 3"),
    ("trap-noexit/end",           "trap ':' EXIT; true"),
    ("trap-exit7/exit-3",         "trap 'exit 7' EXIT; exit 3"),
    ("trap-exit7/end",            "trap 'exit 7' EXIT"),
    ("trap-echo-exit7/exit-3",    "trap 'echo T; exit 7' EXIT; exit 3"),
    # `exit` with NO operand inside the trap: bash preserves the pre-trap status.
    ("trap-bare-exit/exit-3",     "trap 'exit' EXIT; exit 3"),
    ("trap-bare-exit/end-false",  "trap 'exit' EXIT; false"),
    # $? observed at trap entry.
    ("trap-dollarq/exit-3",       "trap 'echo q=$?' EXIT; exit 3"),
    ("trap-dollarq/end-false",    "trap 'echo q=$?' EXIT; false"),
    ("trap-dollarq/exit-0",       "trap 'echo q=$?' EXIT; false; exit 0"),
    # A command INSIDE the trap changes $? before the implicit exit.
    ("trap-cmd-then-end/exit-3",  "trap 'false' EXIT; exit 3"),
    ("trap-cmd-true/exit-3",      "trap 'true' EXIT; exit 3"),
    # Nested: the EXIT trap re-arms EXIT (bash: does NOT re-fire).
    ("trap-rearm/exit-3",         "trap 'echo A; trap \"echo B\" EXIT' EXIT; exit 3"),
    # Trap removed inside the trap.
    ("trap-selfclear/exit-3",     "trap 'echo A; trap - EXIT' EXIT; exit 3"),
    # errexit interaction.
    ("errexit/trap-exit7",        "set -e; trap 'exit 7' EXIT; false; echo NOPE"),
    ("errexit/trap-noexit",       "set -e; trap 'echo T' EXIT; false; echo NOPE"),
    # exit inside a function called from the trap.
    ("trap-func-exit7/exit-3",    "f() { exit 7; }; trap f EXIT; exit 3"),
    # exit status out of range / negative inside trap.
    ("trap-exit-257/exit-3",      "trap 'exit 257' EXIT; exit 3"),
    ("trap-exit-neg1/exit-3",     "trap 'exit -1' EXIT; exit 3"),
    # subshell inside the trap that exits: must NOT exit the shell.
    ("trap-subshell-exit/exit-3", "trap '(exit 9); echo S=$?' EXIT; exit 3"),
]

MODES = ("c", "script", "stdin")


def run(shell_argv, mode, script, workdir):
    env = dict(os.environ)
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    env.pop("PSH_STRICT_ERRORS", None)
    env["HOME"] = workdir
    if mode == "c":
        argv = shell_argv + ["-c", script]
        stdin_data = None
    elif mode == "script":
        path = os.path.join(workdir, "case.sh")
        with open(path, "w") as fh:
            fh.write(script + "\n")
        argv = shell_argv + [path]
        stdin_data = None
    else:
        argv = list(shell_argv)
        stdin_data = script + "\n"
    proc = subprocess.run(argv, input=stdin_data, capture_output=True,
                          text=True, timeout=30, cwd=workdir, env=env)
    return proc.stdout, proc.stderr, proc.returncode


def main():
    assert os.path.isfile(DISCRIMINATOR), DISCRIMINATOR
    bash_ver = subprocess.run([BASH, "--version"], capture_output=True,
                              text=True).stdout.splitlines()[0]
    print(f"# oracle bash: {BASH}")
    print(f"# {bash_ver}")
    print(f"# psh tree:    {PSH_ROOT}")
    print(f"# discriminator: {DISCRIMINATOR} "
          f"({os.path.getsize(DISCRIMINATOR)} bytes)")
    sha = subprocess.run(["git", "-C", PSH_ROOT, "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    print(f"# psh tip:     {sha}")
    print()

    psh_argv = [sys.executable, "-m", "psh", "--norc"]
    bash_argv = [BASH, "--norc", "--noprofile"]

    agree = disagree = 0
    rows = []
    with tempfile.TemporaryDirectory(dir=os.path.join(PSH_ROOT, "tmp")) as wd:
        for cell_id, script in CELLS:
            for mode in MODES:
                env_root = dict(os.environ)
                env_root["PYTHONPATH"] = PSH_ROOT
                os.environ["PYTHONPATH"] = PSH_ROOT
                p = run(psh_argv, mode, script, wd)
                b = run(bash_argv, mode, script, wd)
                same = (p[0], p[2]) == (b[0], b[2])
                agree += same
                disagree += (not same)
                rows.append((cell_id, mode, p, b, same))

    for cell_id, mode, p, b, same in rows:
        mark = "OK  " if same else "DIFF"
        print(f"{mark} {cell_id:<28} {mode:<7} "
              f"psh=({p[0]!r},{p[2]}) bash=({b[0]!r},{b[2]})")
        if not same and p[1] != b[1]:
            print(f"       psh stderr={p[1]!r}")
            print(f"       bash stderr={b[1]!r}")

    print()
    print(f"TOTAL cells={len(rows)} agree={agree} disagree={disagree}")


if __name__ == "__main__":
    main()
