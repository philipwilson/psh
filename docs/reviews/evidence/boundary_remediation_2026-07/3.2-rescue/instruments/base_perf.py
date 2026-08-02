#!/usr/bin/env python3
"""A1 — fresh perf baselines at the slot base (da037aa8 / v0.763.0).

Run ONLY as:
    cd <worktree>/tmp/slot32 && PYTHONPATH=<worktree> python3 base_perf.py

Discriminator: aborts unless the imported psh is the one under PSH_ROOT.
Timing basis (D-2a): in-process operation timings, compile OUTSIDE the timer,
one warmup call per row family before the timed series, steady-state reported.
"""
import os
import sys
import time

PSH_ROOT = os.environ.get('PSH_ROOT', '/Users/pwilson/src/psh-r3-2')

import psh  # noqa: E402
import psh.expansion.pattern_engine as pe  # noqa: E402

# --- import discriminator (hard abort) --------------------------------------
for mod, name in ((psh, 'psh'), (pe, 'pattern_engine')):
    f = os.path.realpath(mod.__file__)
    if not f.startswith(os.path.realpath(PSH_ROOT) + os.sep):
        sys.exit(f"DISCRIMINATOR FAIL: {name} imported from {f}, not {PSH_ROOT}")
print(f"# discriminator OK: psh={psh.__file__}")
print(f"# version={psh.version.__version__}  cwd={os.getcwd()}")
print(f"# python={sys.version.split()[0]}")

C = pe.PatternCompiler.compile
STRING = pe.STRING

BUDGET = float(os.environ.get('BUDGET', '20.0'))  # per-row wall budget (s)


def timed(fn, *a, **kw):
    t0 = time.perf_counter()
    r = fn(*a, **kw)
    return time.perf_counter() - t0, r


def series(label, make_subject, run, sizes, budget=None):
    """Run `run(compiled_or_None, subject)` over sizes; stop past budget."""
    budget = BUDGET if budget is None else budget
    print(f"\n## {label}")
    print(f"{'N':>7} {'seconds':>12} {'ratio':>8}")
    prev = None
    rows = []
    for n in sizes:
        subj = make_subject(n)
        dt, _ = timed(run, subj)
        ratio = (dt / prev) if (prev and prev > 0) else float('nan')
        print(f"{n:>7} {dt:>12.4f} {ratio:>8.2f}")
        rows.append((n, dt))
        prev = dt
        if dt > budget:
            print(f"        (stopped: exceeded {budget}s budget)")
            break
    return rows


def bench_relation(pattern, relation, label, sizes, subject_char='a',
                   extglob=True, budget=None):
    cp = C(pattern, extglob=extglob)
    # warmup (small, same code path)
    getattr(cp, relation)('a' * 8, **({} if relation != 'matching_ends' else {}))

    def run(subj):
        return getattr(cp, relation)(subj)

    return series(f"{label}: {relation} pattern={pattern!r} subject={subject_char!r}*N",
                  lambda n: subject_char * n, run, sizes, budget)


print("\n" + "=" * 70)
print("A1-a  matching_starts quadratic (A9 handoff baseline)")
print("=" * 70)
bench_relation('*b', 'matching_starts', 'A9', [500, 1000, 2000, 4000, 8000])

print("\n" + "=" * 70)
print("A1-b  full_match on quirk patterns  (OPENER PRIORITY, E-1)")
print("=" * 70)
bench_relation('**(a)b', 'full_match', 'E-1 opener', [50, 100, 200, 400, 800])

print("\n" + "=" * 70)
print("A1-c  matching_ends '*!(a)'  (E-1: ~17x base at N=200)")
print("=" * 70)
bench_relation('*!(a)', 'matching_ends', 'E-1', [50, 100, 200, 400, 800])

print("\n" + "=" * 70)
print("A1-d  quirk-flag census for the shapes above")
print("=" * 70)
for p in ('*b', '**(a)b', '*!(a)', '+([[:space:]])', '*([[:space:]])',
          '!(x)', '*+([[:space:]])', '*+([[:space:]])*'):
    root = C(p).root
    print(f"  {p!r:22} bash_quirk={pe._seq_bash_quirk(root)!s:5} "
          f"has_extglob={pe._seq_has_extglob(root)!s:5} "
          f"sub_fast_eligible={pe.sub_fast_eligible(root)}")
