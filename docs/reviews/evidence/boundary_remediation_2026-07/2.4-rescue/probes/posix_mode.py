#!/usr/bin/env python3
"""Phase A: POSIX-mode interaction. psh already has a fatal-syntax-error
policy under `set -o posix` (_posix_syntax_abort). Does my new fatality
collide with it, and does bash agree?"""
import os
import shutil
import sys

import harness

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work-posix")

CASES = {
    "p1_posix_direct": ("set -o posix\necho B\necho $(if)\necho A\n", {}),
    "p2_posix_eval_sub": ("set -o posix\necho B\neval 'echo $(if)'\necho A\n", {}),
    "p3_posix_eval_plain": ("set -o posix\necho B\neval 'if'\necho A\n", {}),
    "p4_posix_source_sub": ("set -o posix\necho B\nsource sub.sh\necho A\n",
                            {"sub.sh": "echo IB\necho $(if)\necho IA\n"}),
    # `command eval` strips the special-builtin property (psh models this)
    "p5_posix_command_eval": (
        "set -o posix\necho B\ncommand eval 'echo $(if)'\necho A\n", {}),
    "p6_nonposix_command_eval": (
        "echo B\ncommand eval 'echo $(if)'\necho A\n", {}),
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
    for name in (sys.argv[1:] or list(CASES)):
        d, mp = prepare(name)
        print("-" * 70)
        print("%s  main=%r" % (name, CASES[name][0]))
        for channel in ("c", "file", "stdin"):
            b = harness.run("bash", mp, channel, d)
            p = harness.run("psh", mp, channel, d, parser="rd")
            mark = "" if (b["rc"] == p["rc"] and b["out"] == p["out"]) else "  <<< DIVERGE"
            print("   %-5s bash rc=%-4s out=%-24r | psh rc=%-4s out=%-24r%s"
                  % (channel, b["rc"], b["out"], p["rc"], p["out"], mark))


if __name__ == "__main__":
    main()
