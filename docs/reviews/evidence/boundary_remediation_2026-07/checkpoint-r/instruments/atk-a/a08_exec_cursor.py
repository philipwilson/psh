#!/usr/bin/env python3
"""Family F8: 4A.1 failed-exec lease/rollback x 4B.4 InputCursor descriptions
on dup'd fds.

Composed cells: stdin cursors (pipe and file) dup'd to high fds, stdin
rebinds, failed exec redirections (parent and subshell), failed exec
PROGRAM with an EXIT trap that reads through the surviving dup, and the
DECLARED move-form fd-lifetime cell (D-4B.4-s2, verified AS DECLARED).

Axis: DIVERGENCE (tip vs bash 5.2.26). Cursor position after partial
consumption IS the observable.
Proof shape: characterization.
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a08_exec_cursor.transcript.txt"))
F = "f8cur"

DATA = b"L1\nL2\nL3\n"

cells = [
    # x1: PIPE stdin: dup to 5, read one line via dup, rebind stdin, keep
    # reading via dup -- description must survive the rebind
    ("x1_pipe_dup_rebind_read", b"""exec 5<&0
IFS= read -r a <&5
exec </dev/null
IFS= read -r b <&5
printf '<%s><%s>\\n' "$a" "$b"
""", DATA, None, None),
    # x2: FILE stdin (seekable): same shape
    ("x2_file_dup_rebind_read", b"""exec < d3
exec 5<&0
IFS= read -r a <&5
exec </dev/null
IFS= read -r b <&5
printf '<%s><%s>\\n' "$a" "$b"
""", None, {"d3": DATA}, None),
    # x3: failed exec REDIRECT mid-read (non-interactive: shell exits)
    ("x3_failed_exec_redirect_exits", b"""IFS= read -r a
exec 3< nonexistent_file_xyz
echo alive rc=$?
IFS= read -r b
printf '<%s><%s>\\n' "$a" "$b"
""", DATA, None, None),
    # x4: failed exec redirect in a SUBSHELL; parent cursor must be intact
    ("x4_subshell_failed_exec_redirect", b"""IFS= read -r a
( exec 3< nonexistent_file_xyz )
echo rc=$?
IFS= read -r b
printf '<%s><%s>\\n' "$a" "$b"
""", DATA, None, None),
    # x5: failed exec PROGRAM + EXIT trap reading the NEXT line through a
    # live dup (4A.1 x 4A.2 x 4B.4)
    ("x5_failed_exec_prog_trap_reads_dup", b"""exec 5<&0
trap 'IFS= read -r t <&5; printf "T<%s>\\n" "$t" >&2' EXIT
IFS= read -r a <&5
exec ./nonexistent_prog_xyz
echo after
""", DATA, None, None),
    # x5f: same on a seekable FILE stdin
    ("x5f_failed_exec_prog_trap_file", b"""exec < d3
exec 5<&0
trap 'IFS= read -r t <&5; printf "T<%s>\\n" "$t" >&2' EXIT
IFS= read -r a <&5
exec ./nonexistent_prog_xyz
echo after
""", None, {"d3": DATA}, None),
    # x6: DECLARED-VERIFY move-form n<&m- fd lifetime (D-4B.4-s2):
    # bash closes the source fd, psh does not
    ("x6_move_form_lifetime_declared", b"""exec 6< d6
exec 7<&6-
IFS= read -r x <&7
if IFS= read -r y <&6; then echo "6alive<$y>"; else echo "6dead rc=$?"; fi
printf 'x<%s>\\n' "$x"
""", None, {"d6": b"m1\nm2\n"}, None),
    # x7: subshell rebinds ITS OWN stdin; parent pipe cursor undisturbed
    ("x7_subshell_stdin_rebind_isolated", b"""IFS= read -r a
( exec </dev/null; IFS= read -r z; echo "sub<$z> rc=$?" )
IFS= read -r b
printf '<%s><%s>\\n' "$a" "$b"
""", DATA, None, None),
]

for name, script, stdin, files, artifacts in cells:
    T.cell(F, name, script,
           H.run_cell(F, name, script, files=files, stdin=stdin,
                      artifacts=artifacts))
T.close()
