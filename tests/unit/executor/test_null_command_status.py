"""Unit guards for the null-command status rule (slot 1.10, C041).

Owner: ``psh/executor/null_command.py`` — the ONE answer to "what is ``$?``
after a simple command that ran no program". Repro:
``psh -c '$(exit 5); echo rc=$?'`` prints rc=5.

These hold the decision itself with synthetic redirect and expansion state; the
shell-level behaviour is pinned against bash in
tests/conformance/bash/test_null_command_status_conformance.py.
"""
import pytest

from psh.ast_nodes import Redirect
from psh.executor.null_command import (
    null_command_redirects_stdin,
    null_command_status,
)
from psh.io_redirect.redirect_program import target_fd_of


class _State:
    """The only piece of shell state the rule reads."""

    def __init__(self, last_cmdsub_status=None):
        self.last_cmdsub_status = last_cmdsub_status


def _r(type_, target="f", **kw):
    return Redirect(type=type_, target=target, **kw)


class TestSubstitutionStatusClause:
    """Clause 3: the last command substitution's status, else 0."""

    def test_no_substitution_ran_is_zero(self):
        assert null_command_status(_State(None), []) == 0

    def test_the_recorded_status_wins(self):
        assert null_command_status(_State(5), []) == 5

    def test_a_successful_substitution_is_still_reported(self):
        """0 recorded is not the same as nothing recorded, and both give 0 —
        but the rule must read the field rather than short-circuit on falsity."""
        assert null_command_status(_State(0), []) == 0

    def test_an_output_redirect_does_not_erase_it(self):
        assert null_command_status(_State(5), [_r('>')]) == 5
        assert null_command_status(_State(5), [_r('>>')]) == 5
        assert null_command_status(_State(5), [_r('>|')]) == 5
        assert null_command_status(_State(5), [_r('>', fd=2)]) == 5
        assert null_command_status(_State(5), [_r('<', fd=3)]) == 5
        assert null_command_status(_State(5), [_r('>', combined=True)]) == 5


class TestStdinClause:
    """Clause 2: a redirection on fd 0 (or a ``{var}`` fd) erases the status,
    because bash performs those in a forked child that exits success."""

    @pytest.mark.parametrize("redirect", [
        _r('<'),
        _r('<', fd=0),
        _r('>', fd=0),
        _r('<>'),
        _r('<&', target=None, dup_fd=7),
        _r('<&-', target=None),
        _r('<<', target='EOF'),
        _r('<<-', target='EOF'),
        _r('<<<', target='word'),
        _r('<', var_fd='v'),
        _r('>', var_fd='v'),
    ], ids=["lt", "0lt", "0gt", "readwrite", "dup_in", "close_in",
            "heredoc", "heredoc_strip", "herestring", "named_in", "named_out"])
    def test_these_erase_the_status(self, redirect):
        assert null_command_redirects_stdin([redirect]) is True
        assert null_command_status(_State(5), [redirect]) == 0

    @pytest.mark.parametrize("redirect", [
        _r('>'),
        _r('>>'),
        _r('>|'),
        _r('>', fd=2),
        _r('<', fd=3),
        _r('<&', target=None, fd=3, dup_fd=7),
        _r('>&-', target=None),
        _r('>', combined=True),
    ], ids=["gt", "append", "clobber", "stderr", "fd3_in", "fd3_dup",
            "close_out", "combined"])
    def test_these_do_not(self, redirect):
        assert null_command_redirects_stdin([redirect]) is False
        assert null_command_status(_State(5), [redirect]) == 5

    def test_one_stdin_redirect_among_several_is_enough(self):
        redirects = [_r('>', target='o'), _r('<', target='i')]
        assert null_command_redirects_stdin(redirects) is True
        assert null_command_status(_State(5), redirects) == 0


class TestTargetFdIsSharedWithThePlanner:
    """The fd classification is ONE function, so the rule and the redirect
    plan can never disagree about which fd a redirection touches."""

    @pytest.mark.parametrize("redirect,expected", [
        (_r('<'), 0),
        (_r('>'), 1),
        (_r('>>'), 1),
        (_r('<', fd=3), 3),
        (_r('>', fd=2), 2),
        (_r('>', combined=True), 1),
        (_r('<<', target='EOF'), 0),
        (_r('<<<', target='w'), 0),
        (_r('<<', target='EOF', fd=3), 3),
    ])
    def test_target_fd(self, redirect, expected):
        assert target_fd_of(redirect) == expected

    def test_the_planner_property_delegates_to_it(self):
        from psh.io_redirect.planner import RedirectPlan
        redirect = _r('<', fd=3)
        assert RedirectPlan(redirect=redirect, target='f').target_fd == \
            target_fd_of(redirect)
