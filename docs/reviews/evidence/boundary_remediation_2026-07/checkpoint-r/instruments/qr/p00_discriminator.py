#!/usr/bin/env python3
"""QR scope discriminator: assert psh resolves under the worktree and version == 0.773.0.

Run with cwd INSIDE the worktree AND PYTHONPATH=<worktree>. Note: for
`python3 <script>`, sys.path[0] is the SCRIPT's directory (instruments dir in
the main repo), not cwd — and an editable install resolves to MAIN otherwise.
PYTHONPATH pinning + the resolved-__file__ assertion here is the mechanism.
"""
import os
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/qr/wt"

cwd = os.getcwd()
assert os.path.realpath(cwd).startswith(os.path.realpath(WT)), f"cwd not in worktree: {cwd}"

import psh  # noqa: E402
import psh.version  # noqa: E402

resolved = os.path.realpath(psh.__file__)
assert resolved.startswith(os.path.realpath(WT)), f"psh resolved OUTSIDE worktree: {resolved}"
assert psh.version.__version__ == "0.773.0", f"version mismatch: {psh.version.__version__}"

print(f"DISCRIMINATOR-OK cwd={cwd}")
print(f"sys.path[:3]={sys.path[:3]}")
print(f"psh.__file__={resolved}")
print(f"psh.version.__version__={psh.version.__version__}")
