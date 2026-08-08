#!/bin/sh
# Q3 mutation-proof: the transitive census guard (slot 2.5) BITES.
# Synthetic offender: unfreeze Position in MY DETACHED WORKTREE (never main),
# run the committed guard, expect FAILURES, revert, expect PASS.
set -u
WT="/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q3/wt"
cd "$WT" || exit 1

echo "== offender edit (match count must be exactly 1) =="
COUNT=$(grep -c '^@dataclass(frozen=True)$' psh/lexer/position.py)
echo "matches in position.py: $COUNT"
# edit ONLY the first decorator (line 17, class Position)
sed -i '' '17s/@dataclass(frozen=True)/@dataclass/' psh/lexer/position.py
grep -n "@dataclass" psh/lexer/position.py | head -3

echo "== guard run against the offender (EXPECT FAILURES) =="
python -m pytest tests/unit/lexer/test_lexical_value_graph_frozen.py -q -p no:randomly 2>&1 | tail -5

echo "== revert =="
git checkout -- psh/lexer/position.py
git status --porcelain psh/ | head -3
echo "revert clean: $(git status --porcelain psh/ | wc -l | tr -d ' ') dirty files"

echo "== guard run after revert (EXPECT PASS) =="
python -m pytest tests/unit/lexer/test_lexical_value_graph_frozen.py -q -p no:randomly 2>&1 | tail -3
