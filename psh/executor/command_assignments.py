"""Variable assignments attached to simple commands (``NAME=value``).

This module owns the "what does a ``NAME=value`` prefix mean" sub-domain;
`CommandExecutor` (command.py) keeps the "how is a command dispatched"
side and calls in here at four points: extract, pure-assignment shortcut,
prefix apply, and restore.

POSIX ordering contract (probe-verified against bash 5.2):

1. **Command words expand BEFORE assignments apply.** ``V=old; V=new echo
   $V`` prints ``old``: the prefix assignment is invisible to the
   command's own expansions.
2. **Assignment values expand left-to-right**, so each value sees the
   assignments to its left: ``A=1 B=$A cmd`` gives B the value ``1``
   (likewise pure ``x=1 y=$x``). For a command prefix this happens in
   :meth:`CommandAssignments.expand_prefix`, BEFORE the command resolves —
   a side effect inside a value must be visible to the dispatch decision it
   governs. A REFUSED assignment (readonly target) is never evaluated at
   all, so it contributes no side effect of any kind (bash).
3. **Prefix assignments are temporary.** Shell state and ``shell.env``
   are restored after the command — unless, **in POSIX mode**
   (``set -o posix``), it resolved to a POSIX special builtin, where the
   prefix assignments persist (``VAR=v :`` leaves VAR set). psh matches
   bash here: both persist only under ``--posix``; in default mode a
   prefix before a special builtin is temporary like any other. Whether
   persistence applies is the *dispatcher's* knowledge: CommandExecutor
   decides whether to call :meth:`restore` (or :meth:`commit`), and the
   saved-state value passes through it opaquely.
4. **A pure assignment reports the NULL-COMMAND status** — it runs no
   program, so it shares the one rule in `null_command.py`: 0 unless a
   command substitution ran while expanding words, then that substitution's
   status (``x=$(false)`` → 1, but ``x=$(false) true`` → 0), and 0 again if
   a redirection targeted fd 0 (``x=$(false) < f`` → 0). The clear of
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
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Sequence, Tuple, cast

from ..ast_nodes import ExpansionPart, LiteralPart, Word
from ..core import (
    AssociativeArray,
    IndexedArray,
    NamerefCycleError,
    ReadonlyVariableError,
    TopLevelAbort,
    VarAttributes,
    arith_assignment_discard,
    is_valid_assignment,
    resolve_append_assignment,
)
from ..core.options import xtrace_quote
from ..expansion.arithmetic import ShellArithmeticError
from .command_resolution import EMPTY_OVERLAY, CommandEnvOverlay
from .null_command import null_command_status

if TYPE_CHECKING:
    from ..ast_nodes import SimpleCommand, Word, WordPart
    from ..shell import Shell

# (name, raw value, Word carrying quote structure) — value unexpanded.
RawAssignment = Tuple[str, str, Optional['Word']]


class PrefixOutcome(NamedTuple):
    """Result of applying prefix assignments before a command.

    ``saved`` is handed back to :meth:`CommandAssignments.restore` by the
    dispatcher (opaque to it) — the save/restore snapshots for the few prefix
    names that take the SEED path (dynamic specials and array-object appends)
    rather than bash's temporary_env. ``applied`` is the
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


class StagedPrefix(NamedTuple):
    """A command's prefix assignments EXPANDED but not yet routed.

    The intermediate value of the two-phase prefix transaction
    (:meth:`CommandAssignments.expand_prefix` →
    :meth:`CommandAssignments.commit_prefix`). It exists because RESOLUTION
    runs BETWEEN the phases: a value's expansion may perform a shell-state
    side effect that decides how the command dispatches (an arithmetic or
    ``${v:=}`` write to ``POSIXLY_CORRECT`` flips posix mode), while the
    destination route is itself chosen by that dispatch answer.

    ``names``
        ``(install_name, staging_key)`` per staged binding, in source order —
        NOT their values. The two differ only for a nameref-to-element prefix
        (``declare -n r=a[0]; r=v cmd``): ``set_temp_env_var`` resolves the
        nameref, so the scope keys that binding on ``a[0]`` while the command
        must still see it installed as ``r``. Recording only one of the two
        loses the binding at commit. The
        staging scope is the single source of truth for what each name is
        WORTH: a later value's in-process store (``A=1 B=$((A=9))``) updates
        the staged binding, and the command must see what the shell sees.
        Carrying values here snapshotted them at staging time and produced a
        split brain — later prefixes read 9 from the scope while the command
        got 1 from the snapshot.

        :meth:`commit_prefix` therefore READS each name's value out of the
        staging scope. That is a read, never a re-expansion: the values are
        expanded EXACTLY ONCE, in phase 1. A second expansion would run every
        value's side effects again, which is observable (a command
        substitution would touch its file twice).
    ``failed``
        True when any assignment was refused (readonly) — fatal under
        ``set -e``, which the caller handles.
    ``staging_scope``
        True when a staging temp-env SCOPE is open holding the bindings. A SCOPE
        (not a command temp-env LAYER) is what makes the staged bindings
        visible to the next value's expansion and to resolution, and it is
        the only staging area that MASKS a dynamic special the way bash's
        temporary environment does.
    """

    names: Sequence[Tuple[str, str]]
    failed: bool
    staging_scope: bool


# The staged value for a command with NO prefix assignments — the hot-path
# default, so an unprefixed command allocates nothing and opens no scope.
EMPTY_STAGED = StagedPrefix((), False, False)


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
    # Overlay (the typed effective-environment view for resolution)
    # ------------------------------------------------------------------

    def build_overlay(
            self, raw_assignments: List[RawAssignment]) -> 'CommandEnvOverlay':
        """Build the :class:`CommandEnvOverlay` for a command's prefix.

        Carries the facts resolution can derive from the assignment NAMES
        alone: the names themselves (source order), whether a ``PATH=``
        override is present, and whether a ``POSIXLY_CORRECT`` assignment will
        flip posix mode for the command's own resolution. Values play no part
        — :meth:`expand_prefix` has already expanded them, in source order, by
        the time resolution consults this overlay.

        The POSIXLY_CORRECT fact mirrors bash's sv_strict_posix coupling rule
        (probe-derived, R3 bounce): NAME-level (any value — even empty or an
        unset-variable expansion — counts), through a NAMEREF (``declare -n
        r=POSIXLY_CORRECT; r=1 cmd`` flips), but a READONLY POSIXLY_CORRECT
        blocks the flip (the assignment will fail; bash never turns posix on,
        and a same-named function keeps winning the lookup). The readonly walk
        is :meth:`_readonly_blocks`, the same one :meth:`expand_prefix` uses to
        refuse the assignment, so the overlay predicts the outcome exactly.

        This covers only the NAME spelling. A posix flip performed INSIDE a
        value (``A=$((POSIXLY_CORRECT=1))``) is invisible to any name-level
        test; that one reaches resolution through ordering instead, because
        :meth:`expand_prefix` runs first (slot 3.4, HIGH-3).

        The common case — a command with NO prefix assignments — returns the
        shared :data:`EMPTY_OVERLAY` singleton (no per-command allocation on
        the hot path).
        """
        if not raw_assignments:
            return EMPTY_OVERLAY
        scope_manager = self.state.scope_manager
        names = tuple(name for name, _value, _word in raw_assignments)
        has_posix = False
        for name in names:
            if name != 'POSIXLY_CORRECT':
                # A nameref prefix writes through to its target (bash flips
                # posix for `declare -n r=POSIXLY_CORRECT; r=1 cmd`). A cycle
                # cannot reach POSIXLY_CORRECT as a final target; treat it as
                # a non-match (expand_prefix reports the cycle later).
                try:
                    name = scope_manager.resolve_nameref_name(name)
                except NamerefCycleError:
                    continue
            if name == 'POSIXLY_CORRECT' \
                    and not self._readonly_blocks('POSIXLY_CORRECT'):
                has_posix = True
                break
        return CommandEnvOverlay(
            assignment_names=names,
            has_path_override='PATH' in names,
            has_posix_override=has_posix,
        )

    def _readonly_blocks(self, name: str) -> bool:
        """True when the innermost scope instance of *name* is readonly — the
        same walk ``set_command_temp_env_var`` performs, so the overlay
        predicts exactly whether the install will be refused."""
        for scope in reversed(self.state.scope_manager.scope_stack):
            if name in scope.variables:
                return scope.variables[name].is_readonly
        return False

    # ------------------------------------------------------------------
    # Pure assignments (no command word)
    # ------------------------------------------------------------------

    def apply_pure(self, node: 'SimpleCommand',
                   raw_assignments: List[RawAssignment]) -> int:
        """Apply pure variable assignments (no command).

        Takes raw (var, value, word) triples: each value is expanded just
        before it is applied so `A=1 B=$A` gives B the new value of A.

        The exit status is the shared null-command status
        (:mod:`psh.executor.null_command`): 0, unless a command substitution
        ran while expanding the values — then it is the substitution's status
        (the caller cleared ``state.last_cmdsub_status`` before any expansion;
        see the module docstring for why the clear lives there) — and 0 again
        whenever a redirection targeted fd 0, which bash performs in a forked
        child (``x=$(exit 5)`` -> 5, ``x=$(exit 5) < f`` -> 0).

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
                print(f"{self.state.error_location_prefix()}{e.name}: readonly variable", file=self.state.stderr)
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
                arith_assignment_discard(self.state)

        if node.redirects:
            # Applied after the assignments (bash order, above). A setup
            # failure prints the one `psh: TARGET: STRERROR` shape and
            # fails the command with status 1 — never the raw OSError repr.
            with self.io_manager.guarded_redirections(
                    node.redirects, compound=False) as ok:
                if not ok:
                    return 1

        # An assignment-only command runs no program, so its status is the
        # ONE null-command status (psh/executor/null_command.py): the last
        # command substitution run while expanding it, unless a redirection
        # targeted fd 0 — `x=$(exit 5)` -> 5, but `x=$(exit 5) < f` -> 0.
        return null_command_status(self.state, node.redirects)

    # ------------------------------------------------------------------
    # Prefix assignments (FOO=bar cmd)
    # ------------------------------------------------------------------

    def expand_prefix(self,
                      raw_assignments: List[RawAssignment]) -> StagedPrefix:
        """Phase 1 of the prefix transaction: expand the values, stage them.

        Each value is expanded ONCE, left to right, and staged in a temp-env
        SCOPE so the NEXT value's expansion sees the bindings to its left
        (``A=1 B=$A cmd`` gives B the value ``1``, bash). Any shell-state side
        effect a value's expansion performs — an arithmetic assignment,
        a ``${v:=}`` store — lands live, at its natural point in the
        left-to-right order.

        Phase 1 runs BEFORE command resolution, which is the whole point: a
        side effect that enables POSIX mode must be visible to the very
        lookup it governs (``A=$((POSIXLY_CORRECT=1)) eval …`` resolves to the
        special builtin, not a same-named function — bash). Resolution has no
        side effects of its own, so moving it after expansion reorders nothing
        observable; the relative order of the values' own command
        substitutions is unchanged.

        The staging area is a temp-env SCOPE rather than a command temp-env
        LAYER for a measured reason: ``get_variable_object`` resolves a
        computed special BEFORE consulting the layer, but a scope binding
        SHADOWS it (``_local_shadows_special``). Only the scope therefore
        reproduces bash's masking, where ``RANDOM=1 b=$RANDOM cmd`` gives b
        the literal ``1`` instead of a generated number.

        A readonly target is refused HERE, before any write, so a blocked
        assignment cannot flip an option as a side effect of being staged.
        The check is :meth:`_readonly_blocks` — a direct scope scan — because
        ``set_temp_env_var`` cannot see a DECLARED-UNSET readonly cell
        (``readonly RX`` with no value): the lookup it uses returns None for
        that cell. bash's shape is skip-and-continue: report, drop that one
        assignment, apply the rest, run the command.
        """
        if not raw_assignments:
            return EMPTY_STAGED

        try:
            return self._stage_values(
                raw_assignments, self.state.options.get('xtrace'))
        except BaseException:
            # A value's expansion can raise from the SECOND assignment onward,
            # after the staging scope is already open (an arithmetic error, a
            # nameref cycle, a fatal expansion). Phase 2 never runs on that
            # path, so phase 1 unwinds its own scope here — a leaked staging
            # scope would be enumeration-INVISIBLE pollution that also grows
            # the scope stack once per error.
            self._discard_staging_scope()
            raise

    def _pop_staging_scope(self) -> None:
        """Pop the staging scope, checking this transaction still owns it.

        Ownership is checked rather than assumed because the failure is silent
        both ways: popping a scope we do not own destroys someone else's
        bindings, and failing to pop ours leaves an enumeration-INVISIBLE
        scope behind. ``staged.staging_scope`` says a scope was opened; this
        says the one on top is still it.

        A ``raise``, not an ``assert``: assertions vanish under ``python -O``,
        which is exactly where a silent scope-stack corruption would be worst.
        """
        stack = self.state.scope_manager.scope_stack
        if len(stack) <= 1 or not stack[-1].is_staging:
            raise RuntimeError(
                "internal error: prefix transaction lost ownership of its "
                f"staging scope (depth={len(stack)}, top_is_staging="
                f"{getattr(stack[-1], 'is_staging', None)})")
        self.state.scope_manager.pop_scope()

    def _discard_staging_scope(self) -> None:
        """Pop the staging scope if this transaction still owns one."""
        scope_manager = self.state.scope_manager
        stack = scope_manager.scope_stack
        if len(stack) > 1 and stack[-1].is_staging:
            scope_manager.pop_scope()

    def _stage_values(self, raw_assignments: List[RawAssignment],
                      xtrace: object) -> StagedPrefix:
        """The staging loop of :meth:`expand_prefix` (which owns unwinding)."""
        scope_manager = self.state.scope_manager
        names: List[Tuple[str, str]] = []
        failed = False
        staging_scope = False

        for var, value, value_word in raw_assignments:
            # REFUSE BEFORE EVALUATE. bash never evaluates the value of an
            # assignment it is going to refuse: after
            # ``readonly RX; RX=$((Z=9)) f`` its Z is UNSET. So the check runs
            # on the NAME alone, before expansion, and a refused assignment
            # contributes ZERO side effects — no arithmetic write, no ``:=``
            # store, no command substitution, and so no posix flip either.
            #
            # Checking after expansion (as this did) let a refused assignment's
            # value still flip posix, which then routed the refusal through the
            # POSIX prefix-error branch and aborted a statement that bash runs.
            # A nameref prefix (``declare -n r=a; r=x cmd``) writes THROUGH to
            # its target, so the name to test is the resolved one; an append
            # (``a+=z``) arrives as ``a+``.
            write_name = scope_manager.resolve_nameref_name(
                var[:-1] if var.endswith('+') else var)
            if '[' not in write_name and self._readonly_blocks(write_name):
                print(f"{self.state.error_location_prefix()}{write_name}: readonly variable",
                      file=self.state.stderr)
                failed = True
                continue

            value = self._expand_value(value, value_word)
            if xtrace:
                # set -x: a command-prefix assignment (`x=5 cmd`) is traced
                # before the command itself (bash), value-quoted like a pure one.
                ps4 = self.expansion_manager.expand_ps4()
                self.state.stderr.write(f"{ps4}{var}={xtrace_quote(value)}\n")
            var, resolved = resolve_append_assignment(scope_manager, var, value)
            # A subscripted target (nameref to an array element) stays as-is.
            if '[' not in write_name:
                var = write_name

            if not staging_scope:
                scope_manager.push_temp_env_scope(staging=True)
                staging_scope = True
            try:
                scope_manager.set_temp_env_var(var, resolved)
            except ReadonlyVariableError as e:
                # Use e.name so a readonly array-element write reports the
                # array name (``a[0]=X cmd`` -> ``a: readonly variable``).
                print(f"{self.state.error_location_prefix()}{e.name}: readonly variable",
                      file=self.state.stderr)
                failed = True
                continue
            entry = (var, write_name)
            if entry not in names:
                names.append(entry)

        return StagedPrefix(names, failed, staging_scope)

    def _live_pairs(self, staged: StagedPrefix) -> List[Tuple[str, object]]:
        """The staged names paired with their CURRENT values in the scope.

        Read straight out of the staging scope's own dict rather than through
        name lookup, so the answer is unambiguously "what this transaction
        staged, as it now stands" — not whatever an outer scope or a computed
        special might otherwise resolve to.
        """
        if not staged.staging_scope:
            return []
        stack = self.state.scope_manager.scope_stack
        staging = stack[-1]
        if len(stack) <= 1 or not staging.is_staging:
            # Same ownership check its sibling `_pop_staging_scope` makes, for
            # the same reason: reading values out of a scope this transaction
            # no longer owns would silently install someone else's bindings.
            raise RuntimeError(
                "internal error: prefix transaction read a staging scope it "
                f"does not own (depth={len(stack)}, top_is_staging="
                f"{getattr(staging, 'is_staging', None)})")
        pairs: List[Tuple[str, object]] = []
        for install_name, staging_key in staged.names:
            var = staging.variables.get(staging_key)
            if var is not None:
                pairs.append((install_name, var.value))
        return pairs

    def commit_prefix(self, staged: StagedPrefix,
                      temp_scope: bool) -> PrefixOutcome:
        """Phase 2 of the prefix transaction: route the staged bindings.

        The values are ALREADY expanded (:meth:`expand_prefix`); this method
        only chooses their destination, which is the one thing that needs the
        resolution answer. It never re-expands — a second expansion would be a
        second run of the values' side effects.

        * ``temp_scope=True`` — the command resolved to a shell FUNCTION, so
          the staging scope IS the destination and is simply adopted (bash
          merges a function's prefix vars into its locals; the caller pops it
          on return). Nothing moves.

        * otherwise the staging scope is popped and each binding installs into
          a command temporary-environment LAYER — which name LOOKUP consults
          but whole-table ENUMERATIONS skip, exactly bash's ``temporary_env``.
          Dynamic specials (RANDOM/SECONDS) and array objects cannot be a
          plain temporary binding, so they take the SEED path here: a real
          exported write plus the save/restore snapshot and literal env
          overlay :meth:`restore` and :meth:`commit` consume. Seeding happens
          at COMMIT, never at staging, so a later prefix value still reads the
          MASKED literal. A nameref-to-element prefix (``declare -n r=a[0];
          r=v cmd``) takes the LAYER route like any other scalar: the command
          SEES it (``r=NEW eval 'echo $r'`` prints NEW, as in bash), but it
          does not write through to the array and leaves no diagnostic — bash
          does neither for the prefix form. The staging scope keys that
          binding on its RESOLVED target (``a[0]``) because
          ``set_temp_env_var`` follows the nameref, which is why the staged
          record carries both the install name and the staging key.
        """
        if temp_scope or not staged.names:
            applied = self._live_pairs(staged)
            if not temp_scope and staged.staging_scope:
                self._pop_staging_scope()
            elif temp_scope and staged.staging_scope:
                # FUNCTION target ADOPTS the staging scope: clear the staging
                # flag so the body enumerates its prefix vars (bash merges a
                # function's prefix vars into its locals).
                self.state.scope_manager.scope_stack[-1].is_staging = False
            return PrefixOutcome({}, applied, staged.failed, False)

        scope_manager = self.state.scope_manager

        # READ the live values out of the staging scope BEFORE disposing of
        # it. The scope is the single source of truth for what each staged
        # name is WORTH: a later value's in-process store (``A=1 B=$((A=9))``)
        # updated the binding there, and the command must see what the shell
        # sees. This is a READ, never a re-expansion — phase 1 expanded each
        # value exactly once, and that has to stay true or every value's side
        # effects would run a second time.
        live = self._live_pairs(staged)

        if staged.staging_scope:
            # OWNERSHIP TRANSFER, done BEFORE the install loop: from here on
            # this transaction no longer owns a staging scope, so an exception
            # raised while installing cannot reach the ownership check and
            # replace itself with a bogus "lost ownership" error. The original
            # exception propagates; the caller's unwinder finds nothing to pop.
            self._pop_staging_scope()

        saved_vars: Dict[str, dict] = {}
        assignments: List[Tuple[str, object]] = []
        # Literal env overlay for the SEED path only (specials/arrays whose
        # exported value is not the literal string). Temp-env vars reach the
        # environment through the variable_changed observer +
        # find_exported_instance, so they need no overlay entry.
        overlay: Dict[str, str] = {}
        failed = staged.failed
        pushed_temp_env = False

        for var, resolved in live:
            # No bracket can reach this test. ``a[0]=v cmd`` is refused
            # upstream as "not a valid identifier" (bash likewise), and a
            # nameref-to-element prefix installs under its NAMEREF name (the
            # bracketed form is the staging KEY, not the install name). The
            # bracket disjunct this once had was therefore unreachable.
            use_seed_path = (
                scope_manager.is_dynamic_special(var)
                or isinstance(resolved, (IndexedArray, AssociativeArray)))

            if not use_seed_path:
                # Common case: a hidden command temporary-environment binding.
                if not pushed_temp_env:
                    scope_manager.push_command_temp_env()
                    pushed_temp_env = True
                try:
                    scope_manager.set_command_temp_env_var(var, resolved)
                except ReadonlyVariableError as e:
                    print(f"{self.state.error_location_prefix()}{e.name}: readonly variable",
                          file=self.state.stderr)
                    failed = True
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
                print(f"{self.state.error_location_prefix()}{e.name}: readonly variable",
                      file=self.state.stderr)
                failed = True
                continue
            # Recorded only once the write SUCCEEDED: a refused assignment left
            # the variable untouched, so restore() must have nothing to undo for
            # it. Snapshotting before the write would hand restore a name it
            # never changed.
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

        return PrefixOutcome(saved_vars, assignments, failed, pushed_temp_env)

    def apply_prefix(self, raw_assignments: List[RawAssignment],
                     temp_scope: bool = False) -> PrefixOutcome:
        """Expand and install a command's prefix assignments in one call.

        TEST-ONLY as of slot 3.4: there are no production callers. The
        executor drives :meth:`expand_prefix` and :meth:`commit_prefix`
        separately, because resolution must run between them and read the
        state the expansions leave behind — a static ratchet
        (``tests/unit/tooling/test_resolution_timing_ratchet_3_4.py``) fails
        if this composition reappears on the dispatch path, where it would
        expand a second time.

        Retained because the unit tests for the assignment sub-domain want
        one call rather than two, and because "expand then commit with a
        known route" is the honest summary of what the pair does.
        """
        return self.commit_prefix(self.expand_prefix(raw_assignments),
                                  temp_scope=temp_scope)

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

        if prefix.pushed_temp_env:
            self.state.scope_manager.pop_command_temp_env()

        for var, saved in prefix.saved.items():
            old_state_value = saved['state']
            if old_state_value is None:
                self.state.scope_manager.unset_variable(var)
            else:
                self.state.set_variable(var, old_state_value)
                # commit_prefix exported the variable for the command's duration;
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
        Seed-path variables stay exactly as commit_prefix left them; their env
        overlay is dropped so later materializations read the persisted vars.
        """

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
