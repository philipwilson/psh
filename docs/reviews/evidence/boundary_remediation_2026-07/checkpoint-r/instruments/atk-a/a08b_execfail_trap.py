#!/usr/bin/env python3
"""Addendum to F8: isolate the x5 observation (EXIT trap after failed `exec
PROG`) and verify the DECLARED move-form shape (D-4B.4-s2, `true 3<&0-`).

y1/y2/y3: minimal exec-fail cells -- psh vs bash, file mode, ./rel and /abs
program paths, plus -c mode.
y4 CONTROL: failed ORDINARY command (no exec) -- trap must fire in BOTH,
proving the differential is exec-specific, not trap machinery.
y5 CONTROL: successful exec -- trap must fire in NEITHER (process replaced).
y6: DECLARED-VERIFY D-4B.4-s2: per-command move `true 3<&0-`; psh restores
fd 0 after the frame (next read succeeds), bash's move closes the source.
Proof shape: characterization (two-sided differential with controls).
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a08b_execfail_trap.transcript.txt"))
F = "f8exf"

cells = [
    ("y1_execfail_trap_rel", b"""trap 'echo T >&2' EXIT
exec ./nonexistent_prog_xyz
echo after
""", None, None),
    ("y2_execfail_trap_abs", b"""trap 'echo T >&2' EXIT
exec /nonexistent_prog_xyz
echo after
""", None, None),
    ("y4_control_ordinary_fail_trap", b"""trap 'echo T >&2' EXIT
./nonexistent_prog_xyz
echo after
""", None, None),
    ("y5_control_successful_exec", b"""trap 'echo T >&2' EXIT
exec /usr/bin/true
echo after
""", None, None),
    # DECLARED-VERIFY D-4B.4-s2: per-command move form
    ("y6_move_form_temp_frame_declared", b"""IFS= read -r a
true 3<&0-
if IFS= read -r b; then echo "alive<$b>"; else echo "dead rc=$?"; fi
printf 'a<%s>\\n' "$a"
""", b"L1\nL2\nL3\n", None),
]

for name, script, stdin, artifacts in cells:
    T.cell(F, name, script,
           H.run_cell(F, name, script, stdin=stdin, artifacts=artifacts))

# y3: -c mode variant of the exec-fail trap cell
import subprocess
CMD = "trap 'echo T >&2' EXIT; exec /nonexistent_prog_xyz; echo after"
res = {}
for tag in ("psh", "bash"):
    d, _ = H.setup_rundir(F, "y3_cmode", tag, CMD.encode(), None)
    if tag == "psh":
        argv = [H.PY, "-m", "psh", "--norc", "-c", CMD]
    else:
        argv = [H.BASH, "-c", CMD]
    rc, out, err = H.run_one(argv, d, None)
    res[tag] = {"rc": rc, "out": out, "err": err, "dir": d, "artifacts": {}}
p, b = res["psh"], res["bash"]
pv, bv = H.norm_view(p, p["dir"]), H.norm_view(b, b["dir"])
res["verdict"] = "MATCH" if (pv[0], pv[1], pv[2]) == (bv[0], bv[1], bv[2]) else (
    "STDERR-ONLY" if (pv[0], pv[1]) == (bv[0], bv[1]) else "DIVERGE")
T.cell(F, "y3_cmode", CMD.encode(), res)
T.close()
