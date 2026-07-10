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

import copy
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Tuple, cast

from ..core import (
    AssociativeArray,
    IndexedArray,
    NamerefCycleError,
    ReadonlyVariableError,
    TopLevelAbort,
    is_valid_assignment,
    resolve_append_assignment,
)
from ..expansion.arithmetic import ShellArithmeticError

if TYPE_CHECKING:
    from ..ast_nodes import SimpleCommand, Word, WordPart
    from ..shell import Shell

# (name, raw value, Word carrying quote structure) — value unexpanded.
RawAssignment = Tuple[str, str, Optional['Word']]


class PrefixOutcome(NamedTuple):
    """Result of applying prefix assignments before a command.

    ``saved`` is handed back to :meth:`CommandAssignments.restore` by the
    dispatcher (opaque to it) — the save/restore snapshots for the few prefix
    names that take the SEED path (dynamic specials, array-object appends,
    nameref-to-element) rather than bash's temporary_env. ``applied`` is the
    expanded (name, value) pairs that took effect (``exec`` without a command
    persists these); ``failed`` is True when any assignment failed (readonly) —
    fatal under ``set -e``. ``pushed_temp_env`` records whether a command
    temporary-environment layer was opened (the common case — plain scalar
    prefix vars over a builtin/external), so :meth:`restore`/:meth:`commit`
    tear it down.
    """
    saved: Dict[str, dict]
    applied: List[Tuple[str, object]]  # value is str, or an array object (rare)
    failed: bool
    pushed_temp_env: bool = False


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
                posix_mode = self.state.options.get('posix', False)
                if '=' in arg and is_valid_assignment(arg, posix_mode):
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

        bash order (probe-verified): the assignments are performed FIRST,
        using the original file descriptors — ``x=$(cat) < file`` reads the
        ORIGINAL stdin, not the redirect — and only then are the command's
        redirections applied. A redirect failure therefore still leaves the
        variables assigned and fails the command with status 1
        (``x=5 > /bad/y`` → x is 5, rc 1).
        """
        xtrace = self.state.options.get('xtrace')
        for var, value, value_word in raw_assignments:
            value = self._expand_value(value, value_word)
            if xtrace:
                from ..core.options import xtrace_quote
                ps4 = self.expansion_manager.expand_ps4()
                # bash quotes the assignment VALUE (`x='a;b'`), not `x=`.
                self.state.stderr.write(f"{ps4}{var}={xtrace_quote(value)}\n")
                self.state.stderr.flush()
            # resolve_append_assignment may return an array object (scalar
            # append to an array updates element 0 and returns the array),
            # so the resolved value is wider than str; set_variable accepts it.
            var, resolved = resolve_append_assignment(
                self.state.scope_manager, var, value)
            try:
                self.state.set_variable(var, resolved)
            except ReadonlyVariableError as e:
                # bash: a readonly-variable assignment error aborts the whole
                # CURRENT top-level command (the rest of the command list, and
                # any enclosing if/loop/function on the same input) but does NOT
                # exit the shell in default mode — execution resumes at the next
                # top-level command. Use e.name so a readonly array-element write
                # reports the array name (``a[0]=X`` → ``a: readonly variable``),
                # like bash.
                #
                # In POSIX mode a variable-assignment error EXITS a
                # non-interactive shell, following bash's fatal expansion-error
                # status model — the SAME one ``set -u`` / ``${x:?}`` already use
                # (fatal_expansion_status): under ``-c`` (command_mode) the status
                # is bash's 127, for a script file or piped stdin it is 1 (both
                # probe-verified vs bash 5.2, 2026-07-10). Reproducing the ``-c``
                # 127 for the PLAIN assignment (this #34 fix) supersedes the
                # v0.677 "artifact not reproduced" call: psh already reproduces
                # 127 for the sibling errors, so leaving readonly at 1 made it the
                # one inconsistent member. The BUILTIN forms (readonly/export
                # ``r=2``, prefix ``r=2 cmd``) stay rc 1 via
                # SpecialBuiltinUsageError — a distinct, bash-correct code.
                print(f"psh: {e.name}: readonly variable", file=self.state.stderr)
                if self.state.options.get('posix'):
                    if self.state.options.get('command_mode'):
                        raise SystemExit(127) from None
                    if self.state.is_script_mode:
                        raise SystemExit(1) from None
                raise TopLevelAbort(1) from None
            except NamerefCycleError as e:
                # bash: writing through a circular nameref warns and aborts
                # the current top-level command (same scope as above).
                self.state.scope_manager.warn_nameref_cycle(e.name)
                raise TopLevelAbort(1) from None
            except ShellArithmeticError as e:
                # An integer-attributed variable (declare -i v; v='1/0')
                # whose value fails to evaluate: bash prints the arithmetic
                # error and DISCARDS the rest of the line (the rest of the
                # whole -c string under -c) — the assignment/subscript
                # arithmetic-error family. Value expansion has already run
                # against the ORIGINAL fds (assignments precede redirects).
                print(f"psh: {e}", file=self.state.stderr)
                from ..core import arith_assignment_discard
                arith_assignment_discard(self.state)

        if node.redirects:
            # Applied after the assignments (bash order, above). A setup
            # failure prints the one `psh: TARGET: STRERROR` shape and
            # fails the command with status 1 — never the raw OSError repr.
            with self.io_manager.guarded_redirections(node.redirects) as ok:
                if not ok:
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

    def apply_prefix(self, raw_assignments: List[RawAssignment],
                     temp_scope: bool = False) -> PrefixOutcome:
        """Apply a command's ``NAME=value`` prefix assignments (``FOO=bar cmd``).

        bash's *temporary environment* model, three routes:

        * ``temp_scope=True`` — the command resolves to a shell FUNCTION and the
          caller has pushed a dedicated temp-env SCOPE (``push_temp_env_scope``).
          Each prefix var becomes an EXPORTED local of that scope
          (``set_temp_env_var``): visible to the body AND to enumerations run
          inside it (bash merges a function's prefix vars into its locals), so a
          body ``declare -g``/``export`` writing past the layer survives the
          return while a plain body assignment is discarded. No per-variable
          ``saved`` snapshot — the caller pops the scope.

        * a plain scalar over a BUILTIN/EXTERNAL — the common case. The var goes
          into a command temporary-environment LAYER
          (``set_command_temp_env_var``) that NAME LOOKUP consults (``$VAR``,
          ``declare -p VAR``, ``${VAR@a}``, the exported-env materialization)
          but whole-table ENUMERATIONS (``set`` / ``export -p`` / ``declare -p``
          with no name) skip — exactly bash's separate ``temporary_env``. It is
          exported into the command's OWN process environment yet is not a shell
          variable, so it does not inherit the shadowed var's attributes
          (``declare -i n=5; n=abc cmd`` -> the command sees plain ``abc``) and
          it vanishes on teardown.

        * a dynamic special / array-object append / nameref-to-element — these
          take the legacy SEED path (a real ``set_variable`` with EXPORT plus a
          per-name save/restore snapshot and a literal env overlay), because the
          effect (seed RANDOM's generator; keep ``a=x cmd`` over an array
          non-destructive; write through a nameref to an array element) cannot
          be a plain temporary binding.

        Values are expanded one at a time so each sees the assignments to its
        left (``A=1 B=$A cmd`` gives B=1, bash). A readonly assignment does NOT
        abort the command (bash 5.2): the error is reported, that one assignment
        is skipped, the others still apply, and the command runs. The caller
        handles ``set -e``, where bash makes the assignment error fatal.
        """
        from ..core import VarAttributes

        scope_manager = self.state.scope_manager
        saved_vars: Dict[str, dict] = {}
        # ``resolved`` is usually a str; resolve_append_assignment can return an
        # array object for a scalar ``+=`` onto an array variable (rare in
        # prefix position) — hence the wider value type on the applied list.
        assignments: List[Tuple[str, object]] = []
        # Literal env overlay for the SEED path only (specials/arrays whose
        # exported value is not the literal string). Temp-env vars reach the
        # environment through the variable_changed observer + find_exported_instance,
        # so they need no overlay entry.
        overlay: Dict[str, str] = {}
        assignment_error = False
        pushed_temp_env = False

        xtrace = self.state.options.get('xtrace')
        for var, value, value_word in raw_assignments:
            value = self._expand_value(value, value_word)
            if xtrace:
                # set -x: a command-prefix assignment (`x=5 cmd`) is traced
                # before the command itself (bash), value-quoted like a pure one.
                from ..core.options import xtrace_quote
                ps4 = self.expansion_manager.expand_ps4()
                self.state.stderr.write(f"{ps4}{var}={xtrace_quote(value)}\n")
            var, resolved = resolve_append_assignment(scope_manager, var, value)
            # A nameref prefix (``declare -n r=a; r=x cmd``) writes THROUGH to
            # the target, so key everything on the target name. A subscripted
            # target (nameref to an array element) stays as-is — set_variable
            # routes that through the element setter (a seed-path case).
            write_name = scope_manager.resolve_nameref_name(var)
            if '[' not in write_name:
                var = write_name

            if temp_scope:
                # Function call: exported local of the pushed temp-env scope.
                try:
                    scope_manager.set_temp_env_var(var, resolved)
                except ReadonlyVariableError as e:
                    print(f"psh: {e.name}: readonly variable",
                          file=self.state.stderr)
                    assignment_error = True
                    continue
                assignments.append((var, resolved))
                continue

            # A dynamic special (RANDOM/SECONDS seed), an array-object result
            # (scalar ``+=`` onto an array), or a nameref-to-element target
            # cannot be a plain temporary binding — take the seed path.
            use_seed_path = (
                scope_manager.is_dynamic_special(var)
                or isinstance(resolved, (IndexedArray, AssociativeArray))
                or '[' in write_name)

            if not use_seed_path:
                # Common case: a hidden command temporary-environment binding.
                if not pushed_temp_env:
                    scope_manager.push_command_temp_env()
                    pushed_temp_env = True
                try:
                    scope_manager.set_command_temp_env_var(var, resolved)
                except ReadonlyVariableError as e:
                    # bash: report and skip; the real (readonly) variable keeps
                    # its value, the other assignments apply, the command runs.
                    print(f"psh: {e.name}: readonly variable",
                          file=self.state.stderr)
                    assignment_error = True
                    continue
                assignments.append((var, resolved))
                continue

            # Seed path: a real EXPORT write with a save/restore snapshot and a
            # literal env overlay. The snapshot is scope-aware — None means the
            # variable was UNSET, so restore() can re-unset it; an ARRAY is a
            # DEEP COPY (the scalar write mutates element 0 in place, and
            # restoring only element 0 would leave a spurious slot).
            saved = None
            if var not in saved_vars:
                existing = scope_manager.get_variable_object(var)
                existing_val = existing.value if existing is not None else None
                state_snapshot: object
                if isinstance(existing_val, (IndexedArray, AssociativeArray)):
                    state_snapshot = copy.deepcopy(existing_val)
                else:
                    state_snapshot = scope_manager.get_variable(var)
                saved = {
                    'state': state_snapshot,
                    'was_exported': bool(existing and existing.is_exported),
                }
            try:
                scope_manager.set_variable(
                    var, resolved, attributes=VarAttributes.EXPORT, local=False)
            except ReadonlyVariableError as e:
                # Use e.name so a readonly array-element write reports the array
                # name (``a[0]=X cmd`` -> ``a: readonly variable``).
                print(f"psh: {e.name}: readonly variable",
                      file=self.state.stderr)
                assignment_error = True
                continue
            if saved is not None:
                saved_vars[var] = saved
            assignments.append((var, resolved))
            # An array object must never reach execve's environment (F8) —
            # serialize to its scalar view (element 0).
            if isinstance(resolved, (IndexedArray, AssociativeArray)):
                overlay[var] = resolved.as_string()
            else:
                overlay[var] = cast(str, resolved)

        if overlay:
            self.state.apply_command_env(overlay)

        return PrefixOutcome(saved_vars, assignments, assignment_error,
                             pushed_temp_env)

    def restore(self, prefix: PrefixOutcome) -> None:
        """Tear down a command's prefix assignments after it runs.

        The temporary-environment LAYER is popped (its bindings vanish; the env
        entry reverts to the shell variable underneath). The few SEED-path names
        are restored to their saved values — None means they were UNSET before —
        and their literal env overlay is dropped, re-materializing from the
        restored variable. Command-prefixed assignments are always temporary,
        even for exported variables. (The POSIX special-builtin persistence
        exception is the dispatcher's: it calls :meth:`commit` instead.)
        """
        from ..core import VarAttributes

        if prefix.pushed_temp_env:
            self.state.scope_manager.pop_command_temp_env()

        for var, saved in prefix.saved.items():
            old_state_value = saved['state']
            if old_state_value is None:
                self.state.scope_manager.unset_variable(var)
            else:
                self.state.set_variable(var, old_state_value)
                # apply_prefix exported the variable for the command's duration;
                # if it was not exported before, take EXPORT back off (a
                # previously-exported variable keeps it, as it should).
                if not saved.get('was_exported'):
                    self.state.scope_manager.remove_attribute(
                        var, VarAttributes.EXPORT)

        # Drop the seed-path overlay and re-derive each name's env entry from the
        # (now restored) variable / opaque base.
        self.state.restore_command_env(prefix.saved.keys())

    def commit(self, prefix: PrefixOutcome) -> None:
        """Make the prefix assignments permanent (POSIX special-builtin rule,
        ``VAR=v :``): the variables persist as real EXPORTED shell variables.

        The temporary-environment bindings are PROMOTED to real exported vars
        (so ``VAR=v : ; declare -p VAR`` shows them), then the layer is popped.
        Seed-path variables stay exactly as apply_prefix left them; their env
        overlay is dropped so later materializations read the persisted vars.
        """
        from ..core import VarAttributes

        if prefix.pushed_temp_env:
            scope_manager = self.state.scope_manager
            layer = dict(scope_manager.command_temp_env[-1])
            scope_manager.pop_command_temp_env()
            for name, var in layer.items():
                scope_manager.set_variable(
                    name, var.value,
                    attributes=VarAttributes.EXPORT, local=False)

        self.state.restore_command_env(prefix.saved.keys())

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
                value_parts: List["WordPart"] = []
                if value_text:
                    value_parts.append(LiteralPart(
                        value_text, quoted=part.quoted,
                        quote_char=part.quote_char))
                value_parts.extend(word.parts[index + 1:])
                return self.expansion_manager.expand_assignment_value_word(
                    Word(parts=value_parts))

        # No '=' found in the word's literal parts
        return ''
