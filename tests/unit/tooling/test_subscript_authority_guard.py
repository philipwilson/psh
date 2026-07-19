"""Drift-locks for the ONE subscript authority (campaign W2).

r21's signature finding was six inconsistent keying implementations of one
feature. These guards keep the consolidation from regrowing:

1. The retired keying helpers stay deleted (no ``expand_assoc_key``,
   ``expand_array_index``, ``_eval_subscript_fatal``, arith ``_parse_subscript``,
   or eager parsed-subscript fields).
2. The service's interpretation entry points are called only from the
   sanctioned consumer set — a new caller is a reviewed edit here, and a new
   keying implementation OUTSIDE the service shows up as a retired-pattern hit.

The scanners are self-tested against synthetic offenders so they cannot rot
into no-ops.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"

# Symbols the W2 consolidation deleted; any reappearance (definition or call)
# in psh/ is a regression toward the six-implementations state.
RETIRED = (
    'expand_assoc_key',
    'expand_array_index',
    '_eval_subscript_fatal',
)


def _psh_sources():
    return [p for p in PSH.rglob('*.py') if '__pycache__' not in p.parts]


def _find_retired(text: str):
    hits = []
    for name in RETIRED:
        # Word-boundary match so e.g. _expand_array_indices (a different,
        # living symbol) does not count.
        if re.search(rf'\b{name}\b', text):
            hits.append(name)
    return hits


def test_retired_keying_symbols_absent():
    offenders = {}
    for path in _psh_sources():
        hits = _find_retired(path.read_text())
        if hits:
            offenders[str(path.relative_to(ROOT))] = hits
    assert not offenders, (
        "Retired subscript-keying symbols reappeared (one authority — "
        f"psh/expansion/subscript.py): {offenders}")


def test_guard_detects_retired_symbol():
    assert _find_retired("x = self.expand_assoc_key(idx)") == ['expand_assoc_key']
    assert _find_retired("y = self._expand_array_indices(s)") == []


def test_arith_parser_has_no_eager_subscript():
    """The arith parser never parses a subscript as arithmetic at parse time:
    no ``_parse_subscript`` and no parsed-node subscript fields — subscripts
    are verbatim SUBSCRIPT tokens interpreted at evaluation."""
    parser_src = (PSH / 'expansion/arithmetic/parser.py').read_text()
    nodes_src = (PSH / 'expansion/arithmetic/nodes.py').read_text()
    assert '_parse_subscript' not in parser_src
    assert 'index: ArithNode' not in nodes_src
    assert 'subscript: Optional[ArithNode]' not in nodes_src
    assert 'index_text: str' in nodes_src


SANCTIONED_ASSOC_CALLERS = {
    'psh/expansion/subscript.py',       # the definition + evaluate()
    'psh/expansion/arrays.py',          # read + set_var_or_array_element
    'psh/expansion/variable.py',        # ${h[k]} string path
    'psh/expansion/operators.py',       # +/-/? is-set
    'psh/expansion/arithmetic/evaluator.py',  # arith lvalue/read (expand_dollar=False)
    'psh/builtins/test_command.py',     # test -v / [[ -v (assoc arm)
    'psh/executor/array.py',            # element assignment
}


def _callers_of(pattern: str):
    callers = set()
    for path in _psh_sources():
        if re.search(pattern, path.read_text()):
            callers.add(str(path.relative_to(ROOT)))
    return callers


def test_associative_key_called_only_from_sanctioned_set():
    callers = _callers_of(r'\.associative_key\(|def associative_key\(')
    assert callers == SANCTIONED_ASSOC_CALLERS, (
        f"associative_key caller set changed: added "
        f"{callers - SANCTIONED_ASSOC_CALLERS}, removed "
        f"{SANCTIONED_ASSOC_CALLERS - callers}. New keying consumers are a "
        "reviewed edit here.")


def test_indexed_index_called_only_from_sanctioned_set():
    callers = _callers_of(r'\.indexed_index\(|def indexed_index\(')
    expected = {
        'psh/expansion/subscript.py',
        'psh/expansion/arrays.py',
        'psh/executor/array.py',
    }
    assert callers == expected, (
        f"indexed_index caller set changed: added {callers - expected}, "
        f"removed {expected - callers}.")


def test_evaluate_dispatch_called_only_from_sanctioned_set():
    """``evaluate(raw, kind, use)`` is the use-aware dispatch: the surfaces
    with a bash EMPTY-subscript policy (``test -v`` silently-unset, ``unset``
    silent no-op) route through it, so ``SubscriptUse`` genuinely drives
    behavior (empty indexed subscript -> ``None``/no-target)."""
    callers = _callers_of(r'subscript\.evaluate\(')
    expected = {
        'psh/builtins/test_command.py',   # -v: empty -> silently unset
        'psh/builtins/environment.py',    # unset: empty -> silent no-op
    }
    assert callers == expected, (
        f"SubscriptEvaluator.evaluate caller set changed: added "
        f"{callers - expected}, removed {expected - callers}.")


def test_guard_detects_new_caller():
    assert re.search(r'\.associative_key\(',
                     "key = mgr.subscript.associative_key(raw)")


def test_declare_p_and_transforms_share_one_key_renderer():
    """declare -p, @A and @K render assoc keys through THE one rule
    (utils/escapes.format_assoc_key) — bash renders identically on all
    three surfaces."""
    declare_fmt = (PSH / 'builtins/declare_format.py').read_text()
    arrays = (PSH / 'expansion/arrays.py').read_text()
    assert 'format_assoc_key' in declare_fmt
    # Both @A and @K construction sites route keys through the renderer:
    assert arrays.count('format_assoc_key(') >= 2
    assert 'def format_assoc_key' in (PSH / 'utils/escapes.py').read_text()
