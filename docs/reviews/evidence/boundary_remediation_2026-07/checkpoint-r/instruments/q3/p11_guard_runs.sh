#!/bin/sh
# Q3: scoped runs of the COMMITTED guards for each representation (file IDs only).
# Run with cwd = worktree. Transcript = p11_guard_runs.transcript.txt
set -u
WT="/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q3/wt"
cd "$WT" || exit 1
echo "HEAD: $(git rev-parse HEAD)"

run() {
  echo ""
  echo "==== $* ===="
  python -m pytest "$@" -q -p no:randomly 2>&1 | tail -4
}

# R1 Token/TokenPart/Position transitive census
run tests/unit/lexer/test_lexical_value_graph_frozen.py
# R2 pattern engine (incl. all 7 poisoning demos as raise-assertions)
run tests/unit/expansion/test_pattern_engine_immutability.py
# R3 VariableLookup three surfaces
run tests/unit/core/test_variable_lookup_immutability.py
# R4 operand projection ruled-consumer guard (incl. its own offender arms)
run tests/unit/tooling/test_operand_projection_guard.py
# R5 OpenDescription/InputCursorRegistry
run tests/unit/io_redirect/test_input_cursor_registry_4b4.py
run tests/unit/tooling/test_input_cursor_m8_locks_4b4.py
run tests/unit/tooling/test_input_cursor_guard_i1.py
run tests/unit/tooling/test_input_decoder_m8_locks_4b2.py
run tests/integration/redirection/test_input_cursor_contract_4b4.py
# R6 history pending set state machine + M8 locks
run tests/unit/interactive/test_history_state_machine_4b3.py
run tests/unit/tooling/test_history_state_machine_m8_locks_4b3.py
# R7 heredoc executable type + alias route
run tests/unit/io_redirect/test_heredoc_executable_type.py
run tests/unit/scripting/test_heredoc_alias_route.py
# R8 AnalysisSession (derived-state guard both directions + shared chunker)
run tests/unit/scripting/test_analysis_session.py
# A1 resolution-timing ratchet (incl. its own 5 offender arms)
run tests/unit/tooling/test_resolution_timing_ratchet_3_4.py
# A2/A4 conformance pins (live-bash oracle single modules)
run tests/conformance/bash/test_dynamic_special_scoping_conformance.py
run tests/conformance/bash/test_posixly_correct_conformance.py
