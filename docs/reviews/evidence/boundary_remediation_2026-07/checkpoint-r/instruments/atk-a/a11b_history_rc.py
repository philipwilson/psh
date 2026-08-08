#!/usr/bin/env python3
"""F1 addendum: precision cells for the /dev/fd history divergence + the
temp-frame read-side cell.

h1b/h3b: capture `history -w /dev/fd/N` exit status in BOTH shells --
distinguishes fail-loud (rc!=0) from claim-success-write-nothing.
h8: history -r /dev/stdin < seed (temp-frame stdin rebind on the READ side
of the history state machine, 4B.3 x 4B.4).
Proof shape: characterization.
"""
import sys, os, subprocess
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a11b_history_rc.transcript.txt"))
F = "f1hist2"

HI = "history*:echo ===*:cat *:exit:printf *:exec *:sed *:wc *:true *:if *:fi"


def run_int(name, script, files=None, artifacts=None):
    res = {}
    for tag in ("psh", "bash"):
        d, sp = H.setup_rundir(F, name, tag, script, files)
        hf = os.path.join(d, "hist")
        open(hf, "w").close()
        env = H.make_env(d)
        env["HISTFILE"] = hf
        env["HISTIGNORE"] = HI
        argv = ([H.PY, "-m", "psh", "--norc", "-i"] if tag == "psh"
                else [H.BASH, "--norc", "-i"])
        try:
            r = subprocess.run(argv, cwd=d, env=env, input=script,
                               capture_output=True, timeout=25,
                               start_new_session=True)
            rc, out, err = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired as e:
            rc, out, err = "TIMEOUT", e.stdout or b"", e.stderr or b""
        res[tag] = {"rc": rc, "out": out, "err": err, "dir": d,
                    "artifacts": H.read_artifacts(d, artifacts)}
    p, b = res["psh"], res["bash"]
    if p["rc"] == "TIMEOUT" or b["rc"] == "TIMEOUT":
        res["verdict"] = "TIMEOUT"
    else:
        pv, bv = H.norm_view(p, p["dir"]), H.norm_view(b, b["dir"])
        res["verdict"] = ("MATCH" if (pv[0], pv[1], pv[3]) == (bv[0], bv[1], bv[3])
                          else "DIVERGE")
    return res


cells = [
    ("h1b_w_devfd_rc", b"""exec 3>hf3
history -s AAA
history -w /dev/fd/3
echo wrc=$?
exec 3>&-
echo ===F===
cat hf3
exit
""", None, ["hf3"]),
    ("h3b_w_devstdout_rc", b"""history -s DDD
history -w /dev/stdout > cap
echo wrc=$?
echo ===C===
cat cap
exit
""", None, ["cap"]),
    ("h8_r_devstdin_tempframe", b"""history -r /dev/stdin < seed
echo rrc=$?
echo ===L===
history | sed 's/^ *//'
exit
""", {"seed": b"echo Z1\necho Z2\n"}, None),
]

for name, script, files, artifacts in cells:
    T.cell(F, name, script, run_int(name, script, files=files,
                                    artifacts=artifacts))
T.close()
