"""Glob (pathname) expansion implementation."""
import os
import re
from typing import TYPE_CHECKING, Callable, Iterator, List, Tuple

from ..core.locale_service import posix_class_ranges

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

# A slash-free variant of the class table: a pathname pattern is split on
# ``/`` before per-component matching, so a bracket range must not carry a
# literal ``/``. punct is the only class that spans ``/`` (0x2f): drop it
# there — no filename can contain ``/``, so the matched set is identical.
# Production-DEAD after W3 (the engine resolves classes via the locale
# service); the dependency of ``normalize_bracket_expressions`` below — the
# PERMANENT fnmatch reference oracle (campaign Q3 ruling) — so it stays.
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

    Locale-aware: like ``==``/``case``, bash's ``=~`` honours the locale for
    classes (``[[ é =~ ^[[:alpha:]]$ ]]`` is true under a UTF-8 locale, false
    under C), so the substituted ranges come from the locale service — the ASCII
    table in the C locale (unchanged) and the host libc's iswctype membership in
    a UTF-8 locale.
    """

    def _sub(m: 're.Match[str]') -> str:
        r = posix_class_ranges(m.group(1))
        return r if r is not None else m.group(0)

    return _POSIX_CLASS_RE.sub(_sub, pattern)


def normalize_bracket_expressions(pattern: str) -> str:
    """Adapt shell bracket expressions to the form stdlib ``fnmatch``
    understands (POSIX ``[[:class:]]`` → equivalent ranges, ``[^...]`` →
    ``[!...]``).

    No PRODUCTION path needs this rewrite after campaign W3 (every pathname
    consumer matches per-name through the ONE compiled pattern engine
    ``_component_matcher`` above), but it is NOT dead: it is a PERMANENT
    reference oracle (campaign Q3 integrator ruling — NOT a deferred deletion),
    the live ``fnmatch`` reference half of the oracle in
    ``tests/unit/expansion/test_unified_glob_converter.py`` (which cross-checks
    ``_component_matcher`` against ``fnmatch.translate(normalize_bracket_
    expressions(comp))``). It and the ``extglob_to_regex`` / ``_convert_pattern``
    differential oracle earn their keep as live differential infrastructure and
    stay; ``_POSIX_CLASSES_PATHNAME`` stays as its dependency. (The
    fully-unreferenced ``extglob.glob_to_regex_body`` sibling WAS deleted in the
    campaign Q2 census — it had no oracle.)
    """
    # POSIX classes first (so a negated class like [^[:digit:]] still works).
    # The pathname table drops '/' from punct (glob.glob splits on '/').
    pattern = _POSIX_CLASS_RE.sub(
        lambda m: _POSIX_CLASSES_PATHNAME.get(m.group(1), m.group(0)), pattern
    )
    # Bracket negation: [^ -> [! when the '[' is not backslash-escaped.
    pattern = re.sub(r'(?<!\\)\[\^', '[!', pattern)
    return pattern


def _component_matcher(comp: str, ignorecase: bool = False) -> Callable[[str], bool]:
    """Return a predicate ``entry -> bool`` matching one pathname COMPONENT glob
    through the shell's ONE compiled pattern engine (``pattern_engine``).

    This is the pathname side of the single relation shared with ``case`` /
    ``[[ == ]]`` / parameter-expansion matching, so bracket/class/escape
    semantics can no longer drift between "matching a pattern against a
    filename" and "matching it against a string", and a pathological component
    (``*a*a…*b``) can no longer backtrack exponentially (#20 H7).

    * ``PATHNAME`` profile → ``*``/``?`` never cross ``/`` (a single component
      never spans it), and ``extglob=False`` because extglob components are
      handled by the caller before a component reaches here.
    * ``comp`` is the ONE canonical protection encoding (``pattern_engine.
      runs_to_pattern_string``, built by ``word_expander._pattern_from_runs``):
      ``\\`` = escape, a residual value backslash already doubled, and a quoted
      class-special char already ``\\``-escaped. A ``x="a\\*b"; echo $x`` value
      backslash is literal because it arrives doubled (``a\\\\*b`` -> literal
      ``\\`` + live ``*``); a quoted ``[a"-"c]`` bracket char is a literal
      member — one protection semantics shared with the ``${...}`` operand path.
    * ``ignorecase`` (``nocaseglob``) uses the engine's locale-aware bracket
      membership, which — like ``nocasematch`` — keeps ``[[:upper:]]`` /
      ``[[:lower:]]`` case-SENSITIVE (bash: ``shopt -s nocaseglob; *[[:upper:]]*``
      matches only actually-uppercase names). The former regex path folded them
      via ``re.IGNORECASE``, a bug this fixes.
    """
    from .pattern_engine import PatternCompiler, pathname_profile
    compiled = PatternCompiler.compile(comp, extglob=False)
    profile = pathname_profile(ignorecase)
    return lambda entry: compiled.full_match(entry, profile)


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
                if (self.state.options.get('globstar', False)
                        and any(c == '**' for c in pattern.split(os.sep))):
                    # extglob combined with a bare `**` component: the
                    # globstar walker recurses properly (and handles the
                    # extglob components via _match_glob_component), where
                    # _expand_extglob would treat `**` as a single level.
                    return self._sorted(self._expand_globstar(
                        pattern, self.state.options.get('dotglob', False)))
                return self._expand_extglob(pattern)

        # Check if the pattern contains glob characters. normalize_bracket_
        # expressions never adds or removes a metacharacter (it only rewrites
        # bracket-expression *contents*), so this holds on the raw pattern.
        if not has_glob_metacharacters(pattern):
            return [pattern]

        dotglob = self.state.options.get('dotglob', False)
        globstar = self.state.options.get('globstar', False)
        nocaseglob = self.state.options.get('nocaseglob', False)

        if nocaseglob:
            matches = self._glob_walk(pattern, dotglob, ignorecase=True)
        elif globstar and any(c == '**' for c in pattern.split(os.sep)):
            # A bare `**` component under shopt -s globstar: bash's recursive
            # scan does NOT descend through symlinked directories, but
            # Python's glob.glob(recursive=True) does (and can loop) — use
            # the symlink-aware walker instead.
            matches = self._expand_globstar(pattern, dotglob)
        else:
            # Default (no `**` component): walk the pattern component by
            # component, matching each directory entry through the ONE compiled
            # pattern engine (``_component_matcher``). Routing pathname matching
            # through the engine — not stdlib ``glob.glob``/``fnmatch`` — keeps
            # one glob semantics across every consumer (#20 H7): a POSIX
            # ``[:class:]`` resolves through the locale service (so
            # ``[[:alpha:]]*`` matches é in a UTF-8 locale), quoted class-special
            # bracket members stay literal (carry-2), and no pattern backtracks
            # exponentially. The readdir/dotfile/collation walk is unchanged.
            matches = self._glob_walk(pattern, dotglob, ignorecase=False)

        # Order glob results in the current LC_COLLATE, like bash. The locale
        # service's collate_key is a codepoint key in the C locale (byte order,
        # psh's historical behaviour) and locale.strxfrm in a UTF-8/OTHER locale
        # (`[a-c]*` -> `aa aB banana` matching bash, not `aB aa banana`).
        return self._sorted(matches)

    def _sorted(self, matches: List[str]) -> List[str]:
        """Sort glob matches in the active collation order (empty-safe)."""
        return sorted(matches, key=self.state.locale.collate_key) if matches else []

    def _glob_walk(self, pattern: str, dotglob: bool,
                   ignorecase: bool) -> List[str]:
        """Pathname expansion by walking the pattern component by component and
        matching each directory entry through the ONE compiled pattern engine
        (``_component_matcher``). This is the sole non-``**`` pathname matcher
        (campaign W3): the default case-sensitive path, ``nocaseglob``
        (``ignorecase=True``), and a UTF-8 POSIX ``[:class:]`` all route here,
        so filename matching shares the shell's single glob semantics. The
        readdir/dotfile walk is unchanged from the former stdlib path.

        A trailing ``/`` (``dir*/``) restricts matches to directories
        (symlink-to-dir qualifies) and appends ``/`` to each result — bash.
        """
        sep = os.sep
        if pattern.startswith(sep):
            current = [sep]
            rest = pattern.lstrip(sep)
        else:
            current = ['']
            rest = pattern

        require_dir = rest.endswith(sep) and rest.strip(sep) != ''
        rest = rest.rstrip(sep)

        for comp in rest.split(sep):
            if comp == '':
                continue
            has_magic = has_glob_metacharacters(comp)
            # One matcher for magic AND literal components: a literal comp
            # compiles to an all-Literal pattern (exact match, ic-folded).
            matches = _component_matcher(comp, ignorecase=ignorecase)

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
                    if matches(entry):
                        nxt.append(os.path.join(base, entry) if base else entry)
            current = nxt

        if require_dir:
            # Trailing '/': keep only directories (symlink-to-dir qualifies,
            # os.path.isdir follows), each with a trailing separator.
            current = [p + sep for p in current if os.path.isdir(p or '.')]
        return current

    @staticmethod
    def _join_entry(text: str, name: str) -> str:
        """Join a directory prefix (as accumulated pattern/path text) and an
        entry name the way bash builds globstar results: ``''`` means the
        current directory (bare entry name), a prefix already ending in the
        separator keeps its written form (``sub//`` + ``deep`` ->
        ``sub//deep``), anything else gets one separator inserted."""
        if not text:
            return name
        if text.endswith(os.sep):
            return text + name
        return text + os.sep + name

    def _walk_no_follow(self, text: str, dotglob: bool
                        ) -> Iterator[Tuple[str, os.DirEntry]]:
        """Yield ``(joined_path, entry)`` for every descendant of the
        directory named by ``text`` ('' = cwd), depth-first.

        This is the ``**`` scan: it recurses into real directories only —
        a symlinked directory is yielded as a leaf but never entered
        (bash 4.3+), which also makes symlink loops safe. Hidden entries
        are skipped (and not descended into) unless ``dotglob``.
        Opening the STARTING directory itself follows symlinks (an explicit
        ``symdir/**`` prefix is honored); only scan-discovered links stop.
        """
        try:
            entries = list(os.scandir(text or '.'))
        except OSError:
            return
        for entry in entries:
            name = entry.name
            if name.startswith('.') and not dotglob:
                continue
            path = self._join_entry(text, name)
            yield path, entry
            try:
                is_real_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_real_dir = False
            if is_real_dir:
                yield from self._walk_no_follow(path, dotglob)

    def _expand_globstar(self, pattern: str, dotglob: bool) -> List[str]:
        """Expand a pattern containing a bare ``**`` component
        (``shopt -s globstar``), with bash-5.2-pinned semantics
        (truth table in tmp/probes-r17t2-grabbag/probe_b_globstar.sh):

        - ``**`` matches the base directory itself (zero components) plus
          every descendant; the recursive scan lists symlinks as leaves but
          never descends through them (so loops cannot hang).
        - A non-``**`` component naming a symlink IS followed
          (``symdir/**`` works; only the ``**`` scan refuses to descend).
        - When ``**`` is followed by more components, only REAL directories
          from the scan continue the match (bash: ``**/*.txt`` does not
          look inside ``symdir``).
        - Zero-component match text is bash-verbatim: a purely literal
          prefix keeps its written form (``sub/**`` -> ``sub/``,
          ``sub//**`` -> ``sub//``, ``./**`` -> ``./``) while a prefix that
          passed through any expanded component is a plain joined path
          (``**/sub/**`` -> ``sub``, ``s*/**`` -> ``sub``).
        - A trailing ``/`` restricts matches to directories (symlink-to-dir
          qualifies) and appends ``/`` to each result.
        """
        # Split off a leading run of separators (absolute patterns).
        lead = re.match(f'{re.escape(os.sep)}+', pattern)
        prefix = lead.group() if lead else ''
        comps = pattern[len(prefix):].split(os.sep)

        require_dir = False
        while comps and comps[-1] == '':
            comps.pop()
            require_dir = True
        if not comps:
            return []

        def is_pattern_comp(comp: str) -> bool:
            if has_glob_metacharacters(comp):
                return True
            if self.state.options.get('extglob', False):
                from .extglob import contains_extglob
                return contains_extglob(comp)
            return False

        def zero_text(text: str) -> str:
            """The base's text after a ``**`` matched zero components:
            joined-path form (no trailing separator; '/' kept for the
            filesystem root)."""
            return text.rstrip(os.sep) or (os.sep if text.startswith(os.sep)
                                           else '')

        # Bases: (text, literal). ``literal`` marks a prefix that is still
        # the pattern's own text verbatim (no expanded component yet).
        bases: List[Tuple[str, bool]] = [(prefix, True)]

        for comp in comps[:-1]:
            new_bases: dict = {}
            if comp == '':
                # Interior empty component (``sub//**``): keep the extra
                # separator verbatim.
                for text, literal in bases:
                    new_bases[(text + os.sep, literal)] = None
            elif comp == '**':
                for text, _literal in bases:
                    # Zero components: the base itself continues, now in
                    # joined-path (expanded) form.
                    new_bases[(zero_text(text), False)] = None
                    # One or more components: real directories only.
                    for path, entry in self._walk_no_follow(text, dotglob):
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                new_bases[(path, False)] = None
                        except OSError:
                            pass
            elif is_pattern_comp(comp):
                texts = [text for text, _ in bases]
                for path in self._match_glob_component(comp, texts, dotglob):
                    new_bases[(path, False)] = None
            else:
                # Literal component: appended verbatim, no scan. Existence
                # is checked when something is finally emitted.
                for text, literal in bases:
                    if literal:
                        new_bases[(text + comp + os.sep, True)] = None
                    else:
                        new_bases[(self._join_entry(text, comp), False)] = None
            bases = list(new_bases)

        results: dict = {}

        def emit(path: str) -> None:
            if require_dir:
                if os.path.isdir(path or '.'):
                    results[path if path.endswith(os.sep)
                            else path + os.sep] = None
            else:
                results[path] = None

        last = comps[-1]
        if last == '**':
            for text, literal in bases:
                # Zero components: the prefix itself (nameless at the top
                # level, so '' is never emitted). Literal prefixes keep
                # their verbatim written form.
                if text and os.path.isdir(text):
                    emit(text if literal else zero_text(text))
                for path, entry in self._walk_no_follow(text, dotglob):
                    if require_dir:
                        try:
                            if not entry.is_dir():  # follows symlinks
                                continue
                        except OSError:
                            continue
                    emit(path)
        elif is_pattern_comp(last):
            texts = [text for text, _ in bases]
            for path in self._match_glob_component(last, texts, dotglob):
                emit(path)
        else:
            for text, _literal in bases:
                candidate = self._join_entry(text, last)
                if os.path.lexists(candidate):
                    emit(candidate)

        return list(results)

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
        return self._sorted(bases)

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

        is_pattern = has_glob_metacharacters(comp)
        if is_pattern:
            matches = _component_matcher(comp)  # case-sensitive pathname match
        else:
            # Literal component: exact-name match (existence check).
            def matches(entry: str, _c: str = comp) -> bool:
                return entry == _c

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
                if matches(entry):
                    result.append(os.path.join(base, entry) if base else entry)
        return result
