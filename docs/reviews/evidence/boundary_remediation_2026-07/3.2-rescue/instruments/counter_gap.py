#!/usr/bin/env python3
"""A4 — is the EXISTING `states` counter able to see the cubic?

`_BashMatcher.match` increments `states` only on a memo MISS, so it counts
DISTINCT (seq, ei, si, se) keys — O(nodes*n^2) — while the real work is the
loop iteration inside `_extmatch`/`_closure`, which re-walks O(n^2) memo HITS
per entry position, O(n) entry positions => O(n^3).

If states grows ~n^2 while wall time grows ~n^3, the chartered
"deterministic transition counts" pin CANNOT be built on `states` as-is.
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


def measure(pat, mk_subj, sizes, extglob=True):
    print(f"\n## pattern={pat!r}   quirk={pe._seq_bash_quirk(pe.compile_pattern(pat, extglob=extglob))}")
    print(f"{'N':>6} {'states':>12} {'st.ratio':>9} {'memo_len':>10} "
          f"{'seconds':>10} {'t.ratio':>8}")
    ps = pt = None
    for n in sizes:
        subj = mk_subj(n)
        root = pe.compile_pattern(pat, extglob=extglob)
        # states via the shipped counter
        t0 = time.perf_counter()
        st = pe.count_states(root, subj)
        dt = time.perf_counter() - t0
        # memo size (distinct keys) for the quirk path
        memo_len = -1
        if pe._seq_bash_quirk(root):
            bm = pe._BashMatcher(subj, False, False)
            bm.match(root, 0, 0, len(subj))
            memo_len = len(bm.memo)
        sr = (st / ps) if ps else float('nan')
        tr = (dt / pt) if pt else float('nan')
        print(f"{n:>6} {st:>12} {sr:>9.2f} {memo_len:>10} {dt:>10.4f} {tr:>8.2f}")
        ps, pt = st, dt


print("=" * 76)
print("The CUBIC pattern the existing pin claims to guard")
print("=" * 76)
measure('**(a)b', lambda n: 'a' * n, (16, 32, 64, 128, 256))

print("\n" + "=" * 76)
print("The existing pin's own bound, evaluated (assert states <= (n+2)**2)")
print("=" * 76)
for n in (16, 64, 128, 256):
    st = pe.count_states(pe.compile_pattern('**(a)b'), 'a' * n)
    bound = (n + 2) ** 2
    print(f"  n={n:>4} states={st:>8} bound={bound:>8} "
          f"{'PASS' if st <= bound else 'FAIL':>5}  headroom={bound - st:>8}")

print("\n" + "=" * 76)
print("Linear-family rows the same pin guards (bound 8*(n+2))")
print("=" * 76)
for pat in ('*!(a)', '*?(a|b)', '*@(a|*)'):
    measure(pat, lambda n: 'a' * n, (16, 64, 256))

print("\n" + "=" * 76)
print("matching_starts (non-quirk '*b') — states vs wall time")
print("=" * 76)
print(f"{'N':>6} {'sum_states':>12} {'ratio':>8} {'seconds':>10} {'t.ratio':>8}")
cp = pe.PatternCompiler.compile('*b')
ps = pt = None
for n in (250, 500, 1000, 2000):
    subj = 'a' * n
    m = pe._Matcher(subj, False, False)
    t0 = time.perf_counter()
    for i in range(len(subj) + 1):
        m._ends(cp.root, 0, i)
    dt = time.perf_counter() - t0
    st = m.states
    sr = (st / ps) if ps else float('nan')
    tr = (dt / pt) if pt else float('nan')
    print(f"{n:>6} {st:>12} {sr:>8.2f} {dt:>10.4f} {tr:>8.2f}")
    ps, pt = st, dt
