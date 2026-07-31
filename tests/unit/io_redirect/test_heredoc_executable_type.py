"""The executable heredoc body is non-optional (remediation 2.5, #22 MEDIUM-10a).

At base e36116c3 BOTH parsers could manufacture an EXECUTABLE heredoc redirect
with `heredoc_content=None` (RD's bare-parse arm, and the combinator's
missing-operator-ID fallback), and execution discovered it only at
`file_redirect.py:361` -- a RuntimeError raised after the redirect had already
been planned.

The fix splits the representation instead of validating it:

* plain `Redirect` with a heredoc operator type = the INCOMPLETE PARSE STATE a
  bare token-level parse produces (bodies still in the token stream). It has no
  body field at all, so the invalid executable value cannot be built;
* `HeredocRedirect` = the ONLY executable form, body required at construction.

WHAT REPLACES THE LATE DISCOVERY (ruling R2-A/C1): the `isinstance` dispatch in
`file_redirect.py#FileRedirector.apply_fd_plan` (and its stream-backend twin in
`manager.py#setup_builtin_redirections`) routes executable heredocs by TYPE,
and a structurally-heredoc plain `Redirect` hits an EXPLICIT arm raising the
typed `NonExecutableRedirectError`. The arm exists so such a value can never
fall through the type-string chain and open a file named after the delimiter.
`NonExecutableRedirectError` derives from `RuntimeError`, i.e. the
strict-errors-LOUD class of the expected-error taxonomy (psh/core/CLAUDE.md).
"""
import dataclasses

import pytest

from psh.ast_nodes import HeredocRedirect, Redirect
from psh.io_redirect.file_redirect import NonExecutableRedirectError
from psh.lexer import tokenize
from psh.parser import parse
from psh.scripting.lex_parse import lex_and_expand


def _redirect_of(program):
    return program.statements[0].pipelines[0].commands[0].redirects[0]


# === The type-level invariant ===

def test_executable_heredoc_cannot_be_built_without_a_body():
    """The whole point: the invalid state is UNREPRESENTABLE, not validated."""
    with pytest.raises(TypeError, match="heredoc_content"):
        HeredocRedirect(type="<<", target="EOF")


def test_empty_body_is_representable_and_is_not_none():
    """An empty here-document is '' -- distinct from 'no body collected'."""
    node = HeredocRedirect(type="<<", target="EOF", heredoc_content="")
    assert node.heredoc_content == ""


def test_plain_redirect_has_no_body_field_at_all():
    """Not 'a None body' -- no field. That is what makes it unrepresentable."""
    names = {f.name for f in dataclasses.fields(Redirect)}
    assert "heredoc_content" not in names
    assert "heredoc_content" in {f.name for f in dataclasses.fields(HeredocRedirect)}


# === Both parsers, both arms ===

@pytest.mark.parametrize("source", ["cat <<EOF", "cat <<-EOF", "cat 0<<EOF"])
def test_bare_parse_yields_incomplete_state_not_an_executable_value(source):
    """RD's bare arm (the #22 site) -- structurally heredoc, not executable."""
    node = _redirect_of(parse(tokenize(source)))
    assert type(node) is Redirect
    assert node.type in ("<<", "<<-")


def test_live_parse_yields_the_executable_type_with_its_body(shell):
    unit = lex_and_expand("cat <<EOF\nbody\nEOF\n", shell)
    from psh.parser import ParseInputs, parse_with_inputs
    program = parse_with_inputs(
        unit.tokens, ParseInputs(heredocs=unit.heredocs))
    node = _redirect_of(program)
    assert isinstance(node, HeredocRedirect)
    assert node.heredoc_content == "body\n"


# === The guard BITES (synthetic offender) ===

def test_synthetic_offender_raises_the_typed_error_at_the_fd_backend(shell):
    """A hand-built non-executable heredoc fed to execution: typed error, and
    demonstrably NOT a file open named after the delimiter."""
    from psh.io_redirect.planner import RedirectPlan

    offender = Redirect(type="<<", target="EOF")
    plan = RedirectPlan(redirect=offender, target=None)
    with pytest.raises(NonExecutableRedirectError, match="no collected body"):
        shell.io_manager.file_redirector.apply_fd_plan(plan)


def test_the_typed_error_is_the_strict_errors_loud_class():
    """RuntimeError == INTERNAL DEFECT in the taxonomy, so strict-errors
    re-raises it instead of masking it as exit 1."""
    assert issubclass(NonExecutableRedirectError, RuntimeError)
    for expected_class in (Exception,):
        assert issubclass(NonExecutableRedirectError, expected_class)


# === Here-strings are NOT part of the split (ruling R2-A/C2) ===

def test_here_string_content_does_not_live_in_a_heredoc_body():
    """`<<<` content has always lived in target/target_word -- never in a
    heredoc body field -- so it stays a plain Redirect and needs no subclass."""
    node = _redirect_of(parse(tokenize("cat <<<hello")))
    assert type(node) is Redirect
    assert node.type == "<<<"
    assert node.target == "hello"
    assert not isinstance(node, HeredocRedirect)
