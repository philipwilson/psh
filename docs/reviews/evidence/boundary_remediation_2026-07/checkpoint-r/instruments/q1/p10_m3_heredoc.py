# Q1 probe 10 (MEDIUM-3): escaped \<< is NOT a heredoc. Fresh 0.773.0
# equivalent of wave0-base-probes/claim_b_psh.py (0.750.0-pinned).
# Base bug: session pending-heredoc detection was regex-based -> `echo \<<EOF`
# misdetected as heredoc -> PS2 drop + swallowed next line.
# Tip claim (v0.761.0): pending heredocs derived from LEXER EVENTS.
# Axis: REGRESSION (accumulator verdict) + DIVERGENCE (-c channel vs bash,
# run by the companion p10_m3_heredoc_c.sh).
import os
import sys

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt')
assert os.getcwd() == WT
sys.path.insert(0, WT)
import psh.version
assert psh.version.__version__ == '0.773.0'
assert psh.version.__file__.startswith(WT)
print("DISCRIMINATOR OK:", psh.version.__version__)

from psh.scripting.command_accumulator import CommandAccumulator, NeedMore, Complete
from psh.shell import Shell

sh = Shell(norc=True)
for line in [r'echo \<<EOF', r'cat <<EOF', r'echo \\<<EOF']:
    acc = CommandAccumulator(sh)
    result = acc.feed(line)
    kind = type(result).__name__
    detail = ''
    if isinstance(result, NeedMore):
        detail = ' hint.kind=%s' % (result.hint.kind,)
    print("line %-16r -> %s%s" % (line, kind, detail))
print()
print("expectations: 'echo \\<<EOF' COMPLETE (escaped, no heredoc);")
print("              'cat <<EOF' NeedMore w/ heredoc hint (real heredoc);")
print("              'echo \\\\<<EOF' NeedMore (escaped backslash THEN <<EOF heredoc).")
sh.close()
