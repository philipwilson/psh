"""RED-ON-BASE for the CORRECTED mechanism, in v0.753.0-only API.

Sets up a live per-command redirect frame (what a signal finds mid-command),
then runs BASE's death-path ordering — EXIT trap, then flush, with NO restore —
and reports where the trap's output went.
"""
import io, sys, tempfile, os
sys.path.insert(0, '.')
from psh.shell import Shell
from psh.lexer import tokenize
from psh.parser import parse

def redirected_command(script):
    node = parse(tokenize(script))
    for _ in range(10):
        if hasattr(node, 'redirects'):
            return node
        for attr in ('statements', 'commands', 'pipelines', 'and_or_lists'):
            kids = getattr(node, attr, None)
            if kids:
                node = kids[0]; break
        else:
            break
    raise AssertionError('no command')

d = tempfile.mkdtemp(dir='tmp')
target = os.path.join(d, 'target.txt')

real_stdout = sys.stdout
captured = io.StringIO()
sys.stdout = captured           # stands in for the process's REAL stdout
try:
    sh = Shell()
    sh.run_command('trap "echo cleanup" EXIT')
    frame = sh.io_manager.setup_builtin_redirections(
        redirected_command(': > %s' % target))
    print('command-output', flush=True)
    # BASE death-path ordering: trap, then flush. No restore.
    try:
        sh.trap_manager.execute_exit_trap()
    except SystemExit:
        pass
    except BaseException:
        pass
    for stream in (sh.state.stdout, sh.state.stderr):
        try:
            stream.flush()
        except (OSError, ValueError, AttributeError):
            pass
    sh.io_manager.restore_builtin_redirections(frame)
finally:
    sys.stdout = real_stdout

out = captured.getvalue()
contents = open(target).read()
print("shell stdout received : %r" % out)
print("redirect target holds : %r" % contents)
print("VERDICT:", "MISDIRECTED (red-on-base)" if ('cleanup' in contents and 'cleanup' not in out)
      else "delivered correctly")
