#!/usr/bin/env python3
"""atk-a shared harness: two-sided (psh-at-ae871a16 vs bash 5.2.26) cell runner.

Every cell is written as a byte-exact script FILE into a fresh per-(cell,shell)
run directory under <WT>/atkwork/, then executed FILE-MODE (default) with a
controlled environment. Outputs are captured as BYTES and compared raw.

Verdicts:
  MATCH        rc, stdout, stderr all byte-equal
  STDERR-ONLY  rc+stdout equal, stderr differs (psh's standing diagnostic
               wording class -- graded per-cell in the report)
  DIVERGE      rc or stdout differ
  TIMEOUT      either side timed out

The DIVERGENCE axis (tip vs bash) is what these cells measure; REGRESSION
grading (vs LEDGER claims / base at 0215279c) happens in the report.
"""
import os
import signal
import subprocess
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-a/wt"
BASH = "/opt/homebrew/bin/bash"
PY = sys.executable
WORK = os.path.join(WT, "atkwork")
INSTR = "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a"


def make_env(home):
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
        "HOME": home,
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TERM": "dumb",
        "PYTHONPATH": WT,
        "PSH_STRICT_ERRORS": "1",
    }


def run_one(argv, cwd, stdin_bytes, timeout=20):
    """Run argv, return (rc, stdout_bytes, stderr_bytes) or ('TIMEOUT', partial, partial)."""
    env = make_env(cwd)
    try:
        r = subprocess.run(argv, cwd=cwd, env=env, input=stdin_bytes,
                           capture_output=True, timeout=timeout,
                           start_new_session=True)
        return (r.returncode, r.stdout, r.stderr)
    except subprocess.TimeoutExpired as e:
        return ("TIMEOUT", e.stdout or b"", e.stderr or b"")


def setup_rundir(family, cell, shell_tag, script_bytes, files):
    d = os.path.join(WORK, family, cell, shell_tag)
    os.makedirs(d, exist_ok=True)
    sp = os.path.join(d, "cell.sh")
    with open(sp, "wb") as f:
        f.write(script_bytes)
    for name, data in (files or {}).items():
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)
    return d, sp


def normalize(data, rundir):
    """Replace the per-shell rundir path in output bytes so path-bearing
    diagnostics compare equal when only the rundir differs."""
    if data is None:
        return None
    return data.replace(rundir.encode(), b"RUNDIR")


def norm_view(r, rundir):
    return (r["rc"],
            normalize(r["out"], rundir),
            normalize(r["err"], rundir),
            {k: normalize(v, rundir) for k, v in r["artifacts"].items()})


def read_artifacts(rundir, artifacts):
    out = {}
    for a in (artifacts or []):
        p = os.path.join(rundir, a)
        try:
            with open(p, "rb") as f:
                out[a] = f.read()
        except OSError:
            out[a] = None  # absent
    return out


def run_cell(family, cell, script, files=None, stdin=None, artifacts=None,
             psh_extra=None, timeout=20):
    """Run one cell under psh (worktree) and bash. Returns result dict."""
    res = {}
    for tag in ("psh", "bash"):
        d, sp = setup_rundir(family, cell, tag, script, files)
        if tag == "psh":
            argv = [PY, "-m", "psh", "--norc"] + (psh_extra or []) + [sp]
        else:
            argv = [BASH, sp]
        rc, out, err = run_one(argv, d, stdin, timeout)
        res[tag] = {"rc": rc, "out": out, "err": err, "dir": d,
                    "artifacts": read_artifacts(d, artifacts)}
    p, b = res["psh"], res["bash"]
    if p["rc"] == "TIMEOUT" or b["rc"] == "TIMEOUT":
        verdict = "TIMEOUT"
    else:
        prc, pout, perr, part = norm_view(p, p["dir"])
        brc, bout, berr, bart = norm_view(b, b["dir"])
        if (prc, pout, part) == (brc, bout, bart):
            verdict = "MATCH" if perr == berr else "STDERR-ONLY"
        else:
            verdict = "DIVERGE"
    res["verdict"] = verdict
    return res


def run_cell_threeway(family, cell, script, files=None, stdin=None,
                      artifacts=None, timeout=20):
    """psh-rd vs psh-combinator vs bash. Parity axis: rd==pc (internal), rd==bash."""
    res = {}
    for tag, extra in (("rd", ["--parser", "rd"]),
                       ("pc", ["--parser", "combinator"]),
                       ("bash", None)):
        d, sp = setup_rundir(family, cell, tag, script, files)
        if tag == "bash":
            argv = [BASH, sp]
        else:
            argv = [PY, "-m", "psh", "--norc"] + extra + [sp]
        rc, out, err = run_one(argv, d, stdin, timeout)
        res[tag] = {"rc": rc, "out": out, "err": err, "dir": d,
                    "artifacts": read_artifacts(d, artifacts)}
    rd, pc, b = res["rd"], res["pc"], res["bash"]
    krd, kpc, kb = (norm_view(r, r["dir"]) for r in (rd, pc, b))
    key = lambda k: (k[0], k[1], k[3])
    parser_parity = "PARSER-MATCH" if (key(krd) == key(kpc) and krd[2] == kpc[2]) else (
        "PARSER-STDOUT-MATCH" if key(krd) == key(kpc) else "PARSER-DIVERGE")
    vs_bash = "MATCH" if key(krd) == key(kb) else "DIVERGE"
    res["verdict"] = f"{parser_parity}|{vs_bash}"
    return res


def fmt(res, tags=("psh", "bash")):
    lines = []
    for tag in tags:
        r = res[tag]
        lines.append(f"--- {tag}: rc={r['rc']}")
        lines.append(f"    out={r['out']!r}")
        lines.append(f"    err={r['err']!r}")
        for a, v in r["artifacts"].items():
            lines.append(f"    artifact[{a}]={v!r}")
    lines.append(f"VERDICT: {res['verdict']}")
    return "\n".join(lines)


class Transcript:
    def __init__(self, path):
        self.f = open(path, "w")
        self.counts = {}

    def cell(self, family, name, script, res, tags=("psh", "bash"), note=""):
        self.f.write(f"\n=== CELL {family}.{name} ===\n")
        self.f.write("script:\n")
        for ln in script.decode("utf-8", "backslashreplace").splitlines():
            self.f.write("  | " + ln + "\n")
        if note:
            self.f.write("note: " + note + "\n")
        self.f.write(fmt(res, tags) + "\n")
        v = res["verdict"]
        self.counts[v] = self.counts.get(v, 0) + 1
        self.f.flush()
        print(f"{family}.{name}: {v}")

    def close(self):
        self.f.write(f"\nSUMMARY: {self.counts}\n")
        self.f.close()
        print(f"SUMMARY: {self.counts}")


def assert_discriminator():
    env = dict(os.environ)
    env["PYTHONPATH"] = WT
    child = ("import psh, psh.version;"
             "print(psh.__file__); print(psh.version.__version__)")
    r = subprocess.run([PY, "-c", child], cwd=WT, env=env,
                       capture_output=True, text=True, timeout=60)
    f, v = r.stdout.strip().splitlines()
    assert f.startswith(WT + "/") and v == "0.773.0", (f, v)
    return f, v
