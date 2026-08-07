"""BL-3b — action-selection model, with the BL-3a detector defect corrected.

DETECTOR DEFECT in probe_bl3_actionmodel.py (self-disclosed): it inferred
"delete fired" from the absence of the typed entry, which a CLEAR also
produces. So `-cr` and `-cs` were reported as having run a `-d` that was never
in the cluster. Those two rows of bl3_actionmodel.txt are VOID.

Corrected: two distinct typed entries, so clear and delete are orthogonal —

    memory starts [KEEPME, true keep]
    cleared  <=>  BOTH gone
    deleted  <=>  KEEPME gone, `true keep` still present   (`-d 1` targets it)

and every file an action might write is pre-seeded with a SENTINEL so
"untouched" is distinguishable from "written empty" — the confound that made
the original `-cw` cell decide nothing.
"""
import os
import subprocess
import sys
import tempfile

REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402

assert psh.__file__.startswith(REPO + '/'), f"WRONG TREE: {psh.__file__}"
print("DISCRIMINATOR:", psh.__file__)
print("ORACLE:", subprocess.run(['/opt/homebrew/bin/bash', '--version'],
                                capture_output=True,
                                text=True).stdout.splitlines()[0])

BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']
HI = 'history*:exit:echo*:cat*:printf*'
SENT = 'SENT'
SEED = ['S1', 'S2']
NAMED = [SENT, 'MARK1']
SETUP = 'true KEEPME\ntrue keep\n'          # two orthogonal typed entries


def run(argv, cluster, seed=SEED, named=NAMED):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf, other = os.path.join(d, 'hist'), os.path.join(d, 'other')
        with open(hf, 'w') as f:
            f.write(''.join(x + '\n' for x in seed))
        with open(other, 'w') as f:
            f.write(''.join(x + '\n' for x in named))
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('HIST', 'PROMPT'))}
        env.update({'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO,
                    'HISTIGNORE': HI})
        script = (SETUP + cluster.replace('$O', other)
                  + '\nhistory\nunset HISTFILE\nexit\n')
        p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, cwd=REPO, env=env,
                           timeout=25)
        out = p.stdout.decode(errors='replace')
        with open(hf) as f:
            hf_after = [x.rstrip('\n') for x in f if x.strip()]
        with open(other) as f:
            oth_after = [x.rstrip('\n') for x in f if x.strip()]
    mem = []
    for ln in out.splitlines():
        s = ln.strip()
        head = s.split('  ', 1)
        if len(head) == 2 and head[0].isdigit():
            mem.append(head[1].strip())
    return mem, hf_after, oth_after, out


def fired(mem, hf_after, oth_after, out):
    acts = set()
    keepme, keep = 'true KEEPME' in mem, 'true keep' in mem
    if not keepme and not keep:
        acts.add('CLEAR')
    elif not keepme and keep:
        acts.add('DELETE')
    if hf_after != SEED:
        acts.add('DEFAULT-FILE-WRITTEN')
    if oth_after != NAMED:
        acts.add('NAMED-FILE-WRITTEN')
    if 'MARK1' in mem:
        acts.add('READ')
    if 'STORED' in mem:
        acts.add('STORE')
    if any(ln.strip() == 'PRINTME' for ln in out.splitlines()):
        acts.add('PRINT')
    return acts or {'NOTHING'}


CELLS = [
    ("-c", 'history -c'), ("-d 1", 'history -d 1'),
    ("-w $O", 'history -w $O'), ("-a $O", 'history -a $O'),
    ("-r $O", 'history -r $O'), ("-w (default)", 'history -w'),
    ("-a (default)", 'history -a'), ("-s STORED", 'history -s STORED'),
    ("-p PRINTME", 'history -p PRINTME'),
    ("-cw $O", 'history -cw $O'), ("-cw (default)", 'history -cw'),
    ("-ca $O", 'history -ca $O'), ("-ca (default)", 'history -ca'),
    ("-cr $O", 'history -cr $O'), ("-cn (default)", 'history -cn'),
    ("-cs STORED", 'history -cs STORED'), ("-cp PRINTME", 'history -cp PRINTME'),
    ("-wd 1 $O", 'history -wd 1 $O'), ("-ad 1 $O", 'history -ad 1 $O'),
    ("-rd 1 $O", 'history -rd 1 $O'), ("-sd 1 STORED", 'history -sd 1 STORED'),
    ("-pd 1 PRINTME", 'history -pd 1 PRINTME'),
    ("-sw $O STORED", 'history -sw $O STORED'),
    ("-pw $O", 'history -pw $O'), ("-ps PRINTME", 'history -ps PRINTME'),
]

div = []
for name, cluster in CELLS:
    b = fired(*run(BASH, cluster))
    p = fired(*run(PSH, cluster))
    same = b == p
    if not same:
        div.append(name)
    print(f"{'  ' if same else '* '}{name:16s} bash={sorted(b)}")
    print(f"  {'':16s} psh ={sorted(p)}")

print(f"\nDIVERGENT ({len(div)}): {div}")
print("\nbash model read off the rows above:")
print("  a cluster runs AT MOST ONE 'action' from {file op, store, print},")
print("  and -c / -d suppress it — EXCEPT where the rows say otherwise;")
print("  see the printed set per row rather than trusting this sentence.")
