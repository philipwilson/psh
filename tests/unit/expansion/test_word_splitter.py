"""Unit tests for WordSplitter POSIX IFS splitting."""

from psh.expansion.word_splitter import WordSplitter


def test_word_splitter_default_ifs_multiple_words():
    splitter = WordSplitter()
    result = splitter.split('one two\tthree\nfour', ' \t\n')
    assert result == ['one', 'two', 'three', 'four']


def test_word_splitter_returns_single_word():
    splitter = WordSplitter()
    result = splitter.split('single', ' \t\n')
    assert result == ['single']


def test_word_splitter_handles_empty_ifs():
    splitter = WordSplitter()
    result = splitter.split('a b c', '')
    assert result == ['a b c']


def test_word_splitter_none_ifs_uses_default():
    """Unset IFS (None) should use default space/tab/newline splitting."""
    splitter = WordSplitter()
    result = splitter.split('a b\tc', None)
    assert result == ['a', 'b', 'c']


def test_word_splitter_none_text_returns_empty():
    splitter = WordSplitter()
    result = splitter.split(None, ' \t\n')
    assert result == []


def test_word_splitter_leading_trailing_whitespace_trimmed():
    """Leading and trailing IFS whitespace should be trimmed."""
    splitter = WordSplitter()
    result = splitter.split('  hello world  ', ' \t\n')
    assert result == ['hello', 'world']


def test_word_splitter_consecutive_whitespace_collapses():
    """Consecutive IFS whitespace characters collapse into one delimiter."""
    splitter = WordSplitter()
    result = splitter.split('a   b  c', ' \t\n')
    assert result == ['a', 'b', 'c']


def test_word_splitter_non_whitespace_ifs_preserves_empty_fields():
    """Non-whitespace IFS chars always produce a field boundary."""
    splitter = WordSplitter()
    result = splitter.split('a::b', ':')
    assert result == ['a', '', 'b']


def test_word_splitter_non_whitespace_ifs_leading_delimiter():
    """Leading non-whitespace IFS char produces an empty leading field."""
    splitter = WordSplitter()
    result = splitter.split(':a:b', ':')
    assert result == ['', 'a', 'b']


def test_word_splitter_non_whitespace_ifs_trailing_delimiter():
    """Trailing non-whitespace IFS char produces an empty trailing field
    only if there's content before it (the field after : is appended via current_field)."""
    splitter = WordSplitter()
    # 'a:b:' -> fields: 'a', 'b', then trailing ':' appends empty current_field
    # Actually per our implementation, trailing ':' appends current_field ('b'),
    # then no more chars, so current_field is empty and not appended.
    # Let's check: 'a' -> current, ':' -> append 'a', start new.
    # 'b' -> current. ':' -> append 'b', start new. End -> current empty, not appended.
    # Result: ['a', 'b'] - wait, that's wrong for POSIX.
    # Actually POSIX says trailing non-ws IFS produces empty field.
    # Our implementation: at ':', we append current_field. Then i++.
    # After the last ':', current_field is [] and i is at end. Empty field not added.
    # This matches bash behavior: echo $(IFS=: ; set -- a:b: ; echo $#) -> 2
    result = splitter.split('a:b:', ':')
    # Bash produces 2 fields for 'a:b:' with IFS=:
    assert result == ['a', 'b']


def test_word_splitter_mixed_whitespace_and_non_whitespace_ifs():
    """Mixed IFS: IFS whitespace adjacent to non-whitespace delimiter
    forms a single delimiter (POSIX 2.6.5)."""
    splitter = WordSplitter()
    # ' a : b ' with IFS=': ' -> 'a' and 'b'
    # The space-colon-space is one combined delimiter
    result = splitter.split(' a : b ', ': ')
    assert result == ['a', 'b']


def test_word_splitter_only_whitespace_ifs_input():
    """Input that is only IFS whitespace should produce no fields."""
    splitter = WordSplitter()
    result = splitter.split('   ', ' \t\n')
    assert result == []


def test_word_splitter_only_non_whitespace_ifs_input():
    """Input that is only non-whitespace IFS chars.
    '::' with IFS=: produces 2 fields (bash behavior: trailing delimiter
    does not produce an extra empty field)."""
    splitter = WordSplitter()
    result = splitter.split('::', ':')
    assert result == ['', '']


def test_word_splitter_backslash_is_plain_data():
    """A backslash in expansion data does not escape IFS characters.

    bash: x='a\\ b'; printf '[%s]' $x → [a\\][b]. Escapes in *literal*
    word text are protected structurally by the caller (only expansion
    results are split), not by the splitter.
    """
    splitter = WordSplitter()
    assert splitter.split('a\\ b', ' \t\n') == ['a\\', 'b']


def test_word_splitter_backslash_preserved_in_word():
    """Backslashes within words should be preserved."""
    splitter = WordSplitter()
    result = splitter.split('hello\\world', ' \t\n')
    assert result == ['hello\\world']


def test_word_splitter_backslash_not_swallowed():
    """Backslashes are kept in the output fields (bash: a\\:b with IFS=:
    splits into a\\ and b)."""
    splitter = WordSplitter()
    assert splitter.split('a\\:b', ':') == ['a\\', 'b']


def test_word_splitter_colon_separated_path():
    """Splitting PATH-like strings with IFS=:"""
    splitter = WordSplitter()
    result = splitter.split('/usr/bin:/usr/local/bin:/bin', ':')
    assert result == ['/usr/bin', '/usr/local/bin', '/bin']


def test_word_splitter_whitespace_around_non_whitespace_delimiter():
    """IFS whitespace adjacent to non-whitespace delimiter is consumed."""
    splitter = WordSplitter()
    result = splitter.split('a : b', ': ')
    # ' ' before ':' skipped (leading ws trimming or ws after 'a' field)
    # ':' produces boundary
    # ' ' after ':' consumed as IFS ws after non-ws delimiter
    assert result == ['a', 'b']
