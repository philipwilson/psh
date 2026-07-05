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


# --- Case mapping for ${x^^}/${x,,}/${x~~} and declare -u/-l ---------------
#
# bash's case-modification uses the C library's towupper/towlower, which map
# one codepoint to exactly one codepoint. Python's str.upper()/str.lower()
# apply the *full* Unicode mappings, which can GROW the string (ß -> "SS",
# the ﬀ ligature -> "FF", İ -> "i̇"). That length change is wrong for shells:
# `x=straße; echo ${x^^}` is STRAßE in bash, not STRASSE.
#
# We reproduce the 1:1 (Unicode "simple") mapping instead: a codepoint is
# case-mapped only when its Unicode mapping is itself a single codepoint;
# otherwise it is left unchanged. This is length-safe by construction and is
# what glibc/newer-libc bash produces. (macOS's frozen libc case tables lag the
# Unicode version, so a handful of recent/rare codepoints — titlecase digraphs
# ǅǈǋǲ, polytonic-Greek iota-subscript, Roman numerals, circled letters — map
# under this rule but not under macOS bash; they DO map under Linux bash, and
# case-mapping is host-libc-dependent regardless, so we follow Unicode.)


def _simple_upper_char(char: str) -> str:
    upper = char.upper()
    return upper if len(upper) == 1 else char


def _simple_lower_char(char: str) -> str:
    lower = char.lower()
    if len(lower) == 1:
        return lower
    # U+0130 (İ, dotted capital I) is the ONLY codepoint in all of Unicode
    # whose full lowercase spans two codepoints ('i' + combining dot); its
    # simple (single-codepoint) lowercase is plain 'i', which is what bash
    # produces. No general table is needed — every other codepoint already
    # lowercases to a single codepoint above.
    return 'i' if char == 'İ' else char


def simple_upper(text: str) -> str:
    """Uppercase like bash: each codepoint maps to at most one codepoint."""
    return ''.join(_simple_upper_char(c) for c in text)


def simple_lower(text: str) -> str:
    """Lowercase like bash: each codepoint maps to at most one codepoint."""
    return ''.join(_simple_lower_char(c) for c in text)


def toggle_case(text: str) -> str:
    """Toggle case per codepoint like bash's ${x~~}.

    bash tests each codepoint with iswupper(): an uppercase codepoint is
    lowercased, everything else is uppercased — both via the length-safe
    (single-codepoint) mappings above.
    """
    return ''.join(_simple_lower_char(c) if c.isupper() else _simple_upper_char(c)
                   for c in text)


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


# The shell's single authoritative "is this a valid variable/function NAME?"
# predicate. Every runtime name-validation site — assignment (``NAME=value``),
# ``declare``/``export``/``readonly``/``local``, ``read NAME``, ``for NAME in``,
# function definitions, and ``${NAME}`` — routes here so identifier policy has
# ONE definition instead of a dozen divergent ``str.isalpha()``/``isalnum()``
# copies.
#
# ``posix_mode`` (wired to ``set -o posix``) restricts names to the POSIX/ASCII
# set ``[A-Za-z_][A-Za-z0-9_]*``, matching bash. With posix mode OFF, the
# lenient Unicode-letter rule applies — psh's DELIBERATE, documented divergence
# from bash (see ``docs/user_guide/17_differences_from_bash.md``). ``is_valid_name``
# is the preferred name; ``validate_identifier`` remains as the original alias.
is_valid_name = validate_identifier
