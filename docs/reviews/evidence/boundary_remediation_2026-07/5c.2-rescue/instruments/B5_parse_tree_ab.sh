#!/bin/bash
# B5 — A/B byte-identity for parse-tree across every format and error path.
# Base tree materialised by A3 (git archive of 3a3e0782); current tree is the
# worktree. Neither side generates the stimulus (4B.2 lesson 1): the case list
# is fixed text here.
set -uo pipefail
BASE=/Users/pwilson/src/psh-r5c-2/tmp/w5c2-scratch/base-3a3e0782
NOW=/Users/pwilson/src/psh-r5c-2
export PYTHONDONTWRITEBYTECODE=1

cases=(
  "parse-tree echo hi"
  "parse-tree -f tree echo hi"
  "parse-tree -f pretty echo hi"
  "parse-tree -f compact echo hi"
  "parse-tree -f dot echo hi"
  "parse-tree -p -f tree echo hi"
  "parse-tree -f pretty if true; then echo a; fi"
  "parse-tree -f compact for i in 1 2; do echo \$i; done"
  "parse-tree -f dot a | b && c"
  "parse-tree"
  "parse-tree -f"
  "parse-tree -f bogus echo hi"
  "parse-tree -z echo hi"
  "parse-tree -h"
  "parse-tree --help"
  "parse-tree -p"
  "parse-tree echo 'unclosed"
  "parse-tree -f tree \$(((((("
)

fail=0
for c in "${cases[@]}"; do
    a_out=$(cd "$BASE" && python -m psh -c "$c" 2>&1); a_rc=$?
    b_out=$(cd "$NOW" && python -m psh -c "$c" 2>&1); b_rc=$?
    if [ "$a_out" == "$b_out" ] && [ "$a_rc" == "$b_rc" ]; then
        echo "  IDENTICAL (rc=$a_rc)  $c"
    else
        fail=1
        echo "  *** DIVERGED  $c"
        echo "      base rc=$a_rc now rc=$b_rc"
        diff <(printf '%s' "$a_out") <(printf '%s' "$b_out") | head -12
    fi
done
echo
if [ "$fail" -eq 0 ]; then
    echo "VERDICT: byte-identical on all ${#cases[@]} cases (stdout+stderr+rc)"
else
    echo "VERDICT: DIVERGENCE — zero-delta claim broken"
fi
exit $fail
