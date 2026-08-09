"""The ``ExpansionHost`` family is mypy-LOAD-BEARING (remediation 5C.1).

5B.2 lesson 2: *typing changes verify only with a consumer in the checked set —
"mypy-clean" on a zero-consumer surface means UNOBSERVED.* A protocol nobody
type-checks against is a comment with syntax highlighting.

These cells run a REAL mypy over a fixture module and assert two things:

* the design type-checks — ``ExpansionManager`` satisfies the composed
  ``ExpansionSurface``, ``Shell`` satisfies ``ExpansionHost``, and every
  measured usage of the three consumers resolves through it;
* it can FAIL — each mutation arm re-widens or mistypes one thing and must
  produce mypy's own error for that specific fault, not merely some error
  (5B.1 lesson 2: a RED arm satisfied by any failure is satisfied by the wrong
  one).

The mutation arms are what make ``ExpansionSubExpanders`` and
``ExpansionSurface`` OBSERVED even though they are not exported: M1 and M3 bite
THROUGH them (integrator ruling R4). Without these, the unexported pieces would
be exactly the unobserved surface the lesson warns about.
"""

import pathlib
import subprocess
import sys
import textwrap

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]

#: The design under test, as a module mypy can check. Mirrors the real
#: consumers' MEASURED usage (ledger §A7): evaluate_arithmetic reaches
#: .state{get_variable,set_variable,scope_manager,error_location_prefix} and
#: .expansion_manager{expand_string_variables,subscript}; PromptExpander reaches
#: .state{command_number,history} and .expansion_manager.expand_string_variables;
#: the nine-hop family reaches the four sub-expander members.
FIXTURE = '''
from psh.expansion.manager import ExpansionManager
from psh.protocols import ExpansionHost
from psh.protocols import ExpansionSubExpanders, ExpansionSurface
from psh.shell import Shell


def c1_producer_satisfies_subexpanders(m: ExpansionManager) -> ExpansionSubExpanders:
    return m


def c2_producer_satisfies_the_composition(m: ExpansionManager) -> ExpansionSurface:
    return m


def c3_shell_satisfies_the_host(s: Shell) -> ExpansionHost:
    return s


def c4_the_nine_hop_family(host: ExpansionHost, expr: str) -> None:
    _ = host.expansion_manager.subscript
    _ = host.expansion_manager.command_sub
    _ = host.expansion_manager.execute_arithmetic_expansion(expr)
    _ = host.expansion_manager.tilde_expander


def c5_evaluate_arithmetic_usage(host: ExpansionHost, text: str) -> None:
    _ = host.expansion_manager.expand_string_variables(text)
    _ = host.expansion_manager.subscript
    _ = host.state.get_variable("x")
    host.state.set_variable("x", "1")
    _ = host.state.scope_manager
    _ = host.state.error_location_prefix


def c6_prompt_expander_usage(host: ExpansionHost, text: str) -> None:
    _ = host.expansion_manager.expand_string_variables(text)
    _ = host.state.command_number
    _ = host.state.history
'''

#: (label, anchored old text, replacement, regex the error MUST match).
#: Every replacement is anchored and applied exactly once (5B.2 lesson 6).
MUTATIONS = [
    ("M1 unknown member on the manager surface",
     "    _ = host.expansion_manager.subscript\n    _ = host.expansion_manager.command_sub",
     "    _ = host.expansion_manager.no_such_member\n    _ = host.expansion_manager.command_sub",
     r'"ExpansionSurface" has no attribute "no_such_member"'),
    ("M2 member absent from the host",
     "    _ = host.state.command_number",
     "    _ = host.job_manager",
     r'"ExpansionHost" has no attribute "job_manager"'),
    ("M3 producer no longer satisfies the sub-expander set",
     "def c1_producer_satisfies_subexpanders(m: ExpansionManager) -> ExpansionSubExpanders:\n    return m",
     "class _Impostor:\n    pass\n\n\n"
     "def c1_producer_satisfies_subexpanders(m: _Impostor) -> ExpansionSubExpanders:\n    return m",
     r'expected "ExpansionSubExpanders"'),
    ("M4 host member mistyped at the use site",
     "    _ = host.state.get_variable(\"x\")",
     "    _ = host.state.get_variable(1, 2, 3)",
     r'get_variable'),
]


def _run_mypy(tmp_path, source):
    src = tmp_path / "witness_fixture.py"
    src.write_text(textwrap.dedent(source))
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--follow-imports=silent",
         "--no-error-summary", "--cache-dir", str(tmp_path / ".mypy_cache"),
         str(src)],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT),
             "PYTHONDONTWRITEBYTECODE": "1"})


@pytest.mark.slow
def test_the_design_type_checks(tmp_path):
    """C1-C6: producer conformance, host conformance, and all three consumers'
    measured usage."""
    pytest.importorskip("mypy")
    r = _run_mypy(tmp_path, FIXTURE)
    assert r.returncode == 0, (
        "the ExpansionHost design no longer type-checks:\n"
        + r.stdout + r.stderr)


@pytest.mark.slow
@pytest.mark.parametrize("label,old,new,pattern", MUTATIONS,
                         ids=[m[0].split()[0] for m in MUTATIONS])
def test_mutation_bites_for_its_own_reason(tmp_path, label, old, new, pattern):
    """Each arm must fail, AND fail with mypy's error for THAT fault.

    A protocol nobody can violate is a protocol nobody is checked against.
    """
    pytest.importorskip("mypy")
    assert FIXTURE.count(old) == 1, f"{label}: anchor is not unique"
    mutant = FIXTURE.replace(old, new, 1)
    r = _run_mypy(tmp_path, mutant)
    out = r.stdout + r.stderr
    assert r.returncode != 0, (
        f"{label}: mypy accepted the mutation — the protocol is not "
        f"load-bearing here:\n{out}")
    import re
    assert re.search(pattern, out), (
        f"{label}: mypy failed, but not for its own reason "
        f"(expected /{pattern}/):\n{out}")


def test_the_unexported_pieces_are_reachable_for_the_arms():
    """``ExpansionSubExpanders``/``ExpansionSurface`` are deliberately absent
    from ``__all__`` (they have no production consumer of their own and would
    fail the adoption census), but they must still be importable — the M1/M3
    arms are what make them OBSERVED rather than decorative."""
    import psh.protocols as P
    assert hasattr(P, "ExpansionSubExpanders")
    assert hasattr(P, "ExpansionSurface")
    assert "ExpansionSubExpanders" not in P.__all__
    assert "ExpansionSurface" not in P.__all__
    assert "ExpansionHost" in P.__all__


def test_expansion_surface_declares_nothing_of_its_own():
    """The composition claim, asserted rather than described: every member of
    ``ExpansionSurface`` comes from one of its two measured bases, so composing
    them widened neither."""
    import typing

    import psh.protocols as P

    def members(proto):
        getter = getattr(typing, "get_protocol_members", None)
        return set(getter(proto)) if getter else set(
            typing._get_protocol_attrs(proto))       # noqa: SLF001 - 3.12

    surface = members(P.ExpansionSurface)
    runtime = members(P.ExpansionRuntime)
    subexp = members(P.ExpansionSubExpanders)
    assert surface == runtime | subexp, (
        f"ExpansionSurface has members of its own: {surface - runtime - subexp}")
    assert not (runtime & subexp), (
        f"the two bases overlap ({runtime & subexp}) — they were measured as "
        "disjoint member sets, so composing them should add nothing")
