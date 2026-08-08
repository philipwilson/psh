"""Integrator verification of D2's load-bearing claims (rulings c1/c2/P5/P6/b1/P7)."""
import os, subprocess, sys, tempfile
REPO = '/Users/pwilson/src/psh'
sys.path.insert(0, REPO)
import psh
assert psh.__file__ == REPO + '/psh/__init__.py', psh.__file__
print("DISCRIMINATOR:", psh.__file__)
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']

def run(argv, script, hf, extra=None):
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
           'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO}
    if extra: env.update(extra)
    p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, cwd=REPO, env=env, timeout=20)
    return p.stdout.decode(errors='replace')

def hist_lines(out):
    return [ln.strip().split('  ')[-1] for ln in out.splitlines()
            if ln.strip()[:1].isdigit()]

with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    # C1a: -s under ignoredups (invocations HISTIGNOREd away)
    for lab, argv in (('bash', BASH), ('psh ', PSH)):
        hf = os.path.join(d, 'c1a' + lab.strip()); open(hf, 'w').close()
        out = run(argv, 'history -s dup\nhistory -s dup\nhistory\nexit\n', hf,
                  {'HISTCONTROL': 'ignoredups', 'HISTIGNORE': 'history *:history'})
        print(f"C1a -s ignoredups {lab}: {hist_lines(out)}")
    # C1b: HISTIGNORE matched against STORED text
    for lab, argv in (('bash', BASH), ('psh ', PSH)):
        hf = os.path.join(d, 'c1b' + lab.strip()); open(hf, 'w').close()
        out = run(argv, 'history -s secret123\nhistory\nexit\n', hf,
                  {'HISTIGNORE': 'secret*:history *:history'})
        print(f"C1b -s HISTIGNORE-stored {lab}: {hist_lines(out)}")
    # C2: -r cap bypass at HISTSIZE=4 (10-line file)
    for lab, argv in (('bash', BASH), ('psh ', PSH)):
        hf = os.path.join(d, 'c2' + lab.strip())
        with open(hf, 'w') as f: f.write(''.join(f'r{i}\n' for i in range(1, 11)))
        out = run(argv, 'history -r\nhistory\nexit\n', hf,
                  {'HISTSIZE': '4', 'HISTIGNORE': 'history *:history'})
        print(f"C2 -r HISTSIZE=4 {lab}: {len(hist_lines(out))} entries: {hist_lines(out)}")
    # P5: -w NAMED then exit -> does newcmd reach $HISTFILE?
    for lab, argv in (('bash', BASH), ('psh ', PSH)):
        hf = os.path.join(d, 'p5' + lab.strip()); open(hf, 'w').close()
        other = os.path.join(d, 'p5other' + lab.strip())
        out = run(argv, f'echo newcmd-{lab.strip()}\nhistory -w {other}\nexit\n', hf)
        saved = open(hf).read()
        print(f"P5 -w NAMED exit {lab}: newcmd in $HISTFILE = {('newcmd-' + lab.strip()) in saved}")
    # P6: -r NAMED then -a -> does leakline reach $HISTFILE?
    for lab, argv in (('bash', BASH), ('psh ', PSH)):
        hf = os.path.join(d, 'p6' + lab.strip()); open(hf, 'w').close()
        other = os.path.join(d, 'p6other' + lab.strip())
        with open(other, 'w') as f: f.write('leakline\n')
        run(argv, f'history -r {other}\nhistory -a\nexit\n', hf)
        print(f"P6 -r NAMED leak {lab}: leakline in $HISTFILE = {'leakline' in open(hf).read()}")
    # B1: external append x2; -n; -a -> duplicate x2 in file?
    for lab, argv in (('bash', BASH), ('psh ', PSH)):
        hf = os.path.join(d, 'b1' + lab.strip())
        with open(hf, 'w') as f: f.write('x1\n')
        run(argv, f'echo ext-x2 >> {hf}\nhistory -n\nhistory -a\nexit\n', hf)
        n = open(hf).read().count('ext-x2')
        print(f"B1 -n then -a {lab}: 'ext-x2' occurrences in file = {n}")
    # P7: separate words -p -s hello
    for lab, argv in (('bash', BASH), ('psh ', PSH)):
        hf = os.path.join(d, 'p7' + lab.strip()); open(hf, 'w').close()
        out = run(argv, 'history -p -s hello\necho rc=$?\nhistory\nexit\n', hf)
        printed = [ln for ln in out.splitlines()
                   if ln.strip() and not ln.strip()[:1].isdigit() and 'rc=' not in ln]
        rc = [ln for ln in out.splitlines() if ln.startswith('rc=')]
        print(f"P7 '-p -s hello' {lab}: rc={rc} printed={printed} listing={hist_lines(out)}")
