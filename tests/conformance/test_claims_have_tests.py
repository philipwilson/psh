"""Meta-test: user-guide conformance claims map to conformance tests.

Project principle (CLAUDE.md): "If we assert that a feature of psh is
POSIX or bash conformant in the user's guide then we must have a test in
tests/conformance/ which proves it."

This test makes that principle CHECKABLE: every feature row in the
compatibility table of docs/user_guide/17_differences_from_bash.md whose
Notes column says "Full support" must have an entry in CLAIM_TESTS below,
and each entry's evidence (a conformance file containing a marker string)
must actually exist. Adding a new "Full support" claim without conformance
evidence fails this test.
"""

import os
import re

import pytest

GUIDE = os.path.join(os.path.dirname(__file__), '..', '..',
                     'docs', 'user_guide', '17_differences_from_bash.md')
CONF_DIR = os.path.dirname(__file__)

# Feature (exactly as in the table's first column) → (conformance file
# relative to tests/conformance/, marker string that must appear in it).
CLAIM_TESTS = {
    'Command execution': ('posix/test_posix_compliance.py', 'class TestPOSIXSimpleCommands'),
    'Pipelines': ('posix/test_posix_compliance.py', 'class TestPOSIXPipelines'),
    'Subshells': ('posix/test_posix_compliance.py', 'class TestPOSIXCompoundCommands'),
    'Simple variables': ('posix/test_posix_compliance.py', 'class TestPOSIXShellParameters'),
    'Arrays': ('bash/test_bash_compatibility.py', 'class TestBashArrays'),
    'Associative arrays': ('bash/test_bash_compatibility.py', 'class TestBashArrays'),
    'Local variables': ('posix/test_posix_compliance.py', 'class TestPOSIXShellFunctions'),
    'Arithmetic expansion': ('posix/test_posix_compliance.py', 'class TestPOSIXArithmeticExpansion'),
    'Brace expansion': ('bash/test_bash_compatibility.py', 'class TestBashBraceExpansion'),
    'Process substitution': ('bash/test_bash_compatibility.py', 'process_substitution'),
    'Tilde expansion': ('posix/test_posix_compliance.py', 'class TestPOSIXTildeExpansion'),
    'if/then/else/fi': ('posix/test_posix_compliance.py', 'class TestPOSIXCompoundCommands'),
    'while/until/do/done': ('posix/test_posix_compliance.py', 'class TestPOSIXCompoundCommands'),
    'for/do/done': ('posix/test_posix_compliance.py', 'class TestPOSIXCompoundCommands'),
    'C-style for loops': ('bash/test_control_eval_conformance.py', 'class TestCStyleForConformance'),
    'case/esac': ('posix/test_posix_compliance.py', 'class TestPOSIXCompoundCommands'),
    'select': ('bash/test_select_trap_conformance.py', 'class TestSelectConformance'),
    'Arithmetic commands (( ))': ('bash/test_bash_compatibility.py', 'class TestBashArithmeticExpansion'),
    'Control structures in pipelines': ('bash/test_control_eval_conformance.py', 'class TestControlStructuresInPipelines'),
    'Return values': ('posix/test_posix_compliance.py', 'class TestPOSIXShellFunctions'),
    'wait builtin': ('posix/test_heredoc_fd_jobs_conformance.py', 'class TestJobControlConformance'),
    'disown builtin': ('posix/test_heredoc_fd_jobs_conformance.py', 'class TestJobControlConformance'),
    'set -e (errexit)': ('posix/test_errexit_conformance.py', 'class TestErrexitTriggers'),
    'set -u (nounset)': ('bash/test_bash_compatibility.py', 'class TestBashOptions'),
    'set -x (xtrace)': ('bash/test_bash_compatibility.py', 'class TestBashOptions'),
    'set -o pipefail': ('bash/test_bash_compatibility.py', 'class TestBashOptions'),
    'set -o noclobber': ('bash/test_bash_compatibility.py', 'class TestBashOptions'),
    'set -o allexport': ('bash/test_bash_compatibility.py', 'class TestBashOptions'),
    'set -o noglob': ('bash/test_bash_compatibility.py', 'class TestBashOptions'),
    'set -o verbose': ('bash/test_bash_compatibility.py', 'class TestBashOptions'),
    'Here documents': ('posix/test_heredoc_fd_jobs_conformance.py', 'class TestHeredocConformance'),
    'Here strings': ('posix/test_heredoc_fd_jobs_conformance.py', 'test_herestring'),
    'Enhanced test [[ ]]': ('bash/test_bash_compatibility.py', 'class TestBashConditionals'),
    'eval builtin': ('bash/test_control_eval_conformance.py', 'class TestEvalConformance'),
    'getopts builtin': ('posix/test_getopts_conformance.py', 'class TestGetoptsBasics'),
    'printf builtin': ('bash/test_bash_compatibility.py', 'printf'),
    'pushd/popd/dirs': ('bash/test_bash_compatibility.py', 'pushd'),
}


def _full_support_features():
    text = open(GUIDE).read()
    features = []
    for line in text.splitlines():
        m = re.match(r'\|\s*([^|]+?)\s*\|\s*Yes\s*\|\s*Yes\s*\|\s*Full support\s*\|', line)
        if m:
            features.append(m.group(1).strip())
    return features


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


@pytest.mark.parametrize("feature", sorted(CLAIM_TESTS))
def test_claim_evidence_exists(feature):
    """Each mapping's evidence file exists and contains its marker."""
    rel_path, marker = CLAIM_TESTS[feature]
    path = os.path.join(CONF_DIR, rel_path)
    assert os.path.exists(path), f"{feature}: missing conformance file {rel_path}"
    content = open(path).read()
    assert marker in content, (
        f"{feature}: marker {marker!r} not found in {rel_path}")
