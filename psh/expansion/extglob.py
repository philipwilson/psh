"""Extended globbing (extglob) pattern matching.

Implements bash-compatible extglob patterns:
  ?(pat|pat)  - Zero or one occurrence
  *(pat|pat)  - Zero or more occurrences
  +(pat|pat)  - One or more occurrences
  @(pat|pat)  - Exactly one occurrence
  !(pat|pat)  - Anything except the pattern

Patterns support nesting and pipe-separated alternatives.
"""

import os
import re
from typing import List, Optional

# Characters that introduce an extglob operator
_EXTGLOB_PREFIXES = frozenset('?*+@!')


def contains_extglob(pattern: str) -> bool:
    """Check if pattern contains extglob operators.

    Respects backslash escapes.
    """
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == '\\' and i + 1 < len(pattern):
            i += 2  # skip escaped char
            continue
        if ch in _EXTGLOB_PREFIXES and i + 1 < len(pattern) and pattern[i + 1] == '(':
            return True
        i += 1
    return False


def _find_matching_paren(pattern: str, open_pos: int) -> Optional[int]:
    """Find the closing ')' that matches the '(' at open_pos.

    Handles nested parentheses (including nested extglob).
    Returns the index of the closing ')' or None if unbalanced.
    """
    depth = 1
    i = open_pos + 1
    while i < len(pattern):
        ch = pattern[i]
        if ch == '\\' and i + 1 < len(pattern):
            i += 2
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _split_pattern_list(inner: str) -> List[str]:
    """Split an extglob inner pattern on '|' respecting nested parens."""
    parts = []
    current = []
    depth = 0
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == '\\' and i + 1 < len(inner):
            current.append(ch)
            current.append(inner[i + 1])
            i += 2
            continue
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == '|' and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    parts.append(''.join(current))
    return parts


def extglob_to_regex(pattern: str, anchored: bool = True,
                     from_start: bool = True,
                     for_pathname: bool = False) -> str:
    """Convert a shell pattern (with extglob operators) to a Python regex.

    Args:
        pattern: Shell pattern potentially containing extglob operators.
        anchored: If True, anchor the regex (^ and/or $).
        from_start: If anchored, anchor at start (True) or just at end (False).
        for_pathname: If True, * and ? do not match '/'.
    """
    regex = _convert_pattern(pattern, for_pathname)

    if anchored:
        if from_start:
            regex = '^' + regex + '$'
        else:
            regex = regex + '$'
    return regex


def glob_to_regex_body(pattern: str, for_pathname: bool = False,
                       extglob: bool = True) -> str:
    """Convert a shell glob pattern to an *unanchored* regex body.

    The public entry point for the shared glob→regex conversion. Callers that
    need anchoring add ``^``/``$`` themselves (see ``extglob_to_regex`` and
    ``PatternMatcher.shell_pattern_to_regex``).
    """
    return _convert_pattern(pattern, for_pathname, extglob)


def _convert_pattern(pattern: str, for_pathname: bool, extglob: bool = True) -> str:
    """Recursively convert a shell pattern to regex.

    Args:
        pattern: Shell pattern.
        for_pathname: If True, ``*`` and ``?`` do not match ``/``.
        extglob: If True, interpret ``?(``/``*(``/``+(``/``@(``/``!(`` as extglob
            operators. Set False for plain-glob conversion (e.g. parameter
            expansion when extglob is off), where those prefixes are literal.

    This is the single source of truth for shell-glob → regex conversion,
    shared by extglob matching and parameter-expansion pattern operators.
    """
    result = []
    i = 0
    dot = '[^/]' if for_pathname else '.'
    star = '[^/]*' if for_pathname else '.*'

    while i < len(pattern):
        ch = pattern[i]

        # Backslash escape
        if ch == '\\' and i + 1 < len(pattern):
            result.append(re.escape(pattern[i + 1]))
            i += 2
            continue

        # Extglob operator
        if extglob and ch in _EXTGLOB_PREFIXES and i + 1 < len(pattern) and pattern[i + 1] == '(':
            close = _find_matching_paren(pattern, i + 1)
            if close is not None:
                inner = pattern[i + 2:close]
                alternatives = _split_pattern_list(inner)
                # Recursively convert each alternative
                alt_regexes = [_convert_pattern(alt, for_pathname, extglob) for alt in alternatives]
                alt_group = '|'.join(alt_regexes)

                if ch == '?':
                    result.append(f'(?:{alt_group})?')
                elif ch == '*':
                    result.append(f'(?:{alt_group})*')
                elif ch == '+':
                    result.append(f'(?:{alt_group})+')
                elif ch == '@':
                    result.append(f'(?:{alt_group})')
                elif ch == '!':
                    # Inline negation via per-character negative lookahead
                    result.append(f'(?:(?!(?:{alt_group}){star}).)*')

                i = close + 1
                continue
            # Unbalanced paren: treat prefix char literally
            result.append(re.escape(ch))
            i += 1
            continue

        # Standard glob characters
        if ch == '*':
            result.append(star)
        elif ch == '?':
            result.append(dot)
        elif ch == '[':
            # Bracket expression: find the closing ']', skipping over
            # POSIX class names like [:alpha:] whose ']' does not close
            # the set ([[:alpha:]] is ONE bracket expression).
            j = i + 1
            if j < len(pattern) and pattern[j] in ('!', '^'):
                j += 1
            if j < len(pattern) and pattern[j] == ']':
                j += 1  # ] right after [ or [! is literal
            while j < len(pattern) and pattern[j] != ']':
                if pattern.startswith('[:', j):
                    close = pattern.find(':]', j + 2)
                    if close != -1:
                        j = close + 2
                        continue
                j += 1
            if j < len(pattern):
                class_content = pattern[i + 1:j]
                # Translate POSIX classes to Python-re ranges
                # ([[:digit:]] -> [0-9]); re has no [:name:] syntax.
                from .glob import _POSIX_CLASS_RE, _POSIX_CLASSES
                class_content = _POSIX_CLASS_RE.sub(
                    lambda m: _POSIX_CLASSES.get(m.group(1), m.group(0)),
                    class_content)
                if class_content.startswith('!'):
                    result.append(f'[^{class_content[1:]}]')
                elif class_content.startswith('^'):
                    result.append(f'[^{class_content[1:]}]')
                else:
                    result.append(f'[{class_content}]')
                i = j + 1
                continue
            else:
                result.append(re.escape('['))
        else:
            result.append(re.escape(ch))

        i += 1

    return ''.join(result)


def match_extglob(pattern: str, string: str,
                  full_match: bool = True) -> bool:
    """Match a string against an extglob pattern.

    For standalone !(pattern) at top level, uses match-and-invert
    for reliability. For other patterns, converts to regex.

    Args:
        pattern: Shell pattern with extglob operators.
        string: The string to match.
        full_match: If True, pattern must match the entire string.
    """
    # Optimisation: standalone !(alt1|alt2) at top level
    # Use match-and-invert for correctness
    if _is_standalone_negation(pattern):
        inner = pattern[2:-1]
        # Convert !(alt) to @(alt) and invert
        positive_pattern = '@(' + inner + ')'
        return not match_extglob(positive_pattern, string, full_match)

    regex_str = extglob_to_regex(pattern, anchored=full_match,
                                 from_start=True)
    try:
        return bool(re.fullmatch(regex_str, string) if full_match
                     else re.search(regex_str, string))
    except re.error:
        return False


def _is_standalone_negation(pattern: str) -> bool:
    """Check if pattern is exactly !(alternatives) with nothing outside."""
    if not pattern.startswith('!('):
        return False
    close = _find_matching_paren(pattern, 1)
    return close is not None and close == len(pattern) - 1


def expand_extglob(pattern: str, directory: str = '.',
                   dotglob: bool = False) -> List[str]:
    """Expand an extglob pattern against directory entries.

    Args:
        pattern: The extglob pattern (single path component).
        directory: Directory to list entries from.
        dotglob: If True, match dotfiles.

    Returns:
        Sorted list of matching filenames, or empty list if no matches.
    """
    try:
        entries = os.listdir(directory)
    except OSError:
        return []

    regex_str = extglob_to_regex(pattern, anchored=True,
                                 from_start=True, for_pathname=False)
    try:
        compiled = re.compile(regex_str)
    except re.error:
        return []

    matches = []
    for entry in entries:
        if not dotglob and entry.startswith('.'):
            # Only match dotfiles if the pattern explicitly starts with '.'
            if not pattern.startswith('.'):
                continue
        if compiled.fullmatch(entry):
            matches.append(entry)

    return sorted(matches)
