#!/usr/bin/env python3
"""A1 (cont) — substitution baselines at base: D-2 shapes + INELIGIBLE class.

Basis = 3.1 D-2a: in-process operation timing, ONE persistent Shell, subject
preset in shell state, time.perf_counter() around sh.run_command(op).

Subject shapes (the 3.1 construction was NOT committed; these are MINE and
are the denominators for this slot's own delta table):
  consecutive : ' ' * N                       (one long whitespace run)
  word_spaced : 'x ' * N                      (N words, N separators)

Run: cd <worktree>/tmp/slot32 && PSH_ROOT=<wt> PYTHONPATH=<wt> python3 base_sub_perf.py
"""
import os
import subprocess
import sys
import time

PSH_ROOT = os.environ.get('PSH_ROOT', '/Users/pwilson/src/psh-r3-2')
BUDGET = float(os.environ.get('BUDGET', '25.0'))
BASH = '/opt/homebrew/bin/bash'

import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402
from psh.shell import Shell  # noqa: E402

for mod, name in ((psh, 'psh'), (pe, 'pattern_engine')):
    f = os.path.realpath(mod.__file__)
    if not f.startswith(os.path.realpath(PSH_ROOT) + os.sep):
        sys.exit(f"DISCRIMINATOR FAIL: {name} from {f}")
print(f"# discriminator OK: {psh.__file__}  version={psh.version.__version__}")
bv = subprocess.run([BASH, '--version'], capture_output=True, text=True).stdout.split('\n')[0]
print(f"# bash oracle: {BASH} -> {bv}")

SHAPES = {
    'consecutive': lambda n: ' ' * n,
    'word_spaced': lambda n: 'x ' * n,
}

# (label, pattern, expected fast_ok class)
PATTERNS = [
    ('ELIGIBLE  +([[:space:]])', '+([[:space:]])'),
    ('INELIG-nullable *([[:space:]])', '*([[:space:]])'),
    ('INELIG-negation !(x)', '!(x)'),
    ('INELIG-nullalt @(x|)', '@(x|)'),
]

sh = Shell()
sh.run_command('shopt -s extglob')


def set_v(val):
    sh.state.set_variable('v', val)


def psh_time(op, subject):
    set_v(subject)
    t0 = time.perf_counter()
    sh.run_command(op)
    return time.perf_counter() - t0


def psh_result(op, subject):
    set_v(subject)
    sh.run_command(op)
    return sh.state.get_variable('r')


def bash_result(op, subject):
    script = 'shopt -s extglob\nv=$1\n' + op + '\nprintf %s "$r"'
    p = subprocess.run([BASH, '--norc', '--noprofile', '-c', script, 'x', subject],
                       capture_output=True, text=True, timeout=60)
    return p.stdout


# --- fast_ok / quirk census for every (pattern, anchor) we time -------------
print("\n" + "=" * 78)
print("A1-e  dispatch census: fast_ok + wrapper quirk per pattern (anchor 'any')")
print("=" * 78)
from psh.expansion.parameter_expansion import _sub_machinery_cached  # noqa: E402
for label, pat in PATTERNS:
    compiled, wrapped, end_elig, fast_ok = _sub_machinery_cached(pat, 'any', True)
    print(f"  {label:34} fast_ok={fast_ok!s:5} "
          f"pat_quirk={pe._seq_bash_quirk(compiled.root)!s:5} "
          f"wrapper_quirk={pe._seq_bash_quirk(wrapped.root)!s:5} "
          f"end_eligible={end_elig}")

# --- semantic sanity vs live bash at small N (pre-change lock) --------------
print("\n" + "=" * 78)
print("A1-f  semantic cross-check vs live bash 5.2.26 (small N, before any edit)")
print("=" * 78)
mismatch = 0
for shape_name, mk in SHAPES.items():
    for label, pat in PATTERNS:
        for n in (0, 1, 2, 3, 7):
            subj = mk(n)
            op = 'r=${v//' + pat + '/-}'
            got = psh_result(op, subj)
            want = bash_result(op, subj)
            if got != want:
                mismatch += 1
                print(f"  MISMATCH {shape_name} n={n} {pat!r}: psh={got!r} bash={want!r}")
print(f"  cross-check cells={len(SHAPES)*len(PATTERNS)*5}  mismatches={mismatch}")

# --- timing table ----------------------------------------------------------
print("\n" + "=" * 78)
print("A1-g  ${v//pat/-} in-process op timing at base (D-2a basis)")
print("=" * 78)
print(f"{'pattern':34} {'shape':12} {'N':>6} {'seconds':>11} {'ratio':>7}")
for label, pat in PATTERNS:
    op = 'r=${v//' + pat + '/-}'
    for shape_name, mk in SHAPES.items():
        psh_time(op, mk(4))  # warmup this (pattern, shape) row family
        prev = None
        for n in (400, 800, 1600, 3200):
            dt = psh_time(op, mk(n))
            ratio = (dt / prev) if (prev and prev > 0) else float('nan')
            print(f"{label:34} {shape_name:12} {n:>6} {dt:>11.4f} {ratio:>7.2f}")
            prev = dt
            if dt > BUDGET:
                print(f"{'':34} {'':12} {'':>6}  (stopped: >{BUDGET}s)")
                break

# --- removal-operator baselines on the same classes ------------------------
print("\n" + "=" * 78)
print("A1-h  removal operators (no consumer layer) on quirk patterns")
print("=" * 78)
print(f"{'op':34} {'N':>6} {'seconds':>11} {'ratio':>7}")
for op, mk in (('r=${v%%*!(a)}', lambda n: 'a' * n),
               ('r=${v##*!(a)}', lambda n: 'a' * n),
               ('r=${v%%*+(a)}', lambda n: 'a' * n)):
    psh_time(op, mk(4))
    prev = None
    for n in (100, 200, 400, 800):
        dt = psh_time(op, mk(n))
        ratio = (dt / prev) if (prev and prev > 0) else float('nan')
        print(f"{op:34} {n:>6} {dt:>11.4f} {ratio:>7.2f}")
        prev = dt
        if dt > BUDGET:
            print(f"{'':34} {'':>6}  (stopped: >{BUDGET}s)")
            break
