#!/bin/bash
# atk-c p02: Gap 3 — run ONE PTY module foreground (sanctioned for atk-c only).
# Usage: p02_pty_one_module.sh <module-path-relative-to-worktree>
# collect-only FIRST, then the module run. Caller enforces the ~3 min kill.
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-c/wt
cd "$WT" || exit 1
export PYTHONPATH="$WT"
m="$1"
[ -f "$m" ] || { echo "MISSING $m"; exit 2; }
echo "COLLECT $m :: $(python3 -m pytest "$m" --collect-only -q 2>/dev/null | tail -1)"
echo "-- run ($m) --"
python3 -m pytest "$m" -q 2>&1 | tail -5
