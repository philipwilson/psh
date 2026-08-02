"""Deterministic complexity pins for the pattern engine (#20 HIGH-7, perf half).

These assert TRANSITION COUNTS, never wall-clock: counts are reproducible on
any machine and under any load, so they can live in the default gate.

WHY A SECOND COUNTER EXISTS. ``count_states`` counts memo MISSES — distinct
``(sequence, element, start, end)`` keys. Work spent re-walking positions whose
answers are already memoized is invisible to it, and that is not hypothetical:
before this slot, ``_BashMatcher`` on ``**(a)b`` had a QUADRATIC key count and
a CUBIC running time, so the shipped state-count pin passed at every size with
~50% headroom while the cubic went unnoticed for a whole release. A complexity
pin that cannot fail for the defect it names is not a pin. ``count_transitions``
increments per unit of loop work — including steps that end in a memo hit.

WHY A THIRD INSTRUMENT EXISTS. ``count_transitions(relation='scan')`` walks
EVERY position, but ``${v//pat/r}`` on a MATCHING subject JUMPS past each
match. The scan mode therefore reports an operation's NO-MATCH cost, and a
claim about a matching subject must be asserted with ``operation_transitions``,
which totals the work of the real consumer call. Reaching for the wrong one of
these three is how a green pin ends up certifying a path nobody takes.

SHAPED SUBJECTS. A fixed ``'a'*n`` subject short-circuits the backward pass
before an extglob element is ever evaluated, which makes an extglob row look
linear for free. Every extglob row below therefore uses a subject that
actually reaches the group, and its bound is the ACHIEVED one.

SCOPE. The "no-match substitution scan is linear" guarantee holds for
EXTGLOB-FREE patterns. Extglob-bearing patterns keep the per-position forward
DP — the all-start pre-filter is gated off for them, because building it costs
O(n^2) there — and get their own achieved-bound rows.

BOUND TIGHTNESS. Several bounds below sit just above the measured ratio (4.6
on a measured 3.97-3.99). That is safe ONLY because the instrument is
noise-free: transition counts are deterministic integers, identical on any
machine under any load. The same margin around a wall-clock measurement would
be a flake generator — which is precisely why these pins count instead of
timing, and why the wall-clock numbers live in the slot ledger instead.
"""
import pytest

from psh.expansion.pattern_engine import (
    STRING,
    PatternCompiler,
    compile_pattern,
    count_transitions,
    operation_transitions,
)

SIZES = (100, 200, 400, 800)

# Extglob-FREE: the all-start pre-filter applies, so scanning is linear.
EXTGLOB_FREE = ['*x', 'a*x', 'zzz', '*a*b*x', '[ab]*x', '*[!a]x']

# Extglob-BEARING with a subject UNIT that reaches the group when repeated.
SHAPED_EXTGLOB = [
    ('+(a)x', 'a'),
    ('+([[:space:]])x', ' '),
    ('*(ab)x', 'ab'),
    ('!(a)b', 'ab'),
]


def _counts(pattern, relation, mk, sizes=SIZES, extglob=True):
    root = compile_pattern(pattern, extglob=extglob)
    return [count_transitions(root, mk(n), relation=relation) for n in sizes]


def _max_ratio(counts):
    """Worst doubling ratio — the growth exponent, base 2."""
    return max(b / a for a, b in zip(counts, counts[1:], strict=False) if a)


# --- R5(1a): the GATE itself -----------------------------------------------

@pytest.mark.parametrize('pattern', EXTGLOB_FREE)
def test_pre_filter_is_taken_for_extglob_free_patterns(pattern):
    """Extglob-free: ``spanner`` spends its one backward all-start pass at
    CONSTRUCTION, which is what makes the later per-position scan free."""
    cp = PatternCompiler.compile(pattern, extglob=True)
    assert cp.root.has_extglob is False
    span_at = cp.spanner('a' * 200, STRING)
    assert span_at.matcher.transitions > 0, (
        f"{pattern!r}: no work at spanner construction — the all-start "
        f"pre-filter is not being taken for an extglob-free pattern")


@pytest.mark.parametrize('pattern', [p for p, _ in SHAPED_EXTGLOB]
                         + ['*([[:space:]])', '!(x)'])
def test_pre_filter_is_skipped_for_extglob_bearing_patterns(pattern):
    """Extglob-bearing: the pre-filter must NOT be built.

    ``_Matcher._starts``'s Extglob branch pays per-position
    ``_element_ends``, so constructing the filter here costs O(n^2) BEFORE the
    first ``span_at`` — which is exactly how a linear eligible-pattern
    substitution became quadratic (``${v//+([[:space:]])/-}`` on ``' '*3200``:
    0.008s -> 11.9s). Zero construction work is the whole fix.
    """
    cp = PatternCompiler.compile(pattern, extglob=True)
    assert cp.root.has_extglob is True
    span_at = cp.spanner('a' * 200, STRING)
    assert span_at.matcher.transitions == 0, (
        f"{pattern!r}: {span_at.matcher.transitions} transitions at spanner "
        f"construction — the O(n^2) pre-filter is being built for an "
        f"extglob-bearing pattern again")


# --- chartered criterion 1: SUFFIX matching is linear (extglob-free) --------

@pytest.mark.parametrize('pattern', ['*b', 'a*b', '*a*b', '*a*a*b', '*',
                                     '[ab]*', 'ab*'])
def test_suffix_relation_transitions_are_linear(pattern):
    """``matching_starts`` (suffix removal) is ONE backward all-start pass, so
    doubling the subject at most doubles the work — FOR EXTGLOB-FREE PATTERNS.
    Extglob-bearing suffix shapes are shape-conditional; see below.

    Before this slot it ran a forward DP per start index — quadratic, and
    ``${v%%*+(a)}`` on ``'a'*800`` was CUBIC (37.7s on the reference machine).
    """
    counts = _counts(pattern, 'starts', lambda n: 'a' * n)
    ratio = _max_ratio(counts)
    assert ratio < 2.6, (
        f"{pattern!r} suffix transitions {counts} grew by x{ratio:.2f} per "
        f"doubling — the all-start pass regressed to per-start evaluation")


# --- chartered criterion 2: NO-MATCH substitution scan, extglob-free -------

@pytest.mark.parametrize('pattern', EXTGLOB_FREE)
def test_no_match_scan_is_linear_for_extglob_free_patterns(pattern):
    """On a subject with NO match the consumer walks every position; the
    all-start pre-filter answers all of them in one backward pass.

    Measured at the tip: exactly ``2n+2`` for every pattern here.
    """
    counts = _counts(pattern, 'scan', lambda n: 'a' * n)
    ratio = _max_ratio(counts)
    assert ratio < 2.6, (
        f"{pattern!r} no-match scan transitions {counts} grew by x{ratio:.2f} "
        f"per doubling — the all-start pre-filter stopped applying")


def test_no_match_scan_is_measured_through_the_real_spanner():
    """The counter must observe the path the consumer actually takes.

    Pinned because an earlier draft of this counter re-derived the scan
    instead — and reported quadratic growth for a path that had already been
    made linear, the same blindness the module docstring warns about.
    """
    root = compile_pattern('*x')
    assert count_transitions(root, 'a' * 200, relation='scan') == 402


# --- extglob-bearing: ACHIEVED bounds on SHAPED subjects -------------------

@pytest.mark.parametrize('pattern,unit', SHAPED_EXTGLOB)
def test_extglob_no_match_scan_achieved_bound(pattern, unit):
    """Extglob-bearing no-match scanning is QUADRATIC, and that is the
    ACHIEVED bound rather than an aspiration: the pre-filter is gated off here
    (building it would cost more than it saves), so each position runs its own
    forward DP. The subject reaches the group, so this row cannot pass by
    short-circuit. Measured x3.97-3.99; bounded at 4.6.

    A bound that sits this close to the measurement is only safe because the
    instrument is NOISE-FREE: transition counts are deterministic, so the same
    tree yields the same integer on any machine under any load. The identical
    margin around a wall-clock number would be a flake generator, which is the
    reason these pins count instead of timing.
    """
    counts = _counts(pattern, 'scan', lambda n: unit * n)
    ratio = _max_ratio(counts)
    assert ratio < 4.6, (
        f"{pattern!r} on {unit!r}*n: scan transitions {counts} grew by "
        f"x{ratio:.2f} per doubling — above the achieved quadratic bound")


def test_extglob_suffix_relation_is_shape_conditional():
    """``*+(a)`` suffix removal is LINEAR on ``'a'*n`` and CUBIC on ``'ba'*n``.

    Recorded as a CLASSIFICATION, not a regression: the base engine is cubic
    on the same shaped subject too, so nothing got worse — the earlier
    "cubic -> linear" reading was true only of the unshaped subject and is
    corrected here. Both rows are pinned so neither can drift unnoticed.
    """
    flat = _counts('*+(a)', 'starts', lambda n: 'a' * n)
    assert _max_ratio(flat) < 2.6, f"'*+(a)' on 'a'*n: {flat}"

    shaped = _counts('*+(a)', 'starts', lambda n: 'ba' * n, sizes=(50, 100, 200))
    assert _max_ratio(shaped) < 8.6, (
        f"'*+(a)' on 'ba'*n: {shaped} — above the achieved cubic-class bound")


def test_extglob_suffix_shaped_subject_bound():
    """``*(ab)b`` suffix removal on a subject that reaches the group."""
    counts = _counts('*(ab)b', 'starts', lambda n: 'ab' * n)
    assert _max_ratio(counts) < 4.6, counts


# --- R6(1a): the D-2 consecutive result, on the REAL consumer --------------

def _sub_all_transitions(pattern, subject):
    from psh.expansion.parameter_expansion import ParameterExpansionOps
    from psh.shell import Shell

    shell = Shell()
    shell.run_command('shopt -s extglob')
    ops = ParameterExpansionOps(shell)
    return operation_transitions(
        lambda: ops.substitute_all(subject, pattern, '-'))


@pytest.mark.parametrize('pattern,unit', [
    ('*([[:space:]])', ' '),      # D-2 ineligible class, consecutive shape
    ('+([[:space:]])', ' '),      # eligible control, consecutive shape
    ('+(a)', 'a'),                # eligible control
    ('!(x)', 'x'),                # negation control
])
def test_global_substitution_is_linear_on_matching_subjects(pattern, unit):
    """``${v//pat/-}`` on a subject that MATCHES throughout is linear.

    This is the D-2 handoff obligation's certification. It is measured with
    ``operation_transitions`` and NOT with the scan relation, because the
    consumer jumps past each match rather than probing every position — the
    scan relation would report the no-match cost and certify the wrong thing.

    The consecutive shape is the one that spent this slot looking like a floor
    it was not: base was quadratic from the per-suffix matcher rebuild, the
    shared-matcher scan fixed it, an eagerly-built pre-filter masked the fix,
    and gating the pre-filter revealed it (13.82s -> 0.0089s at N=3200).
    """
    counts = [_sub_all_transitions(pattern, unit * n) for n in SIZES]
    ratio = _max_ratio(counts)
    assert ratio < 2.6, (
        f"{pattern!r} on {unit!r}*n: operation transitions {counts} grew by "
        f"x{ratio:.2f} per doubling — global substitution is no longer linear "
        f"on a matching subject")


# --- the formerly-CUBIC quirk class ----------------------------------------

def test_bash_composition_full_match_is_quadratic_not_cubic():
    """``**(a)b`` on ``'a'*N`` — the opener-priority shape.

    The group's closure used to be rebuilt at every star entry position:
    O(n) entries x O(n^2) rebuild = CUBIC (x8.4 per doubling, 36s at N=800).
    It is now one memoized ok-table per ``(group, element, slice-end)``, which
    is QUADRATIC — the floor for this family, since the per-slice relation
    itself has O(n^2) cells.
    """
    counts = _counts('**(a)b', 'full', lambda n: 'a' * n)
    ratio = _max_ratio(counts)
    assert ratio < 4.6, (
        f"'**(a)b' full-match transitions {counts} grew by x{ratio:.2f} per "
        f"doubling — above quadratic, the closure memo regressed")


def test_plain_glob_full_match_transitions_are_linear():
    """The two-pointer boolean path stays linear — and is COUNTED.

    It reported zero transitions in a first draft (the loop was
    uninstrumented), which would have made every pin over it vacuous.
    """
    counts = _counts('*a*a*b', 'full', lambda n: 'a' * n)
    assert all(c > 0 for c in counts), (
        f"plain-glob full match reported {counts} transitions — the "
        f"two-pointer loop is not being counted, so its pins are vacuous")
    assert _max_ratio(counts) < 2.6, counts


def test_adversarial_repetition_stays_polynomial():
    """``*(a|aa)c`` on a forced-fail subject — exponential on the legacy
    regex backend, polynomial here."""
    counts = _counts('*(a|aa)c', 'full', lambda n: 'a' * n)
    assert _max_ratio(counts) < 4.6, counts


def test_negation_group_work_is_counted():
    """``_element_ends``' negation span walk is per-position work and must be
    counted, or the counter certifies linear where the wall is quadratic.

    Pinned on a SHAPED subject: on ``'a'*n`` the pattern short-circuits and
    both wall and count are linear, so only a subject that reaches the group
    can hold this honest.
    """
    counts = _counts('!(a)b', 'starts', lambda n: 'ab' * n)
    assert _max_ratio(counts) > 3.0, (
        f"'!(a)b' on 'ab'*n: {counts} — the negation branch's per-position "
        f"span walk is not being counted (wall time here is quadratic)")


# --- the consumer's SHARING property ---------------------------------------

def _matchers_built(fn):
    from psh.expansion.pattern_engine import INSTRUMENTATION
    before = INSTRUMENTATION.matchers
    fn()
    return INSTRUMENTATION.matchers - before


@pytest.mark.parametrize('pattern', ['*([[:space:]])', '+([[:space:]])',
                                     '@(x|)', 'x'])
def test_global_substitution_builds_a_bounded_number_of_matchers(pattern):
    """``${v//pat/-}`` must share ONE matcher across the whole scan.

    bash's substitution mechanics are per-remaining-suffix, and the natural
    way to implement that — hand ``value[pos:]`` to the engine each time —
    copies the subject AND discards the memo at every match, which is
    quadratic in the number of matches however fast the matcher is. It is
    invisible to a per-call transition count because each individual call
    stays small, so the property is pinned by counting CONSTRUCTIONS.
    """
    from psh.expansion.parameter_expansion import ParameterExpansionOps
    from psh.shell import Shell

    shell = Shell()
    shell.run_command('shopt -s extglob')
    ops = ParameterExpansionOps(shell)

    small = _matchers_built(lambda: ops.substitute_all('x ' * 50, pattern, '-'))
    large = _matchers_built(lambda: ops.substitute_all('x ' * 400, pattern, '-'))

    assert large <= small + 2, (
        f"{pattern!r}: {small} matchers for 50 matches but {large} for 400 — "
        f"the scan is rebuilding per suffix instead of sharing one matcher")
    assert large <= 8, (
        f"{pattern!r}: {large} matchers for one substitution — expected O(1)")
