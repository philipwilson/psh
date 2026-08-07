"""Phase A4b — PRODUCER x HISTSIZE: which paths into the in-memory list respect
the cap?

A4 showed leg B converging in the plain spelling: psh's over-cap state is
transient because the NEXT recorded command runs `add_to_history`, whose trim
drags the list back to the cap.  So the cap question is really per-PRODUCER,
and `-s` is not the only producer that skips it — A3b's numbers hinted that
psh's `-n` pulled 21 lines into a HISTSIZE=4 list.

Producers: startup load, normal recording, `history -s`, `history -r`,
`history -n`.  Exit criterion clause under test: "respect memory limits".
"""
import hlib

hlib.header("A4b — producer x HISTSIZE cap (psh vs bash 5.2.26)")

HI = 'history*:echo ===*:cat *:wc *:exit:printf *'
BIGSEED = [f'L{i}' for i in range(1, 11)]      # 10 lines


BIG = {'big': [f'B{i}' for i in range(1, 11)]}


def cell(name, script, env, seed=None, note='', histignore=HI):
    res = hlib.run_cell(script + hlib.observe('OP') + 'exit\n', seed=seed,
                        extra_env=env, histignore=histignore, named_seed=BIG)
    b = hlib._listing(res['bash'][0].get('OP_MEM', []))
    p = hlib._listing(res['psh'][0].get('OP_MEM', []))
    cap = env.get('HISTSIZE', '?')
    print(f"--- {name} ---")
    if note:
        print(f"    ({note})")
    print(f"   HISTSIZE={cap}: bash={len(b)} entries {b}")
    print(f"                psh ={len(p)} entries {p}")
    over = (len(p) > int(cap)) if cap.isdigit() and int(cap) > 0 else False
    print(f"  => {'MATCHES' if b == p else 'DIVERGES'}"
          f"{'   [psh OVER CAP]' if over else ''}\n")


print("\n########## startup load (file longer than HISTSIZE) ##########\n")
cell("load 10 lines, HISTSIZE=4", '', {'HISTSIZE': '4'}, seed=BIGSEED,
     note='load_from_file trims in psh')

print("\n########## normal recording ##########\n")
cell("6 recorded commands, HISTSIZE=4",
     ''.join(f'true r{i}\n' for i in range(1, 7)), {'HISTSIZE': '4'},
     note='add_to_history trims in psh (the established producer)')

print("\n########## history -s ##########\n")
cell("6x -s, HISTSIZE=4", ''.join(f'history -s s{i}\n' for i in range(1, 7)),
     {'HISTSIZE': '4'}, note='store_entry: no cap in psh (leg B)')

print("\n########## history -r (whole file into memory) ##########\n")
cell("-r a 10-line file, HISTSIZE=4", 'history -r $OTHER/big\n',
     {'HISTSIZE': '4'}, note='read_history: extend() with no trim in psh')

print("\n########## history -n (unread tail into memory) ##########\n")
cell("-n after an external 10-line append, HISTSIZE=4",
     'printf "' + '\\n'.join(f'X{i}' for i in range(1, 11)) + '\\n"'
     ' >> "$HISTFILE"\nhistory -n\n',
     {'HISTSIZE': '4'}, seed=['seed1'],
     note='read_new_history: extend() with no trim in psh')

print("\n########## composed: -r past the cap then a recorded command "
      "(does the next record repair it?) ##########\n")
cell("-r 10 lines then 1 recorded command, HISTSIZE=4",
     'history -r $OTHER/big\ntrue AFTER\n', {'HISTSIZE': '4'},
     note='psh: add_to_history trims only ONE entry per call')

print("\n########## HISTSIZE lowered AFTER the entries exist ##########\n")
cell("10 recorded, then HISTSIZE=3, then list",
     ''.join(f'true r{i}\n' for i in range(1, 11)) + 'HISTSIZE=3\n',
     {'HISTSIZE': '50'}, note='does lowering the cap trim retroactively?',
     histignore='history*:echo ===*:cat *:wc *:exit:printf *:HISTSIZE=*')
