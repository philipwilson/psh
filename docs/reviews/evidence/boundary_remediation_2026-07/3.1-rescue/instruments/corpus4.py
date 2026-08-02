#!/usr/bin/env python3
"""Slot 3.1 Phase D (R10 B2-1): backslash / escaped-metachar axis corpus.

Patterns with escaped metachars (heads, tails incl. even/odd backslash runs
before a trailing star, middles, paren-pun shapes) crossed with subjects
containing literal metachars, through FOUR consumer contexts: [[ , case,
removal (4 legs), substitution (4 anchors). End-to-end bash vs psh; tags.

Ceremony: PATH bash /opt/homebrew/bin/bash 5.2.26 --norc LC_ALL=C, one
stdin script per shell; psh from PSH_WORKTREE (discriminator asserted).
Output: corpus4_results.tsv + DIFF census by consumer.
"""
import os
import subprocess
import sys

WORKTREE = os.environ.get("PSH_WORKTREE", "/Users/pwilson/src/psh-r3-1")
BASH = "/opt/homebrew/bin/bash"
SLOTDIR = os.path.join(WORKTREE, "tmp", "slot31")
NEUTRAL = os.path.join(SLOTDIR, "neutral")
ENV = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"),
       "LC_ALL": "C", "PYTHONPATH": WORKTREE}

# Pattern spellings as they appear UNQUOTED in shell source (backslash =
# escape). Sets: ALL-context vs substitution-only (paren shapes would be
# case/[[ syntax hazards).
PATS_ALL = [
    r"\*", r"a\*", r"*a\*", r"*\*", r"\*a", r"\**", r"*\*a", r"a\*b",
    r"a\\*", r"a\\\*", r"*a\\*", r"*a\\\*", r"\\*", r"\\\*",
    r"\?", r"*\?", r"a\?", r"\?*", r"*a\?",
    r"\*!(a)", r"!(\*)", r"*!(\*)", r"@(\*|a)", r"*@(a|\*)", r"+(\*)",
    r"?(\*)a", r"*a\*!(b)",
]
PATS_SUB_ONLY = [
    "(a)", r"\(a\)", "(a|b)", r"*(a)\*",
]
SUBJECTS = ["", "a", "b", "*", "a*", "*b", "a*b", "ab", "**", "a**b",
            "(a)", "b(a)c", "?", "a?b", "\\", "a\\b", "a*b*", "*a*"]


def shq(s):
    return "'" + s.replace("'", "'\\''") + "'"


lines = ["shopt -s extglob"]
tags = []


def emit(tag, line):
    tags.append(tag)
    lines.append(line)


rid = 0
for pat in PATS_ALL:
    for subj in SUBJECTS:
        r = f"r{rid}"
        rid += 1
        q = shq(subj)
        emit(f"{r}_dbr", f"[[ {q} == {pat} ]]; printf '{r}_dbr=%s\\n' $?")
        emit(f"{r}_case", f"case {q} in\n{pat}) printf '{r}_case=M\\n';;\n"
                          f"*) printf '{r}_case=N\\n';;\nesac")
        emit(f"{r}_rem", f"v={q}; printf '{r}_rem=[%s][%s][%s][%s]\\n'"
                         f' "${{v#{pat}}}" "${{v##{pat}}}"'
                         f' "${{v%{pat}}}" "${{v%%{pat}}}"')
        emit(f"{r}_sub", f"v={q}; printf '{r}_sub=[%s][%s][%s][%s]\\n'"
                         f' "${{v/{pat}/Z}}" "${{v//{pat}/Z}}"'
                         f' "${{v/#{pat}/Z}}" "${{v/%{pat}/Z}}"')
for pat in PATS_SUB_ONLY:
    for subj in SUBJECTS:
        r = f"r{rid}"
        rid += 1
        q = shq(subj)
        emit(f"{r}_sub", f"v={q}; printf '{r}_sub=[%s][%s][%s][%s]\\n'"
                         f' "${{v/{pat}/Z}}" "${{v//{pat}/Z}}"'
                         f' "${{v/#{pat}/Z}}" "${{v/%{pat}/Z}}"')

script = "\n".join(lines) + "\n"
with open(os.path.join(SLOTDIR, "corpus4_script.sh"), "w") as f:
    f.write(script)


def run(argv, inp):
    return subprocess.run(argv, input=inp, capture_output=True, text=True,
                          env=ENV, cwd=NEUTRAL, timeout=300)


def tagdict(out):
    d = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v
    return d


b = run([BASH, "--norc"], script)
p = run([sys.executable, "-m", "psh"], script)
bt, pt = tagdict(b.stdout), tagdict(p.stdout)

diff = [(t, bt.get(t), pt.get(t)) for t in tags if bt.get(t) != pt.get(t)]
with open(os.path.join(SLOTDIR, "corpus4_results.tsv"), "w") as f:
    f.write("tag\tbash\tpsh\tsame\n")
    for t in tags:
        f.write(f"{t}\t{bt.get(t)}\t{pt.get(t)}\t"
                f"{'Y' if bt.get(t) == pt.get(t) else 'DIFF'}\n")

from collections import Counter  # noqa: E402
by_kind = Counter(t.rsplit('_', 1)[1] for t, _b, _p in diff)
print(f"corpus4: {len(tags)} cells, DIFF={len(diff)}; by consumer: "
      f"{dict(by_kind)}")
# map tags back to (pattern, subject) for the census
cellmap = {}
rid = 0
for pat in PATS_ALL:
    for subj in SUBJECTS:
        cellmap[f"r{rid}"] = (pat, subj)
        rid += 1
for pat in PATS_SUB_ONLY:
    for subj in SUBJECTS:
        cellmap[f"r{rid}"] = (pat, subj)
        rid += 1
for t, bv, pv in diff[:60]:
    base_tag = t.rsplit('_', 1)[0]
    pat, subj = cellmap[base_tag]
    print(f"  DIFF {t} pat={pat!r} subj={subj!r} bash={bv!r} psh={pv!r}")
