"""Phase A6b — rider supplement: rc for the clusters whose A6 cells came out
NON-DISCRIMINATING.

In A6 the `-an` and `-rw` cells produced identical observables in both shells
even though bash ACCEPTS the cluster and psh REJECTS it — the file/listing
happened to land the same way, so those two cells proved nothing.  rc is the
observable that discriminates, so it is measured directly here.  (`-cw` and
`-cd 1` did discriminate in A6 and are repeated for continuity.)
"""
import hlib

hlib.header("A6b — rider: rc per cluster (discriminating supplement)")

SEED = ['seed1', 'seed2', 'seed3']
CLUSTERS = ['-ps hello', '-sp hello', '-ps', '-an', '-rw', '-cw', '-cd 1',
            '-ca', '-nr', '-p -s hello', '-s -- x', '-pz x', '-zs x']

print()
for spec in CLUSTERS:
    # FAULT F-2 (self-disclosed): the first version of this line read
    #   history ...; echo "===RC==="; echo "$?"
    # so `$?` was the marker echo's status, not the history builtin's, and
    # every row printed rc=0 — including `-pz`, which both shells reject.
    # The status must be captured BEFORE anything else runs.
    script = (f'history {spec} >/dev/null 2>&1; rc=$?\n'
              'echo "===RC==="\n'
              'echo "$rc"\n'
              'exit\n')
    res = hlib.run_cell(script, seed=SEED, histignore=None)
    b = res['bash'][0].get('RC', ['?'])
    p = res['psh'][0].get('RC', ['?'])
    mark = ' ' if b == p else '*'
    print(f" {mark}history {spec:14s}  bash rc={b}   psh rc={p}")

print("\n(`*` = the rc discriminates: bash accepts the spelling, psh rejects "
      "it — or vice versa)")
