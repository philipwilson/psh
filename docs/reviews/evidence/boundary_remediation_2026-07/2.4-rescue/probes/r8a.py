#!/usr/bin/env python3
"""R8-A: the SPELLING axis my round-7 route claim held constant.

Round 7's ledger said "command substitution, backticks and process
substitution do NOT sever — bash carries the suppression into them". The
corpus behind it (r7a.py rows c1-c6) used only the ARGUMENT spelling of
procsub (`cat <(…)`). This battery varies the spelling: argument vs
REDIRECTION (`< <(…)`, `> >(…)`), read side and write side, with and
without errexit, so the claim is measured over the axis instead of
generalised across it.

Measured independently of the verifier's rows — same question, my own
scripts and my own runs.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r8a")

CASES = {
    # ---- REDIRECTION-spelled procsub, READ side --------------------------
    "p1_redirect_read_ifcond":
        b"set -e\nif read -r line < <(false; echo A); then echo got:$line;"
        b" else echo F:$?; fi\necho END\n",
    "p2_redirect_read_orlist":
        b"set -e\n{ read -r line < <(false; echo A); } || echo GOT rc=$?\n"
        b"echo line=[${line-unset}]\necho END\n",
    "p3_redirect_read_eval_body":
        b"set -e\nif read -r line < <(eval 'false; echo A'); then echo got:$line;"
        b" else echo F:$?; fi\necho END\n",
    "p4_redirect_read_no_errexit":
        b"if read -r line < <(false; echo A); then echo got:$line;"
        b" else echo F:$?; fi\necho END\n",
    # ---- REDIRECTION-spelled procsub, WRITE side -------------------------
    # The WRITE side is inherently ASYNC, so these two rows (a) use a unique
    # file per row, (b) DELETE it first — an earlier row's leftover in the
    # shared work dir made the first version of this battery read stale state
    # and report a parser split that was not there — and (c) settle with a
    # BOUNDED poll instead of `wait`, which does not cover a procsub child in
    # every shell. bash's errexit-killed child never writes; a child that runs
    # on writes promptly.
    "p5_redirect_write_ifcond":
        b"rm -f w5.txt\nset -e\n"
        b"if : > >(false; echo A > w5.txt); then echo ok; else echo F:$?; fi\n"
        b"for i in 1 2 3 4 5 6 7 8 9 10; do [ -f w5.txt ] && break; sleep 0.1; done\n"
        b"if [ -f w5.txt ]; then echo WROTE; else echo NOWRITE; fi\necho END\n",
    "p6_redirect_write_no_errexit":
        b"rm -f w6.txt\n"
        b"if : > >(false; echo A > w6.txt); then echo ok; else echo F:$?; fi\n"
        b"for i in 1 2 3 4 5 6 7 8 9 10; do [ -f w6.txt ] && break; sleep 0.1; done\n"
        b"if [ -f w6.txt ]; then echo WROTE; else echo NOWRITE; fi\necho END\n",
    # ---- ARGUMENT-spelled procsub (the round-7 corpus) -------------------
    "p7_argument_orlist":
        b"set -e\n{ cat <(false; echo A); } || echo GOT rc=$?\necho END\n",
    "p8_argument_eval_body":
        b"set -e\n{ cat <(eval 'false; echo A'); } || echo GOT rc=$?\necho END\n",
    "p9_argument_ifcond":
        b"set -e\nif cat <(false; echo A); then echo T; else echo GOT rc=$?; fi\n"
        b"echo END\n",
    # ---- the substitution-abort twin of the same axis ---------------------
    "p10_redirect_read_abort":
        b"set -e\n{ read -r line < <(eval 'echo $(if)'); } || echo GOT rc=$?\n"
        b"echo END\n",
    "p11_argument_abort":
        b"set -e\n{ cat <(eval 'echo $(if)'); } || echo GOT rc=$?\necho END\n",
    # ---- cmdsub / backtick controls (the rest of the round-7 claim) ------
    "p12_cmdsub_ordinary":
        b"set -e\n{ x=$(false; echo A); } || echo GOT rc=$?\necho x=[$x]\necho END\n",
    "p13_backtick_ordinary":
        b"set -e\n{ x=`false; echo A`; } || echo GOT rc=$?\necho x=[$x]\necho END\n",
    "p14_cmdsub_redirect_input":
        b"set -e\n{ read -r line < <(: ); } || echo GOT rc=$?\necho END\n",
}


def main():
    os.makedirs(WORK, exist_ok=True)
    print("discriminator:", discriminator(WORK))
    for name, body in sorted(CASES.items()):
        path = os.path.join(WORK, name + ".sh")
        with open(path, "wb") as f:
            f.write(body)
        od = subprocess.run(["od", "-c", path], capture_output=True)
        print("=" * 72)
        print(name)
        print(od.stdout.decode().rstrip())
        for channel in ("c", "file"):
            b = run("bash", path, channel, WORK)
            prd = run("psh", path, channel, WORK, parser="rd")
            pcb = run("psh", path, channel, WORK, parser="combinator")
            split = "" if (prd["rc"], prd["out"]) == (pcb["rc"], pcb["out"]) \
                else "   <<< PARSER SPLIT"
            verdict = "MATCH" if (b["rc"], b["out"]) == (prd["rc"], prd["out"]) \
                else "DIVERGE"
            print(f"  [{channel}] {verdict}{split}")
            print(f"    bash   rc={b['rc']!r} out={b['out']!r}")
            print(f"    psh-rd rc={prd['rc']!r} out={prd['out']!r}")
            print(f"    psh-cb rc={pcb['rc']!r} out={pcb['out']!r}")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
