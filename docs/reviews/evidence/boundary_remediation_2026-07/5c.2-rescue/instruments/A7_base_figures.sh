#!/bin/bash
# A7 — re-derive every base figure the brief hands me, from the TREE, not the
# brief. Each cell prints its source so the report can cite file+line.
set -uo pipefail
cd /Users/pwilson/src/psh-r5c-2
export PYTHONDONTWRITEBYTECODE=1

echo "=== HEAD ==="
git rev-parse HEAD

echo
echo "=== Q2 BROAD_MASKING ledger entries (brief: 1) ==="
python - <<'PY'
import ast, pathlib
p = pathlib.Path("tests/unit/tooling/test_broad_valueerror_catch_q2.py")
tree = ast.parse(p.read_text())
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in ("BROAD_MASKING", "NARROW_SAFE"):
                val = ast.literal_eval(node.value)
                print(f"{t.id}: {len(val)} entries  (line {node.lineno})")
                for k in val:
                    print(f"    {k!r}")
PY

echo
echo "=== terminal-handler ledger rows (brief: 24) ==="
python - <<'PY'
import ast, pathlib
p = pathlib.Path("tests/unit/tooling/test_terminal_except_ledger_5c1.py")
tree = ast.parse(p.read_text())
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id.isupper():
                try:
                    val = ast.literal_eval(node.value)
                except Exception:
                    continue
                if isinstance(val, (dict, list, set, tuple)) and len(val) > 3:
                    print(f"{t.id}: {len(val)} entries  (line {node.lineno})")
PY

echo
echo "=== consumer-ratchet ALLOWLIST (brief: 8) ==="
python - <<'PY'
import ast, pathlib
p = pathlib.Path("tests/unit/tooling/test_shell_consumer_ratchet_q1.py")
tree = ast.parse(p.read_text())
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name) and "ALLOW" in t.id.upper():
                val = ast.literal_eval(node.value)
                print(f"{t.id}: {len(val)} entries  (line {node.lineno})")
                for k in sorted(val):
                    print(f"    {k!r}")
PY
sed -n '200,212p' tests/unit/tooling/test_shell_consumer_ratchet_q1.py

echo
echo "=== caps floor (brief: 66/177/177/0) ==="
grep -rn "FUNC_IMPORT_CAPS\|_CAP\b" tests/unit/tooling/test_import_layering.py | head -20
