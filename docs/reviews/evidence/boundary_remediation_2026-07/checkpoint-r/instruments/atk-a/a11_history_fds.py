#!/usr/bin/env python3
"""Family F1: 4B.3 history state machine x 4B.4/4A.1 fd machinery.

psh's history builtins are interactive-gated (4B.3 suite pattern), so every
cell drives a piped `--norc -i` shell with its own HISTFILE and a HISTIGNORE
that suppresses scaffolding from being recorded (matched against STORED
text, so it cannot mask `history -s` payloads). Verdict compares rc, stdout
and artifact files; stderr is EXCLUDED by design (interactive prompts).

Cells: history -w/-a/-r through /dev/fd/N spellings over exec-dup'd fds;
temp-frame redirects on the history builtin; read-cursor ops with HISTFILE
appends through dup'd fds.

Axis: DIVERGENCE (tip vs bash 5.2.26); REGRESSION vs the 4B.3 closure rows
graded in the report. Declared rows in scope: the b1-b5 `-a` positional-tail
family -- cells avoid bash's -a tail-window traps except where marked
DECLARED-ADJACENT, graded against the family if divergent.
Proof shape: characterization.
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a11_history_fds.transcript.txt"))
F = "f1hist"

HI = "history*:echo ===*:cat *:exit:printf *:exec *:sed *:wc *:true *:if *:fi"


def run_int(name, script, files=None, artifacts=None, seed_hist=None):
    res = {}
    for tag in ("psh", "bash"):
        d, sp = H.setup_rundir(F, name, tag, script, files)
        hf = os.path.join(d, "hist")
        with open(hf, "w") as f:
            f.write("".join(x + "\n" for x in (seed_hist or [])))
        env = H.make_env(d)
        env["HISTFILE"] = hf
        env["HISTIGNORE"] = HI
        if tag == "psh":
            argv = [H.PY, "-m", "psh", "--norc", "-i"]
        else:
            argv = [H.BASH, "--norc", "-i"]
        rc, out, err = None, None, None
        import subprocess
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
    # h1: history -w through /dev/fd/N over an exec-dup'd fd
    ("h1_w_devfd", b"""exec 3>hf3
history -s AAA
history -s BBB
history -w /dev/fd/3
exec 3>&-
echo ===F===
cat hf3
exit
""", None, ["hf3"], None),
    # h2: HISTFILE pointing AT /dev/fd/N during -w
    ("h2_histfile_devfd", b"""exec 4>hf4
HISTFILE=/dev/fd/4
history -s CCC
history -w
exec 4>&-
echo ===F===
cat hf4
exit
""", None, ["hf4"], None),
    # h3: temp-frame redirect on the history builtin itself (-w to stdout)
    ("h3_w_devstdout_tempframe", b"""history -s DDD
history -w /dev/stdout > cap
echo ===C===
cat cap
exit
""", None, ["cap"], None),
    # h4: history -r through /dev/fd/N from an exec-dup'd READ fd
    ("h4_r_devfd", b"""exec 5<seed5
history -r /dev/fd/5
exec 5<&-
echo ===L===
history | sed 's/^ *//'
exit
""", {"seed5": b"echo S1\necho S2\n"}, None, None),
    # h5: read-cursor ops with HISTFILE appends arriving through a dup'd fd
    ("h5_cursor_with_fd_appends", b"""history -r
exec 6>>"$HISTFILE"
printf 'echo C\\n' >&6
exec 6>&-
history -n
printf 'echo D\\n' >> "$HISTFILE"
history -n
echo ===L===
history | sed 's/^ *//'
exit
""", None, None, ["echo A", "echo B"]),
    # h6: history -a NEW entries to a /dev/fd target (DECLARED-ADJACENT:
    # -a tail-window family; single -s then single -a, no interleaved reads)
    ("h6_a_devfd_declared_adjacent", b"""exec 8>hf8
history -s EEE
history -a /dev/fd/8
exec 8>&-
echo ===F===
cat hf8
exit
""", None, ["hf8"], None),
    # h7: -w then -n composition through a NAMED file (b2-adjacent control
    # kept on the PARITY side: named file, no default-file tail window)
    ("h7_w_named_then_n_default", b"""history -s FFF
history -w named_out
printf 'echo G\\n' >> "$HISTFILE"
history -n
echo ===L===
history | sed 's/^ *//'
echo ===F===
cat named_out
exit
""", None, ["named_out"], None),
]

for name, script, files, artifacts, seed in cells:
    T.cell(F, name, script,
           run_int(name, script, files=files, artifacts=artifacts,
                   seed_hist=seed))
T.close()
