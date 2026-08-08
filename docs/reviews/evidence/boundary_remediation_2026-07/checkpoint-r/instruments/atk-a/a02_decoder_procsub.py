#!/usr/bin/env python3
"""Family F2: 4B.2 input decoding x 2.3/procsub/cmdsub/forks.

Composed cells: split-multibyte payloads streamed through process
substitution, command substitution, subshell forks, and pipeline members,
consumed with read -N. Payload bytes come from harness-written FILES
(cat'ed), never from printf \\x escapes (declared B#19 ANSI-C high-escape
byte-model carry would contaminate the cells).

Axis: DIVERGENCE (tip vs bash 5.2.26). All reads are blocking (no -t), so
the declared D-4B.2-s1 timeout-partial contract is not in play; the declared
I1 row (d) (builtin->EXTERNAL stranding) is not exercised -- forks here are
subshells/pipeline members, which the declaration does not cover.
Proof shape: characterization (two-sided differential).
"""
import sys, os
sys.path.insert(0, "/Users/pwilson/src/psh/tmp/ckr-probes/atk-a")
import harness as H

H.assert_discriminator()
T = H.Transcript(os.path.join(H.INSTR, "a02_decoder_procsub.transcript.txt"))
F = "f2dec"

EACUTE = b"\xc3\xa9"  # U+00E9 in UTF-8

cells = [
    # d1: read -N across a procsub fd, multibyte inside the count window
    ("d1_procsub_readN", b"""IFS= read -r -N 2 v < <(cat p1)
printf '%s' "$v" | od -An -tx1 | tr -s ' '
printf '#%s\\n' "${#v}"
""", {"p1": b"a" + EACUTE + b"b"}),

    # d2: character split across a TIMED seam in a procsub stream; two
    # sequential -N reads on the same fd
    ("d2_split_seam_two_reads", b"""exec 6< <(cat pa; sleep 0.4; cat pb)
IFS= read -r -N 2 x <&6
IFS= read -r -N 2 y <&6
exec 6<&-
printf '%s' "$x" | od -An -tx1 | tr -s ' '
printf '%s' "$y" | od -An -tx1 | tr -s ' '
""", {"pa": b"a\xc3", "pb": b"\xa9b\n"}),

    # d3: command substitution capturing multibyte from a byte file
    ("d3_cmdsub_capture", b"""v=$(cat p1)
printf '%s' "$v" | od -An -tx1 | tr -s ' '
printf '#%s\\n' "${#v}"
""", {"p1": b"x" + EACUTE}),

    # d4: subshell fork consumes 1 char (2 bytes) from shared fd; parent
    # continues -- decoder lookahead must not strand bytes across the fork
    ("d4_subshell_fork_stranding", b"""exec 6< <(cat p2)
( IFS= read -r -N 1 a <&6; printf '%s' "$a" | od -An -tx1 | tr -s ' ' )
IFS= read -r -N 2 b <&6
printf '%s' "$b" | od -An -tx1 | tr -s ' '
exec 6<&-
""", {"p2": EACUTE + b"qr\n"}),

    # d5: -N loop over a procsub stream with multibyte at chunk boundaries
    ("d5_loop_readN3", b"""while IFS= read -r -N 3 c; do
  printf '%s' "$c" | od -An -tx1 | tr -s ' '
done < <(cat p3)
""", {"p3": b"ab" + EACUTE + b"cd" + EACUTE + b"\n"}),

    # d6: pipeline member does two sequential reads; multibyte at the seam
    ("d6_pipeline_member", b"""cat p1 | { IFS= read -r -N 2 x; IFS= read -r -N 1 y; printf '%s' "$x$y" | od -An -tx1 | tr -s ' '; }
""", {"p1": b"a" + EACUTE + b"b\n"}),

    # d7: single char split across the timed seam, blocking read
    ("d7_split_single_char", b"""IFS= read -r -N 1 v < <(cat pa; sleep 0.4; cat pb)
printf '%s' "$v" | od -An -tx1 | tr -s ' '
""", {"pa": b"\xc3", "pb": b"\xa9\n"}),

    # d8: builtin read then EXTERNAL cat on the same procsub fd.
    # I1 row (d) DECLARES builtin->external stranding for the psh side --
    # this cell verifies it behaves AS DECLARED on a procsub (pipe) fd,
    # where lookahead policy governs; graded against the declaration.
    ("d8_builtin_then_external_declared", b"""exec 6< <(cat p4)
IFS= read -r line <&6
printf 'first<%s>\\n' "$line"
cat <&6
exec 6<&-
""", {"p4": b"one\ntwo\nthree\n"}),
]

for name, script, files in cells:
    T.cell(F, name, script, H.run_cell(F, name, script, files=files))
T.close()
