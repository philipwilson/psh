"""Unicode-aware character classification for shell identifiers."""

import string
import unicodedata


def is_identifier_start(char: str, posix_mode: bool = False) -> bool:
    """
    Check if character can start an identifier (variable name).

    Args:
        char: Character to check
        posix_mode: If True, restrict to POSIX ASCII characters

    Returns:
        True if character can start an identifier
    """
    if posix_mode:
        # POSIX mode: ASCII letters and underscore only
        return char in string.ascii_letters or char == '_'
    else:
        # Unicode mode: Unicode letters and underscore
        if char == '_':
            return True
        if len(char) != 1:
            return False
        # Check if it's a Unicode letter
        category = unicodedata.category(char)
        return category.startswith('L')  # L* categories are letters


def is_identifier_char(char: str, posix_mode: bool = False) -> bool:
    """
    Check if character can be part of an identifier (after the first character).

    Args:
        char: Character to check
        posix_mode: If True, restrict to POSIX ASCII characters

    Returns:
        True if character can be part of an identifier
    """
    if posix_mode:
        # POSIX mode: ASCII letters, digits, and underscore
        return char in string.ascii_letters or char in string.digits or char == '_'
    else:
        # Unicode mode: Unicode letters, numbers, marks, and underscore
        if char == '_':
            return True
        if len(char) != 1:
            return False
        # Check Unicode categories
        category = unicodedata.category(char)
        return (category.startswith('L') or    # Letters
                category.startswith('N') or    # Numbers
                category.startswith('M'))      # Marks (combining characters)


# The shell's token separators: the POSIX <blank>s (space, tab) plus newline
# (the command terminator, handled specially by every caller). Bash splits
# words on NOTHING else — not CR, FF, VT, and not Unicode space-category
# characters like NBSP: `echo a<NBSP>b` is ONE word in bash (usually yielding
# "command not found" for a copy-pasted NBSP), and a raw \f/\v/\r inside a
# word is an ordinary word character. Line-ending CRs of a CRLF script are
# the LINE-READING layer's job (FileInput strips one trailing CR per physical
# line; the heredoc terminator rule has the same concession) — the lexer
# itself never treats CR as whitespace.
SHELL_WHITESPACE = frozenset(' \t\n')


def is_whitespace(char: str, posix_mode: bool = False) -> bool:
    """
    Check if character is a shell token separator (space, tab, newline).

    Args:
        char: Character to check
        posix_mode: Accepted for call-site uniformity; the separator set is
            the same in both modes (bash's is too)

    Returns:
        True if character is a shell token separator
    """
    return char in SHELL_WHITESPACE


def normalize_identifier(name: str, posix_mode: bool = False, case_sensitive: bool = True) -> str:
    """
    Normalize an identifier name according to configuration.

    Args:
        name: Identifier name to normalize
        posix_mode: If True, don't apply Unicode normalization
        case_sensitive: If False, convert to lowercase

    Returns:
        Normalized identifier name
    """
    if not posix_mode:
        # Apply Unicode normalization (NFC - Canonical Composition)
        name = unicodedata.normalize('NFC', name)

    if not case_sensitive:
        name = name.lower()

    return name


def validate_identifier(name: str, posix_mode: bool = False) -> bool:
    """
    Validate that a string is a valid identifier.

    Args:
        name: Identifier name to validate
        posix_mode: If True, use POSIX validation rules

    Returns:
        True if the name is a valid identifier
    """
    if not name:
        return False

    # Check first character
    if not is_identifier_start(name[0], posix_mode):
        return False

    # Check remaining characters
    for char in name[1:]:
        if not is_identifier_char(char, posix_mode):
            return False

    return True
