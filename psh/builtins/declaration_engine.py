"""One declaration engine behind ``declare``/``export``/``readonly``.

The builtins appraisal (finding 3) reproduced four defects caused by the
declaration-family builtins each reimplementing shared mechanics instead of
routing through one engine:

1. ``declare -i n=2; export n+=3`` gave 23 — ``export`` concatenated textually
   before applying the integer attribute, ignoring the canonical append.
2. ``a=(x y); declare -A a`` converted (rc=0) instead of failing (rc=1) and
   preserving the indexed array.
3. ``x=G; f(){ local x=L; declare -g x+=A; }`` appended through the local
   shadow (LA) instead of the ``-g`` target's global base (GA).
4. ``declare -pn`` listed every variable instead of only namerefs.

This module centralizes the SCALAR assignment/append commit — the drift locus
for defects 1 and 3 — onto the authoritative :class:`VariableStore`, plus the
array-conversion validation (defect 2). ``declare`` and ``export`` adapt their
own option parsing into a :class:`DeclarationRequest` and call the engine;
``readonly`` reuses this via its existing delegation to ``declare -r``.

Scope of the consolidation: the scalar/append path and array-conversion check
are unified here. ``local``'s scalar path deliberately stays on
``ScopeManager.create_local`` (its local-specific redeclare-merge,
exported-shadow inheritance, and same-scope tombstone semantics are not the
generic store contract); folding ``create_local`` into the store is Phase 4
work. Full array-initialization and print-listing migration onto the request
model is likewise incremental — those paths reference the shared
:class:`ArrayKind`/:class:`PrintMode` vocabulary but keep their existing,
expansion-coupled builtin logic for now.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

from ..core import TargetScope, VarAttributes
from ..core.variable_store import VariableStore

if TYPE_CHECKING:
    from ..core.variables import Variable
    from ..shell import Shell


class ArrayKind(Enum):
    """The array shape a declaration requests (``-a`` vs ``-A``)."""
    INDEXED = auto()
    ASSOC = auto()


class PrintMode(Enum):
    """How a declaration lists rather than mutates (``-p`` reusable form)."""
    REUSABLE = auto()


@dataclass(frozen=True)
class DeclarationAssignment:
    """One ``NAME[=value]`` / ``NAME+=value`` operand of a declaration."""
    name: str
    value: Optional[str]     # None for a bare-name declaration
    append: bool = False     # True for NAME+=value


@dataclass(frozen=True)
class DeclarationRequest:
    """A parsed declaration-family command's target + attributes.

    ``target_scope`` is the declare-family scope selector (DEFAULT is local
    inside a function, global at top level; GLOBAL is ``-g``; LOCAL is the
    ``local`` builtin). ``skip_temp_env`` steps past a command's temp-env prefix
    layer to the variable's real home (``export``/``cd``). ``array_kind`` /
    ``print_mode`` name the requested array shape / listing mode for the paths
    that consume them.
    """
    target_scope: TargetScope = TargetScope.DEFAULT
    add_attributes: VarAttributes = VarAttributes.NONE
    remove_attributes: VarAttributes = VarAttributes.NONE
    array_kind: Optional[ArrayKind] = None
    print_mode: Optional[PrintMode] = None
    skip_temp_env: bool = False

    def write_flags(self, in_function: bool) -> tuple[bool, bool]:
        """The ``(local, global_scope)`` store flags for this request's scope."""
        return VariableStore.resolve_write_flags(self.target_scope, in_function)


class DeclarationEngine:
    """Executes the shared declaration mechanics via the variable store."""

    def __init__(self, shell: "Shell") -> None:
        self.shell = shell

    def commit_scalar(self, name: str, value: Optional[str], *, append: bool,
                      add_attributes: VarAttributes = VarAttributes.NONE,
                      local: bool = False, global_scope: bool = False,
                      skip_temp_env: bool = False) -> None:
        """Assign or append a scalar through the store — the single commit
        chokepoint for declaration-family scalar writes.

        ``append`` routes through :meth:`VariableStore.append`, which reads the
        append base from the SAME scope the write targets (so ``declare -g x+=``
        reads the global base) and applies the target's integer/case attribute
        (so ``export n+=`` on an integer appends arithmetically). A plain
        assignment routes through :meth:`VariableStore.assign`. Raises
        :class:`ReadonlyVariableError` for a readonly target, unchanged.
        """
        store = self.shell.state.scope_manager.store
        if append:
            store.append(name, value or '', attributes=add_attributes,
                         local=local, global_scope=global_scope,
                         skip_temp_env=skip_temp_env)
        else:
            store.assign(name, value, attributes=add_attributes, local=local,
                         global_scope=global_scope, skip_temp_env=skip_temp_env)

    def commit_request_scalar(self, request: DeclarationRequest,
                              assignment: DeclarationAssignment) -> None:
        """Commit one scalar assignment of a :class:`DeclarationRequest`."""
        local, global_scope = request.write_flags(
            bool(self.shell.state.function_stack))
        self.commit_scalar(
            assignment.name, assignment.value, append=assignment.append,
            add_attributes=request.add_attributes, local=local,
            global_scope=global_scope, skip_temp_env=request.skip_temp_env)

    @staticmethod
    def array_conversion_error(existing: Optional["Variable"],
                               requested: ArrayKind) -> Optional[str]:
        """The bash error string for declaring ``requested`` on ``existing``,
        or None when the declaration is allowed.

        bash rejects an incompatible array conversion (indexed<->associative)
        with status 1 and PRESERVES the existing array — this applies even to an
        empty indexed array. Same-kind re-declaration, or a scalar/absent name,
        is allowed. Callers print the returned message and return 1 without
        mutating.
        """
        if existing is None:
            return None
        if requested is ArrayKind.ASSOC and existing.is_indexed_array:
            return "cannot convert indexed to associative array"
        if requested is ArrayKind.INDEXED and existing.is_assoc_array:
            return "cannot convert associative to indexed array"
        return None
