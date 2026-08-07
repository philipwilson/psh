"""b4's MIRROR FACE (R12): the global counter SUPPRESSING a named read.

b4 as pinned covers "a named read corrupts the DEFAULT cursor". The same single
global counter produces a second observable from the other side: because the
startup load has already advanced it, bash's `history -n OTHER` resumes at that
offset INSIDE the named file and can read nothing at all, while psh's
per-default-file cursor starts a named read at 0 and reads the line.

Measured before pinning, with a control that varies the named file's LENGTH so
the reading is "an offset into the named file", not "named reads are blocked".
"""
import os
import subprocess
import sys
import tempfile

REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402

assert psh.__file__.startswith(REPO + '/'), psh.__file__
print("DISCRIMINATOR:", psh.__file__)
print("ORACLE:", subprocess.run(['/opt/homebrew/bin/bash', '--version'],
                                capture_output=True,
                                text=True).stdout.splitlines()[0])
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']


def run(argv, seed, other):
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf, oth = os.path.join(d, 'hist'), os.path.join(d, 'other')
        with open(hf, 'w') as f:
            f.write(''.join(x + '\n' for x in seed))
        with open(oth, 'w') as f:
            f.write(''.join(x + '\n' for x in other))
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('HIST', 'PROMPT'))}
        env.update({'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO,
                    'HISTIGNORE': 'history*:exit:echo*:cat*:printf*'})
        script = f'history -n {oth}\nhistory\nexit\n'
        p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, cwd=REPO, env=env,
                           timeout=25)
        out = p.stdout.decode(errors='replace')
    return [s.strip().split('  ', 1)[1] for s in out.splitlines()
            if len(s.strip().split('  ', 1)) == 2
            and s.strip().split('  ')[0].strip().isdigit()]


for name, seed, other in [
    ("seed 1 line, OTHER 1 line", ['D1'], ['O1']),
    ("seed 1 line, OTHER 2 lines (control: offset, not a block)",
     ['D1'], ['O1', 'O2']),
    ("seed 2 lines, OTHER 3 lines (control: offset tracks the seed)",
     ['D1', 'D2'], ['O1', 'O2', 'O3']),
    ("seed 0 lines, OTHER 2 lines (control: counter at 0 reads all)",
     [], ['O1', 'O2']),
]:
    b, p = run(BASH, seed, other), run(PSH, seed, other)
    print(f"  {name}")
    print(f"      bash mem={b}")
    print(f"      psh  mem={p}")
    print(f"      => {'MATCH' if b == p else 'DIVERGE'}\n")
