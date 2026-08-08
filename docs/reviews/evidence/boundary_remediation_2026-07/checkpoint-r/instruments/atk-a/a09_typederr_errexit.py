#!/usr/bin/env python3
"""Family F9: 3.5 typed expansion/arith errors x errexit x EXIT traps (4A.2).

Composed cells: bad arith subscripts, unset-under-nounset, division by zero
-- each under an EXIT trap and again under set -e. The 3.5 claim was typed
errors with narrowed nets; the composition asks whether severity routing
(continue vs abort) matches bash when errexit/traps are stacked on top.

Axis: DIVERGENCE (tip vs bash 5.2.26).
Declared rows in scope: D-3.5-s4 PS4 (not exercised), D-3.5-s5 regex
diagnostic (not exercised).
Proof shape: characterization.
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a09_typederr_errexit.transcript.txt"))
F = "f9err"

cells = [
    ("e1_bad_subscript_trap", b"""trap 'echo T >&2' EXIT
echo "${a[b+]}"
echo after
"""),
    ("e2_bad_subscript_errexit_trap", b"""set -e
trap 'echo T >&2' EXIT
echo "${a[b+]}"
echo after
"""),
    ("e3_nounset_trap", b"""set -u
trap 'echo T >&2' EXIT
echo "$undef_xyz"
echo after
"""),
    ("e4_div_zero_trap", b"""trap 'echo T >&2' EXIT
echo $((1/0))
echo after
"""),
    ("e5_div_zero_errexit_trap", b"""set -e
trap 'echo T >&2' EXIT
echo $((1/0))
echo after
"""),
    ("e6_bad_subscript_assign_errexit", b"""set -e
trap 'echo T >&2' EXIT
a[b+]=1
echo after
"""),
    ("e7_nounset_in_arith_trap", b"""set -u
trap 'echo T >&2' EXIT
echo $((undef_xyz + 1))
echo after
"""),
]

for name, script in cells:
    T.cell(F, name, script, H.run_cell(F, name, script))
T.close()
