#!/bin/sh
# Q3 p10b: same offender as p10 (unfreeze Position in MY worktree), but record
# the FULL failing-row list, to prove the TRANSITIVE CENSUS ROW itself bites
# (not just the per-field pins). Revert afterwards.
set -u
WT="/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q3/wt"
cd "$WT" || exit 1

sed -i '' '17s/@dataclass(frozen=True)/@dataclass/' psh/lexer/position.py
grep -n "@dataclass" psh/lexer/position.py | head -2

python -m pytest tests/unit/lexer/test_lexical_value_graph_frozen.py -q -p no:randomly 2>&1 | grep -E "^FAILED|failed"

git checkout -- psh/lexer/position.py
echo "revert dirty-count: $(git status --porcelain psh/ | wc -l | tr -d ' ')"
python -m pytest tests/unit/lexer/test_lexical_value_graph_frozen.py -q -p no:randomly 2>&1 | tail -1
