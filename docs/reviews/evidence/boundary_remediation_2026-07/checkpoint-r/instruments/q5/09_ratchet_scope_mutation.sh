#!/bin/sh
# Q5 mutation probe: the Q1 shell-consumer ratchet's module scope is frozen at
# the PREDECESSOR campaign's created set; a full-Shell offender in a
# remediation-campaign-created module (psh/scripting/analysis_session.py) is
# invisible to it, while the same offender in a scanned module
# (psh/parser/session.py) is caught. Runs in the Q5 detached worktree ONLY;
# reverts both edits afterwards via git checkout of the two files (worktree is
# detached at ae871a16 with no other local edits to these files).
set -e
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q5/wt
cd "$WT"
OFFENDER='
def q5_synthetic_offender(shell: "Shell") -> None:  # pragma: no cover
    """Checkpoint-R Q5 probe: full-Shell param, must trip the ratchet IF scanned."""
'
echo "== arm A: offender in analysis_session.py (remediation-created, unscanned)"
printf '%s\n' "$OFFENDER" >> psh/scripting/analysis_session.py
python3 -m pytest tests/unit/tooling/test_shell_consumer_ratchet_q1.py -q 2>&1 | tail -3
git checkout -- psh/scripting/analysis_session.py

echo "== arm B: same offender in parser/session.py (scanned CREATED_MODULES member)"
printf '%s\n' "$OFFENDER" >> psh/parser/session.py
python3 -m pytest tests/unit/tooling/test_shell_consumer_ratchet_q1.py -q 2>&1 | tail -6
git checkout -- psh/parser/session.py

echo "== post-state: worktree clean for the two files"
git status --porcelain -- psh/scripting/analysis_session.py psh/parser/session.py
echo DONE
