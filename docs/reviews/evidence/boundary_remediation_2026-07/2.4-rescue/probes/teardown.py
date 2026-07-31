#!/usr/bin/env python3
"""ROUND 3 item 1: the EXIT-TRAP TEARDOWN family, probed against bash FIRST.

The trap's OWN ACTION TEXT carries the substitution-body error, and the trap
fires at teardown. Distinct from ruling O3 (a mid-script USR1 action).

Checks the integrator's stated expectations:
  bare exit    -> rc preserved (0), diagnostic, NONE of the action runs
  exit N       -> rc stays N
  subshell     -> child 0
  cmdsub       -> child 0
Both error kinds, three channels, both parsers.
"""
import os
import shutil
import sys

import harness

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work-teardown-probe")

# name -> (body bytes, expectation note)
def _cases():
    out = {}
    for kind, body in (("if", b"$(if)"), ("fi", b"$(fi)")):
        out["a_bare_exit_" + kind] = (
            b"trap 'echo T; echo " + body + b"; echo T2' EXIT\necho B\n",
            "rc 0, action does not run")
        out["b_exit_3_" + kind] = (
            b"trap 'echo T; echo " + body + b"' EXIT\necho B\nexit 3\n",
            "rc stays 3")
        out["c_subshell_" + kind] = (
            b"( trap 'echo CT; echo " + body + b"' EXIT; echo IN )\n"
            b"echo AFTER rc=$?\n", "child 0")
        out["d_cmdsub_" + kind] = (
            b"x=$( trap 'echo " + body + b"' EXIT; echo IN )\n"
            b"echo AFTER rc=$? x=$x\n", "child 0, x=IN")
        out["e_eval_in_action_" + kind] = (
            b'trap \'eval "echo \\' + body + b'"\' EXIT\necho B\n',
            "rc 0")
        out["f_exit_0_explicit_" + kind] = (
            b"trap 'echo " + body + b"' EXIT\necho B\nexit 0\n",
            "rc stays 0")
        out["g_valid_action_CTL_" + kind] = (
            b"trap 'echo VALID' EXIT\necho B\n", "control: rc 0, VALID runs")
    return out


CASES = _cases()


def main():
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    mismatches = 0
    for name in (sys.argv[1:] or list(CASES)):
        body, note = CASES[name]
        d = os.path.join(WORK, name)
        os.makedirs(d)
        mp = os.path.join(d, "main.sh")
        with open(mp, "wb") as f:
            f.write(body)
        print("-" * 78)
        print("%s  [%s]  %r" % (name, note, body))
        for ch in ("c", "file", "stdin"):
            b = harness.run("bash", mp, ch, d)
            r = harness.run("psh", mp, ch, d, parser="rd")
            c = harness.run("psh", mp, ch, d, parser="combinator")
            tb = "TRACEBACK" if "Traceback (most recent call last)" in r["err"] else ""
            ok = (b["rc"] == r["rc"] and b["out"] == r["out"])
            if not ok:
                mismatches += 1
            split = "" if (r["rc"] == c["rc"] and r["out"] == c["out"]) else " SPLIT"
            print("   %-5s bash rc=%-4s out=%-20r | psh rc=%-4s out=%-20r %s%s%s"
                  % (ch, b["rc"], b["out"], r["rc"], r["out"],
                     "" if ok else "*** MISMATCH ***", " " + tb if tb else "", split))
    print("\nMISMATCH ROWS:", mismatches)


if __name__ == "__main__":
    main()
