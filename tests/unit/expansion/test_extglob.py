"""Unit tests for the extglob pattern engine."""

import re

from psh.expansion.extglob import (
    _find_matching_paren,
    _split_pattern_list,
    contains_extglob,
    expand_extglob,
    extglob_to_regex,
)


class TestContainsExtglob:
    """Tests for contains_extglob detection."""

    def test_basic_operators(self):
        assert contains_extglob('?(a|b)')
        assert contains_extglob('*(a|b)')
        assert contains_extglob('+(a|b)')
        assert contains_extglob('@(a|b)')
        assert contains_extglob('!(a|b)')

    def test_no_extglob(self):
        assert not contains_extglob('*.txt')
        assert not contains_extglob('file?.log')
        assert not contains_extglob('[abc]')
        assert not contains_extglob('hello')
        assert not contains_extglob('')

    def test_prefix_without_paren(self):
        """Characters that look like extglob prefix but have no '('."""
        assert not contains_extglob('?abc')
        assert not contains_extglob('*abc')
        assert not contains_extglob('+abc')
        assert not contains_extglob('@abc')
        assert not contains_extglob('!abc')

    def test_escaped_prefix(self):
        """Backslash-escaped prefix chars should not trigger extglob."""
        assert not contains_extglob('\\?(a|b)')
        assert not contains_extglob('\\*(a|b)')

    def test_mixed_with_regular_glob(self):
        assert contains_extglob('file_@(a|b).txt')
        assert contains_extglob('*.+(c|h)')

    def test_nested_extglob(self):
        assert contains_extglob('+(a|*(b|c))')


class TestFindMatchingParen:
    """Tests for balanced parenthesis finding."""

    def test_simple(self):
        assert _find_matching_paren('(abc)', 0) == 4

    def test_nested(self):
        assert _find_matching_paren('(a(b)c)', 0) == 6

    def test_deeply_nested(self):
        assert _find_matching_paren('(a(b(c)))', 0) == 8

    def test_unbalanced(self):
        assert _find_matching_paren('(abc', 0) is None

    def test_escaped_paren(self):
        assert _find_matching_paren('(a\\)b)', 0) == 5

    def test_from_offset(self):
        s = 'xx(abc)yy'
        assert _find_matching_paren(s, 2) == 6


class TestSplitPatternList:
    """Tests for splitting on | respecting nesting."""

    def test_simple(self):
        assert _split_pattern_list('a|b|c') == ['a', 'b', 'c']

    def test_single(self):
        assert _split_pattern_list('abc') == ['abc']

    def test_nested_parens(self):
        assert _split_pattern_list('a|(b|c)|d') == ['a', '(b|c)', 'd']

    def test_empty_alternatives(self):
        assert _split_pattern_list('|a|') == ['', 'a', '']

    def test_escaped_pipe(self):
        assert _split_pattern_list('a\\|b|c') == ['a\\|b', 'c']


class TestExtglobToRegex:
    """Tests for pattern-to-regex conversion."""

    def test_question_mark_operator(self):
        regex = extglob_to_regex('?(a|b)', anchored=False)
        assert re.fullmatch(regex, '') is not None
        assert re.fullmatch(regex, 'a') is not None
        assert re.fullmatch(regex, 'b') is not None
        assert re.fullmatch(regex, 'ab') is None

    def test_star_operator(self):
        regex = extglob_to_regex('*(a|b)', anchored=False)
        assert re.fullmatch(regex, '') is not None
        assert re.fullmatch(regex, 'a') is not None
        assert re.fullmatch(regex, 'aab') is not None
        assert re.fullmatch(regex, 'bba') is not None
        assert re.fullmatch(regex, 'c') is None

    def test_plus_operator(self):
        regex = extglob_to_regex('+(a|b)', anchored=False)
        assert re.fullmatch(regex, '') is None
        assert re.fullmatch(regex, 'a') is not None
        assert re.fullmatch(regex, 'ab') is not None
        assert re.fullmatch(regex, 'c') is None

    def test_at_operator(self):
        regex = extglob_to_regex('@(a|b)', anchored=False)
        assert re.fullmatch(regex, 'a') is not None
        assert re.fullmatch(regex, 'b') is not None
        assert re.fullmatch(regex, '') is None
        assert re.fullmatch(regex, 'ab') is None

    def test_regular_glob_chars(self):
        regex = extglob_to_regex('*.txt', anchored=False)
        assert re.fullmatch(regex, 'file.txt') is not None
        assert re.fullmatch(regex, '.txt') is not None
        assert re.fullmatch(regex, 'file.log') is None

    def test_question_glob(self):
        regex = extglob_to_regex('file?.txt', anchored=False)
        assert re.fullmatch(regex, 'file1.txt') is not None
        assert re.fullmatch(regex, 'file.txt') is None

    def test_character_class(self):
        regex = extglob_to_regex('[abc]', anchored=False)
        assert re.fullmatch(regex, 'a') is not None
        assert re.fullmatch(regex, 'd') is None

    def test_negated_character_class(self):
        regex = extglob_to_regex('[!abc]', anchored=False)
        assert re.fullmatch(regex, 'd') is not None
        assert re.fullmatch(regex, 'a') is None

    def test_mixed_glob_and_extglob(self):
        regex = extglob_to_regex('file_@(a|b).txt', anchored=False)
        assert re.fullmatch(regex, 'file_a.txt') is not None
        assert re.fullmatch(regex, 'file_b.txt') is not None
        assert re.fullmatch(regex, 'file_c.txt') is None

    def test_nested_extglob(self):
        regex = extglob_to_regex('+(a|*(b|c))', anchored=False)
        assert re.fullmatch(regex, 'a') is not None
        assert re.fullmatch(regex, 'bbc') is not None
        # +(a|*(b|c)) matches empty since *(b|c) matches empty
        assert re.fullmatch(regex, '') is not None

    def test_nested_at_plus(self):
        """@(a|+(b|c)) - exactly one: a, or one-or-more of b/c."""
        regex = extglob_to_regex('@(a|+(b|c))', anchored=False)
        assert re.fullmatch(regex, 'a') is not None
        assert re.fullmatch(regex, 'b') is not None
        assert re.fullmatch(regex, 'bcc') is not None
        assert re.fullmatch(regex, '') is None
        assert re.fullmatch(regex, 'd') is None

    def test_anchored_start(self):
        # End anchor is ``\Z`` (true end of string), not ``$`` (which also
        # matches before a trailing newline and would over-match $'ab\n').
        regex = extglob_to_regex('@(a|b)', anchored=True, from_start=True)
        assert regex.startswith('^')
        assert regex.endswith(r'\Z')

    def test_anchored_end_only(self):
        regex = extglob_to_regex('@(a|b)', anchored=True, from_start=False)
        assert not regex.startswith('^')
        assert regex.endswith(r'\Z')

    def test_for_pathname(self):
        regex = extglob_to_regex('*', anchored=False, for_pathname=True)
        assert re.fullmatch(regex, 'abc') is not None
        assert re.fullmatch(regex, 'a/b') is None

    def test_escaped_chars(self):
        regex = extglob_to_regex('\\*', anchored=False)
        assert re.fullmatch(regex, '*') is not None
        assert re.fullmatch(regex, 'abc') is None

    def test_literal_dot(self):
        regex = extglob_to_regex('file.txt', anchored=False)
        assert re.fullmatch(regex, 'file.txt') is not None
        assert re.fullmatch(regex, 'filextxt') is None


class TestExpandExtglob:
    """Tests for directory-based extglob expansion."""

    def test_basic_expansion(self, tmp_path):
        # Create test files
        (tmp_path / 'file_a.txt').touch()
        (tmp_path / 'file_b.txt').touch()
        (tmp_path / 'file_c.log').touch()

        result = expand_extglob('@(file_a|file_b).txt', str(tmp_path))
        assert result == ['file_a.txt', 'file_b.txt']

    def test_no_matches(self, tmp_path):
        (tmp_path / 'file.txt').touch()
        result = expand_extglob('@(nope).txt', str(tmp_path))
        assert result == []

    def test_negation_expansion(self, tmp_path):
        (tmp_path / 'keep.txt').touch()
        (tmp_path / 'skip.log').touch()
        (tmp_path / 'also.txt').touch()

        result = expand_extglob('!(*.log)', str(tmp_path))
        assert 'keep.txt' in result
        assert 'also.txt' in result
        assert 'skip.log' not in result

    def test_dotglob_false(self, tmp_path):
        (tmp_path / '.hidden').touch()
        (tmp_path / 'visible').touch()

        result = expand_extglob('*', str(tmp_path), dotglob=False)
        assert 'visible' in result
        assert '.hidden' not in result

    def test_dotglob_true(self, tmp_path):
        (tmp_path / '.hidden').touch()
        (tmp_path / 'visible').touch()

        result = expand_extglob('*', str(tmp_path), dotglob=True)
        assert 'visible' in result
        assert '.hidden' in result

    def test_dot_pattern_matches_dotfiles(self, tmp_path):
        """Pattern starting with '.' should match dotfiles even without dotglob."""
        (tmp_path / '.gitignore').touch()
        (tmp_path / '.bashrc').touch()
        (tmp_path / 'readme').touch()

        result = expand_extglob('.@(gitignore|bashrc)', str(tmp_path))
        assert '.gitignore' in result
        assert '.bashrc' in result
        assert 'readme' not in result

    def test_plus_expansion(self, tmp_path):
        (tmp_path / 'a').touch()
        (tmp_path / 'aa').touch()
        (tmp_path / 'aaa').touch()
        (tmp_path / 'b').touch()

        result = expand_extglob('+(a)', str(tmp_path))
        assert result == ['a', 'aa', 'aaa']

    def test_nonexistent_directory(self):
        result = expand_extglob('*', '/nonexistent/path/12345')
        assert result == []

    def test_sorted_output(self, tmp_path):
        (tmp_path / 'c.txt').touch()
        (tmp_path / 'a.txt').touch()
        (tmp_path / 'b.txt').touch()

        result = expand_extglob('*.txt', str(tmp_path))
        assert result == ['a.txt', 'b.txt', 'c.txt']
