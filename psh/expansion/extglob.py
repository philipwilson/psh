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
                     for_pathname: bool = False,
                     ic: bool = False) -> str:
    """Convert a shell pattern (with extglob operators) to a Python regex.

    Args:
        pattern: Shell pattern potentially containing extglob operators.
        anchored: If True, anchor the regex (^ and/or $).
        from_start: If anchored, anchor at start (True) or just at end (False).
        for_pathname: If True, * and ? do not match '/'.
        ic: If True (``nocasematch``), keep ``[:upper:]``/``[:lower:]``
            case-sensitive; the caller still applies ``re.IGNORECASE``.
    """
    regex = _convert_pattern(pattern, for_pathname, top_level=True, ic=ic)

    if anchored:
        if from_start:
            regex = '^' + regex + '$'
        else:
            regex = regex + '$'
    return regex


def glob_to_regex_body(pattern: str, for_pathname: bool = False,
                       extglob: bool = True, ic: bool = False) -> str:
    """Convert a shell glob pattern to an *unanchored* regex body.

    The public entry point for the shared glob→regex conversion. Callers that
    need anchoring add ``^``/``$`` themselves (see ``extglob_to_regex`` and
    ``PatternMatcher.shell_pattern_to_regex``). ``ic`` (``nocasematch``) keeps
    ``[:upper:]``/``[:lower:]`` case-sensitive; see ``_bracket_to_regex``.
    """
    return _convert_pattern(pattern, for_pathname, extglob, top_level=True,
                            ic=ic)


def _convert_pattern(pattern: str, for_pathname: bool, extglob: bool = True,
                     top_level: bool = False, ic: bool = False) -> str:
    """Recursively convert a shell pattern to regex.

    Args:
        pattern: Shell pattern.
        for_pathname: If True, ``*`` and ``?`` do not match ``/``.
        extglob: If True, interpret ``?(``/``*(``/``+(``/``@(``/``!(`` as extglob
            operators. Set False for plain-glob conversion (e.g. parameter
            expansion when extglob is off), where those prefixes are literal.
        ic: If True (``nocasematch``), bracket expressions keep
            ``[:upper:]``/``[:lower:]`` case-sensitive (see
            ``_bracket_to_regex``); the caller applies ``re.IGNORECASE``.

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
                alt_regexes = [_convert_pattern(alt, for_pathname, extglob, ic=ic) for alt in alternatives]
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
            # Bracket expression: _bracket_end (shared with the backtracking
            # matcher) finds the closing ']' — skipping POSIX class names
            # like [:alpha:] and escaped members like \] — and
            # _bracket_to_regex translates the content for Python's re.
            end = _bracket_end(pattern, i)
            if end is not None:
                result.append(_bracket_to_regex(pattern[i + 1:end - 1], ic))
                i = end
                continue
            result.append(re.escape('['))  # unterminated: '[' is literal
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
    ``]`` (POSIX ``[:class:]`` aware; a backslash-escaped ``\\]`` is a
    member, not the terminator), or None if unterminated."""
    j = i + 1
    if j < len(pattern) and pattern[j] in ('!', '^'):
        j += 1
    if j < len(pattern) and pattern[j] == ']':
        j += 1  # a ']' right after '[' or '[!' is a literal member
    while j < len(pattern) and pattern[j] != ']':
        if pattern[j] == '\\' and j + 1 < len(pattern):
            j += 2
            continue
        if pattern.startswith('[:', j):
            close = pattern.find(':]', j + 2)
            if close != -1:
                j = close + 2
                continue
        j += 1
    return j + 1 if j < len(pattern) else None


def _bracket_to_regex(content: str, ic: bool = False) -> str:
    """Convert raw bracket-expression CONTENT (the text between ``[`` and
    ``]``) to a Python-re character class.

    Handles negation (``!`` or ``^``), backslash-escaped members
    (``[a\\]b]`` is the three-member set a ] b — bash honors ``\\`` inside a
    set, Python's re needs ``\\x`` rewritten to a valid escape), a literal
    ``]`` first member, and POSIX ``[:name:]`` classes (re has no
    ``[:name:]`` syntax). A set that cannot compile (e.g. the reversed
    range ``[z-a]``) yields a valid substitute matching what bash matches:
    nothing — or, negated (``[!z-a]``), any one character. The returned
    class always compiles, so an invalid set inside a larger pattern
    can never crash it.

    ``ic`` (the ``nocasematch`` shopt) is subtle. bash's case-insensitive
    matching folds literals, ranges (``[A-Z]``), sets (``[abc]``) and most
    classes, but it leaves the ``[:upper:]`` / ``[:lower:]`` classes
    case-SENSITIVE — they keep meaning "an actually-uppercase/lowercase
    character" (verified against bash 5.2: ``shopt -s nocasematch;
    ${v//[[:upper:]]/x}`` on ``Hello`` -> ``xello``, only the ``H``). The
    caller applies the ``re.IGNORECASE`` flag, which would wrongly fold the
    ``A-Z`` this function substitutes for ``[:upper:]``. So when ``ic`` is
    set we emit ``[:upper:]`` / ``[:lower:]`` inside a ``(?-i:...)`` scoped
    group (immune to the ambient flag) and combine it with the rest of the
    bracket — which still folds — by alternation (or a negative-lookahead
    atom when the bracket is negated).
    """
    negate = ''
    if content[:1] in ('!', '^'):
        negate = '^'
        content = content[1:]
    out = []
    i = 0
    while i < len(content):
        ch = content[i]
        if ch == '\\' and i + 1 < len(content):
            out.append(re.escape(content[i + 1]))
            i += 2
            continue
        if content.startswith('[:', i):
            close = content.find(':]', i + 2)
            if close != -1:
                out.append(content[i:close + 2])
                i = close + 2
                continue
        if ch == ']' and i == 0:
            out.append('\\]')  # leading ']' is a literal member
            i += 1
            continue
        out.append(ch)
        i += 1
    from .glob import _POSIX_CLASS_RE, _POSIX_CLASSES
    body = ''.join(out)

    if not ic:
        translated = _POSIX_CLASS_RE.sub(
            lambda m: _POSIX_CLASSES.get(m.group(1), m.group(0)), body)
        regex = f'[{negate}{translated}]'
    else:
        # Case-insensitive: protect [:upper:]/[:lower:] from the ambient
        # IGNORECASE flag while letting everything else fold normally.
        has_upper = '[:upper:]' in body
        has_lower = '[:lower:]' in body
        rest = body.replace('[:upper:]', '').replace('[:lower:]', '')
        rest = _POSIX_CLASS_RE.sub(
            lambda m: _POSIX_CLASSES.get(m.group(1), m.group(0)), rest)
        alts = []
        if has_upper:
            alts.append('(?-i:[A-Z])')
        if has_lower:
            alts.append('(?-i:[a-z])')
        if rest:
            alts.append(f'[{rest}]')  # folds under the caller's IGNORECASE
        group = '|'.join(alts)
        if not alts:
            regex = r'[^\s\S]'  # empty bracket: matches nothing
        elif negate:
            # One char that is NONE of the alternatives (matches newline too,
            # like a real negated class, so use [\s\S] not '.').
            regex = rf'(?:(?!(?:{group}))[\s\S])'
        elif len(alts) > 1:
            regex = f'(?:{group})'
        else:
            regex = group

    try:
        re.compile(regex)
    except re.error:
        # bash (verified 5.2): an invalid set matches nothing; a NEGATED
        # invalid set matches any one character.
        return r'[\s\S]' if negate else r'[^\s\S]'
    return regex


def _bracket_match(cls: str, ch: str, ic: bool) -> bool:
    """Whether single char *ch* is in bracket-class content *cls* (no ``[]``).

    ``_bracket_to_regex`` guarantees a compilable class (an invalid set
    becomes its bash-verified match-nothing / match-any substitute), so no
    ``re.error`` guard is needed here. ``ic`` is threaded through so
    ``[:upper:]`` / ``[:lower:]`` stay case-sensitive under ``nocasematch``.
    """
    return re.match(_bracket_to_regex(cls, ic), ch,
                    re.IGNORECASE if ic else 0) is not None


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

    # Order per-directory entries in the active collation (the final glob-level
    # sort re-orders across directories; this keeps single-component extglob
    # results collation-ordered too). Module-level function, so reach the
    # process-active locale rather than a shell handle; codepoint order if none.
    from ..core.locale_service import active_locale
    loc = active_locale()
    return sorted(matches, key=loc.collate_key) if loc else sorted(matches)
