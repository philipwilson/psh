#!/usr/bin/env python3
"""ROUND 2: the ERROR-KIND axis the round-1 corpus held constant.

Round 1 varied the SPELLING ($(), <(), ${x:-}, $(()), ${a[]}, a[]=) but every
body was the at-EOF/NeedMore kind (`if`). The complete-but-invalid kind (`fi`,
`;`, `;;`, `done`, ...) completes the accumulator's trial parse and takes the
OTHER SourceProcessor exit, which round 1 left unwired.

Bodies are written as explicit BYTES (no Python escape processing) and od -c
verified by the caller; one case per shell invocation; both parsers.
"""
import os
import shutil
import sys

import harness_tip1 as harness

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work-errorkind")

# name -> (main body bytes, {helper: bytes})
CASES = {
    # --- the 6 pin spellings, COMPLETE-but-invalid body ------------------
    "k1_cmdsub":      (b"echo B\necho $(fi)\necho AFTER\n", {}),
    "k2_procsub":     (b"echo B\ncat <(fi)\necho AFTER\n", {}),
    "k3_param":       (b"echo B\nx=set; echo ${x:-$(fi)}\necho AFTER\n", {}),
    "k4_arith":       (b"echo B\necho $(( $(fi) + 1 ))\necho AFTER\n", {}),
    "k5_subscr_read": (b"echo B\na=(1 2); echo ${a[$(fi)]}\necho AFTER\n", {}),
    "k6_subscr_asgn": (b"echo B\na[$(fi)]=v\necho AFTER\n", {}),

    # --- other error kinds inside the complete-but-invalid class ---------
    "k7_bare_semi":   (b"echo B\necho $(;)\necho AFTER\n", {}),
    "k8_dsemi":       (b"echo B\necho $(x ;; y)\necho AFTER\n", {}),
    "k9_done":        (b"echo B\necho $(done)\necho AFTER\n", {}),
    "k10_esac":       (b"echo B\necho $(esac)\necho AFTER\n", {}),
    "k11_then":       (b"echo B\necho $(then)\necho AFTER\n", {}),
    "k12_lead_pipe":  (b"echo B\necho $(| x)\necho AFTER\n", {}),
    "k13_lead_and":   (b"echo B\necho $(&& x)\necho AFTER\n", {}),

    # --- FRAME FATALITY for the new class --------------------------------
    "f1_eval":        (b"echo B\neval 'echo $(fi)'\necho AFTER\n", {}),
    "f2_eval_procsub": (b"echo B\neval 'cat <(fi)'\necho AFTER\n", {}),
    "f3_source":      (b"echo B\nsource inner.sh\necho AFTER\n",
                       {"inner.sh": b"echo IB\necho $(fi)\necho IA\n"}),
    "f4_function":    (b"f() { eval \"echo \\$(fi)\"; }\necho B\nf\necho AFTER\n", {}),
    "f5_source_eval": (b"echo B\nsource inner.sh\necho AFTER\n",
                       {"inner.sh": b"echo IB\neval 'echo $(fi)'\necho IA\n"}),
    "f6_if_cond":     (b"echo B\nif eval 'echo $(fi)'; then echo T; fi\necho AFTER\n", {}),
    "f7_and_list":    (b"echo B\neval 'echo $(fi)' && echo AND\necho AFTER\n", {}),

    # --- frame model re-verification for the new class -------------------
    "m1_subshell":    (b"echo B\n( eval 'echo $(fi)' )\necho AFTER rc=$?\n", {}),
    "m2_cmdsub":      (b"echo B\nx=$(eval 'echo $(fi)')\necho AFTER rc=$?\n", {}),
    "m3_pipeline":    (b"echo B\neval 'echo $(fi)' | cat\necho AFTER rc=$?\n", {}),
    "m4_bg":          (b"echo B\neval 'echo $(fi)' &\nwait\necho AFTER rc=$?\n", {}),
    "m5_exit_trap":   (b"trap 'echo T rc=$?' EXIT\necho B\neval 'echo $(fi)'\n", {}),
    "m6_errexit":     (b"set -e\necho B\neval 'echo $(fi)'\necho AFTER\n", {}),
    "m7_errexit_dir": (b"set -e\necho B\necho $(fi)\necho AFTER\n", {}),
    "m8_cmd_eval":    (b"echo B\ncommand eval 'echo $(fi)'\necho AFTER\n", {}),
    "m9_builtin_eval": (b"echo B\nbuiltin eval 'echo $(fi)'\necho AFTER\n", {}),

    # --- CONTROLS --------------------------------------------------------
    "c1_plain_fi":    (b"echo B\nfi\necho AFTER\n", {}),
    "c2_plain_eval":  (b"echo B\neval 'fi'\necho AFTER\n", {}),
    "c3_ateof_if":    (b"echo B\necho $(if)\necho AFTER\n", {}),
    "c4_ateof_eval":  (b"echo B\neval 'echo $(if)'\necho AFTER\n", {}),
}


def prepare(name):
    d = os.path.join(WORK, name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    body, helpers = CASES[name]
    mp = os.path.join(d, "main.sh")
    with open(mp, "wb") as f:
        f.write(body)
    for hn, hb in helpers.items():
        with open(os.path.join(d, hn), "wb") as f:
            f.write(hb)
    return d, mp


def main():
    mismatches = splits = rows = 0
    for name in (sys.argv[1:] or list(CASES)):
        d, mp = prepare(name)
        for ch in ("c", "file", "stdin"):
            b = harness.run("bash", mp, ch, d)
            r = harness.run("psh", mp, ch, d, parser="rd")
            c = harness.run("psh", mp, ch, d, parser="combinator")
            rows += 1
            ok = (b["rc"] == r["rc"] and b["out"] == r["out"])
            same = (r["rc"] == c["rc"] and r["out"] == c["out"])
            if not ok:
                mismatches += 1
            if not same:
                splits += 1
            if not ok or not same:
                print("  %-16s %-5s bash rc=%-4s out=%-24r | psh rc=%-4s "
                      "out=%-24r %s%s" % (
                          name, ch, b["rc"], b["out"], r["rc"], r["out"],
                          "MISMATCH" if not ok else "",
                          " PARSER-SPLIT" if not same else ""))
    print("rows=%d  mismatches=%d  parser_splits=%d" % (rows, mismatches, splits))


if __name__ == "__main__":
    main()
