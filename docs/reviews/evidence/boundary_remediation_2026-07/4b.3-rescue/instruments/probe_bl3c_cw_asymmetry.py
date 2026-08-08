"""BL-3c — why does bash's `-cw` write a NAMED file but not the DEFAULT one?

bl3b showed `-cw $O` truncating the named file while `-cw` (no operand) leaves
$HISTFILE untouched. The sharp test is `-cw $HISTFILE`: if an explicit operand
naming the DEFAULT file still writes, the discriminator is OPERAND-PRESENT, not
which file it is.  Also re-tests the `-d` rows with an offset that actually
targets a typed entry (bl3b's `-d 1` hit the seeded S1, so its DELETE column
was uninformative)."""
import os, subprocess, sys, tempfile
REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402
assert psh.__file__.startswith(REPO + '/'), psh.__file__
print("DISCRIMINATOR:", psh.__file__)
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']
HI = 'history*:exit:echo*:cat*:printf*'

def run(argv, script, seed=('S1', 'S2')):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf = os.path.join(d, 'hist')
        with open(hf, 'w') as f:
            f.write(''.join(x + '\n' for x in seed))
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('HIST', 'PROMPT'))}
        env.update({'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO,
                    'HISTIGNORE': HI})
        p = subprocess.run(argv, input=(script + '\nunset HISTFILE\nexit\n').encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           cwd=REPO, env=env, timeout=25)
        out = p.stdout.decode(errors='replace')
        with open(hf) as f:
            after = [x.rstrip('\n') for x in f if x.strip()]
    mem = [s.strip().split('  ', 1)[1] for s in out.splitlines()
           if len(s.strip().split('  ', 1)) == 2
           and s.strip().split('  ')[0].strip().isdigit()]
    return mem, after

CASES = [
    ("-cw  (no operand)",        'history -cw\nhistory'),
    ("-cw \"$HISTFILE\"",        'history -cw "$HISTFILE"\nhistory'),
    ("-wc  (reversed)",          'history -wc\nhistory'),
    ("CONTROL -c ; -w",          'history -c\nhistory -w\nhistory'),
    ("CONTROL -w alone",         'history -w\nhistory'),
    ("-cd 3 (delete a TYPED entry)", 'true KEEPME\nhistory -cd 3\nhistory'),
    ("-wd 3 (delete TYPED + write)", 'true KEEPME\nhistory -wd 3\nhistory'),
    ("-d 3 alone (control)",     'true KEEPME\nhistory -d 3\nhistory'),
]
for name, script in CASES:
    bm, bf = run(BASH, script)
    pm, pf = run(PSH, script)
    mark = '  ' if (bm, bf) == (pm, pf) else '* '
    print(f"{mark}{name:32s}")
    print(f"    bash mem={bm} FILE={bf}")
    print(f"    psh  mem={pm} FILE={pf}")
