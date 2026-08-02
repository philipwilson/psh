#!/usr/bin/env python3
"""Rebuild the 3.1 corpus UNIVERSE (the (pattern, subject) cells) for the
slot-3.2 equivalence proof.

My proof is base-arm vs tip-arm, so it needs the 3.1 corpora's CELLS but not
their bash oracle column: bash established the MODEL in 3.1 and the model is
already locked by the shipped battery; what 3.2 must show is that the rewrite
computes the same relation the shipped engine does, on the same universe.

The cells are taken from the COMMITTED generators by executing each one down
to its bash-spawn boundary, so the grammar is theirs, not a re-derivation of
theirs (re-typing the grammar would be exactly the kind of silent divergence
the corpus exists to catch). corpus4's backslash axis is a flat constant list
and is read from corpus5_equiv.py, which already carries it as constants.
"""
import itertools
import json
import os
import sys

INSTR = ('/Users/pwilson/src/psh-r3-2/docs/reviews/evidence/'
         'boundary_remediation_2026-07/3.1-rescue/instruments')
WT = os.environ.get('PSH_TIP', '/Users/pwilson/src/psh-r3-2')

# Each generator is executed only as far as its bash spawn; everything after
# builds the oracle column we do not need.
TRUNCATE_AT = {
    'corpus1.py': '# --- bash, one spawn',
    'corpus2.py': 'script_path = os.path.join(SLOTDIR',
    'corpus3.py': 'script_path = os.path.join(SLOTDIR',
}

sys.path.insert(0, INSTR)      # the generators import bash_model as a sibling

cells = set()
report = []

for name, marker in TRUNCATE_AT.items():
    src = open(os.path.join(INSTR, name)).read()
    idx = src.find(marker)
    if idx < 0:
        sys.exit(f"{name}: truncation marker not found — generator changed")
    head = src[:idx]
    ns = {'__name__': '__cellsrc__', '__file__': os.path.join(INSTR, name)}
    os.environ['PSH_WORKTREE'] = WT
    try:
        exec(compile(head, name, 'exec'), ns)
    except Exception as e:                       # noqa: BLE001
        sys.exit(f"{name}: exec failed: {type(e).__name__}: {e}")
    got = ns.get('CELLS')
    if not got:
        sys.exit(f"{name}: no CELLS built")
    # Row shape differs by generator: corpus1/2 emit (cid, subject, pattern),
    # corpus3 emits (subject, pattern). Read the shape, do not assume it.
    before = len(cells)
    for row in got:
        if len(row) == 3:
            _cid, subject, pattern = row
        elif len(row) == 2:
            subject, pattern = row
        else:
            sys.exit(f"{name}: unexpected CELLS row arity {len(row)}: {row!r}")
        cells.add((pattern, subject))
    report.append((name, len(got), len(cells) - before))

# corpus4 backslash axis (constants, duplicated in corpus5_equiv.py)
BS_PATS = [
    r"\*", r"a\*", r"*a\*", r"*\*", r"\*a", r"\**", r"*\*a", r"a\*b",
    r"a\\*", r"a\\\*", r"*a\\*", r"*a\\\*", r"\\*", r"\\\*",
    r"\?", r"*\?", r"a\?", r"\?*", r"*a\?",
    r"\*!(a)", r"!(\*)", r"*!(\*)", r"@(\*|a)", r"*@(a|\*)", r"+(\*)",
    r"?(\*)a", r"*a\*!(b)",
    "(a)", r"\(a\)", "(a|b)", r"*(a)\*",
]
BS_SUBJECTS = ["", "a", "b", "*", "a*", "*b", "a*b", "ab", "**", "a**b",
               "(a)", "b(a)c", "?", "a?b", "\\", "a\\b", "a*b*", "*a*"]
before = len(cells)
for p in BS_PATS:
    for s in BS_SUBJECTS:
        cells.add((p, s))
report.append(('corpus4 (backslash axis)', len(BS_PATS) * len(BS_SUBJECTS),
               len(cells) - before))

for name, raw, added in report:
    print(f"  {name:28} rows={raw:>7}  new distinct={added:>7}")
print(f"\nDISTINCT UNION: {len(cells)} cells")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'corpus_cells.jsonl')
with open(out, 'w') as f:
    for p, s in sorted(cells):
        f.write(json.dumps([p, s]) + '\n')
print(f"written: {out}")
