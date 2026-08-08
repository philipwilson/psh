#!/bin/bash
# atk-c p01: Gap 1 (MEDIUM-7 / 4B.3 committed battery) + Gap 2 (MEDIUM-2 / 4B.2 decoder seam + 4B.4 contract suite)
# Run from the worktree with PYTHONPATH set to it. collect-only FIRST for every module, then module-scoped run.
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-c/wt
cd "$WT" || exit 1
export PYTHONPATH="$WT"

MODULES_4B3="tests/unit/builtins/test_history_flags.py \
tests/unit/interactive/test_history_state_machine_4b3.py \
tests/unit/tooling/test_history_state_machine_m8_locks_4b3.py \
tests/conformance/bash/test_history_state_machine_conformance.py"

MODULES_4B2_4B4="tests/unit/builtins/test_input_decoder_seam_4b2.py \
tests/integration/redirection/test_input_cursor_contract_4b4.py \
tests/unit/io_redirect/test_input_cursor_registry_4b4.py \
tests/unit/tooling/test_input_cursor_m8_locks_4b4.py"

echo "== GAP 1: 4B.3 battery =="
for m in $MODULES_4B3; do
  n=$(python3 -m pytest "$m" --collect-only -q 2>/dev/null | tail -1)
  echo "COLLECT $m :: $n"
done
echo "-- run --"
python3 -m pytest $MODULES_4B3 -q 2>&1 | tail -5

echo
echo "== GAP 2: 4B.2 decoder seam + 4B.4 contract =="
for m in $MODULES_4B2_4B4; do
  if [ -f "$m" ]; then
    n=$(python3 -m pytest "$m" --collect-only -q 2>/dev/null | tail -1)
    echo "COLLECT $m :: $n"
  else
    echo "MISSING $m"
  fi
done
echo "-- run --"
python3 -m pytest $MODULES_4B2_4B4 -q 2>&1 | tail -5
