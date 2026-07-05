"""Convergence pin for the single glob→regex converter (appraisal #18 elegance).

Pathname expansion's per-component matching (the nocaseglob / extglob /
globstar walkers) now routes through the SAME converter used by ``case`` /
``[[ == ]]`` / parameter expansion (``extglob.glob_to_regex_body``), via the
pathname adapter ``glob._compile_component`` — replacing the old stdlib
``fnmatch.translate`` + ``normalize_bracket_expressions`` path.

These tests pin that the adapter reproduces, byte-for-byte, what the previous
``fnmatch``-based path matched (so the reroute is a zero-behavior-change
refactor), and exercise the tricky bracket / class / negation / escape cases
directly.
"""

import fnmatch
import re
import warnings

import pytest

from psh.expansion.glob import _compile_component, normalize_bracket_expressions


def _fnmatch_reference(comp, ignorecase):
    """The pre-refactor pathname matcher: ``fnmatch.translate`` applied to the
    ``normalize_bracket_expressions``-adapted component. This is exactly what
    ``_glob_nocase`` / ``_match_glob_component`` used before the converter was
    unified, so ``_compile_component`` must agree with it on every input."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return re.compile(fnmatch.translate(normalize_bracket_expressions(comp)),
                          re.IGNORECASE if ignorecase else 0)


# Single path components (never contain '/'): plain wildcards, bracket sets,
# ranges, POSIX classes, [!..]/[^..] negation, leading ']', reversed range,
# unterminated bracket, backslash escapes, and regex set-operator sequences.
_PATTERNS = [
    '*', '?', 'a*', '*b', 'a*b', 'a?b', 'ab*cd', '?*', '*?',
    '[abc]', '[a-z]', '[A-Z]', '[!a-z]', '[^a-z]', '[!abc]', '[a-c1-3]',
    '[!a-c1-3]', '[[:alpha:]]', '[[:digit:]]', '[[:upper:]]', '[[:lower:]]',
    '[[:alnum:]]', '[[:punct:]]', '[[:space:]]', '[[:xdigit:]]', '[[:blank:]]',
    '[[:graph:]]', '[[:print:]]', 'a[[:alpha:]]b', '[[:alpha:][:digit:]]',
    '[![:alpha:]]', '[]]', '[!]]', '[]abc]', '[abc', '[', '[z-a]', '[a-]',
    '[-a]', '[.]', 'a[b', 'a]b', '[abc]*', '*[abc]', r'a\*b', r'a\]b',
    r'[a\]b]', r'\?', r'\*', r'\\', r'a\\b', '*[a&&b]*', '*[a||b]*',
    '*.txt', 'file*.txt', 'a[bxX]b', 'a[!x]b', 'a[^x]b',
]

_STRINGS = [
    '', 'a', 'A', 'ab', 'aB', 'abc', 'a]b', 'a*b', 'a-b', 'a^b', 'a!b',
    'a1b', 'a2b', '.a', 'a.b', 'aXb', 'a b', 'a\\b', 'file.txt', 'FILE.TXT',
    '[', ']', 'x]', '!', '1', '9', 'z', 'Z', 'café', 'ab]', '[abc', '..',
    'a&b', 'a|b', 'axxb', 'aXbXc',
]


@pytest.mark.parametrize('ignorecase', [False, True])
@pytest.mark.parametrize('comp', _PATTERNS)
def test_component_matches_fnmatch_reference(comp, ignorecase):
    """_compile_component must match exactly what the old fnmatch path matched."""
    ref = _fnmatch_reference(comp, ignorecase)
    got = _compile_component(comp, ignorecase=ignorecase)
    for s in _STRINGS:
        assert (got.fullmatch(s) is not None) == (ref.fullmatch(s) is not None), (
            f"divergence: pattern={comp!r} string={s!r} ignorecase={ignorecase}")


def test_backslash_is_literal_not_escape():
    """In the pathname adapter a residual backslash is a LITERAL character (as
    stdlib glob/fnmatch treat it), NOT an escape — this preserves the
    deliberate divergence from the case/[[ path (which honors ``\\`` escapes)."""
    rx = _compile_component(r'a\*b')
    assert rx.fullmatch('a\\b') is not None      # backslash + '*' matches 'a\\b'
    assert rx.fullmatch('a*b') is None           # NOT treated as escaped '*'


def test_set_operator_bracket_no_warning():
    """A bracket containing a regex set-operator sequence (&&, ||) must compile
    without leaking a FutureWarning to the caller (the old fnmatch path escaped
    them and never warned)."""
    with warnings.catch_warnings():
        warnings.simplefilter('error')  # any warning becomes an exception
        rx = _compile_component('*[a&&b]*')
    # '&' is matched as a literal set member, exactly as before.
    assert rx.fullmatch('xax') is not None
    assert rx.fullmatch('x&x') is not None
    assert rx.fullmatch('xzx') is None


def test_uncompilable_pattern_matches_nothing():
    """An adapter that somehow produced an uncompilable regex must degrade to
    'match nothing' (bash behavior), never raise."""
    # A well-formed but pathological input still yields a usable matcher.
    rx = _compile_component('[z-a]')  # reversed range: bash matches nothing
    assert rx.fullmatch('a') is None
    assert rx.fullmatch('z') is None
