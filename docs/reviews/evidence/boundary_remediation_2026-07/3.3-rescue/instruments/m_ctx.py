"""Matrices G..K — context grammar, array views, terminal consumers, backslash,
parser axis.

G  outer CONTEXT GRAMMAR: heredoc body, $(( )), [[ ]] operand, case word,
   here-string, redirect target, assignment RHS, array init, declaration.
H  ARRAY VIEWS: ${a[@]:-op} / ${a[*]:-op} — the variable.py joiner path.
I  TERMINAL CONSUMERS: sites where bash itself demands ONE string.
J  BACKSLASH axis inside operands (3.1 lesson).
K  parser axis (rd vs combinator) on the signature family.
"""
import sys
import time

from batch import run_matrix
from harness import header

# ------------------------------------------------------- G: context grammar
def g_cells():
    base = 'set -- a b; a=(p q); unset x;'
    out = [
        # Heredoc body (DQ_STRING context): field structure is irrelevant
        # inside a heredoc (it is one string) — probe what the TEXT is.
        ('G-heredoc', f'{base} cat <<EOF\n[${{x:-"$@"}}]\nEOF'),
        ('G-heredoc-star', f'{base} cat <<EOF\n[${{x:-"$*"}}]\nEOF'),
        # Here-string: one word, no splitting.
        ('G-herestring', f'{base} cat <<< "${{x:-"$@"}}"'),
        ('G-herestring-u', f'{base} cat <<< ${{x:-"$@"}}'),
        # Arithmetic context (DQ_STRING).
        ('G-arith', f'set -- 1 2; unset x; echo $(( ${{x:-3}} + 1 ))'),
        # [[ ]] operand (DQ_STRING): no field splitting inside [[ ]].
        ('G-dbracket', f'{base} [[ "${{x:-"$@"}}" == "a b" ]] && echo yes || echo no'),
        ('G-dbracket-u', f'{base} [[ ${{x:-"$@"}} == "a b" ]] && echo yes || echo no'),
        # case word: no splitting.
        ('G-case', f'{base} case ${{x:-"$@"}} in "a b") echo joined;; a) echo first;; *) echo other;; esac'),
        ('G-case-q', f'{base} case "${{x:-"$@"}}" in "a b") echo joined;; *) echo other;; esac'),
        # Assignment RHS: one string (no splitting).
        ('G-assign', f'{base} v=${{x:-"$@"}}; count "$v"'),
        ('G-assign-q', f'{base} v="${{x:-"$@"}}"; count "$v"'),
        # declare/export values.
        ('G-declare', f'{base} declare v=${{x:-"$@"}}; count "$v"'),
        ('G-export', f'{base} export v=${{x:-"$@"}}; count "$v"'),
        ('G-local', f'{base} f() {{ local v=${{x:-"$@"}}; count "$v"; }}; f'),
        # Array initializer element (splits).
        ('G-arrinit', f'{base} b=(${{x:-"$@"}}); count "${{b[@]}}"'),
        ('G-arrinit-q', f'{base} b=("${{x:-"$@"}}"); count "${{b[@]}}"'),
        # Assoc init element (no split).
        ('G-assoc', f'{base} declare -A h; h=(${{x:-"$@"}} v); count "${{!h[@]}}"'),
        # Redirect target (must be ONE word — bash errors on multiple).
        ('G-redir', f'cd "$(mktemp -d)"; {base} echo hi > ${{x:-"$@"}}; ls | count $(cat)'),
        # for-loop item list (splits like command args).
        ('G-for', f'{base} for i in ${{x:-"$@"}}; do printf "[%s]" "$i"; done; echo'),
        ('G-for-q', f'{base} for i in "${{x:-"$@"}}"; do printf "[%s]" "$i"; done; echo'),
        # Array subscript operand.
        ('G-subscript', f'set -- 1 2; a=(z y x); unset q; count "${{a[${{q:-1}}]}}"'),
        # ${v/pat/repl} operands reaching the (frozen) pattern engine.
        ('G-patop', f'{base} v'
                    f'=aXb; count "${{v/${{x:-X}}/Y}}"'),
        ('G-replop', f'{base} v=aXb; count "${{v/X/${{x:-"$@"}}}}"'),
        # printf/echo argument (plain command argument, splits).
        ('G-cmdarg', f'{base} count ${{x:-"$@"}}'),
    ]
    return out


# ------------------------------------------------------------ H: array views
def h_cells():
    out = []
    subs = [('at', '@'), ('star', '*')]
    states = [('unset', 'unset a;'), ('empty', 'a=();'),
              ('one', 'a=(z);'), ('onenull', 'a=("");'),
              ('twonull', 'a=("" "");'), ('two', 'a=(z w);')]
    contents = [('dqat', '"$@"'), ('bareat', '$@'), ('sqsp', "'p q'"),
                ('dqstar', '"$*"'), ('emptydq', '""'), ('plain', 'p q')]
    for sid, sub in subs:
        for stid, setup in states:
            for op in (':-', ':+', '-', '+'):
                for cid, content in contents:
                    expr = '${a[' + sub + ']' + op + content + '}'
                    for oid, wrap in (('Q', '"%s"'), ('U', '%s')):
                        out.append((
                            f'H-{sid}-{stid}-{op.replace(":", "c")}-{cid}-{oid}',
                            f'set -- a b; {setup} count {wrap % expr}'))
    return out


# ------------------------------------------------------- I: terminal consumers
def i_cells():
    """Sites where bash demands ONE string: does a multi-field operand join?"""
    base = 'set -- a b; unset x;'
    return [
        ('I-assign-scalar',  f'{base} v=${{x:-"$@"}}; count "$v"'),
        ('I-assign-append',  f'{base} v=pre; v+=${{x:-"$@"}}; count "$v"'),
        ('I-arrelem',        f'{base} declare -a b; b[0]=${{x:-"$@"}}; count "${{b[0]}}"'),
        ('I-assockey',       f'{base} declare -A h; h[${{x:-"$@"}}]=v; count "${{!h[@]}}"'),
        ('I-assocval',       f'{base} declare -A h; h[k]=${{x:-"$@"}}; count "${{h[k]}}"'),
        ('I-casesel',        f'{base} case ${{x:-"$@"}} in "a b") echo one;; *) echo other;; esac'),
        ('I-dbracket-lhs',   f'{base} [[ ${{x:-"$@"}} == "a b" ]] && echo eq || echo ne'),
        ('I-dbracket-rhs',   f'{base} [[ "a b" == ${{x:-"$@"}} ]] && echo eq || echo ne'),
        ('I-redirtarget',    f'cd "$(mktemp -d)"; {base} echo hi > ${{x:-"$@"}} 2>&1; ls -1 | count $(cat -)'),
        ('I-subscript',      f'{base} a=(z y w); count "${{a[${{x:-"$@"}}]}}" 2>&1'),
        ('I-arith',          f'{base} y=2; echo $(( ${{x:-1}} + y ))'),
        ('I-patternop',      f'{base} v="a b c"; count "${{v#${{x:-"$@"}}}}"'),
        ('I-replop',         f'{base} v=Q; count "${{v/Q/${{x:-"$@"}}}}"'),
        ('I-herestring',     f'{base} cat <<< ${{x:-"$@"}}'),
        ('I-export',         f'{base} export EV=${{x:-"$@"}}; count "$EV"'),
        ('I-declare',        f'{base} declare dv=${{x:-"$@"}}; count "$dv"'),
        ('I-readonly',       f'{base} readonly rv=${{x:-"$@"}}; count "$rv"'),
        ('I-assign-store',   f'{base} : ${{x:="$@"}}; count "$x"'),
        ('I-qmark-msg',      f'{base} ( : ${{x:?"$@"}} ) 2>&1 | sed "s/^[^:]*: //"'),
        ('I-funcarg',        f'{base} f() {{ count "$@"; }}; f ${{x:-"$@"}}'),
        ('I-exportname',     f'{base} count "${{x:-"$@"}}"'),
    ]


# ----------------------------------------------------------------- J: backslash
def j_cells():
    out = []
    contents = [
        ('bs-space',  'a\\ b'),
        ('bs-dollar', '\\$@'),
        ('bs-quote',  '\\"$@\\"'),
        ('bs-bs',     'a\\\\b'),
        ('bs-star',   'a\\*b'),
        ('bs-in-dq',  '"a\\ b"'),
        ('bs-at-dq',  '"\\$@"'),
        ('bs-nl',     'a\\\nb'),
        ('dq-bs-at',  '"pre\\"$@\\"post"'),
    ]
    for op in (':-', ':+'):
        subj = 'x=S;' if op == ':+' else 'unset x;'
        for cid, content in contents:
            expr = '${x' + op + content + '}'
            for oid, wrap in (('Q', '"%s"'), ('U', '%s')):
                out.append((f'J-{op.replace(":", "c")}-{cid}-{oid}',
                            f'set -- a b; {subj} count {wrap % expr}'))
    return out


# -------------------------------------------------------------- K: parser axis
K_CELLS = [
    ('K-sig-q',   'unset x; set -- a b; count "${x:-"$@"}"'),
    ('K-sig-u',   'unset x; set -- a b; count ${x:-"$@"}'),
    ('K-sig-plus', 'x=S; set -- a b; count "${x:+"$@"}"'),
    ('K-sig-sp',  'unset x; set -- "a 1" b; count "${x:-"$@"}"'),
    ('K-n0',      'unset x; set --; count ${x:-"$@"}'),
    ('K-mixed',   'unset x; set -- a b; count "${x:-pre"$@"post}"'),
    ('K-arr',     'unset x; a=(p q); count "${x:-"${a[@]}"}"'),
    ('K-nested',  'unset x; unset y; set -- a b; count "${x:-${y:-"$@"}}"'),
]


if __name__ == '__main__':
    t0 = time.time()
    header(sys.stdout, tree_note='Matrices G-K (context grammar, arrays, '
                                 'terminal consumers, backslash, parser)')
    tot = 0
    for fn, title in ((g_cells, 'MATRIX-G-CONTEXT-GRAMMAR'),
                      (h_cells, 'MATRIX-H-ARRAY-VIEWS'),
                      (i_cells, 'MATRIX-I-TERMINAL-CONSUMERS'),
                      (j_cells, 'MATRIX-J-BACKSLASH')):
        rows = fn()
        tot += len(rows)
        run_matrix(rows, title, sys.stdout)
    for parser in ('rd', 'combinator'):
        tot += len(K_CELLS)
        run_matrix(K_CELLS, f'MATRIX-K-PARSER-{parser}', sys.stdout,
                   parser=parser)
    print(f"\nelapsed: {time.time() - t0:.1f}s for {tot} cells")
