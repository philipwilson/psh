#!/bin/bash
# A8 — zero-witness censuses for the two registered dead-API rows.
# Denominator is STATED per cell. The `with_redirections` cell must distinguish
# the target symbol from the DIFFERENT symbol `_execute_builtin_with_redirections`
# (the brief's warning) — done by anchoring on the dot.
set -uo pipefail
cd /Users/pwilson/src/psh-r5c-2

echo "############ CELL 1 — IOManager.with_redirections (D-4B.4-s3)"
echo "--- 1a. definition site(s), whole repo, tracked files only"
git grep -n "def with_redirections" -- '*.py'
echo "--- 1b. DENOMINATOR: every occurrence of the string 'with_redirections' in tracked files"
git grep -c "with_redirections" | sort -t: -k2 -rn
echo "--- 1c. total occurrences"
git grep -o "with_redirections" | wc -l
echo "--- 1d. SPLIT: occurrences that are the DIFFERENT symbol _execute_builtin_with_redirections"
git grep -o "_execute_builtin_with_redirections" | wc -l
echo "--- 1e. CALL SITES of the target: '.with_redirections(' (attribute call), tracked files"
git grep -n "\.with_redirections(" || echo "    ZERO attribute-call sites"
echo "--- 1f. bare-name call sites 'with_redirections(' NOT preceded by _builtin_ and NOT a def"
git grep -n "with_redirections(" | grep -v "_execute_builtin_with_redirections" | grep -v "def with_redirections"
echo "--- 1g. residue: every remaining mention, classified by hand in the report"
git grep -n "with_redirections" | grep -v "_execute_builtin_with_redirections"

echo
echo "############ CELL 2 — state.foreground_pgid (D-5B.2-dead)"
echo "--- 2a. DENOMINATOR: every occurrence of 'foreground_pgid' in tracked files"
git grep -c "foreground_pgid" | sort -t: -k2 -rn
echo "--- 2b. total occurrences"
git grep -o "foreground_pgid" | wc -l
echo "--- 2c. every occurrence with file:line (the full chain)"
git grep -n "foreground_pgid"
echo
echo "--- 2d. SPLIT by symbol: publish_foreground_pgid vs bare foreground_pgid"
echo -n "    publish_foreground_pgid occurrences: "; git grep -o "publish_foreground_pgid" | wc -l
echo -n "    bare foreground_pgid occurrences:    "
git grep -o "[^_]foreground_pgid\|^foreground_pgid" | wc -l
echo
echo "--- 2e. production-only (psh/) occurrences, READ vs WRITE shape"
git grep -n "foreground_pgid" -- 'psh/*.py' 'psh/**/*.py'
