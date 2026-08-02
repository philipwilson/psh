"""Matrices B..F — the axes matrix A held fixed.

B  subject SHAPE (positionals with spaces/IFS chars/empties) — unmasks cells
   where a space-join + re-split coincidentally reproduces bash.
C  positional COUNT (0,1,2,3) and empty positionals.
D  ':=' STORE vs EMIT (observe $x after the expansion) — ruling (b).
E  ':?' / '?' message path.
F  IFS axis (default, empty, custom, IFS containing the joiner).
"""
import sys
import time

from batch import run_matrix
from harness import header

# ---------------------------------------------------------------- B: shape
SHAPES = [
    ('plain',   'set -- a b;'),
    ('space',   'set -- "a 1" b;'),          # embedded space in a positional
    ('bothsp',  'set -- "a 1" "b 2";'),
    ('emptyp',  'set -- "" b;'),             # explicit empty positional
    ('allempty', 'set -- "" "";'),
    ('tab',     'set -- "a\tz" b;'),          # embedded IFS tab
    ('colon',   'set -- "a:z" b;'),          # non-IFS char (matters under IFS=:)
    ('glob',    'set -- "a*" b;'),           # glob metachar: protection axis
]
B_OPS = [':-', '-', ':+', '+']
B_CONTENT = [('dqat', '"$@"'), ('bareat', '$@'), ('arrat', '"${a[@]}"')]


def b_cells():
    out = []
    for sh, setup in SHAPES:
        for op in B_OPS:
            subj = 'x=S;' if op in (':+', '+') else 'unset x;'
            for cid, content in B_CONTENT:
                if cid == 'arrat':
                    setup2 = setup.replace('set --', 'a=(') \
                        .replace(';', ');') if False else setup
                expr = '${x' + op + content + '}'
                for oid, wrap in (('Q', '"%s"'), ('U', '%s')):
                    out.append((f'B-{sh}-{op.replace(":", "c")}-{cid}-{oid}',
                                f'a=("a 1" b); {setup} {subj} count {wrap % expr}'))
    return out


# ---------------------------------------------------------------- C: count
def c_cells():
    out = []
    counts = [('n0', 'set --;'), ('n1', 'set -- a;'), ('n2', 'set -- a b;'),
              ('n3', 'set -- a b c;'), ('n1e', 'set -- "";'),
              ('n2e', 'set -- "" b;'), ('n3e', 'set -- a "" c;')]
    for cid, setup in counts:
        for op in (':-', ':+'):
            subj = 'x=S;' if op == ':+' else 'unset x;'
            for name, content in (('dqat', '"$@"'), ('bareat', '$@'),
                                  ('mixed', 'pre"$@"post'),
                                  ('dqstar', '"$*"')):
                expr = '${x' + op + content + '}'
                for oid, wrap in (('Q', '"%s"'), ('U', '%s')):
                    out.append((f'C-{cid}-{op.replace(":", "c")}-{name}-{oid}',
                                f'{setup} {subj} count {wrap % expr}'))
    return out


# ------------------------------------------------------- D: := store vs emit
def d_cells():
    """Observe BOTH what the expansion EMITS and what the variable STORES."""
    out = []
    contents = [('dqat', '"$@"'), ('bareat', '$@'), ('dqstar', '"$*"'),
                ('arrat', '"${a[@]}"'), ('sqsp', "'a b'"), ('bslash', 'a\\ b'),
                ('emptydq', '""'), ('mixed', 'pre"$@"post')]
    for op in (':=', '='):
        for cid, content in contents:
            expr = '${x' + op + content + '}'
            for oid, wrap in (('Q', '"%s"'), ('U', '%s')):
                base = f'set -- "a 1" b; a=(p "q 2"); unset x;'
                # EMIT face: what the expansion produces as fields.
                out.append((f'D-emit-{op.replace(":", "c")}-{cid}-{oid}',
                            f'{base} count {wrap % expr}'))
                # STORE face: what landed in x afterwards (quoted, so the
                # stored scalar is observed verbatim, unsplit).
                out.append((f'D-store-{op.replace(":", "c")}-{cid}-{oid}',
                            f'{base} : {wrap % expr}; count "$x"'))
    return out


# ------------------------------------------------------------- E: :? message
def e_cells():
    out = []
    for op in (':?', '?'):
        for cid, content in (('dqat', '"$@"'), ('bareat', '$@'),
                             ('sq', "'m sg'"), ('empty', '')):
            expr = '${x' + op + content + '}'
            for oid, wrap in (('Q', '"%s"'), ('U', '%s')):
                out.append((f'E-{op.replace(":", "c")}-{cid}-{oid}',
                            f'set -- a b; unset x; count {wrap % expr}'))
    return out


# ------------------------------------------------------------------- F: IFS
def f_cells():
    out = []
    ifss = [('dflt', ''), ('empty', 'IFS=;'), ('colon', 'IFS=:;'),
            ('sp', "IFS=' ';"), ('colonsp', "IFS=': ';")]
    for iid, ifs in ifss:
        for op in (':-', ':+'):
            subj = 'x=S;' if op == ':+' else 'unset x;'
            for cid, content in (('dqat', '"$@"'), ('bareat', '$@'),
                                 ('dqstar', '"$*"'), ('barestar', '$*'),
                                 ('sqsp', "'a b'"), ('plain', 'a b')):
                expr = '${x' + op + content + '}'
                for oid, wrap in (('Q', '"%s"'), ('U', '%s')):
                    out.append((f'F-{iid}-{op.replace(":", "c")}-{cid}-{oid}',
                                f'set -- a b; {ifs} {subj} count {wrap % expr}'))
    return out


if __name__ == '__main__':
    t0 = time.time()
    header(sys.stdout, tree_note='Matrices B-F (axes)')
    tot = 0
    for fn, title in ((b_cells, 'MATRIX-B-SUBJECT-SHAPE'),
                      (c_cells, 'MATRIX-C-POSITIONAL-COUNT'),
                      (d_cells, 'MATRIX-D-ASSIGN-STORE-VS-EMIT'),
                      (e_cells, 'MATRIX-E-QMARK'),
                      (f_cells, 'MATRIX-F-IFS')):
        rows = fn()
        tot += len(rows)
        run_matrix(rows, title, sys.stdout)
    print(f"\nelapsed: {time.time() - t0:.1f}s for {tot} cells")
