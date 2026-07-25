#!/opt/homebrew/bin/bash
# Gate + disk sampler, so an ENOSPC failure can be CORRELATED with host free
# space rather than inferred. Sampler self-terminates with the gate.
cd /Users/pwilson/src/psh-r1-3 || exit 2
: > tmp/disk-samples.txt
( while :; do
    printf '%s %s\n' "$(date +%H:%M:%S)" \
      "$(df -k /Users/pwilson | tail -1 | awk '{printf "%.1fGi", $4/1048576}')" \
      >> tmp/disk-samples.txt
    sleep 3
  done ) &
SAMPLER=$!
python run_tests.py --parallel > tmp/gate10.txt 2>&1
RC=$?
kill "$SAMPLER" 2>/dev/null; wait "$SAMPLER" 2>/dev/null
echo "GATE EXIT=$RC"
echo "--- disk low-water ---"
sort -k2 -h tmp/disk-samples.txt | head -3
echo "--- samples: $(wc -l < tmp/disk-samples.txt) ---"
