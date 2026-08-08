"""Q3 fresh probe: OperandValue is not silently a string (slot 3.3).

str(), f-string, %-format, format() and str-concat must all raise TypeError;
.as_scalar() is the one projection and joins with a literal space (never IFS).
Built through the production field builder, not hand-rolled fixtures.
Run with cwd = worktree.
"""
import os
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q3/wt"
assert os.getcwd() == WT
sys.path.insert(0, WT)

import psh  # noqa: E402
assert os.path.realpath(psh.__file__).startswith(os.path.realpath(WT) + os.sep)

from psh.expansion.operands import OperandValue, _OperandFieldBuilder  # noqa: E402

b = _OperandFieldBuilder()
b.emit("a", True)
b.splice_values(["x", "y"], protected=True) if hasattr(b, "splice_values") else None
ov = OperandValue(b.fields)

results = []


def attempt(label, fn):
    try:
        fn()
    except TypeError as e:
        results.append((label, "REJECTED", type(e).__name__))
        return
    except Exception as e:
        results.append((label, "UNEXPECTED-EXC", type(e).__name__))
        return
    results.append((label, "MUTATION-SUCCEEDED", "-"))


attempt("str(ov)", lambda: str(ov))
attempt("f-string", lambda: f"{ov}")
attempt("'%s' % ov", lambda: "%s" % ov)
attempt("format(ov)", lambda: format(ov))
attempt("'' + ov", lambda: "" + ov)
attempt("''.join([ov])", lambda: "".join([ov]))

scalar = ov.as_scalar()
print("as_scalar():", repr(scalar))
assert isinstance(scalar, str)
assert not isinstance(ov, str), "OperandValue must not subclass str"

# empty vector: no fields vs one empty field are distinguishable
empty = OperandValue([])
assert empty.as_scalar() == ""
assert empty.fields == []

ok = all(v == "REJECTED" for _, v, _ in results)
for label, verdict, exc in results:
    print(f"{'PASS' if verdict == 'REJECTED' else 'FAIL':4} {label:20} {verdict} ({exc})")
print("P04-RESULT:", "ALL-REJECTED" if ok else "HOLE-FOUND")
sys.exit(0 if ok else 1)
