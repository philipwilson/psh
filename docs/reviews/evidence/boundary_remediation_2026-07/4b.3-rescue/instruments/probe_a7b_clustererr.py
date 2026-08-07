"""Phase A7b — stderr/rc for the clusters bash ACCEPTS but that fail (rc 1)."""
import os, subprocess, sys, tempfile
REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402
assert psh.__file__.startswith(REPO + '/'), psh.__file__
print("DISCRIMINATOR:", psh.__file__)
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']
for spec in ('-an', '-rw', '-nr', '-ar', '-aw', '-cw', '-ps hello', '-ds 1 X'):
    for lab, argv in (('bash', BASH), ('psh ', PSH)):
        with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
            hf = os.path.join(d, 'hist')
            with open(hf, 'w') as f:
                f.write('S1\nS2\nS3\n')
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('HIST', 'PROMPT'))}
            env.update({'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO,
                        'HISTIGNORE': 'history*:exit'})
            p = subprocess.run(argv, input=f'history {spec}; echo "RC=$?"\nexit\n'.encode(),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               cwd=REPO, env=env, timeout=20)
            rc = [x for x in p.stdout.decode().splitlines() if x.startswith('RC=')]
            err = [x for x in p.stderr.decode().splitlines()
                   if 'history' in x or 'psh' in x or 'bash' in x]
            print(f"  history {spec:12s} {lab}: {rc}  stderr={err[:2]}")
    print()
