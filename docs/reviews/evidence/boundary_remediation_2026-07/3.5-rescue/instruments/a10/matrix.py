"""A10.1 matrix — fatal/discard expansion errors x channel x boundary x set -e.

Both-sides recording against live bash 5.2.26 (/opt/homebrew/bin/bash).
Explicit argv everywhere (no shell word-splitting; the zsh no-split trap).
Run from the worktree root:  python tmp/a10/matrix.py

Observables per cell:
  * shell_rc  — the exit status of the WHOLE shell invocation
  * out/err   — stdout / stderr (stderr normalised only for the psh/bash
                program-name prefix, never for content)
  * after     — the `after rc=N` marker, i.e. whether execution CONTINUED
                past the boundary and with what $? — this is the A10.1
                observable proper.
"""
import os
import subprocess
import sys
import pathlib
import json

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASH = "/opt/homebrew/bin/bash"

# --- discriminator: assert the tree under test BEFORE any cell runs ----------
disc = subprocess.run(
    [sys.executable, "-c",
     "import psh, psh.version as v; print(psh.__file__); print(v.__version__)"],
    cwd=str(ROOT), capture_output=True, text=True,
    env={**os.environ, "PYTHONPATH": str(ROOT)})
_pshfile, _pshver = disc.stdout.split()
assert _pshfile == str(ROOT / "psh" / "__init__.py"), (
    f"WRONG psh TREE: {_pshfile}")
BASHVER = subprocess.run([BASH, "--version"], capture_output=True,
                         text=True).stdout.splitlines()[0]
print(f"# tree under test : {_pshfile}  (psh {_pshver})")
print(f"# oracle          : {BASHVER}")
print(f"# python          : {sys.version.split()[0]}")
print()

ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
for _k in ("PSH_STRICT_ERRORS",):
    ENV.pop(_k, None)

# --- the axes ---------------------------------------------------------------

# error class -> (setup, the failing WORD)
CLASSES = {
    "unset_q":      ("",            "${x?boom}"),      # unset + ? (fatal fam)
    "unset_colonq": ("x=;",         "${x:?boom}"),     # null + :? (fatal fam)
    "badname":      ("",            "${}"),            # bad param NAME
    "unknown_xform": ("v=set;",     "${v@Z}"),         # unknown @X on SET var
    "arith_div0":   ("",            "$((1/0))"),       # fatal arith (discard)
    "bad_subscript": ("",           "${a[1//]}"),      # bad subscript (discard)
}

# boundary -> a template with {W} = the failing word
BOUNDARIES = {
    "direct":     "echo {W}",
    "subshell":   "( echo {W} )",
    "cmdsub":     "vv=$( echo {W} )",
    "backtick":   "vv=`echo {W}`",
    "bracegroup": "{{ echo {W} ; }}",
    "pipeline":   "echo {W} | cat",
}

CHANNELS = ("dashc", "scriptfile", "stdinpipe")
ERREXIT = (False, True)


def build_script(cls, boundary, errexit):
    setup, word = CLASSES[cls]
    body = BOUNDARIES[boundary].format(W=word)
    pre = "set -e; " if errexit else ""
    # The `after` marker is the A10.1 observable: did the shell continue,
    # and with what $?.
    return f'{pre}{setup}{body}; echo "after rc=$?"'


def run(shell_argv0, channel, script, tmpdir):
    if channel == "dashc":
        argv = shell_argv0 + ["-c", script]
        return subprocess.run(argv, cwd=tmpdir, capture_output=True,
                              text=True, env=ENV, timeout=30)
    if channel == "scriptfile":
        p = pathlib.Path(tmpdir) / "s.sh"
        p.write_text(script + "\n")
        argv = shell_argv0 + [str(p)]
        return subprocess.run(argv, cwd=tmpdir, capture_output=True,
                              text=True, env=ENV, timeout=30)
    if channel == "stdinpipe":
        argv = shell_argv0
        return subprocess.run(argv, cwd=tmpdir, input=script + "\n",
                              capture_output=True, text=True, env=ENV,
                              timeout=30)
    raise AssertionError(channel)


PSH = [sys.executable, "-m", "psh"]
BSH = [BASH]


def after_marker(out):
    for line in out.splitlines():
        if line.startswith("after rc="):
            return line.strip()
    return None


def main():
    import tempfile
    rows = []
    with tempfile.TemporaryDirectory(dir=str(ROOT / "tmp")) as td:
        for cls in CLASSES:
            for boundary in BOUNDARIES:
                for channel in CHANNELS:
                    for ee in ERREXIT:
                        script = build_script(cls, boundary, ee)
                        b = run(BSH, channel, script, td)
                        p = run(PSH, channel, script, td)
                        rows.append(dict(
                            cls=cls, boundary=boundary, channel=channel,
                            errexit=ee, script=script,
                            b_rc=b.returncode, p_rc=p.returncode,
                            b_after=after_marker(b.stdout),
                            p_after=after_marker(p.stdout),
                            b_out=b.stdout, p_out=p.stdout,
                            b_err=b.stderr.strip(), p_err=p.stderr.strip(),
                        ))
    (ROOT / "tmp" / "a10" / "matrix.json").write_text(json.dumps(rows, indent=1))

    # --- report -------------------------------------------------------------
    hdr = (f"{'class':<14} {'boundary':<11} {'chan':<11} {'-e':<3} "
           f"{'bash rc':>7} {'psh rc':>6}  {'bash after':<14} {'psh after':<14} V")
    print(hdr)
    print("-" * len(hdr))
    ndiv = 0
    for r in rows:
        same_rc = r["b_rc"] == r["p_rc"]
        same_after = r["b_after"] == r["p_after"]
        verdict = "OK" if (same_rc and same_after) else "DIVERGE"
        if verdict == "DIVERGE":
            ndiv += 1
        print(f"{r['cls']:<14} {r['boundary']:<11} {r['channel']:<11} "
              f"{'y' if r['errexit'] else 'n':<3} {r['b_rc']:>7} {r['p_rc']:>6}  "
              f"{str(r['b_after']):<14} {str(r['p_after']):<14} {verdict}")
    print()
    print(f"# TOTAL {len(rows)} cells, {ndiv} DIVERGE, {len(rows)-ndiv} OK")


if __name__ == "__main__":
    main()
