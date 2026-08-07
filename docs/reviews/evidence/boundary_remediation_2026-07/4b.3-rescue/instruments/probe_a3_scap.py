"""Phase A3 — `history -s` and the HISTSIZE cap: WHERE it applies, and what a
front-drop does to BOTH markers.

The cap's marker maintenance is the part that can recreate the v0.447
regression under a new producer: `add_to_history`'s trim shifts
`_file_synced_len` when it drops from the front, so a `-s` cap must do the
same — and what it must do to the READ cursor has to come from bash, not from
symmetry arguments.
"""
import hlib

hlib.header("A3 — `-s` cap semantics (psh vs bash 5.2.26)")

# HISTIGNORE blocks the probe's own `history …` invocations from being
# RECORDED (leg-B shape), so add_to_history's own trim can never mask the
# store.  `-s`'s store bypasses HISTIGNORE in both shells (A1c control).
S5 = ''.join(f'history -s s{i}\n' for i in range(1, 6))


def cell(name, script, env, note='', seed=None, sections=('OP_MEM',)):
    res = hlib.run_cell(script, seed=seed, extra_env=env)
    print(f"--- {name} ---")
    if note:
        print(f"    ({note})")
    div = False
    for sec in sections:
        b = hlib._listing(res['bash'][0].get(sec, []))
        p = hlib._listing(res['psh'][0].get(sec, []))
        mark = ' ' if b == p else '*'
        print(f"  {mark}{sec:12s} bash={b}")
        print(f"   {'':12s} psh ={p}")
        div |= (b != p)
    print(f"  => {'DIVERGES' if div else 'MATCHES'}\n")
    return res


print("\n########## 1. WHERE is the cap applied? ##########\n")

cell("HISTSIZE=3, 5x -s, list",
     S5 + hlib.observe('OP') + 'exit\n', {'HISTSIZE': '3'},
     'the leg-B shape: cap visible in the listing?')

cell("HISTSIZE=3, 5x -s, RAISE to 10, list",
     S5 + 'HISTSIZE=10\n' + hlib.observe('OP') + 'exit\n', {'HISTSIZE': '3'},
     'if entries survive the raise the trim was at LISTING, not at STORE')

cell("HISTSIZE=3, 2x -s then a RECORDED command",
     'history -s s1\nhistory -s s2\ntrue RECORDED\n'
     + hlib.observe('OP') + 'exit\n', {'HISTSIZE': '3'},
     'does the cap fire at store, or only at the next record?')

cell("HISTSIZE=3, 4x -s, no other op",
     ''.join(f'history -s s{i}\n' for i in range(1, 5))
     + hlib.observe('OP') + 'exit\n', {'HISTSIZE': '3'},
     'first store PAST the cap')

print("\n########## 2. -s argument joining and HISTCONTROL ##########\n")

cell("-s multiple args", 'history -s echo hello world\n'
     + hlib.observe('OP') + 'exit\n', {}, 'one joined entry?')

cell("-s under ignoredups",
     'history -s dup\nhistory -s dup\n' + hlib.observe('OP') + 'exit\n',
     {'HISTCONTROL': 'ignoredups'}, 'does HISTCONTROL apply to -s?')

cell("-s under erasedups",
     'history -s aaa\nhistory -s bbb\nhistory -s aaa\n'
     + hlib.observe('OP') + 'exit\n',
     {'HISTCONTROL': 'erasedups'}, 'does erasedups apply to -s?')

cell("-s leading space under ignorespace",
     'history -s " spaced"\n' + hlib.observe('OP') + 'exit\n',
     {'HISTCONTROL': 'ignorespace'}, 'does ignorespace apply to -s?')

print("\n########## 3. HISTSIZE edge values ##########\n")

cell("HISTSIZE=0, 3x -s",
     ''.join(f'history -s s{i}\n' for i in range(1, 4))
     + hlib.observe('OP') + 'exit\n', {'HISTSIZE': '0'}, 'zero cap')

cell("HISTSIZE=-1, 5x -s", S5 + hlib.observe('OP') + 'exit\n',
     {'HISTSIZE': '-1'}, 'negative = unlimited (psh must-hold unless bash says no)')

cell("HISTSIZE=1, 3x -s",
     ''.join(f'history -s s{i}\n' for i in range(1, 4))
     + hlib.observe('OP') + 'exit\n', {'HISTSIZE': '1'}, 'cap of one')

print("\n########## 4. front-drop marker maintenance "
      "(the v0.447 face under a NEW producer) ##########\n")

# Seed 3 lines so both markers start at 3, then force the cap to drop from the
# front with -s stores.  Read counter measured by the A1b instrument; append
# slice by truncate-then-`-a`.
MARKERS = [f'M{i}' for i in range(1, 7)]
READ_INSTR = ('printf "' + '\\n'.join(MARKERS) + '\\n" > "$HISTFILE"\n'
              'history -n\n' + hlib.observe('R'))
APPEND_INSTR = ('printf "" > "$HISTFILE"\nhistory -a\n' + hlib.observe('A'))

for label, ops in (
        ("HISTSIZE=4, seed3 + 3x -s (drops 2 from front)",
         'history -s n1\nhistory -s n2\nhistory -s n3\n'),
        ("HISTSIZE=3, seed3 + 2x -s (drops 2 from front)",
         'history -s n1\nhistory -s n2\n'),
):
    hs = label.split('=')[1].split(',')[0]
    r = hlib.run_cell(ops + hlib.observe('OP') + READ_INSTR + 'exit\n',
                      seed=['seed1', 'seed2', 'seed3'],
                      extra_env={'HISTSIZE': hs})
    a = hlib.run_cell(ops + hlib.observe('OP') + APPEND_INSTR + 'exit\n',
                      seed=['seed1', 'seed2', 'seed3'],
                      extra_env={'HISTSIZE': hs})
    print(f"--- {label} ---")
    for sh in ('bash', 'psh'):
        pre = hlib._listing(r[sh][0].get('OP_MEM', []))
        post = hlib._listing(r[sh][0].get('R_MEM', []))
        pulled = post[len(pre):]
        k = next((str(i) for i in range(len(MARKERS) + 1)
                  if pulled == MARKERS[i:]), f"IRREGULAR {pulled}")
        print(f"   {sh:4s}: mem={pre}")
        print(f"         read counter={k}  (pulled {pulled})")
        print(f"         append slice={a[sh][0].get('A_FILE', [])}")
    print()
