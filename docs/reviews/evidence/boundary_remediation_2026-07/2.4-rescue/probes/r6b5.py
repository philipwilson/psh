#!/usr/bin/env python3
"""R6-B Q2 completion: the compound-member kinds, INCLUDING `until`.

The integrator's Q2 condition named five compound kinds (if / while / for /
case / until) to be measured BEFORE implementing. r6b4.py covered four; this
battery closes the gap and adds the nesting shapes that would break the
keep-depth prediction if the rule were shallower than stated.

PREDICTION under the ratified rule (a compound command or function BODY DOES
carry the enclosing suppression into a pipeline member): every row here is
bash 1 == psh 1 already, and must stay so after the fix.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r6b5")

CASES = {
    "u1_until_member_suppressed":
        b"set -e\n{ true | until eval 'echo $(if)'; do break; done; }"
        b" || echo GOT rc=$?\n",
    "u2_until_member_unsuppressed":
        b"set -e\n{ true | until eval 'echo $(if)'; do break; done; }\n"
        b"echo AFTER rc=$?\n",
    "u3_until_member_complete_but_invalid":
        b"set -e\n{ true | until eval 'echo $(fi)'; do break; done; }"
        b" || echo GOT rc=$?\n",
    "u4_subshell_inside_brace_member":
        b"set -e\n{ true | { ( eval 'echo $(if)' ); }; } || echo GOT rc=$?\n",
    "u5_function_calling_function_member":
        b"g() { eval 'echo $(if)'; }\nf() { g; }\nset -e\n"
        b"{ true | f; } || echo GOT rc=$?\n",
    "u6_function_inside_brace_member":
        b"f() { eval 'echo $(if)'; }\nset -e\n"
        b"{ true | { f; }; } || echo GOT rc=$?\n",
    "u7_loop_inside_function_member":
        b"f() { for x in 1; do eval 'echo $(if)'; done; }\nset -e\n"
        b"{ true | f; } || echo GOT rc=$?\n",
    "u8_simple_inside_nothing_control":
        b"set -e\n{ true | eval 'echo $(if)'; } || echo GOT rc=$?\n",
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
