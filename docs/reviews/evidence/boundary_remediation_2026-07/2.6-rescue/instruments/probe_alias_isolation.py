#!/usr/bin/env python3
"""R21-B(1): the alias-axis ISOLATION asymmetry, measured before it is pinned.

The option axis honours state isolation (a `shopt -s` inside a subshell dies
with it). The ALIAS axis does not: absorption runs over each unit's token
stream wherever the definition sits. This measures the divergent direction so
the pin states what is true rather than what the rule says.
"""
import os
import sys

import harness

CASES = [
    ("subshell_def",   "( alias iff='if true; then' )\niff echo X; fi\n"),
    ("pipeline_def",   "alias iff='if true; then' | cat\niff echo X; fi\n"),
    ("background_def", "alias iff='if true; then' &\nwait\niff echo X; fi\n"),
    ("cmdsub_def",     "x=$(alias iff='if true; then')\niff echo X; fi\n"),
    ("isolated_unalias",
     "alias iff='if true; then'\n( unalias -a )\niff echo X; fi\n"),
]


def main() -> int:
    root = os.environ["PSH_ROOT"]
    sha = harness.validate_root(root, os.environ.get("PSH_SHA"))
    cwd = harness.neutral_cwd()
    print(f"{'case':18} {'exec':>5} {'validate':>9}  verdict   (tree {sha[:8]})")
    print("-" * 62)
    for name, text in CASES:
        files = {"s.sh": text}
        ex = harness.run_psh(root, ["s.sh"], stdin_text=None, files=files, cwd=cwd)
        va = harness.run_psh(root, ["--validate", "s.sh"], stdin_text=None,
                             files=files, cwd=cwd)
        if not (ex["discrim_ok"] and va["discrim_ok"]):
            print(f"DISCRIMINATOR INVALID on {name}", file=sys.stderr)
            return 3
        agree = (ex["rc"] == 0) == (va["rc"] == 0)
        verdict = "agree" if agree else (
            "analysis ABSORBED an isolated def" if va["rc"] == 0
            else "analysis NARROWED on an isolated unalias")
        print(f"{name:18} {ex['rc']:>5} {va['rc']:>9}  {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
