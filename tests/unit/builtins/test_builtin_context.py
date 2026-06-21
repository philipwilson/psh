"""The BuiltinContext seam: array initializers reach declaration builtins as
an explicit parameter, not via shell state (reassessment 2026-06-20, #1).

The executor passes a ``BuiltinContext`` (carrying the structured
``ArrayInitialization`` for each ``name=(...)`` argument) through
``execute_builtin_guarded`` to ``Builtin.execute_in_context``. This replaced
the former ``shell._pending_array_inits`` side channel, so these tests pin the
new contract and guard against the side channel being reintroduced.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from psh.builtins.base import EMPTY_BUILTIN_CONTEXT, Builtin, BuiltinContext

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_builtin_context_lookup():
    ctx = BuiltinContext(array_inits={"a=(1 2)": "SENTINEL"})
    assert ctx.array_init("a=(1 2)") == "SENTINEL"
    assert ctx.array_init("missing") is None
    assert EMPTY_BUILTIN_CONTEXT.array_init("anything") is None


def test_execute_in_context_default_delegates_to_execute():
    """An ordinary builtin needn't know the context exists: the base hook
    forwards to execute()."""
    class Dummy(Builtin):
        @property
        def name(self):
            return "dummy"

        def execute(self, args, shell):
            return 42

    d = Dummy()
    assert d.execute_in_context(["dummy"], shell=None, context=EMPTY_BUILTIN_CONTEXT) == 42


def test_shell_side_channel_is_gone():
    """The old mutable handoff API must not come back."""
    from psh.shell import Shell
    for attr in ("set_pending_array_inits", "clear_pending_array_inits",
                 "pending_array_init", "_pending_array_inits"):
        assert not hasattr(Shell, attr), f"side channel reintroduced: {attr}"


def _run(script):
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
    )


@pytest.mark.parametrize("script,expected", [
    # Every declaration builtin still array-ifies name=(...) via the context.
    ("declare -a a=(1 2 3); echo ${a[@]}/${#a[@]}", "1 2 3/3"),
    ("declare -A m=([x]=1 [y]=2); echo ${m[x]}${m[y]}", "12"),
    ("typeset -a t=(j k); echo ${t[@]}", "j k"),
    ("f() { local arr=(a b c); echo ${arr[1]}; }; f", "b"),
    ("export e=(p q r); declare -p e", 'declare -ax e=([0]="p" [1]="q" [2]="r")'),
    ("readonly r=(x y); echo ${r[@]}", "x y"),
])
def test_declaration_builtins_array_init_via_context(script, expected):
    result = _run(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
