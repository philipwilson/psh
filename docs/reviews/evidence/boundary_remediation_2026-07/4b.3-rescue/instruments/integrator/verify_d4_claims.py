"""Verify D4's flipped-pin bash side (-w then -a duplication, named AND default)
and the rider's -cd suppression row."""
import os, subprocess, sys, tempfile
REPO = '/Users/pwilson/src/psh'
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']

def run_bash(script, hf, extra=None):
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
           'HISTFILE': hf, 'TERM': 'dumb'}
    if extra: env.update(extra)
    p = subprocess.run(BASH, input=script.encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, cwd=REPO, env=env, timeout=20)
    return p.stdout.decode(errors='replace'), p.stderr.decode(errors='replace')

with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    # 1a. -w NAMED then -a NAMED: duplicate in named file? (HISTIGNORE convention)
    hf = os.path.join(d, 'hf1'); open(hf, 'w').close()
    other = os.path.join(d, 'other1')
    out, _ = run_bash(f'echo x\nhistory -w {other}\nhistory -a {other}\n'
                      f'echo ===M===\ncat {other}\necho ===E===\nexit\n', hf,
                      {'HISTIGNORE': 'history *'})
    mid = out.split('===M===')[1].split('===E===')[0]
    print("1a bash -w NAMED; -a NAMED:", [ln for ln in mid.splitlines() if ln.strip()])
    # 1b. same on the DEFAULT file
    hf = os.path.join(d, 'hf2'); open(hf, 'w').close()
    out, _ = run_bash(f'echo x\nhistory -w\nhistory -a\n'
                      f'echo ===M===\ncat {hf}\necho ===E===\nexit\n', hf,
                      {'HISTIGNORE': 'history *'})
    mid = out.split('===M===')[1].split('===E===')[0]
    print("1b bash -w DEFAULT; -a DEFAULT:", [ln for ln in mid.splitlines() if ln.strip()])
    # 2. -cd 9 suppression vs bare -d 9
    hf = os.path.join(d, 'hf3'); open(hf, 'w').close()
    out, err = run_bash('echo seed\nhistory -cd 9\necho rc=$?\nhistory -d 9\n'
                        'echo rc2=$?\nhistory\nexit\n', hf)
    print("2 bash -cd 9 then -d 9: stdout rc lines:",
          [ln for ln in out.splitlines() if ln.startswith('rc')],
          "| stderr has -d error:", 'position out of range' in err or 'history position' in err)
