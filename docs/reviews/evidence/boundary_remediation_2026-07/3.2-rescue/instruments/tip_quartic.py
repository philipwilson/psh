#!/usr/bin/env python3
"""Phase B — characterize the two formerly-QUARTIC consumers at the tip,
including one LARGER N than Phase A used (R1 item 7), so the pin's bound is
the achieved one rather than an aspirational one.
"""
import os
import sys
import time

PSH_ROOT = os.environ.get('PSH_ROOT', '/Users/pwilson/src/psh-r3-2')
import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402

if not os.path.realpath(pe.__file__).startswith(os.path.realpath(PSH_ROOT) + os.sep):
    sys.exit("DISCRIMINATOR FAIL")
print(f"# discriminator OK: {psh.__file__}  version={psh.version.__version__}")


def growth(label, fn, sizes, budget=30.0):
    print(f"\n## {label}")
    print(f"{'N':>7} {'seconds':>11} {'ratio':>8} {'implied exp':>12}")
    prev = None
    for n in sizes:
        subj = 'a' * n
        t0 = time.perf_counter()
        fn(subj)
        dt = time.perf_counter() - t0
        r = (dt / prev) if prev else float('nan')
        exp = (r and r == r) and __import__('math').log2(r) or float('nan')
        print(f"{n:>7} {dt:>11.4f} {r:>8.2f} {exp:>12.2f}")
        prev = dt
        if dt > budget:
            print("        (stopped)")
            break


cp = pe.PatternCompiler.compile('**(a)b')
root = cp.root
print("=" * 66)
print("formerly-QUARTIC consumers on '**(a)b' — TIP (base was x15.5/doubling)")
print("=" * 66)
growth("matching_ends", lambda s: cp.matching_ends(s, 0, pe.STRING),
       (50, 100, 200, 400, 800))
growth("span_at(pos=0)", lambda s: cp.span_at(s, 0, pe.STRING),
       (50, 100, 200, 400, 800))
growth("spanner full scan", lambda s: [cp.spanner(s, pe.STRING)(p)
                                       for p in range(len(s) + 1)],
       (50, 100, 200, 400))

print("\n" + "=" * 66)
print("TRANSITION COUNTS (deterministic; the linearity pins' substrate)")
print("=" * 66)
print(f"{'pattern':16} {'relation':9} {'N':>6} {'transitions':>13} {'ratio':>7}")
for pat, rel in (('*b', 'starts'), ('*b', 'full'), ('*a*b', 'starts'),
                 ('**(a)b', 'full'), ('*+(a)', 'starts'), ('*!(a)', 'ends')):
    r = pe.compile_pattern(pat)
    prev = None
    for n in (100, 200, 400, 800):
        t = pe.count_transitions(r, 'a' * n, relation=rel)
        ratio = (t / prev) if prev else float('nan')
        print(f"{pat:16} {rel:9} {n:>6} {t:>13} {ratio:>7.2f}")
        prev = t
