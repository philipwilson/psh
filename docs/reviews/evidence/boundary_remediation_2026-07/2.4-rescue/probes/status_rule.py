#!/usr/bin/env python3
"""Phase A: what determines bash's ABORT STATUS (127 vs 2 vs 1)?

Discriminates: substitution-specific vs channel-specific; whether the
pre-error $? leaks; and what the forked-child status is.
"""
import os
import shutil
import sys

import harness

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work-status")

CASES = {
    # Q1: is 127 substitution-specific, or does ANY -c syntax error give 127?
    "q1_plain_syntax_toplevel": ("echo B\nif\necho A\n", {}),
    "q1_sub_syntax_toplevel": ("echo B\necho $(if)\necho A\n", {}),
    "q1_plain_unclosed_quote": ("echo B\necho 'unclosed\n", {}),

    # Q2: does the pre-error $? leak into the abort status?
    "q2_false_then_direct": ("false\necho $(if)\n", {}),
    "q2_true_then_direct": ("true\necho $(if)\n", {}),
    "q2_false_then_eval": ("false\neval 'echo $(if)'\n", {}),
    "q2_true_then_eval": ("true\neval 'echo $(if)'\n", {}),
    "q2_exit9_then_eval": ("(exit 9)\neval 'echo $(if)'\n", {}),
    "q2_exit9_then_direct": ("(exit 9)\necho $(if)\n", {}),

    # Q3: file mode 2-vs-1 — is it "reader parse" vs "parse_and_execute"?
    "q3_file_direct": ("echo B\necho $(if)\n", {}),
    "q3_file_eval": ("echo B\neval 'echo $(if)'\n", {}),
    "q3_file_source_direct": ("echo B\nsource sub.sh\n",
                              {"sub.sh": "echo IB\necho $(if)\n"}),

    # Q4: forked-child status (cmdsub) for BOTH shapes
    "q4_cmdsub_direct_child": ("x=$(eval 'x=$(if)')\necho RC=$?\n", {}),
    "q4_cmdsub_eval_child": ("x=$(eval 'echo $(if)')\necho RC=$?\n", {}),
    "q4_subshell_direct": ("( eval 'echo $(if)' )\necho RC=$?\n", {}),
    "q4_backtick_child": ("x=`eval 'echo $(if)'`\necho RC=$?\n", {}),

    # Q5: does `set -e` / errexit change anything?
    "q5_errexit_eval": ("set -e\necho B\neval 'echo $(if)'\necho A\n", {}),

    # Q6: trap EXIT — does the abort run EXIT traps (i.e. is it a real exit)?
    "q6_trap_exit_eval": ("trap 'echo TRAPPED rc=$?' EXIT\necho B\n"
                          "eval 'echo $(if)'\necho A\n", {}),
    "q6_trap_exit_direct": ("trap 'echo TRAPPED rc=$?' EXIT\necho B\n"
                            "echo $(if)\n", {}),

    # Q7: is it really "exit"? does an explicit exit in the same place match?
    "q7_explicit_exit": ("trap 'echo TRAPPED rc=$?' EXIT\necho B\nexit 1\necho A\n", {}),
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
        body = CASES[name][0]
        print("-" * 70)
        print("%s  main=%r" % (name, body))
        for channel in ("c", "file", "stdin"):
            b = harness.run("bash", mp, channel, d)
            p = harness.run("psh", mp, channel, d, parser="rd")
            print("   %-5s bash rc=%-4s out=%-34r | psh rc=%-4s out=%r"
                  % (channel, b["rc"], b["out"], p["rc"], p["out"]))


if __name__ == "__main__":
    main()
