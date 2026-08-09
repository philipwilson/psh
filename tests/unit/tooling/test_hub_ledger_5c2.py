"""Ratchet: every ownership HUB carries a disposition, and new hubs are loud.

Campaign §11 asks that large ownership hubs be decomposed "around NAMED
TRANSACTIONS rather than arbitrary line counts", and that decomposition be
"measured by responsibility and testability, not cosmetic extraction". This
ledger is the standing half of that: every hub-sized function in ``psh/``
carries an explicit disposition with a reason a future reader can check, stale
rows are forced out, and a NEW hub cannot land silently.

**WHAT THIS RATCHETS: COMPLEXITY, NOT DOCUMENTATION.** The threshold is
EXECUTABLE lines, and that choice is load-bearing rather than incidental. The
campaign's own function-length census counts raw source lines; measured at the
base tree this ledger was built from, **57 of its 60 rows fall BELOW 100
executable lines** — ``ShellState.__init__`` scores 323 nominal while carrying
**95 executable and 190 comment** lines, and only **3** rows reach 100
executable. Both of the census's named "campaign growers" had in fact SHRUNK in
code while growing in provenance comments (``ReadBuiltin.execute`` −3
executable / +14 comment; ``ParseTreeBuiltin.execute`` −3 / +9). A ratchet keyed
on raw length would therefore have fired on the slot that narrowed an exception
net and documented why — punishing precisely the practice this campaign
enforces. It would be a documentation-suppression device. So: comments and
docstrings are free, and the arms below PROVE that both ways rather than
asserting it.

Every figure above is produced by ``executable_lines`` BELOW — this module's own
metric — not by the Phase A survey instrument that motivated the design. The
distinction is not pedantry: that instrument counted a code line carrying a
TRAILING comment as a comment line, so it reported 58/2 and ``94/191`` where the
canonical rule reports 57/3 and ``95/190``. Same conclusion, different margins —
and the margins are exactly what the rules below exist to pin. A docstring
quoting a different implementation's numbers than its body enforces is the
NAME-VS-BODY defect this campaign brings against other people's work.

**THE METRIC (one canonical implementation — ``executable_lines`` below).**
EXECUTABLE = span − docstring lines − comment-only lines − blank lines. Two
similar-looking implementations disagreed at the margins while this was being
designed, so the rules are stated and the guard owns the only implementation
any figure comes from:

* a line carrying code AND a trailing comment counts as CODE — a "comment line"
  is one whose COMMENT token STARTS the line (``tokenize``, never a ``#``
  substring search, which would misread a ``#`` inside a string);
* a comment line inside a multiline expression counts as comment;
* blank lines inside a docstring are counted ONCE, inside the docstring —
  counting them twice drives ``exec`` negative on docstring-heavy functions.

**MEMBERSHIP.**

* ENTRY (the growth arm): any function with **>= 100 EXECUTABLE lines** and no
  row fails loudly, naming the offender. That is the ratchet.
* GRANDFATHERED: rows created from the campaign census baseline stay
  dispositioned even when their executable length is under the threshold. The
  census's raw-length baseline stays reconcilable that way, and a hub already
  argued about does not silently lose its argument.
* EXIT (stale-forcing): a row whose function no longer exists, or whose NOMINAL
  length has fallen below 100, must be REMOVED. A decomposition therefore
  forces its own row out in the same commit, and no row can outlive the body it
  describes.

**KEY** is ``(file, qualname)`` — stable when OTHER functions are renamed,
unlike anything anchored to a line number. It is not unique tree-wide (42
duplicate keys exist, e.g. ``JobManager.wait_for_job`` appears three times
behind two ``@overload`` stubs), so uniqueness is ASSERTED over the qualifying
set rather than assumed.

**POINTER** rows exist because the census counts a nested function both on its
own and inside its parent. A pointer row names the parent that owns the
argument, so one body never carries two dispositions.
"""

import ast
import io
import pathlib
import tokenize

import pytest

from tests.unit.tooling._hub_ledger_rows import LEDGER

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"

THRESHOLD_EXECUTABLE = 100
THRESHOLD_NOMINAL = 100

DISPOSITIONS = {"JUSTIFIED-KEEP", "DECOMPOSED-THIS-SLOT", "DECOMPOSE-PENDING",
                "POINTER"}


# --------------------------------------------------------------------------
# THE canonical metric. Every figure in this module comes from here.
# --------------------------------------------------------------------------

def _comment_start_lines(source: str) -> set:
    """Line numbers whose FIRST token is a comment.

    A trailing comment on a code line does not make that line a comment line,
    which is why this asks the tokenizer for the token's start column context
    rather than searching for ``#``.
    """
    lines = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                line = tok.line[:tok.start[1]]
                if not line.strip():
                    lines.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return lines


def executable_lines(node: ast.AST, source: str, comment_lines: set) -> int:
    """Executable line count for ``node`` — the ledger's threshold metric."""
    src_lines = source.splitlines()
    lo, hi = node.lineno, node.end_lineno
    span = set(range(lo, hi + 1))

    doc_span = set()
    body = list(getattr(node, "body", []))
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        d = body[0]
        doc_span = set(range(d.lineno, d.end_lineno + 1))

    rest = span - doc_span
    comments = len(comment_lines & rest)
    blanks = sum(1 for n in rest
                 if n <= len(src_lines) and not src_lines[n - 1].strip())
    return (hi - lo + 1) - len(doc_span) - comments - blanks


def nominal_lines(node: ast.AST) -> int:
    return node.end_lineno - node.lineno + 1


def _is_overload_stub(node: ast.AST) -> bool:
    """``@overload`` declares a SIGNATURE, not a body.

    ``JobManager.wait_for_job`` is the live instance: two ``@overload`` stubs
    plus the real 120-line implementation, all sharing one qualname. Counting
    the stubs as functions would make the ledger key ambiguous for a body that
    genuinely needs a row — so the stubs are excluded as the declarations they
    are, rather than the key being weakened to tolerate them.
    """
    for dec in getattr(node, "decorator_list", []):
        name = dec.attr if isinstance(dec, ast.Attribute) else getattr(dec, "id", None)
        if name == "overload":
            return True
    return False


def iter_functions(source: str, rel: str):
    """Yield (qualname, node) for every function, nested ones included."""
    tree = ast.parse(source)

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                yield from visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}{child.name}"
                if not _is_overload_stub(child):
                    yield qual, child
                yield from visit(child, f"{qual}.")

    yield from visit(tree, "")


def measure_tree():
    """(file, qualname) -> (executable, nominal) for all of psh/."""
    out = {}
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(ROOT))
        source = path.read_text()
        comments = _comment_start_lines(source)
        for qual, node in iter_functions(source, rel):
            out.setdefault((rel, qual), []).append(
                (executable_lines(node, source, comments), nominal_lines(node)))
    return out



# --------------------------------------------------------------------------
# Arms
# --------------------------------------------------------------------------

def test_dispositions_are_from_the_declared_vocabulary():
    bad = {k: v[0] for k, v in LEDGER.items() if v[0] not in DISPOSITIONS}
    assert not bad, f"unknown disposition(s): {bad}"


def test_every_qualifying_function_has_a_row():
    """ENTRY / GROWTH ARM: a new hub cannot land silently."""
    measured = measure_tree()
    missing = []
    for (rel, qual), sizes in sorted(measured.items()):
        if any(ex >= THRESHOLD_EXECUTABLE for ex, _ in sizes):
            if (rel, qual) not in LEDGER:
                ex = max(e for e, _ in sizes)
                missing.append(f"{rel}::{qual} ({ex} executable lines)")
    assert not missing, (
        "NEW ownership hub(s) with no ledger disposition. A function of this "
        "size needs an explicit owner argument — which named transaction owns "
        "it, and why this length is the honest shape — added to LEDGER in the "
        "SAME commit. Comments and docstrings do NOT count toward the "
        "threshold, so this fired on executable complexity:\n  "
        + "\n  ".join(missing))


def test_no_stale_rows():
    """EXIT: a row may not outlive the body it describes."""
    measured = measure_tree()
    stale = []
    for (rel, qual), (_disp, _reason) in sorted(LEDGER.items()):
        sizes = measured.get((rel, qual))
        if sizes is None:
            stale.append(f"{rel}::{qual} — function no longer exists")
        elif max(n for _, n in sizes) < THRESHOLD_NOMINAL:
            stale.append(
                f"{rel}::{qual} — now {max(n for _, n in sizes)} nominal lines, "
                "below the hub threshold; the row has done its job, delete it")
    assert not stale, (
        "STALE ledger row(s). A decomposition removes its own row in the same "
        "commit; a rename moves it:\n  " + "\n  ".join(stale))


def test_keys_are_unique_among_qualifying_functions():
    """The key is (file, qualname), which is NOT unique tree-wide."""
    measured = measure_tree()
    collisions = []
    for (rel, qual), sizes in sorted(measured.items()):
        if len(sizes) > 1 and (rel, qual) in LEDGER:
            collisions.append(f"{rel}::{qual} has {len(sizes)} definitions "
                              f"(sizes {sizes})")
    assert not collisions, (
        "A ledger key names more than one function, so one row would silently "
        "carry two dispositions (the @overload / property+setter shape):\n  "
        + "\n  ".join(collisions))


def test_pointer_rows_name_a_real_parent_row():
    orphans = []
    for (rel, qual), (disp, _reason) in sorted(LEDGER.items()):
        if disp != "POINTER":
            continue
        parents = [q for (f, q) in LEDGER
                   if f == rel and q != qual and qual.startswith(q + ".")]
        if not parents:
            orphans.append(f"{rel}::{qual}")
    assert not orphans, (
        "POINTER row(s) with no enclosing row to point at:\n  "
        + "\n  ".join(orphans))


def test_reasons_are_specific():
    """A generic reason is worse than none: it looks like an argument."""
    generic = {"too complex", "legacy", "needs work", "historical", "n/a",
               "cohesive", "fine", "ok", "as-is"}
    weak = []
    for (rel, qual), (_disp, reason) in sorted(LEDGER.items()):
        text = reason.strip()
        if len(text) < 40 or text.lower().rstrip(".") in generic:
            weak.append(f"{rel}::{qual}: {reason!r}")
    assert not weak, (
        "Ledger reason(s) too thin to check. State which named transaction "
        "owns the body and why the length is honest:\n  " + "\n  ".join(weak))


# --- guard-the-guard -------------------------------------------------------

_SUB_THRESHOLD = '''
def f(a):
    x = 1
    y = 2
    return x + y
'''

_COMMENT_FATTENED = "def f(a):\n" + "".join(
    f"    # provenance line {i}\n" for i in range(200)) + "    return a\n"

_DOCSTRING_FATTENED = ('def f(a):\n    """\n'
                       + "".join(f"    line {i}\n" for i in range(200))
                       + '    """\n    return a\n')

_EXECUTABLE_HUB = "def f(a):\n" + "".join(
    f"    a = a + {i}\n" for i in range(150)) + "    return a\n"


def _measure_source(source: str) -> int:
    comments = _comment_start_lines(source)
    quals = dict(iter_functions(source, "<synthetic>"))
    return executable_lines(quals["f"], source, comments)


@pytest.mark.parametrize("label,source", [
    ("200 comment lines", _COMMENT_FATTENED),
    ("200 docstring lines", _DOCSTRING_FATTENED),
])
def test_growth_arm_ignores_documentation(label, source):
    """CONTROL (c-5): documentation can never create a hub.

    Both bodies are two executable lines under 200+ lines of prose. If either
    scored at or above the threshold, the ratchet would fire on a function
    whose author only explained themselves.
    """
    measured = _measure_source(source)
    assert measured < THRESHOLD_EXECUTABLE, (
        f"{label}: scored {measured} executable lines — documentation is "
        "being counted as complexity, which is the exact failure this "
        "metric exists to avoid")


def test_growth_arm_fires_on_executable_growth():
    """RED (c-5): real executable growth DOES cross the threshold.

    The control above is only meaningful next to this: a metric that never
    fires would pass the control arm trivially.
    """
    measured = _measure_source(_EXECUTABLE_HUB)
    assert measured >= THRESHOLD_EXECUTABLE, (
        f"scored {measured} executable lines for a 150-statement body — the "
        "growth arm cannot fire, so the ratchet is inert")


def test_metric_counts_a_trailing_comment_line_as_code():
    """MARGIN RULE: code + trailing comment is CODE, not comment."""
    source = "def f(a):\n" + "".join(
        f"    a = a + {i}  # step {i}\n" for i in range(120)) + "    return a\n"
    measured = _measure_source(source)
    assert measured >= THRESHOLD_EXECUTABLE, (
        f"scored {measured}: trailing comments are being treated as comment "
        "LINES, which would let a hub hide behind end-of-line annotation")


def test_metric_does_not_read_hash_inside_a_string_as_a_comment():
    """MARGIN RULE: '#' in a string literal is not a comment."""
    source = "def f(a):\n" + "".join(
        f'    a = "# not a comment {i}"\n' for i in range(120)) + "    return a\n"
    measured = _measure_source(source)
    assert measured >= THRESHOLD_EXECUTABLE, (
        f"scored {measured}: a '#' inside a string is being counted as a "
        "comment line — the substring-search bug this metric avoids")


def test_sub_threshold_function_needs_no_row():
    assert _measure_source(_SUB_THRESHOLD) < THRESHOLD_EXECUTABLE


# --- the @overload exclusion, and its control ------------------------------

_OVERLOADED = '''
from typing import overload

class C:
    @overload
    def m(self, a: int) -> int: ...
    @overload
    def m(self, a: str) -> str: ...
    def m(self, a):
        return a
'''

_NOT_OVERLOAD = '''
class C:
    @property
    def m(self):
        return 1
'''


def test_overload_stubs_are_excluded_so_the_key_stays_unambiguous():
    """``@overload`` declares a SIGNATURE, not a body.

    ``JobManager.wait_for_job`` is the live instance — two stubs plus the real
    implementation under one qualname. Counting the stubs would make the
    ledger key ambiguous for a body that genuinely needs a row.
    """
    quals = [q for q, _ in iter_functions(_OVERLOADED, "<synthetic>")]
    assert quals.count("C.m") == 1, (
        "expected the two @overload stubs to be excluded and only the real "
        f"body counted; got {quals}")


def test_the_exclusion_is_narrow_and_does_not_swallow_other_decorators():
    """CONTROL: only ``overload`` is excluded, not decorators in general.

    An exclusion that quietly dropped every decorated function would hide
    real hubs behind a ``@property`` or ``@staticmethod``.
    """
    quals = [q for q, _ in iter_functions(_NOT_OVERLOAD, "<synthetic>")]
    assert quals == ["C.m"], (
        f"a non-overload decorator was excluded from measurement: {quals}")
