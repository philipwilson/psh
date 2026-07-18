"""Static guards for the S2 heredoc transaction (boundary campaign).

Two ratchets protect the representation and its chokepoints:

1. **No string-keyed heredoc plumbing remains.** The retired surface —
   ``heredoc_key`` (token/AST field and map keys), the collector's
   text-derived ``f"heredoc_{n}_{delim}"`` keys, the accumulator's private
   ``_close_heredocs_matching`` close policy, and the combinator's
   ``HeredocProcessor``/``populate_heredocs`` attachment walk — must not
   reappear anywhere in ``psh/``.
2. **One close decision.** ``heredoc_terminator_matches`` has exactly ONE
   production call site: ``PendingHeredocQueue.feed_line`` in
   ``psh/utils/heredoc_detection.py``. Every body-gathering layer (lexer
   collector, completeness oracle, accumulator, line-continuation
   preprocessor) must route its terminator decision through the queue.

Both guards are self-tested against synthetic offenders.
"""

import ast
from pathlib import Path

PSH_ROOT = Path(__file__).resolve().parents[3] / 'psh'

# Retired identifiers/patterns (comments and docstrings included on purpose:
# prose teaching a retired representation is drift too).
_FORBIDDEN = (
    'heredoc_key',
    '_close_heredocs_matching',
    'f"heredoc_',
    "f'heredoc_",
    'HeredocProcessor',
    'populate_heredocs',
    'open_heredoc_delimiters',
)

_CHOKEPOINT_FILE = 'utils/heredoc_detection.py'
_CHOKEPOINT_FUNC = 'feed_line'


def _scan_text(text: str):
    """Forbidden retired-surface patterns present in *text*."""
    return [pat for pat in _FORBIDDEN if pat in text]


def _terminator_call_sites(text: str, filename: str):
    """(filename, enclosing-function, lineno) for every CALL of
    heredoc_terminator_matches in *text* (definitions excluded)."""
    tree = ast.parse(text, filename=filename)
    sites = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.stack = ['<module>']

        def visit_FunctionDef(self, node):
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            func = node.func
            name = getattr(func, 'id', None) or getattr(func, 'attr', None)
            if name == 'heredoc_terminator_matches':
                sites.append((filename, self.stack[-1], node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    return sites


def _psh_sources():
    return sorted(PSH_ROOT.rglob('*.py'))


class TestNoStringKeyedHeredocSurface:
    def test_production_tree_clean(self):
        offenders = []
        for path in _psh_sources():
            found = _scan_text(path.read_text())
            if found:
                offenders.append((str(path.relative_to(PSH_ROOT)), found))
        assert offenders == [], (
            "retired heredoc surface resurfaced (S2: identity is the ordinal "
            f"heredoc_id; close decisions live in the queue): {offenders}")

    def test_synthetic_offenders_detected(self):
        # The guard actually fires on each retired pattern.
        assert _scan_text('x = redirect.heredoc_key') == ['heredoc_key']
        assert _scan_text('key = f"heredoc_{n}_{delim}"') == ['f"heredoc_']
        assert _scan_text('self._close_heredocs_matching(line)') == \
            ['_close_heredocs_matching']
        assert _scan_text('HeredocProcessor().populate_heredocs(ast, m)') == \
            ['HeredocProcessor', 'populate_heredocs']
        assert _scan_text('open_heredoc_delimiters(buf)') == \
            ['open_heredoc_delimiters']
        assert _scan_text('entry.spec.cooked') == []


class TestOneCloseDecision:
    def test_single_production_caller(self):
        sites = []
        for path in _psh_sources():
            rel = str(path.relative_to(PSH_ROOT))
            sites.extend(_terminator_call_sites(path.read_text(), rel))
        assert sites == [(_CHOKEPOINT_FILE, _CHOKEPOINT_FUNC,
                          sites[0][2] if sites else -1)], (
            "heredoc_terminator_matches must be called ONLY by "
            "PendingHeredocQueue.feed_line (the head-of-queue policy); "
            f"found call sites: {sites}")

    def test_synthetic_second_caller_detected(self):
        synthetic = (
            "def sneaky(line, word):\n"
            "    return heredoc_terminator_matches(line, word, False)\n")
        sites = _terminator_call_sites(synthetic, 'offender.py')
        assert sites == [('offender.py', 'sneaky', 2)]

    def test_definition_not_counted(self):
        definition = (
            "def heredoc_terminator_matches(line, delimiter, strip_tabs):\n"
            "    return line == delimiter\n")
        assert _terminator_call_sites(definition, 'defs.py') == []
