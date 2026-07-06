"""Central locale service: effective locale + faithful ctype/collation primitives.

Before this module psh was *locale-blind*: it never called ``setlocale`` and so
classified characters with fixed ASCII tables, case-mapped unconditionally, and
sorted glob results / compared ``[[ < ]]`` operands by Unicode codepoint — which
is only correct in the ``C``/``POSIX`` locale. bash, by contrast, honours
``LC_CTYPE`` (character classes + case) and ``LC_COLLATE`` (ordering + string
comparison) from the environment. This service is the one place that:

* computes the **effective** ``LC_CTYPE`` and ``LC_COLLATE`` from the environment
  using bash's precedence ``LC_ALL > LC_{CTYPE,COLLATE} > LANG > C`` (an empty
  value is skipped, exactly as bash does), and
* owns the process ``setlocale`` calls and exposes faithful primitives:
  collation (:meth:`collate_key` / :meth:`compare`, Stage 1), case mapping
  (Stage 2), and POSIX character-class membership (Stage 3).

**Why process-global ``setlocale`` is acceptable here.** ``setlocale`` mutates
process-global C-library state and is not thread-safe. That is faithful, not a
compromise: bash's locale is process-global too, and psh is a single-threaded
shell. Embedding psh inside a multithreaded Python host that also cares about
its own locale is a documented non-goal. To keep the common case side-effect
free, the service calls ``setlocale`` **only** when a category resolves to a
non-C locale — under ``LC_ALL=C`` (the pinned test-suite locale, and psh's
default when nothing is set) it touches nothing and every primitive is
byte-identical to the old codepoint/ASCII behaviour.

Startup-only for now: the profile is read once from the environment at shell
construction. Reacting to mid-script ``LC_*``/``LANG`` assignment (bash does)
is a deliberate deferral — see
``docs/architecture/locale_service_design_2026-07-06.md`` (§5.2 Stage 4) and the
differences ledger.
"""
from __future__ import annotations

import locale as _locale
import sys
from dataclasses import dataclass
from enum import Enum, auto
from typing import Mapping, Optional


class LocaleMode(Enum):
    """How a locale category is interpreted.

    ``C`` — POSIX/C: ASCII-only classes, ASCII-only case mapping, codepoint
    collation (byte-identical to psh's pre-locale behaviour, no ``setlocale``).
    ``UTF8`` — a ``*.UTF-8`` locale: Unicode classes/case, ``strxfrm`` collation.
    ``OTHER`` — a non-UTF-8, non-C locale (e.g. an 8-bit ``ISO8859`` locale):
    documented fallback — ASCII class tables + ASCII case (full ctype fidelity
    in 8-bit locales is a non-goal) but real ``strxfrm`` collation.
    """
    C = auto()
    UTF8 = auto()
    OTHER = auto()


@dataclass(frozen=True)
class LocaleProfile:
    """The two effective locales a shell runs under, resolved and applied."""
    ctype_name: str
    collate_name: str
    ctype_mode: LocaleMode
    collate_mode: LocaleMode


#: Category-variable precedence chains (bash: ``LC_ALL`` overrides the specific
#: category, which overrides ``LANG``). An empty string is treated as unset.
_CTYPE_VARS = ("LC_ALL", "LC_CTYPE", "LANG")
_COLLATE_VARS = ("LC_ALL", "LC_COLLATE", "LANG")


def _classify(name: str) -> LocaleMode:
    """Map a locale NAME to its interpretation mode."""
    up = name.upper()
    if up in ("C", "POSIX", ""):
        return LocaleMode.C
    if up.endswith("UTF-8") or up.endswith("UTF8"):
        return LocaleMode.UTF8
    return LocaleMode.OTHER


def _effective(env: Mapping[str, str], chain: tuple) -> str:
    """First non-empty value along a precedence *chain*, else ``"C"``."""
    for var in chain:
        val = env.get(var)
        if val:  # non-empty -> wins (bash skips empty LC_*/LANG values)
            return val
    return "C"


class LocaleService:
    """Owns the process locale and exposes faithful ctype/collation primitives.

    One instance lives on shell state (``shell.state.locale``), created at
    startup from ``state.env``.
    """

    def __init__(self, env: Mapping[str, str], *, apply: bool = True,
                 warn: bool = True) -> None:
        collate_name = _effective(env, _COLLATE_VARS)
        ctype_name = _effective(env, _CTYPE_VARS)
        collate_mode = _classify(collate_name)
        ctype_mode = _classify(ctype_name)

        if apply:
            # setlocale is process-global; only touch a category that needs a
            # non-C locale. On failure warn (like bash) and fall back to C for
            # that category so the shell still runs.
            if collate_mode is not LocaleMode.C and not _try_setlocale(
                    _locale.LC_COLLATE, collate_name, warn):
                collate_name, collate_mode = "C", LocaleMode.C
            if ctype_mode is not LocaleMode.C and not _try_setlocale(
                    _locale.LC_CTYPE, ctype_name, warn):
                ctype_name, ctype_mode = "C", LocaleMode.C

        self.profile = LocaleProfile(ctype_name, collate_name,
                                     ctype_mode, collate_mode)
        _activate(self)

    # --- case mapping (LC_CTYPE) ------------------------------------------
    #
    # bash case-maps with the C library's towupper/towlower, which is
    # locale-sensitive: in a UTF-8 locale it maps Unicode (é->É), but in the C
    # locale it maps ASCII ONLY and leaves every non-ASCII codepoint untouched
    # (verified: `${x^^}` on é is é under C, É under en_US.UTF-8; likewise
    # `declare -u café` is CAFé under C, CAFÉ under UTF-8). psh used to map
    # Unicode unconditionally, so it over-eagerly upper-cased é even under C.
    # UTF-8 mode delegates to the length-safe ``simple_*`` mappings (1:1
    # codepoint, so ß stays ß rather than growing to "SS"); C/OTHER mode uses
    # the ASCII-only gate below. These are the ONE place ^^ / ,, / ~~ / @U / @L /
    # @u / declare -u / declare -l resolve their case mapping.
    def upper(self, s: str) -> str:
        if self.profile.ctype_mode is LocaleMode.UTF8:
            from ..lexer.unicode_support import simple_upper
            return simple_upper(s)
        return _ascii_upper(s)

    def lower(self, s: str) -> str:
        if self.profile.ctype_mode is LocaleMode.UTF8:
            from ..lexer.unicode_support import simple_lower
            return simple_lower(s)
        return _ascii_lower(s)

    def toggle(self, s: str) -> str:
        if self.profile.ctype_mode is LocaleMode.UTF8:
            from ..lexer.unicode_support import toggle_case
            return toggle_case(s)
        return _ascii_toggle(s)

    # --- collation (LC_COLLATE) -------------------------------------------
    def collate_key(self, s: str):
        """Sort key reproducing the active ``LC_COLLATE`` order.

        In C mode this is the string itself (codepoint order); in UTF-8/OTHER
        mode it is ``locale.strxfrm(s)``, which reproduces bash's ``strcoll``
        ordering exactly (verified against macOS bash; tracks glibc on Linux).
        Undecodable input falls back to the codepoint key rather than raising.
        """
        if self.profile.collate_mode is LocaleMode.C:
            return s
        try:
            return _locale.strxfrm(s)
        except (ValueError, _locale.Error):
            return s

    def compare(self, a: str, b: str) -> int:
        """Three-way comparison of two strings under ``LC_COLLATE``.

        Returns a negative/zero/positive int for ``a<b`` / ``a==b`` / ``a>b``,
        for ``[[ a < b ]]`` / ``[ a \\< b ]``. Codepoint order in C mode,
        ``locale.strcoll`` sign otherwise (with a codepoint fallback on error).
        """
        if self.profile.collate_mode is LocaleMode.C:
            return (a > b) - (a < b)
        try:
            r = _locale.strcoll(a, b)
            return (r > 0) - (r < 0)
        except (ValueError, _locale.Error):
            return (a > b) - (a < b)


def _ascii_upper(s: str) -> str:
    """Uppercase ASCII letters only (C-locale ``towupper``); leave the rest."""
    return "".join(c.upper() if "a" <= c <= "z" else c for c in s)


def _ascii_lower(s: str) -> str:
    """Lowercase ASCII letters only (C-locale ``towlower``); leave the rest."""
    return "".join(c.lower() if "A" <= c <= "Z" else c for c in s)


def _ascii_toggle(s: str) -> str:
    """Toggle ASCII-letter case only (C-locale); leave every other codepoint."""
    out = []
    for c in s:
        if "a" <= c <= "z":
            out.append(c.upper())
        elif "A" <= c <= "Z":
            out.append(c.lower())
        else:
            out.append(c)
    return "".join(out)


def _try_setlocale(category: int, name: str, warn: bool) -> bool:
    """``setlocale(category, name)``; on failure warn like bash and return False."""
    try:
        _locale.setlocale(category, name)
        return True
    except _locale.Error:
        if warn:
            cat = {getattr(_locale, "LC_CTYPE", None): "LC_CTYPE",
                   getattr(_locale, "LC_COLLATE", None): "LC_COLLATE"}.get(
                       category, "LC_ALL")
            # bash prints e.g. "bash: warning: setlocale: LC_CTYPE: cannot
            # change locale (bogus): No such file or directory".
            print(f"psh: warning: setlocale: {cat}: cannot change locale "
                  f"({name})", file=sys.stderr)
        return False


# --- process-active service ------------------------------------------------
#
# The glob->regex converter (extglob.py) and pattern code are stateless
# module-level functions with no shell handle, but character-class membership
# is a function of the process-global locale — which is exactly what this
# reflects. The most-recently-constructed service registers itself here so
# those functions can ask "what does [:alpha:] mean right now?". Consistent
# with setlocale itself being process-global.
_active: Optional["LocaleService"] = None


def _activate(svc: "LocaleService") -> None:
    global _active
    _active = svc


def active_locale() -> Optional["LocaleService"]:
    """The process's active locale service, or None before any shell exists."""
    return _active
