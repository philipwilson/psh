#!/bin/sh
# Slot 1.4: catch the runaway writer on THIS macOS host during a parallel gate.
#
# The integrator's fact: this host has shown the nightly's exact signature for
# weeks under `run_tests.py --parallel` — free space collapsing to ~0 in minutes
# then fully recovering with nothing findable afterwards. That is what an
# unlinked capture file being filled looks like, which is precisely what I
# caught on the Linux runner (a `yes` holding an unlinked .oracle-stdout).
#
# `lsof +L1` lists files whose link count is 0 — i.e. already unlinked but still
# held open. That is the only way to see this file at all.
#
# Usage: host-disk-watch.sh [trip_kb]   (default: trip below 20 GiB free)
TRIP=${1:-20971520}
LOG=tmp/host-disk-watch.log
: > "$LOG"
trips=0
while [ "$trips" -lt 4 ]; do
    avail=$(df -k /var/folders | tail -1 | awk '{print $4}')
    printf '%s avail_kb=%s\n' "$(date +%T)" "$avail" >> "$LOG"
    if [ "${avail:-0}" -lt "$TRIP" ]; then
        trips=$((trips + 1))
        {
            echo "=== TRIP $trips at $(date +%T): avail_kb=$avail ==="
            echo "--- unlinked files still held open, largest first ---"
            lsof -nP +L1 2>/dev/null \
                | awk 'NR==1 || $8 ~ /^[0-9]+$/' \
                | sort -k8 -rn | head -15
            echo "--- largest open regular files (any link count) ---"
            lsof -nP 2>/dev/null | awk '$5=="REG" && $7+0 > 209715200' \
                | sort -k7 -rn | head -10
            echo "=== end TRIP $trips ==="
        } >> "$LOG" 2>&1
    fi
    sleep 2
done
echo "watcher done ($trips trips)" >> "$LOG"
