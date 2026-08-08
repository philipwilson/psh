# Q1 probe 15 (HIGH-7 perf half): matching_starts linear at tip.
# Base: 1.45 s @ N=8000 with 4x/doubling growth. Tip claim (v0.764.0):
# ~0.0002 s @ N=8000 (linear). Generous margins per evidence rule 9:
# require t(8000) < 0.5 s (3x under the base number) and growth ratio
# t(8000)/t(4000) < 3 (linear ~2, base quadratic ~4).
# Axis: REGRESSION vs recorded base measurement.
import os
import sys
import time

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt')
assert os.getcwd() == WT
sys.path.insert(0, WT)
import psh.version
assert psh.version.__version__ == '0.773.0'
assert psh.version.__file__.startswith(WT)
print("DISCRIMINATOR OK:", psh.version.__version__)

from psh.expansion.pattern_engine import PatternCompiler, STRING


def t_starts(n, pat):
    subj = 'a' * n
    cp = PatternCompiler.compile(pat)
    t0 = time.perf_counter()
    res = cp.matching_starts(subj)
    dt = time.perf_counter() - t0
    return dt, len(list(res)) if hasattr(res, '__len__') or hasattr(res, '__iter__') else res


for pat in ['*a', 'a*']:
    d4, n4 = t_starts(4000, pat)
    d8, n8 = t_starts(8000, pat)
    ratio = d8 / d4 if d4 > 0 else float('inf')
    print("pattern %-4r N=4000: %.5fs (%d starts)  N=8000: %.5fs (%d starts)  ratio %.2f"
          % (pat, d4, n4, d8, n8, ratio))
    print("   t8000 < 0.5s:", d8 < 0.5, "| ratio < 3 (linear-ish):", ratio < 3)

# full_match('**(a)b') cubic->quadratic claim spot cell at N=800 (base 36.2s, tip 0.011s)
cp = PatternCompiler.compile('**(a)b')
subj = 'a' * 800
t0 = time.perf_counter()
r = cp.full_match(subj, STRING)
dt = time.perf_counter() - t0
print("full_match('**(a)b') N=800: %.4fs result=%s  (< 2s vs base 36.2s):" % (dt, r), dt < 2)
