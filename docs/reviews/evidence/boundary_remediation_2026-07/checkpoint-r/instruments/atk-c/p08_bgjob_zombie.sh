#!/bin/bash
# atk-c p08: Gap 8 — q4-F4 bg-job zombie divergence.
# Part 1: register sweep — is the divergence recorded ANYWHERE?
#   (FLIP-PINS.md, LEDGER.md, nightly-status.md, checkpoint-r brief)
# Part 2: one fresh DIVERGENCE-axis cell at ae871a16 vs bash 5.2.26:
#   finished bg job's process state past a later command boundary.
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-c/wt
EV=/Users/pwilson/src/psh/docs/reviews/evidence/boundary_remediation_2026-07
BRIEF=/Users/pwilson/src/psh/tmp/remediation-ledgers/briefs/checkpoint-r.md
BASH=/opt/homebrew/bin/bash
cd "$WT" || exit 1
export PYTHONPATH="$WT"

echo "== PART 1: register sweep (fixed strings, case-insensitive) =="
for f in "$EV/FLIP-PINS.md" "$EV/LEDGER.md" "$EV/nightly-status.md" "$BRIEF"; do
  echo "-- $f --"
  for term in zombie defunct reap "background job" waitpid WNOHANG; do
    c=$(grep -icF -- "$term" "$f")
    echo "   '$term': $c"
    if [ "$c" != "0" ]; then grep -inF -- "$term" "$f" | head -4; fi
  done
done

echo
echo "== PART 2: fresh divergence cell (psh @ae871a16 vs bash 5.2.26) =="
cat > /tmp_probe_cell.sh 2>/dev/null || true
PROBE='sleep 0.2 &
sleep 0.9
:
ps -ax -o pid=,ppid=,stat=,comm= | awk -v p=$$ '"'"'$2==p {print}'"'"''
printf '%s\n' "$PROBE" > "$WT/atk_c_zombie_probe.sh"
echo "-- psh --"
python3 -m psh "$WT/atk_c_zombie_probe.sh"
echo "-- bash --"
"$BASH" "$WT/atk_c_zombie_probe.sh"
rm -f "$WT/atk_c_zombie_probe.sh"
echo "(rows above are children of each shell at t=1.1s, past the ':' boundary; a 'Z' stat row = unreaped zombie)"
