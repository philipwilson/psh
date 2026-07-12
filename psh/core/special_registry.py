"""Declarative registry + typed state for computed special parameters.

Bash exposes a handful of *dynamically computed* variables whose value is
produced on each read instead of being stored (``RANDOM``, ``SECONDS``,
``LINENO``, ...). This module is the single place that declares each one's
behaviour, replacing the scattered frozensets and the big ``if``-chain the
core-state appraisal (finding H1) flagged as "no coherent state machine".

Two categories are declared in ``SPECIAL_REGISTRY``:

- **Dynamic specials** (``lifecycle=True``): ``RANDOM``, ``SECONDS``,
  ``BASHPID``, ``SRANDOM``, ``EPOCHSECONDS``, ``EPOCHREALTIME``, ``LINENO``.
  Their value is computed on read, but they otherwise behave like real
  variables: an attribute added to one PERSISTS (``readonly RANDOM`` really is
  readonly; a later assignment fails), ``export`` materialises a SNAPSHOT of the
  current value into the environment, and ``unset`` DEACTIVATES the name so it
  reverts to an ordinary variable (bash). ``SpecialParameterState`` owns their
  bookkeeping: the ``SECONDS`` baseline on a MONOTONIC clock (so a wall-clock
  step never makes elapsed time jump or run backwards), the ``RANDOM`` seed, the
  ``LINENO`` line counter, the deactivated set, and the persistent-attribute
  overlay.

- **Shell-view specials** (``lifecycle=False``): ``PIPESTATUS``,
  ``BASH_COMMAND``, ``FUNCNAME``. Read-only projections of live execution state.
  Their value is computed (and SHADOWS any same-named stored variable on read),
  but assignment / readonly / unset all use the ORDINARY variable path — which
  already matches bash, so they carry no special lifecycle. They live in the
  table only so the declaration of every computed name is in one place.

``UID``/``EUID``/``PPID`` are deliberately NOT here: they are seeded as real
readonly-integer variables at shell startup, which is what makes them
assignment-proof and lists them in ``declare -p``.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional, Set

from .option_registry import SET_O_OPTION_NAMES, SHOPT_OPTION_NAMES
from .variables import IndexedArray, VarAttributes


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


def coerce_special_int(value: object) -> int:
    """Parse an assignment to a SEED special (SECONDS/RANDOM) as a plain int.

    bash parses these as a simple signed decimal integer, NOT a full
    arithmetic expression: ``SECONDS=0x10`` and ``RANDOM=x`` both yield 0,
    while ``SECONDS=-5`` is accepted. (``SECONDS=$((2+3))`` works because the
    arithmetic is expanded to ``5`` before assignment.)
    """
    try:
        return int(str(value).strip())
    except (ValueError, AttributeError):
        return 0


class AssignPolicy(Enum):
    """How a whole-variable assignment to an ACTIVE dynamic special behaves.

    - ``SEED``: honoured — ``SECONDS=N`` resets the elapsed baseline, ``RANDOM=N``
      seeds the reproducible generator. No stored variable is created.
    - ``IGNORE``: silently dropped (bash: assigning ``BASHPID``/``SRANDOM``/
      ``LINENO``/the EPOCH clocks has no effect while the name is special).
    - ``NONE``: shell-view specials — assignment is not intercepted at all and
      takes the ordinary variable path.
    """
    SEED = auto()
    IGNORE = auto()
    NONE = auto()


@dataclass
class SpecialContext:
    """Everything a special's ``compute`` callable may need.

    ``state`` carries the dynamic-special bookkeeping; ``shell`` is the owning
    Shell (or ``None`` before it is wired) for the shell-view projections.
    """
    state: "SpecialParameterState"
    shell: Any = None


@dataclass(frozen=True)
class SpecialVarSpec:
    """One row of the special-parameter registry."""
    name: str
    compute: Callable[[SpecialContext], Optional[object]]
    assign: AssignPolicy = AssignPolicy.NONE
    read_has_side_effects: bool = False
    default_attributes: VarAttributes = VarAttributes.NONE
    lifecycle: bool = False


# --------------------------------------------------------------------------- #
# Compute callables. Each returns the current VALUE (str, IndexedArray, or None
# to fall through to the ordinary variable lookup); the caller wraps it in a
# Variable and applies the declared/overlaid attributes.
# --------------------------------------------------------------------------- #

def _compute_seconds(ctx: SpecialContext) -> str:
    st = ctx.state
    if st.seconds_base is not None:
        # SECONDS=N reset the baseline: read as N + elapsed-since-assignment.
        return str(st.seconds_base + int(time.monotonic() - st.seconds_assigned_at))
    return str(int(time.monotonic() - st.shell_start_time))


def _compute_random(ctx: SpecialContext) -> str:
    st = ctx.state
    if st.random_seed is not None:
        # Seeded: reproducible, matches bash 5.x value-for-value.
        st.random_seed = _intrand32(st.random_seed)
        value = ((st.random_seed >> 16) ^ (st.random_seed & 0xFFFF)) & 0x7FFF
    else:
        value = random.randint(0, 32767)
    return str(value)


def _compute_bashpid(ctx: SpecialContext) -> str:
    # The CURRENT process pid — differs from $$ inside a forked child; read live.
    return str(os.getpid())


def _compute_srandom(ctx: SpecialContext) -> str:
    # bash 5.1+: a fresh 32-bit value from a good entropy source on each read,
    # UNRELATED to RANDOM's seed. os.urandom is unbuffered and independent of
    # Python's (seedable) random module.
    return str(int.from_bytes(os.urandom(4), "big"))


def _compute_epochseconds(ctx: SpecialContext) -> str:
    return str(int(time.time()))


def _compute_epochrealtime(ctx: SpecialContext) -> str:
    return f"{time.time():.6f}"


def _compute_lineno(ctx: SpecialContext) -> str:
    return str(ctx.state.current_line_number)


def _enabled_option_names(ctx: SpecialContext, names) -> Optional[str]:
    """Colon-joined sorted list of the ENABLED options among *names* (bash's
    SHELLOPTS/BASHOPTS value shape). None before the shell is wired, so the
    ordinary variable lookup takes over (like the shell-view specials)."""
    shell = ctx.shell
    if shell is None or not hasattr(shell, "state"):
        return None
    options = shell.state.options
    return ":".join(sorted(n for n in names if options.get(n)))


def _compute_shellopts(ctx: SpecialContext) -> Optional[str]:
    # The set -o option table (bash: SHELLOPTS reflects set -o, not shopt).
    return _enabled_option_names(ctx, SET_O_OPTION_NAMES)


def _compute_bashopts(ctx: SpecialContext) -> Optional[str]:
    # The shopt option table (bash: BASHOPTS is SHELLOPTS' shopt twin).
    return _enabled_option_names(ctx, SHOPT_OPTION_NAMES)


def _compute_pipestatus(ctx: SpecialContext) -> Optional[IndexedArray]:
    shell = ctx.shell
    if shell is None:
        return None
    arr = IndexedArray()
    for i, st in enumerate(shell.state.pipestatus):
        arr.set(i, str(st))
    return arr


def _compute_bash_command(ctx: SpecialContext) -> Optional[str]:
    shell = ctx.shell
    if shell is None:
        return None
    return shell.state.bash_command


def _compute_funcname(ctx: SpecialContext) -> Optional[IndexedArray]:
    shell = ctx.shell
    if shell is None or not hasattr(shell, "state"):
        return None
    # FUNCNAME is an ARRAY: [0] current function, [1] caller, ... —
    # function_stack is pushed on entry (last = current), so reverse it.
    # Outside a function it is an EMPTY array (so $FUNCNAME reads empty and
    # the ARRAY attribute stays consistent with the value type).
    arr = IndexedArray()
    for i, fname in enumerate(reversed(shell.state.function_stack)):
        arr.set(i, fname)
    return arr


_SPECS = (
    SpecialVarSpec("SECONDS", _compute_seconds, AssignPolicy.SEED,
                   default_attributes=VarAttributes.INTEGER, lifecycle=True),
    SpecialVarSpec("RANDOM", _compute_random, AssignPolicy.SEED,
                   read_has_side_effects=True,
                   default_attributes=VarAttributes.INTEGER, lifecycle=True),
    SpecialVarSpec("BASHPID", _compute_bashpid, AssignPolicy.IGNORE,
                   default_attributes=VarAttributes.INTEGER, lifecycle=True),
    SpecialVarSpec("SRANDOM", _compute_srandom, AssignPolicy.IGNORE,
                   read_has_side_effects=True,
                   default_attributes=VarAttributes.INTEGER, lifecycle=True),
    SpecialVarSpec("EPOCHSECONDS", _compute_epochseconds, AssignPolicy.IGNORE,
                   lifecycle=True),
    SpecialVarSpec("EPOCHREALTIME", _compute_epochrealtime, AssignPolicy.IGNORE,
                   lifecycle=True),
    SpecialVarSpec("LINENO", _compute_lineno, AssignPolicy.IGNORE,
                   lifecycle=True),
    # Option-reflection variables: computed live from the option tables and
    # READONLY BY DEFAULT (bash: `SHELLOPTS=x` → "readonly variable"; `unset
    # SHELLOPTS` refused). The READONLY default attribute makes the lifecycle
    # interceptions in ScopeManager raise before the assign policy is ever
    # consulted, so IGNORE here is a formality. Not exported unless the name
    # arrived via the environment (ShellState import) or an explicit `export`.
    SpecialVarSpec("SHELLOPTS", _compute_shellopts, AssignPolicy.IGNORE,
                   default_attributes=VarAttributes.READONLY, lifecycle=True),
    SpecialVarSpec("BASHOPTS", _compute_bashopts, AssignPolicy.IGNORE,
                   default_attributes=VarAttributes.READONLY, lifecycle=True),
    # Shell-view projections — computed read only; ordinary path for everything
    # else (already bash-correct, so no lifecycle).
    SpecialVarSpec("PIPESTATUS", _compute_pipestatus,
                   default_attributes=VarAttributes.ARRAY),
    SpecialVarSpec("BASH_COMMAND", _compute_bash_command),
    SpecialVarSpec("FUNCNAME", _compute_funcname,
                   default_attributes=VarAttributes.ARRAY),
)

SPECIAL_REGISTRY: Dict[str, SpecialVarSpec] = {spec.name: spec for spec in _SPECS}

# The computed specials that no-arg ``set`` and ``declare -p`` ENUMERATE (bash
# lists SHELLOPTS/BASHOPTS in both, with their values). They have no stored
# variable cell, so ``ScopeManager.all_variables_with_attributes`` injects them
# (and, when exported, ``all_exported_variables`` injects them for ``export -p`` — r19-P8).
#
# Every OTHER computed special is a DELIBERATE, DOCUMENTED DIVERGENCE from bash's
# no-arg enumeration — psh lists them only by explicit name (``declare -p RANDOM``
# / ``declare -p FUNCNAME`` work and match bash). Two reasons:
#   * The dynamic clock/counter specials (RANDOM, SECONDS, LINENO, BASHPID,
#     SRANDOM, the EPOCH clocks): bash's ``declare -p`` rendering of them is
#     reference-state-dependent (an unreferenced ``SECONDS`` prints
#     ``declare -- SECONDS`` with NO value, but after one read
#     ``declare -i SECONDS="0"``) and internally inconsistent — a fragile artifact
#     not worth reproducing.
#   * The shell-view specials (FUNCNAME, PIPESTATUS, BASH_COMMAND): bash shows
#     FUNCNAME/BASH_COMMAND in ``set``/``declare -p`` (FUNCNAME only while inside
#     a function); psh has never enumerated them and this stays out of the #34
#     scope (SHELLOPTS/BASHOPTS only).
# See the core-state-polish ledger for the probe evidence behind this boundary.
OPTION_REFLECTION_SPECIALS = ("SHELLOPTS", "BASHOPTS")


class SpecialParameterState:
    """Typed lifecycle state for the dynamically computed special parameters.

    Owns everything the dynamic specials need across a shell's life:

    - ``shell_start_time`` / ``seconds_base`` / ``seconds_assigned_at``: the
      MONOTONIC ``SECONDS`` baseline (``SECONDS=N`` records ``base=N`` at the
      current monotonic instant; reads add the monotonic delta).
    - ``random_seed``: the reproducible ``RANDOM`` generator seed, or ``None``
      for the unseeded (entropy-backed) path.
    - ``current_line_number``: backs ``$LINENO``.
    - ``deactivated``: names that have been ``unset`` and so lost their special
      behaviour, becoming ordinary variables (bash).
    - ``_attributes``: the persistent-attribute overlay. ``readonly RANDOM`` /
      ``export SECONDS`` record the attribute HERE (a dynamic special has no
      stored ``Variable``), so it is enforced on assignment/unset, materialised
      into the environment, and shown by ``declare -p NAME``.
    """

    def __init__(self) -> None:
        self.shell_start_time: float = time.monotonic()
        self.seconds_base: Optional[int] = None
        self.seconds_assigned_at: float = 0.0
        self.random_seed: Optional[int] = None
        self.current_line_number: int = 1
        self.deactivated: Set[str] = set()
        self._attributes: Dict[str, VarAttributes] = {}

    # -- classification ---------------------------------------------------- #

    def is_computed(self, name: str) -> bool:
        """True if *name* currently reads as a computed special (any category).

        A deactivated dynamic special (``unset``) is no longer computed.
        """
        return name in SPECIAL_REGISTRY and name not in self.deactivated

    def has_lifecycle(self, name: str) -> bool:
        """True if *name* is an ACTIVE dynamic special (readonly/export/unset
        are intercepted for it)."""
        spec = SPECIAL_REGISTRY.get(name)
        return (spec is not None and spec.lifecycle
                and name not in self.deactivated)

    def read_has_side_effects(self, name: str) -> bool:
        spec = SPECIAL_REGISTRY.get(name)
        return bool(spec and spec.read_has_side_effects)

    # -- read -------------------------------------------------------------- #

    def compute_value(self, name: str, ctx: SpecialContext) -> Optional[object]:
        return SPECIAL_REGISTRY[name].compute(ctx)

    def attributes_for(self, name: str) -> VarAttributes:
        """Effective attributes of an active special: declared defaults (e.g.
        ``INTEGER`` for RANDOM) OR-ed with any persistent overlay."""
        base = SPECIAL_REGISTRY[name].default_attributes
        return base | self._attributes.get(name, VarAttributes.NONE)

    # -- write ------------------------------------------------------------- #

    def assign(self, name: str, value: object) -> None:
        """Apply a whole-variable assignment to an active dynamic special."""
        policy = SPECIAL_REGISTRY[name].assign
        if policy is AssignPolicy.SEED:
            n = coerce_special_int(value)
            if name == "SECONDS":
                self.seconds_base = n
                self.seconds_assigned_at = time.monotonic()
            elif name == "RANDOM":
                self.random_seed = n & 0xFFFFFFFF
        # IGNORE: assignment silently dropped (still computed on read).

    def add_attributes(self, name: str, attributes: VarAttributes) -> None:
        if attributes:
            self._attributes[name] = self._attributes.get(
                name, VarAttributes.NONE) | attributes

    def remove_attributes(self, name: str, attributes: VarAttributes) -> None:
        current = self._attributes.get(name, VarAttributes.NONE) & ~attributes
        if current:
            self._attributes[name] = current
        else:
            self._attributes.pop(name, None)

    def deactivate(self, name: str) -> None:
        """``unset`` of a dynamic special: it becomes an ordinary variable.

        Drops the recorded baseline/seed and any persistent attributes and
        records the deactivation so reads no longer compute the special value.
        """
        self.deactivated.add(name)
        if name == "SECONDS":
            self.seconds_base = None
        elif name == "RANDOM":
            self.random_seed = None
        self._attributes.pop(name, None)

    # -- child inheritance ------------------------------------------------- #

    def clone(self) -> "SpecialParameterState":
        """Independent copy for a subshell-style child (clone_for_child).

        Inherits the shell start time, the SECONDS baseline (bash:
        ``SECONDS=500; (echo $SECONDS)`` prints 500), the deactivated set (after
        ``unset SECONDS`` it stays plain in children too), the current line
        number, and the persistent-attribute overlay. RANDOM's generator seed is
        deliberately NOT inherited: bash reseeds the generator in subshell
        children (the child's sequence is unrelated to the parent's), which a
        fresh unseeded state reproduces; seeding inside the child
        (``(RANDOM=42; echo $RANDOM)``) is still deterministic.
        """
        new = SpecialParameterState()
        new.shell_start_time = self.shell_start_time
        new.seconds_base = self.seconds_base
        new.seconds_assigned_at = self.seconds_assigned_at
        new.current_line_number = self.current_line_number
        new.deactivated = set(self.deactivated)
        new._attributes = dict(self._attributes)
        return new
