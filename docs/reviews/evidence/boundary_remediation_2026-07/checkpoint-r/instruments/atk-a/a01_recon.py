#!/usr/bin/env python3
"""atk-a recon: pin down feature surfaces used by later family instruments.

r1: does `set -o history` + history builtin work non-interactively (both shells)?
r2: read -r -N spelling accepted from a file (both shells)?
r3: printf '\\xC3' byte emission (both shells)?
r4: /dev/fd/N visibility (both shells, macOS)?
These are recon cells, not findings cells.
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a01_recon.transcript.txt"))
F = "recon"

cells = [
    ("r1_history", b"""HISTFILE=$PWD/hist
set -o history
echo one
echo two
history -w
wc -l < hist
history | wc -l
"""),
    ("r2_readN", b"""printf 'abcdef' > d
IFS= read -r -N 3 v < d
printf '<%s>\\n' "$v"
"""),
    ("r3_printf_hex", b"""printf 'a\\xc3\\xa9b' | od -An -tx1 | tr -s ' '
"""),
    ("r4_devfd", b"""exec 3>f3
echo hi > /dev/fd/3
exec 3>&-
cat f3
"""),
    ("r5_history_r", b"""printf 'echo A\\necho B\\n' > seed
HISTFILE=$PWD/hist
set -o history
history -r seed
history | sed 's/^ *//'
"""),
]
for name, script in cells:
    T.cell(F, name, script, H.run_cell(F, name, script))
T.close()
