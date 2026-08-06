"""Per-site observable probes (subtlety 2) for the remaining sites:
the PS4 net (manager.py:345), the [[ ]] net (core.py:576), and the
extract_substring VE legs (operators.py:144/:396).

Includes a sentinel-gated internal-defect injection for the PS4 net, since
its swallow is invisible from the outside by construction — that is the whole
complaint against it.
"""
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASH = "/opt/homebrew/bin/bash"
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
ENV.pop("PSH_STRICT_ERRORS", None)
ENV_STRICT = {**ENV, "PSH_STRICT_ERRORS": "1"}
PSH = [sys.executable, "-m", "psh"]
MGR = ROOT / "psh" / "expansion" / "manager.py"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def drop_pycache():
    for d in ROOT.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def pair(script, env=ENV, label=""):
    b = subprocess.run([BASH, "-c", script], cwd=str(ROOT), capture_output=True,
                       text=True, env=env, timeout=30)
    p = subprocess.run(PSH + ["-c", script], cwd=str(ROOT), capture_output=True,
                       text=True, env=env, timeout=30)
    same = (b.returncode == p.returncode and b.stdout == p.stdout)
    print(f"  {label:<34} bash rc={b.returncode} out={b.stdout.strip()[:30]!r}")
    print(f"  {'':<34} psh  rc={p.returncode} out={p.stdout.strip()[:30]!r}  "
          f"{'MATCH' if same else 'DIVERGE'}")
    print(f"  {'':<34} bash err={b.stderr.strip()[:100]!r}")
    print(f"  {'':<34} psh  err={p.stderr.strip()[:100]!r}")
    print()
    return same


print("# bash :", subprocess.run([BASH, "--version"], capture_output=True,
                                 text=True).stdout.splitlines()[0])
print("# tree :", subprocess.run(
    [sys.executable, "-c", "import psh,psh.version as v;print(psh.__file__,v.__version__)"],
    cwd=str(ROOT), capture_output=True, text=True, env=ENV).stdout.strip())

print("\n" + "=" * 78)
print("== SITE: [[ ]] net (core.py:576) — the 4 plain-VE raise sites")
print("=" * 78)
print("  enhanced_test_evaluator.py raises bare ValueError at :58 (unknown expr")
print("  TYPE), :183 (invalid REGEX), :206 (unknown binary op), :357 (unknown")
print("  compound op). Only :183 is user-reachable; the other three are")
print("  can't-happen branches = internal defects, currently masked as rc 2.\n")
pair('[[ x =~ [ ]]; echo rc=$?', label="user-reachable: bad regex")
pair('[[ x =~ ^x$ ]]; echo rc=$?', label="control: good regex")
pair('[[ -f /nonexistent/zz ]]; echo rc=$?', label="file test (OSError leg?)")
pair('[[ -f /dev/fd/999 ]]; echo rc=$?', label="file test on bad fd path")

print("=" * 78)
print("== SITE: extract_substring VE legs (operators.py:144/:396)")
print("=" * 78)
print("  parameter_expansion.py:458 raises ONE ValueError:")
print("  'substring expression < 0' — USER-REACHABLE (negative length).\n")
pair('v=abcdefgh; echo X${v:2:-99}Y; echo rc=$?', label="scalar neg length (:396)")
pair('a=(1 2 3 4); echo X${a[@]:1:-99}Y; echo rc=$?', label="array neg length (:144)")
pair('v=abcdefgh; echo X${v:2:3}Y', label="control: good substring")

print("=" * 78)
print("== SITE: PS4 net (manager.py:345) — live classes + the swallow")
print("=" * 78)
for ps4, lab in [
    ("'$((1/0)) '",   "PS4 arith error"),
    ("'${x?boom} '",  "PS4 fatal (:?-family)"),
    ("'${v@Z} '",     "PS4 bad substitution"),
    ("'$(exit 3) '",  "PS4 cmdsub nonzero"),
    ("'${a[1//]} '",  "PS4 bad subscript"),
]:
    pair(f"v=s; set -x; PS4={ps4}; echo hi", label=lab)

# --- the swallow itself: force an INTERNAL defect on the PS4 path -----------
print("=" * 78)
print("== PS4 net: sentinel-gated INTERNAL-DEFECT injection (the masker proper)")
print("=" * 78)
ANCHOR = "        ps4 = self.shell.state.get_variable('PS4', '+ ')\n"
INJECT = ANCHOR + (
    "        if 'FORCEDEFECT' in ps4:\n"
    "            def _boom(*a, **k):\n"
    "                raise TypeError('FORCED-INTERNAL-DEFECT')\n"
    "            self.expand_string_variables = _boom\n")
backup = MGR.with_suffix(".py.bak-ps4")
shutil.copy2(MGR, backup)
before = sha(MGR)
try:
    src = MGR.read_text()
    assert src.count(ANCHOR) == 1, f"anchor count {src.count(ANCHOR)}"
    MGR.write_text(src.replace(ANCHOR, INJECT, 1))
    drop_pycache()
    for env, lab in ((ENV, "default"), (ENV_STRICT, "strict-errors")):
        r = subprocess.run(
            PSH + ["-c", "set -x; PS4='FORCEDEFECT$x '; echo hi"], cwd=str(ROOT),
            capture_output=True, text=True, env=env, timeout=30)
        print(f"  [{lab:<13}] rc={r.returncode} out={r.stdout.strip()!r}")
        print(f"  {'':<15}  err={r.stderr.strip()[:150]!r}")
    print("\n  ^ An internal TypeError on the PS4 path is SWALLOWED into the raw-PS4")
    print("    fallback in BOTH modes — invisible even under PSH_STRICT_ERRORS=1.")
    print("    That is the breadth defect: the net cannot tell a shell error from")
    print("    a psh bug.")
finally:
    shutil.copy2(backup, MGR)
    backup.unlink()
    drop_pycache()
    after = sha(MGR)
    assert after == before, f"RESTORE FAILED {before} -> {after}"
    print(f"\n  [restore verified: manager.py sha256 {after[:16]}… unchanged]")
