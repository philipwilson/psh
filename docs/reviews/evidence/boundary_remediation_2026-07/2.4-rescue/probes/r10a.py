#!/usr/bin/env python3
"""R10-A: the OPTION axis my round-9 mechanism claim held constant.

Round 9 concluded, from `$-` inside a cmdsub child, that "the suppression
depth is not observable there at all". True on the DEFAULT-options axis only:
under `shopt -s inherit_errexit` (and `set -o posix`) a cmdsub child DOES
inherit errexit — the exception psh's own command_sub.py comment documents —
so the depth is observable and a severed member's cmdsub child must keep the
pre-sever suppression.

Rows c* are the intersection under each option spelling; b* are the backtick
twin (same creator); p* the procsub side (already fixed in round 9); x* the
`$-` observation that the round-9 claim rested on, now taken on BOTH sides of
the option axis.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r10a")

INHERIT = b"shopt -s inherit_errexit\n"
POSIX = b"set -o posix\n"

CASES = {
    # ---- the blocker: severed member x cmdsub x option spelling ----------
    "c1_member_cmdsub_inherit_errexit":
        b"set -e\n" + INHERIT +
        b"{ true | echo \"x=$(false; echo A)\"; } || echo GOT rc=$?\necho END\n",
    "c2_member_cmdsub_posix":
        b"set -e\n" + POSIX +
        b"{ true | echo \"x=$(false; echo A)\"; } || echo GOT rc=$?\necho END\n",
    "c3_member_cmdsub_default_options":
        b"set -e\n"
        b"{ true | echo \"x=$(false; echo A)\"; } || echo GOT rc=$?\necho END\n",
    # composition: the cmdsub lives inside the member's eval'd TEXT
    "c4_member_eval_cmdsub_inherit":
        b"set -e\n" + INHERIT +
        b"{ true | eval 'echo \"x=$(false; echo A)\"'; } || echo GOT rc=$?\necho END\n",
    # ---- the BACKTICK twin: same creator, so it must ride the same fix ---
    "b1_member_backtick_inherit_errexit":
        b"set -e\n" + INHERIT +
        b"{ true | echo \"x=`false; echo A`\"; } || echo GOT rc=$?\necho END\n",
    "b2_member_backtick_posix":
        b"set -e\n" + POSIX +
        b"{ true | echo \"x=`false; echo A`\"; } || echo GOT rc=$?\necho END\n",
    # ---- the procsub side under the same options (round-9 fix holds?) ----
    "p1_member_procsub_inherit_errexit":
        b"set -e\n" + INHERIT +
        b"{ true | cat <(false; echo A); } || echo GOT rc=$?\necho END\n",
    "p2_member_redirect_procsub_inherit":
        b"set -e\n" + INHERIT +
        b"{ true | head -1 < <(false; echo A); } || echo GOT rc=$?\necho END\n",
    # ---- CONTROLS: the same substitutions OUTSIDE a severed member -------
    "k1_toplevel_cmdsub_inherit_errexit":
        b"set -e\n" + INHERIT + b"echo \"x=$(false; echo A)\"\necho END\n",
    "k2_toplevel_cmdsub_default":
        b"set -e\necho \"x=$(false; echo A)\"\necho END\n",
    "k3_brace_member_cmdsub_inherit":
        b"set -e\n" + INHERIT +
        b"{ true | { echo \"x=$(false; echo A)\"; }; } || echo GOT rc=$?\necho END\n",
    "k4_member_cmdsub_inherit_unsuppressed":
        b"set -e\n" + INHERIT +
        b"{ true | echo \"x=$(false; echo A)\"; }\necho AFTER rc=$?\necho END\n",
    # ---- the $- observation, on BOTH sides of the option axis ------------
    "x1_dash_in_cmdsub_default":
        b"set -e\n"
        b"echo \"dash=$(case $- in *e*) echo ON;; *) echo OFF;; esac)\"\necho END\n",
    "x2_dash_in_cmdsub_inherit":
        b"set -e\n" + INHERIT +
        b"echo \"dash=$(case $- in *e*) echo ON;; *) echo OFF;; esac)\"\necho END\n",
    "x3_dash_in_cmdsub_member_inherit":
        b"set -e\n" + INHERIT +
        b"{ true | echo \"dash=$(case $- in *e*) echo ON;; *) echo OFF;; esac)\"; }"
        b" || true\necho END\n",
    # ---- this slot's own ABORT family under the option axis --------------
    "a1_member_cmdsub_abort_inherit":
        b"set -e\n" + INHERIT +
        b"{ true | eval 'echo $(if)'; } || echo GOT rc=$?\necho END\n",
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
        for channel in ("c", "file", "stdin"):
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
            sys.stdout.flush()


if __name__ == "__main__":
    main()
