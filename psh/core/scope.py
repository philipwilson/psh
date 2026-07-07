"""Hierarchical variable scope management with attribute support."""

from typing import Any, Callable, Dict, List, Optional, Tuple

from .exceptions import ReadonlyVariableError
from .locale_service import active_locale
from .special_registry import SpecialContext, SpecialParameterState
from .variable_store import VariableStore
from .variables import AssociativeArray, IndexedArray, VarAttributes, Variable


class VariableScope:
    """Represents a single variable scope with attribute-aware variables."""

    def __init__(self, parent: Optional['VariableScope'] = None, name: Optional[str] = None):
        self.variables: Dict[str, Variable] = {}
        self.parent = parent
        self.name = name or 'anonymous'
        # True for a command's temp-env prefix layer (``X=1 func``). A plain
        # body assignment updates this layer (discarded on return), but the
        # ``export``/``declare -g`` builtins write PAST it to the variable's
        # real home (bash) — see set_variable(skip_temp_env=...).
        self.is_temp_env = False
        # `local -` snapshot: (set-option values, edit_mode) saved when the
        # function ran `local -`; restored by the function-return path so the
        # options changed inside the function revert (bash). None if unused.
        self.dash_snapshot: Optional[Tuple[Dict[str, Any], str]] = None

    def __repr__(self):
        return f"VariableScope(name={self.name}, vars={list(self.variables.keys())})"

    def copy(self) -> 'VariableScope':
        """Create a deep copy of this scope.

        Copies ``is_temp_env`` and the ``local -`` ``dash_snapshot`` (a nested
        ``(set-options dict, edit_mode)`` — deep-copied so a child restoring
        it cannot mutate the parent's saved options) alongside every variable.
        """
        new_scope = VariableScope(parent=None, name=self.name)
        new_scope.is_temp_env = self.is_temp_env
        if self.dash_snapshot is not None:
            opts, edit_mode = self.dash_snapshot
            new_scope.dash_snapshot = (dict(opts), edit_mode)
        for name, var in self.variables.items():
            new_scope.variables[name] = var.copy()
        return new_scope


class ScopeManager:
    """Hierarchical scope manager with variable attributes support."""

    def __init__(self):
        self.global_scope = VariableScope(name='global')
        self.scope_stack: List[VariableScope] = [self.global_scope]
        self._debug = False
        self._shell = None  # Reference to shell for arithmetic evaluation
        # The authoritative variable-mutation service (core-state Phase 2). It
        # shares this manager's scope stack and observers; every child manager
        # from ``clone()`` builds a fresh store, so writes never cross the child
        # boundary. See psh/core/variable_store.py.
        self.store = VariableStore(self)

        # Observer fired whenever PATH is assigned, declared local, or
        # unset — installed by ShellState to empty the command hash table
        # (bash empties it on ANY PATH write, even ``PATH=$PATH``; the
        # one string compare per write is the whole cost of the hook).
        self.path_changed: Optional[Callable[[], None]] = None

        # Observer fired with the (nameref-resolved) variable name after
        # any write, attribute change, unset, or scope pop that may alter
        # the variable visible under that name. Installed by ShellState
        # to keep ``state.env`` in sync with export-attributed variables
        # (bash: ``export FOO=old; FOO=new`` updates the environment the
        # next child sees — the assignment itself syncs, not just the
        # ``export`` builtin).
        self.variable_changed: Optional[Callable[[str], None]] = None

        # Computed special-parameter lifecycle (RANDOM/SECONDS/LINENO/...).
        # One typed object owns the SECONDS monotonic baseline, the RANDOM seed,
        # the LINENO counter, the deactivated-on-unset set, and the persistent
        # readonly/export overlay — see special_registry.py (appraisal H1).
        self._special = SpecialParameterState()

    def clone(self) -> 'ScopeManager':
        """Build an independent ScopeManager for a child shell (clone_for_child).

        Copies every scope via ``VariableScope.copy`` (whole ``Variable``
        objects with deep-copied array values), the debug flag, and the
        computed-special bookkeeping (``SpecialParameterState.clone``: SECONDS
        baseline, deactivated specials, current line, persistent attributes —
        RANDOM's seed is deliberately reset there). The observers and the
        ``_shell`` back-reference are left unset: the owning ``ShellState``
        re-wires the observers and ``Shell.set_shell`` installs the
        back-reference.

        Crucially, NO variable is created through ``set_variable``, so the
        child's variable keyset is EXACTLY the parent's — no seeded defaults
        and no ``os.environ`` re-import can resurrect a name the parent unset
        (the C1 resurrection defect).
        """
        new = ScopeManager()
        new.global_scope = self.global_scope.copy()
        new.scope_stack = [new.global_scope]
        for scope in self.scope_stack[1:]:
            new.scope_stack.append(scope.copy())
        new._debug = self._debug
        new._special = self._special.clone()
        return new

    def _notify_path_changed(self, name: str) -> None:
        """Fire the PATH observer when *name* is PATH (post-nameref)."""
        if name == 'PATH' and self.path_changed is not None:
            self.path_changed()

    def _notify_variable_changed(self, name: str) -> None:
        """Fire the per-variable observer (post-nameref name)."""
        if self.variable_changed is not None:
            self.variable_changed(name)

    def set_shell(self, shell):
        """Set reference to shell instance for arithmetic evaluation."""
        self._shell = shell

    def is_dynamic_special(self, name: str) -> bool:
        """True if *name* is an ACTIVE dynamic special (RANDOM/SECONDS/...).

        Public predicate for callers that must treat these specially — e.g.
        ``set -a`` must not auto-export them (see ShellState.set_variable)."""
        return self._special.has_lifecycle(name)

    def enable_debug(self, enabled: bool = True):
        """Enable or disable debug output for scope operations."""
        self._debug = enabled

    def _debug_print(self, message: str):
        """Print debug message if debugging is enabled."""
        if self._debug:
            import sys
            print(f"[SCOPE] {message}", file=sys.stderr)

    def push_scope(self, name: Optional[str] = None) -> VariableScope:
        """Create new scope for function entry."""
        new_scope = VariableScope(parent=self.current_scope, name=name)
        self.scope_stack.append(new_scope)
        self._debug_print(f"Pushing scope for function: {name or 'anonymous'}")
        return new_scope

    def push_temp_env_scope(self) -> VariableScope:
        """Push a scope holding a command's temp-env prefix assignments.

        bash treats ``X=1 func`` as a *temporary variable context* layered
        UNDER the function's own locals: the prefix vars shadow globals for
        the duration of the call, a plain assignment in the body updates
        this temporary layer (and is discarded on return), while a
        ``declare -g``/``export`` in the body reaches PAST it to the real
        global and therefore SURVIVES the return. Modelling the temp-env as
        a genuine scope reproduces all of that exactly — see
        ``CommandAssignments.apply_prefix``. Named distinctly from a
        function scope so ``--debug-scopes`` output stays legible.
        """
        scope = self.push_scope(name='tempenv')
        scope.is_temp_env = True
        return scope

    def set_temp_env_var(self, name: str, value: Any) -> None:
        """Create one temp-env prefix variable in the current (temp-env) scope.

        The variable is EXPORTED for the command's duration (bash places a
        prefix assignment in the command's environment) but does NOT inherit
        the shadowed variable's other attributes: ``declare -i X=5; X=abc f``
        gives the body a plain exported ``X="abc"``, not an integer-evaluated
        ``0`` (probe-verified against bash 5.2 — the value is stored raw). A
        readonly shadowed variable blocks the assignment with
        ReadonlyVariableError, exactly like any prefix assignment to a
        readonly name. The env sync happens through the variable_changed
        observer (this var is the innermost exported instance of the name).
        """
        name = self.resolve_nameref_name(name)
        existing = self.get_variable_object(name)
        if existing is not None and existing.is_readonly:
            raise ReadonlyVariableError(name)
        self.current_scope.variables[name] = Variable(
            name=name, value=value, attributes=VarAttributes.EXPORT)
        self._notify_path_changed(name)
        self._notify_variable_changed(name)

    def pop_scope(self) -> Optional[VariableScope]:
        """Remove scope on function exit."""
        if len(self.scope_stack) > 1:
            scope = self.scope_stack.pop()
            if scope.variables:
                var_names = ', '.join(scope.variables.keys())
                self._debug_print(f"Popping scope: {scope.name} (destroying variables: {var_names})")
            else:
                self._debug_print(f"Popping scope: {scope.name} (no variables)")
            # Every name the popped scope held may now resolve to a
            # different (outer) variable — let the observer re-derive any
            # environment entry (bash: an exported local's env entry
            # reverts to the outer value, or disappears, on return).
            for name in scope.variables:
                self._notify_variable_changed(name)
            return scope
        else:
            raise RuntimeError("Cannot pop global scope")

    def get_variable(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get variable value as string, following namerefs, or default."""
        var = self._lookup_resolved(name)
        if var:
            return var.as_string()
        return default

    def _lookup_resolved(self, name: str) -> Optional[Variable]:
        """Look up a variable, following a nameref chain to its target.

        A nameref stores its target *name* as its value. Returns the final
        non-nameref Variable, or the nameref itself when its target is empty
        (so reading a target-less nameref yields nothing). A cyclic chain
        warns and reads as unset (bash: "warning: a: circular name
        reference", the expansion is empty, status unchanged).
        """
        var = self.get_variable_object(name)
        seen = set()
        while var is not None and var.is_nameref:
            target = str(var.value) if var.value else ''
            if not target:
                return var  # empty target — read the nameref's own value
            if target in seen:
                self.warn_nameref_cycle(name)
                return None
            seen.add(target)
            var = self.get_variable_object(target)
        return var

    @staticmethod
    def warn_nameref_cycle(name: str) -> None:
        """Print bash's circular-nameref warning."""
        import sys
        print(f"psh: warning: {name}: circular name reference", file=sys.stderr)

    def resolve_nameref_name(self, name: str) -> str:
        """Follow a nameref chain and return the final target *name*.

        Used by the write/unset paths. A plain or unset name resolves to
        itself; a nameref with an empty target resolves to its own name (so
        e.g. ``declare -n r; r=x`` sets r's target rather than writing
        through to nothing). A cyclic chain raises NamerefCycleError — bash
        rejects the write with "circular name reference".
        """
        from .exceptions import NamerefCycleError
        # Computed special variables are never namerefs, and probing them
        # through get_variable_object here would fire their side effects
        # (advancing the RANDOM generator, drawing a fresh SRANDOM, building the
        # FUNCNAME/PIPESTATUS arrays) on what is meant to be a name-only
        # inspection. Resolve them to themselves without touching the read path.
        if self._special.is_computed(name):
            return name
        seen = set()
        current = name
        while True:
            var = self.get_variable_object(current)
            if var is None or not var.is_nameref:
                return current
            target = str(var.value) if var.value else ''
            if not target:
                return current
            if target in seen or target == current:
                raise NamerefCycleError(name)
            seen.add(current)
            current = target

    def get_variable_object(self, name: str) -> Optional[Variable]:
        """Get the full Variable object through scope chain (no nameref deref)."""
        # Check for special variables first
        special_var = self._get_special_variable(name)
        if special_var is not None:
            return special_var

        # Search from innermost to outermost scope
        for scope in reversed(self.scope_stack):
            if name in scope.variables:
                var = scope.variables[name]
                # Skip unset variables (tombstones)
                if var.is_unset:
                    self._debug_print(f"Variable lookup: {name} found unset tombstone in scope '{scope.name}', skipping")
                    return None
                self._debug_print(f"Variable lookup: {name} found in scope '{scope.name}' = {var.value}")
                return var

        self._debug_print(f"Variable lookup: {name} not found in any scope")
        return None

    def _innermost_scope_with(self, name: str,
                              skip_temp_env: bool = False) -> Optional[VariableScope]:
        """Innermost scope whose dict holds *name* (tombstones count), or None.

        The single scope-search used to pick a write target. With
        ``skip_temp_env`` it steps past a command's temp-env prefix layer, so
        the ``export``/``declare -g`` builtins reach the variable's real home
        while a plain assignment still lands on the temp layer (bash).
        """
        for scope in reversed(self.scope_stack):
            if skip_temp_env and scope.is_temp_env:
                continue
            if name in scope.variables:
                return scope
        return None

    def get_declared_variable_object(self, name: str) -> Optional[Variable]:
        """Scope-chain lookup that also finds declared-but-unset variables.

        ``export FOO`` / ``declare -i N`` / ``local -x V`` record
        attributes on a variable that still READS as unset (UNSET flag;
        get_variable_object returns None for it). ``declare -p`` must
        nevertheless display it (bash: ``declare -x FOO``). An
        attribute-less declared-unset cell — bare ``declare FOO`` /
        ``local FOO``, or a local unset in its own scope — is found too
        (bash shows ``declare -- FOO``).

        An active dynamic special has no stored cell, so return its computed
        value carrying the effective attributes — ``declare -p RANDOM`` shows
        ``declare -ir RANDOM="..."`` like bash, rather than "not found".
        """
        if self._special.has_lifecycle(name):
            return self._get_special_variable(name)
        for scope in reversed(self.scope_stack):
            if name in scope.variables:
                return scope.variables[name]
        return None

    def set_variable(self, name: str, value: Any,
                     attributes: VarAttributes = VarAttributes.NONE,
                     local: bool = False, global_scope: bool = False,
                     skip_temp_env: bool = False):
        """Set variable with attributes in appropriate scope.

        Args:
            name: Variable name
            value: Variable value
            attributes: Variable attributes to apply
            local: If True, set in current scope. If False and in function,
                   check if variable exists in current scope first
            global_scope: If True (``declare -g``), force the GLOBAL scope
                   regardless of any same-named local — bash: ``local x=2;
                   declare -g x=3`` leaves the local at 2 and writes the
                   global. The existence/readonly/attribute-merge checks
                   then consult the global instance, not the innermost
                   visible one.
            skip_temp_env: If True (the ``export`` builtin / ``cd``'s PWD
                   write), the innermost-scope search that picks the target
                   and the existence/readonly check both SKIP a command's
                   temp-env prefix layer, so ``X=1 f; f(){ export X=2; }``
                   writes the real global X (which survives the return),
                   matching bash — a plain body ``X=2`` still updates the
                   temp layer. No effect when no temp-env scope is present.
        """
        # Redirect writes through a nameref to its target, EXCEPT when we are
        # defining the nameref itself (NAMEREF in the new attributes), where the
        # value IS the target name and must be stored on `name` directly.
        if not (attributes & VarAttributes.NAMEREF):
            name = self.resolve_nameref_name(name)
            # A nameref whose target is an array element (e.g. arr[1]) resolves
            # to a subscripted name; route that through the array-element setter
            # (public ExpansionManager API — same upward path already used for
            # arithmetic evaluation and FUNCNAME).
            if ('[' in name and name.endswith(']') and self._shell is not None
                    and not isinstance(value, (IndexedArray, AssociativeArray))):
                self._shell.expansion_manager.set_var_or_array_element(name, value)
                return

        # Whole-variable assignment to an ACTIVE dynamic special (RANDOM/SECONDS
        # seed; BASHPID/SRANDOM/EPOCH*/LINENO ignore the value). No stored
        # variable is created: readonly is enforced from the persistent-attribute
        # overlay, the value is applied by the special's assign policy, and any
        # declaration attributes (``readonly RANDOM=5``, ``export SECONDS=100``)
        # persist on the overlay — the observer then materialises an EXPORT
        # snapshot into the environment. An array assignment or a nameref
        # DEFINITION is not a special write and falls through.
        if (self._special.has_lifecycle(name)
                and not (attributes & VarAttributes.NAMEREF)
                and not isinstance(value, (IndexedArray, AssociativeArray))):
            if self._special.attributes_for(name) & VarAttributes.READONLY:
                raise ReadonlyVariableError(name)
            self._special.assign(name, value)
            self._special.add_attributes(name, attributes)
            self._notify_variable_changed(name)
            return

        # Check if variable exists. `declare -g` targets the global scope, so
        # its existence/readonly/attribute-merge checks must look at the global
        # instance (a same-named local is irrelevant); a global tombstone reads
        # as absent, like get_variable_object.
        if global_scope:
            existing = self.global_scope.variables.get(name)
            if existing is not None and existing.is_unset:
                existing = None
        elif skip_temp_env:
            # export/cd write past a temp-env layer to the variable's real
            # home; the readonly/merge check must consult THAT instance.
            sc = self._innermost_scope_with(name, skip_temp_env=True)
            existing = sc.variables.get(name) if sc is not None else None
            if existing is not None and existing.is_unset:
                existing = None
        else:
            existing = self.get_variable_object(name)
        if existing and existing.is_readonly:
            raise ReadonlyVariableError(name)

        # If updating existing variable, merge its attributes with new ones
        if existing and not attributes:
            # Use existing attributes when no new attributes specified
            attributes = existing.attributes
        elif existing and attributes:
            # Merge attributes when both exist
            attributes = existing.attributes | attributes

        # Determine target scope
        if global_scope:
            # declare -g: always the global scope, past any local shadow.
            target_scope = self.global_scope
            scope_name = target_scope.name
        elif local or len(self.scope_stack) == 1:
            # Set in current scope (global or explicitly local)
            target_scope = self.current_scope
            scope_name = target_scope.name
        else:
            # In a function, not explicitly local: bind to the innermost
            # scope holding an instance of the name. A declared-but-unset
            # local (tombstone) counts — bash rebinds ``local x; unset x;
            # x=new`` (and an assignment from a CALLED function) in the
            # declaring scope. With no instance anywhere, create a global.
            # ``skip_temp_env`` (export/cd) steps past a temp-env prefix layer.
            sc = self._innermost_scope_with(name, skip_temp_env=skip_temp_env)
            target_scope = sc if sc is not None else self.global_scope
            scope_name = target_scope.name

        # Create or update variable
        if name in target_scope.variables:
            # Update existing variable, preserving some attributes
            var = target_scope.variables[name]
            if var.is_readonly:
                raise ReadonlyVariableError(name)

            # Merge attributes (some attributes like EXPORT are additive)
            # But clear UNSET attribute when setting a value
            base_attributes = var.attributes & ~VarAttributes.UNSET  # Remove UNSET flag
            new_attributes = base_attributes | attributes
            existing_val = var.value
            if (isinstance(existing_val, (IndexedArray, AssociativeArray))
                    and not isinstance(value, (IndexedArray, AssociativeArray))):
                # bash: a plain scalar assigned to an EXISTING array sets
                # element 0 (key "0" for associative) and PRESERVES the array
                # container — ``a=(1 2 3); a=x`` yields a[0]=x with a still an
                # array; only a compound ``a=(...)`` replaces the whole array.
                # This also makes a temp-env prefix (``a=x cmd``) non-destructive:
                # apply_prefix snapshots the whole array (a deep copy) up front
                # and restore() puts that container back afterward.
                scalar = self._apply_attributes(
                    value,
                    new_attributes & ~(VarAttributes.ARRAY
                                       | VarAttributes.ASSOC_ARRAY))
                if isinstance(existing_val, AssociativeArray):
                    existing_val.set("0", scalar)
                else:
                    existing_val.set(0, scalar)
            else:
                # Transform with the FULL merged attribute set: a
                # declared-but-unset variable (``declare -u s; s=abc``) is
                # invisible to the `existing` lookup above, so its -u/-l/-i
                # attributes arrive only via this merge.
                var.value = self._apply_attributes(value, new_attributes)
            var.attributes = new_attributes
            self._debug_print(f"Updating variable in scope '{scope_name}': {name} = {var.value}")
        else:
            # Create new variable
            var = Variable(name=name,
                           value=self._apply_attributes(value, attributes),
                           attributes=attributes)
            target_scope.variables[name] = var
            self._debug_print(f"Setting variable in scope '{scope_name}': {name} = {var.value}")

        self._notify_path_changed(name)
        self._notify_variable_changed(name)

    def create_local(self, name: str, value: Optional[Any] = None,
                     attributes: VarAttributes = VarAttributes.NONE):
        """Create a local variable in the current scope.

        This is what the 'local' builtin uses.
        """
        if not self.is_in_function():
            raise RuntimeError("local: can only be used in a function")

        # Check if variable exists in outer scope and is readonly
        for scope in self.scope_stack[:-1]:  # Check all but current
            if name in scope.variables and scope.variables[name].is_readonly:
                raise ReadonlyVariableError(name)

        # Re-declaring a variable ALREADY local in this scope MERGES its
        # existing attributes (bash): ``local -u x=ab; local x+=cd`` keeps
        # -u so the appended value uppercases to ``ABCD``, and ``local -i
        # n=5; local n+=3`` keeps -i so the append arithmetic-adds to ``8``.
        # A same-scope tombstone (``local x; unset x``) does NOT count — a
        # later ``local x=v`` starts fresh.
        existing_local = self.current_scope.variables.get(name)
        redeclare = existing_local is not None and not existing_local.is_unset
        if redeclare:
            assert existing_local is not None  # narrow for type-checker
            attributes = existing_local.attributes | attributes
        else:
            # New local: inherit ONLY the EXPORT attribute of the variable it
            # shadows — probe: ``declare -xi N=5; f() { local N; declare -p N;
            # }; f`` prints ``declare -x N`` (no -i). The exported local is
            # what children see while the function runs.
            shadowed = self.get_variable_object(name)
            if shadowed is not None and shadowed.is_exported:
                attributes |= VarAttributes.EXPORT

        if value is not None:
            transformed_value = self._apply_attributes(value, attributes)
            var = Variable(name=name, value=transformed_value, attributes=attributes)
            self.current_scope.variables[name] = var
            self._debug_print(f"Creating local variable: {name} = {transformed_value}")
            self._notify_variable_changed(name)
        elif redeclare:
            # Value-less re-declare of an existing local (``local -u x=hi;
            # local x``): keep the value untouched, only merge the attributes
            # — bash does NOT re-apply a case attribute to the existing value
            # (``local x`` leaves x as ``hi``, now shown ``declare -u``).
            assert existing_local is not None  # narrow for type-checker
            existing_local.attributes = attributes
            self._debug_print(f"Re-declaring local (attrs only): {name}")
            self._notify_variable_changed(name)
        else:
            # Create a declared-but-unset local (``local var``): it
            # shadows any outer variable but reads as unset (bash:
            # ``local FOO; echo ${FOO-u}`` prints ``u``). The UNSET
            # attribute is the same tombstone mechanism unset_variable
            # uses; a later assignment in this scope clears it. No
            # variable_changed notification: bash leaves an exported
            # outer variable's env entry visible until the local is
            # actually assigned (probe: ``export FOO=outer; f() { local
            # FOO; printenv FOO; }; f`` prints ``outer``).
            var = Variable(name=name, value="",
                           attributes=attributes | VarAttributes.UNSET)
            self.current_scope.variables[name] = var
            self._debug_print(f"Creating unset local variable: {name}")

        self._notify_path_changed(name)

    def unset_variable(self, name: str):
        """Unset the innermost instance of *name* (bash dynamic scoping).

        bash keeps a per-name stack of instances; ``unset`` removes the
        MOST RECENT one, revealing the next-outer instance (``x=g;
        f(){ local x=f; g; }; g(){ unset x; echo $x; }; f`` prints ``g``)
        — with one exception: a local unset in its own declaring scope
        stays "local and unset" (default, non-``localvar_unset``
        semantics), so the outer instance does NOT show through in that
        scope. The tombstone Variable (attribute-less + UNSET) records
        exactly that state; bash also strips the local's attributes here
        (``local -i x=5; unset x`` shows ``declare -- x``). A repeated
        unset of the tombstone is a no-op, but the same cell seen from a
        DEEPER scope is removed outright like any outer instance.
        """
        # A dynamic special (SECONDS/RANDOM/BASHPID/SRANDOM/EPOCH*/LINENO) loses
        # its special behavior once unset and becomes an ordinary variable
        # (bash: after `unset SECONDS`, a later `SECONDS=foo` stores the literal
        # string; `unset EPOCHSECONDS` makes it a plain unset name). A readonly
        # special cannot be unset (bash: "cannot unset: readonly variable").
        # An active special has no stored Variable, so deactivate and return —
        # there is nothing to clear from the scope chain.
        if self._special.has_lifecycle(name):
            if self._special.attributes_for(name) & VarAttributes.READONLY:
                raise ReadonlyVariableError(name)
            self._special.deactivate(name)
            self._notify_variable_changed(name)
            return

        for scope in reversed(self.scope_stack):
            if name not in scope.variables:
                continue
            var = scope.variables[name]
            if var.is_readonly:
                raise ReadonlyVariableError(name)
            if scope is self.current_scope and scope is not self.global_scope:
                if var.is_unset:
                    return  # already local-and-unset: idempotent
                scope.variables[name] = Variable(
                    name=name, value="", attributes=VarAttributes.UNSET)
                self._debug_print(
                    f"Unsetting local {name} in its declaring scope "
                    f"'{scope.name}' (tombstone planted)")
            else:
                del scope.variables[name]
                self._debug_print(
                    f"Unsetting variable in scope '{scope.name}': {name}")
            self._notify_path_changed(name)
            self._notify_variable_changed(name)
            return

    def _apply_attributes(self, value: Any, attributes: VarAttributes) -> Any:
        """Apply attribute transformations to value."""
        # Don't transform arrays
        if isinstance(value, (IndexedArray, AssociativeArray)):
            return value

        # Convert to string for transformations
        str_value = str(value) if value is not None else ""

        # bash applies these in sequence (they are NOT mutually exclusive):
        # the INTEGER attribute arithmetic-evaluates the value first, then the
        # LOWERCASE/UPPERCASE attribute case-folds the resulting string.
        if attributes & VarAttributes.INTEGER:
            if str_value.strip():
                # _evaluate_integer raises ShellArithmeticError on a malformed
                # RHS / division by zero; let it propagate so the assignment
                # fails like bash (status 1 + message), rather than masking it
                # as 0. The plain-int (shell-less) fallback still returns 0.
                str_value = str(self._evaluate_integer(str_value))
            else:
                str_value = "0"

        # -u and -l are mutually exclusive; if both bits are somehow set,
        # bash applies NEITHER (declare -ul leaves the value unfolded).
        both_case = VarAttributes.UPPERCASE | VarAttributes.LOWERCASE
        if (attributes & both_case) != both_case:
            # declare -u/-l case-fold through the locale service: length-safe
            # (ß stays ß, not "SS") AND locale-gated — bash's declare -u folds
            # ASCII only under the C locale (`declare -u café` is CAFé), Unicode
            # under UTF-8 (CAFÉ). A shell-less ScopeManager (isolated tests)
            # falls back to the process-active locale, else leaves the value.
            loc = (self._shell.state.locale if self._shell is not None
                   else active_locale())
            if attributes & VarAttributes.UPPERCASE:
                return loc.upper(str_value) if loc else str_value
            if attributes & VarAttributes.LOWERCASE:
                return loc.lower(str_value) if loc else str_value

        return str_value

    def _evaluate_integer(self, expr: str) -> int:
        """Evaluate an INTEGER-attributed assignment's value.

        Uses the shell's full arithmetic evaluator (octal, hex, variables,
        operators). Every production ScopeManager has its shell wired in
        (Shell.__init__ calls set_shell before any command runs); the
        plain-int fallback exists only for bare ScopeManager construction
        in unit tests, where a simple conversion is enough.
        """
        expr = expr.strip()

        if self._shell is not None:
            from ..expansion.arithmetic import evaluate_arithmetic
            # Do NOT swallow arithmetic errors here: an -i assignment whose RHS
            # is a malformed expression or divides by zero must fail loudly with
            # the arithmetic-error message and status 1, exactly like $((...)).
            # (An undefined variable like `n=abc` is NOT an error — the
            # evaluator resolves it to 0 — so this only raises on genuine
            # syntax/division errors, matching bash.)
            return evaluate_arithmetic(expr, self._shell)

        try:
            return int(expr)
        except ValueError:
            return 0

    @property
    def current_scope(self) -> VariableScope:
        """Get the current (innermost) scope."""
        return self.scope_stack[-1]

    def _get_special_variable(self, name: str) -> Optional[Variable]:
        """Compute a special variable's value through the special registry.

        Returns a fresh ``Variable`` (its value produced on the spot) for any
        ACTIVE computed special, carrying that special's effective attributes
        (declared defaults such as ``INTEGER`` for RANDOM, OR-ed with the
        persistent readonly/export overlay). A deactivated dynamic special
        (``unset``) is no longer computed, so this returns ``None`` and the
        normal scope lookup takes over. A shell-view special whose compute needs
        a not-yet-wired shell (e.g. PIPESTATUS before ``set_shell``) also returns
        ``None``.

        UID/EUID/PPID are stored as real readonly-integer variables at shell
        startup (see ShellState.__init__), NOT computed here — that is what
        makes them assignment- and unset-proof and lists them in declare -p.
        """
        if not self._special.is_computed(name):
            return None
        value = self._special.compute_value(name, SpecialContext(self._special, self._shell))
        if value is None:
            return None
        return Variable(name=name, value=value,
                        attributes=self._special.attributes_for(name))

    def set_current_line_number(self, line_number: int):
        """Update the current line number for LINENO variable."""
        self._special.current_line_number = line_number

    def get_current_line_number(self) -> int:
        """Current line number backing $LINENO.

        Used to anchor nested executions (eval, trap actions) at the line
        of the command that invoked them, instead of resetting to 1 — see
        Shell.run_command's ``base_line``.
        """
        return self._special.current_line_number

    def is_in_function(self) -> bool:
        """Check if we're currently in a function scope."""
        return len(self.scope_stack) > 1

    def get_all_variables(self) -> Dict[str, str]:
        """Get all variables visible in current scope as strings."""
        result = {}

        # Start with global variables
        for name, var in self.global_scope.variables.items():
            if not var.is_unset:
                result[name] = var.as_string()

        # Override with variables from each scope (oldest to newest).
        # An UNSET tombstone shadows any outer-scope variable, so it must
        # remove the name rather than appear as an empty entry.
        for scope in self.scope_stack[1:]:  # Skip global scope
            for name, var in scope.variables.items():
                if var.is_unset:
                    result.pop(name, None)
                else:
                    result[name] = var.as_string()

        return result

    def all_variables_with_attributes(self) -> List[Variable]:
        """Get all visible variables as Variable objects."""
        # Use dict to handle shadowing correctly
        all_vars: Dict[str, Variable] = {}

        # Start with global variables
        for name, var in self.global_scope.variables.items():
            if not var.is_unset:
                all_vars[name] = var

        # Override with variables from each scope; UNSET tombstones shadow
        # (hide) outer-scope variables rather than appearing themselves.
        for scope in self.scope_stack[1:]:
            for name, var in scope.variables.items():
                if var.is_unset:
                    all_vars.pop(name, None)
                else:
                    all_vars[name] = var

        return list(all_vars.values())

    def all_exported_variables(self) -> List['Variable']:
        """Exported Variable objects across all scopes, shadow-resolved.

        Includes a declared-but-unset export (``export FOO`` with no value —
        EXPORT|UNSET, which bash shows as ``declare -x FOO``); a plain UNSET
        tombstone (``unset`` inside a function — UNSET without EXPORT) instead
        shadows any outer exported variable rather than appearing. Arrays are
        excluded (bash does not list them via ``export -p``). Used by
        ``export -p`` / bare ``export``.
        """
        effective: Dict[str, 'Variable'] = {}
        for scope in self.scope_stack:  # global first, inner scopes override
            for name, var in scope.variables.items():
                effective[name] = var
        return [v for v in effective.values() if v.is_exported and not v.is_array]

    def has_variable(self, name: str) -> bool:
        """Check if a variable exists in any scope."""
        for scope in reversed(self.scope_stack):
            if name in scope.variables:
                return True
        return False

    def find_exported_instance(self, name: str) -> Optional[Variable]:
        """Innermost EXPORTED, non-array, non-unset instance of *name*, else None.

        The live environment reflects the exported instance — NOT merely the
        innermost visible one. A non-exported local shadowing an exported
        outer variable does not hide the outer's environment entry (bash:
        ``x=g; f(){ local x=l; declare -gx x; printenv x; }`` prints ``g`` —
        the global is exported, the plain local is not). Skips arrays (never
        exported) and declared-but-unset cells (``export FOO`` has no entry
        until assigned).

        An exported dynamic special (``export RANDOM``) has no stored cell; its
        computed value is materialised as a SNAPSHOT — the env entry is the value
        at export/change time and does not track later reads (bash). Computing it
        here is why the observer captures that snapshot.
        """
        if (self._special.has_lifecycle(name)
                and (self._special.attributes_for(name) & VarAttributes.EXPORT)):
            return self._get_special_variable(name)
        for scope in reversed(self.scope_stack):
            var = scope.variables.get(name)
            if (var is not None and var.is_exported
                    and not var.is_array and not var.is_unset):
                return var
        return None

    def sync_exports_to_environment(self, env: Dict[str, str]):
        """Sync variables with EXPORT attribute to environment."""
        # First, get all shell variables
        all_shell_vars: set[str] = set()
        for scope in self.scope_stack:
            all_shell_vars.update(scope.variables.keys())

        # Remove from environment any variables that exist in shell but aren't exported
        for var_name in list(env.keys()):
            if var_name in all_shell_vars:
                var = self.get_variable_object(var_name)
                if var and not var.is_exported:
                    del env[var_name]

        # Collect all exported variables. Declared-but-unset variables
        # (UNSET attribute — ``export FOO`` of an unset name, ``local
        # FOO``) carry the attribute for future assignments but have no
        # environment entry yet (bash: ``export FOO; printenv FOO`` fails
        # until FOO is assigned).
        exported_vars = {}

        # Start with global scope
        for name, var in self.global_scope.variables.items():
            if var.is_exported and not var.is_array and not var.is_unset:
                exported_vars[name] = var.as_string()

        # Override with function scopes
        for scope in self.scope_stack[1:]:
            for name, var in scope.variables.items():
                if var.is_exported and not var.is_array and not var.is_unset:
                    exported_vars[name] = var.as_string()

        # Update environment
        env.update(exported_vars)

    def _find_variable_for_mutation(self, name: str,
                                    global_only: bool = False) -> Optional[Variable]:
        """Find a Variable for in-place ATTRIBUTE mutation, including
        declared-but-unset tombstones.

        Unlike get_variable_object (which hides UNSET variables), attribute
        changes must reach declared-but-unset names: ``declare -u y;
        declare -l y`` must let the second declaration flip y's case
        attribute even though y still reads as unset.

        ``global_only`` (``declare -g``) restricts the search to the global
        scope, past any same-named local — bash: ``local x; declare -gr x``
        marks the GLOBAL x readonly, leaving the local writable.
        """
        if global_only:
            return self.global_scope.variables.get(name)
        for scope in reversed(self.scope_stack):
            if name in scope.variables:
                return scope.variables[name]
        return None

    def apply_attribute(self, name: str, attributes: VarAttributes,
                        global_scope: bool = False):
        """Apply additional attributes to an existing variable.

        Readonly variables ACCEPT new attributes — readonly forbids
        changing the value, not the metadata (bash 5.2, probe-verified:
        ``readonly R=1; export R`` and ``readonly R=1; declare -i R``
        both succeed; only a value assignment fails). ``global_scope``
        (``declare -g``) targets the global instance past any local shadow.
        """
        # An active dynamic special has no stored cell — record the attribute on
        # its persistent overlay so ``readonly RANDOM`` / ``export SECONDS``
        # persist (and EXPORT materialises via the observer + find_exported_instance).
        if self._special.has_lifecycle(name):
            self._special.add_attributes(name, attributes)
            self._notify_variable_changed(name)
            return
        var = self._find_variable_for_mutation(name, global_only=global_scope)
        if var:
            # Handle mutually exclusive attributes
            new_attributes = var.attributes

            # If setting lowercase, remove uppercase
            if attributes & VarAttributes.LOWERCASE:
                new_attributes &= ~VarAttributes.UPPERCASE
            # If setting uppercase, remove lowercase
            if attributes & VarAttributes.UPPERCASE:
                new_attributes &= ~VarAttributes.LOWERCASE

            # Apply new attributes. The existing VALUE is left untouched:
            # bash applies -u/-l/-i transformations only to future
            # assignments (`u=abc; declare -u u` leaves $u as abc).
            new_attributes |= attributes
            var.attributes = new_attributes
            self._notify_variable_changed(name)

    def remove_attribute(self, name: str, attributes: VarAttributes,
                         global_scope: bool = False):
        """Remove attributes from an existing variable.

        ``global_scope`` (``declare -g``) targets the global instance past
        any local shadow.
        """
        # Active dynamic special: drop the attribute from its overlay. Removing
        # EXPORT (``export -n RANDOM``) lets the observer delete its env entry;
        # readonly cannot be removed (like any variable).
        if self._special.has_lifecycle(name):
            if (attributes & VarAttributes.READONLY
                    and (self._special.attributes_for(name) & VarAttributes.READONLY)):
                raise ReadonlyVariableError(name)
            self._special.remove_attributes(name, attributes)
            self._notify_variable_changed(name)
            return
        var = self._find_variable_for_mutation(name, global_only=global_scope)
        if var:
            # Cannot remove readonly attribute
            if attributes & VarAttributes.READONLY and var.is_readonly:
                raise ReadonlyVariableError(name)

            # Remove specified attributes. The observer re-derives any
            # environment entry — removing EXPORT deletes it (export -n).
            var.attributes &= ~attributes
            self._notify_variable_changed(name)
