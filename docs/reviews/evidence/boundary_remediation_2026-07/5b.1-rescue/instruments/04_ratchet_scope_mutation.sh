#!/bin/bash
# Slot 5B.1 instrument 04 — arm-A/arm-B replay of the q5 ratchet blind spot.
#
# COPIED FROM the committed READ-ONLY instrument
#   docs/reviews/evidence/boundary_remediation_2026-07/checkpoint-r/
#   instruments/q5/09_ratchet_scope_mutation.sh
# with these recorded edits (the original is never modified):
#   (1) PATH EDIT (the sanctioned single edit): the original hardcodes
#       WT=/private/tmp/.../ckr/q5/wt. Replaced with ROOT=$1 (default git
#       toplevel) — CR-D5 instrument portability.
#   (2) SAFETY EDIT: the original reverts with `git checkout -- <file>`.
#       `git checkout` over a worktree is banned by the 3.x rules; this copy
#       snapshots each victim file to a mktemp backup and restores from the
#       BACKUP in an EXIT trap, so an interrupted run still restores and no
#       git state is consulted.
#   (3) VERIFICATION EDIT: asserts the pre-state is clean for the victim
#       files and re-verifies byte-identity after restore (cmp), so a failed
#       restore is LOUD rather than silent.
#   (4) ARM-C ADDED: same offender in psh/expansion/procsub_render.py (the
#       other unscanned module) — the blind spot is not analysis_session's
#       alone; a one-module probe would leave that face silent.
#
# PROOF SHAPE: mutation-proven. Arm A/C must PASS (blind spot live at this
# tip); arm B must FAIL (scanned module bites). If arm B does not fail, the
# instrument proves nothing and says so.
set -u
ROOT="${1:-$(git rev-parse --show-toplevel)}"
cd "$ROOT" || exit 2

VICTIMS="psh/scripting/analysis_session.py psh/parser/session.py psh/expansion/procsub_render.py"
BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/w5b1-mut.XXXXXX")"

restore() {
  for f in $VICTIMS; do
    b="$BACKUP_DIR/$(echo "$f" | tr / _)"
    [ -f "$b" ] && cp "$b" "$ROOT/$f"
  done
}
trap 'restore' EXIT INT TERM

echo "instrument 04 — ratchet scope mutation (arm A / B / C)"
echo "ROOT=$ROOT"
echo "HEAD=$(git rev-parse HEAD)"
echo "backup dir=$BACKUP_DIR"
echo

echo "=== PRE-STATE: victim files must be clean before mutating ==="
git status --porcelain -- $VICTIMS
if [ -n "$(git status --porcelain -- $VICTIMS)" ]; then
  echo "ABORT: victim file(s) already modified — refusing to mutate."
  exit 3
fi
echo "(empty above = clean)"
for f in $VICTIMS; do
  cp "$ROOT/$f" "$BACKUP_DIR/$(echo "$f" | tr / _)"
done
echo

OFFENDER='
def w5b1_synthetic_offender(shell: "Shell") -> None:  # pragma: no cover
    """5B.1 probe: full-Shell param, must trip the ratchet IF scanned."""
'

run_arm() {
  arm="$1"; file="$2"; expect="$3"
  echo "== arm $arm: offender in $file (expect: $expect)"
  printf '%s\n' "$OFFENDER" >> "$ROOT/$file"
  out=$(python3 -m pytest tests/unit/tooling/test_shell_consumer_ratchet_q1.py -q 2>&1)
  echo "$out" | tail -4
  # restore this one file immediately from its backup
  cp "$BACKUP_DIR/$(echo "$file" | tr / _)" "$ROOT/$file"
  if echo "$out" | grep -q "^[0-9]* passed"; then
    got=PASSED
  else
    got=FAILED
  fi
  echo "   -> arm $arm result: $got   (expected: $expect)"
  if [ "$got" != "$expect" ]; then
    echo "   *** MISMATCH — instrument's premise not reproduced ***"
  fi
  echo
}

run_arm A psh/scripting/analysis_session.py PASSED
run_arm B psh/parser/session.py FAILED
run_arm C psh/expansion/procsub_render.py PASSED

echo "=== POST-STATE: byte-identity after restore ==="
for f in $VICTIMS; do
  b="$BACKUP_DIR/$(echo "$f" | tr / _)"
  if cmp -s "$b" "$ROOT/$f"; then
    echo "  RESTORED-IDENTICAL  $f"
  else
    echo "  *** RESTORE FAILED  $f ***"
  fi
done
echo
echo "git status for victims (must be empty):"
git status --porcelain -- $VICTIMS
echo "(empty above = clean)"
echo
echo "instrument 04 done"
