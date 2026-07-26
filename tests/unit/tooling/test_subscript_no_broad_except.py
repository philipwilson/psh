"""Ratchet: the subscript keying/extent modules stay free of broad catches
(remediation 2.3, MEDIUM-12a).

The r22 finding was two ``except Exception`` fallbacks in
``psh/expansion/subscript.py`` (v0.750.0 lines 129/144) that silently degraded
un-lexable subscript text to a LITERAL key — masking every quote-blind-extent
mis-key (MEDIUM-4) as a wrong-key write, and any internal defect as a key.
Slot 2.3 deleted them for the typed ``SubscriptSyntaxError`` (only the
lexer/word-builder's own ``PshError`` failures translate; anything else
propagates as an internal defect under strict-errors).

No pre-existing tooling registry counted those sites (the Q2 VT ratchet keys
on ValueError/TypeError handler names), so per the integrator's slot-2.3
ruling this ratchet is BORN here instead of shrunk: the guarded module set
must contain ZERO broad handlers, forever. Shrink-only means the guarded set
may only GROW (add modules as their broad catches are removed); a broad
handler reappearing in a guarded module fails loudly.

A "broad handler" is: a bare ``except:``, ``except Exception``, or
``except BaseException`` (alone or in a tuple), regardless of whether it
re-raises — in THESE modules even a translate-and-raise must name the typed
failure classes it converts (``except PshError`` is the widest allowed).
The detector is self-tested against synthetic offenders below.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]

# The guarded set (GROW-only; never remove an entry without removing the file).
GUARDED = (
    "psh/expansion/subscript.py",     # the ONE keying authority
    "psh/expansion/param_parser.py",  # the ${...} classifier + extent scanner
)

_BROAD_NAMES = {"Exception", "BaseException"}


def _handler_names(handler: ast.ExceptHandler):
    """The exception names a handler catches; [None] for a bare ``except:``."""
    t = handler.type
    if t is None:
        return [None]
    elts = t.elts if isinstance(t, ast.Tuple) else [t]
    out = []
    for e in elts:
        if isinstance(e, ast.Name):
            out.append(e.id)
        elif isinstance(e, ast.Attribute):
            out.append(e.attr)
        else:
            out.append("?")
    return out


def broad_handlers(src: str, relpath: str):
    """[(relpath, lineno, caught)] for every broad handler in ``src``."""
    hits = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        for name in _handler_names(node):
            if name is None or name in _BROAD_NAMES:
                hits.append((relpath, node.lineno,
                             name if name is not None else "<bare>"))
    return hits


def test_guarded_modules_have_no_broad_except():
    offenders = []
    for rel in GUARDED:
        path = ROOT / rel
        offenders.extend(broad_handlers(path.read_text(), rel))
    assert not offenders, (
        "broad except reappeared in a subscript module (MEDIUM-12a "
        "regression) — catch the typed failure classes instead "
        f"(PshError at the widest): {offenders}")


def test_guarded_files_exist():
    """A renamed/moved module must update GUARDED — the guard cannot rot by
    silently guarding nothing."""
    for rel in GUARDED:
        assert (ROOT / rel).is_file(), rel


# --- synthetic offenders: the detector must bite -----------------------------

def test_offender_bare_except_is_flagged():
    src = "try:\n    x()\nexcept:\n    pass\n"
    assert broad_handlers(src, "f.py") == [("f.py", 3, "<bare>")]


def test_offender_except_exception_is_flagged():
    src = "try:\n    x()\nexcept Exception:\n    raise Y()\n"
    assert broad_handlers(src, "f.py") == [("f.py", 3, "Exception")]


def test_offender_tuple_and_qualified_forms_are_flagged():
    src = ("try:\n    x()\nexcept (ValueError, Exception) as e:\n    pass\n"
           "try:\n    y()\nexcept builtins.BaseException:\n    pass\n")
    hits = broad_handlers(src, "f.py")
    assert ("f.py", 3, "Exception") in hits
    assert ("f.py", 7, "BaseException") in hits


def test_typed_catches_are_not_flagged():
    src = ("try:\n    x()\nexcept PshError as e:\n    raise Z(1) from e\n"
           "try:\n    y()\nexcept (KeyError, ValueError):\n    pass\n")
    assert broad_handlers(src, "f.py") == []
