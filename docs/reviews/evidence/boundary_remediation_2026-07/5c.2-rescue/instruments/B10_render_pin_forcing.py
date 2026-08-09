#!/usr/bin/env python3
"""B10 — forcing proof for the R9-required _render defect pin.

A pin that would pass without the code it claims to pin is not a pin. This
neuters the raise (returns "" instead) and asserts the new test goes RED, then
restores. Failure REASON asserted, not just the outcome.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/pwilson/src/psh-r5c-2")
TARGET = REPO / "psh/builtins/parse_tree.py"
NODE = ("tests/unit/builtins/test_parse_tree_options.py::"
        "test_render_rejects_an_unknown_format_as_a_defect")
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

ANCHOR = '        raise ValueError(f"unhandled parse-tree format: {format_type!r}")'
NEUTERED = '        return ""'

original = TARGET.read_text()
assert original.count(ANCHOR) == 1, "anchor must match exactly once"


def run(label):
    p = subprocess.run([sys.executable, "-m", "pytest", NODE, "-q", "--no-header"],
                       cwd=REPO, env=ENV, capture_output=True, text=True)
    print(f"  {label}: rc={p.returncode}")
    return p


try:
    green = run("A baseline (raise present)")
    TARGET.write_text(original.replace(ANCHOR, NEUTERED, 1))
    red = run("B neutered (raise -> return '')")
finally:
    TARGET.write_text(original)
    assert TARGET.read_text() == original, "RESTORE FAILED"
    st = subprocess.run(["git", "status", "--short"], cwd=REPO,
                        capture_output=True, text=True).stdout.strip()
    print(f"[restore] byte-identity asserted; git status --short:\n{st or '  (clean)'}")

ok_green = green.returncode == 0
ok_red = red.returncode != 0 and "DID NOT RAISE" in red.stdout
print(f"\n  baseline GREEN: {ok_green}")
print(f"  neutered RED for its own reason (DID NOT RAISE): {ok_red}")
if not ok_red:
    print("  --- neutered output tail ---")
    print("\n".join(red.stdout.strip().splitlines()[-8:]))
print("\n  PIN IS FORCING" if (ok_green and ok_red) else "\n  PIN IS VACUOUS")
sys.exit(0 if (ok_green and ok_red) else 1)
