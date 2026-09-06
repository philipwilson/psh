"""Ratchet: no bash-version literal used as a PREDICATE outside the policy.

Improvement Program 2026-09, standing rules D5 and D12. Version drift must be
ONE named failure (the oracle preflight and its in-suite twin), and a
version-sensitive row is classified by the policy API — never by test code
that re-derives the oracle's version and branches on a literal. Before this
guard, ``test_subscript_keying_conformance.py`` re-parsed
``resolve_bash().version`` with its own regex, compared the tuple against a
private ``(5, 2, 24)`` constant, and fed that into ``skipif`` — a second
implementation of the rule that ``tests/harness/oracle_policy.py`` owns.

Flagged, in every ``.py`` under ``tests/``, ``psh/`` and ``tools/``:

* ``version-literal-compare`` — a string literal shaped like a version
  (``"5.3"``, ``"5.2.24"``) as a direct operand of a comparison whose other
  operand names a bash/oracle/version source, and that is not itself a bare
  ``assert`` (an assertion states an EXPECTATION; a comparison in an
  ``if``/``skipif``/module constant is a classifier). A printf pin comparing
  ``"1234.5"`` against captured output is not a version predicate;
* ``version-literal-in-predicate`` — such a literal anywhere inside an
  ``if``/``elif``/``while``/conditional-expression test or a
  ``skipif(...)``/``skip(...)`` argument that names a version source
  (``oracle.version.startswith("5.2")`` and friends);
* ``version-tuple-compare`` — an int tuple ``(5, 2, 24)`` as a direct
  comparison operand against a bash/oracle/version source (``fd in (1, 2)``
  is an fd test; ``sys.version_info`` comparisons are Python's own version
  and are exempt);
* ``version-tuple-constant`` — an int tuple assigned to a ``*VERSION*`` name
  (the private constant the old offender compared against);
* ``oracle-version-reparsed`` — ``<oracle>.version`` (``resolve_bash().version``,
  ``oracle.version``, or a local name assigned from one — aliases are
  tracked) handed to a parser (``re.match``, ``split``, ``int``,
  ``parse_version``, ...) or a string test (``startswith``, ...). Rendering
  it in an f-string or a message is fine; deriving a verdict from it is not.

WHITELISTED forms (the D5 classifiers): a version literal that is the direct
argument of ``oracle_min(...)`` — the ``@pytest.mark.oracle_min("5.3")``
marker — or of ``oracle_at_least(...)``, the policy primitive the marker and
the golden ``min_bash: "5.3"`` key (YAML, never seen by this AST walk) are
built on. Whitelisted FILES: ``tests/harness/oracle_policy.py`` (owns the
rule) and ``tools/verify_gate_attestation.py`` (its stdlib-only duplicate,
pinned equal by ``test_gate_attestation.py``), plus this guard.
"""
import ast
import os
import re
import textwrap

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
SCAN_ROOTS = ("tests", "psh", "tools")
WHITELISTED_FILES = frozenset({
    "tests/harness/oracle_policy.py",
    "tools/verify_gate_attestation.py",
})

VERSION_LITERAL = re.compile(r"^\d+\.\d+(\.\d+)?$")
#: The D5 policy calls whose direct string argument is the row's version.
ALLOWED_CALLS = frozenset({"oracle_min", "oracle_at_least"})
_PREDICATE_CALLS = frozenset({"skipif", "skip"})
_PARSER_CALLS = frozenset({
    "match", "search", "fullmatch", "findall", "finditer", "split", "rsplit",
    "partition", "rpartition", "int", "float", "tuple", "parse", "parse_version",
    "Version", "LooseVersion", "StrictVersion", "startswith", "endswith",
})
_STRING_TESTS = frozenset({
    "split", "rsplit", "partition", "rpartition", "startswith", "endswith",
    "strip", "lstrip", "rstrip", "replace",
})
_ORACLE_BASE = re.compile(r"(?i)bash|oracle")
_VERSION_NAME = re.compile(r"(?i)version")
#: The other side of a comparison must name a version source for a literal
#: or tuple to count as a version predicate (keeps fd tuples, printf floats
#: and exit-code sets out of the ratchet).
_VERSION_SOURCE = re.compile(r"(?i)bash|oracle|version")


def _is_version_literal(node):
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and bool(VERSION_LITERAL.match(node.value)))


def _is_int_tuple(node):
    return (isinstance(node, ast.Tuple) and 2 <= len(node.elts) <= 3
            and all(isinstance(e, ast.Constant) and isinstance(e.value, int)
                    and not isinstance(e.value, bool) for e in node.elts))


def _callee_name(call):
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return ""


def _is_oracle_version_attr(node):
    """``<something mentioning bash/oracle>.version``."""
    return (isinstance(node, ast.Attribute) and node.attr == "version"
            and bool(_ORACLE_BASE.search(ast.unparse(node.value))))


def find_version_predicates(src):
    """Return ``[(lineno, kind, detail)]`` for Python source ``src``."""
    tree = ast.parse(src)
    offenses = []
    allowed_literals = set()      # id() of literals that are ALLOWED_CALLS args
    assert_tests = set()          # id() of Compare nodes that are bare asserts
    version_aliases = set()       # names assigned from <oracle>.version

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _callee_name(node) in ALLOWED_CALLS:
            for arg in node.args:
                if _is_version_literal(arg):
                    allowed_literals.add(id(arg))
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            assert_tests.add(id(node.test))
        if isinstance(node, ast.Assign) and _is_oracle_version_attr(node.value):
            version_aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))

    def is_version_source(expr):
        """The expression is (or contains) a bash/oracle/version name or an
        alias of ``<oracle>.version`` — and is not Python's ``version_info``."""
        text = ast.unparse(expr)
        if "version_info" in text:
            return False
        return bool(_VERSION_SOURCE.search(text)) or any(
            isinstance(n, ast.Name) and n.id in version_aliases for n in ast.walk(expr))

    def is_oracle_version_expr(expr):
        return _is_oracle_version_attr(expr) or (
            isinstance(expr, ast.Name) and expr.id in version_aliases)

    def literals_in(subtree):
        if not is_version_source(subtree):
            return
        for sub in ast.walk(subtree):
            if _is_version_literal(sub) and id(sub) not in allowed_literals:
                yield sub

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and id(node) not in assert_tests:
            operands = [node.left, *node.comparators]
            for operand in operands:
                against_version = any(is_version_source(o) for o in operands
                                      if o is not operand)
                if (_is_version_literal(operand) and id(operand) not in allowed_literals
                        and against_version):
                    offenses.append((operand.lineno, "version-literal-compare",
                                     operand.value))
                if _is_int_tuple(operand) and against_version:
                    offenses.append((operand.lineno, "version-tuple-compare",
                                     ast.unparse(operand)))
        if isinstance(node, (ast.If, ast.IfExp, ast.While)):
            for lit in literals_in(node.test):
                offenses.append((lit.lineno, "version-literal-in-predicate", lit.value))
        if isinstance(node, ast.Call) and _callee_name(node) in _PREDICATE_CALLS:
            for arg in [*node.args, *(kw.value for kw in node.keywords if kw.arg != "reason")]:
                for lit in literals_in(arg):
                    offenses.append((lit.lineno, "version-literal-in-predicate", lit.value))
        if isinstance(node, ast.Assign) and _is_int_tuple(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name) and _VERSION_NAME.search(target.id):
                    offenses.append((node.lineno, "version-tuple-constant",
                                     f"{target.id} = {ast.unparse(node.value)}"))
        if isinstance(node, ast.Call):
            name = _callee_name(node)
            if name in _PARSER_CALLS and any(
                    is_oracle_version_expr(a) for a in node.args):
                offenses.append((node.lineno, "oracle-version-reparsed",
                                 ast.unparse(node)))
            elif (isinstance(node.func, ast.Attribute) and name in _STRING_TESTS
                    and is_oracle_version_expr(node.func.value)):
                offenses.append((node.lineno, "oracle-version-reparsed",
                                 ast.unparse(node)))
    return offenses


def iter_scanned_files():
    for root in SCAN_ROOTS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(REPO_ROOT, root)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in sorted(filenames):
                if fn.endswith(".py"):
                    yield os.path.join(dirpath, fn)


def test_no_version_literal_predicates_in_tree():
    problems = []
    for path in iter_scanned_files():
        rel = os.path.relpath(path, REPO_ROOT)
        if rel in WHITELISTED_FILES or os.path.abspath(path) == os.path.abspath(__file__):
            continue
        with open(path, encoding="utf-8") as f:
            src = f.read()
        for lineno, kind, detail in find_version_predicates(src):
            problems.append(f"{rel}:{lineno}: {kind}: {detail!r}")
    assert not problems, (
        "bash-version predicate outside tests/harness/oracle_policy.py — "
        "classify the row with @pytest.mark.oracle_min('X.Y') (pytest), "
        "min_bash: \"X.Y\" (golden) or oracle_at_least('X.Y'), never a "
        "version literal, tuple or re-parse of the oracle version:\n  "
        + "\n  ".join(problems))


def test_whitelisted_files_exist():
    for rel in WHITELISTED_FILES:
        assert os.path.isfile(os.path.join(REPO_ROOT, rel)), rel


def test_scan_scope_reaches_the_old_offender_and_the_harness():
    rels = {os.path.relpath(p, REPO_ROOT) for p in iter_scanned_files()}
    for probe in ("tests/conformance/bash/test_subscript_keying_conformance.py",
                  "tests/harness/oracle_policy.py",
                  "tests/behavioral/test_golden_behavior.py",
                  "psh/shell.py",
                  "tools/verify_gate_attestation.py"):
        assert probe in rels, f"scanner scope lost {probe}"


# --- guard-the-guard: synthetic offenders fire, blessed forms do not ---------

_OFFENDER = textwrap.dedent('''
    import re
    import pytest
    from shell_oracle import resolve_bash

    def _oracle_tuple():
        m = re.match(r"(\\d+)\\.(\\d+)\\.(\\d+)", resolve_bash().version)   # reparsed
        return tuple(int(g) for g in m.groups())

    _NEEDS_VERSION = (5, 2, 24)                                       # tuple constant
    _OLD = _oracle_tuple() < (5, 2, 24)                               # tuple compare
    oracle = resolve_bash()
    if oracle.version.startswith("5.2"):                              # reparsed + predicate
        pass
    if resolve_bash().version < "5.3":                                # literal compare
        pass
    label = "new" if oracle.version >= "5.3" else "old"               # literal compare
    parts = oracle.version.split(".")                                 # reparsed
    v = resolve_bash().version
    if v.startswith("5.2"):                                           # alias: reparsed + predicate
        pass
    _parsed = tuple(int(x) for x in v.split("."))                     # alias: reparsed

    @pytest.mark.skipif(_OLD, reason="older than 5.2.24")
    def test_a():
        pass

    @pytest.mark.skipif("5.2" in oracle.version, reason="x")          # predicate + compare
    def test_b():
        pass
''')


def test_synthetic_offender_is_flagged_on_every_shape():
    kinds = {k for _, k, _ in find_version_predicates(_OFFENDER)}
    assert kinds == {
        "oracle-version-reparsed",
        "version-tuple-constant",
        "version-tuple-compare",
        "version-literal-in-predicate",
        "version-literal-compare",
    }


def test_synthetic_offender_module_on_disk_is_flagged(tmp_path):
    """The tree walk, end to end: a temp module with the old offender's exact
    shape is reported with its line numbers."""
    offender = tmp_path / "test_offender.py"
    offender.write_text(_OFFENDER, encoding="utf-8")
    hits = find_version_predicates(offender.read_text(encoding="utf-8"))
    lines = {lineno for lineno, _, _ in hits}
    assert {7, 10, 11, 13, 15, 17, 18, 20, 22, 28} <= lines, sorted(hits)


def test_reason_keyword_of_skipif_is_not_a_predicate():
    src = 'import pytest\n@pytest.mark.skipif(False, reason="needs 5.2.24")\ndef test_x(): pass\n'
    assert find_version_predicates(src) == []


def test_blessed_forms_pass():
    src = textwrap.dedent('''
        import sys
        import pytest
        from oracle_policy import oracle_at_least, oracle_feature, oracle_summary, parse_version
        from shell_oracle import resolve_bash

        @pytest.mark.oracle_min("5.3")                       # the D5 marker
        def test_a():
            assert oracle_at_least("5.3")

        @pytest.mark.skipif(not oracle_at_least("5.2.24"), reason="tilde in subscripts is 5.2.24+")
        def test_b():
            pass

        @pytest.mark.skipif(oracle_feature("x87_long_double"), reason="probed, not a literal")
        def test_c():
            pass

        def test_d():
            assert parse_version("5.3.15") == (5, 3, 15)     # an expectation, not a classifier
            assert resolve_bash().version and resolve_bash().version[0].isdigit()
            line = f"oracle: {resolve_bash().path} {resolve_bash().version}"
            assert line == oracle_summary()
            if sys.version_info >= (3, 12):                  # Python's own version
                pass
            fd = 1
            if fd in (1, 2):                                 # an fd set, not a version
                pass
            out = "1234.5"
            if "1234.5" in out or out == "1.5":              # a printf float, not a version
                pass
    ''')
    assert find_version_predicates(src) == []


@pytest.mark.parametrize("value, is_version", [
    ("5.3", True), ("5.2.24", True), ("10.0.1", True),
    ("5", False), ("5.3.15(1)-release", False), ("v5.3", False), ("1.2.3.4", False),
])
def test_version_literal_shape(value, is_version):
    assert bool(VERSION_LITERAL.match(value)) is is_version
