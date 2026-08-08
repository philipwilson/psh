#!/bin/sh
# Q5: LOW printf %a/%A Wave-5 rider — current repro at ae871a16.
# DIVERGENCE axis (tip vs bash 5.2.26). Run with cwd = the Q5 worktree so
# `python3 -m psh` resolves the worktree tree (discriminator asserted earlier).
BASH=/opt/homebrew/bin/bash
PY=python3
echo "== bash version: $($BASH --version | head -1)"
for fmt in '%.2a' '%a' '%.3A' '%#a'; do
  for val in 3.14 1.5 0.1; do
    b=$($BASH -c "printf '$fmt\n' $val" 2>&1); brc=$?
    p=$($PY -m psh -c "printf '$fmt\n' $val" 2>&1); prc=$?
    match=DIFF
    [ "$b" = "$p" ] && [ "$brc" = "$prc" ] && match=SAME
    printf '%s fmt=%s val=%s bash=[%s] rc=%s psh=[%s] rc=%s\n' "$match" "$fmt" "$val" "$b" "$brc" "$p" "$prc"
  done
done
