"""Guard: the POSIX class table has ONE owner, below both its readers (5B.1).

``core/locale_service.py`` used to reach UP into ``expansion/glob.py`` for the
ASCII class table, through two function-body imports of a PRIVATE name:

    from ..expansion.glob import _POSIX_CLASSES     # locale_service.py:577, :592

Deferring an import hides a layering inversion; it does not fix one. ``psh.core``
is a near-leaf and may not depend on the expansion machinery, and the deferral
was the only thing keeping the cycle from being an import-time error. Remediation
5B.1 moved the data to ``psh/utils/posix_classes.py`` — a true leaf, and one of
the three packages ``core`` may import at MODULE level — so both readers now
import downward.

These cells hold the move honest:

* the table's CONTENT is byte-identical to the pre-move values (the move was a
  relocation, not a rewrite — glob/case-range matching semantics are untouched);
* the pathname variant still differs from the base table in exactly ``punct``;
* the private cross-layer import is GONE and stays gone;
* ``locale_service`` reaches the table WITHOUT any deferred import.

The reference values below are literals on purpose. Deriving them from the
module under test would make this a tautology — it would pass just as happily if
someone rewrote every range.
"""

import ast
import pathlib

from psh.expansion.glob import _POSIX_CLASSES_PATHNAME
from psh.utils.posix_classes import POSIX_CLASSES

ROOT = pathlib.Path(__file__).resolve().parents[3]

#: The table exactly as it stood in expansion/glob.py before the 5B.1 move
#: (v0.774.0, glob.py:18-32). Independent transcription — NOT derived from the
#: module under test.
TABLE_AT_v0_774_0 = {
    'alpha': 'a-zA-Z',
    'digit': '0-9',
    'alnum': 'a-zA-Z0-9',
    'upper': 'A-Z',
    'lower': 'a-z',
    'xdigit': '0-9A-Fa-f',
    'blank': ' \t',
    'space': ' \t\n\r\x0b\x0c',
    'punct': ':-@!-/[-`{-~',
    'graph': '"-~!',
    'print': ' -~',
    'cntrl': '\x00-\x1f\x7f',
}


def test_moved_table_is_byte_identical():
    """The move relocated the table; it did not touch a single range."""
    assert POSIX_CLASSES == TABLE_AT_v0_774_0
    # Key-by-key, so a failure names the class that drifted.
    for name, ranges in TABLE_AT_v0_774_0.items():
        assert POSIX_CLASSES[name] == ranges, f"class [{name}:] drifted"


def test_pathname_variant_differs_only_in_punct():
    """The slash-free variant drops 0x2f from punct and changes nothing else —
    a pathname component can never contain '/', so the matched set is equal."""
    differing = {k for k in POSIX_CLASSES
                 if POSIX_CLASSES[k] != _POSIX_CLASSES_PATHNAME[k]}
    assert differing == {'punct'}
    assert POSIX_CLASSES['punct'] == ':-@!-/[-`{-~'
    assert _POSIX_CLASSES_PATHNAME['punct'] == ':-@!-.[-`{-~'
    assert set(_POSIX_CLASSES_PATHNAME) == set(POSIX_CLASSES)


def test_core_no_longer_imports_the_table_from_expansion():
    """The cross-layer private import is gone — at ANY nesting depth, so a
    reader cannot restore it by burying it deeper in a function body."""
    src = (ROOT / "psh/core/locale_service.py").read_text()
    assert "from ..expansion.glob import" not in src
    assert "_POSIX_CLASSES" not in src, (
        "locale_service references the old private table name; the table now "
        "lives in psh/utils/posix_classes.py as POSIX_CLASSES")


def test_locale_service_reaches_the_table_without_a_deferred_import():
    """The table import is at MODULE level, not inside a function.

    The point of the move was to make the dependency legal, not to relocate the
    same deferral. Walks the AST rather than grepping, so an import nested in a
    helper is still caught.
    """
    tree = ast.parse((ROOT / "psh/core/locale_service.py").read_text())
    module_level: list = []
    deferred: list = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.depth = 0

        def visit_FunctionDef(self, node):
            self.depth += 1
            self.generic_visit(node)
            self.depth -= 1

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ImportFrom(self, node):
            if node.module and "posix_classes" in node.module:
                (deferred if self.depth else module_level).append(node.lineno)
            self.generic_visit(node)

    V().visit(tree)
    assert module_level, "locale_service must import POSIX_CLASSES at module level"
    assert not deferred, (
        f"POSIX_CLASSES imported inside a function body at line(s) {deferred} — "
        "the move exists to remove that deferral, not to relocate it")


def test_the_table_module_is_a_true_leaf():
    """psh/utils/posix_classes.py imports NOTHING — from psh or anywhere.

    It is imported by both psh.core and psh.expansion; any import it grows
    becomes a dependency of both, which is how a shared data module turns back
    into a layering problem.
    """
    tree = ast.parse((ROOT / "psh/utils/posix_classes.py").read_text())
    imports = [ast.unparse(n) for n in ast.walk(tree)
               if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert imports == [], f"the table module must stay dependency-free: {imports}"


def test_the_utils_package_init_stays_inside_psh_utils():
    """The PACKAGE the table lives in must not drag psh code into psh.core.

    Importing ``psh.utils.posix_classes`` executes ``psh/utils/__init__.py``
    first, so that file sits on the ``core -> utils`` path even though nothing
    names it. Its eager imports are intra-package today (``.ast_debug``,
    ``.file_tests``, ``.heredoc_detection``, ``.signal_utils``). The moment one
    reaches OUTSIDE ``psh.utils``, ``psh.core`` acquires that dependency
    transitively and the cycle this move killed returns through the side door —
    while the leaf module itself still looks innocent.
    """
    tree = ast.parse((ROOT / "psh/utils/__init__.py").read_text())
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level == 0:
                if mod.startswith("psh.") and not mod.startswith("psh.utils"):
                    offenders.append(ast.unparse(node))
            elif node.level >= 2:
                # `from ..core import x` climbs out of psh.utils
                offenders.append(ast.unparse(node))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("psh.") and \
                        not a.name.startswith("psh.utils"):
                    offenders.append(ast.unparse(node))
    assert not offenders, (
        "psh/utils/__init__.py eagerly imports outside psh.utils, so importing "
        "the POSIX table now drags that dependency into psh.core: "
        f"{offenders}")
