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
increments per unit of loop work — including steps that end in a memo hit — so
the growth it reports is the growth that costs.

Bounds below are the MEASURED counts at the tip with the stated headroom, not
aspirational targets. Where a relation is genuinely polynomial rather than
linear, the pin says so and bounds the polynomial it actually achieves.
"""
import pytest

from psh.expansion.pattern_engine import (
    compile_pattern,
    count_transitions,
)

SIZES = (100, 200, 400, 800)


def _counts(pattern, relation, sizes=SIZES, subject_char='a', extglob=True):
    root = compile_pattern(pattern, extglob=extglob)
    return [count_transitions(root, subject_char * n, relation=relation)
            for n in sizes]


def _max_ratio(counts):
    """Worst doubling ratio — the growth exponent, base 2."""
    return max(b / a for a, b in zip(counts, counts[1:], strict=False) if a)


# --- chartered criterion 1: SUFFIX matching is linear in subject positions --

@pytest.mark.parametrize('pattern', ['*b', 'a*b', '*a*b', '*a*a*b', '*',
                                     '[ab]*', 'ab*', '*+(a)', '*(ab)b'])
def test_suffix_relation_transitions_are_linear(pattern):
    """``matching_starts`` (suffix removal, ``%``/``%%``) is ONE backward
    all-start pass, so doubling the subject at most doubles the work.

    Before this slot it ran a forward DP per start index — quadratic, and
    ``${v%%*+(a)}`` was CUBIC (37.7s at N=800 on the reference machine).
    """
    counts = _counts(pattern, 'starts')
    ratio = _max_ratio(counts)
    assert ratio < 2.6, (
        f"{pattern!r} suffix transitions {counts} grew by x{ratio:.2f} per "
        f"doubling — the all-start pass regressed to per-start evaluation")


# --- chartered criterion 2: NO-MATCH substitution is linear ----------------

@pytest.mark.parametrize('pattern', ['*x', 'a*x', 'zzz', '*(ab)x', '*a*b*x',
                                     '[ab]*x', '*[!a]x', '+(a)x'])
def test_no_match_substitution_scan_transitions_are_linear(pattern):
    """The substitution consumer walks every position asking "does a match
    start here?". On a subject with NO match that used to be one full forward
    DP per position; the all-start pre-filter answers all of them in one
    backward pass.

    Measured at the tip: exactly ``2n+2`` for every pattern here.
    """
    counts = _counts(pattern, 'scan')
    ratio = _max_ratio(counts)
    assert ratio < 2.6, (
        f"{pattern!r} no-match scan transitions {counts} grew by x{ratio:.2f} "
        f"per doubling — the all-start pre-filter stopped applying")


def test_no_match_scan_is_measured_through_the_real_spanner():
    """The counter must observe the path the consumer actually takes.

    ``count_transitions(relation='scan')`` drives ``CompiledPattern.spanner``
    and reads the counter off the matcher that scan used. Pinned because an
    earlier draft of this counter re-derived the scan instead — and reported
    quadratic growth for a path that had already been made linear, which is
    the same class of blindness the module docstring warns about.
    """
    root = compile_pattern('*x')
    subject = 'a' * 200
    # 2n+2 is the all-start pass plus the per-position probe; a re-derived
    # scan (one forward DP per position) would be ~n^2/2 = two orders more.
    assert count_transitions(root, subject, relation='scan') == 402


# --- the formerly-CUBIC quirk class: state the bound, pin the ratio --------

def test_bash_composition_full_match_is_quadratic_not_cubic():
    """``**(a)b`` on ``'a'*N`` — the opener-priority shape.

    The group's closure used to be rebuilt at every star entry position:
    O(n) entries x O(n^2) rebuild = CUBIC (x8.4 per doubling, 36s at N=800).
    It is now one memoized ok-table per ``(group, element, slice-end)``, which
    is QUADRATIC. Quadratic is the floor for this relation family, not a
    stopping point chosen for convenience: the per-slice relation itself has
    O(n^2) cells.
    """
    counts = _counts('**(a)b', 'full')
    ratio = _max_ratio(counts)
    assert ratio < 4.6, (
        f"'**(a)b' full-match transitions {counts} grew by x{ratio:.2f} per "
        f"doubling — above quadratic, the closure memo regressed")


def test_bash_composition_suffix_relation_is_linear():
    """``*+(a)`` suffix removal was CUBIC; the ok-table makes it linear
    (measured ``6n+1``)."""
    counts = _counts('*+(a)', 'starts')
    ratio = _max_ratio(counts)
    assert ratio < 2.6, (
        f"'*+(a)' suffix transitions {counts} grew by x{ratio:.2f} per "
        f"doubling")


def test_plain_glob_full_match_transitions_are_linear():
    """The two-pointer boolean path stays linear — and is COUNTED.

    It reported zero transitions in a first draft (the loop was
    uninstrumented), which would have made every pin over it vacuous.
    """
    counts = _counts('*a*a*b', 'full')
    assert all(c > 0 for c in counts), (
        f"plain-glob full match reported {counts} transitions — the "
        f"two-pointer loop is not being counted, so its pins are vacuous")
    assert _max_ratio(counts) < 2.6, counts


def test_adversarial_repetition_stays_polynomial():
    """``*(a|aa)c`` on a forced-fail subject — exponential on the legacy
    regex backend, polynomial here."""
    counts = _counts('*(a|aa)c', 'full', subject_char='a')
    assert _max_ratio(counts) < 4.6, counts


# --- the consumer's SHARING property (per-suffix rebuild is the regression) -

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
    stays small, so the property is pinned by counting CONSTRUCTIONS: the
    count must not grow with the number of matches.
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
