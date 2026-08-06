"""PS4 net: (a) identify WHAT escapes on the diverging bad-subscript row, and
(b) DRY-RUN the proposed narrowing `except Exception` -> `except PshError`,
proving it is observably behaviour-preserving on every probed class.

This is the "what does a narrow catch change observably" evidence the brief
asks for, applied to the PS4 site before proposing it.
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
PSH = [sys.executable, "-m", "psh"]
MGR = ROOT / "psh" / "expansion" / "manager.py"

ROWS = [
    ("arith",      "v=s; set -x; PS4='$((1/0)) '; echo hi"),
    ("fatal_q",    "v=s; set -x; PS4='${x?boom} '; echo hi"),
    ("badsub",     "v=s; set -x; PS4='${v@Z} '; echo hi"),
    ("cmdsub",     "v=s; set -x; PS4='$(exit 3) '; echo hi"),
    ("badsubscr",  "v=s; set -x; PS4='${a[1//]} '; echo hi"),
    ("plain",      "v=s; set -x; PS4='+ '; echo hi"),
    ("lineno",     "v=s; set -x; PS4='+${LINENO}: '; echo hi"),
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def drop_pycache():
    for d in ROOT.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def snap():
    out = {}
    for name, script in ROWS:
        r = subprocess.run(PSH + ["-c", script], cwd=str(ROOT),
                           capture_output=True, text=True, env=ENV, timeout=30)
        out[name] = (r.returncode, r.stdout, r.stderr)
    return out


# --- (a) what escapes on badsubscr? -----------------------------------------
print("=" * 78)
print("== (a) WHICH exception class escapes the PS4 net on the diverging row")
print("=" * 78)
probe = subprocess.run(
    [sys.executable, "-c", """
import sys, pathlib
sys.path.insert(0, %r)
from psh.shell import Shell
sh = Shell()
sh.state.set_variable('PS4', '${a[1//]} ')
try:
    sh.expansion_manager.expand_string_variables('${a[1//]} ')
except BaseException as e:
    import psh.core.exceptions as X
    print('ESCAPES:', type(e).__mro__[:4])
    print('is Exception  :', isinstance(e, Exception))
    print('is PshError   :', isinstance(e, X.PshError))
    print('is BaseExc only:', isinstance(e, BaseException) and not isinstance(e, Exception))
else:
    print('NO EXCEPTION')
""" % str(ROOT)], cwd=str(ROOT), capture_output=True, text=True, env=ENV)
print(probe.stdout or probe.stderr[-1500:])

# --- (b) dry-run the narrowing ---------------------------------------------
print("=" * 78)
print("== (b) DRY-RUN: `except Exception:` -> `except PshError:` at the PS4 net")
print("=" * 78)
base = snap()
OLD = """        try:
            return self.expand_string_variables(ps4)
        except Exception:
            return ps4
"""
# INSTRUMENT FIX (round 1): the first version of this dry-run patched only the
# handler and NOT the import, so it measured a NameError ("name 'PshError' is
# not defined") instead of the narrowing. The NameError was itself evidence —
# it proved the handler was REACHED on those rows — but the measurement was
# vacuous for its stated purpose (lesson 8: a careful label on a vacuous probe
# still misleads). manager.py has no core.exceptions import at base, so the
# patch must add one, exactly as the real change would.
NEW = """        try:
            return self.expand_string_variables(ps4)
        except PshError:
            return ps4
"""
IMPORT_ANCHOR = "from ..core.assignment_utils import ASSIGNMENT_PREFIX_RE\n"
IMPORT_NEW = ("from ..core.assignment_utils import ASSIGNMENT_PREFIX_RE\n"
              "from ..core.exceptions import PshError\n")
backup = MGR.with_suffix(".py.bak-dryrun")
shutil.copy2(MGR, backup)
before = sha(MGR)
try:
    src = MGR.read_text()
    assert src.count(OLD) == 1, f"anchor count {src.count(OLD)}"
    patched = src.replace(OLD, NEW, 1)
    assert patched.count(IMPORT_ANCHOR) == 1, "import anchor not unique"
    patched = patched.replace(IMPORT_ANCHOR, IMPORT_NEW, 1)
    MGR.write_text(patched)
    drop_pycache()
    after_rows = snap()
    # GUARD: a NameError anywhere means the instrument, not the shell, is
    # what got measured. Fail loudly rather than report a vacuous result.
    for _n, (_rc, _o, _e) in after_rows.items():
        assert "is not defined" not in _e, (
            f"INSTRUMENT DEFECT: NameError leaked on row {_n}: {_e!r}")
finally:
    shutil.copy2(backup, MGR)
    backup.unlink()
    drop_pycache()
    assert sha(MGR) == before, "RESTORE FAILED"
    print(f"[restore verified: manager.py sha256 {sha(MGR)[:16]}… unchanged]\n")

ndiff = 0
for name, _ in ROWS:
    b, a = base[name], after_rows[name]
    same = b == a
    if not same:
        ndiff += 1
    print(f"  {name:<11} {'IDENTICAL' if same else 'CHANGED'}   "
          f"rc {b[0]}->{a[0]}")
    if not same:
        print(f"      before: out={b[1]!r} err={b[2]!r}")
        print(f"      after : out={a[1]!r} err={a[2]!r}")
print(f"\n  => {len(ROWS)-ndiff}/{len(ROWS)} rows IDENTICAL under the narrowing, "
      f"{ndiff} changed")
