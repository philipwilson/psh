"""Meta-test: no bash `[[ ]]` conditionals in the POSIX conformance tree.

The POSIX conformance tree (``tests/conformance/posix/``) compares PSH against
bash, but its *cases* must be POSIX shell — bash-only syntax there
mislabels a bash extension as POSIX coverage (finding C1 of the 2026-07-06
tests/docs appraisal, which flagged `[[ ]]` cases under posix/). The bash `[[`
parallels belong under ``tests/conformance/bash/``.

The scan looks only at the *command strings* passed to the conformance
helpers (``assert_identical_behavior`` etc.), never at docstrings or comments,
and matches the conditional form ``[[<whitespace>`` — so POSIX glob character
classes like ``[[:alpha:]]`` and bracket expressions are not flagged.
"""

import ast
import os
import re

CONF_POSIX = os.path.join(os.path.dirname(__file__),
                          '..', '..', 'conformance', 'posix')

# Methods whose string arguments are shell command text.
_COMMAND_METHODS = frozenset({
    'assert_identical_behavior', 'assert_documented_difference',
    'assert_psh_extension', 'check_behavior',
    'run_in_psh', 'run_in_bash', 'compare_behavior',
})

# bash `[[` conditional: a double bracket followed by whitespace. This does NOT
# match POSIX `[[:class:]]` (followed by ':') or a `[[abc]` glob (no space).
_DOUBLE_BRACKET = re.compile(r'\[\[\s')


def _command_strings(src):
    """Yield (lineno, string) for every string constant passed to a
    conformance command helper in *src*."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and f.attr in _COMMAND_METHODS):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                yield node.lineno, arg.value


def _posix_files():
    for root, _dirs, names in os.walk(CONF_POSIX):
        for name in names:
            if name.startswith('test_') and name.endswith('.py'):
                yield os.path.join(root, name)


def test_no_double_bracket_in_posix_conformance():
    violations = {}
    for path in _posix_files():
        with open(path) as f:
            hits = [lineno for lineno, s in _command_strings(f.read())
                    if _DOUBLE_BRACKET.search(s)]
        if hits:
            violations[os.path.basename(path)] = sorted(set(hits))
    assert not violations, (
        "bash `[[ ]]` conditionals in POSIX conformance command strings "
        f"(finding C1): {violations}. `[[ ]]` is a bash extension — move the "
        "case to tests/conformance/bash/.")


def test_scanner_discriminates_bashism_from_posix():
    """Self-test: flags a `[[` conditional; ignores POSIX char classes/globs."""
    bashy = "class C:\n def test(self):\n  self.assert_identical_behavior('[[ -x d ]]')\n"
    posix_class = "class C:\n def test(self):\n  self.assert_identical_behavior('echo [[:alpha:]]*')\n"
    docstring_only = "class C:\n def test(self):\n  '''mentions [[ ]] in prose'''\n  self.assert_identical_behavior('echo hi')\n"
    assert [s for _, s in _command_strings(bashy) if _DOUBLE_BRACKET.search(s)]
    assert not [s for _, s in _command_strings(posix_class)
                if _DOUBLE_BRACKET.search(s)]
    # The `[[ ]]` here is only in a docstring, not a command string.
    assert not [s for _, s in _command_strings(docstring_only)
                if _DOUBLE_BRACKET.search(s)]
