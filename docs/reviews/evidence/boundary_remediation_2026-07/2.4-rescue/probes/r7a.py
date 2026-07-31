#!/usr/bin/env python3
"""R7-A/B: the severing rule at EVERY fork route, and the ordinary-errexit twins.

Round 6 implemented bash's severing rule (a SIMPLE command introduces no
compound body, so an ignored `set -e` does not reach into its own execution)
for pipeline members only. This battery covers the routes the verifiers found
it also governs, plus the two ordinary-errexit families the R6-B change moved
toward bash, plus the cmdsub/procsub routes R7-A asks to be stated.

The child's status is read through `wait $!` for background rows, so the row
observes the CHILD, not the backgrounding command's own 0.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r7a")

CASES = {
    # ---- BACKGROUND route x member kind (the R7-A(1) family) --------------
    "b1_bg_bare_simple_suppressed":
        b"set -e\n{ eval 'echo $(if)' & } || true\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\n",
    "b2_bg_bare_simple_unsuppressed":
        b"set -e\neval 'echo $(if)' &\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\n",
    "b3_bg_bare_simple_negated":
        b"set -e\n! { eval 'echo $(if)' & true; }\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\n",
    "b4_bg_bare_simple_ifcond":
        b"set -e\nif { eval 'echo $(if)' & true; }; then :; fi\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\n",
    "b5_bg_subshell_suppressed":
        b"set -e\n{ ( eval 'echo $(if)' ) & } || true\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\n",
    "b6_bg_brace_suppressed":
        b"set -e\n{ { eval 'echo $(if)'; } & } || true\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\n",
    "b7_bg_function_suppressed":
        b"f() { eval 'echo $(if)'; }\nset -e\n{ f & } || true\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\n",
    "b8_bg_andor_list_suppressed":
        b"set -e\n{ : && eval 'echo $(if)' & } || true\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\n",
    "b9_bg_for_loop_suppressed":
        b"set -e\n{ for i in 1; do eval 'echo $(fi)'; done & } || true\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\n",
    # ---- ONE-SHOT deferral (the R7-A(2) family) --------------------------
    "o1_member_eval_reaches_function":
        b"f() { eval 'echo $(if)'; }\nset -e\n"
        b"{ true | eval 'f'; } || echo GOT rc=$?\necho END\n",
    "o2_member_eval_reaches_function_cbi":
        b"f() { eval 'echo $(fi)'; }\nset -e\n"
        b"{ true | eval 'f'; } || echo GOT rc=$?\necho END\n",
    "o3_member_eval_reaches_function_ifcond":
        b"f() { eval 'echo $(if)'; }\nset -e\n"
        b"if true | eval 'f'; then echo T; else echo GOT rc=$?; fi\necho END\n",
    "o4_member_source_reaches_function":
        b"printf '%s\\n' 'f' > call.sh\nf() { eval 'echo $(if)'; }\nset -e\n"
        b"{ true | . ./call.sh; } || echo GOT rc=$?\necho END\n",
    "o5_member_eval_expansion_function":
        b"f() { eval 'echo $(if)'; }\nQ=f\nset -e\n"
        b"{ true | eval '$Q'; } || echo GOT rc=$?\necho END\n",
    "o6_member_is_the_function_control":
        b"f() { eval 'echo $(if)'; }\nset -e\n"
        b"{ true | f; } || echo GOT rc=$?\necho END\n",
    "o7_member_eval_no_function_control":
        b"set -e\n{ true | eval 'echo $(if)'; } || echo GOT rc=$?\necho END\n",
    # ---- ORDINARY errexit co-movements (the R7-B family) -----------------
    "e1_ordinary_member_eval_text":
        b"set -e\n{ true | eval 'false; echo A'; } || echo GOT rc=$?\necho END\n",
    "e2_ordinary_member_source_text":
        b"printf '%s\\n' 'false' 'echo A' > f.sh\nset -e\n"
        b"{ true | . ./f.sh; } || echo GOT rc=$?\necho END\n",
    "e3_ordinary_member_ifcond":
        b"set -e\nif true | eval 'false; echo A'; then echo T;"
        b" else echo GOT rc=$?; fi\necho END\n",
    "e4_ordinary_member_compound_control":
        b"set -e\n{ true | { eval 'false; echo A'; }; } || echo GOT rc=$?\necho END\n",
    "e5_ordinary_bg_subshell_suppressed":
        b"set -e\n{ ( false; echo A ) & wait $!; } || echo GOT rc=$?\necho END\n",
    "e6_ordinary_bg_subshell_ifcond":
        b"set -e\nif { ( false; echo A ) & wait $!; }; then echo T;"
        b" else echo GOT rc=$?; fi\necho END\n",
    "e7_ordinary_bg_subshell_unsuppressed":
        b"set -e\n( false; echo A ) & wait $!\necho END\n",
    "e8_ordinary_bg_bare_simple_suppressed":
        b"set -e\n{ eval 'false; echo A' & } || true\np=$!\n"
        b"if wait $p; then echo child=0; else echo child=$?; fi\n",
    # ---- cmdsub / procsub routes (R7-A asks what bash does) --------------
    "c1_cmdsub_suppressed":
        b"set -e\n{ x=$(eval 'echo $(if)'); } || echo GOT rc=$?\necho END\n",
    "c2_cmdsub_unsuppressed":
        b"set -e\nx=$(eval 'echo $(if)')\necho AFTER rc=$?\n",
    "c3_cmdsub_ordinary_errexit":
        b"set -e\n{ x=$(eval 'false; echo A'); } || echo GOT rc=$?\necho x=[$x]\n",
    "c4_procsub_suppressed":
        b"set -e\n{ cat <(eval 'echo $(if)'); } || echo GOT rc=$?\necho END\n",
    "c5_procsub_ordinary_errexit":
        b"set -e\n{ cat <(eval 'false; echo A'); } || echo GOT rc=$?\necho END\n",
    "c6_backtick_suppressed":
        b"set -e\n{ x=`eval 'echo $(if)'`; } || echo GOT rc=$?\necho END\n",
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
