#!/bin/bash
# B14 — gate pre-registration terms, each DERIVED per file by --collect-only.
# R7 §3: the count moves DOWN by the test-side deletion terms before it moves
# UP by new suites, and both halves must be named, not netted.
set -uo pipefail
cd /Users/pwilson/src/psh-r5c-2
export PYTHONDONTWRITEBYTECODE=1

echo "=== HEAD ==="; git rev-parse HEAD

# Both helpers print EXACTLY one integer. `grep -c` prints 0 AND exits 1 when
# it finds nothing, so a `|| echo 0` fallback emits TWO numbers and the
# arithmetic downstream dies — which is how the first run of this script
# failed. Capture, then default an empty capture.
count() {  # collected count at the CURRENT tree
    local n
    n=$(python -m pytest "$1" --collect-only -q 2>/dev/null | tail -1 \
        | grep -oE '^[0-9]+' | head -1)
    echo "${n:-0}"
}

# SAME METHOD BOTH SIDES. The first version of this counted base with a grep
# for `^def test_` while counting `now` with --collect-only: incomparable the
# moment a file parametrizes, and it invented a +9 on the M8 lock file whose
# arm count never changed. Base is counted by collect-only in a materialised
# base checkout, exactly as `now` is counted in the worktree.
BASE_TREE=/Users/pwilson/src/psh-r5c-2/tmp/w5c2-scratch/base-3a3e0782

base_count() {
    local f="$1" n
    if [ ! -f "$BASE_TREE/$f" ]; then echo 0; return; fi
    n=$(cd "$BASE_TREE" && python -m pytest "$f" --collect-only -q 2>/dev/null \
        | tail -1 | grep -oE '^[0-9]+' | head -1)
    echo "${n:-0}"
}

echo
echo "=== FILES TOUCHED ON THE TEST SIDE (base -> now) ==="
FILES=$(git diff 3a3e0782..HEAD --name-only -- 'tests/*' | sort)
for f in $FILES; do
    now=$(count "$f")
    base=$(base_count "$f")
    printf "  %-58s base=%-4s now=%-4s delta=%+d\n" "$f" "$base" "$now" "$((now - base))"
done
rm -rf tmp/w5c2-basecheck

echo
echo "=== NEW TEST FILES (added this slot) ==="
git diff 3a3e0782..HEAD --name-status -- 'tests/*' | grep '^A' || echo "  (none)"

echo
echo "=== DELETED TEST FILES ==="
git diff 3a3e0782..HEAD --name-status -- 'tests/*' | grep '^D' || echo "  (none)"
