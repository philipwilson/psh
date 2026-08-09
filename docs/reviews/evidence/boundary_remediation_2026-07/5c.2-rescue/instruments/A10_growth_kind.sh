#!/bin/bash
# A10 — SECOND METHOD for the read_builtin/parse_tree "hub growth" claim.
# A9 answered it from the AST (per-line classification at each SHA). This
# answers it from the DIFF (classify every added/removed line by kind), so the
# two methods share no machinery — D-3.5: a verification that mirrors the
# claim's method cannot find the claim's error.
set -uo pipefail
cd /Users/pwilson/src/psh-r5c-2

for f in psh/builtins/read_builtin.py psh/builtins/parse_tree.py; do
  echo "######## $f  (d8166242 -> 67261b29, i.e. v0.776 -> v0.777 = slot 5C.1)"
  git diff d8166242 67261b29 -- "$f" | python - "$f" <<'PY'
import sys, re
added_code = added_cmt = added_blank = 0
removed_code = removed_cmt = removed_blank = 0
for line in sys.stdin:
    if line.startswith('+++') or line.startswith('---'):
        continue
    if line.startswith('+'):
        body = line[1:].strip()
        if not body:
            added_blank += 1
        elif body.startswith('#'):
            added_cmt += 1
        else:
            added_code += 1
    elif line.startswith('-'):
        body = line[1:].strip()
        if not body:
            removed_blank += 1
        elif body.startswith('#'):
            removed_cmt += 1
        else:
            removed_code += 1
print(f"  added:   code={added_code:3d} comment={added_cmt:3d} blank={added_blank:3d}")
print(f"  removed: code={removed_code:3d} comment={removed_cmt:3d} blank={removed_blank:3d}")
print(f"  NET:     code={added_code-removed_code:+4d} comment={added_cmt-removed_cmt:+4d} "
      f"blank={added_blank-removed_blank:+4d}")
PY
  echo
done

echo "######## the actual 5C.1 hunk in read_builtin.py (what the +11 IS)"
git diff d8166242 67261b29 -- psh/builtins/read_builtin.py | sed -n '1,80p'
