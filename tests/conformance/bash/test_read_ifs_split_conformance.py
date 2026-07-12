"""
Conformance tests for `read` field splitting with a MIXED IFS.

When IFS mixes whitespace and non-whitespace, POSIX folds IFS whitespace
ADJACENT to an IFS non-whitespace delimiter into that one delimiter. psh's
`read` splitter treated the leading whitespace as its own separator, producing
a spurious empty field (reappraisal #13 MED): `IFS=": "` on `a : b` gave
[a, '', b] instead of [a, b]. (psh's general word-splitter was already correct;
only `read`'s splitter was wrong.)

Leading/doubled non-whitespace delimiters still produce empty fields
(`:x` => ['', x]; `x::y` => [x, '', y]); a trailing one does not (`x:` => [x]).

Verified against bash 5.2.
"""


from conformance_framework import ConformanceTest


class TestReadMixedIFS(ConformanceTest):
    def test_whitespace_around_nonws_delim(self):
        self.assert_identical_behavior(
            'echo "a : b" | { IFS=": " read x y z; echo "[$x][$y][$z]"; }')

    def test_no_surrounding_whitespace(self):
        self.assert_identical_behavior(
            'echo "a:b" | { IFS=": " read x y; echo "[$x][$y]"; }')

    def test_multiple_mixed_delims(self):
        self.assert_identical_behavior(
            'echo "a : b : c" | { IFS=": " read x y z; echo "[$x][$y][$z]"; }')

    def test_key_value_idiom(self):
        self.assert_identical_behavior(
            'echo "name : Bob" | { IFS=": " read k v; echo "k=[$k] v=[$v]"; }')

    def test_comma_space_csv(self):
        self.assert_identical_behavior(
            'echo "a, b, c" | { IFS=", " read x y z; echo "[$x][$y][$z]"; }')

    def test_read_array_mixed(self):
        self.assert_identical_behavior(
            'IFS=": " read -a a <<< "a : b"; echo n=${#a[@]} "[${a[0]}][${a[1]}]"')


class TestReadIFSEdgesUnchanged(ConformanceTest):
    """Empty-field edges that must keep matching bash."""

    def test_leading_nonws_delim(self):
        self.assert_identical_behavior(
            'IFS=: read -a a <<< ":x"; echo n=${#a[@]} "[${a[0]}][${a[1]}]"')

    def test_doubled_nonws_delim(self):
        self.assert_identical_behavior(
            'IFS=: read -a a <<< "x::y"; echo n=${#a[@]}')

    def test_trailing_nonws_delim_no_empty(self):
        self.assert_identical_behavior(
            'IFS=: read -a a <<< "x:"; echo n=${#a[@]}')

    def test_default_ifs_trims_whitespace(self):
        self.assert_identical_behavior(
            'echo "  a  b  " | { read x y; echo "[$x][$y]"; }')

    def test_trailing_whitespace_no_empty(self):
        self.assert_identical_behavior(
            'IFS=" " read -a a <<< "a b "; echo n=${#a[@]}')

    def test_leftover_to_last_var(self):
        self.assert_identical_behavior(
            'echo "a b c d" | { read x y; echo "[$x][$y]"; }')
