"""Array assignments join the normal status/transaction model (executor F7).

Array assignments used to run in an early preamble that bypassed the status
model, so:
  - a command substitution in an element/init value lost its status
    (`a[0]=$(false)` reported 0, not 1);
  - a backgrounded assignment always reported success;
  - a later successful element masked an earlier failure (no first-failure
    stop);
  - a bad-subscript bare assignment was fatal even in a script file.

These now behave like a pure scalar assignment. Cases that fork (background)
or need multi-line script-file semantics run psh in a subprocess.
"""

import subprocess
import sys


def _run(script: str, cwd=None):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15,
        cwd=str(cwd) if cwd else None,
    )
    return result.stdout, result.stderr, result.returncode


def _run_file(body: str, tmp_path):
    script = tmp_path / "s.sh"
    script.write_text(body)
    result = subprocess.run(
        [sys.executable, "-m", "psh", str(script)],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def test_element_cmdsub_status():
    out, _, _ = _run('a[0]=$(false); echo "$?"')
    assert out == "1\n"


def test_whole_array_cmdsub_status():
    out, _, _ = _run("a=($(sh -c 'exit 7')); echo \"$?\"")
    assert out == "7\n"


def test_element_cmdsub_success():
    out, _, _ = _run('a[0]=$(true); echo "$?"')
    assert out == "0\n"


def test_background_scalar_assignment_status():
    out, _, _ = _run('x=$(false) & p=$!; wait "$p"; echo "$?"')
    assert out == "1\n"


def test_background_array_element_cmdsub_status():
    out, _, _ = _run('a[0]=$(false) & p=$!; wait "$p"; echo "rc=$?"')
    assert out == "rc=1\n"


def test_background_array_bad_subscript_status():
    out, err, _ = _run('unset a; a[-1]=x & p=$!; wait "$p"; echo "rc=$?"')
    assert out == "rc=1\n"
    assert "bad array subscript" in err


def test_first_failure_stops_and_aborts_under_c():
    # Under -c a bad-subscript bare assignment aborts the rest of the string;
    # b is NOT assigned and `echo AFTER` never runs (bash).
    out, err, rc = _run('unset a b; a[-1]=x b[0]=y; echo AFTER')
    assert out == ""
    assert "bad array subscript" in err
    assert rc == 1


def test_bad_subscript_nonfatal_in_script_file(tmp_path):
    # In a script FILE the same error is non-fatal: it aborts that line, then
    # the next line runs (bash).
    out, err, rc = _run_file("echo BEFORE\na[-1]=x\necho AFTER\n", tmp_path)
    assert out == "BEFORE\nAFTER\n"
    assert "bad array subscript" in err
    assert rc == 0


def test_prefix_position_array_not_identifier():
    # `a[0]=x cmd`: not a valid command-prefix identifier -> diagnose, run the
    # command, do NOT create the array (bash).
    out, err, _ = _run(
        'a[0]=x echo RAN; declare -p a 2>/dev/null || echo NOARRAY')
    assert out == "RAN\nNOARRAY\n"
    assert "not a valid identifier" in err


def test_two_ok_elements_both_assigned():
    out, _, _ = _run('a[0]=x a[1]=y; echo "${a[0]}${a[1]}"')
    assert out == "xy\n"
