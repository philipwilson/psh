#!/usr/bin/env python3
"""R6-B part 4: the edges the proposed placement must NOT move.

k1-k4  : compound-command members other than { } / ( ) — if/while/for/case.
         The proposal gives them no touch point, so they must already match.
k5     : a function resolved at RUNTIME through an expansion ($Q) — proves the
         function restore has to happen at function-body entry, not on the AST.
k6-k8  : simple-command members wearing prefixes (command/assignment/redirect).
k9-k10 : nesting (compound inside compound; function whose body is compound).
k11    : middle member of three, read through PIPESTATUS without a brace group.
k12-k15: the OTHER readers of context.errexit_suppress — the POSIX
         special-builtin suppressible-exit floor, and a plain failing member.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r6b4")

CASES = {
    "k1_if_member_suppressed":
        b"set -e\n{ true | if true; then eval 'echo $(if)'; fi; } || echo GOT rc=$?\n",
    "k2_while_member_suppressed":
        b"set -e\n{ true | while :; do eval 'echo $(if)'; break; done; }"
        b" || echo GOT rc=$?\n",
    "k3_for_member_suppressed":
        b"set -e\n{ true | for x in 1; do eval 'echo $(if)'; done; }"
        b" || echo GOT rc=$?\n",
    "k4_case_member_suppressed":
        b"set -e\n{ true | case x in x) eval 'echo $(if)';; esac; }"
        b" || echo GOT rc=$?\n",
    "k5_func_via_expansion_member":
        b"f() { eval 'echo $(if)'; }\nQ=f\nset -e\n{ true | $Q; } || echo GOT rc=$?\n",
    "k6_command_prefix_member":
        b"set -e\n{ true | command eval 'echo $(if)'; } || echo GOT rc=$?\n",
    "k7_assignment_prefix_member":
        b"set -e\n{ true | X=1 eval 'echo $(if)'; } || echo GOT rc=$?\n",
    "k8_redirected_simple_member":
        b"set -e\n{ true | eval 'echo $(if)' 2>/dev/null; } || echo GOT rc=$?\n",
    "k9_nested_brace_member":
        b"set -e\n{ true | { { eval 'echo $(if)'; }; }; } || echo GOT rc=$?\n",
    "k10_func_with_compound_body_member":
        b"f() { { eval 'echo $(if)'; }; }\nset -e\n{ true | f; } || echo GOT rc=$?\n",
    "k11_middle_of_three_pipestatus":
        b"set -e\ntrue | eval 'echo $(if)' | cat || echo GOT rc=$?\n"
        b"echo PS=${PIPESTATUS[*]}\n",
    "k12_posix_special_builtin_member_suppressed":
        b"set -o posix\nset -e\n{ true | set -q; } || echo GOT rc=$?\necho AFTER\n",
    "k13_posix_special_builtin_member_unsuppressed":
        b"set -o posix\nset -e\n{ true | set -q; }\necho AFTER rc=$?\n",
    "k14_failing_simple_member_suppressed":
        b"set -e\n{ true | false; } || echo GOT rc=$?\n",
    "k15_exit_trap_simple_member_suppressed":
        b"set -e\n{ true | { trap 'echo BYE' EXIT; eval 'echo $(if)'; }; }"
        b" || echo GOT rc=$?\n",
    "k16_exit_trap_set_in_parent_simple_member":
        b"set -e\ntrap 'echo BYE' EXIT\n{ true | eval 'echo $(if)'; } || echo GOT rc=$?\n",
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
