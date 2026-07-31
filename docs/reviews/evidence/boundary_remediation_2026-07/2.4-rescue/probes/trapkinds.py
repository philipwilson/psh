#!/usr/bin/env python3
"""ROUND 3 item 6: O3 UNIVERSE ALIGNMENT.

The declared O3 divergence says "a TRAP ACTION string whose own parse fails",
but its pin covers only USR1. Probe the other action-bearing trap kinds —
DEBUG, ERR, RETURN, and a second signal — so the ledger wording and the pin
corpus agree on the domain.
"""
import os
import shutil
import sys

import harness

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work-trapkinds")

CASES = {
    "usr1_pinned": (
        b"trap ' echo TA; echo $(fi); echo TA2' USR1\n"
        b"echo B\nkill -USR1 $$\nsleep 0.2\necho AFTER\n"),
    "term_signal": (
        b"trap ' echo TA; echo $(fi); echo TA2' TERM\n"
        b"echo B\nkill -TERM $$\nsleep 0.2\necho AFTER\n"),
    "debug_trap": (
        b"trap ' echo $(fi)' DEBUG\necho B\necho AFTER\n"),
    "err_trap": (
        b"set -E\ntrap ' echo $(fi)' ERR\necho B\nfalse\necho AFTER\n"),
    "return_trap": (
        b"set -T\ntrap ' echo $(fi)' RETURN\n"
        b"f() { echo IN; }\necho B\nf\necho AFTER\n"),
    "exit_trap_teardown": (
        b"trap ' echo $(fi)' EXIT\necho B\necho AFTER\n"),
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
        print("-" * 78)
        print("%s  %r" % (name, CASES[name]))
        for ch in ("c", "file", "stdin"):
            b = harness.run("bash", mp, ch, d)
            r = harness.run("psh", mp, ch, d, parser="rd")
            c = harness.run("psh", mp, ch, d, parser="combinator")
            tb = " TRACEBACK" if "Traceback (most" in r["err"] else ""
            ok = (b["rc"] == r["rc"] and b["out"] == r["out"])
            split = "" if (r["rc"] == c["rc"] and r["out"] == c["out"]) else " SPLIT"
            print("   %-5s bash rc=%-4s out=%-24r | psh rc=%-4s out=%-24r %s%s%s"
                  % (ch, b["rc"], b["out"], r["rc"], r["out"],
                     "" if ok else "*** DIVERGE ***", tb, split))


if __name__ == "__main__":
    main()
