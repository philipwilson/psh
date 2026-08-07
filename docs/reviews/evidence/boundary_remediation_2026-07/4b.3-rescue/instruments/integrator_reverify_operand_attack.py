"""Integrator re-verify: attack the operand-sensitive suppression rule with
compositions NOT in the pin suite: -ca FILE, -cn FILE, -wd 1, -cs x, -cd 1 FILE."""
import os, subprocess, sys, tempfile
BASE = '/Users/pwilson/src/psh'
TIP = '/Users/pwilson/src/psh-verify-4b3-final'
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']

def run(argv, script, hf, cwd):
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
           'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': cwd,
           'HISTIGNORE': 'history*:exit'}
    p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, cwd=cwd, env=env, timeout=20)
    return p.stdout.decode(errors='replace')

def mem(out):
    return [l.strip().split('  ')[-1] for l in out.splitlines() if l.strip()[:1].isdigit()]

with tempfile.TemporaryDirectory(dir=BASE + '/tmp') as d:
    cells = []
    # -ca FILE: -c with operand -> does -a run? (writes typed cmds to FILE)
    cells.append(('-ca FILE', 'echo t1\nhistory -ca {F}\necho ===M===\ncat {F}\necho ===E===\nhistory\nexit\n'))
    # -cn FILE: -c with operand -> does -n run? (reads FILE into memory)
    cells.append(('-cn FILE', 'history -cn {F}\nhistory\nexit\n'))
    # -wd 1: -d present -> -w suppressed? (file should stay seeded-only in bash)
    cells.append(('-wd 1  ', 'echo t1\nhistory -wd 1\necho ===M===\ncat $HISTFILE\necho ===E===\nhistory\nexit\n'))
    # -cs x: -s vs -c composition
    cells.append(('-cs x  ', 'echo t1\nhistory -cs XX\nhistory\nexit\n'))
    for name, tmpl in cells:
        row = []
        for lab, argv, cwd in (('bash', BASH, BASE), ('tip', PSH, TIP)):
            hf = os.path.join(d, name.strip().replace(' ', '_') + lab)
            with open(hf, 'w') as f: f.write('S1\n')
            other = hf + '.oth'
            with open(other, 'w') as f: f.write('O1\n')
            out = run(argv, tmpl.format(F=other), hf, cwd)
            filepart = out.split('===M===')[1].split('===E===')[0].split() if '===M===' in out else None
            row.append(f"{lab}: mem={mem(out)}" + (f" file={filepart}" if filepart is not None else ""))
        print(f"{name}: " + " | ".join(row))
