"""Direct unit coverage for CommandAssignments (executor/command_assignments.py).

The dispatch-level behavior (prefix assignments around real commands,
readonly conformance, xtrace shapes) is covered by the integration and
conformance batteries; these tests pin the specialist's public surface —
extract / apply_pure / apply_prefix / restore — independent of
CommandExecutor's dispatch.

Contract notes mirrored from the module docstring:
- the DISPATCHER clears state.last_cmdsub_status before any expansion;
  tests do that explicitly before apply_pure.
- restore() takes the PrefixOutcome.saved mapping opaquely.
"""

import dataclasses

import pytest

from psh.ast_nodes import SimpleCommand
from psh.executor.command_assignments import CommandAssignments, PrefixOutcome
from psh.lexer import tokenize
from psh.parser import parse


def first_simple_command(text: str) -> SimpleCommand:
    """Parse text and return the first SimpleCommand in the AST."""
    found = []

    def walk(node):
        if isinstance(node, SimpleCommand):
            found.append(node)
            return
        if dataclasses.is_dataclass(node):
            for f in dataclasses.fields(node):
                value = getattr(node, f.name)
                children = value if isinstance(value, list) else [value]
                for child in children:
                    if dataclasses.is_dataclass(child):
                        walk(child)

    walk(parse(tokenize(text)))
    assert found, f"no SimpleCommand parsed from {text!r}"
    return found[0]


@pytest.fixture
def assignments(captured_shell):
    return CommandAssignments(captured_shell), captured_shell


class TestExtract:
    def test_extracts_leading_assignment_run(self, assignments):
        ca, _shell = assignments
        node = first_simple_command('A=1 B=$A cmd arg')
        raw = ca.extract(node)
        assert [(name, value) for name, value, _w in raw] == \
            [('A', '1'), ('B', '$A')]
        assert all(word is not None for _n, _v, word in raw)

    def test_stops_at_command_word(self, assignments):
        ca, _shell = assignments
        node = first_simple_command('A=1 echo B=2')
        raw = ca.extract(node)
        # B=2 is an ordinary argument of echo, not an assignment
        assert [name for name, _v, _w in raw] == ['A']

    def test_quoted_name_is_not_an_assignment(self, assignments):
        ca, _shell = assignments
        node = first_simple_command('"FOO"=bar cmd')
        assert ca.extract(node) == []

    def test_pure_assignment_consumes_all_args(self, assignments):
        ca, _shell = assignments
        node = first_simple_command('x=1 y=2')
        raw = ca.extract(node)
        assert len(raw) == len(node.args) == 2


class TestApplyPure:
    def test_left_to_right_visibility(self, assignments):
        ca, shell = assignments
        node = first_simple_command('x=1 y=$x')
        shell.state.last_cmdsub_status = None  # dispatcher's job
        assert ca.apply_pure(node, ca.extract(node)) == 0
        assert shell.state.get_variable('x') == '1'
        assert shell.state.get_variable('y') == '1'

    def test_status_is_last_command_substitution(self, assignments):
        ca, shell = assignments
        node = first_simple_command('x=$(exit 7)')
        shell.state.last_cmdsub_status = None
        assert ca.apply_pure(node, ca.extract(node)) == 7

    def test_single_quoted_value_stays_literal(self, assignments):
        ca, shell = assignments
        node = first_simple_command("x='$HOME'")
        shell.state.last_cmdsub_status = None
        assert ca.apply_pure(node, ca.extract(node)) == 0
        assert shell.state.get_variable('x') == '$HOME'

    def test_readonly_raises_assignment_abort(self, assignments):
        # A readonly-variable assignment error aborts the current top-level
        # command (bash) — apply_pure prints the error and raises AssignmentAbort
        # (caught at the source-processor boundary), rather than returning 1.
        from psh.core import AssignmentAbort
        ca, shell = assignments
        shell.run_command('readonly RO=1')
        shell.clear_output()
        node = first_simple_command('RO=2')
        shell.state.last_cmdsub_status = None
        with pytest.raises(AssignmentAbort) as exc_info:
            ca.apply_pure(node, ca.extract(node))
        assert exc_info.value.status == 1
        assert 'readonly variable' in shell.get_stderr()
        assert shell.state.get_variable('RO') == '1'


class TestApplyPrefixAndRestore:
    def test_outcome_applies_state_and_env(self, assignments):
        ca, shell = assignments
        node = first_simple_command('A=1 B=$A true')
        outcome = ca.apply_prefix(ca.extract(node))
        assert isinstance(outcome, PrefixOutcome)
        assert outcome.failed is False
        # left-to-right: B's value saw A's new value
        assert outcome.applied == [('A', '1'), ('B', '1')]
        assert shell.state.get_variable('B') == '1'
        assert shell.env.get('A') == '1'  # visible to external commands

    def test_restore_returns_state_and_env(self, assignments):
        ca, shell = assignments
        shell.run_command('V=old')
        node = first_simple_command('V=new W=1 true')
        outcome = ca.apply_prefix(ca.extract(node))
        assert shell.state.get_variable('V') == 'new'
        ca.restore(outcome.saved)
        assert shell.state.get_variable('V') == 'old'
        # bash 5.2 (pinned 2026-06-13): a previously-UNSET variable is
        # restored to UNSET, not set-but-empty — `W=1 true; echo ${W+yes}`
        # prints nothing in bash. (apply_prefix used to snapshot via
        # get_variable()'s '' default, which could not represent unset.)
        assert shell.state.scope_manager.get_variable('W') is None
        assert 'W' not in shell.env

    def test_readonly_skips_and_continues(self, assignments):
        ca, shell = assignments
        shell.run_command('readonly RO=1')
        shell.clear_output()
        node = first_simple_command('A=9 RO=2 B=8 true')
        outcome = ca.apply_prefix(ca.extract(node))
        # bash 5.2: the failing assignment is reported and skipped, the
        # others still apply, and failed=True lets the caller make it
        # fatal under set -e.
        assert outcome.failed is True
        assert outcome.applied == [('A', '9'), ('B', '8')]
        assert shell.state.get_variable('RO') == '1'
        assert 'readonly variable' in shell.get_stderr()
        ca.restore(outcome.saved)
        # previously-unset variables return to UNSET after restore (bash):
        # see test_restore_returns_state_and_env
        assert shell.state.scope_manager.get_variable('A') is None
        assert shell.state.scope_manager.get_variable('B') is None

    def test_append_assignment_resolves_against_current_value(self, assignments):
        ca, shell = assignments
        shell.run_command('x=ab')
        node = first_simple_command('x+=cd true')
        outcome = ca.apply_prefix(ca.extract(node))
        assert outcome.applied == [('x', 'abcd')]
        ca.restore(outcome.saved)
        assert shell.state.get_variable('x') == 'ab'
