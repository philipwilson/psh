#!/bin/sh
# Q4 axis-6: bounded local re-run of the two un-quarantined exit-trap
# sentinel tests (LEDGER EXIT-trap row gate classification), 10 iterations
# each = 20 total (the charter's <=20 allowance). Node-ID pytest runs only,
# serial, foregrounded. cwd = Q4 worktree; PYTHONPATH = worktree.
set -u
WT="$1"
OUT="$2"
cd "$WT" || exit 1
N1="tests/integration/job_control/test_exit_trap_paths.py::TestExitTrapOnFatalSignal::test_exit_in_exit_trap_matches_bash_sigterm"
N2="tests/integration/job_control/test_exit_trap_paths.py::TestExitTrapOnFatalSignal::test_exit0_in_exit_trap_command_mode_dies_by_signal"
: > "$OUT"
p1=0; f1=0; p2=0; f2=0
i=1
while [ $i -le 10 ]; do
  if PYTHONPATH="$WT" python3 -m pytest "$N1" -q --no-header -x >> "$OUT" 2>&1; then
    p1=$((p1+1)); else f1=$((f1+1)); fi
  i=$((i+1))
done
i=1
while [ $i -le 10 ]; do
  if PYTHONPATH="$WT" python3 -m pytest "$N2" -q --no-header -x >> "$OUT" 2>&1; then
    p2=$((p2+1)); else f2=$((f2+1)); fi
  i=$((i+1))
done
echo "SENTINEL-A (exit_in_exit_trap_matches_bash_sigterm): pass=$p1 fail=$f1 /10" | tee -a "$OUT"
echo "SENTINEL-B (exit0_in_exit_trap_command_mode_dies_by_signal): pass=$p2 fail=$f2 /10" | tee -a "$OUT"
