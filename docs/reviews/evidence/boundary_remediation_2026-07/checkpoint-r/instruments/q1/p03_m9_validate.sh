#!/opt/homebrew/bin/bash
# Q1 probe 03 (MEDIUM-9): state-aware analysis. Base: script enabling extglob
# then using it EXECUTES fine but FAILS --validate. Tip: --validate rc 0.
# Axis: REGRESSION vs recorded base result (execution leg doubles as bash parity).
set -u
WT='/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt'
BASH=/opt/homebrew/bin/bash
cd "$WT" || exit 1
SCRATCH="$WT/tmp/q1m9"; mkdir -p "$SCRATCH"
cat > "$SCRATCH/m9.sh" <<'EOF'
shopt -s extglob
case a in +(a)) echo MATCHED;; esac
EOF

echo "=== execute (psh)"; python -m psh "$SCRATCH/m9.sh"; echo "rc=$?"
echo "=== execute (bash oracle)"; $BASH "$SCRATCH/m9.sh"; echo "rc=$?"
echo "=== psh --validate"; python -m psh --validate "$SCRATCH/m9.sh"; echo "rc=$?"
