#!/usr/bin/env python3
"""B1/B2 reproduction — run at a DETACHED checkout (R4 binding rule).

Measures the eligible fast-path CONTROLS the brief names as must-not-regress,
plus the spanner-construction cost that R4 identifies as the mechanism.

  PSH_ROOT=<detached-wt> PYTHONPATH=<detached-wt> python3 b1_repro.py
"""
import os
import subprocess
import sys
import time

PSH_ROOT = os.environ['PSH_ROOT']
import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402
from psh.shell import Shell  # noqa: E402

real = os.path.realpath(PSH_ROOT) + os.sep
for m, n in ((psh, 'psh'), (pe, 'pattern_engine')):
    if not os.path.realpath(m.__file__).startswith(real):
        sys.exit(f"DISCRIMINATOR FAIL: {n} from {m.__file__}")
sha = subprocess.run(['git', '-C', PSH_ROOT, 'rev-parse', 'HEAD'],
                     capture_output=True, text=True).stdout.strip()
print(f"# tree={PSH_ROOT}")
print(f"# HEAD={sha}")
print(f"# psh={psh.__file__}")

sh = Shell()
sh.run_command('shopt -s extglob')

ROWS = [
    ('+([[:space:]])', 'consecutive', lambda n: ' ' * n),      # eligible ctrl
    ('+([[:space:]])', 'word_spaced', lambda n: 'x ' * n),     # eligible ctrl
    ('+(a)', 'a-run', lambda n: 'a' * n),                      # R4: 1578x
    ('!(x)', 'x-run', lambda n: 'x' * n),                      # R4: 1159x
    ('*([[:space:]])', 'consecutive', lambda n: ' ' * n),      # inelig nullable
    ('*([[:space:]])', 'word_spaced', lambda n: 'x ' * n),
]

print(f"\n{'pattern':18} {'shape':12} " +
      ' '.join(f'{n:>9}' for n in (400, 800, 1600, 3200)) + '   ratios')
for pat, shape, mk in ROWS:
    op = 'r=${v//' + pat + '/-}'
    sh.state.set_variable('v', mk(4))
    sh.run_command(op)                       # warm this row family
    vals = []
    for n in (400, 800, 1600, 3200):
        sh.state.set_variable('v', mk(n))
        t0 = time.perf_counter()
        sh.run_command(op)
        vals.append(time.perf_counter() - t0)
        if vals[-1] > 25:
            break
    ratios = ' '.join(f'{vals[i+1]/vals[i]:.2f}' for i in range(len(vals) - 1))
    print(f"{pat:18} {shape:12} " +
          ' '.join(f'{v:>9.4f}' for v in vals) + f'   {ratios}')

# --- the mechanism R4 names: spanner CONSTRUCTION alone -------------------
print(f"\n{'spanner construction only':30} " +
      ' '.join(f'{n:>9}' for n in (400, 800, 1600)) + '   ratios')
for pat, shape, mk in (('+([[:space:]])', 'consecutive', lambda n: ' ' * n),
                       ('+(a)', 'a-run', lambda n: 'a' * n),
                       ('*b', 'a-run (no extglob)', lambda n: 'a' * n)):
    cp = pe.PatternCompiler.compile(pat, extglob=True)
    cp.spanner(mk(4), pe.STRING)
    vals = []
    for n in (400, 800, 1600):
        subj = mk(n)
        t0 = time.perf_counter()
        cp.spanner(subj, pe.STRING)
        vals.append(time.perf_counter() - t0)
    ratios = ' '.join(f'{vals[i+1]/vals[i]:.2f}' for i in range(len(vals) - 1))
    print(f"{pat + ' ' + shape:30} " +
          ' '.join(f'{v:>9.4f}' for v in vals) + f'   {ratios}')
