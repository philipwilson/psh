#!/usr/bin/env python3
"""4A.2 fix round -- the DISCRIMINATING bare-exit battery (blocker R3).

My Phase A A-1 battery contained two bare-exit cells and BOTH were vacuous:
nothing inside the trap changed `$?` before the bare `exit`, so "uses the
pre-trap status" and "uses the current `$?`" predict the SAME answer and the
cells could not have failed for the reason their row gave (D-3.4 lesson 8).

This battery walks the axis I contributed and did not walk: WHAT RUNS INSIDE
THE TRAP BODY BEFORE THE BARE EXIT.  Every cell is a composition, and the
vacuous shapes are kept as explicit CONTROLS so the discriminating rows cannot
be mistaken for the whole story.

Axes: inner-body shape x outer route x input mode x trap kind.

    python tmp/w4a2-probes/probe_bare_exit.py
"""
import os
import subprocess
import sys
import tempfile

BASH = "/opt/homebrew/bin/bash"
PSH_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# (id, script, discriminating?)  A cell is DISCRIMINATING when the trap body
# changes $? before the bare `exit`; otherwise the two candidate rules agree
# by construction and the cell proves nothing about which one is implemented.
CELLS = [
    # --- the vacuous shapes my A-1 shipped, kept as labelled controls ---
    ("control/bare-exit-after-exit3",   "trap 'exit' EXIT; exit 3", False),
    ("control/bare-exit-after-false",   "trap 'exit' EXIT; false", False),
    ("control/no-bare-exit",            "trap 'false' EXIT; exit 3", False),
    # --- discriminating: the body changes $? before the bare exit ---
    ("DISC/false-then-exit/outer-3",    "trap 'false; exit' EXIT; exit 3", True),
    ("DISC/true-then-exit/outer-3",     "trap 'true; exit' EXIT; exit 3", True),
    ("DISC/false-then-exit/normal-end", "trap 'false; exit' EXIT", True),
    ("DISC/true-then-exit/outer-false", "trap 'true; exit' EXIT; false", True),
    ("DISC/exit9cmd-then-exit/outer-3",
     "trap '(exit 9); exit' EXIT; exit 3", True),
    # $? is READ before the bare exit: does reading agree with what exit uses?
    ("DISC/echo-q-then-exit/outer-3",
     "trap 'false; echo q=$?; exit' EXIT; exit 3", True),
    # explicit operand must still win (regression guard for any fix)
    ("guard/false-then-exit7/outer-3",  "trap 'false; exit 7' EXIT; exit 3", False),
    # nested: bare exit inside a FUNCTION called from the trap
    ("DISC/func-bare-exit/outer-3",
     "f() { false; exit; }; trap f EXIT; exit 3", True),
    # bare exit in a NON-exit trap (bash: same saved-status rule)
    ("DISC/usr1-trap-bare-exit",
     "trap 'false; exit' USR1; (kill -USR1 $$); sleep 0.1; exit 3", True),
    # errexit interaction
    ("DISC/errexit-false-then-exit",
     "set -e; trap 'false; exit' EXIT; exit 3", True),
]

MODES = ("c", "script", "stdin")


def run(argv, mode, script, workdir):
    env = dict(os.environ)
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    env["PYTHONPATH"] = PSH_ROOT
    env["HOME"] = workdir
    env.pop("PSH_STRICT_ERRORS", None)
    if mode == "c":
        full, data = argv + ["-c", script], None
    elif mode == "script":
        path = os.path.join(workdir, "case.sh")
        with open(path, "w") as fh:
            fh.write(script + "\n")
        full, data = argv + [path], None
    else:
        full, data = list(argv), script + "\n"
    proc = subprocess.run(full, input=data, capture_output=True, text=True,
                          timeout=30, cwd=workdir, env=env)
    return proc.stdout, proc.returncode


def main():
    ver = subprocess.run([BASH, "--version"], capture_output=True,
                         text=True).stdout.splitlines()[0]
    sha = subprocess.run(["git", "-C", PSH_ROOT, "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    print(f"# oracle bash: {BASH}")
    print(f"# {ver}")
    print(f"# psh tree: {PSH_ROOT}  tip: {sha}")
    print("# DISC = discriminating (trap body changes $? before the bare exit)")
    print()

    psh_argv = [sys.executable, "-m", "psh", "--norc"]
    bash_argv = [BASH, "--norc", "--noprofile"]

    agree = disagree = 0
    disc_disagree = 0
    scratch = os.path.join(PSH_ROOT, "tmp", "w4a2-probes", "scratch")
    os.makedirs(scratch, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as wd:
        for cell_id, script, disc in CELLS:
            for mode in MODES:
                p = run(psh_argv, mode, script, wd)
                b = run(bash_argv, mode, script, wd)
                same = p == b
                agree += same
                disagree += (not same)
                if not same and disc:
                    disc_disagree += 1
                mark = "OK  " if same else "DIFF"
                print(f"{mark} {cell_id:<34} {mode:<7} "
                      f"psh={p} bash={b}")
    print()
    print(f"TOTAL rows={agree + disagree} agree={agree} disagree={disagree}")
    print(f"      disagreements in DISCRIMINATING cells: {disc_disagree}")


if __name__ == "__main__":
    main()
