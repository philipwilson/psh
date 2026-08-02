"""Slot 3.3 probe harness: operand field-IR matrix, psh vs live bash 5.2.26.

Every run records the psh tree actually imported (PSH_ROOT discriminator) and
the bash binary + version, so a transcript proves WHICH trees produced it.
Usage:  python tmp/probes-3-3/harness.py <matrix-module> [--out FILE]
"""
import os
import subprocess
import sys

PSH_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
BASH = '/opt/homebrew/bin/bash'


def _discriminate():
    """Prove which psh tree `python -m psh` will import from PSH_ROOT."""
    r = subprocess.run(
        [sys.executable, '-c', 'import psh; print(psh.__file__)'],
        cwd=PSH_ROOT, capture_output=True, text=True,
        env={**os.environ, 'PYTHONPATH': PSH_ROOT})
    got = r.stdout.strip()
    want = os.path.join(PSH_ROOT, 'psh', '__init__.py')
    if got != want:
        raise SystemExit(f"DISCRIMINATOR FAILED: imported {got!r}, want {want!r}")
    return got


def bash_version():
    r = subprocess.run([BASH, '--version'], capture_output=True, text=True)
    return r.stdout.splitlines()[0]


def _env():
    e = {k: v for k, v in os.environ.items()
         if k in ('HOME', 'PATH', 'USER', 'LANG', 'TERM')}
    e['PYTHONPATH'] = PSH_ROOT
    e.setdefault('PATH', '/opt/homebrew/bin:/usr/bin:/bin')
    return e


def run_bash(script, extra_env=None):
    env = _env()
    if extra_env:
        env.update(extra_env)
    return subprocess.run([BASH, '-c', script], cwd=PSH_ROOT,
                          capture_output=True, text=True, timeout=30, env=env)


def run_psh(script, extra_env=None, parser=None):
    env = _env()
    env['PSH_STRICT_ERRORS'] = '1'
    if extra_env:
        env.update(extra_env)
    argv = [sys.executable, '-m', 'psh']
    if parser:
        argv += ['--parser', parser]
    argv += ['-c', script]
    return subprocess.run(argv, cwd=PSH_ROOT, capture_output=True,
                          text=True, timeout=60, env=env)


def _fmt(r):
    return f"out={r.stdout!r} err={r.stderr.strip()!r} rc={r.returncode}"


def compare(cells, title, out=sys.stdout, extra_env=None, parser=None):
    """cells: list of (id, script). Prints a both-sides table; returns rows."""
    rows = []
    print(f"\n=== {title} ===", file=out)
    for cid, script in cells:
        b = run_bash(script, extra_env)
        p = run_psh(script, extra_env, parser)
        same = (b.stdout == p.stdout and b.returncode == p.returncode)
        rows.append((cid, script, b, p, same))
        mark = 'SAME' if same else 'DIFF'
        print(f"[{mark}] {cid}: {script}", file=out)
        print(f"    bash: {_fmt(b)}", file=out)
        print(f"    psh : {_fmt(p)}", file=out)
    n_diff = sum(1 for r in rows if not r[4])
    print(f"--- {title}: {len(rows)} cells, {n_diff} DIFF, "
          f"{len(rows) - n_diff} SAME ---", file=out)
    return rows


def header(out=sys.stdout, tree_note=''):
    print(f"PSH_ROOT   : {PSH_ROOT}", file=out)
    print(f"psh import : {_discriminate()}", file=out)
    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=PSH_ROOT,
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', '--', 'psh'],
                           cwd=PSH_ROOT, capture_output=True,
                           text=True).stdout.strip()
    print(f"psh SHA    : {sha}  (psh/ dirty: {bool(dirty)})", file=out)
    print(f"bash       : {BASH} — {bash_version()}", file=out)
    if tree_note:
        print(f"tree note  : {tree_note}", file=out)
