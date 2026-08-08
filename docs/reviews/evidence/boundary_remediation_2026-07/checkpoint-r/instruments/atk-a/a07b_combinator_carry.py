#!/usr/bin/env python3
"""Addendum to F7: the DECLARED combinator arrays.py word-builder seam,
exercised with the pin's EXACT spellings ('a=($(echo @(a|b)))' and
'echo hi > $(echo @(a|b))', extglob on), end-to-end three-way.

The committed pins are unit-level (parse_with_inputs). This runs the same
sources as scripts: expected AS-DECLARED shape = rd+bash accept, combinator
rejects. Graded against the declared carry either way (characterization).
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a07b_combinator_carry.transcript.txt"))
F = "f7carry"

cells = [
    ("c1_array_init_extglob_in_cmdsub_declared", b"""shopt -s extglob
a=($(echo @(a|b)))
printf '<%s>' "${a[@]}"
echo
"""),
    ("c2_redirect_target_extglob_in_cmdsub_declared", b"""shopt -s extglob
echo hi > $(echo @(a|b))
ls
"""),
]

for name, script in cells:
    T.cell(F, name, script, H.run_cell_threeway(F, name, script),
           tags=("rd", "pc", "bash"))
T.close()
