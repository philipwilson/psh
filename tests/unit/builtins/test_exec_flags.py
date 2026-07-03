"""exec flag tests (reappraisal #16 Tier-2): -a NAME, -c, -l.

`exec` replaces the process image, so these run psh in a subprocess and read
the child's stdout. Pinned to bash 5.2.
"""

import subprocess
import sys


def _run_psh(script):
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True,
    )


# Single-quote the inner command so psh keeps $0/$FOO literal and the child
# shell (sh) is the one that expands them.

def test_exec_a_overrides_argv0():
    """`exec -a NAME cmd` runs cmd with argv[0] == NAME (bash)."""
    result = _run_psh("exec -a MYNAME sh -c 'echo $0'")
    assert result.returncode == 0
    assert result.stdout.strip() == "MYNAME"


def test_exec_a_passes_operands_through():
    """Operands after the command reach it normally; `sh -c script A B`
    still assigns $0=A, $1=B (bash parity — -a only sets the exec'd process
    argv[0], which `sh -c` reassigns from its first operand)."""
    result = _run_psh("exec -a COOLNAME sh -c 'echo [$0] [$1]' ARG0 ARG1")
    assert result.returncode == 0
    assert result.stdout.strip() == "[ARG0] [ARG1]"


def test_exec_c_clean_environment():
    """`exec -c cmd` runs with an empty environment (bash)."""
    result = _run_psh("FOO=bar; export FOO; exec -c sh -c 'echo [${FOO:-empty}]'")
    assert result.returncode == 0
    assert result.stdout.strip() == "[empty]"


def test_exec_c_still_finds_path_command():
    """`-c` empties the child env but the command is still located on the
    shell's PATH."""
    result = _run_psh("exec -c sh -c 'echo hello'")
    assert result.returncode == 0
    assert result.stdout.strip() == "hello"


def test_exec_l_login_dash_prefix():
    """`exec -l cmd` prepends '-' to argv[0] (login-shell convention)."""
    result = _run_psh("exec -l -a foo sh -c 'echo $0'")
    assert result.returncode == 0
    assert result.stdout.strip() == "-foo"


def test_exec_flags_no_command_is_noop():
    """`exec -a X` with no command succeeds without replacing the shell."""
    result = _run_psh('exec -a X; echo survived')
    assert result.returncode == 0
    assert result.stdout.strip() == "survived"


def test_exec_double_dash_ends_options():
    """`exec -- cmd` stops option parsing (bash)."""
    result = _run_psh("exec -a foo -- sh -c 'echo $0'")
    assert result.returncode == 0
    assert result.stdout.strip() == "foo"
