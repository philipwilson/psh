#!/usr/bin/env python3
"""Slot 3.1 Phase A anchor probes: H7a/H7b/H7c red-on-base, full ceremony.

Oracle: PATH bash /opt/homebrew/bin/bash (version printed below). NEVER /bin/bash.
psh under test: worktree /Users/pwilson/src/psh-r3-1 at base 29456fdc.
Neutral cwd + PYTHONPATH + import discriminator per B71.
"""
import os
import subprocess
import sys

WORKTREE = "/Users/pwilson/src/psh-r3-1"
BASH = "/opt/homebrew/bin/bash"
NEUTRAL = os.path.join(WORKTREE, "tmp", "slot31", "neutral")
GLOBDIR = os.path.join(WORKTREE, "tmp", "slot31", "globdir")
os.makedirs(NEUTRAL, exist_ok=True)
os.makedirs(GLOBDIR, exist_ok=True)
for name in ("a", "ab", "b"):
    with open(os.path.join(GLOBDIR, name), "w") as f:
        f.write("x")

ENV = {
    "PATH": os.environ["PATH"],
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "PYTHONPATH": WORKTREE,
}


def run(argv, cwd=NEUTRAL):
    r = subprocess.run(argv, capture_output=True, text=True, env=ENV,
                       cwd=cwd, timeout=30)
    return r.returncode, r.stdout, r.stderr


def bash_cell(script, cwd=NEUTRAL):
    return run([BASH, "--norc", "-c", script], cwd=cwd)


def psh_cell(script, parser="rd", cwd=NEUTRAL):
    return run([sys.executable, "-m", "psh", "--parser", parser, "-c", script],
               cwd=cwd)


def fmt(r):
    rc, out, err = r
    return f"rc={rc} out={out!r} err={err!r}"


# --- ceremony: versions + discriminator -------------------------------------
print("== ceremony ==")
print("bash:", subprocess.run([BASH, "--version"], capture_output=True,
                              text=True).stdout.splitlines()[0])
rc, out, err = run([sys.executable, "-c", "import psh; print(psh.__file__); "
                    "import psh.version; print(psh.version.__version__)"])
print(f"psh discriminator (cwd={NEUTRAL}):\n{out}", end="")
rc, out, _ = run(["git", "-C", WORKTREE, "rev-parse", "HEAD"])
print("tree SHA:", out.strip())

# --- the three [[ anchor rows, extglob on/off, both parsers ------------------
ANCHORS = [
    ("H7a", '[[ "" == *@(a|*) ]]'),
    ("H7b", '[[ a == *!(a) ]]'),
    ("H7c", '[[ "" == *!(*) ]]'),
]
print("\n== [[ anchors: rc per shell x extglob on/off x parser ==")
for rid, expr in ANCHORS:
    for eg, egname in (("shopt -s extglob; ", "eg=on "), ("", "eg=off")):
        script = f"{eg}{expr}; echo rc=$?"
        cells = [("bash", bash_cell(script)),
                 ("psh-rd", psh_cell(script, "rd")),
                 ("psh-comb", psh_cell(script, "combinator"))]
        row = "  ".join(f"{name}:[{fmt(r)}]" for name, r in cells)
        print(f"{rid} {egname} {expr!r}\n    {row}")

# --- per-consumer propagation cells (extglob on) -----------------------------
print("\n== per-consumer propagation cells (shopt -s extglob) ==")
CONSUMER_CELLS = [
    ("case_H7b", 'case a in *!(a)) echo M;; *) echo N;; esac'),
    ("case_H7a", 'case "" in *@(a|*)) echo M;; *) echo N;; esac'),
    ("case_H7c", 'case "" in *!(*)) echo M;; *) echo N;; esac'),
    ("rem_H7b", 'v=a; printf "[%s][%s]\\n" "${v#*!(a)}" "${v##*!(a)}"'),
    ("rem_H7b_sfx", 'v=a; printf "[%s][%s]\\n" "${v%*!(a)}" "${v%%*!(a)}"'),
    ("rem_H7a", 'v=""; printf "[%s][%s]\\n" "${v#*@(a|*)}" "${v##*@(a|*)}"'),
    ("sub_H7b", 'v=a; printf "[%s][%s]\\n" "${v/*!(a)/X}" "${v//*!(a)/X}"'),
    ("sub_H7a", 'v=""; printf "[%s][%s]\\n" "${v/*@(a|*)/X}" "${v//*@(a|*)/X}"'),
    ("sub_H7c", 'v=""; printf "[%s][%s]\\n" "${v/*!(*)/X}" "${v//*!(*)/X}"'),
]
for rid, body in CONSUMER_CELLS:
    script = "shopt -s extglob; " + body + "; echo rc=$?"
    b = bash_cell(script)
    p = psh_cell(script, "rd")
    mark = "SAME" if (b[0], b[1]) == (p[0], p[1]) else "DIFF"
    print(f"{rid} [{mark}]\n    bash:[{fmt(b)}]\n    psh :[{fmt(p)}]")

# --- pathname glob propagation (fixture dir: a, ab, b) -----------------------
print("\n== pathname glob cells (cwd=globdir with files: a ab b) ==")
GLOB_CELLS = [
    ("glob_negA", 'printf "[%s]\\n" *!(a)'),
    ("glob_negStar", 'printf "[%s]\\n" *!(*)'),
    ("glob_atStar", 'printf "[%s]\\n" *@(a|*)'),
]
for rid, body in GLOB_CELLS:
    script = "shopt -s extglob; " + body + "; echo rc=$?"
    b = bash_cell(script, cwd=GLOBDIR)
    p = psh_cell(script, "rd", cwd=GLOBDIR)
    mark = "SAME" if (b[0], b[1]) == (p[0], p[1]) else "DIFF"
    print(f"{rid} [{mark}]\n    bash:[{fmt(b)}]\n    psh :[{fmt(p)}]")
