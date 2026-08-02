#!/usr/bin/env python3
"""Slot 3.1 Phase A: per-consumer grid — consumer x anchoring x empty/
non-empty subject x quirk-class pattern, end-to-end bash vs psh (base).

Consumers: [[ == ]], case, ${v#/##/%/%%}, ${v/ // /# /%}, pathname glob.
Plus: KNOWN_DIVERGENCES measurement grid (nullable patterns x 4 substitution
anchors x subjects '' and 'a'), extglob-off controls, quoted-part rows.

Ceremony: oracle PATH bash /opt/homebrew/bin/bash 5.2.26 --norc LC_ALL=C;
psh base 29456fdc end-to-end (subprocess, both consumers' real seams),
neutral cwd, PYTHONPATH=worktree. Output: consumer_grid.tsv + DIFF summary.
"""
import os
import subprocess
import sys

WORKTREE = "/Users/pwilson/src/psh-r3-1"
BASH = "/opt/homebrew/bin/bash"
SLOTDIR = os.path.join(WORKTREE, "tmp", "slot31")
NEUTRAL = os.path.join(SLOTDIR, "neutral")
GLOBDIR2 = os.path.join(SLOTDIR, "globdir2")
ENV = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"),
       "LC_ALL": "C", "PYTHONPATH": WORKTREE}

os.makedirs(GLOBDIR2, exist_ok=True)
for name in ("a", "ab", "b", "ba", ".ha"):
    fp = os.path.join(GLOBDIR2, name)
    if not os.path.exists(fp):
        with open(fp, "w") as f:
            f.write("x")
subdir = os.path.join(GLOBDIR2, "sub")
os.makedirs(subdir, exist_ok=True)
for name in ("a", "ab"):
    fp = os.path.join(subdir, name)
    if not os.path.exists(fp):
        with open(fp, "w") as f:
            f.write("x")

PATTERNS = ["*!(a)", "*!(*)", "*@(a|*)", "*?(a)", "?(a)", "!(a)", "!(*)",
            "*(a)", "*@()", "@(*!(a))", "*!(a)b", "?(x)", "!(x)", "@(|a)"]
SUBJECTS = ["", "a", "b", "ab", "aa"]

lines = ["shopt -s extglob"]
tags = []


def emit(tag, line):
    tags.append(tag)
    lines.append(line)


for pi, pat in enumerate(PATTERNS):
    for si, subj in enumerate(SUBJECTS):
        rid = f"p{pi}s{si}"
        q = f"'{subj}'"
        emit(f"{rid}_dbr", f"if [[ {q} == {pat} ]]; then echo '{rid}_dbr=Y';"
                           f" else echo '{rid}_dbr=N'; fi")
        emit(f"{rid}_case", f"case {q} in\n{pat}) echo '{rid}_case=Y';;\n"
                            f"*) echo '{rid}_case=N';;\nesac")
        emit(f"{rid}_rem", f"s={q}; printf '{rid}_rem=[%s][%s][%s][%s]\\n'"
                           f" \"${{s#{pat}}}\" \"${{s##{pat}}}\""
                           f" \"${{s%{pat}}}\" \"${{s%%{pat}}}\"")
        emit(f"{rid}_sub", f"s={q}; printf '{rid}_sub=[%s][%s][%s][%s]\\n'"
                           f" \"${{s/{pat}/Z}}\" \"${{s//{pat}/Z}}\""
                           f" \"${{s/#{pat}/Z}}\" \"${{s/%{pat}/Z}}\"")

# quoted-part rows: quoted chars inside/around negation
QROWS = [
    ("q1", "[[ 'a' == !(\"a\") ]]; echo q1=$?"),
    ("q2", "[[ 'b' == !(\"a\") ]]; echo q2=$?"),
    ("q3", "[[ '*' == !(\"*\") ]]; echo q3=$?"),
    ("q4", "[[ 'x' == !(\"*\") ]]; echo q4=$?"),
    ("q5", "[[ 'a' == \"*!(a)\" ]]; echo q5=$?"),
    ("q6", "[[ '*!(a)' == \"*!(a)\" ]]; echo q6=$?"),
    ("q7", "v='a'; printf 'q7=[%s]\\n' \"${v/*!(\"a\")/Z}\""),
    ("q8", "[[ '' == *!(\"*\") ]]; echo q8=$?"),
    ("q9", "[[ '' == *@(\"a\"|*) ]]; echo q9=$?"),
]
for tag, line in QROWS:
    emit(tag, line)

# extglob-off controls: ${} patterns parse either way; prefix chars literal
OFFROWS = [
    ("off1", "shopt -u extglob; v='!(a)'; printf 'off1=[%s]\\n' \"${v#!(a)}\""),
    ("off2", "shopt -u extglob; v='ab'; printf 'off2=[%s]\\n' \"${v#*!(a)}\""),
    ("off3", "shopt -u extglob; v='a'; printf 'off3=[%s]\\n' \"${v/?(a)/Z}\""),
    ("off4", "shopt -u extglob; [[ 'ab' == *!(a) ]]; echo off4=$?"),
    ("off5", "shopt -u extglob; [[ '?(a)' == ?(a) ]]; echo off5=$?"),
    ("off6", "shopt -s extglob"),  # restore for any later rows
]
for tag, line in OFFROWS:
    emit(tag, line)

script = "\n".join(lines) + "\n"


def run(argv, cwd, inp=None):
    r = subprocess.run(argv, capture_output=True, text=True, env=ENV,
                       cwd=cwd, timeout=120, input=inp)
    return r


def tagdict(out):
    d = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v
    return d


b = run([BASH, "--norc", "-c", script], NEUTRAL)
p = run([sys.executable, "-m", "psh", "-c", script], NEUTRAL)
bt, pt = tagdict(b.stdout), tagdict(p.stdout)

with open(os.path.join(SLOTDIR, "consumer_grid.tsv"), "w") as f:
    f.write("tag\tbash\tpsh\tsame\n")
    for tag in tags:
        if tag == "off6":
            continue
        tb, tp = bt.get(tag), pt.get(tag)
        f.write(f"{tag}\t{tb}\t{tp}\t{'Y' if tb == tp else 'DIFF'}\n")

ndiff = sum(1 for t in tags if t != "off6" and bt.get(t) != pt.get(t))
print(f"string-consumer grid: {len(tags)-1} rows, DIFF={ndiff}")
print("pattern/subject key:",
      "; ".join(f"p{i}={p_!r}" for i, p_ in enumerate(PATTERNS)))
print("subjects:", "; ".join(f"s{i}={s!r}" for i, s in enumerate(SUBJECTS)))
for tag in tags:
    if tag != "off6" and bt.get(tag) != pt.get(tag):
        print(f"  DIFF {tag}: bash={bt.get(tag)!r} psh={pt.get(tag)!r}")

# ---- pathname glob grid (separate script; cwd=globdir2) --------------------
glines = ["shopt -s extglob"]
gtags = []
GPATS = ["*!(a)", "!(a)", "!(*)", "!(a*)", "*?(a)", "?(a)b", "sub/!(a)",
         "!(sub)", "!(.)*", "!(a)/a", ".!(a)", "*!(a)b"]
for gi, gp in enumerate(GPATS):
    gtags.append(f"g{gi}")
    glines.append(f"printf 'g{gi}=[%s]' {gp}; echo")
gscript = "\n".join(glines) + "\n"
gb = run([BASH, "--norc", "-c", gscript], GLOBDIR2)
gp_ = run([sys.executable, "-m", "psh", "-c", gscript], GLOBDIR2)
gbt, gpt = tagdict(gb.stdout), tagdict(gp_.stdout)
gdiff = sum(1 for t in gtags if gbt.get(t) != gpt.get(t))
print(f"\nglob grid (files a ab b ba .ha sub/a sub/ab): {len(gtags)} rows, "
      f"DIFF={gdiff}")
print("glob key:", "; ".join(f"g{i}={p_!r}" for i, p_ in enumerate(GPATS)))
for t in gtags:
    if gbt.get(t) != gpt.get(t):
        print(f"  DIFF {t}: bash={gbt.get(t)!r} psh={gpt.get(t)!r}")
with open(os.path.join(SLOTDIR, "glob_grid.tsv"), "w") as f:
    f.write("tag\tbash\tpsh\tsame\n")
    for t in gtags:
        f.write(f"{t}\t{gbt.get(t)}\t{gpt.get(t)}\t"
                f"{'Y' if gbt.get(t) == gpt.get(t) else 'DIFF'}\n")
