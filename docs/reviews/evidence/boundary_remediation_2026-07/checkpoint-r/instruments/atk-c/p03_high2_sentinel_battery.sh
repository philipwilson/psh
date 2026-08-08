#!/bin/bash
# atk-c p03: Gap 4 — HIGH-2 generated sentinel battery (traversal totality), collect-only FIRST then module run.
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-c/wt
cd "$WT" || exit 1
export PYTHONPATH="$WT"
M=tests/unit/visitor/test_traversal_totality_battery.py
echo "COLLECT $M :: $(python3 -m pytest "$M" --collect-only -q 2>/dev/null | tail -1)"
echo "-- node list (first 12 + last 3) --"
python3 -m pytest "$M" --collect-only -q 2>/dev/null | head -12
python3 -m pytest "$M" --collect-only -q 2>/dev/null | tail -4
echo "-- run --"
python3 -m pytest "$M" -q 2>&1 | tail -3
