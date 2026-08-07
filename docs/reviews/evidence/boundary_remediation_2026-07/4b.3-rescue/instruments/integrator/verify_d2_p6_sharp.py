"""P6 sharpened: read $HISTFILE after -a but BEFORE exit-save (in-session cat)."""
import os, subprocess, sys, tempfile
REPO = '/Users/pwilson/src/psh'
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']
with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    for lab, argv in (('bash', BASH), ('psh ', PSH)):
        hf = os.path.join(d, 'hf' + lab.strip()); open(hf, 'w').close()
        other = os.path.join(d, 'other' + lab.strip())
        with open(other, 'w') as f: f.write('leakline\n')
        script = (f'history -r {other}\nhistory -a\n'
                  f'echo ===MARK===\ncat {hf}\necho ===END===\nexit\n')
        env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
               'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO}
        p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, cwd=REPO, env=env, timeout=20)
        out = p.stdout.decode(errors='replace')
        mid = out.split('===MARK===')[1].split('===END===')[0] if '===MARK===' in out else '??'
        print(f"P6 {lab}: $HISTFILE after -a, pre-exit = {mid.split()!r}")
