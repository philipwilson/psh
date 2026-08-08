#!/opt/homebrew/bin/bash
# Q1 probe 17: (a) MEDIUM-12 broad-except closed sites stay closed (grep the
# exact files at ae871a16 in the worktree); (b) gate_attestation.json
# reconciliation; (c) HIGH-10 artifact existence at ae871a16;
# (d) MEDIUM-14/15/16 base-fact one-liners (grep census).
set -u
WT='/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt'
MAIN=/Users/pwilson/src/psh
cd "$WT" || exit 1

echo "=== (a) MEDIUM-12: broad except at the closed sites"
echo "--- psh/expansion/subscript.py 'except Exception' hits:"
grep -n "except Exception" psh/expansion/subscript.py | grep -c . || true
grep -n "except Exception" psh/expansion/subscript.py || echo "(none)"
echo "--- psh/expansion/manager.py 'except Exception' hits:"
grep -n "except Exception" psh/expansion/manager.py || echo "(none)"
echo "--- arithmetic evaluator 'except Exception' hits:"
grep -rn "except Exception" psh/arithmetic/ 2>/dev/null || echo "(none under psh/arithmetic/)"
echo "--- ratchet files exist:"
ls tests/unit/tooling/test_subscript_no_broad_except.py

echo
echo "=== (b) gate_attestation.json at ae871a16"
git -C "$MAIN" show ae871a16:gate_attestation.json
GATED=$(git -C "$MAIN" show ae871a16:gate_attestation.json | python -c "import json,sys; d=json.load(sys.stdin); print(d.get('commit') or d.get('gated_commit') or '')")
echo "gated commit field: $GATED"
if [ -n "$GATED" ]; then
  if git -C "$MAIN" merge-base --is-ancestor "$GATED" ae871a16; then
    echo "gated commit IS an ancestor of ae871a16: YES"
  else
    echo "gated commit IS an ancestor of ae871a16: NO"
  fi
fi

echo
echo "=== (c) HIGH-10 closure artifacts exist at ae871a16"
for p in \
  docs/reviews/boundary_remediation_campaign_sequence_2026-07-21.md \
  docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md \
  docs/reviews/evidence/boundary_remediation_2026-07/FLIP-PINS.md \
  tests/harness/oracle_migration_census.md \
  tests/harness/shell_oracle.py; do
  git -C "$MAIN" cat-file -e "ae871a16:$p" 2>/dev/null && echo "  OK $p" || echo "  MISSING $p"
done

echo
echo "=== (d) MEDIUM-14/15/16 base-fact one-liners"
echo "--- M14: Protocol classes in psh/ (count):"
grep -rn "class .*(Protocol" psh/ --include="*.py" | grep -c .
echo "--- M14: ExpansionContext definitions (name collision — expect >=2):"
grep -rn "^class ExpansionContext" psh/ --include="*.py"
echo "--- M14: LocaleContext definitions (name collision — expect >=2):"
grep -rn "^class LocaleContext" psh/ --include="*.py"
