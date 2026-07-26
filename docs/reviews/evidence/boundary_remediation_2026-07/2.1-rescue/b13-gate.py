"""Hard gate for the prefixed-assignment de-dup: USER-FACING base<=tip check.

Measures at the level a user sees — the CLI summary text of --validate /
--lint / --security / --metrics — not raw issue objects (round-3 B6 lesson:
the property users experience is the one to check).

Corpus: {bare, export, local, readonly, declare, concat, dquoted} x
{plain $y, $(), backtick, arith, nested backtick-in-$()} x 4 modes.
Writes JSON {case: {mode: [summary lines]}} for multiset diffing.
"""
import json
import os
import subprocess
import sys

ROOT = os.getcwd()
OUT = sys.argv[1]

VALUES = [
    ('plain', '$y'),
    ('modern', '$(echo $y)'),
    ('backtick', '`echo $y`'),
    ('arith', '$(($y + 1))'),
    ('nested', '$(echo `echo $y`)'),
]
FORMS = [
    ('bare', 'FOO={v}'),
    ('export', 'export FOO={v}'),
    ('local', 'fn() {{ local FOO={v}; }}; fn'),
    ('readonly', 'readonly FOO={v}'),
    ('declare', 'declare FOO={v}'),
    ('concat', 'FOO=a{v}b'),
    ('dquoted', 'FOO="{v}"'),
    ('export-at', 'export FOO=$@'),
    ('bare-at', 'FOO=$@'),
]
MODES = ['--validate', '--lint', '--security', '--metrics']


def run(mode, src):
    r = subprocess.run([sys.executable, '-m', 'psh', mode, '-c', src],
                       capture_output=True, text=True, timeout=60, cwd=ROOT)
    return [line.rstrip() for line in r.stdout.splitlines() if line.strip()]


dump = {'__tree__': ROOT}
for fname, ftpl in FORMS:
    for vname, vsrc in VALUES:
        src = ftpl.format(v=vsrc)
        if fname.endswith('-at'):
            src = ftpl.format(v='')
        key = f'{fname}:{vname}'
        dump[key] = {m: run(m, src) for m in MODES}
        if fname.endswith('-at'):
            break

with open(OUT, 'w') as f:
    json.dump(dump, f, indent=1, sort_keys=True)
print(f'dumped {len(dump)-1} cases from {ROOT}')
