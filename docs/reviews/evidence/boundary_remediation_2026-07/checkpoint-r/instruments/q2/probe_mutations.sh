#!/opt/homebrew/bin/bash
# Q2-resurrection: mutation-proof pass. For each deleted-boundary guard, plant a
# synthetic offender IN THE Q2 WORKTREE, run the guard's exact node ID (expect
# RED), revert the offender, re-run (expect GREEN). A guard only seen passing is
# unverified (evidence rule 4).
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q2/wt
cd "$WT" || exit 1
export PYTHONPATH="$WT"

run_guard() { # $1 = node id
  python3 -m pytest -q "$1" 2>&1 | tail -4
  return "${PIPESTATUS[0]}"
}

verdict() { # $1 label, $2 red_exit, $3 green_exit
  if [ "$2" -ne 0 ] && [ "$3" -eq 0 ]; then
    echo "MUTATION-VERDICT $1: BITES (red=$2 on offender, green after revert)"
  else
    echo "MUTATION-VERDICT $1: *** GUARD-DOES-NOT-BITE (red_exit=$2 green_exit=$3) ***"
  fi
}

# ---------------------------------------------------------------- M1 anti-spawn
echo "##### M1: raw spawn in a conformance module (HIGH-1) #####"
cat > tests/conformance/bash/test_q2res_offender.py <<'EOF'
import subprocess


def test_q2res_offender():
    subprocess.run(["true"])
EOF
run_guard "tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py::test_no_direct_spawn_in_oracle_bearing_modules"; red=$?
rm tests/conformance/bash/test_q2res_offender.py
run_guard "tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py::test_no_direct_spawn_in_oracle_bearing_modules"; green=$?
verdict M1-antispawn "$red" "$green"

# ------------------------------------------------------------- M2 visitor bypass
echo; echo "##### M2: analysis visitor overrides visit() (HIGH-2) #####"
grep -q "class LinterVisitor" psh/visitor/linter_visitor.py || echo "PRECHECK-FAIL: LinterVisitor not in linter_visitor.py"
cat >> psh/visitor/linter_visitor.py <<'EOF'


def _q2res_offender_visit(self, node):
    return None


LinterVisitor.visit = _q2res_offender_visit
EOF
run_guard "tests/unit/visitor/test_traversal_totality_battery.py::test_analysis_visitor_cannot_bypass_the_sweep"; red=$?
git -C "$WT" checkout -- psh/visitor/linter_visitor.py
run_guard "tests/unit/visitor/test_traversal_totality_battery.py::test_analysis_visitor_cannot_bypass_the_sweep"; green=$?
verdict M2-visitor-bypass "$red" "$green"

# ---------------------------------------------------- M3 heredoc second caller
echo; echo "##### M3: second production caller of heredoc_terminator_matches (MEDIUM-3) #####"
cat >> psh/scripting/input_preprocessing.py <<'EOF'


def _q2res_offender(line):
    from ..utils.heredoc_detection import heredoc_terminator_matches
    return heredoc_terminator_matches(line, 'EOF', False)
EOF
run_guard "tests/unit/tooling/test_heredoc_transaction_guards.py::TestOneCloseDecision::test_single_production_caller"; red=$?
git -C "$WT" checkout -- psh/scripting/input_preprocessing.py
run_guard "tests/unit/tooling/test_heredoc_transaction_guards.py::TestOneCloseDecision::test_single_production_caller"; green=$?
verdict M3-heredoc-close "$red" "$green"

# ------------------------------------------------------------ M4 broad except
echo; echo "##### M4: except Exception back in subscript.py (MEDIUM-12a) #####"
cat >> psh/expansion/subscript.py <<'EOF'


def _q2res_offender():
    try:
        return 1
    except Exception:
        return 0
EOF
run_guard "tests/unit/tooling/test_subscript_no_broad_except.py::test_guarded_modules_have_no_broad_except"; red=$?
git -C "$WT" checkout -- psh/expansion/subscript.py
run_guard "tests/unit/tooling/test_subscript_no_broad_except.py::test_guarded_modules_have_no_broad_except"; green=$?
verdict M4-broad-except "$red" "$green"

# ------------------------------------------------------- M5 unruled projection
echo; echo "##### M5: as_scalar() outside the ruled consumer set (HIGH-6/3.3) #####"
cat >> psh/expansion/manager.py <<'EOF'


def _q2res_offender(v):
    return v.as_scalar()
EOF
run_guard "tests/unit/tooling/test_operand_projection_guard.py::test_projection_called_only_from_ruled_consumers"; red=$?
git -C "$WT" checkout -- psh/expansion/manager.py
run_guard "tests/unit/tooling/test_operand_projection_guard.py::test_projection_called_only_from_ruled_consumers"; green=$?
verdict M5-projection "$red" "$green"

# ------------------------------------------------------------ M6 string surgery
echo; echo "##### M6: unsanctioned string surgery in analysis_session.py (2.6) #####"
cat >> psh/scripting/analysis_session.py <<'EOF'


def _q2res_offender(word):
    return word.replace('x', 'y')
EOF
run_guard "tests/unit/scripting/test_analysis_session.py::TestNoUnsanctionedStringSurgery::test_every_string_surgery_site_is_sanctioned"; red=$?
git -C "$WT" checkout -- psh/scripting/analysis_session.py
run_guard "tests/unit/scripting/test_analysis_session.py::TestNoUnsanctionedStringSurgery::test_every_string_surgery_site_is_sanctioned"; green=$?
verdict M6-surgery "$red" "$green"

# ---------------------------------------------------------- M7 dispatch read
echo; echo "##### M7: raw get_function dispatch read in command.py (R3) #####"
cat >> psh/executor/command.py <<'EOF'


def _q2res_offender(fm, name):
    return fm.get_function(name)
EOF
run_guard "tests/unit/tooling/test_command_resolution_ratchet_r3.py::test_command_py_has_no_raw_dispatch_reads"; red=$?
git -C "$WT" checkout -- psh/executor/command.py
run_guard "tests/unit/tooling/test_command_resolution_ratchet_r3.py::test_command_py_has_no_raw_dispatch_reads"; green=$?
verdict M7-dispatch "$red" "$green"

# ------------------------------------------------------------- M8 pushback name
echo; echo "##### M8: _pushback name back in input_reader.py (4B.4 P1) #####"
cat >> psh/builtins/input_reader.py <<'EOF'


_Q2RES_OFFENDER = "_pushback"
EOF
run_guard "tests/unit/tooling/test_input_cursor_m8_locks_4b4.py::test_pushback_buffer_is_not_reintroduced"; red=$?
git -C "$WT" checkout -- psh/builtins/input_reader.py
run_guard "tests/unit/tooling/test_input_cursor_m8_locks_4b4.py::test_pushback_buffer_is_not_reintroduced"; green=$?
verdict M8-pushback "$red" "$green"

# ------------------------------------------------------- M9 rogue ParseInputs
echo; echo "##### M9: rogue ParseInputs construction site (HIGH-5) #####"
cat >> psh/executor/command.py <<'EOF'


def _q2res_rogue_inputs():
    from ..parser import ParseInputs
    return ParseInputs(source_text="q2")
EOF
run_guard "tests/unit/tooling/test_parser_contract_guards_s4.py::test_parse_inputs_construction_sites"; red=$?
git -C "$WT" checkout -- psh/executor/command.py
run_guard "tests/unit/tooling/test_parser_contract_guards_s4.py::test_parse_inputs_construction_sites"; green=$?
verdict M9-parseinputs "$red" "$green"

# ------------------------------------------- M10 third ExpandedField producer
echo; echo "##### M10: third ExpandedField producer (3.3 producer census) #####"
cat >> psh/expansion/variable.py <<'EOF'


def _q2res_field_producer():
    from .word_expansion_types import ExpandedField
    return ExpandedField([])
EOF
run_guard "tests/unit/expansion/test_field_ir_guards.py::TestSoleChokepoint::test_expanded_word_constructed_only_in_engine"; red=$?
git -C "$WT" checkout -- psh/expansion/variable.py
run_guard "tests/unit/expansion/test_field_ir_guards.py::TestSoleChokepoint::test_expanded_word_constructed_only_in_engine"; green=$?
verdict M10-field-producer "$red" "$green"

echo; echo "##### worktree must be clean after all reverts #####"
git -C "$WT" status --porcelain
echo "status-exit=$? (empty output above = clean)"
