#!/usr/bin/env python3
"""A10b — classify every added/removed diff line by kind (code/comment/blank).

SECOND METHOD for the "hub growth" claim: A9 classifies per-line from the AST at
each SHA; this classifies the DIFF itself. The two share no machinery (D-3.5:
a verification mirroring the claim's method cannot find the claim's error).

Usage: A10b_diff_classify.py <old_sha> <new_sha> <path> [<path>...]
Runs `git diff` itself rather than reading stdin — the earlier inline-heredoc
form silently classified an EMPTY stream, because `python - ` takes its program
from stdin and the heredoc had already claimed it. Instruments are files.
"""
import subprocess
import sys

old, new, paths = sys.argv[1], sys.argv[2], sys.argv[3:]

for path in paths:
    diff = subprocess.run(
        ["git", "diff", old, new, "--", path],
        capture_output=True, text=True, check=True).stdout
    counts = {"added": {"code": 0, "comment": 0, "blank": 0},
              "removed": {"code": 0, "comment": 0, "blank": 0}}
    for line in diff.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            side = "added"
        elif line.startswith("-"):
            side = "removed"
        else:
            continue
        body = line[1:].strip()
        kind = "blank" if not body else ("comment" if body.startswith("#") else "code")
        counts[side][kind] += 1

    a, r = counts["added"], counts["removed"]
    print(f"######## {path}  ({old} -> {new})")
    print(f"  added:   code={a['code']:3d} comment={a['comment']:3d} blank={a['blank']:3d}")
    print(f"  removed: code={r['code']:3d} comment={r['comment']:3d} blank={r['blank']:3d}")
    print(f"  NET:     code={a['code'] - r['code']:+4d} "
          f"comment={a['comment'] - r['comment']:+4d} "
          f"blank={a['blank'] - r['blank']:+4d}")
    print()
