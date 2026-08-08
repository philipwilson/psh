"""Phase A1b — PRECISE measurement of the two counters, per op.

A1 showed every op "diverging", but on several distinct axes at once.  This
instrument measures each counter SEPARATELY and NUMERICALLY, and runs the two
measurements as INDEPENDENT executions so neither disturbs the other.

READ-COUNTER instrument: after the op, truncate-rewrite $HISTFILE to a known
6-marker set M1..M6, then `history -n`.  Whatever `-n` appends is M[k:], so the
counter is read directly off the FIRST marker that arrives:
    pulled M1..M6 -> counter 0      pulled M4..M6 -> counter 3
    pulled nothing -> counter >= 6  (widened to 12 if it saturates)

APPEND-MARKER instrument: after the op, truncate $HISTFILE to empty, then
`history -a`.  The file then holds exactly the slice the marker designates.

Both are content-based, so neither derives a counter from the operation whose
rule is under test.
"""
import hlib

hlib.header("A1b — precise counter measurement (psh vs bash 5.2.26)")

SEED = ['seed1', 'seed2', 'seed3']
MARKERS = [f'M{i}' for i in range(1, 7)]

READ_INSTRUMENT = (
    'printf "' + '\\n'.join(MARKERS) + '\\n" > "$HISTFILE"\n'
    'history -n\n' + hlib.observe('R'))

APPEND_INSTRUMENT = (
    'printf "" > "$HISTFILE"\n'
    'history -a\n' + hlib.observe('A'))

CELLS = [
    ("startup-load", SEED, ''),
    ("recording", SEED, 'true RECORDED\n'),
    ("-r default", SEED, 'history -r\n'),
    ("-r default x2", SEED, 'history -r\nhistory -r\n'),
    ("-n default (no-op)", SEED, 'history -n\n'),
    ("-a default", SEED, 'true NEWENTRY\nhistory -a\n'),
    ("-w default", SEED, 'true NEWENTRY\nhistory -w\n'),
    ("-c", SEED, 'history -c\n'),
    ("-d 1 (below cursor)", SEED, 'history -d 1\n'),
    ("-d 1-2 (span)", SEED, 'history -d 1-2\n'),
    ("-d 3 (at cursor)", SEED, 'history -d 3\n'),
    ("-s", SEED, 'history -s STORED\n'),
    ("-r NAMED", SEED, 'history -r $OTHER/other\n'),
    ("-n NAMED", SEED, 'history -n $OTHER/other\n'),
    ("-a NAMED", SEED, 'true NEWENTRY\nhistory -a $OTHER/other\n'),
    ("-w NAMED", SEED, 'true NEWENTRY\nhistory -w $OTHER/other\n'),
    # external shrink: the file loses lines under the cursor (underflow face)
    ("external-truncate", SEED,
     'printf "only1\\n" > "$HISTFILE"\n'),
]

NAMED_SEED = {'other': ['oth1', 'oth2']}


def read_counter(pre_mem, post_mem):
    """Counter k such that the newly-appended entries are MARKERS[k:]."""
    pulled = post_mem[len(pre_mem):]
    if not pulled:
        return ">=6 (nothing pulled)", pulled
    if pulled == MARKERS:
        return "0", pulled
    for k in range(len(MARKERS) + 1):
        if pulled == MARKERS[k:]:
            return str(k), pulled
    return "IRREGULAR", pulled


print("\nColumns: read counter (position in the DEFAULT file that `-n` "
      "resumes from) | append slice (what `-a` writes)\n")
rows = []
for name, seed, op in CELLS:
    r = hlib.run_cell(op + hlib.observe('OP') + READ_INSTRUMENT + 'exit\n',
                      seed=seed, named_seed=NAMED_SEED)
    a = hlib.run_cell(op + hlib.observe('OP') + APPEND_INSTRUMENT + 'exit\n',
                      seed=seed, named_seed=NAMED_SEED)
    row = {'name': name}
    for sh in ('bash', 'psh'):
        pre = hlib._listing(r[sh][0].get('OP_MEM', []))
        post = hlib._listing(r[sh][0].get('R_MEM', []))
        k, pulled = read_counter(pre, post)
        row[f'{sh}_read'] = k
        row[f'{sh}_pulled'] = pulled
        row[f'{sh}_append'] = a[sh][0].get('A_FILE', [])
        row[f'{sh}_mem'] = hlib._listing(a[sh][0].get('OP_MEM', []))
    rows.append(row)
    same_r = row['bash_read'] == row['psh_read']
    same_a = row['bash_append'] == row['psh_append']
    print(f"--- {name} ---")
    print(f"   mem after op : bash={row['bash_mem']}")
    print(f"                  psh ={row['psh_mem']}")
    print(f"  {'' if same_r else '*'}read counter : bash={row['bash_read']:<20} "
          f"psh={row['psh_read']}")
    print(f"     pulled     : bash={row['bash_pulled']}")
    print(f"                  psh ={row['psh_pulled']}")
    print(f"  {'' if same_a else '*'}append slice : bash={row['bash_append']}")
    print(f"                  psh ={row['psh_append']}")
    print()

print("\n" + "=" * 72)
print("SUMMARY — read counter (bash | psh) and append slice agreement")
print("=" * 72)
for row in rows:
    rd = "OK " if row['bash_read'] == row['psh_read'] else "DIV"
    ap = "OK " if row['bash_append'] == row['psh_append'] else "DIV"
    print(f"  read={rd} append={ap}  {row['name']:<24} "
          f"bash_read={row['bash_read']:<20} psh_read={row['psh_read']}")
