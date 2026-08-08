"""Slot 4B.3 Phase A probe harness — psh vs live bash 5.2.26.

Harness shape is the SANCTIONED dispatch-probe shape: piped `--norc -i`
subprocess, explicit argv (never /bin/bash), HISTFILE in the cell's OWN mktemp
scratch under this worktree's tmp/, env scrubbed of HIST*/PROMPT*, the psh
discriminator ASSERTED (4B.2 lesson 4: the search path is a request, the
resolved __file__ is the fact).

OBSERVATION MODEL.  The two counters bash keeps (its `history_lines_in_file`
and the append marker) have no direct spelling, so every cell observes them
INDIRECTLY through content: markers are written into the script and the
in-memory listing + on-disk file are dumped verbatim at each observation
point.  Reading CONTENT rather than counts avoids the circularity of deriving
a counter from the very operation whose rule is under test.

By default the harness sets HISTIGNORE so the probe's own control commands
(`history …`, the `echo ===MARK===` separators, `cat`, `wc`, `exit`) are never
RECORDED — the in-memory list then holds only what the cell deliberately put
there, which is what makes the state machine readable.  `history -s`'s store
bypasses HISTIGNORE in both shells (leg B of the dispatch probe proves it for
bash), so `-s` cells are unaffected by the suppression.  Cells that need the
unsuppressed behaviour pass `histignore=None` and are LABELLED as such.
"""
import os
import subprocess
import sys
import tempfile

REPO = '/Users/pwilson/src/psh-r4b-3'
sys.path.insert(0, REPO)
import psh  # noqa: E402

assert psh.__file__.startswith(REPO + '/'), f"WRONG TREE: {psh.__file__}"
DISCRIMINATOR = psh.__file__

BASH_BIN = '/opt/homebrew/bin/bash'
BASH = [BASH_BIN, '--norc', '-i']
PSH = [sys.executable, '-m', 'psh', '--norc', '-i']

# Suppress the probe's own scaffolding from the RECORDED history.
DEFAULT_HISTIGNORE = 'history*:echo ===*:cat *:wc *:exit:printf *'


def bash_version():
    return subprocess.run([BASH_BIN, '--version'], capture_output=True,
                          text=True).stdout.splitlines()[0]


def header(title):
    print("=" * 72)
    print(title)
    print(f"  discriminator: {DISCRIMINATOR}")
    print(f"  oracle: {bash_version()}")
    tip = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                         capture_output=True, text=True).stdout.strip()
    print(f"  tip: {tip}")
    print("=" * 72)


def _run(argv, script, histfile, extra_env=None, histignore=DEFAULT_HISTIGNORE):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('HIST', 'PROMPT'))}
    env.update({'HISTFILE': histfile, 'TERM': 'dumb', 'PYTHONPATH': REPO})
    if histignore is not None:
        env['HISTIGNORE'] = histignore
    if extra_env:
        env.update(extra_env)
    p = subprocess.run(argv, input=script.encode(), stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, cwd=REPO, env=env,
                       timeout=30)
    return p.stdout.decode(errors='replace')


def _parse(out):
    """Split harness stdout into {section: [lines]} on ``===NAME===`` markers."""
    sections, cur = {}, None
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith('===') and s.endswith('===') and len(s) > 6:
            cur = s.strip('=')
            sections[cur] = []
        elif cur is not None and s:
            sections[cur].append(s)
    return sections


def _listing(lines):
    """Strip the ``NNNNN  `` listing prefix, keeping entry text only."""
    out = []
    for ln in lines:
        parts = ln.split('  ', 1)
        if parts[0].strip().isdigit() and len(parts) == 2:
            out.append(parts[1])
        else:
            out.append('?' + ln)
    return out


def run_cell(script, seed=None, extra_env=None, histignore=DEFAULT_HISTIGNORE,
             named_seed=None):
    """Run *script* in both shells; return {shell: (sections, file_after_exit)}.

    *seed* seeds $HISTFILE before start; *named_seed* is a dict of
    {basename: contents} written into the same scratch dir (for named-file
    cells).  ``$OTHER`` in the script is substituted with the scratch dir path.
    """
    res = {}
    for label, argv in (('bash', BASH), ('psh', PSH)):
        with tempfile.TemporaryDirectory(dir=os.path.join(REPO, 'tmp')) as d:
            hf = os.path.join(d, 'hist')
            with open(hf, 'w') as f:
                if seed:
                    f.write(''.join(line + '\n' for line in seed))
            for base, contents in (named_seed or {}).items():
                with open(os.path.join(d, base), 'w') as f:
                    f.write(''.join(line + '\n' for line in contents))
            out = _run(argv, script.replace('$OTHER', d), hf, extra_env,
                       histignore)
            after = []
            if os.path.exists(hf):
                with open(hf) as f:
                    after = [ln.rstrip('\n') for ln in f if ln.strip()]
        res[label] = (_parse(out), after)
    return res


# The standard observation tail: dump the in-memory listing and the on-disk
# file at the point it is inserted.
def observe(tag='STATE'):
    return (f'echo ==={tag}_MEM===\n'
            'history\n'
            f'echo ==={tag}_FILE===\n'
            'cat "$HISTFILE"\n')


def report(name, script, res, sections, note=''):
    """Print a cell's psh-vs-bash comparison over the named *sections*."""
    print(f"\n--- {name} ---")
    if note:
        print(f"    ({note})")
    diverged = False
    for sec in sections:
        b = res['bash'][0].get(sec, [])
        p = res['psh'][0].get(sec, [])
        if sec.endswith('_MEM'):
            b, p = _listing(b), _listing(p)
        mark = ' ' if b == p else '*'
        print(f"  {mark}{sec:16s} bash={b}")
        print(f"   {'':16s} psh ={p}")
        if b != p:
            diverged = True
    b, p = res['bash'][1], res['psh'][1]
    mark = ' ' if b == p else '*'
    print(f"  {mark}{'FILE_AFTER_EXIT':16s} bash={b}")
    print(f"   {'':16s} psh ={p}")
    if b != p:
        diverged = True
    print(f"  => {'DIVERGES' if diverged else 'MATCHES'}")
    return diverged
