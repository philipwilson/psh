#!/opt/homebrew/bin/bash
# atk-b item 6: re-plant 3 synthetic offenders (VARIED from q2's shapes) in
# MY worktree; confirm each guard goes RED naming the offender, revert, show
# GREEN + clean status. Boundaries chosen: visitor bypass (generated-battery
# guard, planted on security_visitor.py NOT q2's linter_visitor.py), broad
# except in subscript.py (TUPLE form, not q2's bare `except Exception:`),
# third ExpandedField producer (planted in fields.py, not q2's variable.py).
set -u
WT=/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-b/wt
cd "$WT" || exit 1
export PYTHONPATH="$WT"

run_guard() { # $1 = node/file id
  python3 -m pytest -q "$1" 2>&1 | tail -4
  return "${PIPESTATUS[0]}"
}

verdict() {
  if [ "$2" -ne 0 ] && [ "$3" -eq 0 ]; then
    echo "ATK-MUTATION-VERDICT $1: BITES (red=$2 on offender, green=$3 after revert)"
  else
    echo "ATK-MUTATION-VERDICT $1: *** GUARD-DOES-NOT-BITE (red=$2 green=$3) ***"
  fi
}

echo "##### A: visit() override on SecurityVisitor (generated-battery guard) #####"
grep -q "class SecurityVisitor" psh/visitor/security_visitor.py || echo "PRECHECK-FAIL"
cat >> psh/visitor/security_visitor.py <<'EOF'


def _atkb_offender_visit(self, node):
    return None


SecurityVisitor.visit = _atkb_offender_visit
EOF
run_guard "tests/unit/visitor/test_traversal_totality_battery.py::test_analysis_visitor_cannot_bypass_the_sweep"; red=$?
git -C "$WT" checkout -- psh/visitor/security_visitor.py
run_guard "tests/unit/visitor/test_traversal_totality_battery.py::test_analysis_visitor_cannot_bypass_the_sweep"; green=$?
verdict A-visitor-bypass-security "$red" "$green"

echo; echo "##### B: TUPLE-form broad except in subscript.py #####"
cat >> psh/expansion/subscript.py <<'EOF'


def _atkb_offender():
    try:
        return 1
    except (ValueError, Exception):
        return 0
EOF
run_guard "tests/unit/tooling/test_subscript_no_broad_except.py::test_guarded_modules_have_no_broad_except"; red=$?
git -C "$WT" checkout -- psh/expansion/subscript.py
run_guard "tests/unit/tooling/test_subscript_no_broad_except.py::test_guarded_modules_have_no_broad_except"; green=$?
verdict B-subscript-tuple-broad-except "$red" "$green"

echo; echo "##### C: third ExpandedField producer in expansion/fields.py #####"
cat >> psh/expansion/fields.py <<'EOF'


def _atkb_field_producer():
    from .word_expansion_types import ExpandedField
    return ExpandedField([])
EOF
run_guard "tests/unit/expansion/test_field_ir_guards.py::TestSoleChokepoint::test_expanded_word_constructed_only_in_engine"; red=$?
git -C "$WT" checkout -- psh/expansion/fields.py
run_guard "tests/unit/expansion/test_field_ir_guards.py::TestSoleChokepoint::test_expanded_word_constructed_only_in_engine"; green=$?
verdict C-third-field-producer-fields "$red" "$green"

echo; echo "##### worktree must be clean after all reverts #####"
git -C "$WT" status --porcelain
echo "status-exit=$? (empty output above = clean)"
