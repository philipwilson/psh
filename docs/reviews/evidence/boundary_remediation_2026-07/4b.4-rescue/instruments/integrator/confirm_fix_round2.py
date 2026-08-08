"""Re-run the verifier's rows + chained dup at fix tip 3f602cae."""
import os, subprocess, sys
BASE = '/Users/pwilson/src/psh-verify-4b4-base'
TIP = '/Users/pwilson/src/psh-verify-4b4-final'
BASH = ['/opt/homebrew/bin/bash']
PSH = [sys.executable, '-m', 'psh']

def run(argv, script, feed, cwd):
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
           'PYTHONPATH': cwd, 'TERM': 'dumb', 'LC_ALL': 'C'}
    p = subprocess.run(argv + ['-c', script], input=feed,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       cwd=cwd, env=env, timeout=10)
    return p.stdout.decode('utf-8', errors='backslashreplace').strip()

rows = [
    ("R1 true 3<&0", 'read -N 1 a; true 3<&0; read -N 1 b; printf "%s|%s\\n" "$a" "$b"'),
    ("N4 move 3<&0-", 'read -N 1 a; true 3<&0-; read -N 1 b; printf "%s|%s\\n" "$a" "$b"'),
    ("P1 {v}<&0", 'read -N 1 a; read -N 1 b {v}<&0; read -N 1 c; printf "%s|%s|%s\\n" "$a" "$b" "$c"'),
    ("N9 dup-then-dup", 'exec 3<&0; read -N 1 a; true 4<&3; read -N 1 -u 3 b; printf "%s|%s\\n" "$a" "$b"'),
    ("X8 compound { } 3<&0", 'read -N 1 a; { true; } 3<&0; read -N 1 b; printf "%s|%s\\n" "$a" "$b"'),
    ("chained {v}<&3", 'exec 3<&0; read -N 1 -u 3 a; true {v}<&3; read -N 1 -u 3 b; printf "%s|%s\\n" "$a" "$b"'),
]
feed = b'\xc3ABCD\n'
for name, script in rows:
    b = run(BASH, script, feed, BASE)
    pb = run(PSH, script, feed, BASE)
    pt = run(PSH, script, feed, TIP)
    verdict = "TIP==BASH" if pt == b else ("TIP==BASE(pre-existing)" if pt == pb else "TIP DIVERGES BOTH")
    print(f"{name:22s} bash={b:14s} base={pb:14s} tip={pt:14s} {verdict}")
