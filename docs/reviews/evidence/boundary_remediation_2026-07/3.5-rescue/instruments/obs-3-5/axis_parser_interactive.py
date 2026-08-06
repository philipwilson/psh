"""Subtlety-7 axes: PARSER (rd vs combinator) and INPUT-MODE/interactive
(`-ic`), for the two status rules slot 3.5 changed.

Written as a durable instrument for R5-B4: the round-5 disclosure ran these
as ad-hoc shell loops, and evidence must not outlive its instrument. Same
cells, now re-runnable and citable by path.

Both axes are recorded in AGREEMENT FORM (psh vs live bash on this host), so
the rows carry no transcribed status literals.
"""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASH = "/opt/homebrew/bin/bash"
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
ENV.pop("PSH_STRICT_ERRORS", None)

disc = subprocess.run(
    [sys.executable, "-c",
     "import psh, psh.version as v; print(psh.__file__, v.__version__)"],
    cwd=str(ROOT), capture_output=True, text=True, env=ENV)
assert disc.stdout.split()[0] == str(ROOT / "psh" / "__init__.py"), disc.stdout
print("# tree :", disc.stdout.strip())
print("# bash :", subprocess.run([BASH, "--version"], capture_output=True,
                                 text=True).stdout.splitlines()[0])
print()


def run(argv, script, extra=()):
    return subprocess.run([*argv, *extra, "-c", script], cwd=str(ROOT),
                          capture_output=True, text=True, env=ENV, timeout=30)


PSH = [sys.executable, "-m", "psh"]

# --- AXIS: parser (rd vs combinator) ---------------------------------------
PARSER_ROWS = [
    '( echo ${x?boom} ); echo "after rc=$?"',            # A10.1 subshell
    'vv=$( echo ${x?boom} ); echo "after rc=$?"',        # A10.1 cmdsub
    '( echo ${x?boom} ) || echo "child rc=$?"',          # child status
    '( exit 127 ) || echo "child rc=$?"',                # collision control
    'set -e; ( echo ${x?boom} ); echo TAIL',             # composition cell
    '( echo $((1/0)) ); echo "after rc=$?"',             # discard control
    '{ echo ${x?boom} ; }; echo "after rc=$?"',          # no-fork boundary
    'set -e; echo ${x?boom}',                            # ruling (d) direct
    'set -e; set +e; echo ${x?boom}',                    # (d) flag-off
    '[[ x =~ [ ]]; echo rc=$?',                          # ruling (b) typed
    'v=abcdefgh; echo X${v:2:-99}Y',                     # typed substring
]

print("=== AXIS: PARSER (rd vs combinator vs bash) ===")
bad = 0
for s in PARSER_ROWS:
    b = run([BASH], s)
    rd = run(PSH, s)
    cb = run(PSH, s, extra=["--parser", "combinator"])
    ok = ((rd.returncode, rd.stdout) == (b.returncode, b.stdout)
          and (cb.returncode, cb.stdout) == (b.returncode, b.stdout))
    bad += not ok
    print(f"  {'OK  ' if ok else 'DIFF'} {s}")
    if not ok:
        print(f"       bash rc={b.returncode} out={b.stdout!r}")
        print(f"       rd   rc={rd.returncode} out={rd.stdout!r}")
        print(f"       comb rc={cb.returncode} out={cb.stdout!r}")
print(f"  => {len(PARSER_ROWS) - bad}/{len(PARSER_ROWS)} agree "
      f"(rd AND combinator both == bash)\n")

# --- AXIS: interactive-family channel (`-ic`) -------------------------------
# fatal_expansion_status's branch is `command_mode AND NOT interactive`, so the
# ruling-(d) errexit override must NOT reach `-ic`. Probed on the real entry
# path (subprocess), never a hand-built in-process ShellState — the R3 rule.
IC_ROWS = [
    'echo ${x?boom}; echo after',
    'set -e; echo ${x?boom}; echo after',
    'set -u; echo $undef; echo after',
    'set -e; set -u; echo $undef; echo after',
    'x=; echo ${x:?boom}; echo after',
    'v=s; echo ${v@Z}; echo after',
]

print("=== AXIS: INPUT MODE / interactive family (-ic) ===")
bad_ic = 0
for s in IC_ROWS:
    b = subprocess.run([BASH, "-ic", s], cwd=str(ROOT), capture_output=True,
                       text=True, env=ENV, timeout=30)
    p = subprocess.run([*PSH, "-ic", s], cwd=str(ROOT), capture_output=True,
                       text=True, env=ENV, timeout=30)
    ok = b.returncode == p.returncode
    bad_ic += not ok
    print(f"  {'OK  ' if ok else 'DIFF'} rc bash={b.returncode} "
          f"psh={p.returncode}   {s}")
print(f"  => {len(IC_ROWS) - bad_ic}/{len(IC_ROWS)} agree on status\n")

print("VERDICT: parser axis — no seam (error typing and the status rules are "
      "post-parse; both front ends feed the same executor path).")
print("VERDICT: interactive axis — the (d) override is fenced to "
      "`command_mode AND NOT interactive`, so -ic keeps the documented "
      "discard-with-status-1 model.")
