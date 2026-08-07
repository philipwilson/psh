"""Integrator verification of D2's NEW-1 and the CERT-ROW sharpening (C.3).

NEW-1: on a `read -t` timeout mid-multibyte, does bash ASSIGN the stranded
partial bytes while psh holds them for the next read?
C.3: psh `read -t 1 -N 3` with a producer that reaches EOF returns rc=1 at
the producer's exit (not an unbounded hang) — the hang is no-EOF only.
"""
import os
import subprocess
import sys
import time

WORKTREE = '/Users/pwilson/src/psh-r4b-2'
sys.path.insert(0, WORKTREE)
import psh  # noqa: E402
print("DISCRIMINATOR:", psh.__file__)

BASH = '/opt/homebrew/bin/bash'
PSH = [sys.executable, '-m', 'psh']

script = ('read -t 1 v; rc=$?; printf "rc=%s len=%s bytes=" "$rc" "${#v}"; '
          'printf "%s" "$v" | od -An -tx1 | tr -d " \\n"; echo')

def timeout_mid_multibyte(argv):
    r, w = os.pipe()
    p = subprocess.Popen(argv + ['-c', script], stdin=r,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         cwd=WORKTREE, env=dict(os.environ, PYTHONPATH=WORKTREE))
    os.close(r)
    os.write(w, b'\xc3')          # first byte of é; keep the pipe OPEN
    try:
        out, _ = p.communicate(timeout=6)
        return out.decode(errors='replace').strip()
    except subprocess.TimeoutExpired:
        p.kill(); p.communicate()
        return 'HUNG'
    finally:
        try:
            os.close(w)
        except OSError:
            pass

print("NEW-1 bash :", timeout_mid_multibyte([BASH]))
print("NEW-1 psh  :", timeout_mid_multibyte(PSH))

def eof_bounded(argv):
    r, w = os.pipe()
    p = subprocess.Popen(argv + ['-c', 'read -t 1 -N 3 v; echo "rc=$? v=<$v>"'],
                         stdin=r, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, cwd=WORKTREE,
                         env=dict(os.environ, PYTHONPATH=WORKTREE))
    os.close(r)
    os.write(w, b'ab')            # 2 of 3 chars
    t0 = time.monotonic()
    time.sleep(2.0)               # well past the 1s deadline
    os.close(w)                   # EOF at t=2s
    try:
        out, _ = p.communicate(timeout=6)
        dt = time.monotonic() - t0
        return f"dt={dt:.1f}s {out.decode(errors='replace').strip()}"
    except subprocess.TimeoutExpired:
        p.kill(); p.communicate()
        return 'HUNG'

print("C.3 psh  -N with EOF at 2s:", eof_bounded(PSH))
print("C.3 bash -N with EOF at 2s:", eof_bounded([BASH]))
