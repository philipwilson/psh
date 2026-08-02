"""RAW-PAIR base-vs-tip sweep (B1(d) instrument fix).

The round-1 instrument compared VERDICT TAGS (DIFF/SAME per cell against bash).
A cell that was DIFF at base and DIFF at tip passed through it unnoticed even
when its CONTENT changed completely — which is exactly how the redirect-target
consumer's base->tip change escaped, and why B1/B6 bounced.

This instrument compares the RAW OUTPUT PAIR (stdout, rc) of base vs tip for
every cell, so ANY behavior change is visible regardless of what either side
does relative to bash. It also records bash, so each changed cell can be
classified immediately as toward-bash / away-from-bash / neither.

Usage: python rawsweep.py > rawsweep.txt
"""
import os
import subprocess
import sys

import batch
from harness import BASH, bash_version

BASE = '/Users/pwilson/src/psh-r3-3-base'
TIP = '/Users/pwilson/src/psh-r3-3'


def _env(root):
    e = {k: v for k, v in os.environ.items()
         if k in ('HOME', 'PATH', 'USER', 'LANG', 'TERM')}
    e['PYTHONPATH'] = root
    e['PSH_STRICT_ERRORS'] = '1'
    return e


def _discriminate(root):
    r = subprocess.run([sys.executable, '-c', 'import psh; print(psh.__file__)'],
                       cwd=root, capture_output=True, text=True, env=_env(root))
    got = r.stdout.strip()
    want = os.path.join(root, 'psh', '__init__.py')
    if got != want:
        raise SystemExit(f"DISCRIMINATOR FAILED for {root}: {got!r}")
    return got


def _sha(root):
    return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root,
                          capture_output=True, text=True).stdout.strip()


def run_tree(root, script):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script], cwd=root,
                          capture_output=True, text=True, timeout=120,
                          env=_env(root)).stdout


def run_bash_script(script):
    return subprocess.run([BASH, '-c', script], cwd=TIP, capture_output=True,
                          text=True, timeout=120, env=_env(TIP)).stdout


def all_cells():
    """Every cell from every matrix module, de-duplicated by id."""
    import m_axes
    import m_core
    import m_ctx
    import m_h6
    import m_proj
    groups = [
        ('A', m_core.cells()), ('B', m_axes.b_cells()), ('C', m_axes.c_cells()),
        ('D', m_axes.d_cells()), ('E', m_axes.e_cells()), ('F', m_axes.f_cells()),
        ('G', m_ctx.g_cells()), ('H', m_ctx.h_cells()), ('I', m_ctx.i_cells()),
        ('J', m_ctx.j_cells()), ('K', m_ctx.K_CELLS), ('L', m_proj.cells()),
        ('H6', m_h6.cells()),
    ]
    seen = {}
    order = []
    for _, cells in groups:
        for cid, body in cells:
            if cid not in seen:
                seen[cid] = body
                order.append(cid)
    return [(cid, seen[cid]) for cid in order]


def sweep(cells, chunk=120):
    """Return {cell_id: (bash, base, tip)} of raw (output, rc) pairs."""
    out = {}
    for i in range(0, len(cells), chunk):
        part = cells[i:i + chunk]
        script = batch.build_script(part)
        b = batch.parse(run_bash_script(script))
        base = batch.parse(run_tree(BASE, script))
        tip = batch.parse(run_tree(TIP, script))
        for cid, _ in part:
            out[cid] = (b.get(cid), base.get(cid), tip.get(cid))
    return out


def main():
    print("RAW-PAIR BASE-vs-TIP SWEEP (B1(d) corrected instrument)")
    print(f"  base : {BASE}  @ {_sha(BASE)}  import={_discriminate(BASE)}")
    print(f"  tip  : {TIP}  @ {_sha(TIP)}  import={_discriminate(TIP)}")
    print(f"  bash : {BASH} — {bash_version()}")
    dirty = subprocess.run(['git', 'status', '--porcelain', '--', 'psh'],
                           cwd=TIP, capture_output=True, text=True).stdout.strip()
    print(f"  tip psh/ dirty: {bool(dirty)}")
    cells = all_cells()
    print(f"  cells: {len(cells)} distinct ids\n")

    res = sweep(cells)
    changed = [(cid, v) for cid, v in res.items() if v[1] != v[2]]
    print(f"CELLS WHOSE BEHAVIOR CHANGED base -> tip: {len(changed)}\n")
    toward = away = neither = 0
    for cid, (b, base, tip) in sorted(changed):
        cls = ('toward-bash' if tip == b else
               'away-from-bash' if base == b else 'neither-matches-bash')
        toward += cls == 'toward-bash'
        away += cls == 'away-from-bash'
        neither += cls == 'neither-matches-bash'
        print(f"[{cls}] {cid}")
        print(f"    bash: {b}")
        print(f"    base: {base}")
        print(f"    tip : {tip}")
    print(f"\nsummary: {len(changed)} changed — toward-bash {toward}, "
          f"away-from-bash {away}, neither {neither}")
    print(f"unchanged: {len(res) - len(changed)}")


if __name__ == '__main__':
    main()
