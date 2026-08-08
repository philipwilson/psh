#!/usr/bin/env python3
"""F10 redesign: RANDOM x fork boundaries with MECHANISM-VISIBLE cells.

The first a10 composition had the instrument-mirror flaw: bash 5.1+ RESEEDS
$RANDOM in subshells, so the bash side of a child-value equality cell is
stochastic. These cells make each candidate mechanism's execution visible:

  mA (within-run): two sibling subshells read $RANDOM. Sequence-continuation
      => the two values are EQUAL (each fork copies the same state);
      reseed => values differ (P(collision) = 1/32768).
  mB (across-run): the same seeded script run TWICE per shell. Reseed =>
      child value varies across runs; sequence-continuation => constant.
  mC (parent-integrity, deterministic both shells): the PARENT's own seeded
      sequence must be unperturbed by child reads -- direct equality cell.
  mD (cmdsub + pipeline variants of mA).

Axis: DIVERGENCE (tip vs bash 5.2.26) on the MECHANISM (deterministic
child values vs reseeded), not on stochastic values.
Proof shape: characterization with per-shell mechanism classification.
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a10b_random_mechanism.transcript.txt"))
F = "f10rn2"

MA = b"""RANDOM=5
( echo $RANDOM )
( echo $RANDOM )
"""
MD_CMDSUB = b"""RANDOM=5
x=$(echo $RANDOM)
y=$(echo $RANDOM)
echo "$x $y"
"""
MD_PIPE = b"""RANDOM=5
echo $RANDOM | cat
echo $RANDOM | cat
"""
MC = b"""RANDOM=42
( : $RANDOM )
x=$(: ; echo x)
a=$RANDOM
b=$RANDOM
echo "$a $b"
"""


def classify(name, script, runs=2):
    """Run `script` twice per shell; report child values + mechanism class."""
    out = {}
    for tag in ("psh", "bash"):
        vals = []
        for i in range(runs):
            d, sp = H.setup_rundir(F, f"{name}_run{i}", tag, script, None)
            argv = ([H.PY, "-m", "psh", "--norc", sp] if tag == "psh"
                    else [H.BASH, sp])
            rc, o, e = H.run_one(argv, d, None)
            vals.append((rc, o.decode().split()))
        out[tag] = vals
    return out


for name, script in (("mA_two_subshells", MA),
                     ("mD1_two_cmdsubs", MD_CMDSUB),
                     ("mD2_two_pipelines", MD_PIPE)):
    r = classify(name, script)
    lines = []
    mech = {}
    for tag in ("psh", "bash"):
        (rc0, v0), (rc1, v1) = r[tag]
        within_equal = len(v0) == 2 and v0[0] == v0[1]
        across_equal = v0 == v1
        mech[tag] = ("SEQUENCE-DETERMINISTIC" if within_equal and across_equal
                     else "RESEEDED-STOCHASTIC" if not across_equal or not within_equal
                     else "?")
        lines.append(f"{tag}: run0={v0} run1={v1} rc={rc0}/{rc1} "
                     f"within_equal={within_equal} across_equal={across_equal} -> {mech[tag]}")
    verdict = ("MECH-MATCH" if mech["psh"] == mech["bash"]
               else f"MECH-DIVERGE({mech['psh']} vs {mech['bash']})")
    T.f.write(f"\n=== CELL {F}.{name} ===\nscript:\n")
    for ln in script.decode().splitlines():
        T.f.write("  | " + ln + "\n")
    T.f.write("\n".join(lines) + f"\nVERDICT: {verdict}\n")
    T.counts[verdict] = T.counts.get(verdict, 0) + 1
    T.f.flush()
    print(f"{F}.{name}: {verdict}")

# mC: deterministic parent-integrity equality cell (plain two-sided)
T.cell(F, "mC_parent_sequence_integrity", MC, H.run_cell(F, "mC", MC))
T.close()
