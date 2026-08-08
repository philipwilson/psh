"""Integrator confirmation of verify-round-2 BL-1 (R1 row) and BL-2 (P1 row)."""
import os, subprocess, sys
BASE = '/Users/pwilson/src/psh-verify-4b4-base'   # e3924ed3
TIP = '/Users/pwilson/src/psh-verify-4b4-tip'     # 2f355fc3
BASH = ['/opt/homebrew/bin/bash']

def run(argv, script, feed, cwd):
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
           'PYTHONPATH': cwd, 'TERM': 'dumb', 'LC_ALL': 'C'}
    p = subprocess.run(argv + ['-c', script], input=feed,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       cwd=cwd, env=env, timeout=10)
    return p.stdout.decode('utf-8', errors='backslashreplace').strip()

PSH = [sys.executable, '-m', 'psh']
r1 = 'read -N 1 a; true 3<&0; read -N 1 b; printf "a=<%s> b=<%s>\\n" "$a" "$b"'
p1 = ('read -N 1 a; read -N 1 b {v}<&0; read -N 1 c; '
      'printf "a=<%s> b=<%s> c=<%s>\\n" "$a" "$b" "$c"')
feed = b'\xc3ABCD\n'
print("=== BL-1 R1 row: read; true 3<&0; read ===")
print("bash-C:", run(BASH, r1, feed, BASE))
print("base  :", run(PSH, r1, feed, BASE))
print("tip   :", run(PSH, r1, feed, TIP))
print("=== BL-2 P1 row: {v}<&0 named-fd between reads ===")
print("bash-C:", run(BASH, p1, feed, BASE))
print("base  :", run(PSH, p1, feed, BASE))
print("tip   :", run(PSH, p1, feed, TIP))
