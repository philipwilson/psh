#!/usr/bin/env python3
"""ROUND 2 item 6: the FORKED CHILD's own EXIT trap — what $? does it see?

The child now EXITS 1 (fork containment). Question the verifier raised: does
the child's own EXIT trap observe that 1, or a stale 2? Probe bash for the
same observable and either match it or declare+pin.
"""
import os
import shutil
import sys

import harness

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work-childtrap")

CASES = {
    # subshell child with its own EXIT trap; parent reports the child's status
    "t1_subshell_ateof": (
        b"( trap 'echo T rc=$? >&2' EXIT; eval 'echo $(if)' )\necho RC=$?\n"),
    "t2_subshell_complete": (
        b"( trap 'echo T rc=$? >&2' EXIT; eval 'echo $(fi)' )\necho RC=$?\n"),
    # command-substitution child
    "t3_cmdsub_ateof": (
        b"x=$( trap 'echo T rc=$? >&2' EXIT; eval 'echo $(if)' )\necho RC=$?\n"),
    "t4_cmdsub_complete": (
        b"x=$( trap 'echo T rc=$? >&2' EXIT; eval 'echo $(fi)' )\necho RC=$?\n"),
    # CONTROL: an explicit exit 1 in the same position
    "t5_control_exit1": (
        b"( trap 'echo T rc=$? >&2' EXIT; exit 1 )\necho RC=$?\n"),
}


def main():
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    for name in (sys.argv[1:] or list(CASES)):
        d = os.path.join(WORK, name)
        os.makedirs(d)
        mp = os.path.join(d, "main.sh")
        with open(mp, "wb") as f:
            f.write(CASES[name])
        print("-" * 72)
        print(name, CASES[name])
        for ch in ("c", "file", "stdin"):
            b = harness.run("bash", mp, ch, d)
            p = harness.run("psh", mp, ch, d, parser="rd")
            btrap = [ln for ln in b["err"].splitlines() if ln.startswith("T rc=")]
            ptrap = [ln for ln in p["err"].splitlines() if ln.startswith("T rc=")]
            print("   %-5s bash out=%-14r trap=%-12s | psh out=%-14r trap=%-12s %s"
                  % (ch, b["out"], btrap, p["out"], ptrap,
                     "" if (b["out"] == p["out"]) else "<<< STATUS DIFF"))


if __name__ == "__main__":
    main()
