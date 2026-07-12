"""Conformance: POSIX bracket classes in the ``=~`` regex operator.

``docs/user_guide/appendix_c_regex_reference.md`` claims the ``[[ ]]`` ``=~``
operator "supports POSIX Extended Regular Expressions (ERE)", with worked
examples using ``[[:alpha:]]`` / ``[[:space:]]`` classes, grouping and
backreferences (e.g. ``[[ "$text" =~ ([[:alpha:]]+)[[:space:]]+\\1 ]]``).

Before reappraisal #16 (ledger item e) the ``=~`` path built a Python regex
WITHOUT translating POSIX classes, so ``[[:punct:]]`` reached Python ``re`` as
a nested set: it matched the wrong thing AND leaked ``FutureWarning: Possible
nested set`` to stderr. Grouped classes (``([[:alpha:]]+)``) additionally
failed to parse. The fix shares the glob engine's class table with the ``=~``
ERE path (classes only — ``=~`` is a regex, not a glob) and fixes the parser's
regex-operand collection so a ``]]`` inside ``(...)`` is regex content.
"""



from conformance_framework import ConformanceTest

# All 12 POSIX classes, matched against representative subjects.
_CLASSES = ['alpha', 'digit', 'alnum', 'upper', 'lower', 'xdigit',
            'blank', 'space', 'punct', 'graph', 'print', 'cntrl']


class TestRegexPosixClasses(ConformanceTest):
    """Each class in ``=~`` must match bash's ERE result and rc."""

    def test_all_classes_subject_letter(self):
        for cls in _CLASSES:
            self.assert_identical_behavior(
                f'[[ h =~ [[:{cls}:]] ]]; echo $?')

    def test_all_classes_subject_digit(self):
        for cls in _CLASSES:
            self.assert_identical_behavior(
                f'[[ 5 =~ [[:{cls}:]] ]]; echo $?')

    def test_all_classes_subject_punct(self):
        for cls in _CLASSES:
            self.assert_identical_behavior(
                f'[[ "!" =~ [[:{cls}:]] ]]; echo $?')

    def test_all_classes_subject_space(self):
        for cls in _CLASSES:
            self.assert_identical_behavior(
                f'[[ " " =~ [[:{cls}:]] ]]; echo $?')


class TestRegexPosixClassesNegated(ConformanceTest):
    def test_negated_digit(self):
        self.assert_identical_behavior('[[ a =~ [^[:digit:]] ]]; echo $?')
        self.assert_identical_behavior('[[ 5 =~ [^[:digit:]] ]]; echo $?')

    def test_negated_alpha(self):
        self.assert_identical_behavior('[[ a =~ [^[:alpha:]] ]]; echo $?')
        self.assert_identical_behavior('[[ 5 =~ [^[:alpha:]] ]]; echo $?')


class TestRegexPosixClassesCombined(ConformanceTest):
    """Classes combined with other ERE constructs, incl. grouping/backrefs
    (the appendix_c documented examples)."""

    def test_anchored_class_quantifiers(self):
        self.assert_identical_behavior(
            '[[ abc123 =~ ^[[:alpha:]]+[[:digit:]]+$ ]]; echo $?')

    def test_adjacent_classes(self):
        self.assert_identical_behavior(
            '[[ a1b2 =~ [[:alpha:]][[:digit:]] ]]; echo $?')

    def test_upper_then_lower(self):
        self.assert_identical_behavior(
            '[[ Hello =~ [[:upper:]][[:lower:]]+ ]]; echo $?')

    def test_grouped_capture_rematch(self):
        # The BASH_REMATCH capture-group idiom over POSIX classes.
        self.assert_identical_behavior(
            '[[ abc123 =~ ([[:alpha:]]+)([[:digit:]]+) ]]; '
            'echo "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}"')

    def test_two_groups_over_classes(self):
        # Two capture groups over classes (the parse fix: a class-internal ]]
        # inside (...) must not terminate the test). NB backreferences (``\1``)
        # are a psh-only extension via Python ``re`` — POSIX ERE has none — so
        # they are deliberately NOT asserted bash-identical here.
        self.assert_identical_behavior(
            '[[ "hi ho" =~ ([[:alpha:]]+)[[:space:]]+([[:alpha:]]+) ]]; echo $?')

    def test_leading_space_comment_idiom(self):
        # appendix_c line 210: match a comment line.
        self.assert_identical_behavior(
            '[[ "   # x" =~ ^[[:space:]]*# ]]; echo $?')


class TestRegexNocasematchClasses(ConformanceTest):
    """Under nocasematch bash uses REG_ICASE, which folds [[:upper:]]/
    [[:lower:]] in ``=~`` (unlike ==/case) — pin that too."""

    def test_upper_folds_under_nocasematch(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; [[ h =~ [[:upper:]] ]]; echo $?')

    def test_lower_folds_under_nocasematch(self):
        self.assert_identical_behavior(
            'shopt -s nocasematch; [[ H =~ [[:lower:]] ]]; echo $?')


class TestRegexWithoutPosixClassesUnchanged(ConformanceTest):
    """Ordinary EREs (no POSIX class) must be untouched by the translation."""

    def test_plain_ere(self):
        self.assert_identical_behavior('[[ abc =~ ^a.c$ ]]; echo $?')
        self.assert_identical_behavior('[[ abc =~ [abc]+ ]]; echo $?')
        self.assert_identical_behavior('[[ a-b =~ [a-z]-[a-z] ]]; echo $?')
        self.assert_identical_behavior('[[ 12 =~ [0-9]{2} ]]; echo $?')
