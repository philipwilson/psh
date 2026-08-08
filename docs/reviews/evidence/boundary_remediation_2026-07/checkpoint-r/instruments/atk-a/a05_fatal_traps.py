#!/usr/bin/env python3
"""Family F5: 2.4 fatal-substitution syntax x 4A.2 EXIT traps x 4A.1 exec
redirections x errexit.

Composed cells: the $(if -family fatal substitution under EXIT traps, after
permanent exec redirections (artifact files compared), inside trap bodies,
via source frames, and under set -e; child-status severing ($(exit 42))
composed with errexit+trap.

Axis: DIVERGENCE (tip vs bash 5.2.26); REGRESSION vs the 2.4 closure claim
(rc 127, AFTER suppressed on both channels) in the report.
Declared row in scope: exit-trap teardown under errexit is a DECLARED 2.4
divergence -- any t3/t6 mismatch is graded against that pin's domain first.
Proof shape: characterization (two-sided differential).
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a05_fatal_traps.transcript.txt"))
F = "f5fat"

cells = [
    ("t1_fatal_sub_with_exit_trap", b"""trap 'echo TRAP >&2' EXIT
echo $(if)
echo after
""", None, None),
    ("t2_fatal_sub_after_exec_redirect", b"""exec > out.txt
echo $(if)
echo after
""", None, ["out.txt"]),
    ("t3_fatal_sub_errexit_trap", b"""trap 'echo T:$? >&2' EXIT
set -e
echo $(if)
echo after
""", None, None),
    ("t4_fatal_sub_inside_trap_body", b"""trap 'echo $(if)' EXIT
echo main
exit 3
""", None, None),
    ("t5_trap_output_via_dup_fd_after_fatal", b"""exec 3>trace
trap 'echo T >&3' EXIT
echo $(if)
""", None, ["trace"]),
    ("t6_severed_child_status_errexit_trap", b"""trap 'echo T:$? >&2' EXIT
set -e
x=$(exit 42)
echo after
""", None, None),
    ("t7_fatal_sub_via_source_with_trap", b"""printf 'echo $(if)\\necho inner-after\\n' > f.sh
trap 'echo T >&2' EXIT
. ./f.sh
echo outer-after
""", None, None),
    ("t8_fatal_sub_in_cmdsub_redirect_target", b"""trap 'echo T >&2' EXIT
echo hi > "$(if)"
echo after
""", None, None),
]

for name, script, stdin, artifacts in cells:
    T.cell(F, name, script,
           H.run_cell(F, name, script, stdin=stdin, artifacts=artifacts))
T.close()
