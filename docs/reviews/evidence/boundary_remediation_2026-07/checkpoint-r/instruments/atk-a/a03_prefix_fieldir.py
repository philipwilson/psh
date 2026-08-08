#!/usr/bin/env python3
"""Family F3: 3.4 prefix-assignment staging x 3.3 field-IR operands.

Composed cells: field-IR operand expansions ("$@"-bearing operand defaults)
used as PREFIX-ASSIGNMENT VALUES; refuse-before-evaluate on readonly
prefixes with command-substitution operands; staged-binding visibility
chains; RANDOM staging feeding a later prefix expansion.

Axis: DIVERGENCE (tip vs bash 5.2.26); REGRESSION grading vs LEDGER claims
(3.3 operand field preservation, 3.4 refuse-before-evaluate) in the report.
Declared rows in scope: posix special-builtin readonly abort rc (bash 127 /
psh 1) -- p5 verifies AS DECLARED; D-3.4-s4 masked-special LAYER route --
p8 graded against its domain if divergent.
Proof shape: characterization (two-sided differential).
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a03_prefix_fieldir.transcript.txt"))
F = "f3pfx"

cells = [
    ("p1_quoted_at_operand_prefix", b"""set -- a b
v=${u:-"$@"} /usr/bin/env > eo
grep '^v=' eo
"""),
    ("p2_quoted_at_embedded_space", b"""set -- a 'b  c'
v=${u:-"$@"} /usr/bin/env > eo
grep '^v=' eo
"""),
    ("p3_bare_at_operand_prefix", b"""set -- a b
v=${u:-$@} /usr/bin/env > eo
grep '^v=' eo
"""),
    ("p4_readonly_refuse_cmdsub_external", b"""readonly RX=1
RX=${u:-$(touch m1; echo x)} /usr/bin/true
echo rc=$?
[ -e m1 ] && echo M1-PRESENT || echo M1-ABSENT
echo after
"""),
    # DECLARED-VERIFY: posix special-builtin readonly abort rc: bash 127 / psh 1
    ("p5_readonly_refuse_special_builtin_declared", b"""readonly RY=1
RY=${u:-$(touch m2; echo x)} :
echo rc=$?
[ -e m2 ] && echo M2-PRESENT || echo M2-ABSENT
echo after
"""),
    ("p6_staged_chain_visibility", b"""A=7 B=${A}x /usr/bin/env > eo
grep -E '^(A|B)=' eo | sort
"""),
    ("p7_bare_at_nondefault_ifs_assignment", b"""set -- aXq b
IFS=X
v=${u:-$@} /usr/bin/env > eo
grep '^v=' eo
"""),
    ("p8_random_staged_feeds_prefix", b"""RANDOM=42 R=$RANDOM /usr/bin/env > eo
grep -c '^R=[0-9]' eo
"""),
    # p9: field-IR operand value ends up multi-field in COMMAND position but
    # single-field in the SAME line's prefix assignment
    ("p9_prefix_vs_word_same_line", b"""set -- a b
v=${u:-"$@"} /usr/bin/env > eo
grep '^v=' eo
printf '<%s>' ${u:-"$@"}
echo
"""),
]

for name, script in cells:
    T.cell(F, name, script, H.run_cell(F, name, script))
T.close()
