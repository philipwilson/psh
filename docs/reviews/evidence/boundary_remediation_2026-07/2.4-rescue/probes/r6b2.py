#!/usr/bin/env python3
"""R6-B part 2: WHICH member shapes carry the suppression, with stderr.

The part-1 battery (r6b.py) showed bash treats a SIMPLE-COMMAND pipeline
member as unsuppressed (2) but a ( ) / { } / function member as suppressed
(1) — so a blanket "members start at seed 0" would REGRESS the shapes that
already match. These cases separate frame-continuation from status so the
placement can be scoped exactly.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r6b2")

CASES = {
    "s1_brace_member_continues":
        b"set -e\n{ true | { eval 'echo $(if)'; echo INMEM; }; } || echo GOT rc=$?\n",
    "s2_subshell_member_continues":
        b"set -e\n{ true | ( eval 'echo $(if)'; echo INSUB ); } || echo GOT rc=$?\n",
    "s3_func_member_continues":
        b"f() { eval 'echo $(if)'; echo INFUNC; }\nset -e\n"
        b"{ true | f; } || echo GOT rc=$?\n",
    "s4_simple_member_plain":
        b"set -e\n{ true | eval 'echo $(if)'; } || echo GOT rc=$?\n",
    "s5_func_member_unsuppressed":
        b"f() { eval 'echo $(if)'; }\nset -e\n{ true | f; }\necho AFTER rc=$?\n",
    "s6_pipeline_is_the_orleft":
        b"set -e\ntrue | eval 'echo $(if)' || echo GOT rc=$?\n",
    "s7_nonfinal_member_no_brace":
        b"set -e\neval 'echo $(if)' | cat || echo GOT rc=$?\necho PS=${PIPESTATUS[*]}\n",
    "s8_middle_member_of_three":
        b"set -e\n{ true | eval 'echo $(if)' | cat; } || echo GOT rc=$?\n"
        b"echo PS=${PIPESTATUS[*]}\n",
    "s9_simple_member_complete_but_invalid":
        b"set -e\n{ true | eval 'echo $(fi)'; } || echo GOT rc=$?\n",
    "s10_simple_member_procsub":
        b"set -e\n{ true | eval 'cat <(if)'; } || echo GOT rc=$?\n",
    "s11_brace_member_complete_but_invalid":
        b"set -e\n{ true | { eval 'echo $(fi)'; }; } || echo GOT rc=$?\n",
    "s12_simple_member_source":
        b"printf '%s\\n' \"echo \\$(if)\" > sub.sh\nset -e\n"
        b"{ true | . ./sub.sh; } || echo GOT rc=$?\n",
    "s13_fork_suppressed_continues":
        b"set -e\n( eval 'echo $(if)'; echo INCHILD ) || echo GOT rc=$?\n",
    "s14_simple_member_no_eval_runtime":
        b"set -e\nQ='echo $(if)'\n{ true | $Q; } || echo GOT rc=$?\n",
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
            print(f"  [{channel}] {verdict}{split}")
            print(f"    bash   rc={b['rc']!r} out={b['out']!r}")
            print(f"    bash   err={b['err']!r}")
            print(f"    psh-rd rc={prd['rc']!r} out={prd['out']!r}")
            print(f"    psh-rd err={prd['err']!r}")
            print(f"    psh-cb rc={pcb['rc']!r} out={pcb['out']!r}")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
