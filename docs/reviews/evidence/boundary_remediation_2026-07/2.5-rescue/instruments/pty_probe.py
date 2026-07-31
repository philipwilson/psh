#!/usr/bin/env python3
"""ONE case, ONE shell, ONE PTY: does the shell treat the input as COMPLETE?

Usage:  python3 pty_probe.py <case> <bash|psh> [rd|combinator] [--root DIR]

Individual-run protocol (binding): one invocation per (case, shell, parser)
row -- batching desynchronises PTY state across rows.

DETECTOR (aligned with the committed pin,
tests/system/interactive/test_heredoc_detection_interactive_pty.py): send each
physical line and read the PROMPT that follows it. The answer is the prompt
after the LAST line -- PS1 = complete, PS2 = wants more. Reading per line is
what makes multi-line rows meaningful: during a 3-line heredoc the shell shows
PS2 for lines 1-2 legitimately, so a detector that raced "marker vs any PS2"
called every multi-line row incomplete regardless of its actual outcome.

Both shells are SYNCED with a sentinel command first: psh's line editor redraws
its prompt, so a bare expect(PS1) at spawn can consume a redraw and leave a real
prompt queued, shifting every later read by one.

Reports:
    RESULT case=<c> shell=<s> parser=<p> outcome=<...> prompts=<PS1,PS2,...>
"""
import os
import pathlib
import sys

import pexpect

HERE = pathlib.Path(__file__).resolve().parent
ORACLE = "/opt/homebrew/bin/bash"   # PATH bash 5.2.26 (never /bin/bash)


def env(root):
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp", "TERM": "dumb",
        "PS1": "P1> ", "PS2": "P2> ",
        "PYTHONUNBUFFERED": "1", "PYTHONPATH": root,
    }


def sync(child):
    child.send('echo REA""DY\r')
    child.expect("READY")
    child.expect(r"P1> ")
    return child


def spawn(shell, parser, root, cwd):
    if shell == "bash":
        child = pexpect.spawn(ORACLE, ["--norc", "-i"], timeout=20,
                              encoding="utf-8", env=env(root), cwd=cwd)
    else:
        child = pexpect.spawn(
            sys.executable,
            ["-u", "-m", "psh", "--norc", "--force-interactive",
             "--parser", parser],
            timeout=20, encoding="utf-8", env=env(root), cwd=cwd)
    child.expect(r"P1> ")
    return sync(child)


def main():
    case, shell = sys.argv[1], sys.argv[2]
    parser = (sys.argv[3] if len(sys.argv) > 3
              and not sys.argv[3].startswith("--") else "-")
    root = str(HERE.parents[1])
    if "--root" in sys.argv:
        root = sys.argv[sys.argv.index("--root") + 1]
    cwd = str(HERE / "sandbox")
    pathlib.Path(cwd).mkdir(exist_ok=True)

    raw = (HERE / "inputs" / f"{case}.in").read_bytes().decode()
    lines = raw.split("\n")[:-1]
    # The trailing `echo MARK""ER` is the OLD detector's artifact; the
    # prompt-sequence detector does not need it and it would add a meaningless
    # final row. Drop it when present.
    if lines and lines[-1] == 'echo MARK""ER':
        lines = lines[:-1]

    child = spawn(shell, parser, root, cwd)
    prompts, outcome = [], "timeout"
    try:
        for line in lines:
            child.send(line + "\r")
            # THE CONTEXTUAL-PROMPT ALTERNATIVE. psh does not always use PS2
            # to say "I want more": when the parser reports which CONSTRUCTS
            # are still open it renders a contextual prompt instead ("if> ",
            # "then> ", "for then> " -- interactive/multiline_handler.py). PS2
            # proper covers heredoc bodies, unclosed quotes/expansions and line
            # continuations, which is why every heredoc row in this matrix read
            # correctly while a case opening an `if` block read as a TIMEOUT:
            # the shell answered, in a spelling the detector did not know. A
            # detector that reports "timeout" where the shell actually said
            # "PS2" MANUFACTURES a divergence -- the same false-evidence class
            # this slot has been bounced for -- so the contextual form is
            # recognised and classified as PS2, which is what it means. It sits
            # after the literal patterns so an exact PS1/PS2 always wins.
            i = child.expect([r"P1> ", r"P2> ", r"(?m)^[a-z]+(?: [a-z]+)*> ",
                              pexpect.TIMEOUT], timeout=10)
            if i == 3:
                break
            prompts.append("PS1" if i == 0 else "PS2")
        else:
            outcome = "complete" if prompts[-1] == "PS1" else "incomplete"
    finally:
        child.close(force=True)

    print(f"RESULT case={case} shell={shell} parser={parser} "
          f"outcome={outcome} prompts={','.join(prompts)}")


if __name__ == "__main__":
    main()
