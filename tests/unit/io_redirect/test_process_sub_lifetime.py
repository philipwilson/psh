"""Process-substitution lifetime: one owner, all-or-nothing acquisition (C091),
no give-up timer (C082), one transport on every platform (C081).

Two faces:

* **Fault injection.** Every descriptor and the forked child are registered
  with ONE ``ExitStack`` inside
  ``psh/io_redirect/process_sub.py#create_process_substitution`` as they are
  taken, and ownership transfers to the caller only on the success path. A
  failure injected at any acquisition step must therefore leave the process's
  descriptor census unchanged, leave no temporary directory behind, leave no
  child running, and raise the OS error rather than half-acquiring (C091:
  injecting ``OSError`` at the fork used to leak both pipe ends).
* **Static ownership.** Nothing under ``psh/io_redirect/`` acquires a pipe, a
  FIFO, a temp directory or a fork except that one function, every acquisition
  in it sits inside the stack, and no module there arms ``signal.alarm``
  (C082's 5 s give-up, which opened ``/dev/null``, unlinked the FIFO and
  exited 0 having processed no data, is gone — with a pipe transport there is
  no open to time out). Both checks ship with a synthetic offender.

Serial: the rows fork and read the process-wide ``/dev/fd`` census, and an
xdist worker's low descriptors carry the execnet channel.

Behavioural pins (a consumer opening the path 6 s late, the ``/dev/fd/N``
shape, fd-census stability) live in
``tests/integration/redirection/test_process_sub_late_consumer.py``.
"""
import ast
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.serial

PROJECT_ROOT = Path(__file__).resolve().parents[3]
IO_DIR = PROJECT_ROOT / "psh" / "io_redirect"
OWNER = IO_DIR / "process_sub.py"

# Calls that TAKE a resource a substitution must later release. `os.pipe` and
# `fork_with_signal_window` are ordinary elsewhere in psh (pipelines, command
# substitution); inside the redirect subsystem they mean "a substitution is
# being built", which exactly one function is allowed to do.
ACQUIRING = frozenset({
    "os.pipe", "os.mkfifo", "os.fork", "os.forkpty",
    "tempfile.mkdtemp", "tempfile.mkstemp", "tempfile.NamedTemporaryFile",
    "fork_with_signal_window", "_pipe_endpoints",
})
# The owner and the helper it calls to build the pipe.
ACQUIRING_OWNERS = frozenset({"create_process_substitution", "_pipe_endpoints"})


def _dotted(node: ast.AST) -> str:
    """`os.pipe` for an Attribute chain, `fork_with_signal_window` for a Name."""
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _calls(tree: ast.AST):
    """Yield (dotted_name, node) for every call in *tree*."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield _dotted(node.func), node


def find_alarm_uses(source: str):
    """Names of ``signal.alarm``/``signal.setitimer`` calls in *source*."""
    return [name for name, _ in _calls(ast.parse(source))
            if name in ("signal.alarm", "signal.setitimer")]


def find_acquisitions_outside_owner(source: str):
    """Acquiring calls in *source* not lexically inside an allowed function.

    Used two ways: on a non-owner module every acquisition is an offence, so
    the allowed set is empty; on the owner, a call must sit in one of
    ``ACQUIRING_OWNERS``.
    """
    tree = ast.parse(source)
    inside = {}
    for func in ast.walk(tree):
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(func):
                inside.setdefault(id(node), func.name)
    return [name for name, node in _calls(tree)
            if name in ACQUIRING
            and inside.get(id(node)) not in ACQUIRING_OWNERS]


def find_acquisitions_outside_stack(source: str):
    """Acquiring calls in ``create_process_substitution`` that are not inside
    its ``with ExitStack() as ...:`` body."""
    tree = ast.parse(source)
    owner = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef)
         and n.name == "create_process_substitution"), None)
    if owner is None:
        return ["create_process_substitution is missing"]
    stack_body = set()
    for node in ast.walk(owner):
        if isinstance(node, ast.With) and any(
                _dotted(item.context_expr.func) == "ExitStack"
                for item in node.items
                if isinstance(item.context_expr, ast.Call)):
            for child in node.body:
                for sub in ast.walk(child):
                    stack_body.add(id(sub))
    if not stack_body:
        return ["create_process_substitution has no ExitStack acquisition"]
    return [name for name, node in _calls(owner)
            if name in ACQUIRING and id(node) not in stack_body]


# --------------------------------------------------------------------------
# Static ownership guard + synthetic offenders
# --------------------------------------------------------------------------

def test_only_the_owner_acquires_substitution_resources():
    """No module under psh/io_redirect/ builds a substitution except the owner."""
    offences = {}
    for path in sorted(IO_DIR.rglob("*.py")):
        source = path.read_text()
        found = (find_acquisitions_outside_owner(source) if path == OWNER
                 else [name for name, _ in _calls(ast.parse(source))
                       if name in ACQUIRING])
        if found:
            offences[str(path.relative_to(PROJECT_ROOT))] = found
    assert not offences, (
        "process-substitution resources are acquired outside "
        f"create_process_substitution: {offences}")


def test_owner_acquires_only_inside_its_exit_stack():
    """Every acquisition in the owner sits inside the one ExitStack, so a
    failure at any later step releases it."""
    assert find_acquisitions_outside_stack(OWNER.read_text()) == []


def test_no_module_in_io_redirect_arms_an_alarm():
    """C082's give-up timer is gone and may not come back: a pipe-backed
    substitution has no open to time out."""
    armed = {str(p.relative_to(PROJECT_ROOT)): find_alarm_uses(p.read_text())
             for p in sorted(IO_DIR.rglob("*.py"))
             if find_alarm_uses(p.read_text())}
    assert not armed, f"a substitution give-up timer is back: {armed}"


def test_offender_second_acquisition_site_is_rejected():
    """Synthetic offender: a second creation path in the owner module."""
    offender = textwrap.dedent("""
        import os

        def _create_write_process_substitution(cmd):
            fifo_dir = tempfile.mkdtemp(prefix='psh-psub-')
            os.mkfifo(fifo_dir + '/pipe', 0o600)
            return fifo_dir
    """)
    assert find_acquisitions_outside_owner(offender) == [
        "tempfile.mkdtemp", "os.mkfifo"]


def test_offender_acquisition_outside_the_stack_is_rejected():
    """Synthetic offender: the owner takes a pipe before opening the stack."""
    offender = textwrap.dedent("""
        def create_process_substitution(cmd, direction, shell):
            read_fd, write_fd = os.pipe()
            with ExitStack() as acquisition:
                pid = fork_with_signal_window()
                acquisition.pop_all()
            return read_fd, '/dev/fd/x', pid
    """)
    assert find_acquisitions_outside_stack(offender) == ["os.pipe"]


def test_offender_alarm_is_rejected():
    """Synthetic offender: a re-armed give-up timer."""
    offender = "import signal\ndef f():\n    signal.alarm(5)\n"
    assert find_alarm_uses(offender) == ["signal.alarm"]


# --------------------------------------------------------------------------
# Fault injection at each acquisition step
# --------------------------------------------------------------------------

def _fd_census():
    """Descriptors open in THIS process (the same probe fd every time)."""
    return len(os.listdir("/dev/fd"))


def _psub_temp_dirs():
    return sorted(Path(tempfile.gettempdir()).glob("psh-psub-*"))


class _Boom(OSError):
    """The injected acquisition failure."""


def _shim(module, name, raiser):
    """A stand-in for *module* whose *name* attribute raises."""
    class Shim:
        def __getattr__(self, attr):
            if attr == name:
                return raiser
            return getattr(module, attr)
    return Shim()


@pytest.mark.parametrize("step", ["pipe", "cloexec", "fork", "transfer"])
def test_acquisition_failure_leaks_nothing(shell, monkeypatch, step):
    """A failure at any acquisition step leaves no descriptor, no temp
    directory and no child behind, and raises the OS error (C091)."""
    import psh.executor as executor_pkg
    from psh.io_redirect import process_sub

    def boom(*_a, **_k):
        raise _Boom("injected")

    forked = []
    real_fork = executor_pkg.fork_with_signal_window

    if step == "pipe":
        monkeypatch.setattr(process_sub, "os", _shim(os, "pipe", boom))
    elif step == "cloexec":
        import fcntl as fcntl_mod
        # F_GETFD succeeds, the F_SETFD that clears close-on-exec fails.
        calls = {"n": 0}

        def flaky(fd, cmd, *rest):
            calls["n"] += 1
            if calls["n"] > 1:
                raise _Boom("injected")
            return fcntl_mod.fcntl(fd, cmd, *rest)
        monkeypatch.setattr(process_sub, "fcntl", _shim(fcntl_mod, "fcntl", flaky))
    elif step == "fork":
        monkeypatch.setattr(executor_pkg, "fork_with_signal_window", boom)
    else:  # transfer: the fork succeeded, the hand-over then failed
        def recording_fork():
            pid = real_fork()
            if pid != 0:
                forked.append(pid)
            return pid
        monkeypatch.setattr(executor_pkg, "fork_with_signal_window",
                            recording_fork)

        class ExplodingStack(process_sub.ExitStack):
            def pop_all(self):
                raise _Boom("injected")
        monkeypatch.setattr(process_sub, "ExitStack", ExplodingStack)

    before_fds, before_dirs = _fd_census(), _psub_temp_dirs()
    with pytest.raises(OSError):
        process_sub.create_process_substitution("cat", "out", shell)

    assert _fd_census() == before_fds, "acquisition leaked a descriptor"
    assert _psub_temp_dirs() == before_dirs, "acquisition left a temp directory"
    for pid in forked:
        # Killed AND reaped by the stack: the pid is no longer this process's
        # child at all, so waitpid raises ECHILD.
        with pytest.raises(ChildProcessError):
            os.waitpid(pid, 0)
    if step == "transfer":
        assert forked, "the transfer row never reached the fork"


def test_a_substitution_arms_no_alarm(shell):
    """Creating a substitution nobody ever opens leaves SIGALRM's disposition
    and the process alarm untouched (C082)."""
    from psh.io_redirect import process_sub

    before = signal.getsignal(signal.SIGALRM)
    parent_fd, path, pid = process_sub.create_process_substitution(
        "cat", "out", shell)
    try:
        assert path == f"/dev/fd/{parent_fd}"
        assert signal.getsignal(signal.SIGALRM) is before
        assert signal.alarm(0) == 0, "a give-up timer is pending"
    finally:
        os.close(parent_fd)
        os.waitpid(pid, 0)


def test_the_shells_end_is_moved_clear_of_the_low_descriptors():
    """With fd 0/1/2 closed, os.pipe() hands back a LOW descriptor; the shell's
    end must still land in the high range it hands out as /dev/fd/N, and a
    failure to move it must release both pipe ends.

    Runs in its own interpreter: it closes the standard descriptors, which an
    in-process test must never do (an xdist worker's low fds are its channel).
    """
    script = textwrap.dedent("""
        import os, sys
        report = os.dup(1)
        census = lambda: len(os.listdir('/dev/fd'))
        from psh.io_redirect import process_sub

        for fd in (0, 1, 2):
            os.close(fd)

        # The move happens even though 0/1/2 are the free numbers.
        parent_fd, child_fd = process_sub._pipe_endpoints('out')
        moved = 2 < parent_fd < process_sub.HIGH_FD_LIMIT
        os.close(parent_fd); os.close(child_fd)

        # Failure arm: neither the high move nor the fallback can be taken.
        import fcntl as fcntl_mod
        def boom(*a, **k):
            raise OSError('injected')
        class FcntlShim:
            def __getattr__(self, attr):
                return boom if attr == 'fcntl' else getattr(fcntl_mod, attr)
        class OsShim:
            def __getattr__(self, attr):
                return boom if attr == 'dup2' else getattr(os, attr)
        process_sub.fcntl = FcntlShim()
        process_sub.os = OsShim()
        before = census()
        try:
            process_sub._pipe_endpoints('out')
            raised = False
        except OSError:
            raised = True
        after = census()
        os.write(report, f"{moved} {raised} {before} {after}".encode())
    """)
    env = dict(os.environ, PYTHONPATH=str(PROJECT_ROOT))
    result = subprocess.run([sys.executable, "-c", script],
                            capture_output=True, text=True, env=env,
                            cwd=str(PROJECT_ROOT), timeout=60)
    assert result.returncode == 0, result.stderr
    moved, raised, before, after = result.stdout.split()
    assert moved == "True", "the shell's end was left on a low descriptor"
    assert raised == "True", "the injected move failure was swallowed"
    assert before == after, "a failed move leaked a pipe end"


def test_the_shells_end_avoids_the_numbers_scripts_redirect(shell):
    """The handed-out descriptor sits in the high range, so a consuming
    command's own `3>f` cannot replace it before it opens /dev/fd/N."""
    from psh.io_redirect import process_sub

    parent_fd, path, pid = process_sub.create_process_substitution(
        "cat", "out", shell)
    try:
        assert 2 < parent_fd < process_sub.HIGH_FD_LIMIT, parent_fd
        assert path == f"/dev/fd/{parent_fd}"
    finally:
        os.close(parent_fd)
        os.waitpid(pid, 0)
