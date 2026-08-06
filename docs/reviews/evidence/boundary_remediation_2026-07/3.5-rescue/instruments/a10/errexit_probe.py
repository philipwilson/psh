"""A10.1 round-1 follow-up: the ERREXIT x -c cell for the FATAL family.

The main matrix showed 24/216 divergences in TWO shapes, only one of which the
brief predicted. This battery isolates the unpredicted one:

    bash -c 'set -e; echo ${x?boom}'   -> rc 1
    psh  -c 'set -e; echo ${x?boom}'   -> rc 127      (DIRECT channel!)

...which is a DIRECT-channel row, i.e. a row the brief lists as shipped,
probe-verified, must-not-flip behaviour. So either the brief's direct-row
model is incomplete (it was reproduced WITHOUT set -e), or this is a real
second defect. This battery decides it, and walks the SUPPRESSION axis the
substitution_child_abort_status docstring warns about (effective errexit,
not the raw flag).
"""
import os
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASH = "/opt/homebrew/bin/bash"
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
ENV.pop("PSH_STRICT_ERRORS", None)
PSH = [sys.executable, "-m", "psh"]

disc = subprocess.run(
    [sys.executable, "-c", "import psh, psh.version as v; print(psh.__file__, v.__version__)"],
    cwd=str(ROOT), capture_output=True, text=True, env=ENV)
assert disc.stdout.split()[0] == str(ROOT / "psh" / "__init__.py"), disc.stdout
print("# tree :", disc.stdout.strip())
print("# bash :", subprocess.run([BASH, "--version"], capture_output=True,
                                 text=True).stdout.splitlines()[0])
print("# py   :", sys.version.split()[0])
print()

CASES = [
    # --- the isolated cell, DIRECT channel, both errexit states -------------
    ("A1 direct  -e off        ", "echo ${x?boom}"),
    ("A2 direct  -e on         ", "set -e; echo ${x?boom}"),
    ("A3 direct  -e on, tail   ", "set -e; echo ${x?boom}; echo TAIL"),
    ("A4 direct  -e on, pre-cmd", "set -e; true; echo ${x?boom}"),
    # --- is it errexit, or merely 'set -e' being present? -------------------
    ("A5 set +e explicit       ", "set -e; set +e; echo ${x?boom}"),
    ("A6 -e via shopt -so      ", "set -o errexit; echo ${x?boom}"),
    # --- SUPPRESSION shapes (effective errexit, not the raw flag) -----------
    ("B1 -e, || recover        ", "set -e; echo ${x?boom} || echo RECOVERED; echo TAIL"),
    ("B2 -e, if-condition      ", "set -e; if echo ${x?boom}; then :; fi; echo TAIL"),
    ("B3 -e, ! negation        ", "set -e; ! echo ${x?boom}; echo TAIL"),
    ("B4 -e, && non-final      ", "set -e; echo ${x?boom} && echo AND; echo TAIL"),
    ("B5 -e, while-condition   ", "set -e; while echo ${x?boom}; do break; done; echo TAIL"),
    # --- same axis for the OTHER fatal classes ------------------------------
    ("C1 -e, :?                ", "set -e; x=; echo ${x:?boom}"),
    ("C2 -e, unknown xform     ", "set -e; v=s; echo ${v@Z}"),
    ("C3 -e, badname (rc1 cls) ", "set -e; echo ${}"),
    ("C4 -e, set -u violation  ", "set -e; set -u; echo $undef"),
    ("C5 -u alone (no -e)      ", "set -u; echo $undef"),
    # --- the DISCARD family under -e (brief: errexit-immune) ----------------
    ("D1 -e, $((1/0))          ", "set -e; echo $((1/0)); echo TAIL"),
    ("D2 -e, bad subscript     ", "set -e; echo ${a[1//]}; echo TAIL"),
    # --- eval / source containment under -e ---------------------------------
    ("E1 -e, eval fatal        ", "set -e; eval 'echo ${x?boom}'; echo TAIL"),
    ("E2 -e off, eval fatal    ", "eval 'echo ${x?boom}'; echo TAIL"),
    # --- fork boundary x errexit (the composition cell) ---------------------
    ("F1 -e, subshell          ", "set -e; ( echo ${x?boom} ); echo TAIL"),
    ("F2 -e, subshell || rec   ", "set -e; ( echo ${x?boom} ) || echo RECOVERED; echo TAIL"),
    ("F3 -e off, subshell      ", "( echo ${x?boom} ); echo TAIL"),
    ("F4 -e, cmdsub            ", "set -e; v=$( echo ${x?boom} ); echo TAIL"),
    ("F5 -e off, cmdsub||rec   ", "v=$( echo ${x?boom} ) || echo RECOVERED; echo TAIL"),
]

hdr = f"{'case':<27} {'bash rc':>7} {'psh rc':>6}  {'bash stdout':<22} {'psh stdout':<22} V"
print(hdr)
print("-" * len(hdr))
ndiv = 0
detail = []
for name, script in CASES:
    b = subprocess.run([BASH, "-c", script], cwd=str(ROOT), capture_output=True,
                       text=True, env=ENV, timeout=30)
    p = subprocess.run(PSH + ["-c", script], cwd=str(ROOT), capture_output=True,
                       text=True, env=ENV, timeout=30)
    bo = b.stdout.replace("\n", "|").strip("|") or "-"
    po = p.stdout.replace("\n", "|").strip("|") or "-"
    ok = (b.returncode == p.returncode) and (bo == po)
    if not ok:
        ndiv += 1
    print(f"{name:<27} {b.returncode:>7} {p.returncode:>6}  {bo:<22} {po:<22} "
          f"{'OK' if ok else 'DIVERGE'}")
    detail.append((name, script, b, p, ok))

print(f"\n# {len(CASES)} cases, {ndiv} DIVERGE")
print("\n=== stderr of the DIVERGING cases (message-shape evidence) ===")
for name, script, b, p, ok in detail:
    if ok:
        continue
    print(f"\n--- {name.strip()}   script: {script!r}")
    print(f"    bash rc={b.returncode} err={b.stderr.strip()!r}")
    print(f"    psh  rc={p.returncode} err={p.stderr.strip()!r}")
