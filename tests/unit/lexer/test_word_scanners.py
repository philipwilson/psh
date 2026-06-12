"""Contract tests for the pure word-shape scanners (Textbook B6).

Two layers:

* direct contract tests for each mini-scanner (they are pure functions —
  text in, segment out);
* an ORACLE test for WordShapeTracker: the four retro-scanning heuristics
  it replaced are re-implemented here verbatim (from the pre-refactor
  ``LiteralRecognizer``) and the tracker must agree with them over a
  generated battery of word prefixes. If the tracker's transitions ever
  drift from the retired predicates' semantics, this fails with the
  offending prefix.
"""

import itertools

import pytest

from psh.lexer.recognizers.word_scanners import (
    UnmatchedBracketTracker,
    WordShape,
    WordShapeTracker,
    build_assignment_prefix_map,
    can_start_expansion,
    scan_assignment_prefix,
    scan_extglob_group,
    scan_glob_bracket,
    scan_inline_ansi_c,
)
from psh.lexer.unicode_support import is_identifier_char, is_identifier_start

# ---------------------------------------------------------------------------
# The retired retro-heuristics, re-implemented as oracles (verbatim
# semantics from the pre-B6 LiteralRecognizer).
# ---------------------------------------------------------------------------


def oracle_is_variable_assignment_start(value, posix=False):
    if not value:
        return False
    if '[' in value:
        return oracle_is_array_assignment_start(value, posix)
    if not is_identifier_start(value[0], posix):
        return False
    return all(is_identifier_char(c, posix) for c in value)


def oracle_is_array_assignment_start(value, posix=False):
    bracket_pos = value.find('[')
    if bracket_pos == -1:
        return False
    var_name = value[:bracket_pos]
    if not var_name:
        return False
    if not is_identifier_start(var_name[0], posix):
        return False
    return all(is_identifier_char(c, posix) for c in var_name)


def oracle_is_in_variable_assignment_value(value, posix=False):
    if not value or '=' not in value:
        return False
    if value.endswith('='):
        return True
    if value.endswith('+=') or (']=' in value and value.endswith('=')):
        return True
    equals_pos = value.rfind('=')
    before_equals = value[:equals_pos]
    if before_equals.endswith('+'):
        before_equals = before_equals[:-1]
    return (oracle_is_variable_assignment_start(before_equals, posix)
            or oracle_is_array_assignment_start(before_equals, posix))


def oracle_is_in_string_concatenation(value, posix=False):
    if not value:
        return False
    for i, char in enumerate(value):
        if i == 0:
            if not (is_identifier_start(char, posix) or char in '/.~'):
                return False
        else:
            if not (is_identifier_char(char, posix) or char in '/.~-'):
                if char in '=[](){}|&;<>!':
                    return False
    return True


def oracle_plus_equals_array(value, posix=False):
    """value half of _looks_like_array_assignment_before_plus_equals
    (the input_text lookahead for '=' stays at the call site)."""
    if not value or not value.endswith(']'):
        return False
    if '[' not in value:
        return False
    bracket_pos = value.find('[')
    var_name = value[:bracket_pos]
    if not var_name:
        return False
    if not is_identifier_start(var_name[0], posix):
        return False
    if not all(is_identifier_char(c, posix) for c in var_name):
        return False
    bracket_count = 0
    for char in value:
        if char == '[':
            bracket_count += 1
        elif char == ']':
            bracket_count -= 1
    return bracket_count == 0 and value.endswith(']')


def oracle_is_identifier(value, posix=False):
    """The identifier half of _is_potential_array_assignment_start."""
    if not value:
        return False
    if not is_identifier_start(value[0], posix):
        return False
    return all(is_identifier_char(c, posix) for c in value)


def _battery():
    """Generated word prefixes covering the shape grammar's corners."""
    seeds = [
        '', 'a', 'ab', '_x9', '1a', 'a-b', './p', '~/q', 'a,b', 'a%b',
        'a=', 'a=b', 'a=b=', 'a=b=c', 'v=a[', 'v=a[=', 'a+', 'a+=',
        'a+=b', 'a++=', 'a[', 'a[]', 'a[0]', 'a[0]=', 'a[0]=x',
        'a[0]=x=', 'a[0]=x=y', 'a[0]+', 'a[0]+=', 'a[i][j]', 'a[i][j]=',
        'a]b[', 'a[b[', 'a[b]c]', '[x', ']x', '=x', '+x', 'va', 'v=',
        'v==', 'v==y', 'a\\b', 'a"b', "a'b", 'a[x\\]', 'pre', 'a=b+',
        'a[0]"', 'x[a b]', 'a[$v]', 'a[$(e)]',
    ]
    # All 1-3 char words over a small adversarial alphabet
    alphabet = ['a', '_', '1', '[', ']', '=', '+', '.', '/', '~', '-',
                ',', '!', '<', '\\']
    words = list(seeds)
    for n in (1, 2, 3):
        for combo in itertools.product(alphabet, repeat=n):
            words.append(''.join(combo))
    return words


def test_word_shape_tracker_agrees_with_retired_heuristics():
    """Feeding any word prefix, the tracker's properties equal the four
    retired retro-predicates evaluated on that prefix."""
    mismatches = []
    for word in _battery():
        tracker = WordShapeTracker()
        tracker.feed(word)
        checks = [
            ('can_take_assignment', tracker.can_take_assignment,
             oracle_is_variable_assignment_start(word)),
            ('in_assignment_value', tracker.in_assignment_value,
             oracle_is_in_variable_assignment_value(word)),
            ('concat_safe', tracker.concat_safe,
             oracle_is_in_string_concatenation(word)),
            ('plus_assign_ready', tracker.plus_assign_ready,
             oracle_plus_equals_array(word)),
            ('is_identifier', tracker.is_identifier,
             oracle_is_identifier(word)),
        ]
        for name, got, expected in checks:
            if got != expected:
                mismatches.append(f"  {word!r}.{name}: tracker={got} "
                                  f"oracle={expected}")
    assert not mismatches, (
        f"{len(mismatches)} tracker/oracle disagreements:\n"
        + "\n".join(mismatches[:40]))


def test_word_shape_tracker_incremental_equals_batch():
    """Feeding char-by-char equals feeding the whole string at once."""
    for word in ['a[0]=x', 'v=a=b', "pre", 'a+=', 'x[a\\]']:
        one = WordShapeTracker()
        one.feed(word)
        per = WordShapeTracker()
        for ch in word:
            per.feed(ch)
        assert one.shape == per.shape
        assert one.in_assignment_value == per.in_assignment_value
        assert one.concat_safe == per.concat_safe


def test_word_shape_enum_progression():
    """The canonical NEUTRAL → ASSIGN_NAME → ASSIGN_VALUE walk."""
    t = WordShapeTracker()
    assert t.shape is WordShape.NEUTRAL  # empty word
    t.feed('v')
    assert t.shape is WordShape.ASSIGN_NAME
    t.feed('=')
    assert t.shape is WordShape.ASSIGN_VALUE
    t.feed('x')
    assert t.shape is WordShape.ASSIGN_VALUE

    t2 = WordShapeTracker()
    t2.feed('./path')
    assert t2.shape is WordShape.NEUTRAL
    assert t2.concat_safe  # pre$'x'post-style concatenation allowed

    t3 = WordShapeTracker()
    t3.feed('arr[0]')
    assert t3.shape is WordShape.ASSIGN_NAME
    assert t3.plus_assign_ready  # arr[0]+= may continue
    t3.feed('+=')
    assert t3.shape is WordShape.ASSIGN_VALUE


# ---------------------------------------------------------------------------
# Mini-scanner contracts
# ---------------------------------------------------------------------------

class TestScanGlobBracket:
    def test_simple_class_closes(self):
        assert scan_glob_bracket('[ab]c', 0) == ('[ab]', 4, False)

    def test_collects_whitespace_literally(self):
        # Legacy-pinned: a space does not end a glob bracket segment.
        assert scan_glob_bracket('[a b]', 0) == ('[a b]', 5, False)

    def test_unclosed_runs_to_end(self):
        assert scan_glob_bracket('[ab', 0) == ('[ab', 3, False)

    def test_quote_ends_segment(self):
        seg, pos, by_quote = scan_glob_bracket('["ok"]', 0)
        assert (seg, pos, by_quote) == ('[', 1, True)

    def test_valid_expansion_ends_segment(self):
        seg, pos, by_quote = scan_glob_bracket('[$v]', 0)
        assert (seg, pos, by_quote) == ('[', 1, True)

    def test_invalid_dollar_is_literal(self):
        seg, pos, by_quote = scan_glob_bracket('[$]', 0)
        assert (seg, pos, by_quote) == ('[$]', 3, False)

    def test_escaped_pair_collected(self):
        assert scan_glob_bracket('[\\]]', 0) == ('[\\]]', 4, False)


class TestScanExtglobGroup:
    def test_simple_group(self):
        assert scan_extglob_group('(a|b)c', 0) == ('(a|b)', 5)

    def test_nested_group(self):
        assert scan_extglob_group('(a|(b|c))d', 0) == ('(a|(b|c))', 9)

    def test_unbalanced_returns_none(self):
        assert scan_extglob_group('(a|b', 0) is None

    def test_escaped_paren_does_not_close(self):
        assert scan_extglob_group('(a\\))', 0) == ('(a\\))', 5)

    def test_not_at_paren_returns_none(self):
        assert scan_extglob_group('x(a)', 0) is None


class TestScanAssignmentPrefix:
    def test_simple_subscript(self):
        # 'a[0]=v' — scanning from the '[' at index 1
        assert scan_assignment_prefix('a[0]=v', 1) == ('[0]=', 5)

    def test_plus_equals(self):
        assert scan_assignment_prefix('a[k]+=v', 1) == ('[k]+=', 6)

    def test_quoted_key_collected_literally(self):
        assert scan_assignment_prefix('a["k"]=v', 1) == ('["k"]=', 7)

    def test_glob_class_not_confirmed(self):
        assert scan_assignment_prefix('x[ab]', 1) is None
        assert scan_assignment_prefix('x[a-z]*', 1) is None

    def test_whitespace_breaks_pattern(self):
        assert scan_assignment_prefix('h[a b]=v', 1) is None

    def test_expansion_opaque_in_subscript(self):
        # The space inside $( ) must not break the subscript.
        text = 'a[$(echo 1 + 1)]=v'
        assert scan_assignment_prefix(text, 1) == ('[$(echo 1 + 1)]=', 17)

    def test_escaped_bracket_not_an_opener(self):
        # a[\[x]=v — the escaped '[' is literal; subscript still closes.
        text = 'a[\\[x]=v'
        assert scan_assignment_prefix(text, 1) == ('[\\[x]=', 7)

    def test_map_consultation_agrees_with_local_scan(self):
        text = 'a[0]=v'
        amap = build_assignment_prefix_map(text)
        assert scan_assignment_prefix(text, 1, amap) == \
            scan_assignment_prefix(text, 1, None)


class TestScanInlineAnsiC:
    def test_decodes_escapes(self):
        assert scan_inline_ansi_c("$'a\\nb'", 0) == ('a\nb', 7)

    def test_not_ansi_c_returns_none(self):
        assert scan_inline_ansi_c('$x', 0) is None

    def test_unclosed_returns_none(self):
        assert scan_inline_ansi_c("$'abc", 0) is None


class TestCanStartExpansion:
    @pytest.mark.parametrize('text,expected', [
        ('$x', True), ('$(cmd)', True), ('${v}', True), ("$'s'", True),
        ('$"s"', True), ('$?', True), ('$#', True), ('$', False),
        ('$%', False), ('$ ', False),
    ])
    def test_cases(self, text, expected):
        assert can_start_expansion(text, 0) is expected


class TestAssignmentPrefixMap:
    def test_confirmed_subscript_marked(self):
        amap = build_assignment_prefix_map('a["k"]=v')
        # Positions inside the subscript (after '[', through ']') are marked.
        assert amap[2] and amap[5]
        assert not amap[0] and not amap[7]

    def test_glob_class_not_marked(self):
        amap = build_assignment_prefix_map('echo x[ab]')
        assert not any(amap)

    def test_boundary_breaks_subscript(self):
        amap = build_assignment_prefix_map('h[a b]=v')
        assert not any(amap)


class TestUnmatchedBracketTracker:
    def test_inside_after_open(self):
        t = UnmatchedBracketTracker()
        t.feed('a[')
        assert t.inside
        t.feed('0]')
        assert not t.inside

    def test_quoted_brackets_ignored(self):
        t = UnmatchedBracketTracker()
        t.feed('a["]"')  # the quoted ']' must not close the subscript
        assert t.inside

    def test_glob_class_chain(self):
        t = UnmatchedBracketTracker()
        t.feed('*[[:upper:]]*')
        assert not t.inside
