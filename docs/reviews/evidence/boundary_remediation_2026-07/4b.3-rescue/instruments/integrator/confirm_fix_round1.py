"""Confirm BL-1/2/3 fixed at tip 8bb139ee + verify the operand-sensitive
suppression refinement (dev's new claim) vs bash."""
import os, subprocess, sys, tempfile
BASE = '/Users/pwilson/src/psh'
TIP = '/Users/pwilson/src/psh-verify-4b3-tip2'
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']

def run(argv, script, hf, cwd, extra=None):
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
           'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': cwd}
    if extra: env.update(extra)
    p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, cwd=cwd, env=env, timeout=20)
    return p.stdout.decode(errors='replace'), p.stderr.decode(errors='replace')

PSH = [sys.executable, '-m', 'psh', '--norc', '-i']
with tempfile.TemporaryDirectory(dir=BASE + '/tmp') as d:
    print("=== BL-1 fixed? (expect tip ['true same']) ===")
    hf = os.path.join(d, 'f1')
    with open(hf, 'w') as f: f.write('true same\n')
    run(PSH, 'true same\nhistory -d 2\nexit\n', hf, TIP, {'HISTIGNORE': 'history *:exit'})
    print("tip:", open(hf).read().splitlines())
    print("=== BL-2 fixed? (expect tip stderr message, rc 1) ===")
    hf = os.path.join(d, 'f2'); open(hf, 'w').close()
    out, err = run(PSH, 'history -wa\necho rc=$?\nexit\n', hf, TIP)
    print("tip rc:", [l for l in out.splitlines() if l.startswith('rc=')],
          "stderr:", [l for l in err.splitlines() if 'history' in l][:1])
    print("=== BL-3 fixed + operand sensitivity ===")
    for lab, argv, cwd in (('bash', BASH, BASE), ('tip ', PSH, TIP)):
        # no-operand: suppressed
        hf = os.path.join(d, 'f3a' + lab.strip())
        with open(hf, 'w') as f: f.write('S1\nS2\n')
        out, _ = run(argv, f'history -cw\necho ===M===\ncat {hf}\necho ===E===\nunset HISTFILE\nexit\n', hf, cwd)
        noop = out.split('===M===')[1].split('===E===')[0].split()
        # with filename operand: runs
        hf2 = os.path.join(d, 'f3b' + lab.strip())
        with open(hf2, 'w') as f: f.write('S1\nS2\n')
        out, _ = run(argv, f'history -cw {hf2}\necho ===M===\ncat {hf2}\necho ===E===\nunset HISTFILE\nexit\n', hf2, cwd)
        oper = out.split('===M===')[1].split('===E===')[0].split()
        # -cr FILE: re-reads into memory
        hf3 = os.path.join(d, 'f3c' + lab.strip()); open(hf3, 'w').close()
        src = os.path.join(d, 'src' + lab.strip())
        with open(src, 'w') as f: f.write('R1\n')
        out, _ = run(argv, f'history -cr {src}\nhistory\nexit\n', hf3, cwd,
                     {'HISTIGNORE': 'history*:exit'})
        mem = [l.strip().split('  ')[-1] for l in out.splitlines() if l.strip()[:1].isdigit()]
        print(f"{lab}: -cw noop file={noop} | -cw FILE file={oper} | -cr FILE mem={mem}")
