"""Hierarchical variable scope management with attribute support."""

import os
import random
import time
from typing import Any, Dict, List, Optional

from .exceptions import ReadonlyVariableError
from .variables import AssociativeArray, IndexedArray, VarAttributes, Variable


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

        # Special variable state
        self._shell_start_time = time.time()
        self._current_line_number = 1

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

        # Apply attribute transformations
        transformed_value = self._apply_attributes(value, attributes)

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
                target_scope = None
                for scope in reversed(self.scope_stack):
                    if name in scope.variables:
                        var = scope.variables[name]
                        # Skip unset tombstones when searching for existing variables
                        if not var.is_unset:
                            target_scope = scope
                            scope_name = scope.name
                            break

                if target_scope is None:
                    # Variable doesn't exist anywhere, create in global scope
                    target_scope = self.global_scope
                    scope_name = "global"

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
            var.value = transformed_value  # Use the already-transformed value
            var.attributes = new_attributes
            self._debug_print(f"Updating variable in scope '{scope_name}': {name} = {var.value}")
        else:
            # Create new variable
            var = Variable(name=name, value=transformed_value, attributes=attributes)
            target_scope.variables[name] = var
            self._debug_print(f"Setting variable in scope '{scope_name}': {name} = {var.value}")

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

        if value is not None:
            transformed_value = self._apply_attributes(value, attributes)
            var = Variable(name=name, value=transformed_value, attributes=attributes)
            self.current_scope.variables[name] = var
            self._debug_print(f"Creating local variable: {name} = {transformed_value}")
        else:
            # Create unset local variable (shadows global but has no value)
            var = Variable(name=name, value="", attributes=attributes)
            self.current_scope.variables[name] = var
            self._debug_print(f"Creating unset local variable: {name}")

    def unset_variable(self, name: str):
        """Unset a variable in the appropriate scope."""
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
            return

        # If not in current scope and we're in a function, check parent scopes
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
                    return

        # Check global scope as fallback
        if name in self.global_scope.variables:
            var = self.global_scope.variables[name]
            if var.is_readonly:
                raise ReadonlyVariableError(name)
            del self.global_scope.variables[name]
            self._debug_print(f"Unsetting variable in global scope: {name}")

    def _apply_attributes(self, value: Any, attributes: VarAttributes) -> Any:
        """Apply attribute transformations to value."""
        # Don't transform arrays
        if isinstance(value, (IndexedArray, AssociativeArray)):
            return value

        # Convert to string for transformations
        str_value = str(value) if value is not None else ""

        if attributes & VarAttributes.UPPERCASE:
            return str_value.upper()
        elif attributes & VarAttributes.LOWERCASE:
            return str_value.lower()
        elif attributes & VarAttributes.INTEGER:
            # Evaluate arithmetic expressions for integer variables
            if str_value.strip():
                try:
                    # Simple integer evaluation (would need full arithmetic evaluator)
                    # For now, just try to convert or evaluate simple expressions
                    result = self._evaluate_integer(str_value)
                    return str(result)  # Store as string, but evaluated as integer
                except (ValueError, ArithmeticError):
                    return "0"
            return "0"

        return str_value

    def _evaluate_integer(self, expr: str) -> int:
        """Evaluate integer expressions using the shell's arithmetic evaluator."""
        # Remove whitespace
        expr = expr.strip()

        # Always use the shell's arithmetic evaluator if available
        # This properly handles octal (010), hex (0x10), and arithmetic expressions
        if hasattr(self, '_shell') and self._shell:
            from ..expansion.arithmetic import evaluate_arithmetic
            try:
                # Evaluate the expression using the helper function
                result = evaluate_arithmetic(expr, self._shell)
                return result
            except (ValueError, ArithmeticError):
                # If evaluation fails, return 0
                return 0

        # Fallback when no shell context: try to use the arithmetic tokenizer
        # to handle octal and hex properly
        try:
            from ..expansion.arithmetic import ArithmeticEvaluator, ArithParser, ArithTokenizer

            # Create a minimal evaluator without shell context
            class MinimalShell:
                def __init__(self, scope_manager):
                    self.state = type('State', (), {'get_variable': lambda _, name, default='0': scope_manager.get_variable(name, default)})()

            tokenizer = ArithTokenizer(expr)
            tokens = tokenizer.tokenize()
            parser = ArithParser(tokens)
            ast = parser.parse()

            # Use minimal evaluator
            minimal_shell = MinimalShell(self)
            evaluator = ArithmeticEvaluator(minimal_shell)
            return evaluator.evaluate(ast)

        except (ValueError, ArithmeticError, TypeError):
            # Last resort: simple conversion, but this loses octal support
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
        if name == 'LINENO':
            # Return current line number (simplified implementation)
            return Variable(name='LINENO', value=str(self._current_line_number))
        elif name == 'SECONDS':
            # Return seconds since shell start
            elapsed = int(time.time() - self._shell_start_time)
            return Variable(name='SECONDS', value=str(elapsed))
        elif name == 'RANDOM':
            # Return random number between 0 and 32767 (bash compatible)
            return Variable(name='RANDOM', value=str(random.randint(0, 32767)))
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
        all_shell_vars = set()
        for scope in self.scope_stack:
            all_shell_vars.update(scope.variables.keys())

        # Remove from environment any variables that exist in shell but aren't exported
        for var_name in list(env.keys()):
            if var_name in all_shell_vars:
                var = self.get_variable_object(var_name)
                if var and not var.is_exported:
                    del env[var_name]

        # Collect all exported variables
        exported_vars = {}

        # Start with global scope
        for name, var in self.global_scope.variables.items():
            if var.is_exported and not var.is_array:
                exported_vars[name] = var.as_string()

        # Override with function scopes
        for scope in self.scope_stack[1:]:
            for name, var in scope.variables.items():
                if var.is_exported and not var.is_array:
                    exported_vars[name] = var.as_string()

        # Update environment
        env.update(exported_vars)

    def apply_attribute(self, name: str, attributes: VarAttributes):
        """Apply additional attributes to an existing variable."""
        var = self.get_variable_object(name)
        if var:
            # Check readonly before modifying attributes
            if var.is_readonly and attributes != VarAttributes.READONLY:
                raise ReadonlyVariableError(name)

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

    def remove_attribute(self, name: str, attributes: VarAttributes):
        """Remove attributes from an existing variable."""
        var = self.get_variable_object(name)
        if var:
            # Cannot remove readonly attribute
            if attributes & VarAttributes.READONLY and var.is_readonly:
                raise ReadonlyVariableError(name)

            # Remove specified attributes
            var.attributes &= ~attributes

            # If removing export, ensure it's removed from environment
            if attributes & VarAttributes.EXPORT:
                # The variable is no longer exported, so it won't be synced to env
                # in the next sync_exports_to_environment call
                pass
