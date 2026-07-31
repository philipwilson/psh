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
    # NOT a PshError: the taxonomy classifies PshError/OSError/SyntaxError/
    # RecursionError as EXPECTED shell errors (reported, exit 1). This is an
    # internal defect and must stay in the re-raised class.
    from psh.core.exceptions import PshError
    assert not issubclass(NonExecutableRedirectError, PshError)


# === Here-strings are NOT part of the split (ruling R2-A/C2) ===

def test_here_string_content_does_not_live_in_a_heredoc_body():
    """`<<<` content has always lived in target/target_word -- never in a
    heredoc body field -- so it stays a plain Redirect and needs no subclass."""
    node = _redirect_of(parse(tokenize("cat <<<hello")))
    assert type(node) is Redirect
    assert node.type == "<<<"
    assert node.target == "hello"
    assert not isinstance(node, HeredocRedirect)


# === The --debug-ast LABEL delta, declared and pinned (round-1 nit 8) ===

@pytest.mark.parametrize("fmt", ["tree", "compact", "pretty", "sexp", "dot"])
def test_debug_ast_labels_the_executable_heredoc_by_its_type(fmt, tmp_path):
    """All five --debug-ast formats now print `HeredocRedirect` where base
    printed `Redirect`.

    This is an inherent consequence of the MEDIUM-10a type split, not a defect
    — but it is a user-visible change to a DOCUMENTED debug flag, and round-1
    verification found nothing in the suite asserting it (the visualization
    goldens contain no heredoc). Pinned here so a future regression of the
    label is caught rather than discovered.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    # PYTHONPATH pinned to THIS tree, with a DISCRIMINATOR: `python -m psh`
    # from an arbitrary cwd otherwise imports the INSTALLED psh, and the test
    # would silently assert against a different codebase than the one under
    # test (it did exactly that on first writing).
    tree_root = str(Path(__file__).resolve().parents[3])
    env = dict(os.environ, PYTHONPATH=tree_root)

    which = subprocess.run(
        [sys.executable, "-c", "import psh; print(psh.__file__)"],
        capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=30)
    assert which.stdout.startswith(tree_root), \
        f"imported the wrong psh: {which.stdout!r}"

    script = tmp_path / "probe.sh"
    script.write_bytes(b"cat <<EOF\nbody\nEOF\n")
    result = subprocess.run(
        [sys.executable, "-m", "psh", "--norc", f"--debug-ast={fmt}",
         str(script)],
        capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=30)
    # The AST dump goes to STDERR (stdout carries the heredoc body the script
    # actually printed), so both streams are searched.
    dump = result.stdout + result.stderr
    assert "HeredocRedirect" in dump, (fmt, dump[:400])


# FD-KIND AXIS for the synthetic offender (round-3 blocker R9-B). The
# var_fd route reaches the fd universe BEFORE either operator-string arm, so
# it needed its own arm -- and the value shape is one THIS SLOT created: before
# the named-fd heredoc fix, `cat {v}<<EOF` failed at parse time and no
# bare-parse value with type='<<' AND var_fd could exist. When a fix creates a
# new representable shape, every guard universe must grow with it.
_FD_KINDS = [
    ("none", {}),
    ("digit", {"fd": 3}),
    ("named", {"var_fd": "v"}),
]


@pytest.mark.parametrize("kind,extra", _FD_KINDS, ids=[k[0] for k in _FD_KINDS])
def test_synthetic_offender_raises_typed_on_every_fd_kind(shell, kind, extra):
    """Every fd kind, at the fd backend."""
    from psh.io_redirect.planner import RedirectPlan

    offender = Redirect(type="<<", target="EOF", **extra)
    plan = RedirectPlan(redirect=offender, target=None)
    with pytest.raises(NonExecutableRedirectError, match="no collected body"):
        shell.io_manager.file_redirector.apply_fd_plan(plan)


# Only the NAMED kind reaches apply_var_fd_redirect at all, so the route test
# below is parametrized over that one value rather than over all three with two
# structurally-forced skips -- an axis that reads as three live rows when only
# one can ever run is a dishonest axis (round-5 nit 2).
_VAR_FD_ROUTE_KINDS = [k for k in _FD_KINDS if "var_fd" in k[1]]


@pytest.mark.parametrize("kind,extra", _VAR_FD_ROUTE_KINDS,
                         ids=[k[0] for k in _VAR_FD_ROUTE_KINDS])
def test_synthetic_offender_raises_typed_on_the_var_fd_route(shell, kind,
                                                             extra):
    """And through apply_var_fd_redirect directly -- the route that used to die
    on a raw AttributeError from the missing body field."""
    offender = Redirect(type="<<", target="EOF", **extra)
    with pytest.raises(NonExecutableRedirectError, match="no collected body"):
        shell.io_manager.file_redirector.apply_var_fd_redirect(offender)


def test_synthetic_offender_raises_at_the_BUILTIN_STREAM_backend(shell,
                                                                 tmp_path):
    """The OTHER backend's explicit arm (round-2 nit 12).

    C1 promised a guard that bites on BOTH backends, but only the fd backend
    had a committed test — the builtin-stream arm in
    `manager.py#IOManager.setup_builtin_redirections` was covered by a probe I
    ran by hand, which is not a guard. A builtin reading a non-executable
    heredoc parse state must hit the same typed error, not fall through to a
    silent empty document.
    """
    from psh.ast_nodes import Redirect, SimpleCommand, Word
    from psh.io_redirect.file_redirect import NonExecutableRedirectError

    offender = Redirect(type="<<", target="EOF")
    command = SimpleCommand(words=[Word(parts=[])], redirects=[offender])
    with pytest.raises(NonExecutableRedirectError, match="no collected body"):
        shell.io_manager.setup_builtin_redirections(command)


# === DIRECT coverage of redirect_heredoc (round-5 blocker R11-A) ============
#
# This primitive IS the MEDIUM-10 late-discovery site. After the type split it
# ended up with no test touching it at all -- a coverage REGRESSION hidden by
# the fact that everything around it got new tests. The dispatchers are pinned
# elsewhere; these rows pin the primitive itself.

def test_redirect_heredoc_materializes_the_body_on_the_default_fd(shell,
                                                                  capfd):
    """The happy path, called DIRECTLY rather than through a dispatcher."""
    import os
    node = HeredocRedirect(type="<<", target="EOF", heredoc_content="hello\n")
    saved = os.dup(0)
    try:
        content = shell.io_manager.file_redirector.redirect_heredoc(node)
        assert content == "hello\n"
        assert os.read(0, 32) == b"hello\n"
    finally:
        os.dup2(saved, 0)
        os.close(saved)


def test_redirect_heredoc_expands_an_unquoted_body(shell):
    """Expansion is the primitive's other job, and it keys on heredoc_quoted."""
    shell.state.set_variable("WHO", "world")
    node = HeredocRedirect(type="<<", target="EOF",
                           heredoc_content="hi $WHO\n", heredoc_quoted=False)
    assert shell.io_manager.file_redirector.redirect_heredoc(node) == "hi world\n"


def test_redirect_heredoc_leaves_a_quoted_body_literal(shell):
    shell.state.set_variable("WHO", "world")
    node = HeredocRedirect(type="<<", target="'EOF'",
                           heredoc_content="hi $WHO\n", heredoc_quoted=True)
    assert shell.io_manager.file_redirector.redirect_heredoc(node) == "hi $WHO\n"


def test_redirect_heredoc_rejects_the_non_executable_state(shell):
    """The direct-call boundary typed in round 4 (nit 11)."""
    with pytest.raises(NonExecutableRedirectError, match="redirect_heredoc"):
        shell.io_manager.file_redirector.redirect_heredoc(
            Redirect(type="<<", target="EOF"))
