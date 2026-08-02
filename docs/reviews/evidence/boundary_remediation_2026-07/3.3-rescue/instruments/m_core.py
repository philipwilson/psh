"""Matrix A — core: operator x subject-state x outer-quoting x operand-content.

Observer = field counter (n=<count> then [text] per field), so zero-fields and
one-empty-field are distinguishable.
"""
import sys
import time

from batch import run_matrix
from harness import header

SETUP = 'set -- a b; a=(p q); unset y;'

SUBJECTS = [
    ('uns', 'unset x;'),      # unset
    ('nul', 'x=;'),           # set but null
    ('set', 'x=S;'),          # set non-empty
]

# Value-operator families. ':?'/'?' get their own matrix (stderr wording).
OPERATORS = [':-', '-', ':+', '+', ':=', '=']

# Operand content axis. Ids are stable across matrices.
CONTENTS = [
    ('dqat',      '"$@"'),
    ('bareat',    '$@'),
    ('dqstar',    '"$*"'),
    ('barestar',  '$*'),
    ('arrat',     '"${a[@]}"'),
    ('barearrat', '${a[@]}'),
    ('arrstar',   '"${a[*]}"'),
    ('cmdsub',    '$(echo p q)'),
    ('dqcmdsub',  '"$(echo p q)"'),
    ('nested',    '${y:-"$@"}'),
    ('emptydq',   '""'),
    ('emptysq',   "''"),
    ('empty',     ''),
    ('mixed',     'pre"$@"post'),
    ('ansic',     "$'a\\tb'"),
    ('bslash',    'a\\ b'),
    ('sqsp',      "'a b'"),
    ('plain',     'a b'),
]

OUTER = [('Q', '"%s"'), ('U', '%s')]


def cells():
    out = []
    for op in OPERATORS:
        opid = op.replace(':', 'c')
        for sid, setup in SUBJECTS:
            for cid, content in CONTENTS:
                expr = '${x' + op + content + '}'
                for oid, wrap in OUTER:
                    out.append((
                        f'A-{opid}-{sid}-{cid}-{oid}',
                        f'{SETUP} {setup} count {wrap % expr}'))
    return out


if __name__ == '__main__':
    t0 = time.time()
    header(sys.stdout, tree_note='Matrix A (core operator/subject/outer/content)')
    rows = run_matrix(cells(), 'MATRIX-A-CORE', sys.stdout)
    print(f"\nelapsed: {time.time() - t0:.1f}s for {len(rows)} cells")
