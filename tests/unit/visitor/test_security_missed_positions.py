"""The four reappraisal-#22 HIGH-2 security probes, committed as tests.

At v0.755.0 (a765f1a0) `--security` printed ``No security issues found!`` for
every one of these scripts — the dangerous code sits in an executable syntax
position the hand-maintained visitor traversal skipped (redirect-only command,
redirect target, for/case subject words). With framework-owned total traversal
(remediation 2.1) each reports a finding. The template positions
(``${x:-$(...)}``, ``$(( $(...) ))``, ``a[$(...)]=v``) and the
opaque-region flags (backtick bodies, expanding heredoc bodies) are pinned
alongside, plus the ``--security`` CLI leg run exactly as the committed probe
scripts do (``docs/reviews/evidence/boundary_remediation_2026-07/
wave0-base-probes/sec-probe.sh``, ``r22-probes.sh``).
"""

import subprocess
import sys

import pytest

from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor.enhanced_validator_visitor import EnhancedValidatorVisitor
from psh.visitor.security_visitor import SecurityVisitor
from psh.visitor.validator_visitor import Severity


def _issue_types(src):
    v = SecurityVisitor()
    v.visit(parse(tokenize(src)))
    return [i.issue_type for i in v.issues]


# The four probe commands, verbatim from reappraisal #22 HIGH-2.
PROBES = [
    ('redirect-only-command', '>/etc/passwd', 'SENSITIVE_FILE_WRITE'),
    ('redirect-target', 'echo >$(rm -rf /tmp/psh-never-created)',
     'SENSITIVE_COMMAND'),
    ('for-subject-word',
     'for x in "$(rm -rf /tmp/psh-never-created)"; do :; done',
     'SENSITIVE_COMMAND'),
    ('case-subject-word',
     'case "$(rm -rf /tmp/psh-never-created)" in x) :;; esac',
     'SENSITIVE_COMMAND'),
]


@pytest.mark.parametrize("label,src,expected", PROBES,
                         ids=[p[0] for p in PROBES])
def test_probe_position_reports_a_finding(label, src, expected):
    types = _issue_types(src)
    assert expected in types, (
        f"{label}: {src!r} must report {expected}; got {types} "
        "(at base this printed 'No security issues found!')"
    )


@pytest.mark.parametrize("label,src", [
    ('param-operand-template', 'echo "${x:-$(rm -rf /tmp/psh-never-created)}"'),
    ('arith-expansion-template', 'echo "$(( $(rm -rf /tmp/psh-never-created) ))"'),
    ('arith-command-template', '(( $(rm -rf /tmp/psh-never-created) ))'),
    ('subscript-template', 'a[$(rm -rf /tmp/psh-never-created)]=v'),
], ids=lambda x: x if isinstance(x, str) and '-' in x else None)
def test_template_sub_positions_report_findings(label, src):
    """The S3 template carriers' parsed substitutions are analyzed too."""
    types = _issue_types(src)
    assert 'SENSITIVE_COMMAND' in types, (label, src, types)


def test_arith_command_also_keeps_textual_injection_flag():
    """(( $(cmd) )) carries BOTH the textual arithmetic-injection advisory and
    the analyzed body's own findings — complementary, not either/or."""
    types = _issue_types('(( $(rm -rf /tmp/psh-never-created) ))')
    assert 'ARITHMETIC_INJECTION' in types
    assert 'SENSITIVE_COMMAND' in types


# --- Opaque executable regions: flagged, never silently skipped -------------

def test_backtick_body_is_flagged_opaque():
    types = _issue_types('echo `rm -rf /tmp/psh-never-created`')
    assert 'UNANALYZED_REGION' in types


def _security_cli(tmp_path, src):
    script = tmp_path / 'probe.sh'
    script.write_text(src)
    return subprocess.run(
        [sys.executable, '-m', 'psh', '--security', str(script)],
        capture_output=True, text=True, timeout=30)


# Heredoc BODIES exist only on the heredoc-aware parse path (a bare
# parse(tokenize(...)) leaves heredoc_content None and mis-lexes the body
# lines as commands), so these pins run the real --security pipeline.

def test_unquoted_heredoc_with_substitution_is_flagged_opaque(tmp_path):
    result = _security_cli(
        tmp_path, 'cat <<EOF\n$(rm -rf /tmp/psh-never-created)\nEOF\n')
    assert 'cannot be statically analyzed' in result.stdout
    assert result.returncode == 1


def test_quoted_heredoc_is_not_flagged(tmp_path):
    """A quoted delimiter disables expansion — the body is inert data."""
    result = _security_cli(
        tmp_path, "cat <<'EOF'\n$(rm -rf /tmp/psh-never-created)\nEOF\n")
    assert 'No security issues found' in result.stdout
    assert result.returncode == 0


def test_plain_heredoc_without_substitution_is_not_flagged(tmp_path):
    result = _security_cli(tmp_path, 'cat <<EOF\njust text $var\nEOF\n')
    assert 'No security issues found' in result.stdout
    assert result.returncode == 0


# --- The CLI leg, exactly as the committed probe scripts run ----------------

@pytest.mark.parametrize("label,src,expected", PROBES,
                         ids=[p[0] for p in PROBES])
def test_security_cli_reports_findings(label, src, expected, tmp_path):
    script = tmp_path / 'probe.sh'
    script.write_text(src + '\n')
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '--security', str(script)],
        capture_output=True, text=True, timeout=30)
    assert 'No security issues found' not in result.stdout, (
        f"{label}: --security still makes a clean claim:\n{result.stdout}")
    assert result.returncode == 1, (result.returncode, result.stdout,
                                    result.stderr)


# --- Redirect-only commands are legal (bash -n agrees) ----------------------

def test_validator_accepts_redirect_only_command():
    """`>file` is legal shell (bash 5.2.26 `bash -n` exits 0 silently); the
    validator must not call it an empty command — and must still traverse the
    redirect (a dangerous target embedded there is the security visitor's
    finding, exercised above)."""
    v = EnhancedValidatorVisitor()
    v.visit(parse(tokenize('>/tmp/some-file')))
    errors = [i for i in v.issues if i.severity is Severity.ERROR]
    assert errors == [], [i.message for i in errors]


def test_validator_still_rejects_truly_empty_command():
    from psh.ast_nodes import SimpleCommand
    v = EnhancedValidatorVisitor()
    v.visit(SimpleCommand())
    assert any(i.severity is Severity.ERROR and 'Empty command' in i.message
               for i in v.issues)
