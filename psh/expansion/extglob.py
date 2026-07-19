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
import warnings
from functools import lru_cache
from typing import List, Optional

from ..core.locale_service import active_locale, posix_class_ranges

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
        anchored: If True, anchor the regex (``^`` and/or ``\\Z``).
        from_start: If anchored, anchor at start (True) or just at end (False).
        for_pathname: If True, * and ? do not match '/'.
        ic: If True (``nocasematch``), keep ``[:upper:]``/``[:lower:]``
            case-sensitive; the caller still applies ``re.IGNORECASE``.

    The body is wrapped in ``(?s:...)`` (DOTALL) so the ``.``/``.*`` emitted
    for ``?``/``*`` match a newline the way a real shell glob does (bash's
    ``?``/``*`` match ``\\n``). The end anchor is ``\\Z`` (true end of string),
    NOT ``$`` — ``$`` also matches just before a trailing newline, which would
    over-match a subject like ``$'ab\\n'`` (``${x%b}`` must NOT strip).
    """
    regex = '(?s:' + _convert_pattern(pattern, for_pathname,
                                      top_level=True, ic=ic) + ')'

    if anchored:
        if from_start:
            regex = '^' + regex + r'\Z'
        else:
            regex = regex + r'\Z'
    return regex


def glob_to_regex_body(pattern: str, for_pathname: bool = False,
                       extglob: bool = True, ic: bool = False) -> str:
    """Convert a shell glob pattern to an *unanchored* regex body.

    The public entry point for the shared glob→regex conversion. Callers that
    need anchoring add ``^``/``\\Z`` themselves (see ``extglob_to_regex`` and
    ``PatternMatcher.shell_pattern_to_regex``). ``ic`` (``nocasematch``) keeps
    ``[:upper:]``/``[:lower:]`` case-sensitive; see ``_bracket_to_regex``.

    The body is wrapped in ``(?s:...)`` (DOTALL) so the ``.``/``.*`` emitted
    for ``?``/``*`` match a newline like a real shell glob. The wrapper is
    scoped, not a compile flag, precisely because this string is embedded in
    larger regexes by callers (anchoring, prefix/suffix normalisation).
    """
    return ('(?s:'
            + _convert_pattern(pattern, for_pathname, extglob,
                               top_level=True, ic=ic)
            + ')')


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
                        result.append(f'(?!(?:{alt_group})\\Z){star}')
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
    # Cache the conversion, keyed additionally on the active locale's ctype
    # identity: the POSIX [:class:] ranges spliced in below (posix_class_ranges)
    # are locale-dependent, so a mid-session LC_CTYPE change must never serve a
    # stale conversion. Within one pattern match (content, ic) is constant
    # across subject positions, so this collapses the per-position rebuild the
    # memoized engine would otherwise pay in _bracket_match to one compile.
    loc = active_locale()
    ctype = loc.profile.ctype_name if loc is not None else None
    return _bracket_to_regex_cached(content, ic, ctype)


@lru_cache(maxsize=1024)
def _bracket_to_regex_cached(content: str, ic: bool, _ctype: Optional[str]) -> str:
    """Locale-keyed cache body of ``_bracket_to_regex`` (see it for semantics).

    ``_ctype`` is the active locale's ctype identity so a mid-session
    ``LC_CTYPE`` change cannot serve a stale POSIX-class conversion.
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
    # POSIX [:class:] names resolve through the locale service: the fixed ASCII
    # range table in the C/POSIX locale (byte-identical to psh's historical
    # behaviour) and the host libc's iswctype membership (swept to explicit
    # codepoint ranges) in a UTF-8 locale, so `[[:alpha:]]` matches é there just
    # as bash does. Changing this ONE chokepoint fixes case / [[ == ]] /
    # ${x#pat} / pathname matching together (the v0.638 unified converter).
    from .glob import _POSIX_CLASS_RE

    def _sub(m: 're.Match[str]') -> str:
        r = posix_class_ranges(m.group(1))
        return r if r is not None else m.group(0)  # unknown name: keep literal

    body = ''.join(out)

    if not ic:
        translated = _POSIX_CLASS_RE.sub(_sub, body)
        regex = f'[{negate}{translated}]'
    else:
        # Case-insensitive: protect [:upper:]/[:lower:] from the ambient
        # IGNORECASE flag while letting everything else fold normally.
        has_upper = '[:upper:]' in body
        has_lower = '[:lower:]' in body
        rest = body.replace('[:upper:]', '').replace('[:lower:]', '')
        rest = _POSIX_CLASS_RE.sub(_sub, rest)
        alts = []
        if has_upper:
            alts.append(f'(?-i:[{posix_class_ranges("upper")}])')
        if has_lower:
            alts.append(f'(?-i:[{posix_class_ranges("lower")}])')
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
        with warnings.catch_warnings():
            # A bracket may hold a regex set-operator sequence (``&&``/``||``/
            # ``~~``/``--``); ``re`` raises a FutureWarning for those. bash
            # matches them as literal members, so validate silently — the old
            # stdlib ``fnmatch`` pathname path escaped them and never warned.
            warnings.simplefilter('ignore')
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

    A set-operator sequence (``&&``/``||``/``~~``) inside the class raises a
    ``re`` FutureWarning; bash matches such characters literally, so the match
    is done silently (the old ``fnmatch`` pathname path never warned).
    """
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return re.match(_bracket_to_regex(cls, ic), ch,
                        re.IGNORECASE if ic else 0) is not None


def _eq(a: str, b: str, ic: bool) -> bool:
    return a.casefold() == b.casefold() if ic else a == b


def _extglob_consume(pattern: str, s: str, for_pathname: bool = False,
                     ic: bool = False) -> set:
    """Set of lengths ``k`` such that *pattern* fully matches ``s[:k]``.

    ``k in result`` means a complete match of *pattern* consumes exactly the
    first ``k`` characters of *s*. Full-match is ``len(s) in result``;
    prefix/suffix/substitution operators are built from the reachable-length set
    (see ``parameter_expansion.py``).

    As of the compiled-pattern-engine work (expansion appraisal #6) this
    delegates to the memoized matcher (``pattern_engine``): the pattern is
    compiled once and each ``(node, position)`` state is evaluated at most once,
    so the ``?(a)…!(z)`` fan-out that made the former recursive ``_match_from``
    exponential is now polynomial. The reachable-end-set contract is unchanged —
    verified equal to the former matcher over ~24k random cases. The import is
    lazy to avoid a top-level cycle (``pattern_engine`` imports this module's
    scanning/char primitives)."""
    from .pattern_engine import compile_cached, reachable_ends
    return set(reachable_ends(compile_cached(pattern), s,
                              for_pathname=for_pathname, ic=ic))


def extglob_fullmatch(pattern: str, string: str, for_pathname: bool = False,
                      ignorecase: bool = False) -> bool:
    """Whether *pattern* (which may contain negation) fully matches *string*."""
    from .pattern_engine import compile_cached, fullmatch
    return fullmatch(compile_cached(pattern), string,
                     for_pathname=for_pathname, ic=ignorecase)


def extglob_match_at(pattern: str, string: str, pos: int,
                     for_pathname: bool = False,
                     ignorecase: bool = False) -> Optional[int]:
    """Leftmost-longest match LENGTH of *pattern* at ``string[pos:]``, or None.

    Used by the substitution operators (``${v/pat/r}``) to find a match extent
    at a given position; bash uses the longest match at the leftmost position.
    """
    from .pattern_engine import compile_cached, match_at
    return match_at(compile_cached(pattern), string, pos,
                    for_pathname=for_pathname, ic=ignorecase)


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

    # Match each entry through the compiled memoized engine (expansion #6): the
    # pattern is compiled once (cached) and every entry is a bounded full match,
    # so an ambiguous-repetition component like ``*(a|aa)c`` can no longer cause
    # the catastrophic regex backtracking the former non-negation path had.
    # Negation was already engine-only (a regex cannot express it).
    def _matches(entry: str) -> bool:
        return extglob_fullmatch(pattern, entry)

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
    loc = active_locale()
    return sorted(matches, key=loc.collate_key) if loc else sorted(matches)
