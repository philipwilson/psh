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
non-C locale — under an explicit ``LC_ALL=C`` (the pinned test-suite locale)
it touches nothing and every primitive is byte-identical to the old
codepoint/ASCII behaviour.

**PEP 538 caveat (verifier finding, v0.655; resolved in Stage 4).** "Nothing
set" is NOT C mode on CPython 3.7+: when the interpreter starts under an
effectively-C locale with ``LC_ALL`` empty/unset, PEP 538 coercion rewrites
``os.environ['LC_CTYPE']`` to a UTF-8 locale *before* this service reads it, so
a bare-C/``LANG=C``-only environment would compute UTF-8 ctype where bash uses
C. Stage 4 strips that phantom at startup (``ShellState._strip_coerced_lc_ctype``
— detected by ``sys.flags.utf8_mode`` plus a coercion-target value), so psh now
presents bash-C behaviour under those environments (empty ``$LC_CTYPE``, C
classification, no ``LC_CTYPE`` leaked to children). An explicit ``LC_ALL=C``
disables coercion and is likewise fully bash-faithful. The one residual is a
user who forces UTF-8 mode with ``PYTHONUTF8`` while genuinely setting a
``C.UTF-8`` ``LC_CTYPE`` — a Python-only knob, not a shell path; see the
differences ledger.

Reactive as of Stage 4: the startup profile is read once at construction, and
:meth:`reinit` recomputes it whenever ``LC_*``/``LANG`` is assigned, unset, or
laid over a command (``LC_ALL=C cmd``). ``ShellState`` rides its
reactive-special observer to call ``reinit`` on those four names; see
``docs/architecture/locale_service_design_2026-07-06.md`` (§5.2 Stage 4).

**Construction purity (campaign F2).** ``ShellState`` builds its service
DEFERRED (``deferred=True``): construction resolves the profile purely — no
``setlocale`` and no process-active registration — and the libc application
happens at shell ACTIVATION (or on a reactive non-C ``reinit``) under the
``ProcessLeaseCoordinator``'s LOCALE component lease
(``ShellState._acquire_locale_lease`` → :meth:`ensure_applied`), which
captures the pre-application libc names (:func:`libc_locale_names`) and
restores them when the embedded shell deactivates.  Constructing a second
shell therefore changes NOTHING observable about the first — pinned by
``tests/unit/core/test_construction_purity_f2.py``.  The process-active
service (consumed by the stateless pattern helpers via :func:`active_locale`)
is maintained SOLELY by the activation glue
(:func:`set_process_active_locale`), never by construction.  A standalone
service (``deferred=False``, the unit-test seam) keeps the historical
apply-at-construction/reinit behaviour.
"""
from __future__ import annotations

import locale as _locale
import re
import sys
import unicodedata
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Dict, Mapping, Optional, Tuple


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
class LocaleContext:
    """The two effective locales a shell runs under (campaign contract).

    The frozen per-shell classification/collation/case-mapping policy — the
    ``LocaleContext`` row of the boundary campaign's canonical representation
    set (section 5).  Sole authority: the owning shell instance
    (``shell.state.locale.profile``); libc application is a separate,
    lease-guarded step (see the module docstring).
    """
    ctype_name: str
    collate_name: str
    ctype_mode: LocaleMode
    collate_mode: LocaleMode


#: Historical (pre-campaign) name for the canonical :class:`LocaleContext`
#: (brief §5). Owner: the locale service (this module). It has ZERO code
#: consumers (grep-verified, campaign Q3 census) and survives only because the
#: dated design record ``docs/architecture/locale_service_design_2026-07-06.md``
#: still uses the name. Removal condition: safe to delete outright once that
#: design record is archived — no code migration is required.
LocaleProfile = LocaleContext


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


def _resolve_profile(env: Mapping[str, str]) -> LocaleContext:
    """Resolve the two effective locales from *env* (bash precedence).

    PURE — no ``setlocale``.  Shared by startup (:meth:`LocaleService.__init__`)
    and mid-session (:meth:`LocaleService.reinit`).  Driving the process
    ``setlocale`` is the separate :meth:`LocaleService.ensure_applied` step,
    which the activation-lease glue invokes for a deferred (shell-owned)
    service.
    """
    collate_name = _effective(env, _COLLATE_VARS)
    ctype_name = _effective(env, _CTYPE_VARS)
    return LocaleContext(ctype_name, collate_name,
                         _classify(ctype_name), _classify(collate_name))


class LocaleService:
    """Owns the process locale and exposes faithful ctype/collation primitives.

    One instance lives on shell state (``shell.state.locale``), created at
    startup from ``state.env``.
    """

    def __init__(self, env: Mapping[str, str], *, apply: bool = True,
                 warn: bool = True, deferred: bool = False) -> None:
        """Resolve the effective profile from *env*.

        ``deferred=True`` (the shell-owned mode, campaign F2): construction
        is PURE — the profile is resolved but libc is never touched and the
        service is not registered process-active; the owning ``ShellState``
        applies it at activation, under the coordinator's LOCALE lease
        (:meth:`ensure_applied`).  ``deferred=False`` is the standalone /
        unit-test seam: ``apply=True`` applies at construction and
        :meth:`reinit` re-applies, matching the historical behaviour.
        """
        self._deferred = deferred
        self._applied = False
        self.profile = _resolve_profile(env)
        if apply and not deferred:
            self.ensure_applied(warn=warn)

    @property
    def pending_libc(self) -> bool:
        """True when the profile needs a not-yet-performed libc application.

        Only a non-C category ever needs libc; under the pinned test-suite
        ``LC_ALL=C`` this is always False and no lease is taken.
        """
        return (not self._applied
                and (self.profile.ctype_mode is not LocaleMode.C
                     or self.profile.collate_mode is not LocaleMode.C))

    def ensure_applied(self, *, warn: bool = True) -> None:
        """Drive the process ``setlocale`` for the resolved profile (idempotent).

        Only a category resolving to a NON-C locale is touched; a category
        resolving to C is left to the pure-Python C path (byte-identical to
        the historical behaviour, no libc churn).  On a setlocale failure the
        shell warns (like bash) and falls back to C for that category so it
        still runs.  For a deferred (shell-owned) service this runs ONLY
        under the coordinator's LOCALE component lease
        (``ShellState._acquire_locale_lease``), which captured the baseline
        to restore at deactivation.
        """
        if self._applied:
            return
        self._applied = True
        p = self.profile
        collate_name, collate_mode = p.collate_name, p.collate_mode
        ctype_name, ctype_mode = p.ctype_name, p.ctype_mode
        if collate_mode is not LocaleMode.C and not _try_setlocale(
                _locale.LC_COLLATE, collate_name, warn):
            collate_name, collate_mode = "C", LocaleMode.C
        if ctype_mode is not LocaleMode.C and not _try_setlocale(
                _locale.LC_CTYPE, ctype_name, warn):
            ctype_name, ctype_mode = "C", LocaleMode.C
        self.profile = LocaleContext(ctype_name, collate_name,
                                     ctype_mode, collate_mode)

    def invalidate_application(self) -> None:
        """Mark the profile un-applied (the LOCALE lease restore hook).

        Called when the coordinator restores the libc baseline at
        deactivation, so a later re-activation of the owning shell knows to
        re-apply (re-acquiring the lease).
        """
        self._applied = False

    def reinit(self, env: Mapping[str, str], *, warn: bool = True) -> None:
        """Recompute (and, standalone, re-apply) the profile from *env*.

        Called when a locale variable (``LC_ALL``/``LC_CTYPE``/``LC_COLLATE``/
        ``LANG``) is assigned, unset, or laid over a command as a ``LC_ALL=C
        cmd`` temp-env prefix — so classification, case mapping, and collation
        track live ``LC_*``/``LANG`` state the way bash does (Stage 4). It reuses
        the startup resolver, so the same precedence, empty-value skipping, and
        setlocale-only-for-non-C policy apply: a revert TO C simply flips the
        mode back to the pure-Python C path (byte-identical to the historical
        behaviour) without touching the process libc locale — the C-mode
        primitives never consult it, which also keeps in-process locale churn
        from leaking between shells. *env* is the caller's current view of the
        four variables (see ``ShellState._locale_env_snapshot``).

        A DEFERRED (shell-owned) service resolves only; the owning state's
        observer performs the lease-guarded application immediately after
        (``ShellState._sync_exported_variable`` → ``_acquire_locale_lease``),
        so mid-session reactivity is unchanged — merely lease-accounted.
        """
        self.profile = _resolve_profile(env)
        self._applied = False
        if not self._deferred:
            self.ensure_applied(warn=warn)

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

    # --- POSIX character-class membership (LC_CTYPE) ----------------------
    def in_class(self, ch: str, name: str) -> bool:
        """Whether *ch* belongs to POSIX class *name* under the active locale.

        C/OTHER mode uses the fixed ASCII class tables (byte-identical to psh's
        historical behaviour; full 8-bit-locale ctype fidelity is a non-goal);
        UTF-8 mode consults the host libc's ``iswctype`` (via ctypes) so it is
        byte-faithful to the same bash on this host, with a pure-Python
        (``str.is*`` / ``unicodedata``) fallback if ctypes is unavailable.

        This per-character predicate is the shape the finding-#6 pattern engine
        will consume; the regex path uses :func:`posix_class_ranges` instead.
        """
        if self.profile.ctype_mode is LocaleMode.UTF8:
            member = _class_member_fn(name)
            return member(ord(ch)) if member is not None else False
        return _ascii_in_class(ch, name)

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
# reflects.  Campaign F2: the slot is maintained SOLELY by the activation
# glue (``ShellState._on_activation_grant`` under the
# ``ProcessLeaseCoordinator``) — the shell that holds the process owner token
# is the one whose service answers "what does [:alpha:] mean right now?".
# Construction NEVER writes it (that was the H18 defect: building a second
# shell silently changed the first shell's pattern classification).
_active: Optional["LocaleService"] = None


def set_process_active_locale(svc: Optional["LocaleService"]) -> None:
    """Install *svc* as the process-active service (activation glue ONLY).

    Called by ``ShellState._on_activation_grant`` when the process owner
    token is granted or transferred — never by construction (campaign F2
    construction purity; pinned by test_construction_purity_f2.py).
    """
    global _active
    _active = svc


def active_locale() -> Optional["LocaleService"]:
    """The process's active locale service, or None before any shell ACTIVATED."""
    return _active


# --- libc baseline capture/restore (the LOCALE component lease) -------------

def libc_locale_names() -> Tuple[str, str]:
    """The current libc ``(LC_CTYPE, LC_COLLATE)`` names.

    The LOCALE component lease's baseline capture (and the activation
    baselines record) — queried BEFORE :meth:`LocaleService.ensure_applied`
    mutates anything, so :func:`restore_libc_locale` can put the process
    back exactly where the embedding host had it.
    """
    return (_locale.setlocale(_locale.LC_CTYPE),
            _locale.setlocale(_locale.LC_COLLATE))


def restore_libc_locale(names: Tuple[str, str]) -> None:
    """Restore a :func:`libc_locale_names` baseline (lease release hook)."""
    ctype_name, collate_name = names
    for category, name in ((_locale.LC_CTYPE, ctype_name),
                           (_locale.LC_COLLATE, collate_name)):
        try:
            _locale.setlocale(category, name)
        except _locale.Error:
            pass  # baseline no longer valid on this host; best effort


# --- POSIX character-class membership machinery ----------------------------
#
# The one class-interpretation chokepoint is the glob->regex converter
# (extglob._bracket_to_regex), which substitutes a regex character-class body
# for each ``[:name:]``. In C/OTHER mode that body is the fixed ASCII range
# table (glob._POSIX_CLASSES) — byte-identical to psh's historical behaviour.
# In a UTF-8 locale stdlib ``re`` cannot express "Unicode letter", so we
# instead compute the class's membership set ONCE per (locale, class) by
# sweeping every codepoint through the host libc's ``iswctype`` (ctypes), then
# compress it into explicit ``\Uxxxxxxxx`` ranges and splice THAT into the
# regex. The sweep of the full 0x110000 range costs ~0.3s (ctypes) the first
# time a given class is used in a UTF-8 locale; every subsequent use is a cache
# hit, and the C-mode fast path never sweeps at all. (Measured alternatives:
# a BMP-only sweep is ~16x faster but silently drops astral letters/digits; a
# per-codepoint memoized predicate avoids the up-front cost but cannot stay on
# the single shared regex path. The full lazy sweep keeps every match site —
# case / [[ == ]] / ${x#pat} / pathname — on one converter, which is the
# v0.638 design.) ctypes is the maximum-fidelity backend: iswctype is the same
# call bash makes, so it is byte-identical to the host's own bash on macOS AND
# glibc (which genuinely disagree on e.g. whether ٣ is a digit). A pure-Python
# ``str.is*`` / ``unicodedata`` fallback covers the (rare) case where ctypes or
# libc is unavailable; it is close but not byte-identical (documented).

_MAX_CODEPOINT = 0x110000

# Cache: (ctype_locale_name, class_name) -> regex-class body, or None if the
# name is not a POSIX class. In-process; a UTF-8 process resolves each class
# once. Keyed by locale name so it survives across LocaleService instances in
# one process (e.g. subshells sharing the parent's locale).
_RANGE_CACHE: Dict[Tuple[str, str], Optional[str]] = {}

_LIBC_UNSET = object()
_libc: object = _LIBC_UNSET  # host libc handle, or None if unavailable


def _get_libc() -> object:
    """Lazily load the host libc with wctype/iswctype bound (or None)."""
    global _libc
    if _libc is _LIBC_UNSET:
        _libc = _load_libc()
    return _libc


def _load_libc() -> object:
    """Bind the host libc's wctype/iswctype via ctypes, portable across
    macOS (libc.dylib) and Linux (libc.so.6). Returns None on any failure so
    the caller falls back to the pure-Python predicates — never a crash.

    ``wchar_t`` is 32-bit on both platforms (verified), so ``ord(ch)`` fed to
    ``iswctype`` covers astral codepoints; ``wctype_t`` is ``unsigned long`` on
    both (macOS ``__darwin_wctype_t``, glibc ``wctype_t``)."""
    try:
        import ctypes
        import ctypes.util
        libname = ctypes.util.find_library("c")
        libc = ctypes.CDLL(libname, use_errno=True) if libname \
            else ctypes.CDLL(None, use_errno=True)
        libc.wctype.restype = ctypes.c_ulong
        libc.wctype.argtypes = [ctypes.c_char_p]
        libc.iswctype.restype = ctypes.c_int
        libc.iswctype.argtypes = [ctypes.c_int, ctypes.c_ulong]
        return libc
    except Exception:
        return None


def _ctypes_member_fn(name: str) -> Optional[Callable[[int], bool]]:
    """A ``(codepoint) -> bool`` membership predicate backed by the host libc's
    ``iswctype`` under the active locale, or None if libc/this class is
    unavailable. iswctype (NOT the isw* narrow functions, which disagree with it
    on macOS for e.g. ٣) is what bash uses, so this is host-bash-faithful."""
    libc = _get_libc()
    if libc is None:
        return None
    try:
        handle = libc.wctype(name.encode("ascii"))  # type: ignore[attr-defined]
    except Exception:
        return None
    if not handle:
        return None  # libc does not know this class name
    isw = libc.iswctype  # type: ignore[attr-defined]
    return lambda cp: bool(isw(cp, handle))


_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

# Pure-Python fallback predicates (used only when ctypes/libc is unavailable).
# Close to macOS bash for the common classes; the digit/punct/space edges where
# glibc/macOS/Python differ are a documented approximation of the fallback.
_PY_PREDICATES: Dict[str, Callable[[int], bool]] = {
    "alpha": lambda cp: chr(cp).isalpha(),
    "upper": lambda cp: chr(cp).isupper(),
    "lower": lambda cp: chr(cp).islower(),
    "digit": lambda cp: chr(cp).isdigit(),
    "alnum": lambda cp: chr(cp).isalnum(),
    "space": lambda cp: chr(cp).isspace(),
    "blank": lambda cp: chr(cp) in " \t" or unicodedata.category(chr(cp)) == "Zs",
    "xdigit": lambda cp: chr(cp) in _HEX_DIGITS,
    "punct": lambda cp: unicodedata.category(chr(cp))[0] in ("P", "S"),
    "cntrl": lambda cp: unicodedata.category(chr(cp)) == "Cc",
    "graph": lambda cp: chr(cp).isprintable() and not chr(cp).isspace(),
    "print": lambda cp: chr(cp).isprintable(),
}


def _class_member_fn(name: str) -> Optional[Callable[[int], bool]]:
    """Membership predicate for POSIX class *name* under the active locale:
    the host libc (ctypes) if available, else the pure-Python fallback, else
    None if *name* is not a known POSIX class."""
    fn = _ctypes_member_fn(name)
    if fn is not None:
        return fn
    return _PY_PREDICATES.get(name)


def _range_token(lo: int, hi: int) -> str:
    """A ``\\U``-escaped single codepoint or ``lo-hi`` range for a regex class."""
    if lo == hi:
        return f"\\U{lo:08x}"
    return f"\\U{lo:08x}-\\U{hi:08x}"


def _sweep_ranges(member: Callable[[int], bool]) -> str:
    """Sweep every codepoint and compress the members into a regex-class body
    of ``\\U``-escaped ranges (safe to splice inside ``[...]``)."""
    parts = []
    start: Optional[int] = None
    for cp in range(_MAX_CODEPOINT):
        if member(cp):
            if start is None:
                start = cp
        elif start is not None:
            parts.append(_range_token(start, cp - 1))
            start = None
    if start is not None:
        parts.append(_range_token(start, _MAX_CODEPOINT - 1))
    return "".join(parts)


def posix_class_ranges(name: str) -> Optional[str]:
    """Regex character-class body for POSIX ``[:name:]`` under the active locale,
    to be spliced INSIDE a regex ``[...]`` (no brackets). Returns None if *name*
    is not a POSIX class (the caller keeps the ``[:name:]`` text literal).

    C/OTHER mode (or no active service): the fixed ASCII range table, i.e.
    psh's historical behaviour. UTF-8 mode: the host libc's ``iswctype``
    membership swept into explicit ``\\U`` ranges, lazily and cached per
    (locale, class).
    """
    loc = active_locale()
    if loc is None or loc.profile.ctype_mode is not LocaleMode.UTF8:
        from ..expansion.glob import _POSIX_CLASSES
        return _POSIX_CLASSES.get(name)
    key = (loc.profile.ctype_name, name)
    if key not in _RANGE_CACHE:
        member = _class_member_fn(name)
        _RANGE_CACHE[key] = _sweep_ranges(member) if member is not None else None
    return _RANGE_CACHE[key]


_ASCII_CLASS_RE: Dict[str, Optional["re.Pattern[str]"]] = {}


def _ascii_in_class(ch: str, name: str) -> bool:
    """C/OTHER-mode single-char membership, exact to the ASCII class table."""
    if name not in _ASCII_CLASS_RE:
        from ..expansion.glob import _POSIX_CLASSES
        body = _POSIX_CLASSES.get(name)
        _ASCII_CLASS_RE[name] = re.compile(f"[{body}]") if body else None
    pat = _ASCII_CLASS_RE[name]
    return bool(pat.match(ch)) if pat is not None else False
