"""Phase A7 — bash's FIXED INTERNAL ORDER for clustered history flags, and the
`-s` newline question.

A6 established that bash applies a cluster in a fixed internal order (`-ps` ==
`-sp`) with `-s` winning over `-p`.  A correct P7 needs the actual ORDER, not
an assumption, so each pair is probed through an observable that DIFFERS
between the two orders.

Also probes `history -s` with an embedded newline, because P3 routes `-s`
through `add_to_history`, whose cmdhist joiner would rewrite such an entry —
a behaviour change I must not ship unprobed.
"""
import hlib

hlib.header("A7 — cluster order + `-s` newline")

HI = 'history*:echo ===*:cat *:wc *:exit:printf *'
SEED = ['S1', 'S2', 'S3']


def show(name, script, note='', seed=SEED, named=None, histignore=HI):
    res = hlib.run_cell(script + 'exit\n', seed=seed, named_seed=named,
                        histignore=histignore)
    print(f"--- {name} ---")
    if note:
        print(f"    ({note})")
    for sh in ('bash', 'psh'):
        secs = res[sh][0]
        for key in ('MEM', 'OUT'):
            for sec in secs:
                if sec.endswith(key):
                    val = (hlib._listing(secs[sec]) if key == 'MEM'
                           else secs[sec])
                    print(f"   {sh:4s} {sec:10s}={val}")
    print(f"   file-after-exit: bash={res['bash'][1]}")
    print(f"                    psh ={res['psh'][1]}")
    print()
    return res


print("\n########## -c vs -w: which runs first? ##########\n")
show("-cw NAMED (seeded S1..S3, one typed entry)",
     'true keep\n'
     'history -cw $OTHER/out\n'
     'echo ===OUT===\ncat $OTHER/out\n',
     'clear-then-write => out is EMPTY; write-then-clear => out has S1..S3+keep',
     named={'out': []})

print("\n########## -c vs -d: which runs first? ##########\n")
show("-cd 1 then list",
     'true keep\n'
     'history -cd 1\n' + hlib.observe('OP'),
     'delete-then-clear and clear-then-delete both end empty; '
     'rc and any error message are the discriminator')

print("\n########## -a vs -n: which runs first? ##########\n")
show("-an with an external line already in the file",
     'true keep\n'
     'printf "EXTERNAL\\n" >> "$HISTFILE"\n'
     'history -an\n' + hlib.observe('OP'),
     'append-then-read => the appended entry is re-read into memory; '
     'read-then-append => EXTERNAL arrives before `keep` is written')

print("\n########## -r vs -w: which runs first? ##########\n")
show("-rw (default file)",
     'true keep\n'
     'history -rw\n' + hlib.observe('OP'),
     'read-then-write => file ends with the doubled list; '
     'write-then-read => memory ends doubled')

print("\n########## -s vs -p: confirmed precedence, plus -s vs -c ##########\n")
show("-cs STORED (clear + store)",
     'true keep\n'
     'history -cs STORED\n' + hlib.observe('OP'),
     'clear-then-store => [STORED]; store-then-clear => []')

show("-ds 1 STORED (delete + store)",
     'true keep\n'
     'history -ds 1 STORED\n' + hlib.observe('OP'),
     'does -d consume `1` and -s store `STORED`?')

print("\n########## `-s` with an embedded newline (P3 risk) ##########\n")
show("history -s $'a\\nb'",
     "history -s $'a\\nb'\n" + hlib.observe('OP'),
     'bash: one entry verbatim, or joined to `a; b`? '
     'P3 routes -s through add_to_history, whose cmdhist joiner would join it')

show("a REAL multi-line typed command (control for the joiner)",
     'if true\nthen true joined\nfi\n' + hlib.observe('OP'),
     'control: the cmdhist joiner IS correct for typed multi-line commands')
