#!/usr/bin/env python3
"""Family F10: 3.4 RANDOM seed-at-COMMIT x fork boundaries (subshell, cmdsub,
pipeline member).

bash's seeded RANDOM sequence is deterministic and forks inherit the seed
state; psh's 3.4 closure claims seeded-sequence parity value-for-value.
The composition asks whether the sequence stays value-for-value ACROSS
fork boundaries.

Axis: DIVERGENCE (tip vs bash 5.2.26).
Declared row in scope: D-3.4-s4 masked-special LAYER route (RANDOM=1 eval)
-- not exercised; these cells COMMIT the seed with a plain assignment first.
Proof shape: characterization.
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a10_random_forks.transcript.txt"))
F = "f10rnd"

cells = [
    ("r1_parent_sequence_control", b"""RANDOM=42
a=$RANDOM
b=$RANDOM
echo "$a $b"
"""),
    ("r2_subshell_then_parent", b"""RANDOM=42
( echo $RANDOM )
echo $RANDOM
"""),
    ("r3_cmdsub_then_parent", b"""RANDOM=42
x=$(echo $RANDOM)
echo "$x $RANDOM"
"""),
    ("r4_pipeline_member_then_parent", b"""RANDOM=42
echo $RANDOM | cat
echo $RANDOM
"""),
    ("r5_nested_subshell_chain", b"""RANDOM=7
( ( echo $RANDOM ); echo $RANDOM )
echo $RANDOM
"""),
]

for name, script in cells:
    T.cell(F, name, script, H.run_cell(F, name, script))
T.close()
