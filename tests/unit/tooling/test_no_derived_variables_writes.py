"""Meta-test: no writes to the derived ``.variables`` dict in tests or docs.

``ShellState.variables`` is a property that rebuilds a plain dict from the
scope manager on every read. Assigning to it (``shell.state.variables[k] = v``)
or deleting from it (``del shell.state.variables[k]``) mutates a throwaway copy
and silently changes nothing — a dangerous false setup that finding C5 of the
2026-07-06 tests/docs appraisal called out in two fixtures.

Reads are fine (``os.path.join(shell.state.variables['PWD'], ...)`` returns the
correct current value), so this guard is written with an AST walk that flags
only *assignment/augmented-assignment/del targets* whose subscript base ends in
``.variables`` — never a read. It scans every test module plus the Python code
fences embedded in the developer docs, so the guidance and the fixtures stay
honest together.

To set a variable in a test, use ``shell.set_variable(name, value)`` (or the
scope-manager API); to remove one, use ``scope_manager.unset_variable(name)``.
"""

import ast
import os
import re

HERE = os.path.dirname(__file__)
TESTS_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
REPO_ROOT = os.path.abspath(os.path.join(TESTS_ROOT, '..'))
DOCS_ROOT = os.path.join(REPO_ROOT, 'docs')

_PY_FENCE = re.compile(r'```(?:python|py)\n(.*?)```', re.DOTALL)


def _is_variables_subscript(target):
    """True if *target* is ``<expr>.variables[...]`` (a subscript whose base is
    an attribute access named ``variables``)."""
    return (isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Attribute)
            and target.value.attr == 'variables')


def _writes_to_variables(src):
    """Return sorted line numbers in *src* that write to a ``.variables`` dict.

    Catches ``x.variables[k] = v``, ``x.variables[k] += v`` and
    ``del x.variables[k]``. Never catches a read (a read is a Load-context
    subscript, not an assignment/del target)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # Partial/illustrative snippet — cannot be analyzed reliably.
        return []
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = node.targets
        else:
            continue
        for t in targets:
            if _is_variables_subscript(t):
                hits.append(node.lineno)
    return sorted(hits)


def _python_test_files():
    for root, _dirs, names in os.walk(TESTS_ROOT):
        for name in names:
            if name.startswith('test_') and name.endswith('.py'):
                yield os.path.join(root, name)


def _doc_files():
    if not os.path.isdir(DOCS_ROOT):
        return
    for root, _dirs, names in os.walk(DOCS_ROOT):
        for name in names:
            if name.endswith('.md'):
                yield os.path.join(root, name)


# This meta-test and the fixture-semantics test discuss the banned pattern in
# prose/sample strings; AST analysis never flags a string literal, so no file
# needs excluding — but keep the derived-write examples inside string samples,
# not real assignments.


def test_no_variables_writes_in_tests():
    violations = {}
    for path in _python_test_files():
        with open(path) as f:
            lines = _writes_to_variables(f.read())
        if lines:
            violations[os.path.relpath(path, REPO_ROOT)] = lines
    assert not violations, (
        "Writes to the derived shell.state.variables dict in tests (finding "
        f"C5): {violations}. That dict is rebuilt on every read, so the write "
        "is a silent no-op. Use shell.set_variable(name, value) to set or "
        "scope_manager.unset_variable(name) to remove.")


def test_no_variables_writes_in_docs():
    violations = {}
    for path in _doc_files():
        with open(path) as f:
            text = f.read()
        hits = []
        for m in _PY_FENCE.finditer(text):
            hits.extend(_writes_to_variables(m.group(1)))
        if hits:
            violations[os.path.relpath(path, REPO_ROOT)] = sorted(hits)
    assert not violations, (
        "Documentation code samples write to the derived shell.state.variables "
        f"dict (finding C5): {violations}. Use shell.set_variable(...) in "
        "examples so readers copy a write that actually works.")


def test_guard_flags_writes_and_clears_reads():
    """Self-test: writes/del/augmented are flagged; a read is not."""
    assert _writes_to_variables("shell.state.variables['x'] = 1") == [1]
    assert _writes_to_variables("del shell.state.variables['x']") == [1]
    assert _writes_to_variables("shell.state.variables['x'] += 1") == [1]
    # Reads and comparisons are allowed.
    assert _writes_to_variables("y = shell.state.variables['x']") == []
    assert _writes_to_variables("assert shell.state.variables['x'] == 1") == []
    assert _writes_to_variables("os.path.join(s.state.variables['PWD'], 'f')") == []
