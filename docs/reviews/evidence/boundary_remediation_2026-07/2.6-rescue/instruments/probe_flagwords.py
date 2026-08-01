#!/usr/bin/env python3
"""R15-B-B/F: measure the shopt FLAG-WORD ARRANGEMENT axis before encoding it.

The claim `_option_changes` makes quantifies over how a shopt command's flag
words are ARRANGED (before/after the operand, clustered, `--`-terminated, bad
letters, `-o`). The round-4 fix held that axis constant at "flags precede the
operand" and encoded the measurement for that shape only, which is how
`shopt -q extglob -s` came to invent an enable the shell declines to make.

Each row runs a TWO-UNIT script: the directive, then a detector that only
parses when the option is live. So execution's rc is a direct readout of
whether the shell really changed the option, and psh --validate's rc is a
readout of what analysis BELIEVES. Oracle: PATH bash 5.2.26 at
/opt/homebrew/bin/bash (never /bin/bash), execution surface.

Usage: PSH_ROOT=<tree> [PSH_SHA=<sha>] python probe_flagwords.py
"""
import json
import os
import sys

import harness

EXTGLOB_DETECT = "case ab in +(a)b) echo MATCH;; esac\n"
ALIAS_DETECT = "iff echo X; fi\n"

# (id, directive line, axis) — the detector is appended as unit 2.
CASES = [
    # --- option axis (extglob): flag-word arrangement ---------------------
    ("plain_enable",        "shopt -s extglob",            "extglob"),
    ("flag_after_operand",  "shopt -s extglob -u",         "extglob"),
    ("query_then_flag",     "shopt -q extglob -s",         "extglob"),
    ("operand_first",       "shopt extglob -s",            "extglob"),
    ("separate_conflict",   "shopt -s -u extglob",         "extglob"),
    ("clustered_conflict",  "shopt -su extglob",           "extglob"),
    ("unset_then_flag",     "shopt -u extglob -s",         "extglob"),
    ("ddash_after_flags",   "shopt -s -- extglob",         "extglob"),
    ("ddash_first",         "shopt -- -s extglob",         "extglob"),
    ("clustered_sq",        "shopt -sq extglob",           "extglob"),
    ("two_operands",        "shopt -s extglob dotglob",    "extglob"),
    ("bad_flag_letter",     "shopt -z -s extglob",         "extglob"),
    ("irrelevant_operand",  "shopt -s dotglob -s",         "extglob"),
    ("set_o_path",          "shopt -so extglob",           "extglob"),
    ("o_after_operand",     "shopt -s extglob -o",         "extglob"),
    # --- alias axis (expand_aliases): the same arrangements ---------------
    ("ea_plain_disable",    "shopt -u expand_aliases",     "alias"),
    ("ea_flag_after_op",    "shopt -u expand_aliases -s",  "alias"),
    ("ea_query_then_flag",  "shopt -q expand_aliases -u",  "alias"),
    ("ea_separate_conflict", "shopt -s -u expand_aliases", "alias"),
    ("ea_operand_first",    "shopt expand_aliases -u",     "alias"),
]


def script_for(directive: str, axis: str) -> str:
    if axis == "alias":
        # The alias is defined FIRST, so the directive decides whether the
        # later use expands. Without expansion `iff echo X; fi` is a syntax
        # error, so rc reads out the option exactly as the extglob detector.
        return f"alias iff='if true; then'\n{directive}\n{ALIAS_DETECT}"
    return f"{directive}\n{EXTGLOB_DETECT}"


def main() -> int:
    root = os.environ["PSH_ROOT"]
    sha = harness.validate_root(root, os.environ.get("PSH_SHA"))
    cwd = harness.neutral_cwd()
    rows = []
    for cid, directive, axis in CASES:
        text = script_for(directive, axis)
        files = {"s.sh": text}
        ex = harness.run_psh(root, ["s.sh"], stdin_text=None, files=files, cwd=cwd)
        va = harness.run_psh(root, ["--validate", "s.sh"], stdin_text=None,
                             files=files, cwd=cwd)
        bs = harness.run_bash(["s.sh"], stdin_text=None, files=files, cwd=cwd)
        # Execution's verdict on whether the option is LIVE for the detector.
        live_psh = ex["rc"] == 0
        live_bash = bs["rc"] == 0
        analysis_live = va["rc"] == 0
        rows.append({
            "id": cid, "axis": axis, "directive": directive, "sha": sha,
            "psh_exec_rc": ex["rc"], "bash_exec_rc": bs["rc"],
            "validate_rc": va["rc"],
            "live_psh": live_psh, "live_bash": live_bash,
            "analysis_live": analysis_live,
            "agree": analysis_live == live_psh,
            "psh_bash_agree": live_psh == live_bash,
            "discrim_ok": ex["discrim_ok"] and va["discrim_ok"],
            "validate_stderr": va["stderr"].strip()[:120],
            "oracle": bs["oracle"],
        })
    bad = [r for r in rows if not r["discrim_ok"]]
    if bad:
        print(f"DISCRIMINATOR INVALID on {len(bad)} rows", file=sys.stderr)
        return 3
    hdr = f"{'id':22} {'directive':28} {'psh':>4} {'bash':>5} {'val':>4}  verdict"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        if r["agree"]:
            verdict = "agree"
        elif r["analysis_live"] and not r["live_psh"]:
            verdict = "FALSE-GREEN (invents an enable)"
        else:
            verdict = "FALSE-RED (misses a real enable)"
        flag = "" if r["psh_bash_agree"] else "  [psh!=bash]"
        print(f"{r['id']:22} {r['directive']:28} {r['psh_exec_rc']:>4} "
              f"{r['bash_exec_rc']:>5} {r['validate_rc']:>4}  {verdict}{flag}")
    with open(os.path.join(os.path.dirname(__file__),
                           "results_flagwords.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    dis = [r for r in rows if not r["agree"]]
    print(f"\n{len(rows)} rows, {len(dis)} disagreements "
          f"(oracle {rows[0]['oracle']}, execution surface)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
