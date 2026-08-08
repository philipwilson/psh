"""Integrator confirmation of verify-round BL-1 / BL-2 / BL-3 headline cells."""
import os, subprocess, sys, tempfile
BASE = '/Users/pwilson/src/psh'            # = bd13b303 (base)
TIP = '/Users/pwilson/src/psh-verify-4b3-tip'  # = bc280e8f (detached)
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']

def run(argv, script, hf, cwd, extra=None):
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
           'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': cwd}
    if extra: env.update(extra)
    p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, cwd=cwd, env=env, timeout=20)
    return p.stdout.decode(errors='replace'), p.stderr.decode(errors='replace')

def psh(cwd): return [sys.executable, '-m', 'psh', '--norc', '-i']

with tempfile.TemporaryDirectory(dir=BASE + '/tmp') as d:
    # BL-1: seed 'true same'; type same text; history -d 2; exit -> file?
    print("=== BL-1: -d'd entry resurrected as duplicate ===")
    for lab, argv, cwd in (('bash', BASH, BASE), ('base', psh(BASE), BASE), ('tip ', psh(TIP), TIP)):
        hf = os.path.join(d, 'b1' + lab.strip()); 
        with open(hf, 'w') as f: f.write('true same\n')
        run(argv, 'true same\nhistory -d 2\nexit\n', hf, cwd,
            {'HISTIGNORE': 'history *:exit'})
        print(f"{lab}: file after exit = {open(hf).read().splitlines()}")
    # BL-2: history -wa stderr
    print("=== BL-2: -wa diagnostic ===")
    for lab, argv, cwd in (('bash', BASH, BASE), ('tip ', psh(TIP), TIP)):
        hf = os.path.join(d, 'b2' + lab.strip()); open(hf, 'w').close()
        out, err = run(argv, 'history -wa\necho rc=$?\nexit\n', hf, cwd)
        rc = [l for l in out.splitlines() if l.startswith('rc=')]
        msg = [l for l in err.splitlines() if 'history' in l]
        print(f"{lab}: rc={rc} stderr={msg[:2]}")
    # BL-3: -cw with seeded default file
    print("=== BL-3: -cw runs the file op ===")
    for lab, argv, cwd in (('bash', BASH, BASE), ('tip ', psh(TIP), TIP)):
        hf = os.path.join(d, 'b3' + lab.strip())
        with open(hf, 'w') as f: f.write('S1\nS2\n')
        out, _ = run(argv, f'history -cw\necho rc=$?\necho ===M===\ncat {hf}\necho ===E===\nunset HISTFILE\nexit\n', hf, cwd)
        mid = out.split('===M===')[1].split('===E===')[0] if '===M===' in out else '??'
        print(f"{lab}: file after -cw = {[l for l in mid.splitlines() if l.strip()]}")
