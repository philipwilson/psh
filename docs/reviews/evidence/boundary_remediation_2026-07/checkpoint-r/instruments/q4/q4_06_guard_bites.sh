#!/bin/sh
# Q4: mutation-prove the import-layering guard bites, in the Q4 WORKTREE ONLY.
# Offender A: psh/utils/zz_q4_offender.py imports psh.executor at module level
#   -> must fail test_utils_is_a_runtime_leaf (and, since utils<-everything,
#      potentially the cycle test too).
# Offender B: psh/lexer/zz_q4_offender_b.py with a function-body psh import
#   in a module with no cap entry -> must fail test_function_level_import_ratchet.
# Both offenders are then deleted and the guard must pass again.
set -u
WT="$1"
OUT="$2"
cd "$WT" || exit 1

echo "=== offender A: utils leaf violation ===" > "$OUT"
cat > psh/utils/zz_q4_offender.py <<'EOF'
from ..executor import core as _core  # synthetic Q4 offender (module-level)
EOF
PYTHONPATH="$WT" python3 -m pytest tests/unit/tooling/test_import_layering.py -q 2>&1 | tail -8 >> "$OUT"
rm psh/utils/zz_q4_offender.py

echo "=== offender B: uncapped deferred import ===" >> "$OUT"
cat > psh/lexer/zz_q4_offender_b.py <<'EOF'
def f():
    from ..executor import core as _core  # synthetic Q4 offender (deferred)
EOF
PYTHONPATH="$WT" python3 -m pytest tests/unit/tooling/test_import_layering.py -q 2>&1 | tail -8 >> "$OUT"
rm psh/lexer/zz_q4_offender_b.py

echo "=== clean re-run after removing offenders ===" >> "$OUT"
PYTHONPATH="$WT" python3 -m pytest tests/unit/tooling/test_import_layering.py -q 2>&1 | tail -3 >> "$OUT"

echo "=== git status of worktree psh/ (must be clean) ===" >> "$OUT"
git -C "$WT" status --porcelain -- psh/ >> "$OUT"
echo "DONE" >> "$OUT"
