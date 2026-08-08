#!/bin/bash
# Slot 5B.1 instrument 18 — instrument manifest + discharge audit.
#
# SELF-EXCLUDING: this script and its own transcript are omitted from the
# manifest it generates (a manifest that lists itself changes its own hash).
# COMMAND-GENERATED: every hash and count below is produced by this run, not
# transcribed by hand (4B.2 lesson 5 — and the receiver recomputes).
set -u
ROOT="${1:-$(git rev-parse --show-toplevel)}"
cd "$ROOT" || exit 2

SELF="18_manifest_and_discharge"

echo "instrument 18 — manifest + discharge audit"
echo "ROOT=$ROOT"
echo "HEAD=$(git rev-parse HEAD)"
echo "HEAD-short=$(git rev-parse --short HEAD)"
echo "generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

echo "=== INSTRUMENT MANIFEST (self-excluding, md5 per file) ==="
printf '%-46s %-34s %s\n' "INSTRUMENT" "MD5" "TRANSCRIPT MD5"
n=0
for f in tmp/w5b1-instruments/*; do
  b=$(basename "$f")
  case "$b" in *"$SELF"*) continue;; esac
  stem="${b%.*}"
  t="tmp/w5b1-transcripts/${stem}.out"
  if [ -f "$t" ]; then tm=$(md5 -q "$t"); else tm="(none)"; fi
  printf '%-46s %-34s %s\n' "$b" "$(md5 -q "$f")" "$tm"
  n=$((n+1))
done
echo "instrument count (excluding self): $n"
echo

echo "=== EXTRA TRANSCRIPTS (post-state re-runs, no 1:1 instrument stem) ==="
for t in tmp/w5b1-transcripts/*; do
  b=$(basename "$t"); stem="${b%.out}"
  case "$b" in *"$SELF"*) continue;; esac
  if [ ! -f "tmp/w5b1-instruments/${stem}.py" ] && \
     [ ! -f "tmp/w5b1-instruments/${stem}.sh" ]; then
    printf '  %-52s %s\n' "$b" "$(md5 -q "$t")"
  fi
done
echo

echo "=== COMMITS (this slot) ==="
git log --oneline 8af29e6d..HEAD
echo
echo "commit count: $(git rev-list --count 8af29e6d..HEAD)"
echo

echo "=== FILES CHANGED vs base, by commit (boundary check) ==="
git diff --stat 8af29e6d..HEAD
echo

echo "=== NEVER-TOUCH VERIFICATION (must all be UNCHANGED) ==="
for f in psh/version.py CHANGELOG.md README.md ARCHITECTURE.md \
         docs/reviews/README.md \
         docs/reviews/evidence/boundary_remediation_2026-07/FLIP-PINS.md \
         docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md; do
  if git diff --quiet 8af29e6d..HEAD -- "$f" 2>/dev/null; then
    echo "  UNCHANGED  $f"
  else
    echo "  *** MODIFIED (VIOLATION) *** $f"
  fi
done
echo

echo "=== DISCHARGE AUDIT — every claim row, anchored ==="
echo "(claim | instrument anchor | proof shape)"
cat <<'ROWS'
  ratchet scope 16->19 modules          | 02 + test_created_modules_match_enumeration | re-derived by git
  coverage assertion (post-endpoint)    | 13 arm D3 + 4 pure-fn self-tests            | mutation-proven
  detector: class-attribute shape       | 09 part 2 + 13 arm D4 + 3 detector cells    | mutation-proven
  detector: ShellState NOT counted      | 12 (six-shape control) + detector cell      | characterization
  ALLOWLIST x3 (analysis_session)       | 06 (per-param use classification)           | characterization
  arm-A offender now BITES              | 13 arms A/B/C (vs 04 pre-extension)         | mutation-proven
  enumeration drift both directions     | 13 arms D1/D2                               | mutation-proven
  collision: protocol side renamed      | 07 (per-definition import resolution)       | census
  collision recurrence guard            | 11 (red-on-base) + 14 arms G1-G4            | mutation-proven
  table moved to utils leaf             | 08 + test_posix_class_table_ownership        | measured
  table content byte-identical          | 15 arm T3 + independent transcription pin   | mutation-proven
  private import GONE                   | 15 arms T1/T2                               | mutation-proven
  cap 5->3 (genuine -2)                 | 08 POST (guard's own analyzer)              | measured
  dead store removed                    | 16 arms S1/S2                               | mutation-proven
  +22 test delta accounted              | 17 (git-show AST vs gate manifests)         | two-source re-derivation
  gate green                            | tmp/gate-1.txt                              | measured
  compare-bash +0                       | tmp/compare-bash-1.txt                      | measured
ROWS
echo
echo "=== GATE / COMPARE-BASH EVIDENCE (hashes of the run logs) ==="
for f in tmp/gate-1.txt tmp/compare-bash-1.txt; do
  [ -f "$f" ] && printf '  %-28s %s\n' "$f" "$(md5 -q "$f")"
done
echo
echo "=== LEDGER ==="
printf '  %-28s %s\n' "tmp/w5b1-ledger.md" "$(md5 -q tmp/w5b1-ledger.md)"
echo
echo "instrument 18 done"
