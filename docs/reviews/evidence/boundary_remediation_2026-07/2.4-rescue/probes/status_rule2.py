#!/usr/bin/env python3
"""Phase A round 2: errexit anomaly, forked-child internal status,
and the -c-frame-reachability hypothesis."""
import os
import shutil
import sys

import harness

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work-status2")

CASES = {
    # errexit: does it change the DIRECT case too, and what does the trap see?
    "e1_errexit_direct_trap": (
        "set -e\ntrap 'echo T rc=$?' EXIT\necho B\necho $(if)\n", {}),
    "e2_errexit_eval_trap": (
        "set -e\ntrap 'echo T rc=$?' EXIT\necho B\neval 'echo $(if)'\n", {}),
    "e3_noerrexit_eval_trap": (
        "trap 'echo T rc=$?' EXIT\necho B\neval 'echo $(if)'\n", {}),
    "e4_errexit_source_trap": (
        "set -e\ntrap 'echo T rc=$?' EXIT\necho B\nsource sub.sh\n",
        {"sub.sh": "echo IB\necho $(if)\n"}),

    # forked-child internal value (trap inside the child)
    "f1_child_trap_subshell": (
        "( trap 'echo T rc=$? >&2' EXIT; eval 'echo $(if)' )\necho RC=$?\n", {}),
    "f2_child_trap_cmdsub": (
        "x=$( trap 'echo T rc=$? >&2' EXIT; eval 'echo $(if)' )\necho RC=$?\n", {}),

    # -c-frame reachability: subshell inside -c contains it, parent survives
    "g1_subshell_in_c": (
        "echo B\n( eval 'echo $(if)' )\necho AFTER rc=$?\n", {}),
    "g2_func_cmdsub_in_c": (
        "f() { eval 'echo $(if)'; }\nx=$(f)\necho RC=$?\necho AFTER\n", {}),
    "g3_bg_job": (
        "echo B\neval 'echo $(if)' &\nwait\necho AFTER rc=$?\n", {}),

    # Does the abort respect a `trap ... ERR`? and RETURN traps?
    "h1_trap_err": (
        "set -E\ntrap 'echo ERRTRAP rc=$?' ERR\necho B\neval 'echo $(if)'\necho A\n", {}),

    # plain syntax error at -c reader level: does the EXIT trap run? (control)
    "i1_plain_c_trap": (
        "trap 'echo T rc=$?' EXIT\necho B\nif\necho A\n", {}),
}


def prepare(name):
    d = os.path.join(WORK, name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    main, helpers = CASES[name]
    mp = os.path.join(d, "main.sh")
    with open(mp, "wb") as f:
        f.write(main.encode())
    for hn, hb in helpers.items():
        with open(os.path.join(d, hn), "wb") as f:
            f.write(hb.encode())
    return d, mp


def main():
    only = sys.argv[1:] or list(CASES)
    for name in only:
        d, mp = prepare(name)
        print("-" * 70)
        print("%s  main=%r" % (name, CASES[name][0]))
        for channel in ("c", "file", "stdin"):
            b = harness.run("bash", mp, channel, d)
            p = harness.run("psh", mp, channel, d, parser="rd")
            print("   %-5s bash rc=%-4s out=%-30r err=%-30r" % (
                channel, b["rc"], b["out"], b["err"][-60:] if b["err"] else ""))
            print("   %-5s psh  rc=%-4s out=%-30r" % (channel, p["rc"], p["out"]))


if __name__ == "__main__":
    main()
