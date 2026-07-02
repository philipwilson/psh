"""Meta-test: user-guide conformance claims map to conformance tests.

Project principle (CLAUDE.md): "If we assert that a feature of psh is
POSIX or bash conformant in the user's guide then we must have a test in
tests/conformance/ which proves it."

This test makes that principle CHECKABLE: every feature row in the
compatibility table of docs/user_guide/17_differences_from_bash.md whose
Notes column says "Full support" (optionally with a parenthetical such as
"Full support (incl. %q)") must have an entry in CLAIM_TESTS below.

Crucially the evidence must be *real*. Each entry names a conformance file
and a marker string, and the marker must appear inside a test function that
genuinely **exercises** the claim — i.e. a ``test_*`` function that makes an
assertion (a bare ``assert`` or a call to one of the ConformanceTest
``assert_*`` helpers, directly or via a local helper that itself asserts).

A marker that only matches a class name, a module-level constant, or an
assert-free investigative probe (``check_behavior`` with no assertion) does
NOT count. That closes the loophole where, e.g., ``disown`` mapped to a class
whose file never ran disown, or ``pushd`` mapped to an assert-free probe.
"""

import ast
import os
import re

import pytest

GUIDE = os.path.join(os.path.dirname(__file__), '..', '..',
                     'docs', 'user_guide', '17_differences_from_bash.md')
CONF_DIR = os.path.dirname(__file__)

# Feature (exactly as in the table's first column) → (conformance file
# relative to tests/conformance/, marker string). The marker must be a
# distinctive substring of a test that exercises the feature *and asserts*.
CLAIM_TESTS = {
    'Command execution': ('posix/test_posix_compliance.py', 'VAR=value echo $VAR'),
    'Pipelines': ('posix/test_posix_compliance.py', 'echo hello | wc -c'),
    'Subshells': ('posix/test_posix_compliance.py', 'x=outer; (x=inner; echo $x); echo $x'),
    'Simple variables': ('posix/test_posix_compliance.py', 'x=value; echo $x; unset x; echo $x'),
    'Arrays': ('bash/test_bash_compatibility.py', 'arr=(a b c); echo ${#arr[@]}'),
    'Associative arrays': ('bash/test_bash_compatibility.py', 'declare -A arr; arr[key]=value; echo ${arr[key]}'),
    'Local variables': ('bash/test_bash_compatibility.py', 'f() { local x=local; echo $x; }'),
    'Arithmetic expansion': ('posix/test_posix_compliance.py', 'echo $((3 * 4))'),
    'Brace expansion': ('bash/test_bash_compatibility.py', 'echo {a,b,c}'),
    'Process substitution': ('bash/test_bash_compatibility.py', 'cat <(echo hello)'),
    'Tilde expansion': ('posix/test_posix_compliance.py', 'echo ~/test'),
    'if/then/else/fi': ('posix/test_posix_compliance.py', 'if false; then echo no; else echo yes; fi'),
    'while/until/do/done': ('posix/test_posix_compliance.py', 'until [ $i -ge 2 ]'),
    'for/do/done': ('posix/test_posix_compliance.py', 'for word in hello world; do echo $word; done'),
    'C-style for loops': ('bash/test_control_eval_conformance.py', 'for ((i=0; i<3; i++)); do echo "i:$i"; done'),
    'case/esac': ('posix/test_posix_compliance.py', 'case abc in a*) echo starts_with_a;; esac'),
    'select': ('bash/test_select_trap_conformance.py', 'select x in alpha beta'),
    'Arithmetic commands (( ))': ('bash/test_bash_compatibility.py', '(( 1 + 1 == 2 ))'),
    'Control structures in pipelines': ('bash/test_control_eval_conformance.py', 'if true; then echo yes; fi | tr a-z A-Z'),
    'Return values': ('posix/test_posix_compliance.py', 'success() { return 0; }; success; echo $?'),
    'wait builtin': ('posix/test_heredoc_fd_jobs_conformance.py', 'sleep 0.1 & wait $!'),
    'disown builtin': ('posix/test_heredoc_fd_jobs_conformance.py', '& disown %1; jobs; echo done'),
    'set -e (errexit)': ('posix/test_errexit_conformance.py', 'set -e; true | false; echo no'),
    'set -u (nounset)': ('bash/test_nounset_operators_conformance.py', 'set -u; echo ${x:-fallback}'),
    'set -x (xtrace)': ('bash/test_set_options_conformance.py', 'set -x; x=5; echo $x'),
    'set -o pipefail': ('posix/test_errexit_conformance.py', 'set -o pipefail; (false | true); echo rc=$?'),
    'set -o noclobber': ('bash/test_user_guide_notes_conformance.py', 'set -o noclobber'),
    'set -o allexport': ('bash/test_export_env_sync_conformance.py', 'set -a; FOO=auto; printenv FOO'),
    'set -o noglob': ('bash/test_array_init_conformance.py', 'set -f; a=(*.txt)'),
    'set -o verbose': ('bash/test_set_options_conformance.py', 'set -v\\necho hi\\necho bye'),
    'Here documents': ('posix/test_heredoc_fd_jobs_conformance.py', 'plain $USER text'),
    'Here strings': ('posix/test_heredoc_fd_jobs_conformance.py', 'here string $((2*3))'),
    'Enhanced test [[ ]]': ('bash/test_bash_compatibility.py', '[[ -f /dev/null ]]'),
    'eval builtin': ('bash/test_control_eval_conformance.py', "eval 'echo evaled'"),
    'getopts builtin': ('posix/test_getopts_conformance.py', 'while getopts "ab:" opt'),
    'printf builtin': ('bash/test_edge_cases.py', 'printf "%q'),
    'pushd/popd/dirs': ('bash/test_bash_compatibility.py', 'pushd /usr >/dev/null; pushd /bin'),
}


# --- Notes-column parsing --------------------------------------------------
# Accept exactly "Full support" and the parenthetical form the guide uses,
# e.g. "Full support (incl. %q)". Prose "full support" claims outside the
# compatibility table are intentionally out of scope (broadening to arbitrary
# prose is too noisy to gate on).
_FULL_SUPPORT_ROW = re.compile(
    r'\|\s*([^|]+?)\s*\|\s*Yes\s*\|\s*Yes\s*\|\s*Full support[^|]*\|')


def _full_support_features():
    text = open(GUIDE).read()
    features = []
    for line in text.splitlines():
        m = _FULL_SUPPORT_ROW.match(line)
        if m:
            features.append(m.group(1).strip())
    return features


# --- Evidence matcher ------------------------------------------------------
# Assertion helpers provided by the ConformanceTest base class.
_CONFORMANCE_ASSERT_HELPERS = frozenset({
    'assert_identical_behavior', 'assert_documented_difference',
    'assert_psh_extension', 'assert_bash_specific',
})


def _called_names(node):
    """Yield the simple name of every function/method called within node."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute):
                yield f.attr
            elif isinstance(f, ast.Name):
                yield f.id


def _has_bare_assert(node):
    return any(isinstance(n, ast.Assert) for n in ast.walk(node))


def _asserting_helper_names(tree):
    """Names of helpers in this module that themselves assert.

    A conformance file may wrap its comparison in a local helper (e.g.
    ``_both_identical`` in the reappraisal pins) that runs both shells and
    asserts. Any def whose body contains a bare ``assert`` counts, and — to a
    fixpoint — so does any def that calls an already-known asserting helper.
    A test that merely *calls* such a helper is genuinely exercising a claim.
    """
    names = set(_CONFORMANCE_ASSERT_HELPERS)
    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    changed = True
    while changed:
        changed = False
        for fn in funcs:
            if fn.name in names:
                continue
            if _has_bare_assert(fn) or any(c in names for c in _called_names(fn)):
                names.add(fn.name)
                changed = True
    return names


def _function_source(src_lines, node):
    """Source of a function including its decorators — ``@parametrize`` lists
    carry the exercised commands for table-driven tests."""
    start = node.lineno
    for dec in node.decorator_list:
        start = min(start, dec.lineno)
    return "\n".join(src_lines[start - 1:node.end_lineno])


def _exercising_test_sources_from_text(src):
    """Sources of ``test_*`` functions in *src* that make (or delegate) an
    assertion. Class definitions and assert-free probes are excluded."""
    src_lines = src.splitlines()
    tree = ast.parse(src)
    helpers = _asserting_helper_names(tree)
    sources = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith('test'):
            if _has_bare_assert(node) or any(c in helpers for c in _called_names(node)):
                sources.append(_function_source(src_lines, node))
    return sources


def _exercising_test_sources(path):
    return _exercising_test_sources_from_text(open(path).read())


def test_guide_has_full_support_claims():
    """Sanity: the table parses and contains claims."""
    features = _full_support_features()
    assert len(features) >= 30, f"only parsed {len(features)} claims — table moved?"


def test_every_full_support_claim_is_mapped():
    """Every 'Full support' claim must appear in CLAIM_TESTS."""
    missing = [f for f in _full_support_features() if f not in CLAIM_TESTS]
    assert not missing, (
        "User-guide 'Full support' claims without a conformance-test "
        f"mapping: {missing}. Add conformance tests proving each claim, "
        "then map them in CLAIM_TESTS (tests/conformance/"
        "test_claims_have_tests.py) — per the project principle that "
        "conformance claims must be proven by conformance tests.")


def test_matcher_rejects_vacuous_evidence():
    """Guard: the matcher must reject class-name substrings and assert-free
    probes so the meta-test cannot silently regress to substring matching."""
    sample = (
        "from conformance_framework import ConformanceTest\n"
        "\n"
        "class TestVacuous(ConformanceTest):\n"
        "    def test_probe_without_assertion(self):\n"
        "        self.check_behavior('feature_probe_marker')\n"
        "\n"
        "    def test_real(self):\n"
        "        self.assert_identical_behavior('feature_real_marker')\n"
        "\n"
        "def _both(cmd):\n"
        "    assert cmd\n"
        "\n"
        "def test_via_local_helper():\n"
        "    _both('feature_helper_marker')\n"
    )
    sources = _exercising_test_sources_from_text(sample)
    blob = "\n".join(sources)
    # A class name never appears inside a test-function body.
    assert 'class TestVacuous' not in blob
    # An assert-free check_behavior probe is excluded.
    assert 'feature_probe_marker' not in blob
    # A real assertion — and a call to a local asserting helper — count.
    assert 'feature_real_marker' in blob
    assert 'feature_helper_marker' in blob


@pytest.mark.parametrize("feature", sorted(CLAIM_TESTS))
def test_claim_evidence_exists(feature):
    """Each mapping's marker must appear inside an asserting test.

    A class-name substring or an assert-free probe no longer counts — the
    marker has to live in a ``test_*`` function that actually asserts.
    """
    rel_path, marker = CLAIM_TESTS[feature]
    path = os.path.join(CONF_DIR, rel_path)
    assert os.path.exists(path), f"{feature}: missing conformance file {rel_path}"
    sources = _exercising_test_sources(path)
    assert any(marker in s for s in sources), (
        f"{feature}: marker {marker!r} was not found inside any asserting "
        f"test in {rel_path}. The mapping must point at a test that genuinely "
        f"exercises the feature (a class-name substring or an assert-free "
        f"check_behavior probe does not count).")
