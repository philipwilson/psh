"""The single source of truth for shell options.

Before this module, "what options exist and how each behaves" was duplicated
across four places: the defaults dict in ``state.py``, the ``$-`` letter map in
``ShellState.get_option_string()``, ``SetBuiltin.short_to_long``, and
``ShoptBuiltin.SHOPT_OPTIONS``. ``OPTION_REGISTRY`` here is now the one
declaration; those maps are derived from it.

Shell options are a *dynamic, string-keyed* surface — ``set -o $name``,
``shopt $name`` and ``$-`` index options by a runtime name, and several names
(``debug-ast``, ``strict-errors``, ``parser-mode``) are not valid Python
identifiers. So options are NOT a flat dataclass (unlike ``ExecutionState`` &c).
Instead ``ShellState.options`` is a :class:`ShellOptions` — a registry-backed,
dict-compatible container that validates names on write — so the ~280 existing
``state.options[...]`` / ``.get(...)`` call sites are unchanged while the surface
gains a typed, single-source registry.
"""
from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Iterator, Mapping, Optional, Union

OptionValue = Union[bool, str]


class OptionCategory(Enum):
    """Where an option lives in the user-facing surface.

    Informational/organizational — it does NOT restrict ``set -o`` (psh's
    ``set -o`` accepts any registered name, a deliberate superset of bash's
    set-vs-shopt split; preserved here).
    """
    SET = auto()       # set -o / short flag (errexit, xtrace, ...)
    SHOPT = auto()     # shopt -s/-u (extglob, globstar, ...)
    DEBUG = auto()     # debug-ast, debug-tokens, ...
    INTERNAL = auto()  # set by the shell itself (interactive, stdin_mode, ...)


@dataclass(frozen=True)
class OptionSpec:
    """Everything known about one shell option."""
    name: str
    default: OptionValue
    category: OptionCategory
    value_type: type = bool
    short_flag: Optional[str] = None    # toggled by `set -<flag>` (a, e, x, ...)
    dollar_dash: Optional[str] = None   # letter shown in $- (often == short_flag)
    notes: str = ""


def _spec(name, default, category, **kw) -> OptionSpec:
    return OptionSpec(name=name, default=default, category=category, **kw)


# --- The registry -----------------------------------------------------------
# Order here is for readability only; $- order is fixed by DOLLAR_DASH_ORDER.
_SPECS = [
    # Debug options (CLI --debug-* / set -o; no $- letter).
    _spec("debug-ast", False, OptionCategory.DEBUG),
    _spec("debug-tokens", False, OptionCategory.DEBUG),
    _spec("debug-scopes", False, OptionCategory.DEBUG),
    _spec("debug-expansion", False, OptionCategory.DEBUG),
    _spec("debug-expansion-detail", False, OptionCategory.DEBUG),
    _spec("debug-exec", False, OptionCategory.DEBUG),
    _spec("debug-exec-fork", False, OptionCategory.DEBUG),
    # Re-raise unexpected internal exceptions (seeded from PSH_STRICT_ERRORS by
    # ShellState; toggle with set -o strict-errors).
    _spec("strict-errors", False, OptionCategory.SET),
    # POSIX set options with short flags.
    _spec("errexit", False, OptionCategory.SET, short_flag="e", dollar_dash="e"),
    _spec("nounset", False, OptionCategory.SET, short_flag="u", dollar_dash="u"),
    _spec("xtrace", False, OptionCategory.SET, short_flag="x", dollar_dash="x"),
    _spec("allexport", False, OptionCategory.SET, short_flag="a", dollar_dash="a"),
    _spec("notify", False, OptionCategory.SET, short_flag="b", dollar_dash="b"),
    _spec("noclobber", False, OptionCategory.SET, short_flag="C", dollar_dash="C"),
    _spec("noglob", False, OptionCategory.SET, short_flag="f", dollar_dash="f"),
    _spec("hashcmds", True, OptionCategory.SET, short_flag="h", dollar_dash="h"),
    _spec("monitor", False, OptionCategory.SET, short_flag="m", dollar_dash="m"),
    _spec("noexec", False, OptionCategory.SET, short_flag="n", dollar_dash="n"),
    _spec("verbose", False, OptionCategory.SET, short_flag="v", dollar_dash="v"),
    # Trap inheritance into functions/subshells: errtrace (-E) propagates the
    # ERR trap, functrace (-T) the DEBUG and RETURN traps. Off by default —
    # bash does NOT run those traps inside a function body unless these are set.
    _spec("errtrace", False, OptionCategory.SET, short_flag="E", dollar_dash="E"),
    _spec("functrace", False, OptionCategory.SET, short_flag="T", dollar_dash="T"),
    # set -o options without a short flag.
    _spec("pipefail", False, OptionCategory.SET),
    _spec("ignoreeof", False, OptionCategory.SET),
    _spec("nolog", False, OptionCategory.SET),
    _spec("posix", False, OptionCategory.SET),
    _spec("braceexpand", True, OptionCategory.SET, dollar_dash="B"),
    _spec("histexpand", True, OptionCategory.SET, dollar_dash="H"),
    _spec("history", True, OptionCategory.SET),
    _spec("emacs", False, OptionCategory.SET),
    _spec("vi", False, OptionCategory.SET),
    # shopt-managed bash-compat options.
    _spec("dotglob", False, OptionCategory.SHOPT),
    _spec("nullglob", False, OptionCategory.SHOPT),
    _spec("failglob", False, OptionCategory.SHOPT),
    _spec("extglob", False, OptionCategory.SHOPT),
    _spec("nocaseglob", False, OptionCategory.SHOPT),
    _spec("nocasematch", False, OptionCategory.SHOPT),
    _spec("globstar", False, OptionCategory.SHOPT),
    _spec("globasciiranges", True, OptionCategory.SHOPT,
          notes="ON by default (bash 5): bracket RANGES like [a-z] use "
                "ASCII/codepoint bounds regardless of locale, which is already "
                "how psh interprets ranges. Registered so `shopt "
                "globasciiranges` stops erroring; the OFF (collation-range) "
                "behaviour is a documented deferral, see locale_service_design"),
    _spec("inherit_errexit", False, OptionCategory.SHOPT,
          notes="command-substitution children keep set -e instead of "
                "clearing it (bash 4.4+; POSIX mode also keeps it)"),
    _spec("checkhash", False, OptionCategory.SHOPT),
    _spec("expand_aliases", True, OptionCategory.SHOPT,
          notes="gates alias expansion (Shell.expand_aliases). ON by default in "
                "every mode (bash: OFF non-interactively); shopt -u disables it "
                "for subsequently-parsed commands"),
    # Set by the shell itself; shown in $- but not user-toggled by name.
    _spec("interactive", False, OptionCategory.INTERNAL, dollar_dash="i"),
    _spec("stdin_mode", True, OptionCategory.INTERNAL, dollar_dash="s"),
    _spec("command_mode", False, OptionCategory.INTERNAL, dollar_dash="c"),
]

OPTION_REGISTRY: Dict[str, OptionSpec] = {s.name: s for s in _SPECS}

# Short flag (set -<flag>) -> long option name.
SHORT_TO_LONG: Dict[str, str] = {
    s.short_flag: s.name for s in _SPECS if s.short_flag is not None
}

# shopt-managed option names.
SHOPT_OPTION_NAMES = tuple(
    s.name for s in _SPECS if s.category is OptionCategory.SHOPT
)

# $- letter order, bash-pinned: lowercase set flags, then uppercase, then the
# invocation flags c/s last (see ShellOptions.option_string).
DOLLAR_DASH_ORDER = ("a", "b", "e", "f", "h", "i", "m", "n", "u", "v", "x",
                     "B", "C", "E", "H", "T", "c", "s")
_DOLLAR_LETTER_TO_NAME: Dict[str, str] = {
    s.dollar_dash: s.name for s in _SPECS if s.dollar_dash is not None
}


def default_options() -> Dict[str, OptionValue]:
    """A fresh {name: default} dict from the registry."""
    return {s.name: s.default for s in _SPECS}


class ShellOptions(MutableMapping):
    """Registry-backed, dict-compatible shell-option store.

    Behaves like the old plain ``dict`` (``opts['errexit']``, ``opts.get(...)``,
    ``in``, ``update``, ``items``) so existing call sites are untouched, but
    every write is validated against :data:`OPTION_REGISTRY`, so a typo'd
    option name fails loudly instead of silently creating a junk key.
    """

    __slots__ = ("_values",)

    def __init__(self, overrides: Optional[Mapping[str, OptionValue]] = None):
        self._values: Dict[str, OptionValue] = default_options()
        if overrides:
            for name, value in overrides.items():
                self[name] = value

    def __getitem__(self, name: str) -> OptionValue:
        return self._values[name]

    def __setitem__(self, name: str, value: OptionValue) -> None:
        spec = OPTION_REGISTRY.get(name)
        if spec is None:
            raise KeyError(
                f"unknown shell option {name!r} (not in OPTION_REGISTRY)")
        # Enforce the declared value type (core-state appraisal H4). A bool
        # option must receive a real bool — `opts['errexit'] = 'false'` or
        # `= 1` is a caller bug, not a truthy value. (bool is an int subclass,
        # so isinstance(1, bool) is False, correctly rejecting int writes.)
        if not isinstance(value, spec.value_type):
            raise TypeError(
                f"shell option {name!r} expects {spec.value_type.__name__}, "
                f"got {type(value).__name__} {value!r}")
        self._values[name] = value

    def __delitem__(self, name: str) -> None:
        # Registry keys are permanent: deleting one would make a typed accessor
        # raise KeyError on the next read (core-state appraisal H4). Toggle the
        # value instead of removing the key.
        raise TypeError(
            f"shell option {name!r} cannot be deleted (toggle its value)")

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return f"ShellOptions({self._values!r})"

    # Typed convenience accessors for the hottest internal reads. Additive —
    # the dict-style API above remains the general interface.
    @property
    def errexit(self) -> bool:
        return bool(self._values["errexit"])

    @property
    def nounset(self) -> bool:
        return bool(self._values["nounset"])

    @property
    def xtrace(self) -> bool:
        return bool(self._values["xtrace"])

    @property
    def pipefail(self) -> bool:
        return bool(self._values["pipefail"])

    @property
    def interactive(self) -> bool:
        return bool(self._values["interactive"])

    def option_string(self) -> str:
        """The ``$-`` flag string: set single-letter options in bash's order.

        Lowercase set flags, then uppercase, then the invocation flags c/s
        last (bash 5.x: ``set -aefuvx`` -> ``aefhuvxBc``). Verified against
        bash in tests/unit/test_dash_i_and_dollar_dash.py.
        """
        out = []
        for letter in DOLLAR_DASH_ORDER:
            name = _DOLLAR_LETTER_TO_NAME.get(letter)
            if name is not None and self._values.get(name):
                out.append(letter)
        return "".join(out)
