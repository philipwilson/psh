#!/usr/bin/env python3
"""Slot 2.4 differential harness: bash 5.2.26 vs psh (both parsers).

INDIVIDUAL-RUN PROTOCOL: one case per invocation, no batching.
Probe bodies are written to byte-exact FILES (od -c verifiable) and fed
through the three channels (-c / file / stdin) without shell requoting.
"""
import os
import subprocess
import sys

BASH = "/opt/homebrew/bin/bash"
PSH_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env():
    e = dict(os.environ)
    e["PYTHONPATH"] = PSH_ROOT
    e.pop("PSH_STRICT_ERRORS", None)
    return e


def run(shell, script_path, channel, cwd, parser=None, timeout=20):
    """shell: 'bash' | 'psh'.  channel: 'c' | 'file' | 'stdin'."""
    with open(script_path, "rb") as f:
        body = f.read()
    if shell == "bash":
        base = [BASH]
    else:
        base = [sys.executable, "-m", "psh"]
        if parser:
            base += ["--parser", parser]
    stdin_data = b""
    if channel == "c":
        argv = base + ["-c", body.decode()]
    elif channel == "file":
        argv = base + [script_path]
    elif channel == "stdin":
        argv = base
        stdin_data = body
    else:
        raise ValueError(channel)
    try:
        r = subprocess.run(argv, input=stdin_data, capture_output=True,
                           cwd=cwd, env=_env(), timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"rc": "TIMEOUT", "out": "", "err": ""}
    return {"rc": r.returncode,
            "out": r.stdout.decode(errors="replace"),
            "err": r.stderr.decode(errors="replace")}


def discriminator(cwd):
    """Prove the psh under test is THIS worktree, not the installed package."""
    r = subprocess.run([sys.executable, "-c",
                        "import psh, sys; sys.stdout.write(psh.__file__)"],
                       capture_output=True, cwd=cwd, env=_env())
    return r.stdout.decode()
