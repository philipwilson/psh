#!/bin/bash
# B6 — A/B byte-identity for `test` unary operators across every arm the
# decomposition touched, plus the arms it deliberately left inline.
# Base = materialised 3a3e0782 checkout; NOW = the worktree. Fixtures are
# created by THIS script (neither shell under test generates the stimulus).
set -uo pipefail
BASE=/Users/pwilson/src/psh-r5c-2/tmp/w5c2-scratch/base-3a3e0782
NOW=/Users/pwilson/src/psh-r5c-2
export PYTHONDONTWRITEBYTECODE=1

FIX=$(mktemp -d "/Users/pwilson/src/psh-r5c-2/tmp/w5c2-fixtures.XXXXXX")
trap 'rm -rf "$FIX"' EXIT
mkdir -p "$FIX/dir"
echo content > "$FIX/file"
: > "$FIX/empty"
ln -s "$FIX/file" "$FIX/link"
ln -s "$FIX/nonexistent" "$FIX/broken"
mkfifo "$FIX/fifo"
chmod 4755 "$FIX/setuid" 2>/dev/null || { : > "$FIX/setuid"; chmod 4755 "$FIX/setuid"; }
: > "$FIX/setgid"; chmod 2755 "$FIX/setgid"
mkdir -p "$FIX/sticky"; chmod 1755 "$FIX/sticky"
: > "$FIX/noread"; chmod 000 "$FIX/noread"

# every unary operator the builtin implements, over every fixture kind
ops=(-z -n -f -d -e -r -w -x -s -L -h -b -c -p -S -k -u -g -O -G -N -t -v -R -o)
targets=("$FIX/file" "$FIX/dir" "$FIX/empty" "$FIX/link" "$FIX/broken"
         "$FIX/fifo" "$FIX/setuid" "$FIX/setgid" "$FIX/sticky" "$FIX/noread"
         "$FIX/missing" "/dev/null" "/dev/tty" "" "0" "1" "2" "abc" "PATH"
         "errexit" "nosuchopt")

fail=0; n=0
for op in "${ops[@]}"; do
  for t in "${targets[@]}"; do
      n=$((n+1))
      script="test $op \"$t\"; echo rc=\$?"
      a=$(cd "$BASE" && python -m psh -c "$script" 2>&1); arc=$?
      b=$(cd "$NOW"  && python -m psh -c "$script" 2>&1); brc=$?
      if [ "$a" != "$b" ] || [ "$arc" != "$brc" ]; then
          fail=1
          echo "  *** DIVERGED  test $op '$t'"
          echo "      base: rc=$arc [$a]"
          echo "      now : rc=$brc [$b]"
      fi
  done
done

echo "cases compared: $n"
if [ "$fail" -eq 0 ]; then
    echo "VERDICT: byte-identical on all $n cases (stdout+stderr+rc)"
else
    echo "VERDICT: DIVERGENCE — zero-delta claim broken"
fi
exit $fail
