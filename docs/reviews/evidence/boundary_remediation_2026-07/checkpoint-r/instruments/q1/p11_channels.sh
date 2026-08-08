#!/opt/homebrew/bin/bash
# Q1 probe 11: shell-channel parity cells for MEDIUM-3 (-c channel of \<<),
# MEDIUM-10 (named-fd heredoc {v}<<EOF now completes+executes = bash),
# HIGH-5 second face (heredoc diagnostics carry real line numbers),
# LOW printf %a (still-OPEN row: confirm still reproduces).
# Axis: DIVERGENCE (tip vs bash 5.2.26).
set -u
WT='/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt'
BASH=/opt/homebrew/bin/bash
cd "$WT" || exit 1
SCRATCH="$WT/tmp/q1ch"; mkdir -p "$SCRATCH"
PSH="python -m psh"

run_file_probe() {
  local label="$1" file="$2"
  local bo brc po prc
  bo=$(cd "$SCRATCH" && $BASH "$file" 2>&1); brc=$?
  po=$(cd "$SCRATCH" && PYTHONPATH="$WT" python -m psh "$file" 2>&1); prc=$?
  echo "=== $label (file channel)"
  echo "  bash: rc=$brc out=[$bo]"
  echo "  psh : rc=$prc out=[$po]"
}

# MEDIUM-3, -c channel: escaped \<< is a '<' word char + '<EOF' input redirect
echo "=== M3 -c channel: echo \\<<EOF"
bo=$(cd "$SCRATCH" && $BASH -c 'echo \<<EOF' 2>&1); brc=$?
po=$(cd "$SCRATCH" && PYTHONPATH="$WT" python -m psh -c 'echo \<<EOF' 2>&1); prc=$?
echo "  bash: rc=$brc out=[$bo]"
echo "  psh : rc=$prc out=[$po]"

# MEDIUM-10: named-fd heredoc — base parse-errored; tip claims completion = bash
cat > "$SCRATCH/m10.sh" <<'EOF'
exec {v}<<HD
hello-from-heredoc
HD
read -u "$v" line
echo "line=$line v-set=${v:+yes}"
EOF
run_file_probe "M10 named-fd heredoc {v}<<HD" "$SCRATCH/m10.sh"

cat > "$SCRATCH/m10b.sh" <<'EOF'
exec {w}<<<here-string-body
read -u "$w" line
echo "line=$line"
EOF
run_file_probe "M10b named-fd here-string {w}<<<" "$SCRATCH/m10b.sh"

# HIGH-5 co-landed face: RD heredoc line numbers (base misreported line 1)
cat > "$SCRATCH/h5line.sh" <<'EOF'
echo first
cat <<BODY
text
BODY
echo $(if)
EOF
run_file_probe "H5-line heredoc-then-error line number" "$SCRATCH/h5line.sh"

# LOW printf %a — OPEN row, expect DIVERGENCE still present
echo "=== LOW printf %a (expect still-divergent, OPEN row)"
bo=$($BASH -c "printf '%.2a\n' 3.14" 2>&1); brc=$?
po=$($PSH -c "printf '%.2a\n' 3.14" 2>&1); prc=$?
echo "  bash: rc=$brc out=[$bo]"
echo "  psh : rc=$prc out=[$po]"
[ "$bo" = "$po" ] && echo "  MATCH (row would be CLOSED?!)" || echo "  DIVERGE (as recorded, row stays OPEN)"
