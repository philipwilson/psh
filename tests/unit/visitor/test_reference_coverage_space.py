"""Generated reference-coverage space suite (remediation 2.1 round-4).

THE EXECUTABLE CORPUS-COVERAGE STATEMENT for the one-authority rule: rather
than asserting "zero unintentional losses" from a hand-built corpus (which
round-3 B10 proved systematically misses the shapes nobody thought of), this
suite GENERATES the space — construct families x positions — and freezes the
expected undefined-variable finding count per cell for every analysis visitor
plus the metrics variable-name capture.

SPACE: 11 families x 9 positions = 99 cells. Families embed one undefined
``$y`` in a specific region kind (plain reference; modern ``$()``; deferred
backtick; arithmetic with a plain var; arithmetic with a nested ``$()``;
backtick nested under a parsed ``$()``; ``$()`` inside an unparsed backtick;
each of modern/backtick/nested wrapped in a ``${x:-...}`` operand; procsub).
Positions: command argument, five assignment variants (bare/export/local/
quoted/concat), redirect target, for-item, case-subject.

FROZEN TABLE provenance: generated at commit 2e553d46's tree vs base
a765f1a0 (instrument tmp/s21-probes/b10-matrix.py, discriminator-checked
worktrees; ledger 2.1 §14). Row comments carry the base tuple and a
classification: BASE-EQUAL (behavior unchanged), GAIN (a region that had no
reader at base is now read — the sanctioned totality direction; 72 cells),
DE-DUP (a pre-existing base double-read collapsed to one — the
prefixed-assignment fix; plain-var export/local here, readonly/declare in
test_finding_multiplicity.py). Every count is 0 or 1: exactly-once is a
TABLE-WIDE invariant, asserted separately so a future 2 fails twice.

EXCLUDED CELLS, stated per the coverage-statement requirement:
- heredoc-body position: bare parse(tokenize()) does not collect heredoc
  bodies (they mis-lex as commands); covered by the CLI spot-check test at
  the bottom of this file through the real --lint pipeline.
- ``[[ ]]`` operand position: quoted operands parse to flat literal text
  (no reference structure to count); that domain is owned by the
  UNANALYZED_REGION guard and pinned in test_security_missed_positions.py.
- readonly/declare assignment prefixes: same seam as export/local (their
  de-dup pins live in test_finding_multiplicity.py to keep this table's
  position set orthogonal).
"""

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor.enhanced_validator_visitor import EnhancedValidatorVisitor
from psh.visitor.linter_visitor import LinterVisitor
from psh.visitor.metrics_visitor import MetricsVisitor
from psh.visitor.security_visitor import SecurityVisitor
from psh.visitor.validator_visitor import ValidatorVisitor

FAMILIES = {
    'plain-var': '$y',
    'modern': '$(echo $y)',
    'backtick': '`echo $y`',
    'arith-var': '$(($y + 1))',
    'arith-sub': '$(( $(echo $y) ))',
    'bt-in-mod': '$(echo `echo $y`)',
    'mod-in-bt': '`echo $(echo $y)`',
    'op-mod': '${x:-$(echo $y)}',
    'op-bt': '${x:-`echo $y`}',
    'op-nested': '${x:-$(echo `echo $y`)}',
    'procsub': '<(echo $y)',
}

POSITIONS = {
    'cmd-arg': 'echo {f}',
    'assign': 'FOO={f}',
    'assign-export': 'export FOO={f}',
    'assign-local': 'fn() {{ local FOO={f}; }}; fn',
    'assign-quoted': 'FOO="{f}"',
    'assign-concat': 'FOO=a{f}b',
    'redirect': 'echo hi > {f}.log',
    'for-item': 'for i in {f}; do :; done',
    'case-subject': 'case "{f}" in a) :;; esac',
}

# (ENH undef-y, LNT undef-y, VAL undef-y, SEC undef-y, metrics-records-y)
EXPECTED = {
    ('arith-sub', 'assign'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('arith-sub', 'assign-concat'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('arith-sub', 'assign-export'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('arith-sub', 'assign-local'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('arith-sub', 'assign-quoted'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('arith-sub', 'case-subject'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 1) GAIN
    ('arith-sub', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('arith-sub', 'for-item'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('arith-sub', 'redirect'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 0) GAIN
    ('arith-var', 'assign'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('arith-var', 'assign-concat'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('arith-var', 'assign-export'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('arith-var', 'assign-local'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('arith-var', 'assign-quoted'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('arith-var', 'case-subject'): (0, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 1) BASE-EQUAL
    ('arith-var', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('arith-var', 'for-item'): (1, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('arith-var', 'redirect'): (0, 1, 0, 0, 0),  # base=(0, 1, 0, 0, 0) BASE-EQUAL
    ('backtick', 'assign'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('backtick', 'assign-concat'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('backtick', 'assign-export'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('backtick', 'assign-local'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('backtick', 'assign-quoted'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('backtick', 'case-subject'): (0, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 1) BASE-EQUAL
    ('backtick', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('backtick', 'for-item'): (1, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('backtick', 'redirect'): (0, 1, 0, 0, 0),  # base=(0, 1, 0, 0, 0) BASE-EQUAL
    ('bt-in-mod', 'assign'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('bt-in-mod', 'assign-concat'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('bt-in-mod', 'assign-export'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('bt-in-mod', 'assign-local'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('bt-in-mod', 'assign-quoted'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('bt-in-mod', 'case-subject'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 1) GAIN
    ('bt-in-mod', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('bt-in-mod', 'for-item'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('bt-in-mod', 'redirect'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 0) GAIN
    ('mod-in-bt', 'assign'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('mod-in-bt', 'assign-concat'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('mod-in-bt', 'assign-export'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('mod-in-bt', 'assign-local'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('mod-in-bt', 'assign-quoted'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 0) GAIN
    ('mod-in-bt', 'case-subject'): (0, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 1) BASE-EQUAL
    ('mod-in-bt', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('mod-in-bt', 'for-item'): (1, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('mod-in-bt', 'redirect'): (0, 1, 0, 0, 0),  # base=(0, 1, 0, 0, 0) BASE-EQUAL
    ('modern', 'assign'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 0) GAIN
    ('modern', 'assign-concat'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 0) GAIN
    ('modern', 'assign-export'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 0) GAIN
    ('modern', 'assign-local'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 0) GAIN
    ('modern', 'assign-quoted'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 0) GAIN
    ('modern', 'case-subject'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 1) GAIN
    ('modern', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 0) GAIN
    ('modern', 'for-item'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 0) GAIN
    ('modern', 'redirect'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 0) GAIN
    ('op-bt', 'assign'): (0, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 1) BASE-EQUAL
    ('op-bt', 'assign-concat'): (0, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 1) BASE-EQUAL
    ('op-bt', 'assign-export'): (0, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 1) BASE-EQUAL
    ('op-bt', 'assign-local'): (0, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 1) BASE-EQUAL
    ('op-bt', 'assign-quoted'): (0, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 1) BASE-EQUAL
    ('op-bt', 'case-subject'): (0, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 1) BASE-EQUAL
    ('op-bt', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 1) BASE-EQUAL
    ('op-bt', 'for-item'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 1) BASE-EQUAL
    ('op-bt', 'redirect'): (0, 1, 0, 0, 0),  # base=(0, 0, 0, 0, 0) GAIN
    ('op-mod', 'assign'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 1) GAIN
    ('op-mod', 'assign-concat'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 1) GAIN
    ('op-mod', 'assign-export'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 1) GAIN
    ('op-mod', 'assign-local'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 1) GAIN
    ('op-mod', 'assign-quoted'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 1) GAIN
    ('op-mod', 'case-subject'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 1) GAIN
    ('op-mod', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 1) BASE-EQUAL
    ('op-mod', 'for-item'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 1) GAIN
    ('op-mod', 'redirect'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('op-nested', 'assign'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 1) GAIN
    ('op-nested', 'assign-concat'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 1) GAIN
    ('op-nested', 'assign-export'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 1) GAIN
    ('op-nested', 'assign-local'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 1) GAIN
    ('op-nested', 'assign-quoted'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 1) GAIN
    ('op-nested', 'case-subject'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 1) GAIN
    ('op-nested', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 1) BASE-EQUAL
    ('op-nested', 'for-item'): (1, 1, 0, 0, 1),  # base=(1, 0, 0, 0, 1) GAIN
    ('op-nested', 'redirect'): (1, 1, 0, 0, 1),  # base=(0, 0, 0, 0, 0) GAIN
    ('plain-var', 'assign'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 1) BASE-EQUAL
    ('plain-var', 'assign-concat'): (0, 0, 0, 0, 0),  # base=(0, 0, 0, 0, 0) BASE-EQUAL
    ('plain-var', 'assign-export'): (1, 1, 0, 0, 1),  # base=(2, 1, 0, 0, 1) DE-DUP
    ('plain-var', 'assign-local'): (1, 1, 0, 0, 1),  # base=(2, 1, 0, 0, 1) DE-DUP
    ('plain-var', 'assign-quoted'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 1) BASE-EQUAL
    ('plain-var', 'case-subject'): (0, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 1) BASE-EQUAL
    ('plain-var', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 1) BASE-EQUAL
    ('plain-var', 'for-item'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 1) BASE-EQUAL
    ('plain-var', 'redirect'): (0, 1, 0, 0, 0),  # base=(0, 1, 0, 0, 0) BASE-EQUAL
    ('procsub', 'assign'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 0) GAIN
    ('procsub', 'assign-concat'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 0) GAIN
    ('procsub', 'assign-export'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 0) GAIN
    ('procsub', 'assign-local'): (1, 1, 0, 0, 1),  # base=(1, 1, 0, 0, 0) GAIN
    ('procsub', 'assign-quoted'): (1, 0, 0, 0, 1),  # base=(1, 0, 0, 0, 1) BASE-EQUAL
    ('procsub', 'case-subject'): (0, 0, 0, 0, 1),  # base=(0, 0, 0, 0, 1) BASE-EQUAL
    ('procsub', 'cmd-arg'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 0) GAIN
    ('procsub', 'for-item'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 0) GAIN
    ('procsub', 'redirect'): (1, 1, 0, 0, 1),  # base=(0, 1, 0, 0, 0) GAIN
}


def _undef_y(visitor_cls, src):
    v = visitor_cls()
    v.visit(parse(tokenize(src)))
    return sum(1 for i in v.issues
               if 'undefined' in i.message
               and ("'$y'" in i.message or "'y'" in i.message))


def _cell(family, position):
    src = POSITIONS[position].format(f=FAMILIES[family])
    counts = tuple(_undef_y(c, src) for c in
                   (EnhancedValidatorVisitor, LinterVisitor,
                    ValidatorVisitor, SecurityVisitor))
    m = MetricsVisitor()
    m.visit(parse(tokenize(src)))
    return counts + (1 if 'y' in m.metrics.variable_names else 0,)


def test_table_is_total_over_the_generated_space():
    """A new family/position must get a frozen row (no silent shrinkage)."""
    assert set(EXPECTED) == {(f, p) for f in FAMILIES for p in POSITIONS}


def test_exactly_once_is_table_wide():
    """No cell anywhere in the space expects (or may produce) a duplicate."""
    assert all(v <= 1 for row in EXPECTED.values() for v in row)


@pytest.mark.parametrize('family,position', sorted(EXPECTED),
                         ids=[f'{f}.{p}' for f, p in sorted(EXPECTED)])
def test_reference_coverage_cell(family, position):
    actual = _cell(family, position)
    assert actual == EXPECTED[(family, position)], (
        f"{POSITIONS[position].format(f=FAMILIES[family])!r}: "
        f"(ENH, LNT, VAL, SEC, METy) = {actual}, "
        f"frozen {EXPECTED[(family, position)]} — a drop is a lost reader, "
        f"a rise is a duplicate authority; both are the B6/B10 disease."
    )


def test_heredoc_body_reader_unchanged():
    """EXCLUDED-CELL spot-check via the real CLI pipeline: an unquoted
    heredoc body's $y is read by the linter's textual heredoc check (its
    only reader — no structural representation until slot 2.5), exactly
    once, as at base."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '--lint', '-c',
         'cat <<EOF\ntext $y here\nEOF\n'],
        capture_output=True, text=True, timeout=60)
    assert sum(1 for line in result.stdout.splitlines()
               if "Variable 'y' may be undefined" in line) == 1, result.stdout
