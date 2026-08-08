"""Verify D3's sharpest A1' cell: K=4 typed, -r 2 lines -> bash -a writes a MIX
[t3, t4, Q1, Q2] (positional tail N=4), losing t1/t2 and leaking Q1/Q2.
History invocations HISTIGNOREd away (dev's convention: K counts seed commands)."""
import os, subprocess, sys, tempfile
REPO = '/Users/pwilson/src/psh'
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']
with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    for lab, argv in (('bash', BASH), ('psh ', PSH)):
        hf = os.path.join(d, 'hf' + lab.strip()); open(hf, 'w').close()
        q = os.path.join(d, 'q' + lab.strip())
        with open(q, 'w') as f: f.write('Q1\nQ2\n')
        script = ('echo t1\necho t2\necho t3\necho t4\n'
                  f'history -r {q}\nhistory -a\n'
                  f'echo ===MARK===\ncat {hf}\necho ===END===\nexit\n')
        env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
               'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO,
               'HISTIGNORE': 'history *'}
        p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, cwd=REPO, env=env, timeout=20)
        out = p.stdout.decode(errors='replace')
        mid = out.split('===MARK===')[1].split('===END===')[0] if '===MARK===' in out else '??'
        print(f"MIX {lab}: -a wrote = {[ln for ln in mid.splitlines() if ln.strip()]}")
