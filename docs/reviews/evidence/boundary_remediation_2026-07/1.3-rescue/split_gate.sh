#!/opt/homebrew/bin/bash
# Split-phase gate with disk sampler (campaign technique for an unstable host):
# phase 1 and phase 2 run SEPARATELY so a transient ENOSPC costs one phase, not
# the whole run. Sampler records free space so any failure can be CORRELATED.
cd /Users/pwilson/src/psh-r1-3 || exit 2
: > tmp/disk-split.txt
( while :; do
    printf '%s %s\n' "$(date +%H:%M:%S)" \
      "$(df -k /Users/pwilson | tail -1 | awk '{printf "%.1f", $4/1048576}')" \
      >> tmp/disk-split.txt
    sleep 3
  done ) &
SAMPLER=$!
trap 'kill "$SAMPLER" 2>/dev/null' EXIT

echo "=== PHASE 1 (parallel, not serial) ==="
python -m pytest tests/ -m "not serial and not benchmark" -n auto -q > tmp/split-phase1.txt 2>&1
P1=$?; tail -2 tmp/split-phase1.txt; echo "phase1 rc=$P1"

echo "=== PHASE 2 (serial) ==="
python -m pytest tests/ -m "serial and not benchmark" -q > tmp/split-phase2.txt 2>&1
P2=$?; tail -2 tmp/split-phase2.txt; echo "phase2 rc=$P2"

kill "$SAMPLER" 2>/dev/null
echo "--- disk low-water during split gate ---"
sort -k2 -g tmp/disk-split.txt | head -2
echo "--- samples: $(wc -l < tmp/disk-split.txt) ---"
echo "COMBINED: phase1=$P1 phase2=$P2"
