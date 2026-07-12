"""Meta-test: no assertion-free ``check_behavior`` probes in the conformance tree.

``ConformanceTest.check_behavior`` runs a command in psh and bash and returns
the comparison WITHOUT asserting anything (it exists for interactive
investigation). A ``test_*`` function that calls it but never asserts on the
result is counted as a passing conformance test while proving nothing — the
exact "probe, not assertion" trust gap the 2026-07-06 tests/docs appraisal
(finding C2) called out.

This test makes that gap self-correcting: every ``test_*`` function under
``tests/conformance/`` that calls ``check_behavior`` must also assert — either
directly (a bare ``assert``) or by delegating to a helper that asserts (e.g.
the ``_assert_same_stdout_and_status`` pattern in the readonly conformance
file). A bare investigative probe must therefore be converted to an assertion,
an ``assert_*`` conformance helper, or moved out of the conformance tree.

The "does this test genuinely assert" primitives come from the shared
``tests/conformance/_assert_analysis`` module — the same one
``tests/conformance/test_claims_have_tests.py`` uses — so the two guards agree
on what "genuinely exercises a claim" means BY CONSTRUCTION rather than by a
hand-maintained mirror (reappraisal-#19 tests-infra M5).
"""

import ast
import os
import sys

import pytest

CONF_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'conformance')

sys.path.insert(0, os.path.abspath(CONF_DIR))
from _assert_analysis import (  # noqa: E402
    asserting_helper_names,
    called_names,
    has_bare_assert,
)


def _conformance_test_files():
    """Every ``test_*.py`` under the conformance tree, except the meta-tests
    (which reference ``check_behavior`` as data, not as real probes)."""
    skip = {'test_claims_have_tests.py'}
    files = []
    for root, _dirs, names in os.walk(CONF_DIR):
        for name in names:
            if name.startswith('test_') and name.endswith('.py') \
                    and name not in skip:
                files.append(os.path.join(root, name))
    return sorted(files)


def _bare_probe_tests_in_text(src):
    """Names of ``test_*`` functions in *src* that call ``check_behavior`` but
    neither assert directly nor delegate to an asserting helper."""
    tree = ast.parse(src)
    helpers = asserting_helper_names(tree)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith('test'):
            called = list(called_names(node))
            if 'check_behavior' not in called:
                continue
            if has_bare_assert(node) or any(c in helpers for c in called):
                continue
            offenders.append(node.name)
    return offenders


def test_no_assertion_free_conformance_probes():
    """No conformance ``test_*`` may call check_behavior without asserting."""
    violations = {}
    for path in _conformance_test_files():
        with open(path) as f:
            offenders = _bare_probe_tests_in_text(f.read())
        if offenders:
            violations[os.path.relpath(path, CONF_DIR)] = offenders
    assert not violations, (
        "Assertion-free check_behavior probes in the conformance tree "
        f"(finding C2): {violations}. Each listed test calls check_behavior "
        "but never asserts on the result — so it is counted as passing "
        "conformance while proving nothing. Convert it to "
        "assert_identical_behavior / assert_documented_difference, add a bare "
        "assert on the returned result, or move it out of tests/conformance/.")


def test_guard_detects_a_bare_probe():
    """Self-test: the detector must flag a bare probe and clear a real one."""
    bare = (
        "class TestX:\n"
        "    def test_probe(self):\n"
        "        self.check_behavior('echo hi')\n"
    )
    asserted = (
        "class TestX:\n"
        "    def test_real(self):\n"
        "        r = self.check_behavior('echo hi')\n"
        "        assert r.psh_result.exit_code == 0\n"
    )
    via_helper = (
        "def _both(cmd):\n"
        "    assert cmd\n"
        "class TestX:\n"
        "    def test_delegated(self):\n"
        "        self._both(self.check_behavior('echo hi'))\n"
    )
    assert _bare_probe_tests_in_text(bare) == ['test_probe']
    assert _bare_probe_tests_in_text(asserted) == []
    # A helper that asserts clears the caller even without a direct assert.
    assert _bare_probe_tests_in_text(via_helper) == []


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
