"""Hierarchical variable scope management with attribute support."""

import os
import random
import time
from typing import Any, Callable, Dict, List, Optional

from .exceptions import ReadonlyVariableError
from .variables import AssociativeArray, IndexedArray, VarAttributes, Variable

# Variables whose value is computed on read but whose assignment is honored
# (SECONDS resets the elapsed-time baseline; RANDOM seeds the generator).
# RANDOM additionally MUTATES generator state on each read, so name-only
# inspection paths (nameref resolution) must not route through its read.
_COMPUTED_SPECIAL_VARS = frozenset({'SECONDS', 'RANDOM'})


def _intrand32(seed: int) -> int:
    """Park-Miller minimal-standard generator with Schrage's method.

    This is bash's ``intrand32`` (lib/sh/random.c); combined with the
    high/low 16-bit XOR fold in the RANDOM read path it reproduces bash
    5.x's ``$RANDOM`` sequence value-for-value for a given seed.
    """
    s = seed & 0xFFFFFFFF
    if s == 0:
        s = 123459876  # bash's guard against a zero seed inside the generator
    h = s // 127773
    low = s % 127773
    t = 16807 * low - 2836 * h
    if t < 0:
        t += 0x7FFFFFFF
    return t


class VariableScope:
    """Represents a single variable scope with attribute-aware variables."""

    def __init__(self, parent: Optional['VariableScope'] = None, name: Optional[str] = None):
        self.variables: Dict[str, Variable] = {}
        self.parent = parent
        self.name = name or 'anonymous'

    def __repr__(self):
        return f"VariableScope(name={self.name}, vars={list(self.variables.keys())})"

    def copy(self) -> 'VariableScope':
        """Create a deep copy of this scope."""
        new_scope = VariableScope(parent=None, name=self.name)
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

        # Special variable state
        self._shell_start_time = time.time()
        self._current_line_number = 1

        # Settable computed variables (SECONDS, RANDOM). These are computed
        # on read, but assignment is honored: SECONDS=N resets the baseline,
        # RANDOM=N seeds the generator (bash behavior). State recorded here:
        #   _seconds_base / _seconds_assigned_at : if set, SECONDS reads as
        #       base + (now - assigned_at); otherwise now - shell_start.
        #   _random_seed : if not None, RANDOM is reproducible from this seed.
        #   _computed_special_deactivated : names that have been `unset` and
        #       so lost their special behavior, becoming ordinary variables
        #       (bash: after `unset SECONDS`, SECONDS is a plain variable).
        self._seconds_base: Optional[int] = None
        self._seconds_assigned_at: float = 0.0
        self._random_seed: Optional[int] = None
        self._random_last_value: int = 0
        self._computed_special_deactivated: set = set()

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
        # Dynamically computed special variables (e.g. RANDOM, SECONDS) are
        # never namerefs, and probing them through get_variable_object here
        # would fire their side effects (advancing the RANDOM generator) on
        # what is meant to be a name-only inspection. Resolve them to
        # themselves without touching the computed read path.
        if (name in _COMPUTED_SPECIAL_VARS
                and name not in self._computed_special_deactivated):
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

    def get_declared_variable_object(self, name: str) -> Optional[Variable]:
        """Scope-chain lookup that also finds declared-but-unset variables.

        ``export FOO`` / ``declare -i N`` / ``local -x V`` record
        attributes on a variable that still READS as unset (UNSET flag;
        get_variable_object returns None for it). ``declare -p`` must
        nevertheless display it (bash: ``declare -x FOO``). A plain
        ``unset`` tombstone carries no attribute besides UNSET and stays
        hidden — an attribute-less declaration (bare ``declare FOO``) is
        representationally identical, so it stays hidden too (bash would
        show ``declare -- FOO``; accepted divergence).
        """
        for scope in reversed(self.scope_stack):
            if name in scope.variables:
                var = scope.variables[name]
                if var.is_unset and not (var.attributes & ~VarAttributes.UNSET):
                    return None  # plain unset tombstone (or bare declaration)
                return var
        return None

    def set_variable(self, name: str, value: Any,
                     attributes: VarAttributes = VarAttributes.NONE,
                     local: bool = False):
        """Set variable with attributes in appropriate scope.

        Args:
            name: Variable name
            value: Variable value
            attributes: Variable attributes to apply
            local: If True, set in current scope. If False and in function,
                   check if variable exists in current scope first
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

        # Settable computed variables: SECONDS=N resets the elapsed-time
        # baseline; RANDOM=N seeds the reproducible generator. bash honors
        # the assignment without storing a plain variable (the value stays
        # computed on read). Skipped once the name has been `unset` (it then
        # behaves as an ordinary variable) and for array assignments.
        if (name in _COMPUTED_SPECIAL_VARS
                and name not in self._computed_special_deactivated
                and not (attributes & VarAttributes.NAMEREF)
                and not isinstance(value, (IndexedArray, AssociativeArray))):
            n = self._coerce_computed_special_int(value)
            if name == 'SECONDS':
                self._seconds_base = n
                self._seconds_assigned_at = time.time()
            else:  # RANDOM
                self._random_seed = n & 0xFFFFFFFF
                self._random_last_value = 0
            # No variable_changed/env-sync notification: these stay computed
            # (never stored, never exported), and reading them to sync would
            # spuriously advance the RANDOM generator.
            return

        # Check if variable exists
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
        if local or len(self.scope_stack) == 1:
            # Set in current scope (global or explicitly local)
            target_scope = self.current_scope
            scope_name = target_scope.name
        else:
            # In a function, not explicitly local
            # Check if there's an unset tombstone in current scope first
            if name in self.current_scope.variables and self.current_scope.variables[name].is_unset:
                # Replace unset tombstone in current scope
                target_scope = self.current_scope
                scope_name = self.current_scope.name
            else:
                # Search for existing variable in scope chain (bash behavior)
                found_scope: Optional[VariableScope] = None
                for scope in reversed(self.scope_stack):
                    if name in scope.variables:
                        var = scope.variables[name]
                        # Skip unset tombstones when searching for existing variables
                        if not var.is_unset:
                            found_scope = scope
                            break

                if found_scope is None:
                    # Variable doesn't exist anywhere, create in global scope
                    target_scope = self.global_scope
                    scope_name = "global"
                else:
                    target_scope = found_scope
                    scope_name = found_scope.name

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

        # bash: a local inherits the EXPORT attribute (and only that) of
        # the variable it shadows — probe: ``declare -xi N=5; f() { local
        # N; declare -p N; }; f`` prints ``declare -x N`` (no -i). The
        # exported local is what children see while the function runs.
        shadowed = self.get_variable_object(name)
        if shadowed is not None and shadowed.is_exported:
            attributes |= VarAttributes.EXPORT

        if value is not None:
            transformed_value = self._apply_attributes(value, attributes)
            var = Variable(name=name, value=transformed_value, attributes=attributes)
            self.current_scope.variables[name] = var
            self._debug_print(f"Creating local variable: {name} = {transformed_value}")
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
        """Unset a variable in the appropriate scope."""
        # SECONDS/RANDOM lose their special computed behavior once unset and
        # become ordinary variables (bash: after `unset SECONDS`, a later
        # `SECONDS=foo` stores the literal string). Record the deactivation
        # and drop any recorded baseline/seed, then fall through so the name
        # is also cleared from the scope chain.
        if name in _COMPUTED_SPECIAL_VARS:
            self._computed_special_deactivated.add(name)
            if name == 'SECONDS':
                self._seconds_base = None
            else:
                self._random_seed = None

        # Check current scope first
        if name in self.current_scope.variables:
            var = self.current_scope.variables[name]
            if var.is_readonly:
                raise ReadonlyVariableError(name)
            del self.current_scope.variables[name]
            self._debug_print(f"Unsetting variable in scope '{self.current_scope.name}': {name}")

            # If we're in a function scope, create an unset tombstone
            # to prevent fallback to parent scopes
            if len(self.scope_stack) > 1:
                unset_var = Variable(name=name, value="", attributes=VarAttributes.UNSET)
                self.current_scope.variables[name] = unset_var
                self._debug_print(f"Creating unset tombstone for {name} in scope '{self.current_scope.name}'")
            self._notify_path_changed(name)
            self._notify_variable_changed(name)
            return

        # If not in current scope and we're in a function, check parent scopes
        # (the loop includes the global scope — scope_stack[0] — so there is
        # no separate global fallback; when not in a function the current
        # scope IS the global scope and the branch above handled it).
        if len(self.scope_stack) > 1:
            # Search for the variable in parent scopes
            for scope in reversed(self.scope_stack[:-1]):  # Skip current scope
                if name in scope.variables:
                    var = scope.variables[name]
                    if var.is_readonly:
                        raise ReadonlyVariableError(name)
                    del scope.variables[name]
                    self._debug_print(f"Unsetting variable in parent scope '{scope.name}': {name}")

                    # Create unset tombstone in current scope
                    unset_var = Variable(name=name, value="", attributes=VarAttributes.UNSET)
                    self.current_scope.variables[name] = unset_var
                    self._debug_print(f"Creating unset tombstone for {name} in current scope")
                    self._notify_path_changed(name)
                    self._notify_variable_changed(name)
                    return

    def _coerce_computed_special_int(self, value: Any) -> int:
        """Parse an assignment to SECONDS/RANDOM as a plain integer.

        bash parses these as a simple signed decimal integer, NOT a full
        arithmetic expression: ``SECONDS=0x10`` and ``RANDOM=x`` both yield
        0, while ``SECONDS=-5`` is accepted. (``SECONDS=$((2+3))`` works
        because the arithmetic is expanded to ``5`` before assignment.)
        """
        try:
            return int(str(value).strip())
        except (ValueError, AttributeError):
            return 0

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
            if attributes & VarAttributes.UPPERCASE:
                return str_value.upper()
            if attributes & VarAttributes.LOWERCASE:
                return str_value.lower()

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
        """Handle special shell variables that are computed dynamically."""
        # SECONDS / RANDOM lose their special behavior once `unset`, becoming
        # ordinary variables (bash). Returning None lets the normal scope
        # lookup take over.
        if name in self._computed_special_deactivated:
            return None
        if name == 'LINENO':
            # Return current line number (simplified implementation)
            return Variable(name='LINENO', value=str(self._current_line_number))
        elif name == 'SECONDS':
            # Seconds since shell start, or since the last `SECONDS=N`
            # assignment reset the baseline (bash: SECONDS=N then reads
            # return N + elapsed-since-assignment).
            if self._seconds_base is not None:
                elapsed = self._seconds_base + int(
                    time.time() - self._seconds_assigned_at)
            else:
                elapsed = int(time.time() - self._shell_start_time)
            return Variable(name='SECONDS', value=str(elapsed))
        elif name == 'RANDOM':
            # Random number in 0..32767. If RANDOM=N seeded the generator,
            # the sequence is reproducible and matches bash value-for-value
            # (bash 5.x Park-Miller minimal-standard generator). Otherwise
            # fall back to Python's RNG for an unpredictable value.
            if self._random_seed is not None:
                self._random_seed = _intrand32(self._random_seed)
                value = ((self._random_seed >> 16)
                         ^ (self._random_seed & 0xFFFF)) & 0x7FFF
            else:
                value = random.randint(0, 32767)
            return Variable(name='RANDOM', value=str(value))
        elif name == 'EPOCHSECONDS':
            return Variable(name='EPOCHSECONDS', value=str(int(time.time())))
        elif name == 'EPOCHREALTIME':
            return Variable(name='EPOCHREALTIME', value=f"{time.time():.6f}")
        elif name == 'PPID':
            if self._shell is not None:
                return Variable(name='PPID',
                                value=str(self._shell.state.initial_ppid))
        elif name == 'UID':
            return Variable(name='UID', value=str(os.getuid()))
        elif name == 'EUID':
            return Variable(name='EUID', value=str(os.geteuid()))
        elif name == 'PIPESTATUS':
            if self._shell is not None:
                from .variables import IndexedArray, VarAttributes
                arr = IndexedArray()
                for i, st in enumerate(self._shell.state.pipestatus):
                    arr.set(i, str(st))
                return Variable(name='PIPESTATUS', value=arr,
                                attributes=VarAttributes.ARRAY)
        elif name == 'FUNCNAME':
            # Return current function name if in function
            if self._shell and hasattr(self._shell, 'state') and self._shell.state.function_stack:
                func_name = self._shell.state.function_stack[-1]
                return Variable(name='FUNCNAME', value=func_name)
            else:
                # Not in a function, return empty string (bash behavior)
                return Variable(name='FUNCNAME', value='')

        return None

    def set_current_line_number(self, line_number: int):
        """Update the current line number for LINENO variable."""
        self._current_line_number = line_number

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

    def has_variable(self, name: str) -> bool:
        """Check if a variable exists in any scope."""
        for scope in reversed(self.scope_stack):
            if name in scope.variables:
                return True
        return False

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

    def _find_variable_for_mutation(self, name: str) -> Optional[Variable]:
        """Find a Variable for in-place ATTRIBUTE mutation, including
        declared-but-unset tombstones.

        Unlike get_variable_object (which hides UNSET variables), attribute
        changes must reach declared-but-unset names: ``declare -u y;
        declare -l y`` must let the second declaration flip y's case
        attribute even though y still reads as unset.
        """
        for scope in reversed(self.scope_stack):
            if name in scope.variables:
                return scope.variables[name]
        return None

    def apply_attribute(self, name: str, attributes: VarAttributes):
        """Apply additional attributes to an existing variable.

        Readonly variables ACCEPT new attributes — readonly forbids
        changing the value, not the metadata (bash 5.2, probe-verified:
        ``readonly R=1; export R`` and ``readonly R=1; declare -i R``
        both succeed; only a value assignment fails).
        """
        var = self._find_variable_for_mutation(name)
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

    def remove_attribute(self, name: str, attributes: VarAttributes):
        """Remove attributes from an existing variable."""
        var = self._find_variable_for_mutation(name)
        if var:
            # Cannot remove readonly attribute
            if attributes & VarAttributes.READONLY and var.is_readonly:
                raise ReadonlyVariableError(name)

            # Remove specified attributes. The observer re-derives any
            # environment entry — removing EXPORT deletes it (export -n).
            var.attributes &= ~attributes
            self._notify_variable_changed(name)
