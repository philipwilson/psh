#!/usr/bin/env python3
"""B3 — hunt for any remaining case where WALL is quadratic but the
transition counter says linear (the blindness R4 names).

Harness discipline: the spanner is built ONCE per subject, exactly as the
consumer builds it. (A first version of this probe built one per position and
manufactured its own quadratic — recorded because it is the same class of
error as measuring perf in a live worktree.)

A row is a BLIND SPOT iff wall ratio >= 3.0 while transition ratio <= 2.6.
"""
import os
import sys
import time

PSH_ROOT = os.environ.get('PSH_ROOT', '/Users/pwilson/src/psh-r3-2')
import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402

if not os.path.realpath(pe.__file__).startswith(os.path.realpath(PSH_ROOT) + os.sep):
    sys.exit("DISCRIMINATOR FAIL")
print(f"# {psh.__file__}")

SIZES = (250, 500, 1000)


def relation_runners(cp):
    def scan(s):
        span_at = cp.spanner(s, pe.STRING)          # ONCE, like the consumer
        for p in range(len(s) + 1):
            span_at(p)

    return {
        'full': lambda s: cp.full_match(s, pe.STRING),
        'ends': lambda s: cp.matching_ends(s, 0, pe.STRING),
        'starts': lambda s: cp.matching_starts(s, len(s), pe.STRING),
        'scan': scan,
    }


CASES = [
    # (pattern, subject-builder, label) — shaped so the group IS reached
    ('!(a)b', lambda n: 'a' * n, 'a*n (no match)'),
    ('!(a)b', lambda n: 'ab' * n, 'ab*n (matches)'),
    ('!(a)b', lambda n: 'a' * n + 'b', 'a*n+b'),
    ('*(ab)b', lambda n: 'ab' * n, 'ab*n'),
    ('*(ab)b', lambda n: 'a' * n, 'a*n'),
    ('+([[:space:]])', lambda n: ' ' * n, 'sp*n (matches)'),
    ('+(a)', lambda n: 'a' * n, 'a*n (matches)'),
    ('!(x)', lambda n: 'x' * n, 'x*n'),
    ('@(a|b)c', lambda n: 'ab' * n, 'ab*n'),
    ('*x', lambda n: 'a' * n, 'a*n (plain control)'),
]

print(f"\n{'pattern':16} {'subject':18} {'rel':7} {'wall ratio':>11} "
      f"{'trans ratio':>12}  verdict")
blind = []
for pat, mk, label in CASES:
    cp = pe.PatternCompiler.compile(pat, extglob=True)
    runners = relation_runners(cp)
    for rel, fn in runners.items():
        walls, trans = [], []
        for n in SIZES:
            s = mk(n)
            t0 = time.perf_counter()
            fn(s)
            walls.append(time.perf_counter() - t0)
            trans.append(pe.count_transitions(cp.root, s, relation=rel))
        wr = max(walls[i + 1] / walls[i] for i in range(len(walls) - 1)
                 if walls[i] > 0) if all(w > 0 for w in walls) else float('nan')
        tr = max(trans[i + 1] / trans[i] for i in range(len(trans) - 1)
                 if trans[i] > 0) if all(t > 0 for t in trans) else float('nan')
        verdict = ''
        if wr == wr and tr == tr and wr >= 3.0 and tr <= 2.6:
            verdict = '*** BLIND SPOT ***'
            blind.append((pat, label, rel, wr, tr))
        elif wr == wr and wr >= 3.0:
            verdict = 'both see quadratic (ok)'
        print(f"{pat:16} {label:18} {rel:7} {wr:>11.2f} {tr:>12.2f}  {verdict}")

print(f"\nBLIND SPOTS: {len(blind)}")
for b in blind:
    print(f"  {b}")
