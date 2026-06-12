"""Variable assignments attached to simple commands (``NAME=value``).

This module owns the "what does a ``NAME=value`` prefix mean" sub-domain;
`CommandExecutor` (command.py) keeps the "how is a command dispatched"
side and calls in here at four points: extract, pure-assignment shortcut,
prefix apply, and restore.

POSIX ordering contract (probe-verified against bash 5.2):

1. **Command words expand BEFORE assignments apply.** ``V=old; V=new echo
   $V`` prints ``old``: the prefix assignment is invisible to the
   command's own expansions.
2. **Assignment values expand left-to-right at apply time**, so each
   value sees the assignments to its left: ``A=1 B=$A cmd`` gives B the
   value ``1`` (likewise pure ``x=1 y=$x``).
3. **Prefix assignments are temporary.** Shell state and ``shell.env``
   are restored after the command — unless it resolved to a POSIX
   special builtin, where psh deliberately implements the POSIX
   persistence rule (``VAR=v :`` leaves VAR set; bash only does this in
   ``--posix`` mode). Whether persistence applies is the *dispatcher's*
   knowledge: CommandExecutor decides whether to call :meth:`restore`,
   and the saved-state value passes through it opaquely.
4. **A pure assignment's status is 0 unless a command substitution ran**
   while expanding words — then it is that substitution's status
   (``x=$(false)`` → 1, but ``x=$(false) true`` → 0). The clear of
   ``state.last_cmdsub_status`` stays in CommandExecutor, BEFORE
   command-word expansion, because the determining substitution can run
   while expanding command words that then vanish: ``V=v $(false)``
   takes the pure path and must report 1.
5. **Readonly errors differ by path** (bash 5.2, probe-verified): a pure
   assignment fails with status 1 and aborts a non-interactive shell; a
   prefix assignment reports the error, skips that one variable, applies
   the rest, and the command still runs — except under ``set -e``, where
   the caller makes the assignment error fatal instead.
"""

import sys
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Tuple

from ..core import (
    NamerefCycleError,
    ReadonlyVariableError,
    is_valid_assignment,
    resolve_append_assignment,
)

if TYPE_CHECKING:
    from ..ast_nodes import SimpleCommand, Word
    from ..shell import Shell

# (name, raw value, Word carrying quote structure) — value unexpanded.
RawAssignment = Tuple[str, str, Optional['Word']]


class PrefixOutcome(NamedTuple):
    """Result of applying prefix assignments before a command.

    ``saved`` is handed back to :meth:`CommandAssignments.restore` by the
    dispatcher (opaque to it); ``applied`` is the expanded (name, value)
    pairs that took effect (``exec`` without a command persists these);
    ``failed`` is True when any assignment failed (readonly) — fatal
    under ``set -e``.
    """
    saved: Dict[str, dict]
    applied: List[Tuple[str, str]]
    failed: bool


class CommandAssignments:
    """Extraction, expansion, application and restoration of
    ``NAME=value`` words on a simple command."""

    def __init__(self, shell: 'Shell'):
        self.shell = shell
        self.state = shell.state
        self.expansion_manager = shell.expansion_manager
        self.io_manager = shell.io_manager

    # ------------------------------------------------------------------
    # Extraction (pre-expansion)
    # ------------------------------------------------------------------

    def extract(self, node: 'SimpleCommand') -> List[RawAssignment]:
        """Extract the leading run of assignment words, unexpanded.

        Returns (var_name, raw_value, word_or_none) triples. The Word
        object carries the structural quote information expansion needs.
        Extraction stops at the first word that is not an assignment —
        that word is the command name.
        """
        assignments: List[RawAssignment] = []
        args = node.args  # derived from words — snapshot once
        i = 0

        while i < len(args):
            arg = args[i]

            # Use Word AST to determine if this argument is an assignment
            # candidate (i.e., a regular word, not a process substitution
            # or other special token).
            if self._is_assignment_candidate(node, i):
                if '=' in arg and is_valid_assignment(arg):
                    var, value = arg.split('=', 1)
                    assignments.append((var, value, node.words[i]))
                    i += 1
                else:
                    # Stop at first non-assignment
                    break
            else:
                # Stop if we hit a non-word type (process sub, etc.)
                break

        return assignments

    @staticmethod
    def _is_assignment_candidate(node: 'SimpleCommand', index: int) -> bool:
        """Check if the argument at index is an assignment candidate.

        An argument is an assignment candidate if its Word AST contains
        only LiteralPart and ExpansionPart nodes, AND the variable-name
        portion (before the ``=``) consists entirely of unquoted
        LiteralPart text. Quoting any part of the variable name (e.g.
        ``"FOO"=bar``) disqualifies the word as an assignment per POSIX.

        Process substitutions are ExpansionPart nodes like any other
        expansion: ``x=<(cmd)`` is an assignment (bash performs the
        substitution and assigns the /dev/fd/N path), while a word that
        STARTS with a process substitution has an ExpansionPart before any
        ``=`` and is rejected below.
        """
        from ..ast_nodes import ExpansionPart, LiteralPart
        if node.words and index < len(node.words):
            word = node.words[index]
            # First pass: reject non-word part types
            for part in word.parts:
                if not isinstance(part, (LiteralPart, ExpansionPart)):
                    return False

            # Second pass: verify the variable-name portion is unquoted.
            # Walk parts accumulating text until we find '='.  Every part
            # (or portion of a part) before the '=' must be an unquoted
            # LiteralPart — any quoted part or ExpansionPart before '='
            # means this is not an assignment word.
            for part in word.parts:
                if isinstance(part, LiteralPart):
                    if '=' in part.text:
                        # Found the '='.  If this part is quoted, the
                        # variable name includes quoted text.
                        if part.quoted:
                            return False
                        # '=' is in an unquoted literal — valid so far
                        return True
                    # Part before '=' — must be unquoted literal
                    if part.quoted:
                        return False
                elif isinstance(part, ExpansionPart):
                    # Expansion before '=' means the name isn't a plain
                    # identifier (e.g. $FOO=bar is not an assignment)
                    return False

            # No '=' found in the Word parts at all
            return True
        # Unreachable: args is DERIVED from words, so every valid index
        # has a Word. Kept as a defensive default.
        return True

    # ------------------------------------------------------------------
    # Pure assignments (no command word)
    # ------------------------------------------------------------------

    def apply_pure(self, node: 'SimpleCommand',
                   raw_assignments: List[RawAssignment]) -> int:
        """Apply pure variable assignments (no command).

        Takes raw (var, value, word) triples: each value is expanded just
        before it is applied so `A=1 B=$A` gives B the new value of A.

        The exit status is 0, unless a command substitution ran while
        expanding the values — then it is the substitution's status (the
        caller cleared ``state.last_cmdsub_status`` before any expansion;
        see the module docstring for why the clear lives there).
        """
        # Apply redirections first
        with self.io_manager.with_redirections(node.redirects):
            xtrace = self.state.options.get('xtrace')
            for var, value, value_word in raw_assignments:
                value = self._expand_value(value, value_word)
                if xtrace:
                    ps4 = self.state.get_variable('PS4', '+ ')
                    self.state.stderr.write(ps4 + f"{var}={value}\n")
                    self.state.stderr.flush()
                var, value = resolve_append_assignment(
                    self.state.scope_manager, var, value)
                try:
                    self.state.set_variable(var, value)
                except ReadonlyVariableError:
                    # bash: assignment to a readonly variable aborts a
                    # non-interactive shell with status 1.
                    print(f"psh: {var}: readonly variable", file=self.state.stderr)
                    if self.shell.state.is_script_mode:
                        sys.exit(1)
                    return 1
                except NamerefCycleError as e:
                    # bash: writing through a circular nameref warns and
                    # aborts a non-interactive shell with status 1.
                    self.state.scope_manager.warn_nameref_cycle(e.name)
                    if self.shell.state.is_script_mode:
                        sys.exit(1)
                    return 1

            # bash: a pure assignment's status is 0, unless a command
            # substitution ran while expanding the value — then it is the
            # substitution's status (cleared/recorded around expansion).
            if self.state.last_cmdsub_status is not None:
                return self.state.last_cmdsub_status
            return 0

    # ------------------------------------------------------------------
    # Prefix assignments (FOO=bar cmd)
    # ------------------------------------------------------------------

    def apply_prefix(self, raw_assignments: List[RawAssignment]) -> PrefixOutcome:
        """Apply variable assignments for command execution.

        For command-prefixed assignments (FOO=bar cmd), we need to:
        1. Set the variable in shell state (for builtins/functions that use $VAR)
        2. Set the variable in shell.env (for external commands' environments)

        Values are expanded one at a time as they are applied, so each
        sees the assignments to its left (`A=1 B=$A cmd` gives B=1, bash).

        A readonly assignment does NOT abort the command (bash 5.2,
        probe-verified): the error is reported, that one assignment is
        skipped (the command's environment keeps the variable's old
        value), the OTHER assignments still apply, and the command runs
        with its own exit status. The caller handles ``set -e``, where
        bash makes the assignment error fatal instead.
        """
        saved_vars: Dict[str, dict] = {}
        assignments: List[Tuple[str, str]] = []
        assignment_error = False

        for var, value, value_word in raw_assignments:
            value = self._expand_value(value, value_word)
            var, value = resolve_append_assignment(
                self.state.scope_manager, var, value)
            # Save both shell state and environment values (first write wins
            # if the same variable is assigned twice)
            saved = None
            if var not in saved_vars:
                saved = {
                    'state': self.state.get_variable(var),
                    'env': self.shell.env.get(var)  # May be None if not in env
                }
            try:
                self.state.set_variable(var, value)
            except ReadonlyVariableError:
                # bash: report and skip; earlier assignments stay applied
                # (and are later restored), the command still runs.
                print(f"psh: {var}: readonly variable",
                      file=self.state.stderr)
                assignment_error = True
                continue
            if saved is not None:
                saved_vars[var] = saved
            assignments.append((var, value))
            # Also set in shell.env for external commands
            self.shell.env[var] = value

        return PrefixOutcome(saved_vars, assignments, assignment_error)

    def restore(self, saved_vars: Dict[str, dict]) -> None:
        """Restore variables after command execution.

        Restores both shell state and shell.env to their original values.
        Command-prefixed assignments (FOO=bar cmd) are always temporary,
        even for exported variables. (The POSIX special-builtin
        persistence exception is the dispatcher's: it simply does not
        call restore in that case.)
        """
        for var, saved in saved_vars.items():
            # Restore shell state variable
            old_state_value = saved['state']
            if old_state_value is None:
                self.state.unset_variable(var)
            else:
                self.state.set_variable(var, old_state_value)

            # Restore shell.env
            old_env_value = saved['env']
            if old_env_value is None:
                # Variable wasn't in env before, remove it
                if var in self.shell.env:
                    del self.shell.env[var]
            else:
                self.shell.env[var] = old_env_value

    # ------------------------------------------------------------------
    # Value expansion
    # ------------------------------------------------------------------

    def _expand_value(self, value: str, word: Optional['Word']) -> str:
        """Expand an assignment value using its Word AST.

        Locates the ``=`` in the word's parts (the ``NAME=`` prefix), then
        delegates the value portion to the shared bash assignment-value
        policy in ExpansionManager.expand_assignment_value_word() — the
        same policy array element assignments use — so quoting is handled
        structurally (single-quoted values stay literal, etc.).

        word=None is unreachable — SimpleCommand.args is derived from
        words, so every assignment extracted by extract() carries its
        Word. The old silent string-expansion fallback lost quote
        context; fail loudly instead (v0.300 policy).
        """
        if word is None:
            raise RuntimeError(
                f"internal error: assignment value {value!r} has no Word "
                "AST (SimpleCommand.words must parallel args)")

        from ..ast_nodes import LiteralPart, Word

        for index, part in enumerate(word.parts):
            if isinstance(part, LiteralPart) and '=' in part.text:
                # This part contains the '=' — the value is everything
                # after it plus all following parts
                eq_pos = part.text.index('=')
                value_text = part.text[eq_pos + 1:]
                value_parts = []
                if value_text:
                    value_parts.append(LiteralPart(
                        value_text, quoted=part.quoted,
                        quote_char=part.quote_char))
                value_parts.extend(word.parts[index + 1:])
                return self.expansion_manager.expand_assignment_value_word(
                    Word(parts=value_parts))

        # No '=' found in the word's literal parts
        return ''
