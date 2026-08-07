"""Phase A6 — carry #25 rider battery (ruled IN by R1(a)).

R1(a) demotes the LEDGER row's "trivial option-scan" framing: `-ps` composition
semantics are a real behavioural question.  Probed here:

  1. `-p`/`-s` composition, both cluster orders, with and without operands,
     stdout + rc + the resulting history listing.
  2. Whether bash applies clustered flags LEFT-TO-RIGHT or in a fixed internal
     order (the `-ps` vs `-sp` pair answers this directly).
  3. The line-scoped CV3 strip flag under a cluster (`-s` CONSUMES it, `-p`
     KEEPS it — which applies when both letters arrive together?).
  4. A representative sanity set of other clusters (`-cw`, `-an`, `-rw`, `-cd`),
     with full matrices only where a sanity row diverges.
  5. Invalid letters inside a cluster.

Plain spelling throughout (no HISTIGNORE): the strip is part of the subject.
"""
import hlib

hlib.header("A6 — rider carry #25: clustered history flags")


def cell(name, lines, seed=None, named=None, note=''):
    script = ''.join(ln + '\n' for ln in lines) + hlib.observe('OP') + 'exit\n'
    res = hlib.run_cell(script, seed=seed, named_seed=named, histignore=None)
    print(f"--- {name} ---")
    if note:
        print(f"    ({note})")
    same = True
    for sh in ('bash', 'psh'):
        secs = res[sh][0]
        # everything printed before the OP marker that is not a listing line
        pre = [ln for ln in secs.get('PRE', [])]
        mem = hlib._listing(secs.get('OP_MEM', []))
        print(f"   {sh:4s}: stdout-before={pre}")
        print(f"         listing={mem}")
    b = (res['bash'][0].get('PRE', []), hlib._listing(res['bash'][0].get('OP_MEM', [])))
    p = (res['psh'][0].get('PRE', []), hlib._listing(res['psh'][0].get('OP_MEM', [])))
    same = b == p
    print(f"   file-after-exit: bash={res['bash'][1]}")
    print(f"                    psh ={res['psh'][1]}")
    print(f"  => {'MATCHES' if same else 'DIVERGES'}\n")
    return res


P = 'echo ===PRE==='   # everything the cluster prints lands in this section

print("\n########## 1. -p/-s composition, both orders, with operands "
      "##########\n")

cell("-ps WITH operand", ['true prev', P, 'history -ps hello'],
     note='does the -p print happen? does the -s store happen?')
cell("-sp WITH operand", ['true prev', P, 'history -sp hello'],
     note='reverse cluster order — same result => fixed internal order')
cell("-p then -s as SEPARATE words", ['true prev', P, 'history -p -s hello'],
     note='not a cluster: -p with operands "-s" and "hello"')

print("\n########## 2. -p/-s composition WITHOUT operands ##########\n")

cell("-ps with NO operand", ['true prev', P, 'history -ps'],
     note='rc and side effects with an empty operand list')
cell("-sp with NO operand", ['true prev', P, 'history -sp'])

print("\n########## 3. rc observation ##########\n")

for spelling in ('-ps hello', '-sp hello', '-ps', '-p hello', '-s hello'):
    cell(f"rc of `history {spelling}`",
         ['true prev', P, f'history {spelling}; echo "RC=$?"'])

print("\n########## 4. the line-scoped CV3 strip flag under a cluster "
      "##########\n")

cell("SAME LINE: -ps a; -s b", ['true prev', P, 'history -ps a; history -s b'],
     note='-s consumes the flag, -p keeps it: which applies to the cluster?')
cell("SAME LINE control: -p a; -s b",
     ['true prev', P, 'history -p a; history -s b'],
     note='control — -p keeps the flag, so -s still strips')
cell("SAME LINE control: -s a; -s b",
     ['true prev', P, 'history -s a; history -s b'],
     note='control — first -s consumes, second does not strip')
cell("-ps with a history REFERENCE operand",
     ['true prev', 'true target', P, 'history -ps "!!"'],
     note='what does !! resolve to after the strip?')

print("\n########## 5. representative sanity set of OTHER clusters "
      "##########\n")

SEED = ['seed1', 'seed2', 'seed3']
cell("-cw (clear then write)", ['true keep', P, 'history -cw $OTHER/out',
                                'cat $OTHER/out'],
     seed=SEED, named={'out': []}, note='order: clear-then-write or reverse?')
cell("-an (append then read-new)",
     ['true keep', P, 'printf "EXTRA\\n" >> "$HISTFILE"', 'history -an'],
     seed=SEED, note='both file ops in one invocation')
cell("-rw (read then write)", ['true keep', P, 'history -rw'], seed=SEED)
cell("-cd 1 (clear + delete)", ['true keep', P, 'history -cd 1'], seed=SEED,
     note='-d takes an argument; does the cluster consume it?')

print("\n########## 6. invalid letters inside a cluster ##########\n")

cell("-pz (valid then invalid)", ['true prev', P, 'history -pz x; echo "RC=$?"'])
cell("-zs (invalid then valid)", ['true prev', P, 'history -zs x; echo "RC=$?"'])
cell("-- terminator", ['true prev', P, 'history -s -- x; echo "RC=$?"'])
