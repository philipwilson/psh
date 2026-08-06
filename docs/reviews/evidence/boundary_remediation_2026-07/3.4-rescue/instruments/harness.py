#!/usr/bin/env python3
"""A8 ordering matrix harness — slot 3.4.

Runs each case through live bash (PATH bash, MUST be /opt/homebrew/bin/bash
5.2.26) and psh (imported from THIS worktree — discriminator-checked), in a
selectable INPUT MODE, and emits RAW OUTPUT PAIRS (3.3 lesson: verdict tags
hide DIFF->DIFF content changes).

Usage:  python tmp/a8/harness.py <cases_module.py> [--mode -c|script|stdin]
                                 [--parser rd|combinator]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

# PSH_TREE lets Phase A measure a DETACHED prototype checkout; it defaults to
# this worktree. The discriminator below hard-fails if psh imports elsewhere.
PSH_ROOT = os.environ.get("PSH_TREE", "/Users/pwilson/src/psh-r3-4")
BASH = "/opt/homebrew/bin/bash"


def _validate_instrument() -> dict:
    """Hard-fail unless bash is the declared oracle and psh is THIS tree."""
    if os.path.realpath(os.getcwd()) != os.path.realpath(PSH_ROOT):
        sys.exit(f"INSTRUMENT FAIL: cwd {os.getcwd()} != {PSH_ROOT}")
    ver = subprocess.run([BASH, "--version"], capture_output=True, text=True)
    bash_ver = ver.stdout.splitlines()[0]
    if "5.2.26" not in bash_ver:
        sys.exit(f"INSTRUMENT FAIL: bash version {bash_ver!r}")
    which = subprocess.run(["which", "bash"], capture_output=True, text=True)
    if which.stdout.strip() != BASH:
        sys.exit(f"INSTRUMENT FAIL: PATH bash is {which.stdout.strip()!r}")
    # psh must import from this worktree, not the integrator checkout.
    disc = subprocess.run(
        [sys.executable, "-c", "import psh; print(psh.__file__); "
         "import psh.version; print(psh.version.__version__)"],
        capture_output=True, text=True, cwd=PSH_ROOT)
    psh_file = disc.stdout.splitlines()[0] if disc.stdout else "<none>"
    if not psh_file.startswith(PSH_ROOT + "/"):
        sys.exit(f"INSTRUMENT FAIL: psh imports from {psh_file!r}")
    return {
        "bash_version": bash_ver,
        "bash_path": BASH,
        "psh_file": psh_file,
        "psh_version": disc.stdout.splitlines()[1],
        "python": sys.version.split()[0],
    }


def _run(argv_prefix, script, mode, cwd):
    """Run `script` under a shell, in the given INPUT MODE."""
    env = dict(os.environ)
    # Hermetic-ish: strip things that perturb either shell's startup.
    for k in ("BASH_ENV", "ENV", "PS1", "PS4", "POSIXLY_CORRECT",
              "SHELLOPTS", "IFS", "RANDOM"):
        env.pop(k, None)
    env["LC_ALL"] = "C"
    try:
        if mode == "-c":
            return subprocess.run(argv_prefix + ["-c", script],
                                  capture_output=True, text=True,
                                  timeout=25, cwd=cwd, env=env)
        if mode == "script":
            with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                             dir=os.path.join(PSH_ROOT, "tmp", "a8"),
                                             encoding="utf-8") as fh:
                fh.write(script + "\n")
                path = fh.name
            try:
                return subprocess.run(argv_prefix + [path],
                                      capture_output=True, text=True,
                                      timeout=25, cwd=cwd, env=env)
            finally:
                os.unlink(path)
        if mode == "stdin":
            return subprocess.run(argv_prefix, input=script + "\n",
                                  capture_output=True, text=True,
                                  timeout=25, cwd=cwd, env=env)
    except subprocess.TimeoutExpired:
        class _T:
            stdout, stderr, returncode = "<TIMEOUT>", "<TIMEOUT>", -99
        return _T()
    raise ValueError(mode)


def run_case(script, mode="-c", parser="rd", cwd=None):
    cwd = cwd or PSH_ROOT
    bash_r = _run([BASH], script, mode, cwd)
    psh_argv = [sys.executable, "-m", "psh"]
    if parser != "rd":
        psh_argv += ["--parser", parser]
    psh_r = _run(psh_argv, script, mode, cwd)
    return {
        "bash": {"out": bash_r.stdout, "err": bash_r.stderr,
                 "rc": bash_r.returncode},
        "psh": {"out": psh_r.stdout, "err": psh_r.stderr,
                "rc": psh_r.returncode},
    }


def _norm_err(text, shell):
    """Strip the shell-name prefix so error TEXT can be compared separately."""
    return text.replace("psh: ", "").replace("bash: ", "").replace(
        "-bash: ", "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("--mode", default="-c", choices=["-c", "script", "stdin"])
    ap.add_argument("--parser", default="rd", choices=["rd", "combinator"])
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    meta = _validate_instrument()
    ns = {}
    with open(args.cases, encoding="utf-8") as fh:
        exec(compile(fh.read(), args.cases, "exec"), ns)
    cases = ns["CASES"]

    print("=" * 78)
    print(f"A8 MATRIX  cases={args.cases}  mode={args.mode}  parser={args.parser}")
    for k, v in meta.items():
        print(f"  {k}: {v}")
    print("=" * 78)

    results = []
    n_match = n_diff = 0
    for cid, desc, script in cases:
        r = run_case(script, mode=args.mode, parser=args.parser)
        same_out = r["bash"]["out"] == r["psh"]["out"]
        same_rc = r["bash"]["rc"] == r["psh"]["rc"]
        same_err_text = _norm_err(r["bash"]["err"], "bash") == \
            _norm_err(r["psh"]["err"], "psh")
        verdict = "MATCH" if (same_out and same_rc) else "DIFF"
        if verdict == "MATCH":
            n_match += 1
        else:
            n_diff += 1
        results.append({"id": cid, "desc": desc, "script": script,
                        "verdict": verdict, "same_err_text": same_err_text,
                        **r})
        print(f"\n--- [{cid}] {verdict}{'' if same_err_text else ' (err-text differs)'}"
              f"  {desc}")
        print(f"    $ {script}")
        print(f"    bash: rc={r['bash']['rc']} out={r['bash']['out']!r}"
              f" err={r['bash']['err']!r}")
        print(f"    psh : rc={r['psh']['rc']} out={r['psh']['out']!r}"
              f" err={r['psh']['err']!r}")

    print("\n" + "=" * 78)
    print(f"TOTALS: {len(cases)} cases, {n_match} MATCH, {n_diff} DIFF")
    print("=" * 78)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"meta": meta, "mode": args.mode, "parser": args.parser,
                       "results": results}, fh, indent=1)
        print(f"raw pairs -> {args.json}")


if __name__ == "__main__":
    main()
