"""Glob (pathname) expansion implementation."""
import fnmatch
import glob
import os
import re
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..shell import Shell


# POSIX character classes -> the character ranges to substitute *inside* an
# existing bracket expression. Only classes that map to bracket-safe ranges are
# included (punct/cntrl/print/graph contain bracket metacharacters and are left
# untranslated).
_POSIX_CLASSES = {
    'alpha': 'a-zA-Z',
    'digit': '0-9',
    'alnum': 'a-zA-Z0-9',
    'upper': 'A-Z',
    'lower': 'a-z',
    'xdigit': '0-9A-Fa-f',
    'blank': ' \t',
    'space': ' \t\n\r\x0b\x0c',
}

_POSIX_CLASS_RE = re.compile(r'\[:(\w+):\]')


def normalize_bracket_expressions(pattern: str) -> str:
    """Make shell bracket expressions understood by Python's fnmatch/glob.

    Translates POSIX character classes ``[[:alpha:]]`` to equivalent ranges and
    converts ``[^...]`` negation to fnmatch's ``[!...]`` form. Shared by
    pathname expansion and case/``[[ ]]`` pattern matching so all of them agree.
    """
    # POSIX classes first (so a negated class like [^[:digit:]] still works).
    pattern = _POSIX_CLASS_RE.sub(
        lambda m: _POSIX_CLASSES.get(m.group(1), m.group(0)), pattern
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
        if not any(c in translated for c in ('*', '?', '[')):
            return [pattern]

        dotglob = self.state.options.get('dotglob', False)
        globstar = self.state.options.get('globstar', False)
        nocaseglob = self.state.options.get('nocaseglob', False)

        if nocaseglob:
            matches = self._glob_nocase(translated, dotglob)
        else:
            matches = glob.glob(translated, include_hidden=dotglob, recursive=globstar)

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
            has_magic = any(c in comp for c in ('*', '?', '['))
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
        """Expand an extglob pattern against the filesystem."""
        from .extglob import expand_extglob

        dotglob = self.state.options.get('dotglob', False)

        # Determine directory and filename pattern
        dirname = os.path.dirname(pattern)
        basename = os.path.basename(pattern)

        if not dirname:
            dirname = '.'

        matches = expand_extglob(basename, dirname, dotglob=dotglob)

        if matches:
            if dirname != '.':
                matches = [os.path.join(dirname, m) for m in matches]
            return sorted(matches)
        return []
