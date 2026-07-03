"""Glob (pathname) expansion implementation."""
import fnmatch
import glob
import os
import re
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..shell import Shell


# POSIX character classes -> the character ranges to substitute *inside* an
# existing bracket expression. Each range is written so it embeds safely both
# in a Python ``re`` character class AND in stdlib ``fnmatch``: no leading
# ``!``/``^`` (fnmatch reads those as negation) and no bare ``]``/``\`` (which
# would close the class or escape). punct/graph/print/cntrl therefore appear as
# reordered ranges rather than literal metacharacter lists.
_POSIX_CLASSES = {
    'alpha': 'a-zA-Z',
    'digit': '0-9',
    'alnum': 'a-zA-Z0-9',
    'upper': 'A-Z',
    'lower': 'a-z',
    'xdigit': '0-9A-Fa-f',
    'blank': ' \t',
    'space': ' \t\n\r\x0b\x0c',
    # 0x21-0x2f, 0x3a-0x40, 0x5b-0x60, 0x7b-0x7e (': ' first so no leading '!').
    'punct': ':-@!-/[-`{-~',
    'graph': '"-~!',            # 0x21-0x7e ('!' moved to the end)
    'print': ' -~',             # 0x20-0x7e
    'cntrl': '\x00-\x1f\x7f',   # 0x00-0x1f and 0x7f (literal control bytes)
}

# The pathname (``glob.glob``) path splits patterns on ``/`` before matching, so
# a bracket range must not carry a literal ``/``. punct is the only class that
# spans ``/`` (0x2f): drop it there — no filename can contain ``/``, so the
# matched set is identical. Every other class is reused verbatim.
_POSIX_CLASSES_PATHNAME = {**_POSIX_CLASSES, 'punct': ':-@!-.[-`{-~'}

_POSIX_CLASS_RE = re.compile(r'\[:(\w+):\]')

#: The plain (non-extglob) pathname-expansion metacharacters. A word
#: containing any of these from an UNQUOTED, unescaped context is a glob
#: candidate. This is the single source of truth for that character set,
#: shared by ``GlobExpander`` and ``WordExpander``.
GLOB_METACHARS = frozenset('*?[')


def has_glob_metacharacters(s: str) -> bool:
    """True if *s* contains any plain glob metacharacter (``*``, ``?``, ``[``).

    This is the single predicate for "does this string look like a pathname
    pattern". It tests presence only — it does not validate bracket
    expressions, honor backslash escapes, or consider extglob (callers layer
    ``extglob.contains_extglob`` on top when ``shopt -s extglob`` is set, and
    are responsible for having already stripped/accounted-for quoting and
    escapes). Centralizing it keeps every detection site agreeing on the
    exact character set.
    """
    return any(c in GLOB_METACHARS for c in s)


def translate_posix_classes(pattern: str) -> str:
    """Replace POSIX ``[:class:]`` names with their equivalent character
    ranges, leaving everything else untouched.

    Shared with the ``[[ =~ ]]`` regex path (``enhanced_test_evaluator``): a
    bash ``=~`` operand is an ERE where ``[[:punct:]]`` is valid syntax, but
    Python's ``re`` has no ``[:class:]`` support and warns ``Possible nested
    set`` for the bare ``[[`` — so the same class table the glob engine uses
    is spliced in, and NO glob metacharacter handling is applied (``=~`` is a
    regex, not a glob). Unknown class names (not real POSIX classes) are left
    verbatim. A ``[:class:]`` that was ``re.escape``-d (a quoted operand part)
    is not matched here, so quoted text stays literal.
    """
    return _POSIX_CLASS_RE.sub(
        lambda m: _POSIX_CLASSES.get(m.group(1), m.group(0)), pattern
    )


def normalize_bracket_expressions(pattern: str) -> str:
    """Make shell bracket expressions understood by Python's fnmatch/glob.

    Translates POSIX character classes ``[[:alpha:]]`` to equivalent ranges and
    converts ``[^...]`` negation to fnmatch's ``[!...]`` form. Shared by
    pathname expansion and case/``[[ ]]`` pattern matching so all of them agree.
    """
    # POSIX classes first (so a negated class like [^[:digit:]] still works).
    # The pathname table drops '/' from punct (glob.glob splits on '/').
    pattern = _POSIX_CLASS_RE.sub(
        lambda m: _POSIX_CLASSES_PATHNAME.get(m.group(1), m.group(0)), pattern
    )
    # Bracket negation: [^ -> [! when the '[' is not backslash-escaped.
    pattern = re.sub(r'(?<!\\)\[\^', '[!', pattern)
    return pattern


class GlobExpander:
    """Handles pathname expansion (globbing)."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state

    def expand(self, pattern: str) -> List[str]:
        """
        Expand glob pattern.

        Returns a list of matching filenames, or an empty list
        if no matches are found.
        """
        # Check for extglob patterns first
        if self.state.options.get('extglob', False):
            from .extglob import contains_extglob
            if contains_extglob(pattern):
                return self._expand_extglob(pattern)

        # Normalize POSIX classes / [^...] negation so fnmatch/glob handle them.
        translated = normalize_bracket_expressions(pattern)

        # Check if the pattern contains glob characters
        if not has_glob_metacharacters(translated):
            return [pattern]

        dotglob = self.state.options.get('dotglob', False)
        globstar = self.state.options.get('globstar', False)
        nocaseglob = self.state.options.get('nocaseglob', False)

        if nocaseglob:
            matches = self._glob_nocase(translated, dotglob)
        else:
            matches = glob.glob(translated, include_hidden=dotglob, recursive=globstar)

        # Byte (C-locale) ordering. bash sorts glob results with strcoll() in
        # the current LC_COLLATE, so this diverges from bash in a non-C locale
        # (`[a-c]*` -> `aa aB banana` in bash vs `aB aa banana` here). Matching
        # bash would need a process-global locale.setlocale() at startup plus a
        # locale.strxfrm sort key; that is intentionally deferred as the same
        # known limitation as `[[ < ]]` / `[ < ]` collation (see
        # executor/enhanced_test_evaluator.py and builtins/test_command.py).
        return sorted(matches) if matches else []

    def _glob_nocase(self, pattern: str, dotglob: bool) -> List[str]:
        """Case-insensitive pathname expansion (shopt -s nocaseglob).

        Walks the pattern component by component, matching each against the
        directory entries case-insensitively. Used only when nocaseglob is set,
        so the default (case-sensitive) path is untouched.
        """
        sep = os.sep
        if pattern.startswith(sep):
            current = [sep]
            rest = pattern.lstrip(sep)
        else:
            current = ['']
            rest = pattern

        for comp in rest.split(sep):
            if comp == '':
                continue
            has_magic = has_glob_metacharacters(comp)
            if has_magic:
                regex = re.compile(fnmatch.translate(comp), re.IGNORECASE)
            else:
                regex = re.compile(re.escape(comp) + r'\Z', re.IGNORECASE)

            nxt = []
            for base in current:
                listing_dir = base if base else '.'
                try:
                    entries = os.listdir(listing_dir)
                except OSError:
                    continue
                for entry in entries:
                    if (has_magic and not dotglob
                            and entry.startswith('.') and not comp.startswith('.')):
                        continue
                    if regex.match(entry):
                        nxt.append(os.path.join(base, entry) if base else entry)
            current = nxt

        return current

    def _expand_extglob(self, pattern: str) -> List[str]:
        """Expand an extglob pattern against the filesystem.

        Walks the pattern one path component at a time so extglob operators
        work in NON-final components too (``@(dir1|dir2)/file``), not just the
        basename. Plain-glob and literal components in the same pattern are
        matched normally. Returns an empty list on no match (the caller keeps
        the pattern literal).
        """
        dotglob = self.state.options.get('dotglob', False)

        sep = os.sep
        if pattern.startswith(sep):
            bases = [sep]
            rest = pattern[len(sep):]
        else:
            bases = ['']
            rest = pattern

        for comp in rest.split(sep):
            if comp == '':
                continue
            bases = self._match_glob_component(comp, bases, dotglob)
            if not bases:
                return []
        return sorted(bases)

    def _match_glob_component(self, comp: str, bases: List[str],
                              dotglob: bool) -> List[str]:
        """Match a single path component against the entries of each base dir.

        Handles extglob (``@(...)`` etc.), plain glob (``*?[...]``), and literal
        components uniformly, returning the joined paths that matched.
        """
        from .extglob import contains_extglob, expand_extglob

        result: List[str] = []
        if self.state.options.get('extglob', False) and contains_extglob(comp):
            # Extglob component: reuse the per-directory matcher, which does its
            # own dotfile filtering.
            for base in bases:
                listing_dir = base if base else '.'
                for name in expand_extglob(comp, listing_dir, dotglob=dotglob):
                    result.append(os.path.join(base, name) if base else name)
            return result

        if has_glob_metacharacters(comp):
            regex = re.compile(fnmatch.translate(
                normalize_bracket_expressions(comp)))
            is_pattern = True
        else:
            regex = None  # literal component: exact-name match (existence check)
            is_pattern = False

        for base in bases:
            listing_dir = base if base else '.'
            try:
                entries = os.listdir(listing_dir)
            except OSError:
                continue
            for entry in entries:
                if (is_pattern and not dotglob
                        and entry.startswith('.') and not comp.startswith('.')):
                    continue
                if (entry == comp if regex is None
                        else regex.match(entry) is not None):
                    result.append(os.path.join(base, entry) if base else entry)
        return result
