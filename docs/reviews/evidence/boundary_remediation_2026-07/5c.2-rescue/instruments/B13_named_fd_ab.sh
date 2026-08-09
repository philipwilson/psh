#!/bin/bash
# B13 — A/B byte-identity for the named-fd forms, the surface seam 6 touched.
# Every {var} spelling the extraction routes through _publish_named_fd, plus
# the close form it does NOT route (the control that the seam is scoped).
set -uo pipefail
BASE=/Users/pwilson/src/psh-r5c-2/tmp/w5c2-scratch/base-3a3e0782
NOW=/Users/pwilson/src/psh-r5c-2
export PYTHONDONTWRITEBYTECODE=1

FIX=$(mktemp -d "/Users/pwilson/src/psh-r5c-2/tmp/w5c2-nfd.XXXXXX")
trap 'rm -rf "$FIX"' EXIT
printf 'alpha\nbeta\ngamma\n' > "$FIX/in.txt"

cases=(
  # open-a-file forms (allocate >= 10, publish, scope)
  "exec {v}<$FIX/in.txt; read -u \$v line; echo \"\$line\"; echo fd=\$((v>=10))"
  "exec {w}>$FIX/out1; echo hi >&\$w; exec {w}>&-; cat $FIX/out1"
  "exec {a}>>$FIX/out2; echo one >&\$a; echo two >&\$a; exec {a}>&-; cat $FIX/out2"
  # dup form (the arm carrying the cursor alias)
  "exec {d}<$FIX/in.txt; exec {e}<&\$d; read -u \$d x; read -u \$e y; echo \"\$x|\$y\""
  "exec {d}<$FIX/in.txt; exec {e}<&\$d; read -u \$e y; read -u \$d x; echo \"\$y|\$x\""
  "exec {p}>&1; echo dupped >&\$p"
  # here-document / here-string forms
  "exec {h}<<EOF
one
two
EOF
read -u \$h a; read -u \$h b; echo \"\$a-\$b\""
  "exec {s}<<<'herestring'; read -u \$s t; echo \"\$t\""
  "exec {t}<<-EOF
	tabbed
EOF
read -u \$t u; echo \"\$u\""
  # close form (NOT routed through the helper — scope control)
  "exec {c}<$FIX/in.txt; exec {c}<&-; read -u \$c z; echo rc=\$?"
  # per-command (non-exec) named fd
  "read -u 0 v < $FIX/in.txt; echo \"\$v\""
  "{ echo body; } {q}>$FIX/out3; cat $FIX/out3"
  # error paths
  "exec {bad}<$FIX/missing; echo rc=\$?"
  "exec {n}<&99; echo rc=\$?"
  "echo \${v:-unset}"
)

# The fixture directory MUST be reset before each side. Without this the two
# runs share state and any APPEND case ({v}>>file) shows the second side the
# first side's output — which is a probe artefact that reads exactly like a
# production divergence. Caught that way on the first execution of this
# script; the reset is the fix, not a wider comparison.
reset_fixture() {
    rm -rf "$FIX"
    mkdir -p "$FIX"
    printf 'alpha\nbeta\ngamma\n' > "$FIX/in.txt"
}

fail=0
for c in "${cases[@]}"; do
    reset_fixture
    a=$(cd "$BASE" && python -m psh -c "$c" 2>&1); arc=$?
    reset_fixture
    b=$(cd "$NOW"  && python -m psh -c "$c" 2>&1); brc=$?
    if [ "$a" != "$b" ] || [ "$arc" != "$brc" ]; then
        fail=1
        echo "  *** DIVERGED: $c"
        echo "      base: rc=$arc [$a]"
        echo "      now : rc=$brc [$b]"
    fi
done
echo "cases compared: ${#cases[@]}"
if [ "$fail" -eq 0 ]; then
    echo "VERDICT: byte-identical on all ${#cases[@]} cases (stdout+stderr+rc)"
else
    echo "VERDICT: DIVERGENCE — zero-delta claim broken"
fi
exit $fail
