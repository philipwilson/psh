"""Matrix H6 — untriggered conditional returns the VIEW, not an empty scalar.

The integrator's ruled 19-cell model (R2.3) plus the POSITIONAL twin it asked
for: `set -- ""` is the untested sibling of `a=("")`. If any cell here
contradicts the model, that is a stop-and-propose, not a cell to fit.
"""
import sys

from batch import run_matrix
from harness import header

STATES = [
    ('unset',    'unset a;'),
    ('empty',    'a=();'),
    ('onenull',  'a=("");'),     # THE cell that separates view-from-scalar
    ('twonull',  'a=("" "");'),  # joins to " " -> non-null -> DOES fire
    ('one',      'a=(z);'),
    ('two',      'a=(z w);'),
]
POS_STATES = [
    ('p-none',   'set --;'),
    ('p-onenull', 'set -- "";'),   # the positional twin of a=("")
    ('p-twonull', 'set -- "" "";'),
    ('p-one',    'set -- z;'),
]


def cells():
    out = []
    for sid, setup in STATES:
        for sub in ('@', '*'):
            for op in (':+', '+', ':-', '-'):
                expr = '${a[' + sub + ']' + op + 'X}'
                for oid, wrap in (('Q', '"%s"'), ('U', '%s')):
                    out.append((f'H6-{sid}-{sub}-{op.replace(":", "c")}-{oid}',
                                f'{setup} count {wrap % expr}'))
    # Positional twin: ${@:+X} / ${*:+X} over the same states.
    for sid, setup in POS_STATES:
        for param in ('@', '*'):
            for op in (':+', '+', ':-', '-'):
                expr = '${' + param + op + 'X}'
                for oid, wrap in (('Q', '"%s"'), ('U', '%s')):
                    out.append((f'H6-{sid}-{param}-{op.replace(":", "c")}-{oid}',
                                f'{setup} count {wrap % expr}'))
    # Scalar control: already-agreeing rows must stay agreeing.
    for sid, setup in (('s-unset', 'unset x;'), ('s-null', 'x=;'),
                       ('s-set', 'x=S;')):
        for op in (':+', '+', ':-', '-'):
            expr = '${x' + op + 'X}'
            for oid, wrap in (('Q', '"%s"'), ('U', '%s')):
                out.append((f'H6-{sid}-{op.replace(":", "c")}-{oid}',
                            f'{setup} count {wrap % expr}'))
    return out


if __name__ == '__main__':
    header(sys.stdout, tree_note='Matrix H6 (untriggered conditional = the VIEW)')
    run_matrix(cells(), 'MATRIX-H6-UNTRIGGERED-VIEW', sys.stdout)
