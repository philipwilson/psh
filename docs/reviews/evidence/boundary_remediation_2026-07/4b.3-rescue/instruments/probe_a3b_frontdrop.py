"""Phase A3b — the front-drop's effect on the READ counter, measured precisely.

A3 section 4 SATURATED: with a 6-marker instrument bash pulled nothing after
the `-s` stores, so all it proved was "counter >= 6".  Widened to 24 markers
here, and swept over the number of front-drops so the movement per drop is
visible rather than inferred from one point.

Also settles whether HISTIGNORE (as opposed to HISTCONTROL, which A3 showed
bash DOES apply to `-s`) filters a `-s` store.
"""
import hlib

hlib.header("A3b — front-drop vs the read counter; HISTIGNORE vs -s")

WIDE = [f'M{i}' for i in range(1, 25)]
READ_INSTR = ('printf "' + '\\n'.join(WIDE) + '\\n" > "$HISTFILE"\n'
              'history -n\n' + hlib.observe('R'))
APPEND_INSTR = ('printf "" > "$HISTFILE"\nhistory -a\n' + hlib.observe('A'))

SEED = ['seed1', 'seed2', 'seed3']


def counter(pre, post):
    pulled = post[len(pre):]
    for i in range(len(WIDE) + 1):
        if pulled == WIDE[i:]:
            return str(i), pulled
    return f"IRREGULAR({pulled})", pulled


print("\n########## HISTSIZE=4, seed=3 lines, sweeping the number of "
      "`-s` stores ##########")
print("(with a 4-entry cap and 3 seeded, the 2nd store is the first "
      "front-drop)\n")

for n in range(0, 5):
    ops = ''.join(f'history -s n{i}\n' for i in range(1, n + 1))
    r = hlib.run_cell(ops + hlib.observe('OP') + READ_INSTR + 'exit\n',
                      seed=SEED, extra_env={'HISTSIZE': '4'})
    a = hlib.run_cell(ops + hlib.observe('OP') + APPEND_INSTR + 'exit\n',
                      seed=SEED, extra_env={'HISTSIZE': '4'})
    print(f"--- {n} store(s) ---")
    for sh in ('bash', 'psh'):
        pre = hlib._listing(r[sh][0].get('OP_MEM', []))
        post = hlib._listing(r[sh][0].get('R_MEM', []))
        k, pulled = counter(pre, post)
        drops = max(0, (3 + n) - 4)
        print(f"   {sh:4s}: mem({len(pre)})={pre}")
        print(f"         front-drops={drops}  read-counter={k}  "
              f"append-slice={a[sh][0].get('A_FILE', [])}")
    print()

print("\n########## same sweep driven by NORMAL RECORDING "
      "(the established producer — control for the -s rows) ##########\n")
for n in (0, 2, 4):
    ops = ''.join(f'true r{i}\n' for i in range(1, n + 1))
    r = hlib.run_cell(ops + hlib.observe('OP') + READ_INSTR + 'exit\n',
                      seed=SEED, extra_env={'HISTSIZE': '4'})
    a = hlib.run_cell(ops + hlib.observe('OP') + APPEND_INSTR + 'exit\n',
                      seed=SEED, extra_env={'HISTSIZE': '4'})
    print(f"--- {n} recorded command(s) ---")
    for sh in ('bash', 'psh'):
        pre = hlib._listing(r[sh][0].get('OP_MEM', []))
        post = hlib._listing(r[sh][0].get('R_MEM', []))
        k, pulled = counter(pre, post)
        print(f"   {sh:4s}: mem({len(pre)})={pre}")
        print(f"         read-counter={k}  "
              f"append-slice={a[sh][0].get('A_FILE', [])}")
    print()

print("\n########## HISTIGNORE vs `history -s` "
      "(HISTCONTROL DOES apply per A3 — does HISTIGNORE?) ##########\n")

for name, hi, op in (
        ("HISTIGNORE='s*', -s s1",
         's*:history*:echo ===*:cat *:wc *:exit:printf *', 'history -s s1\n'),
        ("HISTIGNORE='ign*', -s ignored + -s kept",
         'ign*:history*:echo ===*:cat *:wc *:exit:printf *',
         'history -s ignoreme\nhistory -s kept\n'),
):
    res = hlib.run_cell(op + hlib.observe('OP') + 'exit\n', histignore=hi)
    b = hlib._listing(res['bash'][0].get('OP_MEM', []))
    p = hlib._listing(res['psh'][0].get('OP_MEM', []))
    print(f"--- {name} ---")
    print(f"   bash={b}")
    print(f"   psh ={p}")
    print(f"  => {'MATCHES' if b == p else 'DIVERGES'}\n")
