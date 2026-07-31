#!/usr/bin/env python3
"""R6-F: the fork x EXIT-teardown x errexit corner, and the member EXIT trap.

t1  = the round-5 verifier's unpinned corner (set -e INSIDE the fork, EXIT
      action carrying the error). The pinned teardown row next to it (t5) has
      no set -e, which is why the corner escaped.
t2  = the pinned DEBUG-trap composition control (must not move).
t3  = the main-shell errexit x teardown row (round-4 NIT).
t4/t6/t7 = does a pipeline MEMBER run its own EXIT trap at all, on the abort
      and on an ordinary failure?
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r6f")

CASES = {
    "t1_fork_errexit_exit_trap_action_error":
        b"( set -e; trap 'echo $(fi)' EXIT; echo IN )\necho AFTER rc=$?\n",
    "t1b_fork_errexit_exit_trap_unclosed_kind":
        b"( set -e; trap 'echo $(if)' EXIT; echo IN )\necho AFTER rc=$?\n",
    "t2_fork_errexit_debug_trap_action_error":
        b"( set -e; set -T; trap 'echo $(fi)' DEBUG; echo IN )\necho AFTER rc=$?\n",
    "t3_main_errexit_exit_trap_action_error":
        b"set -e\ntrap 'echo $(fi)' EXIT\necho IN\n",
    "t4_member_exit_trap_on_abort":
        b"set -e\n{ true | { trap 'echo BYE' EXIT; eval 'echo $(if)'; }; }"
        b" || echo GOT rc=$?\n",
    "t5_fork_exit_trap_action_error_no_errexit":
        b"( trap 'echo CT; echo $(fi)' EXIT; echo IN )\necho AFTER rc=$?\n",
    "t6_member_exit_trap_on_ordinary_failure":
        b"set -e\n{ true | { trap 'echo BYE' EXIT; false; }; } || echo GOT rc=$?\n",
    "t7_member_exit_trap_on_clean_exit":
        b"{ true | { trap 'echo BYE' EXIT; echo OK; }; }\necho AFTER rc=$?\n",
    "t8_subshell_exit_trap_on_abort":
        b"set -e\n( trap 'echo BYE' EXIT; eval 'echo $(if)' ) || echo GOT rc=$?\n",
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
            print(f"    bash   rc={b['rc']!r} out={b['out']!r}")
            print(f"    psh-rd rc={prd['rc']!r} out={prd['out']!r}")
            print(f"    psh-cb rc={pcb['rc']!r} out={pcb['out']!r}")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
