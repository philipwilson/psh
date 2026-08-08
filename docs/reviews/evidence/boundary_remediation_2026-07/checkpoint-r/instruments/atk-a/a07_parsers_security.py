#!/usr/bin/env python3
"""Family F7: 2.2 both-parser parity x 2.1 security traversal x 2.3 composed
spellings.

Composed redirect-target/subscript/procsub/heredoc spellings run THREE-WAY
(psh --parser rd, psh --parser combinator, bash). Verdict axes:
PARSER-* = rd vs combinator internal parity (a divergence here is graded
against the 2.2 closure claims / declared combinator carries);
|MATCH/DIVERGE = rd vs bash.

Security cells run `--security` under BOTH parsers and compare outputs to
each other (parity axis; content graded against the HIGH-2 claim that
executable syntax in redirect targets / subjects / cmdsubs is visited).

Declared rows in scope: combinator arrays.py word-builder seam (array-init
nested substitution, s5 -- verified AS DECLARED); 2.3 read-time procsub
subscript keying (s3 uses the CLOSED literal-keying behavior).
Proof shape: characterization.
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a07_parsers_security.transcript.txt"))
F = "f7par"

cells = [
    ("s1_assoc_subscript_redirect_target", b"""declare -A a
a[k]=out1
echo hi > "${a[k]}"
cat out1
""", None),
    ("s2_procsub_redirect_source", b"""cat < <(echo hi)
""", None),
    ("s3_procsub_text_subscript_readback", b"""declare -A a
a['<(x)']=v
printf '<%s>\\n' "${a[<(x)]}"
""", None),
    ("s4_cmdsub_computed_redirect_target", b"""f=$(echo out4)
echo hi > "$f"
cat out4
""", None),
    # DECLARED-VERIFY: combinator arrays.py word-builder seam
    ("s5_array_init_nested_substitution_declared", b"""a=( $(echo x y) )
printf '<%s>' "${a[@]}"
echo
""", None),
    ("s6_heredoc_to_subscript_target", b"""declare -A m
m[p]=5
cat <<EOF > "${m[p]}.txt"
body
EOF
cat 5.txt
""", ["5.txt"]),
    ("s7_dbracket_with_fd_frame", b"""[[ -e /dev/fd/3 ]] 3</dev/null && echo Y || echo N
""", None),
    ("s8_heredoc_inside_procsub", b"""cat <(cat <<EOF
via procsub
EOF
)
""", None),
]

for name, script, artifacts in cells:
    T.cell(F, name, script,
           H.run_cell_threeway(F, name, script, artifacts=artifacts),
           tags=("rd", "pc", "bash"))

# security traversal parity: --security under both parsers
SEC = b"""eval "$x" > "${a[<(y)]}"
rm -rf $unquoted
for f in $(cat list); do echo $f; done
"""
sec_res = {}
for tag, extra in (("rd", ["--parser", "rd"]), ("pc", ["--parser", "combinator"])):
    d, sp = H.setup_rundir(F, "s9_security", tag, SEC, None)
    rc, out, err = H.run_one([H.PY, "-m", "psh", "--norc"] + extra
                             + ["--security", sp], d, None)
    sec_res[tag] = {"rc": rc, "out": out, "err": err, "dir": d, "artifacts": {}}
rd, pc = sec_res["rd"], sec_res["pc"]
rv, pv = H.norm_view(rd, rd["dir"]), H.norm_view(pc, pc["dir"])
sec_res["verdict"] = ("SECURITY-PARSER-MATCH" if rv == pv else "SECURITY-PARSER-DIVERGE") \
    + f"|rd-rc={rd['rc']},issues-reported={'issue' in rd['out'].decode().lower() or 'warning' in rd['out'].decode().lower()}"
T.cell(F, "s9_security_parity", SEC, sec_res, tags=("rd", "pc"))
T.close()
