"""Shell options builtin (shopt)."""

from typing import TYPE_CHECKING, List, Optional

from ..core.option_registry import SET_O_OPTION_NAMES, SHOPT_OPTION_NAMES
from .base import Builtin
from .environment import apply_set_o_option
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell

_SET_O_NAMES = frozenset(SET_O_OPTION_NAMES)
_SHOPT_NAMES = frozenset(SHOPT_OPTION_NAMES)

_USAGE = "shopt: usage: shopt [-pqsu] [-o] [optname ...]"

# One-line help blurbs for the shopt-managed options. The `help` property
# renders the "Available options" list by walking SHOPT_OPTION_NAMES (the
# registry is the single source of truth for WHICH options exist), so a new
# `_spec(..., OptionCategory.SHOPT)` shows up in help automatically; only its
# blurb is looked up here (missing = the name alone, never a stale/omitted
# option). `tests/unit/builtins/test_shopt.py` pins that every registry name
# has a blurb, so the two cannot silently drift.
_SHOPT_DESCRIPTIONS = {
    "dotglob": "Glob patterns match files beginning with '.'",
    "nullglob": "Patterns with no matches expand to nothing",
    "failglob": "Patterns with no matches fail the command",
    "extglob": "Extended pattern matching: ?()|*()|+()|@()|!()",
    "nocaseglob": "Case-insensitive pathname expansion",
    "nocasematch": "Case-insensitive matching in [[ ]] (==/!=/=~) and case",
    "globstar": "'**' matches all files and directories recursively",
    "globasciiranges": "Bracket ranges like [a-z] use ASCII/codepoint bounds",
    "inherit_errexit": "Command substitutions inherit 'set -e'",
    "checkhash": "Re-verify hashed command paths before executing them",
    "expand_aliases": "Expand aliases (on by default in every mode)",
    "huponexit": "SIGHUP running jobs when an interactive shell exits",
}


@builtin
class ShoptBuiltin(Builtin):
    """Set and unset shell options."""

    @property
    def name(self) -> str:
        return "shopt"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        # Flag grammar, probe-pinned against bash 5.2 (internal_getopt over
        # "psuoq"): flags cluster in any combination and order (-so, -os,
        # -sq, -pso ...); parsing stops at the FIRST non-flag argument, so a
        # later `-s` is an OPERAND (`shopt extglob -s` queries extglob then
        # errors "-s: invalid shell option name"); `--` ends flags; only
        # -s with -u is rejected ("cannot set and unset ...", exit 1); a bad
        # flag char is "shopt: -x: invalid option" + a usage line, exit 2.
        set_flag = unset_flag = print_flag = quiet_flag = o_flag = False
        option_names: List[str] = []

        i = 1
        while i < len(args):
            arg = args[i]
            if arg == '--':
                option_names.extend(args[i + 1:])
                break
            if arg.startswith('-') and len(arg) > 1:
                for ch in arg[1:]:
                    if ch == 's':
                        set_flag = True
                    elif ch == 'u':
                        unset_flag = True
                    elif ch == 'p':
                        print_flag = True
                    elif ch == 'q':
                        quiet_flag = True
                    elif ch == 'o':
                        o_flag = True
                    else:
                        self.error(f"-{ch}: invalid option", shell)
                        self.write_error_line(_USAGE, shell)
                        return 2
            else:
                option_names.extend(args[i:])
                break
            i += 1

        if set_flag and unset_flag:
            self.error(
                "cannot set and unset shell options simultaneously", shell)
            return 1

        # With -o, shopt operates on the SET-O option table: set/unset are
        # exactly `set -o/+o NAME`, and -p prints reusable `set -o NAME`
        # lines (bash keeps `shopt -o` == `set -o` and `shopt -po` == `set
        # +o` — probe: both diffs are empty).
        if option_names:
            if set_flag or unset_flag:
                return self._toggle(option_names, set_flag, o_flag, shell)
            return self._query(option_names, o_flag, quiet_flag,
                               print_flag, shell)

        # No operands: list (filtered to the enabled/disabled subset under
        # -s/-u); -q lists nothing and reports success.
        if quiet_flag:
            return 0
        state_filter: Optional[bool] = None
        if set_flag or unset_flag:
            state_filter = set_flag
        self._list(shell, o_flag, reusable=print_flag,
                   state_filter=state_filter)
        return 0

    # -- modes --------------------------------------------------------------

    def _toggle(self, names: List[str], enable: bool, o_mode: bool,
                shell: 'Shell') -> int:
        """Set (-s) or unset (-u) each named option.

        Exit status, probe-pinned: the shopt-table path reports an unknown
        name and returns 1; the -o path reports it but still returns 0 (a
        bash quirk — `shopt -so nosuch; echo $?` prints 0). Valid names in
        the same command are applied either way.
        """
        status = 0
        for name in names:
            if o_mode:
                if name in _SET_O_NAMES:
                    apply_set_o_option(shell, name, enable)
                else:
                    self.error(f"{name}: invalid option name", shell)
            elif name in _SHOPT_NAMES:
                shell.state.options[name] = enable
            else:
                self.error(f"{name}: invalid shell option name", shell)
                status = 1
        return status

    def _query(self, names: List[str], o_mode: bool, quiet: bool,
               reusable: bool, shell: 'Shell') -> int:
        """Show (or, with -q, just test) the state of each named option.

        Exit status (bash): 0 if every named option is set, 1 if any is
        unset or unknown. This makes ``shopt nocasematch`` /
        ``shopt -qo errexit`` usable as state tests. -q suppresses output
        even when combined with -p.
        """
        status = 0
        for name in names:
            if o_mode:
                known = name in _SET_O_NAMES
                key = name
            else:
                known = name in _SHOPT_NAMES
                key = name
            if not known:
                kind = ("invalid option name" if o_mode
                        else "invalid shell option name")
                self.error(f"{name}: {kind}", shell)
                status = 1
                continue
            enabled = bool(shell.state.options.get(key, False))
            if not enabled:
                status = 1
            if not quiet:
                self._print_option(name, enabled, shell, reusable, o_mode)
        return status

    def _list(self, shell: 'Shell', o_mode: bool, reusable: bool,
              state_filter: Optional[bool]) -> None:
        """List options (all, or only the enabled/disabled subset)."""
        names = SET_O_OPTION_NAMES if o_mode else tuple(sorted(SHOPT_OPTION_NAMES))
        for name in names:
            key = name
            enabled = bool(shell.state.options.get(key, False))
            if state_filter is not None and enabled is not state_filter:
                continue
            self._print_option(name, enabled, shell, reusable, o_mode)

    def _print_option(self, name: str, enabled: bool, shell: 'Shell',
                      reusable: bool, o_mode: bool = False) -> None:
        """Print a single option's status."""
        if reusable:
            if o_mode:
                # Reusable via `set` (bash: shopt -po emits set-style lines).
                flag = '-o' if enabled else '+o'
                self.write_line(f"set {flag} {name}", shell)
            else:
                flag = '-s' if enabled else '-u'
                self.write_line(f"shopt {flag} {name}", shell)
        else:
            # bash left-justifies the option name in a 15-char field, then a
            # tab, then on/off (a name >= 15 chars is not padded — f-string
            # width never truncates, matching bash).
            status = 'on' if enabled else 'off'
            self.write_line(f"{name:<15}\t{status}", shell)

    @property
    def help(self) -> str:
        # The "Available options" list is DERIVED from SHOPT_OPTION_NAMES so it
        # can never drift from the registry (the old hand-kept list documented
        # 8 of 11). Blurbs come from _SHOPT_DESCRIPTIONS.
        available = "\n".join(
            f"      {name:<16}{_SHOPT_DESCRIPTIONS.get(name, '')}".rstrip()
            for name in SHOPT_OPTION_NAMES)
        return f"""shopt: shopt [-pqsu] [-o] [optname ...]

    Toggle shell optional behavior.

    Options:
      -s    Set (enable) each optname (bare: list the enabled options)
      -u    Unset (disable) each optname (bare: list the disabled options)
      -p    Print in reusable form (shopt -s/-u optname)
      -q    Query silently; exit code indicates status
      -o    Operate on the `set -o` option table instead: set/unset are
            exactly `set -o/+o optname`, -p prints reusable `set -o` lines,
            and $SHELLOPTS reflects the same table

    Without options, list all settable options with their status.
    With optname but no flags, show the status of those options.

    Available options:
{available}"""
