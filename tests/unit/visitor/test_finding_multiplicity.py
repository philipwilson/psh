"""Finding-level multiplicity pins (remediation 2.1 round-3, blocker B6).

The dispatch-level exactly-once battery stayed green over a DUPLICATE-FINDINGS
regression: when total traversal made a region structurally reachable, a
TEXTUAL analyzer that was already reading that region's source produced the
same diagnostic a second time — two different nodes, each dispatched once,
reporting one source fact twice. Dispatch multiplicity was 1; FINDING
multiplicity was 2. These pins assert the property users experience: the
COUNT of a specific diagnostic for a given source shape.

Authority rule pinned here (stated in code at the three seams):
a textual fallback must not re-read regions that have a structural
representation — the structural visit is the authority for them. Regions with
NO structural representation (deferred backtick bodies, heredoc bodies,
word-less manual nodes) keep their textual coverage.

Base-vs-tip evidence (probe: tmp/s21-probes/finding-count-probe.py, run at
a765f1a0 and at the pre-fix tip 3a20bd7f, discriminator-checked; ledger §10):
- operand forms :- :+ - :? // : ENH and LNT undefined-'y' counts were 1 at
  base, 2 at the pre-fix tip (the B6 dupes) -> pinned to 1.
- ENH assignment value FOO=$(echo $y): 1 -> 2 -> pinned to 1 (beyond the
  verifier's list).
- LNT redirect target > $(echo $y).log: 1 -> 2 -> pinned to 1 (beyond the
  verifier's list).
- controls: plain-var rows stable 1; newly-reached rows (for/case subjects,
  arith/subscript templates) are exactly 1 (a NEW finding once — totality,
  not duplication); backtick-operand row 1 at BOTH (its body has no
  structural representation, so the textual read must survive the fix).
"""

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor.enhanced_validator_visitor import EnhancedValidatorVisitor
from psh.visitor.linter_visitor import LinterVisitor
from psh.visitor.metrics_visitor import MetricsVisitor
from psh.visitor.security_visitor import SecurityVisitor


def _undef_y_count(visitor_cls, src):
    v = visitor_cls()
    v.visit(parse(tokenize(src)))
    return sum(
        1 for i in v.issues
        if 'undefined' in i.message and ("'$y'" in i.message or "'y'" in i.message)
    )


# --- The B6 duplicate shapes: exactly ONE undefined-variable finding --------

OPERAND_FORMS = [
    ('default', 'echo "${x:-$(echo $y)}"'),
    ('alt-default', 'echo "${x-$(echo $y)}"'),
    ('alternative', 'echo "${x:+$(echo $y)}"'),
    ('error-word', 'echo "${x:?$(echo $y)}"'),
    ('replace', 'echo "${x/$(echo $y)/z}"'),
]


@pytest.mark.parametrize("visitor_cls", [EnhancedValidatorVisitor, LinterVisitor],
                         ids=['enhanced', 'linter'])
@pytest.mark.parametrize("label,src", OPERAND_FORMS, ids=[f[0] for f in OPERAND_FORMS])
def test_operand_substitution_reference_reported_once(visitor_cls, label, src):
    """${x:-$(echo $y)} family: the $y inside the nested substitution is one
    source fact — one finding (was 2: textual operand fallback + structural
    sweep both reported it)."""
    assert _undef_y_count(visitor_cls, src) == 1


def test_assignment_value_substitution_reference_reported_once():
    """FOO=$(echo $y): one finding (was 2: raw value-text scan + sweep)."""
    assert _undef_y_count(EnhancedValidatorVisitor, 'FOO=$(echo $y)') == 1


def test_redirect_target_substitution_reference_reported_once():
    """> $(echo $y).log: one linter finding (was 2: target-text scan + sweep)."""
    assert _undef_y_count(LinterVisitor, 'echo hi > $(echo $y).log') == 1


# --- Structural reach must SURVIVE the fix (no under-fix / lost findings) ---

@pytest.mark.parametrize("label,src,visitor_cls,expected", [
    # plain textual references with no structural double: unchanged behavior.
    ('operand-plain-var-enh', 'echo "${x:-$y}"', EnhancedValidatorVisitor, 1),
    ('operand-plain-var-lnt', 'echo "${x:-$y}"', LinterVisitor, 1),
    ('assign-plain-var', 'FOO=$y', EnhancedValidatorVisitor, 1),
    ('redirect-plain-var', 'echo hi > $y.log', LinterVisitor, 1),
    # newly-structurally-reached positions: found exactly once (totality).
    ('for-item-sub', 'for i in $(echo $y); do :; done', EnhancedValidatorVisitor, 1),
    ('case-subject-sub', 'case "$(echo $y)" in a) :;; esac', EnhancedValidatorVisitor, 1),
    ('arith-template-sub', 'echo "$(( $(echo $y) ))"', EnhancedValidatorVisitor, 1),
    ('subscript-template-sub', 'a[$(echo $y)]=v', EnhancedValidatorVisitor, 1),
    ('cmd-arg-sub', 'echo $(echo $y)', EnhancedValidatorVisitor, 1),
    # deferred backtick body: NO structural representation, so the textual
    # operand read must survive (masking it would LOSE this base finding).
    ('operand-backtick-enh', 'echo "${x:-`echo $y`}"', EnhancedValidatorVisitor, 1),
])
def test_reference_found_exactly_once(label, src, visitor_cls, expected):
    count = _undef_y_count(visitor_cls, src)
    # For the linter, "$y" rows also register 'x' where spelled; expected
    # captures the total undefined-count for the shape (x and/or y).
    assert count == expected, (label, src, count)


def test_operand_backtick_linter_keeps_both_references():
    """Linter control for the backtick-operand row: x once AND y once (the
    exact base counts — base⊆tip preserved through the fix; the y reference
    lives only in the backtick body's TEXT, which has no structural
    representation and must keep its textual coverage)."""
    v = LinterVisitor()
    v.visit(parse(tokenize('echo "${x:-`echo $y`}"')))
    undef = [i.message for i in v.issues if 'undefined' in i.message]
    assert sum(1 for m in undef if "'y'" in m) == 1, undef
    assert sum(1 for m in undef if "'x'" in m) == 1, undef


# --- Unaffected-visitor controls -------------------------------------------

def test_security_and_metrics_unaffected_by_operand_shapes():
    src = 'echo "${x:-$(rm -rf /tmp/psh-never-created)}"'
    v = SecurityVisitor()
    v.visit(parse(tokenize(src)))
    assert sum(1 for i in v.issues if 'rm' in i.message) == 1

    m = MetricsVisitor()
    m.visit(parse(tokenize('echo "${x:-$(echo $y)}"')))
    assert m.metrics.total_commands == 2  # outer echo + inner echo, once each


# --- The base whole-program double emission, fixed by the root gate --------

def test_lint_whole_program_checks_emitted_once_for_subject_substitution():
    """BASE BUG fixed at tip, pinned: a substitution in a for/case subject
    made the base linter run its whole-program checks TWICE (the nested
    Program re-triggered them: two 'no explicit error handling' INFOs at
    a765f1a0, replayed). The at_traversal_root gate emits them exactly once."""
    for src in ('for i in $(echo hi); do :; done',
                'case "$(echo hi)" in a) :;; esac'):
        v = LinterVisitor()
        v.visit(parse(tokenize(src)))
        noerr = [i for i in v.issues
                 if 'no explicit error handling' in i.message]
        assert len(noerr) == 1, (src, [i.message for i in v.issues])


# --- Round-4: prefixed-assignment de-dup + the $@ carve-out ------------------

def _enh_summary_counts(src, needle):
    v = EnhancedValidatorVisitor()
    v.visit(parse(tokenize(src)))
    return sum(1 for i in v.issues if needle in i.message)


def test_export_at_advisory_survives_the_assignment_skip():
    """LOAD-BEARING PIN of the prefixed-assignment de-dup (integrator
    condition 1): the command-args reader SKIPS an assignment word's
    variable-reference loop (the assignment authority owns those), but its
    unquoted-$@ advisory still runs for assignment words — because the
    assignment authority deliberately has NO $@ advisory (the quote-removal
    false-positive note in _check_string_for_undefined_vars), so a wholesale
    skip would silently DROP this exact finding. Per-path attribution proved
    it is the command-args reader's alone; the user-facing gate saved it. If
    a future refactor re-broadens the skip, this pin goes red."""
    assert _enh_summary_counts(
        'export FOO=$@', 'Unquoted $@ should be "$@"') == 1


@pytest.mark.parametrize("src", [
    'export FOO=$y',
    'fn() { local FOO=$y; }; fn',
    'readonly FOO=$y',
    'declare FOO=$y',
], ids=['export', 'local', 'readonly', 'declare'])
def test_prefixed_assignment_value_reported_once(src):
    """NAMED DE-DUP (like at_traversal_root): a PREFIXED assignment's value
    sits at args[1], where BOTH the assignment authority and the command-args
    reader historically read it — base a765f1a0 reported the undefined $y
    TWICE for each of these (replayed; a bare FOO=$y read once only because
    the i==0 guard skipped it). One authority now owns assignment values;
    exactly one finding."""
    assert _undef_y_count(EnhancedValidatorVisitor, src) == 1


@pytest.mark.parametrize("src", [
    'export FOO=`echo $y`',
    'export FOO=$(($y + 1))',
], ids=['backtick-value', 'arith-value'])
def test_prefixed_assignment_unstructured_value_reported_once(src):
    """The six round-4 condition-1 cells, pinned per-name at 1: these read 1
    at base only because BOTH duplicate readers were blind to backtick/
    arithmetic regions; Design A gave them sight and briefly exposed the
    pre-existing double (2) before the de-dup landed. Now: one reader, one
    finding — never zero (the region kept its only reader), never two."""
    assert _undef_y_count(EnhancedValidatorVisitor, src) == 1


def test_brace_blind_redirect_target_gain_is_intentional():
    r"""NAMED BASE-BUG GAIN: at base, `> ${x:-\`echo $y\`}.log` produced ZERO
    $y findings — the raw-text regex swallowed everything inside ${...} as
    the tail of one braced match, so base's own textual reader was blind
    inside ${} in raw-text contexts. The structural operand fallback now
    reads it (deferred-backtick span unmasked): exactly one finding. Pinned
    as an intentional gain closing a base blindness, like at_traversal_root."""
    assert _undef_y_count(LinterVisitor, 'echo hi > ${x:-`echo $y`}.log') == 1
