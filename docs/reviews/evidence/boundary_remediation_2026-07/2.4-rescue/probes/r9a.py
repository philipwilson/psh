#!/usr/bin/env python3
"""R9-A: the member x SUBSTITUTION intersection, and why cmdsub differs.

Round 8's spelling battery (r8a.py) varied the SPELLING axis but held the
ROUTE axis constant — no row put a substitution inside a SEVERED pipeline
member. That intersection is where the severing leaked.

Rows m* are the intersection itself (argument procsub, redirect procsub,
cmdsub, backtick, inside a simple member and inside compound controls).
Rows x* answer the ruling's "why did cmdsub NOT regress" question by
OBSERVATION rather than by reading the code: they ask each substitution
child what `set -e` and the suppression look like FROM INSIDE.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r9a")

CASES = {
    # ---- the intersection: a substitution inside a SEVERED simple member --
    "m1_member_argument_procsub":
        b"set -e\n{ true | cat <(false; echo A); } || echo GOT rc=$?\necho END\n",
    "m2_member_redirect_procsub":
        b"set -e\n{ true | head -1 < <(false; echo A); } || echo GOT rc=$?\n"
        b"echo END\n",
    "m3_member_cmdsub":
        b"set -e\n{ true | echo \"x=$(false; echo A)\"; } || echo GOT rc=$?\n"
        b"echo END\n",
    "m4_member_backtick":
        b"set -e\n{ true | echo \"x=`false; echo A`\"; } || echo GOT rc=$?\n"
        b"echo END\n",
    # ---- controls: the same substitutions in NON-severed member shapes ----
    "m5_brace_member_argument_procsub":
        b"set -e\n{ true | { cat <(false; echo A); }; } || echo GOT rc=$?\necho END\n",
    "m6_bg_argument_procsub":
        b"set -e\n{ cat <(false; echo A) & } || true\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\necho END\n",
    "m7_toplevel_active_errexit":
        b"set -e\ncat <(false; echo A)\necho END\n",
    "m8_member_argument_procsub_unsuppressed":
        b"set -e\n{ true | cat <(false; echo A); }\necho AFTER rc=$?\necho END\n",
    # ---- the ABORT twins of the same intersection (this slot's family) ----
    "m9_member_argument_procsub_abort":
        b"set -e\n{ true | eval 'cat <(if)'; } || echo GOT rc=$?\necho END\n",
    "m10_member_cmdsub_abort":
        b"set -e\n{ true | eval 'echo $(if)'; } || echo GOT rc=$?\necho END\n",
    # ---- WHY: what does each substitution child see from INSIDE? ---------
    # `$-` contains 'e' when the errexit OPTION is set in that child.
    "x1_cmdsub_child_sees_errexit":
        b"set -e\n{ true | echo \"dash=$(case $- in *e*) echo ON;; *) echo OFF;; esac)\"; }"
        b" || true\necho END\n",
    "x2_procsub_child_sees_errexit":
        b"set -e\n{ true | cat <(case $- in *e*) echo ON;; *) echo OFF;; esac); }"
        b" || true\necho END\n",
    "x3_cmdsub_child_toplevel":
        b"set -e\necho \"dash=$(case $- in *e*) echo ON;; *) echo OFF;; esac)\"\necho END\n",
    "x4_procsub_child_toplevel":
        b"set -e\ncat <(case $- in *e*) echo ON;; *) echo OFF;; esac)\necho END\n",
    # does a failing command actually ABORT each child?
    "x5_cmdsub_child_aborts":
        b"set -e\necho \"x=$(false; echo A)\"\necho END\n",
    "x6_procsub_child_aborts":
        b"set -e\ncat <(false; echo A)\necho END\n",
}


def main():
    os.makedirs(WORK, exist_ok=True)
    print("discriminator:", discriminator(WORK))
    for name, body in sorted(CASES.items(), key=lambda kv: (kv[0][0], len(kv[0]), kv[0])):
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
            sys.stdout.flush()


if __name__ == "__main__":
    main()
