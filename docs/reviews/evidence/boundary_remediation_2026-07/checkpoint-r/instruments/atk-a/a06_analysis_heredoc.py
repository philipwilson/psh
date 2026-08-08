#!/usr/bin/env python3
"""Family F6: 2.6 analysis totality x 2.5 heredoc authority x 2.3 scanner class.

Each cell runs FOUR ways: exec (psh vs bash), noexec (psh -n vs bash -n),
and psh --validate is RECORDED as characterization (state-aware BY DESIGN --
the declared two-static-surfaces split says --validate may legitimately
differ from -n; a --validate result is graded only against the 2.6 claim
that analysis tracks execution's own directive state, never against bash).

Axes: exec = DIVERGENCE vs bash; noexec = DIVERGENCE vs bash -n; the
exec-vs-validate column is the 2.6 internal-consistency axis.
Declared rows in scope: 2.6 alias-axis asymmetries (avoided -- no aliases);
unreached-conditional-shopt cost pin (avoided -- directives here are
unconditional); plain/digit dangling-heredoc PS2 policy (avoided -- no
dangling heredocs at EOF in exec cells).
Proof shape: characterization.
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a06_analysis_heredoc.transcript.txt"))
F = "f6ana"

cells = [
    # v1: extglob directive AFTER a heredoc; extglob use later
    ("v1_directive_after_heredoc", b"""cat <<EOF
plain body
EOF
shopt -s extglob
case ab in a@(b)) echo M;; *) echo N;; esac
"""),
    # v2: directive text INSIDE the heredoc body -- must NOT take effect;
    # the later extglob use is a syntax error in both shells
    ("v2_directive_inside_heredoc_body", b"""cat <<EOF
shopt -s extglob
EOF
case ab in a@(b)) echo M;; *) echo N;; esac
"""),
    # v3: heredoc body carrying the scanner-balancing class (unbalanced
    # openers as TEXT); execution and analysis must both stay unconfused
    ("v3_balancing_class_in_body", b"""cat <<'EOF'
case x in
if then
$(
((
[[
`
'
"
EOF
echo done
"""),
    # v4: nested heredoc inside command substitution inside outer heredoc
    ("v4_nested_heredoc_in_cmdsub", b"""cat <<OUTER
before $(cat <<INNER
inner
INNER
) after
OUTER
echo done
"""),
    # v5: escaped \\<< (NOT a heredoc) inside a case arm (2.3 x M3 class)
    ("v5_escaped_heredoc_in_case", b"""case x in x) echo \\<<EOF;; esac
echo done
"""),
    # v6: quoted vs unquoted delimiter expansion suppression, cmdsub in body
    ("v6_quoted_delim_suppression", b"""cat <<'EOF'
literal $(echo X) stays
EOF
cat <<EOF2
expanded $(echo X) runs
EOF2
"""),
]


def run_ways(name, script):
    res_exec = H.run_cell(F, name + "_exec", script)
    # noexec: psh -n vs bash -n
    res_noexec = {}
    for tag, argv_head in (("psh", [H.PY, "-m", "psh", "--norc", "-n"]),
                           ("bash", [H.BASH, "-n"])):
        d, sp = H.setup_rundir(F, name + "_noexec", tag, script, None)
        rc, out, err = H.run_one(argv_head + [sp], d, None)
        res_noexec[tag] = {"rc": rc, "out": out, "err": err, "dir": d,
                           "artifacts": {}}
    p, b = res_noexec["psh"], res_noexec["bash"]
    pv, bv = H.norm_view(p, p["dir"]), H.norm_view(b, b["dir"])
    if (pv[0], pv[1]) == (bv[0], bv[1]):
        res_noexec["verdict"] = "MATCH" if pv[2] == bv[2] else "STDERR-ONLY"
    else:
        res_noexec["verdict"] = "DIVERGE"
    # validate: psh only, recorded (compared against psh's own exec rc class)
    d, sp = H.setup_rundir(F, name + "_validate", "psh", script, None)
    rc, out, err = H.run_one([H.PY, "-m", "psh", "--norc", "--validate", sp], d, None)
    res_val = {"psh": {"rc": rc, "out": out, "err": err, "dir": d,
                       "artifacts": {}},
               "verdict": f"VALIDATE-rc={rc}"}
    return res_exec, res_noexec, res_val


for name, script in cells:
    re_, rn, rv = run_ways(name, script)
    T.cell(F, name + "_exec", script, re_)
    T.cell(F, name + "_noexec", script, rn)
    T.cell(F, name + "_validate", script, rv, tags=("psh",))
T.close()
