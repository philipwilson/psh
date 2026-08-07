"""Phase A2 — the STATE-MACHINE SEQUENCE battery (the exit criterion's own
words), with every cell forced to be DISCRIMINATING.

A1b already covered several of the brief's named sequences, but four of them
came out non-discriminating there because nothing was pending when `-a` ran
(`-d` then `-a`, `-c` then `-a`).  Those are re-run here with a genuinely
pending entry.  Each cell prints the full observable triple — in-memory list,
file mid-run, file after exit — so a vacuous cell is visible.
"""
import hlib

hlib.header("A2 — sequence battery (psh vs bash 5.2.26)")

SEED = ['seed1', 'seed2', 'seed3']
NAMED = {'other': ['oth1', 'oth2', 'oth3', 'oth4', 'oth5']}

CELLS = [
    # -- deletes composed with the file ops -----------------------------
    ("-d then -a (with a PENDING entry)",
     'true NEW\n'                       # pending
     'history -d 1\n'                   # delete an already-synced entry
     'history -a\n' + hlib.observe('END'),
     "does deleting a SYNCED entry corrupt the append slice?"),

    ("-d the PENDING entry then -a",
     'true NEW\n'
     'history -d 4\n'                   # delete the pending entry itself
     'history -a\n' + hlib.observe('END'),
     "delete ABOVE the sync marker"),

    ("-d range spanning the sync marker then -a",
     'true NEW\n'
     'history -d 3-4\n'                 # spans synced|pending boundary
     'history -a\n' + hlib.observe('END'),
     "the SPANNING face"),

    ("-d then exit-save",
     'true NEW\nhistory -d 1\n' + hlib.observe('END'),
     "exit save after a delete"),

    # -- clear composed ------------------------------------------------
    ("-c then -a (with a PENDING entry)",
     'true NEW\nhistory -c\nhistory -a\n' + hlib.observe('END'),
     "what does -a append after a clear?"),

    ("-c then -r",
     'history -c\nhistory -r\n' + hlib.observe('END'),
     "re-read after clear"),

    ("-c then -n (carry #32 / leg C)",
     'history -c\nhistory -n\n' + hlib.observe('END'),
     "the carry #32 shape"),

    ("-c then record then exit-save",
     'true BEFORE\nhistory -c\ntrue AFTER\n' + hlib.observe('END'),
     "post-clear commands must still persist (psh R14.B guard)"),

    # -- read/append interplay (the 'no duplicate file lines' clause) ---
    ("-n then -a (DUPLICATE face)",
     'printf "EXT\\n" >> "$HISTFILE"\n'
     'history -n\nhistory -a\n' + hlib.observe('END'),
     "bash re-appends what -n just read; psh does not"),

    ("-r then -a",
     'history -r\nhistory -a\n' + hlib.observe('END'),
     "control: -r's lines are NOT pending in either shell"),

    ("-n then exit-save (DUPLICATE face at exit)",
     'printf "EXT\\n" >> "$HISTFILE"\nhistory -n\n' + hlib.observe('END'),
     "same question on the exit route"),

    # -- named-file interplay ------------------------------------------
    ("-r NAMED then -a default",
     'history -r $OTHER/other\nhistory -a\n' + hlib.observe('END'),
     "do the OTHER file's lines leak into $HISTFILE?"),

    ("-w NAMED then exit-save",
     'true NEW\nhistory -w $OTHER/other\n' + hlib.observe('END'),
     "does -w to another file consume the pending slice?"),

    ("-a NAMED then -n default",
     'true NEW\nhistory -a $OTHER/other\n'
     'printf "EXT\\n" >> "$HISTFILE"\nhistory -n\n' + hlib.observe('END'),
     "bash's single global counter vs psh's per-default-file cursor"),

    # -- write/read ----------------------------------------------------
    ("-w then -n",
     'true NEW\nhistory -w\n'
     'printf "EXT\\n" >> "$HISTFILE"\nhistory -n\n' + hlib.observe('END'),
     "does -w advance the read cursor?"),

    ("external-truncate then -n (underflow)",
     'printf "only1\\n" > "$HISTFILE"\nhistory -n\n' + hlib.observe('END'),
     "file shrinks BELOW the counter"),

    ("external-truncate then -n then grow then -n",
     'printf "only1\\n" > "$HISTFILE"\nhistory -n\n'
     'printf "g1\\ng2\\ng3\\ng4\\n" >> "$HISTFILE"\nhistory -n\n'
     + hlib.observe('END'),
     "resume offset after an underflow"),
]

div = []
for name, script, note in CELLS:
    res = hlib.run_cell(script + 'exit\n', seed=SEED, named_seed=NAMED)
    if hlib.report(name, script, res, ['END_MEM', 'END_FILE'], note):
        div.append(name)

print(f"\n\nDIVERGING ({len(div)}/{len(CELLS)}):")
for n in div:
    print(f"  - {n}")
print("\nMATCHING:")
for name, _, _ in CELLS:
    if name not in div:
        print(f"  - {name}")
