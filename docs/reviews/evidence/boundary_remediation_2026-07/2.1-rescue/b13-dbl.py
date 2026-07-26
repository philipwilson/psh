import os, sys
sys.path.insert(0, os.getcwd())
import psh
from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor.enhanced_validator_visitor import EnhancedValidatorVisitor
print(f"# psh: {psh.__file__}")
CASES = [
    ("plain-var assign      ", 'FOO=$y'),
    ("plain-var export      ", 'export FOO=$y'),
    ("plain-var local       ", 'fn() { local FOO=$y; }; fn'),
    ("modern export         ", 'export FOO=$(echo $y)'),
    ("backtick export       ", 'export FOO=`echo $y`'),
    ("arith export          ", 'export FOO=$(($y + 1))'),
    ("plain-var readonly    ", 'readonly FOO=$y'),
    ("plain-var declare     ", 'declare FOO=$y'),
]
for label, src in CASES:
    v = EnhancedValidatorVisitor(); v.visit(parse(tokenize(src)))
    n = sum(1 for i in v.issues if 'undefined' in i.message and "'$y'" in i.message)
    print(f"{label} undef-y={n}")
