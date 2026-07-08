"""The option registry is the single source of truth for shell options.

Pins the registry against the values that were previously scattered across
state.py (defaults + $- letters), SetBuiltin.short_to_long, and
ShoptBuiltin.SHOPT_OPTIONS, plus the new ShellOptions container behavior
(dict-compatible, rejects unknown names). A drift-lock test enumerates the
known option set so adding/removing an option is a deliberate registry edit.
"""

import pathlib

import pytest

from psh.core.option_registry import (
    OPTION_REGISTRY,
    SHOPT_OPTION_NAMES,
    SHORT_TO_LONG,
    OptionCategory,
    ShellOptions,
    default_options,
)

# The complete option set (drift lock). Adding/removing an option is a
# deliberate edit here AND in the registry.
EXPECTED_OPTIONS = {
    # debug
    "debug-ast", "debug-tokens", "debug-scopes", "debug-expansion",
    "debug-expansion-detail", "debug-exec", "debug-exec-fork",
    # set -o / short-flag
    "strict-errors", "errexit", "nounset", "xtrace", "allexport", "notify",
    "noclobber", "noglob", "hashcmds", "monitor", "noexec", "verbose",
    "errtrace", "functrace",
    "pipefail", "ignoreeof", "nolog", "posix", "braceexpand",
    "histexpand", "history", "emacs", "vi",
    # shopt
    "dotglob", "nullglob", "failglob", "extglob", "nocaseglob", "nocasematch",
    "globstar", "globasciiranges", "inherit_errexit", "checkhash",
    "expand_aliases",
    # internal (shell-set)
    "interactive", "stdin_mode", "command_mode",
}

# Non-False defaults (everything else defaults to False).
EXPECTED_NON_FALSE_DEFAULTS = {
    "hashcmds": True, "braceexpand": True, "histexpand": True, "history": True,
    "expand_aliases": True, "stdin_mode": True,
    "globasciiranges": True,  # bash 5 default ON
}


def test_registry_option_set_is_exactly_expected():
    assert set(OPTION_REGISTRY) == EXPECTED_OPTIONS


def test_defaults_match_history():
    defaults = default_options()
    assert set(defaults) == EXPECTED_OPTIONS
    for name, value in defaults.items():
        assert value == EXPECTED_NON_FALSE_DEFAULTS.get(name, False), name


def test_short_to_long_map():
    assert SHORT_TO_LONG == {
        "a": "allexport", "b": "notify", "C": "noclobber", "e": "errexit",
        "E": "errtrace", "f": "noglob", "h": "hashcmds", "m": "monitor",
        "n": "noexec", "T": "functrace",
        "u": "nounset", "v": "verbose", "x": "xtrace",
    }


def test_shopt_option_names():
    assert set(SHOPT_OPTION_NAMES) == {
        "dotglob", "nullglob", "failglob", "extglob", "nocaseglob",
        "nocasematch", "globstar", "globasciiranges", "inherit_errexit",
        "checkhash", "expand_aliases",
    }


# ---------------------------------------------------------------------------
# Consumer meta-test (core-state appraisal H4): every user-facing option must
# either be READ somewhere for behavior, or be an explicitly-listed
# presentation-only name. This is the guard that would have caught the inert
# `collect_errors` / phantom `parser-mode` options (retired in Phase 4) — and
# fails when a NEW option is registered without a consumer.
# ---------------------------------------------------------------------------

# Files that mention option names generically (the registry itself, the
# set/shopt/export builtins, the parser-config front-end, the generic option
# handler, help/debug/constants glue). A reference in ONLY these does not count
# as a behavioral consumer.
_PLUMBING = {
    "option_registry.py", "environment.py", "parser_control.py", "options.py",
    "help_command.py", "debug_control.py", "constants.py",
}

# SET/SHOPT options that are deliberately listable/settable but have no
# behavioral consumer today. Each MUST carry a reason.
_PRESENTATION_ONLY = {
    # ON by default already matches how psh interprets bracket ranges
    # (ASCII/codepoint); the OFF collation-range behaviour is a documented
    # locale deferral (see the spec notes + locale_service_design).
    "globasciiranges",
    # bash lists `nolog` (suppress function defs in history); psh keeps it
    # `set -o`-listable for bash-compat but does not implement the logging
    # suppression (cosmetic).
    "nolog",
    # KNOWN GAP (tracked follow-up): the brace expander does not yet consult
    # this toggle, so `set +o braceexpand` is currently a no-op. NOT truly
    # presentation-only — listed here so this meta-test stays honest until the
    # expansion subsystem wires the option in.
    "braceexpand",
}


def _psh_sources():
    root = pathlib.Path(__file__).resolve().parents[3] / "psh"
    return list(root.rglob("*.py"))


def _has_behavioral_consumer(name: str) -> bool:
    needles = (f"'{name}'", f'"{name}"')
    for path in _psh_sources():
        if path.name in _PLUMBING:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(n in text for n in needles):
            return True
    return False


def test_every_set_shopt_option_has_a_consumer_or_is_presentation_only():
    """No inert options: a SET/SHOPT option is read for behavior or allowlisted.

    (DEBUG options are consumed through the debug plumbing and INTERNAL ones
    are shell-set, so only the user-behavioral categories are enforced here.)"""
    behavioral = {OptionCategory.SET, OptionCategory.SHOPT}
    inert = []
    for name, spec in OPTION_REGISTRY.items():
        if spec.category not in behavioral:
            continue
        if name in _PRESENTATION_ONLY:
            continue
        if not _has_behavioral_consumer(name):
            inert.append(name)
    assert not inert, (
        f"registered option(s) with no behavioral consumer and not in "
        f"_PRESENTATION_ONLY: {inert}. Add a consumer, or (if intentionally "
        f"cosmetic) add the name to _PRESENTATION_ONLY with a reason.")


def test_presentation_only_allowlist_stays_minimal():
    """Every allowlisted name must still be a registered option (so the
    allowlist can't rot after an option is retired)."""
    for name in _PRESENTATION_ONLY:
        assert name in OPTION_REGISTRY, f"stale _PRESENTATION_ONLY entry: {name}"


def test_command_mode_is_declared():
    """command_mode was set ad-hoc in __main__.py; it is now a real option."""
    assert "command_mode" in OPTION_REGISTRY
    assert OPTION_REGISTRY["command_mode"].category is OptionCategory.INTERNAL
    assert OPTION_REGISTRY["command_mode"].dollar_dash == "c"


# ---------------------------------------------------------------------------
# ShellOptions container
# ---------------------------------------------------------------------------

def test_shell_options_is_dict_compatible():
    opts = ShellOptions()
    assert opts["errexit"] is False
    assert opts.get("errexit") is False
    assert opts.get("nope-missing", "dflt") == "dflt"
    assert "errexit" in opts
    assert "nope-missing" not in opts
    opts["errexit"] = True
    assert opts["errexit"] is True
    assert ("errexit", True) in opts.items()
    assert len(opts) == len(EXPECTED_OPTIONS)


def test_shell_options_overrides():
    opts = ShellOptions(overrides={"xtrace": True, "pipefail": True})
    assert opts["xtrace"] is True
    assert opts["pipefail"] is True
    assert opts["errexit"] is False  # untouched default


def test_shell_options_rejects_unknown_name_on_write():
    opts = ShellOptions()
    with pytest.raises(KeyError):
        opts["definitely-not-an-option"] = True
    with pytest.raises(KeyError):
        ShellOptions(overrides={"typo": True})


def test_shell_options_enforces_value_type():
    """A bool option rejects a non-bool write (core-state appraisal H4).

    `opts['errexit'] = 'false'` was silently accepted and read as truthy;
    `= 1` likewise. Both are now TypeErrors — the value must match the
    registered ``value_type``."""
    opts = ShellOptions()
    with pytest.raises(TypeError):
        opts["errexit"] = "false"
    with pytest.raises(TypeError):
        opts["errexit"] = 1           # bool is an int subclass; 1 is not a bool
    with pytest.raises(TypeError):
        opts["errexit"] = None
    # A genuine bool is accepted.
    opts["errexit"] = True
    assert opts["errexit"] is True


def test_shell_options_prohibits_deletion():
    """Registry keys are permanent — deleting one would make a typed accessor
    raise KeyError on the next read (core-state appraisal H4)."""
    opts = ShellOptions()
    with pytest.raises(TypeError):
        del opts["errexit"]
    with pytest.raises(TypeError):
        opts.pop("errexit")           # pop routes through __delitem__
    assert "errexit" in opts          # still present


def test_shell_options_update_validates():
    opts = ShellOptions()
    opts.update({"errexit": True, "nounset": True})
    assert opts["errexit"] and opts["nounset"]
    with pytest.raises(KeyError):
        opts.update({"bogus": True})


def test_typed_accessors():
    opts = ShellOptions()
    assert opts.errexit is False and opts.pipefail is False
    opts["errexit"] = True
    opts["pipefail"] = True
    assert opts.errexit is True and opts.pipefail is True


# ---------------------------------------------------------------------------
# $- string ($- order is bash-pinned)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("set_names,expected", [
    ([], ""),
    (["hashcmds", "braceexpand"], "hB"),
    (["errexit", "hashcmds", "braceexpand"], "ehB"),
    (["allexport", "errexit", "noglob", "hashcmds", "nounset", "verbose",
      "xtrace", "braceexpand"], "aefhuvxB"),
    # invocation flags c/s come last
    (["hashcmds", "braceexpand", "command_mode"], "hBc"),
    (["hashcmds", "braceexpand", "stdin_mode"], "hBs"),
    (["interactive", "hashcmds", "braceexpand", "histexpand", "command_mode"],
     "hiBHc"),
])
def test_option_string_order(set_names, expected):
    opts = ShellOptions()
    # Clear the True-by-default letters that would otherwise appear.
    for name in ("hashcmds", "braceexpand", "histexpand", "stdin_mode"):
        opts[name] = False
    for name in set_names:
        opts[name] = True
    assert opts.option_string() == expected
