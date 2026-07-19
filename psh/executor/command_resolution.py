"""Typed command-word normalization, prefix-assignment overlay, and the one
command-resolution result (boundary campaign R3, closes #20 H10).

Reappraisal #20 H10 is the *recompute-from-raw-names* class: the executor
decided a command's scope model (function temp-env SCOPE vs command temp-env
LAYER), its ``exec`` special case, and its POSIX prefix-error branch from raw
``function_manager.get_function`` / ``cmd_name in POSIX_SPECIAL_BUILTINS`` reads
taken BEFORE the actual mode-aware resolution ran — so a POSIX-mode special
builtin shadowed by a same-named function (``eval(){:;}; set -o posix;
X=v eval :``) took the function path and dropped an assignment that must persist.

The fix is authority timing (campaign §2.2): normalize the command word, build
the prefix overlay, then resolve ONCE into a :class:`ResolvedCommand`, and drive
every downstream decision from that value — never from a fresh raw-name read.

Three campaign contract types (§5):

- :class:`NormalizedCommandName` — the post-quote-removal command word plus
  bypass provenance. It cannot consume a resolution; it is produced first.
- :class:`CommandEnvOverlay` — the immutable typed view of the command's
  effective environment (the expanded prefix assignments; the PATH the command
  resolves against). It never mutates live scope.
- :class:`ResolvedCommand` — the single dispatch answer: kind, strategy, POSIX
  status, prefix-assignment persistence, ``exec`` policy, temp-env-scope policy.

``resolve_command`` is the SOLE reader of the function/builtin registries for a
dispatch decision; the v0.660 :class:`~psh.executor.command_resolver.CommandResolver`
remains the sole reader of the command hash and PATH, and the external strategy
consults :attr:`CommandEnvOverlay.effective_path` when it performs that search.
A static ratchet (``tests/unit/tooling/test_command_resolution_ratchet_r3.py``)
fails on a raw dispatch read reintroduced into ``command.py`` outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple

from .strategies import (
    BuiltinExecutionStrategy,
    ExecutionStrategy,
    FunctionExecutionStrategy,
    SpecialBuiltinExecutionStrategy,
)

if TYPE_CHECKING:
    from ..shell import Shell


class DispatchKind(Enum):
    """What a resolved command dispatches to, in the executor's strategy terms.

    This is the *execution* classification (which strategy runs the command),
    the mode-aware winner of function/special-builtin/regular-builtin/external
    lookup. It parallels — but is distinct from — the introspection-oriented
    ``CommandResolver.CandidateKind`` (which also models aliases and keywords,
    resolved earlier at the lex/parse boundary and never reaching this path).
    """

    FUNCTION = "function"
    SPECIAL_BUILTIN = "special_builtin"
    BUILTIN = "builtin"
    EXTERNAL = "external"


@dataclass(frozen=True)
class NormalizedCommandName:
    """A command word after quote removal, with its bypass provenance.

    ``text``
        The command name the resolver looks up (``expanded_args[0]`` — already
        quote-removed and, for a ``\\cmd`` spelling, backslash-stripped).
    ``backslash_bypass``
        True when the source word carried a leading backslash (``\\ls``,
        ``\\export``). A quote on the command word: it suppressed ALIAS
        expansion upstream (the token never matched an alias name) and, after
        quote removal, makes the word ineligible as a declaration builtin
        (``\\export foo=$x`` word-splits its value). It does NOT suppress
        function or builtin lookup (F2), so it is provenance, not a dispatch
        input.
    ``has_slash``
        True when the name contains ``/`` (a pathname, taken as given — never a
        function/builtin/hash lookup, and PATH search returns it verbatim).
    """

    text: str
    backslash_bypass: bool = False
    has_slash: bool = False


def normalize_command_word(text: str, *,
                           backslash_bypass: bool = False) -> NormalizedCommandName:
    """Build the :class:`NormalizedCommandName` for an expanded command word."""
    return NormalizedCommandName(
        text=text,
        backslash_bypass=backslash_bypass,
        has_slash='/' in text,
    )


@dataclass(frozen=True)
class CommandEnvOverlay:
    """The immutable typed view of a command's effective environment.

    Prefix assignments (``FOO=bar cmd``) are expanded left-to-right and
    installed as bash's *temporary environment* (a command temp-env LAYER for a
    builtin/external, an exported temp-env SCOPE for a function, or the seed
    path for a dynamic special / array / nameref-to-element). This value is the
    typed *view* of that environment for resolution and execution; it never
    mutates the persistent variable store (the temp-env stack the layer lives on
    is explicitly not the lexical scope stack — R2).

    ``assignment_names``
        The names the prefix assigns, in source order (metadata available BEFORE
        the values are installed — resolution never needs the values, only
        whether a PATH override is present).
    ``has_path_override``
        True when one of the prefix assignments is ``PATH=...``; then the
        command resolves against the temporary PATH rather than the shell's.
    """

    assignment_names: Tuple[str, ...] = ()
    has_path_override: bool = False

    def effective_path(self, shell: 'Shell') -> str:
        """The PATH the command resolves against.

        Read at resolution/search time: with a ``PATH=`` prefix installed, the
        live environment already reflects the temporary PATH (the prefix layer
        materialises into ``state.env`` through the exported-variable observer),
        so this is that temporary PATH; otherwise it is the shell's PATH. This
        is the value the external strategy's ``CommandResolver`` search uses, so
        ``PATH=/only cmd`` resolves against ``/only`` and a stale hash entry the
        temporary PATH excludes is rejected — the behavior the resolver already
        gets right, now named as the overlay's projection.
        """
        return shell.env.get('PATH', '')


# The overlay for a command with no prefix assignments — the hot-path default.
EMPTY_OVERLAY = CommandEnvOverlay()


@dataclass(frozen=True)
class ResolvedCommand:
    """The single result of resolving a command word to how it dispatches.

    Every dispatch decision the transaction needs is a NAMED field here, decided
    once by :func:`resolve_command`. The executor drives scope creation,
    the ``exec`` shortcut, the POSIX prefix-error branch, and prefix-assignment
    teardown from these fields rather than re-reading the registries (H10).

    ``dispatch_kind`` / ``strategy``
        The mode-aware winner and the strategy instance that runs it.
    ``is_posix_special``
        The resolved command is a POSIX special builtin (``:`` ``.`` ``eval``
        ``exec`` ``export`` ``readonly`` ``set`` ``unset`` …).
    ``assignments_persist``
        Prefix assignments persist in the current shell rather than being
        restored — True only for a POSIX special builtin resolved in POSIX mode.
    ``uses_temp_env_scope``
        The command is a shell FUNCTION, so its prefix assignments layer as an
        exported temp-env SCOPE (visible to and enumerated by the body) rather
        than a command temp-env layer. Drives ``push_temp_env_scope``.
    ``is_exec_special``
        The command resolves to the ``exec`` special builtin (not a same-named
        function that shadowed it), so the executor's ``exec`` redirection path
        applies. In default mode a function ``exec`` wins and this is False; in
        POSIX mode the special builtin wins even over the function.
    """

    dispatch_kind: DispatchKind
    strategy: 'ExecutionStrategy'
    is_posix_special: bool
    assignments_persist: bool
    uses_temp_env_scope: bool
    is_exec_special: bool


def _kind_for_strategy(strategy: 'ExecutionStrategy') -> DispatchKind:
    if isinstance(strategy, FunctionExecutionStrategy):
        return DispatchKind.FUNCTION
    if isinstance(strategy, SpecialBuiltinExecutionStrategy):
        return DispatchKind.SPECIAL_BUILTIN
    if isinstance(strategy, BuiltinExecutionStrategy):
        return DispatchKind.BUILTIN
    return DispatchKind.EXTERNAL


def resolve_command(shell: 'Shell',
                    strategies: Tuple['ExecutionStrategy', ...],
                    normalized: NormalizedCommandName,
                    overlay: CommandEnvOverlay,
                    context: object) -> Optional[ResolvedCommand]:
    """Resolve a normalized command word to how it dispatches — the ONE reader.

    Lookup order and prefix-assignment persistence are BOTH mode-aware, decided
    here once from ``set -o posix`` (F9):

    - Default (bash) mode: functions > (special | regular) builtins > external —
      functions shadow even special builtins; a prefix before a special builtin
      is TEMPORARY, like any builtin.
    - POSIX mode: special builtins > functions > regular builtins > external —
      special builtins take precedence over functions; a prefix before one
      PERSISTS.

    This is the SOLE place a dispatch decision reads the function/builtin
    registries (via the strategies' ``can_execute``); the raw
    ``get_function`` / ``in POSIX_SPECIAL_BUILTINS`` recomputes the executor used
    to take before resolving are gone (the H10 authority-timing inversion). The
    command hash and PATH stay with the v0.660 ``CommandResolver``, consulted by
    the external strategy against ``overlay.effective_path``.

    ``context`` and ``overlay`` are accepted for the campaign resolution
    contract; the strategy CHOICE is PATH-independent (external is the
    always-true catch-all and its PATH search is deferred to execute time), so
    resolution can and must precede prefix-assignment installation.

    Returns ``None`` only if no strategy matches (unreachable in practice — the
    external strategy is the catch-all), preserving the historical 127 fallback.
    """
    posix = shell.state.options.get('posix', False)
    ordered = strategies
    if posix:
        # POSIX lookup precedence: special builtins ahead of functions.
        special = [s for s in strategies
                   if isinstance(s, SpecialBuiltinExecutionStrategy)]
        rest = [s for s in strategies
                if not isinstance(s, SpecialBuiltinExecutionStrategy)]
        ordered = tuple(special + rest)

    cmd_name = normalized.text
    for strategy in ordered:
        if strategy.can_execute(cmd_name, shell):
            kind = _kind_for_strategy(strategy)
            is_special = kind is DispatchKind.SPECIAL_BUILTIN
            return ResolvedCommand(
                dispatch_kind=kind,
                strategy=strategy,
                is_posix_special=is_special,
                assignments_persist=posix and is_special,
                uses_temp_env_scope=kind is DispatchKind.FUNCTION,
                is_exec_special=is_special and cmd_name == 'exec',
            )
    return None
