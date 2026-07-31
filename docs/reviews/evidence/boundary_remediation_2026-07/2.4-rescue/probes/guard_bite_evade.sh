#!/bin/bash
# R6-F: prove the STRENGTHENED consumer guards bite on the two evasion shapes
# the round-5 verifier demonstrated slipping through (attribute-qualified raise
# site; two-line status re-derivation). Inserts a real offender module under
# psh/, runs the guards, removes it, and shows the tree is clean again.
#
# Run from the worktree root. Prints the tip SHA it ran at.
set -u
cd "$(dirname "$0")/../.." || exit 1
echo "SHA: $(git rev-parse HEAD)"
echo "tree before: $(git status --porcelain psh/ | wc -l | tr -d ' ') modified/untracked under psh/"

cat > psh/offender_evade_probe.py <<'EOF'
"""Scratch offender (removed by guard_bite_evade.sh immediately after)."""
from psh.core import exceptions
from psh.core.exceptions import SubstitutionSyntaxAbort


def sneaky_raise():
    raise exceptions.SubstitutionSyntaxAbort(nested=True)


def sneaky_rederive(e):
    if isinstance(e, SubstitutionSyntaxAbort):
        return 127
    return 0
EOF

cat > psh/offender_alias_probe.py <<'EOF'
"""Scratch offender: the round-6 ALIASED-IMPORT evasion."""
from psh.core.exceptions import SubstitutionSyntaxAbort as SSA


def sneaky_alias_raise():
    raise SSA(nested=True)


def sneaky_alias_catch(e):
    try:
        pass
    except SSA:
        return 127
EOF

echo "--- guards WITH the offender present (both must FAIL) ---"
python -m pytest tests/unit/tooling/test_substitution_abort_guards.py -q 2>&1 | tail -4

rm -f psh/offender_evade_probe.py psh/offender_alias_probe.py
echo "--- offender removed; tree under psh/: $(git status --porcelain psh/ | wc -l | tr -d ' ') entries ---"
echo "--- guards WITHOUT the offender (all must PASS) ---"
python -m pytest tests/unit/tooling/test_substitution_abort_guards.py -q 2>&1 | tail -2
