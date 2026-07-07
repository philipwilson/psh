"""The authoritative variable-mutation service.

``VariableStore`` is the single transaction boundary for changing shell
variables. Every write — scalar assignment, append, array-element set/unset,
attribute add/remove, whole-variable unset, and (via the declaration engine)
``declare``/``local``/``export``/``readonly`` — goes through one of its
operations, so readonly enforcement, nameref resolution, negative-index
resolution, and the environment/PATH observers cannot be bypassed by a caller
that forgets a guard (the core-state appraisal's C2 finding).

Ownership model (core-state appraisal Phase 2)
----------------------------------------------
The store is a collaborator of :class:`~psh.core.scope.ScopeManager`, which
still owns the scope STACK, the observers, and the value-transform primitives
(``_apply_attributes`` / ``_evaluate_integer``). ``ScopeManager`` constructs one
store per manager and exposes it as ``scope_manager.store``; ``clone()`` makes a
fresh manager (hence a fresh store) so a child shell's writes never reach the
parent.

- Whole-variable operations (:meth:`assign`, :meth:`unset`,
  :meth:`add_attributes`, :meth:`remove_attributes`) are a thin, typed facade
  over the manager's existing authoritative methods.
- :meth:`append` is a first-class transaction: it resolves the nameref, reads
  the append base from the *target* scope (``-g`` reads the global instance,
  not a local shadow), computes the new value with the target's attributes
  (integer arithmetic vs textual concat vs array-element-0), and commits once.
- :meth:`set_element` / :meth:`unset_element` are the guarded element-commit
  primitives: they resolve the nameref, validate readonly BEFORE mutating,
  resolve a negative subscript exactly ONCE, create the array if absent, mutate
  the live container, and fire the observers. Callers compute the subscript and
  the element value (which is expansion-layer work) and hand the store the
  resolved pieces; they never touch ``.value.set()`` directly.

Splitting ``ScopeManager`` and injecting an arithmetic-evaluator protocol
(removing the store's reach into the manager's private transform helpers) is
deferred to Phase 4.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Optional, Union

from .exceptions import NamerefCycleError
from .variables import AssociativeArray, IndexedArray, VarAttributes

if TYPE_CHECKING:
    from .scope import ScopeManager


class TargetScope(Enum):
    """Which scope a declaration-family write targets.

    - ``DEFAULT``: dynamic-scoping default — the innermost instance of the name,
      or a new global when none exists (a bare ``declare`` at top level; inside
      a function a bare ``declare`` is local, expressed by the builtin passing
      ``DEFAULT`` with ``in_function`` — see :meth:`resolve_write_flags`).
    - ``LOCAL``: force the current scope (the ``local`` builtin).
    - ``GLOBAL``: force the global scope past any local shadow (``declare -g``).
    """
    DEFAULT = auto()
    LOCAL = auto()
    GLOBAL = auto()


class VariableStore:
    """Authoritative variable-mutation service (see module docstring)."""

    def __init__(self, scope_manager: "ScopeManager") -> None:
        self._sm = scope_manager

    # ------------------------------------------------------------------ #
    # Whole-variable operations — typed facade over the ScopeManager
    # authority (which already enforces readonly + fires the observers).
    # ------------------------------------------------------------------ #

    def assign(self, name: str, value: object, *,
               attributes: VarAttributes = VarAttributes.NONE,
               local: bool = False, global_scope: bool = False,
               skip_temp_env: bool = False) -> None:
        """Assign ``value`` to ``name`` in the appropriate scope.

        See :meth:`ScopeManager.set_variable` for the full local/global/
        temp-env target-selection contract; this is the store's public entry
        point for it. Raises :class:`ReadonlyVariableError` (unchanged state)
        for a readonly target.
        """
        self._sm.set_variable(name, value, attributes=attributes, local=local,
                              global_scope=global_scope, skip_temp_env=skip_temp_env)

    def unset(self, name: str) -> None:
        """Unset the innermost instance of ``name`` (dynamic scoping)."""
        self._sm.unset_variable(name)

    def add_attributes(self, name: str, attributes: VarAttributes, *,
                       global_scope: bool = False) -> None:
        """Add attributes to an existing (possibly declared-but-unset) variable."""
        self._sm.apply_attribute(name, attributes, global_scope=global_scope)

    def remove_attributes(self, name: str, attributes: VarAttributes, *,
                          global_scope: bool = False) -> None:
        """Remove attributes from a variable (e.g. ``export -n`` clears EXPORT)."""
        self._sm.remove_attribute(name, attributes, global_scope=global_scope)

    # ------------------------------------------------------------------ #
    # Append — one transaction, target-scope aware.
    # ------------------------------------------------------------------ #

    def append(self, name: str, value: str, *,
               attributes: VarAttributes = VarAttributes.NONE,
               local: bool = False, global_scope: bool = False,
               skip_temp_env: bool = False) -> None:
        """Append ``value`` to ``name`` (``NAME+=value``) as one transaction.

        The append BASE is read from the scope the write will target — so
        ``declare -g x+=A`` reads (and updates) the GLOBAL ``x`` even under a
        local shadow (bash), and ``export -i n; export n+=3`` appends
        arithmetically because the base's INTEGER attribute is honored. The
        computation:

        - INTEGER target: arithmetic ``(base)+(value)`` (empty value = +0);
        - array target: update element 0 in place (integer-add or concat +
          case-fold), preserving the container;
        - otherwise: textual concat, then the target's ``-u``/``-l`` case-fold.

        The result is committed through :meth:`assign` (so readonly enforcement
        and the observers still apply). A cyclic nameref raises
        :class:`NamerefCycleError`, like a direct write.
        """
        target = self._sm.resolve_nameref_name(name)
        base_var = self._instance_in_write_target(
            target, global_scope=global_scope, skip_temp_env=skip_temp_env)
        container = base_var.value if base_var is not None else None

        if isinstance(container, (IndexedArray, AssociativeArray)):
            # Scalar append to an array updates element 0 (bash), preserving the
            # container. Work on a copy so a rejected commit never leaves a
            # half-mutated live array.
            new_container = container.copy()
            key: Union[int, str] = 0 if isinstance(new_container, IndexedArray) else '0'
            old0 = new_container.get(key) or ''  # type: ignore[arg-type]
            base_attrs = base_var.attributes if base_var is not None else VarAttributes.NONE
            if base_attrs & VarAttributes.INTEGER and value.strip():
                new0: object = self._sm._evaluate_integer(f"({old0 or 0})+({value})")
            else:
                new0 = self._sm._apply_attributes(str(old0) + value, base_attrs)
            new_container.set(key, str(new0))  # type: ignore[arg-type]
            self.assign(name, new_container, attributes=attributes, local=local,
                        global_scope=global_scope, skip_temp_env=skip_temp_env)
            return

        old = '' if base_var is None or base_var.value is None else str(base_var.value)
        base_attrs = base_var.attributes if base_var is not None else VarAttributes.NONE
        if base_attrs & VarAttributes.INTEGER and value.strip():
            # Hand set_variable's INTEGER transform the arithmetic expression so
            # the append evaluates numerically (matches bash `declare -i`).
            new_value: object = f"({old or 0})+({value})"
        else:
            new_value = old + value
        self.assign(name, new_value, attributes=attributes, local=local,
                    global_scope=global_scope, skip_temp_env=skip_temp_env)

    # ------------------------------------------------------------------ #
    # Array-element operations — guarded commit primitives.
    # ------------------------------------------------------------------ #

    def set_element(self, name: str, key: Union[int, str], value: str) -> None:
        """Set one array element to ``value`` (the FINAL, already-computed value).

        One guarded transaction: resolve the nameref, validate readonly BEFORE
        mutating, resolve a negative integer subscript exactly once (owns the
        one negative-index formula — callers pass the raw subscript), create an
        indexed array if the name is unset, then mutate the live container and
        fire the observers. Integer/case/append VALUE computation is the
        caller's (expansion-layer) job; the store commits the result.

        Raises :class:`ReadonlyVariableError` for a readonly target and
        :class:`ArraySubscriptError` for an out-of-range negative subscript —
        in both cases the container is left unchanged.
        """
        from .exceptions import ReadonlyVariableError
        target = self._sm.resolve_nameref_name(name)
        var = self._sm.get_variable_object(target)
        if var is not None and var.is_readonly:
            raise ReadonlyVariableError(target)

        if var is not None and isinstance(var.value, IndexedArray):
            idx = var.value.resolve_write_index(int(key)) if isinstance(key, int) else 0
            var.value.set(idx, value)
        elif var is not None and isinstance(var.value, AssociativeArray):
            var.value.set(str(key), value)
        else:
            # Unset (or a plain scalar with no array) — create a fresh indexed
            # array through the manager so the ARRAY attribute + observers apply.
            arr = IndexedArray()
            arr.set(int(key) if isinstance(key, int) else 0, value)
            self._sm.set_variable(target, arr, attributes=VarAttributes.ARRAY)
            return
        self._sm._notify_path_changed(target)
        self._sm._notify_variable_changed(target)

    def unset_element(self, name: str, key: Union[int, str]) -> None:
        """Remove one array element as one guarded transaction.

        Resolves the nameref, validates readonly BEFORE mutating, resolves a
        negative integer subscript with the SAME one-past-the-top formula as a
        write (so read/write/unset agree on sparse arrays), removes the element
        from the live container, and fires the observers. Unsetting an element
        of a missing name is a silent no-op (bash). Raises
        :class:`ReadonlyVariableError` / :class:`ArraySubscriptError` without
        mutating.
        """
        from .exceptions import ReadonlyVariableError
        target = self._sm.resolve_nameref_name(name)
        var = self._sm.get_variable_object(target)
        if var is None:
            return
        if var.is_readonly:
            raise ReadonlyVariableError(target)
        if isinstance(var.value, IndexedArray):
            idx = var.value.resolve_write_index(int(key)) if isinstance(key, int) else 0
            var.value.unset(idx)
        elif isinstance(var.value, AssociativeArray):
            var.value.unset(str(key))
        else:
            return
        self._sm._notify_path_changed(target)
        self._sm._notify_variable_changed(target)

    # ------------------------------------------------------------------ #
    # Scope-selection helper shared by append (and, later, the declaration
    # engine): the variable instance a write to ``name`` would read/update,
    # honoring ``-g`` (global) and a temp-env prefix layer.
    # ------------------------------------------------------------------ #

    def _instance_in_write_target(self, name: str, *, global_scope: bool,
                                  skip_temp_env: bool):
        if global_scope:
            var = self._sm.global_scope.variables.get(name)
            return None if (var is not None and var.is_unset) else var
        if skip_temp_env:
            sc = self._sm._innermost_scope_with(name, skip_temp_env=True)
            var = sc.variables.get(name) if sc is not None else None
            return None if (var is not None and var.is_unset) else var
        # Default: the innermost visible instance (tombstones hidden).
        return self._sm.get_variable_object(name)

    @staticmethod
    def resolve_write_flags(target: TargetScope, in_function: bool) -> tuple[bool, bool]:
        """Map a :class:`TargetScope` (+ whether we're in a function) to the
        ``(local, global_scope)`` flag pair the store/manager writes take.

        ``DEFAULT`` inside a function is local (a bare ``declare NAME`` == ``local
        NAME``); at top level it is a global. ``LOCAL`` is always the current
        scope; ``GLOBAL`` is always the global scope. Used by the declaration
        engine so scope policy lives in one place.
        """
        if target is TargetScope.GLOBAL:
            return (False, True)
        if target is TargetScope.LOCAL:
            return (True, False)
        return (in_function, False)  # DEFAULT

    # Re-exported so callers can catch a cyclic-nameref write without importing
    # from two modules.
    NamerefCycleError = NamerefCycleError

    def resolve_nameref_name(self, name: str) -> str:
        """Follow a nameref chain to its final target name (see ScopeManager)."""
        return self._sm.resolve_nameref_name(name)

    def get_variable_object(self, name: str) -> Optional[object]:
        """Convenience read-through to the manager (no nameref deref)."""
        return self._sm.get_variable_object(name)
