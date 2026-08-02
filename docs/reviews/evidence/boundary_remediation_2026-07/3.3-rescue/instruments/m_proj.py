"""Matrix L — what SEPARATOR does a terminal scalar projection use?

If the operand result is a field vector, every terminal consumer must join it.
bash's separator choice is the thing the projection must reproduce: space, or
IFS[0], or something else. Varies IFS and the field source ($@ vs [@] vs [*]).
"""
import sys
import time

from batch import run_matrix
from harness import header


def cells():
    out = []
    ifss = [('dflt', ''), ('colon', 'IFS=:;'), ('empty', 'IFS=;'),
            ('multi', 'IFS=:-;'), ('tab', "IFS=$'\\t';")]
    # Terminal-scalar consumers from Matrix I, each observed verbatim.
    consumers = [
        ('assign',   'v=%s; count "$v"'),
        ('assignq',  'v="%s"; count "$v"'),
        ('declare',  'declare v=%s; count "$v"'),
        ('store',    ': ${x:="$@"}; count "$x"'),      # := store face
        ('case',     'case %s in "a b") echo SP;; "a:b") echo COLON;; "ab") echo NONE;; *) echo OTHER;; esac'),
        ('dbr',      '[[ %s == "a b" ]] && echo SP || { [[ %s == "a:b" ]] && echo COLON || echo OTHER; }'),
        ('hstr',     'cat <<< %s'),
        ('subkey',   'declare -A h; h[%s]=v; count "${!h[@]}"'),
    ]
    srcs = [('at', '"$@"'), ('bareat', '$@'), ('star', '"$*"'),
            ('arrat', '"${a[@]}"')]
    for iid, ifs in ifss:
        for cid, tmpl in consumers:
            for sid, src in srcs:
                if cid == 'store':
                    if sid != 'at':
                        continue
                    body = tmpl
                else:
                    expr = '${x:-' + src + '}'
                    n = tmpl.count('%s')
                    body = tmpl % ((expr,) * n)
                out.append((f'L-{iid}-{cid}-{sid}',
                            f'set -- a b; a=(a b); {ifs} unset x; {body}'))
    return out


if __name__ == '__main__':
    t0 = time.time()
    header(sys.stdout, tree_note='Matrix L (scalar projection separator)')
    rows = run_matrix(cells(), 'MATRIX-L-SCALAR-PROJECTION', sys.stdout)
    print(f"\nelapsed: {time.time() - t0:.1f}s for {len(rows)} cells")
