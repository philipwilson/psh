"""Phase A3c — front-drop vs the READ counter, with the A3b instrument DEFECT
corrected.

INSTRUMENT DEFECT (self-disclosed, A3 §4 and A3b): the read-counter instrument
derives the counter from `post_mem[len(pre_mem):]`.  That identity only holds
while nothing trims the list.  Under a small HISTSIZE the 24-marker pull is
itself trimmed, so `post` is the TAIL of the list, `post[len(pre):]` is garbage,
and bash's counter was misreported as 23/24 (and as ">=6" in A3 §4).  Both
those columns are VOID.  (The A1/A1b/A1c measurements ran at the DEFAULT
HISTSIZE, where no trim fires — those remain valid.)

Correction: raise HISTSIZE to 500 immediately BEFORE the marker write, so the
pull cannot be trimmed, and HISTIGNORE the raise so it is not itself recorded.
Raising the cap does not move either counter (verified by the control below,
which measures a known-3 counter through the raised-cap instrument and must
still read 3).
"""
import hlib

hlib.header("A3c — front-drop vs read counter (A3b instrument defect fixed)")

WIDE = [f'M{i}' for i in range(1, 25)]
HI = 'history*:echo ===*:cat *:wc *:exit:printf *:HISTSIZE=*'

READ_INSTR = ('HISTSIZE=500\n'
              'printf "' + '\\n'.join(WIDE) + '\\n" > "$HISTFILE"\n'
              'history -n\n' + hlib.observe('R'))
APPEND_INSTR = ('printf "" > "$HISTFILE"\nhistory -a\n' + hlib.observe('A'))
SEED = ['seed1', 'seed2', 'seed3']


def counter(pre, post):
    pulled = post[len(pre):]
    for i in range(len(WIDE) + 1):
        if pulled == WIDE[i:]:
            return str(i)
    return f"IRREGULAR(pre={pre} pulled={pulled})"


def sweep(title, mk_ops, histsize, seed=SEED):
    print(f"\n########## {title} ##########\n")
    for n in (0, 1, 2, 3, 4):
        ops = mk_ops(n)
        r = hlib.run_cell(ops + hlib.observe('OP') + READ_INSTR + 'exit\n',
                          seed=seed, extra_env={'HISTSIZE': histsize},
                          histignore=HI)
        a = hlib.run_cell(ops + hlib.observe('OP') + APPEND_INSTR + 'exit\n',
                          seed=seed, extra_env={'HISTSIZE': histsize},
                          histignore=HI)
        print(f"--- {n} op(s) ---")
        for sh in ('bash', 'psh'):
            pre = hlib._listing(r[sh][0].get('OP_MEM', []))
            post = hlib._listing(r[sh][0].get('R_MEM', []))
            print(f"   {sh:4s}: mem({len(pre)})={pre}")
            print(f"         read-counter={counter(pre, post)}  "
                  f"append-slice={a[sh][0].get('A_FILE', [])}")
        print()


print("\n########## CONTROL: cap large enough that nothing trims — the "
      "instrument must read the known counter 3 ##########\n")
r = hlib.run_cell(hlib.observe('OP') + READ_INSTR + 'exit\n', seed=SEED,
                  extra_env={'HISTSIZE': '500'}, histignore=HI)
for sh in ('bash', 'psh'):
    pre = hlib._listing(r[sh][0].get('OP_MEM', []))
    post = hlib._listing(r[sh][0].get('R_MEM', []))
    print(f"   {sh:4s}: read-counter={counter(pre, post)}   (expected 3)")

sweep("HISTSIZE=4, seed=3, sweeping `history -s` stores "
      "(2nd store = 1st front-drop)",
      lambda n: ''.join(f'history -s n{i}\n' for i in range(1, n + 1)), '4')

sweep("HISTSIZE=4, seed=3, sweeping NORMAL RECORDING (established producer)",
      lambda n: ''.join(f'true r{i}\n' for i in range(1, n + 1)), '4')
