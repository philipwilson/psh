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
    regex = _convert_pattern(pattern, for_pathname, top_level=True)

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
    return _convert_pattern(pattern, for_pathname, extglob, top_level=True)


def _convert_pattern(pattern: str, for_pathname: bool, extglob: bool = True,
                     top_level: bool = False) -> str:
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
                    # Standalone !(P) (the negation spans the WHOLE pattern):
                    # bash matches any string that is not P in its entirety,
                    # so emit a whole-string negative lookahead then consume
                    # everything (e.g. !(foo) matches foobar, foofoo, "" but
                    # not foo). The per-character inline form below wrongly
                    # rejects any string that merely STARTS with an
                    # alternative.
                    if top_level and i == 0 and close == len(pattern) - 1:
                        result.append(f'(?!(?:{alt_group})$){star}')
                    else:
                        # Embedded negation (a!(b)c, !(b)c, !(b)*) is NOT
                        # expressible as a Python regex — the negation is a
                        # property of the whole consumed span, needing a
                        # variable-width lookbehind `re` lacks. Every MATCHING
                        # path routes such patterns to the backtracking matcher
                        # (`_extglob_consume` / `extglob_fullmatch`) instead, so
                        # this per-character lookahead is a lossy last resort
                        # only reached if a caller builds a regex directly; it
                        # over-rejects spans that merely contain an alternative.
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

    Negation (``!(...)``, standalone or embedded) goes through the
    backtracking matcher; everything else converts to a regex.

    Args:
        pattern: Shell pattern with extglob operators.
        string: The string to match.
        full_match: If True, pattern must match the entire string.
    """
    # Negation (standalone OR embedded) is not expressible as a Python regex
    # (see _extglob_consume); use the backtracking matcher.
    if _contains_negation(pattern):
        if full_match:
            return extglob_fullmatch(pattern, string)
        return any(extglob_match_at(pattern, string, pos) is not None
                   for pos in range(len(string) + 1))

    regex_str = extglob_to_regex(pattern, anchored=full_match,
                                 from_start=True)
    try:
        return bool(re.fullmatch(regex_str, string) if full_match
                     else re.search(regex_str, string))
    except re.error:
        return False


# ---------------------------------------------------------------------------
# Recursive matcher for negation patterns
#
# Python's ``re`` cannot express embedded extglob negation ``a!(P)b``: the
# negation is a property of the WHOLE consumed span ("the span is not P"),
# which needs a variable-width lookbehind ``re`` does not support — the inline
# per-character lookahead in ``_convert_pattern`` over-rejects any span that
# merely CONTAINS a character starting an alternative (appraisal H5). So when a
# pattern contains a ``!(...)`` group we match with this small backtracking
# matcher instead of a regex. Non-negation patterns keep the fast regex path.
# ---------------------------------------------------------------------------

def _contains_negation(pattern: str) -> bool:
    """True if *pattern* contains a ``!(...)`` extglob group (at any depth)."""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == '\\' and i + 1 < len(pattern):
            i += 2
            continue
        if (ch == '!' and i + 1 < len(pattern) and pattern[i + 1] == '('
                and _find_matching_paren(pattern, i + 1) is not None):
            return True
        i += 1
    return False


def _bracket_end(pattern: str, i: int) -> Optional[int]:
    """Given ``pattern[i] == '['``, return the index just past the matching
    ``]`` (POSIX ``[:class:]`` aware), or None if unterminated."""
    j = i + 1
    if j < len(pattern) and pattern[j] in ('!', '^'):
        j += 1
    if j < len(pattern) and pattern[j] == ']':
        j += 1  # a ']' right after '[' / '[!' is a literal member
    while j < len(pattern) and pattern[j] != ']':
        if pattern.startswith('[:', j):
            close = pattern.find(':]', j + 2)
            if close != -1:
                j = close + 2
                continue
        j += 1
    return j + 1 if j < len(pattern) else None


def _bracket_match(cls: str, ch: str, ic: bool) -> bool:
    """Whether single char *ch* is in bracket-class content *cls* (no ``[]``)."""
    neg = False
    if cls[:1] in ('!', '^'):
        neg = True
        cls = cls[1:]
    from .glob import _POSIX_CLASS_RE, _POSIX_CLASSES
    body = _POSIX_CLASS_RE.sub(
        lambda m: _POSIX_CLASSES.get(m.group(1), m.group(0)), cls)
    try:
        matched = re.match(f'[{body}]', ch, re.IGNORECASE if ic else 0) is not None
    except re.error:
        matched = ch in cls
    return (not matched) if neg else matched


def _eq(a: str, b: str, ic: bool) -> bool:
    return a.casefold() == b.casefold() if ic else a == b


def _extglob_consume(pattern: str, s: str, for_pathname: bool = False,
                     ic: bool = False) -> set:
    """Set of lengths ``k`` such that *pattern* fully matches ``s[:k]``.

    The core backtracking primitive. ``k in result`` means a complete match of
    *pattern* consumes exactly the first ``k`` characters of *s*. Full-match is
    ``len(s) in result``; prefix/suffix/substitution operators are built from
    the reachable-length set (see ``parameter_expansion.py``).
    """
    return _match_from(pattern, 0, s, 0, for_pathname, ic)


def _match_from(pat: str, pi: int, s: str, si: int, fp: bool, ic: bool) -> set:
    """Reachable end indices in *s* matching ``pat[pi:]`` from ``s[si]``."""
    if pi == len(pat):
        return {si}
    ch = pat[pi]

    if ch == '\\' and pi + 1 < len(pat):
        if si < len(s) and _eq(s[si], pat[pi + 1], ic):
            return _match_from(pat, pi + 2, s, si + 1, fp, ic)
        return set()

    if ch in _EXTGLOB_PREFIXES and pi + 1 < len(pat) and pat[pi + 1] == '(':
        close = _find_matching_paren(pat, pi + 1)
        if close is not None:
            alts = _split_pattern_list(pat[pi + 2:close])
            out: set = set()
            for end in _element_ends(ch, alts, s, si, fp, ic):
                out |= _match_from(pat, close + 1, s, end, fp, ic)
            return out
        # Unbalanced: treat the prefix char as a literal.
        if si < len(s) and _eq(s[si], ch, ic):
            return _match_from(pat, pi + 1, s, si + 1, fp, ic)
        return set()

    if ch == '?':
        if si < len(s) and (not fp or s[si] != '/'):
            return _match_from(pat, pi + 1, s, si + 1, fp, ic)
        return set()

    if ch == '*':
        out = set()
        end = si
        while True:
            out |= _match_from(pat, pi + 1, s, end, fp, ic)
            if end >= len(s) or (fp and s[end] == '/'):
                break
            end += 1
        return out

    if ch == '[':
        be = _bracket_end(pat, pi)
        if be is not None:
            cls = pat[pi + 1:be - 1]
            if (si < len(s) and (not fp or s[si] != '/')
                    and _bracket_match(cls, s[si], ic)):
                return _match_from(pat, be, s, si + 1, fp, ic)
            return set()
        if si < len(s) and s[si] == '[':
            return _match_from(pat, pi + 1, s, si + 1, fp, ic)
        return set()

    if si < len(s) and _eq(s[si], ch, ic):
        return _match_from(pat, pi + 1, s, si + 1, fp, ic)
    return set()


def _alt_ends(alts: List[str], s: str, si: int, fp: bool, ic: bool) -> set:
    """End indices where some alternative fully matches starting at ``s[si]``."""
    out: set = set()
    for alt in alts:
        out |= _match_from(alt, 0, s, si, fp, ic)
    return out


def _element_ends(op: str, alts: List[str], s: str, si: int, fp: bool,
                  ic: bool) -> set:
    """End indices after matching ONE extglob element ``op(alts)`` from ``si``."""
    if op == '@':
        return _alt_ends(alts, s, si, fp, ic)
    if op == '?':
        return {si} | _alt_ends(alts, s, si, fp, ic)
    if op == '+':
        return _alt_closure(alts, s, _alt_ends(alts, s, si, fp, ic), fp, ic)
    if op == '*':
        return _alt_closure(alts, s, {si}, fp, ic)
    if op == '!':
        # Anything except a full match of one alternative: every span s[si:e]
        # that does NOT itself fully match the alternatives. THIS is the case
        # a regex cannot express.
        positive = _alt_ends(alts, s, si, fp, ic)
        out = set()
        for end in range(si, len(s) + 1):
            if fp and '/' in s[si:end]:
                break
            if end not in positive:
                out.add(end)
        return out
    return set()


def _alt_closure(alts: List[str], s: str, start: set, fp: bool, ic: bool) -> set:
    """Zero-or-more closure of matching ``alts`` (for ``*(...)``/``+(...)``)."""
    seen = set(start)
    frontier = set(start)
    while frontier:
        nxt = set()
        for p in frontier:
            for end in _alt_ends(alts, s, p, fp, ic):
                if end not in seen and end != p:  # skip empty matches (no loop)
                    seen.add(end)
                    nxt.add(end)
        frontier = nxt
    return seen


def extglob_fullmatch(pattern: str, string: str, for_pathname: bool = False,
                      ignorecase: bool = False) -> bool:
    """Whether *pattern* (which may contain negation) fully matches *string*."""
    return len(string) in _extglob_consume(pattern, string, for_pathname,
                                            ignorecase)


def extglob_match_at(pattern: str, string: str, pos: int,
                     for_pathname: bool = False,
                     ignorecase: bool = False) -> Optional[int]:
    """Leftmost-longest match LENGTH of *pattern* at ``string[pos:]``, or None.

    Used by the substitution operators (``${v/pat/r}``) to find a match extent
    at a given position; bash uses the longest match at the leftmost position.
    """
    ends = _extglob_consume(pattern, string[pos:], for_pathname, ignorecase)
    return max(ends) if ends else None


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

    # Negation patterns can't be a regex (see _extglob_consume); match per
    # entry with the backtracking matcher. Other patterns use the fast regex.
    if _contains_negation(pattern):
        def _matches(entry: str) -> bool:
            return extglob_fullmatch(pattern, entry)
    else:
        regex_str = extglob_to_regex(pattern, anchored=True,
                                     from_start=True, for_pathname=False)
        try:
            compiled = re.compile(regex_str)
        except re.error:
            return []

        def _matches(entry: str) -> bool:
            return compiled.fullmatch(entry) is not None

    matches = []
    for entry in entries:
        if not dotglob and entry.startswith('.'):
            # Only match dotfiles if the pattern explicitly starts with '.'
            if not pattern.startswith('.'):
                continue
        if _matches(entry):
            matches.append(entry)

    return sorted(matches)
