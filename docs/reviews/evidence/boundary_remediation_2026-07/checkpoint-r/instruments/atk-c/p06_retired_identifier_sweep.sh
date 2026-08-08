#!/bin/bash
# atk-c p06: Gap 7 closure — resurrection sweep for slot-internal DELETED
# authorities/deciders that sit OUTSIDE (or at the edge of) Q2's nine boundary
# groups. Sources: slot ledgers 2.1, 2.2, 3.1, 3.2, 3.3, 4B.3.
# A retired name reappearing in psh/ (or as a live symbol in tests/) would be a
# resurrection no round-1 scope swept for. grep -F per evidence discipline
# (fixed strings; word-boundary via -w where the name is short/generic).
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-c/wt
cd "$WT" || exit 1

names_fixed=(
  "visit_word_substitution_bodies"   # 2.1 opt-in descent helper, DELETED
  "parse_with_heredocs"              # 2.2 utils facade entry, DELETED with file
  "_ParserWrapper"                   # 2.2/HIGH-5 (in the nine; re-swept for completeness)
  "_substitute_scan"                 # 3.1 retired scanner
  "_seq_nullable"                    # 3.2 retired decider
  "OperandResult"                    # 3.3 retired str-subclass
  "_operand_runs"                    # 3.3 retired walker
  "_value_segments_unquoted"         # 3.3 retired walker
  "_value_dq_text"                   # 3.3 retired walker
  "_file_read_len"                   # 4B.3 retired read-cursor conflation field
  "_file_synced_len"                 # 4B.3 retired prefix marker (in the nine; completeness)
  "heredoc_key"                      # MEDIUM-3 retired plumbing (in the nine; completeness)
)

echo "== psh/ (production) =="
for n in "${names_fixed[@]}"; do
  c=$(grep -rF "$n" psh/ --include='*.py' | wc -l | tr -d ' ')
  echo "psh/  $n : $c"
  [ "$c" != "0" ] && grep -rnF "$n" psh/ --include='*.py' | head -5
done

echo
echo "== tests/ + tools/ (live symbols; ledger/docs excluded by pathspec) =="
for n in "${names_fixed[@]}"; do
  c=$(grep -rF "$n" tests/ tools/ --include='*.py' | wc -l | tr -d ' ')
  echo "tests+tools  $n : $c"
  [ "$c" != "0" ] && grep -rnF "$n" tests/ tools/ --include='*.py' | head -6
done
