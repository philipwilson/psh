"""Shared AST analysis for the "does this test genuinely assert" guards.

Two meta-guards need the same notion of "a ``test_*`` function that really
exercises a claim rather than running an assertion-free probe":

* ``tests/conformance/test_claims_have_tests.py`` — every user-guide "Full
  support" row must map to a conformance test that *asserts*.
* ``tests/unit/tooling/test_conformance_probes_assert.py`` — no conformance
  ``test_*`` may call ``check_behavior`` without asserting on the result.

These primitives used to be verbatim twins in both files, with a docstring in
the second admitting it "mirrors" the first "so the two guards agree" — i.e.
the agreement was maintained by hand. That is the project's own divergent-twin
failure mode inside its guardrails (reappraisal-#19 tests-infra M5). This module
is the single source both import, so the two guards cannot silently disagree on
what "genuinely exercises a claim" means.

A test asserts if it contains a bare ``assert`` or calls an *asserting helper*:
one of the ``ConformanceTest`` ``assert_*`` methods, or — to a fixpoint — any
module-level ``def`` that itself asserts or calls a known asserting helper.
"""

import ast

# Assertion helpers provided by the ConformanceTest base class — a test that
# calls one of these is asserting even without a bare ``assert``.
CONFORMANCE_ASSERT_HELPERS = frozenset({
    'assert_identical_behavior', 'assert_documented_difference',
    'assert_psh_extension',
})


def called_names(node):
    """Yield the simple name of every function/method called within *node*."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute):
                yield f.attr
            elif isinstance(f, ast.Name):
                yield f.id


def has_bare_assert(node):
    """True if *node*'s subtree contains an ``assert`` statement."""
    return any(isinstance(n, ast.Assert) for n in ast.walk(node))


def asserting_helper_names(tree):
    """Names of helpers in *tree* that themselves assert (to a fixpoint).

    A conformance file may wrap its comparison in a local helper (e.g.
    ``_both_identical`` in the reappraisal pins, or ``_assert_same_stdout_and_status``
    in the readonly file) that runs both shells and asserts. Any def whose body
    contains a bare ``assert`` counts, and — to a fixpoint — so does any def that
    calls an already-known asserting helper. A test that merely *calls* such a
    helper is genuinely exercising a claim.
    """
    names = set(CONFORMANCE_ASSERT_HELPERS)
    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    changed = True
    while changed:
        changed = False
        for fn in funcs:
            if fn.name in names:
                continue
            if has_bare_assert(fn) or any(c in names for c in called_names(fn)):
                names.add(fn.name)
                changed = True
    return names
