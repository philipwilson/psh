#!/usr/bin/env python3
"""R6-B part 3: the simple-vs-compound suppression boundary.

Hypothesis from parts 1-2 (bash manual, "compound command or shell function
executing in a context where -e is being ignored"): bash's suppression is
applied by CLEARING -e for the duration of a COMPOUND command / function
body, not by a flag the whole frame reads. A SIMPLE command in a suppressed
context keeps -e effective for anything its own execution starts (an eval'd
string). Probed on both sides of the fork boundary:
  m* = main shell (no fork)      n* = pipeline member, UNsuppressed enclosing
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r6b3")

CASES = {
    # ---- main shell, no fork: is a SIMPLE command's eval suppressed? ----
    "m1_simple_orlist":
        b"set -e\neval 'echo $(if)' || echo GOT rc=$?\n",
    "m2_brace_orlist":
        b"set -e\n{ eval 'echo $(if)'; } || echo GOT rc=$?\n",
    "m3_simple_if_cond":
        b"set -e\nif eval 'echo $(if)'; then echo T; else echo GOT rc=$?; fi\n",
    "m4_simple_negated":
        b"set -e\n! eval 'echo $(if)'\necho AFTER rc=$?\n",
    "m5_func_orlist":
        b"f() { eval 'echo $(if)'; }\nset -e\nf || echo GOT rc=$?\n",
    "m6_simple_unsuppressed":
        b"set -e\neval 'echo $(if)'\necho AFTER rc=$?\n",
    "m7_simple_while_cond":
        b"set -e\nwhile eval 'echo $(if)'; do :; done\necho AFTER rc=$?\n",
    "m8_subshell_orlist":
        b"set -e\n( eval 'echo $(if)' ) || echo GOT rc=$?\n",
    "m9_simple_andand_nonfinal":
        b"set -e\neval 'echo $(if)' && echo T\necho AFTER rc=$?\n",
    # ---- pipeline member, enclosing pipeline NOT suppressed ----
    "n1_brace_member_unsuppressed":
        b"set -e\n{ true | { eval 'echo $(if)'; }; }\necho AFTER rc=$?\n",
    "n2_subshell_member_unsuppressed":
        b"set -e\n{ true | ( eval 'echo $(if)' ); }\necho AFTER rc=$?\n",
    "n3_func_member_unsuppressed":
        b"f() { eval 'echo $(if)'; }\nset -e\n{ true | f; }\necho AFTER rc=$?\n",
    "n4_simple_member_unsuppressed":
        b"set -e\n{ true | eval 'echo $(if)'; }\necho AFTER rc=$?\n",
    # ---- fork (non-member) child: does the suppression reach a SIMPLE
    #      command inside a suppressed subshell? ----
    "n5_simple_in_suppressed_subshell":
        b"set -e\n( eval 'echo $(if)' ) || echo GOT rc=$?\n",
    "n6_simple_in_bg_subshell_suppressed":
        b"set -e\n{ ( eval 'echo $(if)' ) & wait $!; } || echo GOT rc=$?\n",
    # ---- inside-the-child suppression (the round-5 in-child family) ----
    "n7_in_child_simple_suppressed":
        b"( set -e; eval 'echo $(if)' || echo IN rc=$? )\necho AFTER rc=$?\n",
    "n8_in_child_brace_suppressed":
        b"( set -e; { eval 'echo $(if)'; } || echo IN rc=$? )\necho AFTER rc=$?\n",
}


def main():
    os.makedirs(WORK, exist_ok=True)
    print("discriminator:", discriminator(WORK))
    sys.stdout.flush()
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
            nlines = len([x for x in b["err"].splitlines() if x])
            print(f"  [{channel}] {verdict}{split}  bash-err-lines={nlines}")
            print(f"    bash   rc={b['rc']!r} out={b['out']!r}")
            print(f"    psh-rd rc={prd['rc']!r} out={prd['out']!r}")
            print(f"    psh-cb rc={pcb['rc']!r} out={pcb['out']!r}")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
