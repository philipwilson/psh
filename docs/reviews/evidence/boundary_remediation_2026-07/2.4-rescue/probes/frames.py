#!/usr/bin/env python3
"""Phase A frame-nesting table: which frames abort, and with what status.

Each case is a directory holding byte-exact probe files. The MAIN file is
run through each channel; helper files ($sub.sh) are sourced by it.
"""
import os
import shutil
import subprocess
import sys

import harness

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")

# name -> (main_body, {helper_name: helper_body})
CASES = {
    # ---- Group A: DIRECT (substitution error at the outer read level) -------
    "A1_direct_cmdsub": (
        "echo BEFORE\necho $(if)\necho AFTER\n", {}),
    "A2_direct_procsub": (
        "echo BEFORE\ncat <(if)\necho AFTER\n", {}),

    # ---- Group B: EVAL frame (error at eval-parse time) --------------------
    "B1_eval_cmdsub": (
        "echo BEFORE\neval 'echo $(if)'\necho AFTER\n", {}),
    "B2_eval_procsub": (
        "echo BEFORE\neval 'cat <(if)'\necho AFTER\n", {}),
    "B3_eval_plain_syntax": (
        "echo BEFORE\neval 'if'\necho AFTER\n", {}),
    "B4_eval_subscript_procsub": (
        "echo BEFORE\neval 'a[<(if)]=1'\necho AFTER\n", {}),
    "B5_eval_subscript_cmdsub": (
        "echo BEFORE\neval 'a[$(if)]=1'\necho AFTER\n", {}),

    # ---- Group C: SOURCE frame (error inside the sourced file) -------------
    "C1_source_cmdsub": (
        "echo BEFORE\nsource sub.sh\necho AFTER\n",
        {"sub.sh": "echo IN-BEFORE\necho $(if)\necho IN-AFTER\n"}),
    "C2_source_plain_syntax": (
        "echo BEFORE\nsource sub.sh\necho AFTER\n",
        {"sub.sh": "echo IN-BEFORE\nif\necho IN-AFTER\n"}),
    "C3_source_procsub": (
        "echo BEFORE\nsource sub.sh\necho AFTER\n",
        {"sub.sh": "echo IN-BEFORE\ncat <(if)\necho IN-AFTER\n"}),

    # ---- Group D: NESTED source>eval (the CORRECT-LEVEL question) ---------
    "D1_source_eval_cmdsub": (
        "echo BEFORE\nsource sub.sh\necho AFTER\n",
        {"sub.sh": "echo IN-BEFORE\neval 'echo $(if)'\necho IN-AFTER\n"}),
    "D2_eval_source_cmdsub": (
        "echo BEFORE\neval 'source sub.sh'\necho AFTER\n",
        {"sub.sh": "echo IN-BEFORE\necho $(if)\necho IN-AFTER\n"}),
    "D3_source_source_cmdsub": (
        "echo BEFORE\nsource sub.sh\necho AFTER\n",
        {"sub.sh": "echo IN-BEFORE\nsource sub2.sh\necho IN-AFTER\n",
         "sub2.sh": "echo IN2-BEFORE\necho $(if)\necho IN2-AFTER\n"}),
    "D4_eval_eval_cmdsub": (
        "echo BEFORE\neval 'echo E-BEFORE; eval \"echo \\$(if)\"; echo E-AFTER'\necho AFTER\n",
        {}),

    # ---- Group E: containment (function / subshell / cmdsub / pipeline) ----
    "E1_func_eval": (
        "f() { echo F-BEFORE; eval 'echo $(if)'; echo F-AFTER; }\n"
        "echo BEFORE\nf\necho AFTER\n", {}),
    "E2_subshell_eval": (
        "echo BEFORE\n( echo S-BEFORE; eval 'echo $(if)'; echo S-AFTER )\necho AFTER\n", {}),
    "E3_cmdsub_of_eval": (
        "echo BEFORE\nx=$(eval 'echo $(if)')\necho AFTER rc=$?\n", {}),
    "E4_pipeline_eval": (
        "echo BEFORE\neval 'echo $(if)' | cat\necho AFTER\n", {}),
    "E5_eval_in_if": (
        "echo BEFORE\nif eval 'echo $(if)'; then echo THEN; else echo ELSE; fi\necho AFTER\n", {}),
    "E6_eval_and_list": (
        "echo BEFORE\neval 'echo $(if)' && echo AND\necho AFTER\n", {}),

    # ---- Group F: status observation --------------------------------------
    "F1_eval_status": (
        "echo BEFORE\neval 'echo $(if)'\necho RC=$?\necho AFTER\n", {}),
    "F2_source_status": (
        "echo BEFORE\nsource sub.sh\necho RC=$?\necho AFTER\n",
        {"sub.sh": "echo IN-BEFORE\necho $(if)\necho IN-AFTER\n"}),

    # ---- Group G: the 6 pin params, direct --------------------------------
    "G1_param_default": ("x=set\necho ${x:-$(if)}\necho AFTER\n", {}),
    "G2_arith": ("echo $(( $(if) + 1 ))\necho AFTER\n", {}),
    "G3_subscript_read": ("a=(1 2)\necho ${a[$(if)]}\necho AFTER\n", {}),
    "G4_subscript_assign": ("a[$(if)]=v\necho AFTER\n", {}),
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


def fmt(r):
    return "rc=%s out=%r err=%s" % (
        r["rc"], r["out"], "YES" if r["err"].strip() else "no")


def main():
    only = sys.argv[1:] or list(CASES)
    for name in only:
        d, mp = prepare(name)
        print("=" * 74)
        print("CASE", name)
        main_body, helpers = CASES[name]
        print("  main.sh =", repr(main_body))
        for hn, hb in helpers.items():
            print("  %s =" % hn, repr(hb))
        for channel in ("c", "file", "stdin"):
            b = harness.run("bash", mp, channel, d)
            prd = harness.run("psh", mp, channel, d, parser="rd")
            pcb = harness.run("psh", mp, channel, d, parser="combinator")
            same = (b["rc"] == prd["rc"] and b["out"] == prd["out"])
            parsers_agree = (prd["rc"] == pcb["rc"] and prd["out"] == pcb["out"])
            print("  [%-5s] bash  %s" % (channel, fmt(b)))
            print("  [%-5s] psh/rd %s" % (channel, fmt(prd)))
            if not parsers_agree:
                print("  [%-5s] psh/cb %s   <<< PARSER SPLIT" % (channel, fmt(pcb)))
            else:
                print("  [%-5s] psh/cb (identical to rd)" % channel)
            print("  [%-5s] MATCH=%s" % (channel, "YES" if same else "*** NO ***"))


if __name__ == "__main__":
    main()
