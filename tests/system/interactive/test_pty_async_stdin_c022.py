"""PTY: an async command inherits its frame's fd 0 at the prompt too (C022).

Interactively the shell HAS job control, so the POSIX async ``/dev/null`` does
not apply to a command backgrounded at the prompt. It still applies inside any
forked child of that shell — a subshell, a pipeline member — because job
control is off there, and that is where C022 bites in an interactive session::

    printf 'payload\\n' > f
    ( cat & wait ) < f      # bash: payload   psh before the fix: nothing
    echo hello | ( cat & wait )

The rule's owner is ``psh/core/stdin_binding.py#StdinBinding``, read by
``psh/executor/process_launcher.py#AsyncJobPolicy.for_launch``; the
non-interactive rows live in
``tests/conformance/bash/test_async_stdin_inheritance_conformance.py``. These
need a REAL TERMINAL: without one the shell does no job control, every launch
takes the same branch, and the interactive half of the rule is unreachable.

The assertions are absolute invariants, so this module drives psh alone. Each
was verified against GNU bash 5.3.15 over the SAME pexpect PTY while the pins
were written (bash prints the file's line / ``hello`` for the inheriting rows,
nothing for the control rows, and leaves no job behind in any of them).
"""

import os
import re
import sys
from pathlib import Path

import pexpect
import pytest

# Terminal ownership and background jobs: never alongside xdist siblings.
pytestmark = pytest.mark.serial

PROMPT = 'PSH\\$ '
PSH_ROOT = str(Path(__file__).resolve().parents[3])
OSC = re.compile(r'\x1b\][^\x07]*\x07')
# Job-control notices (`[1] 1234`, `[1]+  Done  cat`). Filtered out because the
# SUBJECT here is the bytes the background reader consumed, and the two shells
# disagree about which of these notices a forked child prints — a divergence
# with its own owner (registered N-row), not this rule's.
NOTICE = re.compile(r'^\[\d+\][+-]?\s')

# Deliberately awkward: leading/trailing spaces and glob metacharacters, so a
# row cannot pass by echoing a re-expanded or re-split copy of the input.
PAYLOAD = '  a*b?c  '


@pytest.fixture(scope="module")
def workdir(tmp_path_factory):
    d = tmp_path_factory.mktemp("pty-c022")
    (d / "f").write_text(PAYLOAD + "\n")
    return d


def _spawn(workdir):
    """An interactive psh on a real pseudo-terminal, cwd in the temp dir.

    ``cwd`` is pinned as well as ``PYTHONPATH``: ``-m psh`` resolves the
    current directory FIRST, so without this the child would import whichever
    tree the test runner is sitting in.
    """
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': str(workdir),
        'TERM': 'xterm',
        'PS1': 'PSH$ ',
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': PSH_ROOT,
    }
    child = pexpect.spawn(
        sys.executable, ['-u', '-m', 'psh', '--norc', '--force-interactive'],
        timeout=20, encoding='utf-8', env=env, cwd=str(workdir))
    child.send('\r')
    child.expect(PROMPT)
    return child


@pytest.fixture
def psh(workdir):
    """A session of its own per row: a row that leaves a background reader
    holding the terminal must not perturb the next one."""
    child = _spawn(workdir)
    yield child
    child.close(force=True)


def run(child, cmd):
    """Type *cmd*, consume its echo, and return its output lines.

    The PTY is drained by ``expect``, which reads continuously — a bare sleep
    would leave the shell blocked on a full pty buffer and every column of the
    matrix meaningless.
    """
    child.send(cmd + '\r')
    child.expect_exact(cmd)
    child.expect(PROMPT)
    text = OSC.sub('', child.before).replace('\r', '')
    return [ln for ln in text.split('\n')
            if ln.strip() and not NOTICE.match(ln.strip())]


INHERITING = [
    # The shape the slot-1.1 verifier flagged: a forked SUBSHELL with a
    # redirect, backgrounding a reader inside it.
    ("subshell_redirect", '( cat & wait ) < f', [PAYLOAD]),
    ("brace_redirect", '{ cat & wait; } < f', [PAYLOAD]),
    ("pipe_into_subshell", 'echo hello | ( cat & wait )', ['hello']),
    ("pipe_into_brace", 'echo hello | { cat & wait; }', ['hello']),
    # The reader is a `read` in a backgrounded compound, which then prints what
    # it captured — an observable row, not just "the shell survived".
    ("pipe_into_read_group",
     'echo hi | { { read v; echo "[$v]"; } & wait; }', ['[hi]']),
]


@pytest.mark.parametrize("cmd,expected", [(c, e) for _, c, e in INHERITING],
                         ids=[i for i, _, _ in INHERITING])
def test_async_reader_inherits_frame_stdin_at_the_prompt(psh, cmd, expected):
    """C022: at the prompt the reader still gets the frame's input.

    Before the fd-0 binding, the forked child's job control was off, so the
    launcher gave every background command ``/dev/null`` and these printed
    nothing.
    """
    assert run(psh, cmd) == expected, cmd
    # The session survives and still owns the terminal.
    assert run(psh, 'echo alive') == ['alive']


def test_background_reader_with_no_frame_input_does_not_steal_the_terminal(psh):
    """C022 control: nothing supplied fd 0, so the POSIX ``/dev/null`` stands.

    ``( cat & wait )`` must return immediately with no output. If the reader
    kept the TERMINAL instead, it would swallow the next command typed at the
    prompt — which the follow-up row would then not see.
    """
    assert run(psh, '( cat & wait )') == []
    assert run(psh, 'echo alive') == ['alive']
    assert run(psh, 'jobs') == [], "a completed subshell left a job behind"
