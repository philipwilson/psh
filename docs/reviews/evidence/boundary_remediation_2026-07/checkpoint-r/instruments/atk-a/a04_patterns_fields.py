#!/usr/bin/env python3
"""Family F4: 3.1/3.2 pattern engine x 3.3 field-IR / positional params.

Composed cells: extglob/negation/char-class patterns whose TEXT arrives via
expanded fields ($1, vars) consumed by ${v%%pat}/${v//pat/rep}, case, [[.
Multi-field case SUBJECT "$@"; multi-field case PATTERN operand (declared
3.3 successor row b) verified AS DECLARED.

Axis: DIVERGENCE (tip vs bash 5.2.26).
Declared rows in scope: case-pattern multi-field first-field exclusion (g8);
3.1 lex_q1/lex_case_q1 quoted-chars-in-extglob-group (avoided: no quotes
inside groups except g8's field text); opx_slash operand-extent (avoided: no
'/' inside groups in ${v/../..}).
Proof shape: characterization (two-sided differential).
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a04_patterns_fields.transcript.txt"))
F = "f4pat"

cells = [
    ("g1_extglob_from_positional_suffix", b"""shopt -s extglob
set -- '?(a)'
v=xa
printf '<%s>\\n' "${v%%$1}"
"""),
    ("g2_extglob_from_var_both_ends", b"""shopt -s extglob
p='+([0-9])'
v=abc123
printf '<%s><%s>\\n' "${v%$p}" "${v##*([a-c])}"
"""),
    ("g3_negation_from_positional_case", b"""shopt -s extglob
set -- '!(*.txt)'
case foo.txt in $1) echo M;; *) echo N;; esac
case foo.log in $1) echo M;; *) echo N;; esac
"""),
    ("g4_extglob_from_positional_dbracket", b"""shopt -s extglob
set -- '@(x|y)'
[[ x == $1 ]] && echo Y1 || echo N1
[[ z == $1 ]] && echo Y2 || echo N2
"""),
    ("g5_nullable_star_group_substitution", b"""shopt -s extglob
p='*(o)'
v=foo
printf '<%s>\\n' "${v//$p/X}"
"""),
    ("g6_charclass_from_var_substitution", b"""p='[[:alpha:]]'
v=a1b
printf '<%s>\\n' "${v//$p/_}"
"""),
    ("g7_multifield_case_subject", b"""set -- 'a b' c
case "$@" in 'a b c') echo M;; *) echo N;; esac
"""),
    # DECLARED-VERIFY (3.3 successor row b): multi-field case PATTERN operand:
    # bash matches the FIRST FIELD; psh space-joins (no match here)
    ("g8_multifield_case_pattern_declared", b"""shopt -s extglob
set -- '@(a|b)' extra
case a in "$@") echo M;; *) echo N;; esac
"""),
    # g9: pattern text from a FIELD of an operand default (3.3 x 3.1)
    ("g9_pattern_from_operand_default", b"""shopt -s extglob
set -- '@(hi|lo)'
p=${u:-"$@"}
[[ hi == $p ]] && echo Y || echo N
"""),
]

for name, script in cells:
    T.cell(F, name, script, H.run_cell(F, name, script))
T.close()
