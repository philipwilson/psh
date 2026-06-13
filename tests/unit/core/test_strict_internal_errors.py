"""Tests for strict internal-error mode (the strict-errors shell option).

Background: when an UNEXPECTED implementation exception (i.e. not a deliberate
shell-semantics or control-flow exception) escapes command execution, psh
normally swallows it to exit status 1 and prints a generic ``psh: ...`` message
— correct for an interactive shell, but it makes an internal bug look like an
ordinary command failure. The opt-in strict-errors mode RE-RAISES such
exceptions so a test harness can surface internal defects loudly.

These tests prove:
- strict mode OFF (default): an unexpected internal exception is swallowed to
  status 1 (current behavior preserved);
- strict mode ON: the same exception PROPAGATES instead;
- deliberate shell-semantics failures (ordinary nonzero exits, unbound
  variables) are UNAFFECTED by strict mode.
"""

import pytest

from psh.builtins.base import Builtin
from psh.builtins.registry import registry


class _BoomBuiltin(Builtin):
    """Test-only builtin that raises an UNEXPECTED exception (an internal
    defect stand-in) so the last-resort guard is exercised."""

    @property
    def name(self) -> str:
        return "psh_test_boom"

    def execute(self, args, shell) -> int:
        raise RuntimeError("boom from psh_test_boom")


@pytest.fixture
def boom_builtin():
    """Register the boom builtin for the duration of one test, then remove it.

    Builtins are process-wide singletons, so we must un-register to avoid
    leaking the test-only command into other tests.
    """
    registry.register(_BoomBuiltin)
    name = "psh_test_boom"
    instance = registry.get(name)
    try:
        yield name
    finally:
        # Remove from name map and instance set so the registry is clean.
        registry._builtins.pop(name, None)
        registry._instances.discard(instance)


def test_unexpected_exception_swallowed_when_strict_off(captured_shell,
                                                        boom_builtin):
    """Strict OFF: an internal exception becomes exit status 1.

    The suite runs with strict-errors enabled globally (conftest sets
    PSH_STRICT_ERRORS=1), so this test — which characterizes the NON-strict
    swallow-to-1 behavior — explicitly turns the option off first.
    """
    captured_shell.state.options['strict-errors'] = False
    assert captured_shell.state.options.get('strict-errors') is False
    rc = captured_shell.run_command(boom_builtin)
    assert rc == 1
    # The generic last-resort message is printed (byte-identical to before).
    assert f"psh: {boom_builtin}: boom from psh_test_boom" in \
        captured_shell.get_stderr()


def test_unexpected_exception_propagates_when_strict_on(captured_shell,
                                                        boom_builtin):
    """Strict ON: the same internal exception propagates instead of status 1."""
    captured_shell.state.options['strict-errors'] = True
    with pytest.raises(RuntimeError, match="boom from psh_test_boom"):
        captured_shell.run_command(boom_builtin)


def test_unexpected_exception_in_function_propagates_when_strict_on(
        captured_shell, boom_builtin):
    """The function-body guard re-raises under strict mode too."""
    captured_shell.run_command("f() { psh_test_boom; }")
    captured_shell.state.options['strict-errors'] = True
    with pytest.raises(RuntimeError, match="boom from psh_test_boom"):
        captured_shell.run_command("f")


def test_ordinary_nonzero_exit_unaffected_by_strict(captured_shell):
    """Strict mode must NOT turn an ordinary nonzero exit into a raise."""
    captured_shell.state.options['strict-errors'] = True
    rc = captured_shell.run_command("false")
    assert rc == 1  # plain command failure, not an exception


def test_unbound_variable_unaffected_by_strict(captured_shell):
    """A real shell-semantics exception (set -u unbound variable) keeps its
    normal behavior under strict mode — it is not an internal defect."""
    captured_shell.state.options['strict-errors'] = True
    captured_shell.run_command("set -u")
    # Unbound variable under set -u: status 127 in script mode, with the
    # usual diagnostic — NOT a propagated Python exception.
    rc = captured_shell.run_command("echo $THIS_IS_UNSET")
    assert rc == 127
    assert "unbound variable" in captured_shell.get_stderr()


def test_strict_errors_seeded_from_environment(monkeypatch):
    """PSH_STRICT_ERRORS=<truthy> seeds the option to True at construction."""
    from psh.shell import Shell

    for truthy in ("1", "true", "TRUE", "yes", "Yes"):
        monkeypatch.setenv("PSH_STRICT_ERRORS", truthy)
        shell = Shell(norc=True)
        assert shell.state.options['strict-errors'] is True, truthy

    for falsy in ("0", "false", "no", ""):
        monkeypatch.setenv("PSH_STRICT_ERRORS", falsy)
        shell = Shell(norc=True)
        assert shell.state.options['strict-errors'] is False, falsy

    monkeypatch.delenv("PSH_STRICT_ERRORS", raising=False)
    shell = Shell(norc=True)
    assert shell.state.options['strict-errors'] is False


def test_taxonomy_expected_errors_not_reraised_under_strict():
    """report_internal_defect honors the expected-error taxonomy: under strict
    mode a PshError / OSError / SyntaxError is NOT re-raised (handled as exit 1),
    while a genuine defect (RuntimeError) IS re-raised."""
    import io

    from psh.core import report_internal_defect
    from psh.core.exceptions import (
        ExpansionError,
        FunctionDefinitionError,
        PshError,
    )
    from psh.shell import Shell

    shell = Shell(norc=True)
    shell.state.options['strict-errors'] = True

    # Expected shell errors: handled (return 1), never re-raised.
    for exc in (
        PshError("generic psh error"),
        ExpansionError("bad expansion"),
        FunctionDefinitionError("'x': readonly function"),
        OSError("Bad file descriptor"),
        SyntaxError("Unclosed quote"),
    ):
        stream = io.StringIO()
        rc = report_internal_defect(shell.state, exc, stream=stream)
        assert rc == 1, exc
        assert "psh:" in stream.getvalue()

    # Genuine internal defects: re-raised under strict mode.
    for exc in (
        RuntimeError("boom"),
        AttributeError("nope"),
        TypeError("bad type"),
        KeyError("missing"),
        ValueError("plain value error"),
    ):
        stream = io.StringIO()
        with pytest.raises(type(exc)):
            report_internal_defect(shell.state, exc, stream=stream)


def test_taxonomy_expected_errors_handled_when_strict_off():
    """With strict OFF, even a defect is swallowed to exit 1 (baseline)."""
    import io

    from psh.core import report_internal_defect
    from psh.shell import Shell

    shell = Shell(norc=True)
    shell.state.options['strict-errors'] = False
    stream = io.StringIO()
    rc = report_internal_defect(shell.state, RuntimeError("boom"), stream=stream)
    assert rc == 1
    assert "psh:" in stream.getvalue()


def test_set_o_toggles_strict_errors(captured_shell):
    """set -o strict-errors / set +o strict-errors work via the named-option
    framework (mirrors other boolean options)."""
    captured_shell.run_command("set -o strict-errors")
    assert captured_shell.state.options['strict-errors'] is True
    captured_shell.run_command("set +o strict-errors")
    assert captured_shell.state.options['strict-errors'] is False
