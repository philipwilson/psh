#!/bin/bash
# Slot 5B.1 instrument 10 — THREE-register carry sweep (LEDGER Parts B/C/D)
# plus FLIP-PINS, by scripted grep over the committed registers.
#
# Named rows the brief requires a disposition for:
#   MEDIUM-14, the LOW deferred-import ledgers row, D-3.5-s2, D-4B.4-s3,
#   CR-D1..D6, the locale carries (v0.688 reactive LC_*).
# Plus a term sweep: Protocol / locale / glob / POSIX-class / ratchet.
#
# READ-ONLY: this instrument never writes to the registers.
# Portable: ROOT from $1 (default git toplevel).
set -u
ROOT="${1:-$(git rev-parse --show-toplevel)}"
EV="$ROOT/docs/reviews/evidence/boundary_remediation_2026-07"
LEDGER="$EV/LEDGER.md"
FLIP="$EV/FLIP-PINS.md"

echo "instrument 10 — three-register carry sweep"
echo "ROOT=$ROOT"
echo "HEAD=$(git -C "$ROOT" rev-parse --short HEAD)"
echo "LEDGER md5: $(md5 -q "$LEDGER")"
echo "FLIP-PINS md5: $(md5 -q "$FLIP")"
echo

echo "=== 0. Register structure ==="
grep -n '^## Part' "$LEDGER"
echo

echo "=== 1. NAMED ROWS (each must get a disposition in D2) ==="
for row in "MEDIUM-14" "D-3.5-s2" "D-4B.4-s3" "CR-D1" "CR-D2" "CR-D3" "CR-D4" "CR-D5" "CR-D6"; do
  echo "--- $row"
  grep -n "$row" "$LEDGER" | head -6
  echo
done

echo "=== 2. DEFERRED-IMPORT / cap-table rows ==="
grep -n -i "deferred.import\|FUNC_IMPORT_CAPS\|cap table\|import cap" "$LEDGER" | head -12
echo

echo "=== 3. LOCALE carries (v0.688 reactive LC_* must not change) ==="
grep -n -i "locale" "$LEDGER" | head -20
echo

echo "=== 4. TERM SWEEP over the LEDGER ==="
for term in "Protocol" "protocol" "glob" "POSIX class" "POSIX-class" "ratchet" "collision" "ExpansionContext" "LocaleContext"; do
  n=$(grep -c -- "$term" "$LEDGER")
  echo "  '$term': $n line(s)"
done
echo

echo "=== 5. Protocol/ratchet rows in detail ==="
grep -n -i "protocol\|ratchet" "$LEDGER" | head -25
echo

echo "=== 6. FLIP-PINS — authoritative known-deviation register ==="
echo "(read BEFORE declaring any cell a new divergence)"
grep -n "^#\|^##\|^| " "$FLIP" | head -40
echo

echo "=== 7. FLIP-PINS entries touching this slot's subjects ==="
grep -n -i "locale\|glob\|protocol\|POSIX" "$FLIP" | head -20
echo
echo "instrument 10 done"
