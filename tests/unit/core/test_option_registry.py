"""The option registry is the single source of truth for shell options.

Pins the registry against the values that were previously scattered across
state.py (defaults + $- letters), SetBuiltin.short_to_long, and
ShoptBuiltin.SHOPT_OPTIONS, plus the new ShellOptions container behavior
(dict-compatible, rejects unknown names). A drift-lock test enumerates the
known option set so adding/removing an option is a deliberate registry edit.
"""

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
    "pipefail", "ignoreeof", "nolog", "posix", "collect_errors", "braceexpand",
    "histexpand", "history", "emacs", "vi", "parser-mode",
    # shopt
    "dotglob", "nullglob", "failglob", "extglob", "nocaseglob", "nocasematch",
    "globstar", "checkhash", "expand_aliases",
    # internal (shell-set)
    "interactive", "stdin_mode", "command_mode",
}

# Non-False defaults (everything else defaults to False).
EXPECTED_NON_FALSE_DEFAULTS = {
    "hashcmds": True, "braceexpand": True, "histexpand": True, "history": True,
    "expand_aliases": True, "stdin_mode": True, "parser-mode": "balanced",
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
        "nocasematch", "globstar", "checkhash", "expand_aliases",
    }


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
    opts = ShellOptions(overrides={"xtrace": True, "parser-mode": "performance"})
    assert opts["xtrace"] is True
    assert opts["parser-mode"] == "performance"
    assert opts["errexit"] is False  # untouched default


def test_shell_options_rejects_unknown_name_on_write():
    opts = ShellOptions()
    with pytest.raises(KeyError):
        opts["definitely-not-an-option"] = True
    with pytest.raises(KeyError):
        ShellOptions(overrides={"typo": True})


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
