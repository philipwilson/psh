#!/usr/bin/env python3
"""R5-A: the COMPOSITE `!!` observable, at a real terminal.

The question the function-level probe could NOT answer. At BASE, the session
also (wrongly) held `echo \\<<EOF` incomplete, so the mirror's misdetection was
CONSISTENT with the session state and the following line was swallowed anyway.
At TIP the session correctly COMPLETES that line, so `echo !!` is a FRESH
command line -- and if the mirror's pending here-document state persists across
that completion, history expansion gets suppressed on a line where bash expands
it. That composite did not exist at base in the same form, so "the mirror
function is base-identical" does not bound it.

So this probe records WHICH COMMAND ACTUALLY EXECUTED:

    echo FIRST          <- establishes a history entry
    echo \\<<EOF         <- complete in bash; the mirror thinks a body opened
    echo !!             <- expanded, or literal?

If `!!` expanded, the shell re-runs the previous command line and we see its
text/output. If suppressed, `!!` stays literal and `echo !!` prints `!!`.

Usage: python3 history_composite_probe.py <bash|psh> [rd|combinator] [--root D]
"""
import os
import pathlib
import sys
import tempfile

import pexpect

HERE = pathlib.Path(__file__).resolve().parent
ORACLE = "/opt/homebrew/bin/bash"


def env(root, histfile):
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp", "TERM": "dumb",
        "PS1": "P1> ", "PS2": "P2> ",
        "HISTFILE": histfile, "HISTSIZE": "500",
        "PYTHONUNBUFFERED": "1", "PYTHONPATH": root,
    }


def main():
    shell = sys.argv[1]
    parser = (sys.argv[2] if len(sys.argv) > 2
              and not sys.argv[2].startswith("--") else "-")
    root = str(HERE.parents[1])
    if "--root" in sys.argv:
        root = sys.argv[sys.argv.index("--root") + 1]

    cwd = tempfile.mkdtemp()
    histfile = os.path.join(cwd, "hist")
    e = env(root, histfile)

    if shell == "bash":
        child = pexpect.spawn(ORACLE, ["--norc", "-i"], timeout=20,
                              encoding="utf-8", env=e, cwd=cwd)
    else:
        child = pexpect.spawn(
            sys.executable,
            ["-u", "-m", "psh", "--norc", "--force-interactive",
             "--parser", parser],
            timeout=20, encoding="utf-8", env=e, cwd=cwd)
    child.expect(r"P1> ")

    transcript = ""
    try:
        # 1. establish a history entry with a DISTINCTIVE output
        child.send("echo HISTMARK\r")
        child.expect(r"P1> ")
        transcript += (child.before or "") + (child.after or "")

        # 2. the escaped spelling: complete in bash, mirror thinks otherwise
        child.send("echo \\<<EOF\r")
        i = child.expect([r"P1> ", r"P2> ", pexpect.TIMEOUT], timeout=10)
        transcript += (child.before or "") + (child.after or "")
        after_escaped = {0: "PS1", 1: "PS2", 2: "TIMEOUT"}[i]

        # 3. THE OBSERVABLE: does `!!` expand on this line?
        child.send("echo !!\r")
        i2 = child.expect([r"P1> ", r"P2> ", pexpect.TIMEOUT], timeout=10)
        tail = (child.before or "") + (child.after or "")
        transcript += tail
    finally:
        child.close(force=True)

    # `!!` EXPANDED  -> the re-run command's output (HISTMARK) appears again,
    #                   or the echoed expansion text does.
    # `!!` SUPPRESSED-> the literal two characters are printed.
    expanded = "HISTMARK" in tail or "echo \\<<EOF" in tail
    literal = "!!" in tail.replace("echo !!", "", 1)

    print(f"RESULT shell={shell} parser={parser} "
          f"after_escaped={after_escaped} "
          f"bang_expanded={expanded} bang_literal={literal}")
    print("--- tail ---")
    print(repr(tail[-400:]))


if __name__ == "__main__":
    main()
