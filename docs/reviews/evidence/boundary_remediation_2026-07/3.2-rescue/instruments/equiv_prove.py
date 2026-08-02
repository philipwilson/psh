#!/usr/bin/env python3
"""Equivalence PROVER (slot 3.2): base arm vs tip arm, per-cell, all relations.

FORCING is structural, not a flag: each arm runs as its OWN PROCESS in its OWN
tree, so no module object, lru cache (`compile_cached`, `_sub_machinery_cached`)
or matcher memo is shared. Slot 3.1's D-3b lesson (an in-process run compared
"fast vs fast" because a cached decider laundered one arm into the other) is
structurally impossible here.

  python3 equiv_prove.py [--cells FILE] [--inject-arm {none,base,tip}]
                         [--blind] [--same-tree]

M6 self-tests (a proof that cannot fail is not a proof):
  --inject-arm tip   perturb one cell in the tip arm -> the prover MUST FAIL
  --blind            comparator forced to "equal" -> with an injection the
                     prover must WRONGLY PASS, proving the comparator (not
                     some accident of the harness) is what detects differences
  --same-tree        both arms in the tip tree -> must be identical (0)
"""
import argparse
import itertools
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TIP = os.environ.get('PSH_TIP', '/Users/pwilson/src/psh-r3-2')
BASE_SHA = os.environ.get('PSH_BASE_SHA', 'da037aa8')
PROBE_WT = os.path.join(HERE, 'basearm-wt')
NEUTRAL = os.path.join(HERE, 'neutral')


# --- deterministic fallback cell set ---------------------------------------
# (Phase B swaps in the regenerated corpus1/2/3/4 union; this set exercises the
# same shape families so the harness itself can be validated before then.)
def default_cells():
    ops = ['@', '?', '*', '+', '!']
    alts = ['a', 'b', 'a|b', 'a|', '', '*', 'a*']
    pre = ['', '*', 'a', '*a', 'a*', '**', '?', '*?']
    post = ['', 'a', 'b', '*', 'a*', '?', 'c']
    pats = set()
    for p, o, al, q in itertools.product(pre, ops, alts, post):
        pats.add(f"{p}{o}({al}){q}")
    for p in ['*b', 'a*b', '*a*b', '*', '?b', '[ab]*', '*[!a]', 'ab', '',
              r'\*', r'a\*', r'*a\*', '(a)', r'\(a\)', '*a*a*b', '[a-c]x']:
        pats.add(p)
    subjects = ['']
    for L in (1, 2, 3):
        subjects += [''.join(t) for t in itertools.product('ab', repeat=L)]
    subjects += ['c', 'ac', 'abc', 'a*b', '*', '**', 'a/b', '/a', 'A', 'aB']
    return [(p, s) for p in sorted(pats) for s in subjects]


def run_arm(tree, cells_path, out_path, inject=False):
    env = dict(os.environ)
    env['PSH_ROOT'] = tree
    env['PYTHONPATH'] = tree
    if inject:
        env['SLOT32_INJECT'] = '1'
    else:
        env.pop('SLOT32_INJECT', None)
    os.makedirs(NEUTRAL, exist_ok=True)
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, 'equiv_arm.py'), cells_path, out_path],
        cwd=NEUTRAL, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ARM FAILED ({tree}):\n{r.stdout}\n{r.stderr}")
    sys.stderr.write(f"  [{tree}] {r.stderr.strip()}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cells')
    ap.add_argument('--inject-arm', choices=['none', 'base', 'tip'], default='none')
    ap.add_argument('--blind', action='store_true')
    ap.add_argument('--same-tree', action='store_true')
    a = ap.parse_args()

    cells_path = os.path.join(HERE, 'cells.jsonl')
    if a.cells:
        # MUST be absolute: the arms run with a NEUTRAL cwd (so that a bare
        # `python -m psh` cannot pick a psh package off the current directory),
        # which silently breaks any relative input path.
        cells_path = os.path.abspath(a.cells)
    else:
        cells = default_cells()
        with open(cells_path, 'w') as f:
            for p, s in cells:
                f.write(json.dumps([p, s]) + '\n')
    n_cells = sum(1 for _ in open(cells_path))
    print(f"cells: {n_cells}")

    # base arm tree: detached probe worktree at BASE_SHA (removed after)
    made_wt = False
    base_tree = TIP
    if not a.same_tree:
        if os.path.exists(PROBE_WT):
            subprocess.run(['git', '-C', TIP, 'worktree', 'remove', '--force',
                            PROBE_WT], capture_output=True)
        r = subprocess.run(['git', '-C', TIP, 'worktree', 'add', '--detach',
                            PROBE_WT, BASE_SHA], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"worktree add failed: {r.stderr}")
        made_wt = True
        base_tree = PROBE_WT
        sha = subprocess.run(['git', '-C', PROBE_WT, 'rev-parse', 'HEAD'],
                             capture_output=True, text=True).stdout.strip()
        print(f"base arm worktree {PROBE_WT} @ {sha}")

    try:
        base_out = os.path.join(HERE, 'arm_base.jsonl')
        tip_out = os.path.join(HERE, 'arm_tip.jsonl')
        run_arm(base_tree, cells_path, base_out, inject=(a.inject_arm == 'base'))
        run_arm(TIP, cells_path, tip_out, inject=(a.inject_arm == 'tip'))

        disagreements = []
        with open(base_out) as fb, open(tip_out) as ft:
            for lb, lt in zip(fb, ft):
                pb, sb, rb = json.loads(lb)
                pt, st, rt = json.loads(lt)
                assert (pb, sb) == (pt, st), "cell streams desynchronised"
                if a.blind:
                    continue                      # M6: comparator disabled
                for key in sorted(set(rb) | set(rt)):
                    if rb.get(key, '<absent>') != rt.get(key, '<absent>'):
                        disagreements.append((pb, sb, key,
                                              rb.get(key, '<absent>'),
                                              rt.get(key, '<absent>')))
    finally:
        if made_wt:
            subprocess.run(['git', '-C', TIP, 'worktree', 'remove', '--force',
                            PROBE_WT], capture_output=True)
            print(f"probe worktree removed: {not os.path.exists(PROBE_WT)}")

    keys = len(json.loads(open(base_out).readline())[2])
    print(f"comparisons: {n_cells} cells x {keys} recorded relations/operators "
          f"= {n_cells * keys}")
    print(f"DISAGREEMENTS: {len(disagreements)}")
    for d in disagreements[:25]:
        print(f"  pat={d[0]!r} subj={d[1]!r} key={d[2]}: base={d[3]!r} tip={d[4]!r}")
    return 1 if disagreements else 0


sys.exit(main())
