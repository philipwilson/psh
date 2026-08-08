"""Phase A1 — the bash counter-model table, op by op.

For each op: what it does to (i) the in-memory list, (ii) the file, and
(iii) the READ counter.  The read counter has no spelling, so it is observed
by appending a known EXTERNAL line to $HISTFILE and running `history -n`:
whatever `-n` pulls in tells us where the counter stood.  If `-n` pulls ONLY
the external line, the counter was at the file's pre-append length; if it
pulls more, the counter was that many lines short (a re-read); if it pulls
nothing, the counter was at or past the end.

The APPEND (sync) marker is observed by a following `history -a` and reading
the file: whatever `-a` writes is the slice the marker designates.
"""
import hlib

hlib.header("A1 — per-op counter model (psh vs bash 5.2.26)")

SEED = ['seed1', 'seed2', 'seed3']

# After the op, probe the READ counter with an external append + `-n`,
# then probe the APPEND marker with `-a`.
PROBE = ('printf "EXT\\n" >> "$HISTFILE"\n'
         'history -n\n'
         + hlib.observe('AFTERN') +
         'history -a\n'
         + hlib.observe('AFTERA'))

CELLS = [
    # (name, seed, op-script, note)
    ("startup-load", SEED, '', 'baseline: what the startup load consumed'),
    ("recording", SEED, 'true RECORDED\n', 'a normally-recorded command'),
    ("-r default", SEED, 'history -r\n', 're-read of the DEFAULT file'),
    ("-r twice", SEED, 'history -r\nhistory -r\n', 'duplicates?'),
    ("-n default", SEED, 'history -n\n', 'no unread lines at start'),
    ("-n twice", SEED, 'history -n\nhistory -n\n', ''),
    ("-a default", SEED, 'true NEWENTRY\nhistory -a\n',
     'append marker: which entries land in the file'),
    ("-w default", SEED, 'true NEWENTRY\nhistory -w\n',
     'write whole list, truncating'),
    ("-c", SEED, 'history -c\n', 'clear: both markers?'),
    ("-d single", SEED, 'history -d 1\n', 'MEDIUM-7 leg A shape'),
    ("-d range", SEED, 'history -d 1-2\n', 'range delete'),
    ("-d last", SEED, 'history -d 3\n', 'delete ABOVE both cursors'),
    ("-s", SEED, 'history -s STORED\n', 'store without executing'),
]

NAMED = [
    ("-r NAMED", 'history -r $OTHER/other\n'),
    ("-n NAMED", 'history -n $OTHER/other\n'),
    ("-a NAMED", 'true NEWENTRY\nhistory -a $OTHER/other\n'),
    ("-w NAMED", 'true NEWENTRY\nhistory -w $OTHER/other\n'),
]

SECTIONS = ['AFTEROP_MEM', 'AFTEROP_FILE', 'AFTERN_MEM', 'AFTERN_FILE',
            'AFTERA_MEM', 'AFTERA_FILE']

diverging = []
for name, seed, op, note in CELLS:
    script = op + hlib.observe('AFTEROP') + PROBE + 'exit\n'
    res = hlib.run_cell(script, seed=seed)
    if hlib.report(name, script, res, SECTIONS, note):
        diverging.append(name)

print("\n\n########## NAMED-FILE VARIANTS "
      "(does the DEFAULT file's counter move?) ##########")
for name, op in NAMED:
    script = op + hlib.observe('AFTEROP') + PROBE + 'exit\n'
    res = hlib.run_cell(script, seed=SEED,
                        named_seed={'other': ['oth1', 'oth2']})
    if hlib.report(name, script, res, SECTIONS,
                   'named file seeded oth1,oth2; $HISTFILE seeded seed1..3'):
        diverging.append(name)

print(f"\n\nDIVERGING CELLS ({len(diverging)}): {diverging}")
