#!/usr/bin/env python3
"""Base-provenance runs at 0215279c (v0.750.0, campaign base): psh side ONLY
of the three divergent cells found at tip (bash side is constant).

B1: EXIT trap after failed `exec PROG` (tip: psh runs trap, bash doesn't).
B2: pipeline-member $RANDOM determinism (tip: psh deterministic, bash reseeds).
B2b: subshell $RANDOM mechanism at base (provenance of the reseed behavior).
B3: history -w /dev/fd/3 over an exec-dup'd fd (tip: psh writes, bash empty).
B4: declared move-form control (D-4B.4-s2 says PRE-EXISTING; confirm).

Discriminator: psh.__file__ under the BASE worktree, __version__ == 0.750.0.
Proof shape: characterization (base-vs-tip provenance).
"""
import os
import subprocess
import sys

WTB = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-a/wtbase"
PY = sys.executable
OUT = "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a/a12_base_provenance.transcript.txt"
WORK = os.path.join(WTB, "atkwork")

log = open(OUT, "w")


def say(s):
    log.write(s + "\n")
    log.flush()
    print(s)


env_base = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
    "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8", "TERM": "dumb",
    "PYTHONPATH": WTB, "PSH_STRICT_ERRORS": "1",
}

r = subprocess.run(
    [PY, "-c", "import psh, psh.version; print(psh.__file__); print(psh.version.__version__)"],
    cwd=WTB, env=dict(os.environ, PYTHONPATH=WTB), capture_output=True, text=True)
f, v = r.stdout.strip().splitlines()
assert f.startswith(WTB + "/"), f
say(f"BASE discriminator: psh.__file__={f} version={v}")
assert v == "0.750.0", v
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WTB,
                      capture_output=True, text=True).stdout.strip()
say(f"BASE HEAD={head}")
assert head.startswith("0215279c")


def run_psh_script(name, script_bytes, stdin=None, interactive=False,
                   files=None, hist_env=False, artifacts=None):
    d = os.path.join(WORK, name)
    os.makedirs(d, exist_ok=True)
    for fn, data in (files or {}).items():
        with open(os.path.join(d, fn), "wb") as fh:
            fh.write(data)
    env = dict(env_base, HOME=d)
    if hist_env:
        hf = os.path.join(d, "hist")
        open(hf, "w").close()
        env["HISTFILE"] = hf
        env["HISTIGNORE"] = ("history*:echo ===*:cat *:exit:printf *:exec *:"
                             "sed *:wc *:true *:if *:fi")
    if interactive:
        argv = [PY, "-m", "psh", "--norc", "-i"]
        inp = script_bytes
    else:
        sp = os.path.join(d, "cell.sh")
        with open(sp, "wb") as fh:
            fh.write(script_bytes)
        argv = [PY, "-m", "psh", "--norc", sp]
        inp = stdin
    r = subprocess.run(argv, cwd=d, env=env, input=inp,
                       capture_output=True, timeout=25, start_new_session=True)
    arts = {}
    for a in (artifacts or []):
        p = os.path.join(d, a)
        arts[a] = open(p, "rb").read() if os.path.exists(p) else None
    say(f"--- BASE-psh {name}: rc={r.returncode}")
    say(f"    out={r.stdout!r}")
    say(f"    err={r.stderr!r}")
    for a, val in arts.items():
        say(f"    artifact[{a}]={val!r}")
    return r


# B1: exec-fail trap
run_psh_script("B1_execfail_trap", b"trap 'echo T >&2' EXIT\nexec /nonexistent_prog_xyz\necho after\n")

# B2: pipeline-member RANDOM, twice
for i in (0, 1):
    run_psh_script(f"B2_pipeline_random_{i}",
                   b"RANDOM=5\necho $RANDOM | cat\necho $RANDOM | cat\n")

# B2b: subshell RANDOM mechanism, twice
for i in (0, 1):
    run_psh_script(f"B2b_subshell_random_{i}",
                   b"RANDOM=5\n( echo $RANDOM )\n( echo $RANDOM )\n")

# B3: history -w /dev/fd/3 (interactive)
run_psh_script("B3_hist_w_devfd", b"""exec 3>hf3
history -s AAA
history -s BBB
history -w /dev/fd/3
exec 3>&-
echo ===F===
cat hf3
exit
""", interactive=True, hist_env=True, artifacts=["hf3"])

# B4: declared move-form control
run_psh_script("B4_move_form", b"""IFS= read -r a
true 3<&0-
if IFS= read -r b; then echo "alive<$b>"; else echo "dead rc=$?"; fi
printf 'a<%s>\\n' "$a"
""", stdin=b"L1\nL2\nL3\n")

say("BASE-PROVENANCE-DONE")
log.close()
