"""Convergence pin for pathname per-component matching through the ONE engine.

Pathname expansion's per-component matching (the nocaseglob / extglob /
globstar walkers) routes through the SAME compiled pattern engine used by
``case`` / ``[[ == ]]`` / parameter expansion (``pattern_engine`` via the
pathname adapter ``glob._component_matcher``; campaign W3) — replacing the old
regex/``fnmatch`` per-name path.

These tests pin that the engine adapter reproduces, byte-for-byte, what the
previous ``fnmatch``-based path matched for the CASE-SENSITIVE profile and for
the case-INSENSITIVE profile on every pattern EXCEPT those holding
``[[:upper:]]`` / ``[[:lower:]]`` — where the engine correctly keeps those two
classes case-sensitive under ``nocaseglob`` (bash), a bug the old
``re.IGNORECASE`` path had (pinned separately below).
"""

import fnmatch
import re
import warnings

import pytest

from psh.expansion.glob import _component_matcher, normalize_bracket_expressions


def _fnmatch_reference(comp, ignorecase):
    """The pre-refactor pathname matcher: ``fnmatch.translate`` applied to the
    ``normalize_bracket_expressions``-adapted component."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        rx = re.compile(fnmatch.translate(normalize_bracket_expressions(comp)),
                        re.IGNORECASE if ignorecase else 0)
    return lambda s: rx.fullmatch(s) is not None


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

#: Patterns whose ignorecase behaviour is DELIBERATELY different from the old
#: fnmatch path: the engine keeps [[:upper:]]/[[:lower:]] case-sensitive under
#: nocaseglob (bash), rather than folding them via re.IGNORECASE.
_ICASE_DIVERGENT = {'[[:upper:]]', '[[:lower:]]'}


@pytest.mark.parametrize('ignorecase', [False, True])
@pytest.mark.parametrize('comp', _PATTERNS)
def test_component_matches_fnmatch_reference(comp, ignorecase):
    """The engine per-name matcher matches what the old fnmatch path matched,
    except for the two case-class patterns under ignorecase (pinned below)."""
    if ignorecase and comp in _ICASE_DIVERGENT:
        pytest.skip("engine keeps [[:upper:]]/[[:lower:]] case-sensitive (bug fix)")
    ref = _fnmatch_reference(comp, ignorecase)
    got = _component_matcher(comp, ignorecase=ignorecase)
    for s in _STRINGS:
        assert got(s) == ref(s), (
            f"divergence: pattern={comp!r} string={s!r} ignorecase={ignorecase}")


def test_nocaseglob_keeps_posix_case_classes_sensitive():
    """Under nocaseglob (ignorecase=True) the engine keeps [[:upper:]] /
    [[:lower:]] case-SENSITIVE — bash: `shopt -s nocaseglob; *[[:upper:]]*`
    matches only actually-uppercase names. The old re.IGNORECASE regex path
    wrongly folded them (matched lowercase too)."""
    up = _component_matcher('[[:upper:]]', ignorecase=True)
    assert up('A') is True
    assert up('a') is False       # NOT folded — the fix
    lo = _component_matcher('[[:lower:]]', ignorecase=True)
    assert lo('a') is True
    assert lo('A') is False
    # A plain literal/range under ignorecase still folds (bash nocaseglob).
    rng = _component_matcher('[a-c]', ignorecase=True)
    assert rng('B') is True


def test_backslash_is_literal_not_escape():
    """In the pathname adapter a residual backslash is a LITERAL character (as
    stdlib glob/fnmatch treat it), NOT an escape — this preserves the
    deliberate divergence from the case/[[ path (which honors ``\\`` escapes)."""
    m = _component_matcher(r'a\*b')
    assert m('a\\b') is True      # backslash + '*' matches 'a\\b'
    assert m('a*b') is False      # NOT treated as escaped '*'


def test_set_operator_bracket_no_warning():
    """A bracket containing a regex set-operator sequence (&&, ||) must match
    without leaking a FutureWarning to the caller (the old fnmatch path escaped
    them and never warned; the engine's one bracket compiler now suppresses)."""
    with warnings.catch_warnings():
        warnings.simplefilter('error')  # any warning becomes an exception
        m = _component_matcher('*[a&&b]*')
        # '&' is matched as a literal set member, exactly as before.
        assert m('xax') is True
        assert m('x&x') is True
        assert m('xzx') is False


def test_uncompilable_pattern_matches_nothing():
    """A pathological input (reversed range) degrades to 'match nothing' (bash
    behavior), never raises."""
    m = _component_matcher('[z-a]')  # reversed range: bash matches nothing
    assert m('a') is False
    assert m('z') is False
