#!/bin/bash
# Slot 5B.1 instrument 13 — POST-EXTENSION mutation battery (the flagship pin).
#
# Companion to instrument 04, which measured the PRE-extension state
# (arm A blind, arm B bites, arm C blind). Same offender, same three files,
# after the scope extension: ALL THREE must now BITE.
#
# Plus the drift arms the brief requires of the enumeration self-check:
#   D1 plant a FAKE entry in CREATED_MODULES        -> self-check bites
#   D2 remove a REAL entry from CREATED_MODULES     -> self-check bites
#   D3 undispositioned post-endpoint module         -> coverage bites
#   D4 class-ATTRIBUTE offender in a scanned module -> detector bites
#
# PROOF SHAPE: mutation-proven, each class failing for its OWN reason (the
# failing test NAME is captured per arm, not just "something went red").
#
# Portable: ROOT from $1 (default git toplevel). Restores from mktemp backups
# under an EXIT trap; never consults git to revert.
set -u
ROOT="${1:-$(git rev-parse --show-toplevel)}"
cd "$ROOT" || exit 2

# BANKED 4B.2 LESSON (2): mutation-lock drivers MUST disable bytecode caching.
# Learned the hard way in this very instrument: arm D3 replaces "8af29e6d" with
# "75ab5625" — the SAME BYTE LENGTH — so the mutated and restored files have
# identical size, and Python's mtime+size .pyc invalidation reused STALE
# bytecode for the post-restore control run, reporting a red final control on a
# byte-identical-to-original tree. Without this the transcript lies.
export PYTHONDONTWRITEBYTECODE=1

RATCHET=tests/unit/tooling/test_shell_consumer_ratchet_q1.py
VICTIMS="psh/scripting/analysis_session.py psh/parser/session.py psh/expansion/procsub_render.py $RATCHET"
BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/w5b1-mut13.XXXXXX")"

restore() {
  for f in $VICTIMS; do
    b="$BACKUP_DIR/$(echo "$f" | tr / _)"
    [ -f "$b" ] && cp "$b" "$ROOT/$f"
  done
}
trap 'restore' EXIT INT TERM

echo "instrument 13 — post-extension mutation battery"
echo "ROOT=$ROOT"
echo "HEAD=$(git rev-parse HEAD)"
echo

echo "=== PRE-STATE: production victims must be clean ==="
git status --porcelain -- psh/scripting/analysis_session.py psh/parser/session.py psh/expansion/procsub_render.py
echo "(empty above = clean; the ratchet file is expected MODIFIED — this slot's work)"
for f in $VICTIMS; do
  cp "$ROOT/$f" "$BACKUP_DIR/$(echo "$f" | tr / _)"
done
echo

echo "=== CONTROL: unmutated tree must be GREEN ==="
python3 -m pytest "$RATCHET" -q 2>&1 | tail -2
echo

OFFENDER='
def w5b1_synthetic_offender(shell: "Shell") -> None:  # pragma: no cover
    """5B.1 probe: full-Shell param, must trip the extended ratchet."""
'

ATTR_OFFENDER='
class W5b1SyntheticHolder:  # pragma: no cover
    """5B.1 probe: full-Shell held as a FIELD (the A2b shape)."""
    shell: "Shell"
'

run_arm() {
  arm="$1"; file="$2"; payload="$3"; expect="$4"
  echo "== arm $arm: $file (expect: $expect)"
  printf '%s\n' "$payload" >> "$ROOT/$file"
  out=$(python3 -m pytest "$RATCHET" -q 2>&1)
  echo "$out" | grep -E "^(FAILED|ERROR)" | head -3
  echo "$out" | tail -1
  cp "$BACKUP_DIR/$(echo "$file" | tr / _)" "$ROOT/$file"
  if echo "$out" | grep -qE "^[0-9]+ passed"; then got=PASSED; else got=FAILED; fi
  echo "   -> arm $arm: $got (expected $expect)"
  [ "$got" != "$expect" ] && echo "   *** MISMATCH ***"
  echo
}

echo "=== PARAMETER-SHAPE OFFENDER: all three must now BITE ==="
run_arm A psh/scripting/analysis_session.py "$OFFENDER" FAILED
run_arm B psh/parser/session.py             "$OFFENDER" FAILED
run_arm C psh/expansion/procsub_render.py   "$OFFENDER" FAILED

echo "=== D4: CLASS-ATTRIBUTE offender (the A2b shape) must BITE ==="
run_arm D4 psh/parser/session.py "$ATTR_OFFENDER" FAILED

echo "=== ENUMERATION / COVERAGE DRIFT ARMS (edit the ratchet's own lists) ==="

drift_arm() {
  name="$1"; py="$2"; expect="$3"
  echo "== arm $name (expect: $expect)"
  python3 - "$ROOT/$RATCHET" <<PY
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
$py
p.write_text(s)
PY
  out=$(python3 -m pytest "$RATCHET" -q 2>&1)
  echo "$out" | grep -E "^FAILED" | head -3
  echo "$out" | tail -1
  cp "$BACKUP_DIR/$(echo "$RATCHET" | tr / _)" "$ROOT/$RATCHET"
  if echo "$out" | grep -qE "^[0-9]+ passed"; then got=PASSED; else got=FAILED; fi
  echo "   -> arm $name: $got (expected $expect)"
  [ "$got" != "$expect" ] && echo "   *** MISMATCH ***"
  echo
}

# D1: plant a FAKE entry in CREATED_MODULES
drift_arm D1 's = s.replace(
    "    \"psh/invocation.py\",",
    "    \"psh/invocation.py\",\n    \"psh/NOT_A_REAL_MODULE.py\",", 1)' FAILED

# D2: remove a REAL entry from CREATED_MODULES
drift_arm D2 's = s.replace("    \"psh/invocation.py\",\n", "", 1)' FAILED

# D3: the COVERAGE assertion, MECHANISM-ISOLATED.
#
# First attempt moved SCOPE_ENDPOINT alone and went red on
# test_created_modules_match_enumeration — i.e. it proved the ENUMERATION check
# bites, NOT the coverage check. A cell consistent with two mechanisms is
# evidence for neither (4B.3 rule 6). This version rolls the endpoint back to
# 75ab5625 AND rolls CREATED_MODULES back to that range's 16-module set, so the
# enumeration check stays GREEN and the only thing that can fail is coverage —
# which must then report exactly the three modules born in the gap.
drift_arm D3 's = s.replace("SCOPE_ENDPOINT = \"8af29e6d\"",
                            "SCOPE_ENDPOINT = \"75ab5625\"", 1)
for _m in ("    \"psh/expansion/procsub_render.py\",\n",
           "    \"psh/protocols/__init__.py\",\n",
           "    \"psh/scripting/analysis_session.py\",\n"):
    s = s.replace(_m, "", 1)' FAILED

echo "=== POST-STATE: byte-identity after restore ==="
for f in $VICTIMS; do
  b="$BACKUP_DIR/$(echo "$f" | tr / _)"
  if cmp -s "$b" "$ROOT/$f"; then echo "  RESTORED-IDENTICAL  $f"
  else echo "  *** RESTORE FAILED  $f ***"; fi
done
echo
echo "final control (must be green again):"
python3 -m pytest "$RATCHET" -q 2>&1 | tail -2
echo
echo "instrument 13 done"
