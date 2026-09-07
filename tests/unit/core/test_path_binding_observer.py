"""The PATH observer counter: one call per effective rebinding, zero otherwise.

``ScopeManager._effective_binding_changed`` is the ONE authority on when a
remembered command location is stale, and ``CommandHashTable`` is its only
subscriber.  This module is the guard on both halves.

The **counter** below runs every path that can bind, rebind or unbind PATH and
asserts the exact number of observer calls.  A shell that fires too FEW runs
the wrong executable (C044: after a function holding a ``local PATH`` returns,
the pop wrote no name, so a name-keyed observer never fired and the next
dispatch kept the discarded scope's binary).  A shell that fires too MANY
throws the table away on every ordinary function return, which bash does not
do -- so both directions are pinned.

The **static guard** asserts no write path reaches the subscriber behind the
owner's back, and ``test_synthetic_bypass_is_rejected`` is its offender.

Expected counts are what bash 5.3.15 flushes, probed before being written down
(``hash -t probe`` fails exactly when the table was emptied)::

    cd "$(mktemp -d)"; mkdir a; printf '#!/bin/sh\necho A\n' > a/probe
    chmod +x a/probe
    env -u PWD -u OLDPWD /opt/homebrew/bin/bash -c \
      'PATH=$PWD/a; probe; f(){ local PATH=$PWD/a; }; f; hash -t probe'

Two named mutations must turn this module red, and are the checks the slot
records:

``M1 drop-pop-notify``
    Delete the ``_effective_binding_changed('PATH', before)`` call at the end
    of ``ScopeManager.pop_scope`` -- the C044 defect itself.  Every
    ``...-then-pop`` row loses a call and the hash-table row goes red.

``M2 fire-on-every-pop``
    Delete the gate instead, so ``pop_scope`` reports a rebinding whether or
    not the scope bound PATH.  Seven rows go red: ``plain-return-no-PATH``,
    ``nested-plain-returns`` and ``temp-env-prefix-other-name`` rise from 0,
    ``write-through-nameref-to-PATH``, ``temp-env-prefix-over-function`` and
    ``command-temp-env-shadows-a-local`` overcount, and
    ``test_an_ordinary_return_keeps_the_table`` loses its entry.  Over-firing
    is a real defect, not a safe default: bash keeps the table across a return
    that bound no PATH, and throwing it away re-walks PATH for every command
    after every function call.

Improvement Program 2026-09 slot 1.5 (finding C044).
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import List, Tuple

import pytest

#: The one method allowed to call the observer, and the file it lives in.
OWNER_FILE = "psh/core/scope.py"
OWNER_METHOD = "_effective_binding_changed"

#: Files allowed to empty the command hash table directly: ``ShellState``
#: installs the subscription (twice -- once per constructor), and the ``hash``
#: builtin's explicit ``hash -r`` is a user request, not a staleness decision.
HASH_CLEAR_ALLOWED = {"psh/core/state.py", "psh/builtins/hash_builtin.py"}

#: ``(id, script, expected observer calls)``.  A row with 0 is a NON-change:
#: bash keeps the hashed entry across it.
COUNTER_ROWS: Tuple[Tuple[str, str, int], ...] = (
    # --- writes: each one rebinds PATH, bash empties the table for each -----
    ("global-assignment", 'PATH=/x', 1),
    # bash empties even when the value is unchanged, so two writes = two calls.
    ("assignment-twice-same-value", 'PATH=/a; PATH=/a', 2),
    ("export-with-value", 'export PATH=/x', 1),
    ("declare-g-at-global", 'declare -g PATH=/x', 1),
    ("assign-then-unset", 'PATH=/a; unset PATH', 2),
    ("write-through-nameref-to-PATH", 'f(){ local -n r=PATH; r=/b; }; f', 1),
    # --- non-changes: nothing that binds PATH happened ----------------------
    # The single call in these two is the seeding assignment; adding an
    # attribute to an existing PATH binds nothing, and bash keeps the entry.
    ("export-attribute-only", 'PATH=/a; export PATH', 1),
    ("readonly-attribute-only", 'PATH=/a; readonly PATH', 1),
    ("another-name-entirely", 'OTHER=1; export OTHER=2; unset OTHER', 0),
    ("plain-return-no-PATH", 'f(){ local X=1; }; f', 0),
    ("nested-plain-returns", 'f(){ :; }; g(){ f; f; }; g', 0),
    ("temp-env-prefix-other-name", 'g(){ :; }; OTHER=1 g', 0),
    # --- scope pops: the write nobody makes (C044) --------------------------
    ("local-PATH-then-pop", 'f(){ local PATH=/b; }; f', 2),
    ("local-PATH-declaration-only-then-pop", 'f(){ local PATH; }; f', 2),
    ("local-declared-then-assigned-then-pop", 'f(){ local PATH; PATH=/b; }; f', 3),
    ("early-return", 'f(){ local PATH=/b; return 0; }; f', 2),
    ("failing-body", 'f(){ local PATH=/b; false; }; f', 2),
    ("set-e-failing-body", 'set -e; f(){ local PATH=/b; false; }; f || true', 2),
    ("nested-locals", 'g(){ local PATH=/c; }; f(){ local PATH=/b; g; }; f', 4),
    # The pop reveals a DIFFERENT cell holding the SAME string; bash empties
    # the table here too, so the comparison is on the binding, not the value.
    ("local-PATH-equal-to-outer-then-pop", 'PATH=/a; f(){ local PATH=/a; }; f', 3),
    ("unset-of-local-then-pop", 'PATH=/a; f(){ local PATH=/b; unset PATH; }; f', 4),
    # `declare -g` writes the shadowed global: a rebinding of the name PATH,
    # which bash flushes for (probe: `hash -t probe` fails right after it),
    # even though the local still shadows it and the effective VALUE is
    # unchanged until the pop.  See the slot 1.5 handoff, deviation D-1.
    ("declare-g-under-local", 'f(){ local PATH=/b; declare -g PATH=/c; }; f', 3),
    # --- temporary environments --------------------------------------------
    # A prefix over a FUNCTION is one temp-env scope: bound on push, discarded
    # on pop.
    ("temp-env-prefix-over-function", 'g(){ :; }; PATH=/b g', 2),
    # A prefix over a BUILTIN binds twice -- once in the staging scope the
    # prefix is expanded into (visible to name lookup), once in the command
    # temp-env layer -- and each binding is discarded again, so four
    # rebindings, four calls.
    ("temp-env-prefix-over-builtin", 'PATH=/b :', 4),
    # --- a child shell's writes never reach the parent's table --------------
    ("subshell-assignment", 'PATH=/a; ( PATH=/b )', 1),
    # A command temp-env layer SHADOWS a function's own local, so popping the
    # function scope reveals the binding it never hid: that pop is NOT a
    # change, and the count stays at five (staging bind and unbind, the
    # command layer's bind, the `local` declaration, the layer's unbind)
    # instead of six.  This row is where the owner's before/after comparison
    # earns its keep.
    ("command-temp-env-shadows-a-local",
     "PATH=/b eval 'f(){ local PATH; }; f'", 5),
)


def _count(shell, script: str) -> int:
    """Observer calls made while *script* runs, with the real subscriber intact."""
    manager = shell.state.scope_manager
    subscriber = manager.path_changed
    assert subscriber is not None, "ShellState must install the hash-table subscriber"
    calls = 0

    def counting() -> None:
        nonlocal calls
        calls += 1
        subscriber()

    manager.path_changed = counting
    try:
        shell.run_command(script)
    finally:
        manager.path_changed = subscriber
    return calls


@pytest.mark.parametrize(
    "script,expected", [pytest.param(s, n, id=i) for i, s, n in COUNTER_ROWS])
def test_observer_call_count(captured_shell, script: str, expected: int) -> None:
    """Exactly one observer call per effective rebinding of PATH, zero otherwise.

    Closes C044: the pop rows were all one call short before the owner existed.
    """
    assert _count(captured_shell, script) == expected


def _two_probes(root: str) -> str:
    """Create ``a/probe`` and ``b/probe`` under *root*, echoing A and B."""
    for tag in ("a", "b"):
        directory = os.path.join(root, tag)
        os.makedirs(directory, exist_ok=True)
        script = os.path.join(directory, "probe")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(f"#!/bin/sh\necho {tag.upper()}\n")
        os.chmod(script, 0o755)


def test_the_table_is_actually_emptied_by_a_pop(
        isolated_shell_with_temp_dir) -> None:
    """The subscriber is reached, not just the observer (D3: the real target).

    The counter alone would pass with the subscription unwired, so this reads
    the hash table itself -- and it has to be a REAL dispatch that fills it,
    inside the function, after the ``local PATH`` write already emptied it.
    That is the C044 shape exactly: the entry the discarded scope remembered
    must not survive its pop.
    """
    shell = isolated_shell_with_temp_dir
    root = os.getcwd()
    _two_probes(root)
    table = shell.state.command_hash
    shell.run_command(f'PATH={root}/a')
    shell.run_command(f'f(){{ local PATH={root}/b; probe >/dev/null; }}')

    shell.run_command('f')
    assert table.lookup('probe') is None, (
        "the popped scope's remembered location survived the pop: the next "
        "dispatch would run it through the restored PATH")


def test_an_ordinary_return_keeps_the_table(
        isolated_shell_with_temp_dir) -> None:
    """A function that never bound PATH does not cost the table (bash keeps it)."""
    shell = isolated_shell_with_temp_dir
    root = os.getcwd()
    _two_probes(root)
    table = shell.state.command_hash
    shell.run_command(f'PATH={root}/a')
    shell.run_command('probe >/dev/null')
    assert table.lookup('probe') == os.path.join(root, "a", "probe")

    shell.run_command('f(){ local X=1; }; f; g(){ :; }; g')
    assert table.lookup('probe') == os.path.join(root, "a", "probe")


# ---------------------------------------------------------------------------
# Static guard: nothing reaches the subscriber behind the owner's back.
# ---------------------------------------------------------------------------

def _observer_call_sites(source: str, relpath: str) -> List[str]:
    """``file:line`` for every ``*.path_changed()`` CALL outside the owner.

    An assignment (``manager.path_changed = ...``) installs the subscription
    and is not a call; only invoking it decides that the table is stale.
    """
    offenders: List[str] = []
    tree = ast.parse(source)
    owners = {
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == OWNER_METHOD
    }
    inside_owner = {id(n) for owner in owners for n in ast.walk(owner)}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "path_changed"
                and id(node) not in inside_owner):
            offenders.append(f"{relpath}:{node.lineno}")
    return offenders


def _hash_clear_sites(source: str, relpath: str) -> List[str]:
    """``file:line`` for every ``*.command_hash.clear()`` call."""
    sites: List[str] = []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "clear"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "command_hash"):
            sites.append(f"{relpath}:{node.lineno}")
    return sites


def _psh_sources() -> List[Tuple[str, str]]:
    root = Path(__file__).resolve().parents[3]
    return [(str(p.relative_to(root)), p.read_text(encoding="utf-8"))
            for p in sorted((root / "psh").rglob("*.py"))]


def test_only_the_owner_calls_the_observer() -> None:
    """One owner decides staleness; no write path calls the subscriber itself."""
    offenders = [site for rel, src in _psh_sources()
                 for site in _observer_call_sites(src, rel)]
    assert offenders == [], (
        f"these call the PATH observer outside "
        f"{OWNER_FILE}#{OWNER_METHOD}: {offenders}")


def test_only_the_subscriber_empties_the_hash_table() -> None:
    """`CommandHashTable` is emptied by the subscription and by `hash -r`, and
    by nothing else -- no second reader may judge a remembered location stale."""
    stray = [site for rel, src in _psh_sources()
             if rel not in HASH_CLEAR_ALLOWED
             for site in _hash_clear_sites(src, rel)]
    assert stray == [], f"these empty the command hash table on their own: {stray}"


SYNTHETIC_OFFENDER = '''
class Sneaky:
    def pop_scope(self):
        if self.path_changed is not None:
            self.path_changed()

    def _effective_binding_changed(self, name, before=None):
        self.path_changed()
'''

SYNTHETIC_HASH_OFFENDER = '''
def resolve(shell):
    shell.state.command_hash.clear()
'''


def test_synthetic_bypass_is_rejected() -> None:
    """The offender both guards must catch, so a green guard means something.

    ``pop_scope`` here calls the observer itself instead of going through the
    owner; the owner's own call must NOT be reported.
    """
    offenders = _observer_call_sites(SYNTHETIC_OFFENDER, "synthetic.py")
    assert offenders == ["synthetic.py:5"], offenders
    assert _hash_clear_sites(SYNTHETIC_HASH_OFFENDER, "synthetic.py") == \
        ["synthetic.py:3"]
