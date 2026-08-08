#!/bin/bash
# Slot 5B.1 instrument 02 — re-derive the ratchet scan-scope gap by git.
#
# The ratchet's CREATED_MODULES is pinned to v0.724.0..75ab5625. This
# instrument re-derives that set AND enumerates every psh/ module created
# since 75ab5625, split by the two gap ranges the brief names, then
# reconciles against the hardcoded list.
#
# Portable: takes ROOT as $1 (default: git toplevel of cwd). No hardcoded
# worktree paths (CR-D5).
set -u
ROOT="${1:-$(git rev-parse --show-toplevel)}"
cd "$ROOT" || exit 2

echo "instrument 02 — ratchet gap enumeration"
echo "ROOT=$ROOT"
echo "HEAD=$(git rev-parse HEAD)"
echo "HEAD-short=$(git rev-parse --short HEAD)"
echo "git version: $(git --version)"
echo

echo "=== A. The SCANNED range (what the ratchet pins today) ==="
echo "--- git log --diff-filter=A --name-only v0.724.0..75ab5625 -- psh/"
git log --diff-filter=A --pretty=format: --name-only v0.724.0..75ab5625 -- psh/ \
  | grep '\.py$' | sort -u > /dev/stdout
echo

echo "=== B. GAP RANGE 1: 75ab5625..0215279c (v0.746 -> v0.750) ==="
git log --diff-filter=A --pretty=format: --name-only 75ab5625..0215279c -- psh/ \
  | grep '\.py$' | sort -u
echo

echo "=== C. GAP RANGE 2: 0215279c..8af29e6d (remediation range, to tip) ==="
git log --diff-filter=A --pretty=format: --name-only 0215279c..HEAD -- psh/ \
  | grep '\.py$' | sort -u
echo

echo "=== D. CONTINUOUS range v0.724.0..HEAD (the single-range option) ==="
git log --diff-filter=A --pretty=format: --name-only v0.724.0..HEAD -- psh/ \
  | grep '\.py$' | sort -u
echo

echo "=== E. SANITY: do all enumerated files still EXIST at tip? ==="
echo "(a file created-then-deleted inside the range appears in --diff-filter=A"
echo " but must not be added to a scan list that asserts existence)"
git log --diff-filter=A --pretty=format: --name-only v0.724.0..HEAD -- psh/ \
  | grep '\.py$' | sort -u | while read -r f; do
    if [ -f "$ROOT/$f" ]; then
      echo "  EXISTS   $f"
    else
      echo "  MISSING  $f   <<< created-then-deleted/renamed in range"
    fi
  done
echo

echo "=== F. RECONCILE against the hardcoded CREATED_MODULES ==="
python3 - "$ROOT" <<'PY'
import subprocess, sys, pathlib
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "ratchet", root / "tests/unit/tooling/test_shell_consumer_ratchet_q1.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def enum(rng):
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--pretty=format:", "--name-only",
         rng, "--", "psh/"], cwd=root, capture_output=True, text=True)
    return {l.strip() for l in out.stdout.splitlines()
            if l.strip().endswith(".py")}

scanned = enum("v0.724.0..75ab5625")
gap1 = enum("75ab5625..0215279c")
gap2 = enum("0215279c..HEAD")
cont = enum("v0.724.0..HEAD")

hardcoded = set(mod.CREATED_MODULES)
print(f"hardcoded CREATED_MODULES: {len(hardcoded)}")
print(f"git v0.724.0..75ab5625  : {len(scanned)}")
print(f"  identical? {hardcoded == scanned}")
print(f"  only in git : {sorted(scanned - hardcoded)}")
print(f"  only in list: {sorted(hardcoded - scanned)}")
print()
print(f"GAP1 75ab5625..0215279c : {len(gap1)}  {sorted(gap1)}")
print(f"GAP2 0215279c..HEAD     : {len(gap2)}  {sorted(gap2)}")
print(f"UNION of gaps           : {len(gap1|gap2)}  {sorted(gap1|gap2)}")
print()
print(f"CONTINUOUS v0.724.0..HEAD: {len(cont)}")
print(f"  equals scanned|gap1|gap2 ? {cont == (scanned|gap1|gap2)}")
print(f"  difference: {sorted(cont ^ (scanned|gap1|gap2))}")
print()
print("TOUCHED_PREEXISTING (unchanged by any range):")
for m in mod.TOUCHED_PREEXISTING:
    print(f"  {m}  exists={ (root/m).exists() }")
PY
echo
echo "instrument 02 done"
