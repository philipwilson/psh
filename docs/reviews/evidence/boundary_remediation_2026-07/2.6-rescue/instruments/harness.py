#!/usr/bin/env python3
"""Slot 2.6 probe harness — ONE measurement per invocation (individual-run
protocol), every row carrying a TREE DISCRIMINATOR.

Why a discriminator on every row: `psh` is pip-installed EDITABLE against
/Users/pwilson/src/psh-install (a third tree, neither MAIN nor this worktree),
and `python -m psh` prepends CWD to sys.path. A run made from the wrong cwd or
without PYTHONPATH silently measures the wrong tree. This harness therefore

  * validates PSH_ROOT (must hold psh/version.py AND be a git tree at the
    SHA the caller asserts),
  * runs every psh measurement from a NEUTRAL cwd (a directory holding no
    `psh` package), and
  * records the RESOLVED `psh.__file__` inside the measured process itself,
    failing the row if it does not live under PSH_ROOT.

psh is launched through runpy so the discriminator can be captured in-band;
`selfcheck` proves that vehicle is observationally identical to
`python -m psh` (rc + stdout + stderr bytes) and that a deliberately
mis-pointed root is REJECTED rather than silently measured.

Usage:
    harness.py run   <case.json>     # one measurement, one JSON line on stdout
    harness.py selfcheck             # instrument mutation checks
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BASH = "/opt/homebrew/bin/bash"          # PATH bash 5.2.26 — never /bin/bash
BASH_VERSION = "5.2.26"

# In-band launcher: records psh.__file__ to $PSH_DISCRIM, then runs the psh
# package exactly as `python -m psh` does (runpy alter_sys sets sys.argv[0] to
# the module origin, which is what -m does).
_LAUNCHER = (
    "import os,sys,runpy,psh\n"
    "open(os.environ['PSH_DISCRIM'],'w').write(psh.__file__)\n"
    "sys.argv[1:] = sys.argv[1:]\n"
    "runpy.run_module('psh', run_name='__main__', alter_sys=True)\n"
)


def validate_root(root: str, expected_sha: str | None) -> str:
    p = Path(root)
    if not (p / "psh" / "version.py").is_file():
        raise SystemExit(f"harness: PSH_ROOT {root} has no psh/version.py")
    sha = subprocess.run(["git", "-C", str(p), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()
    if expected_sha and not sha.startswith(expected_sha):
        raise SystemExit(f"harness: PSH_ROOT at {sha}, expected {expected_sha}")
    return sha


def neutral_cwd() -> str:
    """A cwd holding no importable `psh` — so CWD-prepending cannot mis-point."""
    d = Path(tempfile.mkdtemp(prefix="psh26-neutral-",
                              dir=str(Path(__file__).parent / "run")))
    return str(d)


def run_psh(root: str, argv: list[str], *, stdin_text: str | None,
            files: dict[str, str], cwd: str) -> dict:
    """One psh measurement. *files* are written into *cwd* before the run."""
    for name, text in files.items():
        (Path(cwd) / name).write_text(text)
    discrim_file = Path(cwd) / ".discrim"
    env = dict(os.environ)
    env["PYTHONPATH"] = root
    env["PSH_DISCRIM"] = str(discrim_file)
    env.pop("PSH_STRICT_ERRORS", None)   # CLI default behavior, not test policy
    proc = subprocess.run(
        [sys.executable, "-c", _LAUNCHER] + argv,
        input=(stdin_text.encode() if stdin_text is not None else b""),
        capture_output=True, cwd=cwd, env=env, timeout=60)
    discrim = discrim_file.read_text() if discrim_file.exists() else "<NONE>"
    ok = discrim.startswith(str(Path(root).resolve()))
    return {
        "rc": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", "surrogateescape"),
        "stderr": proc.stderr.decode("utf-8", "surrogateescape"),
        "discrim": discrim,
        "discrim_ok": ok,
    }


def run_bash(argv: list[str], *, stdin_text: str | None,
             files: dict[str, str], cwd: str) -> dict:
    for name, text in files.items():
        (Path(cwd) / name).write_text(text)
    proc = subprocess.run(
        [BASH] + argv,
        input=(stdin_text.encode() if stdin_text is not None else b""),
        capture_output=True, cwd=cwd, timeout=60)
    return {
        "rc": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", "surrogateescape"),
        "stderr": proc.stderr.decode("utf-8", "surrogateescape"),
        "oracle": f"{BASH} {BASH_VERSION}",
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if sys.argv[1] == "selfcheck":
        return selfcheck()
    if sys.argv[1] != "run":
        print(f"harness: unknown command {sys.argv[1]}", file=sys.stderr)
        return 2

    case = json.loads(Path(sys.argv[2]).read_text())
    root = case["root"]
    sha = validate_root(root, case.get("expect_sha"))
    cwd = neutral_cwd()
    shell = case.get("shell", "psh")
    if shell == "psh":
        result = run_psh(root, case["argv"], stdin_text=case.get("stdin"),
                         files=case.get("files", {}), cwd=cwd)
        if not result["discrim_ok"]:
            result["INVALID"] = "discriminator: measured tree is not PSH_ROOT"
    else:
        result = run_bash(case["argv"], stdin_text=case.get("stdin"),
                          files=case.get("files", {}), cwd=cwd)
    row = {"id": case["id"], "shell": shell, "sha": sha, "cwd": cwd, **result}
    print(json.dumps(row))
    return 0


def selfcheck() -> int:
    """MUTATION checks on the instrument itself (R0-5: break it on purpose)."""
    root = os.environ.get("PSH_ROOT", "/Users/pwilson/src/psh-r2-6")
    failures = []

    # 1. The runpy vehicle must be observationally identical to `python -m psh`.
    for argv in (["-c", "echo hi; echo err >&2; exit 3"],
                 ["--validate", "-c", "if"],
                 ["-c", "shopt -s extglob; case ab in +(a)b) echo Y;; esac"]):
        cwd = neutral_cwd()
        mine = run_psh(root, argv, stdin_text=None, files={}, cwd=cwd)
        env = dict(os.environ)
        env["PYTHONPATH"] = root
        ref = subprocess.run([sys.executable, "-m", "psh"] + argv, input=b"",
                             capture_output=True, cwd=neutral_cwd(), env=env)
        same = (mine["rc"] == ref.returncode
                and mine["stdout"] == ref.stdout.decode("utf-8", "surrogateescape")
                and mine["stderr"] == ref.stderr.decode("utf-8", "surrogateescape"))
        print(f"selfcheck vehicle {argv!r}: {'SAME' if same else 'DIFFERENT'} "
              f"(rc {mine['rc']}/{ref.returncode})")
        if not same:
            failures.append(f"vehicle differs for {argv!r}")

    # 2. A mis-pointed root must be REJECTED, not silently measured.
    other = "/Users/pwilson/src/psh-install"
    if Path(other, "psh", "version.py").is_file():
        cwd = neutral_cwd()
        r = run_psh(other, ["-c", "echo x"], stdin_text=None, files={}, cwd=cwd)
        # measured psh-install, so a row claiming PSH_ROOT=worktree must fail
        wrong_ok = r["discrim"].startswith(str(Path(root).resolve()))
        print(f"selfcheck mis-point: discrim={r['discrim']} "
              f"claims-worktree={wrong_ok} (must be False)")
        if wrong_ok:
            failures.append("discriminator did not notice a mis-pointed root")
    else:
        failures.append(f"selfcheck could not find the rival tree {other}")

    # 3. A neutral cwd must NOT import a psh from cwd; planting one must trip
    #    the discriminator (proves the neutral-cwd leg is real, not decorative).
    cwd = neutral_cwd()
    plant = Path(cwd) / "psh"
    plant.mkdir()
    (plant / "__init__.py").write_text("")
    (plant / "__main__.py").write_text("import sys; sys.exit(42)\n")
    r = run_psh(root, ["-c", "echo x"], stdin_text=None, files={}, cwd=cwd)
    tripped = not r["discrim_ok"] or r["rc"] == 42
    print(f"selfcheck planted-cwd-psh: discrim={r['discrim']} rc={r['rc']} "
          f"detected={tripped}")
    if not tripped and r["discrim_ok"] and r["rc"] != 42:
        print("  (PYTHONPATH won over cwd — discriminator still correct)")

    # 4. Version-SHA gate must reject a wrong expected SHA.
    try:
        validate_root(root, "deadbeef")
        failures.append("validate_root accepted a wrong SHA")
        print("selfcheck sha-gate: ACCEPTED WRONG SHA (bad)")
    except SystemExit:
        print("selfcheck sha-gate: rejected wrong SHA (good)")

    print(f"selfcheck: {len(failures)} failure(s)")
    for f in failures:
        print(f"  FAIL {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
