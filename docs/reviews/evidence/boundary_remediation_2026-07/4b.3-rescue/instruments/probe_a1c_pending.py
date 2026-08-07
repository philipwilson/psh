"""Phase A1c — does a READ make the read-in lines PENDING for a later `-a`?

A1 showed bash duplicating a line into the file (`-n` pulls EXT, then `-a`
writes EXT again) while A1b showed bash's `-a` writing NOTHING after a `-r`
re-read 3 lines.  That asymmetry decides the exit criterion's last clause
("without duplicate file lines"), so it gets its own instrument.

Also fixes a NON-DISCRIMINATING cell in A1b: its `-n NAMED` case read from
offset 3 into a 2-line named file and therefore pulled NOTHING, so its empty
append slice proved nothing.  Here every read cell is forced to actually pull
lines (named file seeded with 5), and each cell PRINTS what it pulled so a
vacuous cell is visible rather than silently counted.

Measurement: after the read, truncate $HISTFILE to empty and run `history -a`.
The file then contains exactly the entries the append marker still considers
pending.
"""
import hlib

hlib.header("A1c — pending-for-append after a read (psh vs bash 5.2.26)")

SEED = ['seed1', 'seed2', 'seed3']
NAMED5 = {'other': ['oth1', 'oth2', 'oth3', 'oth4', 'oth5']}

TAIL = ('printf "" > "$HISTFILE"\n'
        'history -a\n' + hlib.observe('A'))

CELLS = [
    ("-r default (re-reads 3)", 'history -r\n'),
    ("-n default (pulls EXT)",
     'printf "EXT\\n" >> "$HISTFILE"\nhistory -n\n'),
    ("-n default (pulls EXT1,EXT2)",
     'printf "EXT1\\nEXT2\\n" >> "$HISTFILE"\nhistory -n\n'),
    ("-r NAMED (reads 5)", 'history -r $OTHER/other\n'),
    ("-n NAMED (offset 3 of 5 -> pulls oth4,oth5)",
     'history -n $OTHER/other\n'),
    ("recording (control: IS pending)", 'true RECORDED\n'),
    ("-s (control: IS pending)", 'history -s STORED\n'),
]

for name, op in CELLS:
    script = hlib.observe('PRE') + op + hlib.observe('OP') + TAIL + 'exit\n'
    res = hlib.run_cell(script, seed=SEED, named_seed=NAMED5)
    print(f"--- {name} ---")
    vacuous = []
    for sh in ('bash', 'psh'):
        pre = hlib._listing(res[sh][0].get('PRE_MEM', []))
        post = hlib._listing(res[sh][0].get('OP_MEM', []))
        pulled = post[len(pre):]
        pending = res[sh][0].get('A_FILE', [])
        if not pulled:
            vacuous.append(sh)
        print(f"   {sh:4s}: pulled-into-memory={pulled}")
        print(f"         pending-for-append ={pending}")
    b_pend = res['bash'][0].get('A_FILE', [])
    p_pend = res['psh'][0].get('A_FILE', [])
    verdict = 'MATCHES' if b_pend == p_pend else 'DIVERGES'
    if vacuous:
        verdict += f"  [NON-DISCRIMINATING for {vacuous}: nothing pulled]"
    print(f"  => {verdict}\n")
