#!/bin/zsh
# The MEDIUM-3 spelling matrix under a REAL PTY, INDIVIDUAL-RUN protocol:
# one pty_probe.py PROCESS per (case, shell, parser) row. Output is the
# derived table -- never hand-tallied.
#
# Usage: ./run_pty_matrix.sh <outfile>
set -u
cd "$(dirname "$0")"
out="${1:?usage: run_pty_matrix.sh <outfile>}"
: > "$out"
echo "# SHA: $(git rev-parse HEAD)" >> "$out"
echo "# bash oracle: /opt/homebrew/bin/bash $(/opt/homebrew/bin/bash --version | head -1)" >> "$out"
echo "# psh: $(python3 -c 'import sys; sys.path.insert(0,"../..");
import psh; print(psh.__file__, psh.version.__version__)' 2>/dev/null || echo unknown)" >> "$out"
for f in inputs/*.in; do
  case="${f:t:r}"
  for row in "bash -" "psh rd" "psh combinator"; do
    shell="${row% *}"; parser="${row#* }"
    python3 pty_probe.py "$case" "$shell" "$parser" 2>&1 | grep '^RESULT' >> "$out"
  done
done
# Orphan sweep (binding: after EVERY PTY battery).
pkill -f 'pty_probe.py' 2>/dev/null
pkill -f 'psh --norc --force-interactive' 2>/dev/null
echo "# orphan sweep done: $(pgrep -f 'force-interactive' | wc -l | tr -d ' ') survivors" >> "$out"
# DERIVED COUNTS. The previous version escaped the quotes around "$out" inside
# the command substitutions, so grep was handed a filename with literal quote
# characters, found nothing, and every anchor since carried the empty
# `rows= cases=0`. A derived count that silently derives NOTHING is worse than
# a hand tally, because it reads as machine evidence -- found while re-anchoring
# for R12-D, and the same class as the certification's mis-anchors.
rows=$(grep -c '^RESULT' "$out" | tr -d ' ')
cases=$(grep '^RESULT' "$out" | sed 's/.*case=\([^ ]*\).*/\1/' | sort -u | wc -l | tr -d ' ')
echo "# DERIVED: rows=${rows} cases=${cases}" >> "$out"
cat "$out"
