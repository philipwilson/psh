"""Phase A5 — piped-vs-PTY validity, per defect leg.

Carry #34 records that a piped `-i` shell is artifact-bearing (PROMPT_COMMAND
does not fire there), so "the piped harness measured the subject" is a claim
that needs its own evidence rather than an assumption.  Every Phase A figure so
far came from the piped harness; this re-runs the three defect legs plus the two
newly-found data-integrity faces under a REAL PTY and compares.

If a leg's BASH behaviour differs piped-vs-PTY the PTY reading wins and the
piped cell is labelled.  If both shells agree with their own piped readings,
the state machine is harness-independent for that leg.
"""
import os
import sys
import tempfile

import pexpect

REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402

assert psh.__file__.startswith(REPO + '/'), f"WRONG TREE: {psh.__file__}"
print("DISCRIMINATOR:", psh.__file__)

BASH_ARGV = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH_ARGV = [sys.executable, '-m', 'psh', '--norc', '-i']
PROMPT = 'PROBE$ '


def pty_run(argv, lines, histfile, extra_env=None):
    """Drive a REAL pty; return everything the shell printed."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('HIST', 'PROMPT'))}
    env.update({'HISTFILE': histfile, 'TERM': 'dumb', 'PYTHONPATH': REPO,
                'PS1': PROMPT, 'PS2': '> '})
    if extra_env:
        env.update(extra_env)
    child = pexpect.spawn(argv[0], argv[1:], env=env, cwd=REPO, timeout=15,
                          encoding='utf-8', codec_errors='replace',
                          dimensions=(40, 200))
    out = []
    try:
        for ln in lines:
            child.sendline(ln)
        child.sendline('exit')
        child.expect(pexpect.EOF)
        out.append(child.before)
    except pexpect.TIMEOUT:
        out.append('<<TIMEOUT>>' + (child.before or ''))
    finally:
        child.close(force=True)
    return ''.join(out)


def listing(out):
    """History-listing entries: lines shaped ``NNNN  text``."""
    res = []
    for ln in out.splitlines():
        s = ln.strip()
        head = s.split('  ', 1)
        if len(head) == 2 and head[0].isdigit():
            res.append(head[1].strip())
    return res


def cell(name, lines, seed=None, extra_env=None, named=None):
    print(f"\n--- {name} (PTY) ---")
    got = {}
    for label, argv in (('bash', BASH_ARGV), ('psh ', PSH_ARGV)):
        with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
            hf = os.path.join(d, 'hist')
            with open(hf, 'w') as f:
                if seed:
                    f.write(''.join(s + '\n' for s in seed))
            for base, content in (named or {}).items():
                with open(os.path.join(d, base), 'w') as f:
                    f.write(''.join(s + '\n' for s in content))
            body = [ln.replace('$OTHER', d) for ln in lines]
            out = pty_run(argv, body, hf, extra_env)
            after = []
            if os.path.exists(hf):
                with open(hf) as f:
                    after = [x.rstrip('\n') for x in f if x.strip()]
        got[label.strip()] = (listing(out), after)
        print(f"   {label}: listing={listing(out)}")
        print(f"         file-after-exit={after}")
    same = got['bash'] == got['psh']
    print(f"  => {'MATCHES' if same else 'DIVERGES'}")
    return got


HI = 'history*:echo ===*:cat *:wc *:exit:printf *'

# ---- Leg A: cursor conflation ------------------------------------------
cell("LEG A  -d then external append then -n",
     ['history -d 1',
      'printf "seedD\\n" >> "$HISTFILE"',
      'history -n',
      'history'],
     seed=['seedA', 'seedB', 'seedC'], extra_env={'HISTIGNORE': HI})

# ---- Leg B: -s cap ------------------------------------------------------
cell("LEG B  HISTSIZE=3, 5x history -s",
     [f'history -s s{i}' for i in range(1, 6)] + ['history'],
     extra_env={'HISTSIZE': '3', 'HISTIGNORE': HI})

# ---- Leg C: carry #32 ---------------------------------------------------
cell("LEG C  echo; -a; -c; -n",
     ['echo seedX', 'history -a', 'history -c', 'history -n', 'history'],
     seed=None)

# ---- New face 1: -r NAMED leaks into $HISTFILE --------------------------
cell("NEW-1  -r NAMED then -a default",
     ['history -r $OTHER/other', 'history -a', 'history'],
     seed=['seed1', 'seed2', 'seed3'],
     named={'other': ['oth1', 'oth2']}, extra_env={'HISTIGNORE': HI})

# ---- New face 2: -w NAMED loses the pending entry -----------------------
cell("NEW-2  -w NAMED then exit-save",
     ['true NEW', 'history -w $OTHER/other'],
     seed=['seed1', 'seed2', 'seed3'],
     named={'other': ['oth1', 'oth2']}, extra_env={'HISTIGNORE': HI})

# ---- New face 3: -r/-n bypass the cap -----------------------------------
cell("NEW-3  -r a 10-line file under HISTSIZE=4",
     ['history -r $OTHER/big', 'history'],
     named={'big': [f'B{i}' for i in range(1, 11)]},
     extra_env={'HISTSIZE': '4', 'HISTIGNORE': HI})
