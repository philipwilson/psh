import os, sys
sys.path.insert(0, '/Users/pwilson/src/psh-r22-verify')
os.chdir('/Users/pwilson/src/psh-r22-verify')
import psh.version
assert psh.version.__version__ == '0.750.0', psh.version.__version__

from psh.utils import contains_heredoc, open_heredoc_specs
from psh.scripting.command_accumulator import CommandAccumulator, NeedMore, Complete
from psh.shell import Shell

LINE = r'echo \<<EOF'          # backslash-escaped '<' then '<EOF' input redirect
print("input line (repr):", repr(LINE))
print()

# --- Low-level heredoc detectors (what session.py step 2 consults) ---
print("contains_heredoc(...)   =", contains_heredoc(LINE))
specs = open_heredoc_specs(LINE)
print("open_heredoc_specs(...)  =", specs)
if specs:
    print("  spec delimiters        =", [getattr(s, 'delimiter', getattr(s, 'cooked', s)) for s in specs])
print()

# --- Full ParseSession via the production CommandAccumulator driver ---
sh = Shell()
acc = CommandAccumulator(sh)
result = acc.feed(LINE)
print("ParseSession result type:", type(result).__name__)
if isinstance(result, NeedMore):
    print("  -> INCOMPLETE  hint.kind   =", result.hint.kind,
          " hint.detail =", result.hint.detail)
    print("  INCOMPLETE-WITH-HEREDOC-HINT:",
          str(result.hint.kind).lower().endswith('heredoc') or 'heredoc' in str(result.hint.kind).lower())
elif isinstance(result, Complete):
    print("  -> COMPLETE   text =", repr(result.text),
          " error =", result.error)
