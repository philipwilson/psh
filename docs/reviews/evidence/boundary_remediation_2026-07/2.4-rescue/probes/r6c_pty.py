#!/usr/bin/env python3
"""R6-C: the INTERACTIVE (real PTY) rows of the substitution-abort family.

PTY facts need PTY instruments. Drives psh (both parsers) and live bash over a
pseudo-terminal with pexpect, one shell per row, and reports what each prints
for the fork x errexit shape and for bare REPL survival.

Rows print a SENTINEL so the answer is read out of the stream rather than
inferred from a prompt (prompt matching races with line-editor redraw).
"""
import os
import re
import sys

import pexpect

PSH_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASH = "/opt/homebrew/bin/bash"

ROWS = {
    # label: the single line to send
    "fork_errexit_suppressed":
        "( set -e; eval 'echo $(if)' ) || echo SUPPRC=$?",
    "fork_errexit_unsuppressed":
        "( set -e; eval 'echo $(if)' ); echo AFTERRC=$?",
    "fork_no_errexit":
        "( eval 'echo $(if)' ) || echo SUPPRC=$?",
    "eval_frame_direct":
        "eval 'echo $(fi)'; echo AFTERRC=$?",
    "direct_complete_but_invalid":
        "echo $(fi); echo AFTERRC=$?",
}


def _env(extra=None):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp", "TERM": "xterm",
        "PS1": "P1> ", "PS2": "P2> ",
        "PYTHONUNBUFFERED": "1", "PYTHONPATH": PSH_ROOT,
    }
    if extra:
        env.update(extra)
    return env


def spawn_psh(parser):
    child = pexpect.spawn(
        sys.executable,
        ["-u", "-m", "psh", "--norc", "--force-interactive",
         "--parser", parser],
        timeout=10, encoding="utf-8", env=_env())
    child.send("\r")
    child.expect("P1> ")
    return child


def spawn_bash():
    child = pexpect.spawn(BASH, ["--norc", "-i"], timeout=10,
                          encoding="utf-8", env=_env())
    child.expect("P1> ")
    return child


def drive(child, line):
    """Send one line, then a sentinel echo; return (transcript, alive)."""
    child.send(line + "\r")
    child.send("echo ALIVE_SENTINEL\r")
    try:
        child.expect("ALIVE_SENTINEL", timeout=5)
        head = child.before
        # the echoed command line itself contains the sentinel; take the
        # SECOND appearance (the output) as proof the REPL executed it
        alive = child.expect(["ALIVE_SENTINEL", pexpect.TIMEOUT],
                             timeout=5) == 0
    except pexpect.TIMEOUT:
        return ("<TIMEOUT>" + (child.before or ""), False)
    return (head, alive)


def report(label, who, transcript, alive):
    supprc = re.search(r"SUPPRC=(\d+)", transcript)
    afterrc = re.search(r"AFTERRC=(\d+)", transcript)
    err = "syntax error" in transcript or "Parse error" in transcript
    tb = "Traceback (most recent call last)" in transcript
    print(f"  {who:14s} SUPPRC={supprc.group(1) if supprc else None} "
          f"AFTERRC={afterrc.group(1) if afterrc else None} "
          f"diagnostic={err} alive={alive} traceback={tb}")
    sys.stdout.flush()


def main():
    print("PSH_ROOT:", PSH_ROOT)
    print("bash:", BASH)
    for label, line in ROWS.items():
        print("=" * 72)
        print(f"{label}: {line!r}")
        for who, spawner in (("bash", spawn_bash),
                             ("psh-rd", lambda: spawn_psh("rd")),
                             ("psh-comb", lambda: spawn_psh("combinator"))):
            child = spawner()
            try:
                transcript, alive = drive(child, line)
            finally:
                child.close(force=True)
            report(label, who, transcript, alive)


if __name__ == "__main__":
    main()
