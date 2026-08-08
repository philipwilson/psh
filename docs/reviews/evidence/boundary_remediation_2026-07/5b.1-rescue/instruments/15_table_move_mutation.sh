#!/bin/bash
# Slot 5B.1 instrument 15 — the table-move pins, mutation-proven.
#
# Arms (each must fail for its OWN named reason):
#   T1 restore the deferred cross-layer import in locale_service -> ownership
#      guard bites (and the layering cap bites, since actual would exceed 3)
#   T2 bury the table import inside a function body               -> the
#      "no deferred import" cell bites specifically
#   T3 mutate ONE range in the moved table                        -> the
#      byte-identity pin bites
#   T4 give the leaf module an import                             -> the
#      true-leaf cell bites
#   T5 CONTROL: a comment-only edit to the leaf module            -> green
#      (proves the cells are not failing on any edit whatsoever)
#
# PYTHONDONTWRITEBYTECODE=1 per the banked 4B.2 lesson.
set -u
ROOT="${1:-$(git rev-parse --show-toplevel)}"
cd "$ROOT" || exit 2
export PYTHONDONTWRITEBYTECODE=1

PINS="tests/unit/tooling/test_posix_class_table_ownership.py"
CAPS="tests/unit/tooling/test_import_layering.py"
VICTIMS="psh/core/locale_service.py psh/utils/posix_classes.py"
BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/w5b1-mut15.XXXXXX")"

restore() {
  for f in $VICTIMS; do
    b="$BACKUP_DIR/$(echo "$f" | tr / _)"
    [ -f "$b" ] && cp "$b" "$ROOT/$f"
  done
}
trap 'restore' EXIT INT TERM

echo "instrument 15 — table-move mutation battery"
echo "ROOT=$ROOT"
echo "HEAD=$(git rev-parse HEAD)"
echo
for f in $VICTIMS; do cp "$ROOT/$f" "$BACKUP_DIR/$(echo "$f" | tr / _)"; done

echo "=== CONTROL: unmutated tree GREEN ==="
python3 -m pytest "$PINS" "$CAPS" -q 2>&1 | tail -2
echo

run() {
  arm="$1"; expect="$2"; py="$3"
  echo "== arm $arm (expect: $expect)"
  python3 - "$ROOT" <<PY
import sys, pathlib
root = pathlib.Path(sys.argv[1])
ls = root / "psh/core/locale_service.py"
pc = root / "psh/utils/posix_classes.py"
$py
PY
  out=$(python3 -m pytest "$PINS" "$CAPS" -q 2>&1)
  echo "$out" | grep -E "^FAILED" | head -3
  echo "$out" | tail -1
  restore
  if echo "$out" | grep -qE "^[0-9]+ passed"; then got=PASSED; else got=FAILED; fi
  echo "   -> arm $arm: $got (expected $expect)"
  [ "$got" != "$expect" ] && echo "   *** MISMATCH ***"
  echo
}

# T1: put the cross-layer deferred import back exactly as it was
run T1 FAILED 's = ls.read_text()
s = s.replace("        return POSIX_CLASSES.get(name)",
              "        from ..expansion.glob import _POSIX_CLASSES\n        return _POSIX_CLASSES.get(name)", 1)
ls.write_text(s)'

# T2: keep the new module but defer its import into the function body
run T2 FAILED 's = ls.read_text()
s = s.replace("from ..utils.posix_classes import POSIX_CLASSES\n", "", 1)
s = s.replace("        return POSIX_CLASSES.get(name)",
              "        from ..utils.posix_classes import POSIX_CLASSES\n        return POSIX_CLASSES.get(name)", 1)
s = s.replace("        body = POSIX_CLASSES.get(name)",
              "        from ..utils.posix_classes import POSIX_CLASSES\n        body = POSIX_CLASSES.get(name)", 1)
ls.write_text(s)'

# T3: silently change one range in the moved table
run T3 FAILED 's = pc.read_text()
s = s.replace("\x27digit\x27: \x270-9\x27,", "\x27digit\x27: \x270-8\x27,", 1)
pc.write_text(s)'

# T4: give the leaf module a dependency
run T4 FAILED 's = pc.read_text()
s = s.replace("#: POSIX character classes", "import re  # probe\n\n#: POSIX character classes", 1)
pc.write_text(s)'

# T5: CONTROL — comment-only edit, nothing should fail
run T5 PASSED 's = pc.read_text()
pc.write_text(s + "\n# 5B.1 probe: comment-only edit (control arm)\n")'

echo "=== POST-STATE ==="
for f in $VICTIMS; do
  b="$BACKUP_DIR/$(echo "$f" | tr / _)"
  if cmp -s "$b" "$ROOT/$f"; then echo "  RESTORED-IDENTICAL  $f"
  else echo "  *** RESTORE FAILED  $f ***"; fi
done
echo
echo "final control:"
python3 -m pytest "$PINS" "$CAPS" -q 2>&1 | tail -2
echo
echo "instrument 15 done"
