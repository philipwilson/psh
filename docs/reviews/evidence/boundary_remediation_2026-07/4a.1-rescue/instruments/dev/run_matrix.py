"""I-E: the Phase A probe driver — one fresh subprocess per cell.

    python run_matrix.py <instrument.py> <tree-under-test> [cell ...]

Launches EVERY cell of the named instrument in its own subprocess with
PYTHONPATH and cwd set to the tree under test, ASSERTS the discriminator
(the imported ``psh`` package must live under that tree — an editable
install otherwise silently imports the main checkout), captures the rows,
and DERIVES the tallies.  Nothing here is hand-counted.

Exit status is 0 when every cell ran to completion (a cell's RESULT is data,
not a verdict); non-zero when a cell crashed, timed out, or failed the
discriminator check.
"""
import os
import subprocess
import sys

TIMEOUT = 120


def run_cell(script, tree, cell):
    env = dict(os.environ)
    env['PYTHONPATH'] = tree
    env.pop('PSH_STRICT_ERRORS', None)      # probe the SHIPPED default path
    proc = subprocess.run([sys.executable, script, cell], cwd=tree, env=env,
                          capture_output=True, text=True, timeout=TIMEOUT)
    return proc


def main():
    script, tree = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    wanted = sys.argv[3:]
    listing = subprocess.run([sys.executable, script, '--list'], cwd=tree,
                             capture_output=True, text=True,
                             env=dict(os.environ, PYTHONPATH=tree))
    cells = [ln.strip() for ln in listing.stdout.splitlines()
             if ln.strip() and not ln.startswith('DISCRIM')]
    if wanted:
        cells = [c for c in cells if c in wanted]
    print(f"# instrument: {script}")
    print(f"# tree:       {tree}")
    print(f"# cells:      {len(cells)}")
    broken, results = [], {}
    for cell in cells:
        proc = run_cell(script, tree, cell)
        lines = proc.stdout.splitlines()
        discrim = [ln for ln in lines if ln.startswith('DISCRIM ')]
        if not discrim or not discrim[0].split(None, 1)[1].startswith(tree + os.sep):
            broken.append((cell, f"DISCRIMINATOR FAIL: {discrim or proc.stderr[-400:]}"))
            continue
        if proc.returncode != 0:
            broken.append((cell, f"exit {proc.returncode}: {proc.stderr[-400:]}"))
        res = [ln for ln in lines if ' RESULT=' in ln]
        results[cell] = res[-1].split('RESULT=', 1)[1] if res else 'NO-RESULT'
        print(f"\n--- {cell} ---")
        for ln in lines:
            if ln.startswith('CELL '):
                print(ln)
        if proc.returncode != 0:
            print(f"CELL {cell} KEY=stderr_tail VALUE={proc.stderr.strip()[-300:]!r}")

    print("\n=== DERIVED SUMMARY ===")
    for cell in cells:
        print(f"{cell:8s} {results.get(cell, 'DID-NOT-RUN')}")
    print(f"cells_requested={len(cells)} cells_with_result={len(results)} "
          f"broken={len(broken)}")
    for cell, why in broken:
        print(f"BROKEN {cell}: {why}")
    return 1 if broken else 0


if __name__ == '__main__':
    raise SystemExit(main())
