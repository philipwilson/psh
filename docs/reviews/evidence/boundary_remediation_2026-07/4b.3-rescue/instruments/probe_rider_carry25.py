"""Carry #25 rider probe: `history -ps` clustered flag, psh vs bash 5.2.26.

LEDGER Part B row 25 ATTACHES this to slot 4B.3 ("trivial option-scan fix
while history builtin is open") — the brief's Phase A carry sweep omits it.
Characterize before proposing a disposition.
"""
import os
import subprocess
import sys
import tempfile

REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402

print("DISCRIMINATOR:", psh.__file__)
assert psh.__file__.startswith(REPO + '/'), psh.__file__

BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']


def run(argv, script):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('HIST', 'PROMPT'))}
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        env.update({'HISTFILE': os.path.join(d, 'hist'), 'TERM': 'dumb',
                    'PYTHONPATH': REPO})
        p = subprocess.run(argv, input=script.encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           cwd=REPO, env=env, timeout=20)
    return p.stdout.decode(errors='replace'), p.stderr.decode(errors='replace')


CASES = {
    # clustered -ps: bash's internal_getopt sees -p then -s
    'ps_with_arg': 'history -ps hello\nhistory\nexit\n',
    'sp_with_arg': 'history -sp hello\nhistory\nexit\n',
    'p_alone': 'history -p hello\nexit\n',
    's_alone': 'history -s hello\nhistory\nexit\n',
    # rc observation
    'ps_rc': 'history -ps hello; echo rc=$?\nexit\n',
}

for name, script in CASES.items():
    for label, argv in (('bash', BASH), ('psh ', PSH)):
        out, err = run(argv, script)
        out_l = [ln for ln in out.splitlines() if ln.strip()]
        err_l = [ln for ln in err.splitlines() if ln.strip()
                 and 'psh:' in ln or 'history' in ln]
        print(f"{name:14s} {label}: out={out_l} err={err_l[:2]}")
    print()
