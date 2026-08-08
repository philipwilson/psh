"""BL-3d — the DECISIVE cells for the file-op suppression rule.

`-cn`/`-ca` after a clear are non-discriminating (an append with nothing
pending and a read with an unmoved cursor both write/read nothing either way).
`-cr` IS discriminating: after the clear, a `-r` that RUNS re-reads the seeded
lines back into memory, and one that is SUPPRESSED leaves memory empty.
Run with and without a filename operand to decide whether operand-presence is
the discriminator."""
import os, subprocess, sys, tempfile
REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402
assert psh.__file__.startswith(REPO + '/'), psh.__file__
print("DISCRIMINATOR:", psh.__file__)
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']

def run(argv, script):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf, other = os.path.join(d, 'hist'), os.path.join(d, 'other')
        open(hf, 'w').write('S1\nS2\n')
        open(other, 'w').write('O1\nO2\n')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('HIST', 'PROMPT'))}
        env.update({'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO,
                    'HISTIGNORE': 'history*:exit:echo*:cat*:printf*'})
        p = subprocess.run(argv,
                           input=(script.replace('$O', other)
                                  + '\nunset HISTFILE\nexit\n').encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           cwd=REPO, env=env, timeout=25)
        out = p.stdout.decode(errors='replace')
        after = [x.rstrip('\n') for x in open(hf) if x.strip()]
    mem = [s.strip().split('  ', 1)[1] for s in out.splitlines()
           if len(s.strip().split('  ', 1)) == 2
           and s.strip().split('  ')[0].strip().isdigit()]
    return mem, after

CASES = [
    ("-cr  (NO operand)      read runs => mem [S1,S2]", 'history -cr\nhistory'),
    ("-cr \"$HISTFILE\"       (operand)",               'history -cr "$HISTFILE"\nhistory'),
    ("-cr $O                 (named operand)",          'history -cr $O\nhistory'),
    ("CONTROL -c ; -r        (separate commands)",      'history -c\nhistory -r\nhistory'),
    ("-dr 3 $O               (-d suppresses?)",         'true KEEPME\nhistory -dr 3 $O\nhistory'),
    ("-dr 3                  (-d, no operand)",         'true KEEPME\nhistory -dr 3\nhistory'),
]
for name, script in CASES:
    bm, bf = run(BASH, script)
    pm, pf = run(PSH, script)
    mark = '  ' if (bm, bf) == (pm, pf) else '* '
    print(f"{mark}{name}")
    print(f"    bash mem={bm} FILE={bf}")
    print(f"    psh  mem={pm} FILE={pf}")
