"""Phase A7c — the full 2-letter cluster ACCEPT/REJECT matrix in bash 5.2.26.

R1(a) said full matrices only where a sanity row diverges.  Every sanity row
diverged (A6b), and A7b showed bash REJECTS some clusters with a silent rc 1
while accepting others with rc 0 — so the accept/reject rule has to be derived,
not guessed.  rc is the observable; arguments are supplied so a flag that needs
one is never rejected merely for lacking it.
"""
import itertools, os, subprocess, sys, tempfile
REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402
assert psh.__file__.startswith(REPO + '/'), psh.__file__
print("DISCRIMINATOR:", psh.__file__)
print("ORACLE:", subprocess.run(['/opt/homebrew/bin/bash', '--version'],
                                capture_output=True, text=True).stdout.splitlines()[0])
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
LETTERS = 'cdpsanrw'
# operands that satisfy every flag that needs one: -d wants an offset,
# -p/-s want args, -a/-n/-r/-w take an optional filename (omitted -> default)
ARGS = {'d': '1', 'p': 'X', 's': 'X'}


def rc(spec):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf = os.path.join(d, 'hist')
        with open(hf, 'w') as f:
            f.write('S1\nS2\nS3\n')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('HIST', 'PROMPT'))}
        env.update({'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO,
                    'HISTIGNORE': 'history*:exit'})
        p = subprocess.run(BASH, input=f'history {spec}; echo "RC=$?"\nexit\n'.encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           cwd=REPO, env=env, timeout=20)
        for ln in p.stdout.decode().splitlines():
            if ln.startswith('RC='):
                return ln[3:]
    return '?'


print("\nSINGLE letters:")
for a in LETTERS:
    arg = (' ' + ARGS[a]) if a in ARGS else ''
    print(f"  -{a}{arg:4s} rc={rc('-' + a + arg)}")

print("\nPAIRS (unordered; operands appended in letter order):")
FILEOPS = set('anrw')
rows = []
for a, b in itertools.combinations(LETTERS, 2):
    extra = ''.join(' ' + ARGS[x] for x in (a, b) if x in ARGS)
    r = rc(f'-{a}{b}{extra}')
    both_fileops = (a in FILEOPS and b in FILEOPS)
    rows.append((a + b, r, both_fileops))
    print(f"  -{a}{b}{extra:8s} rc={r}   {'[two file ops]' if both_fileops else ''}")

print("\nORDER CHECK (a few reversed pairs — should match):")
for a, b in (('p', 's'), ('c', 'w'), ('d', 's'), ('a', 'n')):
    extra = ''.join(' ' + ARGS[x] for x in (a, b) if x in ARGS)
    rextra = ''.join(' ' + ARGS[x] for x in (b, a) if x in ARGS)
    print(f"  -{a}{b} rc={rc(f'-{a}{b}{extra}')}   "
          f"-{b}{a} rc={rc(f'-{b}{a}{rextra}')}")

print("\nRULE CHECK — 'reject iff more than one of a/n/r/w':")
bad = [f"-{p}(rc={r})" for p, r, two in rows if two and r == '0'] + \
      [f"-{p}(rc={r})" for p, r, two in rows if not two and r != '0']
print("  counterexamples:", bad if bad else "NONE — rule holds for all pairs")
