#!/usr/bin/env python3
"""R16 item 1: re-derive the exact/permissive/blind counts from the SHIPPED code.

The 19-exact / 8-permissive / 2-blind figures quoted in
`psh/scripting/analysis_session.py`'s module docstring and throughout the
ledger came from `score_rules.py`, which folds candidate rules over a
HAND-MODELLED table of each script's structural properties. dev-2-6 flagged
that table as the one human transcription sitting between the code and the
conclusion, and never went back to it; R16 makes re-verifying it binding.

This removes the hand model entirely. It measures what the SHIPPED analysis
actually does against what execution actually does, over battery C's own
corpus, and derives the counts from those measurements — so the docstring's
numbers describe the code rather than a model of a rule the code implements.

  EXACT        analysis agrees with execution about the option
  PERMISSIVE   analysis accepts where execution's detector fails (a superset:
               can miss a real error, never invents one)
  FALSE-ERROR  analysis rejects what execution runs — the reported defect

Oracle: psh execution at the tree under test. `c_after_exit` is reported
separately: its detector line is unreachable at run time too, so execution has
no observable answer and the row cannot be scored either way.

Usage: PSH_ROOT=<tree> [PSH_SHA=<sha>] python rederive_rule_outcomes.py
"""
import json
import os
import sys

import harness

USE = "echo @(a|b)\n"

SCRIPTS = {
    # reached, not isolated
    "c_toplevel": "shopt -s extglob\n" + USE,
    "c_semicolon": "true; shopt -s extglob\n" + USE,
    "c_if_true": "if true; then shopt -s extglob; fi\n" + USE,
    "c_and_true": "true && shopt -s extglob\n" + USE,
    "c_or_false": "false || shopt -s extglob\n" + USE,
    "c_brace": "{ shopt -s extglob; }\n" + USE,
    "c_for_one": "for i in a; do shopt -s extglob; done\n" + USE,
    "c_case_hit": "case a in a) shopt -s extglob;; esac\n" + USE,
    "c_func_called": "e() { shopt -s extglob; }\ne\n" + USE,
    "c_func_nested": "i() { shopt -s extglob; }\no() { i; }\no\n" + USE,
    "c_eval": "eval 'shopt -s extglob'\n" + USE,
    "c_source": "printf 'shopt -s extglob\\n' > sub.sh\n. ./sub.sh\n" + USE,
    "c_setopt_spelling": "set -o extglob\n" + USE,
    # not reached
    "c_if_false": "if false; then shopt -s extglob; fi\n" + USE,
    "c_and_false": "false && shopt -s extglob\n" + USE,
    "c_or_true": "true || shopt -s extglob\n" + USE,
    "c_for_zero": "for i in; do shopt -s extglob; done\n" + USE,
    "c_case_miss": "case z in a) shopt -s extglob;; esac\n" + USE,
    "c_func_uncalled": "e() { shopt -s extglob; }\n" + USE,
    "c_after_exit": "exit 0\nshopt -s extglob\n" + USE,
    "c_while_zero": "while false; do shopt -s extglob; done\n" + USE,
    # reached but state-isolated
    "c_subshell": "( shopt -s extglob )\n" + USE,
    "c_pipeline": "shopt -s extglob | cat\n" + USE,
    "c_background": "shopt -s extglob &\nwait\n" + USE,
    "c_cmdsub": "x=$(shopt -s extglob)\n" + USE,
    "c_procsub": "cat <(shopt -s extglob) >/dev/null\n" + USE,
    # disable direction
    "c_disable_uncond": "shopt -s extglob\nshopt -u extglob\n" + USE,
    "c_disable_if_false": ("shopt -s extglob\nif false; then shopt -u extglob; fi\n"
                           + USE),
    "c_disable_subshell": "shopt -s extglob\n( shopt -u extglob )\n" + USE,
    "c_disable_then_enable": ("shopt -s extglob\nshopt -u extglob\n"
                              "shopt -s extglob\n" + USE),
}

UNSCORABLE = {"c_after_exit"}   # execution never reaches the detector either


def main() -> int:
    root = os.environ["PSH_ROOT"]
    sha = harness.validate_root(root, os.environ.get("PSH_SHA"))
    cwd = harness.neutral_cwd()
    rows, counts = [], {"EXACT": 0, "PERMISSIVE": 0, "FALSE-ERROR": 0}
    for name, text in SCRIPTS.items():
        files = {"s.sh": text}
        ex = harness.run_psh(root, ["s.sh"], stdin_text=None, files=files, cwd=cwd)
        va = harness.run_psh(root, ["--validate", "s.sh"], stdin_text=None,
                             files=files, cwd=cwd)
        if not (ex["discrim_ok"] and va["discrim_ok"]):
            print(f"DISCRIMINATOR INVALID on {name}", file=sys.stderr)
            return 3
        execution_live = ex["rc"] == 0
        analysis_live = va["rc"] != 2
        if name in UNSCORABLE:
            verdict = "UNSCORABLE"
        elif analysis_live == execution_live:
            verdict = "EXACT"
        elif analysis_live:
            verdict = "PERMISSIVE"
        else:
            verdict = "FALSE-ERROR"
        if verdict in counts:
            counts[verdict] += 1
        rows.append(dict(id=name, sha=sha, exec_rc=ex["rc"], validate_rc=va["rc"],
                         execution_live=execution_live,
                         analysis_live=analysis_live, verdict=verdict))

    width = max(len(r["id"]) for r in rows)
    for r in sorted(rows, key=lambda r: (r["verdict"], r["id"])):
        print(f"  {r['id']:<{width}}  exec rc={r['exec_rc']}  "
              f"validate rc={r['validate_rc']}  {r['verdict']}")
    scored = sum(counts.values())
    print(f"\nDERIVED from the shipped code at {sha[:8]} over {len(rows)} "
          f"scripts ({scored} scorable, {len(UNSCORABLE)} unscorable):")
    for k in ("EXACT", "PERMISSIVE", "FALSE-ERROR"):
        print(f"  {k:<12} {counts[k]}")
    if counts["FALSE-ERROR"]:
        print("\n  FALSE-ERROR rows are the reported defect — analysis "
              "inventing a syntax error for a script that runs:")
        for r in rows:
            if r["verdict"] == "FALSE-ERROR":
                print(f"    {r['id']}")
    with open(os.path.join(os.path.dirname(__file__),
                           "results_rule_outcomes.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
