"""Q3 fresh probe: depth>=2 mutation attempts on a LIVE lexed value graph (slot 2.5).

NOT the suite's own cells: attacks end_pos (the suite pins start_pos), a
CollectedHeredoc/HeredocSpec node inside the heredoc map, and the heredocs
mapping itself, then re-reads the graph to prove values unchanged.
Run with cwd = worktree.
"""
import dataclasses
import os
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q3/wt"
assert os.getcwd() == WT
sys.path.insert(0, WT)

from psh.lexer.heredoc_lexer import HeredocLexer  # noqa: E402
import psh  # noqa: E402
assert os.path.realpath(psh.__file__).startswith(os.path.realpath(WT) + os.sep)

unit = HeredocLexer('echo "a$b"c <<E\nbody\nE\n',
                    warn_unterminated=False).tokenize_with_heredocs()

results = []


def attempt(label, fn, expect=(dataclasses.FrozenInstanceError, TypeError, AttributeError)):
    try:
        fn()
    except expect as e:
        results.append((label, "REJECTED", type(e).__name__))
        return
    except Exception as e:  # unexpected type
        results.append((label, "UNEXPECTED-EXC", type(e).__name__))
        return
    results.append((label, "MUTATION-SUCCEEDED", "-"))


# find a part-bearing token
tok = next(t for t in unit.tokens if t.parts)
part = tok.parts[0]
before_end = (part.end_pos.line, part.end_pos.column, part.end_pos.offset)

# depth-3: LexedUnit -> Token -> TokenPart -> Position (END pos, not the suite's start_pos)
attempt("part.end_pos.line = 999", lambda: setattr(part.end_pos, "line", 999))
attempt("part.end_pos.offset = 999", lambda: setattr(part.end_pos, "offset", 999))
# depth-2: token.parts element attr (value) on a DIFFERENT token than suite fixture path
attempt("part.value = 'PWNED'", lambda: setattr(part, "value", "PWNED"))
# new-attribute attach at depth 2
attempt("part.pwned = 1", lambda: setattr(part, "pwned", 1))
# token itself
attempt("tok.value = 'X'", lambda: setattr(tok, "value", "X"))
# tuple surface: slice-assign (suite pins append/setitem/clear)
attempt("tok.parts[0:1] = []", lambda: tok.parts.__setitem__(slice(0, 1), []))
# heredoc map nodes
if unit.heredocs:
    key = next(iter(unit.heredocs))
    hd = unit.heredocs[key]
    for f in dataclasses.fields(hd):
        attempt(f"heredoc.{f.name} rebind", lambda f=f: setattr(hd, f.name, getattr(hd, f.name)))
        break  # one field is enough; the census guard covers the rest
    attempt("heredocs.pop", lambda: unit.heredocs.pop(key))
    attempt("heredocs.clear", lambda: unit.heredocs.clear())
    # descend: CollectedHeredoc inner nodes
    for fname in ("spec",):
        inner = getattr(hd, fname, None)
        if inner is not None and dataclasses.is_dataclass(inner):
            ifld = dataclasses.fields(inner)[0]
            attempt(f"heredoc.{fname}.{ifld.name} rebind",
                    lambda: setattr(inner, ifld.name, getattr(inner, ifld.name)))

after_end = (part.end_pos.line, part.end_pos.column, part.end_pos.offset)
assert after_end == before_end, f"end_pos CHANGED: {before_end} -> {after_end}"
assert part.value != "PWNED"
assert isinstance(tok.parts, tuple)

ok = all(v == "REJECTED" for _, v, _ in results)
for label, verdict, exc in results:
    print(f"{'PASS' if verdict == 'REJECTED' else 'FAIL':4} {label:42} {verdict} ({exc})")
print("P01-RESULT:", "ALL-REJECTED" if ok else "HOLE-FOUND")
sys.exit(0 if ok else 1)
