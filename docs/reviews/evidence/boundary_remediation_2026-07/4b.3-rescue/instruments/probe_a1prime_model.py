"""Phase A1' — re-derivation of bash's `-a` mechanism (R2-F1 bounce).

R2-F1 is correct that my D2 compositions could not tell MARKER-IDENTITY from
TAIL-COUNT: in every A1c cell the two models predicted the same answer.  The
discriminator is a composition where the tail window and the identity set
DIFFER — type K recorded commands, then read M lines, so the last K entries of
the list are NOT the K typed ones.

CANDIDATE MODEL (from the integrator's sharp probe + my A1c rows), stated as
code below so it must predict EVERY cell:

    N = 0
    recorded command            -> N += 1
    `history -s` store          -> N += 1
    `-n` reading L lines        -> N += L      (read lines DO count)
    `-r` reading L lines        -> N += 0      (read lines do NOT count)
    `-a`                        -> writes history[len-N:] BY POSITION, then N = 0
    `-w`                        -> writes everything, N unchanged
    `-d` deleting D entries     -> N -= D
    `-c`                        -> ? (cell 8 decides)

Identity plays no role in `-a`: it is a TAIL WINDOW.  Every cell prints the
model's prediction next to the observation, and a mismatch is reported loudly.
"""
import hlib

hlib.header("A1' — bash `-a` mechanism re-derivation (marker-identity vs tail-count)")

# The scaffolding is HISTIGNOREd, so ONLY `true tN` lines are recorded.
HI = 'history*:echo ===*:cat *:wc *:exit:printf *'
APPEND_INSTR = ('printf "" > "$HISTFILE"\nhistory -a\n' + hlib.observe('A'))


def typed(k, tag='t'):
    return ''.join(f'true {tag}{i}\n' for i in range(1, k + 1))


def predict_tail(mem, n):
    """The candidate model's prediction: the last N entries, by position."""
    if n <= 0:
        return []
    return mem[len(mem) - n:] if n <= len(mem) else list(mem)


CELLS = []


def add(name, script, mem_pred, n_pred, note=''):
    CELLS.append((name, script, mem_pred, n_pred, note))


# 1-3: K typed then M read via -r  (tail window != identity set)
add("K=2 typed, then -r 4 lines",
    typed(2) + 'history -r $OTHER/r4\n',
    ['S1', 'S2', 'S3', 'true t1', 'true t2', 'R1', 'R2', 'R3', 'R4'], 2,
    "identity model would write [true t1,true t2]; tail-2 = [R3,R4]")

add("K=4 typed, then -r 2 lines",
    typed(4) + 'history -r $OTHER/r2\n',
    ['S1', 'S2', 'S3', 'true t1', 'true t2', 'true t3', 'true t4',
     'Q1', 'Q2'], 4,
    "tail-4 = [true t3,true t4,Q1,Q2] — a MIX; identity = the 4 typed")

add("K=2 typed, then -r 2 lines (K==M)",
    typed(2) + 'history -r $OTHER/r2\n',
    ['S1', 'S2', 'S3', 'true t1', 'true t2', 'Q1', 'Q2'], 2,
    "tail-2 = [Q1,Q2]; identity = the 2 typed")

# 4: -r FIRST, then typed  (tail and identity coincide -> labelled control)
add("-r 4 lines FIRST, then K=2 typed",
    'history -r $OTHER/r4\n' + typed(2),
    ['S1', 'S2', 'S3', 'R1', 'R2', 'R3', 'R4', 'true t1', 'true t2'], 2,
    "CONTROL: tail-2 == the typed pair, so this cell does NOT discriminate")

# 5: interleaved
add("typed, -r 2, typed, -r 2",
    typed(1, 'a') + 'history -r $OTHER/r2\n' + typed(1, 'b')
    + 'history -r $OTHER/r2\n',
    ['S1', 'S2', 'S3', 'true a1', 'Q1', 'Q2', 'true b1', 'Q1', 'Q2'], 2,
    "tail-2 = [Q1,Q2] (the SECOND read); identity = [true a1,true b1]")

# 6-7: the same shapes with -n instead of -r (read lines DO count)
add("K=2 typed, then -n pulling 2 lines",
    typed(2) + 'printf "N1\\nN2\\n" >> "$HISTFILE"\nhistory -n\n',
    ['S1', 'S2', 'S3', 'true t1', 'true t2', 'N1', 'N2'], 4,
    "N = 2 typed + 2 read = 4 -> tail-4 = [true t1,true t2,N1,N2]")

add("K=1 typed, then -n pulling 3 lines",
    typed(1) + 'printf "N1\\nN2\\nN3\\n" >> "$HISTFILE"\nhistory -n\n',
    ['S1', 'S2', 'S3', 'true t1', 'N1', 'N2', 'N3'], 4,
    "N = 1 + 3 = 4 -> tail-4 = [true t1,N1,N2,N3]")

# 8: does -c reset the counter?
add("K=2 typed, -c, -r 3 lines, K=1 typed",
    typed(2) + 'history -c\nhistory -r $OTHER/r3\n' + typed(1, 'z'),
    ['P1', 'P2', 'P3', 'true z1'], None,
    "N=3 (no reset) -> tail-3 = [P2,P3,true z1];  "
    "N=1 (reset) -> tail-1 = [true z1]  <-- DECIDES the -c row")

# 9: does -d decrement the counter?
add("K=3 typed, then -d 4 (delete the FIRST typed entry)",
    typed(3) + 'history -d 4\n',
    ['S1', 'S2', 'S3', 'true t2', 'true t3'], 2,
    "N=2 (decrement) -> tail-2 = [true t2,true t3];  "
    "N=3 -> tail-3 = [S3,true t2,true t3]")

# 10: does -w consume the counter?
add("K=2 typed, then -w to a NAMED file",
    typed(2) + 'history -w $OTHER/out\n',
    ['S1', 'S2', 'S3', 'true t1', 'true t2'], 2,
    "N unchanged by -w -> tail-2 = the typed pair")

# 11: -a twice (does the first -a zero the counter?)
add("K=2 typed, -a, then K=1 typed",
    typed(2) + 'history -a\n' + typed(1, 'z'),
    None, 1,
    "if the first -a zeroed N, the second writes only [true z1]")

NAMED = {'r4': ['R1', 'R2', 'R3', 'R4'], 'r2': ['Q1', 'Q2'],
         'r3': ['P1', 'P2', 'P3'], 'out': []}
SEED = ['S1', 'S2', 'S3']

mismatches = []
for name, script, mem_pred, n_pred, note in CELLS:
    res = hlib.run_cell(script + hlib.observe('OP') + APPEND_INSTR + 'exit\n',
                        seed=SEED, named_seed=NAMED, histignore=HI)
    print(f"--- {name} ---")
    if note:
        print(f"    ({note})")
    for sh in ('bash', 'psh'):
        mem = hlib._listing(res[sh][0].get('OP_MEM', []))
        wrote = res[sh][0].get('A_FILE', [])
        print(f"   {sh:4s}: mem={mem}")
        print(f"         `-a` wrote={wrote}")
        if sh == 'bash' and n_pred is not None:
            pred = predict_tail(mem, n_pred)
            ok = (pred == wrote)
            print(f"         MODEL predicts tail-{n_pred} = {pred}   "
                  f"{'OK' if ok else '*** MISMATCH ***'}")
            if not ok:
                mismatches.append(name)
    print()

print("=" * 72)
if mismatches:
    print(f"MODEL MISMATCHES ({len(mismatches)}): {mismatches}")
    print("The candidate tail-count model does NOT predict every cell.")
else:
    print("The candidate tail-count model predicted every cell with a "
          "stated N.")
print("Cells 8 and 11 have no pre-stated N — they DECIDE the -c and "
      "-a-resets rows; read their observations above.")
