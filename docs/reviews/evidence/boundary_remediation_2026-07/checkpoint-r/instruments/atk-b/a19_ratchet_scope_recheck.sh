#!/opt/homebrew/bin/bash
# atk-b: independent re-verification of q5-F2 (shell-consumer ratchet blind to
# remediation-created modules). Arm A: full-Shell offender in
# psh/scripting/analysis_session.py -> ratchet expected to PASS (blind).
# Arm B: same offender in scanned psh/parser/session.py -> expected FAIL.
# Both reverted; clean status shown.
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-b/wt
cd "$WT" || exit 1
export PYTHONPATH="$WT"
G=tests/unit/tooling/test_shell_consumer_ratchet_q1.py

echo "== Arm A: offender in analysis_session.py (unscanned?) =="
cat >> psh/scripting/analysis_session.py <<'EOF'


def _atkb_offender(shell: 'Shell') -> None:
    return None
EOF
python3 -m pytest -q "$G" 2>&1 | tail -2; a=$?
git -C "$WT" checkout -- psh/scripting/analysis_session.py

echo "== Arm B: same offender in parser/session.py (scanned) =="
cat >> psh/parser/session.py <<'EOF'


def _atkb_offender(shell: 'Shell') -> None:
    return None
EOF
python3 -m pytest -q "$G" 2>&1 | tail -3; b=$?
git -C "$WT" checkout -- psh/parser/session.py

echo "arm-A-exit=$a (0 = ratchet BLIND to analysis_session.py, confirming q5-F2)"
echo "arm-B-exit=$b (nonzero = ratchet bites in scanned module)"
git -C "$WT" status --porcelain; echo "clean-exit=$?"
