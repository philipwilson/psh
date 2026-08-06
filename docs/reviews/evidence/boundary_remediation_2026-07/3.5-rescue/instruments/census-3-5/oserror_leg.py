"""Disposition row 4c: is the OSError leg of the [[ ]] net (core.py:576)
reachable, and by what?

Two halves, same discipline as the VE/TE rows:
  (a) FORCING — a sentinel-gated OSError raised on the REAL path inside
      TestExpressionEvaluator.evaluate, proving whether the leg fires at all;
  (b) USER-REACHABILITY — a corpus of [[ ]] file-test and locale forms whose
      underlying primitives (os.stat/os.access/strcoll/open) are the only
      plausible OSError sources, run under PSH_STRICT_ERRORS=1.
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
ETE = ROOT / "psh" / "executor" / "enhanced_test_evaluator.py"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def drop_pycache():
    for d in ROOT.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


print("# bash :", subprocess.run([BASH, "--version"], capture_output=True,
                                 text=True).stdout.splitlines()[0])

# --- (b) user-reachability corpus (run FIRST, unpatched) --------------------
print("\n" + "=" * 78)
print("== (b) USER-REACHABILITY: [[ ]] forms whose primitives could raise OSError")
print("=" * 78)
CORPUS = [
    ("-f missing",        '[[ -f /nonexistent/zz ]]; echo rc=$?'),
    ("-f unreadable dir", '[[ -f /dev/null/impossible ]]; echo rc=$?'),
    ("-r on /proc-ish",   '[[ -r /dev/fd/999 ]]; echo rc=$?'),
    ("-x bad fd path",    '[[ -x /dev/fd/999/x ]]; echo rc=$?'),
    ("-e empty operand",  '[[ -e "" ]]; echo rc=$?'),
    ("-e NUL-ish",        '[[ -e $\'a\\tb\' ]]; echo rc=$?'),
    ("-N missing",        '[[ -N /nonexistent/zz ]]; echo rc=$?'),
    ("-nt missing pair",  '[[ /nonexistent/a -nt /nonexistent/b ]]; echo rc=$?'),
    ("-ef missing pair",  '[[ /nonexistent/a -ef /nonexistent/b ]]; echo rc=$?'),
    ("very long path",    '[[ -f ' + '/' + 'a' * 5000 + ' ]]; echo rc=$?'),
    ("locale compare <",  '[[ abc < def ]]; echo rc=$?'),
    ("-t bad fd",         '[[ -t 999 ]]; echo rc=$?'),
]
nd = 0
for label, script in CORPUS:
    b = subprocess.run([BASH, "-c", script], cwd=str(ROOT), capture_output=True,
                       text=True, env=ENV, timeout=30)
    p = subprocess.run(PSH + ["-c", script], cwd=str(ROOT), capture_output=True,
                       text=True, env=ENV_STRICT, timeout=30)
    same = (b.returncode, b.stdout) == (p.returncode, p.stdout)
    if not same:
        nd += 1
    print(f"  {label:<20} bash rc={b.returncode} out={b.stdout.strip():<7} | "
          f"psh rc={p.returncode} out={p.stdout.strip():<7} "
          f"{'MATCH' if same else 'DIVERGE'}")
    if p.stderr.strip():
        print(f"  {'':<20}   psh stderr: {p.stderr.strip()[:110]!r}")
print(f"\n  => {len(CORPUS)-nd}/{len(CORPUS)} match; 0 psh stderr above means no")
print("     OSError surfaced to the net from any user-reachable form.")

# --- (a) forcing ------------------------------------------------------------
print("\n" + "=" * 78)
print("== (a) FORCING: does the OSError leg fire at all?")
print("=" * 78)
ANCHOR = "    def evaluate(self, expr) -> bool:\n"
backup = ETE.with_suffix(".py.bak-oserr")
shutil.copy2(ETE, backup)
before = sha(ETE)
try:
    src = ETE.read_text()
    n = src.count(ANCHOR)
    if n != 1:
        # fall back to a looser anchor and report it
        print(f"  [anchor '{ANCHOR.strip()}' count={n}; locating evaluate()]")
        import re
        m = re.search(r"\n(    def evaluate\(self[^\n]*\n)", src)
        assert m, "cannot locate evaluate()"
        anchor = m.group(1)
        print(f"  [using anchor: {anchor.strip()!r}]")
    else:
        anchor = ANCHOR
    # insert right after the def line + its docstring-free first statement:
    # simplest correct injection is at the top of the body.
    inject = anchor + (
        "        _s = getattr(expr, 'value', None) or str(expr)\n"
        "        if 'FORCEOSE' in _s:\n"
        "            raise OSError(99, 'FORCED-OSERROR')\n")
    patched = src.replace(anchor, inject, 1)
    assert patched != src
    ETE.write_text(patched)
    drop_pycache()
    for env, lab in ((ENV, "default"), (ENV_STRICT, "strict-errors")):
        r = subprocess.run(PSH + ["-c", '[[ -n FORCEOSE ]]; echo rc=$?'],
                           cwd=str(ROOT), capture_output=True, text=True,
                           env=env, timeout=30)
        print(f"  [{lab:<13}] shell rc={r.returncode} out={r.stdout.strip()!r}")
        print(f"  {'':<15}  err={r.stderr.strip()[:130]!r}")
finally:
    shutil.copy2(backup, ETE)
    backup.unlink()
    drop_pycache()
    assert sha(ETE) == before, "RESTORE FAILED"
    print(f"\n  [restore verified: sha256 {sha(ETE)[:16]}… unchanged]")
