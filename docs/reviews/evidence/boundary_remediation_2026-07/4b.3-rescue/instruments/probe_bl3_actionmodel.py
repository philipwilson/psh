"""BL-3 — re-derivation of bash's ACTION-SELECTION model for a history cluster.

The verifier is right that a7_order.txt's `-cw` cell could not decide anything:
it wrote to a NAMED file created EMPTY, so "clear ran then wrote an empty list"
and "`-w` never ran at all" produce the identical observable. That is the
R2-F1 instrument-mirror failure a third time, and it is the reason the shipped
dispatcher runs a file op that bash suppresses.

THE FIX IN THE INSTRUMENT: every file an action might write is pre-seeded with
a SENTINEL line. "Untouched" (sentinel still there, alone) is then distinct
from "written" (sentinel replaced or appended to) and from "truncated" (empty).
Each action gets an observable that cannot be produced by any other action:

    -c        memory becomes empty
    -d N      one specific entry disappears from memory
    -w FILE   FILE's sentinel is REPLACED by the memory list
    -a FILE   FILE keeps its sentinel and GAINS the pending entries
    -r FILE   memory GAINS FILE's marker lines
    -n FILE   memory GAINS FILE's unread marker lines
    -s ARG    memory GAINS the literal ARG
    -p ARG    stdout GAINS the expansion (memory unchanged)

Every cell reports WHICH actions fired, for bash and for psh, so the model is
read off the data rather than assumed.
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
print("TIP:", subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                             capture_output=True, text=True).stdout.strip())

BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']
HI = 'history*:exit:echo*:cat*:printf*:true SCAFFOLD*'

SENTINEL = 'SENTINEL_UNTOUCHED'
# The default $HISTFILE always starts with these; a typed command is added on
# top so there is always something PENDING for `-a`/`-w` to write.
SEED = ['S1', 'S2']
# The named file always starts with the sentinel plus marker lines a read
# would bring in.
NAMED = [SENTINEL, 'MARK1', 'MARK2']


def run(argv, script, seed=SEED, named=NAMED):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf = os.path.join(d, 'hist')
        other = os.path.join(d, 'other')
        with open(hf, 'w') as f:
            f.write(''.join(x + '\n' for x in seed))
        with open(other, 'w') as f:
            f.write(''.join(x + '\n' for x in named))
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('HIST', 'PROMPT'))}
        env.update({'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO,
                    'HISTIGNORE': HI})
        # HISTFILE is unset before exit so the exit-save cannot pollute the
        # file reading (the verifier's own technique).
        body = script.replace('$O', other) + '\nunset HISTFILE\nexit\n'
        p = subprocess.run(argv, input=body.encode(), stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, cwd=REPO, env=env,
                           timeout=25)
        out = p.stdout.decode(errors='replace')
        err = p.stderr.decode(errors='replace')
        with open(hf) as f:
            hist_after = [x.rstrip('\n') for x in f if x.strip()]
        with open(other) as f:
            other_after = [x.rstrip('\n') for x in f if x.strip()]
    mem = []
    for ln in out.splitlines():
        s = ln.strip()
        head = s.split('  ', 1)
        if len(head) == 2 and head[0].isdigit():
            mem.append(head[1].strip())
    return mem, hist_after, other_after, out, err


def fired(mem, hist_after, other_after, out, default_target):
    """Which actions demonstrably ran, from observables alone."""
    acts = set()
    if mem == []:
        acts.add('c(cleared)')
    if 'true keep' not in mem and mem != []:
        acts.add('d(deleted)')
    tgt = hist_after if default_target else other_after
    if default_target:
        if hist_after == []:
            acts.add('w(wrote-empty)')
        elif 'S1' not in hist_after:
            acts.add('w(rewrote)')
        elif len(hist_after) > len(SEED):
            acts.add('a(appended)')
    else:
        if SENTINEL not in tgt:
            acts.add('w(rewrote)')
        elif len(tgt) > len(NAMED):
            acts.add('a(appended)')
    if 'MARK1' in mem or 'MARK2' in mem:
        acts.add('r/n(read)')
    if 'STORED' in mem:
        acts.add('s(stored)')
    if any(l.strip() == 'PRINTME' for l in out.splitlines()):
        acts.add('p(printed)')
    return acts or {'(none)'}


CELLS = [
    # (name, script, default_target?, note)
    ("-c alone", 'true keep\nhistory -c\nhistory', True, 'baseline'),
    ("-w alone (NAMED)", 'true keep\nhistory -w $O\nhistory', False, 'baseline'),
    ("-a alone (NAMED)", 'true keep\nhistory -a $O\nhistory', False, 'baseline'),
    ("-r alone (NAMED)", 'true keep\nhistory -r $O\nhistory', False, 'baseline'),
    ("-s alone", 'true keep\nhistory -s STORED\nhistory', True, 'baseline'),

    ("-cw NAMED", 'true keep\nhistory -cw $O\nhistory', False,
     'DOES the write run after the clear?'),
    ("-cw DEFAULT", 'true keep\nhistory -cw\nhistory', True,
     'the verifier cell: bash leaves the file untouched'),
    ("-ca NAMED", 'true keep\nhistory -ca $O\nhistory', False, ''),
    ("-cr NAMED", 'true keep\nhistory -cr $O\nhistory', False, ''),
    ("-cn DEFAULT", 'true keep\nhistory -cn\nhistory', True, ''),
    ("-cs STORED", 'true keep\nhistory -cs STORED\nhistory', True,
     'does -s survive the clear?'),
    ("-cp PRINTME", 'true keep\nhistory -cp PRINTME\nhistory', True,
     'does -p survive the clear?'),

    ("-wd 1 NAMED", 'true keep\nhistory -wd 1 $O\nhistory', False,
     'delete plus write'),
    ("-ad 1 NAMED", 'true keep\nhistory -ad 1 $O\nhistory', False, ''),
    ("-rd 1 NAMED", 'true keep\nhistory -rd 1 $O\nhistory', False, ''),
    ("-sd 1 STORED", 'true keep\nhistory -sd 1 STORED\nhistory', True, ''),
    ("-pd 1 PRINTME", 'true keep\nhistory -pd 1 PRINTME\nhistory', True, ''),

    ("-sw NAMED", 'true keep\nhistory -sw $O STORED\nhistory', False,
     'store plus write'),
    ("-pw NAMED", 'true keep\nhistory -pw $O\nhistory', False,
     'print plus write'),
    ("-ps PRINTME", 'true keep\nhistory -ps PRINTME\nhistory', True, ''),
]

print("\nEach cell lists the actions that DEMONSTRABLY fired, per shell.\n")
divergent = []
for name, script, default_target, note in CELLS:
    row = {}
    for label, argv in (('bash', BASH), ('psh ', PSH)):
        mem, hf, of, out, err = run(argv, script)
        row[label.strip()] = fired(mem, hf, of, out, default_target)
        row[label.strip() + '_detail'] = (mem, hf, of)
    same = row['bash'] == row['psh']
    if not same:
        divergent.append(name)
    print(f"{'  ' if same else '* '}{name:18s} bash={sorted(row['bash'])}")
    print(f"  {'':18s} psh ={sorted(row['psh'])}")
    if not same:
        print(f"  {'':18s} bash mem/hist/other={row['bash_detail']}")
        print(f"  {'':18s} psh  mem/hist/other={row['psh_detail']}")
    if note:
        print(f"  {'':18s} ({note})")

print(f"\n\nDIVERGENT CELLS ({len(divergent)}): {divergent}")
