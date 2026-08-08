"""Shared preamble for the standalone 4B.3 probes (discriminator + oracle)."""
import os
import subprocess
import sys
import tempfile

REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402

assert psh.__file__.startswith(REPO + '/'), f"WRONG TREE: {psh.__file__}"
BASH = ['/opt/homebrew/bin/bash', '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']
HI = 'history*:exit:echo*:cat*:printf*'


def banner():
    print("DISCRIMINATOR:", psh.__file__)
    print("ORACLE:", subprocess.run(['/opt/homebrew/bin/bash', '--version'],
                                    capture_output=True,
                                    text=True).stdout.splitlines()[0])


def shell_run(argv, script, seed=None, named=None, histignore=HI,
              extra_env=None, capture_stderr=False):
    """Run one piped `--norc -i` cell; return (stdout, stderr, histfile lines)."""
    with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
        hf = os.path.join(d, 'hist')
        with open(hf, 'w') as f:
            f.write(''.join(s + '\n' for s in (seed or [])))
        for base, lines in (named or {}).items():
            with open(os.path.join(d, base), 'w') as f:
                f.write(''.join(x + '\n' for x in lines))
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('HIST', 'PROMPT'))}
        env.update({'HISTFILE': hf, 'TERM': 'dumb', 'PYTHONPATH': REPO})
        if histignore is not None:
            env['HISTIGNORE'] = histignore
        env.update(extra_env or {})
        p = subprocess.run(argv, input=script.replace('$D', d).encode(),
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE if capture_stderr
                           else subprocess.DEVNULL,
                           cwd=REPO, env=env, timeout=25)
        with open(hf) as f:
            after = [x.rstrip('\n') for x in f if x.strip()]
        extra = {b: open(os.path.join(d, b)).read().splitlines()
                 for b in (named or {})}
    return (p.stdout.decode(errors='replace'),
            (p.stderr.decode(errors='replace') if capture_stderr else ''),
            after, extra)


def listing(out):
    res = []
    for ln in out.splitlines():
        s = ln.strip()
        head = s.split('  ', 1)
        if len(head) == 2 and head[0].isdigit():
            res.append(head[1].strip())
    return res


def rc_of(out):
    return next((l[3:] for l in out.splitlines() if l.startswith('RC=')), '?')
