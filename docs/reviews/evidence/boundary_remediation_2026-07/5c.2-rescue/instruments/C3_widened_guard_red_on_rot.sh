#!/bin/bash
# C3 — RED-ON-ROT proof for the widened R4 (R16 constraint 2).
#
# A widened detector that lands only-ever-green is an unobserved detector. This
# runs the WIDENED guard against the PRE-FIX tree — the tree that still carried
# the dangling `io_manager.with_redirections(node.redirects)` cite — and
# requires it to go RED naming that cite. Then against the fixed tree, where it
# must be GREEN.
#
# The pre-fix tree is materialised from 46776a83 (commit xvii, before the
# one-word doc fix in xviii). Only the GUARD is taken from the current branch;
# everything else is the old tree. That is the point: new detector, old rot.
set -uo pipefail
REPO=/Users/pwilson/src/psh-r5c-2
PREFIX_SHA=46776a83
SCRATCH="$REPO/tmp/w5c2-redonrot"
export PYTHONDONTWRITEBYTECODE=1

rm -rf "$SCRATCH"; mkdir -p "$SCRATCH"
git -C "$REPO" archive "$PREFIX_SHA" | tar -x -C "$SCRATCH"
echo "pre-fix tree materialised at $PREFIX_SHA"
echo -n "  the rot is present: "
grep -c "io_manager.with_redirections" "$SCRATCH/docs/architecture/ast_data_flow.md" \
    || echo "0 (!!)"

# Transplant ONLY the widened guard into the old tree.
cp "$REPO/tests/unit/tooling/test_doc_pointers.py" \
   "$SCRATCH/tests/unit/tooling/test_doc_pointers.py"

echo
echo "===== ARM A: WIDENED guard vs PRE-FIX tree (must be RED, naming the cite)"
( cd "$SCRATCH" && python -m pytest tests/unit/tooling/test_doc_pointers.py \
    -q --no-header 2>&1 | tail -12 )
( cd "$SCRATCH" && python -m pytest tests/unit/tooling/test_doc_pointers.py \
    -q --no-header > "$SCRATCH/arm_a.txt" 2>&1 )
rc_a=$?

echo
echo "===== ARM B: WIDENED guard vs FIXED tree (must be GREEN)"
( cd "$REPO" && python -m pytest tests/unit/tooling/test_doc_pointers.py \
    -q --no-header 2>&1 | tail -3 )
( cd "$REPO" && python -m pytest tests/unit/tooling/test_doc_pointers.py \
    -q --no-header > "$SCRATCH/arm_b.txt" 2>&1 )
rc_b=$?

echo
echo "================ VERDICT"
named=0
grep -q "with_redirections" "$SCRATCH/arm_a.txt" && named=1
echo "  ARM A rc=$rc_a (want non-zero); names the dangling cite: $named"
echo "  ARM B rc=$rc_b (want 0)"
if [ "$rc_a" -ne 0 ] && [ "$named" -eq 1 ] && [ "$rc_b" -eq 0 ]; then
    echo "  RED-ON-ROT PROVEN — the widening catches the real rot it was widened for"
    rm -rf "$SCRATCH"
    exit 0
fi
echo "  PROOF FAILED"
exit 1
