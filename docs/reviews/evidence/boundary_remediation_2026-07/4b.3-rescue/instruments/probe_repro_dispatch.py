"""Dev re-run of the integrator dispatch probe, pointed at THIS worktree.

Faithful to tmp/w4b3-dispatch-probes/probe_medium7_history_cursors.py
(md5 215163db3831118cfb1a948f40bbbe16 at the MAIN checkout) except:
  - REPO = /Users/pwilson/src/psh-r4b-3 (this worktree)
  - the discriminator is ASSERTED, not merely printed (4B.2 lesson 4:
    the search path is a request, the resolved __file__ is the fact)
  - bash version recorded in the transcript (oracle rule)
"""
import os
import subprocess
import sys
import tempfile

REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402

print("DISCRIMINATOR:", psh.__file__)
assert psh.__file__.startswith(REPO + '/'), (
    f"WRONG TREE: {psh.__file__} not under {REPO}")

BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']

print("ORACLE:", subprocess.run(['/opt/homebrew/bin/bash', '--version'],
                                capture_output=True, text=True
                                ).stdout.splitlines()[0])
print("TIP:", subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                             capture_output=True, text=True).stdout.strip())


def run(argv, script, histfile, extra_env=None):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('HIST', 'PROMPT'))}
    env.update({'HISTFILE': histfile, 'TERM': 'dumb',
                'PYTHONPATH': REPO})
    if extra_env:
        env.update(extra_env)
    p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, cwd=REPO, env=env,
                       timeout=20)
    return p.stdout.decode(errors='replace')


def counts(out, tokens):
    res = {}
    for tok in tokens:
        res[tok] = sum(1 for ln in out.splitlines()
                       if ln.strip().split('  ')[-1] == tok
                       and ln.strip()[:1].isdigit())
    return res


def leg_a(argv, label):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf = os.path.join(d, 'hist')
        with open(hf, 'w') as f:
            f.write('seedA\nseedB\nseedC\n')
        script = ('history -d 1\n'
                  f'echo seedD >> {hf}\n'
                  'history -n\n'
                  'history\n'
                  'exit\n')
        out = run(argv, script, hf)
        c = counts(out, ['seedA', 'seedB', 'seedC', 'seedD'])
        print(f"A {label}: {c}")


def leg_b(argv, label):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf = os.path.join(d, 'hist')
        open(hf, 'w').close()
        script = ''.join(f'history -s s{i}\n' for i in range(1, 6))
        script += 'history\nexit\n'
        out = run(argv, script, hf,
                  {'HISTSIZE': '3', 'HISTIGNORE': 'history *:history'})
        c = counts(out, [f's{i}' for i in range(1, 6)])
        print(f"B {label}: {c}  (listing lines: "
              f"{sum(1 for ln in out.splitlines() if ln.strip()[:1].isdigit())})")


def leg_c(argv, label):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf = os.path.join(d, 'hist')
        open(hf, 'w').close()
        script = ('echo seedX\n'
                  'history -a\n'
                  'history -c\n'
                  'history -n\n'
                  'history\n'
                  'exit\n')
        out = run(argv, script, hf)
        c = counts(out, ['echo seedX'])
        print(f"C {label}: 'echo seedX' in final listing: {c['echo seedX']}")


for leg in (leg_a, leg_b, leg_c):
    leg(BASH, 'bash')
    leg(PSH, 'psh ')
    print()
