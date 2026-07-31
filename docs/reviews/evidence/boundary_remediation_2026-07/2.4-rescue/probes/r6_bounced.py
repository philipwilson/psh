#!/usr/bin/env python3
"""BOUNCED-ROWS REPLAY: every verification round's BLOCKER evidence, at the tip.

Round 6's acceptance condition. Each row below is a behavioural row taken from
a round-1..5 BLOCKER, with the disposition it is supposed to have NOW:

  MATCH             psh must equal bash (the blocker demanded a fix)
  ("DECLARED",      psh must be exactly (rc, stdout) while bash differs (the
   rc, stdout)      blocker was resolved by declaring + pinning the divergence,
                    so the pinned VALUE is what must replay, not equality)

A row whose observed disposition differs from its expected one is printed
FAIL and counted; the audit greps this file's SUMMARY line. Byte-exact probe
FILES, one case per invocation, both parsers, bash 5.2.26 on PATH.

The record/doc blockers (falsified absolutes, false coverage claims, the
accounting) are not shell-observable and are checked by discharge_audit.sh
instead — every one of them is a grep row there.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import discriminator, run  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-r6bounced")

# (round, id, script, channels, expectation)
ROWS = [
    # ---- ROUND 1 blockers 1 & 3: the complete-but-invalid class ------------
    ("R1", "cbi_direct_c", "echo $(fi)\n", ("c",), "MATCH"),
    ("R1", "cbi_procsub_c", "cat <(fi)\n", ("c",), "MATCH"),
    ("R1", "cbi_operand_c", "x=set; echo ${x:-$(fi)}\n", ("c",), "MATCH"),
    ("R1", "cbi_arith_c", "echo $(( $(fi) + 1 ))\n", ("c",), "MATCH"),
    ("R1", "cbi_subscript_c", "a=(1 2); echo ${a[$(fi)]}\n", ("c",), "MATCH"),
    ("R1", "cbi_subscript_assign_c", "a[$(fi)]=v\n", ("c",), "MATCH"),
    ("R1", "cbi_eval_frame", "echo B\neval 'echo X; echo $(fi)'\necho AFTER\n",
     ("c", "file", "stdin"), "MATCH"),
    ("R1", "cbi_function_frame",
     "f() { eval 'echo $(fi)'; }\necho B\nf\necho AFTER\n",
     ("c", "file", "stdin"), "MATCH"),
    ("R1", "cbi_midbuffer", "echo B\necho $(fi)\necho AFTER\n",
     ("c", "file", "stdin"), "MATCH"),
    # ---- ROUND 2 blockers 1 & 2: EXIT-trap teardown ------------------------
    ("R2", "teardown_traceback", "trap 'echo T; echo $(fi); echo T2' EXIT\necho B\n",
     ("c", "file", "stdin"), "MATCH"),
    ("R2", "teardown_status_clobber", "trap 'echo T; echo $(fi)' EXIT\necho B\nexit 3\n",
     ("c", "file", "stdin"), "MATCH"),
    ("R2", "teardown_in_subshell",
     "( trap 'echo CT; echo $(fi)' EXIT; echo IN )\necho AFTER rc=$?\n",
     ("c", "file"), "MATCH"),
    ("R2", "teardown_in_cmdsub",
     "x=$( trap 'echo $(fi)' EXIT; echo IN )\necho AFTER rc=$? x=$x\n",
     ("c", "file"), "MATCH"),
    # ---- ROUND 3 blocker 1: the scanner-classified route (DECLARED+CARRIED)
    ("R3", "scanner_case_direct", "echo B\necho $(case x in)\necho AFTER\n",
     ("c",), ("DECLARED", 2, "B\n")),
    ("R3", "scanner_case_eval", "echo B\neval 'echo $(case x in)'\necho AFTER\n",
     ("c",), ("DECLARED", 0, "B\nAFTER\n")),
    ("R3", "scanner_typed_control", "echo B\necho $(while true)\necho AFTER\n",
     ("c",), "MATCH"),
    # ---- ROUND 3 blocker 3: mid-script trap action inside a fork -----------
    ("R3", "fork_debug_trap",
     "( set -T; trap 'echo $(fi)' DEBUG; echo IN )\necho AFTER rc=$?\n",
     ("c", "file"), ("DECLARED", 0, "AFTER rc=1\n")),
    ("R3", "fork_return_trap",
     "( set -T; trap 'echo $(fi)' RETURN; f() { echo INF; }; f; echo IN )\n"
     "echo AFTER rc=$?\n", ("c", "file"), ("DECLARED", 0, "INF\nAFTER rc=1\n")),
    ("R3", "fork_err_trap",
     "( set -E; trap 'echo $(fi)' ERR; false; echo IN )\necho AFTER rc=$?\n",
     ("c", "file"), ("DECLARED", 0, "AFTER rc=1\n")),
    # ---- ROUND 3 blocker 4: fork x errexit ---------------------------------
    ("R3", "fork_errexit", "( set -e; eval 'echo $(fi)' )\necho AFTER rc=$?\n",
     ("c", "file", "stdin"), "MATCH"),
    # ---- ROUND 4 blocker 3: suppression established INSIDE the child -------
    ("R4", "inchild_or",
     "( set -e; eval 'echo $(if)' || echo in-child rc=$? )\necho AFTER rc=$?\n",
     ("c", "file", "stdin"), "MATCH"),
    ("R4", "inchild_ifcond",
     "( set -e; if eval 'echo $(if)'; then echo T; else echo in-child rc=$?; fi )\n"
     "echo AFTER rc=$?\n", ("c", "file"), "MATCH"),
    # ---- ROUND 4 blocker 4 / ROUND 5 blocker 1: the background fork site ---
    ("R4", "bg_subshell_suppressed",
     "set -e\n{ ( eval 'echo $(if)' ) & wait $!; } || echo GOT rc=$?\n",
     ("c", "file", "stdin"), "MATCH"),
    ("R4", "bg_brace_suppressed",
     "set -e\n{ { eval 'echo $(if)'; } & wait $!; } || echo GOT rc=$?\n",
     ("c", "file"), "MATCH"),
    ("R4", "bg_unsuppressed",
     "set -e\n( eval 'echo $(if)' ) & wait $!\necho AFTER rc=$?\n",
     ("c", "file"), "MATCH"),
    # ---- ROUND 4 blocker 7: posix x fork -----------------------------------
    ("R4", "posix_in_fork",
     "( set -o posix; eval 'echo $(if)' )\necho AFTER rc=$?\n",
     ("c", "file"), "MATCH"),
    # ---- ROUND 4 blocker 1: the main-shell suppressed family ---------------
    ("R4", "main_suppressed_or", "set -e\neval 'echo $(if)' || echo GOT rc=$?\n",
     ("c", "file", "stdin"), "MATCH"),
    ("R4", "main_suppressed_ifcond",
     "set -e\nif eval 'echo $(if)'; then echo T; else echo GOT rc=$?; fi\n",
     ("c", "file"), "MATCH"),
    # ---- ROUND 5 blocker 2: the suppressed FINAL pipeline member -----------
    ("R5", "member_simple_suppressed",
     "set -e\n{ true | eval 'echo $(if)'; } || echo GOT rc=$?\n",
     ("c", "file", "stdin"), "MATCH"),
    ("R5", "member_compound_suppressed",
     "set -e\n{ true | { eval 'echo $(if)'; }; } || echo GOT rc=$?\n",
     ("c", "file"), "MATCH"),
    ("R5", "member_unsuppressed",
     "set -e\n{ true | eval 'echo $(if)'; }\necho AFTER rc=$?\n",
     ("c", "file"), "MATCH"),
    # ---- ROUND 5 blocker 3: the interactive rows (non-PTY half; the PTY
    #      half is r6c_pty.py and the PTY pin module) -------------------------
    ("R5", "ic_fork_errexit_note",
     "( set -e; eval 'echo $(if)' ) || echo SUPPRC=$?\n", ("c",), "MATCH"),
    # ---- ROUND 6 blockers: the severing rule at the BACKGROUND route -------
    ("R6", "bg_bare_simple_suppressed",
     "set -e\n{ eval 'echo $(if)' & } || true\np=$!\n"
     "if wait $p; then echo child=0; else echo child=$?; fi\n",
     ("c", "file", "stdin"), "MATCH"),
    ("R6", "bg_bare_simple_negated",
     "set -e\n! { eval 'echo $(if)' & true; }\np=$!\n"
     "if wait $p; then echo child=0; else echo child=$?; fi\n",
     ("c", "file"), "MATCH"),
    ("R6", "bg_andor_list_suppressed",
     "set -e\n{ : && eval 'echo $(if)' & } || true\np=$!\n"
     "if wait $p; then echo child=0; else echo child=$?; fi\n",
     ("c", "file"), "MATCH"),
    ("R6", "bg_for_loop_suppressed",
     "set -e\n{ for i in 1; do eval 'echo $(fi)'; done & } || true\np=$!\n"
     "if wait $p; then echo child=0; else echo child=$?; fi\n",
     ("c", "file"), "MATCH"),
    # ---- ROUND 6 blockers: the deferral must be ONE-SHOT -------------------
    ("R6", "member_eval_reaches_function",
     "f() { eval 'echo $(if)'; }\nset -e\n"
     "{ true | eval 'f'; } || echo GOT rc=$?\necho END\n",
     ("c", "file", "stdin"), "MATCH"),
    ("R6", "member_source_reaches_function",
     "printf '%s\\n' 'f' > call.sh\nf() { eval 'echo $(if)'; }\nset -e\n"
     "{ true | . ./call.sh; } || echo GOT rc=$?\necho END\n",
     ("c", "file"), "MATCH"),
    # ---- ROUND 6 blockers: the ordinary-errexit co-movements ---------------
    ("R6", "ordinary_member_eval_text",
     "set -e\n{ true | eval 'false; echo A'; } || echo GOT rc=$?\necho END\n",
     ("c", "file"), "MATCH"),
    ("R6", "ordinary_bg_subshell_suppressed",
     "set -e\n{ ( false; echo A ) & wait $!; } || echo GOT rc=$?\necho END\n",
     ("c", "file"), "MATCH"),
    # ---- ROUND 9 blocker: the OPTION axis at the cmdsub creator -----------
    ("R9", "member_cmdsub_inherit_errexit",
     'set -e\nshopt -s inherit_errexit\n'
     '{ true | echo "x=$(false; echo A)"; } || echo GOT rc=$?\necho END\n',
     ("c", "file", "stdin"), "MATCH"),
    ("R9", "member_cmdsub_posix",
     'set -e\nset -o posix\n'
     '{ true | echo "x=$(false; echo A)"; } || echo GOT rc=$?\necho END\n',
     ("c", "file"), "MATCH"),
    ("R9", "member_backtick_inherit_errexit",
     'set -e\nshopt -s inherit_errexit\n'
     '{ true | echo "x=`false; echo A`"; } || echo GOT rc=$?\necho END\n',
     ("c", "file"), "MATCH"),
    ("R9", "member_eval_cmdsub_inherit_composition",
     'set -e\nshopt -s inherit_errexit\n'
     '{ true | eval \'echo "x=$(false; echo A)"\'; } || echo GOT rc=$?\necho END\n',
     ("c", "file"), "MATCH"),
    # ---- ROUND 8 blocker: the member x substitution intersection ----------
    ("R8", "member_argument_procsub",
     "set -e\n{ true | cat <(false; echo A); } || echo GOT rc=$?\necho END\n",
     ("c", "file"), "MATCH"),
    ("R8", "member_redirect_procsub",
     "set -e\n{ true | head -1 < <(false; echo A); } || echo GOT rc=$?\necho END\n",
     ("c", "file"), "MATCH"),
    ("R8", "member_cmdsub_twin",
     'set -e\n{ true | echo "x=$(false; echo A)"; } || echo GOT rc=$?\necho END\n',
     ("c", "file"), "MATCH"),
    ("R6", "ordinary_bg_bare_simple_suppressed",
     "set -e\n{ eval 'false; echo A' & } || true\np=$!\n"
     "if wait $p; then echo child=0; else echo child=$?; fi\n",
     ("c", "file"), "MATCH"),
]


def main():
    os.makedirs(WORK, exist_ok=True)
    print("discriminator:", discriminator(WORK))
    print("bash: /opt/homebrew/bin/bash (PATH oracle, 5.2.26)")
    fails = 0
    total = 0
    for rnd, name, body, channels, expect in ROWS:
        path = os.path.join(WORK, f"{rnd}_{name}.sh")
        with open(path, "wb") as f:
            f.write(body.encode())
        od = subprocess.run(["od", "-c", path], capture_output=True)
        print("=" * 72)
        print(f"[{rnd}] {name}   expect={expect}")
        print(od.stdout.decode().rstrip())
        for channel in channels:
            b = run("bash", path, channel, WORK)
            prd = run("psh", path, channel, WORK, parser="rd")
            pcb = run("psh", path, channel, WORK, parser="combinator")
            total += 1
            same = (b["rc"], b["out"]) == (prd["rc"], prd["out"])
            split = (prd["rc"], prd["out"]) != (pcb["rc"], pcb["out"])
            if expect == "MATCH":
                ok = same and not split
            else:
                _, want_rc, want_out = expect
                ok = ((not same) and prd["rc"] == want_rc
                      and prd["out"] == want_out and not split)
            if not ok:
                fails += 1
            verdict = "PASS" if ok else "FAIL"
            print(f"  {verdict} [{channel}]"
                  f"{'   <<< PARSER SPLIT' if split else ''}")
            print(f"    bash   rc={b['rc']!r} out={b['out']!r}")
            print(f"    psh-rd rc={prd['rc']!r} out={prd['out']!r}")
            if "Traceback (most recent call last)" in prd["err"]:
                fails += 1
                print("    FAIL: TRACEBACK in psh stderr")
            sys.stdout.flush()
    print("=" * 72)
    print(f"SUMMARY: {total - fails}/{total} rows PASS, {fails} FAIL")


if __name__ == "__main__":
    main()
