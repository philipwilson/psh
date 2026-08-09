"""A6 — FEASIBILITY probe for the ruling-(e) protocol design.

5B.2 lesson 4 binds: *verify the edit you will make, not a weaker proxy.* So
this is not an argument that the design "should" type-check — it is the actual
protocol declarations, checked by a real mypy run against the real ``Shell``
and ``ExpansionManager``, with the assignments that Phase B would make.

The design under test (composition, NOT widening — see D2):

  ExpansionSubExpanders : the FOUR measured nine-hop members, read-only props
  ExpansionSurface      : ExpansionRuntime + ExpansionSubExpanders, 0 new members
  ExpansionHost         : {state: ShellState, expansion_manager: ExpansionSurface}

Claims each cell tests:
  C1  ExpansionManager structurally satisfies ExpansionSubExpanders
  C2  ExpansionManager structurally satisfies the composed ExpansionSurface
  C3  Shell structurally satisfies ExpansionHost
  C4  the eight nine-hop reaches type-check through ExpansionHost
  C5  evaluate_arithmetic's measured usage type-checks through ExpansionHost
  C6  PromptExpander's measured usage type-checks through ExpansionHost

This file lives in tmp/ and is NEVER imported by the tree. It is checked with
an explicit mypy invocation (see the runner comment at the bottom).
"""
from typing import Optional, Protocol

from psh.core.state import ShellState
from psh.expansion.manager import ExpansionManager
from psh.protocols import ExpansionRuntime
from psh.shell import Shell


class ExpansionSubExpanders(Protocol):
    """The FOUR sub-expander members the nine-hop family actually reaches.

    Read-only properties, per the 5B.2 invariance lesson: a mutable protocol
    attribute is INVARIANT, so a plain `x: SubscriptEvaluator` would demand the
    producer's attribute be exactly that type. Nothing assigns through these.
    """

    @property
    def subscript(self) -> object: ...

    @property
    def command_sub(self) -> object: ...

    @property
    def tilde_expander(self) -> object: ...

    def execute_arithmetic_expansion(self, expr: str) -> int: ...


class ExpansionSurface(ExpansionRuntime, ExpansionSubExpanders, Protocol):
    """Composition of two MEASURED member sets. Declares nothing of its own —
    this is why the design is not a widening of ExpansionRuntime."""


class ExpansionHost(Protocol):
    """What `evaluate_arithmetic` / `PromptExpander` / the nine hops actually
    need from the object they are handed."""

    @property
    def state(self) -> ShellState: ...

    @property
    def expansion_manager(self) -> ExpansionSurface: ...


# --- C1/C2: the producer satisfies the manager protocols --------------------
def c1(m: ExpansionManager) -> ExpansionSubExpanders:
    return m


def c2(m: ExpansionManager) -> ExpansionSurface:
    return m


# --- C3: Shell satisfies the host protocol ----------------------------------
def c3(s: Shell) -> ExpansionHost:
    return s


# --- C4: the eight nine-hop reaches, through the host -----------------------
def c4(host: ExpansionHost, expr: str) -> None:
    _ = host.expansion_manager.subscript                  # arrays x3, operators x1, variable.py x1
    _ = host.expansion_manager.command_sub                # operands x2
    _ = host.expansion_manager.execute_arithmetic_expansion(expr)   # operands x1
    _ = host.expansion_manager.tilde_expander             # operands x1


# --- C5: evaluate_arithmetic's MEASURED usage, through the host -------------
def c5(host: ExpansionHost, text: str) -> None:
    _ = host.expansion_manager.expand_string_variables(text)
    _ = host.expansion_manager.subscript
    _ = host.state.get_variable("x")
    host.state.set_variable("x", "1")
    _ = host.state.scope_manager
    _ = host.state.error_location_prefix


# --- C6: PromptExpander's MEASURED usage, through the host ------------------
def c6(host: ExpansionHost, text: str) -> None:
    _ = host.expansion_manager.expand_string_variables(text)
    _ = host.state.command_number
    _ = host.state.history


# --- MUTATION WITNESS: each cell must be able to FAIL ------------------------
# Uncommenting either line below must produce a mypy error. A design that
# type-checks because nothing is actually checked is unobserved (5B.2 l.2).
def mutation_witness(host: ExpansionHost) -> None:
    # _ = host.expansion_manager.no_such_member       # MUST error
    # _ = host.job_manager                            # MUST error (not on host)
    pass


def _unused(x: Optional[int] = None) -> None:
    return None

# Runner:
#   PYTHONPATH=<ROOT> python -m mypy --follow-imports=silent \
#       --no-error-summary tmp/w5c1-instruments/A6_protocol_feasibility.py
