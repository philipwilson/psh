#!/bin/zsh
# Per-file collected-test counts at BASE vs TIP, derived from pytest itself.
set -u
TIP=/Users/pwilson/src/psh-r2-5
BASE=/Users/pwilson/src/psh-r2-5-base
FILES=(
  tests/unit/lexer/test_lexical_value_graph_frozen.py
  tests/unit/io_redirect/test_heredoc_executable_type.py
  tests/unit/parser/test_session_lexer_heredoc_equivalence.py
  tests/system/interactive/test_heredoc_detection_interactive_pty.py
  tests/unit/parser/test_session_linearity_i3.py
  tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py
  tests/unit/tooling/test_syntax_bearing_ast_fields_q2.py
  tests/unit/visitor/test_analysis_visitors.py
  tests/unit/io_redirect/test_redirect_program_r1.py
  tests/unit/lexer/test_heredoc_transaction_s2.py
  tests/unit/parser/combinators/test_commands.py
  tests/integration/redirection/test_heredoc.py
)
count() {  # $1=root $2=relpath ; prints collected count or 0 if absent
  [[ -f "$1/$2" ]] || { echo 0; return; }
  ( cd "$1" && python -m pytest "$2" --collect-only -q -p no:randomly 2>/dev/null \
      | tail -1 | grep -oE '^[0-9]+' ) || echo 0
}
total=0
printf "%-62s %6s %6s %6s\n" FILE BASE TIP DELTA
for f in $FILES; do
  b=$(count $BASE $f); t=$(count $TIP $f)
  b=${b:-0}; t=${t:-0}
  d=$((t - b)); total=$((total + d))
  printf "%-62s %6s %6s %6s\n" "${f:t}" "$b" "$t" "$d"
done
echo "DERIVED TOTAL DELTA: $total"
