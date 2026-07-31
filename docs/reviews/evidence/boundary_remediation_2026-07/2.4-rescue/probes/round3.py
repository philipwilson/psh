#!/usr/bin/env python3
"""Phase A round 3: (a) is the fatality strippable by `command`/`builtin`?
(b) isolate the posix+source anomaly. (c) builtin eval."""
import os
import shutil
import sys

import harness

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work-r3")

CASES = {
    # (a) `command`/`builtin` strip the SPECIAL property. Does that suppress
    #     the substitution fatality? CONTROL = plain syntax error (non-fatal).
    "a1_command_eval_sub": ("echo B\ncommand eval 'echo $(if)'\necho A\n", {}),
    "a2_command_eval_plain": ("echo B\ncommand eval 'if'\necho A\n", {}),
    "a3_builtin_eval_sub": ("echo B\nbuiltin eval 'echo $(if)'\necho A\n", {}),
    "a4_command_source_sub": ("echo B\ncommand source sub.sh\necho A\n",
                              {"sub.sh": "echo IB\necho $(if)\necho IA\n"}),

    # (b) posix + source: does the sourced file's FIRST line run?
    "b1_posix_source": ("set -o posix\necho B\nsource sub.sh\necho A\n",
                        {"sub.sh": "echo IB\necho $(if)\necho IA\n"}),
    "b2_nonposix_source": ("echo B\nsource sub.sh\necho A\n",
                           {"sub.sh": "echo IB\necho $(if)\necho IA\n"}),
    "b3_posix_source_plain": ("set -o posix\necho B\nsource sub.sh\necho A\n",
                              {"sub.sh": "echo IB\nif\necho IA\n"}),
    "b4_posix_source_ok": ("set -o posix\necho B\nsource sub.sh\necho A\n",
                           {"sub.sh": "echo IB\necho IA\n"}),

    # (c) does the fatality survive a trap ACTION string?
    "c1_trap_action_sub": (
        "trap 'echo TA; eval \"echo \\$(if)\"; echo TA2' USR1\n"
        "echo B\nkill -USR1 $$\nsleep 0.2\necho A\n", {}),
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
            print("   %-5s bash rc=%-4s out=%-22r | psh rc=%-4s out=%-22r%s"
                  % (channel, b["rc"], b["out"], p["rc"], p["out"], mark))


if __name__ == "__main__":
    main()
