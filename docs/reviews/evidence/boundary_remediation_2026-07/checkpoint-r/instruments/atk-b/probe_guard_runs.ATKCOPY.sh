#!/opt/homebrew/bin/bash
# Q2-resurrection: baseline scoped runs of every boundary guard/ratchet at
# ae871a16. Every pytest argument is a FILE or NODE ID (charter-compliant).
# cwd + PYTHONPATH = the Q2 worktree (import discriminator asserted separately
# in probe_discriminator.transcript.txt).
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-b/wt
cd "$WT" || exit 1
export PYTHONPATH="$WT"

echo "== collect count for the generated visitor battery (for the record) =="
python3 -m pytest tests/unit/visitor/test_traversal_totality_battery.py --collect-only -q 2>&1 | tail -2

echo
echo "== guard baseline run (all expected GREEN) =="
python3 -m pytest -q \
  tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py \
  tests/unit/visitor/test_traversal_totality_battery.py \
  tests/unit/tooling/test_heredoc_transaction_guards.py \
  tests/unit/tooling/test_subscript_no_broad_except.py \
  tests/unit/tooling/test_broad_valueerror_catch_q2.py \
  tests/unit/tooling/test_operand_projection_guard.py \
  "tests/unit/scripting/test_analysis_session.py::TestNoUnsanctionedStringSurgery" \
  tests/unit/core/test_env_materialization_p4.py \
  tests/unit/tooling/test_command_resolution_ratchet_r3.py \
  "tests/unit/tooling/test_input_cursor_m8_locks_4b4.py::test_pushback_buffer_is_not_reintroduced" \
  tests/unit/tooling/test_parser_contract_guards_s4.py \
  tests/unit/expansion/test_field_ir_guards.py \
  2>&1 | tail -15
echo "guard-baseline-exit=$?"
