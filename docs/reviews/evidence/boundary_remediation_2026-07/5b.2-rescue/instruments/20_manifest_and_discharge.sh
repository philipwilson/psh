#!/bin/sh
# Instrument 20 (slot 5B.2) — instrument manifest + discharge audit.
# Self-excluding and command-generated (never hand-tallied).
ROOT="$1"
cd "$ROOT" || exit 1
SELF="20_manifest_and_discharge.sh"
echo "ROOT=$ROOT"
echo "HEAD=$(git rev-parse --short HEAD)"
echo
echo "=== INSTRUMENT MANIFEST (self-excluding) ==="
n=0
for f in tmp/w5b2-instruments/*; do
  b=$(basename "$f")
  [ "$b" = "$SELF" ] && continue
  n=$((n+1))
  t="tmp/w5b2-transcripts/$(echo "$b" | sed 's/\.[a-z]*$//').out"
  if [ -f "$t" ]; then
    printf "  %-42s %s   transcript %s\n" "$b" "$(md5 -q "$f")" "$(md5 -q "$t")"
  else
    printf "  %-42s %s   (no transcript)\n" "$b" "$(md5 -q "$f")"
  fi
done
echo "  instruments (excluding self): $n"
echo
echo "=== TRANSCRIPTS ==="
ls -1 tmp/w5b2-transcripts/ | sed 's/^/  /'
echo
echo "=== COMMITS (1c70dfbf..HEAD) ==="
git log --oneline 1c70dfbf..HEAD | sed 's/^/  /'
echo "  count: $(git rev-list --count 1c70dfbf..HEAD)"
echo
echo "=== GATE LEGS ==="
printf "  gate-1.txt        %s\n" "$(md5 -q tmp/gate-1.txt)"
printf "  compare-bash-1.txt %s\n" "$(md5 -q tmp/compare-bash-1.txt)"
grep -E "Combined across" tmp/gate-1.txt | sed 's/^/  /'
tail -1 tmp/compare-bash-1.txt | sed 's/^/  compare-bash: /'
