#!/bin/bash
# atk-c p07: Gap 2/coverage completion — the 4B.2 read-exact NON-PTY arm
# (tests/unit/builtins/test_read_exact_timeout_4b2.py), collect-only first,
# plus the decoder-seam module's collected node names so the s1 (18-cell
# timeout-partial table), s2 (-N count model) and s3 (read -s -N echo)
# declared-contract cell classes are shown PRESENT (charter rule: show the
# collected set, not the summary).
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-c/wt
cd "$WT" || exit 1
export PYTHONPATH="$WT"

M=tests/unit/builtins/test_read_exact_timeout_4b2.py
echo "COLLECT $M :: $(python3 -m pytest "$M" --collect-only -q 2>/dev/null | tail -1)"
echo "-- run --"
python3 -m pytest "$M" -q 2>&1 | tail -3

echo
echo "== decoder-seam collected node names (full set) =="
python3 -m pytest tests/unit/builtins/test_input_decoder_seam_4b2.py --collect-only -q 2>/dev/null
