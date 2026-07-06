"""Prefix `a+=z cmd` (scalar append onto an array) is pure and env-safe (F8).

`resolve_append_assignment` used to mutate the live array in place before the
prefix machinery snapshotted it, and then place the IndexedArray OBJECT into
`shell.env`. So `a=(x y); a+=z /usr/bin/true` raised a Python TypeError from
execve ("expected str ... not IndexedArray") and left `a` mutated as (xz y).

Bash: the command runs (rc 0), its environment sees the scalar view `a=xz`,
and the original array is restored to (x y). Append resolution is now pure
(works on a copy) and the environment value is serialized to the array's
scalar view (element 0).
"""

import subprocess
import sys


def _run(script: str):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def test_prefix_array_append_command_runs_and_restores():
    out, err, rc = _run(
        'a=(x y); a+=z /usr/bin/true; echo "rc=$?"; declare -p a')
    assert rc == 0
    assert err == ""
    assert out == 'rc=0\ndeclare -a a=([0]="x" [1]="y")\n'


def test_prefix_array_append_external_env_view():
    # printenv (external) must see the scalar view "xz", never an object repr.
    out, _, _ = _run('a=(x y); a+=z printenv a')
    assert out == "xz\n"
    assert "IndexedArray" not in out


def test_prefix_array_append_child_scalar_view():
    out, _, _ = _run("a=(x y); a+=z sh -c 'echo \"a=$a\"'; declare -p a")
    assert out == 'a=xz\ndeclare -a a=([0]="x" [1]="y")\n'


def test_prefix_assoc_append_restores():
    out, _, rc = _run(
        'declare -A h=([k]=v); h+=z /usr/bin/true; echo "rc=$?"; declare -p h')
    assert rc == 0
    assert out == 'rc=0\ndeclare -A h=([k]="v" )\n'


def test_prefix_array_append_never_leaks_object_repr():
    # No IndexedArray/AssociativeArray repr must ever reach an external env.
    out, err, _ = _run('a=(x y); a+=z env')
    assert "IndexedArray" not in out and "IndexedArray" not in err
    assert "a=xz" in out


def test_pure_array_append_still_permanent():
    # Regression guard: the bare (no-command) append still mutates permanently.
    out, _, _ = _run('a=(x y); a+=z; declare -p a')
    assert out == 'declare -a a=([0]="xz" [1]="y")\n'


def test_env_invariant_only_strings_after_array_prefix(captured_shell):
    # Invariant: an array `+=` prefix must never place a non-str value into
    # shell.env. Run through a full command and assert every env value is str.
    shell = captured_shell
    shell.run_command('a=(x y)')
    shell.run_command('a+=z /usr/bin/true')
    non_str = {k: type(v).__name__ for k, v in shell.env.items()
               if not isinstance(v, str)}
    assert non_str == {}, f"non-string env values leaked: {non_str}"
