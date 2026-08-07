"""Phase A4 — CV3 strip x `-s` store x HISTSIZE cap: the COMPOSED order for the
PLAIN interactive spelling.

Leg B and the A3 cells suppressed recording with HISTIGNORE so the cap could be
seen in isolation.  WITHOUT that suppression the CV3 strip fires first: the
`history -s X` line is itself recorded, then `-s` deletes that last entry
(unverified), then stores X.  Adding a cap introduces a fourth step, so the
composed order (record -> strip -> store -> cap) must be checked against
bash's observable listing rather than assumed from the isolated cells.

The strip machinery is FENCED (settled by the boundary campaign's closing
verification) — this probe reads its behaviour, it does not propose changing it.
"""
import hlib

hlib.header("A4 — CV3 strip x -s x HISTSIZE cap, plain spelling (no HISTIGNORE)")


def cell(name, script, env, note=''):
    # histignore=None -> the probe's own lines ARE recorded (plain spelling)
    res = hlib.run_cell(script + hlib.observe('OP') + 'exit\n',
                        extra_env=env, histignore=None)
    b = hlib._listing(res['bash'][0].get('OP_MEM', []))
    p = hlib._listing(res['psh'][0].get('OP_MEM', []))
    print(f"--- {name} ---")
    if note:
        print(f"    ({note})")
    print(f"   bash={b}")
    print(f"   psh ={p}")
    print(f"  => {'MATCHES' if b == p else 'DIVERGES'}\n")
    return b, p


print("\n########## plain spelling, cap NOT reached (isolates the strip) "
      "##########\n")

cell("2 commands then `history -s X`",
     'true c1\ntrue c2\nhistory -s STORED\n', {'HISTSIZE': '50'},
     'strip removes the `history -s STORED` line, then stores STORED')

cell("`history -s X` as the FIRST line",
     'history -s STORED\n', {'HISTSIZE': '50'},
     'strip with an almost-empty history')

print("\n########## plain spelling, cap REACHED (strip x cap composition) "
      "##########\n")

cell("HISTSIZE=3, 2 commands then 3x `history -s`",
     'true c1\ntrue c2\n'
     'history -s s1\nhistory -s s2\nhistory -s s3\n', {'HISTSIZE': '3'},
     'each -s: record invocation, strip it, store sN, cap')

cell("HISTSIZE=2, 5x `history -s`",
     ''.join(f'history -s s{i}\n' for i in range(1, 6)), {'HISTSIZE': '2'},
     'tight cap, plain spelling')

cell("HISTSIZE=3, alternating record and -s",
     'true a\nhistory -s s1\ntrue b\nhistory -s s2\ntrue c\n',
     {'HISTSIZE': '3'}, 'interleaved producers under one cap')

print("\n########## the same cells WITH suppression (labelled control: "
      "isolates the cap from the strip) ##########\n")

cell("HISTSIZE=3, 2 commands then 3x -s  [HISTIGNORE control]",
     'true c1\ntrue c2\n'
     'history -s s1\nhistory -s s2\nhistory -s s3\n',
     {'HISTSIZE': '3', 'HISTIGNORE': 'history*:echo ===*:cat *:exit'},
     'control for the cell two above')

print("\n########## -p (the other strip consumer) x cap ##########\n")

cell("HISTSIZE=3, commands then `history -p !!`",
     'true a\ntrue b\ntrue c\nhistory -p "!!"\n', {'HISTSIZE': '3'},
     '-p strips but does not store; the cap must not disturb it')
