"""One declaration engine behind ``declare``/``export``/``readonly``/``local``.

The builtins appraisal (finding 3 / H5) reproduced defects caused by the
declaration-family builtins each reimplementing shared mechanics instead of
routing through one engine:

1. ``declare -i n=2; export n+=3`` gave 23 — ``export`` concatenated textually
   before applying the integer attribute, ignoring the canonical append.
2. ``a=(x y); declare -A a`` converted (rc=0) instead of failing (rc=1) and
   preserving the indexed array.
3. ``x=G; f(){ local x=L; declare -g x+=A; }`` appended through the local
   shadow (LA) instead of the ``-g`` target's global base (GA).
4. ``declare -pn`` listed every variable instead of only namerefs.

This module centralizes:

- the SCALAR assignment/append commit — the drift locus for defects 1 and 3 —
  onto the authoritative :class:`VariableStore` (which owns the ONE append
  formula, :meth:`VariableStore.compute_append_value`);
- the array-conversion validation (defect 2);
- the flag→:class:`VarAttributes` mapping (:data:`ATTRIBUTE_FLAGS` +
  :func:`attributes_from_options` / :func:`removed_attributes_from_options`,
  including the ``-l``/``-u`` mutual-cancellation rule) shared by ``declare``
  and ``local``;
- the nameref target-SHAPE check (:func:`is_valid_nameref_target`), shared so
  ``local -n`` validates its target like ``declare -n``;
- structured ``name=(...)`` array initialization (:meth:`build_array_init`,
  the single home for the former verbatim ``_build_indexed_array`` /
  ``_build_assoc_array`` twins in ``declare`` and ``local``, including the
  copy-then-build ``+=`` snapshot that leaves a readonly target untouched);
- the ``NAME+=scalar`` seam for an explicit ``-a``/``-A`` on an array base
  (:meth:`scalar_append_into_array`) — it appends onto element 0 through the
  ONE append engine instead of clobbering the array (appraisal H5 carry).

``declare``/``export`` adapt their option parsing into a
:class:`DeclarationRequest` and call the engine; ``readonly`` reuses this via
its delegation to ``declare -r``. ``local``'s FINAL scalar commit deliberately
stays on ``ScopeManager.create_local`` (its local-specific redeclare-merge,
exported-shadow inheritance, and same-scope tombstone semantics are not the
generic store contract) — but it now shares every piece of shared MECHANICS
above with ``declare``, so the two are no longer 150-line twins. Folding
``create_local`` itself into the store is the remaining Phase 4 work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Optional, Union

from ..core import TargetScope, VarAttributes
from ..core.variable_store import VariableStore

if TYPE_CHECKING:
    from ..ast_nodes import ArrayInitialization
    from ..core.variables import AssociativeArray, IndexedArray, Variable
    from ..shell import Shell


# Option-dict KEY → the VarAttributes bit it selects. Both ``declare``
# (function_support.py) and ``local`` (shell_state.py) build their attribute
# set from their boolean options dict through this ONE table (the H5 twin was
# two divergent if-chains, each with its own copy of the -l/-u cancel rule).
ATTRIBUTE_FLAGS: dict[str, VarAttributes] = {
    'readonly': VarAttributes.READONLY,
    'export': VarAttributes.EXPORT,
    'integer': VarAttributes.INTEGER,
    'lowercase': VarAttributes.LOWERCASE,
    'uppercase': VarAttributes.UPPERCASE,
    'array': VarAttributes.ARRAY,
    'assoc_array': VarAttributes.ASSOC_ARRAY,
    'trace': VarAttributes.TRACE,
    'nameref': VarAttributes.NAMEREF,
}


def _case_cancels(options: dict) -> bool:
    """True when BOTH ``-l`` and ``-u`` appear — bash applies NEITHER."""
    return bool(options.get('lowercase')) and bool(options.get('uppercase'))


def attributes_from_options(options: dict) -> VarAttributes:
    """The attributes the ``-flags`` select (shared by declare and local).

    ``-l`` and ``-u`` are mutually exclusive; when BOTH appear in one
    declaration bash applies NEITHER (``declare -ul y; y=HeLLo`` leaves $y
    unfolded and records neither case attribute).
    """
    attributes = VarAttributes.NONE
    for key, attr in ATTRIBUTE_FLAGS.items():
        if options.get(key):
            attributes |= attr
    if _case_cancels(options):
        attributes &= ~(VarAttributes.LOWERCASE | VarAttributes.UPPERCASE)
    return attributes


def removed_attributes_from_options(options: dict) -> VarAttributes:
    """The attributes the ``+flags`` remove (plus the -u/-l mutual cancel).

    Both case flags in one declaration cancel AND clear any pre-existing case
    attribute the name already carried (bash).
    """
    removed = VarAttributes.NONE
    for key, attr in ATTRIBUTE_FLAGS.items():
        if options.get(f'remove_{key}'):
            removed |= attr
    if _case_cancels(options):
        removed |= VarAttributes.LOWERCASE | VarAttributes.UPPERCASE
    return removed


def is_valid_nameref_target(value: str, posix_mode: bool = False) -> bool:
    """Check a nameref target: an identifier, optionally followed by ONE
    balanced ``[subscript]`` spanning to the end of the string.

    Mirrors bash's valid_nameref_value/valid_array_reference (pinned against
    bash 5.2): ``a``, ``a[0]``, ``a[$i]``, ``a[b[c]]`` are valid; ``1``,
    ``a b``, ``a-b``, ``a[``, ``a[]``, ``a[0]x``, ``a[0][1]`` are not. The
    subscript is NOT evaluated here — only its shape is checked. Shared by
    ``declare -n`` and ``local -n`` so the two cannot drift (H5).
    """
    from ..lexer.unicode_support import is_valid_name
    bracket = value.find('[')
    name = value if bracket == -1 else value[:bracket]
    if not is_valid_name(name, posix_mode):
        return False
    if bracket == -1:
        return True
    subscript = value[bracket:]
    if len(subscript) < 3 or not subscript.endswith(']'):
        return False  # needs a non-empty, closed [subscript]
    depth = 0
    for i, ch in enumerate(subscript):
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                # The first [ must close exactly at the end (a[0][1] invalid,
                # a[b[c]] valid).
                return i == len(subscript) - 1
    return False


class ArrayKind(Enum):
    """The array shape a declaration requests (``-a`` vs ``-A``)."""
    INDEXED = auto()
    ASSOC = auto()


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
    layer to the variable's real home (``export``/``cd``).
    """
    target_scope: TargetScope = TargetScope.DEFAULT
    add_attributes: VarAttributes = VarAttributes.NONE
    remove_attributes: VarAttributes = VarAttributes.NONE
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

    # ------------------------------------------------------------------ #
    # Structured ``name=(...)`` array initialization — one home for the
    # verbatim twins that lived in declare (function_support.py) AND local
    # (shell_state.py), including the copy-then-build ``+=`` snapshot.
    # ------------------------------------------------------------------ #

    def build_array_init(self, array_init: "ArrayInitialization", *,
                         assoc: bool, append: bool,
                         existing: Optional["Variable"]
                         ) -> Union["IndexedArray", "AssociativeArray"]:
        """Build an array from a structured ``name=(...)`` initializer.

        Runs the SAME structured element expansion as the bare ``a=(...)`` path
        (``ArrayOperationExecutor.build_indexed_array`` /
        ``build_associative_array``; no shlex reparse) — using the shared
        ``parser/array_flat_text`` argv keys (v0.687 escape fix). For a ``+=``
        (``append``), it merges into a COPY of the same-kind ``existing`` array,
        never the live container: if the target turns out readonly the caller's
        commit is rejected and the live array must stay intact (C2/P1.2 — a
        failed operation does not mutate a readonly value). A mismatched-kind or
        scalar/absent base starts a fresh array (bash builds a new one).
        """
        from ..core.variables import AssociativeArray, IndexedArray
        from ..executor.array import ArrayOperationExecutor
        into: Any = None
        if append and existing is not None:
            want = AssociativeArray if assoc else IndexedArray
            if isinstance(existing.value, want):
                into = existing.value.copy()
        ex = ArrayOperationExecutor(self.shell)
        if assoc:
            return ex.build_associative_array(array_init.words, into=into)
        return ex.build_indexed_array(array_init.words, into=into)

    def scalar_append_into_array(self, name: str, value: str, *, assoc: bool,
                                 add_attributes: VarAttributes,
                                 existing: Optional["Variable"],
                                 local: bool = False,
                                 global_scope: bool = False) -> None:
        """Commit ``NAME+=scalar`` when an explicit ``-a``/``-A`` is present and
        the base is (or converts to) an array — appending onto element 0.

        The H5 carry: the explicit-``-a`` path used to route a scalar ``+=`` into
        the fresh-array-init branch and CLOBBER the array to a one-element scalar
        (``a=(1 2); declare -ai a+=10`` gave ``([0]="10")`` instead of bash's
        ``([0]="11" [1]="2")``). Here the element-0 computation goes through the
        ONE append engine, :meth:`VariableStore.compute_append_value` — integer
        add on ``-i``, concat + effective ``-u``/``-l`` case-fold otherwise —
        with the rest of the array preserved. A scalar base is first converted to
        element 0 (bash: ``a=5; declare -a a+=10`` → ``([0]="510")``); an unset
        base starts empty. The array attribute rides in ``add_attributes`` so the
        commit records ``-a``/``-A``.
        """
        from ..core.variables import (
            AssociativeArray,
            IndexedArray,
            Variable,
        )
        store = self.shell.state.scope_manager.store
        kind_cls = AssociativeArray if assoc else IndexedArray
        key: Union[int, str] = '0' if assoc else 0
        if existing is not None and isinstance(existing.value, kind_cls):
            base_container: Any = existing.value.copy()
        elif existing is not None and not isinstance(
                existing.value, (IndexedArray, AssociativeArray)):
            base_container = kind_cls()
            base_container.set(key, existing.as_string())  # scalar -> element 0
        else:
            base_container = kind_cls()  # unset base: append onto empty
        base_var = Variable(
            name=name, value=base_container,
            attributes=(existing.attributes if existing is not None
                        else VarAttributes.NONE))
        new_container = store.compute_append_value(
            base_var, value, extra_attrs=add_attributes)
        store.assign(name, new_container, attributes=add_attributes,
                     local=local, global_scope=global_scope)
