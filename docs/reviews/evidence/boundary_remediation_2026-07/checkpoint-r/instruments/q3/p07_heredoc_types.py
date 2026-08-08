"""Q3 fresh probe: HeredocRedirect required kw-only body + NonExecutableRedirectError arms (MEDIUM-10).

  1. Constructing HeredocRedirect without heredoc_content raises TypeError
     (the invalid executable state is unrepresentable).
  2. heredoc_content is positional-proof: it must be given as a keyword.
  3. The LIVE arm: the alias route (`alias foo='cat <<EOF'; foo`) reaches
     execution as a plain Redirect and is rejected LOUDLY and TYPED
     (internal-integrity closure: loud-rejection probe, not a bash comparison).
  4. The direct arm: handing a structurally-heredoc plain Redirect to the fd
     universe raises NonExecutableRedirectError.
Run with cwd = worktree.
"""
import os
import subprocess
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q3/wt"
assert os.getcwd() == WT
sys.path.insert(0, WT)

import psh  # noqa: E402
assert os.path.realpath(psh.__file__).startswith(os.path.realpath(WT) + os.sep)

from psh.ast_nodes.redirects import HeredocRedirect, Redirect  # noqa: E402
from psh.io_redirect.file_redirect import NonExecutableRedirectError  # noqa: E402

failures = []

# 1. omitted body -> TypeError at construction
try:
    HeredocRedirect(type='<<', target='EOF')
    failures.append("construction WITHOUT body was accepted")
    print("FAIL construction without body accepted")
except TypeError as e:
    print(f"PASS omitted body -> TypeError: {e}")

# 2. body must be keyword-only (positional attempt must not bind it)
try:
    HeredocRedirect('<<', 'EOF', 0, None, None, False, False, False, None,
                    None, None, 'body\n')
    failures.append("12th positional arg bound heredoc_content")
    print("FAIL positional arg bound the body")
except TypeError as e:
    print(f"PASS positional body -> TypeError: {e}")

# valid construction works, empty body is '' not None
ok = HeredocRedirect(type='<<', target='EOF', heredoc_content='')
assert ok.heredoc_content == ''
print("PASS valid kw construction, empty body == ''")

# 3. the LIVE alias route, end-to-end through a subprocess shell
ENV = {"HOME": os.environ["HOME"], "PATH": os.environ["PATH"],
       "PYTHONPATH": WT, "TERM": "dumb"}
r = subprocess.run(
    [sys.executable, "-m", "psh", "-c",
     "shopt -s expand_aliases; alias foo='cat <<EOF'; foo"],
    cwd=WT, env=ENV, capture_output=True, text=True, timeout=30)
loud = r.returncode != 0 and r.stderr.strip() != ""
silent_internal = "Traceback" in r.stderr
print(f"alias route: rc={r.returncode} stderr={r.stderr.strip()!r}")
if not loud:
    failures.append(f"alias route not loud: rc={r.returncode} stderr={r.stderr!r}")
elif silent_internal:
    failures.append("alias route leaks a raw Python traceback")
else:
    print("PASS alias route rejected loudly, no traceback")

# 4. the direct arm: a structurally-heredoc plain Redirect raises typed
from psh.shell import Shell  # noqa: E402

shell = Shell()
bad = Redirect(type='<<', target='EOF')
raised = None
try:
    shell.io_manager.apply_redirections([bad])
except NonExecutableRedirectError as e:
    raised = "typed"
    print(f"PASS direct arm -> NonExecutableRedirectError: {e}")
except Exception as e:
    raised = f"WRONG-TYPE {type(e).__name__}: {e}"
if raised != "typed":
    failures.append(f"direct arm: {raised}")

print("P07-RESULT:", "HOLDS" if not failures else f"HOLE: {failures}")
sys.exit(0 if not failures else 1)
