#!/usr/bin/env python3
"""R6-C: the -i -c fork shape, and the STATIC-CHECK spellings (-n / --validate).

Two questions, both raised by the round-5 verifier:
  1. within the `-i -c` channel, does anything OTHER than the direct shape
     differ? (the round-5 pin's docstring says no — measured here)
  2. psh's `-n` moved 2 -> 127 with the slot (matching bash), but psh's other
     static-check spelling `--validate` stayed at 2, so the two now disagree
     with each other on the same input. Both are measured, at both commits, so
     the disagreement is a recorded fact rather than an accident.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import _env  # noqa: E402

PSH_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASH = "/opt/homebrew/bin/bash"
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r6c")

# (label, script) — run through the -i -c channel for both shells.
IC_ROWS = {
    "fork_errexit_suppressed": "( set -e; eval 'echo $(if)' ) || echo SUPPRC=$?",
    "fork_no_errexit": "( eval 'echo $(if)' ) || echo SUPPRC=$?",
    "eval_frame": "echo B; eval 'echo $(fi)'; echo AFTER",
    "direct": "echo B; echo $(fi); echo AFTER",
    "eval_frame_status": "eval 'echo $(fi)'; echo AFTERRC=$?",
}

# (label, script) — run through each shell's static-check spelling.
STATIC_ROWS = {
    "unclosed_body": "echo $(if)",
    "complete_but_invalid_body": "echo $(fi)",
    "procsub_body": "cat <(if)",
    "plain_syntax_error": "if",          # CONTROL: not substitution-origin
    "valid": "echo hi",                  # CONTROL: nothing wrong at all
}


def run(argv, stdin=b"", cwd=WORK):
    r = subprocess.run(argv, input=stdin, capture_output=True, cwd=cwd,
                       env=_env(), timeout=30)
    return r.returncode, r.stdout.decode(errors="replace")


def main():
    os.makedirs(WORK, exist_ok=True)
    disc = subprocess.run([sys.executable, "-c",
                           "import psh, sys; sys.stdout.write(psh.__file__)"],
                          capture_output=True, cwd=WORK, env=_env())
    print("discriminator:", disc.stdout.decode())

    print("=" * 72)
    print("-i -c CHANNEL")
    for label, script in IC_ROWS.items():
        brc, bout = run([BASH, "-i", "-c", script])
        for parser in ("rd", "combinator"):
            prc, pout = run([sys.executable, "-m", "psh", "--parser", parser,
                             "-i", "-c", script])
            verdict = "MATCH" if (brc, bout) == (prc, pout) else "DIVERGE"
            print(f"  {verdict:7s} {label:26s} [{parser:10s}] "
                  f"bash=({brc}, {bout!r}) psh=({prc}, {pout!r})")
            sys.stdout.flush()

    print("=" * 72)
    print("STATIC CHECK: bash -n  vs  psh -n  vs  psh --validate")
    for label, script in STATIC_ROWS.items():
        path = os.path.join(WORK, label + ".sh")
        with open(path, "wb") as f:
            f.write(script.encode() + b"\n")
        brc, _ = run([BASH, "-n", "-c", script])
        brc_file, _ = run([BASH, "-n", path])
        for parser in ("rd", "combinator"):
            n_rc, _ = run([sys.executable, "-m", "psh", "--parser", parser,
                           "-n", "-c", script])
            n_file, _ = run([sys.executable, "-m", "psh", "--parser", parser,
                             "-n", path])
            v_rc, _ = run([sys.executable, "-m", "psh", "--parser", parser,
                           "--validate", "-c", script])
            v_file, _ = run([sys.executable, "-m", "psh", "--parser", parser,
                             "--validate", path])
            print(f"  {label:26s} [{parser:10s}] "
                  f"bash -n: c={brc} file={brc_file} | "
                  f"psh -n: c={n_rc} file={n_file} | "
                  f"psh --validate: c={v_rc} file={v_file}")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
