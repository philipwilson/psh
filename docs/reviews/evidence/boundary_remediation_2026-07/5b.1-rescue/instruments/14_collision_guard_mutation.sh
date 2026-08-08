#!/bin/bash
# Slot 5B.1 instrument 14 — the collision guard, mutation-proven IN ITS LANDED
# FORM.
#
# Instrument 11 showed the RULE was red on the pre-rename tree (2 offenders).
# That proves the rule, not the shipped file. These arms drive the committed
# guard:
#   G1 re-introduce the collision by reverting the LocaleAccess rename -> bites
#   G2 plant a synthetic Protocol colliding with a concrete class     -> bites
#   G3 plant a synthetic Protocol with a UNIQUE name                  -> green
#      (the control: the guard is not simply failing on any new Protocol)
#   G4 plant a concrete-concrete duplicate                            -> green
#      (the declared scope boundary, exercised rather than asserted)
#
# PROOF SHAPE: mutation-proven, each arm's expectation stated up front.
# PYTHONDONTWRITEBYTECODE=1 per the banked 4B.2 lesson (same-length edits
# defeat mtime+size .pyc invalidation).
set -u
ROOT="${1:-$(git rev-parse --show-toplevel)}"
cd "$ROOT" || exit 2
export PYTHONDONTWRITEBYTECODE=1

GUARD=tests/unit/tooling/test_protocol_name_collision_q5.py
VICTIMS="psh/protocols/__init__.py psh/lexer/expansion_parser.py"
BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/w5b1-mut14.XXXXXX")"

restore() {
  for f in $VICTIMS; do
    b="$BACKUP_DIR/$(echo "$f" | tr / _)"
    [ -f "$b" ] && cp "$b" "$ROOT/$f"
  done
}
trap 'restore' EXIT INT TERM

echo "instrument 14 — collision guard mutation battery"
echo "ROOT=$ROOT"
echo "HEAD=$(git rev-parse HEAD)"
echo
for f in $VICTIMS; do cp "$ROOT/$f" "$BACKUP_DIR/$(echo "$f" | tr / _)"; done

echo "=== CONTROL: unmutated tree GREEN ==="
python3 -m pytest "$GUARD" -q 2>&1 | tail -2
echo

run() {
  arm="$1"; expect="$2"; shift 2
  echo "== arm $arm (expect: $expect)"
  "$@"
  out=$(python3 -m pytest "$GUARD" -q 2>&1)
  echo "$out" | grep -E "^FAILED" | head -2
  echo "$out" | tail -1
  restore
  if echo "$out" | grep -qE "^[0-9]+ passed"; then got=PASSED; else got=FAILED; fi
  echo "   -> arm $arm: $got (expected $expect)"
  [ "$got" != "$expect" ] && echo "   *** MISMATCH ***"
  echo
}

revert_rename() {
  python3 - "$ROOT/psh/protocols/__init__.py" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
s = s.replace("class LocaleAccess(Protocol):", "class LocaleContext(Protocol):", 1)
p.write_text(s)
PY
}

plant_colliding_protocol() {
  # SELF-CAUGHT (second pass): this arm originally planted
  # `class LocaleAccess(Protocol)` here, but expansion_parser.py does not import
  # Protocol — so it went red with NameError, NOT with a collision report. The
  # arm's declared expectation (FAILED) was met for entirely the wrong reason,
  # which is exactly the mirror trap. It now plants a CONCRETE class colliding
  # with the psh.protocols Protocol of that name: no import needed, nothing
  # rebound, and the collision is the ONLY thing that can fail.
  cat >> "$ROOT/psh/lexer/expansion_parser.py" <<'PY'


class LocaleAccess:  # pragma: no cover
    """5B.1 probe: concrete class colliding with psh.protocols#LocaleAccess."""
PY
}

# NOTE (self-caught, first attempt): both CONTROL arms originally appended to
# psh/lexer/expansion_parser.py and went red for reasons that had nothing to do
# with the guard — G3 used `Protocol`, which that module does not import
# (NameError), and G4's second `class ExpansionParser` SHADOWED the live one
# (TypeError at its call site). A mutation that fails for the wrong reason
# proves nothing. Both now append to psh/protocols/__init__.py, where Protocol
# IS imported and where adding a class shadows nothing.

plant_unique_protocol() {
  cat >> "$ROOT/psh/protocols/__init__.py" <<'PY'


@runtime_checkable
class W5b1UniquelyNamedProbe(Protocol):  # pragma: no cover
    """5B.1 control: a Protocol whose name collides with nothing."""
PY
}

plant_concrete_duplicate() {
  # Duplicates psh/lexer/expansion_parser.py#ExpansionParser by NAME, in a
  # different module, so nothing is rebound at runtime. Concrete-concrete =
  # deliberately outside the guard's scope.
  cat >> "$ROOT/psh/protocols/__init__.py" <<'PY'


class ExpansionParser:  # pragma: no cover
    """5B.1 control: concrete-concrete duplicate, OUTSIDE the guard's scope."""
PY
}

run G1 FAILED revert_rename
run G2 FAILED plant_colliding_protocol
run G3 PASSED plant_unique_protocol
run G4 PASSED plant_concrete_duplicate

echo "=== POST-STATE ==="
for f in $VICTIMS; do
  b="$BACKUP_DIR/$(echo "$f" | tr / _)"
  if cmp -s "$b" "$ROOT/$f"; then echo "  RESTORED-IDENTICAL  $f"
  else echo "  *** RESTORE FAILED  $f ***"; fi
done
echo
echo "final control:"
python3 -m pytest "$GUARD" -q 2>&1 | tail -2
echo
echo "instrument 14 done"
