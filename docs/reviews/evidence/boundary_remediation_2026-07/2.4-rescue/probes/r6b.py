#!/usr/bin/env python3
"""R6-B: pipeline-member suppression context. bash 5.2.26 vs psh (both parsers).

INDIVIDUAL-RUN PROTOCOL, byte-exact probe FILES, channels -c / file / stdin.
Question: does a pipeline MEMBER inherit the enclosing list's errexit
suppression (like a background subshell does — R6-A) or start unsuppressed?
Probed for the substitution-abort status AND for generic errexit, so the fix
placement can be scoped to what bash actually does.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r6b")

CASES = {
    # --- substitution-abort status through a pipeline member ---
    "p1_final_member_suppressed":
        b"set -e\n{ true | eval 'echo $(if)'; } || echo GOT rc=$?\n",
    "p2_final_member_unsuppressed":
        b"set -e\n{ true | eval 'echo $(if)'; }\necho AFTER rc=$?\n",
    "p3_subshell_member_suppressed":
        b"set -e\n{ true | ( eval 'echo $(if)' ); } || echo GOT rc=$?\n",
    "p4_brace_member_suppressed":
        b"set -e\n{ true | { eval 'echo $(if)'; }; } || echo GOT rc=$?\n",
    "p5_nonfinal_member_suppressed_pipestatus":
        b"set -e\n{ eval 'echo $(if)' | cat; } || echo GOT rc=$?\n"
        b"echo PS=${PIPESTATUS[*]}\n",
    "p6_final_member_no_errexit":
        b"{ true | eval 'echo $(if)'; } || echo GOT rc=$?\n",
    "p7_final_member_negated":
        b"set -e\n! { true | eval 'echo $(if)'; }\necho AFTER rc=$?\n",
    "p8_final_member_if_cond":
        b"set -e\nif true | eval 'echo $(if)'; then echo T; else echo GOT rc=$?; fi\n",
    "p9_final_member_while_cond":
        b"set -e\nwhile true | eval 'echo $(if)'; do echo BODY; break; done\n"
        b"echo AFTER rc=$?\n",
    "p10_final_member_andand_nonfinal":
        b"set -e\n{ true | eval 'echo $(if)'; } && echo T\necho AFTER rc=$?\n",
    "p11_direct_member_suppressed":
        b"set -e\n{ true | echo $(if); } || echo GOT rc=$?\n",
    "p12_func_member_suppressed":
        b"f() { eval 'echo $(if)'; }\nset -e\n{ true | f; } || echo GOT rc=$?\n",
    # --- generic errexit inside a pipeline member (is the member's whole
    #     errexit context unsuppressed in bash, or only this status rule?) ---
    "g1_generic_false_in_brace_member_suppressed":
        b"set -e\n{ true | { false; echo NOPE; }; } || echo GOT rc=$?\n",
    "g2_generic_false_in_subshell_member_suppressed":
        b"set -e\n{ true | ( false; echo NOPE ); } || echo GOT rc=$?\n",
    "g3_generic_false_in_brace_member_unsuppressed":
        b"set -e\n{ true | { false; echo NOPE; }; }\necho AFTER rc=$?\n",
    "g4_generic_func_member_suppressed":
        b"f() { false; echo NOPE; }\nset -e\n{ true | f; } || echo GOT rc=$?\n",
    # --- controls: the background-subshell family R6-A fixed (must not move) ---
    "b1_bg_subshell_suppressed":
        b"set -e\n{ ( eval 'echo $(if)' ) & wait $!; } || echo GOT rc=$?\n",
    "b2_bg_brace_suppressed":
        b"set -e\n{ { eval 'echo $(if)'; } & wait $!; } || echo GOT rc=$?\n",
    "b3_bg_subshell_unsuppressed":
        b"set -e\n( eval 'echo $(if)' ) & wait $!\necho AFTER rc=$?\n",
    # --- controls: fork-site suppression (round-5 verified rows) ---
    "c1_fork_suppressed":
        b"set -e\n( eval 'echo $(if)' ) || echo GOT rc=$?\n",
    "c2_fork_unsuppressed":
        b"set -e\n( eval 'echo $(if)' )\necho AFTER rc=$?\n",
    "c3_in_child_suppressed":
        b"( set -e; eval 'echo $(if)' || echo in-child rc=$? )\necho AFTER rc=$?\n",
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
        for channel in ("c", "file", "stdin"):
            b = run("bash", path, channel, WORK)
            prd = run("psh", path, channel, WORK, parser="rd")
            pcb = run("psh", path, channel, WORK, parser="combinator")
            split = "" if (prd["rc"], prd["out"]) == (pcb["rc"], pcb["out"]) \
                else "   <<< PARSER SPLIT"
            verdict = "MATCH" if (b["rc"], b["out"]) == (prd["rc"], prd["out"]) \
                else "DIVERGE"
            print(f"  [{channel}] {verdict}{split}")
            print(f"    bash rc={b['rc']!r} out={b['out']!r}")
            print(f"    psh-rd  rc={prd['rc']!r} out={prd['out']!r}")
            print(f"    psh-cb  rc={pcb['rc']!r} out={pcb['out']!r}")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
