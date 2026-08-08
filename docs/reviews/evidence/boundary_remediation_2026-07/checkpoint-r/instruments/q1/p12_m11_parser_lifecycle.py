# Q1 probe 12 (MEDIUM-11): parser single-use ENFORCED. Second .parse() on an
# RD Parser / create_parser handle raises a loud RuntimeError; failed parse
# also consumes; combinator grammar stays reusable.
# Axis: REGRESSION vs recorded base bug (second .parse() returned empty program).
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

from psh.lexer import tokenize
from psh.parser import create_parser

# 1) second parse on a fresh handle
p = create_parser(tokenize('echo hi'))
ast1 = p.parse()
print("first parse ->", type(ast1).__name__)
try:
    ast2 = p.parse()
    print("second parse RETURNED", type(ast2).__name__,
          "-> HOLE (single-use not enforced)")
except RuntimeError as e:
    print("second parse -> RuntimeError (enforced):", str(e)[:100])
except Exception as e:
    print("second parse -> %s (unexpected class): %s" % (type(e).__name__, str(e)[:100]))

# 2) failed parse also consumes
p2 = create_parser(tokenize('if then fi'))
try:
    p2.parse()
    print("bad-input first parse unexpectedly succeeded")
except Exception as e:
    print("bad-input first parse raised", type(e).__name__)
try:
    p2.parse()
    print("post-failure second parse RETURNED -> HOLE")
except RuntimeError as e:
    print("post-failure second parse -> RuntimeError (enforced):", str(e)[:100])
except Exception as e:
    print("post-failure second parse -> %s: %s" % (type(e).__name__, str(e)[:80]))
