"""Census re-derivation using the RATCHETS' OWN detectors (not dev grep shape).

Run from the worktree root. Prints, for the expansion/arith path:
  (1) every Q2 VT-candidate signature, with its LINE, and its classification;
  (2) every 2.3-ratchet broad handler in psh/expansion + psh/executor;
  (3) the live/stale reconciliation for the two executor arithmetic entries.
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "unit" / "tooling"))

import importlib.util


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


q2 = _load("q2", "tests/unit/tooling/test_broad_valueerror_catch_q2.py")
r23 = _load("r23", "tests/unit/tooling/test_subscript_no_broad_except.py")

print("=== ROOT:", ROOT)
print("=== q2.ROOT:", q2.ROOT, " r23.ROOT:", r23.ROOT)

# --- (1) Q2 candidates WITH line numbers (the detector is line-independent;
#         re-walk to attach lines so the census can point at source).
def q2_candidates_with_lines(src, rel):
    out = []
    for n in ast.walk(ast.parse(src)):
        if not isinstance(n, ast.Try):
            continue
        calls = sorted({q2._call_name(c) for st in n.body
                        for c in ast.walk(st) if isinstance(c, ast.Call)})
        broad = len(n.body) > 1 or len(calls) >= 5
        for h in n.handlers:
            if not q2._catches_vt(h):
                continue
            reraises = any(isinstance(x, ast.Raise) for x in ast.walk(h))
            out.append((rel, h.lineno, q2._exc_names(h), tuple(calls),
                        "BROADCAND" if (broad and not reraises)
                        else ("reraise" if reraises else "narrow")))
    return out


print("\n=== (1) ALL VT-catching handlers on the expansion/arith path ===")
print("    (BROADCAND = a live Q2 candidate; reraise/narrow = not a candidate)")
for sub in ("psh/expansion", "psh/executor"):
    for path in sorted((ROOT / sub).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for row in q2_candidates_with_lines(path.read_text(), rel):
            print(f"  {row[0]}:{row[1]:<5} {row[4]:<10} catches={row[2]} calls={row[3]}")

# --- (2) 2.3-ratchet broad handlers over the two subsystems
print("\n=== (2) 2.3-ratchet broad handlers (bare/Exception/BaseException) ===")
for sub in ("psh/expansion", "psh/executor"):
    for path in sorted((ROOT / sub).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for hit in r23.broad_handlers(path.read_text(), rel):
            print(f"  {hit[0]}:{hit[1]:<5} {hit[2]}")

# --- (3) reconciliation of the two executor arithmetic NARROW_SAFE entries
print("\n=== (3) Q2 live/stale reconciliation ===")
live = q2._live_candidates()
classified = set(q2.BROAD_MASKING) | set(q2.NARROW_SAFE)
print("  live candidates:", len(live), " classified:", len(classified))
print("  NEW (unclassified):", sorted(live - classified) or "none")
print("  STALE (classified, not live):", sorted(classified - live) or "none")
for key in sorted(classified):
    if "control_flow" in key[0] or ("core.py" in key[0] and "evaluate_arithmetic" in str(key)):
        print(f"  entry {key}\n     -> live? {key in live}")

# --- (4) 2.3 ratchet guarded-set status
print("\n=== (4) 2.3 ratchet GUARDED set ===")
for rel in r23.GUARDED:
    hits = r23.broad_handlers((ROOT / rel).read_text(), rel)
    print(f"  {rel}: broad handlers = {hits or 'NONE (clean)'}")
