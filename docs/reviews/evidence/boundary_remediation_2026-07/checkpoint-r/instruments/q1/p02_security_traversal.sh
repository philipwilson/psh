#!/opt/homebrew/bin/bash
# Q1 probe 02 (HIGH-2): security traversal reaches executable syntax in
# redirect-only commands, redirect targets, for/case subjects + cmdsub.
# Base (v0.750.0): 4/4 reported "No security issues found!". Tip expectation:
# each reports at least one issue (rc 1), never the false-clean line.
# Axis: REGRESSION vs the recorded base result.
set -u
WT='/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt'
cd "$WT" || exit 1
SCRATCH="$WT/tmp/q1sec"
mkdir -p "$SCRATCH"

cat > "$SCRATCH/s1_redirect_only.sh" <<'EOF'
> $(rm -rf /tmp/psh-never-created-q1)
EOF
cat > "$SCRATCH/s2_redirect_target.sh" <<'EOF'
echo hi > $(rm -rf /tmp/psh-never-created-q1)
EOF
cat > "$SCRATCH/s3_for_subject.sh" <<'EOF'
for i in $(rm -rf /tmp/psh-never-created-q1); do :; done
EOF
cat > "$SCRATCH/s4_case_subject.sh" <<'EOF'
case $(rm -rf /tmp/psh-never-created-q1) in a) : ;; esac
EOF
cat > "$SCRATCH/s5_plain_cmdsub.sh" <<'EOF'
echo $(rm -rf /tmp/psh-never-created-q1)
EOF

for s in s1_redirect_only s2_redirect_target s3_for_subject s4_case_subject s5_plain_cmdsub; do
  echo "=== --security $s"
  out=$(python -m psh --security "$SCRATCH/$s.sh" 2>&1); rc=$?
  echo "$out"
  echo "rc=$rc"
  if printf '%s' "$out" | grep -q "No security issues found"; then
    echo "VERDICT: FALSE-CLEAN (base bug present)"
  else
    echo "VERDICT: reports issues (fixed behavior)"
  fi
done
