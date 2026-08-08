#!/bin/bash
# Slot 5B.1 instrument 16 — the A4b dead-store pin, mutation-proven.
#
#   S1 reintroduce `self.shell = shell` -> the pin bites (named test)
#   S2 CONTROL: add an unrelated field   -> stays green (the pin is specific
#      to the shell field, not to any new attribute)
#
# PYTHONDONTWRITEBYTECODE=1 per the banked 4B.2 lesson.
set -u
ROOT="${1:-$(git rev-parse --show-toplevel)}"
cd "$ROOT" || exit 2
export PYTHONDONTWRITEBYTECODE=1

SUITE=tests/unit/scripting/test_analysis_session.py
VICTIM=psh/scripting/analysis_session.py
BACKUP="$(mktemp -d "${TMPDIR:-/tmp}/w5b1-mut16.XXXXXX")/victim.py"
cp "$ROOT/$VICTIM" "$BACKUP"
trap 'cp "$BACKUP" "$ROOT/$VICTIM"' EXIT INT TERM

echo "instrument 16 — dead-store pin mutation"
echo "ROOT=$ROOT"
echo "HEAD=$(git rev-parse HEAD)"
echo
echo "=== CONTROL: unmutated tree GREEN ==="
python3 -m pytest "$SUITE" -q 2>&1 | tail -2
echo

run() {
  arm="$1"; expect="$2"; field="$3"
  echo "== arm $arm (expect: $expect) — reintroducing \`self.$field = shell\`"
  python3 - "$ROOT/$VICTIM" "$field" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); field = sys.argv[2]
s = p.read_text()
anchor = "    def __init__(self, shell: 'Shell') -> None:\n"
assert anchor in s, "anchor not found"
s = s.replace(anchor, anchor + f"        self.{field} = shell\n", 1)
p.write_text(s)
PY
  out=$(python3 -m pytest "$SUITE" -q 2>&1)
  echo "$out" | grep -E "^FAILED" | head -2
  echo "$out" | tail -1
  cp "$BACKUP" "$ROOT/$VICTIM"
  if echo "$out" | grep -qE "^[0-9]+ passed"; then got=PASSED; else got=FAILED; fi
  echo "   -> arm $arm: $got (expected $expect)"
  [ "$got" != "$expect" ] && echo "   *** MISMATCH ***"
  echo
}

run S1 FAILED shell
run S2 PASSED some_unrelated_field

echo "=== POST-STATE ==="
if cmp -s "$BACKUP" "$ROOT/$VICTIM"; then echo "  RESTORED-IDENTICAL  $VICTIM"
else echo "  *** RESTORE FAILED ***"; fi
echo
echo "final control:"
python3 -m pytest "$SUITE" -q 2>&1 | tail -2
echo
echo "instrument 16 done"
