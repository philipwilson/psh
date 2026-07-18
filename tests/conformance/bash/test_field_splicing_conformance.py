"""Field-splicing and per-character glob protection conformance (reappraisal
#20 H5/H6).

Every row is verified identical to bash 5.2. H5: an unquoted fragment adjacent
to a quoted ``$@``/``${a[@]}`` undergoes IFS field splitting (it was previously
concatenated into a seed). H6: a protected metacharacter (quoted, single-quoted,
or backslash-escaped) beside an active one stays literal during pathname
generation (protection was previously word-wide). The combined rows splice a
field and then glob the resulting field.

Glob rows build a controlled temp dir so the match set is deterministic.
"""
from conformance_framework import ConformanceTest


class TestFieldSplicingH5(ConformanceTest):
    """H5: unquoted fragments adjacent to a quoted $@/[@] must field-split."""

    def test_at_suffix_unquoted_splits(self):
        self.assert_identical_behavior(
            'set -- a b; x="c d"; printf "<%s>" "$@"$x')

    def test_at_prefix_unquoted_splits(self):
        self.assert_identical_behavior(
            'set -- a b; x="c d"; printf "<%s>" $x"$@"')

    def test_at_both_sides_split(self):
        self.assert_identical_behavior(
            'set -- a b; x="c d"; y="e f"; printf "<%s>" $y"$@"$x')

    def test_array_at_suffix_splits(self):
        self.assert_identical_behavior(
            'a=(a b); x="c d"; printf "<%s>" "${a[@]}"$x')

    def test_multiple_at_with_fragment(self):
        self.assert_identical_behavior(
            'set -- 1 2; x="c d"; printf "<%s>" "$@"$x"$@"')

    def test_at_suffix_custom_ifs(self):
        self.assert_identical_behavior(
            'IFS=:; set -- a b; x="c:d"; printf "<%s>" "$@"$x')

    def test_empty_at_with_affixes_is_one_field(self):
        self.assert_identical_behavior('set --; printf "<%s>" pre"$@"post')

    def test_empty_at_alone_is_zero_fields(self):
        self.assert_identical_behavior('set --; printf "<%s>" "$@"')

    def test_at_then_at_splice(self):
        self.assert_identical_behavior(
            'set -- a b; printf "<%s>" x"$@"y"$@"z')


class TestGlobProtectionH6(ConformanceTest):
    """H6: per-character glob protection in a pathname-generated field."""

    def _in_dir(self, files, script):
        touch = ' '.join(f"'{f}'" for f in files)
        return (f'd=$(mktemp -d); cd "$d"; touch {touch}; '
                f'{script}; cd /; rm -rf "$d"')

    def test_quoted_star_beside_active_star(self):
        self.assert_identical_behavior(self._in_dir(
            ('*lit', 'fa', 'abc'), 'printf "<%s>" "*"*'))

    def test_single_quoted_star_beside_active_star(self):
        self.assert_identical_behavior(self._in_dir(
            ('*lit', 'fa', 'abc'), "printf \"<%s>\" '*'*"))

    def test_escaped_star_beside_active_star(self):
        self.assert_identical_behavior(self._in_dir(
            ('a*b', 'abc', 'aXb'), 'printf "<%s>" a\\*b*'))

    def test_quoted_var_glob_beside_active_star(self):
        self.assert_identical_behavior(self._in_dir(
            ('a*b', 'abc', 'aXb'), 'x="a*b"; printf "<%s>" "$x"*'))

    def test_mixed_single_quote_star(self):
        self.assert_identical_behavior(self._in_dir(
            ('a*b', 'abc', 'aXb'), "printf \"<%s>\" a'*'b*"))

    def test_var_glob_then_active_star(self):
        self.assert_identical_behavior(self._in_dir(
            ('a*b', 'abc'), 'x="a*b"; y="*"; printf "<%s>" "$x"$y'))

    def test_quoted_extglob_stays_literal(self):
        self.assert_identical_behavior(self._in_dir(
            ('faXb', 'fa', 'fb'),
            'shopt -s extglob; printf "<%s>" "f"a"?(X)"b'))

    def test_active_star_still_globs(self):
        self.assert_identical_behavior(self._in_dir(
            ('fa', 'fb', 'abc'), 'printf "<%s>" fa*'))


class TestFieldSplicingWithGlobH5H6(ConformanceTest):
    """Combined: splice a field, THEN glob the resulting field."""

    def _in_dir(self, files, script):
        touch = ' '.join(f"'{f}'" for f in files)
        return (f'd=$(mktemp -d); cd "$d"; touch {touch}; '
                f'{script}; cd /; rm -rf "$d"')

    def test_at_suffix_glob(self):
        self.assert_identical_behavior(self._in_dir(
            ('fa', 'fb', 'abc'), 'set -- fa fb; printf "<%s>" "$@"*'))

    def test_at_suffix_var_glob(self):
        self.assert_identical_behavior(self._in_dir(
            ('fa', 'fb', 'abc'), 'set -- a; x="b*"; printf "<%s>" "$@"$x'))

    def test_array_at_suffix_glob(self):
        self.assert_identical_behavior(self._in_dir(
            ('fa', 'fb', 'abc'), 'a=(fa fb); printf "<%s>" "${a[@]}"*'))
